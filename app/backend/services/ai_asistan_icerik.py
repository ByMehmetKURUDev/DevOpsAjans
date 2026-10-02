"""Faz 5A — bilgi bankası kaynaklarından düz metin çıkarma.

* Belge: PDF (`pypdf`), DOCX (zip içindeki `word/document.xml`, kütüphanesiz —
  XML varlık genişletmesi yok, düzenli ifadeyle okunuyor; sıkıştırılmış boyut
  ve açılmış boyut sınırlı), TXT ve MD (UTF-8; olmazsa Windows-1254/Latin-1).
* Web sayfası: SSRF korumalı tarayıcı (`services/site_analizi`: her yönlendirmede
  adres denetimi + bağlantı anında IP denetimi — DNS yeniden bağlama), robots.txt'ye
  saygı (kendi ajan adımız ve `*`), site haritası (sitemap index dahil, en çok N sayfa).
  HTML'den betik/stil/menü/alt bilgi atılıyor; başlıklar (`h1`–`h6`) parçalama için
  `#` satırlarına çevriliyor.
* Modülden içe aktarma: QR menü mağazası (kategoriler ve ürünler, fiyat), randevu
  sayfası (etkinlik türleri, süre, bağlantı) — yalnız asistanın hesabına ait kayıtlar.

Hata kodları (`IcerikHatasi.kod`) ön yüzde yedi dilde çevriliyor.
"""

import asyncio
import html
import io
import json
import logging
import re
import time
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

logger = logging.getLogger(__name__)

AJAN_ADI = "MehmetKuruDevAsistan"
AJAN = f"{AJAN_ADI}/1.0 (+https://mehmetkuru.dev/gizlilik)"
BELGE_EN_COK_BAYT = 10 * 1024 * 1024
METIN_EN_COK = 400_000
PDF_EN_COK_SAYFA = 400
DOCX_ACIK_EN_COK = 30 * 1024 * 1024
SAYFA_EN_COK_URL = 200
TARAMA_SURESI_SN = 90.0
ESZAMANLILIK = 3
UZANTILAR = ("pdf", "docx", "txt", "md")


