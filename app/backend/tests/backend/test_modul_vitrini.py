"""Faz 4V — herkese açık modül vitrini ve sektör paketleri.

Kapsam:
* Yapı modül kaydından türetiliyor: satıştaki modüller (yakında, yönetici,
  çekirdek ve herkese açık olanlar yok), yakında bölümü, temeller; ön yüzdeki
  kopya (`prerender/modul-vitrini-veri.json`) kayıtla AYNI.
* Sektör paketleri: gerçek, satılabilir modül anahtarları; ad tr/en ek paketle
  aynı; ikonlar ön yüz eşlemesinde; "paketi aç" listesi.
* Tanıtım metinleri 7 dilde (özet, kimin için, 3–5 özellik, 2–3 SSS); pazarlama
  izni metni sunucudakiyle aynı; vitrinde olmayan modüle metin yok.
* `GET /api/v1/modul-vitrini`: herkese açık, önbellek başlığı, fiyat yoksa
  boş, fiyatlandırma v5'ten başlangıç fiyatı (Hizmetler'le aynı hesap).
* `POST /api/v1/modul-vitrini/talep`: inquiries + `source` + CRM adayı
  (`modul_vitrini`), yönetici bildirimi, doğrulama, bal küpü, çift tık, hız
  sınırı, pazarlama izni (yalnız JSON true).
"""

import json
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from core import moduller as manifest
from core import sektor_paketleri as sp
from services import modul_vitrini as mv
from services import pazarlama_izni

UC = "/api/v1/modul-vitrini"
ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")


@pytest.fixture(autouse=True)
def _temiz():
    from routers import modul_vitrini as r

    r.hiz_sinirlarini_temizle()
    yield
    r.hiz_sinirlarini_temizle()


def _e(on: str = "vitrin") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@ornek-firma.com"


def _ek(dil: str) -> dict:
    return json.loads((ON_YUZ / "src/i18n/ek/modulVitrini" / f"{dil}.json").read_text(encoding="utf-8"))["modulVitrini"]


async def _talep(istemci, ip: str = "203.0.113.10", **govde):
    veri = {"tur": "modul", "anahtar": "qr_menu", "ad": "Ayşe Kafe", "eposta": _e(), "dil": "tr", **govde}
    return await istemci.post(f"{UC}/talep", json=veri, headers={"x-mk-istemci-ip": ip}), veri


# ---------------------------------------------------------------------------
# Yapı — kayıttan türetiliyor
# ---------------------------------------------------------------------------
def test_satistaki_moduller_kayittan_turuyor():
    y = mv.yapi()
    anahtarlar = [m["anahtar"] for m in y["moduller"]]
    for m in manifest.MODULLER:
        satista = m.musteriye_gorunur and not m.cekirdek and not m.varsayilan_acik and m.durum in ("yayinda", "beta")
        assert (m.anahtar in anahtarlar) == satista, m.anahtar
    # Yakında olan, yönetici modülü, çekirdek ve herkese açık modül vitrinde (satışta) yok.
    assert "whatsapp" not in anahtarlar and manifest.modul("whatsapp").durum == "yakinda"
    assert "crm" not in anahtarlar and "projeler" not in anahtarlar and "site_analizi" not in anahtarlar
    assert [x["anahtar"] for x in y["yakinda"]] == ["whatsapp"]
    temeller = [x["anahtar"] for x in y["temeller"]]
    assert "site_analizi" in temeller and "projeler" in temeller
    assert "profil" not in temeller and "bildirimler" not in temeller and "denetim" not in temeller and "crm" not in temeller
    # Kategoriler yalnız dolu olanlar, slug'lar benzersiz ve URL'ye uygun.
    assert set(y["kategoriler"]) == {m["kategori"] for m in y["moduller"]}
    sluglar = [m["slug"] for m in y["moduller"]] + [p["slug"] for p in y["paketler"]]
    assert len(set(sluglar)) == len(sluglar)
    assert all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", s) for s in sluglar)
    assert y["olcekler"] == list(manifest.PAKETLER)


