"""Faz 5R — Takvim ve randevu: kurallar ve yardımcılar (veritabanına dokunmayan her şey).

Router `routers/randevu.py`. Burada:

* Doğrulayıcılar: slug, haftalık saatler, istisna aralıkları, soru formu,
  hatırlatmalar, konum, saat dilimi.
* **Müsaitlik hesabı** (`slotlar`): sahibin saat diliminde (varsayılan
  Europe/Istanbul) haftalık aralıklar → istisna / resmî tatil → başlangıç
  adımları → en erken / en geç / tamponlar / günlük sınır / kapasite / mevcut
  randevular. Sonuç UTC anları; ziyaretçinin saat dilimindeki güne göre
  gruplanır (ziyaretçi yaz saatli bir bölgede olabilir — Europe/Berlin,
  America/New_York — Türkiye'de yaz saati yok). Gece yarısını aşan aralık
  (`22:00–02:00`) ertesi güne taşar.
* Çakışma kuralı (kesin): yeni randevu B ile mevcut A çakışır ⇔ B'nin gerçek
  süresi A'nın tamponlu aralığına ya da A'nın gerçek süresi B'nin tamponlu
  aralığına değer. Aynı türde, aynı başlangıçlı grup randevusu çakışma değil;
  kapasiteye sayılır.
* Atama: kişiye özel / sırayla (eşit dağılım: son 90 günde bu türden en az
  randevusu olan, eşitlikte en uzun süredir atanmayan) / ilk müsait (öncelik sırası).
* ICS (RFC 5545): METHOD:REQUEST / CANCEL / PUBLISH, kalıcı UID, SEQUENCE,
  zamanlar UTC (`…Z`) — her takvim uygulaması doğru yerel saate çevirir.
* "Takvime ekle" bağlantıları (Google, Outlook) ve imzalı yönetim jetonu
  (HMAC; randevu kimliği + UID'ye bağlı — başka randevuda geçersiz).
* Ziyaretçi e-postaları 7 dilde (tarih biçimi Babel ile; yoksa ISO).
"""

import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import quote, urlencode

from services import dinamik_qr as qr
from services import qr_menu as menu_kurallari

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
MODUL = "randevu"
IZIN = "randevu"
DILLER: Tuple[str, ...] = ("tr", "en", "de", "ru", "zh", "hi", "ar")
VARSAYILAN_SAAT_DILIMI = "Europe/Istanbul"
KONUM_TURLERI: Tuple[str, ...] = ("jitsi", "baglanti", "telefon", "yuz_yuze")
ATAMA_TURLERI: Tuple[str, ...] = ("kisi", "sirali", "ilk_musait")
TELEFON_SECENEKLERI: Tuple[str, ...] = ("gizli", "istege_bagli", "zorunlu")
SORU_TURLERI: Tuple[str, ...] = ("metin", "uzun", "secim", "onay")
KATILIM: Tuple[str, ...] = ("bilinmiyor", "geldi", "gelmedi")
ADIMLAR: Tuple[int, ...] = (5, 10, 15, 20, 30, 45, 60, 90, 120)
HATIRLATMA_SECENEKLERI: Tuple[int, ...] = (2880, 1440, 240, 120, 60, 30, 15)
VARSAYILAN_HATIRLATMALAR: Tuple[int, ...] = (1440, 60)
EN_COK_HATIRLATMA = 3
EN_COK_SORU = 5
EN_COK_SECENEK = 10
EN_COK_ARALIK = 4
EN_COK_KISI = 20
SURE_EN_AZ, SURE_EN_COK = 15, 240
TAMPON_EN_COK = 240
EN_ERKEN_EN_COK = 60 * 24 * 30  # 30 gün (dakika)
EN_GEC_EN_AZ, EN_GEC_EN_COK = 1, 365
KAPASITE_EN_COK = 200
VARSAYILAN_SAKLAMA_GUN = 180
SAKLAMA_EN_AZ, SAKLAMA_EN_COK = 30, 1095
IPTAL_SINIR_EN_COK = 60 * 24 * 14
#: Bir müsaitlik isteğinde en çok bu kadar gün (ay görünümü 6 hafta).
EN_COK_GUN = 42
#: Sırayla atamada dağılımın sayıldığı pencere.
DAGILIM_GUN = 90
#: Yönetim bağlantısı randevunun bitişinden bu kadar gün sonra da açılır (yalnız görüntüleme).
JETON_OMRU_GUN = 30

VARSAYILAN_HAFTALIK: Dict[str, List[List[str]]] = {
    str(g): [["09:00", "17:00"]] for g in range(5)
}

SLUG_DESENI = menu_kurallari.SLUG_DESENI
#: Herkese açık yolların ve API'nin sabit parçaları — sayfa ya da tür slug'ı olamaz.
AYRILMIS_SLUGLAR = frozenset({
    "admin", "api", "app", "yeni", "new", "edit", "duzenle", "www", "static", "assets", "login", "giris",
    "client", "panel", "yonetici", "musteri", "test", "null", "undefined", "index", "home", "ozet",
    "randevu", "randevular", "yonet", "yonetim", "islem", "besleme", "gorsel", "musaitlik", "rezervasyon",
    "widget", "gomulu", "mehmetkuru", "mehmetkurudev",
})
_RENK = re.compile(r"^#[0-9a-fA-F]{6}$")
_SAAT = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$|^24:00$")
_KONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EPOSTA = re.compile(r"^[^@\s<>,;\"']{1,64}@[^@\s<>,;\"']+\.[^@\s<>,;\"']{2,}$")
UTC = timezone.utc


class RandevuHatasi(Exception):
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


def simdi() -> datetime:
    """Testler bu fonksiyonu sabit bir ana çeviriyor (bütün zaman hesapları buradan)."""
    return datetime.now(UTC)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    """SQLite saat dilimini saklamıyor: okunan naive değer UTC sayılıyor."""
    if an is None:
        return None
    return an.replace(tzinfo=UTC) if an.tzinfo is None else an.astimezone(UTC)


def iso(an: Optional[datetime]) -> Optional[str]:
    a = utc(an)
    return a.isoformat().replace("+00:00", "Z") if a else None


def site_adresi() -> str:
    return qr.site_adresi()


def sayfa_adresi(slug: str, tur: Optional[str] = None) -> str:
    return f"{site_adresi()}/randevu/{slug}" + (f"/{tur}" if tur else "")


def yonetim_adresi(jeton: str) -> str:
    return f"{site_adresi()}/randevu/yonet/{jeton}"


