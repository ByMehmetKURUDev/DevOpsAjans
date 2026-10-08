"""Sağdan sola (ar) düzende yatay taşma koruması — kaynak taraması.

Bal küpü gibi görünmez alanlar `left: -9999px` / `-left-[9999px]` ile sayfanın dışına
itildiğinde soldan sağa dillerde sorun çıkmıyor, ama Arapçada sayfa sağdan başladığı için
o boşluk kaydırılabilir alana ekleniyor: belge 11 000 piksel genişliyor ve ekran boş kalıyor
(Ekim 2026, /ar/ortaklik). Doğru yol `sr-only` (ya da `BAL_KUPU` satır içi stili) ya da
mantıksal `-start-[…]`; fiziksel büyük negatif konum yasak.
"""

from __future__ import annotations

import re
from pathlib import Path

ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"
TARANAN = [ON_YUZ / "src", ON_YUZ / "scripts", ON_YUZ / "functions", ON_YUZ / "prerender"]
UZANTILAR = {".ts", ".tsx", ".js", ".mjs", ".css", ".html"}

# Tailwind: -left-[9999px], -right-[2000px], -end-[…] (sağdan sola ile soldan sağa ters yönde
# taşar), left-[-9999px], right-[-…]. `-start-[…]` güvenli: her iki yönde de kaydırılamayan
# tarafa itiyor.
TAILWIND = re.compile(r"(?<![\w-])(?:-(?:left|right|end|inset-x)-\[\d{3,}(?:px)?\]|(?:left|right|end|inset-x)-\[-\d{3,}(?:px)?\])")
# Satır içi stil / CSS: left: -10000px, left: '-10000px', right:-999px
STIL = re.compile(r"\b(?:left|right|insetInlineEnd|inset-inline-end)\s*:\s*['\"]?-\d{3,}")


def _dosyalar():
    for kok in TARANAN:
        if not kok.exists():
            continue
        for yol in kok.rglob("*"):
            if yol.suffix in UZANTILAR and "node_modules" not in yol.parts and yol.is_file():
                yield yol


def test_fiziksel_buyuk_negatif_konum_yok():
    bulgular = []
    for yol in _dosyalar():
        for no, satir in enumerate(yol.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            yalin = satir.strip()
            if yalin.startswith(("*", "//", "/*", "#")):
                continue  # açıklama satırı (sorunu anlatan notlar)
            if TAILWIND.search(satir) or STIL.search(satir):
                bulgular.append(f"{yol.relative_to(ON_YUZ)}:{no}: {yalin[:120]}")
    assert not bulgular, "Sağdan sola düzende yatay taşma açar:\n" + "\n".join(bulgular)


def test_desenler_bilinen_hatali_ornekleri_yakaliyor():
    for kotu in (
        '<div className="absolute -left-[9999px] h-px w-px">',
        "style={{ position: 'absolute', left: '-10000px' }}",
        "left: -9999px;",
        '<i className="-right-[2000px]" />',
        '<i className="left-[-5000px]" />',
        '<i className="-end-[9999px]" />',
    ):
        assert TAILWIND.search(kotu) or STIL.search(kotu), kotu
    for iyi in (
        '<div className="sr-only" aria-hidden="true">',
        '<div className="absolute -start-[9999px] h-px w-px">',
        '<div className="absolute -left-[38px] top-1">',  # küçük süs kayması, taşma yok
        "margin-left: -1.1em;",
    ):
        assert not (TAILWIND.search(iyi) or STIL.search(iyi)), iyi
