"""Faz 6M — Ön muhasebe: kurallar ve yardımcılar (veritabanına dokunmayan her şey).

Router `routers/muhasebe.py`, veritabanı işleri `services/muhasebe_kayit.py`. Burada:

* Doğrulayıcılar: tutar → kuruş (yarım yukarı), KDV hesabı (tam sayı aritmetiği), IBAN (yalnız BİÇİM: ülke
  kodu + 2 denetim hanesi + mod-97; TR'de 26 karakter; saklanır ama uçlar YALNIZ son 4 haneyi maskeli döner),
  kart son 4 hane, vergi no (10/11 hane), etiketler. HESAP NUMARASI ve KART NUMARASI alınmaz/saklanmaz.
* Varsayılan Türkçe kategori seti (gelir + gider; ad değiştirilebilir, ön yüz değiştirilmemiş adı çevirir).
* Tekrarlayan kayıt dönemleri (haftalık / aylık / 3 aylık / yıllık; ay sonu kırpılır: 31 Ocak → 28/29 Şubat
  → 31 Mart).
* Cari yaşlandırma: açık borç kalemleri (vadeli satış, cariye ödeme, artı açılış) ile kapatan kalemler (tahsilat,
  vadeli alış, eksi açılış) FIFO eşlenir; kalan tutar vadeden (yoksa kayıt tarihinden) rapor gününe kadar geçen
  güne göre kovaya düşer: vadesi gelmemiş | 0–30 | 31–60 | 61–90 | 90+ (sınırlar dahil: 30. gün "0–30",
  31. gün "31–60", 90. gün "61–90", 91. gün "90+").
* CSV: dışa aktarma (Excel Türkçe: BOM + noktalı virgül, formül enjeksiyonu kaçışı) ve banka ekstresi içe
  aktarma (sütun eşleme, tarih biçimi, ondalık ayırıcı, tek tutar sütunu ya da ayrı giriş/çıkış sütunları).
* PDF: cari ekstre ve hareket listesi (ReportLab; Faz 3T altyapısı). Yazı tipi Latin: tr / en / de; diğer
  dillerde İngilizce.

KDV özeti BİLGİLENDİRME amaçlıdır, beyanname yerine geçmez (arayüzde ve PDF'te not).
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from services import randevu as r

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
MODUL = "on_muhasebe"
#: Tam yetki (kayıt, ayar, içe aktarma).
IZIN = "muhasebe"
#: Yalnız rapor (özet, bütçe durumu, yaşlandırma, raporlar ve CSV'leri) — örn. mali müşavir. Hareket/cari ayrıntısı yok.
IZIN_OKUR = "muhasebe_okur"
AJANS_KAPSAMI = "@ajans"
SAAT_DILIMI = "Europe/Istanbul"
UTC = timezone.utc

#: `pos`: POS / sanal POS hesabı (iyzico, PayTR, Lemon Squeezy, Shopier bakiyesi…) — banka hesabına aktarım virmandır.
HESAP_TURLERI: Tuple[str, ...] = ("kasa", "banka", "kredi_karti", "pos")
HAREKET_TURLERI: Tuple[str, ...] = ("gelir", "gider", "tahsilat", "odeme", "virman")
KATEGORI_TURLERI: Tuple[str, ...] = ("gelir", "gider")
CARI_TURLERI: Tuple[str, ...] = ("musteri", "tedarikci", "her_ikisi")
PARA_BIRIMLERI: Tuple[str, ...] = ("TRY", "USD", "EUR", "GBP")
#: Türkiye KDV oranları (yüzde).
KDV_ORANLARI: Tuple[int, ...] = (0, 1, 10, 20)
PERIYOTLAR: Tuple[str, ...] = ("haftalik", "aylik", "uc_aylik", "yillik")
#: Elle düzenlenebilen kayıt kaynakları; geri kalanı otomatik yansıma (düzenlenmez/silinmez).
ELLE_KAYNAKLAR: Tuple[str, ...] = ("manuel", "tekrar", "csv")
OTOMATIK_KAYNAKLAR: Tuple[str, ...] = ("odeme", "fatura", "pos", "hukuk", "saha")
KAYNAKLAR: Tuple[str, ...] = ELLE_KAYNAKLAR + OTOMATIK_KAYNAKLAR
#: Otomatik aktarma ayarı kaynakları: ajansta müşterilerden gelen ödemeler (Lemon Squeezy / Shopier / havale / elden —
#: ödeme kayıtları); müşteride ajansa ödediği faturalar (gider) ve kendi modülleri.
AJANS_AKTARIMLARI: Tuple[str, ...] = ("odeme",)
MUSTERI_AKTARIMLARI: Tuple[str, ...] = ("odeme", "pos", "hukuk", "saha")
#: Kaynak başına "onay" varsayılanı: True → her kayıt ÖNERİ olarak gelir, kullanıcı onaylayınca deftere yazılır.
#: Ödeme sağlayıcısının doğruladığı tahsilat (ödeme kaydı) ve kapanmış kasa oturumu (Z raporu) kesin para hareketi:
#: otomatik. Hukuk masrafı (avanstan mı, kişisel mi?) ve saha işi (tahsil edildi mi, tutar kesin mi?) yoruma açık:
#: öneri. Ödeme kaydı OLMADAN "ödendi" işaretlenen fatura (`fatura` alt kaynağı) ayardan bağımsız HER ZAMAN öneri.
AKTARIM_ONAY_VARSAYILAN: Dict[str, bool] = {"odeme": False, "pos": False, "hukuk": True, "saha": True}
HEP_ONERI_KAYNAKLARI: Tuple[str, ...] = ("fatura",)
ONERI_DURUMLARI: Tuple[str, ...] = ("bekliyor", "yoksayildi")
#: Çevrim içi ödeme sağlayıcıları (para önce sağlayıcı bakiyesine düşer → varsa POS/sanal POS hesabına).
CEVRIMICI_SAGLAYICILAR: Tuple[str, ...] = ("lemonsqueezy", "shopier", "stripe", "iyzico", "paytr", "paypal")
#: Kaynağın bağlı olduğu modül (müşteride modül kapalıysa yeni yansıma üretilmez).
AKTARIM_MODULU: Dict[str, str] = {"pos": "stok_pos", "hukuk": "hukuk_burosu", "saha": "saha_servisi"}
#: Aktarım ayarındaki hedef hesap alanları (kaynak → alanlar). İlk alan zorunlu (saha: boş = vadeli, cariye).
AKTARIM_HESAPLARI: Dict[str, Tuple[str, ...]] = {
    "odeme": ("banka_hesap_id", "nakit_hesap_id", "cevrimici_hesap_id"),
    "pos": ("nakit_hesap_id", "kart_hesap_id", "havale_hesap_id"),
    "hukuk": ("hesap_id",),
    "saha": ("hesap_id",),
}
AKTARIM_ZORUNLU: Dict[str, Tuple[str, ...]] = {
    "odeme": ("banka_hesap_id",),
    "pos": ("nakit_hesap_id", "kart_hesap_id"),
    "hukuk": ("hesap_id",),
    "saha": (),
}
#: Cari kartın bağlanabileceği mevcut kayıtlar. Ajansta CRM adayı / müşteri hesabı; müşteride saha servisi
#: müşterisi / POS alıcısı / stok tedarikçisi (o modülün izni de olan kişiye). Hukuk müvekkilleri BİLEREK yok
#: (avukat–müvekkil sırrı: müvekkil adı yalnız `hukuk` izniyle görünür).
BAGLI_TURLER: Tuple[str, ...] = ("crm_aday", "musteri_hesabi", "saha_musteri", "pos_alici", "stok_tedarikci")
#: Yaşlandırma kovaları (sırayla).
KOVALAR: Tuple[str, ...] = ("vadesi_gelmemis", "0_30", "31_60", "61_90", "90_ustu")
#: `muhasebe.alacak_gecikti` eşikleri (vadeden bu yana gün; açık kalem başına eşik başına BİR kez). Eşiğin üstünden
#: `GECIKME_GEC_URETIM_GUN`den fazla geçmişse susar (modül ilk açıldığında eski alacaklar için olay yağmuru olmasın).
GECIKME_ESIKLERI: Tuple[int, ...] = (1, 30, 60, 90)
GECIKME_GEC_URETIM_GUN = 7

VARSAYILAN_HESAP_SINIRI = 10
EN_COK_TUTAR = 100_000_000_000  # 1 milyar (kuruş)
EN_COK_CSV_SATIR = 2000
EN_COK_CSV_BAYT = 2 * 1024 * 1024
EN_COK_ETIKET = 10
DOSYA_EN_COK_MB = 15
EN_COK_GERIYE_GUN = 731  # aktarım başlangıcı en çok ~2 yıl geriye
EN_COK_TEKRAR_TUR = 24  # bir eşitlemede tekrar başına en çok bu kadar dönem (uzun uyku sonrası)
TAHMIN_AY = 3

#: Varsayılan Türkçe kategori seti: (tür, anahtar, ad, renk). Ad değiştirilebilir; anahtar kalır.
VARSAYILAN_KATEGORILER: Tuple[Tuple[str, str, str, str], ...] = (
    ("gelir", "satis", "Satış gelirleri", "#22c55e"),
    ("gelir", "hizmet", "Hizmet gelirleri", "#10b981"),
    ("gelir", "faiz", "Faiz ve finansman gelirleri", "#14b8a6"),
    ("gelir", "diger_gelir", "Diğer gelirler", "#84cc16"),
    ("gider", "kira", "Kira", "#f97316"),
    ("gider", "personel", "Personel ve maaş", "#ef4444"),
    ("gider", "faturalar", "Faturalar ve aidat (elektrik, su, internet)", "#eab308"),
    ("gider", "malzeme", "Malzeme ve stok alımı", "#a855f7"),
    ("gider", "pazarlama", "Reklam ve pazarlama", "#ec4899"),
    ("gider", "ulasim", "Ulaşım ve akaryakıt", "#0ea5e9"),
    ("gider", "vergi", "Vergi, SGK ve harçlar", "#64748b"),
    ("gider", "banka", "Banka ve komisyon giderleri", "#6366f1"),
    ("gider", "yazilim", "Yazılım ve abonelikler", "#8b5cf6"),
    ("gider", "ofis", "Ofis ve kırtasiye", "#06b6d4"),
    ("gider", "yemek", "Yemek ve ikram", "#f59e0b"),
    ("gider", "bakim", "Bakım ve onarım", "#78716c"),
    ("gider", "danismanlik", "Muhasebe, hukuk ve danışmanlık", "#0891b2"),
    ("gider", "diger_gider", "Diğer giderler", "#9ca3af"),
)
#: Yalnız otomatik aktarma gerektirdiğinde (yoksa) açılan kategoriler.
EK_KATEGORILER: Tuple[Tuple[str, str, str, str], ...] = (
    ("gider", "dava_masraf", "Dava ve takip masrafları", "#475569"),
)
KATEGORI_ADLARI: Dict[str, str] = {a: ad for _, a, ad, _ in VARSAYILAN_KATEGORILER + EK_KATEGORILER}
KATEGORI_TURU: Dict[str, str] = {a: t for t, a, _, _ in VARSAYILAN_KATEGORILER + EK_KATEGORILER}
KATEGORI_RENGI: Dict[str, str] = {a: c for _, a, _, c in VARSAYILAN_KATEGORILER + EK_KATEGORILER}
#: Otomatik yansımanın kategorisi (kaynak → anahtar). Müşteride ajansa ödenen fatura gider: "yazilim".
AKTARIM_KATEGORISI: Dict[str, str] = {"odeme": "hizmet", "fatura": "hizmet", "pos": "satis", "hukuk": "dava_masraf",
                                      "saha": "hizmet"}

_RENK = re.compile(r"^#[0-9a-fA-F]{6}$")
_AY = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


class MuhasebeHatasi(r.RandevuHatasi):
    """Doğrulama/iş kuralı hatası: `{"kod", "alan"?, ...}` gövdesiyle döner."""


TemelHata = r.RandevuHatasi


def simdi() -> datetime:
    """Testler bu fonksiyonu sabit bir ana çeviriyor (bütün zaman hesapları buradan)."""
    return datetime.now(UTC)


def tz():
    return r.saat_dilimi(SAAT_DILIMI)


def bugun() -> date:
    """İşletmenin (İstanbul) bugünü."""
    return simdi().astimezone(tz()).date()


def iso(an: Optional[datetime]) -> Optional[str]:
    return r.iso(an)


def gun_iso(g: Optional[date]) -> Optional[str]:
    return g.isoformat() if g else None


def kapsam_anahtari(hesap: Optional[str]) -> str:
    return hesap or AJANS_KAPSAMI


def json_yukle(ham: Any, varsayilan: Any = None) -> Any:
    return r.json_yukle(ham, varsayilan)


def json_yaz(deger: Any) -> str:
    return r.json_yaz(deger)


# ---------------------------------------------------------------------------
# Doğrulayıcılar
# ---------------------------------------------------------------------------
def metin(ham: Any, alan: str, sinir: int, zorunlu: bool = False, cok_satir: bool = False) -> str:
    return r.metin(ham, alan, sinir, zorunlu=zorunlu, cok_satir=cok_satir)


def bos_ya_da(ham: Any, alan: str, sinir: int, cok_satir: bool = False) -> Optional[str]:
    return metin(ham, alan, sinir, cok_satir=cok_satir) or None


def secim(ham: Any, alan: str, secenekler: Sequence[str], varsayilan: Optional[str] = None) -> str:
    if ham in (None, "") and varsayilan is not None:
        return varsayilan
    if ham not in secenekler:
        raise MuhasebeHatasi("secim_gecersiz", alan)
    return str(ham)


def bool_duzelt(ham: Any, alan: str) -> bool:
    if isinstance(ham, bool):
        return ham
    raise MuhasebeHatasi("evet_hayir_gecersiz", alan)


def tam_sayi(ham: Any, alan: str, en_az: int, en_cok: int) -> int:
    if isinstance(ham, bool) or ham in (None, ""):
        raise MuhasebeHatasi("sayi_gecersiz", alan)
    try:
        d = int(str(ham).strip())
    except (TypeError, ValueError):
        raise MuhasebeHatasi("sayi_gecersiz", alan)
    if d < en_az or d > en_cok:
        raise MuhasebeHatasi("aralik_disinda", alan, en_az=en_az, en_cok=en_cok)
    return d


def kimlik(ham: Any, alan: str, bos_olabilir: bool = True) -> Optional[int]:
    if ham in (None, "", 0) and bos_olabilir:
        return None
    if isinstance(ham, bool):
        raise MuhasebeHatasi("kimlik_gecersiz", alan)
    try:
        d = int(ham)
    except (TypeError, ValueError):
        raise MuhasebeHatasi("kimlik_gecersiz", alan)
    if d <= 0:
        if bos_olabilir:
            return None
        raise MuhasebeHatasi("kimlik_gecersiz", alan)
    return d


def para_birimi_duzelt(ham: Any, alan: str = "para_birimi", varsayilan: str = "TRY") -> str:
    if ham in (None, ""):
        return varsayilan
    d = str(ham).strip().upper()
    if d not in PARA_BIRIMLERI:
        raise MuhasebeHatasi("para_birimi_gecersiz", alan)
    return d


def renk_duzelt(ham: Any, alan: str = "renk") -> Optional[str]:
    if ham in (None, ""):
        return None
    if not isinstance(ham, str) or not _RENK.match(ham):
        raise MuhasebeHatasi("renk_gecersiz", alan)
    return ham.lower()


def tarih_duzelt(ham: Any, alan: str) -> date:
    if isinstance(ham, date) and not isinstance(ham, datetime):
        return ham
    h = str(ham or "").strip()[:10]
    try:
        g = date.fromisoformat(h)
    except ValueError:
        raise MuhasebeHatasi("tarih_gecersiz", alan)
    if g.year < 2000 or g.year > 2100:
        raise MuhasebeHatasi("tarih_gecersiz", alan)
    return g


def bos_tarih(ham: Any, alan: str) -> Optional[date]:
    return None if ham in (None, "") else tarih_duzelt(ham, alan)


def ay_duzelt(ham: Any, alan: str = "ay", yildiz: bool = False) -> str:
    h = str(ham or "").strip()
    if yildiz and h == "*":
        return "*"
    m = _AY.match(h)
    if not m or not (2000 <= int(m.group(1)) <= 2100):
        raise MuhasebeHatasi("ay_gecersiz", alan)
    return h


def ay_anahtari(g: date) -> str:
    return f"{g.year:04d}-{g.month:02d}"


def ay_araligi(ay: str) -> Tuple[date, date]:
    y, a = int(ay[:4]), int(ay[5:7])
    bas = date(y, a, 1)
    bit = date(y + (a == 12), 1 if a == 12 else a + 1, 1) - timedelta(days=1)
    return bas, bit


def ay_ekle(ay: str, n: int) -> str:
    y, a = int(ay[:4]), int(ay[5:7])
    toplam = y * 12 + (a - 1) + n
    return f"{toplam // 12:04d}-{toplam % 12 + 1:02d}"


def _ondalik(ham: Any, ondalik: Optional[str]) -> Decimal:
    """Ham tutar metni → Decimal. `ondalik`: "," | "." | None (otomatik: sondaki ayırıcı ondalık)."""
    if isinstance(ham, bool):
        raise InvalidOperation
    if isinstance(ham, int):
        return Decimal(ham)
    if isinstance(ham, float):
        return Decimal(repr(ham))
    m = re.sub(r"[\s ₺$€£]|TL|TRY|USD|EUR|GBP", "", str(ham), flags=re.I)
    eksi = False
    if m.startswith("(") and m.endswith(")"):
        eksi, m = True, m[1:-1]
    if m.endswith("-"):
        eksi, m = True, m[:-1]
    if ondalik == ",":
        m = m.replace(".", "").replace(",", ".")
    elif ondalik == ".":
        m = m.replace(",", "")
    elif "," in m and "." in m:
        m = m.replace(".", "").replace(",", ".") if m.rfind(",") > m.rfind(".") else m.replace(",", "")
    elif m.count(",") > 1:
        m = m.replace(",", "")  # "1,234,567" — binlik
    elif "," in m:
        m = m.replace(",", ".")  # Türkçe ondalık: "12,5" / "0,005" / "1,250" (= 1,25)
    elif m.count(".") > 1 or re.fullmatch(r"-?[1-9]\d{0,2}\.\d{3}", m):
        m = m.replace(".", "")  # "1.234.567" / "1.250" (Türkçe binlik); "19.99" ve "0.005" ondalık kalır
    d = Decimal(m)
    return -d if eksi else d


def kurus_coz(ham: Any, alan: str, *, ondalik: Optional[str] = None, eksi_olabilir: bool = False,
              sifir_olabilir: bool = False, bos_olabilir: bool = False) -> Optional[int]:
    """12 / 12.5 / "12,50" / "1.250,00" / "1,250.00" → kuruş (yarım yukarı: 0,005 → 0,01)."""
    if ham in (None, ""):
        if bos_olabilir:
            return None
        raise MuhasebeHatasi("zorunlu", alan)
    try:
        d = _ondalik(ham, ondalik)
    except (InvalidOperation, ValueError):
        raise MuhasebeHatasi("tutar_gecersiz", alan)
    if not d.is_finite():
        raise MuhasebeHatasi("tutar_gecersiz", alan)
    k = int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if abs(k) > EN_COK_TUTAR:
        raise MuhasebeHatasi("tutar_cok_buyuk", alan)
    if k < 0 and not eksi_olabilir:
        raise MuhasebeHatasi("tutar_eksi", alan)
    if k == 0 and not sifir_olabilir:
        raise MuhasebeHatasi("tutar_sifir", alan)
    return k


def yuvarla(pay: int, payda: int) -> int:
    """Tam sayı bölmesi, yarım YUKARI (sıfırdan uzağa) — kayan nokta yok."""
    if payda <= 0:
        raise ValueError("payda")
    isaret = -1 if pay < 0 else 1
    return isaret * ((abs(pay) * 2 + payda) // (2 * payda))


def kdv_orani_duzelt(ham: Any, alan: str = "kdv_orani") -> Optional[int]:
    if ham in (None, ""):
        return None
    if isinstance(ham, bool):
        raise MuhasebeHatasi("kdv_orani_gecersiz", alan)
    try:
        d = int(str(ham).strip().lstrip("%"))
    except (TypeError, ValueError):
        raise MuhasebeHatasi("kdv_orani_gecersiz", alan)
    if d < 0 or d > 100:
        raise MuhasebeHatasi("kdv_orani_gecersiz", alan)
    return d


def kdv_dahilden(tutar: int, oran: Optional[int]) -> int:
    """KDV dahil tutardan KDV: tutar × oran / (100 + oran), yarım yukarı (1.200,00 ₺ %20 → 200,00 ₺)."""
    if not oran:
        return 0
    return yuvarla(tutar * oran, 100 + oran)


def kdv_haricten(net: int, oran: Optional[int]) -> int:
    """KDV hariç tutardan KDV: net × oran / 100, yarım yukarı."""
    if not oran:
        return 0
    return yuvarla(net * oran, 100)


def iban_duzelt(ham: Any, alan: str = "iban") -> Optional[str]:
    """IBAN METİN olarak — yalnız biçim: boşluklar atılır, büyük harf; ülke kodu + 2 denetim hanesi + 11–30
    harf/rakam, mod-97 = 1 (ISO 13616). TR'de 26 karakter. Banka/hesap varlığı DOĞRULANMAZ."""
    if ham in (None, ""):
        return None
    d = re.sub(r"[\s-]", "", str(ham)).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", d):
        raise MuhasebeHatasi("iban_gecersiz", alan)
    if d.startswith("TR") and len(d) != 26:
        raise MuhasebeHatasi("iban_gecersiz", alan)
    yeniden = d[4:] + d[:4]
    sayisal = "".join(str(int(c, 36)) for c in yeniden)
    if int(sayisal) % 97 != 1:
        raise MuhasebeHatasi("iban_gecersiz", alan)
    return d


