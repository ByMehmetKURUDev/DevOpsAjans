"""Faz 4Q — Dinamik QR stüdyosu ve kısa link.

Kapsam: şema beyaz listesi (javascript: vb. kesin ret), tür doğrulamaları ve
hedef üretimi, kod/takma ad (çakışma, ayrılmış), yönlendirme 302 + no-store,
pasif 410, bilinmeyen 404 (7 dil, noindex), süre/limit dolumu, vCard ve .ics
içeriği, uygulama türünde User-Agent yönlendirmesi, bot taramasının
sayılmaması, IP'nin ham saklanmaması, müşteri izolasyonu + modül kapalıyken
403, kayıt sınırı, hız sınırı, CSV toplu (hatalı satırlar), ZIP, SVG/PNG
çıktısı (PNG imzası, SVG kökü), logo, önizleme uyarıları, yönetici engeli,
çöp kutusu, denetim kaydında Wi-Fi parolasının maskelenmesi.
"""

import base64
import io
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from conftest import jeton_uret

Y = "/api/v1/dinamik-qr/yonetim"
M = "/api/v1/qr-kodlarim"
Q = "/api/v1/q"
MODUL = "/api/v1/moduller"
PNG_IMZA = b"\x89PNG\r\n\x1a\n"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
MASAUSTU = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
WHATSAPP = "WhatsApp/2.23.20.0 A"


def _e(on: str = "qr") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@qr.dev"


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


def _tarayici(ua: str = MASAUSTU, ip: str = "198.51.100.7", **ek) -> dict:
    return {"User-Agent": ua, "X-MK-Istemci-IP": ip, **ek}


@pytest.fixture(autouse=True)
def _temiz():
    from routers import dinamik_qr as r
    from services import hesap_ekibi

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    yield
    r.hiz_sinirlarini_temizle()


