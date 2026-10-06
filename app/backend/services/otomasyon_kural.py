"""Faz 4W — otomasyon kurallarının veritabanından bağımsız parçaları.

Burada: olay kataloğu ve belgelenmiş alan şeması, koşul değerlendirici,
yer tutucu çözücü, kural doğrulama ve hazır şablonlar. Veritabanı, kuyruk ve
eylemlerin kendisi `services/otomasyon.py`de.

Bağlam (koşulların ve yer tutucuların okuduğu veri)
---------------------------------------------------
Olay çalıştırılırken kayıtlar veritabanından taze okunup ad alanlı bir
sözlüğe çevriliyor: ``{"aday": {...}, "hesap": {...}, "kisi": {...}, "olay": {...}}``.
Alan yolu ``aday.ad`` biçiminde; özel alanlar ``aday.ozel.<anahtar>``. Önceki
değer bilinen alanlar (aşama) ``_onceki`` altında: "değişti" işleci bunu
karşılaştırıyor. Yalnız şemada listelenen alanlar bağlama giriyor — müşteri
kuralı ajansın aday/hesap alanlarını, görünür olmayan özel alanları görmüyor.

Koşul işleçleri
---------------
``esittir``/``esit_degil`` (büyük-küçük harf duyarsız; sayıda sayısal; listede
"listede var mı"), ``icerir``/``icermez`` (metinde alt dize, listede öğe),
``buyuktur``/``kucuktur`` (sayı ya da tarih), ``bos``/``dolu``, ``degisti``.
Eksik alan: ``bos`` doğru, diğerleri yanlış (hata değil).

Yer tutucular
-------------
``{{aday.ad}}`` ya da varsayılanlı ``{{aday.ad|Değerli müşterimiz}}``. Jinja
DEĞİL: ifade, filtre, döngü, öznitelik erişimi yok; yalnız bağlamdaki düz
değer tek geçişte yerleştiriliyor (değerin içindeki ``{{...}}`` ikinci kez
çözülmez). ``html`` kipinde hem şablon metni hem değerler kaçışlı; ``konu``
kipinde satır sonu ve denetim karakterleri temizleniyor (başlık enjeksiyonu
yok). Bilinmeyen değişken boş metne döner ve raporlanır; kural kaydedilirken
şemada olmayan değişken 400.
"""

import html
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Sınırlar
# ---------------------------------------------------------------------------
EN_COK_EYLEM = 5
EN_COK_KOSUL = 10
EN_COK_DERINLIK = 3
#: Ajansın kendi kuralları (müşteride modül ayarı).
AJANS_KURAL_SINIRI = 200
AJANS_DAKIKA_SINIRI = 120
AJANS_SAAT_SINIRI = 2000
VARSAYILAN_KURAL_SINIRI = 20
VARSAYILAN_DAKIKA_SINIRI = 20
VARSAYILAN_SAAT_SINIRI = 200
EN_COK_BEKLEME_DK = 30 * 24 * 60
DEGER_SINIRI = 2000

ISLECLER: Tuple[str, ...] = (
    "esittir", "esit_degil", "icerir", "icermez", "buyuktur", "kucuktur", "bos", "dolu", "degisti",
)
DEGERSIZ_ISLECLER = frozenset({"bos", "dolu", "degisti"})
BAGLACLAR = ("ve", "veya")
ONCELIKLER = ("dusuk", "normal", "yuksek", "acil")
AKTIVITE_TURLERI = ("not", "arama", "eposta", "toplanti")
BEKLEME_BIRIMLERI = {"dakika": 1, "saat": 60, "gun": 1440}

# ---------------------------------------------------------------------------
# Alan şeması (ad alanı → alanlar). Tür: metin | sayi | tarih | liste | evet_hayir
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Alan:
    ad: str
    tur: str = "metin"
    #: Önceki değeri bilinir ("değişti" işleci anlamlı).
    degisir: bool = False


NESNELER: Dict[str, Tuple[Alan, ...]] = {
    "aday": (
        Alan("id", "sayi"), Alan("ad"), Alan("firma"), Alan("email"), Alan("telefon"), Alan("kaynak"),
        Alan("asama", degisir=True), Alan("deger_tahmini", "sayi"), Alan("para_birimi"), Alan("etiketler", "liste"),
        Alan("sorumlu"), Alan("puan", "sayi"), Alan("butce"), Alan("pazarlama_izni", "evet_hayir"),
    ),
    "teklif": (
        Alan("id", "sayi"), Alan("no"), Alan("baslik"), Alan("genel_toplam", "sayi"), Alan("para_birimi"), Alan("durum"),
        Alan("aday_ad"), Alan("aday_eposta"),
    ),
    "sozlesme": (Alan("id", "sayi"), Alan("no"), Alan("baslik")),
    "fatura": (
        Alan("id", "sayi"), Alan("no"), Alan("tutar", "sayi"), Alan("para_birimi"), Alan("durum"),
        Alan("vade_tarihi", "tarih"), Alan("gecikme_gun", "sayi"),
    ),
    "talep": (
        Alan("id", "sayi"), Alan("konu"), Alan("durum"), Alan("oncelik"), Alan("hizmet"), Alan("kaynak"),
        Alan("etiketler", "liste"), Alan("yazan"),
    ),
    "gorev": (
        Alan("id", "sayi"), Alan("baslik"), Alan("durum"), Alan("oncelik"), Alan("atanan"), Alan("bitis_tarihi", "tarih"),
    ),
    "proje": (
        Alan("id", "sayi"), Alan("baslik"), Alan("asama", degisir=True), Alan("durum"), Alan("ilerleme", "sayi"),
        Alan("kategori"),
    ),
    "siparis": (
        Alan("id", "sayi"), Alan("no"), Alan("durum"), Alan("teslimat"), Alan("masa"), Alan("toplam", "sayi"),
        Alan("para_birimi"), Alan("kalem_sayisi", "sayi"), Alan("musteri_ad"),
    ),
    "mesaj": (Alan("id", "sayi"), Alan("ad"), Alan("eposta"), Alan("telefon")),
    "randevu": (
        Alan("id", "sayi"), Alan("ad"), Alan("eposta"), Alan("telefon"), Alan("baslangic", "tarih"), Alan("tur"),
        Alan("sure_dk", "sayi"), Alan("konum"),
    ),
    # Faz 5I — içerik stüdyosu gönderisi (metin yok; kanallar, planlanan zaman, kampanya).
    "icerik": (
        Alan("id", "sayi"), Alan("baslik"), Alan("durum", degisir=True), Alan("kanallar", "liste"),
        Alan("planlanan_at", "tarih"), Alan("kampanya"), Alan("sorumlu"), Alan("not"),
    ),
    # Faz 6S — saha servisi iş emri (servis müşterisi: olaydaki kişi).
    "is_emri": (
        Alan("id", "sayi"), Alan("no"), Alan("baslik"), Alan("tur"), Alan("oncelik"), Alan("durum"),
        Alan("musteri_ad"), Alan("musteri_eposta"), Alan("adres"), Alan("baslangic", "tarih"), Alan("teknisyen"),
        Alan("puan", "sayi"),
    ),
    "hesap": (Alan("email"), Alan("ad")),
    "kisi": (Alan("ad"), Alan("email")),
    "olay": (Alan("tur"), Alan("zaman", "tarih")),
}
#: Özel alanı olan ad alanları → `ozel_alanlar.varlik`.
OZEL_VARLIK: Dict[str, str] = {"aday": "crm_aday", "proje": "proje", "talep": "destek", "hesap": "hesap"}


