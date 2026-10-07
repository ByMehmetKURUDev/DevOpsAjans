"""Faz 4L — Marka teması (white-label): müşteri hesabı başına TEK marka kaydı.

Tablo
-----
* `hesap_markalari` — müşterinin herkese açık sayfalarına (kartvizit, QR menü,
  randevu, etkinlik, eğitim, AI asistan, saha servisi, bülten…) uygulanan
  logo / ana renk / vurgu rengi / zemin / köşe / yazı tipi.
  - `hesap_email` kayıt sahibi müşteri hesabı (küçük harf, benzersiz).
  - Renkler `#rrggbb` (küçük harf); zemin `koyu|acik`; köşe
    `keskin|yumusak|yuvarlak`; yazı tipi `jakarta|sistem_sans|sistem_serif|mono`
    (yalnız sitede zaten yüklü yazı tipi ya da sistem yığınları — yeni font yok).
  - Logo `services/dosya_deposu` üzerinden (R2 ya da veritabanı); sunucuda
    Pillow ile küçültülüp WebP'ye çevrilmiş halde. `logo_anahtar` herkese açık
    adresteki tahmin edilemez kimlik (`/api/v1/marka/logo/<anahtar>.webp`); her
    yüklemede yeni → adres değişmez içerik (uzun önbellek).
  - Modül (`marka_temasi`) kapalıyken kayıt durur ama sayfalara uygulanmaz.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class HesapMarkalari(Base):
    __tablename__ = "hesap_markalari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), unique=True, index=True, nullable=False)
    #: Görünen marka adı (logonun alt metni, e-posta başlığı). Boş olabilir.
    ad = Column(String(80), nullable=True)
    ana_renk = Column(String(7), nullable=False, default="#7c3aed")
    vurgu_rengi = Column(String(7), nullable=False, default="#f59e0b")
    zemin = Column(String(8), nullable=False, default="acik")
    kose = Column(String(10), nullable=False, default="yumusak")
    yazi_tipi = Column(String(16), nullable=False, default="jakarta")
    logo_anahtar = Column(String(40), unique=True, index=True, nullable=True)
    logo_depo = Column(String(16), nullable=True)
    logo_yol = Column(String(200), nullable=True)
    logo_genislik = Column(Integer, nullable=True)
    logo_yukseklik = Column(Integer, nullable=True)
    logo_boyut = Column(Integer, nullable=True)
    #: Son değiştiren kişi (ekip üyesi ya da yönetici).
    guncelleyen_email = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)
