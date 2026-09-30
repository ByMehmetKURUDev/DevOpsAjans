"""Katalog çevirisi eşleştirme testleri — veritabanı gerektirmez."""
from scripts.pricing_ceviri_doldur import ceviri_uret, katalogu_yukle

KATALOG = katalogu_yukle()


def test_yedi_dilin_altisi_katalogda():
    assert set(KATALOG) == {"en", "de", "ru", "zh", "hi", "ar"}


def test_olcek_kod_ile_eslesir_ve_liste_alanlari_korunur():
    c = ceviri_uret("pricing_scales", {"kod": "ALFA"}, KATALOG)
    assert c["en"]["ad"] == "Alpha Series"
    assert len(c["de"]["ozellikler"]) == 5
    assert set(c["en"]["karsilastirma"]) == {"hosting", "sla", "panel", "devops", "mulkiyet", "ads", "seo"}


def test_modul_turkce_ad_ile_eslesir():
    c = ceviri_uret("pricing_addons", {"ad": "Blog Modülü"}, KATALOG)
    assert c and c["en"]["ad"] and c["en"]["ad"] != "Blog Modülü"


def test_hizmet_kategori_ve_not_cevrilir():
    c = ceviri_uret("pricing_services", {"ad": "Bakım / Aylık Destek", "kategori": "ALTYAPI"}, KATALOG)
    assert c["en"]["kategori"] and c["en"]["not_metni"]


def test_bilinmeyen_satir_none():
    assert ceviri_uret("pricing_addons", {"ad": "Böyle bir modül yok"}, KATALOG) is None
    assert ceviri_uret("pricing_scales", {"kod": "YOK"}, KATALOG) is None


def test_tum_seed_satirlari_eslesir():
    import importlib.util
    spec = importlib.util.spec_from_file_location("s", "scripts/seed_pricing_v5.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    for s in m.SCALES:
        assert ceviri_uret("pricing_scales", {"kod": s["kod"]}, KATALOG)
    for p in m.PROFILES:
        assert ceviri_uret("pricing_profiles", {"kod": p["kod"]}, KATALOG)
    for t in m.AI_PM_TIERS:
        assert ceviri_uret("ai_pm_tiers", {"kod": t["kod"]}, KATALOG)
    for a in m.ADDONS:
        assert ceviri_uret("pricing_addons", {"ad": a[1]}, KATALOG)
    for sv in m.SERVICES:
        assert ceviri_uret("pricing_services", {"ad": sv[1], "kategori": sv[0]}, KATALOG)
