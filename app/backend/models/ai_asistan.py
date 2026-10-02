"""Faz 5A — AI asistan + bilgi bankası (modül `ai_asistan`).

Tablolar (adlar `ai_asistan_` önekli: Faz 3U'nun Uzman Asistanlar tabloları
`asistan_sohbetleri` / `asistan_mesajlari` ile karışmasın):

* `ai_asistanlar`            — hesabın asistanı (ajansın kendisininki `hesap_email` boş):
                               görünüm, ton, dil, eşik, mesai, izinli kökenler, saklama.
* `ai_asistan_kaynaklari`    — bilgi bankası kaynağı (metin, SSS, belge, URL/site haritası,
                               modülden içe aktarma) + işlem durumu.
* `ai_asistan_parcalari`     — kaynakların parçaları (başlık duyarlı, ~800 karakter) ve
                               sözcüksel arama terimleri (BM25; isteğe bağlı gömme vektörü).
* `ai_asistan_sohbetleri`    — ziyaretçi sohbeti (KİŞİSEL VERİ: saklama süresi dolunca
                               siliniyor; IP yalnız tuzlu özet) + insana devir bilgisi.
* `ai_asistan_mesajlari`     — sohbet mesajları (gösterilen kaynaklarla).
* `ai_asistan_kullanimi`     — hesap × gün sayaçları (mesaj, jeton, düşülen kredi).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class AiAsistanlar(Base):
    __tablename__ = "ai_asistanlar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Sahip hesap (müşteri); ajansın kendi asistanında boş.
    hesap_email = Column(String, index=True, nullable=True)
    #: Herkese açık anahtar (gömme kodu, /asistan/<anahtar>); yenilenebilir.
    anahtar = Column(String, unique=True, index=True, nullable=False)
    ad = Column(String, nullable=False)
    karsilama = Column(Text, nullable=True)
    #: resmi | samimi
    ton = Column(String, nullable=False, default="samimi")
    #: otomatik | tr | en | de | ru | zh | hi | ar
    dil = Column(String, nullable=False, default="otomatik")
    renk = Column(String, nullable=False, default="#7c3aed")
    #: Avatar görseli (dosya deposunda `asistan/<anahtar>.webp`).
    avatar = Column(String, nullable=True)
    avatar_depo = Column(String, nullable=True)
    #: JSON liste: önerilen sorular (en çok 6).
    onerilen_sorular = Column(Text, nullable=True)
    #: kisa | orta | uzun
    yanit_uzunlugu = Column(String, nullable=False, default="orta")
    #: Soru terimlerinin en iyi parçada bulunma oranı (IDF ağırlıklı, 0–1) bunun altındaysa
    #: "bilmiyorum" + insana devret önerisi.
    devir_esigi = Column(Float, nullable=False, default=0.5)
    #: JSON liste: konuşulmayacak konular.
    yasakli_konular = Column(Text, nullable=True)
    #: JSON: {"aktif": bool, "saat_dilimi": "Europe/Istanbul", "gunler": {"0": [["09:00","18:00"]], ...}}
    mesai = Column(Text, nullable=True)
    #: JSON liste: asistanın açılabileceği alan adları (alt alan adları dahil); boş = her yer.
    izinli_kokenler = Column(Text, nullable=True)
    #: Paylaşılabilir tam sayfa (/asistan/<anahtar>) açık mı?
    tam_sayfa = Column(Boolean, nullable=False, default=True)
    aktif = Column(Boolean, nullable=False, default=True)
    saklama_gun = Column(Integer, nullable=False, default=90)
    #: Gömme anahtarı tanımlıysa BM25 + vektör (hibrit) sıralama.
    hibrit = Column(Boolean, nullable=False, default=False)
    aydinlatma_metni = Column(Text, nullable=True)
    aydinlatma_baglantisi = Column(String, nullable=True)
    #: Parçalar her değiştiğinde artar (bellekteki arama dizini önbelleği bunu izliyor).
    dizin_surumu = Column(Integer, nullable=False, default=0)
    olusturan = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class AiAsistanKaynaklari(Base):
    __tablename__ = "ai_asistan_kaynaklari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    asistan_id = Column(Integer, index=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    #: metin | sss | belge | url | modul
    tur = Column(String, nullable=False)
    baslik = Column(String, nullable=False)
    #: JSON: türe göre ayar (url: {"url", "kapsam": "tek"|"site_haritasi", "en_cok"};
    #: modul: {"modul": "qr_menu"|"randevu", "id"}).
    ayar = Column(Text, nullable=True)
    #: metin/belge: çıkarılmış düz metin; sss: JSON [{"soru","cevap"}]. URL/modül kaynağında boş
    #: (her işlemede yeniden alınıyor).
    metin = Column(Text, nullable=True)
    dosya_adi = Column(String, nullable=True)
    boyut = Column(Integer, nullable=True)
    #: isleniyor | hazir | hata
    durum = Column(String, nullable=False, default="isleniyor")
    hata = Column(String, nullable=True)
    parca_sayisi = Column(Integer, nullable=False, default=0)
    karakter = Column(Integer, nullable=False, default=0)
    #: URL kaynağında işlenen sayfa sayısı.
    sayfa_sayisi = Column(Integer, nullable=False, default=0)
    haftalik_yenile = Column(Boolean, nullable=False, default=False)
    son_isleme_at = Column(DateTime(timezone=True), nullable=True)
    sonraki_yenileme_at = Column(DateTime(timezone=True), index=True, nullable=True)
    olusturan = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class AiAsistanParcalari(Base):
    __tablename__ = "ai_asistan_parcalari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    asistan_id = Column(Integer, index=True, nullable=False)
    kaynak_id = Column(Integer, index=True, nullable=False)
    sira = Column(Integer, nullable=False, default=0)
    #: Başlık yolu ("Kargo › Ücretler") — sayfa başlığı ya da SSS sorusu.
    baslik = Column(String, nullable=True)
    metin = Column(Text, nullable=False)
    #: Normalleştirilmiş, kökü kırpılmış terimler (boşlukla ayrılmış) — BM25 bunu okuyor.
    terimler = Column(Text, nullable=False)
    terim_sayisi = Column(Integer, nullable=False, default=0)
    #: URL kaynağında parçanın geldiği sayfa.
    adres = Column(String, nullable=True)
    #: tr | en | de | ru | diger — parçanın tahmini dili (kök kırpma kuralı).
    dil = Column(String, nullable=True)
    #: İsteğe bağlı gömme vektörü (JSON float listesi).
    vektor = Column(Text, nullable=True)


class AiAsistanSohbetleri(Base):
    __tablename__ = "ai_asistan_sohbetleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    asistan_id = Column(Integer, index=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    #: Ziyaretçi oturum jetonunun sha256 özeti (jetonun kendisi saklanmıyor).
    oturum_ozeti = Column(String, unique=True, index=True, nullable=False)
    #: gomulu | sayfa | onizleme
    kaynak = Column(String, nullable=False, default="sayfa")
    #: Gömüldüğü sitenin alan adı (kişisel veri değil).
    koken = Column(String, nullable=True)
    dil = Column(String, nullable=True)
    #: IP'nin tuzlu özeti (ham IP hiçbir yerde yok).
    ip_ozeti = Column(String, nullable=True)
    mesaj_sayisi = Column(Integer, nullable=False, default=0)
    bilinmeyen_sayisi = Column(Integer, nullable=False, default=0)
    #: acik | devredildi
    durum = Column(String, nullable=False, default="acik")
    devir_at = Column(DateTime(timezone=True), nullable=True)
    devir_ad = Column(String, nullable=True)
    devir_eposta = Column(String, nullable=True)
    devir_telefon = Column(String, nullable=True)
    devir_notu = Column(Text, nullable=True)
    talep_id = Column(Integer, nullable=True)
    aday_id = Column(Integer, nullable=True)
    anonim = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=True)
    son_mesaj_at = Column(DateTime(timezone=True), index=True, default=_simdi, nullable=True)


class AiAsistanMesajlari(Base):
    __tablename__ = "ai_asistan_mesajlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    sohbet_id = Column(Integer, index=True, nullable=False)
    #: kullanici | asistan | sistem
    rol = Column(String, nullable=False)
    metin = Column(Text, nullable=False)
    #: JSON [{"no", "kaynak_id", "baslik", "adres"}]
    kaynaklar = Column(Text, nullable=True)
    bilinmiyor = Column(Boolean, nullable=False, default=False)
    kapsama = Column(Float, nullable=True)
    token_giris = Column(Integer, nullable=True)
    token_cikis = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=True)


class AiAsistanKullanimi(Base):
    __tablename__ = "ai_asistan_kullanimi"
    __table_args__ = (
        UniqueConstraint("hesap", "gun", name="uq_ai_asistan_kullanimi_hesap_gun"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Müşteri e-postası; ajansın kendi asistanı için "".
    hesap = Column(String, index=True, nullable=False, default="")
    #: UTC gün, YYYY-AA-GG
    gun = Column(String, index=True, nullable=False)
    #: Yanıtlanan ziyaretçi mesajı (yapay zekâya gidenler + "bilmiyorum" yanıtları).
    mesaj = Column(Integer, nullable=False, default=0)
    #: Yapay zekâya giden mesaj.
    ai_mesaj = Column(Integer, nullable=False, default=0)
    token_giris = Column(Integer, nullable=False, default=0)
    token_cikis = Column(Integer, nullable=False, default=0)
    #: Bu gün düşülen kredi (saat).
    kredi = Column(Float, nullable=False, default=0.0)
    devir = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)
