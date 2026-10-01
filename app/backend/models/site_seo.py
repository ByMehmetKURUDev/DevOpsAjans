"""Faz 2H — müşteri siteleri için teknik SEO + Core Web Vitals izleme (modül #31).

`site_seo_gecmisi`: site başına her ölçüm bir satır. Ölçümü `services/site_analizi`
motoru yapıyor (ücretsiz site analizinin AYNISI); burada yalnız sonucun özeti
duruyor: puanlar, Core Web Vitals sayıları ve bulgu KODLARI. Ham sayfa içeriği
(HTML, başlık metni, bağlantı adresleri) tutulmuyor — müşterinin sitesinden
okunan metin bu tabloya hiç girmiyor.

`site_seo_uyarilari`: gönderilmiş uyarılar. Aynı sorun (puan düşüşü, belirli bir
kritik bulgu, kırık bağlantı artışı) için 7 günde bir kez bildirim gidiyor;
karar bu tablodan.

Site silinince satırlar SİLİNMİYOR (uptime geçmişi gibi): aylık raporda "o ay ne
oldu" sorusunun cevabı.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Float, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class SiteSeoGecmisi(Base):
    """Tek SEO/hız ölçümü."""

    __tablename__ = "site_seo_gecmisi"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    site_id = Column(Integer, index=True, nullable=False)
    #: Ölçüm anındaki site sahibi (hesap). Site başka hesaba geçse de geçmiş
    #: o günkü sahibine ait kalıyor.
    hesap_email = Column(String, index=True, nullable=False)
    olcum_at = Column(DateTime(timezone=True), index=True, nullable=False, default=_simdi)
    #: zamanli | elle (müşteri "Şimdi tara") | yonetici
    kaynak = Column(String, nullable=False, default="zamanli")
    #: calisiyor | tamam | hata — "calisiyor" yalnız ölçüm sürerken (çift tıklamaya kilit).
    durum = Column(String, nullable=False, default="tamam")
    #: Site hiç açılamadıysa kısa kod (ulasilamadi, cozumlenemedi, adres_yasak…).
    hata_kodu = Column(String, nullable=True)

    genel_puan = Column(Integer, nullable=True)
    #: {"hiz": 88, "seo": 72, …} — ölçülemeyen bölüm null.
    bolum_puanlari = Column(Text, nullable=True)
    mobil_puan = Column(Integer, nullable=True)
    masaustu_puan = Column(Integer, nullable=True)
    #: Core Web Vitals (laboratuvar): mobil ölçümden, yoksa masaüstünden.
    lcp_ms = Column(Integer, nullable=True)
    cls = Column(Float, nullable=True)
    tbt_ms = Column(Integer, nullable=True)
    #: [{"kod", "seviye", "bolum", "deger"?}] — kod ve seviye; sayfa metni yok.
    bulgu_ozeti = Column(Text, nullable=True)
    sure_ms = Column(Integer, nullable=True)


class SiteSeoUyarisi(Base):
    """Gönderilmiş SEO uyarısı: (site, sorun) için 7 günde bir."""

    __tablename__ = "site_seo_uyarilari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    site_id = Column(Integer, index=True, nullable=False)
    #: puan_dususu | kirik_baglanti | kritik:<bulgu kodu>
    sorun = Column(String, index=True, nullable=False)
    olcum_id = Column(Integer, nullable=True)
    gonderim_at = Column(DateTime(timezone=True), index=True, nullable=False, default=_simdi)
