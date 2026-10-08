"""Faz 2E — müşteri hesabında birden çok kişi (kişi bazlı yetki) ve hesaplar arası geçiş.

Kavram
------
"Müşteri hesabı" = sahibinin e-postası (bugünkü kimlik). Hesaba üye
eklenebiliyor (`hesap_uyeleri`); her üyenin bir rolü ve modül izinleri var.
Kişi, jetonundaki e-postayla giriş yapıyor; hangi hesapta çalıştığını
`X-MK-Hesap` başlığıyla söylüyor. Karar istek başında bir kez veriliyor
(`middlewares/hesap_baglami.py`) ve uçlar ortak yardımcıdan okuyor
(`dependencies/hesap_baglami.py`).

Roller ve varsayılan izinler
----------------------------
* `yonetici` — bütün modüller; ekibi yönetebilir (kendinden yüksek yetki veremez).
* `uye` — proje/görev/destek/dosya/site/rapor; faturaları göremez.
* `fatura` — fatura/kredi/abonelik; proje ve destek göremez.

Sahip ya da hesap yöneticisi izinleri üye başına özelleştirebiliyor.

Önbellek
--------
Her istekte veritabanına gitmemek için üyelik kararı süreç içinde 25 sn
önbellekte (2D'deki oturum önbelleği gibi). Üyelik değişen her işlem
önbelleği hemen boşaltıyor: pasif yapılan / silinen üyenin erişimi aynı
süreçte anında, en kötü ihtimalle 25 sn içinde her yerde bitiyor.
"""

import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from models.hesap_uyeleri import HesapUyeleri
from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Modül izinleri (ön yüzdeki sekmelerle eşleşiyor).
IZINLER: Tuple[str, ...] = (
    "projeler",
    "gorevler",
    "destek",
    "dosyalar",
    "faturalar",
    "siteler",
    "raporlar",
    "krediler",
    "abonelikler",
    # Faz 2G — müşteri ↔ ajans mesajlaşma.
    "mesajlar",
    # Faz 3U — Uzman Asistanlar (yapay zekâ sohbetleri).
    "asistanlar",
    # Faz 4Q — Dinamik QR ve kısa link.
    "qr",
    # Faz 4K — Dijital kartvizit ve Google yorum sayfası (ekipte her kişi kendi kartını yapabilir).
    "kartvizit",
    # Faz 4M — QR menü ve WhatsApp katalog mağazası.
    "menu",
    # Faz 4A — API anahtarları ve webhook'lar (yalnız sahip/hesap yöneticisi verebilir; üye ve
    # fatura rolünün varsayılanında yok).
    "api",
    # Faz 5R — randevu ve toplantılar (ekipte her kişi kendi uygunluğunu yönetir).
    "randevu",
    # Faz 4W — otomasyon kuralları ve günlüğü (e-posta gönderebildiği için yalnız sahip/hesap
    # yöneticisinin varsayılanında; üye ve fatura rolüne ayrıca verilir).
    "otomasyon",
    # Faz 5A — AI asistan ve bilgi bankası (sohbet kayıtları ziyaretçi kişisel verisi taşır).
    "asistan",
    # Faz 5I — İçerik stüdyosu (marka sesi, AI yazar, planlayıcı) ve ajansın onaya sunduğu
    # içeriklere karar (onay / revizyon). Üyenin varsayılanında var.
    "icerik",
    # Faz 5M — e-posta pazarlama (kişi listesi, kampanya gönderimi: yalnız sahip/hesap yöneticisi
    # verebilir; üye ve fatura rolünün varsayılanında yok — `api` gibi).
    "pazarlama",
    # Faz 6S — saha servisi: `saha_yonetim` (sevk panosu, iş emri, müşteri/cihaz, şablon, malzeme,
    # rapor) ve `saha_teknisyen` (yalnız kendine atanan işler — "İşlerim"). Teknisyen ayrı bir rol
    # değil: üye rolünde yalnız `saha_teknisyen` seçilir. Üye/fatura rolünün varsayılanında yok.
    "saha_yonetim",
    "saha_teknisyen",
    # Faz 6E — etkinlik ve bilet: `etkinlik` yönetim (katılımcı kişisel verisi, duyuru e-postası; üyenin
    # varsayılanında yok), `etkinlik_giris` YALNIZ kapıda okutma (üyenin varsayılanında var).
    "etkinlik",
    "etkinlik_giris",
    # Faz 6P — stok ve satış noktası: `stok` yönetim (ürün, maliyet, stok hareketi, sayım, rapor, ayar; üyenin
    # varsayılanında yok) ve `kasa` YALNIZ satış ekranı (üyenin varsayılanında var: kasiyer = üye).
    "stok",
    "kasa",
    # Faz 6K — eğitim: `egitim` yönetim (kurs, öğrenci + veli kişisel verisi, duyuru, sertifika; üyenin
    # varsayılanında yok), `egitim_egitmen` YALNIZ e-postası kursun eğitmen listesinde geçen kurslarda yoklama +
    # ödev notu (iletişim/veli bilgisi görmez; üyenin varsayılanında yok — ayrıca verilir).
    "egitim",
    "egitim_egitmen",
    # Faz 5B — belgeler, wiki ve strateji araçları: hesabın kendi belgeleri (modül `belgeler`).
    # Ajansın paylaştığı belgeleri okumak için `belgeler` ya da `dosyalar` yeter. Üyenin varsayılanında var.
    "belgeler",
    # Faz 6I — insan kaynakları: personel kartı (kişisel veri), izin onayı/reddi, vardiya planı, portal bağlantısı.
    # Yönetim izni; üye ve fatura rolünün varsayılanında YOK (ayrıca verilir).
    "ik",
    # Faz 6H — hukuk bürosu (müvekkil, dosya, takvim, masraf, portal). Avukat–müvekkil sırrı: üyenin
    # varsayılanında YOK (ayrıca verilir); `gizli` dosyayı izin de yetmez (yalnız sahip + sorumlu avukat).
    "hukuk",
    # Faz 6M — ön muhasebe (hesaplar, gelir-gider, cari, bütçe, raporlar, otomatik aktarma ayarı). Finansal veri:
    # üye ve fatura rolünün varsayılanında YOK (ayrıca verilir). `muhasebe_okur`: YALNIZ raporlar (özet, bütçe
    # durumu, yaşlandırma, aylık / kategori / nakit akışı / KDV ve CSV'leri) — örn. mali müşavir; yazamaz.
    "muhasebe",
    "muhasebe_okur",
)
ROLLER: Tuple[str, ...] = ("yonetici", "uye", "fatura")
DURUMLAR: Tuple[str, ...] = ("davet", "aktif", "pasif")

