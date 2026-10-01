"""Modül kaydı (Faz 1F) testleri.

Veritabanı oturum boyunca paylaşılıyor; her test kendi benzersiz müşteri
e-postasıyla çalışıyor.
"""

import json
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

KOK = Path(__file__).resolve().parents[3]  # app/
ON_YUZ = KOK / "frontend" / "src"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
YONETIM = "/api/v1/moduller"


def _eposta(on: str = "modul") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


def _tab_birlesimi(dosya: Path) -> set:
    """`type Tab = 'a' | 'b' ...;` birleşimindeki anahtarlar."""
    metin = dosya.read_text(encoding="utf-8")
    eslesme = re.search(r"type Tab\s*=\s*([^;]+);", metin)
    assert eslesme, f"{dosya.name}: type Tab bulunamadı"
    return set(re.findall(r"'([A-Za-z0-9_]+)'", eslesme.group(1)))


def _ek_paket(dil: str) -> dict:
    return json.loads((ON_YUZ / "i18n" / "ek" / "modul" / f"{dil}.json").read_text(encoding="utf-8"))["modul"]


async def _ayarla(istemci, baslik, eposta, anahtar, beklenen=200, **govde):
    yanit = await istemci.put(f"{YONETIM}/musteri/{eposta}/{anahtar}", json=govde, headers=baslik)
    assert yanit.status_code == beklenen, yanit.text
    return yanit.json()


def _modul(yanit: dict, anahtar: str) -> dict:
    return next(m for m in yanit["moduller"] if m["anahtar"] == anahtar)


# ---------------------------------------------------------------------------
# Manifest tutarlılığı
# ---------------------------------------------------------------------------


def test_manifest_ic_tutarlilik():
    from core import moduller as mf

    assert mf.manifest_hatalari() == []
    anahtarlar = [m.anahtar for m in mf.MODULLER]
    assert len(anahtarlar) == len(set(anahtarlar))
    for m in mf.MODULLER:
        for b in m.bagimliliklar:
            assert b in mf.MODUL_SOZLUGU, (m.anahtar, b)


def test_cekirdek_moduller_belirtilen_bes_modul():
    from core import moduller as mf

    assert {m.anahtar for m in mf.MODULLER if m.cekirdek} == {
        "projeler", "faturalar", "destek", "bildirimler", "profil",
    }
    assert all(m.varsayilan_acik for m in mf.MODULLER if m.cekirdek)


def test_bugunku_paneller_modul_olarak_tanimli_ve_varsayilan_acik():
    from core import moduller as mf

    for anahtar in ("projeler", "faturalar", "destek", "raporlar", "sitem", "site_analizi",
                    "krediler", "bildirimler", "islem", "denetim", "profil"):
        m = mf.MODUL_SOZLUGU[anahtar]
        assert m.varsayilan_acik, anahtar
        assert m.durum != "yakinda", anahtar
        assert m.musteriye_gorunur, anahtar


def test_sekme_anahtarlari_panellerde_gercekten_var():
    from core import moduller as mf

    musteri = _tab_birlesimi(ON_YUZ / "pages" / "ClientPanel.tsx")
    yonetici = _tab_birlesimi(ON_YUZ / "pages" / "AdminPanel.tsx")
    for m in mf.MODULLER:
        if m.musteri_sekmesi:
            assert m.musteri_sekmesi in musteri, (m.anahtar, m.musteri_sekmesi)
        if m.yonetici_sekmesi:
            assert m.yonetici_sekmesi in yonetici, (m.anahtar, m.yonetici_sekmesi)
    # Tersine: müşteri panelindeki her sekme bir modüle ait (manifest-güdümlü sekme çubuğu).
    tanimli = {m.musteri_sekmesi for m in mf.MODULLER if m.musteri_sekmesi}
    assert musteri <= tanimli, musteri - tanimli
    # Yönetici panelinde modül yönetimi sekmesi var.
    assert "moduller" in yonetici


def test_ikonlar_on_yuz_eslemesinde_var():
    from core import moduller as mf

    metin = (ON_YUZ / "lib" / "modulIkonlari.ts").read_text(encoding="utf-8")
    eslesme = re.search(r"MODUL_IKONLARI[^{]*\{([^}]+)\}", metin)
    assert eslesme
    adlar = set(re.findall(r"\b([A-Z][A-Za-z0-9]+)\b", eslesme.group(1)))
    for m in mf.MODULLER:
        assert m.ikon in adlar, (m.anahtar, m.ikon)


