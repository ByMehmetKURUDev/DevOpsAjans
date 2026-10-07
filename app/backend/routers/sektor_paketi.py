"""Faz 6R — sektör paketini tek tıkla açma + hazır sektör ayarları (YALNIZ yönetici).

Yönetici › Sistem › Modüller ekranının (müşteri seçiliyken) kullandığı uçlar:

  GET  /api/v1/sektor-paketleri                                  paketler + setler (katalog)
  GET  /api/v1/sektor-paketleri/musteri/{eposta}                 müşterinin varsayılanları (dil, işletme adı,
                                                                  adres — yalnız gerçek kayıtlardan) + geçmiş
  POST /api/v1/sektor-paketleri/musteri/{eposta}/onizleme        {paket?, set?, dil?, isletme_adi?, adres?,
                                                                  hazir_ayarlar?} → açılacak/açık modüller,
                                                                  plan etkisi, hazır ayarlar, uyarılar
  POST /api/v1/sektor-paketleri/musteri/{eposta}/uygula          {paket, set?, dil?, isletme_adi?, adres?,
                                                                  hazir_ayarlar?, bildirim?} → TEK işlem
  POST /api/v1/sektor-paketleri/musteri/{eposta}/hazir           {set, dil?, …} → yalnız hazır ayarlar
  POST /api/v1/sektor-paketleri/uygulamalar/{uid}/kaldir         {hazir_ayarlar?, bildirim?} → paketi kaldır
  POST /api/v1/sektor-paketleri/uygulamalar/{uid}/hazir-geri-al  → yalnız el değmemiş hazır kayıtlar

Müşteri tarafında uç YOK: otomasyon önerileri müşterinin kendi Otomasyon
meta yanıtına (`onerilen_sablonlar`) ekleniyor.
"""

import logging
import re
from typing import Any, Dict

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from models.sektor_paketi import SektorPaketiUygulamalari  # noqa: F401 - tablo oluşsun
from models.workspace_modules import WorkspaceModules  # noqa: F401
from services import moduller as ms
from services import sektor_paketi as servis
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sektor-paketleri", tags=["sektor-paketleri"])

_EPOSTA = re.compile(r"^[^@\s<>,;/]+@[^@\s<>,;/]+\.[^@\s<>,;/]{2,}$")


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=401, detail="Giriş yapmanız gerekiyor")
    if not yonetici:
        raise HTTPException(status_code=403, detail="Bu işlem yönetici yetkisi istiyor")
    return (kullanici.email or "").strip().lower()


def _eposta(eposta: str) -> str:
    e = ms.eposta_duzelt(eposta)
    if len(e) > 254 or not _EPOSTA.match(e):
        raise HTTPException(status_code=400, detail={"kod": "gecersiz_eposta"})
    return e


def _bool(govde: Dict[str, Any], alan: str, varsayilan: bool) -> bool:
    deger = govde.get(alan, varsayilan)
    if not isinstance(deger, bool):
        raise HTTPException(status_code=400, detail={"kod": "gecersiz", "alan": alan})
    return deger


def _str(govde: Dict[str, Any], alan: str) -> Any:
    deger = govde.get(alan)
    if deger is not None and not isinstance(deger, str):
        raise HTTPException(status_code=400, detail={"kod": "gecersiz", "alan": alan})
    return deger


def _cevir(h: Exception) -> HTTPException:
    if isinstance(h, servis.PaketHatasi):
        return HTTPException(status_code=h.durum, detail=h.detay())
    if isinstance(h, ms.ModulHatasi):
        return HTTPException(status_code=h.durum, detail=h.detay())
    raise h


@router.get("")
async def katalog(request: Request):
    _yonetici_iste(request)
    return servis.katalog()


@router.get("/musteri/{eposta}")
async def musteri(eposta: str, request: Request, db: AsyncSession = Depends(get_db)):
    _yonetici_iste(request)
    e = _eposta(eposta)
    return {"eposta": e, "varsayilan": await servis.musteri_bilgisi(db, e), "gecmis": await servis.gecmis(db, e)}


@router.post("/musteri/{eposta}/onizleme")
async def onizleme(eposta: str, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    yonetici = _yonetici_iste(request)
    e = _eposta(eposta)
    try:
        return await servis.onizle(
            db, e, paket=_str(govde, "paket"), set_anahtari=_str(govde, "set"), dil=_str(govde, "dil"),
            isletme_adi=_str(govde, "isletme_adi"), adres=_str(govde, "adres"),
            hazir_ayarlar=_bool(govde, "hazir_ayarlar", True), kisi=yonetici,
        )
    except (servis.PaketHatasi, ms.ModulHatasi) as h:
        raise _cevir(h)


@router.post("/musteri/{eposta}/uygula")
async def uygula(eposta: str, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    yonetici = _yonetici_iste(request)
    e = _eposta(eposta)
    try:
        return await servis.uygula(
            db, e, paket=_str(govde, "paket") or "", set_anahtari=_str(govde, "set"), dil=_str(govde, "dil"),
            isletme_adi=_str(govde, "isletme_adi"), adres=_str(govde, "adres"),
            hazir_ayarlar=_bool(govde, "hazir_ayarlar", True), bildirim=_bool(govde, "bildirim", False),
            yonetici=yonetici, request=request,
        )
    except (servis.PaketHatasi, ms.ModulHatasi) as h:
        raise _cevir(h)


@router.post("/musteri/{eposta}/hazir")
async def hazir(eposta: str, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    yonetici = _yonetici_iste(request)
    e = _eposta(eposta)
    try:
        return await servis.hazir_uygula(
            db, e, set_anahtari=_str(govde, "set") or "", dil=_str(govde, "dil"),
            isletme_adi=_str(govde, "isletme_adi"), adres=_str(govde, "adres"), yonetici=yonetici, request=request,
        )
    except (servis.PaketHatasi, ms.ModulHatasi) as h:
        raise _cevir(h)


@router.post("/uygulamalar/{uid}/kaldir")
async def kaldir(uid: int, request: Request, govde: Dict[str, Any] = Body(default={}), db: AsyncSession = Depends(get_db)):
    yonetici = _yonetici_iste(request)
    govde = govde if isinstance(govde, dict) else {}
    try:
        return await servis.kaldir(
            db, uid, hazir_da=_bool(govde, "hazir_ayarlar", True), bildirim=_bool(govde, "bildirim", False),
            yonetici=yonetici, request=request,
        )
    except (servis.PaketHatasi, ms.ModulHatasi) as h:
        raise _cevir(h)


@router.post("/uygulamalar/{uid}/hazir-geri-al")
async def hazir_geri_al(uid: int, request: Request, db: AsyncSession = Depends(get_db)):
    yonetici = _yonetici_iste(request)
    try:
        return await servis.hazir_geri_al(db, uid, yonetici=yonetici, request=request)
    except (servis.PaketHatasi, ms.ModulHatasi) as h:
        raise _cevir(h)
