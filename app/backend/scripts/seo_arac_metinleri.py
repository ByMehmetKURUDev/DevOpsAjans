"""Ücretsiz SEO araçlarının sonuç e-postası için metin özetini üretir (Faz 4S).

Çalıştırma (app/backend içinden):
    python -m scripts.seo_arac_metinleri

Yazdığı dosya: `app/backend/data/seo_arac_metinleri.json` — 7 dilde araç adı,
kontrol adı, seviye adı ve bulgu cümlesi. Kaynak ön yüzün ek paketleri
(`src/i18n/ek/seoAraclari`, `src/i18n/ek/seoAracSonuc`); sunucu (Render) yalnız
`app/backend`'i gördüğü için kopya burada tutuluyor. "Sonucu e-postayla gönder"
e-postası bulguları ziyaretçinin dilinde bu dosyadan kuruyor
(`services/seo_araclari.eposta_icerigi`).

Ön yüz metinleri değişip dosya güncellenmezse `tests/backend/test_seo_araclari.py` düşer.
Yalnız standart kütüphane: veritabanı gerekmez.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EK = Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "ek"
HEDEF = Path(__file__).resolve().parents[1] / "data" / "seo_arac_metinleri.json"


def uret() -> dict:
    from services.seo_araclari import ARAC_ANAHTARI, DILLER

    sonuc = {}
    for dil in DILLER:
        arac = json.loads((EK / "seoAraclari" / f"{dil}.json").read_text("utf-8"))["seoAraclari"]
        son = json.loads((EK / "seoAracSonuc" / f"{dil}.json").read_text("utf-8"))["seoAracSonuc"]
        sonuc[dil] = {
            "arac": {slug: arac["arac"][anahtar]["ad"] for slug, anahtar in ARAC_ANAHTARI.items()},
            "seviye": dict(son["seviye"]),
            "kontrol": {k: v["ad"] for k, v in sorted(son["kontrol"].items())},
            "bulgu": dict(sorted(son["bulgu"].items())),
        }
    return sonuc


def metin() -> str:
    return json.dumps(uret(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main() -> None:
    HEDEF.write_text(metin(), encoding="utf-8")
    print(f"Yazıldı: {HEDEF} ({HEDEF.stat().st_size // 1024} kB)")


if __name__ == "__main__":
    main()
