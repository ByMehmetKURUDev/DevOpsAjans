"""Ücretsiz site analizi motoru.

Ziyaretçinin verdiği bir siteyi dışarıdan inceleyip altı bölümde puanlıyor:
hız, SEO, içerik, teknik, güvenlik ve yapay zekâ görünürlüğü. Router
(`routers/site_analizi.py`) yalnızca kayıt, sınır ve yetkiyle uğraşıyor;
ağa çıkan her şey burada.

Güvenlik: bu uç SSRF yüzeyi
---------------------------
Herkese açık bir form, sunucumuza "şu adrese git" dedirtiyor. Kontrol
edilmezse biri `http://169.254.169.254/` (bulut meta veri servisi) ya da
`http://10.0.0.5/admin` yazıp sunucunun iç ağına bizim adımıza istek
attırabilir. Bu yüzden:

* yalnız http/https, port 80/443 ya da hiç; kullanıcı:parola@ yok,
* `localhost`, `.local`, `.internal` gibi adlar hiç çözülmeden reddediliyor,
* ad çözümlenip dönen TÜM IP'ler genel (global) olmalı; biri bile özel,
  döngü, link-local, ayrılmış, çok noktaya yayın ya da belirsiz çıkarsa ret,
* yönlendirmeler otomatik izlenmiyor: her adım (en çok 5) aynı kontrolden
  geçiyor — genel bir site 302 ile iç adrese yollayamasın,
* doğrudan bağlantıda (vekil yoksa) bağlantı anında adres BİR DAHA
  çözülüp denetleniyor ve soket o denetlenmiş IP'ye açılıyor. Kontrolle
  bağlantı arasında DNS kaydını değiştirme (DNS rebinding) böylece işe
  yaramıyor.

Gövde 1.5 MB'ta kesiliyor, her istek 15 sn, bütün analiz ~45 sn ile
sınırlı. Ücretsiz katmandaki sunucu tek bir ziyaretçi yüzünden kilitlenmesin.

Testlerde ağa çıkılmıyor: `_tasiyici_fabrikasi`, `_dns_cozumle`,
`_ssl_bitis` ve `_pagespeed_cagir` yerine sahteleri konuyor.
"""

import asyncio
import ipaddress
import logging
import os
import socket
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from services import site_inceleme as si

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Tavanlar
# --------------------------------------------------------------------------
ISTEK_ZAMAN_ASIMI = 15.0        # tek istek (bağlantı + okuma), saniye
TOPLAM_TAVAN = 45.0             # bütün analiz, saniye
GOVDE_TAVANI = 1_500_000        # 1.5 MB'tan fazlasını okumuyoruz
EN_COK_YONLENDIRME = 5
SAYFA_TAVANI = 20               # ana sayfa dahil
BAGLANTI_TAVANI = 60            # durumu denetlenecek en çok iç bağlantı
ESZAMANLILIK = 4
SSL_ZAMAN_ASIMI = 8.0
PAGESPEED_ZAMAN_ASIMI = 40.0
PAGESPEED_ADRESI = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

AJAN = "MehmetKuruDevSiteAnalizi/1.0 (+https://mehmetkuru.dev/site-analizi)"

YASAK_ADLAR = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
YASAK_SONEKLER = (".localhost", ".local", ".internal", ".home.arpa")

#: robots.txt'de engellenip engellenmediğine bakılan yapay zekâ tarayıcıları.
AI_BOTLARI = ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended")

BASLIK_ALT, BASLIK_UST = 30, 60
ACIKLAMA_ALT, ACIKLAMA_UST = 70, 160
KELIME_ALT = 300

SEVIYE_SIRASI = {"hata": 0, "uyari": 1, "bilgi": 2, "iyi": 3}
BOLUMLER = ("hiz", "seo", "icerik", "teknik", "guvenlik", "ai")


class AnalizHatasi(Exception):
    """Analizin hiç yapılamadığı durumlar; `kod` ön yüzde çevriliyor.

    adres_gecersiz  adres biçimi / şema / port / kullanıcı bilgisi
    adres_yasak     iç ağ, döngü, yasak ad ya da oraya yönlendirme
    cozumlenemedi   alan adı çözülemedi
    ulasilamadi     bağlantı kurulamadı / zaman aşımı
    cok_yonlendirme 5'ten fazla yönlendirme
    """

    def __init__(self, kod: str):
        super().__init__(kod)
        self.kod = kod


# --------------------------------------------------------------------------
# Adres denetimi
# --------------------------------------------------------------------------
def _ip_mi(host: str) -> Optional[ipaddress._BaseAddress]:
    try:
        return ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return None


def ip_global_mi(ip_metni: str) -> bool:
    """IP genel internette mi? Özel/döngü/link-local/ayrılmış… hepsi hayır."""
    ip = _ip_mi(ip_metni)
    if ip is None:
        return False
    # ::ffff:10.0.0.1 gibi IPv4 eşlemeli ya da 6to4 adresin içindeki IPv4'e
    # bakılıyor; yoksa iç adres IPv6 kılığında geçerdi.
    if isinstance(ip, ipaddress.IPv6Address):
        ic = ip.ipv4_mapped or ip.sixtofour
        if ic is not None and not ip_global_mi(str(ic)):
            return False
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return False
    return bool(ip.is_global)


# --------------------------------------------------------------------------
# Yalnız test / yerel geliştirme: iç adrese izin
# --------------------------------------------------------------------------
#: Bu ortam değerlerinden biri tanımlı değilse "üretim" sayılıyor. Varsayılan
#: (ENVIRONMENT yok) üretim — unutulan bir ayar kapıyı açmasın.
URETIM_DISI_ORTAMLAR = frozenset({"dev", "test", "yerel", "local"})


def uretim_mi() -> bool:
    """Üretimde miyiz? Şüphede EVET.

    `ENVIRONMENT` dev/test/yerel değilse ya da Render'ın her serviste
    tanımladığı `RENDER` değişkeni varsa üretim. İkinci koşul, birinin
    Render paneline yanlışlıkla `ENVIRONMENT=dev` yazması hâlinde de
    iç ağ kapısının kapalı kalması için.
    """
    if (os.environ.get("RENDER") or "").strip():
        return True
    return (os.environ.get("ENVIRONMENT") or "prod").strip().lower() not in URETIM_DISI_ORTAMLAR


def test_izinli_hostlar() -> frozenset:
    """`SSRF_TEST_IZINLI_HOSTLAR` (virgüllü) — YALNIZ üretim dışında.

    Uçtan uca testte yerel bir HTTP sunucusunu (127.0.0.1:<port>) uptime
    hedefi yapabilmek için. Üretimde değişken tanımlı olsa bile boş küme
    dönüyor (bkz. `uretim_mi`); bu davranış testle bağlı.
    """
    if uretim_mi():
        return frozenset()
    ham = os.environ.get("SSRF_TEST_IZINLI_HOSTLAR") or ""
    return frozenset(p.strip().lower().strip("[]") for p in ham.split(",") if p.strip())


