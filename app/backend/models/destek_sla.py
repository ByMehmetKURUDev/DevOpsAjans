"""Faz 2C — Destek: SLA saatleri, hazır cevaplar ve bilgi bankası."""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class TalepSla(Base):
    """Bir destek talebinin SLA saatleri.

    `support_tickets` üretilmiş bir entity tablosu (üç elle yazılmış
    Pydantic sınıfı); SLA alanlarını oraya eklemek entity uçlarının
    yanıtını değiştirirdi. Ayrı tablo: talep başına tek satır.

    Hedefler talep açıldığı anda MESAİ saatine göre hesaplanıp yazılıyor
    (`services/sla.py`); öncelik değişirse yeniden hesaplanıyor.
    Uyarı/eskalasyon zamanları "bir kez" güvencesi: koşullu UPDATE ile
    yalnız boşken doluyor.
    """

    __tablename__ = "talep_sla"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    ticket_id = Column(Integer, unique=True, index=True, nullable=False)
    #: acil | yuksek | normal | dusuk
    oncelik = Column(String, nullable=False, default="normal")
    baslangic = Column(DateTime(timezone=True), nullable=False)
    ilk_yanit_hedef = Column(DateTime(timezone=True), nullable=True)
    cozum_hedef = Column(DateTime(timezone=True), nullable=True)
    ilk_yanit_at = Column(DateTime(timezone=True), nullable=True)
    cozum_at = Column(DateTime(timezone=True), nullable=True)
    uyari_ilk_at = Column(DateTime(timezone=True), nullable=True)
    uyari_cozum_at = Column(DateTime(timezone=True), nullable=True)
    eskalasyon_ilk_at = Column(DateTime(timezone=True), nullable=True)
    eskalasyon_cozum_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)


class HazirCevaplar(Base):
    __tablename__ = "hazir_cevaplar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    baslik = Column(String, nullable=False)
    #: {musteri_adi}, {talep_no}, {konu} yer tutucuları yanıt kutusunda dolduruluyor.
    metin = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)


class BilgiMakaleleri(Base):
    """Bilgi bankası makalesi.

    `icerik` markdown (Türkçe, ana metin). `ceviriler` JSON metni:
    {"en": {"baslik": .., "icerik": ..}, ...}. Görüntülenirken markdown
    güvenli HTML'e çevriliyor (`services/guvenli_html.py`); HTML saklanmıyor,
    temizleme kuralı değişirse eski makaleler de yeni kuralla çıkıyor.
    """

    __tablename__ = "bilgi_makaleleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kategori = Column(String, index=True, nullable=True)
    baslik = Column(String, nullable=False)
    icerik = Column(Text, nullable=False, default="")
    ceviriler = Column(Text, nullable=True)
    #: taslak | yayinda
    durum = Column(String, index=True, nullable=False, default="taslak")
    goruntulenme = Column(Integer, nullable=False, default=0)
    yazan = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)