#: Hesap sahibinin (örtük) rolü — tabloda satırı yok.
SAHIP = "sahip"

ROL_VARSAYILAN: Dict[str, Tuple[str, ...]] = {
    "yonetici": IZINLER,
    # Faz 4K/4M: üye kendi kartvizitini ve menü/katalog mağazalarını da yönetir.
    "uye": ("projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar", "asistanlar", "qr",
            "kartvizit", "menu", "randevu", "asistan", "icerik", "etkinlik_giris", "kasa", "belgeler"),
    "fatura": ("faturalar", "krediler", "abonelikler"),
}

#: Eski (Faz 2G, 3U ve 4Q öncesi) rol varsayılanları. Üyelik satırında izinler açıkça (JSON)
#: saklanıyor; yeni bir izin eklenince eski üyeler onu kendiliğinden almazdı.
#: Kayıtlı liste TAM OLARAK eski varsayılansa (kimse özelleştirmemiş) bugünkü
#: varsayılan geçerli; özelleştirilmiş listelere dokunulmuyor.
ESKI_VARSAYILANLAR: Dict[str, Tuple[frozenset, ...]] = {
    "yonetici": (
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "faturalar", "siteler", "raporlar", "krediler", "abonelikler"}),
        # Faz 2G–3U arası varsayılan (mesajlar var, asistanlar yok).
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "faturalar", "siteler", "raporlar", "krediler",
                   "abonelikler", "mesajlar"}),
        # Faz 3U–4Q arası varsayılan (asistanlar var, qr yok).
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "faturalar", "siteler", "raporlar", "krediler",
                   "abonelikler", "mesajlar", "asistanlar"}),
        # Faz 4Q–4K/4M arası varsayılan (qr var, kartvizit ve menu yok).
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "faturalar", "siteler", "raporlar", "krediler",
                   "abonelikler", "mesajlar", "asistanlar", "qr"}),
        # Faz 4K/4M–4A/5R arası varsayılan (kartvizit ve menu var; api ve randevu yok).
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "faturalar", "siteler", "raporlar", "krediler",
                   "abonelikler", "mesajlar", "asistanlar", "qr", "kartvizit", "menu"}),
        # Faz 5R–5A/5M arası varsayılan (api ve randevu var; asistan ve pazarlama yok).
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "faturalar", "siteler", "raporlar", "krediler",
                   "abonelikler", "mesajlar", "asistanlar", "qr", "kartvizit", "menu", "api", "randevu"}),
        # Faz 5A/5M–5I/6S/6E arası varsayılan (otomasyon, asistan ve pazarlama var; icerik ve saha/etkinlik izinleri yok).
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "faturalar", "siteler", "raporlar", "krediler",
                   "abonelikler", "mesajlar", "asistanlar", "qr", "kartvizit", "menu", "api", "randevu", "otomasyon",
                   "asistan", "pazarlama"}),
        # Faz 5I/6S/6E–6P/6K/5B arası varsayılan (icerik, saha ve etkinlik izinleri var; stok, kasa, egitim ve belgeler izinleri yok).
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "faturalar", "siteler", "raporlar", "krediler",
                   "abonelikler", "mesajlar", "asistanlar", "qr", "kartvizit", "menu", "api", "randevu", "otomasyon",
                   "asistan", "icerik", "pazarlama", "saha_yonetim", "saha_teknisyen", "etkinlik", "etkinlik_giris"}),
        # Faz 6P/6K/5B–6I/6H arası varsayılan (canlıdaki: stok, kasa, egitim, egitim_egitmen ve belgeler var; ik ve hukuk yok).
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "faturalar", "siteler", "raporlar", "krediler",
                   "abonelikler", "mesajlar", "asistanlar", "qr", "kartvizit", "menu", "api", "randevu", "otomasyon",
                   "asistan", "icerik", "pazarlama", "saha_yonetim", "saha_teknisyen", "etkinlik", "etkinlik_giris",
                   "stok", "kasa", "egitim", "egitim_egitmen", "belgeler"}),
        # Faz 6I/6H–6M arası varsayılan (canlıdaki: ik ve hukuk var; muhasebe yok).
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "faturalar", "siteler", "raporlar", "krediler",
                   "abonelikler", "mesajlar", "asistanlar", "qr", "kartvizit", "menu", "api", "randevu", "otomasyon",
                   "asistan", "icerik", "pazarlama", "saha_yonetim", "saha_teknisyen", "etkinlik", "etkinlik_giris",
                   "stok", "kasa", "egitim", "egitim_egitmen", "belgeler", "ik", "hukuk"}),
    ),
    "uye": (
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar"}),
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar"}),
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar", "asistanlar"}),
        # Faz 4Q–4M arası varsayılan.
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar", "asistanlar", "qr"}),
        # Faz 4M–5R arası varsayılan.
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar", "asistanlar", "qr",
                   "kartvizit", "menu"}),
        # Faz 5R–5A arası varsayılan.
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar", "asistanlar", "qr",
                   "kartvizit", "menu", "randevu"}),
        # Faz 5A–5I/6E arası varsayılan (asistan var; icerik ve etkinlik_giris yok).
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar", "asistanlar", "qr",
                   "kartvizit", "menu", "randevu", "asistan"}),
        # Faz 5I/6E–6P/5B arası varsayılan (icerik ve etkinlik_giris var; kasa ve belgeler yok).
        frozenset({"projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar", "asistanlar", "qr",
                   "kartvizit", "menu", "randevu", "asistan", "icerik", "etkinlik_giris"}),
    ),
}

