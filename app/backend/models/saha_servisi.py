"""Faz 6S — Saha servisi (temizlik, klima, teknik servis, bakım-onarım firmaları).

Kim kimdir?
-----------
Modülü ajansın MÜŞTERİSİ (ör. bir klima servis firması) kendi işi için kullanır:
* müşteri hesabı (`hesap_email`) = servis firması;
* firmanın teknisyenleri = hesap ekibi üyeleri (Faz 2E) — `saha_teknisyen` izni +
  bu modüldeki teknisyen listesi (`saha_teknisyenleri`; dispatch satırları);
* firmanın kendi müşterileri = "servis müşterisi" (`saha_musterileri`) — portala
  giriş yapmazlar, imzalı (girişsiz) bağlantıyla iş durumunu görür, servis formunu
  indirir ve puan verirler.

Tablolar
--------
* `saha_ayarlari` — hesap başına tek satır: firma künyesi (servis formu başlığı),
  KDV oranı, saklama süresi, servis müşterisine e-posta anahtarları, imza zorunluluğu,
  randevu → iş emri kancası, Google yorum sayfası seçimi, hazır şablon tohumu izi.
* `saha_teknisyenleri` — dispatch satırları. `eposta` hesabın sahibi ya da ekip
  üyesi. Konum rızası (KVKK): zaman + metin sürümü; geri alınınca `konum_rizasi_geri_at`
  dolar ve konum alınmaz (iş yine yapılır).
* `saha_musterileri` / `saha_lokasyonlari` / `saha_cihazlari` — servis müşterisi
  (bireysel/kurumsal), adresleri ve cihaz/varlık kaydı (marka, model, seri no,
  kurulum, garanti, son bakım, bakım periyodu). `bakim_bildirim_tarihi`: hangi bakım
  vadesi için "bakım zamanı" bildirimi gitti (vade başına TEK bildirim).
* `saha_sablonlari` — kontrol listesi şablonları (maddeler JSON).
* `saha_malzemeleri` — malzeme/parça kataloğu + basit stok (tam envanter ileride).
* `saha_is_emirleri` — iş emri. Zamanlar UTC. Kontrol listesi iş emri açılırken
  şablondan KOPYALANIR (şablon sonradan değişse de iş emri değişmez). Konum yalnız
  "başla" ve "bitir" anında, rıza varsa; 90 gün sonra ham koordinat silinir
  (`konum_indirgendi_at`) — iş emrinin adresi kalır. Fiyatlar kuruş (tam sayı).
* `saha_is_atamalari` — iş emri × teknisyen (bir işte birden çok teknisyen).
* `saha_is_cihazlari` — iş emri × cihaz (cihaz geçmişi bu tablodan).
* `saha_is_fotograflari` — önce/sonra/madde fotoğrafları (içerik dosya deposunda;
  EXIF — konum dahil — sunucuda silinmiş, WebP).
* `saha_malzeme_kullanimi` — iş emrinde kullanılan malzeme (stoktan düşüm).
* `saha_durum_gecmisi` — durum geçişleri (kim, ne zaman, neden).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class SahaAyarlari(Base):
    __tablename__ = "saha_ayarlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), unique=True, index=True, nullable=False)
    firma_adi = Column(String(160), nullable=True)
    telefon = Column(String(32), nullable=True)
    eposta = Column(String(254), nullable=True)
    adres = Column(Text, nullable=True)
    vergi_no = Column(String(64), nullable=True)
    varsayilan_dil = Column(String(2), nullable=False, default="tr")
    para_birimi = Column(String(3), nullable=False, default="TRY")
    kdv_orani = Column(Integer, nullable=False, default=20)
    #: Servis müşterisinin kişisel verisi son işten bu kadar ay sonra anonimleşir.
    saklama_ay = Column(Integer, nullable=False, default=60)
    imza_zorunlu = Column(Boolean, nullable=False, default=False)
    bildirim_planlandi = Column(Boolean, nullable=False, default=True)
    bildirim_yolda = Column(Boolean, nullable=False, default=True)
    bildirim_tamamlandi = Column(Boolean, nullable=False, default=True)
    memnuniyet_acik = Column(Boolean, nullable=False, default=True)
    #: Faz 4K yorum sayfası (boşsa hesabın ilk aktif sayfası; modül kapalıysa bağlantı yok).
    yorum_sayfasi_id = Column(Integer, nullable=True)
    #: Faz 5R randevusu → iş emri (randevu modülü açıksa).
    randevu_kancasi = Column(Boolean, nullable=False, default=False)
    randevu_is_turu = Column(String(16), nullable=False, default="kesif")
    #: Bakım vadesine bu kadar gün kala "bakım zamanı" bildirimi.
    bakim_on_gun = Column(Integer, nullable=False, default=7)
    #: Hazır şablonlar bir kez eklendi (silinenler geri gelmesin).
    tohumlandi = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class SahaTeknisyenleri(Base):
    __tablename__ = "saha_teknisyenleri"
    __table_args__ = (
        UniqueConstraint("hesap_email", "eposta", name="uq_saha_teknisyen_hesap_eposta"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    eposta = Column(String(254), index=True, nullable=False)
    ad = Column(String(120), nullable=False)
    telefon = Column(String(32), nullable=True)
    renk = Column(String(7), nullable=False, default="#7c3aed")
    aktif = Column(Boolean, nullable=False, default=True)
    sira = Column(Integer, nullable=False, default=0)
    #: KVKK açık rıza: verildiği an + gösterilen metnin sürümü; geri alınınca dolu.
    konum_rizasi_at = Column(DateTime(timezone=True), nullable=True)
    konum_rizasi_surumu = Column(String(32), nullable=True)
    konum_rizasi_geri_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class SahaMusterileri(Base):
    __tablename__ = "saha_musterileri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    #: bireysel | kurumsal
    tur = Column(String(10), nullable=False, default="bireysel")
    ad = Column(String(160), nullable=False)
    firma = Column(String(160), nullable=True)
    eposta = Column(String(254), nullable=True)
    telefon = Column(String(32), nullable=True)
    vergi_no = Column(String(64), nullable=True)
    notlar = Column(Text, nullable=True)
    dil = Column(String(2), nullable=False, default="tr")
    #: Saklama süresi dolunca kişisel alanlar boşaltıldı.
    anonim = Column(Boolean, nullable=False, default=False)
    son_is_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class SahaLokasyonlari(Base):
    __tablename__ = "saha_lokasyonlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    musteri_id = Column(Integer, index=True, nullable=False)
    ad = Column(String(120), nullable=False)
    adres = Column(Text, nullable=True)
    ilce = Column(String(80), nullable=True)
    il = Column(String(80), nullable=True)
    posta_kodu = Column(String(16), nullable=True)
    #: Kapı kodu, kat, otopark… (teknisyen görür).
    notlar = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class SahaCihazlari(Base):
    __tablename__ = "saha_cihazlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    musteri_id = Column(Integer, index=True, nullable=False)
    lokasyon_id = Column(Integer, index=True, nullable=True)
    tur = Column(String(60), nullable=False)
    marka = Column(String(80), nullable=True)
    model = Column(String(80), nullable=True)
    seri_no = Column(String(80), nullable=True)
    kurulum_tarihi = Column(Date, nullable=True)
    garanti_bitis = Column(Date, nullable=True)
    son_bakim = Column(Date, nullable=True)
    #: Ay cinsinden bakım periyodu (boş = periyodik bakım yok).
    bakim_periyot_ay = Column(Integer, nullable=True)
    notlar = Column(Text, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    #: Bildirimi giden bakım vadesi (vade başına tek bildirim).
    bakim_bildirim_tarihi = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class SahaSablonlari(Base):
    __tablename__ = "saha_sablonlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    ad = Column(String(120), nullable=False)
    #: Bu iş türünün varsayılan şablonu (boş = yok).
    is_turu = Column(String(16), nullable=True)
    #: JSON: [{id, metin, tur, zorunlu, birim}]
    maddeler = Column(Text, nullable=False, default="[]")
    aktif = Column(Boolean, nullable=False, default=True)
    #: Hazır şablonun anahtarı (tohum); elle oluşturulanlarda boş.
    hazir = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class SahaMalzemeleri(Base):
    __tablename__ = "saha_malzemeleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    ad = Column(String(160), nullable=False)
    kod = Column(String(60), nullable=True)
    birim = Column(String(12), nullable=False, default="adet")
    #: KDV hariç birim fiyat (kuruş).
    birim_fiyat = Column(Integer, nullable=False, default=0)
    #: Boş = stok izlenmiyor.
    stok = Column(Float, nullable=True)
    kritik_stok = Column(Float, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class SahaIsEmirleri(Base):
    __tablename__ = "saha_is_emirleri"
    __table_args__ = (
        UniqueConstraint("hesap_email", "no", name="uq_saha_is_emri_no"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    no = Column(String(24), nullable=False)
    #: Kalıcı rastgele kimlik (imzalı müşteri bağlantısı buna bağlı).
    uid = Column(String(32), unique=True, index=True, nullable=False)
    #: kurulum | ariza | bakim | temizlik | kesif
    tur = Column(String(16), nullable=False, default="ariza")
    #: dusuk | normal | yuksek | acil
    oncelik = Column(String(10), nullable=False, default="normal")
    #: yeni | planlandi | yolda | iste | tamamlandi | iptal | ertelendi
    durum = Column(String(12), nullable=False, default="yeni", index=True)
    baslik = Column(String(160), nullable=False)
    aciklama = Column(Text, nullable=True)
    musteri_id = Column(Integer, index=True, nullable=False)
    lokasyon_id = Column(Integer, nullable=True)
    plan_bas = Column(DateTime(timezone=True), nullable=True, index=True)
    plan_bit = Column(DateTime(timezone=True), nullable=True)
    tahmini_dk = Column(Integer, nullable=False, default=60)
    sablon_id = Column(Integer, nullable=True)
    #: JSON: şablondan kopyalanan maddeler.
    kontrol_listesi = Column(Text, nullable=True)
    #: JSON: {madde_id: değer}
    kontrol_yanitlari = Column(Text, nullable=True)
    teknisyen_notu = Column(Text, nullable=True)
    iscilik_dk = Column(Integer, nullable=True)
    #: KDV hariç işçilik ücreti (kuruş).
    iscilik_ucreti = Column(Integer, nullable=False, default=0)
    #: Teknisyen "tekrar ziyaret gerekli" dedi (ilk seferde çözüm sayılmaz).
    takip_gerekli = Column(Boolean, nullable=False, default=False)
    ertele_sayisi = Column(Integer, nullable=False, default=0)
    #: Faz 5R randevusundan açıldıysa (aynı randevu iki iş emri açmasın).
    randevu_id = Column(Integer, unique=True, nullable=True)
    planlandi_at = Column(DateTime(timezone=True), nullable=True)
    yolda_at = Column(DateTime(timezone=True), nullable=True)
    basla_at = Column(DateTime(timezone=True), nullable=True)
    bitir_at = Column(DateTime(timezone=True), nullable=True)
    iptal_at = Column(DateTime(timezone=True), nullable=True)
    ertele_at = Column(DateTime(timezone=True), nullable=True)
    #: Tek seferlik konum (yalnız başla/bitir anında, rızayla). 90 gün sonra silinir.
    basla_enlem = Column(Float, nullable=True)
    basla_boylam = Column(Float, nullable=True)
    basla_dogruluk = Column(Float, nullable=True)
    bitir_enlem = Column(Float, nullable=True)
    bitir_boylam = Column(Float, nullable=True)
    bitir_dogruluk = Column(Float, nullable=True)
    konum_indirgendi_at = Column(DateTime(timezone=True), nullable=True)
    imza_anahtari = Column(String(64), nullable=True)
    imza_depo = Column(String(16), nullable=True)
    imza_ad = Column(String(120), nullable=True)
    imza_at = Column(DateTime(timezone=True), nullable=True)
    memnuniyet_puan = Column(Integer, nullable=True)
    memnuniyet_yorum = Column(Text, nullable=True)
    memnuniyet_at = Column(DateTime(timezone=True), nullable=True)
    #: JSON: servis müşterisine giden e-postalar {"planlandi": iso, ...} (tekrar gitmesin).
    musteri_bildirimleri = Column(Text, nullable=True)
    anonim = Column(Boolean, nullable=False, default=False)
    olusturan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class SahaIsAtamalari(Base):
    __tablename__ = "saha_is_atamalari"
    __table_args__ = (
        UniqueConstraint("is_emri_id", "teknisyen_id", name="uq_saha_atama"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    is_emri_id = Column(Integer, index=True, nullable=False)
    teknisyen_id = Column(Integer, index=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class SahaIsCihazlari(Base):
    __tablename__ = "saha_is_cihazlari"
    __table_args__ = (
        UniqueConstraint("is_emri_id", "cihaz_id", name="uq_saha_is_cihaz"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    is_emri_id = Column(Integer, index=True, nullable=False)
    cihaz_id = Column(Integer, index=True, nullable=False)


class SahaIsFotograflari(Base):
    __tablename__ = "saha_is_fotograflari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    is_emri_id = Column(Integer, index=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    #: Rastgele depo anahtarları (büyük ve küçük boy WebP).
    anahtar = Column(String(64), unique=True, index=True, nullable=False)
    kucuk_anahtar = Column(String(64), nullable=False)
    depo = Column(String(16), nullable=False, default="veritabani")
    #: once | sonra | madde
    tur = Column(String(8), nullable=False, default="once")
    madde_id = Column(String(16), nullable=True)
    genislik = Column(Integer, nullable=False, default=0)
    yukseklik = Column(Integer, nullable=False, default=0)
    boyut = Column(Integer, nullable=False, default=0)
    yukleyen = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class SahaMalzemeKullanimi(Base):
    __tablename__ = "saha_malzeme_kullanimi"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    is_emri_id = Column(Integer, index=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    malzeme_id = Column(Integer, nullable=True)
    ad = Column(String(160), nullable=False)
    birim = Column(String(12), nullable=False, default="adet")
    miktar = Column(Float, nullable=False, default=1.0)
    birim_fiyat = Column(Integer, nullable=False, default=0)
    #: Bu satır stoktan düştü (silinince geri eklenir).
    stoktan_dusuldu = Column(Boolean, nullable=False, default=False)
    ekleyen = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class SahaDurumGecmisi(Base):
    __tablename__ = "saha_durum_gecmisi"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    is_emri_id = Column(Integer, index=True, nullable=False)
    eski = Column(String(12), nullable=True)
    yeni = Column(String(12), nullable=False)
    kisi = Column(String(254), nullable=True)
    neden = Column(Text, nullable=True)
    #: Bu geçişte konum kaydedildi mi (koordinat burada tutulmuyor).
    konum_alindi = Column(Boolean, nullable=False, default=False)
    zaman = Column(DateTime(timezone=True), default=_simdi, nullable=False)
