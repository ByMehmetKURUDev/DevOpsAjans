"""Faz 6I — İnsan kaynakları: kurallar ve yardımcılar (veritabanına dokunmayan her şey).

Router `routers/ik.py`, veritabanı işleri `services/ik_kayit.py`. Burada:

* Doğrulayıcılar (randevu yardımcıları yeniden kullanılıyor; hata sınıfı onların alt sınıfı).
* Resmi tatiller: sabit ulusal günler KODDA üretilir (her yıl aynı) — 1 Ocak, 23 Nisan, 1 Mayıs, 19 Mayıs,
  15 Temmuz, 30 Ağustos, 29 Ekim; 28 Ekim yarım gün (2429 sayılı Ulusal Bayram ve Genel Tatiller Hakkında
  Kanun). Dini bayramlar (Ramazan/Kurban) yıla göre değiştiği için TOHUMLANMAZ: kullanıcı ayarlardan ekler.
* İzin günü hesabı: işyerinin çalışma günleri (ayar) ve resmi tatiller hariç; yarım gün tatil 0,5 düşer.
  (4857 m.56: ulusal bayram, hafta tatili ve genel tatil günleri yıllık izin süresine sayılmaz.)
* Yıllık izin hakkı — 4857 sayılı İş Kanunu m.53 varsayılanları (HEPSİ ayarlardan değişir; bilgilendirme
  amaçlıdır, hukuki danışmanlık değildir):
    - deneme süresi dahil en az BİR YIL çalışmadan hak doğmaz,
    - kıdemi 1–5 yıl (5 dahil) → 14 gün, 5'ten fazla 15'ten az → 20 gün, 15 yıl ve üstü → 26 gün,
    - 18 yaş ve altı ile 50 yaş ve üstü işçiye en az 20 gün.
  Hak, her işe giriş yıl dönümünde (tamamlanan kıdem yılı n ≥ 1) o yılın gün sayısı kadar doğar.
* Vardiya uyarıları (ENGELLEMEZ; ayarlardan kapanır): izinli kişiye vardiya, aynı kişiye çakışan vardiya,
  iki vardiya arası en az dinlenme (varsayılan 11 saat — Çalışma Süreleri Yönetmeliği m.5), haftalık plan
  üst sınırı (varsayılan 45 saat — 4857 m.63).
* İmzalı personel portalı jetonu (HMAC, `JWT_SECRET_KEY`'den amaca bağlı türetilmiş ayrı anahtar):
  `<personel id>-<sürüm>-<imza>`; sürüm artınca eski bağlantı ölür.
* ICS (izin takvimi: tüm gün; vardiyalar: UTC), CSV (enjeksiyon korumalı), haftalık plan PDF'i, personele
  giden e-postaların 7 dilde metinleri.
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
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from services import randevu as r

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
MODUL = "insan_kaynaklari"
IZIN = "ik"
AJANS_KAPSAMI = "@ajans"
DILLER: Tuple[str, ...] = r.DILLER
SAAT_DILIMI = "Europe/Istanbul"

PERSONEL_DURUMLARI: Tuple[str, ...] = ("aktif", "ayrildi")
#: genel | genc = 18 yaş ve altı | ileri = 50 yaş ve üstü (doğum tarihi TUTULMAZ).
YAS_GRUPLARI: Tuple[str, ...] = ("genel", "genc", "ileri")
IZIN_TURLERI: Tuple[str, ...] = ("yillik", "mazeret", "ucretsiz", "rapor", "dogum", "babalik", "evlilik", "olum", "diger")
#: Gün sayısı ayarlardan düzenlenen yasal izinler.
YASAL_TURLER: Tuple[str, ...] = ("dogum", "babalik", "evlilik", "olum")
#: Doğum izni takvim günüyle (16 hafta), diğerleri çalışma günüyle karşılaştırılır.
TAKVIM_GUNLU: Tuple[str, ...] = ("dogum",)
IZIN_DURUMLARI: Tuple[str, ...] = ("beklemede", "onaylandi", "reddedildi", "iptal")
ETKIN_DURUMLAR: Tuple[str, ...] = ("beklemede", "onaylandi")
VARDIYA_DURUMLARI: Tuple[str, ...] = ("taslak", "yayinda")

#: Pazartesi–Cuma.
VARSAYILAN_CALISMA_GUNLERI: Tuple[int, ...] = (0, 1, 2, 3, 4)
#: 4857 m.53: (en az tamamlanan kıdem yılı, yıllık gün). 1–5 (5 dahil) → 14; 6–14 → 20; 15+ → 26.
VARSAYILAN_KIDEM: Tuple[Tuple[int, int], ...] = ((1, 14), (6, 20), (15, 26))
#: 4857 m.53: 18 yaş ve altı / 50 yaş ve üstü en az 20 gün.
VARSAYILAN_YAS_GUN = 20
#: 4857 m.74 (doğum: 16 hafta = 112 takvim günü), Ek m.2 (babalık 5, evlilik 3, ölüm 3 gün).
VARSAYILAN_YASAL: Dict[str, int] = {"dogum": 112, "babalik": 5, "evlilik": 3, "olum": 3}
VARSAYILAN_DINLENME_SAAT = 11
VARSAYILAN_HAFTALIK_SAAT = 45
VARSAYILAN_PERSONEL_SINIRI = 25

#: 2429 sayılı Kanun — sabit ulusal bayram ve genel tatiller (ay, gün, anahtar, yarım gün mü).
SABIT_TATILLER: Tuple[Tuple[int, int, str, bool], ...] = (
    (1, 1, "yilbasi", False),
    (4, 23, "egemenlik", False),
    (5, 1, "emek", False),
    (5, 19, "genclik", False),
    (7, 15, "demokrasi", False),
    (8, 30, "zafer", False),
    (10, 28, "cumhuriyet_arife", True),
    (10, 29, "cumhuriyet", False),
)
SABIT_TATIL_ADLARI: Dict[str, str] = {
    "yilbasi": "Yılbaşı", "egemenlik": "Ulusal Egemenlik ve Çocuk Bayramı", "emek": "Emek ve Dayanışma Günü",
    "genclik": "Atatürk'ü Anma, Gençlik ve Spor Bayramı", "demokrasi": "Demokrasi ve Milli Birlik Günü",
    "zafer": "Zafer Bayramı", "cumhuriyet_arife": "Cumhuriyet Bayramı arifesi (yarım gün)",
    "cumhuriyet": "Cumhuriyet Bayramı",
}

EN_COK_CSV = 500
EN_COK_TATIL_ARALIGI = 10
EN_COK_IZIN_GUN = 366
EN_COK_KOPYA = 2000
DOSYA_EN_COK_MB = 15
UTC = timezone.utc
_SAAT = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_RENK = re.compile(r"^#[0-9a-fA-F]{6}$")


class IkHatasi(r.RandevuHatasi):
    """Doğrulama/iş kuralı hatası: `{"kod", "alan"?, ...}` gövdesiyle döner."""


TemelHata = r.RandevuHatasi


def simdi() -> datetime:
    """Testler bu fonksiyonu sabit bir ana çeviriyor (bütün zaman hesapları buradan)."""
    return datetime.now(UTC)


def tz():
    return r.saat_dilimi(SAAT_DILIMI)


def bugun() -> date:
    """İşyerinin (İstanbul) bugünü."""
    return simdi().astimezone(tz()).date()


def utc(an: Optional[datetime]) -> Optional[datetime]:
    return r.utc(an)


def iso(an: Optional[datetime]) -> Optional[str]:
    return r.iso(an)


def gun_iso(g: Optional[date]) -> Optional[str]:
    return g.isoformat() if g else None


def yerel_iso(an: Optional[datetime]) -> Optional[str]:
    """Saat dilimsiz yerel an → "YYYY-AA-GGTSS:DD"."""
    return an.strftime("%Y-%m-%dT%H:%M") if an else None


def json_yukle(ham: Any, varsayilan: Any = None) -> Any:
    return r.json_yukle(ham, varsayilan)


def json_yaz(deger: Any) -> str:
    return r.json_yaz(deger)


def site_adresi() -> str:
    return r.site_adresi()


def portal_adresi(jeton: str) -> str:
    return f"{site_adresi()}/personel/{jeton}"


def kapsam_anahtari(hesap: Optional[str]) -> str:
    return hesap or AJANS_KAPSAMI


# ---------------------------------------------------------------------------
# Doğrulayıcılar
# ---------------------------------------------------------------------------
def metin(ham: Any, alan: str, sinir: int, zorunlu: bool = False, cok_satir: bool = False) -> str:
    return r.metin(ham, alan, sinir, zorunlu=zorunlu, cok_satir=cok_satir)


def eposta_duzelt(ham: Any, alan: str = "eposta", zorunlu: bool = False) -> str:
    return r.eposta_duzelt(ham, alan, zorunlu=zorunlu)


def telefon_duzelt(ham: Any, alan: str = "telefon") -> Optional[str]:
    return r.telefon_duzelt(ham, alan)


def tarih_duzelt(ham: Any, alan: str = "tarih", bos_olabilir: bool = False) -> Optional[date]:
    if (ham is None or ham == "") and bos_olabilir:
        return None
    if ham is None or ham == "":
        raise IkHatasi("zorunlu", alan)
    deger = r.tarih_duzelt(ham, alan)
    if deger.year < 1950 or deger.year > 2100:
        raise IkHatasi("tarih_gecersiz", alan)
    return deger


def tam_sayi(ham: Any, alan: str, en_az: int, en_cok: int, bos_olabilir: bool = False) -> Optional[int]:
    return r.tam_sayi(ham, alan, en_az, en_cok, bos_olabilir=bos_olabilir)


def bool_duzelt(ham: Any, alan: str) -> bool:
    return r.bool_duzelt(ham, alan)


def secim(ham: Any, secenekler: Sequence[str], alan: str) -> str:
    deger = str(ham or "").strip()
    if deger not in secenekler:
        raise IkHatasi("secim_gecersiz", alan)
    return deger


def dil_duzelt(ham: Any) -> str:
    deger = str(ham or "tr").strip().lower()[:2]
    return deger if deger in DILLER else "tr"


def renk_duzelt(ham: Any, alan: str = "renk") -> str:
    deger = str(ham or "").strip()
    if not _RENK.match(deger):
        raise IkHatasi("renk_gecersiz", alan)
    return deger.lower()


def saat_duzelt(ham: Any, alan: str) -> str:
    deger = str(ham or "").strip()
    if not _SAAT.match(deger):
        raise IkHatasi("saat_gecersiz", alan)
    return deger


def yarim_sayi(ham: Any, alan: str, en_az: float, en_cok: float) -> float:
    """0,5'in katı gün (devir bakiyesi)."""
    if ham is None or ham == "":
        return 0.0
    if isinstance(ham, bool):
        raise IkHatasi("sayi_gecersiz", alan)
    try:
        deger = float(str(ham).replace(",", ".").strip())
    except ValueError:
        raise IkHatasi("sayi_gecersiz", alan)
    if deger != deger or deger < en_az or deger > en_cok:
        raise IkHatasi("aralik_disi", alan, en_az=en_az, en_cok=en_cok)
    return round(deger * 2) / 2


