"""Faz 6P — Stok ve satış noktası: kurallar, doğrulama, barkod, KDV ve sepet hesabı.

Bu dosya veritabanına dokunmuyor (saf fonksiyonlar); kayıt işleri `services/stok_kayit.py`, PDF
`services/stok_pdf.py`, uçlar `routers/stok_pos.py`.

Para ve miktar
--------------
* Tutarlar TAM SAYI kuruş (Faz 3T/4M deseni); satış fiyatı KDV DAHİL (raf fiyatı), alış fiyatı
  KDV HARİÇ birim maliyet.
* Miktarlar TAM SAYI binde bir: 1 adet = 1000, 1,25 kg = 1250. `adet`/`paket` biriminde kesir yok.

KDV
---
Türkiye'de güncel oranlar (10 Temmuz 2023'ten beri) %1, %10, %20; %0 istisna/muaf satırlar için.
TEK yer: `KDV_ORANLARI`; hesap ayarında (`stok_ayarlari.kdv_oranlari`) değiştirilebilir. KDV raf
fiyatının içinden çıkarılır: kdv = tutar × oran / (100 + oran), yarım yukarı. Fiş/raporun KDV
dökümü ORAN BAŞINA TOPLAM üzerinden hesaplanır (satır satır yuvarlamanın birikmesi yok); satırlara
düşen KDV, grubun KDV'si en büyük kalan yöntemiyle dağıtılarak bulunur (toplamlar birebir tutar).

Yasal not
---------
Bu modülün fişi ve gün sonu raporu MALİ DEĞİLDİR: ÖKC (yeni nesil yazar kasa) fişi, Z raporu ya da
e-Arşiv faturanın yerine geçmez; metinler bunu açıkça yazar. Kart ödemesi yalnız kayıttır (POS
cihazı entegrasyonu yok). Satıştan kesilen fatura bilgi amaçlı PDF'tir (e-Arşiv entegrasyonu sonra).
"""

import csv
import io
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from services import qr_menu as mk

MODUL = "stok_pos"
IZIN_STOK = "stok"
IZIN_KASA = "kasa"

UTC = timezone.utc

#: Türkiye KDV oranları (tek yer). Hesap ayarı boşsa bunlar geçerli.
KDV_ORANLARI: Tuple[int, ...] = (0, 1, 10, 20)
VARSAYILAN_KDV = 20
BIRIMLER: Tuple[str, ...] = ("adet", "kg", "lt", "m", "paket")
#: Kesirli miktar kabul etmeyen birimler.
TAM_BIRIMLER = frozenset({"adet", "paket"})
ODEME_TURLERI: Tuple[str, ...] = ("nakit", "kart", "havale", "karma")
IADE_ODEME_TURLERI: Tuple[str, ...] = ("nakit", "kart", "havale")
#: Elle stok hareketi türleri (satış/iade/sayım/transfer kendi uçlarından).
ELLE_HAREKETLER: Tuple[str, ...] = ("giris", "cikis", "fire", "duzeltme")
HAREKET_TURLERI: Tuple[str, ...] = (
    "giris", "cikis", "satis", "iade", "iptal", "fire", "sayim", "transfer_cikis", "transfer_giris", "duzeltme",
)
PARA_BIRIMLERI: Tuple[str, ...] = ("TRY", "USD", "EUR", "GBP")
ALICI_TURLERI: Tuple[str, ...] = ("bireysel", "kurumsal")

VARSAYILAN_URUN_SINIRI = 1000
VARSAYILAN_SUBE_SINIRI = 1
VARSAYILAN_KASA_KULLANICI_SINIRI = 3
EN_COK_KALEM = 200
EN_COK_FIYAT = 100_000_000  # kuruş (1 milyon)
EN_COK_MIKTAR = 1_000_000_000  # binde bir (1 milyon birim)
CSV_EN_COK_BAYT = 1024 * 1024
CSV_EN_COK_SATIR = 3000
ETIKET_EN_COK = 300
HAREKETSIZ_GUN = 30
#: Barkod: EAN-8/EAN-13 (rakam) ya da Code128'in yazdırılabilir ASCII alt kümesi.
_SERBEST_KOD = re.compile(r"^[A-Za-z0-9\-._/+]{1,32}$")

