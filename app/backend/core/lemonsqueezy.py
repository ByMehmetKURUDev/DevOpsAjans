"""Lemon Squeezy tahsilatı: ödeme sayfası açar, bildirimi doğrular.

Shopier'den farkı
-----------------
Shopier'in API'sinde ödeme ucu YOK; her fatura için gizli bir ürün açıp
müşteriyi o ürünün sayfasına göndermek zorundayız. Bu yüzden sepet adımı
çıkıyor, müşteri siteye dönmüyor ve dükkanda fatura başına ölü bir ürün
birikiyor.

Lemon Squeezy'de gerçek bir ödeme (checkout) ucu var: tek bir "Hizmet
bedeli" ürünü bir kez açılıyor, her faturada tutar `custom_price` ile
eziliyor. Sepet yok, dönüş adresi var, ürün birikmiyor.

Kartın para birimi
------------------
Dokümanları açıkça söylüyor: mağaza hangi para biriminde gösterirse
göstersin, kart SONUÇTA USD çekiliyor. Yani Türk müşteri kartında dolar
işlemi görür, bankası yurt dışı komisyonu ekler ve taksit yapamaz.
Bu dosya o kararı vermiyor; TL müşteriyi Shopier'de tutup dövizi buraya
yönlendirmek panelin işi.

Eşleştirme
----------
Ödeme bağlantısını açarken kendi `jeton`umuzu `checkout_data.custom`
içine koyuyoruz; bildirim geldiğinde `meta.custom_data.jeton` olarak geri
geliyor. Tutar ya da e-posta ile eşleştirmiyoruz: aynı tutarda iki fatura
olabilir, müşteri başka adresle ödeyebilir.
"""

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

API_TABANI = "https://api.lemonsqueezy.com/v1"
ZAMAN_ASIMI = 20.0

#: Lemon Squeezy JSON:API kullanıyor; bu başlıklar zorunlu.
BASLIKLAR = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json",
}

#: Tek seferlik satışta gelen olay. Abonelikte `subscription_created` ile
#: birlikte bu da geliyor, o yüzden tek olayı dinlemek yetiyor.
ODEME_OLAYI = "order_created"

PARA_BIRIMLERI = {"TRY", "USD", "EUR", "GBP"}


class LemonHatasi(Exception):
    """Lemon Squeezy çağrısı başarısız oldu."""


def anahtar() -> str:
    return (os.getenv("LEMON_API_KEY") or "").strip()


def magaza_id() -> str:
    return (os.getenv("LEMON_STORE_ID") or "").strip()


def varyant_id() -> str:
    """Tek seferlik "Hizmet bedeli" ürününün varyant kimliği.

    Bir kez panelden açılıyor; her faturada tutarı `custom_price` eziyor.
    """
    return (os.getenv("LEMON_VARIANT_ID") or "").strip()


def webhook_sirri() -> str:
    return (os.getenv("LEMON_WEBHOOK_SECRET") or "").strip()


def hazir_mi() -> bool:
    """Üçü birden tanımlı değilse tahsilat açılamaz.

    Anahtar varken mağaza ya da varyant eksikse çağrı 404 dönerdi ve
    müşteri boş bir sayfaya giderdi; hazır saymıyoruz.
    """
    return bool(anahtar() and magaza_id() and varyant_id())


