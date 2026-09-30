"""Marketplace ürünlerinin ilk çevirilerini boş satırlara yazar.

Ürünler panelden Türkçe giriliyor. Her satırda `ceviriler` adlı bir JSON
metni var: ``{"en": {"title": "...", "summary": "..."}, "de": {...}}``.
Sitede seçili dilde alan varsa o, yoksa Türkçe alan gösteriliyor.

Bu betik yalnız `ceviriler` BOŞ (NULL) olan satırları dolduruyor: panelden
elle düzeltilmiş ya da bilerek temizlenmiş bir çeviri her açılışta ezilmesin
diye. İlk çeviriler `scripts/marketplace_ceviriler.json` dosyasında; satır
`slug` ile eşleniyor. Dosyada olmayan (sonradan eklenen) ürün boş kalır,
panelden çevrilir.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import select

from models.marketplace_items import Marketplace_items

logger = logging.getLogger(__name__)

KATALOG_DOSYASI = Path(__file__).with_name("marketplace_ceviriler.json")

#: Çevrilebilen alanlar; kategori etiketleri sitede i18n'den geliyor.
ALANLAR = ("title", "summary", "description", "features", "price_note", "delivery_time", "badge")


def katalogu_yukle() -> Dict[str, Any]:
    return json.loads(KATALOG_DOSYASI.read_text(encoding="utf-8"))


def ceviri_uret(slug: Optional[str], katalog: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Tek ürün için {dil: {alan: değer}} üretir; eşleşme yoksa None."""
    if not slug:
        return None
    sonuc: Dict[str, Any] = {}
    for dil, urunler in katalog.items():
        kayit = (urunler or {}).get(slug)
        if not kayit:
            continue
        alanlar = {a: kayit[a] for a in ALANLAR if kayit.get(a)}
        if alanlar:
            sonuc[dil] = alanlar
    return sonuc or None


async def doldur(session) -> int:
    """`ceviriler` boş ürünleri doldurur; doldurulan satır sayısını döndürür."""
    katalog = katalogu_yukle()
    satirlar = (
        await session.execute(select(Marketplace_items).where(Marketplace_items.ceviriler.is_(None)))
    ).scalars().all()
    n = 0
    for satir in satirlar:
        ceviri = ceviri_uret(satir.slug, katalog)
        if ceviri:
            satir.ceviriler = json.dumps(ceviri, ensure_ascii=False)
            n += 1
    await session.commit()
    return n