def test_paket_ve_ilgili_moduller():
    y = {m["anahtar"]: m for m in mv.yapi()["moduller"]}
    # Paketlere bağlı modülde en düşük ölçek; ayrı satılanda null.
    assert y["uptime"]["paket"] == "ALFA" and y["dosyalar"]["paket"] == "BETA"
    assert y["qr_menu"]["paket"] is None and y["randevu"]["paket"] is None
    for m in y.values():
        assert m["anahtar"] not in m["ilgili"] and len(m["ilgili"]) <= mv.ILGILI_SAYISI
        assert all(k in y for k in m["ilgili"])
    # Aynı sektör paketindekiler önce.
    assert y["qr_menu"]["ilgili"][:3] == ["whatsapp_katalog", "google_yorum_sayfasi", "dinamik_qr"]
    assert y["qr_menu"]["sektor_paketleri"] == ["restoran_kafe"]


def test_on_yuz_kopyasi_kayitla_ayni():
    """Kayıt değiştiyse: `python -m scripts.modul_vitrini_tohum` ile kopyayı yeniden üretin."""
    from scripts.modul_vitrini_tohum import HEDEF, metin

    assert HEDEF.read_text(encoding="utf-8") == metin(), "prerender/modul-vitrini-veri.json güncel değil"


# ---------------------------------------------------------------------------
# Sektör paketleri
# ---------------------------------------------------------------------------
def test_sektor_paketleri_tutarli():
    assert sp.paket_hatalari() == []
    assert 5 <= len(sp.SEKTOR_PAKETLERI) <= 6
    for p in sp.SEKTOR_PAKETLERI:
        for k in p.moduller:
            m = manifest.modul(k)
            assert m is not None and mv.satista_mi(m), (p.anahtar, k)
    # Bozuk tanım yakalanıyor.
    eski = sp.SEKTOR_PAKETLERI
    try:
        sp.SEKTOR_PAKETLERI = eski + (
            sp.SektorPaketi("bozuk", {"tr": "x"}, "Wrench", ("crm", "whatsapp", "yok_boyle")),
        )
        hatalar = sp.paket_hatalari()
    finally:
        sp.SEKTOR_PAKETLERI = eski
    assert any("crm" in h for h in hatalar) and any("whatsapp" in h for h in hatalar)
    assert any("yok_boyle" in h for h in hatalar) and any("ad_varsayilan" in h for h in hatalar)


def test_paketi_ac_listesi_bagimliliklarla():
    assert sp.acilacak_moduller("restoran_kafe") == [
        m.anahtar for m in manifest.sirali()
        if m.anahtar in {"qr_menu", "whatsapp_katalog", "google_yorum_sayfasi", "dinamik_qr", "stok_pos"}
    ]
    assert sp.acilacak_moduller("yok") == []
    assert [p.anahtar for p in sp.iceren_paketler("randevu")] == ["klinik_guzellik", "teknik_servis", "egitim_etkinlik", "ajans_serbest"]


def test_paket_ikonlari_on_yuz_eslemesinde_var():
    metin = (ON_YUZ / "src/lib/modulIkonlari.ts").read_text(encoding="utf-8")
    for p in sp.SEKTOR_PAKETLERI:
        assert re.search(rf"\b{p.ikon}\b", metin), p.ikon


# ---------------------------------------------------------------------------
# Tanıtım metinleri (7 dil)
# ---------------------------------------------------------------------------
def test_tanitim_metinleri_yedi_dilde_ve_eksiksiz():
    satistaki = [m.anahtar for m in mv.satistakiler()]
    for dil in DILLER:
        ek = _ek(dil)
        assert set(ek["m"]) == set(satistaki), dil  # eksik de fazla da yok
        for k in satistaki:
            t = ek["m"][k]
            assert t["ozet"].strip() and t["kimIcin"].strip(), (dil, k)
            assert len(t["ozet"]) <= 160, (dil, k, len(t["ozet"]))
            assert 3 <= len(t["ozellikler"]) <= 5 and all(o.strip() for o in t["ozellikler"]), (dil, k)
            assert 2 <= len(t["sss"]) <= 3 and all(s["s"].strip() and s["c"].strip() for s in t["sss"]), (dil, k)
        assert set(ek["p"]) == {p.anahtar for p in sp.SEKTOR_PAKETLERI}, dil
        for p in sp.SEKTOR_PAKETLERI:
            assert all(ek["p"][p.anahtar][a].strip() for a in ("ad", "ozet", "kimIcin", "neden")), (dil, p.anahtar)
        assert set(mv.yapi()["kategoriler"]) <= set(ek["kategori"]), dil
        # Türkçe dışındaki diller Türkçenin kopyası değil (gerçek çeviri).
        if dil != "tr":
            tr = _ek("tr")
            assert ek["m"]["qr_menu"]["ozet"] != tr["m"]["qr_menu"]["ozet"], dil
            assert ek["liste"]["giris"] != tr["liste"]["giris"], dil


