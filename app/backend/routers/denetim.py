"""Denetim kaydı uçları.

Kim ne görüyor
--------------
* Yönetici: bütün kayıt, filtreli ve sayfalı; alan bazında eski→yeni farkı
  dahil. Son 7 günün özeti ve filtre seçenekleri ayrı uçlarda.
* Müşteri: yalnız `/benim` — kendi yaptığı işler ile kendi kayıtlarına
  (projeler, faturalar, destek talepleri, ödemeler, siteleri, abonelikleri)
  yapılan işler. Fark JSON'u, IP özeti ve istek yolu DÖNMÜYOR; başkası
  yaptıysa kişinin e-postası değil yalnız rolü görünüyor. E-posta jetondan
  alınıyor, sorgu parametresinden değil.

Saklama
-------
365 günden eski satırlar siliniyor. Zamanlanmış görev yok (ücretsiz sunucu
uyuyor): yönetici listeyi açtığında, en çok günde bir kez temizleniyor.
"""

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from models.audit_log import AuditLog
from pydantic import BaseModel
from services.denetim import ISLEMLER, ROLLER
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/denetim", tags=["denetim"])
musteri_router = APIRouter(prefix="/api/v1/denetim", tags=["denetim"])

SAKLAMA_GUN = 365
LISTE_SINIRI = 200
MUSTERI_SINIRI = 50

#: Müşterinin "Hesap hareketleri"nde, sahibi olduğu kayıtlara yapılan
#: işleri görebildiği tablolar (client_email sahipliği). Taslak rapor gibi
#: müşteriye henüz açılmamış şeylerin varlığı sızmasın diye liste kapalı.
MUSTERI_TABLOLARI = (
    "projects", "invoices", "support_tickets", "payments",
    "client_sites", "service_subscriptions", "users",
)

_son_temizlik_gunu: Optional[date] = None


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class DenetimSatiri(BaseModel):
    id: int
    created_at: Optional[datetime] = None
    aktor_eposta: Optional[str] = None
    aktor_rol: Optional[str] = None
    islem: str
    tablo: str
    kayit_id: Optional[str] = None
    ozet: Optional[str] = None
    degisiklik: Optional[Dict[str, List[Any]]] = None
    istek_yolu: Optional[str] = None
    ip_ozeti: Optional[str] = None


class DenetimListesi(BaseModel):
    items: List[DenetimSatiri]
    total: int
    skip: int
    limit: int


class SayiSatiri(BaseModel):
    ad: str
    sayi: int


class DenetimOzeti(BaseModel):
    gun: int
    toplam: int
    tablolar: List[SayiSatiri]
    aktorler: List[SayiSatiri]
    islemler: List[SayiSatiri]


class FiltreSecenekleri(BaseModel):
    tablolar: List[str]
    islemler: List[str]
    roller: List[str]


class HareketSatiri(BaseModel):
    id: int
    created_at: Optional[datetime] = None
    islem: str
    tablo: str
    kayit_id: Optional[str] = None
    ozet: Optional[str] = None
    #: True: işlemi müşterinin kendisi yaptı. False: başkası (rolü aşağıda).
    kendisi: bool
    aktor_rol: Optional[str] = None


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _yonetici_iste(request: Request) -> None:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


