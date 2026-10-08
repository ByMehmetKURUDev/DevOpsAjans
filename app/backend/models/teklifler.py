"""Faz 3T — teklif (öneri) modülü.

`pricing_inquiries` fiyat sihirbazından gelen ham "Teklif Al" kaydı (paket +
eklenti seçimi); bu tablo ajansın müşteriye gönderdiği BİÇİMLİ teklif:
kalemler, KDV, geçerlilik, şartlar, kabul/ret kaydı. Sihirbaz kaydı
"teklife çevir" ile buraya taşınabiliyor (`pricing_inquiry_id`).

Tutarlar Decimal (NUMERIC 14,2): toplamlar sunucuda `services/belge_hesap.py`
ile hesaplanıyor; istemcinin gönderdiği toplam yok sayılıyor.

Bağlantı: girişsiz `/teklif/<jeton>` sayfası `signed_actions` tablosunu
kullanıyor (tür `teklif_onay`): görüntüleme çoklu (jeton çözülür, sayaç
artar), karar (kabul/ret) tek — koşullu UPDATE ile. Ham jeton saklanmıyor.

Durum: taslak | gonderildi | goruntulendi | kabul | ret | suresi_doldu | revize
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class Teklifler(Base):
    __tablename__ = "teklifler"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: TKL-YYYY-NNNN (yıl içinde sıralı, benzersiz).
    no = Column(String, unique=True, index=True, nullable=False)
    #: Müşteri hesabı (küçük harf). Henüz müşteri olmayan aday için boş.
    hesap_email = Column(String, index=True, nullable=True)
    #: Aday (henüz hesabı olmayan) ya da muhatap kişi.
    aday_ad = Column(String, nullable=True)
    aday_eposta = Column(String, index=True, nullable=True)
    baslik = Column(String, nullable=False)
    #: JSON: [{aciklama, adet, birim_fiyat, kdv_orani, indirim, matrah, kdv, toplam}]
    kalemler = Column(Text, nullable=True)
    ara_toplam = Column(Numeric(14, 2), nullable=False, default=0)
    indirim_toplam = Column(Numeric(14, 2), nullable=False, default=0)
    kdv_toplam = Column(Numeric(14, 2), nullable=False, default=0)
    genel_toplam = Column(Numeric(14, 2), nullable=False, default=0)
    para_birimi = Column(String, nullable=False, default="TRY")
    #: YYYY-MM-DD — bu günün sonuna kadar kabul edilebilir.
    gecerlilik = Column(String, nullable=True)
    notlar = Column(Text, nullable=True)
    sartlar = Column(Text, nullable=True)
    durum = Column(String, index=True, nullable=False, default="taslak")

    goruntulenme_sayisi = Column(Integer, nullable=False, default=0)
    ilk_goruntulenme = Column(DateTime(timezone=True), nullable=True)
    son_goruntulenme = Column(DateTime(timezone=True), nullable=True)
    gonderildi_at = Column(DateTime(timezone=True), nullable=True)

    #: Kabul/ret kaydı: zaman, not, IP özeti (ham IP yok), kabul edenin yazdığı ad.
    karar_at = Column(DateTime(timezone=True), nullable=True)
    karar_notu = Column(Text, nullable=True)
    karar_ip_ozeti = Column(String, nullable=True)
    karar_ad = Column(String, nullable=True)

    #: Kabulde otomatik oluşturulacaklar (yöneticinin seçimi).
    otomatik_sozlesme = Column(Boolean, nullable=False, default=False)
    sozlesme_sablon_id = Column(Integer, nullable=True)
    otomatik_fatura = Column(Boolean, nullable=False, default=False)
    #: İlk faturanın oranı (yüzde; boş = %100).
    pesinat_yuzde = Column(Numeric(6, 2), nullable=True)
    otomatik_proje = Column(Boolean, nullable=False, default=False)
    #: Faz 3Z — kabulde oluşan projeye uygulanacak proje şablonu (proje_sablonlari.id).
    proje_sablon_id = Column(Integer, nullable=True)

    #: Bağlar.
    pricing_inquiry_id = Column(Integer, index=True, nullable=True)
    fatura_id = Column(Integer, index=True, nullable=True)
    sozlesme_id = Column(Integer, index=True, nullable=True)
    proje_id = Column(Integer, index=True, nullable=True)
    #: Geçerli imzalı bağlantı (signed_actions.id).
    islem_id = Column(Integer, index=True, nullable=True)
    #: Revizyon zinciri: ilk sürümün kimliği ve bir önceki sürüm.
    kok_id = Column(Integer, index=True, nullable=True)
    onceki_id = Column(Integer, nullable=True)
    surum = Column(Integer, nullable=False, default=1)

    olusturan_eposta = Column(String, nullable=True)
    #: Faz 5K — uygulanan indirim kodu (görünen biçim); satırı kalemlerde `indirim_kodu` işaretli.
    indirim_kodu = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)
