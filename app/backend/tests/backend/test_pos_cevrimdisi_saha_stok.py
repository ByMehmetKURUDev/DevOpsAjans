"""Faz 6Q — (a) POS kasa ekranının çevrimdışı satış kuyruğu, (b) saha servisi malzemelerini stoktan düşme.

(a) Kuyruk sunucu tarafı: aynı `istemci_kimligi` iki kez → tek kayıt (ikinci yanıt ilk kaydı `tekrar: true`
ile döndürür, stok bir kez düşer); başka hesapta aynı kimlik çakışmaz; çevrimdışı satışın zorunlu alanları;
kasa oturumu kapalıyken / başka kişi kapatmışken gelen satış "eşitleme" oturumuna bağlanır (kapanmış oturumun
donmuş Z'si değişmez; kaynak oturum başına tek eşitleme satırı; gün sonu raporunda "çevrimdışı eşitlenen"
sayısı); satış zamanı cihazdaki an (gelecek → şimdi, açılıştan önce → açılış); eksi stok kuralı ayardan
(kapalıyken 409 ve hiçbir şey yazılmaz; açıkken satış + uyarı listesi + hareket açıklamasında iz); fiyat
değiştiyse 409 ve "güncel fiyatla" yeniden gönderim.

(b) Saha ↔ stok: Stok ve POS modülü kapalıysa seçenek yok (ayar/ürün arama/bağlı satır 409); ayar varsayılan
KAPALI ve kapalıyken tamamlanan iş stoktan düşmez; açıkken tamamlanınca `cikis` (belge no = iş emri no,
kaynak "saha"), yeniden açılınca ters hareket, iki kez düşülmez (durum + servis düzeyinde), silinen düşülmüş
satır geri eklenir; teknisyen ürün listesini görür ama maliyeti görmez; teknisyenin araç konumundan düşer;
kritik stok olayı (`stok.kritik`) mevcut altyapıdan; stok raporunda saha tüketimi süzgeci + raporu (CSV).
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from conftest import jeton_uret

SP = "/api/v1/stok-pos"
SM = "/api/v1/saha-servisim"
MODUL = "/api/v1/moduller"
UTC = timezone.utc


def _e(on: str) -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@q6.dev"


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


async def _ok(y, kod=200):
    assert y.status_code == kod, y.text
    return y.json()


def _iso(an: datetime) -> str:
    return an.astimezone(UTC).isoformat().replace("+00:00", "Z")


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    from routers import saha_servisi as rs
    from routers import stok_pos as rp
    from services import hesap_ekibi, webhook
    from services import saha_kayit as sk

    rp.hiz_sinirlarini_temizle()
    rs.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    sk.kanca_onbellegi_temizle()
    monkeypatch.setattr(webhook, "ANLIK_TESLIMAT", False)
    yield
    rp.hiz_sinirlarini_temizle()
    rs.hiz_sinirlarini_temizle()


@pytest.fixture
def olaylar(monkeypatch):
    from services import webhook

    kayit = []
    asil = webhook.olay_yayinla

    async def _sahte(db, tur, hesap, veri, **k):
        kayit.append((tur, hesap, veri))
        return await asil(db, tur, hesap, veri, **k)

    monkeypatch.setattr(webhook, "olay_yayinla", _sahte)
    return kayit


async def _modul(istemci, yonetici_basligi, hesap, anahtar, acik=True, **ayarlar):
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


async def _urun(istemci, b, **govde):
    return await _ok(await istemci.post(f"{SP}/urunler", json=govde, headers=b))


async def _giris(istemci, b, urun_id, miktar, konum_id):
    await _ok(await istemci.post(f"{SP}/hareketler", json={"tur": "giris", "konum_id": konum_id,
                                                           "kalemler": [{"urun_id": urun_id, "miktar": miktar}]}, headers=b))


async def _stok(istemci, b, urun_id, konum_id=None):
    u = await _ok(await istemci.get(f"{SP}/urunler/{urun_id}", headers=b))
    return u["stok"]["konumlar"].get(str(konum_id), 0) if konum_id else u["stok"]["toplam"]


# ===========================================================================
# (a) POS çevrimdışı kuyruk
# ===========================================================================
@pytest.fixture
async def kasa(istemci, yonetici_basligi):
    """İşletme (stok_pos açık) + kahve (adet, 120 TL, %10, stok 5) + açık kasa."""
    sahip = _e("kasa")
    await _modul(istemci, yonetici_basligi, sahip, "stok_pos")
    b = _b(sahip)
    kahve = await _urun(istemci, b, ad="Filtre kahve", satis_fiyati="120", alis_fiyati="50", kdv_orani=10)
    konum = (await _ok(await istemci.get(f"{SP}/meta", headers=b)))["konumlar"][0]["id"]
    await _giris(istemci, b, kahve["id"], 5, konum)
    o = await _ok(await istemci.post(f"{SP}/kasa/ac", json={"konum_id": konum, "acilis_nakit": "100"}, headers=b))
    return {"sahip": sahip, "b": b, "kahve": kahve, "konum": konum, "oturum": o}


def _cevrimdisi(k, kimlik=None, adet=1, oturum=None, **ek):
    govde = {"konum_id": k["konum"], "kalemler": [{"urun_id": k["kahve"]["id"], "adet": adet}], "odeme": {"tur": "nakit"},
             "cevrimdisi": True, "istemci_kimligi": kimlik or str(uuid.uuid4()), "oturum_id": (oturum or k["oturum"])["id"],
             "cevrimdisi_no": "ÇEVRİMDIŞI-1"}
    govde.update(ek)
    return govde


async def test_ayni_istemci_kimligi_iki_kez_tek_kayit(istemci, kasa, db_oturumu):
    from models.stok_pos import PosSatislari, StokHareketleri

    k = kasa
    kimlik = str(uuid.uuid4())  # istemcinin ürettiği UUID (36 karakter, tireli)
    x1 = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, kimlik, adet=2), headers=k["b"]))
    x2 = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, kimlik, adet=2), headers=k["b"]))
    assert x1["tekrar"] is False and x2["tekrar"] is True and x1["id"] == x2["id"] and x1["no"] == x2["no"]
    assert x1["cevrimdisi_no"] == "ÇEVRİMDIŞI-1" and x1["esitlendi_at"] and x1["oturum_id"] == k["oturum"]["id"]
    n = (await db_oturumu.execute(select(func.count(PosSatislari.id)).where(PosSatislari.hesap_email == k["sahip"],
                                                                           PosSatislari.istemci_kimligi == kimlik))).scalar()
    assert n == 1
    assert await _stok(istemci, k["b"], k["kahve"]["id"]) == 3  # 5 − 2, bir kez
    h = (await db_oturumu.execute(select(StokHareketleri).where(StokHareketleri.satis_id == x1["id"]))).scalars().all()
    assert len(h) == 1 and h[0].aciklama.startswith("Çevrimdışı satış ÇEVRİMDIŞI-1")
    # Çevrimiçi aynı kimlik de aynı kaydı döndürür (kuyruk ile normal gönderim çakışsa bile tek satış)
    x3 = await _ok(await istemci.post(f"{SP}/satislar", json={"konum_id": k["konum"], "kalemler": [{"urun_id": k["kahve"]["id"], "adet": 2}],
                                                              "odeme": {"tur": "nakit"}, "istemci_kimligi": kimlik}, headers=k["b"]))
    assert x3["id"] == x1["id"] and x3["tekrar"] is True


async def test_farkli_hesap_ayni_kimlik_cakisma_yok(istemci, yonetici_basligi, kasa):
    k1 = kasa
    sahip2 = _e("kasa2")
    await _modul(istemci, yonetici_basligi, sahip2, "stok_pos")
    b2 = _b(sahip2)
    cay = await _urun(istemci, b2, ad="Çay", satis_fiyati="20", kdv_orani=10)
    konum2 = (await _ok(await istemci.get(f"{SP}/meta", headers=b2)))["konumlar"][0]["id"]
    await _giris(istemci, b2, cay["id"], 10, konum2)
    o2 = await _ok(await istemci.post(f"{SP}/kasa/ac", json={"konum_id": konum2}, headers=b2))
    kimlik = str(uuid.uuid4())
    x1 = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k1, kimlik), headers=k1["b"]))
    x2 = await _ok(await istemci.post(f"{SP}/satislar", json={
        "konum_id": konum2, "kalemler": [{"urun_id": cay["id"], "adet": 1}], "odeme": {"tur": "nakit"}, "cevrimdisi": True,
        "istemci_kimligi": kimlik, "oturum_id": o2["id"]}, headers=b2))
    assert x1["id"] != x2["id"] and x2["tekrar"] is False and x2["toplam"] == 2000
    # Başka hesabın oturum kimliğiyle gönderilen kuyruk satışı reddedilir (yalnız aynı hesabın oturumu)
    y = await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k1, oturum=o2), headers=k1["b"])
    assert y.status_code == 404 and _kod(y) == "oturum_yok"


async def test_cevrimdisi_zorunlu_alanlar_ve_cozum_bekleyen_hatalar(istemci, kasa, yonetici_basligi):
    k = kasa
    g = _cevrimdisi(k)
    g.pop("istemci_kimligi")
    y = await istemci.post(f"{SP}/satislar", json=g, headers=k["b"])
    assert y.status_code == 400 and _kod(y) == "istemci_kimligi_gerekli"
    g = _cevrimdisi(k)
    g.pop("oturum_id")
    y = await istemci.post(f"{SP}/satislar", json=g, headers=k["b"])
    assert y.status_code == 400 and _kod(y) == "oturum_gerekli"
    y = await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, cevrimdisi_no="x" * 30), headers=k["b"])
    assert y.status_code == 400 and _kod(y) == "cevrimdisi_no_gecersiz"
    y = await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, istemci_zamani="dün"), headers=k["b"])
    assert y.status_code == 400 and _kod(y) == "istemci_zamani_gecersiz"
    # Ürün bu arada silindiyse (pasif) satış 404 — cihazda "çözüm bekleyen" olarak kalır, hiçbir şey yazılmaz
    sil = await _urun(istemci, k["b"], ad="Kek", satis_fiyati="30", kdv_orani=10, stok_takibi=False)
    await _ok(await istemci.put(f"{SP}/urunler/{sil['id']}", json={"aktif": False}, headers=k["b"]))
    y = await istemci.post(f"{SP}/satislar", json={**_cevrimdisi(k), "kalemler": [{"urun_id": sil["id"], "adet": 1}]}, headers=k["b"])
    assert y.status_code == 404 and _kod(y) == "urun_yok"
    # Fiyat değiştiyse 409 (`toplam_degisti`); kullanıcı "güncel fiyatla kaydet" derse beklenen toplam olmadan gider
    await _ok(await istemci.put(f"{SP}/urunler/{k['kahve']['id']}", json={"satis_fiyati": "130"}, headers=k["b"]))
    kimlik = str(uuid.uuid4())
    y = await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, kimlik, beklenen_toplam="120", odeme={"tur": "nakit", "nakit_alinan": "120"}),
                           headers=k["b"])
    assert y.status_code == 409 and _kod(y) == "toplam_degisti" and y.json()["detail"]["toplam"] == 13000
    x = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, kimlik), headers=k["b"]))
    assert x["toplam"] == 13000 and x["tekrar"] is False
    # Şube eşleşmiyorsa 409 (ikinci şube)
    await _modul(istemci, yonetici_basligi, k["sahip"], "stok_pos", sube_siniri=2)
    sube = await _ok(await istemci.post(f"{SP}/konumlar", json={"ad": "Şube 2"}, headers=k["b"]))
    y = await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, konum_id=sube["id"]), headers=k["b"])
    assert y.status_code == 409 and _kod(y) == "oturum_konum_uyusmuyor"


async def test_satis_zamani_cihazdaki_an_sinirli(istemci, kasa, monkeypatch):
    from services import stok_pos

    k = kasa
    acilis = datetime.fromisoformat(k["oturum"]["acilis_at"].replace("Z", "+00:00"))
    simdi = acilis + timedelta(hours=1)  # kuyruk bir saat sonra eşitleniyor
    monkeypatch.setattr(stok_pos, "simdi", lambda: simdi)
    an = acilis + timedelta(minutes=10)
    x = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, istemci_zamani=_iso(an)), headers=k["b"]))
    assert datetime.fromisoformat(x["zaman"].replace("Z", "+00:00")) == an
    assert datetime.fromisoformat(x["esitlendi_at"].replace("Z", "+00:00")) == simdi
    # Oturum açılışından önce → açılış; gelecekte → şimdi (cihaz saati kaymış olabilir)
    x = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, istemci_zamani=_iso(acilis - timedelta(days=3))), headers=k["b"]))
    assert datetime.fromisoformat(x["zaman"].replace("Z", "+00:00")) == acilis
    x = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, istemci_zamani=_iso(simdi + timedelta(days=2))), headers=k["b"]))
    assert datetime.fromisoformat(x["zaman"].replace("Z", "+00:00")) == simdi
    # Saat dilimi verilmezse UTC sayılır
    x = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, istemci_zamani=an.replace(tzinfo=None).isoformat()), headers=k["b"]))
    assert datetime.fromisoformat(x["zaman"].replace("Z", "+00:00")) == an


async def test_kapali_oturum_esitleme_oturumuna_baglanir(istemci, kasa, db_oturumu):
    """Kasa, kuyruk eşitlenmeden kapandıysa (aynı ya da başka cihaz/kişi): satış kaybolmaz, kapanmış oturumun
    donmuş Z'si değişmez; kaynak oturuma bağlı TEK "eşitleme" oturumu açılır (kendiliğinden kapalı)."""
    from models.stok_pos import PosKasaOturumlari

    k = kasa
    stokcu, kasiyer = _e("stokcu"), _e("kasiyer")
    await _uye(db_oturumu, k["sahip"], stokcu, ["stok"])
    await _uye(db_oturumu, k["sahip"], kasiyer, ["kasa"])
    # Çevrimiçi bir satış, sonra kasayı BAŞKA kişi kapatır
    await _ok(await istemci.post(f"{SP}/satislar", json={"konum_id": k["konum"], "kalemler": [{"urun_id": k["kahve"]["id"], "adet": 1}],
                                                        "odeme": {"tur": "nakit"}}, headers=k["b"]))
    z = await _ok(await istemci.post(f"{SP}/kasa/{k['oturum']['id']}/kapat", json={"sayilan_nakit": "220"}, headers=_b(stokcu, k["sahip"])))
    assert z["ozet"]["satis_sayisi"] == 1 and z["ozet"]["cevrimdisi_sayisi"] == 0
    # Kuyruktaki iki satış eşitlenir (ilkini hiç kasa açmamış kasiyerin cihazı gönderir)
    x1 = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, cevrimdisi_no="ÇEVRİMDIŞI-1"), headers=_b(kasiyer, k["sahip"])))
    x2 = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, adet=2, cevrimdisi_no="ÇEVRİMDIŞI-2"), headers=k["b"]))
    assert x1["oturum_id"] == x2["oturum_id"] != k["oturum"]["id"]
    es = (await db_oturumu.execute(select(PosKasaOturumlari).where(PosKasaOturumlari.id == x1["oturum_id"]))).scalars().one()
    assert es.tur == "esitleme" and es.kaynak_oturum_id == k["oturum"]["id"] and es.durum == "kapali" and es.acan == kasiyer
    assert (await db_oturumu.execute(select(func.count(PosKasaOturumlari.id)).where(
        PosKasaOturumlari.kaynak_oturum_id == k["oturum"]["id"]))).scalar() == 1
    # Kapanmış oturumun Z'si donmuş kaldı; eşitleme oturumunun özeti geç gelen nakdi gösterir
    eski = await _ok(await istemci.get(f"{SP}/kasa/{k['oturum']['id']}", headers=k["b"]))
    assert eski["ozet"]["satis_sayisi"] == 1
    yeni = await _ok(await istemci.get(f"{SP}/kasa/{es.id}", headers=k["b"]))
    assert yeni["oturum"]["tur"] == "esitleme" and yeni["ozet"]["satis_sayisi"] == 2 and yeni["ozet"]["cevrimdisi_sayisi"] == 2
    assert yeni["ozet"]["nakit"]["beklenen"] == 36000
    # Gün sonu raporu: 3 satış, 2'si çevrimdışı eşitlenen; eşitleme oturumu listede türüyle
    g = await _ok(await istemci.get(f"{SP}/raporlar/gun", headers=k["b"]))
    assert g["satis_sayisi"] == 3 and g["cevrimdisi_sayisi"] == 2 and g["cevrimdisi_toplam"] == 36000
    assert {o["tur"] for o in g["oturumlar"]} == {"kasa", "esitleme"}
    # Eşitleme oturumu "açık kasa" sayılmaz: yeni kasa açılabilir; kasa kullanıcı sayısına girmez
    meta = await _ok(await istemci.get(f"{SP}/meta", headers=k["b"]))
    assert meta["acik_oturumlar"] == []
    o2 = await _ok(await istemci.post(f"{SP}/kasa/ac", json={"konum_id": k["konum"]}, headers=k["b"]))
    # Yeni oturum açıkken, eski oturumun kuyruğu yine eşitleme oturumuna (aynı satır) gider
    x3 = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k), headers=k["b"]))
    assert x3["oturum_id"] == es.id != o2["id"]
    # Eşitleme oturumu kuyruk satışının hedefi olarak verilemez
    y = await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, oturum={"id": es.id}), headers=k["b"])
    assert y.status_code == 404 and _kod(y) == "oturum_yok"
    from services import stok_kayit as stk

    # Eşitleme oturumunu açan kasiyer "bu ay kasa kullanan kişi" sınırına sayılmaz
    assert kasiyer not in await stk.ay_kasiyerleri(db_oturumu, k["sahip"])


