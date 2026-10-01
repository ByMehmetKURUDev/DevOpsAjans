"""Faz 2C — Aylık müşteri raporu uçları (ayrıntı `services/aylik_rapor.py`).

Yönetici  GET    /api/v1/aylik-rapor?client_email=     liste
          POST   /api/v1/aylik-rapor/olustur           {client_email, donem?} taslak aç/yenile
          GET    /api/v1/aylik-rapor/{id}              önizleme verisi (+ jeton)
          PUT    /api/v1/aylik-rapor/{id}              {yonetici_notu} (yalnız taslak)
          POST   /api/v1/aylik-rapor/{id}/yayinla      yayınla + e-posta (bir kez)
          DELETE /api/v1/aylik-rapor/{id}              yalnız taslak
Müşteri   GET    /api/v1/raporlarim/aylik              (modül `aylik_rapor`) yayındakiler
Açık      GET    /api/v1/rapor-aylik/{jeton}           yayındaki rapor (imzalı jeton);
                                                        yönetici oturumuyla taslak da açılır
"""

import logging
from typing import Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.hesap_baglami import izin_gerekli, musteri_eposta
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from models.service_subscriptions import Service_reports
from pydantic import BaseModel
from services import aylik_rapor as servis
from services.aylik_rapor import RaporHatasi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/aylik-rapor", tags=["aylik_rapor"])
musteri_router = APIRouter(
    prefix="/api/v1/raporlarim/aylik",
    tags=["aylik_rapor"],
    # Faz 2E: ekip üyesinde `raporlar` izni.
    dependencies=[_Depends(izin_gerekli("raporlar")), _Depends(modul_gerekli("aylik_rapor"))],
)
acik_router = APIRouter(prefix="/api/v1/rapor-aylik", tags=["aylik_rapor"])


def _yonetici_iste(request: Request) -> None:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})


def _hata(h: RaporHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail={"kod": h.kod})


async def _rapor(db: AsyncSession, rapor_id: int) -> Service_reports:
    r = (
        await db.execute(select(Service_reports).where(Service_reports.id == rapor_id, Service_reports.tur == servis.TUR))
    ).scalars().first()
    if r is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    return r


class OlusturGirdisi(BaseModel):
    client_email: str
    donem: Optional[str] = None


class NotGirdisi(BaseModel):
    yonetici_notu: Optional[str] = None


@yonetici_router.get("")
async def liste(request: Request, client_email: Optional[str] = Query(None), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    sorgu = select(Service_reports).where(Service_reports.tur == servis.TUR)
    if client_email:
        sorgu = sorgu.where(Service_reports.client_email == servis.eposta_duzelt(client_email))
    satirlar = (await db.execute(sorgu.order_by(Service_reports.donem.desc(), Service_reports.id.desc()).limit(300))).scalars().all()
    return [
        {
            "id": r.id,
            "client_email": r.client_email,
            "donem": r.donem,
            "baslik": r.baslik,
            "ozet": r.ozet,
            "durum": r.durum,
            "yayin_at": servis.iso(r.yayin_at),
            "eposta_gonderildi_at": servis.iso(r.eposta_gonderildi_at),
            "jeton": servis.jeton_uret(r),
        }
        for r in satirlar
    ]


@yonetici_router.post("/olustur")
async def olustur(request: Request, govde: OlusturGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    """Yönetici "şimdi oluştur": varsayılan dönem bir önceki ay."""
    _yonetici_iste(request)
    try:
        r = await servis.olustur(db, govde.client_email, govde.donem or servis.onceki_donem())
    except RaporHatasi as h:
        raise _hata(h)
    return servis.rapor_sozlugu(r, yonetici=True)


@yonetici_router.get("/{rapor_id}")
async def onizleme(rapor_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return servis.rapor_sozlugu(await _rapor(db, rapor_id), yonetici=True)


@yonetici_router.put("/{rapor_id}")
async def not_yaz(rapor_id: int, request: Request, govde: NotGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    r = await _rapor(db, rapor_id)
    if r.durum == "yayinlandi":
        raise HTTPException(status_code=409, detail={"kod": "yayinlandi"})
    r.yonetici_notu = (govde.yonetici_notu or "").strip()[:4000] or None
    await db.commit()
    await db.refresh(r)
    return servis.rapor_sozlugu(r, yonetici=True)


@yonetici_router.post("/{rapor_id}/yenile")
async def yenile(rapor_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Taslağın verisini yeniden toplar (not korunur)."""
    _yonetici_iste(request)
    r = await _rapor(db, rapor_id)
    try:
        r = await servis.olustur(db, r.client_email, r.donem)
    except RaporHatasi as h:
        raise _hata(h)
    return servis.rapor_sozlugu(r, yonetici=True)


@yonetici_router.post("/{rapor_id}/yayinla")
async def yayinla(rapor_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    r = await _rapor(db, rapor_id)
    gonderildi = await servis.yayinla(db, r)
    await db.refresh(r)
    return {**servis.rapor_sozlugu(r, yonetici=True), "eposta_gonderildi": gonderildi}


@yonetici_router.delete("/{rapor_id}")
async def sil(rapor_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    r = await _rapor(db, rapor_id)
    if r.durum == "yayinlandi":
        # Yayınlanmış rapor müşterinin gördüğü geçmiş: geri alınmıyor.
        raise HTTPException(status_code=409, detail={"kod": "yayinlandi"})
    await db.delete(r)
    await db.commit()
    return {"silindi": rapor_id}


@musteri_router.get("")
async def kendi_aylik_raporlarim(request: Request, db: AsyncSession = _Depends(get_db)):
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not servis.eposta_duzelt(kullanici.email):
        raise HTTPException(status_code=403, detail={"kod": "eposta_gerekli"})
    eposta = musteri_eposta(request)
    satirlar = (
        await db.execute(
            select(Service_reports)
            .where(Service_reports.tur == servis.TUR, Service_reports.client_email == eposta, Service_reports.durum == "yayinlandi")
            .order_by(Service_reports.donem.desc())
            .limit(120)
        )
    ).scalars().all()
    return [
        {"id": r.id, "donem": r.donem, "baslik": r.baslik, "ozet": r.ozet, "yayin_at": servis.iso(r.yayin_at), "jeton": servis.jeton_uret(r)}
        for r in satirlar
    ]


@acik_router.get("/{jeton}")
async def acik_rapor(jeton: str, request: Request, db: AsyncSession = _Depends(get_db)):
    kimlik = servis.jeton_id(jeton)
    if kimlik is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    r = (
        await db.execute(select(Service_reports).where(Service_reports.id == kimlik, Service_reports.tur == servis.TUR))
    ).scalars().first()
    if r is None or not servis.jeton_dogru_mu(r, jeton):
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    _, yonetici = _yonetici_mi(request)
    if r.durum != "yayinlandi" and not yonetici:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    d = servis.rapor_sozlugu(r)
    d.pop("jeton", None)
    return d


router = (yonetici_router, musteri_router, acik_router)
