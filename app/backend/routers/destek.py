"""Faz 2C — Destek: SLA durumları/ayarları ve hazır cevaplar.

Yönetici  GET  /api/v1/destek/sla?ids=1,2      talep başına SLA durumu (rozet)
          GET/PUT /api/v1/destek/sla-ayarlari   mesai, tatiller, öncelik hedefleri
          GET/POST /api/v1/destek/hazir-cevaplar, PUT/DELETE /{id}
          POST /api/v1/destek/hazir-cevaplar/{id}/uygula {ticket_id}
                → değişkenleri ({musteri_adi}, {talep_no}, {konu}) doldurulmuş metin
Müşteri   GET  /api/v1/destek/sla-bilgisi       mesai + hedefler + kendi taleplerinin
                                                ilk yanıt hedefi (e-posta jetondan)
"""

import logging
import re
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from models.destek_sla import HazirCevaplar
from models.support_tickets import Support_tickets
from pydantic import BaseModel
from services import sla as servis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router_yonetici = APIRouter(prefix="/api/v1/destek", tags=["destek"])

DEGISKENLER = ("musteri_adi", "talep_no", "konu")


def _yonetici_iste(request: Request) -> None:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})


def degiskenleri_doldur(metin: str, degerler: Dict[str, Any]) -> str:
    """{ad} yer tutucularını doldurur; tanınmayan olduğu gibi kalır (yazım hatası görünsün)."""

    def degistir(m: "re.Match[str]") -> str:
        ad = m.group(1)
        if ad in degerler and degerler[ad] is not None:
            return str(degerler[ad])
        return m.group(0)

    return re.sub(r"\{([a-z_]+)\}", degistir, metin or "")


def _musteri_adi(t: Any) -> str:
    ad = (t.client_name or "").strip()
    if ad and "@" not in ad:
        return ad
    eposta = (t.client_email or ad or "").strip()
    return eposta.split("@")[0] if eposta else ""


