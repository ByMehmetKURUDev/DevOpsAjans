"""Faz 4A — herkese açık REST API (`/api/public/v1`) ve uzak MCP sunucusu (`/api/public/v1/mcp`).

Kimlik: `Authorization: Bearer mk_live_…` ya da `X-API-Key: mk_live_…`
(panel JWT'si burada GEÇMEZ; anahtar da panel uçlarında geçmez).

Uçlar (kapsam)
--------------
GET    /hesap                         (her anahtar)   hesap özeti
GET    /projeler, /projeler/{id}      projeler:oku
GET    /gorevler, /gorevler/{id}      gorevler:oku
POST   /gorevler                      gorevler:yaz    (Idempotency-Key)
PATCH  /gorevler/{id}                 gorevler:yaz    (Idempotency-Key)
GET    /faturalar, /faturalar/{id}    faturalar:oku
GET    /destek, /destek/{id}          destek:oku
POST   /destek                        destek:yaz      (Idempotency-Key)
POST   /destek/{id}/yanit             destek:yaz      (Idempotency-Key)
GET    /crm/adaylar, /crm/adaylar/{id} crm:oku        (yalnız ajans)
POST   /crm/adaylar                   crm:yaz         (yalnız ajans; Idempotency-Key)
GET    /qr, /qr/{id}                  qr:oku
GET    /menuler, /menuler/{id}/siparisler  menu:oku
GET    /openapi.json                  (kimliksiz) yalnız bu API'nin OpenAPI belgesi
POST   /mcp                           MCP (JSON-RPC; araçlar kapsama göre)

Listeler: `limit` (1–100), `cursor`, `updated_since` (ISO 8601) → `{veri, sonraki_cursor, daha_var}`.
Hata biçimi her yerde: `{"hata": {"kod", "mesaj"}}` (+ isteğe bağlı ek alanlar).
"""

import json
import logging
from typing import Any, Callable, Dict, Optional

from core.database import get_db
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from schemas import public_api as sema
from services import public_api as p
from services.api_erisimi import ApiHatasi, ApiKimlik, MESAJLAR, idem_basla, idem_birak, idem_bitir, kapsam_modulu_acik_mi, kimlik_dogrula
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

TABAN = "/api/public/v1"
SURUM = "1.0.0"


def hata_yaniti(durum: int, kod: str, mesaj: Optional[str] = None, basliklar: Optional[Dict[str, str]] = None,
                **ek: Any) -> JSONResponse:
    govde = {"hata": {"kod": kod, "mesaj": mesaj or MESAJLAR.get(kod) or kod, **ek}}
    return JSONResponse(status_code=durum, content=govde, headers=basliklar or None)


def _http_hatasi(h: StarletteHTTPException) -> JSONResponse:
    detay = h.detail
    if isinstance(detay, dict) and detay.get("kod"):
        ek = {k: v for k, v in detay.items() if k not in ("kod", "mesaj")}
        return hata_yaniti(h.status_code, str(detay["kod"]), detay.get("mesaj"), dict(h.headers or {}), **ek)
    kodlar = {401: "anahtar_gerekli", 403: "yetki_yok", 404: "bulunamadi", 405: "yontem_desteklenmiyor", 409: "cakisma",
              422: "gecersiz_istek", 429: "hiz_siniri"}
    return hata_yaniti(h.status_code, kodlar.get(h.status_code, "hata"), str(detay) if detay else None, dict(h.headers or {}))


