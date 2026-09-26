from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String, Text


class Service_subscriptions(Base):
    """Müşterinin devam eden hizmeti.

    Fatura tek seferlik bir tutar; abonelik "her ay şu iş yapılıyor"
    demek. İkisi ayrı çünkü bir müşterinin üç aboneliği olabiliyor ve
    her biri ayrı rapor üretiyor.

    `sonraki_rapor` hangi dönemin raporunun beklediğini söylüyor
    (YYYY-MM). Tarih değil metin: ay bazında çalışıyoruz ve
    "2026-09" karşılaştırması gün/saat diliminden etkilenmiyor.
    """

    __tablename__ = "service_subscriptions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    client_email = Column(String, index=True, nullable=False)
    client_name = Column(String, nullable=True)
    hizmet = Column(String, index=True, nullable=False)
    baslik = Column(String, nullable=True)
    tutar = Column(Float, nullable=True)
    para_birimi = Column(String, nullable=True)
    # aylik | yillik
    periyot = Column(String, nullable=True)
    # aktif | duraklatildi | iptal
    durum = Column(String, index=True, nullable=True)
    baslangic = Column(String, nullable=True)        # YYYY-MM
    sonraki_rapor = Column(String, nullable=True)     # YYYY-MM
    notlar = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class Service_reports(Base):
    """Bir aboneliğin bir aylık raporu.

    Taslak ile yayınlanmış ayrı: rapor hazırlanırken müşteri panelinde
    görünmüyor. Yayınlanmadan görünseydi yarım rapor müşteriye gider,
    yanlış sayılar konuşulurdu.

    `metrikler` JSON metni: hizmete göre alanlar değişiyor (SEO'da
    tıklama ve sıra, YouTube'da izlenme). Her hizmet için ayrı sütun
    açmak yerine serbest alan; rapor üretimi Faz 5'te araçlara
    bağlanınca da aynı yerde duracak.
    """

    __tablename__ = "service_reports"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    subscription_id = Column(Integer, index=True, nullable=True)
    client_email = Column(String, index=True, nullable=False)
    hizmet = Column(String, index=True, nullable=True)
    donem = Column(String, index=True, nullable=False)   # YYYY-MM
    baslik = Column(String, nullable=True)
    ozet = Column(Text, nullable=True)
    metrikler = Column(Text, nullable=True)
    # taslak | yayinlandi
    durum = Column(String, index=True, nullable=True)
    yayin_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
