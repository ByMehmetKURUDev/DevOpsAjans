"""Faz 4A — uzak MCP sunucusu (Model Context Protocol, Streamable HTTP, durumsuz).

Neden SDK'nın sunucu bileşeni değil?
------------------------------------
`mcp` paketi (1.27) `StreamableHTTPSessionManager` ile Starlette uygulaması
sunuyor; ama uzun ömürlü bir görev grubu (`session_manager.run()`)
uygulamanın yaşam döngüsünde başlatılmalı ve uç, FastAPI router'ı değil ham
ASGI `Mount` olarak bağlanmalı. Bu depoda router'lar otomatik keşfediliyor,
yaşam döngüsü ortak (main.py) ve testler yaşam döngüsünü çalıştırmıyor.
Araçlar da istek başına değişiyor (anahtarın kapsamları). Bu yüzden
protokolün ihtiyacımız olan kısmı burada elle, spesifikasyona uygun yazıldı:

* Taşıma: Streamable HTTP, DURUMSUZ ve yalnız JSON yanıt — her POST bir
  JSON-RPC iletisi (ya da dizisi) taşır; istekler `application/json` yanıt,
  bildirimler 202 alır. Oturum kimliği (`Mcp-Session-Id`) verilmiyor; GET
  (sunucudan akış) ve DELETE 405. Yanıt akış (SSE) olmadığı için Pages
  vekilinden (`functions/api/[[path]].js`) sıradan JSON gibi geçiyor.
* Yöntemler: `initialize`, `ping`, `tools/list`, `tools/call`; bildirimler
  (`notifications/*`) sessizce kabul. Desteklenen sürümler
  `PROTOKOL_SURUMLERI`; istemci desteklenmeyen bir sürüm isterse en yenisi önerilir.
* Kimlik: aynı API anahtarı (`Authorization: Bearer mk_live_…`). Araç listesi
  anahtarın kapsamlarına göre — yazma kapsamı yoksa yazma araçları HİÇ
  görünmüyor; listede olmayan araç çağrısı "bilinmeyen araç".
* Araçlar REST ile AYNI servis fonksiyonlarını çağırıyor (`services/public_api.py`):
  hesap izolasyonu, modül/kapsam denetimi tek yerde.

Uyumluluk testi SDK'nın kendi istemcisiyle yapılıyor (`ClientSession` +
`streamable_http_client`; bkz. tests/backend/test_api_erisimi.py).
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from services import public_api as p
from services.api_erisimi import ApiHatasi, ApiKimlik, kapsam_modulu_acik_mi
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PROTOKOL_SURUMLERI: Tuple[str, ...] = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
ONERILEN_SURUM = "2025-06-18"
SUNUCU = {"name": "mehmetkuru-dev", "title": "mehmetkuru.dev", "version": "1.0.0"}
TALIMAT = (
    "mehmetkuru.dev ajans portalının verileri: projeler, görevler, faturalar, destek talepleri"
    " (ve ajans anahtarında CRM adayları). Araçlar yalnız API anahtarının kapsamındaki işlemleri"
    " gösterir. Listeleme araçları sayfalıdır: yanıttaki `sonraki_cursor` değerini `cursor` olarak"
    " vererek devam edin. Tarihler ISO 8601 (UTC). Yazma araçları gerçek kayıt oluşturur — kullanıcı"
    " açıkça istemedikçe çağırmayın."
)

# JSON-RPC hata kodları
PARSE_HATASI = -32700
GECERSIZ_ISTEK = -32600
YONTEM_YOK = -32601
GECERSIZ_PARAMETRE = -32602
IC_HATA = -32603


@dataclass(frozen=True)
class Arac:
    ad: str
    baslik: str
    aciklama: str
    kapsam: Optional[str]
    giris: Dict[str, Any]
    calistir: Callable[[AsyncSession, ApiKimlik, Dict[str, Any]], Awaitable[Any]]
    yazma: bool = False
    yalniz_ajans: bool = False

    def tanim(self) -> Dict[str, Any]:
        return {
            "name": self.ad,
            "title": self.baslik,
            "description": self.aciklama,
            "inputSchema": self.giris,
            "annotations": {
                "title": self.baslik,
                "readOnlyHint": not self.yazma,
                "destructiveHint": False,
                "idempotentHint": not self.yazma,
                "openWorldHint": False,
            },
        }


def _sema(ozellikler: Dict[str, Any], zorunlu: Tuple[str, ...] = ()) -> Dict[str, Any]:
    s: Dict[str, Any] = {"type": "object", "properties": ozellikler, "additionalProperties": False}
    if zorunlu:
        s["required"] = list(zorunlu)
    return s


_SAYFA = {
    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Sayfa boyutu (varsayılan 25)."},
    "cursor": {"type": "string", "description": "Önceki yanıttaki `sonraki_cursor`."},
    "updated_since": {"type": "string", "description": "Yalnız bu andan sonra güncellenenler (ISO 8601)."},
}
_HESAP = {"hesap": {"type": "string", "description": "Yalnız ajans anahtarı: müşteri hesabı (e-posta) süzgeci."}}
_ONCELIK = {"type": "string", "enum": list(p.ONCELIKLER)}
_GOREV_DURUMU = {"type": "string", "enum": list(p.GOREV_DURUMLARI)}


def _tamsayi(args: Dict[str, Any], ad: str, zorunlu: bool = True) -> Optional[int]:
    deger = args.get(ad)
    if deger is None:
        if zorunlu:
            raise ApiHatasi(400, "gecersiz_istek", mesaj=f"`{ad}` gerekli.")
        return None
    if isinstance(deger, bool):
        raise ApiHatasi(400, "gecersiz_istek", mesaj=f"`{ad}` tamsayı olmalı.")
    try:
        return int(deger)
    except (TypeError, ValueError):
        raise ApiHatasi(400, "gecersiz_istek", mesaj=f"`{ad}` tamsayı olmalı.")


def _sayfa_args(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"limit": args.get("limit"), "cursor": args.get("cursor"), "updated_since": args.get("updated_since")}


def _alanlar(args: Dict[str, Any], izinli: Tuple[str, ...]) -> Dict[str, Any]:
    return {k: v for k, v in args.items() if k in izinli}


ARACLAR: Tuple[Arac, ...] = (
    Arac(
        "hesap_ozeti", "Hesap özeti",
        "API anahtarının bağlı olduğu hesabın özeti: sahip (ajans/müşteri), anahtarın kapsamları ve kapsamdaki"
        " kayıt sayıları (proje, görev, açık destek talebi, ödenmemiş fatura). Account summary for this API key.",
        None, _sema({}), lambda db, k, a: p.hesap_ozeti(db, k),
    ),
    Arac(
        "projeleri_listele", "Projeleri listele",
        "Projeleri listeler (sayfalı). Her projede başlık, kategori, durum, aşama, ilerleme yüzdesi. Lists projects.",
        "projeler:oku", _sema({**_HESAP, **_SAYFA}),
        lambda db, k, a: p.projeler(db, k, hesap=a.get("hesap"), **_sayfa_args(a)),
    ),
    Arac(
        "proje_getir", "Projeyi getir", "Tek bir projenin ayrıntısı. Gets one project by id.",
        "projeler:oku", _sema({"proje_id": {"type": "integer"}}, ("proje_id",)),
        lambda db, k, a: p.proje(db, k, _tamsayi(a, "proje_id")),
    ),
    Arac(
        "gorevleri_listele", "Görevleri listele",
        "Proje görevlerini listeler (sayfalı); `proje_id` ve `durum` ile süzülebilir. Müşteri anahtarında yalnız"
        " müşteriye görünen görevler gelir. Lists project tasks.",
        "gorevler:oku",
        _sema({"proje_id": {"type": "integer"}, "durum": _GOREV_DURUMU, **_HESAP, **_SAYFA}),
        lambda db, k, a: p.gorevler(db, k, proje_id=_tamsayi(a, "proje_id", False), durum=a.get("durum"),
                                    hesap=a.get("hesap"), **_sayfa_args(a)),
    ),
    Arac(
        "gorev_olustur", "Görev oluştur",
        "Bir projeye yeni görev ekler. Müşteri anahtarıyla açılan görev müşteriye görünür ve `yapilacak` durumunda"
        " başlar. Creates a task in a project.",
        "gorevler:yaz",
        _sema({
            "proje_id": {"type": "integer"},
            "baslik": {"type": "string", "minLength": 1, "maxLength": 200},
            "aciklama": {"type": "string", "maxLength": 4000},
            "oncelik": _ONCELIK,
            "bitis_tarihi": {"type": "string", "description": "YYYY-MM-DD"},
            "durum": {**_GOREV_DURUMU, "description": "Yalnız ajans anahtarı."},
            "musteriye_gorunur": {"type": "boolean", "description": "Yalnız ajans anahtarı."},
        }, ("proje_id", "baslik")),
        lambda db, k, a: p.gorev_olustur(db, k, {**_alanlar(a, ("baslik", "aciklama", "oncelik", "bitis_tarihi", "durum",
                                                                 "musteriye_gorunur")), "proje_id": _tamsayi(a, "proje_id")}),
        yazma=True,
    ),
    Arac(
        "gorev_guncelle", "Görevi güncelle",
        "Görevin başlık, açıklama, öncelik, bitiş tarihi ya da durumunu değiştirir (`tamam` için bağımlılıklar bitmiş"
        " olmalı). Müşteri anahtarı yalnız kendi tarafının açtığı görevi değiştirebilir. Updates a task.",
        "gorevler:yaz",
        _sema({
            "gorev_id": {"type": "integer"},
            "baslik": {"type": "string", "minLength": 1, "maxLength": 200},
            "aciklama": {"type": "string", "maxLength": 4000},
            "oncelik": _ONCELIK,
            "bitis_tarihi": {"type": "string", "description": "YYYY-MM-DD; boş metin tarihi kaldırır."},
            "durum": _GOREV_DURUMU,
        }, ("gorev_id",)),
        lambda db, k, a: p.gorev_guncelle(db, k, _tamsayi(a, "gorev_id"),
                                          _alanlar(a, ("baslik", "aciklama", "oncelik", "bitis_tarihi", "durum"))),
        yazma=True,
    ),
    Arac(
        "faturalari_listele", "Faturaları listele",
        "Faturaları listeler (sayfalı): numara, tutar, para birimi, durum (unpaid/paid/overdue…), vade. Lists invoices.",
        "faturalar:oku", _sema({"durum": {"type": "string"}, **_HESAP, **_SAYFA}),
        lambda db, k, a: p.faturalar(db, k, durum=a.get("durum"), hesap=a.get("hesap"), **_sayfa_args(a)),
    ),
    Arac(
        "destek_talepleri_listele", "Destek taleplerini listele",
        "Destek taleplerini listeler (sayfalı): konu, ilk mesaj, durum (open/answered/closed), öncelik. Lists support tickets.",
        "destek:oku", _sema({"durum": {"type": "string"}, **_HESAP, **_SAYFA}),
        lambda db, k, a: p.talepler(db, k, durum=a.get("durum"), hesap=a.get("hesap"), **_sayfa_args(a)),
    ),
    Arac(
        "destek_talebi_getir", "Destek talebini getir",
        "Tek bir destek talebi ve bütün yazışması (mesajlar: musteri/ajans/otomatik). Gets a ticket with its thread.",
        "destek:oku", _sema({"talep_id": {"type": "integer"}}, ("talep_id",)),
        lambda db, k, a: p.talep(db, k, _tamsayi(a, "talep_id")),
    ),
    Arac(
        "destek_talebi_olustur", "Destek talebi oluştur",
        "Yeni destek talebi açar (ajansa bildirim gider). Ajans anahtarında `hesap` zorunlu. Opens a support ticket.",
        "destek:yaz",
        _sema({
            "konu": {"type": "string", "minLength": 1, "maxLength": 200},
            "mesaj": {"type": "string", "minLength": 1, "maxLength": 10000},
            "oncelik": _ONCELIK,
            "proje_id": {"type": "integer"},
            "hesap": {"type": "string", "description": "Yalnız ajans anahtarı: müşteri hesabı (zorunlu)."},
        }, ("konu", "mesaj")),
        lambda db, k, a: p.talep_olustur(db, k, {**_alanlar(a, ("konu", "mesaj", "oncelik", "hesap")),
                                                 "proje_id": _tamsayi(a, "proje_id", False)}),
        yazma=True,
    ),
    Arac(
        "destek_talebini_yanitla", "Destek talebini yanıtla",
        "Destek talebine yazışma mesajı ekler (müşteri anahtarında müşteri, ajans anahtarında ajans yanıtı)."
        " Replies to a support ticket.",
        "destek:yaz",
        _sema({"talep_id": {"type": "integer"}, "mesaj": {"type": "string", "minLength": 1, "maxLength": 10000}},
              ("talep_id", "mesaj")),
        lambda db, k, a: p.talep_yanitla(db, k, _tamsayi(a, "talep_id"), {"mesaj": a.get("mesaj")}),
        yazma=True,
    ),
    Arac(
        "crm_adaylarini_listele", "CRM adaylarını listele",
        "Ajansın satış hunisindeki adayları listeler (sayfalı): ad, firma, iletişim, kaynak, aşama, tahmini değer."
        " Lists CRM leads (agency only).",
        "crm:oku", _sema({"asama": {"type": "string"}, **_SAYFA}),
        lambda db, k, a: p.adaylar(db, k, asama=a.get("asama"), **_sayfa_args(a)),
        yalniz_ajans=True,
    ),
    Arac(
        "crm_adayi_olustur", "CRM adayı oluştur",
        "CRM'e yeni aday ekler (ilk aşamada). Aynı e-postada açık aday varsa hata döner. Creates a CRM lead (agency only).",
        "crm:yaz",
        _sema({
            "ad": {"type": "string", "minLength": 1, "maxLength": 120},
            "firma": {"type": "string", "maxLength": 160},
            "email": {"type": "string", "maxLength": 254},
            "telefon": {"type": "string", "maxLength": 40},
            "deger_tahmini": {"type": "number", "minimum": 0},
            "para_birimi": {"type": "string", "enum": ["TRY", "USD", "EUR", "GBP"]},
            "notlar": {"type": "string", "maxLength": 10000},
        }, ("ad",)),
        lambda db, k, a: p.aday_olustur(db, k, _alanlar(a, ("ad", "firma", "email", "telefon", "deger_tahmini",
                                                            "para_birimi", "notlar"))),
        yazma=True, yalniz_ajans=True,
    ),
)
ARAC_SOZLUGU: Dict[str, Arac] = {a.ad: a for a in ARACLAR}


async def gorunen_araclar(db: AsyncSession, kimlik: ApiKimlik) -> List[Arac]:
    """Anahtarın kapsamına (ve müşteride modülün açıklığına) göre görünen araçlar."""
    sonuc: List[Arac] = []
    for a in ARACLAR:
        if a.yalniz_ajans and not kimlik.ajans:
            continue
        if a.kapsam is not None:
            if not kimlik.kapsam_var(a.kapsam):
                continue
            if not await kapsam_modulu_acik_mi(db, kimlik, a.kapsam):
                continue
        sonuc.append(a)
    return sonuc


def _hata(kimlik_id: Any, kod: int, mesaj: str, veri: Any = None) -> Dict[str, Any]:
    h: Dict[str, Any] = {"code": kod, "message": mesaj}
    if veri is not None:
        h["data"] = veri
    return {"jsonrpc": "2.0", "id": kimlik_id, "error": h}


def _sonuc(kimlik_id: Any, sonuc: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": kimlik_id, "result": sonuc}


def surum_sec(istenen: Any) -> str:
    return istenen if isinstance(istenen, str) and istenen in PROTOKOL_SURUMLERI else ONERILEN_SURUM


async def _arac_cagir(db: AsyncSession, kimlik: ApiKimlik, ad: str, args: Dict[str, Any]) -> Dict[str, Any]:
    arac = ARAC_SOZLUGU.get(ad)
    if arac is None or arac not in await gorunen_araclar(db, kimlik):
        raise _BilinmeyenArac(ad)
    try:
        veri = await arac.calistir(db, kimlik, args)
    except ApiHatasi as h:
        await db.rollback()
        metin = json.dumps({"hata": {"kod": h.kod, "mesaj": h.mesaj, **h.ek}}, ensure_ascii=False, default=str)
        return {"content": [{"type": "text", "text": metin}], "isError": True}
    except Exception as h:  # noqa: BLE001
        await db.rollback()
        detay = getattr(h, "detail", None)
        if isinstance(detay, dict) and detay.get("kod"):
            metin = json.dumps({"hata": {"kod": detay["kod"], "mesaj": detay["kod"]}}, ensure_ascii=False)
            return {"content": [{"type": "text", "text": metin}], "isError": True}
        logger.exception("MCP aracı hata verdi: %s", ad)
        return {"content": [{"type": "text", "text": '{"hata":{"kod":"sunucu_hatasi","mesaj":"Beklenmeyen hata"}}'}],
                "isError": True}
    metin = json.dumps(veri, ensure_ascii=False, default=str)
    sonuc: Dict[str, Any] = {"content": [{"type": "text", "text": metin}], "isError": False}
    if isinstance(veri, dict):
        sonuc["structuredContent"] = veri
    return sonuc


class _BilinmeyenArac(Exception):
    pass


async def ileti_isle(db: AsyncSession, kimlik: ApiKimlik, ileti: Any) -> Optional[Dict[str, Any]]:
    """Tek JSON-RPC iletisi → yanıt (bildirim/yanıt iletisiyse None)."""
    if not isinstance(ileti, dict) or ileti.get("jsonrpc") != "2.0":
        return _hata(ileti.get("id") if isinstance(ileti, dict) else None, GECERSIZ_ISTEK, "Invalid Request")
    yontem = ileti.get("method")
    kimlik_id = ileti.get("id")
    bildirim = "id" not in ileti
    if yontem is None:
        # İstemciden gelen yanıt (result/error): sunucu istek göndermiyor, yok say.
        return None
    if not isinstance(yontem, str):
        return None if bildirim else _hata(kimlik_id, GECERSIZ_ISTEK, "Invalid Request")
    if bildirim:
        return None  # notifications/initialized, notifications/cancelled …
    params = ileti.get("params") or {}
    if not isinstance(params, dict):
        return _hata(kimlik_id, GECERSIZ_PARAMETRE, "Invalid params")

    if yontem == "initialize":
        return _sonuc(kimlik_id, {
            "protocolVersion": surum_sec(params.get("protocolVersion")),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SUNUCU,
            "instructions": TALIMAT,
        })
    if yontem == "ping":
        return _sonuc(kimlik_id, {})
    if yontem == "tools/list":
        return _sonuc(kimlik_id, {"tools": [a.tanim() for a in await gorunen_araclar(db, kimlik)]})
    if yontem == "tools/call":
        ad = params.get("name")
        args = params.get("arguments") or {}
        if not isinstance(ad, str) or not isinstance(args, dict):
            return _hata(kimlik_id, GECERSIZ_PARAMETRE, "Invalid params")
        try:
            return _sonuc(kimlik_id, await _arac_cagir(db, kimlik, ad, args))
        except _BilinmeyenArac:
            return _hata(kimlik_id, GECERSIZ_PARAMETRE, f"Unknown tool: {ad}")
    return _hata(kimlik_id, YONTEM_YOK, f"Method not found: {yontem}")


async def govde_isle(db: AsyncSession, kimlik: ApiKimlik, govde: Any) -> Optional[Any]:
    """Tekil ileti ya da dizi (2025-03-26 toplu biçimi). Hiç yanıt yoksa None (HTTP 202)."""
    if isinstance(govde, list):
        if not govde:
            return _hata(None, GECERSIZ_ISTEK, "Invalid Request")
        yanitlar = [y for y in [await ileti_isle(db, kimlik, i) for i in govde] if y is not None]
        return yanitlar or None
    return await ileti_isle(db, kimlik, govde)
