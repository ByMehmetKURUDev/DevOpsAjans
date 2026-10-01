"""Faz 3B — Google bağlantısı (Analytics 4 + Search Console + YouTube): OAuth, jeton, kaynaklar.

Akış
----
1. Yönetici "Google ile bağlan" → `baslat()` tek kullanımlık `state` (10 dk,
   veritabanında SHA-256 özeti) + PKCE doğrulayıcısı (Fernet ile şifreli)
   üretir ve Google onay adresini döndürür (`access_type=offline`,
   `prompt=consent`, `include_granted_scopes=true`, `code_challenge` S256).
2. Google kullanıcıyı `…/api/v1/baglantilar/google/geri-donus?code&state`
   adresine yönlendirir (girişsiz istek). `geri_donus()` state'i KOŞULLU
   UPDATE ile tüketir (ikinci kullanım / süresi dolmuş → reddedilir), kodu
   doğrulayıcıyla değiştirir, yenileme jetonunu ŞİFRELİ yazar. Ham Google
   hata metni hiçbir yere taşınmaz: yönlendirmede kısa kod (`sonuc=`).
3. Erişim jetonu saklanmaz; ihtiyaçta yenileme jetonuyla alınır ve ~1 saat
   bellekte tutulur. Google `invalid_grant` derse bağlantı
   `yeniden_baglan` durumuna geçer ve yöneticiye BİR KEZ bildirim gider.

Ağ
--
Google'a giden TEK yer `google_istek` → `_ag_istegi`. Testlerde conftest
`_ag_istegi`'ni "ağ yok" ile değiştiriyor; testler kendi sahte Google'ını
koyuyor. `ENVIRONMENT=test` iken (ve yalnız o zaman; Render'da asla —
`sahte_google_acik_mi`) sabit sahte yanıtlar dönülür: tarayıcı uçtan uca
testi Google'a gitmeden bağlan → seç → eşitle akışını yürütebilsin
(2H'deki sahte PageSpeed, 3U'daki sahte yapay zekâ düzeni).

Ortam değişkenleri: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
`BAGLANTI_SIFRE_ANAHTARI` (Fernet; `scripts/baglanti_anahtari_uret.py`).
Biri yoksa özellik "kurulmadı": uçlar 503 `kurulmadi`, panel eksik
değişkenlerin ADINI gösterir (değerini asla).
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

import httpx
from models.baglantilar import Baglanti, BaglantiDurumu
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

GOOGLE = "google"
AJANS = "__ajans__"
#: Panelde "yakında" gösterilen sağlayıcılar (henüz ucu yok).
YAKINDA = ("google_business", "meta")

ORTAM_DEGISKENLERI = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "BAGLANTI_SIFRE_ANAHTARI")

YETKI_ADRESI = "https://accounts.google.com/o/oauth2/v2/auth"
JETON_ADRESI = "https://oauth2.googleapis.com/token"
IPTAL_ADRESI = "https://oauth2.googleapis.com/revoke"
GERI_DONUS_YOLU = "/api/v1/baglantilar/google/geri-donus"
YONETICI_SEKMESI = "/admin?sekme=baglantilar"

KAPSAM_GA = "https://www.googleapis.com/auth/analytics.readonly"
KAPSAM_SC = "https://www.googleapis.com/auth/webmasters.readonly"
KAPSAM_YT = "https://www.googleapis.com/auth/youtube.readonly"
KAPSAM_YTA = "https://www.googleapis.com/auth/yt-analytics.readonly"
KAPSAMLAR = ("openid", "email", KAPSAM_GA, KAPSAM_SC, KAPSAM_YT, KAPSAM_YTA)
#: Kaynak → gereken kapsamlar.
KAYNAK_KAPSAMLARI = {"ga4": (KAPSAM_GA,), "sc": (KAPSAM_SC,), "yt": (KAPSAM_YT, KAPSAM_YTA)}

GA_ADMIN = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"
GA_DATA = "https://analyticsdata.googleapis.com/v1beta"
SC_TABAN = "https://www.googleapis.com/webmasters/v3"
YT_KANALLAR = "https://www.googleapis.com/youtube/v3/channels"
YT_RAPOR = "https://youtubeanalytics.googleapis.com/v2/reports"

DURUM_SURESI = timedelta(minutes=10)
#: Kullanılmış/süresi dolmuş state satırları bu kadar sonra siliniyor.
DURUM_SAKLAMA = timedelta(days=1)
ISTEK_ZAMAN_ASIMI = 10.0
#: Elle eşitleme en çok bu aralıkla.
ELLE_ARALIK = timedelta(minutes=10)

SECIM_DESENLERI = {
    "ga4_mulk": re.compile(r"^properties/\d{1,20}$"),
    "sc_site": re.compile(r"^(sc-domain:[A-Za-z0-9.-]{1,253}|https?://[^\s]{1,280})$"),
    "yt_kanal": re.compile(r"^UC[A-Za-z0-9_-]{10,40}$"),
}

#: Geri dönüşte yönetici paneline taşınan kısa sonuç kodları.
SONUC_KODLARI = (
    "baglandi", "reddedildi", "durum_gecersiz", "kurulmadi", "kod_hatasi",
    "yenileme_yok", "google_hatasi",
)


class BaglantiHatasi(Exception):
    """Uca çevrilecek hata: `kod` ön yüzde yedi dilde metne çevriliyor."""

    def __init__(self, kod: str, durum: int = 400, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.durum = durum
        self.ek = ek


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def _ortam(ad: str) -> str:
    return (os.environ.get(ad) or "").strip()


def sahip_anahtari(hesap_email: Optional[str]) -> str:
    return (hesap_email or "").strip().lower() or AJANS


# ---------------------------------------------------------------------------
# Kurulum (ortam değişkenleri) ve şifreleme
# ---------------------------------------------------------------------------
def _fernet_dene(anahtar: str):
    from cryptography.fernet import Fernet

    try:
        return Fernet(anahtar.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError):
        return None


def kurulum_durumu() -> Dict[str, Any]:
    """{"kurulu", "eksik": [ad…], "gecersiz": [ad…]} — değer ASLA dönmez."""
    eksik = [ad for ad in ORTAM_DEGISKENLERI if not _ortam(ad)]
    gecersiz: List[str] = []
    anahtar = _ortam("BAGLANTI_SIFRE_ANAHTARI")
    if anahtar and _fernet_dene(anahtar) is None:
        gecersiz.append("BAGLANTI_SIFRE_ANAHTARI")
    return {"kurulu": not eksik and not gecersiz, "eksik": eksik, "gecersiz": gecersiz}


def kurulum_iste() -> None:
    if not kurulum_durumu()["kurulu"]:
        raise BaglantiHatasi("kurulmadi", 503)


def _fernet():
    f = _fernet_dene(_ortam("BAGLANTI_SIFRE_ANAHTARI"))
    if f is None:
        raise BaglantiHatasi("kurulmadi", 503)
    return f


def sifrele(metin: str) -> str:
    return _fernet().encrypt(metin.encode("utf-8")).decode("ascii")


def coz(sifreli: Optional[str]) -> str:
    from cryptography.fernet import InvalidToken

    if not sifreli:
        raise BaglantiHatasi("sifre_cozulemedi", 409)
    try:
        return _fernet().decrypt(sifreli.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        # Anahtar değiştiyse eski jeton okunamaz: yeniden bağlanmak gerekir.
        raise BaglantiHatasi("sifre_cozulemedi", 409)


def site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


def yonlendirme_adresi() -> str:
    return site_adresi() + GERI_DONUS_YOLU


def panel_adresi(sonuc: str) -> str:
    kod = sonuc if sonuc in SONUC_KODLARI else "google_hatasi"
    return f"{site_adresi()}{YONETICI_SEKMESI}&sonuc={kod}"


def _b64url(veri: bytes) -> str:
    return base64.urlsafe_b64encode(veri).rstrip(b"=").decode("ascii")


def pkce_meydan_okumasi(dogrulayici: str) -> str:
    return _b64url(hashlib.sha256(dogrulayici.encode("ascii")).digest())


def _ozet(deger: str) -> str:
    return hashlib.sha256(deger.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Sahte Google (yalnız ENVIRONMENT=test)
# ---------------------------------------------------------------------------
def sahte_google_acik_mi() -> bool:
    """Sabit sahte Google yanıtları YALNIZ `ENVIRONMENT=test` iken.

    Üretimde ASLA: `uretim_mi()` evet diyorsa (Render'ın `RENDER` değişkeni
    var ya da ENVIRONMENT tanımsız/dev-test-yerel dışı) kapalı. "dev" ya da
    "yerel" de açmıyor. Bu davranış testle bağlı (`test_baglantilar.py`).
    """
    from services.site_analizi import uretim_mi

    if uretim_mi():
        return False
    return _ortam("ENVIRONMENT").lower() == "test"


SAHTE_EPOSTA = "ajans@ornek-google.test"
SAHTE_KANAL = "UCsahteKanal0123456789ab"


def _sahte_id_jetonu(eposta: str) -> str:
    baslik = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    yuk = _b64url(json.dumps({"email": eposta, "email_verified": True, "iss": "https://accounts.google.com"}).encode())
    return f"{baslik}.{yuk}.sahte"


def _gunler(bas: str, bit: str) -> List[str]:
    try:
        b = datetime.strptime(bas, "%Y-%m-%d").date()
        s = datetime.strptime(bit, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return []
    sonuc = []
    while b <= s and len(sonuc) < 400:
        sonuc.append(b.isoformat())
        b += timedelta(days=1)
    return sonuc


def _sahte_yanit(yontem: str, url: str, form: Optional[Dict[str, Any]], json_govde: Optional[Dict[str, Any]],
                 parametreler: Optional[Dict[str, Any]]) -> "GoogleYaniti":
    form = form or {}
    json_govde = json_govde or {}
    parametreler = parametreler or {}
    if url == JETON_ADRESI:
        if form.get("grant_type") == "authorization_code":
            if not form.get("code_verifier"):
                return GoogleYaniti(400, {"error": "invalid_grant"})
            return GoogleYaniti(200, {
                "access_token": "sahte-erisim-" + secrets.token_hex(4),
                "expires_in": 3599,
                "refresh_token": "sahte-yenileme-" + secrets.token_hex(8),
                "scope": " ".join([KAPSAM_GA, KAPSAM_SC, KAPSAM_YT, KAPSAM_YTA, "openid",
                                   "https://www.googleapis.com/auth/userinfo.email"]),
                "token_type": "Bearer",
                "id_token": _sahte_id_jetonu(SAHTE_EPOSTA),
            })
        return GoogleYaniti(200, {"access_token": "sahte-erisim-" + secrets.token_hex(4), "expires_in": 3599,
                                  "token_type": "Bearer"})
    if url == IPTAL_ADRESI:
        return GoogleYaniti(200, {})
    if url.startswith(GA_ADMIN):
        return GoogleYaniti(200, {"accountSummaries": [{
            "name": "accountSummaries/1001", "account": "accounts/1001", "displayName": "Test Ajans",
            "propertySummaries": [
                {"property": "properties/111111111", "displayName": "mehmetkuru.dev (test)",
                 "propertyType": "PROPERTY_TYPE_ORDINARY", "parent": "accounts/1001"},
                {"property": "properties/222222222", "displayName": "Yan proje (test)",
                 "propertyType": "PROPERTY_TYPE_ORDINARY", "parent": "accounts/1001"},
            ],
        }]})
    if url.startswith(GA_DATA) and url.endswith(":runReport"):
        basliklar = [m.get("name") for m in json_govde.get("metrics", [])]
        degerler = {
            "simdi": {"sessions": "1234", "totalUsers": "987", "activeUsers": "950", "screenPageViews": "3456",
                      "bounceRate": "0.4125", "userEngagementDuration": "79800"},
            "onceki": {"sessions": "1000", "totalUsers": "900", "activeUsers": "880", "screenPageViews": "3000",
                       "bounceRate": "0.45", "userEngagementDuration": "66000"},
        }
        satirlar = [
            {"dimensionValues": [{"value": ad}], "metricValues": [{"value": degerler[ad].get(b, "0")} for b in basliklar]}
            for ad in ("simdi", "onceki")
        ]
        return GoogleYaniti(200, {"dimensionHeaders": [{"name": "dateRange"}],
                                  "metricHeaders": [{"name": b, "type": "TYPE_INTEGER"} for b in basliklar],
                                  "rows": satirlar, "rowCount": 2})
    if url == SC_TABAN + "/sites":
        return GoogleYaniti(200, {"siteEntry": [
            {"siteUrl": "sc-domain:mehmetkuru.dev", "permissionLevel": "siteOwner"},
            {"siteUrl": "https://ornek.test/", "permissionLevel": "siteFullUser"},
        ]})
    if url.startswith(SC_TABAN + "/sites/") and url.endswith("/searchAnalytics/query"):
        boyutlar = json_govde.get("dimensions") or []
        if boyutlar == ["date"]:
            gunler = _gunler(json_govde.get("startDate"), json_govde.get("endDate"))
            yarisi = len(gunler) // 2
            satirlar = []
            for i, g in enumerate(gunler):
                yeni = i >= yarisi
                satirlar.append({"keys": [g], "clicks": 30 if yeni else 25, "impressions": 1000 if yeni else 900,
                                 "ctr": 0.03, "position": 11.5 if yeni else 13.0})
            return GoogleYaniti(200, {"rows": satirlar, "responseAggregationType": "byProperty"})
        if boyutlar in (["query"], ["page"]):
            sinir = int(json_govde.get("rowLimit") or 10)
            satirlar = []
            for i in range(min(sinir, 10)):
                anahtar = f"test sorgusu {i + 1}" if boyutlar == ["query"] else f"https://mehmetkuru.dev/test-sayfa-{i + 1}"
                satirlar.append({"keys": [anahtar], "clicks": 100 - i * 7, "impressions": 2000 - i * 90,
                                 "ctr": round((100 - i * 7) / (2000 - i * 90), 4), "position": 3.2 + i})
            return GoogleYaniti(200, {"rows": satirlar})
        return GoogleYaniti(200, {"rows": []})
    if url == YT_KANALLAR:
        return GoogleYaniti(200, {"items": [{
            "id": SAHTE_KANAL, "snippet": {"title": "Test Kanal"},
            "statistics": {"subscriberCount": "1520", "viewCount": "98000", "videoCount": "42"},
        }]})
    if url == YT_RAPOR:
        gunler = _gunler(parametreler.get("startDate"), parametreler.get("endDate"))
        yarisi = len(gunler) // 2
        satirlar = [[g, 120 if i >= yarisi else 100, 300 if i >= yarisi else 250, 3 if i >= yarisi else 2, 1]
                    for i, g in enumerate(gunler)]
        return GoogleYaniti(200, {
            "kind": "youtubeAnalytics#resultTable",
            "columnHeaders": [{"name": "day"}, {"name": "views"}, {"name": "estimatedMinutesWatched"},
                              {"name": "subscribersGained"}, {"name": "subscribersLost"}],
            "rows": satirlar,
        })
    return GoogleYaniti(404, {"error": {"code": 404, "message": "sahte: bilinmeyen adres"}})


# ---------------------------------------------------------------------------
# Ağ katmanı
# ---------------------------------------------------------------------------
@dataclass
class GoogleYaniti:
    durum: int
    govde: Any


async def _ag_istegi(
    yontem: str,
    url: str,
    *,
    form: Optional[Dict[str, Any]] = None,
    json_govde: Optional[Dict[str, Any]] = None,
    parametreler: Optional[Dict[str, Any]] = None,
    jeton: Optional[str] = None,
) -> GoogleYaniti:
    """Google'a giden TEK ağ çağrısı (testlerde sahteleniyor)."""
    basliklar = {"Accept": "application/json"}
    if jeton:
        basliklar["Authorization"] = f"Bearer {jeton}"
    async with httpx.AsyncClient(timeout=ISTEK_ZAMAN_ASIMI, follow_redirects=False) as istemci:
        yanit = await istemci.request(yontem, url, data=form, json=json_govde, params=parametreler, headers=basliklar)
    try:
        govde = yanit.json()
    except ValueError:
        govde = None
    return GoogleYaniti(yanit.status_code, govde)