class ApiRotasi(APIRoute):
    """Bu router'daki her ucun hatası `{"hata": {"kod","mesaj"}}` biçiminde (genel işleyiciye düşmeden)."""

    def get_route_handler(self) -> Callable:
        asil = super().get_route_handler()

        async def isleyici(request: Request) -> Response:
            try:
                return await asil(request)
            except ApiHatasi as h:
                return hata_yaniti(h.durum, h.kod, h.mesaj, h.basliklar, **h.ek)
            except RequestValidationError as h:
                ayrinti = [
                    {"alan": ".".join(str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path")), "sorun": e.get("msg")}
                    for e in h.errors()
                ][:20]
                return hata_yaniti(422, "gecersiz_istek", None, None, ayrinti=ayrinti)
            except StarletteHTTPException as h:
                return _http_hatasi(h)
            except Exception:  # noqa: BLE001
                logger.exception("Herkese açık API beklenmeyen hata: %s %s", request.method, request.url.path)
                return hata_yaniti(500, "sunucu_hatasi")

        return isleyici


router = APIRouter(prefix=TABAN, tags=["public-api"], route_class=ApiRotasi)


# ---------------------------------------------------------------------------
# Kimlik bağımlılıkları
# ---------------------------------------------------------------------------
async def _kimlik(request: Request, db: AsyncSession = Depends(get_db)) -> ApiKimlik:
    kimlik = await kimlik_dogrula(db, request)
    request.state.api_kimlik = kimlik
    return kimlik


def kapsam_gerekli(kapsam: str):
    async def _bekci(request: Request, db: AsyncSession = Depends(get_db)) -> ApiKimlik:
        kimlik = await kimlik_dogrula(db, request)
        kimlik.kapsam_iste(kapsam)
        if not await kapsam_modulu_acik_mi(db, kimlik, kapsam):
            raise ApiHatasi(403, "modul_kapali")
        request.state.api_kimlik = kimlik
        return kimlik

    _bekci.__name__ = f"kapsam_{kapsam.replace(':', '_')}"
    return _bekci


HATA_YANITLARI = {
    400: {"model": sema.HataYaniti, "description": "Geçersiz istek"},
    401: {"model": sema.HataYaniti, "description": "Anahtar yok / geçersiz / iptal / süresi dolmuş"},
    403: {"model": sema.HataYaniti, "description": "Kapsam yetersiz, IP izinli değil ya da modül kapalı"},
    404: {"model": sema.HataYaniti, "description": "Kayıt yok (ya da başka hesaba ait)"},
    429: {"model": sema.HataYaniti, "description": "Anahtarın dakikalık sınırı aşıldı (Retry-After)"},
}
YAZMA_YANITLARI = {
    **HATA_YANITLARI,
    409: {"model": sema.HataYaniti, "description": "Çakışma (ör. aynı Idempotency-Key işleniyor)"},
    422: {"model": sema.HataYaniti, "description": "Gövde geçersiz ya da Idempotency-Key başka istekle kullanılmış"},
}


def _sayfa_parametreleri(
    limit: int = Query(25, ge=1, le=100, description="Sayfa boyutu (1–100)."),
    cursor: Optional[str] = Query(None, description="Önceki yanıttaki `sonraki_cursor`."),
    updated_since: Optional[str] = Query(None, description="Yalnız bu andan sonra güncellenenler (ISO 8601)."),
) -> Dict[str, Any]:
    return {"limit": limit, "cursor": cursor, "updated_since": updated_since}


IDEM_ACIKLAMA = "İsteğe bağlı; aynı anahtarla 24 saat içinde gelen tekrar aynı yanıtı alır (gövde farklıysa 422)."


async def _yazma(request: Request, db: AsyncSession, kimlik: ApiKimlik, idem: Optional[str], durum: int, isle,
                 model: Any) -> JSONResponse:
    """Yazma ucu: Idempotency-Key varsa önceki yanıtı döndürür ya da sonucu saklar."""
    kayit_id = None
    if idem is not None:
        govde = await request.body()
        kayit_id, onceki = await idem_basla(db, kimlik, idem, f"{request.method} {request.url.path}", govde)
        if onceki is not None:
            return JSONResponse(status_code=onceki[0], content=onceki[1], headers={"Idempotent-Replayed": "true"})
    try:
        sonuc = await isle()
    except ApiHatasi as h:
        if kayit_id is not None:
            if h.durum >= 500:
                await idem_birak(db, kayit_id)
            else:
                await idem_bitir(db, kayit_id, h.durum, {"hata": {"kod": h.kod, "mesaj": h.mesaj, **h.ek}})
        raise
    except StarletteHTTPException as h:
        if kayit_id is not None:
            yanit = _http_hatasi(h)
            if h.status_code >= 500:
                await idem_birak(db, kayit_id)
            else:
                await idem_bitir(db, kayit_id, h.status_code, json.loads(yanit.body))
        raise
    except Exception:
        await idem_birak(db, kayit_id)
        raise
    # Yanıt şemadan geçiriliyor (okuma uçlarındaki `response_model` ile aynı biçim).
    sonuc = model.model_validate(sonuc).model_dump(mode="json")
    await idem_bitir(db, kayit_id, durum, sonuc)
    return JSONResponse(status_code=durum, content=sonuc)


# ---------------------------------------------------------------------------
# Hesap
# ---------------------------------------------------------------------------
@router.get("/hesap", response_model=sema.HesapOzeti, responses=HATA_YANITLARI, summary="Hesap özeti")
async def hesap(kimlik: ApiKimlik = Depends(_kimlik), db: AsyncSession = Depends(get_db)):
    """Anahtarın sahibi (ajans/müşteri), kapsamları ve kapsamdaki kayıt sayıları."""
    return await p.hesap_ozeti(db, kimlik)


# ---------------------------------------------------------------------------
# Projeler
# ---------------------------------------------------------------------------
@router.get("/projeler", response_model=sema.ProjeSayfasi, responses=HATA_YANITLARI, summary="Projeleri listele")
async def projeler(
    hesap: Optional[str] = Query(None, description="Yalnız ajans anahtarı: müşteri hesabı süzgeci."),
    sayfa: Dict[str, Any] = Depends(_sayfa_parametreleri),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("projeler:oku")),
    db: AsyncSession = Depends(get_db),
):
    return await p.projeler(db, kimlik, hesap=hesap, **sayfa)


@router.get("/projeler/{proje_id}", response_model=sema.Proje, responses=HATA_YANITLARI, summary="Projeyi getir")
async def proje(proje_id: int, kimlik: ApiKimlik = Depends(kapsam_gerekli("projeler:oku")), db: AsyncSession = Depends(get_db)):
    return await p.proje(db, kimlik, proje_id)


# ---------------------------------------------------------------------------
# Görevler
# ---------------------------------------------------------------------------
@router.get("/gorevler", response_model=sema.GorevSayfasi, responses=HATA_YANITLARI, summary="Görevleri listele")
async def gorevler(
    proje_id: Optional[int] = Query(None),
    durum: Optional[str] = Query(None, description="yapilacak | suruyor | incelemede | tamam"),
    hesap: Optional[str] = Query(None, description="Yalnız ajans anahtarı."),
    sayfa: Dict[str, Any] = Depends(_sayfa_parametreleri),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("gorevler:oku")),
    db: AsyncSession = Depends(get_db),
):
    return await p.gorevler(db, kimlik, proje_id=proje_id, durum=durum, hesap=hesap, **sayfa)


