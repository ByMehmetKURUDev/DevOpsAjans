"""Faz 4M — QR menü ve WhatsApp katalog mağazası.

Kapsam: fiyatın SUNUCUDA hesaplanması (istemci fiyatı yok sayılır), seçenek grubu
kuralları, kupon (geçersiz / süresi dolmuş / başlamamış / sınır / en düşük tutar),
en düşük sipariş tutarı, çalışma saatleri (saat dilimi, gece yarısını aşan aralık),
wa.me metninin kodlanması, sipariş hız sınırı + bal küpü, kişisel verinin
anonimleştirilmesi, müşteri izolasyonu + modül kapalıyken 403 + düzen/mağaza/ürün
sınırları, CSV içe aktarma, AI çevirisi (anahtarsız zarif kapanma + sahte sağlayıcı),
analitik (bot sayılmaz, ham IP yok), görsel (WebP), masa QR ZIP, herkese açık
404/410 ve özet, yeni sipariş bildirimi, çöp kutusu, denetim dışı sipariş tablosu.
"""

import base64
import io
import json
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import pytest
from sqlalchemy import select

from conftest import jeton_uret

Y = "/api/v1/qr-menu/yonetim"
M = "/api/v1/menulerim"
A = "/api/v1/menu"
MODUL = "/api/v1/moduller"
PNG_IMZA = b"\x89PNG\r\n\x1a\n"
TARAYICI = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"


def _e(on: str = "menu") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@menu.dev"


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


def _ziyaretci(ip: str = "198.51.100.7", ua: str = TARAYICI) -> dict:
    return {"User-Agent": ua, "X-MK-Istemci-IP": ip}


@pytest.fixture(autouse=True)
def _temiz():
    from routers import qr_menu as r
    from services import hesap_ekibi

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    yield
    r.hiz_sinirlarini_temizle()


async def _modul(istemci, yonetici_basligi, eposta, anahtar="qr_menu", acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/{anahtar}", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _musteri(istemci, yonetici_basligi, anahtar="qr_menu", **ayarlar) -> str:
    e = _e()
    await _modul(istemci, yonetici_basligi, e, anahtar, **ayarlar)
    return e


async def _magaza(istemci, basliklar, yol=Y, **govde):
    govde.setdefault("ad", "Test Kafe")
    govde.setdefault("duzen", "menu")
    y = await istemci.post(yol, json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _kurulum(istemci, basliklar, yol=Y, **magaza):
    """Mağaza + WhatsApp + 'İçecekler' kategorisi + seçenekli 'Latte' (50 TL) + 'Çay' (20 TL)."""
    m = await _magaza(istemci, basliklar, yol, **magaza)
    y = await istemci.put(f"{yol}/{m['id']}", json={
        "whatsapp": "+90 555 111 22 33",
        "siparis_ayarlari": {"whatsapp_acik": True, "gel_al": True, "paket": True, "masada": True,
                             "paket_ucreti": "15", "en_dusuk_tutar": "100"},
    }, headers=basliklar)
    assert y.status_code == 200, y.text
    k = (await istemci.post(f"{yol}/{m['id']}/kategoriler", json={"ad": "İçecekler"}, headers=basliklar)).json()
    latte = await istemci.post(f"{yol}/{m['id']}/urunler", json={
        "kategori_id": k["id"], "ad": "Latte", "aciklama": "Sütlü kahve", "fiyat": "50,00",
        "etiketler": ["vejetaryen", "cok_satan"], "alerjenler": ["sut"],
        "secenek_gruplari": [
            {"id": "boy", "ad": "Boy", "tur": "tek", "zorunlu": True, "secenekler": [
                {"id": "k", "ad": "Küçük", "fiyat_farki": 0}, {"id": "b", "ad": "Büyük", "fiyat_farki": "10"},
            ]},
            {"id": "ekstra", "ad": "Ekstralar", "tur": "coklu", "en_az": 0, "en_cok": 2, "secenekler": [
                {"id": "sot", "ad": "Ekstra şot", "fiyat_farki": "5,50"}, {"id": "krema", "ad": "Krema", "fiyat_farki": 3},
                {"id": "surup", "ad": "Şurup", "fiyat_farki": 4},
            ]},
        ],
    }, headers=basliklar)
    assert latte.status_code == 200, latte.text
    cay = await istemci.post(f"{yol}/{m['id']}/urunler", json={"kategori_id": k["id"], "ad": "Çay", "fiyat": 20},
                             headers=basliklar)
    assert cay.status_code == 200, cay.text
    m = (await istemci.get(f"{yol}/{m['id']}", headers=basliklar)).json()
    return m, k, latte.json(), cay.json()


def _png(boyut=(64, 48), bicim="PNG", renk=(200, 30, 120)) -> bytes:
    from PIL import Image

    g = Image.new("RGB", boyut, renk)
    t = io.BytesIO()
    g.save(t, format=bicim)
    return t.getvalue()


# ---------------------------------------------------------------------------
# Saf kurallar
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ham,beklenen", [
    (50, 5000), (12.5, 1250), ("12,50", 1250), ("1.250,00", 125000), ("1,250.00", 125000), ("₺ 9,99", 999),
    ("0.005", 1), ("19.999", 2000), ("1.000.000", 100000000),
])
def test_kurus_cevrimi(ham, beklenen):
    from services import qr_menu as s

    assert s.kurusa_cevir(ham, "fiyat") == beklenen


@pytest.mark.parametrize("ham", ["abc", "-5", "1e999", True, "12,5,0"])
def test_kurus_cevrimi_gecersiz(ham):
    from services import qr_menu as s

    with pytest.raises(s.MenuHatasi):
        s.kurusa_cevir(ham, "fiyat")


def test_tutar_bicimi_dile_gore():
    from services import qr_menu as s

    assert s.tutar_yaz(123450, "TRY", "tr") == "1.234,50 ₺"
    assert s.tutar_yaz(123450, "EUR", "de") == "1.234,50 €"
    assert s.tutar_yaz(123450, "USD", "en") == "$1,234.50"
    assert s.tutar_yaz(123450, "RUB", "ru") == "1 234,50 ₽"
    assert s.tutar_yaz(5, "TRY", "tr") == "0,05 ₺"


def test_slug_kurallari():
    from services import qr_menu as s

    assert s.slug_oner("Çınaraltı Kafe & Bistro") == "cinaralti-kafe-bistro"
    assert s.slug_oner("Menü") == "menu-menu"
    assert s.slug_duzelt("Kafe-Ornek") == "kafe-ornek"
    for kotu, kod in (("admin", "slug_ayrilmis"), ("menu", "slug_ayrilmis"), ("a", "slug_gecersiz"),
                      ("kafe--x", "slug_gecersiz"), ("-kafe", "slug_gecersiz"), ("kafe ornek", "slug_gecersiz")):
        with pytest.raises(s.MenuHatasi) as h:
            s.slug_duzelt(kotu)
        assert h.value.kod == kod, kotu


def test_on_dort_alerjen_ve_etiketler():
    from services import qr_menu as s

    assert len(s.ALERJENLER) == 14 and len(set(s.ALERJENLER)) == 14
    assert {"gluten", "kabuklular", "yumurta", "balik", "yer_fistigi", "soya", "sut", "sert_kabuklu", "kereviz",
            "hardal", "susam", "sulfit", "aci_bakla", "yumusakcalar"} == set(s.ALERJENLER)
    assert s.etiketleri_coz("Vegan, Acılı; yeni | çok satan") == ["vegan", "acili", "yeni", "cok_satan"]
    assert s.etiketleri_coz("gluten-free, vegetarian") == ["glutensiz", "vejetaryen"]
    with pytest.raises(s.MenuHatasi) as h:
        s.etiketleri_coz("vegan, organik")
    assert h.value.kod == "etiket_gecersiz"
    with pytest.raises(s.MenuHatasi):
        s.alerjenleri_coz("sut, fistik")


def _an(yil, ay, gun, saat, dk, tz="Europe/Istanbul") -> datetime:
    from zoneinfo import ZoneInfo

    return datetime(yil, ay, gun, saat, dk, tzinfo=ZoneInfo(tz)).astimezone(timezone.utc)


