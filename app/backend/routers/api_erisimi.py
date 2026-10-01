"""Faz 4A — panelden API anahtarı ve webhook yönetimi.

Yönetici (`/api/v1/api-erisimi/yonetim`) — ajansın kendi anahtarları/uç noktaları
(bütün müşterilere erişir; `?hepsi=1` ile müşterilerinkiler de listelenir ve
iptal edilebilir — kötüye kullanımda):
Müşteri (`/api/v1/api-erisimim`; modül `api_erisimi` açık + hesap izni `api`) —
yalnız etkin hesabın anahtarları/uç noktaları:

  GET    "/meta"                                  kapsamlar, olaylar, sınırlar, API/MCP adresleri
  GET    "/anahtarlar"                            liste (özet/ham anahtar ASLA dönmez)
  POST   "/anahtarlar"                            {ad, kapsamlar[], son_kullanma?, ip_izinleri?, dakika_siniri?,
                                                   suresiz_onay? (ajans)} → {anahtar, ham_anahtar} (BİR KEZ)
  POST   "/anahtarlar/{id}/iptal"                 anında geçersiz
  GET    "/webhooklar"                            uç noktaları (+ bekleyen teslimat sayısı)
  POST   "/webhooklar"                            {url, olaylar[], aciklama?, aktif?, tum_musteriler? (ajans)}
                                                   → {uc, gizli} (gizli BİR KEZ)
  PUT    "/webhooklar/{id}"                       kısmi güncelle (url yeniden SSRF denetimi)
  DELETE "/webhooklar/{id}"                       kalıcı sil (teslimat geçmişiyle)
  POST   "/webhooklar/{id}/gizli-yenile"          yeni sır (eskisi 24 saat ikinci imzayla) → {gizli}
  POST   "/webhooklar/{id}/test"                  `ping` olayı hemen gönderilir → sonuç
  GET    "/webhooklar/{id}/teslimatlar"           ?limit=&once=&durum= — geçmiş + denemeler
  POST   "/webhooklar/{id}/teslimatlar/{tid}/yeniden-gonder"

Kötüye kullanım: kişi başı hız sınırı (anahtar oluşturma 10/dk, test/yeniden gönder 20/dk),
hesap başına anahtar ve uç noktası sınırı (modül ayarları `anahtar_siniri`, `webhook_siniri`).
Ham anahtar ve webhook sırrı hiçbir yanıtta ikinci kez dönmez, günlüğe yazılmaz;
denetim kaydında sütun adları ("anahtar") gereği maskeli.
"""

import logging
import os
from typing import Any, Callable, Dict, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.routing import APIRoute
from fastapi.responses import Response
from services import api_erisimi as s
from services import webhook as w
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri

logger = logging.getLogger(__name__)

_olusturma_hizi = HizSiniri(10, 60.0)
_gonderim_hizi = HizSiniri(20, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_olusturma_hizi, _gonderim_hizi):
        h.temizle()
    s.hiz.temizle()


class _PanelRotasi(APIRoute):
    """Servisin `ApiHatasi`'nı panelin alıştığı `{"detail": {"kod": ...}}` biçimine çevirir."""

    def get_route_handler(self) -> Callable:
        asil = super().get_route_handler()

        async def isleyici(request: Request) -> Response:
            try:
                return await asil(request)
            except s.ApiHatasi as h:
                raise HTTPException(status_code=h.durum, detail=h.detay(), headers=h.basliklar or None)

        return isleyici


yonetici_router = APIRouter(
    prefix="/api/v1/api-erisimi/yonetim",
    tags=["api_erisimi"],
    dependencies=[Depends(yonetici_gerekli)],
    route_class=_PanelRotasi,
)
musteri_router = APIRouter(
    prefix="/api/v1/api-erisimim",
    tags=["api_erisimi"],
    dependencies=[Depends(modul_gerekli(s.MODUL)), Depends(izin_gerekli(s.IZIN))],
    route_class=_PanelRotasi,
)


def _yonetici_sahibi(request: Request) -> s.Sahip:
    kullanici, _ = _yonetici_mi(request)
    return s.Sahip(yonetici=True, hesap=None, kisi=(getattr(kullanici, "email", "") or "").strip().lower())


def _musteri_sahibi(request: Request) -> s.Sahip:
    baglam = izin_iste(request, s.IZIN)
    return s.Sahip(
        yonetici=False,
        hesap=baglam.hesap_email,
        kisi=baglam.kisi_email,
        izinler=frozenset(baglam.izinler),
        sahip_rolu=baglam.rol == "sahip",
    )


def _site() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


def _hiz(sinir: HizSiniri, sahip: s.Sahip) -> None:
    if not sinir.izin_var_mi(sahip.kisi or sahip.hesap or "?"):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"})


