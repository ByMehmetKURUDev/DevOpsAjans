"""Ödeme bağlantısı üretir, tahsilatı kaydeder.

Akış
----
Panelde fatura var. "Ödeme bağlantısı üret" denince burada bir
`payments` satırı açılıyor (durum `bekliyor`) ve satıra rastgele bir
jeton yazılıyor. Müşteriye giden adres `mehmetkuru.dev/ode/<jeton>`.

Müşteri o adresi açınca `GET /api/v1/odeme/<jeton>` çağrılıyor ve
yalnızca ödemek için gereken alanlar dönüyor: tutar, para birimi,
açıklama, fatura numarası, son tarih. Müşteri adı ve e-postası
dönmüyor — bağlantı elden ele gidebilir, kimin faturası olduğu
bilgisi bağlantıyı açan herkese gösterilmemeli.

Sağlayıcı henüz yok
-------------------
Bu ilk adımda kart tahsilatı bağlı değil. `POST .../webhook/<saglayici>`
ucu duruyor ama sağlayıcı ayarlanmadan **hiçbir faturayı ödendi
işaretlemiyor**: imzası doğrulanamayan bir çağrının faturayı kapatması,
adresi bilen herkesin borcu silebilmesi demek olurdu.

Elden/havale tahsilatı bugünden çalışıyor: yönetici `POST
/api/v1/odeme/elle` ile "şu fatura şu kadar, havaleyle geldi"
diyebiliyor. Kayıt aynı tabloya düşüyor, rapor aynı yerden çıkıyor.
"""

import json
import logging
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.entity_guard import entity_guard
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from models.invoices import Invoices
from models.payments import Payments
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Sağlayıcıyı ayarlayana kadar açık olan tek tahsilat yolu.
ELLE_KANALLAR = {"elden", "havale", "eft", "diger"}

DURUMLAR = {"bekliyor", "odendi", "basarisiz", "iade", "iptal"}


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class BaglantiIstegi(BaseModel):
    invoice_id: int


class BaglantiYaniti(BaseModel):
    jeton: str
    adres: str
    payment_id: int


class AcikOdemeYaniti(BaseModel):
    """Müşterinin ödeme sayfasında gördüğü alanlar. Kişisel bilgi yok."""

    jeton: str
    invoice_no: Optional[str] = None
    aciklama: Optional[str] = None
    tutar: Optional[float] = None
    para_birimi: Optional[str] = None
    son_tarih: Optional[str] = None
    durum: Optional[str] = None
    saglayici_hazir: bool = False


class ElleTahsilat(BaseModel):
    invoice_id: int
    tutar: Optional[float] = None
    kanal: str = "havale"
    not_: Optional[str] = None


class OdemeSatiri(BaseModel):
    id: int
    invoice_id: Optional[int] = None
    invoice_no: Optional[str] = None
    client_email: Optional[str] = None
    jeton: Optional[str] = None
    saglayici: Optional[str] = None
    saglayici_ref: Optional[str] = None
    tutar: Optional[float] = None
    para_birimi: Optional[str] = None
    komisyon: Optional[float] = None
    durum: Optional[str] = None
    hata_mesaji: Optional[str] = None
    odendi_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OdemeListesi(BaseModel):
    items: List[OdemeSatiri]
    ozet: Dict[str, Any]


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _yeni_jeton() -> str:
    """Tahmin edilemez, kısa, adres çubuğunda okunabilir."""
    return secrets.token_urlsafe(9)


def _saglayici_hazir_mi() -> bool:
    """Kart tahsilatı için anahtarlar tanımlı mı?

    Anahtarlar ortam değişkeninde duruyor, veritabanında değil. Henüz
    hiçbiri tanımlı değilse müşteriye "kartla öde" gösterilmiyor.
    """
    import os

    return any(
        os.getenv(ad)
        for ad in ("SHOPIER_API_KEY", "IYZICO_API_KEY", "PAYTR_MERCHANT_ID")
    )


