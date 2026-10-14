"""Parti 13 — Meta bağlantısı: OAuth (state), şifreli jeton kasası, sayfa seçimi, eşitleme.

Meta'ya hiç gidilmiyor: `services.meta_baglanti._ag_istegi` her testte `SahteMeta`
ile değiştiriliyor. Sahte, çağrıları kaydediyor ve `_sahte_yanit`'taki
belgelenmiş Graph biçimlerinde yanıt veriyor.
"""

import base64
import json
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import delete, select

SIFRE_ANAHTARI = base64.urlsafe_b64encode(b"m" * 32).decode()
UYGULAMA = "123456789012345"
UYGULAMA_SIRRI = "meta-uygulama-sirri-test"
TABAN = "/api/v1/baglantilar"


class SahteMeta:
    def __init__(self):
        self.cagrilar = []
        self.jeton_gecersiz = False
        self.ig_takip_hatasi = True  # 100 takipçi altı: follows_and_unfollows hata verir
        self.reddedilen_metrik = None

    def say(self, parca: str) -> int:
        return sum(1 for c in self.cagrilar if parca in c["url"])

    async def __call__(self, yontem, url, *, parametreler=None, jeton=None):
        from services import meta_baglanti as mb

        parametreler = parametreler or {}
        self.cagrilar.append({"yontem": yontem, "url": url, "params": dict(parametreler), "jeton": jeton})
        yol = url.split(f"/{mb.graph_surumu()}/", 1)[-1]
        if self.jeton_gecersiz and jeton and yol != "oauth/access_token":
            return mb.MetaYaniti(400, {"error": {"code": 190, "type": "OAuthException", "message": "Session expired"}})
        if yol.endswith("/insights") and parametreler.get("metric") == self.reddedilen_metrik:
            return mb.MetaYaniti(400, {"error": {"code": 100, "message": "(#100) invalid metric"}})
        if yol.endswith("/insights") and parametreler.get("metric") == "follows_and_unfollows" and self.ig_takip_hatasi:
            return mb.MetaYaniti(400, {"error": {"code": 100, "message": "not enough followers"}})
        return mb._sahte_yanit(yontem, url, parametreler)


