"""Faz 4Q — Dinamik QR stüdyosu ve kısa link.

Tablolar
--------
* `dinamik_qr` — bir QR kodu ya da kısa link kaydı.
  - `hesap_email` kayıt sahibi müşteri hesabı (küçük harf); BOŞ (NULL) ise
    ajansın kendi kaydı (yönetici panelinden).
  - `kod` 7 karakter, değişmez: basılı QR her zaman `/q/<kod>` adresini
    taşır. `takma_ad` isteğe bağlı, okunaklı ikinci adres (`/q/<takma-ad>`);
    değiştirilebilir, QR görselini etkilemez.
  - `alanlar` türe özgü alanların JSON'u (Wi-Fi parolası HARİÇ: o
    `wifi_sifre` sütununda — adı "sifre" içerdiği için denetim kaydında maskeli).
  - `hedef` yönlendirmeli türlerde sunucunun ürettiği adres (kaydederken
    hesaplanır, taramada yeniden doğrulanır). vCard / etkinlik / statik
    türlerde boş.
  - `tasarim` renk, kenar, boyut, hata düzeltme JSON'u. Logo ayrı tabloda.
  - `aktif` (sahibi açıp kapatır), `engelli` (yalnız yönetici: kötüye
    kullanım; sahibi kaldıramaz), `bitis`, `tarama_limiti`.
  - `tarama_sayisi` bot olmayan taramaların sayacı (limit kontrolü tek satır
    okumayla yapılsın diye önbellek; asıl kayıt `dinamik_qr_taramalari`).
* `dinamik_qr_logolari` — QR'ın ortasındaki logo (sunucuda en çok 512 px
  PNG'ye çevrilmiş, base64). Liste sorguları bu büyük alana hiç dokunmasın
  diye ayrı; QR silinince birlikte çöp kutusuna düşer.
* `dinamik_qr_taramalari` — her tarama: zaman, gün (UTC), ülke, cihaz sınıfı,
  işletim sistemi ailesi, yönlendiren alan adı, bot/önizleyici işareti ve IP
  özeti. Ham IP ve tam User-Agent SAKLANMAZ. IP özeti gün ve tuzla birlikte
  alınıyor (`utils/istemci_ip.ip_ozeti`): aynı günün tekil sayımı için
  yeterli, günler arası kişi izlemeye yaramıyor.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class DinamikQr(Base):
    __tablename__ = "dinamik_qr"
    __table_args__ = (
        Index("ix_dinamik_qr_hesap_tur", "hesap_email", "tur"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Kayıt sahibi müşteri hesabı; NULL = ajansın kendi kaydı.
    hesap_email = Column(String, index=True, nullable=True)
    #: Oluşturan kişi (jetondaki e-posta).
    olusturan_email = Column(String, nullable=True)
    kod = Column(String(16), unique=True, index=True, nullable=False)
    takma_ad = Column(String(40), unique=True, index=True, nullable=True)
    ad = Column(String(120), nullable=False)
    tur = Column(String(24), index=True, nullable=False)
    #: QR görseli olmadan kullanılan kısa link (yalnız `url` türü).
    kisa_link = Column(Boolean, nullable=False, default=False, index=True)
    alanlar = Column(Text, nullable=True)
    wifi_sifre = Column(String(128), nullable=True)
    hedef = Column(Text, nullable=True)
    tasarim = Column(Text, nullable=True)
    logo_var = Column(Boolean, nullable=False, default=False)
    aktif = Column(Boolean, nullable=False, default=True, index=True)
    engelli = Column(Boolean, nullable=False, default=False)
    bitis = Column(DateTime(timezone=True), nullable=True)
    tarama_limiti = Column(Integer, nullable=True)
    tarama_sayisi = Column(Integer, nullable=False, default=0)
    son_tarama_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class DinamikQrLogolari(Base):
    __tablename__ = "dinamik_qr_logolari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    qr_id = Column(Integer, unique=True, index=True, nullable=False)
    #: Sunucunun yeniden kodladığı PNG (en çok 512 px), base64.
    veri = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class DinamikQrTaramalari(Base):
    __tablename__ = "dinamik_qr_taramalari"
    __table_args__ = (
        Index("ix_dinamik_qr_taramalari_qr_zaman", "qr_id", "zaman"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    qr_id = Column(Integer, index=True, nullable=False)
    zaman = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    #: UTC gün (YYYY-MM-DD) — günlük seri ve tekil sayım için.
    gun = Column(String(10), nullable=False)
    #: ISO 3166-1 alfa-2 (Cloudflare `request.cf.country` → `X-MK-Ulke`).
    ulke = Column(String(2), nullable=True)
    #: mobil | tablet | masaustu | bilinmiyor
    cihaz = Column(String(12), nullable=False, default="bilinmiyor")
    #: ios | android | windows | macos | linux | chromeos | diger
    isletim = Column(String(12), nullable=False, default="diger")
    referer_alan = Column(String(120), nullable=True)
    #: Gün + tuz ile alınmış sha256 (ham IP yok).
    ip_ozeti = Column(String(64), nullable=False)
    #: Bot / bağlantı önizleyici / önden yükleme: sayılara katılmaz.
    bot = Column(Boolean, nullable=False, default=False, index=True)
