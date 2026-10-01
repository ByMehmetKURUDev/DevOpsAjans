"""Faz 4Q — Dinamik QR stüdyosu ve kısa link: kurallar ve yardımcılar.

Bu dosyada veritabanına dokunmayan her şey var (router `routers/dinamik_qr.py`):

* Kod ve takma ad: 7 karakter, karışabilen harfler (0/O/o, 1/l/I) yok;
  takma ad küçük harf/rakam/tire, ayrılmış kelimeler engelli.
* Türler: her tür için alan doğrulaması + hedef üretimi. Hedef adresler
  yalnız beyaz listedeki şemalarla (http, https, tel, mailto, sms) üretilir;
  `javascript:`, `data:`, `file:` vb. hiçbir yoldan geçemez — taramada da
  yeniden doğrulanır (`guvenli_hedef_mi`).
* Statik türler (Wi-Fi, düz metin) yönlendirme olmadan veriyi doğrudan
  kodlar; tarama sayılamaz.
* vCard 3.0 ve iCalendar (.ics) üretimi (dinamik: `/q/<kod>` dosyayı döndürür).
  vCard alanları ileride dijital kartvizit modülünün de kullanacağı biçimde.
* User-Agent → cihaz sınıfı / işletim sistemi ailesi / bot-önizleyici.
  Tam UA saklanmaz; yalnız bu üç sonuç.
* Görsel: `segno` (saf Python) ile SVG ve PNG; renk, kenar, boyut, hata
  düzeltme, ortada logo (logo varsa hata düzeltme H). Logo sunucuda en çok
  512 px PNG'ye yeniden kodlanır (EXIF ve gömülü içerik atılır).
* Toplu CSV ayrıştırma ve pasif/bulunamadı sayfasının 7 dilli HTML'i.
"""

import base64
import binascii
import csv
import html
import io
import json
import os
import re
import secrets
import string
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import segno
from segno import helpers as segno_yardimci

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
KOD_UZUNLUGU = 7
#: Karışabilen karakterler yok: 0/O/o, 1/l/I (56 karakter → 56^7 ≈ 1,7 trilyon).
KOD_ALFABESI = "".join(c for c in string.ascii_letters + string.digits if c not in "0Oo1lI")
KOD_DESENI = re.compile(r"^[A-Za-z0-9-]{3,40}$")
TAKMA_AD_DESENI = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
AYRILMIS_ADLAR = frozenset({
    "admin", "api", "app", "q", "qr", "www", "login", "logout", "giris", "cikis", "client", "panel",
    "yonetici", "yonetim", "musteri", "static", "assets", "favicon", "robots", "sitemap", "null",
    "undefined", "test", "help", "yardim", "destek", "support", "blog", "kaynaklar", "mehmetkuru",
    "mehmetkurudev", "iletisim", "contact", "index", "home", "ana-sayfa", "link", "kisa-link",
    "odeme", "pay", "fatura", "teklif", "sozlesme", "form", "islem", "hesap", "hesap-davet",
    "durum", "status", "health", "abuse", "sikayet", "report", "guvenlik", "security",
})

TURLER: Tuple[str, ...] = (
    "url", "google_yorum", "whatsapp", "telefon", "eposta", "sms", "konum",
    "vcard", "etkinlik", "uygulama", "wifi", "metin",
)
#: Veriyi doğrudan kodlayan (yönlendirmesiz) türler.
STATIK_TURLER = frozenset({"wifi", "metin"})
#: `/q/<kod>` dosya döndüren türler.
DOSYA_TURLERI = frozenset({"vcard", "etkinlik"})
IZINLI_SEMALAR = frozenset({"http", "https", "tel", "mailto", "sms"})
HEDEF_SINIRI = 2048

HATA_DUZEYLERI = ("L", "M", "Q", "H")
VARSAYILAN_TASARIM: Dict[str, Any] = {
    "on_renk": "#000000",
    "arka_renk": "#ffffff",
    "kenar": 4,
    "boyut": 512,
    "hata_duzeltme": "M",
}
BOYUT_EN_AZ, BOYUT_EN_COK = 128, 2048
KENAR_EN_COK = 10
LOGO_EN_COK_BAYT = 512 * 1024
LOGO_KENAR = 512
#: Logo, sembolün (kenar boşluğu hariç) genişliğinin bu oranı kadar (H düzeyi
#: %30'a kadar hasarı onarır; %22 kenar ≈ alanın %5'i).
LOGO_ORANI = 0.22

CSV_EN_COK_BAYT = 512 * 1024
CSV_EN_COK_SATIR = 500

#: Tür → alan → (en çok uzunluk | "bool"). Bilinmeyen alanlar yok sayılır.
ALANLAR: Dict[str, Dict[str, Any]] = {
    "url": {"url": 2000, "utm_source": 100, "utm_medium": 100, "utm_campaign": 100},
    "google_yorum": {"place_id": 512},
    "whatsapp": {"numara": 32, "mesaj": 1000},
    "telefon": {"numara": 32},
    "eposta": {"eposta": 254, "konu": 200, "govde": 1000},
    "sms": {"numara": 32, "mesaj": 500},
    "konum": {"enlem": 32, "boylam": 32, "adres": 300},
    "vcard": {
        "ad": 80, "soyad": 80, "kurum": 120, "unvan": 120, "telefon_cep": 32, "telefon_is": 32,
        "eposta": 254, "web": 500, "adres_sokak": 200, "adres_sehir": 100, "adres_posta_kodu": 20,
        "adres_ulke": 100, "not": 500,
    },
    "etkinlik": {
        "baslik": 200, "baslangic": 16, "bitis": 16, "tum_gun": "bool", "konum": 300,
        "aciklama": 1000, "saat_dilimi": 64,
    },
    "uygulama": {"ios": 2000, "android": 2000, "diger": 2000},
    "wifi": {"ssid": 32, "sifre": 63, "guvenlik": 8, "gizli": "bool"},
    "metin": {"metin": 900},
}
#: Çok satırlı olabilecek alanlar (satır sonu korunur).
COK_SATIRLI = frozenset({"mesaj", "govde", "aciklama", "not", "metin"})
#: CSV `hedef` sütununun türdeki karşılığı.
ANA_ALAN: Dict[str, str] = {
    "url": "url", "google_yorum": "place_id", "whatsapp": "numara", "telefon": "numara",
    "eposta": "eposta", "sms": "numara", "konum": "adres", "vcard": "web", "etkinlik": "baslik",
    "uygulama": "diger", "wifi": "ssid", "metin": "metin",
}
VARSAYILAN_SAAT_DILIMI = "Europe/Istanbul"


