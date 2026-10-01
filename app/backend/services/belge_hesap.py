"""Faz 3T — teklif ve fatura kalemlerinin TEK hesap yeri (Decimal, kuruş doğruluğu).

Neden sunucuda?
---------------
Teklifin ve faturanın toplamı bir borç belgesi: istemcinin gönderdiği
"ara toplam / KDV / genel toplam" sayılarına güvenilmiyor. İstemci yalnız
kalemleri (açıklama, adet, birim fiyat, KDV oranı, indirim yüzdesi) yolluyor;
toplamlar burada yeniden hesaplanıyor ve kayda bu değerler yazılıyor.

Yuvarlama
---------
`float` yerine `Decimal`: 0.1 + 0.2 türü ikili kesir hataları kuruşa
taşınmasın. Kural (e-Fatura uygulamasıyla aynı yön): her KALEM kendi içinde
kuruşa yuvarlanıyor (yarım yukarı — ROUND_HALF_UP), belge toplamları
yuvarlanmış kalemlerin toplamı. Böylece PDF'teki satırların toplamı her
zaman alttaki toplamla birebir tutuyor.

    brüt       = adet × birim fiyat                  (kuruşa yuvarlanır)
    indirim    = brüt × indirim% / 100               (kuruşa yuvarlanır)
    matrah     = brüt − indirim
    KDV        = matrah × KDV% / 100                 (kuruşa yuvarlanır)
    satır top. = matrah + KDV

    ara toplam   = Σ matrah        indirim toplamı = Σ indirim
    KDV toplamı  = Σ KDV           genel toplam    = ara toplam + KDV toplamı

KDV dökümü oran başına (matrah, KDV) — PDF'te ve ekranda gösteriliyor.

İade (alacak) faturası için `eksi_olabilir=True`: adet eksi verilebiliyor,
toplamlar eksi çıkıyor.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

KURUS = Decimal("0.01")
SIFIR = Decimal("0")
YUZ = Decimal("100")

EN_COK_KALEM = 100
ACIKLAMA_SINIRI = 500
#: Tek kalemde ve belgede makul üst sınır (yanlış yazılmış sıfırları yakalar).
TUTAR_SINIRI = Decimal("100000000")
ADET_SINIRI = Decimal("1000000")
PARA_BIRIMLERI = ("TRY", "USD", "EUR", "GBP")


class HesapHatasi(ValueError):
    """Ön yüzün yedi dilde metin kurduğu hata: `kod` (+ kalem sırası)."""

    def __init__(self, kod: str, sira: Optional[int] = None):
        super().__init__(kod)
        self.kod = kod
        self.sira = sira

    def detay(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"kod": self.kod}
        if self.sira is not None:
            d["sira"] = self.sira
        return d


def kurus(deger: Decimal) -> Decimal:
    return deger.quantize(KURUS, rounding=ROUND_HALF_UP)


def ondalik(deger: Any, kod: str = "sayi_gecersiz", sira: Optional[int] = None) -> Decimal:
    """Sayı/metin → Decimal. `float` metne çevrilerek alınıyor (0.1 → "0.1")."""
    if deger is None or deger == "":
        raise HesapHatasi(kod, sira)
    if isinstance(deger, bool):
        raise HesapHatasi(kod, sira)
    try:
        if isinstance(deger, float):
            sonuc = Decimal(repr(deger))
        elif isinstance(deger, str):
            sonuc = Decimal(deger.strip().replace(",", "."))
        else:
            sonuc = Decimal(deger)
    except (InvalidOperation, ValueError, TypeError):
        raise HesapHatasi(kod, sira)
    if not sonuc.is_finite():
        raise HesapHatasi(kod, sira)
    return sonuc


def para_birimi_duzelt(deger: Optional[str], varsayilan: str = "TRY") -> str:
    para = (deger or varsayilan).strip().upper()
    if para not in PARA_BIRIMLERI:
        raise HesapHatasi("para_birimi_gecersiz")
    return para


@dataclass
class KalemSonucu:
    aciklama: str
    adet: Decimal
    birim_fiyat: Decimal
    kdv_orani: Decimal
    indirim: Decimal
    brut: Decimal
    indirim_tutari: Decimal
    matrah: Decimal
    kdv: Decimal
    toplam: Decimal

    def sozluk(self) -> Dict[str, Any]:
        """Kayda (JSON) yazılan ve API'nin döndürdüğü biçim — sayılar metin değil sayı."""
        return {
            "aciklama": self.aciklama,
            "adet": _sayi(self.adet),
            "birim_fiyat": _sayi(self.birim_fiyat),
            "kdv_orani": _sayi(self.kdv_orani),
            "indirim": _sayi(self.indirim),
            "matrah": _sayi(self.matrah),
            "indirim_tutari": _sayi(self.indirim_tutari),
            "kdv": _sayi(self.kdv),
            "toplam": _sayi(self.toplam),
        }


@dataclass
class BelgeSonucu:
    kalemler: List[KalemSonucu] = field(default_factory=list)
    ara_toplam: Decimal = SIFIR
    indirim_toplam: Decimal = SIFIR
    kdv_toplam: Decimal = SIFIR
    genel_toplam: Decimal = SIFIR
    #: oran → {"matrah", "kdv"}
    kdv_dokumu: List[Dict[str, Any]] = field(default_factory=list)

    def ozet(self) -> Dict[str, Any]:
        return {
            "ara_toplam": _sayi(self.ara_toplam),
            "indirim_toplam": _sayi(self.indirim_toplam),
            "kdv_toplam": _sayi(self.kdv_toplam),
            "genel_toplam": _sayi(self.genel_toplam),
            "kdv_dokumu": self.kdv_dokumu,
        }

    def kalem_listesi(self) -> List[Dict[str, Any]]:
        return [k.sozluk() for k in self.kalemler]