async def test_eksi_stok_kurali_ayardan(istemci, kasa, db_oturumu):
    from models.stok_pos import PosSatislari, StokHareketleri

    k = kasa  # kahve stoku 5, eksi stok kapalı (varsayılan)
    kimlik = str(uuid.uuid4())
    y = await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, kimlik, adet=7), headers=k["b"])
    assert y.status_code == 409 and _kod(y) == "yetersiz_stok"
    assert await _stok(istemci, k["b"], k["kahve"]["id"]) == 5
    assert (await db_oturumu.execute(select(func.count(PosSatislari.id)).where(PosSatislari.istemci_kimligi == kimlik))).scalar() == 0
    # Ayar açılınca aynı satış (aynı kimlik — "tekrar dene") geçer; eksiye düşen ürün yanıtta + hareket açıklamasında
    await _ok(await istemci.put(f"{SP}/ayarlar", json={"eksi_stok": True}, headers=k["b"]))
    x = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k, kimlik, adet=7), headers=k["b"]))
    assert x["eksi_stok"] == [{"urun_id": k["kahve"]["id"], "ad": "Filtre kahve", "birim": "adet", "miktar": -2.0}]
    assert await _stok(istemci, k["b"], k["kahve"]["id"]) == -2
    h = (await db_oturumu.execute(select(StokHareketleri).where(StokHareketleri.satis_id == x["id"]))).scalars().one()
    assert "eksiye düştü" in h.aciklama
    # Çevrimiçi satış uyarı listesi taşımaz (yalnız kuyruktan gelenler raporlanır)
    o = await _ok(await istemci.post(f"{SP}/satislar", json={"konum_id": k["konum"], "kalemler": [{"urun_id": k["kahve"]["id"], "adet": 1}],
                                                             "odeme": {"tur": "kart"}}, headers=k["b"]))
    assert o["eksi_stok"] == [] and o["cevrimdisi_no"] is None and o["esitlendi_at"] is None


