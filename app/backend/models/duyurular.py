"""Faz 2B — duyurular (okundu takibiyle) ve öneri kutusu (oylamalı)."""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


DUYURU_ONEMLERI = ("bilgi", "onemli", "kritik")
#: tum = bütün müşteriler, secili = `hedef_epostalar`, ekip = staff + yöneticiler
DUYURU_HEDEFLERI = ("tum", "secili", "ekip")
ONERI_DURUMLARI = ("yeni", "inceleniyor", "planlandi", "yapildi", "reddedildi")


class Duyurular(Base):
    __tablename__ = "duyurular"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    baslik = Column(String, nullable=False)
    metin = Column(Text, nullable=True)
    onem = Column(String, nullable=False, default="bilgi")
    hedef = Column(String, nullable=False, default="tum")
    #: JSON listesi (küçük harf e-postalar) — yalnız hedef == "secili".
    hedef_epostalar = Column(Text, nullable=True)
    bitis_at = Column(DateTime(timezone=True), nullable=True)
    yayinda = Column(Boolean, nullable=False, default=True)
    olusturan_eposta = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class DuyuruOkumalari(Base):
    """Kişi × duyuru: okundu mu, şeritten kapattı mı."""

    __tablename__ = "duyuru_okumalari"
    __table_args__ = (
        UniqueConstraint("duyuru_id", "eposta", name="uq_duyuru_okumalari_kisi"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    duyuru_id = Column(Integer, nullable=False, index=True)
    eposta = Column(String, nullable=False, index=True)
    okundu_at = Column(DateTime(timezone=True), nullable=True)
    kapatildi = Column(Boolean, nullable=False, default=False)


class Oneriler(Base):
    """Öneri kutusu. Sahibin e-postası yalnız yöneticiye görünüyor."""

    __tablename__ = "oneriler"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    baslik = Column(String, nullable=False)
    aciklama = Column(Text, nullable=True)
    sahip_eposta = Column(String, nullable=False, index=True)
    durum = Column(String, nullable=False, default="yeni", index=True)
    yonetici_notu = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class OneriOylari(Base):
    """Kişi başına tek oy (benzersiz kısıt)."""

    __tablename__ = "oneri_oylari"
    __table_args__ = (
        UniqueConstraint("oneri_id", "eposta", name="uq_oneri_oylari_kisi"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    oneri_id = Column(Integer, nullable=False, index=True)
    eposta = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