async def _cagir(
    yontem: str, yol: str, *, govde: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Tek çağrı noktası: başlıklar, zaman aşımı ve hata mesajı burada.

    Hatalı yanıtın gövdesi loglanıyor. Shopier tarafında "media[0].type is
    required" hatasını ancak gövdeyi logladığımız için bulabilmiştik;
    aynı dersi burada baştan uyguluyoruz.
    """
    if not anahtar():
        raise LemonHatasi("Lemon Squeezy erişim anahtarı tanımlı değil")

    basliklar = dict(BASLIKLAR)
    basliklar["Authorization"] = f"Bearer {anahtar()}"

    async with httpx.AsyncClient(timeout=ZAMAN_ASIMI) as istemci:
        yanit = await istemci.request(
            yontem, f"{API_TABANI}{yol}", headers=basliklar, json=govde
        )

    if yanit.status_code in (401, 403):
        logger.error("Lemon Squeezy anahtari reddedildi (%s)", yanit.status_code)
        raise LemonHatasi("Lemon Squeezy erişim anahtarı geçersiz")

    if yanit.status_code >= 400:
        logger.error(
            "Lemon Squeezy hata verdi (%s %s): %s %s",
            yontem,
            yol,
            yanit.status_code,
            yanit.text[:500],
        )
        raise LemonHatasi(f"Lemon Squeezy isteği reddetti ({yanit.status_code})")

    if not yanit.content:
        return {}
    try:
        return yanit.json()
    except ValueError as hata:
        raise LemonHatasi("Lemon Squeezy yanıtı okunamadı") from hata


def _kurus(tutar: float) -> int:
    """Tutarı en küçük birime çeviriyor; Lemon Squeezy tam sayı istiyor.

    `round` şart: 0.1 + 0.2 gibi kayan nokta artıkları yüzünden 1999
    yerine 1998 göndermeyelim.
    """
    return int(round(float(tutar) * 100))


async def odeme_baglantisi_ac(
    *,
    jeton: str,
    baslik: str,
    aciklama: str,
    tutar: float,
    para_birimi: str = "TRY",
    eposta: Optional[str] = None,
    ad: Optional[str] = None,
    donus_adresi: Optional[str] = None,
    son_gecerlilik: Optional[str] = None,
) -> Dict[str, str]:
    """Bir fatura için ödeme sayfası açar, adresini döndürür.

    Ürün AÇMIYOR: panelde bir kez açılmış "Hizmet bedeli" varyantını
    kullanıp tutarı `custom_price` ile eziyor. Shopier'de fatura başına
    ürün açmak zorundaydık ve dükkanda ölü ürün birikiyordu; burada o
    sorun yok.

    `jeton` bizim ödeme kaydımızın jetonu. `checkout_data.custom` içine
    konuyor ve bildirimde `meta.custom_data.jeton` olarak geri geliyor —
    eşleştirmeyi tutar ya da e-posta tahminiyle değil bununla yapıyoruz.
    """
    if not hazir_mi():
        raise LemonHatasi("Lemon Squeezy ayarları eksik (anahtar, mağaza ya da varyant)")

    birim = (para_birimi or "TRY").upper()
    if birim not in PARA_BIRIMLERI:
        birim = "TRY"

    ozellikler: Dict[str, Any] = {
        "custom_price": _kurus(tutar),
        "checkout_data": {
            # Jeton metin olarak gidiyor: JSON'da sayıya dönüşüp başındaki
            # sıfırları kaybetmesin.
            "custom": {"jeton": str(jeton)},
        },
        "product_options": {
            "name": baslik[:255],
            "description": aciklama[:1000],
            # Shopier'de olmayan şey: ödeme bitince müşteri kendi
            # sayfamıza dönüyor.
            "redirect_url": donus_adresi or "",
            "receipt_button_text": "Panele dön",
            "receipt_link_url": donus_adresi or "",
        },
        "checkout_options": {
            "embed": False,
            "media": False,
            "logo": True,
            # Marka yeşili; ödeme sayfası siteyle aynı hissi versin.
            "button_color": "#00DC82",
        },
    }

    # E-posta ve ad ZORUNLU DEĞİL: bağlantı elden ele gidebilir, ödeyen
    # kişi fatura sahibi olmayabilir. Varsa yalnızca ön dolgu olarak
    # gidiyor, kimliği o belirlemiyor.
    if (eposta or "").strip():
        ozellikler["checkout_data"]["email"] = eposta.strip()
    if (ad or "").strip():
        ozellikler["checkout_data"]["name"] = ad.strip()
    if son_gecerlilik:
        ozellikler["expires_at"] = son_gecerlilik

    govde = {
        "data": {
            "type": "checkouts",
            "attributes": ozellikler,
            "relationships": {
                "store": {"data": {"type": "stores", "id": str(magaza_id())}},
                "variant": {"data": {"type": "variants", "id": str(varyant_id())}},
            },
        }
    }

    cevap = await _cagir("POST", "/checkouts", govde=govde)
    veri = cevap.get("data") or {}
    adres = ((veri.get("attributes") or {}).get("url") or "").strip()
    if not adres:
        logger.error("Lemon Squeezy odeme adresi bos dondu: %s", str(cevap)[:400])
        raise LemonHatasi("Lemon Squeezy ödeme adresi üretmedi")

    return {"checkout_id": str(veri.get("id") or ""), "adres": adres, "para_birimi": birim}


async def siparis_getir(siparis_id: str) -> Dict[str, Any]:
    """Siparişi Lemon Squeezy'den kendi anahtarımızla çeker.

    Bildirim gövdesine güvenmiyoruz; bildirim yalnızca tetikleyici, karar
    buradan çekilen kayıttan veriliyor.
    """
    cevap = await _cagir("GET", f"/orders/{siparis_id}")
    return cevap.get("data") or {}


def _ozellik(siparis: Dict[str, Any], alan: str, varsayilan: Any = None) -> Any:
    return (siparis.get("attributes") or {}).get(alan, varsayilan)


def odenmis_mi(siparis: Dict[str, Any]) -> bool:
    """Sipariş gerçekten tahsil edildi mi?

    `paid` dışındaki her durum (pending, failed, refunded) ödenmemiş
    sayılıyor: iade edilmiş bir siparişin faturayı kapatması olmaz.
    """
    return str(_ozellik(siparis, "status", "")).lower() == "paid"


def siparis_tutari(siparis: Dict[str, Any]) -> float:
    """Mağaza para biriminde toplam tutar.

    `total` en küçük birimde tam sayı geliyor. Kartın USD çekildiğini
    unutma: burada dönen sayı mağazanın gösterdiği para birimindedir.
    """
    ham = _ozellik(siparis, "total", 0) or 0
    try:
        return round(int(ham) / 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


def siparis_para_birimi(siparis: Dict[str, Any]) -> str:
    return str(_ozellik(siparis, "currency", "") or "").upper()


def ozel_veri(govde: Dict[str, Any]) -> Dict[str, Any]:
    """Bildirimdeki `meta.custom_data` — ödeme açarken koyduğumuz jeton.

    Sözlük olmayan bir şey gelirse boş dönüyoruz; eşleştirme yapılamaz
    ama istek patlamaz.
    """
    meta = govde.get("meta")
    if not isinstance(meta, dict):
        return {}
    ozel = meta.get("custom_data")
    return ozel if isinstance(ozel, dict) else {}


def govdedeki_jeton(govde: Dict[str, Any]) -> str:
    return str(ozel_veri(govde).get("jeton") or "").strip()


def govdedeki_siparis_id(govde: Dict[str, Any]) -> str:
    veri = govde.get("data")
    if not isinstance(veri, dict):
        return ""
    return str(veri.get("id") or "").strip()


def webhook_imzasi_gecerli_mi(ham_govde: bytes, imza: str, sir: str = "") -> bool:
    """`X-Signature` başlığını doğrular: HMAC-SHA256, onaltılık, ham gövde.

    Sır tanımlı değilse GEÇERSİZ sayıyoruz. Shopier tarafında imza yoksa
    "gövdeye güvenme, siparişi yeniden çek" diyebiliyorduk; burada da uç
    aynı korumayı uyguluyor ama imzayı doğrulanmış saymak yanlış olur.

    Karşılaştırma `compare_digest` ile: uzunluk farkından ya da erken
    çıkıştan sızan zamanlama bilgisi imzayı tahmin ettirmesin.
    """
    gizli = (sir or webhook_sirri()).strip()
    if not gizli or not imza:
        return False
    beklenen = hmac.new(gizli.encode("utf-8"), ham_govde, hashlib.sha256).hexdigest()
    return hmac.compare_digest(beklenen, imza.strip().lower())


def ozet(siparis: Dict[str, Any]) -> Dict[str, Any]:
    """Panelde ve günlükte gösterilecek en az alan."""
    return {
        "id": str(siparis.get("id") or ""),
        "durum": _ozellik(siparis, "status", ""),
        "tutar": siparis_tutari(siparis),
        "para_birimi": siparis_para_birimi(siparis),
        "eposta": _ozellik(siparis, "user_email", ""),
        "siparis_no": _ozellik(siparis, "order_number", ""),
    }
