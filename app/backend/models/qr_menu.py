"""Faz 4M — QR menü ve WhatsApp katalog mağazası (tek motor, iki düzen).

Tablolar
--------
* `menu_magazalari` — bir mağaza / menü. `duzen`: `menu` (restoran/kafe,
  modül `qr_menu`) ya da `katalog` (ürün vitrini, modül `whatsapp_katalog`).
  - `hesap_email` sahibi müşteri hesabı (küçük harf); BOŞ (NULL) ise ajansın
    kendi mağazası (yönetici panelinden).
  - `slug` herkese açık adres (`/menu/<slug>`), benzersiz; ayrılmış adlar engelli.
  - `ceviriler` mağaza adı/açıklamasının ek dillerdeki karşılığı
    (`{"en": {"ad": .., "aciklama": ..}}`).
  - `calisma_saatleri` haftalık aralıklar (`{"0": [["09:00", "23:00"]], …}`,
    0 = pazartesi); gece yarısını aşan aralık (`["18:00", "02:00"]`) izinli.
  - `siparis_ayarlari` WhatsApp siparişi, teslimat türleri, en düşük tutar,
    paket ücreti (kuruş), sipariş notu, kapalıyken sipariş.
  - `saklama_gun`: siparişteki kişisel alanlar bu kadar gün sonra
    anonimleştirilir (zamanlanmış görev yok — istekle tetiklenir).
* `menu_kategorileri`, `menu_urunleri` — sıralı kategori ve ürünler. Fiyatlar
  TAM SAYI kuruş (alt birim): kayan nokta yuvarlama hatası yok.
  `secenek_gruplari` JSON (Boy: tek seçim + fiyat farkı; Ekstralar: çoklu, en
  az/en çok). `etiketler`, `alerjenler` anahtar listeleri (14 alerjen: AB
  1169/2011 Ek II = Türk Gıda Kodeksi Etiketleme Yönetmeliği Ek-1).
* `menu_kuponlari` — basit kupon: yüzde ya da tutar, tarih aralığı, kullanım sınırı.
* `menu_siparisleri` — WhatsApp siparişi. Kalemler ve tutarlar SUNUCUDA
  hesaplanır (istemcinin gönderdiği fiyat yok sayılır). Kişisel alanlar
  (`musteri_ad`, `adres`, `siparis_notu`) saklama süresi dolunca NULL olur.
  Denetim kaydına kopyalanmaz (kişisel veri; `services/denetim.py`).
* `menu_olaylari` — analitik: görüntülenme, ürün görüntüleme, sepete ekleme,
  sipariş. Ham IP / User-Agent YOK: gün + tuzla alınmış IP özeti ve bot işareti.
* `menu_gorselleri` — yüklenen görsellerin kaydı (içerik `services/dosya_deposu`
  üzerinden: S3/R2 ya da veritabanı). Her görselin iki WebP boyu var
  (`k` küçük, `b` büyük); boyutlar `<img width/height>` için saklanıyor.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class MenuMagazalari(Base):
    __tablename__ = "menu_magazalari"
    __table_args__ = (
        Index("ix_menu_magazalari_hesap_duzen", "hesap_email", "duzen"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Sahip müşteri hesabı; NULL = ajansın kendi mağazası.
    hesap_email = Column(String, index=True, nullable=True)
    olusturan_email = Column(String, nullable=True)
    slug = Column(String(60), unique=True, index=True, nullable=False)
    #: menu | katalog
    duzen = Column(String(12), nullable=False, default="menu")
    ad = Column(String(120), nullable=False)
    aciklama = Column(Text, nullable=True)
    ceviriler = Column(Text, nullable=True)
    logo = Column(String(64), nullable=True)
    kapak = Column(String(64), nullable=True)
    tema_rengi = Column(String(7), nullable=False, default="#7c3aed")
    adres = Column(String(300), nullable=True)
    telefon = Column(String(20), nullable=True)
    #: E.164 (`+905551112233`); WhatsApp siparişi buraya gider.
    whatsapp = Column(String(20), nullable=True)
    calisma_saatleri = Column(Text, nullable=True)
    saat_dilimi = Column(String(64), nullable=False, default="Europe/Istanbul")
    para_birimi = Column(String(3), nullable=False, default="TRY")
    varsayilan_dil = Column(String(2), nullable=False, default="tr")
    ek_diller = Column(Text, nullable=True)
    siparis_ayarlari = Column(Text, nullable=True)
    saklama_gun = Column(Integer, nullable=False, default=90)
    #: Arama motorlarında görünsün mü (varsayılan hayır → noindex).
    arama_motoru = Column(Boolean, nullable=False, default=False)
    aktif = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class MenuKategorileri(Base):
    __tablename__ = "menu_kategorileri"
    __table_args__ = (
        Index("ix_menu_kategorileri_magaza_sira", "magaza_id", "sira"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    magaza_id = Column(Integer, index=True, nullable=False)
    ad = Column(String(80), nullable=False)
    ceviriler = Column(Text, nullable=True)
    gorsel = Column(String(64), nullable=True)
    sira = Column(Integer, nullable=False, default=0)
    gizli = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class MenuUrunleri(Base):
    __tablename__ = "menu_urunleri"
    __table_args__ = (
        Index("ix_menu_urunleri_magaza_kategori_sira", "magaza_id", "kategori_id", "sira"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    magaza_id = Column(Integer, index=True, nullable=False)
    kategori_id = Column(Integer, index=True, nullable=False)
    ad = Column(String(120), nullable=False)
    aciklama = Column(Text, nullable=True)
    #: Kuruş (alt birim).
    fiyat = Column(Integer, nullable=False, default=0)
    indirimli_fiyat = Column(Integer, nullable=True)
    gorsel = Column(String(64), nullable=True)
    secenek_gruplari = Column(Text, nullable=True)
    etiketler = Column(Text, nullable=True)
    alerjenler = Column(Text, nullable=True)
    kalori = Column(Integer, nullable=True)
    stokta_yok = Column(Boolean, nullable=False, default=False)
    gizli = Column(Boolean, nullable=False, default=False)
    sira = Column(Integer, nullable=False, default=0)
    ceviriler = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class MenuKuponlari(Base):
    __tablename__ = "menu_kuponlari"
    __table_args__ = (
        UniqueConstraint("magaza_id", "kod", name="uq_menu_kuponlari_magaza_kod"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    magaza_id = Column(Integer, index=True, nullable=False)
    #: Büyük harf, boşluksuz.
    kod = Column(String(32), nullable=False)
    #: yuzde | tutar
    tur = Column(String(8), nullable=False, default="yuzde")
    #: Yüzdede 1–100; tutarda kuruş.
    deger = Column(Integer, nullable=False, default=0)
    #: Kuponun geçerli olduğu en düşük ara toplam (kuruş); boş = sınırsız.
    en_dusuk_tutar = Column(Integer, nullable=True)
    baslangic = Column(DateTime(timezone=True), nullable=True)
    bitis = Column(DateTime(timezone=True), nullable=True)
    kullanim_siniri = Column(Integer, nullable=True)
    kullanim_sayisi = Column(Integer, nullable=False, default=0)
    aktif = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class MenuSiparisleri(Base):
    __tablename__ = "menu_siparisleri"
    __table_args__ = (
        Index("ix_menu_siparisleri_magaza_durum", "magaza_id", "durum"),
        Index("ix_menu_siparisleri_magaza_zaman", "magaza_id", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    magaza_id = Column(Integer, index=True, nullable=False)
    siparis_no = Column(String(12), unique=True, index=True, nullable=False)
    #: yeni | hazirlaniyor | teslim_edildi | iptal
    durum = Column(String(16), nullable=False, default="yeni")
    #: gel_al | paket | masada
    teslimat = Column(String(10), nullable=False, default="gel_al")
    masa = Column(String(12), nullable=True)
    # --- Kişisel alanlar: saklama süresi dolunca NULL ---
    musteri_ad = Column(String(80), nullable=True)
    adres = Column(Text, nullable=True)
    siparis_notu = Column(Text, nullable=True)
    anonim = Column(Boolean, nullable=False, default=False, index=True)
    # --- Sunucunun hesapladığı tutarlar (kuruş) ---
    kalemler = Column(Text, nullable=False)
    ara_toplam = Column(Integer, nullable=False, default=0)
    indirim = Column(Integer, nullable=False, default=0)
    kupon_kodu = Column(String(32), nullable=True)
    paket_ucreti = Column(Integer, nullable=False, default=0)
    toplam = Column(Integer, nullable=False, default=0)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    dil = Column(String(2), nullable=False, default="tr")
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class MenuOlaylari(Base):
    __tablename__ = "menu_olaylari"
    __table_args__ = (
        Index("ix_menu_olaylari_magaza_gun", "magaza_id", "gun"),
        Index("ix_menu_olaylari_magaza_tur", "magaza_id", "tur"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    magaza_id = Column(Integer, nullable=False)
    #: goruntuleme | urun | sepet | siparis
    tur = Column(String(12), nullable=False)
    urun_id = Column(Integer, nullable=True)
    zaman = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    #: UTC gün (YYYY-MM-DD).
    gun = Column(String(10), nullable=False)
    #: Gün + tuz ile alınmış sha256 (ham IP yok).
    ip_ozeti = Column(String(64), nullable=False)
    bot = Column(Boolean, nullable=False, default=False)


class MenuGorselleri(Base):
    __tablename__ = "menu_gorselleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    magaza_id = Column(Integer, index=True, nullable=False)
    #: Rastgele, tahmin edilemez anahtar (herkese açık adresin parçası).
    anahtar = Column(String(64), unique=True, index=True, nullable=False)
    depo = Column(String(16), nullable=False, default="veritabani")
    genislik = Column(Integer, nullable=False, default=0)
    yukseklik = Column(Integer, nullable=False, default=0)
    #: İki boyun toplam bayt sayısı.
    boyut = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
