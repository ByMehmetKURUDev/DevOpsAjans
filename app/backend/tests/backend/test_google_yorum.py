"""Faz 4K — Google yorum sayfası.

Google politikası ("review gating" yasak): puan sorulmuyor ve Google
bağlantısı HER ziyaretçiye, HER koşulda aynı — özel geri bildirim formu açık
ya da kapalı, sorgu parametresi ne olursa olsun, kim isterse istesin.

Kapsam: oluşturma (Place ID doğrulaması, slug), herkese açık yanıtta Google
adresi (4Q üreticisiyle aynı), puan alanı yokluğu; Google tıklaması ve
görüntülenme analitiği (bot sayılmaz); özel geri bildirim (bal küpü, form
jetonu, hız sınırı, bildirim: müşteriye `yorum_geri_bildirim`, ajans
sayfasında yöneticilere); müşteri izolasyonu, modül kapalıyken 403, sayfa
sınırı, pasif 410; logo yükleme; QR; eski slug yönlendirmesi; çöp kutusu.
"""

import json
import time
import uuid

import pytest
from sqlalchemy import select

from conftest import jeton_uret

Y = "/api/v1/yorum-sayfalari/yonetim"
M = "/api/v1/yorum-sayfalarim"
A = "/api/v1/yorum"
MODUL = "/api/v1/moduller"
PLACE_ID = "ChIJN1t_tDeuEmsRUsoyG83frY4"
MASAUSTU = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


def _e(on: str = "yorum") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@yorum.dev"


