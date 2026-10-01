"""Faz 5R — Takvim ve randevu + toplantılar.

Kapsam: müsaitlik hesabı (sahip Europe/Istanbul; ziyaretçi yaz saatli Europe/Berlin ve
America/New_York; gece yarısını aşan aralık; tamponlar; en erken / en geç; günlük sınır;
resmî tatil ve arife; istisnalar; kapasite), çakışma koruması (eşzamanlı iki istek +
veritabanı benzersizliği), kapasite, sırayla atama dağılımı, ICS (REQUEST/CANCEL, UID,
SEQUENCE, UTC), imzalı yönetim bağlantısı (iptal sınırı, başka randevuda geçersiz,
yeniden planlama), hatırlatmaların tek kez gitmesi, ICS besleme jetonu (yenileme), müşteri
izolasyonu + modül kapalıyken 403/410, hız sınırı + bal küpü, anonimleştirme, CRM (yalnız
ajans), tür sınırı, ekip adayları, katılım, analiz, QR, Pages Function özeti.
"""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from conftest import jeton_uret

Y = "/api/v1/randevu/yonetim"
M = "/api/v1/randevularim"
A = "/api/v1/randevu"
MODUL = "/api/v1/moduller"
UTC = timezone.utc
#: Testlerin "şimdi"si: 5 Ekim 2026 Pazartesi 09:00 İstanbul.
SIMDI = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)
TARAYICI = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"


def _e(on: str = "randevu") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@randevu.dev"


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
    return {"User-Agent": TARAYICI, "X-MK-Istemci-IP": ip or f"198.51.100.{uuid.uuid4().int % 250 + 1}"}


def _utc(yil, ay, gun, saat, dk=0) -> datetime:
    return datetime(yil, ay, gun, saat, dk, tzinfo=UTC)


def _iso(an: datetime) -> str:
    return an.astimezone(UTC).isoformat().replace("+00:00", "Z")


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    from routers import randevu as r
    from services import hesap_ekibi
    from services import randevu as s

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    saat = {"an": SIMDI}
    monkeypatch.setattr(s, "simdi", lambda: saat["an"])
    yield saat
    r.hiz_sinirlarini_temizle()


