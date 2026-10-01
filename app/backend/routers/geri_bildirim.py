"""Faz 2B — "Hata bildir": müşteri geri bildirimi, ekran görüntüsü, göreve dönüştürme.

Müşteri  /api/v1/geri-bildirimlerim            (kendi bildirimleri; e-posta JETONDAN)
Yönetici /api/v1/geri-bildirim                 (liste, durum, göreve dönüştür)
Ek       /api/v1/geri-bildirim-ek/{ek_id}      (görsel; yalnız sahibi ve yönetici)

Yükleme doğrulaması `services/geri_bildirim.py` başında.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from dependencies.hesap_baglami import izin_gerekli, izin_iste, musteri_eposta
from fastapi import APIRouter, Body, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi import Depends as _Depends
from models.geri_bildirim import GERI_BILDIRIM_DURUMLARI, GERI_BILDIRIM_TURLERI, FeedbackAttachments, FeedbackItems
from models.proje_gorevleri import ONCELIKLER, ProjectTasks
from models.projects import Projects
from pydantic import BaseModel
from services import geri_bildirim as gb
from services import gorevler as gs
from services.gorevler import GorevHatasi
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

musteri_router = APIRouter(
    prefix="/api/v1/geri-bildirimlerim",
    tags=["geri-bildirim"],
    # Faz 2E: ekip üyesinde `projeler` ya da `destek` izni (hata bildirimi ikisine de girer).
    dependencies=[_Depends(izin_gerekli("projeler", "destek")), _Depends(modul_gerekli("geri_bildirim"))],
)
yonetici_router = APIRouter(
    prefix="/api/v1/geri-bildirim", tags=["geri-bildirim"], dependencies=[_Depends(yonetici_gerekli)]
)
ek_router = APIRouter(prefix="/api/v1/geri-bildirim-ek", tags=["geri-bildirim"])

GUNLUK_SINIR = 20
BASLIK_SINIRI = 200
ACIKLAMA_SINIRI = 4000


class GuncellemeGirdisi(BaseModel):
    durum: Optional[str] = None
    oncelik: Optional[str] = None


class DonusturGirdisi(BaseModel):
    musteriye_gorunur: Optional[bool] = True
    baslik: Optional[str] = None


def _musteri_iste(request: Request) -> str:
    """Etkin hesabın e-postası (Faz 2E)."""
    kullanici, _ = _yonetici_mi(request)
    if not gs.eposta_duzelt(getattr(kullanici, "email", None)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli")
    return musteri_eposta(request)


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli")
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
    return gs.eposta_duzelt(kullanici.email)


async def _gorsel_oku(dosya: UploadFile) -> tuple:
    """(bayt, tür) — boyut ve imza sunucuda doğrulanıyor."""
    bayt = await dosya.read(gb.EN_BUYUK_BOYUT + 1)
    if len(bayt) > gb.EN_BUYUK_BOYUT:
        raise GorevHatasi(413, "dosya_buyuk")
    if not bayt:
        raise GorevHatasi(400, "dosya_bos")
    tur = gb.gorsel_turu(bayt)
    if tur is None:
        raise GorevHatasi(415, "tur_desteklenmiyor")
    return bayt, tur


async def _proje_basliklari(db: AsyncSession, idler) -> dict:
    idler = [i for i in set(idler) if i]
    if not idler:
        return {}
    return {pid: t for pid, t in (await db.execute(select(Projects.id, Projects.title).where(Projects.id.in_(idler)))).all()}


async def _musteri_projesi(db: AsyncSession, eposta: str, proje_id: Optional[int]) -> Optional[Projects]:
    """Verilen proje kullanıcının değilse 404 (varlığı da sızmasın). Verilmediyse
    tek projesi varsa o, yoksa None."""
    if proje_id is not None:
        p = (await db.execute(select(Projects).where(Projects.id == proje_id))).scalar_one_or_none()
        if p is None or gs.eposta_duzelt(p.client_email) != eposta:
            raise GorevHatasi(404, "proje_yok")
        return p
    projeler = await gs.musteri_projeleri(db, eposta)
    return projeler[0] if len(projeler) == 1 else None


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
@musteri_router.get("")
async def kendi_bildirimlerim(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = _musteri_iste(request)
    kayitlar = list(
        (
            await db.execute(
                select(FeedbackItems).where(FeedbackItems.musteri_eposta == eposta).order_by(FeedbackItems.id.desc()).limit(100)
            )
        ).scalars().all()
    )
    ekler = await gb.ekler_sozlugu(db, [k.id for k in kayitlar])
    basliklar = await _proje_basliklari(db, [k.proje_id for k in kayitlar])
    return [gb.sozluk(k, ekler.get(k.id, []), yonetici=False, proje_basligi=basliklar.get(k.proje_id)) for k in kayitlar]


@musteri_router.post("")
async def bildirim_gonder(
    request: Request,
    baslik: str = Form(...),
    aciklama: Optional[str] = Form(None),
    tur: Optional[str] = Form("hata"),
    sayfa_adresi: Optional[str] = Form(None),
    tarayici: Optional[str] = Form(None),
    proje_id: Optional[int] = Form(None),
    ekran: Optional[UploadFile] = File(None),
    db: AsyncSession = _Depends(get_db),
):
    eposta = _musteri_iste(request)
    tur = tur or "hata"
    if tur not in GERI_BILDIRIM_TURLERI:
        raise GorevHatasi(400, "tur_gecersiz")
    baslik_temiz = (baslik or "").strip()[:BASLIK_SINIRI]
    if not baslik_temiz:
        raise GorevHatasi(400, "baslik_gerekli")
    proje = await _musteri_projesi(db, eposta, proje_id)
    son_gun = datetime.now(timezone.utc) - timedelta(days=1)
    adet = (
        await db.execute(
            select(func.count(FeedbackItems.id)).where(FeedbackItems.musteri_eposta == eposta).where(FeedbackItems.created_at >= son_gun)
        )
    ).scalar()
    if int(adet or 0) >= GUNLUK_SINIR:
        raise GorevHatasi(429, "gunluk_sinir")
    # Dosya önce doğrulanıyor: geçersiz görselle yarım kayıt oluşmasın.
    gorsel = await _gorsel_oku(ekran) if ekran is not None and ekran.filename else None
    fb = FeedbackItems(
        proje_id=proje.id if proje else None,
        musteri_eposta=eposta,
        tur=tur,
        baslik=baslik_temiz,
        aciklama=(aciklama or "").strip()[:ACIKLAMA_SINIRI] or None,
        sayfa_adresi=gb.sayfa_adresi_duzelt(sayfa_adresi),
        tarayici=gb.tarayici_bilgisi(tarayici, request.headers.get("user-agent")),
        durum="yeni",
        oncelik="normal",
    )
    db.add(fb)
    await db.flush()
    ekler = []
    if gorsel is not None:
        ekler.append(await gb.ek_kaydet(db, fb, ekran.filename, gorsel[0], gorsel[1]))
    await db.commit()
    await db.refresh(fb)
    await gb.yoneticiye_bildir(db, fb, proje.title if proje else None)
    return gb.sozluk(fb, ekler, yonetici=False, proje_basligi=proje.title if proje else None)


@musteri_router.post("/{fb_id}/ek")
async def ek_ekle(fb_id: int, request: Request, ekran: UploadFile = File(...), db: AsyncSession = _Depends(get_db)):
    eposta = _musteri_iste(request)
    fb = (await db.execute(select(FeedbackItems).where(FeedbackItems.id == fb_id))).scalar_one_or_none()
    if fb is None or fb.musteri_eposta != eposta:
        raise GorevHatasi(404, "kayit_yok")
    adet = (await db.execute(select(func.count(FeedbackAttachments.id)).where(FeedbackAttachments.geri_bildirim_id == fb.id))).scalar()
    if int(adet or 0) >= gb.EK_SINIRI:
        raise GorevHatasi(409, "ek_siniri")
    bayt, tur = await _gorsel_oku(ekran)
    ek = await gb.ek_kaydet(db, fb, ekran.filename, bayt, tur)
    await db.commit()
    return gb.ek_sozlugu(ek)


# --------------------------------------------------------------------------
# Ek (görsel) okuma
# --------------------------------------------------------------------------
@ek_router.get("/{ek_id}")
async def ek_goster(ek_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    kullanici, yonetici = _yonetici_mi(request)
    if not gs.eposta_duzelt(getattr(kullanici, "email", None)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli")
    # Faz 2E: ek etkin hesaba ait olmalı; ekip üyesinde projeler/destek izni.
    eposta = musteri_eposta(request) if yonetici else izin_iste(request, "projeler", "destek").hesap_email
    ek = (await db.execute(select(FeedbackAttachments).where(FeedbackAttachments.id == ek_id))).scalar_one_or_none()
    if ek is None or (not yonetici and ek.musteri_eposta != eposta):
        raise GorevHatasi(404, "ek_yok")
    try:
        icerik = await gb.ek_oku(ek)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ek okunamadı: %s", ek_id)
        raise GorevHatasi(502, "ek_okunamadi") from exc
    return Response(
        content=icerik,
        media_type=ek.icerik_turu,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": f'inline; filename="ek-{ek.id}.{gb.UZANTILAR.get(ek.icerik_turu, "bin")}"',
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'",
        },
    )


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("")
async def liste(
    request: Request,
    durum: Optional[str] = None,
    proje_id: Optional[int] = None,
    tur: Optional[str] = None,
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    sorgu = select(FeedbackItems)
    if durum == "acik":
        sorgu = sorgu.where(FeedbackItems.durum.in_(gb.ACIK_DURUMLAR))
    elif durum:
        sorgu = sorgu.where(FeedbackItems.durum == durum)
    if proje_id is not None:
        sorgu = sorgu.where(FeedbackItems.proje_id == proje_id)
    if tur:
        sorgu = sorgu.where(FeedbackItems.tur == tur)
    kayitlar = list((await db.execute(sorgu.order_by(FeedbackItems.id.desc()).limit(300))).scalars().all())
    ekler = await gb.ekler_sozlugu(db, [k.id for k in kayitlar])
    basliklar = await _proje_basliklari(db, [k.proje_id for k in kayitlar])
    return [gb.sozluk(k, ekler.get(k.id, []), yonetici=True, proje_basligi=basliklar.get(k.proje_id)) for k in kayitlar]


@yonetici_router.patch("/{fb_id}")
async def guncelle(fb_id: int, request: Request, govde: GuncellemeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    fb = (await db.execute(select(FeedbackItems).where(FeedbackItems.id == fb_id))).scalar_one_or_none()
    if fb is None:
        raise GorevHatasi(404, "kayit_yok")
    if govde.oncelik is not None:
        if govde.oncelik not in ONCELIKLER:
            raise GorevHatasi(400, "oncelik_gecersiz")
        fb.oncelik = govde.oncelik
    durum_degisti = False
    if govde.durum is not None:
        if govde.durum not in GERI_BILDIRIM_DURUMLARI:
            raise GorevHatasi(400, "durum_gecersiz")
        if govde.durum == "gorev" and not fb.gorev_id:
            raise GorevHatasi(409, "gorev_yok")
        durum_degisti = fb.durum != govde.durum
        fb.durum = govde.durum
    await db.commit()
    await db.refresh(fb)
    if durum_degisti:
        await gb.musteriye_bildir(db, fb)
    ekler = await gb.ekler_sozlugu(db, [fb.id])
    basliklar = await _proje_basliklari(db, [fb.proje_id])
    return gb.sozluk(fb, ekler.get(fb.id, []), yonetici=True, proje_basligi=basliklar.get(fb.proje_id))


@yonetici_router.post("/{fb_id}/goreve-donustur")
async def goreve_donustur(fb_id: int, request: Request, govde: DonusturGirdisi = Body(default=DonusturGirdisi()), db: AsyncSession = _Depends(get_db)):
    """Tek tıkla proje görevi: "yapilacak" sütununun sonuna, türü etiket olarak."""
    ben = _yonetici_iste(request)
    fb = (await db.execute(select(FeedbackItems).where(FeedbackItems.id == fb_id))).scalar_one_or_none()
    if fb is None:
        raise GorevHatasi(404, "kayit_yok")
    if fb.gorev_id:
        raise GorevHatasi(409, "zaten_gorev", gorev_id=fb.gorev_id)
    if not fb.proje_id:
        raise GorevHatasi(409, "proje_yok")
    proje = await gs.proje_bul(db, fb.proje_id)
    en = (
        await db.execute(
            select(func.coalesce(func.max(ProjectTasks.sira), -1)).where(ProjectTasks.proje_id == proje.id).where(ProjectTasks.durum == "yapilacak")
        )
    ).scalar()
    g = ProjectTasks(
        proje_id=proje.id,
        baslik=((govde.baslik or "").strip() or fb.baslik)[:200],
        aciklama=gb.gorev_aciklamasi(fb),
        durum="yapilacak",
        oncelik=fb.oncelik if fb.oncelik in ONCELIKLER else "normal",
        sira=int(en if en is not None else -1) + 1,
        musteriye_gorunur=govde.musteriye_gorunur is not False,
        kilometre_tasi=False,
        harcanan_saat=0.0,
        etiketler=json.dumps([fb.tur]),
        geri_bildirim_id=fb.id,
        olusturan_eposta=ben,
    )
    db.add(g)
    await db.flush()
    fb.gorev_id = g.id
    fb.durum = "gorev"
    await db.commit()
    await db.refresh(fb)
    await db.refresh(g)
    await gb.musteriye_bildir(db, fb)
    ekler = await gb.ekler_sozlugu(db, [fb.id])
    return {
        "geri_bildirim": gb.sozluk(fb, ekler.get(fb.id, []), yonetici=True, proje_basligi=proje.title),
        "gorev": await gs.tek_gorev(db, g),
    }


router = (musteri_router, yonetici_router, ek_router)
