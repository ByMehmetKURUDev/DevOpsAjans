from datetime import datetime

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Marketplace_items(Base):
    """
    Marketplace ürünü — hazır paketler, araçlar ve eklentiler.

    Hizmet paketlerinden (PricingPlans) ayrı duruyor: oradakiler saatlik
    ya da aylık iş, buradakiler raftan satılan hazır ürünler.

    Fiyat neden String?
    -------------------
    Katalogda "300", "Fiyat Alınız" ve "4.500 ₺'den başlar" yan yana
    durabiliyor. Sayı tutup görüntüyü koda gömmek yerine fiyatın kendisi
    metin, para birimi ve not ayrı alanlar. `price` boşsa kart otomatik
    olarak "Fiyat Alınız" gösteriyor — panelde ayrıca bir şey
    işaretlemeye gerek kalmıyor.

    `published` yanlışken ürün yalnızca yönetim panelinde görünüyor;
    siteye açılan uç (routers/marketplace_public.py) taslakları hiç
    döndürmüyor.
    """

    __tablename__ = "marketplace_items"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    title = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    # tool | plugin | website | ecommerce | saas
    category = Column(String, nullable=True)
    # Kartta görünen kısa metin.
    summary = Column(String, nullable=True)
    # Ayrıntı: uzun açıklama.
    description = Column(String, nullable=True)
    # Her satır bir özellik; kartta liste olarak çıkıyor.
    features = Column(String, nullable=True)
    price = Column(String, nullable=True)
    currency = Column(String, nullable=True)
    # "tek seferlik", "aylık", "başlangıç fiyatı" gibi.
    price_note = Column(String, nullable=True)
    # "3-5 iş günü" gibi teslim süresi.
    delivery_time = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    demo_url = Column(String, nullable=True)
    # "Yeni", "Popüler" gibi küçük rozet.
    badge = Column(String, nullable=True)
    published = Column(Boolean, nullable=True)
    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