async def google_istek(
    yontem: str,
    url: str,
    *,
    form: Optional[Dict[str, Any]] = None,
    json_govde: Optional[Dict[str, Any]] = None,
    parametreler: Optional[Dict[str, Any]] = None,
    jeton: Optional[str] = None,
) -> GoogleYaniti:
    """Sahte açıksa sahte yanıt; değilse ağ. Ağ hataları kısa koda çevrilir."""
    if sahte_google_acik_mi():
        return _sahte_yanit(yontem, url, form, json_govde, parametreler)
    try:
        return await _ag_istegi(yontem, url, form=form, json_govde=json_govde, parametreler=parametreler, jeton=jeton)
    except httpx.TimeoutException:
        raise BaglantiHatasi("zaman_asimi", 504)
    except httpx.HTTPError:
        raise BaglantiHatasi("ag_hatasi", 502)


def hata_kodu(yanit: GoogleYaniti) -> str:
    """Google hata yanıtı → kısa kod (ham mesaj saklanmaz/gösterilmez)."""
    d = yanit.durum
    try:
        metin = json.dumps(yanit.govde) if yanit.govde is not None else ""
    except (TypeError, ValueError):
        metin = ""
    if d == 401:
        return "yetki_yok"
    if d == 403:
        if "SERVICE_DISABLED" in metin or "accessNotConfigured" in metin or "has not been used" in metin:
            return "api_kapali"
        if "SCOPE_INSUFFICIENT" in metin or "insufficientPermissions" in metin or "insufficient authentication scopes" in metin.lower():
            return "kapsam_yok"
        return "erisim_yok"
    if d == 404:
        return "bulunamadi"
    if d == 429:
        return "kota"
    if d == 400:
        return "gecersiz_istek"
    return "google_hatasi"


