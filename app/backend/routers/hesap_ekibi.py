"""Faz 2E — hesap ekibi: üyeler, davet, hesaplar arası geçiş.

Uçlar
-----
Hesap sahibi / hesap yöneticisi (etkin hesap — `X-MK-Hesap` ile seçilen):
* `GET    /api/v1/hesabim/uyeler`                 — liste (uye/fatura salt okunur görür)
* `POST   /api/v1/hesabim/uyeler`                 — davet {email, rol, izinler?}
* `PUT    /api/v1/hesabim/uyeler/{id}`            — rol / izin / pasif-aktif
* `DELETE /api/v1/hesabim/uyeler/{id}`            — üyelik biter (erişim anında düşer)
* `POST   /api/v1/hesabim/uyeler/{id}/davet-yenile`

Davet (bağlantı e-postayla gider; 7 gün, tek kullanımlık, özetle saklanır):
* `GET  /api/v1/hesap-davet/{jeton}`        — girişsiz: hesap adı, maskeli e-posta, rol
* `POST /api/v1/hesap-davet/{jeton}/kabul`  — GİRİŞ GEREKLİ, yalnız davet edilen e-postayla

Her kişi:
* `GET /api/v1/hesaplarim` — erişebildiği hesaplar (kendi + aktif üyelikleri)

Ajans yöneticisi (müşteri adına destek):
* `GET|POST /api/v1/musteri-hesaplari/{hesap_email}/uyeler`, `PUT|DELETE .../{id}`,
  `POST .../{id}/davet-yenile`

Bütün değişiklikler denetim kaydına düşüyor (after_flush; davet jetonu
özeti alan adında "jeton" geçtiği için maskeli). Kabul Core UPDATE olduğu
için servis elle yazıyor.
"""

import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import musteri_baglami
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from models.hesap_uyeleri import HesapUyeleri
from pydantic import BaseModel
from services import hesap_ekibi as servis
from services.hesap_ekibi import HesapBaglami, HesapHatasi
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

hesabim_router = APIRouter(prefix="/api/v1/hesabim/uyeler", tags=["hesap-ekibi"])
davet_router = APIRouter(prefix="/api/v1/hesap-davet", tags=["hesap-ekibi"])
hesaplarim_router = APIRouter(prefix="/api/v1/hesaplarim", tags=["hesap-ekibi"])
yonetici_router = APIRouter(
    prefix="/api/v1/musteri-hesaplari", tags=["hesap-ekibi"], dependencies=[_Depends(yonetici_gerekli)]
)

#: Girişsiz davet ucu: IP başına dakikada en çok bu kadar istek.
_hiz = HizSiniri(30)


class UyeGirdisi(BaseModel):
    email: str
    rol: str = "uye"
    izinler: Optional[List[str]] = None


class UyeGuncelleme(BaseModel):
    rol: Optional[str] = None
    izinler: Optional[List[str]] = None
    #: aktif | pasif
    durum: Optional[str] = None


