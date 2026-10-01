"""Faz 2G — müşteri ↔ ajans mesajlaşma.

Kapsam: hesap yalıtımı (başka hesap 404, `X-MK-Hesap` ile izinli üye 200,
`fatura` rolü 403), yönetici hepsini görür, `sonra=` yoklaması, okunmamış
sayıları ve özet, okundu ilerlemesinin geri gitmemesi, 15 dk düzenleme/silme,
başkasının mesajı, hız sınırı, metin sınırı, ekler (başka hesabın dosyası
olamaz), toplu bildirim (2 dk, bir kez, okunduysa hiç, 30 dk toplama, ekip
genişletmesi), Genel konuşma, arşiv, çöp kutusu, hazır cevap / talep / görev,
modül ve çeviri tutarlılığı.
"""

import io
import json
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update

from conftest import jeton_uret

M = "/api/v1/mesajlarim"
Y = "/api/v1/mesajlar"
BASLIK = "X-MK-Hesap"
KOK = Path(__file__).resolve().parents[3]
EK = KOK / "frontend" / "src" / "i18n" / "ek"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")


def _e(on: str) -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@mesaj.dev"


def _b(eposta: str, hesap: str | None = None, rol: str = "user") -> dict:
    h = {"Authorization": f"Bearer {jeton_uret(eposta, rol)}"}
    if hesap:
        h[BASLIK] = hesap
    return h


def _kod(y) -> str:
    try:
        d = y.json().get("detail")
    except Exception:  # noqa: BLE001
        return ""
    return d.get("kod", "") if isinstance(d, dict) else ""


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    from routers import mesajlar as r
    from services import hesap_ekibi
    from services import mesajlar as s

    monkeypatch.setattr(s, "ISTEKLE_TETIKLE", False)
    r._hiz.temizle()
    r._ek_hizi.temizle()
    hesap_ekibi.onbellegi_temizle()
    yield
    hesap_ekibi.onbellegi_temizle()


async def _genel(istemci, eposta, hesap=None) -> dict:
    y = await istemci.get(f"{M}/konusmalar", headers=_b(eposta, hesap))
    assert y.status_code == 200, y.text
    return next(k for k in y.json()["konusmalar"] if k["genel"])


async def _gonder(istemci, kid, metin, basliklar, yonetici=False, **ek):
    yol = f"{Y if yonetici else M}/konusmalar/{kid}/mesajlar"
    return await istemci.post(yol, json={"metin": metin, **ek}, headers=basliklar)


async def _uye_ekle(db, hesap, uye, rol, izinler=None):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as s

    db.add(
        HesapUyeleri(
            hesap_email=hesap,
            uye_email=uye,
            rol=rol,
            izinler=json.dumps(list(izinler if izinler is not None else s.ROL_VARSAYILAN[rol])),
            durum="aktif",
            olusturma=s.simdi(),
        )
    )
    await db.commit()
    s.onbellegi_temizle()


async def _bildirimler(db, kid):
    from models.notifications import Notifications

    db.expire_all()
    return list(
        (
            await db.execute(
                select(Notifications).where(
                    Notifications.ref_type == "konusma", Notifications.ref_id == kid, Notifications.channel == "inapp"
                )
            )
        ).scalars().all()
    )


# ---------------------------------------------------------------------------
# Genel konuşma, yalıtım, yetki
# ---------------------------------------------------------------------------
async def test_genel_konusma_kendiliginden_acilir_ve_tek_kalir(istemci, db_oturumu):
    from models.mesajlar import Konusmalar

    a = _e("a")
    g1 = await _genel(istemci, a)
    g2 = await _genel(istemci, a)
    assert g1["id"] == g2["id"] and g1["konu"] == "Genel" and g1["durum"] == "acik" and g1["okunmamis"] == 0
    sayi = (await db_oturumu.execute(select(Konusmalar).where(Konusmalar.hesap_email == a))).scalars().all()
    assert len(sayi) == 1
    # Konusuz yeni konuşma isteği de Genel'e düşer (ikinci Genel açılmaz).
    y = await istemci.post(f"{M}/konusmalar", json={"konu": "  "}, headers=_b(a))
    assert y.status_code == 200 and y.json()["id"] == g1["id"]
    y = await istemci.post(f"{M}/konusmalar", json={"konu": "Logo revizyonu"}, headers=_b(a))
    assert y.status_code == 200 and y.json()["genel"] is False
    liste = (await istemci.get(f"{M}/konusmalar", headers=_b(a))).json()["konusmalar"]
    assert {k["konu"] for k in liste} == {"Genel", "Logo revizyonu"}


async def test_oturumsuz_401_ve_yonetici_uclari_musteriye_kapali(istemci):
    assert (await istemci.get(f"{M}/konusmalar")).status_code == 401
    assert (await istemci.get(f"{M}/ozet")).status_code == 401
    assert (await istemci.get(f"{Y}/konusmalar")).status_code == 401
    a = _e("a")
    assert (await istemci.get(f"{Y}/konusmalar", headers=_b(a))).status_code == 403
    assert (await istemci.get(f"{Y}/ozet", headers=_b(a))).status_code == 403


