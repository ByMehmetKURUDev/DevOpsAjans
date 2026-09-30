"""İsteği yapanın IP'si ve saklanabilir özeti.

Site analizi (sınır sayımı) ve denetim kaydı aynı kuralı kullanıyor; iki
ayrı kopya zamanla birbirinden ayrışırdı, bu yüzden tek yerde duruyor.

Ham IP hiçbir yerde saklanmıyor; yalnız tuzlanmış sha256 özeti. "Aynı
kaynak mı" sorusunu cevaplamak yetiyor, kim olduğunu bilmek gerekmiyor.
"""

import hashlib
import ipaddress
import os
from typing import Any


def istemci_ip(request: Any) -> str:
    """İsteği yapanın IP'si.

    1. X-MK-Istemci-IP: sitenin /api vekili (functions/api/[[path]].js)
       ziyaretçinin CF-Connecting-IP değerini buna yazıyor. Vekil Render'a
       Worker alt isteğiyle gittiği için Render'a varan CF-Connecting-IP
       artık ziyaretçinin değil Worker'ın adresi olur — hepsi tek IP sayılırdı.
       (Render adresine doğrudan gelen biri bu başlığı uydurabilir; o zaman
       yalnız IP sınırını atlar, alan adı sınırı yine işler.)
    2. CF-Connecting-IP: Cloudflare yazıyor, istemci değiştiremiyor.
    3. X-Forwarded-For'un ilk değeri — istemci yazabildiği için en son.
    4. Doğrudan bağlantıda soket adresi.
    """
    vekil = (request.headers.get("x-mk-istemci-ip") or "").strip()
    if vekil:
        try:
            return str(ipaddress.ip_address(vekil))
        except ValueError:
            pass
    cf = (request.headers.get("cf-connecting-ip") or "").strip()
    if cf:
        return cf
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff:
        return xff
    return request.client.host if request.client else "bilinmiyor"


def ip_ozeti(ip: str) -> str:
    """Tuzlanmış sha256 özeti (tuz: IP_OZET_TUZU ortam değişkeni)."""
    tuz = os.environ.get("IP_OZET_TUZU", "")
    return hashlib.sha256(f"{tuz}{ip}".encode("utf-8")).hexdigest()
