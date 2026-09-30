"""Faz 2C — Bilgi bankası (modül `bilgi_bankasi`).

Yönetici  /api/v1/bilgi-bankasi/yonetim     makale listesi, ekle, güncelle, sil,
                                             önizleme (markdown → güvenli HTML)
Müşteri   /api/v1/bilgi-bankasi?q=&dil=      yayındaki makalelerde arama
          /api/v1/bilgi-bankasi/oneri?baslik= talep açarken "bu makaleler yardımcı olabilir"
          /api/v1/bilgi-bankasi/<id>?dil=    makale (güvenli HTML)

Metinler 7 dilde: ana metin Türkçe (`baslik`, `icerik`), diğerleri
`ceviriler` JSON'unda; istenen dilde çeviri yoksa Türkçe gösteriliyor.
"""

import json
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from models.destek_sla import BilgiMakaleleri
from pydantic import BaseModel
from services.guvenli_html import duz_metin, markdown_html
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
DURUMLAR = ("taslak", "yayinda")
ICERIK_SINIRI = 60_000

yonetici_router = APIRouter(prefix="/api/v1/bilgi-bankasi/yonetim", tags=["bilgi_bankasi"])
musteri_router = APIRouter(
    prefix="/api/v1/bilgi-bankasi", tags=["bilgi_bankasi"], dependencies=[_Depends(modul_gerekli("bilgi_bankasi"))]
)


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})
    return (kullanici.email or "").strip().lower()


def _oturum_iste(request: Request) -> None:
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})


def _dil(ham: Optional[str]) -> str:
    d = (ham or "tr").strip().lower()[:2]
    return d if d in DILLER else "tr"


def _ceviriler(metin: Optional[str]) -> Dict[str, Dict[str, str]]:
    if not metin:
        return {}
    try:
        veri = json.loads(metin)
    except ValueError:
        return {}
    if not isinstance(veri, dict):
        return {}
    sonuc: Dict[str, Dict[str, str]] = {}
    for dil, deger in veri.items():
        if dil in DILLER and dil != "tr" and isinstance(deger, dict):
            sonuc[dil] = {
                "baslik": str(deger.get("baslik") or "").strip(),
                "icerik": str(deger.get("icerik") or ""),
            }
    return sonuc


def _dilde(m: BilgiMakaleleri, dil: str) -> Tuple[str, str, str]:
    """(başlık, içerik, gösterilen_dil) — çeviri boşsa Türkçe."""
    if dil != "tr":
        c = _ceviriler(m.ceviriler).get(dil)
        if c and c["baslik"] and c["icerik"].strip():
            return c["baslik"], c["icerik"], dil
    return m.baslik, m.icerik or "", "tr"


def normalize(metin: str) -> str:
    """Arama için: küçük harf, Türkçe İ/ı, aksansız."""
    metin = (metin or "").replace("İ", "i").replace("I", "ı").lower().replace("ı", "i")
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(c for c in metin if not unicodedata.combining(c))
    return metin


_KELIME = re.compile(r"[\w]+", re.UNICODE)
#: Öneri skorunu şişiren kısa/bağlaç kelimeler.
DOLGU = frozenset({
    "ve", "ile", "bir", "bu", "da", "de", "icin", "mi", "ne", "nasil", "the", "and", "for", "how", "to",
    "a", "an", "of", "in", "is", "my", "ben", "benim", "sitem", "var", "yok",
})


def kelimeler(metin: str) -> List[str]:
    return [k for k in _KELIME.findall(normalize(metin)) if len(k) >= 2 and k not in DOLGU]


def puanla(sorgu: List[str], baslik: str, icerik: str) -> int:
    b = normalize(baslik)
    i = normalize(icerik)
    puan = 0
    for k in sorgu:
        if k in b:
            puan += 3
        if k in i:
            puan += 1
    return puan


def _satir(m: BilgiMakaleleri, dil: str) -> Dict[str, Any]:
    baslik, icerik, gosterilen = _dilde(m, dil)
    return {
        "id": m.id,
        "kategori": m.kategori,
        "baslik": baslik,
        "ozet": duz_metin(icerik, 180),
        "dil": gosterilen,
    }