async def _api(yontem: str, url: str, jeton: str, **kw: Any) -> Any:
    yanit = await google_istek(yontem, url, jeton=jeton, **kw)
    if yanit.durum != 200:
        raise BaglantiHatasi(hata_kodu(yanit), 502)
    return yanit.govde if isinstance(yanit.govde, dict) else {}


# ---------------------------------------------------------------------------
# Bağlantı satırı
# ---------------------------------------------------------------------------
async def baglanti_getir(db: AsyncSession, hesap_email: Optional[str] = None, saglayici: str = GOOGLE) -> Optional[Baglanti]:
    sonuc = await db.execute(
        select(Baglanti).where(Baglanti.saglayici == saglayici, Baglanti.sahip_anahtari == sahip_anahtari(hesap_email))
    )
    return sonuc.scalar_one_or_none()


def secimleri_oku(b: Optional[Baglanti]) -> Dict[str, Optional[str]]:
    try:
        ham = json.loads(b.secimler) if b is not None and b.secimler else {}
    except ValueError:
        ham = {}
    return {k: (ham.get(k) or None) for k in SECIM_DESENLERI}


def hatalari_oku(b: Optional[Baglanti]) -> Dict[str, str]:
    try:
        ham = json.loads(b.son_hata) if b is not None and b.son_hata else {}
    except ValueError:
        ham = {"genel": "google_hatasi"}
    return {str(k): str(v) for k, v in ham.items()} if isinstance(ham, dict) else {}


