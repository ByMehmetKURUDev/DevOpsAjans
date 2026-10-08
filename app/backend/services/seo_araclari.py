"""Ücretsiz SEO araçları (Faz 4S) — tek adreslik hızlı kontroller.

Sitedeki `/seo-araclari/<arac>` sayfaları buraya geliyor. On araç var:
meta etiketleri, Open Graph / Twitter kartı, Schema (JSON-LD) okuyucu,
robots.txt test aracı, XML site haritası doğrulayıcı, yönlendirme zinciri,
HTTP güvenlik başlıkları, SSL sertifikası, başlık yapısı (H1–H6) ve
kelime / anahtar kelime yoğunluğu. Hepsi kendi sunucumuzda; dış ücretli API YOK.

Güvenlik
--------
Ağa çıkan HER istek `services/site_analizi.py`'deki ortak SSRF korumalı
istemciden geçiyor (`_istemci` + `Gezgin`): yalnız http/https ve 80/443,
özel/döngü/link-local/meta veri adresleri ret, her yönlendirme adımı yeniden
denetleniyor, doğrudan bağlantıda soket denetlenmiş IP'ye açılıyor (DNS
rebinding), gövde 1,5 MB'ta kesiliyor, her istek 10 sn, bütün araç 25 sn.
İkincil adresler (og:image, site haritası örneklemi) de aynı denetimden geçer;
iç ağa çıkan bir ikincil adres İSTEK ATILMADAN "reddedildi" diye işaretlenir.

Gizlilik: sorgulanan adres hiçbir yere yazılmıyor (veritabanı, günlük). Gezgin
`gunlukle=False` ile kuruluyor; router yalnız araç başına günlük sayaç tutuyor.
"Sonucu e-postayla gönder" seçeneği açıkken sonuç YALNIZ bellekte, en çok 30
dakika (`SonucOnbellegi`) duruyor; e-posta gönderilince siliniyor. E-postayı
isteyen ziyaretçi CRM'e aday olarak yazılıyor (adres + kısa özetle — talebin
kendisi; bkz. `routers/seo_araclari.py`).

Çıktı
-----
Bulgular metin taşımıyor: `{kontrol, kod, seviye, deger}` — cümleyi ön yüz
yedi dilde kuruyor (`seoAracSonuc.bulgu.<kod>`, `seoAracSonuc.kontrol.<k>`
→ ad / neden önemli / nasıl düzeltilir). `veri` araca özel ham ölçümler;
hedef sitenin metinleri yalnız DÜZ METİN olarak dönüyor (ön yüz HTML basmıyor).
"""

import asyncio
import html as html_modulu
import json
import logging
import os
import re
import secrets
import struct
import time
import unicodedata
import zlib
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlencode, urljoin, urlsplit, urlunsplit

from services import site_analizi as motor
from services import site_inceleme as si

AnalizHatasi = motor.AnalizHatasi
logger = logging.getLogger(__name__)

# httpx her isteği INFO (adresle), httpcore bağlantıyı DEBUG (host'la) düzeyinde günlüğe yazıyor;
# `main.py` kök günlüğü DEBUG'da olduğu için sorgulanan adresler dosyaya ve konsola düşüyordu
# (sorgu parametresindeki anahtarlar da — ör. PageSpeed `key=`). Araçlarda adres kalıcı
# tutulmamalı: bu iki kütüphanenin günlüğü yalnız uyarı ve üstü.
for _ad in ("httpx", "httpcore"):
    logging.getLogger(_ad).setLevel(logging.WARNING)

#: Araç kısa adları (adres ve sayaç anahtarı). Ön yüzdeki liste
#: (`prerender/seo-araclari-veri.js`) aynı sırada; test karşılaştırıyor.
ARACLAR: Tuple[str, ...] = (
    "meta-etiketleri",
    "open-graph",
    "schema-okuyucu",
    "robots-txt",
    "site-haritasi",
    "yonlendirme",
    "guvenlik-basliklari",
    "ssl-sertifikasi",
    "baslik-yapisi",
    "kelime-yogunlugu",
)

ISTEK_ZAMAN_ASIMI = 10.0       # tek istek, saniye
TOPLAM_TAVAN = 25.0            # bütün araç, saniye
ESZAMANLILIK = 4
AJAN = "MehmetKuruDevSeoAraclari/1.0 (+https://mehmetkuru.dev/seo-araclari)"

METIN_TAVANI = 500             # dönen tek metin alanı (başlık, açıklama…) en çok
ROBOTS_GOOGLE_TAVANI = 512_000  # Google robots.txt'nin ilk 500 KiB'ını okur
SITEMAP_URL_TAVANI = 50_000
SITEMAP_ACIK_TAVAN = 10_000_000  # .gz açılınca en çok bu kadar bayt
ORNEKLEM = 10
SEVIYELER = ("hata", "uyari", "bilgi", "iyi")


# --------------------------------------------------------------------------
# Sonuç
# --------------------------------------------------------------------------
class Sonuc:
    def __init__(self, arac: str):
        self.arac = arac
        self.bulgular: List[Dict[str, Any]] = []
        self.veri: Dict[str, Any] = {}
        self.puan: Optional[int] = None

    def ekle(self, kontrol: str, kod: str, seviye: str, deger: Any = None) -> None:
        bulgu: Dict[str, Any] = {"kontrol": kontrol, "kod": kod, "seviye": seviye}
        if deger is not None:
            bulgu["deger"] = deger
        self.bulgular.append(bulgu)

    def sozluk(self, url: str, son_url: Optional[str] = None, durum: Optional[int] = None) -> Dict[str, Any]:
        sayilar = {s: 0 for s in SEVIYELER}
        for b in self.bulgular:
            sayilar[b["seviye"]] = sayilar.get(b["seviye"], 0) + 1
        return {
            "arac": self.arac,
            "url": url,
            "son_url": son_url or url,
            "durum": durum,
            "puan": self.puan,
            "ozet": sayilar,
            "bulgular": self.bulgular,
            "veri": self.veri,
        }


def _kisalt(metin: Optional[str], tavan: int = METIN_TAVANI) -> str:
    m = re.sub(r"\s+", " ", metin or "").strip()
    return m if len(m) <= tavan else m[: tavan - 1].rstrip() + "…"


def _koken(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def _ayni_adres(a: str, b: str) -> bool:
    """Sondaki eğik çizgi ve parça farkı yok sayılarak aynı adres mi?"""
    def temiz(u: str) -> str:
        p = urlsplit(u.split("#", 1)[0])
        yol = p.path.rstrip("/") or "/"
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), yol, p.query, ""))
    return temiz(a) == temiz(b)


# --------------------------------------------------------------------------
# HTML okuma (regex; ayrıştırıcı bağımlılığı yok — bkz. site_inceleme)
# --------------------------------------------------------------------------
_HEAD_SONU = re.compile(r"</head\s*>", re.I)
_BETIK_STIL = re.compile(r"<(script|style|noscript|template)\b[^>]*>.*?</\1\s*>", re.I | re.S)
#: Tırnak içindeki `>` etiketi bitirmesin (`content="a <b> c"` geçerli HTML).
_ETIKET = re.compile(r"""<(meta|link)\b((?:[^>"']|"[^"]*"|'[^']*')*)>""", re.I)
_OZNITELIK = re.compile(r"""([^\s=/>"']+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'>]+))?""")
_HTML_ETIKETI = re.compile(r"""<html\b((?:[^>"']|"[^"]*"|'[^']*')*)>""", re.I)
_BASLIK = re.compile(r"<title\b[^>]*>(.*?)</title\s*>", re.I | re.S)


def oznitelikler(ham: str) -> Dict[str, str]:
    d: Dict[str, str] = {}
    for ad, deger in _OZNITELIK.findall(ham or ""):
        ad = ad.lower()
        if ad in d:
            continue
        if deger[:1] in ("'", '"'):
            deger = deger[1:-1]
        d[ad] = html_modulu.unescape(deger).strip()
    return d


def bas_bolumu(html: str) -> str:
    """<head> bölümü (yorum, betik ve stil gövdeleri çıkarılmış). </head> yoksa ilk 300 kB."""
    m = _HEAD_SONU.search(html)
    bas = html[: m.start()] if m else html[:300_000]
    bas = si._YORUM.sub(" ", bas)
    return _BETIK_STIL.sub(" ", bas)


def etiketler(bas: str, tur: str) -> List[Dict[str, str]]:
    return [oznitelikler(o) for t, o in _ETIKET.findall(bas) if t.lower() == tur]


def duz_metin(ham: str) -> str:
    return re.sub(r"\s+", " ", html_modulu.unescape(si.ETIKET_TEMIZ.sub(" ", ham or ""))).strip()


def html_dili(html: str) -> str:
    m = _HTML_ETIKETI.search(html[:50_000])
    if not m:
        return ""
    o = oznitelikler(m.group(1))
    return (o.get("lang") or o.get("xml:lang") or "").strip()


def _metalar(bas: str) -> Dict[str, List[str]]:
    """name= ya da property= → içerik listesi (anahtar küçük harf)."""
    sonuc: Dict[str, List[str]] = {}
    for o in etiketler(bas, "meta"):
        ad = (o.get("property") or o.get("name") or "").strip().lower()
        if ad and "content" in o:
            sonuc.setdefault(ad, []).append(o.get("content", ""))
    return sonuc


def _rel(o: Dict[str, str]) -> List[str]:
    return [p.lower() for p in (o.get("rel") or "").split()]


# --------------------------------------------------------------------------
# Ortak getirme
# --------------------------------------------------------------------------
async def _ana_sayfa(gezgin: motor.Gezgin, url: str, govde_oku: bool = True) -> motor.Yanit:
    y = await gezgin.getir(url, govde_oku=govde_oku)
    if y.hata in ("adres_yasak", "adres_gecersiz"):
        # Genel bir adres iç ağa (ya da izinsiz porta) yönlendirdi: açıkça reddet.
        raise AnalizHatasi("adres_yasak")
    if y.durum == 0:
        raise AnalizHatasi(y.hata or "ulasilamadi")
    return y


# ==========================================================================
# 1) Meta etiketleri
# ==========================================================================
_LANG_DESENI = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$")
_HREFLANG_DESENI = re.compile(r"^(x-default|[a-z]{2,3}(-[a-z]{4})?(-([a-z]{2}|\d{3}))?)$", re.I)


def meta_incele(sonuc: Sonuc, html: str, son_url: str, basliklar: Dict[str, str]) -> None:
    bas = bas_bolumu(html)
    metalar = _metalar(bas)
    linkler = etiketler(bas, "link")

    # Başlık
    basliklar_ = [duz_metin(m) for m in _BASLIK.findall(bas)]
    baslik = basliklar_[0] if basliklar_ else ""
    if not baslik:
        sonuc.ekle("title", "title_yok", "hata")
    else:
        g = si.genislik(baslik)
        if g < motor.BASLIK_ALT:
            sonuc.ekle("title", "title_kisa", "uyari", g)
        elif g > motor.BASLIK_UST:
            sonuc.ekle("title", "title_uzun", "uyari", g)
        else:
            sonuc.ekle("title", "title_iyi", "iyi", g)
        if len(basliklar_) > 1:
            sonuc.ekle("title", "title_coklu", "uyari", len(basliklar_))

    # Açıklama
    aciklamalar = metalar.get("description", [])
    aciklama = (aciklamalar[0] if aciklamalar else "").strip()
    if not aciklama:
        sonuc.ekle("aciklama", "aciklama_yok", "hata")
    else:
        g = si.genislik(aciklama)
        if g < motor.ACIKLAMA_ALT:
            sonuc.ekle("aciklama", "aciklama_kisa", "uyari", g)
        elif g > motor.ACIKLAMA_UST:
            sonuc.ekle("aciklama", "aciklama_uzun", "uyari", g)
        else:
            sonuc.ekle("aciklama", "aciklama_iyi", "iyi", g)
        if len(aciklamalar) > 1:
            sonuc.ekle("aciklama", "aciklama_coklu", "uyari", len(aciklamalar))

    # Canonical
    kanonikler = [o.get("href", "") for o in linkler if "canonical" in _rel(o)]
    if not kanonikler:
        sonuc.ekle("canonical", "canonical_yok", "uyari")
    elif len(kanonikler) > 1:
        sonuc.ekle("canonical", "canonical_coklu", "hata", len(kanonikler))
    else:
        ham = kanonikler[0].strip()
        mutlak = urljoin(son_url, ham)
        if not ham:
            sonuc.ekle("canonical", "canonical_yok", "uyari")
        elif not re.match(r"^https?://", ham, re.I):
            sonuc.ekle("canonical", "canonical_goreli", "uyari", _kisalt(ham, 300))
        elif not _ayni_adres(mutlak, son_url):
            sonuc.ekle("canonical", "canonical_baska", "bilgi", _kisalt(mutlak, 300))
        else:
            sonuc.ekle("canonical", "canonical_iyi", "iyi")

    # Robots (meta + X-Robots-Tag başlığı)
    robots = ", ".join(metalar.get("robots", []) + metalar.get("googlebot", [])).lower()
    x_robots = (basliklar.get("x-robots-tag") or "").lower()
    if "noindex" in robots or "none" in [p.strip() for p in robots.split(",")]:
        sonuc.ekle("robots_meta", "robots_noindex", "hata", "meta")
    elif "noindex" in x_robots:
        sonuc.ekle("robots_meta", "robots_noindex", "hata", "X-Robots-Tag")
    elif "nofollow" in robots or "nofollow" in x_robots:
        sonuc.ekle("robots_meta", "robots_nofollow", "uyari")
    else:
        sonuc.ekle("robots_meta", "robots_iyi", "iyi")

    # Viewport
    viewport = (metalar.get("viewport") or [""])[0].strip()
    vp = {k.strip().lower(): v.strip().lower() for k, _, v in (p.partition("=") for p in re.split(r"[,;]", viewport)) if k.strip()}
    if not viewport:
        sonuc.ekle("viewport", "viewport_yok", "hata")
    elif vp.get("width") != "device-width":
        sonuc.ekle("viewport", "viewport_genislik", "uyari")
    else:
        kucultme_kapali = vp.get("user-scalable") in ("no", "0")
        try:
            kucultme_kapali = kucultme_kapali or float(vp.get("maximum-scale", "10")) < 2
        except ValueError:
            pass
        if kucultme_kapali:
            sonuc.ekle("viewport", "viewport_yakinlastirma", "uyari")
        else:
            sonuc.ekle("viewport", "viewport_iyi", "iyi")

    # lang
    dil = html_dili(html)
    if not dil:
        sonuc.ekle("lang", "lang_yok", "uyari")
    elif not _LANG_DESENI.match(dil):
        sonuc.ekle("lang", "lang_gecersiz", "uyari", _kisalt(dil, 40))
    else:
        sonuc.ekle("lang", "lang_iyi", "iyi", dil)

    # hreflang
    hreflar = [
        {"dil": o.get("hreflang", "").strip(), "adres": o.get("href", "").strip()}
        for o in linkler
        if "alternate" in _rel(o) and o.get("hreflang")
    ]
    if not hreflar:
        sonuc.ekle("hreflang", "hreflang_yok", "bilgi")
    else:
        gecersiz = sorted({h["dil"] for h in hreflar if not _HREFLANG_DESENI.match(h["dil"])})
        sayac = Counter(h["dil"].lower() for h in hreflar)
        tekrar = sorted(k for k, v in sayac.items() if v > 1)
        kendisi = any(h["adres"] and _ayni_adres(urljoin(son_url, h["adres"]), son_url) for h in hreflar)
        sorun = False
        if gecersiz:
            sonuc.ekle("hreflang", "hreflang_gecersiz", "hata", ", ".join(gecersiz)[:200])
            sorun = True
        if tekrar:
            sonuc.ekle("hreflang", "hreflang_tekrar", "uyari", ", ".join(tekrar)[:200])
            sorun = True
        if not kendisi:
            sonuc.ekle("hreflang", "hreflang_kendisi_yok", "uyari")
            sorun = True
        if "x-default" not in sayac:
            sonuc.ekle("hreflang", "hreflang_xdefault_yok", "bilgi")
        if not sorun:
            sonuc.ekle("hreflang", "hreflang_iyi", "iyi", len(hreflar))

    sonuc.veri.update(
        {
            "baslik": _kisalt(baslik),
            "baslik_karakter": len(baslik),
            "baslik_genislik": si.genislik(baslik),
            "aciklama": _kisalt(aciklama),
            "aciklama_karakter": len(aciklama),
            "aciklama_genislik": si.genislik(aciklama),
            "canonical": [_kisalt(k, 300) for k in kanonikler[:5]],
            "robots": _kisalt(robots, 200),
            "x_robots": _kisalt(x_robots, 200),
            "viewport": _kisalt(viewport, 200),
            "lang": _kisalt(dil, 40),
            "hreflang": [{"dil": _kisalt(h["dil"], 20), "adres": _kisalt(h["adres"], 300)} for h in hreflar[:50]],
        }
    )


