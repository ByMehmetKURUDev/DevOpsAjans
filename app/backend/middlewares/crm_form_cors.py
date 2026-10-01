"""Faz 3C — gömülebilir CRM formunun CORS kuralı (`/api/v1/crm/form/...`).

Uygulamanın genel CORS ara katmanı her kökene izin veriyor (panel ve site
aynı köken; vekil üzerinden geliyor). Gömülü form için bu yetmez: yanıtı
yalnız formun izinli alan adları (+ site) okuyabilmeli. Bu ara katman genel
CORS'un DIŞINDA çalışıyor (main.py'de ondan sonra ekleniyor):

* Ön kontrol (OPTIONS + Access-Control-Request-Method): formun izinli alan
  adlarına bakıp 204 (izinli: köken yansıtılır) ya da 403 (CORS başlığı yok)
  dönüyor; genel ara katmana hiç gitmiyor.
* Diğer istekler: uç kökeni reddederse yanıta `x-mk-cors: ret` koyuyor;
  burada o işaret görülünce Access-Control-* başlıkları ve işaretin kendisi
  siliniyor — tarayıcı yanıtı izinsiz siteye göstermiyor.

Saf ASGI (BaseHTTPMiddleware değil): denetim bağlamının `ContextVar`'ı bozulmuyor.
"""

import logging

from starlette.datastructures import MutableHeaders

logger = logging.getLogger(__name__)

ONEK = "/api/v1/crm/form/"
ISARET = "x-mk-cors"
SILINECEKLER = (
    "access-control-allow-origin", "access-control-allow-credentials", "access-control-expose-headers",
    "access-control-allow-methods", "access-control-allow-headers", ISARET,
)


def _baslik(scope, ad: bytes) -> str:
    for a, d in scope.get("headers") or ():
        if a == ad:
            return d.decode("latin-1")
    return ""


async def _izinli_mi(anahtar: str, koken: str) -> bool:
    from core.database import db_manager
    from models.crm import CrmFormlari
    from services.crm_form import koken_izinli_mi
    from sqlalchemy import select

    if not anahtar or db_manager.async_session_maker is None:
        return False
    async with db_manager.async_session_maker() as db:
        f = (
            await db.execute(select(CrmFormlari).where(CrmFormlari.genel_anahtar == anahtar, CrmFormlari.aktif.is_(True)))
        ).scalars().first()
        return bool(f) and koken_izinli_mi(koken, f.izinli_alanlar)


class CrmFormCorsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        yol = str(scope.get("path") or "")
        if scope.get("type") != "http" or not yol.startswith(ONEK):
            await self.app(scope, receive, send)
            return

        koken = _baslik(scope, b"origin")
        if scope.get("method") == "OPTIONS" and koken and _baslik(scope, b"access-control-request-method"):
            anahtar = yol[len(ONEK):].split("/")[0]
            try:
                izinli = await _izinli_mi(anahtar, koken)
            except Exception:  # noqa: BLE001 - karar verilemezse kapalı
                logger.exception("CRM form ön kontrolü yapılamadı")
                izinli = False
            if izinli:
                basliklar = [
                    (b"access-control-allow-origin", koken.encode("latin-1")),
                    (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                    (b"access-control-allow-headers", b"content-type"),
                    (b"access-control-max-age", b"600"),
                    (b"vary", b"Origin"),
                    (b"content-length", b"0"),
                ]
                await send({"type": "http.response.start", "status": 204, "headers": basliklar})
            else:
                await send({"type": "http.response.start", "status": 403,
                            "headers": [(b"content-length", b"0"), (b"vary", b"Origin")]})
            await send({"type": "http.response.body", "body": b""})
            return

        async def gonder(mesaj):
            if mesaj.get("type") == "http.response.start":
                basliklar = MutableHeaders(scope=mesaj)
                if basliklar.get(ISARET) == "ret":
                    for ad in SILINECEKLER:
                        if ad in basliklar:
                            del basliklar[ad]
            await send(mesaj)

        await self.app(scope, receive, gonder)