@dataclass(frozen=True)
class OtoOlay:
    anahtar: str
    nesneler: Tuple[str, ...]
    #: Müşteri kuralı kullanabilir mi (CRM olayları yalnız ajans).
    musteri: bool = True
    #: Yalnız otomasyon (webhook kataloğunda yok; zamanlı uçta ya da ek kancada üretiliyor).
    yalniz_otomasyon: bool = False
    #: Görev eyleminde "olaydaki proje" seçilebilir mi.
    proje_var: bool = False


OLAYLAR: Tuple[OtoOlay, ...] = (
    OtoOlay("aday.olusturuldu", ("aday",), musteri=False),
    OtoOlay("aday.asama_degisti", ("aday",), musteri=False, yalniz_otomasyon=True),
    OtoOlay("teklif.kabul_edildi", ("teklif", "proje", "hesap"), proje_var=True),
    OtoOlay("teklif.reddedildi", ("teklif", "hesap")),
    OtoOlay("sozlesme.imzalandi", ("sozlesme", "hesap")),
    OtoOlay("fatura.olusturuldu", ("fatura", "hesap")),
    OtoOlay("fatura.odendi", ("fatura", "hesap")),
    OtoOlay("fatura.gecikti", ("fatura", "hesap"), yalniz_otomasyon=True),
    OtoOlay("destek.olusturuldu", ("talep", "proje", "hesap"), proje_var=True),
    OtoOlay("destek.yanitlandi", ("talep", "proje", "hesap"), proje_var=True),
    OtoOlay("gorev.olusturuldu", ("gorev", "proje", "hesap"), proje_var=True),
    OtoOlay("gorev.tamamlandi", ("gorev", "proje", "hesap"), proje_var=True),
    OtoOlay("proje.asama_degisti", ("proje", "hesap"), proje_var=True),
    OtoOlay("menu.siparis", ("siparis", "hesap")),
    OtoOlay("kart.mesaj", ("mesaj", "hesap")),
    # Faz 5I — içerik stüdyosu (webhook kataloğunda da var).
    OtoOlay("icerik.onaylandi", ("icerik", "hesap")),
    OtoOlay("icerik.revizyon_istendi", ("icerik", "hesap")),
    OtoOlay("icerik.yayin_zamani", ("icerik", "hesap")),
    OtoOlay("icerik.yayinlandi", ("icerik", "hesap")),
    OtoOlay("randevu.olusturuldu", ("randevu", "aday", "hesap"), yalniz_otomasyon=True),
    # Faz 6S — saha servisi.
    OtoOlay("is_emri.olusturuldu", ("is_emri", "hesap")),
    OtoOlay("is_emri.tamamlandi", ("is_emri", "hesap")),
)
OLAY_SOZLUGU: Dict[str, OtoOlay] = {o.anahtar: o for o in OLAYLAR}
#: `fatura.gecikti` hangi gecikme günlerinde üretiliyor (her biri fatura başına bir kez).
GECIKME_ESIKLERI: Tuple[int, ...] = (1, 3, 7, 14, 30)

EYLEM_TURLERI: Tuple[str, ...] = (
    "eposta", "bildirim", "gorev", "crm_asama", "crm_etiket", "crm_sahip", "crm_aktivite", "destek", "webhook", "bekle",
)
#: Müşteri kuralının kullanabildiği eylemler (CRM ve destek talebi eylemleri yok).
MUSTERI_EYLEMLERI = frozenset({"eposta", "bildirim", "gorev", "webhook", "bekle"})


