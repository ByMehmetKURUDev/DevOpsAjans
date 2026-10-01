"""İsteği yapanın IP'si ve saklanabilir özeti.

Site analizi (sınır sayımı) ve denetim kaydı aynı kuralı kullanıyor; iki
ayrı kopya zamanla birbirinden ayrışırdı, bu yüzden tek yerde duruyor.

Ham IP hiçbir yerde saklanmıyor; yalnız tuzlanmış sha256 özeti. "Aynı
kaynak mı" sorusunu cevaplamak yetiyor, kim olduğunu bilmek gerekmiyor.

Vekil imzası (Faz 4G)
---------------------
Sitenin Pages Function'ları (`functions/api/[[path]].js`, `q/[kod].js`,
`kart/[slug].js`, `menu/[slug].js`) arka uca Worker alt isteğiyle gidiyor; o
yüzden Render'a varan `CF-Connecting-IP` ziyaretçinin değil Cloudflare'in
Worker çıkış adresi oluyor. Ziyaretçinin adresi ayrıca `X-MK-Istemci-IP`
başlığıyla taşınıyor. Ama Render adresine (`*.onrender.com`) DOĞRUDAN gelen
biri de bu başlığı yazabilir ve IP tabanlı hız sınırlarını (giriş, formlar,
sipariş, yapay zekâ bütçesi) her istekte başka bir "IP" uydurarak atlatabilir.

Çözüm ortak bir gizli: Pages'te ve Render'da aynı değerli `VEKIL_ANAHTARI`
ortam değişkeni. Function'lar her arka uç isteğine `X-MK-Vekil-Anahtari`
başlığını ekliyor (ziyaretçinin gönderdiği aynı adlı başlığı her zaman
siliyor — `functions/_ortak/vekil.js`). Burada `X-MK-Istemci-IP`'ye yalnız
anahtar sabit zamanlı karşılaştırmayla eşleşirse güveniliyor.

Geçiş (iki değişken farklı zamanlarda girilebilir):

* Render'da `VEKIL_ANAHTARI` YOK → eski davranış: başlığa güvenilir; açılışta
  bir kez uyarı yazılır.
* Render'da VAR, istekte anahtar yok/yanlış → başlığa güvenilmez, istek yine
  çalışır; IP bağlantının kendisinden alınır (aşağıda). Pages'te değişken
  henüz yoksa bütün ziyaretçiler Cloudflare'in Worker adresinden geliyor
  görünür, yani hız sınırları ortak (kaba) olur — bunun için seyrek bir
  uyarı günlüğü yazılır. Önerilen sıra: önce Pages, sonra Render.

Bağlantının kendi IP'si (anahtar tanımlıyken)
--------------------------------------------
Render'ın önünde Cloudflare var (istemci → Cloudflare → Render vekili →
uygulama). Cloudflare `CF-Connecting-IP` ve `True-Client-IP` başlıklarını
kendisi yazıyor; istemcinin gönderdiği aynı adlı başlıkların üzerine yazıyor,
yani uydurulamıyorlar. `X-Forwarded-For` ise Render'da istemcinin gönderdiği
değeri SİLMEDEN sonuna ekleniyor (ilk değer uydurulabilir; araya Render'ın iç
adresleri de girebildiği için sondan sayım da güvenilir değil) — bu yüzden
anahtar tanımlıyken hiç kullanılmıyor. Hiçbiri yoksa (Cloudflare'siz yerel
çalışma) soket adresi.
"""

import hashlib
import hmac
import ipaddress
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: Ziyaretçi IP'sini taşıyan başlık (Pages Function'ları yazıyor).
IP_BASLIGI = "x-mk-istemci-ip"
#: Function'ların ortak gizliyi taşıdığı başlık.
VEKIL_BASLIGI = "x-mk-vekil-anahtari"
#: Bundan kısa anahtar açılışta uyarı verir (tahmin edilebilir olmasın).
EN_KISA_ANAHTAR = 32
#: "Anahtar eşleşmedi" uyarısı en çok bu aralıkla bir kez yazılır (saniye).
UYARI_ARALIGI_SN = 600

_son_uyari: Dict[str, float] = {}


def _vekil_anahtari() -> str:
    return (os.environ.get("VEKIL_ANAHTARI") or "").strip()