def test_ad_ve_aciklama_yedi_dilde_ve_varsayilanla_ayni():
    from core import moduller as mf

    paketler = {dil: _ek_paket(dil) for dil in DILLER}
    for m in mf.MODULLER:
        assert m.ad_anahtari == f"modul.m.{m.anahtar}.ad"
        for dil, p in paketler.items():
            girdi = p["m"].get(m.anahtar)
            assert girdi and girdi.get("ad") and girdi.get("aciklama"), (dil, m.anahtar)
        # Sunucunun bildirimde kullandığı ad ön yüzdekiyle aynı.
        assert paketler["tr"]["m"][m.anahtar]["ad"] == m.ad_varsayilan["tr"]
        assert paketler["en"]["m"][m.anahtar]["ad"] == m.ad_varsayilan["en"]
        # Gerçek çeviri: Türkçe kopyası değil (özel adlar hariç).
        for dil in ("de", "ru", "zh", "hi", "ar"):
            assert paketler[dil]["m"][m.anahtar]["aciklama"] != paketler["tr"]["m"][m.anahtar]["aciklama"]
    for dil, p in paketler.items():
        for k in mf.KATEGORILER:
            assert p["kategori"][k], (dil, k)
        for d in mf.DURUMLAR:
            assert p["durum"][d], (dil, d)
        for m in mf.MODULLER:
            for a in m.ayarlar:
                assert p["ayar"][a.anahtar], (dil, a.anahtar)


def test_paket_kodlari_fiyat_olcekleriyle_eslesiyor():
    from core import moduller as mf

    tohum = (KOK / "backend" / "scripts" / "seed_pricing_v5.py").read_text(encoding="utf-8")
    olcekler = set(re.findall(r'"kod":\s*"([A-Z]+)",\s*"sira"', tohum))
    assert set(mf.PAKETLER) == olcekler
    for m in mf.MODULLER:
        assert set(m.paketler) <= olcekler


def test_bildirim_katalogunda_modul_olaylari_ve_etiketleri():
    from services.bildirim_tercih import OLAYLAR

    for olay in ("modul_acildi", "modul_kapandi"):
        assert OLAYLAR[olay]["roller"] == ("client",)
        for dil in DILLER:
            ek = json.loads((ON_YUZ / "i18n" / "ek" / "bildirim" / f"{dil}.json").read_text(encoding="utf-8"))
            assert ek["bildirim"]["olay"][olay]
    for dil in DILLER:
        ana = json.loads((ON_YUZ / "i18n" / f"{dil}.json").read_text(encoding="utf-8"))
        assert ana["ui"]["tabModuller"]


# ---------------------------------------------------------------------------
# Öncelik kuralı (saf hesap)
# ---------------------------------------------------------------------------


class _Satir:
    def __init__(self, acik, ayarlar_json=None):
        self.acik = acik
        self.ayarlar_json = ayarlar_json


def test_oncelik_varsayilan_paket_elle():
    from services.moduller import durumlari_hesapla

    bos = durumlari_hesapla(None, {})
    assert (bos["krediler"].acik, bos["krediler"].kaynak) == (True, "varsayilan")
    assert (bos["dosyalar"].acik, bos["dosyalar"].kaynak) == (False, "varsayilan")

    beta = durumlari_hesapla("BETA", {})
    assert (beta["dosyalar"].acik, beta["dosyalar"].kaynak) == (True, "paket")
    alfa = durumlari_hesapla("alfa", {})  # küçük harf de kabul
    assert alfa["dosyalar"].acik is False and alfa["uptime"].kaynak == "paket"

    # Elle > paket
    elle = durumlari_hesapla("BETA", {"dosyalar": _Satir(False), "krediler": _Satir(False)})
    assert (elle["dosyalar"].acik, elle["dosyalar"].kaynak) == (False, "elle")
    assert (elle["krediler"].acik, elle["krediler"].kaynak) == (False, "elle")
    # Elle > varsayılan (kapalıyı açma)
    ac = durumlari_hesapla(None, {"whatsapp": _Satir(True)})
    assert (ac["whatsapp"].acik, ac["whatsapp"].kaynak) == (True, "elle")
    # acik=None satır (yalnız ayar) varsayılanı izler
    yalniz_ayar = durumlari_hesapla("BETA", {"dosyalar": _Satir(None)})
    assert (yalniz_ayar["dosyalar"].acik, yalniz_ayar["dosyalar"].kaynak) == (True, "paket")


