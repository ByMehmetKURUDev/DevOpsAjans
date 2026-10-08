"""Faz 6E — Etkinlik ve bilet: kurallar ve yardımcılar (veritabanına dokunmayan her şey).

Router `routers/etkinlik.py`, veritabanı işleri `services/etkinlik_kayit.py`. Burada:

* Doğrulayıcılar (randevu modülünün metin/slug/e-posta/telefon/soru yardımcıları
  yeniden kullanılıyor; hata sınıfı onların alt sınıfı — router tek yerde yakalar).
* Fiyat ve indirim hesabı (kuruş tamsayı; yuvarlama tek yerde).
* Kodlar ve imzalı jetonlar (HMAC, `JWT_SECRET_KEY`'den türetilen ayrı anahtar):
  - bilet sayfası jetonu `<sipariş id>-<imza>` (sipariş koduna bağlı),
  - QR içeriği `MKE1.<bilet kodu>.<imza>` — KİŞİSEL VERİ YOK, yalnız kod + imza;
    büyük harf + rakam + nokta olduğu için QR "alfanümerik" kipte küçük kalıyor,
  - görevli (kapı) jetonu `<etkinlik>-<sürüm>-<bitiş unix>-<imza>` (süreli, yalnız okutma),
  - bekleme listesi davet jetonu `<bekleme id>-<imza>` (davet anına bağlı; 24 saat).
* ICS (RFC 5545, METHOD:PUBLISH, zamanlar UTC; birden çok oturum → birden çok VEVENT),
  Google/Outlook "takvime ekle" bağlantıları, schema.org `Event` JSON-LD.
* Katılımcı e-postaları 7 dilde (bilgilendirme niteliğinde — pazarlama değil) ve QR'lı
  bilet PDF'i (ReportLab; sitenin yazı tipi, vektör QR).
"""

import hashlib
import hmac
import io
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote, urlencode

from services import randevu as r

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
MODUL = "etkinlik_bilet"
IZIN = "etkinlik"
IZIN_GIRIS = "etkinlik_giris"
DILLER: Tuple[str, ...] = r.DILLER
BICIMLER: Tuple[str, ...] = ("yuz_yuze", "online", "karma")
DURUMLAR: Tuple[str, ...] = ("taslak", "yayinda", "iptal", "tamamlandi")
TELEFON_SECENEKLERI: Tuple[str, ...] = r.TELEFON_SECENEKLERI
PARA_BIRIMLERI: Tuple[str, ...] = ("TRY", "USD", "EUR", "GBP")
INDIRIM_TURLERI: Tuple[str, ...] = ("yuzde", "tutar")
OKUTMA_SONUCLARI: Tuple[str, ...] = (
    "gecerli", "zaten_girdi", "gecersiz", "iptal", "farkli_etkinlik", "odeme_bekliyor", "etkinlik_iptal",
)
VARSAYILAN_SAAT_DILIMI = r.VARSAYILAN_SAAT_DILIMI
EN_COK_SORU = r.EN_COK_SORU
EN_COK_OTURUM = 20
EN_COK_TUR = 20
EN_COK_INDIRIM = 100
#: Bir kayıtta en çok bilet (bütün türler toplamı).
EN_COK_ADET = 20
KAPASITE_EN_COK = 100_000
FIYAT_EN_COK = 100_000_000  # 1.000.000,00
VARSAYILAN_SAKLAMA_GUN = 365
SAKLAMA_EN_AZ, SAKLAMA_EN_COK = 30, 1095
IPTAL_SINIR_EN_COK = 24 * 60
#: Ücretli kayıtta yerlerin tutulduğu süre (dakika).
ODEME_SURESI_DK = 60
#: Bekleme listesi davetinin geçerlilik süresi.
DAVET_SURESI = timedelta(hours=24)
#: Bilet sayfası etkinlik bitişinden bu kadar gün sonra da açılır (yalnız görüntüleme).
JETON_OMRU_GUN = 60
#: Görevli bağlantısı varsayılan olarak etkinlik bitişinden bu kadar saat sonra kapanır.
GOREVLI_EK_SAAT = 12
GOREVLI_EN_COK_SAAT = 24 * 30
#: Teşekkür e-postası bitişten bu kadar sonra, en geç şu kadar gün içinde.
TESEKKUR_GECIKME = timedelta(hours=2)
TESEKKUR_PENCERE = timedelta(days=7)

SLUG_DESENI = r.SLUG_DESENI
AYRILMIS_SLUGLAR = frozenset({
    *r.AYRILMIS_SLUGLAR, "etkinlik", "etkinlikler", "giris", "okut", "bilet", "biletler", "kayit", "bekleme",
    "davet", "gorsel", "ozet", "fiyat", "liste", "widget",
})
_KOD_ALFABESI = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
BILET_KODU_UZUNLUGU = 10
SIPARIS_KODU_UZUNLUGU = 8
BILET_KODU_DESENI = re.compile(r"^[A-HJ-NP-Z2-9]{10}$")
QR_ONEKI = "MKE1"
UTC = timezone.utc


class EtkinlikHatasi(r.RandevuHatasi):
    """Doğrulama/iş kuralı hatası: `{"kod", "alan"?, ...}` gövdesiyle döner."""


#: Router bu ikisini birlikte yakalar (randevu yardımcıları RandevuHatasi fırlatır).
TemelHata = r.RandevuHatasi


def simdi() -> datetime:
    """Testler bu fonksiyonu sabit bir ana çeviriyor (bütün zaman hesapları buradan)."""
    return datetime.now(UTC)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    return r.utc(an)


def iso(an: Optional[datetime]) -> Optional[str]:
    return r.iso(an)


def json_yukle(ham: Any, varsayilan: Any = None) -> Any:
    return r.json_yukle(ham, varsayilan)


def json_yaz(deger: Any) -> str:
    return r.json_yaz(deger)


def site_adresi() -> str:
    return r.site_adresi()


def odeme_hazir_mi() -> bool:
    """Kartla tahsilat için sağlayıcı anahtarları (Lemon Squeezy / Shopier …) tanımlı mı?
    Tek kaynak: ödeme sayfasının kullandığı denetim. Yoksa ücretli bilet türü açılamaz
    (ziyaretçi boş bir ödeme sayfasına düşmesin); panelde fiyat alanı açıklamayla kapalı."""
    from routers.odemeler import _saglayici_hazir_mi

    return bool(_saglayici_hazir_mi())


def sayfa_adresi(slug: str) -> str:
    return f"{site_adresi()}/etkinlik/{slug}"


def bilet_adresi(slug: str, jeton: str) -> str:
    return f"{site_adresi()}/etkinlik/{slug}/bilet/{jeton}"


def gorevli_adresi(jeton: str) -> str:
    return f"{site_adresi()}/etkinlik/giris/{jeton}"