class KuralHatasi(Exception):
    def __init__(self, kod: str, durum: int = 400, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.durum = durum
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


def olay_nesneleri(tur: str, ajans: bool) -> Tuple[str, ...]:
    """Olayın bağlamındaki ad alanları (müşteride aday yok); hep: kisi, olay."""
    o = OLAY_SOZLUGU.get(tur)
    if o is None:
        return ()
    nesneler = [n for n in o.nesneler if ajans or n != "aday"]
    return tuple(nesneler) + ("kisi", "olay")


def olay_katalogu(ajans: bool) -> List[Dict[str, Any]]:
    return [
        {"anahtar": o.anahtar, "nesneler": list(olay_nesneleri(o.anahtar, ajans)), "proje_var": o.proje_var}
        for o in OLAYLAR
        if ajans or o.musteri
    ]


def sema(tur: str, ajans: bool, ozel: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> List[Dict[str, Any]]:
    """Olayın belgelenmiş alanları: [{yol, tur, degisir, ozel?, ad?, secenekler?}].

    `ozel`: varlık → [{anahtar, ad, tur, secenekler}] (müşteride yalnız görünürler, hesap/aday hiç).
    """
    sonuc: List[Dict[str, Any]] = []
    for ns in olay_nesneleri(tur, ajans):
        for a in NESNELER[ns]:
            sonuc.append({"yol": f"{ns}.{a.ad}", "tur": a.tur, "degisir": a.degisir})
        varlik = OZEL_VARLIK.get(ns)
        if varlik and ozel and (ajans or varlik in ("proje", "destek")):
            for oz in ozel.get(varlik, []):
                tur_ = {"coklu_secim": "liste", "secim": "metin", "url": "metin"}.get(oz["tur"], oz["tur"])
                sonuc.append({
                    "yol": f"{ns}.ozel.{oz['anahtar']}", "tur": tur_, "degisir": False, "ozel": True, "ad": oz["ad"],
                    "secenekler": oz.get("secenekler") or [],
                })
    return sonuc


# ---------------------------------------------------------------------------
# Örnek bağlam (kuru çalıştırma)
# ---------------------------------------------------------------------------
ORNEK: Dict[str, Dict[str, Any]] = {
    "aday": {"id": 101, "ad": "Ayşe Yılmaz", "firma": "Örnek Ltd.", "email": "ayse@ornek.com", "telefon": "+905551112233",
             "kaynak": "form", "asama": "yeni", "deger_tahmini": 25000, "para_birimi": "TRY", "etiketler": ["web"],
             "sorumlu": None, "puan": 40, "butce": "20-30 bin TL", "pazarlama_izni": False},
    "teklif": {"id": 12, "no": "TKL-2026-0012", "baslik": "Kurumsal web sitesi", "genel_toplam": 48000,
               "para_birimi": "TRY", "durum": "kabul", "aday_ad": "Ayşe Yılmaz", "aday_eposta": "ayse@ornek.com"},
    "sozlesme": {"id": 7, "no": "SZL-2026-0007", "baslik": "Web sitesi sözleşmesi"},
    "fatura": {"id": 31, "no": "FTR-2026-0031", "tutar": 12000, "para_birimi": "TRY", "durum": "unpaid",
               "vade_tarihi": "2026-09-28", "gecikme_gun": 3},
    "talep": {"id": 55, "konu": "Site açılmıyor", "durum": "open", "oncelik": "acil", "hizmet": "website",
              "kaynak": "panel", "etiketler": [], "yazan": "musteri"},
    "gorev": {"id": 210, "baslik": "Ana sayfa tasarımı", "durum": "yapilacak", "oncelik": "normal", "atanan": None,
              "bitis_tarihi": "2026-10-10"},
    "proje": {"id": 9, "baslik": "Kurumsal web sitesi", "asama": "tasarim", "durum": "in_progress", "ilerleme": 40,
              "kategori": "Website"},
    "siparis": {"id": 77, "no": "A1B2C3", "durum": "yeni", "teslimat": "masa", "masa": "4", "toplam": 45000,
                "para_birimi": "TRY", "kalem_sayisi": 3, "musteri_ad": "Ali"},
    "mesaj": {"id": 15, "ad": "Mehmet Demir", "eposta": "mehmet@ornek.com", "telefon": None},
    "randevu": {"id": 40, "ad": "Zeynep Kaya", "eposta": "zeynep@ornek.com", "telefon": None,
                "baslangic": "2026-10-05T10:00:00Z", "tur": "Tanışma görüşmesi", "sure_dk": 30, "konum": "Jitsi"},
    "is_emri": {"id": 88, "no": "IE-2026-0088", "baslik": "Klima bakımı", "tur": "bakim", "oncelik": "normal",
                "durum": "tamamlandi", "musteri_ad": "Ahmet Yıldız", "musteri_eposta": "ahmet@ornek.com",
                "adres": "Atatürk Cad. 12, Kadıköy, İstanbul", "baslangic": "2026-10-05T07:00:00Z", "teknisyen": "Mert",
                "puan": None},
    "hesap": {"email": "musteri@ornek.com", "ad": "Örnek A.Ş."},
}


def ornek_baglam(tur: str, ajans: bool, ozel: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    baglam: Dict[str, Any] = {}
    for ns in olay_nesneleri(tur, ajans):
        if ns in ("kisi", "olay"):
            continue
        baglam[ns] = dict(ORNEK[ns])
        varlik = OZEL_VARLIK.get(ns)
        if varlik and ozel and (ajans or varlik in ("proje", "destek")):
            ornekler = {}
            for oz in ozel.get(varlik, []):
                ornekler[oz["anahtar"]] = {
                    "sayi": 1, "tarih": "2026-10-01", "evet_hayir": True, "url": "https://ornek.com",
                    "secim": (oz.get("secenekler") or [""])[0], "coklu_secim": (oz.get("secenekler") or [])[:1],
                }.get(oz["tur"], "örnek")
            baglam[ns]["ozel"] = ornekler
    baglam["olay"] = {"tur": tur, "zaman": "2026-10-01T09:00:00Z"}
    baglam["kisi"] = kisi_sec(tur, baglam)
    if tur in ("aday.asama_degisti",):
        baglam["_onceki"] = {"aday.asama": "yeni"}
        baglam["aday"]["asama"] = "teklif"
    if tur == "proje.asama_degisti":
        baglam["_onceki"] = {"proje.asama": "kesif"}
    return baglam


def kisi_sec(tur: str, baglam: Dict[str, Any]) -> Dict[str, Any]:
    """"Olaydaki kişi" (e-posta alıcısı `kisi`): adayda aday, randevuda ziyaretçi, kart mesajında
    yazan, teklifte teklifin kişisi (yoksa hesap), diğerlerinde müşteri hesabı."""
    on = tur.split(".", 1)[0]
    if on == "aday" and baglam.get("aday"):
        return {"ad": baglam["aday"].get("ad"), "email": baglam["aday"].get("email")}
    if on == "randevu" and baglam.get("randevu"):
        return {"ad": baglam["randevu"].get("ad"), "email": baglam["randevu"].get("eposta")}
    if on == "is_emri" and baglam.get("is_emri"):
        return {"ad": baglam["is_emri"].get("musteri_ad"), "email": baglam["is_emri"].get("musteri_eposta")}
    if on == "kart" and baglam.get("mesaj"):
        return {"ad": baglam["mesaj"].get("ad"), "email": baglam["mesaj"].get("eposta")}
    if on == "menu" and baglam.get("siparis"):
        return {"ad": baglam["siparis"].get("musteri_ad"), "email": None}
    if on == "teklif" and baglam.get("teklif") and baglam["teklif"].get("aday_eposta"):
        return {"ad": baglam["teklif"].get("aday_ad"), "email": baglam["teklif"].get("aday_eposta")}
    h = baglam.get("hesap") or {}
    return {"ad": h.get("ad"), "email": h.get("email")}


# ---------------------------------------------------------------------------
# Yol okuma ve değer karşılaştırma
# ---------------------------------------------------------------------------
_YOL = re.compile(r"^[a-z_][a-z0-9_]*(?:\.[a-z0-9_]+){1,3}$")
_EKSIK = object()


def yol_oku(baglam: Dict[str, Any], yol: str) -> Any:
    """Bağlamdaki değer; yoksa `_EKSIK`. Yalnız sözlük anahtarları (öznitelik erişimi yok)."""
    if not isinstance(yol, str) or not _YOL.match(yol) or yol.startswith("_"):
        return _EKSIK
    deger: Any = baglam
    for parca in yol.split("."):
        if not isinstance(deger, dict) or parca not in deger:
            return _EKSIK
        deger = deger[parca]
    return deger


def _bos(deger: Any) -> bool:
    return deger is _EKSIK or deger is None or (isinstance(deger, str) and not deger.strip()) or (
        isinstance(deger, (list, dict)) and not deger
    )


def _sayi(deger: Any) -> Optional[float]:
    if isinstance(deger, bool) or deger is None or deger is _EKSIK:
        return None
    if isinstance(deger, (int, float)):
        return float(deger) if not (isinstance(deger, float) and (math.isnan(deger) or math.isinf(deger))) else None
    if isinstance(deger, str):
        try:
            s = float(deger.strip().replace(",", "."))
        except ValueError:
            return None
        return None if math.isnan(s) or math.isinf(s) else s
    return None


def _tarih(deger: Any) -> Optional[datetime]:
    if isinstance(deger, datetime):
        from datetime import timezone

        return deger.replace(tzinfo=None) if deger.tzinfo is None else deger.astimezone(timezone.utc).replace(tzinfo=None)
    if isinstance(deger, date):
        return datetime(deger.year, deger.month, deger.day)
    if not isinstance(deger, str):
        return None
    s = deger.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return None
    try:
        an = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            an = datetime.fromisoformat(s[:10])
        except ValueError:
            return None
    if an.tzinfo is not None:
        from datetime import timezone

        an = an.astimezone(timezone.utc).replace(tzinfo=None)
    return an


_I_KATLA = str.maketrans({"I": "i", "İ": "i", "ı": "i"})


def _metin(deger: Any) -> str:
    """Karşılaştırma biçimi: boşluk sadeleşir, büyük-küçük harf duyarsız (Türkçe ı/i/I/İ aynı)."""
    if isinstance(deger, bool):
        return "true" if deger else "false"
    if isinstance(deger, float) and deger.is_integer():
        return str(int(deger))
    return " ".join(str(deger).split()).translate(_I_KATLA).casefold().replace("i̇", "i")


def _esit(gercek: Any, beklenen: Any) -> bool:
    if gercek is _EKSIK or gercek is None:
        return False
    if isinstance(gercek, list):
        return any(_esit(g, beklenen) for g in gercek)
    if isinstance(gercek, bool):
        b = _metin(beklenen)
        return gercek == (b in ("true", "1", "evet", "yes"))
    gs, bs = _sayi(gercek), _sayi(beklenen)
    if gs is not None and bs is not None and not isinstance(gercek, str):
        return gs == bs
    return _metin(gercek) == _metin(beklenen)


def _icerir(gercek: Any, beklenen: Any) -> bool:
    if gercek is _EKSIK or gercek is None:
        return False
    if isinstance(gercek, list):
        return any(_esit(g, beklenen) for g in gercek)
    b = _metin(beklenen)
    return bool(b) and b in _metin(gercek)


def _karsilastir(gercek: Any, beklenen: Any) -> Optional[int]:
    """-1/0/1; karşılaştırılamazsa None. Önce sayı, sonra tarih."""
    gs, bs = _sayi(gercek), _sayi(beklenen)
    if gs is not None and bs is not None:
        return (gs > bs) - (gs < bs)
    gt, bt = _tarih(gercek), _tarih(beklenen)
    if gt is not None and bt is not None:
        return (gt > bt) - (gt < bt)
    return None


def kosul_tek(baglam: Dict[str, Any], kosul: Dict[str, Any]) -> Tuple[bool, Any]:
    """(sonuç, okunan değer). Eksik alan hata değil: `bos` doğru, diğerleri yanlış."""
    yol = kosul.get("alan")
    islec = kosul.get("islec")
    beklenen = kosul.get("deger")
    gercek = yol_oku(baglam, yol)
    okunan = None if gercek is _EKSIK else gercek
    if islec == "bos":
        return _bos(gercek), okunan
    if islec == "dolu":
        return not _bos(gercek), okunan
    if islec == "degisti":
        onceki = (baglam.get("_onceki") or {})
        if yol not in onceki or gercek is _EKSIK:
            return False, okunan
        return _metin(onceki[yol]) != _metin(gercek) if onceki[yol] is not None else gercek is not None, okunan
    if gercek is _EKSIK:
        return False, None
    if islec == "esittir":
        return _esit(gercek, beklenen), okunan
    if islec == "esit_degil":
        return not _esit(gercek, beklenen), okunan
    if islec == "icerir":
        return _icerir(gercek, beklenen), okunan
    if islec == "icermez":
        return not _icerir(gercek, beklenen), okunan
    if islec in ("buyuktur", "kucuktur"):
        k = _karsilastir(gercek, beklenen)
        if k is None:
            return False, okunan
        return (k > 0) if islec == "buyuktur" else (k < 0), okunan
    return False, okunan


def kosullari_degerlendir(kosullar: Any, baglam: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
    """Kural koşulları (tek seviye VE/VEYA). Koşul yoksa doğru."""
    if isinstance(kosullar, str):
        try:
            kosullar = json.loads(kosullar)
        except ValueError:
            kosullar = None
    if not isinstance(kosullar, dict):
        return True, []
    liste = [k for k in (kosullar.get("kosullar") or []) if isinstance(k, dict)]
    if not liste:
        return True, []
    ayrinti = []
    sonuclar = []
    for k in liste:
        sonuc, okunan = kosul_tek(baglam, k)
        sonuclar.append(sonuc)
        ayrinti.append({
            "alan": k.get("alan"), "islec": k.get("islec"), "deger": k.get("deger"),
            "gercek": okunan if not isinstance(okunan, (dict,)) else None, "sonuc": sonuc,
        })
    genel = any(sonuclar) if kosullar.get("baglac") == "veya" else all(sonuclar)
    return genel, ayrinti


# ---------------------------------------------------------------------------
# Yer tutucu çözücü
# ---------------------------------------------------------------------------
YER_TUTUCU = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*(?:\.[a-z0-9_]+){1,3})\s*(?:\|([^{}\r\n]{0,80}))?\}\}")
_DENETIM = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f  ]")


