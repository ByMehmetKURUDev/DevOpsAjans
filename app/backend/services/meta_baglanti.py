"""Parti 13 — Meta bağlantısı: Facebook sayfası + Instagram profesyonel hesabı (ajansın kendisi).

Akış
----
1. Yönetici "Meta ile bağlan" → `baslat()` tek kullanımlık `state` (10 dk,
   veritabanında SHA-256 özeti; Google ile aynı `baglanti_durumlari` tablosu,
   `saglayici="meta"`) üretir ve Facebook onay adresini döndürür.
   `META_CONFIG_ID` tanımlıysa "Facebook Login for Business" yapılandırması
   (`config_id`), değilse `scope` ile izin listesi gönderilir.
2. Facebook `…/api/v1/baglantilar/meta/geri-donus?code&state` adresine döner
   (girişsiz). State KOŞULLU UPDATE ile tüketilir ve sağlayıcısı `meta`
   olmalı (Google'ın state'i burada geçmez, tersi de). Kod kısa ömürlü
   jetona, o da uzun ömürlü (~60 gün) kullanıcı jetonuna çevrilir.
3. Sayfa seçilince o sayfanın jetonu alınır: uzun ömürlü kullanıcı jetonundan
   türeyen SAYFA jetonunun süresi dolmaz; eşitleme yalnız sayfa jetonuyla
   yürür. Instagram hesabı da bağlı olduğu sayfanın jetonuyla okunur.
   Bütün jetonlar TEK bir Fernet şifreli JSON'da (`sifreli_yenileme_jetonu`);
   düz metin hiçbir yerde yok. Graph isteklerinde jeton adreste değil
   `Authorization` başlığında; `appsecret_proof` da gönderiliyor.

Neden uygulama incelemesi (App Review) gerekmiyor: ajans yalnız KENDİ
sayfasını bağlıyor; uygulamada rolü (yönetici/geliştirici) olan kişiler
geliştirme modunda bütün izinleri verebiliyor. Müşteri hesapları bağlanacağı
gün inceleme gerekecek (o zaman `hesap_email` dolu satırlar).

Eşitleme (`channel=social`, `kaynak=meta`, son 28 gün / önceki 28 gün):
takipçi (Facebook + Instagram), görüntülenme (`page_media_view` + IG
`views`), etkileşim (`page_post_engagements` + IG `total_interactions`),
yeni takipçi (`page_daily_follows_unique` + IG `follows_and_unfollows`).
Meta 2025'te `page_impressions*`/`page_fans*` ölçümlerini kaldırdı; bu yüzden
yalnız yerine konanlar kullanılıyor. Bir ölçüm hata verirse (yeni hesapta
Instagram 100 takipçinin altında bazı ölçümleri vermiyor) o ölçüm atlanır,
diğerleri yazılır.

Ortam değişkenleri: `META_APP_ID`, `META_APP_SECRET`, `BAGLANTI_SIFRE_ANAHTARI`
(+ isteğe bağlı `META_CONFIG_ID`, `META_GRAPH_SURUMU`).
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

import httpx
from models.baglantilar import Baglanti, BaglantiDurumu
from services import baglantilar as bg
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

META = "meta"
ORTAM_DEGISKENLERI = ("META_APP_ID", "META_APP_SECRET", "BAGLANTI_SIFRE_ANAHTARI")
VARSAYILAN_SURUM = "v25.0"
GRAPH = "https://graph.facebook.com"
GERI_DONUS_YOLU = "/api/v1/baglantilar/meta/geri-donus"
ISTEK_ZAMAN_ASIMI = 10.0
KAYNAK_ZAMAN_ASIMI = 25.0

#: Okuma izinleri. `ads_read` şimdiden isteniyor: reklam raporu geldiğinde yeniden bağlanmak gerekmesin.
KAPSAMLAR = (
    "pages_show_list",
    "pages_read_engagement",
    "read_insights",
    "instagram_basic",
    "instagram_manage_insights",
    "business_management",
    "ads_read",
)
KAYNAK_KAPSAMLARI = {
    "fb": ("pages_show_list", "pages_read_engagement", "read_insights"),
    "ig": ("instagram_basic", "instagram_manage_insights"),
}
SECIM_DESENLERI = {
    "fb_sayfa": re.compile(r"^\d{5,25}$"),
    "ig_hesap": re.compile(r"^\d{5,25}$"),
}
SONUC_KODLARI = (
    "meta_baglandi", "meta_reddedildi", "meta_durum_gecersiz", "meta_kurulmadi", "meta_kod_hatasi", "meta_hatasi",
)
KAYNAK = "meta"
KANAL = "social"


def _ortam(ad: str) -> str:
    return (os.environ.get(ad) or "").strip()


def graph_surumu() -> str:
    surum = _ortam("META_GRAPH_SURUMU")
    return surum if re.fullmatch(r"v\d{2}\.\d", surum) else VARSAYILAN_SURUM


def kurulum_durumu() -> Dict[str, Any]:
    """{"kurulu", "eksik", "gecersiz"} — değer ASLA dönmez."""
    eksik = [ad for ad in ORTAM_DEGISKENLERI if not _ortam(ad)]
    gecersiz: List[str] = []
    anahtar = _ortam("BAGLANTI_SIFRE_ANAHTARI")
    if anahtar and bg._fernet_dene(anahtar) is None:
        gecersiz.append("BAGLANTI_SIFRE_ANAHTARI")
    if _ortam("META_APP_ID") and not re.fullmatch(r"\d{5,25}", _ortam("META_APP_ID")):
        gecersiz.append("META_APP_ID")
    return {"kurulu": not eksik and not gecersiz, "eksik": eksik, "gecersiz": gecersiz}


def kurulum_iste() -> None:
    if not kurulum_durumu()["kurulu"]:
        raise bg.BaglantiHatasi("kurulmadi", 503)


def yonlendirme_adresi() -> str:
    return bg.site_adresi() + GERI_DONUS_YOLU


def panel_adresi(sonuc: str) -> str:
    kod = sonuc if sonuc in SONUC_KODLARI else "meta_hatasi"
    return f"{bg.site_adresi()}{bg.YONETICI_SEKMESI}&sonuc={kod}"


# ---------------------------------------------------------------------------
# Şifreli jeton kasası
# ---------------------------------------------------------------------------
def kasa_oku(b: Baglanti) -> Dict[str, Any]:
    """{"kullanici": str, "bitis": iso|None, "sayfalar": {sayfa_id: jeton}}"""
    try:
        veri = json.loads(bg.coz(b.sifreli_yenileme_jetonu))
    except ValueError:
        raise bg.BaglantiHatasi("sifre_cozulemedi", 409)
    if not isinstance(veri, dict):
        raise bg.BaglantiHatasi("sifre_cozulemedi", 409)
    veri.setdefault("sayfalar", {})
    return veri


def kasa_yaz(b: Baglanti, veri: Dict[str, Any]) -> None:
    b.sifreli_yenileme_jetonu = bg.sifrele(json.dumps(veri, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Ağ
# ---------------------------------------------------------------------------
@dataclass
class MetaYaniti:
    durum: int
    govde: Any


async def _ag_istegi(yontem: str, url: str, *, parametreler: Optional[Dict[str, Any]] = None,
                     jeton: Optional[str] = None) -> MetaYaniti:
    """Meta'ya giden TEK ağ çağrısı (testlerde sahteleniyor)."""
    basliklar = {"Accept": "application/json"}
    if jeton:
        basliklar["Authorization"] = f"Bearer {jeton}"
    async with httpx.AsyncClient(timeout=ISTEK_ZAMAN_ASIMI, follow_redirects=False) as istemci:
        yanit = await istemci.request(yontem, url, params=parametreler, headers=basliklar)
    try:
        govde = yanit.json()
    except ValueError:
        govde = None
    return MetaYaniti(yanit.status_code, govde)


