"""Faz 3K — Kaynaklar: tohumlama (idempotent, düzenlenmiş/silinmiş kayda
dokunmuyor), herkese açık liste/ayrıntı (yalnız yayında, arama, kategori,
dil, 404, önbellek başlığı, derleme biçimi), yönetici CRUD yetkisi,
bağlantı doğrulaması ve silmenin çöp kutusuna düşmesi.

Test veritabanı oturum boyunca ortak: her test kendi benzersiz slug'larıyla
çalışıyor, sayımlar yalnız kendi kayıtları üzerinden yapılıyor.
"""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

A = "/api/v1/kaynaklar"
Y = "/api/v1/kaynaklar/yonetim"
GERCEK_TOHUM = Path(__file__).resolve().parents[2] / "data" / "kaynaklar_tohum.json"


def _ek() -> str:
    return uuid.uuid4().hex[:8]


def _girdi(slug: str, **ek) -> dict:
    veri = {
        "slug": slug,
        "kategori": "ajan",
        "baslik": f"Deneme aracı {slug}",
        "ozet": "Türkçe kısa özet.",
        "aciklama": "Birinci paragraf.\n\nİkinci paragraf.",
        "adimlar": ["Kur", "Çalıştır"],
        "ceviriler": {"en": {"baslik": f"Test tool {slug}", "ozet": "English summary.", "adimlar": ["Install", "Run"]}},
        "etiketler": ["Otomasyon", "otomasyon", " Açık Kaynak "],
        "baglanti": "https://github.com/ornek/arac",
        "baglanti_turu": "github",
        "lisans": "MIT",
        "ucretsiz": True,
        "acik_kaynak": True,
        "one_cikan": False,
        "sira": 50,
        "yayinda": True,
        "dogrulama_tarihi": "2026-10-01",
    }
    veri.update(ek)
    return veri


async def _ekle(istemci, yonetici_basligi, slug=None, **ek) -> dict:
    y = await istemci.post(Y, json=_girdi(slug or f"arac-{_ek()}", **ek), headers=yonetici_basligi)
    assert y.status_code == 201, y.text
    return y.json()


def _tohum_dosyasi(tmp_path: Path, kaynaklar: list) -> Path:
    veri = json.loads(GERCEK_TOHUM.read_text(encoding="utf-8"))
    veri["kaynaklar"] = kaynaklar
    yol = tmp_path / "tohum.json"
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return yol


def _tohum_kaydi(slug: str, **ek) -> dict:
    kayit = {
        "slug": slug,
        "kategori": "video-ses",
        "baslik": {"tr": f"Tohum {slug}", "en": f"Seed {slug}"},
        "ozet": {"tr": "Tohum özeti", "de": "Saat-Zusammenfassung"},
        "aciklama": {"tr": "Açıklama"},
        "adimlar": {"tr": ["Bir", "İki"], "en": ["One", "Two"]},
        "etiketler": ["video"],
        "baglanti": "https://example.com/arac",
        "baglanti_turu": "site",
        "lisans": None,
        "ucretsiz": True,
        "acik_kaynak": False,
        "youtube_short": None,
        "one_cikan": False,
        "sira": 10,
        "dogrulama_tarihi": "2026-10-01",
    }
    kayit.update(ek)
    return kayit


async def _kaynak_satiri(db, slug):
    from models.kaynaklar import Kaynaklar

    return (
        await db.execute(select(Kaynaklar).where(Kaynaklar.slug == slug).execution_options(populate_existing=True))
    ).scalars().first()


