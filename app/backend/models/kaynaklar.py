"""Faz 3K — Kaynaklar: sitede herkese açık araç / beceri / açık kaynak listesi.

Metinler marketplace ve bilgi bankasıyla aynı desende: Türkçe ana sütunlarda
(`baslik`, `ozet`, `aciklama`, `adimlar`), diğer altı dil `ceviriler`
JSON'unda (``{"en": {"baslik": .., "ozet": .., "aciklama": .., "adimlar": [..]}}``).
Seçili dilde alan boşsa Türkçesi gösteriliyor.

`adimlar` ve `etiketler` JSON listesi (metin sütunu): SQLite ile Postgres'te
aynı davranışı versin diye JSON türü kullanılmadı (diğer tablolarla tutarlı).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


#: Dış bağlantının türü (düğme metni ve ikon buna göre seçiliyor).
BAGLANTI_TURLERI = ("github", "site", "belge", "video")


class Kaynaklar(Base):
    __tablename__ = "kaynaklar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: URL'deki kısa ad: /kaynaklar/<slug>. Küçük harf, rakam, tire.
    slug = Column(String, unique=True, index=True, nullable=False)
    kategori = Column(String, index=True, nullable=False)
    baslik = Column(String, nullable=False)
    ozet = Column(Text, nullable=True)
    #: Düz metin; paragraflar boş satırla ("\n\n") ayrılıyor.
    aciklama = Column(Text, nullable=True)
    #: JSON listesi: "nasıl başlanır" adımları (Türkçe).
    adimlar = Column(Text, nullable=True)
    #: JSON: {"en": {"baslik", "ozet", "aciklama", "adimlar": [...]}, ...}
    ceviriler = Column(Text, nullable=True)
    #: JSON listesi (Türkçe, küçük harf).
    etiketler = Column(Text, nullable=True)
    baglanti = Column(String, nullable=False)
    baglanti_turu = Column(String, nullable=False, default="site")
    lisans = Column(String, nullable=True)
    ucretsiz = Column(Boolean, nullable=False, default=True)
    acik_kaynak = Column(Boolean, nullable=False, default=False)
    youtube_short = Column(String, nullable=True)
    one_cikan = Column(Boolean, nullable=False, default=False)
    sira = Column(Integer, nullable=False, default=100)
    yayinda = Column(Boolean, index=True, nullable=False, default=True)
    #: Bağlantının ve bilginin en son elle doğrulandığı gün.
    dogrulama_tarihi = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class KaynakTohumIzi(Base):
    """Tohum dosyasından bir kez eklenmiş slug'lar.

    Tohumlama yalnız burada izi OLMAYAN slug'ları ekliyor: yönetici bir tohum
    kaynağını silerse bir sonraki açılışta geri gelmiyor; tohum dosyasına
    yeni kaynak eklenirse o ekleniyor. Panelde düzenlenmiş kayıtlara hiç
    dokunulmuyor.
    """

    __tablename__ = "kaynak_tohum_izi"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    eklendi_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