def davet_adresi(slug: str, jeton: str) -> str:
    return f"{site_adresi()}/etkinlik/{slug}?davet={jeton}"


def liste_adresi(slug: str) -> str:
    return f"{site_adresi()}/etkinlikler/{slug}"


def kapak_adresi(anahtar: Optional[str], mutlak: bool = False) -> Optional[str]:
    if not anahtar:
        return None
    yol = f"/api/v1/etkinlik/gorsel/{anahtar}"
    return f"{site_adresi()}{yol}" if mutlak else yol


# ---------------------------------------------------------------------------
# Doğrulayıcılar (randevu yardımcılarının ince sarmalayıcıları)
# ---------------------------------------------------------------------------
metin = r.metin
eposta_duzelt = r.eposta_duzelt
telefon_duzelt = r.telefon_duzelt
tam_sayi = r.tam_sayi
bool_duzelt = r.bool_duzelt
renk_duzelt = r.renk_duzelt
dil_duzelt = r.dil_duzelt
saat_dilimi = r.saat_dilimi
saat_dilimi_duzelt = r.saat_dilimi_duzelt
sorular_duzelt = r.sorular_duzelt
yanitlari_dogrula = r.yanitlari_dogrula


def slug_oner(ad: str, yedek: str = "etkinlik") -> str:
    aday = r.slug_oner(ad, yedek)
    return aday if aday not in AYRILMIS_SLUGLAR else f"{aday}-{secrets.token_hex(2)}"


def slug_duzelt(ham: Any, alan: str = "slug") -> str:
    deger = r.slug_duzelt(ham, alan)
    if deger in AYRILMIS_SLUGLAR:
        raise EtkinlikHatasi("slug_ayrilmis", alan)
    return deger


def zaman_coz(ham: Any, alan: str, bos_olabilir: bool = False) -> Optional[datetime]:
    """ISO 8601, saat dilimi ŞART (`2026-11-05T10:00:00+03:00` ya da `…Z`) → UTC."""
    if ham in (None, ""):
        if bos_olabilir:
            return None
        raise EtkinlikHatasi("zorunlu", alan)
    try:
        an = datetime.fromisoformat(str(ham).strip().replace("Z", "+00:00"))
    except ValueError:
        raise EtkinlikHatasi("zaman_gecersiz", alan)
    if an.tzinfo is None:
        raise EtkinlikHatasi("zaman_gecersiz", alan)
    return an.astimezone(UTC).replace(microsecond=0)


def https_duzelt(ham: Any, alan: str, zorunlu: bool = False) -> Optional[str]:
    from services import dinamik_qr as qr

    deger = str(ham or "").strip()
    if not deger:
        if zorunlu:
            raise EtkinlikHatasi("zorunlu", alan)
        return None
    try:
        adres = qr.web_adresi_duzelt(deger, alan, True)
    except qr.QrHatasi:
        raise EtkinlikHatasi("baglanti_gecersiz", alan)
    if not adres.startswith("https://"):
        raise EtkinlikHatasi("baglanti_gecersiz", alan)
    return adres[:500]


def oturumlar_duzelt(ham: Any, bas: datetime, bit: datetime) -> List[Dict[str, Any]]:
    """[{"ad", "baslangic", "bitis"}] — etkinlik aralığı içinde, sıralı, en çok 20."""
    if ham in (None, ""):
        return []
    if not isinstance(ham, list) or len(ham) > EN_COK_OTURUM:
        raise EtkinlikHatasi("oturum_gecersiz", "oturumlar", en_cok=EN_COK_OTURUM)
    sonuc = []
    for i, o in enumerate(ham):
        if not isinstance(o, dict):
            raise EtkinlikHatasi("oturum_gecersiz", f"oturumlar.{i}")
        ad = metin(o.get("ad"), f"oturumlar.{i}.ad", 120)
        ob = zaman_coz(o.get("baslangic"), f"oturumlar.{i}.baslangic")
        oe = zaman_coz(o.get("bitis"), f"oturumlar.{i}.bitis")
        if oe <= ob or ob < bas or oe > bit:
            raise EtkinlikHatasi("oturum_araligi", f"oturumlar.{i}")
        sonuc.append({"ad": ad, "baslangic": iso(ob), "bitis": iso(oe)})
    sonuc.sort(key=lambda x: x["baslangic"])
    return sonuc


def para_birimi_duzelt(ham: Any, alan: str = "para_birimi") -> str:
    deger = str(ham or "TRY").strip().upper()
    if deger not in PARA_BIRIMLERI:
        raise EtkinlikHatasi("para_birimi_gecersiz", alan)
    return deger


def fiyat_duzelt(ham: Any, alan: str = "fiyat") -> int:
    """Kuruş tamsayı (0 = ücretsiz)."""
    return int(tam_sayi(ham if ham not in (None, "") else 0, alan, 0, FIYAT_EN_COK))


def indirim_kodu_duzelt(ham: Any, alan: str = "kod") -> str:
    deger = re.sub(r"\s+", "", str(ham or "")).upper()
    if not re.match(r"^[A-Z0-9_-]{3,40}$", deger):
        raise EtkinlikHatasi("kod_gecersiz", alan)
    return deger


# ---------------------------------------------------------------------------
# Fiyat ve indirim
# ---------------------------------------------------------------------------
@dataclass
class Kalem:
    tur_id: int
    adet: int
    birim: int  # kuruş
    para_birimi: str


@dataclass
class IndirimKurali:
    id: int
    tur: str
    deger: int
    turler: Optional[List[int]]  # None = hepsi


def kalemleri_duzelt(ham: Any) -> List[Tuple[int, int]]:
    """[{"tur_id", "adet"}] → [(tur_id, adet)] (aynı tür birleşir, adet ≥ 1, toplam ≤ 20)."""
    if not isinstance(ham, list) or not ham or len(ham) > EN_COK_TUR:
        raise EtkinlikHatasi("kalem_gecersiz", "kalemler")
    toplam: Dict[int, int] = {}
    for i, k in enumerate(ham):
        if not isinstance(k, dict):
            raise EtkinlikHatasi("kalem_gecersiz", f"kalemler.{i}")
        tid = k.get("tur_id")
        if isinstance(tid, bool) or not isinstance(tid, int):
            raise EtkinlikHatasi("kalem_gecersiz", f"kalemler.{i}.tur_id")
        adet = tam_sayi(k.get("adet", 1), f"kalemler.{i}.adet", 0, EN_COK_ADET)
        if adet:
            toplam[tid] = toplam.get(tid, 0) + adet
    if not toplam:
        raise EtkinlikHatasi("kalem_gecersiz", "kalemler")
    if sum(toplam.values()) > EN_COK_ADET:
        raise EtkinlikHatasi("adet_siniri", "kalemler", en_cok=EN_COK_ADET)
    return sorted(toplam.items())