def _kanit(jeton: str) -> str:
    """appsecret_proof: jetonun uygulama sırrıyla HMAC-SHA256'sı (çalınan jeton tek başına işe yaramasın)."""
    return hmac.new(_ortam("META_APP_SECRET").encode(), jeton.encode(), hashlib.sha256).hexdigest()


def adres(yol: str) -> str:
    return f"{GRAPH}/{graph_surumu()}/{yol.lstrip('/')}"


async def meta_istek(yontem: str, yol: str, *, parametreler: Optional[Dict[str, Any]] = None,
                     jeton: Optional[str] = None) -> MetaYaniti:
    parametreler = dict(parametreler or {})
    if jeton:
        parametreler["appsecret_proof"] = _kanit(jeton)
    url = adres(yol)
    if bg.sahte_google_acik_mi():
        return _sahte_yanit(yontem, url, parametreler)
    try:
        return await _ag_istegi(yontem, url, parametreler=parametreler, jeton=jeton)
    except httpx.TimeoutException:
        raise bg.BaglantiHatasi("zaman_asimi", 504)
    except httpx.HTTPError:
        raise bg.BaglantiHatasi("ag_hatasi", 502)


def hata_kodu(yanit: MetaYaniti) -> str:
    """Graph hata yanıtı → kısa kod (ham Meta metni saklanmaz/gösterilmez)."""
    hata = (yanit.govde or {}).get("error") if isinstance(yanit.govde, dict) else None
    kod = (hata or {}).get("code") if isinstance(hata, dict) else None
    try:
        kod = int(kod) if kod is not None else None
    except (TypeError, ValueError):
        kod = None
    if kod in (190, 102, 2500) or yanit.durum == 401:
        return "yetki_yok"
    if kod in (4, 17, 32, 613, 80001, 80002, 80005) or yanit.durum == 429:
        return "kota"
    if kod == 10 or (kod is not None and 200 <= kod <= 299) or yanit.durum == 403:
        return "kapsam_yok"
    if kod == 100:
        return "gecersiz_istek"
    if yanit.durum == 404:
        return "bulunamadi"
    return "meta_hatasi"