#: Ekibi yönetebilen roller.
YONETEN_ROLLER = frozenset({SAHIP, "yonetici"})

DAVET_GUN = 7
ONBELLEK_SN = 25.0
SON_KULLANIM_ARALIGI = timedelta(minutes=5)
#: Bir hesapta en çok bu kadar üye (kötüye kullanım sınırı).
EN_COK_UYE = 50

#: Bildirim olayı → o olayı görmesi için gereken izin. Burada OLMAYAN olaylar
#: üyelere genişletilmiyor: kişisel olaylar (yeni oturum, öneri durumu),
#: davetler ve imzalı işlem bağlantıları (bağlantı bir yetki belgesi, yalnız
#: adı geçen alıcıya gitmeli).
OLAY_IZNI: Dict[str, str] = {
    "ticket_reply": "destek",
    "project_stage": "projeler",
    "stage_change": "projeler",
    "project_note": "projeler",
    "project_delivery": "projeler",
    "geri_bildirim_durumu": "projeler",
    "gorev_guncellendi": "gorevler",
    "invoice": "faturalar",
    "invoice_paid": "faturalar",
    "yenileme_faturasi": "faturalar",
    "kredi_yuklendi": "krediler",
    "kredi_azaldi": "krediler",
    "site_analizi_rapor": "siteler",
    "site_coktu": "siteler",
    "site_duzeldi": "siteler",
    "bitis_yaklasiyor": "siteler",
    "seo_dususu": "siteler",
    "dosya_eklendi": "dosyalar",
    "belge_talebi": "dosyalar",
    "belge_hatirlatma": "dosyalar",
    "belge_gecikti": "dosyalar",
    "aylik_rapor": "raporlar",
    # Faz 2G — karşı taraf okumadıysa toplu mesaj bildirimi.
    "mesaj_yeni": "mesajlar",
    # Faz 3T — vadesi geçen fatura ve sözleşme bitişi faturalar iznine. Teklif/
    # sözleşme bağlantı e-postaları (`teklif_gonderildi`, `sozlesme_imza_bekliyor`)
    # BİLEREK yok: bağlantı bir yetki belgesi, yalnız adı geçen alıcıya.
    "fatura_gecikti": "faturalar",
    "sozlesme_bitis": "faturalar",
    # Faz 4K — kartın "iletişim bırak" mesajı ve yorum sayfasının özel geri bildirimi.
    "kartvizit_mesaj": "kartvizit",
    "yorum_geri_bildirim": "kartvizit",
    # Faz 4M — menü/katalog mağazasına yeni WhatsApp siparişi.
    "menu_siparis": "menu",
    # Faz 4A — art arda başarısız teslimat: webhook uç noktası otomatik durduruldu.
    "webhook_pasiflesti": "api",
    # Faz 5R — yeni / yeniden planlanan / iptal edilen randevu (sahibine).
    "randevu_yeni": "randevu",
    "randevu_degisti": "randevu",
    "randevu_iptal": "randevu",
    # Faz 4W — otomasyon kuralının "panel bildirimi" eylemi (hesaba).
    "otomasyon_bildirimi": "otomasyon",
    # Faz 5A — AI asistan ziyaretçiyi insana devretti.
    "asistan_devir": "asistan",
    # Faz 5I — içerik "paylaşıma hazır" hatırlatması (müşterinin kendi içeriği). Onay isteği
    # (imzalı bağlantı) burada YOK: yalnız adı geçen alıcıya gider.
    "icerik_hatirlatma": "icerik",
    # Faz 5M — pazarlama gönderimleri askıya alındı.
    "pazarlama_askiya_alindi": "pazarlama",
    # Faz 6S — bakım zamanı gelen cihazlar (hesaba; sevk/yönetim izni olan üyelere de).
    # Teknisyene "yeni iş" (`saha_is_atandi`) kişisel: yalnız atanan kişiye gider (burada yok).
    "saha_bakim_zamani": "saha_yonetim",
    # Faz 6P — kritik stok seviyesine inen ürünler (stok yönetimi izni olan üyelere de).
    "stok_kritik": "stok",
    # Faz 6E — etkinliğe yeni kayıt / katılımcı iptali (sahibine).
    "etkinlik_kayit": "etkinlik",
    "etkinlik_iptal": "etkinlik",
    # Faz 6K — kursa yeni kayıt (sahibine).
    "egitim_kayit": "egitim",
    # Faz 5B — ajans hesapla bir belge paylaştı.
    "belge_paylasildi": "belgeler",
    # Faz 6I — personel portaldan izin talebi gönderdi (sahibine; `ik` izinli üyelere de).
    "ik_izin_talebi": "ik",
    # Faz 6H — müvekkil portalından mesaj (içeriksiz bildirim; `hukuk` izinli üyelere de). Süre/duruşma
    # hatırlatması (`hukuk_hatirlatma`) BİLEREK yok: yalnız sorumlu avukata (ya da hesap sahibine) gider.
    "hukuk_portal_mesaj": "hukuk",
    # Faz 6M — ön muhasebe: kategori bütçesi aşıldı (hesaba; `muhasebe` izinli üyelere de — okur değil).
    "muhasebe_butce": "muhasebe",
}