def _gun_basi(gun: date) -> datetime:
    return datetime.combine(gun, time.min, tzinfo=timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    """Zaman UTC yazılıyor; SQLite saat dilimini atıyor — geri ekle ki ön yüz
    yerel saate doğru çevirsin."""
    if an is not None and an.tzinfo is None:
        return an.replace(tzinfo=timezone.utc)
    return an


def _satira_cevir(kayit: AuditLog) -> DenetimSatiri:
    degisiklik = None
    if kayit.degisiklik_json:
        try:
            degisiklik = json.loads(kayit.degisiklik_json)
        except (TypeError, ValueError):
            degisiklik = None
    return DenetimSatiri(
        id=kayit.id,
        created_at=_utc(kayit.created_at),
        aktor_eposta=kayit.aktor_eposta,
        aktor_rol=kayit.aktor_rol,
        islem=kayit.islem,
        tablo=kayit.tablo,
        kayit_id=kayit.kayit_id,
        ozet=kayit.ozet,
        degisiklik=degisiklik,
        istek_yolu=kayit.istek_yolu,
        # Tam özet gerekmiyor; aynı kaynaktan gelen işlemleri eşlemeye yetiyor.
        ip_ozeti=(kayit.ip_ozeti or "")[:12] or None,
    )


async def eski_kayitlari_temizle(db: AsyncSession, *, zorla: bool = False) -> int:
    """365 günden eski satırları siler; en çok günde bir kez çalışır."""
    global _son_temizlik_gunu
    bugun = _simdi().date()
    if not zorla and _son_temizlik_gunu == bugun:
        return 0
    _son_temizlik_gunu = bugun
    try:
        sonuc = await db.execute(
            delete(AuditLog).where(AuditLog.created_at < _simdi() - timedelta(days=SAKLAMA_GUN))
        )
        await db.commit()
        silinen = sonuc.rowcount or 0
        if silinen:
            logger.info("Denetim kaydı saklama temizliği: %d satır silindi", silinen)
        return silinen
    except Exception:  # noqa: BLE001 - liste yine de dönmeli
        logger.exception("Denetim kaydı saklama temizliği başarısız")
        await db.rollback()
        return 0


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("", response_model=DenetimListesi)
async def denetim_listesi(
    request: Request,
    aktor: Optional[str] = Query(None, max_length=200, description="E-postada geçen metin"),
    tablo: Optional[str] = Query(None, max_length=64),
    islem: Optional[str] = Query(None, max_length=32),
    kayit_id: Optional[str] = Query(None, max_length=64),
    baslangic: Optional[date] = Query(None, description="YYYY-AA-GG (dahil)"),
    bitis: Optional[date] = Query(None, description="YYYY-AA-GG (dahil)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=LISTE_SINIRI),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    await eski_kayitlari_temizle(db)

    kosullar = []
    if aktor and aktor.strip():
        kosullar.append(func.lower(AuditLog.aktor_eposta).contains(aktor.strip().lower(), autoescape=True))
    if tablo:
        kosullar.append(AuditLog.tablo == tablo.strip())
    if islem:
        kosullar.append(AuditLog.islem == islem.strip())
    if kayit_id:
        kosullar.append(AuditLog.kayit_id == kayit_id.strip())
    if baslangic:
        kosullar.append(AuditLog.created_at >= _gun_basi(baslangic))
    if bitis:
        kosullar.append(AuditLog.created_at < _gun_basi(bitis) + timedelta(days=1))

    sorgu = select(AuditLog)
    sayim = select(func.count(AuditLog.id))
    if kosullar:
        sorgu = sorgu.where(and_(*kosullar))
        sayim = sayim.where(and_(*kosullar))

    toplam = (await db.execute(sayim)).scalar() or 0
    sonuc = await db.execute(
        sorgu.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(skip).limit(limit)
    )
    return DenetimListesi(
        items=[_satira_cevir(k) for k in sonuc.scalars().all()],
        total=toplam,
        skip=skip,
        limit=limit,
    )


@yonetici_router.get("/ozet", response_model=DenetimOzeti)
async def denetim_ozeti(request: Request, db: AsyncSession = _Depends(get_db)):
    """Son 7 günde tablo, aktör ve işlem başına sayılar."""
    _yonetici_iste(request)
    esik = _simdi() - timedelta(days=7)
    kosul = AuditLog.created_at >= esik

    async def grupla(sutun, sinir: int = 10) -> List[SayiSatiri]:
        sayi = func.count(AuditLog.id)
        satirlar = await db.execute(
            select(sutun, sayi).where(kosul).group_by(sutun).order_by(sayi.desc()).limit(sinir)
        )
        return [SayiSatiri(ad=str(ad or ""), sayi=int(n)) for ad, n in satirlar.all()]

    toplam = (await db.execute(select(func.count(AuditLog.id)).where(kosul))).scalar() or 0
    # E-postası olmayan (anonim/sistem) işlemler rolüyle gruplanıyor.
    aktor_sutunu = func.coalesce(AuditLog.aktor_eposta, AuditLog.aktor_rol)
    return DenetimOzeti(
        gun=7,
        toplam=int(toplam),
        tablolar=await grupla(AuditLog.tablo),
        aktorler=await grupla(aktor_sutunu),
        islemler=await grupla(AuditLog.islem),
    )


@yonetici_router.get("/tablolar", response_model=FiltreSecenekleri)
async def filtre_secenekleri(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    sonuc = await db.execute(select(AuditLog.tablo).distinct().order_by(AuditLog.tablo))
    return FiltreSecenekleri(
        tablolar=[t for t in sonuc.scalars().all() if t],
        islemler=list(ISLEMLER),
        roller=list(ROLLER),
    )


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
@musteri_router.get("/benim", response_model=List[HareketSatiri])
async def hesap_hareketlerim(request: Request, db: AsyncSession = _Depends(get_db)):
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    eposta = (kullanici.email or "").strip().lower()
    if not eposta:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesabınızda e-posta adresi yok")

    sonuc = await db.execute(
        select(AuditLog)
        .where(
            or_(
                AuditLog.aktor_eposta == eposta,
                and_(AuditLog.ilgili_eposta == eposta, AuditLog.tablo.in_(MUSTERI_TABLOLARI)),
            )
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(MUSTERI_SINIRI)
    )
    return [
        HareketSatiri(
            id=k.id,
            created_at=_utc(k.created_at),
            islem=k.islem,
            tablo=k.tablo,
            kayit_id=k.kayit_id,
            ozet=k.ozet,
            kendisi=(k.aktor_eposta or "") == eposta,
            aktor_rol=k.aktor_rol,
        )
        for k in sonuc.scalars().all()
    ]


router = (musteri_router, yonetici_router)
