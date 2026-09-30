from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text


class Pricing_scales(Base):
    """Ölçek (ALFA/BETA/OMEGA/SIGMA) — Fiyatlandırma v5.

    `ozellikler` ve `karsilastirma` JSON metni olarak saklanıyor (bu
    kod tabanında JSONB kullanılmıyor; bkz. inquiries.brief,
    service_reports.metrikler), API katmanında json.loads/dumps ile
    çözülüyor.
    """

    __tablename__ = "pricing_scales"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kod = Column(String, index=True, nullable=False)
    sira = Column(Integer, nullable=False)
    ad = Column(String, nullable=False)
    alt_baslik = Column(String, nullable=False)
    calisan_araligi = Column(String, nullable=False)
    aciklama = Column(Text, nullable=False)
    baz_aylik_fiyat_usd = Column(Float, nullable=False)
    ozellikler = Column(Text, nullable=True)          # JSON: string[]
    eklenti_limiti = Column(String, nullable=True)
    revizyon_saat = Column(String, nullable=True)
    populer = Column(Boolean, nullable=True, default=False)
    karsilastirma = Column(Text, nullable=True)       # JSON: {hosting, sla, panel, devops, mulkiyet, ads, seo}
    # Dil bazlı metinler (JSON): {"en": {"ad": ..., ...}, "de": {...}}. Boş dilde Türkçe alan kullanılır.
    ceviriler = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class Pricing_profiles(Base):
    """Profil çarpanı (kurumsal/startup/stk/bireysel/eğitim)."""

    __tablename__ = "pricing_profiles"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kod = Column(String, index=True, nullable=False)
    ad = Column(String, nullable=False)
    carpan = Column(Float, nullable=False)
    etiket = Column(String, nullable=True)
    sira = Column(Integer, nullable=False)
    # Dil bazlı metinler (JSON): {"en": {"ad": ..., ...}, "de": {...}}. Boş dilde Türkçe alan kullanılır.
    ceviriler = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class Pricing_services(Base):
    """À la carte hizmet kataloğu (80 satır) — yalnızca vitrin, Teklif Al bu tablodan tetiklenmiyor."""

    __tablename__ = "pricing_services"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kategori = Column(String, index=True, nullable=False)
    ad = Column(String, nullable=False)
    baz_fiyat_usd = Column(Float, nullable=False)
    tek_seferlik = Column(Boolean, nullable=True, default=False)
    not_metni = Column(String, nullable=True)
    yeni = Column(Boolean, nullable=True, default=False)
    # Dil bazlı metinler (JSON): {"en": {"ad": ..., ...}, "de": {...}}. Boş dilde Türkçe alan kullanılır.
    ceviriler = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class Pricing_addons(Base):
    """Ölçek başına eklenti — fiyatı kurumsal/×1 baz, diğer profillerde /fiyat-hesapla ile ölçeklenir."""

    __tablename__ = "pricing_addons"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    scale_kod = Column(String, index=True, nullable=False)
    ad = Column(String, nullable=False)
    baz_fiyat_usd = Column(Float, nullable=False)
    birim = Column(String, nullable=True, default="ay")
    sira = Column(Integer, nullable=False)
    # Dil bazlı metinler (JSON): {"en": {"ad": ..., ...}, "de": {...}}. Boş dilde Türkçe alan kullanılır.
    ceviriler = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class Ai_pm_tiers(Base):
    """AI vs PM — ayrı, sabit fiyatlı 4 katmanlı ürün hattı (ölçek/profil çarpanı uygulanmıyor)."""

    __tablename__ = "ai_pm_tiers"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kod = Column(String, index=True, nullable=False)
    ad = Column(String, nullable=False)
    fiyat_aylik_usd = Column(Float, nullable=False)
    rozet = Column(String, nullable=True)
    ozellikler = Column(Text, nullable=True)          # JSON: string[]
    sira = Column(Integer, nullable=False)
    # Dil bazlı metinler (JSON): {"en": {"ad": ..., ...}, "de": {...}}. Boş dilde Türkçe alan kullanılır.
    ceviriler = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class Pricing_inquiries(Base):
    """'Teklif Al' ile oluşan kayıt — ilgili invoices satırına bağlı.

    `kaynak` alanı ileride "kesif_asistani" değerini de alabilecek
    şekilde bırakıldı (bkz. spec'teki "Gelecek entegrasyon notu");
    bu fazda yalnızca "website" yazılıyor.
    """

    __tablename__ = "pricing_inquiries"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    scale_kod = Column(String, nullable=True)
    profile_kod = Column(String, nullable=True)
    ai_pm_tier_kod = Column(String, nullable=True)
    period = Column(String, nullable=True)            # aylik | yillik | kullandikca_ode (eski: tek_seferlik)
    addon_ids = Column(Text, nullable=True)            # JSON: string[]
    hesaplanan_tutar = Column(Float, nullable=False)
    musteri_eposta = Column(String, index=True, nullable=False)
    musteri_adi = Column(String, nullable=True)
    kaynak = Column(String, nullable=True, default="website")
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    # Faz 1E — müşterinin teklife verdiği karar (imzalı işlem bağlantısı ya da
    # müşteri paneli). NULL = henüz karar yok ("bekliyor" sayılıyor).
    # bekliyor | kabul | red
    durum = Column(String, nullable=True)
    # Red gerekçesi (müşterinin yazdığı).
    durum_notu = Column(Text, nullable=True)
    durum_at = Column(DateTime(timezone=True), nullable=True)
