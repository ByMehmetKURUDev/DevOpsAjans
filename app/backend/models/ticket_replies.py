from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text


class Ticket_replies(Base):
    """Bir talebin altındaki yazışma.

    `support_tickets.reply` tek bir cevap alanıydı: ikinci cevapta
    birincisi siliniyordu. Burada her mesaj kendi satırı, sırayla
    okunuyor ve kimin yazdığı kayıtta duruyor.

    `yazan` yalnızca "musteri" ya da "ajans" olabiliyor. Kim olduğu
    oturumdan belirleniyor, gövdeden değil: yoksa müşteri kendi
    mesajını ajans imzasıyla gönderebilirdi.
    """

    __tablename__ = "ticket_replies"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    ticket_id = Column(Integer, index=True, nullable=False)
    yazan = Column(String, nullable=False)          # musteri | ajans
    yazan_ad = Column(String, nullable=True)
    yazan_email = Column(String, index=True, nullable=True)
    mesaj = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
