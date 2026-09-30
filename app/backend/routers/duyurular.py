"""Faz 2B — duyurular: yönetici yayınlar, müşteri panelinde kapatılabilir şerit + liste.

Yönetici  /api/v1/duyurular          (oluştur, düzenle, sil; okunma sayıları)
Kişi      /api/v1/duyurularim        (kendisine hedeflenen etkin duyurular; okundu/kapat)

Hedefleme
---------
* `tum`    — bütün müşteriler (yönetici hariç)
* `secili` — `hedef_epostalar` listesindekiler
* `ekip`   — ekip üyeleri (`staff`, etkin) ve yöneticiler
Yönetici panelinde yalnız ekip duyuruları görünüyor. Süresi (`bitis_at`)
geçmiş ya da yayından kaldırılmış duyuru kimseye dönmüyor.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from models.duyurular import DUYURU_HEDEFLERI, DUYURU_ONEMLERI, DuyuruOkumalari, Duyurular
from models.staff import Staff
from pydantic import BaseModel
from services import gorevler as gs
from services.gorevler import GorevHatasi
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(
    prefix="/api/v1/duyurular", tags=["duyurular"], dependencies=[_Depends(yonetici_gerekli)]
)
kisi_router = APIRouter(
    prefix="/api/v1/duyurularim",
    tags=["duyurular"],
    dependencies=[_Depends(modul_gerekli("duyurular"))],
)

BASLIK_SINIRI = 200
METIN_SINIRI = 4000
SECILI_SINIRI = 500
BILDIRIM_ALICI_SINIRI = 1000


class DuyuruGirdisi(BaseModel):
    baslik: str
    metin: Optional[str] = None
    onem: Optional[str] = "bilgi"
    hedef: Optional[str] = "tum"
    hedef_epostalar: Optional[List[str]] = None
    #: YYYY-MM-DD (o günün sonuna kadar) ya da tam ISO an; boş = süresiz.
    bitis: Optional[str] = None
    yayinda: Optional[bool] = True
    #: Hedef kitleye bildirim de gitsin mi (matris: `duyuru`).
    bildirim_gonder: Optional[bool] = False


class DuyuruGuncelleme(BaseModel):
    baslik: Optional[str] = None
    metin: Optional[str] = None
    onem: Optional[str] = None
    hedef: Optional[str] = None
    hedef_epostalar: Optional[List[str]] = None
    bitis: Optional[str] = None
    yayinda: Optional[bool] = None


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _simdi() -> datetime:
    return datetime.now(timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli")
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
    return gs.eposta_duzelt(kullanici.email)


def _kisi_iste(request: Request):
    kullanici, yonetici = _yonetici_mi(request)
    eposta = gs.eposta_duzelt(getattr(kullanici, "email", None))
    if not eposta:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli")
    return eposta, yonetici


def _bitis_coz(ham: Optional[str]) -> Optional[datetime]:
    d = (ham or "").strip()
    if not d:
        return None
    try:
        if len(d) <= 10:
            gun = datetime.strptime(d, "%Y-%m-%d")
            return gun.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        an = datetime.fromisoformat(d.replace("Z", "+00:00"))
        return _utc(an)
    except ValueError as exc:
        raise GorevHatasi(400, "tarih_gecersiz") from exc


def _epostalar(ham: Optional[List[str]]) -> List[str]:
    sonuc: List[str] = []
    for e in ham or []:
        t = gs.eposta_duzelt(e)
        if not t:
            continue
        if "@" not in t or len(t) > 254 or " " in t:
            raise GorevHatasi(400, "eposta_gecersiz")
        if t not in sonuc:
            sonuc.append(t)
    if len(sonuc) > SECILI_SINIRI:
        raise GorevHatasi(400, "cok_fazla_alici")
    return sonuc


def _hedef_listesi(d: Duyurular) -> List[str]:
    try:
        liste = json.loads(d.hedef_epostalar or "[]")
    except (TypeError, ValueError):
        return []
    return [str(x) for x in liste] if isinstance(liste, list) else []


async def _ekipten_mi(db: AsyncSession, eposta: str) -> bool:
    return (
        await db.execute(select(Staff.id).where(func.lower(Staff.email) == eposta).where(Staff.aktif.isnot(False)))
    ).first() is not None


def hedefte_mi(d: Duyurular, eposta: str, *, yonetici: bool, ekipten: bool) -> bool:
    if d.hedef == "ekip":
        return yonetici or ekipten
    if yonetici:
        return False
    if d.hedef == "tum":
        return True
    return eposta in _hedef_listesi(d)


def _etkin_mi(d: Duyurular, simdi: datetime) -> bool:
    if not d.yayinda:
        return False
    bitis = _utc(d.bitis_at)
    return bitis is None or bitis > simdi


def _yonetici_sozlugu(d: Duyurular, okunma: int = 0, kapatma: int = 0) -> Dict[str, Any]:
    return {
        "id": d.id,
        "baslik": d.baslik,
        "metin": d.metin,
        "onem": d.onem,
        "hedef": d.hedef,
        "hedef_epostalar": _hedef_listesi(d),
        "bitis_at": gs.iso(d.bitis_at),
        "yayinda": bool(d.yayinda),
        "etkin": _etkin_mi(d, _simdi()),
        "okunma_sayisi": okunma,
        "kapatma_sayisi": kapatma,
        "created_at": gs.iso(d.created_at),
    }


def _kisi_sozlugu(d: Duyurular, okuma: Optional[DuyuruOkumalari]) -> Dict[str, Any]:
    return {
        "id": d.id,
        "baslik": d.baslik,
        "metin": d.metin,
        "onem": d.onem,
        "bitis_at": gs.iso(d.bitis_at),
        "created_at": gs.iso(d.created_at),
        "okundu": bool(okuma and okuma.okundu_at),
        "kapatildi": bool(okuma and okuma.kapatildi),
    }


async def _bul(db: AsyncSession, duyuru_id: int) -> Duyurular:
    d = (await db.execute(select(Duyurular).where(Duyurular.id == duyuru_id))).scalar_one_or_none()
    if d is None:
        raise GorevHatasi(404, "duyuru_yok")
    return d


async def _alicilar(db: AsyncSession, d: Duyurular) -> List[Dict[str, str]]:
    if d.hedef == "secili":
        return [{"email": e, "role": "client"} for e in _hedef_listesi(d)]
    if d.hedef == "ekip":
        from services.notify import admin_recipients

        ekip = [
            {"email": gs.eposta_duzelt(e), "role": "admin"}
            for (e,) in (await db.execute(select(Staff.email).where(Staff.aktif.isnot(False)))).all()
            if e
        ]
        return ekip + list(await admin_recipients(db))
    from services.moduller import musteri_listesi

    return [{"email": m["eposta"], "role": "client"} for m in await musteri_listesi(db) if m.get("eposta")]


async def _bildir(db: AsyncSession, d: Duyurular) -> None:
    try:
        from services.notify import dispatch, render

        alicilar = (await _alicilar(db, d))[:BILDIRIM_ALICI_SINIRI]
        if not alicilar:
            return
        baslik, govde = await render(
            db, "duyuru", d.baslik, d.metin or "", {"baslik": d.baslik, "metin": d.metin or "", "onem": d.onem}
        )
        await dispatch(
            db,
            event_type="duyuru",
            title=baslik,
            body=govde,
            recipients=alicilar,
            link="/client",
            ref_type="duyuru",
            ref_id=d.id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Duyuru bildirimi gönderilemedi")


def _alanlari_uygula(d: Duyurular, govde, alanlar) -> None:
    if "baslik" in alanlar:
        b = (govde.baslik or "").strip()[:BASLIK_SINIRI]
        if not b:
            raise GorevHatasi(400, "baslik_gerekli")
        d.baslik = b
    if "metin" in alanlar:
        d.metin = (govde.metin or "").strip()[:METIN_SINIRI] or None
    if "onem" in alanlar and govde.onem is not None:
        if govde.onem not in DUYURU_ONEMLERI:
            raise GorevHatasi(400, "onem_gecersiz")
        d.onem = govde.onem
    if "hedef" in alanlar and govde.hedef is not None:
        if govde.hedef not in DUYURU_HEDEFLERI:
            raise GorevHatasi(400, "hedef_gecersiz")
        d.hedef = govde.hedef
    if "hedef_epostalar" in alanlar:
        d.hedef_epostalar = json.dumps(_epostalar(govde.hedef_epostalar))
    if "bitis" in alanlar:
        d.bitis_at = _bitis_coz(govde.bitis)
    if "yayinda" in alanlar and govde.yayinda is not None:
        d.yayinda = bool(govde.yayinda)
    if d.hedef == "secili" and not _hedef_listesi(d):
        raise GorevHatasi(400, "alici_gerekli")


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("")
async def duyuru_listesi(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    duyurular = list((await db.execute(select(Duyurular).order_by(Duyurular.id.desc()).limit(200))).scalars().all())
    idler = [d.id for d in duyurular]
    okunma: Dict[int, int] = {}
    kapatma: Dict[int, int] = {}
    if idler:
        for did, o, k in (
            await db.execute(
                select(
                    DuyuruOkumalari.duyuru_id,
                    func.count(DuyuruOkumalari.okundu_at),
                    func.sum(case((DuyuruOkumalari.kapatildi.is_(True), 1), else_=0)),
                )
                .where(DuyuruOkumalari.duyuru_id.in_(idler))
                .group_by(DuyuruOkumalari.duyuru_id)
            )
        ).all():
            okunma[did] = int(o or 0)
            kapatma[did] = int(k or 0)
    return [_yonetici_sozlugu(d, okunma.get(d.id, 0), kapatma.get(d.id, 0)) for d in duyurular]


@yonetici_router.post("")
async def duyuru_ekle(request: Request, govde: DuyuruGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    ben = _yonetici_iste(request)
    d = Duyurular(onem="bilgi", hedef="tum", yayinda=True, olusturan_eposta=ben, hedef_epostalar="[]")
    _alanlari_uygula(d, govde, {"baslik", "metin", "onem", "hedef", "hedef_epostalar", "bitis", "yayinda"})
    db.add(d)
    await db.commit()
    await db.refresh(d)
    if govde.bildirim_gonder and _etkin_mi(d, _simdi()):
        await _bildir(db, d)
    return _yonetici_sozlugu(d)


@yonetici_router.patch("/{duyuru_id}")
async def duyuru_guncelle(duyuru_id: int, request: Request, govde: DuyuruGuncelleme = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    d = await _bul(db, duyuru_id)
    _alanlari_uygula(d, govde, govde.model_fields_set)
    await db.commit()
    await db.refresh(d)
    return _yonetici_sozlugu(d)


@yonetici_router.delete("/{duyuru_id}")
async def duyuru_sil(duyuru_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    d = await _bul(db, duyuru_id)
    for o in (await db.execute(select(DuyuruOkumalari).where(DuyuruOkumalari.duyuru_id == d.id))).scalars().all():
        await db.delete(o)
    await db.delete(d)
    await db.commit()
    return {"silindi": duyuru_id}


# --------------------------------------------------------------------------
# Kişi (müşteri / ekip)
# --------------------------------------------------------------------------
async def _gorunur_duyurular(db: AsyncSession, eposta: str, yonetici: bool) -> List[Duyurular]:
    simdi = _simdi()
    ekipten = await _ekipten_mi(db, eposta)
    adaylar = (
        await db.execute(select(Duyurular).where(Duyurular.yayinda.is_(True)).order_by(Duyurular.id.desc()).limit(200))
    ).scalars().all()
    return [d for d in adaylar if _etkin_mi(d, simdi) and hedefte_mi(d, eposta, yonetici=yonetici, ekipten=ekipten)]


async def _okuma(db: AsyncSession, duyuru_id: int, eposta: str) -> DuyuruOkumalari:
    o = (
        await db.execute(select(DuyuruOkumalari).where(DuyuruOkumalari.duyuru_id == duyuru_id).where(DuyuruOkumalari.eposta == eposta))
    ).scalar_one_or_none()
    if o is not None:
        return o
    o = DuyuruOkumalari(duyuru_id=duyuru_id, eposta=eposta, kapatildi=False)
    try:
        async with db.begin_nested():
            db.add(o)
            await db.flush()
    except IntegrityError:
        o = (
            await db.execute(select(DuyuruOkumalari).where(DuyuruOkumalari.duyuru_id == duyuru_id).where(DuyuruOkumalari.eposta == eposta))
        ).scalar_one()
    return o


async def _hedefli_bul(db: AsyncSession, duyuru_id: int, eposta: str, yonetici: bool) -> Duyurular:
    for d in await _gorunur_duyurular(db, eposta, yonetici):
        if d.id == duyuru_id:
            return d
    raise GorevHatasi(404, "duyuru_yok")


@kisi_router.get("")
async def duyurularim(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta, yonetici = _kisi_iste(request)
    duyurular = await _gorunur_duyurular(db, eposta, yonetici)
    okumalar: Dict[int, DuyuruOkumalari] = {}
    if duyurular:
        for o in (
            await db.execute(
                select(DuyuruOkumalari)
                .where(DuyuruOkumalari.eposta == eposta)
                .where(DuyuruOkumalari.duyuru_id.in_([d.id for d in duyurular]))
            )
        ).scalars().all():
            okumalar[o.duyuru_id] = o
    liste = [_kisi_sozlugu(d, okumalar.get(d.id)) for d in duyurular]
    return {"duyurular": liste, "okunmamis": sum(1 for x in liste if not x["okundu"])}


@kisi_router.post("/{duyuru_id}/okundu")
async def okundu_isaretle(duyuru_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    eposta, yonetici = _kisi_iste(request)
    d = await _hedefli_bul(db, duyuru_id, eposta, yonetici)
    o = await _okuma(db, d.id, eposta)
    if o.okundu_at is None:
        o.okundu_at = _simdi()
    await db.commit()
    return _kisi_sozlugu(d, o)


@kisi_router.post("/{duyuru_id}/kapat")
async def seritten_kapat(duyuru_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Şeritten kaldırır (okundu da sayılır); "Duyurular" listesinde kalır."""
    eposta, yonetici = _kisi_iste(request)
    d = await _hedefli_bul(db, duyuru_id, eposta, yonetici)
    o = await _okuma(db, d.id, eposta)
    o.kapatildi = True
    if o.okundu_at is None:
        o.okundu_at = _simdi()
    await db.commit()
    return _kisi_sozlugu(d, o)


router = (yonetici_router, kisi_router)