def kapsam_listesi(b: Optional[Baglanti]) -> List[str]:
    return [k for k in (b.kapsamlar or "").split() if k] if b is not None else []


def kapsam_var(b: Baglanti, kaynak: str) -> bool:
    """Kullanıcı onay ekranında bazı izinleri kaldırmış olabilir (ayrıntılı onay)."""
    verilen = set(kapsam_listesi(b))
    if not verilen:
        return True  # bilinmiyor: Google'a sorulsun, hata dönerse kodu yazılır
    return all(k in verilen for k in KAYNAK_KAPSAMLARI[kaynak])


# ---------------------------------------------------------------------------
# Erişim jetonu (bellek önbelleği)
# ---------------------------------------------------------------------------
#: baglanti_id → (erişim jetonu, geçerlilik sonu — time.monotonic())
_BELLEK: Dict[int, Tuple[str, float]] = {}


def bellegi_temizle(baglanti_id: Optional[int] = None) -> None:
    if baglanti_id is None:
        _BELLEK.clear()
    else:
        _BELLEK.pop(baglanti_id, None)


def _bellege_yaz(baglanti_id: int, jeton: str, sure: Any) -> None:
    try:
        saniye = max(60, min(int(sure or 3600), 3600))
    except (TypeError, ValueError):
        saniye = 3600
    _BELLEK[baglanti_id] = (jeton, time.monotonic() + saniye - 60)


