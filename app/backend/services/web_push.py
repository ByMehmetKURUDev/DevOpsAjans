"""
Web Push (tarayıcı bildirimi).

Ortam değişkenleri
------------------
VAPID_PUBLIC_KEY   tarayıcıya verilen açık anahtar (base64url, 65 bayt)
VAPID_PRIVATE_KEY  gizli anahtar (base64url, 32 bayt ham ya da DER)
VAPID_SUBJECT      push servislerinin ulaşabileceği adres;
                   varsayılan `mailto:by@mehmetkuru.dev`

Anahtar çifti `scripts/vapid_uret.py` ile üretilir. İkisinden biri yoksa
push "yapılandırılmadı" sayılıyor: dağıtıcı push satırını `skipped` yazıyor,
arayüz aç düğmesini göstermiyor.

Gönderim
--------
`pywebpush` eşzamanlı (requests). Olay döngüsünü tutmasın diye her abonelik
`asyncio.to_thread` ile ayrı iş parçacığında ve AYNI ANDA gönderiliyor;
alıcı başına en çok 5 abonelik (en yeniler), her biri 10 sn zaman aşımlı.
Push servisi 404/410 dönerse abonelik ölmüş: satır siliniyor. Başka bir
hata `hata_sayisi`nı artırıyor; art arda çok hata veren abonelik de
siliniyor (tarayıcı kaldırılmış ama servis bunu söylemiyor olabilir).
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from models.bildirim import PushSubscriptions
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ZAMAN_ASIMI = 10.0
ALICI_BASINA_EN_COK = 5
#: Bu kadar art arda başarısız gönderimden sonra abonelik siliniyor.
HATA_SINIRI = 10
#: Push servisi bildirimi en çok bu kadar saniye bekletsin (cihaz kapalıysa).
YASAM_SURESI = 24 * 3600
VARSAYILAN_KONU = "mailto:by@mehmetkuru.dev"


def _env(ad: str) -> str:
    return (os.environ.get(ad) or "").strip()


def vapid_ayarlari() -> Optional[Dict[str, str]]:
    acik, gizli = _env("VAPID_PUBLIC_KEY"), _env("VAPID_PRIVATE_KEY")
    if not (acik and gizli):
        return None
    return {"acik": acik, "gizli": gizli, "konu": _env("VAPID_SUBJECT") or VARSAYILAN_KONU}


def push_yapilandirildi() -> bool:
    return vapid_ayarlari() is not None


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


def _webpush_cagir(abonelik: Dict[str, Any], veri: str, gizli: str, konu: str) -> int:
    """Tek bir aboneliğe gönderir; HTTP durum kodunu döndürür (iş parçacığında).

    Test bu fonksiyonu değiştiriyor (monkeypatch); ağa çıkılmıyor.
    """
    from pywebpush import WebPushException, webpush

    try:
        yanit = webpush(
            subscription_info=abonelik,
            data=veri,
            vapid_private_key=gizli,
            # pywebpush sözlüğe `aud`/`exp` ekliyor; her çağrıya taze sözlük.
            vapid_claims={"sub": konu},
            timeout=ZAMAN_ASIMI,
            ttl=YASAM_SURESI,
        )
        return int(getattr(yanit, "status_code", 201) or 201)
    except WebPushException as hata:
        yanit = getattr(hata, "response", None)
        kod = getattr(yanit, "status_code", None)
        if kod:
            return int(kod)
        raise


async def _tek_gonder(abonelik: PushSubscriptions, veri: str, ayar: Dict[str, str]) -> Tuple[str, str]:
    """('ok' | 'olu' | 'hata', ayrıntı)."""
    bilgi = {"endpoint": abonelik.endpoint, "keys": {"p256dh": abonelik.p256dh, "auth": abonelik.auth}}
    try:
        kod = await asyncio.wait_for(
            asyncio.to_thread(_webpush_cagir, bilgi, veri, ayar["gizli"], ayar["konu"]),
            timeout=ZAMAN_ASIMI + 2,
        )
    except asyncio.TimeoutError:
        return "hata", "zaman aşımı"
    except Exception as hata:  # ağ, anahtar biçimi vb.
        return "hata", str(hata)[:160]
    if kod in (404, 410):
        return "olu", str(kod)
    if kod >= 300:
        return "hata", f"HTTP {kod}"
    return "ok", str(kod)


async def push_gonder(
    db: AsyncSession, eposta: str, baslik: str, govde: str, url: Optional[str] = None
) -> Tuple[str, str]:
    """Bir kişinin tarayıcılarına gönderir → (durum, ayrıntı).

    Abonelik satırlarındaki değişiklikler (silme, sayaç) oturuma yazılıyor;
    commit çağıranın (dağıtıcı) işi.
    """
    ayar = vapid_ayarlari()
    if ayar is None:
        return "skipped", "VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY tanımlı değil"

    sonuc = await db.execute(
        select(PushSubscriptions)
        .where(PushSubscriptions.eposta == (eposta or "").strip().lower())
        .order_by(PushSubscriptions.id.desc())
        .limit(ALICI_BASINA_EN_COK)
    )
    abonelikler: List[PushSubscriptions] = list(sonuc.scalars().all())
    if not abonelikler:
        return "skipped", "bu alıcının bildirim açık tarayıcısı yok"

    veri = json.dumps(
        {"title": (baslik or "")[:120], "body": (govde or "")[:300], "url": url or "/"},
        ensure_ascii=False,
    )
    sonuclar = await asyncio.gather(*(_tek_gonder(a, veri, ayar) for a in abonelikler))

    basarili, silinen, hatalar = 0, 0, []
    for abonelik, (durum, ayrinti) in zip(abonelikler, sonuclar):
        if durum == "ok":
            basarili += 1
            abonelik.son_basari_at = _simdi()
            abonelik.hata_sayisi = 0
        elif durum == "olu":
            silinen += 1
            await db.delete(abonelik)
        else:
            abonelik.hata_sayisi = int(abonelik.hata_sayisi or 0) + 1
            hatalar.append(ayrinti)
            if abonelik.hata_sayisi >= HATA_SINIRI:
                silinen += 1
                await db.delete(abonelik)

    ozet = f"push {basarili}/{len(abonelikler)} tarayıcı"
    if silinen:
        ozet += f", {silinen} ölü abonelik silindi"
    if hatalar:
        ozet += f" · {hatalar[0]}"
    return ("sent" if basarili else "failed"), ozet[:300]


def ua_ozeti(ua: Optional[str]) -> str:
    """Tam UA dizgesi yerine "Chrome · Android" gibi kısa bir özet."""
    ua = ua or ""
    tarayici = next(
        (ad for anahtar, ad in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"),
                                ("Chrome/", "Chrome"), ("Safari/", "Safari")) if anahtar in ua),
        "Tarayıcı",
    )
    sistem = next(
        (ad for anahtar, ad in (("Android", "Android"), ("iPhone", "iOS"), ("iPad", "iPadOS"),
                                ("Windows", "Windows"), ("Mac OS", "macOS"), ("Linux", "Linux")) if anahtar in ua),
        "",
    )
    return f"{tarayici} · {sistem}" if sistem else tarayici
