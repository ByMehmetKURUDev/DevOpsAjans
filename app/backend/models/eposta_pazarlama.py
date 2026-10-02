"""Faz 5M — E-posta pazarlama: bülten, kampanya ve damla dizileri.

Kapsam (hesap)
--------------
Her kayıt bir hesaba ait: `hesap_email` boşsa ajansın kendisi (yönetici paneli),
doluysa müşteri hesabı (müşteri paneli, modül `eposta_pazarlama`). Kişi ve
bastırma tablolarında ayrıca boş olmayan `kapsam` sütunu var (ajans: `@ajans`,
müşteri: e-postası; bastırmada `*` = bütün hesaplar): benzersizlik kısıtı NULL'u
eşit saymadığı için (aynı hesapta aynı adres bir kez) bu ayrı sütun gerekiyor.

Tablolar
--------
* `ep_ayarlar` — hesap başına gönderen adı, yanıt adresi, (müşteride) unvan ve
  adres, marka rengi/logo, takip seçenekleri (varsayılan KAPALI — gizlilik),
  alıcı başına günlük sıklık sınırı, İYS bilgisi (yalnız bilgi), askıya alma.
* `ep_kisiler` — alıcılar: alıcı türü (bireysel/kurumsal), izin durumu + kaynağı
  + zamanı + metin sürümü + kanıtı, ret zamanı/kaynağı. Ret anında etkili ve
  kalıcı (ayrıca `ep_bastirma`).
* `ep_listeler`, `ep_liste_uyelikleri` — statik listeler; üyelik `bekliyor`
  (çift onay bekliyor: onay jetonunun yalnız ÖZETİ ve bitişi) → `aktif` → `cikti`.
* `ep_formlar` — herkese açık abonelik formu (gömme betiği + /bulten/<anahtar>).
* `ep_bastirma` — bastırma listesi (ret, sert geri dönüş, şikâyet, elle).
* `ep_segmentler` — kural tabanlı dinamik kitle.
* `ep_kampanyalar` — konu (+ A/B konusu), önizleme metni, bloklar, hedef kitle,
  durum makinesi (taslak → zamanlandi → gonderiliyor | ab_test → tamamlandi).
* `ep_gonderimler` — alıcı başına ileti satırı (kampanya ya da dizi adımı):
  kuyrukta → gonderiliyor → gonderildi → teslim; atlandi (neden) / hata /
  geri_dondu / sikayet. (kampanya, kişi) ve (dizi adımı, kişi) BENZERSİZ: aynı
  kişiye aynı ileti iki kez gitmez.
* `ep_diziler`, `ep_dizi_adimlari`, `ep_dizi_kayitlari` — damla dizisi: tetik
  (listeye katıldı / abonelik onaylandı), adımlar (bekle N gün → e-posta),
  çıkış (ret her zaman; isteğe bağlı hedef).
* `ep_gorseller` — e-posta görselleri (dosya deposunda; e-postada mutlak URL).
* `ep_tiklamalar` — bağlantı başına tıklama (rapor; takip açıksa).
* `ep_webhook_olaylari` — Resend (Svix) olay kimlikleri: aynı olay iki kez sayılmaz.

Liste/JSON alanları metin sütununda (SQLite ile Postgres aynı davransın).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class EpAyarlar(Base):
    __tablename__ = "ep_ayarlar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: "@ajans" ya da müşteri hesabının e-postası (benzersiz).
    kapsam = Column(String, unique=True, index=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    gonderen_adi = Column(String, nullable=True)
    yanit_adresi = Column(String, nullable=True)
    #: Müşteri hesabında gönderen kimliği (ajansta Site Ayarları › Yasal bilgiler).
    unvan = Column(String, nullable=True)
    adres = Column(Text, nullable=True)
    logo_url = Column(String, nullable=True)
    marka_rengi = Column(String, nullable=True)
    dil = Column(String, nullable=False, default="tr")
    #: bilinmiyor | var | yok — yalnız bilgi (İYS API entegrasyonu yok).
    iys_durumu = Column(String, nullable=False, default="bilinmiyor")
    iys_marka_kodu = Column(String, nullable=True)
    acilma_takibi = Column(Boolean, nullable=False, default=False)
    tiklama_takibi = Column(Boolean, nullable=False, default=False)
    #: Alıcı başına 24 saatte en çok bu kadar pazarlama iletisi.
    gunluk_kisi_siniri = Column(Integer, nullable=False, default=1)
    askida = Column(Boolean, nullable=False, default=False)
    #: elle | sikayet_orani | geri_donme_orani
    askida_neden = Column(String, nullable=True)
    askida_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EpKisiler(Base):
    __tablename__ = "ep_kisiler"
    __table_args__ = (
        UniqueConstraint("kapsam", "eposta", name="uq_ep_kisi"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String, index=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    eposta = Column(String, index=True, nullable=False)
    ad = Column(String, nullable=True)
    firma = Column(String, nullable=True)
    #: bireysel | kurumsal (tacir/esnaf — önceden onay gerekmeyebilir, ret hakkı her iletide)
    alici_turu = Column(String, nullable=False, default="bireysel")
    #: izinli | izinsiz | bekliyor (çift onay) | reddetti
    izin_durumu = Column(String, index=True, nullable=False, default="izinsiz")
    #: "form:<anahtar>" | "csv:<kaynak>" | "crm:<aday_id>" | "manuel:<not>"
    izin_kaynagi = Column(String, nullable=True)
    izin_zamani = Column(DateTime(timezone=True), nullable=True)
    izin_metin_surumu = Column(String, nullable=True)
    #: Kanıt özeti: çift onay, gösterilen metnin özeti, CSV'deki beyan…
    izin_kaniti = Column(Text, nullable=True)
    onay_zamani = Column(DateTime(timezone=True), nullable=True)
    ret_zamani = Column(DateTime(timezone=True), nullable=True)
    #: baglanti | tek_tik | sikayet | yonetici | tercih
    ret_kaynagi = Column(String, nullable=True)
    #: form | csv | manuel | crm
    kaynak = Column(String, nullable=False, default="manuel")
    kaynak_detay = Column(String, nullable=True)
    crm_aday_id = Column(Integer, index=True, nullable=True)
    #: JSON listesi (küçük harf).
    etiketler = Column(Text, nullable=True)
    #: JSON sözlüğü (özel alanlar: {"sehir": "İzmir"}).
    ozel_alanlar = Column(Text, nullable=True)
    dil = Column(String, nullable=False, default="tr")
    son_etkilesim_at = Column(DateTime(timezone=True), nullable=True)
    son_gonderim_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EpListeler(Base):
    __tablename__ = "ep_listeler"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    ad = Column(String, nullable=False)
    aciklama = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EpListeUyelikleri(Base):
    __tablename__ = "ep_liste_uyelikleri"
    __table_args__ = (
        UniqueConstraint("liste_id", "kisi_id", name="uq_ep_liste_uyelik"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    liste_id = Column(Integer, index=True, nullable=False)
    kisi_id = Column(Integer, index=True, nullable=False)
    #: aktif | bekliyor | cikti
    durum = Column(String, nullable=False, default="aktif")
    kaynak = Column(String, nullable=True)
    form_id = Column(Integer, nullable=True)
    katilma_at = Column(DateTime(timezone=True), nullable=True)
    cikis_at = Column(DateTime(timezone=True), nullable=True)
    #: Çift onay jetonunun sha256 özeti (ham jeton yalnız e-postada); kullanılınca boşalır.
    onay_ozeti = Column(String, index=True, nullable=True)
    onay_bitis = Column(DateTime(timezone=True), nullable=True)
    onay_gonderim_at = Column(DateTime(timezone=True), nullable=True)
    onay_gonderim_sayisi = Column(Integer, nullable=False, default=0)
    #: Abonelik anında gösterilen izin metninin sürümü ve özeti (kanıt).
    izin_metin_surumu = Column(String, nullable=True)
    izin_metin_ozeti = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EpFormlar(Base):
    __tablename__ = "ep_formlar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    liste_id = Column(Integer, index=True, nullable=False)
    ad = Column(String, nullable=False)
    genel_anahtar = Column(String, unique=True, index=True, nullable=False)
    baslik = Column(String, nullable=True)
    aciklama = Column(Text, nullable=True)
    #: Formun varsayılan dili (ziyaretçi dili verilmezse).
    dil = Column(String, nullable=False, default="tr")
    ad_sor = Column(Boolean, nullable=False, default=True)
    #: Ziyaretçiye "kurumsal (işletme) adresi" seçeneği sorulsun mu.
    tur_sor = Column(Boolean, nullable=False, default=False)
    tesekkur_metni = Column(Text, nullable=True)
    #: Müşteri formunda hesabın kendi aydınlatma metni (https). Ajansta boşsa sitenin /gizlilik sayfası.
    aydinlatma_baglantisi = Column(String, nullable=True)
    #: JSON listesi: formun gömülebileceği alan adları (site her zaman izinli).
    izinli_alanlar = Column(Text, nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    gonderim_sayisi = Column(Integer, nullable=False, default=0)
    son_gonderim_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EpBastirma(Base):
    __tablename__ = "ep_bastirma"
    __table_args__ = (
        UniqueConstraint("kapsam", "eposta", name="uq_ep_bastirma"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: "*" (bütün hesaplar — sert geri dönüş), "@ajans" ya da müşteri e-postası.
    kapsam = Column(String, index=True, nullable=False)
    eposta = Column(String, index=True, nullable=False)
    #: ret | sert_geri_donme | sikayet | elle
    neden = Column(String, nullable=False)
    kaynak = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EpSegmentler(Base):
    __tablename__ = "ep_segmentler"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    ad = Column(String, nullable=False)
    #: JSON: {"birlesim": "ve"|"veya", "kurallar": [{"alan", "op", "deger", ...}]}
    kurallar = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EpKampanyalar(Base):
    __tablename__ = "ep_kampanyalar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    ad = Column(String, nullable=False)
    konu = Column(String, nullable=True)
    onizleme_metni = Column(String, nullable=True)
    gonderen_adi = Column(String, nullable=True)
    yanit_adresi = Column(String, nullable=True)
    dil = Column(String, nullable=False, default="tr")
    #: JSON blok listesi (services/eposta_icerik.py).
    bloklar = Column(Text, nullable=True)
    #: JSON: {"listeler": [id], "segmentler": [id], "haric_listeler": [id]}
    hedef = Column(Text, nullable=True)
    #: JSON: {"acik": bool, "konu_b": str, "oran": 20, "bekleme_saat": 4, "olcut": "acilma"|"tiklama"}
    ab = Column(Text, nullable=True)
    #: taslak | zamanlandi | gonderiliyor | ab_test | duraklatildi | tamamlandi | iptal
    durum = Column(String, index=True, nullable=False, default="taslak")
    zamanlanan_at = Column(DateTime(timezone=True), index=True, nullable=True)
    baslangic_at = Column(DateTime(timezone=True), nullable=True)
    bitis_at = Column(DateTime(timezone=True), nullable=True)
    ab_karar_at = Column(DateTime(timezone=True), nullable=True)
    #: a | b
    kazanan = Column(String, nullable=True)
    #: kota | hesap_askida | yonetici | kullanici
    duraklatma_nedeni = Column(String, nullable=True)
    #: Gönderim başında dondurulan içerik (işaretli şablon) ve bağlantılar.
    html = Column(Text, nullable=True)
    metin = Column(Text, nullable=True)
    baglantilar = Column(Text, nullable=True)
    takip_acilma = Column(Boolean, nullable=False, default=False)
    takip_tiklama = Column(Boolean, nullable=False, default=False)
    hedef_sayisi = Column(Integer, nullable=False, default=0)
    olusturan = Column(String, nullable=True)
    son_islem_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EpGonderimler(Base):
    __tablename__ = "ep_gonderimler"
    __table_args__ = (
        UniqueConstraint("kampanya_id", "kisi_id", name="uq_ep_gonderim_kampanya"),
        UniqueConstraint("adim_id", "kisi_id", name="uq_ep_gonderim_adim"),
        Index("ix_ep_gonderim_siklik", "kapsam", "eposta", "gonderim_at"),
        Index("ix_ep_gonderim_kuyruk", "durum", "id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String, index=True, nullable=False)
    hesap_email = Column(String, nullable=True)
    kampanya_id = Column(Integer, index=True, nullable=True)
    dizi_id = Column(Integer, index=True, nullable=True)
    adim_id = Column(Integer, nullable=True)
    kisi_id = Column(Integer, index=True, nullable=True)
    eposta = Column(String, nullable=True)
    #: a | b (A/B konu testi) — boş: tek konu ya da kazanan
    varyant = Column(String, nullable=True)
    #: kuyrukta | ab_bekliyor | gonderiliyor | gonderildi | teslim | geri_dondu | sikayet | atlandi | hata
    durum = Column(String, nullable=False, default="kuyrukta")
    #: Atlama/hata nedeni (izin_yok, bastirildi, ret, gecersiz_adres, siklik_siniri, kota…)
    neden = Column(String, nullable=True)
    resend_id = Column(String, index=True, nullable=True)
    deneme = Column(Integer, nullable=False, default=0)
    #: Parça kimliği: satır "gonderiliyor"a hangi çağrıda alındı (eş zamanlı iki çalıştırma aynı satırı alamaz).
    parti = Column(String, index=True, nullable=True)
    #: "gonderiliyor"a alındığı an (yarıda kalan parçayı bulmak için).
    alindi_at = Column(DateTime(timezone=True), nullable=True)
    gonderim_at = Column(DateTime(timezone=True), nullable=True)
    teslim_at = Column(DateTime(timezone=True), nullable=True)
    acilma_at = Column(DateTime(timezone=True), nullable=True)
    tiklama_at = Column(DateTime(timezone=True), nullable=True)
    geri_donme_at = Column(DateTime(timezone=True), nullable=True)
    #: sert | yumusak
    geri_donme_turu = Column(String, nullable=True)
    sikayet_at = Column(DateTime(timezone=True), nullable=True)
    ret_at = Column(DateTime(timezone=True), nullable=True)
    hata = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EpDiziler(Base):
    __tablename__ = "ep_diziler"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    ad = Column(String, nullable=False)
    #: liste_katildi | abonelik_onaylandi
    tetik = Column(String, nullable=False, default="abonelik_onaylandi")
    liste_id = Column(Integer, index=True, nullable=True)
    aktif = Column(Boolean, nullable=False, default=False)
    #: JSON: {"hedef": null | {"tur": "tiklama"} | {"tur": "etiket", "deger": ".."} | {"tur": "liste", "liste_id": n}}
    cikis = Column(Text, nullable=True)
    gonderen_adi = Column(String, nullable=True)
    dil = Column(String, nullable=False, default="tr")
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EpDiziAdimlari(Base):
    __tablename__ = "ep_dizi_adimlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    dizi_id = Column(Integer, index=True, nullable=False)
    sira = Column(Integer, nullable=False, default=0)
    #: Önceki adımdan (ilk adımda kayıttan) sonra bekleme.
    bekle_gun = Column(Integer, nullable=False, default=0)
    bekle_saat = Column(Integer, nullable=False, default=0)
    konu = Column(String, nullable=False)
    onizleme_metni = Column(String, nullable=True)
    bloklar = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class EpDiziKayitlari(Base):
    __tablename__ = "ep_dizi_kayitlari"
    __table_args__ = (
        UniqueConstraint("dizi_id", "kisi_id", name="uq_ep_dizi_kayit"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    dizi_id = Column(Integer, index=True, nullable=False)
    kisi_id = Column(Integer, index=True, nullable=False)
    #: aktif | tamamlandi | cikti
    durum = Column(String, index=True, nullable=False, default="aktif")
    #: Sıradaki adımın sırası (0'dan; adım sayısına eşitse bitti).
    sonraki_sira = Column(Integer, nullable=False, default=0)
    sonraki_at = Column(DateTime(timezone=True), index=True, nullable=True)
    baslangic_at = Column(DateTime(timezone=True), nullable=False)
    bitis_at = Column(DateTime(timezone=True), nullable=True)
    #: ret | hedef | izin_yok | kisi_silindi | dizi_silindi
    cikis_nedeni = Column(String, nullable=True)


class EpGorseller(Base):
    __tablename__ = "ep_gorseller"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    hesap_email = Column(String, index=True, nullable=True)
    anahtar = Column(String(64), unique=True, index=True, nullable=False)
    depo = Column(String(8), nullable=False)
    #: image/jpeg | image/png
    tur = Column(String(16), nullable=False)
    genislik = Column(Integer, nullable=False, default=0)
    yukseklik = Column(Integer, nullable=False, default=0)
    boyut = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EpTiklamalar(Base):
    __tablename__ = "ep_tiklamalar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kampanya_id = Column(Integer, index=True, nullable=True)
    gonderim_id = Column(Integer, index=True, nullable=False)
    indeks = Column(Integer, nullable=False)
    zaman = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class EpWebhookOlaylari(Base):
    __tablename__ = "ep_webhook_olaylari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    svix_id = Column(String, unique=True, index=True, nullable=False)
    tur = Column(String, nullable=True)
    resend_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


__all__ = [
    "EpAyarlar", "EpKisiler", "EpListeler", "EpListeUyelikleri", "EpFormlar", "EpBastirma", "EpSegmentler",
    "EpKampanyalar", "EpGonderimler", "EpDiziler", "EpDiziAdimlari", "EpDiziKayitlari", "EpGorseller",
    "EpTiklamalar", "EpWebhookOlaylari",
]
