"""Faz 3B — dış hizmet bağlantıları (şimdilik Google: Analytics 4, Search Console, YouTube).

`baglantilar`: sağlayıcı başına bir bağlantı. `hesap_email` NULL = ajansın
kendi hesapları (bu fazda yalnız bu var; şema ileride müşteri bağlantılarına
hazır: aynı sağlayıcı müşteri başına bir satır). NULL benzersizlik kısıtında
"farklı" sayıldığı için tekillik `sahip_anahtari` sütunuyla sağlanıyor
(`__ajans__` ya da hesap e-postası).

Yenileme jetonu (refresh token) YALNIZ şifreli duruyor (Fernet,
`BAGLANTI_SIFRE_ANAHTARI`). Erişim jetonu hiç yazılmıyor: kısa ömürlü,
bellekte önbellekleniyor (`services/baglantilar.py`).

`baglanti_durumlari`: OAuth "state" kayıtları — tek kullanımlık, 10 dakika.
Değerin kendisi değil SHA-256 özeti tutuluyor; PKCE doğrulayıcısı şifreli.
Denetim kaydına girmiyor (her bağlan tıklamasında bir satır; teknik iz).

`analitik_listeleri`: Search Console'un en çok tıklanan 10 sorgusu ve 10
sayfası gibi sayı olmayan özetler (JSON). `analytics_snapshots` tek sayı
taşıyor; listeler buraya.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class Baglanti(Base):
    __tablename__ = "baglantilar"
    __table_args__ = (
        UniqueConstraint("saglayici", "sahip_anahtari", name="uq_baglanti_saglayici_sahip"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: google (ileride: google_business, meta …)
    saglayici = Column(String, nullable=False, index=True)
    #: NULL = ajansın kendisi. Müşteri bağlantısı geldiğinde müşteri hesabının e-postası.
    hesap_email = Column(String, nullable=True, index=True)
    #: `__ajans__` ya da hesap e-postası — (saglayici, sahip_anahtari) benzersiz.
    sahip_anahtari = Column(String, nullable=False)
    #: Bağlanan Google hesabının e-postası (id_token'dan).
    harici_email = Column(String, nullable=True)
    #: Fernet ile şifreli yenileme jetonu — düz metin hiçbir yerde yok.
    sifreli_yenileme_jetonu = Column(Text, nullable=True)
    #: Google'ın verdiği kapsamlar (boşlukla ayrılmış). Kullanıcı bazılarını reddedebilir.
    kapsamlar = Column(Text, nullable=True)
    #: {"ga4_mulk": "properties/123", "sc_site": "sc-domain:…", "yt_kanal": "UC…"}
    secimler = Column(Text, nullable=True)
    #: bagli | yeniden_baglan (jeton geçersiz; kullanıcı yeniden onay vermeli)
    durum = Column(String, nullable=False, default="bagli")
    son_esitleme = Column(DateTime(timezone=True), nullable=True)
    #: Son eşitleme denemesi (başarılı ya da değil) — elle eşitleme sınırı buradan.
    son_deneme = Column(DateTime(timezone=True), nullable=True)
    #: {"ga4": "api_kapali", "genel": "invalid_grant"} — kısa kodlar, ham Google metni yok.
    son_hata = Column(Text, nullable=True)
    #: "Yeniden bağlan" bildirimi gönderildi mi (olay başına bir kez).
    hata_bildirildi_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)


class BaglantiDurumu(Base):
    """OAuth `state`: tek kullanımlık, süreli. Değerin özeti + şifreli PKCE doğrulayıcısı."""

    __tablename__ = "baglanti_durumlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: sha256(state) — state'in kendisi yalnız kullanıcının tarayıcısında/Google'da.
    durum_ozeti = Column(String, nullable=False, unique=True, index=True)
    saglayici = Column(String, nullable=False)
    hesap_email = Column(String, nullable=True)
    #: Akışı başlatan yönetici (geri dönüş girişsiz geliyor; denetim aktörü bu).
    baslatan_email = Column(String, nullable=True)
    sifreli_dogrulayici = Column(Text, nullable=False)
    son_kullanma = Column(DateTime(timezone=True), nullable=False, index=True)
    kullanildi_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)


class AnalitikListesi(Base):
    """Sayı olmayan analitik özetleri (en çok tıklanan sorgular/sayfalar)."""

    __tablename__ = "analitik_listeleri"
    __table_args__ = (
        UniqueConstraint("sahip_anahtari", "kaynak", "tur", name="uq_analitik_listesi"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    sahip_anahtari = Column(String, nullable=False)
    #: search_console (ileride: google_analytics sayfaları vb.)
    kaynak = Column(String, nullable=False)
    #: sorgular | sayfalar
    tur = Column(String, nullable=False)
    donem_bas = Column(String, nullable=True)
    donem_bit = Column(String, nullable=True)
    #: [{"anahtar", "tiklama", "gosterim", "to", "sira"}]
    veri = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)