def test_calisma_saatleri_acik_kapali_saat_dilimi_ve_gece_yarisi():
    from services import qr_menu as s

    # 2026-10-05 pazartesi.
    saatler = s.calisma_saatleri_duzelt({
        "0": [["09:00", "12:00"], ["13:00", "17:00"]],
        "4": [["18:00", "02:00"]],  # cuma akşamı → cumartesi 02:00
        "6": [["00:00", "24:00"]],  # pazar bütün gün
    })
    tz = "Europe/Istanbul"
    assert s.acik_mi(saatler, tz, _an(2026, 10, 5, 9, 0)) is True
    assert s.acik_mi(saatler, tz, _an(2026, 10, 5, 12, 0)) is False  # bitiş dakikası dahil değil
    assert s.acik_mi(saatler, tz, _an(2026, 10, 5, 12, 30)) is False
    assert s.acik_mi(saatler, tz, _an(2026, 10, 5, 16, 59)) is True
    assert s.acik_mi(saatler, tz, _an(2026, 10, 9, 23, 30)) is True   # cuma gece
    assert s.acik_mi(saatler, tz, _an(2026, 10, 10, 1, 59)) is True   # cumartesi gece taşan kısım
    assert s.acik_mi(saatler, tz, _an(2026, 10, 10, 2, 0)) is False
    assert s.acik_mi(saatler, tz, _an(2026, 10, 10, 18, 0)) is False  # cumartesi tanımsız
    assert s.acik_mi(saatler, tz, _an(2026, 10, 11, 23, 59)) is True  # pazar 24 saat
    assert s.acik_mi(saatler, tz, _an(2026, 10, 12, 0, 30)) is False  # "24:00" ertesi güne taşmıyor
    # Aynı UTC anı: İstanbul'da 10:00 (açık), New York'ta 03:00 (kapalı).
    an = _an(2026, 10, 5, 10, 0)
    assert s.acik_mi(saatler, "Europe/Istanbul", an) is True
    assert s.acik_mi(saatler, "America/New_York", an) is False
    # Tanım yoksa bilinmiyor (rozet yok).
    assert s.acik_mi({}, tz, an) is None


@pytest.mark.parametrize("kotu", [
    {"7": [["09:00", "10:00"]]}, {"0": [["9:00", "10:00"]]}, {"0": [["10:00", "10:00"]]}, {"0": [["24:00", "02:00"]]},
    {"0": [["09:00", "25:00"]]}, {"0": [["01:00", "02:00"]] * 4}, {"0": "09:00-10:00"},
])
def test_calisma_saatleri_gecersiz(kotu):
    from services import qr_menu as s

    with pytest.raises(s.MenuHatasi):
        s.calisma_saatleri_duzelt(kotu)


def test_secenek_grubu_kurallari():
    from services import qr_menu as s

    gruplar = s.secenek_gruplari_duzelt([
        {"ad": "Boy", "tur": "tek", "zorunlu": True, "secenekler": [{"ad": "K"}, {"ad": "B", "fiyat_farki": "2,5"}]},
        {"ad": "Sos", "tur": "coklu", "en_az": 1, "en_cok": 2, "secenekler": [{"ad": "a"}, {"ad": "b"}, {"ad": "c"}]},
    ])
    boy, sos = gruplar
    assert (boy["en_az"], boy["en_cok"], boy["zorunlu"]) == (1, 1, True)
    assert (sos["en_az"], sos["en_cok"], sos["zorunlu"]) == (1, 2, True)
    assert boy["secenekler"][1]["fiyat_farki"] == 250 and boy["id"] and boy["secenekler"][0]["id"]
    b_id = boy["secenekler"][1]["id"]
    secilen, fark = s.secimleri_dogrula(gruplar, {boy["id"]: [b_id], sos["id"]: [sos["secenekler"][0]["id"]]}, 0)
    assert fark == 250 and len(secilen) == 2
    for secimler, kod in (
        ({sos["id"]: [sos["secenekler"][0]["id"]]}, "secenek_eksik"),               # zorunlu boy yok
        ({boy["id"]: [b_id, boy["secenekler"][0]["id"]], sos["id"]: [sos["secenekler"][0]["id"]]}, "secenek_fazla"),
        ({boy["id"]: [b_id], sos["id"]: [x["id"] for x in sos["secenekler"]]}, "secenek_fazla"),  # en çok 2
        ({boy["id"]: ["yok"], sos["id"]: [sos["secenekler"][0]["id"]]}, "secenek_gecersiz"),
        ({"bilinmeyen": ["x"]}, "secenek_gecersiz"),
    ):
        with pytest.raises(s.MenuHatasi) as h:
            s.secimleri_dogrula(gruplar, secimler, 0)
        assert h.value.kod == kod, secimler
    # Aynı seçenek iki kez → bir kez sayılır.
    _, fark = s.secimleri_dogrula(gruplar, {boy["id"]: [b_id, b_id], sos["id"]: [sos["secenekler"][0]["id"]]}, 0)
    assert fark == 250
    for kotu in ([{"ad": "X", "secenekler": []}], [{"ad": "", "secenekler": [{"ad": "a"}]}],
                 [{"ad": "X", "tur": "coklu", "en_az": 3, "en_cok": 2, "secenekler": [{"ad": "a"}, {"ad": "b"}, {"ad": "c"}]}]):
        with pytest.raises(s.MenuHatasi):
            s.secenek_gruplari_duzelt(kotu)


def test_wa_adresi_kodlamasi():
    from services import qr_menu as s

    metin = "Sipariş #AB12CD — Çınar & Şürekâ\n2 × Latte (Büyük)\nNot: 50% şekerli + #3 #masa?"
    adres = s.wa_adresi("+90 555 111 22 33", metin)
    assert adres.startswith("https://wa.me/905551112233?text=")
    kodlu = adres.split("?text=", 1)[1]
    assert "%0A" in kodlu and "%26" in kodlu and "%23" in kodlu and "%25" in kodlu and "%2B" in kodlu and "%3F" in kodlu
    assert " " not in kodlu and "\n" not in kodlu and "&" not in kodlu and "#" not in kodlu
    assert "%C3%87" in kodlu  # Ç (UTF-8)
    assert unquote(kodlu) == metin


def test_ceviri_yaniti_guvenli_cozulur():
    from services import qr_menu as s

    yanit = 'Tabii!\n```json\n{"en": {"ad": "Latte", "aciklama": "Milky coffee", "kotu": "x"}, "de": {"ad": "Latte"}, "xx": {}}\n```'
    sonuc = s.ceviri_yanitini_coz(yanit, ["en", "de"], ["ad", "aciklama"], {"ad": 120, "aciklama": 1000})
    assert sonuc == {"en": {"ad": "Latte", "aciklama": "Milky coffee"}, "de": {"ad": "Latte"}}
    for kotu in ("", "çeviri yok", "[1,2]", '{"fr": {"ad": "x"}}'):
        with pytest.raises(s.MenuHatasi):
            s.ceviri_yanitini_coz(kotu, ["en"], ["ad"], {"ad": 120})


# ---------------------------------------------------------------------------
# Modül kapısı, düzenler, sınırlar, izolasyon
# ---------------------------------------------------------------------------
async def test_modul_kapaliyken_403_ve_anonim_401(istemci, yonetici_basligi):
    e = _e()
    y = await istemci.get(M, headers=_b(e))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    assert (await istemci.get(M)).status_code == 401
    assert (await istemci.get(Y)).status_code == 401
    assert (await istemci.get(Y, headers=_b(e))).status_code == 403


