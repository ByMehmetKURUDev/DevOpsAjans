"""Fiyatlandırma v5 — herkese açık, entity_guard'a bağlı olmayan iki uç:

`GET /api/v1/fiyat-hesapla`  — tek doğru kaynak: her paket kartı, her
    eklenti fiyatı, her "à la carte" gösterim bu uçtan geçer.
`POST /api/v1/fiyat-teklif`  — "Teklif Al": pricing_inquiries kaydı +
    gerçek invoices kaydı oluşturur, ikisini invoice_id ile bağlar.
`POST /api/v1/fiyat-satin-al` — "Satın Al" (v6): teklifle aynı kaydı açar,
    üstüne ödeme bağlantısı üretir ve `/ode/<jeton>` adresini döndürür.
    Paket için ilk dönem, kredi bloğu için seçilen kredi paketi.

Bu router `dependencies=[Depends(entity_guard)]` KULLANMIYOR — bilerek:
ziyaretçi giriş yapmadan fiyat görebilmeli ve teklif bırakabilmeli
(tıpkı `inquiries` tablosunun `HERKESE_ACIK_OLUSTURMA`'da olması gibi,
ama burada ayrı bir kayıt + otomatik fatura oluşuyor, bu yüzden
entity_guard'ın genel CRUD'undan değil, kendi uç noktasından geçiyor).
"""

import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.fiyat_hesaplama import FiyatHesaplamaHatasi, hesapla, kredi_paketi
from models.invoices import Invoices
from models.payments import Payments
from models.pricing import Ai_pm_tiers, Pricing_addons, Pricing_inquiries, Pricing_profiles, Pricing_scales
from services.pricing_generic import GenericEntityService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["fiyatlandirma"])

#: Faz 7H — herkese açık "Teklif Al" / "Satın Al" (her biri fatura + talep kaydı açıyor; önceden
#: yalnız 60 sn'lik çift gönderim koruması vardı): IP özeti başına 10 dakikada en çok 10 istek,
#: ikisi ortak. Sayaç veritabanında (sunucu uyanınca sıfırlanmıyor).
from utils.hiz_siniri import KaliciHizSiniri, izin_ver  # noqa: E402
from utils.istemci_ip import ip_ozeti, istemci_ip  # noqa: E402