async def _api(yol: str, jeton: str, parametreler: Optional[Dict[str, Any]] = None, yontem: str = "GET") -> Dict[str, Any]:
    yanit = await meta_istek(yontem, yol, parametreler=parametreler, jeton=jeton)
    if yanit.durum != 200:
        raise bg.BaglantiHatasi(hata_kodu(yanit), 502)
    return yanit.govde if isinstance(yanit.govde, dict) else {}


# ---------------------------------------------------------------------------
# Sahte Meta (yalnız ENVIRONMENT=test — tarayıcı e2e testi Meta'ya gitmesin)
# ---------------------------------------------------------------------------
SAHTE_SAYFA = "100000000000001"
SAHTE_IG = "17841400000000001"


def _sahte_yanit(yontem: str, url: str, parametreler: Dict[str, Any]) -> MetaYaniti:
    yol = url.split(f"/{graph_surumu()}/", 1)[-1]
    if yol == "oauth/access_token":
        return MetaYaniti(200, {"access_token": "sahte-meta-" + secrets.token_hex(6), "token_type": "bearer",
                                "expires_in": 5183944})
    if yol == "me":
        return MetaYaniti(200, {"id": "10200000000000001", "name": "Test Ajans"})
    if yol == "me/permissions":
        if yontem == "DELETE":
            return MetaYaniti(200, {"success": True})
        return MetaYaniti(200, {"data": [{"permission": k, "status": "granted"} for k in KAPSAMLAR]})
    if yol == "me/accounts":
        return MetaYaniti(200, {"data": [{
            "id": SAHTE_SAYFA, "name": "Test Sayfa", "access_token": "sahte-sayfa-jetonu",
            "instagram_business_account": {"id": SAHTE_IG, "username": "test.ajans"},
        }]})
    if yol == SAHTE_SAYFA:
        return MetaYaniti(200, {"id": SAHTE_SAYFA, "name": "Test Sayfa", "followers_count": 1200, "fan_count": 1150,
                                "access_token": "sahte-sayfa-jetonu"})
    if yol == f"{SAHTE_SAYFA}/insights":
        metrik = str(parametreler.get("metric") or "")
        try:
            bas = datetime.fromtimestamp(int(parametreler.get("since")), tz=timezone.utc).date()
            bit = datetime.fromtimestamp(int(parametreler.get("until")), tz=timezone.utc).date()
        except (TypeError, ValueError):
            return MetaYaniti(400, {"error": {"code": 100, "message": "sahte: tarih"}})
        degerler = []
        gun = bas
        gunluk = {"page_media_view": 400, "page_post_engagements": 30, "page_daily_follows_unique": 2}.get(metrik, 1)
        while gun < bit:
            degerler.append({"value": gunluk, "end_time": f"{(gun + timedelta(days=1)).isoformat()}T07:00:00+0000"})
            gun += timedelta(days=1)
        return MetaYaniti(200, {"data": [{"name": metrik, "period": "day", "values": degerler}]})
    if yol == SAHTE_IG:
        return MetaYaniti(200, {"id": SAHTE_IG, "username": "test.ajans", "followers_count": 830})
    if yol == f"{SAHTE_IG}/insights":
        metrik = str(parametreler.get("metric") or "")
        sabit = {"views": 9000, "total_interactions": 640, "follows_and_unfollows": 25}
        veri = []
        for m in metrik.split(","):
            if m == "follows_and_unfollows":
                veri.append({"name": m, "total_value": {"value": 31, "breakdowns": [{"dimension_keys": ["follow_type"], "results": [
                    {"dimension_values": ["FOLLOWER"], "value": sabit[m]}, {"dimension_values": ["NON_FOLLOWER"], "value": 6}]}]}})
            elif m in sabit:
                veri.append({"name": m, "total_value": {"value": sabit[m]}})
        return MetaYaniti(200, {"data": veri})
    return MetaYaniti(404, {"error": {"code": 803, "message": "sahte: bilinmeyen yol"}})


# ---------------------------------------------------------------------------
# Bağlantı satırı ve yardımcılar
# ---------------------------------------------------------------------------
async def baglanti_getir(db: AsyncSession, hesap_email: Optional[str] = None) -> Optional[Baglanti]:
    return await bg.baglanti_getir(db, hesap_email, saglayici=META)


def secimleri_oku(b: Optional[Baglanti]) -> Dict[str, Optional[str]]:
    try:
        ham = json.loads(b.secimler) if b is not None and b.secimler else {}
    except ValueError:
        ham = {}
    return {k: (ham.get(k) or None) for k in SECIM_DESENLERI}