class QrHatasi(Exception):
    """Doğrulama/iş kuralı hatası: `{"kod", "alan"?}` gövdesiyle döner."""

    def __init__(self, kod: str, alan: Optional[str] = None, durum: int = 400, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.alan = alan
        self.durum = durum
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"kod": self.kod}
        if self.alan:
            d["alan"] = self.alan
        d.update(self.ek)
        return d


def site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


def kisa_adres(kod: str) -> str:
    return f"{site_adresi()}/q/{kod}"


# ---------------------------------------------------------------------------
# Kod ve takma ad
# ---------------------------------------------------------------------------
def kod_uret() -> str:
    return "".join(secrets.choice(KOD_ALFABESI) for _ in range(KOD_UZUNLUGU))


def takma_ad_duzelt(ham: Any) -> Optional[str]:
    """Boş → None; geçersiz/ayrılmış → QrHatasi."""
    if ham is None:
        return None
    if not isinstance(ham, str):
        raise QrHatasi("takma_ad_gecersiz", "takma_ad")
    deger = ham.strip().lower()
    if not deger:
        return None
    if not TAKMA_AD_DESENI.match(deger) or "--" in deger:
        raise QrHatasi("takma_ad_gecersiz", "takma_ad")
    if deger in AYRILMIS_ADLAR:
        raise QrHatasi("takma_ad_ayrilmis", "takma_ad")
    return deger


# ---------------------------------------------------------------------------
# Alan yardımcıları
# ---------------------------------------------------------------------------
_KONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TELEFON = re.compile(r"^\+[1-9][0-9]{6,14}$")
_GEVSEK_TELEFON = re.compile(r"^\+?[0-9][0-9 ()\-.]{3,30}$")
_EPOSTA = re.compile(r"^[^@\s<>\"'(),;:\\]{1,64}@[^@\s<>\"'(),;:\\]{1,253}\.[^@\s<>\"'(),;:\\.]{2,63}$")
_PLACE_ID = re.compile(r"^[A-Za-z0-9_-]{10,512}$")
_RENK = re.compile(r"^#[0-9a-fA-F]{6}$")
_ONDALIK = re.compile(r"^-?\d{1,3}(?:\.\d{1,10})?$")


def _metin(girdi: Dict[str, Any], ad: str, sinir: int, zorunlu: bool = False) -> str:
    ham = girdi.get(ad)
    if ham is None or isinstance(ham, (dict, list)):
        deger = ""
    elif isinstance(ham, bool):
        deger = ""
    else:
        deger = str(ham)
    deger = _KONTROL.sub("", deger.replace("\r\n", "\n").replace("\r", "\n"))
    if ad not in COK_SATIRLI:
        deger = " ".join(deger.split())
    deger = deger.strip()
    if len(deger) > sinir:
        raise QrHatasi("cok_uzun", ad, sinir=sinir)
    if zorunlu and not deger:
        raise QrHatasi("zorunlu", ad)
    return deger


def _bool(girdi: Dict[str, Any], ad: str) -> bool:
    ham = girdi.get(ad)
    if isinstance(ham, bool):
        return ham
    if isinstance(ham, (int, float)):
        return bool(ham)
    if isinstance(ham, str):
        return ham.strip().lower() in ("1", "true", "evet", "yes", "on", "e", "x")
    return False


def telefon_duzelt(ham: str, alan: str, zorunlu: bool = True) -> str:
    """E.164 (`+905551112233`). Boşluk, tire, nokta, parantez atılır; `00` → `+`."""
    deger = re.sub(r"[\s\-().]", "", ham or "")
    if not deger:
        if zorunlu:
            raise QrHatasi("zorunlu", alan)
        return ""
    if deger.startswith("00"):
        deger = "+" + deger[2:]
    if not _TELEFON.match(deger):
        raise QrHatasi("telefon_gecersiz", alan)
    return deger


def eposta_dogru_mu(deger: str) -> bool:
    return bool(_EPOSTA.match(deger or ""))


def _web_adresi(ham: str, alan: str, zorunlu: bool = True) -> str:
    """http(s) adresi; şema yoksa https eklenir. Başka şema kesin ret."""
    deger = (ham or "").strip().replace(" ", "%20")
    if not deger:
        if zorunlu:
            raise QrHatasi("zorunlu", alan)
        return ""
    if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", deger):
        deger = "https://" + deger.lstrip("/")
    elif re.match(r"^[A-Za-z0-9.-]+:\d+(/|$)", deger):
        # "ornek.com:8080/yol" şema sanılmasın.
        deger = "https://" + deger
    try:
        parca = urlsplit(deger)
    except ValueError as exc:
        raise QrHatasi("url_gecersiz", alan) from exc
    if parca.scheme.lower() not in ("http", "https"):
        raise QrHatasi("sema_izinsiz", alan)
    if not guvenli_hedef_mi(deger) or "." not in (parca.hostname or ""):
        raise QrHatasi("url_gecersiz", alan)
    host = (parca.hostname or "").lower()
    site_host = (urlsplit(site_adresi()).hostname or "").lower()
    yol = parca.path or ""
    if host in (site_host, "mehmetkuru.dev", "www.mehmetkuru.dev") and (
        yol.startswith("/q/") or yol.startswith("/api/v1/q/")
    ):
        raise QrHatasi("dongu", alan)
    deger = ascii_adres(deger)
    if not guvenli_hedef_mi(deger):
        raise QrHatasi("url_gecersiz", alan)
    return deger


def ascii_adres(adres: str) -> str:
    """Türkçe alan adı / yol → IDNA + yüzde kodlama (Location başlığı ASCII olmalı)."""
    parca = urlsplit(adres)
    host = parca.hostname or ""
    try:
        host_ascii = host.encode("idna").decode("ascii") if not host.isascii() else host
    except UnicodeError as exc:
        raise QrHatasi("url_gecersiz", "url") from exc
    netloc = host_ascii
    if ":" in host_ascii:  # IPv6
        netloc = f"[{host_ascii}]"
    if parca.port:
        netloc += f":{parca.port}"
    korunan = "/%:@!$&'()*+,;=~-._"
    return urlunsplit((
        parca.scheme.lower(),
        netloc,
        quote(parca.path, safe=korunan),
        quote(parca.query, safe=korunan + "?/"),
        quote(parca.fragment, safe=korunan + "?/#"),
    ))


