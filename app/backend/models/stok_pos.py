"""Faz 6P — Stok ve satış noktası (POS): kafe, butik, küçük market, kuaför ürün satışı.

Kim kimdir?
-----------
Modülü ajansın MÜŞTERİSİ (ör. bir kafe) kendi işi için kullanır: müşteri hesabı (`hesap_email`) =
işletme; kasiyerler = hesap ekibi üyeleri (`kasa` izni: yalnız satış ekranı), stok sorumlusu =
`stok` izni (ürün, hareket, sayım, rapor, ayar). Ajans yöneticisi salt okunur destek görünümü alır.

Ürün kataloğu neden ayrı tablo (QR menü ürünleri yerine)?
-------------------------------------------------------
QR menü ürünleri (`menu_urunleri`) bir MAĞAZAYA (herkese açık `/menu/<slug>`) ve zorunlu bir
kategoriye bağlı; fiyat farkı taşıyan seçenek grupları stok tutmuyor. POS ise QR menüsü kapalı bir
butikte de çalışmalı, şube başına stok ve beden/renk varyantının kendi barkodunu/stokunu tutmalı.
Bu yüzden ürün kaydı hesaba bağlı ayrı bir tablo; QR menü ürünüyle BAĞ `menu_urun_id` üzerinden:
"QR menüden aktar" ürünleri bağlı olarak kopyalar, bağlı ürünün stoku biterse menüde "tükendi"
(`menu_urunleri.stokta_yok`) kendiliğinden işaretlenir/kalkar (ayar). İkinci bir katalog DEĞİL,
aynı ürünün stok/maliyet/barkod yüzü.

Tablolar
--------
* `stok_ayarlari` — hesap başına tek satır: firma künyesi (fiş/fatura başlığı), para birimi, KDV
  oranları (boş = `services.stok_pos.KDV_ORANLARI`), eksi stok izni, kasiyerin iade/indirim yetkisi,
  QR menü eşitleme, fiş/fatura sayaçları.
* `stok_konumlari` — depo/şube (çoklu konum basit; biri varsayılan).
* `stok_urunleri` — ürün: barkod (hesapta benzersiz; yoksa iç EAN-13 üretilir), SKU, birim, alış
  (maliyet, KDV hariç) ve satış (KDV dahil) fiyatı kuruş, KDV oranı, kritik eşik, varyant
  (`ana_urun_id` + `varyant` {beden, renk}), QR menü bağı, kritik uyarı izi (`kritik_at`: eşik
  altına inince BİR kez dolar, eşik üstüne çıkınca boşalır).
* `stok_seviyeleri` — ürün × konum miktarı. Miktarlar TAM SAYI binde bir (1,5 kg = 1500): kayan
  nokta yok, atomik `miktar = miktar + :d` güncellemesi (eksi stok kapalıysa koşullu).
* `stok_hareketleri` — her değişimin kaydı (giriş, çıkış, satış, iade, fire, sayım, transfer,
  düzeltme): işaretli miktar + hareket sonrası konum stoku.
* `stok_tedarikcileri` — basit tedarikçi listesi.
* `stok_sayimlari` / `stok_sayim_kalemleri` — envanter sayımı: okut-say, onayda fark hareketi.
* `pos_kasa_oturumlari` — kasa aç/kapa: gün başı nakit, gün sonu sayım, beklenen ve fark; kapanışta
  Z-benzeri özet donar. Konum başına tek açık oturum (`acik_anahtar` benzersiz; kapanınca NULL).
* `pos_satislari` / `pos_satis_kalemleri` — satış (fiş). Tutarlar sunucuda hesaplanır, kuruş.
  `istemci_kimligi`: ağ koparsa aynı sepet ikinci kez gönderilse de tek satış (hesapta benzersiz).
* `pos_iadeler` — iade / iptal kayıtları (kasa mutabakatına girer).
* `pos_alicilari` — fatura alıcısı / isteğe bağlı müşteri kaydı (KİŞİSEL VERİ; denetim dışı).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class StokAyarlari(Base):
    __tablename__ = "stok_ayarlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), unique=True, index=True, nullable=False)
    firma_adi = Column(String(160), nullable=True)
    adres = Column(Text, nullable=True)
    telefon = Column(String(32), nullable=True)
    eposta = Column(String(254), nullable=True)
    vergi_dairesi = Column(String(80), nullable=True)
    vergi_no = Column(String(20), nullable=True)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    #: JSON tam sayı listesi; boş = varsayılan oranlar (services.stok_pos.KDV_ORANLARI).
    kdv_oranlari = Column(Text, nullable=True)
    varsayilan_kdv = Column(Integer, nullable=False, default=20)
    #: Stok eksiye düşebilir mi (kapalıyken yetersiz stokta satış/çıkış reddedilir).
    eksi_stok = Column(Boolean, nullable=False, default=False)
    #: Yalnız `kasa` izni olan kişi iade/iptal yapabilir mi; en çok yüzde kaç indirim verebilir.
    kasa_iade = Column(Boolean, nullable=False, default=False)
    kasa_indirim_yuzde = Column(Integer, nullable=False, default=10)
    #: Bağlı QR menü ürününün stoku bitince menüde "tükendi" işaretlensin.
    qr_stok_esitle = Column(Boolean, nullable=False, default=True)
    kritik_bildirim = Column(Boolean, nullable=False, default=True)
    #: Fişin altına eklenen kısa not (teşekkür, iade koşulu…).
    fis_notu = Column(Text, nullable=True)
    satis_sayac = Column(Integer, nullable=False, default=0)
    fatura_sayac = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class StokKonumlari(Base):
    __tablename__ = "stok_konumlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    ad = Column(String(80), nullable=False)
    adres = Column(Text, nullable=True)
    varsayilan = Column(Boolean, nullable=False, default=False)
    aktif = Column(Boolean, nullable=False, default=True)
    sira = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class StokUrunleri(Base):
    __tablename__ = "stok_urunleri"
    __table_args__ = (
        UniqueConstraint("hesap_email", "barkod", name="uq_stok_urun_barkod"),
        UniqueConstraint("hesap_email", "sku", name="uq_stok_urun_sku"),
        Index("ix_stok_urunleri_hesap_ad", "hesap_email", "ad"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    ad = Column(String(160), nullable=False)
    #: EAN-13/EAN-8 (kontrol hanesi doğru) ya da serbest kod (Code128); boş gelirse iç EAN-13.
    barkod = Column(String(32), nullable=False)
    sku = Column(String(64), nullable=True)
    kategori = Column(String(80), nullable=True)
    #: adet | kg | lt | m | paket
    birim = Column(String(8), nullable=False, default="adet")
    #: Kuruş. Alış: KDV HARİÇ birim maliyet (son alış). Satış: KDV DAHİL raf fiyatı.
    alis_fiyati = Column(Integer, nullable=False, default=0)
    satis_fiyati = Column(Integer, nullable=False, default=0)
    kdv_orani = Column(Integer, nullable=False, default=20)
    #: Binde bir; boş = uyarı yok.
    kritik_esik = Column(Integer, nullable=True)
    #: Hizmet/kalemde (ör. kesim) stok tutulmaz.
    stok_takibi = Column(Boolean, nullable=False, default=True)
    ana_urun_id = Column(Integer, index=True, nullable=True)
    #: {"beden": "M", "renk": "Kırmızı"}
    varyant = Column(Text, nullable=True)
    #: Faz 4M QR menü / katalog ürünü bağı.
    menu_urun_id = Column(Integer, index=True, nullable=True)
    notlar = Column(Text, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True, index=True)
    #: Kritik stok uyarısının gönderildiği an (eşik üstüne çıkınca NULL; uyarı başına tek olay).
    kritik_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class StokSeviyeleri(Base):
    __tablename__ = "stok_seviyeleri"
    __table_args__ = (
        UniqueConstraint("urun_id", "konum_id", name="uq_stok_seviye_urun_konum"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    urun_id = Column(Integer, index=True, nullable=False)
    konum_id = Column(Integer, index=True, nullable=False)
    #: Binde bir (1 adet = 1000).
    miktar = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class StokHareketleri(Base):
    __tablename__ = "stok_hareketleri"
    __table_args__ = (
        Index("ix_stok_hareketleri_hesap_zaman", "hesap_email", "zaman"),
        Index("ix_stok_hareketleri_urun_zaman", "urun_id", "zaman"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), nullable=False)
    urun_id = Column(Integer, nullable=False)
    konum_id = Column(Integer, nullable=False)
    #: giris | cikis | satis | iade | iptal | fire | sayim | transfer_cikis | transfer_giris | duzeltme
    tur = Column(String(16), nullable=False)
    #: İşaretli, binde bir.
    miktar = Column(Integer, nullable=False)
    #: Hareket sonrası bu konumdaki stok (binde bir).
    sonra = Column(Integer, nullable=True)
    birim_maliyet = Column(Integer, nullable=True)
    tedarikci_id = Column(Integer, nullable=True)
    satis_id = Column(Integer, index=True, nullable=True)
    sayim_id = Column(Integer, nullable=True)
    transfer_kodu = Column(String(16), nullable=True)
    belge_no = Column(String(40), nullable=True)
    aciklama = Column(String(300), nullable=True)
    kisi = Column(String(254), nullable=True)
    zaman = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class StokTedarikcileri(Base):
    __tablename__ = "stok_tedarikcileri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    ad = Column(String(160), nullable=False)
    yetkili = Column(String(120), nullable=True)
    telefon = Column(String(32), nullable=True)
    eposta = Column(String(254), nullable=True)
    vergi_no = Column(String(20), nullable=True)
    notlar = Column(Text, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class StokSayimlari(Base):
    __tablename__ = "stok_sayimlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    konum_id = Column(Integer, nullable=False)
    #: acik | onaylandi | iptal
    durum = Column(String(10), nullable=False, default="acik")
    aciklama = Column(String(300), nullable=True)
    baslatan = Column(String(254), nullable=True)
    onaylayan = Column(String(254), nullable=True)
    baslangic = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    bitis = Column(DateTime(timezone=True), nullable=True)
    #: Onay özeti: {"kalem": n, "fark_arti": .., "fark_eksi": .., "deger_farki": kuruş}
    ozet = Column(Text, nullable=True)


class StokSayimKalemleri(Base):
    __tablename__ = "stok_sayim_kalemleri"
    __table_args__ = (
        UniqueConstraint("sayim_id", "urun_id", name="uq_stok_sayim_kalem"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    sayim_id = Column(Integer, index=True, nullable=False)
    hesap_email = Column(String(254), nullable=False)
    urun_id = Column(Integer, nullable=False)
    sayilan = Column(Integer, nullable=False, default=0)
    #: Onay anındaki sistem stoku ve fark (binde bir).
    sistem = Column(Integer, nullable=True)
    fark = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class PosKasaOturumlari(Base):
    __tablename__ = "pos_kasa_oturumlari"
    __table_args__ = (
        Index("ix_pos_kasa_hesap_acilis", "hesap_email", "acilis_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    konum_id = Column(Integer, nullable=False)
    #: acik | kapali
    durum = Column(String(8), nullable=False, default="acik")
    #: Açıkken "<hesap>|<konum>", kapanınca NULL — konum başına tek açık kasa (benzersiz).
    acik_anahtar = Column(String(300), unique=True, nullable=True)
    acan = Column(String(254), nullable=False)
    acilis_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    acilis_nakit = Column(Integer, nullable=False, default=0)
    kapatan = Column(String(254), nullable=True)
    kapanis_at = Column(DateTime(timezone=True), nullable=True)
    sayilan_nakit = Column(Integer, nullable=True)
    beklenen_nakit = Column(Integer, nullable=True)
    fark = Column(Integer, nullable=True)
    notlar = Column(Text, nullable=True)
    #: Kapanışta donan Z-benzeri özet (JSON).
    ozet = Column(Text, nullable=True)


class PosSatislari(Base):
    __tablename__ = "pos_satislari"
    __table_args__ = (
        UniqueConstraint("hesap_email", "no", name="uq_pos_satis_no"),
        UniqueConstraint("hesap_email", "istemci_kimligi", name="uq_pos_satis_istemci"),
        Index("ix_pos_satislari_hesap_zaman", "hesap_email", "zaman"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), nullable=False)
    no = Column(String(24), nullable=False)
    konum_id = Column(Integer, nullable=False)
    oturum_id = Column(Integer, index=True, nullable=False)
    kasiyer = Column(String(254), nullable=False)
    alici_id = Column(Integer, nullable=True)
    musteri_ad = Column(String(160), nullable=True)
    #: tamamlandi | kismi_iade | iade | iptal
    durum = Column(String(12), nullable=False, default="tamamlandi")
    # --- Sunucunun hesapladığı tutarlar (kuruş, KDV dahil) ---
    ara_toplam = Column(Integer, nullable=False, default=0)
    satir_indirim = Column(Integer, nullable=False, default=0)
    toplam_indirim = Column(Integer, nullable=False, default=0)
    toplam = Column(Integer, nullable=False, default=0)
    kdv_toplam = Column(Integer, nullable=False, default=0)
    kdv_dokumu = Column(Text, nullable=True)
    #: nakit | kart | havale | karma
    odeme_turu = Column(String(8), nullable=False, default="nakit")
    nakit = Column(Integer, nullable=False, default=0)
    kart = Column(Integer, nullable=False, default=0)
    havale = Column(Integer, nullable=False, default=0)
    nakit_alinan = Column(Integer, nullable=False, default=0)
    para_ustu = Column(Integer, nullable=False, default=0)
    iade_toplam = Column(Integer, nullable=False, default=0)
    para_birimi = Column(String(3), nullable=False, default="TRY")
    istemci_kimligi = Column(String(40), nullable=True)
    fatura_no = Column(String(24), nullable=True)
    fatura_at = Column(DateTime(timezone=True), nullable=True)
    fatura_alici = Column(Text, nullable=True)
    notlar = Column(String(300), nullable=True)
    zaman = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class PosSatisKalemleri(Base):
    __tablename__ = "pos_satis_kalemleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    satis_id = Column(Integer, index=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    urun_id = Column(Integer, index=True, nullable=False)
    ad = Column(String(200), nullable=False)
    barkod = Column(String(32), nullable=True)
    birim = Column(String(8), nullable=False, default="adet")
    #: Binde bir.
    adet = Column(Integer, nullable=False)
    #: Kuruş, KDV dahil.
    birim_fiyat = Column(Integer, nullable=False)
    #: Satırın kendi indirimi ve (toplam indirimden düşen payla) bütün indirim.
    satir_indirim = Column(Integer, nullable=False, default=0)
    indirim = Column(Integer, nullable=False, default=0)
    tutar = Column(Integer, nullable=False)
    kdv_orani = Column(Integer, nullable=False, default=0)
    kdv = Column(Integer, nullable=False, default=0)
    #: Satış anındaki birim maliyet (KDV hariç, kuruş).
    birim_maliyet = Column(Integer, nullable=False, default=0)
    iade_adet = Column(Integer, nullable=False, default=0)
    iade_tutar = Column(Integer, nullable=False, default=0)


class PosIadeler(Base):
    __tablename__ = "pos_iadeler"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    satis_id = Column(Integer, index=True, nullable=False)
    oturum_id = Column(Integer, index=True, nullable=True)
    #: iade | iptal
    tur = Column(String(6), nullable=False, default="iade")
    tutar = Column(Integer, nullable=False, default=0)
    #: nakit | kart | havale
    odeme_turu = Column(String(8), nullable=False, default="nakit")
    kalemler = Column(Text, nullable=False)
    neden = Column(String(300), nullable=True)
    kisi = Column(String(254), nullable=True)
    zaman = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class PosAlicilari(Base):
    __tablename__ = "pos_alicilari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String(254), index=True, nullable=False)
    #: bireysel | kurumsal
    tur = Column(String(10), nullable=False, default="bireysel")
    ad = Column(String(160), nullable=False)
    vergi_dairesi = Column(String(80), nullable=True)
    #: VKN (10) / TCKN (11)
    vergi_no = Column(String(20), nullable=True)
    adres = Column(Text, nullable=True)
    eposta = Column(String(254), nullable=True)
    telefon = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)
