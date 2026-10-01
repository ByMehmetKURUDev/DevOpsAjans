"""Faz 4A — API anahtarları, herkese açık REST API, imzalı webhook'lar ve MCP sunucusu.

Kapsam: anahtar üretimi/özet/önek, bir kez gösterim, iptal (anında), süre dolumu, IP
izin listesi, kapsam 403, hesap izolasyonu 404, hız sınırı 429, idempotency,
sayfalama + updated_since, panel uçlarının anahtarı TANIMAMASI (401) ve public
API'nin JWT'yi tanımaması, ekip üyesi anahtarının yetkisi düşünce çalışmaması,
webhook imzası (belgedeki doğrulama algoritmasıyla), SSRF reddi (özel IP,
localhost, metadata, port, DNS yeniden bağlama — teslimat anında da), yeniden
deneme zamanlaması + vazgeçme + otomatik pasifleştirme (bildirimli), teslimat
kaydı kırpma, olay → doğru hesaba yönlendirme, arka plan teslimatı, sır
yenileme (iki imza), denetim kaydında maskeleme, MCP (initialize / tools/list
kapsama göre / tools/call; SDK istemcisiyle uyumluluk).
"""

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import delete, select, update

from conftest import jeton_uret

Y = "/api/v1/api-erisimi/yonetim"
M = "/api/v1/api-erisimim"
P = "/api/public/v1"
MODUL = "/api/v1/moduller"


def _e(on: str = "api") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@api.dev"


def _b(eposta: str, hesap: str | None = None, rol: str = "user") -> dict:
    h = {"Authorization": f"Bearer {jeton_uret(eposta, rol)}"}
    if hesap:
        h["X-MK-Hesap"] = hesap
    return h


def _k(ham: str, **ek) -> dict:
    return {"Authorization": f"Bearer {ham}", **ek}


def _gelecek(gun: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=gun)).isoformat()


def _kod(y) -> str:
    try:
        d = y.json()
    except Exception:  # noqa: BLE001
        return ""
    if isinstance(d.get("hata"), dict):
        return d["hata"].get("kod", "")
    det = d.get("detail")
    return det.get("kod", "") if isinstance(det, dict) else ""


class _Alici:
    """Sahte webhook alıcısı (httpx.MockTransport): istekleri kaydeder, istenen yanıtı verir."""

    def __init__(self):
        self.istekler: list = []
        self.durum = 200
        self.govde = b"ok"

    def __call__(self, istek: httpx.Request) -> httpx.Response:
        self.istekler.append(istek)
        return httpx.Response(self.durum, content=self.govde)


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    from routers import api_erisimi as r
    from services import hesap_ekibi, site_analizi, webhook

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    webhook.onbellegi_temizle()
    monkeypatch.setattr(webhook, "ANLIK_TESLIMAT", False)

    async def _dns(host, port):
        return ["93.184.216.34"]

    monkeypatch.setattr(site_analizi, "_dns_cozumle", _dns)
    yield
    r.hiz_sinirlarini_temizle()


@pytest.fixture
async def alici(monkeypatch, db_oturumu):
    from services import site_analizi, webhook

    a = _Alici()
    monkeypatch.setattr(site_analizi, "_tasiyici_fabrikasi", lambda: httpx.MockTransport(a))
    yield a
    # Bu dosyanın uç noktaları diğer testlerin kayıtlarından olay üretmesin.
    from models.api_erisimi import WebhookDenemeleri, WebhookTeslimatlari, WebhookUcNoktalari

    await db_oturumu.execute(delete(WebhookDenemeleri))
    await db_oturumu.execute(delete(WebhookTeslimatlari))
    await db_oturumu.execute(delete(WebhookUcNoktalari))
    await db_oturumu.commit()
    webhook.onbellegi_temizle()


