"""Faz 11A — Yönetici "Genel bakış" (komuta ekranı) özeti.

Yönetici  GET /api/v1/yonetim-ozeti   acil talep (SLA), KPI'lar, hizmet hattı, aktivite, kategori,
                                      saha, son işler, son bildirimler — tek istekte

Hesaplar ve tanımlar `services/yonetim_ozeti.py`'de. Sunucu önbelleği yok; ekran 60 sn'de bir
yokluyor (sekme görünmüyorken durur). Müşteri 403, oturumsuz 401.
"""

import logging

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from services import yonetim_ozeti as servis
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/yonetim-ozeti", tags=["yonetim-ozeti"])


def _yonetici_iste(request: Request):
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})
    return kullanici


@router.get("")
async def yonetim_ozeti(request: Request, db: AsyncSession = Depends(get_db)):
    kullanici = _yonetici_iste(request)
    veri = await servis.yonetim_ozeti(db, (kullanici.email or "").strip().lower())
    # Kişiye özel ve canlı: ara katmanlar saklamasın.
    return JSONResponse(veri, headers={"Cache-Control": "no-store"})