def _ic_secimler(b: Baglanti) -> Dict[str, Any]:
    try:
        ham = json.loads(b.secimler) if b.secimler else {}
    except ValueError:
        ham = {}
    return ham if isinstance(ham, dict) else {}


def kapsam_var(b: Baglanti, kaynak: str) -> bool:
    verilen = set(bg.kapsam_listesi(b))
    if not verilen:
        return True
    return all(k in verilen for k in KAYNAK_KAPSAMLARI[kaynak])


async def _yeniden_baglan(db: AsyncSession, b: Baglanti, kod: str = "yetki_yok") -> None:
    await bg.yeniden_baglan_isaretle(db, b, kod)


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------
async def baslat(db: AsyncSession, baslatan_email: Optional[str], hesap_email: Optional[str] = None) -> str:
    kurulum_iste()
    an = bg.simdi()
    await db.execute(delete(BaglantiDurumu).where(BaglantiDurumu.son_kullanma < an - bg.DURUM_SAKLAMA))
    durum = secrets.token_urlsafe(32)
    db.add(
        BaglantiDurumu(
            durum_ozeti=bg._ozet(durum),
            saglayici=META,
            hesap_email=(hesap_email or None),
            baslatan_email=(baslatan_email or "").strip().lower() or None,
            # Meta sunucu akışında PKCE yok; sütun zorunlu: rastgele değer (kullanılmıyor).
            sifreli_dogrulayici=bg.sifrele(secrets.token_urlsafe(16)),
            son_kullanma=an + bg.DURUM_SURESI,
        )
    )
    await db.commit()
    if bg.sahte_google_acik_mi():
        return f"{yonlendirme_adresi()}?{urlencode({'code': 'sahte-meta-kod-' + secrets.token_hex(4), 'state': durum})}"
    parametreler = {
        "client_id": _ortam("META_APP_ID"),
        "redirect_uri": yonlendirme_adresi(),
        "state": durum,
        "response_type": "code",
    }
    yapilandirma = _ortam("META_CONFIG_ID")
    if yapilandirma:
        parametreler["config_id"] = yapilandirma
    else:
        parametreler["scope"] = ",".join(KAPSAMLAR)
        # Daha önce reddedilen izinler yeniden sorulsun.
        parametreler["auth_type"] = "rerequest"
    return f"https://www.facebook.com/{graph_surumu()}/dialog/oauth?{urlencode(parametreler, quote_via=quote)}"


async def geri_donus(db: AsyncSession, code: Optional[str], durum: Optional[str], hata: Optional[str]) -> str:
    kayit = await bg._durumu_tuket(db, durum or "")
    if kayit is None or kayit.saglayici != META:
        return "meta_durum_gecersiz"
    if hata:
        return "meta_reddedildi" if hata in ("access_denied", "user_denied") else "meta_hatasi"
    if not code or len(code) > 4096:
        return "meta_durum_gecersiz"
    if not kurulum_durumu()["kurulu"]:
        return "meta_kurulmadi"
    istemci = {"client_id": _ortam("META_APP_ID"), "client_secret": _ortam("META_APP_SECRET")}
    try:
        kisa = await meta_istek("GET", "oauth/access_token", parametreler={
            **istemci, "redirect_uri": yonlendirme_adresi(), "code": code,
        })
        kisa_govde = kisa.govde if isinstance(kisa.govde, dict) else {}
        if kisa.durum != 200 or not kisa_govde.get("access_token"):
            logger.warning("Meta kod değişimi reddedildi: %s", kisa.durum)
            return "meta_kod_hatasi"
        uzun = await meta_istek("GET", "oauth/access_token", parametreler={
            **istemci, "grant_type": "fb_exchange_token", "fb_exchange_token": kisa_govde["access_token"],
        })
        uzun_govde = uzun.govde if isinstance(uzun.govde, dict) else {}
        jeton = uzun_govde.get("access_token") if uzun.durum == 200 else None
        jeton = jeton or kisa_govde["access_token"]
        sure = uzun_govde.get("expires_in") if uzun.durum == 200 else kisa_govde.get("expires_in")
        ben = await _api("me", jeton, {"fields": "id,name"})
        izinler = await _api("me/permissions", jeton)
    except bg.BaglantiHatasi as h:
        logger.warning("Meta bağlantısı tamamlanamadı: %s", h.kod)
        return "meta_kod_hatasi"

    try:
        from services import denetim

        denetim.aktor_ata(kayit.baslatan_email, "admin")
    except Exception:  # noqa: BLE001
        pass

    verilen = sorted({
        str(i.get("permission")) for i in (izinler.get("data") or [])
        if isinstance(i, dict) and i.get("status") == "granted" and i.get("permission")
    })
    try:
        bitis = (bg.simdi() + timedelta(seconds=int(sure))).isoformat() if sure else None
    except (TypeError, ValueError):
        bitis = None
    ad = str(ben.get("name") or "").strip()[:200] or None
    b = await baglanti_getir(db, kayit.hesap_email)
    eski_kasa: Dict[str, Any] = {}
    if b is None:
        b = Baglanti(saglayici=META, hesap_email=kayit.hesap_email, sahip_anahtari=bg.sahip_anahtari(kayit.hesap_email))
        db.add(b)
    else:
        ic = _ic_secimler(b)
        if ben.get("id") and ic.get("kullanici_id") and str(ben.get("id")) != str(ic.get("kullanici_id")):
            b.secimler = None  # Başka bir Facebook kullanıcısı: eski seçimler ona ait değil.
        else:
            try:
                eski_kasa = kasa_oku(b)
            except bg.BaglantiHatasi:
                eski_kasa = {}
    ic = _ic_secimler(b) if b.secimler else {}
    ic["kullanici_id"] = str(ben.get("id") or "") or None
    b.secimler = json.dumps(ic, ensure_ascii=False)
    b.harici_email = ad
    kasa_yaz(b, {"kullanici": jeton, "bitis": bitis, "sayfalar": eski_kasa.get("sayfalar") or {}})
    b.kapsamlar = " ".join(verilen) or None
    b.durum = "bagli"
    b.son_hata = None
    b.hata_bildirildi_at = None
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return "meta_hatasi"
    return "meta_baglandi"