async def test_musteri_yalniz_kendi_hesabini_gorur(istemci):
    a, b = _e("a"), _e("b")
    ga = await _genel(istemci, a)
    assert (await _gonder(istemci, ga["id"], "A'nın gizli mesajı", _b(a))).status_code == 200
    gb = await _genel(istemci, b)
    assert gb["id"] != ga["id"]
    for metot, yol, govde in (
        ("GET", f"{M}/konusmalar/{ga['id']}/mesajlar", None),
        ("POST", f"{M}/konusmalar/{ga['id']}/mesajlar", {"metin": "sızma"}),
        ("POST", f"{M}/konusmalar/{ga['id']}/okundu", {"mesaj_id": 1}),
    ):
        y = await istemci.request(metot, yol, json=govde, headers=_b(b))
        assert y.status_code == 404 and _kod(y) == "konusma_yok", (yol, y.text)
    liste = (await istemci.get(f"{M}/konusmalar", headers=_b(b))).json()["konusmalar"]
    assert [k["id"] for k in liste] == [gb["id"]]
    assert "gizli" not in (await istemci.get(f"{M}/konusmalar", headers=_b(b))).text


async def test_ekip_uyesi_izinli_200_fatura_rolu_403_yabanci_403(istemci, db_oturumu):
    sahip, uye, fatura, yabanci = _e("sahip"), _e("uye"), _e("fatura"), _e("yabanci")
    await _uye_ekle(db_oturumu, sahip, uye, "uye")
    await _uye_ekle(db_oturumu, sahip, fatura, "fatura")
    g = await _genel(istemci, sahip)
    y = await istemci.get(f"{M}/konusmalar", headers=_b(uye, sahip))
    assert y.status_code == 200 and [k["id"] for k in y.json()["konusmalar"]] == [g["id"]]
    y = await _gonder(istemci, g["id"], "Ekipten merhaba", _b(uye, sahip))
    assert y.status_code == 200 and y.json()["benim"] is True and y.json()["yazan_email"] == uye
    for yol in (f"{M}/konusmalar", f"{M}/ozet", f"{M}/konusmalar/{g['id']}/mesajlar"):
        y = await istemci.get(yol, headers=_b(fatura, sahip))
        assert y.status_code == 403 and _kod(y) == "hesap_izni_yok", (yol, y.text)
        y = await istemci.get(yol, headers=_b(yabanci, sahip))
        assert y.status_code == 403 and _kod(y) == "hesap_uyesi_degil", (yol, y.text)
    # Sahibin görünümünde üyenin mesajı: yazan kişi üye, "benim" değil.
    m = (await istemci.get(f"{M}/konusmalar/{g['id']}/mesajlar", headers=_b(sahip))).json()["mesajlar"][-1]
    assert m["yazan_email"] == uye and m["benim"] is False


async def test_eski_varsayilan_izinli_uye_mesajlar_iznini_alir_ozel_liste_almaz(db_oturumu):
    from services.hesap_ekibi import ESKI_VARSAYILANLAR, izinleri_coz

    eski_uye = sorted(ESKI_VARSAYILANLAR["uye"][0])
    assert "mesajlar" in izinleri_coz(json.dumps(eski_uye), "uye")
    assert "mesajlar" in izinleri_coz(json.dumps(sorted(ESKI_VARSAYILANLAR["yonetici"][0])), "yonetici")
    assert "mesajlar" not in izinleri_coz(json.dumps(["projeler", "destek"]), "uye")
    assert "mesajlar" not in izinleri_coz(json.dumps(["faturalar", "krediler", "abonelikler"]), "fatura")


async def test_yonetici_hepsini_gorur_arama_ve_okunmamis_suzgeci(istemci, yonetici_basligi):
    a, b = _e("a"), _e("b")
    ga, gb = await _genel(istemci, a), await _genel(istemci, b)
    iz = uuid.uuid4().hex[:10]
    await _gonder(istemci, ga["id"], f"Fatura sorusu {iz}", _b(a))
    y = await istemci.get(f"{Y}/konusmalar", headers=yonetici_basligi)
    idler = {k["id"]: k for k in y.json()["konusmalar"]}
    assert ga["id"] in idler and gb["id"] in idler and idler[ga["id"]]["okunmamis"] == 1
    assert idler[ga["id"]]["hesap_email"] == a and "hesap_adi" in idler[ga["id"]]
    # Arama: mesaj metninde ve hesap e-postasında.
    y = await istemci.get(f"{Y}/konusmalar", params={"q": iz}, headers=yonetici_basligi)
    assert [k["id"] for k in y.json()["konusmalar"]] == [ga["id"]]
    y = await istemci.get(f"{Y}/konusmalar", params={"q": b}, headers=yonetici_basligi)
    assert [k["id"] for k in y.json()["konusmalar"]] == [gb["id"]]
    # Okunmamış süzgeci: yalnız okunmamışı olanlar.
    y = await istemci.get(f"{Y}/konusmalar", params={"okunmamis": "true"}, headers=yonetici_basligi)
    secili = {k["id"] for k in y.json()["konusmalar"]}
    assert ga["id"] in secili and gb["id"] not in secili
    # Yönetici okuyunca süzgeçten düşer.
    son = (await istemci.get(f"{Y}/konusmalar/{ga['id']}/mesajlar", headers=yonetici_basligi)).json()["mesajlar"][-1]
    await istemci.post(f"{Y}/konusmalar/{ga['id']}/okundu", json={"mesaj_id": son["id"]}, headers=yonetici_basligi)
    y = await istemci.get(f"{Y}/konusmalar", params={"okunmamis": "true"}, headers=yonetici_basligi)
    assert ga["id"] not in {k["id"] for k in y.json()["konusmalar"]}


