"""Faz 2F — E-postadan destek talebi uçları.

Açık (imzalı)  POST /api/v1/destek/eposta-gelen          genel: HMAC imzalı JSON
               POST /api/v1/destek/eposta-gelen/resend   Resend `email.received` (Svix imzası)
Yönetici       GET  /api/v1/destek/gelen-epostalar       son 200 kayıt (durum/gönderen süzgeci)
               GET/PUT /api/v1/destek/eposta-ayarlari    kurulum durumu (değer DEĞİL, var/yok),
                                                         webhook adresleri, gelen adres
Oturum         GET  /api/v1/destek/eposta-bilgisi        gelen adres tanımlı mı (müşteri ipucu)

Hata ve yeniden deneme kararı
-----------------------------
İşleme İSTEK İÇİNDE yapılıyor (arka plan görevi değil): ücretsiz sunucu
yanıttan sonra uykuya geçebilir, arka plandaki iş yarıda kalırdı. Sonuç:
* İmza yanlış/eski → 401 (sağlayıcı yeniden dener ama geçmez; kayıt yok).
* Anahtar tanımlı değil → 503 "kapali".
* Geçici hata (Resend API'ye ulaşılamadı, ek indirilemedi, depo yazılamadı)
  ve beklenmeyen hata → kayıt "hata" durumunda kalır, uç 503/500 döner;
  sağlayıcı (Svix) üstel geri çekilmeyle yeniden dener. Yeniden deneme
  güvenli: `message_id` benzersiz, "hata"daki ileti yeniden işlenir,
  "islendi"deki ikinci kez işlenmez (talep ve mesaj yazımı tek işlemde).
* Kalıcı ret (otomatik yanıt, spam sınırı, gönderen yok) → 200 "yoksayildi".
"""

import json
import logging
import os
from typing import Any, Dict, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from fastapi.responses import JSONResponse
from models.destek_eposta import GelenEpostalar
from services import eposta_gelen as servis
from services.destek_talep import GELEN_ADRES_AYARI, gelen_adres
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

acik_router = APIRouter(prefix="/api/v1/destek", tags=["destek-eposta"])
yonetici_router = APIRouter(prefix="/api/v1/destek", tags=["destek-eposta"])

GOVDE_SINIRI = 40 * 1024 * 1024
GENEL_ANAHTAR = "EPOSTA_GELEN_ANAHTARI"
RESEND_ANAHTAR = "RESEND_GELEN_IMZA_ANAHTARI"


def _env(ad: str) -> str:
    return (os.environ.get(ad) or "").strip()


def _yonetici_iste(request: Request) -> None:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})


async def _ham_govde(request: Request) -> bytes:
    uzunluk = request.headers.get("content-length")
    if uzunluk and uzunluk.isdigit() and int(uzunluk) > GOVDE_SINIRI:
        raise HTTPException(status_code=413, detail={"kod": "govde_buyuk"})
    govde = await request.body()
    if len(govde) > GOVDE_SINIRI:
        raise HTTPException(status_code=413, detail={"kod": "govde_buyuk"})
    return govde


async def _isle_yanit(db: AsyncSession, ileti: Dict[str, Any], kaynak: str) -> JSONResponse:
    try:
        sonuc = await servis.isle(db, ileti, kaynak=kaynak)
    except servis.GeciciHata as h:
        return JSONResponse(status_code=503, content={"durum": "hata", "neden": str(h), "yeniden_dene": True})
    except Exception:  # noqa: BLE001 - kayıt "hata"; sağlayıcı yeniden denesin
        return JSONResponse(status_code=500, content={"durum": "hata", "yeniden_dene": True})
    return JSONResponse(status_code=200, content=sonuc)


# ---------------------------------------------------------------------------
# Genel uç (HMAC)
# ---------------------------------------------------------------------------
@acik_router.post("/eposta-gelen")
async def eposta_gelen(request: Request, db: AsyncSession = _Depends(get_db)):
    anahtar = _env(GENEL_ANAHTAR)
    if not anahtar:
        raise HTTPException(status_code=503, detail={"kod": "kapali"})
    ham = await _ham_govde(request)
    if not servis.hmac_dogrula(anahtar, request.headers.get("x-mk-zaman"), request.headers.get("x-mk-imza"), ham):
        raise HTTPException(status_code=401, detail={"kod": "imza_gecersiz"})
    try:
        govde = json.loads(ham.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400, detail={"kod": "gecersiz_json"})
    if not isinstance(govde, dict):
        raise HTTPException(status_code=400, detail={"kod": "gecersiz_json"})
    # Güvenlik: genel uçta ek yalnız gövdede (base64). Dışarıdan verilen
    # adresi sunucu indirmez (SSRF: iç ağ adreslerine istek attırılamasın).
    ekler = []
    for e in govde.get("ekler") or []:
        if isinstance(e, dict):
            e = {k: v for k, v in e.items() if k not in ("indirme_url", "icerik_bytes")}
            ekler.append(e)
    govde["ekler"] = ekler
    return await _isle_yanit(db, govde, "genel")


