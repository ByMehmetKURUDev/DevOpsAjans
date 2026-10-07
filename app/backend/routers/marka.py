"""Faz 4L — Marka teması (white-label) uçları.

Müşteri (modül `marka_temasi` açıkken; etkin hesap `dependencies/hesap_baglami`):
  GET    /api/v1/markam              hesabın markası + kontrast denetimi (ekipte herkes okur)
  PUT    /api/v1/markam              {ad, ana_renk, vurgu_rengi, zemin, kose, yazi_tipi}
                                     (yalnız hesap sahibi ya da ekipte "yönetici" rolü;
                                     `rozet_gizle` gönderilirse 403 — o yalnız ajansın modül ayarı)
  DELETE /api/v1/markam              markayı sıfırla (logo dahil)
  POST   /api/v1/markam/logo         çok parçalı {dosya} — PNG/JPEG/WebP ≤ 2 MB, SVG reddedilir
  DELETE /api/v1/markam/logo

Yönetici (Sistem › Modüller › müşteri ayrıntısı):
  GET/PUT/DELETE /api/v1/marka/yonetim/{eposta}
  POST/DELETE    /api/v1/marka/yonetim/{eposta}/logo
  (rozet `rozet_gizle` mevcut modül ayarı ucundan: PUT /api/v1/moduller/musteri/{eposta}/marka_temasi)

Herkese açık:
  GET /api/v1/marka/logo/{anahtar}.webp|.png   (adres her yüklemede yeni → değişmez içerik)

Sayfalara uygulanan marka verisi ayrı bir istekle değil, sayfanın zaten yaptığı
herkese açık isteğin yanıtında (`marka` alanı, `services.marka.acik_marka`) geliyor.
"""

import logging
from typing import Any, Dict

from core.database import get_db
from dependencies.hesap_baglami import musteri_baglami
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from services import marka as m
from services.hesap_ekibi import SAHIP
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri

logger = logging.getLogger(__name__)

musteri_router = APIRouter(prefix="/api/v1/markam", tags=["marka"], dependencies=[Depends(modul_gerekli(m.MODUL))])
yonetici_router = APIRouter(prefix="/api/v1/marka/yonetim", tags=["marka"], dependencies=[Depends(yonetici_gerekli)])
acik_router = APIRouter(prefix="/api/v1/marka", tags=["marka"])