def guvenli_hedef_mi(adres: Any) -> bool:
    """Yönlendirilecek adres beyaz listede mi? (http, https, tel, mailto, sms)."""
    if not isinstance(adres, str) or not adres or len(adres) > HEDEF_SINIRI:
        return False
    if any(ord(c) <= 0x20 or ord(c) == 0x7F for c in adres):
        return False
    try:
        parca = urlsplit(adres)
    except ValueError:
        return False
    sema = (parca.scheme or "").lower()
    if sema not in IZINLI_SEMALAR:
        return False
    if sema in ("http", "https"):
        try:
            if not parca.hostname or parca.username or parca.password or parca.port == 0:
                return False
        except ValueError:
            return False
        return parca.netloc != "" and "\\" not in parca.netloc
    if sema in ("tel", "sms"):
        return bool(re.match(r"^\+?[0-9]{3,20}$", parca.path or ""))
    if sema == "mailto":
        return "@" in (parca.path or "")
    return False


def _utm_ekle(adres: str, alanlar: Dict[str, str]) -> str:
    ek = [(k, alanlar[k]) for k in ("utm_source", "utm_medium", "utm_campaign") if alanlar.get(k)]
    if not ek:
        return adres
    parca = urlsplit(adres)
    sorgu = [(k, v) for k, v in parse_qsl(parca.query, keep_blank_values=True) if k not in dict(ek)]
    sorgu.extend(ek)
    return urlunsplit((parca.scheme, parca.netloc, parca.path, urlencode(sorgu), parca.fragment))


def _tarih_saat(ham: str, alan: str, tum_gun: bool) -> Tuple[Optional[date], Optional[datetime]]:
    """`YYYY-MM-DD` (tüm gün) ya da `YYYY-MM-DDTHH:MM` (yerel saat)."""
    deger = (ham or "").strip().replace(" ", "T")
    if not deger:
        return None, None
    try:
        if tum_gun:
            return date.fromisoformat(deger[:10]), None
        if len(deger) == 10:
            return None, datetime.fromisoformat(deger + "T00:00")
        return None, datetime.fromisoformat(deger[:16])
    except ValueError as exc:
        raise QrHatasi("tarih_gecersiz", alan) from exc


def saat_dilimi(ad: str):
    """IANA saat dilimi; sistemde tz verisi yoksa İstanbul için sabit +03:00."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(ad)
    except Exception:  # noqa: BLE001
        if ad == VARSAYILAN_SAAT_DILIMI:
            return timezone(timedelta(hours=3))
        raise QrHatasi("saat_dilimi_gecersiz", "saat_dilimi")


# ---------------------------------------------------------------------------
# Tür doğrulaması
# ---------------------------------------------------------------------------
def dogrula(tur: Any, ham: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """(temiz alanlar, wifi parolası). Geçersizse QrHatasi."""
    if tur not in TURLER:
        raise QrHatasi("tur_gecersiz", "tur")
    girdi = ham if isinstance(ham, dict) else {}
    tanim = ALANLAR[tur]
    a: Dict[str, Any] = {}
    for ad, sinir in tanim.items():
        if sinir == "bool":
            a[ad] = _bool(girdi, ad)
        else:
            a[ad] = _metin(girdi, ad, sinir)
    sifre: Optional[str] = None

    if tur == "url":
        a["url"] = _web_adresi(a["url"], "url")
    elif tur == "google_yorum":
        if not a["place_id"]:
            raise QrHatasi("zorunlu", "place_id")
        if not _PLACE_ID.match(a["place_id"]):
            raise QrHatasi("place_id_gecersiz", "place_id")
    elif tur in ("whatsapp", "telefon", "sms"):
        a["numara"] = telefon_duzelt(a["numara"], "numara")
    elif tur == "eposta":
        if not a["eposta"]:
            raise QrHatasi("zorunlu", "eposta")
        if not eposta_dogru_mu(a["eposta"]):
            raise QrHatasi("eposta_gecersiz", "eposta")
    elif tur == "konum":
        if a["enlem"] or a["boylam"]:
            for ad, sinir in (("enlem", 90), ("boylam", 180)):
                d = a[ad].replace(",", ".")
                if not _ONDALIK.match(d) or abs(float(d)) > sinir:
                    raise QrHatasi("koordinat_gecersiz", ad)
                a[ad] = d
        elif not a["adres"]:
            raise QrHatasi("konum_gerekli", "adres")
    elif tur == "vcard":
        if not (a["ad"] or a["soyad"] or a["kurum"]):
            raise QrHatasi("zorunlu", "ad")
        for ad in ("telefon_cep", "telefon_is"):
            if a[ad] and not _GEVSEK_TELEFON.match(a[ad]):
                raise QrHatasi("telefon_gecersiz", ad)
        if a["eposta"] and not eposta_dogru_mu(a["eposta"]):
            raise QrHatasi("eposta_gecersiz", "eposta")
        a["web"] = _web_adresi(a["web"], "web", zorunlu=False)
    elif tur == "etkinlik":
        if not a["baslik"]:
            raise QrHatasi("zorunlu", "baslik")
        a["saat_dilimi"] = a["saat_dilimi"] or VARSAYILAN_SAAT_DILIMI
        saat_dilimi(a["saat_dilimi"])
        bas_gun, bas = _tarih_saat(a["baslangic"], "baslangic", a["tum_gun"])
        if bas_gun is None and bas is None:
            raise QrHatasi("zorunlu", "baslangic")
        bit_gun, bit = _tarih_saat(a["bitis"], "bitis", a["tum_gun"])
        if (bit_gun and bas_gun and bit_gun < bas_gun) or (bit and bas and bit < bas):
            raise QrHatasi("bitis_once", "bitis")
        a["baslangic"] = (bas_gun.isoformat() if bas_gun else bas.isoformat(timespec="minutes"))  # type: ignore[union-attr]
        a["bitis"] = (bit_gun.isoformat() if bit_gun else bit.isoformat(timespec="minutes") if bit else "")
    elif tur == "uygulama":
        for ad in ("ios", "android", "diger"):
            a[ad] = _web_adresi(a[ad], ad, zorunlu=False)
        if not (a["ios"] or a["android"] or a["diger"]):
            raise QrHatasi("zorunlu", "diger")
    elif tur == "wifi":
        if not a["ssid"]:
            raise QrHatasi("zorunlu", "ssid")
        guvenlik = (a["guvenlik"] or "WPA").upper()
        if guvenlik in ("YOK", "NONE", "ACIK"):
            guvenlik = "nopass"
        if guvenlik not in ("WPA", "WEP", "NOPASS"):
            raise QrHatasi("guvenlik_gecersiz", "guvenlik")
        a["guvenlik"] = "nopass" if guvenlik == "NOPASS" else guvenlik
        sifre = str(girdi.get("sifre") or "")
        if _KONTROL.search(sifre) or len(sifre) > 63:
            raise QrHatasi("sifre_gecersiz", "sifre")
        if a["guvenlik"] == "nopass":
            sifre = ""
        elif a["guvenlik"] == "WPA" and not (8 <= len(sifre) <= 63):
            raise QrHatasi("sifre_gecersiz", "sifre")
        elif a["guvenlik"] == "WEP" and not sifre:
            raise QrHatasi("zorunlu", "sifre")
        a.pop("sifre", None)
    elif tur == "metin":
        if not a["metin"]:
            raise QrHatasi("zorunlu", "metin")
    return a, sifre


def hedef_uret(tur: str, a: Dict[str, Any]) -> Optional[str]:
    """Yönlendirmeli türün hedefi (beyaz listede); diğer türlerde None."""
    hedef: Optional[str] = None
    if tur == "url":
        hedef = _utm_ekle(a["url"], a)
    elif tur == "google_yorum":
        hedef = "https://search.google.com/local/writereview?placeid=" + quote(a["place_id"], safe="")
    elif tur == "whatsapp":
        hedef = "https://wa.me/" + a["numara"].lstrip("+")
        if a.get("mesaj"):
            hedef += "?text=" + quote(a["mesaj"], safe="")
    elif tur == "telefon":
        hedef = "tel:" + a["numara"]
    elif tur == "sms":
        hedef = "sms:" + a["numara"]
        if a.get("mesaj"):
            hedef += "?body=" + quote(a["mesaj"], safe="")
    elif tur == "eposta":
        hedef = "mailto:" + quote(a["eposta"], safe="@")
        sorgu = [(k, a[v]) for k, v in (("subject", "konu"), ("body", "govde")) if a.get(v)]
        if sorgu:
            hedef += "?" + "&".join(f"{k}={quote(v, safe='')}" for k, v in sorgu)
    elif tur == "konum":
        sorgu = f"{a['enlem']},{a['boylam']}" if a.get("enlem") else a.get("adres", "")
        hedef = "https://www.google.com/maps/search/?api=1&query=" + quote(sorgu, safe=",")
    elif tur == "uygulama":
        hedef = a.get("diger") or a.get("android") or a.get("ios") or None
    if hedef is not None and not guvenli_hedef_mi(hedef):
        raise QrHatasi("hedef_gecersiz", ANA_ALAN.get(tur))
    return hedef


def uygulama_hedefi(a: Dict[str, Any], isletim: str) -> Optional[str]:
    """User-Agent'tan çıkan işletim sistemine göre uygulama mağazası/hedef."""
    if isletim == "ios" and a.get("ios"):
        return a["ios"]
    if isletim == "android" and a.get("android"):
        return a["android"]
    return a.get("diger") or a.get("android") or a.get("ios") or None