async def _modul_ac(istemci, yb, eposta, acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/api_erisimi", json=govde, headers=yb)
    assert y.status_code == 200, y.text


async def _musteri(istemci, yb, **ayarlar) -> str:
    e = _e()
    await _modul_ac(istemci, yb, e, **ayarlar)
    return e


async def _anahtar(istemci, basliklar, yol=Y, **govde) -> tuple:
    govde.setdefault("ad", "Test anahtarı")
    govde.setdefault("kapsamlar", ["projeler:oku"])
    if yol == Y:
        govde.setdefault("son_kullanma", _gelecek())
    y = await istemci.post(f"{yol}/anahtarlar", json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()["ham_anahtar"], y.json()["anahtar"]


async def _proje(db, eposta, baslik="Proje"):
    from models.projects import Projects

    p = Projects(title=baslik, description="d", category="Web", client_email=eposta, published=False, status="in_progress",
                 stage="kesif")
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


# ---------------------------------------------------------------------------
# Anahtar üretimi ve saklama
# ---------------------------------------------------------------------------
def test_anahtar_uretimi_bicim_ozet_onek():
    from services import api_erisimi as s

    ham, ozet, onek = s.anahtar_uret()
    assert ham.startswith("mk_live_") and len(ham) == len("mk_live_") + 43
    assert s.bicim_gecerli_mi(ham)
    assert ozet == hashlib.sha256(ham.encode()).hexdigest()
    assert onek == ham[8:16]
    assert not s.bicim_gecerli_mi(ham[:-1]) and not s.bicim_gecerli_mi("mk_test_" + ham[8:])
    assert len({s.anahtar_uret()[0] for _ in range(50)}) == 50


async def test_anahtar_bir_kez_gosterilir_db_de_yalniz_ozet_denetimde_maskeli(istemci, yonetici_basligi, db_oturumu):
    from models.api_erisimi import ApiAnahtarlari
    from models.audit_log import AuditLog

    ham, a = await _anahtar(istemci, yonetici_basligi, kapsamlar=["projeler:oku", "faturalar:oku"])
    assert a["onek"] == f"mk_live_{ham[8:16]}…" and a["durum"] == "aktif" and a["sahip_tur"] == "ajans"
    liste = await istemci.get(f"{Y}/anahtarlar", headers=yonetici_basligi)
    metin = liste.text
    assert ham not in metin and hashlib.sha256(ham.encode()).hexdigest() not in metin and "anahtar_ozeti" not in metin
    satir = (await db_oturumu.execute(select(ApiAnahtarlari).where(ApiAnahtarlari.id == a["id"]))).scalars().one()
    assert satir.anahtar_ozeti == hashlib.sha256(ham.encode()).hexdigest() and satir.onek == ham[8:16]
    denetim = (await db_oturumu.execute(select(AuditLog).where(AuditLog.tablo == "api_anahtarlari"))).scalars().all()
    assert denetim, "anahtar oluşturma denetime düşmeli"
    for d in denetim:
        assert ham not in (d.degisiklik_json or "") and satir.anahtar_ozeti not in (d.degisiklik_json or "")


async def test_ajans_anahtari_son_kullanma_ya_da_acik_onay_ister(istemci, yonetici_basligi):
    y = await istemci.post(f"{Y}/anahtarlar", json={"ad": "x", "kapsamlar": ["projeler:oku"]}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "ajans_son_kullanma_gerekli" and y.json()["detail"]["onerilen_gun"] == 90
    y = await istemci.post(f"{Y}/anahtarlar", json={"ad": "x", "kapsamlar": ["projeler:oku"], "suresiz_onay": True},
                           headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["anahtar"]["son_kullanma"] is None
    for govde, kod in (
        ({"ad": "x", "kapsamlar": []}, "kapsam_gerekli"),
        ({"ad": "x", "kapsamlar": ["her_sey"]}, "kapsam_gecersiz"),
        ({"ad": "", "kapsamlar": ["projeler:oku"]}, "ad_gerekli"),
        ({"ad": "x", "kapsamlar": ["projeler:oku"], "son_kullanma": "2001-01-01"}, "son_kullanma_gecmiste"),
        ({"ad": "x", "kapsamlar": ["projeler:oku"], "son_kullanma": _gelecek(), "ip_izinleri": ["999.1.1.1"]}, "ip_gecersiz"),
    ):
        y = await istemci.post(f"{Y}/anahtarlar", json=govde, headers=yonetici_basligi)
        assert y.status_code == 400 and _kod(y) == kod, (govde, y.text)


async def test_yetkisiz_ve_musteri_modul_kapali(istemci, yonetici_basligi):
    assert (await istemci.get(f"{Y}/anahtarlar")).status_code == 401
    assert (await istemci.get(f"{Y}/anahtarlar", headers=_b(_e()))).status_code == 403
    y = await istemci.get(f"{M}/anahtarlar", headers=_b(_e()))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    # Müşteri CRM kapsamı veremez.
    e = await _musteri(istemci, yonetici_basligi)
    y = await istemci.post(f"{M}/anahtarlar", json={"ad": "x", "kapsamlar": ["crm:oku"]}, headers=_b(e))
    assert y.status_code == 400 and _kod(y) == "kapsam_yalniz_ajans"
    meta = (await istemci.get(f"{M}/meta", headers=_b(e))).json()
    assert all(not k["anahtar"].startswith("crm:") for k in meta["kapsamlar"])
    assert meta["mcp_url"].endswith("/api/public/v1/mcp") and meta["anahtar_siniri"] == 5
    assert all(o["anahtar"] != "aday.olusturuldu" for o in meta["olaylar"])


# ---------------------------------------------------------------------------
# Kimlik doğrulama
# ---------------------------------------------------------------------------
async def test_anahtarla_projeler_200_iptalden_sonra_aninda_401(istemci, yonetici_basligi, db_oturumu):
    e = _e()
    p = await _proje(db_oturumu, e)
    ham, a = await _anahtar(istemci, yonetici_basligi)
    y = await istemci.get(f"{P}/projeler", headers=_k(ham))
    assert y.status_code == 200, y.text
    assert p.id in [x["id"] for x in y.json()["veri"]]
    # X-API-Key başlığı da geçer.
    assert (await istemci.get(f"{P}/projeler/{p.id}", headers={"X-API-Key": ham})).status_code == 200
    y = await istemci.post(f"{Y}/anahtarlar/{a['id']}/iptal", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "iptal"
    y = await istemci.get(f"{P}/projeler", headers=_k(ham))
    assert y.status_code == 401 and y.json() == {"hata": {"kod": "anahtar_iptal", "mesaj": y.json()["hata"]["mesaj"]}}
    assert "WWW-Authenticate" in y.headers


async def test_kimlik_hatalari_tutarli_bicimde(istemci, yonetici_basligi):
    y = await istemci.get(f"{P}/projeler")
    assert y.status_code == 401 and _kod(y) == "anahtar_gerekli" and set(y.json()) == {"hata"}
    y = await istemci.get(f"{P}/projeler", headers=_k("mk_live_" + "A" * 43))
    assert y.status_code == 401 and _kod(y) == "anahtar_gecersiz"
    # Panel JWT'si herkese açık API'de geçmez.
    y = await istemci.get(f"{P}/projeler", headers=yonetici_basligi)
    assert y.status_code == 401 and _kod(y) == "anahtar_gecersiz"


async def test_panel_uclari_anahtari_tanimaz(istemci, yonetici_basligi):
    ham, _ = await _anahtar(istemci, yonetici_basligi, kapsamlar=["projeler:oku", "faturalar:oku", "destek:oku"])
    for yol in ("/api/v1/entities/invoices", "/api/v1/kredilerim", f"{Y}/anahtarlar", "/api/v1/auth/me",
                "/api/v1/entities/support_tickets/all"):
        y = await istemci.get(yol, headers=_k(ham))
        assert y.status_code == 401, (yol, y.status_code, y.text[:200])
        y = await istemci.get(yol, headers={"X-API-Key": ham})
        assert y.status_code == 401, (yol, y.status_code)


async def test_suresi_dolan_anahtar_401(istemci, yonetici_basligi, db_oturumu):
    from models.api_erisimi import ApiAnahtarlari

    ham, a = await _anahtar(istemci, yonetici_basligi)
    await db_oturumu.execute(update(ApiAnahtarlari).where(ApiAnahtarlari.id == a["id"])
                             .values(son_kullanma=datetime.now(timezone.utc) - timedelta(minutes=1)))
    await db_oturumu.commit()
    y = await istemci.get(f"{P}/projeler", headers=_k(ham))
    assert y.status_code == 401 and _kod(y) == "anahtar_suresi_doldu"
    liste = (await istemci.get(f"{Y}/anahtarlar", headers=yonetici_basligi)).json()["items"]
    assert next(x for x in liste if x["id"] == a["id"])["durum"] == "suresi_doldu"


async def test_ip_izin_listesi(istemci, yonetici_basligi):
    ham, a = await _anahtar(istemci, yonetici_basligi, ip_izinleri=["203.0.113.0/24", "2001:db8::/32"])
    assert a["ip_izinleri"] == ["203.0.113.0/24", "2001:db8::/32"]
    y = await istemci.get(f"{P}/projeler", headers=_k(ham, **{"X-MK-Istemci-IP": "203.0.113.9"}))
    assert y.status_code == 200
    y = await istemci.get(f"{P}/projeler", headers=_k(ham, **{"X-MK-Istemci-IP": "2001:db8::5"}))
    assert y.status_code == 200
    y = await istemci.get(f"{P}/projeler", headers=_k(ham, **{"X-MK-Istemci-IP": "198.51.100.1"}))
    assert y.status_code == 403 and _kod(y) == "ip_izinli_degil"


async def test_kapsam_disi_403(istemci, yonetici_basligi):
    ham, _ = await _anahtar(istemci, yonetici_basligi, kapsamlar=["projeler:oku"])
    y = await istemci.get(f"{P}/faturalar", headers=_k(ham))
    assert y.status_code == 403 and _kod(y) == "kapsam_yetersiz" and y.json()["hata"]["gereken"] == "faturalar:oku"
    y = await istemci.post(f"{P}/destek", json={"konu": "a", "mesaj": "b", "hesap": _e()}, headers=_k(ham))
    assert y.status_code == 403 and _kod(y) == "kapsam_yetersiz"


async def test_hesap_izolasyonu_404_ve_liste(istemci, yonetici_basligi, db_oturumu):
    a, b = await _musteri(istemci, yonetici_basligi), await _musteri(istemci, yonetici_basligi)
    pa, pb = await _proje(db_oturumu, a, "A projesi"), await _proje(db_oturumu, b.upper(), "B projesi")
    ham, anahtar = await _anahtar(istemci, _b(a), M, kapsamlar=["projeler:oku", "faturalar:oku", "destek:oku"])
    assert anahtar["sahip_tur"] == "musteri" and anahtar["hesap_email"] == a
    y = await istemci.get(f"{P}/projeler", headers=_k(ham))
    assert [x["id"] for x in y.json()["veri"]] == [pa.id]
    y = await istemci.get(f"{P}/projeler/{pb.id}", headers=_k(ham))
    assert y.status_code == 404 and _kod(y) == "bulunamadi"
    # Müşteri `hesap` süzgeciyle başka hesaba geçemez (yok sayılır).
    y = await istemci.get(f"{P}/projeler", params={"hesap": b}, headers=_k(ham))
    assert [x["id"] for x in y.json()["veri"]] == [pa.id]
    # Ajans anahtarı ikisini de görür; hesap süzgeci (büyük/küçük harf duyarsız) çalışır.
    ajans, _ = await _anahtar(istemci, yonetici_basligi)
    y = await istemci.get(f"{P}/projeler", params={"hesap": b, "limit": 100}, headers=_k(ajans))
    assert [x["id"] for x in y.json()["veri"]] == [pb.id]
    # Başka müşterinin anahtarı panelden de görünmez/iptal edilemez.
    y = await istemci.post(f"{M}/anahtarlar/{anahtar['id']}/iptal", headers=_b(b))
    assert y.status_code == 404


async def test_musteri_anahtari_modul_kapaninca_403(istemci, yonetici_basligi, db_oturumu):
    e = await _musteri(istemci, yonetici_basligi)
    await _proje(db_oturumu, e)
    ham, _ = await _anahtar(istemci, _b(e), M)
    assert (await istemci.get(f"{P}/projeler", headers=_k(ham))).status_code == 200
    await _modul_ac(istemci, yonetici_basligi, e, acik=False)
    y = await istemci.get(f"{P}/projeler", headers=_k(ham))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"


async def test_hiz_siniri_429(istemci, yonetici_basligi):
    ham, _ = await _anahtar(istemci, yonetici_basligi, dakika_siniri=3)
    for _ in range(3):
        assert (await istemci.get(f"{P}/hesap", headers=_k(ham))).status_code == 200
    y = await istemci.get(f"{P}/hesap", headers=_k(ham))
    assert y.status_code == 429 and _kod(y) == "hiz_siniri" and int(y.headers["Retry-After"]) >= 1
    # Sınır üstü dakika sınırı verilemez; anahtar oluşturmada kişi başı hız sınırı.
    e = await _musteri(istemci, yonetici_basligi, dakika_siniri=10)
    y = await istemci.post(f"{M}/anahtarlar", json={"ad": "x", "kapsamlar": ["projeler:oku"], "dakika_siniri": 11},
                           headers=_b(e))
    assert y.status_code == 400 and _kod(y) == "dakika_siniri_ust"


async def test_anahtar_siniri_ve_olusturma_hizi(istemci, yonetici_basligi):
    e = await _musteri(istemci, yonetici_basligi, anahtar_siniri=2)
    for _ in range(2):
        await _anahtar(istemci, _b(e), M)
    y = await istemci.post(f"{M}/anahtarlar", json={"ad": "x", "kapsamlar": ["projeler:oku"]}, headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "anahtar_siniri"
    son = None
    for _ in range(12):
        son = await istemci.post(f"{M}/anahtarlar", json={"ad": "x", "kapsamlar": ["projeler:oku"]}, headers=_b(e))
    assert son.status_code == 429


async def test_ekip_uyesi_anahtari(istemci, yonetici_basligi, db_oturumu):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi

    sahip = await _musteri(istemci, yonetici_basligi)
    uye = _e("uye")
    db_oturumu.add(HesapUyeleri(hesap_email=sahip, uye_email=uye, rol="uye", izinler=json.dumps(["projeler", "api"]),
                                durum="aktif", olusturma=hesap_ekibi.simdi()))
    await db_oturumu.commit()
    hesap_ekibi.onbellegi_temizle()
    await _proje(db_oturumu, sahip)
    # Kendinde olmayan izni (faturalar) anahtara veremez.
    y = await istemci.post(f"{M}/anahtarlar", json={"ad": "x", "kapsamlar": ["faturalar:oku"]}, headers=_b(uye, sahip))
    assert y.status_code == 403 and _kod(y) == "kapsam_izni_yok"
    ham, a = await _anahtar(istemci, _b(uye, sahip), M)
    assert a["hesap_email"] == sahip and a["olusturan"] == uye
    assert (await istemci.get(f"{P}/projeler", headers=_k(ham))).status_code == 200
    # `api` izni olmayan üye panel uçlarına giremez.
    yok = _e("yok")
    db_oturumu.add(HesapUyeleri(hesap_email=sahip, uye_email=yok, rol="uye", izinler=json.dumps(["projeler"]),
                                durum="aktif", olusturma=hesap_ekibi.simdi()))
    await db_oturumu.commit()
    hesap_ekibi.onbellegi_temizle()
    y = await istemci.get(f"{M}/anahtarlar", headers=_b(yok, sahip))
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"
    # Üye pasifleşince açtığı anahtar da çalışmaz.
    await db_oturumu.execute(update(HesapUyeleri).where(HesapUyeleri.uye_email == uye).values(durum="pasif"))
    await db_oturumu.commit()
    hesap_ekibi.onbellegi_temizle()
    y = await istemci.get(f"{P}/projeler", headers=_k(ham))
    assert y.status_code == 401 and _kod(y) == "anahtar_devre_disi"


def test_rol_varsayilanlari_api_izni():
    from services import hesap_ekibi as he

    assert "api" in he.IZINLER and "api" in he.ROL_VARSAYILAN["yonetici"]
    assert "api" not in he.ROL_VARSAYILAN["uye"] and "api" not in he.ROL_VARSAYILAN["fatura"]
    # Faz 4M varsayılanında kalmış hesap yöneticisi bugünkü varsayılanı (api dahil) alır.
    eski = ["projeler", "gorevler", "destek", "dosyalar", "faturalar", "siteler", "raporlar", "krediler", "abonelikler",
            "mesajlar", "asistanlar", "qr", "kartvizit", "menu"]
    assert "api" in he.izinleri_coz(json.dumps(eski), "yonetici")
    assert he.OLAY_IZNI["webhook_pasiflesti"] == "api"


# ---------------------------------------------------------------------------
# Sayfalama, idempotency, yazma uçları
# ---------------------------------------------------------------------------
async def test_sayfalama_cursor_ve_updated_since(istemci, yonetici_basligi, db_oturumu):
    e = await _musteri(istemci, yonetici_basligi)
    idler = [(await _proje(db_oturumu, e, f"P{i}")).id for i in range(5)]
    ham, _ = await _anahtar(istemci, _b(e), M)
    gorulen, cursor = [], None
    for _ in range(5):
        y = await istemci.get(f"{P}/projeler", params={"limit": 2, **({"cursor": cursor} if cursor else {})}, headers=_k(ham))
        govde = y.json()
        gorulen += [x["id"] for x in govde["veri"]]
        cursor = govde["sonraki_cursor"]
        if not govde["daha_var"]:
            assert cursor is None
            break
    assert gorulen == idler
    y = await istemci.get(f"{P}/projeler", params={"updated_since": _gelecek(1)}, headers=_k(ham))
    assert y.json()["veri"] == []
    gecmis = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    y = await istemci.get(f"{P}/projeler", params={"updated_since": gecmis}, headers=_k(ham))
    assert len(y.json()["veri"]) == 5
    for params, kod in (({"cursor": "bozuk!"}, "cursor_gecersiz"), ({"updated_since": "dün"}, "tarih_gecersiz"),
                        ({"limit": 101}, "gecersiz_istek")):
        y = await istemci.get(f"{P}/projeler", params=params, headers=_k(ham))
        assert y.status_code in (400, 422) and _kod(y) == kod, (params, y.text)


async def test_idempotency_ayni_anahtar_ayni_yanit(istemci, yonetici_basligi, db_oturumu):
    from models.support_tickets import Support_tickets

    e = await _musteri(istemci, yonetici_basligi)
    ham, _ = await _anahtar(istemci, _b(e), M, kapsamlar=["destek:oku", "destek:yaz"])
    idem = uuid.uuid4().hex
    govde = {"konu": "API talebi", "mesaj": "Merhaba", "oncelik": "yuksek"}
    y1 = await istemci.post(f"{P}/destek", json=govde, headers=_k(ham, **{"Idempotency-Key": idem}))
    assert y1.status_code == 201, y1.text
    assert y1.json()["hesap"] == e and y1.json()["kaynak"] == "api" and y1.json()["oncelik"] == "yuksek"
    y2 = await istemci.post(f"{P}/destek", json=govde, headers=_k(ham, **{"Idempotency-Key": idem}))
    assert y2.status_code == 201 and y2.json() == y1.json() and y2.headers.get("Idempotent-Replayed") == "true"
    y3 = await istemci.post(f"{P}/destek", json={**govde, "mesaj": "Başka"}, headers=_k(ham, **{"Idempotency-Key": idem}))
    assert y3.status_code == 422 and _kod(y3) == "idempotency_uyusmazligi"
    sayi = (await db_oturumu.execute(select(Support_tickets).where(Support_tickets.client_email == e))).scalars().all()
    assert len(sayi) == 1
    # Yanıt ucu da idempotent; talep ayrıntısında yazışma görünür (yazanın e-postası yok).
    tid = y1.json()["id"]
    idem2 = uuid.uuid4().hex
    for _ in range(2):
        y = await istemci.post(f"{P}/destek/{tid}/yanit", json={"mesaj": "Ek bilgi"}, headers=_k(ham, **{"Idempotency-Key": idem2}))
        assert y.status_code == 201 and y.json()["yazan"] == "musteri"
    ayr = (await istemci.get(f"{P}/destek/{tid}", headers=_k(ham))).json()
    assert [m["mesaj"] for m in ayr["mesajlar"]] == ["Ek bilgi"] and "yazan_email" not in json.dumps(ayr)
    # Geçersiz gövde: tutarlı hata biçimi.
    y = await istemci.post(f"{P}/destek", json={"konu": ""}, headers=_k(ham))
    assert y.status_code == 422 and _kod(y) == "gecersiz_istek" and y.json()["hata"]["ayrinti"]


async def test_gorev_olustur_guncelle_musteri_ve_ajans(istemci, yonetici_basligi, db_oturumu):
    from models.proje_gorevleri import ProjectTasks

    e = await _musteri(istemci, yonetici_basligi)
    p = await _proje(db_oturumu, e)
    gizli = ProjectTasks(proje_id=p.id, baslik="İç görev", durum="yapilacak", oncelik="normal", sira=0,
                         musteriye_gorunur=False, harcanan_saat=0.0, olusturan_eposta="yonetici@test.dev")
    acik = ProjectTasks(proje_id=p.id, baslik="Ajans görevi", durum="suruyor", oncelik="normal", sira=1,
                        musteriye_gorunur=True, harcanan_saat=0.0, olusturan_eposta="yonetici@test.dev")
    db_oturumu.add_all([gizli, acik])
    await db_oturumu.commit()
    ham, _ = await _anahtar(istemci, _b(e), M, kapsamlar=["gorevler:oku", "gorevler:yaz"])
    y = await istemci.get(f"{P}/gorevler", params={"proje_id": p.id}, headers=_k(ham))
    assert [g["baslik"] for g in y.json()["veri"]] == ["Ajans görevi"]
    assert y.json()["veri"][0]["musteriye_gorunur"] is None
    assert (await istemci.get(f"{P}/gorevler/{gizli.id}", headers=_k(ham))).status_code == 404
    y = await istemci.post(f"{P}/gorevler", json={"proje_id": p.id, "baslik": "Müşteri isteği", "durum": "tamam",
                                                   "musteriye_gorunur": False}, headers=_k(ham))
    assert y.status_code == 201, y.text
    g = y.json()
    assert g["durum"] == "yapilacak" and g["oncelik"] == "normal"
    y = await istemci.patch(f"{P}/gorevler/{g['id']}", json={"durum": "tamam", "baslik": "Müşteri isteği (güncel)"},
                            headers=_k(ham))
    assert y.status_code == 200 and y.json()["durum"] == "tamam" and y.json()["tamamlandi_at"]
    y = await istemci.patch(f"{P}/gorevler/{acik.id}", json={"durum": "tamam"}, headers=_k(ham))
    assert y.status_code == 403 and _kod(y) == "gorev_degistirilemez"
    # Başka hesabın projesine görev açılamaz.
    diger = await _proje(db_oturumu, _e())
    y = await istemci.post(f"{P}/gorevler", json={"proje_id": diger.id, "baslik": "x"}, headers=_k(ham))
    assert y.status_code == 404
    # Ajans anahtarı: durum ve görünürlük verebilir, her görevi günceller.
    ajans, _ = await _anahtar(istemci, yonetici_basligi, kapsamlar=["gorevler:oku", "gorevler:yaz"])
    y = await istemci.post(f"{P}/gorevler", json={"proje_id": p.id, "baslik": "Ajans API", "durum": "suruyor",
                                                   "musteriye_gorunur": True}, headers=_k(ajans))
    assert y.status_code == 201 and y.json()["durum"] == "suruyor" and y.json()["musteriye_gorunur"] is True
    y = await istemci.patch(f"{P}/gorevler/{gizli.id}", json={"oncelik": "acil"}, headers=_k(ajans))
    assert y.status_code == 200 and y.json()["oncelik"] == "acil"


async def test_crm_yalniz_ajans(istemci, yonetici_basligi):
    ajans, _ = await _anahtar(istemci, yonetici_basligi, kapsamlar=["crm:oku", "crm:yaz"])
    eposta = _e("aday")
    y = await istemci.post(f"{P}/crm/adaylar", json={"ad": "Ayşe", "firma": "Acme", "email": eposta, "deger_tahmini": 1500},
                           headers=_k(ajans))
    assert y.status_code == 201, y.text
    assert y.json()["email"] == eposta and y.json()["kaynak"] == "manuel"
    y2 = await istemci.post(f"{P}/crm/adaylar", json={"ad": "Ayşe", "email": eposta}, headers=_k(ajans))
    assert y2.status_code == 409 and _kod(y2) == "ayni_eposta_acik_aday"
    y = await istemci.get(f"{P}/crm/adaylar/{y.json()['id']}", headers=_k(ajans))
    assert y.status_code == 200 and y.json()["firma"] == "Acme"


async def test_hesap_ozeti_ve_openapi(istemci, yonetici_basligi, db_oturumu):
    e = await _musteri(istemci, yonetici_basligi)
    await _proje(db_oturumu, e)
    ham, _ = await _anahtar(istemci, _b(e), M, kapsamlar=["projeler:oku", "destek:oku"])
    y = await istemci.get(f"{P}/hesap", headers=_k(ham))
    assert y.status_code == 200
    assert y.json()["sahip"] == "musteri" and y.json()["hesap"] == e and y.json()["sayilar"]["projeler"] == 1
    assert y.json()["anahtar"]["kapsamlar"] == ["destek:oku", "projeler:oku"]
    belge = (await istemci.get(f"{P}/openapi.json")).json()
    assert belge["info"]["title"] == "mehmetkuru.dev API"
    assert all(yol.startswith("/api/public/v1/") for yol in belge["paths"])
    assert "/api/public/v1/mcp" not in belge["paths"] and "/api/public/v1/openapi.json" not in belge["paths"]
    assert belge["paths"]["/api/public/v1/gorevler"]["post"]["x-kapsam"] == "gorevler:yaz"
    assert belge["paths"]["/api/public/v1/projeler"]["get"]["x-kapsam"] == "projeler:oku"
    assert {"bearer", "apiAnahtari"} <= set(belge["components"]["securitySchemes"])
    assert "HataYaniti" in belge["components"]["schemas"]


# ---------------------------------------------------------------------------
# Webhook: imza, SSRF, teslimat
# ---------------------------------------------------------------------------
def _belgedeki_python_dogrulama(gizli: str, zaman: str, govde: bytes, baslik: str, tolerans: int = 300) -> bool:
    """Panel belgesindeki Python örneğiyle aynı mantık (örneğin kendisi aşağıda ayrıca çalıştırılıyor)."""
    if abs(time.time() - int(zaman)) > tolerans:
        return False
    beklenen = hmac.new(gizli.encode(), f"{zaman}.".encode() + govde, hashlib.sha256).hexdigest()
    return any(
        hmac.compare_digest(p.split("=", 1)[1], beklenen) for p in baslik.split() if p.startswith("v1=")
    )


ON_YUZ = Path(__file__).resolve().parents[3] / "frontend" / "src"


def _belgedeki_ornek(ad: str) -> str:
    metin = (ON_YUZ / "components" / "apiErisimi" / "Belgeler.tsx").read_text(encoding="utf-8")
    bas = metin.index(f"const {ad} = `") + len(f"const {ad} = `")
    return metin[bas: metin.index("`;", bas)]


def test_belgedeki_python_ornegi_calisir_ve_sunucu_imzasini_dogrular():
    from services import webhook as w

    ad_alani: dict = {}
    exec(compile(_belgedeki_ornek("ORNEK_PYTHON"), "ornek_python", "exec"), ad_alani)  # noqa: S102 - kendi belgemiz
    dogrula = ad_alani["verify"]
    gizli, zaman, govde = w.gizli_uret(), str(int(time.time())), '{"id":"evt_x","tur":"ping","veri":{"ç":"ğ"}}'
    baslik = w.imza_basligi([gizli], zaman, govde)
    assert dogrula(gizli, zaman, govde.encode("utf-8"), baslik)
    assert not dogrula("whsec_yanlis", zaman, govde.encode("utf-8"), baslik)
    assert not dogrula(gizli, str(int(time.time()) - 400), govde.encode("utf-8"), w.imza_basligi([gizli], str(int(time.time()) - 400), govde))
    assert dogrula(gizli, zaman, govde.encode("utf-8"), w.imza_basligi(["baska", gizli], zaman, govde))
    # Node örneği de aynı biçimi (v1=, boşlukla ayrılmış, zaman + "." + ham gövde) kullanıyor.
    node = _belgedeki_ornek("ORNEK_NODE")
    assert "createHmac('sha256', secret)" in node and "timingSafeEqual" in node and "startsWith('v1=')" in node


def test_ek_paket_yedi_dilde_ve_kataloglarla_uyumlu():
    from services import api_erisimi as s
    from services import webhook as w

    def duz(d, on=""):
        for k, v in d.items():
            if isinstance(v, dict):
                yield from duz(v, f"{on}{k}.")
            else:
                yield f"{on}{k}", v

    paketler = {
        dil: dict(duz(json.loads((ON_YUZ / "i18n" / "ek" / "apiErisimi" / f"{dil}.json").read_text(encoding="utf-8"))["apiErisimi"]))
        for dil in ("tr", "en", "de", "ru", "zh", "hi", "ar")
    }
    anahtarlar = set(paketler["tr"])
    for dil, p in paketler.items():
        assert set(p) == anahtarlar, dil
        assert all(isinstance(v, str) and v.strip() for v in p.values()), dil
    urun_adlari = {"mcp.desktop", "mcp.code"}
    for dil in ("en", "de", "ru", "zh", "hi", "ar"):
        ayni = [k for k in anahtarlar - urun_adlari if paketler[dil][k] == paketler["tr"][k] and len(paketler["tr"][k]) > 12]
        assert not ayni, (dil, ayni[:5])
    assert {k.split(".", 1)[1] for k in anahtarlar if k.startswith("kapsam.")} == {k.anahtar.replace(":", "_") for k in s.KAPSAMLAR}
    assert {k.split(".", 1)[1] for k in anahtarlar if k.startswith("olay.")} == {o.anahtar.replace(".", "_") for o in w.OLAY_TURLERI} | {"ping"}
    # Sekme etiketi ana pakette (yalnız o), modül adı modül ek paketinde.
    for dil in paketler:
        ana = json.loads((ON_YUZ / "i18n" / f"{dil}.json").read_text(encoding="utf-8"))
        assert ana["ui"]["tabApi"] and "apiErisimi" not in ana


def test_imza_algoritmasi_belgedeki_ornekle_ayni():
    from services import webhook as w

    gizli, zaman, govde = "whsec_deneme", str(int(time.time())), '{"id":"evt_1","tur":"ping"}'
    baslik = w.imza_basligi([gizli], zaman, govde)
    assert baslik == "v1=" + hmac.new(gizli.encode(), f"{zaman}.{govde}".encode(), hashlib.sha256).hexdigest()
    assert _belgedeki_python_dogrulama(gizli, zaman, govde.encode(), baslik)
    assert w.imza_dogrula(gizli, zaman, govde, baslik)
    assert not w.imza_dogrula("whsec_baska", zaman, govde, baslik)
    assert not w.imza_dogrula(gizli, zaman, govde + " ", baslik)
    eski = str(int(time.time()) - 301)
    assert not w.imza_dogrula(gizli, eski, govde, w.imza_basligi([gizli], eski, govde))
    iki = w.imza_basligi(["yeni", "eski"], zaman, govde)
    assert w.imza_dogrula("yeni", zaman, govde, iki) and w.imza_dogrula("eski", zaman, govde, iki)


@pytest.mark.parametrize(
    "url,dns,kod",
    [
        ("http://ornek.com/kanca", None, "url_https_gerekli"),
        ("https://127.0.0.1/kanca", None, "url_adres_yasak"),
        ("https://localhost/kanca", None, "url_adres_yasak"),
        ("https://169.254.169.254/latest/meta-data", None, "url_adres_yasak"),
        ("https://metadata.google.internal/computeMetadata", None, "url_adres_yasak"),
        ("https://[::1]/kanca", None, "url_adres_yasak"),
        ("https://ornek.com:8443/kanca", None, "url_adres_gecersiz"),
        ("https://kullanici:sifre@ornek.com/kanca", None, "url_adres_gecersiz"),
        ("https://ic.ornek.com/kanca", ["10.0.0.5"], "url_adres_yasak"),
        ("https://karisik.ornek.com/kanca", ["93.184.216.34", "192.168.1.2"], "url_adres_yasak"),
        ("ftp://ornek.com/x", None, "url_https_gerekli"),
    ],
)
async def test_ssrf_reddi(istemci, yonetici_basligi, alici, monkeypatch, url, dns, kod):
    from services import site_analizi

    if dns is not None:
        async def _dns(host, port):
            return dns

        monkeypatch.setattr(site_analizi, "_dns_cozumle", _dns)
    y = await istemci.post(f"{Y}/webhooklar", json={"url": url, "olaylar": ["fatura.odendi"]}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == kod, (url, y.text)


async def _uc(istemci, basliklar, yol=Y, **govde):
    govde.setdefault("url", "https://alici.ornek.com/kanca")
    govde.setdefault("olaylar", ["destek.olusturuldu"])
    y = await istemci.post(f"{yol}/webhooklar", json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()["gizli"], y.json()["uc"]


async def test_test_olayi_imzali_teslim_edilir_ve_gecmiste_gorunur(istemci, yonetici_basligi, alici, db_oturumu):
    from models.audit_log import AuditLog

    gizli, uc = await _uc(istemci, yonetici_basligi)
    assert gizli.startswith("whsec_")
    assert gizli not in (await istemci.get(f"{Y}/webhooklar", headers=yonetici_basligi)).text
    y = await istemci.post(f"{Y}/webhooklar/{uc['id']}/test", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["basarili"] is True and y.json()["durum_kodu"] == 200, y.text
    istek = alici.istekler[-1]
    govde = istek.content
    assert istek.method == "POST" and istek.headers["content-type"].startswith("application/json")
    assert istek.headers["MK-Webhook-Id"] == y.json()["olay_id"]
    assert _belgedeki_python_dogrulama(gizli, istek.headers["MK-Webhook-Zaman"], govde, istek.headers["MK-Webhook-Imza"])
    veri = json.loads(govde)
    assert set(veri) == {"id", "tur", "olusturma", "hesap", "veri"} and veri["tur"] == "ping" and veri["hesap"] is None
    gecmis = (await istemci.get(f"{Y}/webhooklar/{uc['id']}/teslimatlar", headers=yonetici_basligi)).json()["items"]
    assert gecmis[0]["tur"] == "ping" and gecmis[0]["durum"] == "basarili"
    assert gecmis[0]["denemeler"][0]["tetik"] == "test" and gecmis[0]["denemeler"][0]["durum_kodu"] == 200
    # Sır denetim kaydında düz yazılmaz.
    for d in (await db_oturumu.execute(select(AuditLog).where(AuditLog.tablo == "webhook_uc_noktalari"))).scalars().all():
        assert gizli not in (d.degisiklik_json or "")


async def test_dns_yeniden_baglama_teslimatta_reddedilir(istemci, yonetici_basligi, alici, monkeypatch):
    from services import site_analizi

    _, uc = await _uc(istemci, yonetici_basligi)

    async def _ic(host, port):
        return ["127.0.0.1"]

    monkeypatch.setattr(site_analizi, "_dns_cozumle", _ic)
    y = await istemci.post(f"{Y}/webhooklar/{uc['id']}/test", headers=yonetici_basligi)
    assert y.json()["basarili"] is False and y.json()["hata"] == "adres_adres_yasak"
    assert alici.istekler == []  # istek hiç çıkmadı


async def test_olay_dogru_hesaba_yonlenir(istemci, yonetici_basligi, alici, db_oturumu):
    from models.api_erisimi import WebhookTeslimatlari
    from services import webhook as w

    a, b = await _musteri(istemci, yonetici_basligi), await _musteri(istemci, yonetici_basligi)
    _, ua = await _uc(istemci, _b(a), M, olaylar=["destek.olusturuldu", "fatura.olusturuldu"])
    _, ub = await _uc(istemci, _b(b), M, olaylar=["destek.olusturuldu"])
    _, uj = await _uc(istemci, yonetici_basligi, olaylar=["destek.olusturuldu", "aday.olusturuldu"])
    _, ut = await _uc(istemci, yonetici_basligi, olaylar=["destek.olusturuldu"], tum_musteriler=True)
    # Müşteri A panelden talep açar.
    y = await istemci.post("/api/v1/entities/support_tickets", json={"subject": "Yardım", "message": "Site açılmıyor"},
                           headers=_b(a))
    assert y.status_code == 201, y.text
    satirlar = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.tur == "destek.olusturuldu"))).scalars().all()
    assert sorted(t.uc_id for t in satirlar) == sorted([ua["id"], ut["id"]])
    govde = json.loads(satirlar[0].govde)
    assert govde["hesap"] == a and govde["veri"]["talep_id"] == y.json()["id"] and "Site açılmıyor" not in satirlar[0].govde
    # Ajansın kendi olayı (CRM adayı, iletişim formundan) yalnız ajans uç noktalarına.
    y = await istemci.post("/api/v1/entities/inquiries", json={"name": "Aday", "email": _e("form"), "message": "Teklif"})
    assert y.status_code in (200, 201), y.text
    aday = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.tur == "aday.olusturuldu"))).scalars().all()
    assert [t.uc_id for t in aday] == [uj["id"]]
    assert "email" not in json.loads(aday[0].govde)["veri"]
    # Teslim: hepsi gider, imzalar uç noktasının sırrıyla.
    w.onbellegi_temizle()
    ozet = await w.bekleyenleri_isle(db_oturumu)
    assert ozet["basarili"] == 3 and len(alici.istekler) == 3


async def test_flush_kancasi_fatura_gorev_asama_olaylari(istemci, yonetici_basligi, alici, db_oturumu):
    from models.api_erisimi import WebhookTeslimatlari
    from models.invoices import Invoices
    from models.proje_gorevleri import ProjectTasks

    e = await _musteri(istemci, yonetici_basligi)
    _, uc = await _uc(istemci, _b(e), M, olaylar=["fatura.olusturuldu", "fatura.odendi", "gorev.olusturuldu",
                                                  "gorev.tamamlandi", "proje.asama_degisti"])
    p = await _proje(db_oturumu, e)
    f = Invoices(invoice_no=f"F-{uuid.uuid4().hex[:6]}", client_email=e, amount=100.0, status="draft")
    db_oturumu.add(f)
    await db_oturumu.commit()
    f.status = "unpaid"
    await db_oturumu.commit()
    f.status = "paid"
    await db_oturumu.commit()
    gizli = ProjectTasks(proje_id=p.id, baslik="İç", durum="yapilacak", oncelik="normal", sira=0, musteriye_gorunur=False,
                         harcanan_saat=0.0)
    acik = ProjectTasks(proje_id=p.id, baslik="Açık", durum="yapilacak", oncelik="normal", sira=1, musteriye_gorunur=True,
                        harcanan_saat=0.0)
    db_oturumu.add_all([gizli, acik])
    await db_oturumu.commit()
    acik.durum = "tamam"
    gizli.durum = "tamam"
    p.stage = "tasarim"
    await db_oturumu.commit()
    turler = [t.tur for t in (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc["id"])
                                                      .order_by(WebhookTeslimatlari.id))).scalars().all()]
    # Taslak fatura olay üretmez; kesilince "oluşturuldu", ödenince "ödendi". Müşteriye görünmeyen görev olmaz.
    # (Aynı flush'taki görev ve proje değişikliklerinin sırası tanımsız: son ikisi küme olarak.)
    assert turler[:3] == ["fatura.olusturuldu", "fatura.odendi", "gorev.olusturuldu"]
    assert sorted(turler[3:]) == ["gorev.tamamlandi", "proje.asama_degisti"]


async def test_yeniden_deneme_zamanlamasi_ve_vazgecme(istemci, yonetici_basligi, alici, db_oturumu):
    from models.api_erisimi import WebhookDenemeleri, WebhookTeslimatlari
    from services import webhook as w

    alici.durum = 500
    e = await _musteri(istemci, yonetici_basligi)
    _, uc = await _uc(istemci, _b(e), M)
    await istemci.post("/api/v1/entities/support_tickets", json={"subject": "a", "message": "b"}, headers=_b(e))
    t = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc["id"]))).scalars().one()
    beklenen = [timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2), timedelta(hours=6), timedelta(hours=12),
                timedelta(hours=24), timedelta(hours=24)]
    for i in range(w.EN_COK_DENEME):
        once = datetime.now(timezone.utc)
        ozet = await w.bekleyenleri_isle(db_oturumu)
        assert ozet["basarisiz"] == 1, (i, ozet)
        await db_oturumu.refresh(t)
        assert t.deneme_sayisi == i + 1 and t.son_durum_kodu == 500
        if i < len(beklenen):
            assert t.durum == "bekliyor"
            fark = w.utc(t.sonraki_deneme) - once
            assert beklenen[i] - timedelta(seconds=5) <= fark <= beklenen[i] + timedelta(seconds=5), (i, fark)
            # Zamanı gelmeden işlenmez.
            assert (await w.bekleyenleri_isle(db_oturumu))["islenen"] == 0
            await db_oturumu.execute(update(WebhookTeslimatlari).where(WebhookTeslimatlari.id == t.id)
                                     .values(sonraki_deneme=datetime.now(timezone.utc) - timedelta(seconds=1)))
            await db_oturumu.commit()
    assert t.durum == "vazgecildi" and t.deneme_sayisi == 8
    assert len((await db_oturumu.execute(select(WebhookDenemeleri).where(WebhookDenemeleri.teslimat_id == t.id))).scalars().all()) == 8
    # 3 günü geçen teslimattan ilk başarısızlıkta vazgeçilir.
    await istemci.post("/api/v1/entities/support_tickets", json={"subject": "c", "message": "d"}, headers=_b(e))
    t2 = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc["id"], WebhookTeslimatlari.id != t.id))).scalars().one()
    await db_oturumu.execute(update(WebhookTeslimatlari).where(WebhookTeslimatlari.id == t2.id)
                             .values(created_at=datetime.now(timezone.utc) - timedelta(days=3, minutes=1)))
    await db_oturumu.commit()
    await w.bekleyenleri_isle(db_oturumu)
    await db_oturumu.refresh(t2)
    assert t2.durum == "vazgecildi" and t2.deneme_sayisi == 1


