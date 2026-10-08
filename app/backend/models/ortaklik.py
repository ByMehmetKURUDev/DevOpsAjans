"""Faz 5K — indirim kodları ve ortaklık (referans) programı.

PARA AKTARIMI YOK: komisyon ödemesini yönetici kendi bankasından elle yapar,
panelde "ödendi" işaretler (dekont eki + ortağa e-posta). Kart numarası hiç
tutulmaz; IBAN yalnız biçimi denetlenen bir metin.

Hesap bazlı (ileride müşteriye açılabilir)
------------------------------------------
Bugün yalnız ajansın KENDİ programı var ve modül vitrininde satılmıyor. Yine de
her program kaydı bir `hesap` sütunu taşır: "" (`AJANS`) = ajansın programı;
ileride bir müşteri kendi ortaklık programını açarsa onun hesap e-postası.
Benzersizlikler hesap başına (aynı kod / aynı ortak e-postası iki programda
ayrı kayıt olabilir); servis katmanı bugün her sorguyu `AJANS`a daraltır.
Kullanım, tıklama satırları kod / ortak kimliğiyle zaten programa bağlı.

Tablolar
--------
* `indirim_kodlari` — ajansın kendi satışları için kod: yüzde | sabit tutar
  (KDV HARİÇ tutar üzerinden), geçerlilik günleri, toplam ve kişi başı
  kullanım sınırı, en az tutar (KDV hariç ara toplam), kapsam (teklif /
  fatura / hizmet paketi), geçerli paketler (ölçek kodları; boş = hepsi),
  isteğe bağlı ortak. `kod_anahtar` büyük/küçük
  harf ve Türkçe İ/ı farkı katlanmış biçim (benzersiz; ortak kodlarıyla aynı
  ad alanında — formdaki tek alan ikisini de kabul ediyor).
* `indirim_kodu_kullanimlari` — kodun uygulandığı belge (teklif ya da
  fatura; belge başına tek satır). Sayım "canlı" belgeden: reddedilmiş /
  süresi dolmuş teklif, iptal edilmiş fatura sayılmaz (`services/indirim_kodlari`).
* `ortaklar` — başvuru ve onaylı ortak tek satır (kişi e-postası benzersiz).
  Durum: beklemede → onaylandi | reddedildi; onaylıda askida. Oran boşsa
  program ayarındaki varsayılan. Program koşullarının kabul anı + metin
  sürümü; pazarlama izni ayrı (Faz 4G deseni).
* `ortak_tiklamalari` — ortak başına GÜNLÜK toplam tıklama (kişi verisi yok:
  IP, çerez kimliği, tarayıcı yok).
* `ortak_referanslari` — müşteri (e-posta) → ortak atfı; müşteri başına TEK
  satır. Kural ayardan: ilk (varsayılan) ya da son referans geçerli.
* `ortak_komisyonlari` — defter: komisyon (+) ve ters kayıt (−). `tekil`
  benzersiz: aynı fatura için ikinci komisyon, aynı iade için ikinci ters
  kayıt yazılamaz. Kural: ilk satış (oran X) | tekrar (abonelik, N ay, oran Y).
  Durum: beklemede (iade süresi) → onaylandi → odeme_talebinde → odendi; iptal.
* `ortak_odeme_talepleri` — ortağın talebi (onaylı bakiyenin tamamı, para
  birimi başına): bekliyor → odendi (dekont) | reddedildi (kayıtlar bakiyeye döner).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, Text, UniqueConstraint


#: Ajansın kendi programının `hesap` değeri.
AJANS = ""


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class IndirimKodlari(Base):
    __tablename__ = "indirim_kodlari"
    __table_args__ = (
        UniqueConstraint("hesap", "kod_anahtar", name="uq_indirim_kodu_hesap_anahtar"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Programın sahibi ("" = ajans).
    hesap = Column(String(254), nullable=False, default=AJANS, index=True)
    #: Görünen biçim (Türkçe büyük harf).
    kod = Column(String(40), nullable=False)
    #: Karşılaştırma anahtarı (`services/indirim_kodlari.kod_anahtari`); hesap başına benzersiz.
    kod_anahtar = Column(String(40), index=True, nullable=False)
    aciklama = Column(String(300), nullable=True)
    #: yuzde | sabit
    tur = Column(String(10), nullable=False, default="yuzde")
    #: Yüzde (0–100] ya da sabit tutar (KDV hariç).
    deger = Column(Float, nullable=False)
    #: Sabit tutarın ve en az tutarın para birimi (yüzdede ve en az tutar yoksa boş = her para birimi).
    para_birimi = Column(String(3), nullable=True)
    #: YYYY-MM-DD (dahil); boş = sınırsız.
    baslangic = Column(String(10), nullable=True)
    bitis = Column(String(10), nullable=True)
    toplam_sinir = Column(Integer, nullable=True)
    kisi_basi_sinir = Column(Integer, nullable=True)
    #: KDV hariç ara toplam alt sınırı (para birimi `para_birimi`).
    en_az_tutar = Column(Float, nullable=True)
    #: JSON listesi: teklif | fatura | paket
    kapsam = Column(Text, nullable=True)
    #: JSON listesi: geçerli olduğu hizmet paketleri (fiyatlandırma ölçeği ALFA/BETA/…, KREDI, AI_PM); boş = hepsi.
    #: Doluysa kod yalnız bu paketin "Teklif al" talebinden açılan teklife / faturaya uygulanır.
    paketler = Column(Text, nullable=True)
    ortak_id = Column(Integer, index=True, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    olusturan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class IndirimKoduKullanimlari(Base):
    __tablename__ = "indirim_kodu_kullanimlari"
    __table_args__ = (
        UniqueConstraint("belge_turu", "belge_id", name="uq_indirim_kullanim_belge"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kod_id = Column(Integer, index=True, nullable=False)
    #: teklif | fatura
    belge_turu = Column(String(10), nullable=False)
    belge_id = Column(Integer, nullable=False)
    #: Alıcı (küçük harf) — kişi başı sınır bununla sayılır.
    eposta = Column(String(254), index=True, nullable=True)
    #: Uygulanan indirim (KDV hariç) ve para birimi.
    tutar = Column(Float, nullable=False, default=0)
    para_birimi = Column(String(3), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class Ortaklar(Base):
    __tablename__ = "ortaklar"
    __table_args__ = (
        UniqueConstraint("hesap", "eposta", name="uq_ortak_hesap_eposta"),
        UniqueConstraint("hesap", "kod_anahtar", name="uq_ortak_hesap_kod"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Programın sahibi ("" = ajans).
    hesap = Column(String(254), nullable=False, default=AJANS, index=True)
    #: Kişinin e-postası (küçük harf) — panele bu adresli kullanıcı hesabıyla girer; program başına benzersiz.
    eposta = Column(String(254), index=True, nullable=False)
    ad = Column(String(120), nullable=False)
    #: Web sitesi / sosyal medya adresi.
    web = Column(String(300), nullable=True)
    #: Nasıl tanıtacağı (başvuru metni).
    tanitim = Column(Text, nullable=True)
    #: Referans kodu (görünen) ve anahtarı (indirim kodlarıyla aynı ad alanı).
    kod = Column(String(40), nullable=True)
    kod_anahtar = Column(String(40), index=True, nullable=True)
    #: beklemede | onaylandi | reddedildi | askida
    durum = Column(String(12), index=True, nullable=False, default="beklemede")
    #: Komisyon yüzdesi; boş = program varsayılanı.
    oran = Column(Float, nullable=True)
    #: Ödeme bilgisi — yalnız biçimi denetlenen metin (kart numarası YOK).
    iban = Column(String(40), nullable=True)
    iban_ad = Column(String(120), nullable=True)
    notlar = Column(Text, nullable=True)
    ret_nedeni = Column(String(500), nullable=True)
    #: Şüpheli işaretleri (JSON listesi; yöneticiye gösterilir).
    supheli = Column(Text, nullable=True)
    dil = Column(String(5), nullable=True)
    kosullar_kabul_at = Column(DateTime(timezone=True), nullable=True)
    kosullar_surumu = Column(String(40), nullable=True)
    pazarlama_izni_at = Column(DateTime(timezone=True), nullable=True)
    pazarlama_metin_surumu = Column(String(40), nullable=True)
    basvuru_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    karar_at = Column(DateTime(timezone=True), nullable=True)
    karar_veren = Column(String(254), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class OrtakTiklamalari(Base):
    __tablename__ = "ortak_tiklamalari"
    __table_args__ = (
        UniqueConstraint("ortak_id", "gun", name="uq_ortak_tiklama_gun"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    ortak_id = Column(Integer, index=True, nullable=False)
    #: YYYY-MM-DD (İstanbul günü)
    gun = Column(String(10), nullable=False)
    sayi = Column(Integer, nullable=False, default=0)


class OrtakReferanslari(Base):
    __tablename__ = "ortak_referanslari"
    __table_args__ = (
        UniqueConstraint("hesap", "musteri_eposta", name="uq_ortak_referans_hesap_musteri"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Programın sahibi ("" = ajans).
    hesap = Column(String(254), nullable=False, default=AJANS, index=True)
    #: Müşteri / aday e-postası (küçük harf) — program başına müşteri başına tek atıf.
    musteri_eposta = Column(String(254), index=True, nullable=False)
    ortak_id = Column(Integer, index=True, nullable=False)
    #: form | fiyat | kod | elle
    kaynak = Column(String(20), nullable=False)
    aday_id = Column(Integer, nullable=True)
    ilk_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    son_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class OrtakKomisyonlari(Base):
    __tablename__ = "ortak_komisyonlari"
    __table_args__ = (
        Index("ix_ortak_komisyon_ortak_durum", "ortak_id", "durum"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Programın sahibi ("" = ajans) — ortağınkiyle aynı.
    hesap = Column(String(254), nullable=False, default=AJANS, index=True)
    ortak_id = Column(Integer, nullable=False)
    #: komisyon | ters
    tur = Column(String(10), nullable=False, default="komisyon")
    #: Komisyonun dayandığı kural: ilk (ilk satış; aynı teklifin peşinat/kalan faturaları da) | tekrar
    #: (ilk satıştan sonra N ay içinde ödenen tekrarlayan / abonelik faturası). Ters kayıtta aslınınki.
    kural = Column(String(10), nullable=False, default="ilk")
    #: Satışın teklifi (varsa) — aynı teklifin sonraki faturası "ilk satış"ın parçası sayılır.
    teklif_id = Column(Integer, nullable=True)
    #: Tekillik anahtarı: "k:<fatura>" | "t:<fatura>:iade:<iade faturası>" | "t:<fatura>:durum"
    tekil = Column(String(80), unique=True, nullable=False)
    fatura_id = Column(Integer, index=True, nullable=True)
    fatura_no = Column(String(80), nullable=True)
    #: Ters kaydın bağlı olduğu komisyon.
    bagli_id = Column(Integer, nullable=True)
    musteri_eposta = Column(String(254), nullable=True)
    #: KDV hariç tutar (komisyon tabanı) ve uygulanan oran.
    matrah = Column(Float, nullable=False, default=0)
    oran = Column(Float, nullable=False, default=0)
    #: İşaretli tutar (ters kayıtta eksi).
    tutar = Column(Float, nullable=False)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    #: beklemede | onaylandi | odeme_talebinde | odendi | iptal
    durum = Column(String(16), index=True, nullable=False, default="beklemede")
    bekleme_bitis = Column(DateTime(timezone=True), nullable=True)
    odeme_talebi_id = Column(Integer, index=True, nullable=True)
    #: Şüpheli işaretleri (JSON listesi).
    supheli = Column(Text, nullable=True)
    notu = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class OrtakOdemeTalepleri(Base):
    __tablename__ = "ortak_odeme_talepleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Programın sahibi ("" = ajans) — ortağınkiyle aynı.
    hesap = Column(String(254), nullable=False, default=AJANS, index=True)
    ortak_id = Column(Integer, index=True, nullable=False)
    tutar = Column(Float, nullable=False)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    #: Talep anındaki ödeme bilgisi (sonradan değişse de bu talep bununla ödenir).
    iban = Column(String(40), nullable=True)
    iban_ad = Column(String(120), nullable=True)
    #: bekliyor | odendi | reddedildi
    durum = Column(String(12), index=True, nullable=False, default="bekliyor")
    notu = Column(String(500), nullable=True)
    ret_nedeni = Column(String(500), nullable=True)
    dekont_dosya_id = Column(Integer, nullable=True)
    odeyen = Column(String(254), nullable=True)
    odendi_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)