@router.get("/gorevler/{gorev_id}", response_model=sema.Gorev, responses=HATA_YANITLARI, summary="Görevi getir")
async def gorev(gorev_id: int, kimlik: ApiKimlik = Depends(kapsam_gerekli("gorevler:oku")), db: AsyncSession = Depends(get_db)):
    return await p.gorev(db, kimlik, gorev_id)


@router.post("/gorevler", response_model=sema.Gorev, status_code=201, responses=YAZMA_YANITLARI, summary="Görev oluştur")
async def gorev_olustur(
    request: Request,
    govde: sema.GorevOlustur,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", description=IDEM_ACIKLAMA),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("gorevler:yaz")),
    db: AsyncSession = Depends(get_db),
):
    return await _yazma(request, db, kimlik, idempotency_key, 201,
                        lambda: p.gorev_olustur(db, kimlik, govde.model_dump(exclude_unset=True)), sema.Gorev)


@router.patch("/gorevler/{gorev_id}", response_model=sema.Gorev, responses=YAZMA_YANITLARI, summary="Görevi güncelle")
async def gorev_guncelle(
    gorev_id: int,
    request: Request,
    govde: sema.GorevGuncelle,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", description=IDEM_ACIKLAMA),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("gorevler:yaz")),
    db: AsyncSession = Depends(get_db),
):
    return await _yazma(request, db, kimlik, idempotency_key, 200,
                        lambda: p.gorev_guncelle(db, kimlik, gorev_id, govde.model_dump(exclude_unset=True)), sema.Gorev)