def fiyat_hesapla(kalemler: Sequence[Kalem], indirim: Optional[IndirimKurali] = None) -> Dict[str, Any]:
    """Ara toplam, indirim, toplam (kuruş). Ücretli kalemler tek para biriminde olmalı.

    Yüzde indirim geçerli kalemlerin toplamına uygulanır (aşağı yuvarlanır); tutar indirimi
    geçerli kalemlerin toplamını aşamaz. Ücretsiz kalemde indirim anlamsız (0).
    """
    birimler = {k.para_birimi for k in kalemler if k.birim > 0}
    if len(birimler) > 1:
        raise EtkinlikHatasi("para_birimi_karisik", "kalemler")
    para = next(iter(birimler)) if birimler else (kalemler[0].para_birimi if kalemler else "TRY")
    ara = sum(k.birim * k.adet for k in kalemler)
    indirim_tutari = 0
    if indirim is not None:
        uygun = sum(k.birim * k.adet for k in kalemler if indirim.turler is None or k.tur_id in indirim.turler)
        if indirim.tur == "yuzde":
            indirim_tutari = (uygun * max(0, min(100, indirim.deger))) // 100
        else:
            indirim_tutari = min(uygun, max(0, indirim.deger))
    return {"ara_toplam": ara, "indirim": indirim_tutari, "toplam": max(0, ara - indirim_tutari), "para_birimi": para}


def para_yaz(kurus: int, para_birimi: str, dil: str = "tr") -> str:
    from services.pdf_belge import para

    return para(round(int(kurus or 0) / 100, 2), para_birimi, dil)


# ---------------------------------------------------------------------------
# Kodlar ve imzalı jetonlar
# ---------------------------------------------------------------------------
def kod_uret(uzunluk: int = BILET_KODU_UZUNLUGU) -> str:
    return "".join(secrets.choice(_KOD_ALFABESI) for _ in range(uzunluk))


_YEDEK: Optional[bytes] = None


def _anahtar() -> bytes:
    global _YEDEK
    gizli = os.environ.get("JWT_SECRET_KEY") or ""
    if not gizli:
        if _YEDEK is None:
            _YEDEK = secrets.token_bytes(32)
        return _YEDEK
    return hashlib.sha256(("etkinlik:" + gizli).encode()).digest()


def _imza(mesaj: str, uzunluk: int = 32) -> str:
    return hmac.new(_anahtar(), mesaj.encode(), hashlib.sha256).hexdigest()[:uzunluk]


def siparis_jetonu(siparis_id: int, kod: str) -> str:
    return f"{int(siparis_id)}-{_imza(f'siparis|{int(siparis_id)}|{kod}')}"


def siparis_jetonu_kimligi(jeton: Any) -> Optional[int]:
    return r.jeton_kimligi(jeton)


def siparis_jetonu_gecerli_mi(jeton: Any, siparis_id: int, kod: str) -> bool:
    return hmac.compare_digest(str(jeton or ""), siparis_jetonu(siparis_id, kod))


def qr_imzasi(kod: str) -> str:
    return _imza(f"bilet|{kod}", 16).upper()


def qr_icerigi(kod: str) -> str:
    """QR'a giden metin: önek + kod + imza. Kişisel veri YOK."""
    return f"{QR_ONEKI}.{kod}.{qr_imzasi(kod)}"


def okutma_coz(ham: Any) -> Tuple[Optional[str], bool]:
    """Okutulan/elle girilen metin → (bilet kodu, imza denetlendi mi).

    * `MKE1.<kod>.<imza>`: imza tutmazsa (sahte/değiştirilmiş) kod None.
    * Çıplak kod (elle giriş): boşluk/tire atılır, büyük harfe çevrilir; biçim tutmazsa None.
    """
    deger = str(ham or "").strip()
    if not deger or len(deger) > 120:
        return None, False
    if deger.upper().startswith(QR_ONEKI + "."):
        parca = deger.split(".")
        if len(parca) != 3:
            return None, True
        kod, imza = parca[1].upper(), parca[2].upper()
        if not BILET_KODU_DESENI.match(kod) or not hmac.compare_digest(imza, qr_imzasi(kod)):
            return None, True
        return kod, True
    kod = re.sub(r"[\s\-]", "", deger).upper()
    return (kod if BILET_KODU_DESENI.match(kod) else None), False


def gorevli_jetonu(etkinlik_id: int, surum: int, bitis: datetime) -> str:
    son = int(utc(bitis).timestamp())
    return f"{int(etkinlik_id)}-{int(surum)}-{son}-{_imza(f'gorevli|{int(etkinlik_id)}|{int(surum)}|{son}')}"


_GOREVLI = re.compile(r"^(\d{1,12})-(\d{1,6})-(\d{9,11})-([0-9a-f]{32})$")


def gorevli_jetonu_coz(jeton: Any) -> Optional[Tuple[int, int, datetime]]:
    """(etkinlik id, sürüm, bitiş) — imza ve biçim doğruysa; süre ve sürüm çağıranda."""
    m = _GOREVLI.match(str(jeton or ""))
    if not m:
        return None
    eid, surum, son = int(m.group(1)), int(m.group(2)), int(m.group(3))
    beklenen = _imza(f"gorevli|{eid}|{surum}|{son}")
    if not hmac.compare_digest(m.group(4), beklenen):
        return None
    return eid, surum, datetime.fromtimestamp(son, UTC)


def davet_jetonu(bekleme_id: int, davet_at: datetime) -> str:
    an = int(utc(davet_at).timestamp())
    return f"{int(bekleme_id)}-{_imza(f'davet|{int(bekleme_id)}|{an}')}"


def davet_jetonu_gecerli_mi(jeton: Any, bekleme_id: int, davet_at: Optional[datetime]) -> bool:
    if davet_at is None:
        return False
    return hmac.compare_digest(str(jeton or ""), davet_jetonu(bekleme_id, davet_at))


# ---------------------------------------------------------------------------
# Görünen zaman, konum
# ---------------------------------------------------------------------------
def zaman_yaz(an: datetime, tz_adi: str, dil: str = "tr") -> str:
    return r.zaman_yaz(an, tz_adi, dil)


def aralik_yaz(bas: datetime, bit: datetime, tz_adi: str, dil: str = "tr") -> str:
    try:
        tz = saat_dilimi(tz_adi)
    except TemelHata:
        tz = saat_dilimi(VARSAYILAN_SAAT_DILIMI)
    yb, ye = utc(bas).astimezone(tz), utc(bit).astimezone(tz)
    if yb.date() == ye.date():
        return f"{zaman_yaz(bas, tz_adi, dil)} – {ye.strftime('%H:%M')}"
    return f"{zaman_yaz(bas, tz_adi, dil)} – {zaman_yaz(bit, tz_adi, dil)}"