def _seyrek_uyar(tur: str, mesaj: str) -> bool:
    """Aynı türden uyarıyı en çok UYARI_ARALIGI_SN'de bir yazar; yazdıysa True."""
    simdi = time.monotonic()
    son = _son_uyari.get(tur)
    if son is not None and simdi - son < UYARI_ARALIGI_SN:
        return False
    _son_uyari[tur] = simdi
    logger.warning(mesaj)
    return True


def acilis_uyarisi() -> Optional[str]:
    """Anahtar yoksa ya da kısaysa açılışta bir kez yazılan uyarı (testler için döndürülüyor)."""
    anahtar = _vekil_anahtari()
    if not anahtar:
        mesaj = (
            "VEKIL_ANAHTARI tanımlı değil: X-MK-Istemci-IP başlığına imzasız güveniliyor. "
            "Render adresine doğrudan gelen biri IP tabanlı hız sınırlarını atlatabilir. "
            "Aynı değeri önce Cloudflare Pages'e, sonra Render'a VEKIL_ANAHTARI olarak girin."
        )
    elif len(anahtar) < EN_KISA_ANAHTAR:
        mesaj = (
            f"VEKIL_ANAHTARI çok kısa ({len(anahtar)} karakter); "
            f"en az {EN_KISA_ANAHTAR} karakterlik rastgele bir değer kullanın."
        )
    else:
        return None
    logger.warning(mesaj)
    return mesaj


def vekil_dogrulandi_mi(request: Any) -> Optional[bool]:
    """None: Render'da anahtar tanımlı değil (geçiş). True/False: istekteki anahtar eşleşti mi."""
    anahtar = _vekil_anahtari()
    if not anahtar:
        return None
    gelen = (request.headers.get(VEKIL_BASLIGI) or "").strip()
    # compare_digest uzunluk farkında da sabit zamanlı; boş değer eşleşmez.
    return bool(gelen) and hmac.compare_digest(gelen.encode("utf-8"), anahtar.encode("utf-8"))


def _gecerli_ip(deger: str) -> Optional[str]:
    try:
        return str(ipaddress.ip_address(deger.strip()))
    except ValueError:
        return None


def _baglanti_ip(request: Any, xff_kullan: bool) -> str:
    for ad in ("cf-connecting-ip", "true-client-ip"):
        deger = (request.headers.get(ad) or "").strip()
        if deger:
            return deger
    if xff_kullan:
        xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if xff:
            return xff
    return request.client.host if request.client else "bilinmiyor"


def istemci_ip(request: Any) -> str:
    """İsteği yapanın IP'si.

    1. `X-MK-Istemci-IP` — yalnız vekil anahtarı eşleşirse (ya da Render'da
       anahtar henüz tanımlı değilse; geçiş).
    2. `CF-Connecting-IP`, `True-Client-IP` — Cloudflare yazıyor, istemci
       değiştiremiyor.
    3. (yalnız anahtar tanımlı DEĞİLKEN, eski davranış) `X-Forwarded-For`'un
       ilk değeri.
    4. Soket adresi.
    """
    beyan = _gecerli_ip(request.headers.get(IP_BASLIGI) or "")
    dogrulama = vekil_dogrulandi_mi(request)
    if beyan:
        if dogrulama is None or dogrulama:
            return beyan
        if (request.headers.get(VEKIL_BASLIGI) or "").strip():
            _seyrek_uyar(
                "yanlis",
                "X-MK-Istemci-IP geldi ama X-MK-Vekil-Anahtari eşleşmedi: başlık yok sayıldı "
                "(Render adresine doğrudan istek ya da Pages ile Render'da farklı anahtar).",
            )
        else:
            _seyrek_uyar(
                "eksik",
                "X-MK-Istemci-IP geldi ama X-MK-Vekil-Anahtari yok: başlık yok sayıldı. Pages'te "
                "VEKIL_ANAHTARI tanımlı değilse bütün ziyaretçiler Cloudflare'in Worker adresinden "
                "geliyor görünür ve IP hız sınırları ortak (kaba) çalışır.",
            )
    return _baglanti_ip(request, xff_kullan=dogrulama is None)


def ip_ozeti(ip: str) -> str:
    """Tuzlanmış sha256 özeti (tuz: IP_OZET_TUZU ortam değişkeni)."""
    tuz = os.environ.get("IP_OZET_TUZU", "")
    return hashlib.sha256(f"{tuz}{ip}".encode("utf-8")).hexdigest()


# Açılışta bir kez: router'lar bu modülü uygulama kurulurken içe aktarıyor.
acilis_uyarisi()
