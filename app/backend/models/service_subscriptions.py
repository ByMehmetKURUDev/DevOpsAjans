from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text


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
    # Faz 3T — tekrarlayan fatura şablonu (tek kaynak: abonelik). Açıksa
    # zamanlı görev her dönem (aylık: YYYY-MM, yıllık: YYYY) bir fatura
    # kesiyor; dönem kilidi `tekrarlayan_fatura_kayitlari` (benzersiz).
    fatura_otomatik = Column(Boolean, nullable=True)
    #: JSON kalem listesi (services/belge_hesap.py biçimi)
    fatura_kalemleri = Column(Text, nullable=True)
    #: İlk faturalanacak dönem (YYYY-MM); öncesi geriye dönük kesilmez.
    fatura_baslangic = Column(String, nullable=True)
    vade_gun = Column(Integer, nullable=True)
    son_fatura_donemi = Column(String, nullable=True)
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
    # Faz 2C — aylık müşteri raporu aynı tabloda (çiftleme yok):
    # `tur` boşsa abonelik raporu, "aylik" ise müşteri başına ay kapanış raporu.
    tur = Column(String, index=True, nullable=True)
    # Aylık raporun toplanmış verisi (JSON metni: özet, site sağlığı, SEO, plan).
    veri = Column(Text, nullable=True)
    # Yöneticinin rapora eklediği not (müşteri görür).
    yonetici_notu = Column(Text, nullable=True)
    # Yayın e-postasının gittiği an — "bir kez" güvencesi (koşullu UPDATE).
    eposta_gonderildi_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
