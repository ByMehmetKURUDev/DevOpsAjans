"""Faz 6K — eğitim Pages Function'ının Node testi pytest'le birlikte koşsun; rotalar ve ek dil paketleri.

Asıl test `app/frontend/scripts/egitim-fonksiyonu.test.mjs` (fetch, ASSETS ve HTMLRewriter taklitli). Node
yoksa atlanır. Ayrıca rotaların lazy olduğu, prerender edilmediği ve site haritasına girmediği, kamera
izninin yalnız Function'daki okutucu sayfasında açıldığı ve iki ek dil paketinin (panel `egitim`,
herkese açık `egitimSayfa`) yedi dilde aynı anahtarlarla gerçek çeviri taşıdığı doğrulanıyor.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_pages_fonksiyonu_node_testi():
    sonuc = subprocess.run(["node", "--test", "scripts/egitim-fonksiyonu.test.mjs"], cwd=ON_YUZ, capture_output=True,
                           text=True, timeout=120)
    assert sonuc.returncode == 0, sonuc.stdout[-3000:] + sonuc.stderr[-2000:]
    assert "# fail 0" in sonuc.stdout


def test_fonksiyon_dosyasi():
    metin = (ON_YUZ / "functions" / "egitim" / "[[yol]].js").read_text(encoding="utf-8")
    assert "export async function onRequest" in metin
    assert "env.API_ORIGIN" in metin and "IZINLER_KAMERA" in metin and "no-referrer" in metin
    assert "noindex, nofollow" in metin and "/api/v1/egitim/kurs/" in metin
    basliklar = (ON_YUZ / "public" / "_headers").read_text(encoding="utf-8")
    assert "camera=()" in basliklar
    # Kamera statik başlıklarda yalnız müşteri panelinde açık (Faz 6P: POS barkod okutma); /egitim/* izni fonksiyondan.
    yol, kamerali = None, []
    for satir in basliklar.splitlines():
        if satir.startswith("/"):
            yol = satir.strip()
        elif satir.strip().startswith("Permissions-Policy:") and "camera=(self)" in satir:
            kamerali.append(yol)
    assert kamerali == ["/client"], kamerali


def test_rotalar_lazy_prerender_disi_ve_site_haritasinda_yok():
    app = (ON_YUZ / "src" / "App.tsx").read_text(encoding="utf-8")
    for yol, gorunum in (("/egitim/ogrenci/:jeton", "ogrenci"), ("/egitim/yoklama/:jeton", "yoklama"),
                         ("/egitim/sertifika/:kod", "sertifika"), ("/egitim/okut/:kid/:oid", "okut"),
                         ("/egitim/kurum/:slug", "kurum"), ("/egitim/:slug", "kurs")):
        assert re.search(r'<Route path="%s" element=\{<EgitimSayfasi gorunum="%s" />\} />' % (re.escape(yol), gorunum), app), yol
    assert re.search(r"const EgitimSayfasi = lazy\(\(\) => import\('\./pages/EgitimSayfasi'\)\)", app)
    # Özel rotalar genel `/egitim/:slug`ten önce (yoksa "ogrenci" slug sanılır).
    assert app.index('path="/egitim/ogrenci/:jeton"') < app.index('path="/egitim/:slug"')
    kontrol = (ON_YUZ / "scripts" / "check-routes.mjs").read_text(encoding="utf-8")
    for yol in ("'/egitim/:slug'", "'/egitim/ogrenci/:jeton'", "'/egitim/yoklama/:jeton'", "'/egitim/sertifika/:kod'",
                "'/egitim/okut/:kid/:oid'", "'/egitim/kurum/:slug'"):
        assert yol in kontrol, yol
    site = (ON_YUZ / "prerender" / "site.js").read_text(encoding="utf-8")
    noindex = site[site.index("export const NOINDEX_ROUTES"):]
    assert "'/egitim'" in noindex[: noindex.index("];")]
    assert "/egitim" not in (ON_YUZ / "prerender" / "app.js").read_text(encoding="utf-8")


def _anahtarlar(d, on=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _anahtarlar(v, f"{on}{k}.")
        else:
            yield f"{on}{k}", v


def _yer_tutucular(metin: str):
    return sorted(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", metin)))


@pytest.mark.parametrize("paket", ["egitim", "egitimSayfa"])
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
    for d in ("en", "de", "ru", "zh", "hi", "ar"):
        diger = dict(_anahtarlar(veriler[d]))
        ayni = [k for k, v in tr.items() if diger[k] == v and len(v) > 4]
        assert len(ayni) <= max(3, len(tr) // 50), f"{paket}/{d}: çevrilmemiş görünen anahtarlar {ayni[:8]}"


def test_kodda_kullanilan_anahtarlar_pakette_var():
    kaynak = ON_YUZ / "src"
    panel = [kaynak / "components" / "Egitim.tsx", *sorted((kaynak / "components" / "egitim").glob("*.tsx")), kaynak / "lib" / "egitim.ts"]
    sayfa = [kaynak / "pages" / "EgitimSayfasi.tsx"]
    for paket, dosyalar, onek in (("egitim", panel, "egitim"), ("egitimSayfa", sayfa, "egitimSayfa")):
        tr = dict(_anahtarlar(json.loads((kaynak / "i18n" / "ek" / paket / "tr.json").read_text(encoding="utf-8"))))
        desen = re.compile(r"""['"`](%s\.[A-Za-z0-9_.]+)['"`]""" % re.escape(onek))
        bulunan = set()
        for dosya in dosyalar:
            bulunan |= set(desen.findall(dosya.read_text(encoding="utf-8")))
        eksik = sorted(k for k in bulunan if k not in tr)
        assert not eksik, f"{paket}: pakette olmayan anahtarlar {eksik[:20]}"
    # Okutucu (etkinlikten yeniden kullanılıyor) `egitimSayfa` önekiyle çalışıyor: gereken anahtarlar var.
    tr = dict(_anahtarlar(json.loads((kaynak / "i18n" / "ek" / "egitimSayfa" / "tr.json").read_text(encoding="utf-8"))))
    okutucu = (kaynak / "components" / "etkinlik" / "Okutucu.tsx").read_text(encoding="utf-8")
    for k in set(re.findall(r"\$\{onek\}\.([A-Za-z0-9_.]+)[`']", okutucu)):
        assert f"egitimSayfa.{k}" in tr, k
    for s in ("gecerli", "zaten_girdi", "gecersiz", "iptal", "farkli_etkinlik", "etkinlik_iptal", "kuyrukta"):
        assert f"egitimSayfa.okut.sonuc.{s}" in tr, s