def iban_maskele(iban: Optional[str]) -> Optional[str]:
    """Gösterim: YALNIZ son 4 hane ("TR•• •••• 1326"). Uçlar tam IBAN'ı hiç döndürmez."""
    if not iban:
        return None
    return f"{iban[:2]}•• •••• {iban[-4:]}"


def son4_duzelt(ham: Any, alan: str = "son4") -> Optional[str]:
    if ham in (None, ""):
        return None
    d = str(ham).strip()
    if not re.fullmatch(r"\d{4}", d):
        raise MuhasebeHatasi("son4_gecersiz", alan)
    return d


def vergi_no_duzelt(ham: Any, alan: str = "vergi_no") -> Optional[str]:
    if ham in (None, ""):
        return None
    d = re.sub(r"\s", "", str(ham))
    if not re.fullmatch(r"\d{10,11}", d):
        raise MuhasebeHatasi("vergi_no_gecersiz", alan)
    return d


def eposta_duzelt(ham: Any, alan: str = "eposta") -> Optional[str]:
    d = metin(ham, alan, 254).lower()
    if not d:
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", d):
        raise MuhasebeHatasi("eposta_gecersiz", alan)
    return d


def telefon_duzelt(ham: Any, alan: str = "telefon") -> Optional[str]:
    d = metin(ham, alan, 32)
    if not d:
        return None
    if not re.fullmatch(r"[+\d][\d\s()-]{5,30}", d):
        raise MuhasebeHatasi("telefon_gecersiz", alan)
    return d