def _parcala(url: str) -> Tuple[str, str, Optional[int]]:
    """(şema, host, port). Biçim hatasında AnalizHatasi('adres_gecersiz')."""
    try:
        parca = urlsplit(url)
        port = parca.port
    except ValueError as exc:
        raise AnalizHatasi("adres_gecersiz") from exc
    sema = (parca.scheme or "").lower()
    if sema not in ("http", "https"):
        raise AnalizHatasi("adres_gecersiz")
    if parca.username is not None or parca.password is not None or "@" in parca.netloc:
        raise AnalizHatasi("adres_gecersiz")
    host = (parca.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise AnalizHatasi("adres_gecersiz")
    if port not in (None, 80, 443) and host not in test_izinli_hostlar():
        raise AnalizHatasi("adres_gecersiz")
    return sema, host, port


def adresi_normalize(ham: str) -> Tuple[str, str, str]:
    """Kullanıcının yazdığını (url, host, alan_adi) üçlüsüne çevirir.

    "ornek.com" → "https://ornek.com/". Alan adı küçük harf, başındaki
    "www." atılmış hâli: sınırlar bununla sayılıyor, "www.x.com" ile
    "x.com" aynı site.
    """
    ham = (ham or "").strip()
    if not ham or len(ham) > 2000 or any(c.isspace() for c in ham):
        raise AnalizHatasi("adres_gecersiz")
    if "://" not in ham:
        ham = "https://" + ham
    sema, host, port = _parcala(ham)

    if _ip_mi(host) is None:
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise AnalizHatasi("adres_gecersiz") from exc
        if "." not in host and host not in YASAK_ADLAR:
            raise AnalizHatasi("adres_gecersiz")
        netloc = host
    else:
        netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc = f"{netloc}:{port}"

    parca = urlsplit(ham)
    yol = parca.path or "/"
    url = urlunsplit((sema, netloc, yol, parca.query, ""))
    alan = host[4:] if host.startswith("www.") else host
    return url, host, alan


async def _dns_cozumle(host: str, port: int) -> List[str]:
    """Alan adını çözer; testlerde sahtesiyle değiştiriliyor."""
    bilgiler = await asyncio.to_thread(
        socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM
    )
    sonuc: List[str] = []
    for bilgi in bilgiler:
        ip = str(bilgi[4][0]).split("%", 1)[0]
        if ip not in sonuc:
            sonuc.append(ip)
    return sonuc


def _yasak_ad_mi(host: str) -> bool:
    return host in YASAK_ADLAR or host.endswith(YASAK_SONEKLER)


async def _guvenli_ipler(host: str, port: int) -> List[str]:
    """Host'un çözüldüğü IP'ler; biri bile genel değilse AnalizHatasi."""
    if host in test_izinli_hostlar():
        # Yalnız üretim dışı + açıkça listelenmiş ad/IP (bkz. yukarı).
        return [host] if _ip_mi(host) is not None else await _dns_cozumle(host, port)
    if _yasak_ad_mi(host):
        raise AnalizHatasi("adres_yasak")
    if _ip_mi(host) is not None:
        if not ip_global_mi(host):
            raise AnalizHatasi("adres_yasak")
        return [host]
    try:
        ipler = await _dns_cozumle(host, port)
    except (OSError, UnicodeError) as exc:
        raise AnalizHatasi("cozumlenemedi") from exc
    if not ipler:
        raise AnalizHatasi("cozumlenemedi")
    if not all(ip_global_mi(ip) for ip in ipler):
        raise AnalizHatasi("adres_yasak")
    # IPv4 önce: IPv6 çıkışı olmayan sunucularda bağlantı boşa beklemesin.
    return sorted(ipler, key=lambda ip: ":" in ip)


async def adres_dogrula(url: str, onbellek: Optional[Dict[str, bool]] = None) -> None:
    """Adres gidilebilir mi? Değilse AnalizHatasi.

    `onbellek` aynı analiz içinde aynı host'u tekrar tekrar çözmemek için.
    Doğrudan bağlantıda bağlantı anında ayrıca denetim var (aşağıda).
    """
    sema, host, port = _parcala(url)
    if onbellek is not None and onbellek.get(host):
        return
    await _guvenli_ipler(host, port or (443 if sema == "https" else 80))
    if onbellek is not None:
        onbellek[host] = True


# --------------------------------------------------------------------------
# Bağlantı anında denetim (DNS rebinding'e karşı)
# --------------------------------------------------------------------------
try:
    import httpcore

    class _GuvenliAgArkaUcu(httpcore.AsyncNetworkBackend):
        """Soketi, o an çözülüp denetlenen IP'ye açan ağ katmanı.

        TLS el sıkışması yine asıl alan adıyla (SNI + sertifika) yapılıyor:
        httpcore sunucu adını istekteki adresten alıyor, buradaki IP'den
        değil.
        """

        def __init__(self) -> None:
            self._asil = httpcore.AnyIOBackend()

        async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            try:
                ipler = await _guvenli_ipler(str(host).lower().rstrip("."), int(port))
            except AnalizHatasi as exc:
                raise httpcore.ConnectError(f"adres reddedildi: {exc.kod}") from exc
            son_hata: Optional[Exception] = None
            for ip in ipler:
                try:
                    return await self._asil.connect_tcp(
                        ip, port, timeout=timeout,
                        local_address=local_address, socket_options=socket_options,
                    )
                except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                    son_hata = exc
            raise son_hata or httpcore.ConnectError("bağlanılamadı")

        async def connect_unix_socket(self, path, timeout=None, socket_options=None):
            raise httpcore.ConnectError("unix soketi kapalı")

        async def sleep(self, seconds: float) -> None:
            await self._asil.sleep(seconds)

except Exception:  # pragma: no cover - httpcore her zaman httpx ile gelir
    _GuvenliAgArkaUcu = None  # type: ignore[assignment]


def _vekil_var_mi() -> bool:
    return any(
        os.environ.get(ad)
        for ad in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")
    )


def _varsayilan_tasiyici() -> Optional[httpx.AsyncBaseTransport]:
    """Doğrudan bağlantıda bağlantı anında denetleyen taşıyıcı.

    Ortamda vekil tanımlıysa (yerel geliştirme kabuğu gibi) None: httpx
    vekili kullanır, adı vekil çözer. O durumda da her adımın ön
    denetimi (`adres_dogrula`) yapılıyor.
    """
    if _vekil_var_mi() or _GuvenliAgArkaUcu is None:
        return None
    tasiyici = httpx.AsyncHTTPTransport(retries=0)
    try:
        tasiyici._pool._network_backend = _GuvenliAgArkaUcu()  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - httpcore iç yapısı değişirse
        logger.warning("Güvenli ağ katmanı takılamadı: %s", exc)
    return tasiyici


#: Testler sahte taşıyıcıyı (httpx.MockTransport) buradan veriyor.
_tasiyici_fabrikasi: Callable[[], Optional[httpx.AsyncBaseTransport]] = _varsayilan_tasiyici


def _istemci(
    zaman_asimi: float = ISTEK_ZAMAN_ASIMI,
    eszamanlilik: int = ESZAMANLILIK,
    ajan: str = AJAN,
) -> httpx.AsyncClient:
    """SSRF korumalı istemci. Uptime ve RDAP da bunu kullanıyor."""
    decoders = list(getattr(httpx, "_decoders").SUPPORTED_DECODERS)
    kodlamalar = ", ".join(k for k in decoders if k != "identity")
    return httpx.AsyncClient(
        timeout=httpx.Timeout(zaman_asimi),
        follow_redirects=False,
        transport=_tasiyici_fabrikasi(),
        headers={
            "user-agent": ajan,
            # Yalnız çözebildiğimiz sıkıştırmaları istiyoruz; br kurulu
            # değilken br isteyip gövdeyi okuyamamak olmasın.
            "accept-encoding": kodlamalar,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        limits=httpx.Limits(max_connections=eszamanlilik * 2, max_keepalive_connections=eszamanlilik),
    )


# --------------------------------------------------------------------------
# İstek
# --------------------------------------------------------------------------
@dataclass
class Yanit:
    url: str
    durum: int = 0                    # 0: ulaşılamadı / reddedildi
    basliklar: Dict[str, str] = field(default_factory=dict)
    govde: str = ""
    sure_ms: int = 0
    zincir: List[Dict[str, Any]] = field(default_factory=list)
    hata: Optional[str] = None
    konum: Optional[str] = None       # yönlendirme izlenmediyse Location
    #: Faz 4S — `ham_oku=True` ile istendiyse gövdenin ham baytları (görsel, .gz site haritası).
    ham: bytes = b""
    #: Faz 4S — gövde `govde_tavani`nda kesildi (dosyanın tamamı okunmadı).
    kesildi: bool = False


_METIN_TURLERI = ("text/", "xml", "json", "javascript")


class Gezgin:
    """Tek analiz boyunca kullanılan, her adımı denetleyen istek yapıcı.

    Faz 4S (ücretsiz SEO araçları) aynı istemciyi kullanıyor; eklenenler
    geriye uyumlu, varsayılanlar eski davranış:

    * `gunlukle=False` — başarısız istekte adres günlüğe YAZILMAZ (araçlarda
      sorgulanan adres hiçbir yerde kalıcı tutulmuyor; yalnız hata türü).
    * `govde_tavani` — gövde okuma tavanı (varsayılan GOVDE_TAVANI).
    * `getir(..., ham_oku=True)` — içerik türüne bakmadan ham bayt (görsel boyutu,
      sıkıştırılmış site haritası); `Yanit.ham`, `Yanit.kesildi`.
    * `getir(..., dongu_algila=True)` — aynı adrese ikinci kez yönlendirilince
      durur, `hata="dongu"` (varsayılan: 5 adımda `cok_yonlendirme`).
    """

    def __init__(
        self,
        istemci: httpx.AsyncClient,
        eszamanlilik: int = ESZAMANLILIK,
        zaman_asimi: float = ISTEK_ZAMAN_ASIMI,
        gunlukle: bool = True,
        govde_tavani: int = GOVDE_TAVANI,
    ):
        self.istemci = istemci
        self.onbellek: Dict[str, bool] = {}
        self.kilit = asyncio.Semaphore(eszamanlilik)
        self.zaman_asimi = zaman_asimi
        self.gunlukle = gunlukle
        self.govde_tavani = govde_tavani

    async def _oku(self, yanit: httpx.Response, ham_oku: bool = False) -> Tuple[str, bytes, bool]:
        """(metin, ham, kesildi). Metin olmayan türde metin boş; `ham_oku` ise baytlar yine okunur."""
        tur = (yanit.headers.get("content-type") or "").lower()
        metin_mi = not tur or any(p in tur for p in _METIN_TURLERI)
        if not metin_mi and not ham_oku:
            return "", b"", False
        parcalar: List[bytes] = []
        boyut = 0
        kesildi = False
        async for parca in yanit.aiter_bytes():
            parcalar.append(parca)
            boyut += len(parca)
            if boyut > self.govde_tavani:
                kesildi = True
                break
        ham = b"".join(parcalar)[: self.govde_tavani]
        metin = ham.decode(yanit.encoding or "utf-8", errors="replace") if metin_mi else ""
        return metin, (ham if ham_oku else b""), kesildi

    async def _tek_adim(self, yontem: str, url: str, govde_oku: bool, izle: bool, ham_oku: bool = False):
        istek = self.istemci.build_request(yontem, url)
        yanit = await self.istemci.send(istek, stream=True)
        try:
            konum = yanit.headers.get("location")
            yonlendirme = yanit.status_code in (301, 302, 303, 307, 308) and bool(konum)
            govde, ham, kesildi = "", b"", False
            if govde_oku and yontem != "HEAD" and not (izle and yonlendirme):
                govde, ham, kesildi = await self._oku(yanit, ham_oku)
            basliklar = {k.lower(): v for k, v in yanit.headers.items()}
            return yanit.status_code, basliklar, govde, (konum if yonlendirme else None), ham, kesildi
        finally:
            await yanit.aclose()

    async def getir(
        self,
        url: str,
        yontem: str = "GET",
        govde_oku: bool = True,
        izle: bool = True,
        ham_oku: bool = False,
        dongu_algila: bool = False,
    ) -> Yanit:
        basla = time.perf_counter()
        zincir: List[Dict[str, Any]] = []
        simdiki = url
        gorulen = set()
        for _adim in range(EN_COK_YONLENDIRME + 1):
            if dongu_algila:
                if simdiki in gorulen:
                    return Yanit(url=simdiki, zincir=zincir, hata="dongu",
                                 sure_ms=int((time.perf_counter() - basla) * 1000))
                gorulen.add(simdiki)
            try:
                await adres_dogrula(simdiki, self.onbellek)
            except AnalizHatasi as exc:
                return Yanit(url=simdiki, zincir=zincir, hata=exc.kod,
                             sure_ms=int((time.perf_counter() - basla) * 1000))
            try:
                async with self.kilit:
                    durum, basliklar, govde, konum, ham, kesildi = await asyncio.wait_for(
                        self._tek_adim(yontem, simdiki, govde_oku, izle, ham_oku),
                        self.zaman_asimi + 1,
                    )
            except (httpx.HTTPError, asyncio.TimeoutError, OSError, ssl.SSLError) as exc:
                if self.gunlukle:
                    logger.info("Analiz isteği başarısız: %s (%s)", simdiki, type(exc).__name__)
                else:
                    logger.info("Araç isteği başarısız (%s)", type(exc).__name__)
                return Yanit(url=simdiki, zincir=zincir, hata="ulasilamadi",
                             sure_ms=int((time.perf_counter() - basla) * 1000))
            zincir.append({"url": simdiki, "durum": durum})
            if konum and izle:
                simdiki = urljoin(simdiki, konum).split("#", 1)[0]
                continue
            return Yanit(
                url=simdiki, durum=durum, basliklar=basliklar, govde=govde,
                sure_ms=int((time.perf_counter() - basla) * 1000),
                zincir=zincir, konum=konum, ham=ham, kesildi=kesildi,
            )
        if dongu_algila and simdiki in gorulen:
            return Yanit(url=simdiki, zincir=zincir, hata="dongu",
                         sure_ms=int((time.perf_counter() - basla) * 1000))
        return Yanit(url=simdiki, zincir=zincir, hata="cok_yonlendirme",
                     sure_ms=int((time.perf_counter() - basla) * 1000))


# --------------------------------------------------------------------------
# Dış ölçümler (testlerde sahteleri konuyor)
# --------------------------------------------------------------------------
#: Uçtan uca test için sabit PageSpeed sonucu: strateji → (puan 0-1, LCP ms, CLS, TBT ms).
#: Yerel hedef site (127.0.0.1) Google'dan ölçülemiyor; tarayıcı testi puanları
#: ve Core Web Vitals renklerini bununla görüyor.
SAHTE_PAGESPEED: Dict[str, Tuple[float, float, float, float]] = {
    "mobile": (0.74, 2900.0, 0.08, 240.0),
    "desktop": (0.95, 1100.0, 0.02, 40.0),
}


def sahte_pagespeed_acik_mi() -> bool:
    """Sabit sahte PageSpeed yanıtı YALNIZ `ENVIRONMENT=test` iken.

    Üretimde ASLA: `uretim_mi()` evet diyorsa (Render'ın `RENDER` değişkeni
    var ya da ENVIRONMENT tanımsız/dev-test-yerel dışı) kapalı. "dev" ya da
    "yerel" de açmıyor — gerçek ölçüm isteyen geliştirme ortamı etkilenmesin.
    Bu davranış testle bağlı (`test_seo_izleme.py`).
    """
    if uretim_mi():
        return False
    return (os.environ.get("ENVIRONMENT") or "").strip().lower() == "test"


def _sahte_pagespeed(strateji: str) -> Dict[str, Any]:
    puan, lcp, cls, tbt = SAHTE_PAGESPEED.get(strateji, SAHTE_PAGESPEED["mobile"])
    return {
        "lighthouseResult": {
            "categories": {"performance": {"score": puan}},
            "audits": {
                "largest-contentful-paint": {"numericValue": lcp},
                "cumulative-layout-shift": {"numericValue": cls},
                "total-blocking-time": {"numericValue": tbt},
            },
        }
    }


async def _pagespeed_cagir(url: str, strateji: str) -> Dict[str, Any]:
    """PageSpeed Insights v5 ham yanıtı. Anahtar yoksa anahtarsız (düşük kota)."""
    if sahte_pagespeed_acik_mi():
        return _sahte_pagespeed(strateji)
    parametreler = {"url": url, "strategy": strateji, "category": "performance"}
    anahtar = (os.environ.get("PAGESPEED_API_KEY") or "").strip()
    if anahtar:
        parametreler["key"] = anahtar
    async with httpx.AsyncClient(timeout=PAGESPEED_ZAMAN_ASIMI) as istemci:
        yanit = await istemci.get(PAGESPEED_ADRESI, params=parametreler)
    yanit.raise_for_status()
    return yanit.json()


async def pagespeed_olc(url: str, strateji: str) -> Optional[Dict[str, Any]]:
    """Puan + LCP/CLS/TBT; API başarısızsa ya da kota dolmuşsa None."""
    try:
        veri = await asyncio.wait_for(_pagespeed_cagir(url, strateji), PAGESPEED_ZAMAN_ASIMI)
        lh = veri.get("lighthouseResult") or {}
        skor = (((lh.get("categories") or {}).get("performance") or {}).get("score"))
        if skor is None:
            return None
        denetim = lh.get("audits") or {}

        def sayi(ad: str) -> Optional[float]:
            deger = (denetim.get(ad) or {}).get("numericValue")
            return float(deger) if isinstance(deger, (int, float)) else None

        return {
            "puan": int(round(float(skor) * 100)),
            "lcp_ms": sayi("largest-contentful-paint"),
            "cls": sayi("cumulative-layout-shift"),
            "tbt_ms": sayi("total-blocking-time"),
        }
    except Exception as exc:
        logger.info("PageSpeed ölçülemedi (%s): %s", strateji, type(exc).__name__)
        return None


def _ssl_bitis_esz(host: str, ip: str) -> Tuple[Optional[datetime], Optional[str]]:
    baglam = ssl.create_default_context()
    try:
        with socket.create_connection((ip, 443), timeout=SSL_ZAMAN_ASIMI) as soket:
            with baglam.wrap_socket(soket, server_hostname=host) as tls:
                sertifika = tls.getpeercert() or {}
    except ssl.SSLCertVerificationError:
        return None, "gecersiz"
    except (OSError, ssl.SSLError, ValueError):
        return None, "olculemedi"
    son = sertifika.get("notAfter")
    if not son:
        return None, "olculemedi"
    return datetime.fromtimestamp(ssl.cert_time_to_seconds(son), timezone.utc), None


async def _ssl_bitis(host: str) -> Tuple[Optional[datetime], Optional[str]]:
    """Sertifikanın bitiş tarihi; (None, 'gecersiz'|'olculemedi') olabilir."""
    try:
        ipler = await _guvenli_ipler(host, 443)
    except AnalizHatasi:
        return None, "olculemedi"
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_ssl_bitis_esz, host, ipler[0]), SSL_ZAMAN_ASIMI + 2
        )
    except Exception:
        return None, "olculemedi"