async def _modul_ac(istemci, yonetici_basligi, eposta, acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/dinamik_qr", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _musteri(istemci, yonetici_basligi, **ayarlar) -> str:
    e = _e()
    await _modul_ac(istemci, yonetici_basligi, e, **ayarlar)
    return e


async def _olustur(istemci, basliklar, yol=Y, **govde):
    govde.setdefault("ad", "Test QR")
    govde.setdefault("tur", "url")
    govde.setdefault("alanlar", {"url": "https://ornek.com/sayfa"})
    y = await istemci.post(yol, json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


def _png_logo(boyut=(64, 64), bicim="PNG") -> str:
    from PIL import Image

    g = Image.new("RGBA" if bicim == "PNG" else "RGB", boyut, (200, 30, 120, 255) if bicim == "PNG" else (200, 30, 120))
    t = io.BytesIO()
    g.save(t, format=bicim)
    return "data:image/png;base64," + base64.b64encode(t.getvalue()).decode()


# ---------------------------------------------------------------------------
# Saf kurallar
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "adres",
    [
        "javascript:alert(1)",
        "JaVaScRiPt:alert(document.cookie)",
        " javascript:alert(1)",
        "java\tscript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "file:///etc/passwd",
        "vbscript:msgbox(1)",
        "mailto:a@b.com",
        "ftp://ornek.com/x",
        "https://kullanici:parola@kotu.com",
        "https://mehmetkuru.dev/q/Abc2345",
    ],
)
def test_url_turu_sema_beyaz_listesi_disini_reddeder(adres):
    from services import dinamik_qr as s

    with pytest.raises(s.QrHatasi) as h:
        s.dogrula("url", {"url": adres})
    assert h.value.kod in ("sema_izinsiz", "url_gecersiz", "dongu")


def test_guvenli_hedef_mi():
    from services import dinamik_qr as s

    for iyi in ("https://ornek.com", "http://ornek.com/a?b=c", "tel:+905551112233", "mailto:a@b.com",
                "sms:+905551112233?body=x"):
        assert s.guvenli_hedef_mi(iyi), iyi
    for kotu in ("javascript:alert(1)", "data:text/html,x", "file:///x", "https://a b.com", "tel:abc",
                 "https://", "geo:41,29", "", None, "https://x.com/" + "a" * 3000, "https://u:p@x.com"):
        assert not s.guvenli_hedef_mi(kotu), kotu


def test_url_hedefi_utm_ve_idn():
    from services import dinamik_qr as s

    a, _ = s.dogrula("url", {"url": "örnek.com.tr/kampanya?x=1", "utm_source": "qr", "utm_medium": "afis",
                              "utm_campaign": "bahar 2026"})
    hedef = s.hedef_uret("url", a)
    assert hedef.startswith("https://xn--rnek-4qa.com.tr/kampanya?x=1&utm_source=qr&utm_medium=afis")
    assert "utm_campaign=bahar+2026" in hedef and hedef.isascii()


@pytest.mark.parametrize(
    "tur,alanlar,beklenen",
    [
        ("google_yorum", {"place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4"},
         "https://search.google.com/local/writereview?placeid=ChIJN1t_tDeuEmsRUsoyG83frY4"),
        ("whatsapp", {"numara": "+90 (555) 111-22-33", "mesaj": "Merhaba & hoş geldiniz"},
         "https://wa.me/905551112233?text=Merhaba%20%26%20ho%C5%9F%20geldiniz"),
        ("telefon", {"numara": "0090 555 111 22 33"}, "tel:+905551112233"),
        ("sms", {"numara": "+905551112233", "mesaj": "Kod: 7"}, "sms:+905551112233?body=Kod%3A%207"),
        ("eposta", {"eposta": "bilgi@ornek.com", "konu": "Teklif", "govde": "Satır 1\nSatır 2"},
         "mailto:bilgi@ornek.com?subject=Teklif&body=Sat%C4%B1r%201%0ASat%C4%B1r%202"),
        ("konum", {"enlem": "41,0082", "boylam": "28.9784"},
         "https://www.google.com/maps/search/?api=1&query=41.0082,28.9784"),
        ("konum", {"adres": "Taksim, İstanbul"},
         "https://www.google.com/maps/search/?api=1&query=Taksim,%20%C4%B0stanbul"),
        ("uygulama", {"ios": "https://apps.apple.com/app/id1", "android": "https://play.google.com/store/apps/details?id=x"},
         "https://play.google.com/store/apps/details?id=x"),
    ],
)
def test_tur_hedefleri(tur, alanlar, beklenen):
    from services import dinamik_qr as s

    a, _ = s.dogrula(tur, alanlar)
    hedef = s.hedef_uret(tur, a)
    assert hedef == beklenen
    assert s.guvenli_hedef_mi(hedef)


@pytest.mark.parametrize(
    "tur,alanlar,kod,alan",
    [
        ("bilinmeyen", {}, "tur_gecersiz", "tur"),
        ("url", {}, "zorunlu", "url"),
        ("google_yorum", {"place_id": "kısa id!"}, "place_id_gecersiz", "place_id"),
        ("whatsapp", {"numara": "05551112233"}, "telefon_gecersiz", "numara"),
        ("telefon", {"numara": "+90abc"}, "telefon_gecersiz", "numara"),
        ("eposta", {"eposta": "gecersiz@"}, "eposta_gecersiz", "eposta"),
        ("konum", {"enlem": "95", "boylam": "10"}, "koordinat_gecersiz", "enlem"),
        ("konum", {}, "konum_gerekli", "adres"),
        ("vcard", {"unvan": "Müdür"}, "zorunlu", "ad"),
        ("vcard", {"ad": "A", "web": "javascript:alert(1)"}, "sema_izinsiz", "web"),
        ("etkinlik", {"baslik": "X"}, "zorunlu", "baslangic"),
        ("etkinlik", {"baslik": "X", "baslangic": "2026-10-10T10:00", "bitis": "2026-10-09T10:00"}, "bitis_once", "bitis"),
        ("etkinlik", {"baslik": "X", "baslangic": "dün"}, "tarih_gecersiz", "baslangic"),
        ("uygulama", {}, "zorunlu", "diger"),
        ("uygulama", {"ios": "data:text/html,x"}, "sema_izinsiz", "ios"),
        ("wifi", {"ssid": "Ev", "sifre": "kisa"}, "sifre_gecersiz", "sifre"),
        ("wifi", {"sifre": "uzunparola1"}, "zorunlu", "ssid"),
        ("metin", {"metin": "x" * 901}, "cok_uzun", "metin"),
    ],
)
def test_tur_dogrulama_hatalari(tur, alanlar, kod, alan):
    from services import dinamik_qr as s

    with pytest.raises(s.QrHatasi) as h:
        s.dogrula(tur, alanlar)
    assert (h.value.kod, h.value.alan) == (kod, alan)


def test_kod_alfabesi_ve_takma_ad():
    from services import dinamik_qr as s

    assert not set("0Oo1lI") & set(s.KOD_ALFABESI)
    kodlar = {s.kod_uret() for _ in range(300)}
    assert all(len(k) == 7 and set(k) <= set(s.KOD_ALFABESI) for k in kodlar) and len(kodlar) == 300
    assert s.takma_ad_duzelt("  Bahar-Kampanyasi ") == "bahar-kampanyasi"
    assert s.takma_ad_duzelt("") is None
    for kotu, kod in (("admin", "takma_ad_ayrilmis"), ("api", "takma_ad_ayrilmis"), ("a", "takma_ad_gecersiz"),
                      ("çiçek", "takma_ad_gecersiz"), ("-bas", "takma_ad_gecersiz"), ("a--b", "takma_ad_gecersiz"),
                      ("x" * 41, "takma_ad_gecersiz")):
        with pytest.raises(s.QrHatasi) as h:
            s.takma_ad_duzelt(kotu)
        assert h.value.kod == kod, kotu


def test_vcard_icerigi():
    from services import dinamik_qr as s

    a, _ = s.dogrula("vcard", {"ad": "Mehmet", "soyad": "Kuru", "kurum": "Ajans; A.Ş.", "unvan": "Kurucu",
                               "telefon_cep": "+90 555 111 22 33", "eposta": "m@ornek.dev", "web": "ornek.dev",
                               "adres_sehir": "İstanbul", "adres_ulke": "Türkiye", "not": "Satır 1\nSatır 2"})
    v = s.vcard_uret(a)
    assert v.startswith("BEGIN:VCARD\r\nVERSION:3.0\r\n") and v.endswith("END:VCARD\r\n")
    for parca in ("N:Kuru;Mehmet;;;", "FN:Mehmet Kuru", "ORG:Ajans\\; A.Ş.", "TITLE:Kurucu", "TEL;TYPE=CELL:+90 555 111 22 33",
                  "EMAIL;TYPE=INTERNET:m@ornek.dev", "URL:https://ornek.dev", "ADR;TYPE=WORK:;;;İstanbul;;;Türkiye",
                  "NOTE:Satır 1\\nSatır 2"):
        assert parca in v, parca
    # Uzun satırlar 75 sekizlide katlanıyor.
    a2, _ = s.dogrula("vcard", {"ad": "A", "not": "ğ" * 120})
    assert all(len(satir.encode()) <= 75 for satir in s.vcard_uret(a2).split("\r\n"))


def test_ics_icerigi_saat_dilimi_ve_tum_gun():
    from services import dinamik_qr as s

    a, _ = s.dogrula("etkinlik", {"baslik": "Lansman, 2026", "baslangic": "2026-10-10T19:30", "konum": "İstanbul",
                                  "aciklama": "Kapı 19:00"})
    ics = s.ics_uret(a, "Abc2345", datetime(2026, 10, 1, tzinfo=timezone.utc))
    for parca in ("BEGIN:VCALENDAR", "BEGIN:VEVENT", "UID:qr-Abc2345@mehmetkuru.dev", "DTSTART:20261010T163000Z",
                  "DTEND:20261010T173000Z", "SUMMARY:Lansman\\, 2026", "LOCATION:İstanbul", "END:VCALENDAR"):
        assert parca in ics, parca
    a, _ = s.dogrula("etkinlik", {"baslik": "Fuar", "baslangic": "2026-10-10", "bitis": "2026-10-12", "tum_gun": True})
    ics = s.ics_uret(a, "Abc2345")
    assert "DTSTART;VALUE=DATE:20261010" in ics and "DTEND;VALUE=DATE:20261013" in ics


def test_user_agent_siniflari():
    from services import dinamik_qr as s

    assert (s.cihaz_sinifi(IPHONE), s.isletim_ailesi(IPHONE), s.bot_mu(IPHONE)) == ("mobil", "ios", False)
    assert (s.cihaz_sinifi(ANDROID), s.isletim_ailesi(ANDROID)) == ("mobil", "android")
    tablet = "Mozilla/5.0 (Linux; Android 13; SM-X700) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    assert s.cihaz_sinifi(tablet) == "tablet"
    assert (s.cihaz_sinifi(MASAUSTU), s.isletim_ailesi(MASAUSTU)) == ("masaustu", "windows")
    for bot in (WHATSAPP, "Slackbot-LinkExpanding 1.0", "facebookexternalhit/1.1", "TelegramBot (like TwitterBot)",
                "Mozilla/5.0 (compatible; Googlebot/2.1)", "curl/8.0", ""):
        assert s.bot_mu(bot), bot
    assert s.bot_mu(MASAUSTU, {"sec-purpose": "prefetch;prerender"})
    assert s.referer_alani("https://www.instagram.com/p/x") == "instagram.com"
    assert s.referer_alani("android-app://com.x") is None
    assert s.ulke_kodu("tr") == "TR" and s.ulke_kodu("XX") is None and s.ulke_kodu("T1") is None


def test_dil_secimi_ve_kontrast():
    from services import dinamik_qr as s

    assert s.dil_sec("ar-SA,ar;q=0.9,en;q=0.5") == "ar"
    assert s.dil_sec("fr-FR,fr;q=0.9,de;q=0.4") == "de"
    assert s.dil_sec("fr") == "en" and s.dil_sec(None) == "tr"
    t = s.tasarim_duzelt({"on_renk": "#999999", "arka_renk": "#aaaaaa", "kenar": 1})
    assert s.tasarim_uyarilari(t) == ["dusuk_kontrast", "dar_kenar"]
    t = s.tasarim_duzelt({"on_renk": "#ffffff", "arka_renk": "#000000"})
    assert "ters_renk" in s.tasarim_uyarilari(t)
    assert s.tasarim_uyarilari(s.tasarim_duzelt({})) == []
    for kotu in ({"on_renk": "red"}, {"boyut": 50}, {"kenar": 11}, {"hata_duzeltme": "X"}):
        with pytest.raises(s.QrHatasi):
            s.tasarim_duzelt(kotu)


def test_logo_hazirla():
    from PIL import Image

    from services import dinamik_qr as s

    cikti = s.logo_hazirla(_png_logo((900, 600)))
    with Image.open(io.BytesIO(base64.b64decode(cikti))) as g:
        assert g.format == "PNG" and max(g.size) == 512
    jpg = _png_logo((40, 40), "JPEG").replace("image/png", "image/jpeg")
    assert s.logo_hazirla(jpg)
    gif = io.BytesIO()
    Image.new("RGB", (32, 32)).save(gif, format="GIF")
    for kotu, kod in (
        (base64.b64encode(gif.getvalue()).decode(), "logo_turu"),
        ("data:image/svg+xml;base64,PHN2Zz4=", "logo_turu"),
        ("bozuk-base64!!", "logo_gecersiz"),
        (base64.b64encode(b"\x89PNG\r\n\x1a\nbozuk").decode(), "logo_gecersiz"),
        ("A" * (700 * 1024), "logo_buyuk"),
    ):
        with pytest.raises(s.QrHatasi) as h:
            s.logo_hazirla(kotu)
        assert h.value.kod == kod


def test_csv_ayristirma():
    from services import dinamik_qr as s

    metin = "ad;tur;hedef;mesaj\nMağaza;url;ornek.com;\nDestek;WhatsApp;+905551112233;Merhaba\nKonum;konum;41.1, 29.0;\n"
    satirlar = [s.csv_satiri(r) for r in s.csv_coz(metin.encode("cp1254"))]
    assert satirlar[0] == {"ad": "Mağaza", "tur": "url", "alanlar": {"url": "ornek.com"}, "kisa_link": False, "takma_ad": None}
    assert satirlar[1]["tur"] == "whatsapp" and satirlar[1]["alanlar"] == {"numara": "+905551112233", "mesaj": "Merhaba"}
    assert satirlar[2]["alanlar"] == {"enlem": "41.1", "boylam": "29.0"}
    kisa = s.csv_satiri(s.csv_coz(b"ad,tur,hedef\nX,kisa link,ornek.com\n")[0])
    assert kisa["tur"] == "url" and kisa["kisa_link"] is True
    for icerik, kod in ((b"isim,adres\nx,y\n", "baslik_eksik"), (b"", "dosya_bos"),
                        (("ad,tur,hedef\n" + "x,url,ornek.com\n" * 501).encode(), "cok_satir"),
                        (b"ad,tur\n" + b"x" * (600 * 1024), "dosya_buyuk")):
        with pytest.raises(s.QrHatasi) as h:
            s.csv_coz(icerik)
        assert h.value.kod == kod


def test_svg_ve_png_ciktisi():
    from services import dinamik_qr as s

    t = s.tasarim_duzelt({"on_renk": "#2a1450", "boyut": 300})
    svg = s.svg_ciz("https://mehmetkuru.dev/q/Abc2345", t).veri.decode()
    assert svg.startswith("<svg ") and 'width="300"' in svg and "viewBox=" in svg and svg.endswith("</svg>")
    assert "<image" not in svg and "#2a1450" in svg
    logo = s.logo_hazirla(_png_logo())
    g = s.svg_ciz("https://mehmetkuru.dev/q/Abc2345", t, logo)
    assert g.hata_duzeltme == "H" and "<image" in g.veri.decode() and "data:image/png;base64," in g.veri.decode()
    p = s.png_ciz("https://mehmetkuru.dev/q/Abc2345", t, logo)
    assert p.veri.startswith(PNG_IMZA) and p.hata_duzeltme == "H"
    with pytest.raises(s.QrHatasi) as h:
        s.svg_ciz("x" * 5000, t)
    assert h.value.kod == "veri_cok_uzun"


# ---------------------------------------------------------------------------
# Yetki, modül kapısı, izolasyon
# ---------------------------------------------------------------------------
async def test_yetki_ve_modul_kapisi(istemci, yonetici_basligi):
    assert (await istemci.get(Y)).status_code == 401
    assert (await istemci.get(Y, headers=_b(_e()))).status_code == 403
    assert (await istemci.get(M)).status_code == 401
    e = _e()
    y = await istemci.get(M, headers=_b(e))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    y = await istemci.post(M, json={"ad": "x", "tur": "url", "alanlar": {"url": "https://a.com"}}, headers=_b(e))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    await _modul_ac(istemci, yonetici_basligi, e)
    y = await istemci.get(M, headers=_b(e))
    assert y.status_code == 200 and y.json() == {"toplam": 0, "items": []}
    meta = (await istemci.get(f"{M}/meta", headers=_b(e))).json()
    assert meta["kayit_siniri"] == 100 and meta["kayit_sayisi"] == 0 and meta["kisa_adres_tabani"] == "https://mehmetkuru.dev/q/"
    # Modül yeniden kapanınca erişim anında düşüyor.
    await _modul_ac(istemci, yonetici_basligi, e, acik=False)
    assert _kod(await istemci.get(M, headers=_b(e))) == "modul_kapali"
    # Engelleme ucu müşteride yok.
    assert (await istemci.post(f"{M}/1/engelle", json={"engelli": False}, headers=_b(e))).status_code in (403, 404, 405)


async def test_musteri_izolasyonu(istemci, yonetici_basligi):
    a = await _musteri(istemci, yonetici_basligi)
    b = await _musteri(istemci, yonetici_basligi)
    qa = await _olustur(istemci, _b(a), M, ad="A'nın QR'ı")
    qb = await _olustur(istemci, _b(b), M, ad="B'nin QR'ı")
    ajans = await _olustur(istemci, yonetici_basligi, Y, ad="Ajans QR")
    assert qa["hesap_email"] == a and ajans["hesap_email"] is None
    liste = (await istemci.get(M, headers=_b(a))).json()["items"]
    assert [x["id"] for x in liste] == [qa["id"]]
    for yol in (f"{M}/{qb['id']}", f"{M}/{ajans['id']}", f"{M}/{qb['id']}/analiz", f"{M}/{qb['id']}/gorsel"):
        y = await istemci.get(yol, headers=_b(a))
        assert y.status_code == 404 and _kod(y) == "bulunamadi", yol
    for metot, yol, govde in (("PUT", f"{M}/{qb['id']}", {"ad": "ele geçir"}), ("DELETE", f"{M}/{qb['id']}", None),
                              ("POST", f"{M}/onizleme", {"qr_id": qb["id"]})):
        y = await istemci.request(metot, yol, json=govde, headers=_b(a))
        assert y.status_code == 404, (metot, yol, y.text)
    y = await istemci.post(f"{M}/zip", json={"idler": [qb["id"], ajans["id"]], "bicim": "svg"}, headers=_b(a))
    assert y.status_code == 404
    # Yönetici hepsini görüyor; hesap süzgeci.
    hepsi = {x["id"] for x in (await istemci.get(Y, headers=yonetici_basligi)).json()["items"]}
    assert {qa["id"], qb["id"], ajans["id"]} <= hepsi
    yalniz_a = (await istemci.get(f"{Y}?hesap={a}", headers=yonetici_basligi)).json()["items"]
    assert [x["id"] for x in yalniz_a] == [qa["id"]]
    ajansin = {x["id"] for x in (await istemci.get(f"{Y}?hesap=ajans", headers=yonetici_basligi)).json()["items"]}
    assert ajans["id"] in ajansin and qa["id"] not in ajansin
    # Müşteri `hesap_email` gönderse de kayıt kendi hesabına yazılıyor.
    q = await _olustur(istemci, _b(a), M, hesap_email=b)
    assert q["hesap_email"] == a


async def test_kayit_siniri_ve_hiz_siniri(istemci, yonetici_basligi, monkeypatch):
    e = await _musteri(istemci, yonetici_basligi, kayit_siniri=2)
    await _olustur(istemci, _b(e), M)
    await _olustur(istemci, _b(e), M)
    y = await istemci.post(M, json={"ad": "3.", "tur": "url", "alanlar": {"url": "https://a.com"}}, headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "kayit_siniri" and y.json()["detail"]["sinir"] == 2
    # Yönetici (ajans) sınırsız; hız sınırı ise herkese.
    from routers import dinamik_qr as r
    from utils.hiz_siniri import HizSiniri

    monkeypatch.setattr(r, "_olusturma_hizi", HizSiniri(2, 60.0))
    await _olustur(istemci, yonetici_basligi, Y)
    await _olustur(istemci, yonetici_basligi, Y)
    y = await istemci.post(Y, json={"ad": "x", "tur": "url", "alanlar": {"url": "https://a.com"}}, headers=yonetici_basligi)
    assert y.status_code == 429 and _kod(y) == "cok_hizli"


# ---------------------------------------------------------------------------
# Oluşturma, kod/takma ad, güncelleme
# ---------------------------------------------------------------------------
async def test_olusturma_dogrulama_ve_javascript_reddi(istemci, yonetici_basligi):
    for govde, kod in (
        ({"ad": "x", "tur": "url", "alanlar": {"url": "javascript:alert(1)"}}, "sema_izinsiz"),
        ({"ad": "x", "tur": "url", "alanlar": {"url": "data:text/html,<script>"}}, "sema_izinsiz"),
        ({"ad": "", "tur": "url", "alanlar": {"url": "https://a.com"}}, "zorunlu"),
        ({"ad": "x", "tur": "yok", "alanlar": {}}, "tur_gecersiz"),
        ({"ad": "x", "tur": "telefon", "alanlar": {"numara": "+905551112233"}, "kisa_link": True}, "kisa_link_yalniz_url"),
        ({"ad": "x", "tur": "url", "alanlar": {"url": "https://a.com"}, "tasarim": {"on_renk": "kırmızı"}}, "renk_gecersiz"),
        ({"ad": "x", "tur": "url", "alanlar": {"url": "https://a.com"}, "tarama_limiti": -1}, "aralik_disi"),
        ({"ad": "x", "tur": "url", "alanlar": {"url": "https://a.com"}, "takma_ad": "admin"}, "takma_ad_ayrilmis"),
        ({"ad": "x", "tur": "url", "alanlar": {"url": "https://a.com"}, "logo": "data:image/gif;base64,R0lG"}, "logo_turu"),
    ):
        y = await istemci.post(Y, json=govde, headers=yonetici_basligi)
        assert y.status_code == 400 and _kod(y) == kod, (govde, y.text)
    # Güncellemede de: hedef javascript: olamaz, eski hedef korunur.
    q = await _olustur(istemci, yonetici_basligi)
    y = await istemci.put(f"{Y}/{q['id']}", json={"alanlar": {"url": "javascript:alert(1)"}}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "sema_izinsiz"
    y = await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())
    assert y.status_code == 302 and y.headers["location"] == "https://ornek.com/sayfa"


async def test_kod_cakismasi_ve_takma_ad(istemci, yonetici_basligi, monkeypatch):
    from services import dinamik_qr as s

    ilk = await _olustur(istemci, yonetici_basligi, takma_ad="Bahar-2026")
    assert len(ilk["kod"]) == 7 and ilk["takma_ad"] == "bahar-2026"
    assert ilk["kisa_adres"] == "https://mehmetkuru.dev/q/bahar-2026"
    assert ilk["qr_adresi"] == f"https://mehmetkuru.dev/q/{ilk['kod']}"
    # Üretici önce var olan kodu, sonra takma adla çakışanı, sonra yenisini veriyor.
    sira = iter([ilk["kod"], "Bahar26", "Yeni234"])
    monkeypatch.setattr(s, "kod_uret", lambda: next(sira))
    await _olustur(istemci, yonetici_basligi, takma_ad="bahar26")  # takma ad "bahar26" artık dolu
    sira2 = iter(["BAHAR26", "Ozgun23"])
    monkeypatch.setattr(s, "kod_uret", lambda: next(sira2))
    q = await _olustur(istemci, yonetici_basligi)
    assert q["kod"] == "Ozgun23"
    # Aynı takma ad, kodla küçük harf çakışan takma ad → 409.
    y = await istemci.post(Y, json={"ad": "x", "tur": "url", "alanlar": {"url": "https://a.com"}, "takma_ad": "BAHAR-2026"},
                           headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "takma_ad_kullaniliyor"
    y = await istemci.post(Y, json={"ad": "x", "tur": "url", "alanlar": {"url": "https://a.com"}, "takma_ad": "ozgun23"},
                           headers=yonetici_basligi)
    assert y.status_code == 409
    # Takma adla ve büyük harfle de çözülüyor.
    for yol in ("bahar-2026", "BAHAR-2026", ilk["kod"]):
        y = await istemci.get(f"{Q}/{yol}", headers=_tarayici())
        assert y.status_code == 302, yol
    # Takma ad kaldırılınca eski takma ad 404, kod çalışmaya devam ediyor.
    y = await istemci.put(f"{Y}/{ilk['id']}", json={"takma_ad": ""}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["takma_ad"] is None
    assert (await istemci.get(f"{Q}/bahar-2026", headers=_tarayici())).status_code == 404
    assert (await istemci.get(f"{Q}/{ilk['kod']}", headers=_tarayici())).status_code == 302


async def test_guncelleme_hedefi_degistirir_kod_ayni(istemci, yonetici_basligi):
    q = await _olustur(istemci, yonetici_basligi, alanlar={"url": "https://eski.com"})
    y = await istemci.put(f"{Y}/{q['id']}", json={"ad": "Yeni ad", "alanlar": {"url": "https://yeni.com", "utm_source": "qr"}},
                          headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["kod"] == q["kod"] and y.json()["ad"] == "Yeni ad"
    r = await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())
    assert r.headers["location"] == "https://yeni.com?utm_source=qr"
    # Tür değişimi (dinamik → dinamik): aynı kod, yeni hedef.
    y = await istemci.put(f"{Y}/{q['id']}", json={"tur": "whatsapp", "alanlar": {"numara": "+905551112233"}},
                          headers=yonetici_basligi)
    assert y.status_code == 200
    assert (await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())).headers["location"] == "https://wa.me/905551112233"


async def test_wifi_statik_parola_korunur_ve_maskeli(istemci, yonetici_basligi, db_oturumu):
    from models.audit_log import AuditLog

    q = await _olustur(istemci, yonetici_basligi, tur="wifi", alanlar={"ssid": "Kafe", "sifre": "cokgizli123"})
    assert q["statik"] is True and q["kisa_adres"] is None and q["alanlar"]["sifre"] == "cokgizli123"
    liste = (await istemci.get(f"{Y}?tur=wifi", headers=yonetici_basligi)).json()["items"]
    assert all("sifre" not in x["alanlar"] for x in liste)
    # Parola gönderilmeden güncelleme: korunuyor.
    y = await istemci.put(f"{Y}/{q['id']}", json={"alanlar": {"ssid": "Kafe 2"}}, headers=yonetici_basligi)
    assert y.json()["alanlar"] == {"ssid": "Kafe 2", "guvenlik": "WPA", "gizli": False, "sifre": "cokgizli123"}
    # Statik QR yönlendirilmiyor (kısa adres yok) ama görseli var.
    assert (await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())).status_code == 404
    g = await istemci.get(f"{Y}/{q['id']}/gorsel?bicim=svg", headers=yonetici_basligi)
    assert g.status_code == 200 and g.text.startswith("<svg")
    # Denetim kaydında parola maskeli.
    satirlar = (await db_oturumu.execute(
        select(AuditLog).where(AuditLog.tablo == "dinamik_qr", AuditLog.kayit_id == str(q["id"]))
    )).scalars().all()
    assert satirlar and all("cokgizli123" not in (s.degisiklik_json or "") for s in satirlar)


# ---------------------------------------------------------------------------
# Kısa adres: 302, 410, 404, dosyalar, User-Agent
# ---------------------------------------------------------------------------
async def test_yonlendirme_302_no_store(istemci, yonetici_basligi):
    q = await _olustur(istemci, yonetici_basligi, alanlar={"url": "https://ornek.com/kampanya", "utm_source": "qr",
                                                           "utm_medium": "afis"})
    y = await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())
    assert y.status_code == 302
    assert y.headers["location"] == "https://ornek.com/kampanya?utm_source=qr&utm_medium=afis"
    assert y.headers["cache-control"] == "no-store"
    assert "noindex" in y.headers["x-robots-tag"]
    h = await istemci.head(f"{Q}/{q['kod']}", headers=_tarayici())
    assert h.status_code == 302


async def test_bilinmeyen_404_pasif_410_yedi_dil(istemci, yonetici_basligi):
    y = await istemci.get(f"{Q}/Yok2345", headers={"Accept-Language": "tr-TR"})
    assert y.status_code == 404 and "Bağlantı bulunamadı" in y.text
    assert '<meta name="robots" content="noindex, nofollow">' in y.text and y.headers["cache-control"] == "no-store"
    assert "noindex" in y.headers["x-robots-tag"] and "default-src 'none'" in y.headers["content-security-policy"]
    assert (await istemci.get(f"{Q}/../etc", headers={})).status_code == 404
    q = await _olustur(istemci, yonetici_basligi, aktif=False)
    beklenen = {
        "tr": "Bu bağlantı şu an etkin değil", "en": "This link is not active right now",
        "de": "Dieser Link ist derzeit nicht aktiv", "ru": "Эта ссылка сейчас неактивна", "zh": "此链接当前不可用",
        "hi": "यह लिंक अभी सक्रिय नहीं है", "ar": "هذا الرابط غير نشط حاليًا",
    }
    for dil, metin in beklenen.items():
        y = await istemci.get(f"{Q}/{q['kod']}", headers={"Accept-Language": f"{dil};q=0.9"})
        assert y.status_code == 410 and metin in y.text, dil
        assert f'lang="{dil}"' in y.text and ('dir="rtl"' in y.text) == (dil == "ar")
    # Yeniden açılınca hemen çalışıyor (410 önbelleğe alınmadı: no-store).
    await istemci.put(f"{Y}/{q['id']}", json={"aktif": True}, headers=yonetici_basligi)
    assert (await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())).status_code == 302


