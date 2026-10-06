"""Faz 4W — otomasyon kuralları ("şu olunca bunu yap") ve özel alanlar.

Tablolar
--------
* `otomasyon_kurallari` — kural: sahip (ajans ya da müşteri hesabı; API
  anahtarı/webhook ile aynı desen: `sahip_tur` + `hesap_email`, ajansta boş),
  tetikleyici olay, koşullar (JSON: `{"baglac": "ve"|"veya", "kosullar": [...]}`),
  sıralı eylemler (JSON listesi, en çok 5). Ayrıntı `services/otomasyon_kural.py`.
  Faz 7H: `bekleme_sonrasi_denetim` — "bekle" eyleminden sonra koşullar kaydın
  GÜNCEL hâliyle yeniden denetlenir; artık tutmuyorsa çalıştırma durur. Yeni
  kurallarda açık; sütun sonradan eklendiği için eski kurallarda NULL = kapalı.
* `otomasyon_calismalari` — HEM kuyruk HEM günlük: olay geldiğinde eşleşen her
  kural için bir satır (`bekliyor`), arka plan görevi / zamanlı uç işliyor;
  koşul sonucu, eylem sonuçları, "bekle" eyleminden sonra kalınan yer burada.
  (olay_id, kural_id) BENZERSİZ: aynı olay aynı kuralı bir kez çalıştırır.
  30 gün saklanıyor (istekle/zamanlı temizlik).
* `ozel_alanlar` — ajansın tanımladığı ek alanlar (CRM adayı, proje, müşteri
  hesabı, destek talebi). Mevcut tablolara sütun EKLENMİYOR.
* `ozel_alan_degerleri` — değerler: (varlık, varlık kimliği, alan) BENZERSİZ,
  değer JSON metni. Varlık kimliği metin: müşteri hesabında e-posta, diğerlerinde
  sayısal kimliğin metni.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class OtomasyonKurallari(Base):
    __tablename__ = "otomasyon_kurallari"
    __table_args__ = (
        Index("ix_otomasyon_kurallari_sahip", "sahip_tur", "hesap_email"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: ajans | musteri
    sahip_tur = Column(String(10), nullable=False, default="ajans")
    #: Müşteri hesabı (küçük harf); ajansta NULL.
    hesap_email = Column(String(254), index=True, nullable=True)
    ad = Column(String(120), nullable=False)
    aciklama = Column(Text, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    #: Tetikleyici olay (ör. "aday.olusturuldu").
    tetik = Column(String(60), index=True, nullable=False)
    #: JSON: {"baglac": "ve"|"veya", "kosullar": [{"alan", "islec", "deger"}]}
    kosullar = Column(Text, nullable=True)
    #: JSON listesi: [{"tur": "eposta", ...}, ...] (en çok 5).
    eylemler = Column(Text, nullable=False, default="[]")
    #: Hazır şablondan oluşturulduysa şablon anahtarı (bilgi amaçlı).
    sablon = Column(String(60), nullable=True)
    #: Faz 7H: "bekle"den sonra koşulları taze kayıtla yeniden denetle (NULL = kapalı; eski kurallar).
    bekleme_sonrasi_denetim = Column(Boolean, nullable=True)
    olusturan = Column(String(254), nullable=True)
    calisma_sayisi = Column(Integer, nullable=False, default=0)
    son_calisma_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class OtomasyonCalismalari(Base):
    __tablename__ = "otomasyon_calismalari"
    __table_args__ = (
        UniqueConstraint("olay_id", "kural_id", name="uq_otomasyon_calisma_olay_kural"),
        Index("ix_otomasyon_calisma_durum_zaman", "durum", "sonraki_zaman"),
        Index("ix_otomasyon_calisma_sahip", "sahip_tur", "hesap_email", "id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kural_id = Column(Integer, index=True, nullable=False)
    sahip_tur = Column(String(10), nullable=False)
    hesap_email = Column(String(254), nullable=True)
    olay_id = Column(String(80), nullable=False)
    #: Olay türü (ör. "destek.olusturuldu").
    tur = Column(String(60), nullable=False)
    #: Olayın hesabı (müşteri hesabı; ajansın kendi olayında boş).
    olay_hesap = Column(String(254), nullable=True)
    #: JSON: olayın ham verisi (kimlikler + iş alanları; bağlam çalışırken kuruluyor).
    veri = Column(Text, nullable=True)
    #: Olay zinciri derinliği (kullanıcı işi = 1; bir kuralın eyleminden doğan olay +1).
    derinlik = Column(Integer, nullable=False, default=1)
    #: JSON listesi: zincirdeki kural kimlikleri (aynı kural kendini tetikleyemez).
    zincir = Column(Text, nullable=True)
    #: bekliyor | tamam | hata | kosul_tutmadi | atlandi
    durum = Column(String(16), nullable=False, default="bekliyor")
    #: atlandi/hata kısa nedeni (dongu | derinlik | hiz_siniri | modul_kapali | kural_yok | kural_pasif …);
    #: Faz 7H: kosul_tutmadi + `kosul_artik_saglanmiyor` = bekleme sonrası yeniden denetimde durdu.
    neden = Column(String(120), nullable=True)
    kosul_sonucu = Column(Boolean, nullable=True)
    #: JSON: [{"alan", "islec", "deger", "gercek", "sonuc"}]
    kosul_ayrinti = Column(Text, nullable=True)
    #: JSON listesi: [{"sira", "tur", "durum": basarili|atlandi|hata|bekliyor, "neden", "ozet"}]
    eylem_sonuclari = Column(Text, nullable=True)
    #: Sıradaki eylemin dizini ("bekle"den sonra kalınan yer).
    sonraki_eylem = Column(Integer, nullable=False, default=0)
    #: Ne zaman işlenebilir ("bekle" eyleminde ileri bir zaman).
    sonraki_zaman = Column(DateTime(timezone=True), nullable=True)
    kilit_bitis = Column(DateTime(timezone=True), nullable=True)
    #: İlk kez işlenmeye başladığı an (hız sınırı bu sütunla sayılıyor).
    baslama_at = Column(DateTime(timezone=True), index=True, nullable=True)
    bitis_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, index=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, nullable=True)


class OzelAlanlar(Base):
    __tablename__ = "ozel_alanlar"
    __table_args__ = (
        UniqueConstraint("varlik", "anahtar", name="uq_ozel_alan_varlik_anahtar"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: crm_aday | proje | hesap | destek
    varlik = Column(String(20), index=True, nullable=False)
    #: Kalıcı anahtar (küçük harf, rakam, alt çizgi) — koşullarda ve yer tutucularda.
    anahtar = Column(String(40), nullable=False)
    ad = Column(String(80), nullable=False)
    #: metin | sayi | tarih | secim | coklu_secim | evet_hayir | url
    tur = Column(String(16), nullable=False, default="metin")
    #: JSON listesi (seçim türlerinde).
    secenekler = Column(Text, nullable=True)
    zorunlu = Column(Boolean, nullable=False, default=False)
    sira = Column(Integer, nullable=False, default=100)
    #: Yalnız proje/destek talebi: müşteri panelinde (salt okunur) ve müşteri kurallarında görünür.
    musteriye_gorunur = Column(Boolean, nullable=False, default=False)
    aktif = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class OzelAlanDegerleri(Base):
    __tablename__ = "ozel_alan_degerleri"
    __table_args__ = (
        UniqueConstraint("varlik", "varlik_id", "alan_id", name="uq_ozel_alan_degeri"),
        Index("ix_ozel_alan_degeri_varlik", "varlik", "varlik_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    varlik = Column(String(20), nullable=False)
    varlik_id = Column(String(254), nullable=False)
    alan_id = Column(Integer, index=True, nullable=False)
    #: JSON (metin, sayı, "YYYY-MM-DD", liste, bool).
    deger = Column(Text, nullable=True)
    guncelleyen = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


__all__ = ["OtomasyonKurallari", "OtomasyonCalismalari", "OzelAlanlar", "OzelAlanDegerleri"]
