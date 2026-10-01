"""Faz 5R — Takvim ve randevu + toplantılar (Calendly benzeri).

Tablolar
--------
* `randevu_sayfalari` — hesabın herkese açık randevu sayfası (`/randevu/<slug>`).
  Hesap başına BİR sayfa; `hesap_email` BOŞ (NULL) ise ajansın kendi sayfası.
  Ayarlar: başlık, karşılama metni, logo, renk, saat dilimi (varsayılan
  Europe/Istanbul), dil, arama motoru (varsayılan kapalı → noindex), resmî
  tatillerde kapalı, hatırlatmalar (randevudan kaç dakika önce), iptal /
  yeniden planlama sınırı, kişisel verinin saklama süresi, ICS besleme sürümü
  (artırılınca eski abonelik adresi geçersiz olur).
* `randevu_kisileri` — sayfanın ekibi (sahip + hesap ekibinden kişiler). Her
  kişinin kendi haftalık çalışma saatleri var (`{"0": [["09:00","12:00"], …]}`,
  0 = pazartesi; gece yarısını aşan aralık `["22:00","02:00"]` izinli).
  `kilit`: rezervasyon sırasında satır kilidi için sayaç (PostgreSQL'de satır
  kilidi, SQLite'ta yazma kilidi; aynı kişiye eşzamanlı iki rezervasyon sıraya girer).
* `randevu_istisnalari` — tarih bazlı istisna: tatil/izin (boş aralık listesi
  = kapalı) ya da o güne özel saatler. `kisi_id` boşsa bütün ekip için.
* `randevu_turleri` — etkinlik türü ("30 dk tanışma görüşmesi"): süre, konum,
  tamponlar, en erken / en geç rezervasyon, günlük üst sınır, kapasite (1 =
  birebir, >1 = grup), soru formu, renk, atama (kişiye özel / sırayla / ilk müsait).
* `randevular` — rezervasyon. Zamanlar UTC. `dolu_bas`/`dolu_bit` tamponlu
  aralık (çakışma sorgusu için). `uid` kalıcı (ICS UID'si; yeniden planlamada
  değişmez, `sira_no` = ICS SEQUENCE artar). Kişisel alanlar (ad, e-posta,
  telefon, yanıtlar) saklama süresi dolunca NULL olur (`anonim`).
  **Çakışma koruması (veritabanı düzeyi):** `(kisi_id, baslangic, koltuk)`
  benzersiz. Birebirde koltuk her zaman 0; grupta 0..kapasite-1. İptal edilen
  randevunun koltuğu NULL olur (yer boşalır). Örtüşen (aynı başlangıçlı
  olmayan) randevular kişi satırı kilidiyle sıraya alınıp yeniden denetleniyor.
* `randevu_hatirlatmalari` — `(randevu_id, dakika)` benzersiz: her hatırlatma
  TEK KEZ gider (zamanlı görevin iki turu aynı satırı ekleyemez).
* `randevu_olaylari` — analitik: sayfa / tür görüntüleme ve rezervasyon. Ham IP
  ya da User-Agent YOK: gün + tuzla alınmış IP özeti ve bot işareti.
* `randevu_gorselleri` — sayfa logosu (içerik `services/dosya_deposu`; WebP).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, Date, DateTime, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class RandevuSayfalari(Base):
    __tablename__ = "randevu_sayfalari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Sahip müşteri hesabı; NULL = ajansın kendi sayfası.
    hesap_email = Column(String(254), index=True, nullable=True)
    olusturan_email = Column(String(254), nullable=True)
    slug = Column(String(60), unique=True, index=True, nullable=False)
    baslik = Column(String(120), nullable=False)
    karsilama = Column(Text, nullable=True)
    logo = Column(String(64), nullable=True)
    renk = Column(String(7), nullable=False, default="#7c3aed")
    saat_dilimi = Column(String(64), nullable=False, default="Europe/Istanbul")
    dil = Column(String(2), nullable=False, default="tr")
    #: Arama motorlarında görünsün mü (varsayılan hayır → noindex).
    arama_motoru = Column(Boolean, nullable=False, default=False)
    #: Türkiye resmî tatillerinde (destek SLA tatil listesi) kapalı.
    tatilde_kapali = Column(Boolean, nullable=False, default=True)
    #: JSON: hatırlatma dakikaları, ör. [1440, 60].
    hatirlatmalar = Column(Text, nullable=True)
    #: Başlangıca bu kadar dakika kala ziyaretçi iptal / yeniden planlama yapamaz.
    iptal_sinir_dk = Column(Integer, nullable=False, default=120)
    #: Kişisel alanlar randevudan bu kadar gün sonra anonimleşir.
    saklama_gun = Column(Integer, nullable=False, default=180)
    #: ICS besleme jetonunun sürümü (yenile → eski adres geçersiz).
    besleme_surumu = Column(Integer, nullable=False, default=1)
    aktif = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class RandevuKisileri(Base):
    __tablename__ = "randevu_kisileri"
    __table_args__ = (
        UniqueConstraint("sayfa_id", "eposta", name="uq_randevu_kisileri_sayfa_eposta"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    sayfa_id = Column(Integer, index=True, nullable=False)
    eposta = Column(String(254), nullable=False)
    ad = Column(String(120), nullable=False)
    #: JSON: haftalık çalışma saatleri.
    haftalik = Column(Text, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    sira = Column(Integer, nullable=False, default=0)
    #: Rezervasyon kilidi sayacı (bkz. modül açıklaması).
    kilit = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class RandevuIstisnalari(Base):
    __tablename__ = "randevu_istisnalari"
    __table_args__ = (
        Index("ix_randevu_istisnalari_sayfa_tarih", "sayfa_id", "tarih"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    sayfa_id = Column(Integer, index=True, nullable=False)
    #: NULL = bütün ekip.
    kisi_id = Column(Integer, index=True, nullable=True)
    tarih = Column(Date, nullable=False)
    #: JSON: o günün aralıkları; boş liste = kapalı (tatil/izin).
    araliklar = Column(Text, nullable=True)
    aciklama = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class RandevuTurleri(Base):
    __tablename__ = "randevu_turleri"
    __table_args__ = (
        UniqueConstraint("sayfa_id", "slug", name="uq_randevu_turleri_sayfa_slug"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    sayfa_id = Column(Integer, index=True, nullable=False)
    slug = Column(String(60), nullable=False)
    ad = Column(String(120), nullable=False)
    aciklama = Column(Text, nullable=True)
    sure_dk = Column(Integer, nullable=False, default=30)
    #: Başlangıç saatlerinin aralığı (dakika).
    adim_dk = Column(Integer, nullable=False, default=30)
    #: jitsi | baglanti | telefon | yuz_yuze
    konum_turu = Column(String(12), nullable=False, default="jitsi")
    #: Sabit toplantı bağlantısı / telefon / adres.
    konum_degeri = Column(String(500), nullable=True)
    tampon_once_dk = Column(Integer, nullable=False, default=0)
    tampon_sonra_dk = Column(Integer, nullable=False, default=0)
    en_erken_dk = Column(Integer, nullable=False, default=240)
    en_gec_gun = Column(Integer, nullable=False, default=60)
    gunluk_sinir = Column(Integer, nullable=True)
    kapasite = Column(Integer, nullable=False, default=1)
    #: gizli | istege_bagli | zorunlu
    telefon = Column(String(12), nullable=False, default="istege_bagli")
    #: JSON: en çok 5 özel soru.
    sorular = Column(Text, nullable=True)
    renk = Column(String(7), nullable=False, default="#7c3aed")
    #: kisi | sirali | ilk_musait
    atama = Column(String(12), nullable=False, default="kisi")
    #: JSON: atanmış kişi kimlikleri (sıra = öncelik).
    kisiler = Column(Text, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    sira = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class Randevular(Base):
    __tablename__ = "randevular"
    __table_args__ = (
        UniqueConstraint("kisi_id", "baslangic", "koltuk", name="uq_randevular_kisi_baslangic_koltuk"),
        Index("ix_randevular_kisi_dolu", "kisi_id", "dolu_bas", "dolu_bit"),
        Index("ix_randevular_sayfa_baslangic", "sayfa_id", "baslangic"),
        Index("ix_randevular_durum_baslangic", "durum", "baslangic"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Kalıcı kimlik (ICS UID); yeniden planlamada değişmez.
    uid = Column(String(32), unique=True, index=True, nullable=False)
    sayfa_id = Column(Integer, nullable=False)
    tur_id = Column(Integer, index=True, nullable=False)
    kisi_id = Column(Integer, nullable=False)
    #: Sayfanın sahibi (izolasyon için kopya); NULL = ajans.
    hesap_email = Column(String(254), index=True, nullable=True)
    baslangic = Column(DateTime(timezone=True), nullable=False)
    bitis = Column(DateTime(timezone=True), nullable=False)
    dolu_bas = Column(DateTime(timezone=True), nullable=False)
    dolu_bit = Column(DateTime(timezone=True), nullable=False)
    #: Birebirde 0; grupta 0..kapasite-1; iptalde NULL (yer boşalır).
    koltuk = Column(Integer, nullable=True)
    #: onayli | iptal
    durum = Column(String(10), nullable=False, default="onayli")
    #: bilinmiyor | geldi | gelmedi
    katilim = Column(String(12), nullable=False, default="bilinmiyor")
    #: ICS SEQUENCE.
    sira_no = Column(Integer, nullable=False, default=0)
    # --- Kişisel alanlar: saklama süresi dolunca NULL ---
    ad = Column(String(120), nullable=True)
    eposta = Column(String(254), nullable=True)
    telefon = Column(String(20), nullable=True)
    yanitlar = Column(Text, nullable=True)
    iptal_nedeni = Column(Text, nullable=True)
    anonim = Column(Boolean, nullable=False, default=False, index=True)
    # --- Diğer ---
    ziyaretci_tz = Column(String(64), nullable=True)
    dil = Column(String(2), nullable=False, default="tr")
    #: Çözülmüş konum (Jitsi odası, bağlantı, telefon, adres).
    konum = Column(String(500), nullable=True)
    #: ziyaretci | sahip
    iptal_eden = Column(String(10), nullable=True)
    iptal_at = Column(DateTime(timezone=True), nullable=True)
    onceki_baslangic = Column(DateTime(timezone=True), nullable=True)
    aydinlatma_at = Column(DateTime(timezone=True), nullable=True)
    crm_aday_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class RandevuHatirlatmalari(Base):
    __tablename__ = "randevu_hatirlatmalari"
    __table_args__ = (
        UniqueConstraint("randevu_id", "dakika", name="uq_randevu_hatirlatmalari"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    randevu_id = Column(Integer, index=True, nullable=False)
    dakika = Column(Integer, nullable=False)
    #: gonderildi | atlandi (daha yakın hatırlatma varken eskisi gönderilmez)
    durum = Column(String(12), nullable=False, default="gonderildi")
    zaman = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class RandevuOlaylari(Base):
    __tablename__ = "randevu_olaylari"
    __table_args__ = (
        Index("ix_randevu_olaylari_sayfa_gun", "sayfa_id", "gun"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    sayfa_id = Column(Integer, nullable=False)
    tur_id = Column(Integer, nullable=True)
    #: sayfa | tur | rezervasyon
    tur = Column(String(12), nullable=False)
    zaman = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    gun = Column(String(10), nullable=False)
    ip_ozeti = Column(String(64), nullable=True)
    bot = Column(Boolean, nullable=False, default=False)


class RandevuGorselleri(Base):
    __tablename__ = "randevu_gorselleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    sayfa_id = Column(Integer, index=True, nullable=False)
    anahtar = Column(String(64), unique=True, index=True, nullable=False)
    depo = Column(String(8), nullable=False)
    genislik = Column(Integer, nullable=False, default=0)
    yukseklik = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