async def test_otomatik_pasiflestirme_ve_bildirim(istemci, yonetici_basligi, alici, db_oturumu, monkeypatch):
    from models.api_erisimi import WebhookTeslimatlari, WebhookUcNoktalari
    from models.notifications import Notifications
    from services import webhook as w

    monkeypatch.setattr(w, "OTOMATIK_PASIF_ESIGI", 3)
    alici.durum = 503
    e = await _musteri(istemci, yonetici_basligi)
    _, uc = await _uc(istemci, _b(e), M)
    for i in range(4):
        await istemci.post("/api/v1/entities/support_tickets", json={"subject": f"t{i}", "message": "m"}, headers=_b(e))
    # Turda düşen uç noktasının diğer teslimatları sonraki tura kalır (dört tur).
    for _ in range(3):
        await db_oturumu.execute(update(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc["id"],
                                                                   WebhookTeslimatlari.durum == "bekliyor")
                                 .values(sonraki_deneme=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db_oturumu.commit()
        await w.bekleyenleri_isle(db_oturumu)
    satir = (await db_oturumu.execute(select(WebhookUcNoktalari).where(WebhookUcNoktalari.id == uc["id"])
                                      .execution_options(populate_existing=True))).scalars().one()
    assert satir.aktif is False and satir.pasif_sebebi == "ardisik_hata"
    durumlar = {t.durum for t in (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc["id"]))).scalars().all()}
    assert "bekliyor" not in durumlar
    bildirim = (await db_oturumu.execute(select(Notifications).where(Notifications.event_type == "webhook_pasiflesti",
                                                                     Notifications.recipient_email == e))).scalars().all()
    assert bildirim and bildirim[0].link == "/client?sekme=api"
    # Elle yeniden açılınca sayaç sıfırlanır.
    y = await istemci.put(f"{M}/webhooklar/{uc['id']}", json={"aktif": True}, headers=_b(e))
    assert y.json()["aktif"] is True and y.json()["ardisik_hata"] == 0 and y.json()["pasif_sebebi"] is None