_fiyat_hizi = KaliciHizSiniri("fiyat-teklif", 10, 600.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    _fiyat_hizi.temizle()


async def _fiyat_hiz_denetle(request: Request) -> None:
    if not await izin_ver((_fiyat_hizi, ip_ozeti(istemci_ip(request)))):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"})


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


async def _ai_pm_getir(db: AsyncSession, kod: str) -> Ai_pm_tiers:
    tier = (await db.execute(select(Ai_pm_tiers).where(Ai_pm_tiers.kod == kod))).scalars().first()
    if not tier:
        raise HTTPException(status_code=400, detail=f"Bilinmeyen AI vs PM paketi: {kod}")
    return tier


@router.get("/fiyat-hesapla")
async def fiyat_hesapla(
    scale: str = Query(...),
    profile: str = Query(...),
    period: str = Query(...),
    addons: str = Query(default="", description="Virgülle ayrılmış eklenti adları"),
    ai_pm: str = Query(default="", description="Karta eklenen AI vs PM paketi (kod), boşsa yok"),
    db: AsyncSession = Depends(get_db),
):
    addon_kodlari = [a for a in addons.split(",") if a]
    scale_baz_fiyatlari, profile_carpanlari, addon_fiyatlari = await _fiyat_verilerini_yukle(db, scale)
    ai_pm_aylik = float((await _ai_pm_getir(db, ai_pm)).fiyat_aylik_usd) if ai_pm else 0.0

    try:
        sonuc = hesapla(
            scale_kod=scale, profile_kod=profile, period=period, addon_kodlari=addon_kodlari,
            scale_baz_fiyatlari=scale_baz_fiyatlari, profile_carpanlari=profile_carpanlari,
            addon_fiyatlari=addon_fiyatlari, ai_pm_aylik=ai_pm_aylik,
        )
    except FiyatHesaplamaHatasi as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "ai_pm_toplami": sonuc.ai_pm_toplami,
        "kredi": sonuc.kredi,
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
    # AI vs PM: tek başına (scale boş) ya da v6'da pakete eklenmiş olarak gelir.
    ai_pm_tier_kod: Optional[str] = None
    # Kullandıkça Öde kredi paketi (10/25/50/100). Doluysa diğer alanlar yok sayılır.
    kredi_paketi: Optional[int] = None
    musteri_eposta: EmailStr
    musteri_adi: Optional[str] = None


def _fatura_no_uret() -> str:
    return f"FIY-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:4].upper()}"


def _secim_tanimi(req: FiyatTeklifRequest) -> str:
    if req.kredi_paketi:
        return "kredi"
    if req.scale and req.profile and req.period:
        return "paket"
    if req.ai_pm_tier_kod:
        return "ai_pm"
    raise HTTPException(
        status_code=400,
        detail="Ya (scale, profile, period), ya ai_pm_tier_kod ya da kredi_paketi gönderilmeli",
    )


async def _son_ayni_kayit(db: AsyncSession, req: FiyatTeklifRequest, tur: str) -> Optional[Pricing_inquiries]:
    """Aynı e-posta + aynı seçim son 60 saniyede geldiyse o kaydı döndürür.

    Çift tıklama ya da ağ tekrarı iki fatura açmasın.
    """
    esik = datetime.now(timezone.utc) - timedelta(seconds=60)
    sorgu = select(Pricing_inquiries).where(
        Pricing_inquiries.musteri_eposta == req.musteri_eposta,
        Pricing_inquiries.created_at >= esik,
    )
    if tur == "kredi":
        sorgu = sorgu.where(
            Pricing_inquiries.period == "kullandikca_ode",
            Pricing_inquiries.addon_ids == json.dumps([f"kredi_paketi:{req.kredi_paketi}"]),
        )
    elif tur == "ai_pm":
        sorgu = sorgu.where(
            Pricing_inquiries.ai_pm_tier_kod == req.ai_pm_tier_kod,
            Pricing_inquiries.scale_kod.is_(None),
        )
    else:
        sorgu = sorgu.where(
            Pricing_inquiries.scale_kod == req.scale,
            Pricing_inquiries.profile_kod == req.profile,
            Pricing_inquiries.period == req.period,
        )
    return (await db.execute(sorgu.order_by(Pricing_inquiries.id.desc()))).scalars().first()


async def _kayit_olustur(db: AsyncSession, req: FiyatTeklifRequest, tur: str, kaynak: str):
    """Tutarı sunucuda hesaplar, fatura + pricing_inquiries kaydını açar."""
    addon_ids = list(req.addon_ids)
    scale_kod, profile_kod, period, ai_pm_kod = req.scale, req.profile, req.period, req.ai_pm_tier_kod

    if tur == "kredi":
        try:
            paket = kredi_paketi(int(req.kredi_paketi))
        except FiyatHesaplamaHatasi as e:
            raise HTTPException(status_code=400, detail=str(e))
        toplam = paket["fiyat"]
        aciklama = f"Kullandıkça Öde — {paket['kredi']} kredi (+{paket['bonus']} bonus, {paket['saat']} saat) — mehmetkuru.dev"
        scale_kod = profile_kod = ai_pm_kod = None
        period = "kullandikca_ode"
        addon_ids = [f"kredi_paketi:{paket['kredi']}"]
    elif tur == "ai_pm":
        tier = await _ai_pm_getir(db, req.ai_pm_tier_kod)
        toplam = float(tier.fiyat_aylik_usd)
        aciklama = f"AI vs PM / {tier.ad} — mehmetkuru.dev Fiyatlandırma v5"
    else:
        scale_baz_fiyatlari, profile_carpanlari, addon_fiyatlari = await _fiyat_verilerini_yukle(db, req.scale)
        ai_pm_aylik = 0.0
        if req.ai_pm_tier_kod:
            ai_pm_aylik = float((await _ai_pm_getir(db, req.ai_pm_tier_kod)).fiyat_aylik_usd)
        try:
            sonuc = hesapla(
                scale_kod=req.scale, profile_kod=req.profile, period=req.period,
                addon_kodlari=req.addon_ids, scale_baz_fiyatlari=scale_baz_fiyatlari,
                profile_carpanlari=profile_carpanlari, addon_fiyatlari=addon_fiyatlari,
                ai_pm_aylik=ai_pm_aylik,
            )
        except FiyatHesaplamaHatasi as e:
            raise HTTPException(status_code=400, detail=str(e))
        toplam = sonuc.toplam
        ek = f" + AI vs PM {req.ai_pm_tier_kod}" if req.ai_pm_tier_kod else ""
        aciklama = f"{req.scale} / {req.profile} / {req.period}{ek} — mehmetkuru.dev Fiyatlandırma v5"

    invoice_service = GenericEntityService(Invoices, db)
    invoice = await invoice_service.create({
        "invoice_no": _fatura_no_uret(),
        "client_name": req.musteri_adi,
        "client_email": req.musteri_eposta,
        "description": aciklama,
        "amount": toplam,
        "currency": "USD",
        "status": "pending",
        "issue_date": datetime.now().strftime("%Y-%m-%d"),
    })

    inquiry_service = GenericEntityService(Pricing_inquiries, db)
    inquiry = await inquiry_service.create({
        "scale_kod": scale_kod,
        "profile_kod": profile_kod,
        "ai_pm_tier_kod": ai_pm_kod,
        "period": period,
        "addon_ids": json.dumps(addon_ids, ensure_ascii=False),
        "hesaplanan_tutar": toplam,
        "musteri_eposta": req.musteri_eposta,
        "musteri_adi": req.musteri_adi,
        "kaynak": kaynak,
        "invoice_id": invoice.id,
    })
    logger.info(f"Fiyat kaydı oluşturuldu ({kaynak}): inquiry={inquiry.id} invoice={invoice.id} tutar={toplam}")
    return invoice, inquiry, toplam


@router.post("/fiyat-teklif")
async def fiyat_teklif(req: FiyatTeklifRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await _fiyat_hiz_denetle(request)
    tur = _secim_tanimi(req)
    if await _son_ayni_kayit(db, req, tur):
        raise HTTPException(status_code=409, detail="Bu teklif az önce zaten gönderildi.")
    invoice, inquiry, toplam = await _kayit_olustur(db, req, tur, "website")
    return {"inquiry_id": inquiry.id, "invoice_id": invoice.id, "toplam": toplam}


async def _bekleyen_odeme(db: AsyncSession, invoice: Invoices) -> Payments:
    """Faturanın bekleyen ödeme kaydı; yoksa açar (panelde üretilenle aynı biçim)."""
    mevcut = (
        await db.execute(
            select(Payments)
            .where(Payments.invoice_id == invoice.id)
            .where(Payments.durum == "bekliyor")
            .order_by(Payments.id.desc())
        )
    ).scalars().first()
    if mevcut:
        return mevcut
    kayit = Payments(
        invoice_id=invoice.id,
        invoice_no=invoice.invoice_no,
        client_email=invoice.client_email,
        jeton=secrets.token_urlsafe(9),
        tutar=invoice.amount,
        para_birimi=invoice.currency or "USD",
        durum="bekliyor",
    )
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)
    return kayit


@router.post("/fiyat-satin-al")
async def fiyat_satin_al(req: FiyatTeklifRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Satın Al: kaydı açar, ödeme sayfasının adresini döndürür.

    Aynı seçim 60 saniye içinde tekrar gelirse yeni fatura açılmaz; önceki
    faturanın bekleyen ödeme bağlantısı döner (çift tıklama güvenli).
    """
    await _fiyat_hiz_denetle(request)
    tur = _secim_tanimi(req)
    onceki = await _son_ayni_kayit(db, req, tur)
    if onceki and onceki.invoice_id:
        invoice = (await db.execute(select(Invoices).where(Invoices.id == onceki.invoice_id))).scalars().first()
        toplam = onceki.hesaplanan_tutar
    else:
        invoice, _inquiry, toplam = await _kayit_olustur(db, req, tur, "website_satin_al")
    if invoice is None:
        raise HTTPException(status_code=500, detail="Fatura bulunamadı")
    odeme = await _bekleyen_odeme(db, invoice)
    return {"adres": f"/ode/{odeme.jeton}", "invoice_id": invoice.id, "toplam": toplam}
