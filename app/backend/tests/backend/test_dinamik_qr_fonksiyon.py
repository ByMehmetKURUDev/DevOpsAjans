"""Faz 4Q — `/q/<kod>` Pages Function'ının Node testi pytest'le birlikte koşsun.

Asıl test `app/frontend/scripts/q-fonksiyonu.test.mjs` (fetch taklitli). Node
yoksa (ör. yalnız Python kurulu bir ortam) atlanır. Ayrıca robots.txt ve
servis çalışanının `/q/` yolunu dışarıda bıraktığı doğrulanıyor.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_pages_fonksiyonu_node_testi():
    sonuc = subprocess.run(
        ["node", "--test", "scripts/q-fonksiyonu.test.mjs"],
        cwd=ON_YUZ, capture_output=True, text=True, timeout=120,
    )
    assert sonuc.returncode == 0, sonuc.stdout[-3000:] + sonuc.stderr[-2000:]
    assert "# fail 0" in sonuc.stdout


def test_fonksiyon_dosyasi_tek_parcali_rota_ve_api_origin():
    metin = (ON_YUZ / "functions" / "q" / "[kod].js").read_text(encoding="utf-8")
    assert "export async function onRequest" in metin
    assert "redirect: 'manual'" in metin and "env.API_ORIGIN" in metin
    assert "X-MK-Istemci-IP" in metin and "X-MK-Ulke" in metin


def test_robots_ve_servis_calisani_q_yolunu_disarida_birakir():
    assert "Disallow: /q/" in (ON_YUZ / "public" / "robots.txt").read_text(encoding="utf-8")
    vite = (ON_YUZ / "vite.config.ts").read_text(encoding="utf-8")
    assert "disallow: ['/q/']" in vite
    sw = (ON_YUZ / "public" / "sw.js").read_text(encoding="utf-8")
    assert "url.pathname.startsWith('/q/')) return;" in sw
