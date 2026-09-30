"""Veritabanı içeriği çevirileri — ortak yardımcılar.

Sitede gösterilen bazı içerikler (fiyat kataloğu, marketplace ürünleri)
veritabanında Türkçe duruyor. Her satırda `ceviriler` adlı bir JSON metni
var: ``{"en": {"title": "..."}, "de": {...}}``. Site seçili dilde alan
varsa onu, yoksa Türkçe alanı gösteriyor.
"""

import json
from typing import Any, Dict, Optional

#: Türkçe ana alanlarda; çeviri tutulan diller.
CEVIRI_DILLERI = ("en", "de", "ru", "zh", "hi", "ar")


def ceviriler_coz(deger: Any) -> Optional[Dict[str, Any]]:
    """Sütundaki JSON metnini sözlüğe çevirir; bozuksa ya da boşsa None."""
    if deger is None or isinstance(deger, dict):
        return deger
    try:
        cozulen = json.loads(deger)
    except (TypeError, ValueError):
        return None
    return cozulen if isinstance(cozulen, dict) else None


def ceviriyi_metne_cevir(veri: Dict[str, Any]) -> Dict[str, Any]:
    """Yazılacak veride `ceviriler` sözlükse sütun için JSON metnine çevirir."""
    if isinstance(veri.get("ceviriler"), dict):
        veri["ceviriler"] = json.dumps(veri["ceviriler"], ensure_ascii=False)
    return veri