def konum_metni(e: Any, dil: str, sahibine: bool = False) -> str:
    """Bilet sahibine (`sahibine=True`) online bağlantı da yazılır; herkese yalnız yer."""
    m = metinler(dil)
    yer = ", ".join(x for x in (e.mekan_adi, (e.adres or "").replace("\n", ", ")) if x)
    if e.bicim == "online":
        return f"{m['online']}: {e.online_baglanti}" if sahibine and e.online_baglanti else m["online"]
    if e.bicim == "karma":
        parca = [yer or m["yuz_yuze"]]
        parca.append(f"{m['online']}: {e.online_baglanti}" if sahibine and e.online_baglanti else m["online"])
        return " / ".join(parca)
    return yer or m["yuz_yuze"]


def harita_adresi(e: Any) -> Optional[str]:
    if e.harita_url:
        return e.harita_url
    yer = ", ".join(x for x in (e.mekan_adi, (e.adres or "").replace("\n", ", ")) if x)
    if not yer or e.bicim == "online":
        return None
    return "https://www.google.com/maps/search/?api=1&" + urlencode({"query": yer}, quote_via=quote)


# ---------------------------------------------------------------------------
# ICS (RFC 5545) ve takvime ekle
# ---------------------------------------------------------------------------
def _ics_an(an: datetime) -> str:
    return utc(an).strftime("%Y%m%dT%H%M%SZ")


def ics_uret(e: Any, siparis_kod: str, dil: str, *, iptal: bool = False, sira_no: int = 0,
             bilet_adresi_: Optional[str] = None, an: Optional[datetime] = None) -> str:
    """Bilet sahibinin takvimi: oturum varsa her oturum bir VEVENT, yoksa tek VEVENT.

    UID kalıcı (`etkinlik-<id>-<sipariş kodu>[-<n>]@alan`): iptal e-postasındaki aynı UID
    STATUS:CANCELLED ile takvimdeki kaydı düşürür.
    """
    from services import dinamik_qr as qr

    an = an or simdi()
    alan = (site_adresi().split("://", 1)[-1].split("/", 1)[0] or "mehmetkuru.dev").split(":", 1)[0]
    oturumlar = json_yukle(e.oturumlar, []) or []
    parcalar = [(o.get("ad") or "", zaman_coz(o["baslangic"], "o"), zaman_coz(o["bitis"], "o")) for o in oturumlar] \
        or [("", utc(e.baslangic), utc(e.bitis))]
    konum = konum_metni(e, dil, sahibine=True)
    aciklama = [e.baslik]
    if e.ozet:
        aciklama.append(e.ozet)
    if bilet_adresi_:
        aciklama.append(bilet_adresi_)
    satirlar = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//mehmetkuru.dev//Etkinlik//TR", "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH"]
    for i, (ad, ob, oe) in enumerate(parcalar):
        uid = f"etkinlik-{e.id}-{siparis_kod}" + (f"-{i + 1}" if len(parcalar) > 1 else "")
        baslik = f"{e.baslik} — {ad}" if ad else e.baslik
        satirlar += [
            "BEGIN:VEVENT",
            f"UID:{uid}@{alan}",
            f"SEQUENCE:{int(sira_no)}",
            "DTSTAMP:" + _ics_an(an),
            "DTSTART:" + _ics_an(ob),
            "DTEND:" + _ics_an(oe),
            f"SUMMARY:{qr._kacis(baslik)}",
            "STATUS:" + ("CANCELLED" if iptal else "CONFIRMED"),
            f"DESCRIPTION:{qr._kacis(chr(10).join(aciklama))}",
            f"LOCATION:{qr._kacis(konum)}",
        ]
        if bilet_adresi_:
            satirlar.append(f"URL:{bilet_adresi_}")
        satirlar.append("END:VEVENT")
    satirlar.append("END:VCALENDAR")
    return "\r\n".join(qr._katla(s) for s in satirlar) + "\r\n"


def takvim_baglantilari(e: Any, dil: str, bilet_adresi_: str, ics_adresi: str) -> Dict[str, str]:
    konum = konum_metni(e, dil, sahibine=True)
    aciklama = "\n".join(x for x in (e.ozet or "", bilet_adresi_) if x)
    return {
        "google": r.google_takvim_adresi(e.baslik, utc(e.baslangic), utc(e.bitis), aciklama, konum),
        "outlook": r.outlook_takvim_adresi(e.baslik, utc(e.baslangic), utc(e.bitis), aciklama, konum),
        "ics": ics_adresi,
    }


# ---------------------------------------------------------------------------
# schema.org Event (JSON-LD) — yalnız "arama motorlarında görünsün" seçiliyken
# ---------------------------------------------------------------------------
def _yerel_iso(an: datetime, tz_adi: str) -> str:
    try:
        tz = saat_dilimi(tz_adi)
    except TemelHata:
        tz = saat_dilimi(VARSAYILAN_SAAT_DILIMI)
    return utc(an).astimezone(tz).isoformat()


def event_jsonld(e: Any, turler: Sequence[Any], dolu: Dict[int, bool], kapak: Optional[str]) -> Dict[str, Any]:
    """Online bağlantı ASLA girmez (VirtualLocation adresi etkinliğin herkese açık sayfası)."""
    adres = sayfa_adresi(e.slug)
    mod = {"yuz_yuze": "Offline", "online": "Online", "karma": "Mixed"}[e.bicim]
    durum = "EventCancelled" if e.durum == "iptal" else "EventScheduled"
    veri: Dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": e.baslik,
        "startDate": _yerel_iso(e.baslangic, e.saat_dilimi),
        "endDate": _yerel_iso(e.bitis, e.saat_dilimi),
        "eventStatus": f"https://schema.org/{durum}",
        "eventAttendanceMode": f"https://schema.org/{mod}EventAttendanceMode",
        "url": adres,
        "inLanguage": e.dil,
    }
    if e.ozet:
        veri["description"] = e.ozet
    if kapak:
        veri["image"] = [kapak]
    konumlar: List[Dict[str, Any]] = []
    if e.bicim in ("yuz_yuze", "karma"):
        yer: Dict[str, Any] = {"@type": "Place", "name": e.mekan_adi or e.baslik}
        if e.adres:
            yer["address"] = {"@type": "PostalAddress", "streetAddress": (e.adres or "").replace("\n", ", ")}
        konumlar.append(yer)
    if e.bicim in ("online", "karma"):
        konumlar.append({"@type": "VirtualLocation", "url": adres})
    if konumlar:
        veri["location"] = konumlar[0] if len(konumlar) == 1 else konumlar
    if e.organizator_ad:
        org: Dict[str, Any] = {"@type": "Organization", "name": e.organizator_ad}
        if e.organizator_url:
            org["url"] = e.organizator_url
        veri["organizer"] = org
    teklifler = []
    for t in turler:
        if not t.aktif or t.gizli:
            continue
        teklif: Dict[str, Any] = {
            "@type": "Offer",
            "name": t.ad,
            "price": f"{int(t.fiyat or 0) / 100:.2f}",
            "priceCurrency": t.para_birimi,
            "availability": "https://schema.org/" + ("SoldOut" if dolu.get(t.id) else "InStock"),
            "url": adres,
        }
        if t.satis_bas:
            teklif["validFrom"] = _yerel_iso(t.satis_bas, e.saat_dilimi)
        teklifler.append(teklif)
    if teklifler:
        veri["offers"] = teklifler
    return veri


