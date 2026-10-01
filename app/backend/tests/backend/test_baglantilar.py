"""Faz 3B — Bağlantılar: Google OAuth (state + PKCE), şifreli jeton, eşitleme, pano.

Google'a hiç gidilmiyor: `services.baglantilar._ag_istegi` her testte
`SahteGoogle` ile değiştiriliyor (conftest varsayılanı "ağ yok"). Sahte,
gelen isteği kaydediyor ve belgelenmiş Google yanıt biçimlerinde yanıt veriyor.
"""

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import delete, func, select

SIFRE_ANAHTARI = base64.urlsafe_b64encode(b"t" * 32).decode()
ISTEMCI = "istemci-123.apps.googleusercontent.com"
ISTEMCI_SIRRI = "gizli-istemci-sirri-test"
YENILEME = "1//yenileme-jetonu-duz-metin-ABCDEF"
GOOGLE_EPOSTA = "ajans.google@gmail.test"
TABAN = "/api/v1/baglantilar"


def _id_jetonu(eposta: str) -> str:
    def b64(v: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(v).encode()).rstrip(b"=").decode()

    return f"{b64({'alg': 'RS256'})}.{b64({'email': eposta, 'email_verified': True})}.imza"


class SahteGoogle:
    """`_ag_istegi` yerine geçer; çağrıları kaydeder."""

    def __init__(self):
        self.cagrilar = []
        self.yenileme_hatasi = None  # ör. "invalid_grant"
        self.iptal_durumu = 200
        self.ga4_durumu = 200
        self.kapsam = " ".join([
            "openid", "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/analytics.readonly",
            "https://www.googleapis.com/auth/webmasters.readonly",
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/yt-analytics.readonly",
        ])

    def say(self, url_parcasi: str) -> int:
        return sum(1 for c in self.cagrilar if url_parcasi in c["url"])

    async def __call__(self, yontem, url, *, form=None, json_govde=None, parametreler=None, jeton=None):
        from services import baglantilar as bg

        self.cagrilar.append({"yontem": yontem, "url": url, "form": form, "json": json_govde, "params": parametreler, "jeton": jeton})
        if url == bg.JETON_ADRESI:
            if form.get("grant_type") == "authorization_code":
                return bg.GoogleYaniti(200, {
                    "access_token": "erisim-1", "expires_in": 3599, "refresh_token": YENILEME,
                    "scope": self.kapsam, "token_type": "Bearer", "id_token": _id_jetonu(GOOGLE_EPOSTA),
                })
            if self.yenileme_hatasi:
                return bg.GoogleYaniti(400, {"error": self.yenileme_hatasi, "error_description": "Token has been expired or revoked."})
            return bg.GoogleYaniti(200, {"access_token": "erisim-2", "expires_in": 3599, "token_type": "Bearer"})
        if url == bg.IPTAL_ADRESI:
            return bg.GoogleYaniti(self.iptal_durumu, {} if self.iptal_durumu == 200 else {"error": "invalid_request"})
        if ":runReport" in url and self.ga4_durumu != 200:
            return bg.GoogleYaniti(self.ga4_durumu, {"error": {"code": 403, "status": "PERMISSION_DENIED", "details": [
                {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "SERVICE_DISABLED"}]}})
        # Diğer uçlar: belgelenmiş biçimdeki sabit yanıtlar (ENVIRONMENT=test sahtesiyle aynı veri).
        return bg._sahte_yanit(yontem, url, form, json_govde, parametreler)


@pytest.fixture
def kurulu(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", ISTEMCI)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", ISTEMCI_SIRRI)
    monkeypatch.setenv("BAGLANTI_SIFRE_ANAHTARI", SIFRE_ANAHTARI)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("RENDER", raising=False)


@pytest.fixture
def google(monkeypatch):
    from services import baglantilar as bg

    sahte = SahteGoogle()
    monkeypatch.setattr(bg, "_ag_istegi", sahte)
    return sahte


@pytest.fixture(autouse=True)
async def _temiz(db_oturumu):
    from models.analytics_snapshots import Analytics_snapshots
    from models.baglantilar import AnalitikListesi, Baglanti, BaglantiDurumu
    from models.notifications import Notifications
    from services import baglantilar as bg

    for model in (Baglanti, BaglantiDurumu, AnalitikListesi):
        await db_oturumu.execute(delete(model))
    await db_oturumu.execute(delete(Analytics_snapshots))
    await db_oturumu.execute(delete(Notifications).where(Notifications.event_type == "baglanti_koptu"))
    await db_oturumu.commit()
    bg.bellegi_temizle()
    yield
    bg.bellegi_temizle()


