"""Site Analiz Raporu uçları ve motoru.

Dış ağa ÇIKILMIYOR:
* site istekleri `httpx.MockTransport` ile sahte bir "internete" gidiyor,
* DNS çözümlemesi, SSL bitiş denetimi ve PageSpeed çağrısı sahte.
"""

import gzip
import json
import socket
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import delete, func, select, update

from models.inquiries import Inquiries
from models.notifications import Notifications
from models.site_analyses import Site_analyses
from services import site_analizi as motor
from services import site_inceleme as si

UC = "/api/v1/site-analizi"
GENEL_IP = "93.184.216.34"

KELIMELER = " ".join(["kelime"] * 400)
ANA_HTML = f"""<!doctype html><html lang="tr"><head>
<title>Örnek Site — kaliteli web hizmetleri ve danışmanlık</title>
<meta name="description" content="Örnek Site, işletmeler için hızlı ve ölçülebilir web siteleri kurar; bakım, SEO ve ölçümleme hizmetleri sunar.">
<link rel="canonical" href="https://ornek.com/">
<link rel="alternate" hreflang="en" href="https://ornek.com/en">
<script type="application/ld+json">{{"@type":"Organization"}}</script>
</head><body><h1>Örnek Site</h1><p>{KELIMELER}</p>
<img src="a.png" alt="a"><img src="b.png"><img src="c.png">
<a href="/hakkinda">Hakkında</a><a href="/kirik">Kırık</a><a href="/blog/">Blog</a>
<a href="https://baska-site.com/">Dış</a><a href="mailto:a@b.com">E-posta</a>
</body></html>"""

ALT_HTML = """<html lang="tr"><head><title>Hakkında — Örnek Site hakkında bilgiler</title></head>
<body><h1>Hakkında</h1><a href="/">Ana sayfa</a></body></html>"""

ROBOTS = """User-agent: *
Allow: /

User-agent: GPTBot
Disallow: /

Sitemap: https://ornek.com/sitemap.xml
"""

SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://ornek.com/</loc></url>
<url><loc>https://ornek.com/hakkinda</loc></url>
<url><loc>https://ornek.com/blog/</loc></url>
<url><loc>https://baska-site.com/x</loc></url>
</urlset>"""

GUVENLI_BASLIKLAR = {
    "strict-transport-security": "max-age=31536000",
    "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "cache-control": "public, max-age=300",
}


def _pagespeed_json(puan: float) -> dict:
    return {
        "lighthouseResult": {
            "categories": {"performance": {"score": puan}},
            "audits": {
                "largest-contentful-paint": {"numericValue": 2100.0},
                "cumulative-layout-shift": {"numericValue": 0.02},
                "total-blocking-time": {"numericValue": 350.0},
            },
        }
    }


class SahteAg:
    """Sahte internet: adres → (durum, başlıklar, gövde)."""

    def __init__(self):
        self.istekler: list[tuple[str, str]] = []
        self.yollar: dict[str, tuple[int, dict, bytes]] = {}
        self.dns: dict[str, list[str]] = {}
        self.dns_hatasi: set[str] = set()
        self.baglanti_hatasi: set[str] = set()
        self.pagespeed = {"mobile": 0.8, "desktop": 0.9}
        self.pagespeed_hatasi = False

    def ekle(self, url, durum=200, basliklar=None, govde="", sikistir=False):
        ham = govde.encode("utf-8") if isinstance(govde, str) else govde
        b = dict(basliklar or {})
        if sikistir:
            ham = gzip.compress(ham)
            b["content-encoding"] = "gzip"
        self.yollar[url] = (durum, b, ham)

    def isle(self, istek: httpx.Request) -> httpx.Response:
        adres = str(istek.url)
        self.istekler.append((istek.method, adres))
        if istek.url.host in self.baglanti_hatasi:
            raise httpx.ConnectError("bağlantı reddedildi", request=istek)
        anahtar = adres.split("?", 1)[0]
        kayit = self.yollar.get(anahtar)
        if kayit is None:
            # Tanımsız site: yalın bir ana sayfa, geri kalanı 404.
            if istek.url.path == "/" and istek.url.host not in {"ornek.com"}:
                return httpx.Response(200, headers={"content-type": "text/html"},
                                      content=b"<html><title>x</title><h1>x</h1></html>")
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
    html = {"content-type": "text/html; charset=utf-8"}
    ag.ekle("https://ornek.com/", 200, {**html, **GUVENLI_BASLIKLAR}, ANA_HTML, sikistir=True)
    ag.ekle("https://ornek.com/hakkinda", 200, html, ALT_HTML)
    ag.ekle("https://ornek.com/blog/", 200, html, ALT_HTML.replace("Hakkında", "Blog"))
    ag.ekle("https://ornek.com/kirik", 404, html, "yok")
    ag.ekle("https://ornek.com/robots.txt", 200, {"content-type": "text/plain"}, ROBOTS)
    ag.ekle("https://ornek.com/sitemap.xml", 200, {"content-type": "application/xml"}, SITEMAP)
    ag.ekle("http://ornek.com/", 301, {"location": "https://ornek.com/"})

    async def sahte_dns(host, port):
        if host in ag.dns_hatasi:
            raise socket.gaierror("çözülemedi")
        return ag.dns.get(host, [GENEL_IP])

    async def sahte_ssl(host):
        return datetime.now(timezone.utc) + timedelta(days=90), None

    async def sahte_pagespeed(url, strateji):
        if ag.pagespeed_hatasi:
            raise httpx.HTTPStatusError(
                "kota", request=httpx.Request("GET", url), response=httpx.Response(429)
            )
        return _pagespeed_json(ag.pagespeed[strateji])

    monkeypatch.setattr(motor, "_tasiyici_fabrikasi", lambda: httpx.MockTransport(ag.isle))
    monkeypatch.setattr(motor, "_dns_cozumle", sahte_dns)
    monkeypatch.setattr(motor, "_ssl_bitis", sahte_ssl)
    monkeypatch.setattr(motor, "_pagespeed_cagir", sahte_pagespeed)

    # Her test temiz tabloyla başlasın (sınır sayımı tablodan yapılıyor).
    for model in (Site_analyses, Inquiries, Notifications):
        await db_oturumu.execute(delete(model))
    await db_oturumu.commit()
    return ag


async def _analiz(istemci, url="ornek.com", ip="198.51.100.7"):
    return await istemci.post(UC, json={"url": url}, headers={"x-forwarded-for": ip})


# --------------------------------------------------------------------------
# Mutlu yol + özet
# --------------------------------------------------------------------------
async def test_ozet_yaniti_tam_ayrintiyi_icermez(istemci, ag):
    yanit = await _analiz(istemci)
    assert yanit.status_code == 200, yanit.text
    govde = yanit.json()

    assert govde["alan_adi"] == "ornek.com"
    assert govde["tam_rapor_icin_eposta"] is True
    assert isinstance(govde["puan"], int) and 0 <= govde["puan"] <= 100
    assert [b["anahtar"] for b in govde["bolumler"]] == ["hiz", "seo", "icerik", "teknik", "guvenlik", "ai"]
    for bolum in govde["bolumler"]:
        assert len(bolum["bulgular"]) <= 3
        for bulgu in bolum["bulgular"]:
            assert set(bulgu) <= {"kod", "deger", "seviye"}
    # Tam ayrıntı yok: sayfa listesi, kırık bağlantılar, jeton dönmüyor.
    for yasak in ("ayrinti", "sayfalar", "kirik_baglantilar", "jeton", "eposta"):
        assert yasak not in govde
    assert "hakkinda" not in yanit.text
    # Dış bağlantıya ve mailto'ya gidilmedi.
    assert not ag.istek_yapildi_mi("baska-site.com")


async def test_tam_raporda_bulgular_dogru(istemci, ag, yonetici_basligi):
    kimlik = (await _analiz(istemci)).json()["id"]
    rapor = (await istemci.get(f"{UC}/yonetim/{kimlik}", headers=yonetici_basligi)).json()
    bulgu = {b["anahtar"]: {x["kod"]: x.get("deger") for x in b["bulgular"]} for b in rapor["bolumler"]}

    assert rapor["bolumler"][0]["puan"] == 85  # (80 + 90) / 2
    assert bulgu["hiz"]["tbt"] == 350
    assert bulgu["seo"]["sitemap_var"] == 4
    assert "title_iyi" in bulgu["seo"] and "aciklama_iyi" in bulgu["seo"]
    assert bulgu["icerik"]["kirik_baglanti"] == 1
    assert bulgu["icerik"]["alt_yok"] == 2
    assert "kelime_sayisi" in bulgu["icerik"]
    assert "https_var" in bulgu["teknik"] and "sikistirma_var" in bulgu["teknik"]
    assert "http_yonlendirme_yok" not in bulgu["teknik"]
    assert "guvenlik_basliklari_tamam" in bulgu["guvenlik"]
    assert bulgu["guvenlik"]["ssl_gecerli"] >= 88
    assert bulgu["ai"]["ai_bot_engelli"] == "GPTBot"
    assert "llms_txt_yok" in bulgu["ai"] and "yapisal_veri_var" in bulgu["ai"]

    kiriklar = rapor["ayrinti"]["kirik_baglantilar"]
    assert [k["url"] for k in kiriklar] == ["https://ornek.com/kirik"]
    assert {s["url"] for s in rapor["ayrinti"]["sayfalar"]} == {
        "https://ornek.com/", "https://ornek.com/hakkinda", "https://ornek.com/blog/",
    }


# --------------------------------------------------------------------------
# SSRF
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "adres",
    [
        "http://127.0.0.1/",
        "http://10.1.2.3/",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/",
        "http://[::1]/",
        "http://[::ffff:10.0.0.1]/",
        "http://0.0.0.0/",
        "http://sunucu.internal/",
        "http://yazici.local/",
        "http://ic.ornek.com/",       # özel IP'ye çözümlenen alan
        "http://karisik.ornek.com/",  # biri genel biri özel
    ],
)
async def test_ssrf_ic_adresler_reddedilir(istemci, ag, adres):
    ag.dns["ic.ornek.com"] = ["10.0.0.7"]
    ag.dns["karisik.ornek.com"] = [GENEL_IP, "192.168.1.5"]
    yanit = await _analiz(istemci, adres)
    assert yanit.status_code == 400, yanit.text
    assert yanit.json()["detail"]["kod"] == "adres_yasak"
    assert ag.istekler == []  # tek bir istek bile gitmedi


@pytest.mark.parametrize(
    "adres",
    [
        "ftp://ornek.com/",
        "http://ornek.com:8080/",
        "http://kullanici:parola@ornek.com/",
        "javascript:alert(1)",
        "",
        "sadece-kelime",
    ],
)
async def test_gecersiz_adresler(istemci, ag, adres):
    yanit = await _analiz(istemci, adres)
    assert yanit.status_code == 400
    assert yanit.json()["detail"]["kod"] == "adres_gecersiz"
    assert ag.istekler == []


@pytest.mark.parametrize(
    "hedef",
    ["http://10.0.0.1/admin", "http://127.0.0.1:80/", "http://169.254.169.254/", "http://localhost/"],
)
async def test_ozel_ipye_yonlendirme_reddedilir(istemci, ag, hedef):
    ag.ekle("https://yonlendiren.com/", 302, {"location": hedef})
    yanit = await _analiz(istemci, "https://yonlendiren.com/")
    assert yanit.status_code == 400
    assert yanit.json()["detail"]["kod"] == "adres_yasak"
    assert ag.istekler == [("GET", "https://yonlendiren.com/")]


async def test_dns_ile_ozele_donen_yonlendirme_reddedilir(istemci, ag):
    ag.dns["gizli.ornek.com"] = ["172.16.0.9"]
    ag.ekle("https://yonlendiren.com/", 301, {"location": "https://gizli.ornek.com/"})
    yanit = await _analiz(istemci, "https://yonlendiren.com/")
    assert yanit.json()["detail"]["kod"] == "adres_yasak"
    assert not ag.istek_yapildi_mi("gizli.ornek.com")


async def test_cok_yonlendirme(istemci, ag):
    for i in range(7):
        ag.ekle(f"https://dongu.com/{i}", 302, {"location": f"/{i + 1}"})
    yanit = await _analiz(istemci, "https://dongu.com/0")
    assert yanit.status_code == 422
    assert yanit.json()["detail"]["kod"] == "cok_yonlendirme"
    assert len(ag.istekler) == 6  # ilk istek + 5 yönlendirme


async def test_ulasilamayan_site(istemci, ag, db_oturumu):
    ag.baglanti_hatasi.add("kapali.com")
    yanit = await _analiz(istemci, "kapali.com")
    assert yanit.status_code == 422
    assert yanit.json()["detail"]["kod"] == "ulasilamadi"
    kayit = (await db_oturumu.execute(select(Site_analyses))).scalar_one()
    assert kayit.durum == "hata" and kayit.hata_kodu == "ulasilamadi"


async def test_cozumlenemeyen_alan(istemci, ag):
    ag.dns_hatasi.add("yok-boyle-bir-alan.com")
    yanit = await _analiz(istemci, "yok-boyle-bir-alan.com")
    assert yanit.status_code == 422
    assert yanit.json()["detail"]["kod"] == "cozumlenemedi"


# --------------------------------------------------------------------------
# Sınırlar
# --------------------------------------------------------------------------
async def test_ayni_alan_gunde_uc(istemci, ag):
    for i in range(3):
        yanit = await _analiz(istemci, "https://www.sinir.com/", ip=f"203.0.113.{i + 1}")
        assert yanit.status_code == 200, yanit.text
    # www'lu ve www'suz aynı alan sayılıyor.
    yanit = await _analiz(istemci, "sinir.com", ip="203.0.113.99")
    assert yanit.status_code == 429
    assert yanit.json()["detail"] == {"kod": "sinir_alan"}


async def test_ayni_ip_saatte_bes(istemci, ag):
    for i in range(5):
        yanit = await _analiz(istemci, f"site{i}.com", ip="198.51.100.50")
        assert yanit.status_code == 200, yanit.text
    yanit = await _analiz(istemci, "site-alti.com", ip="198.51.100.50")
    assert yanit.status_code == 429
    assert yanit.json()["detail"] == {"kod": "sinir_ip"}
    # Başka IP etkilenmiyor.
    assert (await _analiz(istemci, "site-alti.com", ip="198.51.100.51")).status_code == 200


async def test_cf_connecting_ip_once(istemci, ag):
    # X-Forwarded-For'u değiştirerek IP sınırı aşılamıyor.
    for i in range(5):
        yanit = await istemci.post(
            UC, json={"url": f"cf{i}.com"},
            headers={"cf-connecting-ip": "192.0.2.10", "x-forwarded-for": f"10.9.9.{i}"},
        )
        assert yanit.status_code == 200
    yanit = await istemci.post(
        UC, json={"url": "cf-son.com"},
        headers={"cf-connecting-ip": "192.0.2.10", "x-forwarded-for": "10.9.9.200"},
    )
    assert yanit.status_code == 429


async def test_ham_ip_saklanmaz(istemci, ag, db_oturumu):
    await _analiz(istemci, ip="198.51.100.77")
    kayit = (await db_oturumu.execute(select(Site_analyses))).scalar_one()
    assert "198.51.100.77" not in (kayit.ip_ozeti or "")
    assert len(kayit.ip_ozeti) == 64


# --------------------------------------------------------------------------
# Tam rapor + aday
# --------------------------------------------------------------------------
async def test_tam_rapor_kvkk_kutusu_artik_zorunlu_degil(istemci, ag, db_oturumu):
    """Faz 4G: rapor isteği aydınlatmayla işleniyor; onay kutusu ön koşul değil."""
    kimlik = (await _analiz(istemci)).json()["id"]
    yanit = await istemci.post(f"{UC}/{kimlik}/tam-rapor", json={"eposta": "a@ornek.com"})
    assert yanit.status_code == 200, yanit.text
    kayit = (await db_oturumu.execute(select(Site_analyses))).scalar_one()
    assert kayit.eposta == "a@ornek.com" and kayit.kvkk_onay is False
    # Ayar kapalıyken (varsayılan) pazarlama izni gönderilse de kaydedilmez.
    assert not kayit.pazarlama_izni and kayit.pazarlama_izni_at is None
    # Eski istemci `kvkk_onay: false` gönderse de çalışır (geriye uyumlu).
    yanit = await istemci.post(
        f"{UC}/{kimlik}/tam-rapor", json={"eposta": "a@ornek.com", "kvkk_onay": False}
    )
    assert yanit.status_code == 200


async def _pazarlama_ayari(db, deger):
    from models.site_settings import Site_settings
    from services.pazarlama_izni import SITE_ANALIZI_AYARI

    await db.execute(delete(Site_settings).where(Site_settings.setting_key == SITE_ANALIZI_AYARI))
    if deger is not None:
        db.add(Site_settings(setting_key=SITE_ANALIZI_AYARI, setting_value=deger, group_name="kvkk", label=SITE_ANALIZI_AYARI))
    await db.commit()


async def test_tam_rapor_pazarlama_izni_ayar_aciksa_kaydedilir(istemci, ag, db_oturumu, yonetici_basligi):
    from models.crm import CrmAdaylari, CrmBagliKayitlar

    # `ag` talepleri siliyor; SQLite kimlikleri yeniden kullanınca eski CRM bağı
    # "zaten işlendi" sanılmasın (üretimde kimlik tekrar etmiyor).
    await db_oturumu.execute(delete(CrmBagliKayitlar).where(CrmBagliKayitlar.tablo == "inquiries"))
    await db_oturumu.execute(delete(CrmAdaylari).where(CrmAdaylari.email == "izinli@ornek-firma.com"))
    await db_oturumu.commit()
    try:
        # Ayar kapalı: analiz yanıtı kutuyu istemiyor.
        await _pazarlama_ayari(db_oturumu, None)
        assert (await _analiz(istemci)).json()["pazarlama_izni_sor"] is False

        await _pazarlama_ayari(db_oturumu, "1")
        ozet = (await _analiz(istemci, url="ornek.com", ip="198.51.100.8")).json()
        assert ozet["pazarlama_izni_sor"] is True

        # "true" (metin) izin sayılmaz; yalnız JSON true.
        yanit = await istemci.post(
            f"{UC}/{ozet['id']}/tam-rapor",
            json={"eposta": "izinli@ornek-firma.com", "pazarlama_izni": "true", "dil": "en"},
        )
        assert yanit.status_code == 200
        kayit = (await db_oturumu.execute(select(Site_analyses).where(Site_analyses.id == ozet["id"]))).scalar_one()
        assert not kayit.pazarlama_izni

        # Az sonra (yeniden e-posta göndermeden) izin verilirse yine kaydedilir.
        yanit = await istemci.post(
            f"{UC}/{ozet['id']}/tam-rapor",
            json={"eposta": "izinli@ornek-firma.com", "pazarlama_izni": True, "dil": "en"},
        )
        assert yanit.status_code == 200
        db_oturumu.expire_all()
        kayit = (await db_oturumu.execute(select(Site_analyses).where(Site_analyses.id == ozet["id"]))).scalar_one()
        assert kayit.pazarlama_izni is True and kayit.pazarlama_izni_at is not None
        assert kayit.pazarlama_metin_surumu == "1/en"

        # CRM adayında da görünür (kaynak: site analizi).
        aday = (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.email == "izinli@ornek-firma.com"))).scalar_one()
        assert aday.pazarlama_izni_kaynak == f"site_analizi:{ozet['id']}" and aday.pazarlama_metin_surumu == "1/en"
        d = (await istemci.get(f"/api/v1/crm/adaylar/{aday.id}", headers=yonetici_basligi)).json()["aday"]
        assert d["pazarlama_izni"] is True and d["pazarlama_izni_kaynak"] == f"site_analizi:{ozet['id']}"

        # Yönetici raporunda izin alanları var.
        r = (await istemci.get(f"{UC}/yonetim/{ozet['id']}", headers=yonetici_basligi)).json()
        assert r["pazarlama_izni"] is True and r["pazarlama_metin_surumu"] == "1/en"
    finally:
        await _pazarlama_ayari(db_oturumu, None)


async def test_tam_rapor_eposta_bicimi(istemci, ag):
    kimlik = (await _analiz(istemci)).json()["id"]
    for kotu in ("", "ornek.com", "a@b", "a b@c.com", "x@y.z"):
        yanit = await istemci.post(
            f"{UC}/{kimlik}/tam-rapor", json={"eposta": kotu, "kvkk_onay": True}
        )
        assert yanit.status_code == 400, kotu
        assert yanit.json()["detail"]["kod"] == "eposta_gecersiz"


async def test_tam_rapor_aday_acar_ve_idempotent(istemci, ag, db_oturumu):
    kimlik = (await _analiz(istemci)).json()["id"]
    govde = {"eposta": "Musteri@Ornek.com", "ad": "Ayşe", "kvkk_onay": True}

    yanit = await istemci.post(f"{UC}/{kimlik}/tam-rapor", json=govde)
    assert yanit.status_code == 200
    assert yanit.json() == {"gonderildi": True}  # jeton yanıtta yok

    adaylar = (await db_oturumu.execute(select(Inquiries))).scalars().all()
    assert len(adaylar) == 1
    assert adaylar[0].source == "site_analizi"
    assert adaylar[0].subject == "Site analizi: ornek.com"
    assert adaylar[0].email == "musteri@ornek.com"

    kayit = (await db_oturumu.execute(select(Site_analyses))).scalar_one()
    assert kayit.eposta == "musteri@ornek.com" and kayit.kvkk_onay is True
    assert kayit.inquiry_id == adaylar[0].id
    ilk_jeton = kayit.jeton
    assert ilk_jeton and len(ilk_jeton) >= 16

    # Müşteriye bağlantı, yöneticiye panel bildirimi.
    bildirimler = (await db_oturumu.execute(select(Notifications))).scalars().all()
    musteriye = [b for b in bildirimler if b.recipient_email == "musteri@ornek.com" and b.channel == "inapp"]
    assert musteriye and musteriye[0].link == f"https://mehmetkuru.dev/rapor/{ilk_jeton}"
    assert ilk_jeton in (musteriye[0].body or "")
    assert any(b.recipient_role == "admin" and b.event_type == "site_analizi_aday" for b in bildirimler)

    # İkinci çağrı: yeni aday yok, jeton aynı.
    yanit = await istemci.post(f"{UC}/{kimlik}/tam-rapor", json=govde)
    assert yanit.status_code == 200
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(func.count(Inquiries.id)))).scalar() == 1
    kayit = (await db_oturumu.execute(select(Site_analyses))).scalar_one()
    assert kayit.jeton == ilk_jeton

    # Başka adres bu raporu kendine çeviremez.
    yanit = await istemci.post(
        f"{UC}/{kimlik}/tam-rapor", json={"eposta": "baskasi@ornek.com", "kvkk_onay": True}
    )
    assert yanit.status_code == 409


async def test_rapor_jetonu_ve_suresi(istemci, ag, db_oturumu):
    kimlik = (await _analiz(istemci)).json()["id"]
    await istemci.post(f"{UC}/{kimlik}/tam-rapor", json={"eposta": "r@ornek.com", "kvkk_onay": True})
    jeton = (await db_oturumu.execute(select(Site_analyses.jeton))).scalar_one()

    yanit = await istemci.get(f"{UC}/rapor/{jeton}")
    assert yanit.status_code == 200
    rapor = yanit.json()
    assert rapor["ayrinti"]["kirik_baglantilar"]
    assert "eposta" not in rapor and "ip_ozeti" not in rapor

    assert (await istemci.get(f"{UC}/rapor/olmayan-jeton")).status_code == 404

    await db_oturumu.execute(
        update(Site_analyses).values(jeton_son=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db_oturumu.commit()
    yanit = await istemci.get(f"{UC}/rapor/{jeton}")
    assert yanit.status_code == 410
    assert yanit.json()["detail"]["kod"] == "sure_doldu"


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
async def test_yonetici_uclari_musteriye_kapali(istemci, ag, musteri_basligi):
    kimlik = (await _analiz(istemci)).json()["id"]
    for adres in (f"{UC}/yonetim", f"{UC}/yonetim/{kimlik}"):
        assert (await istemci.get(adres, headers=musteri_basligi())).status_code == 403
        assert (await istemci.get(adres)).status_code == 403


async def test_yonetici_listesi_ve_filtre(istemci, ag, yonetici_basligi):
    ilk = (await _analiz(istemci, "ornek.com")).json()["id"]
    await _analiz(istemci, "ikinci.com")
    await istemci.post(f"{UC}/{ilk}/tam-rapor", json={"eposta": "l@ornek.com", "kvkk_onay": True})

    hepsi = (await istemci.get(f"{UC}/yonetim", headers=yonetici_basligi)).json()
    assert hepsi["toplam"] == 2 and len(hepsi["items"]) == 2

    epostali = (await istemci.get(f"{UC}/yonetim?eposta_var=true", headers=yonetici_basligi)).json()
    assert epostali["toplam"] == 1
    satir = epostali["items"][0]
    assert satir["id"] == ilk and satir["eposta"] == "l@ornek.com" and satir["inquiry_id"]

    sayfali = (await istemci.get(f"{UC}/yonetim?adet=1&sayfa=2", headers=yonetici_basligi)).json()
    assert len(sayfali["items"]) == 1 and sayfali["items"][0]["id"] == ilk

    rapor = (await istemci.get(f"{UC}/yonetim/{ilk}", headers=yonetici_basligi)).json()
    assert rapor["eposta"] == "l@ornek.com" and rapor["ayrinti"]


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
async def test_musteri_oturumsuz_401(istemci, ag):
    assert (await istemci.post(f"{UC}/benim", json={"url": "ornek.com"})).status_code == 401
    assert (await istemci.get(f"{UC}/benim")).status_code == 401


async def test_musteri_yalniz_kendi_analizlerini_gorur(istemci, ag, musteri_basligi):
    a = musteri_basligi("a@musteri.com")
    b = musteri_basligi("b@musteri.com")

    yanit = await istemci.post(f"{UC}/benim", json={"url": "ornek.com"}, headers=a)
    assert yanit.status_code == 200, yanit.text
    a_rapor = yanit.json()
    assert a_rapor["ayrinti"]["sayfalar"]  # tam rapor doğrudan
    assert a_rapor["jeton"]

    b_id = (await istemci.post(f"{UC}/benim", json={"url": "baska.com"}, headers=b)).json()["id"]

    a_liste = (await istemci.get(f"{UC}/benim", headers=a)).json()
    assert [s["id"] for s in a_liste] == [a_rapor["id"]]
    assert "eposta" not in a_liste[0]

    assert (await istemci.get(f"{UC}/benim/{a_rapor['id']}", headers=a)).status_code == 200
    assert (await istemci.get(f"{UC}/benim/{b_id}", headers=a)).status_code == 404


async def test_musteri_gunluk_sinir(istemci, ag, db_oturumu, musteri_basligi, yonetici_basligi):
    simdi = datetime.now(timezone.utc)
    for i in range(10):
        db_oturumu.add(Site_analyses(
            alan_adi=f"s{i}.com", url=f"https://s{i}.com/", durum="tamam",
            eposta="yogun@musteri.com", kaynak="musteri", created_at=simdi,
        ))
    await db_oturumu.commit()
    yanit = await istemci.post(
        f"{UC}/benim", json={"url": "ornek.com"}, headers=musteri_basligi("yogun@musteri.com")
    )
    assert yanit.status_code == 429
    assert yanit.json()["detail"]["kod"] == "sinir_musteri"
    # Yöneticiye sınır yok; herkese açık alan sınırı da müşteri/yönetici ucunu etkilemiyor.
    for _ in range(4):
        yanit = await istemci.post(f"{UC}/benim", json={"url": "ornek.com"}, headers=yonetici_basligi)
        assert yanit.status_code == 200


# --------------------------------------------------------------------------
# PageSpeed
# --------------------------------------------------------------------------
async def test_pagespeed_hatasinda_genel_puan_diger_bolumlerden(istemci, ag, yonetici_basligi):
    ag.pagespeed_hatasi = True
    govde = (await _analiz(istemci)).json()
    hiz = govde["bolumler"][0]
    assert hiz["anahtar"] == "hiz"
    assert hiz["durum"] == "olculemedi" and hiz["puan"] is None
    digerleri = [b["puan"] for b in govde["bolumler"][1:]]
    assert all(isinstance(p, int) for p in digerleri)
    assert govde["puan"] == round(sum(digerleri) / len(digerleri))


# --------------------------------------------------------------------------
# Birim testleri
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "ip,beklenen",
    [
        ("93.184.216.34", True),
        ("2606:4700:10::6814:179a", True),
        ("127.0.0.1", False),
        ("10.0.0.1", False),
        ("172.16.5.4", False),
        ("192.168.0.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("224.0.0.1", False),
        ("240.0.0.1", False),
        ("::1", False),
        ("fe80::1", False),
        ("fc00::1", False),
        ("::ffff:127.0.0.1", False),
        ("2002:0a00:0001::1", False),  # 6to4 içinde 10.0.0.1
        ("::", False),
        ("bozuk", False),
    ],
)
def test_ip_global_mi(ip, beklenen):
    assert motor.ip_global_mi(ip) is beklenen


def test_adres_normalize():
    assert motor.adresi_normalize("WWW.Ornek.COM") == ("https://www.ornek.com/", "www.ornek.com", "ornek.com")
    assert motor.adresi_normalize("http://ornek.com/yol?a=1#x")[0] == "http://ornek.com/yol?a=1"
    assert motor.adresi_normalize("https://ornek.com:443/")[0] == "https://ornek.com:443/"
    assert motor.adresi_normalize("bücher.de")[1] == "xn--bcher-kva.de"


def test_robots_ai_engeli():
    assert si.robots_tumden_engelli_mi(ROBOTS, "GPTBot") is True
    assert si.robots_tumden_engelli_mi(ROBOTS, "ClaudeBot") is False
    genel = "User-agent: *\nDisallow: /\n"
    assert si.robots_tumden_engelli_mi(genel, "PerplexityBot") is True
    kismi = "User-agent: ClaudeBot\nDisallow: /admin\n"
    assert si.robots_tumden_engelli_mi(kismi, "ClaudeBot") is False
    ortak = "User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n"
    assert si.robots_tumden_engelli_mi(ortak, "ClaudeBot") is True
    assert si.robots_tumden_engelli_mi("", "GPTBot") is False


def test_kelime_sayisi_betikleri_saymaz():
    html = "<p>bir iki üç</p><script>var a = 'dört beş';</script><style>.x{}</style><!-- yorum -->"
    assert si.kelime_sayisi(html) == 3


def test_site_taramasi_davranisi_ayni():
    """Ortak modüle taşınan inceleme, panel taramasının çıktısını değiştirmedi."""
    from routers import site_tarama

    html = (
        "<html><head><title>Kısa</title>"
        "<meta name='description' content=\"Türkiye'nin en iyi\"></head>"
        "<body><h1>a</h1><h1>b</h1><img src=a><a href='/hizmet'>x</a>"
        "<a href='https://baska.com'>y</a></body></html>"
    )
    rapor, baglantilar = site_tarama._sayfayi_incele("https://mehmetkuru.dev/", 200, 3000, html)
    kodlar = [(b.kod, b.deger) for b in rapor.bulgular]
    assert kodlar == [
        ("yavas", 3000),
        ("baslik_kisa", 4),
        ("aciklama_kisa", 18),
        ("h1_fazla", 2),
        ("canonical_yok", None),
        ("lang_yok", None),
        ("og_yok", None),
        ("alt_yok", 1),
    ]
    assert baglantilar == ["https://mehmetkuru.dev/hizmet"]


def test_ozet_bulgu_tavani():
    bolumler = [{"anahtar": "seo", "puan": 50, "durum": "tamam",
                 "bulgular": [{"kod": str(i), "seviye": "uyari"} for i in range(7)]}]
    assert len(motor.ozetle(bolumler)[0]["bulgular"]) == 3
    assert motor.genel_puan([{"puan": None}, {"puan": 60}, {"puan": 81}]) == 70


def test_json_serilestirilebilir():
    # Bulgu değerleri JSON'a yazılabilir türde olmalı.
    b = motor._teknik_bolumu(
        motor.Yanit(url="http://x.com/", durum=200, zincir=[{"url": "http://x.com/", "durum": 200}]),
        [], None,
    ).sonuc()
    json.dumps(b)
    assert any(x["kod"] == "https_yok" for x in b["bulgular"])


def test_vekil_ip_basligi_once_okunur():
    """Site vekilinin taşıdığı ziyaretçi IP'si, Worker'ın CF-Connecting-IP'sinden önce gelir."""
    from starlette.requests import Request as _Istek

    from routers.site_analizi import _istemci_ip

    def istek(basliklar):
        return _Istek({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in basliklar.items()], "client": ("9.9.9.9", 1)})

    assert _istemci_ip(istek({"x-mk-istemci-ip": "203.0.113.7", "cf-connecting-ip": "2a06:98c0:3600::103"})) == "203.0.113.7"
    # Bozuk değer yok sayılır.
    assert _istemci_ip(istek({"x-mk-istemci-ip": "abc", "cf-connecting-ip": "198.51.100.2"})) == "198.51.100.2"
    assert _istemci_ip(istek({})) == "9.9.9.9"


