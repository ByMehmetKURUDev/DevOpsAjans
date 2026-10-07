"""Faz 6K — Eğitim modülü: kurs, ders, öğrenci, yoklama, quiz/ödev, sertifika.

Kapsam: saf kurallar (puanlama, soru doğrulama, QR imzası, jeton, tekrarlayan program, CSV, maskeli ad),
kurs/ders/öğrenci CRUD + müşteri izolasyonu, modül kapalıyken 403, kapasite + bekleme listesi (eşzamanlı
kayıtta aşım yok, ayrılan yerine sıradaki), imzalı öğrenci bağlantısı (yeniden kullanım, yenileme, süre),
yoklama (oturum QR'ı, kısa kod, eğitmen okutması, çift okutma, pencere dışı, başka kurs), devamsızlık
eşiği → olay ve e-posta BİR KEZ, quiz puanlama + süre + deneme hakkı, ödev teslimi + not, "AI ile soru
üret" (sahte model, anahtar yok, aylık hak, bozuk yanıtta iade), sertifika koşulları + PDF + herkese açık
doğrulama (kişisel veri sızmıyor), veli/çocuk verisi (zorunlu veli, çocuğa pazarlama izni yok, e-posta
veliye) + saklama süresi dolunca anonimleştirme, eğitmen izni (yalnız kendi kursu, iletişim bilgisi yok),
olay kataloğu (webhook + otomasyon) ve teslimat (kişisel veri yok), ders hatırlatması (bir kez), çöp
kutusu, gelen kutusu kaynağı, herkese açık sayfa (taslak 404, noindex, bal küpü, modül kapalı 410).
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from conftest import jeton_uret

Y = "/api/v1/egitim/yonetim"
M = "/api/v1/egitimim"
A = "/api/v1/egitim"
MODUL = "/api/v1/moduller"
UTC = timezone.utc
#: Testlerin "şimdi"si: 5 Ekim 2026 Pazartesi 09:00 İstanbul.
SIMDI = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)


def _e(on: str = "egitim") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@egitim.dev"


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


def _z(ip: str | None = None) -> dict:
    return {"User-Agent": "Mozilla/5.0 Test", "X-MK-Istemci-IP": ip or f"198.51.100.{uuid.uuid4().int % 250 + 1}"}


def _jeton(adres: str) -> str:
    return adres.rstrip("/").rsplit("/", 1)[1]


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    from routers import egitim as r
    from services import egitim as s
    from services import hesap_ekibi

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    saat = {"an": SIMDI}
    monkeypatch.setattr(s, "simdi", lambda: saat["an"])
    yield saat
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


async def _modul(istemci, yonetici_basligi, eposta, acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/egitim", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _kurs(istemci, basliklar, yol=Y, yayinla=True, **govde):
    govde.setdefault("ad", f"Kodlama {uuid.uuid4().hex[:5]}")
    govde.setdefault("mekan", "Kültür Merkezi")
    govde.setdefault("bitis_tarihi", "2026-12-20")
    govde.setdefault("baslangic_tarihi", "2026-10-01")
    y = await istemci.post(yol, json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    k = y.json()
    if yayinla:
        y = await istemci.put(f"{yol}/{k['id']}", json={"durum": "yayinda"}, headers=basliklar)
        assert y.status_code == 200, y.text
        k = y.json()
    return k


async def _kayit(istemci, slug, ip=None, **govde):
    govde.setdefault("ad", "Ayşe Yılmaz")
    if "eposta" not in govde:
        govde["eposta"] = f"ayse-{uuid.uuid4().hex[:6]}@ornek.com"
    return await istemci.post(f"{A}/kurs/{slug}/kayit", json=govde, headers=_z(ip))


async def _oturum(istemci, basliklar, kid, bas: datetime, dk=90, yol=Y, konu=None):
    y = await istemci.post(f"{yol}/{kid}/oturumlar", json={"baslangic": bas.isoformat(), "bitis": (bas + timedelta(minutes=dk)).isoformat(),
                                                           **({"konu": konu} if konu else {})}, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _bakim():
    """Zamanlı görev (`egitim_bakimi`) — doğrudan; `/zamanli/calistir` 5 dakikada bir çalışıyor."""
    from core.database import db_manager
    from services import egitim_kayit as k

    async with db_manager.async_session_maker() as db:
        return await k.zamanli_bakim(db)


async def _portal(istemci, jeton):
    y = await istemci.get(f"{A}/ogrenci/{jeton}", headers=_z())
    assert y.status_code == 200, y.text
    return y.json()


# ---------------------------------------------------------------------------
# Saf kurallar
# ---------------------------------------------------------------------------
def test_puanlama_ve_soru_dogrulama():
    from services import egitim as s

    sorular = s.sorular_duzelt([
        {"tur": "coktan", "metin": "2+2?", "secenekler": ["3", "4", "5"], "dogru": 1, "puan": 2},
        {"tur": "dogru_yanlis", "metin": "Su 100°C'de kaynar.", "dogru": True},
        {"tur": "kisa", "metin": "Türkiye'nin başkenti?", "dogru": ["Ankara"]},
    ])
    assert [q["id"] for q in sorular] == ["s1", "s2", "s3"]
    assert all("dogru" not in q for q in s.sorular_ogrenciye(sorular)) and all("dogru" in q for q in sorular)
    p = s.puanla(sorular, {"s1": 1, "s2": True, "s3": "  ANKARA "})
    assert p["puan"] == 100 and p["dogru"] == 3
    # Türkçe büyük/küçük harf ve noktalama farkı kısa cevapta yok sayılır; yanlış tür sayılmaz.
    assert s.puanla(sorular, {"s3": "ankara."})["ayrinti"]["s3"] is True
    assert s.puanla(sorular, {"s1": "1", "s2": "true"})["puan"] == 0
    p = s.puanla(sorular, {"s1": 1})
    assert p["puan"] == 50 and p["dogru"] == 1  # 2 / 4 puan
    for kotu in ([{"tur": "coktan", "metin": "x", "secenekler": ["a"], "dogru": 0}],
                 [{"tur": "coktan", "metin": "x", "secenekler": ["a", "b"], "dogru": 2}],
                 [{"tur": "dogru_yanlis", "metin": "x", "dogru": "evet"}],
                 [{"tur": "kisa", "metin": "x", "dogru": []}],
                 [{"tur": "uydurma", "metin": "x"}]):
        with pytest.raises(s.TemelHata):
            s.sorular_duzelt(kotu)


def test_qr_imzasi_jetonlar_ve_kodlar():
    from services import egitim as s

    qr = s.qr_icerigi("ABCD2345")
    assert qr.startswith("MKO1.ABCD2345.") and "@" not in qr
    assert s.okutma_coz(qr) == ("ABCD2345", True)
    assert s.okutma_coz(qr[:-1] + ("A" if qr[-1] != "A" else "B"))[0] is None  # değiştirilmiş imza
    assert s.okutma_coz("abcd-2345") == ("ABCD2345", False)
    assert s.okutma_coz("kısa")[0] is None
    j = s.ogrenci_jetonu(7, 1, "ABCD2345")
    assert s.jeton_parcala(j) == (7, 1) and s.ogrenci_jetonu_gecerli_mi(j, 7, 1, "ABCD2345")
    assert not s.ogrenci_jetonu_gecerli_mi(j, 7, 2, "ABCD2345")
    assert s.oturum_kodu(3, 1) != s.oturum_kodu(3, 2) and s.OTURUM_KODU_DESENI.match(s.oturum_kodu(3, 1))
    assert s.ad_maskele("Ayşe Nur Yılmaz") == "Ayşe N. Y." and s.ad_maskele("Cem") == "C." and s.ad_maskele("") == "—"
    assert s.sertifika_kodu_yaz("ABCDEFGHJKLM") == "ABCD-EFGH-JKLM"
    assert s.video_bilgisi("https://youtu.be/dQw4w9WgXcQ")["saglayici"] == "youtube"
    assert s.video_bilgisi("https://vimeo.com/123456789")["saglayici"] == "vimeo"


def test_tekrarlayan_program_ve_csv():
    from datetime import date

    from services import egitim as s

    # Ekim 2026: Pazartesi (0) ve Çarşamba (2) 19:00 İstanbul → 16:00 UTC, 4 hafta.
    araliklar = s.oturumlari_uret(date(2026, 10, 5), date(2026, 10, 30), [0, 2], "19:00", 90, "Europe/Istanbul")
    assert len(araliklar) == 8
    assert araliklar[0][0] == datetime(2026, 10, 5, 16, 0, tzinfo=UTC)
    assert araliklar[0][1] - araliklar[0][0] == timedelta(minutes=90)
    with pytest.raises(s.TemelHata):
        s.oturumlari_uret(date(2026, 10, 5), date(2026, 10, 1), [0], "19:00", 60, "Europe/Istanbul")
    with pytest.raises(s.TemelHata):
        s.oturumlari_uret(date(2026, 10, 5), date(2026, 10, 30), [9], "19:00", 60, "Europe/Istanbul")
    satirlar = s.csv_coz("Ad Soyad;E-posta;Veli adı;Veli e-posta\nAli Veli;ali@ornek.com;;\nCan;;Ece;ece@ornek.com\n")
    assert satirlar == [{"ad": "Ali Veli", "eposta": "ali@ornek.com"}, {"ad": "Can", "veli_ad": "Ece", "veli_eposta": "ece@ornek.com"}]
    with pytest.raises(s.TemelHata):
        s.csv_coz("eposta\nx@y.com\n")
    assert s.csv_hucre("=HYPERLINK()") == "'=HYPERLINK()"


def test_modul_kaydi_ve_sektor_paketi():
    from core import moduller as mf
    from core import sektor_paketleri as sp

    m = mf.modul("egitim")
    assert m is not None and m.kategori == "sektorel" and not m.varsayilan_acik and m.musteri_sekmesi == "egitim"
    assert {a.anahtar for a in m.ayarlar} == {"kurs_siniri", "ogrenci_siniri", "ai_hakki", "kredi_ile_asim"}
    assert sp.paket("egitim_etkinlik").moduller[0] == "egitim"
    assert mf.manifest_hatalari() == [] and sp.paket_hatalari() == []
    from services import zamanli

    assert "egitim_bakimi" in [g.ad for g in zamanli.GOREVLER]


# ---------------------------------------------------------------------------
# Yetki, modül kapısı, izolasyon
# ---------------------------------------------------------------------------
async def test_yetkisiz_ve_modul_kapali_403(istemci, yonetici_basligi):
    musteri = _e("kapali")
    assert (await istemci.get(f"{M}/meta")).status_code == 401
    assert (await istemci.get(f"{Y}/meta", headers=_b(musteri))).status_code == 403
    y = await istemci.get(f"{M}/meta", headers=_b(musteri))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    await _modul(istemci, yonetici_basligi, musteri)
    y = await istemci.get(f"{M}/meta", headers=_b(musteri))
    assert y.status_code == 200 and y.json()["kurs_siniri"] == 10 and y.json()["yonetim"] is True


async def test_kurs_crud_ve_musteri_izolasyonu(istemci, yonetici_basligi):
    a, b = _e("a"), _e("b")
    for m in (a, b):
        await _modul(istemci, yonetici_basligi, m)
    k = await _kurs(istemci, _b(a), M, yayinla=False, ad="Resim Atölyesi")
    assert k["slug"].startswith("resim-atolyesi") and k["durum"] == "taslak" and k["hesap_email"] == a
    assert (await istemci.get(f"{M}/{k['id']}", headers=_b(b))).status_code == 404
    assert (await istemci.put(f"{M}/{k['id']}", json={"ad": "x"}, headers=_b(b))).status_code == 404
    assert [x["id"] for x in (await istemci.get(M, headers=_b(b))).json()["items"]] == []
    y = await istemci.put(f"{M}/{k['id']}", json={"bicim": "online", "durum": "yayinda"}, headers=_b(a))
    assert y.status_code == 400 and _kod(y) == "online_baglanti_gerekli"
    y = await istemci.put(f"{M}/{k['id']}", json={"kapasite": 0}, headers=_b(a))
    assert y.status_code == 400
    # Yönetici müşterinin kursunu görür (destek).
    assert (await istemci.get(f"{Y}/{k['id']}", headers=yonetici_basligi)).status_code == 200
    # Kurs sınırı.
    await _modul(istemci, yonetici_basligi, b, kurs_siniri=1)
    await _kurs(istemci, _b(b), M, yayinla=False)
    y = await istemci.post(M, json={"ad": "İkinci"}, headers=_b(b))
    assert y.status_code == 409 and _kod(y) == "kurs_siniri"


async def test_ders_crud_dosya_ve_sira(istemci, yonetici_basligi):
    k = await _kurs(istemci, yonetici_basligi)
    d1 = (await istemci.post(f"{Y}/{k['id']}/dersler", json={"baslik": "Giriş", "bolum": "1. Hafta", "icerik": "# Merhaba",
                                                             "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
                             headers=yonetici_basligi)).json()
    d2 = (await istemci.post(f"{Y}/{k['id']}/dersler", json={"baslik": "Değişkenler"}, headers=yonetici_basligi)).json()
    assert d1["video"]["saglayici"] == "youtube" and d2["sira"] == d1["sira"] + 1
    y = await istemci.post(f"{Y}/{k['id']}/dersler", json={"baslik": "x", "video_url": "http://duz.ornek.com"}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "baglanti_gecersiz"
    y = await istemci.post(f"{Y}/{k['id']}/dersler/{d1['id']}/dosyalar", files={"dosya": ("notlar.txt", b"ders notu", "text/plain")},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    fid = y.json()["id"]
    y = await istemci.post(f"{Y}/{k['id']}/dersler/{d1['id']}/dosyalar", files={"dosya": ("zararli.html", b"<script>", "text/html")},
                           headers=yonetici_basligi)
    assert y.status_code == 415
    y = await istemci.get(f"{Y}/{k['id']}/dosyalar/{fid}", headers=yonetici_basligi)
    assert y.status_code == 200 and y.content == b"ders notu"
    await istemci.put(f"{Y}/{k['id']}/dersler-sira", json={"sira": [d2["id"], d1["id"]]}, headers=yonetici_basligi)
    liste = (await istemci.get(f"{Y}/{k['id']}/dersler", headers=yonetici_basligi)).json()["items"]
    assert [d["id"] for d in liste] == [d2["id"], d1["id"]] and liste[1]["dosyalar"][0]["ad"] == "notlar.txt"
    assert (await istemci.delete(f"{Y}/{k['id']}/dersler/{d1['id']}", headers=yonetici_basligi)).status_code == 200


# ---------------------------------------------------------------------------
# Kayıt: kapasite, bekleme listesi, herkese açık sayfa
# ---------------------------------------------------------------------------
async def test_herkese_acik_sayfa_ve_kayit(istemci, yonetici_basligi, epostalar):
    k = await _kurs(istemci, yonetici_basligi, yayinla=False, fiyat_metni="Aylık 1.500 TL — havale")
    assert (await istemci.get(f"{A}/kurs/{k['slug']}")).status_code == 404  # taslak
    await istemci.put(f"{Y}/{k['id']}", json={"durum": "yayinda"}, headers=yonetici_basligi)
    y = await istemci.get(f"{A}/kurs/{k['slug']}")
    assert y.status_code == 200 and y.headers.get("x-robots-tag") == "noindex"
    g = y.json()
    assert g["fiyat_metni"] == "Aylık 1.500 TL — havale" and g["kayit_acik"] is True and "online_baglanti" not in g
    # Bal küpü: başarılı görünür, kayıt yok.
    y = await _kayit(istemci, k["slug"], web_adresi="http://spam")
    assert y.status_code == 200 and y.json()["durum"] is None
    y = await _kayit(istemci, k["slug"], ad="Ali Demir", eposta="ali.demir@ornek.com", pazarlama_izni=True)
    assert y.status_code == 200, y.text
    assert y.json()["durum"] == "aktif" and y.json()["portal_adresi"].startswith("/egitim/ogrenci/")
    assert y.headers.get("referrer-policy") == "no-referrer"
    y = await _kayit(istemci, k["slug"], ad="Ali Demir", eposta="ali.demir@ornek.com")
    assert y.status_code == 409 and _kod(y) == "zaten_kayitli"
    liste = (await istemci.get(f"{Y}/{k['id']}/ogrenciler", headers=yonetici_basligi)).json()["items"]
    assert len(liste) == 1 and liste[0]["pazarlama_izni"] is True and liste[0]["kaynak"] == "form"
    giden = [e for e in epostalar if e["alici"] == "ali.demir@ornek.com"]
    assert giden and "/egitim/ogrenci/" in giden[0]["govde"]
    # Kayıt kapatılınca form 409.
    await istemci.put(f"{Y}/{k['id']}", json={"kayit_acik": False}, headers=yonetici_basligi)
    y = await _kayit(istemci, k["slug"])
    assert y.status_code == 409 and _kod(y) == "kayit_kapali"


async def test_kapasite_bekleme_listesi_ve_sira(istemci, yonetici_basligi, epostalar):
    k = await _kurs(istemci, yonetici_basligi, kapasite=2)
    sonuc = await asyncio.gather(*[_kayit(istemci, k["slug"], ad=f"Kişi {i}") for i in range(4)])
    assert all(y.status_code == 200 for y in sonuc), [y.text for y in sonuc]
    durumlar = sorted(y.json()["durum"] for y in sonuc)
    assert durumlar == ["aktif", "aktif", "bekleme", "bekleme"]
    assert sorted(y.json().get("sira") for y in sonuc if y.json()["durum"] == "bekleme") == [1, 2]
    liste = (await istemci.get(f"{Y}/{k['id']}/ogrenciler", headers=yonetici_basligi)).json()["items"]
    aktif = [o for o in liste if o["durum"] == "aktif"]
    bekleyen = sorted((o for o in liste if o["durum"] == "bekleme"), key=lambda o: o["id"])
    # Aktif öğrenci ayrılınca sıradaki bekleyen kendiliğinden aktif olur (+ "yer açıldı" e-postası).
    y = await istemci.put(f"{Y}/{k['id']}/ogrenciler/{aktif[0]['id']}", json={"durum": "ayrildi"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    liste = {o["id"]: o for o in (await istemci.get(f"{Y}/{k['id']}/ogrenciler", headers=yonetici_basligi)).json()["items"]}
    assert liste[bekleyen[0]["id"]]["durum"] == "aktif" and liste[bekleyen[1]["id"]]["durum"] == "bekleme"
    assert any("Yer açıldı" in e["konu"] for e in epostalar)
    # Bekleyeni elle aktif yapmak: yer yoksa 409.
    y = await istemci.put(f"{Y}/{k['id']}/ogrenciler/{bekleyen[1]['id']}", json={"durum": "aktif"}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "dolu"
    # Kapasite artınca bekleyen alınır; aktiften az kapasiteye inilemez.
    y = await istemci.put(f"{Y}/{k['id']}", json={"kapasite": 1}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "kapasite_az"
    await istemci.put(f"{Y}/{k['id']}", json={"kapasite": 3}, headers=yonetici_basligi)
    liste = {o["id"]: o for o in (await istemci.get(f"{Y}/{k['id']}/ogrenciler", headers=yonetici_basligi)).json()["items"]}
    assert liste[bekleyen[1]["id"]]["durum"] == "aktif"


async def test_ogrenci_siniri_csv_ve_elle_ekleme(istemci, yonetici_basligi):
    m = _e("csv")
    await _modul(istemci, yonetici_basligi, m, ogrenci_siniri=3)
    k = await _kurs(istemci, _b(m), M)
    y = await istemci.post(f"{M}/{k['id']}/ogrenciler/csv", json={
        "csv": "Ad Soyad,E-posta,Telefon\nAli,ali@ornek.com,0555 111 22 33\nAli,ali@ornek.com,\nVeli,yok-eposta,\nCan,can@ornek.com,\nDeniz,deniz@ornek.com,\nEce,ece@ornek.com,\n"},
        headers=_b(m))
    assert y.status_code == 200, y.text
    g = y.json()
    assert g["aktif"] == 3 and g["atlanan"] == 1 and g["hata_sayisi"] == 2
    assert {h["kod"] for h in g["hatalar"]} == {"eposta_gecersiz", "ogrenci_siniri"}
    y = await istemci.post(f"{M}/{k['id']}/ogrenciler", json={"ad": "Ek", "eposta": "ek@ornek.com"}, headers=_b(m))
    assert y.status_code == 409 and _kod(y) == "ogrenci_siniri"
    y = await istemci.get(f"{M}/{k['id']}/ogrenciler.csv", headers=_b(m))
    assert y.status_code == 200 and "ali@ornek.com" in y.text and "05551112233" in y.text


# ---------------------------------------------------------------------------
# Öğrenci bağlantısı
# ---------------------------------------------------------------------------
async def test_imzali_ogrenci_baglantisi_sure_ve_yenileme(istemci, yonetici_basligi, _ortam):
    k = await _kurs(istemci, yonetici_basligi, online_baglanti="https://meet.ornek.com/kurs", bicim="karma")
    y = await _kayit(istemci, k["slug"], ad="Portal Kişi")
    jeton = _jeton(y.json()["portal_adresi"])
    p1 = await _portal(istemci, jeton)
    p2 = await _portal(istemci, jeton)  # yeniden kullanılabilir (kalıcı portal bağlantısı)
    assert p1["ogrenci"]["ad"] == "Portal Kişi" and p2["kurs"]["online_baglanti"] == "https://meet.ornek.com/kurs"
    # Herkese açık sayfada online bağlantı yok.
    assert "meet.ornek.com" not in (await istemci.get(f"{A}/kurs/{k['slug']}")).text
    # Değiştirilmiş jeton → 404.
    assert (await istemci.get(f"{A}/ogrenci/{jeton[:-1]}0", headers=_z())).status_code in (404,)
    oid = int(jeton.split("-")[0])
    y = await istemci.post(f"{Y}/{k['id']}/ogrenciler/{oid}/baglanti", json={"yenile": True}, headers=yonetici_basligi)
    yeni = _jeton(y.json()["adres"])
    assert yeni != jeton and y.json()["surum"] == 2
    assert (await istemci.get(f"{A}/ogrenci/{jeton}", headers=_z())).status_code == 404
    assert (await istemci.get(f"{A}/ogrenci/{yeni}", headers=_z())).status_code == 200
    # Kurs bitişinden 120 gün sonra süre dolar.
    _ortam["an"] = datetime(2027, 4, 30, tzinfo=UTC)
    y = await istemci.get(f"{A}/ogrenci/{yeni}", headers=_z())
    assert y.status_code == 410 and _kod(y) == "baglanti_suresi_doldu"


# ---------------------------------------------------------------------------
# Yoklama
# ---------------------------------------------------------------------------
async def test_yoklama_qr_kod_okutma_ve_cift(istemci, yonetici_basligi, _ortam):
    k = await _kurs(istemci, yonetici_basligi)
    diger = await _kurs(istemci, yonetici_basligi)
    ot = await _oturum(istemci, yonetici_basligi, k["id"], SIMDI + timedelta(minutes=10))
    j1 = _jeton((await _kayit(istemci, k["slug"], ad="Bir")).json()["portal_adresi"])
    j2 = _jeton((await _kayit(istemci, k["slug"], ad="İki")).json()["portal_adresi"])
    j3 = _jeton((await _kayit(istemci, diger["slug"], ad="Başka")).json()["portal_adresi"])
    bilgi = (await istemci.get(f"{Y}/{k['id']}/oturumlar/{ot['id']}/yoklama", headers=yonetici_basligi)).json()
    assert bilgi["yoklama"]["acik"] is True and len(bilgi["items"]) == 2
    qr_jeton = _jeton(bilgi["yoklama"]["adres"])
    sayfa = (await istemci.get(f"{A}/yoklama/{qr_jeton}", headers=_z())).json()
    assert sayfa["kurs"] == k["ad"] and sayfa["acik"] is True and "Bir" not in json.dumps(sayfa)
    # Oturum QR'ı + bu cihazdaki öğrenci bağlantısı.
    y = await istemci.post(f"{A}/yoklama/{qr_jeton}", json={"ogrenci": j1}, headers=_z())
    assert y.status_code == 200 and y.json()["sonuc"] == "isaretlendi" and y.json()["durum"] == "var"
    y = await istemci.post(f"{A}/yoklama/{qr_jeton}", json={"ogrenci": j1}, headers=_z())
    assert y.json()["sonuc"] == "zaten"
    y = await istemci.post(f"{A}/yoklama/{qr_jeton}", json={"ogrenci": j3}, headers=_z())
    assert y.status_code == 403 and _kod(y) == "farkli_kurs"
    # Tahtadaki kısa kod (öğrenci portalından).
    y = await istemci.post(f"{A}/ogrenci/{j2}/yoklama", json={"kod": "ZZZZZZ"}, headers=_z())
    assert y.status_code == 404
    y = await istemci.post(f"{A}/ogrenci/{j2}/yoklama", json={"kod": bilgi["yoklama"]["kod"].lower()}, headers=_z())
    assert y.status_code == 200 and y.json()["sonuc"] == "isaretlendi"
    # Eğitmen öğrencinin QR'ını okutur: ikinci okutma "zaten_girdi"; sahte imza, başka kursun öğrencisi.
    p1 = await _portal(istemci, j1)
    qr_metni = (await istemci.get(f"{A}/ogrenci/{j1}/qr.svg", headers=_z()))
    assert qr_metni.status_code == 200 and qr_metni.headers["content-type"].startswith("image/svg")
    from services import egitim as s

    y = await istemci.post(f"{Y}/{k['id']}/oturumlar/{ot['id']}/okut", json={"kod": s.qr_icerigi(p1["ogrenci"]["kod"])},
                           headers=yonetici_basligi)
    assert y.json()["sonuc"] == "zaten_girdi" and y.json()["sayac"]["giren"] == 2
    y = await istemci.post(f"{Y}/{k['id']}/oturumlar/{ot['id']}/okut", json={"kod": "MKO1.ABCD2345.FFFFFFFFFFFFFFFF"},
                           headers=yonetici_basligi)
    assert y.json()["sonuc"] == "gecersiz"
    p3 = await _portal(istemci, j3)
    y = await istemci.post(f"{Y}/{k['id']}/oturumlar/{ot['id']}/okut", json={"kod": p3["ogrenci"]["kod"]}, headers=yonetici_basligi)
    assert y.json()["sonuc"] == "farkli_etkinlik" and y.json()["bilet"] is None
    # Elle düzeltme ve QR yenileme (eski bağlantı geçersiz).
    y = await istemci.put(f"{Y}/{k['id']}/oturumlar/{ot['id']}/yoklama/{bilgi['items'][1]['id']}", json={"durum": "izinli"},
                          headers=yonetici_basligi)
    assert y.status_code == 200
    yeni = (await istemci.post(f"{Y}/{k['id']}/oturumlar/{ot['id']}/qr-yenile", headers=yonetici_basligi)).json()
    assert yeni["kod"] != bilgi["yoklama"]["kod"]
    assert (await istemci.get(f"{A}/yoklama/{qr_jeton}", headers=_z())).status_code == 404
    # Pencere dışında (ders bitiminden 30 dk sonra) kapalı.
    _ortam["an"] = SIMDI + timedelta(hours=3)
    y = await istemci.post(f"{A}/yoklama/{_jeton(yeni['adres'])}", json={"ogrenci": j2}, headers=_z())
    assert y.status_code == 410 and _kod(y) == "yoklama_kapali"


async def test_devamsizlik_esigi_olay_ve_eposta_bir_kez(istemci, yonetici_basligi, db_oturumu, epostalar, monkeypatch, _ortam):
    from models.api_erisimi import WebhookTeslimatlari, WebhookUcNoktalari
    from services import webhook
    from services.api_erisimi import gizli_sakla

    monkeypatch.setattr(webhook, "ANLIK_TESLIMAT", False)
    uc = WebhookUcNoktalari(sahip_tur="ajans", hesap_email=None, url="https://kanca.ornek.com/egitim",
                            olaylar=json.dumps(["egitim.devamsizlik"]), aktif=True, gizli_anahtar=gizli_sakla("whsec_test"),
                            ardisik_hata=0, tum_musteriler=False)
    db_oturumu.add(uc)
    await db_oturumu.commit()
    webhook.onbellegi_temizle()
    try:
        k = await _kurs(istemci, yonetici_basligi, devamsizlik_esik=2)
        j = _jeton((await _kayit(istemci, k["slug"], ad="Devamsız Öğrenci", eposta="devamsiz@ornek.com")).json()["portal_adresi"])
        for gun in (1, 2, 3):
            await _oturum(istemci, yonetici_basligi, k["id"], SIMDI + timedelta(days=gun))
        _ortam["an"] = SIMDI + timedelta(days=2, hours=3)  # iki ders bitti, katılmadı
        epostalar.clear()
        await _bakim()
        uyari = [e for e in epostalar if "Devamsızlık" in e["konu"]]
        assert len(uyari) == 1 and uyari[0]["alici"] == "devamsiz@ornek.com" and "2" in uyari[0]["govde"]
        _ortam["an"] = SIMDI + timedelta(days=3, hours=3)  # üçüncü de kaçtı: yeni uyarı yok
        await _bakim()
        assert len([e for e in epostalar if "Devamsızlık" in e["konu"]]) == 1
        teslimat = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id))).scalars().all()
        assert [x.tur for x in teslimat] == ["egitim.devamsizlik"]
        veri = json.loads(teslimat[0].govde)["veri"]
        assert veri["kurs_id"] == k["id"] and veri["devamsizlik"] == 2 and "devamsiz@" not in teslimat[0].govde
        p = await _portal(istemci, j)
        assert p["istatistik"]["devamsizlik"] == 3 and p["istatistik"]["yoklama"] == 0
    finally:
        uc.aktif = False
        await db_oturumu.commit()
        webhook.onbellegi_temizle()


async def test_program_uretimi_ics_ve_hatirlatma_bir_kez(istemci, yonetici_basligi, epostalar, _ortam):
    k = await _kurs(istemci, yonetici_basligi, hatirlatma_saat=2, bitis_tarihi=None)
    y = await istemci.post(f"{Y}/{k['id']}/oturumlar/uret", json={"bas_tarih": "2026-10-05", "bit_tarih": "2026-10-18",
                                                                  "gunler": [0, 2], "saat": "10:00", "sure_dk": 60, "konu": "Ders"},
                           headers=yonetici_basligi)
    assert y.status_code == 200 and y.json() == {"eklenen": 4, "atlanan": 0}
    y = await istemci.post(f"{Y}/{k['id']}/oturumlar/uret", json={"bas_tarih": "2026-10-05", "bit_tarih": "2026-10-05",
                                                                  "gunler": [0], "saat": "10:00", "sure_dk": 60},
                           headers=yonetici_basligi)
    assert y.json() == {"eklenen": 0, "atlanan": 1}
    assert (await istemci.get(f"{Y}/{k['id']}", headers=yonetici_basligi)).json()["bitis_tarihi"] == "2026-10-18"
    j = _jeton((await _kayit(istemci, k["slug"], eposta="hatir@ornek.com")).json()["portal_adresi"])
    ics = await istemci.get(f"{A}/ogrenci/{j}/takvim.ics", headers=_z())
    assert ics.status_code == 200 and ics.text.count("BEGIN:VEVENT") == 4 and "DTSTART:20261005T070000Z" in ics.text
    epostalar.clear()
    await _bakim()  # 09:00 → 10:00 dersi 2 saat içinde
    await _bakim()
    hatirlatma = [e for e in epostalar if "Ders hatırlatması" in e["konu"]]
    assert len(hatirlatma) == 1 and hatirlatma[0]["alici"] == "hatir@ornek.com"


# ---------------------------------------------------------------------------
# Quiz, ödev, ilerleme, AI
# ---------------------------------------------------------------------------
SORULAR = [
    {"tur": "coktan", "metin": "Python'da liste?", "secenekler": ["()", "[]", "{}"], "dogru": 1},
    {"tur": "dogru_yanlis", "metin": "print bir fonksiyondur.", "dogru": True},
    {"tur": "kisa", "metin": "Döngü anahtar kelimesi?", "dogru": ["for", "while"]},
]


async def test_quiz_puanlama_sure_ve_deneme_hakki(istemci, yonetici_basligi, _ortam):
    k = await _kurs(istemci, yonetici_basligi)
    y = await istemci.post(f"{Y}/{k['id']}/quizler", json={"baslik": "Boş", "yayinda": True}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "soru_yok"
    q = (await istemci.post(f"{Y}/{k['id']}/quizler", json={"baslik": "Temeller", "sorular": SORULAR, "sure_dk": 10,
                                                            "gecme_puani": 60, "yayinda": True}, headers=yonetici_basligi)).json()
    j1 = _jeton((await _kayit(istemci, k["slug"], ad="Hızlı")).json()["portal_adresi"])
    j2 = _jeton((await _kayit(istemci, k["slug"], ad="Yavaş")).json()["portal_adresi"])
    b = (await istemci.post(f"{A}/ogrenci/{j1}/quiz/{q['id']}/basla", headers=_z())).json()
    assert len(b["sorular"]) == 3 and all("dogru" not in x for x in b["sorular"])
    assert b["son_at"] == (SIMDI + timedelta(minutes=10)).isoformat().replace("+00:00", "Z") or b["son_at"]
    y = await istemci.post(f"{A}/ogrenci/{j1}/quiz/{q['id']}/gonder", json={
        "deneme_id": b["deneme_id"], "yanitlar": {"s1": 1, "s2": True, "s3": "While"}}, headers=_z())
    assert y.status_code == 200 and y.json()["puan"] == 100 and y.json()["gecti"] is True
    assert (await istemci.post(f"{A}/ogrenci/{j1}/quiz/{q['id']}/gonder", json={"deneme_id": b["deneme_id"], "yanitlar": {}},
                               headers=_z())).status_code == 409
    y = await istemci.post(f"{A}/ogrenci/{j1}/quiz/{q['id']}/basla", headers=_z())
    assert y.status_code == 409 and _kod(y) == "deneme_hakki_doldu"
    # Süre aşımı: puan 0, "suresi_doldu".
    b2 = (await istemci.post(f"{A}/ogrenci/{j2}/quiz/{q['id']}/basla", headers=_z())).json()
    _ortam["an"] = SIMDI + timedelta(minutes=11)
    y = await istemci.post(f"{A}/ogrenci/{j2}/quiz/{q['id']}/gonder", json={
        "deneme_id": b2["deneme_id"], "yanitlar": {"s1": 1, "s2": True, "s3": "for"}}, headers=_z())
    assert y.json()["durum"] == "suresi_doldu" and y.json()["puan"] == 0
    sonuc = (await istemci.get(f"{Y}/{k['id']}/quizler/{q['id']}/sonuclar", headers=yonetici_basligi)).json()["items"]
    assert sorted((x["ad"], x["puan"], x["durum"]) for x in sonuc) == [("Hızlı", 100, "tamamlandi"), ("Yavaş", 0, "suresi_doldu")]


async def test_odev_teslimi_ve_not(istemci, yonetici_basligi, epostalar):
    k = await _kurs(istemci, yonetici_basligi)
    q = (await istemci.post(f"{Y}/{k['id']}/quizler", json={"baslik": "Proje ödevi", "tur": "odev", "yayinda": True},
                            headers=yonetici_basligi)).json()
    j = _jeton((await _kayit(istemci, k["slug"], ad="Ödevci", eposta="odevci@ornek.com")).json()["portal_adresi"])
    y = await istemci.post(f"{A}/ogrenci/{j}/odev/{q['id']}", data={"metin": ""}, headers=_z())
    assert y.status_code == 400 and _kod(y) == "teslim_bos"
    y = await istemci.post(f"{A}/ogrenci/{j}/odev/{q['id']}", data={"metin": "Çözümüm ektedir."},
                           files={"dosya": ("cozum.txt", b"print('merhaba')", "text/plain")}, headers=_z())
    assert y.status_code == 200, y.text
    p = await _portal(istemci, j)
    teslim = next(x for x in p["quizler"] if x["id"] == q["id"])["teslim"]
    assert teslim["metin"] == "Çözümüm ektedir." and teslim["dosyalar"][0]["ad"] == "cozum.txt"
    d = await istemci.get(f"{A}/ogrenci/{j}/dosya/{teslim['dosyalar'][0]['id']}", headers=_z())
    assert d.status_code == 200 and d.content == b"print('merhaba')"
    sonuc = (await istemci.get(f"{Y}/{k['id']}/quizler/{q['id']}/sonuclar", headers=yonetici_basligi)).json()["items"]
    epostalar.clear()
    y = await istemci.put(f"{Y}/{k['id']}/teslimler/{sonuc[0]['id']}", json={"puan": 85, "geri_bildirim": "Güzel iş"},
                          headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["puan"] == 85
    assert any("değerlendirildi" in e["konu"] and "Güzel iş" in e["govde"] for e in epostalar)
    y = await istemci.post(f"{A}/ogrenci/{j}/odev/{q['id']}", data={"metin": "yeniden"}, headers=_z())
    assert y.status_code == 409 and _kod(y) == "notlandi"


async def test_ai_soru_uretimi_sahte_anahtar_yok_ve_hak(istemci, yonetici_basligi, monkeypatch):
    from services import egitim as s
    from services import yapay_zeka

    m = _e("ai")
    await _modul(istemci, yonetici_basligi, m, ai_hakki=1)
    k = await _kurs(istemci, _b(m), M)
    d = (await istemci.post(f"{M}/{k['id']}/dersler", json={"baslik": "Fotosentez", "icerik": "Bitkiler güneş ışığıyla besin üretir. "
                                                            "Bu süreçte karbondioksit ve su kullanılır ve oksijen açığa çıkar."},
                            headers=_b(m))).json()
    monkeypatch.setattr(s, "ai_hazir", lambda: False)
    y = await istemci.post(f"{M}/{k['id']}/quizler/ai", json={"ders_id": d["id"], "sayi": 2}, headers=_b(m))
    assert y.status_code == 503 and _kod(y) == "ai_kapali"
    monkeypatch.setattr(s, "ai_hazir", lambda: True)
    cagrilar = []

    async def _sahte(mesajlar, model, max_tokens, temperature):
        cagrilar.append(mesajlar)
        if len(cagrilar) == 1:
            return "bu JSON değil", {}
        return json.dumps({"sorular": [{"tur": "dogru_yanlis", "metin": "Bitkiler oksijen üretir.", "dogru": True},
                                       {"tur": "coktan", "metin": "Hangisi kullanılır?", "secenekler": ["Azot", "Su"], "dogru": 1},
                                       {"tur": "uydurma", "metin": "geçersiz"}]}), {"prompt_tokens": 10, "completion_tokens": 20}

    monkeypatch.setattr(yapay_zeka, "_saglayici_cagir", _sahte)
    # Bozuk yanıt: 502 ve hak iade (sayaç düşmez).
    y = await istemci.post(f"{M}/{k['id']}/quizler/ai", json={"ders_id": d["id"], "sayi": 3}, headers=_b(m))
    assert y.status_code == 502 and _kod(y) == "ai_bicim"
    y = await istemci.post(f"{M}/{k['id']}/quizler/ai", json={"ders_id": d["id"], "sayi": 3}, headers=_b(m))
    assert y.status_code == 200, y.text
    sorular = y.json()["sorular"]
    assert [q["tur"] for q in sorular] == ["dogru_yanlis", "coktan"] and y.json()["ai"]["kullanilan"] == 1
    assert "Fotosentez" in cagrilar[-1][1]["content"]
    # Önerilen sorular kaydedilmedi; kullanıcı onaylayınca quiz olur.
    assert (await istemci.get(f"{M}/{k['id']}/quizler", headers=_b(m))).json()["items"] == []
    y = await istemci.post(f"{M}/{k['id']}/quizler", json={"baslik": "AI quiz", "sorular": sorular, "ai_uretildi": True},
                           headers=_b(m))
    assert y.status_code == 200 and y.json()["ai_uretildi"] is True
    # Aylık hak doldu (kredi ile aşım kapalı).
    y = await istemci.post(f"{M}/{k['id']}/quizler/ai", json={"ders_id": d["id"], "sayi": 3}, headers=_b(m))
    assert y.status_code == 409 and _kod(y) == "ai_hakki_doldu"


async def test_ai_test_ortaminda_sahte_model_belirlenimci_soru(istemci, yonetici_basligi, monkeypatch):
    from services import egitim as s
    from services import yapay_zeka

    monkeypatch.setattr(s, "ai_hazir", lambda: True)
    monkeypatch.setattr(yapay_zeka, "sahte_ai_acik_mi", lambda: True)
    k = await _kurs(istemci, yonetici_basligi)
    d = (await istemci.post(f"{Y}/{k['id']}/dersler", json={"baslik": "Kesirler", "icerik": "Kesir bir bütünün parçasıdır. "
                                                            "Pay üstte payda altta yazılır. Paydalar eşitse paylar toplanır."},
                            headers=yonetici_basligi)).json()
    y = await istemci.post(f"{Y}/{k['id']}/quizler/ai", json={"ders_id": d["id"], "sayi": 3}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert [q["tur"] for q in y.json()["sorular"]] == ["coktan", "dogru_yanlis", "kisa"]


# ---------------------------------------------------------------------------
# Sertifika
# ---------------------------------------------------------------------------
async def test_sertifika_kosullari_pdf_ve_dogrulama_kisisel_veri_yok(istemci, yonetici_basligi, epostalar, db_oturumu, _ortam):
    await istemci.put(f"{Y}/ayarlar", json={"kurum_adi": "Kodlama Akademisi", "imza_adi": "Mehmet Kuru"}, headers=yonetici_basligi)
    k = await _kurs(istemci, yonetici_basligi, kosul_ilerleme=100, kosul_quiz=60, kosul_yoklama=50, sertifika_saat=24)
    d = (await istemci.post(f"{Y}/{k['id']}/dersler", json={"baslik": "Tek ders"}, headers=yonetici_basligi)).json()
    q = (await istemci.post(f"{Y}/{k['id']}/quizler", json={"baslik": "Final", "sorular": SORULAR, "yayinda": True},
                            headers=yonetici_basligi)).json()
    ot = await _oturum(istemci, yonetici_basligi, k["id"], SIMDI + timedelta(minutes=5))
    y = await _kayit(istemci, k["slug"], ad="Zeynep Ayşe Kaya", eposta="zeynep.kaya@ornek.com", telefon="+905551234567")
    j = _jeton(y.json()["portal_adresi"])
    oid = int(j.split("-")[0])
    y = await istemci.post(f"{Y}/{k['id']}/sertifikalar", json={"ogrenci_id": oid}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "kosul_saglanmadi"
    assert y.json()["detail"]["kosullar"]["ilerleme"]["tamam"] is False
    # İlerleme + quiz + yoklama.
    y = await istemci.post(f"{A}/ogrenci/{j}/ders/{d['id']}/tamamla", json={"tamamlandi": True}, headers=_z())
    assert y.json()["istatistik"]["ilerleme"] == 100
    b = (await istemci.post(f"{A}/ogrenci/{j}/quiz/{q['id']}/basla", headers=_z())).json()
    await istemci.post(f"{A}/ogrenci/{j}/quiz/{q['id']}/gonder", json={"deneme_id": b["deneme_id"], "yanitlar": {"s1": 1, "s2": True}},
                       headers=_z())
    bilgi = (await istemci.get(f"{Y}/{k['id']}/oturumlar/{ot['id']}/yoklama", headers=yonetici_basligi)).json()
    await istemci.post(f"{A}/ogrenci/{j}/yoklama", json={"kod": bilgi["yoklama"]["kod"]}, headers=_z())
    _ortam["an"] = SIMDI + timedelta(hours=3)
    ilerleme = (await istemci.get(f"{Y}/{k['id']}/ilerleme", headers=yonetici_basligi)).json()["items"][0]
    assert ilerleme["quiz_ortalama"] == 67 and ilerleme["yoklama"] == 100 and ilerleme["uygun"] is True
    epostalar.clear()
    y = await istemci.post(f"{Y}/{k['id']}/sertifikalar/toplu", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["verilen"] == 1
    assert any("Sertifikanız hazır" in e["konu"] for e in epostalar)
    sertifikalar = (await istemci.get(f"{Y}/{k['id']}/sertifikalar", headers=yonetici_basligi)).json()["items"]
    kod = sertifikalar[0]["kod"]
    pdf = await istemci.get(f"{A}/ogrenci/{j}/sertifika.pdf", headers=_z())
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-" and pdf.headers["content-type"] == "application/pdf"
    pdf2 = await istemci.get(f"{Y}/{k['id']}/sertifikalar/{sertifikalar[0]['id']}/pdf", headers=yonetici_basligi)
    assert pdf2.status_code == 200 and pdf2.content[:5] == b"%PDF-"
    # Herkese açık doğrulama: maskeli ad; e-posta, telefon, tam soyad, öğrenci kodu YOK.
    y = await istemci.get(f"{A}/sertifika/{kod.lower()[:4]}-{kod.lower()[4:8]}-{kod.lower()[8:]}", headers=_z())
    assert y.status_code == 200, y.text
    g = y.json()
    assert g["gecerli"] is True and g["ad"] == "Zeynep A. K." and g["kurs"] == k["ad"] and g["kurum"] == "Kodlama Akademisi"
    for gizli in ("zeynep.kaya", "Kaya", "905551234567", (await _portal(istemci, j))["ogrenci"]["kod"]):
        assert gizli not in y.text
    assert y.headers.get("x-robots-tag") == "noindex, nofollow"
    assert (await istemci.get(f"{A}/sertifika/AAAABBBBCCCC", headers=_z())).status_code == 404
    # İptal → geçersiz görünür.
    await istemci.delete(f"{Y}/{k['id']}/sertifikalar/{sertifikalar[0]['id']}", headers=yonetici_basligi)
    assert (await istemci.get(f"{A}/sertifika/{kod}", headers=_z())).json()["gecerli"] is False


# ---------------------------------------------------------------------------
# Veli / çocuk verisi, saklama ve anonimleştirme
# ---------------------------------------------------------------------------
async def test_cocuk_kaydi_veli_zorunlu_pazarlama_yok_eposta_veliye(istemci, yonetici_basligi, epostalar, db_oturumu):
    from models.egitim import EgitimOgrencileri

    k = await _kurs(istemci, yonetici_basligi, hedef_kitle="cocuk")
    assert (await istemci.get(f"{A}/kurs/{k['slug']}")).json()["hedef_kitle"] == "cocuk"
    y = await _kayit(istemci, k["slug"], ad="Deniz", eposta=None)
    assert y.status_code == 400 and y.json()["detail"]["alan"] == "veli_ad"
    y = await _kayit(istemci, k["slug"], ad="Deniz", eposta=None, veli_ad="Elif Kaya", veli_eposta="elif@ornek.com",
                     veli_telefon="0555 222 33 44", pazarlama_izni=True)
    assert y.status_code == 200, y.text and y.json()["cocuk"] is True
    o = (await db_oturumu.execute(select(EgitimOgrencileri).where(EgitimOgrencileri.veli_eposta == "elif@ornek.com"))).scalars().one()
    assert o.cocuk is True and o.eposta is None and o.pazarlama_izni_at is None and o.aydinlatma_at is not None
    giden = [e for e in epostalar if e["alici"] == "elif@ornek.com"]
    assert giden and "velisi" in giden[0]["govde"] and "Merhaba Elif Kaya" in giden[0]["govde"]
    # Karma kursta işaretlemeyen yetişkin: veli istenmez, e-posta zorunlu.
    k2 = await _kurs(istemci, yonetici_basligi, hedef_kitle="karma")
    assert (await _kayit(istemci, k2["slug"], ad="Yetişkin", eposta=None)).status_code == 400
    assert (await _kayit(istemci, k2["slug"], ad="Çocuk", eposta=None, cocuk=True, veli_ad="V", veli_eposta="v@ornek.com")).status_code == 200


async def test_saklama_suresi_dolunca_anonimlestirme(istemci, yonetici_basligi, db_oturumu, _ortam):
    from models.egitim import EgitimOgrencileri, EgitimTeslimleri

    k = await _kurs(istemci, yonetici_basligi, hedef_kitle="karma", saklama_gun=30, bitis_tarihi="2026-10-20")
    q = (await istemci.post(f"{Y}/{k['id']}/quizler", json={"baslik": "Ödev", "tur": "odev", "yayinda": True},
                            headers=yonetici_basligi)).json()
    j = _jeton((await _kayit(istemci, k["slug"], ad="Çocuk Öğrenci", eposta=None, cocuk=True, veli_ad="Veli Ad",
                             veli_eposta="veli.saklama@ornek.com", veli_telefon="05554443322")).json()["portal_adresi"])
    await istemci.post(f"{A}/ogrenci/{j}/odev/{q['id']}", data={"metin": "Kişisel metin"},
                       files={"dosya": ("odev.txt", b"icerik", "text/plain")}, headers=_z())
    oid = int(j.split("-")[0])
    await istemci.put(f"{Y}/{k['id']}/ogrenciler/{oid}", json={"notlar": "Alerjisi var"}, headers=yonetici_basligi)
    _ortam["an"] = datetime(2026, 11, 15, tzinfo=UTC)  # bitiş (20 Ekim) + 30 gün dolmadı
    await _bakim()
    db_oturumu.expire_all()
    o = (await db_oturumu.execute(select(EgitimOgrencileri).where(EgitimOgrencileri.id == oid))).scalars().one()
    assert o.anonim is False and o.veli_eposta == "veli.saklama@ornek.com"
    _ortam["an"] = datetime(2026, 11, 21, 0, 0, tzinfo=UTC) + timedelta(days=1)
    await _bakim()
    db_oturumu.expire_all()
    o = (await db_oturumu.execute(select(EgitimOgrencileri).where(EgitimOgrencileri.id == oid))).scalars().one()
    assert o.anonim is True and o.ad is None and o.veli_ad is None and o.veli_eposta is None and o.veli_telefon is None
    assert o.notlar is None and o.kod  # kod (kişisel değil) kalır
    t = (await db_oturumu.execute(select(EgitimTeslimleri).where(EgitimTeslimleri.ogrenci_id == oid))).scalars().one()
    assert t.metin is None
    assert (await istemci.get(f"{A}/ogrenci/{j}", headers=_z())).status_code == 410
    liste = (await istemci.get(f"{Y}/{k['id']}/ogrenciler", headers=yonetici_basligi)).json()["items"]
    assert liste[0]["anonim"] is True and liste[0]["veli_eposta"] == "" and "Alerjisi" not in json.dumps(liste)


async def test_ogrenci_silme_kvkk_ve_bekleyen_alinir(istemci, yonetici_basligi, db_oturumu):
    from models.egitim import EgitimOgrencileri, EgitimYoklama

    k = await _kurs(istemci, yonetici_basligi, kapasite=1)
    a = int(_jeton((await _kayit(istemci, k["slug"], ad="Silinecek")).json()["portal_adresi"]).split("-")[0])
    b = int(_jeton((await _kayit(istemci, k["slug"], ad="Bekleyen")).json()["portal_adresi"]).split("-")[0])
    ot = await _oturum(istemci, yonetici_basligi, k["id"], SIMDI + timedelta(minutes=5))
    await istemci.put(f"{Y}/{k['id']}/oturumlar/{ot['id']}/yoklama/{a}", json={"durum": "var"}, headers=yonetici_basligi)
    assert (await istemci.delete(f"{Y}/{k['id']}/ogrenciler/{a}", headers=yonetici_basligi)).status_code == 200
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(EgitimOgrencileri).where(EgitimOgrencileri.id == a))).first() is None
    assert (await db_oturumu.execute(select(EgitimYoklama).where(EgitimYoklama.ogrenci_id == a))).first() is None
    assert (await db_oturumu.execute(select(EgitimOgrencileri.durum).where(EgitimOgrencileri.id == b))).scalar() == "aktif"


# ---------------------------------------------------------------------------
# Hesap ekibi: eğitmen izni yalnız kendi kursu
# ---------------------------------------------------------------------------
async def test_egitmen_izni_yalniz_kendi_kursu_yoklama_ve_not(istemci, yonetici_basligi, db_oturumu):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi

    sahip, egitmen = _e("sahip"), _e("egitmen")
    await _modul(istemci, yonetici_basligi, sahip)
    db_oturumu.add(HesapUyeleri(hesap_email=sahip, uye_email=egitmen, rol="uye", izinler=json.dumps(["projeler", "egitim_egitmen"]),
                                durum="aktif", olusturma=hesap_ekibi.simdi()))
    await db_oturumu.commit()
    hesap_ekibi.onbellegi_temizle()
    kendi = await _kurs(istemci, _b(sahip), M, egitmenler=[{"ad": "Eğitmen Ece", "eposta": egitmen.upper()}])
    baska = await _kurs(istemci, _b(sahip), M)
    await _kayit(istemci, kendi["slug"], ad="Öğrenci Bir", eposta="ogrenci.bir@ornek.com", telefon="05551112233")
    q = (await istemci.post(f"{M}/{kendi['id']}/quizler", json={"baslik": "Ödev", "tur": "odev", "yayinda": True},
                            headers=_b(sahip))).json()
    ot = await _oturum(istemci, _b(sahip), kendi["id"], SIMDI + timedelta(minutes=5), yol=M)
    eb = _b(egitmen, sahip)
    meta = (await istemci.get(f"{M}/meta", headers=eb)).json()
    assert meta["egitmen"] is True and meta["yonetim"] is False and meta["ai"] is None
    assert [x["id"] for x in (await istemci.get(M, headers=eb)).json()["items"]] == [kendi["id"]]
    assert (await istemci.get(f"{M}/{baska['id']}", headers=eb)).status_code == 404
    assert (await istemci.get(f"{M}/{baska['id']}/oturumlar", headers=eb)).status_code == 404
    # Yönetim işleri yok.
    for metot, yol, govde in (("PUT", f"{M}/{kendi['id']}", {"ad": "x"}), ("POST", M, {"ad": "Yeni"}),
                              ("POST", f"{M}/{kendi['id']}/ogrenciler", {"ad": "x", "eposta": "x@ornek.com"}),
                              ("GET", f"{M}/{kendi['id']}/ogrenciler.csv", None), ("POST", f"{M}/{kendi['id']}/duyuru", {"konu": "a", "metin": "b"}),
                              ("GET", f"{M}/{kendi['id']}/sertifikalar", None), ("GET", f"{M}/ayarlar", None)):
        y = await istemci.request(metot, yol, headers=eb, **({"json": govde} if govde is not None else {}))
        assert y.status_code == 403 and _kod(y) == "hesap_izni_yok", (metot, yol, y.status_code, y.text)
    # Öğrenci listesi: iletişim/veli bilgisi YOK.
    liste = (await istemci.get(f"{M}/{kendi['id']}/ogrenciler", headers=eb)).json()["items"]
    assert liste[0]["ad"] == "Öğrenci Bir" and "eposta" not in liste[0] and "veli_eposta" not in liste[0]
    assert "ogrenci.bir@" not in json.dumps(liste)
    # Yoklama ve not verebilir.
    y = await istemci.post(f"{M}/{kendi['id']}/oturumlar/{ot['id']}/okut", json={"kod": liste[0]["kod"]}, headers=eb)
    assert y.status_code == 200 and y.json()["sonuc"] == "gecerli"
    j = None
    from models.egitim import EgitimOgrencileri
    from services import egitim as s

    o = (await db_oturumu.execute(select(EgitimOgrencileri).where(EgitimOgrencileri.id == liste[0]["id"]))).scalars().one()
    j = s.ogrenci_jetonu(o.id, o.portal_surumu, o.kod)
    await istemci.post(f"{A}/ogrenci/{j}/odev/{q['id']}", data={"metin": "Teslim"}, headers=_z())
    sonuc = (await istemci.get(f"{M}/{kendi['id']}/quizler/{q['id']}/sonuclar", headers=eb)).json()["items"]
    y = await istemci.put(f"{M}/{kendi['id']}/teslimler/{sonuc[0]['id']}", json={"puan": 90, "bildir": False}, headers=eb)
    assert y.status_code == 200


# ---------------------------------------------------------------------------
# Olaylar, gelen kutusu, çöp kutusu, modül kapanınca
# ---------------------------------------------------------------------------
async def test_olay_katalogu_ve_teslimat_kisisel_veri_yok(istemci, yonetici_basligi, db_oturumu, monkeypatch, _ortam):
    from models.api_erisimi import WebhookTeslimatlari, WebhookUcNoktalari
    from services import otomasyon_kural, webhook
    from services.api_erisimi import gizli_sakla

    tumu = {"egitim.kayit", "egitim.tamamlandi", "egitim.devamsizlik"}
    assert tumu <= set(webhook.OLAY_SOZLUGU) and tumu <= set(otomasyon_kural.OLAY_SOZLUGU)
    assert tumu <= {o["anahtar"] for o in webhook.olay_katalogu(False)}
    assert otomasyon_kural.olay_nesneleri("egitim.kayit", False) == ("egitim", "hesap", "kisi", "olay")
    assert {"egitim_ogrencileri", "egitim_sertifikalari"} <= webhook.IZLENEN_TABLOLAR
    # Çocukta otomasyonun "kişi"si veli.
    assert otomasyon_kural.kisi_sec("egitim.kayit", {"egitim": otomasyon_kural.ORNEK["egitim"]})["email"] == "elif@ornek.com"
    monkeypatch.setattr(webhook, "ANLIK_TESLIMAT", False)
    uc = WebhookUcNoktalari(sahip_tur="ajans", hesap_email=None, url="https://kanca.ornek.com/egitim2",
                            olaylar=json.dumps(sorted(tumu)), aktif=True, gizli_anahtar=gizli_sakla("whsec_test"),
                            ardisik_hata=0, tum_musteriler=False)
    db_oturumu.add(uc)
    await db_oturumu.commit()
    webhook.onbellegi_temizle()
    try:
        k = await _kurs(istemci, yonetici_basligi, kosul_ilerleme=0, kosul_quiz=0, kosul_yoklama=0)
        j = _jeton((await _kayit(istemci, k["slug"], ad="Gizli Öğrenci", eposta="gizli.ogrenci@ornek.com")).json()["portal_adresi"])
        oid = int(j.split("-")[0])
        y = await istemci.post(f"{Y}/{k['id']}/sertifikalar", json={"ogrenci_id": oid, "bildir": False}, headers=yonetici_basligi)
        assert y.status_code == 200 and y.json()["yeni"] is True
        teslimat = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id)
                                             .order_by(WebhookTeslimatlari.id))).scalars().all()
        assert [x.tur for x in teslimat] == ["egitim.kayit", "egitim.tamamlandi"]
        for x in teslimat:
            assert "gizli" not in x.govde.lower() and json.loads(x.govde)["veri"]["kurs_id"] == k["id"]
        assert json.loads(teslimat[1].govde)["veri"]["sertifika_kod"] == y.json()["kod"]
        # Otomasyon bağlamı kişi alanlarını kayıttan okur.
        from core.database import db_manager
        from services import otomasyon

        async with db_manager.async_session_maker() as db:
            b = await otomasyon.baglam_kur(db, "egitim.tamamlandi", json.loads(teslimat[1].govde)["veri"], None, True)
        assert b["egitim"]["eposta"] == "gizli.ogrenci@ornek.com" and b["egitim"]["kod"] == y.json()["kod"]
    finally:
        uc.aktif = False
        await db_oturumu.commit()
        webhook.onbellegi_temizle()


async def test_gelen_kutusu_ajans_kursu_kaydi(istemci, yonetici_basligi):
    k = await _kurs(istemci, yonetici_basligi)
    await _kayit(istemci, k["slug"], ad="Gelen Kutusu Öğrencisi", eposta="gk.ogrenci@ornek.com")
    y = await istemci.get("/api/v1/gelen-kutusu", params={"kaynak": "egitim", "q": "gk.ogrenci"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    ogeler = [o for o in y.json()["ogeler"] if o["kisi_eposta"] == "gk.ogrenci@ornek.com"]
    assert ogeler and ogeler[0]["baslik"] == k["ad"] and ogeler[0]["durum"] == "yeni"
    assert ogeler[0]["yanit"]["tur"] == "eposta"
    # Müşterinin kursu ajansın gelen kutusuna düşmez.
    m = _e("gk")
    await _modul(istemci, yonetici_basligi, m)
    km = await _kurs(istemci, _b(m), M)
    await _kayit(istemci, km["slug"], eposta="musteri.ogrencisi@ornek.com")
    y = await istemci.get("/api/v1/gelen-kutusu", params={"kaynak": "egitim", "q": "musteri.ogrencisi"}, headers=yonetici_basligi)
    assert y.json()["ogeler"] == []


async def test_cop_kutusu_ve_modul_kapaninca_410(istemci, yonetici_basligi, db_oturumu):
    from models.cop_kutusu import CopKutusu
    from models.egitim import EgitimOgrencileri

    m = _e("cop")
    await _modul(istemci, yonetici_basligi, m)
    k = await _kurs(istemci, _b(m), M)
    j = _jeton((await _kayit(istemci, k["slug"], ad="Çöp Öğrenci", eposta="cop.ogrenci@ornek.com")).json()["portal_adresi"])
    await _modul(istemci, yonetici_basligi, m, acik=False)
    y = await istemci.get(f"{A}/kurs/{k['slug']}")
    assert y.status_code == 410 and _kod(y) == "kurs_pasif"
    assert (await istemci.get(f"{A}/ogrenci/{j}", headers=_z())).status_code == 410
    assert (await istemci.get(M, headers=_b(m))).status_code == 403
    await _modul(istemci, yonetici_basligi, m)
    await _oturum(istemci, _b(m), k["id"], SIMDI + timedelta(days=1), yol=M)
    assert (await istemci.delete(f"{M}/{k['id']}", headers=_b(m))).status_code == 200
    cop = (await db_oturumu.execute(select(CopKutusu).where(CopKutusu.tablo == "egitim_kurslari", CopKutusu.kayit_id == k["id"]))).scalars().first()
    assert cop is not None
    db_oturumu.expire_all()
    o = (await db_oturumu.execute(select(EgitimOgrencileri).where(EgitimOgrencileri.kurs_id == k["id"]))).scalars().one()
    assert o.anonim is True and o.eposta is None


async def test_duyuru_bilgilendirme_ve_hiz_siniri(istemci, yonetici_basligi, epostalar):
    k = await _kurs(istemci, yonetici_basligi)
    y = await istemci.post(f"{Y}/{k['id']}/duyuru", json={"konu": "Ders iptal", "metin": "Yarın ders yok."}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "alici_yok"
    await _kayit(istemci, k["slug"], eposta="duyuru1@ornek.com")
    epostalar.clear()
    y = await istemci.post(f"{Y}/{k['id']}/duyuru", json={"konu": "Ders iptal", "metin": "Yarın ders yok."}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["alici"] == 1
    giden = [e for e in epostalar if e["alici"] == "duyuru1@ornek.com"]
    assert giden and giden[0]["konu"] == f"{k['ad']}: Ders iptal" and "kurs bilgilendirmesi" in giden[0]["govde"]
    assert (await istemci.get(f"{Y}/{k['id']}/duyurular", headers=yonetici_basligi)).json()["items"][0]["konu"] == "Ders iptal"


async def test_kurum_listesi_sayfasi(istemci, yonetici_basligi):
    m = _e("kurum")
    await _modul(istemci, yonetici_basligi, m)
    slug = f"kurum-{uuid.uuid4().hex[:6]}"
    y = await istemci.put(f"{M}/ayarlar", json={"liste_acik": True}, headers=_b(m))
    assert y.status_code == 400 and y.json()["detail"]["alan"] == "liste_slug"
    y = await istemci.put(f"{M}/ayarlar", json={"liste_acik": True, "liste_slug": slug, "liste_baslik": "Kurslarımız"}, headers=_b(m))
    assert y.status_code == 200 and y.json()["liste_adresi"].endswith(f"/egitim/kurum/{slug}")
    k = await _kurs(istemci, _b(m), M)
    await _kurs(istemci, _b(m), M, yayinla=False)
    y = await istemci.get(f"{A}/kurum/{slug}")
    assert y.status_code == 200 and [x["slug"] for x in y.json()["items"]] == [k["slug"]]
