"""Faz 6S — Saha servisi: kurallar, doğrulama, imzalı bağlantılar, görsel ve metinler.

Bu dosya veritabanına dokunmuyor (saf fonksiyonlar); kayıt işleri
`services/saha_kayit.py`, PDF `services/saha_pdf.py`, uçlar `routers/saha_servisi.py`.

Durum akışı
-----------
    yeni → planlandi → yolda → iste → tamamlandi
                  ↘ ertelendi ↗ (yeniden planlanır)      iptal (yeni'ye geri açılabilir)

* `planlandi` için plan başlangıcı ve en az bir teknisyen şart.
* `yolda` / `iste` için en az bir teknisyen şart.
* Teknisyen (yalnız `saha_teknisyen` izni) yalnız kendine atanan işte ve yalnız saha
  geçişlerini yapar: yolda, başla (iste), bitir (tamamlandi), ertele (iste → ertelendi),
  yoldan geri (yolda → planlandi). Planlama / iptal / yeniden açma yönetimde.
* Bitirirken kontrol listesinin zorunlu maddeleri (foto maddesi için fotoğraf) ve
  ayarda istenmişse müşteri imzası şart.

KVKK — konum
------------
Konum YALNIZ "başla" ve "bitir" dokunuşunda, isteği yapan kişi o işe atanmış bir
teknisyense ve geçerli (geri alınmamış, güncel metin sürümüne verilmiş) açık rızası
varsa kaydedilir; başka hiçbir uçta konum alanı yok, sürekli takip yok. Ham koordinat
90 gün sonra silinir (iş emrinin adresi düzeyinde kalır).
"""

import base64
import hashlib
import hmac
import io
import math
import os
import re
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services import qr_menu as menu_kurallari

MODUL = "saha_servisi"
IZIN_YONETIM = "saha_yonetim"
IZIN_TEKNISYEN = "saha_teknisyen"

UTC = timezone.utc

IS_TURLERI: Tuple[str, ...] = ("kurulum", "ariza", "bakim", "temizlik", "kesif")
ONCELIKLER: Tuple[str, ...] = ("dusuk", "normal", "yuksek", "acil")
DURUMLAR: Tuple[str, ...] = ("yeni", "planlandi", "yolda", "iste", "tamamlandi", "iptal", "ertelendi")
ACIK_DURUMLAR: Tuple[str, ...] = ("yeni", "planlandi", "yolda", "iste", "ertelendi")
KAPALI_DURUMLAR: Tuple[str, ...] = ("tamamlandi", "iptal")
GECISLER: Dict[str, Tuple[str, ...]] = {
    "yeni": ("planlandi", "ertelendi", "iptal"),
    "planlandi": ("yeni", "yolda", "iste", "ertelendi", "iptal"),
    "yolda": ("planlandi", "iste", "ertelendi", "iptal"),
    "iste": ("tamamlandi", "ertelendi"),
    "ertelendi": ("yeni", "planlandi", "iptal"),
    "tamamlandi": (),
    "iptal": ("yeni",),
}
#: Yalnız teknisyen izniyle yapılabilen (saha) geçişleri.
TEKNISYEN_GECISLERI = frozenset({
    ("planlandi", "yolda"), ("planlandi", "iste"), ("yolda", "iste"), ("yolda", "planlandi"),
    ("iste", "tamamlandi"), ("iste", "ertelendi"),
})
#: Konum kaydedilebilen geçişler (hedef durum → "başla"/"bitir").
KONUMLU_DURUMLAR: Dict[str, str] = {"iste": "basla", "tamamlandi": "bitir"}

MADDE_TURLERI: Tuple[str, ...] = ("evet_hayir", "metin", "sayi", "olcum", "foto")
BIRIMLER: Tuple[str, ...] = ("adet", "m", "m2", "kg", "lt", "paket", "saat", "takim")
MUSTERI_TURLERI: Tuple[str, ...] = ("bireysel", "kurumsal")
FOTO_TURLERI: Tuple[str, ...] = ("once", "sonra", "madde")
DILLER: Tuple[str, ...] = ("tr", "en", "de", "ru", "zh", "hi", "ar")
PARA_BIRIMLERI: Tuple[str, ...] = ("TRY", "USD", "EUR", "GBP")

VARSAYILAN_TEKNISYEN_SINIRI = 5
VARSAYILAN_AYLIK_SINIR = 300
FOTO_SINIRI = 20
FOTO_EN_COK_BAYT = 12 * 1024 * 1024
FOTO_EN_COK_PIKSEL = 50_000_000
FOTO_BUYUK = 1600
FOTO_KUCUK = 360
IMZA_EN_COK_BAYT = 400 * 1024
IMZA_EN_COK_PIKSEL = (2000, 1000)
MADDE_SINIRI = 60
KONUM_SAKLAMA_GUN = 90
JETON_OMRU_GUN = 60
GORSEL_OMRU_SN = 3600
SAKLAMA_EN_AZ_AY, SAKLAMA_EN_COK_AY = 6, 120
#: Konum rızası metninin sürümü — metin değişirse artırılır, eski rıza geçersizleşir.
RIZA_SURUMU = "2026-10-02"
RIZA_METNI_TR = (
    "Saha servisi uygulamasında yalnız 'İşe başla' ve 'İşi bitir' düğmelerine dokunduğum anda, "
    "tek seferlik konumumun alınmasına ve yalnız ilgili iş emrine eklenmesine açık rıza veriyorum. "
    "Sürekli konum takibi yapılmaz. Ham koordinat 90 gün sonra silinir. Rızamı istediğim an geri "
    "alabilirim; geri alırsam konum alınmaz ve işimi yine yapabilirim."
)