@pytest.fixture
def kurulu(monkeypatch):
    monkeypatch.setenv("META_APP_ID", UYGULAMA)
    monkeypatch.setenv("META_APP_SECRET", UYGULAMA_SIRRI)
    monkeypatch.setenv("BAGLANTI_SIFRE_ANAHTARI", SIFRE_ANAHTARI)
    monkeypatch.delenv("META_CONFIG_ID", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("RENDER", raising=False)


@pytest.fixture
def meta(monkeypatch):
    from services import meta_baglanti as mb

    sahte = SahteMeta()
    monkeypatch.setattr(mb, "_ag_istegi", sahte)
    return sahte


@pytest.fixture(autouse=True)
async def _temiz(db_oturumu):
    from models.analytics_snapshots import Analytics_snapshots
    from models.baglantilar import Baglanti, BaglantiDurumu
    from models.notifications import Notifications

    for model in (Baglanti, BaglantiDurumu):
        await db_oturumu.execute(delete(model))
    await db_oturumu.execute(delete(Analytics_snapshots))
    await db_oturumu.execute(delete(Notifications).where(Notifications.event_type == "baglanti_koptu"))
    await db_oturumu.commit()
    yield


async def _baglan(istemci, yonetici_basligi):
    y = await istemci.post(f"{TABAN}/meta/baslat", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    q = {k: v[0] for k, v in parse_qs(urlparse(y.json()["adres"]).query).items()}
    y = await istemci.get(f"{TABAN}/meta/geri-donus", params={"code": "AQ-kod", "state": q["state"]})
    assert y.status_code == 302, y.text
    assert y.headers["location"].endswith("/admin?sekme=baglantilar&sonuc=meta_baglandi"), y.headers["location"]
    return q


async def _meta_satiri(db_oturumu):
    from models.baglantilar import Baglanti

    db_oturumu.expire_all()
    return (await db_oturumu.execute(select(Baglanti).where(Baglanti.saglayici == "meta"))).scalar_one_or_none()


YONETICI_UCLARI = [
    ("POST", f"{TABAN}/meta/baslat"),
    ("GET", f"{TABAN}/meta/kaynaklar"),
    ("PUT", f"{TABAN}/meta/secim"),
    ("POST", f"{TABAN}/meta/esitle"),
    ("DELETE", f"{TABAN}/meta"),
]


@pytest.mark.parametrize("metot,yol", YONETICI_UCLARI)
async def test_yetki_anonim_401_musteri_403(istemci, musteri_basligi, metot, yol, kurulu):
    govde = {"json": {}} if metot in ("POST", "PUT") else {}
    assert (await istemci.request(metot, yol, **govde)).status_code == 401
    y = await istemci.request(metot, yol, headers=musteri_basligi("musteri@test.dev"), **govde)
    assert y.status_code == 403 and y.json()["detail"]["kod"] == "yonetici_gerekli"


async def test_kurulum_eksikse_kurulmadi_ve_deger_donmuyor(istemci, yonetici_basligi, monkeypatch, meta):
    monkeypatch.setenv("META_APP_ID", UYGULAMA)
    monkeypatch.delenv("META_APP_SECRET", raising=False)
    y = await istemci.get(TABAN, headers=yonetici_basligi)
    m = next(s for s in y.json()["saglayicilar"] if s["saglayici"] == "meta")
    assert m["durum"] == "kurulmadi"
    assert set(m["kurulum"]["eksik"]) >= {"META_APP_SECRET"}
    assert UYGULAMA not in y.text
    y = await istemci.post(f"{TABAN}/meta/baslat", headers=yonetici_basligi)
    assert y.status_code == 503 and y.json()["detail"]["kod"] == "kurulmadi"


async def test_onay_adresi_izinler_ve_state(istemci, yonetici_basligi, kurulu, meta):
    y = await istemci.post(f"{TABAN}/meta/baslat", headers=yonetici_basligi)
    adres = urlparse(y.json()["adres"])
    q = {k: v[0] for k, v in parse_qs(adres.query).items()}
    assert adres.netloc == "www.facebook.com" and adres.path.endswith("/dialog/oauth")
    assert q["client_id"] == UYGULAMA
    assert q["redirect_uri"] == "https://mehmetkuru.dev/api/v1/baglantilar/meta/geri-donus"
    assert set(q["scope"].split(",")) >= {"pages_show_list", "read_insights", "instagram_manage_insights"}
    assert len(q["state"]) >= 40
    assert meta.cagrilar == []


async def test_yapilandirma_kimligi_varsa_config_id(istemci, yonetici_basligi, kurulu, meta, monkeypatch):
    monkeypatch.setenv("META_CONFIG_ID", "998877665544")
    y = await istemci.post(f"{TABAN}/meta/baslat", headers=yonetici_basligi)
    q = parse_qs(urlparse(y.json()["adres"]).query)
    assert q["config_id"] == ["998877665544"] and "scope" not in q


async def test_geri_donus_state_zorunlu_ve_saglayiciya_bagli(istemci, yonetici_basligi, kurulu, meta, monkeypatch):
    for parametreler in ({}, {"code": "x"}, {"code": "x", "state": "uydurma"}):
        y = await istemci.get(f"{TABAN}/meta/geri-donus", params=parametreler)
        assert y.headers["location"].endswith("sonuc=meta_durum_gecersiz")
        assert y.headers["cache-control"] == "no-store"
    # Google'ın state'i Meta geri dönüşünde geçmiyor.
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "x.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "s")
    gy = await istemci.post(f"{TABAN}/google/baslat", headers=yonetici_basligi)
    gstate = parse_qs(urlparse(gy.json()["adres"]).query)["state"][0]
    y = await istemci.get(f"{TABAN}/meta/geri-donus", params={"code": "x", "state": gstate})
    assert y.headers["location"].endswith("sonuc=meta_durum_gecersiz")
    # ... tersi de: Meta state'i Google geri dönüşünde geçmiyor.
    my = await istemci.post(f"{TABAN}/meta/baslat", headers=yonetici_basligi)
    mstate = parse_qs(urlparse(my.json()["adres"]).query)["state"][0]
    y = await istemci.get(f"{TABAN}/google/geri-donus", params={"code": "x", "state": mstate})
    assert y.headers["location"].endswith("sonuc=durum_gecersiz")
    assert meta.cagrilar == []


async def test_reddedilirse_kayit_yok(istemci, yonetici_basligi, kurulu, meta, db_oturumu):
    y = await istemci.post(f"{TABAN}/meta/baslat", headers=yonetici_basligi)
    state = parse_qs(urlparse(y.json()["adres"]).query)["state"][0]
    y = await istemci.get(f"{TABAN}/meta/geri-donus", params={"error": "access_denied", "state": state})
    assert y.headers["location"].endswith("sonuc=meta_reddedildi")
    assert await _meta_satiri(db_oturumu) is None


async def test_baglan_sec_esitle_uctan_uca(istemci, yonetici_basligi, kurulu, meta, db_oturumu):
    await _baglan(istemci, yonetici_basligi)
    b = await _meta_satiri(db_oturumu)
    assert b.durum == "bagli" and b.harici_email == "Test Ajans"
    # Jetonlar yalnız şifreli: satırda düz jeton yok.
    assert "sahte-meta-" not in (b.sifreli_yenileme_jetonu or "") and "sahte-meta-" not in (b.secimler or "")
    # Uzun ömürlü jetona çevrildi (iki oauth çağrısı: kod + fb_exchange_token).
    takaslar = [c for c in meta.cagrilar if c["url"].endswith("oauth/access_token")]
    assert len(takaslar) == 2 and takaslar[1]["params"]["grant_type"] == "fb_exchange_token"
    # Jeton adreste değil başlıkta; appsecret_proof ile.
    me = next(c for c in meta.cagrilar if c["url"].endswith("/me"))
    assert me["jeton"] and "access_token" not in me["params"] and len(me["params"]["appsecret_proof"]) == 64

    durum = (await istemci.get(TABAN, headers=yonetici_basligi)).json()
    m = next(s for s in durum["saglayicilar"] if s["saglayici"] == "meta")
    assert m["durum"] == "bagli" and m["harici_ad"] == "Test Ajans" and m["kapsamlar"] == {"fb": True, "ig": True}
    assert "sahte-" not in json.dumps(durum)

    k = (await istemci.get(f"{TABAN}/meta/kaynaklar", headers=yonetici_basligi)).json()
    assert k["fb"] == [{"kimlik": "100000000000001", "ad": "Test Sayfa"}]
    assert k["ig"] == [{"kimlik": "17841400000000001", "ad": "@test.ajans — Test Sayfa"}]
    assert "sahte-sayfa-jetonu" not in json.dumps(k)

    y = await istemci.put(f"{TABAN}/meta/secim", json={"fb_sayfa": "999999999", "ig_hesap": None}, headers=yonetici_basligi)
    assert y.status_code == 422 and y.json()["detail"] == {"kod": "secim_gecersiz", "alan": "fb_sayfa"}
    y = await istemci.put(f"{TABAN}/meta/secim", json={"fb_sayfa": "abc"}, headers=yonetici_basligi)
    assert y.status_code == 422
    y = await istemci.put(
        f"{TABAN}/meta/secim", json={"fb_sayfa": "100000000000001", "ig_hesap": "17841400000000001"}, headers=yonetici_basligi
    )
    assert y.status_code == 200 and y.json()["secimler"] == {"fb_sayfa": "100000000000001", "ig_hesap": "17841400000000001"}
    b = await _meta_satiri(db_oturumu)
    assert "sahte-sayfa-jetonu" not in (b.sifreli_yenileme_jetonu or "")

    meta.cagrilar.clear()
    y = await istemci.post(f"{TABAN}/meta/esitle", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    sonuc = y.json()
    assert sonuc["kaynaklar"] == ["fb", "ig"] and sonuc["hatalar"] == {}
    # Eşitleme yalnız sayfa jetonuyla.
    assert {c["jeton"] for c in meta.cagrilar} == {"sahte-sayfa-jetonu"}

    pano = (await istemci.get(f"{TABAN}/pano", headers=yonetici_basligi)).json()
    sosyal = next(k for k in pano["kanallar"] if k["kanal"] == "social")
    assert sosyal["ornek"] is False and sosyal["kaynaklar"] == ["meta"]
    deger = {m["metric_key"]: m for m in sosyal["metrikler"]}
    # Facebook günlük 400 görüntülenme × 28 + Instagram 9000; etkileşim 30×28 + 640.
    assert deger["followers"]["metric_value"] == 1200 + 830
    assert deger["views"]["metric_value"] == 400 * 28 + 9000
    assert deger["interactions"]["metric_value"] == 30 * 28 + 640
    # Instagram 100 takipçi altında: yeni takipçi yalnız Facebook'tan.
    assert deger["new_followers"]["metric_value"] == 2 * 28
    assert deger["followers"]["change_pct"] == round(56 / (2030 - 56) * 100, 1)


async def test_instagram_takip_olcumu_varsa_eklenir_ve_bir_olcum_hatasi_digerlerini_durdurmaz(
    istemci, yonetici_basligi, kurulu, meta
):
    meta.ig_takip_hatasi = False
    meta.reddedilen_metrik = "page_post_engagements"
    await _baglan(istemci, yonetici_basligi)
    await istemci.put(f"{TABAN}/meta/secim", json={"fb_sayfa": "100000000000001", "ig_hesap": "17841400000000001"},
                      headers=yonetici_basligi)
    sonuc = (await istemci.post(f"{TABAN}/meta/esitle", headers=yonetici_basligi)).json()
    assert sonuc["hatalar"] == {"fb": "gecersiz_istek"}
    pano = (await istemci.get(f"{TABAN}/pano", headers=yonetici_basligi)).json()
    deger = {m["metric_key"]: m["metric_value"] for m in next(k for k in pano["kanallar"] if k["kanal"] == "social")["metrikler"]}
    assert deger["new_followers"] == 2 * 28 + 25
    assert deger["interactions"] == 640  # Facebook etkileşimi gelmedi, Instagram'ınki yazıldı


async def test_jeton_gecersizse_yeniden_baglan_ve_tek_bildirim(istemci, yonetici_basligi, kurulu, meta, db_oturumu):
    from models.notifications import Notifications

    await _baglan(istemci, yonetici_basligi)
    await istemci.put(f"{TABAN}/meta/secim", json={"fb_sayfa": "100000000000001"}, headers=yonetici_basligi)
    meta.jeton_gecersiz = True
    y = await istemci.post(f"{TABAN}/meta/esitle", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "yeniden_baglan"
    b = await _meta_satiri(db_oturumu)
    assert b.durum == "yeniden_baglan"
    bildirimler = (await db_oturumu.execute(
        select(Notifications).where(Notifications.event_type == "baglanti_koptu"))).scalars().all()
    assert bildirimler and all("Meta" in (n.title or "") for n in bildirimler)
    # Yeniden bağlanınca durum düzelir, seçim korunur (aynı Facebook kullanıcısı).
    meta.jeton_gecersiz = False
    await _baglan(istemci, yonetici_basligi)
    b = await _meta_satiri(db_oturumu)
    assert b.durum == "bagli" and json.loads(b.secimler)["fb_sayfa"] == "100000000000001"


async def test_kaldir_izni_geri_alir_ve_siler(istemci, yonetici_basligi, kurulu, meta, db_oturumu):
    await _baglan(istemci, yonetici_basligi)
    y = await istemci.delete(f"{TABAN}/meta", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json() == {"silindi": True, "iptal_edildi": True}
    assert any(c["yontem"] == "DELETE" and c["url"].endswith("me/permissions") for c in meta.cagrilar)
    assert await _meta_satiri(db_oturumu) is None
    y = await istemci.delete(f"{TABAN}/meta", headers=yonetici_basligi)
    assert y.status_code == 404


async def test_elle_esitleme_siniri_ve_secimsiz(istemci, yonetici_basligi, kurulu, meta):
    await _baglan(istemci, yonetici_basligi)
    y = await istemci.post(f"{TABAN}/meta/esitle", headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "secim_yok"
    await istemci.put(f"{TABAN}/meta/secim", json={"fb_sayfa": "100000000000001"}, headers=yonetici_basligi)
    assert (await istemci.post(f"{TABAN}/meta/esitle", headers=yonetici_basligi)).status_code == 200
    y = await istemci.post(f"{TABAN}/meta/esitle", headers=yonetici_basligi)
    assert y.status_code == 429 and y.json()["detail"]["kod"] == "cok_sik"


async def test_zamanli_esitleme_baglantilari_gezer(kurulu, meta, istemci, yonetici_basligi, db_oturumu):
    from services import meta_baglanti as mb

    await _baglan(istemci, yonetici_basligi)
    await istemci.put(f"{TABAN}/meta/secim", json={"ig_hesap": "17841400000000001"}, headers=yonetici_basligi)
    ozet = await mb.zamanli_esitleme(db_oturumu)
    assert ozet["baglanti"] == 1 and ozet["yazilan"] >= 3


def test_gunluk_topla_bitis_gunune_gore_pencere():
    from datetime import date

    from services import meta_baglanti as mb

    veri = {"data": [{"values": [
        {"value": 5, "end_time": "2026-10-02T07:00:00+0000"},  # 1 Ekim → önceki
        {"value": 7, "end_time": "2026-10-03T07:00:00+0000"},  # 2 Ekim → şimdiki
    ]}]}
    assert mb.gunluk_topla(veri, date(2026, 10, 2)) == (7.0, 5.0)


def test_hata_kodlari():
    from services import meta_baglanti as mb

    def k(durum, kod):
        return mb.hata_kodu(mb.MetaYaniti(durum, {"error": {"code": kod}}))

    assert k(400, 190) == "yetki_yok"
    assert k(400, 10) == "kapsam_yok" and k(403, 200) == "kapsam_yok"
    assert k(400, 4) == "kota" and k(400, 80001) == "kota"
    assert k(400, 100) == "gecersiz_istek"
    assert k(500, 1) == "meta_hatasi"
