"""Faz 3Z — proje şablonları (yalnız yönetici).

    GET    /api/v1/proje-sablonlari                    liste (tablo boşsa 3 hazır örnek yazılır)
    POST   /api/v1/proje-sablonlari                    yeni şablon
    GET    /api/v1/proje-sablonlari/{id}
    PUT    /api/v1/proje-sablonlari/{id}
    DELETE /api/v1/proje-sablonlari/{id}               (çöp kutusuna)
    POST   /api/v1/proje-sablonlari/{id}/proje-olustur {baslangic_tarihi, baslik?, client_email?, client_name?, aciklama?, kategori?}
    POST   /api/v1/proje-sablonlari/{id}/uygula        {proje_id, baslangic_tarihi?} — mevcut projeye görevleri ekle
    POST   /api/v1/proje-sablonlari/projeden/{proje_id} {ad?, aciklama?, tahmini_saat?} — projenin görevlerinden şablon

Teklif entegrasyonu `services/teklifler.py` içinde (`proje_sablon_id`).
"""

import logging
from typing import Any, Dict, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from pydantic import BaseModel, ConfigDict
from services import proje_sablonlari as ps
from services.gorevler import eposta_duzelt, proje_bul
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/proje-sablonlari", tags=["proje-sablonlari"], dependencies=[_Depends(yonetici_gerekli)])


class Govde(BaseModel):
    model_config = ConfigDict(extra="allow")


def _govde(g: Optional[Govde]) -> Dict[str, Any]:
    if g is None:
        return {}
    veri = g.model_dump(exclude_unset=True)
    veri.update(g.model_extra or {})
    return veri


def _yonetici(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})
    return eposta_duzelt(kullanici.email)


@router.get("")
async def listele(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici(request)
    return {"sablonlar": await ps.listele(db)}


@router.post("")
async def olustur(request: Request, govde: Govde = Body(...), db: AsyncSession = _Depends(get_db)):
    ben = _yonetici(request)
    return ps.sozluk(await ps.olustur(db, _govde(govde), ben))


@router.post("/projeden/{proje_id}")
async def projeden(proje_id: int, request: Request, govde: Optional[Govde] = Body(None), db: AsyncSession = _Depends(get_db)):
    ben = _yonetici(request)
    proje = await proje_bul(db, proje_id)
    return ps.sozluk(await ps.projeden_kaydet(db, proje, _govde(govde), ben))


@router.get("/{sablon_id}")
async def getir(sablon_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici(request)
    return ps.sozluk(await ps.bul(db, sablon_id))


@router.put("/{sablon_id}")
async def guncelle(sablon_id: int, request: Request, govde: Govde = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici(request)
    return ps.sozluk(await ps.guncelle(db, await ps.bul(db, sablon_id), _govde(govde)))


@router.delete("/{sablon_id}")
async def sil(sablon_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici(request)
    await ps.sil(db, await ps.bul(db, sablon_id))
    return {"silindi": sablon_id}


@router.post("/{sablon_id}/proje-olustur")
async def proje_olustur(sablon_id: int, request: Request, govde: Govde = Body(...), db: AsyncSession = _Depends(get_db)):
    ben = _yonetici(request)
    sablon = await ps.bul(db, sablon_id)
    proje, gorevler = await ps.proje_olustur(db, sablon, _govde(govde), ben)
    return {
        "proje": {"id": proje.id, "baslik": proje.title, "client_email": proje.client_email},
        "gorev_sayisi": len(gorevler),
        "gorevler": [
            {"id": g.id, "baslik": g.baslik, "baslangic_tarihi": ps.iso(g.baslangic_tarihi), "bitis_tarihi": ps.iso(g.bitis_tarihi),
             "atanan": g.atanan, "musteriye_gorunur": bool(g.musteriye_gorunur)}
            for g in gorevler
        ],
    }


@router.post("/{sablon_id}/uygula")
async def uygula(sablon_id: int, request: Request, govde: Govde = Body(...), db: AsyncSession = _Depends(get_db)):
    from services.zaman_takibi import bugun, tarih_coz
    from services.zaman_takibi import proje_bul as proje_dogrula

    ben = _yonetici(request)
    sablon = await ps.bul(db, sablon_id)
    veri = _govde(govde)
    proje = await proje_dogrula(db, veri.get("proje_id"))
    gorevler = await ps.uygula(db, sablon, proje, tarih_coz(veri.get("baslangic_tarihi")) or bugun(), ben)
    await db.commit()
    return {"proje_id": proje.id, "gorev_sayisi": len(gorevler)}