# --------------------------------------------------------------------------
# Faz 4S — sertifika ayrıntısı (ücretsiz SSL aracı)
# --------------------------------------------------------------------------
def _ad_ozeti(ad: Any) -> Dict[str, str]:
    """`cryptography` Name → {"cn","o"} (yalnız okunur metin)."""
    sonuc: Dict[str, str] = {}
    try:
        from cryptography.x509.oid import NameOID

        for anahtar, oid in (("cn", NameOID.COMMON_NAME), ("o", NameOID.ORGANIZATION_NAME)):
            degerler = ad.get_attributes_for_oid(oid)
            if degerler:
                sonuc[anahtar] = str(degerler[0].value)[:200]
    except Exception:  # noqa: BLE001
        pass
    return sonuc


def sertifika_coz(der: bytes) -> Dict[str, Any]:
    """DER sertifikadan gösterilecek alanlar (konu, yayıncı, tarihler, SAN, anahtar, AIA)."""
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec, rsa

    s = x509.load_der_x509_certificate(der)
    try:
        bas, son = s.not_valid_before_utc, s.not_valid_after_utc
    except AttributeError:  # pragma: no cover - eski cryptography
        bas = s.not_valid_before.replace(tzinfo=timezone.utc)
        son = s.not_valid_after.replace(tzinfo=timezone.utc)
    san: List[str] = []
    try:
        uzanti = s.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        san = [str(a) for a in uzanti.value.get_values_for_type(x509.DNSName)][:50]
    except Exception:  # noqa: BLE001
        pass
    aia: Optional[str] = None
    try:
        from cryptography.x509.oid import AuthorityInformationAccessOID

        uzanti = s.extensions.get_extension_for_class(x509.AuthorityInformationAccess)
        for erisim in uzanti.value:
            if erisim.access_method == AuthorityInformationAccessOID.CA_ISSUERS:
                aia = str(erisim.access_location.value)[:300]
                break
    except Exception:  # noqa: BLE001
        pass
    anahtar = s.public_key()
    if isinstance(anahtar, rsa.RSAPublicKey):
        anahtar_turu = f"RSA {anahtar.key_size}"
    elif isinstance(anahtar, ec.EllipticCurvePublicKey):
        anahtar_turu = f"EC {anahtar.curve.name}"
    else:
        anahtar_turu = type(anahtar).__name__.replace("PublicKey", "")
    try:
        imza = s.signature_hash_algorithm.name if s.signature_hash_algorithm else "-"
    except Exception:  # noqa: BLE001
        imza = "-"
    return {
        "konu": _ad_ozeti(s.subject),
        "yayinci": _ad_ozeti(s.issuer),
        "baslangic": bas.isoformat(),
        "bitis": son.isoformat(),
        "san": san,
        "seri": format(s.serial_number, "X")[:64],
        "imza": imza,
        "anahtar": anahtar_turu,
        "aia": aia,
        "kendinden_imzali": s.subject == s.issuer,
    }


