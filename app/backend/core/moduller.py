"""Modül kaydı (manifest): portaldaki her modülün TEK kaynağı.

Neden burada?
-------------
Ajans altyapısı modüler portala dönüşüyor: aynı modüller hem ajansın kendi
işinde (yönetici paneli) hem de müşteriye satılan modüller olarak açılıp
kapanacak. Bir modülün adı, ikonu, hangi panel sekmesine denk geldiği, hangi
pakette varsayılan açık olduğu ve neye bağlı olduğu tek bir listede duruyor.
Yeni modül = bu listeye bir giriş + kendi router'ı (+ ön yüzde sekme
anahtarı → bileşen eşlemesi).

Ad ve açıklama
--------------
Görünen metinler ön yüz i18n ek paketinde (`src/i18n/ek/modul/<dil>.json`,
7 dil) duruyor; manifest yalnız anahtarını taşıyor (`ad_anahtari`,
`aciklama_anahtari`). Sunucunun kendisinin yazdığı iki dilli metinler
(bildirim başlığı) için `ad_varsayilan` Türkçe/İngilizce adı tutuyor; test,
bunların ek paketteki tr/en değerleriyle aynı olduğunu doğruluyor — iki yer
ayrışamıyor.

Kurallar
--------
* `kategori == "cekirdek"` olan modüller kapatılamaz.
* `gerekli_rol == "admin"` olanlar yalnız ajansın kendi işi: müşteriye
  gösterilmez, müşteri başına açılıp kapanmaz.
* `durum == "yakinda"` olanların henüz ucu/sekmesi yok; müşteriye "yakında"
  rozetiyle gösteriliyor. Paketine dahilse açık sayılıyor (çıktığında
  kendiliğinden gelsin).
* `paketler`: modülün varsayılan açık olduğu ölçekler (`pricing_scales.kod`:
  ALFA / BETA / OMEGA / SIGMA). `varsayilan_acik=True` olan modül zaten
  herkese açık; paket listesi yalnız bilgi.
* Öncelik (müşteri başına): tablo satırı (elle) > paket > varsayilan_acik.
  Bir modülün bağımlılığı kapalıysa modül de kapalı sayılır.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

KATEGORILER: Tuple[str, ...] = ("cekirdek", "hizmet", "icerik", "finans", "analiz")
ROLLER: Tuple[str, ...] = ("admin", "client", "her_ikisi")
DURUMLAR: Tuple[str, ...] = ("yayinda", "beta", "yakinda")
#: `pricing_scales.kod` değerleri (scripts/seed_pricing_v5.py).
PAKETLER: Tuple[str, ...] = ("ALFA", "BETA", "OMEGA", "SIGMA")
AYAR_TURLERI: Tuple[str, ...] = ("bool", "int", "metin", "secim")
TUM_PAKETLER: Tuple[str, ...] = PAKETLER


@dataclass(frozen=True)
class AyarAlani:
    """Modül başına müşteriye özel ayar alanı."""

    anahtar: str
    tur: str  # bool | int | metin | secim
    varsayilan: Any
    en_az: Optional[int] = None
    en_cok: Optional[int] = None
    secenekler: Tuple[str, ...] = ()
    uzunluk: int = 200
    #: Boş (None) kabul edilir mi? Boş = "müşteriye özel değer yok, genel
    #: ayar geçerli" (ör. kredi eşiği boşsa site ayarı kullanılıyor).
    bos_olabilir: bool = False

    def sozluk(self) -> Dict[str, Any]:
        return {
            "anahtar": self.anahtar,
            "tur": self.tur,
            "varsayilan": self.varsayilan,
            "en_az": self.en_az,
            "en_cok": self.en_cok,
            "secenekler": list(self.secenekler),
            "bos_olabilir": self.bos_olabilir,
        }

    def dogrula(self, deger: Any) -> Any:
        """Geçerli değeri döndürür; geçersizse ValueError."""
        if deger is None:
            if self.bos_olabilir:
                return None
            raise ValueError("bos")
        if self.tur == "bool":
            if isinstance(deger, bool):
                return deger
            raise ValueError("bool")
        if self.tur == "int":
            if isinstance(deger, bool) or not isinstance(deger, (int, float)) or int(deger) != deger:
                raise ValueError("int")
            deger = int(deger)
            if self.en_az is not None and deger < self.en_az:
                raise ValueError("en_az")
            if self.en_cok is not None and deger > self.en_cok:
                raise ValueError("en_cok")
            return deger
        if self.tur == "secim":
            if deger in self.secenekler:
                return deger
            raise ValueError("secim")
        # metin
        if not isinstance(deger, str):
            raise ValueError("metin")
        return deger.strip()[: self.uzunluk]


@dataclass(frozen=True)
class Modul:
    anahtar: str
    ad_varsayilan: Dict[str, str]  # {"tr": ..., "en": ...} — yalnız sunucu metinleri için
    ikon: str  # lucide ikon adı (PascalCase)
    kategori: str
    musteri_sekmesi: Optional[str]  # ClientPanel `Tab` anahtarı
    yonetici_sekmesi: Optional[str]  # AdminPanel `Tab` anahtarı
    gerekli_rol: str
    varsayilan_acik: bool
    paketler: Tuple[str, ...] = ()
    bagimliliklar: Tuple[str, ...] = ()
    ayarlar: Tuple[AyarAlani, ...] = ()
    durum: str = "yayinda"
    #: Sekmesi olmayan, panelin başka bir yerine gömülü parçalar (bilgi amaçlı;
    #: ön yüz eşlemesi kodda). genel = genel görünüm kartı, profil = profil bölümü.
    yerlesim: Tuple[str, ...] = field(default=())

    @property
    def ad_anahtari(self) -> str:
        return f"modul.m.{self.anahtar}.ad"

    @property
    def aciklama_anahtari(self) -> str:
        return f"modul.m.{self.anahtar}.aciklama"

    @property
    def cekirdek(self) -> bool:
        return self.kategori == "cekirdek"

    @property
    def musteriye_gorunur(self) -> bool:
        return self.gerekli_rol in ("client", "her_ikisi")

    def varsayilan_ayarlar(self) -> Dict[str, Any]:
        return {a.anahtar: a.varsayilan for a in self.ayarlar}

    def sozluk(self) -> Dict[str, Any]:
        return {
            "anahtar": self.anahtar,
            "ad_anahtari": self.ad_anahtari,
            "aciklama_anahtari": self.aciklama_anahtari,
            "ad": dict(self.ad_varsayilan),
            "ikon": self.ikon,
            "kategori": self.kategori,
            "musteri_sekmesi": self.musteri_sekmesi,
            "yonetici_sekmesi": self.yonetici_sekmesi,
            "gerekli_rol": self.gerekli_rol,
            "varsayilan_acik": self.varsayilan_acik,
            "paketler": list(self.paketler),
            "bagimliliklar": list(self.bagimliliklar),
            "ayarlar": [a.sozluk() for a in self.ayarlar],
            "durum": self.durum,
            "cekirdek": self.cekirdek,
            "yerlesim": list(self.yerlesim),
        }


# ---------------------------------------------------------------------------
# Manifest — SIRA ÖNEMLİ: müşteri sekme çubuğu bu sırayla çiziliyor.
# ---------------------------------------------------------------------------
MODULLER: Tuple[Modul, ...] = (
    # --- Çekirdek (kapatılamaz) ---------------------------------------------
    Modul(
        anahtar="projeler",
        ad_varsayilan={"tr": "Projeler", "en": "Projects"},
        ikon="Briefcase",
        kategori="cekirdek",
        musteri_sekmesi="projects",
        yonetici_sekmesi="projects",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
    ),
    Modul(
        anahtar="faturalar",
        ad_varsayilan={"tr": "Faturalar ve ödeme", "en": "Invoices and payments"},
        ikon="Receipt",
        kategori="cekirdek",
        musteri_sekmesi="invoices",
        yonetici_sekmesi="invoices",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
    ),
    # --- Finans ------------------------------------------------------------
    Modul(
        anahtar="krediler",
        ad_varsayilan={"tr": "Krediler", "en": "Credits"},
        ikon="Coins",
        kategori="finans",
        musteri_sekmesi="krediler",
        yonetici_sekmesi="krediler",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        bagimliliklar=("faturalar",),
        # Düşük bakiye uyarı eşiği (saat). Boşsa site ayarı `kredi_esik_saat`,
        # o da yoksa 2 (services/kredi.esik_degeri).
        ayarlar=(AyarAlani("esik_saat", "int", None, en_az=0, en_cok=1000, bos_olabilir=True),),
        yerlesim=("genel",),
    ),
    Modul(
        anahtar="destek",
        ad_varsayilan={"tr": "Destek", "en": "Support"},
        ikon="MessageSquare",
        kategori="cekirdek",
        musteri_sekmesi="tickets",
        yonetici_sekmesi="tickets",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
    ),
    # --- Hizmet / analiz ---------------------------------------------------
    Modul(
        anahtar="raporlar",
        ad_varsayilan={"tr": "Raporlar ve abonelik", "en": "Reports and subscriptions"},
        ikon="FileText",
        kategori="hizmet",
        musteri_sekmesi="raporlar",
        yonetici_sekmesi="abonelik",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        ayarlar=(AyarAlani("eposta_ozeti", "bool", True),),
    ),
    Modul(
        anahtar="sitem",
        ad_varsayilan={"tr": "Site bakım izni", "en": "Site maintenance access"},
        ikon="ShieldCheck",
        kategori="hizmet",
        musteri_sekmesi="sitem",
        yonetici_sekmesi="siteler",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
    ),
    # Faz 2A — "Sitem" sekmesine gömülü; yönetici tarafı "Siteler" sekmesinde.
    Modul(
        anahtar="uptime",
        ad_varsayilan={"tr": "Uptime ve durum sayfası", "en": "Uptime and status page"},
        ikon="Activity",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi=None,
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        paketler=("ALFA", "BETA", "OMEGA", "SIGMA"),
        bagimliliklar=("sitem",),
        # Kontrol başına aralık en az bu kadar sayılıyor (5 dk altı yok:
        # zamanlı uç zaten en sık 5 dakikada bir çalışıyor).
        ayarlar=(AyarAlani("kontrol_araligi_dk", "secim", "5", secenekler=("5", "15", "30", "60")),),
        yerlesim=("sitem",),
    ),
    Modul(
        anahtar="yenileme",
        ad_varsayilan={"tr": "Yenileme yöneticisi", "en": "Renewal manager"},
        ikon="CalendarClock",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi=None,
        gerekli_rol="her_ikisi",
        # Paketli müşteride açık: müşteriye bitiş hatırlatması gider. Paketsiz
        # müşteride kapalı; yönetici listesi ve hatırlatmaları yine çalışır.
        varsayilan_acik=False,
        paketler=TUM_PAKETLER,
        bagimliliklar=("sitem", "faturalar"),
        yerlesim=("sitem",),
    ),
    Modul(
        anahtar="site_analizi",
        ad_varsayilan={"tr": "Site analizi", "en": "Site analysis"},
        ikon="Gauge",
        kategori="analiz",
        musteri_sekmesi="analiz",
        yonetici_sekmesi="siteAnalizleri",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        # Müşterinin panelden günde yapabileceği analiz sayısı
        # (`/site-analizi/benim`; routers/site_analizi.py).
        ayarlar=(AyarAlani("gunluk_sinir", "int", 10, en_az=0, en_cok=500),),
    ),
    Modul(
        anahtar="islem",
        ad_varsayilan={"tr": "Onay bekleyenler", "en": "Awaiting approval"},
        ikon="Link2",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi="islemler",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        durum="beta",
        yerlesim=("genel",),
    ),
    # Faz 2C — Destek sekmesinde arama ve talep açarken öneri; yönetici
    # tarafı kendi sekmesinde (makale yazımı, 7 dil).
    Modul(
        anahtar="bilgi_bankasi",
        ad_varsayilan={"tr": "Bilgi bankası", "en": "Knowledge base"},
        ikon="BookOpen",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi="bilgiBankasi",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        bagimliliklar=("destek",),
        yerlesim=("destek",),
    ),
    # Faz 2C — dosyalar, klasör yetkisi, paylaşım bağlantısı, belge talebi.
    Modul(
        anahtar="dosyalar",
        ad_varsayilan={"tr": "Dosyalar ve belge talebi", "en": "Files and document requests"},
        ikon="FolderOpen",
        kategori="hizmet",
        musteri_sekmesi="dosyalar",
        yonetici_sekmesi="dosyalar",
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        paketler=("BETA", "OMEGA", "SIGMA"),
        bagimliliklar=("projeler",),
    ),
    # Faz 2C — Raporlar sekmesine gömülü (müşteri arşivi) ve yöneticide
    # Raporlar/abonelik sekmesinde oluştur/önizle/yayınla.
    Modul(
        anahtar="aylik_rapor",
        ad_varsayilan={"tr": "Aylık müşteri raporu", "en": "Monthly client report"},
        ikon="BarChart3",
        kategori="analiz",
        musteri_sekmesi=None,
        yonetici_sekmesi=None,
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        paketler=("BETA", "OMEGA", "SIGMA"),
        bagimliliklar=("raporlar", "site_analizi"),
        yerlesim=("raporlar",),
    ),
    Modul(
        anahtar="denetim",
        ad_varsayilan={"tr": "Hesap hareketleri", "en": "Account activity"},
        ikon="History",
        kategori="analiz",
        musteri_sekmesi=None,
        yonetici_sekmesi="denetim",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        yerlesim=("profil",),
    ),
    # --- Çekirdek: bildirim ve profil (sekme çubuğunun sonu) ----------------
    Modul(
        anahtar="bildirimler",
        ad_varsayilan={"tr": "Bildirimler", "en": "Notifications"},
        ikon="BellRing",
        kategori="cekirdek",
        musteri_sekmesi=None,
        yonetici_sekmesi="notify",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        yerlesim=("profil",),
    ),
    Modul(
        anahtar="profil",
        ad_varsayilan={"tr": "Profil", "en": "Profile"},
        ikon="UserCog",
        kategori="cekirdek",
        musteri_sekmesi="profile",
        yonetici_sekmesi=None,
        gerekli_rol="client",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
    ),
    # --- Yakında (Faz 2+) — sekmesi yok, pakete göre açılıyor ---------------
    Modul(
        anahtar="whatsapp",
        ad_varsayilan={"tr": "WhatsApp gelen kutusu", "en": "WhatsApp inbox"},
        ikon="MessagesSquare",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi=None,
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        paketler=("BETA", "OMEGA", "SIGMA"),
        bagimliliklar=("bildirimler",),
        durum="yakinda",
    ),
    # --- Yalnız ajansın kendi işi (müşteriye görünmez) ----------------------
    Modul(
        anahtar="talepler",
        ad_varsayilan={"tr": "İletişim talepleri", "en": "Inquiries"},
        ikon="Mail",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi="inquiries",
        gerekli_rol="admin",
        varsayilan_acik=True,
    ),
    Modul(
        anahtar="icerik",
        ad_varsayilan={"tr": "Blog ve içerik takvimi", "en": "Blog and content calendar"},
        ikon="CalendarDays",
        kategori="icerik",
        musteri_sekmesi=None,
        yonetici_sekmesi="icerik",
        gerekli_rol="admin",
        varsayilan_acik=True,
    ),
    Modul(
        anahtar="pazaryeri",
        ad_varsayilan={"tr": "Pazar yeri", "en": "Marketplace"},
        ikon="Boxes",
        kategori="icerik",
        musteri_sekmesi=None,
        yonetici_sekmesi="marketplace",
        gerekli_rol="admin",
        varsayilan_acik=True,
    ),
    Modul(
        anahtar="analitik",
        ad_varsayilan={"tr": "Site analitiği", "en": "Site analytics"},
        ikon="BarChart3",
        kategori="analiz",
        musteri_sekmesi=None,
        yonetici_sekmesi="analytics",
        gerekli_rol="admin",
        varsayilan_acik=True,
    ),
    Modul(
        anahtar="fiyatlandirma",
        ad_varsayilan={"tr": "Fiyatlandırma", "en": "Pricing"},
        ikon="DollarSign",
        kategori="finans",
        musteri_sekmesi=None,
        yonetici_sekmesi="fiyatlandirmaV5",
        gerekli_rol="admin",
        varsayilan_acik=True,
    ),
)

MODUL_SOZLUGU: Dict[str, Modul] = {m.anahtar: m for m in MODULLER}


def modul(anahtar: str) -> Optional[Modul]:
    return MODUL_SOZLUGU.get(anahtar)


def musteri_modulleri_listesi() -> List[Modul]:
    """Müşteri başına açılıp kapanabilen (ya da müşteriye görünen) modüller."""
    return [m for m in MODULLER if m.musteriye_gorunur]


def bagimli_olanlar(anahtar: str) -> List[Modul]:
    """`anahtar`a doğrudan bağımlı modüller."""
    return [m for m in MODULLER if anahtar in m.bagimliliklar]


def sirali() -> List[Modul]:
    """Bağımlılıklar önce gelecek şekilde (topolojik) sıralı liste."""
    sonuc: List[Modul] = []
    gorulen: set = set()

    def ziyaret(m: Modul, yol: Tuple[str, ...] = ()) -> None:
        if m.anahtar in gorulen:
            return
        if m.anahtar in yol:
            raise ValueError(f"Döngüsel bağımlılık: {' → '.join(yol + (m.anahtar,))}")
        for b in m.bagimliliklar:
            hedef = MODUL_SOZLUGU.get(b)
            if hedef is not None:
                ziyaret(hedef, yol + (m.anahtar,))
        gorulen.add(m.anahtar)
        sonuc.append(m)

    for m in MODULLER:
        ziyaret(m)
    return sonuc


def manifest_hatalari() -> List[str]:
    """Manifestin iç tutarlılığı (testler ve açılışta kayda geçirmek için)."""
    hatalar: List[str] = []
    anahtarlar = [m.anahtar for m in MODULLER]
    if len(set(anahtarlar)) != len(anahtarlar):
        hatalar.append("benzersiz olmayan anahtar")
    musteri_sekmeleri = [m.musteri_sekmesi for m in MODULLER if m.musteri_sekmesi]
    if len(set(musteri_sekmeleri)) != len(musteri_sekmeleri):
        hatalar.append("aynı müşteri sekmesi iki modülde")
    yonetici_sekmeleri = [m.yonetici_sekmesi for m in MODULLER if m.yonetici_sekmesi]
    if len(set(yonetici_sekmeleri)) != len(yonetici_sekmeleri):
        hatalar.append("aynı yönetici sekmesi iki modülde")
    for m in MODULLER:
        if m.kategori not in KATEGORILER:
            hatalar.append(f"{m.anahtar}: kategori")
        if m.gerekli_rol not in ROLLER:
            hatalar.append(f"{m.anahtar}: gerekli_rol")
        if m.durum not in DURUMLAR:
            hatalar.append(f"{m.anahtar}: durum")
        if set(m.ad_varsayilan) != {"tr", "en"}:
            hatalar.append(f"{m.anahtar}: ad_varsayilan tr/en")
        for p in m.paketler:
            if p not in PAKETLER:
                hatalar.append(f"{m.anahtar}: bilinmeyen paket {p}")
        for b in m.bagimliliklar:
            if b not in MODUL_SOZLUGU:
                hatalar.append(f"{m.anahtar}: bilinmeyen bağımlılık {b}")
            elif b == m.anahtar:
                hatalar.append(f"{m.anahtar}: kendine bağımlı")
            elif MODUL_SOZLUGU[b].gerekli_rol == "admin" and m.gerekli_rol != "admin":
                hatalar.append(f"{m.anahtar}: yalnız yönetici modülüne bağımlı")
        if m.cekirdek and not m.varsayilan_acik:
            hatalar.append(f"{m.anahtar}: çekirdek modül varsayılan kapalı olamaz")
        if m.gerekli_rol == "admin" and m.musteri_sekmesi:
            hatalar.append(f"{m.anahtar}: yönetici modülünün müşteri sekmesi olamaz")
        if m.durum == "yakinda" and (m.musteri_sekmesi or m.yonetici_sekmesi):
            hatalar.append(f"{m.anahtar}: yakında olan modülün sekmesi olamaz")
        ayar_adlari = [a.anahtar for a in m.ayarlar]
        if len(set(ayar_adlari)) != len(ayar_adlari):
            hatalar.append(f"{m.anahtar}: ayar anahtarı tekrarı")
        for a in m.ayarlar:
            if a.tur not in AYAR_TURLERI:
                hatalar.append(f"{m.anahtar}.{a.anahtar}: ayar türü")
                continue
            try:
                a.dogrula(a.varsayilan)
            except ValueError:
                hatalar.append(f"{m.anahtar}.{a.anahtar}: varsayılan geçersiz")
    try:
        sirali()
    except ValueError as h:
        hatalar.append(str(h))
    return hatalar
