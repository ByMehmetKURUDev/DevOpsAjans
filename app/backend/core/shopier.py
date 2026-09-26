"""Shopier — yeni REST API (Kişisel Erişim Anahtarı ile).

Neden baştan yazıldı
--------------------
İlk sürüm Shopier'in API V1 ödeme formunu (`api_pay4.php`) kullanıyordu:
API Key + API Secret çifti ve HMAC imzalı bir form POST'u. Shopier V1'i
kaldırdı; yeni açılan hesaplara o çift verilmiyor, panelde yalnızca
Kişisel Erişim Anahtarı (PAT) var. Yani eski yol bu hesapta hiç
çalışmıyor — kod değil, altyapı değişti.

Yeni API'de "şu tutarı tahsil et" diyen bir uç yok. Onun yerine ürün
oluşturulabiliyor ve her ürünün kendi satın alma linki dönüyor. Bir
faturayı tahsil etmek, o fatura için müşteriye özel gizli bir ürün
açıp müşteriyi o linke göndermek demek.

Ürün şöyle açılıyor:
  type=digital          hizmet satıyoruz, kargo yok
  customListing=True    dükkânın vitrininde görünmüyor
  stockQuantity=1       aynı fatura iki kez ödenemiyor

Ödeme doğrulaması
-----------------
Webhook gövdesine GÜVENİLMİYOR. Gelen bildirim yalnızca bir tetikleyici
sayılıyor; sipariş bilgisi API'den kendi anahtarımızla yeniden
çekiliyor. Böylece "ödendi" kararı bize gelen istekten değil,
Shopier'in kendi cevabından çıkıyor — imza sırrı yapılandırılmamış
olsa bile sahte bir bildirim faturayı ödenmiş gösteremiyor.

İmza sırrı varsa ayrıca doğrulanıyor; ikisi birbirinin yedeği.
"""

import base64
import hashlib
import hmac
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

API_TABANI = "https://api.shopier.com/v1"
ZAMAN_ASIMI = 20.0

PARA_BIRIMLERI = {"TRY", "USD", "EUR"}

# Ürün oluştururken en az bir görsel zorunlu. Faturaya özel bir görsel
# üretmenin anlamı yok; ajans logosu yeterli ve her ürün için aynı.
VARSAYILAN_GORSEL = "https://mehmetkuru.dev/logo192.png"


class ShopierHatasi(Exception):
    """Shopier API'sinden dönen hata; çağıran tarafa olduğu gibi taşınıyor."""


def anahtar() -> str:
    return (os.getenv("SHOPIER_PAT") or "").strip()


def webhook_sirri() -> str:
    return (os.getenv("SHOPIER_WEBHOOK_SECRET") or "").strip()


def hazir_mi() -> bool:
    """Kart ile tahsilat açılabilir mi?"""
    return bool(anahtar())


