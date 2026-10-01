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
#: Fiyatlandırma v5 tabloları da buraya eklendi: ziyaretçi giriş yapmadan
#: paket/hizmet/eklenti/AI-PM katalogunu görebilmeli (yazma hâlâ admin'e
#: kapalı — bu sadece okuma kuralı).
HERKESE_ACIK_OKUMA = {
    "projects", "blog_posts", "site_settings",
    "pricing_scales", "pricing_profiles", "pricing_services", "pricing_addons", "ai_pm_tiers",
}

#: Giriş yapmadan kayıt oluşturulabilen tablolar — iletişim formu.
HERKESE_ACIK_OLUSTURMA = {"inquiries"}

#: Oturum açmış herhangi bir kullanıcının kayıt oluşturabildiği tablolar.
OTURUMLA_OLUSTURMA = {"support_tickets"}

#: Faz 2E güvenlik incelemesi: oturum açmış olmak bile okumaya yetmeyen
#: tablolar/yollar. Fiyat teklifleri başka müşterilerin e-postasını ve
#: tutarlarını taşıyor; gönderim günlüğü bütün alıcıları listeliyor; içerik
#: planı, analitik görüntüleri ve pazaryeri taslakları ajansın iç verisi
#: (vitrin `/api/v1/marketplace` ayrı, açık uçtan). Müşteri paneli bunların
#: hiçbirini kullanmıyor (teklif kararı imzalı bağlantıyla veriliyor).
YALNIZ_YONETICI_OKUMA = {"pricing_inquiries", "content_posts", "analytics_snapshots", "marketplace_items"}
YALNIZ_YONETICI_YOLLAR = {"/api/v1/entities/notifications/log"}

OKUMA_METOTLARI = {"GET", "HEAD", "OPTIONS"}
OLUSTURMA_METOTLARI = {"POST"}


def _tablo_adi(path: str) -> str:
    """`/api/v1/entities/invoices/all` -> `invoices`."""
    parcalar = [p for p in path.split("/") if p]
    try:
        return parcalar[parcalar.index("entities") + 1]
    except (ValueError, IndexError):
        return ""


def _koleksiyon_koku_mu(path: str) -> bool:
    """`/api/v1/entities/<tablo>` (sonunda başka parça yok) mu?

    Açık/oturumlu oluşturma izni yalnız tek kayıt içindir: `/batch` ile
    toplu ekleme (ve müşterinin başkası adına talep açması) yöneticiye kalıyor.
    """
    parcalar = [p for p in path.split("/") if p]
    try:
        return len(parcalar) == parcalar.index("entities") + 2
    except ValueError:
        return False


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

    # Faz 2D: oturum iptal edildiyse (ya da kullanıcı her yerden çıkarıldıysa)
    # jeton geçersiz sayılıyor. Karar ara katmanda verildi (bu fonksiyon
    # eşzamanlı; veritabanına gidemez) — bkz. middlewares/oturum_bekcisi.py.
    from services.oturumlar import istek_iptal_mi

    if istek_iptal_mi(request):
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

    # 2) İletişim formu: ziyaretçi mesaj bırakabilmeli (tek kayıt)
    if metot in OLUSTURMA_METOTLARI and tablo in HERKESE_ACIK_OLUSTURMA and _koleksiyon_koku_mu(request.url.path):
        return

    if kullanici is None:
        from services.oturumlar import IPTAL_SEBEBI, istek_iptal_mi

        _reddet(
            status.HTTP_401_UNAUTHORIZED,
            IPTAL_SEBEBI if istek_iptal_mi(request) else "Bu işlem için giriş yapmanız gerekiyor",
        )

    yonetici = kullanici.role == "admin"

    # 3) Oturum açmış kullanıcının kendi kaydını oluşturabildiği yerler (tek kayıt;
    #    sahiplik alanını uç kendisi etkin hesaptan yazıyor)
    if metot in OLUSTURMA_METOTLARI and tablo in OTURUMLA_OLUSTURMA and _koleksiyon_koku_mu(request.url.path):
        return

    # 4) Okumalar: oturum yeterli (müşteri paneli kendi kayıtlarını çekiyor;
    #    sahiplik süzgeci uçta — bkz. kayit_sahipligi.py). İstisnalar yönetici.
    if metot in OKUMA_METOTLARI:
        if not yonetici and (tablo in YALNIZ_YONETICI_OKUMA or request.url.path.rstrip("/") in YALNIZ_YONETICI_YOLLAR):
            _reddet(status.HTTP_403_FORBIDDEN, "Bu işlem için yönetici yetkisi gerekiyor")
        return

    # 5) Geri kalan her yazma işlemi yönetici yetkisi istiyor
    if not yonetici:
        _reddet(status.HTTP_403_FORBIDDEN, "Bu işlem için yönetici yetkisi gerekiyor")