def yer_tutuculari(sablon: Any) -> List[str]:
    return [m.group(1) for m in YER_TUTUCU.finditer(str(sablon or ""))]


def _deger_metni(deger: Any) -> str:
    if deger is None or deger is _EKSIK or isinstance(deger, dict):
        return ""
    if isinstance(deger, bool):
        return "✓" if deger else "✗"
    if isinstance(deger, float):
        if math.isnan(deger) or math.isinf(deger):
            return ""
        return str(int(deger)) if deger.is_integer() else f"{deger:.2f}"
    if isinstance(deger, list):
        return ", ".join(_deger_metni(d) for d in deger if not isinstance(d, (list, dict)))
    return str(deger)


def _temizle(metin: str, kip: str) -> str:
    if kip == "konu":
        metin = metin.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return _DENETIM.sub("", metin)


def yer_tutuculari_coz(sablon: Any, baglam: Dict[str, Any], kip: str = "metin") -> Tuple[str, List[str]]:
    """(çıktı, bilinmeyen değişkenler). kip: metin | html | konu.

    Tek geçiş: değer içindeki `{{...}}` yeniden çözülmez. html kipinde şablonun düz
    metni de kaçışlı (sahibi düz metin yazıyor; HTML yazamaz) ve satır sonu `<br>`.
    """
    s = str(sablon or "")
    bilinmeyen: List[str] = []
    parcalar: List[str] = []
    son = 0

    def kac(metin: str) -> str:
        metin = _temizle(metin, kip)
        if kip == "html":
            return html.escape(metin, quote=True).replace("\n", "<br>\n")
        return metin

    for m in YER_TUTUCU.finditer(s):
        parcalar.append(kac(s[son:m.start()]))
        yol, varsayilan = m.group(1), m.group(2)
        deger = yol_oku(baglam, yol)
        if deger is _EKSIK:
            bilinmeyen.append(yol)
        metin = _deger_metni(deger)[:DEGER_SINIRI]
        if not metin.strip() and varsayilan is not None:
            metin = varsayilan.strip()
        parcalar.append(kac(metin))
        son = m.end()
    parcalar.append(kac(s[son:]))
    sonuc = "".join(parcalar)
    if kip == "konu":
        sonuc = " ".join(sonuc.split())[:200]
    return sonuc, bilinmeyen


