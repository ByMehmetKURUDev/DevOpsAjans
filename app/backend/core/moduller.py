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

KATEGORILER: Tuple[str, ...] = ("cekirdek", "hizmet", "icerik", "finans", "analiz", "dijital_kimlik", "is_araclari")
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
    # Faz 3T — teklif (öneri) ve sözleşme + basit e-imza. Müşteride "Faturalar"
    # sekmesine gömülü (kendi sekmeleri yok); yöneticide kendi sekmeleri.
    Modul(
        anahtar="teklifler",
        ad_varsayilan={"tr": "Teklifler", "en": "Quotes"},
        ikon="FileCheck2",
        kategori="finans",
        musteri_sekmesi=None,
        yonetici_sekmesi="teklifler",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        bagimliliklar=("faturalar",),
        yerlesim=("faturalar",),
    ),
    Modul(
        anahtar="sozlesmeler",
        ad_varsayilan={"tr": "Sözleşmeler ve e-imza", "en": "Contracts and e-signature"},
        ikon="FileSignature",
        kategori="finans",
        musteri_sekmesi=None,
        yonetici_sekmesi="sozlesmeler",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        bagimliliklar=("faturalar",),
        yerlesim=("faturalar",),
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
    # Faz 2G — müşteri ↔ ajans mesajlaşma (kısa yoklamayla neredeyse gerçek zamanlı).
    Modul(
        anahtar="mesajlar",
        ad_varsayilan={"tr": "Mesajlar", "en": "Messages"},
        ikon="MessagesSquare",
        kategori="hizmet",
        musteri_sekmesi="mesajlar",
        yonetici_sekmesi="mesajlar",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
    ),
    # Faz 3U — konuya özel yapay zekâ asistanları (SEO, reklam, sosyal medya…).
    # Varsayılan KAPALI ve hiçbir pakette yok: yönetici müşteri başına açıyor
    # (maliyeti olan bir özellik). `gunluk_mesaj` boşsa site ayarı
    # `asistan_gunluk_sinir` (varsayılan 50) geçerli.
    Modul(
        anahtar="uzman_asistanlar",
        ad_varsayilan={"tr": "Uzman Asistanlar", "en": "Expert Assistants"},
        ikon="Bot",
        kategori="hizmet",
        musteri_sekmesi="asistanlar",
        yonetici_sekmesi="uzmanAsistanlar",
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        ayarlar=(AyarAlani("gunluk_mesaj", "int", None, en_az=0, en_cok=100000, bos_olabilir=True),),
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
    # --- Dijital Kimlik (Faz 4) ----------------------------------------------
    # Faz 4Q — dinamik QR stüdyosu + kısa link (`/q/<kod>`), tarama analitiği,
    # toplu CSV. Varsayılan KAPALI ve pakete bağlı değil: ayrı satılan modül
    # (önerilen fiyat: aylık 19 $ — WorkDo eklentileri 19–69 $, QR SaaS
    # planları 15–35 $/ay bandında). Yönetici müşteri başına açıyor.
    # `kayit_siniri`: hesap başına en çok kayıt.
    Modul(
        anahtar="dinamik_qr",
        ad_varsayilan={"tr": "Dinamik QR ve kısa link", "en": "Dynamic QR and short links"},
        ikon="QrCode",
        kategori="dijital_kimlik",
        musteri_sekmesi="qr",
        yonetici_sekmesi="dinamikQr",
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        ayarlar=(AyarAlani("kayit_siniri", "int", 100, en_az=0, en_cok=100000),),
    ),
    # Faz 4K — dijital kartvizit + bio link (`/kart/<slug>`): vCard, QR, paylaşım
    # önizlemesi, iletişim formu, analitik. Varsayılan KAPALI, pakete bağlı değil
    # (ayrı satılan modül). `kart_siniri`: hesap başına en çok kart (ekipte her
    # kişi kendi kartını yapabilir; izin `kartvizit`).
    Modul(
        anahtar="dijital_kartvizit",
        ad_varsayilan={"tr": "Dijital kartvizit ve bio link", "en": "Digital business card and bio link"},
        ikon="IdCard",
        kategori="dijital_kimlik",
        musteri_sekmesi="kartvizit",
        yonetici_sekmesi="kartvizit",
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        ayarlar=(AyarAlani("kart_siniri", "int", 5, en_az=0, en_cok=1000),),
    ),
    # Faz 4K — Google yorum sayfası (`/yorum/<slug>`): ayrı modül, çünkü alıcısı
    # farklı (kafe, klinik, mağaza gibi yerel işletme; kartvizite ihtiyaç
    # duymayabilir) ve tek başına "masa QR'ı" olarak satılıyor. Kendi sekmesi yok:
    # "Dijital kartvizit" sekmesine gömülü (yalnız bu modül açıksa sekme yine
    # görünür — ClientPanel), aynı ekip izniyle (`kartvizit`).
    # `sayfa_siniri`: hesap başına en çok sayfa.
    Modul(
        anahtar="google_yorum_sayfasi",
        ad_varsayilan={"tr": "Google yorum sayfası", "en": "Google review page"},
        ikon="Star",
        kategori="dijital_kimlik",
        musteri_sekmesi=None,
        yonetici_sekmesi=None,
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        ayarlar=(AyarAlani("sayfa_siniri", "int", 3, en_az=0, en_cok=1000),),
        yerlesim=("kartvizit",),
    ),
    # Faz 4M — QR menü (restoran/kafe) ve WhatsApp katalog mağazası (ürün vitrini):
    # TEK motor, iki düzen; hangi modül açıksa o düzende mağaza kurulur, ikisi de
    # açıksa ikisi. Herkese açık sayfa `/menu/<slug>`, sipariş wa.me bağlantısıyla.
    # Müşteri panelinde tek sekme ("menu"): katalog modülünün kendi sekmesi yok,
    # yalnız katalog açıksa da aynı sekme görünür (ClientPanel). Varsayılan KAPALI,
    # ayrı satılan modüller (önerilen: QR menü aylık 15 $, katalog aylık 19 $).
    # `magaza_siniri` hesap başına bu düzende en çok mağaza; `urun_siniri` mağaza başına.
    Modul(
        anahtar="qr_menu",
        ad_varsayilan={"tr": "QR menü", "en": "QR menu"},
        ikon="UtensilsCrossed",
        kategori="dijital_kimlik",
        musteri_sekmesi="menu",
        yonetici_sekmesi="qrMenu",
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        ayarlar=(
            AyarAlani("magaza_siniri", "int", 1, en_az=0, en_cok=100),
            AyarAlani("urun_siniri", "int", 300, en_az=0, en_cok=100000),
        ),
    ),
    Modul(
        anahtar="whatsapp_katalog",
        ad_varsayilan={"tr": "WhatsApp katalog mağazası", "en": "WhatsApp catalog store"},
        ikon="ShoppingBag",
        kategori="dijital_kimlik",
        musteri_sekmesi=None,
        yonetici_sekmesi=None,
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        ayarlar=(
            AyarAlani("magaza_siniri", "int", 1, en_az=0, en_cok=100),
            AyarAlani("urun_siniri", "int", 300, en_az=0, en_cok=100000),
        ),
        yerlesim=("menu",),
    ),
    # --- İş araçları (Faz 5) ------------------------------------------------
    # Faz 5R — takvim ve randevu + toplantılar (Calendly benzeri): herkese açık
    # `/randevu/<slug>`, etkinlik türleri, haftalık uygunluk + istisnalar, ekip
    # (kişiye özel / sırayla / ilk müsait), .ics davet, hatırlatma, ICS besleme,
    # gömülebilir pencere. Varsayılan KAPALI, pakete bağlı değil (ayrı satılan
    # modül; önerilen fiyat aylık 12 $ — Calendly Standard 10–12 $/kişi).
    # `tur_siniri`: hesap başına en çok etkinlik türü. Ekip izni `randevu`.
    Modul(
        anahtar="randevu",
        ad_varsayilan={"tr": "Randevu ve toplantılar", "en": "Appointments and meetings"},
        ikon="CalendarCheck",
        kategori="is_araclari",
        musteri_sekmesi="randevu",
        yonetici_sekmesi="randevu",
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        ayarlar=(AyarAlani("tur_siniri", "int", 5, en_az=0, en_cok=200),),
    ),
    # Faz 4W — otomasyon kuralları ("şu olunca bunu yap": e-posta, bildirim, görev, webhook,
    # bekle) + çalıştırma günlüğü. Varsayılan KAPALI, pakete bağlı değil (ayrı satılan modül;
    # önerilen aylık 19 $). Ekip izni `otomasyon`. `kural_siniri`: hesap başına kural;
    # `calisma_dakika_siniri` / `calisma_saat_siniri`: hesap başına çalıştırma tavanı. Özel alanlar ajansın
    # yönetici aracı (modül değil); müşteri yalnız görünür alanları salt okunur görür.
    Modul(
        anahtar="otomasyon",
        ad_varsayilan={"tr": "Otomasyon kuralları", "en": "Automation rules"},
        ikon="Workflow",
        kategori="is_araclari",
        musteri_sekmesi="otomasyon",
        yonetici_sekmesi="otomasyon",
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        ayarlar=(
            AyarAlani("kural_siniri", "int", 20, en_az=0, en_cok=500),
            AyarAlani("calisma_dakika_siniri", "int", 20, en_az=1, en_cok=1000),
            AyarAlani("calisma_saat_siniri", "int", 200, en_az=1, en_cok=20000),
        ),
    ),
    # Faz 5A — AI asistan + bilgi bankası: müşterinin belgeleri/sitesi/SSS'si üzerinden yanıt veren,
    # müşterinin sitesine gömülebilen sohbet asistanı; bilmediğinde insana devreder (destek talebi).
    # Varsayılan KAPALI, pakete bağlı değil (ayrı satılan modül; önerilen fiyat aylık 29 $ — Chatbase/
    # Tidio Lyro bandı 19–49 $). Ekip izni `asistan`. `kaynak_siniri`: hesap başına en çok bilgi bankası
    # kaynağı; `url_sayfa_siniri`: URL/site haritasından en çok sayfa; `aylik_mesaj`: aya dahil yapay zekâ
    # yanıtı; `gunluk_yanit`: günlük üst sınır; `kredi_ile_asim`: dahil hak bitince kredi bloğuyla sürsün mü.
    # (Ayar adları bütün modüllerde ortak etiket anahtarı: `sayfa_siniri`/`gunluk_mesaj` başka modüllerde var.)
    Modul(
        anahtar="ai_asistan",
        ad_varsayilan={"tr": "AI asistan ve bilgi bankası", "en": "AI assistant and knowledge base"},
        ikon="BotMessageSquare",
        kategori="is_araclari",
        musteri_sekmesi="aiAsistan",
        yonetici_sekmesi="aiAsistan",
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        ayarlar=(
            AyarAlani("kaynak_siniri", "int", 20, en_az=0, en_cok=1000),
            AyarAlani("url_sayfa_siniri", "int", 50, en_az=0, en_cok=2000),
            AyarAlani("aylik_mesaj", "int", 500, en_az=0, en_cok=1_000_000),
            AyarAlani("gunluk_yanit", "int", 300, en_az=0, en_cok=100_000),
            AyarAlani("kredi_ile_asim", "bool", True),
        ),
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
    # Faz 4A — API anahtarları, imzalı webhook'lar ve uzak MCP sunucusu (Claude ile bağlama).
    # Varsayılan KAPALI, pakete bağlı değil (ayrı satılan modül; önerilen aylık 29 $ — Zapier/Make
    # entegrasyonu ve yapay zekâ asistanı bağlantısı isteyen müşteriye). Ekip izni `api`.
    # `anahtar_siniri` / `webhook_siniri`: hesap başına en çok etkin anahtar / uç noktası;
    # `dakika_siniri`: anahtar başına dakikalık istek tavanı.
    Modul(
        anahtar="api_erisimi",
        ad_varsayilan={"tr": "API ve webhook", "en": "API and webhooks"},
        ikon="KeyRound",
        kategori="hizmet",
        musteri_sekmesi="api",
        yonetici_sekmesi="api",
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        ayarlar=(
            AyarAlani("anahtar_siniri", "int", 5, en_az=0, en_cok=100),
            AyarAlani("webhook_siniri", "int", 5, en_az=0, en_cok=100),
            AyarAlani("dakika_siniri", "int", 60, en_az=1, en_cok=6000),
        ),
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
    # Faz 2B — proje yönetimi: görevler, geri bildirim, duyurular, öneri kutusu.
    # Hepsi çekirdek "projeler"in altında; kendi müşteri sekmeleri yok
    # (Projeler / Destek sekmelerine ve panelin üstüne gömülü).
    Modul(
        anahtar="gorevler",
        ad_varsayilan={"tr": "Görevler ve revizyon sayacı", "en": "Tasks and revision meter"},
        ikon="ListChecks",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi=None,
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        bagimliliklar=("projeler",),
        yerlesim=("projeler",),
    ),
    Modul(
        anahtar="geri_bildirim",
        ad_varsayilan={"tr": "Hata ve geri bildirim", "en": "Bug reports and feedback"},
        ikon="Bug",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi="geriBildirim",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        bagimliliklar=("projeler",),
        yerlesim=("genel", "destek"),
    ),
    Modul(
        anahtar="duyurular",
        ad_varsayilan={"tr": "Duyurular", "en": "Announcements"},
        ikon="Megaphone",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi="duyurular",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        bagimliliklar=("projeler",),
        yerlesim=("genel",),
    ),
    Modul(
        anahtar="oneri_kutusu",
        ad_varsayilan={"tr": "Öneri kutusu", "en": "Suggestion box"},
        ikon="Lightbulb",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi=None,
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        bagimliliklar=("projeler",),
        durum="beta",
        yerlesim=("destek",),
    ),
    # Faz 3Z — zaman takibi + iş yükü: sayaç, faturalanabilir saat, çizelge
    # onayı, faturaya aktarım. Ajans tarafı yönetici sekmesinde (personel de
    # kendi kaydını girer); müşteride proje kartına gömülü "harcanan süre"
    # (proje ayarı açıksa). Ücretli paketlerde (BETA/OMEGA/SIGMA) açık.
    Modul(
        anahtar="zaman_takibi",
        ad_varsayilan={"tr": "Zaman takibi ve iş yükü", "en": "Time tracking and workload"},
        ikon="Timer",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi="zaman",
        gerekli_rol="her_ikisi",
        varsayilan_acik=False,
        paketler=("BETA", "OMEGA", "SIGMA"),
        bagimliliklar=("projeler",),
        yerlesim=("projeler",),
    ),
    # Faz 3Z — proje şablonları: hazır görev planı, şablondan proje, kabul
    # edilen tekliften şablonlu proje. Müşteri tarafında ayrı ekranı yok
    # (şablonun müşteriye görünür görevleri proje görünümüne düşüyor):
    # ücretsiz, bütün paketlerde açık (Görevler gibi).
    Modul(
        anahtar="proje_sablonlari",
        ad_varsayilan={"tr": "Proje şablonları", "en": "Project templates"},
        ikon="LayoutTemplate",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi="projeSablonlari",
        gerekli_rol="her_ikisi",
        varsayilan_acik=True,
        paketler=TUM_PAKETLER,
        # Yalnız "projeler": müşteride Görevler kapatılabilsin (şablon yönetici aracı).
        bagimliliklar=("projeler",),
        yerlesim=("projeler",),
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
        ad_varsayilan={"tr": "Pazaryeri", "en": "Marketplace"},
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
        anahtar="baglantilar",
        ad_varsayilan={"tr": "Bağlantılar", "en": "Connections"},
        ikon="Link2",
        kategori="analiz",
        musteri_sekmesi=None,
        yonetici_sekmesi="baglantilar",
        gerekli_rol="admin",
        varsayilan_acik=True,
        bagimliliklar=("analitik",),
    ),
    # Faz 3C — ajansın kendi satış hunisi: adaylar, kanban, gömülebilir form.
    # Yalnız yönetici; müşteri portalında karşılığı yok.
    Modul(
        anahtar="crm",
        ad_varsayilan={"tr": "CRM ve aday hunisi", "en": "CRM and lead pipeline"},
        ikon="Handshake",
        kategori="hizmet",
        musteri_sekmesi=None,
        yonetici_sekmesi="crm",
        gerekli_rol="admin",
        varsayilan_acik=True,
        bagimliliklar=("talepler",),
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