async def baglantiyi_kaldir(db: AsyncSession, hesap_email: Optional[str] = None) -> Dict[str, Any]:
    """Facebook'ta uygulama iznini geri alır (en iyi çaba) ve kaydı siler."""
    b = await baglanti_getir(db, hesap_email)
    if b is None:
        raise bg.BaglantiHatasi("bagli_degil", 404)
    iptal = False
    try:
        kasa = kasa_oku(b)
        yanit = await meta_istek("DELETE", "me/permissions", jeton=kasa.get("kullanici"))
        iptal = yanit.durum == 200 or hata_kodu(yanit) == "yetki_yok"
    except bg.BaglantiHatasi as h:
        logger.warning("Meta izni geri alınamadı: %s", h.kod)
    await db.delete(b)
    await db.commit()
    return {"silindi": True, "iptal_edildi": iptal}


# ---------------------------------------------------------------------------
# Kaynaklar ve seçim
# ---------------------------------------------------------------------------
async def _sayfalar(db: AsyncSession, b: Baglanti) -> List[Dict[str, Any]]:
    """Kullanıcının yönettiği sayfalar (+ bağlı Instagram hesabı) — sayfa jetonlarıyla."""
    kasa = kasa_oku(b)
    try:
        govde = await _api("me/accounts", kasa.get("kullanici") or "", {
            "fields": "id,name,access_token,instagram_business_account{id,username}", "limit": 100,
        })
    except bg.BaglantiHatasi as h:
        if h.kod == "yetki_yok":
            await _yeniden_baglan(db, b, "yetki_yok")
            raise bg.BaglantiHatasi("yeniden_baglan", 409)
        raise
    sayfalar = []
    for s in govde.get("data") or []:
        if not isinstance(s, dict) or not SECIM_DESENLERI["fb_sayfa"].match(str(s.get("id") or "")):
            continue
        ig = s.get("instagram_business_account") if isinstance(s.get("instagram_business_account"), dict) else None
        sayfalar.append({
            "id": str(s["id"]),
            "ad": str(s.get("name") or s["id"])[:200],
            "jeton": str(s.get("access_token") or ""),
            "ig_id": str(ig.get("id")) if ig and SECIM_DESENLERI["ig_hesap"].match(str(ig.get("id") or "")) else None,
            "ig_ad": str(ig.get("username") or "")[:100] if ig else None,
        })
    return sayfalar


async def kaynaklari_getir(db: AsyncSession, hesap_email: Optional[str] = None) -> Dict[str, Any]:
    kurulum_iste()
    b = await baglanti_getir(db, hesap_email)
    if b is None:
        raise bg.BaglantiHatasi("bagli_degil", 404)
    if b.durum != "bagli":
        raise bg.BaglantiHatasi("yeniden_baglan", 409)
    sonuc: Dict[str, Any] = {"fb": [], "ig": [], "hatalar": {}}
    for k in KAYNAK_KAPSAMLARI:
        if not kapsam_var(b, k):
            sonuc["hatalar"][k] = "kapsam_yok"
    sayfalar = await _sayfalar(db, b)
    sonuc["fb"] = [{"kimlik": s["id"], "ad": s["ad"]} for s in sayfalar]
    sonuc["ig"] = [
        {"kimlik": s["ig_id"], "ad": f"@{s['ig_ad']} — {s['ad']}" if s["ig_ad"] else s["ad"]}
        for s in sayfalar if s["ig_id"]
    ]
    return sonuc


