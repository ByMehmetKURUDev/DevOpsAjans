"""Faz 4L — Marka teması (white-label).

Kapsam: yetki (oturumsuz 401, modül kapalı 403, yönetici uçları, müşteri yalnız kendi
markası, ekipte üye yazamaz / hesap yöneticisi yazar, başka hesaba başlıkla erişim yok);
renk biçimi ve alan doğrulaması; WCAG kontrast hesabı (oran, otomatik yazı rengi, öneri);
logo (PNG → WebP, boyut/tür sınırı, SVG reddi — gizlenmiş SVG dahil, PNG sürümü, kaldırma);
`rozet_gizle` yalnız yönetici (modül ayarı); herkese açık uçların `marka` alanı (kartvizit,
yorum, QR menü, randevu; sayfanın kendi teması öncelikli; sahip e-postası sızmıyor); e-posta
HTML başlığı (kaçış, yalnız modül açıkken).

Kontrast eşiği WCAG 2.1 Başarı Ölçütü 1.4.3 "Contrast (Minimum)" — AA, normal metin 4.5:1;
göreli parlaklık ve oran tanımları WCAG 2.1 sözlüğündeki formüller.
"""

import io
import json
import uuid

import pytest

from conftest import jeton_uret

M = "/api/v1/markam"
Y = "/api/v1/marka/yonetim"
A = "/api/v1/marka"
MODUL = "/api/v1/moduller"


def _e(on: str = "marka") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@marka.dev"


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


def _png(boyut=(800, 400), renk=(20, 120, 220, 255), bicim="PNG") -> bytes:
    from PIL import Image

    g = Image.new("RGBA" if bicim == "PNG" else "RGB", boyut, renk if bicim == "PNG" else renk[:3])
    c = io.BytesIO()
    g.save(c, format=bicim)
    return c.getvalue()


SVG = b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(1)</script></svg>'


@pytest.fixture(autouse=True)
def _temiz():
    from routers import marka
    from services import hesap_ekibi

    marka.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    yield
    marka.hiz_sinirlarini_temizle()


