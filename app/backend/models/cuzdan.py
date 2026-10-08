"""Faz 5C — Cüzdan ve bakiye (müşteri avansı).

Müşteri ajansa avans (ön ödeme) yatırır; faturalar bu bakiyeden tamamen ya da kısmen ödenir. Bakiye yalnız ajansın
kendi hizmetlerinin bedeli için verilmiş avanstır: üçüncü kişilere ödeme aracı ya da elektronik para DEĞİLDİR, faiz
işlemez, devredilemez; kullanılmayan bakiye talep üzerine ajans tarafından elle iade edilir.

Tutarlar KURUŞ (tam sayı; ön muhasebe ile aynı). Fatura tarafı Decimal — dönüşüm tek yerde: `services/cuzdan.py`
`kurusa` / `ondaliga`. Para birimi dönüşümü YOK: hesap × para birimi başına ayrı bakiye.

Tablolar
--------
* `cuzdan_hesaplari` — (hesap, para birimi) başına BİR satır: güncel bakiye (asla eksi değil: CHECK + koşullu
  güncelleme), düşük bakiye eşiği ve "uyarı gönderildi" işareti (eşik altına inişte BİR kez; eşik üstüne çıkınca
  sıfırlanır).
* `cuzdan_hareketleri` — defter. Satırlar DEĞİŞTİRİLMEZ, silinmez; hata yalnız ters kayıtla düzeltilir. `tutar`
  işaretli (artı: bakiye artar), `sonra` = hareket sonrası bakiye. Türler: yukleme | harcama (fatura) | iade
  (müşteriye geri ödeme) | duzeltme (yönetici, gerekçe zorunlu) | ters_kayit. `tekil` benzersiz: aynı istek
  (idempotent anahtar), aynı talebin onayı, aynı satırın tersi iki kez yazılamaz.
* `cuzdan_yukleme_talepleri` — müşterinin "Bakiye yükle" bildirimi (havale/EFT/nakit + dekont): beklemede →
  onaylandi (deftere yukleme) | reddedildi (neden) | iptal (müşteri vazgeçti). Gelen kutusu kaynağı `bakiye_yukleme`.
* `cuzdan_ayarlari` — hesap başına: açıklama (referans) kodu, otomatik ödeme (açarken onay metni + sürüm + zaman),
  yetersiz bakiyede kısmi uygulama, zamanlama (kesilince | vadesinde).
* `cuzdan_otomatik_izleri` — otomatik ödeme denemesi fatura başına BİR kez (benzersiz).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


HAREKET_TURLERI = ("yukleme", "harcama", "iade", "duzeltme", "ters_kayit")
TALEP_DURUMLARI = ("beklemede", "onaylandi", "reddedildi", "iptal")


class CuzdanHesaplari(Base):
    __tablename__ = "cuzdan_hesaplari"
    __table_args__ = (
        UniqueConstraint("hesap_email", "para_birimi", name="uq_cuzdan_hesap_pb"),
        CheckConstraint("bakiye >= 0", name="ck_cuzdan_bakiye_eksi_degil"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Müşteri hesabı (etkin hesabın sahibi; küçük harf).
    hesap_email = Column(String(254), nullable=False, index=True)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    #: Kuruş, eksi olamaz.
    bakiye = Column(BigInteger, nullable=False, default=0)
    #: Her bakiye değişiminde +1 (iyimser kilit / iz).
    surum = Column(Integer, nullable=False, default=0)
    #: Düşük bakiye eşiği (kuruş); boş = uyarı kapalı.
    dusuk_esik = Column(BigInteger, nullable=True)
    #: Eşik altına inişte bir kez yazılır; bakiye eşiğe ya da üstüne çıkınca silinir (yeniden kurulur).
    dusuk_uyari_at = Column(DateTime(timezone=True), nullable=True)
    son_hareket_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class CuzdanHareketleri(Base):
    __tablename__ = "cuzdan_hareketleri"
    __table_args__ = (
        Index("ix_cuzdan_hareket_hesap", "hesap_email", "para_birimi", "id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    cuzdan_id = Column(Integer, nullable=False, index=True)
    hesap_email = Column(String(254), nullable=False)
    para_birimi = Column(String(3), nullable=False)
    #: yukleme | harcama | iade | duzeltme | ters_kayit
    tur = Column(String(12), nullable=False, index=True)
    #: Kuruş, işaretli (artı: bakiye artar).
    tutar = Column(BigInteger, nullable=False)
    #: Hareket sonrası bakiye (kuruş).
    sonra = Column(BigInteger, nullable=False)
    #: İşlemin (paranın) tarihi — müşterinin/yöneticinin bildirdiği gün; defter sırası `id`.
    tarih = Column(Date, nullable=False)
    #: havale | eft | nakit | diger (yükleme/iade); harcamada "bakiye".
    yontem = Column(String(12), nullable=True)
    fatura_id = Column(Integer, nullable=True, index=True)
    #: Harcamanın / bakiyeye iadenin `payments` satırı.
    odeme_id = Column(Integer, nullable=True, index=True)
    talep_id = Column(Integer, nullable=True, index=True)
    #: Ters kaydın aslı.
    bagli_id = Column(Integer, nullable=True, index=True)
    dekont_dosya_id = Column(Integer, nullable=True)
    notu = Column(Text, nullable=True)
    #: Düzeltme ve ters kayıtta zorunlu.
    gerekce = Column(Text, nullable=True)
    yazan = Column(String(254), nullable=True)
    #: admin | musteri | sistem
    yazan_rol = Column(String(10), nullable=False, default="admin")
    #: Benzersiz iş anahtarı (idempotent istek, talep onayı, ters kayıt, ödeme silme…); boş olabilir.
    tekil = Column(String(160), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)


class CuzdanYuklemeTalepleri(Base):
    __tablename__ = "cuzdan_yukleme_talepleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), nullable=False, index=True)
    #: Talebi gönderen kişi (ekip üyesi olabilir).
    kisi_email = Column(String(254), nullable=True)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    #: Müşterinin bildirdiği tutar (kuruş).
    tutar = Column(BigInteger, nullable=False)
    #: havale | eft | nakit | diger
    yontem = Column(String(12), nullable=False, default="havale")
    #: Müşterinin bildirdiği ödeme günü.
    odeme_tarihi = Column(Date, nullable=True)
    #: Açıklama (referans) kodu — talep anındaki.
    referans = Column(String(24), nullable=True)
    dekont_dosya_id = Column(Integer, nullable=True)
    notu = Column(Text, nullable=True)
    #: beklemede | onaylandi | reddedildi | iptal
    durum = Column(String(12), nullable=False, default="beklemede", index=True)
    karar_veren = Column(String(254), nullable=True)
    karar_at = Column(DateTime(timezone=True), nullable=True)
    ret_nedeni = Column(Text, nullable=True)
    #: Onayda yazılan yükleme hareketi (onaylanan tutar talepten farklı olabilir).
    hareket_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)


class CuzdanAyarlari(Base):
    __tablename__ = "cuzdan_ayarlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), nullable=False, unique=True, index=True)
    #: Havale açıklamasına yazılacak, hesaba özgü kısa kod (ör. BKY-7KQ2M9).
    referans = Column(String(24), nullable=False, unique=True)
    otomatik_odeme = Column(Boolean, nullable=False, default=False)
    #: Yetersiz bakiyede: True → olan kadarını uygula, False → hiç uygulama (bildir).
    otomatik_kismi = Column(Boolean, nullable=False, default=False)
    #: kesilince | vadesinde
    otomatik_zaman = Column(String(10), nullable=False, default="kesilince")
    #: Açılış anı (gösterim) ve o anki en büyük fatura kimliği: yalnız bundan SONRA kesilen faturalar (kimliği büyük
    #: olanlar) otomatik ödenir ("yeni faturalarım") — saat dilimi/saat farkından bağımsız.
    otomatik_baslangic = Column(DateTime(timezone=True), nullable=True)
    otomatik_son_fatura_id = Column(Integer, nullable=True)
    onay_metni_surumu = Column(String(16), nullable=True)
    onaylayan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class CuzdanOtomatikIzleri(Base):
    __tablename__ = "cuzdan_otomatik_izleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    fatura_id = Column(Integer, nullable=False, unique=True)
    hesap_email = Column(String(254), nullable=False, index=True)
    #: odendi | kismi | yetersiz | hata
    sonuc = Column(String(10), nullable=False)
    #: Uygulanan tutar (kuruş).
    tutar = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
