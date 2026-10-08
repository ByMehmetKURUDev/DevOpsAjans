"""Faz 6K — Eğitim modülü: kurallar ve yardımcılar (veritabanına dokunmayan her şey).

Router `routers/egitim.py`, veritabanı işleri `services/egitim_kayit.py`. Burada:

* Doğrulayıcılar (randevu/etkinlik yardımcıları yeniden kullanılıyor; hata sınıfı onların alt
  sınıfı — router tek yerde yakalar).
* İmzalı jetonlar (HMAC, `JWT_SECRET_KEY`'den amaca bağlı türetilmiş ayrı anahtar):
  - öğrenci portalı `<öğrenci id>-<sürüm>-<imza>` (girişsiz; sürüm artınca eski bağlantı ölür;
    kurs bitişinden `JETON_OMRU_GUN` sonra süresi dolar),
  - oturum yoklaması `<oturum id>-<sürüm>-<imza>` (yalnız ders saati penceresinde geçerli) ve
    aynı imzadan türeyen 6 haneli kısa kod (tahtaya yazılır, öğrenci portalda girer),
  - öğrenci QR'ı `MKO1.<öğrenci kodu>.<imza>` — KİŞİSEL VERİ YOK (etkinlik bileti deseni).
* Quiz soruları: doğrulama, öğrenciye giden (cevapsız) kopya ve otomatik puanlama.
* ICS (RFC 5545; her oturum bir VEVENT), öğrenci/veli e-postaları 7 dilde (bilgilendirme —
  pazarlama değil), şablonlu sertifika PDF'i (ReportLab, sitenin yazı tipi, vektör QR).
* "AI ile soru üret": istem + yanıt ayrıştırma (model JSON döndürmezse test ortamında sahte
  yanıt yerine dersin metninden belirlenimci soru).
"""

import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services import randevu as r

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
MODUL = "egitim"
IZIN = "egitim"
IZIN_EGITMEN = "egitim_egitmen"
DILLER: Tuple[str, ...] = r.DILLER
BICIMLER: Tuple[str, ...] = ("yuz_yuze", "online", "karma")
DURUMLAR: Tuple[str, ...] = ("taslak", "yayinda", "tamamlandi", "arsiv")
HEDEF_KITLELER: Tuple[str, ...] = ("yetiskin", "cocuk", "karma")
TELEFON_SECENEKLERI: Tuple[str, ...] = r.TELEFON_SECENEKLERI
OGRENCI_DURUMLARI: Tuple[str, ...] = ("aktif", "bekleme", "ayrildi")
YOKLAMA_DURUMLARI: Tuple[str, ...] = ("var", "gec", "yok", "izinli")
#: Katıldı sayılan yoklama durumları.
KATILDI: Tuple[str, ...] = ("var", "gec")
SORU_TURLERI: Tuple[str, ...] = ("coktan", "dogru_yanlis", "kisa")
QUIZ_TURLERI: Tuple[str, ...] = ("quiz", "odev")
SABLONLAR: Tuple[str, ...] = ("klasik", "modern")
OKUTMA_SONUCLARI: Tuple[str, ...] = ("gecerli", "zaten_girdi", "gecersiz", "iptal", "farkli_etkinlik", "etkinlik_iptal")
VARSAYILAN_SAAT_DILIMI = r.VARSAYILAN_SAAT_DILIMI
EN_COK_EGITMEN = 10
EN_COK_OTURUM = 400
EN_COK_URETIM = 200
EN_COK_DERS = 300
EN_COK_QUIZ = 100
EN_COK_SORU = 50
EN_COK_SECENEK = 6
EN_COK_KABUL = 5
EN_COK_CSV = 500
KAPASITE_EN_COK = 10_000
VARSAYILAN_SAKLAMA_GUN = 365
SAKLAMA_EN_AZ, SAKLAMA_EN_COK = 30, 1095
#: Öğrenci bağlantısı kurs bitişinden bu kadar gün sonra da açılır (sertifika indirme).
JETON_OMRU_GUN = 120
#: Oturum QR'ı / kısa kodu ders başlamadan bu kadar önce açılır, bittikten bu kadar sonra kapanır.
YOKLAMA_PENCERESI = timedelta(minutes=30)
#: Bu kadar geç okutma "geç" sayılır.
GEC_ESIGI = timedelta(minutes=15)
#: Quiz süresinde ağ gecikmesi payı.
SURE_PAYI = timedelta(seconds=30)
#: "AI ile soru üret": dahil hak bitince kredi ile aşımda üretim başına kredi (saat).
AI_KREDI = 0.05
#: Bütün hesaplar için günlük yapay zekâ bütçesi (site geneli kesici).
AI_GUNLUK_BUTCE = 300
AI_KAPSAM = "egitim"
AI_ICERIK_SINIRI = 6000
DOSYA_EN_COK_MB = 20

SLUG_DESENI = r.SLUG_DESENI
AYRILMIS_SLUGLAR = frozenset({
    *r.AYRILMIS_SLUGLAR, "egitim", "egitimler", "ogrenci", "sertifika", "yoklama", "okut", "kurum", "kurs",
    "kayit", "liste", "dosya", "quiz", "odev", "takvim",
})
_KOD_ALFABESI = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
OGRENCI_KODU_UZUNLUGU = 8
SERTIFIKA_KODU_UZUNLUGU = 12
OGRENCI_KODU_DESENI = re.compile(r"^[A-HJ-NP-Z2-9]{8}$")
SERTIFIKA_KODU_DESENI = re.compile(r"^[A-HJ-NP-Z2-9]{12}$")
OTURUM_KODU_DESENI = re.compile(r"^[A-HJ-NP-Z2-9]{6}$")
QR_ONEKI = "MKO1"
UTC = timezone.utc


class EgitimHatasi(r.RandevuHatasi):
    """Doğrulama/iş kuralı hatası: `{"kod", "alan"?, ...}` gövdesiyle döner."""


TemelHata = r.RandevuHatasi


def simdi() -> datetime:
    """Testler bu fonksiyonu sabit bir ana çeviriyor (bütün zaman hesapları buradan)."""
    return datetime.now(UTC)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    return r.utc(an)


def iso(an: Optional[datetime]) -> Optional[str]:
    return r.iso(an)


def json_yukle(ham: Any, varsayilan: Any = None) -> Any:
    return r.json_yukle(ham, varsayilan)


def json_yaz(deger: Any) -> str:
    return r.json_yaz(deger)


def site_adresi() -> str:
    return r.site_adresi()


def kurs_adresi(slug: str) -> str:
    return f"{site_adresi()}/egitim/{slug}"


def portal_adresi(jeton: str) -> str:
    return f"{site_adresi()}/egitim/ogrenci/{jeton}"


def yoklama_adresi(jeton: str) -> str:
    return f"{site_adresi()}/egitim/yoklama/{jeton}"


def sertifika_adresi(kod: str) -> str:
    return f"{site_adresi()}/egitim/sertifika/{kod}"


def kurum_adresi(slug: str) -> str:
    return f"{site_adresi()}/egitim/kurum/{slug}"


# ---------------------------------------------------------------------------
# Doğrulayıcılar
# ---------------------------------------------------------------------------
metin = r.metin
eposta_duzelt = r.eposta_duzelt
telefon_duzelt = r.telefon_duzelt
tam_sayi = r.tam_sayi
bool_duzelt = r.bool_duzelt
renk_duzelt = r.renk_duzelt
dil_duzelt = r.dil_duzelt
saat_dilimi = r.saat_dilimi
saat_dilimi_duzelt = r.saat_dilimi_duzelt


def slug_oner(ad: str, yedek: str = "kurs") -> str:
    aday = r.slug_oner(ad, yedek)
    return aday if aday not in AYRILMIS_SLUGLAR else f"{aday}-{secrets.token_hex(2)}"


def slug_duzelt(ham: Any, alan: str = "slug") -> str:
    deger = r.slug_duzelt(ham, alan)
    if deger in AYRILMIS_SLUGLAR:
        raise EgitimHatasi("slug_ayrilmis", alan)
    return deger


def secim(ham: Any, secenekler: Sequence[str], alan: str) -> str:
    if ham not in secenekler:
        raise EgitimHatasi("secim_gecersiz", alan)
    return str(ham)


