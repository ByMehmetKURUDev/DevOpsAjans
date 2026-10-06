"""Modül vitrini yapısının ön yüz kopyasını üretir (Faz 4V).

Çalıştırma (app/backend içinden):
    python -m scripts.modul_vitrini_tohum

`app/frontend/prerender/modul-vitrini-veri.json` dosyasını modül kaydından
(`core/moduller.py` + `core/sektor_paketleri.py`) yeniden yazar. Prerender ve
vitrin sayfası yapıyı bu dosyadan okuyor (derleme sunucuya bağlı kalmasın);
fiyat yok, fiyat canlı uçtan. Kayıt değişip bu dosya güncellenmezse
`tests/backend/test_modul_vitrini.py` düşer.

Yalnız standart kütüphane + saf Python kayıt modülleri: veritabanı gerekmez.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HEDEF = Path(__file__).resolve().parents[2] / "frontend" / "prerender" / "modul-vitrini-veri.json"


def metin() -> str:
    from services.modul_vitrini import yapi

    return json.dumps(yapi(), ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    HEDEF.write_text(metin(), encoding="utf-8")
    print(f"Yazıldı: {HEDEF}")


if __name__ == "__main__":
    main()