@pytest.fixture
def epostalar(monkeypatch):
    """Giden e-postaları yakala (alıcı, konu, gövde, ek)."""
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
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/randevu", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _sayfa(istemci, basliklar, yol=Y, **govde):
    govde.setdefault("baslik", "Test Danışmanlık")
    y = await istemci.post(yol, json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _ajans_sayfasi(istemci, yonetici_basligi):
    """Ajansın kendi sayfası: tek tane; yoksa kurulur, varsa ayarları test için sıfırlanır."""
    y = await istemci.get(f"{Y}?hesap=ajans", headers=yonetici_basligi)
    items = y.json()["items"]
    if items:
        return items[0]
    return await _sayfa(istemci, yonetici_basligi, baslik="Ajans görüşmeleri")


async def _tur(istemci, basliklar, sid, yol=Y, **govde):
    govde.setdefault("ad", f"Tanışma {uuid.uuid4().hex[:4]}")
    govde.setdefault("sure_dk", 30)
    govde.setdefault("en_erken_dk", 0)
    y = await istemci.post(f"{yol}/{sid}/turler", json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _kurulum(istemci, basliklar, yol=Y, sayfa=None, haftalik=None, **tur):
    """Sayfa + sahip kişinin haftalık saatleri (varsayılan hafta içi 09:00–17:00) + tür."""
    p = sayfa or await _sayfa(istemci, basliklar, yol)
    kisiler = (await istemci.get(f"{yol}/{p['id']}/kisiler", headers=basliklar)).json()["items"]
    if haftalik is not None:
        y = await istemci.put(f"{yol}/{p['id']}/kisiler/{kisiler[0]['id']}", json={"haftalik": haftalik}, headers=basliklar)
        assert y.status_code == 200, y.text
    t = await _tur(istemci, basliklar, p["id"], yol, **tur)
    return p, kisiler[0], t


async def _musaitlik(istemci, slug, tur, bas="2026-10-05", gun=7, tz=None):
    q = f"?bas={bas}&gun={gun}" + (f"&tz={tz}" if tz else "")
    y = await istemci.get(f"{A}/{slug}/{tur}/musaitlik{q}", headers=_z())
    assert y.status_code == 200, y.text
    return y.json()


async def _rezervasyon(istemci, slug, tur, bas: datetime, ip=None, **govde):
    govde.setdefault("ad", "Ayşe Yılmaz")
    govde.setdefault("eposta", f"ayse-{uuid.uuid4().hex[:6]}@ornek.com")
    govde.setdefault("tz", "Europe/Istanbul")
    govde["baslangic"] = _iso(bas)
    return await istemci.post(f"{A}/{slug}/{tur}/rezervasyon", json=govde, headers=_z(ip))


# ---------------------------------------------------------------------------
# Saf müsaitlik hesabı
# ---------------------------------------------------------------------------
def _kural(**k):
    from services import randevu as s

    k.setdefault("id", 1)
    k.setdefault("sure_dk", 60)
    k.setdefault("adim_dk", 60)
    return s.TurKurali(**k)


def _kisi(haftalik, kid=1, istisnalar=None):
    from services import randevu as s

    return s.KisiTakvimi(id=kid, haftalik=haftalik, istisnalar=istisnalar or {})


def _slotlar(tur, kisiler, bas, bit, simdi_=SIMDI, mevcutlar=(), **ek):
    from services import randevu as s

    return s.slotlar(tur=tur, kisiler=kisiler, tz_adi="Europe/Istanbul", aralik_bas=bas, aralik_bit=bit,
                     mevcutlar=list(mevcutlar), simdi_=simdi_, **ek)


def test_ziyaretci_berlin_yaz_saati_degisimi():
    """TR'de yaz saati yok; Berlin 25 Ekim 2026'da kışa geçiyor: aynı UTC, farklı Berlin saati."""
    from services import randevu as s

    tur = _kural()
    kisi = _kisi({"0": [["09:00", "12:00"]]})
    a, b = s.ziyaretci_araligi(date(2026, 10, 19), 8, "Europe/Berlin")
    sl = _slotlar(tur, [kisi], a, b)
    assert [x.bas for x in sl] == [
        _utc(2026, 10, 19, 6), _utc(2026, 10, 19, 7), _utc(2026, 10, 19, 8),
        _utc(2026, 10, 26, 6), _utc(2026, 10, 26, 7), _utc(2026, 10, 26, 8),
    ]
    gunler = s.gunlere_bol(sl, "Europe/Berlin")
    assert [x["saat"] for x in gunler["2026-10-19"]] == ["08:00", "09:00", "10:00"]  # CEST (UTC+2)
    assert [x["saat"] for x in gunler["2026-10-26"]] == ["07:00", "08:00", "09:00"]  # CET (UTC+1)
    # Sahibin saat diliminde değişmiyor.
    tr = s.gunlere_bol(sl, "Europe/Istanbul")
    assert [x["saat"] for x in tr["2026-10-26"]] == ["09:00", "10:00", "11:00"]


def test_ziyaretci_new_york_gun_kaymasi_ve_yaz_saati():
    """İstanbul 01:00–03:00 → New York'ta bir önceki gün; 1 Kasım'da EDT→EST."""
    from services import randevu as s

    tur = _kural()
    kisi = _kisi({"0": [["01:00", "03:00"]]})  # Pazartesi gecesi
    a, b = s.ziyaretci_araligi(date(2026, 10, 25), 9, "America/New_York")
    gunler = s.gunlere_bol(_slotlar(tur, [kisi], a, b), "America/New_York")
    # Pazartesi 26 Ekim 01:00 İstanbul = 25 Ekim Pazar 22:00Z = 18:00 EDT
    assert [x["saat"] for x in gunler["2026-10-25"]] == ["18:00", "19:00"]
    # Pazartesi 2 Kasım 01:00 İstanbul = 1 Kasım 22:00Z = 17:00 EST
    assert [x["saat"] for x in gunler["2026-11-01"]] == ["17:00", "18:00"]
    assert "2026-10-26" not in gunler and "2026-11-02" not in gunler


def test_gece_yarisini_asan_aralik():
    from services import randevu as s

    tur = _kural()
    kisi = _kisi({"4": [["22:00", "02:00"]]})  # Cuma 22:00 → Cumartesi 02:00
    a, b = s.ziyaretci_araligi(date(2026, 10, 9), 2, "Europe/Istanbul")
    gunler = s.gunlere_bol(_slotlar(tur, [kisi], a, b), "Europe/Istanbul")
    assert [x["saat"] for x in gunler["2026-10-09"]] == ["22:00", "23:00"]
    assert [x["saat"] for x in gunler["2026-10-10"]] == ["00:00", "01:00"]  # Cumartesi'nin kendi saati yok


def test_aralik_dogrulama():
    from services import randevu as s

    assert s.araliklar_duzelt([["13:00", "17:00"], ["09:00", "12:00"]], "x") == [["09:00", "12:00"], ["13:00", "17:00"]]
    assert s.araliklar_duzelt([["18:00", "24:00"]], "x") == [["18:00", "24:00"]]
    for kotu in ([["09:00", "12:00"], ["11:00", "13:00"]], [["9:00", "12:00"]], [["25:00", "26:00"]], "x",
                 [["09:00", "09:10"]], [["09:00"]]):
        with pytest.raises(s.RandevuHatasi):
            s.araliklar_duzelt(kotu, "x")


def test_tamponlar_kesin_kural():
    from services import randevu as s

    hafta = _kisi({"2": [["09:00", "13:00"]]})
    a, b = s.ziyaretci_araligi(date(2026, 10, 7), 1, "Europe/Istanbul")
    # Mevcut: 10:00–10:30 İstanbul, sonrasında 15 dk tampon → 10:45'e kadar dolu.
    m = s.Mevcut(id=9, kisi_id=1, tur_id=99, bas=_utc(2026, 10, 7, 7), bit=_utc(2026, 10, 7, 7, 30),
                 dolu_bas=_utc(2026, 10, 7, 7), dolu_bit=_utc(2026, 10, 7, 7, 45))
    tampsiz = _kural(sure_dk=30, adim_dk=15)
    saatler = [x["saat"] for x in s.gunlere_bol(_slotlar(tampsiz, [hafta], a, b, mevcutlar=[m]), "Europe/Istanbul")["2026-10-07"]]
    assert "09:30" in saatler and "09:45" not in saatler  # 09:45–10:15 gerçek süre çakışır
    assert "10:30" not in saatler and "10:45" in saatler  # A'nın sonraki tamponu
    # Öncesinde 30 dk tamponlu tür: 10:45 olmaz (B'nin tamponu A'ya değer), 11:00 olur.
    onceli = _kural(id=2, sure_dk=30, adim_dk=15, tampon_once_dk=30)
    saatler = [x["saat"] for x in s.gunlere_bol(_slotlar(onceli, [hafta], a, b, mevcutlar=[m]), "Europe/Istanbul")["2026-10-07"]]
    assert "10:45" not in saatler and "11:00" in saatler
    # Sonrasında 30 dk tamponlu tür: 09:30–10:00 + tampon 10:30 → A'ya değer; 09:00 olur.
    sonrali = _kural(id=3, sure_dk=30, adim_dk=15, tampon_sonra_dk=30)
    saatler = [x["saat"] for x in s.gunlere_bol(_slotlar(sonrali, [hafta], a, b, mevcutlar=[m]), "Europe/Istanbul")["2026-10-07"]]
    assert "09:00" in saatler and "09:30" not in saatler and "09:15" not in saatler


def test_en_erken_ve_en_gec():
    from services import randevu as s

    kisi = _kisi({str(g): [["09:00", "17:00"]] for g in range(7)})
    tur = _kural(en_erken_dk=240, en_gec_gun=2)
    a, b = s.ziyaretci_araligi(date(2026, 10, 5), 7, "Europe/Istanbul")
    sl = _slotlar(tur, [kisi], a, b, simdi_=_utc(2026, 10, 5, 4))  # 07:00 İstanbul
    assert sl[0].bas == _utc(2026, 10, 5, 8)  # 4 saat sonrası: 11:00 İstanbul
    assert max(x.bas for x in sl) < _utc(2026, 10, 7, 4)  # en geç 2 gün


def test_gunluk_sinir():
    from services import randevu as s

    kisi = _kisi({"2": [["09:00", "17:00"]], "3": [["09:00", "17:00"]]})
    tur = _kural(id=5, sure_dk=60, adim_dk=60, gunluk_sinir=2)
    mevcut = [
        s.Mevcut(id=i, kisi_id=1, tur_id=5, bas=_utc(2026, 10, 7, 6 + i), bit=_utc(2026, 10, 7, 7 + i),
                 dolu_bas=_utc(2026, 10, 7, 6 + i), dolu_bit=_utc(2026, 10, 7, 7 + i)) for i in (0, 1)
    ]
    a, b = s.ziyaretci_araligi(date(2026, 10, 7), 2, "Europe/Istanbul")
    gunler = s.gunlere_bol(_slotlar(tur, [kisi], a, b, mevcutlar=mevcut), "Europe/Istanbul")
    assert "2026-10-07" not in gunler and len(gunler["2026-10-08"]) == 8
    # Başka türün randevuları bu türün sınırına sayılmaz.
    baska = [s.Mevcut(**{**m.__dict__, "tur_id": 77}) for m in mevcut]
    gunler = s.gunlere_bol(_slotlar(tur, [kisi], a, b, mevcutlar=baska), "Europe/Istanbul")
    assert len(gunler["2026-10-07"]) == 6


def test_resmi_tatil_arife_ve_istisnalar():
    from services import randevu as s

    kisi = _kisi({str(g): [["09:00", "17:00"]] for g in range(7)}, istisnalar={date(2026, 10, 30): [["18:00", "20:00"]]})
    tur = _kural()
    a, b = s.ziyaretci_araligi(date(2026, 10, 27), 5, "Europe/Istanbul")
    ortak = {"tatiller": {date(2026, 10, 29)}, "yarim_gunler": {date(2026, 10, 28)}}
    gunler = s.gunlere_bol(_slotlar(tur, [kisi], a, b, tatilde_kapali=True, **ortak,
                                    sayfa_istisnalari={date(2026, 10, 31): []}), "Europe/Istanbul")
    assert "2026-10-29" not in gunler  # Cumhuriyet Bayramı
    assert [x["saat"] for x in gunler["2026-10-28"]] == ["09:00", "10:00", "11:00", "12:00"]  # arife 13:00
    assert [x["saat"] for x in gunler["2026-10-30"]] == ["18:00", "19:00"]  # kişiye özel saat
    assert "2026-10-31" not in gunler  # ekip istisnası: kapalı
    assert len(gunler["2026-10-27"]) == 8
    # Seçenek kapalıysa tatil normal gün.
    gunler = s.gunlere_bol(_slotlar(tur, [kisi], a, b, tatilde_kapali=False, **ortak), "Europe/Istanbul")
    assert len(gunler["2026-10-29"]) == 8


def test_kapasite_grup():
    from services import randevu as s

    kisi = _kisi({"2": [["09:00", "12:00"]]})
    tur = _kural(id=8, kapasite=3)
    bas = _utc(2026, 10, 7, 6)
    m = [s.Mevcut(id=i, kisi_id=1, tur_id=8, bas=bas, bit=bas + timedelta(hours=1), dolu_bas=bas,
                  dolu_bit=bas + timedelta(hours=1)) for i in range(2)]
    a, b = s.ziyaretci_araligi(date(2026, 10, 7), 1, "Europe/Istanbul")
    sl = {x.bas: x.kalan for x in _slotlar(tur, [kisi], a, b, mevcutlar=m)}
    assert sl[bas] == 1 and sl[_utc(2026, 10, 7, 7)] == 3
    sl = {x.bas: x.kalan for x in _slotlar(tur, [kisi], a, b, mevcutlar=m + [s.Mevcut(**{**m[0].__dict__, "id": 5})])}
    assert bas not in sl


def test_sirali_atama_esit_dagilim_ve_ilk_musait():
    from services import randevu as s

    dagilim = {}
    secilenler = []
    for i in range(6):
        k = s.kisi_sec("sirali", [1, 2], [1, 2], dagilim)
        secilenler.append(k)
        d = dagilim.setdefault(k, s.DagilimBilgisi())
        d.sayi += 1
        d.son_atama = SIMDI + timedelta(minutes=i)
    assert secilenler.count(1) == 3 and secilenler.count(2) == 3 and secilenler[:2] == [1, 2]
    assert s.kisi_sec("ilk_musait", [2, 1], [1, 2], {1: s.DagilimBilgisi(sayi=9)}) == 1
    assert s.kisi_sec("ilk_musait", [2], [1, 2]) == 2
    assert s.kisi_sec("sirali", [], [1, 2]) is None


# ---------------------------------------------------------------------------
# ICS ve jetonlar
# ---------------------------------------------------------------------------
def test_ics_request_cancel_uid_utc():
    from services import randevu as s

    e = s.IcsEtkinligi(uid="abc123", bas=_utc(2026, 10, 7, 11), bit=_utc(2026, 10, 7, 11, 30),
                       baslik="Tanışma; görüşmesi, uzun " + "x" * 120, aciklama="Satır 1\nSatır 2",
                       konum="Çevrim içi", duzenleyen_eposta="sahip@ornek.com", duzenleyen_ad="Sahip",
                       katilimci_eposta="ayse@ornek.com", katilimci_ad="Ayşe", sira_no=2)
    ham = s.ics_uret([e], "REQUEST", an=SIMDI)
    assert ham.startswith("BEGIN:VCALENDAR\r\n") and ham.endswith("END:VCALENDAR\r\n")
    assert all(len(x.encode("utf-8")) <= 75 for x in ham.split("\r\n"))
    istek = ham.replace("\r\n ", "")  # katlanmış satırları aç (RFC 5545 3.1)
    assert "\r\nMETHOD:REQUEST\r\n" in istek and "UID:randevu-abc123@mehmetkuru.dev" in istek
    # 14:00 İstanbul = 11:00Z
    assert "DTSTART:20261007T110000Z" in istek and "DTEND:20261007T113000Z" in istek
    assert "SEQUENCE:2" in istek and "STATUS:CONFIRMED" in istek
    assert "ORGANIZER;CN=\"Sahip\":mailto:sahip@ornek.com" in istek
    assert "PARTSTAT=ACCEPTED" in istek and "mailto:ayse@ornek.com" in istek
    assert "Tanışma\\; görüşmesi\\, uzun" in istek and "Satır 1\\nSatır 2" in istek
    iptal = s.ics_uret([s.IcsEtkinligi(**{**e.__dict__, "iptal": True, "sira_no": 3})], "CANCEL", an=SIMDI).replace("\r\n ", "")
    assert "METHOD:CANCEL" in iptal and "STATUS:CANCELLED" in iptal and "UID:randevu-abc123@mehmetkuru.dev" in iptal
    assert "SEQUENCE:3" in iptal and "PARTSTAT=DECLINED" in iptal
    yayin = s.ics_uret([e], "PUBLISH", takvim_adi="Takvim", an=SIMDI)
    assert "METHOD:PUBLISH" in yayin and "ORGANIZER" not in yayin and "X-WR-CALNAME:Takvim" in yayin


def test_takvim_baglantilari():
    from services import randevu as s

    g = s.google_takvim_adresi("Görüşme", _utc(2026, 10, 7, 11), _utc(2026, 10, 7, 11, 30), "Not", "Yer")
    assert g.startswith("https://calendar.google.com/calendar/render?action=TEMPLATE")
    assert "dates=20261007T110000Z%2F20261007T113000Z" in g
    o = s.outlook_takvim_adresi("Görüşme", _utc(2026, 10, 7, 11), _utc(2026, 10, 7, 11, 30))
    assert "startdt=2026-10-07T11%3A00%3A00Z" in o and o.startswith("https://outlook.live.com/")


def test_yonetim_jetonu_baska_randevuda_gecersiz():
    from services import randevu as s

    j = s.yonetim_jetonu(12, "uid-a")
    assert s.jeton_kimligi(j) == 12 and s.yonetim_jetonu_gecerli_mi(j, 12, "uid-a")
    assert not s.yonetim_jetonu_gecerli_mi(j, 12, "uid-b")
    sahte = "13-" + j.split("-", 1)[1]
    assert not s.yonetim_jetonu_gecerli_mi(sahte, 13, "uid-a")
    b = s.besleme_jetonu(4, 1)
    assert s.besleme_jetonu_coz(b) == (4, 1) and s.besleme_jetonu_gecerli_mi(b, 4, 1)
    assert not s.besleme_jetonu_gecerli_mi(b, 4, 2)


def test_eposta_metni_7_dil():
    from services import randevu as s

    for dil in s.DILLER:
        konu, govde = s.eposta_govdesi(tur="onay", dil=dil, ad="Ali", sayfa="Ajans", tur_adi="Tanışma",
                                       zaman=s.zaman_yaz(_utc(2026, 10, 7, 11), "Europe/Istanbul", dil), sure=30,
                                       konum="x", kiminle="Mehmet", yonet_adresi="https://ornek/yonet",
                                       google="https://g", outlook="https://o")
        assert "Tanışma" in konu and "https://ornek/yonet" in govde and "14:00" in govde
    assert "Pazartesi" in s.zaman_yaz(_utc(2026, 10, 5, 11), "Europe/Istanbul", "tr")


# ---------------------------------------------------------------------------
# Yetki, modül kapısı, izolasyon
# ---------------------------------------------------------------------------
async def test_yetki_ve_modul_kapisi(istemci, yonetici_basligi, musteri_basligi):
    e = _e()
    assert (await istemci.get(Y)).status_code == 401
    assert (await istemci.get(Y, headers=musteri_basligi(e))).status_code == 403
    y = await istemci.get(M, headers=_b(e))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    await _modul(istemci, yonetici_basligi, e)
    y = await istemci.get(M, headers=_b(e))
    assert y.status_code == 200 and y.json()["items"] == []
    p = await _sayfa(istemci, _b(e), M)
    assert p["hesap_email"] == e and p["adres_url"].endswith(f"/randevu/{p['slug']}")
    y = await istemci.post(M, json={"baslik": "İkinci"}, headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "sayfa_var"
    # Başka müşteri bu sayfayı göremez.
    e2 = _e()
    await _modul(istemci, yonetici_basligi, e2)
    assert (await istemci.get(f"{M}/{p['id']}", headers=_b(e2))).status_code == 404
    assert (await istemci.get(M, headers=_b(e2))).json()["items"] == []
    # Yönetici görür; müşteriye özel süzgeç.
    y = await istemci.get(f"{Y}?hesap={e}", headers=yonetici_basligi)
    assert [x["id"] for x in y.json()["items"]] == [p["id"]]
    # Modül kapanınca: panel 403, herkese açık sayfa 410, besleme 404.
    await _modul(istemci, yonetici_basligi, e, acik=False)
    assert (await istemci.get(f"{M}/{p['id']}", headers=_b(e))).status_code == 403
    assert (await istemci.get(f"{A}/{p['slug']}")).status_code == 410
    jeton = p["besleme_adresi"].rsplit("/", 1)[1]
    assert (await istemci.get(f"{A}/besleme/{jeton}")).status_code == 404
    assert (await istemci.get(f"{A}/yok-boyle-sayfa")).status_code == 404


async def test_slug_kurallari_ve_ayarlar(istemci, yonetici_basligi):
    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p = await _sayfa(istemci, _b(e), M, baslik="Diş Kliniği Çağrı")
    assert p["slug"].startswith("dis-klinigi-cagri")
    for slug, kod in (("yonet", "slug_ayrilmis"), ("A b", "slug_gecersiz"), ("besleme", "slug_ayrilmis")):
        y = await istemci.put(f"{M}/{p['id']}", json={"slug": slug}, headers=_b(e))
        assert y.status_code == 400 and _kod(y) == kod, (slug, y.text)
    y = await istemci.put(f"{M}/{p['id']}", json={
        "hatirlatmalar": [60, 1440], "saat_dilimi": "Europe/Berlin", "renk": "#0EA5E9", "karsilama": "Hoş geldiniz",
        "iptal_sinir_dk": 60, "saklama_gun": 90, "arama_motoru": True,
    }, headers=_b(e))
    assert y.status_code == 200, y.text
    d = y.json()
    assert d["hatirlatmalar"] == [1440, 60] and d["saat_dilimi"] == "Europe/Berlin" and d["renk"] == "#0ea5e9"
    for govde in ({"hatirlatmalar": [61]}, {"saat_dilimi": "Mars/Olympus"}, {"saklama_gun": 5}, {"renk": "kirmizi"}):
        y = await istemci.put(f"{M}/{p['id']}", json=govde, headers=_b(e))
        assert y.status_code == 400, (govde, y.text)


async def test_tur_dogrulama_ve_tur_siniri(istemci, yonetici_basligi):
    e = _e()
    await _modul(istemci, yonetici_basligi, e, tur_siniri=2)
    p = await _sayfa(istemci, _b(e), M)
    t = await _tur(istemci, _b(e), p["id"], M, ad="30 dk tanışma görüşmesi", konum_turu="baglanti",
                   konum_degeri="https://zoom.us/j/123", sorular=[
                       {"etiket": "Şirketiniz?", "tur": "metin", "zorunlu": True},
                       {"etiket": "Bütçe", "tur": "secim", "secenekler": ["<1000", "1000+"]},
                   ])
    assert t["slug"] == "30-dk-tanisma-gorusmesi" and t["adim_dk"] == 30 and len(t["sorular"]) == 2
    assert t["kisiler"] and t["atama"] == "kisi"
    for govde, kod in (
        ({"ad": "x", "sure_dk": 10}, "aralik_disi"),
        ({"ad": "x", "sure_dk": 300}, "aralik_disi"),
        ({"ad": "x", "konum_turu": "baglanti", "konum_degeri": "javascript:alert(1)"}, "baglanti_gecersiz"),
        ({"ad": "x", "konum_turu": "yuz_yuze"}, "zorunlu"),
        ({"ad": "x", "sorular": [{"etiket": "a"}] * 6}, "soru_sayisi"),
        ({"ad": "x", "kapasite": 3, "atama": "sirali"}, "grup_tek_kisi"),
        ({"ad": "x", "kisiler": [999999]}, "kisi_gecersiz"),
        ({"ad": "x", "adim_dk": 7}, "adim_gecersiz"),
    ):
        y = await istemci.post(f"{M}/{p['id']}/turler", json=govde, headers=_b(e))
        assert y.status_code == 400 and _kod(y) == kod, (govde, y.text)
    await _tur(istemci, _b(e), p["id"], M, ad="İkinci")
    y = await istemci.post(f"{M}/{p['id']}/turler", json={"ad": "Üçüncü"}, headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "tur_siniri"
    # Telefon türünde sahibin numarası yoksa ziyaretçi telefonu zorunlu olur.
    y = await istemci.put(f"{M}/{p['id']}/turler/{t['id']}", json={"konum_turu": "telefon", "konum_degeri": ""}, headers=_b(e))
    assert y.status_code == 200 and y.json()["telefon"] == "zorunlu"


# ---------------------------------------------------------------------------
# Rezervasyon akışı (ajans): e-posta + .ics, CRM, yönetim bağlantısı
# ---------------------------------------------------------------------------
async def test_ajans_rezervasyon_eposta_ics_crm(istemci, yonetici_basligi, epostalar, db_oturumu):
    from models.crm import CrmAdaylari, CrmAktiviteler
    from models.notifications import Notifications

    p = await _ajans_sayfasi(istemci, yonetici_basligi)
    _, kisi, t = await _kurulum(istemci, yonetici_basligi, sayfa=p, sorular=[{"etiket": "Konu", "tur": "metin"}])
    acik = await istemci.get(f"{A}/{p['slug']}", headers=_z())
    assert acik.status_code == 200 and any(x["slug"] == t["slug"] for x in acik.json()["turler"])
    assert acik.headers.get("x-robots-tag") == "noindex"
    m = await _musaitlik(istemci, p["slug"], t["slug"], bas="2026-10-07", gun=1)
    assert m["gunler"]["2026-10-07"][0]["saat"] == "09:00"
    bas = _utc(2026, 10, 7, 7)  # 10:00 İstanbul
    eposta = f"musteri-adayi-{uuid.uuid4().hex[:6]}@firma.com.tr"
    y = await _rezervasyon(istemci, p["slug"], t["slug"], bas, ad="Can Demir", eposta=eposta, telefon="0555 111 22 33",
                           yanitlar={"s1": "Web sitesi"}, tz="Europe/Berlin", dil="de")
    assert y.status_code == 200, y.text
    d = y.json()
    assert d["randevu"]["baslangic"] == "2026-10-07T07:00:00Z" and d["randevu"]["konum"].startswith("https://meet.jit.si/MK-")
    assert d["yonet_adresi"].startswith("https://mehmetkuru.dev/randevu/yonet/")
    assert d["randevu"]["takvim"]["google"].startswith("https://calendar.google.com/")
    # Ziyaretçi e-postası: Almanca, .ics REQUEST eki, yönetim bağlantısı.
    ziyaretci = [x for x in epostalar if x["alici"] == eposta]
    assert len(ziyaretci) == 1
    z = ziyaretci[0]
    assert "Ihr Termin ist bestätigt" in z["konu"] and d["yonet_adresi"] in z["govde"] and "09:00" in z["govde"]
    ek = z["ek"]["ekler"][0]
    assert ek["tur"].startswith("text/calendar; method=REQUEST") and "METHOD:REQUEST" in ek["icerik"]
    assert f"UID:randevu-{d['randevu']['uid']}@" in ek["icerik"] and "DTSTART:20261007T070000Z" in ek["icerik"]
    # Sahip (ajans: yöneticiler) — yeni randevu bildirimi.
    assert any(x["alici"] == "yonetici@test.dev" and x["konu"].startswith("Yeni randevu: Can Demir") for x in epostalar)
    # Kalıcı bildirim kaydında yönetim jetonu yok.
    satirlar = (await db_oturumu.execute(select(Notifications).where(Notifications.recipient_email == eposta))).scalars().all()
    assert satirlar and all(d["jeton"] not in (s_.body or "") for s_ in satirlar)
    # Ziyaretçi panel kullanıcısı değil: yalnız e-posta kaydı (panel içi kopya yok).
    assert {(s_.event_type, s_.channel) for s_ in satirlar} == {("randevu_ziyaretci", "email")}
    # CRM: aday + toplantı etkinliği.
    aday = (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.email == eposta))).scalars().first()
    assert aday is not None and aday.kaynak == "form" and aday.telefon == "05551112233"
    akt = (await db_oturumu.execute(select(CrmAktiviteler).where(CrmAktiviteler.aday_id == aday.id, CrmAktiviteler.tur == "toplanti"))).scalars().all()
    assert len(akt) == 1 and "randevu" == akt[0].olay
    # Panelde görünür.
    y = await istemci.get(f"{Y}/{p['id']}/randevular", headers=yonetici_basligi)
    kayit = next(x for x in y.json()["items"] if x["uid"] == d["randevu"]["uid"])
    assert kayit["ad"] == "Can Demir" and kayit["kisi_id"] == kisi["id"] and kayit["yanitlar"][0]["yanit"] == "Web sitesi"
    assert kayit["crm_aday_id"] == aday.id


async def test_musteri_randevusu_crm_e_karismaz(istemci, yonetici_basligi, epostalar, db_oturumu):
    from models.crm import CrmAdaylari

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p, _, t = await _kurulum(istemci, _b(e), M)
    eposta = f"hasta-{uuid.uuid4().hex[:6]}@ornek.com"
    y = await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 7, 8), eposta=eposta)
    assert y.status_code == 200, y.text
    assert (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.email == eposta))).scalars().first() is None
    # Sahibine (müşteri) bildirim gitti, yöneticiye gitmedi.
    assert any(x["alici"] == e and x["konu"].startswith("Yeni randevu") for x in epostalar)
    assert not any(x["alici"] == "yonetici@test.dev" for x in epostalar)