async def test_kasiyer_kuyrugu_yalniz_kendi_hesabinda(istemci, kasa, db_oturumu):
    """Kasiyer (yalnız `kasa`) kuyruğu sahibin hesabına gönderebilir; üye olmadığı hesaba gönderemez."""
    k = kasa
    kasiyer = _e("kasiyer")
    await _uye(db_oturumu, k["sahip"], kasiyer, ["kasa"])
    x = await _ok(await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k), headers=_b(kasiyer, k["sahip"])))
    assert x["kasiyer"] == kasiyer
    yabanci = _e("yabanci")
    y = await istemci.post(f"{SP}/satislar", json=_cevrimdisi(k), headers=_b(yabanci, k["sahip"]))
    assert y.status_code == 403 and _kod(y) == "hesap_uyesi_degil"


# ===========================================================================
# (b) Saha malzemeleri ↔ stok
# ===========================================================================
@pytest.fixture
async def servis(istemci, yonetici_basligi, db_oturumu):
    """Saha servisi + Stok ve POS açık firma; teknisyen (yalnız `saha_teknisyen`); stok ürünü "Bakır boru"
    (m, alış 40, satış 120 KDV %20, kritik eşik 7, stok 10); teknisyene atanmış planlı iş emri."""
    sahip = _e("servis")
    await _modul(istemci, yonetici_basligi, sahip, "saha_servisi")
    await _modul(istemci, yonetici_basligi, sahip, "stok_pos", sube_siniri=2)
    tek = _e("tek")
    await _uye(db_oturumu, sahip, tek, ["saha_teknisyen"])
    b = _b(sahip)
    await _ok(await istemci.get(f"{SM}/meta", headers=b))
    ta = await _ok(await istemci.post(f"{SM}/teknisyenler", json={"eposta": tek, "ad": "Ali Usta"}, headers=b))
    m = await _ok(await istemci.post(f"{SM}/musteriler", json={"ad": "Ayşe Kaya", "lokasyon": {"ad": "Ev", "adres": "Bağdat Cad. 1"}},
                                     headers=b))
    konum = (await _ok(await istemci.get(f"{SP}/meta", headers=b)))["konumlar"][0]["id"]
    boru = await _urun(istemci, b, ad="Bakır boru", birim="m", satis_fiyati="120", alis_fiyati="40", kdv_orani=20, kritik_esik=7,
                       barkod="BKR-14", sku="BKR14")
    vida = await _urun(istemci, b, ad="Vida", satis_fiyati="2", alis_fiyati="1", kdv_orani=20)
    await _giris(istemci, b, boru["id"], 10, konum)
    await _giris(istemci, b, vida["id"], 100, konum)
    yarin = datetime.now(UTC) + timedelta(days=1)
    ie = await _ok(await istemci.post(f"{SM}/is-emirleri", json={
        "musteri_id": m["id"], "lokasyon_id": m["lokasyonlar"][0]["id"], "baslik": "Klima montajı", "tur": "ariza",
        "plan_bas": _iso(yarin), "tahmini_dk": 60, "teknisyenler": [ta["id"]]}, headers=b))
    return {"sahip": sahip, "b": b, "tek": tek, "tb": _b(tek, sahip), "ta": ta, "m": m, "konum": konum, "boru": boru,
            "vida": vida, "ie": ie}


