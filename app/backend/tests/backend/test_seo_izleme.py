"""Faz 2H — müşteri siteleri için teknik SEO + Core Web Vitals izleme (modül #31).

Dış ağa ÇIKILMIYOR: site istekleri `httpx.MockTransport` ile sahte bir
"internete" gidiyor; DNS, SSL bitişi ve PageSpeed sahte. Ölçümü gerçek motor
(`services/site_analizi.analiz_et`) yapıyor — sahtelenen yalnız ağ katmanı.

Kapsam: zamanlı görev (en çok 3 site, en eskiden), PageSpeed hatasında kısmi
kayıt, düşüş / yeni kritik bulgu / kırık bağlantı uyarısı (7 günde bir), elle
tarama sınırı (müşteri günde 1, yönetici sınırsız), hesap/izin kuralları,
yönetici özeti, aylık rapora özet, test ortamı sahte PageSpeed'inin üretimde
asla devreye girmemesi, i18n paketleri.
"""

import json
import socket
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, update

from conftest import jeton_uret
from services import site_analizi as motor

#: Modül yüklenirken (fixture'lar sahtelemeden önce) gerçek fonksiyon.
GERCEK_PAGESPEED = motor._pagespeed_cagir

SITE = "/api/v1/musteri-sitesi"
BAKIM = "/api/v1/site-bakim"
MUSTERI = "/api/v1/sitelerim"
GENEL_IP = "93.184.216.34"
EK = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
BASLIK_METNI = "Örnek Site — kaliteli web hizmetleri ve danışmanlık"


def _eposta(on: str = "seo") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


def _host() -> str:
    return f"seo-{uuid.uuid4().hex[:10]}.example.com"