def json_yukle(ham: Any, varsayilan: Any = None) -> Any:
    return menu_kurallari.json_yukle(ham, varsayilan)


def json_yaz(deger: Any) -> str:
    return menu_kurallari.json_yaz(deger)


# ---------------------------------------------------------------------------
# Metin, slug, renk, dil, saat dilimi, e-posta, telefon
# ---------------------------------------------------------------------------
def metin(ham: Any, alan: str, sinir: int, zorunlu: bool = False, cok_satir: bool = False) -> str:
    try:
        return menu_kurallari.metin(ham, alan, sinir, zorunlu=zorunlu, cok_satir=cok_satir)
    except menu_kurallari.MenuHatasi as h:
        raise RandevuHatasi(h.kod, h.alan, h.durum, **h.ek)


def slug_oner(ad: str, yedek: str = "randevu") -> str:
    sade = re.sub(r"[^a-z0-9]+", "-", menu_kurallari._ascii(ad or "").lower()).strip("-")
    sade = re.sub(r"-{2,}", "-", sade)[:40].strip("-")
    if len(sade) < 3 or sade in AYRILMIS_SLUGLAR:
        sade = (sade + "-" + yedek).strip("-") if sade else yedek + "-" + secrets.token_hex(3)
    return sade


def slug_duzelt(ham: Any, alan: str = "slug") -> str:
    if not isinstance(ham, str):
        raise RandevuHatasi("slug_gecersiz", alan)
    deger = ham.strip().lower()
    if not SLUG_DESENI.match(deger) or "--" in deger:
        raise RandevuHatasi("slug_gecersiz", alan)
    if deger in AYRILMIS_SLUGLAR:
        raise RandevuHatasi("slug_ayrilmis", alan)
    return deger


def renk_duzelt(ham: Any, alan: str = "renk") -> str:
    deger = str(ham or "").strip()
    if not _RENK.match(deger):
        raise RandevuHatasi("renk_gecersiz", alan)
    return deger.lower()


def dil_duzelt(ham: Any, alan: str = "dil") -> str:
    deger = str(ham or "").strip().lower()[:2]
    if deger not in DILLER:
        raise RandevuHatasi("dil_gecersiz", alan)
    return deger


def saat_dilimi(ad: str):
    """IANA saat dilimi nesnesi; geçersizse RandevuHatasi."""
    try:
        from zoneinfo import ZoneInfo

        if not isinstance(ad, str) or not ad or len(ad) > 64 or ".." in ad:
            raise ValueError(ad)
        return ZoneInfo(ad)
    except Exception:  # noqa: BLE001
        if ad == VARSAYILAN_SAAT_DILIMI:
            return timezone(timedelta(hours=3))
        raise RandevuHatasi("saat_dilimi_gecersiz", "saat_dilimi")


def saat_dilimi_duzelt(ham: Any, alan: str = "saat_dilimi") -> str:
    deger = str(ham or "").strip()
    try:
        saat_dilimi(deger)
    except RandevuHatasi:
        raise RandevuHatasi("saat_dilimi_gecersiz", alan)
    return deger


def eposta_duzelt(ham: Any, alan: str = "eposta", zorunlu: bool = True) -> str:
    deger = str(ham or "").strip().lower()
    if not deger:
        if zorunlu:
            raise RandevuHatasi("zorunlu", alan)
        return ""
    if len(deger) > 254 or not _EPOSTA.match(deger):
        raise RandevuHatasi("eposta_gecersiz", alan)
    return deger


_TELEFON = re.compile(r"^\+?[0-9]{7,15}$")


def telefon_duzelt(ham: Any, alan: str = "telefon", zorunlu: bool = False) -> Optional[str]:
    """Ziyaretçi dostu: `+90 555 111 22 33`, `0555 111 22 33`, `(212) 555-0100` kabul;
    boşluk/tire/nokta/parantez atılır, `00` → `+`."""
    deger = re.sub(r"[\s\-().]", "", str(ham or ""))
    if not deger:
        if zorunlu:
            raise RandevuHatasi("zorunlu", alan)
        return None
    if deger.startswith("00"):
        deger = "+" + deger[2:]
    if not _TELEFON.match(deger):
        raise RandevuHatasi("telefon_gecersiz", alan)
    return deger


def tam_sayi(ham: Any, alan: str, en_az: int, en_cok: int, bos_olabilir: bool = False) -> Optional[int]:
    if ham is None or ham == "":
        if bos_olabilir:
            return None
        raise RandevuHatasi("zorunlu", alan)
    if isinstance(ham, bool):
        raise RandevuHatasi("sayi_gecersiz", alan)
    try:
        deger = int(str(ham).strip())
    except (TypeError, ValueError):
        raise RandevuHatasi("sayi_gecersiz", alan)
    if deger < en_az or deger > en_cok:
        raise RandevuHatasi("aralik_disi", alan, en_az=en_az, en_cok=en_cok)
    return deger


def bool_duzelt(ham: Any, alan: str) -> bool:
    if isinstance(ham, bool):
        return ham
    raise RandevuHatasi("bool_gecersiz", alan)


# ---------------------------------------------------------------------------
# Haftalık saatler, istisnalar
# ---------------------------------------------------------------------------
def _dk(saat: str) -> int:
    s, d = saat.split(":")
    return int(s) * 60 + int(d)


def araliklar_duzelt(ham: Any, alan: str) -> List[List[str]]:
    """[["09:00","12:00"], ["13:00","18:00"]] — çakışmasız, en çok 4 aralık.

    Bitiş başlangıçtan küçük ya da eşitse aralık gece yarısını aşıyor (ertesi gün
    biter); "24:00" gün sonu. Aynı gündeki aralıklar birbirine değmemeli.
    """
    if ham is None:
        return []
    if not isinstance(ham, list) or len(ham) > EN_COK_ARALIK:
        raise RandevuHatasi("aralik_gecersiz", alan)
    sonuc: List[List[str]] = []
    dakikalar: List[Tuple[int, int]] = []
    for a in ham:
        if not isinstance(a, (list, tuple)) or len(a) != 2 or not all(isinstance(x, str) for x in a):
            raise RandevuHatasi("aralik_gecersiz", alan)
        bas, bit = a[0].strip(), a[1].strip()
        if not _SAAT.match(bas) or not _SAAT.match(bit) or bas == "24:00":
            raise RandevuHatasi("saat_gecersiz", alan)
        b, e = _dk(bas), _dk(bit)
        if e <= b:
            e += 24 * 60  # gece yarısını aşıyor
        if e - b < SURE_EN_AZ or e - b > 24 * 60:
            raise RandevuHatasi("aralik_gecersiz", alan)
        dakikalar.append((b, e))
        sonuc.append([bas, bit])
    sirali = sorted(zip(dakikalar, sonuc))
    for (onceki, _), (sonraki, _) in zip(sirali, sirali[1:]):
        if sonraki[0] < onceki[1]:
            raise RandevuHatasi("aralik_cakisiyor", alan)
    return [s for _, s in sirali]