FIS_NOTU_TR = "Bu belge mali fiş değildir; ÖKC fişi / e-Arşiv belge yerine geçmez."
Z_NOTU_TR = "Mali değildir: ÖKC (yazar kasa) Z raporu yerine geçmez."


class StokHatasi(Exception):
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
    """Testler bu fonksiyonu sabit bir ana çevirebilir."""
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


def _tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Europe/Istanbul")
    except Exception:  # noqa: BLE001 - tz veritabanı yoksa Türkiye UTC+3 (yaz saati yok)
        return timezone(timedelta(hours=3))


def tr_gunu(an: Optional[datetime] = None) -> date:
    return utc(an or simdi()).astimezone(_tz()).date()


def gun_araligi(bas: date, bit: date) -> Tuple[datetime, datetime]:
    """İstanbul günlerinden [bas 00:00, bit+1 00:00) UTC aralığı."""
    tz = _tz()
    b = datetime(bas.year, bas.month, bas.day, tzinfo=tz).astimezone(UTC)
    s = datetime(bit.year, bit.month, bit.day, tzinfo=tz).astimezone(UTC) + timedelta(days=1)
    return b, s


def tarih_coz(ham: Any, alan: str, varsayilan: Optional[date] = None) -> date:
    if ham in (None, ""):
        if varsayilan is None:
            raise StokHatasi("zorunlu", alan)
        return varsayilan
    try:
        return date.fromisoformat(str(ham).strip()[:10])
    except ValueError:
        raise StokHatasi("tarih_gecersiz", alan)


# ---------------------------------------------------------------------------
# Ortak doğrulama (QR menü yardımcıları üstüne)
# ---------------------------------------------------------------------------
def _cevir(fonk, *a, **k):
    try:
        return fonk(*a, **k)
    except mk.MenuHatasi as h:
        raise StokHatasi(h.kod, h.alan, durum=h.durum, **h.ek)


def metin(ham: Any, alan: str, sinir: int, zorunlu: bool = False, cok_satir: bool = False) -> str:
    return _cevir(mk.metin, ham, alan, sinir, zorunlu=zorunlu, cok_satir=cok_satir)


def bos_ya_da(ham: Any, alan: str, sinir: int, cok_satir: bool = False) -> Optional[str]:
    return metin(ham, alan, sinir, cok_satir=cok_satir) or None


def tam_sayi(ham: Any, alan: str, en_az: int, en_cok: int, bos_olabilir: bool = True) -> Optional[int]:
    return _cevir(mk.tam_sayi, ham, alan, en_az, en_cok, bos_olabilir=bos_olabilir)


def kurus(ham: Any, alan: str, bos_olabilir: bool = False) -> Optional[int]:
    deger = _cevir(mk.kurusa_cevir, ham, alan, bos_olabilir=bos_olabilir)
    if deger is not None and deger > EN_COK_FIYAT:
        raise StokHatasi("fiyat_cok_buyuk", alan)
    return deger


def evet_hayir(ham: Any, alan: str) -> bool:
    if isinstance(ham, bool):
        return ham
    raise StokHatasi("evet_hayir_gecersiz", alan)


def eposta(ham: Any, alan: str = "eposta") -> Optional[str]:
    d = metin(ham, alan, 254).lower()
    if not d:
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", d):
        raise StokHatasi("eposta_gecersiz", alan)
    return d


def json_yukle(ham: Any, varsayilan: Any = None) -> Any:
    return mk.json_yukle(ham, varsayilan)


def json_yaz(deger: Any) -> str:
    return mk.json_yaz(deger)


def tl(kurus_: Optional[int]) -> float:
    return round((kurus_ or 0) / 100, 2)