def _guvenlik(basliklar):
    ana = motor.Yanit(url="http://ornek.com/", durum=200, basliklar=basliklar)
    return motor._guvenlik_bolumu(ana, None, None).sonuc()


def test_csp_rapor_modu_kismen_sayilir():
    tam = dict(GUVENLI_BASLIKLAR)
    zorunlu = _guvenlik(tam)
    assert "guvenlik_basliklari_tamam" in [b["kod"] for b in zorunlu["bulgular"]]

    rapor = dict(tam)
    politika = rapor.pop("content-security-policy")
    rapor["content-security-policy-report-only"] = politika
    rapor["x-frame-options"] = "SAMEORIGIN"
    kismen = _guvenlik(rapor)
    kodlar = [b["kod"] for b in kismen["bulgular"]]
    assert "csp_rapor" in kodlar and "csp_yok" not in kodlar
    # "Tamam" sayılmaz; ama hiç CSP olmayandan daha yüksek puan alır.
    assert "guvenlik_basliklari_tamam" not in kodlar
    assert next(b for b in kismen["bulgular"] if b["kod"] == "csp_rapor")["seviye"] == "bilgi"

    hic = dict(rapor)
    hic.pop("content-security-policy-report-only")
    yok = _guvenlik(hic)
    assert "csp_yok" in [b["kod"] for b in yok["bulgular"]]
    assert zorunlu["puan"] > kismen["puan"] > yok["puan"]
    assert kismen["puan"] - yok["puan"] == 8