def etiketler_duzelt(ham: Any, alan: str = "etiketler") -> List[str]:
    if ham in (None, ""):
        return []
    if isinstance(ham, str):
        ham = [x for x in re.split(r"[,;]", ham)]
    if not isinstance(ham, list):
        raise MuhasebeHatasi("etiket_gecersiz", alan)
    sonuc: List[str] = []
    for x in ham:
        if not isinstance(x, str):
            raise MuhasebeHatasi("etiket_gecersiz", alan)
        e = re.sub(r"\s+", " ", x).strip().lower()[:30]
        if e and e not in sonuc:
            sonuc.append(e)
    if len(sonuc) > EN_COK_ETIKET:
        raise MuhasebeHatasi("etiket_cok", alan, en_cok=EN_COK_ETIKET)
    return sonuc


# ---------------------------------------------------------------------------
# Tekrarlayan dönemler
# ---------------------------------------------------------------------------
def _ay_gunu(y: int, a: int, gun: int) -> date:
    son = (date(y + (a == 12), 1 if a == 12 else a + 1, 1) - timedelta(days=1)).day
    return date(y, a, min(gun, son))


def donem_tarihi(baslangic: date, periyot: str, n: int) -> date:
    """Başlangıçtan itibaren n. dönem (0 = başlangıç). Ay tabanlılarda gün başlangıçtan; ay sonu kırpılır."""
    if periyot == "haftalik":
        return baslangic + timedelta(weeks=n)
    adim = {"aylik": 1, "uc_aylik": 3, "yillik": 12}[periyot]
    toplam = baslangic.year * 12 + (baslangic.month - 1) + n * adim
    return _ay_gunu(toplam // 12, toplam % 12 + 1, baslangic.day)


def sonraki_donem(baslangic: date, periyot: str, simdiki: date) -> date:
    """`simdiki` dönemin ardından gelen dönem (kırpılmış ay sonundan kaymadan; başlangıç gününe göre)."""
    n = 0
    # Haftalıkta doğrudan hesap; ay tabanlılarda en çok birkaç yüz adım.
    if periyot == "haftalik":
        n = (simdiki - baslangic).days // 7 + 1
        return donem_tarihi(baslangic, periyot, max(n, 0))
    while donem_tarihi(baslangic, periyot, n) <= simdiki:
        n += 1
        if n > 5000:
            break
    return donem_tarihi(baslangic, periyot, n)


def donemler(baslangic: date, periyot: str, bas: date, bit: date, bitis: Optional[date] = None, sinir: int = 400) -> List[date]:
    """[bas, bit] aralığına düşen dönem tarihleri (bitis'ten sonrası yok)."""
    sonuc: List[date] = []
    n = 0
    if periyot == "haftalik" and bas > baslangic:
        n = max(0, (bas - baslangic).days // 7 - 1)
    while len(sonuc) < sinir:
        g = donem_tarihi(baslangic, periyot, n)
        if g > bit or (bitis and g > bitis):
            break
        if g >= bas:
            sonuc.append(g)
        n += 1
        if n > 5000:
            break
    return sonuc


# ---------------------------------------------------------------------------
# Yaşlandırma
# ---------------------------------------------------------------------------
def gecikme_esigi(gun: int) -> Optional[int]:
    """Ulaşılan en büyük gecikme eşiği; üstünden `GECIKME_GEC_URETIM_GUN`den fazla geçtiyse None (susar)."""
    ulasilan = [e for e in GECIKME_ESIKLERI if e <= gun]
    if not ulasilan:
        return None
    esik = ulasilan[-1]
    return esik if gun - esik <= GECIKME_GEC_URETIM_GUN else None


def kova(gun: int) -> str:
    """Vadeden bu yana geçen gün → kova. Eksi = vadesi gelmemiş; 0–30, 31–60, 61–90, 91+ (sınırlar dahil)."""
    if gun < 0:
        return "vadesi_gelmemis"
    if gun <= 30:
        return "0_30"
    if gun <= 60:
        return "31_60"
    if gun <= 90:
        return "61_90"
    return "90_ustu"


@dataclass
class AcikKalem:
    vade: date
    tutar: int
    hareket_id: Optional[int] = None
    kalan: int = 0


@dataclass
class Yaslandirma:
    kovalar: Dict[str, int] = field(default_factory=lambda: {k: 0 for k in KOVALAR})
    acik: int = 0
    #: Kapatan kalemler borcu aştıysa fazlası (avans / fazla ödeme).
    fazla: int = 0
    en_eski_gun: Optional[int] = None
    kalemler: List[AcikKalem] = field(default_factory=list)


def yaslandir(borclar: Iterable[AcikKalem], kapatan: int, rapor_tarihi: date) -> Yaslandirma:
    """FIFO: en eski vadeli borç önce kapanır. `kapatan` (≥ 0) toplam kapatan tutar."""
    sirali = sorted((AcikKalem(k.vade, int(k.tutar), k.hareket_id) for k in borclar if k.tutar > 0),
                    key=lambda k: (k.vade, k.hareket_id or 0))
    kalan_kapatan = max(0, int(kapatan))
    y = Yaslandirma()
    for k in sirali:
        dus = min(k.tutar, kalan_kapatan)
        kalan_kapatan -= dus
        k.kalan = k.tutar - dus
        if k.kalan <= 0:
            continue
        gun = (rapor_tarihi - k.vade).days
        y.kovalar[kova(gun)] += k.kalan
        y.acik += k.kalan
        if gun >= 0 and (y.en_eski_gun is None or gun > y.en_eski_gun):
            y.en_eski_gun = gun
        y.kalemler.append(k)
    y.fazla = kalan_kapatan
    return y


# ---------------------------------------------------------------------------
# Cari etkisi (borç / alacak sütunları)
# ---------------------------------------------------------------------------
def cari_etkisi(tur: str, tutar: int, hesapli: bool) -> Tuple[int, int]:
    """(borç, alacak) — cari ekstresindeki sütunlar. Bakiye = Σ borç − Σ alacak (artı: cari bize borçlu).

    vadeli satış (gelir, hesapsız) → borç · peşin satış → borç + alacak (etkisiz) · vadeli alış (gider,
    hesapsız) → alacak · peşin alış → borç + alacak · tahsilat → alacak · cariye ödeme → borç."""
    if tur == "gelir":
        return (tutar, tutar) if hesapli else (tutar, 0)
    if tur == "gider":
        return (tutar, tutar) if hesapli else (0, tutar)
    if tur == "tahsilat":
        return 0, tutar
    if tur == "odeme":
        return tutar, 0
    return 0, 0


def hesap_etkisi(tur: str, tutar: int, hesap_id: Optional[int], hedef_hesap_id: Optional[int], hedef_tutar: Optional[int],
                 hangi: int) -> int:
    """Hareketin `hangi` hesabın bakiyesine etkisi (kuruş, işaretli)."""
    etki = 0
    if hesap_id == hangi:
        if tur in ("gelir", "tahsilat"):
            etki += tutar
        elif tur in ("gider", "odeme", "virman"):
            etki -= tutar
    if tur == "virman" and hedef_hesap_id == hangi:
        etki += hedef_tutar if hedef_tutar is not None else tutar
    return etki


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
def csv_hucre(deger: Any) -> Any:
    if deger is None:
        return ""
    s = str(deger)
    if s[:1] in ("=", "+", "-", "@", "\t", "\r") and not re.fullmatch(r"-?\d+([.,]\d+)?", s):
        return "'" + s
    return s


def csv_metni(basliklar: Sequence[str], satirlar: Iterable[Sequence[Any]]) -> str:
    """Excel'in Türkçe ayarıyla açılan CSV: UTF-8 BOM + noktalı virgül; formül enjeksiyonuna karşı kaçış."""
    tampon = io.StringIO()
    yazici = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
    yazici.writerow(basliklar)
    for satir in satirlar:
        yazici.writerow([csv_hucre(h) for h in satir])
    return "﻿" + tampon.getvalue()


def kurus_metni(k: Optional[int]) -> str:
    """CSV için: 123456 → "1234,56" (eksi işaretli)."""
    if k is None:
        return ""
    eksi = k < 0
    tam, kesir = divmod(abs(int(k)), 100)
    return f"{'-' if eksi else ''}{tam},{kesir:02d}"


TARIH_BICIMLERI: Tuple[str, ...] = ("otomatik", "gg.aa.yyyy", "yyyy-aa-gg", "gg/aa/yyyy", "aa/gg/yyyy")
ONDALIKLAR: Tuple[str, ...] = ("otomatik", ",", ".")
ESLEME_ALANLARI: Tuple[str, ...] = ("tarih", "aciklama", "tutar", "giris", "cikis", "belge_no")

_BASLIK_IPUCLARI: Dict[str, Tuple[str, ...]] = {
    "tarih": ("tarih", "islem tarihi", "işlem tarihi", "date", "valor", "value date", "booking date", "datum"),
    "aciklama": ("aciklama", "açıklama", "description", "detay", "islem", "işlem", "narrative", "memo", "buchungstext"),
    "tutar": ("tutar", "amount", "miktar", "islem tutari", "işlem tutarı", "betrag"),
    "giris": ("alacak", "giris", "giriş", "credit", "yatan", "gelen", "haben"),
    "cikis": ("borc", "borç", "cikis", "çıkış", "debit", "cekilen", "çekilen", "giden", "soll"),
    "belge_no": ("dekont", "belge", "referans", "reference", "ref", "fis no", "fiş no", "receipt"),
}


def _sade(b: str) -> str:
    tablo = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return re.sub(r"\s+", " ", (b or "").translate(tablo).strip().lower())


def csv_ayristir(metin_: str, ayirici: Optional[str] = None) -> Tuple[List[str], List[List[str]]]:
    """Başlıklı CSV → (başlıklar, satırlar). Ayırıcı verilmezse ilk satırdan (; , tab) tahmin."""
    metin_ = (metin_ or "").lstrip("﻿")
    if not metin_.strip():
        raise MuhasebeHatasi("csv_bos", "csv")
    if len(metin_.encode("utf-8")) > EN_COK_CSV_BAYT:
        raise MuhasebeHatasi("csv_buyuk", "csv")
    satirlar_ = metin_.splitlines()
    ilk = next((s for s in satirlar_ if s.strip()), "")
    if ayirici not in (";", ",", "\t"):
        sayilar = {a: ilk.count(a) for a in (";", ",", "\t")}
        ayirici = max(sayilar, key=lambda a: sayilar[a]) if any(sayilar.values()) else ";"
    try:
        okunan = [s for s in csv.reader(io.StringIO(metin_), delimiter=ayirici) if any((h or "").strip() for h in s)]
    except csv.Error:
        raise MuhasebeHatasi("csv_gecersiz", "csv")
    if len(okunan) < 2:
        raise MuhasebeHatasi("csv_bos", "csv")
    basliklar = [(b or "").strip()[:80] for b in okunan[0]]
    veri = okunan[1:]
    if len(veri) > EN_COK_CSV_SATIR:
        raise MuhasebeHatasi("csv_cok", "csv", en_cok=EN_COK_CSV_SATIR)
    return basliklar, [[(h or "").strip() for h in s] for s in veri]


def tahmini_esleme(basliklar: Sequence[str]) -> Dict[str, Optional[int]]:
    """Başlık adlarından sütun eşlemesi tahmini (alan → sütun sırası)."""
    sade = [_sade(b) for b in basliklar]
    sonuc: Dict[str, Optional[int]] = {a: None for a in ESLEME_ALANLARI}
    kullanilan: set = set()
    for alan in ("tarih", "giris", "cikis", "tutar", "aciklama", "belge_no"):
        for i, b in enumerate(sade):
            if i in kullanilan:
                continue
            if any(b == _sade(ip) or b.startswith(_sade(ip)) for ip in _BASLIK_IPUCLARI[alan]):
                sonuc[alan] = i
                kullanilan.add(i)
                break
    if sonuc["giris"] is not None and sonuc["cikis"] is not None:
        sonuc["tutar"] = None
    return sonuc


def esleme_duzelt(ham: Any, sutun_sayisi: int) -> Dict[str, Optional[int]]:
    if not isinstance(ham, dict):
        raise MuhasebeHatasi("esleme_gecersiz", "esleme")
    sonuc: Dict[str, Optional[int]] = {}
    for alan in ESLEME_ALANLARI:
        d = ham.get(alan)
        if d in (None, "", -1):
            sonuc[alan] = None
            continue
        if isinstance(d, bool) or not isinstance(d, int) or d < 0 or d >= sutun_sayisi:
            raise MuhasebeHatasi("esleme_gecersiz", f"esleme.{alan}")
        sonuc[alan] = d
    if sonuc["tarih"] is None:
        raise MuhasebeHatasi("esleme_tarih_gerekli", "esleme.tarih")
    if sonuc["tutar"] is None and sonuc["giris"] is None and sonuc["cikis"] is None:
        raise MuhasebeHatasi("esleme_tutar_gerekli", "esleme.tutar")
    return sonuc


def csv_tarih(ham: str, bicim: str = "otomatik") -> date:
    h = (ham or "").strip()[:19]
    if not h:
        raise MuhasebeHatasi("tarih_gecersiz", "tarih")
    h = h.split(" ")[0].split("T")[0]
    try:
        if bicim == "yyyy-aa-gg" or (bicim == "otomatik" and re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", h)):
            y, a, g = (int(x) for x in h.split("-"))
            return tarih_duzelt(f"{y:04d}-{a:02d}-{g:02d}", "tarih")
        m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", h)
        if not m:
            raise MuhasebeHatasi("tarih_gecersiz", "tarih")
        x, y_, yil = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if yil < 100:
            yil += 2000
        if bicim == "aa/gg/yyyy":
            ay, gun = x, y_
        else:
            gun, ay = x, y_
        return tarih_duzelt(f"{yil:04d}-{ay:02d}-{gun:02d}", "tarih")
    except (ValueError, MuhasebeHatasi):
        raise MuhasebeHatasi("tarih_gecersiz", "tarih")


@dataclass
class CsvSatiri:
    satir: int
    tarih: date
    #: İşaretli: artı = hesaba giriş (gelir), eksi = çıkış (gider).
    tutar: int
    aciklama: str
    belge_no: Optional[str]


def csv_satiri_coz(no: int, satir: Sequence[str], esleme: Dict[str, Optional[int]], tarih_bicimi: str,
                   ondalik: Optional[str]) -> CsvSatiri:
    def hucre(alan: str) -> str:
        i = esleme.get(alan)
        return (satir[i] if i is not None and i < len(satir) else "").strip()

    tarih = csv_tarih(hucre("tarih"), tarih_bicimi)
    od = None if ondalik in (None, "otomatik") else ondalik
    if esleme.get("tutar") is not None:
        t = kurus_coz(hucre("tutar"), "tutar", ondalik=od, eksi_olabilir=True)
    else:
        giris = kurus_coz(hucre("giris"), "giris", ondalik=od, bos_olabilir=True, sifir_olabilir=True, eksi_olabilir=True) or 0
        cikis = kurus_coz(hucre("cikis"), "cikis", ondalik=od, bos_olabilir=True, sifir_olabilir=True, eksi_olabilir=True) or 0
        t = abs(giris) - abs(cikis)
        if t == 0:
            raise MuhasebeHatasi("tutar_sifir", "tutar")
    aciklama = re.sub(r"\s+", " ", hucre("aciklama"))[:300]
    belge = hucre("belge_no")[:60] or None
    return CsvSatiri(no, tarih, int(t or 0), aciklama, belge)


def csv_kimligi(hesap_id: int, s: CsvSatiri, tekrar: int) -> str:
    """Aynı ekstre ikinci kez yüklenirse aynı satır iki kez sayılmasın (hesap + tarih + tutar + açıklama +
    aynı içerikli satırın sırası)."""
    import hashlib

    ham = f"{hesap_id}|{s.tarih.isoformat()}|{s.tutar}|{_sade(s.aciklama)}|{s.belge_no or ''}|{tekrar}"
    return hashlib.sha256(ham.encode("utf-8")).hexdigest()[:40]


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
PDF_ETIKET: Dict[str, Dict[str, str]] = {
    "tr": {
        "ekstre": "CARİ HESAP EKSTRESİ", "hareketler": "HAREKET LİSTESİ", "cari": "Cari", "donem": "Dönem",
        "tarih": "Tarih", "aciklama": "Açıklama", "belge": "Belge no", "vade": "Vade", "borc": "Borç", "alacak": "Alacak",
        "bakiye": "Bakiye", "devreden": "Devreden bakiye", "kapanis": "Dönem sonu bakiyesi", "toplam": "Toplam",
        "tur": "Tür", "kategori": "Kategori", "hesap": "Hesap", "tutar": "Tutar", "kdv": "KDV",
        "borclu": "(cari borçlu)", "alacakli": "(cari alacaklı)", "vergi": "Vergi dairesi / no",
        "olusturma": "Oluşturma", "gelir": "Gelir", "gider": "Gider", "tahsilat": "Tahsilat", "odeme": "Ödeme",
        "virman": "Virman", "ters": "Ters kayıt", "not": "Bu belge bilgi amaçlıdır; resmî kayıt ve beyan yerine geçmez.",
        "bos": "Bu dönemde hareket yok.",
    },
    "en": {
        "ekstre": "ACCOUNT STATEMENT", "hareketler": "TRANSACTION LIST", "cari": "Contact", "donem": "Period",
        "tarih": "Date", "aciklama": "Description", "belge": "Document no", "vade": "Due", "borc": "Debit",
        "alacak": "Credit", "bakiye": "Balance", "devreden": "Opening balance", "kapanis": "Closing balance",
        "toplam": "Total", "tur": "Type", "kategori": "Category", "hesap": "Account", "tutar": "Amount", "kdv": "VAT",
        "borclu": "(contact owes)", "alacakli": "(we owe)", "vergi": "Tax office / no", "olusturma": "Created",
        "gelir": "Income", "gider": "Expense", "tahsilat": "Collection", "odeme": "Payment", "virman": "Transfer",
        "ters": "Reversal", "not": "This document is for information only; it does not replace official records or returns.",
        "bos": "No transactions in this period.",
    },
    "de": {
        "ekstre": "KONTOAUSZUG", "hareketler": "BUCHUNGSLISTE", "cari": "Kontakt", "donem": "Zeitraum",
        "tarih": "Datum", "aciklama": "Beschreibung", "belge": "Beleg-Nr.", "vade": "Fällig", "borc": "Soll",
        "alacak": "Haben", "bakiye": "Saldo", "devreden": "Anfangssaldo", "kapanis": "Endsaldo", "toplam": "Summe",
        "tur": "Art", "kategori": "Kategorie", "hesap": "Konto", "tutar": "Betrag", "kdv": "MwSt.",
        "borclu": "(Kontakt schuldet)", "alacakli": "(wir schulden)", "vergi": "Finanzamt / Steuer-Nr.",
        "olusturma": "Erstellt", "gelir": "Einnahme", "gider": "Ausgabe", "tahsilat": "Zahlungseingang",
        "odeme": "Zahlungsausgang", "virman": "Umbuchung", "ters": "Storno",
        "not": "Dieses Dokument dient nur zur Information und ersetzt keine amtlichen Aufzeichnungen oder Erklärungen.",
        "bos": "Keine Buchungen in diesem Zeitraum.",
    },
    "ru": {
        "ekstre": "ВЫПИСКА ПО СЧЁТУ КОНТРАГЕНТА", "hareketler": "СПИСОК ОПЕРАЦИЙ", "cari": "Контрагент", "donem": "Период",
        "tarih": "Дата", "aciklama": "Описание", "belge": "№ документа", "vade": "Срок", "borc": "Дебет", "alacak": "Кредит",
        "bakiye": "Сальдо", "devreden": "Входящее сальдо", "kapanis": "Исходящее сальдо", "toplam": "Итого",
        "tur": "Тип", "kategori": "Категория", "hesap": "Счёт", "tutar": "Сумма", "kdv": "НДС",
        "borclu": "(долг контрагента)", "alacakli": "(наш долг)", "vergi": "Налоговая инспекция / ИНН",
        "olusturma": "Создано", "gelir": "Доход", "gider": "Расход", "tahsilat": "Поступление", "odeme": "Платёж",
        "virman": "Перевод", "ters": "Сторно",
        "not": "Документ носит информационный характер и не заменяет официальный учёт и отчётность.",
        "bos": "За этот период операций нет.",
    },
    "ar": {
        "ekstre": "كشف حساب جارٍ", "hareketler": "قائمة الحركات", "cari": "الطرف", "donem": "الفترة",
        "tarih": "التاريخ", "aciklama": "الوصف", "belge": "رقم المستند", "vade": "الاستحقاق", "borc": "مدين", "alacak": "دائن",
        "bakiye": "الرصيد", "devreden": "الرصيد الافتتاحي", "kapanis": "الرصيد الختامي", "toplam": "الإجمالي",
        "tur": "النوع", "kategori": "الفئة", "hesap": "الحساب", "tutar": "المبلغ", "kdv": "ضريبة القيمة المضافة",
        "borclu": "(مستحق على الطرف)", "alacakli": "(مستحق علينا)", "vergi": "مكتب الضرائب / الرقم",
        "olusturma": "تاريخ الإنشاء", "gelir": "إيراد", "gider": "مصروف", "tahsilat": "تحصيل", "odeme": "دفعة",
        "virman": "تحويل", "ters": "قيد عكسي",
        "not": "هذا المستند للعلم فقط ولا يحل محل السجلات أو الإقرارات الرسمية.",
        "bos": "لا توجد حركات في هذه الفترة.",
    },
    "zh": {
        "ekstre": "往来账户对账单", "hareketler": "流水明细", "cari": "往来方", "donem": "期间",
        "tarih": "日期", "aciklama": "说明", "belge": "单据号", "vade": "到期", "borc": "借方", "alacak": "贷方",
        "bakiye": "余额", "devreden": "期初余额", "kapanis": "期末余额", "toplam": "合计",
        "tur": "类型", "kategori": "类别", "hesap": "账户", "tutar": "金额", "kdv": "增值税",
        "borclu": "（对方欠款）", "alacakli": "（我方欠款）", "vergi": "税务局 / 税号",
        "olusturma": "生成日期", "gelir": "收入", "gider": "支出", "tahsilat": "收款", "odeme": "付款",
        "virman": "转账", "ters": "冲销",
        "not": "本文件仅供参考，不能替代正式账簿和申报。",
        "bos": "本期间无流水。",
    },
    "hi": {
        "ekstre": "खाता विवरण", "hareketler": "लेन-देन सूची", "cari": "पक्ष", "donem": "अवधि",
        "tarih": "तारीख", "aciklama": "विवरण", "belge": "दस्तावेज़ सं.", "vade": "देय तिथि", "borc": "नामे", "alacak": "जमा",
        "bakiye": "शेष", "devreden": "प्रारंभिक शेष", "kapanis": "अंतिम शेष", "toplam": "कुल",
        "tur": "प्रकार", "kategori": "श्रेणी", "hesap": "खाता", "tutar": "राशि", "kdv": "कर (VAT)",
        "borclu": "(पक्ष पर बकाया)", "alacakli": "(हम पर बकाया)", "vergi": "कर कार्यालय / संख्या",
        "olusturma": "बनाया गया", "gelir": "आय", "gider": "व्यय", "tahsilat": "प्राप्ति", "odeme": "भुगतान",
        "virman": "स्थानांतरण", "ters": "उलट प्रविष्टि",
        "not": "यह दस्तावेज़ केवल जानकारी के लिए है; यह आधिकारिक रिकॉर्ड या रिटर्न का स्थान नहीं लेता।",
        "bos": "इस अवधि में कोई लेन-देन नहीं।",
    },
}


def pdf_dili(dil: Optional[str]) -> str:
    d = (dil or "tr")[:2].lower()
    return d if d in PDF_ETIKET else "en"


def _pdf_para(kurus: int, para_birimi: str, dil: str) -> str:
    from services import pdf_belge as pb

    return pb.para(Decimal(int(kurus or 0)) / 100, para_birimi, "tr" if dil in ("tr", "de") else "en")


def _pdf_tarih(g: Optional[date]) -> str:
    return g.strftime("%d.%m.%Y") if g else "—"


def ekstre_pdf(v: Dict[str, Any], dil: str = "tr") -> bytes:
    """`v`: {"firma", "cari": {...}, "bas", "bit", "para_birimi", "devreden", "satirlar": [...], "toplam_borc",
    "toplam_alacak", "kapanis"} (tutarlar kuruş, tarihler date)."""
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Spacer, Table, TableStyle

    from services.pdf_yazi import Paragraf as Paragraph  # çok dilli paragraf (Faz 7K yazı tipi yedeği)
    from services import pdf_belge as pb

    dil = pdf_dili(dil)
    e = PDF_ETIKET[dil]
    st = pb._stiller()  # noqa: SLF001
    m = pb._metin  # noqa: SLF001
    pbr = v.get("para_birimi") or "TRY"
    c = v.get("cari") or {}
    sol = [Paragraph(f"<b>{m(v.get('firma') or '')}</b>" if v.get("firma") else "&nbsp;", st["govde"])]
    bilgiler = [(e["donem"], f"{_pdf_tarih(v.get('bas'))} – {_pdf_tarih(v.get('bit'))}"),
                (e["olusturma"], _pdf_tarih(v.get("olusturma")))]
    parcalar: List[Any] = [pb._baslik_blogu(sol, e["ekstre"], bilgiler, st), pb._ayrac(), Spacer(1, 3 * mm)]  # noqa: SLF001
    cari_satir = [f"<b>{m(c.get('ad'))}</b>"]
    vergi = " / ".join(x for x in (c.get("vergi_dairesi"), c.get("vergi_no")) if x)
    if vergi:
        cari_satir.append(f"{m(e['vergi'])}: {m(vergi)}")
    for alan in ("eposta", "telefon"):
        if c.get(alan):
            cari_satir.append(m(c[alan]))
    parcalar += [Paragraph(f"<font color='#5B5368'>{m(e['cari'])}</font>", st["kucuk"]),
                 Paragraph("<br/>".join(cari_satir), st["govde"]), Spacer(1, 4 * mm)]
    basliklar = [e["tarih"], e["aciklama"], e["vade"], e["borc"], e["alacak"], e["bakiye"]]
    veri: List[List[Any]] = [[Paragraph(f"<b>{m(b)}</b>", st["govde"] if i < 3 else st["sag"]) for i, b in enumerate(basliklar)]]
    veri.append([Paragraph(_pdf_tarih(v.get("bas")), st["govde"]), Paragraph(f"<i>{m(e['devreden'])}</i>", st["govde"]),
                 Paragraph("", st["govde"]), Paragraph("", st["sag"]), Paragraph("", st["sag"]),
                 Paragraph(m(_pdf_para(v.get("devreden") or 0, pbr, dil)), st["sag"])])
    for s in v.get("satirlar") or []:
        aciklama = s.get("aciklama") or e.get(s.get("tur") or "", "")
        if s.get("belge_no"):
            aciklama = f"{aciklama} · {s['belge_no']}"
        if s.get("ters"):
            aciklama = f"{aciklama} ({e['ters']})"
        veri.append([Paragraph(_pdf_tarih(s.get("tarih")), st["govde"]), Paragraph(m(aciklama), st["govde"]),
                     Paragraph(_pdf_tarih(s.get("vade")) if s.get("vade") else "", st["govde"]),
                     Paragraph(m(_pdf_para(s["borc"], pbr, dil)) if s.get("borc") else "", st["sag"]),
                     Paragraph(m(_pdf_para(s["alacak"], pbr, dil)) if s.get("alacak") else "", st["sag"]),
                     Paragraph(m(_pdf_para(s.get("bakiye") or 0, pbr, dil)), st["sag"])])
    if not v.get("satirlar"):
        veri.append([Paragraph("", st["govde"]), Paragraph(m(e["bos"]), st["kucuk"]), Paragraph("", st["govde"]),
                     Paragraph("", st["sag"]), Paragraph("", st["sag"]), Paragraph("", st["sag"])])
    t = Table(veri, colWidths=[23 * mm, 63 * mm, 23 * mm, 24 * mm, 24 * mm, 23 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), pb.VURGU_ACIK), ("LINEBELOW", (0, 0), (-1, 0), 0.8, pb.VURGU),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.3, pb.CIZGI), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    parcalar += [t, Spacer(1, 3 * mm)]
    kapanis = int(v.get("kapanis") or 0)
    yon = e["borclu"] if kapanis > 0 else (e["alacakli"] if kapanis < 0 else "")
    toplamlar = [(f"{e['toplam']} {e['borc']}", _pdf_para(v.get("toplam_borc") or 0, pbr, dil), False),
                 (f"{e['toplam']} {e['alacak']}", _pdf_para(v.get("toplam_alacak") or 0, pbr, dil), False),
                 (f"{e['kapanis']} {yon}".strip(), _pdf_para(kapanis, pbr, dil), True)]
    parcalar.append(KeepTogether(pb._toplam_tablosu(toplamlar, st)))  # noqa: SLF001
    return pb._uret(parcalar, e["not"], "tr" if dil == "tr" else "en", f"{e['ekstre']} {c.get('ad') or ''}")  # noqa: SLF001


def hareketler_pdf(v: Dict[str, Any], dil: str = "tr") -> bytes:
    """`v`: {"firma", "bas", "bit", "satirlar": [{tarih, tur, aciklama, kategori, hesap, tutar, kdv, para_birimi}],
    "toplamlar": [{para_birimi, gelir, gider, net}]}."""
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Spacer, Table, TableStyle

    from services.pdf_yazi import Paragraf as Paragraph  # çok dilli paragraf (Faz 7K yazı tipi yedeği)
    from services import pdf_belge as pb

    dil = pdf_dili(dil)
    e = PDF_ETIKET[dil]
    st = pb._stiller()  # noqa: SLF001
    m = pb._metin  # noqa: SLF001
    sol = [Paragraph(f"<b>{m(v.get('firma') or '')}</b>" if v.get("firma") else "&nbsp;", st["govde"])]
    donem = f"{_pdf_tarih(v.get('bas'))} – {_pdf_tarih(v.get('bit'))}" if v.get("bas") or v.get("bit") else "—"
    parcalar: List[Any] = [pb._baslik_blogu(sol, e["hareketler"], [(e["donem"], donem)], st), pb._ayrac(), Spacer(1, 3 * mm)]  # noqa: SLF001
    basliklar = [e["tarih"], e["tur"], e["aciklama"], e["kategori"], e["kdv"], e["tutar"]]
    veri: List[List[Any]] = [[Paragraph(f"<b>{m(b)}</b>", st["govde"] if i < 4 else st["sag"]) for i, b in enumerate(basliklar)]]
    for s in v.get("satirlar") or []:
        tur = e.get(s.get("tur") or "", s.get("tur") or "")
        if s.get("ters"):
            tur = f"{tur} ({e['ters']})"
        aciklama = s.get("aciklama") or ""
        if s.get("hesap"):
            aciklama = f"{aciklama} · {s['hesap']}" if aciklama else s["hesap"]
        veri.append([Paragraph(_pdf_tarih(s.get("tarih")), st["govde"]), Paragraph(m(tur), st["govde"]),
                     Paragraph(m(aciklama), st["govde"]), Paragraph(m(s.get("kategori") or ""), st["govde"]),
                     Paragraph(m(_pdf_para(s.get("kdv") or 0, s.get("para_birimi") or "TRY", dil)) if s.get("kdv") else "", st["sag"]),
                     Paragraph(m(_pdf_para(s.get("tutar") or 0, s.get("para_birimi") or "TRY", dil)), st["sag"])])
    if not v.get("satirlar"):
        veri.append([Paragraph("", st["govde"]), Paragraph("", st["govde"]), Paragraph(m(e["bos"]), st["kucuk"]),
                     Paragraph("", st["govde"]), Paragraph("", st["sag"]), Paragraph("", st["sag"])])
    t = Table(veri, colWidths=[23 * mm, 24 * mm, 59 * mm, 34 * mm, 18 * mm, 22 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), pb.VURGU_ACIK), ("LINEBELOW", (0, 0), (-1, 0), 0.8, pb.VURGU),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.3, pb.CIZGI), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    parcalar += [t, Spacer(1, 3 * mm)]
    toplamlar = []
    for tp in v.get("toplamlar") or []:
        pbr = tp.get("para_birimi") or "TRY"
        toplamlar += [(f"{e['gelir']} ({pbr})", _pdf_para(tp.get("gelir") or 0, pbr, dil), False),
                      (f"{e['gider']} ({pbr})", _pdf_para(tp.get("gider") or 0, pbr, dil), False),
                      (f"{e['toplam']} ({pbr})", _pdf_para(tp.get("net") or 0, pbr, dil), True)]
    if toplamlar:
        parcalar.append(KeepTogether(pb._toplam_tablosu(toplamlar, st)))  # noqa: SLF001
    return pb._uret(parcalar, e["not"], "tr" if dil == "tr" else "en", e["hareketler"])  # noqa: SLF001
