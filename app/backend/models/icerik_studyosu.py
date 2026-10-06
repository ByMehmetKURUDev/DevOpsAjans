"""Faz 5I — İçerik stüdyosu: marka sesi, AI içerik şablonları ve üretim geçmişi.

Gönderilerin kendisi YENİ bir tabloda değil: mevcut `content_posts` (içerik
takvimi) genişletildi (bkz. `models/content_posts.py`). Bu dosyada stüdyonun
gönderi dışındaki kayıtları var.

Kapsam (hesap)
--------------
Her kayıt bir hesaba ait: `hesap_email` boşsa ajansın kendisi (yönetici paneli),
doluysa müşteri hesabı. Ajans bir müşteri İÇİN marka/şablon hazırlayabilir
(yönetici `hesap` seçer); kayıt o müşterinin hesabına yazılır.

Tablolar
--------
* `icerik_markalari` — marka sesi profili: sektör, hedef kitle, ton ölçekleri
  (resmî↔samimi …, 0–100), yazım kuralları (yapılacak/yapılmayacak), yasaklı
  kelimeler, en çok 5 örnek metin, anahtar mesajlar, emoji/hashtag politikası,
  diller.
* `icerik_sablonlari` — kullanıcının kendi şablonu (alanlar + istem). Hazır
  şablonlar kodda (`services/icerik_studyosu.py` › `HAZIR_SABLONLAR`).
* `icerik_uretimleri` — üretim geçmişi (girdi, varyasyonlar, uyarılar, jeton,
  kredi). İnce ayar ("daha kısa", "çevir" …) yeni satır, `kaynak_id` ile bağlı.
* `icerik_kullanimi` — hesap × gün sayaç (aylık dahil hak, günlük üst sınır,
  kredi bloğu; Faz 5A deseni).
* `icerik_gorselleri` — gönderi görselleri (dosya deposunda; tahmin edilemez
  anahtarla herkese açık adres — onay bağlantısı ve dışa aktarma için).

Liste/JSON alanları metin sütununda (SQLite ile Postgres aynı davransın).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class IcerikMarkalari(Base):
    __tablename__ = "icerik_markalari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    ad = Column(String, nullable=False)
    sektor = Column(String, nullable=True)
    hedef_kitle = Column(Text, nullable=True)
    #: JSON {resmi_samimi, ciddi_esprili, sade_teknik, sakin_enerjik} — 0 (sol uç) … 100 (sağ uç).
    ton = Column(Text, nullable=True)
    #: JSON listeler.
    yapilacaklar = Column(Text, nullable=True)
    yapilmayacaklar = Column(Text, nullable=True)
    yasakli_kelimeler = Column(Text, nullable=True)
    ornek_metinler = Column(Text, nullable=True)
    anahtar_mesajlar = Column(Text, nullable=True)
    #: yok | az | serbest
    emoji_politikasi = Column(String, nullable=False, default="az")
    hashtag_politikasi = Column(String, nullable=False, default="az")
    #: JSON liste — markanın sabit etiketleri (#markaadi).
    hashtagler = Column(Text, nullable=True)
    #: JSON liste — içerik dilleri (ilki varsayılan).
    diller = Column(Text, nullable=True)
    olusturan = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)


class IcerikSablonlari(Base):
    __tablename__ = "icerik_sablonlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    ad = Column(String, nullable=False)
    aciklama = Column(Text, nullable=True)
    #: Karakter sınırı denetimi için varsayılan kanal (boş = genel).
    kanal = Column(String, nullable=True)
    #: JSON [{anahtar, etiket, tur: metin|uzun, zorunlu}]
    alanlar = Column(Text, nullable=False, default="[]")
    #: `{{anahtar}}` yer tutuculu istem (kullanıcı girdisi VERİ olarak yerleşir).
    istem = Column(Text, nullable=False)
    olusturan = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)


class IcerikUretimleri(Base):
    __tablename__ = "icerik_uretimleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    kisi_email = Column(String, nullable=True)
    marka_id = Column(Integer, index=True, nullable=True)
    #: Hazır şablon kodu ya da "ozel:<id>"; ince ayarda kaynak üretimin şablonu.
    sablon = Column(String, nullable=False)
    kanal = Column(String, nullable=True)
    #: uret | kisalt | samimi | emoji_ekle | emoji_cikar | cevir | ses_cikar
    islem = Column(String, nullable=False, default="uret")
    kaynak_id = Column(Integer, nullable=True)
    dil = Column(String, nullable=False, default="tr")
    #: JSON — kullanıcı girdisi.
    girdi = Column(Text, nullable=True)
    #: JSON [{metin, alanlar, olcum, uyarilar}]
    varyasyonlar = Column(Text, nullable=True)
    model = Column(String, nullable=True)
    sahte = Column(Integer, nullable=False, default=0)
    token_giris = Column(Integer, nullable=False, default=0)
    token_cikis = Column(Integer, nullable=False, default=0)
    kredi = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_simdi, index=True)


class IcerikKullanimi(Base):
    __tablename__ = "icerik_kullanimi"
    __table_args__ = (
        UniqueConstraint("hesap", "gun", name="uq_icerik_kullanimi_hesap_gun"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Müşteri e-postası; ajansın kendi işi için "".
    hesap = Column(String, index=True, nullable=False, default="")
    #: UTC gün, YYYY-AA-GG
    gun = Column(String, index=True, nullable=False)
    uretim = Column(Integer, nullable=False, default=0)
    token_giris = Column(Integer, nullable=False, default=0)
    token_cikis = Column(Integer, nullable=False, default=0)
    #: Bu gün düşülen kredi (saat).
    kredi = Column(Float, nullable=False, default=0.0)


class IcerikGorselleri(Base):
    __tablename__ = "icerik_gorselleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    anahtar = Column(String(64), unique=True, index=True, nullable=False)
    depo = Column(String(16), nullable=False)
    #: image/jpeg | image/png | image/webp
    tur = Column(String(16), nullable=False)
    ad = Column(String, nullable=True)
    genislik = Column(Integer, nullable=False, default=0)
    yukseklik = Column(Integer, nullable=False, default=0)
    boyut = Column(Integer, nullable=False, default=0)
    yukleyen = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