def test_cekirdek_satiri_yok_sayilir_ve_bagimlilik_uygulanir():
    from services.moduller import durumlari_hesapla

    d = durumlari_hesapla(None, {"projeler": _Satir(False)})
    assert d["projeler"].acik is True and d["projeler"].elle is None

    # Paket uptime'ı açıyor ama sitem elle kapalı: uptime da kapalı sayılır.
    d = durumlari_hesapla("ALFA", {"sitem": _Satir(False)})
    assert d["uptime"].acik_ham is True
    assert d["uptime"].acik is False
    assert d["uptime"].engelleyen == ["sitem"]


def test_ayar_dogrulama():
    from core.moduller import MODUL_SOZLUGU
    from services.moduller import ModulHatasi, ayarlari_dogrula

    m = MODUL_SOZLUGU["krediler"]
    assert ayarlari_dogrula(m, {"esik_saat": 5}) == {"esik_saat": 5}
    # Boş = "müşteriye özel eşik yok, site ayarı geçerli".
    assert ayarlari_dogrula(m, {"esik_saat": None}) == {"esik_saat": None}
    for kotu in ({"esik_saat": -1}, {"esik_saat": "5"}, {"esik_saat": True},
                 {"esik_saat": 1.5}, {"yok": 1}):
        with pytest.raises(ModulHatasi):
            ayarlari_dogrula(m, kotu)
    # Boş olamayan alan None kabul etmiyor.
    with pytest.raises(ModulHatasi):
        ayarlari_dogrula(MODUL_SOZLUGU["site_analizi"], {"gunluk_sinir": None})


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metot,yol",
    [
        ("GET", YONETIM),
        ("GET", f"{YONETIM}/ozet"),
        ("GET", f"{YONETIM}/musteriler"),
        ("GET", f"{YONETIM}/musteri/a@b.dev"),
        ("PUT", f"{YONETIM}/musteri/a@b.dev/krediler"),
        ("DELETE", f"{YONETIM}/musteri/a@b.dev/krediler"),
    ],
)
async def test_yonetici_uclari_anonime_401_musteriye_403(istemci, musteri_basligi, metot, yol):
    govde = {"acik": False} if metot == "PUT" else None
    anonim = await istemci.request(metot, yol, json=govde)
    assert anonim.status_code == 401
    musteri = await istemci.request(metot, yol, json=govde, headers=musteri_basligi())
    assert musteri.status_code == 403


async def test_modullerim_oturumsuz_401(istemci):
    assert (await istemci.get("/api/v1/modullerim")).status_code == 401


async def test_modullerim_yalniz_musteri_modulleri_ve_gorunumler(istemci, musteri_basligi):
    eposta = _eposta()
    yanit = await istemci.get("/api/v1/modullerim", headers=musteri_basligi(eposta))
    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["paket"] is None
    anahtarlar = [m["anahtar"] for m in govde["moduller"]]
    assert "talepler" not in anahtarlar and "fiyatlandirma" not in anahtarlar
    # Sekme sırası bugünkü müşteri paneliyle aynı.
    sekmeler = [m["musteri_sekmesi"] for m in govde["moduller"] if m["musteri_sekmesi"]]
    # Faz 2C: "dosyalar" sekmesi (paketsiz müşteride kapalı ama manifestte sırası belli).
    # Faz 2G: "mesajlar" sekmesi Destek'in hemen ardında.
    assert sekmeler == [
        "projects", "invoices", "krediler", "tickets", "mesajlar", "raporlar", "sitem", "analiz", "dosyalar", "profile",
    ]
    from core import moduller as mf

    for m in govde["moduller"]:
        if m["durum"] == "yakinda":
            assert m["gorunum"] == "yakinda"
        elif not mf.modul(m["anahtar"]).varsayilan_acik:
            # Paketsiz müşteride pakete bağlı modüller (Faz 2A: uptime, yenileme) eklenebilir.
            assert m["acik"] is False and m["gorunum"] == "eklenebilir"
        else:
            assert m["acik"] is True and m["gorunum"] == "acik"
    # Yöneticiye özel alanlar müşteriye gitmiyor.
    assert "elle" not in govde["moduller"][0]