def _sayi(d: Decimal) -> float:
    """JSON'a sayı olarak: kuruşa yuvarlanmış Decimal'ın float'ı tam iki basamak gösterir."""
    # Para alanları zaten kuruşta; adet/oran en çok 4 basamak — float bunu kesin gösterir.
    return float(d)


def kalem_hesapla(ham: Any, sira: int = 0, *, eksi_olabilir: bool = False) -> KalemSonucu:
    if not isinstance(ham, dict):
        raise HesapHatasi("kalem_gecersiz", sira)
    aciklama = " ".join(str(ham.get("aciklama") or "").split())[:ACIKLAMA_SINIRI]
    if not aciklama:
        raise HesapHatasi("aciklama_gerekli", sira)
    adet = ondalik(ham.get("adet", 1), "adet_gecersiz", sira)
    birim = ondalik(ham.get("birim_fiyat"), "birim_fiyat_gecersiz", sira)
    kdv_orani = ondalik(ham.get("kdv_orani", 0) if ham.get("kdv_orani") is not None else 0, "kdv_gecersiz", sira)
    indirim = ondalik(ham.get("indirim", 0) if ham.get("indirim") is not None else 0, "indirim_gecersiz", sira)

    if adet == 0 or abs(adet) > ADET_SINIRI or (adet < 0 and not eksi_olabilir):
        raise HesapHatasi("adet_gecersiz", sira)
    if adet.as_tuple().exponent < -4:
        raise HesapHatasi("adet_gecersiz", sira)
    if birim < 0 or birim > TUTAR_SINIRI:
        raise HesapHatasi("birim_fiyat_gecersiz", sira)
    if kdv_orani < 0 or kdv_orani > YUZ:
        raise HesapHatasi("kdv_gecersiz", sira)
    if indirim < 0 or indirim > YUZ:
        raise HesapHatasi("indirim_gecersiz", sira)

    brut = kurus(adet * birim)
    indirim_tutari = kurus(brut * indirim / YUZ)
    matrah = brut - indirim_tutari
    kdv = kurus(matrah * kdv_orani / YUZ)
    return KalemSonucu(
        aciklama=aciklama,
        adet=adet,
        birim_fiyat=birim,
        kdv_orani=kdv_orani,
        indirim=indirim,
        brut=brut,
        indirim_tutari=indirim_tutari,
        matrah=matrah,
        kdv=kdv,
        toplam=matrah + kdv,
    )


def belge_hesapla(kalemler: Any, *, eksi_olabilir: bool = False, bos_olabilir: bool = False) -> BelgeSonucu:
    """Kalem listesinden belge toplamlarını hesaplar (istemci toplamı yok sayılır)."""
    if kalemler is None:
        kalemler = []
    if not isinstance(kalemler, list):
        raise HesapHatasi("kalemler_gecersiz")
    if not kalemler and not bos_olabilir:
        raise HesapHatasi("kalem_gerekli")
    if len(kalemler) > EN_COK_KALEM:
        raise HesapHatasi("kalem_cok")
    sonuc = BelgeSonucu()
    dokum: Dict[Decimal, Dict[str, Decimal]] = {}
    for i, ham in enumerate(kalemler):
        k = kalem_hesapla(ham, i, eksi_olabilir=eksi_olabilir)
        sonuc.kalemler.append(k)
        sonuc.ara_toplam += k.matrah
        sonuc.indirim_toplam += k.indirim_tutari
        sonuc.kdv_toplam += k.kdv
        satir = dokum.setdefault(k.kdv_orani.normalize(), {"matrah": SIFIR, "kdv": SIFIR})
        satir["matrah"] += k.matrah
        satir["kdv"] += k.kdv
    sonuc.genel_toplam = sonuc.ara_toplam + sonuc.kdv_toplam
    if abs(sonuc.genel_toplam) > TUTAR_SINIRI:
        raise HesapHatasi("toplam_cok_buyuk")
    sonuc.kdv_dokumu = [
        {"oran": _sayi(oran), "matrah": _sayi(d["matrah"]), "kdv": _sayi(d["kdv"])}
        for oran, d in sorted(dokum.items(), key=lambda x: x[0])
    ]
    return sonuc


def kayitli_kalemler(metin: Optional[str]) -> List[Dict[str, Any]]:
    """Kayıttaki JSON metni → liste (bozuksa boş)."""
    import json

    if not metin:
        return []
    try:
        deger = json.loads(metin)
    except (TypeError, ValueError):
        return []
    return deger if isinstance(deger, list) else []


def oranla_bol(belge: BelgeSonucu, yuzde: Decimal, aciklama_kalibi: str) -> List[Dict[str, Any]]:
    """Peşinat faturası kalemleri: KDV oranı başına matrahın `yuzde`si.

    Kalemleri tek tek ölçeklemek birim fiyatları bozardı; oran başına tek
    kalem hem KDV'yi doğru tutuyor hem de faturada okunur kalıyor.
    `aciklama_kalibi` içinde `{oran}` yer tutucusu KDV oranıyla doluyor.
    """
    kalemler = []
    for satir in belge.kdv_dokumu:
        matrah = ondalik(satir["matrah"])
        tutar = kurus(matrah * yuzde / YUZ)
        if tutar == 0:
            continue
        kalemler.append(
            {
                "aciklama": aciklama_kalibi.format(oran=f"{satir['oran']:g}"),
                "adet": 1,
                "birim_fiyat": float(tutar),
                "kdv_orani": satir["oran"],
                "indirim": 0,
            }
        )
    return kalemler
