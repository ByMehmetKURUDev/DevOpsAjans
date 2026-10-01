"""Faz 3Z — zaman takibi uçları.

Personel + yönetici  /api/v1/zaman/...          (personel YALNIZ kendi kayıtları)
    GET    /ben                        kim olduğum (personel mi, yönetici mi) — herkese 200
    GET    /secenekler                 form listeleri (projeler, görevler; yöneticiye ekip + ayarlar)
    GET    /sayac                      açık sayacım
    POST   /sayac/baslat               {proje_id, gorev_id?, aciklama?, faturalanabilir?, tur?}
    POST   /sayac/durdur               {sure_dk?, aciklama?}  (12 saati aşan sayaç: 409 uzun_sayac)
    GET    /kayitlar                   ?durum=&proje_id=&kisi=&baslangic=&bitis=&faturalanabilir=&sinir=
    POST   /kayitlar                   elle kayıt {proje_id, gorev_id?, tarih+saat | baslangic, sure_dk | bitis, ...}
    PATCH  /kayitlar/{id}              (onaylı/faturalı kilitli → 409)
    DELETE /kayitlar/{id}              (çöp kutusuna; kilitli → 409)
    GET    /cizelge                    ?hafta=YYYY-MM-DD&kisi=&proje_id=

Yönetici  /api/v1/zaman/yonetim/...
    POST   /onay                       {idler, islem: onayla|reddet, not?}
    POST   /kayitlar/{id}/onay-geri-al
    GET    /is-yuku
    GET    /faturalanabilir?proje_id=
    POST   /faturaya-aktar             {proje_id, idler?, gruplama: tek|kisi|gorev, kdv_orani?, fatura_id?, varsayilan_ucret?}
    GET    /disa-aktar.csv             ?baslangic=&bitis=&proje_id=&kisi=
    GET|PUT /proje/{proje_id}/ayar     saatlik ücret, para birimi, müşteriye süre gösterimi
    GET|PUT /ayarlar                   site varsayılan saatlik ücreti + para birimi

Müşteri  /api/v1/zamanim/proje/{proje_id}   (`projeler` izni + `zaman_takibi` modülü;
    yalnız kendi projesi ve proje ayarı açıksa — yoksa 404)
"""

import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, musteri_eposta
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from services import zaman_takibi as zs
from services.gorevler import eposta_duzelt
from services.zaman_takibi import Kisi, ZamanHatasi
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Kimlik
# --------------------------------------------------------------------------
async def personel_baglami(request: Request, db: AsyncSession = _Depends(get_db)) -> Kisi:
    """Oturumsuz 401; yönetici ya da AKTİF ekip üyesi değilse 403 `personel_degil`."""
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    eposta = eposta_duzelt(getattr(kullanici, "email", None))
    if not eposta:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "personel_degil"})
    if yonetici:
        kisi = await zs.personel_mi(db, eposta)
        return Kisi(eposta=eposta, yonetici=True, personel=True, ad=kisi.ad if kisi else None)
    kisi = await zs.personel_mi(db, eposta)
    if kisi is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "personel_degil"})
    return Kisi(eposta=eposta, yonetici=False, personel=True, ad=kisi.ad)


acik_router = APIRouter(prefix="/api/v1/zaman", tags=["zaman"])
personel_router = APIRouter(prefix="/api/v1/zaman", tags=["zaman"], dependencies=[_Depends(personel_baglami)])
yonetici_router = APIRouter(
    prefix="/api/v1/zaman/yonetim", tags=["zaman"], dependencies=[_Depends(yonetici_gerekli)]
)
musteri_router = APIRouter(
    prefix="/api/v1/zamanim",
    tags=["zaman"],
    dependencies=[_Depends(izin_gerekli("projeler")), _Depends(modul_gerekli("zaman_takibi"))],
)


# --------------------------------------------------------------------------
# Şemalar (ek alanlar yok sayılır; doğrulama serviste)
# --------------------------------------------------------------------------
class Govde(BaseModel):
    model_config = ConfigDict(extra="allow")