def _hata(h: HesapHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _hiz_denetle(request: Request) -> None:
    if not _hiz.izin_var_mi(ip_ozeti(istemci_ip(request))):
        raise HTTPException(status_code=429, detail={"kod": "cok_istek"})


def _rol_varsayilanlari() -> Dict[str, List[str]]:
    return {r: list(servis.ROL_VARSAYILAN[r]) for r in servis.ROLLER}


async def _liste_yaniti(db: AsyncSession, aktor: HesapBaglami, hesap: str) -> Dict[str, Any]:
    satirlar = await servis.uyeler(db, hesap)
    adlar = await servis.hesap_adlari(db, [hesap])
    return {
        "hesap_email": hesap,
        "hesap_adi": adlar.get(hesap),
        "rolum": aktor.rol,
        "izinlerim": list(servis.IZINLER if (aktor.yonetici or aktor.rol == servis.SAHIP) else aktor.izinler),
        "yonetebilir": aktor.ekibi_yonetebilir,
        "ben": aktor.kisi_email,
        "izinler": list(servis.IZINLER),
        "roller": _rol_varsayilanlari(),
        "uyeler": [servis.uye_sozlugu(s) for s in satirlar],
    }


async def _ekle(db: AsyncSession, aktor: HesapBaglami, hesap: str, govde: UyeGirdisi) -> Dict[str, Any]:
    rol = servis.rol_duzelt(govde.rol)
    izinler = servis.izinleri_duzelt(govde.izinler, rol)
    servis.degisiklik_yetkisi(aktor, hedef=None, yeni_rol=rol, yeni_izinler=izinler)
    jeton, satir = await servis.davet_olustur(
        db, hesap=hesap, uye=govde.email, rol=rol, izinler=izinler, ekleyen=aktor.kisi_email
    )
    eposta = await servis.davet_epostasi(db, satir, jeton, aktor.kisi_email)
    return {
        "uye": servis.uye_sozlugu(satir),
        # Davet eden kişiye bağlantı da veriliyor (e-posta kapalıysa elden
        # iletebilsin). Bağlantı tek başına yetki değil: kabul, davet edilen
        # e-postayla giriş yapmayı gerektiriyor.
        "baglanti": servis.davet_baglantisi(jeton),
        **eposta,
    }


async def _guncelle(
    db: AsyncSession, aktor: HesapBaglami, hesap: str, uye_id: int, govde: UyeGuncelleme
) -> Dict[str, Any]:
    satir = await servis.uye_bul(db, hesap, uye_id)
    yeni_rol = servis.rol_duzelt(govde.rol) if govde.rol is not None else None
    rol = yeni_rol or satir.rol
    if govde.izinler is not None:
        yeni_izinler = servis.izinleri_duzelt(govde.izinler, rol)
    elif yeni_rol is not None and yeni_rol != satir.rol:
        yeni_izinler = servis.izinleri_duzelt(None, rol)
    else:
        yeni_izinler = None
    servis.degisiklik_yetkisi(aktor, hedef=satir, yeni_rol=yeni_rol, yeni_izinler=yeni_izinler)

    if govde.durum is not None:
        durum = (govde.durum or "").strip().lower()
        if durum not in ("aktif", "pasif"):
            raise HesapHatasi(400, "durum_gecersiz")
        if satir.durum == "davet":
            raise HesapHatasi(409, "davet_bekliyor")
        satir.durum = durum
    if yeni_rol is not None:
        satir.rol = yeni_rol
    if yeni_izinler is not None:
        import json

        satir.izinler = json.dumps(list(yeni_izinler))
    await db.commit()
    await db.refresh(satir)
    servis.onbellegi_temizle()
    return servis.uye_sozlugu(satir)


async def _sil(db: AsyncSession, aktor: HesapBaglami, hesap: str, uye_id: int) -> Dict[str, Any]:
    satir = await servis.uye_bul(db, hesap, uye_id)
    servis.degisiklik_yetkisi(aktor, hedef=satir, yeni_rol=None, yeni_izinler=None)
    await db.delete(satir)
    await db.commit()
    # Üyelik bitti: önbellekteki "aktif" kararı bu süreçte hemen düşsün.
    servis.onbellegi_temizle()
    return {"silindi": uye_id}


async def _davet_yenile(db: AsyncSession, aktor: HesapBaglami, hesap: str, uye_id: int) -> Dict[str, Any]:
    satir = await servis.uye_bul(db, hesap, uye_id)
    servis.degisiklik_yetkisi(aktor, hedef=satir, yeni_rol=None, yeni_izinler=None)
    jeton = await servis.davet_yenile(db, satir)
    eposta = await servis.davet_epostasi(db, satir, jeton, aktor.kisi_email)
    return {"uye": servis.uye_sozlugu(satir), "baglanti": servis.davet_baglantisi(jeton), **eposta}


# ---------------------------------------------------------------------------
# Hesap sahibi / hesap yöneticisi — etkin hesap
# ---------------------------------------------------------------------------


def _aktor(request: Request) -> HesapBaglami:
    return musteri_baglami(request)


@hesabim_router.get("")
async def uye_listesi(request: Request, db: AsyncSession = _Depends(get_db)):
    aktor = _aktor(request)
    return await _liste_yaniti(db, aktor, aktor.hesap_email)


@hesabim_router.post("")
async def uye_ekle(request: Request, govde: UyeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    aktor = _aktor(request)
    try:
        return await _ekle(db, aktor, aktor.hesap_email, govde)
    except HesapHatasi as h:
        raise _hata(h)


@hesabim_router.put("/{uye_id}")
async def uye_guncelle(
    uye_id: int, request: Request, govde: UyeGuncelleme = Body(...), db: AsyncSession = _Depends(get_db)
):
    aktor = _aktor(request)
    try:
        return await _guncelle(db, aktor, aktor.hesap_email, uye_id, govde)
    except HesapHatasi as h:
        raise _hata(h)


@hesabim_router.delete("/{uye_id}")
async def uye_sil(uye_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    aktor = _aktor(request)
    try:
        return await _sil(db, aktor, aktor.hesap_email, uye_id)
    except HesapHatasi as h:
        raise _hata(h)


@hesabim_router.post("/{uye_id}/davet-yenile")
async def uye_davet_yenile(uye_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    aktor = _aktor(request)
    try:
        return await _davet_yenile(db, aktor, aktor.hesap_email, uye_id)
    except HesapHatasi as h:
        raise _hata(h)


# ---------------------------------------------------------------------------
# Davet bağlantısı
# ---------------------------------------------------------------------------


@davet_router.get("/{jeton}")
async def davet_bilgisi(jeton: str, request: Request, db: AsyncSession = _Depends(get_db)):
    """Girişsiz: kim, hangi hesaba, hangi rolle davet edilmiş (e-postalar maskeli)."""
    _hiz_denetle(request)
    satir = await servis.davet_coz(db, jeton)
    if satir is None or satir.durum != "davet":
        raise HTTPException(status_code=404, detail={"kod": "davet_yok"})
    adlar = await servis.hesap_adlari(db, [satir.hesap_email])
    return {
        "durum": servis.gecerli_durum(satir),
        "hesap_adi": adlar.get(satir.hesap_email),
        "hesap_eposta": servis.eposta_maskele(satir.hesap_email),
        "davet_eposta": servis.eposta_maskele(satir.uye_email),
        "rol": satir.rol,
        "izinler": list(servis.izinleri_coz(satir.izinler, satir.rol)),
        "davet_bitis": servis._utc(satir.davet_bitis).isoformat() if satir.davet_bitis else None,
    }


@davet_router.post("/{jeton}/kabul")
async def davet_kabul(jeton: str, request: Request, db: AsyncSession = _Depends(get_db)):
    """Giriş gerekli; jetondaki e-posta davet edilen e-postayla aynı olmalı."""
    _hiz_denetle(request)
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    kisi = servis.eposta_duzelt(kullanici.email)
    if not kisi:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "eposta_yok"})
    try:
        satir = await servis.davet_kabul(db, jeton, kisi)
    except HesapHatasi as h:
        raise _hata(h)
    adlar = await servis.hesap_adlari(db, [satir.hesap_email])
    return {
        "hesap_email": satir.hesap_email,
        "hesap_adi": adlar.get(satir.hesap_email),
        "rol": satir.rol,
        "izinler": list(servis.izinleri_coz(satir.izinler, satir.rol)),
    }


# ---------------------------------------------------------------------------
# Hesaplarım
# ---------------------------------------------------------------------------


@hesaplarim_router.get("")
async def hesaplarim(request: Request, db: AsyncSession = _Depends(get_db)):
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    kisi = servis.eposta_duzelt(kullanici.email)
    if not kisi:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "eposta_yok"})
    return {"ben": kisi, "hesaplar": await servis.hesaplarim(db, kisi)}