async def meta_etiketleri(gezgin: motor.Gezgin, url: str, secenek: Dict[str, Any]) -> Dict[str, Any]:
    y = await _ana_sayfa(gezgin, url)
    s = Sonuc("meta-etiketleri")
    meta_incele(s, y.govde, y.url, y.basliklar)
    return s.sozluk(url, y.url, y.durum)


# ==========================================================================
# 2) Open Graph / Twitter kartı
# ==========================================================================
def gorsel_boyutu(ham: bytes) -> Optional[Tuple[int, int]]:
    """PNG, GIF, JPEG ve WebP başlığından (genişlik, yükseklik); bilinmiyorsa None."""
    try:
        if ham[:8] == b"\x89PNG\r\n\x1a\n" and len(ham) >= 24:
            return struct.unpack(">II", ham[16:24])
        if ham[:6] in (b"GIF87a", b"GIF89a") and len(ham) >= 10:
            return struct.unpack("<HH", ham[6:10])
        if ham[:4] == b"RIFF" and ham[8:12] == b"WEBP" and len(ham) >= 30:
            parca = ham[12:16]
            if parca == b"VP8X":
                g = 1 + int.from_bytes(ham[24:27], "little")
                y = 1 + int.from_bytes(ham[27:30], "little")
                return g, y
            if parca == b"VP8 " and len(ham) >= 30:
                g, y = struct.unpack("<HH", ham[26:30])
                return g & 0x3FFF, y & 0x3FFF
            if parca == b"VP8L" and len(ham) >= 25:
                b0, b1, b2, b3 = ham[21:25]
                g = 1 + (((b1 & 0x3F) << 8) | b0)
                y = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
                return g, y
        if ham[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(ham):
                if ham[i] != 0xFF:
                    i += 1
                    continue
                isaret = ham[i + 1]
                if isaret in (0xD8, 0x01) or 0xD0 <= isaret <= 0xD7:
                    i += 2
                    continue
                uzunluk = struct.unpack(">H", ham[i + 2 : i + 4])[0]
                if isaret in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    y, g = struct.unpack(">HH", ham[i + 5 : i + 9])
                    return g, y
                i += 2 + uzunluk
    except (struct.error, IndexError, ValueError):
        return None
    return None


_TWITTER_KARTLARI = ("summary", "summary_large_image", "app", "player")


async def _gorsel_incele(gezgin: motor.Gezgin, adres: str) -> Dict[str, Any]:
    g: Dict[str, Any] = {"url": _kisalt(adres, 500), "https": adres.lower().startswith("https://")}
    y = await gezgin.getir(adres, ham_oku=True)
    if y.hata:
        g["hata"] = y.hata
        return g
    g["durum"] = y.durum
    g["tur"] = _kisalt((y.basliklar.get("content-type") or "").split(";", 1)[0], 80)
    try:
        g["boyut_bayt"] = int(y.basliklar.get("content-length") or 0) or (None if y.kesildi else len(y.ham))
    except ValueError:
        g["boyut_bayt"] = None if y.kesildi else len(y.ham)
    boyut = gorsel_boyutu(y.ham) if y.durum == 200 else None
    if boyut:
        g["genislik"], g["yukseklik"] = boyut
    return g


async def open_graph(gezgin: motor.Gezgin, url: str, secenek: Dict[str, Any]) -> Dict[str, Any]:
    y = await _ana_sayfa(gezgin, url)
    s = Sonuc("open-graph")
    bas = bas_bolumu(y.govde)
    metalar = _metalar(bas)

    def ilk(*adlar: str) -> str:
        for ad in adlar:
            for deger in metalar.get(ad, []):
                if deger.strip():
                    return deger.strip()
        return ""

    og = {ad: ilk(ad) for ad in ("og:title", "og:description", "og:image", "og:url", "og:type", "og:site_name", "og:locale", "og:image:alt")}
    tw = {ad: ilk(ad) for ad in ("twitter:card", "twitter:title", "twitter:description", "twitter:image", "twitter:site")}
    sayfa_basligi = duz_metin((_BASLIK.findall(bas) or [""])[0])
    sayfa_aciklamasi = ilk("description")

    eksik = False
    if not og["og:title"]:
        s.ekle("og_etiketleri", "og_baslik_yok", "uyari")
        eksik = True
    if not og["og:description"]:
        s.ekle("og_etiketleri", "og_aciklama_yok", "uyari")
        eksik = True
    if not og["og:url"]:
        s.ekle("og_etiketleri", "og_url_yok", "bilgi")
        eksik = True
    if not og["og:type"]:
        s.ekle("og_etiketleri", "og_type_yok", "bilgi")
        eksik = True
    if not eksik:
        s.ekle("og_etiketleri", "og_tamam", "iyi")

    kart = tw["twitter:card"].lower()
    if not kart:
        s.ekle("twitter_karti", "twitter_kart_yok", "uyari")
    elif kart not in _TWITTER_KARTLARI:
        s.ekle("twitter_karti", "twitter_kart_gecersiz", "uyari", _kisalt(kart, 40))
    else:
        s.ekle("twitter_karti", "twitter_kart_iyi", "iyi", kart)

    gorsel: Optional[Dict[str, Any]] = None
    gorsel_ham = og["og:image"] or tw["twitter:image"]
    if not gorsel_ham:
        s.ekle("og_gorsel", "og_gorsel_yok", "hata")
    else:
        adres = urljoin(y.url, gorsel_ham)
        if not re.match(r"^https?://", gorsel_ham, re.I):
            s.ekle("og_gorsel", "og_gorsel_goreli", "uyari")
        if not re.match(r"^https?://", adres, re.I):
            gorsel = {"url": _kisalt(adres, 500), "hata": "adres_gecersiz", "https": False}
        else:
            gorsel = await _gorsel_incele(gezgin, adres)
        if gorsel.get("hata") or gorsel.get("durum") != 200:
            s.ekle("og_gorsel", "gorsel_erisilemedi", "hata", gorsel.get("hata") or gorsel.get("durum"))
        elif not str(gorsel.get("tur", "")).startswith("image/"):
            s.ekle("og_gorsel", "gorsel_tur_yanlis", "hata", gorsel.get("tur") or "-")
        else:
            sorun = False
            gn, yk = gorsel.get("genislik"), gorsel.get("yukseklik")
            if gn and yk:
                if gn < 200 or yk < 200:
                    s.ekle("og_gorsel", "gorsel_kucuk", "hata", f"{gn}×{yk}")
                    sorun = True
                elif gn < 1200 or yk < 630:
                    s.ekle("og_gorsel", "gorsel_onerilen_alti", "uyari", f"{gn}×{yk}")
                    sorun = True
                if abs(gn / yk - 1.91) > 0.3:
                    s.ekle("og_gorsel", "gorsel_oran", "bilgi", f"{gn}×{yk}")
            else:
                s.ekle("og_gorsel", "gorsel_boyut_bilinmiyor", "bilgi")
            bayt = gorsel.get("boyut_bayt")
            if bayt and bayt > 5_000_000:
                s.ekle("og_gorsel", "gorsel_buyuk", "uyari", round(bayt / 1024))
                sorun = True
            elif bayt and bayt > 1_000_000:
                s.ekle("og_gorsel", "gorsel_agir", "bilgi", round(bayt / 1024))
            if not gorsel.get("https"):
                s.ekle("og_gorsel", "gorsel_http", "uyari")
                sorun = True
            if not sorun and gn and yk:
                s.ekle("og_gorsel", "gorsel_iyi", "iyi", f"{gn}×{yk}")

    alan = urlsplit(og["og:url"] if re.match(r"^https?://", og["og:url"], re.I) else y.url).hostname or ""
    onizleme_gorsel = None
    if gorsel and gorsel.get("https") and gorsel.get("durum") == 200 and str(gorsel.get("tur", "")).startswith("image/"):
        onizleme_gorsel = gorsel["url"]
    s.veri.update(
        {
            "og": {k: _kisalt(v) for k, v in og.items() if v},
            "twitter": {k: _kisalt(v) for k, v in tw.items() if v},
            "gorsel": gorsel,
            "onizleme": {
                "baslik": _kisalt(og["og:title"] or tw["twitter:title"] or sayfa_basligi, 200),
                "aciklama": _kisalt(og["og:description"] or tw["twitter:description"] or sayfa_aciklamasi, 300),
                "alan": _kisalt(alan, 200),
                "gorsel": onizleme_gorsel,
                "kart": kart or "summary",
            },
        }
    )
    return s.sozluk(url, y.url, y.durum)


# ==========================================================================
# 3) Schema (JSON-LD) okuyucu
# ==========================================================================
_JSONLD_BLOK = re.compile(
    r"<script\b[^>]*type\s*=\s*[\"']?application/ld\+json[\"']?[^>]*>(.*?)</script\s*>", re.I | re.S
)
_MIKROVERI = re.compile(r"\sitemtype\s*=\s*[\"']([^\"']+)[\"']", re.I)
_RDFA = re.compile(r"\stypeof\s*=\s*[\"']([^\"']+)[\"']", re.I)

_MAKALE = ("Article", "NewsArticle", "BlogPosting", "TechArticle", "Report", "ScholarlyArticle")
_ISLETME = (
    "LocalBusiness", "Restaurant", "Store", "ProfessionalService", "MedicalBusiness", "Dentist",
    "AutoRepair", "BeautySalon", "HairSalon", "LegalService", "Attorney", "RealEstateAgent",
    "FoodEstablishment", "CafeOrCoffeeShop", "Bakery", "HomeAndConstructionBusiness", "Hotel",
    "LodgingBusiness", "HealthAndBeautyBusiness", "SportsActivityLocation", "FinancialService",
    "AccountingService", "TravelAgency", "EducationalOrganization",
)
_YAZILIM = ("SoftwareApplication", "WebApplication", "MobileApplication", "VideoGame")

#: Tür → (zorunlu, önerilen). Zorunlu listede "a|b" = ikisinden biri yeter.
#: Temel kurallar: Google arama zengin sonuç belgelerindeki zorunlu alanlar ve
#: schema.org'un sağduyulu asgarisi; tam doğrulayıcı değil.
SCHEMA_KURALLARI: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "Organization": (("name",), ("url", "logo")),
    "Person": (("name",), ()),
    "WebSite": (("name", "url"), ()),
    "WebPage": ((), ("name",)),
    "Product": (("name", "offers|review|aggregateRating"), ("image", "description", "brand")),
    "Offer": (("price|priceSpecification", "priceCurrency|priceSpecification"), ("availability", "url")),
    "AggregateOffer": (("lowPrice", "priceCurrency"), ("highPrice", "offerCount")),
    "BreadcrumbList": (("itemListElement",), ()),
    "ItemList": (("itemListElement",), ()),
    "FAQPage": (("mainEntity",), ()),
    "Event": (("name", "startDate", "location"), ("endDate", "eventStatus", "image", "offers")),
    "Recipe": (("name", "image"), ("recipeIngredient", "recipeInstructions", "author")),
    "JobPosting": (("title", "description", "datePosted", "hiringOrganization"), ("validThrough", "employmentType", "baseSalary")),
    "Review": (("itemReviewed|@nested", "reviewRating", "author"), ()),
    "AggregateRating": (("ratingValue", "ratingCount|reviewCount"), ()),
    "VideoObject": (("name", "thumbnailUrl", "uploadDate"), ("description", "contentUrl", "duration")),
    "HowTo": (("name", "step"), ("totalTime", "image")),
    "Course": (("name", "description"), ("provider",)),
    "Service": (("name",), ("provider", "areaServed")),
    "ImageObject": (("contentUrl|url",), ()),
}
for _t in _MAKALE:
    SCHEMA_KURALLARI[_t] = (("headline",), ("image", "datePublished", "author"))
for _t in _ISLETME:
    SCHEMA_KURALLARI[_t] = (("name", "address"), ("telephone", "openingHoursSpecification|openingHours", "url", "image"))
for _t in _YAZILIM:
    SCHEMA_KURALLARI[_t] = (("name", "offers"), ("applicationCategory", "operatingSystem", "aggregateRating|review"))