async def test_duzen_modulleri_ve_magaza_siniri(istemci, yonetici_basligi):
    e = await _musteri(istemci, yonetici_basligi, "qr_menu")
    meta = (await istemci.get(f"{M}/meta", headers=_b(e))).json()
    assert meta["duzenler"] == ["menu"] and meta["sinirlar"]["menu"]["magaza_siniri"] == 1
    assert meta["sinirlar"]["menu"]["urun_siniri"] == 300 and len(meta["alerjenler"]) == 14
    y = await istemci.post(M, json={"ad": "Katalog", "duzen": "katalog"}, headers=_b(e))
    assert y.status_code == 403 and _kod(y) == "duzen_kapali"
    m = await _magaza(istemci, _b(e), M, ad="Çınar Kafe")
    assert m["slug"] == "cinar-kafe" and m["hesap_email"] == e and m["duzen"] == "menu"
    y = await istemci.post(M, json={"ad": "İkinci", "duzen": "menu"}, headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "magaza_siniri"
    # Yalnız katalog modülü açık müşteri: sekme/uçlar açık, yalnız katalog düzeni.
    k = await _musteri(istemci, yonetici_basligi, "whatsapp_katalog", magaza_siniri=2)
    meta = (await istemci.get(f"{M}/meta", headers=_b(k))).json()
    assert meta["duzenler"] == ["katalog"] and meta["sinirlar"]["katalog"]["magaza_siniri"] == 2
    km = await _magaza(istemci, _b(k), M, ad="Çınar Kafe", duzen="katalog")
    assert km["slug"] == "cinar-kafe-2"
    assert km["siparis_ayarlari"]["masada"] is False and km["siparis_ayarlari"]["paket"] is True
    y = await istemci.put(f"{M}/{km['id']}", json={"duzen": "menu"}, headers=_b(k))
    assert y.status_code == 403 and _kod(y) == "duzen_kapali"
    # Modül kapanınca: yazma 403, herkese açık sayfa 410; okuma (siparişler) sürer.
    await _modul(istemci, yonetici_basligi, e, "qr_menu", acik=False)
    await _modul(istemci, yonetici_basligi, e, "whatsapp_katalog", acik=True)
    y = await istemci.put(f"{M}/{m['id']}", json={"ad": "Yeni"}, headers=_b(e))
    assert y.status_code == 403 and _kod(y) == "duzen_kapali"
    assert (await istemci.get(f"{M}/{m['id']}/siparisler", headers=_b(e))).status_code == 200
    assert (await istemci.get(f"{A}/{m['slug']}")).status_code == 410


async def test_musteri_izolasyonu_ve_yonetici_hepsini_gorur(istemci, yonetici_basligi):
    a = await _musteri(istemci, yonetici_basligi)
    b = await _musteri(istemci, yonetici_basligi)
    ma, ka, latte, _ = await _kurulum(istemci, _b(a), M, ad="A Kafe")
    mb = await _magaza(istemci, _b(b), M, ad="B Kafe")
    liste = (await istemci.get(M, headers=_b(b))).json()["items"]
    assert [x["id"] for x in liste] == [mb["id"]]
    for yol in (f"{M}/{ma['id']}", f"{M}/{ma['id']}/icerik", f"{M}/{ma['id']}/siparisler", f"{M}/{ma['id']}/analiz",
                f"{M}/{ma['id']}/kuponlar"):
        y = await istemci.get(yol, headers=_b(b))
        assert y.status_code == 404, yol
    y = await istemci.put(f"{M}/{ma['id']}/urunler/{latte['id']}", json={"fiyat": 1}, headers=_b(b))
    assert y.status_code == 404
    y = await istemci.delete(f"{M}/{ma['id']}", headers=_b(b))
    assert y.status_code == 404
    # B kendi mağazasında A'nın kategorisine ürün ekleyemez.
    y = await istemci.post(f"{M}/{mb['id']}/urunler", json={"kategori_id": ka["id"], "ad": "X", "fiyat": 1}, headers=_b(b))
    assert y.status_code == 404 and _kod(y) == "kategori_yok"
    # Yönetici: hepsi + süzgeç.
    hepsi = {x["id"] for x in (await istemci.get(Y, headers=yonetici_basligi)).json()["items"]}
    assert {ma["id"], mb["id"]} <= hepsi
    yalniz = (await istemci.get(f"{Y}?hesap={a}", headers=yonetici_basligi)).json()["items"]
    assert [x["id"] for x in yalniz] == [ma["id"]]
    # Yönetici müşteri adına kurar.
    c = _e()
    m = await _magaza(istemci, yonetici_basligi, Y, ad="Kurulum", hesap_email=c)
    assert m["hesap_email"] == c


async def test_urun_siniri(istemci, yonetici_basligi):
    e = await _musteri(istemci, yonetici_basligi, urun_siniri=2)
    m, k, _, _ = await _kurulum(istemci, _b(e), M)
    y = await istemci.post(f"{M}/{m['id']}/urunler", json={"kategori_id": k["id"], "ad": "Üçüncü", "fiyat": 5}, headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "urun_siniri" and y.json()["detail"]["sinir"] == 2
    # Yönetici sınıra takılmaz.
    y = await istemci.post(f"{Y}/{m['id']}/urunler", json={"kategori_id": k["id"], "ad": "Üçüncü", "fiyat": 5},
                           headers=yonetici_basligi)
    assert y.status_code == 200


async def test_magaza_dogrulamalari(istemci, yonetici_basligi):
    m = await _magaza(istemci, yonetici_basligi)
    for govde, kod in (
        ({"slug": "admin"}, "slug_ayrilmis"), ({"tema_rengi": "mor"}, "renk_gecersiz"), ({"whatsapp": "0555"}, "telefon_gecersiz"),
        ({"para_birimi": "XYZ"}, "para_birimi_gecersiz"), ({"varsayilan_dil": "fr"}, "dil_gecersiz"),
        ({"saat_dilimi": "Mars/Olympus"}, "saat_dilimi_gecersiz"), ({"saklama_gun": 0}, "aralik_disi"),
        ({"calisma_saatleri": {"0": [["10:00", "10:00"]]}}, "saat_gecersiz"),
        ({"siparis_ayarlari": {"gel_al": False, "paket": False, "masada": False}}, "teslimat_yok"),
        ({"logo": "baskasinin-gorseli"}, "gorsel_gecersiz"),
    ):
        y = await istemci.put(f"{Y}/{m['id']}", json=govde, headers=yonetici_basligi)
        assert y.status_code == 400 and _kod(y) == kod, (govde, y.text)
    diger = await _magaza(istemci, yonetici_basligi, ad="Diğer")
    y = await istemci.put(f"{Y}/{m['id']}", json={"slug": diger["slug"]}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "slug_kullaniliyor"
    y = await istemci.put(f"{Y}/{m['id']}", json={
        "varsayilan_dil": "tr", "ek_diller": ["en", "ar", "tr", "en"], "ceviriler": {"en": {"ad": "Test Cafe"}, "fr": {"ad": "x"}},
        "saat_dilimi": "Europe/Berlin", "para_birimi": "eur", "whatsapp": "0090 555 111 22 33",
    }, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    d = y.json()
    assert d["ek_diller"] == ["en", "ar"] and d["ceviriler"] == {"en": {"ad": "Test Cafe"}}
    assert d["para_birimi"] == "EUR" and d["whatsapp"] == "+905551112233" and d["saat_dilimi"] == "Europe/Berlin"


# ---------------------------------------------------------------------------
# Herkese açık menü, sepet ve sipariş
# ---------------------------------------------------------------------------
async def test_acik_menu_404_410_ve_gorunurluk(istemci, yonetici_basligi):
    assert (await istemci.get(f"{A}/yok-boyle-menu")).status_code == 404
    assert (await istemci.get(f"{A}/../admin")).status_code == 404
    m, k, latte, cay = await _kurulum(istemci, yonetici_basligi)
    gizli_kat = (await istemci.post(f"{Y}/{m['id']}/kategoriler", json={"ad": "Gizli", "gizli": True}, headers=yonetici_basligi)).json()
    await istemci.post(f"{Y}/{m['id']}/urunler", json={"kategori_id": gizli_kat["id"], "ad": "Sır", "fiyat": 1}, headers=yonetici_basligi)
    await istemci.put(f"{Y}/{m['id']}/urunler/{cay['id']}", json={"gizli": True}, headers=yonetici_basligi)
    y = await istemci.get(f"{A}/{m['slug']}")
    assert y.status_code == 200 and y.headers["x-robots-tag"] == "noindex"
    d = y.json()
    assert [u["ad"] for u in d["urunler"]] == ["Latte"]
    assert [k2["ad"] for k2 in d["kategoriler"]] == ["İçecekler"]
    assert d["urunler"][0]["fiyat"] == 50.0 and d["urunler"][0]["alerjenler"] == ["sut"]
    assert d["siparis"]["whatsapp_acik"] is True and d["siparis"]["paket_ucreti"] == 15.0
    assert "hesap_email" not in d and "whatsapp" not in d
    await istemci.put(f"{Y}/{m['id']}", json={"aktif": False}, headers=yonetici_basligi)
    assert (await istemci.get(f"{A}/{m['slug']}")).status_code == 410
    assert (await istemci.get(f"{A}/{m['slug']}/ozet")).status_code == 410


async def test_ozet_paylasim_icin(istemci, yonetici_basligi):
    m, _, latte, _ = await _kurulum(istemci, yonetici_basligi, ad="Özet Kafe")
    await istemci.put(f"{Y}/{m['id']}", json={"aciklama": "Taze kahve", "ek_diller": ["en"],
                                              "ceviriler": {"en": {"ad": "Summary Cafe", "aciklama": "Fresh coffee"}}},
                      headers=yonetici_basligi)
    await istemci.put(f"{Y}/{m['id']}/urunler/{latte['id']}", json={"ceviriler": {"en": {"ad": "Caffe Latte"}}}, headers=yonetici_basligi)
    d = (await istemci.get(f"{A}/{m['slug']}/ozet?urun={latte['id']}")).json()
    assert d["ad"] == "Özet Kafe" and d["aciklama"] == "Taze kahve" and d["indekslenebilir"] is False
    assert d["urun"]["ad"] == "Latte" and d["urun"]["fiyat"] == "50,00 ₺"
    assert d["adres_url"] == f"https://mehmetkuru.dev/menu/{m['slug']}"
    d = (await istemci.get(f"{A}/{m['slug']}/ozet?urun={latte['id']}&dil=en")).json()
    assert d["ad"] == "Summary Cafe" and d["urun"]["ad"] == "Caffe Latte" and d["dil"] == "en"
    d = (await istemci.get(f"{A}/{m['slug']}/ozet?urun=999999&dil=fr")).json()
    assert d["urun"] is None and d["dil"] == "tr"


async def test_fiyat_sunucuda_hesaplanir_istemci_fiyati_yok_sayilir(istemci, yonetici_basligi, db_oturumu):
    m, _, latte, cay = await _kurulum(istemci, yonetici_basligi)
    sepet = [
        {"urun_id": latte["id"], "adet": 2, "secimler": {"boy": ["b"], "ekstra": ["sot", "krema"]},
         "fiyat": 0.01, "birim_fiyat": 0.01, "tutar": 0.01},
        {"urun_id": cay["id"], "adet": 3, "fiyat": 1},
    ]
    y = await istemci.post(f"{A}/{m['slug']}/hesapla", json={"kalemler": sepet, "teslimat": "gel_al", "toplam": 1},
                           headers=_ziyaretci())
    assert y.status_code == 200, y.text
    h = y.json()
    # Latte: 50 + 10 (büyük) + 5,50 + 3 = 68,50 × 2 = 137; çay 20 × 3 = 60.
    assert [k["birim_fiyat"] for k in h["kalemler"]] == [68.5, 20.0]
    assert h["ara_toplam"] == 197.0 and h["toplam"] == 197.0 and h["paket_ucreti"] == 0
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json={
        "kalemler": sepet, "teslimat": "paket", "ad": "Ali Veli", "adres": "Moda Cd. 1, Kadıköy", "not": "Zil çalmasın",
        "toplam": 1, "ara_toplam": 1, "dil": "tr",
    }, headers=_ziyaretci())
    assert y.status_code == 200, y.text
    o = y.json()
    assert o["toplam"] == 212.0  # + 15 paket ücreti
    from models.qr_menu import MenuSiparisleri

    satir = (await db_oturumu.execute(select(MenuSiparisleri).where(MenuSiparisleri.siparis_no == o["siparis_no"]))).scalars().one()
    assert (satir.ara_toplam, satir.paket_ucreti, satir.toplam) == (19700, 1500, 21200)
    kalemler = json.loads(satir.kalemler)
    assert kalemler[0]["birim_fiyat"] == 6850 and [s["ad"] for s in kalemler[0]["secenekler"]] == ["Büyük", "Ekstra şot", "Krema"]
    # İndirimli fiyat geçerli.
    await istemci.put(f"{Y}/{m['id']}/urunler/{cay['id']}", json={"indirimli_fiyat": "15"}, headers=yonetici_basligi)
    h = (await istemci.post(f"{A}/{m['slug']}/hesapla", json={"kalemler": [{"urun_id": cay["id"], "adet": 1}]})).json()
    assert h["ara_toplam"] == 15.0
    y = await istemci.put(f"{Y}/{m['id']}/urunler/{cay['id']}", json={"indirimli_fiyat": "25"}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "indirimli_fiyat_buyuk"


async def test_sepet_kurallari_ve_secenek_hatalari(istemci, yonetici_basligi):
    m, _, latte, cay = await _kurulum(istemci, yonetici_basligi)
    yol = f"{A}/{m['slug']}/hesapla"
    for kalemler, kod in (
        ([{"urun_id": latte["id"], "adet": 1}], "secenek_eksik"),
        ([{"urun_id": latte["id"], "adet": 1, "secimler": {"boy": ["k", "b"]}}], "secenek_fazla"),
        ([{"urun_id": latte["id"], "adet": 1, "secimler": {"boy": ["k"], "ekstra": ["sot", "krema", "surup"]}}], "secenek_fazla"),
        ([{"urun_id": latte["id"], "adet": 1, "secimler": {"boy": ["dev"]}}], "secenek_gecersiz"),
        ([{"urun_id": latte["id"], "adet": 0, "secimler": {"boy": ["k"]}}], "aralik_disi"),
        ([{"urun_id": latte["id"], "adet": 100, "secimler": {"boy": ["k"]}}], "aralik_disi"),
        ([{"urun_id": 999999, "adet": 1}], "urun_yok"),
        ([], "sepet_bos"),
    ):
        y = await istemci.post(yol, json={"kalemler": kalemler})
        assert y.status_code == 400 and _kod(y) == kod, (kalemler, y.text)
    await istemci.put(f"{Y}/{m['id']}/urunler/{cay['id']}", json={"stokta_yok": True}, headers=yonetici_basligi)
    y = await istemci.post(yol, json={"kalemler": [{"urun_id": cay["id"], "adet": 1}]})
    assert y.status_code == 400 and _kod(y) == "urun_stokta_yok"
    # Başka mağazanın ürünü bu menüde yok.
    m2, _, _, cay2 = await _kurulum(istemci, yonetici_basligi, ad="Başka")
    y = await istemci.post(yol, json={"kalemler": [{"urun_id": cay2["id"], "adet": 1}]})
    assert y.status_code == 400 and _kod(y) == "urun_yok"
    # Kapalı teslimat türü.
    await istemci.put(f"{Y}/{m2['id']}", json={"siparis_ayarlari": {"paket": False}}, headers=yonetici_basligi)
    y = await istemci.post(f"{A}/{m2['slug']}/hesapla", json={"kalemler": [{"urun_id": cay2["id"], "adet": 1}], "teslimat": "paket"})
    assert y.status_code == 400 and _kod(y) == "teslimat_gecersiz"


async def test_en_dusuk_tutar_yalniz_paket_serviste(istemci, yonetici_basligi):
    m, _, _, cay = await _kurulum(istemci, yonetici_basligi)
    govde = {"kalemler": [{"urun_id": cay["id"], "adet": 2}], "ad": "Ayşe", "adres": "Bir sokak 5"}
    h = (await istemci.post(f"{A}/{m['slug']}/hesapla", json={**govde, "teslimat": "paket"})).json()
    assert h["en_dusuk_tutar"] == 100.0 and h["en_dusuk_eksik"] == 60.0
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json={**govde, "teslimat": "paket"}, headers=_ziyaretci())
    assert y.status_code == 409 and _kod(y) == "en_dusuk_tutar" and y.json()["detail"]["eksik"] == 60.0
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json={**govde, "teslimat": "gel_al"}, headers=_ziyaretci())
    assert y.status_code == 200, y.text
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json={**govde, "kalemler": [{"urun_id": cay["id"], "adet": 5}],
                                                            "teslimat": "paket"}, headers=_ziyaretci())
    assert y.status_code == 200, y.text
    # Paket serviste adres zorunlu; masada masa zorunlu.
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json={**govde, "kalemler": [{"urun_id": cay["id"], "adet": 5}],
                                                            "adres": "", "teslimat": "paket"}, headers=_ziyaretci("10.0.0.2"))
    assert y.status_code == 400 and _kod(y) == "zorunlu" and y.json()["detail"]["alan"] == "adres"
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json={**govde, "teslimat": "masada"}, headers=_ziyaretci("10.0.0.2"))
    assert y.status_code == 400 and _kod(y) == "masa_gerekli"


