"""Dosya içeriğinin nereye yazıldığı — kalıcı depo seçimi.

Sorun: Render'ın ücretsiz planında kalıcı disk YOK
--------------------------------------------------
Sunucunun diski her yayında (ve uyuyup uyanınca) sıfırlanıyor; yerel diske
yazılan dosya bir sonraki deploy'da kayboluyor. Mevcut `routers/storage.py`
ise platformun (Atoms/MetaGPT) kendi nesne deposu servisine bağlı
(`OSS_SERVICE_URL` + `OSS_API_KEY`) — Render'da bu değişkenler yok, uçlar
kullanılamıyor. Yani yerel disk de o servis de kalıcı çözüm değil.

Karar
-----
1. **S3 uyumlu nesne deposu** (Cloudflare R2 önerilir; `render.yaml` zaten
   `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` bekliyor):
   dört değişken (+ `S3_BUCKET`) tanımlıysa içerik oraya yazılıyor. İndirme,
   depo tarafından imzalanmış 15 dakikalık adrese yönlendirme — dosya
   Render'ın bant genişliğinden geçmiyor. İmzalama (AWS SigV4) elle: boto3
   gibi ağır bir bağımlılık eklenmedi.
2. **Yedek: veritabanı** (`dosya_icerikleri`, Postgres BYTEA). Değişkenler
   yoksa özellik yine çalışıyor ve dosyalar KALICI (Neon/Render Postgres).
   Bedeli veritabanı boyutu: ücretsiz Postgres kotası küçük, bu yüzden
   panel depo türünü gösteriyor ve R2'ye geçiş öneriliyor.

Her dosya satırı hangi depoya yazıldığını (`files.depo`) taşıyor: R2 sonradan
açılırsa eski dosyalar veritabanından okunmaya devam ediyor.
"""

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from urllib.parse import quote, urlsplit

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ZAMAN_ASIMI = 60.0
BOS_OZET = hashlib.sha256(b"").hexdigest()


# ---------------------------------------------------------------------------
# AWS SigV4 (S3) — saf fonksiyonlar, test vektörleriyle doğrulanıyor
# ---------------------------------------------------------------------------
def _uri_kodla(metin: str, egik_koru: bool = True) -> str:
    guvenli = "-_.~/" if egik_koru else "-_.~"
    return quote(metin, safe=guvenli)


def _anahtar_turet(gizli: str, gun: str, bolge: str, servis: str = "s3") -> bytes:
    k = hmac.new(("AWS4" + gizli).encode(), gun.encode(), hashlib.sha256).digest()
    k = hmac.new(k, bolge.encode(), hashlib.sha256).digest()
    k = hmac.new(k, servis.encode(), hashlib.sha256).digest()
    return hmac.new(k, b"aws4_request", hashlib.sha256).digest()


def _kanonik_sorgu(parametreler: Dict[str, str]) -> str:
    return "&".join(
        f"{_uri_kodla(k, False)}={_uri_kodla(str(v), False)}" for k, v in sorted(parametreler.items())
    )


