"""Faz 5A — AI asistan Pages Function'ı ve gömme betiğinin Node testleri pytest'le birlikte koşsun.

Asıl testler `app/frontend/scripts/asistan-fonksiyonu.test.mjs` (fetch, ASSETS ve
HTMLRewriter taklitli) ve `scripts/asistan-widget.test.mjs` (DOM taklidi). Node yoksa
atlanır. Ayrıca rotanın prerender edilmediği, site haritasına girmediği, uygulamada lazy
olduğu, gömme betiğinin kaynağıyla birlikte depoda ve küçük olduğu, ajansın kendi sitesindeki
sohbetin (AsistanSohbeti) yerine geçmediği doğrulanıyor.
"""

import gzip
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
    _node_testi("scripts/asistan-fonksiyonu.test.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_gomme_betigi_node_testi():
    _node_testi("scripts/asistan-widget.test.mjs")


def test_fonksiyon_dosyasi_csp_ve_noindex():
    metin = (ON_YUZ / "functions" / "asistan" / "[[yol]].js").read_text(encoding="utf-8")
    assert "export async function onRequest" in metin
    assert "env.API_ORIGIN" in metin and "env.ASSETS" in metin and "new HTMLRewriter()" in metin
    assert "cspBasliklari" in metin and "SAMEORIGIN" in metin and "X-Robots-Tag" in metin
    assert "noindex, nofollow" in metin


def test_gomme_betigi_depoda_ve_kucuk():
    betik = ON_YUZ / "public" / "asistan-widget.js"
    assert betik.is_file()
    assert len(gzip.compress(betik.read_bytes())) < 6 * 1024
    assert (ON_YUZ / "scripts" / "asistan-widget.kaynak.js").is_file()
    assert (ON_YUZ / "scripts" / "asistan-widget-kucult.mjs").is_file()


def test_asistan_rotasi_lazy_prerender_disi_ve_noindex():
    app = (ON_YUZ / "src" / "App.tsx").read_text(encoding="utf-8")
    assert re.search(r'<Route path="/asistan/:anahtar" element=\{<AsistanSayfasi />\} />', app)
    assert re.search(r"const AsistanSayfasi = lazy\(\(\) => import\('\./pages/AsistanSayfasi'\)\)", app)
    kontrol = (ON_YUZ / "scripts" / "check-routes.mjs").read_text(encoding="utf-8")
    assert "'/asistan/:anahtar'" in kontrol
    site = (ON_YUZ / "prerender" / "site.js").read_text(encoding="utf-8")
    noindex = site[site.index("export const NOINDEX_ROUTES"):]
    assert "'/asistan'" in noindex[: noindex.index("];")]
    prerender = (ON_YUZ / "prerender" / "app.js").read_text(encoding="utf-8")
    assert "/asistan/" not in prerender


def test_ajansin_site_sohbeti_yerinde():
    """Ajansın kendi asistanı yalnız panelde; sitedeki mevcut sohbet (Layout › AsistanSohbeti) yerinde."""
    layout = (ON_YUZ / "src" / "components" / "Layout.tsx").read_text(encoding="utf-8")
    assert "AsistanSohbeti" in layout
    assert "aiAsistan" not in layout and "asistan-widget" not in layout
    for dosya in (ON_YUZ / "src").rglob("*.tsx"):
        metin = dosya.read_text(encoding="utf-8")
        assert not re.search(r"<script[^>]+asistan-widget", metin), dosya