async def test_kupon_kurallari(istemci, yonetici_basligi):
    m, _, _, cay = await _kurulum(istemci, yonetici_basligi)
    simdi = datetime.now(timezone.utc)
    kup = lambda **g: istemci.post(f"{Y}/{m['id']}/kuponlar", json=g, headers=yonetici_basligi)  # noqa: E731
    assert (await kup(kod="yaz 10", tur="yuzde", deger=10)).json()["kod"] == "YAZ10"
    assert (await kup(kod="TEK", tur="tutar", deger="12,5", kullanim_siniri=1)).status_code == 200
    assert (await kup(kod="ESKI", tur="yuzde", deger=50, bitis=(simdi - timedelta(days=1)).isoformat())).status_code == 200
    assert (await kup(kod="GELECEK", tur="yuzde", deger=50, baslangic=(simdi + timedelta(days=2)).isoformat())).status_code == 200
    assert (await kup(kod="BUYUK", tur="tutar", deger=30, en_dusuk_tutar=500)).status_code == 200
    assert (await kup(kod="KAPALI", tur="yuzde", deger=20, aktif=False)).status_code == 200
    y = await kup(kod="YAZ10", tur="yuzde", deger=5)
    assert y.status_code == 409 and _kod(y) == "kupon_kodu_kullaniliyor"
    for govde, kod in (({"kod": "X", "tur": "yuzde", "deger": 5}, "kupon_kodu_gecersiz"),
                       ({"kod": "YUZ", "tur": "yuzde", "deger": 101}, "aralik_disi"),
                       ({"kod": "TURS", "tur": "bedava", "deger": 1}, "kupon_turu_gecersiz")):
        y = await kup(**govde)
        assert y.status_code == 400 and _kod(y) == kod, govde
    sepet = {"kalemler": [{"urun_id": cay["id"], "adet": 3}], "teslimat": "gel_al"}  # 60 TL

    async def hesap(kod):
        return (await istemci.post(f"{A}/{m['slug']}/hesapla", json={**sepet, "kupon": kod})).json()

    h = await hesap("yaz10")
    assert h["kupon"]["gecerli"] and h["indirim"] == 6.0 and h["toplam"] == 54.0
    assert (await hesap("TEK"))["indirim"] == 12.5
    for kod, hata in (("YOK", "kupon_gecersiz"), ("ESKI", "kupon_suresi_doldu"), ("GELECEK", "kupon_baslamadi"),
                      ("BUYUK", "kupon_en_dusuk"), ("KAPALI", "kupon_gecersiz")):
        h = await hesap(kod)
        assert h["kupon"] == {"kod": kod, "gecerli": False, "hata": hata, "tur": None, "deger": None} and h["indirim"] == 0, kod
    siparis = {**sepet, "ad": "Can", "kupon": "TEK"}
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json=siparis, headers=_ziyaretci("10.1.1.1"))
    assert y.status_code == 200 and y.json()["toplam"] == 47.5
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json=siparis, headers=_ziyaretci("10.1.1.2"))
    assert y.status_code == 409 and _kod(y) == "kupon_siniri"
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json={**siparis, "kupon": "ESKI"}, headers=_ziyaretci("10.1.1.3"))
    assert y.status_code == 409 and _kod(y) == "kupon_suresi_doldu"
    kuponlar = {c["kod"]: c for c in (await istemci.get(f"{Y}/{m['id']}/kuponlar", headers=yonetici_basligi)).json()["items"]}
    assert kuponlar["TEK"]["kullanim_sayisi"] == 1 and kuponlar["TEK"]["durum"] == "kupon_siniri"
    assert kuponlar["ESKI"]["durum"] == "kupon_suresi_doldu" and kuponlar["YAZ10"]["durum"] == "gecerli"


