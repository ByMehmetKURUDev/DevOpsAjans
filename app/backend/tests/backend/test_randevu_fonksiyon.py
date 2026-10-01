"""Faz 5R — randevu Pages Function'ı ve gömme betiğinin Node testleri pytest'le birlikte koşsun.

Asıl testler `app/frontend/scripts/randevu-fonksiyonu.test.mjs` (fetch, ASSETS ve
HTMLRewriter taklitli) ve `scripts/randevu-widget.test.mjs` (DOM taklidi). Node yoksa
atlanır. Ayrıca rotaların prerender edilmediği, site haritasına girmediği, uygulamada
lazy olduğu ve gömme betiğinin kaynağıyla birlikte depoda durduğu doğrulanıyor.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"


def _node_testi(dosya: str) -> None:
    sonuc = subprocess.run(
        ["node", "--test", dosya],
        cwd=ON_YUZ, capture_output=True, text=True, timeout=120,
    )
    assert sonuc.returncode == 0, sonuc.stdout[-3000:] + sonuc.stderr[-2000:]
    assert "# fail 0" in sonuc.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_pages_fonksiyonu_node_testi():
    _node_testi("scripts/randevu-fonksiyonu.test.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_gomme_betigi_node_testi():
    _node_testi("scripts/randevu-widget.test.mjs")


def test_fonksiyon_dosyasi_api_origin_assets_htmlrewriter():
    metin = (ON_YUZ / "functions" / "randevu" / "[[yol]].js").read_text(encoding="utf-8")
    assert "export async function onRequest" in metin
    assert "env.API_ORIGIN" in metin and "env.ASSETS" in metin and "new HTMLRewriter()" in metin
    for etiket in ("og:title", "og:image", "twitter:card", 'rel="canonical"', 'name="robots"', "X-Robots-Tag"):
        assert etiket in metin, etiket
    # Gömülü pencere başka sitelerin çerçevesinde açılabilmeli; normal sayfa açılamamalı.
    assert "frame-ancestors *" in metin and "SAMEORIGIN" in metin


def test_gomme_betigi_depoda_ve_kucuk():
    betik = ON_YUZ / "public" / "randevu-widget.js"
    assert betik.is_file()
    assert betik.stat().st_size < 4096
    assert (ON_YUZ / "scripts" / "randevu-widget.kaynak.js").is_file()
    assert (ON_YUZ / "scripts" / "randevu-widget-kucult.mjs").is_file()


def test_randevu_rotalari_lazy_prerender_disi_ve_site_haritasinda_yok():
    app = (ON_YUZ / "src" / "App.tsx").read_text(encoding="utf-8")
    for yol in ("/randevu/yonet/:jeton", "/randevu/:slug", "/randevu/:slug/:tur"):
        assert re.search(r'<Route path="%s" element=\{<RandevuSayfasi />\} />' % re.escape(yol), app), yol
    assert re.search(r"const RandevuSayfasi = ekliLazy\(", app)
    # Yönetim rotası, `:slug/:tur` kalıbından önce tanımlı (yoksa "yonet" bir sayfa adı sanılır).
    assert app.index('"/randevu/yonet/:jeton"') < app.index('"/randevu/:slug/:tur"')
    kontrol = (ON_YUZ / "scripts" / "check-routes.mjs").read_text(encoding="utf-8")
    for yol in ("'/randevu/:slug'", "'/randevu/:slug/:tur'", "'/randevu/yonet/:jeton'"):
        assert yol in kontrol, yol
    site = (ON_YUZ / "prerender" / "site.js").read_text(encoding="utf-8")
    noindex = site[site.index("export const NOINDEX_ROUTES"):]
    assert "'/randevu'" in noindex[: noindex.index("];")]
    prerender = (ON_YUZ / "prerender" / "app.js").read_text(encoding="utf-8")
    assert "/randevu/" not in prerender