def calisma_gunleri_duzelt(ham: Any) -> List[int]:
    if not isinstance(ham, list) or not ham:
        raise IkHatasi("calisma_gunu_gerekli", "calisma_gunleri")
    gunler = set()
    for g in ham:
        if isinstance(g, bool) or not isinstance(g, int) or g < 0 or g > 6:
            raise IkHatasi("calisma_gunu_gecersiz", "calisma_gunleri")
        gunler.add(g)
    return sorted(gunler)


def kidem_kurallari_duzelt(ham: Any) -> List[Dict[str, int]]:
    """[{"yil", "gun"}] — en az 1, en çok 6 kural; yıllar artan ve tekil; gün 1–60."""
    if not isinstance(ham, list) or not 1 <= len(ham) <= 6:
        raise IkHatasi("kidem_gecersiz", "kidem_kurallari")
    sonuc: List[Dict[str, int]] = []
    for k in ham:
        if not isinstance(k, dict):
            raise IkHatasi("kidem_gecersiz", "kidem_kurallari")
        yil = tam_sayi(k.get("yil"), "kidem_kurallari", 0, 50)
        gun = tam_sayi(k.get("gun"), "kidem_kurallari", 0, 60)
        sonuc.append({"yil": int(yil), "gun": int(gun)})
    sonuc.sort(key=lambda k: k["yil"])
    if len({k["yil"] for k in sonuc}) != len(sonuc):
        raise IkHatasi("kidem_gecersiz", "kidem_kurallari")
    return sonuc