async def test_calisma_saatine_gore_siparis(istemci, yonetici_basligi):
    from zoneinfo import ZoneInfo

    m, _, _, cay = await _kurulum(istemci, yonetici_basligi)
    yerel = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Istanbul"))
    dk = yerel.hour * 60 + yerel.minute
    saat = lambda d: f"{(d % 1440) // 60:02d}:{(d % 1440) % 60:02d}"  # noqa: E731
    kapali = {str(g): [[saat(dk + 120), saat(dk + 180)]] for g in range(7)}
    await istemci.put(f"{Y}/{m['id']}", json={"calisma_saatleri": kapali}, headers=yonetici_basligi)
    d = (await istemci.get(f"{A}/{m['slug']}")).json()
    assert d["acik"] is False
    govde = {"kalemler": [{"urun_id": cay["id"], "adet": 1}], "teslimat": "gel_al", "ad": "Deniz"}
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json=govde, headers=_ziyaretci())
    assert y.status_code == 409 and _kod(y) == "magaza_kapali"
    await istemci.put(f"{Y}/{m['id']}", json={"siparis_ayarlari": {"kapaliyken_siparis": True}}, headers=yonetici_basligi)
    assert (await istemci.post(f"{A}/{m['slug']}/siparis", json=govde, headers=_ziyaretci())).status_code == 200
    # Gece yarısını aşan aralık (dün başlayıp şimdiyi kapsayan): açık.
    acik = {str(g): [[saat(dk - 60), saat(dk + 60)]] for g in range(7)}
    await istemci.put(f"{Y}/{m['id']}", json={"calisma_saatleri": acik}, headers=yonetici_basligi)
    assert (await istemci.get(f"{A}/{m['slug']}")).json()["acik"] is True


async def test_whatsapp_siparisi_metin_ve_bildirim(istemci, yonetici_basligi, db_oturumu):
    e = await _musteri(istemci, yonetici_basligi)
    m, _, latte, cay = await _kurulum(istemci, _b(e), M, ad="Çınar & Şürekâ")
    await istemci.put(f"{M}/{m['id']}", json={"ek_diller": ["en"]}, headers=_b(e))
    await istemci.put(f"{M}/{m['id']}/urunler/{cay['id']}", json={"ceviriler": {"en": {"ad": "Tea"}}}, headers=_b(e))
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json={
        "kalemler": [{"urun_id": cay["id"], "adet": 2}, {"urun_id": latte["id"], "adet": 1, "secimler": {"boy": ["k"]}}],
        "teslimat": "masada", "masa": "12", "ad": "Zeynep", "not": "Şekersiz & sıcak #1", "dil": "en",
    }, headers=_ziyaretci())
    assert y.status_code == 200, y.text
    o = y.json()
    assert o["wa_adresi"].startswith("https://wa.me/905551112233?text=")
    metin = unquote(o["wa_adresi"].split("?text=", 1)[1])
    assert metin == o["metin"]
    assert metin.splitlines()[0] == f"Order #{o['siparis_no']} — Çınar & Şürekâ"
    assert "Delivery: At the table" in metin and "Table: 12" in metin and "Name: Zeynep" in metin
    assert "2 × Tea — ₺40.00" in metin and "1 × Latte (Küçük) — ₺50.00" in metin
    assert "Total: ₺90.00" in metin and "Note: Şekersiz & sıcak #1" in metin
    # Panelde sipariş görünür (yeni), sayaç 1.
    liste = (await istemci.get(f"{M}/{m['id']}/siparisler", headers=_b(e))).json()
    assert liste["yeni_sayisi"] == 1 and liste["items"][0]["siparis_no"] == o["siparis_no"]
    assert liste["items"][0]["musteri_ad"] == "Zeynep" and liste["items"][0]["masa"] == "12"
    ozet = (await istemci.get(f"{M}/siparis-ozeti", headers=_b(e))).json()
    assert ozet["yeni"] == 1 and ozet["magazalar"] == {str(m["id"]): 1}
    sid = liste["items"][0]["id"]
    y = await istemci.put(f"{M}/{m['id']}/siparisler/{sid}", json={"durum": "hazirlaniyor"}, headers=_b(e))
    assert y.json()["durum"] == "hazirlaniyor"
    y = await istemci.put(f"{M}/{m['id']}/siparisler/{sid}", json={"durum": "uçtu"}, headers=_b(e))
    assert y.status_code == 400
    ayrinti = (await istemci.get(f"{M}/{m['id']}/siparisler/{sid}", headers=_b(e))).json()
    assert ayrinti["magaza"]["ad"] == "Çınar & Şürekâ" and ayrinti["toplam"] == 90.0
    # "Yeni sipariş" bildirimi mağaza sahibine (panel içi satır).
    from models.notifications import Notifications

    bildirimler = (await db_oturumu.execute(
        select(Notifications).where(Notifications.event_type == "menu_siparis", Notifications.recipient_email == e)
    )).scalars().all()
    assert bildirimler and bildirimler[0].link == "/client?sekme=menu" and o["siparis_no"] in bildirimler[0].title
    assert "Zeynep" not in (bildirimler[0].body or "")


