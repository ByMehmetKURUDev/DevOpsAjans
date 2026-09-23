"""Ajan tabanlı site taraması.

Ne yapıyor
----------
Yayındaki siteyi DIŞARIDAN, bir tarayıcı botu gibi geziyor: sitemap.xml'i
okuyup her sayfayı tek tek çekiyor ve HTML'ine bakıyor. Sonuç panelde
liste olarak duruyor.

Neden panelde ayrı bir tarama var
---------------------------------
PageSpeed tek bir sayfanın hızını ölçüyor, Search Console ise Google'ın
kendi taramasını -- ikisi de "başlık etiketi 90 karakter olmuş",
"şu sayfada H1 yok", "menüdeki şu bağlantı 404 veriyor" demiyor. Bunlar
her yayından sonra elle bakılacak şeyler değil; bakılmadığı için de fark
edilmiyor. Tarama bunları söylüyor.

Sınırlar bilerek dar
--------------------
Sunucu ücretsiz katmanda; tarama bir istek içinde bitmek zorunda. O yüzden
sayfa sayısı, eşzamanlılık ve zaman aşımı sabit tavanlarla sınırlı. Site
büyürse burada sayfa sayısını artırmak yerine taramayı parçalara bölmek
gerekir.

Uç yalnızca yöneticiye açık: herkese açık olsaydı site kendi sunucusunu
yormak için kullanılabilirdi.
"""

import asyncio
import logging
import os
import re
import time
from typing import Dict, List, Optional, Tuple

import httpx
from dependencies.entity_guard import entity_guard
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, HTTPException, Request, status
from fastapi import Depends as _Depends
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/site-scan",
    tags=["site_scan"],
    dependencies=[_Depends(entity_guard)],
)