def _turler(nesne: Dict[str, Any]) -> List[str]:
    t = nesne.get("@type")
    if isinstance(t, str):
        return [t.rsplit("/", 1)[-1]]
    if isinstance(t, list):
        return [str(x).rsplit("/", 1)[-1] for x in t if isinstance(x, (str, int))]
    return []


def _dolu(deger: Any) -> bool:
    if deger is None:
        return False
    if isinstance(deger, str):
        return bool(deger.strip())
    if isinstance(deger, (list, dict)):
        return len(deger) > 0
    return True


def _alan_var(nesne: Dict[str, Any], kural: str, ic_ice: bool) -> bool:
    for parca in kural.split("|"):
        if parca == "@nested":
            if ic_ice:
                return True
            continue
        if _dolu(nesne.get(parca)):
            return True
    return False


def _alan_denetimi(nesne: Dict[str, Any], tur: str, ic_ice: bool) -> Tuple[List[str], List[str]]:
    zorunlu, onerilen = SCHEMA_KURALLARI.get(tur, ((), ()))
    eksik_z = [k.replace("|@nested", "") for k in zorunlu if not _alan_var(nesne, k, ic_ice)]
    eksik_o = [k for k in onerilen if not _alan_var(nesne, k, ic_ice)]
    # BreadcrumbList / FAQPage alt öğeleri
    if tur == "BreadcrumbList" and isinstance(nesne.get("itemListElement"), list):
        for i, oge in enumerate(nesne["itemListElement"][:50], 1):
            if not isinstance(oge, dict):
                continue
            ad_var = _dolu(oge.get("name")) or (isinstance(oge.get("item"), dict) and _dolu(oge["item"].get("name")))
            if not _dolu(oge.get("position")):
                eksik_z.append(f"itemListElement[{i}].position")
            if not ad_var:
                eksik_z.append(f"itemListElement[{i}].name")
    if tur == "FAQPage":
        sorular = nesne.get("mainEntity")
        sorular = sorular if isinstance(sorular, list) else [sorular] if isinstance(sorular, dict) else []
        for i, soru in enumerate(sorular[:50], 1):
            if not isinstance(soru, dict):
                continue
            if not _dolu(soru.get("name")):
                eksik_z.append(f"mainEntity[{i}].name")
            cevap = soru.get("acceptedAnswer")
            if not (isinstance(cevap, dict) and _dolu(cevap.get("text"))):
                eksik_z.append(f"mainEntity[{i}].acceptedAnswer.text")
    return eksik_z[:20], eksik_o[:10]


def _ogeleri_topla(veri: Any, ogeler: List[Dict[str, Any]], ic_ice: bool = False, derinlik: int = 0) -> None:
    """Türü olan nesneleri (üst düzey + @graph + iç içe) sırayla toplar."""
    if derinlik > 8 or len(ogeler) >= 200:
        return
    if isinstance(veri, list):
        for x in veri:
            _ogeleri_topla(x, ogeler, ic_ice, derinlik + 1)
        return
    if not isinstance(veri, dict):
        return
    if "@graph" in veri and isinstance(veri["@graph"], list):
        for x in veri["@graph"]:
            _ogeleri_topla(x, ogeler, False, derinlik + 1)
    turler = _turler(veri)
    if turler:
        ogeler.append({"nesne": veri, "turler": turler, "ic_ice": ic_ice})
    for anahtar, deger in veri.items():
        if anahtar in ("@graph", "@context"):
            continue
        if isinstance(deger, (dict, list)):
            _ogeleri_topla(deger, ogeler, bool(turler) or ic_ice, derinlik + 1)


def jsonld_incele(sonuc: Sonuc, html: str) -> None:
    bloklar = _JSONLD_BLOK.findall(html)
    veri_bloklari: List[Dict[str, Any]] = []
    ogeler: List[Dict[str, Any]] = []
    hatali = 0
    context_sorunu = 0
    for sira, ham in enumerate(bloklar[:30], 1):
        metin = ham.strip()
        metin = re.sub(r"^\s*(<!--|/\*\s*<!\[CDATA\[\s*\*/)", "", metin)
        metin = re.sub(r"(-->|/\*\s*\]\]>\s*\*/)\s*$", "", metin).strip()
        blok: Dict[str, Any] = {"sira": sira, "boyut": len(metin), "metin": metin[:4000]}
        try:
            veri = json.loads(metin)
        except json.JSONDecodeError as exc:
            hatali += 1
            blok.update({"gecerli": False, "hata": {"satir": exc.lineno, "sutun": exc.colno, "mesaj": exc.msg[:120]}})
            veri_bloklari.append(blok)
            sonuc.ekle("jsonld_sozdizimi", "jsonld_sozdizimi", "hata",
                       {"blok": sira, "satir": exc.lineno, "sutun": exc.colno, "mesaj": exc.msg[:120]})
            continue
        blok["gecerli"] = True
        try:
            blok["metin"] = json.dumps(veri, ensure_ascii=False, indent=2)[:4000]
        except (TypeError, ValueError):
            pass
        kokler = veri if isinstance(veri, list) else [veri]
        for kok in kokler:
            if isinstance(kok, dict):
                ctx = kok.get("@context")
                ctx_metni = json.dumps(ctx) if ctx is not None else ""
                if "schema.org" not in ctx_metni:
                    context_sorunu += 1
        once = len(ogeler)
        _ogeleri_topla(veri, ogeler)
        blok["turler"] = sorted({t for o in ogeler[once:] if not o["ic_ice"] for t in o["turler"]})
        veri_bloklari.append(blok)

    if not bloklar:
        sonuc.ekle("jsonld_turler", "jsonld_yok", "uyari")
    elif not hatali:
        sonuc.ekle("jsonld_sozdizimi", "jsonld_sozdizimi_iyi", "iyi", len(bloklar))
    if context_sorunu:
        sonuc.ekle("jsonld_sozdizimi", "jsonld_context", "uyari", context_sorunu)

    ust_ogeler = [o for o in ogeler if not o["ic_ice"]]
    if bloklar and not ust_ogeler and hatali < len(bloklar):
        sonuc.ekle("jsonld_turler", "jsonld_tur_yok", "uyari")
    elif ust_ogeler:
        sonuc.ekle("jsonld_turler", "jsonld_turler_var", "iyi",
                   ", ".join(sorted({t for o in ust_ogeler for t in o["turler"]}))[:200])

    oge_ozeti: List[Dict[str, Any]] = []
    eksik_toplam = 0
    onerilen_toplam = 0
    for o in ogeler[:60]:
        for tur in o["turler"][:3]:
            if tur not in SCHEMA_KURALLARI and o["ic_ice"]:
                continue
            eksik_z, eksik_o = _alan_denetimi(o["nesne"], tur, o["ic_ice"])
            nesne = o["nesne"]
            ad = nesne.get("name") or nesne.get("headline") or nesne.get("title") or ""
            oge_ozeti.append(
                {
                    "tur": tur[:60],
                    "ad": _kisalt(ad if isinstance(ad, str) else "", 120),
                    "ic_ice": o["ic_ice"],
                    "bilinen": tur in SCHEMA_KURALLARI,
                    "eksik_zorunlu": eksik_z,
                    "eksik_onerilen": eksik_o,
                    "alanlar": sorted(k for k in nesne.keys() if isinstance(k, str) and not k.startswith("@"))[:30],
                }
            )
            if eksik_z:
                eksik_toplam += 1
                sonuc.ekle("jsonld_alanlar", "jsonld_alan_eksik", "hata",
                           {"tur": tur[:60], "alanlar": ", ".join(eksik_z)[:300]})
            if eksik_o and not o["ic_ice"]:
                onerilen_toplam += 1
                sonuc.ekle("jsonld_alanlar", "jsonld_onerilen_eksik", "bilgi",
                           {"tur": tur[:60], "alanlar": ", ".join(eksik_o)[:300]})
    if ust_ogeler and not eksik_toplam:
        sonuc.ekle("jsonld_alanlar", "jsonld_alanlar_iyi", "iyi")

    mikro = sorted({m.rsplit("/", 1)[-1] for m in _MIKROVERI.findall(html)})[:20]
    rdfa = sorted({m for m in _RDFA.findall(html)})[:20]
    if mikro or rdfa:
        sonuc.ekle("jsonld_turler", "mikroveri_var", "bilgi", ", ".join(mikro + rdfa)[:200])

    sonuc.veri.update({"bloklar": veri_bloklari, "ogeler": oge_ozeti, "mikroveri": mikro, "rdfa": rdfa})


async def schema_okuyucu(gezgin: motor.Gezgin, url: str, secenek: Dict[str, Any]) -> Dict[str, Any]:
    y = await _ana_sayfa(gezgin, url)
    s = Sonuc("schema-okuyucu")
    jsonld_incele(s, y.govde)
    return s.sozluk(url, y.url, y.durum)


# ==========================================================================
# 4) robots.txt test aracı
# ==========================================================================
AJANLAR = (
    "Googlebot", "Googlebot-Image", "Bingbot", "YandexBot", "Applebot", "DuckDuckBot",
    "GPTBot", "OAI-SearchBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot", "*",
)
_AJAN_DESENI = re.compile(r"^[A-Za-z0-9._*-]{1,40}$")
_BILINEN_YONERGELER = {"user-agent", "allow", "disallow", "sitemap", "crawl-delay", "host", "clean-param", "noindex"}


def ajan_dogrula(ham: Optional[str]) -> str:
    a = (ham or "Googlebot").strip()
    if not _AJAN_DESENI.match(a):
        raise AnalizHatasi("ajan_gecersiz")
    return a


def robots_coz(metin: str) -> Dict[str, Any]:
    """Satır numaralı gruplar, site haritaları ve söz dizimi uyarıları."""
    gruplar: List[Dict[str, Any]] = []
    sitemapler: List[str] = []
    bilinmeyen: List[int] = []
    ajansiz: List[int] = []
    crawl_delay: List[int] = []
    simdiki: Optional[Dict[str, Any]] = None
    kural_goruldu = False
    for no, satir in enumerate(metin.splitlines(), 1):
        temiz = satir.split("#", 1)[0].strip()
        if not temiz:
            continue
        if ":" not in temiz:
            bilinmeyen.append(no)
            continue
        alan, deger = temiz.split(":", 1)
        alan = alan.strip().lower()
        deger = deger.strip()
        if alan not in _BILINEN_YONERGELER:
            bilinmeyen.append(no)
            continue
        if alan == "sitemap":
            if deger:
                sitemapler.append(deger)
            continue
        if alan == "user-agent":
            if simdiki is None or kural_goruldu:
                simdiki = {"ajanlar": [], "kurallar": [], "satir": no}
                gruplar.append(simdiki)
                kural_goruldu = False
            simdiki["ajanlar"].append(deger.lower())
            continue
        if alan == "crawl-delay":
            crawl_delay.append(no)
        if simdiki is None:
            ajansiz.append(no)
            continue
        kural_goruldu = True
        if alan in ("allow", "disallow"):
            simdiki["kurallar"].append({"alan": alan, "deger": deger, "satir": no})
    return {
        "gruplar": gruplar,
        "sitemapler": sitemapler,
        "bilinmeyen": bilinmeyen[:50],
        "ajansiz": ajansiz[:50],
        "crawl_delay": crawl_delay[:20],
    }


def _ajan_gruplari(gruplar: List[Dict[str, Any]], ajan: str) -> List[Dict[str, Any]]:
    """Google kuralı: ajanın kendi grubu (birden çoksa birleşik); yoksa ön eki (googlebot-image →
    googlebot); o da yoksa `*`."""
    a = ajan.lower()
    adaylar = [a]
    if "-" in a:
        adaylar.append(a.split("-", 1)[0])
    if a != "*":
        for aday in adaylar:
            secili = [g for g in gruplar if aday in g["ajanlar"]]
            if secili:
                return secili
    return [g for g in gruplar if "*" in g["ajanlar"]]


def _desen_eslesir(desen: str, yol: str) -> bool:
    ifade = re.escape(desen).replace(r"\*", ".*")
    if ifade.endswith(r"\$"):
        ifade = ifade[:-2] + "$"
    return re.match(ifade, yol) is not None


def robots_karar(cozum: Dict[str, Any], ajan: str, yol: str) -> Dict[str, Any]:
    """Yol bu ajan için taranabilir mi? En uzun eşleşen kural kazanır; eşitlikte Allow."""
    yol = unquote(yol or "/")
    if not yol.startswith("/"):
        yol = "/" + yol
    if yol == "/robots.txt":
        return {"izinli": True, "kural": None, "grup_ajanlari": []}
    gruplar = _ajan_gruplari(cozum["gruplar"], ajan)
    kurallar = [k for g in gruplar for k in g["kurallar"] if k["deger"]]
    en_iyi: Optional[Dict[str, Any]] = None
    for k in kurallar:
        if not _desen_eslesir(unquote(k["deger"]), yol):
            continue
        if (
            en_iyi is None
            or len(k["deger"]) > len(en_iyi["deger"])
            or (len(k["deger"]) == len(en_iyi["deger"]) and k["alan"] == "allow")
        ):
            en_iyi = k
    return {
        "izinli": en_iyi is None or en_iyi["alan"] == "allow",
        "kural": en_iyi,
        "grup_ajanlari": sorted({a for g in gruplar for a in g["ajanlar"]}),
    }


