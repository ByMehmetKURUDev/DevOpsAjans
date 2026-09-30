"""Yenileme yöneticisi (Faz 2A): yaklaşan yenilemeler + tek tıkla yenileme faturası.

GET  /api/v1/yenilemeler?gun=90     alan adı, hosting, (elle yenilenen) SSL ve
                                     aktif abonelikler tek listede, bitişe göre
POST /api/v1/yenilemeler/fatura     fatura + `/ode/<jeton>` ödeme bağlantısı +
                                     müşteriye `yenileme_faturasi` bildirimi

Fatura ve ödeme bağlantısı mevcut akışla aynı biçimde açılıyor (`invoices`
+ `payments` bekliyor satırı, jeton): müşteri aynı `/ode/<jeton>` sayfasında
öder, tahsilat mevcut webhook/elle tahsilat yolundan faturayı kapatır.
Aynı kalem ve aynı dönem için ödenmemiş bir yenileme faturası varsa ikinci
fatura açılmıyor; var olan döndürülüyor (çift tıklama güvenli).
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from models.client_sites import Client_sites
from models.invoices import Invoices
from models.payments import Payments
from models.service_subscriptions import Service_subscriptions
from models.site_izleme import YenilemeFaturasi
from pydantic import BaseModel
from services import site_izleme as si
from services.moduller import toplu_durumlar
from services.musteri_sitesi import site_adresi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/yenilemeler", tags=["yenilemeler"])

TURLER = ("alan", "ssl", "hosting", "abonelik")
PARA_BIRIMLERI = ("TRY", "USD", "EUR")
EN_COK_GUN = 400
GECMIS_GUN = 30


class FaturaGirdisi(BaseModel):
    tur: str
    ref_id: int
    tutar: float
    para_birimi: Optional[str] = "TRY"
    aciklama: Optional[str] = None
    #: YYYY-MM-DD; boşsa yenilenen kalemin bitişi (en geç o gün ödensin).
    son_odeme: Optional[str] = None
    eposta_gonder: Optional[bool] = True


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
    return (getattr(kullanici, "email", "") or "").strip().lower()


def _hata(kod: int, anahtar: str) -> HTTPException:
    return HTTPException(status_code=kod, detail={"kod": anahtar})


def _fatura_no() -> str:
    return f"YEN-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:5].upper()}"


async def _faturalar(db: AsyncSession) -> Dict[tuple, Dict[str, Any]]:
    """(tur, ref_id, bitis) → en son yenileme faturası + ödeme bağlantısı."""
    baglar = list((await db.execute(select(YenilemeFaturasi).order_by(YenilemeFaturasi.id))).scalars().all())
    if not baglar:
        return {}
    faturalar = {
        f.id: f
        for f in (await db.execute(select(Invoices).where(Invoices.id.in_({b.invoice_id for b in baglar})))).scalars().all()
    }
    odemeler = {
        p.id: p
        for p in (
            await db.execute(select(Payments).where(Payments.id.in_({b.payment_id for b in baglar if b.payment_id})))
        ).scalars().all()
    }
    sonuc: Dict[tuple, Dict[str, Any]] = {}
    for b in baglar:
        f = faturalar.get(b.invoice_id)
        if f is None:
            continue
        p = odemeler.get(b.payment_id) if b.payment_id else None
        sonuc[(b.tur, b.ref_id, b.bitis)] = {
            "invoice_id": f.id,
            "invoice_no": f.invoice_no,
            "status": f.status,
            "tutar": f.amount,
            "para_birimi": f.currency,
            "odeme_adresi": f"/ode/{p.jeton}" if p is not None and p.jeton and p.durum == "bekliyor" else None,
        }
    return sonuc


@router.get("")
async def yenileme_listesi(
    request: Request,
    gun: int = Query(90, ge=1, le=EN_COK_GUN),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    bugun = si.tr_gunu(si.simdi())
    ust = bugun + timedelta(days=gun)
    alt = bugun - timedelta(days=GECMIS_GUN)
    kalemler = [k for k in await si.kalemler(db) if alt <= k.bitis <= ust]
    faturalar = await _faturalar(db)
    mm = await toplu_durumlar(db, [k.client_email for k in kalemler])
    liste: List[Dict[str, Any]] = []
    for k in kalemler:
        m = mm.get(k.client_email)
        d = m.durumlar.get("yenileme") if m else None
        liste.append({
            "tur": k.tur,
            "ref_id": k.ref_id,
            "site_id": k.site_id,
            "abonelik_id": k.abonelik_id,
            "client_email": k.client_email,
            "baslik": k.baslik,
            "bitis": k.bitis.isoformat(),
            "kalan_gun": (k.bitis - bugun).days,
            "saglayici": k.saglayici,
            "tutar": k.tutar,
            "para_birimi": k.para_birimi,
            "periyot": k.periyot,
            "modul_acik": bool(d and d.acik),
            "fatura": faturalar.get((k.tur, k.ref_id, k.bitis.isoformat())),
        })
    return {"gun": gun, "bugun": bugun.isoformat(), "kalemler": liste}


async def _kalem_bul(db: AsyncSession, tur: str, ref_id: int) -> si.Kalem:
    for k in await si.kalemler(db):
        if k.tur == tur and k.ref_id == ref_id:
            return k
    # Bitişi henüz girilmemiş site/abonelik de faturalanabilsin (bitişsiz).
    if tur == "abonelik":
        a = (await db.execute(select(Service_subscriptions).where(Service_subscriptions.id == ref_id))).scalar_one_or_none()
        if a is None:
            raise _hata(404, "kalem_yok")
        return si.Kalem("abonelik", a.id, (a.client_email or "").strip().lower(), a.baslik or a.hizmet,
                        si.tr_gunu(si.simdi()), abonelik_id=a.id, tutar=a.tutar, para_birimi=a.para_birimi,
                        periyot=a.periyot)
    site = (await db.execute(select(Client_sites).where(Client_sites.id == ref_id))).scalar_one_or_none()
    if site is None:
        raise _hata(404, "kalem_yok")
    return si.Kalem(tur, site.id, (site.client_email or "").strip().lower(), site.ad, si.tr_gunu(si.simdi()),
                    site_id=site.id)


@router.post("/fatura")
async def yenileme_faturasi_kes(
    request: Request, govde: FaturaGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    _yonetici_iste(request)
    tur = (govde.tur or "").strip().lower()
    if tur not in TURLER:
        raise _hata(400, "tur_gecersiz")
    try:
        tutar = round(float(govde.tutar), 2)
    except (TypeError, ValueError) as exc:
        raise _hata(400, "tutar_gecersiz") from exc
    if not 0 < tutar <= 1_000_000:
        raise _hata(400, "tutar_gecersiz")
    para = (govde.para_birimi or "TRY").strip().upper()
    if para not in PARA_BIRIMLERI:
        raise _hata(400, "para_birimi_gecersiz")

    kalem = await _kalem_bul(db, tur, govde.ref_id)
    if "@" not in kalem.client_email:
        raise _hata(409, "musteri_epostasi_yok")
    bitis = kalem.bitis.isoformat()

    # Aynı kalem + dönem için ödenmemiş fatura varsa onu döndür.
    onceki = (await _faturalar(db)).get((tur, kalem.ref_id, bitis))
    if onceki and onceki.get("status") not in ("paid", "cancelled", "iptal") and onceki.get("odeme_adresi"):
        return {**onceki, "mevcut": True, "adres": onceki["odeme_adresi"]}

    son_odeme = (govde.son_odeme or "").strip()[:10] or bitis
    tr_ad, en_ad = si.TUR_ADLARI[tur]
    aciklama = (govde.aciklama or "").strip()[:300] or f"{tr_ad} yenileme — {kalem.baslik} ({kalem.bitis:%d.%m.%Y})"

    fatura = Invoices(
        invoice_no=_fatura_no(),
        client_email=kalem.client_email,
        description=aciklama,
        amount=tutar,
        currency=para,
        status="pending",
        issue_date=datetime.now().strftime("%Y-%m-%d"),
        due_date=son_odeme,
    )
    db.add(fatura)
    await db.flush()
    odeme = Payments(
        invoice_id=fatura.id,
        invoice_no=fatura.invoice_no,
        client_email=fatura.client_email,
        jeton=secrets.token_urlsafe(9),
        tutar=fatura.amount,
        para_birimi=para,
        durum="bekliyor",
    )
    db.add(odeme)
    await db.flush()
    db.add(YenilemeFaturasi(
        tur=tur, ref_id=kalem.ref_id, bitis=bitis, client_email=kalem.client_email,
        invoice_id=fatura.id, payment_id=odeme.id,
    ))
    await db.commit()
    await db.refresh(fatura)
    await db.refresh(odeme)

    adres = f"/ode/{odeme.jeton}"
    if govde.eposta_gonder is not False:
        await _bildir(db, kalem, fatura, adres)
    return {
        "invoice_id": fatura.id,
        "invoice_no": fatura.invoice_no,
        "status": fatura.status,
        "tutar": fatura.amount,
        "para_birimi": fatura.currency,
        "odeme_adresi": adres,
        "adres": adres,
        "mevcut": False,
    }


async def _bildir(db: AsyncSession, kalem: si.Kalem, fatura: Invoices, adres: str) -> None:
    try:
        from services.notify import dispatch, render

        tam = f"{site_adresi()}{adres}"
        tr_ad, en_ad = si.TUR_ADLARI[kalem.tur]
        tutar = f"{fatura.amount:,.2f} {fatura.currency}"
        baslik, govde = await render(
            db,
            "yenileme_faturasi",
            f"Yenileme faturası: {kalem.baslik} / Renewal invoice: {kalem.baslik}",
            (
                f"{kalem.baslik} için {tr_ad.lower()} yenileme faturanız hazır: {fatura.invoice_no}, {tutar}. "
                f"Son ödeme: {fatura.due_date}. Güvenli ödeme bağlantısı: {tam}\n\n"
                f"Your {en_ad.lower()} renewal invoice for {kalem.baslik} is ready: {fatura.invoice_no}, {tutar}. "
                f"Due: {fatura.due_date}. Secure payment link: {tam}"
            ),
            {"kalem": kalem.baslik, "fatura_no": fatura.invoice_no, "tutar": tutar, "odeme": tam},
        )
        await dispatch(
            db,
            event_type="yenileme_faturasi",
            title=baslik,
            body=govde,
            recipients=[{"email": kalem.client_email, "role": "client"}],
            link=adres,
            ref_type="invoice",
            ref_id=fatura.id,
        )
    except Exception:  # noqa: BLE001 - fatura kesildi; bildirim sonra yeniden gönderilebilir
        logger.exception("Yenileme faturası bildirimi gönderilemedi")