def yasal_gunler_duzelt(ham: Any) -> Dict[str, int]:
    if not isinstance(ham, dict):
        raise IkHatasi("yasal_gecersiz", "yasal_gunler")
    sonuc = dict(VARSAYILAN_YASAL)
    for tur in YASAL_TURLER:
        if tur in ham:
            sonuc[tur] = int(tam_sayi(ham.get(tur), f"yasal_gunler.{tur}", 0, 400))
    return sonuc


# ---------------------------------------------------------------------------
# Ayarların etkin hâli (satır yoksa varsayılanlar)
# ---------------------------------------------------------------------------
@dataclass
class Kurallar:
    calisma_gunleri: Tuple[int, ...] = VARSAYILAN_CALISMA_GUNLERI
    kidem: Tuple[Tuple[int, int], ...] = VARSAYILAN_KIDEM
    yas_en_az_gun: int = VARSAYILAN_YAS_GUN
    yasal: Optional[Dict[str, int]] = None
    kapali_sabitler: Tuple[str, ...] = ()
    uyari_izinli: bool = True
    uyari_cakisma: bool = True
    uyari_dinlenme: bool = True
    en_az_dinlenme_saat: int = VARSAYILAN_DINLENME_SAAT
    uyari_haftalik: bool = True
    haftalik_en_cok_saat: int = VARSAYILAN_HAFTALIK_SAAT

    def yasal_gun(self, tur: str) -> Optional[int]:
        return (self.yasal or VARSAYILAN_YASAL).get(tur)


def kurallar(a: Any) -> Kurallar:
    if a is None:
        return Kurallar(yasal=dict(VARSAYILAN_YASAL))
    cg = json_yukle(a.calisma_gunleri, None)
    kd = json_yukle(a.kidem_kurallari, None)
    ys = json_yukle(a.yasal_gunler, None)
    ks = json_yukle(a.kapali_sabitler, None)
    return Kurallar(
        calisma_gunleri=tuple(cg) if isinstance(cg, list) and cg else VARSAYILAN_CALISMA_GUNLERI,
        kidem=tuple((int(k["yil"]), int(k["gun"])) for k in kd) if isinstance(kd, list) and kd else VARSAYILAN_KIDEM,
        yas_en_az_gun=int(a.yas_en_az_gun) if a.yas_en_az_gun is not None else VARSAYILAN_YAS_GUN,
        yasal={**VARSAYILAN_YASAL, **(ys if isinstance(ys, dict) else {})},
        kapali_sabitler=tuple(ks) if isinstance(ks, list) else (),
        uyari_izinli=bool(a.uyari_izinli), uyari_cakisma=bool(a.uyari_cakisma), uyari_dinlenme=bool(a.uyari_dinlenme),
        en_az_dinlenme_saat=int(a.en_az_dinlenme_saat or VARSAYILAN_DINLENME_SAAT), uyari_haftalik=bool(a.uyari_haftalik),
        haftalik_en_cok_saat=int(a.haftalik_en_cok_saat or VARSAYILAN_HAFTALIK_SAAT),
    )


# ---------------------------------------------------------------------------
# Resmi tatiller ve izin günü hesabı
# ---------------------------------------------------------------------------
def sabit_anahtari(ay: int, gun: int) -> str:
    return f"{ay:02d}-{gun:02d}"


def sabit_tatiller(yil: int, kapali: Iterable[str] = ()) -> List[Dict[str, Any]]:
    kapali_k = set(kapali or ())
    sonuc = []
    for ay, gun, anahtar, yarim in SABIT_TATILLER:
        k = sabit_anahtari(ay, gun)
        sonuc.append({"tarih": date(yil, ay, gun).isoformat(), "anahtar": anahtar, "sabit": k, "ad": SABIT_TATIL_ADLARI[anahtar],
                      "yarim": yarim, "kaynak": "sabit", "kapali": k in kapali_k})
    return sonuc


def tatil_haritasi(yillar: Iterable[int], kapali: Iterable[str], eklenenler: Iterable[Tuple[date, bool]]) -> Dict[date, float]:
    """Gün → tatil oranı (1 = tam gün tatil, 0,5 = yarım gün). Kullanıcının eklediği gün sabitin üstüne yazar."""
    harita: Dict[date, float] = {}
    for y in set(yillar):
        for t in sabit_tatiller(y, kapali):
            if not t["kapali"]:
                harita[date.fromisoformat(t["tarih"])] = 0.5 if t["yarim"] else 1.0
    for g, yarim in eklenenler:
        harita[g] = 0.5 if yarim else 1.0
    return harita


def gunler(bas: date, bit: date) -> Iterable[date]:
    g = bas
    while g <= bit:
        yield g
        g += timedelta(days=1)


def izin_gunu(bas: date, bit: date, calisma_gunleri: Sequence[int], tatiller: Dict[date, float], yarim_gun: bool = False) -> float:
    """Çalışma günü sayısı: işyerinin çalışma günleri, tam gün tatiller hariç; yarım gün tatil 0,5 düşer.
    `yarim_gun` (yalnız tek günlük izin): o günün değerinin en çok yarısı."""
    calisma = set(calisma_gunleri)
    toplam = 0.0
    for g in gunler(bas, bit):
        if g.weekday() not in calisma:
            continue
        toplam += max(0.0, 1.0 - tatiller.get(g, 0.0))
    if yarim_gun and bas == bit:
        toplam = min(toplam, 0.5)
    return round(toplam * 2) / 2


def takvim_gunu(bas: date, bit: date) -> int:
    return (bit - bas).days + 1


# ---------------------------------------------------------------------------
# Yıllık izin hakkı (4857 m.53) ve bakiye
# ---------------------------------------------------------------------------
def yildonumu(ise_giris: date, n: int) -> date:
    """İşe girişin n. yıl dönümü (29 Şubat → artık olmayan yılda 28 Şubat)."""
    try:
        return ise_giris.replace(year=ise_giris.year + n)
    except ValueError:
        return ise_giris.replace(year=ise_giris.year + n, day=28)


def tamamlanan_yil(ise_giris: date, gun: date) -> int:
    if gun < ise_giris:
        return 0
    n = gun.year - ise_giris.year
    if yildonumu(ise_giris, n) > gun:
        n -= 1
    return max(0, n)