class SahaHatasi(Exception):
    """Doğrulama/iş kuralı hatası: `{"kod", "alan"?, ...}` gövdesiyle döner."""

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


# ---------------------------------------------------------------------------
# Zaman
# ---------------------------------------------------------------------------
def simdi() -> datetime:
    """Testler bu fonksiyonu sabit bir ana çeviriyor."""
    return datetime.now(UTC)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=UTC) if an.tzinfo is None else an.astimezone(UTC)


def iso(an: Any) -> Optional[str]:
    if an is None:
        return None
    if isinstance(an, datetime):
        return utc(an).isoformat().replace("+00:00", "Z")
    if isinstance(an, date):
        return an.isoformat()
    return str(an)


def tr_bugun(an: Optional[datetime] = None) -> date:
    from zoneinfo import ZoneInfo

    return (an or simdi()).astimezone(ZoneInfo("Europe/Istanbul")).date()


def site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


def json_yukle(ham: Any, varsayilan: Any = None) -> Any:
    return menu_kurallari.json_yukle(ham, varsayilan)


def json_yaz(deger: Any) -> str:
    return menu_kurallari.json_yaz(deger)


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------
def metin(ham: Any, alan: str, sinir: int, zorunlu: bool = False, cok_satir: bool = False) -> str:
    try:
        return menu_kurallari.metin(ham, alan, sinir, zorunlu=zorunlu, cok_satir=cok_satir)
    except menu_kurallari.MenuHatasi as h:
        raise SahaHatasi(h.kod, h.alan, h.durum, **h.ek)


def bos_ya_da(ham: Any, alan: str, sinir: int, cok_satir: bool = False) -> Optional[str]:
    return metin(ham, alan, sinir, cok_satir=cok_satir) or None


def secim(ham: Any, alan: str, secenekler: Sequence[str]) -> str:
    deger = str(ham or "").strip().lower()
    if deger not in secenekler:
        raise SahaHatasi("secim_gecersiz", alan)
    return deger


def bool_duzelt(ham: Any, alan: str) -> bool:
    if isinstance(ham, bool):
        return ham
    raise SahaHatasi("bool_gecersiz", alan)


def tam_sayi(ham: Any, alan: str, en_az: int, en_cok: int, bos_olabilir: bool = False) -> Optional[int]:
    if ham is None or ham == "":
        if bos_olabilir:
            return None
        raise SahaHatasi("zorunlu", alan)
    if isinstance(ham, bool):
        raise SahaHatasi("sayi_gecersiz", alan)
    try:
        deger = int(str(ham).strip())
    except (TypeError, ValueError):
        raise SahaHatasi("sayi_gecersiz", alan)
    if deger < en_az or deger > en_cok:
        raise SahaHatasi("aralik_disi", alan, en_az=en_az, en_cok=en_cok)
    return deger


def ondalik(ham: Any, alan: str, en_az: float, en_cok: float, bos_olabilir: bool = False) -> Optional[float]:
    """`12,5` ve `12.5` kabul; NaN/sonsuz yok."""
    if ham is None or ham == "":
        if bos_olabilir:
            return None
        raise SahaHatasi("zorunlu", alan)
    if isinstance(ham, bool):
        raise SahaHatasi("sayi_gecersiz", alan)
    try:
        deger = float(str(ham).strip().replace(",", "."))
    except (TypeError, ValueError):
        raise SahaHatasi("sayi_gecersiz", alan)
    if not math.isfinite(deger):
        raise SahaHatasi("sayi_gecersiz", alan)
    if deger < en_az or deger > en_cok:
        raise SahaHatasi("aralik_disi", alan, en_az=en_az, en_cok=en_cok)
    return round(deger, 3)


def kurus(ham: Any, alan: str) -> int:
    """`1250,50` (TL) → 125050 kuruş. Boş → 0."""
    if ham is None or ham == "":
        return 0
    deger = ondalik(ham, alan, 0, 100_000_000)
    return int(round((deger or 0) * 100))


_EPOSTA = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TELEFON = re.compile(r"^\+?[0-9]{7,15}$")
_RENK = re.compile(r"^#[0-9a-fA-F]{6}$")


def eposta_duzelt(ham: Any, alan: str = "eposta", zorunlu: bool = False) -> Optional[str]:
    deger = str(ham or "").strip().lower()
    if not deger:
        if zorunlu:
            raise SahaHatasi("zorunlu", alan)
        return None
    if len(deger) > 254 or not _EPOSTA.match(deger):
        raise SahaHatasi("eposta_gecersiz", alan)
    return deger


