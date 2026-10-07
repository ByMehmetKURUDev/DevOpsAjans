"""Faz 6P — Stok ve satış noktası (POS).

Kapsam: EAN-13 kontrol hanesi ve iç barkod üretimi, KDV dökümü yuvarlaması (grup toplamından; satır KDV'leri
toplamı tutar), toplam indirimin dağıtımı, stok hareketleri tutarlılığı (giriş/çıkış/fire/düzeltme + hareket
sonrası miktar), eksi stok ayarı, eşzamanlı iki satış aynı son ürünü (tek düşüş), sayım farkı, şubeler arası
transfer ve şube sınırı, satış + para üstü + kısmi iade + kasa kapanış farkı ve Z-benzeri özet, iptal, ürün
bazlı kâr raporu, kritik stok olayı TEK kez (eşik üstüne çıkınca yeniden kurulur), izinler (kasa yalnız satış,
iade/indirim limiti), müşteri izolasyonu, modül kapalıyken 403, yönetici salt okunur görünümü, QR menü ürünleriyle
ortak kullanım (bağlı aktarım + "tükendi" eşitlemesi), CSV içe/dışa aktarma, fiş/fatura PDF'i (mali değil ibaresi),
istemci kimliğiyle tekrar gönderimde tek satış, olay kataloğu ve haftalık özet kalemi.
"""

import asyncio
import json
import uuid

import pytest
from sqlalchemy import func, select

from conftest import jeton_uret

M = "/api/v1/stok-pos"
Y = "/api/v1/stok-pos-yonetim"
MODUL = "/api/v1/moduller"


def _e(on: str = "pos") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@pos.dev"


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


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    from routers import stok_pos as r
    from services import hesap_ekibi, webhook

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    monkeypatch.setattr(webhook, "ANLIK_TESLIMAT", False)
    yield
    r.hiz_sinirlarini_temizle()


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


