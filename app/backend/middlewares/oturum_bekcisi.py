"""Oturum bekçisi: jetonun iptal edilip edilmediğine istek başında bir kez karar verir.

Neden ara katman?
-----------------
Jeton iki ayrı yoldan çözülüyor: async `get_current_user` bağımlılığı ve
birçok router'ın kullandığı eşzamanlı `_yonetici_mi(request)`. Eşzamanlı yol
veritabanına gidemediği için karar burada (async) veriliyor ve isteğin
`scope`'una yazılıyor (`services.oturumlar.KAPSAM_ANAHTARI`); iki yol da
oradan okuyor. İmzası/süresi geçersiz jetonlara bakılmıyor — onları
zaten iki yol da reddediyor.

Saf ASGI (BaseHTTPMiddleware değil): isteği ayrı göreve taşımıyor, denetim
bağlamının `ContextVar`'ı bozulmuyor.
"""

import logging

from services import oturumlar

logger = logging.getLogger(__name__)


def _jeton(scope) -> str:
    for ad, deger in scope.get("headers") or ():
        if ad == b"authorization":
            metin = deger.decode("latin-1").strip()
            if metin.lower().startswith("bearer "):
                return metin.split(" ", 1)[1].strip()
            return ""
    return ""


class OturumBekcisiMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and str(scope.get("path") or "").startswith("/api/"):
            jeton = _jeton(scope)
            if jeton:
                try:
                    from core.auth import AccessTokenError, decode_access_token

                    try:
                        payload = decode_access_token(jeton)
                    except AccessTokenError:
                        payload = None
                    if payload is not None:
                        scope[oturumlar.KAPSAM_ANAHTARI] = await oturumlar.jeton_denetle(payload)
                except Exception:  # noqa: BLE001 - bekçi hatası isteği düşürmesin
                    logger.exception("Oturum bekçisi çalışamadı")
        await self.app(scope, receive, send)
