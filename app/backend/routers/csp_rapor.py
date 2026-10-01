"""Faz 4G — CSP ihlal raporu ucu.

    POST   /api/v1/csp-rapor            herkese açık (tarayıcı gönderiyor), gövdesiz yanıt
    GET    /api/v1/csp-rapor/yonetim    yönetici: son raporlar (Güvenlik sekmesi)
    DELETE /api/v1/csp-rapor/yonetim    yönetici: listeyi temizle

Sitenin CSP'si (`functions/_ortak/csp.js` → `dist/_headers`, kart/menü
Function'ları) `report-uri /api/v1/csp-rapor` ve `report-to csp` taşıyor.
Tarayıcı iki biçimden birini gönderiyor:

* `report-uri`: `Content-Type: application/csp-report`, gövde
  `{"csp-report": {"document-uri", "violated-directive", "blocked-uri", ...}}`
* Reporting API (`report-to`): `Content-Type: application/reports+json`, gövde
  `[{"type": "csp-violation", "body": {"documentURL", "effectiveDirective",
  "blockedURL", ...}}, ...]`

Kötüye kullanım: gövde en çok `GOVDE_SINIRI` bayt, istek başına en çok
`RAPOR_SINIRI` rapor, IP başına dakikada `IP_SINIRI` istek ve bütün site için
10 dakikada `GENEL_SINIR` yazma. Tablo en çok `TABLO_SINIRI` satır; aynı ihlal
bir saat içinde tekrar gelince sayaç artıyor. Yazma Core ifadeleriyle
yapılıyor (iş biriminden geçmediği için denetim kaydını doldurmuyor).
"""

import json
import logging
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from core.database import get_db
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Depends, Query, Request, Response
from models.csp_raporlari import CspRaporlari
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

acik_router = APIRouter(prefix="/api/v1/csp-rapor", tags=["csp"])
yonetici_router = APIRouter(prefix="/api/v1/csp-rapor/yonetim", tags=["csp"], dependencies=[Depends(yonetici_gerekli)])

GOVDE_SINIRI = 32_000
RAPOR_SINIRI = 20
TABLO_SINIRI = 500
IP_SINIRI = 30
GENEL_SINIR = 600
BIRLESTIRME_SURESI = timedelta(hours=1)
DILLER = {"tr", "en", "de", "ru", "zh", "hi", "ar"}
#: Tarayıcının adres yerine yazdığı anahtar sözcükler (olduğu gibi saklanır).
OZEL_KAYNAKLAR = {"inline", "eval", "wasm-eval", "trusted-types-policy", "trusted-types-sink", "self"}