def test_paket_adlari_varsayilanla_ayni_ve_pazarlama_metni_sunucudakiyle_ayni():
    for p in sp.SEKTOR_PAKETLERI:
        assert _ek("tr")["p"][p.anahtar]["ad"] == p.ad_varsayilan["tr"]
        assert _ek("en")["p"][p.anahtar]["ad"] == p.ad_varsayilan["en"]
    for dil in DILLER:
        assert _ek(dil)["form"]["pazarlama"] == pazarlama_izni.METINLER[dil], dil


def test_modul_adlari_modul_ek_paketinde_var():
    """Vitrin adları mevcut modül ek paketinden alıyor (ikinci bir ad listesi yok)."""
    y = mv.yapi()
    for dil in DILLER:
        modul = json.loads((ON_YUZ / "src/i18n/ek/modul" / f"{dil}.json").read_text(encoding="utf-8"))["modul"]
        for m in y["moduller"] + y["yakinda"] + y["temeller"]:
            assert modul["m"][m["anahtar"]]["ad"].strip(), (dil, m["anahtar"])
        for k in y["kategoriler"]:
            assert modul["kategori"][k].strip(), (dil, k)


# ---------------------------------------------------------------------------
# GET — vitrin verisi
# ---------------------------------------------------------------------------
async def test_vitrin_ucu_herkese_acik_fiyatsiz(istemci, db_oturumu):
    from models.pricing import Pricing_profiles, Pricing_scales

    for model in (Pricing_scales, Pricing_profiles):
        for satir in (await db_oturumu.execute(select(model))).scalars().all():
            await db_oturumu.delete(satir)
    await db_oturumu.commit()
    y = await istemci.get(UC)
    assert y.status_code == 200
    assert "max-age=300" in y.headers.get("cache-control", "")
    g = y.json()
    assert g["fiyatlar"] == {}
    assert {k: v for k, v in g.items() if k != "fiyatlar"} == mv.yapi()


async def test_vitrin_ucu_baslangic_fiyati_v5(istemci, db_oturumu):
    from models.pricing import Pricing_profiles, Pricing_scales
    from scripts.seed_pricing_v5 import seed

    await seed(db_oturumu)
    s = (await db_oturumu.execute(select(Pricing_scales).where(Pricing_scales.kod == "ALFA"))).scalar_one()
    s.ceviriler = json.dumps({"en": {"ad": "Alpha Series"}})
    await db_oturumu.commit()
    profiller = (await db_oturumu.execute(select(Pricing_profiles))).scalars().all()
    en_dusuk = min(p.carpan for p in profiller)

    g = (await istemci.get(UC)).json()
    alfa = g["fiyatlar"]["ALFA"]
    assert alfa["para_birimi"] == "USD"
    assert alfa["ad"]["tr"] == "Alfa Serisi" and alfa["ad"]["en"] == "Alpha Series"
    # Hizmetler sayfasıyla aynı hesap (/fiyat-hesapla, aylık): profiller içinde en düşüğü.
    tutarlar = []
    for p in profiller:
        r = await istemci.get("/api/v1/fiyat-hesapla", params={"scale": "ALFA", "profile": p.kod, "period": "aylik"})
        tutarlar.append(r.json()["paket_fiyat"])
    assert alfa["baslangic_aylik"] == min(tutarlar) == round(540 * en_dusuk, 2)
    assert set(g["fiyatlar"]) >= {"ALFA", "BETA", "OMEGA", "SIGMA"}