async def test_sure_ve_limit_dolumu(istemci, yonetici_basligi):
    gecmis = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    q = await _olustur(istemci, yonetici_basligi, bitis=gecmis)
    assert q["durum"] == "suresi_doldu"
    assert (await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())).status_code == 410
    gelecek = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    await istemci.put(f"{Y}/{q['id']}", json={"bitis": gelecek}, headers=yonetici_basligi)
    assert (await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())).status_code == 302

    q = await _olustur(istemci, yonetici_basligi, tarama_limiti=2)
    for i in range(2):
        assert (await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici(ip=f"203.0.113.{i}"))).status_code == 302
    # Bot taraması limiti tüketmiyor ama limit dolunca o da 410 alıyor.
    y = await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())
    assert y.status_code == 410
    d = (await istemci.get(f"{Y}/{q['id']}", headers=yonetici_basligi)).json()
    assert d["durum"] == "limit_doldu" and d["tarama_sayisi"] == 2


async def test_vcard_ve_ics_dosyalari(istemci, yonetici_basligi):
    v = await _olustur(istemci, yonetici_basligi, ad="Kartvizit", tur="vcard",
                       alanlar={"ad": "Ayşe", "soyad": "Yılmaz", "telefon_cep": "+905551112233", "eposta": "ayse@ornek.com"})
    y = await istemci.get(f"{Q}/{v['kod']}", headers=_tarayici(IPHONE))
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/vcard")
    assert "attachment" in y.headers["content-disposition"] and ".vcf" in y.headers["content-disposition"]
    assert "FN:Ayşe Yılmaz" in y.text and "EMAIL;TYPE=INTERNET:ayse@ornek.com" in y.text
    assert y.headers["cache-control"] == "no-store"
    e = await _olustur(istemci, yonetici_basligi, ad="Lansman", tur="etkinlik",
                       alanlar={"baslik": "Lansman", "baslangic": "2026-12-01T10:00", "bitis": "2026-12-01T12:00"})
    y = await istemci.get(f"{Q}/{e['kod']}", headers=_tarayici())
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/calendar")
    assert "DTSTART:20261201T070000Z" in y.text and "DTEND:20261201T090000Z" in y.text and ".ics" in y.headers["content-disposition"]


