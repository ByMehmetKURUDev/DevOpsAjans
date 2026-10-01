"""Faz 3K — Kaynaklar (herkese açık araç / beceri / açık kaynak listesi).

Herkese açık (oturumsuz, yalnız `yayinda=true`, `Cache-Control` 5 dk):
  GET /api/v1/kaynaklar?kategori=&q=&dil=       liste (hafif kart alanları)
  GET /api/v1/kaynaklar?bicim=tam                derleme verisi: 7 dil, tüm alanlar
                                                  (prerender ve llms.txt okuyor)
  GET /api/v1/kaynaklar/{slug}?dil=              ayrıntı + aynı kategoriden 3 ilgili

Yönetici (`/api/v1/kaynaklar/yonetim`):
  GET    ""            hepsi (taslaklar dahil) + kategoriler
  POST   ""            yeni kaynak
  PUT    "/{id}"       tam güncelleme
  PATCH  "/{id}"       hızlı anahtarlar: yayinda, one_cikan, sira
  POST   "/sirala"     {"sira": [id, ...]} → 10, 20, 30…
  DELETE "/{id}"       silme; kayıt çöp kutusuna düşer (services/cop_kutusu.py)

Hata gövdeleri `{"detail": {"kod": "...", "alan": "..."}}`: metni ön yüz
yedi dilde kuruyor.

Yönetici router'ı ÖNCE ekleniyor (`router` demetinin sırası): aksi hâlde
`GET /kaynaklar/yonetim` herkese açık `/{slug}` ucuna düşerdi. `yonetim`
slug olarak da ayrılmış (services/kaynaklar.py `AYRILMIS_SLUGLAR`).
"""

import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Query, Request, Response, status
from fastapi import Depends as _Depends
from models.kaynaklar import Kaynaklar
from pydantic import BaseModel
from services import kaynaklar as servis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# Çöp kutusu kancası bu tabloyu yakalasın diye modülün yüklü olduğundan emin ol.
from services import cop_kutusu as _cop_kutusu  # noqa: F401

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/kaynaklar/yonetim", tags=["kaynaklar"])
acik_router = APIRouter(prefix="/api/v1/kaynaklar", tags=["kaynaklar"])

#: Herkese açık uçlarda tarayıcı önbelleği (sn). Yeni kaynak en geç bu kadar sonra görünür.
ONBELLEK_SN = 300
ILGILI_SAYISI = 3


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})
    return (kullanici.email or "").strip().lower()


def _hata(exc: servis.KaynakHatasi) -> HTTPException:
    return HTTPException(status_code=400, detail={"kod": exc.kod, "alan": exc.alan})


def _onbellek(response: Response) -> None:
    response.headers["Cache-Control"] = f"public, max-age={ONBELLEK_SN}"


async def _yayindakiler(db: AsyncSession) -> List[Kaynaklar]:
    try:
        satirlar = list(
            (await db.execute(select(Kaynaklar).where(Kaynaklar.yayinda.is_(True)).limit(2000))).scalars().all()
        )
    except Exception as hata:  # noqa: BLE001 - tablo henüz yoksa sayfa boş açılsın
        logger.warning("Kaynaklar okunamadı: %s", hata)
        return []
    satirlar.sort(key=servis.siralama_anahtari)
    return satirlar


# ---------------------------------------------------------------------------
# Herkese açık
# ---------------------------------------------------------------------------
@acik_router.get("")
async def kaynak_listesi(
    response: Response,
    kategori: Optional[str] = Query(None, max_length=60),
    q: Optional[str] = Query(None, max_length=200),
    dil: Optional[str] = Query(None, max_length=10),
    bicim: Optional[str] = Query(None, max_length=10, description="tam: 7 dil, bütün alanlar (derleme)"),
    db: AsyncSession = _Depends(get_db),
):
    _onbellek(response)
    kat_listesi = servis.kategoriler()
    satirlar = await _yayindakiler(db)

    if (bicim or "").strip().lower() == "tam":
        return {
            "surum": 1,
            "kategoriler": kat_listesi,
            "kaynaklar": [servis.tam_kayit(k) for k in satirlar],
        }

    d = servis.dil_coz(dil)
    sayilar: Dict[str, int] = {}
    for k in satirlar:
        sayilar[k.kategori] = sayilar.get(k.kategori, 0) + 1

    kelimeler = servis.arama_kelimeleri(q)
    secili = (kategori or "").strip()
    suzulmus = [
        k
        for k in satirlar
        if (not secili or k.kategori == secili) and servis.arama_eslesir(k, d, kelimeler, kat_listesi)
    ]
    return {
        "dil": d,
        "kaynaklar": [servis.ozet_satiri(k, d) for k in suzulmus],
        "kategoriler": [
            {"anahtar": c["anahtar"], "ad": servis.kategori_adi(c, d), "sayi": sayilar.get(c["anahtar"], 0)}
            for c in kat_listesi
        ],
        "toplam": len(suzulmus),
    }


