"""Modül bekçisi: müşteri isteğinde modül kapalıysa 403 `modul_kapali`.

Kullanım::

    musteri_router = APIRouter(
        prefix="/api/v1/kredilerim",
        dependencies=[Depends(modul_gerekli("krediler"))],
    )

* Yönetici hiç etkilenmiyor (ajansın kendi işinde bütün modüller açık).
* Oturumsuz istekte hiçbir şey yapmıyor: uç kendi 401'ini döndürsün
  (mevcut davranış ve testler değişmesin).
* Çekirdek modüller için sorgu bile atılmıyor.
"""

from core.database import get_db
from core.moduller import modul as _modul_bul
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession


def modul_gerekli(anahtar: str):
    """`anahtar` modülü kapalı müşteriyi 403 ile durduran FastAPI bağımlılığı."""
    tanim = _modul_bul(anahtar)
    if tanim is None:  # yazım hatası sessizce "her şey açık" olmasın
        raise ValueError(f"Bilinmeyen modül: {anahtar}")

    async def _bekci(request: Request, db: AsyncSession = Depends(get_db)) -> None:
        if tanim.cekirdek:
            return
        kullanici, yonetici = _yonetici_mi(request)
        if kullanici is None or yonetici:
            return
        eposta = (kullanici.email or "").strip().lower()
        if not eposta:
            return  # uç kendi 403'ünü veriyor
        from services.moduller import modul_acik_mi

        if not await modul_acik_mi(db, eposta, anahtar):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"kod": "modul_kapali", "modul": anahtar},
            )

    _bekci.__name__ = f"modul_gerekli_{anahtar}"
    return _bekci