async def test_uygulama_turu_user_agent_yonlendirmesi(istemci, yonetici_basligi):
    q = await _olustur(istemci, yonetici_basligi, tur="uygulama", alanlar={
        "ios": "https://apps.apple.com/tr/app/id123", "android": "https://play.google.com/store/apps/details?id=dev.mk",
        "diger": "https://mehmetkuru.dev/uygulama"})
    for ua, beklenen in ((IPHONE, "https://apps.apple.com/tr/app/id123"),
                         (ANDROID, "https://play.google.com/store/apps/details?id=dev.mk"),
                         (MASAUSTU, "https://mehmetkuru.dev/uygulama")):
        y = await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici(ua))
        assert y.status_code == 302 and y.headers["location"] == beklenen, ua
    # Yalnız iOS bağlantısı varsa Android de oraya düşüyor.
    q = await _olustur(istemci, yonetici_basligi, tur="uygulama", alanlar={"ios": "https://apps.apple.com/app/id9"})
    assert (await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici(ANDROID))).headers["location"] == "https://apps.apple.com/app/id9"


async def test_guvensiz_hedef_taramada_da_engellenir(istemci, yonetici_basligi, db_oturumu):
    from models.dinamik_qr import DinamikQr

    q = await _olustur(istemci, yonetici_basligi)
    k = (await db_oturumu.execute(select(DinamikQr).where(DinamikQr.id == q["id"]))).scalar_one()
    k.hedef = "javascript:alert(document.cookie)"  # veritabanı doğrudan bozulmuş olsa bile
    await db_oturumu.commit()
    y = await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())
    assert y.status_code == 410 and "location" not in y.headers