# ---------------------------------------------------------------------------
# Katılımcı e-postaları (7 dil; bilgilendirme niteliğinde)
# ---------------------------------------------------------------------------
METINLER: Dict[str, Dict[str, str]] = {
    "tr": {
        "merhaba": "Merhaba {ad},",
        "onay_konu": "Biletiniz hazır: {etkinlik}",
        "onay_giris": "{etkinlik} etkinliğine kaydınız onaylandı.",
        "odeme_konu": "Ödemenizi tamamlayın: {etkinlik}",
        "odeme_giris": "{etkinlik} için yerleriniz {son} saatine kadar ayrıldı. Ödemeyi tamamladığınızda biletleriniz e-postayla gelecek.",
        "odeme_baglanti": "Ödeme bağlantısı:",
        "iptal_konu": "Biletiniz iptal edildi: {etkinlik}",
        "iptal_giris": "{etkinlik} biletiniz iptal edildi.",
        "etkinlik_iptal_konu": "Etkinlik iptal edildi: {etkinlik}",
        "etkinlik_iptal_giris": "Üzgünüz, {etkinlik} etkinliği iptal edildi.",
        "iade_notu": "Ücretli biletlerin iadesi için organizatör sizinle iletişime geçecek.",
        "bekleme_konu": "Bekleme listesindesiniz: {etkinlik}",
        "bekleme_giris": "{etkinlik} için bekleme listesine eklendiniz. Yer açılırsa size 24 saat geçerli bir kayıt bağlantısı göndereceğiz.",
        "davet_konu": "Yer açıldı: {etkinlik}",
        "davet_giris": "{etkinlik} için yer açıldı. Aşağıdaki bağlantıyla {son} saatine kadar kaydınızı tamamlayabilirsiniz.",
        "davet_baglanti": "Kayıt bağlantısı:",
        "duyuru_not": "Bu e-postayı {etkinlik} etkinliğine kayıtlı olduğunuz için alıyorsunuz (etkinlik bilgilendirmesi).",
        "tesekkur_konu": "Katıldığınız için teşekkürler: {etkinlik}",
        "tesekkur_giris": "{etkinlik} etkinliğine katıldığınız için teşekkür ederiz.",
        "anket": "Görüşleriniz bizim için değerli — kısa anketimize katılır mısınız?",
        "ne_zaman": "Zaman", "nerede": "Yer", "bilet": "Bilet", "biletler": "Biletleriniz", "toplam": "Toplam",
        "bilet_sayfasi": "Bilet sayfası (QR kodlar, takvime ekle, iptal):",
        "takvim": "Takvime ekle:",
        "ekler": "Bilet PDF'i ve takvim dosyası (.ics) bu e-postanın ekinde.",
        "online_baglanti": "Çevrim içi katılım bağlantısı:",
        "harita": "Haritada aç:",
        "organizator": "Organizatör", "iade_politikasi": "İptal / iade politikası", "odeme_notu": "Ödeme bilgisi",
        "yuz_yuze": "Yüz yüze", "online": "Çevrim içi", "karma": "Yüz yüze + çevrim içi",
    },
    "en": {
        "merhaba": "Hello {ad},",
        "onay_konu": "Your ticket is ready: {etkinlik}",
        "onay_giris": "Your registration for {etkinlik} is confirmed.",
        "odeme_konu": "Complete your payment: {etkinlik}",
        "odeme_giris": "Your places for {etkinlik} are held until {son}. Your tickets will be emailed once the payment is complete.",
        "odeme_baglanti": "Payment link:",
        "iptal_konu": "Your ticket has been cancelled: {etkinlik}",
        "iptal_giris": "Your ticket for {etkinlik} has been cancelled.",
        "etkinlik_iptal_konu": "Event cancelled: {etkinlik}",
        "etkinlik_iptal_giris": "We are sorry, {etkinlik} has been cancelled.",
        "iade_notu": "The organiser will contact you about refunds for paid tickets.",
        "bekleme_konu": "You are on the waiting list: {etkinlik}",
        "bekleme_giris": "You have been added to the waiting list for {etkinlik}. If a place opens up, we will send you a registration link valid for 24 hours.",
        "davet_konu": "A place has opened up: {etkinlik}",
        "davet_giris": "A place has opened up for {etkinlik}. You can complete your registration with the link below until {son}.",
        "davet_baglanti": "Registration link:",
        "duyuru_not": "You are receiving this email because you are registered for {etkinlik} (event information).",
        "tesekkur_konu": "Thank you for attending: {etkinlik}",
        "tesekkur_giris": "Thank you for attending {etkinlik}.",
        "anket": "Your feedback matters to us — would you take our short survey?",
        "ne_zaman": "When", "nerede": "Where", "bilet": "Ticket", "biletler": "Your tickets", "toplam": "Total",
        "bilet_sayfasi": "Ticket page (QR codes, add to calendar, cancel):",
        "takvim": "Add to calendar:",
        "ekler": "The ticket PDF and the calendar file (.ics) are attached to this email.",
        "online_baglanti": "Online joining link:",
        "harita": "Open in maps:",
        "organizator": "Organiser", "iade_politikasi": "Cancellation / refund policy", "odeme_notu": "Payment information",
        "yuz_yuze": "In person", "online": "Online", "karma": "In person + online",
    },
    "de": {
        "merhaba": "Hallo {ad},",
        "onay_konu": "Ihr Ticket ist bereit: {etkinlik}",
        "onay_giris": "Ihre Anmeldung für {etkinlik} ist bestätigt.",
        "odeme_konu": "Schließen Sie Ihre Zahlung ab: {etkinlik}",
        "odeme_giris": "Ihre Plätze für {etkinlik} sind bis {son} reserviert. Nach Abschluss der Zahlung erhalten Sie Ihre Tickets per E-Mail.",
        "odeme_baglanti": "Zahlungslink:",
        "iptal_konu": "Ihr Ticket wurde storniert: {etkinlik}",
        "iptal_giris": "Ihr Ticket für {etkinlik} wurde storniert.",
        "etkinlik_iptal_konu": "Veranstaltung abgesagt: {etkinlik}",
        "etkinlik_iptal_giris": "Es tut uns leid, {etkinlik} wurde abgesagt.",
        "iade_notu": "Wegen der Erstattung kostenpflichtiger Tickets meldet sich der Veranstalter bei Ihnen.",
        "bekleme_konu": "Sie stehen auf der Warteliste: {etkinlik}",
        "bekleme_giris": "Sie wurden auf die Warteliste für {etkinlik} gesetzt. Wird ein Platz frei, senden wir Ihnen einen 24 Stunden gültigen Anmeldelink.",
        "davet_konu": "Ein Platz ist frei geworden: {etkinlik}",
        "davet_giris": "Für {etkinlik} ist ein Platz frei geworden. Über den folgenden Link können Sie sich bis {son} anmelden.",
        "davet_baglanti": "Anmeldelink:",
        "duyuru_not": "Sie erhalten diese E-Mail, weil Sie für {etkinlik} angemeldet sind (Veranstaltungsinformation).",
        "tesekkur_konu": "Danke für Ihre Teilnahme: {etkinlik}",
        "tesekkur_giris": "Vielen Dank, dass Sie an {etkinlik} teilgenommen haben.",
        "anket": "Ihre Meinung ist uns wichtig — nehmen Sie an unserer kurzen Umfrage teil?",
        "ne_zaman": "Zeit", "nerede": "Ort", "bilet": "Ticket", "biletler": "Ihre Tickets", "toplam": "Gesamt",
        "bilet_sayfasi": "Ticketseite (QR-Codes, zum Kalender hinzufügen, stornieren):",
        "takvim": "Zum Kalender hinzufügen:",
        "ekler": "Das Ticket-PDF und die Kalenderdatei (.ics) sind dieser E-Mail angehängt.",
        "online_baglanti": "Link zur Online-Teilnahme:",
        "harita": "In Karten öffnen:",
        "organizator": "Veranstalter", "iade_politikasi": "Storno- / Erstattungsbedingungen", "odeme_notu": "Zahlungsinformation",
        "yuz_yuze": "Vor Ort", "online": "Online", "karma": "Vor Ort + online",
    },
    "ru": {
        "merhaba": "Здравствуйте, {ad}!",
        "onay_konu": "Ваш билет готов: {etkinlik}",
        "onay_giris": "Ваша регистрация на мероприятие «{etkinlik}» подтверждена.",
        "odeme_konu": "Завершите оплату: {etkinlik}",
        "odeme_giris": "Места на «{etkinlik}» забронированы до {son}. После оплаты билеты придут на вашу почту.",
        "odeme_baglanti": "Ссылка для оплаты:",
        "iptal_konu": "Ваш билет отменён: {etkinlik}",
        "iptal_giris": "Ваш билет на «{etkinlik}» отменён.",
        "etkinlik_iptal_konu": "Мероприятие отменено: {etkinlik}",
        "etkinlik_iptal_giris": "К сожалению, мероприятие «{etkinlik}» отменено.",
        "iade_notu": "Организатор свяжется с вами по поводу возврата средств за платные билеты.",
        "bekleme_konu": "Вы в листе ожидания: {etkinlik}",
        "bekleme_giris": "Вы добавлены в лист ожидания на «{etkinlik}». Если место освободится, мы пришлём ссылку для регистрации, действующую 24 часа.",
        "davet_konu": "Освободилось место: {etkinlik}",
        "davet_giris": "На «{etkinlik}» освободилось место. Завершите регистрацию по ссылке ниже до {son}.",
        "davet_baglanti": "Ссылка для регистрации:",
        "duyuru_not": "Вы получили это письмо, потому что зарегистрированы на «{etkinlik}» (информация о мероприятии).",
        "tesekkur_konu": "Спасибо за участие: {etkinlik}",
        "tesekkur_giris": "Благодарим вас за участие в «{etkinlik}».",
        "anket": "Нам важно ваше мнение — ответите на короткий опрос?",
        "ne_zaman": "Время", "nerede": "Место", "bilet": "Билет", "biletler": "Ваши билеты", "toplam": "Итого",
        "bilet_sayfasi": "Страница билета (QR-коды, добавить в календарь, отмена):",
        "takvim": "Добавить в календарь:",
        "ekler": "PDF с билетами и файл календаря (.ics) приложены к этому письму.",
        "online_baglanti": "Ссылка для онлайн-участия:",
        "harita": "Открыть на карте:",
        "organizator": "Организатор", "iade_politikasi": "Правила отмены и возврата", "odeme_notu": "Информация об оплате",
        "yuz_yuze": "Очно", "online": "Онлайн", "karma": "Очно + онлайн",
    },
    "zh": {
        "merhaba": "{ad}，您好：",
        "onay_konu": "您的门票已就绪：{etkinlik}",
        "onay_giris": "您已成功报名 {etkinlik}。",
        "odeme_konu": "请完成付款：{etkinlik}",
        "odeme_giris": "您在 {etkinlik} 的名额将保留至 {son}。付款完成后，门票将通过电子邮件发送给您。",
        "odeme_baglanti": "付款链接：",
        "iptal_konu": "您的门票已取消：{etkinlik}",
        "iptal_giris": "您在 {etkinlik} 的门票已取消。",
        "etkinlik_iptal_konu": "活动已取消：{etkinlik}",
        "etkinlik_iptal_giris": "很抱歉，{etkinlik} 已取消。",
        "iade_notu": "主办方将就付费门票的退款与您联系。",
        "bekleme_konu": "您已进入候补名单：{etkinlik}",
        "bekleme_giris": "您已加入 {etkinlik} 的候补名单。如有空位，我们会发送一个 24 小时内有效的报名链接。",
        "davet_konu": "有空位了：{etkinlik}",
        "davet_giris": "{etkinlik} 有空位了。请在 {son} 之前通过下方链接完成报名。",
        "davet_baglanti": "报名链接：",
        "duyuru_not": "您收到此邮件是因为您已报名 {etkinlik}（活动通知）。",
        "tesekkur_konu": "感谢您的参与：{etkinlik}",
        "tesekkur_giris": "感谢您参加 {etkinlik}。",
        "anket": "您的意见对我们很重要——愿意填写一份简短的问卷吗？",
        "ne_zaman": "时间", "nerede": "地点", "bilet": "门票", "biletler": "您的门票", "toplam": "合计",
        "bilet_sayfasi": "门票页面（二维码、添加到日历、取消）：",
        "takvim": "添加到日历：",
        "ekler": "门票 PDF 和日历文件 (.ics) 已附在本邮件中。",
        "online_baglanti": "线上参与链接：",
        "harita": "在地图中打开：",
        "organizator": "主办方", "iade_politikasi": "取消 / 退款政策", "odeme_notu": "付款信息",
        "yuz_yuze": "线下", "online": "线上", "karma": "线下 + 线上",
    },
    "hi": {
        "merhaba": "नमस्ते {ad},",
        "onay_konu": "आपका टिकट तैयार है: {etkinlik}",
        "onay_giris": "{etkinlik} के लिए आपका पंजीकरण पक्का हो गया है।",
        "odeme_konu": "अपना भुगतान पूरा करें: {etkinlik}",
        "odeme_giris": "{etkinlik} के लिए आपकी जगहें {son} तक आरक्षित हैं। भुगतान पूरा होते ही आपके टिकट ईमेल से आ जाएँगे।",
        "odeme_baglanti": "भुगतान लिंक:",
        "iptal_konu": "आपका टिकट रद्द कर दिया गया: {etkinlik}",
        "iptal_giris": "{etkinlik} के लिए आपका टिकट रद्द कर दिया गया है।",
        "etkinlik_iptal_konu": "कार्यक्रम रद्द: {etkinlik}",
        "etkinlik_iptal_giris": "हमें खेद है, {etkinlik} रद्द कर दिया गया है।",
        "iade_notu": "सशुल्क टिकटों की धनवापसी के लिए आयोजक आपसे संपर्क करेंगे।",
        "bekleme_konu": "आप प्रतीक्षा सूची में हैं: {etkinlik}",
        "bekleme_giris": "आपको {etkinlik} की प्रतीक्षा सूची में जोड़ दिया गया है। जगह खाली होने पर हम आपको 24 घंटे तक मान्य पंजीकरण लिंक भेजेंगे।",
        "davet_konu": "जगह खाली हुई: {etkinlik}",
        "davet_giris": "{etkinlik} में एक जगह खाली हुई है। नीचे दिए लिंक से {son} तक अपना पंजीकरण पूरा करें।",
        "davet_baglanti": "पंजीकरण लिंक:",
        "duyuru_not": "आपको यह ईमेल इसलिए मिला है क्योंकि आपने {etkinlik} के लिए पंजीकरण किया है (कार्यक्रम सूचना)।",
        "tesekkur_konu": "भाग लेने के लिए धन्यवाद: {etkinlik}",
        "tesekkur_giris": "{etkinlik} में भाग लेने के लिए धन्यवाद।",
        "anket": "आपकी राय हमारे लिए महत्वपूर्ण है — क्या आप हमारा छोटा सर्वे भरेंगे?",
        "ne_zaman": "समय", "nerede": "स्थान", "bilet": "टिकट", "biletler": "आपके टिकट", "toplam": "कुल",
        "bilet_sayfasi": "टिकट पेज (QR कोड, कैलेंडर में जोड़ें, रद्द करें):",
        "takvim": "कैलेंडर में जोड़ें:",
        "ekler": "टिकट PDF और कैलेंडर फ़ाइल (.ics) इस ईमेल के साथ संलग्न हैं।",
        "online_baglanti": "ऑनलाइन जुड़ने का लिंक:",
        "harita": "मानचित्र में खोलें:",
        "organizator": "आयोजक", "iade_politikasi": "रद्दीकरण / धनवापसी नीति", "odeme_notu": "भुगतान जानकारी",
        "yuz_yuze": "व्यक्तिगत रूप से", "online": "ऑनलाइन", "karma": "व्यक्तिगत रूप से + ऑनलाइन",
    },
    "ar": {
        "merhaba": "مرحبًا {ad}،",
        "onay_konu": "تذكرتك جاهزة: {etkinlik}",
        "onay_giris": "تم تأكيد تسجيلك في {etkinlik}.",
        "odeme_konu": "أكمل الدفع: {etkinlik}",
        "odeme_giris": "تم حجز أماكنك في {etkinlik} حتى {son}. ستصلك التذاكر عبر البريد الإلكتروني بعد إتمام الدفع.",
        "odeme_baglanti": "رابط الدفع:",
        "iptal_konu": "تم إلغاء تذكرتك: {etkinlik}",
        "iptal_giris": "تم إلغاء تذكرتك لفعالية {etkinlik}.",
        "etkinlik_iptal_konu": "تم إلغاء الفعالية: {etkinlik}",
        "etkinlik_iptal_giris": "نأسف، تم إلغاء فعالية {etkinlik}.",
        "iade_notu": "سيتواصل معك المنظم بشأن استرداد قيمة التذاكر المدفوعة.",
        "bekleme_konu": "أنت في قائمة الانتظار: {etkinlik}",
        "bekleme_giris": "تمت إضافتك إلى قائمة الانتظار لفعالية {etkinlik}. إذا توفر مكان، سنرسل إليك رابط تسجيل صالحًا لمدة 24 ساعة.",
        "davet_konu": "توفر مكان: {etkinlik}",
        "davet_giris": "توفر مكان في {etkinlik}. يمكنك إكمال تسجيلك عبر الرابط أدناه حتى {son}.",
        "davet_baglanti": "رابط التسجيل:",
        "duyuru_not": "تصلك هذه الرسالة لأنك مسجل في {etkinlik} (معلومات عن الفعالية).",
        "tesekkur_konu": "شكرًا لحضورك: {etkinlik}",
        "tesekkur_giris": "شكرًا لحضورك {etkinlik}.",
        "anket": "رأيك يهمنا — هل تشارك في استبياننا القصير؟",
        "ne_zaman": "الوقت", "nerede": "المكان", "bilet": "التذكرة", "biletler": "تذاكرك", "toplam": "الإجمالي",
        "bilet_sayfasi": "صفحة التذكرة (رموز QR، الإضافة إلى التقويم، الإلغاء):",
        "takvim": "أضف إلى التقويم:",
        "ekler": "ملف PDF للتذاكر وملف التقويم (.ics) مرفقان بهذه الرسالة.",
        "online_baglanti": "رابط الحضور عبر الإنترنت:",
        "harita": "افتح في الخرائط:",
        "organizator": "المنظم", "iade_politikasi": "سياسة الإلغاء / الاسترداد", "odeme_notu": "معلومات الدفع",
        "yuz_yuze": "حضوريًا", "online": "عبر الإنترنت", "karma": "حضوريًا + عبر الإنترنت",
    },
}


