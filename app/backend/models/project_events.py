from datetime import datetime

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String


class Project_events(Base):
    """
    Bir projenin zaman çizelgesi.

    Her satır projede olan bir şeyi anlatıyor: aşama değişti, not düşüldü,
    dosya eklendi, teslim edildi. Müşteri panelinde bu satırlar projenin
    geçmişi olarak görünüyor; yönetici panelinde de aynı kayıt.

    Projenin kendi tablosunda yalnızca GÜNCEL durum var (`status`, `stage`,
    `progress`). Geçmiş burada tutuluyor: "proje ne zaman hangi aşamadaydı"
    sorusunun cevabı projenin satırını güncelleyince kaybolmasın diye.
    """

    __tablename__ = "project_events"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    project_id = Column(Integer, index=True, nullable=False)
    # stage_change | note | file | status_change | delivery
    event_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    body = Column(String, nullable=True)
    # Aşama/durum değişimlerinde önceki ve yeni değer.
    from_value = Column(String, nullable=True)
    to_value = Column(String, nullable=True)
    # Kaydı kimin oluşturduğu; müşteriye gösterilen isim.
    actor_name = Column(String, nullable=True)
    actor_email = Column(String, nullable=True)
    # Müşteri panelinde görünsün mü? İç notlar için False.
    visible_to_client = Column(String, nullable=True, default="1")
    attachment_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
