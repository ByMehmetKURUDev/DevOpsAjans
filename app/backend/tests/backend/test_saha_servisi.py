"""Faz 6S — Saha servisi.

Kapsam: durum akışı (geçersiz geçiş reddi, otomatik planlandı), atama çakışması (uyarı + pano),
teknisyen yalnız kendi işlerini görür/değiştirir, konum YALNIZ rıza varken ve YALNIZ başla/bitir
anında kaydedilir, rıza geri alma ve metin sürümü, konum indirgeme temizliği (90 gün), EXIF silme
(GPS'li test görseli), fotoğraf sınırı, imza + PDF (dosya imzası `%PDF-`), kontrol listesi zorunlu
madde doğrulaması, malzeme stok düşümü, servis müşterisinin imzalı sayfası (süre / başka iş / modül
kapalı), memnuniyet + Google bağlantısının her puanda aynı olması, bakım zamanı taraması (tek
bildirim), randevu → iş emri kancası, olay kataloğu (webhook + otomasyon), müşteri izolasyonu +
modül kapalıyken 403, ajans salt okunur görünümü, sınırlar, rapor, servis müşterisine e-posta.
"""

import base64
import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select, update

from conftest import jeton_uret

M = "/api/v1/saha-servisim"
Y = "/api/v1/saha/yonetim"
A = "/api/v1/saha/servis"
MODUL = "/api/v1/moduller"
UTC = timezone.utc


def _e(on: str = "saha") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@saha.dev"


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


