"""Faz 6H — hukuk bürosu: müvekkil, dosya, takvim/süre, zaman, masraf, ek, müvekkil portalı.

Tablolar (hepsi `hesap_email` = büronun müşteri hesabı; ajansın kendi kaydı YOK — modül yalnız
müşteri hesabında kullanılıyor, ajans yöneticisi yalnız META VERİ görür):

* `hukuk_ayarlari`       — hesap başına: büro adı (PDF başlığı), hatırlatma eşikleri, sabah saati,
                            adli tatil aralığı/uzatması (HMK m.104), sabit tatillerin tohumlandığı işareti.
* `hukuk_tatilleri`      — resmî tatiller: sabit ulusal günler (2429 s. Kanun; yıllık tekrar) tohumlanır,
                            dini bayramlar her yıl kullanıcı tarafından eklenir (tarih aralığı, yarım gün).
* `hukuk_muvekkilleri`   — kişi/şirket, iletişim, vergi/kimlik no (çıkar çatışması kontrolü), isteğe bağlı
                            kaynak (büronun randevu kaydı); portal bağlantısı sürümü (yenile/iptal).
* `hukuk_dosyalari`      — tür, esas/dosya no, mahkeme/icra dairesi (serbest metin), karşı taraflar ve
                            vekilleri (JSON), konu, durum, sorumlu avukat, etiketler, açılış/kapanış,
                            notlar, `gizli` (yalnız hesap sahibi + sorumlu avukat), portal alanları.
* `hukuk_olaylari`       — duruşma, keşif, bilirkişi, kesin süre (son gün), görev; süre hesaplayıcının
                            girdisi (`hesap` JSON) saklanır.
* `hukuk_hatirlatmalari` — (olay, eşik) başına BİR satır: hatırlatma bir kez gider (benzersiz kısıt).
* `hukuk_zaman_kayitlari`, `hukuk_masraflari` — dosyaya saat kaydı ve masraf (tutar kuruş, avanstan mı,
                            makbuz eki). Tahsilat/ödeme YOK.
* `hukuk_ekleri`         — dosya eki (içerik `services/dosya_deposu`) ya da Belgeler (5B) kaydına bağlantı;
                            `muvekkile_gorunur` ile portalda paylaşılır.
* `hukuk_mesajlari`      — müvekkil portalından gelen mesaj ve büronun yanıtı (ajansın gelen kutusuna DÜŞMEZ).

Silme: müvekkil ve dosya önce "silinenler"e düşer (`silindi_at`; modül içinden geri alınır,
`hukuk_bakimi` 30 gün sonra kalıcı siler). Paylaşılan çöp kutusu KULLANILMIYOR: ajans yöneticisi çöp
kutusundaki kaydın tam kopyasını görebildiği için avukat–müvekkil sırrı oraya kopyalanmaz.
Denetim kaydı bütün değişikliklerde yazılıyor; bu tablolarda alan DEĞERLERİ maskeli (yalnız alan adları).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class HukukAyarlari(Base):
    __tablename__ = "hukuk_ayarlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), unique=True, index=True, nullable=False)
    buro_adi = Column(String(160), nullable=True)
    #: JSON liste: kaç gün önce hatırlatılsın (0 = aynı gün sabah). Varsayılan [7, 3, 1, 0].
    hatirlatma_gunleri = Column(String(60), nullable=True)
    #: Aynı gün hatırlatmasının en erken saati (yerel, "HH:MM").
    sabah_saati = Column(String(5), nullable=False, default="08:00")
    #: Adli tatil (HMK m.102: 20 Temmuz – 31 Ağustos) ve uzatma (HMK m.104: bir hafta) — ayarlanabilir.
    adli_tatil_bas = Column(String(5), nullable=False, default="07-20")
    adli_tatil_bit = Column(String(5), nullable=False, default="08-31")
    adli_tatil_uzatma_gun = Column(Integer, nullable=False, default=7)
    #: Süre hesaplayıcıda "adli tatil" seçeneğinin varsayılanı.
    adli_tatil_varsayilan = Column(Boolean, nullable=False, default=True)
    tatiller_tohumlandi = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class HukukTatilleri(Base):
    __tablename__ = "hukuk_tatilleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    ad = Column(String(120), nullable=False)
    tarih = Column(Date, nullable=False)
    #: Çok günlü tatil (bayram) için son gün; tek günde boş.
    bitis = Column(Date, nullable=True)
    #: Her yıl aynı ay-gün (sabit ulusal günler); yıl yok sayılır.
    tekrar = Column(Boolean, nullable=False, default=False)
    #: Yarım gün (arife, 28 Ekim öğleden sonra): süreyi UZATMAZ, yalnız uyarı verir.
    yarim = Column(Boolean, nullable=False, default=False)
    #: sabit | dini | diger
    tur = Column(String(10), nullable=False, default="diger")
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class HukukMuvekkilleri(Base):
    __tablename__ = "hukuk_muvekkilleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    #: kisi | sirket
    tur = Column(String(8), nullable=False, default="kisi")
    ad = Column(String(200), nullable=False)
    #: Şirkette yetkili kişi.
    yetkili = Column(String(160), nullable=True)
    vergi_no = Column(String(20), nullable=True)
    eposta = Column(String(254), nullable=True)
    telefon = Column(String(20), nullable=True)
    adres = Column(Text, nullable=True)
    notlar = Column(Text, nullable=True)
    #: Çıkar çatışması araması için normalize ad (Türkçe harf + büyük/küçük; şirket ekleri atılmış).
    ad_normal = Column(String(220), index=True, nullable=True)
    #: elle | randevu
    kaynak = Column(String(10), nullable=False, default="elle")
    kaynak_id = Column(Integer, nullable=True)
    portal_acik = Column(Boolean, nullable=False, default=False)
    portal_surum = Column(Integer, nullable=False, default=0)
    portal_olusturma_at = Column(DateTime(timezone=True), nullable=True)
    portal_son_at = Column(DateTime(timezone=True), nullable=True)
    olusturan = Column(String(254), nullable=True)
    silindi_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class HukukDosyalari(Base):
    __tablename__ = "hukuk_dosyalari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    muvekkil_id = Column(Integer, index=True, nullable=False)
    #: dava | icra | arabuluculuk | danismanlik | sozlesme | diger
    tur = Column(String(14), nullable=False, default="dava")
    #: Büronun iç dosya no'su ve esas no (mahkeme/icra dosya numarası).
    dosya_no = Column(String(60), nullable=True)
    esas_no = Column(String(60), nullable=True)
    mahkeme = Column(String(200), nullable=True)
    #: JSON: [{"ad", "vergi_no", "vekil"}]
    karsi_taraflar = Column(Text, nullable=True)
    konu = Column(String(300), nullable=True)
    #: acik | beklemede | kapandi
    durum = Column(String(10), nullable=False, default="acik", index=True)
    sorumlu_email = Column(String(254), nullable=True, index=True)
    etiketler = Column(Text, nullable=True)
    acilis_tarihi = Column(Date, nullable=True)
    kapanis_tarihi = Column(Date, nullable=True)
    notlar = Column(Text, nullable=True)
    #: Yalnız hesap sahibi ve sorumlu avukat görür.
    gizli = Column(Boolean, nullable=False, default=False)
    #: Müvekkil portalında görünsün mü + hangi alanlar (JSON {"konu","durum","durusma","belgeler","masraf","not"}).
    portal_acik = Column(Boolean, nullable=False, default=False)
    portal_alanlari = Column(Text, nullable=True)
    #: Portalda "not" alanı açıksa müvekkile görünen kısa açıklama.
    muvekkil_notu = Column(Text, nullable=True)
    olusturan = Column(String(254), nullable=True)
    silindi_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class HukukOlaylari(Base):
    __tablename__ = "hukuk_olaylari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    #: Genel görevde boş olabilir.
    dosya_id = Column(Integer, index=True, nullable=True)
    #: durusma | kesif | bilirkisi | kesin_sure | gorev
    tur = Column(String(12), nullable=False, default="durusma")
    baslik = Column(String(200), nullable=True)
    tarih = Column(Date, nullable=False, index=True)
    #: Yerel saat "HH:MM" (kesin süre ve görevde boş olabilir).
    saat = Column(String(5), nullable=True)
    yer = Column(String(200), nullable=True)
    notlar = Column(Text, nullable=True)
    sorumlu_email = Column(String(254), nullable=True, index=True)
    tamamlandi_at = Column(DateTime(timezone=True), nullable=True)
    #: Süre hesaplayıcının girdisi ve adımları (JSON) — kesin sürede.
    hesap = Column(Text, nullable=True)
    olusturan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class HukukHatirlatmalari(Base):
    __tablename__ = "hukuk_hatirlatmalari"
    __table_args__ = (
        UniqueConstraint("olay_id", "esik", name="uq_hukuk_hatirlatma_olay_esik"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    olay_id = Column(Integer, index=True, nullable=False)
    #: Gün eşiği (7, 3, 1, 0). Daha küçük bir eşik gönderilince büyükler de "geçildi" yazılır.
    esik = Column(Integer, nullable=False)
    #: gonderildi | gecildi
    durum = Column(String(10), nullable=False, default="gonderildi")
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class HukukZamanKayitlari(Base):
    __tablename__ = "hukuk_zaman_kayitlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    dosya_id = Column(Integer, index=True, nullable=False)
    tarih = Column(Date, nullable=False)
    sure_dk = Column(Integer, nullable=False)
    aciklama = Column(String(500), nullable=True)
    faturalanabilir = Column(Boolean, nullable=False, default=True)
    kisi_email = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class HukukMasraflari(Base):
    __tablename__ = "hukuk_masraflari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    dosya_id = Column(Integer, index=True, nullable=False)
    #: harc | tebligat | bilirkisi | yol | diger
    tur = Column(String(10), nullable=False, default="diger")
    #: Kuruş (tam sayı; kayan nokta yok).
    tutar_kurus = Column(Integer, nullable=False)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    tarih = Column(Date, nullable=False)
    aciklama = Column(String(300), nullable=True)
    #: Müvekkilin verdiği avanstan mı karşılandı?
    avanstan = Column(Boolean, nullable=False, default=False)
    makbuz_ek_id = Column(Integer, nullable=True)
    kisi_email = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class HukukEkleri(Base):
    __tablename__ = "hukuk_ekleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    dosya_id = Column(Integer, index=True, nullable=False)
    #: belge (dosya eki) | makbuz (masraf makbuzu) | baglanti (Belgeler kaydına bağlantı)
    tip = Column(String(10), nullable=False, default="belge")
    ad = Column(String(200), nullable=False)
    tur = Column(String(120), nullable=True)
    boyut = Column(Integer, nullable=False, default=0)
    depo = Column(String(12), nullable=True)
    anahtar = Column(String(200), nullable=True)
    #: Belgeler (5B) kaydı — `tip=baglanti`.
    belge_id = Column(Integer, nullable=True)
    muvekkile_gorunur = Column(Boolean, nullable=False, default=False)
    yukleyen = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class HukukMesajlari(Base):
    __tablename__ = "hukuk_mesajlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    muvekkil_id = Column(Integer, index=True, nullable=False)
    dosya_id = Column(Integer, nullable=True)
    #: muvekkil (portaldan) | buro (paneldeki yanıt)
    yon = Column(String(8), nullable=False, default="muvekkil")
    metin = Column(Text, nullable=False)
    yazan = Column(String(254), nullable=True)
    okundu_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)
