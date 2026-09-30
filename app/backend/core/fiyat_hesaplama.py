"""Fiyatlandırma v5 — tek doğru kaynak (single source of truth) hesaplama.

Hem `GET /api/v1/fiyat-hesapla` hem `POST /api/v1/fiyat-teklif` bu
fonksiyonu çağırır. Frontend hiçbir zaman fiyatı kendisi hesaplamaz —
paket kartı da, teklif de aynı sayıyı üretir (spec: "fiyat tutarlılığı
için kritik").
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class FiyatHesaplamaHatasi(Exception):
    pass


@dataclass
class FiyatSonucu:
    paket_fiyat: float
    eklentiler_toplami: float
    toplam: float
    para_birimi: str = "USD"
    formul_notu: Optional[str] = None
    eklenti_detay: List[dict] = field(default_factory=list)
    # AI vs PM paketi karta eklendiyse, periyoda göre tutarı (profil
    # çarpanı uygulanmaz — sabit fiyatlı hizmet).
    ai_pm_toplami: float = 0.0
    # Yalnız "kullandikca_ode": bu paketin aylık karşılığı kaç kredi.
    kredi: Optional[int] = None


GECERLI_PERIYOTLAR = ("tek_seferlik", "aylik", "yillik", "kullandikca_ode")

# Kullandıkça Öde: 1 kredi = 1 saat senior. Paket kartındaki "kaç kredi"
# gösterimi aylık tutarın bu taban birime bölünüp yukarı yuvarlanmasıdır
# (10 kredilik paketin kredi başı fiyatı).
KREDI_BIRIM_USD = 100.0

# Kredi paketleri — sitedeki kredi bloğuyla aynı. Satın alma tutarı
# buradan gelir, tarayıcıdan gelen tutara güvenilmez.
KREDI_PAKETLERI = {
    10: {"bonus": 0, "fiyat": 1000.0},
    25: {"bonus": 2, "fiyat": 2250.0},
    50: {"bonus": 5, "fiyat": 4000.0},
    100: {"bonus": 15, "fiyat": 7000.0},
}


def kredi_paketi(kredi: int) -> dict:
    """Kredi paketinin sunucudaki fiyatı ve toplam saati."""
    if kredi not in KREDI_PAKETLERI:
        raise FiyatHesaplamaHatasi(f"Bilinmeyen kredi paketi: {kredi}")
    p = KREDI_PAKETLERI[kredi]
    return {"kredi": kredi, "bonus": p["bonus"], "saat": kredi + p["bonus"], "fiyat": p["fiyat"]}


def hesapla(
    *,
    scale_kod: str,
    profile_kod: str,
    period: str,
    addon_kodlari: List[str],
    scale_baz_fiyatlari: Dict[str, float],
    profile_carpanlari: Dict[str, float],
    addon_fiyatlari: Dict[str, float],
    ai_pm_aylik: float = 0.0,
) -> FiyatSonucu:
    if scale_kod not in scale_baz_fiyatlari:
        raise FiyatHesaplamaHatasi(f"Bilinmeyen ölçek: {scale_kod}")
    if profile_kod not in profile_carpanlari:
        raise FiyatHesaplamaHatasi(f"Bilinmeyen profil: {profile_kod}")
    if period not in GECERLI_PERIYOTLAR:
        raise FiyatHesaplamaHatasi(f"Bilinmeyen ödeme periyodu: {period}")

    baz = scale_baz_fiyatlari[scale_kod]
    carpan = profile_carpanlari[profile_kod]
    aylik_paket_fiyat = round(baz * carpan, 2)

    formul_notu = None
    if period == "aylik":
        paket_fiyat = aylik_paket_fiyat
    elif period == "kullandikca_ode":
        # Aylık tutarla aynı; kartta ayrıca "kaç kredi" gösterilir.
        paket_fiyat = aylik_paket_fiyat
        formul_notu = "kredi"
    elif period == "yillik":
        # %16 indirim, yıllıklaştırılmış toplam üzerinden — aylık gösterim
        # değeri üzerinden değil.
        paket_fiyat = round(aylik_paket_fiyat * 12 * 0.84, 2)
    else:  # tek_seferlik — mockup'ta tanımlı değildi, iş onayı bekleyen varsayılan
        paket_fiyat = round(aylik_paket_fiyat * 3, 2)
        formul_notu = "varsayilan_aylik_x3"

    eklenti_detay = []
    eklentiler_toplami = 0.0
    for kod in addon_kodlari:
        if kod not in addon_fiyatlari:
            raise FiyatHesaplamaHatasi(f"Bilinmeyen eklenti: {kod}")
        # Eklenti fiyatı da profil çarpanıyla, bir kez ölçeklenir — STK/bireysel/
        # eğitim indirimi burada ikinci kez uygulanmaz (hizmet notlarındaki
        # "STK için −%40" zaten stk çarpanının kendisi).
        fiyat = round(addon_fiyatlari[kod] * carpan, 2)
        eklentiler_toplami += fiyat
        eklenti_detay.append({"kod": kod, "fiyat": fiyat})
    eklentiler_toplami = round(eklentiler_toplami, 2)

    if period == "yillik":
        ai_pm_toplami = round(ai_pm_aylik * 12 * 0.84, 2)
    elif period == "tek_seferlik":
        ai_pm_toplami = round(ai_pm_aylik * 3, 2)
    else:
        ai_pm_toplami = round(ai_pm_aylik, 2)

    toplam = round(paket_fiyat + eklentiler_toplami + ai_pm_toplami, 2)
    kredi = math.ceil(toplam / KREDI_BIRIM_USD) if period == "kullandikca_ode" else None

    return FiyatSonucu(
        paket_fiyat=paket_fiyat,
        eklentiler_toplami=eklentiler_toplami,
        toplam=toplam,
        formul_notu=formul_notu,
        eklenti_detay=eklenti_detay,
        ai_pm_toplami=ai_pm_toplami,
        kredi=kredi,
    )
