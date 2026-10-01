"""Faz 4K — `/kart/<slug>` paylaşım önizlemesi Pages Function'ının Node testi pytest'le birlikte koşsun.

Asıl test `app/frontend/scripts/kart-fonksiyonu.test.mjs` (fetch / ASSETS / HTMLRewriter
taklitli). Node yoksa atlanır. Ayrıca rota yapısı (prerender yok, site haritası dışı,
dil önekli adres kök adrese yönleniyor) ve servis çalışanına dokunulmadığı doğrulanıyor.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_kart_fonksiyonu_node_testi():
    sonuc = subprocess.run(
        ["node", "--test", "scripts/kart-fonksiyonu.test.mjs"],
        cwd=ON_YUZ, capture_output=True, text=True, timeout=120,
    )
    assert sonuc.returncode == 0, sonuc.stdout[-3000:] + sonuc.stderr[-2000:]
    assert "# fail 0" in sonuc.stdout


def test_fonksiyon_dosyasi_htmlrewriter_assets_ve_api_origin():
    metin = (ON_YUZ / "functions" / "kart" / "[slug].js").read_text(encoding="utf-8")
    assert "export async function onRequest" in metin
    assert "env.ASSETS.fetch" in metin and "env.API_ORIGIN" in metin and "new HTMLRewriter()" in metin
    assert "/api/v1/kart/" in metin and "/ozet" in metin
    for etiket in ("og:title", "og:image", "twitter:card", "canonical", "robots"):
        assert etiket in metin, etiket


def test_rotalar_prerender_disi_ve_site_haritasinda_yok():
    app = (ON_YUZ / "src" / "App.tsx").read_text(encoding="utf-8")
    for yol in ('path="/kart/:slug"', 'path="/yorum/:slug"', 'path="/:lang/kart/:slug"', 'path="/:lang/yorum/:slug"'):
        assert yol in app, yol
    kontrol = (ON_YUZ / "scripts" / "check-routes.mjs").read_text(encoding="utf-8")
    for yol in ("'/kart/:slug'", "'/yorum/:slug'", "'/:lang/kart/:slug'", "'/:lang/yorum/:slug'"):
        assert yol in kontrol, yol
    site = (ON_YUZ / "prerender" / "site.js").read_text(encoding="utf-8")
    assert "'/kart'" in site and "'/yorum'" in site
    # Servis çalışanı bu fazda değişmedi (paralel iş: public/sw.js'e dokunulmuyor).
    sw = (ON_YUZ / "public" / "sw.js").read_text(encoding="utf-8")
    assert "/kart/" not in sw


def _duz(sozluk, on=""):
    for anahtar, deger in sozluk.items():
        if isinstance(deger, dict):
            yield from _duz(deger, f"{on}{anahtar}.")
        else:
            yield f"{on}{anahtar}", deger


@pytest.mark.parametrize("klasor", ["ek/kartvizit", "kartSayfasi"])
def test_ceviri_paketleri_yedi_dilde_ayni_anahtarlar(klasor):
    """Panel (ek/kartvizit) ve herkese açık sayfa (kartSayfasi) paketleri: 7 dil, aynı anahtarlar, boş metin yok."""
    import json

    kok = ON_YUZ / "src" / "i18n" / klasor
    paketler = {}
    for dil in ("tr", "en", "de", "ru", "zh", "hi", "ar"):
        veri = json.loads((kok / f"{dil}.json").read_text(encoding="utf-8"))
        paketler[dil] = dict(_duz(veri))
    temel = set(paketler["tr"])
    assert len(temel) > 50
    for dil, anahtarlar in paketler.items():
        assert set(anahtarlar) == temel, (dil, sorted(set(anahtarlar) ^ temel)[:10])
        bos = [a for a, d in anahtarlar.items() if not str(d).strip()]
        assert not bos, (dil, bos[:5])
    # Çeviri gerçekten yapılmış: Arapça paketin çoğu Türkçeden farklı.
    ayni = [a for a in temel if paketler["ar"][a] == paketler["tr"][a]]
    assert len(ayni) < len(temel) * 0.1, ayni[:10]