#: Kişi başı: dakikada 30 kayıt, 10 logo yükleme.
_yazma_hizi = HizSiniri(30, 60.0)
_logo_hizi = HizSiniri(10, 60.0)
#: Markayı değiştirebilen ekip rolleri (hesap sahibi örtük rol).
YAZABILEN_ROLLER = (SAHIP, "yonetici")


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _logo_hizi):
        h.temizle()


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _marka_hatasi(h: m.MarkaHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _hiz(sinir: HizSiniri, anahtar: str) -> None:
    if not sinir.izin_var_mi(anahtar or "anonim"):
        raise _hata(429, "cok_hizli")


def _eposta_dogrula(eposta: str) -> str:
    e = m.eposta_duzelt(eposta)
    if not e or "@" not in e or len(e) > 254 or any(c.isspace() for c in e):
        raise _hata(400, "eposta_gecersiz")
    return e


async def _panel(db: AsyncSession, hesap: str) -> Dict[str, Any]:
    acik, rozet_gizle = await m.modul_durumu(db, hesap)
    return m.panel_sozlugu(await m.kayit_getir(db, hesap), hesap=hesap, modul_acik=acik, rozet_gizle=rozet_gizle)


def _musteri_yazar(request: Request):
    """Yazma: yalnız hesap sahibi ya da ekipte hesap yöneticisi."""
    baglam = musteri_baglami(request)
    if not (baglam.yonetici or baglam.rol in YAZABILEN_ROLLER):
        raise _hata(403, "marka_yetkisi_yok")
    return baglam


async def _kaydet(db: AsyncSession, hesap: str, govde: Any, kisi: str) -> Dict[str, Any]:
    _hiz(_yazma_hizi, kisi)
    try:
        await m.kaydet(db, hesap, govde, kisi)
    except m.MarkaHatasi as h:
        await db.rollback()
        raise _marka_hatasi(h)
    return await _panel(db, hesap)


async def _logo(db: AsyncSession, hesap: str, dosya: UploadFile, kisi: str) -> Dict[str, Any]:
    _hiz(_logo_hizi, kisi)
    bayt = await dosya.read(m.LOGO_EN_COK_BAYT + 1)
    try:
        await m.logo_kaydet(db, hesap, bayt, dosya.filename or "", dosya.content_type or "", kisi)
    except m.MarkaHatasi as h:
        await db.rollback()
        raise _marka_hatasi(h)
    return await _panel(db, hesap)


# ---------------------------------------------------------------------------
# Müşteri
# ---------------------------------------------------------------------------
@musteri_router.get("")
async def markam(request: Request, db: AsyncSession = Depends(get_db)):
    return await _panel(db, musteri_baglami(request).hesap_email)


@musteri_router.put("")
async def markam_kaydet(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    baglam = _musteri_yazar(request)
    if "rozet_gizle" in govde:
        # Rozet ajansın ticari kararı: yalnız yönetici (modül ayarı) değiştirir.
        raise _hata(403, "yalniz_yonetici", alan="rozet_gizle")
    return await _kaydet(db, baglam.hesap_email, govde, baglam.kisi_email)


@musteri_router.delete("")
async def markam_sifirla(request: Request, db: AsyncSession = Depends(get_db)):
    baglam = _musteri_yazar(request)
    _hiz(_yazma_hizi, baglam.kisi_email)
    await m.sifirla(db, baglam.hesap_email)
    return await _panel(db, baglam.hesap_email)


@musteri_router.post("/logo")
async def markam_logo(request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    baglam = _musteri_yazar(request)
    return await _logo(db, baglam.hesap_email, dosya, baglam.kisi_email)


@musteri_router.delete("/logo")
async def markam_logo_kaldir(request: Request, db: AsyncSession = Depends(get_db)):
    baglam = _musteri_yazar(request)
    await m.logo_kaldir(db, baglam.hesap_email, baglam.kisi_email)
    return await _panel(db, baglam.hesap_email)


# ---------------------------------------------------------------------------
# Yönetici
# ---------------------------------------------------------------------------
def _yonetici(request: Request) -> str:
    kullanici, _ = _yonetici_mi(request)
    return m.eposta_duzelt(getattr(kullanici, "email", "") or "")


@yonetici_router.get("/{eposta}")
async def yonetim_marka(eposta: str, db: AsyncSession = Depends(get_db)):
    return await _panel(db, _eposta_dogrula(eposta))


@yonetici_router.put("/{eposta}")
async def yonetim_kaydet(eposta: str, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    hesap = _eposta_dogrula(eposta)
    if "rozet_gizle" in govde:
        raise _hata(400, "modul_ayari_kullanin", alan="rozet_gizle")
    return await _kaydet(db, hesap, govde, _yonetici(request))


@yonetici_router.delete("/{eposta}")
async def yonetim_sifirla(eposta: str, db: AsyncSession = Depends(get_db)):
    hesap = _eposta_dogrula(eposta)
    await m.sifirla(db, hesap)
    return await _panel(db, hesap)


@yonetici_router.post("/{eposta}/logo")
async def yonetim_logo(eposta: str, request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    return await _logo(db, _eposta_dogrula(eposta), dosya, _yonetici(request))


@yonetici_router.delete("/{eposta}/logo")
async def yonetim_logo_kaldir(eposta: str, request: Request, db: AsyncSession = Depends(get_db)):
    hesap = _eposta_dogrula(eposta)
    await m.logo_kaldir(db, hesap, _yonetici(request))
    return await _panel(db, hesap)


# ---------------------------------------------------------------------------
# Herkese açık: logo
# ---------------------------------------------------------------------------
@acik_router.get("/logo/{dosya}")
async def logo(dosya: str, db: AsyncSession = Depends(get_db)):
    anahtar, _, uzanti = dosya.rpartition(".")
    if uzanti not in ("webp", "png") or not anahtar:
        raise _hata(404, "bulunamadi")
    veri = await m.logo_icerigi(db, anahtar)
    if veri is None:
        raise _hata(404, "bulunamadi")
    basliklar = {
        # Adres yüklemeye özel (anahtar her yüklemede yeni): içerik asla değişmiyor.
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
    }
    if uzanti == "png":
        # E-posta istemcileri (Outlook WebP göstermiyor).
        return Response(m.png_uret(veri), media_type="image/png", headers=basliklar)
    return Response(veri, media_type="image/webp", headers=basliklar)


router = (musteri_router, yonetici_router, acik_router)