async def test_teslimat_kaydi_kirpilir_ve_yeniden_gonder(istemci, yonetici_basligi, alici, db_oturumu):
    alici.govde = ("ç" * 3000).encode()
    alici.durum = 400
    _, uc = await _uc(istemci, yonetici_basligi)
    y = await istemci.post(f"{Y}/webhooklar/{uc['id']}/test", headers=yonetici_basligi)
    assert y.json()["basarili"] is False and y.json()["durum_kodu"] == 400
    gecmis = (await istemci.get(f"{Y}/webhooklar/{uc['id']}/teslimatlar", headers=yonetici_basligi)).json()["items"]
    t = gecmis[0]
    assert len(t["son_yanit"].encode("utf-8")) <= 1024 + 3 and t["durum"] == "vazgecildi"
    assert len(t["denemeler"][0]["yanit"].encode("utf-8")) <= 1024 + 3
    alici.durum, alici.govde = 204, b""
    y = await istemci.post(f"{Y}/webhooklar/{uc['id']}/teslimatlar/{t['id']}/yeniden-gonder", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["basarili"] is True and y.json()["deneme_no"] == 2
    gecmis = (await istemci.get(f"{Y}/webhooklar/{uc['id']}/teslimatlar", headers=yonetici_basligi)).json()["items"]
    assert gecmis[0]["durum"] == "basarili" and [d["tetik"] for d in gecmis[0]["denemeler"]] == ["test", "elle"]
    # Başka sahibin uç noktası/teslimatı görünmez.
    e = await _musteri(istemci, yonetici_basligi)
    assert (await istemci.get(f"{M}/webhooklar/{uc['id']}/teslimatlar", headers=_b(e))).status_code == 404


async def test_gizli_yenileme_iki_imza(istemci, yonetici_basligi, alici):
    eski, uc = await _uc(istemci, yonetici_basligi)
    y = await istemci.post(f"{Y}/webhooklar/{uc['id']}/gizli-yenile", headers=yonetici_basligi)
    yeni = y.json()["gizli"]
    assert yeni != eski and y.json()["uc"]["gizli_gecis_bitis"]
    await istemci.post(f"{Y}/webhooklar/{uc['id']}/test", headers=yonetici_basligi)
    istek = alici.istekler[-1]
    baslik = istek.headers["MK-Webhook-Imza"]
    assert len(baslik.split()) == 2
    for g in (eski, yeni):
        assert _belgedeki_python_dogrulama(g, istek.headers["MK-Webhook-Zaman"], istek.content, baslik)


async def test_arka_plan_teslimati_istegi_beklemeden(istemci, yonetici_basligi, alici, db_oturumu, monkeypatch):
    from models.api_erisimi import WebhookTeslimatlari
    from services import webhook as w

    monkeypatch.setattr(w, "ANLIK_TESLIMAT", True)
    e = await _musteri(istemci, yonetici_basligi)
    _, uc = await _uc(istemci, _b(e), M)
    y = await istemci.post("/api/v1/entities/support_tickets", json={"subject": "Arka", "message": "plan"}, headers=_b(e))
    assert y.status_code == 201
    await w.pompa_bitmesini_bekle()
    t = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc["id"])
                                  .execution_options(populate_existing=True))).scalars().one()
    assert t.durum == "basarili" and t.deneme_sayisi == 1 and len(alici.istekler) == 1


