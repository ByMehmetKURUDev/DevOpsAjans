"""Faz 5G — birleşik gelen kutusu uçları (yalnız yönetici).

GET    /api/v1/gelen-kutusu                          liste: ?kaynak=a,b &durum=bekleyen|hepsi|yeni|yanit_bekliyor|okundu|kapandi
                                                     &q= &bas=YYYY-MM-DD &bit=YYYY-MM-DD &sayfa= &adet=
GET    /api/v1/gelen-kutusu/sayac                    kaynak başına yanıt bekleyen (menü rozeti, hafif)
GET    /api/v1/gelen-kutusu/{kaynak}/{kimlik}        tek öğe + ayrıntı (tam metin)
POST   /api/v1/gelen-kutusu/{kaynak}/{kimlik}/isaret {durum: okundu|kapandi|yeni} — yalnız kendi alanı olmayan kaynaklar
POST   /api/v1/gelen-kutusu/{kaynak}/{kimlik}/taslak {dil?, talimat?} — AI yanıt taslağı (GÖNDERİLMEZ)
POST   /api/v1/gelen-kutusu/{kaynak}/{kimlik}/eposta {konu, metin} — e-posta yanıtı (destek/sohbet hariç)

Kaynağa özgü öteki eylemler (çözüldü, projeye çevir, talebe yanıt, sohbete yanıt,
arşivle, okundu…) mevcut uçlarından çağrılıyor; öğenin `eylemler` listesi yolu taşıyor.
"""

import logging
from datetime import date
from typing import Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from services import gelen_kutusu as gk
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gelen-kutusu", tags=["gelen_kutusu"], dependencies=[Depends(yonetici_gerekli)])


class IsaretGirdisi(BaseModel):
    durum: str


class TaslakGirdisi(BaseModel):
    dil: Optional[str] = None
    talimat: Optional[str] = None


class EpostaGirdisi(BaseModel):
    konu: Optional[str] = ""
    metin: Optional[str] = ""


def _hata(h: gk.GelenKutusuHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail={"kod": h.kod})


def _kisi(request: Request) -> str:
    kullanici, _ = _yonetici_mi(request)
    return gk.eposta_duzelt(getattr(kullanici, "email", ""))


def _tarih(ham: Optional[str]) -> Optional[date]:
    if not ham:
        return None
    try:
        return date.fromisoformat(ham.strip()[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail={"kod": "tarih_gecersiz"})


@router.get("")
async def liste(
    request: Request,
    kaynak: Optional[str] = Query(None, max_length=200),
    durum: str = Query("bekleyen", max_length=20),
    q: Optional[str] = Query(None, max_length=200),
    bas: Optional[str] = Query(None, max_length=10),
    bit: Optional[str] = Query(None, max_length=10),
    sayfa: int = Query(1, ge=1, le=1000),
    adet: int = Query(gk.VARSAYILAN_ADET, ge=1, le=gk.EN_COK_ADET),
    db: AsyncSession = Depends(get_db),
):
    if durum not in gk.DURUM_SUZGECLERI:
        raise HTTPException(status_code=400, detail={"kod": "durum_gecersiz"})
    kaynaklar = gk.KAYNAKLAR
    if kaynak:
        istenen = [k.strip() for k in kaynak.split(",") if k.strip()]
        if any(k not in gk.KAYNAKLAR for k in istenen):
            raise HTTPException(status_code=400, detail={"kod": "kaynak_gecersiz"})
        kaynaklar = tuple(k for k in gk.KAYNAKLAR if k in istenen)
    sz = gk.Suzgec(kaynaklar=kaynaklar, durum=durum, q=q or "", bas=_tarih(bas), bit=_tarih(bit))
    if sz.bas and sz.bit and sz.bas > sz.bit:
        raise HTTPException(status_code=400, detail={"kod": "tarih_gecersiz"})
    return await gk.liste(db, _kisi(request), sz, sayfa=sayfa, adet=adet)


@router.get("/sayac")
async def sayac(request: Request, db: AsyncSession = Depends(get_db)):
    return await gk.sayac(db, _kisi(request))


@router.get("/{kaynak}/{kimlik}")
async def ayrinti(kaynak: str, kimlik: int, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        return await gk.ayrinti(db, _kisi(request), kaynak, kimlik)
    except gk.GelenKutusuHatasi as h:
        raise _hata(h)


@router.post("/{kaynak}/{kimlik}/isaret")
async def isaret(kaynak: str, kimlik: int, request: Request, govde: IsaretGirdisi = Body(...),
                 db: AsyncSession = Depends(get_db)):
    try:
        return await gk.isaretle(db, _kisi(request), kaynak, kimlik, govde.durum)
    except gk.GelenKutusuHatasi as h:
        raise _hata(h)


@router.post("/{kaynak}/{kimlik}/taslak")
async def taslak(kaynak: str, kimlik: int, request: Request, govde: TaslakGirdisi = Body(default=TaslakGirdisi()),
                 db: AsyncSession = Depends(get_db)):
    try:
        return await gk.taslak_uret(db, _kisi(request), kaynak, kimlik, dil=govde.dil, talimat=govde.talimat)
    except gk.GelenKutusuHatasi as h:
        raise _hata(h)


@router.post("/{kaynak}/{kimlik}/eposta")
async def eposta(kaynak: str, kimlik: int, request: Request, govde: EpostaGirdisi = Body(...),
                 db: AsyncSession = Depends(get_db)):
    try:
        return await gk.eposta_gonder(db, _kisi(request), kaynak, kimlik, govde.konu or "", govde.metin or "")
    except gk.GelenKutusuHatasi as h:
        raise _hata(h)
