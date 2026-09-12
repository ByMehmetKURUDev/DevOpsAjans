"""Varlık (entity) uçları için yetki bekçisi.

Sorun
-----
Üretilmiş entity router'larının hiçbirinde yetki bağımlılığı yoktu:
dokuz tablonun okuma **ve yazma** uçlarının tamamı kimlik doğrulaması
istemeden çalışıyordu. Yani internetteki herhangi biri faturaları ve
iletişim mesajlarını okuyabiliyor, blog yazılarını ve site ayarlarını
değiştirebiliyor ya da silebiliyordu.

Yaklaşım
--------
Uç uca (81 imza) tek tek bağımlılık eklemek yerine, router düzeyinde tek
bir bekçi kullanılıyor: her router'a `dependencies=[Depends(entity_guard)]`
ekleniyor, kural tablosu burada tek yerde duruyor. Böylece politikayı
okumak ve değiştirmek için tek dosyaya bakmak yeterli.

Kural tablosu
-------------
Sitenin kendisinin giriş yapmadan göstermesi gereken şeyler açık kalıyor
(portfolyo, blog, site ayarları); geri kalan her okuma oturum, her yazma
yönetici yetkisi istiyor. İletişim formunun POST'u bilerek açık — ziyaretçi
giriş yapmadan mesaj gönderebilmeli.
"""

import logging
from typing import Optional

from core.auth import AccessTokenError, decode_access_token
from fastapi import HTTPException, Request, status
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)

#: Giriş yapmadan okunabilen tablolar — sitenin kendisi bunları gösteriyor.
HERKESE_ACIK_OKUMA = {"projects", "blog_posts", "site_settings"}

#: Giriş yapmadan kayıt oluşturulabilen tablolar — iletişim formu.
HERKESE_ACIK_OLUSTURMA = {"inquiries"}

#: Oturum açmış herhangi bir kullanıcının kayıt oluşturabildiği tablolar.
OTURUMLA_OLUSTURMA = {"support_tickets"}

OKUMA_METOTLARI = {"GET", "HEAD", "OPTIONS"}
OLUSTURMA_METOTLARI = {"POST"}


def _tablo_adi(path: str) -> str:
    """`/api/v1/entities/invoices/all` -> `invoices`."""
    parcalar = [p for p in path.split("/") if p]
    try:
        return parcalar[parcalar.index("entities") + 1]
    except (ValueError, IndexError):
        return ""


def _istekteki_kullanici(request: Request) -> Optional[UserResponse]:
    """Authorization başlığındaki jetonu çözer; yoksa veya geçersizse None.

    `get_current_user` gibi hata fırlatmıyor — bekçi, kuralı uyguladıktan
    sonra hangi hatanın döneceğine kendisi karar veriyor.
    """
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None

    token = header.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        payload = decode_access_token(token)
    except AccessTokenError as exc:
        logger.debug("Jeton çözülemedi: %s", type(exc).__name__)
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    return UserResponse(
        id=user_id,
        email=payload.get("email", ""),
        name=payload.get("name"),
        role=payload.get("role", "user"),
        last_login=None,
    )


def _reddet(kod: int, mesaj: str) -> None:
    raise HTTPException(status_code=kod, detail=mesaj)


async def entity_guard(request: Request) -> None:
    """Router düzeyinde çalışan bekçi. Geçerse None döner, geçmezse 401/403."""
    tablo = _tablo_adi(request.url.path)
    metot = request.method.upper()
    kullanici = _istekteki_kullanici(request)

    # 1) Sitenin giriş yapmadan göstermesi gereken okumalar
    if metot in OKUMA_METOTLARI and tablo in HERKESE_ACIK_OKUMA:
        return

    # 2) İletişim formu: ziyaretçi mesaj bırakabilmeli
    if metot in OLUSTURMA_METOTLARI and tablo in HERKESE_ACIK_OLUSTURMA:
        return

    if kullanici is None:
        _reddet(status.HTTP_401_UNAUTHORIZED, "Bu işlem için giriş yapmanız gerekiyor")

    yonetici = kullanici.role == "admin"

    # 3) Oturum açmış kullanıcının kendi kaydını oluşturabildiği yerler
    if metot in OLUSTURMA_METOTLARI and tablo in OTURUMLA_OLUSTURMA:
        return

    # 4) Okumalar: oturum yeterli (müşteri paneli kendi kayıtlarını çekiyor)
    if metot in OKUMA_METOTLARI:
        return

    # 5) Geri kalan her yazma işlemi yönetici yetkisi istiyor
    if not yonetici:
        _reddet(status.HTTP_403_FORBIDDEN, "Bu işlem için yönetici yetkisi gerekiyor")