async def _ayar(istemci, f, **govde):
    return await _ok(await istemci.put(f"{SM}/ayarlar", json=govde, headers=f["b"]))


async def _bitir(istemci, f, is_id):
    """Teknisyen: yolda → başla → bitir."""
    for d in ("yolda", "iste", "tamamlandi"):
        await _ok(await istemci.post(f"{SM}/is-emirleri/{is_id}/durum", json={"durum": d}, headers=f["tb"]))
    return await _ok(await istemci.get(f"{SM}/is-emirleri/{is_id}", headers=f["b"]))


async def test_stok_modulu_kapaliysa_secenek_yok(istemci, yonetici_basligi):
    sahip = _e("yalniz-saha")
    await _modul(istemci, yonetici_basligi, sahip, "saha_servisi")
    b = _b(sahip)
    meta = await _ok(await istemci.get(f"{SM}/meta", headers=b))
    assert meta["stok"] == {"modul": False, "acik": False}
    a = await _ok(await istemci.get(f"{SM}/ayarlar", headers=b))
    assert a["stok_modulu"] is False and a["stok_konumlari"] == [] and a["stoktan_dus"] is False
    y = await istemci.put(f"{SM}/ayarlar", json={"stoktan_dus": True}, headers=b)
    assert y.status_code == 409 and _kod(y) == "stok_modulu_kapali"
    # Ön yüz kaydederken kapalı değeri geri gönderir: sorun değil
    await _ok(await istemci.put(f"{SM}/ayarlar", json={"stoktan_dus": False, "stok_konum_id": None, "firma_adi": "X"}, headers=b))
    y = await istemci.put(f"{SM}/ayarlar", json={"stok_konum_id": 1}, headers=b)
    assert y.status_code == 409 and _kod(y) == "stok_modulu_kapali"
    y = await istemci.get(f"{SM}/stok-urunleri", headers=b)
    assert y.status_code == 409 and _kod(y) == "stok_baglantisi_kapali"


