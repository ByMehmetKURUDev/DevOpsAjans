"""Faz 6E — etkinlik Pages Function'ları ve gömme betiğinin Node testleri pytest'le birlikte koşsun.

Asıl testler `app/frontend/scripts/etkinlik-fonksiyonu.test.mjs` (fetch, ASSETS ve HTMLRewriter
taklitli) ve `scripts/etkinlik-widget.test.mjs` (DOM taklidi). Node yoksa atlanır. Ayrıca rotaların
prerender edilmediği, site haritasına girmediği, uygulamada lazy olduğu, kamera izninin yalnız okutucu
sayfalarında açıldığı, gömme betiğinin kaynağıyla birlikte depoda durduğu ve iki ek dil paketinin
(panel `etkinlik`, herkese açık `etkinlikSayfa`) yedi dilde aynı anahtarlarla gerçek çeviri taşıdığı
doğrulanıyor.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")


def _node_testi(dosya: str) -> None:
    sonuc = subprocess.run(["node", "--test", dosya], cwd=ON_YUZ, capture_output=True, text=True, timeout=120)
    assert sonuc.returncode == 0, sonuc.stdout[-3000:] + sonuc.stderr[-2000:]
    assert "# fail 0" in sonuc.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_pages_fonksiyonu_node_testi():
    _node_testi("scripts/etkinlik-fonksiyonu.test.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_gomme_betigi_node_testi():
    _node_testi("scripts/etkinlik-widget.test.mjs")


def test_fonksiyon_dosyalari():
    metin = (ON_YUZ / "functions" / "etkinlik" / "[[yol]].js").read_text(encoding="utf-8")
    assert "export async function onRequest" in metin
    assert "env.API_ORIGIN" in metin and "env.ASSETS" in metin and "new HTMLRewriter()" in metin
    for etiket in ("og:title", "og:image", "twitter:card", 'rel="canonical"', 'name="robots"', "X-Robots-Tag",
                   "application/ld+json", "cspBasliklari", "vekilBasliklari", "camera=(self)", "no-referrer"):
        assert etiket in metin, etiket
    assert "frame-ancestors *" in metin and "SAMEORIGIN" in metin
    liste = (ON_YUZ / "functions" / "etkinlikler" / "[slug].js").read_text(encoding="utf-8")
    assert "export async function onRequest" in liste and "noindex, nofollow" in liste
    # Sitenin geri kalanında kamera kapalı kalıyor (Function okutucu sayfalarında açık; Faz 6P: bir de müşteri
    # panelinde — kasa ekranının barkod okutucusu — `/client` kuralında `camera=(self)`).
    basliklar = (ON_YUZ / "public" / "_headers").read_text(encoding="utf-8")
    kamerali, kural = set(), None
    for satir in basliklar.splitlines():
        if not satir.strip() or satir.strip().startswith("#"):
            continue
        if not satir[0].isspace():
            kural = satir.strip()
        elif satir.strip().lower().startswith("permissions-policy:") and "camera=(self)" in satir:
            kamerali.add(kural)
    assert "camera=()" in basliklar and kamerali == {"/client"}, kamerali


def test_gomme_betigi_depoda_ve_kucuk():
    betik = ON_YUZ / "public" / "etkinlik-widget.js"
    assert betik.is_file() and betik.stat().st_size < 4096
    assert (ON_YUZ / "scripts" / "etkinlik-widget.kaynak.js").is_file()
    assert (ON_YUZ / "scripts" / "etkinlik-widget-kucult.mjs").is_file()


def test_etkinlik_rotalari_lazy_prerender_disi_ve_site_haritasinda_yok():
    app = (ON_YUZ / "src" / "App.tsx").read_text(encoding="utf-8")
    for yol, gorunum in (("/etkinlik/giris/:jeton", "giris"), ("/etkinlik/okut/:eid", "okut"),
                         ("/etkinlik/:slug/bilet/:jeton", "bilet"), ("/etkinlik/:slug", "etkinlik"),
                         ("/etkinlikler/:slug", "liste")):
        assert re.search(r'<Route path="%s" element=\{<EtkinlikSayfasi gorunum="%s" />\} />' % (re.escape(yol), gorunum), app), yol
    assert re.search(r"const EtkinlikSayfasi = lazy\(\(\) => import\('\./pages/EtkinlikSayfasi'\)\)", app)
    kontrol = (ON_YUZ / "scripts" / "check-routes.mjs").read_text(encoding="utf-8")
    for yol in ("'/etkinlik/:slug'", "'/etkinlik/:slug/bilet/:jeton'", "'/etkinlik/giris/:jeton'", "'/etkinlik/okut/:eid'",
                "'/etkinlikler/:slug'"):
        assert yol in kontrol, yol
    site = (ON_YUZ / "prerender" / "site.js").read_text(encoding="utf-8")
    noindex = site[site.index("export const NOINDEX_ROUTES"):]
    noindex = noindex[: noindex.index("];")]
    assert "'/etkinlik'" in noindex and "'/etkinlikler'" in noindex
    prerender = (ON_YUZ / "prerender" / "app.js").read_text(encoding="utf-8")
    assert "/etkinlik" not in prerender


def _anahtarlar(d, on=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _anahtarlar(v, f"{on}{k}.")
        else:
            yield f"{on}{k}", v


def _yer_tutucular(metin: str):
    return sorted(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", metin)))


@pytest.mark.parametrize("paket", ["etkinlik", "etkinlikSayfa"])
def test_ek_paket_yedi_dilde_tutarli_ve_cevrilmis(paket):
    veriler = {d: json.loads((ON_YUZ / "src" / "i18n" / "ek" / paket / f"{d}.json").read_text(encoding="utf-8")) for d in DILLER}
    tr = dict(_anahtarlar(veriler["tr"]))
    assert tr, "boş paket"
    for d in DILLER[1:]:
        diger = dict(_anahtarlar(veriler[d]))
        assert set(diger) == set(tr), f"{paket}/{d}: eksik {sorted(set(tr) - set(diger))[:5]} fazla {sorted(set(diger) - set(tr))[:5]}"
        for k, v in tr.items():
            assert isinstance(diger[k], str) and diger[k].strip(), f"{paket}/{d}: {k} boş"
            assert _yer_tutucular(diger[k]) == _yer_tutucular(v), f"{paket}/{d}: {k} yer tutucu farklı"
            assert "{{count}}" not in diger[k], f"{paket}/{d}: {k} count kullanıyor"
    # Gerçek çeviri: Türkçe ile birebir aynı kalan metin oranı düşük (marka/kısaltmalar hariç).
    for d in ("en", "de", "ru", "zh", "hi", "ar"):
        diger = dict(_anahtarlar(veriler[d]))
        ayni = [k for k, v in tr.items() if diger[k] == v and len(v) > 4]
        assert len(ayni) <= max(3, len(tr) // 50), f"{paket}/{d}: çevrilmemiş görünen anahtarlar {ayni[:8]}"


def _kullanilan_anahtarlar(dosyalar, onek):
    desen = re.compile(r"""t\(\s*['"`](%s\.[A-Za-z0-9_.]+)['"`]""" % re.escape(onek))
    bulunan = set()
    for dosya in dosyalar:
        bulunan |= set(desen.findall(dosya.read_text(encoding="utf-8")))
    return bulunan


def test_kodda_kullanilan_anahtarlar_pakette_var():
    kaynak = ON_YUZ / "src"
    panel = [kaynak / "components" / "Etkinlik.tsx", *sorted((kaynak / "components" / "etkinlik").glob("*.tsx")), kaynak / "lib" / "etkinlik.ts"]
    sayfa = [kaynak / "pages" / "EtkinlikSayfasi.tsx", kaynak / "components" / "etkinlik" / "Okutucu.tsx"]
    for paket, dosyalar, onek in (("etkinlik", panel, "etkinlik"), ("etkinlikSayfa", sayfa, "etkinlikSayfa")):
        tr = dict(_anahtarlar(json.loads((kaynak / "i18n" / "ek" / paket / "tr.json").read_text(encoding="utf-8"))))
        eksik = sorted(k for k in _kullanilan_anahtarlar(dosyalar, onek) if k not in tr)
        assert not eksik, f"{paket}: pakette olmayan anahtarlar {eksik[:20]}"
