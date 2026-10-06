"""Faz 2A — müşteri sitesi bakımı, uptime, durum sayfası, yenileme ve zamanlı görevler.

Ağa hiç çıkılmıyor: site istekleri `httpx.MockTransport` ile sahte bir
"internete" gidiyor, DNS/SSL/RDAP yerine sahteleri konuyor (autouse).
Veritabanı oturum boyunca paylaşılıyor; her test kendi e-postası/sitesiyle.
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select, update

SITE = "/api/v1/musteri-sitesi"
BAKIM = "/api/v1/site-bakim"
MUSTERI = "/api/v1/sitelerim-bakim"
DURUM = "/api/v1/durum"
YENILEME = "/api/v1/yenilemeler"
ZAMANLI = "/api/v1/zamanli"
MODUL = "/api/v1/moduller"
GENEL_IP = "93.184.216.34"


def _eposta(on: str = "bakim") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


class SahteAg:
    """Adres → (durum, gövde). Kapatılan adres bağlantı hatası verir."""

    def __init__(self):
        self.yanitlar = {}
        self.kapali = set()
        self.cagrilar = []

    def isle(self, istek: httpx.Request) -> httpx.Response:
        url = str(istek.url)
        self.cagrilar.append(url)
        host = istek.url.host
        if host in self.kapali:
            raise httpx.ConnectError("kapalı", request=istek)
        durum, govde = self.yanitlar.get(host, (200, "<html><body>Merhaba dunya</body></html>"))
        return httpx.Response(durum, text=govde, headers={"content-type": "text/html; charset=utf-8"})


@pytest.fixture(autouse=True)
def ag(monkeypatch):
    from services import site_analizi as sa
    from services import site_izleme as si

    sahte = SahteAg()

    async def dns(host, port):
        if host.endswith(".ic-ag.test"):
            return ["10.0.0.5"]
        return [GENEL_IP]

    async def ssl(host):
        return datetime.now(timezone.utc) + timedelta(days=80), None

    async def rdap(alan):
        return datetime.now(timezone.utc) + timedelta(days=200), None

    monkeypatch.setattr(sa, "_tasiyici_fabrikasi", lambda: httpx.MockTransport(sahte.isle))
    monkeypatch.setattr(sa, "_dns_cozumle", dns)
    monkeypatch.setattr(sa, "_ssl_bitis", ssl)
    monkeypatch.setattr(si, "rdap_sorgula", rdap)
    monkeypatch.delenv("SSRF_TEST_IZINLI_HOSTLAR", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("ZAMANLI_ANAHTAR", raising=False)
    return sahte


async def _site(istemci, yonetici_basligi, eposta, adres=None, ad=None):
    adres = adres or f"https://{uuid.uuid4().hex[:8]}.example.com"
    yanit = await istemci.post(
        SITE, json={"client_email": eposta, "ad": ad or "Deneme Sitesi", "adres": adres}, headers=yonetici_basligi
    )
    assert yanit.status_code == 200, yanit.text
    return yanit.json()


async def _modul(istemci, yonetici_basligi, eposta, anahtar, acik=True):
    yanit = await istemci.put(f"{MODUL}/musteri/{eposta}/{anahtar}", json={"acik": acik}, headers=yonetici_basligi)
    assert yanit.status_code == 200, yanit.text


async def _bildirimler(db, olay, eposta=None, ref_id=None):
    from models.notifications import Notifications

    sorgu = select(Notifications).where(Notifications.event_type == olay, Notifications.channel == "inapp")
    if eposta:
        sorgu = sorgu.where(Notifications.recipient_email == eposta)
    if ref_id is not None:
        sorgu = sorgu.where(Notifications.ref_id == ref_id)
    return list((await db.execute(sorgu)).scalars().all())


async def _genel_kilidi_sifirla(db):
    from models.site_izleme import ZamanliCalisma

    await db.execute(
        update(ZamanliCalisma)
        .where(ZamanliCalisma.gorev == "__genel__")
        .values(son_baslangic=None, kilit_bitis=None)
    )
    await db.commit()


# ===========================================================================
# SSRF test kapısı — üretimde asla açık değil
# ===========================================================================
def test_test_kapisi_uretimde_kapali(monkeypatch):
    from services import site_analizi as sa

    monkeypatch.setenv("SSRF_TEST_IZINLI_HOSTLAR", "127.0.0.1")
    # ENVIRONMENT yok → üretim sayılıyor.
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert sa.uretim_mi() is True
    assert sa.test_izinli_hostlar() == frozenset()
    # Açıkça prod.
    monkeypatch.setenv("ENVIRONMENT", "prod")
    assert sa.test_izinli_hostlar() == frozenset()
    # Render'da ENVIRONMENT yanlışlıkla dev yazılsa bile kapalı.
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("RENDER", "true")
    assert sa.uretim_mi() is True
    assert sa.test_izinli_hostlar() == frozenset()
    # Yalnız üretim dışı + liste.
    monkeypatch.delenv("RENDER")
    monkeypatch.setenv("ENVIRONMENT", "test")
    assert sa.test_izinli_hostlar() == frozenset({"127.0.0.1"})


async def test_test_kapisi_yalniz_listelenen_ic_adresi_acar(monkeypatch):
    from services import site_analizi as sa

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SSRF_TEST_IZINLI_HOSTLAR", "127.0.0.1")
    await sa.adres_dogrula("http://127.0.0.1:8999/")  # hata yok
    with pytest.raises(sa.AnalizHatasi):
        await sa.adres_dogrula("http://10.0.0.8/")
    with pytest.raises(sa.AnalizHatasi):
        await sa.adres_dogrula("http://169.254.169.254/latest/meta-data")
    monkeypatch.setenv("ENVIRONMENT", "prod")
    with pytest.raises(sa.AnalizHatasi):
        await sa.adres_dogrula("http://127.0.0.1:8999/")


@pytest.mark.parametrize(
    "adres,kod",
    [
        ("http://127.0.0.1/", "adres_yasak"),
        ("http://169.254.169.254/latest", "adres_yasak"),
        ("http://localhost/", "adres_yasak"),
        ("http://127.0.0.1:8999/", "adres_gecersiz"),
        ("https://sunucu.ic-ag.test/", "adres_yasak"),
        ("ftp://ornek.com/", "adres_gecersiz"),
        ("http://kullanici:parola@ornek.com/", "adres_gecersiz"),
    ],
)
async def test_ic_adres_uptime_hedefi_olamaz(istemci, yonetici_basligi, adres, kod):
    site = await _site(istemci, yonetici_basligi, _eposta())
    yanit = await istemci.post(f"{BAKIM}/{site['id']}/uptime", json={"url": adres}, headers=yonetici_basligi)
    assert yanit.status_code == 400, yanit.text
    assert yanit.json()["detail"]["kod"] == kod


# ===========================================================================
# RDAP ayrıştırma (ağsız)
# ===========================================================================
RDAP_ORNEK = {
    "objectClassName": "domain",
    "ldhName": "EXAMPLE.COM",
    "events": [
        {"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"},
        {"eventAction": "expiration", "eventDate": "2027-08-13T04:00:00Z"},
        {"eventAction": "last update of RDAP database", "eventDate": "2026-09-30T10:11:12.1234567Z"},
    ],
}


def test_rdap_bitis_tarihi_ayristirilir():
    from services import site_izleme as si

    an = si.rdap_ayristir(RDAP_ORNEK)
    assert an == datetime(2027, 8, 13, 4, 0, tzinfo=timezone.utc)
    # Kayıt firması biçimi ve en geç tarih.
    veri = {"events": [{"eventAction": "registrar expiration", "eventDate": "2026-01-01"},
                       {"eventAction": "expiration", "eventDate": "2028-02-03T00:00:00+03:00"}]}
    assert si.rdap_ayristir(veri) == datetime(2028, 2, 2, 21, 0, tzinfo=timezone.utc)
    assert si.rdap_ayristir({"events": [{"eventAction": "registration", "eventDate": "2020-01-01"}]}) is None
    assert si.rdap_ayristir({"events": "bozuk"}) is None
    assert si.rdap_ayristir(None) is None
    assert si.rdap_ayristir({"events": [{"eventAction": "expiration", "eventDate": "saçma"}]}) is None


def test_kok_alan_ve_alan_dogrulama():
    from services import site_izleme as si

    assert si.kok_alan("www.magaza.ornek.com.tr") == "ornek.com.tr"
    assert si.kok_alan("blog.example.com") == "example.com"
    assert si.alan_adi_turet("https://www.ornek.co.uk/yol") == "ornek.co.uk"
    assert si.alan_adi_turet("http://93.184.216.34/") is None
    assert si.alan_adi_dogrula("https://WWW.Ornek.com/x") == "ornek.com"
    with pytest.raises(ValueError):
        si.alan_adi_dogrula("bosluklu alan")


async def test_rdap_tr_desteklenmiyor_ve_sahte_ag_uzerinden(monkeypatch, ag):
    from services import site_izleme as si

    # autouse sahteyi geri al: gerçek fonksiyon + sahte ağ.
    monkeypatch.undo()
    from services import site_analizi as sa

    async def dns(host, port):
        return [GENEL_IP]

    def isle(istek):
        if istek.url.host == "rdap.org":
            return httpx.Response(302, headers={"location": "https://rdap.kayit.test/domain/example.com"})
        return httpx.Response(200, json=RDAP_ORNEK, headers={"content-type": "application/rdap+json"})

    monkeypatch.setattr(sa, "_tasiyici_fabrikasi", lambda: httpx.MockTransport(isle))
    monkeypatch.setattr(sa, "_dns_cozumle", dns)
    assert await si.rdap_sorgula("ornek.com.tr") == (None, "desteklenmiyor")
    bitis, hata = await si.rdap_sorgula("example.com")
    assert hata is None and bitis == datetime(2027, 8, 13, 4, 0, tzinfo=timezone.utc)

    # Yönlendirme iç adrese giderse SSRF koruması durduruyor.
    def kotu(istek):
        return httpx.Response(302, headers={"location": "http://10.0.0.1/"})

    monkeypatch.setattr(sa, "_tasiyici_fabrikasi", lambda: httpx.MockTransport(kotu))
    assert await si.rdap_sorgula("example.com") == (None, "ulasilamadi")


# ===========================================================================
# Eşik bildirimleri — her eşik bir kez
# ===========================================================================
def test_esik_secimi_saf():
    from services import site_izleme as si

    assert si.esik_sec(40, si.ESIKLER, []) == (None, [])
    assert si.esik_sec(30, si.ESIKLER, []) == (30, [30])
    # 5 gün kala ilk kez görülen: tek "7" bildirimi, 30/15 de işaretlenir.
    assert si.esik_sec(5, si.ESIKLER, []) == (7, [7, 15, 30])
    assert si.esik_sec(5, si.ESIKLER, [7, 15, 30]) == (None, [])
    assert si.esik_sec(1, si.ESIKLER, [7, 15, 30]) == (1, [1])
    assert si.esik_sec(-3, si.ESIKLER, [7, 15, 30]) == (1, [1])
    assert si.esik_sec(-30, si.ESIKLER, []) == (None, [])
    # Otomatik SSL: 30 gün kala sessiz.
    assert si.esik_sec(20, si.OTOMATIK_SSL_ESIKLERI, []) == (None, [])


async def test_bitis_esikleri_bir_kez_ve_yenilenince_sifirlanir(istemci, yonetici_basligi, db_oturumu):
    from services import site_izleme as si

    eposta = _eposta("esik")
    site = await _site(istemci, yonetici_basligi, eposta)
    await _modul(istemci, yonetici_basligi, eposta, "yenileme")
    bitis = (datetime.now(timezone.utc) + timedelta(days=5)).date().isoformat()
    yanit = await istemci.put(f"{BAKIM}/{site['id']}", json={"hosting_bitis": bitis, "hosting_saglayici": "Örnek Host"},
                              headers=yonetici_basligi)
    assert yanit.status_code == 200, yanit.text
    assert yanit.json()["izleme"]["hosting_kalan"] in (4, 5)

    await si.yenileme_hatirlatmalari(db_oturumu)
    yonetici = await _bildirimler(db_oturumu, "bitis_yaklasiyor", "yonetici@test.dev", site["id"])
    musteri = await _bildirimler(db_oturumu, "bitis_yaklasiyor", eposta, site["id"])
    assert len(yonetici) == 1 and len(musteri) == 1
    assert "7" not in yonetici[0].title or "gün" in yonetici[0].title
    # İkinci tur: yeni bildirim yok.
    await si.yenileme_hatirlatmalari(db_oturumu)
    assert len(await _bildirimler(db_oturumu, "bitis_yaklasiyor", eposta, site["id"])) == 1

    # Yenilendi: bitiş ileri gitti → eşikler yeni tarih için sıfırdan.
    yeni = (datetime.now(timezone.utc) + timedelta(days=12)).date().isoformat()
    await istemci.put(f"{BAKIM}/{site['id']}", json={"hosting_bitis": yeni}, headers=yonetici_basligi)
    await si.yenileme_hatirlatmalari(db_oturumu)
    assert len(await _bildirimler(db_oturumu, "bitis_yaklasiyor", eposta, site["id"])) == 2


async def test_yenileme_modulu_kapaliysa_musteriye_hatirlatma_gitmez(istemci, yonetici_basligi, db_oturumu):
    from services import site_izleme as si

    eposta = _eposta("esik-kapali")
    site = await _site(istemci, yonetici_basligi, eposta)
    bitis = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
    await istemci.put(f"{BAKIM}/{site['id']}", json={"alan_bitis": bitis}, headers=yonetici_basligi)
    await si.yenileme_hatirlatmalari(db_oturumu)
    assert await _bildirimler(db_oturumu, "bitis_yaklasiyor", eposta, site["id"]) == []
    assert len(await _bildirimler(db_oturumu, "bitis_yaklasiyor", "yonetici@test.dev", site["id"])) == 1


# ===========================================================================
# Uptime — 2 ardışık hata → kesinti, düzelince kapanış + bildirim
# ===========================================================================
async def test_uptime_kesinti_acilir_kapanir_ve_bildirir(istemci, yonetici_basligi, musteri_basligi, db_oturumu, ag):
    from models.site_izleme import UptimeKesintisi, UptimeOlcumu
    from services import site_izleme as si

    eposta = _eposta("uptime")
    site = await _site(istemci, yonetici_basligi, eposta)
    await _modul(istemci, yonetici_basligi, eposta, "uptime")
    host = f"up-{uuid.uuid4().hex[:6]}.example.com"
    yanit = await istemci.post(f"{BAKIM}/{site['id']}/uptime", json={"url": f"https://{host}/", "aralik_dk": 5},
                               headers=yonetici_basligi)
    assert yanit.status_code == 200, yanit.text
    kontrol = yanit.json()
    assert kontrol["aralik_dk"] == 5 and kontrol["acik"] is True

    async def kesintiler():
        return list((await db_oturumu.execute(
            select(UptimeKesintisi).where(UptimeKesintisi.kontrol_id == kontrol["id"]))).scalars().all())

    await si.uptime_calistir(db_oturumu, zorla=True)  # başarılı
    ag.kapali.add(host)
    await si.uptime_calistir(db_oturumu, zorla=True)  # 1. hata: kesinti yok
    assert await kesintiler() == []
    assert await _bildirimler(db_oturumu, "site_coktu", eposta) == []
    await si.uptime_calistir(db_oturumu, zorla=True)  # 2. hata: kesinti
    ks = await kesintiler()
    assert len(ks) == 1 and ks[0].bitis is None and ks[0].sebep == "ulasilamadi"
    assert len(await _bildirimler(db_oturumu, "site_coktu", eposta)) == 1
    assert len(await _bildirimler(db_oturumu, "site_coktu", "yonetici@test.dev", ks[0].id)) == 1
    await si.uptime_calistir(db_oturumu, zorla=True)  # 3. hata: yeni kesinti/bildirim yok
    assert len(await kesintiler()) == 1
    assert len(await _bildirimler(db_oturumu, "site_coktu", eposta)) == 1

    ag.kapali.discard(host)
    await si.uptime_calistir(db_oturumu, zorla=True)  # düzeldi
    ks = await kesintiler()
    await db_oturumu.refresh(ks[0])
    assert ks[0].bitis is not None
    assert len(await _bildirimler(db_oturumu, "site_duzeldi", eposta)) == 1

    olcum_sayisi = (await db_oturumu.execute(
        select(func.count(UptimeOlcumu.id)).where(UptimeOlcumu.kontrol_id == kontrol["id"]))).scalar()
    assert olcum_sayisi == 5

    kart = (await istemci.get(f"{BAKIM}/{site['id']}", headers=yonetici_basligi)).json()
    assert kart["uptime"]["guncel"] == "calisiyor"
    assert kart["uptime"]["oran_24s"] == 40.0
    assert kart["uptime"]["kesintiler"][0]["sebep"] == "ulasilamadi"
    # Müşteri kartında iç kategori yok.
    musteri = (await istemci.get(MUSTERI, headers=musteri_basligi(eposta))).json()
    assert musteri[0]["uptime"]["oran_24s"] == 40.0
    assert "sebep" not in json.dumps(musteri[0]["uptime"])


async def test_uptime_anahtar_kelime_ve_beklenen_kod(istemci, yonetici_basligi, db_oturumu, ag):
    from models.site_izleme import UptimeOlcumu
    from services import site_izleme as si

    site = await _site(istemci, yonetici_basligi, _eposta())
    host = f"kw-{uuid.uuid4().hex[:6]}.example.com"
    ag.yanitlar[host] = (200, "<html>Bakımdayız</html>")
    k1 = (await istemci.post(f"{BAKIM}/{site['id']}/uptime",
                             json={"url": f"https://{host}/", "anahtar_kelime": "Sepete ekle"},
                             headers=yonetici_basligi)).json()
    await si.uptime_calistir(db_oturumu, zorla=True)
    olcum = (await db_oturumu.execute(select(UptimeOlcumu).where(UptimeOlcumu.kontrol_id == k1["id"]))).scalars().first()
    assert olcum.basarili is False and olcum.hata_ozeti == "anahtar_kelime_yok"

    ag.yanitlar[host] = (503, "hata")
    await istemci.patch(f"{BAKIM}/uptime/{k1['id']}", json={"anahtar_kelime": ""}, headers=yonetici_basligi)
    await si.uptime_calistir(db_oturumu, zorla=True)
    son = (await db_oturumu.execute(select(UptimeOlcumu).where(UptimeOlcumu.kontrol_id == k1["id"])
                                    .order_by(UptimeOlcumu.id.desc()))).scalars().first()
    assert son.hata_ozeti == "kod_503" and son.durum_kodu == 503


async def test_uptime_araligi_ve_dogrulama(istemci, yonetici_basligi, db_oturumu):
    from services import site_izleme as si

    site = await _site(istemci, yonetici_basligi, _eposta())
    kotu = await istemci.post(f"{BAKIM}/{site['id']}/uptime", json={"url": "https://ornek.com", "aralik_dk": 1},
                              headers=yonetici_basligi)
    assert kotu.status_code == 400 and kotu.json()["detail"]["kod"] == "aralik_gecersiz"
    kotu = await istemci.post(f"{BAKIM}/{site['id']}/uptime", json={"url": "https://ornek.com", "beklenen_kod": 999},
                              headers=yonetici_basligi)
    assert kotu.status_code == 400
    k = (await istemci.post(f"{BAKIM}/{site['id']}/uptime", json={"url": "https://ornek.com", "aralik_dk": 15},
                            headers=yonetici_basligi)).json()

    class K:
        aralik_dk = 15
        son_kontrol_at = datetime.now(timezone.utc) - timedelta(minutes=10)

    assert si.zamani_geldi_mi(K, datetime.now(timezone.utc), si.gecerli_aralik(K, None)) is False
    K.son_kontrol_at = datetime.now(timezone.utc) - timedelta(minutes=15)
    assert si.zamani_geldi_mi(K, datetime.now(timezone.utc), si.gecerli_aralik(K, None)) is True
    # Modül ayarı daha büyükse o geçerli.
    assert si.gecerli_aralik(K, 30) == 30
    sil = await istemci.delete(f"{BAKIM}/uptime/{k['id']}", headers=yonetici_basligi)
    assert sil.status_code == 200


# ===========================================================================
# Durum sayfası
# ===========================================================================
async def test_durum_sayfasi_yalniz_aciksa_ve_toplulastirma(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.site_izleme import UptimeGunluk, UptimeKesintisi, UptimeKontrolu, UptimeOlcumu
    from services import site_izleme as si

    eposta = _eposta("durum")
    site = await _site(istemci, yonetici_basligi, eposta, ad="Örnek Mağaza")
    k = UptimeKontrolu(site_id=site["id"], url="https://gizli-ic-yol.example.com/panel?anahtar=1", aralik_dk=5,
                       beklenen_kod=200, acik=True, ardisik_hata=0, son_durum="up",
                       son_kontrol_at=datetime.now(timezone.utc))
    db_oturumu.add(k)
    await db_oturumu.commit()
    bugun = si.tr_gunu(si.simdi())
    db_oturumu.add_all([
        UptimeGunluk(kontrol_id=k.id, site_id=site["id"], gun=bugun.isoformat(), toplam=100, basarili=99, toplam_sure_ms=1),
        UptimeGunluk(kontrol_id=k.id, site_id=site["id"], gun=(bugun - timedelta(days=1)).isoformat(),
                     toplam=100, basarili=50, toplam_sure_ms=1),
        UptimeGunluk(kontrol_id=k.id, site_id=site["id"], gun=(bugun - timedelta(days=40)).isoformat(),
                     toplam=10, basarili=10, toplam_sure_ms=1),
        UptimeOlcumu(kontrol_id=k.id, site_id=site["id"], zaman=si.simdi(), durum_kodu=503, sure_ms=10,
                     basarili=False, hata_ozeti="kod_503"),
        UptimeOlcumu(kontrol_id=k.id, site_id=site["id"], zaman=si.simdi(), durum_kodu=200, sure_ms=10, basarili=True),
        UptimeKesintisi(kontrol_id=k.id, site_id=site["id"], baslangic=si.simdi() - timedelta(hours=30),
                        bitis=si.simdi() - timedelta(hours=29), sebep="kod_503"),
    ])
    await db_oturumu.commit()

    # Kapalıyken: slug bile yok.
    kart = (await istemci.get(f"{BAKIM}/{site['id']}", headers=yonetici_basligi)).json()
    assert kart["durum_adresi"] is None

    # Müşteri uptime modülü kapalıyken açamaz.
    kapali = await istemci.post(f"{MUSTERI}/{site['id']}/durum-sayfasi", json={"acik": True},
                                headers=musteri_basligi(eposta))
    assert kapali.status_code == 403 and kapali.json()["detail"]["kod"] == "modul_kapali"
    await _modul(istemci, yonetici_basligi, eposta, "uptime")
    acik = await istemci.post(f"{MUSTERI}/{site['id']}/durum-sayfasi", json={"acik": True},
                              headers=musteri_basligi(eposta))
    assert acik.status_code == 200, acik.text
    slug = acik.json()["durum_slug"]
    assert slug.startswith("ornek-magaza-") and acik.json()["durum_adresi"] == f"/durum/{slug}"

    yanit = await istemci.get(f"{DURUM}/{slug}")
    assert yanit.status_code == 200
    assert yanit.headers.get("x-robots-tag") == "noindex, nofollow"
    govde = yanit.json()
    assert govde["ad"] == "Örnek Mağaza" and govde["index"] is False
    assert govde["guncel"] == "calisiyor"
    assert len(govde["gunler"]) == 90
    assert govde["gunler"][-1] == {"gun": bugun.isoformat(), "oran": 99.0}
    assert govde["gunler"][-2]["oran"] == 50.0
    assert govde["gunler"][-3]["oran"] is None
    assert govde["oran_7g"] == 74.5
    assert govde["oran_90g"] == round(100 * 159 / 210, 2)
    assert govde["oran_24s"] == 50.0
    assert govde["kesintiler"][0]["sure_dk"] == 60
    # İç ayrıntı sızmıyor.
    ham = yanit.text
    for yasak in ("gizli-ic-yol", "kod_503", "sebep", eposta, "kontrol_id", "client_email", "hata_ozeti", "503"):
        assert yasak not in ham, yasak

    # Müşteri dizine açtı → noindex başlığı yok.
    await istemci.post(f"{MUSTERI}/{site['id']}/durum-sayfasi", json={"acik": True, "index": True},
                       headers=musteri_basligi(eposta))
    yanit = await istemci.get(f"{DURUM}/{slug}")
    assert "x-robots-tag" not in yanit.headers and yanit.json()["index"] is True

    # Kapatınca 404; modül kapanınca da 404.
    await istemci.post(f"{MUSTERI}/{site['id']}/durum-sayfasi", json={"acik": False}, headers=musteri_basligi(eposta))
    assert (await istemci.get(f"{DURUM}/{slug}")).status_code == 404
    await istemci.post(f"{BAKIM}/{site['id']}/durum-sayfasi", json={"acik": True}, headers=yonetici_basligi)
    assert (await istemci.get(f"{DURUM}/{slug}")).status_code == 200
    await _modul(istemci, yonetici_basligi, eposta, "uptime", acik=False)
    assert (await istemci.get(f"{DURUM}/{slug}")).status_code == 404
    assert (await istemci.get(f"{DURUM}/olmayan-sayfa-123")).status_code == 404


# ===========================================================================
# Yenileme yöneticisi
# ===========================================================================
async def test_yenileme_listesi_fatura_ve_odeme_baglantisi(istemci, yonetici_basligi, db_oturumu):
    from models.invoices import Invoices

    eposta = _eposta("yenileme")
    site = await _site(istemci, yonetici_basligi, eposta, ad="Yenilenecek Site")
    bitis = (datetime.now(timezone.utc) + timedelta(days=20)).date().isoformat()
    await istemci.put(f"{BAKIM}/{site['id']}", json={"hosting_bitis": bitis, "hosting_saglayici": "HostX",
                                                      "alan_adi": "yenilenecek-site.com", "alan_bitis": bitis},
                      headers=yonetici_basligi)
    liste = (await istemci.get(YENILEME, params={"gun": 60}, headers=yonetici_basligi)).json()
    benim = [k for k in liste["kalemler"] if k["site_id"] == site["id"]]
    assert {k["tur"] for k in benim} == {"hosting", "alan"}
    hosting = next(k for k in benim if k["tur"] == "hosting")
    assert hosting["saglayici"] == "HostX" and hosting["fatura"] is None and hosting["kalan_gun"] in (19, 20)

    kotu = await istemci.post(f"{YENILEME}/fatura", json={"tur": "hosting", "ref_id": site["id"], "tutar": 0},
                              headers=yonetici_basligi)
    assert kotu.status_code == 400
    kotu = await istemci.post(f"{YENILEME}/fatura", json={"tur": "kahve", "ref_id": site["id"], "tutar": 10},
                              headers=yonetici_basligi)
    assert kotu.status_code == 400

    yanit = await istemci.post(f"{YENILEME}/fatura",
                               json={"tur": "hosting", "ref_id": site["id"], "tutar": 1250.5, "para_birimi": "TRY"},
                               headers=yonetici_basligi)
    assert yanit.status_code == 200, yanit.text
    fatura = yanit.json()
    assert fatura["adres"].startswith("/ode/") and fatura["mevcut"] is False
    kayit = (await db_oturumu.execute(select(Invoices).where(Invoices.id == fatura["invoice_id"]))).scalar_one()
    assert kayit.amount == 1250.5 and kayit.client_email == eposta and kayit.status == "pending"
    assert kayit.due_date == bitis

    # Ödeme sayfasının açık ucu faturayı gösteriyor.
    jeton = fatura["adres"].rsplit("/", 1)[1]
    ode = await istemci.get(f"/api/v1/odeme/{jeton}")
    assert ode.status_code == 200 and ode.json()["tutar"] == 1250.5

    # Müşteriye bildirim, bağlantı içinde.
    bildirim = await _bildirimler(db_oturumu, "yenileme_faturasi", eposta)
    assert len(bildirim) == 1 and fatura["adres"] in bildirim[0].body and bildirim[0].link == fatura["adres"]

    # Çift tıklama: aynı fatura döner.
    ikinci = (await istemci.post(f"{YENILEME}/fatura", json={"tur": "hosting", "ref_id": site["id"], "tutar": 1250.5},
                                 headers=yonetici_basligi)).json()
    assert ikinci["mevcut"] is True and ikinci["invoice_id"] == fatura["invoice_id"]

    liste = (await istemci.get(YENILEME, params={"gun": 60}, headers=yonetici_basligi)).json()
    hosting = next(k for k in liste["kalemler"] if k["site_id"] == site["id"] and k["tur"] == "hosting")
    assert hosting["fatura"]["invoice_no"] == fatura["invoice_no"]
    assert hosting["fatura"]["odeme_adresi"] == fatura["adres"]


async def test_abonelik_yenileme_tarihi():
    from datetime import date

    from services import site_izleme as si

    bugun = date(2026, 9, 30)
    assert si.abonelik_yenileme_tarihi("2026-03", "aylik", bugun) == date(2026, 10, 1)
    assert si.abonelik_yenileme_tarihi("2026-03", "aylik", date(2026, 10, 1)) == date(2026, 10, 1)
    assert si.abonelik_yenileme_tarihi("2026-12", "aylik", bugun) == date(2027, 1, 1)
    assert si.abonelik_yenileme_tarihi("2026-03", "yillik", bugun) == date(2027, 3, 1)
    assert si.abonelik_yenileme_tarihi("2025-10", "yillik", bugun) == date(2026, 10, 1)
    assert si.abonelik_yenileme_tarihi("2026-10", "yillik", bugun) == date(2027, 10, 1)
    assert si.abonelik_yenileme_tarihi("bozuk", "aylik", bugun) is None


# ===========================================================================
# Yetkiler ve modül bekçisi
# ===========================================================================
async def test_yetkiler(istemci, yonetici_basligi, musteri_basligi):
    eposta = _eposta("yetki")
    site = await _site(istemci, yonetici_basligi, eposta)
    baska = await _site(istemci, yonetici_basligi, _eposta("baska"))
    mb = musteri_basligi(eposta)

    for yontem, yol, govde in [
        ("GET", BAKIM, None),
        ("GET", f"{BAKIM}/{site['id']}", None),
        ("PUT", f"{BAKIM}/{site['id']}", {"notlar": "x"}),
        ("POST", f"{BAKIM}/{site['id']}/uptime", {"url": "https://ornek.com"}),
        ("POST", f"{BAKIM}/{site['id']}/tara", None),
        ("POST", f"{BAKIM}/{site['id']}/durum-sayfasi", {"acik": True}),
        ("GET", YENILEME, None),
        ("POST", f"{YENILEME}/fatura", {"tur": "hosting", "ref_id": site["id"], "tutar": 5}),
        ("GET", f"{ZAMANLI}/yonetim", None),
        ("POST", f"{ZAMANLI}/yonetim/calistir", None),
    ]:
        for baslik in (None, mb):
            yanit = await istemci.request(yontem, yol, json=govde, headers=baslik or {})
            assert yanit.status_code in (401, 403), (yontem, yol, yanit.status_code)

    assert (await istemci.get(MUSTERI)).status_code == 401
    kendi = (await istemci.get(MUSTERI, headers=mb)).json()
    assert [k["site_id"] for k in kendi] == [site["id"]]
    assert "notlar" not in kendi[0]["izleme"] and "kontroller" not in kendi[0]
    assert kendi[0]["uptime"] is None and kendi[0]["uptime_modulu"] is False

    # Başkasının sitesinin durum sayfası: 403 (modül açık olsa bile).
    await _modul(istemci, yonetici_basligi, eposta, "uptime")
    yanit = await istemci.post(f"{MUSTERI}/{baska['id']}/durum-sayfasi", json={"acik": True}, headers=mb)
    assert yanit.status_code == 403

    # Sitem modülü kapalıysa müşteri ucu 403 modul_kapali.
    await _modul(istemci, yonetici_basligi, eposta, "uptime", acik=False)
    await _modul(istemci, yonetici_basligi, eposta, "sitem", acik=False)
    yanit = await istemci.get(MUSTERI, headers=mb)
    assert yanit.status_code == 403 and yanit.json()["detail"]["kod"] == "modul_kapali"


# ===========================================================================
# Zamanlı uç — kısma, kilit, anahtar
# ===========================================================================
async def test_zamanli_kisma_ve_acik_yanitta_ayrinti_yok(istemci, yonetici_basligi, db_oturumu):
    from services import zamanli

    await _genel_kilidi_sifirla(db_oturumu)
    ilk = await istemci.post(f"{ZAMANLI}/calistir")
    assert ilk.status_code == 200, ilk.text
    govde = ilk.json()
    assert govde["atlandi"] is False
    assert [g["gorev"] for g in govde["gorevler"]] == zamanli.GOREV_ADLARI
    # Ayrıntı (özet/hata) anahtarı sızmıyor. (Faz 7O: görev adı "haftalik_ozet" alt dize olarak geçiyor;
    # denetim anahtar düzeyinde.)
    assert '"ozet"' not in ilk.text and '"hata"' not in ilk.text
    assert all(set(g) <= {"gorev", "calisti", "sure_ms", "basarili"} for g in govde["gorevler"])

    ikinci = await istemci.post(f"{ZAMANLI}/calistir")
    assert ikinci.status_code == 200 and ikinci.json() == {"atlandi": True, "sebep": "erken"}

    # Yönetici "şimdi çalıştır" 5 dk kuralını atlıyor ve ayrıntıyı görüyor.
    zorla = await istemci.post(f"{ZAMANLI}/yonetim/calistir", headers=yonetici_basligi)
    assert zorla.status_code == 200 and zorla.json()["atlandi"] is False
    liste = (await istemci.get(f"{ZAMANLI}/yonetim", headers=yonetici_basligi)).json()
    adlar = [g["gorev"] for g in liste["gorevler"]]
    assert adlar == zamanli.GOREV_ADLARI
    uptime = liste["gorevler"][0]
    assert uptime["son_calisma"] and uptime["calisma_sayisi"] >= 2 and uptime["hata"] is None
    assert liste["genel"]["calisiyor"] is False


async def test_zamanli_kilit_calisan_turu_ezmez(istemci, db_oturumu):
    from core.database import db_manager
    from models.site_izleme import ZamanliCalisma
    from services import zamanli

    await _genel_kilidi_sifirla(db_oturumu)
    await db_oturumu.execute(
        update(ZamanliCalisma).where(ZamanliCalisma.gorev == "__genel__")
        .values(kilit_bitis=datetime.now(timezone.utc) + timedelta(minutes=5))
    )
    await db_oturumu.commit()
    yanit = await istemci.post(f"{ZAMANLI}/calistir")
    assert yanit.json() == {"atlandi": True, "sebep": "calisiyor"}
    # Zorla bile çalışan turu ezmiyor.
    async with db_manager.async_session_maker() as s:
        assert await zamanli.kilidi_al(s, zorla=True) == "calisiyor"

    # Aynı anda iki çağrı: yalnız biri kilidi alıyor.
    await _genel_kilidi_sifirla(db_oturumu)

    async def dene():
        async with db_manager.async_session_maker() as s:
            return await zamanli.kilidi_al(s)

    sonuclar = await asyncio.gather(dene(), dene(), dene())
    assert sorted(sonuclar, key=str) == sorted([None, "calisiyor", "calisiyor"], key=str)
    await _genel_kilidi_sifirla(db_oturumu)


async def test_zamanli_anahtar(istemci, db_oturumu, monkeypatch):
    await _genel_kilidi_sifirla(db_oturumu)
    monkeypatch.setenv("ZAMANLI_ANAHTAR", "cok-gizli-anahtar")
    assert (await istemci.post(f"{ZAMANLI}/calistir")).status_code == 401
    assert (await istemci.post(f"{ZAMANLI}/calistir", headers={"X-Zamanli-Anahtar": "yanlis"})).status_code == 401
    yanit = await istemci.post(f"{ZAMANLI}/calistir", headers={"X-Zamanli-Anahtar": "cok-gizli-anahtar"})
    assert yanit.status_code == 200 and yanit.json()["atlandi"] is False
    await _genel_kilidi_sifirla(db_oturumu)


async def test_zamanli_bir_gorevin_hatasi_digerlerini_durdurmaz(istemci, yonetici_basligi, db_oturumu, monkeypatch):
    from services import zamanli

    async def patla(db, zorla):
        raise RuntimeError("deneme hatası")

    gorevler = list(zamanli.GOREVLER)
    gorevler[1] = zamanli.Gorev(gorevler[1].ad, gorevler[1].siklik, patla)
    monkeypatch.setattr(zamanli, "GOREVLER", gorevler)
    await _genel_kilidi_sifirla(db_oturumu)
    yanit = (await istemci.post(f"{ZAMANLI}/calistir")).json()
    durumlar = {g["gorev"]: g for g in yanit["gorevler"]}
    assert durumlar[gorevler[1].ad]["basarili"] is False
    assert "deneme hatası" not in json.dumps(yanit)
    liste = (await istemci.get(f"{ZAMANLI}/yonetim", headers=yonetici_basligi)).json()
    satir = next(g for g in liste["gorevler"] if g["gorev"] == gorevler[1].ad)
    assert "deneme hatası" in satir["hata"]
    await _genel_kilidi_sifirla(db_oturumu)


# ===========================================================================
# Temizlik
# ===========================================================================
async def test_eski_olcumler_ve_analizler_temizlenir(db_oturumu):
    from models.site_analyses import Site_analyses
    from models.site_izleme import UptimeOlcumu
    from services import site_analizi_temizlik, site_izleme as si

    an = si.simdi()
    eski = UptimeOlcumu(kontrol_id=987654, site_id=987654, zaman=an - timedelta(days=91), basarili=True)
    yeni = UptimeOlcumu(kontrol_id=987654, site_id=987654, zaman=an - timedelta(days=1), basarili=True)
    eski_analiz = Site_analyses(alan_adi="eski-temizlik.com", url="https://eski-temizlik.com/", durum="tamam",
                                kaynak="acik", created_at=an - timedelta(days=120), kvkk_onay=False)
    yeni_analiz = Site_analyses(alan_adi="yeni-temizlik.com", url="https://yeni-temizlik.com/", durum="tamam",
                                kaynak="acik", created_at=an - timedelta(days=5), kvkk_onay=False)
    takili = Site_analyses(alan_adi="takili-temizlik.com", url="https://takili-temizlik.com/", durum="calisiyor",
                           kaynak="musteri", created_at=an - timedelta(hours=3), kvkk_onay=False)
    db_oturumu.add_all([eski, yeni, eski_analiz, yeni_analiz, takili])
    await db_oturumu.commit()

    sonuc = await si.olcum_temizligi(db_oturumu)
    assert sonuc["olcum_silinen"] >= 1
    kalan = (await db_oturumu.execute(select(UptimeOlcumu).where(UptimeOlcumu.kontrol_id == 987654))).scalars().all()
    assert [o.id for o in kalan] == [yeni.id]

    sonuc = await site_analizi_temizlik.eski_analizleri_temizle(db_oturumu)
    assert sonuc["silinen"] >= 1 and sonuc["takili_duzeltilen"] >= 1
    adlar = {a.alan_adi: a for a in (await db_oturumu.execute(
        select(Site_analyses).where(Site_analyses.alan_adi.like("%-temizlik.com")))).scalars().all()}
    assert "eski-temizlik.com" not in adlar and "yeni-temizlik.com" in adlar
    await db_oturumu.refresh(adlar["takili-temizlik.com"])
    assert adlar["takili-temizlik.com"].durum == "hata"


# ===========================================================================
# Bitiş taraması, denetim, katalog
# ===========================================================================
async def test_bitis_taramasi_ve_elle_tarih_ezilmez(istemci, yonetici_basligi, db_oturumu):
    from models.site_izleme import SiteIzleme
    from services import site_izleme as si

    site = await _site(istemci, yonetici_basligi, _eposta("tarama"), adres="https://www.tarama-deneme.com")
    kart = (await istemci.post(f"{BAKIM}/{site['id']}/tara", headers=yonetici_basligi)).json()
    assert kart["izleme"]["alan_adi"] == "tarama-deneme.com"
    assert kart["izleme"]["alan_bitis_kaynak"] == "rdap" and 195 <= kart["izleme"]["alan_kalan"] <= 200
    assert 75 <= kart["izleme"]["ssl_kalan"] <= 80

    elle = (datetime.now(timezone.utc) + timedelta(days=10)).date().isoformat()
    kart = (await istemci.put(f"{BAKIM}/{site['id']}", json={"alan_bitis": elle}, headers=yonetici_basligi)).json()
    assert kart["izleme"]["alan_bitis_kaynak"] == "elle"
    await db_oturumu.execute(update(SiteIzleme).where(SiteIzleme.site_id == site["id"]).values(alan_kontrol_at=None))
    await db_oturumu.commit()
    await si.bitis_taramasi(db_oturumu)
    kart = (await istemci.get(f"{BAKIM}/{site['id']}", headers=yonetici_basligi)).json()
    assert kart["izleme"]["alan_bitis"].startswith(elle)


async def test_denetim_ayar_degisikligini_yazar_olcum_durumunu_yazmaz(istemci, yonetici_basligi, db_oturumu):
    from models.audit_log import AuditLog
    from services import site_izleme as si

    site = await _site(istemci, yonetici_basligi, _eposta("denetim"))
    await istemci.put(f"{BAKIM}/{site['id']}", json={"hosting_saglayici": "Denetim Host"}, headers=yonetici_basligi)
    k = (await istemci.post(f"{BAKIM}/{site['id']}/uptime", json={"url": "https://denetim-deneme.com"},
                            headers=yonetici_basligi)).json()
    satirlar = (await db_oturumu.execute(select(AuditLog).where(AuditLog.tablo.in_(("site_izleme", "uptime_kontrolleri")))
                                         .order_by(AuditLog.id))).scalars().all()
    assert any("Denetim Host" in (s.degisiklik_json or "") for s in satirlar)
    assert any(s.tablo == "uptime_kontrolleri" and s.islem == "olustur" and str(k["id"]) == s.kayit_id for s in satirlar)
    once = len(satirlar)
    await si.uptime_calistir(db_oturumu, zorla=True)
    sonra = (await db_oturumu.execute(select(func.count(AuditLog.id))
                                      .where(AuditLog.tablo.in_(("uptime_kontrolleri", "uptime_olculeri", "uptime_gunluk"))))
             ).scalar()
    kontrol_satiri = (await db_oturumu.execute(select(func.count(AuditLog.id)).where(AuditLog.tablo == "uptime_kontrolleri"))).scalar()
    assert kontrol_satiri == len([s for s in satirlar if s.tablo == "uptime_kontrolleri"])
    assert sonra == kontrol_satiri
    assert once >= 2


def test_bildirim_katalogu_ve_etiketler():
    from pathlib import Path

    from services.bildirim_tercih import OLAYLAR

    kok = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek"
    for olay in ("site_coktu", "site_duzeldi", "bitis_yaklasiyor", "yenileme_faturasi"):
        assert OLAYLAR[olay]["tetikleniyor"] is True
        for dil in ("tr", "en", "de", "ru", "zh", "hi", "ar"):
            ek = json.loads((kok / "bildirim" / f"{dil}.json").read_text(encoding="utf-8"))
            assert ek["bildirim"]["olay"][olay], (dil, olay)
    tr = json.loads((kok / "bildirim" / "tr.json").read_text(encoding="utf-8"))["bildirim"]["olay"]
    for dil in ("de", "ru", "zh", "hi", "ar"):
        ek = json.loads((kok / "bildirim" / f"{dil}.json").read_text(encoding="utf-8"))["bildirim"]["olay"]
        assert ek["site_coktu"] != tr["site_coktu"]


def test_manifest_faz2a():
    from core import moduller as mf

    uptime = mf.modul("uptime")
    yenileme = mf.modul("yenileme")
    assert uptime.durum == "yayinda" and uptime.bagimliliklar == ("sitem",)
    assert yenileme.kategori == "hizmet" and set(yenileme.bagimliliklar) == {"sitem", "faturalar"}
    assert mf.manifest_hatalari() == []


def test_github_zamanli_is_akisi():
    from pathlib import Path

    yol = Path(__file__).resolve().parents[4] / ".github" / "workflows" / "zamanli.yml"
    metin = yol.read_text(encoding="utf-8")
    assert "*/10 * * * *" in metin
    assert "/api/v1/zamanli/calistir" in metin
    assert "X-Zamanli-Anahtar" in metin and "secrets.ZAMANLI_ANAHTAR" in metin
    assert "|| true" in metin and "60" in metin


def test_site_bakim_ek_paketi_yedi_dilde_ayni_anahtarlar_ve_gercek_ceviri():
    from pathlib import Path

    kok = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek" / "siteBakim"

    def duz(d, on=""):
        for k, v in d.items():
            if isinstance(v, dict):
                yield from duz(v, f"{on}{k}.")
            else:
                yield f"{on}{k}", v

    paketler = {dil: dict(duz(json.loads((kok / f"{dil}.json").read_text(encoding="utf-8"))["siteBakim"]))
                for dil in ("tr", "en", "de", "ru", "zh", "hi", "ar")}
    anahtarlar = set(paketler["tr"])
    for dil, p in paketler.items():
        assert set(p) == anahtarlar, dil
        assert all(isinstance(v, str) and v.strip() for v in p.values()), dil
    for dil in ("en", "de", "ru", "zh", "hi", "ar"):
        ayni = [k for k in anahtarlar if paketler[dil][k] == paketler["tr"][k] and len(paketler["tr"][k]) > 12]
        assert not ayni, (dil, ayni[:5])
    # Arayüzün kullandığı görev adları sunucudaki kayıt listesiyle aynı.
    from services.zamanli import GOREV_ADLARI

    assert {k.split(".")[-1] for k in anahtarlar if k.startswith("zamanli.gorev.")} == set(GOREV_ADLARI)