async def test_ayar_varsayilan_kapali_ve_kapaliyken_dusmez(istemci, servis):
    f = servis
    a = await _ok(await istemci.get(f"{SM}/ayarlar", headers=f["b"]))
    assert a["stok_modulu"] is True and a["stoktan_dus"] is False and [k["id"] for k in a["stok_konumlari"]] == [f["konum"]]
    meta = await _ok(await istemci.get(f"{SM}/meta", headers=f["b"]))
    assert meta["stok"] == {"modul": True, "acik": False}
    y = await istemci.post(f"{SM}/is-emirleri/{f['ie']['id']}/malzemeler", json={"stok_urun_id": f["boru"]["id"], "miktar": 2}, headers=f["tb"])
    assert y.status_code == 409 and _kod(y) == "stok_baglantisi_kapali"
    # Açıkken bağlı satır eklenir, sonra ayar kapatılır: tamamlanınca düşmez
    await _ayar(istemci, f, stoktan_dus=True)
    k = await _ok(await istemci.post(f"{SM}/is-emirleri/{f['ie']['id']}/malzemeler", json={"stok_urun_id": f["boru"]["id"], "miktar": "2,5"},
                                     headers=f["tb"]))
    assert k["stok_urun_id"] == f["boru"]["id"] and k["miktar"] == 2.5 and k["stoktan_dusuldu"] is False
    await _ayar(istemci, f, stoktan_dus=False)
    ie = await _bitir(istemci, f, f["ie"]["id"])
    assert ie["durum"] == "tamamlandi" and ie["malzemeler"][0]["stoktan_dusuldu"] is False
    assert await _stok(istemci, f["b"], f["boru"]["id"]) == 10