async def test_siparis_kapaliyken_ve_numarasizken_409(istemci, yonetici_basligi):
    m, _, _, cay = await _kurulum(istemci, yonetici_basligi)
    govde = {"kalemler": [{"urun_id": cay["id"], "adet": 1}], "teslimat": "gel_al", "ad": "Ece"}
    await istemci.put(f"{Y}/{m['id']}", json={"whatsapp": ""}, headers=yonetici_basligi)
    assert (await istemci.get(f"{A}/{m['slug']}")).json()["siparis"]["whatsapp_acik"] is False
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json=govde, headers=_ziyaretci())
    assert y.status_code == 409 and _kod(y) == "siparis_kapali"


async def test_siparis_hiz_siniri_ve_bal_kupu(istemci, yonetici_basligi, db_oturumu):
    m, _, _, cay = await _kurulum(istemci, yonetici_basligi)
    govde = {"kalemler": [{"urun_id": cay["id"], "adet": 1}], "teslimat": "gel_al", "ad": "Bot"}
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json={**govde, "web_adresi": "http://spam"}, headers=_ziyaretci("10.9.9.9"))
    assert y.status_code == 200 and y.json() == {"ok": True, "siparis_no": None, "wa_adresi": None}
    from models.qr_menu import MenuSiparisleri

    assert (await db_oturumu.execute(select(MenuSiparisleri).where(MenuSiparisleri.magaza_id == m["id"]))).scalars().all() == []
    for i in range(4):
        assert (await istemci.post(f"{A}/{m['slug']}/siparis", json=govde, headers=_ziyaretci("10.9.9.9"))).status_code == 200, i
    y = await istemci.post(f"{A}/{m['slug']}/siparis", json=govde, headers=_ziyaretci("10.9.9.9"))
    assert y.status_code == 429 and _kod(y) == "cok_hizli"
    # Başka IP etkilenmez.
    assert (await istemci.post(f"{A}/{m['slug']}/siparis", json=govde, headers=_ziyaretci("10.9.9.10"))).status_code == 200


async def test_kisisel_veri_anonimlestirilir(istemci, yonetici_basligi, db_oturumu):
    m, _, _, cay = await _kurulum(istemci, yonetici_basligi)
    govde = {"kalemler": [{"urun_id": cay["id"], "adet": 5}], "teslimat": "paket", "ad": "Gizli Kişi",
             "adres": "Gizli sokak 1", "not": "Kapıda ödeme"}
    eski_no = (await istemci.post(f"{A}/{m['slug']}/siparis", json=govde, headers=_ziyaretci("10.2.0.1"))).json()["siparis_no"]
    orta_no = (await istemci.post(f"{A}/{m['slug']}/siparis", json=govde, headers=_ziyaretci("10.2.0.2"))).json()["siparis_no"]
    yeni_no = (await istemci.post(f"{A}/{m['slug']}/siparis", json=govde, headers=_ziyaretci("10.2.0.3"))).json()["siparis_no"]
    from models.qr_menu import MenuSiparisleri

    simdi = datetime.now(timezone.utc)
    for no, gun in ((eski_no, 91), (orta_no, 40)):
        satir = (await db_oturumu.execute(select(MenuSiparisleri).where(MenuSiparisleri.siparis_no == no))).scalars().one()
        satir.created_at = simdi - timedelta(days=gun)
    await db_oturumu.commit()
    liste = {o["siparis_no"]: o for o in (await istemci.get(f"{Y}/{m['id']}/siparisler", headers=yonetici_basligi)).json()["items"]}
    assert liste[eski_no]["anonim"] is True and liste[eski_no]["musteri_ad"] is None and liste[eski_no]["adres"] is None
    assert liste[eski_no]["siparis_notu"] is None and liste[eski_no]["toplam"] == 115.0  # tutarlar kalır
    assert liste[orta_no]["musteri_ad"] == "Gizli Kişi" and liste[yeni_no]["adres"] == "Gizli sokak 1"
    # Saklama süresi 30 güne inince 40 günlük de anonimleşir.
    await istemci.put(f"{Y}/{m['id']}", json={"saklama_gun": 30}, headers=yonetici_basligi)
    liste = {o["siparis_no"]: o for o in (await istemci.get(f"{Y}/{m['id']}/siparisler", headers=yonetici_basligi)).json()["items"]}
    assert liste[orta_no]["anonim"] is True and liste[orta_no]["musteri_ad"] is None
    assert liste[yeni_no]["anonim"] is False
    # Kişisel veri denetim kaydına hiç kopyalanmadı.
    from models.audit_log import AuditLog

    sizinti = (await db_oturumu.execute(select(AuditLog).where(AuditLog.tablo == "menu_siparisleri"))).scalars().all()
    assert sizinti == []


async def test_analitik_bot_sayilmaz_ham_ip_yok(istemci, yonetici_basligi, db_oturumu):
    m, _, latte, cay = await _kurulum(istemci, yonetici_basligi)
    slug = m["slug"]
    await istemci.get(f"{A}/{slug}", headers=_ziyaretci("203.0.113.1"))
    await istemci.get(f"{A}/{slug}", headers=_ziyaretci("203.0.113.1"))
    await istemci.get(f"{A}/{slug}", headers=_ziyaretci("203.0.113.2"))
    await istemci.get(f"{A}/{slug}", headers=_ziyaretci("203.0.113.3", "WhatsApp/2.23.20.0 A"))
    await istemci.get(f"{A}/{slug}", headers=_ziyaretci("203.0.113.4", "Googlebot/2.1 (+http://www.google.com/bot.html)"))
    await istemci.get(f"{A}/{slug}/ozet", headers=_ziyaretci("203.0.113.5"))  # özet sayılmaz
    for _ in range(3):
        await istemci.post(f"{A}/{slug}/olay", json={"tur": "urun", "urun_id": latte["id"]}, headers=_ziyaretci("203.0.113.1"))
    await istemci.post(f"{A}/{slug}/olay", json={"tur": "urun", "urun_id": cay["id"]}, headers=_ziyaretci("203.0.113.2"))
    await istemci.post(f"{A}/{slug}/olay", json={"tur": "sepet", "urun_id": latte["id"]}, headers=_ziyaretci("203.0.113.1"))
    y = await istemci.post(f"{A}/{slug}/olay", json={"tur": "goruntuleme", "urun_id": latte["id"]})
    assert y.status_code == 400  # görüntülenme/sipariş istemciden yazılamaz
    y = await istemci.post(f"{A}/{slug}/olay", json={"tur": "urun", "urun_id": 999999})
    assert y.status_code == 404
    await istemci.post(f"{A}/{slug}/siparis", json={"kalemler": [{"urun_id": cay["id"], "adet": 1}], "teslimat": "gel_al", "ad": "A"},
                       headers=_ziyaretci("203.0.113.1"))
    a = (await istemci.get(f"{Y}/{m['id']}/analiz?gun=7", headers=yonetici_basligi)).json()
    assert (a["goruntuleme"], a["tekil"], a["bot"]) == (3, 2, 2)
    assert a["urun_goruntuleme"] == 4 and a["sepete_ekleme"] == 1 and a["siparis"] == 1 and a["siparis_tutari"] == 20.0
    assert a["en_cok_bakilan"][0] == {"urun_id": latte["id"], "ad": "Latte", "goruntuleme": 3, "sepet": 1}
    assert len(a["gunluk"]) == 7 and a["gunluk"][-1]["goruntuleme"] == 3 and a["gunluk"][-1]["tekil"] == 2
    from models.qr_menu import MenuOlaylari

    satirlar = (await db_oturumu.execute(select(MenuOlaylari).where(MenuOlaylari.magaza_id == m["id"]))).scalars().all()
    for satir in satirlar:
        assert "203.0.113" not in satir.ip_ozeti and len(satir.ip_ozeti) == 64
    assert not hasattr(MenuOlaylari, "user_agent") and not hasattr(MenuOlaylari, "ip")