def _b(eposta: str, hesap: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {jeton_uret(eposta)}"}
    if hesap:
        h["X-MK-Hesap"] = hesap
    return h


def _kod(y) -> str:
    try:
        d = y.json().get("detail")
    except Exception:  # noqa: BLE001
        return ""
    return d.get("kod", "") if isinstance(d, dict) else ""


def _tarayici(ua: str = MASAUSTU, ip: str = "198.51.100.7") -> dict:
    return {"User-Agent": ua, "X-MK-Istemci-IP": ip}


@pytest.fixture(autouse=True)
def _temiz():
    from routers import google_yorum, kartvizit
    from services import hesap_ekibi

    kartvizit.hiz_sinirlarini_temizle()
    google_yorum.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    yield
    google_yorum.hiz_sinirlarini_temizle()


async def _modul_ac(istemci, yonetici_basligi, eposta, acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/google_yorum_sayfasi", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _musteri(istemci, yonetici_basligi, **ayarlar) -> str:
    e = _e()
    await _modul_ac(istemci, yonetici_basligi, e, **ayarlar)
    return e


async def _olustur(istemci, basliklar, yol=Y, **govde):
    govde.setdefault("isletme_adi", "Kafe Örnek")
    govde.setdefault("place_id", PLACE_ID)
    govde.setdefault("tesekkur", "Bizi tercih ettiğiniz için teşekkürler!")
    y = await istemci.post(yol, json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


def _jeton(sayfa_id: int, once: float = 10.0) -> str:
    from services import kartvizit as k

    return k.form_jetonu_uret("yorum", sayfa_id, an=time.time() - once)


async def _geri_bildirim(istemci, sayfa, ip="198.51.100.40", **govde):
    govde.setdefault("mesaj", "Kahve soğuktu.")
    govde.setdefault("form_jetonu", _jeton(sayfa["id"]))
    return await istemci.post(f"{A}/{sayfa['slug']}/geri-bildirim", content=json.dumps(govde),
                              headers={**_tarayici(ip=ip), "Content-Type": "text/plain"})


BEKLENEN_GOOGLE = f"https://search.google.com/local/writereview?placeid={PLACE_ID}"


async def test_google_baglantisi_her_kosulda_ayni_puan_yok(istemci, yonetici_basligi):
    from services import dinamik_qr as qr

    sayfa = await _olustur(istemci, yonetici_basligi)
    assert sayfa["google_adresi"] == BEKLENEN_GOOGLE == qr.google_yorum_adresi(PLACE_ID)
    # Farklı ziyaretçi, farklı sorgu parametresi (ör. puan) → aynı Google adresi.
    yanitlar = []
    for ek, ua in (("", MASAUSTU), ("?puan=1", MASAUSTU), ("?puan=5", "Mozilla/5.0 (iPhone)"), ("?memnun=hayir", MASAUSTU)):
        y = await istemci.get(f"{A}/{sayfa['slug']}{ek}", headers=_tarayici(ua))
        assert y.status_code == 200
        yanitlar.append(y.json())
    assert {d["google_adresi"] for d in yanitlar} == {BEKLENEN_GOOGLE}
    # Değişmez kodla da aynı.
    assert (await istemci.get(f"{A}/{sayfa['kod']}", headers=_tarayici())).json()["google_adresi"] == BEKLENEN_GOOGLE
    # Özel geri bildirim kapalıyken de Google bağlantısı aynen duruyor.
    await istemci.put(f"{Y}/{sayfa['id']}", json={"geri_bildirim_acik": False}, headers=yonetici_basligi)
    d = (await istemci.get(f"{A}/{sayfa['slug']}", headers=_tarayici())).json()
    assert d["google_adresi"] == BEKLENEN_GOOGLE and d["geri_bildirim"]["acik"] is False
    # Puan / derecelendirme alanı hiçbir yerde yok.
    for d in yanitlar:
        metin = json.dumps(d).lower()
        assert "puan" not in metin and "rating" not in metin and "yildiz" not in metin
    assert d["isletme_adi"] == "Kafe Örnek" and "hesap_email" not in d and "place_id" not in d


async def test_place_id_ve_alan_dogrulamasi(istemci, yonetici_basligi):
    for kotu in ("", "kisa", "javascript:alert(1)", "abc def ghi jkl", "x" * 600):
        y = await istemci.post(Y, json={"isletme_adi": "X", "place_id": kotu}, headers=yonetici_basligi)
        assert y.status_code == 400 and _kod(y) in ("zorunlu", "place_id_gecersiz"), kotu
    y = await istemci.post(Y, json={"isletme_adi": "", "place_id": PLACE_ID}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "zorunlu"
    y = await istemci.post(Y, json={"isletme_adi": "X", "place_id": PLACE_ID, "renk": "kirmizi"}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "renk_gecersiz"
    y = await istemci.post(Y, json={"isletme_adi": "X", "place_id": PLACE_ID, "dil": "fr"}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "dil_gecersiz"


async def test_analitik_google_tiklamasi_ve_bot(istemci, yonetici_basligi):
    sayfa = await _olustur(istemci, yonetici_basligi)
    s = sayfa["slug"]
    await istemci.get(f"{A}/{s}", headers=_tarayici(ip="198.51.100.11"))
    await istemci.get(f"{A}/{s}", headers=_tarayici(ip="198.51.100.12"))
    await istemci.get(f"{A}/{s}", headers=_tarayici("WhatsApp/2.23", ip="198.51.100.13"))
    for _ in range(2):
        y = await istemci.post(f"{A}/{s}/olay", content=json.dumps({"tur": "google"}),
                               headers={**_tarayici(ip="198.51.100.11"), "Content-Type": "text/plain"})
        assert y.status_code == 204
    assert (await istemci.post(f"{A}/{s}/olay", json={"tur": "puan"}, headers=_tarayici())).status_code == 400
    an = (await istemci.get(f"{Y}/{sayfa['id']}/analiz", headers=yonetici_basligi)).json()
    assert an["toplam"] == {"goruntulenme": 2, "google": 2, "geri_bildirim": 0}
    assert an["tekil"] == 2 and an["bot"] == 1
    liste = (await istemci.get(f"{Y}?ara={s}", headers=yonetici_basligi)).json()["items"]
    assert liste[0]["son30"] == {"goruntulenme": 2, "google": 2}


async def test_musteri_geri_bildirimi_panelde_ve_bildirim(istemci, yonetici_basligi, db_oturumu):
    from models.kartvizit import KartvizitMesajlari
    from models.notifications import Notifications

    e = await _musteri(istemci, yonetici_basligi)
    sayfa = await _olustur(istemci, _b(e), M, dil="ar")
    d = (await istemci.get(f"{A}/{sayfa['slug']}", headers=_tarayici())).json()
    assert d["geri_bildirim"]["aydinlatma_adresi"] == "/ar/gizlilik" and d["geri_bildirim"]["jeton"]
    mesaj = f"Servis yavaştı {uuid.uuid4().hex[:6]}"
    y = await _geri_bildirim(istemci, sayfa, mesaj=mesaj, eposta="ziyaretci@ornek.com")
    assert y.status_code == 200 and y.json() == {"ok": True}
    m = (await db_oturumu.execute(select(KartvizitMesajlari).where(KartvizitMesajlari.mesaj == mesaj))).scalar_one()
    assert m.sahip_tur == "yorum" and m.hesap_email == e and m.aydinlatma_at is not None and m.crm_aday_id is None
    liste = (await istemci.get(f"{M}/geri-bildirimler", headers=_b(e))).json()
    assert [x["mesaj"] for x in liste["items"]] == [mesaj] and liste["items"][0]["sahip_baslik"] == "Kafe Örnek"
    bildirim = (await db_oturumu.execute(select(Notifications).where(
        Notifications.recipient_email == e, Notifications.event_type == "yorum_geri_bildirim"))).scalars().all()
    assert bildirim and bildirim[0].link == "/client?sekme=kartvizit&alt=geri-bildirim"
    an = (await istemci.get(f"{M}/{sayfa['id']}/analiz", headers=_b(e))).json()
    assert an["toplam"]["geri_bildirim"] == 1
    # Başka müşteri göremez.
    e2 = await _musteri(istemci, yonetici_basligi)
    assert (await istemci.get(f"{M}/geri-bildirimler", headers=_b(e2))).json()["items"] == []
    mid = liste["items"][0]["id"]
    assert (await istemci.put(f"{M}/geri-bildirimler/{mid}", json={"okundu": True}, headers=_b(e2))).status_code == 404
    assert (await istemci.put(f"{M}/geri-bildirimler/{mid}", json={"okundu": True}, headers=_b(e))).json()["okundu"] is True


async def test_ajans_sayfasi_geri_bildirimi_yoneticiye(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications

    sayfa = await _olustur(istemci, yonetici_basligi)
    y = await _geri_bildirim(istemci, sayfa, mesaj="Ajans sayfası geri bildirimi")
    assert y.status_code == 200
    bildirim = (await db_oturumu.execute(select(Notifications).where(
        Notifications.event_type == "yorum_geri_bildirim", Notifications.ref_type == "kartvizit_mesaj",
        Notifications.recipient_email == "yonetici@test.dev"))).scalars().all()
    assert bildirim and bildirim[-1].link == "/admin?sekme=kartvizit&alt=geri-bildirim"
    liste = (await istemci.get(f"{Y}/geri-bildirimler?hesap=ajans&sayfa_id={sayfa['id']}", headers=yonetici_basligi)).json()
    assert [x["mesaj"] for x in liste["items"]] == ["Ajans sayfası geri bildirimi"]


async def test_geri_bildirim_bal_kupu_jeton_hiz_ve_kapali(istemci, yonetici_basligi, db_oturumu):
    from models.kartvizit import KartvizitMesajlari

    sayfa = await _olustur(istemci, yonetici_basligi)
    tuzak = f"bal-kupu-{uuid.uuid4().hex[:6]}"
    y = await _geri_bildirim(istemci, sayfa, mesaj=tuzak, web_sitesi="spam.example")
    assert y.status_code == 200
    assert (await db_oturumu.execute(select(KartvizitMesajlari).where(KartvizitMesajlari.mesaj == tuzak))).first() is None
    y = await _geri_bildirim(istemci, sayfa, ip="198.51.100.41", form_jetonu=_jeton(sayfa["id"], once=0))
    assert y.status_code == 429 and _kod(y) == "cok_hizli"
    y = await _geri_bildirim(istemci, sayfa, ip="198.51.100.42", form_jetonu="1.x")
    assert y.status_code == 400 and _kod(y) == "form_jetonu"
    y = await _geri_bildirim(istemci, sayfa, ip="198.51.100.43", mesaj="")
    assert y.status_code == 400 and _kod(y) == "zorunlu"
    kodlar = [(await _geri_bildirim(istemci, sayfa, ip="198.51.100.44")).status_code for _ in range(4)]
    assert kodlar == [200, 200, 200, 429]
    await istemci.put(f"{Y}/{sayfa['id']}", json={"geri_bildirim_acik": False}, headers=yonetici_basligi)
    y = await _geri_bildirim(istemci, sayfa, ip="198.51.100.45")
    assert y.status_code == 403 and _kod(y) == "form_kapali"


async def test_izolasyon_modul_kapali_sinir_ve_pasif(istemci, yonetici_basligi):
    e1 = await _musteri(istemci, yonetici_basligi, sayfa_siniri=1)
    e2 = await _musteri(istemci, yonetici_basligi)
    sayfa = await _olustur(istemci, _b(e1), M)
    y = await istemci.post(M, json={"isletme_adi": "İkinci", "place_id": PLACE_ID}, headers=_b(e1))
    assert y.status_code == 409 and _kod(y) == "sayfa_siniri"
    for metot, yol in (("GET", f"{M}/{sayfa['id']}"), ("PUT", f"{M}/{sayfa['id']}"), ("DELETE", f"{M}/{sayfa['id']}"),
                       ("GET", f"{M}/{sayfa['id']}/qr"), ("GET", f"{M}/{sayfa['id']}/analiz")):
        y = await istemci.request(metot, yol, json={"aktif": False} if metot == "PUT" else None, headers=_b(e2))
        assert y.status_code == 404, (metot, yol)
    assert (await istemci.get(M, headers=_b(e2))).json()["items"] == []
    y = await istemci.get(M, headers=_b(_e()))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    # Kartvizit modülü açık olmak yorum sayfası modülünü açmaz (ayrı satılıyor).
    kartci = _e()
    await istemci.put(f"{MODUL}/musteri/{kartci}/dijital_kartvizit", json={"acik": True}, headers=yonetici_basligi)
    y = await istemci.get(M, headers=_b(kartci))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    # Pasif sayfa ve modülü kapanan müşterinin sayfası 410.
    await istemci.put(f"{M}/{sayfa['id']}", json={"aktif": False}, headers=_b(e1))
    assert (await istemci.get(f"{A}/{sayfa['slug']}", headers=_tarayici())).status_code == 410
    await istemci.put(f"{M}/{sayfa['id']}", json={"aktif": True}, headers=_b(e1))
    assert (await istemci.get(f"{A}/{sayfa['slug']}", headers=_tarayici())).status_code == 200
    await _modul_ac(istemci, yonetici_basligi, e1, acik=False)
    assert (await istemci.get(f"{A}/{sayfa['slug']}", headers=_tarayici())).status_code == 410
    assert (await istemci.get(f"{A}/yok-{uuid.uuid4().hex[:5]}", headers=_tarayici())).status_code == 404


async def test_logo_qr_ve_eski_slug(istemci, yonetici_basligi):
    import io

    from PIL import Image

    sayfa = await _olustur(istemci, yonetici_basligi, slug=f"kafe-{uuid.uuid4().hex[:6]}", renk="#1e3a8a")
    t = io.BytesIO()
    Image.new("RGBA", (300, 300), (30, 60, 140, 255)).save(t, format="PNG")
    y = await istemci.post(f"{Y}/{sayfa['id']}/logo", files={"dosya": ("logo.png", t.getvalue(), "image/png")}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["logo"]["url"].endswith(".webp")
    q = await istemci.get(f"{Y}/{sayfa['id']}/qr?bicim=svg", headers=yonetici_basligi)
    assert q.status_code == 200 and q.text.startswith("<svg ") and "<image" in q.text and "#1e3a8a" in q.text
    assert "yorum-" in q.headers["content-disposition"]
    p = await istemci.get(f"{Y}/{sayfa['id']}/qr?bicim=png&boyut=1024", headers=yonetici_basligi)
    assert p.content.startswith(b"\x89PNG")
    assert sayfa["qr_adresi"] == f"https://mehmetkuru.dev/yorum/{sayfa['kod']}"
    yeni = f"yeni-kafe-{uuid.uuid4().hex[:6]}"
    y = await istemci.put(f"{Y}/{sayfa['id']}", json={"slug": yeni}, headers=yonetici_basligi)
    assert y.json()["slug"] == yeni
    assert (await istemci.get(f"{A}/{sayfa['slug']}", headers=_tarayici())).json() == {"durum": "yonlendir", "yonlendir": yeni}
    y = await istemci.delete(f"{Y}/{sayfa['id']}/logo", headers=yonetici_basligi)
    assert y.json()["logo"] is None
    # Silme çöp kutusuna; herkese açık 404.
    assert (await istemci.delete(f"{Y}/{sayfa['id']}", headers=yonetici_basligi)).json() == {"ok": True}
    assert (await istemci.get(f"{A}/{yeni}", headers=_tarayici())).status_code == 404


def test_yonetici_notu_ve_politika_metni_on_yuzde():
    """Yönetici ekranında Google kuralı notu 7 dilde var (ek paket)."""
    from pathlib import Path

    ek = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek" / "kartvizit"
    for dil in ("tr", "en", "de", "ru", "zh", "hi", "ar"):
        p = json.loads((ek / f"{dil}.json").read_text(encoding="utf-8"))["kartvizit"]
        assert p["yorum"]["politikaNotu"].strip(), dil
    tr = json.loads((ek / "tr.json").read_text(encoding="utf-8"))["kartvizit"]["yorum"]["politikaNotu"]
    assert "Google kuralları gereği tüm müşterilere aynı bağlantı gösterilir" in tr
