"""Faz 4G — aydınlatma ile açık rızanın ayrılması: metin tutarlılığı ve gömülü betik.

Uç davranışları `test_crm.py` (form) ve `test_site_analizi.py` (tam rapor)
içinde; burada:
* site analizi sayfasının pazarlama kutusu metni (ön yüz ek paketi) ile
  sunucunun kaydettiği metin sürümünün metni AYNI (7 dil) — biri değişip
  diğeri unutulursa kayıttaki sürüm yanlış metni gösterirdi,
* gömülü form betiğinde (`public/crm-form.js`) zorunlu onay kutusu yok,
  pazarlama kutusu isteğe bağlı ve betik küçük kalıyor.
"""

import json
import re
from pathlib import Path

from services import crm_form, pazarlama_izni

ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")


def test_site_analizi_pazarlama_metni_sunucudakiyle_ayni():
    for dil in DILLER:
        paket = json.loads((ON_YUZ / "src/i18n/ek/siteAnalizi" / f"{dil}.json").read_text(encoding="utf-8"))
        tam = paket["siteAnalizi"]["tamRapor"]
        assert tam["pazarlama"] == pazarlama_izni.METINLER[dil], dil
        assert tam["istegeBagli"] and "kvkk" not in tam, dil
    assert pazarlama_izni.surum_etiketi("AR") == f"{pazarlama_izni.METIN_SURUMU}/ar"
    assert pazarlama_izni.surum_etiketi("xx") == f"{pazarlama_izni.METIN_SURUMU}/tr"


def test_form_aydinlatma_satiri_sitedekiyle_ayni():
    """Gömülü formun hazır aydınlatma satırı sitedeki (Faz 3Y) satırla aynı cümle."""
    for dil in DILLER:
        paket = json.loads((ON_YUZ / "src/i18n/ek/aydinlatma" / f"{dil}.json").read_text(encoding="utf-8"))
        assert crm_form.ETIKETLER[dil]["aydinlatma_satiri"] == paket["aydinlatma"]["satir"], dil


def test_izin_yalniz_json_true():
    assert pazarlama_izni.izin_verildi_mi(True)
    for deger in ("true", 1, "1", None, False, {"x": 1}):
        assert not pazarlama_izni.izin_verildi_mi(deger), deger
    assert pazarlama_izni.ayar_acik_mi("1") and not pazarlama_izni.ayar_acik_mi("0") and not pazarlama_izni.ayar_acik_mi(None)


def test_gomulu_betikte_zorunlu_onay_kutusu_yok():
    kaynak = (ON_YUZ / "scripts/crm-form.kaynak.js").read_text(encoding="utf-8")
    betik = (ON_YUZ / "public/crm-form.js").read_text(encoding="utf-8")
    # Onay kutusu zorunlu değil, gönderimde kvkk_onay yok; pazarlama kutusu isteğe bağlı.
    assert not re.search(r"type:\s*'checkbox',\s*required", kaynak)
    assert "kvkk_onay" not in kaynak and "kvkk_onay" not in betik
    assert "kvkk_gerekli" not in kaynak
    assert "pazarlama_izni" in betik and "data-aydinlatma" in betik
    # Eski tanım adı (`kvkk`) da okunuyor: önbellekte kalan sayfalar kırılmasın.
    assert "t.aydinlatma || t.kvkk" in kaynak
    # Küçük kalıyor (ana uygulama paketine girmiyor; ~4 kB).
    assert len(betik.encode("utf-8")) < 4800
