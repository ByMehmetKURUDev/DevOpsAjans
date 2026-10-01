"""Faz 4K — Dijital kartvizit + bio link.

Kapsam: slug kuralları (ayrılmış, biçim, Türkçe öneri), değişmez kod (QR) ve
eski slug'ın 30 gün yönlenmesi; parola koruması (yanlış/doğru, jeton,
paylaşım önizlemesinde ve kilitli yanıtta kişisel bilgi sızmaması, parola
değişince eski jetonun düşmesi); vCard içeriği (ek telefonlar, sosyal,
gömülü fotoğraf sınırı); iletişim formu (hız sınırı, bal küpü, imzalı form
jetonu, aydınlatma bağlantısı/zamanı; ajans kartı → CRM adayı, müşteri kartı →
CRM'e karışmadan müşteri listesi + bildirim); müşteri izolasyonu, modül
kapalıyken 403, kart sınırı, modülü kapanan müşterinin kartı 410; analitik
(bot ve önizleyici sayılmaz, ham IP saklanmaz, tıklama hedefi, QR kanalı);
görsel yükleme (WebP'ye çevirme, kare kırpma, EXIF atma, boyut/tür sınırı,
galeri ≤ 8); içerik doğrulaması (javascript: ret, kullanıcı adı → adres);
paylaşım özeti; çöp kutusu (görsellerle birlikte, içerik korunuyor, geri alma).
"""

import io
import json
import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from conftest import jeton_uret

Y = "/api/v1/kartvizit/yonetim"
M = "/api/v1/kartvizitlerim"
A = "/api/v1/kart"
MODUL = "/api/v1/moduller"
MASAUSTU = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
WHATSAPP = "WhatsApp/2.23.20.0 A"
FACEBOOK = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"


def _e(on: str = "kart") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@kart.dev"


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
    kartvizit.hiz_sinirlarini_temizle()
    google_yorum.hiz_sinirlarini_temizle()