DAVET_OLAYI = "hesap_davet"


class HesapHatasi(Exception):
    """Uca çevrilecek hata: HTTP durumu + kod (ön yüz yedi dilde metin kuruyor)."""

    def __init__(self, durum: int, kod: str, **ek: Any):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


@dataclass(frozen=True)
class HesapBaglami:
    """İsteğin etkin hesabı: kim (kişi), hangi hesapta, hangi rol ve izinlerle."""

    kisi_email: str
    hesap_email: str
    rol: str
    izinler: Tuple[str, ...] = field(default_factory=tuple)
    #: Üyelik satırı (sahipte ve yöneticide None).
    uye_id: Optional[int] = None
    #: Ajans yöneticisi (role=admin): başlık yok sayılıyor, her şeye yetkili.
    yonetici: bool = False

    @property
    def kendi_hesabi(self) -> bool:
        return self.hesap_email == self.kisi_email

    @property
    def ekibi_yonetebilir(self) -> bool:
        return self.yonetici or self.rol in YONETEN_ROLLER

    def izin_var(self, izin: str) -> bool:
        return self.yonetici or self.rol == SAHIP or izin in self.izinler

    def sozluk(self) -> Dict[str, Any]:
        return {
            "kisi_email": self.kisi_email,
            "hesap_email": self.hesap_email,
            "rol": self.rol,
            "izinler": list(self.izinler),
        }


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def eposta_duzelt(eposta: Optional[str]) -> str:
    return (eposta or "").strip().lower()


def eposta_gecerli_mi(eposta: str) -> bool:
    if not eposta or len(eposta) > 254 or eposta.count("@") != 1:
        return False
    yerel, alan = eposta.split("@")
    return bool(yerel) and "." in alan and not any(c.isspace() for c in eposta)


def eposta_maskele(eposta: Optional[str]) -> str:
    """`ahmet@alan.com` → `a***@alan.com` (davet bağlantısı elden ele gidebilir)."""
    eposta = eposta_duzelt(eposta)
    if "@" not in eposta:
        return "***"
    yerel, alan = eposta.split("@", 1)
    return f"{yerel[:1]}***@{alan}"


def jeton_ozeti(jeton: str) -> str:
    return hashlib.sha256((jeton or "").encode("utf-8")).hexdigest()


def tam_baglam(eposta: str, *, yonetici: bool = False) -> HesapBaglami:
    """Kişinin kendi hesabı: tam yetki."""
    return HesapBaglami(kisi_email=eposta, hesap_email=eposta, rol=SAHIP, izinler=IZINLER, yonetici=yonetici)


def izinleri_coz(ham: Optional[str], rol: str) -> Tuple[str, ...]:
    """Kayıtlı JSON → izin demeti (bozuksa rol varsayılanı)."""
    try:
        deger = json.loads(ham) if ham else None
    except (TypeError, ValueError):
        deger = None
    if not isinstance(deger, list):
        return tuple(ROL_VARSAYILAN.get(rol, ()))
    secili = {str(x) for x in deger}
    if any(secili == eski for eski in ESKI_VARSAYILANLAR.get(rol, ())):
        return tuple(ROL_VARSAYILAN[rol])
    return tuple(i for i in IZINLER if i in secili)