def yillik_hak(yil: int, k: Kurallar, yas_grubu: str = "genel", ozel: Optional[int] = None) -> int:
    """`yil` tamamlanan kıdem yılı olan yıl dönümünde doğan gün sayısı.

    En küçük eşiğin altında (varsayılan: 1 yıl dolmadan) hak doğmaz. 18 yaş ve altı / 50 yaş ve üstü için
    en az `yas_en_az_gun`; sözleşmeyle verilen özel gün kanunun üstündeyse o geçerli."""
    gun = 0
    hak_dogdu = False
    for esik, g in sorted(k.kidem):
        if yil >= esik:
            gun = g
            hak_dogdu = True
    if not hak_dogdu or yil < 1 or gun <= 0:
        return 0
    if yas_grubu in ("genc", "ileri"):
        gun = max(gun, int(k.yas_en_az_gun))
    if ozel:
        gun = max(gun, int(ozel))
    return int(gun)


def hakedisler(ise_giris: date, baslangic: date, son: date, k: Kurallar, yas_grubu: str = "genel",
               ozel: Optional[int] = None) -> List[Dict[str, Any]]:
    """[baslangic, son] aralığındaki yıl dönümleri (n ≥ 1) ve o gün doğan hak."""
    sonuc = []
    n = 1
    while n < 80:
        g = yildonumu(ise_giris, n)
        if g > son:
            break
        if g >= baslangic:
            sonuc.append({"tarih": g.isoformat(), "yil": n, "gun": yillik_hak(n, k, yas_grubu, ozel)})
        n += 1
    return sonuc


def bakiye_hesapla(p: Any, k: Kurallar, onayli_yillik: Iterable[Tuple[date, float]], bekleyen_yillik: Iterable[Tuple[date, float]],
                   gun: Optional[date] = None) -> Dict[str, Any]:
    """Yıllık izin bakiyesi.

    devir (devir tarihinin BAŞINDAKİ kalan) + devir tarihinden (dahil) bugüne kadar doğan haklar
    − devir tarihinden (dahil) başlayan onaylı yıllık izinler. Ayrılan personelde haklar ayrılış gününde durur."""
    gun = gun or bugun()
    baslangic = p.devir_tarihi or p.ise_giris
    son = min(gun, p.ayrilis_tarihi) if p.durum == "ayrildi" and p.ayrilis_tarihi else gun
    hd = hakedisler(p.ise_giris, baslangic, son, k, p.yas_grubu or "genel", p.yillik_gun_ozel)
    kazanilan = float(sum(h["gun"] for h in hd))
    kullanilan = float(sum(g for b, g in onayli_yillik if b >= baslangic))
    bekleyen = float(sum(g for b, g in bekleyen_yillik if b >= baslangic))
    devir = float(p.devir_gun or 0)
    kalan = devir + kazanilan - kullanilan
    kidem = tamamlanan_yil(p.ise_giris, son)
    sonraki = None
    if p.durum != "ayrildi":
        n = kidem + 1
        sg = yildonumu(p.ise_giris, n)
        sonraki = {"tarih": sg.isoformat(), "yil": n, "gun": yillik_hak(n, k, p.yas_grubu or "genel", p.yillik_gun_ozel)}
    return {
        "devir": devir, "devir_tarihi": baslangic.isoformat(), "kazanilan": kazanilan, "kullanilan": kullanilan,
        "bekleyen": bekleyen, "kalan": kalan, "kullanilabilir": kalan - bekleyen, "kidem_yil": kidem,
        "yillik_hak": yillik_hak(max(kidem, 1), k, p.yas_grubu or "genel", p.yillik_gun_ozel) if kidem >= 1 else 0,
        "sonraki": sonraki, "hakedisler": hd[-10:],
    }


# ---------------------------------------------------------------------------
# Vardiyalar
# ---------------------------------------------------------------------------
def hafta_basi(g: date) -> date:
    return g - timedelta(days=g.weekday())


def vardiya_anlari(tarih: date, bas: str, bit: str) -> Tuple[datetime, datetime]:
    """"SS:DD" → yerel (saat dilimsiz) başlangıç/bitiş; bitiş ≤ başlangıçsa ertesi gün (gece vardiyası)."""
    b = datetime.combine(tarih, time(int(bas[:2]), int(bas[3:])))
    e = datetime.combine(tarih, time(int(bit[:2]), int(bit[3:])))
    if e <= b:
        e += timedelta(days=1)
    return b, e


