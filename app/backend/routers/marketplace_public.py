"""
Marketplace -- ziyaretçiye açık uç.

Neden ayrı bir dosya?
---------------------
Yönetim ucu (`/api/v1/entities/marketplace_items`) `entity_guard`
altında; okumak için bile oturum istiyor. Site ise ziyaretçiye ürünleri
giriş yapmadan göstermek zorunda.

İki seçenek vardı: tabloyu bekçinin "herkese açık okuma" listesine
eklemek, ya da yalnızca yayındaki ürünleri döndüren ayrı bir uç yazmak.
İkincisini seçtim. Birincisinde taslak ürünler `published=true`
filtresine güvenerek korunmuş olurdu; filtreyi yazmayan bir sorgu
(ya da meraklı biri) taslakları görürdü. Burada taslak hiç sorgudan
çıkmıyor: filtre uçta, istemcide değil.

Sıralama: önce `sort_order` (panelden verilen el sırası), sonra en yeni.
`sort_order` boş olanlar sona düşüyor -- sırası verilmemiş bir ürün,
sırası verilmiş olanların arasına karışmamalı.
"""

import logging
from datetime import datetime
from typing import List, Optional

from core.database import get_db
from fastapi import APIRouter, Depends, Query
from models.marketplace_items import Marketplace_items
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/marketplace", tags=["marketplace"])

#: Sitede gösterilen kategoriler. Panelde bunun dışında bir değer
#: yazılırsa ürün "diğer" sayılıp yine listeleniyor -- yazım hatası
#: yüzünden ürünün kaybolması, yanlış sekmede görünmesinden kötü.
KATEGORILER = ["tool", "plugin", "website", "ecommerce", "saas"]


class UrunYaniti(BaseModel):
    id: int
    title: str
    slug: str
    category: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    features: Optional[str] = None
    price: Optional[str] = None
    currency: Optional[str] = None
    price_note: Optional[str] = None
    delivery_time: Optional[str] = None
    image_url: Optional[str] = None
    demo_url: Optional[str] = None
    badge: Optional[str] = None
    sort_order: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ListeYaniti(BaseModel):
    items: List[UrunYaniti]
    total: int
    categories: List[str]


@router.get("", response_model=ListeYaniti)
async def yayindaki_urunler(
    category: Optional[str] = Query(None, description="tool|plugin|website|ecommerce|saas"),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    sorgu = select(Marketplace_items).where(Marketplace_items.published.is_(True))
    if category:
        sorgu = sorgu.where(Marketplace_items.category == category)

    try:
        sonuc = await db.execute(sorgu.limit(limit))
        satirlar = list(sonuc.scalars().all())
    except Exception as hata:
        # Tablo henüz oluşmadıysa (ilk yayın) sayfa boş açılsın, düşmesin.
        logger.warning("Marketplace okunamadı: %s", hata)
        return ListeYaniti(items=[], total=0, categories=KATEGORILER)

    # Sıralama Python tarafında: "sort_order boşsa sona" kuralını
    # SQL'de yazmak sürücüye göre değişiyor (NULLS LAST her yerde yok).
    satirlar.sort(
        key=lambda u: (
            u.sort_order is None,
            u.sort_order if u.sort_order is not None else 0,
            -(u.id or 0),
        )
    )

    return ListeYaniti(
        items=[UrunYaniti.model_validate(u) for u in satirlar],
        total=len(satirlar),
        categories=KATEGORILER,
    )