#: Taranacak sitenin adresi. Ortam değişkeniyle değiştirilebiliyor ki
#: önizleme dalları kendi adreslerini tarayabilsin.
SITE_ADRESI = (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")

SAYFA_TAVANI = 60          # sitemap'ten alınacak en fazla sayfa
BAGLANTI_TAVANI = 150      # ayrıca durumu denetlenecek en fazla benzersiz bağlantı
ESZAMANLILIK = 6           # aynı anda açık istek
ISTEK_ZAMAN_ASIMI = 12.0   # saniye
GOVDE_TAVANI = 1_500_000   # 1.5 MB'tan büyük gövdeyi okumuyoruz

BASLIK_ALT, BASLIK_UST = 15, 65
ACIKLAMA_ALT, ACIKLAMA_UST = 70, 165

AJAN = "MehmetKuruDevSiteTaramasi/1.0 (+https://mehmetkuru.dev)"


class Bulgu(BaseModel):
    """Bulgunun kendisi, metni degil.

    Metni panel yaziyor: panel yedi dilde ve arka uc hangi dilde
    bakildigini bilmiyor. Burasi ne oldugunu (`kod`) ve varsa sayiyi
    (`deger`) soyluyor, cumleyi i18n kuruyor.
    """

    kod: str
    seviye: str  # "hata" | "uyari" | "bilgi"
    deger: Optional[int] = None


class SayfaRaporu(BaseModel):
    url: str
    durum: int
    sure_ms: int
    boyut: int
    baslik: str = ""
    bulgular: List[Bulgu] = []


class KirikBaglanti(BaseModel):
    url: str
    durum: int
    kaynaklar: List[str] = []


class Not(BaseModel):
    """Taramanin kendisiyle ilgili aciklama (tavana takilma gibi)."""

    kod: str
    deger: Optional[int] = None
    tavan: Optional[int] = None


class TaramaRaporu(BaseModel):
    site: str
    sayfa_sayisi: int
    baglanti_sayisi: int
    sure_ms: int
    ozet: Dict[str, int]
    sayfalar: List[SayfaRaporu]
    kirik_baglantilar: List[KirikBaglanti]
    notlar: List[Not] = []


# --------------------------------------------------------------------------
# HTML'i regex ile okuyoruz. Tam bir ayrıştırıcı değil ve olmak zorunda da
# değil: baktığımız etiketlerin hepsi <head> içinde, tek satırlık, üretilmiş
# çıktı. Bağımlılık eklememek (beautifulsoup/lxml) ücretsiz katmanda
# derleme süresi ve bellek demek.
# --------------------------------------------------------------------------

_BASLIK = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_H1 = re.compile(r"<h1[\s>]", re.I)
_LANG = re.compile(r"<html[^>]*\slang\s*=\s*[\"']([^\"']+)", re.I)
_CANONICAL = re.compile(r"<link[^>]+rel\s*=\s*[\"']canonical[\"'][^>]*>", re.I)
_IMG = re.compile(r"<img\b[^>]*>", re.I)
_ALT = re.compile(r"\salt\s*=", re.I)
_HREF = re.compile(r"<a\b[^>]*\shref\s*=\s*[\"']([^\"']+)[\"']", re.I)
_ETIKET_TEMIZ = re.compile(r"<[^>]+>")


def _meta(html: str, ad: str, alan: str = "name") -> str:
    kalip = re.compile(
        r"<meta[^>]+" + alan + r"\s*=\s*[\"']" + re.escape(ad) + r"[\"'][^>]*>",
        re.I,
    )
    m = kalip.search(html)
    if not m:
        return ""
    icerik = re.search(r"content\s*=\s*[\"'](.*?)[\"']", m.group(0), re.I | re.S)
    return (icerik.group(1).strip() if icerik else "")


def _metin(ham: str) -> str:
    return _ETIKET_TEMIZ.sub("", ham).strip()


def _sitemap_adresleri(xml: str) -> List[str]:
    return [u.strip() for u in re.findall(r"<loc>(.*?)</loc>", xml, re.I | re.S)]


def _ic_baglanti_mi(url: str) -> bool:
    return url.startswith(SITE_ADRESI)


def _normalize(ham: str, sayfa: str) -> Optional[str]:
    """Göreli adresi mutlak yapar; site dışını ve gezilemezleri eler."""
    u = ham.strip()
    if not u or u.startswith("#"):
        return None
    if u.startswith(("mailto:", "tel:", "sms:", "javascript:", "data:", "whatsapp:")):
        return None
    if u.startswith("//"):
        return None
    if u.startswith("/"):
        u = SITE_ADRESI + u
    elif not u.startswith("http"):
        taban = sayfa.rsplit("/", 1)[0]
        u = f"{taban}/{u}"
    u = u.split("#", 1)[0].rstrip("/")
    return u or SITE_ADRESI


def _sayfayi_incele(url: str, durum: int, sure_ms: int, html: str) -> Tuple[SayfaRaporu, List[str]]:
    bulgular: List[Bulgu] = []
    baglantilar: List[str] = []

    if durum >= 400:
        bulgular.append(Bulgu(kod="durum", seviye="hata", deger=durum))
        return SayfaRaporu(url=url, durum=durum, sure_ms=sure_ms, boyut=len(html),
                           bulgular=bulgular), baglantilar

    if sure_ms > 2500:
        bulgular.append(Bulgu(kod="yavas", seviye="uyari", deger=sure_ms))

    m = _BASLIK.search(html)
    baslik = _metin(m.group(1)) if m else ""
    if not baslik:
        bulgular.append(Bulgu(kod="baslik_yok", seviye="hata"))
    elif len(baslik) < BASLIK_ALT:
        bulgular.append(Bulgu(kod="baslik_kisa", seviye="uyari", deger=len(baslik)))
    elif len(baslik) > BASLIK_UST:
        bulgular.append(Bulgu(kod="baslik_uzun", seviye="uyari", deger=len(baslik)))

    aciklama = _meta(html, "description")
    if not aciklama:
        bulgular.append(Bulgu(kod="aciklama_yok", seviye="hata"))
    elif len(aciklama) < ACIKLAMA_ALT:
        bulgular.append(Bulgu(kod="aciklama_kisa", seviye="uyari", deger=len(aciklama)))
    elif len(aciklama) > ACIKLAMA_UST:
        bulgular.append(Bulgu(kod="aciklama_uzun", seviye="uyari", deger=len(aciklama)))

    h1_sayisi = len(_H1.findall(html))
    if h1_sayisi == 0:
        bulgular.append(Bulgu(kod="h1_yok", seviye="hata"))
    elif h1_sayisi > 1:
        bulgular.append(Bulgu(kod="h1_fazla", seviye="uyari", deger=h1_sayisi))

    if not _CANONICAL.search(html):
        bulgular.append(Bulgu(kod="canonical_yok", seviye="uyari"))

    if not _LANG.search(html):
        bulgular.append(Bulgu(kod="lang_yok", seviye="uyari"))

    if not _meta(html, "og:image", alan="property"):
        bulgular.append(Bulgu(kod="og_yok", seviye="bilgi"))

    robots = (_meta(html, "robots") or "").lower()
    if "noindex" in robots:
        bulgular.append(Bulgu(kod="noindex", seviye="hata"))

    altsiz = sum(1 for g in _IMG.findall(html) if not _ALT.search(g))
    if altsiz:
        bulgular.append(Bulgu(kod="alt_yok", seviye="uyari", deger=altsiz))

    if len(html) > 400_000:
        bulgular.append(Bulgu(kod="agir", seviye="uyari", deger=len(html) // 1024))

    for ham in _HREF.findall(html):
        hedef = _normalize(ham, url)
        if hedef and _ic_baglanti_mi(hedef):
            baglantilar.append(hedef)

    return SayfaRaporu(url=url, durum=durum, sure_ms=sure_ms, boyut=len(html),
                       baslik=baslik, bulgular=bulgular), baglantilar


async def _cek(istemci: httpx.AsyncClient, url: str) -> Tuple[int, int, str]:
    basla = time.perf_counter()
    try:
        yanit = await istemci.get(url)
    except httpx.HTTPError as exc:
        logger.info("Tarama isteği başarısız: %s (%s)", url, type(exc).__name__)
        return 0, int((time.perf_counter() - basla) * 1000), ""
    sure = int((time.perf_counter() - basla) * 1000)
    govde = yanit.text[:GOVDE_TAVANI] if "html" in (
        yanit.headers.get("content-type") or ""
    ) else ""
    return yanit.status_code, sure, govde


async def _durum(istemci: httpx.AsyncClient, url: str) -> int:
    """Bağlantı denetimi: önce HEAD, sunucu kabul etmezse GET."""
    try:
        yanit = await istemci.head(url)
        if yanit.status_code in (405, 501):
            yanit = await istemci.get(url)
        return yanit.status_code
    except httpx.HTTPError:
        return 0


@router.post("", response_model=TaramaRaporu)
async def tarama_calistir(request: Request):
    _, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için yönetici olmanız gerekiyor",
        )

    basla = time.perf_counter()
    notlar: List[Not] = []

    limitler = httpx.Limits(max_connections=ESZAMANLILIK, max_keepalive_connections=ESZAMANLILIK)
    async with httpx.AsyncClient(
        timeout=ISTEK_ZAMAN_ASIMI,
        follow_redirects=True,
        headers={"user-agent": AJAN},
        limits=limitler,
    ) as istemci:
        # 1) Sitemap
        try:
            sm = await istemci.get(f"{SITE_ADRESI}/sitemap.xml")
            adresler = _sitemap_adresleri(sm.text) if sm.status_code == 200 else []
        except httpx.HTTPError:
            adresler = []

        if not adresler:
            notlar.append(Not(kod="sitemap_yok"))
            adresler = [SITE_ADRESI + "/"]

        # Aynı sayfanın dil kopyaları raporu şişiriyor; benzersizleştirip
        # tavanı uyguluyoruz.
        benzersiz: List[str] = []
        for a in adresler:
            a = a.strip()
            if a and a not in benzersiz:
                benzersiz.append(a)
        if len(benzersiz) > SAYFA_TAVANI:
            notlar.append(
                Not(kod="sayfa_tavani", deger=len(benzersiz), tavan=SAYFA_TAVANI)
            )
            benzersiz = benzersiz[:SAYFA_TAVANI]

        # 2) Sayfalar
        kilit = asyncio.Semaphore(ESZAMANLILIK)

        async def sayfa_isi(u: str):
            async with kilit:
                durum, sure, html = await _cek(istemci, u)
            if durum == 0:
                return SayfaRaporu(
                    url=u, durum=0, sure_ms=sure, boyut=0,
                    bulgular=[Bulgu(kod="ulasilamadi", seviye="hata")],
                ), []
            return _sayfayi_incele(u, durum, sure, html)

        sonuclar = await asyncio.gather(*[sayfa_isi(u) for u in benzersiz])
        sayfalar = [s for s, _ in sonuclar]

        # 3) Bağlantılar — sayfalarda geçen benzersiz iç adresler
        nerede: Dict[str, List[str]] = {}
        taranmis = {s.url.rstrip("/") for s in sayfalar}
        for (sayfa, baglar) in sonuclar:
            for b in baglar:
                if b in taranmis:
                    continue
                nerede.setdefault(b, [])
                if sayfa.url not in nerede[b]:
                    nerede[b].append(sayfa.url)

        hedefler = list(nerede.keys())
        if len(hedefler) > BAGLANTI_TAVANI:
            notlar.append(
                Not(kod="baglanti_tavani", deger=len(hedefler), tavan=BAGLANTI_TAVANI)
            )
            hedefler = hedefler[:BAGLANTI_TAVANI]

        async def baglanti_isi(u: str):
            async with kilit:
                return u, await _durum(istemci, u)

        durumlar = await asyncio.gather(*[baglanti_isi(u) for u in hedefler])

    kiriklar = [
        KirikBaglanti(url=u, durum=d, kaynaklar=nerede.get(u, [])[:5])
        for u, d in durumlar
        if d == 0 or d >= 400
    ]

    ozet = {"hata": 0, "uyari": 0, "bilgi": 0}
    for s in sayfalar:
        for b in s.bulgular:
            ozet[b.seviye] = ozet.get(b.seviye, 0) + 1
    ozet["hata"] += len(kiriklar)

    # Bulgusu olan sayfalar üstte dursun.
    sayfalar.sort(key=lambda s: (len(s.bulgular) == 0, s.url))

    return TaramaRaporu(
        site=SITE_ADRESI,
        sayfa_sayisi=len(sayfalar),
        baglanti_sayisi=len(hedefler),
        sure_ms=int((time.perf_counter() - basla) * 1000),
        ozet=ozet,
        sayfalar=sayfalar,
        kirik_baglantilar=kiriklar,
        notlar=notlar,
    )