def haftalik_duzelt(ham: Any, alan: str = "haftalik") -> Dict[str, List[List[str]]]:
    if not isinstance(ham, dict):
        raise RandevuHatasi("haftalik_gecersiz", alan)
    sonuc: Dict[str, List[List[str]]] = {}
    for anahtar, deger in ham.items():
        if str(anahtar) not in {str(i) for i in range(7)}:
            raise RandevuHatasi("haftalik_gecersiz", alan)
        araliklar = araliklar_duzelt(deger, f"{alan}.{anahtar}")
        if araliklar:
            sonuc[str(anahtar)] = araliklar
    return sonuc


def aralik_dakikalari(araliklar: Iterable[Sequence[str]]) -> List[Tuple[int, int]]:
    """Doğrulanmış aralıklar → (başlangıç dk, bitiş dk); bitiş 1440'ı aşabilir."""
    sonuc = []
    for bas, bit in araliklar:
        b, e = _dk(bas), _dk(bit)
        if e <= b:
            e += 24 * 60
        sonuc.append((b, e))
    return sonuc


def tarih_duzelt(ham: Any, alan: str = "tarih") -> date:
    try:
        return date.fromisoformat(str(ham or "")[:10])
    except ValueError:
        raise RandevuHatasi("tarih_gecersiz", alan)


# ---------------------------------------------------------------------------
# Soru formu, hatırlatmalar, konum
# ---------------------------------------------------------------------------
def sorular_duzelt(ham: Any) -> List[Dict[str, Any]]:
    if ham is None:
        return []
    if not isinstance(ham, list) or len(ham) > EN_COK_SORU:
        raise RandevuHatasi("soru_sayisi", "sorular", en_cok=EN_COK_SORU)
    sonuc: List[Dict[str, Any]] = []
    kullanilan: Set[str] = set()
    for i, s in enumerate(ham):
        if not isinstance(s, dict):
            raise RandevuHatasi("soru_gecersiz", f"sorular.{i}")
        kimlik = str(s.get("id") or "").strip()
        if not re.match(r"^[a-z0-9_]{1,20}$", kimlik) or kimlik in kullanilan:
            kimlik = f"s{i + 1}"
            while kimlik in kullanilan:
                kimlik += "x"
        kullanilan.add(kimlik)
        tur = s.get("tur") or "metin"
        if tur not in SORU_TURLERI:
            raise RandevuHatasi("soru_gecersiz", f"sorular.{i}.tur")
        etiket = metin(s.get("etiket"), f"sorular.{i}.etiket", 200, zorunlu=True)
        secenekler: List[str] = []
        if tur == "secim":
            ham_sec = s.get("secenekler")
            if not isinstance(ham_sec, list) or not 2 <= len(ham_sec) <= EN_COK_SECENEK:
                raise RandevuHatasi("secenek_sayisi", f"sorular.{i}.secenekler", en_cok=EN_COK_SECENEK)
            for j, x in enumerate(ham_sec):
                secenekler.append(metin(x, f"sorular.{i}.secenekler.{j}", 80, zorunlu=True))
            if len(set(secenekler)) != len(secenekler):
                raise RandevuHatasi("secenek_tekrar", f"sorular.{i}.secenekler")
        sonuc.append({"id": kimlik, "etiket": etiket, "tur": tur, "zorunlu": bool(s.get("zorunlu")),
                      "secenekler": secenekler})
    return sonuc


def yanitlari_dogrula(sorular: List[Dict[str, Any]], ham: Any) -> Dict[str, Any]:
    ham = ham if isinstance(ham, dict) else {}
    sonuc: Dict[str, Any] = {}
    for s in sorular:
        alan = f"yanitlar.{s['id']}"
        deger = ham.get(s["id"])
        if s["tur"] == "onay":
            secili = deger is True
            if s["zorunlu"] and not secili:
                raise RandevuHatasi("zorunlu", alan)
            sonuc[s["id"]] = secili
            continue
        if s["tur"] == "secim":
            d = str(deger or "").strip()
            if d and d not in s["secenekler"]:
                raise RandevuHatasi("secenek_gecersiz", alan)
            if s["zorunlu"] and not d:
                raise RandevuHatasi("zorunlu", alan)
            if d:
                sonuc[s["id"]] = d
            continue
        d = metin(deger, alan, 2000 if s["tur"] == "uzun" else 300, zorunlu=s["zorunlu"], cok_satir=s["tur"] == "uzun")
        if d:
            sonuc[s["id"]] = d
    return sonuc


def hatirlatmalar_duzelt(ham: Any) -> List[int]:
    if not isinstance(ham, list) or len(ham) > EN_COK_HATIRLATMA:
        raise RandevuHatasi("hatirlatma_gecersiz", "hatirlatmalar", en_cok=EN_COK_HATIRLATMA)
    sonuc = set()
    for x in ham:
        if isinstance(x, bool) or not isinstance(x, int) or x not in HATIRLATMA_SECENEKLERI:
            raise RandevuHatasi("hatirlatma_gecersiz", "hatirlatmalar")
        sonuc.add(x)
    return sorted(sonuc, reverse=True)


def hatirlatmalar(sayfa_ham: Optional[str]) -> List[int]:
    deger = json_yukle(sayfa_ham, None)
    if deger is None:
        return list(VARSAYILAN_HATIRLATMALAR)
    try:
        return hatirlatmalar_duzelt(deger)
    except RandevuHatasi:
        return list(VARSAYILAN_HATIRLATMALAR)


def konum_duzelt(tur: Any, deger: Any) -> Tuple[str, Optional[str]]:
    if tur not in KONUM_TURLERI:
        raise RandevuHatasi("konum_gecersiz", "konum_turu")
    if tur == "jitsi":
        return tur, None
    if tur == "baglanti":
        try:
            adres = qr.web_adresi_duzelt(str(deger or ""), "konum_degeri", True)
        except qr.QrHatasi as h:
            raise RandevuHatasi("zorunlu" if h.kod == "zorunlu" else "baglanti_gecersiz", "konum_degeri")
        if not adres.startswith("https://"):
            raise RandevuHatasi("baglanti_gecersiz", "konum_degeri")
        return tur, adres[:500]
    if tur == "telefon":
        return tur, telefon_duzelt(deger, "konum_degeri") or None
    return tur, metin(deger, "konum_degeri", 300, zorunlu=True, cok_satir=True)