# ---------------------------------------------------------------------------
# Aç / kapa, çekirdek, bağımlılık
# ---------------------------------------------------------------------------


async def test_kapat_ac_ve_varsayilana_don(istemci, yonetici_basligi, musteri_basligi):
    eposta = _eposta()
    yanit = await _ayarla(istemci, yonetici_basligi, eposta, "krediler", acik=False)
    k = _modul(yanit, "krediler")
    assert (k["acik"], k["kaynak"], k["elle"]) == (False, "elle", False)

    musteri = (await istemci.get("/api/v1/modullerim", headers=musteri_basligi(eposta))).json()
    assert _modul(musteri, "krediler")["gorunum"] == "eklenebilir"

    yanit = await _ayarla(istemci, yonetici_basligi, eposta, "krediler", acik=True)
    assert _modul(yanit, "krediler")["acik"] is True

    geri = await istemci.delete(f"{YONETIM}/musteri/{eposta}/krediler", headers=yonetici_basligi)
    assert geri.status_code == 200
    k = _modul(geri.json(), "krediler")
    assert (k["acik"], k["kaynak"], k["elle"]) == (True, "varsayilan", None)


async def test_eposta_buyuk_harf_ve_bosluk_duzeltiliyor(istemci, yonetici_basligi, musteri_basligi):
    eposta = _eposta()
    await _ayarla(istemci, yonetici_basligi, eposta.upper(), "raporlar", acik=False)
    musteri = (await istemci.get("/api/v1/modullerim", headers=musteri_basligi(eposta))).json()
    assert _modul(musteri, "raporlar")["acik"] is False


async def test_cekirdek_kapatilamaz(istemci, yonetici_basligi):
    eposta = _eposta()
    for anahtar in ("projeler", "faturalar", "destek", "bildirimler", "profil"):
        yanit = await istemci.put(f"{YONETIM}/musteri/{eposta}/{anahtar}", json={"acik": False}, headers=yonetici_basligi)
        assert yanit.status_code == 400, anahtar
        assert yanit.json()["detail"]["kod"] == "cekirdek_kapatilamaz"


async def test_gecersiz_istekler(istemci, yonetici_basligi):
    eposta = _eposta()
    yok = await istemci.put(f"{YONETIM}/musteri/{eposta}/boyle_modul_yok", json={"acik": True}, headers=yonetici_basligi)
    assert yok.status_code == 404 and yok.json()["detail"]["kod"] == "modul_yok"
    ajans = await istemci.put(f"{YONETIM}/musteri/{eposta}/talepler", json={"acik": False}, headers=yonetici_basligi)
    assert ajans.status_code == 400 and ajans.json()["detail"]["kod"] == "yalniz_yonetici_modulu"
    bos = await istemci.put(f"{YONETIM}/musteri/{eposta}/krediler", json={}, headers=yonetici_basligi)
    assert bos.status_code == 400 and bos.json()["detail"]["kod"] == "degisiklik_yok"
    kotu = await istemci.put(f"{YONETIM}/musteri/bir-adres-degil/krediler", json={"acik": True}, headers=yonetici_basligi)
    assert kotu.status_code == 400 and kotu.json()["detail"]["kod"] == "gecersiz_eposta"
    kotu_ayar = await istemci.put(
        f"{YONETIM}/musteri/{eposta}/krediler", json={"ayarlar": {"esik_saat": 9999}}, headers=yonetici_basligi
    )
    assert kotu_ayar.status_code == 400 and kotu_ayar.json()["detail"] == {"kod": "gecersiz_ayar", "alan": "esik_saat"}