async def secimi_kaydet(db: AsyncSession, girdi: Dict[str, Any], hesap_email: Optional[str] = None) -> Dict[str, Optional[str]]:
    kurulum_iste()
    b = await baglanti_getir(db, hesap_email)
    if b is None:
        raise bg.BaglantiHatasi("bagli_degil", 404)
    ic = _ic_secimler(b)
    for alan, desen in SECIM_DESENLERI.items():
        if alan not in girdi:
            continue
        deger = girdi.get(alan)
        deger = str(deger).strip() if deger is not None else ""
        if deger and not desen.match(deger):
            raise bg.BaglantiHatasi("secim_gecersiz", 422, alan=alan)
        ic[alan] = deger or None

    gerekli = {ic.get("fb_sayfa"), ic.get("ig_hesap")} - {None}
    kasa = kasa_oku(b)
    sayfa_jetonlari: Dict[str, str] = {}
    ic["ig_sayfa"] = None
    if gerekli:
        sayfalar = await _sayfalar(db, b)
        for s in sayfalar:
            if ic.get("fb_sayfa") == s["id"] and s["jeton"]:
                sayfa_jetonlari[s["id"]] = s["jeton"]
            if ic.get("ig_hesap") and ic.get("ig_hesap") == s["ig_id"] and s["jeton"]:
                sayfa_jetonlari[s["id"]] = s["jeton"]
                ic["ig_sayfa"] = s["id"]
        if ic.get("fb_sayfa") and ic["fb_sayfa"] not in sayfa_jetonlari:
            raise bg.BaglantiHatasi("secim_gecersiz", 422, alan="fb_sayfa")
        if ic.get("ig_hesap") and not ic.get("ig_sayfa"):
            raise bg.BaglantiHatasi("secim_gecersiz", 422, alan="ig_hesap")
    # Yalnız seçili sayfaların jetonları kalıyor (gereksiz jeton saklanmıyor).
    kasa["sayfalar"] = sayfa_jetonlari
    kasa_yaz(b, kasa)
    b.secimler = json.dumps(ic, ensure_ascii=False)
    await db.commit()
    return secimleri_oku(b)


# ---------------------------------------------------------------------------
# Eşitleme
# ---------------------------------------------------------------------------
def _gun_damgasi(gun: date) -> int:
    return int(datetime(gun.year, gun.month, gun.day, tzinfo=timezone.utc).timestamp())


def _pencereler() -> Tuple[Tuple[date, date], Tuple[date, date]]:
    from services import google_esitleme as ge

    (bas, bit), (obas, obit) = ge.pencereler(ge.bugun() - timedelta(days=1))
    return (date.fromisoformat(bas), date.fromisoformat(bit)), (date.fromisoformat(obas), date.fromisoformat(obit))


def gunluk_topla(veri: Dict[str, Any], bas: date) -> Tuple[float, float]:
    """Sayfa ölçümünün günlük değerleri → (şimdiki pencere, önceki pencere) toplamı.

    `period=day` değerinde `end_time` günün BİTİŞİ (ertesi gün, Pasifik gece yarısı);
    gün = end_time tarihi − 1.
    """
    simdi = onceki = 0.0
    for kayit in (veri.get("data") or [{}])[0].get("values") or []:
        try:
            gun = date.fromisoformat(str(kayit.get("end_time"))[:10]) - timedelta(days=1)
            deger = float(kayit.get("value") or 0)
        except (TypeError, ValueError):
            continue
        if gun >= bas:
            simdi += deger
        else:
            onceki += deger
    return simdi, onceki


async def _facebook(sayfa: str, jeton: str) -> Dict[str, Any]:
    (bas, bit), (obas, _obit) = _pencereler()
    sonuc: Dict[str, Any] = {"hatalar": []}
    temel = await _api(sayfa, jeton, {"fields": "followers_count,fan_count"})
    takipci = temel.get("followers_count", temel.get("fan_count"))
    sonuc["takipci"] = float(takipci) if isinstance(takipci, (int, float)) else None

    async def olcum(ad: str) -> Optional[Tuple[float, float]]:
        try:
            veri = await _api(f"{sayfa}/insights", jeton, {
                "metric": ad, "period": "day",
                "since": _gun_damgasi(obas), "until": _gun_damgasi(bit + timedelta(days=1)),
            })
        except bg.BaglantiHatasi as h:
            if h.kod == "yetki_yok":
                raise
            sonuc["hatalar"].append(h.kod)
            return None
        return gunluk_topla(veri, bas)

    sonuc["goruntulenme"], sonuc["etkilesim"], sonuc["yeni_takipci"] = await asyncio.gather(
        olcum("page_media_view"), olcum("page_post_engagements"), olcum("page_daily_follows_unique")
    )
    return sonuc