# ---------------------------------------------------------------------------
# Yoklama, okunmamış, okundu
# ---------------------------------------------------------------------------
async def test_sonra_yoklamasi_yalniz_yenileri_dondurur(istemci, yonetici_basligi):
    a = _e("a")
    g = await _genel(istemci, a)
    idler = [(await _gonder(istemci, g["id"], f"Mesaj {i}", _b(a))).json()["id"] for i in range(3)]
    y = await istemci.get(f"{M}/konusmalar/{g['id']}/mesajlar", params={"sonra": idler[0]}, headers=_b(a))
    assert [m["id"] for m in y.json()["mesajlar"]] == idler[1:]
    y = await istemci.get(f"{M}/konusmalar/{g['id']}/mesajlar", params={"sonra": idler[-1]}, headers=_b(a))
    govde = y.json()
    assert govde["mesajlar"] == [] and govde["konusma"]["son_mesaj_id"] == idler[-1]
    assert len(y.content) < 400  # değişiklik yoksa küçük yanıt
    # Yönetici yanıtı müşterinin yoklamasında görünür.
    ym = (await _gonder(istemci, g["id"], "Ajans yanıtı", yonetici_basligi, yonetici=True)).json()
    y = await istemci.get(f"{M}/konusmalar/{g['id']}/mesajlar", params={"sonra": idler[-1]}, headers=_b(a))
    m = y.json()["mesajlar"]
    assert [x["id"] for x in m] == [ym["id"]] and m[0]["yazan_rol"] == "admin" and m[0]["benim"] is False
    # Sayfalama: once= ile eskiler, daha_eski bayrağı.
    y = await istemci.get(f"{M}/konusmalar/{g['id']}/mesajlar", params={"adet": 2}, headers=_b(a))
    assert [x["id"] for x in y.json()["mesajlar"]] == [idler[2], ym["id"]] and y.json()["daha_eski"] is True
    y = await istemci.get(f"{M}/konusmalar/{g['id']}/mesajlar", params={"once": idler[2], "adet": 5}, headers=_b(a))
    assert [x["id"] for x in y.json()["mesajlar"]] == idler[:2] and y.json()["daha_eski"] is False


async def test_okunmamis_sayilari_ozet_ve_okundu_isareti(istemci, yonetici_basligi):
    a = _e("a")
    g = await _genel(istemci, a)
    y1 = (await _gonder(istemci, g["id"], "Bir", yonetici_basligi, yonetici=True)).json()
    y2 = (await _gonder(istemci, g["id"], "İki", yonetici_basligi, yonetici=True)).json()
    assert (await _genel(istemci, a))["okunmamis"] == 2
    oz = (await istemci.get(f"{M}/ozet", headers=_b(a))).json()
    assert oz["okunmamis"] == 2 and oz["okunmamis_konusma"] == 1 and oz["son_mesaj_id"] == y2["id"]
    # Kendi mesajı okunmamış sayılmaz; yöneticinin karşı-okundu işareti henüz 0.
    m = (await _gonder(istemci, g["id"], "Müşteri yanıtı", _b(a))).json()
    liste = (await istemci.get(f"{Y}/konusmalar/{g['id']}/mesajlar", headers=yonetici_basligi)).json()
    assert liste["karsi_okunan"] == m["id"]  # müşteri yazınca kendi tarafı o noktaya kadar okumuş
    assert (await _genel(istemci, a))["okunmamis"] == 0
    # Müşteri yazmadan okursa da sıfırlanır.
    await _gonder(istemci, g["id"], "Üç", yonetici_basligi, yonetici=True)
    assert (await istemci.get(f"{M}/ozet", headers=_b(a))).json()["okunmamis"] == 1
    son = (await istemci.get(f"{M}/konusmalar/{g['id']}/mesajlar", headers=_b(a))).json()["mesajlar"][-1]
    y = await istemci.post(f"{M}/konusmalar/{g['id']}/okundu", json={"mesaj_id": son["id"]}, headers=_b(a))
    assert y.status_code == 200 and y.json()["okudugum"] == son["id"]
    assert (await istemci.get(f"{M}/ozet", headers=_b(a))).json()["okunmamis"] == 0
    assert y1["id"] < y2["id"]


async def test_okundu_ilerlemesi_geri_gitmez_ve_son_mesaji_gecmez(istemci, yonetici_basligi):
    a = _e("a")
    g = await _genel(istemci, a)
    idler = [(await _gonder(istemci, g["id"], f"Y{i}", yonetici_basligi, yonetici=True)).json()["id"] for i in range(3)]
    yol = f"{M}/konusmalar/{g['id']}/okundu"
    assert (await istemci.post(yol, json={"mesaj_id": idler[2]}, headers=_b(a))).json()["okudugum"] == idler[2]
    assert (await istemci.post(yol, json={"mesaj_id": idler[0]}, headers=_b(a))).json()["okudugum"] == idler[2]
    assert (await istemci.post(yol, json={"mesaj_id": 10**9}, headers=_b(a))).json()["okudugum"] == idler[2]
    assert (await istemci.post(yol, json={"mesaj_id": -5}, headers=_b(a))).json()["okudugum"] == idler[2]
    # Yöneticinin görünümünde "okundu" işareti.
    assert (await istemci.get(f"{Y}/konusmalar/{g['id']}/mesajlar", headers=yonetici_basligi)).json()["karsi_okunan"] == idler[2]