def izinleri_duzelt(ham: Optional[Iterable[str]], rol: str) -> Tuple[str, ...]:
    """İstekten gelen izin listesi: None → rol varsayılanı; bilinmeyen → 400."""
    if ham is None:
        return tuple(ROL_VARSAYILAN[rol])
    secili = set()
    for x in ham:
        x = str(x).strip()
        if x not in IZINLER:
            raise HesapHatasi(400, "izin_gecersiz", izin=x)
        secili.add(x)
    return tuple(i for i in IZINLER if i in secili)


def rol_duzelt(rol: Optional[str]) -> str:
    r = (rol or "").strip().lower()
    if r not in ROLLER:
        raise HesapHatasi(400, "rol_gecersiz")
    return r


def site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


def davet_baglantisi(jeton: str) -> str:
    return f"{site_adresi()}/hesap-davet/{jeton}"


def gecerli_durum(satir: HesapUyeleri, an: Optional[datetime] = None) -> str:
    """Davetin süresi geçmişse `suresi_doldu` (yazılmış durum `davet` kalıyor)."""
    an = an or simdi()
    if satir.durum == "davet":
        bitis = _utc(satir.davet_bitis)
        if bitis is None or bitis <= an:
            return "suresi_doldu"
    return satir.durum


def uye_sozlugu(satir: HesapUyeleri) -> Dict[str, Any]:
    """API yanıtı — jeton özeti asla dönmüyor."""
    return {
        "id": satir.id,
        "hesap_email": satir.hesap_email,
        "uye_email": satir.uye_email,
        "rol": satir.rol,
        "izinler": list(izinleri_coz(satir.izinler, satir.rol)),
        "durum": gecerli_durum(satir),
        "davet_bitis": _utc(satir.davet_bitis).isoformat() if satir.davet_bitis else None,
        "ekleyen": satir.ekleyen,
        "olusturma": _utc(satir.olusturma).isoformat() if satir.olusturma else None,
        "son_kullanim": _utc(satir.son_kullanim).isoformat() if satir.son_kullanim else None,
    }


# ---------------------------------------------------------------------------
# Önbellek ve istek başı karar
# ---------------------------------------------------------------------------
#: (kişi, hesap) → (bitiş_monotonic, {"id","rol","izinler","son_kullanim"} | None)
_onbellek: Dict[Tuple[str, str], Tuple[float, Optional[Dict[str, Any]]]] = {}


def onbellegi_temizle() -> None:
    """Üyelik değişince: bu süreçte bir sonraki istek veritabanına baksın."""
    _onbellek.clear()


def _oturum_yapici():
    from core.database import db_manager

    return db_manager.async_session_maker


async def uyelik_karari(kisi: str, hesap: str) -> Optional[Dict[str, Any]]:
    """Kişi bu hesapta AKTİF üye mi? Önbellekli; veritabanı hatasında None (kapalı).

    Oturum kararının tersine burada hata "kapalı" sonuçlanıyor: üyelik
    doğrulanamazsa kişi başkasının hesabına giremesin (kendi hesabı etkilenmez).
    """
    anahtar = (kisi, hesap)
    kayit = _onbellek.get(anahtar)
    if kayit is not None and kayit[0] >= time.monotonic():
        return kayit[1]

    yapici = _oturum_yapici()
    if yapici is None:
        return None
    bilgi: Optional[Dict[str, Any]] = None
    try:
        async with yapici() as db:
            satir = (
                await db.execute(
                    select(HesapUyeleri).where(
                        HesapUyeleri.hesap_email == hesap,
                        HesapUyeleri.uye_email == kisi,
                        HesapUyeleri.durum == "aktif",
                    )
                )
            ).scalar_one_or_none()
            if satir is not None:
                bilgi = {
                    "id": satir.id,
                    "rol": satir.rol,
                    "izinler": izinleri_coz(satir.izinler, satir.rol),
                }
                son = _utc(satir.son_kullanim)
                if son is None or simdi() - son >= SON_KULLANIM_ARALIGI:
                    await db.execute(
                        update(HesapUyeleri)
                        .where(HesapUyeleri.id == satir.id)
                        .values(son_kullanim=simdi())
                        .execution_options(synchronize_session=False)
                    )
                    await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Hesap üyeliği denetlenemedi (erişim verilmedi)")
        return None

    if len(_onbellek) > 10000:
        _onbellek.clear()
    _onbellek[anahtar] = (time.monotonic() + ONBELLEK_SN, bilgi)
    return bilgi


# ---------------------------------------------------------------------------
# Sorgular
# ---------------------------------------------------------------------------


async def uyeler(db: AsyncSession, hesap: str) -> List[HesapUyeleri]:
    return list(
        (
            await db.execute(
                select(HesapUyeleri)
                .where(HesapUyeleri.hesap_email == hesap)
                .order_by(HesapUyeleri.olusturma.asc(), HesapUyeleri.id.asc())
            )
        )
        .scalars()
        .all()
    )


