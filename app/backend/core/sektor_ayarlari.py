"""Faz 6R — hazır sektör ayarları ("sektör setleri"): başlangıç verisinin TEK kaynağı.

Ne işe yarıyor?
---------------
Bir sektör paketi (`core/sektor_paketleri.py`) hangi modüllerin açılacağını
söylüyor; set ise o modüllere sektöre uygun BAŞLANGIÇ verisi yazıyor: randevu
türleri + süreleri + tamponlar + çalışma saatleri, randevu formu soruları, AI
asistan için başlangıç SSS'si, dijital kartvizit şablonu/alanları, Google yorum
sayfası teşekkür metni, QR menü kategorileri, saha servisi kontrol listesi
şablonları, e-posta pazarlama hoş geldin dizisi TASLAĞI ve otomasyon önerileri.
Uygulayan kod `services/sektor_ayarlari.py`: yalnız BOŞ yerlere yazar, var olanı
asla ezmez, oluşturduğu her kaydı günlüğe yazar (geri alma el değmemişleri siler).

Paket ↔ set
-----------
Her paketin en az bir seti var. "Klinik, güzellik ve danışmanlık" paketinin
dört alt seçeneği var (klinik/sağlık danışmanlığı, güzellik/kuaför, spor
salonu/stüdyo, danışmanlık/koçluk): modüller aynı, başlangıç verisi farklı.
Paket bölünmedi — vitrin adresleri (`/moduller/paket/klinik-guzellik`), talep
formu ve testler aynı kalıyor; setler paket sayfasında "hazır kurulum
seçenekleri" olarak listeleniyor (adları `modulVitrini.s.<set>`, 7 dil).

Dil kararı
----------
Başlangıç içeriği Türkçe ve İngilizce yazıldı. Hesabın dili Türkçe ise Türkçe,
başka herhangi bir dilse İngilizce kullanılıyor (`icerik_dili`). Kayıtların
kendi dil alanı (randevu sayfası, kartvizit, e-posta dizisi…) seçilen dilde
kalıyor: sayfa iskeleti o dilde, müşteri metinleri kendi diline göre düzenliyor.
Yedi dilin hepsine başlangıç içeriği yazmak, çoğu zaman müşterinin zaten
değiştireceği metni yedi kez çevirmek demek; yönetim ekranındaki metinler ve
vitrin ise 7 dilde.

Kurallar (test `set_hatalari()` ve `yasak_ifadeler()` ile denetliyor)
---------------------------------------------------------------------
* Uydurma yok: fiyat, adres, telefon, kişi adı ya da tıbbi iddia yazılmıyor.
  SSS cevapları modülün gerçekten yaptığı şeyi anlatıyor (randevu sayfası,
  onay e-postasındaki iptal bağlantısı, hatırlatma, insana devir).
* Sağlık/güzellik/spor setleri (`kvkk_ozel`): randevu formunda sağlık bilgisi
  İSTENMİYOR; karşılama ve tür açıklamalarında "formda sağlık bilgisi
  paylaşmayın, gerekirse görüşmede açık rızanızla" notu var. Bu setlerde
  teşhis/tedavi/garanti gibi ifadeler yasak.
* Google yorum metninde koşul yok (gating yok): herkese aynı çağrı.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from core import sektor_paketleri as sp

DILLER: Tuple[str, ...] = ("tr", "en", "de", "ru", "zh", "hi", "ar")
#: Başlangıç içeriğinin yazıldığı diller.
ICERIK_DILLERI: Tuple[str, ...] = ("tr", "en")

Metin = Dict[str, str]  # {"tr": ..., "en": ...}


def _m(tr: str, en: str) -> Metin:
    return {"tr": tr, "en": en}


def icerik_dili(dil: Optional[str]) -> str:
    """Hesabın dili → başlangıç içeriğinin dili (tr ise tr, değilse en)."""
    return "tr" if (dil or "tr").strip().lower()[:2] == "tr" else "en"


def dil_duzelt(dil: Optional[str]) -> str:
    d = (dil or "tr").strip().lower()[:2]
    return d if d in DILLER else "tr"


# ---------------------------------------------------------------------------
# Yapılar
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Soru:
    """Randevu formu sorusu (`services/randevu.sorular_duzelt` biçimi)."""

    kimlik: str
    tur: str  # metin | uzun | secim | onay
    etiket: Metin
    zorunlu: bool = False
    secenekler: Tuple[Metin, ...] = ()

    def sozluk(self, dil: str) -> Dict[str, object]:
        return {"id": self.kimlik, "tur": self.tur, "etiket": self.etiket[dil], "zorunlu": self.zorunlu,
                "secenekler": [s[dil] for s in self.secenekler]}


@dataclass(frozen=True)
class RandevuTuru:
    anahtar: str  # tür slug'ı (ASCII)
    ad: Metin
    aciklama: Metin
    sure_dk: int
    adim_dk: int
    #: jitsi (görüntülü) | telefon (boş: "biz sizi arayalım") | yuz_yuze (adres gerekir)
    konum_turu: str
    tampon_once_dk: int = 0
    tampon_sonra_dk: int = 0
    kapasite: int = 1
    telefon: str = "istege_bagli"
    sorular: Tuple[Soru, ...] = ()
    renk: str = "#7c3aed"


@dataclass(frozen=True)
class RandevuSeti:
    karsilama: Metin
    #: Haftalık çalışma saatleri (0 = pazartesi), `[["09:00", "18:00"], …]`.
    haftalik: Dict[str, Tuple[Tuple[str, str], ...]]
    turler: Tuple[RandevuTuru, ...]

    def haftalik_sozluk(self) -> Dict[str, List[List[str]]]:
        return {g: [list(a) for a in araliklar] for g, araliklar in self.haftalik.items()}


@dataclass(frozen=True)
class SssMaddesi:
    soru: Metin
    cevap: Metin


@dataclass(frozen=True)
class AsistanSeti:
    ad: Metin
    karsilama: Metin
    sss_baslik: Metin
    sss: Tuple[SssMaddesi, ...]
    yasakli_konular: Tuple[Metin, ...] = ()
    #: Önerilen sorular SSS'nin ilk kaçı (asistan penceresindeki hızlı düğmeler).
    onerilen_sayisi: int = 3


@dataclass(frozen=True)
class KartSeti:
    sablon: str  # services/kartvizit.SABLONLAR
    #: Hizmet listesi randevu türlerinden (ad + açıklama).
    hizmetler_randevudan: bool = True
    calisma_saatleri: bool = True
    randevu_baglantisi: bool = True


@dataclass(frozen=True)
class MenuSeti:
    kategoriler: Tuple[Metin, ...]


@dataclass(frozen=True)
class SahaMaddesi:
    kimlik: str
    metin: Metin
    tur: str  # evet_hayir | metin | sayi | olcum | foto
    zorunlu: bool = False


@dataclass(frozen=True)
class SahaSablonu:
    anahtar: str
    ad: Metin
    is_turu: str
    maddeler: Tuple[SahaMaddesi, ...]


@dataclass(frozen=True)
class SahaSeti:
    sablonlar: Tuple[SahaSablonu, ...]
    #: Randevu → iş emri kancası (yalnız ayar satırı yoksa yazılır).
    randevu_kancasi: bool = True
    randevu_is_turu: str = "kesif"


@dataclass(frozen=True)
class EpostaAdimi:
    bekle_gun: int
    konu: Metin
    onizleme: Metin
    baslik: Metin
    metin: Metin


@dataclass(frozen=True)
class EpostaSeti:
    liste_adi: Metin
    liste_aciklama: Metin
    dizi_adi: Metin
    adimlar: Tuple[EpostaAdimi, ...]


@dataclass(frozen=True)
class HazirSet:
    anahtar: str
    paket: str
    ikon: str  # src/lib/modulIkonlari.ts'te olan bir lucide adı
    kvkk_ozel: bool = False
    randevu: Optional[RandevuSeti] = None
    asistan: Optional[AsistanSeti] = None
    kartvizit: Optional[KartSeti] = None
    yorum_tesekkur: Optional[Metin] = None
    menu: Optional[MenuSeti] = None
    saha: Optional[SahaSeti] = None
    eposta: Optional[EpostaSeti] = None
    #: Otomasyon › Hazır şablonlar'da "sektörünüz için önerilen" işaretlenecek şablonlar (kurulmaz).
    otomasyon: Tuple[str, ...] = ()

    def moduller(self) -> List[str]:
        """Başlangıç verisi yazılan modüller (uygulama sırası)."""
        sira = []
        if self.randevu:
            sira.append("randevu")
        if self.asistan:
            sira.append("ai_asistan")
        if self.kartvizit:
            sira.append("dijital_kartvizit")
        if self.yorum_tesekkur:
            sira.append("google_yorum_sayfasi")
        if self.menu:
            sira.append("qr_menu")
        if self.saha:
            sira.append("saha_servisi")
        if self.eposta:
            sira.append("eposta_pazarlama")
        if self.otomasyon:
            sira.append("otomasyon")
        return sira

    def sozluk(self) -> Dict[str, object]:
        return {"anahtar": self.anahtar, "paket": self.paket, "ikon": self.ikon, "kvkk_ozel": self.kvkk_ozel,
                "moduller": self.moduller(), "otomasyon": list(self.otomasyon)}


# ---------------------------------------------------------------------------
# Ortak parçalar
# ---------------------------------------------------------------------------
def _gunler(gunler: Iterable[int], *araliklar: Tuple[str, str]) -> Dict[str, Tuple[Tuple[str, str], ...]]:
    return {str(g): tuple(araliklar) for g in gunler}


HAFTA_ICI = range(0, 5)

_ILETISIM_SORUSU = Soru(
    "iletisim", "secim", _m("Size nasıl ulaşalım?", "How should we contact you?"),
    secenekler=(_m("Telefon", "Phone"), _m("E-posta", "Email")),
)
_SSS_RANDEVU = (
    SssMaddesi(
        _m("Nasıl randevu alabilirim?", "How do I book an appointment?"),
        _m("Randevu sayfamızdan size uygun gün ve saati seçip formu doldurmanız yeterli; onay e-postası hemen gelir.",
           "Choose a day and time that suits you on our booking page and fill in the short form; a confirmation "
           "email arrives right away."),
    ),
    SssMaddesi(
        _m("Randevumu nasıl iptal eder ya da değiştiririm?", "How can I cancel or change my appointment?"),
        _m("Onay e-postanızdaki bağlantıdan randevunuzu iptal edebilir ya da yeni bir saat seçebilirsiniz.",
           "Use the link in your confirmation email to cancel your appointment or pick a new time."),
    ),
    SssMaddesi(
        _m("Randevudan önce hatırlatma gönderiyor musunuz?", "Do you send a reminder before the appointment?"),
        _m("Evet, randevunuzdan önce e-posta ile hatırlatma gönderiyoruz.",
           "Yes, we send you a reminder by email before your appointment."),
    ),
)
_SSS_BASLIK = _m("Başlangıç SSS — işletmenize göre düzenleyin", "Starter FAQ — edit it for your business")
_YASAK_SAGLIK = (
    _m("Bir kişinin sağlık durumu hakkında yorum", "Comments on anyone's health condition"),
    _m("İlaç ya da doz önerisi", "Medication or dosage advice"),
)
_KVKK_NOTU = _m(
    "Lütfen bu formda sağlık bilgisi paylaşmayın; gerekli bilgiler görüşmede, açık rızanız alınarak sorulur.",
    "Please do not share health information in this form; anything needed is asked during your visit, "
    "with your explicit consent.",
)


def _kvkk(tr: str, en: str) -> Metin:
    """Tür açıklaması + KVKK notu (sağlık bilgisi istenmez)."""
    return _m(f"{tr} {_KVKK_NOTU['tr']}", f"{en} {_KVKK_NOTU['en']}")


# ---------------------------------------------------------------------------
# Setler — sıra: paket sırası, paket içinde varsayılan set önce
# ---------------------------------------------------------------------------
HAZIR_SETLER: Tuple[HazirSet, ...] = (
    # --- Restoran ve kafe ----------------------------------------------------------------------
    HazirSet(
        anahtar="restoran_kafe",
        paket="restoran_kafe",
        ikon="UtensilsCrossed",
        menu=MenuSeti(kategoriler=(
            _m("Kahvaltı", "Breakfast"),
            _m("Başlangıçlar", "Starters"),
            _m("Ana yemekler", "Mains"),
            _m("Tatlılar", "Desserts"),
            _m("Sıcak içecekler", "Hot drinks"),
            _m("Soğuk içecekler", "Cold drinks"),
        )),
        yorum_tesekkur=_m(
            "Afiyet olsun! Bizi tercih ettiğiniz için teşekkürler; deneyiminizi Google'da paylaşırsanız seviniriz.",
            "Thank you for dining with us! We'd love to hear about your experience on Google.",
        ),
    ),
    # --- Klinik, güzellik ve danışmanlık: dört alt seçenek -------------------------------------
    HazirSet(
        anahtar="klinik_saglik",
        paket="klinik_guzellik",
        ikon="Activity",
        kvkk_ozel=True,
        randevu=RandevuSeti(
            karsilama=_m(
                "Size uygun günü ve saati seçin; onay e-postası hemen gelir. Lütfen randevu formunda sağlık bilgisi "
                "paylaşmayın — gerekli bilgiler görüşmede, açık rızanız alınarak sorulur.",
                "Pick a day and time that suits you; a confirmation email arrives right away. Please do not share "
                "health information in the booking form — anything needed is asked during your visit, with your "
                "explicit consent.",
            ),
            haftalik={**_gunler(HAFTA_ICI, ("09:00", "12:30"), ("13:30", "18:00")), **_gunler((5,), ("09:00", "13:00"))},
            turler=(
                RandevuTuru(
                    "ilk-muayene", _m("İlk muayene", "First visit"),
                    _kvkk("İlk kez gelecekler için yaklaşık 30 dakikalık randevu.",
                          "An appointment of about 30 minutes for first-time visitors."),
                    sure_dk=30, adim_dk=15, konum_turu="yuz_yuze", tampon_sonra_dk=10, telefon="zorunlu",
                    sorular=(_ILETISIM_SORUSU,), renk="#0ea5e9",
                ),
                RandevuTuru(
                    "kontrol", _m("Kontrol", "Follow-up visit"),
                    _kvkk("Daha önce görüştüğümüz kişiler için kısa kontrol randevusu.",
                          "A short follow-up appointment for people we have already seen."),
                    sure_dk=15, adim_dk=15, konum_turu="yuz_yuze", tampon_sonra_dk=5, telefon="zorunlu",
                    sorular=(_ILETISIM_SORUSU,), renk="#14b8a6",
                ),
                RandevuTuru(
                    "online-on-gorusme", _m("Online ön görüşme", "Online pre-consultation"),
                    _kvkk("Görüntülü kısa ön görüşme; bağlantı onay e-postanızda yer alır.",
                          "A short video call; the link is in your confirmation email."),
                    sure_dk=20, adim_dk=20, konum_turu="jitsi", tampon_sonra_dk=10,
                    sorular=(_ILETISIM_SORUSU,), renk="#8b5cf6",
                ),
            ),
        ),
        asistan=AsistanSeti(
            ad=_m("Randevu asistanı", "Appointment assistant"),
            karsilama=_m(
                "Merhaba! Randevu, çalışma saatleri ve işleyişle ilgili sorularınızı yanıtlayabilirim. Sağlığınızla "
                "ilgili sorularınızı görüşmede uzmanımıza iletebilirsiniz.",
                "Hi! I can answer questions about appointments, opening hours and how things work. Please bring "
                "questions about your health to your appointment.",
            ),
            sss_baslik=_SSS_BASLIK,
            sss=_SSS_RANDEVU + (
                SssMaddesi(
                    _m("Randevu formunda sağlık bilgisi paylaşmalı mıyım?", "Should I share health information in the booking form?"),
                    _m("Hayır, lütfen formda sağlık bilgisi paylaşmayın. Gerekli bilgiler görüşmede, açık rızanız alınarak sorulur.",
                       "No, please do not share health information in the form. Anything needed is asked during your "
                       "visit, with your explicit consent."),
                ),
                SssMaddesi(
                    _m("Asistan sağlıkla ilgili sorularımı yanıtlar mı?", "Can the assistant answer questions about my health?"),
                    _m("Hayır. Bu asistan yalnız randevu ve işleyişle ilgili genel soruları yanıtlar; sağlığınızla ilgili "
                       "her konuyu görüşmede uzmanımızla konuşabilirsiniz.",
                       "No. This assistant only answers general questions about appointments and how things work; "
                       "please discuss anything about your health with our specialist during your visit."),
                ),
            ),
            yasakli_konular=_YASAK_SAGLIK,
        ),
        kartvizit=KartSeti(sablon="beyaz"),
        yorum_tesekkur=_m(
            "Bizi tercih ettiğiniz için teşekkür ederiz. Deneyiminizi Google'da paylaşırsanız bizi arayan diğer kişilere "
            "de yol göstermiş olursunuz.",
            "Thank you for choosing us. Sharing your experience on Google helps others who are looking for us.",
        ),
        otomasyon=("kart_mesaj_otomatik_yanit",),
    ),
    HazirSet(
        anahtar="guzellik_kuafor",
        paket="klinik_guzellik",
        ikon="Star",
        kvkk_ozel=True,
        randevu=RandevuSeti(
            karsilama=_m(
                "Hizmeti ve size uygun saati seçin; onay e-postası hemen gelir. Alerji gibi sağlık bilgilerinizi formda "
                "paylaşmayın; gerekirse randevuda yüz yüze konuşalım.",
                "Choose a service and a time that suits you; a confirmation email arrives right away. Please don't "
                "share health details such as allergies in the form — we can talk about them in person.",
            ),
            haftalik=_gunler(range(0, 6), ("10:00", "20:00")),
            turler=(
                RandevuTuru(
                    "sac-kesimi", _m("Saç kesimi", "Haircut"),
                    _m("Yaklaşık 45 dakika.", "About 45 minutes."),
                    sure_dk=45, adim_dk=15, konum_turu="yuz_yuze", tampon_sonra_dk=10,
                    sorular=(Soru("uzunluk", "secim", _m("Saç uzunluğunuz", "Your hair length"),
                                  secenekler=(_m("Kısa", "Short"), _m("Orta", "Medium"), _m("Uzun", "Long"))),),
                    renk="#ec4899",
                ),
                RandevuTuru(
                    "sac-boyama", _m("Saç boyama", "Hair colouring"),
                    _m("Yaklaşık 2 saat.", "About 2 hours."),
                    sure_dk=120, adim_dk=30, konum_turu="yuz_yuze", tampon_sonra_dk=15,
                    sorular=(Soru("renk", "metin", _m("Aklınızdaki renk (isteğe bağlı)", "Colour you have in mind (optional)")),),
                    renk="#a855f7",
                ),
                RandevuTuru(
                    "fon", _m("Fön", "Blow-dry"),
                    _m("Yaklaşık 30 dakika.", "About 30 minutes."),
                    sure_dk=30, adim_dk=15, konum_turu="yuz_yuze", tampon_sonra_dk=5, renk="#f97316",
                ),
                RandevuTuru(
                    "manikur", _m("Manikür", "Manicure"),
                    _m("Yaklaşık 45 dakika.", "About 45 minutes."),
                    sure_dk=45, adim_dk=15, konum_turu="yuz_yuze", tampon_sonra_dk=10, renk="#f43f5e",
                ),
            ),
        ),
        asistan=AsistanSeti(
            ad=_m("Salon asistanı", "Salon assistant"),
            karsilama=_m("Merhaba! Hizmetlerimiz, randevu ve çalışma saatleri hakkında sorularınızı yanıtlayabilirim.",
                         "Hi! I can answer your questions about our services, bookings and opening hours."),
            sss_baslik=_SSS_BASLIK,
            sss=_SSS_RANDEVU + (
                SssMaddesi(
                    _m("Hizmetlerin ne kadar sürdüğünü nereden görebilirim?", "Where can I see how long each service takes?"),
                    _m("Randevu sayfamızda her hizmetin yaklaşık süresi yazılıdır.",
                       "Our booking page shows the approximate duration of each service."),
                ),
                SssMaddesi(
                    _m("Fiyat bilgisi alabilir miyim?", "Can I get price information?"),
                    _m("Güncel fiyatlarımız için bu sohbetten bize mesaj bırakabilirsiniz; ekibimiz size dönüş yapar.",
                       "For our current prices, leave us a message in this chat and our team will get back to you."),
                ),
            ),
            yasakli_konular=_YASAK_SAGLIK,
        ),
        kartvizit=KartSeti(sablon="canli"),
        yorum_tesekkur=_m(
            "Bizi tercih ettiğiniz için teşekkürler! Deneyiminizi Google'da paylaşırsanız çok seviniriz.",
            "Thanks for visiting us! We'd love to hear about your experience on Google.",
        ),
        otomasyon=("kart_mesaj_otomatik_yanit",),
    ),
    HazirSet(
        anahtar="spor_studyo",
        paket="klinik_guzellik",
        ikon="Timer",
        kvkk_ozel=True,
        randevu=RandevuSeti(
            karsilama=_m(
                "Seansınızı ya da dersinizi seçin; onay e-postası hemen gelir. Sağlık durumunuzla ilgili bilgileri formda "
                "paylaşmayın; gerekirse ilk görüşmede, açık rızanızla konuşuruz.",
                "Choose your session or class; a confirmation email arrives right away. Please don't share health "
                "details in the form — if needed we'll discuss them at your first visit, with your explicit consent.",
            ),
            haftalik={**_gunler(HAFTA_ICI, ("07:00", "22:00")), **_gunler((5, 6), ("09:00", "18:00"))},
            turler=(
                RandevuTuru(
                    "pt-seansi", _m("Kişisel antrenman (PT)", "Personal training (PT)"),
                    _m("Antrenörünüzle birebir 60 dakika.", "A one-to-one 60-minute session with your trainer."),
                    sure_dk=60, adim_dk=30, konum_turu="yuz_yuze", tampon_sonra_dk=10,
                    sorular=(Soru("deneyim", "secim", _m("Deneyim düzeyiniz", "Your experience level"),
                                  secenekler=(_m("Yeni başlıyorum", "Beginner"), _m("Orta", "Intermediate"),
                                              _m("İleri", "Advanced"))),),
                    renk="#22c55e",
                ),
                RandevuTuru(
                    "grup-dersi", _m("Grup dersi", "Group class"),
                    _m("60 dakikalık grup dersi; kontenjan sınırlıdır.", "A 60-minute group class with limited places."),
                    sure_dk=60, adim_dk=60, konum_turu="yuz_yuze", tampon_sonra_dk=15, kapasite=12, renk="#eab308",
                ),
                RandevuTuru(
                    "tanisma", _m("Tanışma ve salon turu", "Intro and studio tour"),
                    _m("İlk kez gelecekler için 30 dakikalık tanışma.", "A 30-minute introduction for first-timers."),
                    sure_dk=30, adim_dk=30, konum_turu="yuz_yuze", sorular=(_ILETISIM_SORUSU,), renk="#06b6d4",
                ),
            ),
        ),
        asistan=AsistanSeti(
            ad=_m("Stüdyo asistanı", "Studio assistant"),
            karsilama=_m("Merhaba! Dersler, seanslar ve randevularla ilgili sorularınızı yanıtlayabilirim.",
                         "Hi! I can answer your questions about classes, sessions and bookings."),
            sss_baslik=_SSS_BASLIK,
            sss=_SSS_RANDEVU + (
                SssMaddesi(
                    _m("Grup derslerinde kontenjan var mı?", "Are group classes limited?"),
                    _m("Evet, grup derslerinin kontenjanı sınırlıdır; randevu sayfasında yalnız boş yer kalan saatler görünür.",
                       "Yes, group classes have limited places; the booking page only shows times with places left."),
                ),
                SssMaddesi(
                    _m("İlk kez geleceğim, nereden başlamalıyım?", "It's my first time — where should I start?"),
                    _m("Randevu sayfamızdan tanışma ve salon turu randevusu alabilirsiniz.",
                       "You can book an intro and studio tour on our booking page."),
                ),
            ),
            yasakli_konular=_YASAK_SAGLIK,
        ),
        kartvizit=KartSeti(sablon="canli"),
        yorum_tesekkur=_m(
            "Bizimle antrenman yaptığınız için teşekkürler! Deneyiminizi Google'da paylaşırsanız seviniriz.",
            "Thanks for training with us! We'd appreciate it if you shared your experience on Google.",
        ),
        otomasyon=("kart_mesaj_otomatik_yanit",),
    ),
    HazirSet(
        anahtar="danismanlik_kocluk",
        paket="klinik_guzellik",
        ikon="Handshake",
        randevu=RandevuSeti(
            karsilama=_m("Görüşme türünü ve size uygun saati seçin; görüntülü görüşme bağlantısı onay e-postasında yer alır.",
                         "Choose a session type and a time that suits you; the video call link is in your confirmation email."),
            haftalik=_gunler(HAFTA_ICI, ("09:00", "18:00")),
            turler=(
                RandevuTuru(
                    "tanisma", _m("Tanışma görüşmesi", "Intro call"),
                    _m("Birbirimizi tanımak için kısa görüntülü görüşme.", "A short video call to get to know each other."),
                    sure_dk=20, adim_dk=20, konum_turu="jitsi", tampon_sonra_dk=10,
                    sorular=(Soru("konu", "uzun", _m("Konuşmak istediğiniz konu (isteğe bağlı)",
                                                    "What would you like to talk about? (optional)")),),
                    renk="#6366f1",
                ),
                RandevuTuru(
                    "seans", _m("Danışmanlık seansı", "Consulting session"),
                    _m("60 dakikalık görüntülü seans.", "A 60-minute video session."),
                    sure_dk=60, adim_dk=30, konum_turu="jitsi", tampon_sonra_dk=15,
                    sorular=(Soru("kurum", "metin", _m("Şirket ya da kurum (varsa)", "Company or organisation (if any)")),),
                    renk="#7c3aed",
                ),
                RandevuTuru(
                    "takip", _m("Takip görüşmesi", "Follow-up call"),
                    _m("30 dakikalık görüntülü takip görüşmesi.", "A 30-minute follow-up video call."),
                    sure_dk=30, adim_dk=30, konum_turu="jitsi", tampon_sonra_dk=10, renk="#0ea5e9",
                ),
            ),
        ),
        asistan=AsistanSeti(
            ad=_m("Randevu asistanı", "Booking assistant"),
            karsilama=_m("Merhaba! Görüşmeler ve randevularla ilgili sorularınızı yanıtlayabilirim.",
                         "Hi! I can answer your questions about sessions and bookings."),
            sss_baslik=_SSS_BASLIK,
            sss=_SSS_RANDEVU + (
                SssMaddesi(
                    _m("Görüşmeler online mı yapılıyor?", "Are sessions held online?"),
                    _m("Randevu sayfamızdaki görüşmeler görüntülü bağlantıyla yapılır; bağlantı onay e-postanızda yer alır.",
                       "The sessions on our booking page are held by video call; the link is in your confirmation email."),
                ),
                SssMaddesi(
                    _m("Görüşmeye nasıl hazırlanabilirim?", "How can I prepare for the session?"),
                    _m("Randevu formuna konuşmak istediğiniz konuyu kısaca yazmanız görüşmeyi daha verimli kılar.",
                       "Briefly noting your topic in the booking form helps make the session more productive."),
                ),
            ),
        ),
        kartvizit=KartSeti(sablon="kurumsal"),
        yorum_tesekkur=_m(
            "Görüşmemiz için teşekkür ederim. Deneyiminizi Google'da paylaşırsanız çok sevinirim.",
            "Thank you for our session. I'd be grateful if you shared your experience on Google.",
        ),
        otomasyon=("kart_mesaj_otomatik_yanit",),
    ),
    # --- Teknik servis ve bakım ------------------------------------------------------------------
    HazirSet(
        anahtar="teknik_servis",
        paket="teknik_servis",
        ikon="Wrench",
        randevu=RandevuSeti(
            karsilama=_m(
                "Size uygun zamanı seçin, adresinizi ve arızayı kısaca yazın; ekibimiz sizi arayarak ziyareti teyit eder.",
                "Pick a time that suits you and briefly describe the address and the issue; our team will call you "
                "to confirm the visit.",
            ),
            haftalik=_gunler(range(0, 6), ("09:00", "18:00")),
            turler=(
                RandevuTuru(
                    "kesif", _m("Keşif ziyareti", "Site survey visit"),
                    _m("Yerinde inceleme ve ölçüm; ziyaret öncesi sizi arıyoruz.",
                       "An on-site look and measurements; we call you before the visit."),
                    sure_dk=60, adim_dk=60, konum_turu="telefon", tampon_sonra_dk=30, telefon="zorunlu",
                    sorular=(
                        Soru("adres", "uzun", _m("Ziyaret adresi", "Visit address"), zorunlu=True),
                        Soru("cihaz", "secim", _m("Cihaz ya da hizmet", "Appliance or service"),
                             secenekler=(_m("Klima", "Air conditioner"), _m("Kombi", "Combi boiler"),
                                         _m("Beyaz eşya", "Home appliance"), _m("Diğer", "Other"))),
                    ),
                    renk="#0ea5e9",
                ),
                RandevuTuru(
                    "ariza", _m("Arıza ve servis ziyareti", "Repair visit"),
                    _m("Arıza bildirimi; ziyaret öncesi sizi arıyoruz.", "Report an issue; we call you before the visit."),
                    sure_dk=90, adim_dk=30, konum_turu="telefon", tampon_sonra_dk=30, telefon="zorunlu",
                    sorular=(
                        Soru("adres", "uzun", _m("Ziyaret adresi", "Visit address"), zorunlu=True),
                        Soru("cihaz", "secim", _m("Cihaz ya da hizmet", "Appliance or service"),
                             secenekler=(_m("Klima", "Air conditioner"), _m("Kombi", "Combi boiler"),
                                         _m("Beyaz eşya", "Home appliance"), _m("Diğer", "Other"))),
                        Soru("aciklama", "uzun", _m("Arızayı kısaca anlatın", "Briefly describe the issue")),
                    ),
                    renk="#f97316",
                ),
                RandevuTuru(
                    "bakim", _m("Periyodik bakım", "Scheduled maintenance"),
                    _m("Planlı bakım ziyareti; ziyaret öncesi sizi arıyoruz.", "A planned maintenance visit; we call you before the visit."),
                    sure_dk=60, adim_dk=60, konum_turu="telefon", tampon_sonra_dk=30, telefon="zorunlu",
                    sorular=(
                        Soru("adres", "uzun", _m("Ziyaret adresi", "Visit address"), zorunlu=True),
                        Soru("cihaz", "secim", _m("Cihaz ya da hizmet", "Appliance or service"),
                             secenekler=(_m("Klima", "Air conditioner"), _m("Kombi", "Combi boiler"),
                                         _m("Beyaz eşya", "Home appliance"), _m("Diğer", "Other"))),
                    ),
                    renk="#22c55e",
                ),
            ),
        ),
        saha=SahaSeti(sablonlar=(
            SahaSablonu("sektor_kesif", _m("Keşif ziyareti", "Site survey"), "kesif", (
                SahaMaddesi("ihtiyac", _m("Müşterinin ihtiyacı not edildi", "Customer's needs noted"), "evet_hayir", True),
                SahaMaddesi("olcum", _m("Ölçüm ve alan bilgisi", "Measurements and site details"), "metin"),
                SahaMaddesi("mevcut", _m("Mevcut cihaz (marka/model)", "Existing appliance (brand/model)"), "metin"),
                SahaMaddesi("oneri", _m("Önerilen çözüm", "Proposed solution"), "metin", True),
                SahaMaddesi("foto", _m("Keşif fotoğrafı", "Survey photo"), "foto"),
            )),
            SahaSablonu("sektor_ariza", _m("Arıza onarımı", "Repair"), "ariza", (
                SahaMaddesi("tespit", _m("Arıza tespit edildi", "Fault identified"), "evet_hayir", True),
                SahaMaddesi("islem", _m("Yapılan işlem", "Work done"), "metin", True),
                SahaMaddesi("parca", _m("Değişen parça", "Parts replaced"), "metin"),
                SahaMaddesi("calisiyor", _m("Cihaz çalışır durumda teslim edildi", "Appliance handed over in working order"),
                            "evet_hayir", True),
                SahaMaddesi("foto", _m("Onarım sonrası fotoğraf", "Photo after repair"), "foto"),
            )),
            SahaSablonu("sektor_kurulum", _m("Kurulum", "Installation"), "kurulum", (
                SahaMaddesi("yer", _m("Montaj yeri müşteriyle teyit edildi", "Mounting location confirmed with customer"),
                            "evet_hayir", True),
                SahaMaddesi("baglanti", _m("Bağlantılar kontrol edildi", "Connections checked"), "evet_hayir", True),
                SahaMaddesi("test", _m("Test çalıştırması yapıldı", "Test run completed"), "evet_hayir", True),
                SahaMaddesi("bilgi", _m("Müşteriye kullanım bilgisi verildi", "Usage explained to customer"), "evet_hayir"),
                SahaMaddesi("foto", _m("Kurulum fotoğrafı", "Installation photo"), "foto"),
            )),
        )),
        yorum_tesekkur=_m(
            "Servisimiz için teşekkürler! Deneyiminizi Google'da paylaşırsanız diğer müşterilerimize de yol göstermiş olursunuz.",
            "Thank you for choosing our service! Sharing your experience on Google helps other customers.",
        ),
        otomasyon=("is_emri_acil_bildirim",),
    ),
    # --- Eğitim, kurs ve etkinlik ------------------------------------------------------------------
    HazirSet(
        anahtar="egitim_etkinlik",
        paket="egitim_etkinlik",
        ikon="Ticket",
        randevu=RandevuSeti(
            karsilama=_m("Tanışma görüşmesi ya da deneme dersi için size uygun saati seçin; bağlantı onay e-postasında yer alır.",
                         "Pick a time for an intro call or a trial lesson; the link is in your confirmation email."),
            haftalik={**_gunler(HAFTA_ICI, ("10:00", "18:00")), **_gunler((5,), ("10:00", "14:00"))},
            turler=(
                RandevuTuru(
                    "tanisma", _m("Tanışma görüşmesi", "Intro call"),
                    _m("Eğitimlerimizi tanıtan kısa görüntülü görüşme.", "A short video call about our courses."),
                    sure_dk=20, adim_dk=20, konum_turu="jitsi", tampon_sonra_dk=10,
                    sorular=(Soru("ilgi", "metin", _m("İlgilendiğiniz eğitim ya da kurs", "Course you're interested in")),),
                    renk="#6366f1",
                ),
                RandevuTuru(
                    "deneme-dersi", _m("Deneme dersi (online)", "Trial lesson (online)"),
                    _m("45 dakikalık görüntülü deneme dersi.", "A 45-minute online trial lesson."),
                    sure_dk=45, adim_dk=15, konum_turu="jitsi", tampon_sonra_dk=15,
                    sorular=(Soru("seviye", "secim", _m("Seviyeniz", "Your level"),
                                  secenekler=(_m("Başlangıç", "Beginner"), _m("Orta", "Intermediate"),
                                              _m("İleri", "Advanced"))),),
                    renk="#22c55e",
                ),
            ),
        ),
        eposta=EpostaSeti(
            liste_adi=_m("Bülten aboneleri", "Newsletter subscribers"),
            liste_aciklama=_m("Hazır ayarlarla oluşturuldu; bir abonelik formuna bağlayabilirsiniz.",
                              "Created by the starter setup; you can connect it to a subscription form."),
            dizi_adi=_m("Hoş geldin dizisi (taslak)", "Welcome series (draft)"),
            adimlar=(
                EpostaAdimi(
                    0, _m("Aramıza hoş geldiniz", "Welcome aboard"),
                    _m("Yeni eğitim ve etkinliklerimizi ilk siz duyacaksınız.", "You'll be the first to hear about new courses and events."),
                    _m("Hoş geldiniz!", "Welcome!"),
                    _m("Bültenimize katıldığınız için teşekkür ederiz. Yeni kurs, atölye ve etkinliklerimizi ilk siz duyacaksınız.",
                       "Thank you for joining our newsletter. You'll be the first to hear about new courses, workshops and events."),
                ),
                EpostaAdimi(
                    3, _m("Takvimimize göz atın", "Have a look at our calendar"),
                    _m("Size uygun eğitim ve etkinlikleri kaçırmayın.", "Don't miss the courses and events that suit you."),
                    _m("Yaklaşan eğitim ve etkinlikler", "Upcoming courses and events"),
                    _m("Takvimimizdeki eğitim ve etkinliklere göz atın; ilginizi çeken bir konu varsa yerinizi erkenden ayırtabilirsiniz.",
                       "Take a look at the courses and events on our calendar; if something catches your eye, you can "
                       "reserve your place early."),
                ),
                EpostaAdimi(
                    7, _m("Aklınıza takılan bir soru var mı?", "Any questions?"),
                    _m("Bu e-postayı yanıtlamanız yeterli.", "Just reply to this email."),
                    _m("Size nasıl yardımcı olabiliriz?", "How can we help?"),
                    _m("Eğitimlerimizle ilgili sorularınız için bu e-postayı yanıtlamanız yeterli; ekibimiz size dönüş yapar.",
                       "If you have any questions about our courses, just reply to this email and our team will get back to you."),
                ),
            ),
        ),
    ),
    # --- Ajans ve serbest çalışan -------------------------------------------------------------------
    HazirSet(
        anahtar="ajans_serbest",
        paket="ajans_serbest",
        ikon="PenTool",
        randevu=RandevuSeti(
            karsilama=_m("Tanışmak ya da projenizi konuşmak için size uygun saati seçin; görüntülü görüşme bağlantısı onay "
                         "e-postasında yer alır.",
                         "Pick a time to get to know each other or discuss your project; the video call link is in your "
                         "confirmation email."),
            haftalik=_gunler(HAFTA_ICI, ("10:00", "17:00")),
            turler=(
                RandevuTuru(
                    "tanisma", _m("Tanışma görüşmesi", "Intro call"),
                    _m("30 dakikalık görüntülü tanışma.", "A 30-minute introductory video call."),
                    sure_dk=30, adim_dk=30, konum_turu="jitsi", tampon_sonra_dk=10,
                    sorular=(
                        Soru("marka", "metin", _m("Şirket ya da marka", "Company or brand")),
                        Soru("web", "metin", _m("Web siteniz (varsa)", "Your website (if any)")),
                    ),
                    renk="#a855f7",
                ),
                RandevuTuru(
                    "proje", _m("Proje görüşmesi", "Project call"),
                    _m("Projenizi ayrıntılı konuştuğumuz 60 dakikalık görüşme.", "A 60-minute call to discuss your project in detail."),
                    sure_dk=60, adim_dk=30, konum_turu="jitsi", tampon_sonra_dk=15,
                    sorular=(Soru("ihtiyac", "uzun", _m("Kısaca ihtiyacınız", "Briefly, what do you need?")),),
                    renk="#ec4899",
                ),
            ),
        ),
        kartvizit=KartSeti(sablon="kurumsal", hizmetler_randevudan=False, calisma_saatleri=False),
        otomasyon=("kart_mesaj_otomatik_yanit", "teklif_kabul_gorev", "destek_acil_bildirim"),
    ),
    # --- E-ticaret ve KOBİ ---------------------------------------------------------------------------
    HazirSet(
        anahtar="eticaret_kobi",
        paket="eticaret_kobi",
        ikon="ShoppingBag",
        asistan=AsistanSeti(
            ad=_m("Mağaza asistanı", "Store assistant"),
            karsilama=_m("Merhaba! Sipariş, kampanya ve iletişimle ilgili genel sorularınızı yanıtlayabilirim.",
                         "Hi! I can answer general questions about orders, offers and how to reach us."),
            sss_baslik=_SSS_BASLIK,
            sss=(
                SssMaddesi(
                    _m("Siparişim hakkında nasıl bilgi alabilirim?", "How can I get information about my order?"),
                    _m("Sipariş numaranızla birlikte bu sohbetten bize mesaj bırakın; ekibimiz size e-posta ile dönüş yapar.",
                       "Leave us a message in this chat with your order number; our team will get back to you by email."),
                ),
                SssMaddesi(
                    _m("Kampanyalardan nasıl haberdar olurum?", "How can I hear about offers?"),
                    _m("Bültenimize abone olabilirsiniz; abonelikten istediğiniz an e-postadaki bağlantıyla çıkabilirsiniz.",
                       "You can subscribe to our newsletter and unsubscribe at any time with the link in each email."),
                ),
                SssMaddesi(
                    _m("Size nasıl ulaşabilirim?", "How can I reach you?"),
                    _m("Bu sohbet penceresinden mesaj bırakabilirsiniz; ekibimiz en kısa sürede size dönüş yapar.",
                       "You can leave a message in this chat window; our team will get back to you as soon as possible."),
                ),
            ),
        ),
        eposta=EpostaSeti(
            liste_adi=_m("Bülten aboneleri", "Newsletter subscribers"),
            liste_aciklama=_m("Hazır ayarlarla oluşturuldu; bir abonelik formuna bağlayabilirsiniz.",
                              "Created by the starter setup; you can connect it to a subscription form."),
            dizi_adi=_m("Hoş geldin dizisi (taslak)", "Welcome series (draft)"),
            adimlar=(
                EpostaAdimi(
                    0, _m("Hoş geldiniz", "Welcome"),
                    _m("Kampanya ve yeniliklerden ilk siz haberdar olacaksınız.", "You'll be the first to hear about offers and news."),
                    _m("Aramıza hoş geldiniz!", "Welcome aboard!"),
                    _m("Bültenimize katıldığınız için teşekkür ederiz. Kampanya ve yeniliklerimizi ilk siz duyacaksınız.",
                       "Thank you for joining our newsletter. You'll be the first to hear about our offers and news."),
                ),
                EpostaAdimi(
                    2, _m("Mağazamızda neler var?", "What's in our store?"),
                    _m("Öne çıkan ürünlere ve yeni gelenlere göz atın.", "Have a look at featured products and new arrivals."),
                    _m("Öne çıkanlar ve yeni gelenler", "Featured products and new arrivals"),
                    _m("Öne çıkan ürünlerimize ve yeni gelenlere mağazamızdan göz atabilirsiniz.",
                       "Take a look at our featured products and new arrivals in our store."),
                ),
                EpostaAdimi(
                    6, _m("Size nasıl yardımcı olabiliriz?", "How can we help?"),
                    _m("Bu e-postayı yanıtlamanız yeterli.", "Just reply to this email."),
                    _m("Sorunuz mu var?", "Got a question?"),
                    _m("Sipariş ya da ürünlerle ilgili sorularınız için bu e-postayı yanıtlamanız yeterli; ekibimiz size dönüş yapar.",
                       "If you have any questions about orders or products, just reply to this email and our team will get back to you."),
                ),
            ),
        ),
        otomasyon=("destek_acil_bildirim",),
    ),
)

SET_SOZLUGU: Dict[str, HazirSet] = {s.anahtar: s for s in HAZIR_SETLER}


def hazir_set(anahtar: Optional[str]) -> Optional[HazirSet]:
    return SET_SOZLUGU.get(anahtar or "")


def paket_setleri(paket: str) -> List[str]:
    """Paketin setleri (ilki varsayılan)."""
    return [s.anahtar for s in HAZIR_SETLER if s.paket == paket]


def varsayilan_set(paket: str) -> Optional[str]:
    liste = paket_setleri(paket)
    return liste[0] if liste else None


# ---------------------------------------------------------------------------
# Tutarlılık ve yasak ifade taraması (testler çağırıyor)
# ---------------------------------------------------------------------------
#: Sağlık/güzellik/spor setlerinde geçmemesi gereken ifadeler (tıbbi iddia / vaat).
YASAK_IFADELER: Tuple[str, ...] = (
    r"te[şs]his", r"tedavi", r"garanti", r"tan[ıi]\s+koy", r"iyile[şs]", r"[şs]ifa", r"kesin\s+sonu[çc]",
    r"diagnos", r"\btreat", r"\bcure", r"guarantee", r"\bheal(?:s|ed|ing)?\b",
)


def metinleri(nesne: object) -> List[str]:
    """Bir yapının içindeki bütün metinler (tarama ve tutarlılık için)."""
    sonuc: List[str] = []
    if isinstance(nesne, str):
        return [nesne]
    if isinstance(nesne, dict):
        for v in nesne.values():
            sonuc += metinleri(v)
        return sonuc
    if isinstance(nesne, (list, tuple)):
        for v in nesne:
            sonuc += metinleri(v)
        return sonuc
    if hasattr(nesne, "__dataclass_fields__"):
        for ad in nesne.__dataclass_fields__:  # type: ignore[attr-defined]
            if ad in ("anahtar", "paket", "ikon", "kimlik", "tur", "konum_turu", "telefon", "renk", "is_turu", "sablon"):
                continue
            sonuc += metinleri(getattr(nesne, ad))
    return sonuc


def yasak_ifadeler(s: HazirSet) -> List[str]:
    bulunan = []
    for metin in metinleri(s):
        for desen in YASAK_IFADELER:
            if re.search(desen, metin, flags=re.IGNORECASE):
                bulunan.append(f"{s.anahtar}: '{desen}' → {metin[:80]}")
    return bulunan


def _metin_hatasi(m: object, yer: str) -> List[str]:
    if not isinstance(m, dict) or set(m) != set(ICERIK_DILLERI) or not all(isinstance(v, str) and v.strip() for v in m.values()):
        return [f"{yer}: tr/en metin eksik"]
    if m["tr"] == m["en"]:
        return [f"{yer}: İngilizce metin Türkçenin kopyası"]
    return []


def set_hatalari() -> List[str]:
    """Setlerin iç tutarlılığı: paket, modül, sınırlar, alan değerleri, metinler."""
    from services import kartvizit as kv
    from services import randevu as rv
    from services import saha_servisi as ss
    from services.otomasyon_kural import SABLON_SOZLUGU

    hatalar: List[str] = []
    anahtarlar = [s.anahtar for s in HAZIR_SETLER]
    if len(set(anahtarlar)) != len(anahtarlar):
        hatalar.append("benzersiz olmayan set anahtarı")
    for p in sp.SEKTOR_PAKETLERI:
        if not paket_setleri(p.anahtar):
            hatalar.append(f"{p.anahtar}: paketin seti yok")
    for s in HAZIR_SETLER:
        p = sp.paket(s.paket)
        if p is None:
            hatalar.append(f"{s.anahtar}: bilinmeyen paket {s.paket}")
            continue
        if s.anahtar in sp.PAKET_SOZLUGU and s.anahtar != s.paket:
            hatalar.append(f"{s.anahtar}: başka bir paketin anahtarıyla çakışıyor")
        for k in s.moduller():
            # Otomasyon önerisi veri yazmıyor: paketin modülü olmasa da (müşteride açıksa) gösterilir.
            if k != "otomasyon" and k not in p.moduller:
                hatalar.append(f"{s.anahtar}: {k} paketin modüllerinde yok")
        if s.randevu:
            r = s.randevu
            hatalar += _metin_hatasi(r.karsilama, f"{s.anahtar}.randevu.karsilama")
            try:
                rv.haftalik_duzelt(r.haftalik_sozluk())
            except rv.RandevuHatasi as h:
                hatalar.append(f"{s.anahtar}: haftalık saatler geçersiz ({h.kod})")
            if not 1 <= len(r.turler) <= 4:
                hatalar.append(f"{s.anahtar}: 1-4 randevu türü")
            if len({t.anahtar for t in r.turler}) != len(r.turler):
                hatalar.append(f"{s.anahtar}: tür anahtarı tekrarı")
            for t in r.turler:
                yer = f"{s.anahtar}.{t.anahtar}"
                hatalar += _metin_hatasi(t.ad, yer + ".ad") + _metin_hatasi(t.aciklama, yer + ".aciklama")
                if not rv.SLUG_DESENI.match(t.anahtar) or t.anahtar in rv.AYRILMIS_SLUGLAR:
                    hatalar.append(f"{yer}: slug geçersiz")
                if not rv.SURE_EN_AZ <= t.sure_dk <= rv.SURE_EN_COK or t.adim_dk not in rv.ADIMLAR:
                    hatalar.append(f"{yer}: süre/adım")
                if t.konum_turu not in ("jitsi", "telefon", "yuz_yuze"):
                    hatalar.append(f"{yer}: konum")
                if t.telefon not in rv.TELEFON_SECENEKLERI:
                    hatalar.append(f"{yer}: telefon")
                if not 0 <= t.tampon_once_dk <= rv.TAMPON_EN_COK or not 0 <= t.tampon_sonra_dk <= rv.TAMPON_EN_COK:
                    hatalar.append(f"{yer}: tampon")
                if not 1 <= t.kapasite <= rv.KAPASITE_EN_COK:
                    hatalar.append(f"{yer}: kapasite")
                for dil in ICERIK_DILLERI:
                    try:
                        rv.sorular_duzelt([q.sozluk(dil) for q in t.sorular])
                    except rv.RandevuHatasi as h:
                        hatalar.append(f"{yer}: sorular ({dil}) {h.kod}")
                for q in t.sorular:
                    hatalar += _metin_hatasi(q.etiket, f"{yer}.{q.kimlik}")
        if s.asistan:
            a = s.asistan
            for ad, m in (("ad", a.ad), ("karsilama", a.karsilama), ("sss_baslik", a.sss_baslik)):
                hatalar += _metin_hatasi(m, f"{s.anahtar}.asistan.{ad}")
            if not 2 <= len(a.sss) <= 8 or not 0 <= a.onerilen_sayisi <= 6:
                hatalar.append(f"{s.anahtar}: SSS sayısı")
            for i, x in enumerate(a.sss):
                hatalar += _metin_hatasi(x.soru, f"{s.anahtar}.sss.{i}.soru") + _metin_hatasi(x.cevap, f"{s.anahtar}.sss.{i}.cevap")
                if any(len(v) > 150 for v in x.soru.values()):
                    hatalar.append(f"{s.anahtar}.sss.{i}: önerilen soru 150 karakteri aşıyor")
            for i, x in enumerate(a.yasakli_konular):
                hatalar += _metin_hatasi(x, f"{s.anahtar}.asistan.yasakli.{i}")
            if any(len(v) > 80 for v in a.ad.values()) or any(len(v) > 500 for v in a.karsilama.values()):
                hatalar.append(f"{s.anahtar}: asistan metni uzun")
        if s.kartvizit:
            if s.kartvizit.sablon not in kv.SABLONLAR:
                hatalar.append(f"{s.anahtar}: kartvizit şablonu geçersiz")
            if (s.kartvizit.hizmetler_randevudan or s.kartvizit.randevu_baglantisi) and not s.randevu:
                hatalar.append(f"{s.anahtar}: kartvizit randevuya bağlı ama randevu seti yok")
        if s.yorum_tesekkur:
            hatalar += _metin_hatasi(s.yorum_tesekkur, f"{s.anahtar}.yorum")
            if any(len(v) > kv.SINIR["tesekkur"] for v in s.yorum_tesekkur.values()):
                hatalar.append(f"{s.anahtar}: yorum metni uzun")
        if s.menu:
            if not 1 <= len(s.menu.kategoriler) <= 20:
                hatalar.append(f"{s.anahtar}: menü kategori sayısı")
            for i, k in enumerate(s.menu.kategoriler):
                hatalar += _metin_hatasi(k, f"{s.anahtar}.menu.{i}")
                if any(len(v) > 80 for v in k.values()):
                    hatalar.append(f"{s.anahtar}.menu.{i}: uzun")
        if s.saha:
            if s.saha.randevu_is_turu not in ss.IS_TURLERI:
                hatalar.append(f"{s.anahtar}: randevu iş türü")
            for sb in s.saha.sablonlar:
                if sb.is_turu not in ss.IS_TURLERI or not sb.maddeler or len(sb.anahtar) > 32:
                    hatalar.append(f"{s.anahtar}.{sb.anahtar}: şablon")
                hatalar += _metin_hatasi(sb.ad, f"{s.anahtar}.{sb.anahtar}.ad")
                kimlikler = [md.kimlik for md in sb.maddeler]
                if len(set(kimlikler)) != len(kimlikler):
                    hatalar.append(f"{s.anahtar}.{sb.anahtar}: madde tekrarı")
                for md in sb.maddeler:
                    if md.tur not in ss.MADDE_TURLERI:
                        hatalar.append(f"{s.anahtar}.{sb.anahtar}.{md.kimlik}: tür")
                    hatalar += _metin_hatasi(md.metin, f"{s.anahtar}.{sb.anahtar}.{md.kimlik}")
        if s.eposta:
            e = s.eposta
            for ad, m in (("liste_adi", e.liste_adi), ("liste_aciklama", e.liste_aciklama), ("dizi_adi", e.dizi_adi)):
                hatalar += _metin_hatasi(m, f"{s.anahtar}.eposta.{ad}")
            if not 1 <= len(e.adimlar) <= 5:
                hatalar.append(f"{s.anahtar}: e-posta adım sayısı")
            for i, ad_ in enumerate(e.adimlar):
                for ad, m in (("konu", ad_.konu), ("onizleme", ad_.onizleme), ("baslik", ad_.baslik), ("metin", ad_.metin)):
                    hatalar += _metin_hatasi(m, f"{s.anahtar}.eposta.{i}.{ad}")
        for k in s.otomasyon:
            sablon = SABLON_SOZLUGU.get(k)
            if sablon is None or sablon.yalniz_ajans:
                hatalar.append(f"{s.anahtar}: otomasyon şablonu {k} müşteride yok")
        if s.kvkk_ozel:
            hatalar += yasak_ifadeler(s)
    return hatalar


__all__ = [
    "DILLER", "ICERIK_DILLERI", "icerik_dili", "dil_duzelt", "Soru", "RandevuTuru", "RandevuSeti", "SssMaddesi",
    "AsistanSeti", "KartSeti", "MenuSeti", "SahaMaddesi", "SahaSablonu", "SahaSeti", "EpostaAdimi", "EpostaSeti",
    "HazirSet", "HAZIR_SETLER", "SET_SOZLUGU", "hazir_set", "paket_setleri", "varsayilan_set", "YASAK_IFADELER",
    "metinleri", "yasak_ifadeler", "set_hatalari",
]