# ---------------------------------------------------------------------------
# Faturalar
# ---------------------------------------------------------------------------
@router.get("/faturalar", response_model=sema.FaturaSayfasi, responses=HATA_YANITLARI, summary="Faturaları listele")
async def faturalar(
    durum: Optional[str] = Query(None, description="unpaid | paid | overdue | kismi_odendi | cancelled …"),
    hesap: Optional[str] = Query(None, description="Yalnız ajans anahtarı."),
    sayfa: Dict[str, Any] = Depends(_sayfa_parametreleri),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("faturalar:oku")),
    db: AsyncSession = Depends(get_db),
):
    return await p.faturalar(db, kimlik, durum=durum, hesap=hesap, **sayfa)


@router.get("/faturalar/{fatura_id}", response_model=sema.Fatura, responses=HATA_YANITLARI, summary="Faturayı getir")
async def fatura(fatura_id: int, kimlik: ApiKimlik = Depends(kapsam_gerekli("faturalar:oku")), db: AsyncSession = Depends(get_db)):
    return await p.fatura(db, kimlik, fatura_id)


# ---------------------------------------------------------------------------
# Destek
# ---------------------------------------------------------------------------
@router.get("/destek", response_model=sema.DestekSayfasi, responses=HATA_YANITLARI, summary="Destek taleplerini listele")
async def talepler(
    durum: Optional[str] = Query(None, description="open | answered | closed"),
    hesap: Optional[str] = Query(None, description="Yalnız ajans anahtarı."),
    sayfa: Dict[str, Any] = Depends(_sayfa_parametreleri),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("destek:oku")),
    db: AsyncSession = Depends(get_db),
):
    return await p.talepler(db, kimlik, durum=durum, hesap=hesap, **sayfa)


@router.get("/destek/{talep_id}", response_model=sema.DestekTalebi, responses=HATA_YANITLARI, summary="Destek talebini getir")
async def talep(talep_id: int, kimlik: ApiKimlik = Depends(kapsam_gerekli("destek:oku")), db: AsyncSession = Depends(get_db)):
    return await p.talep(db, kimlik, talep_id)


@router.post("/destek", response_model=sema.DestekTalebi, status_code=201, responses=YAZMA_YANITLARI,
             summary="Destek talebi oluştur")
async def talep_olustur(
    request: Request,
    govde: sema.DestekOlustur,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", description=IDEM_ACIKLAMA),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("destek:yaz")),
    db: AsyncSession = Depends(get_db),
):
    return await _yazma(request, db, kimlik, idempotency_key, 201,
                        lambda: p.talep_olustur(db, kimlik, govde.model_dump(exclude_unset=True)), sema.DestekTalebi)


@router.post("/destek/{talep_id}/yanit", response_model=sema.DestekMesaji, status_code=201, responses=YAZMA_YANITLARI,
             summary="Destek talebini yanıtla")
async def talep_yanitla(
    talep_id: int,
    request: Request,
    govde: sema.DestekYanit,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", description=IDEM_ACIKLAMA),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("destek:yaz")),
    db: AsyncSession = Depends(get_db),
):
    return await _yazma(request, db, kimlik, idempotency_key, 201,
                        lambda: p.talep_yanitla(db, kimlik, talep_id, govde.model_dump()), sema.DestekMesaji)


# ---------------------------------------------------------------------------
# CRM (yalnız ajans)
# ---------------------------------------------------------------------------
@router.get("/crm/adaylar", response_model=sema.AdaySayfasi, responses=HATA_YANITLARI, summary="CRM adaylarını listele")
async def adaylar(
    asama: Optional[str] = Query(None),
    sayfa: Dict[str, Any] = Depends(_sayfa_parametreleri),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("crm:oku")),
    db: AsyncSession = Depends(get_db),
):
    return await p.adaylar(db, kimlik, asama=asama, **sayfa)


@router.get("/crm/adaylar/{aday_id}", response_model=sema.Aday, responses=HATA_YANITLARI, summary="CRM adayını getir")
async def aday(aday_id: int, kimlik: ApiKimlik = Depends(kapsam_gerekli("crm:oku")), db: AsyncSession = Depends(get_db)):
    return await p.aday(db, kimlik, aday_id)


