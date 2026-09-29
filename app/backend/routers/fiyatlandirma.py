"""Fiyatlandırma v5 — herkese açık, entity_guard'a bağlı olmayan iki uç:

`GET /api/v1/fiyat-hesapla`  — tek doğru kaynak: her paket kartı, her
    eklenti fiyatı, her "à la carte" gösterim bu uçtan geçer.
`POST /api/v1/fiyat-teklif`  — "Teklif Al": pricing_inquiries kaydı +
    gerçek invoices kaydı oluşturur, ikisini invoice_id ile bağlar.

Bu router `dependencies=[Depends(entity_guard)]` KULLANMIYOR — bilerek:
ziyaretçi giriş yapmadan fiyat görebilmeli ve teklif bırakabilmeli
(tıpkı `inquiries` tablosunun `HERKESE_ACIK_OLUSTURMA`'da olması gibi,
ama burada ayrı bir kayıt + otomatik fatura oluşuyor, bu yüzden
entity_guard'ın genel CRUD'undan değil, kendi uç noktasından geçiyor).
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.fiyat_hesaplama import FiyatHesaplamaHatasi, hesapla
from models.invoices import Invoices
from models.pricing import Ai_pm_tiers, Pricing_addons, Pricing_inquiries, Pricing_profiles, Pricing_scales
from services.pricing_generic import GenericEntityService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["fiyatlandirma"])


async def _fiyat_verilerini_yukle(db: AsyncSession, scale_kod: str):
    scales = (await db.execute(select(Pricing_scales))).scalars().all()
    profiles = (await db.execute(select(Pricing_profiles))).scalars().all()
    addons = (
        await db.execute(select(Pricing_addons).where(Pricing_addons.scale_kod == scale_kod))
    ).scalars().all()

    scale_baz_fiyatlari = {s.kod: float(s.baz_aylik_fiyat_usd) for s in scales}
    profile_carpanlari = {p.kod: float(p.carpan) for p in profiles}
    # Eklenti kimliği olarak `ad` kullanılıyor (bu tablonun doğal anahtarı
    # yok; ölçek+ad kombinasyonu benzersiz kabul ediliyor).
    addon_fiyatlari = {a.ad: float(a.baz_fiyat_usd) for a in addons}
    return scale_baz_fiyatlari, profile_carpanlari, addon_fiyatlari


@router.get("/fiyat-hesapla")
async def fiyat_hesapla(
    scale: str = Query(...),
    profile: str = Query(...),
    period: str = Query(...),
    addons: str = Query(default="", description="Virgülle ayrılmış eklenti adları"),
    db: AsyncSession = Depends(get_db),
):
    addon_kodlari = [a for a in addons.split(",") if a]
    scale_baz_fiyatlari, profile_carpanlari, addon_fiyatlari = await _fiyat_verilerini_yukle(db, scale)

    try:
        sonuc = hesapla(
            scale_kod=scale, profile_kod=profile, period=period, addon_kodlari=addon_kodlari,
            scale_baz_fiyatlari=scale_baz_fiyatlari, profile_carpanlari=profile_carpanlari,
            addon_fiyatlari=addon_fiyatlari,
        )
    except FiyatHesaplamaHatasi as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "paket_fiyat": sonuc.paket_fiyat,
        "eklentiler_toplami": sonuc.eklentiler_toplami,
        "toplam": sonuc.toplam,
        "para_birimi": sonuc.para_birimi,
        "formul_notu": sonuc.formul_notu,
        "eklenti_detay": sonuc.eklenti_detay,
    }


class FiyatTeklifRequest(BaseModel):
    # Paket teklifi: scale + profile birlikte gelir.
    scale: Optional[str] = None
    profile: Optional[str] = None
    period: Optional[str] = None
    addon_ids: List[str] = []
    # AI vs PM teklifi: bunun yerine ai_pm_tier_kod gelir (scale/profile/period boş kalır).
    ai_pm_tier_kod: Optional[str] = None
    musteri_eposta: EmailStr
    musteri_adi: Optional[str] = None


def _fatura_no_uret() -> str:
    return f"FIY-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:4].upper()}"


@router.post("/fiyat-teklif")
async def fiyat_teklif(req: FiyatTeklifRequest, db: AsyncSession = Depends(get_db)):
    if not req.ai_pm_tier_kod and not (req.scale and req.profile and req.period):
        raise HTTPException(
            status_code=400,
            detail="Ya (scale, profile, period) ya da ai_pm_tier_kod gönderilmeli",
        )

    # --- Aynı e-posta / aynı seçim son 60 saniyede tekrar geldiyse reddet ---
    # (çift tıklama / ağ tekrar denemesi ile iki kez fatura oluşmasın)
    esik = datetime.now(timezone.utc) - timedelta(seconds=60)
    mevcut_sorgu = select(Pricing_inquiries).where(
        Pricing_inquiries.musteri_eposta == req.musteri_eposta,
        Pricing_inquiries.created_at >= esik,
    )
    if req.ai_pm_tier_kod:
        mevcut_sorgu = mevcut_sorgu.where(Pricing_inquiries.ai_pm_tier_kod == req.ai_pm_tier_kod)
    else:
        mevcut_sorgu = mevcut_sorgu.where(
            Pricing_inquiries.scale_kod == req.scale,
            Pricing_inquiries.profile_kod == req.profile,
            Pricing_inquiries.period == req.period,
        )
    mevcut = (await db.execute(mevcut_sorgu)).scalars().first()
    if mevcut:
        raise HTTPException(status_code=409, detail="Bu teklif az önce zaten gönderildi.")

    aciklama_kaynak = None
    if req.ai_pm_tier_kod:
        tier = (
            await db.execute(select(Ai_pm_tiers).where(Ai_pm_tiers.kod == req.ai_pm_tier_kod))
        ).scalars().first()
        if not tier:
            raise HTTPException(status_code=400, detail=f"Bilinmeyen AI vs PM paketi: {req.ai_pm_tier_kod}")
        toplam = float(tier.fiyat_aylik_usd)
        aciklama_kaynak = f"AI vs PM / {tier.ad} — mehmetkuru.dev Fiyatlandırma v5"
    else:
        scale_baz_fiyatlari, profile_carpanlari, addon_fiyatlari = await _fiyat_verilerini_yukle(db, req.scale)
        try:
            sonuc = hesapla(
                scale_kod=req.scale, profile_kod=req.profile, period=req.period,
                addon_kodlari=req.addon_ids, scale_baz_fiyatlari=scale_baz_fiyatlari,
                profile_carpanlari=profile_carpanlari, addon_fiyatlari=addon_fiyatlari,
            )
        except FiyatHesaplamaHatasi as e:
            raise HTTPException(status_code=400, detail=str(e))
        toplam = sonuc.toplam
        aciklama_kaynak = f"{req.scale} / {req.profile} / {req.period} — mehmetkuru.dev Fiyatlandırma v5"

    # --- Fatura oluştur ---
    invoice_service = GenericEntityService(Invoices, db)
    invoice = await invoice_service.create({
        "invoice_no": _fatura_no_uret(),
        "client_name": req.musteri_adi,
        "client_email": req.musteri_eposta,
        "description": aciklama_kaynak,
        "amount": toplam,
        "currency": "USD",
        "status": "pending",
        "issue_date": datetime.now().strftime("%Y-%m-%d"),
    })

    # --- pricing_inquiries kaydı ---
    inquiry_service = GenericEntityService(Pricing_inquiries, db)
    inquiry = await inquiry_service.create({
        "scale_kod": req.scale,
        "profile_kod": req.profile,
        "ai_pm_tier_kod": req.ai_pm_tier_kod,
        "period": req.period,
        "addon_ids": json.dumps(req.addon_ids, ensure_ascii=False),
        "hesaplanan_tutar": toplam,
        "musteri_eposta": req.musteri_eposta,
        "musteri_adi": req.musteri_adi,
        "kaynak": "website",
        "invoice_id": invoice.id,
    })

    logger.info(f"Fiyat teklifi oluşturuldu: inquiry={inquiry.id} invoice={invoice.id} tutar={toplam}")
    return {"inquiry_id": inquiry.id, "invoice_id": invoice.id, "toplam": toplam}
