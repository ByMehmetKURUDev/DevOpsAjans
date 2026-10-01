"""Faz 4M — `/menu/<slug>` Pages Function'ının Node testi pytest'le birlikte koşsun.

Asıl test `app/frontend/scripts/menu-fonksiyonu.test.mjs` (fetch, ASSETS ve
HTMLRewriter taklitli). Node yoksa atlanır. Ayrıca rotanın prerender edilmediği,
site haritasına girmediği ve uygulamada lazy olduğu doğrulanıyor.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_pages_fonksiyonu_node_testi():
    sonuc = subprocess.run(
        ["node", "--test", "scripts/menu-fonksiyonu.test.mjs"],
        cwd=ON_YUZ, capture_output=True, text=True, timeout=120,
    )
    assert sonuc.returncode == 0, sonuc.stdout[-3000:] + sonuc.stderr[-2000:]
    assert "# fail 0" in sonuc.stdout


def test_fonksiyon_dosyasi_api_origin_assets_htmlrewriter():
    metin = (ON_YUZ / "functions" / "menu" / "[slug].js").read_text(encoding="utf-8")
    assert "export async function onRequest" in metin
    assert "env.API_ORIGIN" in metin and "env.ASSETS" in metin and "new HTMLRewriter()" in metin
    for etiket in ("og:title", "og:image", "twitter:card", 'rel="canonical"', 'name="robots"'):
        assert etiket in metin, etiket


def test_menu_rotasi_lazy_prerender_disi_ve_site_haritasinda_yok():
    app = (ON_YUZ / "src" / "App.tsx").read_text(encoding="utf-8")
    assert re.search(r'<Route path="/menu/:slug" element=\{<MenuSayfasi />\} />', app)
    assert re.search(r"const MenuSayfasi = ekliLazy\(", app)
    kontrol = (ON_YUZ / "scripts" / "check-routes.mjs").read_text(encoding="utf-8")
    assert "'/menu/:slug'" in kontrol
    site = (ON_YUZ / "prerender" / "site.js").read_text(encoding="utf-8")
    noindex = site[site.index("export const NOINDEX_ROUTES"):]
    assert "'/menu'" in noindex[: noindex.index("];")]
    prerender = (ON_YUZ / "prerender" / "app.js").read_text(encoding="utf-8")
    assert "/menu/" not in prerender