async def test_qr_tarama_olayi_istege_bagli(istemci, yonetici_basligi, alici, db_oturumu):
    from models.api_erisimi import WebhookTeslimatlari
    from models.dinamik_qr import DinamikQr

    e = await _musteri(istemci, yonetici_basligi)
    _, uc = await _uc(istemci, _b(e), M, olaylar=["qr.tarama"])
    meta = (await istemci.get(f"{M}/meta", headers=_b(e))).json()
    assert next(o for o in meta["olaylar"] if o["anahtar"] == "qr.tarama")["varsayilan"] is False
    kod = uuid.uuid4().hex[:7]
    db_oturumu.add(DinamikQr(hesap_email=e, kod=kod, ad="QR", tur="url", alanlar=json.dumps({"url": "https://ornek.com"}),
                             hedef="https://ornek.com", tarama_sayisi=0, aktif=True, engelli=False, kisa_link=False))
    await db_oturumu.commit()
    y = await istemci.get(f"/api/v1/q/{kod}", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120",
                                                      "X-MK-Istemci-IP": "198.51.100.3"})
    assert y.status_code == 302
    t = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc["id"]))).scalars().all()
    assert len(t) == 1 and json.loads(t[0].govde)["veri"]["kod"] == kod and "ip" not in t[0].govde