# ---------------------------------------------------------------------------
# Görsel, QR, CSV, çeviri, silme
# ---------------------------------------------------------------------------
async def test_gorsel_yukleme_webp_ve_baglama(istemci, yonetici_basligi):
    m, k, latte, _ = await _kurulum(istemci, yonetici_basligi)
    y = await istemci.post(f"{Y}/{m['id']}/gorsel", files={"dosya": ("foto.png", io.BytesIO(_png((2000, 1500))), "image/png")},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    g = y.json()
    assert (g["genislik"], g["yukseklik"]) == (1200, 900) and g["b"].endswith("?b=b") and g["k"].endswith("?b=k")
    for boy, en in (("b", 1200), ("k", 480)):
        r = await istemci.get(f"/api/v1/menu-gorsel/{g['anahtar']}?b={boy}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
        assert r.content[:4] == b"RIFF" and r.content[8:12] == b"WEBP"
        assert "immutable" in r.headers["cache-control"]
        from PIL import Image

        assert Image.open(io.BytesIO(r.content)).width == en
    assert (await istemci.get(f"/api/v1/menu-gorsel/{g['anahtar']}?b=x")).status_code == 404
    assert (await istemci.get("/api/v1/menu-gorsel/yok")).status_code == 404
    y = await istemci.put(f"{Y}/{m['id']}/urunler/{latte['id']}", json={"gorsel": g["anahtar"]}, headers=yonetici_basligi)
    assert y.json()["gorsel"]["genislik"] == 1200
    # GIF reddedilir, bozuk dosya reddedilir.
    y = await istemci.post(f"{Y}/{m['id']}/gorsel", files={"dosya": ("a.gif", io.BytesIO(_png(bicim="GIF")), "image/gif")},
                           headers=yonetici_basligi)
    assert y.status_code == 415 and _kod(y) == "gorsel_turu"
    y = await istemci.post(f"{Y}/{m['id']}/gorsel", files={"dosya": ("a.png", io.BytesIO(b"\x89PNG bozuk"), "image/png")},
                           headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "gorsel_gecersiz"
    # Başka mağazanın görseli bağlanamaz.
    m2, _, latte2, _ = await _kurulum(istemci, yonetici_basligi, ad="Diğer")
    y = await istemci.put(f"{Y}/{m2['id']}/urunler/{latte2['id']}", json={"gorsel": g["anahtar"]}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "gorsel_gecersiz"
    # Ürün silinince görsel de silinir.
    await istemci.delete(f"{Y}/{m['id']}/urunler/{latte['id']}", headers=yonetici_basligi)
    assert (await istemci.get(f"/api/v1/menu-gorsel/{g['anahtar']}")).status_code == 404


async def test_menu_ve_masa_qr_zip(istemci, yonetici_basligi):
    m, _, _, _ = await _kurulum(istemci, yonetici_basligi)
    y = await istemci.get(f"{Y}/{m['id']}/qr?bicim=png", headers=yonetici_basligi)
    assert y.status_code == 200 and y.content[:8] == PNG_IMZA
    y = await istemci.get(f"{Y}/{m['id']}/qr?bicim=svg&masa=7", headers=yonetici_basligi)
    assert y.status_code == 200 and y.text.startswith("<svg") and "masa-7" in y.headers["content-disposition"]
    y = await istemci.post(f"{Y}/{m['id']}/masa-qr", json={"bas": 1, "bit": 3, "bicim": "png"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.headers["content-type"] == "application/zip"
    arsiv = zipfile.ZipFile(io.BytesIO(y.content))
    assert arsiv.namelist() == ["masa-001.png", "masa-002.png", "masa-003.png"]
    assert all(arsiv.read(ad)[:8] == PNG_IMZA for ad in arsiv.namelist())
    # QR'ın içeriği masa numaralı menü adresi.
    import segno  # noqa: F401
    from services import dinamik_qr as qr

    beklenen = qr.svg_ciz(f"https://mehmetkuru.dev/menu/{m['slug']}?masa=2", {**qr.VARSAYILAN_TASARIM, "boyut": 768}).veri
    y = await istemci.post(f"{Y}/{m['id']}/masa-qr", json={"bas": 2, "bit": 2, "bicim": "svg"}, headers=yonetici_basligi)
    assert zipfile.ZipFile(io.BytesIO(y.content)).read("masa-002.svg") == beklenen
    for govde in ({"bas": 5, "bit": 2}, {"bas": 1, "bit": 300}, {"bas": 0, "bit": 3}, {"bas": 1, "bit": 2, "bicim": "gif"}):
        assert (await istemci.post(f"{Y}/{m['id']}/masa-qr", json=govde, headers=yonetici_basligi)).status_code == 400, govde


async def test_csv_ice_aktarma(istemci, yonetici_basligi):
    e = await _musteri(istemci, yonetici_basligi, urun_siniri=4)
    m, _, _, _ = await _kurulum(istemci, _b(e), M)  # 2 ürün var
    csv_metni = (
        "kategori;ad;aciklama;fiyat;etiketler\n"
        "İçecekler;Ayran;Köpüklü;15,00;vejetaryen\n"
        "Tatlılar;Baklava;Fıstıklı;120;yeni, çok satan\n"
        "Tatlılar;Kazandibi;;fiyatsız;\n"
        "Tatlılar;Sütlaç;;55;organik\n"
        ";Adsız kategori;;10;\n"
        "Tatlılar;Künefe;;95;\n"
    ).encode("utf-8")
    y = await istemci.post(f"{M}/{m['id']}/ice-aktar/onizleme", files={"dosya": ("menu.csv", io.BytesIO(csv_metni), "text/csv")},
                           headers=_b(e))
    assert y.status_code == 200, y.text
    o = y.json()
    assert (o["toplam"], o["gecerli"], o["hatali"], o["kalan_hak"]) == (6, 3, 3, 2)
    assert o["yeni_kategoriler"] == ["Tatlılar"]
    hatalar = {x["satir"]: x["hata"]["kod"] for x in o["satirlar"] if not x["gecerli"]}
    assert hatalar == {4: "fiyat_gecersiz", 5: "etiket_gecersiz", 6: "zorunlu"}
    assert o["satirlar"][1]["veri"]["etiketler"] == ["yeni", "cok_satan"] and o["satirlar"][1]["veri"]["fiyat"] == 120.0
    gecerli = [x for x in o["satirlar"] if x["gecerli"]]
    y = await istemci.post(f"{M}/{m['id']}/ice-aktar", json={"satirlar": gecerli}, headers=_b(e))
    assert y.status_code == 200, y.text
    sonuc = y.json()
    assert sonuc["olusturulan"] == 2 and sonuc["yeni_kategori"] == 1 and sonuc["hatalar"][0]["kod"] == "urun_siniri"
    icerik = (await istemci.get(f"{M}/{m['id']}/icerik", headers=_b(e))).json()
    assert [k["ad"] for k in icerik["kategoriler"]] == ["İçecekler", "Tatlılar"] and icerik["urun_sayisi"] == 4
    assert {u["ad"]: u["fiyat"] for u in icerik["urunler"]}["Baklava"] == 120.0
    # Başlık eksik / boş / büyük dosya.
    for govde, kod in ((b"isim,fiyat\nx,1\n", "baslik_eksik"), (b"", "dosya_bos")):
        y = await istemci.post(f"{M}/{m['id']}/ice-aktar/onizleme", files={"dosya": ("a.csv", io.BytesIO(govde), "text/csv")},
                               headers=_b(e))
        assert y.status_code == 400 and _kod(y) == kod
    y = await istemci.post(f"{M}/{m['id']}/ice-aktar/onizleme",
                           files={"dosya": ("a.csv", io.BytesIO(b"kategori,ad,fiyat\n" + b"x" * 600_000), "text/csv")}, headers=_b(e))
    assert y.status_code == 413


async def test_ai_ceviri_anahtarsiz_zarifce_kapali(istemci, yonetici_basligi):
    m, _, _, _ = await _kurulum(istemci, yonetici_basligi)
    await istemci.put(f"{Y}/{m['id']}", json={"ek_diller": ["en"]}, headers=yonetici_basligi)
    assert (await istemci.get(f"{Y}/meta", headers=yonetici_basligi)).json()["ai_ceviri"] is False
    y = await istemci.post(f"{Y}/{m['id']}/ceviri", json={"tur": "magaza"}, headers=yonetici_basligi)
    assert y.status_code == 503 and _kod(y) == "ai_kapali"


async def test_ai_ceviri_sahte_saglayici_ve_butce(istemci, yonetici_basligi, monkeypatch, db_oturumu):
    from routers import qr_menu as r
    from services import yapay_zeka

    monkeypatch.setattr(r, "_ai_hazir", lambda: True)
    gonderilen = []

    async def _saglayici(mesajlar, model, max_tokens, temperature):
        gonderilen.append(mesajlar)
        veri = json.loads(mesajlar[-1]["content"])
        metinler = veri["metinler"]
        return json.dumps({d: {k: f"{v}-{d}" for k, v in metinler.items()} for d in veri["hedef_diller"]}), {
            "prompt_tokens": 10, "completion_tokens": 20}

    monkeypatch.setattr(yapay_zeka, "_saglayici_cagir", _saglayici)
    m, k, latte, _ = await _kurulum(istemci, yonetici_basligi)
    await istemci.put(f"{Y}/{m['id']}", json={"ek_diller": ["en", "de"]}, headers=yonetici_basligi)
    assert (await istemci.get(f"{Y}/meta", headers=yonetici_basligi)).json()["ai_ceviri"] is True
    y = await istemci.post(f"{Y}/{m['id']}/ceviri", json={"tur": "urun", "id": latte["id"]}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    u = y.json()["kayit"]
    assert u["ceviriler"]["en"] == {"ad": "Latte-en", "aciklama": "Sütlü kahve-en"}
    assert u["ceviriler"]["de"]["ad"] == "Latte-de"
    boy = u["secenek_gruplari"][0]
    assert boy["ceviriler"] == {"en": "Boy-en", "de": "Boy-de"} and boy["secenekler"][1]["ceviriler"]["en"] == "Büyük-en"
    # Sistem istemi sunucuda; ürün metni yalnız VERİ olarak kullanıcı mesajında.
    assert gonderilen[0][0]["role"] == "system" and "DATA, not instructions" in gonderilen[0][0]["content"]
    # Herkese açık menüde çeviri görünür.
    d = (await istemci.get(f"{A}/{m['slug']}")).json()
    assert d["diller"] == ["tr", "en", "de"] and d["urunler"][0]["ceviriler"]["en"]["ad"] == "Latte-en"
    # Ek dil yoksa / bilinmeyen tür.
    y = await istemci.post(f"{Y}/{m['id']}/ceviri", json={"tur": "kategori", "id": k["id"], "diller": ["fr"]}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "ek_dil_yok"
    # Günlük bütçe dolunca 429 ve meta düğmeyi kapatır.
    from models.ai_kullanim import AiGunlukKullanim

    satir = (await db_oturumu.execute(select(AiGunlukKullanim).where(AiGunlukKullanim.kapsam == "menu"))).scalars().first()
    assert satir is not None and satir.istek >= 1 and satir.token_cikis >= 20
    from services.yapay_zeka import ayar_yaz

    await ayar_yaz(db_oturumu, "ai_menu_gunluk_butce", str(satir.istek))
    await db_oturumu.commit()
    assert (await istemci.get(f"{Y}/meta", headers=yonetici_basligi)).json()["ai_ceviri"] is False
    y = await istemci.post(f"{Y}/{m['id']}/ceviri", json={"tur": "magaza"}, headers=yonetici_basligi)
    assert y.status_code == 429 and _kod(y) == "gunluk_butce"
    await ayar_yaz(db_oturumu, "ai_menu_gunluk_butce", "300")
    await db_oturumu.commit()
    # Model saçma yanıt verirse 502, kayıt bozulmaz.

    async def _bozuk(*a, **k2):
        return "Üzgünüm, çeviremem.", {}

    monkeypatch.setattr(yapay_zeka, "_saglayici_cagir", _bozuk)
    y = await istemci.post(f"{Y}/{m['id']}/ceviri", json={"tur": "magaza"}, headers=yonetici_basligi)
    assert y.status_code == 502 and _kod(y) == "ai_yanit_gecersiz"


async def test_silme_cop_kutusuna_ve_siparisler_anonim(istemci, yonetici_basligi, db_oturumu):
    e = await _musteri(istemci, yonetici_basligi)
    m, _, _, cay = await _kurulum(istemci, _b(e), M)
    await istemci.post(f"{M}/{m['id']}/kuponlar", json={"kod": "SIL", "tur": "yuzde", "deger": 5}, headers=_b(e))
    await istemci.post(f"{A}/{m['slug']}/siparis", json={"kalemler": [{"urun_id": cay["id"], "adet": 1}], "teslimat": "gel_al",
                                                        "ad": "Silinecek Kişi"}, headers=_ziyaretci())
    y = await istemci.delete(f"{M}/{m['id']}", headers=_b(e))
    assert y.status_code == 200
    assert (await istemci.get(f"{A}/{m['slug']}")).status_code == 404
    from models.cop_kutusu import CopKutusu
    from models.qr_menu import MenuSiparisleri

    satirlar = (await db_oturumu.execute(select(CopKutusu).where(CopKutusu.tablo.like("menu_%")))).scalars().all()
    tablolar = {(c.tablo, c.kayit_id) for c in satirlar}
    assert ("menu_magazalari", str(m["id"])) in tablolar
    assert {"menu_kategorileri", "menu_urunleri", "menu_kuponlari"} <= {t for t, _ in tablolar}
    ana = next(c for c in satirlar if c.tablo == "menu_magazalari" and c.kayit_id == str(m["id"]))
    assert ana.sahip_email == e
    siparisler = (await db_oturumu.execute(select(MenuSiparisleri).where(MenuSiparisleri.magaza_id == m["id"]))).scalars().all()
    assert siparisler and all(o.anonim and o.musteri_ad is None for o in siparisler)
    # Müşteri "Silinenler"de görür ve geri alır.
    cop = (await istemci.get("/api/v1/cop-kutum", headers=_b(e))).json()
    kayit = next(x for x in (cop.get("items") if isinstance(cop, dict) else cop) if x["tablo"] == "menu_magazalari")
    y = await istemci.post(f"/api/v1/cop-kutum/{kayit['id']}/geri-al", headers=_b(e))
    assert y.status_code == 200, y.text
    icerik = (await istemci.get(f"{M}/{m['id']}/icerik", headers=_b(e))).json()
    assert icerik["urun_sayisi"] == 2 and (await istemci.get(f"{A}/{m['slug']}")).status_code == 200


async def test_ekip_uyesi_menu_iznine_gore(istemci, yonetici_basligi, db_oturumu):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as he

    sahip = await _musteri(istemci, yonetici_basligi)
    m = await _magaza(istemci, _b(sahip), M)
    uye, izinsiz = _e("uye"), _e("izinsiz")
    for kisi, izinler in ((uye, list(he.ROL_VARSAYILAN["uye"])), (izinsiz, ["projeler"])):
        db_oturumu.add(HesapUyeleri(hesap_email=sahip, uye_email=kisi, rol="uye", izinler=json.dumps(izinler), durum="aktif",
                                    olusturma=he.simdi()))
    await db_oturumu.commit()
    he.onbellegi_temizle()
    assert "menu" in he.ROL_VARSAYILAN["uye"] and "menu" in he.IZINLER
    y = await istemci.get(M, headers=_b(uye, sahip))
    assert y.status_code == 200 and [x["id"] for x in y.json()["items"]] == [m["id"]]
    y = await istemci.get(M, headers=_b(izinsiz, sahip))
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"
    # Faz 4Q–4M arası kaydedilmiş varsayılan üye listesi yeni izni kendiliğinden alır.
    eski = ["projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar", "asistanlar", "qr"]
    assert "menu" in he.izinleri_coz(json.dumps(eski), "uye")
