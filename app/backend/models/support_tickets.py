from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Support_tickets(Base):
    __tablename__ = "support_tickets"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    client_name = Column(String, nullable=True)
    client_email = Column(String, nullable=True)
    subject = Column(String, nullable=False)
    message = Column(String, nullable=False)
    reply = Column(String, nullable=True)
    status = Column(String, nullable=True)
    priority = Column(String, nullable=True)

    # Faz 1 — talep akışı
    # Hangi hizmet kalemi için açıldı (seo, website, youtube_pr ...).
    # Müşteri panelindeki hizmet düğmeleri bunu dolduruyor; boş kalırsa
    # "genel" sayılıyor, eski kayıtlar da öyle.
    hizmet = Column(String, index=True, nullable=True)
    # Hangi projeye bağlı. Müşterinin birden çok işi olabiliyor.
    project_id = Column(Integer, index=True, nullable=True)
    # panel | site | eposta — talebin nereden geldiği.
    kaynak = Column(String, nullable=True)
    # Faz 2 — hangi ekip uyesine atandi (staff.email). Bos ise atanmamis.
    atanan = Column(String, index=True, nullable=True)
    # Son mesajın zamanı. Listeyi buna göre sıralıyoruz: cevap
    # bekleyen talep, açılış tarihi eski olsa da üste çıksın.
    son_mesaj_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)