def statik_icerik(tur: str, a: Dict[str, Any], sifre: Optional[str]) -> str:
    if tur == "wifi":
        guvenlik = None if a.get("guvenlik") == "nopass" else a.get("guvenlik")
        return segno_yardimci.make_wifi_data(
            ssid=a.get("ssid", ""), password=(sifre or None) if guvenlik else None,
            security=guvenlik, hidden=bool(a.get("gizli")),
        )
    if tur == "metin":
        return a.get("metin", "")
    raise ValueError(tur)


def qr_icerigi(tur: str, kod: str, a: Dict[str, Any], sifre: Optional[str]) -> str:
    """QR'a yazılan veri: dinamikte `/q/<kod>` (değişmez kod), statikte verinin kendisi."""
    if tur in STATIK_TURLER:
        return statik_icerik(tur, a, sifre)
    return kisa_adres(kod)


def ozet_hedef(tur: str, a: Dict[str, Any], hedef: Optional[str]) -> str:
    """Listede gösterilecek kısa hedef açıklaması (parola yok)."""
    if hedef:
        return hedef
    if tur == "vcard":
        return " ".join(x for x in (a.get("ad"), a.get("soyad")) if x) or a.get("kurum", "")
    if tur == "etkinlik":
        return f"{a.get('baslik', '')} · {a.get('baslangic', '')}"
    if tur == "wifi":
        return a.get("ssid", "")
    if tur == "metin":
        m = a.get("metin", "")
        return m if len(m) <= 80 else m[:79] + "…"
    return ""


# ---------------------------------------------------------------------------
# vCard 3.0 ve iCalendar
# ---------------------------------------------------------------------------
def _kacis(deger: str) -> str:
    return (
        (deger or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\n")
        .replace("\n", "\\n")
    )


def _katla(satir: str) -> str:
    """RFC 6350/5545: 75 sekizliği aşan satır CRLF + boşlukla katlanır (UTF-8 bölünmeden)."""
    bayt = satir.encode("utf-8")
    if len(bayt) <= 75:
        return satir
    parcalar: List[str] = []
    gecerli = ""
    sinir = 75
    for c in satir:
        if len((gecerli + c).encode("utf-8")) > sinir:
            parcalar.append(gecerli)
            gecerli = c
            sinir = 74  # devam satırının baştaki boşluğu
        else:
            gecerli += c
    parcalar.append(gecerli)
    return "\r\n ".join(parcalar)


def vcard_uret(a: Dict[str, Any]) -> str:
    ad, soyad = a.get("ad", ""), a.get("soyad", "")
    tam = " ".join(x for x in (ad, soyad) if x) or a.get("kurum", "")
    satirlar = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{_kacis(soyad)};{_kacis(ad)};;;",
        f"FN:{_kacis(tam)}",
    ]
    if a.get("kurum"):
        satirlar.append(f"ORG:{_kacis(a['kurum'])}")
    if a.get("unvan"):
        satirlar.append(f"TITLE:{_kacis(a['unvan'])}")
    if a.get("telefon_cep"):
        satirlar.append(f"TEL;TYPE=CELL:{_kacis(a['telefon_cep'])}")
    if a.get("telefon_is"):
        satirlar.append(f"TEL;TYPE=WORK,VOICE:{_kacis(a['telefon_is'])}")
    if a.get("eposta"):
        satirlar.append(f"EMAIL;TYPE=INTERNET:{_kacis(a['eposta'])}")
    if a.get("web"):
        satirlar.append(f"URL:{a['web']}")
    if any(a.get(k) for k in ("adres_sokak", "adres_sehir", "adres_posta_kodu", "adres_ulke")):
        satirlar.append(
            "ADR;TYPE=WORK:;;{};{};;{};{}".format(
                _kacis(a.get("adres_sokak", "")), _kacis(a.get("adres_sehir", "")),
                _kacis(a.get("adres_posta_kodu", "")), _kacis(a.get("adres_ulke", "")),
            )
        )
    if a.get("not"):
        satirlar.append(f"NOTE:{_kacis(a['not'])}")
    satirlar.append("END:VCARD")
    return "\r\n".join(_katla(s) for s in satirlar) + "\r\n"


