"""Faz 2D — çöp kutusu: silinen kaydın tam kopyası (geri alma için).

Satır, SQLAlchemy flush kancasıyla (`services/cop_kutusu.py`) yazılıyor;
yalnız izin listesindeki tablolar. `veri` satırın bütün sütunları (JSON;
tarih/ondalık metin olarak, ikili içerik HARİÇ). Aynı flush'ta silinen
kayıtlar aynı `grup`u paylaşıyor: görev + kontrol listesi birlikte geri
geliyor.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class CopKutusu(Base):
    __tablename__ = "cop_kutusu"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    tablo = Column(String(64), index=True, nullable=False)
    #: Silinen kaydın birincil anahtarı (metin; bileşik anahtarda virgülle).
    kayit_id = Column(String(64), index=True, nullable=True)
    veri = Column(Text, nullable=False)
    #: Aynı flush'ta silinenlerin ortak uuid'i.
    grup = Column(String(36), index=True, nullable=False)
    silen_email = Column(String, index=True, nullable=True)
    silen_rol = Column(String, nullable=True)
    #: Kaydın sahibi müşteri (küçük harf) — müşteri yalnız bunu görür.
    sahip_email = Column(String, index=True, nullable=True)
    #: Listede gösterilecek kısa ad (başlık, fatura no, dosya adı…).
    etiket = Column(String(200), nullable=True)
    silinme = Column(DateTime(timezone=True), default=_simdi, index=True)
    geri_alindi = Column(Boolean, nullable=False, default=False, index=True)
    geri_alan = Column(String, nullable=True)
    geri_alinma = Column(DateTime(timezone=True), nullable=True)