def _ssl_bilgisi_esz(host: str, ip: str, port: int = 443) -> Dict[str, Any]:
    """Sertifika + bağlantı ayrıntısı (eşzamanlı; iş parçacığında çalışır).

    Önce doğrulamalı bağlanılıyor: başarılıysa zincir güvenilir köke ulaşıyor ve
    ad eşleşiyor. Doğrulama düşerse hata nedeni (OpenSSL doğrulama kodu) alınıp
    sertifikayı yine gösterebilmek için doğrulamasız ikinci bir bağlantı açılıyor
    (yalnız sertifikayı okumak için — başka veri gönderilmiyor).
    """
    sonuc: Dict[str, Any] = {"dogrulandi": False, "hata": None, "hata_kodu": None}

    def _baglan(dogrula: bool):
        baglam = ssl.create_default_context()
        if not dogrula:
            baglam.check_hostname = False
            baglam.verify_mode = ssl.CERT_NONE
        soket = socket.create_connection((ip, port), timeout=SSL_ZAMAN_ASIMI)
        try:
            return baglam.wrap_socket(soket, server_hostname=host)
        except Exception:
            soket.close()
            raise

    tls = None
    try:
        tls = _baglan(True)
        sonuc["dogrulandi"] = True
    except ssl.SSLCertVerificationError as exc:
        sonuc["hata"] = (getattr(exc, "verify_message", "") or str(exc))[:200]
        sonuc["hata_kodu"] = getattr(exc, "verify_code", None)
    except (OSError, ssl.SSLError, ValueError) as exc:
        sonuc["hata"] = "baglanti"
        sonuc["baglanti_hatasi"] = type(exc).__name__
        return sonuc
    try:
        if tls is None:
            tls = _baglan(False)
        sonuc["tls_surumu"] = tls.version()
        sifre = tls.cipher()
        sonuc["sifre"] = sifre[0] if sifre else None
        der = tls.getpeercert(binary_form=True)
        zincir_der: List[bytes] = []
        # Python 3.13+: doğrulanmış zincirin tamamı; daha eskisinde yalnız yaprak + AIA.
        for ad in ("get_verified_chain", "get_unverified_chain"):
            fonk = getattr(tls, ad, None) or getattr(getattr(tls, "_sslobj", None), ad, None)
            if fonk is None:
                continue
            try:
                parcalar = fonk() or []
                zincir_der = [p if isinstance(p, bytes) else p.public_bytes(ssl._ssl.ENCODING_DER) for p in parcalar]  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                zincir_der = []
            if zincir_der:
                break
    except (OSError, ssl.SSLError, ValueError) as exc:
        sonuc["hata"] = sonuc["hata"] or "baglanti"
        sonuc["baglanti_hatasi"] = type(exc).__name__
        return sonuc
    finally:
        if tls is not None:
            try:
                tls.close()
            except OSError:
                pass
    if der:
        try:
            sonuc["sertifika"] = sertifika_coz(der)
        except Exception:  # noqa: BLE001
            sonuc["sertifika"] = None
    zincir: List[Dict[str, Any]] = []
    for parca in zincir_der[:6]:
        try:
            c = sertifika_coz(parca)
            zincir.append({"konu": c["konu"], "yayinci": c["yayinci"], "bitis": c["bitis"]})
        except Exception:  # noqa: BLE001
            continue
    sonuc["zincir"] = zincir
    return sonuc


