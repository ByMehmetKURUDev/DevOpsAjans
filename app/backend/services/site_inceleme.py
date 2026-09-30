"""HTML inceleme yardımcıları — site taraması ile site analizinin ortak parçası.

İki yer aynı işi yapıyor: panelde kendi sitemizi tarayan `routers/site_tarama`
ve ziyaretçinin verdiği herhangi bir siteyi inceleyen `site_analizi`. İkisi
de sayfanın başlığına, açıklamasına, H1'ine, bağlantılarına bakıyor; kurallar
iki yerde ayrı ayrı yazılırsa zamanla ayrışır ("tarama başlığı kısa diyor,
analiz demiyor"). Bu yüzden okuma burada, tek yerde.

HTML'i regex ile okuyoruz. Tam bir ayrıştırıcı değil ve olmak zorunda da
değil: baktığımız etiketlerin hepsi <head> içinde, tek satırlık, üretilmiş
çıktı. Bağımlılık eklememek (beautifulsoup/lxml) ücretsiz katmanda derleme
süresi ve bellek demek.

Buradaki fonksiyonlar yan etkisiz: ağa çıkmıyor, yalnızca metin okuyor.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

BASLIK = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
H1 = re.compile(r"<h1[\s>]", re.I)
LANG = re.compile(r"<html[^>]*\slang\s*=\s*[\"']([^\"']+)", re.I)
CANONICAL = re.compile(r"<link[^>]+rel\s*=\s*[\"']canonical[\"'][^>]*>", re.I)
IMG = re.compile(r"<img\b[^>]*>", re.I)
ALT = re.compile(r"\salt\s*=", re.I)
#: Ayni geri basvuru mantigi: apostrof tasiyan adres kesilmesin.
HREF = re.compile(r"<a\b[^>]*\shref\s*=\s*([\"'])(.*?)\1", re.I)
ETIKET_TEMIZ = re.compile(r"<[^>]+>")
HREFLANG = re.compile(r"<link[^>]+hreflang\s*=", re.I)
JSONLD = re.compile(r"<script[^>]+type\s*=\s*[\"']application/ld\+json[\"']", re.I)
#: Kelime sayarken görünmeyen blokları atıyoruz: betik ve stil metni
#: "içerik" değil, sayıya girerse ince bir sayfa dolu görünür.
_GORUNMEZ = re.compile(
    r"<(script|style|noscript|template|svg)\b[^>]*>.*?</\1\s*>", re.I | re.S
)
_YORUM = re.compile(r"<!--.*?-->", re.S)
_KELIME = re.compile(r"\w+", re.U)
_VARLIK = re.compile(r"&[#\w]+;")


def meta(html: str, ad: str, alan: str = "name") -> str:
    kalip = re.compile(
        r"<meta[^>]+" + alan + r"\s*=\s*[\"']" + re.escape(ad) + r"[\"'][^>]*>",
        re.I,
    )
    m = kalip.search(html)
    if not m:
        return ""
    # Kapanis tirnagi ACILIS tirnagiyla ayni olmali (geri basvuru).
    # Onceden `[\"']` yaziyordu: content="Turkiye'nin ..." gibi bir
    # degerde ic apostrof kapanis sanilip metin 7 karakterde kesiliyordu.
    # Tarama da "aciklama cok kisa" diye YANLIS uyari veriyordu.
    icerik = re.search(r"content\s*=\s*([\"'])(.*?)\1", m.group(0), re.I | re.S)
    return (icerik.group(2).strip() if icerik else "")


def genislik(metin: str) -> int:
    """Metnin arama sonucunda kaplayacagi yaklasik genislik.

    Google baslik ve aciklamayi karakter sayisina gore degil, PIKSEL
    genisligine gore kesiyor. Cince/Japonca/Korece karakterler latin
    harflerin yaklasik iki kati genislikte; ayni bilgi yarisi kadar
    karakterle anlatiliyor.

    Karakter sayarak olctugumuzde Cince sayfalarin hepsi "aciklama cok
    kisa" diye uyari veriyordu -- 64 karakterlik bir Cince aciklama
    aslinda ~130 latin karakteri genisliginde ve gayet yeterli. Bu
    yuzden CJK araliklarindaki her karakter iki sayiliyor.
    """
    toplam = 0
    for ch in metin:
        k = ord(ch)
        genis = (
            0x1100 <= k <= 0x115F        # Hangul Jamo
            or 0x2E80 <= k <= 0xA4CF     # CJK radikalleri, Kana, Han
            or 0xAC00 <= k <= 0xD7A3     # Hangul heceleri
            or 0xF900 <= k <= 0xFAFF     # CJK uyumluluk
            or 0xFF00 <= k <= 0xFF60     # tam genislikte biçimler
            or 0x20000 <= k <= 0x3FFFD   # CJK ek düzlemler
        )
        toplam += 2 if genis else 1
    return toplam


def metin(ham: str) -> str:
    return ETIKET_TEMIZ.sub("", ham).strip()


def sitemap_adresleri(xml: str) -> List[str]:
    return [u.strip() for u in re.findall(r"<loc>(.*?)</loc>", xml, re.I | re.S)]


def sitemap_dizini_mi(xml: str) -> bool:
    """`<sitemapindex>` başka sitemap'leri listeler, sayfaları değil."""
    return bool(re.search(r"<sitemapindex[\s>]", xml, re.I))