def jitsi_odasi() -> str:
    """Tahmin edilemeyen oda adı (Jitsi'de oda adını bilen katılabilir)."""
    govde = "".join(c for c in secrets.token_urlsafe(18) if c.isalnum())[:16]
    return f"https://meet.jit.si/MK-{govde}"


def adim_varsayilani(sure: int) -> int:
    return sure if sure <= 30 else 30


# ---------------------------------------------------------------------------
# Müsaitlik hesabı
# ---------------------------------------------------------------------------
@dataclass
class KisiTakvimi:
    id: int
    haftalik: Dict[str, List[List[str]]]
    #: tarih → aralıklar ([] = kapalı). Kişiye özel istisna sayfanınkini ezer.
    istisnalar: Dict[date, List[List[str]]] = field(default_factory=dict)


@dataclass
class TurKurali:
    id: int
    sure_dk: int
    adim_dk: int
    tampon_once_dk: int = 0
    tampon_sonra_dk: int = 0
    en_erken_dk: int = 0
    en_gec_gun: int = 60
    gunluk_sinir: Optional[int] = None
    kapasite: int = 1


@dataclass
class Mevcut:
    """Kişinin onaylı bir randevusu (UTC)."""

    id: int
    kisi_id: int
    tur_id: int
    bas: datetime
    bit: datetime
    dolu_bas: datetime
    dolu_bit: datetime


@dataclass
class Slot:
    bas: datetime
    #: kişi kimliği → kalan yer
    kisiler: Dict[int, int]

    @property
    def kalan(self) -> int:
        return max(self.kisiler.values()) if self.kisiler else 0


def tamponlu(bas: datetime, sure: int, once: int, sonra: int) -> Tuple[datetime, datetime, datetime, datetime]:
    bit = bas + timedelta(minutes=sure)
    return bas, bit, bas - timedelta(minutes=once), bit + timedelta(minutes=sonra)


def cakisiyor_mu(a: Mevcut, bas: datetime, bit: datetime, dolu_bas: datetime, dolu_bit: datetime) -> bool:
    """B'nin gerçek süresi A'nın tamponuna ya da A'nın gerçek süresi B'nin tamponuna değiyor mu?"""
    return (bas < a.dolu_bit and bit > a.dolu_bas) or (a.bas < dolu_bit and a.bit > dolu_bas)


def gun_araliklari(gun: date, k: KisiTakvimi, sayfa_istisnalari: Dict[date, List[List[str]]],
                   tatiller: Set[date], yarim_gunler: Set[date], tatilde_kapali: bool) -> List[Tuple[int, int]]:
    """Sahibin yerel gününde (dakika) açık aralıklar. Öncelik: kişi istisnası >
    ekip istisnası > resmî tatil > haftalık saatler."""
    if gun in k.istisnalar:
        return aralik_dakikalari(k.istisnalar[gun])
    if gun in sayfa_istisnalari:
        return aralik_dakikalari(sayfa_istisnalari[gun])
    if tatilde_kapali and gun in tatiller:
        return []
    araliklar = aralik_dakikalari(k.haftalik.get(str(gun.weekday())) or [])
    if tatilde_kapali and gun in yarim_gunler:
        # Arife: yarım gün, 13:00'te biter (destek SLA ile aynı kural).
        araliklar = [(b, min(e, 13 * 60)) for b, e in araliklar if b < 13 * 60]
    return araliklar


def _yerel_an(gun: date, dakika: int, tz) -> datetime:
    return (datetime.combine(gun, time()) + timedelta(minutes=dakika)).replace(tzinfo=tz)


def aday_baslangiclar(k: KisiTakvimi, tur: TurKurali, tz, ilk_gun: date, son_gun: date,
                      sayfa_istisnalari: Dict[date, List[List[str]]], tatiller: Set[date],
                      yarim_gunler: Set[date], tatilde_kapali: bool) -> List[datetime]:
    """Sahibin yerel [ilk_gun, son_gun] günlerindeki aralıklardan başlangıç anları (UTC)."""
    sonuc: Set[datetime] = set()
    gun = ilk_gun
    sure = timedelta(minutes=tur.sure_dk)
    while gun <= son_gun:
        for b, e in gun_araliklari(gun, k, sayfa_istisnalari, tatiller, yarim_gunler, tatilde_kapali):
            bitis = _yerel_an(gun, e, tz).astimezone(UTC)
            dk = b
            while dk < e:
                bas = _yerel_an(gun, dk, tz).astimezone(UTC)
                if bas + sure > bitis:
                    break
                sonuc.add(bas)
                dk += tur.adim_dk
        gun += timedelta(days=1)
    return sorted(sonuc)


def slotlar(
    *,
    tur: TurKurali,
    kisiler: List[KisiTakvimi],
    tz_adi: str,
    aralik_bas: datetime,
    aralik_bit: datetime,
    mevcutlar: List[Mevcut],
    simdi_: datetime,
    sayfa_istisnalari: Optional[Dict[date, List[List[str]]]] = None,
    tatiller: Optional[Set[date]] = None,
    yarim_gunler: Optional[Set[date]] = None,
    tatilde_kapali: bool = False,
    haric_id: Optional[int] = None,
) -> List[Slot]:
    """[aralik_bas, aralik_bit) (UTC) içindeki müsait başlangıçlar; her biri için müsait kişiler."""
    tz = saat_dilimi(tz_adi)
    en_erken = simdi_ + timedelta(minutes=tur.en_erken_dk)
    en_gec = simdi_ + timedelta(days=tur.en_gec_gun)
    alt = max(aralik_bas, en_erken)
    ust = min(aralik_bit, en_gec)
    if alt >= ust:
        return []
    ilk_gun = alt.astimezone(tz).date() - timedelta(days=1)
    son_gun = ust.astimezone(tz).date()
    sayfa_istisnalari = sayfa_istisnalari or {}
    tatiller = tatiller or set()
    yarim_gunler = yarim_gunler or set()
    kisi_mevcut: Dict[int, List[Mevcut]] = {}
    for m in mevcutlar:
        if m.id != haric_id:
            kisi_mevcut.setdefault(m.kisi_id, []).append(m)

    toplam: Dict[datetime, Dict[int, int]] = {}
    for k in kisiler:
        liste = kisi_mevcut.get(k.id, [])
        # Günlük sınır: bu türün o gündeki (sahibin yerel günü) ayrı başlangıç sayısı.
        gunluk: Dict[date, Set[datetime]] = {}
        for m in liste:
            if m.tur_id == tur.id:
                gunluk.setdefault(m.bas.astimezone(tz).date(), set()).add(m.bas)
        for bas in aday_baslangiclar(k, tur, tz, ilk_gun, son_gun, sayfa_istisnalari, tatiller, yarim_gunler,
                                     tatilde_kapali):
            if bas < alt or bas >= ust:
                continue
            b, e, db, de = tamponlu(bas, tur.sure_dk, tur.tampon_once_dk, tur.tampon_sonra_dk)
            dolu = 0
            engel = False
            for m in liste:
                if tur.kapasite > 1 and m.tur_id == tur.id and m.bas == bas:
                    dolu += 1
                    continue
                if cakisiyor_mu(m, b, e, db, de):
                    engel = True
                    break
            if engel or dolu >= tur.kapasite:
                continue
            gun_sayisi = gunluk.get(bas.astimezone(tz).date(), set())
            if tur.gunluk_sinir is not None and bas not in gun_sayisi and len(gun_sayisi) >= tur.gunluk_sinir:
                continue
            toplam.setdefault(bas, {})[k.id] = tur.kapasite - dolu
    return [Slot(bas=b, kisiler=toplam[b]) for b in sorted(toplam)]