async def ssl_bilgisi(host: str) -> Dict[str, Any]:
    """Sertifika ayrıntısı. Adres SSRF denetiminden geçmezse AnalizHatasi."""
    ipler = await _guvenli_ipler(host, 443)
    try:
        return await asyncio.wait_for(asyncio.to_thread(_ssl_bilgisi_esz, host, ipler[0]), SSL_ZAMAN_ASIMI * 2 + 2)
    except asyncio.TimeoutError:
        return {"dogrulandi": False, "hata": "baglanti", "baglanti_hatasi": "TimeoutError"}


# --------------------------------------------------------------------------
# Puanlama
# --------------------------------------------------------------------------
class Bolum:
    def __init__(self, anahtar: str):
        self.anahtar = anahtar
        self.bulgular: List[Dict[str, Any]] = []
        self.ceza = 0
        self.olculemedi = False
        self.sabit_puan: Optional[int] = None

    def ekle(self, kod: str, seviye: str, ceza: int = 0, deger: Any = None) -> None:
        bulgu: Dict[str, Any] = {"kod": kod, "seviye": seviye}
        if deger is not None:
            bulgu["deger"] = deger
        self.bulgular.append(bulgu)
        self.ceza += max(0, ceza)

    def sonuc(self) -> Dict[str, Any]:
        sirali = sorted(self.bulgular, key=lambda b: SEVIYE_SIRASI.get(b["seviye"], 9))
        if self.olculemedi:
            return {"anahtar": self.anahtar, "puan": None, "durum": "olculemedi", "bulgular": sirali}
        puan = self.sabit_puan if self.sabit_puan is not None else 100 - self.ceza
        return {
            "anahtar": self.anahtar,
            "puan": max(0, min(100, int(puan))),
            "durum": "tamam",
            "bulgular": sirali,
        }