_ip_hizi = HizSiniri(IP_SINIRI, 60.0)
_genel_hiz = HizSiniri(GENEL_SINIR, 600.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    _ip_hizi.temizle()
    _genel_hiz.temizle()


def _bos(durum: int) -> Response:
    return Response(status_code=durum, headers={"Cache-Control": "no-store"})


def _metin(deger: Any, sinir: int) -> str:
    return " ".join(str(deger or "").split())[:sinir]


def _sayi(deger: Any) -> Optional[int]:
    try:
        s = int(deger)
    except (TypeError, ValueError):
        return None
    return s if 0 <= s < 10_000_000 else None


def adres_kisalt(ham: Any, belge: bool = False) -> str:
    """Sorgu dizgesi ve parça atılır. `belge` ise yol ilk anlamlı parçadan sonra
    "…" ile kısaltılır (`/teklif/<jeton>` gibi adresler jeton taşıyabilir)."""
    s = _metin(ham, 2000)
    if not s:
        return ""
    if s.lower() in OZEL_KAYNAKLAR:
        return s.lower()
    p = urlparse(s)
    if p.scheme in ("data", "blob", "filesystem", "about", "chrome-extension", "moz-extension", "safari-extension"):
        return p.scheme
    if not p.scheme or not p.netloc:
        return s[:60]
    yol = p.path or "/"
    if belge:
        parcalar = [x for x in yol.split("/") if x]
        tut = 2 if parcalar and parcalar[0] in DILLER else 1
        yol = "/" + "/".join(parcalar[:tut]) + ("/…" if len(parcalar) > tut else "")
    return f"{p.scheme}://{p.netloc}{yol}"[:300]


def _normalize(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """İki biçimden (report-uri / Reporting API) ortak satıra."""
    if not isinstance(r, dict):
        return None
    al = lambda *adlar: next((r.get(a) for a in adlar if r.get(a) not in (None, "")), None)  # noqa: E731
    yonerge = _metin(al("effectiveDirective", "effective-directive", "violated-directive", "violatedDirective"), 60)
    yonerge = yonerge.split(" ")[0]
    if not yonerge:
        return None
    mod = _metin(al("disposition"), 10).lower()
    return {
        "belge": adres_kisalt(al("documentURL", "document-uri", "documentURI"), belge=True),
        "yonerge": yonerge,
        "engellenen": adres_kisalt(al("blockedURL", "blocked-uri", "blockedURI")),
        "kaynak_dosya": adres_kisalt(al("sourceFile", "source-file")) or None,
        "satir": _sayi(al("lineNumber", "line-number")),
        "sutun": _sayi(al("columnNumber", "column-number")),
        "mod": mod if mod in ("enforce", "report") else "enforce",
        "ornek": _metin(al("sample", "script-sample"), 40) or None,
    }


def raporlari_ayikla(govde: Any) -> List[Dict[str, Any]]:
    adaylar: Iterable[Any]
    if isinstance(govde, list):
        adaylar = (o.get("body") for o in govde if isinstance(o, dict) and o.get("type") in ("csp-violation", None))
    elif isinstance(govde, dict) and isinstance(govde.get("csp-report"), dict):
        adaylar = [govde["csp-report"]]
    elif isinstance(govde, dict) and isinstance(govde.get("body"), dict):
        adaylar = [govde["body"]]
    else:
        adaylar = []
    sonuc = []
    for a in adaylar:
        n = _normalize(a) if isinstance(a, dict) else None
        if n:
            sonuc.append(n)
        if len(sonuc) >= RAPOR_SINIRI:
            break
    return sonuc


async def _kaydet(db: AsyncSession, satirlar: List[Dict[str, Any]]) -> None:
    from services.crm import simdi

    an = simdi()
    T = CspRaporlari
    for s in satirlar:
        mevcut = (
            await db.execute(
                select(T.id).where(
                    T.belge == s["belge"], T.yonerge == s["yonerge"], T.engellenen == s["engellenen"],
                    (T.kaynak_dosya == s["kaynak_dosya"]) if s["kaynak_dosya"] else T.kaynak_dosya.is_(None),
                    T.mod == s["mod"], T.son_at >= an - BIRLESTIRME_SURESI,
                ).order_by(T.id.desc()).limit(1)
            )
        ).scalar()
        if mevcut:
            await db.execute(update(T).where(T.id == mevcut).values(sayi=T.sayi + 1, son_at=an))
        else:
            await db.execute(insert(T).values(**s, sayi=1, ilk_at=an, son_at=an))
    # En yeni TABLO_SINIRI satır kalsın.
    fazla = select(T.id).order_by(T.son_at.desc(), T.id.desc()).offset(TABLO_SINIRI).scalar_subquery()
    await db.execute(delete(T).where(T.id.in_(fazla)))
    await db.commit()


@acik_router.post("")
async def csp_raporu_al(request: Request, db: AsyncSession = Depends(get_db)):
    if not _ip_hizi.izin_var_mi(ip_ozeti("csp|" + istemci_ip(request))):
        return _bos(429)
    uzunluk = request.headers.get("content-length")
    if uzunluk and uzunluk.isdigit() and int(uzunluk) > GOVDE_SINIRI:
        return _bos(413)
    ham = b""
    async for parca in request.stream():
        ham += parca
        if len(ham) > GOVDE_SINIRI:
            return _bos(413)
    try:
        govde = json.loads(ham.decode("utf-8") or "null")
    except (ValueError, UnicodeDecodeError):
        return _bos(400)
    satirlar = raporlari_ayikla(govde)
    if not satirlar:
        return _bos(204)
    if not _genel_hiz.izin_var_mi("genel"):
        return _bos(429)
    try:
        await _kaydet(db, satirlar)
    except Exception:  # noqa: BLE001 - rapor kaybı siteyi etkilemesin
        logger.exception("CSP raporu kaydedilemedi")
        await db.rollback()
    return _bos(204)


def _sozluk(k: CspRaporlari) -> Dict[str, Any]:
    from services.crm import iso

    return {
        "id": k.id, "belge": k.belge, "yonerge": k.yonerge, "engellenen": k.engellenen,
        "kaynak_dosya": k.kaynak_dosya, "satir": k.satir, "sutun": k.sutun, "mod": k.mod, "ornek": k.ornek,
        "sayi": k.sayi or 1, "ilk_at": iso(k.ilk_at), "son_at": iso(k.son_at),
    }


@yonetici_router.get("")
async def csp_raporlari(adet: int = Query(100, ge=1, le=TABLO_SINIRI), db: AsyncSession = Depends(get_db)):
    toplam = int((await db.execute(select(func.count(CspRaporlari.id)))).scalar() or 0)
    satirlar = (
        await db.execute(select(CspRaporlari).order_by(CspRaporlari.son_at.desc(), CspRaporlari.id.desc()).limit(adet))
    ).scalars().all()
    return {"items": [_sozluk(k) for k in satirlar], "toplam": toplam, "sinir": TABLO_SINIRI}


@yonetici_router.delete("")
async def csp_raporlarini_temizle(db: AsyncSession = Depends(get_db)):
    sonuc = await db.execute(delete(CspRaporlari))
    await db.commit()
    return {"silinen": int(sonuc.rowcount or 0)}


router = (acik_router, yonetici_router)