async def yeniden_baglan_isaretle(db: AsyncSession, b: Baglanti, kod: str = "invalid_grant") -> None:
    """Jeton artık geçersiz: durum `yeniden_baglan`, yöneticiye bir kez bildirim."""
    bellegi_temizle(b.id)
    b.durum = "yeniden_baglan"
    b.son_hata = json.dumps({"genel": kod})
    bildir = b.hata_bildirildi_at is None
    if bildir:
        b.hata_bildirildi_at = simdi()
    await db.commit()
    if not bildir:
        return
    try:
        from services.notify import admin_recipients, dispatch, render

        baslik, govde = await render(
            db,
            "baglanti_koptu",
            "Google bağlantısı yenilenmeli",
            "Google (Analytics, Search Console, YouTube) bağlantısının izni artık geçerli değil; "
            "panodaki veriler güncellenmiyor. Yönetim paneli › Bağlantılar'dan yeniden bağlayın.",
            {"saglayici": "Google", "hesap": b.harici_email or ""},
        )
        await dispatch(
            db,
            event_type="baglanti_koptu",
            title=baslik,
            body=govde,
            recipients=await admin_recipients(db),
            link=YONETICI_SEKMESI,
            ref_type="baglanti",
            ref_id=b.id,
        )
    except Exception:  # noqa: BLE001 - bildirim akışı bozmasın
        logger.exception("Bağlantı kopma bildirimi gönderilemedi")


async def erisim_jetonu(db: AsyncSession, b: Baglanti) -> str:
    """Bellekteki geçerli jeton ya da yenileme jetonuyla yenisi."""
    bellek = _BELLEK.get(b.id)
    if bellek and bellek[1] > time.monotonic():
        return bellek[0]
    kurulum_iste()
    if b.durum != "bagli":
        raise BaglantiHatasi("yeniden_baglan", 409)
    try:
        yenileme = coz(b.sifreli_yenileme_jetonu)
    except BaglantiHatasi:
        await yeniden_baglan_isaretle(db, b, "sifre_cozulemedi")
        raise BaglantiHatasi("yeniden_baglan", 409)
    yanit = await google_istek(
        "POST",
        JETON_ADRESI,
        form={
            "client_id": _ortam("GOOGLE_OAUTH_CLIENT_ID"),
            "client_secret": _ortam("GOOGLE_OAUTH_CLIENT_SECRET"),
            "refresh_token": yenileme,
            "grant_type": "refresh_token",
        },
    )
    govde = yanit.govde if isinstance(yanit.govde, dict) else {}
    if yanit.durum != 200 or not govde.get("access_token"):
        if govde.get("error") == "invalid_grant":
            await yeniden_baglan_isaretle(db, b, "invalid_grant")
            raise BaglantiHatasi("yeniden_baglan", 409)
        raise BaglantiHatasi("jeton_alinamadi", 502)
    _bellege_yaz(b.id, govde["access_token"], govde.get("expires_in"))
    return govde["access_token"]


