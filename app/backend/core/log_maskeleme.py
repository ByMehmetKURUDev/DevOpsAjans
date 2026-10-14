"""Erişim kaydında gizli sorgu değerlerini maskeleme (Parti 14).

Uvicorn erişim satırı isteğin tam yolunu sorgusuyla birlikte yazıyor. OAuth geri
dönüşlerinde bu yol tek kullanımlık yetki kodunu (`code`) ve `state` değerini
taşıyor (`/api/v1/baglantilar/meta/geri-donus?code=…&state=…`). Kod kısa ömürlü
olsa da günlük kayıtları üçüncü taraf bir panelde (Render) duruyor; değerin orada
düz metin kalmasına gerek yok.

Filtre yalnız `uvicorn.access` kaydına takılıyor ve yalnız adı aşağıdaki
listedeki sorgu parametrelerinin DEĞERİNİ `***` yapıyor: yol, parametre adları
ve diğer değerler olduğu gibi kalıyor (hata ayıklarken hangi ucun çağrıldığı
görünmeye devam ediyor).
"""

from __future__ import annotations

import logging

GIZLI_PARAMETRELER = frozenset(
    {
        "code",
        "state",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "jeton",
        "key",
        "api_key",
        "anahtar",
        "secret",
        "client_secret",
        "password",
        "sifre",
        "signature",
        "imza",
        "sig",
    }
)

MASKE = "***"


def sorguyu_maskele(yol: str) -> str:
    """`/a?code=x&b=1` → `/a?code=***&b=1`. Sorgusuz yol aynen döner."""
    if not isinstance(yol, str) or "?" not in yol:
        return yol
    govde, sorgu = yol.split("?", 1)
    parcalar = []
    for parca in sorgu.split("&"):
        ad, esittir, deger = parca.partition("=")
        if esittir and deger and ad.lower() in GIZLI_PARAMETRELER:
            parcalar.append(f"{ad}={MASKE}")
        else:
            parcalar.append(parca)
    return f"{govde}?{'&'.join(parcalar)}"


class ErisimKaydiMaskesi(logging.Filter):
    """Uvicorn erişim kaydının argümanlarındaki yolu maskeler.

    Uvicorn `AccessFormatter` argüman sırası: (istemci, yöntem, tam_yol, http_sürümü, durum).
    Biçim değişirse filtre hiçbir şeye dokunmadan kaydı geçiriyor.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API adı
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            maskeli = sorguyu_maskele(args[2])
            if maskeli is not args[2]:
                record.args = (*args[:2], maskeli, *args[3:])
        return True


def erisim_kaydini_maskele() -> None:
    """Filtreyi bir kez takar (tekrar çağrılırsa ikinci kopya eklenmez)."""
    kayitci = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, ErisimKaydiMaskesi) for f in kayitci.filters):
        kayitci.addFilter(ErisimKaydiMaskesi())