def gunlere_bol(slotlar_: List[Slot], tz_adi: str) -> Dict[str, List[Dict[str, Any]]]:
    """Ziyaretçinin saat dilimindeki güne göre (YYYY-AA-GG) gruplar."""
    tz = saat_dilimi(tz_adi)
    sonuc: Dict[str, List[Dict[str, Any]]] = {}
    for s in slotlar_:
        yerel = s.bas.astimezone(tz)
        sonuc.setdefault(yerel.date().isoformat(), []).append({
            "bas": iso(s.bas), "saat": yerel.strftime("%H:%M"), "kalan": s.kalan,
        })
    return sonuc


def ziyaretci_araligi(bas_gun: date, gun_sayisi: int, tz_adi: str) -> Tuple[datetime, datetime]:
    """Ziyaretçinin yerel [bas_gun 00:00, +gun_sayisi gün 00:00) → UTC."""
    tz = saat_dilimi(tz_adi)
    bas = datetime.combine(bas_gun, time()).replace(tzinfo=tz).astimezone(UTC)
    bit = datetime.combine(bas_gun + timedelta(days=gun_sayisi), time()).replace(tzinfo=tz).astimezone(UTC)
    return bas, bit


@dataclass
class DagilimBilgisi:
    #: Son DAGILIM_GUN günde bu türden aldığı onaylı randevu sayısı.
    sayi: int = 0
    son_atama: Optional[datetime] = None


def kisi_sec(atama: str, musait: Iterable[int], oncelik: Sequence[int],
             dagilim: Optional[Dict[int, DagilimBilgisi]] = None) -> Optional[int]:
    """Müsait kişilerden atanacak olan. `oncelik` türün kişi sırası."""
    musait_kume = set(musait)
    sirali = [k for k in oncelik if k in musait_kume] + sorted(musait_kume - set(oncelik))
    if not sirali:
        return None
    if atama in ("kisi", "ilk_musait"):
        return sirali[0]
    dagilim = dagilim or {}
    en_eski = datetime.min.replace(tzinfo=UTC)

    def anahtar(k: int) -> Tuple[int, datetime, int]:
        d = dagilim.get(k) or DagilimBilgisi()
        return d.sayi, utc(d.son_atama) or en_eski, sirali.index(k)

    return min(sirali, key=anahtar)


# ---------------------------------------------------------------------------
# İmzalı yönetim jetonu ve ICS besleme jetonu (HMAC; JWT_SECRET_KEY'den türetilir)
# ---------------------------------------------------------------------------
_YEDEK: Optional[bytes] = None


def _anahtar() -> bytes:
    global _YEDEK
    gizli = os.environ.get("JWT_SECRET_KEY") or ""
    if not gizli:
        if _YEDEK is None:
            _YEDEK = secrets.token_bytes(32)
        return _YEDEK
    return hashlib.sha256(("randevu:" + gizli).encode()).digest()


def _imza(mesaj: str) -> str:
    return hmac.new(_anahtar(), mesaj.encode(), hashlib.sha256).hexdigest()[:32]


def yonetim_jetonu(randevu_id: int, uid: str) -> str:
    """`<id>-<imza>`: imza randevu kimliği + kalıcı UID'ye bağlı (başka randevuda geçersiz)."""
    return f"{int(randevu_id)}-{_imza(f'yonet|{int(randevu_id)}|{uid}')}"


def jeton_kimligi(jeton: Any) -> Optional[int]:
    parca = str(jeton or "").split("-", 1)
    if len(parca) != 2 or not parca[0].isdigit() or len(parca[1]) != 32:
        return None
    kimlik = int(parca[0])
    return kimlik if kimlik > 0 else None


def yonetim_jetonu_gecerli_mi(jeton: Any, randevu_id: int, uid: str) -> bool:
    return hmac.compare_digest(str(jeton or ""), yonetim_jetonu(randevu_id, uid))


def besleme_jetonu(sayfa_id: int, surum: int) -> str:
    return f"{int(sayfa_id)}-{int(surum)}-{_imza(f'besleme|{int(sayfa_id)}|{int(surum)}')}"


def besleme_jetonu_coz(jeton: Any) -> Optional[Tuple[int, int]]:
    parca = str(jeton or "").split("-")
    if len(parca) != 3 or not parca[0].isdigit() or not parca[1].isdigit() or len(parca[2]) != 32:
        return None
    return int(parca[0]), int(parca[1])


def besleme_jetonu_gecerli_mi(jeton: Any, sayfa_id: int, surum: int) -> bool:
    return hmac.compare_digest(str(jeton or ""), besleme_jetonu(sayfa_id, surum))


def besleme_adresi(jeton: str) -> str:
    return f"{site_adresi()}/api/v1/randevu/besleme/{jeton}.ics"


# ---------------------------------------------------------------------------
# ICS (RFC 5545)
# ---------------------------------------------------------------------------
def _ics_an(an: datetime) -> str:
    return utc(an).strftime("%Y%m%dT%H%M%SZ")


def _kacis(deger: str) -> str:
    return qr._kacis(deger or "")


def _katla(satir: str) -> str:
    return qr._katla(satir)


def _cn(ad: str) -> str:
    return '"' + re.sub(r'["\r\n]', "", ad or "")[:100] + '"'


