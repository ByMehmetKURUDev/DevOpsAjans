"""Faz 2G — müşteri ↔ ajans mesajlaşma: konuşma, mesaj, okunma.

Neden üç tablo?
---------------
* `konusmalar` bir hesabın (müşteri hesabı = sahibinin e-postası) yazışma
  başlığı. Her hesapta bir "Genel" konuşma kendiliğinden açılıyor
  (`tekil_anahtar = "genel:<hesap>"` — benzersiz; eş zamanlı iki istek ikinci
  bir Genel açamıyor). Proje bazlı ek konuşmalar açılabiliyor.
  Liste ve yoklama her seferinde mesaj tablosunu taramasın diye son mesajın
  özeti ve taraf başına son mesaj kimliği burada tutuluyor; bildirim
  toplamanın durumu da (`bildirilen_*`, `bildirim_*_at`).
* `konusma_mesajlari` düz metin (en çok 5000 karakter; HTML çizilmez) +
  ek dosya kimlikleri (JSON; dosyanın kendisi `files` tablosunda). Silme
  yumuşak: satır kalıyor, içerik boşalıyor ("bu mesaj silindi").
* `konusma_okunma` kişi başına "nereye kadar okudu" (yalnız ileri gider).
  `taraf` (admin/client): bildirim kararı taraf düzeyinde — karşı taraftan
  biri okuduysa bildirim gitmiyor.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class Konusmalar(Base):
    __tablename__ = "konusmalar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Sahip müşteri hesabı (küçük harf). Müşteri yalnız bununla eşleşenleri görür.
    hesap_email = Column(String, index=True, nullable=False)
    konu = Column(String, nullable=False)
    proje_id = Column(Integer, index=True, nullable=True)
    #: acik | arsiv
    durum = Column(String, nullable=False, default="acik", index=True)
    #: "genel:<hesap>" — hesabın varsayılan konuşması; diğerlerinde boş.
    tekil_anahtar = Column(String, unique=True, nullable=True)
    olusturan = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)

    # --- Son mesaj (liste ve yoklama için önbellek) ---------------------------
    son_mesaj_at = Column(DateTime(timezone=True), nullable=True, index=True)
    son_mesaj_id = Column(Integer, nullable=True)
    son_mesaj_ozet = Column(String, nullable=True)
    #: admin | client
    son_mesaj_rol = Column(String, nullable=True)
    son_client_mesaj_id = Column(Integer, nullable=True)
    son_admin_mesaj_id = Column(Integer, nullable=True)
    #: Düzenleme/silme sayacı: yoklamada "eski mesajlardan biri değişti" sinyali.
    degisiklik = Column(Integer, nullable=False, default=0)

    # --- Bildirim toplama ----------------------------------------------------
    #: Karşı tarafa bildirimi gönderilmiş (ya da okunduğu için kapsanmış) son mesaj.
    bildirilen_admin_mesaj_id = Column(Integer, nullable=True)
    bildirilen_client_mesaj_id = Column(Integer, nullable=True)
    bildirim_admin_at = Column(DateTime(timezone=True), nullable=True)
    bildirim_client_at = Column(DateTime(timezone=True), nullable=True)


class KonusmaMesajlari(Base):
    __tablename__ = "konusma_mesajlari"
    __table_args__ = (
        Index("ix_konusma_mesajlari_konusma_id_id", "konusma_id", "id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    konusma_id = Column(Integer, index=True, nullable=False)
    #: Yazan KİŞİ (ekip üyesi de olabilir); taraf `yazan_rol`.
    yazan_email = Column(String, nullable=False)
    #: admin | client — gövdeden değil oturumdan.
    yazan_rol = Column(String, nullable=False)
    #: Yazıldığı andaki görünen ad (ajansta `staff.ad`).
    yazan_ad = Column(String, nullable=True)
    metin = Column(Text, nullable=False, default="")
    #: JSON: [{"id": dosya_id, "ad", "boyut", "tur"}]
    ekler = Column(Text, nullable=True)
    duzenlendi_at = Column(DateTime(timezone=True), nullable=True)
    silindi = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, index=True)


class KonusmaOkunma(Base):
    __tablename__ = "konusma_okunma"
    __table_args__ = (
        UniqueConstraint("konusma_id", "kisi_email", name="uq_konusma_okunma"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    konusma_id = Column(Integer, index=True, nullable=False)
    kisi_email = Column(String, index=True, nullable=False)
    #: admin | client
    taraf = Column(String, nullable=False)
    son_okunan_mesaj_id = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), default=_simdi)