async def robots_txt(gezgin: motor.Gezgin, url: str, secenek: Dict[str, Any]) -> Dict[str, Any]:
    ajan = ajan_dogrula(secenek.get("ajan"))
    p = urlsplit(url)
    yol = (p.path or "/") + (f"?{p.query}" if p.query else "")
    robots_url = f"{_koken(url)}/robots.txt"
    y = await gezgin.getir(robots_url)
    if y.hata in ("adres_yasak", "adres_gecersiz"):
        raise AnalizHatasi("adres_yasak")
    s = Sonuc("robots-txt")
    tur = (y.basliklar.get("content-type") or "").lower()
    metin = ""
    if y.durum == 0 or y.durum >= 500:
        s.ekle("robots_dosyasi", "robots_erisilemedi", "hata", y.durum or y.hata)
    elif y.durum >= 400:
        s.ekle("robots_dosyasi", "robots_yok", "uyari", y.durum)
    elif y.durum == 200 and "html" in tur:
        s.ekle("robots_dosyasi", "robots_html", "uyari")
    elif y.durum == 200:
        metin = y.govde
        boyut = len(y.govde.encode("utf-8"))
        if boyut > ROBOTS_GOOGLE_TAVANI or y.kesildi:
            s.ekle("robots_dosyasi", "robots_buyuk", "uyari", round(boyut / 1024))
        else:
            s.ekle("robots_dosyasi", "robots_var", "iyi", boyut)
    else:
        s.ekle("robots_dosyasi", "robots_erisilemedi", "hata", y.durum)

    cozum = robots_coz(metin)
    karar = robots_karar(cozum, ajan, yol)
    if y.durum == 0 or y.durum >= 500:
        # Google 5xx'te siteyi geçici olarak tamamen engellenmiş sayar.
        karar = {"izinli": False, "kural": None, "grup_ajanlari": []}
        s.ekle("robots_yol", "yol_bilinmiyor", "hata", {"yol": _kisalt(yol, 200), "ajan": ajan})
    elif karar["izinli"]:
        s.ekle("robots_yol", "yol_izinli", "iyi", {"yol": _kisalt(yol, 200), "ajan": ajan})
    else:
        k = karar["kural"] or {}
        s.ekle("robots_yol", "yol_engelli", "uyari",
               {"yol": _kisalt(yol, 200), "ajan": ajan, "satir": k.get("satir"), "kural": _kisalt(f"Disallow: {k.get('deger', '')}", 200)})
    if metin:
        kok = robots_karar(cozum, ajan, "/")
        if not kok["izinli"] and (kok["kural"] or {}).get("deger") == "/":
            s.ekle("robots_yol", "tum_site_engelli", "hata", ajan)

    if metin:
        if cozum["sitemapler"]:
            goreli = [x for x in cozum["sitemapler"] if not re.match(r"^https?://", x, re.I)]
            if goreli:
                s.ekle("robots_sitemap", "sitemap_satiri_goreli", "uyari", len(goreli))
            else:
                s.ekle("robots_sitemap", "sitemap_satiri_var", "iyi", len(cozum["sitemapler"]))
        else:
            s.ekle("robots_sitemap", "sitemap_satiri_yok", "bilgi")
        if cozum["ajansiz"]:
            s.ekle("robots_sozdizimi", "kural_ajansiz", "uyari", ", ".join(map(str, cozum["ajansiz"][:10])))
        if cozum["bilinmeyen"]:
            s.ekle("robots_sozdizimi", "bilinmeyen_yonerge", "bilgi", ", ".join(map(str, cozum["bilinmeyen"][:10])))
        if cozum["crawl_delay"]:
            s.ekle("robots_sozdizimi", "crawl_delay", "bilgi")
        if not (cozum["ajansiz"] or cozum["bilinmeyen"]):
            s.ekle("robots_sozdizimi", "sozdizimi_iyi", "iyi")

    satirlar = metin.splitlines()
    s.veri.update(
        {
            "robots_url": robots_url,
            "durum": y.durum,
            "satir_sayisi": len(satirlar),
            "metin": "\n".join(satirlar[:400])[:40_000],
            "yol": _kisalt(yol, 300),
            "ajan": ajan,
            "sonuc": karar,
            "gruplar": [
                {"ajanlar": g["ajanlar"][:20], "kural_sayisi": len(g["kurallar"]), "satir": g["satir"]}
                for g in cozum["gruplar"][:50]
            ],
            "sitemapler": [_kisalt(x, 300) for x in cozum["sitemapler"][:30]],
        }
    )
    return s.sozluk(url, robots_url, y.durum)


# ==========================================================================
# 5) XML site haritası doğrulayıcı
# ==========================================================================
SITEMAP_AD_ALANI = "http://www.sitemaps.org/schemas/sitemap/0.9"
_DTD = re.compile(rb"<!(DOCTYPE|ENTITY)", re.I)
_W3C_TARIH = re.compile(
    r"^\d{4}(-\d{2}(-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2}))?)?)?$"
)
_DEGISIM = {"always", "hourly", "daily", "weekly", "monthly", "yearly", "never"}


def _yerel(ad: str) -> Tuple[str, str]:
    if ad.startswith("{"):
        ns, _, yerel = ad[1:].partition("}")
        return ns, yerel
    return "", ad


def sitemap_ac(ham: bytes, adres: str, tur: str) -> Tuple[bytes, bool]:
    """Gerekirse gzip'i açar (bomba koruması: en çok SITEMAP_ACIK_TAVAN). (bayt, kesildi)."""
    if ham[:2] != b"\x1f\x8b":
        return ham, False
    acici = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        acik = acici.decompress(ham, SITEMAP_ACIK_TAVAN)
    except zlib.error as exc:
        raise ValueError(f"gzip: {exc}") from exc
    return acik, bool(acici.unconsumed_tail)


def sitemap_coz(veri: bytes, kesildi: bool) -> Dict[str, Any]:
    """{tur, ad_alani, girdiler:[{loc,lastmod,changefreq,priority}]} ya da {hata}.

    DTD/varlık tanımı taşıyan belge HİÇ ayrıştırılmıyor (XXE / "billion laughs"):
    site haritası protokolü bunlara ihtiyaç duymaz. Dosya kesildiyse (1,5 MB tavanı)
    ayrıştırıcı yerine düzenli ifadeyle okunuyor; kesik son girdi atılıyor.
    """
    import xml.etree.ElementTree as ET

    if _DTD.search(veri[:200_000]):
        return {"hata": "dtd"}
    if kesildi:
        metin = veri.decode("utf-8", errors="replace")
        kok = re.search(r"<(?:\w+:)?(urlset|sitemapindex)\b([^>]*)>", metin)
        if not kok:
            return {"hata": "xml", "mesaj": "kök öğe bulunamadı"}
        tur = kok.group(1)
        ad_alani_m = re.search(r"xmlns\s*=\s*[\"']([^\"']+)", kok.group(2))
        ogeler = re.findall(r"<(?:\w+:)?(?:url|sitemap)\b[^>]*>(.*?)</(?:\w+:)?(?:url|sitemap)\s*>", metin, re.S)
        girdiler = []
        for o in ogeler:
            def al(ad: str) -> Optional[str]:
                m = re.search(rf"<(?:\w+:)?{ad}\b[^>]*>(.*?)</(?:\w+:)?{ad}\s*>", o, re.S)
                return html_modulu.unescape(m.group(1)).strip() if m else None
            girdiler.append({"loc": al("loc"), "lastmod": al("lastmod"), "changefreq": al("changefreq"), "priority": al("priority")})
        return {"tur": tur, "ad_alani": ad_alani_m.group(1) if ad_alani_m else "", "girdiler": girdiler}
    try:
        kok = ET.fromstring(veri)
    except ET.ParseError as exc:
        satir, sutun = getattr(exc, "position", (None, None))
        return {"hata": "xml", "mesaj": str(exc)[:160], "satir": satir, "sutun": sutun}
    ad_alani, tur = _yerel(kok.tag)
    if tur not in ("urlset", "sitemapindex"):
        return {"hata": "kok", "mesaj": tur[:60]}
    girdiler = []
    for oge in list(kok)[: SITEMAP_URL_TAVANI + 1]:
        _, ad = _yerel(oge.tag)
        if ad not in ("url", "sitemap"):
            continue
        alanlar: Dict[str, Optional[str]] = {"loc": None, "lastmod": None, "changefreq": None, "priority": None}
        for alt in oge:
            _, alt_ad = _yerel(alt.tag)
            if alt_ad in alanlar and alanlar[alt_ad] is None:
                alanlar[alt_ad] = (alt.text or "").strip()
        girdiler.append(alanlar)
    return {"tur": tur, "ad_alani": ad_alani, "girdiler": girdiler}


def _gecerli_adres(adres: Optional[str]) -> bool:
    if not adres or len(adres) > 2048 or any(c.isspace() for c in adres) or "#" in adres:
        return False
    try:
        p = urlsplit(adres)
    except ValueError:
        return False
    return p.scheme in ("http", "https") and bool(p.hostname)


