"""Yönetici uçları için router düzeyi bekçi: oturumsuz 401, yönetici değilse 403.

Router'ın `dependencies=[Depends(yonetici_gerekli)]` listesine konuyor.
Bağımlılıklar gövde doğrulamasından ÖNCE çalıştığı için yetkisiz bir istek,
gövdesi hatalı olsa bile 422 değil 401/403 alıyor (uç var mı, gövde ne
bekliyor gibi bilgiler sızmıyor).
"""

from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import HTTPException, Request, status


async def yonetici_gerekli(request: Request) -> None:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli")
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
