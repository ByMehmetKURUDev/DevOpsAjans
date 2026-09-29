"""fiyat_hesaplama() birim testleri — veritabanı gerektirmez.

Fiyatlandırma v5'in tek doğru kaynağı: bu testler geçmeden hiçbir
uç nokta veya frontend bileşeni bu fonksiyona güvenmemeli.
"""
import pytest

from core.fiyat_hesaplama import FiyatHesaplamaHatasi, hesapla

SCALES = {"ALFA": 540, "BETA": 1140, "OMEGA": 2280, "SIGMA": 3360}
PROFILES = {"kurumsal": 1.0, "startup": 0.85, "stk": 0.6, "bireysel": 0.7, "egitim": 0.75}


@pytest.mark.parametrize(
    "scale,profile,expected_aylik",
    [
        ("ALFA", "kurumsal", 540.0),
        ("ALFA", "startup", 459.0),
        ("ALFA", "stk", 324.0),
        ("ALFA", "bireysel", 378.0),
        ("ALFA", "egitim", 405.0),
        ("BETA", "kurumsal", 1140.0),
        ("OMEGA", "kurumsal", 2280.0),
        ("SIGMA", "kurumsal", 3360.0),
    ],
)
def test_paket_fiyat_aylik(scale, profile, expected_aylik):
    sonuc = hesapla(
        scale_kod=scale, profile_kod=profile, period="aylik", addon_kodlari=[],
        scale_baz_fiyatlari=SCALES, profile_carpanlari=PROFILES, addon_fiyatlari={},
    )
    assert sonuc.toplam == pytest.approx(expected_aylik, abs=0.01)


def test_paket_fiyat_yillik_16_indirim_yillik_toplam_uzerinden():
    sonuc = hesapla(
        scale_kod="ALFA", profile_kod="kurumsal", period="yillik", addon_kodlari=[],
        scale_baz_fiyatlari=SCALES, profile_carpanlari=PROFILES, addon_fiyatlari={},
    )
    assert sonuc.toplam == pytest.approx(5443.20, abs=0.01)


def test_paket_fiyat_tek_seferlik_varsayilan_aylik_x3_isaretli():
    sonuc = hesapla(
        scale_kod="ALFA", profile_kod="kurumsal", period="tek_seferlik", addon_kodlari=[],
        scale_baz_fiyatlari=SCALES, profile_carpanlari=PROFILES, addon_fiyatlari={},
    )
    assert sonuc.toplam == pytest.approx(1620.0, abs=0.01)
    assert sonuc.formul_notu == "varsayilan_aylik_x3"


def test_diger_periyotlarda_formul_notu_yok():
    sonuc = hesapla(
        scale_kod="ALFA", profile_kod="kurumsal", period="aylik", addon_kodlari=[],
        scale_baz_fiyatlari=SCALES, profile_carpanlari=PROFILES, addon_fiyatlari={},
    )
    assert sonuc.formul_notu is None


def test_eklenti_fiyati_profil_carpaniyla_bir_kez_olceklenir():
    sonuc = hesapla(
        scale_kod="ALFA", profile_kod="egitim", period="aylik", addon_kodlari=["cok_dilli"],
        scale_baz_fiyatlari=SCALES, profile_carpanlari=PROFILES, addon_fiyatlari={"cok_dilli": 80},
    )
    # 80 * 0.75 = 60 — stk/egitim indirimi carpanin kendisinde, ikinci kez uygulanmaz
    assert sonuc.eklentiler_toplami == pytest.approx(60.0, abs=0.01)


def test_bilinmeyen_olcek_hata_firlatir():
    with pytest.raises(FiyatHesaplamaHatasi):
        hesapla(
            scale_kod="YOK", profile_kod="kurumsal", period="aylik", addon_kodlari=[],
            scale_baz_fiyatlari=SCALES, profile_carpanlari=PROFILES, addon_fiyatlari={},
        )


def test_bilinmeyen_profil_hata_firlatir():
    with pytest.raises(FiyatHesaplamaHatasi):
        hesapla(
            scale_kod="ALFA", profile_kod="YOK", period="aylik", addon_kodlari=[],
            scale_baz_fiyatlari=SCALES, profile_carpanlari=PROFILES, addon_fiyatlari={},
        )


def test_bilinmeyen_periyot_hata_firlatir():
    with pytest.raises(FiyatHesaplamaHatasi):
        hesapla(
            scale_kod="ALFA", profile_kod="kurumsal", period="YOK", addon_kodlari=[],
            scale_baz_fiyatlari=SCALES, profile_carpanlari=PROFILES, addon_fiyatlari={},
        )


def test_bilinmeyen_eklenti_hata_firlatir():
    with pytest.raises(FiyatHesaplamaHatasi):
        hesapla(
            scale_kod="ALFA", profile_kod="kurumsal", period="aylik", addon_kodlari=["yok"],
            scale_baz_fiyatlari=SCALES, profile_carpanlari=PROFILES, addon_fiyatlari={},
        )