# ---------------------------------------------------------------------------
# Tohum dosyası
# ---------------------------------------------------------------------------
def test_gercek_tohum_dosyasi_semaya_uygun():
    """Depodaki tohum dosyası (gerçeği sonra konacak) yönetici doğrulamasından geçmeli."""
    from services import kaynaklar as servis

    veri = json.loads(GERCEK_TOHUM.read_text(encoding="utf-8"))
    anahtarlar = [k["anahtar"] for k in veri["kategoriler"]]
    assert set(servis.VARSAYILAN_KATEGORILER) <= set(anahtarlar)
    for k in veri["kategoriler"]:
        assert set(k["ad"]) == set(servis.DILLER), k["anahtar"]
    sluglar = [k["slug"] for k in veri["kaynaklar"]]
    assert sluglar and len(sluglar) == len(set(sluglar))
    for kayit in veri["kaynaklar"]:
        servis.girdiyi_dogrula(servis.tohum_girdisi(kayit), anahtarlar)
        assert kayit["baglanti"].startswith("https://")


# ---------------------------------------------------------------------------
# Tohumlama
# ---------------------------------------------------------------------------
async def test_tohumlama_idempotent(db_oturumu, tmp_path):
    from models.kaynaklar import Kaynaklar
    from services.kaynaklar import tohumla

    a, b = f"tohum-a-{_ek()}", f"tohum-b-{_ek()}"
    yol = _tohum_dosyasi(tmp_path, [_tohum_kaydi(a), _tohum_kaydi(b, one_cikan=True)])
    ilk = await tohumla(db_oturumu, yol)
    assert sorted(ilk["eklenen"]) == sorted([a, b])
    ikinci = await tohumla(db_oturumu, yol)
    assert ikinci["eklenen"] == []
    sayi = (await db_oturumu.execute(select(func.count()).select_from(Kaynaklar).where(Kaynaklar.slug.in_([a, b])))).scalar()
    assert sayi == 2
    satir = await _kaynak_satiri(db_oturumu, a)
    assert satir.baslik == f"Tohum {a}"
    cev = json.loads(satir.ceviriler)
    assert cev["en"]["baslik"] == f"Seed {a}" and cev["en"]["adimlar"] == ["One", "Two"]
    assert cev["de"] == {"ozet": "Saat-Zusammenfassung"}
    assert satir.yayinda is True