def _uclari_kur(r: APIRouter, sahip_bul: Callable[[Request], s.Sahip]) -> None:
    @r.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        izinli = set(s.kullanilabilir_kapsamlar(sahip))
        return {
            "sahip_tur": sahip.sahip_tur,
            "hesap": sahip.hesap,
            "kapsamlar": [
                {"anahtar": k.anahtar, "yazma": k.yazma, "yalniz_ajans": k.yalniz_ajans, "izinli": k.anahtar in izinli}
                for k in s.KAPSAMLAR
                if sahip.yonetici or not k.yalniz_ajans
            ],
            "olaylar": w.olay_katalogu(sahip.yonetici),
            "anahtar_siniri": await s.anahtar_siniri(db, sahip),
            "anahtar_sayisi": await s.etkin_anahtar_sayisi(db, sahip),
            "webhook_siniri": await w.webhook_siniri(db, sahip),
            "webhook_sayisi": len(await w.uclar(db, sahip)),
            "dakika_siniri": await s.dakika_siniri_ust(db, sahip),
            "onerilen_ajans_suresi_gun": s.ONERILEN_AJANS_SURESI_GUN,
            "en_cok_deneme": w.EN_COK_DENEME,
            "pasif_esigi": w.OTOMATIK_PASIF_ESIGI,
            "api_taban": f"{_site()}/api/public/v1",
            "mcp_url": f"{_site()}/api/public/v1/mcp",
            "openapi_url": f"{_site()}/api/public/v1/openapi.json",
        }

    @r.get("/anahtarlar")
    async def anahtar_listesi(request: Request, hepsi: bool = Query(False), db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        return {"items": [s.anahtar_sozlugu(a) for a in await s.anahtarlar(db, sahip, hepsi=hepsi)]}

    @r.post("/anahtarlar")
    async def anahtar_olustur(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        _hiz(_olusturma_hizi, sahip)
        ham, satir = await s.anahtar_olustur(db, sahip, govde)
        logger.info("API anahtarı oluşturuldu: id=%s önek=%s sahip=%s", satir.id, satir.onek, sahip.sahip_tur)
        return {"anahtar": s.anahtar_sozlugu(satir), "ham_anahtar": ham}

    @r.post("/anahtarlar/{anahtar_id}/iptal")
    async def anahtar_iptal(anahtar_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        satir = await s.anahtar_bul(db, sahip, anahtar_id)
        return s.anahtar_sozlugu(await s.anahtar_iptal(db, satir, sahip.kisi))

    @r.get("/webhooklar")
    async def uc_listesi(request: Request, hepsi: bool = Query(False), db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        return {"items": [w.uc_sozlugu(u, b) for u, b in await w.uclar(db, sahip, hepsi=hepsi)]}

    @r.post("/webhooklar")
    async def uc_olustur(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        _hiz(_olusturma_hizi, sahip)
        gizli, uc = await w.uc_olustur(db, sahip, govde)
        return {"uc": w.uc_sozlugu(uc), "gizli": gizli}

    @r.put("/webhooklar/{uc_id}")
    async def uc_guncelle(uc_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        uc = await w.uc_bul(db, sahip, uc_id)
        return w.uc_sozlugu(await w.uc_guncelle(db, sahip, uc, govde))

    @r.delete("/webhooklar/{uc_id}")
    async def uc_sil(uc_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        uc = await w.uc_bul(db, sahip, uc_id)
        await w.uc_sil(db, uc)
        return {"silindi": uc_id}

    @r.post("/webhooklar/{uc_id}/gizli-yenile")
    async def gizli_yenile(uc_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        _hiz(_olusturma_hizi, sahip)
        uc = await w.uc_bul(db, sahip, uc_id)
        gizli = await w.gizli_yenile(db, uc)
        return {"uc": w.uc_sozlugu(uc), "gizli": gizli}

    @r.post("/webhooklar/{uc_id}/test")
    async def test_gonder(uc_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        _hiz(_gonderim_hizi, sahip)
        uc = await w.uc_bul(db, sahip, uc_id)
        return await w.test_gonder(db, uc, sahip.kisi)

    @r.get("/webhooklar/{uc_id}/teslimatlar")
    async def teslimat_listesi(
        uc_id: int,
        request: Request,
        limit: int = Query(25, ge=1, le=100),
        once: Optional[int] = Query(None, ge=1),
        durum: Optional[str] = Query(None, pattern="^(bekliyor|basarili|vazgecildi|atlandi)$"),
        db: AsyncSession = Depends(get_db),
    ):
        sahip = sahip_bul(request)
        uc = await w.uc_bul(db, sahip, uc_id)
        liste, sonraki = await w.teslimatlar(db, uc, limit=limit, once=once, durum=durum)
        return {"items": liste, "sonraki_once": sonraki}

    @r.post("/webhooklar/{uc_id}/teslimatlar/{teslimat_id}/yeniden-gonder")
    async def yeniden_gonder(uc_id: int, teslimat_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        _hiz(_gonderim_hizi, sahip)
        uc = await w.uc_bul(db, sahip, uc_id)
        t = await w.teslimat_bul(db, uc, teslimat_id)
        return await w.yeniden_gonder(db, t)


_uclari_kur(yonetici_router, _yonetici_sahibi)
_uclari_kur(musteri_router, _musteri_sahibi)

router = (yonetici_router, musteri_router)
