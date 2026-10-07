"""Faz 6K — Eğitim modülü: kurs/okul + LMS (ders, öğrenci, yoklama, quiz/ödev, sertifika).

Tablolar
--------
* `egitim_kurslari` — kurs / sınıf / atölye. Herkese açık sayfa `/egitim/<slug>`. `hesap_email`
  BOŞ (NULL) ise ajansın kendi kursu; doluysa müşterinin. Ücretli tahsilat YOK (fiyat yalnız metin:
  "aylık 1.500 TL — havale / kapıda"). `egitmenler` JSON: [{"ad", "eposta"}] — `egitim_egitmen`
  izinli ekip üyesi yalnız e-postası burada geçen kursları görür. `kilit`: kayıt sırasında satır
  kilidi sayacı (etkinlik deseni). Tamamlama koşulları (`kosul_*`, yüzde) sertifika için.
* `egitim_oturumlari` — ders saatleri (program). Tekrarlayan program panelde tek seferde üretilir
  (haftanın günleri × saat × tarih aralığı). `yoklama_surumu` artınca oturumun QR bağlantısı ve
  kısa kodu değişir (eskisi geçersiz).
* `egitim_ogrencileri` — kursa kayıt (öğrenci kurs başına bir satır). `kod`: öğrenci kodu (QR'da yalnız
  kod + HMAC imzası; kişisel veri yok). `koltuk`: kapasite koltuğu — `(kurs_id, koltuk)` benzersiz,
  ayrılan / bekleyen öğrencide NULL (etkinlikteki aşırı satış koruması). 18 yaş altı (`cocuk`) için
  veli adı/telefonu/e-postası; doğum tarihi, kimlik no, adres TUTULMAZ (en az veri). Çocuğa pazarlama
  izni sorulmaz. `portal_surumu` artınca öğrenci bağlantısı geçersiz olur. Kişisel alanlar kursun
  bitişinden `saklama_gun` sonra anonimleşir (`anonim`).
* `egitim_dersleri` — LMS dersleri (bölüm + sıra): metin (güvenli Markdown), video BAĞLANTISI
  (YouTube/Vimeo — sitenin CSP'si gömmeye izin vermiyor; yeni sekmede açılıyor), dosya ekleri.
* `egitim_dosyalari` — ders ekleri ve ödev teslim dosyaları (içerik `services/dosya_deposu`: R2 ya da
  veritabanı; tür içerikten doğrulanır — `services/dosyalar.turu_dogrula`).
* `egitim_ilerleme` — öğrenci × ders "tamamlandı" işareti.
* `egitim_yoklama` — oturum × öğrenci: var / geç / yok / izinli; kaynak qr | kod | okutma | elle.
  `(oturum_id, ogrenci_id)` benzersiz: çift okutma ikinci satır açmaz ("zaten işaretli").
* `egitim_quizleri` — quiz (çoktan seçmeli / doğru-yanlış / kısa cevap; otomatik puan) ya da ödev
  (dosya + metin teslimi, eğitmen notu). `sorular` JSON; `dogru` alanları öğrenciye GİTMEZ.
* `egitim_denemeleri` — quiz denemesi: başlangıç sunucuda yazılır, süre sınırı sunucuda denetlenir.
* `egitim_teslimleri` — ödev teslimi (öğrenci × ödev tek satır; notlanana kadar yeniden teslim).
* `egitim_sertifikalari` — verilen sertifika: benzersiz `kod` (doğrulama `/egitim/sertifika/<kod>`),
  doğrulama sayfası için yalnız maskeli ad ("Ayşe Y."), kurs adı ve tarih kopyası.
* `egitim_duyurulari` — kursa gönderilen bilgilendirme duyuruları (portalda da görünür).
* `egitim_ayarlari` — hesap düzeyi: kurum adı, sertifika imzası, herkese açık kurs listesi.
  `kapsam`: ajans için `@ajans`, müşteride hesap e-postası.
* `egitim_ai_kullanimi` — "AI ile soru üret" aylık sayacı (hesap × ay; kredi ile aşım tutarı).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class EgitimKurslari(Base):
    __tablename__ = "egitim_kurslari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Sahip müşteri hesabı; NULL = ajansın kendi kursu.
    hesap_email = Column(String(254), index=True, nullable=True)
    olusturan_email = Column(String(254), nullable=True)
    slug = Column(String(60), unique=True, index=True, nullable=False)
    ad = Column(String(160), nullable=False)
    ozet = Column(String(300), nullable=True)
    #: Güvenli Markdown (HTML çizilmez).
    aciklama = Column(Text, nullable=True)
    renk = Column(String(7), nullable=False, default="#2563eb")
    #: JSON: [{"ad", "eposta"}] — en çok 10.
    egitmenler = Column(Text, nullable=True)
    #: yuz_yuze | online | karma
    bicim = Column(String(10), nullable=False, default="yuz_yuze")
    mekan = Column(String(160), nullable=True)
    adres = Column(Text, nullable=True)
    #: YALNIZ aktif öğrencilere (portal + hatırlatma e-postası).
    online_baglanti = Column(String(500), nullable=True)
    saat_dilimi = Column(String(64), nullable=False, default="Europe/Istanbul")
    baslangic_tarihi = Column(Date, nullable=True)
    bitis_tarihi = Column(Date, nullable=True)
    #: NULL = sınırsız.
    kapasite = Column(Integer, nullable=True)
    #: Yalnız metin ("Aylık 1.500 TL — havale / kapıda"); tahsilat yok.
    fiyat_metni = Column(String(300), nullable=True)
    #: taslak | yayinda | tamamlandi | arsiv
    durum = Column(String(12), nullable=False, default="taslak", index=True)
    kayit_acik = Column(Boolean, nullable=False, default=True)
    bekleme_listesi = Column(Boolean, nullable=False, default=True)
    #: yetiskin | cocuk | karma — çocuk/karma kursta veli bilgisi istenir.
    hedef_kitle = Column(String(10), nullable=False, default="yetiskin")
    #: gizli | istege_bagli | zorunlu
    telefon = Column(String(14), nullable=False, default="istege_bagli")
    dil = Column(String(2), nullable=False, default="tr")
    #: Ek aydınlatma metni (KVKK); boşsa varsayılan satır + /gizlilik.
    kvkk_metni = Column(Text, nullable=True)
    arama_motoru = Column(Boolean, nullable=False, default=False)
    listede_goster = Column(Boolean, nullable=False, default=True)
    #: Bu kadar devamsızlıkta öğrenciye/veliye bilgilendirme + `egitim.devamsizlik` (0 = kapalı).
    devamsizlik_esik = Column(Integer, nullable=False, default=3)
    #: Ders başlamadan bu kadar saat önce hatırlatma e-postası (0 = kapalı).
    hatirlatma_saat = Column(Integer, nullable=False, default=0)
    sertifika_aktif = Column(Boolean, nullable=False, default=True)
    #: Kurs bitince koşulları sağlayana sertifika kendiliğinden (zamanlı iş).
    otomatik_sertifika = Column(Boolean, nullable=False, default=False)
    kosul_ilerleme = Column(Integer, nullable=False, default=80)
    kosul_quiz = Column(Integer, nullable=False, default=60)
    kosul_yoklama = Column(Integer, nullable=False, default=70)
    #: klasik | modern
    sertifika_sablon = Column(String(10), nullable=False, default="klasik")
    #: Sertifikada gösterilen toplam ders saati (isteğe bağlı).
    sertifika_saat = Column(Integer, nullable=True)
    #: Kişisel alanlar kurs bitişinden bu kadar gün sonra anonimleşir.
    saklama_gun = Column(Integer, nullable=False, default=365)
    kilit = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EgitimOturumlari(Base):
    __tablename__ = "egitim_oturumlari"
    __table_args__ = (
        Index("ix_egitim_oturumlari_kurs_bas", "kurs_id", "baslangic"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kurs_id = Column(Integer, nullable=False)
    baslangic = Column(DateTime(timezone=True), nullable=False)
    bitis = Column(DateTime(timezone=True), nullable=False)
    konu = Column(String(160), nullable=True)
    #: planli | iptal
    durum = Column(String(8), nullable=False, default="planli")
    yoklama_surumu = Column(Integer, nullable=False, default=1)
    hatirlatma_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EgitimOgrencileri(Base):
    __tablename__ = "egitim_ogrencileri"
    __table_args__ = (
        UniqueConstraint("kurs_id", "koltuk", name="uq_egitim_ogrenci_koltuk"),
        Index("ix_egitim_ogrencileri_kurs_durum", "kurs_id", "durum"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kurs_id = Column(Integer, nullable=False)
    #: Kursun sahibi (kopya: müşteri izolasyonu ve sınır sayımı).
    hesap_email = Column(String(254), index=True, nullable=True)
    kod = Column(String(10), unique=True, index=True, nullable=False)
    ad = Column(String(120), nullable=True)
    eposta = Column(String(254), index=True, nullable=True)
    telefon = Column(String(24), nullable=True)
    #: 18 yaş altı → veli bilgisi zorunlu, pazarlama izni yok.
    cocuk = Column(Boolean, nullable=False, default=False)
    veli_ad = Column(String(120), nullable=True)
    veli_telefon = Column(String(24), nullable=True)
    veli_eposta = Column(String(254), nullable=True)
    #: aktif | bekleme | ayrildi
    durum = Column(String(8), nullable=False, default="aktif")
    #: form | elle | csv
    kaynak = Column(String(6), nullable=False, default="form")
    koltuk = Column(Integer, nullable=True)
    notlar = Column(String(1000), nullable=True)
    dil = Column(String(2), nullable=False, default="tr")
    aydinlatma_at = Column(DateTime(timezone=True), nullable=True)
    pazarlama_izni_at = Column(DateTime(timezone=True), nullable=True)
    pazarlama_metin_surumu = Column(String(40), nullable=True)
    portal_surumu = Column(Integer, nullable=False, default=1)
    portal_son_at = Column(DateTime(timezone=True), nullable=True)
    devamsizlik_sayisi = Column(Integer, nullable=False, default=0)
    devamsizlik_uyari_at = Column(DateTime(timezone=True), nullable=True)
    tamamlandi_at = Column(DateTime(timezone=True), nullable=True)
    ayrilma_at = Column(DateTime(timezone=True), nullable=True)
    anonim = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EgitimDersleri(Base):
    __tablename__ = "egitim_dersleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kurs_id = Column(Integer, index=True, nullable=False)
    #: Modül / bölüm adı ("1. Hafta", "Temeller"); aynı bölümdeki dersler birlikte listelenir.
    bolum = Column(String(120), nullable=True)
    sira = Column(Integer, nullable=False, default=0)
    baslik = Column(String(160), nullable=False)
    icerik = Column(Text, nullable=True)
    video_url = Column(String(500), nullable=True)
    sure_dk = Column(Integer, nullable=True)
    yayinda = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EgitimDosyalari(Base):
    __tablename__ = "egitim_dosyalari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kurs_id = Column(Integer, index=True, nullable=False)
    ders_id = Column(Integer, index=True, nullable=True)
    teslim_id = Column(Integer, index=True, nullable=True)
    ad = Column(String(120), nullable=False)
    tur = Column(String(120), nullable=False)
    boyut = Column(Integer, nullable=False, default=0)
    depo = Column(String(20), nullable=False, default="db")
    anahtar = Column(String(80), unique=True, index=True, nullable=False)
    yukleyen = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EgitimIlerleme(Base):
    __tablename__ = "egitim_ilerleme"
    __table_args__ = (
        UniqueConstraint("ogrenci_id", "ders_id", name="uq_egitim_ilerleme"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kurs_id = Column(Integer, index=True, nullable=False)
    ogrenci_id = Column(Integer, index=True, nullable=False)
    ders_id = Column(Integer, nullable=False)
    tamamlandi_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EgitimYoklama(Base):
    __tablename__ = "egitim_yoklama"
    __table_args__ = (
        UniqueConstraint("oturum_id", "ogrenci_id", name="uq_egitim_yoklama"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kurs_id = Column(Integer, index=True, nullable=False)
    oturum_id = Column(Integer, index=True, nullable=False)
    ogrenci_id = Column(Integer, index=True, nullable=False)
    #: var | gec | yok | izinli
    durum = Column(String(8), nullable=False, default="var")
    #: qr | kod | okutma | elle
    kaynak = Column(String(8), nullable=False, default="elle")
    zaman = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    yapan = Column(String(254), nullable=True)


class EgitimQuizleri(Base):
    __tablename__ = "egitim_quizleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kurs_id = Column(Integer, index=True, nullable=False)
    ders_id = Column(Integer, nullable=True)
    #: quiz | odev
    tur = Column(String(6), nullable=False, default="quiz")
    baslik = Column(String(160), nullable=False)
    aciklama = Column(Text, nullable=True)
    #: JSON: [{"id", "tur": coktan|dogru_yanlis|kisa, "metin", "secenekler", "dogru", "puan"}]
    sorular = Column(Text, nullable=True)
    #: Dakika; NULL = süresiz.
    sure_dk = Column(Integer, nullable=True)
    gecme_puani = Column(Integer, nullable=False, default=60)
    deneme_hakki = Column(Integer, nullable=False, default=1)
    son_tarih = Column(DateTime(timezone=True), nullable=True)
    yayinda = Column(Boolean, nullable=False, default=False)
    sira = Column(Integer, nullable=False, default=0)
    ai_uretildi = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EgitimDenemeleri(Base):
    __tablename__ = "egitim_denemeleri"
    __table_args__ = (
        Index("ix_egitim_denemeleri_quiz_ogrenci", "quiz_id", "ogrenci_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kurs_id = Column(Integer, index=True, nullable=False)
    quiz_id = Column(Integer, nullable=False)
    ogrenci_id = Column(Integer, nullable=False)
    baslangic_at = Column(DateTime(timezone=True), nullable=False)
    #: Süre sınırı (sunucu saati); NULL = süresiz.
    son_at = Column(DateTime(timezone=True), nullable=True)
    gonderim_at = Column(DateTime(timezone=True), nullable=True)
    yanitlar = Column(Text, nullable=True)
    puan = Column(Integer, nullable=True)
    dogru = Column(Integer, nullable=False, default=0)
    toplam = Column(Integer, nullable=False, default=0)
    #: devam | tamamlandi | suresi_doldu
    durum = Column(String(14), nullable=False, default="devam")


class EgitimTeslimleri(Base):
    __tablename__ = "egitim_teslimleri"
    __table_args__ = (
        UniqueConstraint("quiz_id", "ogrenci_id", name="uq_egitim_teslim"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kurs_id = Column(Integer, index=True, nullable=False)
    quiz_id = Column(Integer, nullable=False)
    ogrenci_id = Column(Integer, index=True, nullable=False)
    metin = Column(Text, nullable=True)
    teslim_at = Column(DateTime(timezone=True), nullable=False)
    puan = Column(Integer, nullable=True)
    geri_bildirim = Column(Text, nullable=True)
    notlandi_at = Column(DateTime(timezone=True), nullable=True)
    notlayan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EgitimSertifikalari(Base):
    __tablename__ = "egitim_sertifikalari"
    __table_args__ = (
        UniqueConstraint("kurs_id", "ogrenci_id", name="uq_egitim_sertifika"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kurs_id = Column(Integer, index=True, nullable=False)
    ogrenci_id = Column(Integer, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=True)
    kod = Column(String(16), unique=True, index=True, nullable=False)
    #: Doğrulama sayfasında görünen tek kişisel bilgi ("Ayşe Y.").
    ad_maskeli = Column(String(80), nullable=True)
    kurs_adi = Column(String(160), nullable=False)
    kurum_adi = Column(String(160), nullable=True)
    verilme_at = Column(DateTime(timezone=True), nullable=False)
    iptal_at = Column(DateTime(timezone=True), nullable=True)
    #: elle | toplu | otomatik
    kaynak = Column(String(8), nullable=False, default="elle")
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EgitimDuyurulari(Base):
    __tablename__ = "egitim_duyurulari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kurs_id = Column(Integer, index=True, nullable=False)
    konu = Column(String(150), nullable=False)
    metin = Column(Text, nullable=False)
    alici = Column(Integer, nullable=False, default=0)
    gonderen = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EgitimAyarlari(Base):
    __tablename__ = "egitim_ayarlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: "@ajans" ya da hesap e-postası.
    kapsam = Column(String(254), unique=True, index=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=True)
    kurum_adi = Column(String(160), nullable=True)
    imza_adi = Column(String(120), nullable=True)
    imza_unvan = Column(String(120), nullable=True)
    liste_slug = Column(String(60), unique=True, index=True, nullable=True)
    liste_baslik = Column(String(160), nullable=True)
    liste_aciklama = Column(Text, nullable=True)
    liste_acik = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EgitimAiKullanimi(Base):
    __tablename__ = "egitim_ai_kullanimi"
    __table_args__ = (
        UniqueConstraint("hesap", "ay", name="uq_egitim_ai_kullanimi"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Hesap e-postası; ajans için boş metin.
    hesap = Column(String(254), nullable=False, default="")
    #: "2026-10"
    ay = Column(String(7), nullable=False)
    sayi = Column(Integer, nullable=False, default=0)
    kredi = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