@acik_router.get("/{slug}")
async def kaynak_ayrintisi(
    slug: str,
    response: Response,
    dil: Optional[str] = Query(None, max_length=10),
    db: AsyncSession = _Depends(get_db),
):
    d = servis.dil_coz(dil)
    satirlar = await _yayindakiler(db)
    kaynak = next((k for k in satirlar if k.slug == slug.strip().lower()), None)
    if kaynak is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    _onbellek(response)
    ilgili = [k for k in satirlar if k.kategori == kaynak.kategori and k.id != kaynak.id][:ILGILI_SAYISI]
    return {
        "dil": d,
        "kaynak": servis.ayrinti(kaynak, d, servis.kategoriler()),
        "ilgili": [servis.ozet_satiri(k, d) for k in ilgili],
    }


# ---------------------------------------------------------------------------
# Yönetici
# ---------------------------------------------------------------------------
class SiralamaGirdisi(BaseModel):
    sira: List[int]


async def _kaynak(db: AsyncSession, kaynak_id: int) -> Kaynaklar:
    k = (await db.execute(select(Kaynaklar).where(Kaynaklar.id == kaynak_id))).scalars().first()
    if k is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    return k


async def _slug_bos_mu(db: AsyncSession, slug: str, haric_id: Optional[int] = None) -> None:
    sorgu = select(Kaynaklar.id).where(Kaynaklar.slug == slug)
    if haric_id is not None:
        sorgu = sorgu.where(Kaynaklar.id != haric_id)
    if (await db.execute(sorgu)).first():
        raise HTTPException(status_code=409, detail={"kod": "slug_var", "alan": "slug"})


async def _kaydet(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail={"kod": "slug_var", "alan": "slug"}) from exc


@yonetici_router.get("")
async def yonetim_listesi(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    satirlar = list((await db.execute(select(Kaynaklar).limit(2000))).scalars().all())
    satirlar.sort(key=servis.siralama_anahtari)
    return {
        "kaynaklar": [servis.yonetim_satiri(k) for k in satirlar],
        "kategoriler": servis.kategoriler(),
    }


@yonetici_router.post("", status_code=201)
async def kaynak_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        alanlar = servis.girdiyi_dogrula(govde)
    except servis.KaynakHatasi as exc:
        raise _hata(exc) from exc
    await _slug_bos_mu(db, alanlar["slug"])
    k = Kaynaklar(**alanlar)
    db.add(k)
    await _kaydet(db)
    await db.refresh(k)
    return servis.yonetim_satiri(k)


@yonetici_router.post("/sirala")
async def sirala(request: Request, govde: SiralamaGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    kimlikler = list(dict.fromkeys(govde.sira))[:2000]
    if not kimlikler:
        return {"guncellenen": 0}
    satirlar = {k.id: k for k in (await db.execute(select(Kaynaklar).where(Kaynaklar.id.in_(kimlikler)))).scalars()}
    guncellenen = 0
    for i, kimlik in enumerate(kimlikler):
        k = satirlar.get(kimlik)
        if k is not None and k.sira != (i + 1) * 10:
            k.sira = (i + 1) * 10
            guncellenen += 1
    await db.commit()
    return {"guncellenen": guncellenen}


@yonetici_router.put("/{kaynak_id}")
async def kaynak_guncelle(
    kaynak_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = _Depends(get_db)
):
    _yonetici_iste(request)
    k = await _kaynak(db, kaynak_id)
    try:
        alanlar = servis.girdiyi_dogrula(govde)
    except servis.KaynakHatasi as exc:
        raise _hata(exc) from exc
    await _slug_bos_mu(db, alanlar["slug"], haric_id=k.id)
    for alan, deger in alanlar.items():
        setattr(k, alan, deger)
    await _kaydet(db)
    await db.refresh(k)
    return servis.yonetim_satiri(k)


@yonetici_router.patch("/{kaynak_id}")
async def kaynak_yama(
    kaynak_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = _Depends(get_db)
):
    """Listeden tek tıkla: yayında, öne çıkan, sıra. Başka alan kabul edilmiyor."""
    _yonetici_iste(request)
    k = await _kaynak(db, kaynak_id)
    bilinmeyen = set(govde) - {"yayinda", "one_cikan", "sira"}
    if bilinmeyen or not govde:
        raise HTTPException(status_code=400, detail={"kod": "gecersiz_alan", "alan": ",".join(sorted(bilinmeyen))})
    for alan in ("yayinda", "one_cikan"):
        if alan in govde:
            if not isinstance(govde[alan], bool):
                raise HTTPException(status_code=400, detail={"kod": "gecersiz_alan", "alan": alan})
            setattr(k, alan, govde[alan])
    if "sira" in govde:
        try:
            k.sira = max(-100_000, min(100_000, int(govde["sira"])))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail={"kod": "gecersiz_sira", "alan": "sira"}) from exc
    await db.commit()
    await db.refresh(k)
    return servis.yonetim_satiri(k)


@yonetici_router.delete("/{kaynak_id}")
async def kaynak_sil(kaynak_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    k = await _kaynak(db, kaynak_id)
    await db.delete(k)
    await db.commit()
    return {"silindi": kaynak_id}


router = (yonetici_router, acik_router)