async def _modul(istemci, yonetici_basligi, eposta, anahtar="marka_temasi", acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/{anahtar}", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _logo(istemci, basliklar, veri=None, ad="logo.png", tip="image/png", yol=f"{M}/logo"):
    return await istemci.post(yol, files={"dosya": (ad, veri if veri is not None else _png(), tip)}, headers=basliklar)


# ---------------------------------------------------------------------------
# Kontrast (saf fonksiyonlar)
# ---------------------------------------------------------------------------
def test_kontrast_wcag_formulu():
    from services import marka as m

    # WCAG: siyah/beyaz 21:1, aynı renk 1:1; #777 beyazda ~4.48 (AA'nın hemen altı — bilinen örnek).
    assert round(m.kontrast("#ffffff", "#000000"), 2) == 21.0
    assert m.kontrast("#336699", "#336699") == pytest.approx(1.0)
    assert round(m.kontrast("#777777", "#ffffff"), 2) == 4.48
    assert round(m.kontrast("#767676", "#ffffff"), 2) == 4.54
    assert m.kontrast("#123456", "#abcdef") == pytest.approx(m.kontrast("#abcdef", "#123456"))
    # Otomatik yazı rengi: koyu zeminde beyaz, açık zeminde koyu.
    assert m.yazi_rengi("#1d4ed8") == "#ffffff"
    assert m.yazi_rengi("#facc15") == "#111111"
    assert m.yazi_rengi("#ffffff") == "#111111"


def test_denetim_yetersizde_uyari_ve_oneri():
    from services import marka as m

    iyi = m.denetim({**m.VARSAYILAN, "ana_renk": "#1d4ed8", "vurgu_rengi": "#b45309", "zemin": "acik"})
    assert iyi["ana"]["yeterli"] is True and iyi["ana"]["oneri"] is None and iyi["ana"]["yazi"] == "#ffffff"
    assert iyi["vurgu"]["yeterli"] is True and iyi["esik"] == 4.5
    # Orta tonlu renk: ne beyaz ne #111 4.5'e ulaşıyor → uyarı + öneri (öneri eşiği geçiyor, ton korunuyor).
    orta = m.denetim({**m.VARSAYILAN, "ana_renk": "#8b5cf6", "vurgu_rengi": "#fde68a", "zemin": "acik"})
    assert orta["ana"]["yeterli"] is False and orta["ana"]["oran"] < 4.5
    oneri = orta["ana"]["oneri"]
    assert oneri and m.RENK_DESENI.match(oneri) and m.kontrast(oneri, m.yazi_rengi(oneri)) >= 4.5
    # Açık sarı vurgu açık zeminde okunmuyor → koyulaştırılmış öneri.
    assert orta["vurgu"]["yeterli"] is False
    v = orta["vurgu"]["oneri"]
    assert v and m.kontrast(v, m.ZEMIN_RENKLERI["acik"]["zemin"]) >= 4.5
    # Koyu zeminde koyu vurgu → açılmış öneri.
    koyu = m.denetim({**m.VARSAYILAN, "vurgu_rengi": "#1e1b4b", "zemin": "koyu"})
    assert koyu["vurgu"]["yeterli"] is False
    assert m.goreli_parlaklik(koyu["vurgu"]["oneri"]) > m.goreli_parlaklik("#1e1b4b")


def test_dogrulama_saf():
    from services import marka as m

    assert m.dogrula({"ana_renk": "#ABC"})["ana_renk"] == "#aabbcc"
    assert m.dogrula({"ana_renk": " #12AB9F "})["ana_renk"] == "#12ab9f"
    for kotu in ("red", "#12345", "#gggggg", "rgb(1,2,3)", "", None, "#1234567", "url(javascript:alert(1))"):
        with pytest.raises(m.MarkaHatasi) as h:
            m.dogrula({"ana_renk": kotu})
        assert h.value.kod == "renk_gecersiz" and h.value.alan == "ana_renk"
    for alan, kotu in (("zemin", "gri"), ("kose", "oval"), ("yazi_tipi", "comic_sans"), ("yazi_tipi", "https://x/f.woff2")):
        with pytest.raises(m.MarkaHatasi) as h:
            m.dogrula({alan: kotu})
        assert h.value.kod == f"{alan}_gecersiz"
    with pytest.raises(m.MarkaHatasi) as h:
        m.dogrula({"css": "body{}"})
    assert h.value.kod == "bilinmeyen_alan"
    for kotu in ("<script>", "a" * 81, "x\x00y"):
        with pytest.raises(m.MarkaHatasi):
            m.dogrula({"ad": kotu})


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------
async def test_oturumsuz_modul_kapali_ve_yonetici_uclari(istemci, yonetici_basligi):
    e = _e()
    assert (await istemci.get(M)).status_code == 401
    assert (await istemci.put(M, json={"ana_renk": "#000000"})).status_code == 401
    y = await istemci.get(M, headers=_b(e))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    # Yönetici uçları müşteriye kapalı.
    assert (await istemci.get(f"{Y}/{e}", headers=_b(e))).status_code == 403
    assert (await istemci.put(f"{Y}/{e}", json={"ana_renk": "#000000"}, headers=_b(e))).status_code == 403
    assert (await istemci.get(f"{Y}/{e}")).status_code == 401
    await _modul(istemci, yonetici_basligi, e)
    y = await istemci.get(M, headers=_b(e))
    assert y.status_code == 200
    d = y.json()
    assert d["kayitli"] is False and d["ana_renk"] == "#7c3aed" and d["modul_acik"] is True and d["rozet_gizle"] is False


async def test_musteri_yalniz_kendi_markasi(istemci, yonetici_basligi):
    a, b = _e("a"), _e("b")
    for x in (a, b):
        await _modul(istemci, yonetici_basligi, x)
    y = await istemci.put(M, json={"ad": "A Kafe", "ana_renk": "#0f766e", "zemin": "koyu"}, headers=_b(a))
    assert y.status_code == 200, y.text
    assert y.json()["hesap_email"] == a and y.json()["ana_renk"] == "#0f766e"
    # B kendi (boş) markasını görür; A'nınkine başlıkla erişemez.
    yb = await istemci.get(M, headers=_b(b))
    assert yb.json()["kayitli"] is False and yb.json()["ana_renk"] == "#7c3aed"
    y = await istemci.get(M, headers=_b(b, hesap=a))
    assert y.status_code == 403 and _kod(y) == "hesap_uyesi_degil"
    y = await istemci.put(M, json={"ana_renk": "#000000"}, headers=_b(b, hesap=a))
    assert y.status_code == 403
    assert (await istemci.get(M, headers=_b(a))).json()["ana_renk"] == "#0f766e"
    # Yönetici her müşterinin markasını görür ve düzenler.
    yy = await istemci.get(f"{Y}/{a}", headers=yonetici_basligi)
    assert yy.status_code == 200 and yy.json()["ad"] == "A Kafe"
    yy = await istemci.put(f"{Y}/{a}", json={"vurgu_rengi": "#b45309"}, headers=yonetici_basligi)
    assert yy.status_code == 200 and yy.json()["vurgu_rengi"] == "#b45309" and yy.json()["ana_renk"] == "#0f766e"
    assert (await istemci.get(f"{Y}/gecersiz-adres", headers=yonetici_basligi)).status_code == 400


async def test_ekipte_uye_okur_yazamaz_hesap_yoneticisi_yazar(istemci, yonetici_basligi, db_oturumu):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as he

    sahip, uye, hy = _e("sahip"), _e("uye"), _e("hy")
    await _modul(istemci, yonetici_basligi, sahip)
    for kisi, rol in ((uye, "uye"), (hy, "yonetici")):
        db_oturumu.add(HesapUyeleri(hesap_email=sahip, uye_email=kisi, rol=rol,
                                    izinler=json.dumps(list(he.ROL_VARSAYILAN[rol])), durum="aktif", olusturma=he.simdi()))
    await db_oturumu.commit()
    he.onbellegi_temizle()
    assert (await istemci.get(M, headers=_b(uye, hesap=sahip))).status_code == 200
    y = await istemci.put(M, json={"ana_renk": "#000000"}, headers=_b(uye, hesap=sahip))
    assert y.status_code == 403 and _kod(y) == "marka_yetkisi_yok"
    assert (await _logo(istemci, _b(uye, hesap=sahip))).status_code == 403
    y = await istemci.put(M, json={"ana_renk": "#1d4ed8"}, headers=_b(hy, hesap=sahip))
    assert y.status_code == 200 and y.json()["hesap_email"] == sahip


async def test_alan_dogrulama_uctan(istemci, yonetici_basligi):
    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    for govde, kod in (
        ({"ana_renk": "kırmızı"}, "renk_gecersiz"),
        ({"vurgu_rengi": "#12"}, "renk_gecersiz"),
        ({"zemin": "seffaf"}, "zemin_gecersiz"),
        ({"kose": "daire"}, "kose_gecersiz"),
        ({"yazi_tipi": "Roboto"}, "yazi_tipi_gecersiz"),
        ({"logo_url": "https://kotu.example/x.svg"}, "bilinmeyen_alan"),
    ):
        y = await istemci.put(M, json=govde, headers=_b(e))
        assert y.status_code == 400 and _kod(y) == kod, (govde, y.text)
    y = await istemci.put(M, json={"ana_renk": "#8b5cf6", "vurgu_rengi": "#FDE68A"}, headers=_b(e))
    assert y.status_code == 200
    d = y.json()
    assert d["vurgu_rengi"] == "#fde68a"
    # Kayıt engellenmiyor ama denetim uyarı + öneri döndürüyor.
    assert d["denetim"]["ana"]["yeterli"] is False and d["denetim"]["ana"]["oneri"]
    assert d["denetim"]["vurgu"]["yeterli"] is False and d["denetim"]["vurgu"]["oneri"]


# ---------------------------------------------------------------------------
# Rozet: yalnız yönetici
# ---------------------------------------------------------------------------
async def test_rozet_gizle_musteri_degistiremez(istemci, yonetici_basligi):
    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    y = await istemci.put(M, json={"rozet_gizle": True}, headers=_b(e))
    assert y.status_code == 403 and _kod(y) == "yalniz_yonetici"
    y = await istemci.put(f"{MODUL}/musteri/{e}/marka_temasi", json={"ayarlar": {"rozet_gizle": True}}, headers=_b(e))
    assert y.status_code == 403
    assert (await istemci.get(M, headers=_b(e))).json()["rozet_gizle"] is False
    # Yönetici: marka ucundan değil, modül ayarından.
    y = await istemci.put(f"{Y}/{e}", json={"rozet_gizle": True}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "modul_ayari_kullanin"
    await _modul(istemci, yonetici_basligi, e, rozet_gizle=True)
    assert (await istemci.get(M, headers=_b(e))).json()["rozet_gizle"] is True
    # Geçersiz tür reddediliyor (bool).
    y = await istemci.put(f"{MODUL}/musteri/{e}/marka_temasi", json={"ayarlar": {"rozet_gizle": "evet"}}, headers=yonetici_basligi)
    assert y.status_code == 400


def test_modul_kaydi():
    from core import moduller as manifest
    from core import sektor_paketleri as sp

    m = manifest.modul("marka_temasi")
    assert m is not None and m.kategori == "dijital_kimlik" and m.varsayilan_acik is False and m.paketler == ()
    assert m.musteriye_gorunur and m.musteri_sekmesi is None and m.yonetici_sekmesi is None
    assert m.varsayilan_ayarlar() == {"rozet_gizle": False}
    assert all("marka_temasi" not in p.moduller for p in sp.SEKTOR_PAKETLERI)
    assert manifest.manifest_hatalari() == []


# ---------------------------------------------------------------------------
# Logo
# ---------------------------------------------------------------------------
async def test_logo_yukleme_donusturme_ve_sunma(istemci, yonetici_basligi):
    from PIL import Image

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    y = await _logo(istemci, _b(e), _png((1600, 400), (20, 120, 220, 128)))
    assert y.status_code == 200, y.text
    logo = y.json()["logo"]
    assert logo["url"].startswith("/api/v1/marka/logo/") and logo["url"].endswith(".webp")
    assert logo["genislik"] == 512 and logo["yukseklik"] == 128
    g = await istemci.get(logo["url"])
    assert g.status_code == 200 and g.headers["content-type"] == "image/webp"
    assert "immutable" in g.headers["cache-control"] and g.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(g.content)) as im:
        assert im.format == "WEBP" and im.mode == "RGBA"  # saydamlık korunuyor
    p = await istemci.get(logo["url"].replace(".webp", ".png"))
    assert p.status_code == 200 and p.headers["content-type"] == "image/png" and p.content[:8] == b"\x89PNG\r\n\x1a\n"
    # Değiştirince eski adres düşer; kaldırınca yenisi de.
    y2 = await _logo(istemci, _b(e), _png((300, 300), bicim="JPEG"), ad="logo.jpg", tip="image/jpeg")
    assert y2.status_code == 200
    assert (await istemci.get(logo["url"])).status_code == 404
    yeni = y2.json()["logo"]["url"]
    assert (await istemci.get(yeni)).status_code == 200
    y3 = await istemci.delete(f"{M}/logo", headers=_b(e))
    assert y3.status_code == 200 and y3.json()["logo"] is None
    assert (await istemci.get(yeni)).status_code == 404
    for kotu in ("/x.webp", "/../../etc.webp", "/abc.svg", "/" + "a" * 60 + ".webp"):
        assert (await istemci.get(f"{A}/logo{kotu}")).status_code == 404


async def test_logo_tur_boyut_ve_svg_reddi(istemci, yonetici_basligi):
    from services import marka as m

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    b = _b(e)
    # SVG her kılıkta reddediliyor (XSS: betik/olay öznitelikleri).
    for veri, ad, tip in (
        (SVG, "logo.svg", "image/svg+xml"),
        (SVG, "logo.png", "image/png"),  # uzantısı/türü yalan söyleyen SVG
        (b"  <svg xmlns='http://www.w3.org/2000/svg'><circle r='4'/></svg>", "x.png", "application/octet-stream"),
    ):
        y = await _logo(istemci, b, veri, ad, tip)
        assert y.status_code == 415 and _kod(y) == "svg_desteklenmiyor", (ad, y.text)
    y = await _logo(istemci, b, _png(bicim="GIF"), "logo.gif", "image/gif")
    assert y.status_code == 415 and _kod(y) == "logo_bicimi"
    y = await _logo(istemci, b, b"duz metin, gorsel degil", "logo.png")
    assert y.status_code == 415 and _kod(y) == "logo_bicimi"
    y = await _logo(istemci, b, _png((8, 8)))
    assert y.status_code == 400 and _kod(y) == "logo_boyutu"
    y = await _logo(istemci, b, b"\x89PNG\r\n\x1a\n" + b"0" * (m.LOGO_EN_COK_BAYT + 10))
    assert y.status_code == 413 and _kod(y) == "logo_buyuk"
    assert (await istemci.get(M, headers=b)).json()["logo"] is None


async def test_yonetici_logo_ve_sifirlama(istemci, yonetici_basligi):
    e = _e()
    y = await _logo(istemci, yonetici_basligi, yol=f"{Y}/{e}/logo")
    assert y.status_code == 200 and y.json()["logo"] and y.json()["modul_acik"] is False
    url = y.json()["logo"]["url"]
    y = await istemci.delete(f"{Y}/{e}", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["kayitli"] is False and y.json()["logo"] is None
    assert (await istemci.get(url)).status_code == 404


# ---------------------------------------------------------------------------
# Herkese açık uçlar
# ---------------------------------------------------------------------------
async def _kart(istemci, basliklar, **govde):
    govde.setdefault("icerik", {"ad_soyad": "Ayşe Yılmaz", "unvan": "Kurucu"})
    y = await istemci.post("/api/v1/kartvizitlerim", json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def test_kartvizit_acik_ucunda_marka(istemci, yonetici_basligi):
    from routers import kartvizit

    kartvizit.hiz_sinirlarini_temizle()
    e = _e("kart")
    await _modul(istemci, yonetici_basligi, e, "dijital_kartvizit")
    kart = await _kart(istemci, _b(e))
    ozel = await _kart(istemci, _b(e), tema={"sablon": "doga", "renk": "#16a34a", "yazi_tipi": "mono", "kose": "keskin"})

    # Marka modülü kapalı: tema yok, rozet görünür.
    d = (await istemci.get(f"/api/v1/kart/{kart['slug']}")).json()
    assert d["marka"] == {"rozet": True, "tema": None, "sayfa_ozel": False}

    await _modul(istemci, yonetici_basligi, e)
    await istemci.put(M, json={"ad": "Ayşe Ajans", "ana_renk": "#0ea5e9", "zemin": "koyu", "yazi_tipi": "sistem_serif"},
                      headers=_b(e))
    await _logo(istemci, _b(e))
    d = (await istemci.get(f"/api/v1/kart/{kart['slug']}")).json()
    t = d["marka"]["tema"]
    assert d["marka"]["rozet"] is True and d["marka"]["sayfa_ozel"] is False
    assert t["ana"] == "#0ea5e9" and t["ana_yazi"] == "#111111" and t["zemin"] == "koyu" and t["yazi_tipi"] == "sistem_serif"
    assert t["ad"] == "Ayşe Ajans" and t["logo"]["url"].startswith("/api/v1/marka/logo/")
    # Sahibin e-postası herkese açık yanıtta yok.
    assert e not in json.dumps(d)
    # Kartın kendi teması varsa o öncelikli (işaret).
    d2 = (await istemci.get(f"/api/v1/kart/{ozel['slug']}")).json()
    assert d2["marka"]["sayfa_ozel"] is True and d2["tema"]["renk"] == "#16a34a"
    # Paylaşım özeti (Pages Function ilk boyama) aynı bilgiyi taşıyor.
    o = (await istemci.get(f"/api/v1/kart/{kart['slug']}/ozet")).json()
    assert o["marka"]["tema"]["ana"] == "#0ea5e9" and o["tema"]["sablon"] == "gece"
    # Yönetici rozeti gizler.
    await _modul(istemci, yonetici_basligi, e, rozet_gizle=True)
    d = (await istemci.get(f"/api/v1/kart/{kart['slug']}")).json()
    assert d["marka"]["rozet"] is False and d["marka"]["tema"]["ana"] == "#0ea5e9"
    # Modül kapanınca tema düşer, rozet geri gelir (gizleme modülle birlikte).
    await _modul(istemci, yonetici_basligi, e, acik=False)
    d = (await istemci.get(f"/api/v1/kart/{kart['slug']}")).json()
    assert d["marka"] == {"rozet": True, "tema": None, "sayfa_ozel": False}


async def test_ajans_kartinda_tema_yok_rozet_bugunku_gibi(istemci, yonetici_basligi):
    y = await istemci.post("/api/v1/kartvizit/yonetim", json={"icerik": {"ad_soyad": "Ajans Kişi"}}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    d = (await istemci.get(f"/api/v1/kart/{y.json()['slug']}")).json()
    assert d["marka"] == {"rozet": True, "tema": None, "sayfa_ozel": False}


async def test_menu_ve_randevu_acik_uclarinda_marka(istemci, yonetici_basligi):
    e = _e("isletme")
    await _modul(istemci, yonetici_basligi, e, "qr_menu")
    await _modul(istemci, yonetici_basligi, e, "randevu")
    await _modul(istemci, yonetici_basligi, e)
    await istemci.put(M, json={"ana_renk": "#be123c", "vurgu_rengi": "#1d4ed8"}, headers=_b(e))

    mg = await istemci.post("/api/v1/menulerim", json={"ad": "Marka Kafe", "duzen": "menu"}, headers=_b(e))
    assert mg.status_code == 200, mg.text
    slug = mg.json()["slug"]
    d = (await istemci.get(f"/api/v1/menu/{slug}")).json()
    assert d["marka"]["tema"]["ana"] == "#be123c" and d["marka"]["sayfa_ozel"] is False
    o = (await istemci.get(f"/api/v1/menu/{slug}/ozet")).json()
    assert o["marka"]["tema"]["ana"] == "#be123c"
    # Mağaza kendi rengini seçince o öncelikli.
    y = await istemci.put(f"/api/v1/menulerim/{mg.json()['id']}", json={"tema_rengi": "#16a34a"}, headers=_b(e))
    assert y.status_code == 200, y.text
    assert (await istemci.get(f"/api/v1/menu/{slug}")).json()["marka"]["sayfa_ozel"] is True

    rs = await istemci.post("/api/v1/randevularim", json={"baslik": "Marka Danışmanlık"}, headers=_b(e))
    assert rs.status_code == 200, rs.text
    tur = await istemci.post(f"/api/v1/randevularim/{rs.json()['id']}/turler", json={"ad": "Görüşme", "sure_dk": 30},
                             headers=_b(e))
    assert tur.status_code == 200, tur.text
    rslug = rs.json()["slug"]
    d = (await istemci.get(f"/api/v1/randevu/{rslug}")).json()
    assert d["marka"]["tema"]["ana"] == "#be123c" and d["marka"]["rozet"] is True
    d = (await istemci.get(f"/api/v1/randevu/{rslug}/{tur.json()['slug']}")).json()
    assert d["marka"]["tema"]["vurgu"] == "#1d4ed8"
    assert (await istemci.get(f"/api/v1/randevu/{rslug}/ozet")).json()["marka"]["tema"]["ana"] == "#be123c"


async def test_yorum_sayfasinda_marka(istemci, yonetici_basligi):
    e = _e("yorum")
    await _modul(istemci, yonetici_basligi, e, "google_yorum_sayfasi")
    await _modul(istemci, yonetici_basligi, e)
    await istemci.put(M, json={"ana_renk": "#7e22ce"}, headers=_b(e))
    y = await istemci.post("/api/v1/yorum-sayfalarim", json={"isletme_adi": "Marka Kafe", "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4"},
                           headers=_b(e))
    assert y.status_code == 200, y.text
    d = (await istemci.get(f"/api/v1/yorum/{y.json()['slug']}")).json()
    assert d["marka"]["tema"]["ana"] == "#7e22ce" and d["marka"]["sayfa_ozel"] is False


# ---------------------------------------------------------------------------
# E-posta başlığı
# ---------------------------------------------------------------------------
def test_eposta_html_kacisli_ve_markali():
    from services import marka as m

    tema = {"ad": "<b>Kötü</b> & Co", "ana": "#0ea5e9", "ana_yazi": "#111111", "yazi_tipi": "mono",
            "logo": {"url": "/api/v1/marka/logo/AbCdEfGh12345678.webp"}}
    h = m.eposta_html(tema, "Konu <x>", "Merhaba <script>alert(1)</script>\nBağlantı: https://mehmetkuru.dev/randevu/a?b=1&c=2",
                      "https://mehmetkuru.dev")
    assert "<script>" not in h and "&lt;script&gt;" in h and "&lt;b&gt;Kötü&lt;/b&gt; &amp; Co" in h
    assert "background:#0ea5e9" in h and "JetBrains Mono" in h
    assert 'src="https://mehmetkuru.dev/api/v1/marka/logo/AbCdEfGh12345678.png"' in h
    assert '<a href="https://mehmetkuru.dev/randevu/a?b=1&amp;c=2"' in h and "<br>" in h
    # Başka kökten logo adresi asla gömülmüyor; bozuk renk varsayılana düşüyor.
    h2 = m.eposta_html({**tema, "ana": "red;}</style>", "logo": {"url": "https://kotu.example/x.png"}}, "K", "G", "https://mehmetkuru.dev")
    assert "kotu.example" not in h2 and "background:#7c3aed" in h2


async def test_eposta_eki_yalniz_modul_acikken(istemci, yonetici_basligi, db_oturumu):
    from services import marka as m

    e = _e("eposta")
    await _modul(istemci, yonetici_basligi, e)
    await istemci.put(M, json={"ad": "Klinik Bir", "ana_renk": "#be123c"}, headers=_b(e))
    ek = await m.eposta_eki(db_oturumu, e, "Randevunuz onaylandı", "Merhaba", {"ekler": [{"dosya_adi": "a.ics"}]})
    assert ek["ekler"] == [{"dosya_adi": "a.ics"}] and "background:#be123c" in ek["html"] and "Klinik Bir" in ek["html"]
    assert await m.eposta_eki(db_oturumu, None, "K", "G", None) is None  # ajansın kendi e-postası markasız
    await _modul(istemci, yonetici_basligi, e, acik=False)
    assert await m.eposta_eki(db_oturumu, e, "K", "G", {"ekler": []}) == {"ekler": []}


# ---------------------------------------------------------------------------
# Pages Function ilk boyama (Node testi)
# ---------------------------------------------------------------------------
def test_ilk_boyama_fonksiyon_node_testi():
    import shutil
    import subprocess
    from pathlib import Path

    if shutil.which("node") is None:
        pytest.skip("node yok")
    on_yuz = Path(__file__).resolve().parents[3] / "frontend"
    sonuc = subprocess.run(["node", "--test", "scripts/marka-fonksiyonu.test.mjs"], cwd=on_yuz, capture_output=True,
                           text=True, timeout=120)
    assert sonuc.returncode == 0, sonuc.stdout[-3000:] + sonuc.stderr[-2000:]
    assert "# fail 0" in sonuc.stdout


def test_yazi_tipleri_yalniz_yuklu_ya_da_sistem():
    """Yeni font dosyası / dış font yok: yığınlar yalnız sitede yüklü yazı tipleri ve sistem adları."""
    from pathlib import Path

    from services import marka as m

    on_yuz = Path(__file__).resolve().parents[3] / "frontend"
    fontlar = (on_yuz / "src" / "fonts.css").read_text(encoding="utf-8")
    for yigin in m.YAZI_YIGINLARI.values():
        assert "url(" not in yigin and "http" not in yigin
        for ad in ("Plus Jakarta Sans", "JetBrains Mono", "Inter"):
            if ad in yigin:
                assert ad in fontlar, ad
    for dosya in ("src/lib/marka.ts", "functions/_ortak/marka.js", "src/components/marka/marka.css"):
        metin = (on_yuz / dosya).read_text(encoding="utf-8")
        assert "fonts.googleapis" not in metin and "@font-face" not in metin and "@import" not in metin, dosya


async def test_etkinlik_kurs_acik_uclari_ve_bilet_epostasinda_marka(istemci, yonetici_basligi, monkeypatch):
    """Etkinlik / bilet / liste / kurs yanıtlarında `marka`; bilet e-postasının HTML sürümünde marka başlığı
    (metin sürümü aynen; marka yokken HTML eklenmiyor)."""
    from routers import egitim as re_
    from routers import etkinlik as rk
    from services import notify

    rk.hiz_sinirlarini_temizle()
    re_.hiz_sinirlarini_temizle()
    giden = []

    async def _sahte(alici, baslik, govde, ek=None):
        giden.append({"alici": alici, "konu": baslik, "govde": govde, "ek": ek or {}})
        return "sent", "test"

    monkeypatch.setattr(notify, "_eposta_gonder", _sahte)
    e = _e("etkinlik")
    for anahtar in ("etkinlik_bilet", "egitim"):
        await _modul(istemci, yonetici_basligi, e, anahtar)
    y = await istemci.post("/api/v1/etkinliklerim", json={
        "baslik": "Marka Atölyesi", "baslangic": "2026-11-05T10:00:00+03:00", "bitis": "2026-11-05T17:00:00+03:00",
        "mekan_adi": "Kültür Merkezi", "adres": "Moda Cd. 1, Kadıköy / İstanbul"}, headers=_b(e))
    assert y.status_code == 200, y.text
    ev = y.json()
    assert (await istemci.put(f"/api/v1/etkinliklerim/{ev['id']}", json={"durum": "yayinda"}, headers=_b(e))).status_code == 200
    tur = (await istemci.get(f"/api/v1/etkinliklerim/{ev['id']}/bilet-turleri", headers=_b(e))).json()["items"][0]
    ip = {"User-Agent": "Mozilla/5.0 Test", "X-MK-Istemci-IP": "198.51.100.77"}

    # Marka modülü kapalı: tema yok; bilet e-postası markasız (HTML yok).
    assert (await istemci.get(f"/api/v1/etkinlik/{ev['slug']}", headers=ip)).json()["marka"]["tema"] is None
    y = await istemci.post(f"/api/v1/etkinlik/{ev['slug']}/kayit", json={
        "ad": "Ayşe", "eposta": "markasiz@ornek.com", "kalemler": [{"tur_id": tur["id"], "adet": 1}]}, headers=ip)
    assert y.status_code == 200, y.text
    onay = [x for x in giden if x["alici"] == "markasiz@ornek.com"]
    assert onay and "html" not in onay[0]["ek"]

    await _modul(istemci, yonetici_basligi, e)
    await istemci.put(M, json={"ad": "Atölye Evi", "ana_renk": "#0f766e"}, headers=_b(e))
    await _logo(istemci, _b(e))
    d = (await istemci.get(f"/api/v1/etkinlik/{ev['slug']}", headers=ip)).json()
    assert d["marka"]["tema"]["ana"] == "#0f766e" and d["marka"]["sayfa_ozel"] is False
    assert (await istemci.get(f"/api/v1/etkinlik/{ev['slug']}/ozet")).json()["marka"]["tema"]["ana"] == "#0f766e"
    y = await istemci.post(f"/api/v1/etkinlik/{ev['slug']}/kayit", json={
        "ad": "Can", "eposta": "markali@ornek.com", "kalemler": [{"tur_id": tur["id"], "adet": 1}]},
        headers={**ip, "X-MK-Istemci-IP": "198.51.100.78"})
    assert y.status_code == 200, y.text
    bilet = (await istemci.get(f"/api/v1/etkinlik/bilet/{y.json()['jeton']}", headers=ip)).json()
    assert bilet["marka"]["tema"]["ana"] == "#0f766e"
    onay = [x for x in giden if x["alici"] == "markali@ornek.com"]
    assert onay, giden
    html_ = onay[0]["ek"].get("html") or ""
    assert "background:#0f766e" in html_ and "Atölye Evi" in html_ and "/api/v1/marka/logo/" in html_
    assert onay[0]["ek"].get("ekler")  # PDF + ICS ekleri korunuyor
    assert "Marka Atölyesi" in onay[0]["govde"]  # metin sürümü aynı

    # Kurs: kendi rengi varsayılandaysa marka; özel renkte sayfa_ozel.
    y = await istemci.post("/api/v1/egitimim", json={"ad": "Marka Kursu", "mekan": "Merkez", "baslangic_tarihi": "2026-10-20",
                                                     "bitis_tarihi": "2026-12-20"}, headers=_b(e))
    assert y.status_code == 200, y.text
    k = y.json()
    assert (await istemci.put(f"/api/v1/egitimim/{k['id']}", json={"durum": "yayinda"}, headers=_b(e))).status_code == 200
    d = (await istemci.get(f"/api/v1/egitim/kurs/{k['slug']}")).json()
    assert d["marka"]["tema"]["ana"] == "#0f766e" and d["marka"]["sayfa_ozel"] is False
    assert (await istemci.put(f"/api/v1/egitimim/{k['id']}", json={"renk": "#be123c"}, headers=_b(e))).status_code == 200
    assert (await istemci.get(f"/api/v1/egitim/kurs/{k['slug']}")).json()["marka"]["sayfa_ozel"] is True
