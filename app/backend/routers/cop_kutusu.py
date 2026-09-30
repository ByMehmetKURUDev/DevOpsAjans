"""Faz 2D — çöp kutusu uçları.

* Yönetici (`/api/v1/cop-kutusu`): liste (tablo süzgeci, arama, sayfa),
  ayrıntı (`veri`), geri al (aynı gruptakilerle birlikte), kalıcı sil,
  saklama süresi ayarı.
* Müşteri (`/api/v1/cop-kutum`): yalnız sahibi olduğu VE kendisinin sildiği
  kayıtlar (e-posta JETONDAN); geri alabilir, kalıcı silemez.

Hata gövdeleri `{"detail": {"kod": "..."}}` — ön yüz metni yedi dilde
kendisi kuruyor. Kayıtlar `services/cop_kutusu.py`deki flush kancasıyla
yazılıyor; bu dosyanın import edilmesi kancayı da kaydediyor.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from models.cop_kutusu import CopKutusu
from pydantic import BaseModel, Field
from services import cop_kutusu as servis
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/cop-kutusu", tags=["cop-kutusu"])
musteri_router = APIRouter(prefix="/api/v1/cop-kutum", tags=["cop-kutusu"])

EN_COK_ADET = 100


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class CopSatiri(BaseModel):
    id: int
    tablo: str
    kayit_id: Optional[str] = None
    etiket: Optional[str] = None
    silen_email: Optional[str] = None
    silen_rol: Optional[str] = None
    sahip_email: Optional[str] = None
    silinme: Optional[datetime] = None
    geri_alindi: bool = False
    geri_alan: Optional[str] = None
    geri_alinma: Optional[datetime] = None
    #: Aynı işlemde silinen, birlikte geri gelecek bağlı kayıt sayısı.
    bagli_sayisi: int = 0
    #: Kalıcı silineceği an (silinme + saklama günü).
    kalici_silinme: Optional[datetime] = None


class CopListesi(BaseModel):
    items: List[CopSatiri]
    toplam: int
    sayfa: int
    adet: int
    saklama_gun: int
    tablolar: List[str]


class CopAyrintisi(CopSatiri):
    veri: Dict[str, Any] = {}


class AyarGirdisi(BaseModel):
    gun: int = Field(..., ge=1, le=365)


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
    return (kullanici.email or "").strip().lower()


def _musteri_iste(request: Request) -> str:
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    eposta = (kullanici.email or "").strip().lower()
    if not eposta:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "eposta_yok"})
    return eposta


def _hata(exc: servis.CopHatasi) -> HTTPException:
    return HTTPException(status_code=exc.kod, detail={"kod": exc.anahtar, **exc.ek})


async def _bagli_sayilari(db: AsyncSession, gruplar: List[str]) -> Dict[str, int]:
    if not gruplar:
        return {}
    satirlar = (
        await db.execute(
            select(CopKutusu.grup, func.count(CopKutusu.id))
            .where(CopKutusu.grup.in_(gruplar), CopKutusu.geri_alindi.is_(False))
            .group_by(CopKutusu.grup)
        )
    ).all()
    return {g: int(n) for g, n in satirlar}


def _satir(k: CopKutusu, bagli: Dict[str, int], gun: int) -> CopSatiri:
    from datetime import timedelta

    silinme = servis._utc(k.silinme)
    return CopSatiri(
        id=k.id,
        tablo=k.tablo,
        kayit_id=k.kayit_id,
        etiket=k.etiket,
        silen_email=k.silen_email,
        silen_rol=k.silen_rol,
        sahip_email=k.sahip_email,
        silinme=silinme,
        geri_alindi=bool(k.geri_alindi),
        geri_alan=k.geri_alan,
        geri_alinma=servis._utc(k.geri_alinma),
        bagli_sayisi=max(0, bagli.get(k.grup, 1) - 1) if not k.geri_alindi else 0,
        kalici_silinme=(silinme + timedelta(days=gun)) if silinme else None,
    )


async def _liste(
    db: AsyncSession,
    kosullar: list,
    *,
    tablo: Optional[str],
    q: Optional[str],
    sayfa: int,
    adet: int,
) -> CopListesi:
    gun = await servis.saklama_gunu(db)
    # Çocuk tablolar (kontrol listesi, bağımlılık) görevle birlikte geri gelir; ayrı satır değil.
    kosullar = list(kosullar) + [CopKutusu.tablo.notin_(servis.COCUK_TABLOLAR)]
    tablolar = [
        t for (t,) in (await db.execute(select(CopKutusu.tablo).where(*kosullar).distinct())).all()
    ]
    if tablo:
        kosullar.append(CopKutusu.tablo == tablo)
    arama = (q or "").strip()
    if arama:
        desen = f"%{arama}%"
        kosullar.append(
            or_(
                CopKutusu.etiket.ilike(desen),
                CopKutusu.sahip_email.ilike(desen),
                CopKutusu.silen_email.ilike(desen),
                CopKutusu.kayit_id == arama,
            )
        )
    toplam = (await db.execute(select(func.count(CopKutusu.id)).where(*kosullar))).scalar() or 0
    kayitlar = (
        await db.execute(
            select(CopKutusu)
            .where(*kosullar)
            .order_by(CopKutusu.silinme.desc(), CopKutusu.id.desc())
            .offset((sayfa - 1) * adet)
            .limit(adet)
        )
    ).scalars().all()
    bagli = await _bagli_sayilari(db, list({k.grup for k in kayitlar}))
    return CopListesi(
        items=[_satir(k, bagli, gun) for k in kayitlar],
        toplam=int(toplam),
        sayfa=sayfa,
        adet=adet,
        saklama_gun=gun,
        tablolar=sorted(tablolar),
    )


async def _kayit(db: AsyncSession, kayit_id: int) -> CopKutusu:
    k = (await db.execute(select(CopKutusu).where(CopKutusu.id == kayit_id))).scalar_one_or_none()
    if k is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"kod": "bulunamadi"})
    return k


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("", response_model=CopListesi)
async def yonetici_listesi(
    request: Request,
    tablo: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    geri_alinanlar: bool = Query(False),
    sayfa: int = Query(1, ge=1),
    adet: int = Query(50, ge=1, le=EN_COK_ADET),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    kosullar = [] if geri_alinanlar else [CopKutusu.geri_alindi.is_(False)]
    return await _liste(db, kosullar, tablo=tablo, q=q, sayfa=sayfa, adet=adet)


@yonetici_router.get("/{kayit_id}", response_model=CopAyrintisi)
async def yonetici_ayrinti(kayit_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    k = await _kayit(db, kayit_id)
    bagli = await _bagli_sayilari(db, [k.grup])
    return CopAyrintisi(
        **_satir(k, bagli, await servis.saklama_gunu(db)).model_dump(), veri=servis.veri_coz(k)
    )


@yonetici_router.post("/{kayit_id}/geri-al")
async def yonetici_geri_al(kayit_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    k = await _kayit(db, kayit_id)
    try:
        return await servis.geri_al(db, k, geri_alan=yonetici, request=request)
    except servis.CopHatasi as exc:
        raise _hata(exc) from exc


@yonetici_router.delete("/{kayit_id}")
async def yonetici_kalici_sil(kayit_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    k = await _kayit(db, kayit_id)
    await servis.kalici_sil(db, k, request=request)
    return {"silindi": kayit_id}


@yonetici_router.put("/ayar")
async def saklama_ayari(request: Request, govde: AyarGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    """Saklama süresi (gün). site_settings `cop_kutusu_gun`."""
    _yonetici_iste(request)
    from models.site_settings import Site_settings

    satir = (
        await db.execute(select(Site_settings).where(Site_settings.setting_key == servis.AYAR_ANAHTARI))
    ).scalar_one_or_none()
    if satir is None:
        db.add(Site_settings(setting_key=servis.AYAR_ANAHTARI, setting_value=str(govde.gun)))
    else:
        satir.setting_value = str(govde.gun)
    await db.commit()
    return {"saklama_gun": govde.gun}


# --------------------------------------------------------------------------
# Müşteri: yalnız kendi sildiği, kendi kayıtları
# --------------------------------------------------------------------------
def _musteri_kosullari(eposta: str) -> list:
    return [
        CopKutusu.sahip_email == eposta,
        CopKutusu.silen_email == eposta,
        CopKutusu.geri_alindi.is_(False),
    ]


@musteri_router.get("", response_model=CopListesi)
async def musteri_listesi(
    request: Request,
    tablo: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sayfa: int = Query(1, ge=1),
    adet: int = Query(50, ge=1, le=EN_COK_ADET),
    db: AsyncSession = _Depends(get_db),
):
    eposta = _musteri_iste(request)
    liste = await _liste(db, _musteri_kosullari(eposta), tablo=tablo, q=q, sayfa=sayfa, adet=adet)
    # Müşteriye silenin/sahibin e-postası gerekmiyor (ikisi de kendisi).
    for s in liste.items:
        s.silen_email = None
        s.sahip_email = None
    return liste


@musteri_router.post("/{kayit_id}/geri-al")
async def musteri_geri_al(kayit_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = _musteri_iste(request)
    k = (
        await db.execute(select(CopKutusu).where(CopKutusu.id == kayit_id, *_musteri_kosullari(eposta)))
    ).scalar_one_or_none()
    if k is None:
        # Başkasının kaydı da "yok": varlığı sızmasın.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"kod": "bulunamadi"})
    try:
        return await servis.geri_al(db, k, geri_alan=eposta, request=request, yalniz_sahip=eposta)
    except servis.CopHatasi as exc:
        raise _hata(exc) from exc


router = (yonetici_router, musteri_router)