# ---------------------------------------------------------------------------
# Analitik
# ---------------------------------------------------------------------------
async def test_tarama_analitigi_bot_sayilmaz_ip_ham_saklanmaz(istemci, yonetici_basligi, db_oturumu):
    from models.dinamik_qr import DinamikQrTaramalari

    q = await _olustur(istemci, yonetici_basligi)
    ip = "198.51.100.42"
    await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici(IPHONE, ip, **{"X-MK-Ulke": "TR", "Referer": "https://www.instagram.com/x"}))
    await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici(IPHONE, ip, **{"X-MK-Ulke": "TR"}))
    await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici(MASAUSTU, "198.51.100.43", **{"X-MK-Ulke": "DE"}))
    # Bağlantı önizleyicileri ve HEAD: yönlendirme çalışıyor ama sayılmıyor.
    y = await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici(WHATSAPP, "198.51.100.44"))
    assert y.status_code == 302
    await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici("Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)"))
    await istemci.head(f"{Q}/{q['kod']}", headers=_tarayici())

    d = (await istemci.get(f"{Y}/{q['id']}", headers=yonetici_basligi)).json()
    assert d["tarama_sayisi"] == 3 and d["son_tarama_at"]
    a = (await istemci.get(f"{Y}/{q['id']}/analiz", headers=yonetici_basligi)).json()
    assert (a["toplam"], a["tekil"], a["bot"]) == (3, 2, 3)
    assert len(a["gunluk"]) == 30 and a["gunluk"][-1] == {"gun": datetime.now(timezone.utc).date().isoformat(), "tarama": 3, "tekil": 2}
    assert a["donem"] == {"gun": 30, "tarama": 3, "tekil": 2}
    assert {x["anahtar"]: x["sayi"] for x in a["ulkeler"]} == {"TR": 2, "DE": 1}
    assert {x["anahtar"]: x["sayi"] for x in a["cihazlar"]} == {"mobil": 2, "masaustu": 1}
    assert {x["anahtar"]: x["sayi"] for x in a["isletim"]} == {"ios": 2, "windows": 1}
    assert a["refererlar"] == [{"anahtar": "instagram.com", "sayi": 1}]
    assert len((await istemci.get(f"{Y}/{q['id']}/analiz?gun=7", headers=yonetici_basligi)).json()["gunluk"]) == 7

    satirlar = (await db_oturumu.execute(select(DinamikQrTaramalari).where(DinamikQrTaramalari.qr_id == q["id"]))).scalars().all()
    assert len(satirlar) == 6 and sum(1 for x in satirlar if x.bot) == 3
    sutunlar = {c.name for c in DinamikQrTaramalari.__table__.columns}
    assert not {"ip", "ip_adresi", "user_agent", "ua"} & sutunlar
    for x in satirlar:
        degerler = " ".join(str(getattr(x, c)) for c in sutunlar)
        assert ip not in degerler and "Mozilla" not in degerler and "iPhone" not in degerler
        assert len(x.ip_ozeti) == 64
    # Aynı IP farklı günde farklı özet (günler arası izleme yok).
    from utils.istemci_ip import ip_ozeti

    assert ip_ozeti(f"qr|2026-01-01|{ip}") != ip_ozeti(f"qr|2026-01-02|{ip}")