async def _modul_ac(istemci, yonetici_basligi, eposta, acik=True, modul="dijital_kartvizit", **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/{modul}", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _musteri(istemci, yonetici_basligi, **ayarlar) -> str:
    e = _e()
    await _modul_ac(istemci, yonetici_basligi, e, **ayarlar)
    return e


def _icerik(**ek) -> dict:
    d = {
        "ad_soyad": "Ayşe Yılmaz",
        "unvan": "Kurucu",
        "sirket": "Örnek Ajans",
        "tanitim": "Web ve mobil ürünler geliştiriyoruz.",
        "telefonlar": [{"etiket": "İş", "numara": "+90 (555) 111 22 33", "tip": "is"}],
        "eposta": "ayse@ornek.com",
        "webler": [{"etiket": "Site", "url": "ornek.com"}],
        "adres": "Moda Cad. 1, Kadıköy, İstanbul",
        "whatsapp": "+90 555 111 22 33",
        "sosyal": [{"platform": "linkedin", "url": "@ayseyilmaz"}, {"platform": "instagram", "url": "https://instagram.com/ayse"}],
        "baglantilar": [{"baslik": "Portfolyo", "url": "https://ornek.com/portfolyo", "simge": "briefcase"}],
        "hizmetler": [{"baslik": "Web sitesi", "aciklama": "Hızlı ve SEO uyumlu"}],
    }
    d.update(ek)
    return d


async def _olustur(istemci, basliklar, yol=Y, **govde):
    govde.setdefault("icerik", _icerik())
    y = await istemci.post(yol, json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


def _png(boyut=(800, 600), renk=(200, 30, 120), bicim="PNG", exif=False) -> bytes:
    from PIL import Image

    g = Image.new("RGB", boyut, renk)
    t = io.BytesIO()
    if exif:
        e = Image.Exif()
        e[0x010F] = "GizliKameraMarkasi"  # Make
        e[0x0112] = 6  # Orientation: 90° döndür
        g.save(t, format="JPEG", exif=e.tobytes())
    else:
        g.save(t, format=bicim)
    return t.getvalue()


async def _gorsel(istemci, basliklar, kart_id, tur, veri=None, yol=Y, ad="g.png", tip="image/png"):
    return await istemci.post(
        f"{yol}/{kart_id}/gorsel", data={"tur": tur}, files={"dosya": (ad, veri or _png(), tip)}, headers=basliklar
    )


def _form_jetonu(sahip_tur: str, sahip_id: int, once: float = 10.0) -> str:
    from services import kartvizit as k

    return k.form_jetonu_uret(sahip_tur, sahip_id, an=time.time() - once)


# ---------------------------------------------------------------------------
# Saf kurallar
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("slug", ["ab", "-ayse", "ayse-", "Ayse Yilmaz", "ay--se", "ayşe", "a" * 51, "a_b", "x/y"])
def test_slug_gecersiz(slug):
    from services import kartvizit as k

    with pytest.raises(k.KartHatasi) as h:
        k.slug_duzelt(slug)
    assert h.value.kod == "slug_gecersiz"


@pytest.mark.parametrize("slug", ["admin", "api", "kart", "yorum", "gorsel", "ozet", "vcard", "mehmetkuru", "login"])
def test_slug_ayrilmis(slug):
    from services import kartvizit as k

    with pytest.raises(k.KartHatasi) as h:
        k.slug_duzelt(slug)
    assert h.value.kod == "slug_ayrilmis"


def test_slug_onerisi_turkce_ve_kod_buyuk_harfli():
    from services import kartvizit as k

    assert k.slug_duzelt("  Ayse-Yilmaz ") == "ayse-yilmaz"
    assert k.slug_oner("Çağrı Işık Öztürk") == "cagri-isik-ozturk"
    assert k.slug_oner("İş & Güç  Ltd. Şti.") == "is-guc-ltd-sti"
    assert k.slug_oner("!!") == ""
    for _ in range(200):
        kod = k.kod_uret()
        assert len(kod) == 7 and any(c.isupper() for c in kod) and k.kod_mu(kod)
        assert not k.SLUG_DESENI.match(kod)  # büyük harf: slug ad alanıyla çakışmaz
    assert not k.kod_mu("abcdefg")


def test_icerik_dogrulama_ve_beyaz_liste():
    from services import kartvizit as k

    a = k.icerik_dogrula(_icerik())
    assert a["sosyal"][0]["url"] == "https://www.linkedin.com/in/ayseyilmaz"
    assert a["webler"][0]["url"] == "https://ornek.com"
    assert a["whatsapp"] == "+905551112233"
    assert len(a["baglantilar"][0]["id"]) == 6
    for kotu in ("javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "ftp://x.com"):
        with pytest.raises(k.KartHatasi) as h:
            k.icerik_dogrula(_icerik(baglantilar=[{"baslik": "x", "url": kotu}]))
        assert h.value.alan == "baglantilar.0.url", kotu
    for kotu in ("javascript:alert(1)", "https://u:p@x.com"):
        with pytest.raises(k.KartHatasi):
            k.icerik_dogrula(_icerik(sosyal=[{"platform": "x", "url": kotu}]))
    assert k.icerik_dogrula(_icerik(baglantilar=[{"baslik": "Ara", "url": "tel:+905551112233"}]))["baglantilar"][0]["url"].startswith("tel:")
    with pytest.raises(k.KartHatasi) as h:
        k.icerik_dogrula(_icerik(ad_soyad="  "))
    assert h.value.kod == "zorunlu"
    with pytest.raises(k.KartHatasi) as h:
        k.icerik_dogrula(_icerik(telefonlar=[{"numara": "abc"}]))
    assert h.value.kod == "telefon_gecersiz"
    with pytest.raises(k.KartHatasi) as h:
        k.icerik_dogrula(_icerik(baglantilar=[{"baslik": "x", "url": "https://a.com"}] * 31))
    assert h.value.kod == "cok_oge"
    with pytest.raises(k.KartHatasi) as h:
        k.icerik_dogrula(_icerik(calisma_saatleri={"goster": True, "gunler": [{"gun": "pzt", "acik": True, "acilis": "25:00", "kapanis": "18:00"}]}))
    assert h.value.kod == "saat_gecersiz"
    saat = k.icerik_dogrula(_icerik(calisma_saatleri={"goster": True, "gunler": [{"gun": "pzt", "acik": True, "acilis": "09:00", "kapanis": "18:00"}]}))
    assert saat["calisma_saatleri"]["gunler"][0] == {"gun": "pzt", "acik": True, "acilis": "09:00", "kapanis": "18:00"}
    assert len(saat["calisma_saatleri"]["gunler"]) == 7
    with pytest.raises(k.KartHatasi):
        k.tema_dogrula({"sablon": "yok"})
    assert k.tema_dogrula({"sablon": "beyaz"})["renk"] == "#2563eb"


def test_gorsel_isleme_webp_kare_exif_ve_sinirlar():
    from PIL import Image

    from services import kartvizit as k

    veri, gen, yuk = k.gorsel_hazirla(_png((1200, 800)), "foto")
    assert (gen, yuk) == (640, 640)
    with Image.open(io.BytesIO(veri)) as g:
        assert g.format == "WEBP"
    veri, gen, yuk = k.gorsel_hazirla(_png((3000, 1000)), "kapak")
    assert gen == 1600 and yuk <= 900
    # EXIF yönü uygulanıyor ve EXIF (kamera markası) atılıyor.
    veri, gen, yuk = k.gorsel_hazirla(_png((400, 200), exif=True), "galeri")
    assert (gen, yuk) == (200, 400)
    assert b"GizliKameraMarkasi" not in veri
    with Image.open(io.BytesIO(veri)) as g:
        assert not g.getexif()
    for kotu, kod in ((b"merhaba", "gorsel_bicimi"), (_png(bicim="GIF"), "gorsel_bicimi"), (_png((10, 10)), "gorsel_boyutu"),
                      (b"x" * (k.GORSEL_EN_COK_BAYT + 1), "gorsel_buyuk")):
        with pytest.raises(k.KartHatasi) as h:
            k.gorsel_hazirla(kotu, "logo")
        assert h.value.kod == kod


def test_jetonlar():
    from services import kartvizit as k

    j = k.erisim_jetonu_uret(5, "ozet-1")
    assert k.erisim_jetonu_gecerli_mi(j, 5, "ozet-1")
    assert not k.erisim_jetonu_gecerli_mi(j, 6, "ozet-1")
    assert not k.erisim_jetonu_gecerli_mi(j, 5, "baska-ozet")  # parola değişti
    assert not k.erisim_jetonu_gecerli_mi(j, 5, "ozet-1", an=time.time() + k.ERISIM_SURE_SN + 5)
    assert not k.erisim_jetonu_gecerli_mi("1.abc", 5, "ozet-1")
    f = k.form_jetonu_uret("kart", 5)
    with pytest.raises(k.KartHatasi) as h:
        k.form_jetonu_dogrula(f, "kart", 5)
    assert h.value.kod == "cok_hizli"
    k.form_jetonu_dogrula(f, "kart", 5, an=time.time() + 3)
    with pytest.raises(k.KartHatasi) as h:
        k.form_jetonu_dogrula(f, "yorum", 5, an=time.time() + 3)
    assert h.value.kod == "form_jetonu"
    with pytest.raises(k.KartHatasi) as h:
        k.form_jetonu_dogrula(f, "kart", 5, an=time.time() + k.FORM_OMRU_SN + 5)
    assert h.value.kod == "form_suresi"


# ---------------------------------------------------------------------------
# Oluşturma, slug, eski slug, kod
# ---------------------------------------------------------------------------
async def test_yetkisiz_401_musteriye_yonetici_ucu_403(istemci):
    assert (await istemci.get(Y)).status_code == 401
    assert (await istemci.get(Y, headers=_b(_e()))).status_code == 403
    assert (await istemci.get(M)).status_code == 401


async def test_olustur_otomatik_slug_ve_cakisma(istemci, yonetici_basligi):
    ad = f"Ayşe Yılmaz {uuid.uuid4().hex[:4]}"
    k1 = await _olustur(istemci, yonetici_basligi, icerik=_icerik(ad_soyad=ad))
    beklenen = ad.lower().replace("ş", "s").replace("ı", "i").replace(" ", "-")
    assert k1["slug"] == beklenen and k1["hesap_email"] is None and k1["duzen"] == "kartvizit"
    assert k1["kart_adresi"] == f"https://mehmetkuru.dev/kart/{beklenen}"
    assert k1["qr_adresi"] == f"https://mehmetkuru.dev/kart/{k1['kod']}"
    k2 = await _olustur(istemci, yonetici_basligi, icerik=_icerik(ad_soyad=ad))
    assert k2["slug"] == f"{beklenen}-2"
    y = await istemci.post(Y, json={"slug": k1["slug"], "icerik": _icerik()}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "slug_kullaniliyor"
    y = await istemci.post(Y, json={"slug": "admin", "icerik": _icerik()}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "slug_ayrilmis"
    u = (await istemci.get(f"{Y}/slug-uygun?slug={k1['slug']}&ad=Ayşe", headers=yonetici_basligi)).json()
    assert u["uygun"] is False and u["kod"] == "slug_kullaniliyor" and u["oneri"].startswith("ayse")
    u = (await istemci.get(f"{Y}/slug-uygun?slug={k1['slug']}&haric_id={k1['id']}", headers=yonetici_basligi)).json()
    assert u["uygun"] is True


async def test_slug_degisince_eski_30_gun_yonlenir_sonra_serbest(istemci, yonetici_basligi, db_oturumu):
    from models.kartvizit import KartvizitEskiSluglar

    eski = f"eski-{uuid.uuid4().hex[:6]}"
    yeni = f"yeni-{uuid.uuid4().hex[:6]}"
    kart = await _olustur(istemci, yonetici_basligi, slug=eski)
    y = await istemci.put(f"{Y}/{kart['id']}", json={"slug": yeni}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["slug"] == yeni
    a = await istemci.get(f"{A}/{eski}", headers=_tarayici())
    assert a.status_code == 200 and a.json() == {"durum": "yonlendir", "yonlendir": yeni}
    assert (await istemci.get(f"{A}/{eski}/ozet")).json()["yonlendir"] == yeni
    # Eski slug 30 gün başka karta verilemez.
    y = await istemci.post(Y, json={"slug": eski, "icerik": _icerik()}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "slug_kullaniliyor"
    # Değişmez kod hâlâ aynı karta gidiyor (QR basılıysa çalışmaya devam eder).
    q = await istemci.get(f"{A}/{kart['kod']}", headers=_tarayici())
    assert q.status_code == 200 and q.json()["slug"] == yeni
    # 30 gün dolunca: yönlenmez (404) ve başka kart alabilir.
    satir = (await db_oturumu.execute(select(KartvizitEskiSluglar).where(KartvizitEskiSluglar.slug == eski))).scalar_one()
    satir.bitis = satir.bitis - timedelta(days=31)
    await db_oturumu.commit()
    assert (await istemci.get(f"{A}/{eski}", headers=_tarayici())).status_code == 404
    k2 = await _olustur(istemci, yonetici_basligi, slug=eski)
    assert k2["slug"] == eski


async def test_kart_kendi_eski_slugina_donebilir(istemci, yonetici_basligi):
    a, b = f"a-{uuid.uuid4().hex[:6]}", f"b-{uuid.uuid4().hex[:6]}"
    kart = await _olustur(istemci, yonetici_basligi, slug=a)
    assert (await istemci.put(f"{Y}/{kart['id']}", json={"slug": b}, headers=yonetici_basligi)).status_code == 200
    y = await istemci.put(f"{Y}/{kart['id']}", json={"slug": a}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["slug"] == a
    assert (await istemci.get(f"{A}/{b}", headers=_tarayici())).json()["yonlendir"] == a
    assert (await istemci.get(f"{A}/{a}", headers=_tarayici())).json()["durum"] == "aktif"


async def test_acik_kart_alanlari_bilinmeyen_404_pasif_410(istemci, yonetici_basligi):
    kart = await _olustur(istemci, yonetici_basligi, dil="en", tema={"sablon": "kurumsal", "yazi_tipi": "mono", "kose": "yuvarlak"})
    y = await istemci.get(f"{A}/{kart['slug']}", headers=_tarayici())
    assert y.status_code == 200 and y.headers["cache-control"] == "no-store"
    d = y.json()
    assert d["ad_soyad"] == "Ayşe Yılmaz" and d["dil"] == "en" and d["tema"]["sablon"] == "kurumsal"
    assert d["telefonlar"][0]["tel"] == "tel:+905551112233"
    assert d["whatsapp_url"] == "https://wa.me/905551112233"
    assert d["harita_url"].startswith("https://www.google.com/maps/search/?api=1&query=")
    assert d["form"]["acik"] is True and d["form"]["jeton"] and d["form"]["aydinlatma_adresi"] == "/en/gizlilik"
    assert d["vcard_adresi"] == f"/api/v1/kart/{kart['slug']}/rehber.vcf"
    # Sahip / oluşturan e-postası herkese açık yanıtta yok.
    assert "hesap_email" not in d and "olusturan_email" not in d and "yonetici@test.dev" not in y.text
    assert (await istemci.get(f"{A}/yok-boyle-kart-{uuid.uuid4().hex[:4]}")).status_code == 404
    assert (await istemci.get(f"{A}/<script>")).status_code == 404
    await istemci.put(f"{Y}/{kart['id']}", json={"aktif": False}, headers=yonetici_basligi)
    y = await istemci.get(f"{A}/{kart['slug']}", headers=_tarayici())
    assert y.status_code == 410 and _kod(y) == "pasif"
    assert (await istemci.get(f"{A}/{kart['slug']}/ozet")).json() == {"durum": "pasif", "index": False}


async def test_bio_link_duzeni(istemci, yonetici_basligi):
    kart = await _olustur(istemci, yonetici_basligi, duzen="bio_link", icerik=_icerik(baglantilar=[
        {"baslik": "Mağaza", "url": "ornek.com/magaza", "simge": "shop"},
        {"baslik": "Bülten", "url": "https://ornek.com/bulten", "simge": "yok-simge"},
    ]))
    d = (await istemci.get(f"{A}/{kart['slug']}", headers=_tarayici())).json()
    assert d["duzen"] == "bio_link"
    assert [b["baslik"] for b in d["baglantilar"]] == ["Mağaza", "Bülten"]
    assert d["baglantilar"][0]["url"] == "https://ornek.com/magaza" and d["baglantilar"][1]["simge"] == ""
    # Sıralama korunuyor, kimlikler kalıcı.
    ters = list(reversed(kart["icerik"]["baglantilar"]))
    y = await istemci.put(f"{Y}/{kart['id']}", json={"icerik": {**kart["icerik"], "baglantilar": ters}}, headers=yonetici_basligi)
    assert [b["id"] for b in y.json()["icerik"]["baglantilar"]] == [b["id"] for b in ters]
    assert (await istemci.post(Y, json={"duzen": "yok", "icerik": _icerik()}, headers=yonetici_basligi)).status_code == 400


# ---------------------------------------------------------------------------
# Parola koruması
# ---------------------------------------------------------------------------
async def test_parola_korumasi_ve_onizlemede_bilgi_sizmaz(istemci, yonetici_basligi):
    kart = await _olustur(istemci, yonetici_basligi, sifre="gizli-1234", icerik=_icerik(ad_soyad="Gizli Kişi Adı"))
    assert kart["sifreli"] is True and "sifre_ozet" not in kart and "gizli-1234" not in json.dumps(kart)
    slug = kart["slug"]
    y = await istemci.get(f"{A}/{slug}", headers=_tarayici())
    assert y.status_code == 200 and y.json()["durum"] == "kilitli"
    for metin in ("Gizli Kişi Adı", "ayse@ornek.com", "555", "Örnek Ajans", "Kurucu"):
        assert metin not in y.text, metin
    oz = await istemci.get(f"{A}/{slug}/ozet")
    assert oz.json()["durum"] == "kilitli" and oz.json()["gorsel"] is None and oz.json()["index"] is False
    for metin in ("Gizli Kişi Adı", "ayse@ornek.com", "Örnek Ajans", "Kurucu"):
        assert metin not in oz.text, metin
    assert (await istemci.get(f"{A}/{slug}/rehber.vcf", headers=_tarayici())).status_code == 401
    assert (await istemci.get(f"{A}/{slug}/qr.png")).status_code == 401
    y = await istemci.post(f"{A}/{slug}/mesaj", json={"ad": "x", "eposta": "a@b.com", "form_jetonu": "1.x"}, headers=_tarayici())
    assert y.status_code == 401 and _kod(y) == "parola_gerekli"
    # Yanlış parola, sonra doğru parola.
    y = await istemci.post(f"{A}/{slug}/parola", json={"parola": "yanlis"}, headers=_tarayici())
    assert y.status_code == 403 and _kod(y) == "parola_yanlis"
    # Tarayıcı gövdeyi `text/plain` JSON olarak gönderiyor (ön kontrol isteği yok).
    y = await istemci.post(f"{A}/{slug}/parola", content=json.dumps({"parola": "gizli-1234"}),
                           headers={**_tarayici(), "Content-Type": "text/plain;charset=UTF-8"})
    assert y.status_code == 200
    jeton = y.json()["jeton"]
    assert y.json()["kart"]["ad_soyad"] == "Gizli Kişi Adı"
    assert (await istemci.get(f"{A}/{slug}?j={jeton}", headers=_tarayici())).json()["durum"] == "aktif"
    v = await istemci.get(f"{A}/{slug}/rehber.vcf?j={jeton}", headers=_tarayici())
    assert v.status_code == 200 and "FN:Gizli Kişi Adı" in v.text
    # Parola değişince eski jeton geçersiz; kaldırılınca herkese açık.
    await istemci.put(f"{Y}/{kart['id']}", json={"sifre": "yeni-parola-99"}, headers=yonetici_basligi)
    assert (await istemci.get(f"{A}/{slug}?j={jeton}", headers=_tarayici())).json()["durum"] == "kilitli"
    await istemci.put(f"{Y}/{kart['id']}", json={"sifre_kaldir": True}, headers=yonetici_basligi)
    assert (await istemci.get(f"{A}/{slug}", headers=_tarayici())).json()["durum"] == "aktif"


async def test_parola_deneme_hiz_siniri(istemci, yonetici_basligi):
    kart = await _olustur(istemci, yonetici_basligi, sifre="dogru-parola")
    kodlar = [
        (await istemci.post(f"{A}/{kart['slug']}/parola", json={"parola": f"yanlis{i}"}, headers=_tarayici(ip="203.0.113.9"))).status_code
        for i in range(6)
    ]
    assert kodlar == [403] * 5 + [429]
    # Başka IP etkilenmiyor.
    y = await istemci.post(f"{A}/{kart['slug']}/parola", json={"parola": "dogru-parola"}, headers=_tarayici(ip="203.0.113.10"))
    assert y.status_code == 200


async def test_sifre_kurallari(istemci, yonetici_basligi):
    y = await istemci.post(Y, json={"icerik": _icerik(), "sifre": "abc"}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "sifre_gecersiz"


# ---------------------------------------------------------------------------
# vCard ve QR
# ---------------------------------------------------------------------------
async def test_vcard_icerigi_ve_foto_sinirli(istemci, yonetici_basligi):
    import base64
    import re

    kart = await _olustur(istemci, yonetici_basligi)
    assert (await _gorsel(istemci, yonetici_basligi, kart["id"], "foto", _png((1500, 1500)))).status_code == 200
    y = await istemci.get(f"{A}/{kart['slug']}/rehber.vcf", headers=_tarayici(IPHONE))
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/vcard")
    assert f'filename="{kart["slug"]}.vcf"' in y.headers["content-disposition"]
    v = y.text
    assert v.startswith("BEGIN:VCARD\r\nVERSION:3.0\r\n") and v.endswith("END:VCARD\r\n")
    duz = v.replace("\r\n ", "")
    for satir in ("N:Yılmaz;Ayşe;;;", "FN:Ayşe Yılmaz", "ORG:Örnek Ajans", "TITLE:Kurucu", "TEL;TYPE=WORK:+90 (555) 111 22 33",
                  "TEL;TYPE=CELL:+905551112233", "EMAIL;TYPE=INTERNET:ayse@ornek.com", f"URL:https://mehmetkuru.dev/kart/{kart['slug']}",
                  "URL:https://ornek.com", "X-SOCIALPROFILE;TYPE=linkedin:https://www.linkedin.com/in/ayseyilmaz"):
        assert satir in duz, satir
    foto = re.search(r"PHOTO;ENCODING=b;TYPE=JPEG:([A-Za-z0-9+/=]+)", duz)
    assert foto
    jpeg = base64.b64decode(foto.group(1))
    assert jpeg[:2] == b"\xff\xd8" and len(jpeg) <= 40 * 1024
    assert all(len(s.encode()) <= 75 for s in v.split("\r\n"))


async def test_qr_degismez_kodu_tasir_ve_kanal_qr(istemci, yonetici_basligi):
    kart = await _olustur(istemci, yonetici_basligi)
    y = await istemci.get(f"{Y}/{kart['id']}/qr?bicim=svg", headers=yonetici_basligi)
    assert y.status_code == 200 and y.text.startswith("<svg ")
    p = await istemci.get(f"{A}/{kart['slug']}/qr.png")
    assert p.status_code == 200 and p.content.startswith(b"\x89PNG")
    assert (await istemci.get(f"{A}/{kart['slug']}/qr.gif")).status_code == 404
    from services import kartvizit as k
    from services import kartvizit_kayit as kk

    assert k.kart_adresi(kart["kod"]).endswith(f"/kart/{kart['kod']}")
    await istemci.get(f"{A}/{kart['kod']}", headers=_tarayici(ip="198.51.100.31"))
    await istemci.get(f"{A}/{kart['slug']}", headers=_tarayici(ip="198.51.100.32"))
    an = (await istemci.get(f"{Y}/{kart['id']}/analiz", headers=yonetici_basligi)).json()
    assert an["toplam"]["goruntulenme"] == 2 and an["qr"] == 1
    assert kk.MODELLER["kart"].__tablename__ == "kartvizitler"


# ---------------------------------------------------------------------------
# İletişim formu
# ---------------------------------------------------------------------------
async def _gonder(istemci, kart, ip="198.51.100.50", **govde):
    govde.setdefault("ad", "Ziyaretçi")
    govde.setdefault("eposta", f"z-{uuid.uuid4().hex[:6]}@musteri.com")
    govde.setdefault("mesaj", "Merhaba, görüşelim.")
    if "form_jetonu" not in govde:
        govde["form_jetonu"] = _form_jetonu("kart", kart["id"])
    return await istemci.post(f"{A}/{kart['slug']}/mesaj", content=json.dumps(govde), headers={
        **_tarayici(ip=ip), "Content-Type": "text/plain;charset=UTF-8"})


async def test_ajans_karti_mesaji_crm_adayi_olur(istemci, yonetici_basligi, db_oturumu):
    from models.crm import CrmAdaylari
    from models.kartvizit import KartvizitMesajlari

    kart = await _olustur(istemci, yonetici_basligi)
    eposta = f"aday-{uuid.uuid4().hex[:6]}@firma.com"
    y = await _gonder(istemci, kart, eposta=eposta, telefon="+90 532 000 00 00")
    assert y.status_code == 200 and y.json() == {"ok": True}
    m = (await db_oturumu.execute(select(KartvizitMesajlari).where(KartvizitMesajlari.eposta == eposta))).scalar_one()
    assert m.hesap_email is None and m.aydinlatma_at is not None and m.dil == "tr" and m.crm_aday_id
    aday = (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.id == m.crm_aday_id))).scalar_one()
    assert aday.email == eposta and aday.kaynak == "form" and "kartvizit:" in (aday.kaynak_detay or "")
    liste = (await istemci.get(f"{Y}/mesajlar?kart_id={kart['id']}", headers=yonetici_basligi)).json()
    assert [x["eposta"] for x in liste["items"]] == [eposta] and liste["okunmamis"] == 1
    assert liste["items"][0]["sahip_baslik"] == "Ayşe Yılmaz"
    mid = liste["items"][0]["id"]
    assert (await istemci.put(f"{Y}/mesajlar/{mid}", json={"okundu": True}, headers=yonetici_basligi)).json()["okundu"] is True


async def test_musteri_karti_mesaji_crme_karismaz_bildirim_gider(istemci, yonetici_basligi, db_oturumu):
    from models.crm import CrmAdaylari
    from models.notifications import Notifications

    e = await _musteri(istemci, yonetici_basligi)
    kart = await _olustur(istemci, _b(e), M)
    eposta = f"ziyaretci-{uuid.uuid4().hex[:6]}@musteri.com"
    y = await _gonder(istemci, kart, eposta=eposta)
    assert y.status_code == 200
    assert (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.email == eposta))).first() is None
    liste = (await istemci.get(f"{M}/mesajlar", headers=_b(e))).json()
    assert [x["eposta"] for x in liste["items"]] == [eposta] and liste["items"][0]["crm_aday_id"] is None
    bildirim = (await db_oturumu.execute(select(Notifications).where(
        Notifications.recipient_email == e, Notifications.event_type == "kartvizit_mesaj"))).scalars().all()
    assert bildirim and bildirim[0].link == "/client?sekme=kartvizit&alt=mesajlar"
    # Başka müşteri bu mesajı göremez / silemez.
    e2 = await _musteri(istemci, yonetici_basligi)
    assert (await istemci.get(f"{M}/mesajlar", headers=_b(e2))).json()["items"] == []
    mid = liste["items"][0]["id"]
    assert (await istemci.delete(f"{M}/mesajlar/{mid}", headers=_b(e2))).status_code == 404
    assert (await istemci.delete(f"{M}/mesajlar/{mid}", headers=_b(e))).json() == {"ok": True}


async def test_form_bal_kupu_jeton_hiz_ve_dogrulama(istemci, yonetici_basligi, db_oturumu):
    from models.kartvizit import KartvizitMesajlari

    kart = await _olustur(istemci, yonetici_basligi)
    # Bal küpü dolu → "başarılı" ama kayıt yok.
    tuzak = f"bot-{uuid.uuid4().hex[:6]}@spam.com"
    y = await _gonder(istemci, kart, eposta=tuzak, web_sitesi="http://spam.example")
    assert y.status_code == 200 and y.json() == {"ok": True}
    assert (await db_oturumu.execute(select(KartvizitMesajlari).where(KartvizitMesajlari.eposta == tuzak))).first() is None
    # Form jetonu: çok hızlı (sayfa açılır açılmaz gönderim) ve sahte.
    y = await _gonder(istemci, kart, ip="198.51.100.61", form_jetonu=_form_jetonu("kart", kart["id"], once=0))
    assert y.status_code == 429 and _kod(y) == "cok_hizli"
    y = await _gonder(istemci, kart, ip="198.51.100.62", form_jetonu="123.sahte")
    assert y.status_code == 400 and _kod(y) == "form_jetonu"
    # Ad ve iletişim (e-posta ya da telefon) zorunlu.
    y = await _gonder(istemci, kart, ip="198.51.100.63", eposta="", telefon="")
    assert y.status_code == 400 and _kod(y) == "iletisim_gerekli"
    y = await _gonder(istemci, kart, ip="198.51.100.64", eposta="gecersiz")
    assert y.status_code == 400 and _kod(y) == "eposta_gecersiz"
    # Hız sınırı: aynı IP + kart 10 dakikada 3.
    kodlar = [(await _gonder(istemci, kart, ip="198.51.100.70")).status_code for _ in range(4)]
    assert kodlar == [200, 200, 200, 429]
    # Form kapalıysa 403.
    await istemci.put(f"{Y}/{kart['id']}", json={"form_acik": False}, headers=yonetici_basligi)
    y = await _gonder(istemci, kart, ip="198.51.100.71")
    assert y.status_code == 403 and _kod(y) == "form_kapali"
    assert (await istemci.get(f"{A}/{kart['slug']}", headers=_tarayici())).json()["form"]["jeton"] is None


# ---------------------------------------------------------------------------
# Müşteri izolasyonu, modül, sınır
# ---------------------------------------------------------------------------
async def test_musteri_izolasyonu_modul_kapali_403_ve_kart_siniri(istemci, yonetici_basligi):
    e1 = await _musteri(istemci, yonetici_basligi, kart_siniri=1)
    e2 = await _musteri(istemci, yonetici_basligi)
    kart = await _olustur(istemci, _b(e1), M)
    assert kart["hesap_email"] == e1 and kart["olusturan_email"] == e1
    meta = (await istemci.get(f"{M}/meta", headers=_b(e1))).json()
    assert meta["kart_siniri"] == 1 and meta["kart_sayisi"] == 1 and "linkedin" in meta["platformlar"]
    y = await istemci.post(M, json={"icerik": _icerik()}, headers=_b(e1))
    assert y.status_code == 409 and _kod(y) == "kart_siniri"
    for metot, yol in (("GET", f"{M}/{kart['id']}"), ("PUT", f"{M}/{kart['id']}"), ("DELETE", f"{M}/{kart['id']}"),
                       ("GET", f"{M}/{kart['id']}/analiz"), ("GET", f"{M}/{kart['id']}/qr")):
        y = await istemci.request(metot, yol, json={"aktif": False} if metot == "PUT" else None, headers=_b(e2))
        assert y.status_code == 404, (metot, yol)
    y = await _gorsel(istemci, _b(e2), kart["id"], "foto", yol=M)
    assert y.status_code == 404
    assert (await istemci.get(M, headers=_b(e2))).json()["items"] == []
    assert [x["id"] for x in (await istemci.get(M, headers=_b(e1))).json()["items"]] == [kart["id"]]
    # Müşteri `hesap_email` yazarak başkası adına kart açamaz.
    e3 = await _musteri(istemci, yonetici_basligi)
    k3 = await _olustur(istemci, _b(e3), M, hesap_email=e1)
    assert k3["hesap_email"] == e3
    # Modül kapalı → 403; herkese açık kartı da 410.
    yok = _e()
    y = await istemci.get(M, headers=_b(yok))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    await _modul_ac(istemci, yonetici_basligi, e1, acik=False)
    y = await istemci.get(M, headers=_b(e1))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    assert (await istemci.get(f"{A}/{kart['slug']}", headers=_tarayici())).status_code == 410
    # Yönetici her kartı görür; müşteri adına kart açabilir (sınır yöneticiye uygulanmaz).
    y = await istemci.get(f"{Y}?hesap={e1}", headers=yonetici_basligi)
    assert [x["id"] for x in y.json()["items"]] == [kart["id"]]
    k4 = await _olustur(istemci, yonetici_basligi, hesap_email=e1)
    assert k4["hesap_email"] == e1


async def test_ekip_uyesi_kendi_kartini_yapar_izinsiz_403(istemci, yonetici_basligi, db_oturumu):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as he

    sahip = await _musteri(istemci, yonetici_basligi)
    uye, izinsiz = _e("uye"), _e("izinsiz")
    for kisi, izinler in ((uye, list(he.ROL_VARSAYILAN["uye"])), (izinsiz, ["projeler"])):
        db_oturumu.add(HesapUyeleri(hesap_email=sahip, uye_email=kisi, rol="uye", izinler=json.dumps(izinler),
                                    durum="aktif", olusturma=he.simdi()))
    await db_oturumu.commit()
    he.onbellegi_temizle()
    assert "kartvizit" in he.ROL_VARSAYILAN["uye"]
    kart = await _olustur(istemci, _b(uye, sahip), M, icerik=_icerik(ad_soyad="Üye Kişi"))
    assert kart["hesap_email"] == sahip and kart["olusturan_email"] == uye
    y = await istemci.get(M, headers=_b(izinsiz, sahip))
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"


# ---------------------------------------------------------------------------
# Analitik
# ---------------------------------------------------------------------------
async def test_analitik_bot_sayilmaz_ham_ip_yok(istemci, yonetici_basligi, db_oturumu):
    from models.kartvizit import KartvizitOlaylari

    kart = await _olustur(istemci, yonetici_basligi)
    s = kart["slug"]
    await istemci.get(f"{A}/{s}", headers=_tarayici(ip="198.51.100.81"))
    await istemci.get(f"{A}/{s}", headers=_tarayici(ip="198.51.100.81"))
    await istemci.get(f"{A}/{s}", headers=_tarayici(IPHONE, ip="198.51.100.82"))
    for ua in (WHATSAPP, FACEBOOK, "", "curl/8.0"):
        await istemci.get(f"{A}/{s}", headers={"User-Agent": ua, "X-MK-Istemci-IP": "198.51.100.83"})
    await istemci.get(f"{A}/{s}", headers={**_tarayici(ip="198.51.100.84"), "Sec-Purpose": "prefetch"})
    await istemci.get(f"{A}/{s}/rehber.vcf", headers=_tarayici(ip="198.51.100.81"))
    await istemci.get(f"{A}/{s}/rehber.vcf", headers=_tarayici(WHATSAPP, ip="198.51.100.81"))
    bag = kart["icerik"]["baglantilar"][0]["id"]
    for hedef in (f"l:{bag}", f"l:{bag}", "wa", "s:linkedin"):
        y = await istemci.post(f"{A}/{s}/olay", content=json.dumps({"tur": "tik", "hedef": hedef}),
                               headers={**_tarayici(ip="198.51.100.81"), "Content-Type": "text/plain"})
        assert y.status_code == 204
    await istemci.post(f"{A}/{s}/olay", json={"tur": "paylas"}, headers=_tarayici(ip="198.51.100.81"))
    y = await istemci.post(f"{A}/{s}/olay", json={"tur": "tik", "hedef": "javascript:x"}, headers=_tarayici())
    assert y.status_code == 400
    y = await istemci.post(f"{A}/{s}/olay", json={"tur": "hack"}, headers=_tarayici())
    assert y.status_code == 400
    await istemci.get(f"{A}/{s}/ozet", headers=_tarayici(FACEBOOK))  # önizleme özeti hiç sayılmaz

    an = (await istemci.get(f"{Y}/{kart['id']}/analiz?gun=30", headers=yonetici_basligi)).json()
    assert an["toplam"] == {"goruntulenme": 3, "rehber": 1, "tik": 4, "form": 0, "paylas": 1}
    assert an["tekil"] == 2 and an["bot"] == 6 and an["qr"] == 0
    assert an["donem"]["goruntulenme"] == 3 and an["donem"]["tekil"] == 2 and len(an["gunluk"]) == 30
    assert an["gunluk"][-1]["goruntulenme"] == 3 and an["gunluk"][-1]["tekil"] == 2
    hedefler = {h["hedef"]: (h["sayi"], h["etiket"]) for h in an["hedefler"]}
    assert hedefler[f"l:{bag}"] == (2, "Portfolyo") and hedefler["wa"] == (1, "WhatsApp")
    assert {c["anahtar"] for c in an["cihazlar"]} == {"masaustu", "mobil"}
    liste = (await istemci.get(f"{Y}?ara={s}", headers=yonetici_basligi)).json()["items"]
    assert liste[0]["son30"]["goruntulenme"] == 3
    # Ham IP / User-Agent hiçbir sütunda yok.
    satirlar = (await db_oturumu.execute(select(KartvizitOlaylari).where(KartvizitOlaylari.sahip_id == kart["id"],
                                                                         KartvizitOlaylari.sahip_tur == "kart"))).scalars().all()
    assert satirlar
    for satir in satirlar:
        degerler = " ".join(str(getattr(satir, c.name)) for c in KartvizitOlaylari.__table__.columns)
        assert "198.51.100" not in degerler and "Mozilla" not in degerler and "WhatsApp" not in degerler
        assert len(satir.ip_ozeti) == 64


# ---------------------------------------------------------------------------
# Görseller
# ---------------------------------------------------------------------------
async def test_gorsel_yukleme_sunma_degistirme_ve_sinirlar(istemci, yonetici_basligi, db_oturumu):
    from models.kartvizit import KartvizitGorselleri

    kart = await _olustur(istemci, yonetici_basligi)
    y = await _gorsel(istemci, yonetici_basligi, kart["id"], "foto", _png((900, 500)))
    assert y.status_code == 200, y.text
    foto = y.json()["foto"]
    assert (foto["genislik"], foto["yukseklik"]) == (500, 500) and foto["url"].endswith(".webp")
    g = await istemci.get(foto["url"])
    assert g.status_code == 200 and g.headers["content-type"] == "image/webp"
    assert "immutable" in g.headers["cache-control"] and g.content[:4] == b"RIFF"
    j = await istemci.get(foto["url"].replace(".webp", ".jpg"))
    assert j.status_code == 200 and j.headers["content-type"] == "image/jpeg" and j.content[:2] == b"\xff\xd8"
    # Değiştirme: eski satır ve adres gider.
    y2 = await _gorsel(istemci, yonetici_basligi, kart["id"], "foto", _png((300, 300), (10, 200, 10)))
    assert y2.json()["foto"]["id"] != foto["id"]
    assert (await istemci.get(foto["url"])).status_code == 404
    # Tür / boyut / biçim sınırları.
    y = await _gorsel(istemci, yonetici_basligi, kart["id"], "arka-plan")
    assert y.status_code == 400 and _kod(y) == "gorsel_turu_gecersiz"
    y = await _gorsel(istemci, yonetici_basligi, kart["id"], "logo", b"%PDF-1.4 sahte", ad="x.pdf", tip="application/pdf")
    assert y.status_code == 400 and _kod(y) == "gorsel_bicimi"
    y = await _gorsel(istemci, yonetici_basligi, kart["id"], "logo", b"\x89PNG" + b"0" * (5 * 1024 * 1024 + 10))
    assert y.status_code == 413 and _kod(y) == "gorsel_buyuk"
    # Galeri en çok 8; sıralama.
    idler = []
    for i in range(8):
        y = await _gorsel(istemci, yonetici_basligi, kart["id"], "galeri", _png((200 + i, 200)))
        assert y.status_code == 200
        idler.append(y.json()["galeri"][-1]["id"])
    y = await _gorsel(istemci, yonetici_basligi, kart["id"], "galeri")
    assert y.status_code == 409 and _kod(y) == "galeri_dolu"
    y = await istemci.put(f"{Y}/{kart['id']}/galeri-sira", json={"idler": list(reversed(idler))}, headers=yonetici_basligi)
    assert [g["id"] for g in y.json()["galeri"]] == list(reversed(idler))
    y = await istemci.put(f"{Y}/{kart['id']}/galeri-sira", json={"idler": idler[:3]}, headers=yonetici_basligi)
    assert y.status_code == 400
    y = await istemci.delete(f"{Y}/{kart['id']}/gorsel/{idler[0]}", headers=yonetici_basligi)
    assert len(y.json()["galeri"]) == 7
    acik = (await istemci.get(f"{A}/{kart['slug']}", headers=_tarayici())).json()
    assert len(acik["galeri"]) == 7 and acik["foto"]["url"].startswith("/api/v1/kart/gorsel/")
    assert (await istemci.get(f"{A}/gorsel/yok.webp")).status_code == 404
    assert (await istemci.get(f"{A}/gorsel/{acik['foto']['url'].rsplit('/', 1)[1].replace('.webp', '.exe')}")).status_code == 404
    sayi = (await db_oturumu.execute(select(KartvizitGorselleri).where(KartvizitGorselleri.sahip_id == kart["id"],
                                                                       KartvizitGorselleri.sahip_tur == "kart"))).scalars().all()
    assert len(sayi) == 8  # 1 foto + 7 galeri


# ---------------------------------------------------------------------------
# Paylaşım özeti
# ---------------------------------------------------------------------------
async def test_paylasim_ozeti(istemci, yonetici_basligi):
    kart = await _olustur(istemci, yonetici_basligi, dil="de", index_acik=True)
    oz = (await istemci.get(f"{A}/{kart['slug']}/ozet")).json()
    assert oz["durum"] == "aktif" and oz["index"] is True and oz["locale"] == "de_DE"
    assert oz["baslik"] == "Ayşe Yılmaz — Kurucu · Örnek Ajans"
    assert oz["aciklama"] == "Web ve mobil ürünler geliştiriyoruz." and oz["gorsel"] is None
    assert oz["kart_adresi"] == f"https://mehmetkuru.dev/kart/{kart['slug']}"
    await _gorsel(istemci, yonetici_basligi, kart["id"], "foto")
    oz = (await istemci.get(f"{A}/{kart['slug']}/ozet")).json()
    assert oz["gorsel"].startswith("https://mehmetkuru.dev/api/v1/kart/gorsel/") and oz["gorsel"].endswith(".jpg")
    assert oz["gorsel_genislik"] == 600
    kart2 = await _olustur(istemci, yonetici_basligi, icerik=_icerik(tanitim="", unvan="", sirket=""), dil="ar")
    oz = (await istemci.get(f"{A}/{kart2['slug']}/ozet")).json()
    assert oz["index"] is False and oz["aciklama"] == "بطاقة أعمال رقمية"
    assert (await istemci.get(f"{A}/yok-{uuid.uuid4().hex[:5]}/ozet")).json() == {"durum": "yok", "index": False}


# ---------------------------------------------------------------------------
# Çöp kutusu
# ---------------------------------------------------------------------------
async def test_silme_cop_kutusuna_gorsellerle_ve_geri_alma(istemci, yonetici_basligi, db_oturumu):
    from models.cop_kutusu import CopKutusu
    from models.dosyalar import DosyaIcerikleri
    from models.kartvizit import KartvizitGorselleri

    e = await _musteri(istemci, yonetici_basligi)
    kart = await _olustur(istemci, _b(e), M)
    foto = (await _gorsel(istemci, _b(e), kart["id"], "foto", yol=M)).json()["foto"]
    satir = (await db_oturumu.execute(select(KartvizitGorselleri).where(KartvizitGorselleri.id == foto["id"]))).scalar_one()
    depolama = satir.depolama_anahtari
    assert (await istemci.delete(f"{M}/{kart['id']}", headers=_b(e))).json() == {"ok": True}
    assert (await istemci.get(f"{A}/{kart['slug']}", headers=_tarayici())).status_code == 404
    kopyalar = (await db_oturumu.execute(
        select(CopKutusu).where(CopKutusu.tablo.in_(("kartvizitler", "kartvizit_gorselleri")), CopKutusu.sahip_email == e)
    )).scalars().all()
    assert {x.tablo for x in kopyalar} == {"kartvizitler", "kartvizit_gorselleri"}
    # Görsel içeriği çöp kaydı kalıcı silinene kadar duruyor.
    assert (await db_oturumu.execute(select(DosyaIcerikleri.id).where(DosyaIcerikleri.anahtar == depolama))).first()
    ana = next(x for x in kopyalar if x.tablo == "kartvizitler")
    y = await istemci.post(f"/api/v1/cop-kutum/{ana.id}/geri-al", headers=_b(e))
    assert y.status_code == 200, y.text
    acik = await istemci.get(f"{A}/{kart['slug']}", headers=_tarayici())
    assert acik.status_code == 200 and acik.json()["foto"]["id"] == foto["id"]
    assert (await istemci.get(acik.json()["foto"]["url"])).status_code == 200


async def test_tek_gorsel_kaldirma_icerigi_hemen_siler(istemci, yonetici_basligi, db_oturumu):
    from models.dosyalar import DosyaIcerikleri
    from models.kartvizit import KartvizitGorselleri

    kart = await _olustur(istemci, yonetici_basligi)
    logo = (await _gorsel(istemci, yonetici_basligi, kart["id"], "logo")).json()["logo"]
    depolama = (await db_oturumu.execute(select(KartvizitGorselleri.depolama_anahtari).where(
        KartvizitGorselleri.id == logo["id"]))).scalar_one()
    y = await istemci.delete(f"{Y}/{kart['id']}/gorsel/{logo['id']}", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["logo"] is None
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(DosyaIcerikleri.id).where(DosyaIcerikleri.anahtar == depolama))).first() is None


# ---------------------------------------------------------------------------
# Ön yüz / kayıt tutarlılığı
# ---------------------------------------------------------------------------
def test_modul_kaydi_ve_bildirim_olaylari():
    from core import moduller as mf
    from services.bildirim_tercih import OLAYLAR
    from services.hesap_ekibi import IZINLER, OLAY_IZNI

    kart = mf.MODUL_SOZLUGU["dijital_kartvizit"]
    yorum = mf.MODUL_SOZLUGU["google_yorum_sayfasi"]
    assert kart.kategori == yorum.kategori == "dijital_kimlik"
    assert not kart.varsayilan_acik and not yorum.varsayilan_acik
    assert kart.varsayilan_ayarlar() == {"kart_siniri": 5} and yorum.varsayilan_ayarlar() == {"sayfa_siniri": 3}
    assert kart.musteri_sekmesi == kart.yonetici_sekmesi == "kartvizit" and yorum.yerlesim == ("kartvizit",)
    assert mf.manifest_hatalari() == []
    assert "kartvizit" in IZINLER and OLAY_IZNI["kartvizit_mesaj"] == OLAY_IZNI["yorum_geri_bildirim"] == "kartvizit"
    assert OLAYLAR["kartvizit_mesaj"]["roller"] == ("client",)
    assert OLAYLAR["yorum_geri_bildirim"]["roller"] == ("admin", "client")
