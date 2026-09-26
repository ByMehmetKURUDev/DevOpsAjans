"""Hizmet abonelikleri ve aylık raporlar.

Neden ayrı
----------
Fatura tek seferlik bir tutar; abonelik "her ay şu iş yapılıyor"
demek. Bir müşterinin üç aboneliği olabiliyor ve her biri kendi
raporunu üretiyor.

Taslak / yayın
--------------
Rapor hazırlanırken `taslak`; müşteri panelinde görünmüyor.
Yayınlanmadan görünseydi yarım rapor müşteriye gider, yanlış sayılar
konuşulurdu. Yayınlandığında abonelik bir sonraki döneme ilerliyor.

Kim ne görüyor
--------------
Abonelik yönetimi ve taslaklar yalnızca yöneticide. Müşteri yalnızca
kendi yayınlanmış raporlarını görüyor; e-posta eşleşmesi sunucuda
yapılıyor, gövdeden gelen adrese güvenilmiyor.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from models.service_subscriptions import Service_reports, Service_subscriptions
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/abonelik", tags=["abonelik"])
musteri_router = APIRouter(prefix="/api/v1/raporlarim", tags=["abonelik"])

PERIYOTLAR = {"aylik", "yillik"}
DURUMLAR = {"aktif", "duraklatildi", "iptal"}


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class AbonelikGirdisi(BaseModel):
    client_email: str
    client_name: Optional[str] = None
    hizmet: str
    baslik: Optional[str] = None
    tutar: Optional[float] = None
    para_birimi: str = "TRY"
    periyot: str = "aylik"
    notlar: Optional[str] = None


class AbonelikSatiri(BaseModel):
    id: int
    client_email: str
    client_name: Optional[str] = None
    hizmet: str
    baslik: Optional[str] = None
    tutar: Optional[float] = None
    para_birimi: Optional[str] = None
    periyot: Optional[str] = None
    durum: Optional[str] = None
    baslangic: Optional[str] = None
    sonraki_rapor: Optional[str] = None
    notlar: Optional[str] = None

    class Config:
        from_attributes = True


class DurumGirdisi(BaseModel):
    durum: str


class RaporGirdisi(BaseModel):
    subscription_id: int
    donem: Optional[str] = None
    baslik: Optional[str] = None
    ozet: Optional[str] = None
    metrikler: Optional[Dict[str, Any]] = None


class RaporSatiri(BaseModel):
    id: int
    subscription_id: Optional[int] = None
    client_email: str
    hizmet: Optional[str] = None
    donem: str
    baslik: Optional[str] = None
    ozet: Optional[str] = None
    metrikler: Optional[Dict[str, Any]] = None
    durum: Optional[str] = None
    yayin_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _yonetici_iste(request: Request) -> None:
    _, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem yönetici yetkisi istiyor",
        )


def _bu_donem() -> str:
    simdi = datetime.now()
    return f"{simdi.year:04d}-{simdi.month:02d}"


def _sonraki_donem(donem: str) -> str:
    """YYYY-MM biçimindeki dönemi bir ay ilerletir."""
    try:
        yil, ay = donem.split("-")
        yil, ay = int(yil), int(ay)
    except (ValueError, AttributeError):
        return _bu_donem()
    if ay >= 12:
        return f"{yil + 1:04d}-01"
    return f"{yil:04d}-{ay + 1:02d}"


def _metrik_coz(metin: Optional[str]) -> Optional[Dict[str, Any]]:
    if not metin:
        return None
    try:
        veri = json.loads(metin)
        return veri if isinstance(veri, dict) else None
    except (ValueError, TypeError):
        # Bozuk JSON raporu kaybettirmesin: ozet ve donem yine gorunur.
        logger.warning("Rapor metrikleri cozulemedi")
        return None


def _rapora_cevir(kayit: Service_reports) -> RaporSatiri:
    return RaporSatiri(
        id=kayit.id,
        subscription_id=kayit.subscription_id,
        client_email=kayit.client_email,
        hizmet=kayit.hizmet,
        donem=kayit.donem,
        baslik=kayit.baslik,
        ozet=kayit.ozet,
        metrikler=_metrik_coz(kayit.metrikler),
        durum=kayit.durum,
        yayin_at=kayit.yayin_at,
    )


def _eposta(kullanici) -> str:
    deger = getattr(kullanici, "email", None) if kullanici else None
    return str(deger).strip().lower() if deger else ""


# --------------------------------------------------------------------------
# Abonelikler — yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("", response_model=List[AbonelikSatiri])
async def abonelik_listesi(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    sonuc = await db.execute(
        select(Service_subscriptions).order_by(Service_subscriptions.id.desc())
    )
    return list(sonuc.scalars().all())


@yonetici_router.post("", response_model=AbonelikSatiri)
async def abonelik_ekle(
    request: Request,
    govde: AbonelikGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)

    eposta = (govde.client_email or "").strip().lower()
    hizmet = (govde.hizmet or "").strip()
    periyot = (govde.periyot or "aylik").strip().lower()
    if "@" not in eposta or not hizmet:
        raise HTTPException(status_code=400, detail="Müşteri e-postası ve hizmet gerekli")
    if periyot not in PERIYOTLAR:
        raise HTTPException(status_code=400, detail="Periyot aylik ya da yillik olmalı")

    donem = _bu_donem()
    kayit = Service_subscriptions(
        client_email=eposta,
        client_name=(govde.client_name or "").strip() or None,
        hizmet=hizmet,
        baslik=(govde.baslik or "").strip() or None,
        tutar=govde.tutar,
        para_birimi=(govde.para_birimi or "TRY").upper(),
        periyot=periyot,
        durum="aktif",
        baslangic=donem,
        sonraki_rapor=donem,
        notlar=(govde.notlar or "").strip() or None,
    )
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)
    return kayit


@yonetici_router.post("/{abonelik_id}/durum", response_model=AbonelikSatiri)
async def abonelik_durumu(
    abonelik_id: int,
    request: Request,
    govde: DurumGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)

    durum = (govde.durum or "").strip().lower()
    if durum not in DURUMLAR:
        raise HTTPException(status_code=400, detail="Geçersiz durum")

    sonuc = await db.execute(
        select(Service_subscriptions).where(Service_subscriptions.id == abonelik_id)
    )
    kayit = sonuc.scalar_one_or_none()
    if kayit is None:
        raise HTTPException(status_code=404, detail="Abonelik bulunamadı")

    kayit.durum = durum
    await db.commit()
    await db.refresh(kayit)
    return kayit


@yonetici_router.delete("/{abonelik_id}")
async def abonelik_sil(
    abonelik_id: int,
    request: Request,
    db: AsyncSession = _Depends(get_db),
):
    """Aboneliği siler; raporları durur.

    Yayınlanmış raporlar müşterinin gördüğü geçmiş. Abonelik bittiği
    için geçmişi silmek, müşteriye verilmiş bilgiyi geri almak olurdu.
    """
    _yonetici_iste(request)

    sonuc = await db.execute(
        select(Service_subscriptions).where(Service_subscriptions.id == abonelik_id)
    )
    kayit = sonuc.scalar_one_or_none()
    if kayit is None:
        raise HTTPException(status_code=404, detail="Abonelik bulunamadı")

    await db.delete(kayit)
    await db.commit()
    return {"silindi": abonelik_id}


# --------------------------------------------------------------------------
# Raporlar — yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("/raporlar", response_model=List[RaporSatiri])
async def rapor_listesi(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    sonuc = await db.execute(select(Service_reports).order_by(Service_reports.id.desc()).limit(300))
    return [_rapora_cevir(r) for r in sonuc.scalars().all()]


@yonetici_router.post("/raporlar", response_model=RaporSatiri)
async def rapor_yaz(
    request: Request,
    govde: RaporGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    """Taslak rapor oluşturur ya da aynı dönemin taslağını günceller.

    Aynı abonelik ve döneme ikinci bir rapor açılmıyor: müşteri aynı
    ay için iki farklı rapor görürse hangisinin geçerli olduğunu
    bilemez.
    """
    _yonetici_iste(request)

    sonuc = await db.execute(
        select(Service_subscriptions).where(Service_subscriptions.id == govde.subscription_id)
    )
    abonelik = sonuc.scalar_one_or_none()
    if abonelik is None:
        raise HTTPException(status_code=404, detail="Abonelik bulunamadı")

    donem = (govde.donem or abonelik.sonraki_rapor or _bu_donem()).strip()

    mevcut = await db.execute(
        select(Service_reports)
        .where(Service_reports.subscription_id == abonelik.id)
        .where(Service_reports.donem == donem)
    )
    kayit = mevcut.scalars().first()

    if kayit is not None and kayit.durum == "yayinlandi":
        raise HTTPException(
            status_code=409,
            detail="Bu dönemin raporu yayımlandı; yeni dönem seçin",
        )

    metrik_metni = (
        json.dumps(govde.metrikler, ensure_ascii=False) if govde.metrikler else None
    )

    if kayit is None:
        kayit = Service_reports(
            subscription_id=abonelik.id,
            client_email=abonelik.client_email,
            hizmet=abonelik.hizmet,
            donem=donem,
            durum="taslak",
        )
        db.add(kayit)

    kayit.baslik = (govde.baslik or "").strip() or kayit.baslik
    kayit.ozet = govde.ozet if govde.ozet is not None else kayit.ozet
    if metrik_metni is not None:
        kayit.metrikler = metrik_metni

    await db.commit()
    await db.refresh(kayit)
    return _rapora_cevir(kayit)


@yonetici_router.post("/raporlar/{rapor_id}/yayimla", response_model=RaporSatiri)
async def rapor_yayimla(
    rapor_id: int,
    request: Request,
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)

    sonuc = await db.execute(select(Service_reports).where(Service_reports.id == rapor_id))
    kayit = sonuc.scalar_one_or_none()
    if kayit is None:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı")
    if not (kayit.ozet or "").strip():
        # Bos rapor yayimlamak, musteriye "bu ay bir sey yapmadik"
        # demenin en kotu yolu olurdu.
        raise HTTPException(status_code=400, detail="Özet boşken rapor yayımlanamaz")

    kayit.durum = "yayinlandi"
    kayit.yayin_at = datetime.now()

    if kayit.subscription_id:
        abonelik = await db.execute(
            select(Service_subscriptions).where(
                Service_subscriptions.id == kayit.subscription_id
            )
        )
        abonelik = abonelik.scalar_one_or_none()
        if abonelik is not None and (abonelik.sonraki_rapor or "") <= kayit.donem:
            abonelik.sonraki_rapor = _sonraki_donem(kayit.donem)

    await db.commit()
    await db.refresh(kayit)
    return _rapora_cevir(kayit)


@yonetici_router.delete("/raporlar/{rapor_id}")
async def rapor_sil(
    rapor_id: int,
    request: Request,
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    sonuc = await db.execute(select(Service_reports).where(Service_reports.id == rapor_id))
    kayit = sonuc.scalar_one_or_none()
    if kayit is None:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı")
    await db.delete(kayit)
    await db.commit()
    return {"silindi": rapor_id}


# --------------------------------------------------------------------------
# Müşteri — kendi yayınlanmış raporları
# --------------------------------------------------------------------------
@musteri_router.get("", response_model=List[RaporSatiri])
async def kendi_raporlarim(request: Request, db: AsyncSession = _Depends(get_db)):
    """Müşterinin yayınlanmış raporları.

    Adres oturumdan alınıyor, sorgudan değil: yoksa müşteri başkasının
    e-postasını yazıp raporlarını okuyabilirdi.
    """
    kullanici, yonetici = _yonetici_mi(request)
    eposta = _eposta(kullanici)
    if not eposta:
        raise HTTPException(status_code=403, detail="Oturum gerekli")

    sorgu = (
        select(Service_reports)
        .where(Service_reports.durum == "yayinlandi")
        .order_by(Service_reports.donem.desc(), Service_reports.id.desc())
    )
    if not yonetici:
        sorgu = sorgu.where(Service_reports.client_email == eposta)

    sonuc = await db.execute(sorgu.limit(200))
    return [_rapora_cevir(r) for r in sonuc.scalars().all()]


# `include_routers_from_package` liste de kabul ediyor.
router = (yonetici_router, musteri_router)
