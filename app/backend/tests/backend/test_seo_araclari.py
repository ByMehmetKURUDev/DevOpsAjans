"""Faz 4S — ücretsiz SEO araçları: motor, uçlar, SSRF, sınırlar, gizlilik, e-posta + CRM adayı.

Dış ağa ÇIKILMIYOR: site istekleri `httpx.MockTransport` ile sahte bir
"internete" gidiyor, DNS ve SSL ayrıntısı sahte. Yalnız `_ssl_bilgisi_esz`
testi yerel (127.0.0.1) bir TLS sunucusuna bağlanıyor.
"""

import asyncio
import gzip
import json
import logging
import re
import socket
import ssl
import struct
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import delete, select

from models.crm import CrmAdaylari
from models.inquiries import Inquiries
from models.seo_arac_istatistikleri import SeoAracIstatistikleri
from models.site_analyses import Site_analyses
from routers import seo_araclari as router_modulu
from services import pazarlama_izni
from services import seo_araclari as araclar
from services import site_analizi as motor

UC = "/api/v1/seo-araclari"
GENEL_IP = "93.184.216.34"
ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"
HTML = {"content-type": "text/html; charset=utf-8"}


def png(genislik: int, yukseklik: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", genislik, yukseklik) + b"\x08\x06\x00\x00\x00" + b"\x00" * 64


class SahteAg:
    """Sahte internet: adres → (durum, başlıklar, gövde). İstekler kaydediliyor."""

    def __init__(self):
        self.istekler: list[tuple[str, str]] = []
        self.yollar: dict[str, tuple[int, dict, bytes]] = {}
        self.dns: dict[str, list[str]] = {}
        self.yavas: set[str] = set()

    def ekle(self, url, durum=200, basliklar=None, govde: object = ""):
        ham = govde.encode("utf-8") if isinstance(govde, str) else govde
        self.yollar[url] = (durum, dict(basliklar or {}), ham)

    async def isle(self, istek: httpx.Request) -> httpx.Response:
        adres = str(istek.url)
        self.istekler.append((istek.method, adres))
        if istek.url.host in self.yavas:
            await asyncio.sleep(3)
        kayit = self.yollar.get(adres)
        if kayit is None:
            return httpx.Response(404, headers={"content-type": "text/html"}, content=b"yok")
        durum, basliklar, govde = kayit
        if istek.method == "HEAD":
            govde = b""
        return httpx.Response(durum, headers=basliklar, content=govde)

    def istek_yapildi_mi(self, parca: str) -> bool:
        return any(parca in adres for _y, adres in self.istekler)


@pytest.fixture
async def ag(monkeypatch, db_oturumu):
    ag = SahteAg()

    async def sahte_dns(host, port):
        if host in ag.dns:
            return ag.dns[host]
        if host.endswith(".yok"):
            raise socket.gaierror("çözülemedi")
        return [GENEL_IP]

    monkeypatch.setattr(motor, "_tasiyici_fabrikasi", lambda: httpx.MockTransport(ag.isle))
    monkeypatch.setattr(motor, "_dns_cozumle", sahte_dns)
    router_modulu.hiz_sinirlarini_temizle()
    # Yalnız bu özelliğin kendi sayaç tablosu temizlenir. Paylaşılan tablolar (inquiries, site_analyses,
    # crm_*) SİLİNMEZ: SQLite kimlikleri yeniden kullanır, başka testlerin CRM bağları bozulur. Testler
    # benzersiz e-posta (@seo4s.test) ve alan adı kullanıyor.
    await db_oturumu.execute(delete(SeoAracIstatistikleri))
    await db_oturumu.commit()
    return ag


async def _arac(istemci, arac, url, ip="198.51.100.7", **ek):
    return await istemci.post(f"{UC}/{arac}", json={"url": url, **ek}, headers={"x-forwarded-for": ip})


def _kodlar(govde: dict) -> dict:
    return {b["kod"]: b.get("deger") for b in govde["bulgular"]}


# --------------------------------------------------------------------------
# 1) Meta etiketleri
# --------------------------------------------------------------------------
IYI_META = """<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Örnek Site — kaliteli web hizmetleri ve danışmanlık</title>
<meta name="description" content="Örnek Site, işletmeler için hızlı ve ölçülebilir web siteleri kurar; bakım, SEO ve ölçümleme hizmetleri sunar.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<link rel="canonical" href="https://ornek.com/">
<link rel="alternate" hreflang="tr" href="https://ornek.com/">
<link rel="alternate" hreflang="en" href="https://ornek.com/en/">
<link rel="alternate" hreflang="x-default" href="https://ornek.com/">
</head><body><h1>Örnek</h1></body></html>"""


async def test_meta_mutlu_yol(istemci, ag):
    ag.ekle("https://ornek.com/", 200, HTML, IYI_META)
    y = await _arac(istemci, "meta-etiketleri", "ornek.com")
    assert y.status_code == 200, y.text
    g = y.json()
    k = _kodlar(g)
    for kod in ("title_iyi", "aciklama_iyi", "canonical_iyi", "robots_iyi", "viewport_iyi", "lang_iyi", "hreflang_iyi"):
        assert kod in k, (kod, k)
    assert g["ozet"]["hata"] == 0 and g["ozet"]["uyari"] == 0
    assert g["veri"]["baslik"].startswith("Örnek Site")
    assert g["veri"]["lang"] == "tr" and len(g["veri"]["hreflang"]) == 3
    # E-posta kanalı yok (testte RESEND/SMTP tanımsız): seçenek kapalı, sonuç önbelleğe de girmez.
    assert g["eposta"] == {"acik": False, "jeton": None, "pazarlama_izni_sor": False}
    assert len(araclar.onbellek) == 0
    # Her bulgu metin taşımıyor: yalnız kod/seviye/kontrol/değer.
    for b in g["bulgular"]:
        assert set(b) <= {"kontrol", "kod", "seviye", "deger"}


@pytest.fixture
def sahte_eposta(monkeypatch):
    """`ENVIRONMENT=test` (üretim dışı): sonuç e-postası sahte kutuya düşer, ağa çıkılmaz."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    for ad in ("RENDER", "RESEND_API_KEY", "SMTP_HOST"):
        monkeypatch.delenv(ad, raising=False)
    return router_modulu.sahte_kutu


async def test_meta_sorunlar(istemci, ag):
    sayfa = """<html><head><meta name="viewport" content="width=device-width, user-scalable=no">
<link rel="canonical" href="/a"><link rel="canonical" href="/b">
<link rel="alternate" hreflang="english" href="https://ornek.com/en/">
</head><body></body></html>"""
    ag.ekle("https://ornek.com/", 200, {**HTML, "x-robots-tag": "noindex"}, sayfa)
    k = _kodlar((await _arac(istemci, "meta-etiketleri", "https://ornek.com/")).json())
    assert {"title_yok", "aciklama_yok", "canonical_coklu", "viewport_yakinlastirma", "lang_yok"} <= set(k)
    assert k["robots_noindex"] == "X-Robots-Tag"
    assert k["hreflang_gecersiz"] == "english"
    assert "hreflang_kendisi_yok" in k


# --------------------------------------------------------------------------
# 2) Open Graph
# --------------------------------------------------------------------------
OG = """<html><head><title>Sayfa</title>
<meta property="og:title" content="OG Başlık &amp; Fazlası">
<meta property="og:description" content="Açıklama <b>kalın değil</b>">
<meta property="og:image" content="{gorsel}">
<meta property="og:url" content="https://ornek.com/"><meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
</head><body></body></html>"""


async def test_open_graph_mutlu_yol(istemci, ag):
    ag.ekle("https://ornek.com/", 200, HTML, OG.format(gorsel="https://cdn.ornek.com/kapak.png"))
    ag.ekle("https://cdn.ornek.com/kapak.png", 200, {"content-type": "image/png"}, png(1200, 630))
    g = (await _arac(istemci, "open-graph", "ornek.com")).json()
    k = _kodlar(g)
    assert "og_tamam" in k and k["twitter_kart_iyi"] == "summary_large_image"
    assert k["gorsel_iyi"] == "1200×630"
    on = g["veri"]["onizleme"]
    assert on["baslik"] == "OG Başlık & Fazlası"
    # Hedef sitenin metni düz metin olarak geliyor (etiket korunur, HTML olarak işlenmez).
    assert on["aciklama"] == "Açıklama <b>kalın değil</b>"
    assert on["gorsel"] == "https://cdn.ornek.com/kapak.png" and on["alan"] == "ornek.com"


async def test_open_graph_kucuk_ve_ic_ag_gorseli(istemci, ag):
    ag.ekle("https://ornek.com/", 200, HTML, OG.format(gorsel="https://cdn.ornek.com/k.png"))
    ag.ekle("https://cdn.ornek.com/k.png", 200, {"content-type": "image/png"}, png(600, 315))
    assert _kodlar((await _arac(istemci, "open-graph", "ornek.com")).json())["gorsel_onerilen_alti"] == "600×315"

    # og:image iç ağa işaret ediyor: istek ATILMADAN reddedilir.
    ag.ekle("https://ornek.com/", 200, HTML, OG.format(gorsel="http://10.0.0.5/gizli.png"))
    g = (await _arac(istemci, "open-graph", "ornek.com", ip="198.51.100.8")).json()
    assert _kodlar(g)["gorsel_erisilemedi"] == "adres_yasak"
    assert g["veri"]["onizleme"]["gorsel"] is None
    assert not ag.istek_yapildi_mi("10.0.0.5")


def test_gorsel_boyutu_bicimleri():
    assert araclar.gorsel_boyutu(png(1200, 630)) == (1200, 630)
    assert araclar.gorsel_boyutu(b"GIF89a" + struct.pack("<HH", 40, 30) + b"\x00" * 10) == (40, 30)
    jpeg = b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9 + b"\xff\xc0" + struct.pack(">HBHH", 17, 8, 630, 1200) + b"\x00" * 20
    assert araclar.gorsel_boyutu(jpeg) == (1200, 630)
    webp = b"RIFF\x00\x00\x00\x00WEBPVP8X" + b"\x00" * 8 + (1199).to_bytes(3, "little") + (629).to_bytes(3, "little")
    assert araclar.gorsel_boyutu(webp) == (1200, 630)
    assert araclar.gorsel_boyutu(b"<svg/>") is None


# --------------------------------------------------------------------------
# 3) Schema (JSON-LD)
# --------------------------------------------------------------------------
async def test_schema_okuyucu(istemci, ag):
    sayfa = """<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Kalem"}</script>
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
 {"@type":"Organization","name":"Örnek","url":"https://ornek.com/","logo":"https://ornek.com/l.png"},
 {"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"Soru?"}]},
 {"@type":"BlogPosting","headline":"Yazı","image":"x","datePublished":"2026-01-01","author":{"@type":"Person","name":"M"}}]}</script>