def _seviye(deger: float, iyi: float, orta: float) -> str:
    if deger <= iyi:
        return "iyi"
    if deger <= orta:
        return "uyari"
    return "hata"


def _hiz_bolumu(mobil: Optional[Dict[str, Any]], masaustu: Optional[Dict[str, Any]]) -> Bolum:
    b = Bolum("hiz")
    puanlar = []
    for kod, olcum in (("hiz_mobil", mobil), ("hiz_masaustu", masaustu)):
        if olcum:
            p = olcum["puan"]
            puanlar.append(p)
            b.ekle(kod, "iyi" if p >= 90 else ("uyari" if p >= 50 else "hata"), deger=p)
    if not puanlar:
        b.olculemedi = True
        b.ekle("hiz_olculemedi", "bilgi")
        return b
    kaynak = mobil or masaustu or {}
    if kaynak.get("lcp_ms") is not None:
        b.ekle("lcp", _seviye(kaynak["lcp_ms"], 2500, 4000), deger=int(round(kaynak["lcp_ms"])))
    if kaynak.get("cls") is not None:
        b.ekle("cls", _seviye(kaynak["cls"], 0.1, 0.25), deger=round(kaynak["cls"], 3))
    if kaynak.get("tbt_ms") is not None:
        b.ekle("tbt", _seviye(kaynak["tbt_ms"], 200, 600), deger=int(round(kaynak["tbt_ms"])))
    b.sabit_puan = int(round(sum(puanlar) / len(puanlar)))
    return b


@dataclass
class Sayfa:
    url: str
    durum: int
    sure_ms: int
    html: str
    oz: Optional[si.SayfaOzellikleri] = None


def _seo_bolumu(
    ana: Sayfa, diger: List[Sayfa], robots_var: bool, sitemap_adet: Optional[int], robots_metni: str = ""
) -> Bolum:
    b = Bolum("seo")
    oz = ana.oz or si.SayfaOzellikleri()

    if not oz.baslik:
        b.ekle("title_yok", "hata", 20)
    else:
        g = si.genislik(oz.baslik)
        if g < BASLIK_ALT:
            b.ekle("title_kisa", "uyari", 8, g)
        elif g > BASLIK_UST:
            b.ekle("title_uzun", "uyari", 8, g)
        else:
            b.ekle("title_iyi", "iyi", deger=g)

    if not oz.aciklama:
        b.ekle("aciklama_yok", "hata", 15)
    else:
        g = si.genislik(oz.aciklama)
        if g < ACIKLAMA_ALT:
            b.ekle("aciklama_kisa", "uyari", 6, g)
        elif g > ACIKLAMA_UST:
            b.ekle("aciklama_uzun", "uyari", 6, g)
        else:
            b.ekle("aciklama_iyi", "iyi", deger=g)

    if oz.h1_sayisi == 0:
        b.ekle("h1_yok", "hata", 10)
    elif oz.h1_sayisi > 1:
        b.ekle("h1_fazla", "uyari", 5, oz.h1_sayisi)

    if not oz.canonical_var:
        b.ekle("canonical_yok", "uyari", 8)
    if "noindex" in oz.robots_meta:
        b.ekle("noindex", "hata", 30)
    if not oz.lang_var:
        b.ekle("lang_yok", "uyari", 4)
    if not robots_var:
        b.ekle("robots_txt_yok", "uyari", 8)
    elif robots_metni and si.robots_tumden_engelli_mi(robots_metni, "Googlebot"):
        # Faz 2H: `Disallow: /` sitenin tamamını Google'a kapatıyor (noindex kadar ağır).
        b.ekle("robots_engelli", "hata", 30)
    if sitemap_adet is None:
        b.ekle("sitemap_yok", "uyari", 8)
    else:
        b.ekle("sitemap_var", "iyi", deger=sitemap_adet)
    if not oz.jsonld_var:
        b.ekle("jsonld_yok", "uyari", 6)
    if not oz.hreflang_var:
        b.ekle("hreflang_yok", "bilgi")

    basliksiz = sum(1 for s in diger if s.oz and not s.oz.baslik)
    aciklamasiz = sum(1 for s in diger if s.oz and not s.oz.aciklama)
    if basliksiz:
        b.ekle("sayfa_basliksiz", "uyari", 5, basliksiz)
    if aciklamasiz:
        b.ekle("sayfa_aciklamasiz", "uyari", 5, aciklamasiz)
    return b


def _icerik_bolumu(ana: Sayfa, sayfalar: List[Sayfa], kiriklar: List[Dict[str, Any]], denetlenen: int) -> Bolum:
    b = Bolum("icerik")
    kelime = si.kelime_sayisi(ana.html) if ana.html else 0
    if kelime < KELIME_ALT:
        b.ekle("icerik_az", "uyari", 15, kelime)
    else:
        b.ekle("kelime_sayisi", "iyi", deger=kelime)

    altsiz = sum(s.oz.altsiz_gorsel for s in sayfalar if s.oz)
    if altsiz:
        b.ekle("alt_yok", "uyari", min(30, 3 * altsiz), altsiz)
    else:
        b.ekle("alt_tamam", "iyi")

    if kiriklar:
        b.ekle("kirik_baglanti", "hata", min(50, 10 * len(kiriklar)), len(kiriklar))
    else:
        b.ekle("kirik_baglanti_yok", "iyi", deger=denetlenen)
    return b


def _teknik_bolumu(ana: Yanit, sayfalar: List[Sayfa], http_yonlendiriyor: Optional[bool]) -> Bolum:
    b = Bolum("teknik")
    https = ana.url.lower().startswith("https://")
    if https:
        b.ekle("https_var", "iyi")
        if http_yonlendiriyor is False:
            b.ekle("http_yonlendirme_yok", "uyari", 10)
    else:
        b.ekle("https_yok", "hata", 30)

    adim = max(0, len(ana.zincir) - 1)
    if adim >= 2:
        b.ekle("yonlendirme_uzun", "uyari", 5 * (adim - 1), adim)

    if ana.durum != 200:
        b.ekle("ana_sayfa_durum", "hata", 30, ana.durum)
    hatali = sum(1 for s in sayfalar[1:] if s.durum == 0 or s.durum >= 400)
    if hatali:
        b.ekle("sayfa_hatali", "hata", min(25, 5 * hatali), hatali)

    kodlama = (ana.basliklar.get("content-encoding") or "").lower()
    if not any(k in kodlama for k in ("br", "gzip", "zstd", "deflate")):
        b.ekle("sikistirma_yok", "uyari", 10)
    else:
        b.ekle("sikistirma_var", "iyi", deger=kodlama)

    if not ana.basliklar.get("cache-control"):
        b.ekle("onbellek_yok", "uyari", 5)

    if ana.sure_ms > 3000:
        b.ekle("yavas_yanit", "uyari", 8, ana.sure_ms)
    return b


