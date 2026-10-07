"""Modül vitrini yapısının ve fiyat anlık görüntüsünün ön yüz kopyalarını üretir (Faz 4V + 6R).

Çalıştırma (app/backend içinden):
    python -m scripts.modul_vitrini_tohum

İki dosya yazar:

* `app/frontend/prerender/modul-vitrini-veri.json` — modül kaydından
  (`core/moduller.py` + `core/sektor_paketleri.py` + `core/sektor_ayarlari.py`)
  vitrin yapısı. Prerender ve vitrin sayfası yapıyı bu dosyadan okuyor (derleme
  sunucuya bağlı kalmasın).
* `app/frontend/prerender/modul-vitrini-fiyat.json` — fiyat anlık görüntüsü
  (Faz 6R): fiyatlandırma v5 tohumundan (`scripts/seed_pricing_v5.py`) ölçek
  başına başlangıç aylık tutarı, Hizmetler sayfasıyla aynı `hesapla`. Derlemede
  canlı uç (`/api/v1/modul-vitrini`) okunamazsa prerender bunu kullanıyor;
  böylece JSON-LD `offers` sunucu uyurken de üretiliyor.

Kayıt ya da tohum değişip dosyalar güncellenmezse `tests/backend/test_modul_vitrini.py`
ve `tests/backend/test_sektor_paketi.py` düşer.

Yalnız standart kütüphane + saf Python kayıt/tohum modülleri: veritabanı gerekmez.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HEDEF = Path(__file__).resolve().parents[2] / "frontend" / "prerender" / "modul-vitrini-veri.json"
FIYAT_HEDEF = HEDEF.with_name("modul-vitrini-fiyat.json")


def metin() -> str:
    from services.modul_vitrini import yapi

    return json.dumps(yapi(), ensure_ascii=False, indent=2) + "\n"


def fiyat_metni() -> str:
    from services.modul_vitrini import anlik_goruntu

    return json.dumps(anlik_goruntu(), ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    HEDEF.write_text(metin(), encoding="utf-8")
    print(f"Yazıldı: {HEDEF}")
    FIYAT_HEDEF.write_text(fiyat_metni(), encoding="utf-8")
    print(f"Yazıldı: {FIYAT_HEDEF}")


if __name__ == "__main__":
    main()
