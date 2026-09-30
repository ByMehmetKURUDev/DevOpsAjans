from datetime import datetime

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String


class Content_posts(Base):
    """
    İçerik takvimi — planlanan gönderiler.

    Bu tablo YAYIN YAPMIYOR, plan tutuyor. Instagram, Facebook ve
    LinkedIn'e program üzerinden gönderi atmak için platformların onaylı
    uygulama hesapları gerekiyor; X'in API'si ücretli. Üstelik arka uç
    ücretsiz planda 15 dakikada uykuya geçtiği için "salı 09:00'da at"
    denen bir iş tam saatinde çalışmaz. Söz verip tutmamaktansa dürüst
    olanı yapıyoruz: metin burada hazırlanıyor, zamanı gelince tek tuşla
    kopyalanıp ilgili uygulamada paylaşılıyor.

    Platform onayları alınırsa buraya gerçek gönderim eklenebilir; tablo
    o gün için de uygun (status alanı zaten "published" durumunu
    tutuyor).
    """

    __tablename__ = "content_posts"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    # Panelde görünen iç ad; gönderi metni değil.
    title = Column(String, nullable=False)
    # instagram | facebook | linkedin | x | blog | email
    channel = Column(String, nullable=True)
    # Paylaşılacak metnin kendisi.
    body = Column(String, nullable=True)
    hashtags = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    link_url = Column(String, nullable=True)
    # Ne zaman paylaşılacak. Saat dilimi yok: yönetici kendi saatini
    # giriyor ve kendi paylaşıyor; araya sunucu girmediği için
    # dönüştürmek fayda değil karışıklık üretirdi.
    scheduled_at = Column(DateTime, nullable=True)
    # draft | approved | published
    status = Column(String, nullable=True)
    # Aynı kampanyaya ait gönderileri birlikte görmek için.
    campaign = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