def _govde(g: Optional[Govde]) -> Dict[str, Any]:
    if g is None:
        return {}
    veri = g.model_dump(exclude_unset=True)
    veri.update(g.model_extra or {})
    return veri


def _yonetici(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})
    return eposta_duzelt(kullanici.email)


def _bool(deger: Optional[str]) -> Optional[bool]:
    if deger in (None, ""):
        return None
    return str(deger).lower() in ("1", "true", "evet", "yes")


# --------------------------------------------------------------------------
# Herkese (oturumlu) açık: kim olduğum
# --------------------------------------------------------------------------
@acik_router.get("/ben")
async def ben(request: Request, db: AsyncSession = _Depends(get_db)):
    """Panelin "Zaman" bölümünü gösterip göstermeyeceği. Kişiye ait (hesaptan bağımsız)."""
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    eposta = eposta_duzelt(getattr(kullanici, "email", None))
    kisi = await zs.personel_mi(db, eposta) if eposta else None
    return {"eposta": eposta, "yonetici": bool(yonetici), "personel": bool(yonetici or kisi is not None),
            "ad": kisi.ad if kisi else None}


# --------------------------------------------------------------------------
# Personel + yönetici
# --------------------------------------------------------------------------
@personel_router.get("/secenekler")
async def secenekler(kisi: Kisi = _Depends(personel_baglami), db: AsyncSession = _Depends(get_db)):
    return await zs.secenekler(db, kisi)


@personel_router.get("/sayac")
async def sayac(kisi: Kisi = _Depends(personel_baglami), db: AsyncSession = _Depends(get_db)):
    return await zs.sayac_durumu(db, kisi)


@personel_router.post("/sayac/baslat")
async def sayac_baslat(govde: Govde = Body(...), kisi: Kisi = _Depends(personel_baglami), db: AsyncSession = _Depends(get_db)):
    return await zs.sayac_baslat(db, kisi, _govde(govde))


@personel_router.post("/sayac/durdur")
async def sayac_durdur(
    govde: Optional[Govde] = Body(None), kisi: Kisi = _Depends(personel_baglami), db: AsyncSession = _Depends(get_db)
):
    return await zs.sayac_durdur(db, kisi, _govde(govde))


@personel_router.get("/kayitlar")
async def kayitlar(
    durum: Optional[str] = Query(None),
    proje_id: Optional[int] = Query(None),
    kisi_eposta: Optional[str] = Query(None, alias="kisi"),
    baslangic: Optional[str] = Query(None),
    bitis: Optional[str] = Query(None),
    faturalanabilir: Optional[str] = Query(None),
    faturalanmamis: Optional[str] = Query(None),
    sinir: int = Query(200, ge=1, le=zs.LISTE_SINIRI),
    kisi: Kisi = _Depends(personel_baglami),
    db: AsyncSession = _Depends(get_db),
):
    liste = await zs.kayitlari_listele(
        db, kisi, durum=durum, proje_id=proje_id, kisi_eposta=kisi_eposta, baslangic=baslangic, bitis=bitis,
        faturalanabilir=_bool(faturalanabilir), faturalanmamis=bool(_bool(faturalanmamis)), sinir=sinir,
    )
    return {"kayitlar": await zs.sozlukler(db, liste)}


@personel_router.post("/kayitlar")
async def kayit_ekle(govde: Govde = Body(...), kisi: Kisi = _Depends(personel_baglami), db: AsyncSession = _Depends(get_db)):
    return await zs.kayit_olustur(db, kisi, _govde(govde))


@personel_router.patch("/kayitlar/{kayit_id}")
async def kayit_guncelle(
    kayit_id: int, govde: Govde = Body(...), kisi: Kisi = _Depends(personel_baglami), db: AsyncSession = _Depends(get_db)
):
    return await zs.kayit_guncelle(db, kisi, kayit_id, _govde(govde))


