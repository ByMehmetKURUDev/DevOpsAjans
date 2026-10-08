"""Faz 4S — ücretsiz SEO araçlarının günlük kullanım sayaçları.

Araçlarda sorgulanan adres burada (ve günlükte) saklanmıyor. Yalnız araç ×
UTC gün başına sayılar tutuluyor: kaç kez çalıştırıldı, kaçı hata/ret ile
bitti, kaç sonuç e-postayla gönderildi ve bunlardan kaçı CRM'de YENİ aday
açtı. IP, IP özeti, adres, alan adı yok. Hız sınırı sayaçları ayrı
(`hiz_sayaclari`, anahtarı tuzlu IP özeti).
"""

from core.database import Base
from sqlalchemy import Column, Integer, String, UniqueConstraint


class SeoAracIstatistikleri(Base):
    __tablename__ = "seo_arac_istatistikleri"
    __table_args__ = (
        UniqueConstraint("arac", "gun", name="uq_seo_arac_gun"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Araç kısa adı (`services/seo_araclari.ARACLAR`).
    arac = Column(String(40), nullable=False)
    #: UTC gün (YYYY-MM-DD).
    gun = Column(String(10), nullable=False, index=True)
    #: Hız sınırını geçip çalıştırılan istek sayısı (başarılı + hatalı).
    sayi = Column(Integer, nullable=False, default=0)
    #: Bunlardan adres reddi / ulaşılamama / zaman aşımıyla bitenler.
    hata = Column(Integer, nullable=False, default=0)
    #: "Sonucu e-postayla gönder" ile gönderilen sonuç sayısı.
    eposta = Column(Integer, nullable=False, default=0)
    #: Bu e-postalardan CRM'de açılan YENİ aday sayısı (aynı e-postada açık aday varsa sayılmaz).
    aday = Column(Integer, nullable=False, default=0)


__all__ = ["SeoAracIstatistikleri"]