# ---------------------------------------------------------------------------
# Resend webhook (Svix imzası)
# ---------------------------------------------------------------------------
@acik_router.post("/eposta-gelen/resend")
async def eposta_gelen_resend(request: Request, db: AsyncSession = _Depends(get_db)):
    gizli = _env(RESEND_ANAHTAR)
    if not gizli:
        raise HTTPException(status_code=503, detail={"kod": "kapali"})
    ham = await _ham_govde(request)
    if not servis.svix_dogrula(
        gizli,
        request.headers.get("svix-id"),
        request.headers.get("svix-timestamp"),
        request.headers.get("svix-signature"),
        ham,
    ):
        raise HTTPException(status_code=401, detail={"kod": "imza_gecersiz"})
    try:
        olay = json.loads(ham.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400, detail={"kod": "gecersiz_json"})
    if not isinstance(olay, dict) or olay.get("type") != "email.received" or not isinstance(olay.get("data"), dict):
        # Aynı webhook'a başka olay türü bağlanmış olabilir: sessizce kabul.
        return {"durum": "yoksayildi", "neden": "olay_turu"}
    veri = olay["data"]

    # Zaten işlenmiş ileti için Resend API'ye gitme (yeniden gönderim).
    mid = servis.message_id_duzelt(veri.get("message_id"))
    if mid:
        onceki = (await db.execute(select(GelenEpostalar).where(GelenEpostalar.message_id == mid))).scalars().first()
        if onceki is not None and onceki.durum in ("islendi", "yoksayildi"):
            return {"durum": onceki.durum, "neden": onceki.neden, "talep_id": onceki.talep_id, "tekrar": True}
    try:
        ileti = await servis.resend_iletisi(veri)
    except ValueError:
        raise HTTPException(status_code=400, detail={"kod": "gecersiz_olay"})
    except servis.GeciciHata as h:
        logger.warning("Resend iletisi alınamadı: %s", h)
        return JSONResponse(status_code=503, content={"durum": "hata", "neden": str(h), "yeniden_dene": True})
    if mid and not ileti.get("message_id"):
        ileti["message_id"] = mid
    return await _isle_yanit(db, ileti, "resend")


# ---------------------------------------------------------------------------
# Yönetici: kayıtlar ve kurulum
# ---------------------------------------------------------------------------
def _kayit(k: GelenEpostalar) -> Dict[str, Any]:
    return {
        "id": k.id,
        "gonderen": k.gonderen,
        "konu": k.konu,
        "durum": k.durum,
        "neden": k.neden,
        "talep_id": k.talep_id,
        "kaynak": k.kaynak,
        "ozet": k.ozet,
        "ek_sayisi": int(k.ek_sayisi or 0),
        "created_at": servis._utc(k.created_at).isoformat() if k.created_at else None,  # type: ignore[union-attr]
    }


@yonetici_router.get("/gelen-epostalar")
async def gelen_epostalar(
    request: Request,
    durum: Optional[str] = Query(None),
    gonderen: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=200),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    sorgu = select(GelenEpostalar).order_by(GelenEpostalar.id.desc())
    if durum:
        if durum not in ("isleniyor", "islendi", "yoksayildi", "hata"):
            raise HTTPException(status_code=400, detail={"kod": "gecersiz_durum"})
        sorgu = sorgu.where(GelenEpostalar.durum == durum)
    if gonderen:
        sorgu = sorgu.where(GelenEpostalar.gonderen == gonderen.strip().lower()[:254])
    satirlar = (await db.execute(sorgu.limit(limit))).scalars().all()
    return [_kayit(k) for k in satirlar]


def _arka_uc_adresi(request: Request) -> str:
    adres = _env("PYTHON_BACKEND_URL")
    if adres.startswith("http"):
        return adres.rstrip("/")
    return str(request.base_url).rstrip("/")


async def _ayarlar(db: AsyncSession, request: Request) -> Dict[str, Any]:
    kok = _arka_uc_adresi(request)
    return {
        # Değerler ASLA dönmüyor; yalnız tanımlı olup olmadıkları.
        "genel_anahtar_tanimli": bool(_env(GENEL_ANAHTAR)),
        "resend_imza_tanimli": bool(_env(RESEND_ANAHTAR)),
        "resend_api_tanimli": bool(_env("RESEND_API_KEY")),
        "gelen_adres": await gelen_adres(db),
        "webhook": {
            "genel": f"{kok}/api/v1/destek/eposta-gelen",
            "resend": f"{kok}/api/v1/destek/eposta-gelen/resend",
        },
        "sinirlar": {
            "saatlik": servis.SAATLIK_SINIR,
            "ek_mb": servis.EK_SINIRI_BAYT // (1024 * 1024),
            "ek_sayisi": servis.EK_SAYISI_SINIRI,
        },
    }


@yonetici_router.get("/eposta-ayarlari")
async def eposta_ayarlari(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return await _ayarlar(db, request)


@yonetici_router.put("/eposta-ayarlari")
async def eposta_ayarlari_yaz(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = _Depends(get_db)):
    from models.site_settings import Site_settings

    _yonetici_iste(request)
    _, adres = servis.adres_coz(govde.get("gelen_adres") or "")
    ham = str(govde.get("gelen_adres") or "").strip()
    if ham and not adres:
        raise HTTPException(status_code=400, detail={"kod": "gecersiz_eposta"})
    satir = (await db.execute(select(Site_settings).where(Site_settings.setting_key == GELEN_ADRES_AYARI))).scalars().first()
    if satir:
        satir.setting_value = adres
    else:
        db.add(Site_settings(setting_key=GELEN_ADRES_AYARI, setting_value=adres, group_name="destek", label="Destek: gelen e-posta adresi"))
    await db.commit()
    return await _ayarlar(db, request)


@yonetici_router.get("/eposta-bilgisi")
async def eposta_bilgisi(request: Request, db: AsyncSession = _Depends(get_db)):
    """Müşteri paneli ipucu: talebe e-postayla da yanıt verilebilir mi."""
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    adres = await gelen_adres(db)
    # Resend imzası ya da genel anahtar tanımlı değilse e-posta alınamıyor:
    # ipucu gösterilmesin (müşteri boşluğa yazmasın).
    acik = bool(adres) and bool(_env(RESEND_ANAHTAR) or _env(GENEL_ANAHTAR))
    return {"acik": acik, "gelen_adres": adres if acik else ""}


router = (acik_router, yonetici_router)