async def test_rezervasyon_dogrulama_bal_kupu_hiz_siniri(istemci, yonetici_basligi, db_oturumu):
    from models.randevu import Randevular

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p, _, t = await _kurulum(istemci, _b(e), M, telefon="zorunlu")
    bas = _utc(2026, 10, 7, 9)
    y = await _rezervasyon(istemci, p["slug"], t["slug"], bas)
    assert y.status_code == 400 and _kod(y) == "zorunlu"  # telefon
    y = await _rezervasyon(istemci, p["slug"], t["slug"], bas, telefon="+90555", eposta="x@y")
    assert y.status_code == 400 and _kod(y) == "eposta_gecersiz"
    y = await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 7, 9, 7), telefon="+905551112233")
    assert y.status_code == 409 and _kod(y) == "dolu"  # adım dışı saat
    y = await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 10, 9), telefon="+905551112233")
    assert y.status_code == 409  # cumartesi kapalı
    # Bal küpü: başarılı görünür, kayıt yok.
    y = await _rezervasyon(istemci, p["slug"], t["slug"], bas, telefon="+905551112233", web_adresi="http://spam")
    assert y.status_code == 200 and y.json()["randevu"] is None
    sayi = len((await db_oturumu.execute(select(Randevular).where(Randevular.sayfa_id == p["id"]))).scalars().all())
    assert sayi == 0
    # Hız sınırı: aynı IP'den 10 dakikada 5'ten fazla deneme 429.
    kodlar = []
    for i in range(6):
        y = await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 8, 6 + i), ip="203.0.113.77",
                               telefon="+905551112233")
        kodlar.append(y.status_code)
    assert kodlar[:5] == [200] * 5 and kodlar[5] == 429