def _yonetim_satiri(m: BilgiMakaleleri) -> Dict[str, Any]:
    return {
        "id": m.id,
        "kategori": m.kategori,
        "baslik": m.baslik,
        "icerik": m.icerik,
        "ceviriler": _ceviriler(m.ceviriler),
        "durum": m.durum,
        "goruntulenme": int(m.goruntulenme or 0),
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Yönetici
# ---------------------------------------------------------------------------
class MakaleGirdisi(BaseModel):
    kategori: Optional[str] = None
    baslik: str
    icerik: str = ""
    ceviriler: Optional[Dict[str, Dict[str, str]]] = None
    durum: str = "taslak"


class OnizlemeGirdisi(BaseModel):
    icerik: str = ""


def _dogrula(govde: MakaleGirdisi) -> Dict[str, Any]:
    baslik = (govde.baslik or "").strip()[:200]
    if not baslik:
        raise HTTPException(status_code=400, detail={"kod": "baslik_gerekli"})
    if govde.durum not in DURUMLAR:
        raise HTTPException(status_code=400, detail={"kod": "gecersiz_durum"})
    if len(govde.icerik or "") > ICERIK_SINIRI:
        raise HTTPException(status_code=400, detail={"kod": "icerik_uzun"})
    ceviriler: Dict[str, Dict[str, str]] = {}
    for dil, deger in (govde.ceviriler or {}).items():
        if dil not in DILLER or dil == "tr":
            raise HTTPException(status_code=400, detail={"kod": "gecersiz_dil"})
        b = str((deger or {}).get("baslik") or "").strip()[:200]
        i = str((deger or {}).get("icerik") or "")
        if len(i) > ICERIK_SINIRI:
            raise HTTPException(status_code=400, detail={"kod": "icerik_uzun"})
        if b or i.strip():
            ceviriler[dil] = {"baslik": b, "icerik": i}
    return {
        "kategori": (govde.kategori or "").strip()[:80] or None,
        "baslik": baslik,
        "icerik": govde.icerik or "",
        "ceviriler": json.dumps(ceviriler, ensure_ascii=False) if ceviriler else None,
        "durum": govde.durum,
    }


@yonetici_router.get("")
async def yonetim_listesi(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    satirlar = (await db.execute(select(BilgiMakaleleri).order_by(BilgiMakaleleri.id.desc()).limit(500))).scalars().all()
    return [_yonetim_satiri(m) for m in satirlar]


@yonetici_router.post("/onizle")
async def onizle(request: Request, govde: OnizlemeGirdisi = Body(...)):
    _yonetici_iste(request)
    return {"html": markdown_html(govde.icerik[:ICERIK_SINIRI])}


@yonetici_router.post("")
async def makale_ekle(request: Request, govde: MakaleGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yazan = _yonetici_iste(request)
    m = BilgiMakaleleri(**_dogrula(govde), yazan=yazan, goruntulenme=0)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _yonetim_satiri(m)


async def _makale(db: AsyncSession, makale_id: int) -> BilgiMakaleleri:
    m = (await db.execute(select(BilgiMakaleleri).where(BilgiMakaleleri.id == makale_id))).scalars().first()
    if m is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    return m


@yonetici_router.put("/{makale_id}")
async def makale_guncelle(
    makale_id: int, request: Request, govde: MakaleGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    _yonetici_iste(request)
    m = await _makale(db, makale_id)
    for alan, deger in _dogrula(govde).items():
        setattr(m, alan, deger)
    await db.commit()
    await db.refresh(m)
    return _yonetim_satiri(m)


@yonetici_router.delete("/{makale_id}")
async def makale_sil(makale_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    m = await _makale(db, makale_id)
    await db.delete(m)
    await db.commit()
    return {"silindi": makale_id}


# ---------------------------------------------------------------------------
# Müşteri
# ---------------------------------------------------------------------------
async def _yayindakiler(db: AsyncSession) -> List[BilgiMakaleleri]:
    return list(
        (
            await db.execute(
                select(BilgiMakaleleri).where(BilgiMakaleleri.durum == "yayinda").order_by(BilgiMakaleleri.id.desc()).limit(1000)
            )
        ).scalars().all()
    )


def _siralanmis(makaleler: List[BilgiMakaleleri], sorgu: List[str], dil: str) -> List[Tuple[int, BilgiMakaleleri]]:
    sonuc = []
    for m in makaleler:
        # Hem seçili dilde hem Türkçede ara: müşteri Türkçe terimle arayabilir.
        baslik, icerik, _ = _dilde(m, dil)
        puan = puanla(sorgu, baslik, icerik)
        if dil != "tr":
            puan = max(puan, puanla(sorgu, m.baslik, m.icerik or ""))
        if puan > 0:
            sonuc.append((puan, m))
    sonuc.sort(key=lambda x: (-x[0], -x[1].id))
    return sonuc


@musteri_router.get("")
async def ara(
    request: Request,
    q: Optional[str] = Query(None, max_length=200),
    dil: Optional[str] = Query(None),
    db: AsyncSession = _Depends(get_db),
):
    _oturum_iste(request)
    d = _dil(dil)
    makaleler = await _yayindakiler(db)
    sorgu = kelimeler(q or "")
    if not sorgu:
        return {"makaleler": [_satir(m, d) for m in makaleler[:50]]}
    return {"makaleler": [_satir(m, d) for _, m in _siralanmis(makaleler, sorgu, d)[:30]]}


@musteri_router.get("/oneri")
async def oneri(
    request: Request,
    baslik: str = Query("", max_length=300),
    dil: Optional[str] = Query(None),
    db: AsyncSession = _Depends(get_db),
):
    _oturum_iste(request)
    sorgu = kelimeler(baslik)
    if not sorgu:
        return {"makaleler": []}
    d = _dil(dil)
    return {"makaleler": [_satir(m, d) for _, m in _siralanmis(await _yayindakiler(db), sorgu, d)[:3]]}


@musteri_router.get("/{makale_id}")
async def makale(
    makale_id: int,
    request: Request,
    dil: Optional[str] = Query(None),
    db: AsyncSession = _Depends(get_db),
):
    _oturum_iste(request)
    _, yonetici = _yonetici_mi(request)
    m = await _makale(db, makale_id)
    if m.durum != "yayinda" and not yonetici:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    baslik, icerik, gosterilen = _dilde(m, _dil(dil))
    if not yonetici:
        await db.execute(
            update(BilgiMakaleleri)
            .where(BilgiMakaleleri.id == m.id)
            .values(goruntulenme=BilgiMakaleleri.goruntulenme + 1)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
    return {
        "id": m.id,
        "kategori": m.kategori,
        "baslik": baslik,
        "html": markdown_html(icerik),
        "dil": gosterilen,
    }


router = (yonetici_router, musteri_router)