<script type="application/ld+json">{"@type": "Thing",
  "name": "bozuk",}</script>
</head><body><div itemscope itemtype="https://schema.org/Recipe"></div></body></html>"""
    ag.ekle("https://ornek.com/", 200, HTML, sayfa)
    g = (await _arac(istemci, "schema-okuyucu", "ornek.com")).json()
    eksikler = [b["deger"] for b in g["bulgular"] if b["kod"] == "jsonld_alan_eksik"]
    assert {"tur": "Product", "alanlar": "offers|review|aggregateRating"} in eksikler
    assert any(e["tur"] == "FAQPage" and "acceptedAnswer.text" in e["alanlar"] for e in eksikler)
    sozdizimi = [b["deger"] for b in g["bulgular"] if b["kod"] == "jsonld_sozdizimi"]
    assert len(sozdizimi) == 1 and sozdizimi[0]["blok"] == 3 and sozdizimi[0]["satir"] == 2
    k = _kodlar(g)
    assert "Organization" in k["jsonld_turler_var"] and "BlogPosting" in k["jsonld_turler_var"]
    assert k["mikroveri_var"] == "Recipe"
    turler = {o["tur"] for o in g["veri"]["ogeler"]}
    assert {"Product", "Organization", "FAQPage", "BlogPosting", "Person"} <= turler
    assert [b["gecerli"] for b in g["veri"]["bloklar"]] == [True, True, False]


async def test_schema_yok(istemci, ag):
    ag.ekle("https://ornek.com/", 200, HTML, "<html><head><title>x</title></head></html>")
    assert "jsonld_yok" in _kodlar((await _arac(istemci, "schema-okuyucu", "ornek.com")).json())


# --------------------------------------------------------------------------
# 4) robots.txt
# --------------------------------------------------------------------------
ROBOTS = """# yorum
Disallow: /eski
User-agent: *
Disallow: /admin
Allow: /admin/acik
Disallow: /*.pdf$
Crawl-delay: 5

User-agent: GPTBot
User-agent: CCBot
Disallow: /

Sitemap: https://ornek.com/sitemap.xml
Bilinmeyen: x
"""


def test_robots_karar_kurallari():
    c = araclar.robots_coz(ROBOTS)
    assert c["ajansiz"] == [2] and c["bilinmeyen"] == [14] and c["sitemapler"] == ["https://ornek.com/sitemap.xml"]
    k = araclar.robots_karar
    assert k(c, "Googlebot", "/admin/x")["izinli"] is False
    assert k(c, "Googlebot", "/admin/acik/sayfa")["izinli"] is True  # en uzun kural kazanır
    assert k(c, "Googlebot", "/dosya.pdf")["izinli"] is False
    assert k(c, "Googlebot", "/dosya.pdf?x=1")["izinli"] is True  # $ sonu bağlar
    assert k(c, "GPTBot", "/blog")["izinli"] is False
    assert k(c, "Googlebot-Image", "/admin")["izinli"] is False  # kendi grubu yok → *
    esit = araclar.robots_coz("User-agent: *\nDisallow: /a\nAllow: /a\n")
    assert k(esit, "*", "/a")["izinli"] is True  # eşitlikte Allow


async def test_robots_txt_araci(istemci, ag):
    ag.ekle("https://ornek.com/robots.txt", 200, {"content-type": "text/plain"}, ROBOTS)
    g = (await _arac(istemci, "robots-txt", "https://ornek.com/admin/gizli", ajan="Googlebot")).json()
    k = _kodlar(g)
    assert k["yol_engelli"]["satir"] == 4 and k["yol_engelli"]["ajan"] == "Googlebot"
    assert k["sitemap_satiri_var"] == 1 and "kural_ajansiz" in k and "bilinmeyen_yonerge" in k
    assert g["veri"]["sonuc"]["izinli"] is False

    g = (await _arac(istemci, "robots-txt", "https://ornek.com/", ajan="GPTBot")).json()
    assert _kodlar(g)["tum_site_engelli"] == "GPTBot"

    # 404 → her şey izinli; 5xx → Google siteyi geçici olarak engelli sayar.
    ag.ekle("https://ornek.com/robots.txt", 404, {"content-type": "text/html"}, "yok")
    k = _kodlar((await _arac(istemci, "robots-txt", "ornek.com/x", ajan="Bingbot")).json())
    assert "robots_yok" in k and "yol_izinli" in k
    ag.ekle("https://ornek.com/robots.txt", 503, {}, "")
    k = _kodlar((await _arac(istemci, "robots-txt", "ornek.com/x", ip="198.51.100.9")).json())
    assert k["robots_erisilemedi"] == 503 and "yol_bilinmiyor" in k

    y = await _arac(istemci, "robots-txt", "ornek.com", ajan="kötü ajan<script>", ip="198.51.100.9")
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "ajan_gecersiz"


# --------------------------------------------------------------------------
# 5) Site haritası
# --------------------------------------------------------------------------
SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://ornek.com/</loc><lastmod>2026-09-01</lastmod><priority>0.9</priority></url>
<url><loc>https://ornek.com/a</loc><lastmod>2026-09-01T10:00:00+03:00</lastmod></url>
<url><loc>https://ornek.com/kirik</loc><lastmod>01.09.2026</lastmod></url>
<url><loc>https://ornek.com/eski</loc><lastmod>2099-01-01</lastmod><changefreq>bazen</changefreq></url>
<url><loc>https://baska.com/x</loc></url>
<url><loc>ftp://ornek.com/y</loc></url>
</urlset>"""


async def test_site_haritasi_robots_uzerinden(istemci, ag):
    ag.ekle("https://ornek.com/robots.txt", 200, {"content-type": "text/plain"}, "Sitemap: https://ornek.com/harita.xml\n")
    ag.ekle("https://ornek.com/harita.xml", 200, {"content-type": "application/xml"}, SITEMAP)
    ag.ekle("https://ornek.com/", 200, HTML, "x")
    ag.ekle("https://ornek.com/a", 200, HTML, "x")
    ag.ekle("https://ornek.com/kirik", 404, HTML, "")
    ag.ekle("https://ornek.com/eski", 301, {"location": "https://ornek.com/"}, "")
    g = (await _arac(istemci, "site-haritasi", "ornek.com")).json()
    k = _kodlar(g)
    assert g["veri"]["kaynak"] == "robots" and g["veri"]["adres_sayisi"] == 6
    assert k["adres_hatali"] == 1 and k["adres_baska_site"] == 1
    assert k["lastmod_hatali"] == 1 and k["lastmod_gelecek"] == 1 and k["lastmod_eksik"] == 1
    assert k["alan_hatali"] == 1
    assert k["orneklem_hatali"] == {"hatali": 1, "toplam": 4}
    assert k["orneklem_yonlendirme"] == {"hatali": 1, "toplam": 4}
    assert not ag.istek_yapildi_mi("baska.com")


async def test_site_haritasi_gz_dizin_ve_dtd(istemci, ag):
    dizin = """<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://ornek.com/s1.xml.gz</loc><lastmod>2026-09-01</lastmod></sitemap></sitemapindex>"""
    alt = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://ornek.com/</loc></url></urlset>"""
    ag.ekle("https://ornek.com/sitemap.xml", 200, {"content-type": "application/xml"}, dizin)
    ag.ekle("https://ornek.com/s1.xml.gz", 200, {"content-type": "application/x-gzip"}, gzip.compress(alt.encode()))
    ag.ekle("https://ornek.com/", 200, HTML, "x")
    g = (await _arac(istemci, "site-haritasi", "https://ornek.com/sitemap.xml")).json()
    k = _kodlar(g)
    assert k["sitemap_dizini"] == 1 and g["veri"]["alt_adres_sayisi"] == 1
    assert k["orneklem_iyi"] == 1

    # DTD / varlık tanımı: XML ayrıştırılmadan reddedilir (XXE, "billion laughs").
    kotu = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><urlset><url><loc>&a;</loc></url></urlset>'
    ag.ekle("https://ornek.com/kotu.xml", 200, {"content-type": "application/xml"}, kotu)
    assert "dtd_reddedildi" in _kodlar((await _arac(istemci, "site-haritasi", "https://ornek.com/kotu.xml")).json())


# --------------------------------------------------------------------------
# 6) Yönlendirme zinciri
# --------------------------------------------------------------------------
async def test_yonlendirme_zinciri(istemci, ag):
    ag.ekle("http://ornek.com/", 301, {"location": "https://ornek.com/"})
    ag.ekle("https://ornek.com/", 200, HTML, "x")
    ag.ekle("http://www.ornek.com/", 301, {"location": "http://ornek.com/"})
    ag.ekle("https://www.ornek.com/", 302, {"location": "https://ornek.com/"})
    g = (await _arac(istemci, "yonlendirme", "http://www.ornek.com/")).json()
    k = _kodlar(g)
    assert k["zincir_uzun"] == 2 and k["son_durum_iyi"] == 200
    assert "https_yonlendirme_iyi" in k and "www_iyi" in k
    girilen = g["veri"]["zincirler"][0]
    assert [a["durum"] for a in girilen["adimlar"]] == [301, 301, 200]
    assert g["son_url"] == "https://ornek.com/"


async def test_yonlendirme_dongu_ve_gecici_https(istemci, ag):
    ag.ekle("https://ornek.com/a", 301, {"location": "/b"})
    ag.ekle("https://ornek.com/b", 302, {"location": "/a"})
    ag.ekle("http://ornek.com/", 302, {"location": "https://ornek.com/"})
    ag.ekle("https://ornek.com/", 200, HTML, "x")
    k = _kodlar((await _arac(istemci, "yonlendirme", "https://ornek.com/a")).json())
    assert "dongu" in k and k["https_gecici"] == 302


# --------------------------------------------------------------------------
# 7) Güvenlik başlıkları
# --------------------------------------------------------------------------
async def test_guvenlik_basliklari(istemci, ag):
    tam = {
        **HTML,
        "strict-transport-security": "max-age=31536000; includeSubDomains",
        "content-security-policy": "default-src 'self'; script-src 'self' 'sha256-abc'; frame-ancestors 'none'",
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin-when-cross-origin",
        "permissions-policy": "camera=()",
        "server": "nginx/1.25.3",
    }
    ag.ekle("https://ornek.com/", 200, tam, "x")
    g = (await _arac(istemci, "guvenlik-basliklari", "ornek.com")).json()
    assert g["puan"] == 100 and g["veri"]["harf"] == "A+"
    assert _kodlar(g)["sunucu_surumu"] == "Server: nginx/1.25.3"

    ag.ekle("https://ornek.com/", 200, {**HTML, "content-security-policy": "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
                                        "referrer-policy": "unsafe-url"}, "x")
    g = (await _arac(istemci, "guvenlik-basliklari", "ornek.com")).json()
    k = _kodlar(g)
    assert {"hsts_yok", "csp_unsafe_inline", "csp_unsafe_eval", "nosniff_yok", "permissions_yok", "frame_yok"} <= set(k)
    assert k["referrer_zayif"] == "unsafe-url"
    assert g["puan"] == 25 - 8 - 5 + 4 and g["veri"]["harf"] == "F"


# --------------------------------------------------------------------------
# 8) SSL
# --------------------------------------------------------------------------
async def test_ssl_araci_sahte_bilgi(istemci, ag, monkeypatch):
    bitis = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()

    async def sahte(host):
        await motor._guvenli_ipler(host, 443)  # SSRF denetimi gerçek
        return {
            "dogrulandi": True, "hata": None, "tls_surumu": "TLSv1.3", "sifre": "TLS_AES_256_GCM_SHA384",
            "sertifika": {"konu": {"cn": host}, "yayinci": {"cn": "R11", "o": "Let's Encrypt"}, "bitis": bitis,
                          "baslangic": bitis, "san": [host], "seri": "AB", "imza": "sha256", "anahtar": "EC secp256r1",
                          "aia": None, "kendinden_imzali": False},
            "zincir": [],
        }

    monkeypatch.setattr(motor, "ssl_bilgisi", sahte)
    g = (await _arac(istemci, "ssl-sertifikasi", "ornek.com")).json()
    k = _kodlar(g)
    assert k["ssl_bitiyor"] in (9, 10) and k["tls_iyi"] == "TLSv1.3" and "ssl_dogrulandi" in k
    assert g["veri"]["sertifika"]["yayinci"]["o"] == "Let's Encrypt"

    y = await _arac(istemci, "ssl-sertifikasi", "https://127.0.0.1/")
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "adres_yasak"


def _kendinden_imzali(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    anahtar = ec.generate_private_key(ec.SECP256R1())
    ad = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "yerel.test")])
    simdi = datetime.now(timezone.utc)
    sert = (
        x509.CertificateBuilder().subject_name(ad).issuer_name(ad).public_key(anahtar.public_key())
        .serial_number(4242).not_valid_before(simdi - timedelta(days=1)).not_valid_after(simdi + timedelta(days=45))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("yerel.test")]), critical=False)
        .sign(anahtar, hashes.SHA256())
    )
    (tmp_path / "s.pem").write_bytes(sert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "a.pem").write_bytes(anahtar.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return tmp_path / "s.pem", tmp_path / "a.pem"


def test_ssl_bilgisi_yerel_tls_sunucusu(tmp_path):
    sert, anahtar = _kendinden_imzali(tmp_path)
    baglam = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    baglam.load_cert_chain(sert, anahtar)
    dinleyici = socket.socket()
    dinleyici.bind(("127.0.0.1", 0))
    dinleyici.listen(4)
    port = dinleyici.getsockname()[1]

    def sun():
        for _ in range(2):
            try:
                baglanti, _a = dinleyici.accept()
                with baglam.wrap_socket(baglanti, server_side=True) as tls:
                    tls.recv(1)
            except (OSError, ssl.SSLError):
                pass

    is_ = threading.Thread(target=sun, daemon=True)
    is_.start()
    bilgi = motor._ssl_bilgisi_esz("yerel.test", "127.0.0.1", port)
    dinleyici.close()
    assert bilgi["dogrulandi"] is False and bilgi["hata_kodu"] in (18, 19)
    assert bilgi["sertifika"]["konu"]["cn"] == "yerel.test" and bilgi["sertifika"]["kendinden_imzali"] is True
    assert bilgi["sertifika"]["san"] == ["yerel.test"] and bilgi["sertifika"]["seri"] == format(4242, "X")
    assert bilgi["tls_surumu"] in ("TLSv1.2", "TLSv1.3")
    s = araclar.Sonuc("ssl-sertifikasi")
    araclar.ssl_incele(s, bilgi)
    k = {b["kod"]: b.get("deger") for b in s.bulgular}
    assert "ssl_kendinden_imzali" in k and 43 <= k["ssl_gecerli"] <= 45


# --------------------------------------------------------------------------
# 9) Başlık yapısı  ·  10) Kelime / anahtar kelime yoğunluğu
# --------------------------------------------------------------------------
def test_turkce_kucuk_harf_ve_durak_kelimeler():
    assert araclar.kucuk_harf("IŞIK İSTANBUL", "tr") == "ışık istanbul"
    assert araclar.kucuk_harf("Iğdır'da İzmir", "tr-TR") == "ığdır'da izmir"
    # Türkçe dışı: I → i, İ birleşik nokta üretmeden i.
    assert araclar.kucuk_harf("INDEX İstanbul", "en") == "index istanbul"
    a = araclar.kelime_analizi("Bu bir İSTANBUL rehberi ve İstanbul için ışık. IŞIK da çok güzel; İstanbul'da 2026.", "tr")
    sozluk = {x["kelime"]: x["sayi"] for x in a["en_sik"]}
    assert sozluk["istanbul"] == 3 and sozluk["ışık"] == 2
    for durak in ("bu", "bir", "ve", "için", "da", "çok"):
        assert durak not in sozluk
    assert "i̇stanbul" not in sozluk and "isik" not in sozluk
    assert a["toplam_kelime"] == 14  # rakam kelime sayılmaz


async def test_baslik_yapisi(istemci, ag):
    govde = "<p>" + " ".join(["SEO"] * 30 + ["içerik"] * 300) + "</p>"
    sayfa = f"""<html lang="tr"><head><title>T</title><style>h1{{}}</style></head><body>
<h2>Önce iki</h2><h1>Ana <em>başlık</em></h1><h2>Alt</h2><h3>Üç</h3><h2></h2><h4>Dördüncü</h4>
<script>var h = "<h1>sahte</h1>";</script>{govde}</body></html>"""
    ag.ekle("https://ornek.com/", 200, HTML, sayfa)
    g = (await _arac(istemci, "baslik-yapisi", "ornek.com")).json()
    k = _kodlar(g)
    assert k["h1_iyi"] == "Ana başlık"
    assert k["seviye_atlama"] == "H2→H4" and k["bos_baslik"] == 1 and k["ilk_baslik_h1_degil"] == "H2"
    assert [b["seviye"] for b in g["veri"]["basliklar"]] == [2, 1, 2, 3, 2, 4]
    assert g["veri"]["seviye_sayilari"] == {"h1": 1, "h2": 3, "h3": 1, "h4": 1, "h5": 0, "h6": 0}
    # Kelime yoğunluğu artık ayrı araç: başlık aracında kelime bulgusu yok.
    assert not {"anahtar_asiri", "icerik_az", "kelime_iyi"} & set(k)


async def test_kelime_yogunlugu_hedef_kelimeyle(istemci, ag):
    govde = "<p>" + " ".join(["SEO"] * 30 + ["içerik"] * 300) + " İSTANBUL IŞIK ve İstanbul ışık için bir rehber.</p>"
    sayfa = f"""<html lang="tr"><head><title>Seo Ajansı | Örnek</title>
<meta name="description" content="Kurumsal SEO ajansı hizmetleri."></head><body>
<h1>SEO ajansı</h1>{govde}<script>var x = "seo ajansı seo ajansı";</script></body></html>"""
    ag.ekle("https://ornek.com/hizmetler/seo-ajansi", 200, HTML, sayfa)
    g = (await _arac(istemci, "kelime-yogunlugu", "https://ornek.com/hizmetler/seo-ajansi", kelime="SEO  Ajansı")).json()
    k = _kodlar(g)
    assert k["anahtar_asiri"]["kelime"] == "içerik" and "kelime_iyi" in k
    v = g["veri"]
    assert v["dil"] == "tr" and v["en_sik"][1]["kelime"] == "seo"
    sozluk = {x["kelime"]: x["sayi"] for x in v["en_sik"]}
    # Türkçe küçük harf: İSTANBUL/İstanbul → istanbul (2), IŞIK/ışık → ışık (2); durak kelimeler ayıklandı.
    assert sozluk["istanbul"] == 2 and sozluk["ışık"] == 2 and not {"ve", "için", "bir"} & set(sozluk)
    # Hedef: H1'de bir kez, metinde betik içindeki geçmiyor; title/açıklama/URL'de var (URL ASCII'ye katlanıyor).
    assert v["hedef"] == {"kelime": "SEO Ajansı", "sayi": 1, "yuzde": round(100 * 2 / v["toplam_kelime"], 2),
                          "title": True, "h1": True, "aciklama": True, "url": True}
    assert k["hedef_iyi"]["sayi"] == 1 and k["hedef_konum_iyi"] == "SEO Ajansı"
    assert any(x["kelime"] == "seo seo seo" for x in v["ucluler"])

    # Hedef hiç geçmiyor → hata; yerleri de eksik.
    g = (await _arac(istemci, "kelime-yogunlugu", "https://ornek.com/hizmetler/seo-ajansi", kelime="web tasarım")).json()
    k = _kodlar(g)
    assert k["hedef_yok"] == "web tasarım"
    assert {"hedef_title_yok", "hedef_h1_yok", "hedef_aciklama_yok", "hedef_url_yok"} <= set(k)

    # Hedefsiz de çalışır; biçim dışı hedef sınırdan önce 400.
    g = (await _arac(istemci, "kelime-yogunlugu", "https://ornek.com/hizmetler/seo-ajansi")).json()
    assert g["veri"]["hedef"] is None and not any(b["kontrol"].startswith("hedef") for b in g["bulgular"])
    for kotu in ("<script>", "a" * 61, "bir iki üç dört beş altı yedi", "seo_ajansi", "2026"):
        y = await _arac(istemci, "kelime-yogunlugu", "ornek.com", kelime=kotu)
        assert y.status_code == 400 and y.json()["detail"]["kod"] == "kelime_gecersiz", kotu


# --------------------------------------------------------------------------
# SSRF
# --------------------------------------------------------------------------
@pytest.mark.parametrize("adres", ["http://127.0.0.1/", "http://10.1.2.3/", "http://169.254.169.254/latest/meta-data/",
                                   "http://localhost/", "http://[::ffff:10.0.0.1]/", "http://ic.ornek.com/"])
@pytest.mark.parametrize("arac", ["meta-etiketleri", "yonlendirme", "robots-txt", "site-haritasi", "guvenlik-basliklari"])
async def test_ic_adresler_reddedilir(istemci, ag, adres, arac):
    ag.dns["ic.ornek.com"] = ["10.0.0.7"]
    y = await _arac(istemci, arac, adres)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "adres_yasak", y.text
    assert ag.istekler == []


@pytest.mark.parametrize(
    "arac", ["meta-etiketleri", "open-graph", "yonlendirme", "guvenlik-basliklari", "baslik-yapisi", "kelime-yogunlugu"]
)
async def test_yonlendirmeyle_ic_adrese_kacis_reddedilir(istemci, ag, arac):
    ag.ekle("https://ornek.com/", 302, {"location": "http://169.254.169.254/latest/meta-data/"})
    y = await _arac(istemci, arac, "ornek.com")
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "adres_yasak"
    assert not ag.istek_yapildi_mi("169.254.169.254")


async def test_izinsiz_port_ve_bicim(istemci, ag):
    for adres, kod in (("http://ornek.com:8080/", "adres_gecersiz"), ("ftp://ornek.com/", "adres_gecersiz"),
                       ("file:///etc/passwd", "adres_gecersiz"), ("file://localhost/etc/hosts", "adres_gecersiz"),
                       ("gopher://ornek.com/", "adres_gecersiz"), ("javascript:alert(1)", "adres_gecersiz"),
                       ("http://kullanici:parola@ornek.com/", "adres_gecersiz"), ("", "adres_gecersiz")):
        y = await _arac(istemci, "meta-etiketleri", adres)
        assert y.status_code == 400 and y.json()["detail"]["kod"] == kod, adres
    assert ag.istekler == []
    assert (await _arac(istemci, "yok-boyle-arac", "ornek.com")).status_code == 404
    y = await _arac(istemci, "meta-etiketleri", "bulunamaz.yok")
    assert y.status_code == 422 and y.json()["detail"]["kod"] == "cozumlenemedi"


# --------------------------------------------------------------------------
# Boyut / süre sınırı
# --------------------------------------------------------------------------
async def test_govde_tavani_ve_kesilme(istemci, ag, monkeypatch):
    buyuk = "User-agent: *\n" + ("Disallow: /x\n" * 60_000)  # ~780 kB > 500 KiB
    ag.ekle("https://ornek.com/robots.txt", 200, {"content-type": "text/plain"}, buyuk)
    assert "robots_buyuk" in _kodlar((await _arac(istemci, "robots-txt", "ornek.com")).json())

    ag.ekle("https://ornek.com/buyuk", 200, HTML, "a" * 5000)
    async with motor._istemci() as istemci_:
        y = await motor.Gezgin(istemci_, govde_tavani=1000).getir("https://ornek.com/buyuk")
    assert y.kesildi is True and len(y.govde) == 1000


async def test_sure_siniri(istemci, ag, monkeypatch):
    ag.ekle("https://yavas.com/", 200, HTML, "x")
    ag.yavas.add("yavas.com")
    monkeypatch.setattr(araclar, "ISTEK_ZAMAN_ASIMI", 0.2)
    y = await _arac(istemci, "meta-etiketleri", "yavas.com")
    assert y.status_code == 422 and y.json()["detail"]["kod"] == "ulasilamadi"

    monkeypatch.setattr(araclar, "ISTEK_ZAMAN_ASIMI", 10.0)
    monkeypatch.setattr(araclar, "TOPLAM_TAVAN", 0.3)
    y = await _arac(istemci, "meta-etiketleri", "yavas.com", ip="198.51.100.20")
    assert y.status_code == 422 and y.json()["detail"]["kod"] == "zaman_asimi"


# --------------------------------------------------------------------------
# Hız sınırı (kalıcı sayaç)
# --------------------------------------------------------------------------
async def test_hiz_siniri_dakika_ve_gun(istemci, ag, monkeypatch):
    ag.ekle("https://ornek.com/", 200, HTML, IYI_META)
    for _ in range(router_modulu.ARAC_DAKIKA):
        assert (await _arac(istemci, "meta-etiketleri", "ornek.com")).status_code == 200
    y = await _arac(istemci, "meta-etiketleri", "ornek.com")
    assert y.status_code == 429 and y.json()["detail"]["kod"] == "sinir_dakika"
    assert y.headers.get("retry-after") == "60"
    # Başka araç ve başka IP etkilenmez.
    assert (await _arac(istemci, "baslik-yapisi", "ornek.com")).status_code == 200
    assert (await _arac(istemci, "meta-etiketleri", "ornek.com", ip="203.0.113.5")).status_code == 200
    # Sayaç veritabanında (hiz_sayaclari) — ham IP değil özet anahtar.
    from models.hiz_sayaclari import HizSayaclari
    from core.database import db_manager

    async with db_manager.async_session_maker() as o:
        anahtarlar = [r[0] for r in (await o.execute(select(HizSayaclari.anahtar))).all()]
    assert anahtarlar and not any("198.51.100.7" in a for a in anahtarlar)

    router_modulu.hiz_sinirlarini_temizle()
    monkeypatch.setattr(router_modulu._arac_gun, "sinir", 2)
    for _ in range(2):
        assert (await _arac(istemci, "open-graph", "ornek.com", ip="203.0.113.9")).status_code == 200
    y = await _arac(istemci, "open-graph", "ornek.com", ip="203.0.113.9")
    assert y.status_code == 429 and y.json()["detail"]["kod"] == "sinir_gun"


# --------------------------------------------------------------------------
# Gizlilik: sorgulanan adres saklanmıyor, yalnız sayaç
# --------------------------------------------------------------------------
async def test_sorgulanan_adres_saklanmaz(istemci, ag, db_oturumu, caplog):
    caplog.set_level(logging.DEBUG)
    host = "gizli-musteri-alani.com"
    ag.ekle(f"https://{host}/", 200, HTML, IYI_META)
    ag.ekle(f"https://{host}/robots.txt", 200, {"content-type": "text/plain"}, ROBOTS)
    for arac in ("meta-etiketleri", "robots-txt", "guvenlik-basliklari", "baslik-yapisi", "kelime-yogunlugu"):
        assert (await _arac(istemci, arac, host)).status_code == 200
    # Ulaşılamayan adres de (hata yolu) günlüğe yazılmıyor.
    ag.yavas.add("yavas-gizli.com")
    ag.ekle("https://yavas-gizli.com/", 200, HTML, "x")
    araclar_zaman = araclar.ISTEK_ZAMAN_ASIMI
    araclar.ISTEK_ZAMAN_ASIMI = 0.1
    try:
        assert (await _arac(istemci, "meta-etiketleri", "yavas-gizli.com")).status_code == 422
    finally:
        araclar.ISTEK_ZAMAN_ASIMI = araclar_zaman

    # Bütün tablolarda bütün metin sütunları: adres hiçbir yerde yok.
    from core.database import Base

    for tablo in Base.metadata.sorted_tables:
        try:
            satirlar = (await db_oturumu.execute(select(tablo))).all()
        except Exception:  # noqa: BLE001 - henüz oluşmamış tablo
            await db_oturumu.rollback()
            continue
        for satir in satirlar:
            metin = " ".join(str(d) for d in satir)
            assert host not in metin and "yavas-gizli" not in metin, tablo.name
    assert host not in caplog.text and "yavas-gizli" not in caplog.text

    # Kalıcı olan yalnız araç × gün sayacı.
    sayilar = {
        r.arac: (r.sayi, r.hata)
        for r in (await db_oturumu.execute(select(SeoAracIstatistikleri))).scalars().all()
    }
    assert sayilar["meta-etiketleri"] == (2, 1) and sayilar["robots-txt"] == (1, 0)
    # "Son analizler" listesi gibi herkese açık bir okuma ucu yok.
    assert (await istemci.get(UC)).status_code in (404, 405)
    assert (await istemci.get(f"{UC}/meta-etiketleri")).status_code in (404, 405)


# --------------------------------------------------------------------------
# "Sonucu e-postayla gönder" → CRM adayı (Gelen kutusuna düşmez) + pazarlama izni
# --------------------------------------------------------------------------
async def _calistir_jeton(istemci, arac="meta-etiketleri", url="ornek.com", ip="198.51.100.7", **ek):
    y = await _arac(istemci, arac, url, ip=ip, **ek)
    assert y.status_code == 200, y.text
    e = y.json()["eposta"]
    assert e["acik"] is True and e["jeton"]
    return y.json(), e["jeton"]


async def _epostala(istemci, arac, govde, ip="198.51.100.7"):
    return await istemci.post(f"{UC}/{arac}/eposta", json=govde, headers={"x-forwarded-for": ip})


async def _aday(db, eposta):
    db.expire_all()
    return (await db.execute(select(CrmAdaylari).where(CrmAdaylari.email == eposta))).scalars().all()


async def test_eposta_kanali_yoksa_secenek_gizli_ve_uc_503(istemci, ag, db_oturumu, monkeypatch):
    for ad in ("RESEND_API_KEY", "SMTP_HOST", "ENVIRONMENT"):
        monkeypatch.delenv(ad, raising=False)
    ag.ekle("https://ornek.com/", 200, HTML, IYI_META)
    g = (await _arac(istemci, "meta-etiketleri", "ornek.com")).json()
    assert g["eposta"] == {"acik": False, "jeton": None, "pazarlama_izni_sor": False}
    y = await _epostala(istemci, "meta-etiketleri", {"jeton": "x", "eposta": "a@seo4s.test"})
    assert y.status_code == 503 and y.json()["detail"]["kod"] == "eposta_kapali"
    assert await _aday(db_oturumu, "a@seo4s.test") == []


async def test_eposta_kanali_uretimde_sahte_degil(monkeypatch, db_oturumu):
    """`ENVIRONMENT=test` Render'da (RENDER tanımlı) sahte kanal açmaz: seçenek kapalı kalır."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert await router_modulu.eposta_kanali(db_oturumu) == ""
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    assert await router_modulu.eposta_kanali(db_oturumu) == "resend"


async def test_sonucu_epostala_crm_adayi_gelen_kutusuna_dusmez(istemci, ag, db_oturumu, sahte_eposta, yonetici_basligi):
    ag.ekle("https://ornek.com/", 200, HTML, IYI_META.replace('content="index, follow"', 'content="noindex"'))
    sonuc, jeton = await _calistir_jeton(istemci)
    assert sonuc["eposta"]["pazarlama_izni_sor"] is False
    eposta = "Aday.Kisi@SEO4S.test"
    y = await _epostala(istemci, "meta-etiketleri", {"jeton": jeton, "eposta": eposta, "ad": "Ayşe  Yılmaz", "dil": "en"})
    assert y.status_code == 200 and y.json() == {"gonderildi": True}

    # E-posta: alıcıya, ziyaretçinin dilinde, bulgu cümleleriyle; hedefin metni HTML'de kaçışlı.
    kutu = sahte_eposta()
    assert len(kutu) == 1 and kutu[0]["alici"] == "aday.kisi@seo4s.test"
    m = kutu[0]
    assert m["konu"] == f"{araclar.arac_adi('meta-etiketleri', 'en')} result: ornek.com"
    assert m["metin"].startswith("Hi Ayşe Yılmaz,") and "Recommended fixes:" in m["metin"]
    # Sorun cümlesi ziyaretçinin dilinde (noindex → robots meta bulgusu).
    assert araclar.metinler()["en"]["kontrol"]["robots_meta"] in m["metin"]
    assert "{{" not in m["metin"] and "{{" not in m["html"]
    assert "https://mehmetkuru.dev/en/site-analizi/?url=https%3A%2F%2Fornek.com%2F&amp;arac=meta-etiketleri" in m["html"]

    # CRM adayı: kaynak seo_araci, ayrıntı seo_araci:<arac>; izin yok → pazarlama izni kaydı yok.
    a = (await _aday(db_oturumu, "aday.kisi@seo4s.test"))[0]
    assert a.kaynak == "seo_araci" and a.kaynak_detay == "seo_araci:meta-etiketleri"
    assert a.kaynak_tablo is None and a.ad == "Ayşe Yılmaz" and a.bildirim_bekliyor is True
    assert "ornek.com" in (a.ilk_mesaj or "") and a.pazarlama_izni_at is None and a.pazarlama_izni_kaynak is None
    # Gelen kutusuna düşmez: talep (inquiries) açılmadı, aday hiçbir kayda bağlı değil, Gelen kutusu listesinde yok.
    assert (await db_oturumu.execute(select(Inquiries).where(Inquiries.email == "aday.kisi@seo4s.test"))).scalars().all() == []
    from models.crm import CrmBagliKayitlar

    assert (await db_oturumu.execute(select(CrmBagliKayitlar).where(CrmBagliKayitlar.aday_id == a.id))).scalars().all() == []
    gk = await istemci.get("/api/v1/gelen-kutusu", params={"q": "aday.kisi@seo4s.test"}, headers=yonetici_basligi)
    assert gk.status_code == 200 and "aday.kisi@seo4s.test" not in gk.text

    # Jeton tek kullanımlık; sonuç bellekten silindi.
    y = await _epostala(istemci, "meta-etiketleri", {"jeton": jeton, "eposta": eposta})
    assert y.status_code == 410 and y.json()["detail"]["kod"] == "sonuc_suresi_doldu"
    assert len(araclar.onbellek) == 0

    # Aynı kişi ikinci kez isterse yeni aday açılmaz (açık aday tekilleştirmesi), sayaçta aday artmaz.
    _s, jeton2 = await _calistir_jeton(istemci, "open-graph")
    assert (await _epostala(istemci, "open-graph", {"jeton": jeton2, "eposta": eposta})).status_code == 200
    assert len(await _aday(db_oturumu, "aday.kisi@seo4s.test")) == 1
    sayac = {r.arac: (r.eposta, r.aday) for r in (await db_oturumu.execute(select(SeoAracIstatistikleri))).scalars().all()}
    assert sayac["meta-etiketleri"] == (1, 1) and sayac["open-graph"] == (1, 0)


async def test_eposta_pazarlama_izni_ayri_ve_istege_bagli(istemci, ag, db_oturumu, sahte_eposta):
    from models.site_settings import Site_settings

    ag.ekle("https://ornek.com/", 200, HTML, IYI_META)
    db_oturumu.add(Site_settings(setting_key=pazarlama_izni.SITE_ANALIZI_AYARI, setting_value="1"))
    await db_oturumu.commit()
    try:
        # Ayar açık + kutu işaretli (JSON true) → izin, zaman, metin sürümü ve kaynak kaydedilir.
        sonuc, jeton = await _calistir_jeton(istemci)
        assert sonuc["eposta"]["pazarlama_izni_sor"] is True
        y = await _epostala(istemci, "meta-etiketleri", {"jeton": jeton, "eposta": "izinli@seo4s.test", "pazarlama_izni": True, "dil": "en"})
        assert y.status_code == 200
        a = (await _aday(db_oturumu, "izinli@seo4s.test"))[0]
        assert a.pazarlama_izni_at is not None and a.pazarlama_izni_kaynak == "seo_araci:meta-etiketleri"
        assert a.pazarlama_metin_surumu == "1/en"

        # Kutu işaretsiz ya da "true" metni (JSON true değil) → izin YOK.
        for i, deger in enumerate((False, "true", None)):
            _s, jeton = await _calistir_jeton(istemci, ip=f"198.51.100.{60 + i}")
            eposta = f"izinsiz{i}@seo4s.test"
            y = await _epostala(istemci, "meta-etiketleri", {"jeton": jeton, "eposta": eposta, "pazarlama_izni": deger}, ip=f"198.51.100.{60 + i}")
            assert y.status_code == 200
            a = (await _aday(db_oturumu, eposta))[0]
            assert a.pazarlama_izni_at is None and a.pazarlama_metin_surumu is None, deger
    finally:
        await db_oturumu.execute(delete(Site_settings).where(Site_settings.setting_key == pazarlama_izni.SITE_ANALIZI_AYARI))
        await db_oturumu.commit()

    # Ayar kapalı: kutu gösterilmez; istemci yine de true gönderse izin kaydedilmez.
    sonuc, jeton = await _calistir_jeton(istemci, ip="198.51.100.70")
    assert sonuc["eposta"]["pazarlama_izni_sor"] is False
    y = await _epostala(istemci, "meta-etiketleri", {"jeton": jeton, "eposta": "ayarsiz@seo4s.test", "pazarlama_izni": True}, ip="198.51.100.70")
    assert y.status_code == 200
    assert (await _aday(db_oturumu, "ayarsiz@seo4s.test"))[0].pazarlama_izni_at is None


async def test_eposta_dogrulama_jeton_bal_kupu_ve_hiz_siniri(istemci, ag, db_oturumu, sahte_eposta):
    ag.ekle("https://ornek.com/", 200, HTML, IYI_META)
    _s, jeton = await _calistir_jeton(istemci)
    # Geçersiz e-posta, bilinmeyen araç, başka aracın jetonu.
    for kotu in ("", "a@b", "x" * 250 + "@ornek.com", "iki@@ornek.com"):
        y = await _epostala(istemci, "meta-etiketleri", {"jeton": jeton, "eposta": kotu})
        assert y.status_code == 400 and y.json()["detail"]["kod"] == "eposta_gecersiz", kotu
    assert (await _epostala(istemci, "yok-arac", {"jeton": jeton, "eposta": "a@seo4s.test"})).status_code == 404
    y = await _epostala(istemci, "open-graph", {"jeton": jeton, "eposta": "a@seo4s.test"})
    assert y.status_code == 410 and y.json()["detail"]["kod"] == "sonuc_suresi_doldu"
    # Bal küpü: bot "başarılı" görür, hiçbir şey gönderilmez/kaydedilmez, jeton harcanmaz.
    y = await _epostala(istemci, "meta-etiketleri", {"jeton": jeton, "eposta": "bot@seo4s.test", "web_sitesi": "http://spam"})
    assert y.status_code == 200 and sahte_eposta() == [] and await _aday(db_oturumu, "bot@seo4s.test") == []
    assert araclar.onbellek.al(jeton, "meta-etiketleri") is not None

    # Alıcı başına günde 3: farklı IP'lerden de olsa 4. istek 429 (başkasının kutusu doldurulamaz).
    for i in range(router_modulu.EPOSTA_ALICI_GUN):
        _s, j = await _calistir_jeton(istemci, ip=f"203.0.113.{10 + i}")
        assert (await _epostala(istemci, "meta-etiketleri", {"jeton": j, "eposta": "kurban@seo4s.test"}, ip=f"203.0.113.{10 + i}")).status_code == 200
    _s, j = await _calistir_jeton(istemci, ip="203.0.113.20")
    y = await _epostala(istemci, "meta-etiketleri", {"jeton": j, "eposta": "kurban@seo4s.test"}, ip="203.0.113.20")
    assert y.status_code == 429 and y.json()["detail"]["kod"] == "sinir_eposta" and y.headers["retry-after"] == "3600"
    assert len([m for m in sahte_eposta() if m["alici"] == "kurban@seo4s.test"]) == router_modulu.EPOSTA_ALICI_GUN

    # IP başına saatte 5 (farklı alıcılar).
    router_modulu.hiz_sinirlarini_temizle()
    for i in range(router_modulu.EPOSTA_IP_SAAT):
        _s, j = await _calistir_jeton(istemci, ip="203.0.113.50" if i < 4 else "203.0.113.51")
        assert (await _epostala(istemci, "meta-etiketleri", {"jeton": j, "eposta": f"k{i}@seo4s.test"}, ip="203.0.113.99")).status_code == 200
    y = await _epostala(istemci, "meta-etiketleri", {"jeton": "x", "eposta": "k9@seo4s.test"}, ip="203.0.113.99")
    assert y.status_code == 429 and y.json()["detail"]["kod"] == "sinir_eposta"
    # Sayaç anahtarlarında ham e-posta da ham IP de yok (özet).
    from models.hiz_sayaclari import HizSayaclari

    anahtarlar = " ".join(r[0] for r in (await db_oturumu.execute(select(HizSayaclari.anahtar))).all())
    assert "kurban@seo4s.test" not in anahtarlar and "203.0.113.99" not in anahtarlar


async def test_eposta_gonderilemezse_502_aday_yok_jeton_kalir(istemci, ag, db_oturumu, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")

    async def basarisiz(alici, baslik, govde, ek=None):
        return "failed", "resend 500"

    from services import notify

    monkeypatch.setattr(notify, "_eposta_gonder", basarisiz)
    ag.ekle("https://ornek.com/", 200, HTML, IYI_META)
    _s, jeton = await _calistir_jeton(istemci)
    y = await _epostala(istemci, "meta-etiketleri", {"jeton": jeton, "eposta": "dusen@seo4s.test"})
    assert y.status_code == 502 and y.json()["detail"]["kod"] == "eposta_gonderilemedi"
    assert await _aday(db_oturumu, "dusen@seo4s.test") == []
    assert araclar.onbellek.al(jeton, "meta-etiketleri") is not None


def test_sonuc_onbellegi_suresi_ve_tavani():
    saat = [1000.0]
    o = araclar.SonucOnbellegi(sure=60, tavan=3, saat=lambda: saat[0])
    j1 = o.koy("meta-etiketleri", {"a": 1})
    assert o.al(j1, "meta-etiketleri") == {"a": 1} and o.al(j1, "open-graph") is None
    saat[0] += 61
    assert o.al(j1, "meta-etiketleri") is None and len(o) == 0
    jetonlar = [o.koy("robots-txt", {"i": i}) for i in range(4)]
    assert len(o) == 3 and o.al(jetonlar[0], "robots-txt") is None and o.al(jetonlar[3], "robots-txt") == {"i": 3}
    assert len(set(jetonlar)) == 4 and all(len(j) >= 20 for j in jetonlar)


@pytest.mark.parametrize("dil", ("tr", "en", "de", "ru", "zh", "hi", "ar"))
def test_eposta_icerigi_yedi_dilde(dil):
    sonuc = {
        "arac": "kelime-yogunlugu", "url": "https://ornek.com/a", "son_url": "https://ornek.com/a", "durum": 200, "puan": 72,
        "ozet": {"hata": 1, "uyari": 1, "bilgi": 1, "iyi": 2},
        "bulgular": [
            {"kontrol": "hedef_kelime", "kod": "hedef_yok", "seviye": "hata", "deger": "<b>seo</b>"},
            {"kontrol": "anahtar_yogunlugu", "kod": "anahtar_asiri", "seviye": "uyari", "deger": {"kelime": "x" * 200, "yuzde": 7.5}},
            {"kontrol": "hedef_konum", "kod": "hedef_url_yok", "seviye": "bilgi", "deger": "seo"},
            {"kontrol": "icerik_uzunlugu", "kod": "kelime_iyi", "seviye": "iyi", "deger": 900},
        ],
    }
    e = araclar.eposta_icerigi(sonuc, dil, "Ad <i>Soyad</i>")
    metin = araclar.metinler()[dil]
    assert metin["arac"]["kelime-yogunlugu"] in e["konu"] and "ornek.com" in e["konu"]
    assert "{{" not in e["metin"] and "{{" not in e["html"] and "{" not in e["konu"]
    # Sorunlar (hata + uyarı) cümleyle; başarılılar listelenmiyor; hedefin metni kısaltılmış ve kaçışlı.
    assert metin["kontrol"]["hedef_kelime"] in e["metin"] and metin["kontrol"]["anahtar_yogunlugu"] in e["metin"]
    assert "x" * 81 not in e["metin"] and "<b>" not in e["html"] and "&lt;b&gt;seo&lt;/b&gt;" in e["html"]
    assert "<i>Soyad</i>" not in e["html"] and "72/100" in e["metin"]
    onek = "" if dil == "tr" else f"/{dil}"
    assert f"https://mehmetkuru.dev{onek}/seo-araclari/kelime-yogunlugu/?url=" in e["metin"]
    assert (f'dir="rtl"' in e["html"]) == (dil == "ar")


def test_eposta_metin_dosyasi_guncel():
    """Ön yüz metinleri değiştiyse: `python -m scripts.seo_arac_metinleri` ile dosyayı yeniden üretin."""
    from scripts.seo_arac_metinleri import HEDEF, metin

    assert HEDEF == araclar.METIN_DOSYASI
    assert HEDEF.read_text("utf-8") == metin()


# --------------------------------------------------------------------------
# Yönetici özeti: araç başına günlük kullanım, e-posta/aday dönüşümü, tam analiz geçişi
# --------------------------------------------------------------------------
async def test_yonetici_ozeti(istemci, ag, db_oturumu, yonetici_basligi, musteri_basligi, monkeypatch, sahte_eposta):
    ag.ekle("https://ornek.com/", 200, HTML, IYI_META)
    _s, jeton = await _calistir_jeton(istemci)
    assert (await _arac(istemci, "open-graph", "ornek.com")).status_code == 200
    assert (await _arac(istemci, "meta-etiketleri", "ftp://ornek.com/")).status_code == 400  # biçim hatası: sayılmaz
    assert (await _arac(istemci, "meta-etiketleri", "http://10.0.0.1/")).status_code == 400  # SSRF reddi: hatalı sayılır
    assert (await _arac(istemci, "meta-etiketleri", "bulunamaz.yok")).status_code == 422  # çalıştı ama hatalı bitti
    assert (await _epostala(istemci, "meta-etiketleri", {"jeton": jeton, "eposta": "ozet@seo4s.test"})).status_code == 200

    # "Sitenin tam analizini al" → mevcut site analizi akışı (araç adıyla); e-posta bırakan aday.
    async def sahte_ssl(host):
        return datetime.now(timezone.utc) + timedelta(days=90), None

    monkeypatch.setattr(motor, "_ssl_bitis", sahte_ssl)
    ag.ekle("https://ozet-4s.com/", 200, HTML, IYI_META)
    analiz = await istemci.post("/api/v1/site-analizi", json={"url": "ozet-4s.com", "arac": "meta-etiketleri"},
                                headers={"x-forwarded-for": "198.51.100.207"})
    assert analiz.status_code == 200, analiz.text
    kimlik = analiz.json()["id"]
    tam = await istemci.post(f"/api/v1/site-analizi/{kimlik}/tam-rapor", json={"eposta": "tam@seo4s.test", "dil": "tr"})
    assert tam.status_code == 200
    kayit = (await db_oturumu.execute(select(Site_analyses).where(Site_analyses.id == kimlik))).scalar_one()
    assert kayit.arac == "meta-etiketleri" and kayit.inquiry_id
    talep = (await db_oturumu.execute(select(Inquiries).where(Inquiries.id == kayit.inquiry_id))).scalar_one()
    assert "ücretsiz SEO aracı (meta-etiketleri)" in talep.message
    # Bilinmeyen araç adı yok sayılır; e-posta bırakılmayan analiz yalnız "tam analiz" sayılır.
    diger = await istemci.post("/api/v1/site-analizi", json={"url": "ozet-4s.com", "arac": "<script>"},
                               headers={"x-forwarded-for": "198.51.100.208"})
    assert (await db_oturumu.execute(select(Site_analyses.arac).where(Site_analyses.id == diger.json()["id"]))).scalar() is None
    await istemci.post("/api/v1/site-analizi", json={"url": "ozet-4s.com", "arac": "kelime-yogunlugu"},
                       headers={"x-forwarded-for": "198.51.100.209"})

    assert (await istemci.get(f"{UC}/yonetim/ozet")).status_code in (401, 403)
    assert (await istemci.get(f"{UC}/yonetim/ozet", headers=musteri_basligi())).status_code == 403
    y = await istemci.get(f"{UC}/yonetim/ozet?gun=7", headers=yonetici_basligi)
    assert y.status_code == 200
    o = y.json()
    satir = {s["arac"]: s for s in o["araclar"]}
    assert [s["arac"] for s in o["araclar"]] == list(araclar.ARACLAR)
    assert len(o["gunler"]) == 7 and o["gunler"][-1] == datetime.now(timezone.utc).strftime("%Y-%m-%d")
    m = satir["meta-etiketleri"]
    assert (m["kullanim"], m["hata"], m["eposta"], m["aday"], m["tam_analiz"], m["tam_analiz_aday"]) == (3, 2, 1, 1, 1, 1)
    assert m["gunluk"] == [0] * 6 + [3] and satir["open-graph"]["gunluk"][-1] == 1
    assert satir["kelime-yogunlugu"]["tam_analiz"] == 1 and satir["kelime-yogunlugu"]["tam_analiz_aday"] == 0
    assert o["toplam"] == {"kullanim": 4, "hata": 2, "eposta": 1, "aday": 1, "tam_analiz": 2, "tam_analiz_aday": 1}
    assert o["gunluk"][-1] == 4

    # Yönetici listesinde aracın adı görünür.
    liste = (await istemci.get("/api/v1/site-analizi/yonetim", headers=yonetici_basligi)).json()
    assert any(s.get("arac") == "meta-etiketleri" for s in liste["items"])


async def test_pazarlama_izni_sorusu_site_ayarina_bagli(istemci, ag, db_oturumu, sahte_eposta):
    from models.site_settings import Site_settings

    ag.ekle("https://ornek.com/", 200, HTML, IYI_META)
    db_oturumu.add(Site_settings(setting_key=pazarlama_izni.SITE_ANALIZI_AYARI, setting_value="1"))
    await db_oturumu.commit()
    try:
        g = (await _arac(istemci, "meta-etiketleri", "ornek.com")).json()
        assert g["eposta"]["pazarlama_izni_sor"] is True
        # Panelde e-posta kanalı kapalıysa seçenek de kapalı.
        db_oturumu.add(Site_settings(setting_key="notify_email", setting_value="0"))
        await db_oturumu.commit()
        g = (await _arac(istemci, "meta-etiketleri", "ornek.com")).json()
        assert g["eposta"] == {"acik": False, "jeton": None, "pazarlama_izni_sor": False}
    finally:
        await db_oturumu.execute(delete(Site_settings).where(
            Site_settings.setting_key.in_([pazarlama_izni.SITE_ANALIZI_AYARI, "notify_email"])))
        await db_oturumu.commit()


# --------------------------------------------------------------------------
# Ön yüz ile eşleşme: araç listesi, 7 dilde metinler, pazarlama izni metni
# --------------------------------------------------------------------------
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")


def _ek(paket: str, dil: str) -> dict:
    return json.loads((ON_YUZ / "src" / "i18n" / "ek" / paket / f"{dil}.json").read_text("utf-8"))[paket]


def test_on_yuz_arac_listesi_ayni():
    veri = (ON_YUZ / "prerender" / "seo-araclari-veri.js").read_text("utf-8")
    slugs = re.findall(r"slug:\s*'([a-z0-9-]+)'", veri)
    assert tuple(slugs) == araclar.ARACLAR


@pytest.mark.parametrize("dil", DILLER)
def test_yedi_dilde_metinler_tam(dil):
    sayfa = _ek("seoAraclari", dil)
    sonuc = _ek("seoAracSonuc", dil)
    veri = (ON_YUZ / "prerender" / "seo-araclari-veri.js").read_text("utf-8")
    anahtarlar = dict((slug, a) for a, slug in re.findall(r"anahtar:\s*'(\w+)',\s*slug:\s*'([a-z0-9-]+)'", veri))
    assert set(anahtarlar) == set(araclar.ARACLAR) and anahtarlar == araclar.ARAC_ANAHTARI
    for slug in araclar.ARACLAR:
        arac = sayfa["arac"][anahtarlar[slug]]
        for alan in ("ad", "kisa", "giris", "seoBaslik", "seoAciklama"):
            assert arac.get(alan), (dil, slug, alan)
        assert len(arac["sss"]) >= 2 and all(s["s"] and s["c"] for s in arac["sss"])
        assert len(arac["neler"]) >= 3
    kaynak = Path(araclar.__file__).read_text("utf-8")
    kontroller = set(re.findall(r'\.ekle\(\s*"([a-z0-9_]+)",', kaynak))
    kodlar = set(re.findall(r'\.ekle\(\s*"[a-z0-9_]+",\s*"([a-z0-9_]+)"', kaynak))
    # Dinamik kodlar (sözlükten seçilenler) da metinde olmalı.
    kodlar |= {"ssl_suresi_gecmis", "ssl_kendinden_imzali", "zincir_eksik", "ssl_ad_uyusmuyor", "ssl_gecersiz",
               "dtd_reddedildi", "sitemap_kok_hatali", "sitemap_xml_hatasi", "sitemap_dizini", "sitemap_bicim_iyi"}
    for k in kontroller:
        for alan in ("ad", "neden", "duzelt"):
            assert sonuc["kontrol"][k][alan], (dil, k, alan)
    eksik = sorted(k for k in kodlar if not sonuc["bulgu"].get(k))
    assert not eksik, (dil, eksik)
    # "Sonucu e-postayla gönder" formundaki pazarlama izni metni sunucudaki izin metniyle aynı (Faz 4G).
    assert sayfa["eposta"]["pazarlama"] == pazarlama_izni.METINLER[dil]
    for alan in ("baslik", "aciklama", "ad", "eposta", "istegeBagli", "gonder", "gonderiliyor", "basarili", "basariliMetin"):
        assert sayfa["eposta"][alan], (dil, alan)
    assert "{{alan}}" in sayfa["tamAnaliz"]["metin"] and sayfa["tamAnaliz"]["dugme"]
    # Uçların döndürdüğü her hata kodunun metni var.
    for kod in ("adres_gecersiz", "adres_yasak", "cozumlenemedi", "ulasilamadi", "cok_yonlendirme", "zaman_asimi",
                "ajan_gecersiz", "kelime_gecersiz", "sinir_dakika", "sinir_gun", "sinir_eposta", "eposta_gecersiz",
                "sonuc_suresi_doldu", "eposta_kapali", "eposta_gonderilemedi", "arac_yok", "beklenmedik", "ag", "genel"):
        assert sayfa["hata"].get(kod), (dil, kod)
    # Kelime aracının görünüm metinleri ve CRM'de yeni kaynağın etiketi.
    for alan in ("kelimeler", "toplam", "enSik", "ikililer", "ucluler", "hedef", "hedefOzet", "konumTitle", "konumUrl", "var", "yok"):
        assert sonuc["veri"]["kelime"][alan], (dil, alan)
    crm = _ek("crm", dil)
    assert crm["kaynak"]["seo_araci"] and "{{arac}}" in crm["pazarlama"]["kaynakSeoAraci"]
    # Ham İngilizce kopya değil: en dışındaki dillerde araç adları İngilizceden farklı.
    if dil not in ("en",):
        en = _ek("seoAraclari", "en")
        assert sayfa["arac"]["meta"]["giris"] != en["arac"]["meta"]["giris"]
