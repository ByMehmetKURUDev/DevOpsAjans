from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class NotificationPrefs(Base):
    """Kişisel bildirim tercihi — kişi başına tek satır.

    `tercih_json`: `{"<olay>": {"<kanal>": true|false}}`. Yalnız kişinin
    değiştirdiği hücreler yazılıyor; yazılmayan hücre yönetici matrisindeki
    değeri izliyor. Yönetici matrisi bir kanalı kapattıysa kişinin burada
    `true` yazması bir şey değiştirmiyor (`services/bildirim_tercih.py`).

    `sessiz_saatler`: `{"bas": "22:00", "bit": "08:00"}` ya da boş. Bu
    aralıkta anlık kanallar (push, SMS, WhatsApp) gönderilmiyor; panel içi
    ve e-posta etkilenmiyor.
    """

    __tablename__ = "notification_prefs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Küçük harf; jetondaki e-posta.
    eposta = Column(String, nullable=False, unique=True, index=True)
    tercih_json = Column(Text, nullable=True)
    sessiz_saatler = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)


class PushSubscriptions(Base):
    """Bir tarayıcının Web Push aboneliği.

    Aynı kişinin birden çok tarayıcısı/cihazı olabilir; her biri ayrı satır.
    `endpoint` tarayıcı üreticisinin (Google, Mozilla, Apple) push
    sunucusundaki adres ve benzersiz. O sunucu 404/410 dönerse abonelik
    ölmüş demektir, satır siliniyor.
    """

    __tablename__ = "push_subscriptions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    eposta = Column(String, nullable=False, index=True)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    #: "Chrome · Android" gibi kısa özet; tam UA dizgesi saklanmıyor.
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)
    son_basari_at = Column(DateTime(timezone=True), nullable=True)
    hata_sayisi = Column(Integer, nullable=False, default=0)
