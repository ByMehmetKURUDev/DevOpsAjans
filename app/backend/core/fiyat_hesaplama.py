"""Fiyatlandırma v5 — tek doğru kaynak (single source of truth) hesaplama.

Hem `GET /api/v1/fiyat-hesapla` hem `POST /api/v1/fiyat-teklif` bu
fonksiyonu çağırır. Frontend hiçbir zaman fiyatı kendisi hesaplamaz —
paket kartı da, teklif de aynı sayıyı üretir (spec: "fiyat tutarlılığı
için kritik").
"""

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


GECERLI_PERIYOTLAR = ("tek_seferlik", "aylik", "yillik")


def hesapla(
    *,
    scale_kod: str,
    profile_kod: str,
    period: str,
    addon_kodlari: List[str],
    scale_baz_fiyatlari: Dict[str, float],
    profile_carpanlari: Dict[str, float],
    addon_fiyatlari: Dict[str, float],
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

    return FiyatSonucu(
        paket_fiyat=paket_fiyat,
        eklentiler_toplami=eklentiler_toplami,
        toplam=round(paket_fiyat + eklentiler_toplami, 2),
        formul_notu=formul_notu,
        eklenti_detay=eklenti_detay,
    )