def telefon_duzelt(ham: Any, alan: str = "telefon") -> Optional[str]:
    deger = re.sub(r"[\s\-().]", "", str(ham or ""))
    if not deger:
        return None
    if deger.startswith("00"):
        deger = "+" + deger[2:]
    if not _TELEFON.match(deger):
        raise SahaHatasi("telefon_gecersiz", alan)
    return deger


def renk_duzelt(ham: Any, alan: str = "renk") -> str:
    deger = str(ham or "").strip()
    if not _RENK.match(deger):
        raise SahaHatasi("renk_gecersiz", alan)
    return deger.lower()


def tarih_duzelt(ham: Any, alan: str, bos_olabilir: bool = True) -> Optional[date]:
    if ham is None or ham == "":
        if bos_olabilir:
            return None
        raise SahaHatasi("zorunlu", alan)
    try:
        return date.fromisoformat(str(ham).strip()[:10])
    except ValueError:
        raise SahaHatasi("tarih_gecersiz", alan)


def an_duzelt(ham: Any, alan: str, bos_olabilir: bool = True) -> Optional[datetime]:
    """ISO 8601 (saat dilimli; yoksa UTC sayılır) → UTC."""
    if ham is None or ham == "":
        if bos_olabilir:
            return None
        raise SahaHatasi("zorunlu", alan)
    metin_ = str(ham).strip().replace("Z", "+00:00")
    try:
        an = datetime.fromisoformat(metin_)
    except ValueError:
        raise SahaHatasi("tarih_gecersiz", alan)
    an = utc(an)
    if an.year < 2000 or an.year > 2100:
        raise SahaHatasi("tarih_gecersiz", alan)
    return an.replace(microsecond=0)


