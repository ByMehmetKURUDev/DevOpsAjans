"""Faz 3U — Uzman Asistanlar: müşteri panelinde konuya özel yapay zekâ asistanları.

Tablolar
--------
* `uzman_asistanlar` — asistan tanımı. Metinler marketplace / kaynaklar
  desende: Türkçe ana sütunlarda (`ad`, `aciklama`, `ornek_sorular`), diğer
  altı dil `ceviriler` JSON'unda (``{"en": {"ad", "aciklama", "ornek_sorular": [..]}}``).
  `sistem_istemi` YALNIZ sunucuda kalır: müşteri yanıtlarında asla dönmez.
* `uzman_asistan_tohum_izi` — tohum dosyasından bir kez eklenmiş anahtarlar
  (kaynaklardaki `kaynak_tohum_izi` düzeni): panelde düzenlenen ya da silinen
  asistan bir sonraki açılışta ezilmez / geri gelmez.
* `asistan_sohbetleri` — müşteri hesabında (``hesap_email``) bir kişinin
  (``kisi_email``) bir asistanla sohbeti. Silme yumuşak (`silindi`).
* `asistan_mesajlari` — sohbetin mesajları: rol `user` | `assistant`, düz
  metin (en çok 8000 karakter; arayüz HTML çizmez), varsa jeton sayıları.

`ornek_sorular` JSON listesi (metin sütunu): SQLite ile Postgres'te aynı
davranışı versin diye JSON türü kullanılmadı (diğer tablolarla tutarlı).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class UzmanAsistanlar(Base):
    __tablename__ = "uzman_asistanlar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Kısa ad (küçük harf, rakam, tire): `seo-specialist`.
    anahtar = Column(String, unique=True, index=True, nullable=False)
    kategori = Column(String, index=True, nullable=False)
    ad = Column(String, nullable=False)
    aciklama = Column(Text, nullable=True)
    #: JSON listesi (Türkçe örnek sorular).
    ornek_sorular = Column(Text, nullable=True)
    #: JSON: {"en": {"ad", "aciklama", "ornek_sorular": [...]}, ...}
    ceviriler = Column(Text, nullable=True)
    #: Modele giden sistem istemi — müşteriye hiçbir uçta dönmez.
    sistem_istemi = Column(Text, nullable=False)
    aktif = Column(Boolean, nullable=False, default=True, index=True)
    sira = Column(Integer, nullable=False, default=100)
    #: Kaynak bildirimi: "agency-agents (marketing/marketing-seo-specialist.md), MIT".
    atif = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class UzmanAsistanTohumIzi(Base):
    """Tohum dosyasından bir kez eklenmiş asistan anahtarları."""

    __tablename__ = "uzman_asistan_tohum_izi"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    anahtar = Column(String, unique=True, index=True, nullable=False)
    eklendi_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class AsistanSohbetleri(Base):
    __tablename__ = "asistan_sohbetleri"
    __table_args__ = (
        Index("ix_asistan_sohbetleri_hesap_kisi", "hesap_email", "kisi_email"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Etkin müşteri hesabı (kayıt sahibi; küçük harf).
    hesap_email = Column(String, index=True, nullable=False)
    #: Sohbeti açan kişi (jetondaki e-posta). Sohbet kişiye özel: ekipteki
    #: başka kişi göremez; sınır ve kredi hesap düzeyinde.
    kisi_email = Column(String, index=True, nullable=False)
    asistan_anahtar = Column(String, index=True, nullable=False)
    baslik = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, nullable=True, index=True)
    silindi = Column(Boolean, nullable=False, default=False, index=True)


class AsistanMesajlari(Base):
    __tablename__ = "asistan_mesajlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    sohbet_id = Column(Integer, index=True, nullable=False)
    #: user | assistant
    rol = Column(String, nullable=False)
    icerik = Column(Text, nullable=False)
    token_giris = Column(Integer, nullable=True)
    token_cikis = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)