# ---------------------------------------------------------------------------
# Çakışma ve kapasite
# ---------------------------------------------------------------------------
async def test_eszamanli_iki_rezervasyon_biri_reddedilir(istemci, yonetici_basligi, db_oturumu):
    from models.randevu import Randevular

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p, _, t = await _kurulum(istemci, _b(e), M)
    bas = _utc(2026, 10, 7, 10)
    y1, y2 = await asyncio.gather(
        _rezervasyon(istemci, p["slug"], t["slug"], bas, ad="Bir"),
        _rezervasyon(istemci, p["slug"], t["slug"], bas, ad="İki"),
    )
    assert sorted([y1.status_code, y2.status_code]) == [200, 409], (y1.text, y2.text)
    kayitlar = (await db_oturumu.execute(select(Randevular).where(Randevular.sayfa_id == p["id"]))).scalars().all()
    assert len(kayitlar) == 1
    # Örtüşen (aynı başlangıçlı olmayan) saat de reddedilir: 30 dk tür, 15 dk sonra.
    t2 = await _tur(istemci, _b(e), p["id"], M, ad="Kısa", sure_dk=15, adim_dk=15)
    y = await _rezervasyon(istemci, p["slug"], t2["slug"], bas + timedelta(minutes=15))
    assert y.status_code == 409 and _kod(y) == "dolu"


