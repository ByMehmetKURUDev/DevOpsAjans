"""Faz 3U — yapay zekâ çağrılarının günlük sayacı (bütçe kesici ve kullanım özeti).

Bir satır = bir gün (UTC, ``YYYY-MM-DD``) × bir kapsam:

* ``acik`` — herkese açık amaca özel uçlar (keşif asistanı, site sohbeti).
  Günlük toplam bütçe kesici (site ayarı ``ai_acik_gunluk_butce``) buna bakar.
* ``asistan`` — müşteri panelindeki Uzman Asistanlar.
* ``yonetici`` — yönetici araçları (içerik taslağı, asistan denemesi).

Sayaç süreç belleğinde değil veritabanında: ücretsiz sunucu uyuyup kalkınca
bellek sıfırlanır, günlük bütçe sıfırlanmamalı.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class AiGunlukKullanim(Base):
    __tablename__ = "ai_gunluk_kullanim"
    __table_args__ = (
        UniqueConstraint("gun", "kapsam", name="uq_ai_gunluk_kullanim_gun_kapsam"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    gun = Column(String, index=True, nullable=False)
    kapsam = Column(String, nullable=False)
    istek = Column(Integer, nullable=False, default=0)
    token_giris = Column(Integer, nullable=False, default=0)
    token_cikis = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)
