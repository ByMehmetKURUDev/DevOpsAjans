"""Faz 4K — Dijital kartvizit + bio link ve Google yorum sayfası.

Tablolar
--------
* `kartvizitler` — bir dijital kartvizit ya da bio link sayfası (`/kart/<slug>`).
  - `hesap_email` kayıt sahibi müşteri hesabı (küçük harf); BOŞ (NULL) ise
    ajansın kendi kartı (yönetici panelinden).
  - `kod` 7 karakter, DEĞİŞMEZ ve en az bir büyük harf içeriyor (slug'lar
    küçük harf; ikisi asla çakışmıyor). Kartın QR'ı `/kart/<kod>` taşıyor:
    slug değişse de basılı kartvizitteki QR çalışmaya devam ediyor.
  - `slug` okunaklı adres; değiştirilebilir. Eski slug 30 gün
    `kartvizit_eski_sluglar` üzerinden yeni adrese yönleniyor.
  - `icerik` (JSON) telefonlar, web siteleri, sosyal bağlantılar, bağlantı
    listesi, hizmetler, çalışma saatleri…; `ad_soyad`, `unvan`, `sirket`
    liste/arama için ayrıca sütunda.
  - `tema` (JSON) şablon, vurgu rengi, yazı tipi, köşe yuvarlaklığı.
  - `foto_id`, `logo_id`, `kapak_id` → `kartvizit_gorselleri`.
  - `sifre_ozet` / `sifre_tuz`: parola korumalı kart (pbkdf2-sha256, dosya
    paylaşımıyla aynı yardımcı). Adlarında "sifre" geçtiği için denetim
    kaydında maskeli.
  - `index_acik`: arama motorlarında görünürlük (varsayılan kapalı → noindex).
* `yorum_sayfalari` — Google yorum sayfası (`/yorum/<slug>`): işletme adı,
  logo, teşekkür metni, Place ID, isteğe bağlı özel geri bildirim formu.
  Aynı `kod` / `slug` / eski slug düzeni.
* `kartvizit_gorselleri` — profil fotoğrafı, logo, kapak ve galeri (kart) ile
  yorum sayfası logosu. İçerik `services/dosya_deposu` üzerinden (R2 ya da
  veritabanı); sunucuda Pillow ile küçültülüp WebP'ye çevrilmiş halde. `anahtar`
  herkese açık adresteki tahmin edilemez kimlik (`/api/v1/kart/gorsel/<anahtar>.webp`).
  `hesap_email` sahibin kopyası (çöp kutusu için).
* `kartvizit_eski_sluglar` — slug değişince eskisi 30 gün burada.
* `kartvizit_olaylari` — analitik: görüntülenme, rehbere kaydet, bağlantı
  tıklaması, form, paylaş (kart); görüntülenme, Google düğmesi, geri bildirim
  (yorum). Ham IP / User-Agent SAKLANMAZ: gün + tuzla alınmış IP özeti
  (tekil sayım), cihaz sınıfı, bot işareti (Faz 4Q ile aynı kural).
* `kartvizit_mesajlari` — kartın "iletişim bırak" formu ve yorum sayfasının
  özel geri bildirimleri. Ajansın kendi kartından gelen mesaj ayrıca CRM'e
  aday olarak düşüyor (`crm_aday_id`); müşteri kartlarınınki CRM'e KARIŞMIYOR
  (CRM yalnız ajansın satış hunisi), müşterinin panelinde listeleniyor.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class Kartvizitler(Base):
    __tablename__ = "kartvizitler"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Kayıt sahibi müşteri hesabı; NULL = ajansın kendi kartı.
    hesap_email = Column(String, index=True, nullable=True)
    #: Oluşturan kişi (jetondaki e-posta; ekip üyesi kendi kartını yapabilir).
    olusturan_email = Column(String, nullable=True)
    kod = Column(String(16), unique=True, index=True, nullable=False)
    slug = Column(String(60), unique=True, index=True, nullable=False)
    #: kartvizit | bio_link
    duzen = Column(String(16), nullable=False, default="kartvizit")
    dil = Column(String(5), nullable=False, default="tr")
    ad_soyad = Column(String(120), nullable=False)
    unvan = Column(String(120), nullable=True)
    sirket = Column(String(160), nullable=True)
    icerik = Column(Text, nullable=True)
    tema = Column(Text, nullable=True)
    foto_id = Column(Integer, nullable=True)
    logo_id = Column(Integer, nullable=True)
    kapak_id = Column(Integer, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True, index=True)
    form_acik = Column(Boolean, nullable=False, default=True)
    index_acik = Column(Boolean, nullable=False, default=False)
    sifre_ozet = Column(String(128), nullable=True)
    sifre_tuz = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class YorumSayfalari(Base):
    __tablename__ = "yorum_sayfalari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    olusturan_email = Column(String, nullable=True)
    kod = Column(String(16), unique=True, index=True, nullable=False)
    slug = Column(String(60), unique=True, index=True, nullable=False)
    isletme_adi = Column(String(120), nullable=False)
    place_id = Column(String(512), nullable=False)
    tesekkur = Column(Text, nullable=True)
    geri_bildirim_acik = Column(Boolean, nullable=False, default=True)
    dil = Column(String(5), nullable=False, default="tr")
    renk = Column(String(7), nullable=True)
    logo_id = Column(Integer, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class KartvizitGorselleri(Base):
    __tablename__ = "kartvizit_gorselleri"
    __table_args__ = (
        Index("ix_kartvizit_gorselleri_sahip", "sahip_tur", "sahip_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Sahibin kopyası (çöp kutusu "kimin" sorusu için); NULL = ajans.
    hesap_email = Column(String, index=True, nullable=True)
    #: kart | yorum
    sahip_tur = Column(String(8), nullable=False)
    sahip_id = Column(Integer, nullable=False)
    #: foto | logo | kapak | galeri
    tur = Column(String(12), nullable=False)
    #: Herkese açık adresteki tahmin edilemez kimlik.
    anahtar = Column(String(40), unique=True, index=True, nullable=False)
    depo = Column(String(16), nullable=False, default="veritabani")
    depolama_anahtari = Column(String(255), nullable=False)
    boyut = Column(Integer, nullable=False, default=0)
    genislik = Column(Integer, nullable=False, default=0)
    yukseklik = Column(Integer, nullable=False, default=0)
    sira = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class KartvizitEskiSluglar(Base):
    __tablename__ = "kartvizit_eski_sluglar"
    __table_args__ = (
        UniqueConstraint("sahip_tur", "slug", name="uq_kartvizit_eski_slug"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    sahip_tur = Column(String(8), nullable=False)
    sahip_id = Column(Integer, index=True, nullable=False)
    slug = Column(String(60), index=True, nullable=False)
    bitis = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class KartvizitOlaylari(Base):
    __tablename__ = "kartvizit_olaylari"
    __table_args__ = (
        Index("ix_kartvizit_olaylari_sahip_zaman", "sahip_tur", "sahip_id", "zaman"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    sahip_tur = Column(String(8), nullable=False)
    sahip_id = Column(Integer, nullable=False)
    #: goruntulenme | rehber | tik | form | paylas | google | geri_bildirim
    olay = Column(String(16), nullable=False)
    #: Tıklanan öğe (`l:<id>`, `tel:0`, `wa`, `s:linkedin`…); diğer olaylarda boş.
    hedef = Column(String(40), nullable=True)
    #: Görüntülenme kaynağı: `qr` (değişmez kodla açıldı) ya da boş.
    kanal = Column(String(8), nullable=True)
    zaman = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    #: UTC gün (YYYY-MM-DD) — günlük seri ve tekil sayım için.
    gun = Column(String(10), nullable=False)
    #: Gün + tuz ile alınmış sha256 (ham IP yok).
    ip_ozeti = Column(String(64), nullable=False)
    cihaz = Column(String(12), nullable=False, default="bilinmiyor")
    #: Bot / bağlantı önizleyici / önden yükleme: sayılara katılmaz.
    bot = Column(Boolean, nullable=False, default=False, index=True)


class KartvizitMesajlari(Base):
    __tablename__ = "kartvizit_mesajlari"
    __table_args__ = (
        Index("ix_kartvizit_mesajlari_sahip", "sahip_tur", "sahip_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: kart (iletişim bırak) | yorum (özel geri bildirim)
    sahip_tur = Column(String(8), nullable=False)
    sahip_id = Column(Integer, nullable=False)
    #: Kartın/sayfanın hesabı (listeleme süzgeci); NULL = ajans.
    hesap_email = Column(String, index=True, nullable=True)
    ad = Column(String(120), nullable=True)
    eposta = Column(String(254), nullable=True)
    telefon = Column(String(40), nullable=True)
    mesaj = Column(Text, nullable=True)
    #: Ziyaretçinin gördüğü aydınlatma satırının dili ve zamanı.
    dil = Column(String(5), nullable=True)
    aydinlatma_at = Column(DateTime(timezone=True), nullable=True)
    okundu = Column(Boolean, nullable=False, default=False, index=True)
    #: Ajans kartından gelen mesajın açtığı/güncellediği CRM adayı.
    crm_aday_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)