async def test_tarama_seli_kaydedilmez_yonlendirme_calisir(istemci, yonetici_basligi, monkeypatch):
    from routers import dinamik_qr as r
    from utils.hiz_siniri import HizSiniri

    monkeypatch.setattr(r, "_tarama_hizi", HizSiniri(2, 60.0))
    q = await _olustur(istemci, yonetici_basligi)
    for _ in range(4):
        assert (await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())).status_code == 302
    assert (await istemci.get(f"{Y}/{q['id']}", headers=yonetici_basligi)).json()["tarama_sayisi"] == 2


# ---------------------------------------------------------------------------
# Görsel, önizleme, logo
# ---------------------------------------------------------------------------
async def test_gorsel_indirme_png_svg_ve_logo(istemci, yonetici_basligi):
    q = await _olustur(istemci, yonetici_basligi, ad="Mağaza Girişi", tasarim={"on_renk": "#2a1450", "boyut": 256},
                       logo=_png_logo())
    assert q["logo_var"] is True and q["tasarim"]["boyut"] == 256
    p = await istemci.get(f"{Y}/{q['id']}/gorsel?bicim=png", headers=yonetici_basligi)
    assert p.status_code == 200 and p.content.startswith(PNG_IMZA) and p.headers["content-type"] == "image/png"
    assert f"qr-{q['kod']}-magaza-girisi.png" in p.headers["content-disposition"]
    svg = await istemci.get(f"{Y}/{q['id']}/gorsel?bicim=svg&boyut=1024", headers=yonetici_basligi)
    assert svg.text.startswith("<svg ") and 'width="1024"' in svg.text and "<image" in svg.text
    assert (await istemci.get(f"{Y}/{q['id']}/gorsel?bicim=gif", headers=yonetici_basligi)).status_code == 400
    # Logo kaldırma.
    y = await istemci.put(f"{Y}/{q['id']}", json={"logo_kaldir": True}, headers=yonetici_basligi)
    assert y.json()["logo_var"] is False
    svg = await istemci.get(f"{Y}/{q['id']}/gorsel?bicim=svg", headers=yonetici_basligi)
    assert "<image" not in svg.text


