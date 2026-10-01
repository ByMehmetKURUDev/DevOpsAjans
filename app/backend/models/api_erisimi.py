"""Faz 4A — API anahtarları, imzalı webhook'lar ve idempotency kayıtları.

Tablolar
--------
* `api_anahtarlari` — herkese açık API (`/api/public/v1`) ve MCP sunucusu için
  anahtar. Ham anahtar (`mk_live_…`) VERİTABANINA YAZILMAZ: yalnız SHA-256
  özeti (`anahtar_ozeti`) ve rastgele kısmın ilk 8 karakteri (`onek`, listede
  "hangi anahtar" sorusunu cevaplamak için). Adında "anahtar" geçen sütunlar
  denetim kaydında zaten maskeli.
  - `sahip_tur` = `ajans` (yönetici; `hesap_email` NULL — bütün müşteriler)
    ya da `musteri` (`hesap_email` = müşteri hesabı; yalnız o hesap).
  - `olusturan` anahtarı açan kişi (hesap sahibi ya da `api` izinli ekip üyesi);
    üye açtıysa her istekte üyeliği ve izni yeniden doğrulanıyor.
  - `kapsamlar` JSON liste (`projeler:oku`, `gorevler:yaz` …), `ip_izinleri`
    JSON liste (CIDR; boş = her yer), `dakika_siniri` anahtar başına istek sınırı.
  - `son_kullanim_at` / `son_ip_ozeti` en çok dakikada bir Core UPDATE ile
    yazılıyor (denetim kaydına gürültü düşmesin). IP'nin tuzlu özeti, ham IP yok.
  - `iptal_at` doluysa anahtar o istekten itibaren geçersiz (önbellek yok).
* `webhook_uc_noktalari` — olayların POST edildiği adres. `gizli_anahtar`
  imzalama sırrı (yalnız oluşturulurken / yenilenirken bir kez gösterilir;
  `BAGLANTI_SIFRE_ANAHTARI` tanımlıysa Fernet ile şifreli saklanır). Yenilemede
  eskisi 24 saat `onceki_gizli_anahtar` olarak ikinci imzayla gönderilmeye devam
  eder (alıcı tarafı kesintisiz geçsin).
  - `tum_musteriler` yalnız ajans uç noktası: müşteri hesaplarının olayları da gelsin.
  - `ardisik_hata` art arda başarısız deneme sayısı; eşiği aşınca uç noktası
    otomatik pasifleşir ve sahibine bildirim gider.
* `webhook_teslimatlari` — bir olayın bir uç noktasına teslimi (olay başına uç
  nokta başına bir satır; gövde ve imza girdisi burada). `durum`:
  bekliyor | basarili | vazgecildi | atlandi. `kilit_bitis` aynı teslimatı iki
  işçinin birden göndermesini engelleyen kısa süreli kilit.
* `webhook_denemeleri` — her HTTP denemesi: durum kodu, süre, yanıtın ilk 1 kB'ı.
  30 günden eski teslimat ve denemeler temizleniyor.
* `api_idempotency` — yazma uçlarındaki `Idempotency-Key` (anahtar başına,
  24 saat): aynı anahtarla gelen tekrar aynı yanıtı alır; gövde farklıysa 422.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class ApiAnahtarlari(Base):
    __tablename__ = "api_anahtarlari"
    __table_args__ = (
        Index("ix_api_anahtarlari_sahip", "sahip_tur", "hesap_email"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: ajans | musteri
    sahip_tur = Column(String(8), nullable=False)
    #: Müşteri hesabı (küçük harf); ajansta NULL.
    hesap_email = Column(String, index=True, nullable=True)
    ad = Column(String(80), nullable=False)
    #: Rastgele kısmın ilk 8 karakteri (görünür önek).
    onek = Column(String(8), index=True, nullable=False)
    #: Ham anahtarın SHA-256 özeti (onaltılık).
    anahtar_ozeti = Column(String(64), unique=True, nullable=False)
    kapsamlar = Column(Text, nullable=False, default="[]")
    ip_izinleri = Column(Text, nullable=True)
    dakika_siniri = Column(Integer, nullable=False, default=60)
    son_kullanma = Column(DateTime(timezone=True), nullable=True)
    olusturan = Column(String, nullable=True)
    son_kullanim_at = Column(DateTime(timezone=True), nullable=True)
    son_ip_ozeti = Column(String(64), nullable=True)
    iptal_at = Column(DateTime(timezone=True), nullable=True)
    iptal_eden = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class WebhookUcNoktalari(Base):
    __tablename__ = "webhook_uc_noktalari"
    __table_args__ = (
        Index("ix_webhook_uc_noktalari_sahip", "sahip_tur", "hesap_email"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    sahip_tur = Column(String(8), nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    url = Column(String(2000), nullable=False)
    aciklama = Column(String(200), nullable=True)
    #: JSON liste — abone olunan olay türleri.
    olaylar = Column(Text, nullable=False, default="[]")
    tum_musteriler = Column(Boolean, nullable=False, default=False)
    aktif = Column(Boolean, nullable=False, default=True, index=True)
    #: Otomatik pasifleştirildiyse sebebi (ör. "ardisik_hata").
    pasif_sebebi = Column(String(40), nullable=True)
    gizli_anahtar = Column(Text, nullable=False)
    onceki_gizli_anahtar = Column(Text, nullable=True)
    onceki_gizli_bitis = Column(DateTime(timezone=True), nullable=True)
    ardisik_hata = Column(Integer, nullable=False, default=0)
    son_basari_at = Column(DateTime(timezone=True), nullable=True)
    son_hata_at = Column(DateTime(timezone=True), nullable=True)
    olusturan = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class WebhookTeslimatlari(Base):
    __tablename__ = "webhook_teslimatlari"
    __table_args__ = (
        Index("ix_webhook_teslimatlari_bekleyen", "durum", "sonraki_deneme"),
        Index("ix_webhook_teslimatlari_uc_zaman", "uc_id", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    uc_id = Column(Integer, index=True, nullable=False)
    #: Olay kimliği (`evt_…`) — aynı olay her uç noktasına aynı kimlikle gider.
    olay_id = Column(String(40), index=True, nullable=False)
    tur = Column(String(40), nullable=False)
    hesap_email = Column(String, nullable=True)
    #: İmzalanan gövdenin TAMAMI (JSON metni) — yeniden denemede birebir aynısı.
    govde = Column(Text, nullable=False)
    durum = Column(String(12), nullable=False, default="bekliyor")
    deneme_sayisi = Column(Integer, nullable=False, default=0)
    sonraki_deneme = Column(DateTime(timezone=True), nullable=True)
    kilit_bitis = Column(DateTime(timezone=True), nullable=True)
    son_durum_kodu = Column(Integer, nullable=True)
    son_sure_ms = Column(Integer, nullable=True)
    son_yanit = Column(Text, nullable=True)
    son_hata = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, nullable=True)


class WebhookDenemeleri(Base):
    __tablename__ = "webhook_denemeleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    teslimat_id = Column(Integer, index=True, nullable=False)
    deneme_no = Column(Integer, nullable=False)
    #: otomatik | elle | test
    tetik = Column(String(10), nullable=False, default="otomatik")
    durum_kodu = Column(Integer, nullable=True)
    sure_ms = Column(Integer, nullable=True)
    yanit = Column(Text, nullable=True)
    hata = Column(String(200), nullable=True)
    basarili = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class ApiIdempotency(Base):
    __tablename__ = "api_idempotency"
    __table_args__ = (
        UniqueConstraint("anahtar_id", "idem_anahtari", name="uq_api_idempotency_anahtar"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    anahtar_id = Column(Integer, index=True, nullable=False)
    idem_anahtari = Column(String(200), nullable=False)
    #: "POST /api/public/v1/gorevler" — aynı anahtar başka uçta kullanılamaz.
    istek = Column(String(300), nullable=False)
    govde_ozeti = Column(String(64), nullable=False)
    #: NULL = işleniyor (aynı anda gelen kopya 409 alır).
    durum_kodu = Column(Integer, nullable=True)
    yanit = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)
