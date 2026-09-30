"""Marketplace ürün çevirileri: katalog, açılış doldurucusu, entity ve açık uç."""
import json

from scripts.marketplace_ceviri_doldur import ALANLAR, ceviri_uret, doldur, katalogu_yukle

KATALOG = katalogu_yukle()
CANLI_SLUGLAR = {
    "kartvizit-web-sitesi",
    "ozel-yazilim-eticaret-sitesi",
    "kurumsal-urun-tanitim-sitesi",
    "konfiguratorlu-urun-sitesi",
}
TURKCE_HARF = set("ğşıİĞŞ")


def test_alti_dil_ve_canli_urunlerin_hepsi_katalogda():
    assert set(KATALOG) == {"en", "de", "ru", "zh", "hi", "ar"}
    for dil, urunler in KATALOG.items():
        assert set(urunler) == CANLI_SLUGLAR, dil
        for slug, alanlar in urunler.items():
            assert set(alanlar) <= set(ALANLAR)
            for a in ("title", "summary", "description", "features", "badge"):
                assert alanlar.get(a), (dil, slug, a)
            # Özellik satır sayısı Türkçe ile aynı (kartta satır satır çıkıyor).
            assert len(alanlar["features"].split("\n")) == 5
            # Türkçeye özgü harf kalmamış olmalı.
            metin = "".join(alanlar.values())
            assert not (TURKCE_HARF & set(metin)), (dil, slug)


def test_slug_eslesmesi_ve_bilinmeyen_urun():
    c = ceviri_uret("kartvizit-web-sitesi", KATALOG)
    assert c["en"]["title"] == "Business Card Website"
    assert c["de"]["badge"] and c["ar"]["summary"]
    assert ceviri_uret("boyle-bir-urun-yok", KATALOG) is None
    assert ceviri_uret(None, KATALOG) is None


async def _urun_ekle(istemci, baslik, slug, yonetici_basligi, **ek):
    y = await istemci.post(
        "/api/v1/entities/marketplace_items",
        json={"title": baslik, "slug": slug, "category": "website", "published": True, **ek},
        headers=yonetici_basligi,
    )
    assert y.status_code == 201, y.text
    return y.json()


async def test_doldurucu_yalniz_bos_satirlari_doldurur(istemci, db_oturumu, yonetici_basligi):
    from models.marketplace_items import Marketplace_items

    bos = await _urun_ekle(istemci, "Kartvizit Web Sitesi", "kartvizit-web-sitesi", yonetici_basligi)
    elle = await _urun_ekle(
        istemci,
        "Konfigüratörlü Ürün Sitesi",
        "konfiguratorlu-urun-sitesi",
        yonetici_basligi,
        ceviriler={"en": {"title": "Elle düzeltildi"}},
    )
    bilinmeyen = await _urun_ekle(istemci, "Yeni Ürün", "yeni-urun-xyz", yonetici_basligi)

    await doldur(db_oturumu)
    # İkinci çalıştırma hiçbir şeyi değiştirmemeli (idempotent).
    assert await doldur(db_oturumu) == 0

    satirlar = {
        s.id: s
        for s in (await db_oturumu.execute(Marketplace_items.__table__.select())).fetchall()
    }
    assert json.loads(satirlar[bos["id"]].ceviriler)["en"]["title"] == "Business Card Website"
    assert json.loads(satirlar[elle["id"]].ceviriler) == {"en": {"title": "Elle düzeltildi"}}
    assert satirlar[bilinmeyen["id"]].ceviriler is None


async def test_entity_ucu_ceviriyi_sozluk_olarak_yazar_ve_okur(istemci, yonetici_basligi):
    u = await _urun_ekle(
        istemci, "Deneme", "deneme-ceviri", yonetici_basligi, ceviriler={"de": {"title": "Versuch"}}
    )
    assert u["ceviriler"] == {"de": {"title": "Versuch"}}

    # Kısmi güncelleme: yalnız çeviri değişiyor, başlık korunuyor.
    y = await istemci.put(
        f"/api/v1/entities/marketplace_items/{u['id']}",
        json={"ceviriler": {"de": {"title": "Test"}, "en": {"summary": "Short"}}},
        headers=yonetici_basligi,
    )
    assert y.status_code == 200, y.text
    assert y.json()["title"] == "Deneme"
    assert y.json()["ceviriler"]["en"]["summary"] == "Short"

    # Toplu güncelleme de sözlüğü metne çevirip yazabilmeli.
    y = await istemci.put(
        "/api/v1/entities/marketplace_items/batch",
        json={"items": [{"id": u["id"], "updates": {"ceviriler": {"ar": {"title": "تجربة"}}}}]},
        headers=yonetici_basligi,
    )
    assert y.status_code == 200, y.text
    assert y.json()[0]["ceviriler"] == {"ar": {"title": "تجربة"}}

    liste = await istemci.get("/api/v1/entities/marketplace_items?limit=200", headers=yonetici_basligi)
    kayit = next(i for i in liste.json()["items"] if i["id"] == u["id"])
    assert kayit["ceviriler"] == {"ar": {"title": "تجربة"}}


async def test_acik_uc_ceviriyi_dondurur_taslagi_dondurmez(istemci, yonetici_basligi):
    yayinda = await _urun_ekle(
        istemci, "Açık Ürün", "acik-urun", yonetici_basligi, ceviriler={"en": {"title": "Open product"}}
    )
    taslak = await _urun_ekle(
        istemci, "Taslak Ürün", "taslak-urun", yonetici_basligi, published=False, ceviriler={"en": {"title": "Draft"}}
    )
    y = await istemci.get("/api/v1/marketplace")
    assert y.status_code == 200
    ogeler = {i["id"]: i for i in y.json()["items"]}
    assert ogeler[yayinda["id"]]["ceviriler"] == {"en": {"title": "Open product"}}
    assert taslak["id"] not in ogeler


async def test_bozuk_ceviri_metni_uclari_dusurmez(istemci, db_oturumu, yonetici_basligi):
    from models.marketplace_items import Marketplace_items

    u = await _urun_ekle(istemci, "Bozuk", "bozuk-ceviri", yonetici_basligi)
    satir = await db_oturumu.get(Marketplace_items, u["id"])
    satir.ceviriler = "{bozuk json"
    await db_oturumu.commit()

    y = await istemci.get("/api/v1/marketplace")
    assert y.status_code == 200
    assert next(i for i in y.json()["items"] if i["id"] == u["id"])["ceviriler"] is None


async def test_yetkisiz_ceviri_yazamaz(istemci, musteri_basligi, yonetici_basligi):
    u = await _urun_ekle(istemci, "Korumalı", "korumali-urun", yonetici_basligi)
    y = await istemci.put(
        f"/api/v1/entities/marketplace_items/{u['id']}", json={"ceviriler": {"en": {"title": "x"}}}
    )
    assert y.status_code in (401, 403)
    y = await istemci.put(
        f"/api/v1/entities/marketplace_items/{u['id']}",
        json={"ceviriler": {"en": {"title": "x"}}},
        headers=musteri_basligi(),
    )
    assert y.status_code == 403