async def test_onizleme_svg_ve_uyarilar(istemci, yonetici_basligi):
    y = await istemci.post(f"{Y}/onizleme", json={"tur": "url", "tasarim": {"on_renk": "#bbbbbb", "arka_renk": "#ffffff"}},
                           headers=yonetici_basligi)
    assert y.status_code == 200
    g = y.json()
    assert g["svg"].startswith("<svg ") and "dusuk_kontrast" in g["uyarilar"] and g["kontrast"] < 4
    y = await istemci.post(f"{Y}/onizleme", json={"tur": "url", "logo": _png_logo()}, headers=yonetici_basligi)
    assert y.json()["hata_duzeltme"] == "H" and "<image" in y.json()["svg"]
    # Statik türde alanlar doğrulanıyor.
    y = await istemci.post(f"{Y}/onizleme", json={"tur": "wifi", "alanlar": {"ssid": ""}}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "zorunlu"
    y = await istemci.post(f"{Y}/onizleme", json={"tur": "metin", "alanlar": {"metin": "Merhaba dünya"}}, headers=yonetici_basligi)
    assert y.status_code == 200


# ---------------------------------------------------------------------------
# Toplu CSV + ZIP, kısa link süzgeci
# ---------------------------------------------------------------------------
async def test_toplu_csv_onizleme_olustur_ve_zip(istemci, yonetici_basligi):
    e = await _musteri(istemci, yonetici_basligi, kayit_siniri=3)
    csv_metni = (
        "ad;tur;hedef;mesaj;takma_ad\n"
        "Vitrin;url;ornek.com/vitrin;;vitrin-" + uuid.uuid4().hex[:6] + "\n"
        "WhatsApp;whatsapp;+905551112233;Merhaba;\n"
        "Kötü;url;javascript:alert(1);;\n"
        "Bilinmeyen;faks;123;;\n"
        "Kafe Wi-Fi;wifi;KafeAg;;\n"
        "Kısa;kisa link;ornek.com/k;;\n"
        "Fazla;metin;Merhaba;;\n"
    )
    y = await istemci.post(f"{M}/toplu/onizleme", files={"dosya": ("liste.csv", csv_metni.encode("utf-8"), "text/csv")},
                           headers=_b(e))
    assert y.status_code == 200, y.text
    o = y.json()
    assert (o["toplam"], o["gecerli"], o["hatali"], o["kalan_hak"]) == (7, 4, 3, 3)
    hatalar = {x["satir"]: x["hata"]["kod"] for x in o["satirlar"] if not x["gecerli"]}
    assert hatalar == {4: "sema_izinsiz", 5: "tur_gecersiz", 6: "sifre_gecersiz"}
    gecerli = [x for x in o["satirlar"] if x["gecerli"]]
    assert gecerli[2]["tur"] == "url" and gecerli[2]["kisa_link"] is True
    y = await istemci.post(f"{M}/toplu/olustur", json={"satirlar": gecerli, "tasarim": {"on_renk": "#123456"}}, headers=_b(e))
    assert y.status_code == 200
    sonuc = y.json()
    assert len(sonuc["olusturulan"]) == 3 and sonuc["hatalar"] == [{"satir": 8, "kod": "kayit_siniri", "sinir": 3}]
    assert all(x["hesap_email"] == e and x["tasarim"]["on_renk"] == "#123456" for x in sonuc["olusturulan"])
    kisa = (await istemci.get(f"{M}?kisa=true", headers=_b(e))).json()["items"]
    assert [x["ad"] for x in kisa] == ["Kısa"]
    idler = [x["id"] for x in sonuc["olusturulan"]]
    z = await istemci.post(f"{M}/zip", json={"idler": idler, "bicim": "png"}, headers=_b(e))
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(z.content)) as arsiv:
        adlar = arsiv.namelist()
        assert len(adlar) == 3 and all(a.endswith(".png") for a in adlar)
        assert all(arsiv.read(a).startswith(PNG_IMZA) for a in adlar)
    z = await istemci.post(f"{M}/zip", json={"idler": idler, "bicim": "svg"}, headers=_b(e))
    with zipfile.ZipFile(io.BytesIO(z.content)) as arsiv:
        assert all(arsiv.read(a).startswith(b"<svg ") for a in arsiv.namelist())
    # Sınırlar.
    y = await istemci.post(f"{M}/toplu/olustur", json={"satirlar": [{}] * 501}, headers=_b(e))
    assert y.status_code == 400 and _kod(y) == "cok_satir"
    buyuk = b"ad,tur,hedef\n" + b"x,url,ornek.com\n" * 501
    y = await istemci.post(f"{Y}/toplu/onizleme", files={"dosya": ("b.csv", buyuk, "text/csv")}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "cok_satir"


# ---------------------------------------------------------------------------
# Yönetici engeli, çöp kutusu
# ---------------------------------------------------------------------------
async def test_yonetici_engeli_musteri_kaldiramaz(istemci, yonetici_basligi):
    e = await _musteri(istemci, yonetici_basligi)
    q = await _olustur(istemci, _b(e), M)
    y = await istemci.post(f"{Y}/{q['id']}/engelle", json={"engelli": True}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "engelli"
    assert (await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())).status_code == 410
    y = await istemci.put(f"{M}/{q['id']}", json={"aktif": True, "engelli": False}, headers=_b(e))
    assert y.status_code == 200 and y.json()["engelli"] is True and y.json()["durum"] == "engelli"
    assert (await istemci.post(f"{Y}/{q['id']}/engelle", json={"engelli": True}, headers=_b(e))).status_code == 403
    await istemci.post(f"{Y}/{q['id']}/engelle", json={"engelli": False}, headers=yonetici_basligi)
    assert (await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())).status_code == 302


