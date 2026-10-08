"""Faz 6M — Ön muhasebe: kasa/banka/kredi kartı hesapları, gelir-gider, cari hesap, bütçe, nakit akışı.

e-Fatura / e-Arşiv ve banka entegrasyonu YOK (hesap/sözleşme gerektirir; sonraki faz). Tutarlar KURUŞ (tam
sayı; kayan nokta yok), her kayıtta para birimi var; çok para biriminde DÖNÜŞÜM YAPILMAZ — raporlar para
birimine göre ayrılır.

Kapsam
------
`kapsam`: ajansın kendi muhasebesi için `@ajans`, müşteride hesap e-postası. `hesap_email` ajans kaydında
BOŞ (NULL) — çöp kutusu / denetim "sahip" alanı. Benzersizlik kuralları `kapsam` üzerinden (NULL eşitsiz).

Tablolar
--------
* `muhasebe_ayarlari` — kapsam başına tek satır: firma adı (PDF başlığı), varsayılan para birimi, bütçe
  "yaklaştı" eşiği (%), otomatik aktarma ayarları (JSON; kaynak başına açık/kapalı + hedef hesap + başlangıç),
  son eşitlemenin özeti, CSV içe aktarmada son sütun eşlemesi.
* `muhasebe_hesaplari` — kasa | banka | kredi_karti | pos (POS / sanal POS bakiyesi). Bankada IBAN METİN olarak
  (yalnız biçim + mod-97 denetimi; uçlar yalnız son 4 haneyi maskeli döner); HESAP NUMARASI ve KART NUMARASI
  SAKLANMAZ — kartta yalnız ad + son 4 hane. Açılış bakiyesi.
* `muhasebe_kategorileri` — gelir / gider kategorileri. Varsayılan Türkçe set ilk açılışta tohumlanır
  (`anahtar` dolu; ad değiştirilebilir), kullanıcı yenisini ekler.
* `muhasebe_cariler` — müşteri / tedarikçi kartı; mevcut bir kayda (ajansta CRM adayı / müşteri hesabı; müşteride
  saha servisi müşterisi / POS alıcısı) `bagli_tur` + `bagli_id` ile bağlanabilir. Hukuk müvekkilleri BİLEREK yok
  (avukat–müvekkil sırrı). Açılış bakiyesi (artı = cari bize borçlu).
* `muhasebe_hareketleri` — defter: gelir | gider | tahsilat | odeme | virman. `tutar` KDV DAHİL, kuruş;
  normal kayıtta > 0, TERS KAYITTA eksi (storno: aslının eksisi, aynı tür/hesap/kategori). Hesaplı gelir/gider
  peşin, hesapsız (cari zorunlu) vadeli kayıttır. Otomatik yansıma: `kaynak` (odeme | fatura | pos | hukuk |
  saha) + `kaynak_ref` (kaynaktaki kimlik) + `kaynak_id` = "<ref>#<sürüm>" (ters kaydında "~ters" eki) —
  (kapsam, kaynak, kaynak_id) BENZERSİZ: aynı kaynak iki kez sayılmaz. `ters_kayit_id` (aslında, ters kaydına
  işaret) / `ters_edilen_id` (ters kayıtta, aslına işaret).
* `muhasebe_tekrarlar` — tekrarlayan gelir/gider (aylık kira vb.): zamanlı iş (`muhasebe_bakimi`) ya da panel
  açılışındaki eşitleme vadesi gelen dönemi kayda çevirir (kaynak `tekrar`, kaynak_id "<id>:<tarih>" benzersiz).
* `muhasebe_butceler` — gider kategorisi başına aylık bütçe (`ay` = "YYYY-AA" ya da "*" = her ay).
* `muhasebe_butce_asimlari` — aşım izi: (kapsam, kategori, ay, para birimi) başına BİR satır; satır eklenince
  `muhasebe.butce_asildi` olayı (webhook + otomasyon) bir kez yayınlanır.
* `muhasebe_ekleri` — hareketin belge ekleri (içerik `services/dosya_deposu`; çöp kutusu kalıcı silinince
  içerik de silinir).
* `muhasebe_oneriler` — ONAY bekleyen otomatik yansıma (kaynak ayarında "onay" açıksa; ödeme kaydı olmadan
  "ödendi" işaretlenen fatura her zaman): (kapsam, kaynak, kaynak_ref) BENZERSİZ. Onaylanınca deftere hareket
  yazılır (aynı kaynak kimliğiyle — iki kez sayılmaz) ve satır silinir; "yok say" → `yoksayildi` (kaynak değişirse,
  ör. tutar, yeniden `bekliyor`). Kaynak geçersizleşince satır silinir.
* `muhasebe_gecikme_izleri` — `muhasebe.alacak_gecikti` izi: (kapsam, cari, açık kalem, eşik) başına BİR satır.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, Date, DateTime, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class MuhasebeAyarlari(Base):
    __tablename__ = "muhasebe_ayarlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), unique=True, index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    firma_adi = Column(String(160), nullable=True)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    #: Bütçenin bu yüzdesine ulaşınca "yaklaştı" (yalnız arayüz); %100'ü geçince aşım (olay).
    uyari_yuzde = Column(Integer, nullable=False, default=80)
    #: JSON: {"odeme": {"acik", "baslangic", "banka_hesap_id", "nakit_hesap_id"}, "pos": {...}, ...}
    aktarim = Column(Text, nullable=True)
    #: JSON: son eşitlemenin sayıları (oluşturulan, ters, atlanan nedenleri).
    son_esitleme = Column(Text, nullable=True)
    son_esitleme_at = Column(DateTime(timezone=True), nullable=True)
    #: JSON: CSV içe aktarmada son kullanılan sütun eşlemesi (kolaylık).
    csv_esleme = Column(Text, nullable=True)
    kategoriler_tohumlandi = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class MuhasebeHesaplari(Base):
    __tablename__ = "muhasebe_hesaplari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    #: kasa | banka | kredi_karti
    tur = Column(String(12), nullable=False, default="kasa")
    ad = Column(String(120), nullable=False)
    banka_adi = Column(String(120), nullable=True)
    #: Yalnız bankada; boşluksuz büyük harf (biçim + mod-97 denetimi). Hesap numarası tutulmaz.
    iban = Column(String(34), nullable=True)
    #: Yalnız kredi kartında: son 4 hane (kart numarası TUTULMAZ).
    son4 = Column(String(4), nullable=True)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    #: Kuruş (kredi kartında borç eksi girilir).
    acilis_bakiyesi = Column(Integer, nullable=False, default=0)
    acilis_tarihi = Column(Date, nullable=True)
    arsiv = Column(Boolean, nullable=False, default=False)
    notlar = Column(Text, nullable=True)
    sira = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class MuhasebeKategorileri(Base):
    __tablename__ = "muhasebe_kategorileri"
    __table_args__ = (
        UniqueConstraint("kapsam", "tur", "ad", name="uq_muhasebe_kategori_ad"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    #: gelir | gider
    tur = Column(String(6), nullable=False)
    ad = Column(String(80), nullable=False)
    #: Varsayılan setten geliyorsa anahtarı (ön yüz adı çevirir; ad değiştirilmişse kullanıcının adı).
    anahtar = Column(String(40), nullable=True)
    renk = Column(String(7), nullable=True)
    arsiv = Column(Boolean, nullable=False, default=False)
    sira = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class MuhasebeCariler(Base):
    __tablename__ = "muhasebe_cariler"
    __table_args__ = (
        Index("ix_muhasebe_cariler_kapsam_ad", "kapsam", "ad"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    #: musteri | tedarikci | her_ikisi
    tur = Column(String(10), nullable=False, default="musteri")
    ad = Column(String(160), nullable=False)
    vergi_dairesi = Column(String(80), nullable=True)
    #: VKN (10) / TCKN (11) — yalnız rakam.
    vergi_no = Column(String(11), nullable=True)
    eposta = Column(String(254), nullable=True)
    telefon = Column(String(32), nullable=True)
    adres = Column(Text, nullable=True)
    notlar = Column(Text, nullable=True)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    #: Kuruş; artı = cari bize borçlu (alacağımız), eksi = biz cariye borçluyuz.
    acilis_bakiyesi = Column(Integer, nullable=False, default=0)
    acilis_tarihi = Column(Date, nullable=True)
    #: crm_aday | musteri_hesabi | saha_musteri | pos_alici | stok_tedarikci
    bagli_tur = Column(String(16), nullable=True)
    bagli_id = Column(String(254), nullable=True)
    arsiv = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class MuhasebeHareketleri(Base):
    __tablename__ = "muhasebe_hareketleri"
    __table_args__ = (
        UniqueConstraint("kapsam", "kaynak", "kaynak_id", name="uq_muhasebe_hareket_kaynak"),
        Index("ix_muhasebe_hareket_kapsam_tarih", "kapsam", "tarih"),
        Index("ix_muhasebe_hareket_kapsam_cari", "kapsam", "cari_id"),
        Index("ix_muhasebe_hareket_kapsam_ref", "kapsam", "kaynak", "kaynak_ref"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), nullable=False)
    hesap_email = Column(String(254), nullable=True)
    #: gelir | gider | tahsilat | odeme | virman
    tur = Column(String(8), nullable=False)
    tarih = Column(Date, nullable=False)
    #: Kuruş, KDV dahil. Ters kayıtta eksi.
    tutar = Column(Integer, nullable=False)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    kdv_orani = Column(Integer, nullable=True)
    kdv_tutari = Column(Integer, nullable=False, default=0)
    kategori_id = Column(Integer, nullable=True)
    #: Peşin gelir/gider, tahsilat/ödeme ve virmanın çıkış hesabı.
    hesap_id = Column(Integer, index=True, nullable=True)
    #: Virmanın giriş hesabı ve (para birimleri farklıysa) girişe yazılan tutar.
    hedef_hesap_id = Column(Integer, index=True, nullable=True)
    hedef_tutar = Column(Integer, nullable=True)
    cari_id = Column(Integer, nullable=True)
    vade_tarihi = Column(Date, nullable=True)
    aciklama = Column(String(300), nullable=True)
    belge_no = Column(String(60), nullable=True)
    #: JSON listesi (küçük harf).
    etiketler = Column(Text, nullable=True)
    #: manuel | tekrar | csv | odeme | fatura | pos | hukuk | saha
    kaynak = Column(String(10), nullable=False, default="manuel")
    kaynak_ref = Column(String(80), nullable=True)
    kaynak_id = Column(String(100), nullable=True)
    ters_kayit_id = Column(Integer, nullable=True)
    ters_edilen_id = Column(Integer, nullable=True)
    tekrar_id = Column(Integer, nullable=True)
    olusturan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class MuhasebeTekrarlar(Base):
    __tablename__ = "muhasebe_tekrarlar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    #: gelir | gider
    tur = Column(String(6), nullable=False, default="gider")
    aciklama = Column(String(300), nullable=False)
    tutar = Column(Integer, nullable=False)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    kdv_orani = Column(Integer, nullable=True)
    kategori_id = Column(Integer, nullable=True)
    hesap_id = Column(Integer, nullable=True)
    cari_id = Column(Integer, nullable=True)
    #: haftalik | aylik | uc_aylik | yillik
    periyot = Column(String(10), nullable=False, default="aylik")
    baslangic = Column(Date, nullable=False)
    bitis = Column(Date, nullable=True)
    #: Bir sonraki üretilecek dönem tarihi (NULL = bitti).
    sonraki = Column(Date, nullable=True)
    son_uretilen = Column(Date, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    etiketler = Column(Text, nullable=True)
    olusturan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class MuhasebeButceler(Base):
    __tablename__ = "muhasebe_butceler"
    __table_args__ = (
        UniqueConstraint("kapsam", "kategori_id", "ay", "para_birimi", name="uq_muhasebe_butce"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    kategori_id = Column(Integer, nullable=False)
    #: "YYYY-AA" ya da "*" (her ay; ayın kendi satırı varsa o geçerli).
    ay = Column(String(7), nullable=False, default="*")
    tutar = Column(Integer, nullable=False)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class MuhasebeButceAsimlari(Base):
    __tablename__ = "muhasebe_butce_asimlari"
    __table_args__ = (
        UniqueConstraint("kapsam", "kategori_id", "ay", "para_birimi", name="uq_muhasebe_butce_asim"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    kategori_id = Column(Integer, nullable=False)
    ay = Column(String(7), nullable=False)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    butce = Column(Integer, nullable=False)
    gerceklesen = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class MuhasebeEkleri(Base):
    __tablename__ = "muhasebe_ekleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    hareket_id = Column(Integer, index=True, nullable=False)
    ad = Column(String(120), nullable=False)
    tur = Column(String(100), nullable=False)
    boyut = Column(Integer, nullable=False, default=0)
    depo = Column(String(16), nullable=False)
    depolama_anahtari = Column(String(200), nullable=False)
    yukleyen = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class MuhasebeOneriler(Base):
    __tablename__ = "muhasebe_oneriler"
    __table_args__ = (
        UniqueConstraint("kapsam", "kaynak", "kaynak_ref", name="uq_muhasebe_oneri_kaynak"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    #: odeme | fatura | pos | hukuk | saha
    kaynak = Column(String(10), nullable=False)
    kaynak_ref = Column(String(80), nullable=False)
    #: bekliyor | yoksayildi
    durum = Column(String(12), nullable=False, default="bekliyor")
    #: Önerilen kaydın özeti (tür|tutar|para birimi|KDV) — değişirse yok sayılan öneri yeniden açılır.
    parmak_izi = Column(String(80), nullable=False)
    #: JSON: tur, tarih, tutar, para_birimi, kdv_orani, kdv_tutari, hesap_id, cari_id, kategori (anahtar),
    #: aciklama, belge_no, vade.
    veri = Column(Text, nullable=False)
    tarih = Column(Date, nullable=False)
    tutar = Column(Integer, nullable=False)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    karar_veren = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class MuhasebeGecikmeIzleri(Base):
    __tablename__ = "muhasebe_gecikme_izleri"
    __table_args__ = (
        UniqueConstraint("kapsam", "cari_id", "hareket_id", "esik", name="uq_muhasebe_gecikme"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    cari_id = Column(Integer, nullable=False)
    #: Açık kalemin hareketi (0 = carinin açılış bakiyesi).
    hareket_id = Column(Integer, nullable=False)
    esik = Column(Integer, nullable=False)
    gun = Column(Integer, nullable=False)
    vade = Column(Date, nullable=False)
    tutar = Column(Integer, nullable=False)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