async def uye_bul(db: AsyncSession, hesap: str, uye_id: int) -> HesapUyeleri:
    satir = (
        await db.execute(select(HesapUyeleri).where(HesapUyeleri.id == uye_id, HesapUyeleri.hesap_email == hesap))
    ).scalar_one_or_none()
    if satir is None:
        # Başka hesabın üyeliği de "yok": varlığı sızmasın.
        raise HesapHatasi(404, "uye_yok")
    return satir


async def hesap_adlari(db: AsyncSession, epostalar: Iterable[str]) -> Dict[str, str]:
    """Hesabın görünen adı: müşteri kayıtlarındaki şirket/müşteri adı, yoksa kullanıcı adı."""
    from models.auth import User
    from models.invoices import Invoices
    from models.projects import Projects
    from sqlalchemy import func

    liste = sorted({eposta_duzelt(e) for e in epostalar if e})
    if not liste:
        return {}
    adlar: Dict[str, str] = {}
    try:
        for model in (Projects, Invoices):
            satirlar = (
                await db.execute(
                    select(func.lower(model.client_email), model.client_name)
                    .where(func.lower(model.client_email).in_(liste), model.client_name.isnot(None))
                    .order_by(model.id.desc())
                )
            ).all()
            for eposta, ad in satirlar:
                if eposta and (ad or "").strip() and eposta not in adlar:
                    adlar[eposta] = ad.strip()[:120]
        eksik = [e for e in liste if e not in adlar]
        if eksik:
            for eposta, ad in (
                await db.execute(select(func.lower(User.email), User.name).where(func.lower(User.email).in_(eksik)))
            ).all():
                if eposta and (ad or "").strip() and eposta not in adlar:
                    adlar[eposta] = ad.strip()[:120]
    except Exception:  # noqa: BLE001 - görünen ad süs, işi bozmasın
        logger.debug("Hesap adları okunamadı", exc_info=True)
    return adlar


async def hesapta_izinli_mi(db: AsyncSession, kisi: str, hesap: str, izin: str) -> bool:
    """Kişi bu hesapta `izin` sahibi AKTİF üye mi? (oturumsuz akışlar için: e-posta yanıtı)."""
    kisi, hesap = eposta_duzelt(kisi), eposta_duzelt(hesap)
    if not kisi or not hesap or kisi == hesap:
        return kisi == hesap and bool(kisi)
    satir = (
        await db.execute(
            select(HesapUyeleri.rol, HesapUyeleri.izinler).where(
                HesapUyeleri.hesap_email == hesap, HesapUyeleri.uye_email == kisi, HesapUyeleri.durum == "aktif"
            )
        )
    ).first()
    return bool(satir) and izin in izinleri_coz(satir[1], satir[0])


async def hesaplarim(db: AsyncSession, kisi: str) -> List[Dict[str, Any]]:
    """Kişinin erişebildiği hesaplar: kendi hesabı + aktif üyelikleri."""
    satirlar = list(
        (
            await db.execute(
                select(HesapUyeleri)
                .where(HesapUyeleri.uye_email == kisi, HesapUyeleri.durum == "aktif")
                .order_by(HesapUyeleri.hesap_email.asc())
            )
        )
        .scalars()
        .all()
    )
    adlar = await hesap_adlari(db, [kisi, *(s.hesap_email for s in satirlar)])
    liste = [
        {
            "hesap_email": kisi,
            "ad": adlar.get(kisi),
            "rol": SAHIP,
            "izinler": list(IZINLER),
            "kendi": True,
        }
    ]
    for s in satirlar:
        if s.hesap_email == kisi:
            continue
        liste.append(
            {
                "hesap_email": s.hesap_email,
                "ad": adlar.get(s.hesap_email),
                "rol": s.rol,
                "izinler": list(izinleri_coz(s.izinler, s.rol)),
                "kendi": False,
            }
        )
    return liste


# ---------------------------------------------------------------------------
# Yetki kuralları (ekip yönetimi)
# ---------------------------------------------------------------------------


def yonetim_yetkisi_iste(aktor: HesapBaglami) -> None:
    if not aktor.ekibi_yonetebilir:
        raise HesapHatasi(403, "ekip_yetkisi_yok")


def _alt_kume_mi(izinler: Iterable[str], ust: Iterable[str]) -> bool:
    return set(izinler) <= set(ust)


def degisiklik_yetkisi(
    aktor: HesapBaglami,
    *,
    hedef: Optional[HesapUyeleri],
    yeni_rol: Optional[str],
    yeni_izinler: Optional[Tuple[str, ...]],
) -> None:
    """Sahip ve ajans yöneticisi her şeyi yapabilir; hesap yöneticisi:

    * kendi üyeliğini değiştiremez/silemez (kendi yetkisini yükseltemez),
    * kendinden geniş izni olan bir üyeye dokunamaz,
    * kendinde olmayan bir izni kimseye veremez.
    """
    yonetim_yetkisi_iste(aktor)
    if aktor.yonetici or aktor.rol == SAHIP:
        return
    if hedef is not None:
        if hedef.uye_email == aktor.kisi_email:
            raise HesapHatasi(403, "kendini_duzenleyemez")
        if not _alt_kume_mi(izinleri_coz(hedef.izinler, hedef.rol), aktor.izinler):
            raise HesapHatasi(403, "yetki_yukseltilemez")
    if yeni_izinler is not None and not _alt_kume_mi(yeni_izinler, aktor.izinler):
        raise HesapHatasi(403, "yetki_yukseltilemez")
    if yeni_rol == "yonetici" and not _alt_kume_mi(IZINLER, aktor.izinler) and yeni_izinler is None:
        # Rol varsayılanı (tüm izinler) aktörde yoksa açıkça alt küme verilmeli.
        raise HesapHatasi(403, "yetki_yukseltilemez")


