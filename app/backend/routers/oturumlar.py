"""Faz 2D — oturum yönetimi uçları.

Kim ne yapabiliyor
------------------
* Giriş yapmış herkes (`/api/v1/oturumlarim`): kendi etkin oturumlarını
  görür ("bu cihaz" işaretli), tek tek kapatır, "diğer tüm oturumları
  kapat" der. E-posta JETONDAN alınıyor; başkasının oturumu 404.
* Yönetici (`/api/v1/oturumlar`): bütün oturumlar (e-posta süzgeci,
  yalnız etkinler, sayfalı), tek oturumu kapatma, bir kullanıcıyı her
  yerden çıkarma (bütün oturumları iptal + kullanıcı bazlı kesim — sid
  taşımayan eski jetonlar da düşüyor). Yönetici kendi ŞU ANKİ oturumunu bu
  uçlarla kapatamıyor (400): paneli kilitlememek için "Çıkış yap" var.

`sid` hiçbir yanıtta dönmüyor; iptaller denetim kaydına sid'siz düşüyor.
"""

import logging
from datetime import datetime
from typing import List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from models.oturumlar import Oturumlar
from pydantic import BaseModel
from services import oturumlar as servis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

kisi_router = APIRouter(prefix="/api/v1/oturumlarim", tags=["oturumlar"])
yonetici_router = APIRouter(prefix="/api/v1/oturumlar", tags=["oturumlar"])

EN_COK_ADET = 100


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class OturumSatiri(BaseModel):
    id: int
    cihaz: Optional[str] = None
    ip_ozet: Optional[str] = None
    olusturma: Optional[datetime] = None
    son_gorulme: Optional[datetime] = None
    bitis: Optional[datetime] = None
    bu_cihaz: bool = False


class YoneticiOturumSatiri(OturumSatiri):
    email: str
    rol: Optional[str] = None
    etkin: bool = True
    iptal_zamani: Optional[datetime] = None
    iptal_eden: Optional[str] = None


class OturumListesi(BaseModel):
    items: List[YoneticiOturumSatiri]
    toplam: int
    sayfa: int
    adet: int


class KullaniciCikisGirdisi(BaseModel):
    email: str


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _kisi_iste(request: Request) -> str:
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    eposta = (kullanici.email or "").strip().lower()
    if not eposta:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesabınızda e-posta adresi tanımlı değil")
    return eposta


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
    return (kullanici.email or "").strip().lower()


def _satir(s: Oturumlar, bu_sid: Optional[str]) -> OturumSatiri:
    return OturumSatiri(
        id=s.id,
        cihaz=s.cihaz,
        ip_ozet=s.ip_ozet,
        olusturma=servis._utc(s.olusturma),
        son_gorulme=servis._utc(s.son_gorulme),
        bitis=servis._utc(s.bitis),
        bu_cihaz=bool(bu_sid) and s.sid == bu_sid,
    )


def _yonetici_satiri(s: Oturumlar, bu_sid: Optional[str]) -> YoneticiOturumSatiri:
    return YoneticiOturumSatiri(
        **_satir(s, bu_sid).model_dump(),
        email=s.email,
        rol=s.rol,
        etkin=servis.etkin_mi(s),
        iptal_zamani=servis._utc(s.iptal_zamani),
        iptal_eden=s.iptal_eden,
    )