def ay_ekle(gun: date, ay: int) -> date:
    toplam = gun.month - 1 + ay
    yil, ay_ = gun.year + toplam // 12, toplam % 12 + 1
    son = [31, 29 if (yil % 4 == 0 and (yil % 100 != 0 or yil % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][ay_ - 1]
    return date(yil, ay_, min(gun.day, son))


def bakim_vadesi(son_bakim: Optional[date], kurulum: Optional[date], periyot_ay: Optional[int]) -> Optional[date]:
    """Son bakım (yoksa kurulum) + periyot. Periyot ya da başlangıç yoksa None."""
    if not periyot_ay:
        return None
    taban = son_bakim or kurulum
    return ay_ekle(taban, int(periyot_ay)) if taban else None


# ---------------------------------------------------------------------------
# Durum akışı
# ---------------------------------------------------------------------------
def gecis_denetle(eski: str, yeni: str, *, yonetim: bool, teknisyen: bool) -> None:
    """Geçersiz geçiş → 409 `gecersiz_gecis`; yetkisiz geçiş → 403 `gecis_yetkisi_yok`."""
    if yeni not in DURUMLAR:
        raise SahaHatasi("secim_gecersiz", "durum")
    if eski == yeni or yeni not in GECISLER.get(eski, ()):
        raise SahaHatasi("gecersiz_gecis", "durum", durum=409, eski=eski, yeni=yeni)
    if yonetim:
        return
    if not teknisyen or (eski, yeni) not in TEKNISYEN_GECISLERI:
        raise SahaHatasi("gecis_yetkisi_yok", "durum", durum=403)


# ---------------------------------------------------------------------------
# Kontrol listesi
# ---------------------------------------------------------------------------
def maddeleri_duzelt(ham: Any) -> List[Dict[str, Any]]:
    if not isinstance(ham, list):
        raise SahaHatasi("liste_gecersiz", "maddeler")
    if len(ham) > MADDE_SINIRI:
        raise SahaHatasi("cok_fazla", "maddeler", sinir=MADDE_SINIRI)
    sonuc: List[Dict[str, Any]] = []
    kimlikler = set()
    for i, m in enumerate(ham):
        if not isinstance(m, dict):
            raise SahaHatasi("liste_gecersiz", "maddeler")
        kimlik = str(m.get("id") or "").strip()[:16]
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,16}", kimlik or "") or kimlik in kimlikler:
            kimlik = f"m{secrets.token_hex(4)}"
        kimlikler.add(kimlik)
        tur = secim(m.get("tur") or "evet_hayir", f"maddeler.{i}.tur", MADDE_TURLERI)
        madde = {
            "id": kimlik,
            "metin": metin(m.get("metin"), f"maddeler.{i}.metin", 200, zorunlu=True),
            "tur": tur,
            "zorunlu": bool(m.get("zorunlu")) if isinstance(m.get("zorunlu"), bool) else False,
        }
        if tur == "olcum":
            madde["birim"] = metin(m.get("birim"), f"maddeler.{i}.birim", 12)
        sonuc.append(madde)
    return sonuc


def yanit_duzelt(madde: Dict[str, Any], ham: Any) -> Any:
    """Tek maddenin yanıtı; None = boşalt. Foto maddesinin yanıtı yok (fotoğraf sayılır)."""
    alan = f"yanitlar.{madde.get('id')}"
    if ham is None or ham == "":
        return None
    tur = madde.get("tur")
    if tur == "evet_hayir":
        return bool_duzelt(ham, alan)
    if tur == "metin":
        return metin(ham, alan, 500, cok_satir=True) or None
    if tur in ("sayi", "olcum"):
        return ondalik(ham, alan, -1_000_000, 1_000_000)
    return None


def yanitlari_birlestir(maddeler: List[Dict[str, Any]], mevcut: Dict[str, Any], gelen: Any) -> Dict[str, Any]:
    if not isinstance(gelen, dict):
        raise SahaHatasi("liste_gecersiz", "yanitlar")
    sozluk = {m["id"]: m for m in maddeler}
    sonuc = {k: v for k, v in (mevcut or {}).items() if k in sozluk}
    for kimlik, deger in gelen.items():
        madde = sozluk.get(str(kimlik))
        if madde is None:
            raise SahaHatasi("madde_yok", "yanitlar", madde=str(kimlik)[:16])
        temiz = yanit_duzelt(madde, deger)
        if temiz is None:
            sonuc.pop(madde["id"], None)
        else:
            sonuc[madde["id"]] = temiz
    return sonuc


def eksik_zorunlular(maddeler: List[Dict[str, Any]], yanitlar: Dict[str, Any], foto_maddeleri: Sequence[str]) -> List[str]:
    eksik: List[str] = []
    fotolu = set(foto_maddeleri)
    for m in maddeler:
        if not m.get("zorunlu"):
            continue
        if m.get("tur") == "foto":
            if m["id"] not in fotolu:
                eksik.append(m["id"])
            continue
        deger = (yanitlar or {}).get(m["id"])
        if deger is None or deger == "":
            eksik.append(m["id"])
    return eksik


def _madde(kimlik: str, metin_: str, tur: str, zorunlu: bool = False, birim: Optional[str] = None) -> Dict[str, Any]:
    d: Dict[str, Any] = {"id": kimlik, "metin": metin_, "tur": tur, "zorunlu": zorunlu}
    if birim:
        d["birim"] = birim
    return d


#: Hazır şablonlar (hesap modülü ilk kullandığında bir kez eklenir; firmanın diliyle).
HAZIR_SABLONLAR: Dict[str, Dict[str, Any]] = {
    "klima_bakimi": {
        "is_turu": "bakim",
        "ad": {"tr": "Klima bakımı", "en": "Air conditioner maintenance"},
        "maddeler": {
            "tr": [
                _madde("filtre", "Filtreler temizlendi", "evet_hayir", True),
                _madde("serpantin", "İç ünite serpantini temizlendi", "evet_hayir", True),
                _madde("dis_unite", "Dış ünite kontrol edildi", "evet_hayir"),
                _madde("gaz", "Gaz basıncı", "olcum", True, "bar"),
                _madde("ufleme", "Üfleme sıcaklığı", "olcum", False, "°C"),
                _madde("drenaj", "Drenaj hattı kontrol edildi", "evet_hayir"),
                _madde("foto", "Bakım sonrası fotoğraf", "foto", True),
                _madde("not", "Müşteriye not", "metin"),
            ],
            "en": [
                _madde("filtre", "Filters cleaned", "evet_hayir", True),
                _madde("serpantin", "Indoor unit coil cleaned", "evet_hayir", True),
                _madde("dis_unite", "Outdoor unit checked", "evet_hayir"),
                _madde("gaz", "Refrigerant pressure", "olcum", True, "bar"),
                _madde("ufleme", "Supply air temperature", "olcum", False, "°C"),
                _madde("drenaj", "Drain line checked", "evet_hayir"),
                _madde("foto", "Photo after maintenance", "foto", True),
                _madde("not", "Note to customer", "metin"),
            ],
        },
    },
    "ofis_temizligi": {
        "is_turu": "temizlik",
        "ad": {"tr": "Ofis temizliği", "en": "Office cleaning"},
        "maddeler": {
            "tr": [
                _madde("yuzey", "Masalar ve yüzeyler silindi", "evet_hayir", True),
                _madde("zemin", "Zeminler süpürüldü ve paspaslandı", "evet_hayir", True),
                _madde("wc", "Tuvalet ve lavabolar dezenfekte edildi", "evet_hayir", True),
                _madde("mutfak", "Mutfak alanı temizlendi", "evet_hayir"),
                _madde("cop", "Çöpler boşaltıldı", "evet_hayir", True),
                _madde("sarf", "Eksik sarf malzemesi", "metin"),
                _madde("foto", "Temizlik sonrası fotoğraf", "foto"),
            ],
            "en": [
                _madde("yuzey", "Desks and surfaces wiped", "evet_hayir", True),
                _madde("zemin", "Floors swept and mopped", "evet_hayir", True),
                _madde("wc", "Toilets and sinks disinfected", "evet_hayir", True),
                _madde("mutfak", "Kitchen area cleaned", "evet_hayir"),
                _madde("cop", "Bins emptied", "evet_hayir", True),
                _madde("sarf", "Missing supplies", "metin"),
                _madde("foto", "Photo after cleaning", "foto"),
            ],
        },
    },
    "kombi_bakimi": {
        "is_turu": None,
        "ad": {"tr": "Kombi bakımı", "en": "Combi boiler maintenance"},
        "maddeler": {
            "tr": [
                _madde("brulor", "Yanma odası ve brülör temizlendi", "evet_hayir", True),
                _madde("co", "Baca gazı ölçümü (CO)", "olcum", True, "ppm"),
                _madde("basinc", "Tesisat basıncı", "olcum", True, "bar"),
                _madde("tank", "Genleşme tankı basıncı", "olcum", False, "bar"),
                _madde("kacak", "Gaz kaçağı kontrolü yapıldı", "evet_hayir", True),
                _madde("filtre", "Filtre temizlendi", "evet_hayir"),
                _madde("foto", "Bakım sonrası fotoğraf", "foto"),
            ],
            "en": [
                _madde("brulor", "Combustion chamber and burner cleaned", "evet_hayir", True),
                _madde("co", "Flue gas measurement (CO)", "olcum", True, "ppm"),
                _madde("basinc", "System pressure", "olcum", True, "bar"),
                _madde("tank", "Expansion vessel pressure", "olcum", False, "bar"),
                _madde("kacak", "Gas leak check done", "evet_hayir", True),
                _madde("filtre", "Filter cleaned", "evet_hayir"),
                _madde("foto", "Photo after maintenance", "foto"),
            ],
        },
    },
}


def hazir_sablon(anahtar: str, dil: str) -> Dict[str, Any]:
    t = HAZIR_SABLONLAR[anahtar]
    d = "tr" if dil == "tr" else "en"
    return {"ad": t["ad"][d], "is_turu": t["is_turu"], "maddeler": [dict(m) for m in t["maddeler"][d]]}


# ---------------------------------------------------------------------------
# Konum (KVKK)
# ---------------------------------------------------------------------------
def konum_duzelt(ham: Any) -> Optional[Tuple[float, float, Optional[float]]]:
    """`{"enlem", "boylam", "dogruluk"?}` → (enlem, boylam, doğruluk). Yoksa None; bozuksa 400."""
    if ham in (None, "", {}):
        return None
    if not isinstance(ham, dict):
        raise SahaHatasi("konum_gecersiz", "konum")

    def sayi(deger: Any, en_az: float, en_cok: float, bos: bool = False) -> Optional[float]:
        if deger is None or deger == "":
            if bos:
                return None
            raise SahaHatasi("konum_gecersiz", "konum")
        if isinstance(deger, bool) or not isinstance(deger, (int, float)):
            raise SahaHatasi("konum_gecersiz", "konum")
        d = float(deger)
        if not math.isfinite(d) or d < en_az or d > en_cok:
            raise SahaHatasi("konum_gecersiz", "konum")
        return d

    enlem = sayi(ham.get("enlem"), -90, 90)
    boylam = sayi(ham.get("boylam"), -180, 180)
    dogruluk = sayi(ham.get("dogruluk"), 0, 100_000, bos=True)
    return round(enlem, 6), round(boylam, 6), (round(dogruluk, 1) if dogruluk is not None else None)


def riza_gecerli_mi(rizasi_at: Optional[datetime], surum: Optional[str], geri_at: Optional[datetime]) -> bool:
    if rizasi_at is None or surum != RIZA_SURUMU:
        return False
    return geri_at is None or utc(geri_at) < utc(rizasi_at)


# ---------------------------------------------------------------------------
# İmzalı bağlantılar (JWT_SECRET_KEY'den türetilen HMAC)
# ---------------------------------------------------------------------------
_YEDEK: Optional[bytes] = None


def _anahtar() -> bytes:
    global _YEDEK
    gizli = os.environ.get("JWT_SECRET_KEY") or ""
    if not gizli:
        if _YEDEK is None:
            _YEDEK = secrets.token_bytes(32)
        return _YEDEK
    return hashlib.sha256(("saha-servisi:" + gizli).encode()).digest()


def _imza(mesaj: str, uzunluk: int = 32) -> str:
    return hmac.new(_anahtar(), mesaj.encode(), hashlib.sha256).hexdigest()[:uzunluk]


def musteri_jetonu(is_emri_id: int, uid: str) -> str:
    """`<id>-<imza>`: iş emrinin kalıcı UID'sine bağlı (başka işte geçersiz)."""
    return f"{int(is_emri_id)}-{_imza(f'servis|{int(is_emri_id)}|{uid}')}"


def jeton_kimligi(jeton: Any) -> Optional[int]:
    parca = str(jeton or "").split("-", 1)
    if len(parca) != 2 or not parca[0].isdigit() or len(parca[1]) != 32:
        return None
    kimlik = int(parca[0])
    return kimlik if kimlik > 0 else None


def musteri_jetonu_gecerli_mi(jeton: Any, is_emri_id: int, uid: str) -> bool:
    return hmac.compare_digest(str(jeton or ""), musteri_jetonu(is_emri_id, uid))


def musteri_adresi(jeton: str) -> str:
    return f"{site_adresi()}/servis/{jeton}"


def gorsel_adresi(anahtar: str, an: Optional[float] = None) -> str:
    """Kısa ömürlü imzalı görsel adresi (oturumsuz <img>; 10 dk'lık dilime yuvarlı → önbellek dostu)."""
    simdi_ = an if an is not None else time.time()
    bitis = int((simdi_ + GORSEL_OMRU_SN) // 600 * 600 + 600)
    return f"/api/v1/saha/gorsel/{anahtar}?b={bitis}&i={_imza(f'gorsel|{anahtar}|{bitis}', 24)}"


def gorsel_imzasi_gecerli_mi(anahtar: str, bitis: Any, imza: Any, an: Optional[float] = None) -> bool:
    try:
        b = int(str(bitis))
    except (TypeError, ValueError):
        return False
    if b < (an if an is not None else time.time()) or b > (an if an is not None else time.time()) + GORSEL_OMRU_SN + 1200:
        return False
    return hmac.compare_digest(str(imza or ""), _imza(f"gorsel|{anahtar}|{b}", 24))


def depo_anahtari(onek: str) -> str:
    return f"saha-{onek}-" + secrets.token_urlsafe(18).replace("-", "x").replace("_", "y")


# ---------------------------------------------------------------------------
# Görsel (fotoğraf: EXIF silinir, WebP) ve imza (PNG)
# ---------------------------------------------------------------------------
def foto_hazirla(bayt: bytes) -> Tuple[bytes, bytes, int, int]:
    """JPEG/PNG/WebP/HEIC dışı → 415. Yön EXIF'e göre düzeltilir, sonra BÜTÜN üst veri
    (EXIF — GPS konumu dahil —, XMP, ICC, yorum) atılır: piksellerden yeni görüntü kurulur.
    Döner: (büyük WebP, küçük WebP, genişlik, yükseklik)."""
    if not bayt:
        raise SahaHatasi("gorsel_gecersiz", "dosya")
    if len(bayt) > FOTO_EN_COK_BAYT:
        raise SahaHatasi("gorsel_buyuk", "dosya", durum=413, en_cok_mb=FOTO_EN_COK_BAYT // (1024 * 1024))
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(bayt)) as ham:
            if ham.format not in ("JPEG", "PNG", "WEBP", "MPO"):
                raise SahaHatasi("gorsel_turu", "dosya", durum=415)
            gen, yuk = ham.size
            if gen < 16 or yuk < 16 or gen * yuk > FOTO_EN_COK_PIKSEL:
                raise SahaHatasi("gorsel_boyutu", "dosya")
            ham.load()
            yonlu = ImageOps.exif_transpose(ham)
            saydam = yonlu.mode in ("RGBA", "LA") or (yonlu.mode == "P" and "transparency" in yonlu.info)
            yonlu = yonlu.convert("RGBA" if saydam else "RGB")
    except SahaHatasi:
        raise
    except Exception as exc:  # noqa: BLE001 - bozuk dosya
        raise SahaHatasi("gorsel_gecersiz", "dosya") from exc

    def kodla(kenar: int, kalite: int) -> Tuple[bytes, int, int]:
        kopya = yonlu.copy()
        kopya.thumbnail((kenar, kenar), Image.LANCZOS)
        # Üst veri taşımayan temiz görüntü: yalnız pikseller.
        temiz = Image.frombytes(kopya.mode, kopya.size, kopya.tobytes())
        cikti = io.BytesIO()
        temiz.save(cikti, format="WEBP", quality=kalite, method=4, exif=b"")
        return cikti.getvalue(), temiz.width, temiz.height

    buyuk, g, y = kodla(FOTO_BUYUK, 80)
    kucuk, _, _ = kodla(FOTO_KUCUK, 70)
    return buyuk, kucuk, g, y


def imza_png_coz(veri: Any) -> bytes:
    """`data:image/png;base64,...` → yeniden kodlanmış PNG. Boş tuval / bozuk → 400."""
    if not isinstance(veri, str) or not veri.strip():
        raise SahaHatasi("imza_gerekli", "png")
    metin_ = veri.strip()
    if metin_.startswith("data:"):
        if not metin_.startswith("data:image/png;base64,"):
            raise SahaHatasi("imza_gecersiz", "png")
        metin_ = metin_.split(",", 1)[1]
    if len(metin_) > IMZA_EN_COK_BAYT * 4 // 3 + 16:
        raise SahaHatasi("imza_buyuk", "png", durum=413)
    try:
        ham = base64.b64decode(metin_, validate=True)
    except (ValueError, base64.binascii.Error):
        raise SahaHatasi("imza_gecersiz", "png")
    if not ham.startswith(b"\x89PNG\r\n\x1a\n") or len(ham) > IMZA_EN_COK_BAYT:
        raise SahaHatasi("imza_gecersiz", "png")
    from PIL import Image

    try:
        with Image.open(io.BytesIO(ham)) as g:
            if g.format != "PNG" or g.width > IMZA_EN_COK_PIKSEL[0] or g.height > IMZA_EN_COK_PIKSEL[1] \
                    or g.width < 20 or g.height < 10:
                raise SahaHatasi("imza_gecersiz", "png")
            g.load()
            temiz = g.convert("RGBA")
    except SahaHatasi:
        raise
    except Exception:  # noqa: BLE001
        raise SahaHatasi("imza_gecersiz", "png")
    # Boş tuval (tamamen saydam ya da düz tek renk) imza sayılmaz.
    alfa = temiz.getchannel("A")
    gri = temiz.convert("L").getextrema()
    if alfa.getbbox() is None or (alfa.getextrema() == (255, 255) and gri[0] == gri[1]):
        raise SahaHatasi("imza_bos", "png")
    cikti = io.BytesIO()
    Image.frombytes(temiz.mode, temiz.size, temiz.tobytes()).save(cikti, format="PNG", optimize=True)
    return cikti.getvalue()


# ---------------------------------------------------------------------------
# Biçim
# ---------------------------------------------------------------------------
def para_yaz(kurus_: int, para_birimi: str = "TRY", dil: str = "tr") -> str:
    from services.pdf_belge import para

    return para((kurus_ or 0) / 100, para_birimi, dil)


def yerel_zaman(an: Optional[datetime], dil: str = "tr") -> str:
    if an is None:
        return "—"
    from zoneinfo import ZoneInfo

    yerel = utc(an).astimezone(ZoneInfo("Europe/Istanbul"))
    return yerel.strftime("%d.%m.%Y %H:%M") if dil == "tr" else yerel.strftime("%Y-%m-%d %H:%M")


def harita_baglantisi(adres: str) -> str:
    from urllib.parse import quote

    return "https://www.google.com/maps/search/?api=1&query=" + quote(adres or "", safe="")


# ---------------------------------------------------------------------------
# Servis müşterisine e-posta (7 dil)
# ---------------------------------------------------------------------------
EPOSTA_METINLERI: Dict[str, Dict[str, str]] = {
    "tr": {
        "planlandi_konu": "{firma}: servis ziyaretiniz planlandı ({no})",
        "yolda_konu": "{firma}: teknisyen yola çıktı ({no})",
        "tamamlandi_konu": "{firma}: servis tamamlandı ({no})",
        "merhaba": "Merhaba {ad},",
        "planlandi_giris": "{firma} servis ziyaretiniz planlandı.",
        "yolda_giris": "{firma} teknisyeni şu anda size doğru yola çıktı.",
        "tamamlandi_giris": "{firma} servis işiniz tamamlandı. Servis formunu indirebilir ve hizmeti değerlendirebilirsiniz.",
        "is": "İş", "zaman": "Zaman", "adres": "Adres", "teknisyen": "Teknisyen",
        "baglanti": "İş durumunu ve servis formunu buradan görebilirsiniz (giriş gerekmez):",
        "kurulum": "Kurulum", "ariza": "Arıza", "bakim": "Bakım", "temizlik": "Temizlik", "kesif": "Keşif",
    },
    "en": {
        "planlandi_konu": "{firma}: your service visit is scheduled ({no})",
        "yolda_konu": "{firma}: the technician is on the way ({no})",
        "tamamlandi_konu": "{firma}: service completed ({no})",
        "merhaba": "Hello {ad},",
        "planlandi_giris": "Your service visit with {firma} has been scheduled.",
        "yolda_giris": "The {firma} technician is now on the way to you.",
        "tamamlandi_giris": "Your service job with {firma} is complete. You can download the service report and rate the service.",
        "is": "Job", "zaman": "Time", "adres": "Address", "teknisyen": "Technician",
        "baglanti": "See the job status and service report here (no login needed):",
        "kurulum": "Installation", "ariza": "Repair", "bakim": "Maintenance", "temizlik": "Cleaning", "kesif": "Site survey",
    },
    "de": {
        "planlandi_konu": "{firma}: Ihr Servicetermin ist geplant ({no})",
        "yolda_konu": "{firma}: Der Techniker ist unterwegs ({no})",
        "tamamlandi_konu": "{firma}: Service abgeschlossen ({no})",
        "merhaba": "Hallo {ad},",
        "planlandi_giris": "Ihr Servicetermin bei {firma} wurde geplant.",
        "yolda_giris": "Der Techniker von {firma} ist jetzt auf dem Weg zu Ihnen.",
        "tamamlandi_giris": "Ihr Serviceauftrag bei {firma} ist abgeschlossen. Sie können den Servicebericht herunterladen und den Service bewerten.",
        "is": "Auftrag", "zaman": "Zeit", "adres": "Adresse", "teknisyen": "Techniker",
        "baglanti": "Auftragsstatus und Servicebericht finden Sie hier (ohne Anmeldung):",
        "kurulum": "Installation", "ariza": "Störung", "bakim": "Wartung", "temizlik": "Reinigung", "kesif": "Vor-Ort-Besichtigung",
    },
    "ru": {
        "planlandi_konu": "{firma}: ваш визит мастера запланирован ({no})",
        "yolda_konu": "{firma}: мастер выехал к вам ({no})",
        "tamamlandi_konu": "{firma}: работы завершены ({no})",
        "merhaba": "Здравствуйте, {ad}!",
        "planlandi_giris": "Визит мастера {firma} запланирован.",
        "yolda_giris": "Мастер {firma} уже едет к вам.",
        "tamamlandi_giris": "Работы {firma} по вашей заявке завершены. Вы можете скачать акт выполненных работ и оценить сервис.",
        "is": "Заявка", "zaman": "Время", "adres": "Адрес", "teknisyen": "Мастер",
        "baglanti": "Статус заявки и акт работ (без входа в систему):",
        "kurulum": "Установка", "ariza": "Ремонт", "bakim": "Обслуживание", "temizlik": "Уборка", "kesif": "Выезд на осмотр",
    },
    "zh": {
        "planlandi_konu": "{firma}：您的上门服务已安排（{no}）",
        "yolda_konu": "{firma}：技师已出发（{no}）",
        "tamamlandi_konu": "{firma}：服务已完成（{no}）",
        "merhaba": "{ad}，您好：",
        "planlandi_giris": "{firma} 已为您安排上门服务。",
        "yolda_giris": "{firma} 的技师正在前往您处。",
        "tamamlandi_giris": "{firma} 的服务工单已完成。您可以下载服务单并为服务评分。",
        "is": "工单", "zaman": "时间", "adres": "地址", "teknisyen": "技师",
        "baglanti": "在此查看工单状态和服务单（无需登录）：",
        "kurulum": "安装", "ariza": "故障维修", "bakim": "保养", "temizlik": "清洁", "kesif": "上门勘察",
    },
    "hi": {
        "planlandi_konu": "{firma}: आपकी सर्विस विज़िट तय हो गई है ({no})",
        "yolda_konu": "{firma}: तकनीशियन रास्ते में है ({no})",
        "tamamlandi_konu": "{firma}: सर्विस पूरी हुई ({no})",
        "merhaba": "नमस्ते {ad},",
        "planlandi_giris": "{firma} के साथ आपकी सर्विस विज़िट तय कर दी गई है।",
        "yolda_giris": "{firma} का तकनीशियन अभी आपकी ओर निकल चुका है।",
        "tamamlandi_giris": "{firma} द्वारा आपका सर्विस कार्य पूरा हो गया है। आप सर्विस रिपोर्ट डाउनलोड कर सकते हैं और सेवा को रेटिंग दे सकते हैं।",
        "is": "कार्य", "zaman": "समय", "adres": "पता", "teknisyen": "तकनीशियन",
        "baglanti": "कार्य की स्थिति और सर्विस रिपोर्ट यहाँ देखें (लॉगिन की ज़रूरत नहीं):",
        "kurulum": "इंस्टॉलेशन", "ariza": "मरम्मत", "bakim": "रखरखाव", "temizlik": "सफ़ाई", "kesif": "साइट निरीक्षण",
    },
    "ar": {
        "planlandi_konu": "{firma}: تم تحديد موعد زيارة الصيانة ({no})",
        "yolda_konu": "{firma}: الفني في الطريق إليك ({no})",
        "tamamlandi_konu": "{firma}: اكتملت الخدمة ({no})",
        "merhaba": "مرحبًا {ad}،",
        "planlandi_giris": "تم تحديد موعد زيارة الخدمة من {firma}.",
        "yolda_giris": "فني {firma} في طريقه إليك الآن.",
        "tamamlandi_giris": "اكتمل طلب الخدمة لدى {firma}. يمكنك تنزيل تقرير الخدمة وتقييمها.",
        "is": "الطلب", "zaman": "الوقت", "adres": "العنوان", "teknisyen": "الفني",
        "baglanti": "اطّلع على حالة الطلب وتقرير الخدمة هنا (دون تسجيل دخول):",
        "kurulum": "تركيب", "ariza": "إصلاح عطل", "bakim": "صيانة", "temizlik": "تنظيف", "kesif": "معاينة",
    },
}


def eposta_metni(tur: str, dil: str, *, firma: str, ad: str, no: str, is_turu: str, zaman: Optional[str],
                 adres: Optional[str], teknisyen: Optional[str], baglanti: str) -> Tuple[str, str]:
    """(konu, gövde). `tur`: planlandi | yolda | tamamlandi."""
    m = EPOSTA_METINLERI.get(dil) or EPOSTA_METINLERI["tr"]
    konu = m[f"{tur}_konu"].format(firma=firma, no=no)
    satirlar = [m["merhaba"].format(ad=ad or ""), "", m[f"{tur}_giris"].format(firma=firma), ""]
    satirlar.append(f"{m['is']}: {no} — {m.get(is_turu, is_turu)}")
    if zaman and tur != "tamamlandi":
        satirlar.append(f"{m['zaman']}: {zaman}")
    if adres:
        satirlar.append(f"{m['adres']}: {adres}")
    if teknisyen:
        satirlar.append(f"{m['teknisyen']}: {teknisyen}")
    satirlar += ["", m["baglanti"], baglanti, "", f"— {firma}"]
    return konu, "\n".join(satirlar)


def ilk_ad(ad: Optional[str]) -> str:
    """Servis müşterisine teknisyenin yalnız adı (soyadı yok)."""
    return (ad or "").strip().split(" ")[0][:40]
