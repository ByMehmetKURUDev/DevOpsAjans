"""Bildirim tercihleri ve Web Push uçları (Faz 1D).

Kim ne yapıyor
--------------
* Herkes: `GET /api/v1/bildirim/push/anahtar` — tarayıcının abone olmak
  için ihtiyaç duyduğu VAPID açık anahtarı (yoksa `{acik: false}`).
* Oturumlu kişi (müşteri ya da yönetici): kendi tercihleri
  (`/tercihlerim`), kendi tarayıcı abonelikleri (`/push/abone`) ve kendine
  deneme bildirimi (`/push/dene`). E-posta her zaman JETONDAN alınıyor.
* Yönetici: olay × kanal matrisi (`/matris`).

Kural (ayrıntı `services/bildirim_tercih.py`): yönetici matrisi izin
vermiyorsa kişi açamaz; izin veriyorsa kişi kapatabilir; panel içi
kapatılamaz.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from models.bildirim import NotificationPrefs, PushSubscriptions  # noqa: F401 — tabloları kaydeder
from models.notifications import Notifications
from pydantic import BaseModel, Field
from services import bildirim_tercih as bt
from services import web_push
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bildirim", tags=["bildirim"])

#: Bir kişinin tutulabilecek en çok tarayıcı aboneliği; fazlası en eskiden silinir.
KISI_BASINA_ABONELIK = 20


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class AbonelikAnahtarlari(BaseModel):
    p256dh: str = Field(..., min_length=20, max_length=200)
    auth: str = Field(..., min_length=8, max_length=100)


class AbonelikGirdisi(BaseModel):
    """Tarayıcıdaki `PushSubscription.toJSON()` ile aynı biçim."""

    endpoint: str = Field(..., min_length=10, max_length=2000)
    keys: AbonelikAnahtarlari


class AbonelikSilGirdisi(BaseModel):
    endpoint: str = Field(..., min_length=10, max_length=2000)


class TercihGirdisi(BaseModel):
    tercih: Dict[str, Dict[str, bool]] = Field(default_factory=dict)
    sessiz_saatler: Optional[Dict[str, str]] = None


class MatrisGirdisi(BaseModel):
    matris: Dict[str, Any]


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _oturum_iste(request: Request):
    """(e-posta, rol) — rol "admin" ya da "client"."""
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    eposta = (kullanici.email or "").strip().lower()
    if not eposta:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesabınızda e-posta adresi tanımlı değil")
    return eposta, ("admin" if yonetici else "client")


def _yonetici_iste(request: Request) -> str:
    eposta, rol = _oturum_iste(request)
    if rol != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
    return eposta


def _endpoint_dogrula(endpoint: str) -> str:
    temiz = endpoint.strip()
    adres = urlparse(temiz)
    if adres.scheme != "https" or not adres.netloc:
        raise HTTPException(status_code=400, detail="Geçersiz abonelik adresi")
    return temiz


async def _abonelik_sayisi(db: AsyncSession, eposta: Optional[str] = None) -> int:
    sorgu = select(func.count()).select_from(PushSubscriptions)
    if eposta:
        sorgu = sorgu.where(PushSubscriptions.eposta == eposta)
    return int(await db.scalar(sorgu) or 0)


def _push_bilgisi() -> Dict[str, Any]:
    ayar = web_push.vapid_ayarlari()
    return {"yapilandirildi": ayar is not None, "anahtar": ayar["acik"] if ayar else None}


# --------------------------------------------------------------------------
# Herkese açık
# --------------------------------------------------------------------------
@router.get("/push/anahtar")
async def push_anahtari():
    ayar = web_push.vapid_ayarlari()
    if ayar is None:
        return {"acik": False}
    return {"acik": True, "anahtar": ayar["acik"]}


# --------------------------------------------------------------------------
# Oturumlu kişi
# --------------------------------------------------------------------------
@router.post("/push/abone")
async def push_abone_ol(girdi: AbonelikGirdisi, request: Request, db: AsyncSession = _Depends(get_db)):
    eposta, _ = _oturum_iste(request)
    if not web_push.push_yapilandirildi():
        raise HTTPException(status_code=409, detail="Tarayıcı bildirimleri sunucuda yapılandırılmamış")
    endpoint = _endpoint_dogrula(girdi.endpoint)

    sonuc = await db.execute(select(PushSubscriptions).where(PushSubscriptions.endpoint == endpoint))
    kayit = sonuc.scalars().first()
    ua = web_push.ua_ozeti(request.headers.get("user-agent"))
    if kayit is None:
        kayit = PushSubscriptions(endpoint=endpoint, hata_sayisi=0)
        db.add(kayit)
    # Aynı tarayıcıda başka hesapla giriş yapılıp yeniden abone olunduysa
    # tarayıcı artık bu kişinin: bildirimler son giriş yapana gitsin.
    kayit.eposta = eposta
    kayit.p256dh = girdi.keys.p256dh.strip()
    kayit.auth = girdi.keys.auth.strip()
    kayit.user_agent = ua
    kayit.hata_sayisi = 0
    await db.flush()

    # Sınır: en eski abonelikler silinir.
    eskiler = await db.execute(
        select(PushSubscriptions)
        .where(PushSubscriptions.eposta == eposta)
        .order_by(PushSubscriptions.id.desc())
        .offset(KISI_BASINA_ABONELIK)
    )
    for eski in eskiler.scalars().all():
        await db.delete(eski)
    await db.commit()
    return {"ok": True, "abonelik_sayisi": await _abonelik_sayisi(db, eposta)}


@router.delete("/push/abone")
async def push_abonelikten_cik(
    request: Request,
    girdi: Optional[AbonelikSilGirdisi] = Body(None),
    endpoint: Optional[str] = Query(None, max_length=2000),
    db: AsyncSession = _Depends(get_db),
):
    """Yalnız kendi aboneliği; başkasınınki "bulunamadı" (varlığı sızmasın).

    Adres gövdede gelir; SDK'sı DELETE gövdesi gönderemeyen istemci için
    `?endpoint=` de kabul ediliyor.
    """
    eposta, _ = _oturum_iste(request)
    hedef = ((girdi.endpoint if girdi else endpoint) or "").strip()
    if not hedef:
        raise HTTPException(status_code=400, detail="Abonelik adresi gerekli")
    sonuc = await db.execute(
        select(PushSubscriptions).where(
            PushSubscriptions.endpoint == hedef,
            PushSubscriptions.eposta == eposta,
        )
    )
    kayit = sonuc.scalars().first()
    if kayit is None:
        raise HTTPException(status_code=404, detail="Abonelik bulunamadı")
    await db.delete(kayit)
    await db.commit()
    return {"ok": True, "abonelik_sayisi": await _abonelik_sayisi(db, eposta)}


@router.post("/push/dene")
async def push_dene(request: Request, db: AsyncSession = _Depends(get_db)):
    """Kişinin kendi tarayıcılarına deneme bildirimi; sonuç gönderim kaydına da yazılır."""
    eposta, rol = _oturum_iste(request)
    baslik = "mehmetkuru.dev"
    govde = "Deneme bildirimi — bu tarayıcıda bildirimler çalışıyor."
    baglanti = "/admin" if rol == "admin" else "/client?sekme=profile"
    durum, ayrinti = await web_push.push_gonder(db, eposta, baslik, govde, baglanti)
    db.add(
        Notifications(
            recipient_email=eposta,
            recipient_role=rol,
            event_type="test",
            title=baslik,
            body=govde,
            link=baglanti,
            channel="push",
            delivery_status=durum,
            delivery_detail=ayrinti,
            # Çanda görünmesin: deneme kaydı zaten okunmuş sayılıyor.
            read_at=datetime.now(),
            created_at=datetime.now(),
        )
    )
    await db.commit()
    return {"durum": durum, "ayrinti": ayrinti}


async def _tercih_yaniti(db: AsyncSession, eposta: str, rol: str) -> Dict[str, Any]:
    matris = await bt.matris_oku(db)
    kisi = await bt.tercih_oku(db, eposta)
    olaylar: List[Dict[str, Any]] = []
    for olay in bt.olay_listesi(rol):
        izin = {k: bool(matris[rol][olay].get(k, True)) for k in bt.KANALLAR}
        acik = {k: bt.izinli_mi(matris, kisi, rol, olay, k) for k in bt.KANALLAR}
        olaylar.append({"olay": olay, "izin": izin, "acik": acik})
    return {
        "rol": rol,
        "kanallar": list(bt.KANALLAR),
        "kanal_durumu": await bt.kanal_durumlari(db),
        "olaylar": olaylar,
        "sessiz_saatler": kisi.sessiz,
        "push": {**_push_bilgisi(), "abonelik_sayisi": await _abonelik_sayisi(db, eposta)},
    }


@router.get("/tercihlerim")
async def tercihlerim(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta, rol = _oturum_iste(request)
    return await _tercih_yaniti(db, eposta, rol)


@router.put("/tercihlerim")
async def tercihlerimi_kaydet(girdi: TercihGirdisi, request: Request, db: AsyncSession = _Depends(get_db)):
    """Yalnız KAPATILAN hücreler saklanıyor; açık hücre matrisi izliyor.

    Böylece yönetici sonradan bir kanalı açarsa, kişinin kapatmadığı her yer
    kendiliğinden açılıyor; kişinin "açık" demesi matrisi aşamıyor.
    """
    eposta, rol = _oturum_iste(request)
    kapali = {
        olay: {k: False for k, v in hucre.items() if v is False}
        for olay, hucre in (girdi.tercih or {}).items()
    }
    await bt.tercih_yaz(db, eposta, {o: h for o, h in kapali.items() if h}, girdi.sessiz_saatler)
    return await _tercih_yaniti(db, eposta, rol)


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
async def _matris_yaniti(db: AsyncSession, matris: Dict[str, Any]) -> Dict[str, Any]:
    kisi_sayisi = int(
        await db.scalar(select(func.count(func.distinct(PushSubscriptions.eposta)))) or 0
    )
    return {
        "matris": matris,
        "kanallar": list(bt.KANALLAR),
        "olaylar": [
            {"olay": o, "roller": list(b["roller"]), "tetikleniyor": bool(b["tetikleniyor"])}
            for o, b in bt.OLAYLAR.items()
        ],
        "kanal_durumu": await bt.kanal_durumlari(db),
        "push": {
            **_push_bilgisi(),
            "abonelik_sayisi": await _abonelik_sayisi(db),
            "kisi_sayisi": kisi_sayisi,
        },
    }


@router.get("/matris")
async def matris_getir(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return await _matris_yaniti(db, await bt.matris_oku(db))


@router.put("/matris")
async def matris_kaydet(girdi: MatrisGirdisi, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return await _matris_yaniti(db, await bt.matris_yaz(db, girdi.matris))