async def test_tamamlaninca_duser_yeniden_acinca_geri_alir_iki_kez_dusmez(istemci, servis, db_oturumu, olaylar):
    from models.saha_servisi import SahaIsEmirleri, SahaMalzemeKullanimi
    from services import saha_stok

    f = servis
    await _ayar(istemci, f, stoktan_dus=True)
    is_id = f["ie"]["id"]
    # Teknisyen stok ürününü arar (ad / barkod / SKU) ve ekler; serbest metin malzeme de mümkün
    for ara in ("bakır", "Bakır", "BKR-1", "BKR14"):
        bul = await _ok(await istemci.get(f"{SM}/stok-urunleri", params={"ara": ara}, headers=f["tb"]))
        assert [u["id"] for u in bul["items"]] == [f["boru"]["id"]], ara
    y = await istemci.post(f"{SM}/is-emirleri/{is_id}/malzemeler", json={"stok_urun_id": f["vida"]["id"], "miktar": "1,5"}, headers=f["tb"])
    assert y.status_code == 400 and _kod(y) == "miktar_tam_olmali"
    k1 = await _ok(await istemci.post(f"{SM}/is-emirleri/{is_id}/malzemeler", json={"stok_urun_id": f["boru"]["id"], "miktar": 4}, headers=f["tb"]))
    assert k1["birim"] == "m" and k1["birim_fiyat"] == 10000 and k1["tutar"] == 40000  # 120 KDV dahil → 100 KDV hariç
    k2 = await _ok(await istemci.post(f"{SM}/is-emirleri/{is_id}/malzemeler", json={"stok_urun_id": f["vida"]["id"], "miktar": 6}, headers=f["tb"]))
    await _ok(await istemci.post(f"{SM}/is-emirleri/{is_id}/malzemeler", json={"ad": "Bant", "miktar": 1, "birim_fiyat": "15"}, headers=f["tb"]))
    assert await _stok(istemci, f["b"], f["boru"]["id"]) == 10  # eklerken düşmez
    ie = await _bitir(istemci, f, is_id)
    assert await _stok(istemci, f["b"], f["boru"]["id"]) == 6 and await _stok(istemci, f["b"], f["vida"]["id"]) == 94
    assert [x["stoktan_dusuldu"] for x in ie["malzemeler"]] == [True, True, False]
    # Hareket: cikis, belge no = iş emri no, kaynak saha; kritik eşik (7) altına inince stok.kritik TEK olay
    h = await _ok(await istemci.get(f"{SP}/hareketler", params={"kaynak": "saha"}, headers=f["b"]))
    assert {(x["tur"], x["belge_no"], x["kaynak"], x["kaynak_id"]) for x in h["items"]} == {("cikis", ie["no"], "saha", is_id)}
    assert len(h["items"]) == 2
    kritik = [v for t, _, v in olaylar if t == "stok.kritik"]
    assert len(kritik) == 1 and kritik[0]["urun_id"] == f["boru"]["id"] and kritik[0]["miktar"] == 6
    # İkinci kez tamamlanamaz (geçersiz geçiş) ve servis yeniden çağrılsa da düşmez
    y = await istemci.post(f"{SM}/is-emirleri/{is_id}/durum", json={"durum": "tamamlandi"}, headers=f["b"])
    assert y.status_code == 409 and _kod(y) == "gecersiz_gecis"
    ie_db = (await db_oturumu.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.id == is_id))).scalars().one()
    assert await saha_stok.is_tamamlandi(db_oturumu, ie_db, f["sahip"]) == []
    await db_oturumu.commit()
    assert await _stok(istemci, f["b"], f["boru"]["id"]) == 6
    # Yeniden açma yalnız yönetimde; teknisyen 403
    y = await istemci.post(f"{SM}/is-emirleri/{is_id}/yeniden-ac", json={"neden": "Kaçak"}, headers=f["tb"])
    assert y.status_code == 403
    ie = await _ok(await istemci.post(f"{SM}/is-emirleri/{is_id}/yeniden-ac", json={"neden": "Kaçak"}, headers=f["b"]))
    assert ie["durum"] == "iste" and ie["bitir_at"] is None and ie["gecmis"][-1]["yeni"] == "iste" and ie["gecmis"][-1]["neden"] == "Kaçak"
    assert [x["stoktan_dusuldu"] for x in ie["malzemeler"]] == [False, False, False]
    assert await _stok(istemci, f["b"], f["boru"]["id"]) == 10 and await _stok(istemci, f["b"], f["vida"]["id"]) == 100
    y = await istemci.post(f"{SM}/is-emirleri/{is_id}/yeniden-ac", json={}, headers=f["b"])
    assert y.status_code == 409 and _kod(y) == "gecersiz_gecis"
    h = await _ok(await istemci.get(f"{SP}/hareketler", params={"kaynak": "saha", "tur": "iade"}, headers=f["b"]))
    assert len(h["items"]) == 2 and all(x["belge_no"] == ie["no"] for x in h["items"])
    # Açıkken vida satırı silinir; yeniden bitirince yalnız boru BİR kez düşer
    await _ok(await istemci.delete(f"{SM}/is-emirleri/{is_id}/malzemeler/{k2['id']}", headers=f["tb"]))
    await _ok(await istemci.post(f"{SM}/is-emirleri/{is_id}/durum", json={"durum": "tamamlandi"}, headers=f["tb"]))
    assert await _stok(istemci, f["b"], f["boru"]["id"]) == 6 and await _stok(istemci, f["b"], f["vida"]["id"]) == 100
    # Düşülmüş satır silinirse (servis) ters hareket; ikinci kez geri alınmaz
    satir = (await db_oturumu.execute(select(SahaMalzemeKullanimi).where(SahaMalzemeKullanimi.id == k1["id"]))).scalars().one()
    await db_oturumu.refresh(satir)
    assert satir.stok_dusum_at is not None and satir.stok_konum_id == f["konum"]
    ie_db = (await db_oturumu.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.id == is_id))).scalars().one()
    g1 = await saha_stok.satir_silindi(db_oturumu, ie_db, satir, f["sahip"])
    await db_oturumu.commit()
    await db_oturumu.refresh(satir)
    g2 = await saha_stok.satir_silindi(db_oturumu, ie_db, satir, f["sahip"])
    await db_oturumu.commit()
    assert len(g1) == 1 and g2 == [] and await _stok(istemci, f["b"], f["boru"]["id"]) == 10


