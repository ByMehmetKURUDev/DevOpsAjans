"""Kredi defteri uçları (Kullandıkça Öde).

Kim ne görüyor
--------------
* Yönetici (`/api/v1/kredi/yonetim`): bütün müşterilerin bakiyesi,
  bir müşterinin hareketleri; saat harcama, kredi ekleme (hediye, iade,
  düzeltme, elle satın alma) ve süre dolumlarını toplu işleme.
* Müşteri (`/api/v1/kredilerim`): yalnız kendi bakiyesi, yaklaşan son
  kullanmalar ve hareketleri. E-posta jetondan alınıyor, sorgudan değil.

Ödeme ile gelen krediler burada değil, `routers/odemeler.py` içindeki
tahsilat işleyicilerinden `services/kredi.odeme_kredilerini_yukle` ile
yazılıyor. Her yazım denetim kaydına kendiliğinden düşüyor (1B).
"""

import logging
from datetime import datetime
from typing import List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, musteri_eposta
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from models.credit_ledger import CreditLedger
from pydantic import BaseModel
from services import kredi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/kredi/yonetim", tags=["kredi"])
# Faz 1F: müşterinin bu modülü kapalıysa 403 `modul_kapali` (yönetici etkilenmez).
# Faz 2E: ekip üyesinde `krediler` izni (hesap_baglami.izin_gerekli).
musteri_router = APIRouter(
    prefix="/api/v1/kredilerim",
    tags=["kredi"],
    dependencies=[_Depends(izin_gerekli("krediler")), _Depends(modul_gerekli("krediler"))],
)


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class HareketSatiri(BaseModel):
    id: int
    created_at: Optional[datetime] = None
    miktar: float
    tur: str
    aciklama: Optional[str] = None
    fatura_id: Optional[int] = None
    proje_id: Optional[int] = None
    son_kullanma: Optional[datetime] = None
    olusturan_eposta: Optional[str] = None


class MusteriHareketi(BaseModel):
    """Müşteriye dönen satır: kimin yazdığı ve iç referanslar yok."""

    id: int
    created_at: Optional[datetime] = None
    miktar: float
    tur: str
    aciklama: Optional[str] = None
    son_kullanma: Optional[datetime] = None


class SonKullanma(BaseModel):
    miktar: float
    tarih: datetime


class MusteriOzeti(BaseModel):
    eposta: str
    bakiye: float
    borc: float = 0.0
    hareket_sayisi: int
    son_hareket: Optional[datetime] = None
    son_hareket_turu: Optional[str] = None
    en_yakin_son_kullanma: Optional[datetime] = None
    en_yakin_miktar: Optional[float] = None
    #: Süresi geçmiş ama dolum satırı henüz yazılmamış kalan.
    dolum_bekleyen: float = 0.0


class MusteriAyrintisi(BaseModel):
    eposta: str
    bakiye: float
    borc: float = 0.0
    yaklasan_son_kullanma: List[SonKullanma]
    hareketler: List[HareketSatiri]


class Kredilerim(BaseModel):
    bakiye: float
    yaklasan_son_kullanma: List[SonKullanma]
    hareketler: List[MusteriHareketi]


class HarcaGirdisi(BaseModel):
    eposta: str
    saat: float
    aciklama: str
    proje_id: Optional[int] = None
    izin_eksi: bool = False


class YukleGirdisi(BaseModel):
    eposta: str
    saat: float
    tur: str
    aciklama: str
    fatura_id: Optional[int] = None


class IslemYaniti(BaseModel):
    hareket: HareketSatiri
    bakiye: float


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


def _satir(s: CreditLedger) -> HareketSatiri:
    return HareketSatiri(
        id=s.id,
        created_at=kredi._utc(s.created_at),
        miktar=kredi.yuvarla(s.miktar or 0),
        tur=s.tur,
        aciklama=s.aciklama,
        fatura_id=s.fatura_id,
        proje_id=s.proje_id,
        son_kullanma=kredi._utc(s.son_kullanma),
        olusturan_eposta=s.olusturan_eposta,
    )


