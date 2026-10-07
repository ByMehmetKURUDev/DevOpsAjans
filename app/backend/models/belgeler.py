"""Faz 5B — belgeler, wiki ve strateji araçları.

Tablolar
--------
* `belgeler` — tek tablo, iki tür aile:
  - `tur="belge"`: Markdown gövdeli belge / wiki / not (yapılacaklar onay
    kutularıyla gövdenin içinde: `- [ ] madde @kisi@ornek.com`).
  - strateji şablonları (`swot`, `is_modeli`, `lean`, `pestle`, `porter`,
    `mckinsey_7s`, `mavi_okyanus`, `ikigai`): gövde JSON
    `{"isletme": "...", "kutular": {"<kutu>": "metin"}}`; kutular ve ızgara
    düzeni kodda (`services/belgeler.py` › `STRATEJI_SABLONLARI`).
* `belge_surumleri` — başlık + gövdenin anlık görüntüsü (oluşturma ve her
  içerik değişikliği; belge başına son `SURUM_SINIRI`). Geri yükleme yeni
  sürüm olarak yazılır, eskiler silinmez.
* `belge_ai_kullanimi` — hesap × gün AI sayacı (Faz 5A/5I deseni: aya dahil
  hak, günlük üst sınır, kredi bloğu). Ajansın kendi kullanımı `hesap=""`.

Sahiplik ve görünürlük
----------------------
* Ajans belgesi: `sahip_hesap` BOŞ. `alan` = `ajans` (ajans içi wiki),
  `musteri` (`musteri_email` dolu) ya da `proje` (`proje_id` + projenin
  müşterisi). `gorunurluk` = `ekip` (yalnız ajans) | `paylasilan` (ilgili
  müşteri panelinde salt okunur görür; ajans içi wikide paylaşım yok).
* Müşterinin kendi belgesi (modül `belgeler`): `sahip_hesap` = hesap e-postası,
  `musteri_email` aynı. `gorunurluk` = `ekip` (yalnız müşterinin hesabı) |
  `paylasilan` (ajansla paylaşıldı — ajans salt okunur görür). Paylaşılmamış
  müşteri belgesi ajans listesinde YOK.
* Çöp kutusu sahibi `sahip_hesap`: ajans belgesi müşterinin "Silinenler"ine
  hiç düşmüyor (ekip içi belgenin başlığı da sızmasın).

Liste/JSON alanları metin sütununda (SQLite ile Postgres aynı davransın).
`arama_metni`: başlık + gövdenin küçük harfli, aksansız kopyası (Türkçe İ/ı,
ş/ğ/ç … — SQLite'ın `lower()`ı yalnız ASCII'yi küçültüyor); arama bunun
üstünde `LIKE`.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class Belgeler(Base):
    __tablename__ = "belgeler"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: belge | swot | is_modeli | lean | pestle | porter | mckinsey_7s | mavi_okyanus | ikigai
    tur = Column(String(30), nullable=False, default="belge", index=True)
    baslik = Column(String(200), nullable=False)
    #: Markdown (belge) ya da JSON (strateji).
    icerik = Column(Text, nullable=True)
    #: JSON liste.
    etiketler = Column(Text, nullable=True)
    #: ajans | musteri | proje
    alan = Column(String(20), nullable=False, default="ajans")
    musteri_email = Column(String(255), nullable=True, index=True)
    proje_id = Column(Integer, nullable=True, index=True)
    #: ekip | paylasilan
    gorunurluk = Column(String(20), nullable=False, default="ekip")
    #: Müşterinin kendi belgesiyse hesabı; ajans belgesinde boş.
    sahip_hesap = Column(String(255), nullable=True, index=True)
    sabit = Column(Boolean, nullable=False, default=False)
    surum = Column(Integer, nullable=False, default=1)
    olusturan = Column(String(255), nullable=True)
    son_duzenleyen = Column(String(255), nullable=True)
    #: admin | client
    son_duzenleyen_rol = Column(String(10), nullable=True)
    paylasildi_at = Column(DateTime(timezone=True), nullable=True)
    #: Müşterinin "okudum / onaylıyorum" işareti (ajansın paylaştığı belgede).
    okundu_at = Column(DateTime(timezone=True), nullable=True)
    okuyan = Column(String(255), nullable=True)
    okundu_surum = Column(Integer, nullable=True)
    arama_metni = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class BelgeSurumleri(Base):
    __tablename__ = "belge_surumleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    belge_id = Column(Integer, index=True, nullable=False)
    surum = Column(Integer, nullable=False)
    baslik = Column(String(200), nullable=False)
    icerik = Column(Text, nullable=True)
    duzenleyen = Column(String(255), nullable=True)
    #: admin | client
    rol = Column(String(10), nullable=True)
    #: Neden yazıldı: "olusturma", "duzenleme", "geri_yukleme:<sürüm>", "yapilacak", "gorev:<id>".
    aciklama = Column(String(120), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class BelgeAiKullanimi(Base):
    __tablename__ = "belge_ai_kullanimi"
    __table_args__ = (
        UniqueConstraint("hesap", "gun", name="uq_belge_ai_kullanimi_hesap_gun"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Müşteri hesabı; ajansın kendi işi için "".
    hesap = Column(String, index=True, nullable=False, default="")
    #: UTC gün, YYYY-AA-GG
    gun = Column(String, index=True, nullable=False)
    uretim = Column(Integer, nullable=False, default=0)
    token_giris = Column(Integer, nullable=False, default=0)
    token_cikis = Column(Integer, nullable=False, default=0)
    #: Bu gün düşülen kredi (saat).
    kredi = Column(Float, nullable=False, default=0.0)