async def test_veritabani_benzersizligi(db_oturumu):
    from sqlalchemy.exc import IntegrityError

    from models.randevu import Randevular

    bas = _utc(2030, 1, 1, 9)
    ortak = dict(sayfa_id=-1, tur_id=-1, kisi_id=-424242, baslangic=bas, bitis=bas + timedelta(minutes=30),
                 dolu_bas=bas, dolu_bit=bas + timedelta(minutes=30), koltuk=0)
    db_oturumu.add(Randevular(uid=uuid.uuid4().hex, **ortak))
    await db_oturumu.commit()
    db_oturumu.add(Randevular(uid=uuid.uuid4().hex, **ortak))
    with pytest.raises(IntegrityError):
        await db_oturumu.commit()
    await db_oturumu.rollback()
    # İptal edilen (koltuğu boş) kayıtlar çakışmaz.
    db_oturumu.add(Randevular(uid=uuid.uuid4().hex, **{**ortak, "koltuk": None, "durum": "iptal"}))
    db_oturumu.add(Randevular(uid=uuid.uuid4().hex, **{**ortak, "koltuk": None, "durum": "iptal"}))
    await db_oturumu.commit()


async def test_grup_kapasitesi_ve_ortak_oda(istemci, yonetici_basligi):
    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p, _, t = await _kurulum(istemci, _b(e), M, ad="Atölye", sure_dk=60, kapasite=2)
    bas = _utc(2026, 10, 7, 6)
    y1 = await _rezervasyon(istemci, p["slug"], t["slug"], bas, ad="A")
    m = await _musaitlik(istemci, p["slug"], t["slug"], bas="2026-10-07", gun=1)
    assert m["gunler"]["2026-10-07"][0]["kalan"] == 1
    y2 = await _rezervasyon(istemci, p["slug"], t["slug"], bas, ad="B")
    y3 = await _rezervasyon(istemci, p["slug"], t["slug"], bas, ad="C")
    assert (y1.status_code, y2.status_code, y3.status_code) == (200, 200, 409)
    assert y1.json()["randevu"]["konum"] == y2.json()["randevu"]["konum"]  # aynı Jitsi odası
    m = await _musaitlik(istemci, p["slug"], t["slug"], bas="2026-10-07", gun=1)
    assert m["gunler"]["2026-10-07"][0]["saat"] == "10:00"