def html_govde(govde_html: str) -> str:
    """E-postanın HTML sürümü (sade, satır içi stil; dış kaynak yok)."""
    return (
        '<!doctype html><html><body style="margin:0;padding:24px;background:#f6f6f8">'
        '<div style="max-width:600px;margin:0 auto;padding:24px;background:#ffffff;border-radius:12px;'
        'font:15px/1.6 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2937">'
        f"{govde_html}</div></body></html>"
    )


# ---------------------------------------------------------------------------
# Kural doğrulama
# ---------------------------------------------------------------------------
_EPOSTA = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ETIKET = re.compile(r"^[a-z0-9_]{1,40}$")


def _metin_al(veri: Dict[str, Any], ad: str, sinir: int, *, zorunlu: bool = False, tek_satir: bool = True,
              hata_on: str = "") -> Optional[str]:
    ham = veri.get(ad)
    if ham is None:
        ham = ""
    if not isinstance(ham, (str, int, float)) or isinstance(ham, bool):
        raise KuralHatasi("alan_gecersiz", alan=hata_on + ad)
    s = str(ham).strip()
    if tek_satir:
        s = " ".join(s.split())
    if zorunlu and not s:
        raise KuralHatasi("alan_gerekli", alan=hata_on + ad)
    if len(s) > sinir:
        raise KuralHatasi("alan_uzun", alan=hata_on + ad, en_cok=sinir)
    return s or None


def _eposta(ham: Any, alan: str) -> str:
    e = str(ham or "").strip().lower()
    if not _EPOSTA.match(e) or len(e) > 254:
        raise KuralHatasi("eposta_gecersiz", alan=alan)
    return e


@dataclass
class DogrulamaBaglami:
    """Router'ın veritabanından topladığı izinli değerler."""

    ajans: bool
    #: Özel alan haritası (varlık → [{anahtar, ad, tur, secenekler}]); müşteride yalnız görünürler.
    ozel: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    crm_asamalari: Set[str] = field(default_factory=set)
    webhook_uclari: Set[int] = field(default_factory=set)
    projeler: Set[int] = field(default_factory=set)
    ekip: Set[str] = field(default_factory=set)


