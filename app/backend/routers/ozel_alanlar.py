"""Faz 4W — özel alanlar (tanım: yalnız ajans; değerler: ajans düzenler, müşteri görünürleri okur).

Yönetici (`/api/v1/ozel-alanlar/yonetim`, yönetici):
  GET    ""                              ?varlik= — tanımlar (pasifler dahil) + varlık/tür listesi
  POST   ""                              {varlik, ad, anahtar?, tur, secenekler?, zorunlu?, sira?, musteriye_gorunur?}
  PUT    "/{id}"                         kısmi güncelle (varlık ve anahtar değişmez)
  DELETE "/{id}"                         sil (çöp kutusuna; değerler kalır, geri alınınca döner)
  GET    "/deger/{varlik}/{varlik_id}"   ekran bölümü: tanımlar + değerler
  PUT    "/deger/{varlik}/{varlik_id}"   {degerler: {anahtar: değer}} — tür + zorunlu doğrulaması

Müşteri (`/api/v1/ozel-alanlarim`; kayıt etkin hesabın olmalı):
  GET    "/proje/{id}"                   yalnız "müşteriye görünür" alanlar, salt okunur (izin `projeler`)
  GET    "/destek/{id}"                  aynı (izin `destek`)
"""

from typing import Any, Dict, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from models.otomasyon import OzelAlanlar
from services import ozel_alanlar as s
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

yonetici_router = APIRouter(prefix="/api/v1/ozel-alanlar/yonetim", tags=["ozel_alanlar"],
                            dependencies=[Depends(yonetici_gerekli)])
musteri_router = APIRouter(prefix="/api/v1/ozel-alanlarim", tags=["ozel_alanlar"])


