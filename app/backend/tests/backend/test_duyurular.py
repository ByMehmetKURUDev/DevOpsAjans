"""Faz 2B — duyurular (hedefleme, süre, okundu/kapat) ve öneri kutusu (tekil oy,
sahibin gizliliği, durum bildirimi, Yol haritası "Topluluktan" ucu); bildirim
kataloğu ve ek çeviri paketleri.
"""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

D = "/api/v1/duyurular"
DK = "/api/v1/duyurularim"
O = "/api/v1/oneri-kutusu"
OY = "/api/v1/oneri-yonetimi"
TOP = "/api/v1/topluluk-onerileri"
MODUL = "/api/v1/moduller"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
EK = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek"


def _eposta(on: str = "d") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


async def _duyuru(istemci, basliklar, beklenen=200, **govde):
    govde.setdefault("baslik", f"Duyuru {uuid.uuid4().hex[:4]}")
    y = await istemci.post(D, json=govde, headers=basliklar)
    assert y.status_code == beklenen, y.text
    return y.json()


async def _benim(istemci, basliklar):
    y = await istemci.get(DK, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _bildirimler(db, olay, eposta=None, ref_id=None):
    from models.notifications import Notifications

    sorgu = select(Notifications).where(Notifications.event_type == olay, Notifications.channel == "inapp")
    if eposta:
        sorgu = sorgu.where(Notifications.recipient_email == eposta)
    if ref_id is not None:
        sorgu = sorgu.where(Notifications.ref_id == ref_id)
    return list((await db.execute(sorgu)).scalars().all())


# ---------------------------------------------------------------------------
# Duyurular
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("metot,yol", [("GET", D), ("POST", D), ("PATCH", f"{D}/1"), ("DELETE", f"{D}/1"),
                                       ("GET", OY), ("PATCH", f"{OY}/1"), ("PUT", f"{OY}/ayar")])
async def test_yonetici_uclari_yetki(istemci, musteri_basligi, metot, yol):
    govde = {} if metot in ("POST", "PATCH", "PUT") else None
    assert (await istemci.request(metot, yol, json=govde)).status_code == 401
    assert (await istemci.request(metot, yol, json=govde, headers=musteri_basligi())).status_code == 403


async def test_hedefleme_sure_ve_yayin(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.staff import Staff

    a, b, ekipten = _eposta("a"), _eposta("b"), _eposta("ekip")
    db_oturumu.add(Staff(ad="Ekip", email=ekipten, rol="calisan", aktif=True))
    await db_oturumu.commit()

    herkes = await _duyuru(istemci, yonetici_basligi, baslik="Bakım penceresi", metin="Cumartesi 02:00", onem="onemli")
    secili = await _duyuru(istemci, yonetici_basligi, baslik="Size özel", hedef="secili", hedef_epostalar=[a.upper(), a])
    ekip = await _duyuru(istemci, yonetici_basligi, baslik="Ekip toplantısı", hedef="ekip")
    gecmis = await _duyuru(istemci, yonetici_basligi, baslik="Eski", bitis="2020-01-01")
    taslak = await _duyuru(istemci, yonetici_basligi, baslik="Taslak", yayinda=False)
    assert secili["hedef_epostalar"] == [a] and gecmis["etkin"] is False and taslak["etkin"] is False

    await _duyuru(istemci, yonetici_basligi, 400, hedef="secili", hedef_epostalar=[])
    await _duyuru(istemci, yonetici_basligi, 400, onem="acil")
    await _duyuru(istemci, yonetici_basligi, 400, hedef="herkes")
    await _duyuru(istemci, yonetici_basligi, 400, bitis="yarın")
    await _duyuru(istemci, yonetici_basligi, 400, baslik=" ")

    basliklar = lambda liste: {d["baslik"] for d in liste["duyurular"]}  # noqa: E731
    assert {"Bakım penceresi", "Size özel"} <= basliklar(await _benim(istemci, musteri_basligi(a)))
    gb = basliklar(await _benim(istemci, musteri_basligi(b)))
    assert "Bakım penceresi" in gb and "Size özel" not in gb and "Ekip toplantısı" not in gb
    ge = basliklar(await _benim(istemci, musteri_basligi(ekipten)))
    assert "Ekip toplantısı" in ge and "Bakım penceresi" in ge
    gy = basliklar(await _benim(istemci, yonetici_basligi))
    assert "Ekip toplantısı" in gy and "Bakım penceresi" not in gy
    for liste in (await _benim(istemci, musteri_basligi(a)), await _benim(istemci, yonetici_basligi)):
        assert not {"Eski", "Taslak"} & basliklar(liste)
    # Hedef dışı duyuru okunamaz/kapatılamaz (404)
    assert (await istemci.post(f"{DK}/{secili['id']}/okundu", headers=musteri_basligi(b))).status_code == 404
    assert (await istemci.post(f"{DK}/{ekip['id']}/kapat", headers=musteri_basligi(a))).status_code == 404

    # Yayından kaldırınca kaybolur
    y = await istemci.patch(f"{D}/{herkes['id']}", json={"yayinda": False}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["etkin"] is False
    assert "Bakım penceresi" not in basliklar(await _benim(istemci, musteri_basligi(b)))
    assert (await istemci.delete(f"{D}/{secili['id']}", headers=yonetici_basligi)).status_code == 200
    assert "Size özel" not in basliklar(await _benim(istemci, musteri_basligi(a)))


async def test_okundu_ve_kapat(istemci, yonetici_basligi, musteri_basligi):
    a = _eposta("okur")
    d = await _duyuru(istemci, yonetici_basligi, hedef="secili", hedef_epostalar=[a], onem="kritik")
    ilk = await _benim(istemci, musteri_basligi(a))
    kayit = next(x for x in ilk["duyurular"] if x["id"] == d["id"])
    assert kayit == {**kayit, "okundu": False, "kapatildi": False} and ilk["okunmamis"] >= 1
    y = await istemci.post(f"{DK}/{d['id']}/okundu", headers=musteri_basligi(a))
    assert y.status_code == 200 and y.json()["okundu"] is True and y.json()["kapatildi"] is False
    assert (await istemci.post(f"{DK}/{d['id']}/okundu", headers=musteri_basligi(a))).status_code == 200  # tekrar zararsız
    y = await istemci.post(f"{DK}/{d['id']}/kapat", headers=musteri_basligi(a))
    assert y.json()["kapatildi"] is True
    sonra = next(x for x in (await _benim(istemci, musteri_basligi(a)))["duyurular"] if x["id"] == d["id"])
    assert sonra["kapatildi"] is True and sonra["okundu"] is True  # listede kalır, şeritten kalkar
    yl = next(x for x in (await istemci.get(D, headers=yonetici_basligi)).json() if x["id"] == d["id"])
    assert yl["okunma_sayisi"] == 1 and yl["kapatma_sayisi"] == 1


async def test_duyuru_bildirimi_istege_bagli(istemci, yonetici_basligi, db_oturumu):
    a = _eposta("bil")
    d1 = await _duyuru(istemci, yonetici_basligi, hedef="secili", hedef_epostalar=[a])
    assert not await _bildirimler(db_oturumu, "duyuru", a, d1["id"])
    d2 = await _duyuru(istemci, yonetici_basligi, hedef="secili", hedef_epostalar=[a], bildirim_gonder=True)
    assert len(await _bildirimler(db_oturumu, "duyuru", a, d2["id"])) == 1


async def test_duyurular_modulu_kapaliyken_403(istemci, yonetici_basligi, musteri_basligi):
    a = _eposta("kapali")
    y = await istemci.put(f"{MODUL}/musteri/{a}/duyurular", json={"acik": False}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    y = await istemci.get(DK, headers=musteri_basligi(a))
    assert y.status_code == 403 and y.json()["detail"]["modul"] == "duyurular"
    assert (await istemci.get(DK)).status_code == 401


# ---------------------------------------------------------------------------
# Öneri kutusu
# ---------------------------------------------------------------------------


async def test_oneri_oylama_tekil_ve_sahip_gizli(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    sahip, oycu, oycu2 = _eposta("sahip"), _eposta("oycu"), _eposta("oycu2")
    y = await istemci.post(O, json={"baslik": "Karanlık tema", "aciklama": "Panelde koyu tema olsun"}, headers=musteri_basligi(sahip))
    assert y.status_code == 200, y.text
    oneri = y.json()
    assert oneri["benim"] is True and oneri["oy_sayisi"] == 0 and sahip not in json.dumps(oneri)
    assert (await istemci.post(O, json={"baslik": "  "}, headers=musteri_basligi(sahip))).status_code == 400

    # Sahip kendi önerisine oy veremez
    y = await istemci.post(f"{O}/{oneri['id']}/oy", headers=musteri_basligi(sahip))
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kendi_onerin"
    # Tekil oy: iki kez vermek sayıyı değiştirmez
    for _ in range(2):
        y = await istemci.post(f"{O}/{oneri['id']}/oy", headers=musteri_basligi(oycu))
        assert y.status_code == 200 and y.json()["oy_sayisi"] == 1 and y.json()["oyladim"] is True
    y = await istemci.post(f"{O}/{oneri['id']}/oy", headers=musteri_basligi(oycu2))
    assert y.json()["oy_sayisi"] == 2

    # Başka müşterinin listesi: sahibin e-postası ve oy verenler hiçbir yerde yok
    liste = (await istemci.get(O, headers=musteri_basligi(oycu2))).json()
    kayit = next(x for x in liste if x["id"] == oneri["id"])
    assert kayit["benim"] is False and kayit["oyladim"] is True and kayit["oy_sayisi"] == 2
    metin = json.dumps(liste)
    assert sahip not in metin and oycu not in metin and "sahip_eposta" not in metin
    # Yönetici sahibi görür
    yl = (await istemci.get(OY, headers=yonetici_basligi)).json()
    assert next(x for x in yl["oneriler"] if x["id"] == oneri["id"])["sahip_eposta"] == sahip

    # Oy geri alma
    y = await istemci.delete(f"{O}/{oneri['id']}/oy", headers=musteri_basligi(oycu))
    assert y.json()["oy_sayisi"] == 1 and y.json()["oyladim"] is False

    # Durum → sahibe bildirim; yapıldı/reddedildi oylamaya kapalı
    y = await istemci.patch(f"{OY}/{oneri['id']}", json={"durum": "planlandi", "yonetici_notu": "Ekim sonu"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "planlandi"
    assert len(await _bildirimler(db_oturumu, "oneri_durumu", sahip, oneri["id"])) == 1
    assert (await istemci.patch(f"{OY}/{oneri['id']}", json={"durum": "belki"}, headers=yonetici_basligi)).status_code == 400
    kapali = (await istemci.post(O, json={"baslik": "Eski fikir"}, headers=musteri_basligi(sahip))).json()
    await istemci.patch(f"{OY}/{kapali['id']}", json={"durum": "reddedildi"}, headers=yonetici_basligi)
    assert (await istemci.post(f"{O}/{kapali['id']}/oy", headers=musteri_basligi(oycu))).status_code == 409
    assert (await istemci.post(f"{O}/999999/oy", headers=musteri_basligi(oycu))).status_code == 404


async def test_oneri_gunluk_sinir(istemci, musteri_basligi):
    m = _eposta("sinir")
    for i in range(5):
        assert (await istemci.post(O, json={"baslik": f"Fikir {i}"}, headers=musteri_basligi(m))).status_code == 200
    y = await istemci.post(O, json={"baslik": "Bir tane daha"}, headers=musteri_basligi(m))
    assert y.status_code == 429


async def test_topluluk_ucu_ayarla_ve_yalniz_planlananlar(istemci, yonetici_basligi, musteri_basligi):
    sahip, oycu = _eposta("t1"), _eposta("t2")
    planli = (await istemci.post(O, json={"baslik": f"Planlı {uuid.uuid4().hex[:4]}"}, headers=musteri_basligi(sahip))).json()
    yeni = (await istemci.post(O, json={"baslik": f"Yeni {uuid.uuid4().hex[:4]}"}, headers=musteri_basligi(sahip))).json()
    await istemci.post(f"{O}/{planli['id']}/oy", headers=musteri_basligi(oycu))
    await istemci.patch(f"{OY}/{planli['id']}", json={"durum": "planlandi"}, headers=yonetici_basligi)

    assert (await istemci.put(f"{OY}/ayar", json={"topluluk_yol_haritasi": False}, headers=yonetici_basligi)).status_code == 200
    y = await istemci.get(TOP)
    assert y.status_code == 200 and y.json() == {"acik": False, "oneriler": []}
    assert (await istemci.put(f"{OY}/ayar", json={"topluluk_yol_haritasi": True}, headers=yonetici_basligi)).json()["topluluk_yol_haritasi"] is True
    y = await istemci.get(TOP)
    govde = y.json()
    assert govde["acik"] is True
    assert {"baslik": planli["baslik"], "oy_sayisi": 1} in govde["oneriler"]
    assert all(set(x) == {"baslik", "oy_sayisi"} for x in govde["oneriler"])
    assert yeni["baslik"] not in json.dumps(govde) and sahip not in json.dumps(govde)
    assert (await istemci.get(OY, headers=yonetici_basligi)).json()["topluluk_yol_haritasi"] is True
    await istemci.put(f"{OY}/ayar", json={"topluluk_yol_haritasi": False}, headers=yonetici_basligi)


async def test_oneri_kutusu_modulu_kapaliyken_403(istemci, yonetici_basligi, musteri_basligi):
    m = _eposta("okk")
    assert (await istemci.put(f"{MODUL}/musteri/{m}/oneri_kutusu", json={"acik": False}, headers=yonetici_basligi)).status_code == 200
    y = await istemci.get(O, headers=musteri_basligi(m))
    assert y.status_code == 403 and y.json()["detail"]["modul"] == "oneri_kutusu"


# ---------------------------------------------------------------------------
# Katalog ve çeviriler
# ---------------------------------------------------------------------------

YENI_OLAYLAR = ("gorev_guncellendi", "revizyon_asildi", "geri_bildirim_yeni", "geri_bildirim_durumu", "duyuru", "oneri_durumu")


def test_bildirim_katalogu_ve_etiketler_7_dilde():
    from services.bildirim_tercih import OLAYLAR

    tr = json.loads((EK / "bildirim" / "tr.json").read_text(encoding="utf-8"))["bildirim"]["olay"]
    for olay in YENI_OLAYLAR:
        assert OLAYLAR[olay]["tetikleniyor"] is True, olay
        for dil in DILLER:
            ek = json.loads((EK / "bildirim" / f"{dil}.json").read_text(encoding="utf-8"))["bildirim"]["olay"]
            assert ek.get(olay), (dil, olay)
            if dil != "tr":
                assert ek[olay] != tr[olay], (dil, olay)


def _duz(d, on=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _duz(v, f"{on}{k}.")
        else:
            yield f"{on}{k}", v


@pytest.mark.parametrize("paket", ["gorevler", "geriBildirim", "duyurular"])
def test_ek_paketler_yedi_dilde_ayni_anahtarlar_ve_gercek_ceviri(paket):
    paketler = {
        dil: dict(_duz(json.loads((EK / paket / f"{dil}.json").read_text(encoding="utf-8"))[paket])) for dil in DILLER
    }
    anahtarlar = set(paketler["tr"])
    assert len(anahtarlar) > 10
    for dil, p in paketler.items():
        assert set(p) == anahtarlar, (dil, set(p) ^ anahtarlar)
        assert all(isinstance(v, str) and v.strip() for v in p.values()), dil
    for dil in ("en", "de", "ru", "zh", "hi", "ar"):
        ayni = [k for k in anahtarlar if paketler[dil][k] == paketler["tr"][k] and len(paketler["tr"][k]) > 12]
        assert not ayni, (dil, ayni[:5])


def test_arayuz_durum_anahtarlari_sunucuyla_ayni():
    from models.duyurular import DUYURU_HEDEFLERI, DUYURU_ONEMLERI, ONERI_DURUMLARI
    from models.geri_bildirim import GERI_BILDIRIM_DURUMLARI, GERI_BILDIRIM_TURLERI
    from models.proje_gorevleri import GOREV_DURUMLARI, ONCELIKLER

    tr_g = json.loads((EK / "gorevler" / "tr.json").read_text(encoding="utf-8"))["gorevler"]
    assert set(tr_g["durum"]) == set(GOREV_DURUMLARI) and set(tr_g["oncelik"]) == set(ONCELIKLER)
    tr_f = json.loads((EK / "geriBildirim" / "tr.json").read_text(encoding="utf-8"))["geriBildirim"]
    assert set(tr_f["durum"]) == set(GERI_BILDIRIM_DURUMLARI) and set(tr_f["tur"]) == set(GERI_BILDIRIM_TURLERI)
    tr_d = json.loads((EK / "duyurular" / "tr.json").read_text(encoding="utf-8"))["duyurular"]
    assert set(tr_d["onem"]) == set(DUYURU_ONEMLERI) and set(tr_d["hedef"]) == set(DUYURU_HEDEFLERI)
    assert set(tr_d["oneriDurum"]) == set(ONERI_DURUMLARI)