async def test_teknisyen_maliyet_goremez_ve_arac_konumundan_duser(istemci, servis):
    f = servis
    sube = await _ok(await istemci.post(f"{SP}/konumlar", json={"ad": "Araç 34 AB 12"}, headers=f["b"]))
    await _giris(istemci, f["b"], f["boru"]["id"], 5, sube["id"])
    await _ayar(istemci, f, stoktan_dus=True, stok_konum_id=f["konum"])
    a = await _ok(await istemci.get(f"{SM}/ayarlar", headers=f["b"]))
    assert a["stok_konum_id"] == f["konum"] and {k["id"] for k in a["stok_konumlari"]} == {f["konum"], sube["id"]}
    y = await istemci.put(f"{SM}/ayarlar", json={"stok_konum_id": 999999}, headers=f["b"])
    assert y.status_code == 404 and _kod(y) == "stok_konum_yok"
    t = await _ok(await istemci.put(f"{SM}/teknisyenler/{f['ta']['id']}", json={"stok_konum_id": sube["id"]}, headers=f["b"]))
    assert t["stok_konum_id"] == sube["id"]
    # Teknisyen: ürün listesi + KDV hariç birim fiyat + KENDİ araç stoğu; alış fiyatı (maliyet) yok
    bul = await _ok(await istemci.get(f"{SM}/stok-urunleri", params={"ara": "Bakır"}, headers=f["tb"]))
    u = bul["items"][0]
    assert bul["konum_id"] == sube["id"] and u["stok"] == 5 and u["stok_toplam"] == 15 and u["birim_fiyat"] == 10000
    assert "alis_fiyati" not in u and "maliyet" not in json.dumps(bul)
    yon = await _ok(await istemci.get(f"{SM}/stok-urunleri", headers=f["b"]))
    assert all("alis_fiyati" not in x for x in yon["items"])
    # Teknisyen 6P stok uçlarına erişemez (maliyet orada)
    assert (await istemci.get(f"{SP}/urunler", headers=f["tb"])).status_code == 403
    await _ok(await istemci.post(f"{SM}/is-emirleri/{f['ie']['id']}/malzemeler", json={"stok_urun_id": f["boru"]["id"], "miktar": 3},
                                 headers=f["tb"]))
    ie = await _ok(await istemci.get(f"{SM}/is-emirleri/{f['ie']['id']}", headers=f["tb"]))
    assert "alis_fiyati" not in json.dumps(ie["malzemeler"])
    await _bitir(istemci, f, f["ie"]["id"])
    assert await _stok(istemci, f["b"], f["boru"]["id"], sube["id"]) == 2
    assert await _stok(istemci, f["b"], f["boru"]["id"], f["konum"]) == 10