# ---------------------------------------------------------------------------
# Düzenleme, silme, sınırlar
# ---------------------------------------------------------------------------
async def test_15_dakika_duzenleme_ve_silme_siniri(istemci, db_oturumu, yonetici_basligi):
    from models.mesajlar import KonusmaMesajlari

    a = _e("a")
    g = await _genel(istemci, a)
    m = (await _gonder(istemci, g["id"], "İlk hali", _b(a))).json()
    assert m["duzenleme_bitis"]
    y = await istemci.put(f"{M}/mesajlar/{m['id']}", json={"metin": "Düzeltilmiş"}, headers=_b(a))
    assert y.status_code == 200 and y.json()["metin"] == "Düzeltilmiş" and y.json()["duzenlendi_at"]
    # Düzenleme yoklamada "değişiklik" sayacıyla duyuluyor.
    assert (await istemci.get(f"{M}/konusmalar/{g['id']}/mesajlar", params={"sonra": m["id"]}, headers=_b(a))).json()["konusma"]["degisiklik"] == 1
    # 16 dakika önce yazılmış gibi.
    from services.mesajlar import simdi

    await db_oturumu.execute(
        update(KonusmaMesajlari).where(KonusmaMesajlari.id == m["id"]).values(created_at=simdi() - timedelta(minutes=16))
    )
    await db_oturumu.commit()
    y = await istemci.put(f"{M}/mesajlar/{m['id']}", json={"metin": "Geç"}, headers=_b(a))
    assert y.status_code == 409 and _kod(y) == "duzenleme_suresi_doldu"
    y = await istemci.delete(f"{M}/mesajlar/{m['id']}", headers=_b(a))
    assert y.status_code == 409 and _kod(y) == "duzenleme_suresi_doldu"
    # Yeni mesaj 15 dk içinde silinir: "bu mesaj silindi" (içerik boş), son özet bir öncekine döner.
    m2 = (await _gonder(istemci, g["id"], "Yanlışlıkla", _b(a))).json()
    y = await istemci.delete(f"{M}/mesajlar/{m2['id']}", headers=_b(a))
    assert y.status_code == 200 and y.json()["silindi"] is True and y.json()["metin"] == ""
    yliste = (await istemci.get(f"{Y}/konusmalar/{g['id']}/mesajlar", headers=yonetici_basligi)).json()["mesajlar"]
    silinen = next(x for x in yliste if x["id"] == m2["id"])
    assert silinen["silindi"] is True and silinen["metin"] == "" and "Yanlışlıkla" not in json.dumps(yliste)
    genel = (await istemci.get(f"{M}/konusmalar", headers=_b(a))).json()["konusmalar"][0]
    assert genel["son_mesaj_ozet"] == "Düzeltilmiş"
    # Silinmiş mesaj yeniden düzenlenemez.
    y = await istemci.put(f"{M}/mesajlar/{m2['id']}", json={"metin": "x"}, headers=_b(a))
    assert y.status_code == 409 and _kod(y) == "mesaj_silinmis"