def metinler(dil: str) -> Dict[str, str]:
    return METINLER.get(dil) or METINLER["tr"]


def eposta_govdesi(tur: str, dil: str, *, ad: str, e: Any, satirlar: Sequence[str] = (),
                   son: Optional[str] = None) -> Tuple[str, str]:
    """(konu, metin). `tur`: onay | odeme | iptal | etkinlik_iptal | bekleme | davet | tesekkur."""
    m = metinler(dil)
    konu = m[f"{tur}_konu"].format(etkinlik=e.baslik)
    govde = [m["merhaba"].format(ad=ad or "—"), "", m[f"{tur}_giris"].format(etkinlik=e.baslik, son=son or ""), ""]
    if tur in ("onay", "odeme", "davet", "bekleme", "etkinlik_iptal", "iptal"):
        govde.append(f"{m['ne_zaman']}: {aralik_yaz(e.baslangic, e.bitis, e.saat_dilimi, dil)}")
        govde.append(f"{m['nerede']}: {konum_metni(e, dil, sahibine=tur == 'onay')}")
    govde += list(satirlar)
    govde += ["", f"— {e.organizator_ad or e.baslik}"]
    return konu, "\n".join(govde)


# ---------------------------------------------------------------------------
# Bilet PDF'i (QR'lı) — ReportLab, sitenin yazı tipi
# ---------------------------------------------------------------------------
PDF_ETIKET = {
    "tr": {"bilet": "Bilet", "etkinlik": "Etkinlik", "zaman": "Zaman", "yer": "Yer", "katilimci": "Katılımcı",
           "tur": "Bilet türü", "kod": "Bilet kodu", "goster": "Girişte bu QR kodu gösterin (ekrandan ya da çıktı).",
           "siparis": "Kayıt", "iptal": "İPTAL", "odeme": "ÖDEME BEKLENİYOR"},
    "en": {"bilet": "Ticket", "etkinlik": "Event", "zaman": "When", "yer": "Where", "katilimci": "Attendee",
           "tur": "Ticket type", "kod": "Ticket code", "goster": "Show this QR code at the entrance (on screen or printed).",
           "siparis": "Registration", "iptal": "CANCELLED", "odeme": "PAYMENT PENDING"},
    "de": {"bilet": "Ticket", "etkinlik": "Veranstaltung", "zaman": "Wann", "yer": "Wo", "katilimci": "Teilnehmer",
           "tur": "Ticketart", "kod": "Ticketcode",
           "goster": "Zeigen Sie diesen QR-Code am Eingang (auf dem Bildschirm oder ausgedruckt).",
           "siparis": "Anmeldung", "iptal": "STORNIERT", "odeme": "ZAHLUNG AUSSTEHEND"},
    "ru": {"bilet": "Билет", "etkinlik": "Мероприятие", "zaman": "Когда", "yer": "Где", "katilimci": "Участник",
           "tur": "Тип билета", "kod": "Код билета",
           "goster": "Покажите этот QR-код на входе (на экране или распечатанным).",
           "siparis": "Регистрация", "iptal": "ОТМЕНЁН", "odeme": "ОЖИДАЕТСЯ ОПЛАТА"},
    "zh": {"bilet": "门票", "etkinlik": "活动", "zaman": "时间", "yer": "地点", "katilimci": "参加者", "tur": "票种",
           "kod": "票码", "goster": "入场时请出示此二维码（屏幕或打印件均可）。", "siparis": "报名", "iptal": "已取消",
           "odeme": "待付款"},
    "hi": {"bilet": "टिकट", "etkinlik": "कार्यक्रम", "zaman": "कब", "yer": "कहाँ", "katilimci": "प्रतिभागी",
           "tur": "टिकट प्रकार", "kod": "टिकट कोड", "goster": "प्रवेश पर यह QR कोड दिखाएँ (स्क्रीन पर या प्रिंट किया हुआ)।",
           "siparis": "पंजीकरण", "iptal": "रद्द", "odeme": "भुगतान लंबित"},
    "ar": {"bilet": "تذكرة", "etkinlik": "الفعالية", "zaman": "الوقت", "yer": "المكان", "katilimci": "المشارك",
           "tur": "نوع التذكرة", "kod": "رمز التذكرة", "goster": "اعرض رمز QR هذا عند المدخل (على الشاشة أو مطبوعًا).",
           "siparis": "التسجيل", "iptal": "ملغاة", "odeme": "بانتظار الدفع"},
}


