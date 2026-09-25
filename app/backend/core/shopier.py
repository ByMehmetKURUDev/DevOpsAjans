"""Shopier ödeme formu ve geri bildirim doğrulaması.

Shopier'de akış şöyle işliyor: sunucu bir HTML formunun alanlarını
imzalayıp müşteriye veriyor, müşterinin tarayıcısı o formu Shopier'e
POST ediyor, kart bilgisi Shopier'de giriliyor. Kart numarası hiçbir
zaman bize uğramıyor — bu yüzden PCI yükümlülüğü de bizde değil.

Ödeme bitince Shopier, müşterinin tarayıcısını `callback` adresine POST
ile geri gönderiyor. O çağrının içinde `signature` var ve HMAC-SHA256
ile doğrulanıyor.

İki imza farklı dizeler üzerinden kuruluyor; Shopier böyle tanımlamış:

* Form imzası:   random_nr + platform_order_id + total_order_value + currency
* Dönüş imzası:  random_nr + platform_order_id

Dönüş imzası tutarı kapsamadığı için **geri bildirimin bildirdiği tutara
güvenmiyoruz**. Faturayı kendi kaydımızdaki tutarla kapatıyoruz; dönüşten
yalnızca "ödendi mi" bilgisi ile Shopier'in ödeme numarası alınıyor.
Aksi halde imzayı üretebilen biri tutarı bir kuruşa indirip faturayı
kapatabilirdi.

Anahtarlar ortam değişkeninde: SHOPIER_API_KEY, SHOPIER_API_SECRET.
Panele ya da veritabanına yazılmıyor.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import random
from typing import Dict, Optional, Tuple

ODEME_ADRESI = "https://www.shopier.com/ShowProduct/api_pay4.php"

# Shopier para birimini sayı bekliyor.
PARA_KODLARI = {"TRY": "0", "TL": "0", "USD": "1", "EUR": "2"}


def anahtarlar() -> Tuple[Optional[str], Optional[str]]:
    return os.getenv("SHOPIER_API_KEY"), os.getenv("SHOPIER_API_SECRET")


def hazir_mi() -> bool:
    api_key, api_secret = anahtarlar()
    return bool(api_key and api_secret)


def yeni_rastgele() -> str:
    """Shopier altı haneli bir sayı bekliyor."""
    return str(random.randint(100000, 999999))


def _imzala(veri: str, api_secret: str) -> str:
    ozet = hmac.new(api_secret.encode("utf-8"), veri.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(ozet).decode("ascii")


def _tutar_metni(tutar: float) -> str:
    """Shopier iki ondalıklı, noktalı biçim bekliyor.

    İmza bu metnin birebir aynısı üzerinden kuruluyor; formda başka bir
    biçim gönderilirse Shopier imzayı reddediyor.
    """
    return f"{float(tutar):.2f}"


def form_alanlari(
    *,
    siparis_no: str,
    tutar: float,
    para_birimi: str,
    urun_adi: str,
    ad: str,
    soyad: str,
    eposta: str,
    telefon: str,
    donus_adresi: str,
    rastgele: str,
) -> Dict[str, str]:
    """Müşterinin tarayıcısının Shopier'e göndereceği alanlar."""
    api_key, api_secret = anahtarlar()
    if not api_key or not api_secret:
        raise RuntimeError("Shopier anahtarları tanımlı değil")

    para = PARA_KODLARI.get((para_birimi or "TRY").upper(), "0")
    tutar_metni = _tutar_metni(tutar)
    imza = _imzala(f"{rastgele}{siparis_no}{tutar_metni}{para}", api_secret)

    return {
        "API_key": api_key,
        "website_index": "1",
        "platform_order_id": siparis_no,
        "product_name": (urun_adi or "Hizmet bedeli")[:100],
        # 1 = dijital/hizmet: kargo adresi istenmiyor.
        "product_type": "1",
        "buyer_name": ad[:50],
        "buyer_surname": soyad[:50],
        "buyer_email": eposta[:100],
        "buyer_phone": telefon[:20],
        "buyer_account_age": "0",
        "buyer_id_nr": "",
        "billing_address": "-",
        "billing_city": "-",
        "billing_country": "Turkiye",
        "billing_postcode": "34000",
        "shipping_address": "-",
        "shipping_city": "-",
        "shipping_country": "Turkiye",
        "shipping_postcode": "34000",
        "total_order_value": tutar_metni,
        "currency": para,
        "platform": "0",
        "is_in_frame": "0",
        "current_language": "0",
        "modul_version": "mkdev-1.0",
        "random_nr": rastgele,
        "callback": donus_adresi,
        "signature": imza,
    }


def donus_gecerli_mi(*, rastgele: str, siparis_no: str, imza: str) -> bool:
    """Geri bildirimin imzasını doğrular.

    `rastgele` bizim kaydımızdan geliyor, gelen çağrıdan değil: yoksa
    saldırgan kendi seçtiği bir sayıyla imza üretebilirdi.
    """
    _, api_secret = anahtarlar()
    if not api_secret or not rastgele or not imza:
        return False
    beklenen = _imzala(f"{rastgele}{siparis_no}", api_secret)
    # Sabit süreli karşılaştırma: imzayı deneme yanılma ile bulmayı
    # zorlaştırıyor.
    return hmac.compare_digest(beklenen, imza.strip())