async def test_silme_cop_kutusuna_logo_ile_ve_geri_alma(istemci, yonetici_basligi, db_oturumu):
    from models.cop_kutusu import CopKutusu

    e = await _musteri(istemci, yonetici_basligi)
    q = await _olustur(istemci, _b(e), M, logo=_png_logo(), takma_ad="geri-" + uuid.uuid4().hex[:6])
    assert (await istemci.delete(f"{M}/{q['id']}", headers=_b(e))).json() == {"ok": True}
    assert (await istemci.get(f"{M}/{q['id']}", headers=_b(e))).status_code == 404
    assert (await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())).status_code == 404
    kopyalar = (await db_oturumu.execute(
        select(CopKutusu).where(CopKutusu.tablo.in_(("dinamik_qr", "dinamik_qr_logolari")), CopKutusu.sahip_email == e)
    )).scalars().all()
    assert {k.tablo for k in kopyalar} == {"dinamik_qr", "dinamik_qr_logolari"}
    ana = next(k for k in kopyalar if k.tablo == "dinamik_qr")
    y = await istemci.post(f"/api/v1/cop-kutum/{ana.id}/geri-al", headers=_b(e))
    assert y.status_code == 200, y.text
    d = (await istemci.get(f"{M}/{q['id']}", headers=_b(e))).json()
    assert d["kod"] == q["kod"] and d["logo_var"] is True
    svg = await istemci.get(f"{M}/{q['id']}/gorsel?bicim=svg", headers=_b(e))
    assert "<image" in svg.text
    assert (await istemci.get(f"{Q}/{q['kod']}", headers=_tarayici())).status_code == 302
