"""Teknik SEO + Core Web Vitals izleme uçları (Faz 2H, modül #31) — ayrıntı `services/seo_izleme.py`.

Müşteri (`siteler` izni + `sitem` modülü; e-posta etkin hesaptan, sorgudan değil)
    GET  /api/v1/sitelerim/{site_id}/seo-gecmisi?gun=90
    POST /api/v1/sitelerim/{site_id}/seo-tara          (site başına 24 saatte 1)
Yönetici
    GET  /api/v1/site-bakim/seo-ozet                   (son puanlar, düşüşte olanlar üstte)
    GET  /api/v1/site-bakim/{site_id}/seo-gecmisi?gun=90
    POST /api/v1/site-bakim/{site_id}/seo-tara         (sınırsız)
    PUT  /api/v1/site-bakim/{site_id}/seo-ayar         {"tarama_gun": 0..90}

Not: `/api/v1/site-bakim/seo-ozet`, `routers/site_bakim.py`deki `GET /{site_id}`
ile aynı biçimde. Router keşfi modülleri ada göre sıralı yüklüyor
(`seo_izleme` < `site_bakim`), bu uç önce eşleşiyor; test bunu bağlıyor.
"""

import logging
from typing import Any, Dict

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, musteri_eposta
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from models.client_sites import Client_sites
from pydantic import BaseModel
from services import seo_izleme as servis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/site-bakim", tags=["seo-izleme"])
musteri_router = APIRouter(
    prefix="/api/v1/sitelerim",
    tags=["seo-izleme"],
    dependencies=[_Depends(izin_gerekli("siteler")), _Depends(modul_gerekli("sitem"))],
)

GUN_EN_AZ, GUN_EN_COK = 7, 365


class AyarGirdisi(BaseModel):
    tarama_gun: int


def _hata(kod: int, anahtar: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=kod, detail={"kod": anahtar, **ek})


def _yonetici_iste(request: Request) -> None:
    _, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")


async def _site_bul(db: AsyncSession, site_id: int) -> Client_sites:
    site = (await db.execute(select(Client_sites).where(Client_sites.id == site_id))).scalar_one_or_none()
    if site is None:
        raise _hata(404, "site_yok")
    return site


async def _musteri_sitesi(request: Request, db: AsyncSession, site_id: int) -> tuple[Client_sites, bool]:
    """Oturum yoksa 401; site başka hesabınsa 404 (varlığı da belli edilmiyor)."""
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None or not (getattr(kullanici, "email", "") or "").strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli")
    eposta = musteri_eposta(request)
    site = await _site_bul(db, site_id)
    if not yonetici and (site.client_email or "").strip().lower() != eposta:
        raise _hata(404, "site_yok")
    return site, yonetici


async def _tara(db: AsyncSession, site: Client_sites, kaynak: str) -> Dict[str, Any]:
    try:
        olcum, uyarilar = await servis.elle_tara(db, site, kaynak)
    except servis.SeoHatasi as h:
        raise _hata(h.durum, h.kod, **h.ek) from h
    return {
        "olcum": servis.tam_sozluk(olcum) if olcum.durum == servis.TAMAM else servis.kisa_sozluk(olcum),
        "uyari_sayisi": len(uyarilar),
    }


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("/seo-ozet")
async def seo_ozet(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return {"siteler": await servis.ozet_listesi(db), "esik": servis.DUSUS_ESIGI}


@yonetici_router.get("/{site_id}/seo-gecmisi")
async def yonetici_gecmis(
    site_id: int,
    request: Request,
    gun: int = Query(90, ge=GUN_EN_AZ, le=GUN_EN_COK),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    site = await _site_bul(db, site_id)
    return await servis.gecmis_sozlugu(db, site, gun, yonetici=True)


@yonetici_router.post("/{site_id}/seo-tara")
async def yonetici_tara(site_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Yönetici için sınır yok (yalnız aynı sitede süren ölçüm varsa 409)."""
    _yonetici_iste(request)
    site = await _site_bul(db, site_id)
    return await _tara(db, site, "yonetici")


@yonetici_router.put("/{site_id}/seo-ayar")
async def yonetici_ayar(
    site_id: int, request: Request, govde: AyarGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    _yonetici_iste(request)
    site = await _site_bul(db, site_id)
    try:
        gun = await servis.ayar_kaydet(db, site, govde.tarama_gun)
    except servis.SeoHatasi as h:
        raise _hata(h.durum, h.kod) from h
    return {"site_id": site.id, "tarama_gun": gun}


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
@musteri_router.get("/{site_id}/seo-gecmisi")
async def musteri_gecmis(
    site_id: int,
    request: Request,
    gun: int = Query(90, ge=GUN_EN_AZ, le=GUN_EN_COK),
    db: AsyncSession = _Depends(get_db),
):
    site, yonetici = await _musteri_sitesi(request, db, site_id)
    return await servis.gecmis_sozlugu(db, site, gun, yonetici=yonetici)


@musteri_router.post("/{site_id}/seo-tara")
async def musteri_tara(site_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Müşteri site başına 24 saatte bir; aşılırsa 429 `gunluk_sinir` + `sonraki_at`."""
    site, yonetici = await _musteri_sitesi(request, db, site_id)
    return await _tara(db, site, "yonetici" if yonetici else "elle")


router = (yonetici_router, musteri_router)