@router.post("/crm/adaylar", response_model=sema.Aday, status_code=201, responses=YAZMA_YANITLARI, summary="CRM adayı oluştur")
async def aday_olustur(
    request: Request,
    govde: sema.AdayOlustur,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", description=IDEM_ACIKLAMA),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("crm:yaz")),
    db: AsyncSession = Depends(get_db),
):
    return await _yazma(request, db, kimlik, idempotency_key, 201,
                        lambda: p.aday_olustur(db, kimlik, govde.model_dump(exclude_unset=True)), sema.Aday)


# ---------------------------------------------------------------------------
# QR ve menü
# ---------------------------------------------------------------------------
@router.get("/qr", response_model=sema.QrSayfasi, responses=HATA_YANITLARI, summary="QR kodlarını listele")
async def qr_kodlari(
    hesap: Optional[str] = Query(None, description="Yalnız ajans anahtarı."),
    sayfa: Dict[str, Any] = Depends(_sayfa_parametreleri),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("qr:oku")),
    db: AsyncSession = Depends(get_db),
):
    return await p.qr_kodlari(db, kimlik, hesap=hesap, **sayfa)


@router.get("/qr/{qr_id}", response_model=sema.QrKodu, responses=HATA_YANITLARI, summary="QR kodunu getir")
async def qr_kodu(qr_id: int, kimlik: ApiKimlik = Depends(kapsam_gerekli("qr:oku")), db: AsyncSession = Depends(get_db)):
    return await p.qr_kodu(db, kimlik, qr_id)


@router.get("/menuler", response_model=sema.MenuSayfasi, responses=HATA_YANITLARI, summary="Menü / katalog mağazalarını listele")
async def menuler(
    hesap: Optional[str] = Query(None, description="Yalnız ajans anahtarı."),
    sayfa: Dict[str, Any] = Depends(_sayfa_parametreleri),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("menu:oku")),
    db: AsyncSession = Depends(get_db),
):
    return await p.menuler(db, kimlik, hesap=hesap, **sayfa)


@router.get("/menuler/{magaza_id}/siparisler", response_model=sema.SiparisSayfasi, responses=HATA_YANITLARI,
            summary="Mağazanın siparişleri")
