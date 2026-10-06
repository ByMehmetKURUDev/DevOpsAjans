"""Faz 6E — Etkinlik ve bilet: kayıt, QR bilet, kapıda okutma.

Tablolar
--------
* `etkinlikler` — seminer, atölye, konser, webinar, kurs tanıtım günü… Herkese açık
  sayfa `/etkinlik/<slug>`. `hesap_email` BOŞ (NULL) ise ajansın kendi etkinliği
  (ücretli bilet YALNIZ burada: para ajansın ödeme hesabına gidiyor); doluysa müşterinin
  etkinliği (yalnız ücretsiz kayıt + "kapıda ödeme / havale bilgisi" metni).
  Zamanlar UTC; `saat_dilimi` gösterim için. `online_baglanti` yalnız bilet sahiplerine
  (bilet sayfası + e-posta) gösterilir, herkese açık yanıtta YOK. `kilit`: kayıt sırasında
  satır kilidi sayacı (PostgreSQL'de satır kilidi, SQLite'ta yazma kilidi). `gorevli_surumu`
  artırılınca bütün görevli (kapı) bağlantıları geçersiz olur.
* `etkinlik_bilet_turleri` — "Erken kayıt", "Standart", "Öğrenci"…: fiyat (kuruş; 0 =
  ücretsiz), para birimi, kontenjan, satış aralığı, kişi başı en çok adet, gizli tür (yalnız
  kodla görünür).
* `etkinlik_indirim_kodlari` — yüzde / tutar (kuruş), kullanım sınırı (`kullanilan`
  KOŞULLU UPDATE ile artar: sınır aşılamaz), son tarih, hangi türlere geçerli.
* `etkinlik_siparisleri` — bir kayıt (bir kişi, bir ya da birkaç bilet). `kod` bilet
  sayfası jetonunun parçası. Ücretli kayıt `odeme_bekliyor` ile açılır, yerleri `odeme_son`
  zamanına kadar tutar; ödeme sağlayıcısının webhook'u gelince `onayli` olur. Kişisel
  alanlar saklama süresi dolunca NULL (`anonim`).
* `etkinlik_biletleri` — tek bilet: benzersiz `kod` (QR'da yalnız kod + HMAC imzası,
  kişisel veri yok). **Kapasite koruması (veritabanı düzeyi):** `(etkinlik_id, koltuk)` ve
  `(tur_id, tur_koltuk)` benzersiz; kapasite 0..N-1 koltuk numarası demek, iptal edilen
  biletin koltuğu NULL olur (yer boşalır). Eşzamanlı iki kayıt etkinlik satırı kilidiyle
  sıraya girer, kilit tutmasa bile benzersizlik son güvence. Kapıda giriş `giris_at` KOŞULLU
  UPDATE ile yazılır (`... WHERE giris_at IS NULL`): ikinci okutma "zaten girdi".
* `etkinlik_bekleme` — bekleme listesi; yer açılınca sıradakine 24 saat geçerli imzalı
  davet bağlantısı (davetli kişi o süre boyunca yerini tutar).
* `etkinlik_okutmalar` — kapı okutma günlüğü (sonuç, kaynak; canlı sayaç ve son okutmalar).
* `etkinlik_gorselleri` — kapak görseli (içerik `services/dosya_deposu`; WebP).
* `etkinlik_listeleri` — hesabın herkese açık etkinlik listesi (`/etkinlikler/<slug>`,
  isteğe bağlı). `kapsam`: ajans için `@ajans`, müşteride hesap e-postası.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class Etkinlikler(Base):
    __tablename__ = "etkinlikler"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Sahip müşteri hesabı; NULL = ajansın kendi etkinliği.
    hesap_email = Column(String(254), index=True, nullable=True)
    olusturan_email = Column(String(254), nullable=True)
    slug = Column(String(60), unique=True, index=True, nullable=False)
    baslik = Column(String(160), nullable=False)
    #: Kısa özet (paylaşım önizlemesi, liste kartı).
    ozet = Column(String(300), nullable=True)
    #: Zengin metin (güvenli markdown; HTML çizilmez).
    aciklama = Column(Text, nullable=True)
    kapak = Column(String(64), nullable=True)
    renk = Column(String(7), nullable=False, default="#7c3aed")
    #: yuz_yuze | online | karma
    bicim = Column(String(10), nullable=False, default="yuz_yuze")
    mekan_adi = Column(String(160), nullable=True)
    adres = Column(Text, nullable=True)
    harita_url = Column(String(500), nullable=True)
    #: YALNIZ bilet sahiplerine (bilet sayfası, e-posta, ICS).
    online_baglanti = Column(String(500), nullable=True)
    saat_dilimi = Column(String(64), nullable=False, default="Europe/Istanbul")
    baslangic = Column(DateTime(timezone=True), nullable=False)
    bitis = Column(DateTime(timezone=True), nullable=False)
    #: JSON: [{"ad", "baslangic", "bitis"}] — birden çok oturum/gün (isteğe bağlı).
    oturumlar = Column(Text, nullable=True)
    #: NULL = sınırsız (yalnız ajans; müşteride modül ayarı üst sınır).
    kapasite = Column(Integer, nullable=True)
    kayit_acilis = Column(DateTime(timezone=True), nullable=True)
    #: NULL = etkinlik başlayana kadar.
    kayit_kapanis = Column(DateTime(timezone=True), nullable=True)
    #: taslak | yayinda | iptal | tamamlandi
    durum = Column(String(12), nullable=False, default="taslak", index=True)
    dil = Column(String(2), nullable=False, default="tr")
    organizator_ad = Column(String(160), nullable=True)
    organizator_eposta = Column(String(254), nullable=True)
    organizator_url = Column(String(500), nullable=True)
    iade_politikasi = Column(Text, nullable=True)
    #: Organizatörün ek aydınlatma metni (KVKK); boşsa varsayılan satır + /gizlilik.
    kvkk_metni = Column(Text, nullable=True)
    #: Müşteri etkinliğinde ödeme notu ("kapıda ödeme", "havale bilgisi") — para toplanmaz.
    odeme_notu = Column(Text, nullable=True)
    #: "Herkese açık + arama motorlarında görünsün" → index + schema.org Event JSON-LD.
    arama_motoru = Column(Boolean, nullable=False, default=False)
    #: Hesabın herkese açık etkinlik listesinde görünsün mü.
    listede_goster = Column(Boolean, nullable=False, default=True)
    #: Birden çok bilet alınırken her katılımcının adı istensin mi.
    katilimci_adlari = Column(Boolean, nullable=False, default=False)
    #: gizli | istege_bagli | zorunlu
    telefon = Column(String(14), nullable=False, default="istege_bagli")
    #: JSON: en çok 5 özel soru (randevu soru biçimi).
    sorular = Column(Text, nullable=True)
    bekleme_listesi = Column(Boolean, nullable=False, default=True)
    #: Başlangıca bu kadar saat kala katılımcı kendisi iptal edemez.
    iptal_sinir_saat = Column(Integer, nullable=False, default=24)
    #: Kişisel alanlar etkinlik bitişinden bu kadar gün sonra anonimleşir.
    saklama_gun = Column(Integer, nullable=False, default=365)
    gorevli_surumu = Column(Integer, nullable=False, default=1)
    #: Etkinlik sonrası "teşekkür + anket" e-postası (zamanlı uç).
    tesekkur_aktif = Column(Boolean, nullable=False, default=False)
    tesekkur_metni = Column(Text, nullable=True)
    anket_url = Column(String(500), nullable=True)
    tesekkur_at = Column(DateTime(timezone=True), nullable=True)
    #: Kayıt kilidi sayacı.
    kilit = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EtkinlikBiletTurleri(Base):
    __tablename__ = "etkinlik_bilet_turleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    etkinlik_id = Column(Integer, index=True, nullable=False)
    ad = Column(String(120), nullable=False)
    aciklama = Column(String(500), nullable=True)
    #: Kuruş (0 = ücretsiz).
    fiyat = Column(Integer, nullable=False, default=0)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    #: NULL = etkinlik kapasitesi kadar.
    kontenjan = Column(Integer, nullable=True)
    satis_bas = Column(DateTime(timezone=True), nullable=True)
    satis_bit = Column(DateTime(timezone=True), nullable=True)
    kisi_basi_en_cok = Column(Integer, nullable=False, default=10)
    gizli = Column(Boolean, nullable=False, default=False)
    gizli_kod = Column(String(40), nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    sira = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EtkinlikIndirimKodlari(Base):
    __tablename__ = "etkinlik_indirim_kodlari"
    __table_args__ = (
        UniqueConstraint("etkinlik_id", "kod", name="uq_etkinlik_indirim_kod"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    etkinlik_id = Column(Integer, index=True, nullable=False)
    kod = Column(String(40), nullable=False)
    #: yuzde | tutar
    tur = Column(String(8), nullable=False, default="yuzde")
    #: Yüzde (1–100) ya da kuruş.
    deger = Column(Integer, nullable=False, default=0)
    kullanim_siniri = Column(Integer, nullable=True)
    kullanilan = Column(Integer, nullable=False, default=0)
    #: JSON: geçerli olduğu bilet türü kimlikleri; boş = hepsi.
    bilet_turleri = Column(Text, nullable=True)
    son_tarih = Column(DateTime(timezone=True), nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EtkinlikSiparisleri(Base):
    __tablename__ = "etkinlik_siparisleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    etkinlik_id = Column(Integer, index=True, nullable=False)
    #: Etkinliğin sahibi (kopya: müşteri izolasyonu sorguları için).
    hesap_email = Column(String(254), index=True, nullable=True)
    kod = Column(String(12), unique=True, index=True, nullable=False)
    ad = Column(String(120), nullable=True)
    eposta = Column(String(254), index=True, nullable=True)
    telefon = Column(String(24), nullable=True)
    yanitlar = Column(Text, nullable=True)
    dil = Column(String(2), nullable=False, default="tr")
    #: onayli | odeme_bekliyor | iptal | suresi_doldu | iade_gerekli
    durum = Column(String(16), nullable=False, default="onayli", index=True)
    #: form | panel | davet
    kaynak = Column(String(10), nullable=False, default="form")
    ara_toplam = Column(Integer, nullable=False, default=0)
    indirim = Column(Integer, nullable=False, default=0)
    toplam = Column(Integer, nullable=False, default=0)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    indirim_kodu_id = Column(Integer, nullable=True)
    #: `payments.jeton` (ücretli ajans kaydı).
    odeme_jeton = Column(String(40), index=True, nullable=True)
    odeme_son = Column(DateTime(timezone=True), nullable=True)
    odendi_at = Column(DateTime(timezone=True), nullable=True)
    pazarlama_izni_at = Column(DateTime(timezone=True), nullable=True)
    pazarlama_metin_surumu = Column(String(40), nullable=True)
    aydinlatma_at = Column(DateTime(timezone=True), nullable=True)
    crm_aday_id = Column(Integer, nullable=True)
    bekleme_id = Column(Integer, nullable=True)
    tesekkur_at = Column(DateTime(timezone=True), nullable=True)
    anonim = Column(Boolean, nullable=False, default=False)
    iptal_at = Column(DateTime(timezone=True), nullable=True)
    #: katilimci | sahip | sistem
    iptal_eden = Column(String(10), nullable=True)
    iptal_nedeni = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EtkinlikBiletleri(Base):
    __tablename__ = "etkinlik_biletleri"
    __table_args__ = (
        UniqueConstraint("etkinlik_id", "koltuk", name="uq_etkinlik_bilet_koltuk"),
        UniqueConstraint("tur_id", "tur_koltuk", name="uq_etkinlik_bilet_tur_koltuk"),
        Index("ix_etkinlik_biletleri_etkinlik_durum", "etkinlik_id", "durum"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    etkinlik_id = Column(Integer, nullable=False)
    siparis_id = Column(Integer, index=True, nullable=False)
    tur_id = Column(Integer, index=True, nullable=False)
    kod = Column(String(16), unique=True, index=True, nullable=False)
    katilimci_ad = Column(String(120), nullable=True)
    #: gecerli | odeme_bekliyor | iptal
    durum = Column(String(16), nullable=False, default="gecerli")
    #: Kapasite koltuğu (0..kapasite-1); sınırsızsa NULL; iptalde NULL.
    koltuk = Column(Integer, nullable=True)
    #: Tür kontenjanı koltuğu; kontenjansızsa NULL; iptalde NULL.
    tur_koltuk = Column(Integer, nullable=True)
    #: Kuruş (indirim öncesi birim fiyat).
    fiyat = Column(Integer, nullable=False, default=0)
    giris_at = Column(DateTime(timezone=True), nullable=True)
    giris_yapan = Column(String(254), nullable=True)
    iptal_at = Column(DateTime(timezone=True), nullable=True)
    iptal_eden = Column(String(10), nullable=True)
    #: yok | bekliyor | yapildi
    iade = Column(String(10), nullable=False, default="yok")
    #: ICS SEQUENCE.
    sira_no = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EtkinlikBekleme(Base):
    __tablename__ = "etkinlik_bekleme"
    __table_args__ = (
        Index("ix_etkinlik_bekleme_etkinlik_durum", "etkinlik_id", "durum"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    etkinlik_id = Column(Integer, nullable=False)
    tur_id = Column(Integer, nullable=True)
    ad = Column(String(120), nullable=True)
    eposta = Column(String(254), nullable=True)
    telefon = Column(String(24), nullable=True)
    adet = Column(Integer, nullable=False, default=1)
    dil = Column(String(2), nullable=False, default="tr")
    #: bekliyor | davet | kullanildi | suresi_doldu | iptal
    durum = Column(String(14), nullable=False, default="bekliyor")
    davet_at = Column(DateTime(timezone=True), nullable=True)
    davet_son = Column(DateTime(timezone=True), nullable=True)
    siparis_id = Column(Integer, nullable=True)
    pazarlama_izni_at = Column(DateTime(timezone=True), nullable=True)
    pazarlama_metin_surumu = Column(String(40), nullable=True)
    anonim = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EtkinlikOkutmalar(Base):
    __tablename__ = "etkinlik_okutmalar"
    __table_args__ = (
        Index("ix_etkinlik_okutmalar_etkinlik_zaman", "etkinlik_id", "zaman"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    etkinlik_id = Column(Integer, nullable=False)
    bilet_id = Column(Integer, nullable=True)
    #: gecerli | zaten_girdi | gecersiz | iptal | farkli_etkinlik | odeme_bekliyor | etkinlik_iptal
    sonuc = Column(String(16), nullable=False)
    #: panel | gorevli
    kaynak = Column(String(8), nullable=False, default="panel")
    yapan = Column(String(254), nullable=True)
    cevrimdisi = Column(Boolean, nullable=False, default=False)
    istemci_zaman = Column(DateTime(timezone=True), nullable=True)
    zaman = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EtkinlikGorselleri(Base):
    __tablename__ = "etkinlik_gorselleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    etkinlik_id = Column(Integer, index=True, nullable=False)
    anahtar = Column(String(64), unique=True, index=True, nullable=False)
    depo = Column(String(20), nullable=False, default="db")
    genislik = Column(Integer, nullable=True)
    yukseklik = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EtkinlikListeleri(Base):
    __tablename__ = "etkinlik_listeleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: "@ajans" ya da hesap e-postası.
    kapsam = Column(String(254), unique=True, index=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=True)
    slug = Column(String(60), unique=True, index=True, nullable=False)
    baslik = Column(String(160), nullable=False)
    aciklama = Column(Text, nullable=True)
    acik = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)
