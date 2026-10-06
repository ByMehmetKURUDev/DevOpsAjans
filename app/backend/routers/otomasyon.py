"""Faz 4W — otomasyon kuralları ("şu olunca bunu yap") ve çalıştırma günlüğü.

Yönetici (`/api/v1/otomasyon/yonetim`) — ajansın kuralları (bütün hesapların olaylarında
çalışır; CRM ve destek talebi eylemleri yalnız burada).
Müşteri (`/api/v1/otomasyonlarim`; modül `otomasyon` açık + hesap izni `otomasyon`) —
yalnız etkin hesabın kuralları; yalnız kendi hesabının (müşteriye görünen) olayları.

  GET    "/meta"                       olaylar + alan şeması (özel alanlar dahil), işleçler, eylemler,
                                         şablonlar, sınırlar, seçilebilir webhook/proje/ekip/CRM aşaması
  GET    "/ornek-baglam?tetik="        kuru çalıştırma için örnek olay verisi
  GET    "/kurallar"                   liste
  POST   "/kurallar"                   {ad, aciklama?, aktif?, tetik, kosullar{baglac, kosullar[]}, eylemler[]}
  POST   "/kurallar/sablondan"         {sablon, metinler?} — hazır şablondan tek tıkla
  GET    "/kurallar/{id}"              tek kural
  PUT    "/kurallar/{id}"              kısmi güncelle (tetik değişirse koşul/eylemler yeniden denetlenir)
  DELETE "/kurallar/{id}"              sil (çöp kutusuna)
  POST   "/kurallar/{id}/test"         {baglam? | calisma_id?} — KURU çalıştırma (eylem YAPILMAZ)
  POST   "/test"                       {kural, baglam? | calisma_id?} — kaydedilmemiş kuralın kuru çalıştırması
  GET    "/gunluk"                     ?kural_id=&durum=&once=&limit= — çalıştırmalar (30 gün)
  GET    "/gunluk/{id}"                tek çalıştırma

Yalnız yönetici (Faz 7O — Otomasyon › Sistem; `services/haftalik_ozet.py`):
  GET    "/haftalik-ozet"              durum: açık mı (bildirim matrisi), son gönderim, bu hafta, sonraki, e-posta kanalı
  GET    "/haftalik-ozet/onizle"       özetin ŞU ANKİ içeriği (JSON; gönderilmez, iz yazılmaz)
  PUT    "/haftalik-ozet"              {acik: bool} — matristeki yönetici × haftalik_ozet × e-posta hücresi
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.routing import APIRoute
from models.otomasyon import OtomasyonCalismalari, OtomasyonKurallari
from services import otomasyon as s
from services import otomasyon_kural as kural
from services import ozel_alanlar as oz
from services.api_erisimi import Sahip
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri

logger = logging.getLogger(__name__)

_test_hizi = HizSiniri(30, 60.0)
_yazma_hizi = HizSiniri(30, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    _test_hizi.temizle()
    _yazma_hizi.temizle()


class _Rota(APIRoute):
    """Servis hatalarını panelin alıştığı `{"detail": {"kod": ...}}` biçimine çevirir."""

    def get_route_handler(self) -> Callable:
        asil = super().get_route_handler()

        async def isleyici(request: Request) -> Response:
            try:
                return await asil(request)
            except kural.KuralHatasi as h:
                raise HTTPException(status_code=h.durum, detail=h.detay())

        return isleyici


yonetici_router = APIRouter(
    prefix="/api/v1/otomasyon/yonetim",
    tags=["otomasyon"],
    dependencies=[Depends(yonetici_gerekli)],
    route_class=_Rota,
)
musteri_router = APIRouter(
    prefix="/api/v1/otomasyonlarim",
    tags=["otomasyon"],
    dependencies=[Depends(modul_gerekli(s.MODUL)), Depends(izin_gerekli(s.IZIN))],
    route_class=_Rota,
)


def _yonetici_sahibi(request: Request) -> Sahip:
    kullanici, _ = _yonetici_mi(request)
    return Sahip(yonetici=True, hesap=None, kisi=(getattr(kullanici, "email", "") or "").strip().lower())


def _musteri_sahibi(request: Request) -> Sahip:
    baglam = izin_iste(request, s.IZIN)
    return Sahip(yonetici=False, hesap=baglam.hesap_email, kisi=baglam.kisi_email, izinler=frozenset(baglam.izinler),
                 sahip_rolu=baglam.rol == "sahip")


def _hiz(sinir: HizSiniri, sahip: Sahip) -> None:
    if not sinir.izin_var_mi(sahip.kisi or sahip.hesap or "?"):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"})


# ---------------------------------------------------------------------------
# Doğrulama bağlamı (veritabanından seçilebilir değerler)
# ---------------------------------------------------------------------------
async def _ekip(db: AsyncSession) -> Set[str]:
    from models.staff import Staff
    from services.notify import admin_recipients

    ekip = {str(a.get("email") or "").strip().lower() for a in await admin_recipients(db)}
    for e, aktif in (await db.execute(select(Staff.email, Staff.aktif))).all():
        if e and aktif is not False:
            ekip.add(e.strip().lower())
    return {e for e in ekip if e}


async def _projeler(db: AsyncSession, sahip: Sahip, idler: Optional[List[int]] = None, limit: int = 500) -> List[Any]:
    from models.projects import Projects

    sorgu = select(Projects.id, Projects.title, Projects.client_email)
    if not sahip.yonetici:
        sorgu = sorgu.where(func.lower(Projects.client_email) == sahip.hesap)
    if idler is not None:
        if not idler:
            return []
        sorgu = sorgu.where(Projects.id.in_(idler))
    return list((await db.execute(sorgu.order_by(Projects.id.desc()).limit(limit))).all())


async def _webhook_uclari(db: AsyncSession, sahip: Sahip) -> List[Any]:
    from models.api_erisimi import WebhookUcNoktalari

    return list((await db.execute(
        select(WebhookUcNoktalari.id, WebhookUcNoktalari.url, WebhookUcNoktalari.aktif, WebhookUcNoktalari.aciklama)
        .where(sahip.sahip_kosulu(WebhookUcNoktalari)).order_by(WebhookUcNoktalari.id.desc()).limit(100)
    )).all())


async def _crm_asamalari(db: AsyncSession) -> List[Dict[str, Any]]:
    from services import crm

    await crm.asamalari_hazirla(db)
    return [crm.asama_sozlugu(a) for a in await crm.asamalar(db)]


async def _dogrulama(db: AsyncSession, sahip: Sahip, govde: Dict[str, Any]) -> kural.DogrulamaBaglami:
    b = kural.DogrulamaBaglami(ajans=sahip.yonetici)
    b.ozel = await oz.anahtar_haritasi(db, yalniz_gorunur=not sahip.yonetici)
    eylemler = govde.get("eylemler") if isinstance(govde.get("eylemler"), list) else []
    proje_idler = []
    for e in eylemler:
        if isinstance(e, dict) and e.get("tur") == "gorev" and str(e.get("proje") or "").isdigit():
            proje_idler.append(int(str(e.get("proje"))))
    b.projeler = {int(r[0]) for r in await _projeler(db, sahip, proje_idler)} if proje_idler else set()
    b.webhook_uclari = {int(r[0]) for r in await _webhook_uclari(db, sahip)}
    if sahip.yonetici:
        b.ekip = await _ekip(db)
        b.crm_asamalari = {a["anahtar"] for a in await _crm_asamalari(db)}
    return b


async def _kural(db: AsyncSession, sahip: Sahip, kural_id: int) -> OtomasyonKurallari:
    k = (
        await db.execute(select(OtomasyonKurallari).where(OtomasyonKurallari.id == kural_id, sahip.sahip_kosulu(OtomasyonKurallari)))
    ).scalars().first()
    if k is None:
        raise HTTPException(status_code=404, detail={"kod": "kural_yok"})
    return k


async def _kural_sayisi(db: AsyncSession, sahip: Sahip) -> int:
    return int((await db.execute(select(func.count(OtomasyonKurallari.id)).where(sahip.sahip_kosulu(OtomasyonKurallari)))).scalar() or 0)


async def _olustur(db: AsyncSession, sahip: Sahip, govde: Dict[str, Any]) -> Dict[str, Any]:
    sinir = await s.kural_siniri(db, sahip)
    if await _kural_sayisi(db, sahip) >= sinir:
        raise HTTPException(status_code=409, detail={"kod": "kural_siniri", "sinir": sinir})
    temiz = kural.kural_dogrula(govde, await _dogrulama(db, sahip, govde))
    k = OtomasyonKurallari(
        sahip_tur=sahip.sahip_tur, hesap_email=None if sahip.yonetici else sahip.hesap, olusturan=sahip.kisi or None,
        calisma_sayisi=0, **temiz,
    )
    db.add(k)
    await db.commit()
    await db.refresh(k)
    s.onbellegi_temizle()
    return kural.kural_sozlugu(k)


def _uclari_kur(r: APIRouter, sahip_bul: Callable[[Request], Sahip]) -> None:
    @r.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        ajans = sahip.yonetici
        ozel = await oz.anahtar_haritasi(db, yalniz_gorunur=not ajans)
        dakika, saat = await s.hiz_sinirlari(db, sahip.sahip_tur, sahip.hesap)
        yanit: Dict[str, Any] = {
            "sahip_tur": sahip.sahip_tur,
            "olaylar": [
                {**o, "sema": kural.sema(o["anahtar"], ajans, ozel)} for o in kural.olay_katalogu(ajans)
            ],
            "islecler": list(kural.ISLECLER),
            "degersiz_islecler": sorted(kural.DEGERSIZ_ISLECLER),
            "eylemler": [e for e in kural.EYLEM_TURLERI if ajans or e in kural.MUSTERI_EYLEMLERI],
            "oncelikler": list(kural.ONCELIKLER),
            "aktivite_turleri": list(kural.AKTIVITE_TURLERI),
            "bekleme_birimleri": list(kural.BEKLEME_BIRIMLERI),
            "sablonlar": kural.sablon_katalogu(ajans),
            "sinirlar": {
                "kural": await s.kural_siniri(db, sahip), "kural_sayisi": await _kural_sayisi(db, sahip),
                "eylem": kural.EN_COK_EYLEM, "kosul": kural.EN_COK_KOSUL, "derinlik": kural.EN_COK_DERINLIK,
                "dakika": dakika, "saat": saat, "saklama_gun": s.SAKLAMA_SURESI.days,
            },
            "webhook_uclari": [{"id": u[0], "url": u[1], "aktif": bool(u[2]), "aciklama": u[3]} for u in await _webhook_uclari(db, sahip)],
            "projeler": [{"id": p[0], "baslik": p[1], "hesap": (p[2] or "").lower() or None} for p in await _projeler(db, sahip, limit=300)],
        }
        if ajans:
            yanit["ekip"] = sorted(await _ekip(db))
            yanit["crm_asamalari"] = [{"anahtar": a["anahtar"], "ad": a.get("ad"), "ceviriler": a.get("ceviriler")}
                                      for a in await _crm_asamalari(db)]
        return yanit

    @r.get("/ornek-baglam")
    async def ornek_baglam(request: Request, tetik: str = Query(...), db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        olay = kural.OLAY_SOZLUGU.get(tetik)
        if olay is None or (not sahip.yonetici and not olay.musteri):
            raise HTTPException(status_code=400, detail={"kod": "tetik_gecersiz"})
        ozel = await oz.anahtar_haritasi(db, yalniz_gorunur=not sahip.yonetici)
        return {"baglam": kural.ornek_baglam(tetik, sahip.yonetici, ozel)}

    @r.get("/kurallar")
    async def kurallar(request: Request, db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        liste = (
            await db.execute(select(OtomasyonKurallari).where(sahip.sahip_kosulu(OtomasyonKurallari)).order_by(OtomasyonKurallari.id.desc()).limit(500))
        ).scalars().all()
        return {"items": [kural.kural_sozlugu(k) for k in liste]}

    @r.post("/kurallar")
    async def olustur(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        _hiz(_yazma_hizi, sahip)
        return await _olustur(db, sahip, govde)

    @r.post("/kurallar/sablondan")
    async def sablondan(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        _hiz(_yazma_hizi, sahip)
        metinler = govde.get("metinler") if isinstance(govde.get("metinler"), dict) else None
        taslak = kural.sablondan_kural(str(govde.get("sablon") or ""), sahip.yonetici, metinler)
        return await _olustur(db, sahip, taslak)

    @r.get("/kurallar/{kural_id}")
    async def tek(kural_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        return kural.kural_sozlugu(await _kural(db, sahip_bul(request), kural_id))

    @r.put("/kurallar/{kural_id}")
    async def guncelle(kural_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        _hiz(_yazma_hizi, sahip)
        k = await _kural(db, sahip, kural_id)
        temiz = kural.kural_dogrula(govde, await _dogrulama(db, sahip, govde), mevcut=k)
        for alan, deger in temiz.items():
            setattr(k, alan, deger)
        await db.commit()
        await db.refresh(k)
        s.onbellegi_temizle()
        return kural.kural_sozlugu(k)

    @r.delete("/kurallar/{kural_id}")
    async def sil(kural_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        k = await _kural(db, sahip, kural_id)
        await db.delete(k)
        await db.commit()
        s.onbellegi_temizle()
        return {"silindi": True, "id": kural_id}

    async def _kuru(sahip: Sahip, db: AsyncSession, temiz: Dict[str, Any], govde: Dict[str, Any], kural_id: Optional[int]):
        _hiz(_test_hizi, sahip)
        calisma_id = govde.get("calisma_id")
        if calisma_id is not None and (isinstance(calisma_id, bool) or not str(calisma_id).isdigit()):
            raise HTTPException(status_code=400, detail={"kod": "calisma_yok"})
        ozel = await oz.anahtar_haritasi(db, yalniz_gorunur=not sahip.yonetici)
        return await s.kuru_calistir(
            db, sahip, temiz, kural_id=kural_id, baglam=govde.get("baglam") if "baglam" in govde else None,
            calisma_id=int(calisma_id) if calisma_id is not None else None, ozel=ozel,
        )

    @r.post("/kurallar/{kural_id}/test")
    async def kayitli_test(kural_id: int, request: Request, govde: Optional[Dict[str, Any]] = Body(None),
                           db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        k = await _kural(db, sahip, kural_id)
        temiz = {"tetik": k.tetik, "kosullar": k.kosullar, "eylemler": k.eylemler, "ad": k.ad}
        return await _kuru(sahip, db, temiz, govde or {}, k.id)

    @r.post("/test")
    async def taslak_test(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        taslak = govde.get("kural")
        if not isinstance(taslak, dict):
            raise HTTPException(status_code=400, detail={"kod": "kural_gerekli"})
        taslak = {**taslak, "ad": taslak.get("ad") or "—"}
        temiz = kural.kural_dogrula(taslak, await _dogrulama(db, sahip, taslak))
        return await _kuru(sahip, db, temiz, govde, None)

    @r.get("/gunluk")
    async def gunluk(
        request: Request,
        kural_id: Optional[int] = Query(None),
        durum: Optional[str] = Query(None),
        once: Optional[int] = Query(None),
        limit: int = Query(30, ge=1, le=100),
        db: AsyncSession = Depends(get_db),
    ):
        sahip = sahip_bul(request)
        items, sonraki = await s.gunluk(db, sahip, kural_id=kural_id, durum=durum, once=once, limit=limit)
        return {"items": items, "sonraki": sonraki}

    @r.get("/gunluk/{calisma_id}")
    async def gunluk_tek(calisma_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        sahip = sahip_bul(request)
        c = (
            await db.execute(
                select(OtomasyonCalismalari).where(
                    OtomasyonCalismalari.id == calisma_id,
                    s._sahip_kosulu_calisma(sahip.sahip_tur, None if sahip.yonetici else sahip.hesap),
                )
            )
        ).scalars().first()
        if c is None:
            raise HTTPException(status_code=404, detail={"kod": "calisma_yok"})
        ad = (await db.execute(select(OtomasyonKurallari.ad).where(OtomasyonKurallari.id == c.kural_id))).scalar()
        return s.calisma_sozlugu(c, ad)


_uclari_kur(yonetici_router, _yonetici_sahibi)
_uclari_kur(musteri_router, _musteri_sahibi)


# ---------------------------------------------------------------------------
# Faz 7O — haftalık özet (yalnız yönetici router'ında; müşteri yolu yok)
# ---------------------------------------------------------------------------
@yonetici_router.get("/haftalik-ozet")
async def haftalik_ozet_durumu(db: AsyncSession = Depends(get_db)):
    from services import haftalik_ozet

    return await haftalik_ozet.durum(db)


@yonetici_router.get("/haftalik-ozet/onizle")
async def haftalik_ozet_onizle(db: AsyncSession = Depends(get_db)):
    from services import haftalik_ozet

    return await haftalik_ozet.ozet_hazirla(db)


@yonetici_router.put("/haftalik-ozet")
async def haftalik_ozet_ayarla(govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    from services import haftalik_ozet

    acik = govde.get("acik") if isinstance(govde, dict) else None
    if not isinstance(acik, bool):
        raise HTTPException(status_code=400, detail={"kod": "acik_gerekli"})
    return await haftalik_ozet.ac_kapat(db, acik)

router = (yonetici_router, musteri_router)