async def test_bagimlilik_kapaliyken_acilamaz_409(istemci, yonetici_basligi):
    eposta = _eposta()
    await _ayarla(istemci, yonetici_basligi, eposta, "raporlar", acik=False)
    yanit = await istemci.put(f"{YONETIM}/musteri/{eposta}/aylik_rapor", json={"acik": True}, headers=yonetici_basligi)
    assert yanit.status_code == 409
    assert yanit.json()["detail"] == {"kod": "bagimlilik_kapali", "moduller": ["raporlar"]}
    # Bağımlılık açılınca olur.
    await _ayarla(istemci, yonetici_basligi, eposta, "raporlar", acik=True)
    yanit = await _ayarla(istemci, yonetici_basligi, eposta, "aylik_rapor", acik=True)
    assert _modul(yanit, "aylik_rapor")["acik"] is True


async def test_bagimlisi_acikken_kapatilamaz_409(istemci, yonetici_basligi):
    eposta = _eposta()
    await _ayarla(istemci, yonetici_basligi, eposta, "uptime", acik=True)
    yanit = await istemci.put(f"{YONETIM}/musteri/{eposta}/sitem", json={"acik": False}, headers=yonetici_basligi)
    assert yanit.status_code == 409
    assert yanit.json()["detail"] == {"kod": "bagimli_acik", "moduller": ["uptime"]}
    # Önce bağımlı kapatılınca olur.
    await _ayarla(istemci, yonetici_basligi, eposta, "uptime", acik=False)
    yanit = await _ayarla(istemci, yonetici_basligi, eposta, "sitem", acik=False)
    assert _modul(yanit, "sitem")["acik"] is False
    # Varsayılana dönmek de bağımlılık kuralından geçiyor: sitem kapalıyken
    # uptime'ın varsayılanı (kapalı) → sorun yok; sitem'i varsayılana döndür → açılır.
    geri = await istemci.delete(f"{YONETIM}/musteri/{eposta}/sitem", headers=yonetici_basligi)
    assert geri.status_code == 200 and _modul(geri.json(), "sitem")["acik"] is True


async def test_ayarlar_kaydediliyor_ve_varsayilana_donunce_korunuyor(istemci, yonetici_basligi):
    eposta = _eposta()
    yanit = await _ayarla(
        istemci, yonetici_basligi, eposta, "site_analizi", ayarlar={"gunluk_sinir": 3}
    )
    m = _modul(yanit, "site_analizi")
    assert m["ayarlar"] == {"gunluk_sinir": 3}
    assert m["kaynak"] == "varsayilan" and m["elle"] is None  # yalnız ayar: durum değişmedi
    await _ayarla(istemci, yonetici_basligi, eposta, "site_analizi", acik=False)
    geri = (await istemci.delete(f"{YONETIM}/musteri/{eposta}/site_analizi", headers=yonetici_basligi)).json()
    m = _modul(geri, "site_analizi")
    assert m["acik"] is True and m["ayarlar"] == {"gunluk_sinir": 3}


# ---------------------------------------------------------------------------
# Paket kaynağı (fiyat teklifi)
# ---------------------------------------------------------------------------