async def test_saha_tuketimi_raporu_ve_hareket_suzgeci(istemci, servis):
    f = servis
    await _ayar(istemci, f, stoktan_dus=True)
    await _ok(await istemci.post(f"{SM}/is-emirleri/{f['ie']['id']}/malzemeler", json={"stok_urun_id": f["boru"]["id"], "miktar": 2},
                                 headers=f["tb"]))
    ie = await _bitir(istemci, f, f["ie"]["id"])
    r = await _ok(await istemci.get(f"{SP}/raporlar/saha-tuketimi", headers=f["b"]))
    assert r["urunler"] == [{"urun_id": f["boru"]["id"], "ad": "Bakır boru", "barkod": "BKR-14", "birim": "m", "miktar": 2.0,
                             "maliyet": 8000, "is_emri": 1}]
    assert r["toplam"] == {"urun": 1, "maliyet": 8000, "is_emri": 1}
    csv = await istemci.get(f"{SP}/raporlar/saha-tuketimi?bicim=csv", headers=f["b"])
    assert csv.status_code == 200 and "Bakır boru" in csv.text and "80,00" in csv.text
    meta = await _ok(await istemci.get(f"{SP}/meta", headers=f["b"]))
    assert meta["saha"] is True and meta["hareket_kaynaklari"] == ["saha"]
    tum = await _ok(await istemci.get(f"{SP}/hareketler", headers=f["b"]))
    saha = await _ok(await istemci.get(f"{SP}/hareketler", params={"kaynak": "saha"}, headers=f["b"]))
    assert tum["toplam"] > saha["toplam"] == 1 and saha["items"][0]["belge_no"] == ie["no"]
    y = await istemci.get(f"{SP}/hareketler", params={"kaynak": "uydurma"}, headers=f["b"])
    assert y.status_code == 400 and _kod(y) == "kaynak_gecersiz"
    # Yeniden açılınca rapor net sıfır (ürün listeden düşer)
    await _ok(await istemci.post(f"{SM}/is-emirleri/{f['ie']['id']}/yeniden-ac", json={}, headers=f["b"]))
    r = await _ok(await istemci.get(f"{SP}/raporlar/saha-tuketimi", headers=f["b"]))
    assert r["urunler"] == [] and r["toplam"]["maliyet"] == 0
