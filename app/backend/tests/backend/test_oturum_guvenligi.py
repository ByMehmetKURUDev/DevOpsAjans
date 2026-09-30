"""Faz 2D — oturum güvenliği: sid'li jeton + oturum satırı, iptal (iki doğrulama
yolu), sid'siz eski jeton, kullanıcı bazlı kesim, kişisel ve yönetici uçları,
giriş hız sınırı, yeni cihaz bildirimi, temizlik, denetimde sid görünmemesi.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from starlette.requests import Request


def jeton_uret(eposta: str, rol: str = "user") -> str:
    """conftest'teki gibi sid'siz (eski usul) jeton."""
    from core.auth import create_access_token

    return create_access_token({"sub": f"kimlik-{eposta}", "email": eposta, "role": rol})

K = "/api/v1/oturumlarim"
Y = "/api/v1/oturumlar"

MAC_CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
IPHONE_SAFARI = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)


def _eposta(on: str = "o") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


def _istek(ua: str = MAC_CHROME, ip: str = "203.0.113.5") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/auth/callback",
            "headers": [(b"user-agent", ua.encode()), (b"x-mk-istemci-ip", ip.encode())],
            "client": ("127.0.0.1", 1),
            "query_string": b"",
        }
    )


async def _giris(db, eposta: str, rol: str = "user", ua: str = MAC_CHROME, ip: str = "203.0.113.5"):
    """Gerçek giriş yolundaki gibi jeton verir (sid + oturum satırı)."""
    from models.auth import User
    from services.auth import AuthService

    kullanici = User(id=f"kimlik-{eposta}", email=eposta, name=eposta.split("@")[0], role=rol)
    jeton, _, iddialar = await AuthService(db).issue_app_token(kullanici, request=_istek(ua, ip))
    return jeton, iddialar


def _baslik(jeton: str):
    return {"Authorization": f"Bearer {jeton}"}


async def _bildirimler(db, olay, eposta):
    from models.notifications import Notifications

    return list(
        (
            await db.execute(
                select(Notifications).where(
                    Notifications.event_type == olay,
                    Notifications.channel == "inapp",
                    Notifications.recipient_email == eposta,
                )
            )
        ).scalars().all()
    )


# ---------------------------------------------------------------------------
# Jeton + oturum satırı
# ---------------------------------------------------------------------------
async def test_jetonda_sid_ve_iat_oturum_satiri_yaziliyor(db_oturumu):
    from core.auth import decode_access_token
    from models.oturumlar import Oturumlar

    eposta = _eposta()
    jeton, iddialar = await _giris(db_oturumu, eposta.upper())
    yuk = decode_access_token(jeton)
    assert isinstance(yuk.get("sid"), str) and len(yuk["sid"]) >= 22
    assert isinstance(yuk.get("iat"), int)
    satir = (await db_oturumu.execute(select(Oturumlar).where(Oturumlar.sid == yuk["sid"]))).scalar_one()
    assert satir.email == eposta  # küçük harf
    assert satir.cihaz == "Chrome · macOS"
    assert satir.ip_ozet and len(satir.ip_ozet) == 16 and "203.0.113.5" not in satir.ip_ozet
    assert satir.user_agent == MAC_CHROME
    assert satir.bitis is not None and satir.iptal_zamani is None


def test_cihaz_adi_ve_ua_siniri():
    from services.oturumlar import cihaz_adi

    assert cihaz_adi(IPHONE_SAFARI) == "Safari · iOS"
    assert cihaz_adi("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36 Edg/126") == "Edge · Windows"
    assert cihaz_adi("Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0") == "Firefox · Linux"
    assert cihaz_adi("") is None and cihaz_adi(None) is None


async def test_oturum_yazimi_patlarsa_giris_bozulmaz(db_oturumu, monkeypatch):
    from models.oturumlar import Oturumlar

    def patla(*a, **k):
        raise RuntimeError("veritabanı yok")

    monkeypatch.setattr(Oturumlar, "__init__", patla)
    jeton, iddialar = await _giris(db_oturumu, _eposta())
    assert jeton and iddialar.get("sid")


# ---------------------------------------------------------------------------
# İptal: iki doğrulama yolu, eski jeton, kesim
# ---------------------------------------------------------------------------
async def test_iptalden_sonra_iki_yolda_da_401(istemci, db_oturumu):
    eposta = _eposta("iptal")
    jeton, _ = await _giris(db_oturumu, eposta, rol="admin")
    b = _baslik(jeton)
    # get_current_user yolu
    assert (await istemci.get("/api/v1/auth/me", headers=b)).status_code == 200
    # _yonetici_mi yolu (denetim router'ı jetonu kendisi çözüyor)
    assert (await istemci.get("/api/v1/denetim", headers=b)).status_code == 200

    liste = (await istemci.get(K, headers=b)).json()
    assert len(liste) == 1 and liste[0]["bu_cihaz"] is True
    assert "sid" not in liste[0]
    y = await istemci.delete(f"{K}/{liste[0]['id']}", headers=b)
    assert y.status_code == 200 and y.json() == {"kapatilan": 1, "bu_cihaz": True}

    me = await istemci.get("/api/v1/auth/me", headers=b)
    assert me.status_code == 401 and me.json()["detail"] == "Oturum sonlandırıldı"
    den = await istemci.get("/api/v1/denetim", headers=b)
    assert den.status_code == 401 and den.json()["detail"] == "Oturum sonlandırıldı"
    # entity bekçisi de (okuma oturum istiyor)
    ent = await istemci.get("/api/v1/entities/invoices", headers=b)
    assert ent.status_code == 401 and ent.json()["detail"] == "Oturum sonlandırıldı"
    # Herkese açık okuma iptal edilmiş jetonla da çalışıyor (anonim sayılır).
    assert (await istemci.get("/api/v1/entities/blog_posts", headers=b)).status_code == 200


async def test_sidsiz_eski_jeton_gecerli(istemci, musteri_basligi):
    b = musteri_basligi(_eposta("eski"))
    assert (await istemci.get("/api/v1/auth/me", headers=b)).status_code == 200
    y = await istemci.get(K, headers=b)
    assert y.status_code == 200 and y.json() == []


async def test_kullanici_bazli_kesim_eski_jetonu_da_dusurur(istemci, db_oturumu, yonetici_basligi):
    eposta = _eposta("kesim")
    eski = _baslik(jeton_uret(eposta))  # sid'siz
    yeni, _ = await _giris(db_oturumu, eposta)
    for b in (eski, _baslik(yeni)):
        assert (await istemci.get("/api/v1/auth/me", headers=b)).status_code == 200

    y = await istemci.post(f"{Y}/kullanici-cikis", json={"email": eposta.upper()}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert y.json()["kapatilan"] == 1

    for b in (eski, _baslik(yeni)):
        r = await istemci.get("/api/v1/auth/me", headers=b)
        assert r.status_code == 401 and r.json()["detail"] == "Oturum sonlandırıldı"
        assert (await istemci.get("/api/v1/denetim/benim", headers=b)).status_code == 401

    # Kesimden SONRA verilen jeton geçerli (tekrar giriş yapabiliyor).
    import asyncio

    await asyncio.sleep(1.05)
    sonraki, _ = await _giris(db_oturumu, eposta)
    assert (await istemci.get("/api/v1/auth/me", headers=_baslik(sonraki))).status_code == 200


async def test_kesim_varken_iatsiz_jeton_reddedilir(istemci, db_oturumu):
    from core.config import settings
    from jose import jwt
    from services import oturumlar

    eposta = _eposta("iatsiz")
    yuk = {
        "sub": "x", "email": eposta, "role": "user",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    jeton = jwt.encode(yuk, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    assert (await istemci.get("/api/v1/auth/me", headers=_baslik(jeton))).status_code == 200
    await oturumlar.kesim_koy(db_oturumu, eposta, iptal_eden="test")
    assert (await istemci.get("/api/v1/auth/me", headers=_baslik(jeton))).status_code == 401


async def test_onbellek_ve_son_gorulme(istemci, db_oturumu):
    from models.oturumlar import Oturumlar
    from services import oturumlar

    eposta = _eposta("gorulme")
    jeton, iddia = await _giris(db_oturumu, eposta)
    eski = datetime.now(timezone.utc) - timedelta(hours=1)
    satir = (await db_oturumu.execute(select(Oturumlar).where(Oturumlar.sid == iddia["sid"]))).scalar_one()
    satir.son_gorulme = eski
    await db_oturumu.commit()
    oturumlar.onbellegi_temizle()
    assert (await istemci.get("/api/v1/auth/me", headers=_baslik(jeton))).status_code == 200
    await db_oturumu.refresh(satir)
    ilk = oturumlar._utc(satir.son_gorulme)
    assert ilk > eski + timedelta(minutes=50)
    # 5 dakika dolmadan tekrar yazılmıyor.
    assert (await istemci.get("/api/v1/auth/me", headers=_baslik(jeton))).status_code == 200
    await db_oturumu.refresh(satir)
    assert oturumlar._utc(satir.son_gorulme) == ilk


# ---------------------------------------------------------------------------
# Kişisel uçlar
# ---------------------------------------------------------------------------
async def test_kisisel_uclar_yetkisiz_401(istemci):
    assert (await istemci.get(K)).status_code == 401
    assert (await istemci.delete(f"{K}/1")).status_code == 401
    assert (await istemci.post(f"{K}/digerlerini-kapat")).status_code == 401


async def test_musteri_baskasinin_oturumunu_kapatamaz(istemci, db_oturumu):
    a, b = _eposta("a"), _eposta("b")
    ja, _ = await _giris(db_oturumu, a)
    jb, _ = await _giris(db_oturumu, b)
    b_oturumu = (await istemci.get(K, headers=_baslik(jb))).json()[0]["id"]
    y = await istemci.delete(f"{K}/{b_oturumu}", headers=_baslik(ja))
    assert y.status_code == 404
    assert (await istemci.get("/api/v1/auth/me", headers=_baslik(jb))).status_code == 200
    # A'nın listesinde B'nin oturumu yok.
    assert all(s["id"] != b_oturumu for s in (await istemci.get(K, headers=_baslik(ja))).json())


async def test_digerlerini_kapat_bu_cihazi_birakir(istemci, db_oturumu):
    eposta = _eposta("diger")
    bu, _ = await _giris(db_oturumu, eposta)
    diger1, _ = await _giris(db_oturumu, eposta, ua=IPHONE_SAFARI, ip="198.51.100.7")
    diger2, _ = await _giris(db_oturumu, eposta, ip="198.51.100.8")
    assert len((await istemci.get(K, headers=_baslik(bu))).json()) == 3
    y = await istemci.post(f"{K}/digerlerini-kapat", headers=_baslik(bu))
    assert y.status_code == 200 and y.json()["kapatilan"] == 2
    assert (await istemci.get("/api/v1/auth/me", headers=_baslik(bu))).status_code == 200
    for j in (diger1, diger2):
        assert (await istemci.get("/api/v1/auth/me", headers=_baslik(j))).status_code == 401
    kalan = (await istemci.get(K, headers=_baslik(bu))).json()
    assert len(kalan) == 1 and kalan[0]["bu_cihaz"]


# ---------------------------------------------------------------------------
# Yönetici uçları
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "yontem,yol,govde",
    [("GET", Y, None), ("DELETE", f"{Y}/1", None), ("POST", f"{Y}/kullanici-cikis", {"email": "x@y.dev"})],
)
async def test_yonetici_uclari_401_403(istemci, musteri_basligi, yontem, yol, govde):
    assert (await istemci.request(yontem, yol, json=govde)).status_code == 401
    assert (await istemci.request(yontem, yol, json=govde, headers=musteri_basligi())).status_code == 403


async def test_yonetici_listesi_suzgec_ve_kapatma(istemci, db_oturumu, yonetici_basligi):
    eposta = _eposta("liste")
    jeton, _ = await _giris(db_oturumu, eposta)
    y = await istemci.get(Y, params={"email": eposta}, headers=yonetici_basligi)
    assert y.status_code == 200
    govde = y.json()
    assert govde["toplam"] == 1 and govde["items"][0]["email"] == eposta
    assert govde["items"][0]["etkin"] is True and "sid" not in govde["items"][0]
    oturum_id = govde["items"][0]["id"]

    assert (await istemci.delete(f"{Y}/{oturum_id}", headers=yonetici_basligi)).status_code == 200
    assert (await istemci.get("/api/v1/auth/me", headers=_baslik(jeton))).status_code == 401
    # Yalnız etkinler: artık yok; hepsi: iptal bilgisiyle var.
    assert (await istemci.get(Y, params={"email": eposta}, headers=yonetici_basligi)).json()["toplam"] == 0
    hepsi = (await istemci.get(Y, params={"email": eposta, "yalniz_etkin": "false"}, headers=yonetici_basligi)).json()
    assert hepsi["items"][0]["etkin"] is False and hepsi["items"][0]["iptal_eden"] == "yonetici@test.dev"
    assert (await istemci.delete(f"{Y}/999999", headers=yonetici_basligi)).status_code == 404


async def test_yonetici_kendi_oturumunu_kapatamaz(istemci, db_oturumu):
    eposta = _eposta("yon")
    jeton, _ = await _giris(db_oturumu, eposta, rol="admin")
    b = _baslik(jeton)
    kendi = (await istemci.get(K, headers=b)).json()[0]["id"]
    y = await istemci.delete(f"{Y}/{kendi}", headers=b)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "kendi_oturumun"
    y = await istemci.post(f"{Y}/kullanici-cikis", json={"email": eposta}, headers=b)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "kendi_hesabin"
    assert (await istemci.get("/api/v1/auth/me", headers=b)).status_code == 200


async def test_iptal_denetim_kaydinda_sid_gorunmez(istemci, db_oturumu, yonetici_basligi):
    from models.audit_log import AuditLog

    eposta = _eposta("denetim")
    jeton, iddia = await _giris(db_oturumu, eposta)
    oturum_id = (await istemci.get(K, headers=_baslik(jeton))).json()[0]["id"]
    assert (await istemci.delete(f"{Y}/{oturum_id}", headers=yonetici_basligi)).status_code == 200
    satirlar = (
        await db_oturumu.execute(select(AuditLog).where(AuditLog.tablo == "oturumlar", AuditLog.kayit_id == str(oturum_id)))
    ).scalars().all()
    assert len(satirlar) == 1
    assert satirlar[0].aktor_eposta == "yonetici@test.dev"
    assert eposta in satirlar[0].ozet
    tum_metin = json.dumps([s.ozet for s in satirlar]) + json.dumps([s.degisiklik_json for s in satirlar])
    assert iddia["sid"] not in tum_metin
    # Girişte oturum satırı denetime "olustur" olarak düşmüyor (teknik tablo).
    olustur = (
        await db_oturumu.execute(select(AuditLog).where(AuditLog.tablo == "oturumlar", AuditLog.islem == "olustur"))
    ).scalars().all()
    assert olustur == []
    from services.denetim import hassas_mi

    assert hassas_mi("sid") and not hassas_mi("inside")


# ---------------------------------------------------------------------------
# Giriş uçları: hız sınırı, çıkış
# ---------------------------------------------------------------------------
async def test_giris_hiz_siniri_429(istemci, monkeypatch):
    from routers import auth as auth_router

    auth_router.giris_hiz_siniri.temizle()
    ip = {"X-MK-Istemci-IP": "192.0.2.77"}
    try:
        for _ in range(auth_router.GIRIS_SINIRI):
            y = await istemci.get("/api/v1/auth/callback", params={"error": "iptal"}, headers=ip)
            assert y.status_code == 302 and "OIDC+error" in y.headers["location"]
        y = await istemci.get("/api/v1/auth/callback", params={"error": "iptal"}, headers=ip)
        assert y.status_code == 302 and "/auth/error" in y.headers["location"]
        assert "OIDC+error" not in y.headers["location"]
        assert (await istemci.get("/api/v1/auth/login", headers=ip)).status_code == 429
        y = await istemci.post("/api/v1/auth/token/exchange", json={"platform_token": "x"}, headers=ip)
        assert y.status_code == 429
        # Başka IP etkilenmiyor.
        y = await istemci.get("/api/v1/auth/callback", params={"error": "iptal"}, headers={"X-MK-Istemci-IP": "192.0.2.78"})
        assert "OIDC+error" in y.headers["location"]
    finally:
        auth_router.giris_hiz_siniri.temizle()


async def test_token_exchange_sidli_jeton_verir(istemci, db_oturumu, monkeypatch):
    import types

    from core.auth import decode_access_token
    from models.oturumlar import Oturumlar
    from routers import auth as auth_router

    eposta = _eposta("platform")

    class _Yanit:
        status_code = 200

        def json(self):
            return {"success": True, "data": {"user_id": "p-123", "email": eposta, "name": "P"}}

    class _SahteIstemci:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kwargs):
            return _Yanit()

    from core.config import settings

    monkeypatch.setitem(settings.__dict__, "oidc_issuer_url", "https://kimlik.test")
    monkeypatch.setitem(settings.__dict__, "admin_user_id", "yonetici-kimligi")
    # Yalnız router'ın gördüğü httpx sahte (test istemcisi de httpx kullanıyor).
    monkeypatch.setattr(
        auth_router, "httpx", types.SimpleNamespace(AsyncClient=lambda *a, **k: _SahteIstemci(), HTTPError=Exception)
    )
    auth_router.giris_hiz_siniri.temizle()
    y = await istemci.post(
        "/api/v1/auth/token/exchange", json={"platform_token": "x"}, headers={"User-Agent": IPHONE_SAFARI}
    )
    assert y.status_code == 200, y.text
    sid = decode_access_token(y.json()["token"])["sid"]
    satir = (await db_oturumu.execute(select(Oturumlar).where(Oturumlar.sid == sid))).scalar_one()
    assert satir.email == eposta and satir.cihaz == "Safari · iOS"


async def test_cikis_oturumu_iptal_eder(istemci, db_oturumu, monkeypatch):
    from core.config import settings

    monkeypatch.setitem(settings.__dict__, "frontend_url", "https://mehmetkuru.dev")
    monkeypatch.setitem(settings.__dict__, "oidc_end_session_endpoint", "none")
    jeton, _ = await _giris(db_oturumu, _eposta("cikis"))
    y = await istemci.get("/api/v1/auth/logout", headers=_baslik(jeton))
    assert y.status_code == 200 and "redirect_url" in y.json()
    assert (await istemci.get("/api/v1/auth/me", headers=_baslik(jeton))).status_code == 401
    # Jetonsuz çıkış eskisi gibi çalışıyor.
    assert (await istemci.get("/api/v1/auth/logout")).status_code == 200


# ---------------------------------------------------------------------------
# Yeni cihaz bildirimi
# ---------------------------------------------------------------------------
async def test_yeni_cihaz_bildirimi(db_oturumu):
    eposta = _eposta("cihaz")
    await _giris(db_oturumu, eposta)
    assert await _bildirimler(db_oturumu, "yeni_oturum", eposta) == []  # ilk giriş
    await _giris(db_oturumu, eposta)  # aynı cihaz + ağ
    assert await _bildirimler(db_oturumu, "yeni_oturum", eposta) == []
    await _giris(db_oturumu, eposta, ua=IPHONE_SAFARI)  # farklı cihaz
    bildirimler = await _bildirimler(db_oturumu, "yeni_oturum", eposta)
    assert len(bildirimler) == 1
    assert "Safari · iOS" in (bildirimler[0].body or "")
    await _giris(db_oturumu, eposta, ip="198.51.100.200")  # aynı cihaz, farklı ağ
    assert len(await _bildirimler(db_oturumu, "yeni_oturum", eposta)) == 2


def test_yeni_oturum_olayi_katalogda_ve_7_dilde():
    from pathlib import Path

    from services.bildirim_tercih import OLAYLAR

    assert OLAYLAR["yeni_oturum"]["tetikleniyor"] is True
    ek = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek" / "bildirim"
    tr = json.loads((ek / "tr.json").read_text(encoding="utf-8"))["bildirim"]["olay"]["yeni_oturum"]
    for dil in ("en", "de", "ru", "zh", "hi", "ar"):
        deger = json.loads((ek / f"{dil}.json").read_text(encoding="utf-8"))["bildirim"]["olay"]["yeni_oturum"]
        assert deger and deger != tr, dil


# ---------------------------------------------------------------------------
# Temizlik
# ---------------------------------------------------------------------------
async def test_temizlik_30_gunden_eski_biten_ve_iptal(db_oturumu):
    from models.oturumlar import Oturumlar
    from services import oturumlar, zamanli

    assert "oturum_temizligi" in zamanli.GOREV_ADLARI
    eposta = _eposta("temiz")
    an = datetime.now(timezone.utc)
    satirlar = [
        Oturumlar(sid=uuid.uuid4().hex, email=eposta, bitis=an - timedelta(days=31)),
        Oturumlar(sid=uuid.uuid4().hex, email=eposta, bitis=an + timedelta(days=1), iptal_zamani=an - timedelta(days=40)),
        Oturumlar(sid=uuid.uuid4().hex, email=eposta, bitis=an - timedelta(days=5)),
        Oturumlar(sid=uuid.uuid4().hex, email=eposta, bitis=an + timedelta(days=1)),
    ]
    db_oturumu.add_all(satirlar)
    await db_oturumu.commit()
    sonuc = await oturumlar.temizle(db_oturumu)
    assert sonuc["silinen_oturum"] >= 2
    kalan = (await db_oturumu.execute(select(Oturumlar).where(Oturumlar.email == eposta))).scalars().all()
    assert len(kalan) == 2