# ---------------------------------------------------------------------------
# SLA — yönetici
# ---------------------------------------------------------------------------
@router_yonetici.get("/sla")
async def sla_durumlari(request: Request, ids: Optional[str] = Query(None), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    sorgu = select(Support_tickets).order_by(Support_tickets.id.desc())
    if ids:
        try:
            idler = [int(x) for x in ids.split(",") if x.strip()][:500]
        except ValueError:
            raise HTTPException(status_code=400, detail={"kod": "gecersiz_id"})
        sorgu = sorgu.where(Support_tickets.id.in_(idler))
    talepler = (await db.execute(sorgu.limit(500))).scalars().all()
    ayar = await servis.ayarlari_oku(db)
    satirlar = await servis.senkronla(db, talepler, ayar)
    an = servis.simdi()
    sonuc: Dict[str, Any] = {}
    for t in talepler:
        s = satirlar.get(t.id)
        if s is None:
            continue
        d = servis.durum_sozlugu(s, ayar, an)
        d["ozet"] = servis.ozet_durum(d)
        sonuc[str(t.id)] = d
    return sonuc


@router_yonetici.get("/sla-ayarlari")
async def sla_ayarlari(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return (await servis.ayarlari_oku(db)).sozluk()


@router_yonetici.put("/sla-ayarlari")
async def sla_ayarlari_yaz(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        ayar = await servis.ayarlari_yaz(db, govde)
    except servis.SlaHatasi as h:
        raise HTTPException(status_code=400, detail={"kod": h.kod})
    return ayar.sozluk()


# ---------------------------------------------------------------------------
# SLA — müşteri
# ---------------------------------------------------------------------------
@router_yonetici.get("/sla-bilgisi")
async def sla_bilgisi(request: Request, db: AsyncSession = _Depends(get_db)):
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    eposta = (kullanici.email or "").strip().lower()
    ayar = await servis.ayarlari_oku(db)
    talepler = []
    if eposta:
        talepler = (
            await db.execute(
                select(Support_tickets).where(Support_tickets.client_email == eposta).order_by(Support_tickets.id.desc()).limit(100)
            )
        ).scalars().all()
    satirlar = await servis.senkronla(db, talepler, ayar)
    an = servis.simdi()
    kendi: Dict[str, Any] = {}
    for t in talepler:
        s = satirlar.get(t.id)
        if s is None:
            continue
        d = servis.durum_sozlugu(s, ayar, an)
        # Müşteriye iç eskalasyon ayrıntısı değil, yalnız "ne zaman yanıt beklemeli".
        kendi[str(t.id)] = {
            "oncelik": d["oncelik"],
            "ilk_yanit_hedef": d["ilk_yanit"]["hedef"],
            "ilk_yanit_durum": d["ilk_yanit"]["durum"],
        }
    genel = ayar.sozluk()
    return {"mesai": genel["mesai"], "hedefler": genel["hedefler"], "talepler": kendi}


# ---------------------------------------------------------------------------
# Hazır cevaplar
# ---------------------------------------------------------------------------
class HazirCevapGirdisi(BaseModel):
    baslik: str
    metin: str


class UygulaGirdisi(BaseModel):
    ticket_id: int


def _hc(h: HazirCevaplar) -> Dict[str, Any]:
    return {"id": h.id, "baslik": h.baslik, "metin": h.metin}


def _hc_dogrula(govde: HazirCevapGirdisi) -> tuple:
    baslik = (govde.baslik or "").strip()[:120]
    metin = (govde.metin or "").strip()[:8000]
    if not baslik or not metin:
        raise HTTPException(status_code=400, detail={"kod": "alan_gerekli"})
    return baslik, metin


@router_yonetici.get("/hazir-cevaplar")
async def hazir_cevaplar(request: Request, db: AsyncSession = _Depends(get_db)) -> List[Dict[str, Any]]:
    _yonetici_iste(request)
    satirlar = (await db.execute(select(HazirCevaplar).order_by(HazirCevaplar.baslik.asc()))).scalars().all()
    return [_hc(h) for h in satirlar]


@router_yonetici.post("/hazir-cevaplar")
async def hazir_cevap_ekle(request: Request, govde: HazirCevapGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    baslik, metin = _hc_dogrula(govde)
    h = HazirCevaplar(baslik=baslik, metin=metin)
    db.add(h)
    await db.commit()
    await db.refresh(h)
    return _hc(h)


async def _hc_bul(db: AsyncSession, hc_id: int) -> HazirCevaplar:
    h = (await db.execute(select(HazirCevaplar).where(HazirCevaplar.id == hc_id))).scalars().first()
    if h is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    return h


@router_yonetici.put("/hazir-cevaplar/{hc_id}")
async def hazir_cevap_guncelle(
    hc_id: int, request: Request, govde: HazirCevapGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    _yonetici_iste(request)
    h = await _hc_bul(db, hc_id)
    h.baslik, h.metin = _hc_dogrula(govde)
    await db.commit()
    return _hc(h)


@router_yonetici.delete("/hazir-cevaplar/{hc_id}")
async def hazir_cevap_sil(hc_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    h = await _hc_bul(db, hc_id)
    await db.delete(h)
    await db.commit()
    return {"silindi": hc_id}


@router_yonetici.post("/hazir-cevaplar/{hc_id}/uygula")
async def hazir_cevap_uygula(
    hc_id: int, request: Request, govde: UygulaGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    _yonetici_iste(request)
    h = await _hc_bul(db, hc_id)
    t = (await db.execute(select(Support_tickets).where(Support_tickets.id == govde.ticket_id))).scalars().first()
    if t is None:
        raise HTTPException(status_code=404, detail={"kod": "talep_yok"})
    return {
        "metin": degiskenleri_doldur(
            h.metin, {"musteri_adi": _musteri_adi(t), "talep_no": f"#{t.id}", "konu": t.subject}
        )
    }


router = router_yonetici