def _basliklar() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {anahtar()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _cagir(
    yontem: str,
    yol: str,
    *,
    govde: Optional[Dict[str, Any]] = None,
) -> Any:
    """Shopier API'sine tek bir istek.

    Hata gövdesi log'a olduğu gibi yazılıyor: Shopier'in doğrulama
    mesajları alan adı veriyor, onlar olmadan "400 Bad Request"
    tek başına hiçbir şey anlatmıyor.
    """
    if not hazir_mi():
        raise ShopierHatasi("Shopier erişim anahtarı tanımlı değil")

    adres = f"{API_TABANI}{yol}"
    try:
        async with httpx.AsyncClient(timeout=ZAMAN_ASIMI) as istemci:
            yanit = await istemci.request(
                yontem, adres, headers=_basliklar(), json=govde
            )
    except httpx.HTTPError as hata:
        logger.warning("Shopier erişilemedi (%s %s): %s", yontem, yol, hata)
        raise ShopierHatasi("Shopier'e ulaşılamadı") from hata

    if yanit.status_code >= 400:
        logger.warning(
            "Shopier hata verdi (%s %s): %s %s",
            yontem,
            yol,
            yanit.status_code,
            yanit.text[:500],
        )
        if yanit.status_code in (401, 403):
            raise ShopierHatasi("Shopier erişim anahtarı geçersiz")
        raise ShopierHatasi(f"Shopier isteği reddetti ({yanit.status_code})")

    if not yanit.content:
        return None
    try:
        return yanit.json()
    except ValueError as hata:
        raise ShopierHatasi("Shopier okunamayan bir cevap döndü") from hata


def _tutar_metni(tutar: float) -> str:
    return f"{float(tutar):.2f}"


# --------------------------------------------------------------------------
# Ürün — bir faturanın ödeme bağlantısı
# --------------------------------------------------------------------------
async def odeme_urunu_olustur(
    *,
    baslik: str,
    aciklama: str,
    tutar: float,
    para_birimi: str = "TRY",
    gorsel: Optional[str] = None,
) -> Dict[str, str]:
    """Faturaya özel gizli bir ürün açar, satın alma linkini döndürür.

    `customListing` dükkânın vitrininde göstermiyor, `stockQuantity=1`
    ikinci kez ödenmesini engelliyor. İkisi birlikte, bir ödeme
    bağlantısının olması gereken davranışı veriyor.
    """
    birim = (para_birimi or "TRY").upper()
    if birim not in PARA_BIRIMLERI:
        birim = "TRY"

    govde: Dict[str, Any] = {
        "title": baslik[:200],
        "description": aciklama[:2000],
        "type": "digital",
        # `type` zorunlu: Shopier medyasız ürün kabul etmiyor ve
        # alanı eksik bırakınca "media[0].type is required" diyor.
        "media": [
            {"type": "image", "url": gorsel or VARSAYILAN_GORSEL, "placement": 1}
        ],
        "priceData": {
            "currency": birim,
            "price": _tutar_metni(tutar),
        },
        "stockQuantity": 1,
        "shippingPayer": "sellerPays",
        "customListing": True,
    }

    cevap = await _cagir("POST", "/products", govde=govde)
    urun_id = str((cevap or {}).get("id") or "").strip()
    adres = str((cevap or {}).get("url") or "").strip()
    if not urun_id or not adres:
        raise ShopierHatasi("Shopier ürünü oluşturdu ama link dönmedi")
    return {"urun_id": urun_id, "adres": adres}


async def odeme_urununu_kapat(urun_id: str) -> bool:
    """Ödendikten (ya da iptal edildikten) sonra ürünü stoktan düşürür.

    Silmek yerine stoğu sıfırlıyoruz: sipariş geçmişinde ürün adı
    görünmeye devam etsin, ama kimse aynı linkten ikinci kez
    ödeyemesin. Başarısız olursa iş durmuyor — tahsilat zaten alınmış.
    """
    urun_id = (urun_id or "").strip()
    if not urun_id:
        return False
    try:
        await _cagir(
            "PUT",
            f"/products/{urun_id}",
            govde={"stockQuantity": 0},
        )
        return True
    except ShopierHatasi as hata:
        logger.warning("Shopier ürünü kapatılamadı (%s): %s", urun_id, hata)
        return False


# --------------------------------------------------------------------------
# Sipariş — ödemenin gerçekten olduğunun kanıtı
# --------------------------------------------------------------------------
async def siparis_getir(siparis_id: str) -> Optional[Dict[str, Any]]:
    """Tek siparişi Shopier'den çeker."""
    siparis_id = (siparis_id or "").strip()
    if not siparis_id:
        return None
    try:
        return await _cagir("GET", f"/orders/{siparis_id}")
    except ShopierHatasi as hata:
        logger.warning("Shopier siparişi okunamadı (%s): %s", siparis_id, hata)
        return None


async def siparisleri_getir(limit: int = 50) -> List[Dict[str, Any]]:
    """Son siparişler — webhook kaçarsa mutabakat için."""
    try:
        cevap = await _cagir("GET", f"/orders?limit={int(limit)}")
    except ShopierHatasi as hata:
        logger.warning("Shopier siparişleri okunamadı: %s", hata)
        return []

    if isinstance(cevap, list):
        return cevap
    if isinstance(cevap, dict):
        for anahtar_adi in ("data", "orders", "items", "results"):
            deger = cevap.get(anahtar_adi)
            if isinstance(deger, list):
                return deger
    return []


def odenmis_mi(siparis: Optional[Dict[str, Any]]) -> bool:
    """Sipariş gerçekten ödenmiş mi?

    Shopier bugün yalnızca ödemesi tamamlanmış siparişleri döndürüyor
    ama alan ileride `unpaid` de alabilir; o gün sessizce yanlış
    çalışmasın diye açıkça kontrol ediliyor.
    """
    if not siparis:
        return False
    return str(siparis.get("paymentStatus") or "").strip().lower() == "paid"


def siparisin_urun_kimlikleri(siparis: Optional[Dict[str, Any]]) -> List[str]:
    """Siparişteki ürün id'leri — ödeme kaydıyla eşleştirme anahtarımız.

    Tutar ve e-posta ile eşleştirmiyoruz: aynı tutarda iki fatura
    olabilir, müşteri başka bir e-postayla ödeyebilir. Ürün id'si
    faturaya birebir bağlı.
    """
    if not siparis:
        return []
    satirlar = siparis.get("lineItems")
    if not isinstance(satirlar, list):
        return []
    kimlikler = []
    for satir in satirlar:
        if isinstance(satir, dict):
            deger = str(satir.get("productId") or "").strip()
            if deger:
                kimlikler.append(deger)
    return kimlikler


def siparis_tutari(siparis: Optional[Dict[str, Any]]) -> Optional[float]:
    if not siparis:
        return None
    toplamlar = siparis.get("totals")
    if not isinstance(toplamlar, dict):
        return None
    try:
        return float(str(toplamlar.get("total") or "").replace(",", "."))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Webhook imzası
# --------------------------------------------------------------------------
def webhook_imzasi_gecerli_mi(ham_govde: bytes, imza: str) -> bool:
    """Bildirimin Shopier'den geldiğini imzayla doğrular.

    Sır tanımlı değilse False dönüyor — ama bu bildirimi reddetmek
    için tek başına yeterli sayılmıyor: `odemeler.py` her hâlükârda
    siparişi API'den yeniden çekip oradan karar veriyor. İmza ek bir
    katman, tek dayanak değil.

    Shopier imzanın kodlamasını belgelemiyor; base64 ve hex'in ikisi
    de kabul ediliyor, karşılaştırma sabit zamanlı.
    """
    sir = webhook_sirri()
    imza = (imza or "").strip()
    if not sir or not imza or not ham_govde:
        return False

    ozet = hmac.new(sir.encode("utf-8"), ham_govde, hashlib.sha256).digest()
    adaylar = (
        base64.b64encode(ozet).decode("ascii"),
        ozet.hex(),
    )
    return any(hmac.compare_digest(aday, imza) for aday in adaylar)


# --------------------------------------------------------------------------
# Webhook abonelikleri
# --------------------------------------------------------------------------
# Webhook ucunu yazmak yetmiyor: Shopier'in bize bildirim gönderebilmesi
# için önce "şu olayı şu adrese yolla" diye abone olmak gerekiyor. İlk
# canlı denemede ödeme alındı ama panele düşmedi, çünkü bu adım
# atlanmıştı — uç hazırdı, Shopier adresimizi bilmiyordu.
ODEME_OLAYI = "order.created"


async def webhook_abonelikleri() -> List[Dict[str, Any]]:
    """Kayıtlı abonelikler."""
    try:
        cevap = await _cagir("GET", "/webhooks")
    except ShopierHatasi as hata:
        logger.warning("Shopier webhook abonelikleri okunamadi: %s", hata)
        return []

    if isinstance(cevap, list):
        return cevap
    if isinstance(cevap, dict):
        for ad in ("data", "webhooks", "items", "results"):
            deger = cevap.get(ad)
            if isinstance(deger, list):
                return deger
    return []


async def webhook_aboneligi_olustur(*, olay: str, adres: str) -> Dict[str, Any]:
    """Yeni abonelik açar.

    Cevapta dönen `token`, webhook yüklerinin imzasında kullanılıyor ve
    Shopier onu YALNIZCA bu ilk cevapta veriyor. Çağıran taraf saklamak
    zorunda; kaybolursa aboneliği silip yeniden açmaktan başka yol yok.
    """
    cevap = await _cagir("POST", "/webhooks", govde={"event": olay, "url": adres})
    if not isinstance(cevap, dict):
        raise ShopierHatasi("Shopier abonelik cevabı okunamadı")
    return cevap


async def webhook_aboneligi_sil(abonelik_id: str) -> bool:
    try:
        await _cagir("DELETE", f"/webhooks/{abonelik_id}")
        return True
    except ShopierHatasi as hata:
        logger.warning("Shopier webhook aboneligi silinemedi (%s): %s", abonelik_id, hata)
        return False


def webhook_imzasi_gecerli_mi_sirla(ham_govde: bytes, imza: str, sir: str) -> bool:
    """`webhook_imzasi_gecerli_mi` ile aynı, ama sırrı çağıran veriyor.

    Abonelik token'ı veritabanında duruyor (ortam değişkeninde değil):
    aboneliği panelden kuran kişinin token'ı bir yere kopyalayıp
    yapıştırması gerekmesin diye.
    """
    imza = (imza or "").strip()
    sir = (sir or "").strip()
    if not sir or not imza or not ham_govde:
        return False

    ozet = hmac.new(sir.encode("utf-8"), ham_govde, hashlib.sha256).digest()
    adaylar = (base64.b64encode(ozet).decode("ascii"), ozet.hex())
    return any(hmac.compare_digest(aday, imza) for aday in adaylar)