def test_csp_rapor_modu_frame_korumasi_saymaz():
    # Rapor modundaki frame-ancestors tarayıcıyı bağlamaz: X-Frame-Options
    # yoksa çerçeveleme koruması eksik sayılmalı.
    basliklar = {
        "strict-transport-security": "max-age=31536000",
        "content-security-policy-report-only": "default-src 'self'; frame-ancestors 'self'",
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin-when-cross-origin",
    }
    kodlar = [b["kod"] for b in _guvenlik(basliklar)["bulgular"]]
    assert "frame_koruma_yok" in kodlar and "csp_rapor" in kodlar


def test_csp_rapor_metni_yedi_dilde():
    import pathlib

    kok = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek" / "siteAnalizi"
    for dil in ("tr", "en", "de", "ru", "zh", "hi", "ar"):
        veri = json.loads((kok / f"{dil}.json").read_text(encoding="utf-8"))
        metin = veri["siteAnalizi"]["bulgu"]["csp_rapor"]
        assert metin["baslik"] and metin["neden"] and metin["oneri"], dil


async def test_musteri_gunluk_siniri_modul_ayarindan(istemci, ag, db_oturumu, musteri_basligi, yonetici_basligi):
    """`site_analizi` modülünün `gunluk_sinir` ayarı müşteri başına okunuyor."""
    simdi = datetime.now(timezone.utc)

    def _dolu(eposta, adet):
        for i in range(adet):
            db_oturumu.add(Site_analyses(
                alan_adi=f"g{i}.com", url=f"https://g{i}.com/", durum="tamam",
                eposta=eposta, kaynak="musteri", created_at=simdi,
            ))

    # Sınırı 2'ye indirilen müşteri: 2 analizden sonra 429.
    yanit = await istemci.put(
        "/api/v1/moduller/musteri/sinirli@musteri.com/site_analizi",
        json={"ayarlar": {"gunluk_sinir": 2}}, headers=yonetici_basligi,
    )
    assert yanit.status_code == 200, yanit.text
    _dolu("sinirli@musteri.com", 2)
    # Sınırı 20'ye çıkarılan müşteri: 12 analizden sonra hâlâ açık (varsayılan 10 olsaydı 429).
    yanit = await istemci.put(
        "/api/v1/moduller/musteri/genis@musteri.com/site_analizi",
        json={"ayarlar": {"gunluk_sinir": 20}}, headers=yonetici_basligi,
    )
    assert yanit.status_code == 200, yanit.text
    _dolu("genis@musteri.com", 12)
    # Ayarı olmayan müşteri: varsayılan 10.
    _dolu("varsayilan@musteri.com", 10)
    await db_oturumu.commit()

    async def _dene(eposta):
        return await istemci.post(f"{UC}/benim", json={"url": "ornek.com"}, headers=musteri_basligi(eposta))

    y = await _dene("sinirli@musteri.com")
    assert y.status_code == 429 and y.json()["detail"]["kod"] == "sinir_musteri"
    assert (await _dene("genis@musteri.com")).status_code == 200
    assert (await _dene("varsayilan@musteri.com")).status_code == 429

    # Sıfır: müşteri panelden hiç analiz yapamaz.
    await istemci.put(
        "/api/v1/moduller/musteri/sifir@musteri.com/site_analizi",
        json={"ayarlar": {"gunluk_sinir": 0}}, headers=yonetici_basligi,
    )
    assert (await _dene("sifir@musteri.com")).status_code == 429