async def test_sirali_atama_ve_ekip(istemci, yonetici_basligi, db_oturumu):
    import json

    from models.hesap_uyeleri import HesapUyeleri
    from models.randevu import Randevular
    from services import hesap_ekibi as he

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p = await _sayfa(istemci, _b(e), M)
    uye = _e("uye")
    y = await istemci.post(f"{M}/{p['id']}/kisiler", json={"eposta": uye}, headers=_b(e))
    assert y.status_code == 403 and _kod(y) == "kisi_aday_degil"
    db_oturumu.add(HesapUyeleri(hesap_email=e, uye_email=uye, rol="uye", izinler=json.dumps(list(he.ROL_VARSAYILAN["uye"])),
                                durum="aktif", olusturma=he.simdi()))
    await db_oturumu.commit()
    he.onbellegi_temizle()
    kisiler = (await istemci.get(f"{M}/{p['id']}/kisiler", headers=_b(e))).json()
    assert {a["eposta"] for a in kisiler["adaylar"]} == {e, uye}
    y = await istemci.post(f"{M}/{p['id']}/kisiler", json={"eposta": uye, "ad": "Zeynep"}, headers=_b(e))
    assert y.status_code == 200, y.text
    ikinci = y.json()
    sahip = kisiler["items"][0]
    t = await _tur(istemci, _b(e), p["id"], M, ad="Ekip görüşmesi", atama="sirali", kisiler=[sahip["id"], ikinci["id"]])
    # Üye kendi hesabıyla değil sahibin hesabında (izinli) çalışabilir.
    y = await istemci.get(f"{M}/{p['id']}/turler", headers=_b(uye, e))
    assert y.status_code == 200 and len(y.json()["items"]) == 1
    for i in range(4):
        y = await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 7, 6 + i))
        assert y.status_code == 200, y.text
    kisiler_ = [r.kisi_id for r in (await db_oturumu.execute(select(Randevular).where(Randevular.tur_id == t["id"]))).scalars().all()]
    assert sorted(kisiler_) == sorted([sahip["id"], sahip["id"], ikinci["id"], ikinci["id"]])
    # Aynı saatte iki kişi de dolu değilse ikinci bir rezervasyon diğer kişiye düşer (ekip kapasitesi).
    y1 = await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 8, 6))
    y2 = await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 8, 6))
    y3 = await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 8, 6))
    assert (y1.status_code, y2.status_code, y3.status_code) == (200, 200, 409)
    # Yaklaşan randevusu olan kişi silinemez; son kişi silinemez.
    y = await istemci.delete(f"{M}/{p['id']}/kisiler/{ikinci['id']}", headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "yaklasan_randevu_var"


# ---------------------------------------------------------------------------
# Yönetim bağlantısı: iptal, yeniden planlama, süre sınırı
# ---------------------------------------------------------------------------
async def test_yonetim_baglantisi_iptal_yeniden_planlama(istemci, yonetici_basligi, epostalar, _ortam, db_oturumu):
    from models.randevu import Randevular

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p, _, t = await _kurulum(istemci, _b(e), M)
    y = await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 7, 7), ad="Ali", eposta="ali@ornek.com")
    d = y.json()
    jeton = d["jeton"]
    y2 = await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 7, 9), ad="Veli")
    jeton2 = y2.json()["jeton"]
    # Başka randevunun kimliğiyle imza tutmaz.
    sahte = jeton2.split("-")[0] + "-" + jeton.split("-", 1)[1]
    assert (await istemci.get(f"{A}/islem/{sahte}")).status_code == 404
    assert (await istemci.get(f"{A}/islem/abc")).status_code == 404
    ozet = (await istemci.get(f"{A}/islem/{jeton}")).json()
    assert ozet["ad"] == "Ali" and ozet["degistirilebilir"] is True and ozet["durum"] == "onayli"
    # Yeniden planla: kendi saati engel sayılmaz (30 dk ileri, örtüşen).
    m = (await istemci.get(f"{A}/islem/{jeton}/musaitlik?bas=2026-10-07&gun=1&tz=Europe/Istanbul")).json()
    assert "10:00" in [x["saat"] for x in m["gunler"]["2026-10-07"]] and "12:00" not in [x["saat"] for x in m["gunler"]["2026-10-07"]]
    epostalar.clear()
    y = await istemci.post(f"{A}/islem/{jeton}/yeniden", json={"baslangic": _iso(_utc(2026, 10, 7, 7, 30))})
    assert y.status_code == 200, y.text
    yeni = y.json()
    assert yeni["baslangic"] == "2026-10-07T07:30:00Z" and yeni["onceki_baslangic"] == "2026-10-07T07:00:00Z"
    assert yeni["uid"] == d["randevu"]["uid"]
    z = next(x for x in epostalar if x["alici"] == "ali@ornek.com")
    assert "yeniden planlandı" in z["konu"] and "SEQUENCE:1" in z["ek"]["ekler"][0]["icerik"]
    assert any(x["alici"] == e and x["konu"].startswith("Randevu yeniden planlandı") for x in epostalar)
    # Eski saat boşaldı.
    m = await _musaitlik(istemci, p["slug"], t["slug"], bas="2026-10-07", gun=1)
    saatler = [x["saat"] for x in m["gunler"]["2026-10-07"]]
    assert "10:30" not in saatler and "10:00" in saatler and "11:00" in saatler  # 10:30–11:00 dolu
    # Dolu saate taşınamaz.
    y = await istemci.post(f"{A}/islem/{jeton}/yeniden", json={"baslangic": _iso(_utc(2026, 10, 7, 9))})
    assert y.status_code == 409 and _kod(y) == "dolu"
    # İptal sınırı: başlangıca 2 saatten az kala değiştirilemez.
    _ortam["an"] = _utc(2026, 10, 7, 6)  # 09:00 İstanbul, randevu 10:30
    y = await istemci.post(f"{A}/islem/{jeton}/iptal", json={"neden": "Gelemiyorum"})
    assert y.status_code == 409 and _kod(y) == "iptal_suresi_gecti"
    _ortam["an"] = SIMDI
    epostalar.clear()
    y = await istemci.post(f"{A}/islem/{jeton}/iptal", json={"neden": "Gelemiyorum"})
    assert y.status_code == 200 and y.json()["durum"] == "iptal"
    z = next(x for x in epostalar if x["alici"] == "ali@ornek.com")
    ics = z["ek"]["ekler"][0]
    assert "method=CANCEL" in ics["tur"] and "METHOD:CANCEL" in ics["icerik"] and "SEQUENCE:2" in ics["icerik"]
    assert any(x["alici"] == e and "iptal edildi (ziyaretçi)" in x["konu"] and "Gelemiyorum" in x["govde"] for x in epostalar)
    r = (await db_oturumu.execute(select(Randevular).where(Randevular.uid == d["randevu"]["uid"]))).scalars().first()
    assert r.koltuk is None and r.iptal_eden == "ziyaretci"
    y = await istemci.post(f"{A}/islem/{jeton}/iptal", json={})
    assert y.status_code == 409 and _kod(y) == "zaten_iptal"
    # Takvim dosyası indirilebilir.
    y = await istemci.get(f"{A}/islem/{jeton2}/takvim.ics")
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/calendar") and "METHOD:PUBLISH" in y.text