# ---------------------------------------------------------------------------
# Davet
# ---------------------------------------------------------------------------


def _yeni_jeton() -> Tuple[str, str]:
    jeton = secrets.token_urlsafe(24)
    return jeton, jeton_ozeti(jeton)


async def davet_olustur(
    db: AsyncSession,
    *,
    hesap: str,
    uye: str,
    rol: str,
    izinler: Tuple[str, ...],
    ekleyen: str,
) -> Tuple[str, HesapUyeleri]:
    """Yeni üye satırı (durum=davet). Ham jetonu (bir kez) ve satırı döndürür."""
    hesap, uye = eposta_duzelt(hesap), eposta_duzelt(uye)
    if not eposta_gecerli_mi(uye):
        raise HesapHatasi(400, "eposta_gecersiz")
    if uye == hesap:
        # Sahip zaten tam yetkili; kendini üye olarak ekleyemez (sahibi değiştiremez).
        raise HesapHatasi(400, "sahip_eklenemez")
    mevcut = (
        await db.execute(
            select(HesapUyeleri.id).where(HesapUyeleri.hesap_email == hesap, HesapUyeleri.uye_email == uye)
        )
    ).first()
    if mevcut:
        raise HesapHatasi(409, "zaten_uye")
    sayi = len((await db.execute(select(HesapUyeleri.id).where(HesapUyeleri.hesap_email == hesap))).all())
    if sayi >= EN_COK_UYE:
        raise HesapHatasi(409, "uye_siniri")

    jeton, ozet = _yeni_jeton()
    satir = HesapUyeleri(
        hesap_email=hesap,
        uye_email=uye,
        rol=rol,
        izinler=json.dumps(list(izinler)),
        durum="davet",
        davet_jetonu_ozet=ozet,
        davet_bitis=simdi() + timedelta(days=DAVET_GUN),
        ekleyen=eposta_duzelt(ekleyen) or None,
        olusturma=simdi(),
    )
    db.add(satir)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HesapHatasi(409, "zaten_uye")
    await db.refresh(satir)
    onbellegi_temizle()
    return jeton, satir


async def davet_yenile(db: AsyncSession, satir: HesapUyeleri) -> str:
    """Bekleyen (ya da süresi geçmiş) davete yeni jeton + 7 gün. Eski bağlantı geçersizleşir."""
    if satir.durum != "davet":
        raise HesapHatasi(409, "davet_degil")
    jeton, ozet = _yeni_jeton()
    satir.davet_jetonu_ozet = ozet
    satir.davet_bitis = simdi() + timedelta(days=DAVET_GUN)
    await db.commit()
    await db.refresh(satir)
    return jeton


async def davet_coz(db: AsyncSession, jeton: str) -> Optional[HesapUyeleri]:
    if not jeton or len(jeton) > 200:
        return None
    return (
        await db.execute(select(HesapUyeleri).where(HesapUyeleri.davet_jetonu_ozet == jeton_ozeti(jeton)))
    ).scalar_one_or_none()


async def davet_kabul(db: AsyncSession, jeton: str, kisi: str) -> HesapUyeleri:
    """Daveti kabul eder: jeton tek kullanımlık, süreli, YALNIZ davet edilen e-postayla.

    "Kullanıldı" işaretlemesi tek koşullu UPDATE (imzalı işlemlerdeki gibi):
    aynı anda iki kabul gelirse birini veritabanı kazanıyor.
    """
    kisi = eposta_duzelt(kisi)
    satir = await davet_coz(db, jeton)
    if satir is None:
        raise HesapHatasi(404, "davet_yok")
    if satir.uye_email != kisi:
        raise HesapHatasi(403, "eposta_uyusmuyor", beklenen=eposta_maskele(satir.uye_email))
    if gecerli_durum(satir) == "suresi_doldu":
        raise HesapHatasi(410, "davet_suresi_doldu")
    if satir.durum != "davet":
        raise HesapHatasi(409, "davet_kullanildi")
    kimlik, ozet = satir.id, satir.davet_jetonu_ozet
    # Okuma işlemini kapat: UPDATE yeni işlemin ilk ifadesi olsun (SQLite kilidi).
    await db.commit()
    an = simdi()
    sonuc = await db.execute(
        update(HesapUyeleri)
        .where(
            and_(
                HesapUyeleri.id == kimlik,
                HesapUyeleri.durum == "davet",
                HesapUyeleri.davet_jetonu_ozet == ozet,
                HesapUyeleri.davet_bitis > an,
            )
        )
        .values(durum="aktif", davet_jetonu_ozet=None, davet_bitis=None, son_kullanim=an)
        .execution_options(synchronize_session=False)
    )
    if not sonuc.rowcount:
        await db.rollback()
        raise HesapHatasi(409, "davet_kullanildi")
    # Core UPDATE iş biriminden geçmiyor: denetime elle düş.
    try:
        from services.denetim import denetim_yaz

        await denetim_yaz(
            db,
            request=None,
            islem="onay",
            tablo="hesap_uyeleri",
            kayit_id=kimlik,
            ozet=f"Hesap daveti kabul edildi · {kisi} → {satir.hesap_email}",
            once={"durum": "davet"},
            sonra={"durum": "aktif"},
        )
    except Exception:  # noqa: BLE001
        logger.exception("Davet kabulü denetime yazılamadı")
    await db.commit()
    onbellegi_temizle()
    await db.refresh(satir)
    return satir