# ---------------------------------------------------------------------------
# Ajans yöneticisi — müşteri adına
# ---------------------------------------------------------------------------


def _yonetici_aktor(request: Request, hesap_email: str) -> tuple:
    kullanici, _ = _yonetici_mi(request)
    hesap = servis.eposta_duzelt(hesap_email)
    if not servis.eposta_gecerli_mi(hesap):
        raise HTTPException(status_code=400, detail={"kod": "eposta_gecersiz"})
    return servis.tam_baglam(servis.eposta_duzelt(kullanici.email), yonetici=True), hesap


@yonetici_router.get("/{hesap_email}/uyeler")
async def yonetici_uye_listesi(hesap_email: str, request: Request, db: AsyncSession = _Depends(get_db)):
    aktor, hesap = _yonetici_aktor(request, hesap_email)
    return await _liste_yaniti(db, aktor, hesap)


@yonetici_router.post("/{hesap_email}/uyeler")
async def yonetici_uye_ekle(
    hesap_email: str, request: Request, govde: UyeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    aktor, hesap = _yonetici_aktor(request, hesap_email)
    try:
        return await _ekle(db, aktor, hesap, govde)
    except HesapHatasi as h:
        raise _hata(h)


@yonetici_router.put("/{hesap_email}/uyeler/{uye_id}")
async def yonetici_uye_guncelle(
    hesap_email: str,
    uye_id: int,
    request: Request,
    govde: UyeGuncelleme = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    aktor, hesap = _yonetici_aktor(request, hesap_email)
    try:
        return await _guncelle(db, aktor, hesap, uye_id, govde)
    except HesapHatasi as h:
        raise _hata(h)


@yonetici_router.delete("/{hesap_email}/uyeler/{uye_id}")
async def yonetici_uye_sil(hesap_email: str, uye_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    aktor, hesap = _yonetici_aktor(request, hesap_email)
    try:
        return await _sil(db, aktor, hesap, uye_id)
    except HesapHatasi as h:
        raise _hata(h)


@yonetici_router.post("/{hesap_email}/uyeler/{uye_id}/davet-yenile")
async def yonetici_davet_yenile(
    hesap_email: str, uye_id: int, request: Request, db: AsyncSession = _Depends(get_db)
):
    aktor, hesap = _yonetici_aktor(request, hesap_email)
    try:
        return await _davet_yenile(db, aktor, hesap, uye_id)
    except HesapHatasi as h:
        raise _hata(h)


__all__ = ["HesapUyeleri"]

router = (hesabim_router, davet_router, hesaplarim_router, yonetici_router)