async def _fatura_getir(db: AsyncSession, invoice_id: int) -> Invoices:
    sonuc = await db.execute(select(Invoices).where(Invoices.id == invoice_id))
    fatura = sonuc.scalar_one_or_none()
    if fatura is None:
        raise HTTPException(status_code=404, detail="Fatura bulunamadı")
    return fatura


def _yonetici_iste(request: Request) -> None:
    _, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem yönetici yetkisi istiyor",
        )


# --------------------------------------------------------------------------
# Yönetici uçları
# --------------------------------------------------------------------------
yonetici_router = APIRouter(
    prefix="/api/v1/odeme",
    tags=["odeme"],
    dependencies=[_Depends(entity_guard)],
)


@yonetici_router.post("/baglanti", response_model=BaglantiYaniti)
async def baglanti_uret(
    request: Request,
    govde: BaglantiIstegi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    """Faturaya ödeme bağlantısı açar.

    Aynı fatura için bekleyen bir bağlantı varsa yenisi üretilmiyor;
    var olan dönüyor. Yoksa müşteriye iki farklı adres gidebilir ve
    hangisinin ödendiği karışır.
    """
    _yonetici_iste(request)
    fatura = await _fatura_getir(db, govde.invoice_id)

    mevcut = await db.execute(
        select(Payments)
        .where(Payments.invoice_id == fatura.id)
        .where(Payments.durum == "bekliyor")
        .order_by(Payments.id.desc())
    )
    kayit = mevcut.scalars().first()

    if kayit is None:
        kayit = Payments(
            invoice_id=fatura.id,
            invoice_no=fatura.invoice_no,
            client_email=fatura.client_email,
            jeton=_yeni_jeton(),
            tutar=fatura.amount,
            para_birimi=fatura.currency or "TRY",
            durum="bekliyor",
        )
        db.add(kayit)
        await db.commit()
        await db.refresh(kayit)

    return BaglantiYaniti(
        jeton=kayit.jeton,
        adres=f"/ode/{kayit.jeton}",
        payment_id=kayit.id,
    )


@yonetici_router.post("/elle", response_model=OdemeSatiri)
async def elle_tahsilat(
    request: Request,
    govde: ElleTahsilat = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    """Elden, havale ya da EFT ile gelen tahsilatı kaydeder."""
    _yonetici_iste(request)

    kanal = (govde.kanal or "havale").strip().lower()
    if kanal not in ELLE_KANALLAR:
        raise HTTPException(
            status_code=400,
            detail=f"Kanal şunlardan biri olmalı: {', '.join(sorted(ELLE_KANALLAR))}",
        )

    fatura = await _fatura_getir(db, govde.invoice_id)
    tutar = govde.tutar if govde.tutar is not None else fatura.amount

    kayit = Payments(
        invoice_id=fatura.id,
        invoice_no=fatura.invoice_no,
        client_email=fatura.client_email,
        saglayici=kanal,
        tutar=tutar,
        para_birimi=fatura.currency or "TRY",
        durum="odendi",
        hata_mesaji=None,
        ham_yanit=json.dumps({"not": govde.not_}, ensure_ascii=False) if govde.not_ else None,
        odendi_at=datetime.now(),
    )
    db.add(kayit)

    # Tamamı tahsil edildiyse fatura kapanıyor ve bekleyen ödeme
    # bağlantısı iptal ediliyor. Yoksa iki şey bozuluyor: özet aynı
    # parayı hem "tahsil edildi" hem "bekliyor" sayıyor, ve müşteriye
    # gönderilmiş bağlantı ödenmiş bir faturayı istemeye devam ediyor.
    if fatura.amount is not None and tutar is not None and tutar + 0.001 >= fatura.amount:
        fatura.status = "paid"
        bekleyenler = await db.execute(
            select(Payments)
            .where(Payments.invoice_id == fatura.id)
            .where(Payments.durum == "bekliyor")
        )
        for eski in bekleyenler.scalars().all():
            eski.durum = "iptal"
            eski.hata_mesaji = f"{kanal} ile tahsil edildi"

    await db.commit()
    await db.refresh(kayit)
    return kayit


@yonetici_router.get("", response_model=OdemeListesi)
async def odeme_listesi(
    request: Request,
    db: AsyncSession = _Depends(get_db),
):
    """Tahsilat listesi ve panel özeti."""
    _yonetici_iste(request)

    sonuc = await db.execute(select(Payments).order_by(Payments.id.desc()).limit(200))
    satirlar = list(sonuc.scalars().all())

    tahsil = sum(s.tutar or 0 for s in satirlar if s.durum == "odendi")
    bekleyen = sum(s.tutar or 0 for s in satirlar if s.durum == "bekliyor")
    komisyon = sum(s.komisyon or 0 for s in satirlar if s.durum == "odendi")

    ozet = {
        "tahsil_edilen": round(tahsil, 2),
        "bekleyen": round(bekleyen, 2),
        "komisyon": round(komisyon, 2),
        "adet": len(satirlar),
        "saglayici_hazir": _saglayici_hazir_mi(),
    }
    return OdemeListesi(items=satirlar, ozet=ozet)


# --------------------------------------------------------------------------
# Açık uçlar — müşterinin ödeme sayfası ve sağlayıcı geri bildirimi
# --------------------------------------------------------------------------
acik_router = APIRouter(prefix="/api/v1/odeme", tags=["odeme"])


@acik_router.get("/{jeton}", response_model=AcikOdemeYaniti)
async def odeme_ozeti(jeton: str, db: AsyncSession = _Depends(get_db)):
    """Ödeme sayfasının gösterdiği özet. Kişisel bilgi dönmüyor."""
    sonuc = await db.execute(select(Payments).where(Payments.jeton == jeton))
    kayit = sonuc.scalar_one_or_none()
    if kayit is None:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")

    son_tarih = None
    if kayit.invoice_id:
        fatura = await db.execute(select(Invoices).where(Invoices.id == kayit.invoice_id))
        fatura = fatura.scalar_one_or_none()
        if fatura is not None:
            son_tarih = fatura.due_date
            aciklama = fatura.description
        else:
            aciklama = None
    else:
        aciklama = None

    return AcikOdemeYaniti(
        jeton=kayit.jeton,
        invoice_no=kayit.invoice_no,
        aciklama=aciklama,
        tutar=kayit.tutar,
        para_birimi=kayit.para_birimi,
        son_tarih=son_tarih,
        durum=kayit.durum,
        saglayici_hazir=_saglayici_hazir_mi(),
    )


@acik_router.post("/webhook/{saglayici}")
async def saglayici_bildirimi(saglayici: str, request: Request):
    """Sağlayıcının ödeme sonucu bildirimi.

    Şu an hiçbir sağlayıcı bağlı değil. Uç, imzayı doğrulayan kod
    yazılana kadar **hiçbir kaydı değiştirmiyor** — doğrulanmamış bir
    çağrının faturayı ödendi işaretlemesi, adresi bilen herkesin borcu
    silebilmesi demek olurdu.

    Gelen gövde yine de kayda geçiyor: entegrasyonu yazarken
    sağlayıcının gerçekte ne gönderdiğini görmek gerekiyor.
    """
    try:
        govde = await request.body()
        logger.info(
            "Odeme bildirimi alindi ama islenmedi (saglayici=%s, %d bayt)",
            saglayici,
            len(govde or b""),
        )
    except Exception:  # pragma: no cover - gövde okunamazsa da uç ayakta kalsın
        logger.warning("Odeme bildiriminin govdesi okunamadi (saglayici=%s)", saglayici)

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Ödeme sağlayıcısı henüz kurulmadı",
    )


# `include_routers_from_package` liste de kabul ediyor: biri yönetici
# bekçisinin arkasında, diğeri müşteriye açık.
router = (yonetici_router, acik_router)