@dataclass
class IcsEtkinligi:
    uid: str
    bas: datetime
    bit: datetime
    baslik: str
    aciklama: str = ""
    konum: str = ""
    adres: str = ""
    sira_no: int = 0
    iptal: bool = False
    duzenleyen_eposta: str = ""
    duzenleyen_ad: str = ""
    katilimci_eposta: str = ""
    katilimci_ad: str = ""


def _etkinlik_satirlari(e: IcsEtkinligi, an: datetime, katilimci: bool) -> List[str]:
    alan = (site_adresi().split("://", 1)[-1].split("/", 1)[0] or "mehmetkuru.dev").split(":", 1)[0]
    satirlar = [
        "BEGIN:VEVENT",
        f"UID:randevu-{e.uid}@{alan}",
        f"SEQUENCE:{int(e.sira_no)}",
        "DTSTAMP:" + _ics_an(an),
        "DTSTART:" + _ics_an(e.bas),
        "DTEND:" + _ics_an(e.bit),
        f"SUMMARY:{_kacis(e.baslik)}",
        "STATUS:" + ("CANCELLED" if e.iptal else "CONFIRMED"),
        "TRANSP:OPAQUE",
    ]
    if e.aciklama:
        satirlar.append(f"DESCRIPTION:{_kacis(e.aciklama)}")
    if e.konum:
        satirlar.append(f"LOCATION:{_kacis(e.konum)}")
    if e.adres:
        satirlar.append(f"URL:{e.adres}")
    if katilimci and e.duzenleyen_eposta:
        satirlar.append(f"ORGANIZER;CN={_cn(e.duzenleyen_ad)}:mailto:{e.duzenleyen_eposta}")
    if katilimci and e.katilimci_eposta:
        satirlar.append(
            f"ATTENDEE;CN={_cn(e.katilimci_ad)};ROLE=REQ-PARTICIPANT;PARTSTAT="
            + ("DECLINED" if e.iptal else "ACCEPTED") + f";RSVP=FALSE:mailto:{e.katilimci_eposta}"
        )
    satirlar.append("END:VEVENT")
    return satirlar


def ics_uret(etkinlikler: List[IcsEtkinligi], yontem: str = "PUBLISH", takvim_adi: Optional[str] = None,
             an: Optional[datetime] = None) -> str:
    """`yontem`: REQUEST (davet), CANCEL (iptal), PUBLISH (indirme / besleme)."""
    if yontem not in ("REQUEST", "CANCEL", "PUBLISH"):
        raise ValueError(yontem)
    an = an or simdi()
    satirlar = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//mehmetkuru.dev//Randevu//TR",
        "CALSCALE:GREGORIAN",
        f"METHOD:{yontem}",
    ]
    if takvim_adi:
        satirlar += [f"X-WR-CALNAME:{_kacis(takvim_adi)}", "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
                     "X-PUBLISHED-TTL:PT1H"]
    for e in etkinlikler:
        satirlar += _etkinlik_satirlari(e, an, katilimci=yontem != "PUBLISH")
    satirlar.append("END:VCALENDAR")
    return "\r\n".join(_katla(s) for s in satirlar) + "\r\n"


def google_takvim_adresi(baslik: str, bas: datetime, bit: datetime, aciklama: str = "", konum: str = "") -> str:
    p = {"action": "TEMPLATE", "text": baslik, "dates": f"{_ics_an(bas)}/{_ics_an(bit)}"}
    if aciklama:
        p["details"] = aciklama[:1500]
    if konum:
        p["location"] = konum
    return "https://calendar.google.com/calendar/render?" + urlencode(p, quote_via=quote)