def ig_toplam(veri: Dict[str, Any]) -> Dict[str, float]:
    sonuc: Dict[str, float] = {}
    for m in veri.get("data") or []:
        if not isinstance(m, dict):
            continue
        tv = m.get("total_value") or {}
        if m.get("name") == "follows_and_unfollows":
            for kirilim in tv.get("breakdowns") or []:
                for r in kirilim.get("results") or []:
                    if "FOLLOWER" in (r.get("dimension_values") or []):
                        sonuc["follows"] = float(r.get("value") or 0)
            continue
        try:
            sonuc[str(m.get("name"))] = float(tv.get("value") or 0)
        except (TypeError, ValueError):
            continue
    return sonuc


async def _instagram(hesap: str, jeton: str) -> Dict[str, Any]:
    (bas, bit), (obas, obit) = _pencereler()
    sonuc: Dict[str, Any] = {"hatalar": []}
    temel = await _api(hesap, jeton, {"fields": "followers_count,username"})
    takipci = temel.get("followers_count")
    sonuc["takipci"] = float(takipci) if isinstance(takipci, (int, float)) else None

    async def pencere(b0: date, b1: date) -> Dict[str, float]:
        degerler: Dict[str, float] = {}
        for metrik, ek in (("views", {}), ("total_interactions", {}), ("follows_and_unfollows", {"breakdown": "follow_type"})):
            try:
                veri = await _api(f"{hesap}/insights", jeton, {
                    "metric": metrik, "period": "day", "metric_type": "total_value",
                    "since": _gun_damgasi(b0), "until": _gun_damgasi(b1 + timedelta(days=1)), **ek,
                })
            except bg.BaglantiHatasi as h:
                if h.kod == "yetki_yok":
                    raise
                # 100 takipçinin altındaki hesapta follows_and_unfollows hiç dönmüyor: hata sayılmaz.
                if metrik != "follows_and_unfollows":
                    sonuc["hatalar"].append(h.kod)
                continue
            degerler.update(ig_toplam(veri))
        return degerler

    s, o = await asyncio.gather(pencere(bas, bit), pencere(obas, obit))
    for anahtar, ad in (("goruntulenme", "views"), ("etkilesim", "total_interactions"), ("yeni_takipci", "follows")):
        sonuc[anahtar] = (s[ad], o.get(ad, 0.0)) if ad in s else None
    return sonuc