async def test_webhook_siniri_ve_musteri_olay_kisiti(istemci, yonetici_basligi, alici):
    e = await _musteri(istemci, yonetici_basligi, webhook_siniri=1)
    await _uc(istemci, _b(e), M)
    y = await istemci.post(f"{M}/webhooklar", json={"url": "https://iki.ornek.com/k", "olaylar": ["fatura.odendi"]},
                           headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "webhook_siniri"
    e2 = await _musteri(istemci, yonetici_basligi)
    y = await istemci.post(f"{M}/webhooklar", json={"url": "https://x.ornek.com/k", "olaylar": ["aday.olusturuldu"]},
                           headers=_b(e2))
    assert y.status_code == 400 and _kod(y) == "olay_yalniz_ajans"
    # Müşteri `tum_musteriler` bayrağını açamaz.
    _, uc = await _uc(istemci, _b(e2), M, tum_musteriler=True)
    assert uc["tum_musteriler"] is False


async def test_temizlik_30_gun(istemci, yonetici_basligi, alici, db_oturumu):
    from models.api_erisimi import WebhookTeslimatlari
    from services import webhook as w

    _, uc = await _uc(istemci, yonetici_basligi)
    await istemci.post(f"{Y}/webhooklar/{uc['id']}/test", headers=yonetici_basligi)
    await istemci.post(f"{Y}/webhooklar/{uc['id']}/test", headers=yonetici_basligi)
    ilk = (await db_oturumu.execute(select(WebhookTeslimatlari.id).where(WebhookTeslimatlari.uc_id == uc["id"])
                                    .order_by(WebhookTeslimatlari.id))).scalars().first()
    await db_oturumu.execute(update(WebhookTeslimatlari).where(WebhookTeslimatlari.id == ilk)
                             .values(created_at=datetime.now(timezone.utc) - timedelta(days=31)))
    await db_oturumu.commit()
    sonuc = await w.temizle(db_oturumu)
    assert sonuc["teslimat"] == 1 and sonuc["deneme"] == 1
    kalan = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc["id"]))).scalars().all()
    assert len(kalan) == 1