async def test_baskasinin_mesajini_duzenleyemez_silemez(istemci, db_oturumu, yonetici_basligi):
    sahip, uye, yabanci = _e("sahip"), _e("uye"), _e("yabanci")
    await _uye_ekle(db_oturumu, sahip, uye, "uye")
    g = await _genel(istemci, sahip)
    ms = (await _gonder(istemci, g["id"], "Sahibin mesajı", _b(sahip))).json()
    ma = (await _gonder(istemci, g["id"], "Ajansın mesajı", yonetici_basligi, yonetici=True)).json()
    # Aynı hesaptaki üye sahibin mesajını düzenleyemez (403); müşteri ajans mesajını da.
    for mid, b in ((ms["id"], _b(uye, sahip)), (ma["id"], _b(sahip))):
        y = await istemci.put(f"{M}/mesajlar/{mid}", json={"metin": "değişti"}, headers=b)
        assert y.status_code == 403 and _kod(y) == "mesaj_sizin_degil", y.text
        y = await istemci.delete(f"{M}/mesajlar/{mid}", headers=b)
        assert y.status_code == 403 and _kod(y) == "mesaj_sizin_degil"
    # Başka hesap: mesaj "yok".
    y = await istemci.put(f"{M}/mesajlar/{ms['id']}", json={"metin": "x"}, headers=_b(yabanci))
    assert y.status_code == 404
    # Yönetici de müşterinin mesajını düzenleyemez (yalnız kendi mesajı).
    y = await istemci.put(f"{Y}/mesajlar/{ms['id']}", json={"metin": "x"}, headers=yonetici_basligi)
    assert y.status_code == 403
    y = await istemci.put(f"{Y}/mesajlar/{ma['id']}", json={"metin": "Ajans düzeltti"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["metin"] == "Ajans düzeltti"


async def test_hiz_siniri_dakikada_30_mesaj(istemci):
    a = _e("a")
    g = await _genel(istemci, a)
    for i in range(30):
        assert (await _gonder(istemci, g["id"], f"m{i}", _b(a))).status_code == 200
    y = await _gonder(istemci, g["id"], "fazla", _b(a))
    assert y.status_code == 429 and _kod(y) == "cok_hizli"
    # Sayaç kişi başına: aynı hesapta başka biri etkilenmez (yönetici).
    b = _e("b")
    gb = await _genel(istemci, b)
    assert (await _gonder(istemci, gb["id"], "başka kişi", _b(b))).status_code == 200


async def test_metin_siniri_bos_mesaj_ve_duz_metin(istemci, yonetici_basligi):
    a = _e("a")
    g = await _genel(istemci, a)
    assert (await _gonder(istemci, g["id"], "x" * 5000, _b(a))).status_code == 200
    y = await _gonder(istemci, g["id"], "x" * 5001, _b(a))
    assert y.status_code == 400 and _kod(y) == "metin_uzun"
    y = await _gonder(istemci, g["id"], "   \n ", _b(a))
    assert y.status_code == 400 and _kod(y) == "bos_mesaj"
    # HTML dokunulmadan METİN olarak saklanır (ön yüz çizmez); denetim/yön karakterleri atılır.
    ham = '<script>alert(1)</script> <b>kalın</b> https://ornek.com\x00‮'
    m = (await _gonder(istemci, g["id"], ham, _b(a))).json()
    assert m["metin"] == "<script>alert(1)</script> <b>kalın</b> https://ornek.com"
    y = (await istemci.get(f"{Y}/konusmalar/{g['id']}/mesajlar", headers=yonetici_basligi)).json()["mesajlar"][-1]
    assert y["metin"] == m["metin"]
    # Konu sınırı
    y = await istemci.post(f"{M}/konusmalar", json={"konu": "k" * 500}, headers=_b(a))
    assert y.status_code == 200 and len(y.json()["konu"]) == 200


# ---------------------------------------------------------------------------
# Ekler
# ---------------------------------------------------------------------------
def _dosya(ad="not.txt", icerik=b"merhaba"):
    return {"dosya": (ad, io.BytesIO(icerik), "text/plain")}


async def test_ek_yukleme_baska_hesabin_dosyasi_olamaz(istemci, db_oturumu, yonetici_basligi):
    from models.dosyalar import Dosyalar

    a, b = _e("a"), _e("b")
    ga, gb = await _genel(istemci, a), await _genel(istemci, b)
    y = await istemci.post(f"{M}/ekler", files=_dosya(), headers=_b(a))
    assert y.status_code == 200, y.text
    ek = y.json()
    assert ek["ad"] == "not.txt" and ek["boyut"] == 7
    d = (await db_oturumu.execute(select(Dosyalar).where(Dosyalar.id == ek["id"]))).scalar_one()
    assert d.client_email == a and d.klasor == "Mesajlar" and d.yukleyen == a
    # Tür sınırları Dosyalar'la aynı: SVG yok.
    y = await istemci.post(f"{M}/ekler", files={"dosya": ("x.svg", io.BytesIO(b"<svg/>"), "image/svg+xml")}, headers=_b(a))
    assert y.status_code == 415 and _kod(y) == "tur_izinsiz"
    # Başka hesap A'nın dosyasını ekleyemez.
    y = await _gonder(istemci, gb["id"], "çalıntı", _b(b), ekler=[ek["id"]])
    assert y.status_code == 400 and _kod(y) == "ek_gecersiz"
    # A, Dosyalar'daki (sohbetten yüklenmemiş) bir dosyayı da ekleyemez.
    gizli = Dosyalar(client_email=a, klasor="Sözleşmeler", ad="gizli.pdf", boyut=1, tur="application/pdf", uzanti="pdf",
                     depolama_anahtari=f"test/{uuid.uuid4().hex}", depo="veritabani", yukleyen="yonetici@test.dev",
                     yukleyen_rol="admin", surum=1, guncel=True)
    db_oturumu.add(gizli)
    await db_oturumu.commit()
    y = await _gonder(istemci, ga["id"], "ekip dosyası", _b(a), ekler=[gizli.id])
    assert y.status_code == 400 and _kod(y) == "ek_gecersiz"
    # Kendi yüklediği ek: metinsiz de gider.
    y = await _gonder(istemci, ga["id"], "", _b(a), ekler=[ek["id"]])
    assert y.status_code == 200 and y.json()["ekler"][0]["id"] == ek["id"]
    mid = y.json()["id"]
    assert (await istemci.post(f"{M}/konusmalar", headers=_b(a), json={})).status_code == 200
    liste = (await istemci.get(f"{M}/konusmalar", headers=_b(a))).json()["konusmalar"]
    assert any(k["son_mesaj_ozet"] == "📎 not.txt" for k in liste)
    # İndirme: sahibi + yönetici; başka hesap 404; mesajda olmayan ek 404.
    y = await istemci.post(f"{M}/mesajlar/{mid}/ekler/{ek['id']}/indirme-baglantisi", headers=_b(a))
    assert y.status_code == 200 and y.json()["adres"].startswith(f"/api/v1/dosya-indir/{ek['id']}?")
    indir = await istemci.get(y.json()["adres"])
    assert indir.status_code == 200 and indir.content == b"merhaba"
    assert (await istemci.post(f"{M}/mesajlar/{mid}/ekler/{ek['id']}/indirme-baglantisi", headers=_b(b))).status_code == 404
    assert (await istemci.post(f"{M}/mesajlar/{mid}/ekler/{gizli.id}/indirme-baglantisi", headers=_b(a))).status_code == 404
    assert (await istemci.post(f"{Y}/mesajlar/{mid}/ekler/{ek['id']}/indirme-baglantisi", headers=yonetici_basligi)).status_code == 200
    # Yönetici: B'nin konuşmasına A'nın dosyası eklenemez; kendi yüklediği ek o hesaba yazılır.
    y = await _gonder(istemci, gb["id"], "yanlış hesap", yonetici_basligi, yonetici=True, ekler=[ek["id"]])
    assert y.status_code == 400 and _kod(y) == "ek_gecersiz"
    y = await istemci.post(f"{Y}/konusmalar/{gb['id']}/ekler", files=_dosya("teklif.txt"), headers=yonetici_basligi)
    assert y.status_code == 200
    d = (await db_oturumu.execute(select(Dosyalar).where(Dosyalar.id == y.json()["id"]))).scalar_one()
    assert d.client_email == b and d.yukleyen_rol == "admin"
    y = await _gonder(istemci, gb["id"], "Teklif ekte", yonetici_basligi, yonetici=True, ekler=[d.id])
    assert y.status_code == 200
    # En çok 5 ek.
    y = await _gonder(istemci, ga["id"], "çok", _b(a), ekler=[1, 2, 3, 4, 5, 6])
    assert y.status_code == 400 and _kod(y) == "cok_ek"


# ---------------------------------------------------------------------------
# Bildirimler
# ---------------------------------------------------------------------------
async def test_bildirim_2dk_sonra_bir_kez(istemci, db_oturumu):
    from services.mesajlar import bildirimleri_isle, simdi

    a = _e("a")
    g = await _genel(istemci, a)
    await _gonder(istemci, g["id"], "Merhaba, acil bir sorum var", _b(a))
    t0 = simdi()
    await bildirimleri_isle(db_oturumu, an=t0 + timedelta(minutes=1))
    assert await _bildirimler(db_oturumu, g["id"]) == []
    await bildirimleri_isle(db_oturumu, an=t0 + timedelta(minutes=3))
    satirlar = await _bildirimler(db_oturumu, g["id"])
    assert len(satirlar) >= 1 and {s.recipient_role for s in satirlar} == {"admin"}
    s = satirlar[0]
    assert s.event_type == "mesaj_yeni" and s.link == f"/admin?sekme=mesajlar&konusma={g['id']}"
    assert "Merhaba, acil bir sorum var" in s.body and f"/admin?sekme=mesajlar&konusma={g['id']}" in s.body
    # Bir kez: sonraki turlarda tekrar yok.
    await bildirimleri_isle(db_oturumu, an=t0 + timedelta(minutes=10))
    await bildirimleri_isle(db_oturumu, an=t0 + timedelta(hours=2))
    assert len(await _bildirimler(db_oturumu, g["id"])) == len(satirlar)


async def test_okunduysa_hic_bildirim_yok(istemci, db_oturumu, yonetici_basligi):
    from services.mesajlar import bildirimleri_isle, simdi

    a = _e("a")
    g = await _genel(istemci, a)
    m = (await _gonder(istemci, g["id"], "Teklifiniz hazır", yonetici_basligi, yonetici=True)).json()
    await istemci.post(f"{M}/konusmalar/{g['id']}/okundu", json={"mesaj_id": m["id"]}, headers=_b(a))
    t0 = simdi()
    await bildirimleri_isle(db_oturumu, an=t0 + timedelta(minutes=5))
    await bildirimleri_isle(db_oturumu, an=t0 + timedelta(hours=1))
    assert await _bildirimler(db_oturumu, g["id"]) == []


async def test_30dk_icinde_ikinci_bildirim_yok_toplanir(istemci, db_oturumu, yonetici_basligi):
    from services.mesajlar import bildirimleri_isle, simdi

    a = _e("a")
    g = await _genel(istemci, a)
    t0 = simdi()
    await _gonder(istemci, g["id"], "Birinci mesaj", yonetici_basligi, yonetici=True)
    await bildirimleri_isle(db_oturumu, an=t0 + timedelta(minutes=3))
    ilk = await _bildirimler(db_oturumu, g["id"])
    assert len(ilk) == 1 and ilk[0].recipient_email == a and ilk[0].recipient_role == "client"
    assert ilk[0].link == f"/client?sekme=mesajlar&konusma={g['id']}"
    assert f"hesap={a.replace('@', '%40')}" in ilk[0].body
    await _gonder(istemci, g["id"], "İkinci mesaj", yonetici_basligi, yonetici=True)
    await _gonder(istemci, g["id"], "Üçüncü mesaj", yonetici_basligi, yonetici=True)
    await bildirimleri_isle(db_oturumu, an=t0 + timedelta(minutes=10))
    await bildirimleri_isle(db_oturumu, an=t0 + timedelta(minutes=25))
    assert len(await _bildirimler(db_oturumu, g["id"])) == 1
    await bildirimleri_isle(db_oturumu, an=t0 + timedelta(minutes=34))
    satirlar = await _bildirimler(db_oturumu, g["id"])
    assert len(satirlar) == 2
    ikinci = max(satirlar, key=lambda s: s.id)
    assert "İkinci mesaj" in ikinci.body and "2 okunmamış" in ikinci.body


async def test_bildirim_mesajlar_izni_olan_ekibe_gider(istemci, db_oturumu, yonetici_basligi):
    from services.mesajlar import bildirimleri_isle, simdi

    sahip, uye, fatura = _e("sahip"), _e("uye"), _e("fatura")
    await _uye_ekle(db_oturumu, sahip, uye, "uye")
    await _uye_ekle(db_oturumu, sahip, fatura, "fatura")
    g = await _genel(istemci, sahip)
    await _gonder(istemci, g["id"], "Ekibe duyuru", yonetici_basligi, yonetici=True)
    await bildirimleri_isle(db_oturumu, an=simdi() + timedelta(minutes=3))
    satirlar = {s.recipient_email: s for s in await _bildirimler(db_oturumu, g["id"])}
    assert set(satirlar) == {sahip, uye}
    assert satirlar[uye].link == f"/client?sekme=mesajlar&konusma={g['id']}&hesap={sahip.replace('@', '%40')}"


async def test_bildirim_katalogu_ve_zamanli_gorev():
    from services.bildirim_tercih import OLAYLAR
    from services.hesap_ekibi import OLAY_IZNI
    from services.zamanli import GOREV_ADLARI

    assert OLAYLAR["mesaj_yeni"] == {"roller": ("admin", "client"), "tetikleniyor": True}
    assert OLAY_IZNI["mesaj_yeni"] == "mesajlar"
    assert "mesaj_bildirimleri" in GOREV_ADLARI and GOREV_ADLARI[-1] == "aylik_site_analizi"
    tr = json.loads((EK / "bildirim" / "tr.json").read_text(encoding="utf-8"))["bildirim"]["olay"]
    for dil in DILLER:
        ek = json.loads((EK / "bildirim" / f"{dil}.json").read_text(encoding="utf-8"))["bildirim"]["olay"]
        assert ek["mesaj_yeni"].strip()
        if dil != "tr":
            assert ek["mesaj_yeni"] != tr["mesaj_yeni"]


async def test_istek_tetiklemesi_dakikada_bir(monkeypatch):
    from services import mesajlar as s

    monkeypatch.setattr(s, "ISTEKLE_TETIKLE", True)
    monkeypatch.setattr(s, "_son_tetik", 0.0)
    assert s.istekle_tetiklenmeli_mi() is True
    assert s.istekle_tetiklenmeli_mi() is False


# ---------------------------------------------------------------------------
# Arşiv, silme, yönetici araçları
# ---------------------------------------------------------------------------
async def test_arsiv_ve_yazinca_yeniden_acilir(istemci, yonetici_basligi):
    a = _e("a")
    g = await _genel(istemci, a)
    y = await istemci.put(f"{Y}/konusmalar/{g['id']}", json={"durum": "arsiv"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "arsiv"
    ids = {k["id"] for k in (await istemci.get(f"{Y}/konusmalar", params={"durum": "acik"}, headers=yonetici_basligi)).json()["konusmalar"]}
    assert g["id"] not in ids
    assert (await istemci.put(f"{Y}/konusmalar/{g['id']}", json={"durum": "uydurma"}, headers=yonetici_basligi)).status_code == 400
    await _gonder(istemci, g["id"], "Bir sorum daha var", _b(a))
    assert (await _genel(istemci, a))["durum"] == "acik"
    # Müşteri arşivleyemez / silemez (uç yok).
    assert (await istemci.put(f"{M}/konusmalar/{g['id']}", json={"durum": "arsiv"}, headers=_b(a))).status_code in (404, 405)
    assert (await istemci.delete(f"{M}/konusmalar/{g['id']}", headers=_b(a))).status_code in (404, 405)


async def test_konusma_silme_cop_kutusuna_ve_geri_alma(istemci, db_oturumu, yonetici_basligi):
    from models.cop_kutusu import CopKutusu
    from models.mesajlar import KonusmaMesajlari, Konusmalar

    a = _e("a")
    y = await istemci.post(f"{Y}/konusmalar", json={"hesap_email": a, "konu": "Silinecek konu"}, headers=yonetici_basligi)
    assert y.status_code == 200
    kid = y.json()["id"]
    await _gonder(istemci, kid, "Ajans", yonetici_basligi, yonetici=True)
    await _gonder(istemci, kid, "Müşteri", _b(a))
    y = await istemci.delete(f"{Y}/konusmalar/{kid}", headers=yonetici_basligi)
    assert y.status_code == 200
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(Konusmalar).where(Konusmalar.id == kid))).first() is None
    kayitlar = (
        await db_oturumu.execute(select(CopKutusu).where(CopKutusu.sahip_email == a).order_by(CopKutusu.id))
    ).scalars().all()
    tablolar = sorted(k.tablo for k in kayitlar)
    assert tablolar.count("konusmalar") == 1 and tablolar.count("konusma_mesajlari") == 2 and "konusma_okunma" in tablolar
    assert len({k.grup for k in kayitlar}) == 1
    ana_id = next(k.id for k in kayitlar if k.tablo == "konusmalar")
    y = await istemci.post(f"/api/v1/cop-kutusu/{ana_id}/geri-al", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(Konusmalar).where(Konusmalar.id == kid))).first() is not None
    mesajlar = (await db_oturumu.execute(select(KonusmaMesajlari).where(KonusmaMesajlari.konusma_id == kid))).scalars().all()
    assert len(mesajlar) == 2
    # Müşteri silinen konuşmasını geri getiremez (silen yönetici).
    assert (await istemci.post(f"/api/v1/cop-kutum/{ana_id}/geri-al", headers=_b(a))).status_code in (403, 404, 409)


async def test_yonetici_adi_staff_tablosundan_ve_musteriye_eposta_gitmez(istemci, db_oturumu, yonetici_basligi):
    from models.staff import Staff

    db_oturumu.add(Staff(ad="Ayşe Destek", email="yonetici@test.dev", rol="yonetici", aktif=True))
    await db_oturumu.commit()
    a = _e("a")
    g = await _genel(istemci, a)
    m = (await _gonder(istemci, g["id"], "Merhaba", yonetici_basligi, yonetici=True)).json()
    assert m["yazan_ad"] == "Ayşe Destek" and m["yazan_email"] == "yonetici@test.dev"
    musteri_gorunumu = (await istemci.get(f"{M}/konusmalar/{g['id']}/mesajlar", headers=_b(a))).json()["mesajlar"][-1]
    assert musteri_gorunumu["yazan_ad"] == "Ayşe Destek" and musteri_gorunumu["yazan_email"] is None
    assert "yonetici@test.dev" not in json.dumps(musteri_gorunumu)


async def test_hazir_cevap_talep_ve_gorev(istemci, db_oturumu, yonetici_basligi):
    from models.projects import Projects
    from models.proje_gorevleri import ProjectTasks
    from models.support_tickets import Support_tickets

    a, b = _e("a"), _e("b")
    p = Projects(title="A projesi", description="d", category="Web", client_email=a.upper(), client_name="A Ltd")
    pb = Projects(title="B projesi", description="d", category="Web", client_email=b)
    db_oturumu.add_all([p, pb])
    await db_oturumu.commit()
    g = await _genel(istemci, a)
    m = (await _gonder(istemci, g["id"], "Ödeme sayfası açılmıyor, hata veriyor.", _b(a))).json()

    hc = (await istemci.post("/api/v1/destek/hazir-cevaplar", json={"baslik": "Selam", "metin": "Merhaba {musteri_adi}, {konu} için bakıyoruz."}, headers=yonetici_basligi)).json()
    y = await istemci.post(f"{Y}/konusmalar/{g['id']}/hazir-cevap", json={"hazir_cevap_id": hc["id"]}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["metin"] == "Merhaba A Ltd, Genel için bakıyoruz."

    y = await istemci.post(f"{Y}/konusmalar/{g['id']}/talep", json={"mesaj_id": m["id"]}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    t = (await db_oturumu.execute(select(Support_tickets).where(Support_tickets.id == y.json()["talep_id"]))).scalar_one()
    assert t.client_email == a and t.message == m["metin"] and t.acan_email == a and t.status == "open"

    y = await istemci.get(f"{Y}/konusmalar/{g['id']}", headers=yonetici_basligi)
    assert [x["id"] for x in y.json()["projeler"]] == [p.id]
    y = await istemci.post(f"{Y}/konusmalar/{g['id']}/gorev", json={"proje_id": p.id, "mesaj_id": m["id"]}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    gorev = (await db_oturumu.execute(select(ProjectTasks).where(ProjectTasks.id == y.json()["id"]))).scalar_one()
    assert gorev.proje_id == p.id and gorev.baslik.startswith("Ödeme sayfası") and gorev.musteriye_gorunur is False
    # Başka hesabın projesine görev açılmaz.
    y = await istemci.post(f"{Y}/konusmalar/{g['id']}/gorev", json={"proje_id": pb.id}, headers=yonetici_basligi)
    assert y.status_code == 404 and _kod(y) == "proje_yok"
    # Müşteri bu araçları kullanamaz.
    assert (await istemci.post(f"{Y}/konusmalar/{g['id']}/talep", json={}, headers=_b(a))).status_code == 403


async def test_proje_konusmasi_yalniz_kendi_projesiyle(istemci, db_oturumu):
    from models.projects import Projects

    a, b = _e("a"), _e("b")
    pb = Projects(title="B gizli", description="d", category="Web", client_email=b)
    pa = Projects(title="A", description="d", category="Web", client_email=a)
    db_oturumu.add_all([pa, pb])
    await db_oturumu.commit()
    y = await istemci.post(f"{M}/konusmalar", json={"konu": "Proje sorusu", "proje_id": pb.id}, headers=_b(a))
    assert y.status_code == 404 and _kod(y) == "proje_yok"
    y = await istemci.post(f"{M}/konusmalar", json={"konu": "Proje sorusu", "proje_id": pa.id}, headers=_b(a))
    assert y.status_code == 200 and y.json()["proje_id"] == pa.id


async def test_modul_kapaliysa_403(istemci, monkeypatch):
    from services import moduller

    async def _kapali(db, eposta, anahtar):
        return anahtar != "mesajlar"

    monkeypatch.setattr(moduller, "modul_acik_mi", _kapali)
    y = await istemci.get(f"{M}/konusmalar", headers=_b(_e("a")))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"


# ---------------------------------------------------------------------------
# Ön yüz tutarlılığı
# ---------------------------------------------------------------------------
def _duz(d, on=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _duz(v, f"{on}{k}.")
        else:
            yield f"{on}{k}", v


def test_ek_paket_yedi_dilde_ayni_anahtarlar_ve_gercek_ceviri():
    paketler = {
        dil: dict(_duz(json.loads((EK / "mesajlar" / f"{dil}.json").read_text(encoding="utf-8"))["mesajlar"]))
        for dil in DILLER
    }
    anahtarlar = set(paketler["tr"])
    assert len(anahtarlar) > 30
    for dil, p in paketler.items():
        assert set(p) == anahtarlar, (dil, set(p) ^ anahtarlar)
        assert all(isinstance(v, str) and v.strip() for v in p.values()), dil
    for dil in ("en", "de", "ru", "zh", "hi", "ar"):
        ayni = [k for k in anahtarlar if paketler[dil][k] == paketler["tr"][k] and len(paketler["tr"][k]) > 12]
        assert not ayni, (dil, ayni[:5])
    # Sunucunun hata kodlarının hepsinin metni var.
    for kod in ("metin_uzun", "bos_mesaj", "ek_gecersiz", "cok_ek", "cok_hizli", "duzenleme_suresi_doldu",
                "mesaj_sizin_degil", "konusma_yok", "proje_yok", "konusma_siniri", "tur_izinsiz", "boyut_asildi"):
        assert f"hata.{kod}" in anahtarlar, kod


def test_sekme_etiketi_ve_izin_etiketi_yedi_dilde():
    for dil in DILLER:
        ana = json.loads((KOK / "frontend" / "src" / "i18n" / f"{dil}.json").read_text(encoding="utf-8"))
        assert ana["ui"]["tabMesajlar"].strip() and ana["ui"]["tabSohbetler"].strip(), dil
        ekip = json.loads((EK / "hesapEkibi" / f"{dil}.json").read_text(encoding="utf-8"))["hesapEkibi"]
        assert ekip["izin"]["mesajlar"].strip(), dil
        cop = json.loads((EK / "copKutusu" / f"{dil}.json").read_text(encoding="utf-8"))["copKutusu"]
        assert cop["tablo"]["konusmalar"].strip(), dil
