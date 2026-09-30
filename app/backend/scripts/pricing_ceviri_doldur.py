"""Fiyat kataloğunun ilk çevirilerini boş satırlara yazar.

Katalog (ölçekler, profiller, modüller, 80 hizmet, AI vs PM) veritabanında
Türkçe duruyor. Her satırda `ceviriler` adlı bir JSON metni var:
``{"en": {"ad": "...", "aciklama": "..."}, "de": {...}}``. Sitede seçili dilde
alan varsa o, yoksa Türkçe alan gösteriliyor.

Bu betik yalnız `ceviriler` BOŞ olan satırları dolduruyor: panelden elle
düzeltilmiş bir çeviri her açılışta ezilmesin diye. İlk çeviriler
`scripts/pricing_ceviriler.json` dosyasında; satır, doğal anahtarıyla
eşleniyor (ölçek/profil/AI PM `kod`, modül ve hizmet Türkçe `ad`).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import select

from models.pricing import Ai_pm_tiers, Pricing_addons, Pricing_profiles, Pricing_scales, Pricing_services

logger = logging.getLogger(__name__)

KATALOG_DOSYASI = Path(__file__).with_name("pricing_ceviriler.json")

ALANLAR = {
    "pricing_scales": ("scales", "kod", ["ad", "alt_baslik", "calisan_araligi", "aciklama", "ozellikler",
                                         "eklenti_limiti", "revizyon_saat", "karsilastirma"]),
    "pricing_profiles": ("profiles", "kod", ["ad", "etiket"]),
    "ai_pm_tiers": ("tiers", "kod", ["ad", "rozet", "ozellikler"]),
}


def katalogu_yukle() -> Dict[str, Any]:
    return json.loads(KATALOG_DOSYASI.read_text(encoding="utf-8"))


def ceviri_uret(tablo: str, satir: Dict[str, Any], katalog: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Tek satır için {dil: {alan: değer}} üretir; eşleşme yoksa None."""
    sonuc: Dict[str, Any] = {}
    for dil, veri in katalog.items():
        if tablo in ALANLAR:
            bolum, anahtar, alanlar = ALANLAR[tablo]
            kayit = veri.get(bolum, {}).get(satir.get(anahtar))
            if not kayit:
                continue
            sonuc[dil] = {a: kayit[a] for a in alanlar if kayit.get(a) is not None}
        elif tablo == "pricing_addons":
            ad = veri.get("addons", {}).get(satir.get("ad"))
            if ad:
                sonuc[dil] = {"ad": ad}
        elif tablo == "pricing_services":
            hizmet = veri.get("services", {}).get(satir.get("ad"))
            kategori = veri.get("kategoriler", {}).get(satir.get("kategori"))
            alanlar: Dict[str, Any] = {}
            if hizmet:
                alanlar["ad"] = hizmet.get("ad")
                if hizmet.get("not_metni"):
                    alanlar["not_metni"] = hizmet["not_metni"]
            if kategori:
                alanlar["kategori"] = kategori
            if alanlar:
                sonuc[dil] = alanlar
    return sonuc or None


MODELLER = [
    ("pricing_scales", Pricing_scales),
    ("pricing_profiles", Pricing_profiles),
    ("pricing_services", Pricing_services),
    ("pricing_addons", Pricing_addons),
    ("ai_pm_tiers", Ai_pm_tiers),
]


async def doldur(session) -> Dict[str, int]:
    """`ceviriler` boş satırları doldurur; tablo başına doldurulan sayıyı döndürür."""
    katalog = katalogu_yukle()
    sayac: Dict[str, int] = {}
    for tablo, model in MODELLER:
        satirlar = (await session.execute(select(model).where(model.ceviriler.is_(None)))).scalars().all()
        n = 0
        for satir in satirlar:
            veri = {c.name: getattr(satir, c.name) for c in satir.__table__.columns}
            ceviri = ceviri_uret(tablo, veri, katalog)
            if ceviri:
                satir.ceviriler = json.dumps(ceviri, ensure_ascii=False)
                n += 1
        sayac[tablo] = n
    await session.commit()
    return sayac