def test_zamanli_gorevleri_kayitli():
    from services.zamanli import GOREV_ADLARI

    assert "webhook_teslimatlari" in GOREV_ADLARI and "webhook_temizligi" in GOREV_ADLARI
    assert GOREV_ADLARI[-1] == "aylik_site_analizi"


async def test_uc_noktasi_silinir(istemci, yonetici_basligi, alici):
    _, uc = await _uc(istemci, yonetici_basligi)
    await istemci.post(f"{Y}/webhooklar/{uc['id']}/test", headers=yonetici_basligi)
    y = await istemci.delete(f"{Y}/webhooklar/{uc['id']}", headers=yonetici_basligi)
    assert y.status_code == 200
    assert (await istemci.get(f"{Y}/webhooklar/{uc['id']}/teslimatlar", headers=yonetici_basligi)).status_code == 404


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------
async def _rpc(istemci, ham, yontem, params=None, kimlik=1, **basliklar):
    govde = {"jsonrpc": "2.0", "id": kimlik, "method": yontem}
    if params is not None:
        govde["params"] = params
    return await istemci.post(f"{P}/mcp", json=govde, headers=_k(ham, Accept="application/json, text/event-stream", **basliklar))


async def test_mcp_initialize_ve_araclar_kapsama_gore(istemci, yonetici_basligi, db_oturumu):
    e = await _musteri(istemci, yonetici_basligi)
    await _proje(db_oturumu, e, "MCP projesi")
    oku, _ = await _anahtar(istemci, _b(e), M, kapsamlar=["projeler:oku", "destek:oku"])
    y = await _rpc(istemci, oku, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                "clientInfo": {"name": "test", "version": "1"}})
    assert y.status_code == 200
    sonuc = y.json()["result"]
    assert sonuc["protocolVersion"] == "2025-06-18" and "tools" in sonuc["capabilities"]
    assert sonuc["serverInfo"]["name"] == "mehmetkuru-dev"
    y = await _rpc(istemci, oku, "initialize", {"protocolVersion": "1999-01-01"})
    assert y.json()["result"]["protocolVersion"] == "2025-06-18"
    y = await istemci.post(f"{P}/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=_k(oku))
    assert y.status_code == 202 and y.content == b""
    araclar = {a["name"] for a in (await _rpc(istemci, oku, "tools/list")).json()["result"]["tools"]}
    assert araclar == {"hesap_ozeti", "projeleri_listele", "proje_getir", "destek_talepleri_listele", "destek_talebi_getir"}
    yaz, _ = await _anahtar(istemci, _b(e), M, kapsamlar=["destek:oku", "destek:yaz"])
    araclar = {a["name"] for a in (await _rpc(istemci, yaz, "tools/list")).json()["result"]["tools"]}
    assert {"destek_talebi_olustur", "destek_talebini_yanitla"} <= araclar and "projeleri_listele" not in araclar
    ajans, _ = await _anahtar(istemci, yonetici_basligi, kapsamlar=["crm:oku", "crm:yaz"])
    tanimlar = (await _rpc(istemci, ajans, "tools/list")).json()["result"]["tools"]
    adlar = {a["name"] for a in tanimlar}
    assert {"crm_adaylarini_listele", "crm_adayi_olustur"} <= adlar
    for t in tanimlar:
        assert t["description"] and t["inputSchema"]["type"] == "object"
    assert next(t for t in tanimlar if t["name"] == "crm_adayi_olustur")["annotations"]["readOnlyHint"] is False


async def test_mcp_tools_call_ve_hatalar(istemci, yonetici_basligi, db_oturumu):
    e = await _musteri(istemci, yonetici_basligi)
    p = await _proje(db_oturumu, e, "Çağrı projesi")
    ham, _ = await _anahtar(istemci, _b(e), M, kapsamlar=["projeler:oku"])
    y = await _rpc(istemci, ham, "tools/call", {"name": "projeleri_listele", "arguments": {"limit": 5}})
    r = y.json()["result"]
    assert r["isError"] is False and r["structuredContent"]["veri"][0]["id"] == p.id
    assert json.loads(r["content"][0]["text"])["veri"][0]["baslik"] == "Çağrı projesi"
    y = await _rpc(istemci, ham, "tools/call", {"name": "proje_getir", "arguments": {"proje_id": 999999}})
    assert y.json()["result"]["isError"] is True and "bulunamadi" in y.json()["result"]["content"][0]["text"]
    # Kapsam dışı araç listede yok → bilinmeyen araç (yazma aracı görünmüyor, çağrılamıyor).
    y = await _rpc(istemci, ham, "tools/call", {"name": "gorev_olustur", "arguments": {"proje_id": p.id, "baslik": "x"}})
    assert y.json()["error"]["code"] == -32602
    y = await _rpc(istemci, ham, "resources/list")
    assert y.json()["error"]["code"] == -32601
    # Toplu ileti (2025-03-26) ve ping.
    y = await istemci.post(f"{P}/mcp", json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"},
                                            {"jsonrpc": "2.0", "method": "notifications/cancelled"}], headers=_k(ham))
    assert y.json() == [{"jsonrpc": "2.0", "id": 1, "result": {}}]
    # HTTP katmanı.
    assert (await istemci.get(f"{P}/mcp", headers=_k(ham))).status_code == 405
    assert (await istemci.post(f"{P}/mcp", content=b"{bozuk", headers=_k(ham))).json()["error"]["code"] == -32700
    y = await _rpc(istemci, ham, "ping", Origin="https://kotu.ornek.com")
    assert y.status_code == 403
    y = await _rpc(istemci, ham, "ping", **{"MCP-Protocol-Version": "1990-01-01"})
    assert y.status_code == 400
    y = await istemci.post(f"{P}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert y.status_code == 401 and _kod(y) == "anahtar_gerekli"


async def test_mcp_sdk_istemcisiyle_uyumlu(istemci, yonetici_basligi, uygulama, db_oturumu):
    """Resmî `mcp` SDK'sının istemcisi (Streamable HTTP) sunucumuzla konuşabiliyor."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    e = await _musteri(istemci, yonetici_basligi)
    p = await _proje(db_oturumu, e, "SDK projesi")
    ham, _ = await _anahtar(istemci, _b(e), M, kapsamlar=["projeler:oku", "gorevler:oku", "gorevler:yaz"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=uygulama), base_url="http://test",
                                 headers={"Authorization": f"Bearer {ham}"}, timeout=30) as hc:
        async with streamable_http_client("http://test/api/public/v1/mcp", http_client=hc) as (oku, yaz, _):
            async with ClientSession(oku, yaz) as oturum:
                bilgi = await oturum.initialize()
                assert bilgi.serverInfo.name == "mehmetkuru-dev"
                araclar = await oturum.list_tools()
                assert {"projeleri_listele", "gorev_olustur", "gorev_guncelle"} <= {a.name for a in araclar.tools}
                sonuc = await oturum.call_tool("projeleri_listele", {})
                assert not sonuc.isError and sonuc.structuredContent["veri"][0]["id"] == p.id
                sonuc = await oturum.call_tool("gorev_olustur", {"proje_id": p.id, "baslik": "Claude'dan görev"})
                assert not sonuc.isError and sonuc.structuredContent["baslik"] == "Claude'dan görev"
