"""Faz 2C — Dosyalar, klasör yetkisi, paylaşım bağlantısı ve belge talebi.

Neden beş tablo?
----------------
* `files` yalnız dosyanın kimliği (sahip müşteri, klasör, ad, boyut, tür,
  depolama anahtarı, sürüm). İçerik burada DEĞİL: nereye yazıldığını
  `services/dosya_deposu.py` biliyor (S3 uyumlu nesne deposu ya da
  veritabanındaki `dosya_icerikleri`).
* `dosya_klasorleri` klasör yetkisi: müşteri görür / yalnız ekip. Yetki
  dosyada değil klasörde, çünkü "bu klasördeki her şey iç yazışma" demek
  dosya dosya işaretlemekten daha az hata üretiyor.
* `dosya_icerikleri` Render'ın ücretsiz planında kalıcı disk olmadığı için:
  nesne deposu tanımlı değilken içerik Postgres'te duruyor (kalıcı).
* `paylasim_baglantilari` girişsiz, süreli, isteğe bağlı parolalı ve
  indirme sayısı sınırlı bağlantı. Jeton ve parola YALNIZ özet olarak.
* `belge_talepleri` ajansın müşteriden istediği belge (son tarih, kabul
  edilen türler, teslim ve hatırlatma zamanları).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, LargeBinary, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class Dosyalar(Base):
    __tablename__ = "files"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Sahip müşteri (küçük harf). Müşteri yalnız bununla eşleşen dosyaları görür.
    client_email = Column(String, index=True, nullable=False)
    proje_id = Column(Integer, index=True, nullable=True)
    klasor = Column(String, index=True, nullable=False, default="Genel")
    #: Temizlenmiş görünen ad (yol ayırıcısı, denetim karakteri yok).
    ad = Column(String, nullable=False)
    boyut = Column(Integer, nullable=False, default=0)
    #: Sunucuda içerikten doğrulanmış MIME türü (istemcinin söylediği değil).
    tur = Column(String, nullable=False)
    uzanti = Column(String, nullable=False)
    #: Depodaki anahtar (rastgele; dosya adından türemez → tahmin edilemez).
    depolama_anahtari = Column(String, unique=True, index=True, nullable=False)
    #: Hangi depoda: s3 | veritabani (depo sonradan değişirse eski dosyalar okunabilsin).
    depo = Column(String, nullable=False, default="veritabani")
    yukleyen = Column(String, nullable=True)
    #: admin | client
    yukleyen_rol = Column(String, nullable=True)
    #: Aynı müşteri + klasör + ad ikinci kez yüklenince sürüm artıyor; eski
    #: sürüm silinmiyor, `guncel=False` oluyor.
    surum = Column(Integer, nullable=False, default=1)
    guncel = Column(Boolean, nullable=False, default=True, index=True)
    belge_talebi_id = Column(Integer, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, index=True)


class DosyaKlasorleri(Base):
    __tablename__ = "dosya_klasorleri"
    __table_args__ = (
        UniqueConstraint("client_email", "ad", name="uq_dosya_klasoru"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    client_email = Column(String, index=True, nullable=False)
    ad = Column(String, nullable=False)
    #: musteri (müşteri görür) | ekip (yalnız ekip)
    gorunurluk = Column(String, nullable=False, default="musteri")
    created_at = Column(DateTime(timezone=True), default=_simdi)


class DosyaIcerikleri(Base):
    """Nesne deposu yokken dosya içeriği (Postgres BYTEA / SQLite BLOB)."""

    __tablename__ = "dosya_icerikleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    anahtar = Column(String, unique=True, index=True, nullable=False)
    veri = Column(LargeBinary, nullable=False)
    boyut = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi)


class PaylasimBaglantilari(Base):
    __tablename__ = "paylasim_baglantilari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    dosya_id = Column(Integer, index=True, nullable=False)
    #: sha256(jeton) — ham jeton yalnız üretildiği anda yöneticiye gösteriliyor.
    jeton_ozeti = Column(String, unique=True, index=True, nullable=False)
    son_kullanma = Column(DateTime(timezone=True), nullable=False)
    #: pbkdf2-sha256(parola, tuz) — parola hiç saklanmıyor.
    sifre_ozeti = Column(String, nullable=True)
    sifre_tuzu = Column(String, nullable=True)
    #: Boş = sınırsız (süre dolana kadar).
    indirme_siniri = Column(Integer, nullable=True)
    indirme_sayisi = Column(Integer, nullable=False, default=0)
    #: Yanlış parola denemesi; 10'a ulaşınca bağlantı kilitleniyor.
    hatali_deneme = Column(Integer, nullable=False, default=0)
    iptal = Column(Boolean, nullable=False, default=False)
    olusturan = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)


class BelgeTalepleri(Base):
    __tablename__ = "belge_talepleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    client_email = Column(String, index=True, nullable=False)
    proje_id = Column(Integer, nullable=True)
    baslik = Column(String, nullable=False)
    aciklama = Column(Text, nullable=True)
    #: YYYY-MM-DD (Türkiye günü). Boş olabilir: son tarihsiz talep.
    son_tarih = Column(String, nullable=True)
    #: Virgüllü uzantı listesi (pdf,jpg); boşsa genel izinli türlerin hepsi.
    kabul_turleri = Column(String, nullable=True)
    #: bekliyor | teslim_edildi | iptal
    durum = Column(String, index=True, nullable=False, default="bekliyor")
    dosya_id = Column(Integer, nullable=True)
    teslim_at = Column(DateTime(timezone=True), nullable=True)
    #: Hatırlatmalar bir kez: "yaklaşıyor" (son 2 gün) ve "geçti".
    hatirlatma_yaklasti_at = Column(DateTime(timezone=True), nullable=True)
    hatirlatma_gecti_at = Column(DateTime(timezone=True), nullable=True)
    olusturan = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)
