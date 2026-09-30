"""Faz 2F — Otomatik destek kuralları (yönetici).

GET  /api/v1/destek/kurallar              sıralı liste
POST /api/v1/destek/kurallar              yeni kural (sona eklenir)
PUT  /api/v1/destek/kurallar/{id}         güncelle
DELETE /api/v1/destek/kurallar/{id}       sil
POST /api/v1/destek/kurallar/sirala       {"idler": [3, 1, 2]} → sıra 0, 1, 2 …
POST /api/v1/destek/kurallar/dene         örnek konu/metin/gönderen → eşleşecek
                                          kurallar ve eylemleri (HİÇBİR ŞEY YAZMAZ)

Kural biçimi ve eşleşme mantığı `services/destek_kurallari.py`.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from models.destek_eposta import DestekKurallari
from pydantic import BaseModel
from services import destek_kurallari as servis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/destek/kurallar", tags=["destek-kurallari"])


def _yonetici_iste(request: Request) -> None:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})


def _hata(h: servis.KuralHatasi) -> HTTPException:
    return HTTPException(status_code=400, detail={"kod": h.kod, **h.ek})


class KuralGirdisi(BaseModel):
    ad: str
    aktif: bool = True
    eslesme: str = "hepsi"
    kosullar: List[Dict[str, Any]] = []
    eylemler: List[Dict[str, Any]] = []


class SiraGirdisi(BaseModel):
    idler: List[int]


class DeneGirdisi(BaseModel):
    konu: str = ""
    metin: str = ""
    gonderen: str = ""
    kanal: str = "eposta"
    oncelik: str = "normal"
    hizmet: str = "genel"
    paket: Optional[str] = None


async def _dogrula(db: AsyncSession, govde: KuralGirdisi) -> Dict[str, Any]:
    ad = (govde.ad or "").strip()[:120]
    if not ad:
        raise HTTPException(status_code=400, detail={"kod": "ad_gerekli"})
    try:
        return {
            "ad": ad,
            "aktif": bool(govde.aktif),
            "eslesme": servis.eslesme_dogrula(govde.eslesme),
            "kosullar": json.dumps(servis.kosullari_dogrula(govde.kosullar), ensure_ascii=False),
            "eylemler": json.dumps(await servis.eylemleri_dogrula(db, govde.eylemler), ensure_ascii=False),
        }
    except servis.KuralHatasi as h:
        raise _hata(h)


async def _bul(db: AsyncSession, kural_id: int) -> DestekKurallari:
    k = (await db.execute(select(DestekKurallari).where(DestekKurallari.id == kural_id))).scalars().first()
    if k is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    return k


@router.get("")
async def kurallar(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return await servis.kurallari_oku(db)


@router.post("")
async def kural_ekle(request: Request, govde: KuralGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    sayi = (await db.execute(select(func.count(DestekKurallari.id)))).scalar_one()
    if int(sayi or 0) >= servis.EN_COK_KURAL:
        raise HTTPException(status_code=400, detail={"kod": "kural_siniri"})
    alanlar = await _dogrula(db, govde)
    en_buyuk = (await db.execute(select(func.max(DestekKurallari.sira)))).scalar_one()
    k = DestekKurallari(sira=int(en_buyuk if en_buyuk is not None else -1) + 1, **alanlar)
    db.add(k)
    await db.commit()
    await db.refresh(k)
    return servis.kural_sozlugu(k)


@router.post("/sirala")
async def kurallari_sirala(request: Request, govde: SiraGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    idler = list(dict.fromkeys(int(i) for i in govde.idler))
    satirlar = {k.id: k for k in (await db.execute(select(DestekKurallari))).scalars().all()}
    if set(idler) != set(satirlar):
        # Eksik/fazla kimlik: iki sekmede aynı anda düzenleme — eski listeyle sıralama yapılmasın.
        raise HTTPException(status_code=409, detail={"kod": "liste_degisti"})
    for sira, kid in enumerate(idler):
        satirlar[kid].sira = sira
    await db.commit()
    return await servis.kurallari_oku(db)


@router.post("/dene")
async def kurallari_dene(request: Request, govde: DeneGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    """Örnek girdiyle hangi kuralların eşleşeceğini döndürür; hiçbir şey yazmaz."""
    _yonetici_iste(request)
    liste = await servis.kurallari_oku(db)
    b = await servis.baglam_kur(
        db, liste, konu=govde.konu[:500], metin=govde.metin[:8000], gonderen=govde.gonderen[:254],
        kanal=govde.kanal, oncelik=govde.oncelik, hizmet=govde.hizmet, paket=govde.paket,
    )
    eslesen = servis.eslesenleri_bul(liste, b)
    return {
        "eslesen": [{"id": k["id"], "ad": k["ad"], "eylemler": k["eylemler"]} for k in eslesen],
        "durduruldu": bool(eslesen) and any(e.get("tur") == "durdur" for e in eslesen[-1]["eylemler"]),
        "paket": b.paket,
    }


@router.put("/{kural_id}")
async def kural_guncelle(kural_id: int, request: Request, govde: KuralGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    k = await _bul(db, kural_id)
    for alan, deger in (await _dogrula(db, govde)).items():
        setattr(k, alan, deger)
    await db.commit()
    return servis.kural_sozlugu(k)


@router.delete("/{kural_id}")
async def kural_sil(kural_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    k = await _bul(db, kural_id)
    await db.delete(k)
    await db.commit()
    return {"silindi": kural_id}