def sigv4_imza(
    *,
    yontem: str,
    url: str,
    basliklar: Dict[str, str],
    govde_ozeti: str,
    an: datetime,
    erisim: str,
    gizli: str,
    bolge: str,
    sorgu: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """(imza, imzalanan_basliklar). `basliklar` host dahil, küçük harf anahtar."""
    parca = urlsplit(url)
    gun = an.strftime("%Y%m%d")
    zaman = an.strftime("%Y%m%dT%H%M%SZ")
    ad_sirali = sorted(basliklar)
    kanonik_basliklar = "".join(f"{a}:{' '.join(str(basliklar[a]).split())}\n" for a in ad_sirali)
    imzalananlar = ";".join(ad_sirali)
    istek = "\n".join(
        [
            yontem.upper(),
            _uri_kodla(parca.path or "/"),
            _kanonik_sorgu(sorgu or {}),
            kanonik_basliklar,
            imzalananlar,
            govde_ozeti,
        ]
    )
    kapsam = f"{gun}/{bolge}/s3/aws4_request"
    metin = "\n".join(["AWS4-HMAC-SHA256", zaman, kapsam, hashlib.sha256(istek.encode()).hexdigest()])
    imza = hmac.new(_anahtar_turet(gizli, gun, bolge), metin.encode(), hashlib.sha256).hexdigest()
    return imza, imzalananlar


def on_imzali_adres(
    *, url: str, an: datetime, erisim: str, gizli: str, bolge: str, sure_sn: int, ek_sorgu: Optional[Dict[str, str]] = None
) -> str:
    """Süreli GET adresi (query string ile imzalı; gövde UNSIGNED-PAYLOAD)."""
    parca = urlsplit(url)
    gun = an.strftime("%Y%m%d")
    sorgu = dict(ek_sorgu or {})
    sorgu.update(
        {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{erisim}/{gun}/{bolge}/s3/aws4_request",
            "X-Amz-Date": an.strftime("%Y%m%dT%H%M%SZ"),
            "X-Amz-Expires": str(int(sure_sn)),
            "X-Amz-SignedHeaders": "host",
        }
    )
    imza, _ = sigv4_imza(
        yontem="GET", url=url, basliklar={"host": parca.netloc}, govde_ozeti="UNSIGNED-PAYLOAD",
        an=an, erisim=erisim, gizli=gizli, bolge=bolge, sorgu=sorgu,
    )
    return f"{parca.scheme}://{parca.netloc}{_uri_kodla(parca.path)}?{_kanonik_sorgu(sorgu)}&X-Amz-Signature={imza}"


# ---------------------------------------------------------------------------
# Depolar
# ---------------------------------------------------------------------------
class DepoHatasi(Exception):
    pass


@dataclass(frozen=True)
class S3Ayari:
    uc: str
    erisim: str
    gizli: str
    kova: str
    bolge: str


def s3_ayari() -> Optional[S3Ayari]:
    uc = (os.environ.get("S3_ENDPOINT_URL") or "").strip().rstrip("/")
    erisim = (os.environ.get("S3_ACCESS_KEY_ID") or "").strip()
    gizli = (os.environ.get("S3_SECRET_ACCESS_KEY") or "").strip()
    kova = (os.environ.get("S3_BUCKET") or "").strip()
    if not (uc and erisim and gizli and kova):
        return None
    # R2 "auto" bölgesini kabul ediyor; AWS için S3_REGION verilmeli.
    return S3Ayari(uc, erisim, gizli, kova, (os.environ.get("S3_REGION") or "auto").strip())


def _nesne_adresi(ayar: S3Ayari, anahtar: str) -> str:
    # Yol biçimi (path-style): R2 ve MinIO ile aynı çalışıyor.
    return f"{ayar.uc}/{ayar.kova}/{anahtar}"


async def _s3_istek(ayar: S3Ayari, yontem: str, anahtar: str, veri: bytes = b"", tur: Optional[str] = None) -> httpx.Response:
    url = _nesne_adresi(ayar, anahtar)
    an = datetime.now(timezone.utc)
    ozet = hashlib.sha256(veri).hexdigest() if veri else BOS_OZET
    basliklar = {
        "host": urlsplit(url).netloc,
        "x-amz-content-sha256": ozet,
        "x-amz-date": an.strftime("%Y%m%dT%H%M%SZ"),
    }
    if tur:
        basliklar["content-type"] = tur
    imza, imzalananlar = sigv4_imza(
        yontem=yontem, url=url, basliklar=basliklar, govde_ozeti=ozet, an=an,
        erisim=ayar.erisim, gizli=ayar.gizli, bolge=ayar.bolge,
    )
    gonderilen = {k: v for k, v in basliklar.items() if k != "host"}
    gonderilen["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={ayar.erisim}/{an.strftime('%Y%m%d')}/{ayar.bolge}/s3/aws4_request, "
        f"SignedHeaders={imzalananlar}, Signature={imza}"
    )
    async with httpx.AsyncClient(timeout=ZAMAN_ASIMI) as istemci:
        return await istemci.request(yontem, _uri_kodla_tam(url), headers=gonderilen, content=veri or None)


def _uri_kodla_tam(url: str) -> str:
    parca = urlsplit(url)
    return f"{parca.scheme}://{parca.netloc}{_uri_kodla(parca.path)}"


def depo_turu() -> str:
    """Yeni yüklemenin gideceği depo: s3 | veritabani."""
    return "s3" if s3_ayari() else "veritabani"


def depo_bilgisi() -> Dict[str, object]:
    """Yönetici paneli için: hangi depo, kalıcı mı, öneri."""
    tur = depo_turu()
    return {
        "tur": tur,
        "kalici": True,
        "oneri": None if tur == "s3" else "r2",
    }


async def yaz(db: AsyncSession, anahtar: str, veri: bytes, tur: str) -> str:
    """İçeriği yazar; hangi depoya yazdığını döndürür (commit ETMEZ — veritabanı deposunda)."""
    ayar = s3_ayari()
    if ayar is not None:
        yanit = await _s3_istek(ayar, "PUT", anahtar, veri, tur)
        if yanit.status_code >= 300:
            logger.error("S3 yazma hatası %s: %s", yanit.status_code, yanit.text[:200])
            raise DepoHatasi("yazilamadi")
        return "s3"
    from models.dosyalar import DosyaIcerikleri

    db.add(DosyaIcerikleri(anahtar=anahtar, veri=veri, boyut=len(veri)))
    return "veritabani"


async def oku(db: AsyncSession, depo: str, anahtar: str) -> bytes:
    if depo == "s3":
        ayar = s3_ayari()
        if ayar is None:
            raise DepoHatasi("s3_tanimsiz")
        yanit = await _s3_istek(ayar, "GET", anahtar)
        if yanit.status_code >= 300:
            raise DepoHatasi("okunamadi")
        return yanit.content
    from models.dosyalar import DosyaIcerikleri

    satir = (await db.execute(select(DosyaIcerikleri.veri).where(DosyaIcerikleri.anahtar == anahtar))).first()
    if satir is None:
        raise DepoHatasi("bulunamadi")
    return bytes(satir[0])


async def sil(db: AsyncSession, depo: str, anahtar: str) -> None:
    if depo == "s3":
        ayar = s3_ayari()
        if ayar is None:
            return
        try:
            await _s3_istek(ayar, "DELETE", anahtar)
        except Exception:  # noqa: BLE001 - silinemeyen nesne kaydı düşürmesin
            logger.warning("S3 nesnesi silinemedi: %s", anahtar)
        return
    from models.dosyalar import DosyaIcerikleri

    await db.execute(delete(DosyaIcerikleri).where(DosyaIcerikleri.anahtar == anahtar))


def dogrudan_adres(depo: str, anahtar: str, ad: str, tur: str, sure_sn: int = 900) -> Optional[str]:
    """S3'te: depo tarafından imzalanmış süreli adres. Veritabanında None (uç akıtır)."""
    if depo != "s3":
        return None
    ayar = s3_ayari()
    if ayar is None:
        return None
    return on_imzali_adres(
        url=_nesne_adresi(ayar, anahtar),
        an=datetime.now(timezone.utc),
        erisim=ayar.erisim,
        gizli=ayar.gizli,
        bolge=ayar.bolge,
        sure_sn=sure_sn,
        ek_sorgu={
            "response-content-disposition": icerik_konumu(ad),
            "response-content-type": tur,
        },
    )


def icerik_konumu(ad: str) -> str:
    """RFC 6266: ASCII yedek + UTF-8 ad (Türkçe harfler bozulmasın)."""
    ascii_ad = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in ad) or "dosya"
    return f"attachment; filename=\"{ascii_ad}\"; filename*=UTF-8''{quote(ad, safe='')}"
