from datetime import datetime

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String


class Notifications(Base):
    """
    Bildirimler.

    Tek tablo iki işi görüyor:

    1. Panel içi bildirim — yönetici ve müşteri panellerindeki çan.
       `read_at` boşsa okunmamış.
    2. Dış kanalların (e-posta, SMS, WhatsApp) gönderim kaydı.
       `channel` hangi kanal, `delivery_status` ne olduğu.

    İkisini ayırmadım çünkü aynı olay her iki yere de gidiyor ve tek
    tabloda "bu olay kime, hangi kanaldan, ne zaman ulaştı" tek sorguyla
    cevaplanıyor. Kanal başına bir satır yazılıyor.
    """

    __tablename__ = "notifications"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    # Kime: e-posta adresi kimliğin kendisi (auth da e-posta üzerinden).
    recipient_email = Column(String, index=True, nullable=False)
    # admin | client
    recipient_role = Column(String, nullable=True)
    # inquiry | ticket | project_stage | project_delivery | invoice
    event_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    body = Column(String, nullable=True)
    # Panelde tıklanınca gidilecek yer.
    link = Column(String, nullable=True)
    # inapp | email | sms | whatsapp
    channel = Column(String, nullable=False, default="inapp")
    # pending | sent | failed | skipped
    delivery_status = Column(String, nullable=True, default="pending")
    # Başarısızlıkta sebebi; panelde neden gitmediğini görebilmek için.
    delivery_detail = Column(String, nullable=True)
    # İlgili kaydın kimliği (proje, talep, fatura).
    ref_type = Column(String, nullable=True)
    ref_id = Column(Integer, nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