def _aciklama_iste(metin: Optional[str]) -> str:
    temiz = (metin or "").strip()
    if not temiz:
        raise HTTPException(status_code=400, detail="Açıklama gerekli")
    return temiz[:500]


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("/musteriler", response_model=List[MusteriOzeti])
async def musteriler(request: Request, db: AsyncSession = _Depends(get_db)):
    """Defterde hareketi olan bütün müşteriler, bakiyeleriyle.

    Satırlar tek sorguda çekilip bellekte müşteriye göre gruplanıyor;
    müşteri başına ayrı sorgu yok.
    """
    _yonetici_iste(request)
    sonuc = await db.execute(select(CreditLedger).order_by(CreditLedger.id.asc()))
    gruplar: dict[str, list[CreditLedger]] = {}
    for s in sonuc.scalars().all():
        gruplar.setdefault(s.musteri_eposta, []).append(s)

    simdi = kredi._simdi()
    liste: List[MusteriOzeti] = []
    for eposta, satirlar in gruplar.items():
        d = kredi.durum_hesapla(satirlar, simdi)
        son = max(satirlar, key=lambda x: (kredi._utc(x.created_at) or simdi, x.id))
        ilk = d.aktif[0] if d.aktif else None
        liste.append(
            MusteriOzeti(
                eposta=eposta,
                bakiye=d.bakiye,
                borc=d.borc,
                hareket_sayisi=len(satirlar),
                son_hareket=kredi._utc(son.created_at),
                son_hareket_turu=son.tur,
                en_yakin_son_kullanma=ilk.son_kullanma if ilk else None,
                en_yakin_miktar=kredi.yuvarla(ilk.kalan) if ilk else None,
                dolum_bekleyen=kredi.yuvarla(sum(y.kalan for y in d.dolmus)),
            )
        )
    liste.sort(key=lambda m: (m.son_hareket or simdi), reverse=True)
    return liste


@yonetici_router.get("/musteri/{eposta}", response_model=MusteriAyrintisi)
async def musteri_ayrintisi(eposta: str, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    eposta = kredi.eposta_duzelt(eposta)
    d = await kredi.durum(db, eposta)
    satirlar = await kredi.hareketler(db, eposta, limit=500)
    return MusteriAyrintisi(
        eposta=eposta,
        bakiye=d.bakiye,
        borc=d.borc,
        yaklasan_son_kullanma=[SonKullanma(**k) for k in kredi.yaklasan_son_kullanmalar(d)],
        hareketler=[_satir(s) for s in satirlar],
    )


@yonetici_router.post("/harca", response_model=IslemYaniti)
async def harca(request: Request, govde: HarcaGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    satir, yeni = await kredi.harca(
        db,
        eposta=govde.eposta,
        saat=govde.saat,
        aciklama=_aciklama_iste(govde.aciklama),
        proje_id=govde.proje_id,
        izin_eksi=bool(govde.izin_eksi),
        olusturan=yonetici,
    )
    return IslemYaniti(hareket=_satir(satir), bakiye=yeni)


@yonetici_router.post("/yukle", response_model=IslemYaniti)
async def yukle(request: Request, govde: YukleGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    tur = (govde.tur or "").strip().lower()
    if tur not in kredi.YUKLEME_TURLERI:
        raise HTTPException(
            status_code=400,
            detail=f"Tür şunlardan biri olmalı: {', '.join(kredi.YUKLEME_TURLERI)}",
        )
    satir = await kredi.yukle(
        db,
        eposta=govde.eposta,
        saat=govde.saat,
        tur=tur,
        aciklama=_aciklama_iste(govde.aciklama),
        fatura_id=govde.fatura_id,
        olusturan=yonetici,
    )
    return IslemYaniti(hareket=_satir(satir), bakiye=await kredi.bakiye(db, satir.musteri_eposta))


@yonetici_router.post("/sure-dolumlari")
async def sure_dolumlari(request: Request, db: AsyncSession = _Depends(get_db)):
    """Süresi geçmiş bütün yüklemelerin kalanını düşer (istekle tetiklenir)."""
    _yonetici_iste(request)
    return await kredi.sure_dolumlarini_isle(db)


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
@musteri_router.get("", response_model=Kredilerim)
async def kredilerim(request: Request, db: AsyncSession = _Depends(get_db)):
    """Müşterinin kendi kredileri.

    Okurken o müşterinin süresi geçmiş yüklemeleri işleniyor: zamanlanmış
    görev olmadığı için "süresi doldu" satırı müşteri baktığında yazılıyor.
    """
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    if not (kullanici.email or "").strip():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesabınızda e-posta adresi yok")
    eposta = musteri_eposta(request)

    await kredi.sure_dolumlarini_isle(db, eposta)
    d = await kredi.durum(db, eposta)
    satirlar = await kredi.hareketler(db, eposta, limit=200)
    return Kredilerim(
        bakiye=d.bakiye,
        yaklasan_son_kullanma=[SonKullanma(**k) for k in kredi.yaklasan_son_kullanmalar(d)],
        hareketler=[
            MusteriHareketi(
                id=s.id,
                created_at=kredi._utc(s.created_at),
                miktar=kredi.yuvarla(s.miktar or 0),
                tur=s.tur,
                aciklama=s.aciklama,
                son_kullanma=kredi._utc(s.son_kullanma),
            )
            for s in satirlar
        ],
    )


router = (yonetici_router, musteri_router)