def _ics_zaman(deger: str, tz_adi: str) -> str:
    yerel = datetime.fromisoformat(deger).replace(tzinfo=saat_dilimi(tz_adi))
    return yerel.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ics_uret(a: Dict[str, Any], kod: str, an: Optional[datetime] = None) -> str:
    an = an or datetime.now(timezone.utc)
    alan = urlsplit(site_adresi()).hostname or "mehmetkuru.dev"
    satirlar = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//mehmetkuru.dev//Dinamik QR//TR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:qr-{kod}@{alan}",
        "DTSTAMP:" + an.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    ]
    if a.get("tum_gun"):
        bas = date.fromisoformat(a["baslangic"][:10])
        bit = date.fromisoformat(a["bitis"][:10]) if a.get("bitis") else bas
        satirlar.append(f"DTSTART;VALUE=DATE:{bas.strftime('%Y%m%d')}")
        satirlar.append(f"DTEND;VALUE=DATE:{(bit + timedelta(days=1)).strftime('%Y%m%d')}")
    else:
        tz = a.get("saat_dilimi") or VARSAYILAN_SAAT_DILIMI
        satirlar.append("DTSTART:" + _ics_zaman(a["baslangic"], tz))
        if a.get("bitis"):
            satirlar.append("DTEND:" + _ics_zaman(a["bitis"], tz))
        else:
            bit = datetime.fromisoformat(a["baslangic"]) + timedelta(hours=1)
            satirlar.append("DTEND:" + _ics_zaman(bit.isoformat(timespec="minutes"), tz))
    satirlar.append(f"SUMMARY:{_kacis(a.get('baslik', ''))}")
    if a.get("konum"):
        satirlar.append(f"LOCATION:{_kacis(a['konum'])}")
    if a.get("aciklama"):
        satirlar.append(f"DESCRIPTION:{_kacis(a['aciklama'])}")
    satirlar += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_katla(s) for s in satirlar) + "\r\n"


# ---------------------------------------------------------------------------
# User-Agent → cihaz / işletim sistemi / bot
# ---------------------------------------------------------------------------
_BOT = re.compile(
    r"bot\b|bot/|crawl|spider|slurp|facebookexternalhit|facebookcatalog|meta-external|whatsapp|"
    r"telegram|slack|discord|skypeuripreview|linkedin|embedly|iframely|quora link preview|pinterest|"
    r"vkshare|redditbot|applebot|bingpreview|google-inspectiontool|googleother|headlesschrome|"
    r"phantomjs|lighthouse|preview|curl/|wget/|python-requests|python-httpx|python-urllib|aiohttp|"
    r"go-http-client|okhttp/|java/|libwww|httpclient|node-fetch|undici|axios/|scrapy|ahrefs|semrush|"
    r"mj12|dotbot|petalbot|yandex|baiduspider|duckduck|bytespider|gptbot|claudebot|ccbot|perplexity|"
    r"amazonbot|viber|line/|kakaotalk-scrap|snapchat|mastodon|bluesky|cardyb",
    re.IGNORECASE,
)


def bot_mu(ua: Optional[str], basliklar: Optional[Dict[str, str]] = None) -> bool:
    ua = (ua or "").strip()
    if not ua:
        return True
    if _BOT.search(ua):
        return True
    for ad in ("purpose", "sec-purpose", "x-purpose", "x-moz"):
        if "prefetch" in ((basliklar or {}).get(ad) or "").lower():
            return True
    return False


def cihaz_sinifi(ua: Optional[str]) -> str:
    u = (ua or "").lower()
    if not u:
        return "bilinmiyor"
    if re.search(r"ipad|tablet|kindle|silk/|playbook", u) or ("android" in u and "mobile" not in u):
        return "tablet"
    if re.search(r"mobi|iphone|ipod|android|windows phone|blackberry|opera mini", u):
        return "mobil"
    return "masaustu"


def isletim_ailesi(ua: Optional[str]) -> str:
    u = (ua or "").lower()
    if re.search(r"iphone|ipad|ipod", u):
        return "ios"
    if "android" in u:
        return "android"
    if "windows" in u:
        return "windows"
    if "cros" in u:
        return "chromeos"
    if "macintosh" in u or "mac os x" in u:
        return "macos"
    if "linux" in u:
        return "linux"
    return "diger"


def referer_alani(ham: Optional[str]) -> Optional[str]:
    if not ham:
        return None
    try:
        parca = urlsplit(ham.strip())
        if parca.scheme not in ("http", "https"):
            return None
        host = (parca.hostname or "").lower()
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host[:120] or None


def ulke_kodu(ham: Optional[str]) -> Optional[str]:
    deger = (ham or "").strip().upper()
    if re.match(r"^[A-Z]{2}$", deger) and deger != "XX":
        return deger
    return None


# ---------------------------------------------------------------------------
# Tasarım ve görsel
# ---------------------------------------------------------------------------
def tasarim_duzelt(ham: Any) -> Dict[str, Any]:
    girdi = ham if isinstance(ham, dict) else {}
    t = dict(VARSAYILAN_TASARIM)
    for ad in ("on_renk", "arka_renk"):
        if girdi.get(ad) not in (None, ""):
            deger = str(girdi[ad]).strip()
            if not _RENK.match(deger):
                raise QrHatasi("renk_gecersiz", ad)
            t[ad] = deger.lower()
    for ad, alt, ust in (("kenar", 0, KENAR_EN_COK), ("boyut", BOYUT_EN_AZ, BOYUT_EN_COK)):
        if girdi.get(ad) not in (None, ""):
            try:
                deger = int(girdi[ad])
            except (TypeError, ValueError) as exc:
                raise QrHatasi("sayi_gecersiz", ad) from exc
            if not alt <= deger <= ust:
                raise QrHatasi("aralik_disi", ad, en_az=alt, en_cok=ust)
            t[ad] = deger
    if girdi.get("hata_duzeltme") not in (None, ""):
        deger = str(girdi["hata_duzeltme"]).strip().upper()
        if deger not in HATA_DUZEYLERI:
            raise QrHatasi("hata_duzeltme_gecersiz", "hata_duzeltme")
        t["hata_duzeltme"] = deger
    return t