async def test_sahip_iptali_ve_katilim(istemci, yonetici_basligi, epostalar, _ortam):
    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p, _, t = await _kurulum(istemci, _b(e), M)
    r1 = (await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 7, 7), eposta="z1@ornek.com")).json()
    r2 = (await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 7, 8), eposta="z2@ornek.com")).json()
    liste = (await istemci.get(f"{M}/{p['id']}/randevular", headers=_b(e))).json()["items"]
    k1 = next(x for x in liste if x["uid"] == r1["randevu"]["uid"])
    k2 = next(x for x in liste if x["uid"] == r2["randevu"]["uid"])
    epostalar.clear()
    y = await istemci.post(f"{M}/{p['id']}/randevular/{k1['id']}/iptal", json={"neden": "Hastalık"}, headers=_b(e))
    assert y.status_code == 200 and y.json()["durum"] == "iptal" and y.json()["iptal_eden"] == "sahip"
    z = next(x for x in epostalar if x["alici"] == "z1@ornek.com")
    assert "METHOD:CANCEL" in z["ek"]["ekler"][0]["icerik"] and "Hastalık" in z["govde"]
    assert (await istemci.get(f"{M}/{p['id']}/randevular?donem=iptal", headers=_b(e))).json()["toplam"] == 1
    # Katılım: başlamadan önce işaretlenemez.
    y = await istemci.put(f"{M}/{p['id']}/randevular/{k2['id']}/katilim", json={"katilim": "gelmedi"}, headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "henuz_baslamadi"
    _ortam["an"] = _utc(2026, 10, 7, 12)
    y = await istemci.put(f"{M}/{p['id']}/randevular/{k2['id']}/katilim", json={"katilim": "gelmedi"}, headers=_b(e))
    assert y.status_code == 200 and y.json()["katilim"] == "gelmedi"
    gecmis = (await istemci.get(f"{M}/{p['id']}/randevular?donem=gecmis", headers=_b(e))).json()
    assert [x["id"] for x in gecmis["items"]] == [k2["id"]]
    # Hafta görünümü (bas/bit).
    hafta = (await istemci.get(f"{M}/{p['id']}/randevular?bas=2026-10-05T00:00:00Z&bit=2026-10-12T00:00:00Z", headers=_b(e))).json()
    assert hafta["toplam"] == 2


# ---------------------------------------------------------------------------
# Hatırlatmalar (tek kez), besleme, anonimleştirme
# ---------------------------------------------------------------------------
async def test_hatirlatmalar_tek_kez(istemci, yonetici_basligi, epostalar, _ortam, db_oturumu):
    from services import randevu_kayit as rk

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p, _, t = await _kurulum(istemci, _b(e), M)
    eposta = f"hatirla-{uuid.uuid4().hex[:6]}@ornek.com"
    bas = _utc(2026, 10, 7, 11)  # 14:00 İstanbul, 2 gün sonra
    assert (await _rezervasyon(istemci, p["slug"], t["slug"], bas, eposta=eposta)).status_code == 200

    def hatirlatmalar():
        return [x for x in epostalar if x["alici"] == eposta and x["konu"].startswith("Hatırlatma")]

    await rk.hatirlatmalari_gonder(db_oturumu)
    assert hatirlatmalar() == []  # henüz vakti değil
    _ortam["an"] = bas - timedelta(hours=23)
    await rk.hatirlatmalari_gonder(db_oturumu)
    await rk.hatirlatmalari_gonder(db_oturumu)
    assert len(hatirlatmalar()) == 1
    _ortam["an"] = bas - timedelta(minutes=59)
    await rk.hatirlatmalari_gonder(db_oturumu)
    await rk.hatirlatmalari_gonder(db_oturumu)
    assert len(hatirlatmalar()) == 2
    # Zamanlı uç üzerinden de ikinci kez gitmez.
    y = await istemci.post("/api/v1/zamanli/yonetim/calistir", headers=yonetici_basligi)
    assert y.status_code == 200
    assert len(hatirlatmalar()) == 2


async def test_gec_kalinan_hatirlatmada_yalniz_en_yakini_gider(istemci, yonetici_basligi, epostalar, _ortam, db_oturumu):
    from services import randevu_kayit as rk

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p, _, t = await _kurulum(istemci, _b(e), M)
    eposta = f"gec-{uuid.uuid4().hex[:6]}@ornek.com"
    bas = _utc(2026, 10, 7, 11)
    assert (await _rezervasyon(istemci, p["slug"], t["slug"], bas, eposta=eposta)).status_code == 200
    _ortam["an"] = bas - timedelta(minutes=30)  # sunucu uyudu: 24 saat ve 1 saat hatırlatmaları kaçtı
    sonuc = await rk.hatirlatmalari_gonder(db_oturumu)
    hat = [x for x in epostalar if x["alici"] == eposta and x["konu"].startswith("Hatırlatma")]
    assert len(hat) == 1 and sonuc["atlanan"] >= 1


async def test_besleme_jetonu_ve_yenileme(istemci, yonetici_basligi):
    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p, _, t = await _kurulum(istemci, _b(e), M)
    await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 7, 7), ad="Besleme Kişisi")
    adres = p["besleme_adresi"]
    assert adres.startswith("https://mehmetkuru.dev/api/v1/randevu/besleme/") and adres.endswith(".ics")
    yol = adres.split("mehmetkuru.dev", 1)[1]
    y = await istemci.get(yol)
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/calendar")
    assert "METHOD:PUBLISH" in y.text and "Besleme Kişisi" in y.text and "X-WR-CALNAME" in y.text
    y = await istemci.post(f"{M}/{p['id']}/besleme/yenile", headers=_b(e))
    yeni = y.json()["besleme_adresi"]
    assert yeni != adres
    assert (await istemci.get(yol)).status_code == 404
    assert (await istemci.get(yeni.split("mehmetkuru.dev", 1)[1])).status_code == 200
    assert (await istemci.get(f"{A}/besleme/1-1-{'0' * 32}.ics")).status_code == 404