def net_dakika(bas: datetime, bit: datetime, mola_dk: int) -> int:
    return max(0, int((bit - bas).total_seconds() // 60) - int(mola_dk or 0))


def saat_metni(an: datetime) -> str:
    return an.strftime("%H:%M")


@dataclass
class VardiyaOzeti:
    id: int
    personel_id: int
    bas: datetime
    bit: datetime
    mola_dk: int = 0


def vardiya_uyarilari(vardiyalar: Sequence[VardiyaOzeti], izinli: Dict[int, Dict[date, str]], k: Kurallar,
                      hafta_bas: date) -> List[Dict[str, Any]]:
    """Haftanın planı için uyarılar (ENGELLEMEZ). `vardiyalar` haftadan bir gün öncesini de içerebilir
    (hafta başındaki dinlenme denetimi için); uyarılar yalnız bu haftanın vardiyalarına yazılır.
    `izinli`: personel → {gün: izin türü} (onaylı izinler)."""
    hafta_bit = hafta_bas + timedelta(days=7)
    kisiye: Dict[int, List[VardiyaOzeti]] = {}
    for v in vardiyalar:
        kisiye.setdefault(v.personel_id, []).append(v)
    uyarilar: List[Dict[str, Any]] = []

    def bu_hafta(v: VardiyaOzeti) -> bool:
        return hafta_bas <= v.bas.date() < hafta_bit

    for pid, liste in kisiye.items():
        liste.sort(key=lambda v: (v.bas, v.id))
        if k.uyari_izinli:
            gunler_ = izinli.get(pid) or {}
            for v in liste:
                if not bu_hafta(v):
                    continue
                gun = v.bas.date()
                # Gece vardiyasının ertesi güne taşan kısmı da (bitiş günü) izin günüyse uyarı.
                tasma = v.bit.date() if v.bit.time() > time(0, 0) else (v.bit - timedelta(minutes=1)).date()
                for g in {gun, tasma}:
                    if g in gunler_:
                        uyarilar.append({"tur": "izinli", "personel_id": pid, "vardiya_id": v.id, "tarih": g.isoformat(),
                                         "izin_turu": gunler_[g]})
                        break
        for i, v in enumerate(liste):
            if i == 0:
                continue
            o = liste[i - 1]
            if not (bu_hafta(v) or bu_hafta(o)):
                continue
            if k.uyari_cakisma and v.bas < o.bit:
                uyarilar.append({"tur": "cakisma", "personel_id": pid, "vardiya_id": v.id, "diger_id": o.id,
                                 "tarih": v.bas.date().isoformat()})
            elif k.uyari_dinlenme and v.bas >= o.bit:
                ara = (v.bas - o.bit).total_seconds() / 3600
                if ara < k.en_az_dinlenme_saat and bu_hafta(v):
                    uyarilar.append({"tur": "dinlenme", "personel_id": pid, "vardiya_id": v.id, "diger_id": o.id,
                                     "tarih": v.bas.date().isoformat(), "saat": round(ara, 1), "en_az": k.en_az_dinlenme_saat})
        if k.uyari_haftalik:
            dk = sum(net_dakika(v.bas, v.bit, v.mola_dk) for v in liste if bu_hafta(v))
            if dk > k.haftalik_en_cok_saat * 60:
                uyarilar.append({"tur": "haftalik", "personel_id": pid, "saat": round(dk / 60, 1),
                                 "en_cok": k.haftalik_en_cok_saat})
    return uyarilar


# ---------------------------------------------------------------------------
# İmzalı personel portalı jetonu
# ---------------------------------------------------------------------------
_YEDEK: Optional[bytes] = None


def _anahtar() -> bytes:
    global _YEDEK
    gizli = os.environ.get("JWT_SECRET_KEY") or ""
    if not gizli:
        if _YEDEK is None:
            _YEDEK = secrets.token_bytes(32)
        return _YEDEK
    return hashlib.sha256(("ik-personel:" + gizli).encode()).digest()


def _imza(mesaj: str) -> str:
    return hmac.new(_anahtar(), mesaj.encode(), hashlib.sha256).hexdigest()[:32]


_JETON = re.compile(r"^(\d{1,12})-(\d{1,6})-([0-9a-f]{32})$")


def portal_jetonu(personel_id: int, surum: int) -> str:
    return f"{int(personel_id)}-{int(surum)}-{_imza(f'personel|{int(personel_id)}|{int(surum)}')}"


def jeton_parcala(jeton: Any) -> Optional[Tuple[int, int]]:
    m = _JETON.match(str(jeton or ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def portal_jetonu_gecerli_mi(jeton: Any, personel_id: int, surum: int) -> bool:
    return hmac.compare_digest(str(jeton or ""), portal_jetonu(personel_id, surum))


# ---------------------------------------------------------------------------
# ICS (RFC 5545)
# ---------------------------------------------------------------------------
def _ics_alan() -> str:
    return (site_adresi().split("://", 1)[-1].split("/", 1)[0] or "mehmetkuru.dev").split(":", 1)[0]


def _ics_basi(ad: str) -> List[str]:
    from services import dinamik_qr as qr

    return ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//mehmetkuru.dev//IK//TR", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
            f"X-WR-CALNAME:{qr._kacis(ad)}"]


def _ics_sonu(satirlar: List[str]) -> str:
    from services import dinamik_qr as qr

    satirlar.append("END:VCALENDAR")
    return "\r\n".join(qr._katla(s) for s in satirlar) + "\r\n"


def yerelden_utc(an: datetime) -> datetime:
    return an.replace(tzinfo=tz()).astimezone(UTC)


def vardiya_ics(ad: str, vardiyalar: Sequence[Tuple[int, datetime, datetime, str]], an: Optional[datetime] = None) -> str:
    """(kimlik, yerel başlangıç, yerel bitiş, başlık) → VEVENT (UTC). UID kalıcı."""
    from services import dinamik_qr as qr

    an = an or simdi()
    alan = _ics_alan()
    satirlar = _ics_basi(ad)
    for vid, bas, bit, baslik in vardiyalar:
        satirlar += ["BEGIN:VEVENT", f"UID:ik-vardiya-{vid}@{alan}", "DTSTAMP:" + utc(an).strftime("%Y%m%dT%H%M%SZ"),
                     "DTSTART:" + yerelden_utc(bas).strftime("%Y%m%dT%H%M%SZ"),
                     "DTEND:" + yerelden_utc(bit).strftime("%Y%m%dT%H%M%SZ"),
                     f"SUMMARY:{qr._kacis(baslik)}", "STATUS:CONFIRMED", "TRANSP:OPAQUE", "END:VEVENT"]
    return _ics_sonu(satirlar)


def izin_ics(ad: str, izinler: Sequence[Tuple[int, date, date, str]], an: Optional[datetime] = None) -> str:
    """(kimlik, başlangıç, bitiş (dahil), başlık) → tüm gün VEVENT (DTEND bir gün sonrası)."""
    from services import dinamik_qr as qr

    an = an or simdi()
    alan = _ics_alan()
    satirlar = _ics_basi(ad)
    for iid, bas, bit, baslik in izinler:
        satirlar += ["BEGIN:VEVENT", f"UID:ik-izin-{iid}@{alan}", "DTSTAMP:" + utc(an).strftime("%Y%m%dT%H%M%SZ"),
                     "DTSTART;VALUE=DATE:" + bas.strftime("%Y%m%d"),
                     "DTEND;VALUE=DATE:" + (bit + timedelta(days=1)).strftime("%Y%m%d"),
                     f"SUMMARY:{qr._kacis(baslik)}", "STATUS:CONFIRMED", "TRANSP:TRANSPARENT", "END:VEVENT"]
    return _ics_sonu(satirlar)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
def csv_hucre(deger: Any) -> Any:
    """Tablo programında formül olarak çalışmasın (CSV enjeksiyonu)."""
    if isinstance(deger, str) and deger[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + deger
    return deger


def csv_metni(basliklar: Sequence[str], satirlar: Iterable[Sequence[Any]]) -> str:
    cikti = io.StringIO()
    w = csv.writer(cikti)
    w.writerow(basliklar)
    for s in satirlar:
        w.writerow([csv_hucre(x) for x in s])
    return "﻿" + cikti.getvalue()


PERSONEL_CSV_ALANLARI: Tuple[str, ...] = ("ad", "eposta", "telefon", "gorev", "departman", "ise_giris", "durum",
                                          "ayrilis_tarihi", "yas_grubu", "devir_gun", "devir_tarihi", "notlar")

_CSV_BASLIKLAR = {
    "ad": "ad", "ad soyad": "ad", "adsoyad": "ad", "isim": "ad", "name": "ad", "full name": "ad", "personel": "ad",
    "eposta": "eposta", "e-posta": "eposta", "email": "eposta", "e-mail": "eposta", "mail": "eposta",
    "telefon": "telefon", "tel": "telefon", "phone": "telefon", "gsm": "telefon",
    "gorev": "gorev", "unvan": "gorev", "pozisyon": "gorev", "title": "gorev", "position": "gorev", "role": "gorev",
    "departman": "departman", "bolum": "departman", "department": "departman",
    "ise giris": "ise_giris", "ise giris tarihi": "ise_giris", "giris tarihi": "ise_giris", "start date": "ise_giris",
    "hire date": "ise_giris", "ise_giris": "ise_giris",
    "durum": "durum", "status": "durum",
    "ayrilis": "ayrilis_tarihi", "ayrilis tarihi": "ayrilis_tarihi", "end date": "ayrilis_tarihi",
    "yas grubu": "yas_grubu", "age group": "yas_grubu",
    "devir": "devir_gun", "devir gun": "devir_gun", "izin bakiyesi": "devir_gun", "kalan izin": "devir_gun",
    "leave balance": "devir_gun", "devir tarihi": "devir_tarihi", "balance date": "devir_tarihi",
    "not": "notlar", "notlar": "notlar", "notes": "notlar",
}


def _baslik_normal(b: str) -> str:
    b = unicodedata.normalize("NFKD", (b or "").strip().lower().replace("ı", "i"))
    b = "".join(c for c in b if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", b.replace("_", " ")).strip()


def csv_oku(metin_: str) -> List[Dict[str, str]]:
    """Başlıklı CSV (virgül ya da noktalı virgül) → alan adlarına çevrilmiş satırlar (en çok `EN_COK_CSV`)."""
    metin_ = (metin_ or "").lstrip("﻿")
    if not metin_.strip():
        raise IkHatasi("csv_bos", "csv")
    ilk = metin_.splitlines()[0] if metin_.splitlines() else ""
    ayirici = ";" if ilk.count(";") > ilk.count(",") else ","
    okuyucu = csv.reader(io.StringIO(metin_), delimiter=ayirici)
    try:
        satirlar = list(okuyucu)
    except csv.Error:
        raise IkHatasi("csv_gecersiz", "csv")
    if not satirlar:
        raise IkHatasi("csv_bos", "csv")
    basliklar = [_CSV_BASLIKLAR.get(_baslik_normal(b)) for b in satirlar[0]]
    if "ad" not in basliklar:
        raise IkHatasi("csv_baslik", "csv")
    veri = [s for s in satirlar[1:] if any((h or "").strip() for h in s)]
    if len(veri) > EN_COK_CSV:
        raise IkHatasi("csv_cok", "csv", en_cok=EN_COK_CSV)
    sonuc = []
    for s in veri:
        d: Dict[str, str] = {}
        for i, alan in enumerate(basliklar):
            if alan and i < len(s):
                d[alan] = (s[i] or "").strip()
        sonuc.append(d)
    return sonuc


def csv_tarih(ham: str, alan: str, bos_olabilir: bool = True) -> Optional[date]:
    """2026-01-31, 31.01.2026 ya da 31/01/2026."""
    h = (ham or "").strip()
    if not h:
        if bos_olabilir:
            return None
        raise IkHatasi("zorunlu", alan)
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", h)
    if m:
        try:
            return tarih_duzelt(f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}", alan)
        except IkHatasi:
            raise IkHatasi("tarih_gecersiz", alan)
    return tarih_duzelt(h, alan)


# ---------------------------------------------------------------------------
# Haftalık plan PDF'i (ReportLab; Faz 3T yazı tipi)
# ---------------------------------------------------------------------------
PDF_ETIKET: Dict[str, Dict[str, Any]] = {
    "tr": {"baslik": "Haftalık vardiya planı", "personel": "Personel", "toplam": "Toplam",
           "gunler": ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"], "taslak": "taslak", "izin": "İzin",
           "saat_kisa": "s",
           "not": "Bilgilendirme amaçlıdır. Saatler molasız toplam değil, mola düşülmüş net süredir."},
    "en": {"baslik": "Weekly shift plan", "personel": "Employee", "toplam": "Total",
           "gunler": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "taslak": "draft", "izin": "Leave",
           "saat_kisa": "h", "not": "For information only. Hours are net of breaks."},
    "de": {"baslik": "Wöchentlicher Schichtplan", "personel": "Mitarbeiter", "toplam": "Summe",
           "gunler": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"], "taslak": "Entwurf", "izin": "Urlaub",
           "saat_kisa": "Std.", "not": "Nur zur Information. Stunden ohne Pausen (netto)."},
    "ru": {"baslik": "Недельный график смен", "personel": "Сотрудник", "toplam": "Итого",
           "gunler": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"], "taslak": "черновик", "izin": "Отпуск",
           "saat_kisa": "ч", "not": "Для информации. Часы указаны за вычетом перерывов."},
    "zh": {"baslik": "每周排班表", "personel": "员工", "toplam": "合计",
           "gunler": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"], "taslak": "草稿", "izin": "休假",
           "saat_kisa": "小时", "not": "仅供参考。工时为扣除休息后的净时长。"},
    "hi": {"baslik": "साप्ताहिक शिफ्ट योजना", "personel": "कर्मचारी", "toplam": "कुल",
           "gunler": ["सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "रवि"], "taslak": "मसौदा", "izin": "अवकाश",
           "saat_kisa": "घं", "not": "केवल जानकारी के लिए। घंटे विराम घटाकर शुद्ध समय हैं।"},
    "ar": {"baslik": "جدول المناوبات الأسبوعي", "personel": "الموظف", "toplam": "الإجمالي",
           "gunler": ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"], "taslak": "مسودة",
           "izin": "إجازة", "saat_kisa": "س", "not": "للعلم فقط. الساعات صافية بعد خصم فترات الراحة."},
}


def pdf_dili(dil: Optional[str]) -> str:
    d = (dil or "tr")[:2].lower()
    return d if d in PDF_ETIKET else "en"


def plan_pdf(*, firma: str, hafta_bas: date, satirlar: Sequence[Dict[str, Any]], dil: str = "tr") -> bytes:
    """`satirlar`: [{"ad", "gunler": [7 × [metin, ...]], "toplam_saat"}]. Yatay A4 tablo."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle
    from services import pdf_belge as pb
    from services.pdf_yazi import Paragraf as Paragraph  # çok dilli paragraf (Faz 7K)

    dil = pdf_dili(dil)
    e = PDF_ETIKET[dil]
    pb.fontlari_kaydet()
    kucuk = ParagraphStyle("ik_k", fontName=pb.YAZI, fontSize=7.5, leading=9.5)
    govde = ParagraphStyle("ik_g", fontName=pb.YAZI, fontSize=8.5, leading=11)
    baslik = ParagraphStyle("ik_b", fontName=pb.KALIN, fontSize=14, leading=18)

    def m(x: Any) -> str:
        return pb._metin(x)  # noqa: SLF001

    bit = hafta_bas + timedelta(days=6)
    parcalar: List[Any] = [Paragraph(m(f"{e['baslik']} — {firma}" if firma else e["baslik"]), baslik),
                           Paragraph(m(f"{hafta_bas.strftime('%d.%m.%Y')} – {bit.strftime('%d.%m.%Y')}"), govde), Spacer(1, 4 * mm)]
    ust = [Paragraph(f"<b>{m(e['personel'])}</b>", govde)]
    for i in range(7):
        g = hafta_bas + timedelta(days=i)
        ust.append(Paragraph(f"<b>{m(e['gunler'][i])}</b> {g.strftime('%d.%m')}", govde))
    ust.append(Paragraph(f"<b>{m(e['toplam'])}</b>", govde))
    tablo = [ust]
    for s in satirlar:
        satir = [Paragraph(m(s.get("ad") or "—"), govde)]
        for hucre in s.get("gunler") or [[] for _ in range(7)]:
            satir.append(Paragraph("<br/>".join(m(x) for x in hucre) or "—", kucuk))
        satir.append(Paragraph(m(f"{s.get('toplam_saat', 0):g} {e['saat_kisa']}"), govde))
        tablo.append(satir)
    genislik = landscape(A4)[0] - 24 * mm
    sutun = [genislik * 0.16] + [genislik * 0.11] * 7 + [genislik * 0.07]
    t = Table(tablo, colWidths=sutun, repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c7c7d1")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efeaff")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    parcalar += [t, Spacer(1, 4 * mm), Paragraph(m(e["not"]), kucuk)]
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm,
                            bottomMargin=12 * mm, title=e["baslik"], author=firma or "mehmetkuru.dev")
    doc.build(parcalar)
    return tampon.getvalue()


# ---------------------------------------------------------------------------
# Personele giden e-postalar (7 dil; bilgilendirme)
# ---------------------------------------------------------------------------
METINLER: Dict[str, Dict[str, str]] = {
    "tr": {
        "onay_konu": "İzin talebiniz onaylandı", "ret_konu": "İzin talebiniz reddedildi",
        "iptal_konu": "İzniniz iptal edildi", "vardiya_konu": "Vardiya planınız yayınlandı",
        "baglanti_konu": "Personel sayfanız", "merhaba": "Merhaba {ad},",
        "onay": "{tur} talebiniz ({aralik}, {gun} iş günü) onaylandı.",
        "ret": "{tur} talebiniz ({aralik}) reddedildi.", "iptal": "{tur} kaydınız ({aralik}) iptal edildi.",
        "not": "Not: {not_}", "vardiya": "{hafta} haftasının vardiya planı yayınlandı. Vardiyalarınız:",
        "baglanti": "İzin bakiyenizi, izin geçmişinizi ve yayınlanan vardiyalarınızı aşağıdaki kişisel bağlantıdan "
                    "görebilir, izin talebi gönderebilirsiniz. Bağlantıyı kimseyle paylaşmayın.",
        "sayfa": "Kişisel sayfanız: {adres}", "imza": "{firma}",
        "turler": "yillik=Yıllık izin|mazeret=Mazeret izni|ucretsiz=Ücretsiz izin|rapor=Rapor|dogum=Doğum izni|"
                  "babalik=Babalık izni|evlilik=Evlilik izni|olum=Ölüm izni|diger=Diğer izin",
    },
    "en": {
        "onay_konu": "Your leave request was approved", "ret_konu": "Your leave request was declined",
        "iptal_konu": "Your leave was cancelled", "vardiya_konu": "Your shift schedule is published",
        "baglanti_konu": "Your employee page", "merhaba": "Hello {ad},",
        "onay": "Your {tur} request ({aralik}, {gun} working days) was approved.",
        "ret": "Your {tur} request ({aralik}) was declined.", "iptal": "Your {tur} ({aralik}) was cancelled.",
        "not": "Note: {not_}", "vardiya": "The shift schedule for the week of {hafta} is published. Your shifts:",
        "baglanti": "You can see your leave balance, leave history and published shifts and send leave requests from "
                    "the personal link below. Do not share the link.",
        "sayfa": "Your personal page: {adres}", "imza": "{firma}",
        "turler": "yillik=annual leave|mazeret=compassionate leave|ucretsiz=unpaid leave|rapor=sick leave|dogum=maternity leave|"
                  "babalik=paternity leave|evlilik=marriage leave|olum=bereavement leave|diger=other leave",
    },
    "de": {
        "onay_konu": "Ihr Urlaubsantrag wurde genehmigt", "ret_konu": "Ihr Urlaubsantrag wurde abgelehnt",
        "iptal_konu": "Ihr Urlaub wurde storniert", "vardiya_konu": "Ihr Schichtplan wurde veröffentlicht",
        "baglanti_konu": "Ihre Mitarbeiterseite", "merhaba": "Hallo {ad},",
        "onay": "Ihr Antrag auf {tur} ({aralik}, {gun} Arbeitstage) wurde genehmigt.",
        "ret": "Ihr Antrag auf {tur} ({aralik}) wurde abgelehnt.", "iptal": "Ihr Eintrag {tur} ({aralik}) wurde storniert.",
        "not": "Hinweis: {not_}", "vardiya": "Der Schichtplan für die Woche ab {hafta} ist veröffentlicht. Ihre Schichten:",
        "baglanti": "Über den persönlichen Link unten sehen Sie Ihr Urlaubskonto, Ihren Urlaubsverlauf und veröffentlichte "
                    "Schichten und können Urlaub beantragen. Teilen Sie den Link nicht.",
        "sayfa": "Ihre persönliche Seite: {adres}", "imza": "{firma}",
        "turler": "yillik=Jahresurlaub|mazeret=Sonderurlaub|ucretsiz=unbezahlter Urlaub|rapor=Krankmeldung|dogum=Mutterschaftsurlaub|"
                  "babalik=Vaterschaftsurlaub|evlilik=Hochzeitsurlaub|olum=Trauerurlaub|diger=sonstiger Urlaub",
    },
    "ru": {
        "onay_konu": "Ваша заявка на отпуск одобрена", "ret_konu": "Ваша заявка на отпуск отклонена",
        "iptal_konu": "Ваш отпуск отменён", "vardiya_konu": "Ваш график смен опубликован",
        "baglanti_konu": "Ваша страница сотрудника", "merhaba": "Здравствуйте, {ad}!",
        "onay": "Ваша заявка ({tur}, {aralik}, рабочих дней: {gun}) одобрена.",
        "ret": "Ваша заявка ({tur}, {aralik}) отклонена.", "iptal": "Запись ({tur}, {aralik}) отменена.",
        "not": "Примечание: {not_}", "vardiya": "Опубликован график смен на неделю с {hafta}. Ваши смены:",
        "baglanti": "По личной ссылке ниже вы можете посмотреть остаток отпуска, историю отпусков и опубликованные смены, "
                    "а также подать заявку на отпуск. Не передавайте ссылку другим.",
        "sayfa": "Ваша личная страница: {adres}", "imza": "{firma}",
        "turler": "yillik=ежегодный отпуск|mazeret=отгул по семейным обстоятельствам|ucretsiz=отпуск без сохранения зарплаты|"
                  "rapor=больничный|dogum=отпуск по беременности и родам|babalik=отпуск отцу|evlilik=отпуск по случаю брака|"
                  "olum=отпуск в связи со смертью близкого|diger=другой отпуск",
    },
    "zh": {
        "onay_konu": "您的请假申请已批准", "ret_konu": "您的请假申请未获批准", "iptal_konu": "您的假期已取消",
        "vardiya_konu": "您的排班已发布", "baglanti_konu": "您的员工页面", "merhaba": "{ad}，您好：",
        "onay": "您的{tur}申请（{aralik}，{gun} 个工作日）已批准。", "ret": "您的{tur}申请（{aralik}）未获批准。",
        "iptal": "您的{tur}记录（{aralik}）已取消。", "not": "备注：{not_}", "vardiya": "{hafta} 起一周的排班已发布。您的班次：",
        "baglanti": "通过下面的个人链接，您可以查看假期余额、请假记录和已发布的班次，并提交请假申请。请勿与他人分享此链接。",
        "sayfa": "您的个人页面：{adres}", "imza": "{firma}",
        "turler": "yillik=年假|mazeret=事假|ucretsiz=无薪假|rapor=病假|dogum=产假|babalik=陪产假|evlilik=婚假|olum=丧假|diger=其他假期",
    },
    "hi": {
        "onay_konu": "आपका अवकाश अनुरोध स्वीकृत हुआ", "ret_konu": "आपका अवकाश अनुरोध अस्वीकृत हुआ",
        "iptal_konu": "आपका अवकाश रद्द किया गया", "vardiya_konu": "आपकी शिफ्ट योजना प्रकाशित हुई",
        "baglanti_konu": "आपका कर्मचारी पृष्ठ", "merhaba": "नमस्ते {ad},",
        "onay": "आपका {tur} अनुरोध ({aralik}, {gun} कार्य दिवस) स्वीकृत हुआ।", "ret": "आपका {tur} अनुरोध ({aralik}) अस्वीकृत हुआ।",
        "iptal": "आपका {tur} ({aralik}) रद्द किया गया।", "not": "टिप्पणी: {not_}",
        "vardiya": "{hafta} से शुरू होने वाले सप्ताह की शिफ्ट योजना प्रकाशित हुई। आपकी शिफ्टें:",
        "baglanti": "नीचे दिए गए व्यक्तिगत लिंक से आप अपना अवकाश शेष, अवकाश इतिहास और प्रकाशित शिफ्टें देख सकते हैं और अवकाश "
                    "अनुरोध भेज सकते हैं। यह लिंक किसी से साझा न करें।",
        "sayfa": "आपका व्यक्तिगत पृष्ठ: {adres}", "imza": "{firma}",
        "turler": "yillik=वार्षिक अवकाश|mazeret=आकस्मिक अवकाश|ucretsiz=अवैतनिक अवकाश|rapor=चिकित्सा अवकाश|dogum=मातृत्व अवकाश|"
                  "babalik=पितृत्व अवकाश|evlilik=विवाह अवकाश|olum=शोक अवकाश|diger=अन्य अवकाश",
    },
    "ar": {
        "onay_konu": "تمت الموافقة على طلب إجازتك", "ret_konu": "تم رفض طلب إجازتك", "iptal_konu": "تم إلغاء إجازتك",
        "vardiya_konu": "تم نشر جدول مناوباتك", "baglanti_konu": "صفحتك كموظف", "merhaba": "مرحبًا {ad}،",
        "onay": "تمت الموافقة على طلب {tur} ({aralik}، {gun} يوم عمل).", "ret": "تم رفض طلب {tur} ({aralik}).",
        "iptal": "تم إلغاء {tur} ({aralik}).", "not": "ملاحظة: {not_}",
        "vardiya": "تم نشر جدول المناوبات للأسبوع الذي يبدأ في {hafta}. مناوباتك:",
        "baglanti": "يمكنك من الرابط الشخصي أدناه رؤية رصيد إجازاتك وسجلها والمناوبات المنشورة وإرسال طلب إجازة. لا تشارك الرابط مع أحد.",
        "sayfa": "صفحتك الشخصية: {adres}", "imza": "{firma}",
        "turler": "yillik=الإجازة السنوية|mazeret=إجازة ظرفية|ucretsiz=إجازة غير مدفوعة|rapor=إجازة مرضية|dogum=إجازة أمومة|"
                  "babalik=إجازة أبوة|evlilik=إجازة زواج|olum=إجازة وفاة|diger=إجازة أخرى",
    },
}


def metinler(dil: str) -> Dict[str, str]:
    return METINLER.get(dil) or METINLER["tr"]


def tur_adi(tur: str, dil: str = "tr") -> str:
    eslesme = dict(x.split("=", 1) for x in metinler(dil)["turler"].split("|"))
    return eslesme.get(tur, tur)


def aralik_metni(bas: date, bit: date) -> str:
    return bas.strftime("%d.%m.%Y") if bas == bit else f"{bas.strftime('%d.%m.%Y')} – {bit.strftime('%d.%m.%Y')}"


def gun_metni(gun: float) -> str:
    return f"{gun:g}".replace(".", ",")


__all__ = [
    "MODUL", "IZIN", "IkHatasi", "TemelHata", "Kurallar", "kurallar", "izin_gunu", "tatil_haritasi", "sabit_tatiller",
    "yillik_hak", "bakiye_hesapla", "vardiya_uyarilari", "portal_jetonu", "vardiya_ics", "izin_ics", "plan_pdf",
]