def _tarih_coz(deger: str) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(deger.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = datetime.strptime(deger[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _ayni_host(a: str, b: str) -> bool:
    return (urlsplit(a).hostname or "").lower() == (urlsplit(b).hostname or "").lower()


def girdileri_denetle(s: Sonuc, girdiler: List[Dict[str, Optional[str]]], sitemap_url: str, tur: str) -> List[str]:
    """Adres/lastmod/öncelik denetimi; örneklem için geçerli aynı site adreslerini döndürür."""
    hatali: List[str] = []
    baska: List[str] = []
    lastmod_yok = lastmod_hatali = lastmod_gelecek = alan_hatali = 0
    gorulen: set = set()
    tekrar = 0
    gecerliler: List[str] = []
    yarin = datetime.now(timezone.utc) + timedelta(days=1)
    for g in girdiler[:SITEMAP_URL_TAVANI]:
        loc = g.get("loc")
        if not _gecerli_adres(loc):
            hatali.append(_kisalt(loc or "(boş)", 200))
            continue
        if loc in gorulen:
            tekrar += 1
        gorulen.add(loc)
        if not _ayni_host(loc, sitemap_url):
            baska.append(_kisalt(loc, 200))
        else:
            gecerliler.append(loc)
        lm = g.get("lastmod")
        if not lm:
            lastmod_yok += 1
        elif not _W3C_TARIH.match(lm) or _tarih_coz(lm) is None:
            lastmod_hatali += 1
        elif _tarih_coz(lm) > yarin:
            lastmod_gelecek += 1
        if tur == "urlset":
            cf, pr = g.get("changefreq"), g.get("priority")
            if cf and cf.lower() not in _DEGISIM:
                alan_hatali += 1
            if pr:
                try:
                    if not 0.0 <= float(pr) <= 1.0:
                        alan_hatali += 1
                except ValueError:
                    alan_hatali += 1
    toplam = len(girdiler)
    if hatali:
        s.ekle("sitemap_adresler", "adres_hatali", "hata", len(hatali))
    if baska:
        s.ekle("sitemap_adresler", "adres_baska_site", "uyari", len(baska))
    if tekrar:
        s.ekle("sitemap_adresler", "adres_tekrar", "uyari", tekrar)
    if toplam and not (hatali or baska or tekrar):
        s.ekle("sitemap_adresler", "adresler_iyi", "iyi", toplam)
    if toplam and lastmod_yok == toplam:
        s.ekle("sitemap_lastmod", "lastmod_yok", "bilgi")
    elif lastmod_yok:
        s.ekle("sitemap_lastmod", "lastmod_eksik", "bilgi", lastmod_yok)
    if lastmod_hatali:
        s.ekle("sitemap_lastmod", "lastmod_hatali", "uyari", lastmod_hatali)
    if lastmod_gelecek:
        s.ekle("sitemap_lastmod", "lastmod_gelecek", "uyari", lastmod_gelecek)
    if toplam and not (lastmod_yok or lastmod_hatali or lastmod_gelecek):
        s.ekle("sitemap_lastmod", "lastmod_iyi", "iyi")
    if alan_hatali:
        s.ekle("sitemap_bicim", "alan_hatali", "bilgi", alan_hatali)
    s.veri.setdefault("hatali_adresler", []).extend(hatali[:10])
    s.veri.setdefault("baska_site_adresleri", []).extend(baska[:10])
    s.veri["lastmod_orani"] = round(100 * (toplam - lastmod_yok) / toplam) if toplam else 0
    return gecerliler


async def _orneklem(gezgin: motor.Gezgin, adresler: List[str]) -> List[Dict[str, Any]]:
    if not adresler:
        return []
    adim = max(1, len(adresler) // ORNEKLEM)
    secilen = adresler[::adim][:ORNEKLEM]

    async def bak(a: str) -> Dict[str, Any]:
        y = await gezgin.getir(a, yontem="HEAD", govde_oku=False, izle=False)
        if y.durum in (405, 501):
            y = await gezgin.getir(a, govde_oku=False, izle=False)
        return {"url": _kisalt(a, 300), "durum": y.durum, "hata": y.hata}

    return list(await asyncio.gather(*(bak(a) for a in secilen)))


async def _sitemap_getir(gezgin: motor.Gezgin, adres: str) -> Tuple[motor.Yanit, bytes, bool]:
    y = await gezgin.getir(adres, ham_oku=True)
    if y.hata or y.durum != 200:
        return y, b"", False
    try:
        acik, kesik = sitemap_ac(y.ham, adres, y.basliklar.get("content-type", ""))
    except ValueError:
        return y, b"", False
    return y, acik, kesik or y.kesildi


async def site_haritasi(gezgin: motor.Gezgin, url: str, secenek: Dict[str, Any]) -> Dict[str, Any]:
    s = Sonuc("site-haritasi")
    p = urlsplit(url)
    koken = _koken(url)
    adaylar: List[Tuple[str, str]] = []
    if p.path not in ("", "/"):
        adaylar.append((url, "girilen"))
    else:
        r = await gezgin.getir(f"{koken}/robots.txt")
        if r.hata in ("adres_yasak", "adres_gecersiz"):
            raise AnalizHatasi("adres_yasak")
        if r.durum == 0:
            raise AnalizHatasi(r.hata or "ulasilamadi")
        if r.durum == 200 and "html" not in (r.basliklar.get("content-type") or "").lower():
            for x in robots_coz(r.govde)["sitemapler"]:
                if _gecerli_adres(x) and _ayni_host(x, url):
                    adaylar.append((x, "robots"))
                    break
        adaylar += [(f"{koken}/sitemap.xml", "varsayilan"), (f"{koken}/sitemap_index.xml", "varsayilan")]

    y: Optional[motor.Yanit] = None
    veri, kesik, kaynak, sitemap_url = b"", False, "", url
    for aday, kaynak_ in adaylar:
        y, veri, kesik = await _sitemap_getir(gezgin, aday)
        if y.hata in ("adres_yasak", "adres_gecersiz") and kaynak_ != "robots":
            raise AnalizHatasi("adres_yasak")
        if veri:
            sitemap_url, kaynak = y.url, kaynak_
            break
    s.veri.update({"sitemap_url": sitemap_url, "kaynak": kaynak or None})
    if not veri:
        if y is not None and y.durum == 0 and not adaylar[1:]:
            raise AnalizHatasi(y.hata or "ulasilamadi")
        s.ekle("sitemap_erisim", "sitemap_bulunamadi", "hata", (y.durum if y else None) or (y.hata if y else None))
        return s.sozluk(url, y.url if y else url, y.durum if y else None)

    s.ekle("sitemap_erisim", "sitemap_erisildi", "iyi", sitemap_url)
    s.veri["boyut_bayt"] = len(veri)
    s.veri["sikistirilmis"] = y.ham[:2] == b"\x1f\x8b" if y else False
    if kesik:
        s.ekle("sitemap_erisim", "sitemap_kesildi", "bilgi", round(len(veri) / 1024))

    cozum = sitemap_coz(veri, kesik)
    if "hata" in cozum:
        kod = {"dtd": "dtd_reddedildi", "kok": "sitemap_kok_hatali"}.get(cozum["hata"], "sitemap_xml_hatasi")
        s.ekle("sitemap_bicim", kod, "hata", cozum.get("mesaj"))
        return s.sozluk(url, sitemap_url, y.durum if y else None)
    tur = cozum["tur"]
    girdiler = cozum["girdiler"]
    s.veri.update({"tur": tur, "adres_sayisi": len(girdiler)})
    if cozum["ad_alani"] != SITEMAP_AD_ALANI:
        s.ekle("sitemap_bicim", "sitemap_ad_alani", "uyari", _kisalt(cozum["ad_alani"] or "-", 120))
    if len(girdiler) > SITEMAP_URL_TAVANI:
        s.ekle("sitemap_bicim", "sitemap_cok_buyuk", "hata", len(girdiler))
    elif not girdiler:
        s.ekle("sitemap_bicim", "sitemap_bos", "uyari")
    else:
        s.ekle("sitemap_bicim", "sitemap_dizini" if tur == "sitemapindex" else "sitemap_bicim_iyi",
               "bilgi" if tur == "sitemapindex" else "iyi", len(girdiler))

    gecerliler = girdileri_denetle(s, girdiler, sitemap_url, tur)
    if tur == "sitemapindex":
        s.veri["alt_sitemapler"] = [_kisalt(g.get("loc") or "", 300) for g in girdiler[:20]]
        alt = next((a for a in gecerliler), None)
        if alt:
            y2, veri2, kesik2 = await _sitemap_getir(gezgin, alt)
            cozum2 = sitemap_coz(veri2, kesik2) if veri2 else {"hata": "yok"}
            if "hata" in cozum2 or cozum2.get("tur") != "urlset":
                s.ekle("sitemap_bicim", "alt_sitemap_hatali", "uyari", _kisalt(alt, 200))
                gecerliler = []
            else:
                s.veri.update({"incelenen_alt": _kisalt(alt, 300), "alt_adres_sayisi": len(cozum2["girdiler"])})
                gecerliler = girdileri_denetle(s, cozum2["girdiler"], alt, "urlset")
        else:
            gecerliler = []

    ornekler = await _orneklem(gezgin, gecerliler)
    s.veri["ornekler"] = ornekler
    bozuk = [o for o in ornekler if o["hata"] not in (None, "adres_yasak", "adres_gecersiz") or (o["durum"] >= 400 and not o["hata"])]
    yonlenen = [o for o in ornekler if 300 <= (o["durum"] or 0) < 400]
    if bozuk:
        s.ekle("sitemap_orneklem", "orneklem_hatali", "hata", {"hatali": len(bozuk), "toplam": len(ornekler)})
    if yonlenen:
        s.ekle("sitemap_orneklem", "orneklem_yonlendirme", "uyari", {"hatali": len(yonlenen), "toplam": len(ornekler)})
    if ornekler and not (bozuk or yonlenen):
        s.ekle("sitemap_orneklem", "orneklem_iyi", "iyi", len(ornekler))
    return s.sozluk(url, sitemap_url, y.durum if y else None)


# ==========================================================================
# 6) Yönlendirme zinciri
# ==========================================================================
async def yonlendirme(gezgin: motor.Gezgin, url: str, secenek: Dict[str, Any]) -> Dict[str, Any]:
    s = Sonuc("yonlendirme")
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    apex = host[4:] if host.startswith("www.") else host
    port = f":{p.port}" if p.port else ""
    ip_mi = motor._ip_mi(host) is not None
    varyantlar: List[Tuple[str, str]] = [("girilen", url), ("http", f"http://{apex}{port}/"), ("https", f"https://{apex}{port}/")]
    if not ip_mi:
        varyantlar += [("http_www", f"http://www.{apex}{port}/"), ("https_www", f"https://www.{apex}{port}/")]

    async def zincir(etiket: str, adres: str) -> Dict[str, Any]:
        y = await gezgin.getir(adres, govde_oku=False, dongu_algila=True)
        adimlar = [{"url": _kisalt(z["url"], 400), "durum": z["durum"]} for z in y.zincir]
        return {
            "etiket": etiket,
            "baslangic": _kisalt(adres, 400),
            "adimlar": adimlar,
            "son_url": _kisalt(y.url, 400),
            "son_durum": y.durum,
            "hata": y.hata,
        }

    ana = await zincir("girilen", url)
    if ana["hata"] in ("adres_yasak", "adres_gecersiz"):
        raise AnalizHatasi("adres_yasak")
    if ana["hata"] in ("ulasilamadi", "cozumlenemedi") and not ana["adimlar"]:
        raise AnalizHatasi(ana["hata"])
    digerleri = await asyncio.gather(*(zincir(e, a) for e, a in varyantlar[1:] if not _ayni_adres(a, url)))
    zincirler = [ana] + list(digerleri)
    s.veri["zincirler"] = zincirler
    bul = {z["etiket"]: z for z in zincirler}
    for etiket, adres in varyantlar[1:]:
        if etiket not in bul and _ayni_adres(adres, url):
            bul[etiket] = ana  # girilen adres bu varyantın kendisi

    # Zincir (girilen adres)
    adim = max(0, len(ana["adimlar"]) - 1)
    if ana["hata"] == "dongu":
        s.ekle("zincir", "dongu", "hata")
    elif ana["hata"] == "cok_yonlendirme":
        s.ekle("zincir", "cok_yonlendirme", "hata", motor.EN_COK_YONLENDIRME)
    elif adim >= 2:
        s.ekle("zincir", "zincir_uzun", "uyari", adim)
    else:
        s.ekle("zincir", "zincir_iyi", "iyi", adim)
    gecici = [a for a in ana["adimlar"][:-1] if a["durum"] in (302, 303, 307)]
    if gecici:
        s.ekle("zincir", "gecici_yonlendirme", "bilgi", gecici[0]["durum"])

    # Son durum
    if not ana["hata"]:
        if ana["son_durum"] == 200:
            s.ekle("son_durum", "son_durum_iyi", "iyi", 200)
        else:
            s.ekle("son_durum", "son_durum_hatali", "hata", ana["son_durum"])

    # http → https
    http = bul.get("http")
    https = bul.get("https")
    if http and not http["hata"]:
        if http["son_url"].lower().startswith("https://"):
            ilk = http["adimlar"][0]["durum"] if http["adimlar"] else None
            if ilk in (302, 303, 307):
                s.ekle("https_yonlendirme", "https_gecici", "uyari", ilk)
            else:
                s.ekle("https_yonlendirme", "https_yonlendirme_iyi", "iyi", ilk)
        elif https and not https["hata"] and https["son_durum"] and https["son_durum"] < 400:
            s.ekle("https_yonlendirme", "https_yonlendirme_yok", "hata")
        else:
            s.ekle("https_yonlendirme", "https_yok", "hata")
    elif https and https["hata"]:
        s.ekle("https_yonlendirme", "https_yok", "hata")

    # www tutarlılığı
    if not ip_mi:
        sonlar = {}
        for e in ("http", "https", "http_www", "https_www"):
            z = bul.get(e)
            if z and not z["hata"] and z["son_durum"] and z["son_durum"] < 400:
                sonlar[e] = z["son_url"]
        erisilemeyen = [e for e in ("http_www", "https_www") if e in bul and bul[e]["hata"]]
        normal = {re.sub(r"/+$", "", u.lower()) for u in sonlar.values()}
        if len(normal) > 1:
            s.ekle("www_tutarlilik", "www_tutarsiz", "uyari", len(normal))
        elif sonlar:
            s.ekle("www_tutarlilik", "www_iyi", "iyi")
        if erisilemeyen and len(erisilemeyen) == 2:
            s.ekle("www_tutarlilik", "www_erisilemedi", "bilgi", f"www.{apex}")
    son = ana["son_url"]
    return s.sozluk(url, son, ana["son_durum"])


# ==========================================================================
# 7) HTTP güvenlik başlıkları
# ==========================================================================
_GUCLU_REFERRER = {"no-referrer", "same-origin", "strict-origin", "strict-origin-when-cross-origin"}
_ZAYIF_REFERRER = {"unsafe-url", "no-referrer-when-downgrade", "origin-when-cross-origin", "origin"}
GUVENLIK_AGIRLIK = {"hsts": 25, "csp": 25, "frame": 15, "nosniff": 15, "referrer": 10, "permissions": 10}


def _csp_yonergeleri(csp: str) -> Dict[str, List[str]]:
    d: Dict[str, List[str]] = {}
    for parca in csp.split(";"):
        kelimeler = parca.strip().split()
        if kelimeler:
            d.setdefault(kelimeler[0].lower(), [k.lower() for k in kelimeler[1:]])
    return d


def harf_notu(puan: int) -> str:
    for sinir, harf in ((95, "A+"), (85, "A"), (70, "B"), (55, "C"), (40, "D")):
        if puan >= sinir:
            return harf
    return "F"


def guvenlik_incele(s: Sonuc, son_url: str, h: Dict[str, str]) -> None:
    puan = 0
    https = son_url.lower().startswith("https://")
    durumlar: Dict[str, str] = {}

    # HSTS
    hsts = h.get("strict-transport-security", "")
    if not https:
        s.ekle("hsts", "https_degil", "hata")
        durumlar["strict-transport-security"] = "hata"
    elif not hsts:
        s.ekle("hsts", "hsts_yok", "hata")
        durumlar["strict-transport-security"] = "yok"
    else:
        m = re.search(r"max-age\s*=\s*\"?(\d+)", hsts, re.I)
        sure = int(m.group(1)) if m else 0
        if sure < 15_552_000:
            s.ekle("hsts", "hsts_kisa", "uyari", sure // 86400)
            puan += 15
            durumlar["strict-transport-security"] = "uyari"
        else:
            s.ekle("hsts", "hsts_iyi", "iyi", sure // 86400)
            puan += GUVENLIK_AGIRLIK["hsts"]
            durumlar["strict-transport-security"] = "iyi"
            if "includesubdomains" not in hsts.lower():
                s.ekle("hsts", "hsts_alt_alan_yok", "bilgi")

    # CSP
    csp = h.get("content-security-policy", "")
    yonergeler = _csp_yonergeleri(csp)
    if csp:
        betik = yonergeler.get("script-src", yonergeler.get("default-src", []))
        ozetli = any(k.startswith(("'nonce-", "'sha256-", "'sha384-", "'sha512-")) or k == "'strict-dynamic'" for k in betik)
        kazanc = GUVENLIK_AGIRLIK["csp"]
        sorun = False
        if "'unsafe-inline'" in betik and not ozetli:
            s.ekle("csp", "csp_unsafe_inline", "uyari")
            kazanc -= 8
            sorun = True
        if "'unsafe-eval'" in betik:
            s.ekle("csp", "csp_unsafe_eval", "uyari")
            kazanc -= 5
            sorun = True
        if not sorun:
            s.ekle("csp", "csp_iyi", "iyi")
        puan += kazanc
        durumlar["content-security-policy"] = "uyari" if sorun else "iyi"
    elif h.get("content-security-policy-report-only"):
        s.ekle("csp", "csp_rapor", "uyari")
        puan += 8
        durumlar["content-security-policy-report-only"] = "uyari"
    else:
        s.ekle("csp", "csp_yok", "hata")
        durumlar["content-security-policy"] = "yok"

    # Çerçeve koruması
    xfo = h.get("x-frame-options", "").strip().lower()
    if "frame-ancestors" in yonergeler or xfo in ("deny", "sameorigin"):
        s.ekle("frame", "frame_iyi", "iyi", "frame-ancestors" if "frame-ancestors" in yonergeler else xfo.upper())
        puan += GUVENLIK_AGIRLIK["frame"]
        durumlar["x-frame-options"] = "iyi" if xfo else "bilgi"
    else:
        s.ekle("frame", "frame_yok", "uyari")
        durumlar["x-frame-options"] = "yok"

    # nosniff
    if h.get("x-content-type-options", "").strip().lower() == "nosniff":
        s.ekle("nosniff", "nosniff_iyi", "iyi")
        puan += GUVENLIK_AGIRLIK["nosniff"]
        durumlar["x-content-type-options"] = "iyi"
    else:
        s.ekle("nosniff", "nosniff_yok", "uyari")
        durumlar["x-content-type-options"] = "yok"

    # Referrer-Policy (birden çok değer: sonuncusu geçerli)
    ref = h.get("referrer-policy", "").strip().lower()
    son_deger = [p.strip() for p in ref.split(",") if p.strip()][-1:] if ref else []
    if not ref:
        s.ekle("referrer", "referrer_yok", "uyari")
        durumlar["referrer-policy"] = "yok"
    elif son_deger and son_deger[0] in _ZAYIF_REFERRER:
        s.ekle("referrer", "referrer_zayif", "uyari", son_deger[0])
        puan += 4
        durumlar["referrer-policy"] = "uyari"
    else:
        s.ekle("referrer", "referrer_iyi", "iyi", son_deger[0] if son_deger else ref[:60])
        puan += GUVENLIK_AGIRLIK["referrer"]
        durumlar["referrer-policy"] = "iyi"

    # Permissions-Policy
    if h.get("permissions-policy"):
        s.ekle("permissions", "permissions_iyi", "iyi")
        puan += GUVENLIK_AGIRLIK["permissions"]
        durumlar["permissions-policy"] = "iyi"
    else:
        s.ekle("permissions", "permissions_yok", "uyari")
        durumlar["permissions-policy"] = "yok"

    # Sunucu sürüm bilgisi (puana girmez)
    sizan = []
    sunucu = h.get("server", "")
    if re.search(r"\d", sunucu):
        sizan.append(f"Server: {sunucu[:60]}")
    if h.get("x-powered-by"):
        sizan.append(f"X-Powered-By: {h['x-powered-by'][:60]}")
    if sizan:
        s.ekle("sunucu_bilgisi", "sunucu_surumu", "bilgi", "; ".join(sizan))
        if sunucu:
            durumlar["server"] = "bilgi"
        if h.get("x-powered-by"):
            durumlar["x-powered-by"] = "bilgi"

    s.puan = max(0, min(100, puan))
    gosterilen = (
        "strict-transport-security", "content-security-policy", "content-security-policy-report-only",
        "x-frame-options", "x-content-type-options", "referrer-policy", "permissions-policy",
        "cross-origin-opener-policy", "cross-origin-resource-policy", "cross-origin-embedder-policy",
        "server", "x-powered-by",
    )
    tablo = []
    for ad in gosterilen:
        deger = h.get(ad)
        if deger is None and durumlar.get(ad) != "yok":
            continue
        tablo.append({"ad": ad, "deger": _kisalt(deger or "", 400), "durum": durumlar.get(ad, "bilgi" if deger else "yok")})
    s.veri.update({"puan": s.puan, "harf": harf_notu(s.puan), "https": https, "basliklar": tablo})


async def guvenlik_basliklari(gezgin: motor.Gezgin, url: str, secenek: Dict[str, Any]) -> Dict[str, Any]:
    y = await _ana_sayfa(gezgin, url, govde_oku=False)
    s = Sonuc("guvenlik-basliklari")
    guvenlik_incele(s, y.url, y.basliklar)
    return s.sozluk(url, y.url, y.durum)


# ==========================================================================
# 8) SSL sertifikası
# ==========================================================================
_SSL_HATALARI = {10: "ssl_suresi_gecmis", 18: "ssl_kendinden_imzali", 19: "ssl_kendinden_imzali",
                 20: "zincir_eksik", 21: "zincir_eksik", 62: "ssl_ad_uyusmuyor"}


def ssl_incele(s: Sonuc, bilgi: Dict[str, Any], simdi: Optional[datetime] = None) -> None:
    simdi = simdi or datetime.now(timezone.utc)
    if bilgi.get("hata") == "baglanti" and not bilgi.get("sertifika"):
        s.ekle("sertifika_gecerlilik", "ssl_yok", "hata")
        s.veri.update({"dogrulandi": False})
        return
    sert = bilgi.get("sertifika") or {}
    if bilgi.get("dogrulandi"):
        s.ekle("sertifika_gecerlilik", "ssl_dogrulandi", "iyi")
    else:
        kod = _SSL_HATALARI.get(bilgi.get("hata_kodu"), "ssl_gecersiz")
        if kod == "zincir_eksik":
            s.ekle("ssl_zincir", "zincir_eksik", "hata")
        elif kod != "ssl_suresi_gecmis":
            s.ekle("sertifika_gecerlilik", kod, "hata", _kisalt(bilgi.get("hata") or "", 160))
    if sert.get("bitis"):
        bitis = datetime.fromisoformat(sert["bitis"])
        kalan = int((bitis - simdi).total_seconds() // 86400)
        if kalan < 0:
            s.ekle("sertifika_suresi", "ssl_suresi_gecmis", "hata", -kalan)
        elif kalan < 14:
            s.ekle("sertifika_suresi", "ssl_bitiyor", "hata", kalan)
        elif kalan < 30:
            s.ekle("sertifika_suresi", "ssl_yakinda", "uyari", kalan)
        else:
            s.ekle("sertifika_suresi", "ssl_gecerli", "iyi", kalan)
        s.veri["kalan_gun"] = kalan
    surum = bilgi.get("tls_surumu") or ""
    if surum in ("TLSv1.3",):
        s.ekle("tls_surumu", "tls_iyi", "iyi", surum)
    elif surum == "TLSv1.2":
        s.ekle("tls_surumu", "tls_12", "bilgi", surum)
    elif surum:
        s.ekle("tls_surumu", "tls_eski", "uyari", surum)
    zincir = bilgi.get("zincir") or []
    if bilgi.get("dogrulandi"):
        s.ekle("ssl_zincir", "zincir_iyi", "iyi", max(len(zincir), 2))
    s.veri.update(
        {
            "dogrulandi": bool(bilgi.get("dogrulandi")),
            "hata": _kisalt(bilgi.get("hata") or "", 200) if bilgi.get("hata") not in (None, "baglanti") else None,
            "tls_surumu": surum or None,
            "sifre": bilgi.get("sifre"),
            "sertifika": sert or None,
            "zincir": zincir,
        }
    )


async def ssl_sertifikasi(gezgin: motor.Gezgin, url: str, secenek: Dict[str, Any]) -> Dict[str, Any]:
    host = (urlsplit(url).hostname or "").lower()
    s = Sonuc("ssl-sertifikasi")
    bilgi = await motor.ssl_bilgisi(host)  # SSRF denetimi içeride (_guvenli_ipler)
    ssl_incele(s, bilgi)
    s.veri["host"] = host
    return s.sozluk(f"https://{host}/", f"https://{host}/", None)


# ==========================================================================
# 9) Başlık yapısı (H1–H6)
# ==========================================================================
_HN = re.compile(r"<h([1-6])\b[^>]*>(.*?)</h\1\s*>", re.I | re.S)
_GORUNMEZ = re.compile(r"<(script|style|noscript|template|svg|head)\b[^>]*>.*?</\1\s*>", re.I | re.S)


def basliklari_cikar(html: str) -> List[Dict[str, Any]]:
    """Görünür gövdedeki H1–H6 (betik/stil/şablon/svg/head içindekiler sayılmaz), en çok 300."""
    govde = _GORUNMEZ.sub(" ", si._YORUM.sub(" ", html))
    return [{"seviye": int(sv), "metin": _kisalt(duz_metin(ic), 200)} for sv, ic in _HN.findall(govde)][:300]


def baslik_incele(s: Sonuc, html: str) -> None:
    basliklar = basliklari_cikar(html)
    h1 = [b for b in basliklar if b["seviye"] == 1]
    if not h1:
        s.ekle("h1", "h1_yok", "hata")
    elif len(h1) > 1:
        s.ekle("h1", "h1_fazla", "uyari", len(h1))
    elif not h1[0]["metin"]:
        s.ekle("h1", "h1_bos", "hata")
    else:
        s.ekle("h1", "h1_iyi", "iyi", h1[0]["metin"][:120])

    atlamalar = []
    onceki = 0
    for b in basliklar:
        if onceki and b["seviye"] > onceki + 1:
            atlamalar.append(f"H{onceki}→H{b['seviye']}")
        onceki = b["seviye"]
    bos = sum(1 for b in basliklar if not b["metin"])
    uzun = sum(1 for b in basliklar if len(b["metin"]) > 70)
    if basliklar and basliklar[0]["seviye"] != 1 and h1:
        s.ekle("baslik_hiyerarsi", "ilk_baslik_h1_degil", "bilgi", f"H{basliklar[0]['seviye']}")
    if atlamalar:
        s.ekle("baslik_hiyerarsi", "seviye_atlama", "uyari", ", ".join(sorted(set(atlamalar)))[:120])
    if bos:
        s.ekle("baslik_hiyerarsi", "bos_baslik", "uyari", bos)
    if uzun:
        s.ekle("baslik_hiyerarsi", "uzun_baslik", "bilgi", uzun)
    if not basliklar:
        s.ekle("baslik_hiyerarsi", "baslik_yok", "uyari")
    elif not (atlamalar or bos):
        s.ekle("baslik_hiyerarsi", "hiyerarsi_iyi", "iyi", len(basliklar))
    s.veri.update({
        "basliklar": basliklar,
        "seviye_sayilari": {f"h{i}": sum(1 for b in basliklar if b["seviye"] == i) for i in range(1, 7)},
    })


async def baslik_yapisi(gezgin: motor.Gezgin, url: str, secenek: Dict[str, Any]) -> Dict[str, Any]:
    y = await _ana_sayfa(gezgin, url)
    s = Sonuc("baslik-yapisi")
    baslik_incele(s, y.govde)
    return s.sozluk(url, y.url, y.durum)


# ==========================================================================
# 10) Kelime / anahtar kelime yoğunluğu
# ==========================================================================
_SOZCUK = re.compile(r"[^\W\d_]+", re.U)

TR_DURAK = frozenset(
    """
    acaba ama ancak artık aslında ayrıca az bana bazen bazı belki ben beni benim bile bir biraz birçok birkaç
    birşey biz bize bizi bizim bu buna bunda bundan bunlar bunları bunların bunu bunun burada böyle böylece
    da daha dahi de defa değil diğer diye dolayı dolayısıyla eğer en fakat gibi göre halen hangi hatta hem
    henüz hep hepsi her herhangi herkes hiç hiçbir için ile ilgili ise işte itibaren kadar karşın kendi
    kendine kendini ki kim kimse mi mı mu mü nasıl ne neden nedenle nerde nerede nereye niçin niye o olan
    olarak oldu olduğu olduğunu olmak olması olmayan olup on ona ondan onlar onları onların onu onun orada
    öyle pek rağmen sadece sanki sen senin siz size sizi sizin son sonra şey şeyi şimdi şu şuna şunda şundan
    şunu tarafından tüm tümü üzere var vardır ve veya ya yani yapılan yine yok zaten çok çünkü önce olsun
    olur olabilir kez gerek ayrı aynı bütün biri birisi bunlardan buradan çoğu daima dek dahil
    """.split()
)
EN_DURAK = frozenset(
    """
    a about above after again against all am an and any are as at be because been before being below between
    both but by can could did do does doing down during each few for from further had has have having he her
    here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not
    now of off on once only or other our ours ourselves out over own same she should so some such than that
    the their theirs them themselves then there these they this those through to too under until up very was
    we were what when where which while who whom why will with you your yours yourself yourselves us also
    may might must shall would get got one two new
    """.split()
)

DE_DURAK = frozenset(
    """
    der die das den dem des ein eine einer eines einem einen und oder aber auch als am an auf aus bei bin bis
    bist da dann daran darum dass dein deine dem denn dich dir doch du durch er es euch euer für hat haben hatte
    hier ich ihm ihn ihr ihre im in ist ja jede jeder jedes kann kein keine man mehr mein meine mich mir mit muss
    nach nicht noch nun nur ob ohne sehr sein seine sich sie sind so über um und uns unser unter vom von vor war
    waren was weil wenn wer wie wir wird wo zu zum zur zwischen sowie wurde werden diese dieser dieses
    """.split()
)

#: Hedef anahtar kelime: en çok 60 karakter, 6 sözcük; sözcükler harf/rakam, aralarında boşluk, - ya da '.
KELIME_TAVANI = 60
KELIME_SOZCUK_TAVANI = 6
_HEDEF_DESENI = re.compile(r"[^\W_]+(?:[ \-'’][^\W_]+)*", re.U)
#: Hedef ifade metnin bu yüzdesinden fazlasını kaplıyorsa doğal görünmez (yol gösterici eşik, kural değil).
HEDEF_ASIRI_YUZDE = 3.0
#: Tek bir kelime metnin bu yüzdesinden fazlasıysa (ve en az ASIRI_ADET kez geçiyorsa) aşırı tekrar uyarısı.
ASIRI_YUZDE = 5.0
ASIRI_ADET = 10


def kucuk_harf(metin: str, dil: str = "") -> str:
    """Dile duyarlı küçük harf: Türkçe/Azericede I→ı, İ→i (Python'un `lower()`'ı I→i, İ→i̇ yapar)."""
    if (dil or "").lower()[:2] in ("tr", "az"):
        metin = metin.replace("I", "ı").replace("İ", "i")
    else:
        metin = metin.replace("İ", "i")
    return metin.lower()


def sozcukler(metin: str, dil: str = "") -> List[str]:
    """Küçük harfe çevrilmiş harf dizileri (rakam ve noktalama sözcük sayılmaz)."""
    return _SOZCUK.findall(kucuk_harf(metin or "", dil))


def gorunur_metin(html: str) -> str:
    govde = si._YORUM.sub(" ", html)
    govde = _GORUNMEZ.sub(" ", govde)
    return duz_metin(govde)


def _durak_listesi(dil: str) -> frozenset:
    d = (dil or "").lower()[:2]
    return {"tr": TR_DURAK, "az": TR_DURAK, "en": EN_DURAK, "de": DE_DURAK}.get(d, TR_DURAK | EN_DURAK | DE_DURAK)


def kelime_analizi(metin: str, dil: str = "") -> Dict[str, Any]:
    soz = sozcukler(metin, dil)
    durak = _durak_listesi(dil)
    anlamli = [w for w in soz if len(w) > 1 and w not in durak]
    toplam = len(soz)
    sayac = Counter(anlamli)

    def gecerli(w: str) -> bool:
        return len(w) > 1 and w not in durak

    ikili: Counter = Counter()
    uclu: Counter = Counter()
    for i in range(len(soz) - 1):
        a, b = soz[i], soz[i + 1]
        if gecerli(a) and gecerli(b):
            ikili[f"{a} {b}"] += 1
        if i + 2 < len(soz):
            c = soz[i + 2]
            # Üçlüde ortadaki durak kelime olabilir ("arama motoru optimizasyonu", "seo ve sem" değil).
            if gecerli(a) and gecerli(c) and len(b) > 1:
                uclu[f"{a} {b} {c}"] += 1

    def yuzde(n: int, uzunluk: int = 1) -> float:
        return round(100 * n * uzunluk / toplam, 2) if toplam else 0.0

    return {
        "toplam_kelime": toplam,
        "anlamli_kelime": len(anlamli),
        "benzersiz": len(sayac),
        "en_sik": [{"kelime": w, "sayi": n, "yuzde": yuzde(n)} for w, n in sayac.most_common(20)],
        "ikililer": [{"kelime": w, "sayi": n, "yuzde": yuzde(n, 2)} for w, n in ikili.most_common(10) if n > 1],
        "ucluler": [{"kelime": w, "sayi": n, "yuzde": yuzde(n, 3)} for w, n in uclu.most_common(10) if n > 1],
    }


def kelime_dogrula(ham: Optional[str]) -> Optional[str]:
    """İsteğe bağlı hedef anahtar kelime. Boşsa None; biçim dışıysa AnalizHatasi("kelime_gecersiz")."""
    k = " ".join(str(ham or "").split())
    if not k:
        return None
    if (
        len(k) > KELIME_TAVANI
        or len(k.split()) > KELIME_SOZCUK_TAVANI
        or not _HEDEF_DESENI.fullmatch(k)
        or not _SOZCUK.search(k)
    ):
        raise AnalizHatasi("kelime_gecersiz")
    return k


def ifade_sayisi(dizi: List[str], ifade: List[str]) -> int:
    """`ifade` sözcük dizisi `dizi`de kaç kez (üst üste binmeden değil, her başlangıçta) geçiyor."""
    n = len(ifade)
    if not n or len(dizi) < n:
        return 0
    return sum(1 for i in range(len(dizi) - n + 1) if dizi[i : i + n] == ifade)


def _katla(metin: str) -> str:
    """Adres karşılaştırması için ASCII'ye katla: ş→s, ı/İ→i, ğ→g, é→e…"""
    m = (metin or "").replace("ı", "i").replace("İ", "i")
    m = unicodedata.normalize("NFKD", m)
    return "".join(c for c in m if not unicodedata.combining(c)).lower()


def kelime_incele(s: Sonuc, html: str, son_url: str, hedef: Optional[str]) -> None:
    dil = html_dili(html)
    metin = gorunur_metin(html)
    analiz = kelime_analizi(metin, dil)
    toplam = analiz["toplam_kelime"]
    if toplam < motor.KELIME_ALT:
        s.ekle("icerik_uzunlugu", "icerik_az", "uyari", toplam)
    else:
        s.ekle("icerik_uzunlugu", "kelime_iyi", "iyi", toplam)
    asiri = [k for k in analiz["en_sik"] if k["yuzde"] > ASIRI_YUZDE and k["sayi"] >= ASIRI_ADET]
    if asiri:
        s.ekle("anahtar_yogunlugu", "anahtar_asiri", "uyari", {"kelime": asiri[0]["kelime"], "yuzde": asiri[0]["yuzde"]})
    elif analiz["en_sik"]:
        s.ekle("anahtar_yogunlugu", "yogunluk_iyi", "iyi", analiz["en_sik"][0]["kelime"])

    hedef_veri: Optional[Dict[str, Any]] = None
    if hedef:
        ifade = sozcukler(hedef, dil)
        sayi = ifade_sayisi(sozcukler(metin, dil), ifade)
        yuzde = round(100 * sayi * len(ifade) / toplam, 2) if toplam else 0.0
        bas = bas_bolumu(html)
        basliklar_ = [duz_metin(m) for m in _BASLIK.findall(bas)]
        aciklama = (_metalar(bas).get("description") or [""])[0]
        h1ler = [b["metin"] for b in basliklari_cikar(html) if b["seviye"] == 1]
        yol_sozcukleri = re.findall(r"[a-z]+", _katla(unquote(urlsplit(son_url).path)))
        konum = {
            "title": bool(basliklar_) and ifade_sayisi(sozcukler(basliklar_[0], dil), ifade) > 0,
            "h1": any(ifade_sayisi(sozcukler(h, dil), ifade) > 0 for h in h1ler),
            "aciklama": ifade_sayisi(sozcukler(aciklama, dil), ifade) > 0,
            "url": ifade_sayisi(yol_sozcukleri, [_katla(w) for w in ifade]) > 0,
        }
        gosterim = _kisalt(hedef, KELIME_TAVANI)
        if sayi == 0:
            s.ekle("hedef_kelime", "hedef_yok", "hata", gosterim)
        elif yuzde > HEDEF_ASIRI_YUZDE:
            s.ekle("hedef_kelime", "hedef_asiri", "uyari", {"kelime": gosterim, "sayi": sayi, "yuzde": yuzde})
        else:
            s.ekle("hedef_kelime", "hedef_iyi", "iyi", {"kelime": gosterim, "sayi": sayi, "yuzde": yuzde})
        if not konum["title"]:
            s.ekle("hedef_konum", "hedef_title_yok", "uyari", gosterim)
        if not konum["h1"]:
            s.ekle("hedef_konum", "hedef_h1_yok", "uyari", gosterim)
        if not konum["aciklama"]:
            s.ekle("hedef_konum", "hedef_aciklama_yok", "bilgi", gosterim)
        if not konum["url"]:
            s.ekle("hedef_konum", "hedef_url_yok", "bilgi", gosterim)
        if all(konum.values()):
            s.ekle("hedef_konum", "hedef_konum_iyi", "iyi", gosterim)
        hedef_veri = {"kelime": gosterim, "sayi": sayi, "yuzde": yuzde, **konum}
    s.veri.update({"dil": _kisalt(dil, 20), **analiz, "hedef": hedef_veri})


async def kelime_yogunlugu(gezgin: motor.Gezgin, url: str, secenek: Dict[str, Any]) -> Dict[str, Any]:
    y = await _ana_sayfa(gezgin, url)
    s = Sonuc("kelime-yogunlugu")
    kelime_incele(s, y.govde, y.url, secenek.get("kelime"))
    return s.sozluk(url, y.url, y.durum)


# ==========================================================================
# Çalıştırıcı
# ==========================================================================
AracFonksiyonu = Callable[[motor.Gezgin, str, Dict[str, Any]], Awaitable[Dict[str, Any]]]

FONKSIYONLAR: Dict[str, AracFonksiyonu] = {
    "meta-etiketleri": meta_etiketleri,
    "open-graph": open_graph,
    "schema-okuyucu": schema_okuyucu,
    "robots-txt": robots_txt,
    "site-haritasi": site_haritasi,
    "yonlendirme": yonlendirme,
    "guvenlik-basliklari": guvenlik_basliklari,
    "ssl-sertifikasi": ssl_sertifikasi,
    "baslik-yapisi": baslik_yapisi,
    "kelime-yogunlugu": kelime_yogunlugu,
}
assert tuple(FONKSIYONLAR) == ARACLAR


def secenekleri_dogrula(arac: str, secenek: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Araca özel girdiler (robots: ajan, kelime: hedef). Biçim dışıysa AnalizHatasi."""
    secenek = dict(secenek or {})
    if arac == "robots-txt":
        secenek["ajan"] = ajan_dogrula(secenek.get("ajan"))
    if arac == "kelime-yogunlugu":
        secenek["kelime"] = kelime_dogrula(secenek.get("kelime"))
    return secenek


async def calistir(arac: str, ham_url: str, secenek: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Aracı çalıştırır. Adres reddedilir/ulaşılamazsa AnalizHatasi (kodu ön yüzde çevriliyor)."""
    if arac not in FONKSIYONLAR:
        raise AnalizHatasi("arac_yok")
    secenek = secenekleri_dogrula(arac, secenek)
    url, _host, _alan = motor.adresi_normalize(ham_url)
    # Hiçbir istek atılmadan önce: adres baştan iç ağa çıkıyorsa dur.
    await motor.adres_dogrula(url)
    async with motor._istemci(zaman_asimi=ISTEK_ZAMAN_ASIMI, eszamanlilik=ESZAMANLILIK, ajan=AJAN) as istemci:
        gezgin = motor.Gezgin(istemci, eszamanlilik=ESZAMANLILIK, zaman_asimi=ISTEK_ZAMAN_ASIMI, gunlukle=False)
        try:
            return await asyncio.wait_for(FONKSIYONLAR[arac](gezgin, url, secenek), TOPLAM_TAVAN)
        except asyncio.TimeoutError as exc:
            raise AnalizHatasi("zaman_asimi") from exc


# ==========================================================================
# "Sonucu e-postayla gönder" — kısa ömürlü önbellek + e-posta içeriği
# ==========================================================================
#: Sonuç, e-posta isteği gelene kadar en çok bu kadar bellekte durur (saniye).
ONBELLEK_SURESI = 30 * 60
ONBELLEK_TAVANI = 300


class SonucOnbellegi:
    """Bellek içi, kısa ömürlü sonuç deposu: `jeton → (bitiş, araç, sonuç)`.

    Diske ya da veritabanına YAZILMAZ; süreç yeniden başlarsa boşalır. E-posta
    seçeneği açıkken her başarılı çalıştırmanın sonucu `ONBELLEK_SURESI` kadar
    burada durur. "Sonucu e-postayla gönder" isteği yalnız jetonu taşır: gönderilen
    içerik sunucunun ürettiği sonuçtur, istemciden ALINMAZ (bu uçla başkasına
    keyfi metin gönderilemesin). Gönderilince jeton silinir (tek kullanım).
    """

    def __init__(self, sure: float = ONBELLEK_SURESI, tavan: int = ONBELLEK_TAVANI, saat=time.monotonic):
        self.sure = sure
        self.tavan = tavan
        self.saat = saat
        self._kayit: "OrderedDict[str, Tuple[float, str, Dict[str, Any]]]" = OrderedDict()

    def _ayikla(self) -> None:
        simdi = self.saat()
        for jeton in [j for j, (bitis, _a, _s) in self._kayit.items() if bitis <= simdi]:
            self._kayit.pop(jeton, None)

    def koy(self, arac: str, sonuc: Dict[str, Any]) -> str:
        self._ayikla()
        while len(self._kayit) >= self.tavan:
            self._kayit.popitem(last=False)
        jeton = secrets.token_urlsafe(18)
        self._kayit[jeton] = (self.saat() + self.sure, arac, sonuc)
        return jeton

    def al(self, jeton: str, arac: str) -> Optional[Dict[str, Any]]:
        self._ayikla()
        kayit = self._kayit.get(jeton or "")
        if not kayit or kayit[1] != arac:
            return None
        return kayit[2]

    def sil(self, jeton: str) -> None:
        self._kayit.pop(jeton or "", None)

    def temizle(self) -> None:
        self._kayit.clear()

    def __len__(self) -> int:
        return len(self._kayit)


onbellek = SonucOnbellegi()

#: Araç kısa adı → ön yüz metin anahtarı (`seoAraclari.arac.<anahtar>`); `prerender/seo-araclari-veri.js` ile aynı.
ARAC_ANAHTARI: Dict[str, str] = {
    "meta-etiketleri": "meta",
    "open-graph": "og",
    "schema-okuyucu": "schema",
    "robots-txt": "robots",
    "site-haritasi": "sitemap",
    "yonlendirme": "yonlendirme",
    "guvenlik-basliklari": "guvenlik",
    "ssl-sertifikasi": "ssl",
    "baslik-yapisi": "basliklar",
    "kelime-yogunlugu": "kelime",
}
assert tuple(ARAC_ANAHTARI) == ARACLAR

DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")

#: Ön yüz metinlerinden üretilen özet (araç adı, kontrol adı, bulgu cümlesi; 7 dil).
#: Üretim: `python -m scripts.seo_arac_metinleri` (test eşitliği denetliyor).
METIN_DOSYASI = Path(__file__).resolve().parents[1] / "data" / "seo_arac_metinleri.json"
_METINLER: Optional[Dict[str, Any]] = None


def metinler() -> Dict[str, Any]:
    global _METINLER
    if _METINLER is None:
        try:
            _METINLER = json.loads(METIN_DOSYASI.read_text("utf-8"))
        except (OSError, ValueError):  # dosya yoksa e-posta kodlarla gider, düşmez
            logger.warning("SEO aracı metin dosyası okunamadı: %s", METIN_DOSYASI.name)
            _METINLER = {}
    return _METINLER


#: E-postanın kendi metinleri (7 dil). `{arac}`, `{alan}`, `{url}`, `{ad}`, `{sayi}` yer tutucuları.
EPOSTA_METINLERI: Dict[str, Dict[str, str]] = {
    "tr": {
        "konu": "{arac} sonucu: {alan}",
        "selam": "Merhaba {ad},",
        "selam_adsiz": "Merhaba,",
        "giris": "mehmetkuru.dev'deki ücretsiz “{arac}” aracıyla {url} adresini kontrol ettiniz. Sonuç aşağıda.",
        "puan": "Puan",
        "ozet": "Özet",
        "sorunlar": "Düzeltilmesi önerilenler",
        "sorun_yok": "Önemli bir sorun bulunmadı.",
        "fazlasi": "… ve {sayi} bulgu daha (tamamı sitede).",
        "bilgi_notu": "{sayi} bilgi notu ve {iyi} başarılı kontrol sitede ayrıntılı görünür.",
        "tekrar": "Sonucu sitede ayrıntılı gör",
        "tam_analiz": "Sitenin tam analizini ücretsiz al",
        "tam_analiz_metin": "Hız, SEO, içerik, teknik, güvenlik ve yapay zekâ görünürlüğünü 0–100 puanla ölçen tam rapor.",
        "not": "Bu e-postayı mehmetkuru.dev'deki SEO aracına adresinizi yazarak istediniz. Sorguladığınız site adresi sunucumuzda saklanmaz; e-posta adresiniz yalnız bu talebi yanıtlamak için kullanılır.",
        "imza": "Mehmet KURU · mehmetkuru.dev",
    },
    "en": {
        "konu": "{arac} result: {alan}",
        "selam": "Hi {ad},",
        "selam_adsiz": "Hi,",
        "giris": "You checked {url} with the free “{arac}” tool on mehmetkuru.dev. Here is the result.",
        "puan": "Score",
        "ozet": "Summary",
        "sorunlar": "Recommended fixes",
        "sorun_yok": "No significant issues were found.",
        "fazlasi": "… and {sayi} more findings (all of them on the site).",
        "bilgi_notu": "{sayi} informational notes and {iyi} passed checks are shown in detail on the site.",
        "tekrar": "See the detailed result on the site",
        "tam_analiz": "Get a free full analysis of the site",
        "tam_analiz_metin": "A full report that scores speed, SEO, content, technical health, security and AI visibility from 0 to 100.",
        "not": "You requested this email by entering your address in the SEO tool on mehmetkuru.dev. The site address you checked is not stored on our server; your email address is used only to answer this request.",
        "imza": "Mehmet KURU · mehmetkuru.dev",
    },
    "de": {
        "konu": "Ergebnis {arac}: {alan}",
        "selam": "Hallo {ad},",
        "selam_adsiz": "Hallo,",
        "giris": "Sie haben {url} mit dem kostenlosen Tool „{arac}“ auf mehmetkuru.dev geprüft. Hier ist das Ergebnis.",
        "puan": "Punktzahl",
        "ozet": "Zusammenfassung",
        "sorunlar": "Empfohlene Korrekturen",
        "sorun_yok": "Es wurden keine wesentlichen Probleme gefunden.",
        "fazlasi": "… und {sayi} weitere Befunde (alle auf der Website).",
        "bilgi_notu": "{sayi} Hinweise und {iyi} bestandene Prüfungen sehen Sie ausführlich auf der Website.",
        "tekrar": "Ausführliches Ergebnis auf der Website ansehen",
        "tam_analiz": "Kostenlose vollständige Analyse der Website anfordern",
        "tam_analiz_metin": "Ein vollständiger Bericht, der Geschwindigkeit, SEO, Inhalt, Technik, Sicherheit und KI-Sichtbarkeit mit 0–100 Punkten bewertet.",
        "not": "Sie haben diese E-Mail angefordert, indem Sie Ihre Adresse im SEO-Tool auf mehmetkuru.dev eingegeben haben. Die geprüfte Website-Adresse wird auf unserem Server nicht gespeichert; Ihre E-Mail-Adresse wird nur zur Beantwortung dieser Anfrage verwendet.",
        "imza": "Mehmet KURU · mehmetkuru.dev",
    },
    "ru": {
        "konu": "Результат «{arac}»: {alan}",
        "selam": "Здравствуйте, {ad}!",
        "selam_adsiz": "Здравствуйте!",
        "giris": "Вы проверили {url} бесплатным инструментом «{arac}» на mehmetkuru.dev. Результат ниже.",
        "puan": "Оценка",
        "ozet": "Сводка",
        "sorunlar": "Что рекомендуется исправить",
        "sorun_yok": "Существенных проблем не найдено.",
        "fazlasi": "… и ещё {sayi} замечаний (все — на сайте).",
        "bilgi_notu": "{sayi} информационных замечаний и {iyi} пройденных проверок подробно показаны на сайте.",
        "tekrar": "Подробный результат на сайте",
        "tam_analiz": "Получить бесплатный полный анализ сайта",
        "tam_analiz_metin": "Полный отчёт с оценкой от 0 до 100: скорость, SEO, контент, техническое состояние, безопасность и видимость для ИИ.",
        "not": "Вы запросили это письмо, указав свой адрес в SEO-инструменте на mehmetkuru.dev. Проверенный адрес сайта не хранится на нашем сервере; ваш адрес электронной почты используется только для ответа на этот запрос.",
        "imza": "Mehmet KURU · mehmetkuru.dev",
    },
    "zh": {
        "konu": "{arac}结果：{alan}",
        "selam": "{ad}，您好：",
        "selam_adsiz": "您好：",
        "giris": "您使用 mehmetkuru.dev 上的免费工具“{arac}”检查了 {url}，结果如下。",
        "puan": "得分",
        "ozet": "摘要",
        "sorunlar": "建议修复的问题",
        "sorun_yok": "未发现明显问题。",
        "fazlasi": "……另有 {sayi} 项发现（完整内容见网站）。",
        "bilgi_notu": "{sayi} 条提示和 {iyi} 项通过的检查可在网站上查看详情。",
        "tekrar": "在网站上查看详细结果",
        "tam_analiz": "免费获取网站完整分析",
        "tam_analiz_metin": "完整报告以 0–100 分评估速度、SEO、内容、技术、安全和 AI 可见性。",
        "not": "您在 mehmetkuru.dev 的 SEO 工具中填写了邮箱地址，因此收到这封邮件。您检查的网站地址不会保存在我们的服务器上；您的邮箱地址仅用于回复本次请求。",
        "imza": "Mehmet KURU · mehmetkuru.dev",
    },
    "hi": {
        "konu": "{arac} परिणाम: {alan}",
        "selam": "नमस्ते {ad},",
        "selam_adsiz": "नमस्ते,",
        "giris": "आपने mehmetkuru.dev के मुफ़्त “{arac}” टूल से {url} की जाँच की। परिणाम नीचे है।",
        "puan": "स्कोर",
        "ozet": "सारांश",
        "sorunlar": "सुझाए गए सुधार",
        "sorun_yok": "कोई बड़ी समस्या नहीं मिली।",
        "fazlasi": "… और {sayi} अन्य निष्कर्ष (सभी साइट पर)।",
        "bilgi_notu": "{sayi} जानकारी नोट और {iyi} सफल जाँचें साइट पर विस्तार से दिखती हैं।",
        "tekrar": "साइट पर विस्तृत परिणाम देखें",
        "tam_analiz": "साइट का पूरा विश्लेषण मुफ़्त पाएँ",
        "tam_analiz_metin": "गति, SEO, सामग्री, तकनीकी स्थिति, सुरक्षा और AI दृश्यता को 0–100 अंकों में मापने वाली पूरी रिपोर्ट।",
        "not": "आपने mehmetkuru.dev के SEO टूल में अपना ईमेल पता लिखकर यह ईमेल माँगा था। जाँचा गया साइट पता हमारे सर्वर पर सहेजा नहीं जाता; आपका ईमेल पता केवल इस अनुरोध का उत्तर देने के लिए उपयोग होता है।",
        "imza": "Mehmet KURU · mehmetkuru.dev",
    },
    "ar": {
        "konu": "نتيجة {arac}: {alan}",
        "selam": "مرحبًا {ad}،",
        "selam_adsiz": "مرحبًا،",
        "giris": "لقد فحصت {url} باستخدام أداة «{arac}» المجانية على mehmetkuru.dev. إليك النتيجة.",
        "puan": "النتيجة",
        "ozet": "الملخص",
        "sorunlar": "إصلاحات مقترحة",
        "sorun_yok": "لم يتم العثور على مشكلات مهمة.",
        "fazlasi": "… و{sayi} ملاحظات أخرى (جميعها على الموقع).",
        "bilgi_notu": "تظهر {sayi} ملاحظات معلوماتية و{iyi} فحوصات ناجحة بالتفصيل على الموقع.",
        "tekrar": "عرض النتيجة المفصلة على الموقع",
        "tam_analiz": "احصل على تحليل كامل ومجاني للموقع",
        "tam_analiz_metin": "تقرير كامل يقيّم السرعة وتحسين محركات البحث والمحتوى والجانب التقني والأمان والظهور في الذكاء الاصطناعي من 0 إلى 100.",
        "not": "طلبت هذه الرسالة بإدخال عنوان بريدك في أداة SEO على mehmetkuru.dev. لا يُحفظ عنوان الموقع الذي فحصته على خادمنا، ويُستخدم بريدك الإلكتروني فقط للرد على هذا الطلب.",
        "imza": "Mehmet KURU · mehmetkuru.dev",
    },
}
assert set(EPOSTA_METINLERI) == set(DILLER)

#: E-postada listelenen sorun (hata + uyarı) en çok.
EPOSTA_SORUN_TAVANI = 20
#: Hedef sitenin bulgu değerine giren metin (başlık, kelime…) e-postada en çok bu kadar karakter.
EPOSTA_DEGER_TAVANI = 80
_YER_TUTUCU = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def dil_sec(ham: Optional[str]) -> str:
    d = (ham or "").strip().lower()[:2]
    return d if d in DILLER else "tr"


def site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


def _dil_oneki(dil: str) -> str:
    return "" if dil == "tr" else f"/{dil}"


def alan_adi(sonuc: Dict[str, Any]) -> str:
    """Sonucun (son) adresindeki ana makine adı."""
    url = str(sonuc.get("son_url") or sonuc.get("url") or "")
    return urlsplit(url).hostname or url


def arac_adi(arac: str, dil: str) -> str:
    return ((metinler().get(dil) or {}).get("arac") or {}).get(arac) or arac


def _deger_metni(deger: Any) -> str:
    return _kisalt(str(deger), EPOSTA_DEGER_TAVANI)


def bulgu_cumlesi(b: Dict[str, Any], dil: str) -> str:
    """Ön yüzdeki `bulguMetni` ile aynı yerleştirme: sözlük değerin alanları + düz `deger`."""
    sablon = ((metinler().get(dil) or {}).get("bulgu") or {}).get(b.get("kod") or "")
    deger = b.get("deger")
    alanlar: Dict[str, str] = {}
    if isinstance(deger, dict):
        alanlar = {str(k): _deger_metni(v) for k, v in deger.items()}
        alanlar.setdefault("deger", "")
    elif deger is not None:
        alanlar["deger"] = _deger_metni(deger)
    if not sablon:
        return f"{b.get('kod')}" + (f": {alanlar.get('deger')}" if alanlar.get("deger") else "")
    return _YER_TUTUCU.sub(lambda m: alanlar.get(m.group(1), ""), sablon)


def kontrol_adi(kontrol: str, dil: str) -> str:
    return ((metinler().get(dil) or {}).get("kontrol") or {}).get(kontrol) or kontrol


def seviye_adi(seviye: str, dil: str) -> str:
    return ((metinler().get(dil) or {}).get("seviye") or {}).get(seviye) or seviye


def eposta_icerigi(sonuc: Dict[str, Any], dil: Optional[str] = None, ad: Optional[str] = None) -> Dict[str, str]:
    """Sonuç e-postası: {"konu", "metin", "html"}. Bütün dinamik değerler HTML'de kaçışlı."""
    dil = dil_sec(dil)
    m = EPOSTA_METINLERI[dil]
    arac = str(sonuc.get("arac") or "")
    ad_ = arac_adi(arac, dil)
    url = str(sonuc.get("son_url") or sonuc.get("url") or "")
    alan = alan_adi(sonuc)
    kok = f"{urlsplit(url).scheme or 'https'}://{urlsplit(url).netloc}/" if urlsplit(url).netloc else url
    taban = site_adresi()
    tekrar = f"{taban}{_dil_oneki(dil)}/seo-araclari/{arac}/?{urlencode({'url': str(sonuc.get('url') or url), 'calistir': '1'})}"
    tam = f"{taban}{_dil_oneki(dil)}/site-analizi/?{urlencode({'url': kok, 'arac': arac})}"

    bulgular = list(sonuc.get("bulgular") or [])
    sorunlar = [b for b in bulgular if b.get("seviye") in ("hata", "uyari")]
    sorunlar.sort(key=lambda b: 0 if b.get("seviye") == "hata" else 1)
    ozet = sonuc.get("ozet") or {}
    ozet_satiri = " · ".join(f"{int(ozet.get(s) or 0)} {seviye_adi(s, dil)}" for s in SEVIYELER)
    puan = sonuc.get("puan")
    selam = m["selam"].format(ad=_kisalt(ad, 60)) if ad else m["selam_adsiz"]
    giris = m["giris"].format(arac=ad_, url=url)
    konu = _kisalt(m["konu"].format(arac=ad_, alan=alan), 150)

    satirlar = [selam, "", giris, ""]
    if puan is not None:
        satirlar.append(f"{m['puan']}: {puan}/100")
    satirlar.append(f"{m['ozet']}: {ozet_satiri}")
    satirlar.append("")
    satirlar.append(f"{m['sorunlar']}:")
    if not sorunlar:
        satirlar.append(f"- {m['sorun_yok']}")
    for b in sorunlar[:EPOSTA_SORUN_TAVANI]:
        satirlar.append(f"- [{seviye_adi(b['seviye'], dil)}] {kontrol_adi(b.get('kontrol', ''), dil)}: {bulgu_cumlesi(b, dil)}")
    if len(sorunlar) > EPOSTA_SORUN_TAVANI:
        satirlar.append(m["fazlasi"].format(sayi=len(sorunlar) - EPOSTA_SORUN_TAVANI))
    satirlar += [
        "",
        m["bilgi_notu"].format(sayi=int(ozet.get("bilgi") or 0), iyi=int(ozet.get("iyi") or 0)),
        "",
        f"{m['tekrar']}: {tekrar}",
        f"{m['tam_analiz']}: {tam}",
        m["tam_analiz_metin"],
        "",
        m["not"],
        "",
        f"— {m['imza']}",
    ]
    metin = "\n".join(satirlar)

    e = html_modulu.escape
    renk = {"hata": "#dc2626", "uyari": "#d97706"}
    yon = "rtl" if dil == "ar" else "ltr"
    sorun_html = (
        "".join(
            f'<li style="margin:0 0 8px"><strong style="color:{renk.get(b["seviye"], "#334155")}">'
            f"{e(seviye_adi(b['seviye'], dil))}</strong> · {e(kontrol_adi(b.get('kontrol', ''), dil))}<br>"
            f'<span style="color:#334155">{e(bulgu_cumlesi(b, dil))}</span></li>'
            for b in sorunlar[:EPOSTA_SORUN_TAVANI]
        )
        or f"<li>{e(m['sorun_yok'])}</li>"
    )
    if len(sorunlar) > EPOSTA_SORUN_TAVANI:
        sorun_html += f'<li style="list-style:none;color:#64748b">{e(m["fazlasi"].format(sayi=len(sorunlar) - EPOSTA_SORUN_TAVANI))}</li>'
    dugme = (
        'display:inline-block;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:600;'
    )
    html = (
        f'<!doctype html><html lang="{dil}" dir="{yon}"><body style="margin:0;padding:24px;background:#f8fafc;'
        'font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#0f172a">'
        '<div style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;padding:24px">'
        f'<p style="margin:0 0 12px">{e(selam)}</p>'
        f'<p style="margin:0 0 16px;line-height:1.5">{e(giris)}</p>'
        + (f'<p style="margin:0 0 4px;font-size:18px"><strong>{e(m["puan"])}: {e(str(puan))}/100</strong></p>' if puan is not None else "")
        + f'<p style="margin:0 0 16px;color:#475569">{e(m["ozet"])}: {e(ozet_satiri)}</p>'
        f'<h2 style="font-size:16px;margin:0 0 8px">{e(m["sorunlar"])}</h2>'
        f'<ul style="padding-inline-start:18px;margin:0 0 16px">{sorun_html}</ul>'
        f'<p style="margin:0 0 20px;color:#64748b;font-size:13px">'
        f'{e(m["bilgi_notu"].format(sayi=int(ozet.get("bilgi") or 0), iyi=int(ozet.get("iyi") or 0)))}</p>'
        f'<p style="margin:0 0 12px"><a href="{e(tekrar, quote=True)}" style="{dugme}background:#7c3aed;color:#ffffff">{e(m["tekrar"])}</a></p>'
        f'<p style="margin:0 0 4px"><a href="{e(tam, quote=True)}" style="{dugme}background:#f1f5f9;color:#4c1d95;border:1px solid #ddd6fe">{e(m["tam_analiz"])}</a></p>'
        f'<p style="margin:0 0 20px;color:#64748b;font-size:13px">{e(m["tam_analiz_metin"])}</p>'
        f'<p style="margin:0;color:#94a3b8;font-size:12px;line-height:1.5">{e(m["not"])}</p>'
        f'<p style="margin:12px 0 0;color:#94a3b8;font-size:12px">— {e(m["imza"])}</p>'
        "</div></body></html>"
    )
    return {"konu": konu, "metin": metin, "html": html}


def crm_ozeti(sonuc: Dict[str, Any]) -> str:
    """CRM adayının ilk mesajı (Türkçe, kısa): araç, adres, puan, sayılar ve sorun kodları."""
    ozet = sonuc.get("ozet") or {}
    sorunlar = [f"{b.get('kontrol')}/{b.get('kod')}" for b in (sonuc.get("bulgular") or []) if b.get("seviye") in ("hata", "uyari")]
    satirlar = [
        f"Ücretsiz SEO aracı sonucu e-postayla istendi: {arac_adi(str(sonuc.get('arac')), 'tr')}",
        f"Adres: {sonuc.get('son_url') or sonuc.get('url')}",
    ]
    if sonuc.get("puan") is not None:
        satirlar.append(f"Puan: {sonuc.get('puan')}/100")
    satirlar.append(
        f"Hata {int(ozet.get('hata') or 0)}, uyarı {int(ozet.get('uyari') or 0)}, "
        f"bilgi {int(ozet.get('bilgi') or 0)}, başarılı {int(ozet.get('iyi') or 0)}"
    )
    if sorunlar:
        satirlar.append("Sorunlar: " + ", ".join(sorunlar[:15]) + (" …" if len(sorunlar) > 15 else ""))
    return "\n".join(satirlar)
