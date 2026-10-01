"""Faz 2E — etkin hesap kararı: istek başında bir kez, `X-MK-Hesap` başlığından.

Düzen 2D'deki oturum bekçisiyle aynı (bkz. `middlewares/oturum_bekcisi.py`):
uçların çoğu jetonu eşzamanlı `_yonetici_mi(request)` ile çözüyor ve
veritabanına gidemiyor. Üyelik kararı burada (async) veriliyor ve isteğin
`scope`'una yazılıyor (`KAPSAM_ANAHTARI`); ortak yardımcı
(`dependencies/hesap_baglami.py`) oradan okuyor.

Karar
-----
* Başlık yok, boş ya da kişinin kendi e-postası → hiçbir şey yazılmaz
  (yardımcı kişinin kendi hesabını tam yetkiyle kurar; eski davranış).
* Yönetici (role=admin) → başlık YOK SAYILIR.
* Jeton geçersiz / oturum iptal → dokunulmaz (uç zaten 401 veriyor).
* Kişi o hesapta AKTİF üye → {"hesap_email", "rol", "izinler", "uye_id"}.
* Değilse → {"hata": "hesap_uyesi_degil", ...}: yardımcı 403 veriyor —
  sessizce kişinin kendi hesabına düşülmüyor.

Saf ASGI (BaseHTTPMiddleware değil): denetim bağlamının `ContextVar`'ı bozulmuyor.
"""

import logging

from services import hesap_ekibi, oturumlar

logger = logging.getLogger(__name__)

KAPSAM_ANAHTARI = "mk_hesap"
BASLIK = b"x-mk-hesap"


def _basliklar(scope):
    jeton, hesap = "", ""
    for ad, deger in scope.get("headers") or ():
        if ad == b"authorization" and not jeton:
            metin = deger.decode("latin-1").strip()
            if metin.lower().startswith("bearer "):
                jeton = metin.split(" ", 1)[1].strip()
        elif ad == BASLIK and not hesap:
            hesap = deger.decode("latin-1")
    return jeton, hesap_ekibi.eposta_duzelt(hesap)


class HesapBaglamiMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and str(scope.get("path") or "").startswith("/api/"):
            try:
                await self._karar(scope)
            except Exception:  # noqa: BLE001 - karar verilemezse kapalı kal
                logger.exception("Hesap bağlamı kurulamadı")
                scope[KAPSAM_ANAHTARI] = {"hata": "hesap_dogrulanamadi"}
        await self.app(scope, receive, send)

    async def _karar(self, scope) -> None:
        jeton, hesap = _basliklar(scope)
        if not jeton or not hesap:
            return
        durum = scope.get(oturumlar.KAPSAM_ANAHTARI)
        if durum and durum.get("iptal"):
            return
        from core.auth import AccessTokenError, decode_access_token

        try:
            payload = decode_access_token(jeton)
        except AccessTokenError:
            return
        if payload.get("role") == "admin":
            return
        kisi = hesap_ekibi.eposta_duzelt(payload.get("email"))
        if not kisi or hesap == kisi:
            return
        bilgi = await hesap_ekibi.uyelik_karari(kisi, hesap)
        if bilgi is None:
            scope[KAPSAM_ANAHTARI] = {"hata": "hesap_uyesi_degil", "hesap_email": hesap, "kisi_email": kisi}
            return
        scope[KAPSAM_ANAHTARI] = {
            "hesap_email": hesap,
            "kisi_email": kisi,
            "rol": bilgi["rol"],
            "izinler": tuple(bilgi["izinler"]),
            "uye_id": bilgi["id"],
        }
