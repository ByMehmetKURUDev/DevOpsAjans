"""Arka uç testlerinin ortak altyapısı.

* Her test oturumu kendi geçici SQLite dosyasını kullanıyor; gerçek bir
  veritabanına asla bağlanılmıyor (DATABASE_URL burada zorla yazılıyor).
* Uygulama `httpx.AsyncClient(transport=ASGITransport(app))` ile çağrılıyor.
  ASGITransport lifespan'ı çalıştırmıyor: tablolar burada
  `initialize_database()` ile kuruluyor, mock veri / fiyat seed'i / yönetici
  kullanıcı yüklemesi hiç çalışmıyor.
* Jetonlar uygulamanın kendi `create_access_token`'ıyla, test ortamı
  değişkenindeki gizli anahtarla üretiliyor; `entity_guard._istekteki_kullanici`
  ve `dependencies/auth.get_current_user` bunları gerçek jeton gibi çözüyor.
* Bildirim kanalları (e-posta/SMS/WhatsApp) ve PageSpeed anahtarı ortamdan
  siliniyor: testler dışarıya e-posta atmasın, ağa çıkmasın.

Asenkron testler anyio eklentisiyle koşuyor (pytest-asyncio gerekmiyor);
`async def test_*` fonksiyonları otomatik işaretleniyor.
"""

import inspect
import os
import shutil
import tempfile

# Uygulama modülleri import edilmeden ÖNCE: `core.config.settings` ortamı
# ilk erişimde okuyup önbelleğe alıyor.
_GECICI_KLASOR = tempfile.mkdtemp(prefix="mk-test-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_GECICI_KLASOR}/test.db"
os.environ["JWT_SECRET_KEY"] = "test-ortami-gizli-anahtari-yalniz-testte"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_EXPIRE_MINUTES"] = "60"
os.environ["SITE_PUBLIC_URL"] = "https://mehmetkuru.dev"
for _ad in (
    "RESEND_API_KEY",
    "SMTP_HOST",
    "SMS_PROVIDER",
    "WHATSAPP_TOKEN",
    "PAGESPEED_API_KEY",
    "NOTIFY_ADMIN_EMAIL",
    # Faz 3B: Google bağlantısı — testler kendi değerlerini koyuyor ("kurulmadı" varsayılan).
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "BAGLANTI_SIFRE_ANAHTARI",
):
    os.environ.pop(_ad, None)
os.environ["NOTIFY_ADMIN_EMAIL"] = "yonetici@test.dev"

import httpx  # noqa: E402
import pytest  # noqa: E402


def pytest_collection_modifyitems(config, items):
    """`async def` testleri anyio ile koşsun (elle işaret gerekmesin)."""
    for oge in items:
        fonk = getattr(oge, "function", None)
        if fonk is not None and inspect.iscoroutinefunction(fonk):
            oge.add_marker(pytest.mark.anyio)


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_GECICI_KLASOR, ignore_errors=True)


@pytest.fixture(scope="session")
def anyio_backend():
    # Oturum boyunca tek olay döngüsü: veritabanı motoru bir döngüye bağlı.
    return "asyncio"


@pytest.fixture(scope="session")
async def uygulama(anyio_backend):
    from main import app
    from services.database import close_database, initialize_database

    await initialize_database()
    yield app
    await close_database()


@pytest.fixture
async def istemci(uygulama):
    tasiyici = httpx.ASGITransport(app=uygulama)
    async with httpx.AsyncClient(transport=tasiyici, base_url="http://test") as c:
        yield c


@pytest.fixture
async def db_oturumu(uygulama):
    """Doğrudan veritabanına bakmak/yazmak için oturum."""
    from core.database import db_manager

    async with db_manager.async_session_maker() as oturum:
        yield oturum


def jeton_uret(eposta: str, rol: str = "user", kimlik: str | None = None) -> str:
    from core.auth import create_access_token

    return create_access_token(
        {"sub": kimlik or f"kimlik-{eposta}", "email": eposta, "name": eposta.split("@")[0], "role": rol}
    )


@pytest.fixture
def yonetici_basligi():
    return {"Authorization": f"Bearer {jeton_uret('yonetici@test.dev', 'admin')}"}


@pytest.fixture
def musteri_basligi():
    """Fabrika: `musteri_basligi("a@b.com")` → o müşterinin başlığı."""

    def _uret(eposta: str = "musteri@test.dev"):
        return {"Authorization": f"Bearer {jeton_uret(eposta)}"}

    return _uret


@pytest.fixture(autouse=True)
def _dis_ag_kapali(monkeypatch):
    """Testlerde dış ağ yok (Faz 2H): PageSpeed ve DNS varsayılan olarak "ağ yok".

    Zamanlı uç (`/zamanli/calistir`) bütün görevleri — SEO taraması dahil —
    çalıştırıyor; önceki testlerin açtığı sitelere gerçek PageSpeed/DNS isteği
    gitmesin. Ağı sahteleyen test dosyaları (site analizi, site bakımı, SEO
    izleme) kendi sahtelerini bunun ÜSTÜNE koyuyor; o testlerde onlar geçerli.
    """
    import socket

    from services import site_analizi as motor

    async def _pagespeed_yok(url, strateji):
        raise httpx.ConnectError("test ortamında dış ağ yok")

    async def _dns_yok(host, port):
        raise socket.gaierror("test ortamında dış ağ yok")

    monkeypatch.setattr(motor, "_pagespeed_cagir", _pagespeed_yok)
    monkeypatch.setattr(motor, "_dns_cozumle", _dns_yok)

    # Faz 3U: yapay zekâ sağlayıcısına giden TEK yer; ortamda APP_AI_* tanımlı
    # olsa bile testler gerçek modele gitmesin. Sahte yanıt isteyen testler
    # kendi sahtelerini bunun üstüne koyuyor.
    from services import yapay_zeka

    async def _ai_yok(mesajlar, model, max_tokens, temperature):
        raise yapay_zeka.YapayZekaHatasi("ai_kapali", 503)

    monkeypatch.setattr(yapay_zeka, "_saglayici_cagir", _ai_yok)

    # Faz 3B: Google'a giden TEK ağ çağrısı. Sahte Google isteyen testler
    # (test_baglantilar.py) kendi sahtesini bunun üstüne koyuyor.
    from services import baglantilar

    async def _google_yok(*a, **k):
        raise httpx.ConnectError("test ortamında dış ağ yok")

    monkeypatch.setattr(baglantilar, "_ag_istegi", _google_yok)
    baglantilar.bellegi_temizle()