def _b(eposta: str, hesap: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {jeton_uret(eposta)}"}
    if hesap:
        h["X-MK-Hesap"] = hesap
    return h


class SahteSite:
    def __init__(self, host: str):
        self.host = host
        self.noindex = False
        self.sitemap = True
        self.kirik = 0
        self.robots_engel = False
        self.kapali = False

    def html(self) -> str:
        meta = '<meta name="robots" content="noindex">' if self.noindex else ""
        kiriklar = "".join(f'<a href="/kirik-{i}">k{i}</a>' for i in range(self.kirik))
        kelimeler = " ".join(["kelime"] * 400)
        return (
            f'<!doctype html><html lang="tr"><head><title>{BASLIK_METNI}</title>'
            '<meta name="description" content="Örnek Site, işletmeler için hızlı ve ölçülebilir web siteleri kurar; '
            'bakım, SEO ve ölçümleme hizmetleri sunar.">'
            f'<link rel="canonical" href="https://{self.host}/">{meta}'
            '<script type="application/ld+json">{"@type":"Organization"}</script>'
            f'</head><body><h1>Örnek</h1><p>{kelimeler}</p><a href="/hakkinda">Hakkında</a>{kiriklar}</body></html>'
        )


class SahteAg:
    def __init__(self):
        self.siteler: dict[str, SahteSite] = {}
        self.pagespeed = {"mobile": 0.9, "desktop": 0.96}
        self.pagespeed_hatasi = False

    def site(self, host: str) -> SahteSite:
        self.siteler[host] = SahteSite(host)
        return self.siteler[host]

    def isle(self, istek: httpx.Request) -> httpx.Response:
        s = self.siteler.get(istek.url.host)
        if s is None or s.kapali:
            raise httpx.ConnectError("bağlantı reddedildi", request=istek)
        if istek.url.scheme == "http":
            return httpx.Response(301, headers={"location": f"https://{s.host}/"})
        yol = istek.url.path
        html = {"content-type": "text/html; charset=utf-8", "cache-control": "max-age=60", "strict-transport-security": "max-age=1"}
        if yol == "/":
            return httpx.Response(200, headers=html, text=s.html())
        if yol == "/hakkinda":
            return httpx.Response(200, headers=html, text="<html lang='tr'><title>Hakkında sayfası — Örnek</title><h1>H</h1></html>")
        if yol == "/robots.txt":
            metin = "User-agent: *\nDisallow: /\n" if s.robots_engel else f"User-agent: *\nAllow: /\n\nSitemap: https://{s.host}/sitemap.xml\n"
            return httpx.Response(200, headers={"content-type": "text/plain"}, text=metin)
        if yol == "/sitemap.xml" and s.sitemap:
            return httpx.Response(200, headers={"content-type": "application/xml"},
                                  text=f"<urlset><url><loc>https://{s.host}/</loc></url></urlset>")
        return httpx.Response(404, headers={"content-type": "text/html"}, text="yok")


def _pagespeed_json(puan: float) -> dict:
    return {
        "lighthouseResult": {
            "categories": {"performance": {"score": puan}},
            "audits": {
                "largest-contentful-paint": {"numericValue": 2300.0},
                "cumulative-layout-shift": {"numericValue": 0.12},
                "total-blocking-time": {"numericValue": 650.0},
            },
        }
    }


@pytest.fixture(autouse=True)
def ag(monkeypatch):
    sahte = SahteAg()

    async def dns(host, port):
        if host in sahte.siteler:
            return [GENEL_IP]
        raise socket.gaierror("bilinmeyen")

    async def ssl(host):
        return datetime.now(timezone.utc) + timedelta(days=90), None

    async def pagespeed(url, strateji):
        if sahte.pagespeed_hatasi:
            raise httpx.HTTPStatusError("kota", request=httpx.Request("GET", url), response=httpx.Response(429))
        return _pagespeed_json(sahte.pagespeed[strateji])

    monkeypatch.setattr(motor, "_tasiyici_fabrikasi", lambda: httpx.MockTransport(sahte.isle))
    monkeypatch.setattr(motor, "_dns_cozumle", dns)
    monkeypatch.setattr(motor, "_ssl_bitis", ssl)
    monkeypatch.setattr(motor, "_pagespeed_cagir", pagespeed)
    for ad in ("SSRF_TEST_IZINLI_HOSTLAR", "ENVIRONMENT", "RENDER"):
        monkeypatch.delenv(ad, raising=False)
    return sahte


async def _site(istemci, yonetici_basligi, ag, eposta=None, host=None):
    eposta = eposta or _eposta()
    host = host or _host()
    ag.site(host)
    y = await istemci.post(SITE, json={"client_email": eposta, "ad": f"Site {host[:12]}", "adres": f"https://{host}/"},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    return y.json()["id"], eposta, ag.siteler[host]


async def _tara(istemci, yonetici_basligi, site_id):
    y = await istemci.post(f"{BAKIM}/{site_id}/seo-tara", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    return y.json()["olcum"]


async def _bildirimler(db, eposta, olay="seo_dususu"):
    from models.notifications import Notifications

    return list(
        (
            await db.execute(
                select(Notifications).where(
                    Notifications.event_type == olay, Notifications.channel == "inapp", Notifications.recipient_email == eposta
                )
            )
        ).scalars().all()
    )


async def _digerlerini_sustur(db, haric: set):
    """Paylaşılan veritabanındaki başka testlerin sitelerini "az önce ölçüldü" yap."""
    from models.client_sites import Client_sites
    from models.site_seo import SiteSeoGecmisi

    simdi = datetime.now(timezone.utc)
    for (sid,) in (await db.execute(select(Client_sites.id))).all():
        if sid not in haric:
            db.add(SiteSeoGecmisi(site_id=sid, hesap_email="baska@test.dev", olcum_at=simdi, kaynak="zamanli", durum="tamam"))
    await db.commit()


# ===========================================================================
# Zamanlı görev
# ===========================================================================
async def test_zamanli_en_cok_uc_site_ve_en_eskiden(istemci, yonetici_basligi, ag, db_oturumu):
    from models.site_seo import SiteSeoGecmisi
    from services import seo_izleme, zamanli

    assert "seo_taramasi" in zamanli.GOREV_ADLARI
    idler = {}
    for ad in "ABCDE":
        sid, eposta, _ = await _site(istemci, yonetici_basligi, ag)
        idler[ad] = sid
    await _digerlerini_sustur(db_oturumu, set(idler.values()))
    simdi = datetime.now(timezone.utc)
    for ad, gun in (("A", 10), ("B", 8), ("D", 2)):
        db_oturumu.add(SiteSeoGecmisi(site_id=idler[ad], hesap_email="x@test.dev", olcum_at=simdi - timedelta(days=gun),
                                      kaynak="zamanli", durum="tamam", genel_puan=80))
    await db_oturumu.commit()

    sira = [s.id for s, _ in await seo_izleme.tarama_sirasi(db_oturumu)]
    assert sira == [idler["C"], idler["E"], idler["A"], idler["B"]]  # hiç ölçülmemiş önce, sonra en eski

    ozet = await seo_izleme.zamanli_tarama(db_oturumu)
    assert ozet["olculen"] == 3 and ozet["bekleyen"] == 1 and ozet["hata"] == 0

    async def yeni_olcumler():
        satirlar = (
            await db_oturumu.execute(
                select(SiteSeoGecmisi.site_id).where(
                    SiteSeoGecmisi.site_id.in_(list(idler.values())),
                    SiteSeoGecmisi.kaynak == "zamanli",
                    SiteSeoGecmisi.olcum_at >= simdi - timedelta(minutes=1),
                    SiteSeoGecmisi.durum == "tamam",
                )
            )
        ).all()
        return sorted(s for (s,) in satirlar)

    assert await yeni_olcumler() == sorted([idler["C"], idler["E"], idler["A"]])

    # İkinci tur: yalnız B kaldı; D (2 gün önce) zamanı gelmedi.
    ozet = await seo_izleme.zamanli_tarama(db_oturumu)
    assert ozet["olculen"] == 1 and ozet["bekleyen"] == 0
    assert await yeni_olcumler() == sorted([idler["A"], idler["B"], idler["C"], idler["E"]])
    assert (await seo_izleme.zamanli_tarama(db_oturumu))["olculen"] == 0


async def test_tarama_sikligi_ayari(istemci, yonetici_basligi, musteri_basligi, ag, db_oturumu):
    from models.site_seo import SiteSeoGecmisi
    from services import seo_izleme

    sid, eposta, _ = await _site(istemci, yonetici_basligi, ag)
    db_oturumu.add(SiteSeoGecmisi(site_id=sid, hesap_email=eposta, olcum_at=datetime.now(timezone.utc) - timedelta(days=4),
                                  kaynak="zamanli", durum="tamam", genel_puan=70))
    await db_oturumu.commit()
    sira = lambda: seo_izleme.tarama_sirasi(db_oturumu)  # noqa: E731
    assert sid not in [s.id for s, _ in await sira()]  # varsayılan 7 gün

    y = await istemci.put(f"{BAKIM}/{sid}/seo-ayar", json={"tarama_gun": 3}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["tarama_gun"] == 3
    assert sid in [s.id for s, _ in await sira()]
    y = await istemci.put(f"{BAKIM}/{sid}/seo-ayar", json={"tarama_gun": 0}, headers=yonetici_basligi)
    assert y.status_code == 200
    assert sid not in [s.id for s, _ in await sira()]  # 0 = kapalı
    assert (await istemci.put(f"{BAKIM}/{sid}/seo-ayar", json={"tarama_gun": 91}, headers=yonetici_basligi)).status_code == 400
    assert (await istemci.put(f"{BAKIM}/{sid}/seo-ayar", json={"tarama_gun": 3}, headers=musteri_basligi(eposta))).status_code == 403
    g = await istemci.get(f"{MUSTERI}/{sid}/seo-gecmisi", headers=_b(eposta))
    assert g.status_code == 200 and g.json()["tarama_gun"] == 0 and g.json()["sonraki_tarama_at"] is None


# ===========================================================================
# Kayıt
# ===========================================================================
async def test_pagespeed_hatasinda_diger_bolumler_kaydedilir(istemci, yonetici_basligi, ag, db_oturumu):
    from models.site_seo import SiteSeoGecmisi

    sid, _, _ = await _site(istemci, yonetici_basligi, ag)
    ag.pagespeed_hatasi = True
    olcum = await _tara(istemci, yonetici_basligi, sid)
    assert olcum["durum"] == "tamam"
    assert olcum["mobil_puan"] is None and olcum["masaustu_puan"] is None
    assert olcum["lcp_ms"] is None and olcum["cls"] is None and olcum["tbt_ms"] is None
    assert olcum["bolum_puanlari"]["hiz"] is None
    assert all(olcum["bolum_puanlari"][b] is not None for b in ("seo", "icerik", "teknik", "guvenlik", "ai"))
    assert olcum["genel_puan"] is not None

    satir = (await db_oturumu.execute(select(SiteSeoGecmisi).where(SiteSeoGecmisi.id == olcum["id"]))).scalar_one()
    bulgular = json.loads(satir.bulgu_ozeti)
    assert {"kod": "hiz_olculemedi", "seviye": "bilgi", "bolum": "hiz"} in bulgular
    # Ham sayfa içeriği yok: başlık metni, HTML, adres saklanmıyor.
    ham = satir.bulgu_ozeti + (satir.bolum_puanlari or "")
    assert "Örnek" not in ham and "<" not in ham and "://" not in ham
    assert all(set(b) <= {"kod", "seviye", "bolum", "deger"} for b in bulgular)

    # PageSpeed düzelince mobil/masaüstü ve Core Web Vitals yazılıyor.
    ag.pagespeed_hatasi = False
    olcum = await _tara(istemci, yonetici_basligi, sid)
    assert (olcum["mobil_puan"], olcum["masaustu_puan"]) == (90, 96)
    assert (olcum["lcp_ms"], olcum["cls"], olcum["tbt_ms"]) == (2300, 0.12, 650)


async def test_site_acilamazsa_hata_satiri(istemci, yonetici_basligi, ag):
    sid, eposta, site = await _site(istemci, yonetici_basligi, ag)
    site.kapali = True
    olcum = await _tara(istemci, yonetici_basligi, sid)
    assert olcum["durum"] == "hata" and olcum["hata_kodu"] == "ulasilamadi" and olcum["genel_puan"] is None
    g = (await istemci.get(f"{MUSTERI}/{sid}/seo-gecmisi", headers=_b(eposta))).json()
    assert g["son"] is None and g["son_deneme"]["hata_kodu"] == "ulasilamadi"


async def test_robots_engeli_kritik_bulgu(istemci, yonetici_basligi, ag):
    sid, _, site = await _site(istemci, yonetici_basligi, ag)
    site.robots_engel = True
    olcum = await _tara(istemci, yonetici_basligi, sid)
    assert "robots_engelli" in olcum["kritik"]
    assert olcum["onemli_bulgular"][0]["kod"] in olcum["kritik"]


# ===========================================================================
# Uyarılar
# ===========================================================================
async def _uye_ekle(db, hesap, uye, rol, izinler=None):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as he

    db.add(HesapUyeleri(
        hesap_email=hesap, uye_email=uye, rol=rol,
        izinler=json.dumps(list(izinler if izinler is not None else he.ROL_VARSAYILAN[rol])),
        durum="aktif", olusturma=he.simdi(),
    ))
    await db.commit()
    he.onbellegi_temizle()


async def test_dusus_uyarisi_bir_kez_7_gunde(istemci, yonetici_basligi, ag, db_oturumu):
    from models.site_seo import SiteSeoUyarisi

    sid, eposta, _ = await _site(istemci, yonetici_basligi, ag)
    # Hesap ekibi: `siteler` izni olan üye de bildirimi alır, fatura rolü almaz (2E genişletmesi).
    uye, fatura = _eposta("uye"), _eposta("fatura")
    await _uye_ekle(db_oturumu, eposta, uye, "uye")
    await _uye_ekle(db_oturumu, eposta, fatura, "fatura")

    ag.pagespeed = {"mobile": 0.95, "desktop": 0.95}
    await _tara(istemci, yonetici_basligi, sid)  # taban: kıyas yok, uyarı yok
    assert await _bildirimler(db_oturumu, eposta) == []

    ag.pagespeed = {"mobile": 0.2, "desktop": 0.2}  # hız 95 → 20: genel puan ~12 düşer
    olcum = await _tara(istemci, yonetici_basligi, sid)
    assert olcum["genel_puan"] is not None
    musteri = await _bildirimler(db_oturumu, eposta)
    assert len(musteri) == 1 and musteri[0].link == "/client?sekme=sitem" and "→" in musteri[0].body
    assert len(await _bildirimler(db_oturumu, "yonetici@test.dev")) >= 1
    assert len(await _bildirimler(db_oturumu, uye)) == 1
    assert await _bildirimler(db_oturumu, fatura) == []

    # Yine düşük: önceki ölçüme göre düşüş yok → uyarı yok.
    await _tara(istemci, yonetici_basligi, sid)
    # Yükselip yeniden düşse de 7 gün dolmadan aynı sorun tekrar bildirilmez.
    ag.pagespeed = {"mobile": 0.95, "desktop": 0.95}
    await _tara(istemci, yonetici_basligi, sid)
    ag.pagespeed = {"mobile": 0.2, "desktop": 0.2}
    await _tara(istemci, yonetici_basligi, sid)
    assert len(await _bildirimler(db_oturumu, eposta)) == 1

    # 8 gün önce gönderilmiş say → bir sonraki düşüşte yine bildirilir.
    await db_oturumu.execute(
        update(SiteSeoUyarisi).where(SiteSeoUyarisi.site_id == sid)
        .values(gonderim_at=datetime.now(timezone.utc) - timedelta(days=8))
    )
    await db_oturumu.commit()
    ag.pagespeed = {"mobile": 0.95, "desktop": 0.95}
    await _tara(istemci, yonetici_basligi, sid)
    ag.pagespeed = {"mobile": 0.2, "desktop": 0.2}
    await _tara(istemci, yonetici_basligi, sid)
    assert len(await _bildirimler(db_oturumu, eposta)) == 2


async def test_pagespeed_dusmesi_sahte_dusus_sayilmaz(istemci, yonetici_basligi, ag, db_oturumu):
    """Hız ölçülemeyince kıyas, iki ölçümde de olan bölümlerle yapılır."""
    sid, eposta, _ = await _site(istemci, yonetici_basligi, ag)
    ag.pagespeed = {"mobile": 1.0, "desktop": 1.0}
    await _tara(istemci, yonetici_basligi, sid)
    ag.pagespeed_hatasi = True
    await _tara(istemci, yonetici_basligi, sid)
    assert await _bildirimler(db_oturumu, eposta) == []


async def test_yeni_kritik_bulgu_ve_kirik_baglanti_artisi(istemci, yonetici_basligi, ag, db_oturumu):
    from models.site_seo import SiteSeoUyarisi

    sid, eposta, site = await _site(istemci, yonetici_basligi, ag)
    await _tara(istemci, yonetici_basligi, sid)
    site.noindex = True
    site.sitemap = False
    site.kirik = 2
    olcum = await _tara(istemci, yonetici_basligi, sid)
    assert {"noindex", "sitemap_yok"} <= set(olcum["kritik"]) and olcum["kirik_baglanti"] == 2
    sorunlar = {
        s for (s,) in (await db_oturumu.execute(select(SiteSeoUyarisi.sorun).where(SiteSeoUyarisi.site_id == sid))).all()
    }
    # (noindex + sitemap cezası genel puanı da 10+ düşürüyor: puan_dususu da var.)
    assert {"kritik:noindex", "kritik:sitemap_yok", "kirik_baglanti"} <= sorunlar
    [b] = await _bildirimler(db_oturumu, eposta)
    assert "noindex" in b.body and "sitemap" in b.body and "0 → 2" in b.body

    # Aynı durum sürüyor: yeni bulgu yok. Kırık bağlantı 2 → 3: 7 gün dolmadığı için yine sessiz.
    site.kirik = 3
    await _tara(istemci, yonetici_basligi, sid)
    assert len(await _bildirimler(db_oturumu, eposta)) == 1
    # En önemli 5 bulgu: kritikler başta, "iyi" yok.
    g = (await istemci.get(f"{MUSTERI}/{sid}/seo-gecmisi", headers=_b(eposta))).json()
    onemli = g["son"]["onemli_bulgular"]
    assert len(onemli) == 5 and onemli[0]["kritik"] and all(b["seviye"] != "iyi" for b in onemli)


def test_sorunlari_bul_saf():
    from services.seo_izleme import sorunlari_bul

    yeni = {"bolum_puanlari": {"hiz": 40, "seo": 80}, "bulgu_ozeti": [{"kod": "https_yok", "seviye": "hata"}]}
    assert sorunlari_bul(None, yeni) == []  # ilk ölçüm taban
    onceki = {"bolum_puanlari": {"hiz": 70, "seo": 80}, "bulgu_ozeti": [{"kod": "kirik_baglanti", "seviye": "hata", "deger": 1}]}
    assert sorunlari_bul(onceki, yeni) == [
        {"sorun": "puan_dususu", "onceki": 75, "simdiki": 60},
        {"sorun": "kritik:https_yok", "kod": "https_yok"},
    ]
    # 9 puan: eşiğin altında.
    assert sorunlari_bul({"bolum_puanlari": {"seo": 89}, "bulgu_ozeti": []}, {"bolum_puanlari": {"seo": 80}, "bulgu_ozeti": []}) == []


# ===========================================================================
# Elle tarama ve yetki
# ===========================================================================
async def test_elle_tarama_musteri_gunde_bir_yonetici_sinirsiz(istemci, yonetici_basligi, ag):
    sid, eposta, _ = await _site(istemci, yonetici_basligi, ag)
    y = await istemci.post(f"{MUSTERI}/{sid}/seo-tara", headers=_b(eposta))
    assert y.status_code == 200, y.text
    assert y.json()["olcum"]["kaynak"] == "elle" and y.json()["olcum"]["genel_puan"] is not None
    y = await istemci.post(f"{MUSTERI}/{sid}/seo-tara", headers=_b(eposta))
    assert y.status_code == 429 and y.json()["detail"]["kod"] == "gunluk_sinir" and y.json()["detail"]["sonraki_at"]
    g = (await istemci.get(f"{MUSTERI}/{sid}/seo-gecmisi", headers=_b(eposta))).json()
    assert g["elle"]["kalan"] == 0 and g["elle"]["sonraki_at"]
    for _ in range(3):
        y = await istemci.post(f"{BAKIM}/{sid}/seo-tara", headers=yonetici_basligi)
        assert y.status_code == 200 and y.json()["olcum"]["kaynak"] == "yonetici"
    # Yönetici müşteri ucundan da sınırsız (kaynak yönetici).
    assert (await istemci.post(f"{MUSTERI}/{sid}/seo-tara", headers=yonetici_basligi)).status_code == 200
    # Hâlâ müşteriye kapalı (yönetici taramaları sayılmıyor ama müşterinin hakkı doldu).
    assert (await istemci.post(f"{MUSTERI}/{sid}/seo-tara", headers=_b(eposta))).status_code == 429


async def test_suren_tarama_ikinci_istegi_409(istemci, yonetici_basligi, ag, db_oturumu):
    from models.site_seo import SiteSeoGecmisi
    from services import seo_izleme

    sid, eposta, _ = await _site(istemci, yonetici_basligi, ag)
    db_oturumu.add(SiteSeoGecmisi(site_id=sid, hesap_email=eposta, olcum_at=datetime.now(timezone.utc),
                                  kaynak="zamanli", durum="calisiyor"))
    await db_oturumu.commit()
    y = await istemci.post(f"{BAKIM}/{sid}/seo-tara", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "tarama_suruyor"
    # Yarıda kalmış (10 dk'dan eski) "calisiyor" satırı kapanır, tarama yeniden yapılabilir.
    await db_oturumu.execute(
        update(SiteSeoGecmisi).where(SiteSeoGecmisi.site_id == sid)
        .values(olcum_at=datetime.now(timezone.utc) - timedelta(minutes=11))
    )
    await db_oturumu.commit()
    assert await seo_izleme.yarida_kalanlari_kapat(db_oturumu) >= 1
    assert (await istemci.post(f"{BAKIM}/{sid}/seo-tara", headers=yonetici_basligi)).status_code == 200


async def test_musteri_baska_hesabin_sitesine_erisemez(istemci, yonetici_basligi, ag):
    sid, eposta, _ = await _site(istemci, yonetici_basligi, ag)
    baska = _b(_eposta("baska"))
    for metot, yol in (("GET", f"{MUSTERI}/{sid}/seo-gecmisi"), ("POST", f"{MUSTERI}/{sid}/seo-tara")):
        y = await istemci.request(metot, yol, headers=baska)
        assert y.status_code == 404 and y.json()["detail"]["kod"] == "site_yok", (yol, y.text)
        assert (await istemci.request(metot, yol)).status_code == 401
    assert (await istemci.get(f"{MUSTERI}/999999/seo-gecmisi", headers=_b(eposta))).status_code == 404
    # Yönetici uçları müşteriye kapalı.
    for metot, yol in (("GET", f"{BAKIM}/seo-ozet"), ("GET", f"{BAKIM}/{sid}/seo-gecmisi"), ("POST", f"{BAKIM}/{sid}/seo-tara")):
        assert (await istemci.request(metot, yol, headers=_b(eposta))).status_code == 403
        assert (await istemci.request(metot, yol)).status_code in (401, 403)
    assert (await istemci.get(f"{MUSTERI}/{sid}/seo-gecmisi?gun=3", headers=_b(eposta))).status_code == 422


async def test_uye_siteler_izni_yoksa_403(istemci, yonetici_basligi, ag, db_oturumu):
    sid, sahip, _ = await _site(istemci, yonetici_basligi, ag)
    kisitli, izinli = _eposta("kisitli"), _eposta("izinli")
    await _uye_ekle(db_oturumu, sahip, kisitli, "uye", izinler=["projeler"])
    await _uye_ekle(db_oturumu, sahip, izinli, "uye", izinler=["siteler"])
    for metot, yol in (("GET", f"{MUSTERI}/{sid}/seo-gecmisi"), ("POST", f"{MUSTERI}/{sid}/seo-tara")):
        y = await istemci.request(metot, yol, headers=_b(kisitli, sahip))
        assert y.status_code == 403 and y.json()["detail"]["kod"] == "hesap_izni_yok", y.text
    y = await istemci.get(f"{MUSTERI}/{sid}/seo-gecmisi", headers=_b(izinli, sahip))
    assert y.status_code == 200 and y.json()["site_id"] == sid
    # Başlıksız: üyenin kendi (boş) hesabı → site onun değil.
    assert (await istemci.get(f"{MUSTERI}/{sid}/seo-gecmisi", headers=_b(izinli))).status_code == 404


# ===========================================================================
# Geçmiş ve yönetici özeti
# ===========================================================================
async def test_gecmis_90_gun_ve_bicim(istemci, yonetici_basligi, ag, db_oturumu):
    from models.site_seo import SiteSeoGecmisi

    sid, eposta, _ = await _site(istemci, yonetici_basligi, ag)
    an = datetime.now(timezone.utc)
    for gun, puan in ((100, 50), (40, 60), (20, 70)):
        db_oturumu.add(SiteSeoGecmisi(site_id=sid, hesap_email=eposta, olcum_at=an - timedelta(days=gun), kaynak="zamanli",
                                      durum="tamam", genel_puan=puan, bolum_puanlari="{}", bulgu_ozeti="[]"))
    await db_oturumu.commit()
    g = (await istemci.get(f"{MUSTERI}/{sid}/seo-gecmisi?gun=90", headers=_b(eposta))).json()
    assert [s["genel_puan"] for s in g["gecmis"]] == [60, 70]  # artan sırada, 100 gün öncesi yok
    assert g["son"]["genel_puan"] == 70 and g["onceki_puan"] == 60 and g["degisim"] == 10
    assert g["elle"] == {"kalan": 1, "sonraki_at": None, "sinirsiz": False}
    assert g["sonraki_tarama_at"] and g["calisiyor"] is False
    assert "client_email" not in g and "bulgu_ozeti" not in json.dumps(g)


async def test_yonetici_ozeti_dususte_olanlar_ustte(istemci, yonetici_basligi, ag, db_oturumu):
    from models.site_seo import SiteSeoGecmisi

    an = datetime.now(timezone.utc)
    dusen, _, _ = await _site(istemci, yonetici_basligi, ag)
    artan, _, _ = await _site(istemci, yonetici_basligi, ag)
    for sid, puanlar in ((dusen, (90, 70)), (artan, (40, 45))):
        for i, puan in enumerate(puanlar):
            db_oturumu.add(SiteSeoGecmisi(site_id=sid, hesap_email="x@test.dev", olcum_at=an - timedelta(days=2 - i),
                                          kaynak="zamanli", durum="tamam", genel_puan=puan, bolum_puanlari="{}", bulgu_ozeti="[]"))
    await db_oturumu.commit()
    y = await istemci.get(f"{BAKIM}/seo-ozet", headers=yonetici_basligi)
    assert y.status_code == 200, y.text  # `/{site_id}` ile çakışmıyor (router sırası)
    satirlar = y.json()["siteler"]
    idler = [s["site_id"] for s in satirlar]
    d = satirlar[idler.index(dusen)]
    assert d["dususte"] is True and d["degisim"] == -20 and d["son"]["genel_puan"] == 70
    assert satirlar[idler.index(artan)]["dususte"] is False
    assert idler.index(dusen) < idler.index(artan)
    # Düşüşte olan bütün satırlar düşüşte olmayanlardan önce.
    durumlar = [s["dususte"] for s in satirlar]
    assert durumlar == sorted(durumlar, reverse=True)
    g = (await istemci.get(f"{BAKIM}/{dusen}/seo-gecmisi", headers=yonetici_basligi)).json()
    assert g["elle"]["sinirsiz"] is True and len(g["gecmis"]) == 2


# ===========================================================================
# Aylık rapor
# ===========================================================================
async def test_aylik_rapora_seo_ozeti_girer(db_oturumu):
    from models.client_sites import Client_sites
    from models.site_seo import SiteSeoGecmisi, SiteSeoUyarisi
    from services.aylik_rapor import ozet_metni, veri_topla

    tr = timezone(timedelta(hours=3))
    eposta = _eposta("aylik")
    site = Client_sites(client_email=eposta, ad="Aylık SEO sitesi", adres="https://aylik-seo.example/")
    db_oturumu.add(site)
    await db_oturumu.flush()
    bulgu = json.dumps([{"kod": "noindex", "seviye": "hata", "bolum": "seo"}])
    db_oturumu.add_all([
        SiteSeoGecmisi(site_id=site.id, hesap_email=eposta, olcum_at=datetime(2026, 8, 30, 12, tzinfo=tr), kaynak="zamanli",
                       durum="tamam", genel_puan=95),
        SiteSeoGecmisi(site_id=site.id, hesap_email=eposta, olcum_at=datetime(2026, 9, 3, 12, tzinfo=tr), kaynak="zamanli",
                       durum="tamam", genel_puan=80, mobil_puan=70, masaustu_puan=90),
        SiteSeoGecmisi(site_id=site.id, hesap_email=eposta, olcum_at=datetime(2026, 9, 10, 12, tzinfo=tr), kaynak="zamanli",
                       durum="hata", hata_kodu="ulasilamadi"),
        SiteSeoGecmisi(site_id=site.id, hesap_email=eposta, olcum_at=datetime(2026, 9, 24, 12, tzinfo=tr), kaynak="elle",
                       durum="tamam", genel_puan=68, mobil_puan=55, masaustu_puan=88, lcp_ms=3100, cls=0.05, tbt_ms=420,
                       bulgu_ozeti=bulgu),
        SiteSeoUyarisi(site_id=site.id, sorun="puan_dususu", gonderim_at=datetime(2026, 9, 24, 12, tzinfo=tr)),
        SiteSeoUyarisi(site_id=site.id, sorun="kritik:noindex", gonderim_at=datetime(2026, 10, 2, 12, tzinfo=tr)),
    ])
    await db_oturumu.commit()

    v = await veri_topla(db_oturumu, eposta, "2026-09")
    [s] = v["seo_izleme"]
    assert (s["ad"], s["olcum_sayisi"], s["ilk_puan"], s["son_puan"], s["degisim"]) == ("Aylık SEO sitesi", 2, 80, 68, -12)
    assert (s["en_dusuk"], s["en_yuksek"], s["ortalama"]) == (68, 80, 74.0)
    assert (s["son_mobil"], s["son_masaustu"], s["son_lcp_ms"], s["son_cls"], s["son_tbt_ms"]) == (55, 88, 3100, 0.05, 420)
    assert s["son_kritik"] == ["noindex"] and s["uyari_sayisi"] == 1
    assert "2 SEO/hız ölçümü, son puan 68" in ozet_metni(v)
    # Ölçümü olmayan ay / müşteri: boş liste.
    assert (await veri_topla(db_oturumu, eposta, "2026-07"))["seo_izleme"] == []
    assert (await veri_topla(db_oturumu, _eposta("yok"), "2026-09"))["seo_izleme"] == []


# ===========================================================================
# Test ortamının sahte PageSpeed'i üretimde ASLA devreye girmiyor
# ===========================================================================
class _GercekIstek(Exception):
    pass


@pytest.fixture
def gercek_istek_yakala(monkeypatch):
    async def yakala(self, *a, **k):
        raise _GercekIstek()

    monkeypatch.setattr(httpx.AsyncClient, "get", yakala)


#: (ortam değişkenleri, sahte açık mı)
SAHTE_DURUMLARI = [
    ({"ENVIRONMENT": "test"}, True),
    ({"ENVIRONMENT": " TEST "}, True),
    ({"ENVIRONMENT": "test", "RENDER": "srv-123"}, False),  # Render'da asla
    ({}, False),  # tanımsız = üretim
    ({"ENVIRONMENT": "production"}, False),
    ({"ENVIRONMENT": "dev"}, False),
    ({"ENVIRONMENT": "yerel"}, False),
]


async def test_sahte_pagespeed_yalniz_test_ortaminda(monkeypatch, gercek_istek_yakala):
    for degiskenler, acik_mi in SAHTE_DURUMLARI:
        with monkeypatch.context() as m:
            for ad in ("ENVIRONMENT", "RENDER"):
                m.delenv(ad, raising=False)
            for ad, deger in degiskenler.items():
                m.setenv(ad, deger)
            assert motor.sahte_pagespeed_acik_mi() is acik_mi, degiskenler
            if acik_mi:
                veri = await GERCEK_PAGESPEED("https://ornek.example/", "mobile")
                assert veri["lighthouseResult"]["categories"]["performance"]["score"] == motor.SAHTE_PAGESPEED["mobile"][0]
                m.setattr(motor, "_pagespeed_cagir", GERCEK_PAGESPEED)
                olcum = await motor.pagespeed_olc("https://ornek.example/", "desktop")
                assert olcum == {"puan": 95, "lcp_ms": 1100.0, "cls": 0.02, "tbt_ms": 40.0}
            else:
                # Gerçek yola gidiyor (burada ağ yerine yakalayıcı): sahte yanıt dönmüyor.
                with pytest.raises(_GercekIstek):
                    await GERCEK_PAGESPEED("https://ornek.example/", "mobile")


# ===========================================================================
# Kayıtlar ve i18n
# ===========================================================================
def test_olay_katalogu_ve_izin():
    from services.bildirim_tercih import OLAYLAR
    from services.hesap_ekibi import OLAY_IZNI

    assert OLAYLAR["seo_dususu"] == {"roller": ("admin", "client"), "tetikleniyor": True}
    assert OLAY_IZNI["seo_dususu"] == "siteler"
    tr = json.loads((EK / "bildirim" / "tr.json").read_text(encoding="utf-8"))["bildirim"]["olay"]["seo_dususu"]
    for dil in DILLER:
        ek = json.loads((EK / "bildirim" / f"{dil}.json").read_text(encoding="utf-8"))["bildirim"]["olay"]["seo_dususu"]
        assert ek.strip() and (dil == "tr" or ek != tr)


def _duz(d, on=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _duz(v, f"{on}{k}.")
        else:
            yield f"{on}{k}", v


def test_seo_izleme_paketi_yedi_dilde():
    paketler = {
        dil: dict(_duz(json.loads((EK / "seoIzleme" / f"{dil}.json").read_text(encoding="utf-8"))["seoIzleme"])) for dil in DILLER
    }
    anahtarlar = set(paketler["tr"])
    assert len(anahtarlar) > 40
    for dil, p in paketler.items():
        assert set(p) == anahtarlar, (dil, sorted(set(p) ^ anahtarlar)[:5])
        assert all(isinstance(v, str) and v.strip() for v in p.values()), dil
        assert not any("{{count}}" in v for v in p.values()), dil
    for dil in DILLER[1:]:
        ayni = [k for k in anahtarlar if paketler[dil][k] == paketler["tr"][k] and len(paketler["tr"][k]) > 12]
        assert not ayni, (dil, ayni[:5])
    # Arayüzün çevirdiği hata kodları motorun kodlarını kapsıyor.
    for kod in ("ulasilamadi", "cozumlenemedi", "adres_yasak", "adres_gecersiz", "cok_yonlendirme", "zaman_asimi",
                "yarida_kaldi", "beklenmedik"):
        assert f"hataKodu.{kod}" in anahtarlar


def test_kritik_kodlar_ve_robots_metni_paketlerde():
    from services.seo_izleme import KRITIK_KODLAR

    for dil in DILLER:
        sa = json.loads((EK / "siteAnalizi" / f"{dil}.json").read_text(encoding="utf-8"))["siteAnalizi"]["bulgu"]
        for kod in KRITIK_KODLAR:
            assert sa[kod]["baslik"].strip(), (dil, kod)
        ar = json.loads((EK / "aylikRapor" / f"{dil}.json").read_text(encoding="utf-8"))["aylikRapor"]["seoIzleme"]
        assert set(ar["kritikKod"]) == set(KRITIK_KODLAR), dil