# --------------------------------------------------------------------------
# Kişi: kendi oturumları
# --------------------------------------------------------------------------
@kisi_router.get("", response_model=List[OturumSatiri])
async def oturumlarim(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = _kisi_iste(request)
    bu_sid = servis.istek_sid(request)
    satirlar = (
        await db.execute(
            select(Oturumlar)
            .where(Oturumlar.email == eposta, servis.etkin_kosulu())
            .order_by(Oturumlar.son_gorulme.desc(), Oturumlar.id.desc())
            .limit(EN_COK_ADET)
        )
    ).scalars().all()
    liste = [_satir(s, bu_sid) for s in satirlar]
    # "Bu cihaz" en üstte.
    liste.sort(key=lambda s: not s.bu_cihaz)
    return liste


@kisi_router.delete("/{oturum_id}")
async def oturumumu_kapat(oturum_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = _kisi_iste(request)
    satir = (
        await db.execute(select(Oturumlar).where(Oturumlar.id == oturum_id, Oturumlar.email == eposta))
    ).scalar_one_or_none()
    if satir is None:
        # Başkasının oturumu da "yok": varlığı sızmasın.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Oturum bulunamadı")
    sayi = await servis.iptal_et(db, [satir], iptal_eden=eposta, request=request)
    return {"kapatilan": sayi, "bu_cihaz": satir.sid == servis.istek_sid(request)}


@kisi_router.post("/digerlerini-kapat")
async def digerlerini_kapat(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = _kisi_iste(request)
    bu_sid = servis.istek_sid(request)
    sorgu = select(Oturumlar).where(Oturumlar.email == eposta, servis.etkin_kosulu())
    if bu_sid:
        sorgu = sorgu.where(Oturumlar.sid != bu_sid)
    satirlar = (await db.execute(sorgu)).scalars().all()
    sayi = await servis.iptal_et(db, satirlar, iptal_eden=eposta, request=request)
    return {"kapatilan": sayi}


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("", response_model=OturumListesi)
async def oturum_listesi(
    request: Request,
    email: Optional[str] = Query(None),
    yalniz_etkin: bool = Query(True),
    sayfa: int = Query(1, ge=1),
    adet: int = Query(50, ge=1, le=EN_COK_ADET),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    bu_sid = servis.istek_sid(request)
    kosullar = []
    arama = (email or "").strip().lower()
    if arama:
        kosullar.append(Oturumlar.email.contains(arama))
    if yalniz_etkin:
        kosullar.append(servis.etkin_kosulu())
    toplam = (await db.execute(select(func.count(Oturumlar.id)).where(*kosullar))).scalar() or 0
    satirlar = (
        await db.execute(
            select(Oturumlar)
            .where(*kosullar)
            .order_by(Oturumlar.son_gorulme.desc(), Oturumlar.id.desc())
            .offset((sayfa - 1) * adet)
            .limit(adet)
        )
    ).scalars().all()
    return OturumListesi(
        items=[_yonetici_satiri(s, bu_sid) for s in satirlar], toplam=int(toplam), sayfa=sayfa, adet=adet
    )


@yonetici_router.delete("/{oturum_id}")
async def oturumu_kapat(oturum_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    satir = (await db.execute(select(Oturumlar).where(Oturumlar.id == oturum_id))).scalar_one_or_none()
    if satir is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Oturum bulunamadı")
    bu_sid = servis.istek_sid(request)
    if bu_sid and satir.sid == bu_sid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "kod": "kendi_oturumun",
                "mesaj": "Şu an kullandığınız oturumu buradan kapatamazsınız; bunun için çıkış yapın.",
            },
        )
    sayi = await servis.iptal_et(db, [satir], iptal_eden=yonetici, request=request)
    return {"kapatilan": sayi}


@yonetici_router.post("/kullanici-cikis")
async def kullaniciyi_cikar(
    request: Request, govde: KullaniciCikisGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    """Kullanıcının bütün oturumlarını iptal eder + kesim koyar (sid'siz eski jetonlar da düşer)."""
    yonetici = _yonetici_iste(request)
    eposta = (govde.email or "").strip().lower()
    if "@" not in eposta:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"kod": "eposta_gecersiz"})
    if eposta == yonetici:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "kod": "kendi_hesabin",
                "mesaj": (
                    "Kendi hesabınızı her yerden çıkarmak şu anki oturumunuzu da kapatır. "
                    "Diğer cihazlar için profilinizdeki \"Diğer tüm oturumları kapat\"ı kullanın."
                ),
            },
        )
    satirlar = (
        await db.execute(select(Oturumlar).where(Oturumlar.email == eposta, servis.etkin_kosulu()))
    ).scalars().all()
    sayi = await servis.iptal_et(db, satirlar, iptal_eden=yonetici, request=request)
    an = await servis.kesim_koy(db, eposta, iptal_eden=yonetici, request=request)
    return {"kapatilan": sayi, "gecersiz_once": an}


router = (kisi_router, yonetici_router)