def _parlaklik(renk: str) -> float:
    def kanal(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(renk[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * kanal(r) + 0.7152 * kanal(g) + 0.0722 * kanal(b)


def kontrast_orani(on: str, arka: str) -> float:
    a, b = _parlaklik(on), _parlaklik(arka)
    acik, koyu = max(a, b), min(a, b)
    return round((acik + 0.05) / (koyu + 0.05), 2)


def tasarim_uyarilari(t: Dict[str, Any]) -> List[str]:
    """Okunabilirlik uyarıları (engellemez): düşük kontrast, ters renk, dar kenar."""
    uyarilar: List[str] = []
    if kontrast_orani(t["on_renk"], t["arka_renk"]) < 4.0:
        uyarilar.append("dusuk_kontrast")
    if _parlaklik(t["on_renk"]) > _parlaklik(t["arka_renk"]):
        uyarilar.append("ters_renk")
    if t["kenar"] < 2:
        uyarilar.append("dar_kenar")
    return uyarilar


def logo_hazirla(ham: Any) -> str:
    """Yüklenen PNG/JPG (≤ 512 KB, base64 ya da data: URL) → en çok 512 px PNG (base64).

    Görüntü Pillow ile açılıp yeniden kodlandığı için içinde gömülü başka bir
    şey (EXIF, metin parçası, çokluortam) kalmaz.
    """
    if not isinstance(ham, str) or not ham.strip():
        raise QrHatasi("logo_gecersiz", "logo")
    deger = ham.strip()
    if deger.startswith("data:"):
        baslik, _, deger = deger.partition(",")
        if ";base64" not in baslik or not re.match(r"^data:image/(png|jpe?g);", baslik, re.I):
            raise QrHatasi("logo_turu", "logo")
    if len(deger) > (LOGO_EN_COK_BAYT * 4) // 3 + 8:
        raise QrHatasi("logo_buyuk", "logo", en_cok_kb=LOGO_EN_COK_BAYT // 1024)
    try:
        bayt = base64.b64decode(deger, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise QrHatasi("logo_gecersiz", "logo") from exc
    if len(bayt) > LOGO_EN_COK_BAYT:
        raise QrHatasi("logo_buyuk", "logo", en_cok_kb=LOGO_EN_COK_BAYT // 1024)
    from PIL import Image

    try:
        with Image.open(io.BytesIO(bayt)) as gorsel:
            if gorsel.format not in ("PNG", "JPEG"):
                raise QrHatasi("logo_turu", "logo")
            gen, yuk = gorsel.size
            if gen < 16 or yuk < 16 or gen * yuk > 25_000_000:
                raise QrHatasi("logo_boyutu", "logo")
            gorsel.load()
            rgba = gorsel.convert("RGBA")
    except QrHatasi:
        raise
    except Exception as exc:  # noqa: BLE001 - bozuk dosya
        raise QrHatasi("logo_gecersiz", "logo") from exc
    rgba.thumbnail((LOGO_KENAR, LOGO_KENAR))
    cikti = io.BytesIO()
    rgba.save(cikti, format="PNG", optimize=True)
    return base64.b64encode(cikti.getvalue()).decode("ascii")


def _sembol(icerik: str, t: Dict[str, Any], logo: bool):
    try:
        return segno.make(
            icerik,
            error="h" if logo else t["hata_duzeltme"].lower(),
            micro=False,
            boost_error=not logo,
        )
    except segno.DataOverflowError as exc:
        raise QrHatasi("veri_cok_uzun", None) from exc
    except ValueError as exc:
        raise QrHatasi("veri_gecersiz", None) from exc


@dataclass
class Gorsel:
    veri: bytes
    tur: str
    surum: int
    hata_duzeltme: str
    piksel: int


def svg_ciz(icerik: str, t: Dict[str, Any], logo_b64: Optional[str] = None) -> Gorsel:
    qr = _sembol(icerik, t, bool(logo_b64))
    tampon = io.BytesIO()
    qr.save(
        tampon, kind="svg", scale=1, border=t["kenar"], dark=t["on_renk"], light=t["arka_renk"],
        xmldecl=False, omitsize=True, nl=False, svgclass=None, lineclass=None,
    )
    svg = tampon.getvalue().decode("utf-8")
    genislik = qr.symbol_size(scale=1, border=t["kenar"])[0]
    svg = svg.replace(
        "<svg ",
        f'<svg width="{t["boyut"]}" height="{t["boyut"]}" xmlns:xlink="http://www.w3.org/1999/xlink" ',
        1,
    )
    if logo_b64:
        ic = genislik - 2 * t["kenar"]
        kenar = ic * LOGO_ORANI
        bosluk = max(1.0, kenar * 0.12)
        x = (genislik - kenar) / 2
        kutu = (
            f'<rect x="{x - bosluk:.3f}" y="{x - bosluk:.3f}" width="{kenar + 2 * bosluk:.3f}" '
            f'height="{kenar + 2 * bosluk:.3f}" rx="{bosluk:.3f}" fill="{t["arka_renk"]}"/>'
        )
        resim = (
            f'<image x="{x:.3f}" y="{x:.3f}" width="{kenar:.3f}" height="{kenar:.3f}" '
            f'href="data:image/png;base64,{logo_b64}" xlink:href="data:image/png;base64,{logo_b64}" '
            'preserveAspectRatio="xMidYMid meet"/>'
        )
        svg = svg.replace("</svg>", kutu + resim + "</svg>")
    return Gorsel(svg.encode("utf-8"), "image/svg+xml", qr.version, qr.error, t["boyut"])


def png_ciz(icerik: str, t: Dict[str, Any], logo_b64: Optional[str] = None) -> Gorsel:
    qr = _sembol(icerik, t, bool(logo_b64))
    genislik = qr.symbol_size(scale=1, border=t["kenar"])[0]
    olcek = max(1, round(t["boyut"] / genislik))
    tampon = io.BytesIO()
    qr.save(tampon, kind="png", scale=olcek, border=t["kenar"], dark=t["on_renk"], light=t["arka_renk"])
    veri = tampon.getvalue()
    piksel = genislik * olcek
    if logo_b64:
        from PIL import Image, ImageDraw

        with Image.open(io.BytesIO(veri)) as taban_ham:
            taban = taban_ham.convert("RGBA")
        with Image.open(io.BytesIO(base64.b64decode(logo_b64))) as logo_ham:
            logo = logo_ham.convert("RGBA")
        ic = (genislik - 2 * t["kenar"]) * olcek
        kenar = max(4, int(ic * LOGO_ORANI))
        bosluk = max(olcek, int(kenar * 0.12))
        logo.thumbnail((kenar, kenar), Image.LANCZOS)
        merkez = piksel // 2
        kutu_yari = kenar // 2 + bosluk
        ciz = ImageDraw.Draw(taban)
        ciz.rounded_rectangle(
            (merkez - kutu_yari, merkez - kutu_yari, merkez + kutu_yari, merkez + kutu_yari),
            radius=bosluk, fill=t["arka_renk"],
        )
        taban.alpha_composite(logo, (merkez - logo.width // 2, merkez - logo.height // 2))
        cikti = io.BytesIO()
        taban.convert("RGB").save(cikti, format="PNG", optimize=True)
        veri = cikti.getvalue()
    return Gorsel(veri, "image/png", qr.version, qr.error, piksel)


# ---------------------------------------------------------------------------
# Toplu CSV
# ---------------------------------------------------------------------------
_TUR_ESLEME = {
    "url": "url", "link": "url", "web": "url", "baglanti": "url",
    "kisa_link": "kisa_link", "kisalink": "kisa_link", "short_link": "kisa_link",
    "google_yorum": "google_yorum", "googleyorum": "google_yorum", "google_review": "google_yorum", "yorum": "google_yorum",
    "whatsapp": "whatsapp", "wa": "whatsapp",
    "telefon": "telefon", "tel": "telefon", "phone": "telefon",
    "eposta": "eposta", "e_posta": "eposta", "email": "eposta", "e_mail": "eposta", "mail": "eposta",
    "sms": "sms",
    "konum": "konum", "harita": "konum", "location": "konum",
    "vcard": "vcard", "kartvizit": "vcard",
    "etkinlik": "etkinlik", "event": "etkinlik", "ics": "etkinlik",
    "uygulama": "uygulama", "app": "uygulama",
    "wifi": "wifi", "wi_fi": "wifi",
    "metin": "metin", "text": "metin",
}
_KOORDINAT = re.compile(r"^\s*(-?\d{1,3}(?:[.]\d+)?)\s*[,;]\s*(-?\d{1,3}(?:[.]\d+)?)\s*$")


def _tur_coz(ham: str) -> Tuple[Optional[str], bool]:
    anahtar = re.sub(r"[\s\-]+", "_", (ham or "").strip().lower())
    anahtar = anahtar.translate(str.maketrans("ışğüöçİ", "isguoci"))
    tur = _TUR_ESLEME.get(anahtar)
    if tur == "kisa_link":
        return "url", True
    return tur, False


def csv_coz(bayt: bytes) -> List[Dict[str, str]]:
    """CSV (virgül/noktalı virgül/sekme; UTF-8 ya da Windows-1254) → başlık anahtarlı satırlar."""
    if len(bayt) > CSV_EN_COK_BAYT:
        raise QrHatasi("dosya_buyuk", "dosya", en_cok_kb=CSV_EN_COK_BAYT // 1024, durum=413)
    try:
        metin = bayt.decode("utf-8-sig")
    except UnicodeDecodeError:
        metin = bayt.decode("cp1254", errors="replace")
    if not metin.strip():
        raise QrHatasi("dosya_bos", "dosya")
    ornek = metin[:4096]
    try:
        lehce = csv.Sniffer().sniff(ornek, delimiters=",;\t")
        ayirici = lehce.delimiter
    except csv.Error:
        ayirici = ";" if ornek.count(";") > ornek.count(",") else ","
    okuyucu = csv.reader(io.StringIO(metin), delimiter=ayirici)
    try:
        basliklar = [re.sub(r"\s+", "_", h.strip().lower()) for h in next(okuyucu)]
    except StopIteration as exc:
        raise QrHatasi("dosya_bos", "dosya") from exc
    if "ad" not in basliklar or "tur" not in basliklar:
        raise QrHatasi("baslik_eksik", "dosya", gerekli=["ad", "tur"])
    satirlar: List[Dict[str, str]] = []
    try:
        for satir in okuyucu:
            if not any(h.strip() for h in satir):
                continue
            if len(satirlar) >= CSV_EN_COK_SATIR:
                raise QrHatasi("cok_satir", "dosya", en_cok=CSV_EN_COK_SATIR)
            satirlar.append({basliklar[i]: (satir[i] if i < len(satir) else "") for i in range(len(basliklar))})
    except csv.Error as exc:
        raise QrHatasi("csv_bozuk", "dosya") from exc
    return satirlar


def csv_satiri(ham: Dict[str, str]) -> Dict[str, Any]:
    """CSV satırı → oluşturma girdisi (`ad, tur, alanlar, kisa_link, takma_ad`). Doğrulamaz."""
    tur, kisa = _tur_coz(ham.get("tur", ""))
    alanlar: Dict[str, Any] = {}
    if tur:
        for alan in ALANLAR[tur]:
            if alan == "ad":
                continue
            if ham.get(alan) not in (None, ""):
                alanlar[alan] = ham[alan]
        if tur == "vcard" and ham.get("kisi_ad"):
            alanlar["ad"] = ham["kisi_ad"]
        hedef = (ham.get("hedef") or "").strip()
        if hedef:
            ana = ANA_ALAN[tur]
            eslesme = _KOORDINAT.match(hedef) if tur == "konum" else None
            if eslesme:
                alanlar["enlem"], alanlar["boylam"] = eslesme.group(1), eslesme.group(2)
            elif not alanlar.get(ana):
                alanlar[ana] = hedef
        if tur == "vcard" and not any(alanlar.get(k) for k in ("ad", "soyad", "kurum")):
            alanlar["ad"] = (ham.get("ad") or "").strip()
    kisa_link = kisa or _bool(ham, "kisa_link")
    return {
        "ad": (ham.get("ad") or "").strip(),
        "tur": tur or (ham.get("tur") or "").strip(),
        "alanlar": alanlar,
        "kisa_link": bool(kisa_link and tur == "url"),
        "takma_ad": (ham.get("takma_ad") or "").strip() or None,
    }


def dosya_adi(kod: str, ad: str, uzanti: str) -> str:
    sade = ad.translate(str.maketrans("ışğüöçİŞĞÜÖÇ", "isguocISGUOC"))
    sade = re.sub(r"[^A-Za-z0-9]+", "-", sade).strip("-").lower()[:40]
    return f"qr-{kod}{('-' + sade) if sade else ''}.{uzanti}"


# ---------------------------------------------------------------------------
# Pasif / bulunamadı sayfası (7 dil, noindex)
# ---------------------------------------------------------------------------
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
SAYFA_METINLERI: Dict[str, Dict[str, str]] = {
    "tr": {
        "pasif_baslik": "Bu bağlantı şu an etkin değil",
        "pasif_aciklama": "QR kodun ya da kısa bağlantının sahibi bu bağlantıyı durdurmuş ya da süresi dolmuş olabilir. Daha sonra yeniden deneyin ya da sahibiyle iletişime geçin.",
        "yok_baslik": "Bağlantı bulunamadı",
        "yok_aciklama": "Bu QR kodu ya da kısa bağlantı mevcut değil. Adresi doğru yazdığınızdan emin olun.",
    },
    "en": {
        "pasif_baslik": "This link is not active right now",
        "pasif_aciklama": "The owner of this QR code or short link may have paused it, or it may have expired. Please try again later or contact the owner.",
        "yok_baslik": "Link not found",
        "yok_aciklama": "This QR code or short link does not exist. Please check that the address is correct.",
    },
    "de": {
        "pasif_baslik": "Dieser Link ist derzeit nicht aktiv",
        "pasif_aciklama": "Der Inhaber dieses QR-Codes oder Kurzlinks hat ihn möglicherweise pausiert, oder er ist abgelaufen. Bitte versuchen Sie es später erneut oder wenden Sie sich an den Inhaber.",
        "yok_baslik": "Link nicht gefunden",
        "yok_aciklama": "Dieser QR-Code oder Kurzlink existiert nicht. Bitte prüfen Sie, ob die Adresse korrekt ist.",
    },
    "ru": {
        "pasif_baslik": "Эта ссылка сейчас неактивна",
        "pasif_aciklama": "Владелец этого QR-кода или короткой ссылки мог приостановить её, либо срок её действия истёк. Попробуйте позже или свяжитесь с владельцем.",
        "yok_baslik": "Ссылка не найдена",
        "yok_aciklama": "Такого QR-кода или короткой ссылки не существует. Проверьте правильность адреса.",
    },
    "zh": {
        "pasif_baslik": "此链接当前不可用",
        "pasif_aciklama": "此二维码或短链接的所有者可能已将其暂停，或其已过期。请稍后再试或联系所有者。",
        "yok_baslik": "未找到链接",
        "yok_aciklama": "此二维码或短链接不存在。请确认地址是否正确。",
    },
    "hi": {
        "pasif_baslik": "यह लिंक अभी सक्रिय नहीं है",
        "pasif_aciklama": "इस QR कोड या छोटे लिंक के मालिक ने इसे रोक दिया हो सकता है, या इसकी अवधि समाप्त हो गई है। कृपया बाद में फिर से प्रयास करें या मालिक से संपर्क करें।",
        "yok_baslik": "लिंक नहीं मिला",
        "yok_aciklama": "यह QR कोड या छोटा लिंक मौजूद नहीं है। कृपया जाँचें कि पता सही है।",
    },
    "ar": {
        "pasif_baslik": "هذا الرابط غير نشط حاليًا",
        "pasif_aciklama": "ربما أوقف مالك رمز QR أو الرابط المختصر هذا الرابط مؤقتًا، أو انتهت صلاحيته. يُرجى المحاولة لاحقًا أو التواصل مع المالك.",
        "yok_baslik": "لم يتم العثور على الرابط",
        "yok_aciklama": "رمز QR أو الرابط المختصر هذا غير موجود. يُرجى التأكد من صحة العنوان.",
    },
}


def dil_sec(accept_language: Optional[str]) -> str:
    """Accept-Language (q değerleriyle) → desteklenen ilk dil. Başlık yoksa tr, desteklenmiyorsa en."""
    if not accept_language or not accept_language.strip():
        return "tr"
    adaylar: List[Tuple[float, int, str]] = []
    for sira, parca in enumerate(accept_language.split(",")[:20]):
        ad, _, param = parca.strip().partition(";")
        q = 1.0
        if param.strip().startswith("q="):
            try:
                q = float(param.strip()[2:])
            except ValueError:
                q = 0.0
        if ad:
            adaylar.append((-q, sira, ad.strip().lower()[:2]))
    for _, _, dil in sorted(adaylar):
        if dil in DILLER:
            return dil
    return "en"


def durum_sayfasi(tur: str, dil: str) -> str:
    """`tur`: 'pasif' (410) | 'yok' (404). Satır içi stil; betik yok."""
    m = SAYFA_METINLERI.get(dil) or SAYFA_METINLERI["tr"]
    baslik = html.escape(m[f"{tur}_baslik"])
    aciklama = html.escape(m[f"{tur}_aciklama"])
    yon = "rtl" if dil == "ar" else "ltr"
    site = html.escape(site_adresi())
    return (
        f'<!doctype html><html lang="{dil}" dir="{yon}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex, nofollow">'
        f"<title>{baslik}</title>"
        "<style>"
        ":root{color-scheme:dark}*{box-sizing:border-box}"
        "body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;"
        "padding:24px 16px;background:radial-gradient(ellipse at top,#2a1450 0%,#0b0714 60%);"
        "color:#ece8f5;font:16px/1.6 system-ui,-apple-system,'Segoe UI',Roboto,'Noto Sans',sans-serif}"
        "main{max-width:440px;width:100%;padding:32px 28px;border:1px solid rgba(255,255,255,.12);"
        "border-radius:20px;background:rgba(255,255,255,.04);text-align:center}"
        ".i{width:56px;height:56px;margin:0 auto 18px;border-radius:16px;display:flex;align-items:center;"
        "justify-content:center;background:rgba(168,85,247,.18);font-size:26px}"
        "h1{margin:0 0 10px;font-size:1.3rem;line-height:1.35}p{margin:0 0 22px;color:#b9b2c9}"
        "a{color:#c4a3ff;text-decoration:none;font-weight:600}a:hover{text-decoration:underline}"
        "</style></head><body><main>"
        '<div class="i" aria-hidden="true"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" '
        'stroke="#c4a3ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M9 17H7A5 5 0 0 1 7 7h2M15 7h2a5 5 0 0 1 4 8M8 12h4M3 3l18 18"/></svg></div>'
        f"<h1>{baslik}</h1><p>{aciklama}</p>"
        f'<a href="{site}/" rel="nofollow">mehmetkuru.dev</a>'
        "</main></body></html>"
    )


def json_yukle(ham: Any) -> Dict[str, Any]:
    if not ham:
        return {}
    try:
        d = json.loads(ham)
    except (TypeError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}