async def _baslat(istemci, yonetici_basligi):
    y = await istemci.post(f"{TABAN}/google/baslat", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    adres = y.json()["adres"]
    return adres, {k: v[0] for k, v in parse_qs(urlparse(adres).query).items()}


async def _baglan(istemci, yonetici_basligi):
    _, q = await _baslat(istemci, yonetici_basligi)
    y = await istemci.get(f"{TABAN}/google/geri-donus", params={"code": "4/kod", "state": q["state"]})
    assert y.status_code == 302, y.text
    assert y.headers["location"].endswith("/admin?sekme=baglantilar&sonuc=baglandi"), y.headers["location"]
    return q


async def _sec(istemci, yonetici_basligi, **secim):
    govde = {"ga4_mulk": "properties/111111111", "sc_site": "sc-domain:mehmetkuru.dev", "yt_kanal": "UCsahteKanal0123456789ab"}
    govde.update(secim)
    y = await istemci.put(f"{TABAN}/google/secim", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    return y.json()


async def _denemeyi_sifirla(db_oturumu):
    from models.baglantilar import Baglanti
    from sqlalchemy import update

    await db_oturumu.execute(update(Baglanti).values(son_deneme=None))
    await db_oturumu.commit()


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------
YONETICI_UCLARI = [
    ("GET", TABAN),
    ("GET", f"{TABAN}/pano"),
    ("POST", f"{TABAN}/google/baslat"),
    ("GET", f"{TABAN}/google/kaynaklar"),
    ("PUT", f"{TABAN}/google/secim"),
    ("POST", f"{TABAN}/google/esitle"),
    ("DELETE", f"{TABAN}/google"),
]


@pytest.mark.parametrize("metot,yol", YONETICI_UCLARI)
async def test_yetki_anonim_401_musteri_403(istemci, musteri_basligi, metot, yol, kurulu):
    govde = {"json": {}} if metot in ("POST", "PUT") else {}
    assert (await istemci.request(metot, yol, **govde)).status_code == 401
    y = await istemci.request(metot, yol, headers=musteri_basligi("musteri@test.dev"), **govde)
    assert y.status_code == 403 and y.json()["detail"]["kod"] == "yonetici_gerekli"


async def test_geri_donus_girissiz_ama_state_zorunlu(istemci, kurulu, google):
    for parametreler in ({}, {"code": "x"}, {"code": "x", "state": "uydurma-state"}):
        y = await istemci.get(f"{TABAN}/google/geri-donus", params=parametreler)
        assert y.status_code == 302
        assert y.headers["location"] == "https://mehmetkuru.dev/admin?sekme=baglantilar&sonuc=durum_gecersiz"
        assert y.headers["cache-control"] == "no-store"
    assert google.cagrilar == []  # state yoksa Google'a kod gönderilmiyor


# ---------------------------------------------------------------------------
# Kurulum
# ---------------------------------------------------------------------------
async def test_ortam_degiskeni_eksikken_kurulmadi(istemci, yonetici_basligi, monkeypatch, google):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", ISTEMCI)
    y = await istemci.get(TABAN, headers=yonetici_basligi)
    assert y.status_code == 200
    g = y.json()["saglayicilar"][0]
    assert g["saglayici"] == "google" and g["durum"] == "kurulmadi"
    assert g["kurulum"] == {"kurulu": False, "eksik": ["GOOGLE_OAUTH_CLIENT_SECRET", "BAGLANTI_SIFRE_ANAHTARI"], "gecersiz": []}
    assert ISTEMCI not in y.text  # değerler asla dönmüyor
    assert [s["durum"] for s in y.json()["saglayicilar"][1:]] == ["yakinda", "yakinda"]
    assert y.json()["yonlendirme_adresi"] == "https://mehmetkuru.dev/api/v1/baglantilar/google/geri-donus"
    y = await istemci.post(f"{TABAN}/google/baslat", headers=yonetici_basligi)
    assert y.status_code == 503 and y.json()["detail"]["kod"] == "kurulmadi"
    # Geçersiz Fernet anahtarı da "kurulmadı" (adıyla, değeri olmadan).
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", ISTEMCI_SIRRI)
    monkeypatch.setenv("BAGLANTI_SIFRE_ANAHTARI", "kisa-gecersiz-anahtar")
    g = (await istemci.get(TABAN, headers=yonetici_basligi)).json()["saglayicilar"][0]
    assert g["durum"] == "kurulmadi" and g["kurulum"]["gecersiz"] == ["BAGLANTI_SIFRE_ANAHTARI"]
    assert "kisa-gecersiz-anahtar" not in json.dumps(g)
    assert google.cagrilar == []


# ---------------------------------------------------------------------------
# OAuth: adres, state, PKCE
# ---------------------------------------------------------------------------
async def test_baslat_adresi_parametreleri(istemci, yonetici_basligi, kurulu, db_oturumu):
    from models.baglantilar import BaglantiDurumu
    from services import baglantilar as bg

    adres, q = await _baslat(istemci, yonetici_basligi)
    assert adres.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert q["client_id"] == ISTEMCI
    assert q["redirect_uri"] == "https://mehmetkuru.dev/api/v1/baglantilar/google/geri-donus"
    assert q["response_type"] == "code"
    assert q["access_type"] == "offline" and q["prompt"] == "consent" and q["include_granted_scopes"] == "true"
    assert q["code_challenge_method"] == "S256" and len(q["code_challenge"]) == 43
    assert set(q["scope"].split()) == {
        "openid", "email",
        "https://www.googleapis.com/auth/analytics.readonly",
        "https://www.googleapis.com/auth/webmasters.readonly",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    }
    assert ISTEMCI_SIRRI not in adres
    # Veritabanında state'in kendisi değil özeti; doğrulayıcı şifreli; 10 dk.
    db_oturumu.expire_all()
    kayit = (await db_oturumu.execute(select(BaglantiDurumu))).scalar_one()
    assert kayit.durum_ozeti == hashlib.sha256(q["state"].encode()).hexdigest()
    assert q["state"] not in (kayit.durum_ozeti + kayit.sifreli_dogrulayici)
    dogrulayici = bg.coz(kayit.sifreli_dogrulayici)
    assert dogrulayici not in kayit.sifreli_dogrulayici
    assert bg.pkce_meydan_okumasi(dogrulayici) == q["code_challenge"]
    son = kayit.son_kullanma.replace(tzinfo=timezone.utc) if kayit.son_kullanma.tzinfo is None else kayit.son_kullanma
    assert timedelta(minutes=9) < son - datetime.now(timezone.utc) <= timedelta(minutes=10)
    assert kayit.baslatan_email == "yonetici@test.dev"


async def test_pkce_dogrulayici_gonderiliyor_ve_state_tek_kullanimlik(istemci, yonetici_basligi, kurulu, google):
    _, q = await _baslat(istemci, yonetici_basligi)
    y = await istemci.get(f"{TABAN}/google/geri-donus", params={"code": "4/kod-1", "state": q["state"]})
    assert y.headers["location"].endswith("sonuc=baglandi")
    takas = [c for c in google.cagrilar if c["form"] and c["form"].get("grant_type") == "authorization_code"]
    assert len(takas) == 1
    form = takas[0]["form"]
    assert form["code"] == "4/kod-1" and form["client_id"] == ISTEMCI and form["client_secret"] == ISTEMCI_SIRRI
    assert form["redirect_uri"] == q["redirect_uri"]
    beklenen = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode()
    assert beklenen == q["code_challenge"]
    # İkinci kullanım reddediliyor; Google'a ikinci kez gidilmiyor.
    y = await istemci.get(f"{TABAN}/google/geri-donus", params={"code": "4/kod-1", "state": q["state"]})
    assert y.headers["location"].endswith("sonuc=durum_gecersiz")
    assert len([c for c in google.cagrilar if c["form"] and c["form"].get("grant_type") == "authorization_code"]) == 1


async def test_state_suresi_dolunca_reddedilir(istemci, yonetici_basligi, kurulu, google, db_oturumu):
    from models.baglantilar import BaglantiDurumu
    from sqlalchemy import update

    _, q = await _baslat(istemci, yonetici_basligi)
    await db_oturumu.execute(update(BaglantiDurumu).values(son_kullanma=datetime.now(timezone.utc) - timedelta(seconds=1)))
    await db_oturumu.commit()
    y = await istemci.get(f"{TABAN}/google/geri-donus", params={"code": "4/kod", "state": q["state"]})
    assert y.headers["location"].endswith("sonuc=durum_gecersiz")
    assert google.cagrilar == []


async def test_kullanici_reddederse_kisa_kod_ham_metin_yok(istemci, yonetici_basligi, kurulu, google):
    _, q = await _baslat(istemci, yonetici_basligi)
    y = await istemci.get(f"{TABAN}/google/geri-donus", params={"error": "access_denied", "state": q["state"]})
    assert y.headers["location"] == "https://mehmetkuru.dev/admin?sekme=baglantilar&sonuc=reddedildi"
    _, q = await _baslat(istemci, yonetici_basligi)
    y = await istemci.get(
        f"{TABAN}/google/geri-donus", params={"error": "<script>alert(1)</script>", "state": q["state"]}
    )
    assert y.headers["location"].endswith("sonuc=google_hatasi") and "script" not in y.headers["location"]


async def test_jeton_sifreli_saklaniyor_duz_metin_yok(istemci, yonetici_basligi, kurulu, google, db_oturumu):
    from core.database import db_manager
    from models.baglantilar import Baglanti
    from services import baglantilar as bg
    from sqlalchemy import text

    await _baglan(istemci, yonetici_basligi)
    db_oturumu.expire_all()
    b = (await db_oturumu.execute(select(Baglanti))).scalar_one()
    assert b.hesap_email is None and b.sahip_anahtari == "__ajans__"
    assert b.harici_email == GOOGLE_EPOSTA
    assert b.durum == "bagli"
    assert YENILEME not in (b.sifreli_yenileme_jetonu or "")
    assert bg.coz(b.sifreli_yenileme_jetonu) == YENILEME
    # Ham veritabanında (bütün tablolar) ne yenileme ne erişim jetonu düz metin var.
    async with db_manager.engine.connect() as conn:
        tablolar = [r[0] for r in (await conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
        for tablo in tablolar:
            for satir in (await conn.execute(text(f'SELECT * FROM "{tablo}"'))).fetchall():
                ham = " ".join(str(v) for v in satir)
                assert YENILEME not in ham, tablo
                assert "erisim-1" not in ham, tablo
    # Durum ucu jeton/şifreli değer döndürmüyor.
    y = await istemci.get(TABAN, headers=yonetici_basligi)
    assert y.json()["saglayicilar"][0]["durum"] == "bagli"
    assert y.json()["saglayicilar"][0]["harici_email"] == GOOGLE_EPOSTA
    assert b.sifreli_yenileme_jetonu not in y.text and YENILEME not in y.text


async def test_denetimde_jeton_alanlari_maskeli(istemci, yonetici_basligi, kurulu, google, db_oturumu):
    from models.audit_log import AuditLog

    ilk = (await db_oturumu.execute(select(func.max(AuditLog.id)))).scalar() or 0
    await _baglan(istemci, yonetici_basligi)
    db_oturumu.expire_all()
    satirlar = list((await db_oturumu.execute(
        select(AuditLog).where(AuditLog.id > ilk, AuditLog.tablo == "baglantilar")
    )).scalars().all())
    assert satirlar and satirlar[0].islem == "olustur"
    # Geri dönüş girişsiz geliyor; aktör akışı başlatan yönetici.
    assert satirlar[0].aktor_eposta == "yonetici@test.dev" and satirlar[0].aktor_rol == "admin"
    fark = json.loads(satirlar[0].degisiklik_json)
    assert fark["sifreli_yenileme_jetonu"] == [None, "***"]
    from models.baglantilar import Baglanti

    b = (await db_oturumu.execute(select(Baglanti))).scalar_one()
    for s in satirlar:
        ham = (s.degisiklik_json or "") + (s.ozet or "")
        assert YENILEME not in ham and b.sifreli_yenileme_jetonu not in ham
    # State satırları denetime hiç girmiyor (teknik iz).
    assert not (await db_oturumu.execute(
        select(AuditLog).where(AuditLog.id > ilk, AuditLog.tablo == "baglanti_durumlari")
    )).scalars().first()
    from services.denetim import hassas_mi

    assert hassas_mi("sifreli_yenileme_jetonu") and hassas_mi("sifreli_dogrulayici")


# ---------------------------------------------------------------------------
# Kaynaklar ve seçim
# ---------------------------------------------------------------------------
async def test_kaynaklar_ve_secim_kaydi(istemci, yonetici_basligi, kurulu, google):
    y = await istemci.get(f"{TABAN}/google/kaynaklar", headers=yonetici_basligi)
    assert y.status_code == 404 and y.json()["detail"]["kod"] == "bagli_degil"
    await _baglan(istemci, yonetici_basligi)
    y = await istemci.get(f"{TABAN}/google/kaynaklar", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    k = y.json()
    assert [m["kimlik"] for m in k["ga4"]] == ["properties/111111111", "properties/222222222"]
    assert k["ga4"][0]["ad"] == "mehmetkuru.dev (test) — Test Ajans"
    assert [s["kimlik"] for s in k["sc"]] == ["sc-domain:mehmetkuru.dev", "https://ornek.test/"]
    assert k["yt"] == [{"kimlik": "UCsahteKanal0123456789ab", "ad": "Test Kanal"}]
    assert k["hatalar"] == {}
    # Erişim jetonu bellekte: kaynak çağrıları Bearer ile, yenileme isteği yok.
    assert all(c["jeton"] == "erisim-1" for c in google.cagrilar if c["url"] != "https://oauth2.googleapis.com/token")
    yt = next(c for c in google.cagrilar if "youtube/v3/channels" in c["url"])
    assert yt["params"]["mine"] == "true"

    s = await _sec(istemci, yonetici_basligi)
    assert s["secimler"] == {"ga4_mulk": "properties/111111111", "sc_site": "sc-domain:mehmetkuru.dev", "yt_kanal": "UCsahteKanal0123456789ab"}
    # Kısmi güncelleme ve temizleme.
    y = await istemci.put(f"{TABAN}/google/secim", json={"yt_kanal": None}, headers=yonetici_basligi)
    assert y.json()["secimler"]["yt_kanal"] is None and y.json()["secimler"]["ga4_mulk"] == "properties/111111111"
    for alan, deger in (("ga4_mulk", "123"), ("sc_site", "javascript:alert(1)"), ("yt_kanal", "../x")):
        y = await istemci.put(f"{TABAN}/google/secim", json={alan: deger}, headers=yonetici_basligi)
        assert y.status_code == 422 and y.json()["detail"] == {"kod": "secim_gecersiz", "alan": alan}
    d = (await istemci.get(TABAN, headers=yonetici_basligi)).json()["saglayicilar"][0]
    assert d["secimler"]["ga4_mulk"] == "properties/111111111" and d["secimler"]["yt_kanal"] is None


# ---------------------------------------------------------------------------
# Eşitleme
# ---------------------------------------------------------------------------
def _satir_haritasi(satirlar):
    return {(s.kaynak, s.channel, s.metric_key): s for s in satirlar}


async def test_esitleme_dogru_metrikleri_yazar_ve_cogaltmaz(istemci, yonetici_basligi, kurulu, google, db_oturumu):
    from models.analytics_snapshots import Analytics_snapshots
    from models.baglantilar import AnalitikListesi

    await _baglan(istemci, yonetici_basligi)
    y = await istemci.post(f"{TABAN}/google/esitle", headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "secim_yok"
    await _sec(istemci, yonetici_basligi)
    y = await istemci.post(f"{TABAN}/google/esitle", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    sonuc = y.json()
    assert sonuc["hatalar"] == {} and sorted(sonuc["kaynaklar"]) == ["ga4", "sc", "yt"]
    assert sonuc["yazilan"] == 13
    assert sonuc["durum"]["saglayicilar"][0]["son_esitleme"]

    db_oturumu.expire_all()
    satirlar = (await db_oturumu.execute(select(Analytics_snapshots))).scalars().all()
    assert len(satirlar) == 13
    h = _satir_haritasi(satirlar)
    bugun = datetime.now(timezone.utc).date().isoformat()
    assert all(s.snapshot_date == bugun for s in satirlar)
    # GA4: 1234 vs 1000 oturum → +23,4 %; hemen çıkma 41,3 % (0,4125); etkileşim 79800/950 = 84 sn.
    assert h[("google_analytics", "traffic", "sessions")].metric_value == 1234
    assert h[("google_analytics", "traffic", "sessions")].change_pct == 23.4
    assert h[("google_analytics", "traffic", "users")].metric_value == 987
    assert h[("google_analytics", "traffic", "pageviews")].metric_value == 3456
    hc = h[("google_analytics", "traffic", "bounce_rate")]
    assert hc.metric_value == 41.2 and hc.unit == "%" and hc.change_pct == -8.4
    sure = h[("google_analytics", "traffic", "avg_engagement_time")]
    assert sure.metric_value == 84 and sure.unit == "sn" and sure.change_pct == 12.0
    # Search Console: 28 gün × 30 tık = 840 (önceki 28 × 25 = 700 → +20 %), 28 000 gösterim, TO 3 %, sıra 11,5.
    assert h[("search_console", "seo", "organic_clicks")].metric_value == 840
    assert h[("search_console", "seo", "organic_clicks")].change_pct == 20.0
    assert h[("search_console", "seo", "impressions")].metric_value == 28000
    assert h[("search_console", "seo", "ctr")].metric_value == 3.0
    assert h[("search_console", "seo", "avg_position")].metric_value == 11.5
    assert h[("search_console", "seo", "avg_position")].change_pct == -11.5
    # YouTube: abone 1520 (pencerede net +56 → 1464'ten +3,8 %), görüntülenme 28×120, izlenme 28×300 dk, yeni abone 28×3.
    assert h[("youtube", "youtube", "subscribers")].metric_value == 1520
    assert h[("youtube", "youtube", "subscribers")].change_pct == 3.8
    assert h[("youtube", "youtube", "views")].metric_value == 3360 and h[("youtube", "youtube", "views")].change_pct == 20.0
    assert h[("youtube", "youtube", "watch_time")].metric_value == 8400 and h[("youtube", "youtube", "watch_time")].unit == "dk"
    assert h[("youtube", "youtube", "subscribers_gained")].metric_value == 84
    # İstekler: GA4 iki adlı aralık; SC günlük + sorgu + sayfa; YT channel==<kanal>.
    ga = next(c for c in google.cagrilar if ":runReport" in c["url"])
    assert ga["url"].endswith("/properties/111111111:runReport")
    assert [r["name"] for r in ga["json"]["dateRanges"]] == ["simdi", "onceki"]
    sc = [c for c in google.cagrilar if "searchAnalytics" in c["url"]]
    assert {tuple(c["json"]["dimensions"]) for c in sc} == {("date",), ("query",), ("page",)}
    assert "sc-domain%3Amehmetkuru.dev" in sc[0]["url"]
    ytr = next(c for c in google.cagrilar if "youtubeanalytics" in c["url"])
    assert ytr["params"]["ids"] == "channel==UCsahteKanal0123456789ab"
    # Listeler: en çok tıklanan 10 sorgu ve 10 sayfa.
    listeler = {l.tur: json.loads(l.veri) for l in (await db_oturumu.execute(select(AnalitikListesi))).scalars().all()}
    assert len(listeler["sorgular"]) == 10 and listeler["sorgular"][0]["anahtar"] == "test sorgusu 1"
    assert listeler["sorgular"][0]["tiklama"] == 100 and listeler["sorgular"][0]["to"] == 5.0
    assert len(listeler["sayfalar"]) == 10

    # Tekrar çalıştırma: 10 dk sınırı; sınır kalkınca aynı gün GÜNCELLENİR, çoğalmaz.
    y = await istemci.post(f"{TABAN}/google/esitle", headers=yonetici_basligi)
    assert y.status_code == 429 and y.json()["detail"]["kod"] == "cok_sik" and y.json()["detail"]["kalan_sn"] > 500
    await _denemeyi_sifirla(db_oturumu)
    google.ga4_durumu = 200
    y = await istemci.post(f"{TABAN}/google/esitle", headers=yonetici_basligi)
    assert y.status_code == 200
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(func.count()).select_from(Analytics_snapshots))).scalar() == 13
    assert (await db_oturumu.execute(select(func.count()).select_from(AnalitikListesi))).scalar() == 2


async def test_bir_kaynak_hata_verirse_digerleri_yazilir(istemci, yonetici_basligi, kurulu, google, db_oturumu):
    from models.analytics_snapshots import Analytics_snapshots

    await _baglan(istemci, yonetici_basligi)
    await _sec(istemci, yonetici_basligi)
    google.ga4_durumu = 403
    y = await istemci.post(f"{TABAN}/google/esitle", headers=yonetici_basligi)
    assert y.status_code == 200
    assert y.json()["hatalar"] == {"ga4": "api_kapali"}
    assert sorted(y.json()["kaynaklar"]) == ["sc", "yt"]
    d = y.json()["durum"]["saglayicilar"][0]
    assert d["son_hata"] == {"ga4": "api_kapali"} and d["durum"] == "bagli"
    db_oturumu.expire_all()
    kaynaklar = {s.kaynak for s in (await db_oturumu.execute(select(Analytics_snapshots))).scalars().all()}
    assert kaynaklar == {"search_console", "youtube"}


async def test_reddedilen_kapsam_atlanir(istemci, yonetici_basligi, kurulu, google):
    google.kapsam = "openid https://www.googleapis.com/auth/webmasters.readonly"
    await _baglan(istemci, yonetici_basligi)
    d = (await istemci.get(TABAN, headers=yonetici_basligi)).json()["saglayicilar"][0]
    assert d["kapsamlar"] == {"ga4": False, "sc": True, "yt": False}
    k = (await istemci.get(f"{TABAN}/google/kaynaklar", headers=yonetici_basligi)).json()
    assert k["hatalar"] == {"ga4": "kapsam_yok", "yt": "kapsam_yok"} and k["sc"]
    assert google.say("analyticsadmin") == 0 and google.say("youtube/v3") == 0
    await _sec(istemci, yonetici_basligi)
    y = await istemci.post(f"{TABAN}/google/esitle", headers=yonetici_basligi)
    assert y.json()["kaynaklar"] == ["sc"] and y.json()["hatalar"] == {"ga4": "kapsam_yok", "yt": "kapsam_yok"}


async def test_invalid_grant_yeniden_baglan_ve_tek_bildirim(istemci, yonetici_basligi, kurulu, google, db_oturumu):
    from models.notifications import Notifications
    from services import baglantilar as bg

    await _baglan(istemci, yonetici_basligi)
    await _sec(istemci, yonetici_basligi)
    bg.bellegi_temizle()  # erişim jetonu süresi doldu → yenileme jetonu kullanılacak
    google.yenileme_hatasi = "invalid_grant"
    y = await istemci.post(f"{TABAN}/google/esitle", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "yeniden_baglan"
    yenileme = [c for c in google.cagrilar if c["form"] and c["form"].get("grant_type") == "refresh_token"]
    assert yenileme and yenileme[0]["form"]["refresh_token"] == YENILEME
    d = (await istemci.get(TABAN, headers=yonetici_basligi)).json()["saglayicilar"][0]
    assert d["durum"] == "yeniden_baglan" and d["son_hata"] == {"genel": "invalid_grant"}

    async def bildirim_sayisi():
        db_oturumu.expire_all()
        return (await db_oturumu.execute(
            select(func.count()).select_from(Notifications).where(
                Notifications.event_type == "baglanti_koptu", Notifications.channel == "inapp"
            )
        )).scalar()

    from services.notify import admin_recipients

    yonetici_sayisi = len(await admin_recipients(db_oturumu))
    assert yonetici_sayisi >= 1
    assert await bildirim_sayisi() == yonetici_sayisi
    n = (await db_oturumu.execute(select(Notifications).where(Notifications.event_type == "baglanti_koptu"))).scalars().first()
    assert n.recipient_role == "admin" and n.link == "/admin?sekme=baglantilar"
    # Zamanlı tur ve tekrar denemeler bildirimi çoğaltmıyor (yeniden_baglan durumunda Google'a da gidilmiyor).
    await _denemeyi_sifirla(db_oturumu)
    y = await istemci.post(f"{TABAN}/google/esitle", headers=yonetici_basligi)
    assert y.status_code == 409
    from services.google_esitleme import zamanli_esitleme

    assert (await zamanli_esitleme(db_oturumu))["baglanti"] == 0
    assert await bildirim_sayisi() == yonetici_sayisi
    # Yeniden bağlanınca durum düzelir; sonraki kopuşta yine bir bildirim.
    google.yenileme_hatasi = None
    await _baglan(istemci, yonetici_basligi)
    d = (await istemci.get(TABAN, headers=yonetici_basligi)).json()["saglayicilar"][0]
    assert d["durum"] == "bagli" and d["son_hata"] == {}
    assert d["secimler"]["ga4_mulk"] == "properties/111111111"  # aynı Google hesabı: seçim korunur
    bg.bellegi_temizle()
    google.yenileme_hatasi = "invalid_grant"
    await _denemeyi_sifirla(db_oturumu)
    await istemci.post(f"{TABAN}/google/esitle", headers=yonetici_basligi)
    assert await bildirim_sayisi() == 2 * yonetici_sayisi


async def test_baglanti_kaldirma_revoke_cagirir(istemci, yonetici_basligi, kurulu, google, db_oturumu, monkeypatch):
    from models.baglantilar import Baglanti

    y = await istemci.delete(f"{TABAN}/google", headers=yonetici_basligi)
    assert y.status_code == 404
    await _baglan(istemci, yonetici_basligi)
    y = await istemci.delete(f"{TABAN}/google", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json() == {"silindi": True, "iptal_edildi": True}
    iptal = [c for c in google.cagrilar if c["url"] == "https://oauth2.googleapis.com/revoke"]
    assert len(iptal) == 1 and iptal[0]["form"] == {"token": YENILEME} and iptal[0]["yontem"] == "POST"
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(Baglanti))).scalars().first() is None
    d = (await istemci.get(TABAN, headers=yonetici_basligi)).json()["saglayicilar"][0]
    assert d["durum"] == "bagli_degil" and d["harici_email"] is None
    # Google ulaşılamazsa da kayıt silinir; yanıt "iptal edilemedi" der.
    await _baglan(istemci, yonetici_basligi)
    from services import baglantilar as bg

    async def ag_yok(*a, **k):
        raise httpx.ConnectError("yok")

    monkeypatch.setattr(bg, "_ag_istegi", ag_yok)
    y = await istemci.delete(f"{TABAN}/google", headers=yonetici_basligi)
    assert y.json() == {"silindi": True, "iptal_edildi": False}
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(Baglanti))).scalars().first() is None


async def test_zamanli_gorev_kayitli_ve_esitler(istemci, yonetici_basligi, kurulu, google, db_oturumu):
    from models.analytics_snapshots import Analytics_snapshots
    from services import zamanli
    from services.google_esitleme import zamanli_esitleme

    adlar = zamanli.GOREV_ADLARI
    assert "google_esitleme" in adlar and adlar[-1] == "aylik_site_analizi"
    gorev = next(g for g in zamanli.GOREVLER if g.ad == "google_esitleme")
    assert gorev.siklik == timedelta(hours=6)
    assert await zamanli_esitleme(db_oturumu) == {"baglanti": 0, "yazilan": 0, "hata": 0}
    await _baglan(istemci, yonetici_basligi)
    await _sec(istemci, yonetici_basligi, yt_kanal=None)
    ozet = await zamanli_esitleme(db_oturumu)
    assert ozet == {"baglanti": 1, "yazilan": 9, "hata": 0}
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(func.count()).select_from(Analytics_snapshots))).scalar() == 9


async def test_zamanli_kurulmadiysa_atlar(db_oturumu):
    from services.google_esitleme import zamanli_esitleme

    assert await zamanli_esitleme(db_oturumu) == {"atlandi": "kurulmadi"}


# ---------------------------------------------------------------------------
# Örnek veri: işaretleme ve pano
# ---------------------------------------------------------------------------
async def test_ornek_isaretleme_idempotent_gercek_veriye_dokunmaz(db_oturumu):
    from core.database import db_manager
    from models.analytics_snapshots import Analytics_snapshots
    from services.mock_data import _analitik_ornek_kayitlari, analitik_orneklerini_isaretle

    kayitlar = _analitik_ornek_kayitlari()
    assert len(kayitlar) == 16 and all(k["kaynak"] == "ornek" for k in kayitlar)
    # Eski canlı durum: mock satırlar kaynaksız yüklenmiş.
    for k in kayitlar:
        db_oturumu.add(Analytics_snapshots(**{a: v for a, v in k.items() if a != "kaynak"}))
    # Gerçek veri: elle girilmiş (kaynaksız, farklı değer) ve Google'dan gelen (mock değerleriyle aynı bile olsa).
    db_oturumu.add(Analytics_snapshots(channel="traffic", metric_key="sessions", metric_value=777, snapshot_date="2026-09-01"))
    db_oturumu.add(Analytics_snapshots(channel="traffic", metric_key="sessions", metric_value=18432,
                                       snapshot_date="2026-09-01", kaynak="google_analytics"))
    await db_oturumu.commit()

    assert await analitik_orneklerini_isaretle(db_manager.engine) == 16
    assert await analitik_orneklerini_isaretle(db_manager.engine) == 0  # idempotent
    db_oturumu.expire_all()
    satirlar = (await db_oturumu.execute(select(Analytics_snapshots))).scalars().all()
    say = {}
    for s in satirlar:
        say[s.kaynak] = say.get(s.kaynak, 0) + 1
    assert say == {"ornek": 16, None: 1, "google_analytics": 1}
    elle = next(s for s in satirlar if s.kaynak is None)
    assert elle.metric_value == 777


async def test_mock_yukleme_ornek_isaretli(db_oturumu, monkeypatch):
    """Boş tabloya mock yüklemesi satırları doğrudan `ornek` yazıyor."""
    from models.analytics_snapshots import Analytics_snapshots
    from services import mock_data

    await mock_data._load_table_from_file(mock_data.MOCK_DATA_DIR / "analytics_snapshots.json")
    db_oturumu.expire_all()
    satirlar = (await db_oturumu.execute(select(Analytics_snapshots))).scalars().all()
    assert len(satirlar) == 16 and {s.kaynak for s in satirlar} == {"ornek"}


async def test_pano_gercek_veri_varsa_kanalin_ornegini_gizler(istemci, yonetici_basligi, kurulu, google, db_oturumu):
    from services import mock_data

    await mock_data._load_table_from_file(mock_data.MOCK_DATA_DIR / "analytics_snapshots.json")
    p = (await istemci.get(f"{TABAN}/pano", headers=yonetici_basligi)).json()
    assert p["yalniz_ornek"] is True
    assert [k["kanal"] for k in p["kanallar"]] == ["traffic", "seo", "ads", "social"]
    assert all(k["ornek"] for k in p["kanallar"])
    trafik = p["kanallar"][0]
    assert [m["metric_key"] for m in trafik["metrikler"]] == ["sessions", "users", "pageviews", "bounce_rate"]
    assert all(m["kaynak"] == "ornek" for m in trafik["metrikler"])

    await _baglan(istemci, yonetici_basligi)
    await _sec(istemci, yonetici_basligi)
    assert (await istemci.post(f"{TABAN}/google/esitle", headers=yonetici_basligi)).status_code == 200
    p = (await istemci.get(f"{TABAN}/pano", headers=yonetici_basligi)).json()
    assert p["yalniz_ornek"] is False
    k = {x["kanal"]: x for x in p["kanallar"]}
    assert list(k) == ["traffic", "seo", "youtube", "ads", "social"]
    assert not k["traffic"]["ornek"] and k["traffic"]["kaynaklar"] == ["google_analytics"]
    # Örnek "18.432 oturum" artık görünmüyor; yalnız gerçek satırlar.
    assert all(m["kaynak"] == "google_analytics" for m in k["traffic"]["metrikler"])
    assert [m["metric_key"] for m in k["traffic"]["metrikler"]] == ["sessions", "users", "pageviews", "bounce_rate", "avg_engagement_time"]
    assert next(m for m in k["traffic"]["metrikler"] if m["metric_key"] == "sessions")["metric_value"] == 1234
    # SEO: örnekteki "İndekslenen sayfa" da gizli (kanalda gerçek veri var).
    assert {m["metric_key"] for m in k["seo"]["metrikler"]} == {"organic_clicks", "impressions", "ctr", "avg_position"}
    assert k["ads"]["ornek"] and k["social"]["ornek"]
    assert len(p["listeler"]["sorgular"]["satirlar"]) == 10 and p["listeler"]["sayfalar"]["kaynak"] == "search_console"


async def test_analitik_entity_kaynak_alani(istemci, yonetici_basligi):
    """Elle yazılmış Pydantic sınıfları `kaynak`ı taşıyor (oluştur/güncelle/yanıt)."""
    y = await istemci.post(
        "/api/v1/entities/analytics_snapshots",
        json={"channel": "seo", "metric_key": "x", "metric_value": 1, "kaynak": "elle"},
        headers=yonetici_basligi,
    )
    assert y.status_code == 201 and y.json()["kaynak"] == "elle"
    kimlik = y.json()["id"]
    y = await istemci.put(f"/api/v1/entities/analytics_snapshots/{kimlik}", json={"kaynak": "ornek"}, headers=yonetici_basligi)
    assert y.json()["kaynak"] == "ornek"
    y = await istemci.get(f"/api/v1/entities/analytics_snapshots/{kimlik}", headers=yonetici_basligi)
    assert y.json()["kaynak"] == "ornek"


async def test_sonradan_eklenen_sutun_kaydi():
    from core.database import DatabaseManager

    assert {"tablo": "analytics_snapshots", "sutun": "kaynak", "tur_pg": "VARCHAR", "tur_sqlite": "TEXT"} in DatabaseManager.SONRADAN_EKLENEN_SUTUNLAR


# ---------------------------------------------------------------------------
# Hesaplama birimleri (belgelenmiş yanıt biçimleri)
# ---------------------------------------------------------------------------
async def test_ga4_hesap_adsiz_araliklar_ve_bos_onceki():
    from services.google_esitleme import ga4_metrikleri_hesapla

    govde = {
        "metricHeaders": [{"name": n} for n in ("sessions", "totalUsers", "screenPageViews", "bounceRate", "userEngagementDuration", "activeUsers")],
        "rows": [{"dimensionValues": [{"value": "date_range_0"}], "metricValues": [{"value": v} for v in ("10", "8", "30", "0.5", "600", "6")]}],
    }
    m = {x["metric_key"]: x for x in ga4_metrikleri_hesapla(govde)}
    assert m["sessions"]["metric_value"] == 10 and m["sessions"]["change_pct"] is None
    assert m["bounce_rate"]["metric_value"] == 50.0
    assert m["avg_engagement_time"]["metric_value"] == 100
    assert {x["metric_key"] for x in ga4_metrikleri_hesapla({})} == {"sessions", "users", "pageviews", "bounce_rate", "avg_engagement_time"}


async def test_sc_ve_yt_hesap():
    from services.google_esitleme import sc_metrikleri_hesapla, yt_metrikleri_hesapla

    satirlar = [
        {"keys": ["2026-08-01"], "clicks": 10, "impressions": 100, "position": 4},
        {"keys": ["2026-09-01"], "clicks": 30, "impressions": 300, "position": 2},
        {"keys": ["2026-09-02"], "clicks": 10, "impressions": 100, "position": 6},
    ]
    m = {x["metric_key"]: x for x in sc_metrikleri_hesapla(satirlar, "2026-09-01")}
    assert m["organic_clicks"]["metric_value"] == 40 and m["organic_clicks"]["change_pct"] == 300.0
    assert m["ctr"]["metric_value"] == 10.0
    assert m["avg_position"]["metric_value"] == 3.0  # (2×300 + 6×100) / 400
    rapor = {"columnHeaders": [{"name": n} for n in ("day", "views", "estimatedMinutesWatched", "subscribersGained", "subscribersLost")],
             "rows": [["2026-09-02", 50, 70, 5, 1]]}
    y = {x["metric_key"]: x for x in yt_metrikleri_hesapla(104, rapor, "2026-09-01")}
    assert y["subscribers"]["metric_value"] == 104 and y["subscribers"]["change_pct"] == 4.0
    assert y["views"]["change_pct"] is None
    # Gizli abone sayısı: abone kartı yok.
    assert "subscribers" not in {x["metric_key"] for x in yt_metrikleri_hesapla(None, rapor, "2026-09-01")}


# ---------------------------------------------------------------------------
# Sahte Google yalnız ENVIRONMENT=test (üretimde asla)
# ---------------------------------------------------------------------------
SAHTE_DURUMLARI = [
    ({"ENVIRONMENT": "test"}, True),
    ({"ENVIRONMENT": " TEST "}, True),
    ({"ENVIRONMENT": "test", "RENDER": "srv-123"}, False),  # Render'da asla
    ({}, False),  # tanımsız = üretim
    ({"ENVIRONMENT": "production"}, False),
    ({"ENVIRONMENT": "dev"}, False),
    ({"ENVIRONMENT": "yerel"}, False),
]


class _GercekCagri(Exception):
    pass


async def test_sahte_google_yalniz_test_ortaminda(monkeypatch, kurulu):
    from services import baglantilar as bg

    async def gercek(*a, **k):
        raise _GercekCagri()

    monkeypatch.setattr(bg, "_ag_istegi", gercek)
    for degiskenler, acik_mi in SAHTE_DURUMLARI:
        with monkeypatch.context() as m:
            for ad in ("ENVIRONMENT", "RENDER"):
                m.delenv(ad, raising=False)
            for ad, deger in degiskenler.items():
                m.setenv(ad, deger)
            assert bg.sahte_google_acik_mi() is acik_mi, degiskenler
            if acik_mi:
                y = await bg.google_istek("GET", bg.SC_TABAN + "/sites")
                assert y.durum == 200 and y.govde["siteEntry"]
            else:
                with pytest.raises(_GercekCagri):
                    await bg.google_istek("GET", bg.SC_TABAN + "/sites")


async def test_sahte_akis_test_ortaminda_uctan_uca(istemci, yonetici_basligi, kurulu, monkeypatch, db_oturumu):
    """ENVIRONMENT=test: onay adresi doğrudan geri dönüşe gider; bağlan → seç → eşitle ağsız çalışır."""
    from services import baglantilar as bg

    async def gercek(*a, **k):
        raise _GercekCagri()

    monkeypatch.setattr(bg, "_ag_istegi", gercek)
    monkeypatch.setenv("ENVIRONMENT", "test")
    y = await istemci.post(f"{TABAN}/google/baslat", headers=yonetici_basligi)
    adres = y.json()["adres"]
    assert adres.startswith("https://mehmetkuru.dev/api/v1/baglantilar/google/geri-donus?code=sahte-kod-")
    q = {k: v[0] for k, v in parse_qs(urlparse(adres).query).items()}
    y = await istemci.get(f"{TABAN}/google/geri-donus", params=q)
    assert y.headers["location"].endswith("sonuc=baglandi")
    d = (await istemci.get(TABAN, headers=yonetici_basligi)).json()
    assert d["test_modu"] is True and d["saglayicilar"][0]["harici_email"] == bg.SAHTE_EPOSTA
    await _sec(istemci, yonetici_basligi)
    y = await istemci.post(f"{TABAN}/google/esitle", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["yazilan"] == 13
    # Üretim işareti (RENDER) varken aynı akış gerçek ağa gider (burada yakalayıcı).
    monkeypatch.setenv("RENDER", "srv-1")
    assert (await istemci.get(TABAN, headers=yonetici_basligi)).json()["test_modu"] is False
    y = await istemci.post(f"{TABAN}/google/baslat", headers=yonetici_basligi)
    assert y.json()["adres"].startswith("https://accounts.google.com/")


# ---------------------------------------------------------------------------
# Modül, bildirim kataloğu, ortam dosyaları
# ---------------------------------------------------------------------------
async def test_modul_ve_bildirim_katalogu():
    from core.moduller import MODUL_SOZLUGU
    from services.bildirim_tercih import OLAYLAR

    m = MODUL_SOZLUGU["baglantilar"]
    assert m.gerekli_rol == "admin" and m.yonetici_sekmesi == "baglantilar" and not m.musteri_sekmesi
    assert OLAYLAR["baglanti_koptu"] == {"roller": ("admin",), "tetikleniyor": True}


async def test_render_yaml_ve_anahtar_betigi():
    import subprocess
    import sys
    from pathlib import Path

    kok = Path(__file__).resolve().parents[3]
    render = (kok.parent / "render.yaml").read_text(encoding="utf-8")
    for ad in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "BAGLANTI_SIFRE_ANAHTARI"):
        i = render.index(f"- key: {ad}")
        assert "sync: false" in render[i: i + 120], ad
    betik = kok / "backend" / "scripts" / "baglanti_anahtari_uret.py"
    cikti = subprocess.run([sys.executable, str(betik)], capture_output=True, text=True, timeout=30, cwd=str(kok / "backend"))
    assert cikti.returncode == 0
    satir = next(s for s in cikti.stdout.splitlines() if s.startswith("BAGLANTI_SIFRE_ANAHTARI="))
    from cryptography.fernet import Fernet

    Fernet(satir.split("=", 1)[1].encode())  # geçerli bir Fernet anahtarı
    assert (kok.parent / "GOOGLE-BAGLANTI-KURULUM.md").exists()


async def test_gizli_ayar_suzgeci_baglanti_adlarini_yakalar():
    """Biri bu değerleri yanlışlıkla site ayarına yazsa bile ziyaretçiye dönmez."""
    from routers.site_settings import gizli_ayar_mi

    assert gizli_ayar_mi("google_oauth_client_secret")
    assert gizli_ayar_mi("baglanti_sifre_anahtari")
    assert gizli_ayar_mi("GOOGLE_REFRESH_TOKEN")