async def _modul(istemci, yonetici_basligi, hesap, acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{hesap}/stok_pos", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _uye(db, hesap, uye, izinler, rol="uye"):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as he

    db.add(HesapUyeleri(hesap_email=hesap, uye_email=uye, rol=rol, izinler=json.dumps(izinler), durum="aktif", olusturma=he.simdi()))
    await db.commit()
    he.onbellegi_temizle()


@pytest.fixture
async def dukkan(istemci, yonetici_basligi):
    """İşletme (modül açık, 2 şube hakkı) + iki ürün: kahve (adet, %10) ve peynir (kg, %1)."""
    sahip = _e("dukkan")
    await _modul(istemci, yonetici_basligi, sahip, sube_siniri=2)
    b = _b(sahip)
    kahve = await _ok(await istemci.post(f"{M}/urunler", json={
        "ad": "Filtre kahve", "barkod": "4006381333931", "sku": "FK-1", "kategori": "Kahve", "alis_fiyati": "50",
        "satis_fiyati": "120", "kdv_orani": 10, "kritik_esik": 2}, headers=b))
    peynir = await _ok(await istemci.post(f"{M}/urunler", json={
        "ad": "Beyaz peynir", "birim": "kg", "alis_fiyati": "150", "satis_fiyati": "240,50", "kdv_orani": 1}, headers=b))
    meta = await _ok(await istemci.get(f"{M}/meta", headers=b))
    return {"sahip": sahip, "b": b, "kahve": kahve, "peynir": peynir, "konum": meta["konumlar"][0]["id"]}


async def _giris(istemci, d, urun_id, miktar, maliyet=None, konum=None):
    kalem = {"urun_id": urun_id, "miktar": miktar}
    if maliyet is not None:
        kalem["birim_maliyet"] = maliyet
    return await _ok(await istemci.post(f"{M}/hareketler", json={"tur": "giris", "konum_id": konum or d["konum"],
                                                                   "kalemler": [kalem]}, headers=d["b"]))


async def _stok(istemci, d, urun_id, konum=None):
    u = await _ok(await istemci.get(f"{M}/urunler/{urun_id}", headers=d["b"]))
    return u["stok"]["konumlar"].get(str(konum or d["konum"]), 0) if konum else u["stok"]["toplam"]


async def _kasa_ac(istemci, d, nakit="100", basliklar=None, konum=None):
    return await _ok(await istemci.post(f"{M}/kasa/ac", json={"konum_id": konum or d["konum"], "acilis_nakit": nakit},
                                        headers=basliklar or d["b"]))


async def _sat(istemci, d, kalemler, odeme=None, basliklar=None, **ek):
    return await istemci.post(f"{M}/satislar", json={"konum_id": d["konum"], "kalemler": kalemler,
                                                      "odeme": odeme or {"tur": "nakit"}, **ek}, headers=basliklar or d["b"])


# ---------------------------------------------------------------------------
# Saf kurallar
# ---------------------------------------------------------------------------
def test_ean13_kontrol_hanesi_ve_ic_barkod():
    import random

    from services import stok_pos as s

    assert s.ean_kontrol_hanesi("400638133393") == 1
    assert s.ean_kontrol_hanesi("869000000001") == 2
    assert s.ean_gecerli_mi("4006381333931") and not s.ean_gecerli_mi("4006381333932")
    assert s.ean_gecerli_mi("96385074")  # EAN-8
    for _ in range(50):
        kod = s.ic_barkod_uret(random.Random(_))
        assert len(kod) == 13 and kod.startswith("20") and s.ean_gecerli_mi(kod)
    with pytest.raises(s.StokHatasi) as h:
        s.barkod_duzelt("4006381333932")
    assert h.value.kod == "barkod_kontrol_hanesi" and h.value.ek["beklenen"] == 1
    assert s.barkod_duzelt(" ABC-123 ") == "ABC-123" and s.barkod_turu("ABC-123") == "code128"
    with pytest.raises(s.StokHatasi):
        s.barkod_duzelt("ç<script>")


def test_kdv_dokumu_yuvarlama_ve_indirim_dagitimi():
    from services import stok_pos as s

    # Üç ayrı satır 0,10 TL (%20): satır satır yuvarlasaydık 3 × 0,02 = 0,06 KDV olurdu; grup toplamından 0,05.
    k = [s.KalemGirdi(i, f"u{i}", None, "adet", 1000, 10, 20) for i in range(3)]
    r = s.sepet_hesapla(k)
    assert r.toplam == 30 and r.kdv_dokumu == [{"oran": 20, "tutar": 30, "matrah": 25, "kdv": 5}]
    assert sum(x.kdv for x in r.kalemler) == r.kdv_toplam == 5
    # Karışık oranlar + satır indirimi + toplam indirim (orantılı dağıtım, toplamlar birebir).
    k = [s.KalemGirdi(1, "a", None, "adet", 3000, 333, 10, satir_indirim=99), s.KalemGirdi(2, "b", None, "kg", 1250, 24050, 1),
         s.KalemGirdi(3, "c", None, "adet", 1000, 1999, 20)]
    r = s.sepet_hesapla(k, 1001)
    assert r.ara_toplam == 999 + 30063 + 1999 and r.satir_indirim == 99 and r.toplam_indirim == 1001
    assert r.toplam == r.ara_toplam - 99 - 1001 == sum(x.tutar for x in r.kalemler)
    assert sum(x.pay for x in r.kalemler) == 1001
    assert sum(d["tutar"] for d in r.kdv_dokumu) == r.toplam
    for d in r.kdv_dokumu:
        assert d["kdv"] == s.kdv_ayir(d["tutar"], d["oran"]) and d["matrah"] + d["kdv"] == d["tutar"]
        assert sum(x.kdv for x in r.kalemler if x.girdi.kdv_orani == d["oran"]) == d["kdv"]
    # Yarım yukarı: 1,10 TL %10 → 0,10 KDV; 0,21 %10 → 0,019 → 0,02.
    assert s.kdv_ayir(110, 10) == 10 and s.kdv_ayir(21, 10) == 2 and s.kdv_ayir(5, 0) == 0
    # Miktar: kg kesirli, adet tam.
    assert s.miktar_coz("1,25", "x", "kg") == 1250
    with pytest.raises(s.StokHatasi) as h:
        s.miktar_coz(1.5, "x", "adet")
    assert h.value.kod == "miktar_tam_olmali"
    # Ödeme: karma, para üstü.
    assert s.odeme_coz({"tur": "nakit", "nakit_alinan": "200"}, 15050) == {
        "tur": "nakit", "nakit": 15050, "kart": 0, "havale": 0, "nakit_alinan": 20000, "para_ustu": 4950}
    assert s.odeme_coz({"tur": "karma", "kart": "100", "nakit_alinan": "60"}, 15050)["para_ustu"] == 950
    with pytest.raises(s.StokHatasi):
        s.odeme_coz({"tur": "nakit", "nakit_alinan": "100"}, 15050)


# ---------------------------------------------------------------------------
# Erişim
# ---------------------------------------------------------------------------
async def test_modul_kapaliyken_403_oturumsuz_401_yonetici_ucu_musteriye_403(istemci, yonetici_basligi):
    kapali = _e("kapali")
    y = await istemci.get(f"{M}/meta", headers=_b(kapali))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    assert (await istemci.get(f"{M}/meta")).status_code == 401
    assert (await istemci.get(f"{Y}/hesaplar", headers=_b(kapali))).status_code == 403
    await _modul(istemci, yonetici_basligi, kapali)
    assert (await istemci.get(f"{M}/meta", headers=_b(kapali))).status_code == 200
    await _modul(istemci, yonetici_basligi, kapali, acik=False)
    y = await istemci.post(f"{M}/satislar", json={}, headers=_b(kapali))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"


async def test_urun_barkod_uretimi_dogrulama_cakisma_ve_varyant(istemci, dukkan):
    from services import stok_pos as s

    d = dukkan
    assert d["kahve"]["barkod_turu"] == "ean13" and d["kahve"]["alis_fiyati"] == 5000 and d["kahve"]["satis_fiyati"] == 12000
    assert s.ean_gecerli_mi(d["peynir"]["barkod"]) and d["peynir"]["barkod"].startswith("20")
    assert d["peynir"]["satis_fiyati"] == 24050 and d["peynir"]["kdv_orani"] == 1
    y = await istemci.post(f"{M}/urunler", json={"ad": "x", "barkod": "4006381333932", "satis_fiyati": 1}, headers=d["b"])
    assert y.status_code == 400 and _kod(y) == "barkod_kontrol_hanesi"
    y = await istemci.post(f"{M}/urunler", json={"ad": "x", "barkod": "4006381333931", "satis_fiyati": 1}, headers=d["b"])
    assert y.status_code == 409 and _kod(y) == "barkod_kullaniliyor"
    y = await istemci.post(f"{M}/urunler", json={"ad": "x", "sku": "FK-1", "satis_fiyati": 1}, headers=d["b"])
    assert y.status_code == 409 and _kod(y) == "sku_kullaniliyor"
    y = await istemci.post(f"{M}/urunler", json={"ad": "x", "satis_fiyati": 1, "kdv_orani": 8}, headers=d["b"])
    assert y.status_code == 400 and _kod(y) == "kdv_orani_gecersiz"
    # Okutma: barkod ya da SKU
    assert (await _ok(await istemci.get(f"{M}/urunler/kod/FK-1", headers=d["b"])))["id"] == d["kahve"]["id"]
    assert (await istemci.get(f"{M}/urunler/kod/0000", headers=d["b"])).status_code == 404
    # Varyant (beden/renk): kendi barkodu, ana ürünün fiyatı
    v = await _ok(await istemci.post(f"{M}/urunler/{d['kahve']['id']}/varyant", json={"varyant": {"beden": "250 g"}}, headers=d["b"]))
    assert v["ana_urun_id"] == d["kahve"]["id"] and v["ad"] == "Filtre kahve — 250 g" and v["satis_fiyati"] == 12000
    assert v["barkod"] != d["kahve"]["barkod"]
    u = await _ok(await istemci.get(f"{M}/urunler/{d['kahve']['id']}", headers=d["b"]))
    assert [x["id"] for x in u["varyantlar"]] == [v["id"]]
    # Ürün sınırı (modül ayarı)
    meta = await _ok(await istemci.get(f"{M}/meta", headers=d["b"]))
    assert meta["sinirlar"]["urun"] == 1000 and meta["sayilar"]["urun"] == 3


async def test_stok_hareketleri_tutarliligi_ve_eksi_stok_ayari(istemci, dukkan):
    d = dukkan
    k = d["kahve"]["id"]
    await _giris(istemci, d, k, 10, maliyet="55")
    assert await _stok(istemci, d, k) == 10
    u = await _ok(await istemci.get(f"{M}/urunler/{k}", headers=d["b"]))
    assert u["alis_fiyati"] == 5500  # son alış fiyatı
    await _ok(await istemci.post(f"{M}/hareketler", json={"tur": "cikis", "kalemler": [{"urun_id": k, "miktar": 3}]}, headers=d["b"]))
    await _ok(await istemci.post(f"{M}/hareketler", json={"tur": "fire", "kalemler": [{"urun_id": k, "miktar": 1}]}, headers=d["b"]))
    assert await _stok(istemci, d, k) == 6
    await _ok(await istemci.post(f"{M}/hareketler", json={"tur": "duzeltme", "kalemler": [{"urun_id": k, "miktar": 8}]}, headers=d["b"]))
    h = (await _ok(await istemci.get(f"{M}/hareketler?urun_id={k}", headers=d["b"])))["items"]
    assert [(x["tur"], x["miktar"], x["sonra"]) for x in reversed(h)] == [
        ("giris", 10, 10), ("cikis", -3, 7), ("fire", -1, 6), ("duzeltme", 2, 8)]
    # Kesirli kg
    p = d["peynir"]["id"]
    await _giris(istemci, d, p, "2,5")
    assert await _stok(istemci, d, p) == 2.5
    y = await istemci.post(f"{M}/hareketler", json={"tur": "giris", "kalemler": [{"urun_id": k, "miktar": 1.5}]}, headers=d["b"])
    assert y.status_code == 400 and _kod(y) == "miktar_tam_olmali"
    # Eksi stok kapalı: yetersiz → 409, hiçbir kalem düşmez (işlem geri alınır)
    y = await istemci.post(f"{M}/hareketler", json={"tur": "cikis", "kalemler": [{"urun_id": p, "miktar": 1}, {"urun_id": k, "miktar": 20}]},
                           headers=d["b"])
    assert y.status_code == 409 and _kod(y) == "yetersiz_stok" and y.json()["detail"]["mevcut"] == 8
    assert await _stok(istemci, d, p) == 2.5 and await _stok(istemci, d, k) == 8
    # Eksi stok açık: düşer
    await _ok(await istemci.put(f"{M}/ayarlar", json={"eksi_stok": True}, headers=d["b"]))
    await _ok(await istemci.post(f"{M}/hareketler", json={"tur": "cikis", "kalemler": [{"urun_id": k, "miktar": 10}]}, headers=d["b"]))
    assert await _stok(istemci, d, k) == -2


async def test_eszamanli_iki_satis_ayni_son_urun_tek_dusus(istemci, dukkan, db_oturumu):
    from models.stok_pos import PosSatislari

    d = dukkan
    k = d["kahve"]["id"]
    await _giris(istemci, d, k, 1)
    await _kasa_ac(istemci, d)
    y1, y2 = await asyncio.gather(_sat(istemci, d, [{"urun_id": k, "adet": 1}]), _sat(istemci, d, [{"urun_id": k, "adet": 1}]))
    assert sorted([y1.status_code, y2.status_code]) == [200, 409], (y1.text, y2.text)
    assert "yetersiz_stok" in {_kod(y1), _kod(y2)}
    assert await _stok(istemci, d, k) == 0
    n = (await db_oturumu.execute(select(func.count(PosSatislari.id)).where(PosSatislari.hesap_email == d["sahip"]))).scalar()
    assert n == 1


async def test_satis_para_ustu_iade_kasa_kapanis_farki_ve_z_ozeti(istemci, dukkan, olaylar):
    d = dukkan
    k, p = d["kahve"]["id"], d["peynir"]["id"]
    await _giris(istemci, d, k, 10)
    await _giris(istemci, d, p, 5)
    # Kasa kapalıyken satış yok
    y = await _sat(istemci, d, [{"urun_id": k, "adet": 1}])
    assert y.status_code == 409 and _kod(y) == "kasa_kapali"
    o = await _kasa_ac(istemci, d, "100")
    y = await istemci.post(f"{M}/kasa/ac", json={"konum_id": d["konum"]}, headers=d["b"])
    assert y.status_code == 409 and _kod(y) == "kasa_zaten_acik"
    # 2 kahve (240) + 1,5 kg peynir (360,75) − satırda 10 TL indirim − toplamda %5 → nakit, 600 TL verildi
    x = await _ok(await _sat(istemci, d, [{"urun_id": k, "adet": 2, "indirim": "10"}, {"urun_id": p, "adet": 1.5}],
                             {"tur": "nakit", "nakit_alinan": "600"}, toplam_indirim_yuzde=5))
    assert x["ara_toplam"] == 24000 + 36075 and x["satir_indirim"] == 1000
    assert x["toplam_indirim"] == round((60075 - 1000) * 5 / 100)
    toplam = 60075 - 1000 - x["toplam_indirim"]
    assert x["toplam"] == toplam and x["nakit"] == toplam and x["para_ustu"] == 60000 - toplam
    assert sum(dd["tutar"] for dd in x["kdv_dokumu"]) == toplam
    assert x["mali_degil"].startswith("Bu belge mali fiş değildir")
    assert await _stok(istemci, d, k) == 8 and await _stok(istemci, d, p) == 3.5
    assert any(t == "pos.satis" and v["satis_id"] == x["id"] and "musteri" not in json.dumps(v) for t, _, v in olaylar)
    # Kart satışı
    xk = await _ok(await _sat(istemci, d, [{"urun_id": k, "adet": 1}], {"tur": "kart"}))
    assert xk["kart"] == 12000 and xk["nakit"] == 0
    # Kısmi iade (1 kahve, nakit): stok geri, tutar satırın payı
    kahve_kalem = next(kk for kk in x["kalemler"] if kk["urun_id"] == k)
    xi = await _ok(await istemci.post(f"{M}/satislar/{x['id']}/iade", json={"kalemler": [{"kalem_id": kahve_kalem["id"], "adet": 1}],
                                                                             "odeme_turu": "nakit", "neden": "kırık"}, headers=d["b"]))
    iade_tutar = xi["iadeler"][0]["tutar"]
    assert xi["durum"] == "kismi_iade" and xi["iade_toplam"] == iade_tutar == round(kahve_kalem["tutar"] / 2)
    assert await _stok(istemci, d, k) == 8
    y = await istemci.post(f"{M}/satislar/{x['id']}/iade", json={"kalemler": [{"kalem_id": kahve_kalem["id"], "adet": 2}]}, headers=d["b"])
    assert y.status_code == 400 and _kod(y) == "iade_fazla"
    # Kalan her şeyi iade: son birim kalan tutarın tamamı (yuvarlama birikmez)
    xi = await _ok(await istemci.post(f"{M}/satislar/{x['id']}/iade", json={"odeme_turu": "nakit"}, headers=d["b"]))
    assert xi["durum"] == "iade" and xi["iade_toplam"] == toplam
    # Özet ve kapanış: beklenen = açılış + nakit satış − nakit iade
    oz = (await _ok(await istemci.get(f"{M}/kasa/{o['id']}", headers=d["b"])))["ozet"]
    assert oz["satis_sayisi"] == 2 and oz["iade_toplam"] == toplam and oz["net"] == 12000
    assert oz["odemeler"] == {"nakit": 0, "kart": 12000, "havale": 0}
    assert oz["nakit"]["beklenen"] == 10000 + toplam - toplam
    assert oz["kdv_dokumu"] == [{"oran": 10, "tutar": 12000, "matrah": 10909, "kdv": 1091}]
    assert oz["en_cok_satanlar"][0]["urun_id"] == k and oz["en_cok_satanlar"][0]["adet"] == 1
    z = await _ok(await istemci.post(f"{M}/kasa/{o['id']}/kapat", json={"sayilan_nakit": "95,50"}, headers=d["b"]))
    assert z["oturum"]["durum"] == "kapali" and z["oturum"]["beklenen_nakit"] == 10000 and z["oturum"]["fark"] == -450
    assert z["ozet"]["nakit"]["fark"] == -450 and "Z raporu" in z["not"]
    # Kapalı kasada satış yok; gün raporu iki satışı görür
    assert _kod(await _sat(istemci, d, [{"urun_id": k, "adet": 1}])) == "kasa_kapali"
    g = await _ok(await istemci.get(f"{M}/raporlar/gun", headers=d["b"]))
    assert g["satis_sayisi"] == 2 and g["net"] == 12000 and len(g["oturumlar"]) == 1
    csv = await istemci.get(f"{M}/raporlar/donem?bicim=csv", headers=d["b"])
    assert csv.status_code == 200 and csv.text.startswith("﻿tarih;satis_sayisi") and "120,00" in csv.text


async def test_iptal_ayni_oturumda_kapaninca_yok(istemci, dukkan):
    d = dukkan
    k = d["kahve"]["id"]
    await _giris(istemci, d, k, 5)
    o = await _kasa_ac(istemci, d, "0")
    x = await _ok(await _sat(istemci, d, [{"urun_id": k, "adet": 2}]))
    xi = await _ok(await istemci.post(f"{M}/satislar/{x['id']}/iptal", json={"neden": "yanlış ürün"}, headers=d["b"]))
    assert xi["durum"] == "iptal" and await _stok(istemci, d, k) == 5
    assert (await istemci.post(f"{M}/satislar/{x['id']}/iptal", json={}, headers=d["b"])).status_code == 409
    x2 = await _ok(await _sat(istemci, d, [{"urun_id": k, "adet": 1}]))
    oz = (await _ok(await istemci.get(f"{M}/kasa/{o['id']}", headers=d["b"])))["ozet"]
    assert oz["satis_sayisi"] == 1 and oz["iptal_sayisi"] == 1 and oz["iptal_toplam"] == 24000 and oz["nakit"]["beklenen"] == 12000
    await _ok(await istemci.post(f"{M}/kasa/{o['id']}/kapat", json={"sayilan_nakit": 120}, headers=d["b"]))
    await _kasa_ac(istemci, d, "0")
    y = await istemci.post(f"{M}/satislar/{x2['id']}/iptal", json={}, headers=d["b"])
    assert y.status_code == 409 and _kod(y) == "iptal_suresi_gecti"


async def test_sayim_farki_ve_sayilmayanlar(istemci, dukkan):
    d = dukkan
    k, p = d["kahve"]["id"], d["peynir"]["id"]
    await _giris(istemci, d, k, 10)
    await _giris(istemci, d, p, 2)
    x = await _ok(await istemci.post(f"{M}/sayimlar", json={}, headers=d["b"]))
    assert (await istemci.post(f"{M}/sayimlar", json={}, headers=d["b"])).status_code == 409
    for _ in range(3):
        r = await _ok(await istemci.post(f"{M}/sayimlar/{x['id']}/okut", json={"kod": "4006381333931"}, headers=d["b"]))
    assert r["sayilan"] == 3 and r["sistem"] == 10 and r["fark"] == -7
    r = await _ok(await istemci.post(f"{M}/sayimlar/{x['id']}/okut", json={"urun_id": k, "sayilan": 8}, headers=d["b"]))
    assert r["fark"] == -2
    ay = await _ok(await istemci.get(f"{M}/sayimlar/{x['id']}", headers=d["b"]))
    assert [(s["urun_id"], s["sayilan"], s["sistem"]) for s in ay["kalemler"]] == [(k, 8, 10)]
    onay = await _ok(await istemci.post(f"{M}/sayimlar/{x['id']}/onayla", json={"sayilmayanlar_sifir": True}, headers=d["b"]))
    assert onay["durum"] == "onaylandi" and onay["ozet"]["farkli"] == 2 and onay["ozet"]["fark_eksi"] == 4
    assert onay["ozet"]["deger_farki"] == -(2 * 5000 + 2 * 15000)
    assert await _stok(istemci, d, k) == 8 and await _stok(istemci, d, p) == 0
    h = (await _ok(await istemci.get(f"{M}/hareketler?tur=sayim", headers=d["b"])))["items"]
    assert sorted(x_["miktar"] for x_ in h) == [-2, -2]
    assert (await istemci.post(f"{M}/sayimlar/{x['id']}/okut", json={"urun_id": k}, headers=d["b"])).status_code == 409


async def test_transfer_ve_sube_siniri(istemci, dukkan, yonetici_basligi):
    d = dukkan
    k = d["kahve"]["id"]
    sube = await _ok(await istemci.post(f"{M}/konumlar", json={"ad": "Kadıköy şubesi"}, headers=d["b"]))
    y = await istemci.post(f"{M}/konumlar", json={"ad": "Üçüncü"}, headers=d["b"])
    assert y.status_code == 403 and _kod(y) == "sube_siniri"
    await _giris(istemci, d, k, 10)
    await _ok(await istemci.post(f"{M}/transfer", json={"kaynak_konum_id": d["konum"], "hedef_konum_id": sube["id"],
                                                         "kalemler": [{"urun_id": k, "miktar": 4}]}, headers=d["b"]))
    u = await _ok(await istemci.get(f"{M}/urunler/{k}", headers=d["b"]))
    assert u["stok"]["konumlar"] == {str(d["konum"]): 6, str(sube["id"]): 4} and u["stok"]["toplam"] == 10
    y = await istemci.post(f"{M}/transfer", json={"kaynak_konum_id": sube["id"], "hedef_konum_id": d["konum"],
                                                   "kalemler": [{"urun_id": k, "miktar": 5}]}, headers=d["b"])
    assert y.status_code == 409 and _kod(y) == "yetersiz_stok"
    y = await istemci.post(f"{M}/transfer", json={"kaynak_konum_id": sube["id"], "hedef_konum_id": sube["id"],
                                                   "kalemler": [{"urun_id": k, "miktar": 1}]}, headers=d["b"])
    assert y.status_code == 400 and _kod(y) == "ayni_konum"
    h = (await _ok(await istemci.get(f"{M}/hareketler", headers=d["b"])))["items"]
    t = [x for x in h if x["tur"].startswith("transfer")]
    assert len(t) == 2 and len({x["transfer_kodu"] for x in t}) == 1
    # Stok değeri raporu şube süzgeci
    r = await _ok(await istemci.get(f"{M}/raporlar/stok-degeri?konum_id={sube['id']}", headers=d["b"]))
    assert r["toplam"]["maliyet_degeri"] == 4 * 5000


async def test_urun_bazli_kar_raporu_ve_hareketsiz(istemci, dukkan):
    d = dukkan
    k, p = d["kahve"]["id"], d["peynir"]["id"]
    await _giris(istemci, d, k, 10)
    await _giris(istemci, d, p, 3)
    await _kasa_ac(istemci, d)
    x = await _ok(await _sat(istemci, d, [{"urun_id": k, "adet": 3}], {"tur": "kart"}))
    await _ok(await istemci.post(f"{M}/satislar/{x['id']}/iade", json={"kalemler": [{"kalem_id": x["kalemler"][0]["id"], "adet": 1}],
                                                                        "odeme_turu": "kart"}, headers=d["b"]))
    r = await _ok(await istemci.get(f"{M}/raporlar/kar", headers=d["b"]))
    satir = next(u for u in r["urunler"] if u["urun_id"] == k)
    # Net 2 adet × 120 TL (KDV %10 dahil) = 240 → matrah 218,18; maliyet 2 × 50 = 100
    assert satir["adet"] == 2 and satir["ciro"] == 24000 - 2182 and satir["maliyet"] == 10000 and satir["kar"] == 24000 - 2182 - 10000
    csv = await istemci.get(f"{M}/raporlar/kar?bicim=csv", headers=d["b"])
    assert "Filtre kahve" in csv.text
    hz = await _ok(await istemci.get(f"{M}/raporlar/hareketsiz?gun=30", headers=d["b"]))
    assert [u["urun_id"] for u in hz["urunler"]] == [p]


async def test_kritik_stok_olayi_tek_kez_ve_yeniden_kurulur(istemci, dukkan, olaylar, db_oturumu):
    from models.notifications import Notifications

    d = dukkan
    k = d["kahve"]["id"]  # eşik 2
    await _giris(istemci, d, k, 5)
    await _kasa_ac(istemci, d)
    await _ok(await _sat(istemci, d, [{"urun_id": k, "adet": 3}]))
    x = await _ok(await _sat(istemci, d, [{"urun_id": k, "adet": 1}]))
    assert x["kritik"] == []
    kritik = [v for t, _, v in olaylar if t == "stok.kritik"]
    assert len(kritik) == 1 and kritik[0]["urun_id"] == k and kritik[0]["miktar"] == 2 and kritik[0]["esik"] == 2
    n = (await db_oturumu.execute(select(func.count(Notifications.id)).where(
        Notifications.event_type == "stok_kritik", Notifications.recipient_email == d["sahip"]))).scalar()
    assert n >= 1
    liste = await _ok(await istemci.get(f"{M}/urunler?kritik=true", headers=d["b"]))
    assert [u["id"] for u in liste["items"]] == [k] and liste["items"][0]["kritik"] is True
    # Eşik üstüne çıkınca kurulur, yeniden düşünce bir olay daha
    await _giris(istemci, d, k, 10)
    assert (await _ok(await istemci.get(f"{M}/urunler?kritik=true", headers=d["b"])))["items"] == []
    await _ok(await _sat(istemci, d, [{"urun_id": k, "adet": 10}]))
    assert len([1 for t, _, _ in olaylar if t == "stok.kritik"]) == 2
    # Haftalık özet (ajans) kalemi
    from services import haftalik_ozet

    oz = await haftalik_ozet.ozet_hazirla(db_oturumu)
    b = next(x for x in oz["bolumler"] if x["anahtar"] == "stok_kritik")
    assert b["sayi"] >= 1 and b["sekme"] == "stokPos" and any(o["ayrinti"] == d["sahip"] for o in b["ornekler"]) or b["sayi"] > 5


async def test_kasa_izni_yalniz_satis_iade_ve_indirim_siniri(istemci, dukkan, db_oturumu):
    d = dukkan
    kasiyer = _e("kasiyer")
    await _uye(db_oturumu, d["sahip"], kasiyer, ["kasa"])
    kb = _b(kasiyer, d["sahip"])
    k = d["kahve"]["id"]
    await _giris(istemci, d, k, 10)
    meta = await _ok(await istemci.get(f"{M}/meta", headers=kb))
    assert meta["yetki"] == {"stok": False, "kasa": True, "ajans": False}
    liste = await _ok(await istemci.get(f"{M}/urunler", headers=kb))
    assert liste["items"] and all("alis_fiyati" not in u for u in liste["items"])
    for yol, govde in (("/urunler", {"ad": "x", "satis_fiyati": 1}), ("/hareketler", {"tur": "giris", "kalemler": []}),
                       ("/sayimlar", {}), ("/konumlar", {"ad": "x"})):
        y = await istemci.post(M + yol, json=govde, headers=kb)
        assert y.status_code == 403 and _kod(y) == "hesap_izni_yok", (yol, y.text)
    for yol in ("/raporlar/gun", "/raporlar/kar", "/ayarlar", "/urunler.csv", "/tedarikciler"):
        y = await istemci.get(M + yol, headers=kb)
        assert y.status_code == 403 and _kod(y) == "hesap_izni_yok", yol
    o = await _kasa_ac(istemci, d, "50", basliklar=kb)
    assert o["acan"] == kasiyer
    # İndirim sınırı %10 (varsayılan): %15 → 403
    y = await _sat(istemci, d, [{"urun_id": k, "adet": 1}], basliklar=kb, toplam_indirim_yuzde=15)
    assert y.status_code == 403 and _kod(y) == "indirim_limiti"
    x = await _ok(await _sat(istemci, d, [{"urun_id": k, "adet": 2}], basliklar=kb, toplam_indirim_yuzde=10))
    assert x["kasiyer"] == kasiyer
    # İade: ayar kapalıyken 403, açınca olur
    y = await istemci.post(f"{M}/satislar/{x['id']}/iade", json={"odeme_turu": "nakit"}, headers=kb)
    assert y.status_code == 403 and _kod(y) == "iade_yetkisi_yok"
    await _ok(await istemci.put(f"{M}/ayarlar", json={"kasa_iade": True}, headers=d["b"]))
    await _ok(await istemci.post(f"{M}/satislar/{x['id']}/iade", json={"odeme_turu": "nakit"}, headers=kb))
    # Kasiyer kapalı kasanın satışını görmez
    await _ok(await istemci.post(f"{M}/kasa/{o['id']}/kapat", json={"sayilan_nakit": 50}, headers=kb))
    assert (await istemci.get(f"{M}/satislar/{x['id']}", headers=kb)).status_code == 404
    assert (await _ok(await istemci.get(f"{M}/satislar", headers=kb)))["items"] == []
    assert (await istemci.get(f"{M}/satislar/{x['id']}", headers=d["b"])).status_code == 200


async def test_kasa_kullanici_siniri(istemci, yonetici_basligi, db_oturumu):
    sahip = _e("sinir")
    await _modul(istemci, yonetici_basligi, sahip, kasa_kullanici_siniri=1, sube_siniri=2)
    b = _b(sahip)
    sube = await _ok(await istemci.post(f"{M}/konumlar", json={"ad": "İkinci"}, headers=b))
    meta = await _ok(await istemci.get(f"{M}/meta", headers=b))
    await _ok(await istemci.post(f"{M}/kasa/ac", json={"konum_id": meta["konumlar"][0]["id"]}, headers=b))
    kasiyer = _e("kasiyer")
    await _uye(db_oturumu, sahip, kasiyer, ["kasa"])
    y = await istemci.post(f"{M}/kasa/ac", json={"konum_id": sube["id"]}, headers=_b(kasiyer, sahip))
    assert y.status_code == 403 and _kod(y) == "kasa_kullanici_siniri"


async def test_musteri_izolasyonu(istemci, dukkan, yonetici_basligi):
    d = dukkan
    baska = _e("baska")
    await _modul(istemci, yonetici_basligi, baska)
    bb = _b(baska)
    assert (await istemci.get(f"{M}/urunler/{d['kahve']['id']}", headers=bb)).status_code == 404
    assert (await istemci.get(f"{M}/urunler/kod/4006381333931", headers=bb)).status_code == 404
    assert (await _ok(await istemci.get(f"{M}/urunler", headers=bb)))["items"] == []
    await _kasa_ac(istemci, {"b": bb, "konum": None})
    y = await istemci.post(f"{M}/satislar", json={"kalemler": [{"urun_id": d["kahve"]["id"], "adet": 1}], "odeme": {"tur": "nakit"}},
                           headers=bb)
    assert y.status_code == 404 and _kod(y) == "urun_yok"
    y = await istemci.put(f"{M}/urunler/{d['kahve']['id']}", json={"ad": "çalıntı"}, headers=bb)
    assert y.status_code == 404
    y = await istemci.post(f"{M}/hareketler", json={"tur": "giris", "konum_id": d["konum"], "kalemler": [{"urun_id": d["kahve"]["id"], "miktar": 1}]},
                           headers=bb)
    assert y.status_code == 404


async def test_yonetici_salt_okunur(istemci, dukkan, yonetici_basligi):
    d = dukkan
    h = await _ok(await istemci.get(f"{Y}/hesaplar", headers=yonetici_basligi))
    assert any(x["hesap_email"] == d["sahip"] and x["urun"] == 2 for x in h["items"])
    assert (await istemci.get(f"{Y}/meta", headers=yonetici_basligi)).status_code == 400
    meta = await _ok(await istemci.get(f"{Y}/meta?hesap={d['sahip']}", headers=yonetici_basligi))
    assert meta["salt_okunur"] is True and meta["yetki"]["ajans"] is True
    u = await _ok(await istemci.get(f"{Y}/urunler?hesap={d['sahip']}", headers=yonetici_basligi))
    assert len(u["items"]) == 2
    assert (await istemci.get(f"{Y}/raporlar/stok-degeri?hesap={d['sahip']}", headers=yonetici_basligi)).status_code == 200
    y = await istemci.post(f"{Y}/urunler?hesap={d['sahip']}", json={"ad": "x", "satis_fiyati": 1}, headers=yonetici_basligi)
    assert y.status_code in (404, 405)
    y = await istemci.get(f"{Y}/alicilar?hesap={d['sahip']}", headers=yonetici_basligi)
    assert y.status_code == 404


async def test_qr_menu_urunleriyle_ortak_kullanim(istemci, dukkan, yonetici_basligi, db_oturumu):
    from models.qr_menu import MenuKategorileri, MenuMagazalari, MenuUrunleri

    d = dukkan
    m = MenuMagazalari(hesap_email=d["sahip"], slug=f"pos-{uuid.uuid4().hex[:8]}", duzen="menu", ad="Kafe")
    db_oturumu.add(m)
    await db_oturumu.commit()
    kat = MenuKategorileri(magaza_id=m.id, ad="Sıcak içecekler")
    db_oturumu.add(kat)
    await db_oturumu.commit()
    latte = MenuUrunleri(magaza_id=m.id, kategori_id=kat.id, ad="Latte", fiyat=9500)
    cay = MenuUrunleri(magaza_id=m.id, kategori_id=kat.id, ad="Çay", fiyat=3000, indirimli_fiyat=2500)
    db_oturumu.add_all([latte, cay])
    await db_oturumu.commit()
    # QR menü modülü kapalıyken meta "qr_menu" yanlış; açınca doğru
    assert (await _ok(await istemci.get(f"{M}/meta", headers=d["b"])))["qr_menu"] is False
    y = await istemci.put(f"{MODUL}/musteri/{d['sahip']}/qr_menu", json={"acik": True}, headers=yonetici_basligi)
    assert y.status_code == 200
    assert (await _ok(await istemci.get(f"{M}/meta", headers=d["b"])))["qr_menu"] is True
    kaynak = (await _ok(await istemci.get(f"{M}/menu-kaynaklari", headers=d["b"])))["items"]
    assert kaynak == [{"id": m.id, "ad": "Kafe", "duzen": "menu", "slug": m.slug, "urun": 2, "bagli": 0}]
    r = await _ok(await istemci.post(f"{M}/menuden-aktar", json={"magaza_id": m.id}, headers=d["b"]))
    assert r["eklenen"] == 2
    r = await _ok(await istemci.post(f"{M}/menuden-aktar", json={"magaza_id": m.id}, headers=d["b"]))
    assert r == {"eklenen": 0, "guncellenen": 2, "sinir": 1000}
    liste = (await _ok(await istemci.get(f"{M}/urunler?ara=Latte", headers=d["b"])))["items"]
    pl = liste[0]
    assert pl["menu_urun_id"] == latte.id and pl["satis_fiyati"] == 9500 and pl["kategori"] == "Sıcak içecekler"
    assert pl["stok_takibi"] is False  # menü ürünü varsayılan stoksuz (hazırlanan içecek)
    pc = (await _ok(await istemci.get(f"{M}/urunler?ara=%C3%87ay", headers=d["b"])))["items"][0]
    assert pc["satis_fiyati"] == 2500
    # Stok takibi açılınca: stok bitince QR menüde "tükendi", gelince geri
    await _ok(await istemci.put(f"{M}/urunler/{pl['id']}", json={"stok_takibi": True}, headers=d["b"]))
    await _giris(istemci, d, pl["id"], 1)
    await _kasa_ac(istemci, d)
    await _ok(await _sat(istemci, d, [{"urun_id": pl["id"], "adet": 1}]))
    await db_oturumu.refresh(latte)
    assert latte.stokta_yok is True
    await _giris(istemci, d, pl["id"], 5)
    await db_oturumu.refresh(latte)
    assert latte.stokta_yok is False
    # Başka hesabın mağazası aktarılamaz
    baska = _e("baska")
    await _modul(istemci, yonetici_basligi, baska)
    y = await istemci.post(f"{M}/menuden-aktar", json={"magaza_id": m.id}, headers=_b(baska))
    assert y.status_code == 404


async def test_csv_ice_ve_disa_aktarma(istemci, dukkan):
    d = dukkan
    metin = ("Barkod;Ad;Kategori;Birim;Alış fiyatı;Satış fiyatı;KDV;Kritik eşik;Stok\n"
             "4006381333931;Filtre kahve (yeni);Kahve;adet;60;130;10;3;7\n"
             ";Tuz 1 kg;Bakkal;adet;8;15,90;1;;20\n"
             "1234567890123;Hatalı barkod;;adet;1;2;20;;\n"
             ";Pirinç;Bakkal;kg;30;45;1;;12,5\n")
    r = await _ok(await istemci.post(f"{M}/urunler/ice-aktar", files={"dosya": ("u.csv", metin.encode("utf-8"), "text/csv")},
                                     headers=d["b"]))
    assert r["eklenen"] == 2 and r["guncellenen"] == 1 and r["hata_sayisi"] == 1 and r["hatalar"][0]["satir"] == 4
    assert r["hatalar"][0]["kod"] == "barkod_kontrol_hanesi"
    k = await _ok(await istemci.get(f"{M}/urunler/{d['kahve']['id']}", headers=d["b"]))
    assert k["ad"] == "Filtre kahve (yeni)" and k["satis_fiyati"] == 13000 and k["stok"]["toplam"] == 7 and k["kritik_esik"] == 3
    pir = (await _ok(await istemci.get(f"{M}/urunler?ara=Pirin", headers=d["b"])))["items"][0]
    assert pir["birim"] == "kg" and pir["stok"]["toplam"] == 12.5 and pir["kdv_orani"] == 1
    disa = await istemci.get(f"{M}/urunler.csv", headers=d["b"])
    assert disa.status_code == 200 and disa.headers["content-type"].startswith("text/csv")
    satirlar = disa.text.lstrip("﻿").splitlines()
    assert satirlar[0] == "barkod;sku;ad;kategori;birim;alis_fiyati;satis_fiyati;kdv_orani;kritik_esik;stok"
    assert any(s.startswith("4006381333931;FK-1;Filtre kahve (yeni);Kahve;adet;60,00;130,00;10;3;7") for s in satirlar)
    y = await istemci.post(f"{M}/urunler/ice-aktar", files={"dosya": ("u.csv", b"x;y\n1;2\n", "text/csv")}, headers=d["b"])
    assert y.status_code == 400 and _kod(y) == "baslik_eksik"


async def test_fis_ve_fatura_pdf_mali_degil_ibaresi(istemci, dukkan):
    from services.pdf_belge import pdf_metni

    d = dukkan
    await _ok(await istemci.put(f"{M}/ayarlar", json={"firma_adi": "Köşe Kafe", "vergi_no": "1234567890", "fis_notu": "Yine bekleriz"},
                                headers=d["b"]))
    await _giris(istemci, d, d["kahve"]["id"], 3)
    await _kasa_ac(istemci, d)
    x = await _ok(await _sat(istemci, d, [{"urun_id": d["kahve"]["id"], "adet": 2}], {"tur": "karma", "kart": "100", "nakit_alinan": "200"}))
    assert x["kart"] == 10000 and x["nakit"] == 14000 and x["para_ustu"] == 6000 and x["odeme_turu"] == "karma"
    y = await istemci.get(f"{M}/satislar/{x['id']}/fis.pdf", headers=d["b"])
    assert y.status_code == 200 and y.content[:5] == b"%PDF-"
    metin = pdf_metni(y.content)
    assert "MALİ FİŞ DEĞİLDİR" in metin and "Köşe Kafe" in metin and x["no"] in metin
    assert (await istemci.get(f"{M}/satislar/{x['id']}/fatura.pdf", headers=d["b"])).status_code == 404
    y = await istemci.post(f"{M}/satislar/{x['id']}/fatura", json={"alici": {"ad": "Ali Veli Ltd.", "vergi_no": "9876543210",
                                                                             "vergi_dairesi": "Kadıköy"}, "kaydet": True}, headers=d["b"])
    f = await _ok(y)
    assert f["fatura_no"].startswith("SF-") and f["fatura_alici"]["ad"] == "Ali Veli Ltd." and f["alici_id"]
    assert (await istemci.post(f"{M}/satislar/{x['id']}/fatura", json={"alici": {"ad": "x"}}, headers=d["b"])).status_code == 409
    y = await istemci.get(f"{M}/satislar/{x['id']}/fatura.pdf", headers=d["b"])
    metin = pdf_metni(y.content)
    assert "Ali Veli Ltd." in metin and "e-Arşiv" in metin and f["fatura_no"] in metin
    al = await _ok(await istemci.get(f"{M}/alicilar?ara=ali", headers=d["b"]))
    assert [a["ad"] for a in al["items"]] == ["Ali Veli Ltd."]
    y = await istemci.post(f"{M}/alicilar", json={"ad": "Y", "vergi_no": "12"}, headers=d["b"])
    assert y.status_code == 400 and _kod(y) == "vergi_no_gecersiz"


async def test_istemci_kimligi_tekrar_gonderimde_tek_satis(istemci, dukkan):
    d = dukkan
    await _giris(istemci, d, d["kahve"]["id"], 5)
    await _kasa_ac(istemci, d)
    kimlik = uuid.uuid4().hex
    x1 = await _ok(await _sat(istemci, d, [{"urun_id": d["kahve"]["id"], "adet": 1}], istemci_kimligi=kimlik))
    x2 = await _ok(await _sat(istemci, d, [{"urun_id": d["kahve"]["id"], "adet": 1}], istemci_kimligi=kimlik))
    assert x1["id"] == x2["id"] and x2["tekrar"] is True and await _stok(istemci, d, d["kahve"]["id"]) == 4
    # Fiyat değiştiyse kasiyer uyarılır (beklenen toplam)
    y = await _sat(istemci, d, [{"urun_id": d["kahve"]["id"], "adet": 1}], beklenen_toplam="100")
    assert y.status_code == 409 and _kod(y) == "toplam_degisti" and y.json()["detail"]["toplam"] == 12000
    on = await _ok(await istemci.post(f"{M}/satislar/onizle", json={"kalemler": [{"urun_id": d["kahve"]["id"], "adet": 2}],
                                                                     "toplam_indirim": "4"}, headers=d["b"]))
    assert on["toplam"] == 23600 and on["toplam_indirim"] == 400


async def test_olay_katalogu_ve_baglam(istemci, dukkan, db_oturumu):
    from services import otomasyon, otomasyon_kural, webhook

    assert {"pos.satis", "stok.kritik"} <= set(webhook.OLAY_SOZLUGU)
    assert webhook.OLAY_SOZLUGU["pos.satis"].varsayilan is False
    musteri = {o["anahtar"] for o in otomasyon_kural.olay_katalogu(False)}
    assert {"pos.satis", "stok.kritik"} <= musteri
    d = dukkan
    await _giris(istemci, d, d["kahve"]["id"], 3)
    await _kasa_ac(istemci, d)
    x = await _ok(await _sat(istemci, d, [{"urun_id": d["kahve"]["id"], "adet": 1}], musteri_ad="Gizli Kişi"))
    b = await otomasyon.baglam_kur(db_oturumu, "pos.satis", {"satis_id": x["id"], "kalem_sayisi": 1}, d["sahip"], False)
    assert b["satis"]["toplam"] == 120.0 and b["satis"]["konum"] == "Merkez" and "Gizli" not in json.dumps(b, ensure_ascii=False)
    assert await otomasyon.baglam_kur(db_oturumu, "pos.satis", {"satis_id": x["id"]}, "baska@pos.dev", False) is None
    b = await otomasyon.baglam_kur(db_oturumu, "stok.kritik", {"urun_id": d["kahve"]["id"], "miktar": 2}, d["sahip"], False)
    assert b["stok"]["ad"] == "Filtre kahve" and b["stok"]["esik"] == 2
    # Örnek bağlam şemayla uyumlu
    for tur in ("pos.satis", "stok.kritik"):
        ornek = otomasyon_kural.ornek_baglam(tur, False)
        for alan in otomasyon_kural.sema(tur, False):
            ns, ad = alan["yol"].split(".", 1)
            assert ad in ornek[ns], (tur, alan["yol"])