def _guvenlik_bolumu(ana: Yanit, ssl_bitis: Optional[datetime], ssl_hata: Optional[str]) -> Bolum:
    b = Bolum("guvenlik")
    h = ana.basliklar
    eksik = 0
    if not h.get("strict-transport-security"):
        b.ekle("hsts_yok", "uyari", 15)
        eksik += 1
    csp = (h.get("content-security-policy") or "").lower()
    if not csp:
        if h.get("content-security-policy-report-only"):
            # Yalnız rapor modunda CSP: politika yazılmış ama tarayıcı henüz
            # engellemiyor. Kısmen sayılır — cezanın yarısı, "tamam" değil.
            b.ekle("csp_rapor", "bilgi", 7)
        else:
            b.ekle("csp_yok", "uyari", 15)
        eksik += 1
    if not h.get("x-frame-options") and "frame-ancestors" not in csp:
        b.ekle("frame_koruma_yok", "uyari", 10)
        eksik += 1
    if (h.get("x-content-type-options") or "").lower().strip() != "nosniff":
        b.ekle("nosniff_yok", "uyari", 10)
        eksik += 1
    if not h.get("referrer-policy"):
        b.ekle("referrer_yok", "bilgi", 5)
        eksik += 1
    if not eksik:
        b.ekle("guvenlik_basliklari_tamam", "iyi")

    if ana.url.lower().startswith("https://"):
        if ssl_hata == "gecersiz":
            b.ekle("ssl_gecersiz", "hata", 40)
        elif ssl_bitis is None:
            b.ekle("ssl_olculemedi", "bilgi")
        else:
            kalan = int((ssl_bitis - datetime.now(timezone.utc)).total_seconds() // 86400)
            if kalan < 0:
                # Değer "kaç gün önce doldu": metin "{{deger}} gün önce" diye kuruluyor.
                b.ekle("ssl_suresi_gecmis", "hata", 40, -kalan)
            elif kalan < 14:
                b.ekle("ssl_bitiyor", "hata", 20, kalan)
            elif kalan < 30:
                b.ekle("ssl_yakinda", "uyari", 10, kalan)
            else:
                b.ekle("ssl_gecerli", "iyi", deger=kalan)
    return b


def _ai_bolumu(llms_var: bool, robots_metni: str, jsonld_var: bool) -> Bolum:
    b = Bolum("ai")
    if llms_var:
        b.ekle("llms_txt_var", "iyi")
    else:
        b.ekle("llms_txt_yok", "uyari", 20)

    engelli = [bot for bot in AI_BOTLARI if robots_metni and si.robots_tumden_engelli_mi(robots_metni, bot)]
    if engelli:
        b.ekle("ai_bot_engelli", "uyari", 15 * len(engelli), ", ".join(engelli))
    else:
        b.ekle("ai_botlar_acik", "iyi")

    if jsonld_var:
        b.ekle("yapisal_veri_var", "iyi")
    else:
        b.ekle("yapisal_veri_yok", "uyari", 25)
    return b


def ozetle(bolumler: List[Dict[str, Any]], bulgu_tavani: int = 3) -> List[Dict[str, Any]]:
    """Herkese açık özet: her bölümde en önemli `bulgu_tavani` bulgu."""
    return [
        {
            "anahtar": b["anahtar"],
            "puan": b["puan"],
            "durum": b["durum"],
            "bulgular": list(b["bulgular"])[:bulgu_tavani],
        }
        for b in bolumler
    ]


def genel_puan(bolumler: List[Dict[str, Any]]) -> Optional[int]:
    puanlar = [b["puan"] for b in bolumler if b.get("puan") is not None]
    if not puanlar:
        return None
    return int(round(sum(puanlar) / len(puanlar)))


# --------------------------------------------------------------------------
# Analiz
# --------------------------------------------------------------------------
async def _sinirli(gorevler: Dict[str, Awaitable], son_an: float) -> Dict[str, Any]:
    """Görevleri son ana kadar bekler; bitmeyenler iptal, sonucu None."""
    isler = {ad: asyncio.ensure_future(g) for ad, g in gorevler.items()}
    kalan = max(0.1, son_an - time.monotonic())
    if isler:
        await asyncio.wait(list(isler.values()), timeout=kalan)
    sonuc: Dict[str, Any] = {}
    for ad, is_ in isler.items():
        if is_.done() and not is_.cancelled() and is_.exception() is None:
            sonuc[ad] = is_.result()
        else:
            if not is_.done():
                is_.cancel()
            sonuc[ad] = None
    return sonuc


def _koken(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def _ayni_site(url: str, koken: str) -> bool:
    return url == koken or url.startswith(koken + "/")


async def analiz_et(ham_url: str) -> Dict[str, Any]:
    """Siteyi inceler; {url, alan_adi, puan, bolumler, ayrinti}.

    Site hiç açılamıyorsa AnalizHatasi. Bölüm ölçülemezse (PageSpeed
    kotası gibi) o bölüm "olculemedi" olur ve genel puana girmez.
    """
    url, host, alan = adresi_normalize(ham_url)
    basla = time.monotonic()
    son_an = basla + TOPLAM_TAVAN
    # Hiçbir istek atılmadan önce: adres baştan iç ağa çıkıyorsa dur.
    await adres_dogrula(url)

    notlar: List[str] = []
    async with _istemci() as istemci:
        gezgin = Gezgin(istemci)
        ana = await gezgin.getir(url)
        if ana.hata in ("adres_yasak", "adres_gecersiz"):
            # Genel bir adres iç ağa yönlendirdi: sessizce değil, açıkça reddet.
            raise AnalizHatasi("adres_yasak")
        if ana.durum == 0:
            raise AnalizHatasi(ana.hata or "ulasilamadi")

        koken = _koken(ana.url)
        son_host = urlsplit(ana.url).hostname or host
        https = ana.url.lower().startswith("https://")

        # PageSpeed en uzun süren iş; baştan başlatılıp sonda toplanıyor.
        hiz_isleri = {
            "mobil": asyncio.ensure_future(pagespeed_olc(ana.url, "mobile")),
            "masaustu": asyncio.ensure_future(pagespeed_olc(ana.url, "desktop")),
        }

        async def http_denetimi() -> Optional[bool]:
            if not https:
                return None
            y = await gezgin.getir(f"http://{son_host}/", govde_oku=False, izle=False)
            if y.durum == 0:
                return None
            return bool(y.konum and urljoin(f"http://{son_host}/", y.konum).startswith("https://"))

        async def ssl_denetimi():
            if not https:
                return None, None
            return await _ssl_bitis(son_host)

        yardimci = await _sinirli(
            {
                "robots": gezgin.getir(f"{koken}/robots.txt"),
                "llms": gezgin.getir(f"{koken}/llms.txt"),
                "http": http_denetimi(),
                "ssl": ssl_denetimi(),
            },
            son_an - 25,
        )

        robots: Optional[Yanit] = yardimci.get("robots")
        robots_var = bool(robots and robots.durum == 200 and "html" not in robots.basliklar.get("content-type", ""))
        robots_metni = robots.govde if robots_var and robots else ""

        llms: Optional[Yanit] = yardimci.get("llms")
        llms_var = bool(
            llms and llms.durum == 200 and llms.govde.strip()
            and "html" not in llms.basliklar.get("content-type", "")
        )

        # Sitemap: robots.txt'de adres verilmişse o, yoksa /sitemap.xml.
        sitemap_adresi = f"{koken}/sitemap.xml"
        for satir in robots_metni.splitlines():
            if satir.lower().startswith("sitemap:"):
                aday = satir.split(":", 1)[1].strip()
                if _ayni_site(aday, koken):
                    sitemap_adresi = aday
                    break
        sitemap_adresleri: Optional[List[str]] = None
        sm = (await _sinirli({"sm": gezgin.getir(sitemap_adresi)}, son_an - 22)).get("sm")
        if sm and sm.durum == 200 and "<loc>" in sm.govde.lower():
            adresler = si.sitemap_adresleri(sm.govde)
            if si.sitemap_dizini_mi(sm.govde):
                alt = [a for a in adresler if _ayni_site(a, koken)][:1]
                sm2 = (await _sinirli({"sm": gezgin.getir(alt[0])}, son_an - 20)).get("sm") if alt else None
                adresler = si.sitemap_adresleri(sm2.govde) if sm2 and sm2.durum == 200 else []
            sitemap_adresleri = adresler

        ana_sayfa = Sayfa(url=ana.url, durum=ana.durum, sure_ms=ana.sure_ms, html=ana.govde,
                          oz=si.sayfa_ozellikleri(ana.govde) if ana.govde else None)

        # Taranacak diğer sayfalar: önce sitemap, yoksa ana sayfanın iç bağlantıları.
        adaylar: List[str] = []
        gorulen = {ana.url.rstrip("/"), url.rstrip("/")}
        kaynak_listesi = sitemap_adresleri or []
        if not kaynak_listesi and ana_sayfa.oz:
            kaynak_listesi = [
                n for n in (si.normalize(h, ana.url, koken) for h in ana_sayfa.oz.hrefler) if n
            ]
        for aday in kaynak_listesi:
            aday = aday.strip().split("#", 1)[0]
            if not _ayni_site(aday, koken) or aday.rstrip("/") in gorulen:
                continue
            gorulen.add(aday.rstrip("/"))
            adaylar.append(aday)
            if len(adaylar) >= SAYFA_TAVANI - 1:
                break

        sayfa_sonuclari = await _sinirli(
            {str(i): gezgin.getir(a) for i, a in enumerate(adaylar)}, son_an - 12
        )
        sayfalar: List[Sayfa] = [ana_sayfa]
        for i, a in enumerate(adaylar):
            y: Optional[Yanit] = sayfa_sonuclari.get(str(i))
            if y is None:
                notlar.append("sayfa_zaman_asimi")
                continue
            if y.hata in ("adres_yasak", "adres_gecersiz"):
                continue
            sayfalar.append(Sayfa(url=a, durum=y.durum, sure_ms=y.sure_ms, html=y.govde,
                                  oz=si.sayfa_ozellikleri(y.govde) if y.govde else None))

        # İç bağlantılar: taranan sayfalardaki benzersiz adresler, en çok 60.
        bilinen = {s.url.rstrip("/"): s.durum for s in sayfalar}
        nerede: Dict[str, str] = {}
        for s in sayfalar:
            if not s.oz:
                continue
            for ham in s.oz.hrefler:
                hedef = si.normalize(ham, s.url, koken)
                if hedef and _ayni_site(hedef, koken) and hedef not in nerede:
                    nerede[hedef] = s.url
        hedefler = list(nerede.keys())[:BAGLANTI_TAVANI]
        denetlenecek = [h for h in hedefler if h.rstrip("/") not in bilinen]

        async def baglanti_durumu(adres: str) -> int:
            y = await gezgin.getir(adres, yontem="HEAD", govde_oku=False)
            if y.durum in (405, 501):
                y = await gezgin.getir(adres, govde_oku=False)
            if y.hata in ("adres_yasak", "adres_gecersiz"):
                return -1
            return y.durum

        baglanti_sonuclari = await _sinirli(
            {h: baglanti_durumu(h) for h in denetlenecek}, son_an - 4
        )
        kiriklar: List[Dict[str, Any]] = []
        denetlenen = 0
        for h in hedefler:
            d = bilinen.get(h.rstrip("/"))
            if d is None:
                d = baglanti_sonuclari.get(h)
            if d is None or d < 0:
                continue
            denetlenen += 1
            if d == 0 or d >= 400:
                kiriklar.append({"url": h, "durum": d, "kaynak": nerede.get(h)})
        if len(nerede) > BAGLANTI_TAVANI:
            notlar.append("baglanti_tavani")

        hiz = await _sinirli(
            {"mobil": hiz_isleri["mobil"], "masaustu": hiz_isleri["masaustu"]}, son_an
        )

    ssl_sonuc = yardimci.get("ssl") or (None, None)
    bolum_listesi = [
        _hiz_bolumu(hiz.get("mobil"), hiz.get("masaustu")),
        _seo_bolumu(
            ana_sayfa, sayfalar[1:], robots_var,
            None if sitemap_adresleri is None else len(sitemap_adresleri), robots_metni,
        ),
        _icerik_bolumu(ana_sayfa, sayfalar, kiriklar, denetlenen),
        _teknik_bolumu(ana, sayfalar, yardimci.get("http")),
        _guvenlik_bolumu(ana, ssl_sonuc[0], ssl_sonuc[1]),
        _ai_bolumu(llms_var, robots_metni, bool(ana_sayfa.oz and ana_sayfa.oz.jsonld_var)),
    ]
    bolumler = [b.sonuc() for b in bolum_listesi]

    ayrinti = {
        "son_url": ana.url,
        "yonlendirmeler": ana.zincir,
        "ana_sayfa_ms": ana.sure_ms,
        "sayfalar": [
            {
                "url": s.url,
                "durum": s.durum,
                "sure_ms": s.sure_ms,
                "baslik": (s.oz.baslik if s.oz else "")[:200],
            }
            for s in sayfalar
        ],
        "kirik_baglantilar": kiriklar,
        "denetlenen_baglanti": denetlenen,
        "hiz": {"mobil": hiz.get("mobil"), "masaustu": hiz.get("masaustu")},
        "ssl_bitis": ssl_sonuc[0].isoformat() if ssl_sonuc[0] else None,
        "robots_txt": robots_var,
        "sitemap_adres_sayisi": None if sitemap_adresleri is None else len(sitemap_adresleri),
        "llms_txt": llms_var,
        "notlar": sorted(set(notlar)),
        "sure_ms": int((time.monotonic() - basla) * 1000),
    }
    return {
        "url": url,
        "alan_adi": alan,
        "puan": genel_puan(bolumler),
        "bolumler": bolumler,
        "ayrinti": ayrinti,
    }
