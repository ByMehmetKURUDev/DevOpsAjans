"""Faz 5K — indirim kodu uçları. Ayrıntı: `services/indirim_kodlari.py`.

* Herkese açık `POST /api/v1/indirim-kodu/dogrula` — formdaki "indirim /
  referans kodu" alanının anlık denetimi. Kod tahmin saldırısına karşı IP
  özeti başına 10 dakikada 10 deneme (kalıcı sayaç; ham IP saklanmaz). Yanıt
  asgari: geçerli mi, türü (indirim | referans), indirimin değeri. Sınırlar,
  kullanım sayısı, paket listesi ve ortak bilgisi DÖNMEZ; bilinmeyen, pasif,
  süresi dolmuş ya da seçili pakete uymayan kodun yanıtı aynı (`gecerli: false`).
* Yönetici `/api/v1/indirim-kodu-yonetim`: CRUD + belge önizlemesi (teklif /
  fatura formundaki "Uygula": kalemler + kod → indirim satırları ve toplamlar;
  kaydedilmez).
"""

import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi import Depends as _Depends
from pydantic import BaseModel, ConfigDict
from services import indirim_kodlari as servis
from services.belge_hesap import HesapHatasi, belge_hesapla
from services.indirim_kodlari import KodHatasi
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

acik_router = APIRouter(prefix="/api/v1/indirim-kodu", tags=["indirim-kodu"])
yonetici_router = APIRouter(prefix="/api/v1/indirim-kodu-yonetim", tags=["indirim-kodu"],
                            dependencies=[_Depends(yonetici_gerekli)])

#: Kod tahminine karşı: IP özeti başına 10 dakikada 10 deneme.
dogrulama_hizi = KaliciHizSiniri("indirim-kodu-dogrula", 10, 600.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    dogrulama_hizi.temizle()


def _hata(h: Exception) -> HTTPException:
    return HTTPException(status_code=getattr(h, "durum", 400), detail=h.detay() if hasattr(h, "detay") else {"kod": "hata"})


class KodGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kod: Optional[str] = None
    aciklama: Optional[str] = None
    tur: Optional[str] = None
    deger: Optional[Any] = None
    para_birimi: Optional[str] = None
    baslangic: Optional[str] = None
    bitis: Optional[str] = None
    toplam_sinir: Optional[Any] = None
    kisi_basi_sinir: Optional[Any] = None
    en_az_tutar: Optional[Any] = None
    kapsam: Optional[List[str]] = None
    paketler: Optional[List[str]] = None
    ortak_id: Optional[Any] = None
    aktif: Optional[bool] = None


class OnizlemeGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kod: Optional[str] = None
    kalemler: List[Dict[str, Any]] = []
    para_birimi: Optional[str] = "TRY"
    belge_turu: str = "teklif"
    eposta: Optional[str] = None
    belge_id: Optional[int] = None


# --------------------------------------------------------------------------
# Herkese açık
# --------------------------------------------------------------------------
@acik_router.post("/dogrula")
async def dogrula(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = _Depends(get_db)):
    if not await izin_ver((dogrulama_hizi, ip_ozeti(istemci_ip(request)))):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"})
    ham = str((govde or {}).get("kod") or "")[:64]
    if not servis.bicim_gecerli(ham):
        return {"gecerli": False}
    cozum = await servis.formdan_coz(db, ham)
    if cozum["indirim_kodu"]:
        k = await servis.kod_bul(db, ham)
        # "Teklif al" penceresi seçili paketi gönderir: pakete uymayan kod bu formda geçersiz görünür.
        paket = str((govde or {}).get("paket") or "").strip().upper()[:20]
        if paket and servis.paketler(k) and paket not in servis.paketler(k):
            return {"gecerli": False}
        return {"gecerli": True, "tur": "indirim", "kod": k.kod, "indirim": servis.herkese_acik(k)}
    if cozum["referans_kodu"]:
        return {"gecerli": True, "tur": "referans", "kod": cozum["referans_kodu"]}
    return {"gecerli": False}


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
def _yonetici(request: Request) -> str:
    kullanici, _ = _yonetici_mi(request)
    return (getattr(kullanici, "email", "") or "").strip().lower()


@yonetici_router.get("")
async def liste(db: AsyncSession = _Depends(get_db)):
    return await servis.liste(db)


@yonetici_router.post("")
async def olustur(request: Request, govde: KodGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    try:
        k = await servis.olustur(db, govde.model_dump(exclude_unset=True), _yonetici(request))
    except KodHatasi as h:
        raise _hata(h)
    return await servis.kod_sozlugu(db, k)


@yonetici_router.put("/{kod_id}")
async def guncelle(kod_id: int, govde: KodGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    try:
        k = await servis.getir(db, kod_id)
        k = await servis.guncelle(db, k, govde.model_dump(exclude_unset=True))
    except KodHatasi as h:
        raise _hata(h)
    return await servis.kod_sozlugu(db, k)


@yonetici_router.delete("/{kod_id}")
async def sil(kod_id: int, db: AsyncSession = _Depends(get_db)):
    try:
        k = await servis.getir(db, kod_id)
        await servis.sil(db, k)
    except KodHatasi as h:
        raise _hata(h)
    return {"silindi": kod_id}


@yonetici_router.post("/onizle")
async def onizle(govde: OnizlemeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    """Kalemler + kod → indirim satırları ve toplamlar (kaydedilmez; kullanım yazılmaz)."""
    if govde.belge_turu not in servis.BELGE_TURLERI:
        raise HTTPException(status_code=400, detail={"kod": "belge_turu_gecersiz"})
    paket, ek_kapsam = None, ()
    if govde.belge_id and govde.belge_turu == "teklif":
        from models.teklifler import Teklifler
        from sqlalchemy import select

        talep_id = (await db.execute(select(Teklifler.pricing_inquiry_id).where(Teklifler.id == govde.belge_id))).scalar()
        if talep_id:
            paket, ek_kapsam = await servis.belge_paketi(db, pricing_inquiry_id=talep_id), ("paket",)
    elif govde.belge_id:
        paket = await servis.belge_paketi(db, fatura_id=govde.belge_id)
    try:
        u = await servis.belgeye_uygula(
            db, kalemler=govde.kalemler, ham_kod=govde.kod or "", mevcut_kod=None, belge_turu=govde.belge_turu,
            belge_id=govde.belge_id, para_birimi=(govde.para_birimi or "TRY").upper(), eposta=govde.eposta,
            ek_kapsam=ek_kapsam, paket=paket,
        )
        belge = belge_hesapla(u.kalemler, bos_olabilir=True)
    except KodHatasi as h:
        raise _hata(h)
    except HesapHatasi as h:
        raise HTTPException(status_code=400, detail=h.detay())
    return {"kod": u.kod.kod if u.kod else None, "indirim": float(u.indirim), "kalemler": belge.kalem_listesi(),
            **belge.ozet()}


router = (acik_router, yonetici_router)