def normalize(ham: str, sayfa: str, taban: str) -> Optional[str]:
    """Göreli adresi mutlak yapar; site dışını ve gezilemezleri eler.

    `taban` sitenin kökü (`https://alan.com`, sonda eğik çizgi yok).
    """
    u = ham.strip()
    if not u or u.startswith("#"):
        return None
    if u.startswith(("mailto:", "tel:", "sms:", "javascript:", "data:", "whatsapp:")):
        return None
    if u.startswith("//"):
        return None
    if u.startswith("/"):
        u = taban + u
    elif not u.startswith("http"):
        kok = sayfa.rsplit("/", 1)[0]
        u = f"{kok}/{u}"
    u = u.split("#", 1)[0].rstrip("/")
    return u or taban


def ham_baglantilar(html: str) -> List[str]:
    """Sayfadaki `<a href>` değerleri, olduğu gibi."""
    return [ham for _tirnak, ham in HREF.findall(html)]


def altsiz_gorsel_sayisi(html: str) -> int:
    return sum(1 for g in IMG.findall(html) if not ALT.search(g))


def kelime_sayisi(html: str) -> int:
    """Sayfada okunabilir metnin kelime sayısı (yaklaşık)."""
    govde = _YORUM.sub(" ", html)
    govde = _GORUNMEZ.sub(" ", govde)
    govde = ETIKET_TEMIZ.sub(" ", govde)
    govde = _VARLIK.sub(" ", govde)
    return len(_KELIME.findall(govde))


@dataclass
class SayfaOzellikleri:
    """Bir HTML sayfasından okunan ham bilgiler; yorum yok, yalnız ölçüm."""

    baslik: str = ""
    aciklama: str = ""
    h1_sayisi: int = 0
    canonical_var: bool = False
    lang_var: bool = False
    og_image_var: bool = False
    robots_meta: str = ""
    altsiz_gorsel: int = 0
    hreflang_var: bool = False
    jsonld_var: bool = False
    hrefler: List[str] = field(default_factory=list)


def sayfa_ozellikleri(html: str) -> SayfaOzellikleri:
    m = BASLIK.search(html)
    return SayfaOzellikleri(
        baslik=metin(m.group(1)) if m else "",
        aciklama=meta(html, "description"),
        h1_sayisi=len(H1.findall(html)),
        canonical_var=bool(CANONICAL.search(html)),
        lang_var=bool(LANG.search(html)),
        og_image_var=bool(meta(html, "og:image", alan="property")),
        robots_meta=(meta(html, "robots") or "").lower(),
        altsiz_gorsel=altsiz_gorsel_sayisi(html),
        hreflang_var=bool(HREFLANG.search(html)),
        jsonld_var=bool(JSONLD.search(html)),
        hrefler=ham_baglantilar(html),
    )


# --------------------------------------------------------------------------
# robots.txt
# --------------------------------------------------------------------------
def robots_gruplari(metin_: str) -> List[tuple]:
    """robots.txt'yi (ajanlar, kurallar) gruplarına ayırır.

    Ardışık `User-agent` satırları aynı grubu paylaşır; araya bir kural
    girince yeni grup başlar. Kurallar (alan, değer) çiftleri, alan küçük
    harfle.
    """
    gruplar: List[tuple] = []
    ajanlar: List[str] = []
    kurallar: List[tuple] = []
    kural_goruldu = False
    for satir in metin_.splitlines():
        satir = satir.split("#", 1)[0].strip()
        if not satir or ":" not in satir:
            continue
        alan, deger = satir.split(":", 1)
        alan = alan.strip().lower()
        deger = deger.strip()
        if alan == "user-agent":
            if kural_goruldu:
                gruplar.append((ajanlar, kurallar))
                ajanlar, kurallar, kural_goruldu = [], [], False
            ajanlar.append(deger.lower())
        elif alan in ("allow", "disallow"):
            if ajanlar:
                kurallar.append((alan, deger))
                kural_goruldu = True
    if ajanlar:
        gruplar.append((ajanlar, kurallar))
    return gruplar


def robots_tumden_engelli_mi(metin_: str, ajan: str) -> bool:
    """Ajan sitenin tamamına kapalı mı? (`Disallow: /`, `Allow: /` yok)

    Ajanın kendi grubu varsa o geçerli; yoksa `*` grubu. Kısmi engeller
    (yalnız /admin gibi) "engelli" sayılmıyor — soru sitenin yapay zekâ
    arama motorlarına görünüp görünmediği.
    """
    ajan = ajan.lower()
    gruplar = robots_gruplari(metin_)
    ozel = [k for a, k in gruplar if ajan in a]
    genel = [k for a, k in gruplar if "*" in a]
    secili = ozel or genel
    if not secili:
        return False
    kurallar = [k for grup in secili for k in grup]
    kok_engel = any(alan == "disallow" and deger == "/" for alan, deger in kurallar)
    kok_izin = any(alan == "allow" and deger == "/" for alan, deger in kurallar)
    return kok_engel and not kok_izin