# ---------------------------------------------------------------------------
# POST — teklif talebi
# ---------------------------------------------------------------------------
async def _talep_kaydi(db, eposta):
    from models.inquiries import Inquiries

    return (
        await db.execute(select(Inquiries).where(Inquiries.email == eposta).execution_options(populate_existing=True))
    ).scalars().all()


async def _aday(db, eposta):
    from models.crm import CrmAdaylari

    return (
        await db.execute(select(CrmAdaylari).where(CrmAdaylari.email == eposta).execution_options(populate_existing=True))
    ).scalars().all()


async def test_modul_talebi_inquiries_ve_crm_adayi(istemci, db_oturumu):
    from models.notifications import Notifications

    y, v = await _talep(istemci, telefon="0555 000 00 00", isletme_turu="restoran_kafe", **{"not": "İki şubemiz var."})
    assert y.status_code == 200 and y.json() == {"ok": True}
    talepler = await _talep_kaydi(db_oturumu, v["eposta"])
    assert len(talepler) == 1
    t = talepler[0]
    assert t.source == "modul_vitrini:modul:qr_menu" and t.status == "new"
    assert t.subject == "Modül talebi: QR menü" and t.phone == "0555 000 00 00" and t.name == "Ayşe Kafe"
    assert "QR menü (qr_menu)" in t.message and "İşletme türü: Restoran ve kafe" in t.message and "İki şubemiz var." in t.message
    adaylar = await _aday(db_oturumu, v["eposta"])
    assert len(adaylar) == 1
    a = adaylar[0]
    assert a.kaynak == "modul_vitrini" and a.kaynak_tablo == "inquiries" and a.kaynak_id == t.id
    assert a.kaynak_detay == "modul_vitrini:modul:qr_menu" and a.pazarlama_izni_at is None
    # Yöneticiye iletişim formuyla aynı olay.
    bildirim = (
        await db_oturumu.execute(
            select(Notifications).where(Notifications.event_type == "inquiry", Notifications.title.contains("Ayşe Kafe"))
        )
    ).scalars().all()
    assert bildirim and all(b.recipient_role == "admin" for b in bildirim)


async def test_paket_talebi_mesajda_moduller(istemci, db_oturumu):
    y, v = await _talep(istemci, tur="paket", anahtar="teknik_servis", dil="de")
    assert y.status_code == 200
    t = (await _talep_kaydi(db_oturumu, v["eposta"]))[0]
    assert t.source == "modul_vitrini:paket:teknik_servis" and t.subject == "Paket talebi: Teknik servis ve bakım"
    assert "Paketteki modüller: Saha servisi, Randevu ve toplantılar, Google yorum sayfası" in t.message
    assert "Sayfa dili: de" in t.message
    assert (await _aday(db_oturumu, v["eposta"]))[0].kaynak == "modul_vitrini"


async def test_pazarlama_izni_yalniz_json_true(istemci, db_oturumu):
    y, v = await _talep(istemci, pazarlama_izni=True, dil="en")
    assert y.status_code == 200
    a = (await _aday(db_oturumu, v["eposta"]))[0]
    assert a.pazarlama_izni_at is not None
    assert a.pazarlama_izni_kaynak == "modul_vitrini:modul:qr_menu" and a.pazarlama_metin_surumu == "1/en"
    for deger in ("true", 1, None):
        y, v = await _talep(istemci, ip="203.0.113.11", pazarlama_izni=deger)
        assert y.status_code == 200
        assert (await _aday(db_oturumu, v["eposta"]))[0].pazarlama_izni_at is None, deger