def outlook_takvim_adresi(baslik: str, bas: datetime, bit: datetime, aciklama: str = "", konum: str = "") -> str:
    p = {
        "path": "/calendar/action/compose", "rru": "addevent", "subject": baslik,
        "startdt": utc(bas).strftime("%Y-%m-%dT%H:%M:%SZ"), "enddt": utc(bit).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if aciklama:
        p["body"] = aciklama[:1500]
    if konum:
        p["location"] = konum
    return "https://outlook.live.com/calendar/0/deeplink/compose?" + urlencode(p, quote_via=quote)


# ---------------------------------------------------------------------------
# Ziyaretçi e-postaları (7 dil)
# ---------------------------------------------------------------------------
METINLER: Dict[str, Dict[str, str]] = {
    "tr": {
        "onay_konu": "Randevunuz onaylandı: {tur} — {zaman}",
        "yeniden_konu": "Randevunuz yeniden planlandı: {tur} — {zaman}",
        "iptal_konu": "Randevunuz iptal edildi: {tur} — {zaman}",
        "hatirlatma_konu": "Hatırlatma: {tur} — {zaman}",
        "merhaba": "Merhaba {ad},",
        "onay_giris": "{sayfa} ile randevunuz onaylandı.",
        "yeniden_giris": "{sayfa} ile randevunuz yeni zamana taşındı.",
        "iptal_giris": "{sayfa} ile randevunuz iptal edildi.",
        "hatirlatma_giris": "{sayfa} ile randevunuz yaklaşıyor.",
        "ne": "Görüşme", "ne_zaman": "Zaman", "sure": "Süre", "nerede": "Konum", "kiminle": "Kiminle",
        "onceki": "Önceki zaman", "neden": "Neden",
        "dk": "{sayi} dk",
        "yonet": "İptal etmek ya da yeniden planlamak için:",
        "takvim": "Takvime ekle:",
        "ics_not": "Takvim dosyası (.ics) bu e-postanın ekinde.",
        "yeni_randevu": "Yeni bir randevu almak için:",
        "jitsi": "Çevrim içi görüşme (Jitsi Meet)", "baglanti": "Çevrim içi görüşme",
        "telefon": "Telefon görüşmesi", "yuz_yuze": "Yüz yüze",
        "biz_arariz": "Sizi {telefon} numarasından arayacağız.", "siz_arayin": "Lütfen {telefon} numarasını arayın.",
        "biz_arariz_bos": "Sizi verdiğiniz numaradan arayacağız.",
    },
    "en": {
        "onay_konu": "Your appointment is confirmed: {tur} — {zaman}",
        "yeniden_konu": "Your appointment has been rescheduled: {tur} — {zaman}",
        "iptal_konu": "Your appointment has been cancelled: {tur} — {zaman}",
        "hatirlatma_konu": "Reminder: {tur} — {zaman}",
        "merhaba": "Hello {ad},",
        "onay_giris": "Your appointment with {sayfa} is confirmed.",
        "yeniden_giris": "Your appointment with {sayfa} has been moved to a new time.",
        "iptal_giris": "Your appointment with {sayfa} has been cancelled.",
        "hatirlatma_giris": "Your appointment with {sayfa} is coming up.",
        "ne": "Meeting", "ne_zaman": "When", "sure": "Duration", "nerede": "Where", "kiminle": "With",
        "onceki": "Previous time", "neden": "Reason",
        "dk": "{sayi} min",
        "yonet": "To cancel or reschedule:",
        "takvim": "Add to calendar:",
        "ics_not": "The calendar file (.ics) is attached to this email.",
        "yeni_randevu": "To book a new appointment:",
        "jitsi": "Online meeting (Jitsi Meet)", "baglanti": "Online meeting",
        "telefon": "Phone call", "yuz_yuze": "In person",
        "biz_arariz": "We will call you at {telefon}.", "siz_arayin": "Please call {telefon}.",
        "biz_arariz_bos": "We will call you at the number you provided.",
    },
    "de": {
        "onay_konu": "Ihr Termin ist bestätigt: {tur} — {zaman}",
        "yeniden_konu": "Ihr Termin wurde verschoben: {tur} — {zaman}",
        "iptal_konu": "Ihr Termin wurde abgesagt: {tur} — {zaman}",
        "hatirlatma_konu": "Erinnerung: {tur} — {zaman}",
        "merhaba": "Hallo {ad},",
        "onay_giris": "Ihr Termin bei {sayfa} ist bestätigt.",
        "yeniden_giris": "Ihr Termin bei {sayfa} wurde auf eine neue Zeit verschoben.",
        "iptal_giris": "Ihr Termin bei {sayfa} wurde abgesagt.",
        "hatirlatma_giris": "Ihr Termin bei {sayfa} steht bald an.",
        "ne": "Termin", "ne_zaman": "Zeit", "sure": "Dauer", "nerede": "Ort", "kiminle": "Mit",
        "onceki": "Bisherige Zeit", "neden": "Grund",
        "dk": "{sayi} Min.",
        "yonet": "Zum Absagen oder Verschieben:",
        "takvim": "Zum Kalender hinzufügen:",
        "ics_not": "Die Kalenderdatei (.ics) ist dieser E-Mail angehängt.",
        "yeni_randevu": "Für einen neuen Termin:",
        "jitsi": "Online-Meeting (Jitsi Meet)", "baglanti": "Online-Meeting",
        "telefon": "Telefonat", "yuz_yuze": "Vor Ort",
        "biz_arariz": "Wir rufen Sie unter {telefon} an.", "siz_arayin": "Bitte rufen Sie {telefon} an.",
        "biz_arariz_bos": "Wir rufen Sie unter der angegebenen Nummer an.",
    },
    "ru": {
        "onay_konu": "Ваша встреча подтверждена: {tur} — {zaman}",
        "yeniden_konu": "Ваша встреча перенесена: {tur} — {zaman}",
        "iptal_konu": "Ваша встреча отменена: {tur} — {zaman}",
        "hatirlatma_konu": "Напоминание: {tur} — {zaman}",
        "merhaba": "Здравствуйте, {ad}!",
        "onay_giris": "Ваша встреча с {sayfa} подтверждена.",
        "yeniden_giris": "Ваша встреча с {sayfa} перенесена на новое время.",
        "iptal_giris": "Ваша встреча с {sayfa} отменена.",
        "hatirlatma_giris": "Скоро ваша встреча с {sayfa}.",
        "ne": "Встреча", "ne_zaman": "Время", "sure": "Длительность", "nerede": "Место", "kiminle": "С кем",
        "onceki": "Прежнее время", "neden": "Причина",
        "dk": "{sayi} мин",
        "yonet": "Чтобы отменить или перенести:",
        "takvim": "Добавить в календарь:",
        "ics_not": "Файл календаря (.ics) приложен к этому письму.",
        "yeni_randevu": "Чтобы записаться снова:",
        "jitsi": "Онлайн-встреча (Jitsi Meet)", "baglanti": "Онлайн-встреча",
        "telefon": "Телефонный звонок", "yuz_yuze": "Лично",
        "biz_arariz": "Мы позвоним вам по номеру {telefon}.", "siz_arayin": "Пожалуйста, позвоните по номеру {telefon}.",
        "biz_arariz_bos": "Мы позвоним вам по указанному номеру.",
    },
    "zh": {
        "onay_konu": "您的预约已确认：{tur} — {zaman}",
        "yeniden_konu": "您的预约已改期：{tur} — {zaman}",
        "iptal_konu": "您的预约已取消：{tur} — {zaman}",
        "hatirlatma_konu": "提醒：{tur} — {zaman}",
        "merhaba": "{ad}，您好：",
        "onay_giris": "您与 {sayfa} 的预约已确认。",
        "yeniden_giris": "您与 {sayfa} 的预约已改到新的时间。",
        "iptal_giris": "您与 {sayfa} 的预约已取消。",
        "hatirlatma_giris": "您与 {sayfa} 的预约即将开始。",
        "ne": "会面", "ne_zaman": "时间", "sure": "时长", "nerede": "地点", "kiminle": "与谁",
        "onceki": "原定时间", "neden": "原因",
        "dk": "{sayi} 分钟",
        "yonet": "取消或改期：",
        "takvim": "添加到日历：",
        "ics_not": "日历文件 (.ics) 已附在本邮件中。",
        "yeni_randevu": "重新预约：",
        "jitsi": "在线会议（Jitsi Meet）", "baglanti": "在线会议",
        "telefon": "电话沟通", "yuz_yuze": "面对面",
        "biz_arariz": "我们将拨打 {telefon} 联系您。", "siz_arayin": "请拨打 {telefon}。",
        "biz_arariz_bos": "我们将拨打您提供的号码联系您。",
    },
    "hi": {
        "onay_konu": "आपकी अपॉइंटमेंट पक्की हो गई: {tur} — {zaman}",
        "yeniden_konu": "आपकी अपॉइंटमेंट का समय बदला गया: {tur} — {zaman}",
        "iptal_konu": "आपकी अपॉइंटमेंट रद्द हो गई: {tur} — {zaman}",
        "hatirlatma_konu": "रिमाइंडर: {tur} — {zaman}",
        "merhaba": "नमस्ते {ad},",
        "onay_giris": "{sayfa} के साथ आपकी अपॉइंटमेंट पक्की हो गई है।",
        "yeniden_giris": "{sayfa} के साथ आपकी अपॉइंटमेंट नए समय पर कर दी गई है।",
        "iptal_giris": "{sayfa} के साथ आपकी अपॉइंटमेंट रद्द कर दी गई है।",
        "hatirlatma_giris": "{sayfa} के साथ आपकी अपॉइंटमेंट जल्द है।",
        "ne": "मीटिंग", "ne_zaman": "समय", "sure": "अवधि", "nerede": "स्थान", "kiminle": "किसके साथ",
        "onceki": "पिछला समय", "neden": "कारण",
        "dk": "{sayi} मिनट",
        "yonet": "रद्द करने या समय बदलने के लिए:",
        "takvim": "कैलेंडर में जोड़ें:",
        "ics_not": "कैलेंडर फ़ाइल (.ics) इस ईमेल के साथ संलग्न है।",
        "yeni_randevu": "नई अपॉइंटमेंट लेने के लिए:",
        "jitsi": "ऑनलाइन मीटिंग (Jitsi Meet)", "baglanti": "ऑनलाइन मीटिंग",
        "telefon": "फ़ोन कॉल", "yuz_yuze": "आमने-सामने",
        "biz_arariz": "हम आपको {telefon} पर कॉल करेंगे।", "siz_arayin": "कृपया {telefon} पर कॉल करें।",
        "biz_arariz_bos": "हम आपको आपके दिए नंबर पर कॉल करेंगे।",
    },
    "ar": {
        "onay_konu": "تم تأكيد موعدك: {tur} — {zaman}",
        "yeniden_konu": "تمت إعادة جدولة موعدك: {tur} — {zaman}",
        "iptal_konu": "تم إلغاء موعدك: {tur} — {zaman}",
        "hatirlatma_konu": "تذكير: {tur} — {zaman}",
        "merhaba": "مرحبًا {ad}،",
        "onay_giris": "تم تأكيد موعدك مع {sayfa}.",
        "yeniden_giris": "تم نقل موعدك مع {sayfa} إلى وقت جديد.",
        "iptal_giris": "تم إلغاء موعدك مع {sayfa}.",
        "hatirlatma_giris": "موعدك مع {sayfa} يقترب.",
        "ne": "الاجتماع", "ne_zaman": "الوقت", "sure": "المدة", "nerede": "المكان", "kiminle": "مع",
        "onceki": "الوقت السابق", "neden": "السبب",
        "dk": "{sayi} دقيقة",
        "yonet": "للإلغاء أو إعادة الجدولة:",
        "takvim": "أضف إلى التقويم:",
        "ics_not": "ملف التقويم (.ics) مرفق بهذه الرسالة.",
        "yeni_randevu": "لحجز موعد جديد:",
        "jitsi": "اجتماع عبر الإنترنت (Jitsi Meet)", "baglanti": "اجتماع عبر الإنترنت",
        "telefon": "مكالمة هاتفية", "yuz_yuze": "حضوريًا",
        "biz_arariz": "سنتصل بك على الرقم {telefon}.", "siz_arayin": "يرجى الاتصال بالرقم {telefon}.",
        "biz_arariz_bos": "سنتصل بك على الرقم الذي قدمته.",
    },
}


def metinler(dil: str) -> Dict[str, str]:
    return METINLER.get(dil) or METINLER["tr"]


def zaman_yaz(an: datetime, tz_adi: str, dil: str = "tr") -> str:
    """Yerelleştirilmiş tarih + saat + saat dilimi adı (Babel yoksa ISO)."""
    try:
        tz = saat_dilimi(tz_adi)
    except RandevuHatasi:
        tz, tz_adi = saat_dilimi(VARSAYILAN_SAAT_DILIMI), VARSAYILAN_SAAT_DILIMI
    yerel = utc(an).astimezone(tz)
    try:
        from babel.dates import format_date

        gun = format_date(yerel.date(), "full", locale=dil if dil in DILLER else "tr")
    except Exception:  # noqa: BLE001 - Babel yoksa sade biçim
        gun = yerel.strftime("%Y-%m-%d")
    return f"{gun}, {yerel.strftime('%H:%M')} ({tz_adi})"


def konum_metni(konum_turu: str, konum: Optional[str], dil: str, ziyaretci_telefonu: Optional[str] = None) -> str:
    m = metinler(dil)
    if konum_turu in ("jitsi", "baglanti"):
        return f"{m[konum_turu]}: {konum}" if konum else m[konum_turu]
    if konum_turu == "telefon":
        if konum:
            return f"{m['telefon']} — {m['siz_arayin'].format(telefon=konum)}"
        if ziyaretci_telefonu:
            return f"{m['telefon']} — {m['biz_arariz'].format(telefon=ziyaretci_telefonu)}"
        return f"{m['telefon']} — {m['biz_arariz_bos']}"
    return f"{m['yuz_yuze']}: {konum}" if konum else m["yuz_yuze"]


def eposta_govdesi(
    *, tur: str, dil: str, ad: str, sayfa: str, tur_adi: str, zaman: str, sure: int, konum: str, kiminle: str,
    yonet_adresi: Optional[str] = None, google: Optional[str] = None, outlook: Optional[str] = None,
    onceki: Optional[str] = None, neden: Optional[str] = None, yeni_randevu: Optional[str] = None,
) -> Tuple[str, str]:
    """(konu, metin). `tur`: onay | yeniden | iptal | hatirlatma."""
    m = metinler(dil)
    konu = m[f"{tur}_konu"].format(tur=tur_adi, zaman=zaman)
    satirlar = [m["merhaba"].format(ad=ad or "—"), "", m[f"{tur}_giris"].format(sayfa=sayfa), ""]
    satirlar.append(f"{m['ne']}: {tur_adi}")
    satirlar.append(f"{m['ne_zaman']}: {zaman}")
    if onceki:
        satirlar.append(f"{m['onceki']}: {onceki}")
    satirlar.append(f"{m['sure']}: {m['dk'].format(sayi=sure)}")
    satirlar.append(f"{m['nerede']}: {konum}")
    if kiminle:
        satirlar.append(f"{m['kiminle']}: {kiminle}")
    if neden:
        satirlar.append(f"{m['neden']}: {neden}")
    if tur != "iptal":
        if google or outlook:
            satirlar += ["", m["takvim"]]
            if google:
                satirlar.append(f"Google: {google}")
            if outlook:
                satirlar.append(f"Outlook: {outlook}")
            satirlar.append(m["ics_not"])
        if yonet_adresi:
            satirlar += ["", m["yonet"], yonet_adresi]
    elif yeni_randevu:
        satirlar += ["", m["yeni_randevu"], yeni_randevu]
    satirlar += ["", f"— {sayfa}"]
    return konu, "\n".join(satirlar)