async def test_tohumlama_duzenlenmis_kaydi_ezmez_silineni_geri_getirmez(
    istemci, db_oturumu, tmp_path, yonetici_basligi
):
    from services.kaynaklar import tohumla

    a, b = f"tohum-duz-{_ek()}", f"tohum-sil-{_ek()}"
    yol = _tohum_dosyasi(tmp_path, [_tohum_kaydi(a), _tohum_kaydi(b)])
    await tohumla(db_oturumu, yol)

    liste = (await istemci.get(Y, headers=yonetici_basligi)).json()["kaynaklar"]
    ka = next(k for k in liste if k["slug"] == a)
    kb = next(k for k in liste if k["slug"] == b)
    y = await istemci.put(f"{Y}/{ka['id']}", json={**ka, "baslik": "Panelde düzenlendi"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert (await istemci.delete(f"{Y}/{kb['id']}", headers=yonetici_basligi)).status_code == 200

    # Tohum dosyası güncellendi: a'nın metni değişti, yeni bir c eklendi.
    c = f"tohum-yeni-{_ek()}"
    yol = _tohum_dosyasi(
        tmp_path, [_tohum_kaydi(a, baslik={"tr": "Tohumdaki yeni başlık"}), _tohum_kaydi(b), _tohum_kaydi(c)]
    )
    sonuc = await tohumla(db_oturumu, yol)
    assert sonuc["eklenen"] == [c]
    assert (await _kaynak_satiri(db_oturumu, a)).baslik == "Panelde düzenlendi"
    assert await _kaynak_satiri(db_oturumu, b) is None


async def test_tohumlama_elle_acilmis_ayni_slugi_ezmez_hatali_kaydi_atlar(
    istemci, db_oturumu, tmp_path, yonetici_basligi
):
    from services.kaynaklar import tohumla

    elle = await _ekle(istemci, yonetici_basligi, baslik="Elle açıldı")
    bozuk = f"tohum-bozuk-{_ek()}"
    yol = _tohum_dosyasi(
        tmp_path,
        [_tohum_kaydi(elle["slug"]), _tohum_kaydi(bozuk, baglanti="javascript:alert(1)")],
    )
    sonuc = await tohumla(db_oturumu, yol)
    assert sonuc["eklenen"] == [] and sonuc["atlanan"] == [bozuk]
    assert (await _kaynak_satiri(db_oturumu, elle["slug"])).baslik == "Elle açıldı"
    assert await _kaynak_satiri(db_oturumu, bozuk) is None


async def test_tohum_dosyasi_yoksa_bos_doner(db_oturumu, tmp_path):
    from services.kaynaklar import tohumla

    assert await tohumla(db_oturumu, tmp_path / "yok.json") == {"eklenen": [], "atlanan": []}


# ---------------------------------------------------------------------------
# Herkese açık uçlar
# ---------------------------------------------------------------------------
async def test_liste_yalniz_yayindakiler_ve_onbellek_basligi(istemci, yonetici_basligi):
    acik = await _ekle(istemci, yonetici_basligi)
    taslak = await _ekle(istemci, yonetici_basligi, yayinda=False)
    y = await istemci.get(A)
    assert y.status_code == 200
    assert "max-age=300" in y.headers.get("cache-control", "")
    sluglar = {k["slug"] for k in y.json()["kaynaklar"]}
    assert acik["slug"] in sluglar and taslak["slug"] not in sluglar
    kart = next(k for k in y.json()["kaynaklar"] if k["slug"] == acik["slug"])
    # Liste hafif: açıklama ve adımlar yok.
    assert "aciklama" not in kart and "adimlar" not in kart and "baglanti" not in kart
    assert kart["etiketler"] == ["otomasyon", "açık kaynak"]
    kat = {c["anahtar"]: c for c in y.json()["kategoriler"]}
    assert kat["ajan"]["sayi"] >= 1 and kat["ajan"]["ad"] == _kategori_adi("ajan")


async def test_liste_arama_kategori_ve_dil(istemci, yonetici_basligi):
    ek = _ek()
    video = await _ekle(
        istemci, yonetici_basligi, kategori="video-ses", baslik=f"Kısa video {ek}", etiketler=["shorts"]
    )
    ajan = await _ekle(istemci, yonetici_basligi, kategori="ajan", baslik=f"İş akışı ajanı {ek}")

    y = (await istemci.get(A, params={"kategori": "video-ses"})).json()
    sluglar = {k["slug"] for k in y["kaynaklar"]}
    assert video["slug"] in sluglar and ajan["slug"] not in sluglar

    # Arama: aksansız/küçük harf eşleşir ve her kelime geçmeli.
    y = (await istemci.get(A, params={"q": f"is AKISI {ek}"})).json()
    assert [k["slug"] for k in y["kaynaklar"]] == [ajan["slug"]]
    y = (await istemci.get(A, params={"q": f"shorts {ek}"})).json()
    assert [k["slug"] for k in y["kaynaklar"]] == [video["slug"]]
    y = (await istemci.get(A, params={"q": f"yok-boyle-bir-sey-{ek}"})).json()
    assert y["kaynaklar"] == [] and y["toplam"] == 0

    # Dil: çeviri varsa o, yoksa Türkçe; kategori adı da çevrili.
    y = (await istemci.get(A, params={"dil": "en", "q": ek})).json()
    kart = next(k for k in y["kaynaklar"] if k["slug"] == video["slug"])
    assert kart["baslik"] == f"Test tool {video['slug']}" and kart["ozet"] == "English summary."
    assert y["dil"] == "en"
    assert next(c for c in y["kategoriler"] if c["anahtar"] == "video-ses")["ad"] == _kategori_adi("video-ses", "en")
    y = (await istemci.get(A, params={"dil": "de", "q": ek})).json()
    kart = next(k for k in y["kaynaklar"] if k["slug"] == video["slug"])
    assert kart["baslik"] == f"Kısa video {ek}"
    # Bilinmeyen dil Türkçeye düşer.
    assert (await istemci.get(A, params={"dil": "xx"})).json()["dil"] == "tr"


async def test_liste_siralama_one_cikan_once(istemci, yonetici_basligi):
    ek = _ek()
    sonra = await _ekle(istemci, yonetici_basligi, slug=f"a-sira-{ek}", sira=1, baslik=f"sira {ek} a")
    once = await _ekle(istemci, yonetici_basligi, slug=f"b-sira-{ek}", sira=99, one_cikan=True, baslik=f"sira {ek} b")
    y = (await istemci.get(A, params={"q": f"sira {ek}"})).json()
    assert [k["slug"] for k in y["kaynaklar"]] == [once["slug"], sonra["slug"]]


async def test_ayrinti_ilgili_ve_404(istemci, yonetici_basligi):
    ek = _ek()
    ana = await _ekle(istemci, yonetici_basligi, kategori="model-api", slug=f"ana-{ek}")
    ilgililer = [await _ekle(istemci, yonetici_basligi, kategori="model-api", slug=f"ilgili-{i}-{ek}", sira=i) for i in range(4)]
    baska = await _ekle(istemci, yonetici_basligi, kategori="rehber", slug=f"baska-{ek}")
    taslak = await _ekle(istemci, yonetici_basligi, kategori="model-api", slug=f"taslak-{ek}", yayinda=False, sira=0)

    y = await istemci.get(f"{A}/{ana['slug']}", params={"dil": "en"})
    assert y.status_code == 200
    assert "max-age=300" in y.headers.get("cache-control", "")
    g = y.json()
    k = g["kaynak"]
    assert k["baslik"] == f"Test tool {ana['slug']}"
    assert k["aciklama"] == "Birinci paragraf.\n\nİkinci paragraf."  # çevirisi yok → Türkçe
    assert k["adimlar"] == ["Install", "Run"]
    assert k["baglanti"] == "https://github.com/ornek/arac" and k["lisans"] == "MIT"
    assert k["kategori_adi"] == _kategori_adi("model-api", "en") and k["dogrulama_tarihi"] == "2026-10-01"
    ilgili = [i["slug"] for i in g["ilgili"]]
    assert len(ilgili) == 3 and ana["slug"] not in ilgili
    assert baska["slug"] not in ilgili and taslak["slug"] not in ilgili
    assert set(ilgili) <= {i["slug"] for i in ilgililer}

    assert (await istemci.get(f"{A}/yok-{ek}")).status_code == 404
    y = await istemci.get(f"{A}/{taslak['slug']}")
    assert y.status_code == 404 and y.json()["detail"]["kod"] == "bulunamadi"


async def test_derleme_bicimi_yedi_dil(istemci, yonetici_basligi):
    k = await _ekle(istemci, yonetici_basligi)
    taslak = await _ekle(istemci, yonetici_basligi, yayinda=False)
    y = await istemci.get(A, params={"bicim": "tam"})
    assert y.status_code == 200
    g = y.json()
    assert g["surum"] == 1 and any(c["anahtar"] == "ajan" and c["ad"]["ar"] for c in g["kategoriler"])
    kayit = next(x for x in g["kaynaklar"] if x["slug"] == k["slug"])
    assert kayit["baslik"] == {"tr": k["baslik"], "en": f"Test tool {k['slug']}"}
    assert kayit["adimlar"] == {"tr": ["Kur", "Çalıştır"], "en": ["Install", "Run"]}
    assert kayit["baglanti"] == "https://github.com/ornek/arac" and "yayinda" not in kayit
    assert taslak["slug"] not in {x["slug"] for x in g["kaynaklar"]}


# ---------------------------------------------------------------------------
# Yönetici
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "yontem,yol",
    [("GET", Y), ("POST", Y), ("PUT", f"{Y}/1"), ("PATCH", f"{Y}/1"), ("DELETE", f"{Y}/1"), ("POST", f"{Y}/sirala")],
)
async def test_yonetici_uclari_401_403(istemci, musteri_basligi, yontem, yol):
    govde = {"sira": [1]} if yol.endswith("sirala") else {"yayinda": True}
    y = await istemci.request(yontem, yol, json=govde if yontem in ("POST", "PUT", "PATCH") else None)
    assert y.status_code == 401
    y = await istemci.request(
        yontem, yol, json=govde if yontem in ("POST", "PUT", "PATCH") else None, headers=musteri_basligi()
    )
    assert y.status_code == 403


async def test_yonetici_crud_ve_hizli_anahtarlar(istemci, yonetici_basligi):
    k = await _ekle(istemci, yonetici_basligi)
    assert k["etiketler"] == ["otomasyon", "açık kaynak"] and k["adimlar"] == ["Kur", "Çalıştır"]
    assert k["ceviriler"]["en"]["baslik"].startswith("Test tool")

    # Liste: taslaklar da dahil; `yonetim` yolu /{slug}'a düşmüyor.
    taslak = await _ekle(istemci, yonetici_basligi, yayinda=False)
    y = await istemci.get(Y, headers=yonetici_basligi)
    assert y.status_code == 200
    sluglar = {x["slug"] for x in y.json()["kaynaklar"]}
    assert {k["slug"], taslak["slug"]} <= sluglar
    assert any(c["anahtar"] == "rehber" for c in y.json()["kategoriler"])

    # Tam güncelleme (slug değişebilir).
    yeni_slug = f"yeni-{_ek()}"
    y = await istemci.put(
        f"{Y}/{k['id']}",
        json={**_girdi(yeni_slug), "ceviriler": {}, "youtube_short": "https://youtube.com/shorts/abc123"},
        headers=yonetici_basligi,
    )
    assert y.status_code == 200, y.text
    assert y.json()["slug"] == yeni_slug and y.json()["ceviriler"] == {}
    assert y.json()["youtube_short"] == "https://youtube.com/shorts/abc123"
    assert (await istemci.get(f"{A}/{yeni_slug}")).status_code == 200

    # Yayından kaldır → herkese açık 404; öne çıkar + sıra.
    y = await istemci.patch(f"{Y}/{k['id']}", json={"yayinda": False}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["yayinda"] is False
    assert (await istemci.get(f"{A}/{yeni_slug}")).status_code == 404
    y = await istemci.patch(f"{Y}/{k['id']}", json={"one_cikan": True, "sira": 7}, headers=yonetici_basligi)
    assert y.json()["one_cikan"] is True and y.json()["sira"] == 7
    y = await istemci.patch(f"{Y}/{k['id']}", json={"baslik": "olmaz"}, headers=yonetici_basligi)
    assert y.status_code == 400
    y = await istemci.patch(f"{Y}/{k['id']}", json={"yayinda": "evet"}, headers=yonetici_basligi)
    assert y.status_code == 400

    # Sıralama.
    y = await istemci.post(f"{Y}/sirala", json={"sira": [taslak["id"], k["id"]]}, headers=yonetici_basligi)
    assert y.status_code == 200
    liste = {x["id"]: x for x in (await istemci.get(Y, headers=yonetici_basligi)).json()["kaynaklar"]}
    assert liste[taslak["id"]]["sira"] == 10 and liste[k["id"]]["sira"] == 20

    assert (await istemci.put(f"{Y}/999999", json=_girdi(f"x-{_ek()}"), headers=yonetici_basligi)).status_code == 404
    assert (await istemci.delete(f"{Y}/999999", headers=yonetici_basligi)).status_code == 404


async def test_slug_kurallari(istemci, yonetici_basligi):
    k = await _ekle(istemci, yonetici_basligi)
    y = await istemci.post(Y, json=_girdi(k["slug"]), headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "slug_var"
    diger = await _ekle(istemci, yonetici_basligi)
    y = await istemci.put(f"{Y}/{diger['id']}", json=_girdi(k["slug"]), headers=yonetici_basligi)
    assert y.status_code == 409
    for kotu in ("yonetim", "Büyük Harf", "alt_cizgi", "-bas", "son-", ""):
        y = await istemci.post(Y, json=_girdi(kotu), headers=yonetici_basligi)
        assert y.status_code == 400, kotu
        assert y.json()["detail"]["alan"] == "slug"


@pytest.mark.parametrize(
    "alan,deger,kod",
    [
        ("baglanti", "javascript:alert(1)", "gecersiz_baglanti"),
        ("baglanti", "ftp://ornek.com/dosya", "gecersiz_baglanti"),
        ("baglanti", "https://", "gecersiz_baglanti"),
        ("baglanti", "https://ornek.com/bir yol", "gecersiz_baglanti"),
        ("baglanti", "https://kullanici:parola@ornek.com", "gecersiz_baglanti"),
        ("baglanti", "//ornek.com", "gecersiz_baglanti"),
        ("baglanti", "", "baglanti_gerekli"),
        ("youtube_short", "https://vimeo.com/123", "gecersiz_youtube"),
        ("youtube_short", "javascript:alert(1)", "gecersiz_baglanti"),
        ("kategori", "uydurma", "gecersiz_kategori"),
        ("baglanti_turu", "ftp", "gecersiz_baglanti_turu"),
        ("baslik", "", "baslik_gerekli"),
        ("ozet", "x" * 301, "cok_uzun"),
        ("adimlar", ["x"] * 13, "cok_uzun"),
        ("ceviriler", {"fr": {"baslik": "Bonjour"}}, "gecersiz_dil"),
        ("dogrulama_tarihi", "dün", "gecersiz_tarih"),
    ],
)
async def test_girdi_dogrulamasi(istemci, yonetici_basligi, alan, deger, kod):
    y = await istemci.post(Y, json=_girdi(f"dogrula-{_ek()}", **{alan: deger}), headers=yonetici_basligi)
    assert y.status_code == 400, y.text
    assert y.json()["detail"]["kod"] == kod


async def test_http_baglanti_kabul(istemci, yonetici_basligi):
    k = await _ekle(istemci, yonetici_basligi, baglanti="http://ornek.com/yol?a=1", youtube_short="https://youtu.be/abc")
    assert k["baglanti"] == "http://ornek.com/yol?a=1" and k["youtube_short"] == "https://youtu.be/abc"


async def test_silme_cop_kutusuna_gider_ve_geri_alinir(istemci, db_oturumu, yonetici_basligi):
    from models.cop_kutusu import CopKutusu

    k = await _ekle(istemci, yonetici_basligi, baslik="Çöpe gidecek kaynak")
    y = await istemci.delete(f"{Y}/{k['id']}", headers=yonetici_basligi)
    assert y.status_code == 200
    assert (await istemci.get(f"{A}/{k['slug']}")).status_code == 404
    cop = (
        await db_oturumu.execute(
            select(CopKutusu).where(CopKutusu.tablo == "kaynaklar", CopKutusu.kayit_id == str(k["id"]))
        )
    ).scalars().first()
    assert cop is not None and cop.etiket == "Çöpe gidecek kaynak" and cop.geri_alindi is False
    veri = json.loads(cop.veri)
    assert veri["slug"] == k["slug"] and json.loads(veri["ceviriler"])["en"]["ozet"] == "English summary."

    y = await istemci.post(f"/api/v1/cop-kutusu/{cop.id}/geri-al", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    y = await istemci.get(f"{A}/{k['slug']}", params={"dil": "en"})
    assert y.status_code == 200 and y.json()["kaynak"]["ozet"] == "English summary."
    assert y.json()["kaynak"]["dogrulama_tarihi"] == "2026-10-01"


def _kategori_adi(anahtar, dil="tr"):
    """Kategori adı tohum dosyasından (içerik değişince test kırılmasın)."""
    import json, pathlib
    veri = json.loads((pathlib.Path(__file__).resolve().parents[2] / "data" / "kaynaklar_tohum.json").read_text(encoding="utf-8"))
    return next(k["ad"][dil] for k in veri["kategoriler"] if k["anahtar"] == anahtar)
