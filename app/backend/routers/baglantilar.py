"""Faz 3B — Bağlantılar: Google (Analytics 4 + Search Console + YouTube).

Ayrıntı `services/baglantilar.py` (OAuth, jeton) ve `services/google_esitleme.py`
(eşitleme, pano). Bu fazda yalnız ajansın kendi Google hesabı (yönetici);
müşteri ucu YOK.

GET    /api/v1/baglantilar                       durum listesi (yönetici)
GET    /api/v1/baglantilar/pano                  "Anlık Analitik" verisi (yönetici)
POST   /api/v1/baglantilar/google/baslat         → {adres} Google onay adresi
GET    /api/v1/baglantilar/google/geri-donus     Google yönlendirmesi — GİRİŞSİZ;
       state zorunlu ve tek kullanımlık. Sonuç `/admin?sekme=baglantilar&sonuc=<kod>`.
GET    /api/v1/baglantilar/google/kaynaklar      GA4 mülkleri, SC siteleri, YT kanalları
PUT    /api/v1/baglantilar/google/secim          {ga4_mulk, sc_site, yt_kanal}
POST   /api/v1/baglantilar/google/esitle         elle eşitleme (10 dk'da bir)
DELETE /api/v1/baglantilar/google                Google'da iptal + kaydı sil

Yetki: oturumsuz 401, yönetici olmayan 403.
"""

import logging
from typing import Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from services import baglantilar as servis
from services import google_esitleme as esitleme
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/baglantilar", tags=["baglantilar"])
acik_router = APIRouter(prefix="/api/v1/baglantilar", tags=["baglantilar"])


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})
    return (kullanici.email or "").strip().lower()


def _hata(h: servis.BaglantiHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail={"kod": h.kod, **h.ek})


class SecimGirdisi(BaseModel):
    ga4_mulk: Optional[str] = None
    sc_site: Optional[str] = None
    yt_kanal: Optional[str] = None


@yonetici_router.get("")
async def durum(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return await servis.durum_listesi(db)


@yonetici_router.get("/pano")
async def pano(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return await esitleme.pano_verisi(db)


@yonetici_router.post("/google/baslat")
async def baslat(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = _yonetici_iste(request)
    try:
        return {"adres": await servis.baslat(db, eposta)}
    except servis.BaglantiHatasi as h:
        raise _hata(h)


@acik_router.get("/google/geri-donus")
async def geri_donus(
    db: AsyncSession = _Depends(get_db),
    code: Optional[str] = Query(default=None, max_length=4096),
    state: Optional[str] = Query(default=None, max_length=512),
    error: Optional[str] = Query(default=None, max_length=200),
):
    """Google'ın yönlendirdiği adres. Hata ayrıntısı URL'de taşınmaz: kısa kod."""
    try:
        sonuc = await servis.geri_donus(db, code, state, error)
    except Exception:  # noqa: BLE001 - kullanıcı ham hata görmesin
        logger.exception("Google geri dönüşü işlenemedi")
        sonuc = "google_hatasi"
    yanit = RedirectResponse(servis.panel_adresi(sonuc), status_code=status.HTTP_302_FOUND)
    yanit.headers["Cache-Control"] = "no-store"
    yanit.headers["Referrer-Policy"] = "no-referrer"
    return yanit


@yonetici_router.get("/google/kaynaklar")
async def kaynaklar(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        return await servis.kaynaklari_getir(db)
    except servis.BaglantiHatasi as h:
        raise _hata(h)


@yonetici_router.put("/google/secim")
async def secim(girdi: SecimGirdisi, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        secimler = await servis.secimi_kaydet(db, girdi.model_dump(exclude_unset=True))
    except servis.BaglantiHatasi as h:
        raise _hata(h)
    return {"secimler": secimler}


@yonetici_router.post("/google/esitle")
async def esitle(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        sonuc = await esitleme.elle_esitle(db)
    except servis.BaglantiHatasi as h:
        raise _hata(h)
    return {**sonuc, "durum": await servis.durum_listesi(db)}


@yonetici_router.delete("/google")
async def kaldir(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        return await servis.baglantiyi_kaldir(db)
    except servis.BaglantiHatasi as h:
        raise _hata(h)


router = (acik_router, yonetici_router)
