from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text


class Projects(Base):
    __tablename__ = "projects"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    category = Column(String, nullable=False)
    image_url = Column(String, nullable=True)
    project_url = Column(String, nullable=True)
    client_name = Column(String, nullable=True)
    client_email = Column(String, nullable=True)
    status = Column(String, nullable=True)
    stage = Column(String, nullable=True)
    progress = Column(Integer, nullable=True)
    tech_stack = Column(String, nullable=True)
    featured = Column(Boolean, nullable=True)
    # Halka acik "Vaka Calismalari" sayfasinda gorunsun mu?
    # Musteri paneli bundan bagimsiz: musteri kendi projesini her halukarda gorur.
    # Yeni projeler taslak baslar; is bitince yonetici yayina alir.
    published = Column(Boolean, nullable=True, default=False)
    # Talepten tasinan uzman promptlari (JSON metni). Proje ise
    # basladiginda brief'in yeniden uretilmesi gerekmiyor; hangi
    # varsayimlarla baslandigi da kayitli kaliyor.
    brief = Column(Text, nullable=True)
    # Faz 2B — paketten revizyon hakkı bulunamazsa elle girilen aylık
    # revizyon saati (bkz. services/gorevler.revizyon_sayaci).
    aylik_revizyon_saati = Column(Float, nullable=True)
    # Faz 3Z — zaman takibi: projenin saatlik ücreti (boşsa site ayarı
    # `zaman_saatlik_ucret`) ve müşteri panelinde harcanan süre görünürlüğü.
    saatlik_ucret = Column(Float, nullable=True)
    ucret_para_birimi = Column(String, nullable=True)
    sure_musteriye_gorunur = Column(Boolean, nullable=True, default=False)
    faturalanabilir_musteriye_gorunur = Column(Boolean, nullable=True, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