def tarih_duzelt(ham: Any, alan: str, bos_olabilir: bool = True) -> Optional[date]:
    if ham in (None, ""):
        if bos_olabilir:
            return None
        raise EgitimHatasi("zorunlu", alan)
    try:
        return r.tarih_duzelt(ham, alan)
    except TemelHata:
        raise EgitimHatasi("tarih_gecersiz", alan)


def zaman_coz(ham: Any, alan: str, bos_olabilir: bool = False) -> Optional[datetime]:
    """ISO 8601, saat dilimi ŞART (`2026-11-05T19:00:00+03:00` ya da `…Z`) → UTC."""
    if ham in (None, ""):
        if bos_olabilir:
            return None
        raise EgitimHatasi("zorunlu", alan)
    try:
        an = datetime.fromisoformat(str(ham).strip().replace("Z", "+00:00"))
    except ValueError:
        raise EgitimHatasi("zaman_gecersiz", alan)
    if an.tzinfo is None:
        raise EgitimHatasi("zaman_gecersiz", alan)
    return an.astimezone(UTC).replace(microsecond=0)


def https_duzelt(ham: Any, alan: str, zorunlu: bool = False) -> Optional[str]:
    from services import dinamik_qr as qr

    deger = str(ham or "").strip()
    if not deger:
        if zorunlu:
            raise EgitimHatasi("zorunlu", alan)
        return None
    try:
        adres = qr.web_adresi_duzelt(deger, alan, True)
    except qr.QrHatasi:
        raise EgitimHatasi("baglanti_gecersiz", alan)
    if not adres.startswith("https://"):
        raise EgitimHatasi("baglanti_gecersiz", alan)
    return adres[:500]


_YOUTUBE = re.compile(r"^https://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{6,20})")
_VIMEO = re.compile(r"^https://(?:www\.|player\.)?vimeo\.com/(?:video/)?(\d{5,12})")


def video_bilgisi(adres: Optional[str]) -> Optional[Dict[str, Any]]:
    """Video bağlantısının türü. Sitenin CSP'si YouTube/Vimeo çerçevesine izin vermiyor (frame-src):
    video gömülmez, bağlantı yeni sekmede açılır — tıklanana kadar üçüncü tarafa istek yok (KVKK)."""
    if not adres:
        return None
    m = _YOUTUBE.match(adres)
    if m:
        return {"saglayici": "youtube", "kimlik": m.group(1), "adres": adres}
    m = _VIMEO.match(adres)
    if m:
        return {"saglayici": "vimeo", "kimlik": m.group(1), "adres": adres}
    return {"saglayici": "baglanti", "kimlik": None, "adres": adres}


def egitmenler_duzelt(ham: Any) -> List[Dict[str, str]]:
    """[{"ad", "eposta"}] — e-posta küçük harf, tekrar yok, en çok 10."""
    if ham in (None, ""):
        return []
    if not isinstance(ham, list) or len(ham) > EN_COK_EGITMEN:
        raise EgitimHatasi("egitmen_gecersiz", "egitmenler", en_cok=EN_COK_EGITMEN)
    sonuc: List[Dict[str, str]] = []
    gorulen = set()
    for i, e in enumerate(ham):
        if not isinstance(e, dict):
            raise EgitimHatasi("egitmen_gecersiz", f"egitmenler.{i}")
        ad = metin(e.get("ad"), f"egitmenler.{i}.ad", 120, zorunlu=True)
        ep = eposta_duzelt(e.get("eposta"), f"egitmenler.{i}.eposta", zorunlu=False) or ""
        if ep and ep in gorulen:
            raise EgitimHatasi("egitmen_tekrar", f"egitmenler.{i}.eposta")
        if ep:
            gorulen.add(ep)
        sonuc.append({"ad": ad, "eposta": ep})
    return sonuc


def egitmen_epostalari(kurs: Any) -> List[str]:
    return [e.get("eposta") for e in (json_yukle(kurs.egitmenler, []) or []) if isinstance(e, dict) and e.get("eposta")]


def egitmen_mi(kurs: Any, eposta: Optional[str]) -> bool:
    return bool(eposta) and (eposta or "").strip().lower() in egitmen_epostalari(kurs)


def egitmen_adlari(kurs: Any) -> List[str]:
    return [str(e.get("ad")) for e in (json_yukle(kurs.egitmenler, []) or []) if isinstance(e, dict) and e.get("ad")]


# ---------------------------------------------------------------------------
# Quiz soruları ve puanlama
# ---------------------------------------------------------------------------
def _kisa_normal(deger: Any) -> str:
    """Kısa cevap karşılaştırması: büyük/küçük harf, i/ı/İ/I, aksan ve noktalama farkı yok sayılır."""
    metin_ = unicodedata.normalize("NFKC", str(deger or "")).replace("İ", "i").replace("I", "i").replace("ı", "i")
    metin_ = metin_.casefold()
    metin_ = "".join(c for c in unicodedata.normalize("NFD", metin_) if unicodedata.category(c) != "Mn")
    metin_ = re.sub(r"[^\w\s]", " ", metin_)
    return re.sub(r"\s+", " ", metin_).strip()


def sorular_duzelt(ham: Any) -> List[Dict[str, Any]]:
    """[{"id", "tur", "metin", "secenekler"?, "dogru", "puan"}] — doğrulanmış kopya (kimlik yoksa verilir)."""
    if ham in (None, ""):
        return []
    if not isinstance(ham, list) or len(ham) > EN_COK_SORU:
        raise EgitimHatasi("soru_sayisi", "sorular", en_cok=EN_COK_SORU)
    sonuc: List[Dict[str, Any]] = []
    kimlikler = set()
    for i, s in enumerate(ham):
        alan = f"sorular.{i}"
        if not isinstance(s, dict):
            raise EgitimHatasi("soru_gecersiz", alan)
        tur = s.get("tur")
        if tur not in SORU_TURLERI:
            raise EgitimHatasi("soru_turu", f"{alan}.tur")
        kimlik = str(s.get("id") or "").strip()[:12]
        if not re.match(r"^[A-Za-z0-9_-]{1,12}$", kimlik) or kimlik in kimlikler:
            kimlik = f"s{len(sonuc) + 1}"
            while kimlik in kimlikler:
                kimlik = f"s{secrets.token_hex(2)}"
        kimlikler.add(kimlik)
        soru: Dict[str, Any] = {
            "id": kimlik,
            "tur": tur,
            "metin": metin(s.get("metin"), f"{alan}.metin", 1000, zorunlu=True, cok_satir=True),
            "puan": int(tam_sayi(s.get("puan", 1) if s.get("puan") not in (None, "") else 1, f"{alan}.puan", 1, 10)),
        }
        if tur == "coktan":
            secenekler = s.get("secenekler")
            if not isinstance(secenekler, list) or not 2 <= len(secenekler) <= EN_COK_SECENEK:
                raise EgitimHatasi("secenek_sayisi", f"{alan}.secenekler", en_az=2, en_cok=EN_COK_SECENEK)
            soru["secenekler"] = [metin(x, f"{alan}.secenekler.{j}", 200, zorunlu=True) for j, x in enumerate(secenekler)]
            dogru = s.get("dogru")
            if isinstance(dogru, bool) or not isinstance(dogru, int) or not 0 <= dogru < len(secenekler):
                raise EgitimHatasi("dogru_gecersiz", f"{alan}.dogru")
            soru["dogru"] = int(dogru)
        elif tur == "dogru_yanlis":
            if not isinstance(s.get("dogru"), bool):
                raise EgitimHatasi("dogru_gecersiz", f"{alan}.dogru")
            soru["dogru"] = bool(s["dogru"])
        else:
            dogru = s.get("dogru")
            if isinstance(dogru, str):
                dogru = [x for x in dogru.split("|")]
            if not isinstance(dogru, list) or not 1 <= len(dogru) <= EN_COK_KABUL:
                raise EgitimHatasi("dogru_gecersiz", f"{alan}.dogru", en_cok=EN_COK_KABUL)
            kabul = [metin(x, f"{alan}.dogru.{j}", 100, zorunlu=True) for j, x in enumerate(dogru)]
            if not all(_kisa_normal(x) for x in kabul):
                raise EgitimHatasi("dogru_gecersiz", f"{alan}.dogru")
            soru["dogru"] = kabul
        sonuc.append(soru)
    return sonuc