# ---------------------------------------------------------------------------
# OAuth akışı
# ---------------------------------------------------------------------------
async def baslat(db: AsyncSession, baslatan_email: Optional[str], hesap_email: Optional[str] = None) -> str:
    """Google onay adresini üretir; state + PKCE veritabanında (özet / şifreli)."""
    kurulum_iste()
    an = simdi()
    # Eski state satırları: bir gün sonra kalıcı olarak sil (ucuz; her başlatmada).
    await db.execute(delete(BaglantiDurumu).where(BaglantiDurumu.son_kullanma < an - DURUM_SAKLAMA))
    durum = secrets.token_urlsafe(32)
    dogrulayici = secrets.token_urlsafe(64)  # 86 karakter, [A-Za-z0-9_-] (RFC 7636: 43–128)
    db.add(
        BaglantiDurumu(
            durum_ozeti=_ozet(durum),
            saglayici=GOOGLE,
            hesap_email=(hesap_email or None),
            baslatan_email=(baslatan_email or "").strip().lower() or None,
            sifreli_dogrulayici=sifrele(dogrulayici),
            son_kullanma=an + DURUM_SURESI,
        )
    )
    await db.commit()
    if sahte_google_acik_mi():
        # Test ortamı: Google'a gitmeden doğrudan geri dönüş adresine.
        return f"{yonlendirme_adresi()}?{urlencode({'code': 'sahte-kod-' + secrets.token_hex(4), 'state': durum})}"
    parametreler = {
        "client_id": _ortam("GOOGLE_OAUTH_CLIENT_ID"),
        "redirect_uri": yonlendirme_adresi(),
        "response_type": "code",
        "scope": " ".join(KAPSAMLAR),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": durum,
        "code_challenge": pkce_meydan_okumasi(dogrulayici),
        "code_challenge_method": "S256",
    }
    return f"{YETKI_ADRESI}?{urlencode(parametreler, quote_via=quote)}"


def _id_jetonundan_eposta(id_jetonu: Any) -> Optional[str]:
    """id_token doğrudan Google'ın jeton ucundan (TLS) geldi; imzayı ayrıca doğrulamıyoruz,
    yalnız görüntülemek için e-postayı okuyoruz (OpenID Connect Core §3.1.3.7)."""
    if not isinstance(id_jetonu, str) or id_jetonu.count(".") < 2:
        return None
    try:
        yuk = id_jetonu.split(".")[1]
        yuk += "=" * (-len(yuk) % 4)
        veri = json.loads(base64.urlsafe_b64decode(yuk.encode("ascii")))
    except (ValueError, UnicodeError):
        return None
    eposta = veri.get("email") if isinstance(veri, dict) else None
    return str(eposta).strip().lower()[:254] if eposta else None