async def menu_siparisleri(
    magaza_id: int,
    durum: Optional[str] = Query(None, description="yeni | hazirlaniyor | teslim_edildi | iptal"),
    sayfa: Dict[str, Any] = Depends(_sayfa_parametreleri),
    kimlik: ApiKimlik = Depends(kapsam_gerekli("menu:oku")),
    db: AsyncSession = Depends(get_db),
):
    return await p.menu_siparisleri(db, kimlik, magaza_id, durum=durum, **sayfa)


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------
def _izinli_kokenler() -> set:
    import os

    site = (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")
    return {site, "https://mehmetkuru.dev", "https://www.mehmetkuru.dev"}


def _mcp_hata(durum: int, kod: int, mesaj: str, basliklar: Optional[Dict[str, str]] = None) -> JSONResponse:
    return JSONResponse(status_code=durum, content={"jsonrpc": "2.0", "id": None, "error": {"code": kod, "message": mesaj}},
                        headers=basliklar)


@router.post("/mcp", include_in_schema=False)
async def mcp(request: Request, db: AsyncSession = Depends(get_db)):
    from services import mcp_sunucu as m

    # DNS yeniden bağlama koruması (spesifikasyon): tarayıcıdan gelen istekte Origin izinli olmalı.
    koken = request.headers.get("origin")
    if koken and koken.rstrip("/") not in _izinli_kokenler():
        return _mcp_hata(403, m.GECERSIZ_ISTEK, "Origin not allowed")
    surum = request.headers.get("mcp-protocol-version")
    if surum and surum not in m.PROTOKOL_SURUMLERI:
        return _mcp_hata(400, m.GECERSIZ_ISTEK, f"Unsupported MCP-Protocol-Version: {surum}")
    kabul = (request.headers.get("accept") or "").lower()
    if kabul and not any(t in kabul for t in ("application/json", "*/*", "application/*")):
        return _mcp_hata(406, m.GECERSIZ_ISTEK, "Accept must include application/json")
    kimlik = await kimlik_dogrula(db, request)
    try:
        govde = json.loads(await request.body() or b"null")
    except (ValueError, UnicodeDecodeError):
        return _mcp_hata(400, m.PARSE_HATASI, "Parse error")
    yanit = await m.govde_isle(db, kimlik, govde)
    if yanit is None:
        return Response(status_code=202)
    return JSONResponse(status_code=200, content=yanit)


@router.get("/mcp", include_in_schema=False)
async def mcp_akis():
    # Sunucudan istemciye ayrı akış (SSE) sunulmuyor — spesifikasyonda izinli yanıt 405.
    return Response(status_code=405, headers={"Allow": "POST"})


@router.delete("/mcp", include_in_schema=False)
async def mcp_oturum_sil():
    # Durumsuz sunucu: oturum kimliği verilmiyor, sonlandırılacak oturum yok.
    return Response(status_code=405, headers={"Allow": "POST"})


# ---------------------------------------------------------------------------
# OpenAPI (yalnız bu API)
# ---------------------------------------------------------------------------
_openapi_onbellek: Dict[str, Any] = {}

ACIKLAMA = """mehmetkuru.dev ajans portalının herkese açık API'si.

**Kimlik:** `Authorization: Bearer mk_live_…` ya da `X-API-Key: mk_live_…`. Anahtarı panelde
**API ve webhook** sekmesinden oluşturun; yalnız oluşturulduğunda bir kez gösterilir.

**Kapsamlar:** her uç bir kapsam ister (`projeler:oku`, `gorevler:yaz` …); anahtarda yoksa 403 `kapsam_yetersiz`.
Müşteri anahtarı yalnız kendi hesabını görür (başka hesabın kaydı 404); ajans anahtarı bütün hesapları
(`hesap` süzgeciyle daraltılabilir).

**Sayfalama:** `limit` (1–100) + `cursor` → yanıt `{veri, sonraki_cursor, daha_var}`; `updated_since` (ISO 8601) ile
yalnız değişenler.

**Hatalar:** `{"hata": {"kod": "...", "mesaj": "..."}}`. **Hız sınırı:** anahtar başına dakikada N istek (429 +
`Retry-After`). **Idempotency:** yazma uçlarında `Idempotency-Key` başlığı (24 saat).

**Webhook imzası:** `MK-Webhook-Imza: v1=<hex HMAC-SHA256(gizli, MK-Webhook-Zaman + "." + gövde)>`; 5 dakikadan eski
zaman damgasını reddedin.

**MCP:** `POST /api/public/v1/mcp` (Streamable HTTP, aynı anahtar).
"""


def openapi_belgesi() -> Dict[str, Any]:
    if "belge" in _openapi_onbellek:
        return _openapi_onbellek["belge"]
    rotalar = [r for r in router.routes if getattr(r, "include_in_schema", True)]
    belge = get_openapi(
        title="mehmetkuru.dev API",
        version=SURUM,
        description=ACIKLAMA,
        routes=rotalar,
        servers=[{"url": "https://mehmetkuru.dev"}],
    )
    belge.setdefault("components", {}).setdefault("securitySchemes", {}).update({
        "bearer": {"type": "http", "scheme": "bearer", "bearerFormat": "mk_live_…"},
        "apiAnahtari": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
    })
    belge["security"] = [{"bearer": []}, {"apiAnahtari": []}]
    # Her ucun kapsamı (bağımlılık adından) belgeye — panel bunu gösteriyor.
    for r in rotalar:
        if not isinstance(r, APIRoute):
            continue
        kapsam = None
        for bag in r.dependant.dependencies:
            ad = getattr(bag.call, "__name__", "")
            if ad.startswith("kapsam_"):
                kapsam = ad[len("kapsam_"):].replace("_", ":", 1)
        for metot in r.methods:
            islem = belge.get("paths", {}).get(r.path_format, {}).get(metot.lower())
            if islem is not None:
                islem["x-kapsam"] = kapsam
    _openapi_onbellek["belge"] = belge
    return belge


@router.get("/openapi.json", include_in_schema=False)
async def openapi_json():
    return JSONResponse(openapi_belgesi(), headers={"Cache-Control": "public, max-age=300"})