def bilet_pdf(e: Any, siparis: Any, biletler: Sequence[Tuple[Any, str]], dil: str = "tr") -> bytes:
    """Her bilet ayrı sayfa: künye, etkinlik bilgisi, büyük QR (vektör), kod.

    `biletler`: [(bilet, tür adı)]. Etiketler 7 dilde; Kiril/Arap/Çin/Devanagari adlar Faz 7K'dan beri
    `services/pdf_yazi.py`'nin yazı tipi zinciriyle doğru çıkıyor.
    """
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Spacer, Table, TableStyle

    from services import pdf_belge as pb
    from services.pdf_yazi import Paragraf as Paragraph  # çok dilli paragraf

    d = dil if dil in PDF_ETIKET else "en"
    et = PDF_ETIKET[d]
    st = pb._stiller()
    parcalar: List[Any] = []
    zaman = aralik_yaz(e.baslangic, e.bitis, e.saat_dilimi, d)
    yer = konum_metni(e, d, sahibine=False)
    for i, (b, tur_adi) in enumerate(biletler):
        if i:
            parcalar.append(PageBreak())
        parcalar += [pb.MarkaKunyesi("By Mehmet KURU Dev", "Etkinlik · Event"), Spacer(1, 8 * mm)]
        baslik = pb._metin(e.baslik)
        parcalar.append(Paragraph(f"<b>{baslik}</b>", st["h1"]))
        satirlar = [
            (et["zaman"], zaman), (et["yer"], yer), (et["tur"], tur_adi),
            (et["katilimci"], b.katilimci_ad or siparis.ad or "—"), (et["siparis"], siparis.kod),
        ]
        tablo = Table([[Paragraph(f"<font color='#5B5368'>{pb._metin(a)}</font>", st["govde"]),
                        Paragraph(pb._metin(v), st["kalin"])] for a, v in satirlar], colWidths=[35 * mm, 140 * mm])
        tablo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        parcalar += [tablo, Spacer(1, 8 * mm)]
        kenar = 70 * mm
        w = QrCodeWidget(qr_icerigi(b.kod), barLevel="M")
        x1, y1, x2, y2 = w.getBounds()
        ciz = Drawing(kenar, kenar, transform=[kenar / (x2 - x1), 0, 0, kenar / (y2 - y1), 0, 0])
        ciz.add(w)
        qr_tablo = Table([[ciz], [Paragraph(f"<b>{et['kod']}: {b.kod}</b>", st["h2"])],
                          [Paragraph(pb._metin(et["goster"]), st["kucuk"])]], colWidths=[180 * mm])
        qr_tablo.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        parcalar.append(qr_tablo)
        if b.durum != "gecerli":
            parcalar += [Spacer(1, 4 * mm), Paragraph(
                f"<font color='#B91C1C'><b>{et['iptal'] if b.durum == 'iptal' else et['odeme']}</b></font>", st["h2"])]
    not_metni = f"{e.baslik} · {siparis.kod}"
    return pb._uret(parcalar, not_metni, d, f"{et['bilet']} {siparis.kod}")


def csv_hucre(deger: Any) -> Any:
    """Tablo programında formül olarak çalışmasın (CSV enjeksiyonu)."""
    if isinstance(deger, str) and deger[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + deger
    return deger


__all__ = [
    "MODUL", "IZIN", "IZIN_GIRIS", "EtkinlikHatasi", "TemelHata", "simdi", "fiyat_hesapla", "kalemleri_duzelt",
    "siparis_jetonu", "qr_icerigi", "okutma_coz", "gorevli_jetonu", "gorevli_jetonu_coz", "davet_jetonu",
    "ics_uret", "event_jsonld", "eposta_govdesi", "bilet_pdf",
]