async def test_kabul_edilen_teklifin_olcegi_paket_olur(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.pricing import Pricing_inquiries

    eposta = _eposta()
    # Karar verilmemiş teklif paket sayılmaz.
    db_oturumu.add(Pricing_inquiries(scale_kod="OMEGA", hesaplanan_tutar=100, musteri_eposta=eposta))
    await db_oturumu.commit()
    yanit = (await istemci.get(f"{YONETIM}/musteri/{eposta}", headers=yonetici_basligi)).json()
    assert yanit["paket"] is None

    db_oturumu.add(Pricing_inquiries(scale_kod="BETA", hesaplanan_tutar=100, musteri_eposta=eposta, durum="kabul"))
    await db_oturumu.commit()
    yanit = (await istemci.get(f"{YONETIM}/musteri/{eposta}", headers=yonetici_basligi)).json()
    assert yanit["paket"] == "BETA"
    d = _modul(yanit, "dosyalar")
    assert (d["acik"], d["kaynak"]) == (True, "paket")
    assert _modul(yanit, "uptime")["kaynak"] == "paket"

    musteri = (await istemci.get("/api/v1/modullerim", headers=musteri_basligi(eposta))).json()
    assert musteri["paket"] == "BETA"
    # Faz 2C: dosyalar yayında → paketli müşteride doğrudan açık.
    assert _modul(musteri, "dosyalar")["gorunum"] == "acik" and _modul(musteri, "dosyalar")["acik"] is True

    # Elle kapatma paketi geçersiz kılar.
    yanit = await _ayarla(istemci, yonetici_basligi, eposta, "dosyalar", acik=False)
    d = _modul(yanit, "dosyalar")
    assert (d["acik"], d["kaynak"]) == (False, "elle")


async def test_odenmis_faturali_teklif_de_paket_olur(istemci, yonetici_basligi, db_oturumu):
    from models.invoices import Invoices
    from models.pricing import Pricing_inquiries

    eposta = _eposta()
    fatura = Invoices(invoice_no=f"T-{uuid.uuid4().hex[:6]}", amount=10, status="paid", client_email=eposta)
    db_oturumu.add(fatura)
    await db_oturumu.flush()
    db_oturumu.add(Pricing_inquiries(scale_kod="SIGMA", hesaplanan_tutar=10, musteri_eposta=eposta, invoice_id=fatura.id))
    await db_oturumu.commit()
    yanit = (await istemci.get(f"{YONETIM}/musteri/{eposta}", headers=yonetici_basligi)).json()
    assert yanit["paket"] == "SIGMA"
    assert _modul(yanit, "whatsapp")["kaynak"] == "paket"


# ---------------------------------------------------------------------------
# Bekçi: mevcut müşteri uçları
# ---------------------------------------------------------------------------

KORUNAN_UCLAR = [
    ("krediler", "/api/v1/kredilerim"),
    ("site_analizi", "/api/v1/site-analizi/benim"),
    ("islem", "/api/v1/islemlerim"),
    ("raporlar", "/api/v1/raporlarim"),
    ("sitem", "/api/v1/sitelerim"),
    ("denetim", "/api/v1/denetim/benim"),
]


@pytest.mark.parametrize("anahtar,yol", KORUNAN_UCLAR)
async def test_mevcut_uclar_varsayilanda_calismaya_devam_ediyor(istemci, musteri_basligi, anahtar, yol):
    eposta = _eposta("varsayilan")
    assert (await istemci.get(yol, headers=musteri_basligi(eposta))).status_code == 200
    # Oturumsuz: bekçi karışmıyor, ucun kendi yanıtı (401, raporlarımda 403) döner.
    anonim = await istemci.get(yol)
    assert anonim.status_code in (401, 403)
    assert anonim.json().get("detail") != {"kod": "modul_kapali", "modul": anahtar}


@pytest.mark.parametrize("anahtar,yol", KORUNAN_UCLAR)
async def test_bekci_kapali_modulde_403_ve_baskasini_etkilemez(
    istemci, yonetici_basligi, musteri_basligi, anahtar, yol
):
    eposta, baska = _eposta("kapali"), _eposta("baska")
    await _ayarla(istemci, yonetici_basligi, eposta, anahtar, acik=False)

    yanit = await istemci.get(yol, headers=musteri_basligi(eposta))
    assert yanit.status_code == 403
    assert yanit.json()["detail"] == {"kod": "modul_kapali", "modul": anahtar}
    assert (await istemci.get(yol, headers=musteri_basligi(baska))).status_code == 200

    await _ayarla(istemci, yonetici_basligi, eposta, anahtar, acik=True)
    assert (await istemci.get(yol, headers=musteri_basligi(eposta))).status_code == 200


async def test_bekci_yoneticiyi_etkilemez(istemci, yonetici_basligi):
    # Yöneticinin kendi e-postası için modülü kapatsak bile yönetici uçları ve
    # müşteri uçları yöneticide açık.
    await _ayarla(istemci, yonetici_basligi, "yonetici@test.dev", "krediler", acik=False)
    try:
        assert (await istemci.get("/api/v1/kredilerim", headers=yonetici_basligi)).status_code == 200
        assert (await istemci.get("/api/v1/kredi/yonetim/musteriler", headers=yonetici_basligi)).status_code == 200
    finally:
        await istemci.delete(f"{YONETIM}/musteri/yonetici@test.dev/krediler", headers=yonetici_basligi)


async def test_bekci_bagimlilik_uzerinden_de_kapatir(db_oturumu):
    """Bağımlılığı kapalı modül de kapalı sayılır (`modul_acik_mi`)."""
    from models.workspace_modules import WorkspaceModules
    from services.moduller import modul_acik_mi

    eposta = _eposta()
    db_oturumu.add(WorkspaceModules(musteri_eposta=eposta, modul_anahtari="uptime", acik=True))
    db_oturumu.add(WorkspaceModules(musteri_eposta=eposta, modul_anahtari="sitem", acik=False))
    await db_oturumu.commit()
    assert await modul_acik_mi(db_oturumu, eposta, "uptime") is False
    assert await modul_acik_mi(db_oturumu, eposta, "projeler") is True
    assert await modul_acik_mi(db_oturumu, eposta, "boyle_yok") is False


def test_bilinmeyen_modul_icin_bekci_kurulamaz():
    from dependencies.modul_bekcisi import modul_gerekli

    with pytest.raises(ValueError):
        modul_gerekli("yazim_hatasi")


# ---------------------------------------------------------------------------
# Bildirim, denetim, özet
# ---------------------------------------------------------------------------


async def test_ac_kapa_bildirim_ve_denetim_kaydi(istemci, yonetici_basligi, db_oturumu):
    from models.audit_log import AuditLog
    from models.notifications import Notifications

    eposta = _eposta()
    await _ayarla(istemci, yonetici_basligi, eposta, "krediler", acik=False)
    await _ayarla(istemci, yonetici_basligi, eposta, "krediler", acik=True)
    # Durum değişmeyen istek bildirim üretmez.
    await _ayarla(istemci, yonetici_basligi, eposta, "krediler", acik=True)

    olaylar = (
        await db_oturumu.execute(
            select(Notifications.event_type, Notifications.title)
            .where(Notifications.recipient_email == eposta, Notifications.channel == "inapp")
            .order_by(Notifications.id)
        )
    ).all()
    assert [o[0] for o in olaylar] == ["modul_kapandi", "modul_acildi"]
    assert "Krediler" in olaylar[0][1] and "Credits" in olaylar[0][1]

    kayitlar = (
        await db_oturumu.execute(
            select(AuditLog).where(AuditLog.tablo == "workspace_modules", AuditLog.ilgili_eposta == eposta)
        )
    ).scalars().all()
    assert kayitlar, "denetim kaydı yok"
    assert all(k.aktor_eposta == "yonetici@test.dev" and k.aktor_rol == "admin" for k in kayitlar)
    ilk = min(kayitlar, key=lambda k: k.id)
    assert "krediler" in (ilk.ozet or "")
    assert "***" not in (ilk.degisiklik_json or "")


async def test_ozet_ve_musteri_listesi(istemci, yonetici_basligi):
    eposta = _eposta("ozet")
    await _ayarla(istemci, yonetici_basligi, eposta, "sitem", acik=False)

    liste = (await istemci.get(f"{YONETIM}/musteriler", headers=yonetici_basligi)).json()
    assert eposta in [m["eposta"] for m in liste]

    ozet = (await istemci.get(f"{YONETIM}/ozet", headers=yonetici_basligi)).json()
    satirlar = {s["anahtar"]: s for s in ozet["moduller"]}
    toplam = ozet["toplam_musteri"]
    assert toplam >= 1
    assert satirlar["projeler"]["acik_musteri"] == toplam
    assert satirlar["sitem"]["acik_musteri"] < toplam
    assert satirlar["sitem"]["elle_kapali"] >= 1
    assert satirlar["talepler"]["acik_musteri"] is None  # yalnız ajans

    manifest = (await istemci.get(YONETIM, headers=yonetici_basligi)).json()
    assert [m["anahtar"] for m in manifest["moduller"]][:2] == ["projeler", "faturalar"]
    assert manifest["paketler"] == ["ALFA", "BETA", "OMEGA", "SIGMA"]


async def test_yazacak_bir_sey_yoksa_satir_olusmaz(istemci, yonetici_basligi, db_oturumu):
    from models.workspace_modules import WorkspaceModules

    eposta = _eposta()
    yanit = await _ayarla(istemci, yonetici_basligi, eposta, "projeler", acik=True)
    assert _modul(yanit, "projeler")["acik"] is True
    geri = await istemci.delete(f"{YONETIM}/musteri/{eposta}/krediler", headers=yonetici_basligi)
    assert geri.status_code == 200
    satirlar = (
        await db_oturumu.execute(select(WorkspaceModules).where(WorkspaceModules.musteri_eposta == eposta))
    ).scalars().all()
    assert satirlar == []
