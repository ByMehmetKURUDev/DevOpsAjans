"""Zamanlanmış görev ucu (Faz 2A) — ayrıntı `services/zamanli.py`.

POST /api/v1/zamanli/calistir
    Herkese açık; GitHub Actions her 10 dakikada çağırıyor. En çok 5
    dakikada bir gerçekten iş yapıyor, aksi hâlde 200 `{atlandi: true}`.
    `ZAMANLI_ANAHTAR` ortam değişkeni tanımlıysa `X-Zamanli-Anahtar`
    başlığı zorunlu (yanlış/eksikse 401).

GET  /api/v1/zamanli/yonetim            — son çalışmalar (yönetici)
POST /api/v1/zamanli/yonetim/calistir   — "şimdi çalıştır" (yönetici; 5 dk
    kuralını ve görev sıklıklarını atlıyor, çalışan turun kilidini ezmiyor)
"""

from typing import Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi import Depends as _Depends
from services import zamanli as servis
from sqlalchemy.ext.asyncio import AsyncSession

acik_router = APIRouter(prefix="/api/v1/zamanli", tags=["zamanli"])
yonetici_router = APIRouter(prefix="/api/v1/zamanli/yonetim", tags=["zamanli"])


def _yonetici_iste(request: Request) -> None:
    _, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")


@acik_router.post("/calistir")
async def calistir(
    x_zamanli_anahtar: Optional[str] = Header(default=None),
    db: AsyncSession = _Depends(get_db),
):
    if not servis.anahtar_gecerli_mi(x_zamanli_anahtar):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Anahtar geçersiz")
    sonuc = await servis.calistir(db, zorla=False)
    return servis.acik_yanit(sonuc)


@yonetici_router.get("")
async def durum(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return await servis.durum_listesi(db)


@yonetici_router.post("/calistir")
async def simdi_calistir(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    sonuc = await servis.calistir(db, zorla=True)
    liste = await servis.durum_listesi(db)
    return {"atlandi": bool(sonuc.get("atlandi")), "sebep": sonuc.get("sebep"), **liste}


router = (acik_router, yonetici_router)
