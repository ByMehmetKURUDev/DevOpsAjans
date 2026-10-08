"""Faz 7K — PDF yazı tipi yedek zincirinin dosyalarını üretir (bir kez çalıştırılır; çıktı depoda).

ReportLab woff2 ve CFF (OTF) okuyamıyor; yalnız TrueType (glyf) TTF. Kaynaklar (hepsi SIL OFL 1.1):

* Noto Sans (Kiril, Yunan, Latin genişletilmiş), Noto Sans Arabic, Noto Sans Devanagari: npm'deki
  `@fontsource/noto-sans`, `@fontsource/noto-sans-arabic`, `@fontsource/noto-sans-devanagari`
  (5.x) paketlerinin 400/700 statik woff2 alt kümeleri → TTF (glif ve GSUB/GPOS olduğu gibi;
  Devanagari şekillendirmesi için şart).

Çince (CJK) için dosya ÜRETİLMİYOR: `services/pdf_yazi.py` ReportLab'ın gömülmeyen CID yazı tipi
STSong-Light'ı kullanıyor (binlerce ideogramlık bir alt küme bile MB'larca tutuyor).

Kullanım:
    python -m scripts.pdf_fontlari_uret --fontsource <npm paketlerinin açıldığı dizin>
"""

import argparse
from pathlib import Path

from fontTools.ttLib import TTFont

HEDEF = Path(__file__).resolve().parents[1] / "data" / "fonts"

#: (fontsource paketi, alt küme dosya öneki, çıktı adı)
WOFF2 = [
    ("noto-sans", "noto-sans-cyrillic", "NotoSans-Kiril"),
    ("noto-sans", "noto-sans-greek", "NotoSans-Yunan"),
    ("noto-sans", "noto-sans-latin-ext", "NotoSans-LatinEk"),
    ("noto-sans-arabic", "noto-sans-arabic-arabic", "NotoSansArabic"),
    ("noto-sans-devanagari", "noto-sans-devanagari-devanagari", "NotoSansDevanagari"),
]
KALINLIK = {"400": "Regular", "700": "Bold"}


def woff2_ttf(kaynak: Path) -> None:
    for paket, onek, ad in WOFF2:
        for agirlik, son in KALINLIK.items():
            f = TTFont(kaynak / paket / "package" / "files" / f"{onek}-{agirlik}-normal.woff2")
            f.flavor = None
            # Noto Sans alt kümelerinin PostScript adı aynı ("NotoSans-Regular"); ReportLab PDF'teki
            # yazı tipi nesnelerini bu adla adlandırdığı için çakışıp yanlış glif dosyası
            # kullanılıyordu (Kiril boş çıktı). Her dosyaya ayrı ad.
            f["name"].setName(f"{ad}-{son}", 6, 3, 1, 0x409)
            f["name"].setName(f"{ad}-{son}", 6, 1, 0, 0)
            cikti = HEDEF / f"{ad}-{son}.ttf"
            f.save(cikti)
            print(cikti.name, cikti.stat().st_size)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fontsource", required=True, type=Path)
    woff2_ttf(ap.parse_args().fontsource)


if __name__ == "__main__":
    main()
