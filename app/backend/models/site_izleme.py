"""Müşteri sitesi bakımı (Faz 2A): bitiş tarihleri, uptime, durum sayfası,
yenileme faturaları ve zamanlanmış görev kayıtları.

Neden ayrı tablolar?
--------------------
`client_sites` "bu siteye bakıyoruz ve erişim izni şu" kaydı; oraya bitiş
tarihi, sağlayıcı, uptime ayarı eklemek o tabloyu her iş için büyütürdü.
Site başına tek `site_izleme` satırı bakım bilgisini, uptime tabloları da
ölçüm geçmişini tutuyor. Bir siteyi silmek bu satırları silmiyor (erişim
günlüğü gibi): kesinti geçmişi sonradan "o ay ne oldu" sorusunun cevabı.

Müşteri parolası burada da YOK: hosting/alan adı sağlayıcısının yalnız ADI
tutuluyor (skill kuralı — şifre kasası yapılmıyor).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class SiteIzleme(Base):
    """Bir müşteri sitesinin bakım kartı (site başına tek satır)."""

    __tablename__ = "site_izleme"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    site_id = Column(Integer, unique=True, index=True, nullable=False)
    #: Kayıtlı alan adı (www. yok, küçük harf). Boşsa site adresinden türetiliyor.
    alan_adi = Column(String, nullable=True)

    # --- Alan adı -----------------------------------------------------------
    alan_bitis = Column(DateTime(timezone=True), nullable=True)
    #: rdap | elle — elle girilen tarih RDAP taramasıyla ezilmiyor.
    alan_bitis_kaynak = Column(String, nullable=True)
    #: RDAP okunamadıysa kısa kod: desteklenmiyor | bulunamadi | ulasilamadi | tarih_yok
    alan_rdap_hata = Column(String, nullable=True)
    alan_kontrol_at = Column(DateTime(timezone=True), nullable=True)
    alan_saglayici = Column(String, nullable=True)

    # --- SSL ------------------------------------------------------------------
    ssl_bitis = Column(DateTime(timezone=True), nullable=True)
    #: gecersiz | olculemedi (dolu ise son ölçüm başarısız)
    ssl_hata = Column(String, nullable=True)
    ssl_kontrol_at = Column(DateTime(timezone=True), nullable=True)
    #: Sertifika elle mi yenileniyor? (Let's Encrypt gibi otomatikse hayır.)
    #: Elle yenilenen sertifika yenileme listesine giriyor ve 30/15 gün
    #: kala da hatırlatılıyor; otomatikte yalnız 7/1 gün kala (o noktada
    #: otomatik yenileme olmamışsa gerçekten sorun var demektir).
    ssl_elle_yenilenir = Column(Boolean, nullable=True, default=False)

    # --- Hosting (elle) -------------------------------------------------------
    hosting_bitis = Column(DateTime(timezone=True), nullable=True)
    hosting_saglayici = Column(String, nullable=True)

    notlar = Column(Text, nullable=True)

    # --- Herkese açık durum sayfası -------------------------------------------
    durum_sayfasi_acik = Column(Boolean, nullable=True, default=False)
    durum_slug = Column(String, unique=True, index=True, nullable=True)
    #: Arama motoru dizinine açık mı? Varsayılan HAYIR (noindex).
    durum_index = Column(Boolean, nullable=True, default=False)

    # --- Teknik SEO + hız izleme (Faz 2H) --------------------------------------
    #: Kaç günde bir otomatik SEO/hız taraması; boş = varsayılan (7), 0 = kapalı.
    seo_tarama_gun = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)


class UptimeKontrolu(Base):
    """Bir adresin düzenli erişilebilirlik kontrolü."""

    __tablename__ = "uptime_kontrolleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    site_id = Column(Integer, index=True, nullable=False)
    url = Column(String, nullable=False)
    #: Dakika; en az 5 (zamanlı uç zaten en sık 5 dakikada bir çalışıyor).
    aralik_dk = Column(Integer, nullable=False, default=5)
    #: Doluysa yanıt gövdesinde geçmeli (büyük/küçük harf duyarsız).
    anahtar_kelime = Column(String, nullable=True)
    beklenen_kod = Column(Integer, nullable=False, default=200)
    acik = Column(Boolean, nullable=False, default=True)

    # Çalışma durumu — zamanlı görev yazıyor (denetim kaydında gürültü sayılıyor).
    son_kontrol_at = Column(DateTime(timezone=True), nullable=True)
    #: up | down | None (henüz ölçülmedi)
    son_durum = Column(String, nullable=True)
    ardisik_hata = Column(Integer, nullable=False, default=0)
    #: Süren hata serisinin ilk ölçümü; kesinti başlangıcı buradan.
    ilk_hata_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)


class UptimeOlcumu(Base):
    """Tek ölçüm. 90 günden eskisi zamanlı görevle siliniyor."""

    __tablename__ = "uptime_olculeri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kontrol_id = Column(Integer, index=True, nullable=False)
    site_id = Column(Integer, index=True, nullable=False)
    zaman = Column(DateTime(timezone=True), index=True, nullable=False, default=_simdi)
    durum_kodu = Column(Integer, nullable=True)
    sure_ms = Column(Integer, nullable=True)
    basarili = Column(Boolean, nullable=False, default=False)
    #: Kısa kategori (ulasilamadi, kod_503, anahtar_kelime_yok…); ham hata metni YOK.
    hata_ozeti = Column(String, nullable=True)


class UptimeGunluk(Base):
    """Gün başına toplam (Türkiye saati). Durum sayfası ve %'ler buradan.

    Ham ölçümden her istekte gün gün saymak 90 günde ~26 bin satır okumak
    demekti; ölçüm yazılırken bu satır da artırılıyor. Ham ölçüm 90 günde
    silinse de günlük toplam kalıyor.
    """

    __tablename__ = "uptime_gunluk"
    __table_args__ = (
        UniqueConstraint("kontrol_id", "gun", name="uq_uptime_gunluk_kontrol_gun"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kontrol_id = Column(Integer, index=True, nullable=False)
    site_id = Column(Integer, index=True, nullable=False)
    gun = Column(String, index=True, nullable=False)  # YYYY-MM-DD (Türkiye saati)
    toplam = Column(Integer, nullable=False, default=0)
    basarili = Column(Integer, nullable=False, default=0)
    toplam_sure_ms = Column(Float, nullable=False, default=0)


class UptimeKesintisi(Base):
    """Kesinti olayı: 2 ardışık başarısız ölçümde açılıp düzelince kapanıyor."""

    __tablename__ = "uptime_kesintileri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kontrol_id = Column(Integer, index=True, nullable=False)
    site_id = Column(Integer, index=True, nullable=False)
    baslangic = Column(DateTime(timezone=True), nullable=False, default=_simdi)
    bitis = Column(DateTime(timezone=True), nullable=True)
    #: Kısa kategori (hata_ozeti ile aynı sözlük); herkese açık sayfada GÖSTERİLMİYOR.
    sebep = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)


class BitisBildirimi(Base):
    """Gönderilmiş bitiş eşikleri: (tür, kayıt, bitiş tarihi, eşik) bir kez.

    Bitiş tarihi anahtarın parçası: yenilenip tarih ileri gidince eşikler
    kendiliğinden sıfırlanıyor. Benzersizlik kısıtı eş zamanlı iki
    çalışmanın aynı bildirimi iki kez göndermesini de önlüyor.
    """

    __tablename__ = "bitis_bildirimleri"
    __table_args__ = (
        UniqueConstraint("tur", "ref_id", "bitis", "esik", name="uq_bitis_bildirimi"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: alan | ssl | hosting | abonelik
    tur = Column(String, nullable=False)
    #: site_id (alan/ssl/hosting) ya da abonelik id'si
    ref_id = Column(Integer, nullable=False)
    bitis = Column(String, nullable=False)  # YYYY-MM-DD
    esik = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_simdi)


class YenilemeFaturasi(Base):
    """Yenileme için kesilen fatura ↔ yenilenen kalem bağı."""

    __tablename__ = "yenileme_faturalari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    tur = Column(String, nullable=False)  # alan | ssl | hosting | abonelik
    ref_id = Column(Integer, index=True, nullable=False)
    bitis = Column(String, nullable=True)  # yenilenen dönemin bitişi (YYYY-MM-DD)
    client_email = Column(String, index=True, nullable=True)
    invoice_id = Column(Integer, index=True, nullable=False)
    payment_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)


class ZamanliCalisma(Base):
    """Zamanlanmış görevlerin son çalışması + küresel kilit satırı (`__genel__`)."""

    __tablename__ = "zamanli_calisma"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    gorev = Column(String, unique=True, index=True, nullable=False)
    son_baslangic = Column(DateTime(timezone=True), nullable=True)
    son_calisma = Column(DateTime(timezone=True), nullable=True)
    sure_ms = Column(Integer, nullable=True)
    #: Kısa JSON özet (sayılar); ham hata metni değil.
    sonuc = Column(Text, nullable=True)
    #: Son çalışma hata verdiyse istisna türü + kısa mesaj (yalnız yönetici görür).
    hata = Column(String, nullable=True)
    #: Küresel satırda: bu ana kadar başka çalışma başlamasın.
    kilit_bitis = Column(DateTime(timezone=True), nullable=True)
    calisma_sayisi = Column(Integer, nullable=False, default=0)
