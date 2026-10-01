"""Faz 3T — sözleşme şablonları, sözleşmeler ve basit elektronik imza kaydı.

Hukuki not
----------
Buradaki imza 5070 sayılı Elektronik İmza Kanunu anlamında GÜVENLİ
elektronik imza DEĞİLDİR; taraflar arasında basit elektronik onay
kaydıdır. Kayıt şunları tutuyor: imzalayanın yazdığı ad soyad, zaman, IP
özeti (tuzlu sha256 — ham IP yok), tarayıcı bilgisi (kısaltılmış), isteğe
bağlı el çizimi imza görseli (PNG, dosya deposunda) ve imzalanan METNİN
SHA-256 özeti.

Değişmezlik
-----------
İmzalanan sürümün metni bir daha değişmiyor: imzalı sözleşmede metin
değiştirilmek istenirse YENİ SÜRÜM açılıyor (`surum` + 1, `onceki_id`,
`kok_id`); eski sürüm imzasıyla birlikte olduğu gibi kalıyor. Gönderilmiş
ama imzalanmamış sözleşmede metin değişirse bağlantı iptal ediliyor ve
sözleşme taslağa dönüyor (müşteri gördüğünden farklı bir metni imzalamasın).
İmza anında sunucu, gösterilen metnin özetiyle kayıttaki metnin özetini
karşılaştırıyor; tutmazsa imza reddediliyor.

Durum: taslak | gonderildi | imzalandi | iptal
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class SozlesmeSablonlari(Base):
    __tablename__ = "sozlesme_sablonlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    baslik = Column(String, nullable=False)
    #: Markdown. Yer tutucular: {{musteri_adi}}, {{musteri_eposta}}, {{teklif_no}},
    #: {{toplam}}, {{tarih}}, {{baslangic}}, {{bitis}}, {{ajans_unvani}}, {{sozlesme_no}}
    govde = Column(Text, nullable=False)
    #: İsteğe bağlı İngilizce sürüm (yoksa Türkçe kullanılır).
    baslik_en = Column(String, nullable=True)
    govde_en = Column(Text, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)


class Sozlesmeler(Base):
    __tablename__ = "sozlesmeler"
    __table_args__ = (
        UniqueConstraint("no", "surum", name="uq_sozlesme_no_surum"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: SZL-YYYY-NNNN — sürümler aynı numarayı taşır (no + surum benzersiz).
    no = Column(String, index=True, nullable=False)
    surum = Column(Integer, nullable=False, default=1)
    kok_id = Column(Integer, index=True, nullable=True)
    onceki_id = Column(Integer, nullable=True)

    hesap_email = Column(String, index=True, nullable=True)
    #: İmzalayacak taraf (müşteri ya da aday).
    taraf_ad = Column(String, nullable=True)
    taraf_eposta = Column(String, index=True, nullable=True)

    baslik = Column(String, nullable=False)
    #: Yer tutucuları doldurulmuş Markdown metni.
    govde = Column(Text, nullable=False)
    #: tr | en (gövdenin dili; arayüz dili bundan bağımsız)
    dil = Column(String, nullable=False, default="tr")
    sablon_id = Column(Integer, nullable=True)
    teklif_id = Column(Integer, index=True, nullable=True)

    baslangic = Column(String, nullable=True)  # YYYY-MM-DD
    bitis = Column(String, index=True, nullable=True)  # YYYY-MM-DD (hatırlatma 30/7 gün)
    durum = Column(String, index=True, nullable=False, default="taslak")
    #: Gönderilen metnin SHA-256 özeti (onaltılık); imzada yeniden doğrulanır.
    metin_ozeti = Column(String(64), nullable=True)
    gonderildi_at = Column(DateTime(timezone=True), nullable=True)
    islem_id = Column(Integer, index=True, nullable=True)

    # --- İmza kaydı (basit elektronik onay) ---
    imza_ad = Column(String, nullable=True)
    imza_at = Column(DateTime(timezone=True), nullable=True)
    imza_ip_ozeti = Column(String, nullable=True)
    imza_tarayici = Column(String, nullable=True)
    #: İmzalanan metnin özeti (imza anında hesaplanan; metin_ozeti ile aynı olmalı).
    imza_metin_ozeti = Column(String(64), nullable=True)
    #: El çizimi imza görseli: dosya deposundaki anahtar (`services/dosya_deposu`).
    imza_gorsel_anahtari = Column(String, nullable=True)
    imza_gorsel_depo = Column(String, nullable=True)
    #: panel | baglanti
    imza_kanali = Column(String, nullable=True)

    iptal_at = Column(DateTime(timezone=True), nullable=True)
    olusturan_eposta = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)


class HatirlatmaIzleri(Base):
    """Bir kez gönderilmesi gereken hatırlatmaların kilidi (eşik başına bir satır).

    `tur`: fatura_vade (vade +1/+7/+14 gün) | sozlesme_bitis (30/7 gün kala).
    Benzersizlik veritabanında: aynı zamanlı görev iki kez çalışsa da (ya da iki
    tur çakışsa da) ikinci yazım IntegrityError alıyor, bildirim bir kez gidiyor.
    """

    __tablename__ = "hatirlatma_izleri"
    __table_args__ = (
        UniqueConstraint("tur", "ref_id", "esik", name="uq_hatirlatma_izi"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    tur = Column(String, nullable=False)
    ref_id = Column(Integer, index=True, nullable=False)
    esik = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_simdi)


class TekrarlayanFaturaKayitlari(Base):
    """Tekrarlayan faturanın dönem kilidi: (abonelik, dönem) başına TEK fatura.

    Tekrarlayan fatura şablonu ayrı bir tablo değil: `service_subscriptions`
    satırının fatura alanları (`fatura_otomatik`, `fatura_kalemleri`…). Bu
    tablo yalnız "bu dönemin faturası kesildi" bilgisini tutuyor; benzersizlik
    kısıtı aynı dönemin iki kez üretilmesini veritabanı düzeyinde engelliyor.
    """

    __tablename__ = "tekrarlayan_fatura_kayitlari"
    __table_args__ = (
        UniqueConstraint("abonelik_id", "donem", name="uq_tekrarlayan_donem"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    abonelik_id = Column(Integer, index=True, nullable=False)
    #: aylık: YYYY-MM, yıllık: YYYY
    donem = Column(String, nullable=False)
    invoice_id = Column(Integer, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)