def gecerli_yollar(tur: str, ajans: bool, ozel: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> Set[str]:
    return {a["yol"] for a in sema(tur, ajans, ozel)}


def _yer_tutuculari_denetle(metin: Optional[str], yollar: Set[str], alan: str) -> None:
    for yol in yer_tutuculari(metin):
        if yol not in yollar:
            raise KuralHatasi("degisken_bilinmiyor", alan=alan, degisken=yol)


def _kosullari_dogrula(ham: Any, yollar: Set[str], semasi: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if ham in (None, "", {}):
        return {"baglac": "ve", "kosullar": []}
    if not isinstance(ham, dict):
        raise KuralHatasi("kosullar_gecersiz")
    baglac = ham.get("baglac") or "ve"
    if baglac not in BAGLACLAR:
        raise KuralHatasi("baglac_gecersiz")
    liste = ham.get("kosullar") or []
    if not isinstance(liste, list):
        raise KuralHatasi("kosullar_gecersiz")
    if len(liste) > EN_COK_KOSUL:
        raise KuralHatasi("kosul_sayisi", en_cok=EN_COK_KOSUL)
    temiz = []
    for i, k in enumerate(liste):
        if not isinstance(k, dict):
            raise KuralHatasi("kosullar_gecersiz", sira=i)
        alan = str(k.get("alan") or "")
        if alan not in yollar:
            raise KuralHatasi("kosul_alani_bilinmiyor", sira=i, alan=alan[:80])
        islec = k.get("islec")
        if islec not in ISLECLER:
            raise KuralHatasi("islec_gecersiz", sira=i)
        if islec == "degisti" and not semasi.get(alan, {}).get("degisir"):
            raise KuralHatasi("degisti_desteklenmiyor", sira=i, alan=alan)
        deger = k.get("deger")
        if islec in DEGERSIZ_ISLECLER:
            deger = None
        else:
            if isinstance(deger, bool):
                deger = "true" if deger else "false"
            if not isinstance(deger, (str, int, float)):
                raise KuralHatasi("kosul_degeri_gerekli", sira=i)
            deger = str(deger).strip()
            if not deger:
                raise KuralHatasi("kosul_degeri_gerekli", sira=i)
            if len(deger) > 200:
                raise KuralHatasi("kosul_degeri_uzun", sira=i, en_cok=200)
            if islec in ("buyuktur", "kucuktur") and _sayi(deger) is None and _tarih(deger) is None:
                raise KuralHatasi("kosul_degeri_sayi_tarih", sira=i)
        temiz.append({"alan": alan, "islec": islec, "deger": deger})
    return {"baglac": baglac, "kosullar": temiz}


def _eylem_dogrula(i: int, e: Any, tetik: str, b: DogrulamaBaglami, yollar: Set[str]) -> Dict[str, Any]:
    if not isinstance(e, dict):
        raise KuralHatasi("eylem_gecersiz", sira=i)
    tur = e.get("tur")
    if tur not in EYLEM_TURLERI:
        raise KuralHatasi("eylem_turu_gecersiz", sira=i)
    if not b.ajans and tur not in MUSTERI_EYLEMLERI:
        raise KuralHatasi("eylem_yalniz_ajans", sira=i, tur=tur)
    on = f"eylemler.{i}."
    olay = OLAY_SOZLUGU[tetik]

    def metin(ad: str, sinir: int, zorunlu: bool = False, tek_satir: bool = True, yer_tutucu: bool = True) -> Optional[str]:
        s = _metin_al(e, ad, sinir, zorunlu=zorunlu, tek_satir=tek_satir, hata_on=on)
        if yer_tutucu:
            _yer_tutuculari_denetle(s, yollar, on + ad)
        return s

    if tur == "eposta":
        nitelik = e.get("nitelik")
        if nitelik not in ("bilgilendirme", "pazarlama"):
            raise KuralHatasi("nitelik_gerekli", alan=on + "nitelik")
        alici = e.get("alici") or "kisi"
        if alici not in ("kisi", "sabit", "hesap"):
            raise KuralHatasi("alici_gecersiz", alan=on + "alici")
        d = {"tur": tur, "nitelik": nitelik, "alici": alici,
             "konu": metin("konu", 200, zorunlu=True), "govde": metin("govde", 5000, zorunlu=True, tek_satir=False)}
        if alici == "sabit":
            d["adres"] = _eposta(e.get("adres"), on + "adres")
        return d
    if tur == "bildirim":
        alici = e.get("alici") or ("yoneticiler" if b.ajans else "hesap")
        izinli = ("yoneticiler", "hesap", "sorumlu", "ekip_uyesi") if b.ajans else ("hesap",)
        if alici not in izinli:
            raise KuralHatasi("alici_gecersiz", alan=on + "alici")
        d = {"tur": tur, "alici": alici, "baslik": metin("baslik", 200, zorunlu=True),
             "govde": metin("govde", 2000, tek_satir=False) or ""}
        if alici == "ekip_uyesi":
            adres = _eposta(e.get("adres"), on + "adres")
            if b.ekip and adres not in b.ekip:
                raise KuralHatasi("ekip_uyesi_degil", alan=on + "adres")
            d["adres"] = adres
        return d
    if tur == "gorev":
        proje = e.get("proje")
        if proje == "olay":
            if not olay.proje_var:
                raise KuralHatasi("olayda_proje_yok", alan=on + "proje")
        else:
            if isinstance(proje, bool) or not isinstance(proje, (int, float, str)) or not str(proje).strip().isdigit():
                raise KuralHatasi("proje_gerekli", alan=on + "proje")
            proje = int(str(proje).strip())
            if proje not in b.projeler:
                raise KuralHatasi("proje_yok", alan=on + "proje")
        gun = e.get("son_tarih_gun")
        if gun in (None, ""):
            gun = None
        elif isinstance(gun, bool) or not isinstance(gun, (int, float)) or int(gun) != gun or not 0 <= int(gun) <= 365:
            raise KuralHatasi("son_tarih_gecersiz", alan=on + "son_tarih_gun")
        oncelik = e.get("oncelik") or "normal"
        if oncelik not in ONCELIKLER:
            raise KuralHatasi("oncelik_gecersiz", alan=on + "oncelik")
        d = {"tur": tur, "proje": proje, "baslik": metin("baslik", 200, zorunlu=True),
             "aciklama": metin("aciklama", 2000, tek_satir=False), "son_tarih_gun": None if gun is None else int(gun),
             "oncelik": oncelik}
        if b.ajans:
            atanan = str(e.get("atanan") or "").strip().lower() or None
            if atanan:
                atanan = _eposta(atanan, on + "atanan")
                if b.ekip and atanan not in b.ekip:
                    raise KuralHatasi("ekip_uyesi_degil", alan=on + "atanan")
            d["atanan"] = atanan
            d["musteriye_gorunur"] = e.get("musteriye_gorunur") is True
        else:
            d["atanan"] = None
            d["musteriye_gorunur"] = True
        return d
    if tur == "crm_asama":
        asama = str(e.get("asama") or "").strip()
        if not asama or (b.crm_asamalari and asama not in b.crm_asamalari):
            raise KuralHatasi("asama_yok", alan=on + "asama")
        return {"tur": tur, "asama": asama}
    if tur == "crm_etiket":
        islem = e.get("islem") or "ekle"
        if islem not in ("ekle", "kaldir"):
            raise KuralHatasi("islem_gecersiz", alan=on + "islem")
        etiket = " ".join(str(e.get("etiket") or "").split()).lower()
        if not etiket or len(etiket) > 40:
            raise KuralHatasi("etiket_gecersiz", alan=on + "etiket")
        return {"tur": tur, "islem": islem, "etiket": etiket}
    if tur == "crm_sahip":
        sorumlu = _eposta(e.get("sorumlu"), on + "sorumlu")
        if b.ekip and sorumlu not in b.ekip:
            raise KuralHatasi("ekip_uyesi_degil", alan=on + "sorumlu")
        return {"tur": tur, "sorumlu": sorumlu}
    if tur == "crm_aktivite":
        a_tur = e.get("aktivite_tur") or "not"
        if a_tur not in AKTIVITE_TURLERI:
            raise KuralHatasi("aktivite_turu_gecersiz", alan=on + "aktivite_tur")
        return {"tur": tur, "aktivite_tur": a_tur, "metin": metin("metin", 2000, zorunlu=True, tek_satir=False)}
    if tur == "destek":
        if not tetik.startswith("destek."):
            raise KuralHatasi("olayda_talep_yok", alan=on + "tur")
        oncelik = e.get("oncelik") or None
        if oncelik is not None and oncelik not in ONCELIKLER:
            raise KuralHatasi("oncelik_gecersiz", alan=on + "oncelik")
        etiket = " ".join(str(e.get("etiket") or "").split()).lower() or None
        if etiket and (len(etiket) > 40 or "," in etiket):
            raise KuralHatasi("etiket_gecersiz", alan=on + "etiket")
        if not oncelik and not etiket:
            raise KuralHatasi("destek_degisiklik_gerekli", alan=on + "oncelik")
        return {"tur": tur, "oncelik": oncelik, "etiket": etiket}
    if tur == "webhook":
        uc = e.get("uc_id")
        if isinstance(uc, bool) or not isinstance(uc, (int, float)) or int(uc) != uc or int(uc) not in b.webhook_uclari:
            raise KuralHatasi("webhook_yok", alan=on + "uc_id")
        etiket = str(e.get("etiket") or "").strip().lower() or None
        if etiket and not _ETIKET.match(etiket):
            raise KuralHatasi("etiket_gecersiz", alan=on + "etiket")
        return {"tur": tur, "uc_id": int(uc), "etiket": etiket}
    # bekle
    miktar = e.get("miktar")
    birim = e.get("birim") or "dakika"
    if birim not in BEKLEME_BIRIMLERI:
        raise KuralHatasi("birim_gecersiz", alan=on + "birim")
    if isinstance(miktar, bool) or not isinstance(miktar, (int, float)) or int(miktar) != miktar or int(miktar) < 1:
        raise KuralHatasi("miktar_gecersiz", alan=on + "miktar")
    if int(miktar) * BEKLEME_BIRIMLERI[birim] > EN_COK_BEKLEME_DK:
        raise KuralHatasi("bekleme_uzun", alan=on + "miktar")
    return {"tur": tur, "miktar": int(miktar), "birim": birim}


def kural_dogrula(veri: Dict[str, Any], b: DogrulamaBaglami, mevcut: Optional[Any] = None) -> Dict[str, Any]:
    """Panel gövdesi → sütun değerleri (JSON metinleri dahil). Güncellemede verilmeyen alanlar
    mevcuttan alınıp birlikte doğrulanıyor (tetik değişirse koşullar/eylemler yeniden denetlenir)."""
    if not isinstance(veri, dict):
        raise KuralHatasi("govde_gecersiz")
    yeni = mevcut is None
    sonuc: Dict[str, Any] = {}
    if "ad" in veri or yeni:
        sonuc["ad"] = _metin_al(veri, "ad", 120, zorunlu=True)
    if "aciklama" in veri:
        sonuc["aciklama"] = _metin_al(veri, "aciklama", 1000, tek_satir=False)
    if "aktif" in veri:
        sonuc["aktif"] = veri.get("aktif") is not False
    elif yeni:
        sonuc["aktif"] = True
    tetik = veri.get("tetik") if ("tetik" in veri or yeni) else mevcut.tetik
    olay = OLAY_SOZLUGU.get(str(tetik or ""))
    if olay is None:
        raise KuralHatasi("tetik_gecersiz")
    if not b.ajans and not olay.musteri:
        raise KuralHatasi("tetik_yalniz_ajans")
    sonuc["tetik"] = olay.anahtar
    semasi = {a["yol"]: a for a in sema(olay.anahtar, b.ajans, b.ozel)}
    yollar = set(semasi)
    tetik_degisti = yeni or olay.anahtar != mevcut.tetik
    # Kısmi güncellemede (ör. yalnız aç/kapa) saklı koşul/eylemler yeniden denetlenmez: sonradan silinen
    # webhook ucu ya da proje yüzünden kural kapatılamaz hâle gelmesin (çalışırken zaten "atlandı" olur).
    if "kosullar" in veri or tetik_degisti:
        kosul_ham = veri.get("kosullar") if "kosullar" in veri else (json.loads(mevcut.kosullar) if mevcut is not None and mevcut.kosullar else None)
        sonuc["kosullar"] = json.dumps(_kosullari_dogrula(kosul_ham, yollar, semasi), ensure_ascii=False)
    if "eylemler" not in veri and not tetik_degisti:
        if "sablon" in veri:
            s = str(veri.get("sablon") or "").strip()
            sonuc["sablon"] = s[:60] if s in SABLON_SOZLUGU else None
        return sonuc
    eylem_ham = veri.get("eylemler") if "eylemler" in veri else (json.loads(mevcut.eylemler) if mevcut is not None else None)
    if not isinstance(eylem_ham, list) or not eylem_ham:
        raise KuralHatasi("eylem_gerekli")
    if len(eylem_ham) > EN_COK_EYLEM:
        raise KuralHatasi("eylem_sayisi", en_cok=EN_COK_EYLEM)
    eylemler = [_eylem_dogrula(i, e, olay.anahtar, b, yollar) for i, e in enumerate(eylem_ham)]
    if eylemler[-1]["tur"] == "bekle":
        raise KuralHatasi("bekle_son_eylem_olamaz")
    if all(e["tur"] == "bekle" for e in eylemler):
        raise KuralHatasi("eylem_gerekli")
    sonuc["eylemler"] = json.dumps(eylemler, ensure_ascii=False)
    if "sablon" in veri:
        s = str(veri.get("sablon") or "").strip()
        sonuc["sablon"] = s[:60] if s in SABLON_SOZLUGU else None
    return sonuc


def kural_sozlugu(k: Any) -> Dict[str, Any]:
    def _j(m: Any, v: Any) -> Any:
        try:
            return json.loads(m) if m else v
        except ValueError:
            return v

    def iso(an: Any) -> Optional[str]:
        if an is None:
            return None
        from datetime import timezone

        if an.tzinfo is None:
            an = an.replace(tzinfo=timezone.utc)
        return an.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "id": k.id, "sahip_tur": k.sahip_tur, "hesap_email": k.hesap_email, "ad": k.ad, "aciklama": k.aciklama,
        "aktif": bool(k.aktif), "tetik": k.tetik, "kosullar": _j(k.kosullar, {"baglac": "ve", "kosullar": []}),
        "eylemler": _j(k.eylemler, []), "sablon": k.sablon, "olusturan": k.olusturan,
        "calisma_sayisi": int(k.calisma_sayisi or 0), "son_calisma_at": iso(k.son_calisma_at),
        "olusturma": iso(k.created_at), "guncelleme": iso(k.updated_at),
    }


# ---------------------------------------------------------------------------
# Hazır şablonlar (tek tıkla kural). Metinler ön yüzden (kullanıcının dili)
# gelebilir; gelmezse Türkçe varsayılan.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Sablon:
    anahtar: str
    tetik: str
    kosullar: Dict[str, Any]
    #: Eylemler; metin alanları `$<anahtar>` → metinler sözlüğünden.
    eylemler: Tuple[Dict[str, Any], ...]
    metinler: Dict[str, str]
    yalniz_ajans: bool = False


SABLONLAR: Tuple[Sablon, ...] = (
    Sablon(
        "yeni_aday_hosgeldin", "aday.olusturuldu", {"baglac": "ve", "kosullar": [{"alan": "aday.email", "islec": "dolu"}]},
        ({"tur": "eposta", "nitelik": "bilgilendirme", "alici": "kisi", "konu": "$konu", "govde": "$govde"},),
        {"ad": "Yeni aday → hoş geldin e-postası",
         "konu": "Hoş geldiniz, {{aday.ad}}",
         "govde": "Merhaba {{aday.ad|}},\n\nBize ulaştığınız için teşekkür ederiz. Talebinizi aldık; en kısa sürede "
                  "sizinle iletişime geçeceğiz.\n\nSevgiler"},
        yalniz_ajans=True,
    ),
    Sablon(
        "teklif_kabul_gorev", "teklif.kabul_edildi", {"baglac": "ve", "kosullar": []},
        ({"tur": "gorev", "proje": "olay", "baslik": "$gorev", "son_tarih_gun": 3, "oncelik": "yuksek"},
         {"tur": "bildirim", "alici": "$bildirim_alici", "baslik": "$bildirim", "govde": "$bildirim_govde"}),
        {"ad": "Teklif kabul → proje görevi + ekibe bildirim",
         "gorev": "Başlangıç toplantısı: {{teklif.baslik}}",
         "bildirim": "Teklif kabul edildi: {{teklif.no}}",
         "bildirim_govde": "{{teklif.baslik}} ({{teklif.genel_toplam}} {{teklif.para_birimi}}) kabul edildi. "
                           "Başlangıç görevi açıldı."},
    ),
    Sablon(
        "fatura_gecikti_hatirlatma", "fatura.gecikti",
        {"baglac": "ve", "kosullar": [{"alan": "fatura.gecikme_gun", "islec": "esittir", "deger": "3"}]},
        ({"tur": "eposta", "nitelik": "bilgilendirme", "alici": "kisi", "konu": "$konu", "govde": "$govde"},),
        {"ad": "Fatura 3 gün gecikti → hatırlatma e-postası",
         "konu": "Ödeme hatırlatması: {{fatura.no}}",
         "govde": "Merhaba {{kisi.ad|}},\n\n{{fatura.no}} numaralı {{fatura.tutar}} {{fatura.para_birimi}} tutarındaki "
                  "faturanızın vadesi {{fatura.gecikme_gun}} gün önce doldu. Ödemeyi panelinizden yapabilirsiniz.\n\n"
                  "Teşekkürler"},
    ),
    Sablon(
        "destek_acil_bildirim", "destek.olusturuldu",
        {"baglac": "ve", "kosullar": [{"alan": "talep.oncelik", "islec": "esittir", "deger": "acil"}]},
        ({"tur": "bildirim", "alici": "$bildirim_alici", "baslik": "$baslik", "govde": "$govde"},),
        {"ad": "Destek talebi 'acil' → yöneticilere bildirim",
         "baslik": "Acil destek talebi: {{talep.konu}}",
         "govde": "{{hesap.email}} hesabından acil öncelikli talep açıldı (#{{talep.id}})."},
    ),
    Sablon(
        "randevu_crm_etkinligi", "randevu.olusturuldu", {"baglac": "ve", "kosullar": []},
        ({"tur": "crm_aktivite", "aktivite_tur": "toplanti", "metin": "$metin"},),
        {"ad": "Randevu oluştu → CRM etkinliği",
         "metin": "Randevu alındı: {{randevu.tur}} — {{randevu.baslangic}} ({{randevu.ad}})"},
        yalniz_ajans=True,
    ),
)
SABLON_SOZLUGU: Dict[str, Sablon] = {s.anahtar: s for s in SABLONLAR}


def sablon_katalogu(ajans: bool) -> List[Dict[str, Any]]:
    return [
        {"anahtar": s.anahtar, "tetik": s.tetik, "kosullar": s.kosullar, "eylemler": [dict(e) for e in s.eylemler],
         "metinler": dict(s.metinler)}
        for s in SABLONLAR
        if ajans or not s.yalniz_ajans
    ]


def sablondan_kural(anahtar: str, ajans: bool, metinler: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    s = SABLON_SOZLUGU.get(anahtar)
    if s is None or (s.yalniz_ajans and not ajans):
        raise KuralHatasi("sablon_yok", 404)
    m = dict(s.metinler)
    for k, v in (metinler or {}).items():
        if k in m and isinstance(v, str) and v.strip():
            m[k] = v[:5000]
    m["bildirim_alici"] = "yoneticiler" if ajans else "hesap"

    def doldur(d: Dict[str, Any]) -> Dict[str, Any]:
        return {k: (m.get(v[1:], v) if isinstance(v, str) and v.startswith("$") else v) for k, v in d.items()}

    return {
        "ad": m["ad"][:120], "tetik": s.tetik, "kosullar": json.loads(json.dumps(s.kosullar)),
        "eylemler": [doldur(e) for e in s.eylemler], "aktif": True, "sablon": s.anahtar,
    }


__all__ = [
    "OLAYLAR", "OLAY_SOZLUGU", "ISLECLER", "EYLEM_TURLERI", "KuralHatasi", "DogrulamaBaglami", "sema", "olay_katalogu",
    "ornek_baglam", "kisi_sec", "kosullari_degerlendir", "yer_tutuculari_coz", "yer_tutuculari", "kural_dogrula",
    "kural_sozlugu", "SABLONLAR", "sablondan_kural", "sablon_katalogu", "html_govde",
]
