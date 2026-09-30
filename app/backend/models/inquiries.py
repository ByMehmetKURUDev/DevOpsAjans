from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text


class Inquiries(Base):
    __tablename__ = "inquiries"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    message = Column(String, nullable=False)
    status = Column(String, nullable=True)
    # Talebin nereden geldigi: iletisim formu mu, kesif sihirbazi mi,
    # marketplace urun karti mi. Hangi sayfanin is getirdigini bilmeden
    # nereye yatirim yapilacagina karar vermek tahmine kaliyor.
    # Deger orn. "contact", "kesif", "marketplace:kartvizit-web-sitesi".
    source = Column(String, nullable=True)
    # Uretilen uzman promptlari (JSON metni: secimler + roller + zincir).
    # Panelde uretilip burada saklaniyor; yoksa modal kapaninca kayboluyor
    # ve ayni talep icin ayni brief tekrar tekrar uretiliyordu. Text: icerik
    # birkac bin karakter, VARCHAR sinirina takilmasin.
    brief = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)