def sorular_ogrenciye(sorular: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Öğrenciye giden kopya: doğru cevaplar YOK."""
    return [{k: v for k, v in s.items() if k != "dogru"} for s in sorular]


def puanla(sorular: Sequence[Dict[str, Any]], yanitlar: Any) -> Dict[str, Any]:
    """Otomatik puan: yüzde (0–100, yuvarlanmış), doğru sayısı, soru başına doğru/yanlış."""
    yanitlar = yanitlar if isinstance(yanitlar, dict) else {}
    toplam_puan = kazanilan = dogru_sayisi = 0
    ayrinti: Dict[str, bool] = {}
    for s in sorular:
        puan = int(s.get("puan") or 1)
        toplam_puan += puan
        y = yanitlar.get(s["id"])
        dogru = False
        if s["tur"] == "coktan":
            dogru = isinstance(y, int) and not isinstance(y, bool) and y == s.get("dogru")
        elif s["tur"] == "dogru_yanlis":
            dogru = isinstance(y, bool) and y == s.get("dogru")
        elif isinstance(y, str) and y.strip():
            dogru = _kisa_normal(y[:200]) in {_kisa_normal(x) for x in (s.get("dogru") or [])}
        ayrinti[s["id"]] = dogru
        if dogru:
            kazanilan += puan
            dogru_sayisi += 1
    yuzde = int(round(100 * kazanilan / toplam_puan)) if toplam_puan else 0
    return {"puan": yuzde, "dogru": dogru_sayisi, "toplam": len(sorular), "ayrinti": ayrinti}


def yanitlari_temizle(sorular: Sequence[Dict[str, Any]], ham: Any) -> Dict[str, Any]:
    """Saklanacak yanıtlar: yalnız sorulan kimlikler, türüne uygun değerler."""
    if not isinstance(ham, dict):
        return {}
    sonuc: Dict[str, Any] = {}
    for s in sorular:
        y = ham.get(s["id"])
        if s["tur"] == "coktan" and isinstance(y, int) and not isinstance(y, bool) and 0 <= y < len(s.get("secenekler") or []):
            sonuc[s["id"]] = y
        elif s["tur"] == "dogru_yanlis" and isinstance(y, bool):
            sonuc[s["id"]] = y
        elif s["tur"] == "kisa" and isinstance(y, str) and y.strip():
            sonuc[s["id"]] = y.strip()[:200]
    return sonuc


# ---------------------------------------------------------------------------
# Kodlar ve imzalı jetonlar
# ---------------------------------------------------------------------------
def kod_uret(uzunluk: int = OGRENCI_KODU_UZUNLUGU) -> str:
    return "".join(secrets.choice(_KOD_ALFABESI) for _ in range(uzunluk))


_YEDEK: Optional[bytes] = None


def _anahtar() -> bytes:
    global _YEDEK
    gizli = os.environ.get("JWT_SECRET_KEY") or ""
    if not gizli:
        if _YEDEK is None:
            _YEDEK = secrets.token_bytes(32)
        return _YEDEK
    return hashlib.sha256(("egitim:" + gizli).encode()).digest()


def _imza(mesaj: str, uzunluk: int = 32) -> str:
    return hmac.new(_anahtar(), mesaj.encode(), hashlib.sha256).hexdigest()[:uzunluk]


_UC_PARCA = re.compile(r"^(\d{1,12})-(\d{1,6})-([0-9a-f]{32})$")


def ogrenci_jetonu(ogrenci_id: int, surum: int, kod: str) -> str:
    return f"{int(ogrenci_id)}-{int(surum)}-{_imza(f'ogrenci|{int(ogrenci_id)}|{int(surum)}|{kod}')}"


def jeton_parcala(jeton: Any) -> Optional[Tuple[int, int]]:
    """(kimlik, sürüm) — yalnız biçim; imza ve süre çağıranda."""
    m = _UC_PARCA.match(str(jeton or ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def ogrenci_jetonu_gecerli_mi(jeton: Any, ogrenci_id: int, surum: int, kod: str) -> bool:
    return hmac.compare_digest(str(jeton or ""), ogrenci_jetonu(ogrenci_id, surum, kod))


def oturum_jetonu(oturum_id: int, surum: int) -> str:
    return f"{int(oturum_id)}-{int(surum)}-{_imza(f'oturum|{int(oturum_id)}|{int(surum)}')}"


def oturum_jetonu_gecerli_mi(jeton: Any, oturum_id: int, surum: int) -> bool:
    return hmac.compare_digest(str(jeton or ""), oturum_jetonu(oturum_id, surum))


def oturum_kodu(oturum_id: int, surum: int) -> str:
    """Tahtaya yazılan 6 haneli kısa kod (QR okutamayan öğrenci portalda girer)."""
    ozet = hmac.new(_anahtar(), f"oturum-kod|{int(oturum_id)}|{int(surum)}".encode(), hashlib.sha256).digest()
    return "".join(_KOD_ALFABESI[b % len(_KOD_ALFABESI)] for b in ozet[:6])


def yoklama_penceresi(oturum: Any) -> Tuple[datetime, datetime]:
    return utc(oturum.baslangic) - YOKLAMA_PENCERESI, utc(oturum.bitis) + YOKLAMA_PENCERESI


def yoklama_acik_mi(oturum: Any, an: Optional[datetime] = None) -> bool:
    an = an or simdi()
    bas, bit = yoklama_penceresi(oturum)
    return oturum.durum != "iptal" and bas <= an <= bit


def qr_imzasi(kod: str) -> str:
    return _imza(f"ogrenci-qr|{kod}", 16).upper()


def qr_icerigi(kod: str) -> str:
    """Öğrencinin QR'ına giden metin: önek + öğrenci kodu + imza. Kişisel veri YOK."""
    return f"{QR_ONEKI}.{kod}.{qr_imzasi(kod)}"


def okutma_coz(ham: Any) -> Tuple[Optional[str], bool]:
    """Okutulan/elle girilen metin → (öğrenci kodu, imza denetlendi mi). Sahte imza → None."""
    deger = str(ham or "").strip()
    if not deger or len(deger) > 120:
        return None, False
    if deger.upper().startswith(QR_ONEKI + "."):
        parca = deger.split(".")
        if len(parca) != 3:
            return None, True
        kod, imza = parca[1].upper(), parca[2].upper()
        if not OGRENCI_KODU_DESENI.match(kod) or not hmac.compare_digest(imza, qr_imzasi(kod)):
            return None, True
        return kod, True
    kod = re.sub(r"[\s\-]", "", deger).upper()
    return (kod if OGRENCI_KODU_DESENI.match(kod) else None), False


def kisa_kod_duzelt(ham: Any) -> Optional[str]:
    kod = re.sub(r"[\s\-]", "", str(ham or "")).upper()
    return kod if OTURUM_KODU_DESENI.match(kod) else None


def sertifika_kodu_duzelt(ham: Any) -> Optional[str]:
    kod = re.sub(r"[\s\-]", "", str(ham or "")).upper()
    return kod if SERTIFIKA_KODU_DESENI.match(kod) else None


def sertifika_kodu_yaz(kod: str) -> str:
    return "-".join(kod[i:i + 4] for i in range(0, len(kod), 4))


def ad_maskele(ad: Optional[str]) -> str:
    """Doğrulama sayfasında görünen ad: "Ayşe Yılmaz" → "Ayşe Y."; tek kelime → "A.". """
    parcalar = [p for p in re.split(r"\s+", str(ad or "").strip()) if p]
    if not parcalar:
        return "—"
    if len(parcalar) == 1:
        return parcalar[0][:1].upper() + "."
    return f"{parcalar[0][:40]} " + " ".join(p[:1].upper() + "." for p in parcalar[1:])


# ---------------------------------------------------------------------------
# Görünen zaman
# ---------------------------------------------------------------------------
def zaman_yaz(an: datetime, tz_adi: str, dil: str = "tr") -> str:
    return r.zaman_yaz(an, tz_adi, dil)


def aralik_yaz(bas: datetime, bit: datetime, tz_adi: str, dil: str = "tr") -> str:
    try:
        tz = saat_dilimi(tz_adi)
    except TemelHata:
        tz = saat_dilimi(VARSAYILAN_SAAT_DILIMI)
    yb, ye = utc(bas).astimezone(tz), utc(bit).astimezone(tz)
    if yb.date() == ye.date():
        return f"{zaman_yaz(bas, tz_adi, dil)} – {ye.strftime('%H:%M')}"
    return f"{zaman_yaz(bas, tz_adi, dil)} – {zaman_yaz(bit, tz_adi, dil)}"


def tarih_yaz(gun: Optional[date], dil: str = "tr") -> str:
    if gun is None:
        return ""
    try:
        from babel.dates import format_date

        return format_date(gun, "long", locale=dil if dil in DILLER else "tr")
    except Exception:  # noqa: BLE001 - Babel yoksa sade biçim
        return gun.isoformat()


def yerel_gun(an: datetime, tz_adi: str) -> date:
    try:
        tz = saat_dilimi(tz_adi)
    except TemelHata:
        tz = saat_dilimi(VARSAYILAN_SAAT_DILIMI)
    return utc(an).astimezone(tz).date()


def oturumlari_uret(bas_tarih: date, bit_tarih: date, gunler: Sequence[int], saat: str, sure_dk: int,
                    tz_adi: str) -> List[Tuple[datetime, datetime]]:
    """Tekrarlayan program: tarih aralığında haftanın seçili günleri (0 = Pazartesi) × saat → UTC aralıkları."""
    if bit_tarih < bas_tarih:
        raise EgitimHatasi("bitis_once", "bit_tarih")
    if (bit_tarih - bas_tarih).days > 400:
        raise EgitimHatasi("aralik_uzun", "bit_tarih")
    if not isinstance(gunler, (list, tuple)) or not gunler or any(isinstance(g, bool) or not isinstance(g, int) or not 0 <= g <= 6 for g in gunler):
        raise EgitimHatasi("gun_gecersiz", "gunler")
    m = re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", str(saat or ""))
    if not m:
        raise EgitimHatasi("saat_gecersiz", "saat")
    tz = saat_dilimi(tz_adi)
    sonuc: List[Tuple[datetime, datetime]] = []
    gun = bas_tarih
    while gun <= bit_tarih:
        if gun.weekday() in gunler:
            yerel = datetime(gun.year, gun.month, gun.day, int(m.group(1)), int(m.group(2)), tzinfo=tz)
            b = yerel.astimezone(UTC)
            sonuc.append((b, b + timedelta(minutes=int(sure_dk))))
            if len(sonuc) > EN_COK_URETIM:
                raise EgitimHatasi("oturum_cok", "gunler", en_cok=EN_COK_URETIM)
        gun += timedelta(days=1)
    return sonuc


# ---------------------------------------------------------------------------
# ICS (RFC 5545)
# ---------------------------------------------------------------------------
def _ics_an(an: datetime) -> str:
    return utc(an).strftime("%Y%m%dT%H%M%SZ")


def konum_metni(k: Any, dil: str, ogrenciye: bool = False) -> str:
    m = metinler(dil)
    yer = ", ".join(x for x in (k.mekan, (k.adres or "").replace("\n", ", ")) if x)
    if k.bicim == "online":
        return f"{m['online']}: {k.online_baglanti}" if ogrenciye and k.online_baglanti else m["online"]
    if k.bicim == "karma":
        parca = [yer or m["yuz_yuze"]]
        parca.append(f"{m['online']}: {k.online_baglanti}" if ogrenciye and k.online_baglanti else m["online"])
        return " / ".join(parca)
    return yer or m["yuz_yuze"]


def ics_uret(k: Any, oturumlar: Sequence[Any], dil: str, *, ogrenciye: bool = False, adres: Optional[str] = None,
             an: Optional[datetime] = None) -> str:
    """Kursun programı: her oturum bir VEVENT (iptal edilen STATUS:CANCELLED). UID kalıcı."""
    from services import dinamik_qr as qr

    an = an or simdi()
    alan = (site_adresi().split("://", 1)[-1].split("/", 1)[0] or "mehmetkuru.dev").split(":", 1)[0]
    konum = konum_metni(k, dil, ogrenciye=ogrenciye)
    satirlar = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//mehmetkuru.dev//Egitim//TR", "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH", f"X-WR-CALNAME:{qr._kacis(k.ad)}"]
    for o in oturumlar:
        baslik = f"{k.ad} — {o.konu}" if o.konu else k.ad
        aciklama = [k.ad] + ([k.ozet] if k.ozet else []) + ([adres] if adres else [])
        satirlar += [
            "BEGIN:VEVENT",
            f"UID:egitim-{k.id}-{o.id}@{alan}",
            "DTSTAMP:" + _ics_an(an),
            "DTSTART:" + _ics_an(o.baslangic),
            "DTEND:" + _ics_an(o.bitis),
            f"SUMMARY:{qr._kacis(baslik)}",
            "STATUS:" + ("CANCELLED" if o.durum == "iptal" else "CONFIRMED"),
            f"DESCRIPTION:{qr._kacis(chr(10).join(aciklama))}",
            f"LOCATION:{qr._kacis(konum)}",
        ]
        if adres:
            satirlar.append(f"URL:{adres}")
        satirlar.append("END:VEVENT")
    satirlar.append("END:VCALENDAR")
    return "\r\n".join(qr._katla(s) for s in satirlar) + "\r\n"


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
def csv_hucre(deger: Any) -> Any:
    """Tablo programında formül olarak çalışmasın (CSV enjeksiyonu)."""
    if isinstance(deger, str) and deger[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + deger
    return deger


_CSV_BASLIKLAR = {
    "ad": "ad", "ad soyad": "ad", "adsoyad": "ad", "isim": "ad", "name": "ad", "full name": "ad", "ogrenci": "ad",
    "eposta": "eposta", "e-posta": "eposta", "email": "eposta", "e-mail": "eposta", "mail": "eposta",
    "telefon": "telefon", "tel": "telefon", "phone": "telefon", "gsm": "telefon",
    "veli": "veli_ad", "veli ad": "veli_ad", "veli adi": "veli_ad", "veli_ad": "veli_ad", "parent": "veli_ad",
    "parent name": "veli_ad", "veli eposta": "veli_eposta", "veli e-posta": "veli_eposta", "veli_eposta": "veli_eposta",
    "parent email": "veli_eposta", "veli telefon": "veli_telefon", "veli_telefon": "veli_telefon",
    "parent phone": "veli_telefon", "cocuk": "cocuk", "18 alti": "cocuk", "minor": "cocuk",
}


def _baslik_normal(b: str) -> str:
    b = unicodedata.normalize("NFKD", (b or "").strip().lower().replace("ı", "i"))
    b = "".join(c for c in b if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", b.replace("_", " ")).strip()


def csv_coz(ham: Any) -> List[Dict[str, str]]:
    """Başlık satırlı CSV (`,` ya da `;`) → [{"ad", "eposta", ...}]. En çok 500 satır."""
    if not isinstance(ham, str) or not ham.strip():
        raise EgitimHatasi("csv_bos", "csv")
    if len(ham) > 512 * 1024:
        raise EgitimHatasi("csv_buyuk", "csv")
    metin_ = ham.lstrip("﻿")
    ilk = metin_.splitlines()[0] if metin_.splitlines() else ""
    ayirici = ";" if ilk.count(";") > ilk.count(",") else ","
    okuyucu = csv.reader(io.StringIO(metin_), delimiter=ayirici)
    satirlar = [s for s in okuyucu if any((h or "").strip() for h in s)]
    if len(satirlar) < 2:
        raise EgitimHatasi("csv_bos", "csv")
    basliklar = [_CSV_BASLIKLAR.get(_baslik_normal(b)) for b in satirlar[0]]
    if "ad" not in basliklar:
        raise EgitimHatasi("csv_baslik", "csv")
    if len(satirlar) - 1 > EN_COK_CSV:
        raise EgitimHatasi("csv_cok", "csv", en_cok=EN_COK_CSV)
    sonuc = []
    for s in satirlar[1:]:
        kayit: Dict[str, str] = {}
        for b, h in zip(basliklar, s):
            if b and (h or "").strip():
                kayit[b] = h.strip()
        sonuc.append(kayit)
    return sonuc


def evet_mi(deger: Any) -> bool:
    return _baslik_normal(str(deger or "")) in ("1", "evet", "e", "yes", "y", "true", "x", "var")


# ---------------------------------------------------------------------------
# Öğrenci / veli e-postaları (7 dil; bilgilendirme niteliğinde — pazarlama değil)
# ---------------------------------------------------------------------------
METINLER: Dict[str, Dict[str, str]] = {
    "tr": {
        "merhaba": "Merhaba {ad},",
        "kayit_konu": "Kaydınız alındı: {kurs}",
        "kayit_giris": "{kurs} kursuna kaydınız tamamlandı. Ders programınız, ders içerikleri, ödevler ve yoklama durumunuz öğrenci sayfanızda.",
        "bekleme_konu": "Bekleme listesindesiniz: {kurs}",
        "bekleme_giris": "{kurs} şu an dolu; bekleme listesine {sira}. sıradan eklendiniz. Yer açılınca kaydınız kendiliğinden aktifleşir ve size haber veririz.",
        "yer_konu": "Yer açıldı, kaydınız aktif: {kurs}",
        "yer_giris": "{kurs} kursunda yer açıldı; bekleme listesindeki kaydınız aktifleştirildi.",
        "portal_konu": "Öğrenci sayfanız: {kurs}",
        "portal_giris": "{kurs} için öğrenci sayfanızın bağlantısı aşağıda. Bu bağlantı size özeldir; başkalarıyla paylaşmayın.",
        "portal": "Öğrenci sayfası (derslerim, programım, ödevlerim, quiz, sertifika):",
        "veli_not": "Bu e-postayı {ogrenci} adlı öğrencinin velisi olarak alıyorsunuz.",
        "duyuru_not": "Bu e-postayı {kurs} kursuna kayıtlı olduğunuz için alıyorsunuz (kurs bilgilendirmesi).",
        "hatirlatma_konu": "Ders hatırlatması: {kurs}",
        "hatirlatma_giris": "{kurs} dersiniz yaklaşıyor.",
        "devamsizlik_konu": "Devamsızlık bilgilendirmesi: {kurs}",
        "devamsizlik_giris": "{ogrenci} adlı öğrencinin {kurs} kursundaki devamsızlığı {sayi} derse ulaştı. Yoklama ayrıntısını öğrenci sayfasında görebilirsiniz.",
        "sertifika_konu": "Sertifikanız hazır: {kurs}",
        "sertifika_giris": "Tebrikler! {kurs} kursunu tamamladınız. Sertifikanızı öğrenci sayfanızdan indirebilirsiniz.",
        "dogrulama": "Sertifika doğrulama bağlantısı:",
        "not_konu": "Ödeviniz değerlendirildi: {odev}",
        "not_giris": "{kurs} kursundaki “{odev}” ödeviniz değerlendirildi.",
        "puan": "Puan", "geri_bildirim": "Eğitmenin notu",
        "ne_zaman": "Zaman", "nerede": "Yer", "ilk_ders": "İlk ders", "fiyat": "Ücret bilgisi",
        "online_baglanti": "Çevrim içi ders bağlantısı:",
        "yuz_yuze": "Yüz yüze", "online": "Çevrim içi", "karma": "Yüz yüze + çevrim içi",
    },
    "en": {
        "merhaba": "Hello {ad},",
        "kayit_konu": "Your enrolment is confirmed: {kurs}",
        "kayit_giris": "Your enrolment in {kurs} is complete. Your schedule, lessons, assignments and attendance are on your student page.",
        "bekleme_konu": "You are on the waiting list: {kurs}",
        "bekleme_giris": "{kurs} is currently full; you have been added to the waiting list in position {sira}. When a place opens up, your enrolment becomes active automatically and we will let you know.",
        "yer_konu": "A place opened up — your enrolment is active: {kurs}",
        "yer_giris": "A place opened up in {kurs}; your waiting-list enrolment is now active.",
        "portal_konu": "Your student page: {kurs}",
        "portal_giris": "Below is the link to your student page for {kurs}. The link is personal — please do not share it.",
        "portal": "Student page (lessons, schedule, assignments, quizzes, certificate):",
        "veli_not": "You are receiving this email as the parent or guardian of {ogrenci}.",
        "duyuru_not": "You are receiving this email because you are enrolled in {kurs} (course information).",
        "hatirlatma_konu": "Class reminder: {kurs}",
        "hatirlatma_giris": "Your {kurs} class is coming up.",
        "devamsizlik_konu": "Attendance notice: {kurs}",
        "devamsizlik_giris": "{ogrenci} has now missed {sayi} classes of {kurs}. Attendance details are on the student page.",
        "sertifika_konu": "Your certificate is ready: {kurs}",
        "sertifika_giris": "Congratulations! You have completed {kurs}. You can download your certificate from your student page.",
        "dogrulama": "Certificate verification link:",
        "not_konu": "Your assignment has been graded: {odev}",
        "not_giris": "Your assignment “{odev}” in {kurs} has been graded.",
        "puan": "Score", "geri_bildirim": "Instructor's note",
        "ne_zaman": "When", "nerede": "Where", "ilk_ders": "First class", "fiyat": "Fee information",
        "online_baglanti": "Online class link:",
        "yuz_yuze": "In person", "online": "Online", "karma": "In person + online",
    },
    "de": {
        "merhaba": "Hallo {ad},",
        "kayit_konu": "Ihre Anmeldung ist bestätigt: {kurs}",
        "kayit_giris": "Ihre Anmeldung zum Kurs {kurs} ist abgeschlossen. Stundenplan, Lektionen, Aufgaben und Anwesenheit finden Sie auf Ihrer Schülerseite.",
        "bekleme_konu": "Sie stehen auf der Warteliste: {kurs}",
        "bekleme_giris": "{kurs} ist derzeit ausgebucht; Sie stehen auf Platz {sira} der Warteliste. Wird ein Platz frei, wird Ihre Anmeldung automatisch aktiv und wir informieren Sie.",
        "yer_konu": "Ein Platz ist frei — Ihre Anmeldung ist aktiv: {kurs}",
        "yer_giris": "Im Kurs {kurs} ist ein Platz frei geworden; Ihre Anmeldung von der Warteliste ist jetzt aktiv.",
        "portal_konu": "Ihre Schülerseite: {kurs}",
        "portal_giris": "Unten finden Sie den Link zu Ihrer Schülerseite für {kurs}. Der Link ist persönlich — bitte nicht weitergeben.",
        "portal": "Schülerseite (Lektionen, Stundenplan, Aufgaben, Quiz, Zertifikat):",
        "veli_not": "Sie erhalten diese E-Mail als Erziehungsberechtigte(r) von {ogrenci}.",
        "duyuru_not": "Sie erhalten diese E-Mail, weil Sie im Kurs {kurs} angemeldet sind (Kursinformation).",
        "hatirlatma_konu": "Erinnerung an die Unterrichtsstunde: {kurs}",
        "hatirlatma_giris": "Ihre Stunde im Kurs {kurs} beginnt bald.",
        "devamsizlik_konu": "Hinweis zur Anwesenheit: {kurs}",
        "devamsizlik_giris": "{ogrenci} hat im Kurs {kurs} inzwischen {sayi} Stunden verpasst. Details zur Anwesenheit finden Sie auf der Schülerseite.",
        "sertifika_konu": "Ihr Zertifikat ist fertig: {kurs}",
        "sertifika_giris": "Herzlichen Glückwunsch! Sie haben den Kurs {kurs} abgeschlossen. Ihr Zertifikat können Sie auf Ihrer Schülerseite herunterladen.",
        "dogrulama": "Link zur Zertifikatsprüfung:",
        "not_konu": "Ihre Aufgabe wurde bewertet: {odev}",
        "not_giris": "Ihre Aufgabe „{odev}“ im Kurs {kurs} wurde bewertet.",
        "puan": "Punkte", "geri_bildirim": "Anmerkung der Lehrkraft",
        "ne_zaman": "Zeit", "nerede": "Ort", "ilk_ders": "Erste Stunde", "fiyat": "Gebühreninformation",
        "online_baglanti": "Link zum Online-Unterricht:",
        "yuz_yuze": "Vor Ort", "online": "Online", "karma": "Vor Ort + online",
    },
    "ru": {
        "merhaba": "Здравствуйте, {ad}!",
        "kayit_konu": "Вы записаны на курс: {kurs}",
        "kayit_giris": "Ваша запись на курс «{kurs}» оформлена. Расписание, уроки, задания и посещаемость — на вашей странице ученика.",
        "bekleme_konu": "Вы в листе ожидания: {kurs}",
        "bekleme_giris": "Курс «{kurs}» сейчас заполнен; вы добавлены в лист ожидания под номером {sira}. Когда освободится место, запись станет активной автоматически, и мы вам сообщим.",
        "yer_konu": "Освободилось место — запись активна: {kurs}",
        "yer_giris": "На курсе «{kurs}» освободилось место; ваша запись из листа ожидания теперь активна.",
        "portal_konu": "Ваша страница ученика: {kurs}",
        "portal_giris": "Ниже — ссылка на вашу страницу ученика курса «{kurs}». Ссылка личная, не передавайте её другим.",
        "portal": "Страница ученика (уроки, расписание, задания, тесты, сертификат):",
        "veli_not": "Вы получили это письмо как родитель или законный представитель ученика {ogrenci}.",
        "duyuru_not": "Вы получили это письмо, потому что записаны на курс «{kurs}» (информация о курсе).",
        "hatirlatma_konu": "Напоминание о занятии: {kurs}",
        "hatirlatma_giris": "Скоро ваше занятие по курсу «{kurs}».",
        "devamsizlik_konu": "Уведомление о пропусках: {kurs}",
        "devamsizlik_giris": "Ученик {ogrenci} пропустил уже {sayi} занятий курса «{kurs}». Подробности о посещаемости — на странице ученика.",
        "sertifika_konu": "Ваш сертификат готов: {kurs}",
        "sertifika_giris": "Поздравляем! Вы завершили курс «{kurs}». Сертификат можно скачать на странице ученика.",
        "dogrulama": "Ссылка для проверки сертификата:",
        "not_konu": "Ваше задание проверено: {odev}",
        "not_giris": "Ваше задание «{odev}» по курсу «{kurs}» проверено.",
        "puan": "Баллы", "geri_bildirim": "Комментарий преподавателя",
        "ne_zaman": "Время", "nerede": "Место", "ilk_ders": "Первое занятие", "fiyat": "Информация об оплате",
        "online_baglanti": "Ссылка на онлайн-занятие:",
        "yuz_yuze": "Очно", "online": "Онлайн", "karma": "Очно + онлайн",
    },
    "zh": {
        "merhaba": "{ad}，您好：",
        "kayit_konu": "报名成功：{kurs}",
        "kayit_giris": "您已成功报名 {kurs}。课程表、课程内容、作业和考勤情况都在您的学员页面中。",
        "bekleme_konu": "您已进入候补名单：{kurs}",
        "bekleme_giris": "{kurs} 目前已满；您已被加入候补名单，排在第 {sira} 位。有空位时，您的报名会自动生效，我们会通知您。",
        "yer_konu": "有空位了，您的报名已生效：{kurs}",
        "yer_giris": "{kurs} 有了空位；您在候补名单中的报名现已生效。",
        "portal_konu": "您的学员页面：{kurs}",
        "portal_giris": "以下是 {kurs} 的学员页面链接。此链接仅供您本人使用，请勿分享。",
        "portal": "学员页面（课程、课程表、作业、测验、证书）：",
        "veli_not": "您以学员 {ogrenci} 的家长或监护人身份收到此邮件。",
        "duyuru_not": "您收到此邮件是因为您已报名 {kurs}（课程通知）。",
        "hatirlatma_konu": "上课提醒：{kurs}",
        "hatirlatma_giris": "您的 {kurs} 课程即将开始。",
        "devamsizlik_konu": "缺勤通知：{kurs}",
        "devamsizlik_giris": "学员 {ogrenci} 在 {kurs} 中已缺勤 {sayi} 次课。考勤详情请查看学员页面。",
        "sertifika_konu": "您的证书已就绪：{kurs}",
        "sertifika_giris": "恭喜！您已完成 {kurs}。您可以在学员页面下载证书。",
        "dogrulama": "证书验证链接：",
        "not_konu": "您的作业已评分：{odev}",
        "not_giris": "您在 {kurs} 中的作业“{odev}”已评分。",
        "puan": "分数", "geri_bildirim": "讲师评语",
        "ne_zaman": "时间", "nerede": "地点", "ilk_ders": "第一节课", "fiyat": "费用信息",
        "online_baglanti": "线上课程链接：",
        "yuz_yuze": "线下", "online": "线上", "karma": "线下 + 线上",
    },
    "hi": {
        "merhaba": "नमस्ते {ad},",
        "kayit_konu": "आपका नामांकन पक्का हुआ: {kurs}",
        "kayit_giris": "{kurs} में आपका नामांकन पूरा हो गया है। आपकी समय-सारणी, पाठ, असाइनमेंट और उपस्थिति आपके छात्र पेज पर हैं।",
        "bekleme_konu": "आप प्रतीक्षा सूची में हैं: {kurs}",
        "bekleme_giris": "{kurs} अभी भरा हुआ है; आपको प्रतीक्षा सूची में {sira}वें स्थान पर जोड़ा गया है। जगह खाली होते ही आपका नामांकन अपने-आप सक्रिय हो जाएगा और हम आपको सूचित करेंगे।",
        "yer_konu": "जगह खाली हुई — आपका नामांकन सक्रिय है: {kurs}",
        "yer_giris": "{kurs} में जगह खाली हुई; प्रतीक्षा सूची वाला आपका नामांकन अब सक्रिय है।",
        "portal_konu": "आपका छात्र पेज: {kurs}",
        "portal_giris": "{kurs} के लिए आपके छात्र पेज का लिंक नीचे है। यह लिंक निजी है — कृपया इसे साझा न करें।",
        "portal": "छात्र पेज (पाठ, समय-सारणी, असाइनमेंट, क्विज़, प्रमाणपत्र):",
        "veli_not": "आपको यह ईमेल छात्र {ogrenci} के अभिभावक के रूप में मिला है।",
        "duyuru_not": "आपको यह ईमेल इसलिए मिला है क्योंकि आप {kurs} में नामांकित हैं (पाठ्यक्रम सूचना)।",
        "hatirlatma_konu": "कक्षा अनुस्मारक: {kurs}",
        "hatirlatma_giris": "आपकी {kurs} कक्षा जल्द शुरू होने वाली है।",
        "devamsizlik_konu": "अनुपस्थिति सूचना: {kurs}",
        "devamsizlik_giris": "छात्र {ogrenci} {kurs} की {sayi} कक्षाओं में अनुपस्थित रह चुके हैं। उपस्थिति का विवरण छात्र पेज पर है।",
        "sertifika_konu": "आपका प्रमाणपत्र तैयार है: {kurs}",
        "sertifika_giris": "बधाई हो! आपने {kurs} पूरा कर लिया है। आप अपना प्रमाणपत्र छात्र पेज से डाउनलोड कर सकते हैं।",
        "dogrulama": "प्रमाणपत्र सत्यापन लिंक:",
        "not_konu": "आपके असाइनमेंट का मूल्यांकन हो गया: {odev}",
        "not_giris": "{kurs} में आपके असाइनमेंट “{odev}” का मूल्यांकन हो गया है।",
        "puan": "अंक", "geri_bildirim": "प्रशिक्षक की टिप्पणी",
        "ne_zaman": "समय", "nerede": "स्थान", "ilk_ders": "पहली कक्षा", "fiyat": "शुल्क जानकारी",
        "online_baglanti": "ऑनलाइन कक्षा लिंक:",
        "yuz_yuze": "व्यक्तिगत रूप से", "online": "ऑनलाइन", "karma": "व्यक्तिगत रूप से + ऑनलाइन",
    },
    "ar": {
        "merhaba": "مرحبًا {ad}،",
        "kayit_konu": "تم تأكيد تسجيلك: {kurs}",
        "kayit_giris": "اكتمل تسجيلك في {kurs}. جدولك والدروس والواجبات وسجل حضورك موجودة في صفحة الطالب الخاصة بك.",
        "bekleme_konu": "أنت في قائمة الانتظار: {kurs}",
        "bekleme_giris": "{kurs} مكتملة العدد حاليًا؛ تمت إضافتك إلى قائمة الانتظار في المرتبة {sira}. عند توفر مكان يصبح تسجيلك فعالًا تلقائيًا وسنبلغك بذلك.",
        "yer_konu": "توفر مكان — تسجيلك فعّال الآن: {kurs}",
        "yer_giris": "توفر مكان في {kurs}؛ أصبح تسجيلك من قائمة الانتظار فعّالًا.",
        "portal_konu": "صفحة الطالب الخاصة بك: {kurs}",
        "portal_giris": "فيما يلي رابط صفحة الطالب الخاصة بك في {kurs}. الرابط شخصي — يُرجى عدم مشاركته.",
        "portal": "صفحة الطالب (الدروس، الجدول، الواجبات، الاختبارات، الشهادة):",
        "veli_not": "تصلك هذه الرسالة بصفتك وليّ أمر الطالب {ogrenci}.",
        "duyuru_not": "تصلك هذه الرسالة لأنك مسجل في {kurs} (معلومات الدورة).",
        "hatirlatma_konu": "تذكير بالدرس: {kurs}",
        "hatirlatma_giris": "يقترب موعد درسك في {kurs}.",
        "devamsizlik_konu": "إشعار غياب: {kurs}",
        "devamsizlik_giris": "بلغ عدد غيابات الطالب {ogrenci} في {kurs} {sayi} دروس. تفاصيل الحضور في صفحة الطالب.",
        "sertifika_konu": "شهادتك جاهزة: {kurs}",
        "sertifika_giris": "تهانينا! لقد أتممت {kurs}. يمكنك تنزيل شهادتك من صفحة الطالب.",
        "dogrulama": "رابط التحقق من الشهادة:",
        "not_konu": "تم تقييم واجبك: {odev}",
        "not_giris": "تم تقييم واجبك «{odev}» في {kurs}.",
        "puan": "الدرجة", "geri_bildirim": "ملاحظة المدرّب",
        "ne_zaman": "الوقت", "nerede": "المكان", "ilk_ders": "الدرس الأول", "fiyat": "معلومات الرسوم",
        "online_baglanti": "رابط الدرس عبر الإنترنت:",
        "yuz_yuze": "حضوريًا", "online": "عبر الإنترنت", "karma": "حضوريًا + عبر الإنترنت",
    },
}


def metinler(dil: str) -> Dict[str, str]:
    return METINLER.get(dil) or METINLER["tr"]


def imza_satiri(k: Any, kurum: Optional[str] = None) -> str:
    return f"— {kurum or (', '.join(egitmen_adlari(k)) or k.ad)}"


# ---------------------------------------------------------------------------
# Sertifika PDF'i (şablonlu) — ReportLab, sitenin yazı tipi, vektör QR
# ---------------------------------------------------------------------------
PDF_ETIKET = {
    "tr": {"baslik": "SERTİFİKA", "alt": "Kurs tamamlama belgesi", "onay": "Bu belge,", "tamamladi": "adlı katılımcının",
           "kursu": "kursunu başarıyla tamamladığını onaylar.", "tarih": "Tarih", "saat": "Toplam süre", "saat_birim": "saat",
           "egitmen": "Eğitmen", "kod": "Doğrulama kodu", "dogrula": "Doğrulamak için QR'ı okutun ya da adresi açın:"},
    "en": {"baslik": "CERTIFICATE", "alt": "Certificate of completion", "onay": "This is to certify that", "tamamladi": "",
           "kursu": "has successfully completed the course.", "tarih": "Date", "saat": "Duration", "saat_birim": "hours",
           "egitmen": "Instructor", "kod": "Verification code", "dogrula": "Scan the QR code or open the address to verify:"},
    "de": {"baslik": "ZERTIFIKAT", "alt": "Abschlusszertifikat", "onay": "Hiermit wird bestätigt, dass", "tamamladi": "",
           "kursu": "den Kurs erfolgreich abgeschlossen hat.", "tarih": "Datum", "saat": "Dauer", "saat_birim": "Stunden",
           "egitmen": "Dozent", "kod": "Prüfcode",
           "dogrula": "QR-Code scannen oder Adresse öffnen, um das Zertifikat zu prüfen:"},
    "ru": {"baslik": "СЕРТИФИКАТ", "alt": "Свидетельство об окончании курса", "onay": "Настоящим подтверждается, что",
           "tamamladi": "успешно завершил(а) курс", "kursu": "", "tarih": "Дата", "saat": "Продолжительность",
           "saat_birim": "ч", "egitmen": "Преподаватель", "kod": "Код проверки",
           "dogrula": "Для проверки отсканируйте QR-код или откройте адрес:"},
    "zh": {"baslik": "证书", "alt": "结业证书", "onay": "兹证明", "tamamladi": "已成功完成", "kursu": "课程。",
           "tarih": "日期", "saat": "总时长", "saat_birim": "小时", "egitmen": "讲师", "kod": "验证码",
           "dogrula": "扫描二维码或打开以下地址进行验证："},
    "hi": {"baslik": "प्रमाणपत्र", "alt": "पाठ्यक्रम पूर्णता प्रमाणपत्र", "onay": "यह प्रमाणित किया जाता है कि",
           "tamamladi": "ने", "kursu": "पाठ्यक्रम सफलतापूर्वक पूरा कर लिया है।", "tarih": "दिनांक", "saat": "कुल अवधि",
           "saat_birim": "घंटे", "egitmen": "प्रशिक्षक", "kod": "सत्यापन कोड",
           "dogrula": "सत्यापन के लिए QR कोड स्कैन करें या पता खोलें:"},
    "ar": {"baslik": "شهادة", "alt": "شهادة إتمام دورة", "onay": "تشهد هذه الوثيقة بأن", "tamamladi": "قد أتمّ بنجاح دورة",
           "kursu": "", "tarih": "التاريخ", "saat": "المدة الإجمالية", "saat_birim": "ساعة", "egitmen": "المدرّب",
           "kod": "رمز التحقق", "dogrula": "امسح رمز QR أو افتح العنوان للتحقق:"},
}


def sertifika_pdf(*, ad: str, kurs_adi: str, kurum: Optional[str], kod: str, verilme: datetime, sablon: str = "klasik",
                  renk: str = "#2563eb", dil: str = "tr", saat: Optional[int] = None, egitmenler: Sequence[str] = (),
                  imza_adi: Optional[str] = None, imza_unvan: Optional[str] = None,
                  tarih_araligi: Optional[str] = None) -> bytes:
    """Yatay A4, iki şablon (klasik: çift çerçeve; modern: sol renk şeridi). Etiketler 7 dilde; metin
    `services/pdf_yazi.metin_ciz` ile çiziliyor (Faz 7K: Kiril, Arapça, Devanagari, Çince adlar doğru)."""
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    from services import pdf_belge as pb
    from services.pdf_yazi import metin_ciz, metin_genisligi

    pb.fontlari_kaydet()
    d = dil if dil in PDF_ETIKET else "en"
    et = PDF_ETIKET[d]
    try:
        vurgu = colors.HexColor(renk if re.match(r"^#[0-9a-fA-F]{6}$", renk or "") else "#2563eb")
    except Exception:  # noqa: BLE001
        vurgu = colors.HexColor("#2563eb")
    koyu = colors.HexColor("#1A0B2E")
    gri = colors.HexColor("#5B5368")
    tampon = io.BytesIO()
    gen, yuk = landscape(A4)
    c = canvas.Canvas(tampon, pagesize=(gen, yuk))
    c.setTitle(f"{et['baslik'].title()} {sertifika_kodu_yaz(kod)}")
    c.setAuthor(kurum or "By Mehmet KURU Dev")
    c.setCreator("mehmetkuru.dev")
    if sablon == "modern":
        c.setFillColor(vurgu)
        c.rect(0, 0, 18 * mm, yuk, stroke=0, fill=1)
        sol, merkez = 34 * mm, (gen + 18 * mm) / 2
    else:
        c.setStrokeColor(vurgu)
        c.setLineWidth(3)
        c.rect(10 * mm, 10 * mm, gen - 20 * mm, yuk - 20 * mm, stroke=1, fill=0)
        c.setLineWidth(0.8)
        c.rect(14 * mm, 14 * mm, gen - 28 * mm, yuk - 28 * mm, stroke=1, fill=0)
        sol, merkez = 24 * mm, gen / 2

    def ortala(metin_: str, y: float, font: str, boyut: float, renk_=koyu) -> None:
        c.setFillColor(renk_)
        genislik = metin_genisligi(metin_, font, boyut)
        sinir = gen - 2 * sol
        while genislik > sinir and boyut > 9:
            boyut -= 1
            genislik = metin_genisligi(metin_, font, boyut)
        metin_ciz(c, merkez, y, metin_, font, boyut, "orta")

    ortala((kurum or "By Mehmet KURU Dev")[:80], yuk - 34 * mm, pb.KALIN, 14, gri)
    ortala(et["baslik"], yuk - 56 * mm, pb.KALIN, 40, vurgu)
    ortala(et["alt"], yuk - 66 * mm, pb.YAZI, 12, gri)
    ortala(et["onay"], yuk - 84 * mm, pb.YAZI, 13)
    ortala(ad[:80] or "—", yuk - 100 * mm, pb.KALIN, 28)
    if et["tamamladi"]:
        ortala(et["tamamladi"], yuk - 110 * mm, pb.YAZI, 13)
    ortala(f"“{kurs_adi[:120]}”", yuk - 122 * mm, pb.KALIN, 18, vurgu)
    ortala(et["kursu"], yuk - 132 * mm, pb.YAZI, 13)
    bilgi = [f"{et['tarih']}: {tarih_araligi or verilme.date().isoformat()}"]
    if saat:
        bilgi.append(f"{et['saat']}: {int(saat)} {et['saat_birim']}")
    if egitmenler:
        bilgi.append(f"{et['egitmen']}: {', '.join(egitmenler)[:120]}")
    ortala("   ·   ".join(bilgi), yuk - 146 * mm, pb.YAZI, 10.5, gri)
    # İmza alanı (sol alt) ve doğrulama (sağ alt).
    if imza_adi:
        c.setStrokeColor(gri)
        c.setLineWidth(0.6)
        c.line(sol + 6 * mm, 40 * mm, sol + 76 * mm, 40 * mm)
        c.setFillColor(koyu)
        metin_ciz(c, sol + 41 * mm, 34 * mm, imza_adi[:60], pb.KALIN, 11, "orta")
        if imza_unvan:
            c.setFillColor(gri)
            metin_ciz(c, sol + 41 * mm, 29 * mm, imza_unvan[:60], pb.YAZI, 9, "orta")
    adres = sertifika_adresi(kod)
    kenar = 30 * mm
    w = QrCodeWidget(adres, barLevel="M")
    x1, y1, x2, y2 = w.getBounds()
    ciz = Drawing(kenar, kenar, transform=[kenar / (x2 - x1), 0, 0, kenar / (y2 - y1), 0, 0])
    ciz.add(w)
    qx = gen - sol - kenar
    renderPDF.draw(ciz, c, qx, 24 * mm)
    c.setFillColor(gri)
    metin_ciz(c, qx - 4 * mm, 44 * mm, f"{et['kod']}: {sertifika_kodu_yaz(kod)}", pb.YAZI, 8, "sag")
    metin_ciz(c, qx - 4 * mm, 39 * mm, et["dogrula"], pb.YAZI, 8, "sag")
    metin_ciz(c, qx - 4 * mm, 34 * mm, adres[:90], pb.YAZI, 7.5, "sag")
    c.showPage()
    c.save()
    return tampon.getvalue()


# ---------------------------------------------------------------------------
# "AI ile soru üret"
# ---------------------------------------------------------------------------
def ai_hazir() -> bool:
    """Sağlayıcı yapılandırılmış mı (ya da test ortamının sahte yanıtı açık mı)? İçerik stüdyosuyla aynı kural."""
    from services.icerik_studyosu import ai_hazir as studyo_ai_hazir

    return studyo_ai_hazir()


def ai_mesajlari(*, dil: str, ders_baslik: str, icerik: str, sayi: int, turler: Sequence[str]) -> List[Dict[str, str]]:
    from services.yapay_zeka import DIL_ADLARI

    tur_tarifi = {
        "coktan": '{"tur":"coktan","metin":"…","secenekler":["…","…","…","…"],"dogru":<index 0-3>}',
        "dogru_yanlis": '{"tur":"dogru_yanlis","metin":"…","dogru":true|false}',
        "kisa": '{"tur":"kisa","metin":"…","dogru":["accepted answer","alternative"]}',
    }
    sistem = (
        "You write quiz questions for a course lesson. Use ONLY facts stated in the lesson text; do not invent facts. "
        f"Write in {DIL_ADLARI.get(dil, 'Turkish')}. Answer with ONLY a JSON object, no prose, no code fences: "
        '{"sorular":[...]} where each item is one of: ' + "; ".join(tur_tarifi[t] for t in turler) + ". "
        "Short-answer questions must have one- to three-word answers."
    )
    kullanici = f"Lesson title: {ders_baslik}\nNumber of questions: {int(sayi)}\n\nLesson text:\n{icerik[:AI_ICERIK_SINIRI]}"
    return [{"role": "system", "content": sistem}, {"role": "user", "content": kullanici}]


def ai_yanitini_coz(metin_: str, sayi: int) -> List[Dict[str, Any]]:
    """Modelin JSON yanıtı → doğrulanmış sorular (geçersiz olanlar atılır). Hiçbiri geçerli değilse hata."""
    ham = (metin_ or "").strip()
    ham = re.sub(r"^```(?:json)?\s*|\s*```$", "", ham)
    bas, son = ham.find("{"), ham.rfind("}")
    try:
        veri = json.loads(ham[bas:son + 1]) if bas >= 0 and son > bas else json.loads(ham)
    except (ValueError, TypeError):
        raise EgitimHatasi("ai_bicim", durum=502)
    liste = veri.get("sorular") if isinstance(veri, dict) else veri
    if not isinstance(liste, list):
        raise EgitimHatasi("ai_bicim", durum=502)
    sonuc: List[Dict[str, Any]] = []
    for s in liste[: max(1, int(sayi))]:
        try:
            sonuc += sorular_duzelt([s])
        except TemelHata:
            continue
    if not sonuc:
        raise EgitimHatasi("ai_bicim", durum=502)
    for i, s in enumerate(sonuc):
        s["id"] = f"s{i + 1}"
    return sonuc


def sahte_sorular(ders_baslik: str, icerik: str, sayi: int, turler: Sequence[str]) -> List[Dict[str, Any]]:
    """Test ortamı (ENVIRONMENT=test, sahte model): dersin cümlelerinden belirlenimci sorular."""
    cumleler = [c.strip() for c in re.split(r"(?<=[.!?])\s+", re.sub(r"[#*_`>]", "", icerik or "")) if len(c.strip()) > 12] or [ders_baslik]
    sonuc: List[Dict[str, Any]] = []
    for i in range(max(1, int(sayi))):
        tur = turler[i % len(turler)]
        cumle = cumleler[i % len(cumleler)][:300]
        if tur == "coktan":
            sonuc.append({"tur": "coktan", "metin": f"{ders_baslik}: {cumle}", "secenekler": ["Doğru", "Yanlış", "Belirtilmemiş"], "dogru": 0})
        elif tur == "dogru_yanlis":
            sonuc.append({"tur": "dogru_yanlis", "metin": cumle, "dogru": True})
        else:
            kelime = (re.findall(r"\w{4,}", cumle) or [ders_baslik])[0]
            sonuc.append({"tur": "kisa", "metin": f"{cumle.replace(kelime, '____', 1)}", "dogru": [kelime]})
    return ai_yanitini_coz(json.dumps({"sorular": sonuc}, ensure_ascii=False), sayi)


__all__ = [
    "MODUL", "IZIN", "IZIN_EGITMEN", "EgitimHatasi", "TemelHata", "simdi", "sorular_duzelt", "puanla",
    "ogrenci_jetonu", "oturum_jetonu", "oturum_kodu", "qr_icerigi", "okutma_coz", "ics_uret", "sertifika_pdf",
    "ai_mesajlari", "ai_yanitini_coz", "sahte_sorular", "csv_coz",
]
