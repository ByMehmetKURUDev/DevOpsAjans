"""Faz 2B — öneri kutusu: müşteriler öneri gönderir, diğerleri oylar, yönetici durum verir.

Kişi      /api/v1/oneri-kutusu          (liste + oy; sahibin e-postası HİÇ dönmüyor)
Yönetici  /api/v1/oneri-yonetimi        (sahip dahil liste, durum, "Topluluktan" ayarı)
Açık      /api/v1/topluluk-onerileri    (ayar açıksa yalnız "planlandı" önerilerin
                                         başlığı + oy sayısı — Yol haritası sayfası)

Oy: kişi başına tek oy (benzersiz kısıt); kendi önerisine oy verilmiyor.
Oy sayısı anonim: kimin oy verdiği hiçbir uçta dönmüyor.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, HTTPException, Request, Response, status
from fastapi import Depends as _Depends
from models.duyurular import ONERI_DURUMLARI, OneriOylari, Oneriler
from pydantic import BaseModel
from services import gorevler as gs
from services.gorevler import GorevHatasi
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

kisi_router = APIRouter(
    prefix="/api/v1/oneri-kutusu",
    tags=["oneri-kutusu"],
    dependencies=[_Depends(modul_gerekli("oneri_kutusu"))],
)
yonetici_router = APIRouter(
    prefix="/api/v1/oneri-yonetimi", tags=["oneri-kutusu"], dependencies=[_Depends(yonetici_gerekli)]
)
acik_router = APIRouter(prefix="/api/v1/topluluk-onerileri", tags=["oneri-kutusu"])

AYAR_ANAHTARI = "oneri_topluluk_yol_haritasi"
GUNLUK_SINIR = 5
BASLIK_SINIRI = 160
ACIKLAMA_SINIRI = 2000
DURUM_ADLARI = {
    "yeni": ("Alındı", "Received"),
    "inceleniyor": ("İnceleniyor", "Under review"),
    "planlandi": ("Planlandı", "Planned"),
    "yapildi": ("Yapıldı", "Done"),
    "reddedildi": ("Reddedildi", "Declined"),
}


class OneriGirdisi(BaseModel):
    baslik: str
    aciklama: Optional[str] = None


class OneriGuncelleme(BaseModel):
    durum: Optional[str] = None
    yonetici_notu: Optional[str] = None


class AyarGirdisi(BaseModel):
    topluluk_yol_haritasi: bool


def _kisi_iste(request: Request) -> str:
    kullanici, _ = _yonetici_mi(request)
    eposta = gs.eposta_duzelt(getattr(kullanici, "email", None))
    if not eposta:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli")
    return eposta


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli")
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
    return gs.eposta_duzelt(kullanici.email)


async def _oy_sayilari(db: AsyncSession, idler: List[int]) -> Dict[int, int]:
    if not idler:
        return {}
    return {
        oid: int(n)
        for oid, n in (
            await db.execute(
                select(OneriOylari.oneri_id, func.count(OneriOylari.id)).where(OneriOylari.oneri_id.in_(idler)).group_by(OneriOylari.oneri_id)
            )
        ).all()
    }


def _kisi_sozlugu(o: Oneriler, oy: int, eposta: str, oyladiklarim: set) -> Dict[str, Any]:
    """Sahibin e-postası yok; yalnız "benim mi?" bilgisi."""
    return {
        "id": o.id,
        "baslik": o.baslik,
        "aciklama": o.aciklama,
        "durum": o.durum,
        "yonetici_notu": o.yonetici_notu,
        "oy_sayisi": oy,
        "benim": o.sahip_eposta == eposta,
        "oyladim": o.id in oyladiklarim,
        "created_at": gs.iso(o.created_at),
    }


def _yonetici_sozlugu(o: Oneriler, oy: int) -> Dict[str, Any]:
    return {
        "id": o.id,
        "baslik": o.baslik,
        "aciklama": o.aciklama,
        "durum": o.durum,
        "yonetici_notu": o.yonetici_notu,
        "oy_sayisi": oy,
        "sahip_eposta": o.sahip_eposta,
        "created_at": gs.iso(o.created_at),
    }


async def _bul(db: AsyncSession, oneri_id: int) -> Oneriler:
    o = (await db.execute(select(Oneriler).where(Oneriler.id == oneri_id))).scalar_one_or_none()
    if o is None:
        raise GorevHatasi(404, "oneri_yok")
    return o


async def _ayar_satiri(db: AsyncSession):
    from models.site_settings import Site_settings

    return (await db.execute(select(Site_settings).where(Site_settings.setting_key == AYAR_ANAHTARI))).scalars().first()


async def topluluk_acik_mi(db: AsyncSession) -> bool:
    try:
        satir = await _ayar_satiri(db)
    except Exception:  # noqa: BLE001
        return False
    return bool(satir and str(satir.setting_value or "").strip().lower() in ("1", "true", "evet"))


async def _tek(db: AsyncSession, o: Oneriler, eposta: str) -> Dict[str, Any]:
    oy = (await _oy_sayilari(db, [o.id])).get(o.id, 0)
    oyladim = (
        await db.execute(select(OneriOylari.id).where(OneriOylari.oneri_id == o.id).where(OneriOylari.eposta == eposta))
    ).first() is not None
    return _kisi_sozlugu(o, oy, eposta, {o.id} if oyladim else set())


# --------------------------------------------------------------------------
# Kişi
# --------------------------------------------------------------------------
@kisi_router.get("")
async def oneriler(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = _kisi_iste(request)
    kayitlar = list((await db.execute(select(Oneriler).order_by(Oneriler.id.desc()).limit(300))).scalars().all())
    oylar = await _oy_sayilari(db, [o.id for o in kayitlar])
    oyladiklarim = {
        oid for (oid,) in (await db.execute(select(OneriOylari.oneri_id).where(OneriOylari.eposta == eposta))).all()
    }
    liste = [_kisi_sozlugu(o, oylar.get(o.id, 0), eposta, oyladiklarim) for o in kayitlar]
    # Reddedilenler sona, sonra çok oy alan önce.
    liste.sort(key=lambda x: (x["durum"] == "reddedildi", -x["oy_sayisi"], -x["id"]))
    return liste


@kisi_router.post("")
async def oneri_gonder(request: Request, govde: OneriGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    eposta = _kisi_iste(request)
    baslik = (govde.baslik or "").strip()[:BASLIK_SINIRI]
    if not baslik:
        raise GorevHatasi(400, "baslik_gerekli")
    son_gun = datetime.now(timezone.utc) - timedelta(days=1)
    adet = (
        await db.execute(select(func.count(Oneriler.id)).where(Oneriler.sahip_eposta == eposta).where(Oneriler.created_at >= son_gun))
    ).scalar()
    if int(adet or 0) >= GUNLUK_SINIR:
        raise GorevHatasi(429, "gunluk_sinir")
    o = Oneriler(baslik=baslik, aciklama=(govde.aciklama or "").strip()[:ACIKLAMA_SINIRI] or None, sahip_eposta=eposta, durum="yeni")
    db.add(o)
    await db.commit()
    await db.refresh(o)
    return await _tek(db, o, eposta)


@kisi_router.post("/{oneri_id}/oy")
async def oy_ver(oneri_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = _kisi_iste(request)
    o = await _bul(db, oneri_id)
    if o.sahip_eposta == eposta:
        raise GorevHatasi(409, "kendi_onerin")
    if o.durum in ("yapildi", "reddedildi"):
        raise GorevHatasi(409, "oylamaya_kapali")
    try:
        async with db.begin_nested():
            db.add(OneriOylari(oneri_id=o.id, eposta=eposta))
            await db.flush()
    except IntegrityError:
        pass  # zaten oy vermiş: tekil oy, sayı değişmez
    await db.commit()
    return await _tek(db, o, eposta)


@kisi_router.delete("/{oneri_id}/oy")
async def oy_geri_al(oneri_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = _kisi_iste(request)
    o = await _bul(db, oneri_id)
    for oy in (
        await db.execute(select(OneriOylari).where(OneriOylari.oneri_id == o.id).where(OneriOylari.eposta == eposta))
    ).scalars().all():
        await db.delete(oy)
    await db.commit()
    return await _tek(db, o, eposta)


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("")
async def yonetici_listesi(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    kayitlar = list((await db.execute(select(Oneriler).order_by(Oneriler.id.desc()).limit(500))).scalars().all())
    oylar = await _oy_sayilari(db, [o.id for o in kayitlar])
    return {
        "oneriler": [_yonetici_sozlugu(o, oylar.get(o.id, 0)) for o in kayitlar],
        "topluluk_yol_haritasi": await topluluk_acik_mi(db),
    }


@yonetici_router.patch("/{oneri_id}")
async def oneri_guncelle(oneri_id: int, request: Request, govde: OneriGuncelleme = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    o = await _bul(db, oneri_id)
    degisti = False
    if govde.durum is not None:
        if govde.durum not in ONERI_DURUMLARI:
            raise GorevHatasi(400, "durum_gecersiz")
        degisti = govde.durum != o.durum
        o.durum = govde.durum
    if "yonetici_notu" in govde.model_fields_set:
        o.yonetici_notu = (govde.yonetici_notu or "").strip()[:1000] or None
    await db.commit()
    await db.refresh(o)
    if degisti:
        try:
            from services.notify import dispatch, render

            tr, en = DURUM_ADLARI.get(o.durum, (o.durum, o.durum))
            baslik, metin = await render(
                db,
                "oneri_durumu",
                f"Öneriniz: {o.baslik} — {tr} / Your suggestion: {en}",
                f"“{o.baslik}” önerinizin durumu: {tr}.\n\nStatus of your suggestion “{o.baslik}”: {en}.",
                {"baslik": o.baslik, "durum": tr},
            )
            await dispatch(
                db,
                event_type="oneri_durumu",
                title=baslik,
                body=metin,
                recipients=[{"email": o.sahip_eposta, "role": "client"}],
                link="/client?sekme=tickets",
                ref_type="oneri",
                ref_id=o.id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Öneri durum bildirimi gönderilemedi")
    oy = (await _oy_sayilari(db, [o.id])).get(o.id, 0)
    return _yonetici_sozlugu(o, oy)


@yonetici_router.put("/ayar")
async def ayar_yaz(request: Request, govde: AyarGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    """Yol haritası sayfasında "Topluluktan" bölümü (yalnız planlananlar)."""
    _yonetici_iste(request)
    from models.site_settings import Site_settings

    satir = await _ayar_satiri(db)
    deger = "1" if govde.topluluk_yol_haritasi else "0"
    if satir:
        satir.setting_value = deger
    else:
        db.add(Site_settings(setting_key=AYAR_ANAHTARI, setting_value=deger, group_name="oneri", label="Yol haritasında topluluk önerileri"))
    await db.commit()
    return {"topluluk_yol_haritasi": govde.topluluk_yol_haritasi}


# --------------------------------------------------------------------------
# Herkese açık (Yol haritası › Topluluktan)
# --------------------------------------------------------------------------
@acik_router.get("")
async def topluluk_onerileri(response: Response, db: AsyncSession = _Depends(get_db)):
    response.headers["Cache-Control"] = "public, max-age=120"
    if not await topluluk_acik_mi(db):
        return {"acik": False, "oneriler": []}
    kayitlar = list(
        (await db.execute(select(Oneriler).where(Oneriler.durum == "planlandi").order_by(Oneriler.id.desc()).limit(100))).scalars().all()
    )
    oylar = await _oy_sayilari(db, [o.id for o in kayitlar])
    liste = sorted(
        ({"baslik": o.baslik, "oy_sayisi": oylar.get(o.id, 0)} for o in kayitlar),
        key=lambda x: -x["oy_sayisi"],
    )[:20]
    return {"acik": True, "oneriler": liste}


router = (kisi_router, yonetici_router, acik_router)
