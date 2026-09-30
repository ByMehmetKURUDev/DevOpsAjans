from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class Site_analyses(Base):
    """Ücretsiz site analizi kayıtları.

    Herkese açık formdan, müşteri panelinden ya da yönetici panelinden
    çalıştırılan her analiz bir satır. Sınır sayımı (alan adı / IP /
    müşteri) da bu tablodan yapılıyor: ayrı bir sayaç tablosu yok.

    Ham IP saklanmıyor; yalnızca özeti (`ip_ozeti`, sha256). Sınır için
    "aynı kaynak mı" sorusunu cevaplamak yetiyor, kim olduğunu bilmek
    gerekmiyor.
    """

    __tablename__ = "site_analyses"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Normalize: küçük harf, başında www. olmayan host. Sınır bu alanla sayılıyor.
    alan_adi = Column(String, nullable=False, index=True)
    #: Taranan başlangıç adresi (kullanıcının verdiği, normalize edilmiş).
    url = Column(String, nullable=False)
    ip_ozeti = Column(String, nullable=True, index=True)
    #: calisiyor | tamam | hata. "calisiyor" analiz sürerken yazılıyor ki
    #: aynı anda gelen istekler de sınıra sayılsın.
    durum = Column(String, nullable=False, default="calisiyor")
    #: Hata durumunda kısa kod (ulasilamadi, adres_yasak…).
    hata_kodu = Column(String, nullable=True)
    #: Genel puan (0-100); ölçülebilen bölümlerin ortalaması.
    puan = Column(Integer, nullable=True)
    #: Bölüm puanları + bölüm başına en çok 3 bulgu (JSON metni).
    ozet_json = Column(Text, nullable=True)
    #: Tam ayrıntı (JSON metni): bütün bulgular, sayfalar, kırık bağlantılar.
    rapor_json = Column(Text, nullable=True)
    eposta = Column(String, nullable=True, index=True)
    ad = Column(String, nullable=True)
    kvkk_onay = Column(Boolean, nullable=False, default=False)
    #: Tam rapor bağlantısının jetonu (secrets.token_urlsafe(16)).
    jeton = Column(String, nullable=True, unique=True, index=True)
    jeton_son = Column(DateTime(timezone=True), nullable=True)
    gonderildi_at = Column(DateTime(timezone=True), nullable=True)
    inquiry_id = Column(Integer, nullable=True)
    #: acik (herkese açık form) | musteri | yonetici
    kaynak = Column(String, nullable=False, default="acik")
    created_at = Column(DateTime(timezone=True), default=_simdi, index=True)