async def _durumu_tuket(db: AsyncSession, durum: str) -> Optional[BaglantiDurumu]:
    """State'i TEK KEZ kullanır: koşullu UPDATE; ikinci çağrı / süresi dolmuş → None."""
    if not durum or len(durum) > 200:
        return None
    ozet = _ozet(durum)
    an = simdi()
    sonuc = await db.execute(
        update(BaglantiDurumu)
        .where(
            BaglantiDurumu.durum_ozeti == ozet,
            BaglantiDurumu.kullanildi_at.is_(None),
            BaglantiDurumu.son_kullanma > an,
        )
        .values(kullanildi_at=an)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if int(sonuc.rowcount or 0) != 1:
        return None
    return (await db.execute(select(BaglantiDurumu).where(BaglantiDurumu.durum_ozeti == ozet))).scalar_one_or_none()


async def geri_donus(db: AsyncSession, code: Optional[str], durum: Optional[str], hata: Optional[str]) -> str:
    """Google yönlendirmesi. Dönen değer kısa sonuç kodu (`SONUC_KODLARI`)."""
    kayit = await _durumu_tuket(db, durum or "")
    if kayit is None:
        return "durum_gecersiz"
    if hata:
        return "reddedildi" if hata == "access_denied" else "google_hatasi"
    if not code or len(code) > 2048:
        return "durum_gecersiz"
    if not kurulum_durumu()["kurulu"]:
        return "kurulmadi"
    try:
        dogrulayici = coz(kayit.sifreli_dogrulayici)
        yanit = await google_istek(
            "POST",
            JETON_ADRESI,
            form={
                "code": code,
                "client_id": _ortam("GOOGLE_OAUTH_CLIENT_ID"),
                "client_secret": _ortam("GOOGLE_OAUTH_CLIENT_SECRET"),
                "redirect_uri": yonlendirme_adresi(),
                "grant_type": "authorization_code",
                "code_verifier": dogrulayici,
            },
        )
    except BaglantiHatasi as h:
        logger.warning("Google kod değişimi başarısız: %s", h.kod)
        return "kod_hatasi"
    govde = yanit.govde if isinstance(yanit.govde, dict) else {}
    if yanit.durum != 200 or not govde.get("access_token"):
        logger.warning("Google kod değişimi reddedildi: %s %s", yanit.durum, govde.get("error"))
        return "kod_hatasi"
    yenileme = govde.get("refresh_token")
    if not yenileme:
        return "yenileme_yok"

    # Geri dönüş girişsiz: denetim kaydında akışı başlatan yönetici görünsün.
    try:
        from services import denetim

        denetim.aktor_ata(kayit.baslatan_email, "admin")
    except Exception:  # noqa: BLE001
        pass

    harici = _id_jetonundan_eposta(govde.get("id_token"))
    kapsamlar = " ".join(sorted(set(str(govde.get("scope") or "").split())))
    b = await baglanti_getir(db, kayit.hesap_email)
    if b is None:
        b = Baglanti(
            saglayici=GOOGLE,
            hesap_email=kayit.hesap_email,
            sahip_anahtari=sahip_anahtari(kayit.hesap_email),
        )
        db.add(b)
    elif harici and b.harici_email and harici != b.harici_email:
        # Başka bir Google hesabı: eski seçimler o hesaba aitti.
        b.secimler = None
    b.harici_email = harici
    b.sifreli_yenileme_jetonu = sifrele(yenileme)
    b.kapsamlar = kapsamlar or None
    b.durum = "bagli"
    b.son_hata = None
    b.hata_bildirildi_at = None
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return "google_hatasi"
    await db.refresh(b)
    _bellege_yaz(b.id, govde["access_token"], govde.get("expires_in"))
    return "baglandi"


async def baglantiyi_kaldir(db: AsyncSession, hesap_email: Optional[str] = None) -> Dict[str, Any]:
    """Google'da jetonu iptal eder (en iyi çaba) ve kaydı siler."""
    b = await baglanti_getir(db, hesap_email)
    if b is None:
        raise BaglantiHatasi("bagli_degil", 404)
    iptal = False
    try:
        yenileme = coz(b.sifreli_yenileme_jetonu)
        yanit = await google_istek("POST", IPTAL_ADRESI, form={"token": yenileme})
        govde = yanit.govde if isinstance(yanit.govde, dict) else {}
        # 400 invalid_token: jeton zaten geçersiz (kullanıcı Google'dan kaldırmış) — iptal sayılır.
        iptal = yanit.durum == 200 or (yanit.durum == 400 and govde.get("error") in ("invalid_token", "invalid_grant"))
    except BaglantiHatasi as h:
        logger.warning("Google jeton iptali yapılamadı: %s", h.kod)
    bellegi_temizle(b.id)
    await db.delete(b)
    await db.commit()
    return {"silindi": True, "iptal_edildi": iptal}


# ---------------------------------------------------------------------------
# Seçilebilir kaynaklar (GA4 mülkleri, Search Console siteleri, YouTube kanalları)
# ---------------------------------------------------------------------------
async def _ga4_mulkleri(jeton: str) -> List[Dict[str, str]]:
    mulkler: List[Dict[str, str]] = []
    sayfa: Optional[str] = None
    for _ in range(5):
        parametreler: Dict[str, Any] = {"pageSize": 200}
        if sayfa:
            parametreler["pageToken"] = sayfa
        govde = await _api("GET", GA_ADMIN, jeton, parametreler=parametreler)
        for hesap in govde.get("accountSummaries") or []:
            hesap_adi = str(hesap.get("displayName") or "")
            for m in hesap.get("propertySummaries") or []:
                kimlik = str(m.get("property") or "")
                if SECIM_DESENLERI["ga4_mulk"].match(kimlik):
                    ad = str(m.get("displayName") or kimlik)
                    mulkler.append({"kimlik": kimlik, "ad": f"{ad} — {hesap_adi}" if hesap_adi else ad})
        sayfa = govde.get("nextPageToken") or None
        if not sayfa:
            break
    return mulkler


async def _sc_siteleri(jeton: str) -> List[Dict[str, str]]:
    govde = await _api("GET", SC_TABAN + "/sites", jeton)
    siteler = []
    for s in govde.get("siteEntry") or []:
        adres = str(s.get("siteUrl") or "")
        if SECIM_DESENLERI["sc_site"].match(adres) and s.get("permissionLevel") != "siteUnverifiedUser":
            siteler.append({"kimlik": adres, "ad": adres, "yetki": str(s.get("permissionLevel") or "")})
    return siteler


async def _yt_kanallari(jeton: str) -> List[Dict[str, str]]:
    govde = await _api("GET", YT_KANALLAR, jeton, parametreler={"part": "snippet", "mine": "true", "maxResults": 50})
    kanallar = []
    for k in govde.get("items") or []:
        kimlik = str(k.get("id") or "")
        if SECIM_DESENLERI["yt_kanal"].match(kimlik):
            kanallar.append({"kimlik": kimlik, "ad": str((k.get("snippet") or {}).get("title") or kimlik)})
    return kanallar


async def kaynaklari_getir(db: AsyncSession, hesap_email: Optional[str] = None) -> Dict[str, Any]:
    kurulum_iste()
    b = await baglanti_getir(db, hesap_email)
    if b is None:
        raise BaglantiHatasi("bagli_degil", 404)
    jeton = await erisim_jetonu(db, b)
    islevler = {"ga4": _ga4_mulkleri, "sc": _sc_siteleri, "yt": _yt_kanallari}
    sonuc: Dict[str, Any] = {"ga4": [], "sc": [], "yt": [], "hatalar": {}}
    sirali = [k for k in islevler if kapsam_var(b, k)]
    for k in islevler:
        if k not in sirali:
            sonuc["hatalar"][k] = "kapsam_yok"
    yanitlar = await asyncio.gather(
        *(asyncio.wait_for(islevler[k](jeton), ISTEK_ZAMAN_ASIMI * 2) for k in sirali), return_exceptions=True
    )
    for k, y in zip(sirali, yanitlar):
        if isinstance(y, BaglantiHatasi):
            sonuc["hatalar"][k] = y.kod
        elif isinstance(y, asyncio.TimeoutError):
            sonuc["hatalar"][k] = "zaman_asimi"
        elif isinstance(y, BaseException):
            logger.warning("Google kaynak listesi alınamadı (%s): %s", k, type(y).__name__)
            sonuc["hatalar"][k] = "google_hatasi"
        else:
            sonuc[k] = y
    return sonuc


async def secimi_kaydet(db: AsyncSession, girdi: Dict[str, Any], hesap_email: Optional[str] = None) -> Dict[str, Optional[str]]:
    b = await baglanti_getir(db, hesap_email)
    if b is None:
        raise BaglantiHatasi("bagli_degil", 404)
    secimler = secimleri_oku(b)
    for alan, desen in SECIM_DESENLERI.items():
        if alan not in girdi:
            continue
        deger = girdi.get(alan)
        deger = str(deger).strip() if deger is not None else ""
        if not deger:
            secimler[alan] = None
            continue
        if not desen.match(deger):
            raise BaglantiHatasi("secim_gecersiz", 422, alan=alan)
        secimler[alan] = deger
    b.secimler = json.dumps(secimler, ensure_ascii=False)
    await db.commit()
    return secimler


# ---------------------------------------------------------------------------
# Durum listesi (panel kartı)
# ---------------------------------------------------------------------------
def _iso(an: Optional[datetime]) -> Optional[str]:
    an = _utc(an)
    return an.isoformat() if an else None


def elle_bekleme_sn(b: Optional[Baglanti]) -> int:
    son = _utc(b.son_deneme) if b is not None else None
    if son is None:
        return 0
    kalan = (son + ELLE_ARALIK) - simdi()
    return max(0, int(kalan.total_seconds()))


async def durum_listesi(db: AsyncSession, hesap_email: Optional[str] = None) -> Dict[str, Any]:
    kurulum = kurulum_durumu()
    b = await baglanti_getir(db, hesap_email)
    if b is None:
        durum = "bagli_degil" if kurulum["kurulu"] else "kurulmadi"
    else:
        durum = b.durum if kurulum["kurulu"] else "kurulmadi"
    kapsamlar = {k: (b is not None and kapsam_var(b, k)) for k in KAYNAK_KAPSAMLARI}
    google = {
        "saglayici": GOOGLE,
        "durum": durum,
        "kurulum": kurulum,
        "harici_email": b.harici_email if b is not None else None,
        "kapsamlar": kapsamlar,
        "secimler": secimleri_oku(b),
        "son_esitleme": _iso(b.son_esitleme) if b is not None else None,
        "son_deneme": _iso(b.son_deneme) if b is not None else None,
        "son_hata": hatalari_oku(b),
        "elle_bekleme_sn": elle_bekleme_sn(b),
        "baglanti_tarihi": _iso(b.created_at) if b is not None else None,
    }
    return {
        "saglayicilar": [google] + [{"saglayici": s, "durum": "yakinda"} for s in YAKINDA],
        "yonlendirme_adresi": yonlendirme_adresi(),
        "test_modu": sahte_google_acik_mi(),
    }

