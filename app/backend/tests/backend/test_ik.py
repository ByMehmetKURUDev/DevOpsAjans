"""Faz 6I — İnsan kaynakları: personel, izin, vardiya, girişsiz personel portalı.

Kapsam: saf kurallar (4857 m.53 kıdem eşikleri + yaş grubu + ilk yıl, izin günü hesabı: çalışma günü +
resmi tatil + yarım gün, bakiye: devir + hak ediş − kullanım, artık yıl, vardiya uyarıları), yetki (401/403,
modül kapalı, müşteri yalnız kendi hesabı, yönetici ajans tam / müşteri salt okunur), personel sınırı ve veri
azaltma, CSV dışa/içe aktarma (enjeksiyon koruması), izin akışı (talep → onay → bakiye → e-posta; ret + not;
iptal + geri alma; çakışma/bakiye/yasal süre uyarıları; rapor türünde açıklama yok), ayarlar (Cumartesi çalışma,
tatil ekleme, sabit tatili kapatma), portal (imzalı bağlantı, noindex, izin talebi, idempotent, geri çekme,
yenile/iptal/ayrılma/modül kapalı), vardiya (şablon, uyarılar, kopyala, yayınla → portal + e-posta, CSV/PDF,
ICS), olaylar (webhook + otomasyon, kişisel veri yok), gelen kutusu (ajans personeli), haftalık özet, çöp kutusu.

Yasal varsayılanlar BİLGİLENDİRME amaçlıdır; testler hangi kurala dayandığını yorumda belirtir.
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from conftest import jeton_uret

Y = "/api/v1/ik-yonetim"
M = "/api/v1/ik"
P = "/api/v1/ik-portal"
MODUL = "/api/v1/moduller"
UTC = timezone.utc
#: Testlerin "şimdi"si: 5 Ekim 2026 Pazartesi 09:00 İstanbul.
SIMDI = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)


def _e(on: str = "ik") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@ik.dev"


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


def _z() -> dict:
    return {"User-Agent": "Mozilla/5.0 Test", "X-MK-Istemci-IP": f"198.51.100.{uuid.uuid4().int % 250 + 1}"}


def _jeton(adres: str) -> str:
    return adres.rstrip("/").rsplit("/", 1)[1]


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    from routers import ik as r
    from services import hesap_ekibi
    from services import ik as s

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
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/insan_kaynaklari", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _personel(istemci, basliklar, yol=Y, **govde):
    govde.setdefault("ad", f"Personel {uuid.uuid4().hex[:6]}")
    govde.setdefault("ise_giris", "2020-01-15")
    govde.setdefault("eposta", f"p-{uuid.uuid4().hex[:6]}@ornek.com")
    y = await istemci.post(f"{yol}/personel", json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _izin(istemci, basliklar, pid, yol=Y, **govde):
    govde.setdefault("tur", "yillik")
    govde.setdefault("baslangic", "2026-10-26")
    govde.setdefault("bitis", "2026-10-30")
    y = await istemci.post(f"{yol}/izinler", json={"personel_id": pid, **govde}, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _portal_adresi(istemci, basliklar, pid, yol=Y, islem="goster"):
    y = await istemci.post(f"{yol}/personel/{pid}/baglanti", json={"islem": islem}, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()["adres"]


def _kurallar(**ek):
    from services import ik as s

    return s.Kurallar(yasal=dict(s.VARSAYILAN_YASAL), **ek)


# ---------------------------------------------------------------------------
# Saf kurallar
# ---------------------------------------------------------------------------
def test_kidem_esikleri_yas_grubu_ve_ilk_yil():
    """4857 sayılı İş Kanunu m.53: bir yıl dolmadan hak yok; 1–5 yıl (5 dahil) 14 gün, 5'ten fazla 15'ten az 20 gün,
    15 yıl ve üstü 26 gün; 18 yaş ve altı ile 50 yaş ve üstüne en az 20 gün."""
    from services import ik as s

    k = _kurallar()
    assert [s.yillik_hak(y, k) for y in (0, 1, 2, 5, 6, 10, 14, 15, 30)] == [0, 14, 14, 14, 20, 20, 20, 26, 26]
    # Yaş grubu: en az 20 (kıdemi 26 olanı düşürmez); ilk yıl dolmadan yaş grubunda da hak yok.
    assert s.yillik_hak(1, k, "genc") == 20 and s.yillik_hak(3, k, "ileri") == 20 and s.yillik_hak(16, k, "ileri") == 26
    assert s.yillik_hak(0, k, "genc") == 0
    # Sözleşmeyle kanunun üstünde gün; kanundan azsa kanun geçerli.
    assert s.yillik_hak(2, k, ozel=18) == 18 and s.yillik_hak(20, k, ozel=18) == 26
    # Ayarlardan değişen eşikler (ör. işyeri politikası: 3. yıldan sonra 18 gün).
    k2 = _kurallar(kidem=((1, 15), (3, 18)), yas_en_az_gun=22)
    assert [s.yillik_hak(y, k2) for y in (0, 1, 2, 3, 10)] == [0, 15, 15, 18, 18]
    assert s.yillik_hak(1, k2, "genc") == 22
    # Tamamlanan kıdem yılı: yıl dönümünde artar.
    assert s.tamamlanan_yil(date(2020, 1, 15), date(2025, 1, 14)) == 4
    assert s.tamamlanan_yil(date(2020, 1, 15), date(2025, 1, 15)) == 5


def test_izin_gunu_calisma_gunu_resmi_tatil_ve_yarim_gun():
    """4857 m.56: hafta tatili ve ulusal bayram/genel tatil günleri izin süresine sayılmaz. 2429 sayılı Kanun:
    29 Ekim tam gün, 28 Ekim öğleden sonra (yarım gün)."""
    from services import ik as s

    k = _kurallar()
    h = s.tatil_haritasi([2026], (), [])
    # 26–30 Ekim 2026 (Pzt–Cum): 28 Ekim yarım, 29 Ekim tam tatil → 3,5 gün.
    assert s.izin_gunu(date(2026, 10, 26), date(2026, 10, 30), k.calisma_gunleri, h) == 3.5
    # Hafta sonu sayılmaz: 9–18 Ekim (iki hafta sonu) → 8 gün.
    assert s.izin_gunu(date(2026, 10, 9), date(2026, 10, 18), k.calisma_gunleri, h) == 6
    # 23 Nisan 2026 Perşembe tatil.
    assert s.izin_gunu(date(2026, 4, 20), date(2026, 4, 24), k.calisma_gunleri, h) == 4
    # Cumartesi çalışılan işyeri: Pzt–Cmt.
    assert s.izin_gunu(date(2026, 10, 5), date(2026, 10, 11), (0, 1, 2, 3, 4, 5), h) == 6
    # Kullanıcının eklediği dini bayram (yıla göre değişir, tohumlanmaz) ve arifesi.
    h2 = s.tatil_haritasi([2027], (), [(date(2027, 3, 9), True), (date(2027, 3, 10), False), (date(2027, 3, 11), False),
                                       (date(2027, 3, 12), False)])
    assert s.izin_gunu(date(2027, 3, 8), date(2027, 3, 12), k.calisma_gunleri, h2) == 1.5
    # Sabit tatil kapatılınca sayılır.
    h3 = s.tatil_haritasi([2026], ("04-23",), [])
    assert s.izin_gunu(date(2026, 4, 23), date(2026, 4, 23), k.calisma_gunleri, h3) == 1
    # Yarım gün izin (tek gün).
    assert s.izin_gunu(date(2026, 10, 6), date(2026, 10, 6), k.calisma_gunleri, h, yarim_gun=True) == 0.5
    sabitler = {t["sabit"]: t for t in s.sabit_tatiller(2026)}
    assert set(sabitler) == {"01-01", "04-23", "05-01", "05-19", "07-15", "08-30", "10-28", "10-29"}
    assert sabitler["10-28"]["yarim"] is True and sabitler["10-29"]["yarim"] is False


def test_bakiye_devir_hakedis_kullanim_ve_artik_yil():
    from services import ik as s

    k = _kurallar()
    p = SimpleNamespace(ise_giris=date(2020, 1, 15), devir_tarihi=date(2026, 1, 1), devir_gun=4.5, durum="aktif",
                        ayrilis_tarihi=None, yas_grubu="genel", yillik_gun_ozel=None)
    # Devir 4,5 + 15 Ocak 2026'da 6. yıl dönümü (20 gün) − 2026'da kullanılan 3 − devirden önceki izin sayılmaz.
    b = s.bakiye_hesapla(p, k, [(date(2026, 3, 2), 3.0), (date(2025, 6, 1), 5.0)], [(date(2026, 11, 2), 2.0)], date(2026, 10, 5))
    assert (b["devir"], b["kazanilan"], b["kullanilan"], b["kalan"], b["bekleyen"], b["kullanilabilir"]) == (4.5, 20, 3, 21.5, 2, 19.5)
    assert b["kidem_yil"] == 6 and b["yillik_hak"] == 20 and b["sonraki"] == {"tarih": "2027-01-15", "yil": 7, "gun": 20}
    # Devir yoksa işe girişten itibaren bütün yıl dönümleri: 5×14 + 20 = 90.
    p2 = SimpleNamespace(**{**p.__dict__, "devir_tarihi": None, "devir_gun": 0})
    assert s.bakiye_hesapla(p2, k, [], [], date(2026, 10, 5))["kazanilan"] == 90
    # İlk yıl dolmadan hak yok.
    p3 = SimpleNamespace(**{**p.__dict__, "ise_giris": date(2026, 3, 1), "devir_tarihi": None, "devir_gun": 0})
    assert s.bakiye_hesapla(p3, k, [], [], date(2026, 10, 5))["kalan"] == 0
    # Ayrılan personelde hak ayrılış gününde durur.
    p4 = SimpleNamespace(**{**p2.__dict__, "durum": "ayrildi", "ayrilis_tarihi": date(2023, 1, 10)})
    assert s.bakiye_hesapla(p4, k, [], [], date(2026, 10, 5))["kazanilan"] == 28
    # 29 Şubat'ta işe giren: artık olmayan yılda yıl dönümü 28 Şubat.
    assert s.yildonumu(date(2024, 2, 29), 1) == date(2025, 2, 28) and s.yildonumu(date(2024, 2, 29), 4) == date(2028, 2, 29)


def test_vardiya_uyarilari_kurallari():
    """Uyarılar ENGELLEMEZ: izinli kişi, çakışma, 11 saatten az dinlenme (Çalışma Süreleri Yönetmeliği m.5),
    haftalık 45 saati aşan plan (4857 m.63)."""
    from services import ik as s

    hb = date(2026, 10, 5)
    V = s.VardiyaOzeti

    def an(gun, saat):
        return datetime(2026, 10, gun, saat, 0)

    liste = [
        V(1, 7, an(5, 9), an(5, 18), 60),
        V(2, 7, an(5, 17), an(5, 22), 0),  # çakışıyor
        V(3, 8, an(5, 14), an(5, 23), 0),
        V(4, 8, an(6, 8), an(6, 17), 0),  # 9 saat dinlenme
        V(5, 9, an(7, 9), an(7, 17), 0),  # izinli gün
    ] + [V(10 + i, 10, an(5 + i, 8), an(5 + i, 18), 30) for i in range(5)]  # 47,5 saat
    uy = s.vardiya_uyarilari(liste, {9: {date(2026, 10, 7): "yillik"}}, _kurallar(), hb)
    turler = {(u["tur"], u["personel_id"]) for u in uy}
    assert {("cakisma", 7), ("dinlenme", 8), ("izinli", 9), ("haftalik", 10)} <= turler
    dinlenme = [u for u in uy if u["tur"] == "dinlenme"][0]
    assert dinlenme["saat"] == 9.0 and dinlenme["en_az"] == 11
    # Ayarla kapanır / eşik değişir.
    uy2 = s.vardiya_uyarilari(liste, {9: {date(2026, 10, 7): "yillik"}},
                              _kurallar(uyari_dinlenme=False, uyari_izinli=False, haftalik_en_cok_saat=50), hb)
    assert {u["tur"] for u in uy2} == {"cakisma"}


# ---------------------------------------------------------------------------
# Yetki ve kapsam
# ---------------------------------------------------------------------------
async def test_yetki_401_403_ve_modul_kapali(istemci, yonetici_basligi):
    m = _e()
    for yol in (f"{M}/meta", f"{M}/personel", f"{Y}/meta", f"{Y}/hesaplar"):
        assert (await istemci.get(yol)).status_code == 401, yol
    assert (await istemci.get(f"{Y}/personel", headers=_b(m))).status_code == 403
    assert (await istemci.post(f"{Y}/personel", json={"ad": "X", "ise_giris": "2024-01-01"}, headers=_b(m))).status_code == 403
    y = await istemci.get(f"{M}/meta", headers=_b(m))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    await _modul(istemci, yonetici_basligi, m)
    y = await istemci.get(f"{M}/meta", headers=_b(m))
    assert y.status_code == 200 and y.json()["personel_siniri"] == 25 and y.json()["ajans"] is False


async def test_musteri_yalniz_kendi_hesabi(istemci, yonetici_basligi):
    a, b = _e("a"), _e("b")
    for x in (a, b):
        await _modul(istemci, yonetici_basligi, x)
    pa = await _personel(istemci, _b(a), M, ad="A Kişisi")
    ia = (await _izin(istemci, _b(a), pa["id"], M))["izin"]
    hb = _b(b)
    for yontem, yol in (("GET", f"{M}/personel/{pa['id']}"), ("PUT", f"{M}/personel/{pa['id']}"), ("DELETE", f"{M}/personel/{pa['id']}"),
                        ("GET", f"{M}/izinler/{ia['id']}"), ("POST", f"{M}/izinler/{ia['id']}/karar"),
                        ("POST", f"{M}/personel/{pa['id']}/baglanti")):
        y = await istemci.request(yontem, yol, json={"karar": "onay", "ad": "Ele geçir"} if yontem != "GET" else None, headers=hb)
        assert y.status_code == 404, (yontem, yol, y.text)
    assert (await istemci.get(f"{M}/personel", headers=hb)).json()["items"] == []
    assert (await istemci.get(f"{M}/izinler", headers=hb)).json()["items"] == []
    y = await istemci.post(f"{M}/izinler", json={"personel_id": pa["id"], "tur": "yillik", "baslangic": "2026-11-02"}, headers=hb)
    assert y.status_code == 404
    y = await istemci.post(f"{M}/vardiyalar", json={"personel_id": pa["id"], "tarih": "2026-10-06", "baslangic": "09:00",
                                                     "bitis": "17:00"}, headers=hb)
    assert y.status_code == 404
    # Sorguda başka hesap yazmak müşteri ucunda işe yaramaz.
    assert (await istemci.get(f"{M}/personel", params={"hesap": a}, headers=hb)).json()["items"] == []


async def test_yonetici_ajans_tam_musteri_salt_okunur(istemci, yonetici_basligi):
    m = _e("destek")
    await _modul(istemci, yonetici_basligi, m)
    pm = await _personel(istemci, _b(m), M, ad="Müşteri Personeli")
    pa = await _personel(istemci, yonetici_basligi, ad=f"Ajans Personeli {uuid.uuid4().hex[:4]}")
    ajans = (await istemci.get(f"{Y}/personel", headers=yonetici_basligi)).json()["items"]
    assert pa["id"] in [p["id"] for p in ajans] and pm["id"] not in [p["id"] for p in ajans]
    assert pa["hesap_email"] is None
    # Müşteri hesabı seçili: okunur, yazılmaz.
    y = await istemci.get(f"{Y}/personel", params={"hesap": m}, headers=yonetici_basligi)
    assert [p["id"] for p in y.json()["items"]] == [pm["id"]]
    meta = (await istemci.get(f"{Y}/meta", params={"hesap": m}, headers=yonetici_basligi)).json()
    assert meta["salt_okunur"] is True and meta["hesap"] == m
    for yontem, yol, govde in (("POST", f"{Y}/personel?hesap={m}", {"ad": "X", "ise_giris": "2024-01-01"}),
                               ("PUT", f"{Y}/personel/{pm['id']}?hesap={m}", {"gorev": "Şef"}),
                               ("DELETE", f"{Y}/personel/{pm['id']}?hesap={m}", None),
                               ("PUT", f"{Y}/ayarlar?hesap={m}", {"firma_adi": "X"})):
        y = await istemci.request(yontem, yol, json=govde, headers=yonetici_basligi)
        assert y.status_code == 403 and _kod(y) == "salt_okunur", (yol, y.text)
    # Ajans görünümünden müşteri personeline ulaşılamaz (kapsam ayrık).
    assert (await istemci.get(f"{Y}/personel/{pm['id']}", headers=yonetici_basligi)).status_code == 404
    hesaplar = (await istemci.get(f"{Y}/hesaplar", headers=yonetici_basligi)).json()["items"]
    assert any(h["hesap_email"] == m and h["personel"] == 1 for h in hesaplar)


async def test_ekip_izni_ik(istemci, yonetici_basligi):
    from core.database import db_manager
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as he

    sahip, uye, ikci = _e("sahip"), _e("uye"), _e("ikci")
    await _modul(istemci, yonetici_basligi, sahip)
    async with db_manager.async_session_maker() as db:
        for kisi, izinler in ((uye, he.ROL_VARSAYILAN["uye"]), (ikci, ("projeler", "ik"))):
            db.add(HesapUyeleri(hesap_email=sahip, uye_email=kisi, rol="uye", izinler=json.dumps(list(izinler)), durum="aktif",
                                olusturma=he.simdi()))
        await db.commit()
    he.onbellegi_temizle()
    assert "ik" not in he.ROL_VARSAYILAN["uye"] and "ik" in he.ROL_VARSAYILAN["yonetici"]
    y = await istemci.get(f"{M}/personel", headers=_b(uye, sahip))
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"
    await _personel(istemci, _b(ikci, sahip), M, ad="Ekip Ekledi")
    assert [p["ad"] for p in (await istemci.get(f"{M}/personel", headers=_b(sahip))).json()["items"]] == ["Ekip Ekledi"]


def test_modul_kaydi_ve_eski_yonetici_varsayilani():
    import json as _json

    from core import moduller, sektor_paketleri
    from services import hesap_ekibi as he

    m = moduller.modul("insan_kaynaklari")
    assert m is not None and m.varsayilan_acik is False and m.kategori == "is_araclari" and not m.paketler
    assert m.musteri_sekmesi == "ik" and m.yonetici_sekmesi == "ik" and m.varsayilan_ayarlar() == {"personel_siniri": 25}
    assert all("insan_kaynaklari" not in p.moduller for p in sektor_paketleri.SEKTOR_PAKETLERI)
    # Canlıdaki (ik'sız; 6I ile birlikte yayına çıkan 6H `hukuk` da yok) yönetici varsayılanı olduğu gibi kayıtlı
    # üye yeni izni de alır.
    eski = sorted(set(he.IZINLER) - {"ik", "hukuk"})
    assert "ik" in he.izinleri_coz(_json.dumps(eski), "yonetici")


# ---------------------------------------------------------------------------
# Personel
# ---------------------------------------------------------------------------
async def test_personel_siniri_ve_veri_azaltma(istemci, yonetici_basligi):
    m = _e("sinir")
    await _modul(istemci, yonetici_basligi, m, personel_siniri=1)
    p = await _personel(istemci, _b(m), M, ad="Tek Kişi", tc_kimlik_no="12345678901", dogum_tarihi="1990-01-01",
                        adres="Gizli Sk.", saglik="—", yas_grubu="ileri", telefon="0555 111 22 33", departman="Mutfak")
    for alan in ("tc_kimlik_no", "dogum_tarihi", "adres", "saglik", "din"):
        assert alan not in p
    assert p["yas_grubu"] == "ileri" and p["telefon"] == "05551112233" and p["departman"] == "Mutfak"
    y = await istemci.post(f"{M}/personel", json={"ad": "İkinci", "ise_giris": "2024-01-01"}, headers=_b(m))
    assert y.status_code == 409 and _kod(y) == "personel_siniri" and y.json()["detail"]["sinir"] == 1
    # Ayrılan kişi sınırı boşaltır; yeniden aktif etmek sınıra takılır.
    y = await istemci.put(f"{M}/personel/{p['id']}", json={"durum": "ayrildi"}, headers=_b(m))
    assert y.status_code == 200 and y.json()["ayrilis_tarihi"] == "2026-10-05"
    await _personel(istemci, _b(m), M, ad="Yeni Gelen")
    y = await istemci.put(f"{M}/personel/{p['id']}", json={"durum": "aktif"}, headers=_b(m))
    assert y.status_code == 409 and _kod(y) == "personel_siniri"
    # Doğrulama.
    for govde, alan in (({"ad": "", "ise_giris": "2024-01-01"}, "ad"), ({"ad": "X"}, "ise_giris"),
                        ({"ad": "X", "ise_giris": "2024-01-01", "eposta": "bozuk"}, "eposta"),
                        ({"ad": "X", "ise_giris": "2024-01-01", "yas_grubu": "65"}, "yas_grubu"),
                        ({"ad": "X", "ise_giris": "2024-01-01", "devir_gun": "abc"}, "devir_gun"),
                        ({"ad": "X", "ise_giris": "2024-01-01", "devir_tarihi": "2023-01-01"}, "devir_tarihi")):
        y = await istemci.post(f"{Y}/personel", json=govde, headers=yonetici_basligi)
        assert y.status_code == 400 and y.json()["detail"].get("alan") == alan, (govde, y.text)


async def test_personel_csv_disa_ve_ice_aktar(istemci, yonetici_basligi):
    m = _e("csv")
    await _modul(istemci, yonetici_basligi, m, personel_siniri=4)
    var = await _personel(istemci, _b(m), M, ad="Eski Ad", eposta="var@ornek.com")
    await _personel(istemci, _b(m), M, ad="=HYPERLINK(\"x\")", eposta="formul@ornek.com")
    csv_metni = ("Ad Soyad;E-posta;Görev;Departman;İşe giriş tarihi;Devir;Durum\n"
                 "Ayşe Yılmaz;ayse@ornek.com;Kasiyer;Satış;15.03.2021;3,5;aktif\n"
                 "Var Olan;var@ornek.com;Şef;Mutfak;2019-05-01;;\n"
                 "Tarihsiz;;;;;;\n"
                 "Mehmet Demir;mehmet@ornek.com;Garson;Salon;01/02/2024;;\n"
                 "Fazla Kişi;fazla@ornek.com;;;2024-01-01;;\n")
    y = await istemci.post(f"{M}/personel/ice-aktar", json={"csv": csv_metni}, headers=_b(m))
    assert y.status_code == 200, y.text
    r = y.json()
    assert (r["eklenen"], r["guncellenen"], r["hata_sayisi"]) == (2, 1, 2)
    assert {h["kod"] for h in r["hatalar"]} == {"zorunlu", "personel_siniri"}
    liste = {p["eposta"]: p for p in (await istemci.get(f"{M}/personel", headers=_b(m))).json()["items"]}
    assert liste["ayse@ornek.com"]["ise_giris"] == "2021-03-15" and liste["ayse@ornek.com"]["devir_gun"] == 3.5
    assert liste["var@ornek.com"]["id"] == var["id"] and liste["var@ornek.com"]["gorev"] == "Şef"
    assert liste["mehmet@ornek.com"]["ise_giris"] == "2024-02-01"
    y = await istemci.get(f"{M}/personel.csv", headers=_b(m))
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/csv")
    metin = y.content.decode("utf-8-sig")
    assert metin.splitlines()[0].startswith("ad,eposta,telefon,gorev,departman,ise_giris")
    assert "'=HYPERLINK" in metin  # CSV enjeksiyonu: formül olarak çalışmasın
    y = await istemci.post(f"{M}/personel/ice-aktar", json={"csv": "isim_yok;eposta\nx;y\n"}, headers=_b(m))
    assert y.status_code == 400 and _kod(y) == "csv_baslik"


# ---------------------------------------------------------------------------
# İzin akışı
# ---------------------------------------------------------------------------
async def test_izin_onay_bakiye_eposta_iptal_ve_geri_al(istemci, yonetici_basligi, epostalar):
    m = _e("izin")
    await _modul(istemci, yonetici_basligi, m)
    p = await _personel(istemci, _b(m), M, ad="Selin Arslan", eposta="selin.ik@ornek.com", devir_tarihi="2026-01-01", devir_gun=10)
    # Devir 10 + 15 Ocak 2026'da 6. yıl dönümü (4857 m.53: 5 yıldan fazla → 20 gün) = 30.
    assert p["bakiye"]["kalan"] == 30 and p["bakiye"]["kidem_yil"] == 6
    r = await _izin(istemci, _b(m), p["id"], M, aciklama="Tatil")
    izin = r["izin"]
    assert izin["durum"] == "beklemede" and izin["gun"] == 3.5 and izin["takvim_gunu"] == 5 and r["uyarilar"] == []
    b = (await istemci.get(f"{M}/personel/{p['id']}", headers=_b(m))).json()["bakiye"]
    assert (b["kalan"], b["bekleyen"], b["kullanilabilir"]) == (30, 3.5, 26.5)
    epostalar.clear()
    y = await istemci.post(f"{M}/izinler/{izin['id']}/karar", json={"karar": "onay", "not": "İyi tatiller"}, headers=_b(m))
    assert y.status_code == 200 and y.json()["izin"]["durum"] == "onaylandi" and y.json()["izin"]["karar_veren"] == m
    b = (await istemci.get(f"{M}/personel/{p['id']}", headers=_b(m))).json()["bakiye"]
    assert (b["kalan"], b["kullanilan"], b["bekleyen"]) == (26.5, 3.5, 0)
    giden = [e for e in epostalar if e["alici"] == "selin.ik@ornek.com"]
    assert len(giden) == 1 and giden[0]["konu"] == "İzin talebiniz onaylandı" and "İyi tatiller" in giden[0]["govde"]
    assert "/personel/" in giden[0]["govde"]  # kişisel bağlantı e-postada (kalıcı kayıtta maskeli)
    from core.database import db_manager
    from models.notifications import Notifications

    async with db_manager.async_session_maker() as db:
        kayitlar = (await db.execute(select(Notifications).where(Notifications.recipient_email == "selin.ik@ornek.com"))).scalars().all()
    assert kayitlar and all(k.channel != "inapp" and "/personel/" not in (k.body or "") for k in kayitlar)
    # İkinci karar 409.
    y = await istemci.post(f"{M}/izinler/{izin['id']}/karar", json={"karar": "ret"}, headers=_b(m))
    assert y.status_code == 409 and _kod(y) == "karar_verilmis"
    # İptal: gün bakiyeye geri döner, personele bildirilir.
    epostalar.clear()
    y = await istemci.post(f"{M}/izinler/{izin['id']}/iptal", json={}, headers=_b(m))
    assert y.status_code == 200 and y.json()["izin"]["durum"] == "iptal"
    assert (await istemci.get(f"{M}/personel/{p['id']}", headers=_b(m))).json()["bakiye"]["kalan"] == 30
    assert [e["konu"] for e in epostalar if e["alici"] == "selin.ik@ornek.com"] == ["İzniniz iptal edildi"]
    # Geri al → yeniden beklemede.
    y = await istemci.post(f"{M}/izinler/{izin['id']}/geri-al", json={}, headers=_b(m))
    assert y.status_code == 200 and y.json()["izin"]["durum"] == "beklemede" and y.json()["izin"]["iptal_at"] is None
    y = await istemci.post(f"{M}/izinler/{izin['id']}/geri-al", json={}, headers=_b(m))
    assert y.status_code == 409


async def test_izin_ret_notu_cakisma_bakiye_ve_yasal_uyarilar(istemci, yonetici_basligi, epostalar):
    m = _e("uyari")
    await _modul(istemci, yonetici_basligi, m)
    p = await _personel(istemci, _b(m), M, ise_giris="2026-01-10", eposta="uyari.p@ornek.com")
    # İlk yıl dolmadı: yıllık izin bakiyesi yok → uyarı (engellemez).
    r = await _izin(istemci, _b(m), p["id"], M)
    assert {u["tur"] for u in r["uyarilar"]} == {"bakiye_yetersiz"}
    r2 = await _izin(istemci, _b(m), p["id"], M, tur="mazeret", baslangic="2026-10-29", bitis="2026-11-02")
    assert any(u["tur"] == "cakisan_talep" and u["izin_id"] == r["izin"]["id"] for u in r2["uyarilar"])
    y = await istemci.get(f"{M}/izinler/{r2['izin']['id']}", headers=_b(m))
    assert any(u["tur"] == "cakisan_talep" for u in y.json()["uyarilar"])
    epostalar.clear()
    y = await istemci.post(f"{M}/izinler/{r2['izin']['id']}/karar", json={"karar": "ret", "not": "Yoğun dönem"}, headers=_b(m))
    assert y.status_code == 200 and y.json()["izin"]["durum"] == "reddedildi" and y.json()["izin"]["karar_notu"] == "Yoğun dönem"
    giden = [e for e in epostalar if e["alici"] == "uyari.p@ornek.com"]
    assert giden and giden[0]["konu"] == "İzin talebiniz reddedildi" and "Yoğun dönem" in giden[0]["govde"]
    # Rapor: YALNIZ tarih aralığı — açıklama alınmaz ve listelenmez.
    r3 = await _izin(istemci, _b(m), p["id"], M, tur="rapor", baslangic="2026-11-09", bitis="2026-11-10", aciklama="Grip — teşhis")
    assert r3["izin"]["aciklama"] == ""
    from core.database import db_manager
    from models.ik import IkIzinler

    async with db_manager.async_session_maker() as db:
        assert (await db.execute(select(IkIzinler.aciklama).where(IkIzinler.id == r3["izin"]["id"]))).scalar() is None
    # Yasal süre (Ek m.2: evlilik 3 gün) aşımı uyarısı; doğum izni takvim günüyle (16 hafta = 112).
    r4 = await _izin(istemci, _b(m), p["id"], M, tur="evlilik", baslangic="2026-11-16", bitis="2026-11-20")
    assert any(u["tur"] == "yasal_sure_asildi" and u["yasal"] == 3 and u["istenen"] == 5 for u in r4["uyarilar"])
    r5 = await _izin(istemci, _b(m), p["id"], M, tur="dogum", baslangic="2026-12-01", bitis="2027-03-31")
    assert any(u["tur"] == "yasal_sure_asildi" and u["birim"] == "takvim" for u in r5["uyarilar"])
    # Ayardan değişince uyarı kalkar.
    await istemci.put(f"{M}/ayarlar", json={"yasal_gunler": {"evlilik": 5}}, headers=_b(m))
    y = await istemci.get(f"{M}/izinler/{r4['izin']['id']}", headers=_b(m))
    assert not any(u["tur"] == "yasal_sure_asildi" for u in y.json()["uyarilar"])
    # Doğrulama: bitiş önce, yarım gün çok günlü, geçersiz tür.
    for govde, kod in (({"baslangic": "2026-11-05", "bitis": "2026-11-01"}, "bitis_once"),
                       ({"baslangic": "2026-11-05", "bitis": "2026-11-06", "yarim_gun": True}, "yarim_tek_gun"),
                       ({"tur": "bordro"}, "secim_gecersiz")):
        y = await istemci.post(f"{M}/izinler", json={"personel_id": p["id"], "tur": "yillik", "baslangic": "2026-11-05", **govde},
                               headers=_b(m))
        assert y.status_code == 400 and _kod(y) == kod, (govde, y.text)
    # Doğrudan onaylı ekleme.
    r6 = await _izin(istemci, _b(m), p["id"], M, tur="ucretsiz", baslangic="2027-01-04", bitis="2027-01-04", onayli=True)
    assert r6["izin"]["durum"] == "onaylandi" and r6["izin"]["karar_veren"] == m


async def test_ayarlar_cumartesi_tatil_ekle_ve_sabit_kapat(istemci, yonetici_basligi):
    m = _e("ayar")
    await _modul(istemci, yonetici_basligi, m)
    hesapla = lambda **q: istemci.get(f"{M}/gun-hesapla", params=q, headers=_b(m))  # noqa: E731
    assert (await hesapla(bas="2026-10-05", bit="2026-10-11")).json() == {"gun": 5, "takvim_gunu": 7}
    y = await istemci.put(f"{M}/ayarlar", json={"calisma_gunleri": [0, 1, 2, 3, 4, 5], "firma_adi": "Kafe Ada"}, headers=_b(m))
    assert y.status_code == 200 and y.json()["calisma_gunleri"] == [0, 1, 2, 3, 4, 5]
    assert (await hesapla(bas="2026-10-05", bit="2026-10-11")).json()["gun"] == 6
    # Dini bayram yıla göre değişir: kullanıcı ekler (arife yarım gün + 3 gün).
    y = await istemci.post(f"{M}/tatiller", json={"tarih": "2027-03-09", "bitis": "2027-03-12", "ad": "Ramazan Bayramı", "yarim": True},
                           headers=_b(m))
    assert y.status_code == 200 and [t["yarim"] for t in y.json()["eklenen"]] == [True, False, False, False]
    assert (await hesapla(bas="2027-03-08", bit="2027-03-13")).json()["gun"] == 2.5  # Pzt + yarım + Cmt
    t = (await istemci.get(f"{M}/tatiller", params={"yil": 2027}, headers=_b(m))).json()
    assert len(t["eklenen"]) == 4 and len(t["sabit"]) == 8
    assert (await istemci.delete(f"{M}/tatiller/{t['eklenen'][-1]['id']}", headers=_b(m))).status_code == 200
    # Sabit tatili kapat.
    assert (await hesapla(bas="2026-04-23", bit="2026-04-23")).json()["gun"] == 0
    y = await istemci.put(f"{M}/ayarlar", json={"kapali_sabitler": ["04-23"]}, headers=_b(m))
    assert y.status_code == 200 and y.json()["kapali_sabitler"] == ["04-23"]
    assert (await hesapla(bas="2026-04-23", bit="2026-04-23")).json()["gun"] == 1
    # Kıdem kuralları ve doğrulama.
    for govde, alan in (({"calisma_gunleri": []}, "calisma_gunleri"), ({"calisma_gunleri": [7]}, "calisma_gunleri"),
                        ({"kidem_kurallari": [{"yil": 1, "gun": 14}, {"yil": 1, "gun": 20}]}, "kidem_kurallari"),
                        ({"kapali_sabitler": ["12-25"]}, "kapali_sabitler"), ({"tatil": 1, "en_az_dinlenme_saat": 0}, "en_az_dinlenme_saat")):
        y = await istemci.put(f"{M}/ayarlar", json=govde, headers=_b(m))
        assert y.status_code == 400 and y.json()["detail"].get("alan") == alan, (govde, y.text)
    y = await istemci.put(f"{M}/ayarlar", json={"kidem_kurallari": [{"yil": 1, "gun": 16}], "yas_en_az_gun": 22}, headers=_b(m))
    assert y.json()["kidem_kurallari"] == [{"yil": 1, "gun": 16}]
    p = await _personel(istemci, _b(m), M, ise_giris="2024-10-01", yas_grubu="genc")
    assert p["bakiye"]["kazanilan"] == 44  # 2025 ve 2026 yıl dönümü × 22 (yaş grubu en az)
    y = await istemci.put(f"{M}/ayarlar", json={"varsayilana_don": True}, headers=_b(m))
    assert y.json()["kidem_kurallari"] == [{"yil": 1, "gun": 14}, {"yil": 6, "gun": 20}, {"yil": 15, "gun": 26}]


# ---------------------------------------------------------------------------
# Personel portalı
# ---------------------------------------------------------------------------
async def test_portal_izin_talebi_bildirim_ve_idempotent(istemci, yonetici_basligi, epostalar):
    m = _e("portal")
    await _modul(istemci, yonetici_basligi, m)
    p = await _personel(istemci, _b(m), M, ad="Portal Kişi", eposta="portal.kisi@ornek.com", gorev="Garson",
                        devir_tarihi="2026-01-01", devir_gun=2)
    baska = await _personel(istemci, _b(m), M, ad="Başka Kişi")
    await _izin(istemci, _b(m), baska["id"], M, onayli=True)
    jeton = _jeton(await _portal_adresi(istemci, _b(m), p["id"], M))
    y = await istemci.get(f"{P}/{jeton}", headers=_z())
    assert y.status_code == 200 and "noindex" in y.headers["x-robots-tag"] and y.headers["referrer-policy"] == "no-referrer"
    v = y.json()
    assert v["personel"]["ad"] == "Portal Kişi" and v["bakiye"]["kalan"] == 22 and v["izinler"] == [] and v["vardiyalar"] == []
    assert "Başka Kişi" not in y.text and "eposta" not in v["personel"]
    epostalar.clear()
    govde = {"tur": "yillik", "baslangic": "2026-10-26", "bitis": "2026-10-30", "aciklama": "Aile ziyareti", "istek_kimligi": "abc-1"}
    y = await istemci.post(f"{P}/{jeton}/izin", json=govde, headers=_z())
    assert y.status_code == 200, y.text
    izin = y.json()["izin"]
    assert izin["durum"] == "beklemede" and izin["kaynak"] == "portal" and izin["gun"] == 3.5 and y.json()["tekrar"] is False
    # Başkasının izni personele gösterilmez (yalnız kendi çakışması).
    assert all(u["tur"] != "ayni_tarihte" for u in y.json()["uyarilar"])
    # Hesap sahibine bildirim.
    assert any(e["alici"] == m and "Yeni izin talebi: Portal Kişi" in e["konu"] for e in epostalar)
    # Aynı istek kimliği / aynı bekleyen talep ikinci kez açılmaz.
    y = await istemci.post(f"{P}/{jeton}/izin", json=govde, headers=_z())
    assert y.json()["tekrar"] is True and y.json()["izin"]["id"] == izin["id"]
    y = await istemci.post(f"{P}/{jeton}/izin", json={**govde, "istek_kimligi": "abc-2"}, headers=_z())
    assert y.json()["tekrar"] is True
    # Rapor: açıklama alınmaz.
    y = await istemci.post(f"{P}/{jeton}/izin", json={"tur": "rapor", "baslangic": "2026-10-06", "aciklama": "Teşhis"}, headers=_z())
    assert y.status_code == 200 and y.json()["izin"]["aciklama"] == ""
    # Çok eski tarih reddedilir; gün önizlemesi.
    y = await istemci.post(f"{P}/{jeton}/izin", json={"tur": "mazeret", "baslangic": "2026-01-02"}, headers=_z())
    assert y.status_code == 400 and _kod(y) == "cok_eski"
    y = await istemci.get(f"{P}/{jeton}/gun-hesapla", params={"bas": "2026-10-26", "bit": "2026-10-30"}, headers=_z())
    assert y.json() == {"gun": 3.5, "takvim_gunu": 5}
    v = (await istemci.get(f"{P}/{jeton}", headers=_z())).json()
    assert len(v["izinler"]) == 2 and v["bakiye"]["bekleyen"] == 3.5
    # Geri çek: yalnız bekleyen ve yalnız kendi talebi.
    y = await istemci.post(f"{P}/{jeton}/izin/{izin['id']}/geri-cek", json={}, headers=_z())
    assert y.status_code == 200 and y.json()["izin"]["durum"] == "iptal"
    assert (await istemci.post(f"{P}/{jeton}/izin/{izin['id']}/geri-cek", json={}, headers=_z())).status_code == 409
    baska_izin = (await istemci.get(f"{M}/izinler", params={"personel_id": baska["id"]}, headers=_b(m))).json()["items"][0]
    assert (await istemci.post(f"{P}/{jeton}/izin/{baska_izin['id']}/geri-cek", json={}, headers=_z())).status_code == 404


async def test_portal_jeton_yenile_iptal_ayrilma_ve_modul_kapali(istemci, yonetici_basligi, epostalar):
    m = _e("jeton")
    await _modul(istemci, yonetici_basligi, m)
    p = await _personel(istemci, _b(m), M, eposta="jeton.kisi@ornek.com")
    eski = _jeton(await _portal_adresi(istemci, _b(m), p["id"], M))
    assert (await istemci.get(f"{P}/{eski}", headers=_z())).status_code == 200
    # Bozuk imza / biçim → 404.
    assert (await istemci.get(f"{P}/{eski[:-1]}0", headers=_z())).status_code == 404
    assert (await istemci.get(f"{P}/uydurma", headers=_z())).status_code == 404
    # Yenile: eski bağlantı ölür; e-postayla gönder.
    epostalar.clear()
    y = await istemci.post(f"{M}/personel/{p['id']}/baglanti", json={"islem": "yenile", "gonder": True}, headers=_b(m))
    assert y.status_code == 200 and y.json()["gonderildi"] is True
    yeni = _jeton(y.json()["adres"])
    assert yeni != eski
    assert (await istemci.get(f"{P}/{eski}", headers=_z())).status_code == 404
    assert (await istemci.get(f"{P}/{yeni}", headers=_z())).status_code == 200
    assert [e["konu"] for e in epostalar if e["alici"] == "jeton.kisi@ornek.com"] == ["Personel sayfanız"]
    # İptal: 404/410 (yeni sürümle de açılmaz).
    y = await istemci.post(f"{M}/personel/{p['id']}/baglanti", json={"islem": "iptal"}, headers=_b(m))
    assert y.json() == {"portal_acik": False, "adres": None}
    assert (await istemci.get(f"{P}/{yeni}", headers=_z())).status_code == 404
    son = _jeton(await _portal_adresi(istemci, _b(m), p["id"], M))
    assert (await istemci.get(f"{P}/{son}", headers=_z())).status_code == 200
    # Personel ayrıldı → 410.
    await istemci.put(f"{M}/personel/{p['id']}", json={"durum": "ayrildi"}, headers=_b(m))
    y = await istemci.get(f"{P}/{son}", headers=_z())
    assert y.status_code == 410 and _kod(y) == "personel_ayrildi"
    await istemci.put(f"{M}/personel/{p['id']}", json={"durum": "aktif"}, headers=_b(m))
    # Modül kapalı → 410.
    await _modul(istemci, yonetici_basligi, m, acik=False)
    y = await istemci.get(f"{P}/{son}", headers=_z())
    assert y.status_code == 410 and _kod(y) == "modul_kapali"
    await _modul(istemci, yonetici_basligi, m)
    # Bağlantı iptal edildiğinde portal_acik false iken jeton sürümü doğruysa 410.
    from core.database import db_manager
    from models.ik import IkPersonel

    async with db_manager.async_session_maker() as db:
        kayit = (await db.execute(select(IkPersonel).where(IkPersonel.id == p["id"]))).scalars().one()
        kayit.portal_acik = False
        await db.commit()
    y = await istemci.get(f"{P}/{son}", headers=_z())
    assert y.status_code == 410 and _kod(y) == "baglanti_kapali"


async def test_gelen_kutusu_ajans_personeli_izin_talebi(istemci, yonetici_basligi, epostalar):
    ad = f"Gelen Personel {uuid.uuid4().hex[:5]}"
    p = await _personel(istemci, yonetici_basligi, ad=ad, eposta=f"gk-{uuid.uuid4().hex[:5]}@ornek.com", departman="Tasarım")
    jeton = _jeton(await _portal_adresi(istemci, yonetici_basligi, p["id"]))
    y = await istemci.post(f"{P}/{jeton}/izin", json={"tur": "mazeret", "baslangic": "2026-10-12", "aciklama": "Taşınma"}, headers=_z())
    assert y.status_code == 200
    iid = y.json()["izin"]["id"]
    y = await istemci.get("/api/v1/gelen-kutusu", params={"kaynak": "izin_talebi", "q": ad}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    ogeler = [o for o in y.json()["ogeler"] if o["kimlik"] == iid]
    assert len(ogeler) == 1 and ogeler[0]["durum"] == "yeni" and ogeler[0]["kisi_ad"] == ad
    eylemler = {e["anahtar"]: e["istek"] for e in ogeler[0]["eylemler"]}
    assert set(eylemler) == {"onayla", "reddet"}
    onay = eylemler["onayla"]
    y = await istemci.request(onay["yontem"], onay["yol"], json=onay["govde"], headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["izin"]["durum"] == "onaylandi"
    y = await istemci.get("/api/v1/gelen-kutusu", params={"kaynak": "izin_talebi", "q": ad, "durum": "hepsi"}, headers=yonetici_basligi)
    assert [o["durum"] for o in y.json()["ogeler"] if o["kimlik"] == iid] == ["kapandi"]
    # Müşterinin personelinin talebi ajansın gelen kutusuna düşmez.
    m = _e("gk")
    await _modul(istemci, yonetici_basligi, m)
    pm = await _personel(istemci, _b(m), M, ad=f"Müşteri {ad}")
    jm = _jeton(await _portal_adresi(istemci, _b(m), pm["id"], M))
    await istemci.post(f"{P}/{jm}/izin", json={"tur": "mazeret", "baslangic": "2026-10-13"}, headers=_z())
    y = await istemci.get("/api/v1/gelen-kutusu", params={"kaynak": "izin_talebi", "q": f"Müşteri {ad}"}, headers=yonetici_basligi)
    assert y.json()["ogeler"] == []


# ---------------------------------------------------------------------------
# Vardiya
# ---------------------------------------------------------------------------
async def test_vardiya_uyarilar_kopyala_yayinla_portal_ve_eposta(istemci, yonetici_basligi, epostalar):
    m = _e("vardiya")
    await _modul(istemci, yonetici_basligi, m)
    a = await _personel(istemci, _b(m), M, ad="Ali Vardiya", eposta="ali.vardiya@ornek.com")
    b = await _personel(istemci, _b(m), M, ad="Banu Vardiya", eposta="banu.vardiya@ornek.com")
    y = await istemci.post(f"{M}/sablonlar", json={"ad": "Sabah", "baslangic": "08:00", "bitis": "17:00", "mola_dk": 60, "renk": "#16a34a"},
                           headers=_b(m))
    assert y.status_code == 200 and y.json()["net_dk"] == 480
    sabah = y.json()
    gece = (await istemci.post(f"{M}/sablonlar", json={"ad": "Gece", "baslangic": "22:00", "bitis": "06:00"}, headers=_b(m))).json()
    assert gece["gece"] is True
    # Banu 7 Ekim'de onaylı izinli.
    await _izin(istemci, _b(m), b["id"], M, tur="mazeret", baslangic="2026-10-07", bitis="2026-10-07", onayli=True)

    async def ekle(pid, tarih, **g):
        y = await istemci.post(f"{M}/vardiyalar", json={"personel_id": pid, "tarih": tarih, **g}, headers=_b(m))
        assert y.status_code == 200, y.text
        return y.json()

    for gun in ("2026-10-05", "2026-10-06", "2026-10-08", "2026-10-09", "2026-10-10"):
        await ekle(a["id"], gun, sablon_id=sabah["id"])
    r = await ekle(a["id"], "2026-10-05", baslangic="16:00", bitis="20:00")  # çakışma
    assert any(u["tur"] == "cakisma" for u in r["uyarilar"])
    await ekle(b["id"], "2026-10-05", sablon_id=gece["id"])  # 22:00–06:00
    r = await ekle(b["id"], "2026-10-06", baslangic="14:00", bitis="20:00")  # 8 saat dinlenme
    assert any(u["tur"] == "dinlenme" and u["saat"] == 8.0 for u in r["uyarilar"])
    r = await ekle(b["id"], "2026-10-07", sablon_id=sabah["id"])  # izinli güne vardiya (engellenmez)
    assert any(u["tur"] == "izinli" and u["izin_turu"] == "mazeret" for u in r["uyarilar"])
    r = await ekle(a["id"], "2026-10-11", baslangic="08:00", bitis="16:00")  # 5×8 + 4 + 8 = 52 > 45
    assert any(u["tur"] == "haftalik" and u["saat"] == 52.0 for u in r["uyarilar"])
    plan = (await istemci.get(f"{M}/vardiyalar", params={"hafta": "2026-10-07"}, headers=_b(m))).json()
    assert plan["hafta_bas"] == "2026-10-05" and plan["sayilar"]["taslak"] == 10
    assert {u["tur"] for u in plan["uyarilar"]} == {"cakisma", "dinlenme", "izinli", "haftalik"}
    assert plan["izinli"][str(b["id"])] == {"2026-10-07": "mazeret"} and plan["toplam_dk"][str(a["id"])] == 52 * 60
    # Ayarla kapanır.
    await istemci.put(f"{M}/ayarlar", json={"uyari_dinlenme": False, "haftalik_en_cok_saat": 60}, headers=_b(m))
    plan = (await istemci.get(f"{M}/vardiyalar", params={"hafta": "2026-10-05"}, headers=_b(m))).json()
    assert {u["tur"] for u in plan["uyarilar"]} == {"cakisma", "izinli"}
    # Yayınlanmadan portal görmez.
    ja = _jeton(await _portal_adresi(istemci, _b(m), a["id"], M))
    assert (await istemci.get(f"{P}/{ja}", headers=_z())).json()["vardiyalar"] == []
    epostalar.clear()
    y = await istemci.post(f"{M}/vardiyalar/yayinla", json={"hafta": "2026-10-05"}, headers=_b(m))
    assert y.json() == {"yayinlanan": 10, "etkilenen": 2, "bildirilen": 2}
    alicilar = sorted(e["alici"] for e in epostalar if e["konu"] == "Vardiya planınız yayınlandı")
    assert alicilar == ["ali.vardiya@ornek.com", "banu.vardiya@ornek.com"]
    ali_posta = [e for e in epostalar if e["alici"] == "ali.vardiya@ornek.com"][0]["govde"]
    assert "08:00–17:00" in ali_posta and "Banu" not in ali_posta
    v = (await istemci.get(f"{P}/{ja}", headers=_z())).json()
    assert len(v["vardiyalar"]) == 7 and {x["baslangic"] for x in v["vardiyalar"]} == {"08:00", "16:00"}
    ics = await istemci.get(f"{P}/{ja}/vardiyalar.ics", headers=_z())
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    assert ics.text.count("BEGIN:VEVENT") == 7 and "DTSTART:20261005T050000Z" in ics.text  # 08:00 İstanbul = 05:00 UTC
    # Yayındaki vardiya değişince yeniden bildirim yalnız ilgiliye.
    plan = (await istemci.get(f"{M}/vardiyalar", params={"hafta": "2026-10-05"}, headers=_b(m))).json()
    vid = [x for x in plan["vardiyalar"] if x["personel_id"] == a["id"] and x["tarih"] == "2026-10-11"][0]["id"]
    y = await istemci.put(f"{M}/vardiyalar/{vid}", json={"baslangic": "09:00"}, headers=_b(m))
    assert y.json()["vardiya"]["degisti"] is True and y.json()["vardiya"]["durum"] == "yayinda"
    epostalar.clear()
    y = await istemci.post(f"{M}/vardiyalar/yayinla", json={"hafta": "2026-10-05"}, headers=_b(m))
    assert y.json() == {"yayinlanan": 0, "etkilenen": 1, "bildirilen": 1}
    # Geçen haftayı kopyala → taslak; ayrılan personel kopyalanmaz; dolu gün atlanır.
    await istemci.put(f"{M}/personel/{b['id']}", json={"durum": "ayrildi"}, headers=_b(m))
    await ekle(a["id"], "2026-10-12", baslangic="10:00", bitis="14:00")
    y = await istemci.post(f"{M}/vardiyalar/kopyala", json={"hafta": "2026-10-12"}, headers=_b(m))
    # Ali'nin 5 Ekim'deki iki vardiyası (12 Ekim dolu) ve ayrılan Banu'nun üçü atlanır.
    assert y.json() == {"eklenen": 5, "atlanan": 5, "kaynak_hafta": "2026-10-05"}
    plan = (await istemci.get(f"{M}/vardiyalar", params={"hafta": "2026-10-12"}, headers=_b(m))).json()
    assert plan["sayilar"] == {"taslak": 6, "yayinda": 0, "degisti": 0}
    y = await istemci.post(f"{M}/vardiyalar/kopyala", json={"hafta": "2026-10-12", "uzerine_yaz": True}, headers=_b(m))
    assert y.json()["eklenen"] == 7
    # Ayrılmış kişiye vardiya eklenemez; mola süreyi aşamaz.
    y = await istemci.post(f"{M}/vardiyalar", json={"personel_id": b["id"], "tarih": "2026-10-13", "baslangic": "09:00", "bitis": "10:00"},
                           headers=_b(m))
    assert y.status_code == 409 and _kod(y) == "personel_ayrildi"
    y = await istemci.post(f"{M}/vardiyalar", json={"personel_id": a["id"], "tarih": "2026-10-13", "baslangic": "09:00", "bitis": "10:00",
                                                     "mola_dk": 60}, headers=_b(m))
    assert y.status_code == 400 and _kod(y) == "mola_uzun"


async def test_vardiya_csv_pdf_ve_sablon_silme(istemci, yonetici_basligi):
    m = _e("plan")
    await _modul(istemci, yonetici_basligi, m)
    await istemci.put(f"{M}/ayarlar", json={"firma_adi": "Plan Kafe"}, headers=_b(m))
    p = await _personel(istemci, _b(m), M, ad="=Plan Kişi")
    x = (await istemci.post(f"{M}/sablonlar", json={"ad": "Öğle", "baslangic": "11:00", "bitis": "19:00", "mola_dk": 30}, headers=_b(m))).json()
    await istemci.post(f"{M}/vardiyalar", json={"personel_id": p["id"], "tarih": "2026-10-06", "sablon_id": x["id"]}, headers=_b(m))
    y = await istemci.get(f"{M}/vardiyalar.csv", params={"hafta": "2026-10-06"}, headers=_b(m))
    satirlar = y.content.decode("utf-8-sig").splitlines()
    assert satirlar[0] == "personel,departman,tarih,baslangic,bitis,mola_dk,net_saat,sablon,durum,not"
    assert satirlar[1].startswith("'=Plan Kişi,,2026-10-06,11:00,19:00,30,7.5,Öğle,taslak")
    y = await istemci.get(f"{M}/vardiyalar.pdf", params={"hafta": "2026-10-06", "dil": "tr"}, headers=_b(m))
    assert y.status_code == 200 and y.content[:4] == b"%PDF" and y.headers["content-type"] == "application/pdf"
    from services.pdf_belge import pdf_metni

    metin = pdf_metni(y.content)
    assert "Haftalık vardiya planı" in metin and "Plan Kafe" in metin and "11:00–19:00" in metin
    # Şablon silinince vardiya saatleriyle kalır.
    assert (await istemci.delete(f"{M}/sablonlar/{x['id']}", headers=_b(m))).status_code == 200
    plan = (await istemci.get(f"{M}/vardiyalar", params={"hafta": "2026-10-06"}, headers=_b(m))).json()
    assert plan["vardiyalar"][0]["sablon_id"] is None and plan["vardiyalar"][0]["baslangic"] == "11:00"


# ---------------------------------------------------------------------------
# Takvim, ICS, dosyalar, çöp kutusu, olaylar, haftalık özet
# ---------------------------------------------------------------------------
async def test_izin_takvimi_ics_ve_csv(istemci, yonetici_basligi):
    m = _e("takvim")
    await _modul(istemci, yonetici_basligi, m)
    p = await _personel(istemci, _b(m), M, ad="Takvim Kişi")
    await _izin(istemci, _b(m), p["id"], M, onayli=True)
    await _izin(istemci, _b(m), p["id"], M, tur="mazeret", baslangic="2026-10-13", bitis="2026-10-13")
    t = (await istemci.get(f"{M}/izinler/takvim", params={"ay": "2026-10"}, headers=_b(m))).json()
    assert t["ilk"] == "2026-10-01" and t["son"] == "2026-10-31" and len(t["izinler"]) == 2
    assert {"tarih": "2026-10-29", "ad": "Cumhuriyet Bayramı", "oran": 1.0} in t["tatiller"]
    assert any(x["tarih"] == "2026-10-28" and x["oran"] == 0.5 for x in t["tatiller"])
    ics = await istemci.get(f"{M}/izinler.ics", headers=_b(m))
    assert ics.text.count("BEGIN:VEVENT") == 1 and "DTSTART;VALUE=DATE:20261026" in ics.text and "DTEND;VALUE=DATE:20261031" in ics.text
    csv_ = (await istemci.get(f"{M}/izinler.csv", headers=_b(m))).content.decode("utf-8-sig").splitlines()
    assert csv_[0].startswith("personel,tur,baslangic") and len(csv_) == 3
    assert (await istemci.get(f"{M}/izinler/takvim", params={"ay": "2026-13"}, headers=_b(m))).status_code == 400


async def test_dosya_ekle_indir_sil_ve_kapsam(istemci, yonetici_basligi):
    m, baska = _e("dosya"), _e("dosya2")
    for x in (m, baska):
        await _modul(istemci, yonetici_basligi, x)
    p = await _personel(istemci, _b(m), M)
    y = await istemci.post(f"{M}/personel/{p['id']}/dosyalar", files={"dosya": ("sozlesme.txt", b"is sozlesmesi", "text/plain")},
                           headers=_b(m))
    assert y.status_code == 200, y.text
    d = y.json()
    assert (await istemci.get(f"{M}/dosyalar/{d['id']}", headers=_b(m))).content == b"is sozlesmesi"
    assert (await istemci.get(f"{M}/dosyalar/{d['id']}", headers=_b(baska))).status_code == 404
    assert [x["id"] for x in (await istemci.get(f"{M}/personel/{p['id']}", headers=_b(m))).json()["dosyalar"]] == [d["id"]]
    assert (await istemci.delete(f"{M}/dosyalar/{d['id']}", headers=_b(baska))).status_code == 404
    assert (await istemci.delete(f"{M}/dosyalar/{d['id']}", headers=_b(m))).status_code == 200
    assert (await istemci.get(f"{M}/dosyalar/{d['id']}", headers=_b(m))).status_code == 404


async def test_personel_silme_cop_kutusu_ve_geri_alma(istemci, yonetici_basligi, db_oturumu):
    from models.cop_kutusu import CopKutusu

    m = _e("cop")
    await _modul(istemci, yonetici_basligi, m)
    p = await _personel(istemci, _b(m), M, ad="Çöp Personel")
    i = (await _izin(istemci, _b(m), p["id"], M))["izin"]
    await istemci.post(f"{M}/vardiyalar", json={"personel_id": p["id"], "tarih": "2026-10-06", "baslangic": "09:00", "bitis": "17:00"},
                       headers=_b(m))
    await istemci.post(f"{M}/personel/{p['id']}/dosyalar", files={"dosya": ("not.txt", b"belge", "text/plain")}, headers=_b(m))
    assert (await istemci.delete(f"{M}/personel/{p['id']}", headers=_b(m))).status_code == 200
    assert (await istemci.get(f"{M}/personel/{p['id']}", headers=_b(m))).status_code == 404
    satirlar = (await db_oturumu.execute(select(CopKutusu).where(CopKutusu.sahip_email == m))).scalars().all()
    assert {c.tablo for c in satirlar} == {"ik_personel", "ik_izinler", "ik_vardiyalar", "ik_dosyalar"}
    ana = [c for c in satirlar if c.tablo == "ik_personel"][0]
    assert ana.etiket == "Çöp Personel"
    # Müşteri kendi çöp kutusunda görür ve geri alır (izin ve vardiya birlikte gelir).
    y = await istemci.post(f"/api/v1/cop-kutum/{ana.id}/geri-al", headers=_b(m))
    assert y.status_code == 200, y.text
    d = (await istemci.get(f"{M}/personel/{p['id']}", headers=_b(m))).json()
    assert [x["id"] for x in d["izinler"]] == [i["id"]] and len(d["dosyalar"]) == 1


async def test_olay_katalogu_webhook_ve_otomasyon_baglami(istemci, yonetici_basligi, db_oturumu, monkeypatch):
    from models.api_erisimi import WebhookTeslimatlari, WebhookUcNoktalari
    from services import otomasyon_kural, webhook
    from services.api_erisimi import gizli_sakla

    tumu = {"ik.izin_talebi", "ik.izin_karari"}
    assert tumu <= set(webhook.OLAY_SOZLUGU) and tumu <= set(otomasyon_kural.OLAY_SOZLUGU)
    assert tumu <= {o["anahtar"] for o in webhook.olay_katalogu(False)}
    assert otomasyon_kural.olay_nesneleri("ik.izin_talebi", False) == ("izin", "hesap", "kisi", "olay")
    assert "ik_izinler" in webhook.IZLENEN_TABLOLAR
    assert otomasyon_kural.kisi_sec("ik.izin_karari", {"izin": otomasyon_kural.ORNEK["izin"]})["email"] == "selin@ornek.com"
    monkeypatch.setattr(webhook, "ANLIK_TESLIMAT", False)
    uc = WebhookUcNoktalari(sahip_tur="ajans", hesap_email=None, url="https://kanca.ornek.com/ik", olaylar=json.dumps(sorted(tumu)),
                            aktif=True, gizli_anahtar=gizli_sakla("whsec_test"), ardisik_hata=0, tum_musteriler=False)
    db_oturumu.add(uc)
    await db_oturumu.commit()
    webhook.onbellegi_temizle()
    try:
        p = await _personel(istemci, yonetici_basligi, ad="Gizli Personel", eposta="gizli.personel@ornek.com")
        jeton = _jeton(await _portal_adresi(istemci, yonetici_basligi, p["id"]))
        y = await istemci.post(f"{P}/{jeton}/izin", json={"tur": "mazeret", "baslangic": "2026-10-14", "aciklama": "Gizli neden"},
                               headers=_z())
        iid = y.json()["izin"]["id"]
        await istemci.post(f"{Y}/izinler/{iid}/karar", json={"karar": "ret", "bildir": False}, headers=yonetici_basligi)
        await istemci.post(f"{Y}/izinler/{iid}/geri-al", json={}, headers=yonetici_basligi)  # olay değil
        await _izin(istemci, yonetici_basligi, p["id"], tur="yillik", baslangic="2026-12-01", bitis="2026-12-01", onayli=True)
        teslimat = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id)
                                             .order_by(WebhookTeslimatlari.id))).scalars().all()
        assert [x.tur for x in teslimat] == ["ik.izin_talebi", "ik.izin_karari", "ik.izin_karari"]
        for x in teslimat:
            assert "gizli" not in x.govde.lower() and json.loads(x.govde)["veri"]["personel_id"] == p["id"]
        assert json.loads(teslimat[1].govde)["veri"]["durum"] == "reddedildi"
        from core.database import db_manager
        from services import otomasyon

        async with db_manager.async_session_maker() as db:
            b = await otomasyon.baglam_kur(db, "ik.izin_talebi", json.loads(teslimat[0].govde)["veri"], None, True)
        assert b["izin"]["personel_eposta"] == "gizli.personel@ornek.com" and b["izin"]["tur"] == "mazeret"
    finally:
        uc.aktif = False
        await db_oturumu.commit()
        webhook.onbellegi_temizle()


async def test_haftalik_ozet_bekleyen_izin_yalniz_ajans(istemci, yonetici_basligi, db_oturumu):
    from services import haftalik_ozet as ho

    ad = f"Özet Personel {uuid.uuid4().hex[:5]}"
    p = await _personel(istemci, yonetici_basligi, ad=ad)
    await _izin(istemci, yonetici_basligi, p["id"])
    m = _e("ozet")
    await _modul(istemci, yonetici_basligi, m)
    pm = await _personel(istemci, _b(m), M, ad=f"Müşteri {ad}")
    await _izin(istemci, _b(m), pm["id"], M)
    o = await ho.ozet_hazirla(db_oturumu)
    bolum = [b for b in o["bolumler"] if b["anahtar"] == "ik_izin"][0]
    assert bolum["sekme"] == "ik" and bolum["sayi"] >= 1
    tumu = (await istemci.get(f"{Y}/izinler", params={"durum": "beklemede"}, headers=yonetici_basligi)).json()["items"]
    assert bolum["sayi"] == len(tumu)
    assert not any(s["ad"] == f"Müşteri {ad}" for s in bolum["ornekler"])
    gelen = [b for b in o["bolumler"] if b["anahtar"] == "gelen_kutusu"]
    assert not gelen or "izin_talebi" not in gelen[0]["ek"].get("kaynaklar", {})
