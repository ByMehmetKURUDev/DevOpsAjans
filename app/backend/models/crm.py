"""Faz 3C — CRM ve aday hunisi (yalnız ajansın kendi satış hunisi).

Tablolar
--------
* `crm_asamalar`  — huninin aşamaları (Yeni → … → Kazanıldı / Kaybedildi).
  Ad Türkçe `ad` sütununda, diğer altı dil `ceviriler` JSON'unda
  (``{"en": {"ad": ".."}, ...}``; kaynaklar/marketplace ile aynı desen).
  `tur`: acik | kazanildi | kaybedildi.
* `crm_adaylar`   — aday (potansiyel müşteri). Aşamaya `asama` (anahtar)
  ile bağlı; aşama silinirken adayların başka aşamaya taşınması zorunlu.
* `crm_aktiviteler` — adayın zaman çizelgesi: not / arama / e-posta /
  toplantı (elle), aşama değişimi ve sistem olayları (otomatik). Sistem
  olaylarının metni dile göre ön yüzde üretiliyor: `olay` + `veri` (JSON);
  `metin` yalnız kullanıcının/ziyaretçinin yazdığı içerik.
* `crm_bagli_kayitlar` — adaya bağlanan kaynak kayıtlar (talep, fiyat
  teklifi, form gönderimi). (tablo, kayit_id) BENZERSİZ: otomatik aday
  oluşturma ve "geçmiş talepleri içe aktar" aynı kaydı iki kez işlemiyor.
  Aday silinince satırlar KALIYOR (işlendi işareti): içe aktarma silinen
  adayı geri getirmiyor; çöp kutusundan geri alınan aday aynı kimlikle
  döndüğü için bağlar yeniden geçerli oluyor.
* `crm_formlar`    — gömülebilir aday formu tanımları (genel anahtar ile).
* `crm_form_gonderimleri` — her gönderimin kaydı: gösterilen aydınlatma
  metninin sürümü ve özeti, zaman, IP özeti, köken; Faz 4G'den beri ayrıca
  isteğe bağlı pazarlama izni (izin + zaman + metin sürümü). Aday silinse de
  saklanıyor (kanıt); ham IP hiçbir yerde tutulmuyor. `kvkk_*` sütun adları
  eski: Faz 4G'ye kadar zorunlu onay kutusuydu, artık yalnız bilgilendirme.

Liste/JSON alanları metin sütununda (SQLite ile Postgres aynı davransın).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class CrmAsamalari(Base):
    __tablename__ = "crm_asamalar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Kalıcı kimlik (küçük harf, rakam, alt çizgi). Ad değişse de değişmez.
    anahtar = Column(String, unique=True, index=True, nullable=False)
    ad = Column(String, nullable=False)
    #: JSON: {"en": {"ad": ".."}, "de": {...}, ...}
    ceviriler = Column(Text, nullable=True)
    sira = Column(Integer, nullable=False, default=100)
    #: Ön yüzdeki renk anahtarı (slate, sky, violet, amber, orange, emerald, rose, pink, teal).
    renk = Column(String, nullable=False, default="slate")
    #: acik | kazanildi | kaybedildi
    tur = Column(String, nullable=False, default="acik")
    #: Bu aşamaya geçen adayın varsayılan olasılığı (%). Boşsa değişmiyor.
    olasilik = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class CrmAdaylari(Base):
    __tablename__ = "crm_adaylar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    ad = Column(String, nullable=False)
    firma = Column(String, nullable=True)
    #: Küçük harfe çevrilmiş; tekilleştirme anahtarı (aynı e-postada açık aday bir tane).
    email = Column(String, index=True, nullable=True)
    telefon = Column(String, nullable=True)
    #: iletisim | bekleme | site_analizi | kesif | fiyat_teklifi | kaynaklar | form | manuel | eposta
    kaynak = Column(String, index=True, nullable=False, default="manuel")
    #: Kaynağın ham değeri (ör. "marketplace: Kartvizit", form adı) — bilgi amaçlı.
    kaynak_detay = Column(String, nullable=True)
    #: İlk kaynak kayıt (tablo + id). Hepsi `crm_bagli_kayitlar`da.
    kaynak_tablo = Column(String, nullable=True)
    kaynak_id = Column(Integer, nullable=True)
    asama = Column(String, index=True, nullable=False)
    deger_tahmini = Column(Float, nullable=True)
    para_birimi = Column(String, nullable=False, default="TRY")
    olasilik = Column(Integer, nullable=True)
    #: Sorumlu ekip üyesi (staff/yönetici e-postası).
    sorumlu = Column(String, index=True, nullable=True)
    #: JSON listesi (küçük harf).
    etiketler = Column(Text, nullable=True)
    notlar = Column(Text, nullable=True)
    #: İlk talebin metni (puanlamadaki "kapsam" ölçüsü ve detayda özet).
    ilk_mesaj = Column(Text, nullable=True)
    #: Ziyaretçinin belirttiği bütçe (serbest metin).
    butce = Column(String, nullable=True)
    sonraki_adim = Column(String, nullable=True)
    sonraki_adim_tarihi = Column(Date, index=True, nullable=True)
    #: Hatırlatmanın en son gönderildiği gün (günde bir kez).
    hatirlatma_tarihi = Column(Date, nullable=True)
    kaybedilme_nedeni = Column(Text, nullable=True)
    #: Müşteriye dönüştürüldüyse müşterinin panel e-postası.
    musteri_email = Column(String, index=True, nullable=True)
    puan = Column(Integer, index=True, nullable=False, default=0)
    #: JSON: [{"kural", "puan", "en_cok", "deger"}] — "neden bu puan".
    puan_ayrinti = Column(Text, nullable=True)
    #: Yeni aday bildirimi zamanlı görevle gidecek mi (kaynağı kendi bildirimini atmayanlar).
    bildirim_bekliyor = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)
    asama_degisme_at = Column(DateTime(timezone=True), default=_simdi, nullable=True)
    #: Faz 4G — pazarlama (ticari elektronik ileti) izni: en son verildiği an,
    #: kaynağı ("form:<id>" | "site_analizi:<id>") ve metin sürümü. Boşsa izin
    #: yok; yönetici geri alınca (kişinin talebi) boşalıyor.
    pazarlama_izni_at = Column(DateTime(timezone=True), nullable=True)
    pazarlama_izni_kaynak = Column(String, nullable=True)
    pazarlama_metin_surumu = Column(String, nullable=True)
    #: Faz 5K — formda girilen / bağlantıdan gelen ortak referans kodu ve indirim kodu (görünen biçim).
    referans_kodu = Column(String, nullable=True)
    indirim_kodu = Column(String, nullable=True)


class CrmAktiviteler(Base):
    __tablename__ = "crm_aktiviteler"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    aday_id = Column(Integer, index=True, nullable=False)
    #: not | arama | eposta | toplanti | asama | sistem
    tur = Column(String, nullable=False)
    #: Sistem/aşama olaylarında olay kodu (aday_olustu, talep_eklendi, asama_degisti,
    #: donusturuldu, form_gonderimi, ice_aktarildi); elle eklenenlerde boş.
    olay = Column(String, nullable=True)
    #: JSON: olay parametreleri (kaynak, eski/yeni aşama, tablo/kayit_id, davet durumu…).
    veri = Column(Text, nullable=True)
    metin = Column(Text, nullable=True)
    #: E-posta ya da "sistem".
    yapan = Column(String, nullable=True)
    zaman = Column(DateTime(timezone=True), default=_simdi, index=True, nullable=False)


class CrmBagliKayitlar(Base):
    __tablename__ = "crm_bagli_kayitlar"
    __table_args__ = (
        UniqueConstraint("tablo", "kayit_id", name="uq_crm_bagli_kayit"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    aday_id = Column(Integer, index=True, nullable=False)
    #: inquiries | pricing_inquiries | crm_form_gonderimleri
    tablo = Column(String, nullable=False)
    kayit_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class CrmFormlari(Base):
    __tablename__ = "crm_formlar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Panelde görünen ad (ziyaretçiye gösterilmez).
    ad = Column(String, nullable=False)
    #: Ziyaretçiye görünen başlık (boşsa başlık yok).
    baslik = Column(String, nullable=True)
    #: Gömme kodundaki ve /form/<anahtar> adresindeki tahmin edilemez anahtar.
    genel_anahtar = Column(String, unique=True, index=True, nullable=False)
    #: JSON: {"ad": {"acik": true, "zorunlu": true}, "email": {...}, "telefon": .., "firma": .., "mesaj": .., "butce": ..}
    alanlar = Column(Text, nullable=False)
    varsayilan_asama = Column(String, nullable=True)
    #: JSON listesi.
    varsayilan_etiketler = Column(Text, nullable=True)
    tesekkur_metni = Column(Text, nullable=True)
    #: Gönderimden sonra gidilecek adres (yalnız https; boşsa teşekkür metni).
    yonlendirme_adresi = Column(String, nullable=True)
    #: JSON listesi: formun gömülebileceği alan adları (mehmetkuru.dev her zaman izinli).
    izinli_alanlar = Column(Text, nullable=True)
    #: ESKİ (Faz 4G öncesi): zorunlu KVKK onay kutusunun metni. Artık
    #: gösterilmiyor (aydınlatma ile açık rıza ayrıldı); yeni formlarda boş.
    kvkk_metni = Column(Text, nullable=False, default="")
    #: Gönder düğmesinin altındaki aydınlatma satırı (isteğe bağlı, tek dil).
    #: Boşsa ziyaretçinin dilinde hazır cümle (`services/crm_form.py`).
    aydinlatma_metni = Column(Text, nullable=True)
    aydinlatma_baglantisi = Column(String, nullable=True)
    #: Aydınlatma metni ya da bağlantısı her değiştiğinde 1 artıyor (gönderim kaydı sürümü).
    kvkk_surum = Column(Integer, nullable=False, default=1)
    #: Faz 4G: "Kampanya ve duyurulardan e-posta ile haberdar olmak istiyorum"
    #: kutusu (isteğe bağlı, varsayılan işaretsiz) gösterilsin mi.
    pazarlama_izni_sor = Column(Boolean, nullable=True, default=False)
    aktif = Column(Boolean, nullable=False, default=True)
    gonderim_sayisi = Column(Integer, nullable=False, default=0)
    son_gonderim_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class CrmFormGonderimleri(Base):
    __tablename__ = "crm_form_gonderimleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    form_id = Column(Integer, index=True, nullable=False)
    aday_id = Column(Integer, index=True, nullable=True)
    kvkk_surum = Column(Integer, nullable=False)
    #: sha256(gösterilen metin + "\n" + aydınlatma bağlantısı) — o anki metnin
    #: kanıtı (Faz 4G öncesi: onay kutusu metni; sonrası: aydınlatma satırı).
    kvkk_metin_ozeti = Column(String, nullable=False)
    #: Gönderim anı (eski adıyla "onay" zamanı).
    kvkk_onay_at = Column(DateTime(timezone=True), nullable=False)
    ip_ozeti = Column(String, nullable=True)
    #: Faz 4G — isteğe bağlı pazarlama izni: verildi mi, ne zaman, hangi metin
    #: sürümüyle (`services/pazarlama_izni.py`, ör. "1/tr").
    pazarlama_izni = Column(Boolean, nullable=True, default=False)
    pazarlama_izni_at = Column(DateTime(timezone=True), nullable=True)
    pazarlama_metin_surumu = Column(String, nullable=True)
    #: İsteğin Origin başlığı (gömüldüğü site) — yoksa boş.
    koken = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


__all__ = [
    "CrmAsamalari",
    "CrmAdaylari",
    "CrmAktiviteler",
    "CrmBagliKayitlar",
    "CrmFormlari",
    "CrmFormGonderimleri",
]