def metrikleri_birlestir(fb: Optional[Dict[str, Any]], ig: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Facebook + Instagram → pano satırları (ikisinden biri yoksa olanla)."""
    from services import google_esitleme as ge

    kaynaklar = [k for k in (fb, ig) if k]

    def toplam(anahtar: str) -> Optional[Tuple[float, float]]:
        parcalar = [k[anahtar] for k in kaynaklar if k.get(anahtar) is not None]
        if not parcalar:
            return None
        return sum(p[0] for p in parcalar), sum(p[1] for p in parcalar)

    metrikler: List[Dict[str, Any]] = []
    takipciler = [k["takipci"] for k in kaynaklar if k.get("takipci") is not None]
    yeni = toplam("yeni_takipci")
    if takipciler:
        takipci = float(sum(takipciler))
        once = takipci - yeni[0] if yeni else None
        metrikler.append(ge._metrik("followers", takipci, once if once and once > 0 else None))
    for anahtar, metrik in (("goruntulenme", "views"), ("etkilesim", "interactions")):
        t = toplam(anahtar)
        if t is not None:
            metrikler.append(ge._metrik(metrik, t[0], t[1] if t[1] else None))
    if yeni is not None:
        metrikler.append(ge._metrik("new_followers", yeni[0], yeni[1] if yeni[1] else None))
    return metrikler


async def esitle(db: AsyncSession, b: Baglanti) -> Dict[str, Any]:
    from services import google_esitleme as ge

    kurulum_iste()
    ic = _ic_secimler(b)
    b.son_deneme = bg.simdi()
    await db.commit()
    kasa = kasa_oku(b)
    jetonlar = kasa.get("sayfalar") or {}
    hatalar: Dict[str, str] = {}
    gorevler: Dict[str, Any] = {}
    if ic.get("fb_sayfa"):
        if not kapsam_var(b, "fb"):
            hatalar["fb"] = "kapsam_yok"
        elif jetonlar.get(ic["fb_sayfa"]):
            gorevler["fb"] = _facebook(ic["fb_sayfa"], jetonlar[ic["fb_sayfa"]])
        else:
            hatalar["fb"] = "yeniden_baglan"
    if ic.get("ig_hesap"):
        if not kapsam_var(b, "ig"):
            hatalar["ig"] = "kapsam_yok"
        elif ic.get("ig_sayfa") and jetonlar.get(ic["ig_sayfa"]):
            gorevler["ig"] = _instagram(ic["ig_hesap"], jetonlar[ic["ig_sayfa"]])
        else:
            hatalar["ig"] = "yeniden_baglan"
    adlar = list(gorevler)
    yanitlar = await asyncio.gather(
        *(asyncio.wait_for(gorevler[k], KAYNAK_ZAMAN_ASIMI) for k in adlar), return_exceptions=True
    )
    veriler: Dict[str, Optional[Dict[str, Any]]] = {"fb": None, "ig": None}
    jeton_gecersiz = False
    for k, y in zip(adlar, yanitlar):
        if isinstance(y, bg.BaglantiHatasi):
            hatalar[k] = y.kod
            jeton_gecersiz = jeton_gecersiz or y.kod == "yetki_yok"
        elif isinstance(y, asyncio.TimeoutError):
            hatalar[k] = "zaman_asimi"
        elif isinstance(y, BaseException):
            logger.warning("Meta eşitleme hatası (%s): %s", k, type(y).__name__)
            hatalar[k] = "meta_hatasi"
        else:
            veriler[k] = y
            if y.get("hatalar"):
                hatalar[k] = y["hatalar"][0]
    if jeton_gecersiz:
        await _yeniden_baglan(db, b, "yetki_yok")
        raise bg.BaglantiHatasi("yeniden_baglan", 409)
    metrikler = metrikleri_birlestir(veriler["fb"], veriler["ig"])
    yazilan = 0
    if metrikler:
        yazilan = await ge._metrikleri_yaz(db, KAYNAK, KANAL, metrikler, ge.bugun().isoformat())
        b.son_esitleme = bg.simdi()
    from models.analytics_snapshots import Analytics_snapshots

    sinir = (ge.bugun() - timedelta(days=ge.SAKLAMA_GUN)).isoformat()
    await db.execute(delete(Analytics_snapshots).where(Analytics_snapshots.kaynak == KAYNAK,
                                                       Analytics_snapshots.snapshot_date < sinir))
    b.son_hata = json.dumps(hatalar) if hatalar else None
    await db.commit()
    return {"yazilan": yazilan, "kaynaklar": [k for k, v in veriler.items() if v], "hatalar": hatalar}


async def elle_esitle(db: AsyncSession, hesap_email: Optional[str] = None) -> Dict[str, Any]:
    kurulum_iste()
    b = await baglanti_getir(db, hesap_email)
    if b is None:
        raise bg.BaglantiHatasi("bagli_degil", 404)
    if b.durum != "bagli":
        raise bg.BaglantiHatasi("yeniden_baglan", 409)
    if not any(secimleri_oku(b).values()):
        raise bg.BaglantiHatasi("secim_yok", 400)
    kalan = bg.elle_bekleme_sn(b)
    if kalan > 0:
        raise bg.BaglantiHatasi("cok_sik", 429, kalan_sn=kalan)
    return await esitle(db, b)


async def zamanli_esitleme(db: AsyncSession) -> Dict[str, Any]:
    if not kurulum_durumu()["kurulu"]:
        return {"atlandi": "kurulmadi"}
    baglantilar = (
        await db.execute(select(Baglanti).where(Baglanti.saglayici == META, Baglanti.durum == "bagli"))
    ).scalars().all()
    ozet: Dict[str, Any] = {"baglanti": 0, "yazilan": 0, "hata": 0}
    for b in baglantilar:
        if not any(secimleri_oku(b).values()):
            continue
        ozet["baglanti"] += 1
        try:
            sonuc = await esitle(db, b)
            ozet["yazilan"] += sonuc["yazilan"]
            ozet["hata"] += len(sonuc["hatalar"])
        except bg.BaglantiHatasi as h:
            ozet["hata"] += 1
            ozet.setdefault("kodlar", []).append(h.kod)
    return ozet


# ---------------------------------------------------------------------------
# Panel kartı
# ---------------------------------------------------------------------------
async def durum(db: AsyncSession, hesap_email: Optional[str] = None) -> Dict[str, Any]:
    kurulum = kurulum_durumu()
    b = await baglanti_getir(db, hesap_email)
    if b is None:
        d = "bagli_degil" if kurulum["kurulu"] else "kurulmadi"
    else:
        d = b.durum if kurulum["kurulu"] else "kurulmadi"
    bitis = None
    if b is not None and kurulum["kurulu"]:
        try:
            bitis = kasa_oku(b).get("bitis")
        except bg.BaglantiHatasi:
            bitis = None
    return {
        "saglayici": META,
        "durum": d,
        "kurulum": kurulum,
        "harici_ad": b.harici_email if b is not None else None,
        "kapsamlar": {k: (b is not None and kapsam_var(b, k)) for k in KAYNAK_KAPSAMLARI},
        "secimler": secimleri_oku(b),
        "son_esitleme": bg._iso(b.son_esitleme) if b is not None else None,
        "son_hata": bg.hatalari_oku(b),
        "elle_bekleme_sn": bg.elle_bekleme_sn(b),
        "baglanti_tarihi": bg._iso(b.created_at) if b is not None else None,
        "kullanici_jetonu_bitis": bitis,
        "yonlendirme_adresi": yonlendirme_adresi(),
    }