def _hata(h: s.OzelAlanHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _kisi(request: Request) -> Optional[str]:
    kullanici, _ = _yonetici_mi(request)
    return (getattr(kullanici, "email", "") or "").strip().lower() or None


async def _tanim(db: AsyncSession, alan_id: int) -> OzelAlanlar:
    a = (await db.execute(select(OzelAlanlar).where(OzelAlanlar.id == alan_id))).scalars().first()
    if a is None:
        raise HTTPException(status_code=404, detail={"kod": "alan_yok"})
    return a


async def varlik_var_mi(db: AsyncSession, varlik: str, varlik_id: str, hesap: Optional[str] = None) -> bool:
    """Kayıt var mı (müşteride ayrıca etkin hesabın mı)."""
    if varlik == "hesap":
        return hesap is None and s.eposta_gecerli(varlik_id)
    if not str(varlik_id).isdigit():
        return False
    kimlik = int(varlik_id)
    if varlik == "crm_aday":
        from models.crm import CrmAdaylari

        return hesap is None and (await db.execute(select(CrmAdaylari.id).where(CrmAdaylari.id == kimlik))).scalar() is not None
    if varlik == "proje":
        from models.projects import Projects

        sorgu = select(Projects.id).where(Projects.id == kimlik)
        if hesap is not None:
            sorgu = sorgu.where(func.lower(Projects.client_email) == hesap)
        return (await db.execute(sorgu)).scalar() is not None
    if varlik == "destek":
        from models.support_tickets import Support_tickets

        sorgu = select(Support_tickets.id).where(Support_tickets.id == kimlik)
        if hesap is not None:
            sorgu = sorgu.where(func.lower(Support_tickets.client_email) == hesap)
        return (await db.execute(sorgu)).scalar() is not None
    return False


def _kimlik(varlik: str, varlik_id: str) -> str:
    if varlik not in s.VARLIKLAR:
        raise HTTPException(status_code=404, detail={"kod": "varlik_gecersiz"})
    return s.eposta_duzelt(varlik_id) if varlik == "hesap" else str(varlik_id).strip()


# ---------------------------------------------------------------------------
# Yönetici
# ---------------------------------------------------------------------------
@yonetici_router.get("")
async def liste(varlik: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    if varlik and varlik not in s.VARLIKLAR:
        raise HTTPException(status_code=400, detail={"kod": "varlik_gecersiz"})
    alanlar = await s.tanimlar(db, varlik, yalniz_aktif=False)
    return {
        "items": [s.tanim_sozlugu(a) for a in alanlar],
        "varliklar": list(s.VARLIKLAR),
        "turler": list(s.TURLER),
        "gorunur_olabilir": list(s.GORUNUR_OLABILIR),
        "form_turleri": list(s.FORM_TURLERI),
        "sinir": s.VARLIK_ALAN_SINIRI,
    }


@yonetici_router.post("")
async def olustur(govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    try:
        temiz = s.tanim_dogrula(govde)
    except s.OzelAlanHatasi as h:
        raise _hata(h)
    sayi = int((await db.execute(select(func.count(OzelAlanlar.id)).where(OzelAlanlar.varlik == temiz["varlik"]))).scalar() or 0)
    if sayi >= s.VARLIK_ALAN_SINIRI:
        raise HTTPException(status_code=409, detail={"kod": "alan_siniri", "sinir": s.VARLIK_ALAN_SINIRI})
    cakisan = (await db.execute(
        select(OzelAlanlar.id).where(OzelAlanlar.varlik == temiz["varlik"], OzelAlanlar.anahtar == temiz["anahtar"])
    )).scalar()
    if cakisan is not None:
        raise HTTPException(status_code=409, detail={"kod": "anahtar_kullanimda"})
    if "sira" not in temiz:
        en_buyuk = (await db.execute(select(func.max(OzelAlanlar.sira)).where(OzelAlanlar.varlik == temiz["varlik"]))).scalar()
        temiz["sira"] = int(en_buyuk or 0) + 10
    a = OzelAlanlar(**{"aktif": True, **temiz})
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return s.tanim_sozlugu(a)


@yonetici_router.put("/{alan_id}")
async def guncelle(alan_id: int, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    a = await _tanim(db, alan_id)
    try:
        temiz = s.tanim_dogrula(govde, mevcut=a)
    except s.OzelAlanHatasi as h:
        raise _hata(h)
    for k, v in temiz.items():
        setattr(a, k, v)
    await db.commit()
    await db.refresh(a)
    return s.tanim_sozlugu(a)


@yonetici_router.delete("/{alan_id}")
async def sil(alan_id: int, db: AsyncSession = Depends(get_db)):
    a = await _tanim(db, alan_id)
    await db.delete(a)
    await db.commit()
    return {"silindi": True, "id": alan_id}


@yonetici_router.get("/deger/{varlik}/{varlik_id}")
async def deger_oku(varlik: str, varlik_id: str, db: AsyncSession = Depends(get_db)):
    kimlik = _kimlik(varlik, varlik_id)
    if not await varlik_var_mi(db, varlik, kimlik):
        raise HTTPException(status_code=404, detail={"kod": "kayit_yok"})
    return await s.bolum(db, varlik, kimlik)


@yonetici_router.put("/deger/{varlik}/{varlik_id}")
async def deger_yaz(varlik: str, varlik_id: str, request: Request, govde: Dict[str, Any] = Body(...),
                    db: AsyncSession = Depends(get_db)):
    kimlik = _kimlik(varlik, varlik_id)
    if not await varlik_var_mi(db, varlik, kimlik):
        raise HTTPException(status_code=404, detail={"kod": "kayit_yok"})
    degerler = govde.get("degerler")
    try:
        await s.degerleri_yaz(db, varlik, kimlik, degerler if isinstance(degerler, dict) else None, kisi=_kisi(request),
                              tam=govde.get("tam") is not False)
    except s.OzelAlanHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.commit()
    return await s.bolum(db, varlik, kimlik)


# ---------------------------------------------------------------------------
# Müşteri (salt okunur, yalnız görünür alanlar)
# ---------------------------------------------------------------------------
@musteri_router.get("/{varlik}/{varlik_id}")
async def musteri_oku(varlik: str, varlik_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    izin = {"proje": "projeler", "destek": "destek"}.get(varlik)
    if izin is None:
        # Yine de hesap/izin bağlamı denetlensin (yabancı başlık 403 alsın), sonra 404.
        izin_iste(request)
        raise HTTPException(status_code=404, detail={"kod": "varlik_gecersiz"})
    baglam = izin_iste(request, izin)
    if not await varlik_var_mi(db, varlik, str(varlik_id), hesap=baglam.hesap_email):
        raise HTTPException(status_code=404, detail={"kod": "kayit_yok"})
    return await s.bolum(db, varlik, varlik_id, yalniz_gorunur=True)


router = (yonetici_router, musteri_router)