async def davet_epostasi(db: AsyncSession, satir: HesapUyeleri, jeton: str, davet_eden: str) -> Dict[str, str]:
    """Davet e-postasını gönderir; e-posta durumunu (sent/skipped/failed/off) döndürür."""
    from services.notify import dispatch, render

    baglanti = davet_baglantisi(jeton)
    adlar = await hesap_adlari(db, [satir.hesap_email])
    hesap_adi = adlar.get(satir.hesap_email) or satir.hesap_email
    varsayilan = (
        f"Merhaba,\n\n{davet_eden} sizi mehmetkuru.dev müşteri panelinde "
        f"\"{hesap_adi}\" hesabına ekip üyesi olarak davet etti.\n\n"
        f"Daveti kabul etmek için (7 gün geçerli):\n{baglanti}\n\n"
        f"Kabul ederken bu e-posta adresiyle giriş yapmalısınız: {satir.uye_email}\n\n"
        "Bu daveti beklemiyorsanız e-postayı yok sayabilirsiniz."
    )
    baslik, govde = await render(
        db,
        DAVET_OLAYI,
        f"{hesap_adi} hesabına davet edildiniz",
        varsayilan,
        {"hesap": hesap_adi, "davet_eden": davet_eden, "baglanti": baglanti, "eposta": satir.uye_email},
    )
    satirlar = await dispatch(
        db,
        event_type=DAVET_OLAYI,
        title=baslik,
        body=govde,
        recipients=[{"email": satir.uye_email, "role": "client", "phone": ""}],
        link=f"/hesap-davet/{jeton}",
        ref_type="hesap_uyeleri",
        ref_id=satir.id,
    )
    durum, ayrinti = "off", ""
    for s in satirlar:
        if s.channel == "email":
            durum, ayrinti = s.delivery_status or "unknown", s.delivery_detail or ""
            break
    return {"eposta_durumu": durum, "eposta_ayrinti": ayrinti}


# ---------------------------------------------------------------------------
# Bildirim alıcılarını genişletme (services/notify.dispatch çağırıyor)
# ---------------------------------------------------------------------------


def _hesap_baglantisi(link: Optional[str], hesap: str) -> Optional[str]:
    """Panel bağlantısına `hesap=` ekle: üye tıklayınca doğru hesap açılsın."""
    if not link or not link.startswith("/client"):
        return link
    from urllib.parse import quote

    ayrac = "&" if "?" in link else "?"
    return f"{link}{ayrac}hesap={quote(hesap)}"


async def alicilari_genislet(
    db: AsyncSession,
    event_type: str,
    alicilar: List[Dict[str, Any]],
    link: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Müşteri alıcılarına, olayın modülüne izni olan aktif üyeleri ekler.

    Her eklenen kişi `dispatch` içinde kendi bildirim tercihine tabi.
    Hata fırlatmaz: genişletme yapılamazsa liste olduğu gibi döner.
    """
    izin = OLAY_IZNI.get(event_type)
    if not izin:
        return alicilar
    try:
        hesaplar = {
            eposta_duzelt(a.get("email"))
            for a in alicilar
            if (a.get("role") or "client") == "client" and eposta_duzelt(a.get("email"))
        }
        if not hesaplar:
            return alicilar
        satirlar = (
            await db.execute(
                select(HesapUyeleri.hesap_email, HesapUyeleri.uye_email, HesapUyeleri.rol, HesapUyeleri.izinler).where(
                    HesapUyeleri.hesap_email.in_(sorted(hesaplar)), HesapUyeleri.durum == "aktif"
                )
            )
        ).all()
        if not satirlar:
            return alicilar
        mevcut = {eposta_duzelt(a.get("email")) for a in alicilar}
        sonuc = list(alicilar)
        for hesap, uye, rol, izinler in satirlar:
            uye = eposta_duzelt(uye)
            if uye in mevcut or izin not in izinleri_coz(izinler, rol):
                continue
            mevcut.add(uye)
            sonuc.append({"email": uye, "role": "client", "phone": "", "link": _hesap_baglantisi(link, hesap)})
        return sonuc
    except Exception:  # noqa: BLE001 - bildirim asıl işi bozmasın
        logger.exception("Bildirim alıcıları genişletilemedi")
        return alicilar
