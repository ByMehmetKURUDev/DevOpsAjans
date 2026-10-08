"""Faz 6T — toplantılar (ajans ↔ müşteri / CRM adayı): planlama, davet, katılım yanıtı, tutanak, takvim aboneliği.

Zaman: `baslangic` HER ZAMAN UTC saklanır; panel Europe/Istanbul gösterir (tarayıcının saat dilimi farklıysa ikisi).
ICS: `uid` kalıcı (davet, güncelleme ve iptal aynı takvim kaydını hedefler), `sira_no` = SEQUENCE (saat / süre / yer
değişince ve ertelemede +1; iptalde +1).

Jetonlar (katılım yanıtı, takvim aboneliği): ham jeton YALNIZ üretildiği anda (e-postada / bir kez panelde) görünür;
veritabanında sha256 özeti (`services/imzali_islem.py` deseni). Denetim kaydı `*jeton*` adlı alanları maskeler.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


#: planlandi → (ertelendi →) yapildi | iptal. "ertelendi" yeni tarihli, hâlâ yaklaşan toplantıdır.
DURUMLAR = ("planlandi", "yapildi", "ertelendi", "iptal")
YER_TURLERI = ("cevrimici", "yuz_yuze", "telefon")
KATILIMCI_TURLERI = ("ekip", "dis")
YANITLAR = ("bekliyor", "katilacak", "katilamayacak", "belki")
AKSIYON_DURUMLARI = ("acik", "tamamlandi")
SORUMLU_TURLERI = ("ekip", "musteri")
TALEP_DURUMLARI = ("bekliyor", "planlandi", "kapandi")


class Toplantilar(Base):
    __tablename__ = "toplantilar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: ICS UID'nin yerel kısmı (rastgele; tahmin edilmesi bir şey kazandırmaz ama kimlik sızdırmasın).
    uid = Column(String(64), nullable=False, unique=True, index=True)
    baslik = Column(String, nullable=False)
    #: JSON listesi (sıralı gündem maddeleri).
    gundem = Column(Text, nullable=True)
    #: UTC.
    baslangic = Column(DateTime(timezone=True), nullable=False, index=True)
    sure_dk = Column(Integer, nullable=False, default=60)
    yer_turu = Column(String, nullable=False, default="cevrimici")
    #: Çevrim içi toplantı bağlantısı (elle ya da "Jitsi bağlantısı üret").
    baglanti = Column(String, nullable=True)
    #: Yüz yüze: adres. Telefon: aranacak numara / katılım bilgisi.
    adres = Column(String, nullable=True)
    telefon = Column(String, nullable=True)
    #: Müşteri hesabı (sahibinin e-postası, küçük harf); boş = ajans içi / yalnız CRM adayı.
    hesap_email = Column(String, nullable=True, index=True)
    #: Seçilen proje müşteriye ait olmalı (sunucu doğrular).
    proje_id = Column(Integer, nullable=True, index=True)
    crm_aday_id = Column(Integer, nullable=True, index=True)
    #: Müşterinin "Toplantı iste" talebinden planlandıysa.
    talep_id = Column(Integer, nullable=True, index=True)
    durum = Column(String, nullable=False, default="planlandi", index=True)
    iptal_nedeni = Column(Text, nullable=True)
    #: ICS SEQUENCE.
    sira_no = Column(Integer, nullable=False, default=0)
    davet_gonderildi_at = Column(DateTime(timezone=True), nullable=True)
    #: Davetten sonra saat/yer değişti, güncelleme daveti henüz gitmedi.
    guncelleme_bekliyor = Column(Boolean, nullable=False, default=False)
    #: Tutanak: notlar (markdown → `services/guvenli_html.py` ile güvenli HTML), kararlar (JSON listesi).
    notlar = Column(Text, nullable=True)
    kararlar = Column(Text, nullable=True)
    notlar_paylasildi = Column(Boolean, nullable=False, default=False)
    paylasildi_at = Column(DateTime(timezone=True), nullable=True)
    yapildi_at = Column(DateTime(timezone=True), nullable=True)
    iptal_at = Column(DateTime(timezone=True), nullable=True)
    olusturan_eposta = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class ToplantiKatilimcilari(Base):
    """Ekip üyesi (`staff`) ya da dış e-posta (müşteri hesabının kişileri, aday, başka biri)."""

    __tablename__ = "toplanti_katilimcilari"
    __table_args__ = (
        UniqueConstraint("toplanti_id", "eposta", name="uq_toplanti_katilimcilari_eposta"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    toplanti_id = Column(Integer, nullable=False, index=True)
    tur = Column(String, nullable=False, default="dis")
    eposta = Column(String, nullable=False, index=True)
    ad = Column(String, nullable=True)
    yanit = Column(String, nullable=False, default="bekliyor")
    yanit_notu = Column(String, nullable=True)
    yanit_at = Column(DateTime(timezone=True), nullable=True)
    #: baglanti (girişsiz imzalı bağlantı) | panel (müşteri paneli)
    yanit_kaynagi = Column(String, nullable=True)
    #: sha256(ham yanıt jetonu). Her davette yenilenir (eski e-postadaki bağlantı geçersizleşir).
    yanit_jeton_ozeti = Column(String(64), nullable=True, unique=True, index=True)
    davet_at = Column(DateTime(timezone=True), nullable=True)
    #: Hatırlatmalar (her biri bir kez; erteleme sıfırlar).
    hatirlatma_24_at = Column(DateTime(timezone=True), nullable=True)
    hatirlatma_1_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class ToplantiAksiyonlari(Base):
    """Tutanağın aksiyon maddesi. "Göreve dönüştür" proje görevi açar (`gorev_id`, tek sefer)."""

    __tablename__ = "toplanti_aksiyonlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    toplanti_id = Column(Integer, nullable=False, index=True)
    metin = Column(String, nullable=False)
    #: ekip (sorumlu_eposta = staff.email) | musteri (sorumlu_eposta = hesaptaki kişi; boş = hesabın kendisi)
    sorumlu_tur = Column(String, nullable=False, default="ekip")
    sorumlu_eposta = Column(String, nullable=True, index=True)
    son_tarih = Column(Date, nullable=True)
    durum = Column(String, nullable=False, default="acik")
    tamamlandi_at = Column(DateTime(timezone=True), nullable=True)
    tamamlayan_eposta = Column(String, nullable=True)
    gorev_id = Column(Integer, nullable=True, unique=True)
    sira = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class ToplantiTalepleri(Base):
    """Müşterinin "Toplantı iste" talebi → Gelen kutusu `toplanti_talebi`; planlanınca kapanır."""

    __tablename__ = "toplanti_talepleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String, nullable=False, index=True)
    #: İsteyen kişi (ekip üyesi olabilir).
    kisi_email = Column(String, nullable=False)
    konu = Column(String, nullable=False)
    #: JSON: [{"bas": ISO UTC, "bit": ISO UTC}] (en çok 3).
    araliklar = Column(Text, nullable=True)
    notlar = Column(Text, nullable=True)
    durum = Column(String, nullable=False, default="bekliyor", index=True)
    toplanti_id = Column(Integer, nullable=True)
    kapandi_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)


class ToplantiTakvimAbonelikleri(Base):
    """Kişinin gizli ICS akışı (`/api/v1/toplanti-takvimi/<jeton>.ics`): yalnız o kişinin toplantıları.

    Kişi başına tek satır; yeniden üretmek özeti değiştirir (eski adres 404), iptal satırı siler.
    """

    __tablename__ = "toplanti_takvim_abonelikleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kisi_email = Column(String, nullable=False, unique=True, index=True)
    #: ekip | musteri | yonetici
    tur = Column(String, nullable=False, default="musteri")
    jeton_ozeti = Column(String(64), nullable=False, unique=True, index=True)
    olusturan_eposta = Column(String, nullable=True)
    son_erisim_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