class IcerikHatasi(Exception):
    def __init__(self, kod: str, durum: int = 400, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.durum = durum
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


# ---------------------------------------------------------------------------
# Belgeler
# ---------------------------------------------------------------------------
def _uzanti(ad: str) -> str:
    ad = (ad or "").strip().lower()
    return ad.rsplit(".", 1)[-1] if "." in ad else ""


def _metin_coz(bayt: bytes) -> str:
    if b"\x00" in bayt[:4096]:
        raise IcerikHatasi("dosya_bozuk")
    for kodlama in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            return bayt.decode(kodlama)
        except UnicodeDecodeError:
            continue
    raise IcerikHatasi("dosya_bozuk")


def _pdf_metni(bayt: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - requirements.txt'te var
        raise IcerikHatasi("tur_desteklenmiyor")
    try:
        okuyucu = PdfReader(io.BytesIO(bayt))
        if okuyucu.is_encrypted:
            try:
                okuyucu.decrypt("")
            except Exception:  # noqa: BLE001
                raise IcerikHatasi("dosya_sifreli")
        sayfalar = []
        for i, sayfa in enumerate(okuyucu.pages):
            if i >= PDF_EN_COK_SAYFA:
                break
            sayfalar.append((sayfa.extract_text() or "").strip())
            if sum(map(len, sayfalar)) > METIN_EN_COK:
                break
    except IcerikHatasi:
        raise
    except Exception as hata:  # noqa: BLE001 - bozuk/kısmi PDF
        logger.info("PDF okunamadı: %s", type(hata).__name__)
        raise IcerikHatasi("dosya_bozuk")
    return "\n\n".join(s for s in sayfalar if s)


_W_P = re.compile(r"<w:p[ >].*?</w:p>|<w:p/>", re.S)
_W_STIL = re.compile(r'<w:pStyle\s+w:val="([^"]+)"')
_W_PARCA = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>|<w:tab/>|<w:br/>|<w:cr/>", re.S)
_BASLIK_STILI = re.compile(r"^(?:heading|baslik|başlık|berschrift|titre|titolo)\s*(\d)$", re.I)


def _docx_metni(bayt: bytes) -> str:
    try:
        arsiv = zipfile.ZipFile(io.BytesIO(bayt))
        bilgi = arsiv.getinfo("word/document.xml")
    except (zipfile.BadZipFile, KeyError, OSError):
        raise IcerikHatasi("dosya_bozuk")
    if bilgi.file_size > DOCX_ACIK_EN_COK:
        raise IcerikHatasi("dosya_buyuk", 413)
    try:
        xml = arsiv.read(bilgi).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        raise IcerikHatasi("dosya_bozuk")
    satirlar: List[str] = []
    for p in _W_P.findall(xml):
        parcalar = []
        for m in _W_PARCA.finditer(p):
            if m.group(1) is not None:
                parcalar.append(html.unescape(m.group(1)))
            elif m.group(0) == "<w:tab/>":
                parcalar.append("\t")
            else:
                parcalar.append("\n")
        metin = "".join(parcalar).strip()
        if not metin:
            satirlar.append("")
            continue
        stil = _W_STIL.search(p)
        seviye = None
        if stil:
            ad = stil.group(1).replace(" ", "")
            if ad.lower() == "title":
                seviye = 1
            else:
                b = _BASLIK_STILI.match(ad)
                seviye = int(b.group(1)) if b else None
        satirlar.append(("#" * max(1, min(6, seviye)) + " " + metin) if seviye else metin)
        satirlar.append("")
    return "\n".join(satirlar)


def belge_metni(dosya_adi: str, bayt: bytes) -> str:
    """Yüklenen belgeden düz metin. Hata → IcerikHatasi (tur_desteklenmiyor | dosya_buyuk | dosya_bozuk | bos)."""
    uz = _uzanti(dosya_adi)
    if uz not in UZANTILAR:
        raise IcerikHatasi("tur_desteklenmiyor", 415, turler=list(UZANTILAR))
    if len(bayt) > BELGE_EN_COK_BAYT:
        raise IcerikHatasi("dosya_buyuk", 413, en_cok_mb=BELGE_EN_COK_BAYT // (1024 * 1024))
    if not bayt:
        raise IcerikHatasi("bos")
    if uz == "pdf":
        if not bayt.startswith(b"%PDF"):
            raise IcerikHatasi("dosya_bozuk")
        metin = _pdf_metni(bayt)
    elif uz == "docx":
        if not bayt.startswith(b"PK"):
            raise IcerikHatasi("dosya_bozuk")
        metin = _docx_metni(bayt)
    else:
        metin = _metin_coz(bayt)
    metin = metin.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not metin:
        raise IcerikHatasi("bos")
    return metin[:METIN_EN_COK]


# ---------------------------------------------------------------------------
# HTML → metin
# ---------------------------------------------------------------------------
_GORUNMEZ = re.compile(
    r"<(script|style|noscript|template|svg|nav|footer|header|aside|form|iframe|canvas|select|button)\b[^>]*>.*?</\1\s*>",
    re.I | re.S,
)
_YORUM = re.compile(r"<!--.*?-->", re.S)
_ANA = re.compile(r"<(main|article)\b[^>]*>(.*?)</\1\s*>", re.I | re.S)
_BASLIK_ETIKETI = re.compile(r"<h([1-6])\b[^>]*>(.*?)</h\1\s*>", re.I | re.S)
_LI = re.compile(r"<li\b[^>]*>", re.I)
_BLOK = re.compile(r"</?(p|div|section|article|br|tr|ul|ol|table|blockquote|pre|dd|dt|li|main|h[1-6])\b[^>]*>", re.I)
_ETIKET = re.compile(r"<[^>]+>")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _duz(parca: str) -> str:
    return " ".join(html.unescape(_ETIKET.sub(" ", parca)).split())


def html_metni(belge: str) -> Tuple[str, str]:
    """(sayfa başlığı, başlık satırları korunmuş düz metin)."""
    baslik_m = _TITLE.search(belge or "")
    baslik = _duz(baslik_m.group(1))[:200] if baslik_m else ""
    govde = _YORUM.sub(" ", belge or "")
    govde = _GORUNMEZ.sub(" ", govde)
    ana = [m.group(2) for m in _ANA.finditer(govde)]
    if ana and sum(len(_duz(a)) for a in ana) > 200:
        govde = "\n".join(ana)
    govde = _BASLIK_ETIKETI.sub(lambda m: f"\n\n{'#' * int(m.group(1))} {_duz(m.group(2))}\n\n", govde)
    govde = _LI.sub("\n- ", govde)
    govde = _BLOK.sub("\n", govde)
    govde = html.unescape(_ETIKET.sub(" ", govde))
    satirlar = [" ".join(s.split()) for s in govde.split("\n")]
    metin = re.sub(r"\n{3,}", "\n\n", "\n".join(satirlar)).strip()
    return baslik, metin[:METIN_EN_COK]


# ---------------------------------------------------------------------------
# robots.txt ve site haritası
# ---------------------------------------------------------------------------
@dataclass
class Robots:
    kurallar: List[Tuple[bool, str]]
    haritalar: List[str]

    def izinli_mi(self, yol: str) -> bool:
        """En uzun eşleşen kural kazanır; eşitlikte Allow."""
        en_iyi: Optional[Tuple[int, bool]] = None
        for izin, desen in self.kurallar:
            if not desen:
                continue
            uzunluk = _desen_eslesir(desen, yol)
            if uzunluk is None:
                continue
            if en_iyi is None or uzunluk > en_iyi[0] or (uzunluk == en_iyi[0] and izin):
                en_iyi = (uzunluk, izin)
        return True if en_iyi is None else en_iyi[1]


def _desen_eslesir(desen: str, yol: str) -> Optional[int]:
    son = desen.endswith("$")
    govde = desen[:-1] if son else desen
    duzenli = "^" + ".*".join(re.escape(p) for p in govde.split("*")) + ("$" if son else "")
    return len(desen) if re.match(duzenli, yol) else None


def robots_coz(metin: str, ajan: str = AJAN_ADI) -> Robots:
    """Bizim ajan adımızın grubu varsa o, yoksa `*` grubu."""
    gruplar: List[Tuple[List[str], List[Tuple[bool, str]]]] = []
    haritalar: List[str] = []
    ajanlar: List[str] = []
    kurallar: List[Tuple[bool, str]] = []
    son_kural = False
    for ham in (metin or "").splitlines():
        satir = ham.split("#", 1)[0].strip()
        if ":" not in satir:
            continue
        ad, deger = (p.strip() for p in satir.split(":", 1))
        ad = ad.lower()
        if ad == "sitemap":
            if deger:
                haritalar.append(deger)
            continue
        if ad == "user-agent":
            if son_kural:
                gruplar.append((ajanlar, kurallar))
                ajanlar, kurallar = [], []
                son_kural = False
            ajanlar.append(deger.lower())
        elif ad in ("allow", "disallow") and ajanlar:
            son_kural = True
            kurallar.append((ad == "allow", deger))
    if ajanlar:
        gruplar.append((ajanlar, kurallar))
    ajan = ajan.lower()
    secili = next((k for a, k in gruplar if any(x and x != "*" and x in ajan for x in a)), None)
    if secili is None:
        secili = next((k for a, k in gruplar if "*" in a), [])
    return Robots(kurallar=secili, haritalar=haritalar)


_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)


def site_haritasi_coz(xml: str) -> Tuple[List[str], bool]:
    """(adresler, sitemap index mi)."""
    adresler = [html.unescape(a).strip() for a in _LOC.findall(xml or "")]
    return [a for a in adresler if a], bool(re.search(r"<sitemapindex\b", xml or "", re.I))


# ---------------------------------------------------------------------------
# Tarama
# ---------------------------------------------------------------------------
@dataclass
class SayfaMetni:
    adres: str
    baslik: str
    metin: str


def _host(url: str) -> str:
    h = (urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def _temiz_adres(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path or "/", p.query, ""))


def _yol(url: str) -> str:
    p = urlsplit(url)
    return (p.path or "/") + (f"?{p.query}" if p.query else "")


async def _robots_al(gezgin: Any, kok: str) -> Robots:
    yanit = await gezgin.getir(urljoin(kok, "/robots.txt"))
    if yanit.hata in ("adres_gecersiz", "adres_yasak", "cozumlenemedi"):
        raise IcerikHatasi(yanit.hata)
    if yanit.durum == 200 and yanit.govde:
        return robots_coz(yanit.govde)
    # 5xx: Google gibi temkinli davran (hepsi kapalı). 4xx / ulaşılamadı: robots yok sayılır
    # (ulaşılamayan sitede sayfa isteği de zaten hata verecek).
    if yanit.durum >= 500:
        return Robots(kurallar=[(False, "/")], haritalar=[])
    return Robots(kurallar=[], haritalar=[])


async def _harita_adresleri(gezgin: Any, harita: str, en_cok: int, host: str) -> List[str]:
    gorulen: List[str] = []
    kuyruk = [harita]
    ziyaret = 0
    while kuyruk and len(gorulen) < en_cok and ziyaret < 5:
        adres = kuyruk.pop(0)
        ziyaret += 1
        yanit = await gezgin.getir(adres)
        if yanit.durum != 200 or not yanit.govde:
            continue
        adresler, indeks = site_haritasi_coz(yanit.govde)
        if indeks:
            kuyruk.extend(adresler[:5])
            continue
        for a in adresler:
            if _host(a) == host and _temiz_adres(a) not in gorulen:
                gorulen.append(_temiz_adres(a))
                if len(gorulen) >= en_cok:
                    break
    return gorulen


async def url_kaynagini_getir(ham_url: str, kapsam: str = "tek", en_cok: int = 1) -> List[SayfaMetni]:
    """URL (tek sayfa) ya da site haritasından en çok `en_cok` sayfanın metni.

    Hata → IcerikHatasi: adres_gecersiz | adres_yasak | cozumlenemedi | ulasilamadi |
    robots_engelli | site_haritasi_yok | icerik_yok.
    """
    from services import site_analizi as sa

    try:
        url, _, _ = sa.adresi_normalize(ham_url)
    except sa.AnalizHatasi as h:
        raise IcerikHatasi(h.kod)
    en_cok = max(1, min(int(en_cok or 1), SAYFA_EN_COK_URL))
    bitis = time.monotonic() + TARAMA_SURESI_SN
    async with sa._istemci(ajan=AJAN, eszamanlilik=ESZAMANLILIK) as istemci:
        gezgin = sa.Gezgin(istemci, eszamanlilik=ESZAMANLILIK)
        p = urlsplit(url)
        kok = f"{p.scheme}://{p.netloc}/"
        robots = await _robots_al(gezgin, kok)
        host = _host(url)
        if kapsam == "site_haritasi":
            haritalar = [url] if p.path.lower().endswith(".xml") else (robots.haritalar or [urljoin(kok, "/sitemap.xml")])
            adresler: List[str] = []
            for h in haritalar[:3]:
                if _host(h) != host:
                    continue
                adresler += [a for a in await _harita_adresleri(gezgin, h, en_cok - len(adresler), host) if a not in adresler]
                if len(adresler) >= en_cok:
                    break
            if not adresler:
                raise IcerikHatasi("site_haritasi_yok")
        else:
            adresler = [url]
        adresler = [a for a in adresler if robots.izinli_mi(_yol(a))]
        if not adresler:
            raise IcerikHatasi("robots_engelli")

        sayfalar: List[SayfaMetni] = []
        son_hata: Optional[str] = None

        async def tek(adres: str) -> None:
            nonlocal son_hata
            if time.monotonic() > bitis:
                return
            yanit = await gezgin.getir(adres)
            if yanit.hata:
                son_hata = yanit.hata
                return
            tur = (yanit.basliklar.get("content-type") or "").lower()
            if yanit.durum != 200 or (tur and "html" not in tur and "text/plain" not in tur):
                return
            # Yönlendirmeyle başka siteye gidildiyse alma.
            if _host(yanit.url) != host or not robots.izinli_mi(_yol(yanit.url)):
                return
            if "text/plain" in tur:
                baslik, metin = "", yanit.govde.strip()
            else:
                baslik, metin = html_metni(yanit.govde)
            if len(metin) >= 40:
                sayfalar.append(SayfaMetni(adres=_temiz_adres(yanit.url), baslik=baslik, metin=metin))

        for i in range(0, len(adresler), ESZAMANLILIK):
            await asyncio.gather(*(tek(a) for a in adresler[i:i + ESZAMANLILIK]))
            if time.monotonic() > bitis:
                break
    if not sayfalar:
        if son_hata in ("adres_gecersiz", "adres_yasak", "cozumlenemedi", "ulasilamadi", "cok_yonlendirme"):
            raise IcerikHatasi(son_hata)
        raise IcerikHatasi("icerik_yok")
    sira = {a: i for i, a in enumerate(adresler)}
    return sorted(sayfalar, key=lambda s: sira.get(s.adres, 10**6))


# ---------------------------------------------------------------------------
# Modüllerden içe aktarma
# ---------------------------------------------------------------------------
MODULLER = ("qr_menu", "randevu")


def _para(kurus: Optional[int], birim: str) -> str:
    if kurus is None:
        return ""
    tutar = kurus / 100
    metin = f"{tutar:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if metin.endswith(",00"):
        metin = metin[:-3]
    return f"{metin} {birim}"


async def modul_secenekleri(db: Any, hesap: Optional[str]) -> List[Dict[str, Any]]:
    """Asistanın hesabına ait içe aktarılabilir kayıtlar: [{modul, id, ad}]."""
    from sqlalchemy import select

    sonuc: List[Dict[str, Any]] = []
    try:
        from models.qr_menu import MenuMagazalari

        kosul = MenuMagazalari.hesap_email == hesap if hesap else MenuMagazalari.hesap_email.is_(None)
        for m in (await db.execute(select(MenuMagazalari).where(kosul).order_by(MenuMagazalari.id))).scalars().all():
            sonuc.append({"modul": "qr_menu", "id": m.id, "ad": m.ad})
    except Exception:  # noqa: BLE001 - modül tablosu yoksa atla
        logger.debug("QR menü seçenekleri okunamadı", exc_info=True)
    try:
        from models.randevu import RandevuSayfalari

        kosul = RandevuSayfalari.hesap_email == hesap if hesap else RandevuSayfalari.hesap_email.is_(None)
        for p in (await db.execute(select(RandevuSayfalari).where(kosul).order_by(RandevuSayfalari.id))).scalars().all():
            sonuc.append({"modul": "randevu", "id": p.id, "ad": p.baslik})
    except Exception:  # noqa: BLE001
        logger.debug("Randevu seçenekleri okunamadı", exc_info=True)
    return sonuc


async def modul_metni(db: Any, hesap: Optional[str], modul: str, kayit_id: Any) -> Tuple[str, str]:
    """(başlık, metin). Kayıt asistanın hesabına ait değilse IcerikHatasi('modul_kaydi_yok', 404)."""
    from sqlalchemy import select

    try:
        kayit_id = int(kayit_id)
    except (TypeError, ValueError):
        raise IcerikHatasi("modul_kaydi_yok", 404)
    if modul == "qr_menu":
        from models.qr_menu import MenuKategorileri, MenuMagazalari, MenuUrunleri

        m = (await db.execute(select(MenuMagazalari).where(MenuMagazalari.id == kayit_id))).scalars().first()
        if m is None or (m.hesap_email or None) != (hesap or None):
            raise IcerikHatasi("modul_kaydi_yok", 404)
        satirlar = [f"# {m.ad}"]
        if m.aciklama:
            satirlar += ["", m.aciklama.strip()]
        iletisim = [x for x in (m.adres and f"Adres: {m.adres}", m.telefon and f"Telefon: {m.telefon}") if x]
        if iletisim:
            satirlar += ["", *iletisim]
        try:
            saatler = json.loads(m.calisma_saatleri or "null")
        except ValueError:
            saatler = None
        if isinstance(saatler, dict) and saatler:
            gun_adlari = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
            parcalar = []
            for g, araliklar in sorted(saatler.items(), key=lambda x: str(x[0])):
                try:
                    ad = gun_adlari[int(g)]
                except (ValueError, IndexError):
                    ad = str(g)
                if isinstance(araliklar, list) and araliklar:
                    parcalar.append(f"{ad}: " + ", ".join("–".join(map(str, a)) for a in araliklar if isinstance(a, (list, tuple))))
            if parcalar:
                satirlar += ["", "Çalışma saatleri: " + "; ".join(parcalar)]
        kategoriler = (await db.execute(
            select(MenuKategorileri).where(MenuKategorileri.magaza_id == m.id, MenuKategorileri.gizli.is_(False))
            .order_by(MenuKategorileri.sira, MenuKategorileri.id)
        )).scalars().all()
        urunler = (await db.execute(
            select(MenuUrunleri).where(MenuUrunleri.magaza_id == m.id, MenuUrunleri.gizli.is_(False))
            .order_by(MenuUrunleri.sira, MenuUrunleri.id)
        )).scalars().all()
        for k in kategoriler:
            satirlar += ["", f"## {k.ad}"]
            for u in (u for u in urunler if u.kategori_id == k.id):
                fiyat = _para(u.indirimli_fiyat if u.indirimli_fiyat is not None else u.fiyat, m.para_birimi or "TRY")
                bilgi = [f"- {u.ad}" + (f": {fiyat}" if fiyat else "")]
                if u.aciklama:
                    bilgi.append(f"  {u.aciklama.strip()}")
                if u.stokta_yok:
                    bilgi.append("  (şu an stokta yok)")
                satirlar += bilgi
        return m.ad, "\n".join(satirlar).strip()[:METIN_EN_COK]
    if modul == "randevu":
        from models.randevu import RandevuSayfalari, RandevuTurleri
        from services.randevu import sayfa_adresi

        p = (await db.execute(select(RandevuSayfalari).where(RandevuSayfalari.id == kayit_id))).scalars().first()
        if p is None or (p.hesap_email or None) != (hesap or None):
            raise IcerikHatasi("modul_kaydi_yok", 404)
        satirlar = [f"# {p.baslik}"]
        if p.karsilama:
            satirlar += ["", p.karsilama.strip()]
        satirlar += ["", f"Online randevu sayfası: {sayfa_adresi(p.slug)}"]
        turler = (await db.execute(
            select(RandevuTurleri).where(RandevuTurleri.sayfa_id == p.id, RandevuTurleri.aktif.is_(True))
            .order_by(RandevuTurleri.sira, RandevuTurleri.id)
        )).scalars().all()
        konum = {"jitsi": "görüntülü görüşme", "baglanti": "online toplantı", "telefon": "telefon", "yuz_yuze": "yüz yüze"}
        for t in turler:
            satirlar += ["", f"## {t.ad}", f"Süre: {t.sure_dk} dakika. Görüşme şekli: {konum.get(t.konum_turu, t.konum_turu)}.",
                         f"Randevu almak için: {sayfa_adresi(p.slug, t.slug)}"]
            if t.aciklama:
                satirlar.append(t.aciklama.strip())
        return p.baslik, "\n".join(satirlar).strip()[:METIN_EN_COK]
    raise IcerikHatasi("modul_gecersiz")