# ---------------------------------------------------------------------------
# Miktar (binde bir)
# ---------------------------------------------------------------------------
def miktar_coz(ham: Any, alan: str, birim: str = "adet", *, sifir_olabilir: bool = False, eksi_olabilir: bool = False) -> int:
    """1 / 1.5 / "1,250" → binde bir tam sayı. `adet`/`paket` biriminde kesir yok."""
    if ham in (None, "") or isinstance(ham, bool):
        raise StokHatasi("miktar_gecersiz", alan)
    try:
        d = Decimal(repr(float(ham)) if isinstance(ham, float) else str(ham).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        raise StokHatasi("miktar_gecersiz", alan)
    if not d.is_finite():
        raise StokHatasi("miktar_gecersiz", alan)
    binde = int((d * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if binde < 0 and not eksi_olabilir:
        raise StokHatasi("miktar_gecersiz", alan)
    if binde == 0 and not sifir_olabilir:
        raise StokHatasi("miktar_gecersiz", alan)
    if abs(binde) > EN_COK_MIKTAR:
        raise StokHatasi("miktar_cok_buyuk", alan)
    if birim in TAM_BIRIMLER and binde % 1000:
        raise StokHatasi("miktar_tam_olmali", alan)
    return binde


def miktar_yaz(binde: Optional[int]) -> Optional[float]:
    if binde is None:
        return None
    return round(binde / 1000, 3)


def yuvarla(pay: int, carpan: int, bolen: int) -> int:
    """pay × çarpan / bölen, yarım yukarı (sıfırdan uzağa) — tam sayı aritmetiği."""
    if bolen == 0:
        return 0
    deger = pay * carpan
    isaret = -1 if (deger < 0) != (bolen < 0) else 1
    deger, bolen = abs(deger), abs(bolen)
    return isaret * ((2 * deger + bolen) // (2 * bolen))


def dagit(toplam: int, agirliklar: Sequence[int]) -> List[int]:
    """`toplam`ı ağırlıklarla orantılı tam sayılara böler (en büyük kalan): Σ = toplam."""
    n = len(agirliklar)
    if n == 0:
        return []
    agirlik_toplam = sum(max(0, a) for a in agirliklar)
    if agirlik_toplam <= 0 or toplam == 0:
        return [0] * n
    paylar, kalanlar = [], []
    for i, a in enumerate(agirliklar):
        tam, kalan = divmod(toplam * max(0, a), agirlik_toplam)
        paylar.append(tam)
        kalanlar.append((kalan, -i))
    eksik = toplam - sum(paylar)
    for _, eksi_i in sorted(kalanlar, reverse=True)[:eksik]:
        paylar[-eksi_i] += 1
    return paylar


# ---------------------------------------------------------------------------
# Barkod
# ---------------------------------------------------------------------------
def ean_kontrol_hanesi(govde: str) -> int:
    """EAN-8/EAN-13/UPC kontrol hanesi: sağdan başlayarak tek konumlar ×3."""
    if not govde.isdigit():
        raise ValueError("rakam")
    toplam = 0
    for i, rakam in enumerate(reversed(govde)):
        toplam += int(rakam) * (3 if i % 2 == 0 else 1)
    return (10 - toplam % 10) % 10


def ean_gecerli_mi(kod: str) -> bool:
    return kod.isdigit() and len(kod) in (8, 12, 13, 14) and ean_kontrol_hanesi(kod[:-1]) == int(kod[-1])


def ic_barkod_uret(rastgele: Optional[Any] = None) -> str:
    """Mağaza içi EAN-13: GS1 "kısıtlı dolaşım" öneki 20 + 10 rastgele hane + kontrol hanesi."""
    r = rastgele or secrets.SystemRandom()
    govde = "20" + "".join(str(r.randrange(10)) for _ in range(10))
    return govde + str(ean_kontrol_hanesi(govde))


def barkod_duzelt(ham: Any, alan: str = "barkod") -> Optional[str]:
    """Boş → None (iç kod üretilecek). Rakamsa EAN-8/12/13 kontrol hanesi doğrulanır; değilse Code128 serbest kod."""
    if ham is None:
        return None
    kod = re.sub(r"\s+", "", str(ham))
    if not kod:
        return None
    if kod.isdigit() and len(kod) in (8, 12, 13):
        if not ean_gecerli_mi(kod):
            raise StokHatasi("barkod_kontrol_hanesi", alan, beklenen=ean_kontrol_hanesi(kod[:-1]))
        return kod
    if not _SERBEST_KOD.match(kod):
        raise StokHatasi("barkod_gecersiz", alan)
    return kod


def barkod_turu(kod: str) -> str:
    if kod.isdigit() and len(kod) == 13 and ean_gecerli_mi(kod):
        return "ean13"
    if kod.isdigit() and len(kod) == 8 and ean_gecerli_mi(kod):
        return "ean8"
    return "code128"


def okutma_kodu(ham: Any) -> str:
    """Okuyucudan gelen kodu sadeleştirir (boşluk/denetim karakteri yok, en çok 64)."""
    return re.sub(r"[\s\x00-\x1f]+", "", str(ham or ""))[:64]


# ---------------------------------------------------------------------------
# KDV
# ---------------------------------------------------------------------------
def kdv_oranlari(ayar_ham: Optional[str]) -> List[int]:
    liste = json_yukle(ayar_ham, None)
    if isinstance(liste, list) and liste and all(isinstance(x, int) and not isinstance(x, bool) for x in liste):
        return sorted(set(liste))
    return list(KDV_ORANLARI)


def kdv_oranlari_duzelt(ham: Any) -> List[int]:
    if not isinstance(ham, list) or not 1 <= len(ham) <= 8:
        raise StokHatasi("kdv_oranlari_gecersiz", "kdv_oranlari")
    sonuc = set()
    for x in ham:
        sonuc.add(tam_sayi(x, "kdv_oranlari", 0, 100, bos_olabilir=False))
    return sorted(sonuc)


def kdv_ayir(brut: int, oran: int) -> int:
    """KDV dahil tutarın içindeki KDV (yarım yukarı)."""
    if oran <= 0 or brut == 0:
        return 0
    return yuvarla(brut, oran, 100 + oran)


# ---------------------------------------------------------------------------
# Sepet hesabı
# ---------------------------------------------------------------------------
@dataclass
class KalemGirdi:
    urun_id: int
    ad: str
    barkod: Optional[str]
    birim: str
    adet: int  # binde bir
    birim_fiyat: int  # kuruş, KDV dahil
    kdv_orani: int
    birim_maliyet: int = 0
    satir_indirim: int = 0  # kuruş


@dataclass
class KalemSonuc:
    girdi: KalemGirdi
    brut: int
    satir_indirim: int
    pay: int
    tutar: int
    kdv: int

    @property
    def indirim(self) -> int:
        return self.satir_indirim + self.pay


@dataclass
class SepetSonucu:
    kalemler: List[KalemSonuc]
    ara_toplam: int
    satir_indirim: int
    toplam_indirim: int
    toplam: int
    kdv_toplam: int
    kdv_dokumu: List[Dict[str, int]] = field(default_factory=list)

    def sozluk(self) -> Dict[str, Any]:
        return {
            "ara_toplam": self.ara_toplam, "satir_indirim": self.satir_indirim, "toplam_indirim": self.toplam_indirim,
            "toplam": self.toplam, "kdv_toplam": self.kdv_toplam, "kdv_dokumu": self.kdv_dokumu,
            "kalemler": [{"urun_id": k.girdi.urun_id, "brut": k.brut, "indirim": k.indirim, "tutar": k.tutar, "kdv": k.kdv}
                         for k in self.kalemler],
        }


def kdv_dokumu_hesapla(satirlar: Iterable[Tuple[int, int]]) -> List[Dict[str, int]]:
    """(oran, KDV dahil tutar) → oran başına {oran, tutar, matrah, kdv} — KDV grup toplamından."""
    gruplar: Dict[int, int] = {}
    for oran, tutar in satirlar:
        gruplar[oran] = gruplar.get(oran, 0) + tutar
    sonuc = []
    for oran in sorted(gruplar):
        tutar = gruplar[oran]
        kdv = kdv_ayir(tutar, oran)
        sonuc.append({"oran": oran, "tutar": tutar, "matrah": tutar - kdv, "kdv": kdv})
    return sonuc


def sepet_hesapla(kalemler: Sequence[KalemGirdi], toplam_indirim: int = 0) -> SepetSonucu:
    """Satır tutarı = birim fiyat × miktar − satır indirimi; toplam indirim satırlara orantılı dağıtılır."""
    if not kalemler:
        raise StokHatasi("sepet_bos", "kalemler")
    ara: List[Tuple[KalemGirdi, int, int]] = []
    for k in kalemler:
        brut = yuvarla(k.birim_fiyat, k.adet, 1000)
        satir_ind = max(0, min(int(k.satir_indirim or 0), brut))
        ara.append((k, brut, satir_ind))
    netler = [brut - ind for _, brut, ind in ara]
    net_toplam = sum(netler)
    toplam_ind = max(0, min(int(toplam_indirim or 0), net_toplam))
    paylar = dagit(toplam_ind, netler)
    sonuclar: List[KalemSonuc] = []
    for (k, brut, ind), net, pay in zip(ara, netler, paylar):
        sonuclar.append(KalemSonuc(girdi=k, brut=brut, satir_indirim=ind, pay=pay, tutar=net - pay, kdv=0))
    dokum = kdv_dokumu_hesapla((s.girdi.kdv_orani, s.tutar) for s in sonuclar)
    # Grubun KDV'si satırlara (tutarlarıyla orantılı) dağıtılır: satır KDV'lerinin toplamı = döküm.
    for d in dokum:
        grup = [s for s in sonuclar if s.girdi.kdv_orani == d["oran"]]
        for s, kdv in zip(grup, dagit(d["kdv"], [s.tutar for s in grup])):
            s.kdv = kdv
    return SepetSonucu(
        kalemler=sonuclar,
        ara_toplam=sum(b for _, b, _ in ara),
        satir_indirim=sum(i for _, _, i in ara),
        toplam_indirim=toplam_ind,
        toplam=net_toplam - toplam_ind,
        kdv_toplam=sum(d["kdv"] for d in dokum),
        kdv_dokumu=dokum,
    )


def indirim_yuzdesi(sonuc: SepetSonucu) -> Decimal:
    """Verilen toplam indirimin (satır + toplam) brüte oranı (yüzde)."""
    if sonuc.ara_toplam <= 0:
        return Decimal(0)
    return Decimal(sonuc.satir_indirim + sonuc.toplam_indirim) * 100 / Decimal(sonuc.ara_toplam)


def odeme_coz(ham: Any, toplam: int) -> Dict[str, Any]:
    """Ödeme gövdesi → {tur, nakit, kart, havale, nakit_alinan, para_ustu}.

    * `nakit` / `kart` / `havale`: toplamın tamamı o türle. Nakitte `nakit_alinan` (yoksa = toplam)
      toplamdan az olamaz; fark para üstü.
    * `karma`: `kart` + `havale` tutarları verilir, kalan nakit (eksi olamaz); `nakit_alinan` kalan nakit
      için.
    """
    if not isinstance(ham, dict):
        raise StokHatasi("odeme_gecersiz", "odeme")
    tur = ham.get("tur")
    if tur not in ODEME_TURLERI:
        raise StokHatasi("odeme_turu_gecersiz", "odeme.tur")
    nakit = kart = havale = 0
    if tur == "nakit":
        nakit = toplam
    elif tur == "kart":
        kart = toplam
    elif tur == "havale":
        havale = toplam
    else:
        kart = kurus(ham.get("kart"), "odeme.kart", bos_olabilir=True) or 0
        havale = kurus(ham.get("havale"), "odeme.havale", bos_olabilir=True) or 0
        nakit = toplam - kart - havale
        if nakit < 0:
            raise StokHatasi("odeme_fazla", "odeme", toplam=toplam)
    alinan = kurus(ham.get("nakit_alinan"), "odeme.nakit_alinan", bos_olabilir=True)
    if alinan is None:
        alinan = nakit
    if alinan < nakit:
        raise StokHatasi("nakit_yetersiz", "odeme.nakit_alinan", gereken=nakit)
    if nakit == 0 and alinan > 0:
        alinan = 0
    return {"tur": tur, "nakit": nakit, "kart": kart, "havale": havale, "nakit_alinan": alinan, "para_ustu": alinan - nakit}


def iade_tutari(tutar: int, adet: int, onceki_iade_adet: int, onceki_iade_tutar: int, iade_adet: int) -> int:
    """Satırın kalan tutarından iade payı: son birimler kalanın tamamını alır (yuvarlama birikmesin)."""
    if onceki_iade_adet + iade_adet >= adet:
        return tutar - onceki_iade_tutar
    return yuvarla(tutar, iade_adet, adet)


# ---------------------------------------------------------------------------
# Ürün doğrulaması
# ---------------------------------------------------------------------------
def birim_duzelt(ham: Any) -> str:
    b = str(ham or "adet").strip().lower()
    if b not in BIRIMLER:
        raise StokHatasi("birim_gecersiz", "birim")
    return b


def kdv_duzelt(ham: Any, oranlar: Sequence[int], alan: str = "kdv_orani") -> int:
    oran = tam_sayi(ham, alan, 0, 100, bos_olabilir=False)
    if oran not in oranlar:
        raise StokHatasi("kdv_orani_gecersiz", alan, oranlar=list(oranlar))
    return oran


def varyant_duzelt(ham: Any) -> Optional[Dict[str, str]]:
    if ham in (None, "", {}):
        return None
    if not isinstance(ham, dict):
        raise StokHatasi("varyant_gecersiz", "varyant")
    sonuc = {}
    for anahtar in ("beden", "renk"):
        d = metin(ham.get(anahtar), f"varyant.{anahtar}", 40)
        if d:
            sonuc[anahtar] = d
    return sonuc or None


def varyant_adi(ana_ad: str, varyant: Optional[Dict[str, str]]) -> str:
    if not varyant:
        return ana_ad
    ek = " / ".join(v for v in (varyant.get("beden"), varyant.get("renk")) if v)
    return f"{ana_ad} — {ek}"[:160] if ek else ana_ad


def vergi_no_duzelt(ham: Any, alan: str = "vergi_no") -> Optional[str]:
    d = re.sub(r"\s+", "", str(ham or ""))
    if not d:
        return None
    if not (d.isdigit() and len(d) in (10, 11)):
        raise StokHatasi("vergi_no_gecersiz", alan)
    return d


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
CSV_ALANLARI: Tuple[str, ...] = (
    "barkod", "sku", "ad", "kategori", "birim", "alis_fiyati", "satis_fiyati", "kdv_orani", "kritik_esik", "stok",
)
_BASLIK_ESLEME = {
    "barcode": "barkod", "kod": "barkod", "urun_adi": "ad", "urun": "ad", "name": "ad", "category": "kategori",
    "unit": "birim", "alis": "alis_fiyati", "maliyet": "alis_fiyati", "cost": "alis_fiyati", "satis": "satis_fiyati",
    "fiyat": "satis_fiyati", "price": "satis_fiyati", "kdv": "kdv_orani", "vat": "kdv_orani", "kritik": "kritik_esik",
    "stok_miktari": "stok", "miktar": "stok", "stock": "stok",
}


def _baslik(ham: str) -> str:
    tablo = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    a = re.sub(r"[^a-z0-9]+", "_", ham.strip().lower().translate(tablo)).strip("_")
    return _BASLIK_ESLEME.get(a, a)


def csv_coz(bayt: bytes) -> List[Dict[str, str]]:
    """CSV (virgül/noktalı virgül/sekme; UTF-8 ya da Windows-1254) → başlık anahtarlı satırlar."""
    if len(bayt) > CSV_EN_COK_BAYT:
        raise StokHatasi("dosya_buyuk", "dosya", durum=413, en_cok_kb=CSV_EN_COK_BAYT // 1024)
    try:
        metin_ = bayt.decode("utf-8-sig")
    except UnicodeDecodeError:
        metin_ = bayt.decode("cp1254", errors="replace")
    if not metin_.strip():
        raise StokHatasi("dosya_bos", "dosya")
    ornek = metin_[:4096]
    try:
        ayirici = csv.Sniffer().sniff(ornek, delimiters=",;\t").delimiter
    except csv.Error:
        ayirici = ";" if ornek.count(";") >= ornek.count(",") else ","
    okuyucu = csv.reader(io.StringIO(metin_), delimiter=ayirici)
    try:
        basliklar = [_baslik(h) for h in next(okuyucu)]
    except StopIteration as exc:
        raise StokHatasi("dosya_bos", "dosya") from exc
    if "ad" not in basliklar or "satis_fiyati" not in basliklar:
        raise StokHatasi("baslik_eksik", "dosya", gerekli=["ad", "satis_fiyati"])
    satirlar: List[Dict[str, str]] = []
    try:
        for satir in okuyucu:
            if not any(h.strip() for h in satir):
                continue
            if len(satirlar) >= CSV_EN_COK_SATIR:
                raise StokHatasi("cok_satir", "dosya", en_cok=CSV_EN_COK_SATIR)
            satirlar.append({basliklar[i]: (satir[i] if i < len(satir) else "") for i in range(len(basliklar))})
    except csv.Error as exc:
        raise StokHatasi("csv_bozuk", "dosya") from exc
    return satirlar


def csv_metni(basliklar: Sequence[str], satirlar: Iterable[Sequence[Any]]) -> str:
    """Excel'in Türkçe ayarıyla açılan CSV: UTF-8 BOM + noktalı virgül; formül enjeksiyonuna karşı kaçış."""
    tampon = io.StringIO()
    yazici = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
    yazici.writerow(basliklar)
    for satir in satirlar:
        yazici.writerow([_hucre(h) for h in satir])
    return "﻿" + tampon.getvalue()


def _hucre(deger: Any) -> Any:
    if deger is None:
        return ""
    if isinstance(deger, float):
        return f"{deger:.3f}".rstrip("0").rstrip(".").replace(".", ",")
    s = str(deger)
    if s[:1] in ("=", "+", "-", "@", "\t", "\r") and not re.fullmatch(r"-?\d+([.,]\d+)?", s):
        return "'" + s
    return s


def kurus_csv(k: Optional[int]) -> str:
    if k is None:
        return ""
    eksi = k < 0
    tam, kesir = divmod(abs(int(k)), 100)
    return f"{'-' if eksi else ''}{tam},{kesir:02d}"


# ---------------------------------------------------------------------------
# Numara
# ---------------------------------------------------------------------------
def fis_no(sayac: int) -> str:
    return f"S-{sayac:06d}"


def fatura_no(yil: int, sayac: int) -> str:
    return f"SF-{yil}-{sayac:06d}"


def istemci_kimligi_duzelt(ham: Any) -> Optional[str]:
    if ham in (None, ""):
        return None
    d = str(ham).strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{8,40}", d):
        raise StokHatasi("istemci_kimligi_gecersiz", "istemci_kimligi")
    return d


__all__ = [n for n in dir() if not n.startswith("_")]
