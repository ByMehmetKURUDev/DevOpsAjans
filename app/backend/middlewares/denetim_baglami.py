"""Denetim bağlamı: her HTTP isteği için "kim yapıyor" bilgisini kurar.

Saf ASGI ara katmanı (BaseHTTPMiddleware değil): isteği ayrı bir göreve
taşımadığı için `ContextVar` uç fonksiyonuna ve SQLAlchemy'nin flush
olayına olduğu gibi ulaşıyor. Jeton burada çözülmüyor; yalnız istek
bağlama konuyor, çözüm ilk denetim satırı yazılırken yapılıyor
(bkz. `services/denetim.py`).
"""

from services.denetim import baglam_birak, baglam_kur
from starlette.requests import Request


class DenetimBaglamiMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        jeton = baglam_kur(Request(scope))
        try:
            await self.app(scope, receive, send)
        finally:
            baglam_birak(jeton)
