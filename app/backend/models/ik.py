"""Faz 6I — İnsan kaynakları modülü: personel, izin, vardiya. Bordro/maaş/SGK/puantaj YOK.

Tablolar
--------
* `ik_ayarlari` — hesap düzeyi kurallar (`kapsam`: ajans için `@ajans`, müşteride hesap e-postası):
  çalışma günleri, yıllık izin kıdem eşikleri (4857 m.53 varsayılanları), yaş grubu en az günü, yasal
  izin günleri (doğum, babalık, evlilik, ölüm), kapatılan sabit resmi tatiller, vardiya uyarı ayarları.
  Hepsi BİLGİLENDİRME amaçlıdır; arayüz "hukuki danışmanlık değildir" der.
* `ik_tatiller` — kullanıcının eklediği tatil günleri (dini bayramlar yıla göre değiştiği için
  TOHUMLANMAZ; sabit ulusal günler kodda üretilir — `services/ik.sabit_tatiller`).
* `ik_personel` — personel kartı. VERİ AZALTMA: TC kimlik no, doğum tarihi, sağlık, din, adres TUTULMAZ;
  yaşa bağlı izin kuralı için yalnız yaş grubu işareti (`genel` | `genc` = 18 yaş ve altı | `ileri` = 50 yaş
  ve üstü). `devir_gun` + `devir_tarihi`: o günün başındaki kalan yıllık izin (başlangıç bakiyesi).
  `portal_surumu` artınca girişsiz personel bağlantısı geçersiz olur; `portal_acik` kapalıysa bağlantı ölü.
  `hesap_email` BOŞ (NULL) ise ajansın kendi personeli.
* `ik_izinler` — izin talebi / kaydı: beklemede → onaylandı | reddedildi; iptal; karar geri alınabilir.
  `gun`: çalışma günü sayısı (işyerinin çalışma günleri ve resmi tatiller hariç; yarım gün 0,5). Rapor
  türünde YALNIZ tarih aralığı (teşhis / açıklama alanı yok). `istek_kimligi`: portaldan çift gönderim
  koruması.
* `ik_vardiya_sablonlari` — vardiya şablonu (ad, başlangıç–bitiş "SS:DD", mola, renk).
* `ik_vardiyalar` — planlanan vardiya: `bas`/`bit` işyerinin yerel saatiyle (saat dilimsiz), taslak →
  yayında. Yayındaki vardiya değişirse `degisti` (bir sonraki yayında personele yeniden bildirilir).
* `ik_dosyalar` — personel belge ekleri (içerik `services/dosya_deposu`; çöp kutusu kalıcı silinince içerik
  de silinir).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class IkAyarlari(Base):
    __tablename__ = "ik_ayarlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: `@ajans` ya da hesap e-postası (tek satır).
    kapsam = Column(String(254), unique=True, index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    #: Portalda ve PDF başlığında görünen işyeri adı.
    firma_adi = Column(String(160), nullable=True)
    #: JSON: haftanın günleri (0 = Pazartesi … 6 = Pazar). Boş = varsayılan Pzt–Cum.
    calisma_gunleri = Column(Text, nullable=True)
    #: JSON: [{"yil": en az tamamlanan kıdem yılı, "gun": yıllık gün}] (artan). Boş = 4857 m.53 varsayılanı.
    kidem_kurallari = Column(Text, nullable=True)
    #: 18 yaş ve altı / 50 yaş ve üstü için en az yıllık gün (boş = 20).
    yas_en_az_gun = Column(Integer, nullable=True)
    #: JSON: {"dogum", "babalik", "evlilik", "olum"} → gün. Boş = varsayılan.
    yasal_gunler = Column(Text, nullable=True)
    #: JSON: kapatılan sabit ulusal tatiller ["AA-GG", ...].
    kapali_sabitler = Column(Text, nullable=True)
    uyari_izinli = Column(Boolean, nullable=False, default=True)
    uyari_cakisma = Column(Boolean, nullable=False, default=True)
    uyari_dinlenme = Column(Boolean, nullable=False, default=True)
    en_az_dinlenme_saat = Column(Integer, nullable=False, default=11)
    uyari_haftalik = Column(Boolean, nullable=False, default=True)
    haftalik_en_cok_saat = Column(Integer, nullable=False, default=45)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class IkTatiller(Base):
    __tablename__ = "ik_tatiller"
    __table_args__ = (
        UniqueConstraint("kapsam", "tarih", name="uq_ik_tatil_gun"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    tarih = Column(Date, nullable=False)
    ad = Column(String(120), nullable=False)
    #: Yarım gün tatil (arife): izin hesabında 0,5 gün düşer.
    yarim = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class IkPersonel(Base):
    __tablename__ = "ik_personel"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Sahip müşteri hesabı; NULL = ajansın kendi personeli.
    hesap_email = Column(String(254), index=True, nullable=True)
    ad = Column(String(120), nullable=False)
    eposta = Column(String(254), nullable=True)
    telefon = Column(String(20), nullable=True)
    gorev = Column(String(120), nullable=True)
    departman = Column(String(120), nullable=True)
    ise_giris = Column(Date, nullable=False)
    #: aktif | ayrildi
    durum = Column(String(10), nullable=False, default="aktif", index=True)
    ayrilis_tarihi = Column(Date, nullable=True)
    #: genel | genc (18 yaş ve altı) | ileri (50 yaş ve üstü) — doğum tarihi TUTULMAZ.
    yas_grubu = Column(String(8), nullable=False, default="genel")
    #: Başlangıç bakiyesi: `devir_tarihi` gününün başında kalan yıllık izin (gün; yarım olabilir).
    devir_gun = Column(Float, nullable=False, default=0.0)
    devir_tarihi = Column(Date, nullable=True)
    #: Sözleşmeyle kanunun üstünde yıllık gün verildiyse (boş = kurala göre).
    yillik_gun_ozel = Column(Integer, nullable=True)
    notlar = Column(Text, nullable=True)
    #: E-posta ve portal dili.
    dil = Column(String(2), nullable=False, default="tr")
    portal_surumu = Column(Integer, nullable=False, default=1)
    portal_acik = Column(Boolean, nullable=False, default=True)
    portal_son_at = Column(DateTime(timezone=True), nullable=True)
    olusturan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class IkIzinler(Base):
    __tablename__ = "ik_izinler"
    __table_args__ = (
        Index("ix_ik_izin_personel_tarih", "personel_id", "baslangic"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=True)
    personel_id = Column(Integer, index=True, nullable=False)
    #: yillik | mazeret | ucretsiz | rapor | dogum | babalik | evlilik | olum | diger
    tur = Column(String(12), nullable=False)
    baslangic = Column(Date, nullable=False)
    bitis = Column(Date, nullable=False)
    yarim_gun = Column(Boolean, nullable=False, default=False)
    #: Çalışma günü sayısı (talep anında hesaplanır, onayda yeniden).
    gun = Column(Float, nullable=False, default=0.0)
    #: beklemede | onaylandi | reddedildi | iptal
    durum = Column(String(12), nullable=False, default="beklemede", index=True)
    #: Personelin kısa notu (rapor türünde YOK).
    aciklama = Column(String(500), nullable=True)
    karar_notu = Column(String(500), nullable=True)
    karar_veren = Column(String(254), nullable=True)
    karar_at = Column(DateTime(timezone=True), nullable=True)
    #: panel | portal
    kaynak = Column(String(8), nullable=False, default="panel")
    talep_eden = Column(String(254), nullable=True)
    iptal_eden = Column(String(254), nullable=True)
    iptal_at = Column(DateTime(timezone=True), nullable=True)
    istek_kimligi = Column(String(40), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class IkVardiyaSablonlari(Base):
    __tablename__ = "ik_vardiya_sablonlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=True)
    ad = Column(String(60), nullable=False)
    #: "SS:DD" — bitiş başlangıçtan küçük/eşitse ertesi güne taşar (gece vardiyası).
    baslangic = Column(String(5), nullable=False)
    bitis = Column(String(5), nullable=False)
    mola_dk = Column(Integer, nullable=False, default=0)
    renk = Column(String(7), nullable=False, default="#7c3aed")
    aktif = Column(Boolean, nullable=False, default=True)
    sira = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class IkVardiyalar(Base):
    __tablename__ = "ik_vardiyalar"
    __table_args__ = (
        Index("ix_ik_vardiya_hesap_tarih", "hesap_email", "tarih"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    personel_id = Column(Integer, index=True, nullable=False)
    #: Vardiyanın başladığı gün (ızgaradaki sütun).
    tarih = Column(Date, nullable=False, index=True)
    #: Yerel saat (işyerinin saat dilimi; saat dilimsiz).
    bas = Column(DateTime(timezone=False), nullable=False)
    bit = Column(DateTime(timezone=False), nullable=False)
    mola_dk = Column(Integer, nullable=False, default=0)
    sablon_id = Column(Integer, nullable=True)
    #: taslak | yayinda
    durum = Column(String(8), nullable=False, default="taslak", index=True)
    #: Yayındayken değişti: bir sonraki "Yayınla"da personele yeniden bildirilir.
    degisti = Column(Boolean, nullable=False, default=False)
    notlar = Column(String(200), nullable=True)
    yayin_at = Column(DateTime(timezone=True), nullable=True)
    olusturan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class IkDosyalar(Base):
    __tablename__ = "ik_dosyalar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    personel_id = Column(Integer, index=True, nullable=False)
    ad = Column(String(120), nullable=False)
    tur = Column(String(120), nullable=False)
    boyut = Column(Integer, nullable=False, default=0)
    depo = Column(String(20), nullable=False, default="veritabani")
    depolama_anahtari = Column(String(80), unique=True, index=True, nullable=False)
    yukleyen = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