def _iso(an: datetime) -> str:
    return an.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _yarin(saat: int = 9, dk: int = 0, gun: int = 1) -> datetime:
    """İstanbul saatiyle yarın `saat:dk` (UTC'ye çevrili)."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Istanbul")
    b = datetime.now(tz).date() + timedelta(days=gun)
    return datetime(b.year, b.month, b.day, saat, dk, tzinfo=tz).astimezone(UTC)


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    from routers import saha_servisi as r
    from services import hesap_ekibi
    from services import saha_kayit as sk
    from services import webhook

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    sk.kanca_onbellegi_temizle()
    sk._son_istek_temizligi["an"] = None
    monkeypatch.setattr(webhook, "ANLIK_TESLIMAT", False)
    yield
    r.hiz_sinirlarini_temizle()


@pytest.fixture
def epostalar(monkeypatch):
    from services import notify

    giden = []

    async def _sahte(alici, baslik, govde, ek=None):
        giden.append({"alici": alici, "konu": baslik, "govde": govde, "ek": ek or {}})
        return "sent", "test"

    monkeypatch.setattr(notify, "_eposta_gonder", _sahte)
    return giden


async def _modul(istemci, yonetici_basligi, hesap, anahtar="saha_servisi", acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{hesap}/{anahtar}", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _uye(db, hesap, uye, izinler, rol="uye"):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as he

    db.add(HesapUyeleri(hesap_email=hesap, uye_email=uye, rol=rol, izinler=json.dumps(izinler), durum="aktif", olusturma=he.simdi()))
    await db.commit()
    he.onbellegi_temizle()


async def _ok(y, kod=200):
    assert y.status_code == kod, y.text
    return y.json()


@pytest.fixture
async def firma(istemci, yonetici_basligi, db_oturumu):
    """Servis firması (modül açık) + iki teknisyen üye (yalnız `saha_teknisyen`) + bir sevk sorumlusu
    (`saha_yonetim`) + müşteri, adres, cihaz. Şablonlar ilk `meta`da tohumlanır."""
    sahip = _e("firma")
    await _modul(istemci, yonetici_basligi, sahip)
    tek_a, tek_b, sevk = _e("teka"), _e("tekb"), _e("sevk")
    await _uye(db_oturumu, sahip, tek_a, ["saha_teknisyen"])
    await _uye(db_oturumu, sahip, tek_b, ["saha_teknisyen"])
    await _uye(db_oturumu, sahip, sevk, ["saha_yonetim"])
    b = _b(sahip)
    meta = await _ok(await istemci.get(f"{M}/meta", headers=b))
    assert meta["yonetim"] is True
    ta = await _ok(await istemci.post(f"{M}/teknisyenler", json={"eposta": tek_a, "ad": "Ali Usta", "renk": "#22c55e"}, headers=b))
    tb = await _ok(await istemci.post(f"{M}/teknisyenler", json={"eposta": tek_b, "ad": "Berk Usta"}, headers=b))
    m = await _ok(await istemci.post(f"{M}/musteriler", json={
        "ad": "Ayşe Kaya", "eposta": _e("musteri"), "telefon": "0532 111 22 33", "tur": "bireysel",
        "lokasyon": {"ad": "Ev", "adres": "Bağdat Cad. 100 D:5", "ilce": "Kadıköy", "il": "İstanbul"}}, headers=b))
    c = await _ok(await istemci.post(f"{M}/musteriler/{m['id']}/cihazlar", json={
        "tur": "Klima", "marka": "Daikin", "model": "FTXM35", "seri_no": "SN-001", "kurulum_tarihi": "2024-05-01",
        "garanti_bitis": "2027-05-01", "bakim_periyot_ay": 6, "lokasyon_id": m["lokasyonlar"][0]["id"]}, headers=b))
    sablonlar = (await _ok(await istemci.get(f"{M}/sablonlar", headers=b)))["items"]
    return {"sahip": sahip, "b": b, "tek_a": tek_a, "tek_b": tek_b, "sevk": sevk, "ta": ta, "tb": tb, "m": m,
            "l": m["lokasyonlar"][0], "c": c, "sablonlar": {t["hazir"]: t for t in sablonlar}}


async def _is(istemci, f, **govde):
    govde.setdefault("musteri_id", f["m"]["id"])
    govde.setdefault("lokasyon_id", f["l"]["id"])
    govde.setdefault("baslik", "Klima soğutmuyor")
    govde.setdefault("tur", "ariza")
    return await _ok(await istemci.post(f"{M}/is-emirleri", json=govde, headers=f["b"]))


async def _planli_is(istemci, f, teknisyen="ta", bas=None, **govde):
    return await _is(istemci, f, plan_bas=_iso(bas or _yarin()), tahmini_dk=60, teknisyenler=[f[teknisyen]["id"]], **govde)


async def _durum(istemci, f, is_id, durum, kisi=None, **govde):
    basliklar = _b(kisi, f["sahip"]) if kisi else f["b"]
    return await istemci.post(f"{M}/is-emirleri/{is_id}/durum", json={"durum": durum, **govde}, headers=basliklar)


def _png(bos: bool = False) -> str:
    from PIL import Image, ImageDraw

    g = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
    if not bos:
        ImageDraw.Draw(g).line([(10, 100), (80, 20), (150, 90), (290, 15)], fill=(20, 20, 60, 255), width=4)
    b = io.BytesIO()
    g.save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def _gps_jpeg() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (640, 320), (200, 30, 30))
    exif = Image.Exif()
    exif[0x0112] = 6  # yön: 90° döndür
    exif[0x010F] = "GizliKamera"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (41.0, 0.0, 30.0), "E", (29.0, 1.0, 2.0)
    b = io.BytesIO()
    img.save(b, "JPEG", exif=exif.tobytes())
    veri = b.getvalue()
    assert b"GPS" in veri or b"Exif" in veri
    return veri


async def _gorsel(istemci, url: str):
    return await istemci.get(url)


# ---------------------------------------------------------------------------
# Modül kapısı, izolasyon, hazır şablonlar
# ---------------------------------------------------------------------------
async def test_modul_kapaliyken_403_oturumsuz_401(istemci, yonetici_basligi):
    hesap = _e("kapali")
    y = await istemci.get(f"{M}/meta", headers=_b(hesap))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    assert (await istemci.get(f"{M}/meta")).status_code == 401
    await _modul(istemci, yonetici_basligi, hesap)
    assert (await istemci.get(f"{M}/meta", headers=_b(hesap))).status_code == 200
    await _modul(istemci, yonetici_basligi, hesap, acik=False)
    y = await istemci.get(f"{M}/is-emirleri", headers=_b(hesap))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"


async def test_hazir_sablonlar_bir_kez_tohumlanir(istemci, firma):
    f = firma
    assert set(f["sablonlar"]) == {"klima_bakimi", "ofis_temizligi", "kombi_bakimi"}
    adlar = {t["ad"] for t in f["sablonlar"].values()}
    assert adlar == {"Klima bakımı", "Ofis temizliği", "Kombi bakımı"}
    klima = f["sablonlar"]["klima_bakimi"]
    assert klima["is_turu"] == "bakim" and any(m["tur"] == "olcum" and m.get("birim") == "bar" for m in klima["maddeler"])
    assert any(m["tur"] == "foto" and m["zorunlu"] for m in klima["maddeler"])
    # Silinen hazır şablon geri gelmez.
    await _ok(await istemci.delete(f"{M}/sablonlar/{f['sablonlar']['kombi_bakimi']['id']}", headers=f["b"]))
    await istemci.get(f"{M}/meta", headers=f["b"])
    kalan = (await _ok(await istemci.get(f"{M}/sablonlar", headers=f["b"])))["items"]
    assert len(kalan) == 2


async def test_musteri_izolasyonu(istemci, yonetici_basligi, firma):
    f = firma
    ie = await _is(istemci, f)
    baska = _e("baska")
    await _modul(istemci, yonetici_basligi, baska)
    bb = _b(baska)
    for yol in (f"{M}/is-emirleri/{ie['id']}", f"{M}/musteriler/{f['m']['id']}", f"{M}/cihazlar/{f['c']['id']}/gecmis",
                f"{M}/is-emirleri/{ie['id']}/pdf"):
        assert (await istemci.get(yol, headers=bb)).status_code == 404, yol
    assert (await _ok(await istemci.get(f"{M}/is-emirleri", headers=bb)))["items"] == []
    assert (await _ok(await istemci.get(f"{M}/musteriler", headers=bb)))["items"] == []
    # Başka hesabın müşterisiyle iş emri açılamaz.
    y = await istemci.post(f"{M}/is-emirleri", json={"musteri_id": f["m"]["id"], "baslik": "x"}, headers=bb)
    assert y.status_code == 404 and _kod(y) == "musteri_yok"
    # Başka hesabın teknisyeni atanamaz.
    m2 = await _ok(await istemci.post(f"{M}/musteriler", json={"ad": "Kendi müşterim"}, headers=bb))
    y = await istemci.post(f"{M}/is-emirleri", json={"musteri_id": m2["id"], "baslik": "x", "teknisyenler": [f["ta"]["id"]]}, headers=bb)
    assert y.status_code == 404 and _kod(y) == "teknisyen_yok"


async def test_ajans_salt_okunur_gorunum(istemci, yonetici_basligi, firma):
    f = firma
    ie = await _is(istemci, f)
    y = await istemci.get(f"{Y}/is-emirleri", headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "hesap_gerekli"
    liste = await _ok(await istemci.get(f"{Y}/is-emirleri?hesap={f['sahip']}", headers=yonetici_basligi))
    assert [x["id"] for x in liste["items"]] == [ie["id"]]
    ayr = await _ok(await istemci.get(f"{Y}/is-emirleri/{ie['id']}?hesap={f['sahip']}", headers=yonetici_basligi))
    assert ayr["no"] == ie["no"] and "musteri_baglantisi" not in ayr
    meta = await _ok(await istemci.get(f"{Y}/meta?hesap={f['sahip']}", headers=yonetici_basligi))
    assert meta["salt_okunur"] is True
    hesaplar = await _ok(await istemci.get(f"{Y}/hesaplar", headers=yonetici_basligi))
    assert any(h["hesap_email"] == f["sahip"] for h in hesaplar["items"])
    # Yazma ucu yok (salt okunur), müşteri jetonuyla yönetici uçlarına giriş yok.
    y = await istemci.post(f"{Y}/is-emirleri?hesap={f['sahip']}", json={"baslik": "x"}, headers=yonetici_basligi)
    assert y.status_code in (404, 405)
    assert (await istemci.get(f"{Y}/hesaplar", headers=f["b"])).status_code == 403


# ---------------------------------------------------------------------------
# Durum akışı
# ---------------------------------------------------------------------------
async def test_durum_akisi_ve_gecersiz_gecis_reddi(istemci, firma, epostalar):
    f = firma
    ie = await _is(istemci, f)
    assert ie["durum"] == "yeni" and ie["no"].startswith("IE-")
    # Yeni → işte: geçersiz; planla: plan/teknisyen yok.
    y = await _durum(istemci, f, ie["id"], "iste")
    assert y.status_code == 409 and _kod(y) == "gecersiz_gecis"
    y = await _durum(istemci, f, ie["id"], "planlandi")
    assert y.status_code == 409 and _kod(y) == "plan_gerekli"
    y = await _durum(istemci, f, ie["id"], "uydurma")
    assert y.status_code == 400
    # Plan + teknisyen → kendiliğinden planlandı.
    ie = await _ok(await istemci.put(f"{M}/is-emirleri/{ie['id']}", json={"plan_bas": _iso(_yarin(10)), "tahmini_dk": 90,
                                                                          "teknisyenler": [f["ta"]["id"]]}, headers=f["b"]))
    assert ie["durum"] == "planlandi" and ie["zaman"]["planlandi"]
    y = await _durum(istemci, f, ie["id"], "tamamlandi")
    assert y.status_code == 409 and _kod(y) == "gecersiz_gecis"
    for d in ("yolda", "iste", "tamamlandi"):
        ie = await _ok(await _durum(istemci, f, ie["id"], d))
        assert ie["durum"] == d
    assert ie["zaman"]["yolda"] and ie["zaman"]["basla"] and ie["zaman"]["bitir"]
    assert [g["yeni"] for g in ie["gecmis"]] == ["yeni", "planlandi", "yolda", "iste", "tamamlandi"]
    # Tamamlanan iş kapalı: hiçbir yere geçmez, düzenlenemez.
    for d in ("yeni", "iptal", "iste"):
        y = await _durum(istemci, f, ie["id"], d)
        assert y.status_code == 409 and _kod(y) == "gecersiz_gecis", d
    y = await istemci.put(f"{M}/is-emirleri/{ie['id']}", json={"baslik": "Değişti"}, headers=f["b"])
    assert y.status_code == 409 and _kod(y) == "is_kapali"
    # İptal → yeniden açılabilir (yeni); ertele sayacı.
    ie2 = await _planli_is(istemci, f)
    ie2 = await _ok(await _durum(istemci, f, ie2["id"], "ertelendi", neden="Parça bekleniyor"))
    assert ie2["ertele_sayisi"] == 1 and ie2["gecmis"][-1]["neden"] == "Parça bekleniyor"
    ie2 = await _ok(await _durum(istemci, f, ie2["id"], "iptal"))
    ie2 = await _ok(await _durum(istemci, f, ie2["id"], "yeni"))
    assert ie2["durum"] == "yeni"


async def test_atama_cakismasi_uyarisi_ve_pano(istemci, firma):
    f = firma
    bir = await _planli_is(istemci, f, bas=_yarin(9))
    assert bir["cakismalar"] == []
    iki = await _planli_is(istemci, f, bas=_yarin(9, 30), baslik="İkinci iş")
    assert [c["is_emri_id"] for c in iki["cakismalar"]] == [bir["id"]]
    # Başka teknisyene sürükle-bırak: çakışma yok.
    y = await _ok(await istemci.put(f"{M}/is-emirleri/{iki['id']}/plan",
                                    json={"teknisyen_id": f["tb"]["id"], "eski_teknisyen_id": f["ta"]["id"], "plan_bas": _iso(_yarin(9, 30))},
                                    headers=f["b"]))
    assert y["cakismalar"] == [] and [t["id"] for t in y["teknisyenler"]] == [f["tb"]["id"]]
    # Geri aynı teknisyene, örtüşmeyen saate: çakışma yok; örtüşen saate: uyarı (engellemez).
    y = await _ok(await istemci.put(f"{M}/is-emirleri/{iki['id']}/plan",
                                    json={"teknisyen_id": f["ta"]["id"], "eski_teknisyen_id": f["tb"]["id"], "plan_bas": _iso(_yarin(11))},
                                    headers=f["b"]))
    assert y["cakismalar"] == [] and y["plan_bit"] == _iso(_yarin(12))
    y = await _ok(await istemci.put(f"{M}/is-emirleri/{iki['id']}/plan", json={"plan_bas": _iso(_yarin(9, 45))}, headers=f["b"]))
    assert [c["is_emri_id"] for c in y["cakismalar"]] == [bir["id"]] and y["durum"] == "planlandi"
    pano = await _ok(await istemci.get(f"{M}/pano?gun={_yarin().astimezone(UTC).date().isoformat()}", headers=f["b"]))
    isler = {x["id"]: x for x in pano["isler"]}
    assert isler[bir["id"]]["cakisan"] == [iki["id"]] and isler[iki["id"]]["cakisan"] == [bir["id"]]
    assert [t["id"] for t in pano["teknisyenler"]] == [f["ta"]["id"], f["tb"]["id"]]
    # Atamayı kaldır → kuyruğa döner (durum yeni).
    y = await _ok(await istemci.put(f"{M}/is-emirleri/{iki['id']}/plan", json={"teknisyen_id": None}, headers=f["b"]))
    assert y["durum"] == "yeni" and y["teknisyenler"] == []
    pano = await _ok(await istemci.get(f"{M}/pano?gorunum=hafta", headers=f["b"]))
    assert iki["id"] in [x["id"] for x in pano["kuyruk"]] and pano["gorunum"] == "hafta"


# ---------------------------------------------------------------------------
# Teknisyen: yalnız kendi işleri
# ---------------------------------------------------------------------------
async def test_teknisyen_yalniz_kendi_islerini_gorur_ve_degistirir(istemci, firma):
    f = firma
    benim = await _planli_is(istemci, f, teknisyen="ta", bas=_yarin(0, 10, gun=0) + timedelta(hours=0))
    onun = await _planli_is(istemci, f, teknisyen="tb", baslik="Berk'in işi")
    ba = _b(f["tek_a"], f["sahip"])
    meta = await _ok(await istemci.get(f"{M}/meta", headers=ba))
    assert meta["yonetim"] is False and meta["teknisyen"] is True and meta["benim"]["id"] == f["ta"]["id"]
    islerim = await _ok(await istemci.get(f"{M}/islerim", headers=ba))
    gorunen = [x["id"] for x in islerim["bugun"] + islerim["diger"]]
    assert benim["id"] in gorunen and onun["id"] not in gorunen
    # Yönetim uçları kapalı.
    for metot, yol in (("GET", f"{M}/is-emirleri"), ("GET", f"{M}/pano"), ("GET", f"{M}/musteriler"), ("GET", f"{M}/raporlar"),
                       ("GET", f"{M}/sablonlar"), ("POST", f"{M}/is-emirleri"), ("PUT", f"{M}/is-emirleri/{benim['id']}")):
        y = await istemci.request(metot, yol, json={} if metot != "GET" else None, headers=ba)
        assert y.status_code == 403 and _kod(y) == "hesap_izni_yok", (metot, yol, y.text)
    # Başkasının işi: varlığı bile görünmez.
    for metot, yol, govde in (("GET", f"{M}/is-emirleri/{onun['id']}", None),
                              ("POST", f"{M}/is-emirleri/{onun['id']}/durum", {"durum": "yolda"}),
                              ("PUT", f"{M}/is-emirleri/{onun['id']}/kontrol", {"yanitlar": {}}),
                              ("GET", f"{M}/is-emirleri/{onun['id']}/pdf", None),
                              ("POST", f"{M}/is-emirleri/{onun['id']}/imza", {"ad": "x", "png": _png()})):
        y = await istemci.request(metot, yol, json=govde, headers=ba)
        assert y.status_code == 404, (metot, yol, y.text)
    # Kendi işi: görür, saha geçişlerini yapar; planlama/iptal yapamaz.
    ayr = await _ok(await istemci.get(f"{M}/is-emirleri/{benim['id']}", headers=ba))
    assert ayr["benim_isim"] is True and "konum" not in ayr and "musteri_baglantisi" not in ayr
    y = await _durum(istemci, f, benim["id"], "iptal", kisi=f["tek_a"])
    assert y.status_code == 403 and _kod(y) == "gecis_yetkisi_yok"
    assert (await _durum(istemci, f, benim["id"], "yolda", kisi=f["tek_a"])).status_code == 200
    # Atama kaldırılınca erişim de biter.
    await _ok(await istemci.put(f"{M}/is-emirleri/{benim['id']}", json={"teknisyenler": [f["tb"]["id"]]}, headers=f["b"]))
    assert (await istemci.get(f"{M}/is-emirleri/{benim['id']}", headers=ba)).status_code == 404
    # Sevk sorumlusu (yalnız saha_yonetim) her işi görür ama "İşlerim"i yok.
    bs = _b(f["sevk"], f["sahip"])
    assert len((await _ok(await istemci.get(f"{M}/is-emirleri", headers=bs)))["items"]) >= 2
    assert (await _ok(await istemci.get(f"{M}/islerim", headers=bs)))["kayitli"] is False


# ---------------------------------------------------------------------------
# KVKK: konum ve rıza
# ---------------------------------------------------------------------------
KONUM = {"enlem": 40.987654321, "boylam": 29.0361234, "dogruluk": 12.5}


async def _is_satiri(db, is_id):
    from models.saha_servisi import SahaIsEmirleri

    return (await db.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.id == is_id)
                             .execution_options(populate_existing=True))).scalars().one()


async def test_konum_yalniz_riza_varken_ve_basla_bitir_aninda(istemci, firma, db_oturumu):
    from services import saha_servisi as s

    f = firma
    ie = await _planli_is(istemci, f)
    ta = f["tek_a"]
    # Rıza yok: yola çık + başla konumlu gelir, hiçbir şey saklanmaz.
    assert (await _durum(istemci, f, ie["id"], "yolda", kisi=ta, konum=KONUM)).status_code == 200
    y = await _ok(await _durum(istemci, f, ie["id"], "iste", kisi=ta, konum=KONUM))
    assert y["konum_kaydedildi"] is False
    satir = await _is_satiri(db_oturumu, ie["id"])
    assert satir.basla_enlem is None and satir.basla_boylam is None
    # Yanlış metin sürümüyle rıza verilemez; doğru sürüm + açık onay.
    ba = _b(ta, f["sahip"])
    y = await istemci.post(f"{M}/rizam", json={"surum": "eski", "onay": True}, headers=ba)
    assert y.status_code == 400 and _kod(y) == "riza_surumu_gecersiz"
    y = await istemci.post(f"{M}/rizam", json={"surum": s.RIZA_SURUMU}, headers=ba)
    assert y.status_code == 400
    riza = await _ok(await istemci.post(f"{M}/rizam", json={"surum": s.RIZA_SURUMU, "onay": True}, headers=ba))
    assert riza["gecerli"] is True and riza["verildi_at"]
    # Bitir: rıza var → bitiş konumu kaydedilir (6 ondalık).
    y = await _ok(await _durum(istemci, f, ie["id"], "tamamlandi", kisi=ta, konum=KONUM))
    assert y["konum_kaydedildi"] is True and y["konum_alindi"] == {"basla": False, "bitir": True, "indirgendi_at": None}
    satir = await _is_satiri(db_oturumu, ie["id"])
    assert (satir.bitir_enlem, satir.bitir_boylam, satir.bitir_dogruluk) == (40.987654, 29.036123, 12.5)
    assert [g["konum_alindi"] for g in y["gecmis"]] == [False, False, False, False, True]
    # Rıza varken bile "yolda" anında konum alınmaz; işe atanmamış kişinin (sahip) konumu da alınmaz.
    ie2 = await _planli_is(istemci, f)
    y = await _ok(await _durum(istemci, f, ie2["id"], "yolda", kisi=ta, konum=KONUM))
    assert y["konum_kaydedildi"] is False
    y = await _ok(await _durum(istemci, f, ie2["id"], "iste", konum=KONUM))  # sahip (yönetim), atanmamış
    assert y["konum_kaydedildi"] is False
    satir = await _is_satiri(db_oturumu, ie2["id"])
    assert satir.basla_enlem is None and satir.bitir_enlem is None
    # Yönetim görünümü koordinatı görür; teknisyen görmez.
    ayr = await _ok(await istemci.get(f"{M}/is-emirleri/{ie['id']}", headers=f["b"]))
    assert ayr["konum"]["bitir"]["enlem"] == 40.987654 and ayr["konum"]["basla"] is None
    # Bozuk konum gövdesi sessizce yutulmaz.
    ie3 = await _planli_is(istemci, f)
    y = await _durum(istemci, f, ie3["id"], "iste", kisi=ta, konum={"enlem": 200, "boylam": 10})
    assert y.status_code == 400


async def test_riza_geri_alma_ve_metin_surumu(istemci, firma, db_oturumu, monkeypatch):
    from services import saha_servisi as s

    f = firma
    ba = _b(f["tek_a"], f["sahip"])
    await _ok(await istemci.post(f"{M}/rizam", json={"surum": s.RIZA_SURUMU, "onay": True}, headers=ba))
    geri = await _ok(await istemci.delete(f"{M}/rizam", headers=ba))
    assert geri["gecerli"] is False and geri["geri_alindi_at"]
    durum = await _ok(await istemci.get(f"{M}/rizam", headers=ba))
    assert durum["gecerli"] is False and durum["verildi_at"] and durum["geri_alindi_at"]
    # Geri alındıktan sonra konum alınmaz, iş yine yapılır.
    ie = await _planli_is(istemci, f)
    y = await _ok(await _durum(istemci, f, ie["id"], "iste", kisi=f["tek_a"], konum=KONUM))
    assert y["durum"] == "iste" and y["konum_kaydedildi"] is False
    # Yeniden rıza → geçerli; metin sürümü değişirse eski rıza geçersiz.
    await _ok(await istemci.post(f"{M}/rizam", json={"surum": s.RIZA_SURUMU, "onay": True}, headers=ba))
    assert (await _ok(await istemci.get(f"{M}/rizam", headers=ba)))["gecerli"] is True
    monkeypatch.setattr(s, "RIZA_SURUMU", "2099-01-01")
    assert (await _ok(await istemci.get(f"{M}/rizam", headers=ba)))["gecerli"] is False
    y = await _ok(await _durum(istemci, f, ie["id"], "tamamlandi", kisi=f["tek_a"], konum=KONUM))
    assert y["konum_kaydedildi"] is False
    # Rıza yalnız teknisyen kaydı olan kişinin.
    y = await istemci.post(f"{M}/rizam", json={"surum": s.RIZA_SURUMU, "onay": True}, headers=_b(f["sevk"], f["sahip"]))
    assert y.status_code == 409 and _kod(y) == "teknisyen_degil"


async def test_konum_indirgeme_temizligi(istemci, firma, db_oturumu):
    from models.saha_servisi import SahaIsEmirleri
    from services import saha_kayit as sk
    from services import saha_servisi as s

    f = firma
    eski = await _is(istemci, f)
    yeni = await _is(istemci, f)
    an = s.simdi()
    await db_oturumu.execute(update(SahaIsEmirleri).where(SahaIsEmirleri.id == eski["id"]).values(
        basla_at=an - timedelta(days=91), basla_enlem=41.0, basla_boylam=29.0, basla_dogruluk=5.0,
        bitir_at=an - timedelta(days=89), bitir_enlem=41.1, bitir_boylam=29.1, bitir_dogruluk=5.0))
    await db_oturumu.execute(update(SahaIsEmirleri).where(SahaIsEmirleri.id == yeni["id"]).values(
        basla_at=an - timedelta(days=10), basla_enlem=40.0, basla_boylam=28.0))
    await db_oturumu.commit()
    sayi = await sk.konum_indirge(db_oturumu)
    assert sayi >= 1
    e = await _is_satiri(db_oturumu, eski["id"])
    assert (e.basla_enlem, e.basla_boylam, e.basla_dogruluk) == (None, None, None) and e.konum_indirgendi_at is not None
    assert e.bitir_enlem == 41.1  # 89 gün: henüz değil
    y = await _is_satiri(db_oturumu, yeni["id"])
    assert y.basla_enlem == 40.0 and y.konum_indirgendi_at is None
    # 91. günde bitiş koordinatı da gider; adres (lokasyon) kalır.
    sayi = await sk.konum_indirge(db_oturumu, an + timedelta(days=2))
    e = await _is_satiri(db_oturumu, eski["id"])
    assert e.bitir_enlem is None and e.lokasyon_id == f["l"]["id"]
    # İstekle tetiklenen temizlik (uyuyan sunucu): liste ucu açılınca da çalışır.
    await db_oturumu.execute(update(SahaIsEmirleri).where(SahaIsEmirleri.id == yeni["id"]).values(basla_at=an - timedelta(days=100)))
    await db_oturumu.commit()
    await _ok(await istemci.get(f"{M}/is-emirleri", headers=f["b"]))
    assert (await _is_satiri(db_oturumu, yeni["id"])).basla_enlem is None


# ---------------------------------------------------------------------------
# Fotoğraf (EXIF), imza + PDF, kontrol listesi, malzeme
# ---------------------------------------------------------------------------
async def test_fotograf_exif_silinir_ve_sinir(istemci, firma, monkeypatch):
    from PIL import Image

    from services import saha_servisi as s

    f = firma
    ie = await _planli_is(istemci, f)
    ba = _b(f["tek_a"], f["sahip"])
    y = await istemci.post(f"{M}/is-emirleri/{ie['id']}/fotograflar", data={"tur": "once"},
                           files={"dosya": ("kamera.jpg", io.BytesIO(_gps_jpeg()), "image/jpeg")}, headers=ba)
    foto = await _ok(y)
    assert (foto["genislik"], foto["yukseklik"]) == (320, 640)  # EXIF yönü uygulandı
    for adres in (foto["url"], foto["kucuk_url"]):
        g = await _gorsel(istemci, adres)
        assert g.status_code == 200 and g.headers["content-type"] == "image/webp"
        assert b"Exif" not in g.content and b"GPS" not in g.content and b"GizliKamera" not in g.content
        img = Image.open(io.BytesIO(g.content))
        assert img.format == "WEBP" and dict(img.getexif()) == {} and "exif" not in img.info
    # İmzasız / süresi geçmiş / kurcalanmış görsel adresi açılmaz.
    anahtar = foto["url"].split("/gorsel/")[1].split("?")[0]
    assert (await istemci.get(f"/api/v1/saha/gorsel/{anahtar}")).status_code == 404
    assert (await istemci.get(foto["url"].replace("&i=", "&i=0"))).status_code == 404
    # Desteklenmeyen tür ve bozuk dosya.
    y = await istemci.post(f"{M}/is-emirleri/{ie['id']}/fotograflar", data={"tur": "once"},
                           files={"dosya": ("x.gif", io.BytesIO(b"GIF89a" + b"\x00" * 40), "image/gif")}, headers=ba)
    assert y.status_code in (400, 415)
    # İş emri başına sınır.
    monkeypatch.setattr(s, "FOTO_SINIRI", 2)
    await _ok(await istemci.post(f"{M}/is-emirleri/{ie['id']}/fotograflar", data={"tur": "sonra"},
                                 files={"dosya": ("a.jpg", io.BytesIO(_gps_jpeg()), "image/jpeg")}, headers=ba))
    y = await istemci.post(f"{M}/is-emirleri/{ie['id']}/fotograflar", data={"tur": "sonra"},
                           files={"dosya": ("b.jpg", io.BytesIO(_gps_jpeg()), "image/jpeg")}, headers=ba)
    assert y.status_code == 409 and _kod(y) == "foto_siniri"
    # Fotoğraf silinir.
    await _ok(await istemci.delete(f"{M}/is-emirleri/{ie['id']}/fotograflar/{foto['id']}", headers=ba))
    assert (await _gorsel(istemci, foto["url"])).status_code == 404


async def test_kontrol_listesi_zorunlu_madde_dogrulamasi(istemci, firma):
    f = firma
    ie = await _planli_is(istemci, f, tur="bakim", cihazlar=[f["c"]["id"]])
    # Bakım türünün varsayılan şablonu (Klima bakımı) kopyalandı.
    assert ie["sablon_id"] == f["sablonlar"]["klima_bakimi"]["id"] and len(ie["kontrol_listesi"]) == 8
    ta = f["tek_a"]
    ba = _b(ta, f["sahip"])
    await _ok(await _durum(istemci, f, ie["id"], "iste", kisi=ta))
    y = await _durum(istemci, f, ie["id"], "tamamlandi", kisi=ta)
    assert y.status_code == 409 and _kod(y) == "zorunlu_madde_eksik"
    assert set(y.json()["detail"]["maddeler"]) == {"filtre", "serpantin", "gaz", "foto"}
    # Tür doğrulaması: evet/hayır'a metin, ölçüme metin, bilinmeyen madde.
    for yanit in ({"filtre": "evet"}, {"gaz": "çok"}, {"yok_boyle": True}):
        y = await istemci.put(f"{M}/is-emirleri/{ie['id']}/kontrol", json={"yanitlar": yanit}, headers=ba)
        assert y.status_code in (400, 404), yanit
    k = await _ok(await istemci.put(f"{M}/is-emirleri/{ie['id']}/kontrol",
                                    json={"yanitlar": {"filtre": True, "serpantin": False, "gaz": "8,5", "not": "Filtre değişmeli"}}, headers=ba))
    assert k["kontrol_yanitlari"] == {"filtre": True, "serpantin": False, "gaz": 8.5, "not": "Filtre değişmeli"}
    y = await _durum(istemci, f, ie["id"], "tamamlandi", kisi=ta)
    assert y.status_code == 409 and y.json()["detail"]["maddeler"] == ["foto"]
    # Foto maddesi: genel "sonra" fotoğrafı yetmez, maddeye bağlı fotoğraf gerekir.
    await _ok(await istemci.post(f"{M}/is-emirleri/{ie['id']}/fotograflar", data={"tur": "sonra"},
                                 files={"dosya": ("s.jpg", io.BytesIO(_gps_jpeg()), "image/jpeg")}, headers=ba))
    assert (await _durum(istemci, f, ie["id"], "tamamlandi", kisi=ta)).status_code == 409
    y = await istemci.post(f"{M}/is-emirleri/{ie['id']}/fotograflar", data={"tur": "madde", "madde_id": "uydurma"},
                           files={"dosya": ("m.jpg", io.BytesIO(_gps_jpeg()), "image/jpeg")}, headers=ba)
    assert y.status_code == 404
    await _ok(await istemci.post(f"{M}/is-emirleri/{ie['id']}/fotograflar", data={"tur": "madde", "madde_id": "foto"},
                                 files={"dosya": ("m.jpg", io.BytesIO(_gps_jpeg()), "image/jpeg")}, headers=ba))
    son = await _ok(await _durum(istemci, f, ie["id"], "tamamlandi", kisi=ta))
    assert son["durum"] == "tamamlandi"
    # Bakım işi bitince cihazın son bakım tarihi bugün.
    from services import saha_servisi as s

    cihaz = (await _ok(await istemci.get(f"{M}/cihazlar/{f['c']['id']}/gecmis", headers=f["b"])))
    assert cihaz["cihaz"]["son_bakim"] == s.tr_bugun().isoformat() and cihaz["isler"][0]["id"] == ie["id"]


async def test_sablon_maddeleri_dogrulanir(istemci, firma):
    f = firma
    y = await istemci.post(f"{M}/sablonlar", json={"ad": "Bozuk", "maddeler": [{"metin": "x", "tur": "uydurma"}]}, headers=f["b"])
    assert y.status_code == 400
    t = await _ok(await istemci.post(f"{M}/sablonlar", json={"ad": "Kurulum listesi", "is_turu": "kurulum", "maddeler": [
        {"metin": "Montaj yüksekliği", "tur": "olcum", "birim": "cm", "zorunlu": True},
        {"metin": "Etiket yapıştırıldı", "tur": "evet_hayir"}]}, headers=f["b"]))
    assert [m["tur"] for m in t["maddeler"]] == ["olcum", "evet_hayir"] and t["maddeler"][0]["birim"] == "cm"
    ie = await _is(istemci, f, tur="kurulum")
    assert ie["sablon_id"] == t["id"]
    # Şablon sonradan değişse de iş emrindeki kopya değişmez.
    await _ok(await istemci.put(f"{M}/sablonlar/{t['id']}", json={"maddeler": []}, headers=f["b"]))
    assert len((await _ok(await istemci.get(f"{M}/is-emirleri/{ie['id']}", headers=f["b"])))["kontrol_listesi"]) == 2


async def test_imza_ve_servis_formu_pdf(istemci, firma, db_oturumu):
    from services.pdf_belge import pdf_metni

    f = firma
    await _ok(await istemci.put(f"{M}/ayarlar", json={"firma_adi": "Serin Klima Servis", "telefon": "0212 555 00 00",
                                                       "kdv_orani": 20, "imza_zorunlu": True}, headers=f["b"]))
    malzeme = await _ok(await istemci.post(f"{M}/malzemeler", json={"ad": "R32 gaz", "birim": "kg", "birim_fiyat": "450", "stok": 10},
                                           headers=f["b"]))
    ie = await _planli_is(istemci, f, cihazlar=[f["c"]["id"]], iscilik_ucreti="600")
    ta = f["tek_a"]
    ba = _b(ta, f["sahip"])
    # İşe başlamadan imza alınmaz.
    y = await istemci.post(f"{M}/is-emirleri/{ie['id']}/imza", json={"ad": "Ayşe Kaya", "png": _png()}, headers=ba)
    assert y.status_code == 409 and _kod(y) == "imza_zamani_degil"
    await _ok(await _durum(istemci, f, ie["id"], "iste", kisi=ta))
    await _ok(await istemci.post(f"{M}/is-emirleri/{ie['id']}/malzemeler", json={"malzeme_id": malzeme["id"], "miktar": "1,5"}, headers=ba))
    await _ok(await istemci.put(f"{M}/is-emirleri/{ie['id']}/saha", json={"teknisyen_notu": "Gaz eklendi, kaçak yok.", "iscilik_dk": 45},
                                headers=ba))
    # İmza zorunlu: imzasız bitmez.
    y = await _durum(istemci, f, ie["id"], "tamamlandi", kisi=ta)
    assert y.status_code == 409 and _kod(y) == "imza_gerekli"
    # Boş tuval ve bozuk görsel reddedilir.
    y = await istemci.post(f"{M}/is-emirleri/{ie['id']}/imza", json={"ad": "Ayşe Kaya", "png": _png(bos=True)}, headers=ba)
    assert y.status_code == 400 and _kod(y) == "imza_bos"
    y = await istemci.post(f"{M}/is-emirleri/{ie['id']}/imza", json={"ad": "Ayşe Kaya", "png": "data:image/png;base64,QUJD"}, headers=ba)
    assert y.status_code == 400
    imza = await _ok(await istemci.post(f"{M}/is-emirleri/{ie['id']}/imza", json={"ad": "Ayşe Kaya", "png": _png()}, headers=ba))
    assert imza["imza"]["ad"] == "Ayşe Kaya" and imza["imza"]["at"]
    g = await _gorsel(istemci, imza["imza"]["url"])
    assert g.status_code == 200 and g.content.startswith(b"\x89PNG")
    son = await _ok(await _durum(istemci, f, ie["id"], "tamamlandi", kisi=ta))
    assert son["imza"]["ad"] == "Ayşe Kaya"
    # Tamamlanmış ve imzalı işe ikinci imza yok.
    y = await istemci.post(f"{M}/is-emirleri/{ie['id']}/imza", json={"ad": "Başka", "png": _png()}, headers=ba)
    assert y.status_code == 409 and _kod(y) == "zaten_imzali"
    # PDF: dosya imzası, Türkçe metin, firma künyesi, kalemler, imzalayan.
    y = await istemci.get(f"{M}/is-emirleri/{ie['id']}/pdf", headers=ba)
    assert y.status_code == 200 and y.headers["content-type"] == "application/pdf" and y.content.startswith(b"%PDF-")
    assert "servis-formu-IE-" in y.headers["content-disposition"]
    metin = pdf_metni(y.content)
    for parca in ("SERVİS FORMU", ie["no"], "Serin Klima Servis", "Ayşe Kaya", "R32 gaz", "İşçilik", "Gaz eklendi", "Daikin",
                  "Ali Usta", "e-Fatura"):
        assert parca in metin, parca
    # 1,5 kg × 450 = 675 + işçilik 600 = 1.275; KDV %20 = 255; toplam 1.530.
    assert "1.275,00" in metin and "1.530,00" in metin
    # İngilizce form.
    y = await istemci.get(f"{M}/is-emirleri/{ie['id']}/pdf?dil=en", headers=f["b"])
    assert "SERVICE REPORT" in pdf_metni(y.content)


async def test_malzeme_stok_dusumu(istemci, firma):
    f = firma
    m = await _ok(await istemci.post(f"{M}/malzemeler", json={"ad": "Bakır boru", "birim": "m", "birim_fiyat": "120,50", "stok": 10,
                                                                "kritik_stok": 7}, headers=f["b"]))
    assert m["birim_fiyat"] == 12050 and m["stok"] == 10 and m["kritik"] is False
    ie = await _planli_is(istemci, f)
    ba = _b(f["tek_a"], f["sahip"])
    # Teknisyen kataloğu okur (yalnız aktifler), değiştiremez.
    assert any(x["id"] == m["id"] for x in (await _ok(await istemci.get(f"{M}/malzemeler", headers=ba)))["items"])
    assert (await istemci.post(f"{M}/malzemeler", json={"ad": "x"}, headers=ba)).status_code == 403
    k = await _ok(await istemci.post(f"{M}/is-emirleri/{ie['id']}/malzemeler", json={"malzeme_id": m["id"], "miktar": 3}, headers=ba))
    assert k["tutar"] == 36150
    liste = {x["id"]: x for x in (await _ok(await istemci.get(f"{M}/malzemeler", headers=f["b"])))["items"]}
    assert liste[m["id"]]["stok"] == 7 and liste[m["id"]]["kritik"] is True
    serbest = await _ok(await istemci.post(f"{M}/is-emirleri/{ie['id']}/malzemeler",
                                           json={"ad": "Kelepçe", "birim": "adet", "miktar": 2, "birim_fiyat": "15"}, headers=ba))
    assert serbest["malzeme_id"] is None and serbest["tutar"] == 3000
    await _ok(await istemci.delete(f"{M}/is-emirleri/{ie['id']}/malzemeler/{k['id']}", headers=ba))
    liste = {x["id"]: x for x in (await _ok(await istemci.get(f"{M}/malzemeler", headers=f["b"])))["items"]}
    assert liste[m["id"]]["stok"] == 10
    y = await istemci.post(f"{M}/is-emirleri/{ie['id']}/malzemeler", json={"malzeme_id": m["id"], "miktar": 0}, headers=ba)
    assert y.status_code == 400
    # Kapalı işe malzeme eklenmez.
    await _ok(await _durum(istemci, f, ie["id"], "iptal"))
    y = await istemci.post(f"{M}/is-emirleri/{ie['id']}/malzemeler", json={"malzeme_id": m["id"], "miktar": 1}, headers=f["b"])
    assert y.status_code == 409 and _kod(y) == "is_kapali"


# ---------------------------------------------------------------------------
# Servis müşterisinin imzalı sayfası, memnuniyet, Google bağlantısı
# ---------------------------------------------------------------------------
async def _tamamla(istemci, f, ie):
    await _ok(await _durum(istemci, f, ie["id"], "iste"))
    return await _ok(await _durum(istemci, f, ie["id"], "tamamlandi"))


def _jeton(ie):
    return ie["musteri_baglantisi"].rsplit("/servis/", 1)[1]


async def test_servis_musterisi_imzali_sayfasi(istemci, yonetici_basligi, firma, db_oturumu):
    from models.saha_servisi import SahaIsEmirleri
    from services import saha_servisi as s

    f = firma
    ie = await _planli_is(istemci, f)
    jeton = _jeton(ie)
    sayfa = await _ok(await istemci.get(f"{A}/{jeton}"))
    assert sayfa["is"]["no"] == ie["no"] and sayfa["is"]["durum"] == "planlandi" and sayfa["pdf_var"] is False
    assert sayfa["is"]["teknisyenler"] == ["Ali"]  # yalnız ilk ad
    assert sayfa["aydinlatma"]["saklama_ay"] == 60 and sayfa["musteri_ad"] == "Ayşe Kaya"
    y = await istemci.get(f"{A}/{jeton}")
    assert "noindex" in y.headers["x-robots-tag"] and y.headers["cache-control"] == "no-store"
    assert (await istemci.get(f"{A}/{jeton}/pdf")).status_code == 409
    # Başka işin kimliğiyle aynı imza → geçersiz; kurcalanmış imza → geçersiz.
    diger = await _planli_is(istemci, f)
    sahte = f"{diger['id']}-{jeton.split('-', 1)[1]}"
    assert (await istemci.get(f"{A}/{sahte}")).status_code == 404
    assert (await istemci.get(f"{A}/{jeton[:-1]}{'a' if jeton[-1] != 'a' else 'b'}")).status_code == 404
    assert (await istemci.get(f"{A}/x")).status_code == 404
    # Tamamlanınca PDF iner.
    await _tamamla(istemci, f, ie)
    y = await istemci.get(f"{A}/{jeton}/pdf")
    assert y.status_code == 200 and y.content.startswith(b"%PDF-")
    # Süre: kapanıştan 60 gün sonra bağlantı biter.
    await db_oturumu.execute(update(SahaIsEmirleri).where(SahaIsEmirleri.id == ie["id"]).values(
        bitir_at=s.simdi() - timedelta(days=61)))
    await db_oturumu.commit()
    y = await istemci.get(f"{A}/{jeton}")
    assert y.status_code == 410 and _kod(y) == "baglanti_suresi_doldu"
    # Modül kapanırsa sayfa da kapanır.
    j2 = _jeton(diger)
    await _modul(istemci, yonetici_basligi, f["sahip"], acik=False)
    assert (await istemci.get(f"{A}/{j2}")).status_code == 410
    await _modul(istemci, yonetici_basligi, f["sahip"])
    assert (await istemci.get(f"{A}/{j2}")).status_code == 200


async def test_memnuniyet_ve_google_baglantisi_her_durumda_ayni(istemci, yonetici_basligi, firma, db_oturumu):
    from models.kartvizit import YorumSayfalari

    f = firma
    bir, iki = await _planli_is(istemci, f), await _planli_is(istemci, f)
    # Google yorum modülü kapalı: bağlantı yok.
    j1, j2 = _jeton(bir), _jeton(iki)
    assert (await _ok(await istemci.get(f"{A}/{j1}")))["google_yorum_url"] is None
    await _modul(istemci, yonetici_basligi, f["sahip"], anahtar="google_yorum_sayfasi")
    db_oturumu.add(YorumSayfalari(hesap_email=f["sahip"], kod="Y" + uuid.uuid4().hex[:6], slug="serin-" + uuid.uuid4().hex[:8],
                                  isletme_adi="Serin Klima", place_id="ChIJsaha123"))
    await db_oturumu.commit()
    beklenen = "https://search.google.com/local/writereview?placeid=ChIJsaha123"
    # Tamamlanmadan puan verilemez.
    y = await istemci.post(f"{A}/{j1}/memnuniyet", json={"puan": 5})
    assert y.status_code == 409 and _kod(y) == "puanlanamaz"
    await _tamamla(istemci, f, bir)
    await _tamamla(istemci, f, iki)
    once = await _ok(await istemci.get(f"{A}/{j1}"))
    assert once["google_yorum_url"] == beklenen and once["memnuniyet"]["acik"] is True
    dusuk = await _ok(await istemci.post(f"{A}/{j1}/memnuniyet", json={"puan": 1, "yorum": "Geç geldiler"}))
    yuksek = await _ok(await istemci.post(f"{A}/{j2}/memnuniyet", json={"puan": 5}))
    # Review gating YOK: 1 yıldız da 5 yıldız da aynı bağlantıyı görür.
    assert dusuk["google_yorum_url"] == yuksek["google_yorum_url"] == beklenen
    assert dusuk["memnuniyet"]["puan"] == 1 and dusuk["memnuniyet"]["yorum"] == "Geç geldiler"
    y = await istemci.post(f"{A}/{j1}/memnuniyet", json={"puan": 5})
    assert y.status_code == 409 and _kod(y) == "zaten_puanlandi"
    y = await istemci.post(f"{A}/{_jeton(await _planli_is(istemci, f))}/memnuniyet", json={"puan": 9})
    assert y.status_code == 409  # tamamlanmamış (puan aralığından önce)
    ayr = await _ok(await istemci.get(f"{M}/is-emirleri/{bir['id']}", headers=f["b"]))
    assert ayr["memnuniyet"]["puan"] == 1


# ---------------------------------------------------------------------------
# Bildirimler: servis müşterisi e-postası, teknisyen ataması, bakım taraması
# ---------------------------------------------------------------------------
async def test_servis_musterisine_eposta_ve_teknisyene_atama_bildirimi(istemci, firma, epostalar, db_oturumu):
    from models.notifications import Notifications

    f = firma
    await _ok(await istemci.put(f"{M}/ayarlar", json={"firma_adi": "Serin Klima Servis", "eposta": "info@serin.dev"}, headers=f["b"]))
    musteri = f["m"]["eposta"]
    ie = await _planli_is(istemci, f)
    planli = [e for e in epostalar if e["alici"] == musteri]
    assert len(planli) == 1 and "planlandı" in planli[0]["konu"] and "/servis/" in planli[0]["govde"]
    assert planli[0]["ek"].get("reply_to") == "info@serin.dev"
    # Teknisyene yeni iş bildirimi (panel + e-posta), bağlantı doğru hesaba.
    tek = (await db_oturumu.execute(select(Notifications).where(Notifications.recipient_email == f["tek_a"],
                                                                Notifications.event_type == "saha_is_atandi"))).scalars().all()
    assert tek and ie["no"] in tek[0].title and "hesap=" in (tek[0].link or "") and f"is={ie['id']}" in tek[0].link
    await _ok(await _durum(istemci, f, ie["id"], "yolda"))
    await _tamamla(istemci, f, ie)
    konular = [e["konu"] for e in epostalar if e["alici"] == musteri]
    assert len(konular) == 3 and "yola çıktı" in konular[1] and "tamamlandı" in konular[2]
    # Servis müşterisi panel kullanıcısı değil: panel içi kopya yok, jeton kalıcı kayıtta maskeli.
    satirlar = (await db_oturumu.execute(select(Notifications).where(Notifications.recipient_email == musteri))).scalars().all()
    assert satirlar and all(s.channel == "email" for s in satirlar)
    jeton = _jeton(ie)
    assert all(jeton not in (s.body or "") for s in satirlar)
    # Aynı plan için ikinci "planlandı" e-postası gitmez; plan değişince gider.
    ie2 = await _planli_is(istemci, f)
    sayi = len(epostalar)
    await _ok(await istemci.put(f"{M}/is-emirleri/{ie2['id']}", json={"baslik": "Yeni başlık"}, headers=f["b"]))
    assert len(epostalar) == sayi
    await _ok(await istemci.put(f"{M}/is-emirleri/{ie2['id']}", json={"plan_bas": _iso(_yarin(15))}, headers=f["b"]))
    assert len(epostalar) == sayi + 1
    # Müşterinin dili: Almanca.
    m2 = await _ok(await istemci.post(f"{M}/musteriler", json={"ad": "Hans", "eposta": _e("de"), "dil": "de"}, headers=f["b"]))
    await _ok(await istemci.post(f"{M}/is-emirleri", json={"musteri_id": m2["id"], "baslik": "Wartung", "plan_bas": _iso(_yarin(16)),
                                                           "teknisyenler": [f["tb"]["id"]]}, headers=f["b"]))
    assert "Servicetermin" in [e for e in epostalar if e["alici"] == m2["eposta"]][0]["konu"]
    # Ayar kapalıysa gitmez.
    await _ok(await istemci.put(f"{M}/ayarlar", json={"bildirim_yolda": False}, headers=f["b"]))
    ie3 = await _planli_is(istemci, f)
    sayi = len(epostalar)
    await _ok(await _durum(istemci, f, ie3["id"], "yolda"))
    assert len(epostalar) == sayi


async def test_bakim_taramasi_tek_bildirim(istemci, firma, db_oturumu):
    from models.notifications import Notifications
    from models.saha_servisi import SahaCihazlari
    from services import saha_kayit as sk
    from services import saha_servisi as s

    f = firma
    bugun = s.tr_bugun()
    await _ok(await istemci.put(f"{M}/cihazlar/{f['c']['id']}", json={"son_bakim": s.ay_ekle(bugun, -6).isoformat()}, headers=f["b"]))
    yakin = await _ok(await istemci.post(f"{M}/musteriler/{f['m']['id']}/cihazlar", json={
        "tur": "Kombi", "marka": "Vaillant", "son_bakim": (s.ay_ekle(bugun, -12) + timedelta(days=3)).isoformat(),
        "bakim_periyot_ay": 12}, headers=f["b"]))
    uzak = await _ok(await istemci.post(f"{M}/musteriler/{f['m']['id']}/cihazlar", json={
        "tur": "Klima", "son_bakim": bugun.isoformat(), "bakim_periyot_ay": 6}, headers=f["b"]))
    liste = (await _ok(await istemci.get(f"{M}/bakim?gun=30", headers=f["b"])))["items"]
    assert {x["cihaz_id"] for x in liste} == {f["c"]["id"], yakin["id"]}

    async def bildirimler():
        return (await db_oturumu.execute(select(Notifications).where(
            Notifications.recipient_email == f["sahip"], Notifications.event_type == "saha_bakim_zamani",
            Notifications.channel == "inapp"))).scalars().all()

    await sk.bakim_taramasi(db_oturumu)
    ilk = await bildirimler()
    assert len(ilk) == 1 and "2" in ilk[0].title
    await sk.bakim_taramasi(db_oturumu)
    await sk.bakim_taramasi(db_oturumu, bugun + timedelta(days=1))
    assert len(await bildirimler()) == 1
    satir = (await db_oturumu.execute(select(SahaCihazlari).where(SahaCihazlari.id == uzak["id"]))).scalars().one()
    assert satir.bakim_bildirim_tarihi is None
    # Sevk sorumlusu (saha_yonetim) de alır (ekip genişletmesi).
    sevk = (await db_oturumu.execute(select(Notifications).where(Notifications.recipient_email == f["sevk"],
                                                                 Notifications.event_type == "saha_bakim_zamani"))).scalars().all()
    assert sevk
    # "Bakım iş emri oluştur": açık bakım işi varken ikincisi açılmaz.
    ie = await _ok(await istemci.post(f"{M}/cihazlar/{yakin['id']}/bakim-is-emri", json={}, headers=f["b"]))
    assert ie["tur"] == "bakim" and [c["id"] for c in ie["cihazlar"]] == [yakin["id"]]
    y = await istemci.post(f"{M}/cihazlar/{yakin['id']}/bakim-is-emri", json={}, headers=f["b"])
    assert y.status_code == 409 and _kod(y) == "acik_bakim_var"


# ---------------------------------------------------------------------------
# Randevu → iş emri kancası, olaylar, sınırlar, rapor
# ---------------------------------------------------------------------------
async def test_randevu_is_emri_kancasi(istemci, yonetici_basligi, firma, db_oturumu):
    from models.randevu import Randevular, RandevuKisileri, RandevuSayfalari, RandevuTurleri
    from models.saha_servisi import SahaIsEmirleri, SahaMusterileri
    from services import saha_kayit as sk

    f = firma
    await _modul(istemci, yonetici_basligi, f["sahip"], anahtar="randevu")

    async def randevu(eposta):
        sayfa = RandevuSayfalari(hesap_email=f["sahip"], slug=f"servis-{uuid.uuid4().hex[:8]}", baslik="Servis randevusu")
        db_oturumu.add(sayfa)
        await db_oturumu.flush()
        kisi = RandevuKisileri(sayfa_id=sayfa.id, eposta=f["tek_a"], ad="Ali Usta", haftalik="{}")
        tur = RandevuTurleri(sayfa_id=sayfa.id, slug="kesif", ad="Ücretsiz keşif",
                             sorular=json.dumps([{"id": "adres", "etiket": "Adres", "tur": "metin"}]))
        db_oturumu.add_all([kisi, tur])
        await db_oturumu.flush()
        bas = _yarin(14)
        r = Randevular(uid=uuid.uuid4().hex, sayfa_id=sayfa.id, tur_id=tur.id, kisi_id=kisi.id, hesap_email=f["sahip"],
                       baslangic=bas, bitis=bas + timedelta(minutes=45), dolu_bas=bas, dolu_bit=bas + timedelta(minutes=45),
                       koltuk=0, ad="Can Demir", eposta=eposta, telefon="+905551112233",
                       yanitlar=json.dumps({"adres": "Moda Cad. 5"}), dil="tr")
        db_oturumu.add(r)
        await db_oturumu.commit()
        await sk.kanca_bitmesini_bekle()
        return r

    # Kanca kapalı: iş emri açılmaz.
    r0 = await randevu(_e("kapali"))
    assert (await db_oturumu.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.randevu_id == r0.id))).scalars().first() is None
    await _ok(await istemci.put(f"{M}/ayarlar", json={"randevu_kancasi": True, "randevu_is_turu": "kesif"}, headers=f["b"]))
    # Ayar ekranı dış bağımlılıkları bilir (kapalıysa ilgili anahtar devre dışı + açıklama).
    ayar = await _ok(await istemci.get(f"{M}/ayarlar", headers=f["b"]))
    assert ayar["randevu_modulu"] is True and isinstance(ayar["eposta_kanali"], bool) and ayar["yorum_modulu"] is False
    eposta = _e("randevulu")
    r = await randevu(eposta)
    ie = (await db_oturumu.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.randevu_id == r.id)
                                   .execution_options(populate_existing=True))).scalars().first()
    assert ie is not None and ie.tur == "kesif" and ie.durum == "planlandi" and "Adres: Moda Cad. 5" in ie.aciklama
    m = (await db_oturumu.execute(select(SahaMusterileri).where(SahaMusterileri.id == ie.musteri_id))).scalars().one()
    assert m.eposta == eposta and m.ad == "Can Demir" and m.hesap_email == f["sahip"]
    ayr = await _ok(await istemci.get(f"{M}/is-emirleri/{ie.id}", headers=f["b"]))
    assert [t["id"] for t in ayr["teknisyenler"]] == [f["ta"]["id"]] and ayr["randevu_id"] == r.id
    # Aynı randevu ikinci iş emri açmaz.
    assert await sk.randevudan_is_emri(db_oturumu, r.id) == ie.id
    # Randevu modülü kapalıysa kanca çalışmaz.
    await _modul(istemci, yonetici_basligi, f["sahip"], anahtar="randevu", acik=False)
    assert (await _ok(await istemci.get(f"{M}/ayarlar", headers=f["b"])))["randevu_modulu"] is False
    r2 = await randevu(_e("modulsuz"))
    assert (await db_oturumu.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.randevu_id == r2.id))).scalars().first() is None


async def test_olay_katalogu_webhook_ve_otomasyon(istemci, firma, db_oturumu):
    from models.api_erisimi import WebhookTeslimatlari, WebhookUcNoktalari
    from services import otomasyon_kural, webhook

    assert {"is_emri.olusturuldu", "is_emri.tamamlandi"} <= set(webhook.OLAY_SOZLUGU)
    assert {"is_emri.olusturuldu", "is_emri.tamamlandi"} <= set(otomasyon_kural.OLAY_SOZLUGU)
    assert {o["anahtar"] for o in webhook.olay_katalogu(False)} >= {"is_emri.olusturuldu", "is_emri.tamamlandi"}
    assert "is_emri.musteri_eposta" in {a["yol"] for a in otomasyon_kural.sema("is_emri.tamamlandi", False)}
    f = firma
    uc = WebhookUcNoktalari(sahip_tur="musteri", hesap_email=f["sahip"], url="https://kanca.ornek.com/saha",
                            olaylar=json.dumps(["is_emri.olusturuldu", "is_emri.tamamlandi"]), aktif=True,
                            gizli_anahtar="d1:whsec_saha", ardisik_hata=0)
    db_oturumu.add(uc)
    await db_oturumu.commit()
    webhook.onbellegi_temizle()
    try:
        ie = await _planli_is(istemci, f)
        await _tamamla(istemci, f, ie)
        satirlar = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id)
                                             .order_by(WebhookTeslimatlari.id))).scalars().all()
        assert [t.tur for t in satirlar] == ["is_emri.olusturuldu", "is_emri.tamamlandi"]
        govde = json.loads(satirlar[1].govde)
        assert govde["hesap"] == f["sahip"] and govde["veri"]["is_emri_id"] == ie["id"] and govde["veri"]["durum"] == "tamamlandi"
        # Kişisel veri (müşteri adı/e-posta/adres, konum) olay gövdesinde yok.
        assert "Ayşe" not in satirlar[1].govde and "Bağdat" not in satirlar[1].govde and "enlem" not in satirlar[1].govde
        # Otomasyon bağlamı: olaydaki kişi servis müşterisi.
        from services import otomasyon

        b = await otomasyon.baglam_kur(db_oturumu, "is_emri.tamamlandi", {"is_emri_id": ie["id"]}, f["sahip"], False)
        assert b["is_emri"]["no"] == ie["no"] and b["kisi"]["email"] == f["m"]["eposta"] and b["is_emri"]["teknisyen"] == "Ali Usta"
    finally:
        await db_oturumu.execute(update(WebhookUcNoktalari).where(WebhookUcNoktalari.id == uc.id).values(aktif=False))
        await db_oturumu.execute(delete(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id))
        await db_oturumu.commit()
        webhook.onbellegi_temizle()


async def test_sinirlar_teknisyen_ve_aylik_is_emri(istemci, yonetici_basligi, firma, db_oturumu):
    f = firma
    await _modul(istemci, yonetici_basligi, f["sahip"], teknisyen_siniri=2, aylik_is_emri_siniri=2)
    yeni = _e("tekc")
    await _uye(db_oturumu, f["sahip"], yeni, ["saha_teknisyen"])
    y = await istemci.post(f"{M}/teknisyenler", json={"eposta": yeni}, headers=f["b"])
    assert y.status_code == 409 and _kod(y) == "teknisyen_siniri"
    # Ekip üyesi olmayan biri teknisyen yapılamaz.
    await _modul(istemci, yonetici_basligi, f["sahip"], teknisyen_siniri=10, aylik_is_emri_siniri=2)
    y = await istemci.post(f"{M}/teknisyenler", json={"eposta": _e("yabanci")}, headers=f["b"])
    assert y.status_code == 409 and _kod(y) == "ekip_uyesi_degil"
    await _ok(await istemci.post(f"{M}/teknisyenler", json={"eposta": f["sahip"], "ad": "Patron"}, headers=f["b"]))
    await _is(istemci, f)
    await _is(istemci, f)
    y = await istemci.post(f"{M}/is-emirleri", json={"musteri_id": f["m"]["id"], "baslik": "Üçüncü"}, headers=f["b"])
    assert y.status_code == 409 and _kod(y) == "aylik_sinir"
    meta = await _ok(await istemci.get(f"{M}/meta", headers=f["b"]))
    assert meta["bu_ay_is_emri"] == 2 and meta["aylik_is_emri_siniri"] == 2


async def test_rapor_teknisyen_basina(istemci, firma):
    from services import saha_servisi as s

    f = firma
    bir = await _planli_is(istemci, f)
    await _tamamla(istemci, f, bir)
    iki = await _planli_is(istemci, f)
    await _ok(await _durum(istemci, f, iki["id"], "iste"))
    await _ok(await _durum(istemci, f, iki["id"], "ertelendi"))
    await _ok(await istemci.put(f"{M}/is-emirleri/{iki['id']}", json={"plan_bas": _iso(_yarin(16))}, headers=f["b"]))
    await _tamamla(istemci, f, iki)
    await _ok(await istemci.post(f"{A}/{_jeton(bir)}/memnuniyet", json={"puan": 4}))
    await _ok(await istemci.post(f"{A}/{_jeton(iki)}/memnuniyet", json={"puan": 2}))
    r = await _ok(await istemci.get(f"{M}/raporlar", headers=f["b"]))
    ali = next(x for x in r["teknisyenler"] if x["teknisyen_id"] == f["ta"]["id"])
    assert ali["tamamlanan"] == 2 and ali["ilk_seferde_oran"] == 0.5 and ali["memnuniyet_ortalama"] == 3.0
    assert ali["ortalama_sure_dk"] is not None
    berk = next(x for x in r["teknisyenler"] if x["teknisyen_id"] == f["tb"]["id"])
    assert berk["tamamlanan"] == 0 and berk["ilk_seferde_oran"] is None
    assert r["toplam"]["tamamlanan"] == 2
    y = await istemci.get(f"{M}/raporlar?bas=2026-12-01&bit=2026-01-01", headers=f["b"])
    assert y.status_code == 400
    assert s.tr_bugun().isoformat() == r["bit"]


async def test_musteri_silme_kvkk(istemci, firma):
    f = firma
    bos = await _ok(await istemci.post(f"{M}/musteriler", json={"ad": "Silinecek", "eposta": _e("sil")}, headers=f["b"]))
    assert (await _ok(await istemci.delete(f"{M}/musteriler/{bos['id']}", headers=f["b"])))["anonimlesti"] is False
    ie = await _planli_is(istemci, f)
    y = await istemci.delete(f"{M}/musteriler/{f['m']['id']}", headers=f["b"])
    assert y.status_code == 409 and _kod(y) == "acik_is_var"
    await _tamamla(istemci, f, ie)
    sonuc = await _ok(await istemci.delete(f"{M}/musteriler/{f['m']['id']}", headers=f["b"]))
    assert sonuc["anonimlesti"] is True
    assert (await istemci.get(f"{M}/musteriler/{f['m']['id']}", headers=f["b"])).status_code == 404
    # İş emri kalır ama imzalı bağlantı artık açılmaz.
    assert (await istemci.get(f"{A}/{_jeton(ie)}")).status_code == 410


async def test_zamanli_gorev_kayitli():
    from services import zamanli

    assert "saha_servisi" in zamanli.GOREV_ADLARI