@pytest.mark.parametrize(
    "degisiklik,kod",
    [
        ({"tur": "hepsi"}, "tur_gecersiz"),
        ({"anahtar": "yok_boyle"}, "anahtar_gecersiz"),
        ({"anahtar": "whatsapp"}, "anahtar_gecersiz"),  # yakında
        ({"anahtar": "crm"}, "anahtar_gecersiz"),  # yalnız yönetici
        ({"anahtar": "projeler"}, "anahtar_gecersiz"),  # çekirdek, herkese açık
        ({"tur": "paket", "anahtar": "qr_menu"}, "anahtar_gecersiz"),
        ({"anahtar": 5}, "anahtar_gecersiz"),
        ({"ad": "  "}, "ad_gerekli"),
        ({"eposta": "gecersiz"}, "eposta_gecersiz"),
        ({"ad": "x" * 121}, "alan_uzun"),
        ({"not": "x" * 2001}, "alan_uzun"),
        ({"telefon": {"a": 1}}, "alan_gecersiz"),
        ({"isletme_turu": "banka"}, "isletme_turu_gecersiz"),
    ],
)
async def test_dogrulama(istemci, db_oturumu, degisiklik, kod):
    y, v = await _talep(istemci, ip="203.0.113.20", **degisiklik)
    assert y.status_code == 400, y.text
    assert y.json()["detail"]["kod"] == kod
    eposta = v["eposta"] if isinstance(v.get("eposta"), str) else ""
    assert await _talep_kaydi(db_oturumu, eposta) == []


async def test_govde_gecersiz_ve_buyuk(istemci):
    y = await istemci.post(f"{UC}/talep", content=b"{bozuk", headers={"content-type": "application/json"})
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "govde_gecersiz"
    y = await istemci.post(f"{UC}/talep", json=[1, 2])
    assert y.status_code == 400
    y = await istemci.post(f"{UC}/talep", content=b"x" * 9000, headers={"content-type": "application/json"})
    assert y.status_code == 413


async def test_bal_kupu_sessizce_yok_sayar(istemci, db_oturumu):
    y, v = await _talep(istemci, web_sitesi="http://spam.example")
    assert y.status_code == 200 and y.json()["ok"] is True
    assert await _talep_kaydi(db_oturumu, v["eposta"]) == []


async def test_cift_tik_tek_kayit(istemci, db_oturumu):
    eposta = _e("cift")
    y1, _ = await _talep(istemci, eposta=eposta)
    y2, _ = await _talep(istemci, eposta=eposta.upper())
    assert y1.status_code == y2.status_code == 200
    assert len(await _talep_kaydi(db_oturumu, eposta)) == 1
    # Başka modül için aynı kişi yeni talep açabilir (CRM'de aynı adaya eklenir).
    y3, _ = await _talep(istemci, eposta=eposta, anahtar="randevu")
    assert y3.status_code == 200
    assert len(await _talep_kaydi(db_oturumu, eposta)) == 2
    assert len(await _aday(db_oturumu, eposta)) == 1


async def test_hiz_siniri_iletisim_formuyla_ayni(istemci):
    kodlar = []
    for _ in range(6):
        y, _ = await _talep(istemci, ip="198.51.100.40")
        kodlar.append(y.status_code)
    assert kodlar[:5] == [200] * 5 and kodlar[5] == 429
    y, _ = await _talep(istemci, ip="198.51.100.40")
    assert y.json()["detail"]["kod"] == "cok_fazla_istek"
    # Başka IP etkilenmiyor.
    y, _ = await _talep(istemci, ip="198.51.100.41")
    assert y.status_code == 200


async def test_crm_kaynak_esleme_ve_puan():
    from services.crm import KAYNAK_PUANI, KAYNAKLAR, kaynak_esle

    assert "modul_vitrini" in KAYNAKLAR and KAYNAK_PUANI["modul_vitrini"] == KAYNAK_PUANI["iletisim"]
    assert kaynak_esle("inquiries", "modul_vitrini:paket:restoran_kafe") == "modul_vitrini"
    # Müşteri panelindeki "Teklif iste" (modul: …) iletişim olarak kalıyor.
    assert kaynak_esle("inquiries", "modul: QR menü") == "iletisim"
    for dil in DILLER:
        crm = json.loads((ON_YUZ / "src/i18n/ek/crm" / f"{dil}.json").read_text(encoding="utf-8"))["crm"]
        assert crm["kaynak"]["modul_vitrini"].strip() and "{{anahtar}}" in crm["pazarlama"]["kaynakModulVitrini"], dil