async def test_anonimlestirme(istemci, yonetici_basligi, db_oturumu):
    from models.randevu import Randevular

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p, kisi, t = await _kurulum(istemci, _b(e), M)
    eski = _utc(2026, 3, 1, 9)  # 180 günden eski
    db_oturumu.add(Randevular(uid=uuid.uuid4().hex, sayfa_id=p["id"], tur_id=t["id"], kisi_id=kisi["id"], hesap_email=e,
                              baslangic=eski, bitis=eski + timedelta(minutes=30), dolu_bas=eski,
                              dolu_bit=eski + timedelta(minutes=30), koltuk=0, ad="Eski Kişi", eposta="eski@ornek.com",
                              telefon="+905550000000", yanitlar='{"s1":"x"}', created_at=eski))
    await db_oturumu.commit()
    from models.notifications import Notifications
    from services import randevu_kayit as rk_

    rid = (await db_oturumu.execute(select(Randevular.id).where(Randevular.sayfa_id == p["id"]))).scalar_one()
    for olay, alici in (("randevu_ziyaretci", "eski@ornek.com"), ("randevu_yeni", e)):
        for kanal in ("inapp", "email"):
            db_oturumu.add(Notifications(recipient_email=alici, recipient_role="client", event_type=olay, channel=kanal,
                                         title="Yeni randevu: Eski Kişi", body="E-posta: eski@ornek.com", ref_type="randevular",
                                         ref_id=rid, created_at=eski))
    await db_oturumu.commit()
    y = await istemci.get(f"{M}/{p['id']}/randevular?donem=gecmis", headers=_b(e))
    kayit = y.json()["items"][0]
    assert kayit["anonim"] is True and kayit["ad"] is None and kayit["eposta"] is None and kayit["yanitlar"] == []
    assert y.json()["saklama_gun"] == 180
    # Bağlı bildirim kayıtları: ziyaretçininkiler silindi, sahibininkilerde kişisel bilgi kalmadı.
    db_oturumu.expire_all()
    kalan = (await db_oturumu.execute(select(Notifications).where(Notifications.ref_type == "randevular",
                                                                  Notifications.ref_id == rid))).scalars().all()
    assert {(n.event_type, n.channel) for n in kalan} == {("randevu_yeni", "inapp"), ("randevu_yeni", "email")}
    assert all("Eski Kişi" not in n.title and not n.body for n in kalan)
    assert await rk_.anonimlestir(db_oturumu) == 0  # ikinci çalıştırma: yapılacak iş yok
    await db_oturumu.commit()


# ---------------------------------------------------------------------------
# İstisnalar, analiz, QR, özet, logo, silme
# ---------------------------------------------------------------------------
async def test_istisna_analiz_qr_ozet_silme(istemci, yonetici_basligi):
    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p, kisi, t = await _kurulum(istemci, _b(e), M)
    y = await istemci.post(f"{M}/{p['id']}/istisnalar", json={"tarih": "2026-10-07", "araliklar": [], "aciklama": "İzin"},
                           headers=_b(e))
    assert y.status_code == 200
    y = await istemci.post(f"{M}/{p['id']}/istisnalar", json={"tarih": "2026-10-08", "kisi_id": kisi["id"],
                                                              "araliklar": [["14:00", "15:00"]]}, headers=_b(e))
    assert y.status_code == 200
    m = await _musaitlik(istemci, p["slug"], t["slug"], bas="2026-10-07", gun=2)
    assert "2026-10-07" not in m["gunler"] and [x["saat"] for x in m["gunler"]["2026-10-08"]] == ["14:00", "14:30"]
    assert len((await istemci.get(f"{M}/{p['id']}/istisnalar", headers=_b(e))).json()["items"]) == 2
    # Analiz: görüntüleme (bot sayılmaz) → rezervasyon dönüşümü.
    await istemci.get(f"{A}/{p['slug']}", headers=_z("192.0.2.10"))
    await istemci.get(f"{A}/{p['slug']}/{t['slug']}", headers=_z("192.0.2.11"))
    await istemci.get(f"{A}/{p['slug']}", headers={"User-Agent": "Googlebot/2.1", "X-MK-Istemci-IP": "192.0.2.12"})
    await _rezervasyon(istemci, p["slug"], t["slug"], _utc(2026, 10, 8, 11))
    a = (await istemci.get(f"{M}/{p['id']}/analiz", headers=_b(e))).json()
    assert a["goruntuleme"] == 2 and a["tekil"] == 2 and a["rezervasyon"] == 1 and a["donusum"] == 50.0
    assert a["turler"][0]["goruntuleme"] == 1 and a["turler"][0]["rezervasyon"] == 1
    # QR
    y = await istemci.get(f"{M}/{p['id']}/qr?bicim=svg", headers=_b(e))
    assert y.status_code == 200 and "<svg" in y.text
    y = await istemci.get(f"{M}/{p['id']}/qr?bicim=png&tur={t['slug']}", headers=_b(e))
    assert y.status_code == 200 and y.content[:8] == b"\x89PNG\r\n\x1a\n"
    # Pages Function özeti.
    o = (await istemci.get(f"{A}/{p['slug']}/ozet?tur={t['slug']}")).json()
    assert o["baslik"] == p["baslik"] and o["tur"]["slug"] == t["slug"] and o["indekslenebilir"] is False
    # Yaklaşan randevu varken sayfa ve tür silinmez.
    y = await istemci.delete(f"{M}/{p['id']}", headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "yaklasan_randevu_var"
    y = await istemci.delete(f"{M}/{p['id']}/turler/{t['id']}", headers=_b(e))
    assert y.status_code == 409


async def test_logo_ve_cop_kutusu(istemci, yonetici_basligi, db_oturumu):
    import io

    from PIL import Image

    from models.cop_kutusu import CopKutusu

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    p, _, t = await _kurulum(istemci, _b(e), M)
    tampon = io.BytesIO()
    Image.new("RGB", (200, 100), (124, 58, 237)).save(tampon, format="PNG")
    y = await istemci.post(f"{M}/{p['id']}/logo", files={"dosya": ("logo.png", tampon.getvalue(), "image/png")}, headers=_b(e))
    assert y.status_code == 200, y.text
    logo = y.json()["logo"]
    assert logo.startswith("/api/v1/randevu/gorsel/")
    y = await istemci.get(logo)
    assert y.status_code == 200 and y.headers["content-type"] == "image/webp"
    y = await istemci.delete(f"{M}/{p['id']}", headers=_b(e))
    assert y.status_code == 200
    kayitlar = (await db_oturumu.execute(select(CopKutusu).where(CopKutusu.sahip_email == e))).scalars().all()
    assert {k.tablo for k in kayitlar} == {"randevu_sayfalari", "randevu_turleri", "randevu_kisileri"}
    assert len({k.grup for k in kayitlar}) == 1  # birlikte geri gelir
    assert (await istemci.get(f"{A}/{p['slug']}")).status_code == 404


async def test_denetim_kisisel_veri_kopyalamaz():
    from services import denetim

    for tablo in ("randevular", "randevu_hatirlatmalari", "randevu_olaylari", "randevu_gorselleri"):
        assert tablo in denetim.HARIC_TABLOLAR


def test_modul_ve_izin_kaydi():
    from core import moduller as mf
    from services import bildirim_tercih as bt
    from services import hesap_ekibi as he

    m = mf.MODUL_SOZLUGU["randevu"]
    assert m.kategori == "is_araclari" and not m.varsayilan_acik and m.musteri_sekmesi == "randevu"
    assert m.varsayilan_ayarlar() == {"tur_siniri": 5}
    assert "randevu" in he.IZINLER and "randevu" in he.ROL_VARSAYILAN["uye"]
    assert he.OLAY_IZNI["randevu_yeni"] == "randevu"
    for olay in ("randevu_yeni", "randevu_degisti", "randevu_iptal"):
        assert olay in bt.OLAYLAR
    assert "randevu_ziyaretci" not in bt.OLAYLAR  # ziyaretçiye yalnız e-posta (matris dışı)
    # Eski (4M dönemi) varsayılan üye izinleri yeni izni kendiliğinden alır.
    import json

    eski = ["projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar", "asistanlar", "qr", "kartvizit", "menu"]
    assert "randevu" in he.izinleri_coz(json.dumps(eski), "uye")