@personel_router.delete("/kayitlar/{kayit_id}")
async def kayit_sil(kayit_id: int, kisi: Kisi = _Depends(personel_baglami), db: AsyncSession = _Depends(get_db)):
    return await zs.kayit_sil(db, kisi, kayit_id)


@personel_router.get("/cizelge")
async def cizelge(
    hafta: Optional[str] = Query(None),
    kisi_eposta: Optional[str] = Query(None, alias="kisi"),
    proje_id: Optional[int] = Query(None),
    kisi: Kisi = _Depends(personel_baglami),
    db: AsyncSession = _Depends(get_db),
):
    return await zs.cizelge(db, kisi, hafta=hafta, kisi_eposta=kisi_eposta, proje_id=proje_id)


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.post("/onay")
async def onay(request: Request, govde: Govde = Body(...), db: AsyncSession = _Depends(get_db)):
    return await zs.onay_islemi(db, _yonetici(request), _govde(govde))


@yonetici_router.post("/kayitlar/{kayit_id}/onay-geri-al")
async def onay_geri_al(kayit_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici(request)
    return await zs.onayi_geri_al(db, kayit_id)


@yonetici_router.get("/is-yuku")
async def is_yuku(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici(request)
    return await zs.is_yuku(db)


@yonetici_router.get("/faturalanabilir")
async def faturalanabilir(request: Request, proje_id: int = Query(...), db: AsyncSession = _Depends(get_db)):
    _yonetici(request)
    return await zs.faturalanabilir_ozet(db, proje_id)


@yonetici_router.post("/faturaya-aktar")
async def faturaya_aktar(request: Request, govde: Govde = Body(...), db: AsyncSession = _Depends(get_db)):
    return await zs.faturaya_aktar(db, _yonetici(request), _govde(govde))


@yonetici_router.get("/disa-aktar.csv")
async def disa_aktar(
    request: Request,
    baslangic: Optional[str] = Query(None),
    bitis: Optional[str] = Query(None),
    proje_id: Optional[int] = Query(None),
    kisi_eposta: Optional[str] = Query(None, alias="kisi"),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici(request)
    metin = await zs.csv_metni(db, baslangic=baslangic, bitis=bitis, proje_id=proje_id, kisi_eposta=kisi_eposta)
    ad = f"zaman-{baslangic or 'tum'}-{bitis or 'bugun'}.csv".replace("/", "-")
    return Response(
        content=metin.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{ad}"', "Cache-Control": "no-store"},
    )


@yonetici_router.get("/proje/{proje_id}/ayar")
async def proje_ayari(proje_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici(request)
    return await zs.proje_ayari(db, await zs.proje_bul(db, proje_id))


@yonetici_router.put("/proje/{proje_id}/ayar")
async def proje_ayari_yaz(proje_id: int, request: Request, govde: Govde = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici(request)
    return await zs.proje_ayari_yaz(db, await zs.proje_bul(db, proje_id), _govde(govde))


@yonetici_router.get("/ayarlar")
async def ayarlar(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici(request)
    return await zs.ayarlar(db)


@yonetici_router.put("/ayarlar")
async def ayarlari_yaz(request: Request, govde: Govde = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici(request)
    return await zs.ayarlari_yaz(db, _govde(govde))


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
@musteri_router.get("/proje/{proje_id}")
async def musteri_proje_suresi(proje_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Kendi projesinin onaylı süre özeti. Başkasının projesi ya da ayar kapalı → 404."""
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    eposta = musteri_eposta(request)
    try:
        proje = await zs.proje_bul(db, proje_id)
    except ZamanHatasi:
        raise HTTPException(status_code=404, detail={"kod": "proje_yok"})
    if not yonetici and eposta_duzelt(proje.client_email) != eposta:
        raise HTTPException(status_code=404, detail={"kod": "proje_yok"})
    if not proje.sure_musteriye_gorunur:
        raise HTTPException(status_code=404, detail={"kod": "gizli"})
    return await zs.musteri_ozeti(db, proje)


router = (acik_router, yonetici_router, personel_router, musteri_router)
