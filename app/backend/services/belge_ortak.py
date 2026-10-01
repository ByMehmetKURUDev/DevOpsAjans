"""Faz 3T — teklif ve sözleşmenin ortak yardımcıları (numara, bağlantı süresi, e-posta)."""

import logging
import os
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TR = ZoneInfo("Europe/Istanbul")
EN_COK_BAGLANTI_GUN = 90
AD_EN_AZ = 2
AD_EN_COK = 120


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def tr_bugun() -> date:
    return simdi().astimezone(TR).date()


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def iso(an: Optional[datetime]) -> Optional[str]:
    a = utc(an)
    return a.isoformat() if a else None


def tarih_dogrula(metin: Optional[str], kod: str = "tarih_gecersiz") -> Optional[str]:
    """YYYY-MM-DD ya da boş. Geçersizse ValueError(kod)."""
    temiz = (metin or "").strip()[:10]
    if not temiz:
        return None
    try:
        return date.fromisoformat(temiz).isoformat()
    except ValueError:
        raise ValueError(kod)


def gun_sonu(gun: date) -> datetime:
    """Türkiye saatiyle o günün sonu (UTC)."""
    return datetime.combine(gun, time(23, 59, 59), tzinfo=TR).astimezone(timezone.utc)


def baglanti_bitisi(gecerlilik: Optional[str]) -> datetime:
    """İmzalı bağlantının son kullanması: geçerlilik gününün sonu, en çok 90 gün."""
    ust = simdi() + timedelta(days=EN_COK_BAGLANTI_GUN)
    if gecerlilik:
        try:
            return min(gun_sonu(date.fromisoformat(gecerlilik[:10])), ust)
        except ValueError:
            pass
    return ust


def baglanti_gunu(bitis: datetime) -> int:
    """`imzali_islem.olustur` gün ister (1–90); son kullanma sonra kesinleştiriliyor."""
    gun = (bitis - simdi()).total_seconds() / 86400
    return max(1, min(EN_COK_BAGLANTI_GUN, int(gun) + 1))


def ad_duzelt(ad: Optional[str]) -> str:
    """İmzalayan/kabul edenin yazdığı ad soyad: boşluklar sadeleşir, 2–120 karakter."""
    temiz = unicodedata.normalize("NFC", " ".join(str(ad or "").split()))
    temiz = re.sub(r"[\x00-\x1f\x7f<>]", "", temiz)
    if len(temiz) < AD_EN_AZ or len(temiz) > AD_EN_COK or not re.search(r"\w", temiz):
        raise ValueError("ad_gerekli")
    return temiz


def eposta_duzelt(eposta: Optional[str]) -> str:
    return (eposta or "").strip().lower()


EPOSTA = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]{2,}$")


def eposta_gecerli(eposta: str) -> bool:
    return bool(eposta) and len(eposta) <= 254 and bool(EPOSTA.match(eposta))


def site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


async def sirali_no(db: AsyncSession, sutun: Any, onek: str, yil: Optional[int] = None) -> str:
    """`ONEK-YYYY-NNNN`: o yılın en büyük numarası + 1 (revizyon ekleri yok sayılır)."""
    yil = yil or tr_bugun().year
    kalip = f"{onek}-{yil:04d}-"
    mevcutlar = (await db.execute(select(sutun).where(sutun.like(f"{kalip}%")))).scalars().all()
    en_buyuk = 0
    for no in mevcutlar:
        m = re.match(rf"^{re.escape(kalip)}(\d+)", no or "")
        if m:
            en_buyuk = max(en_buyuk, int(m.group(1)))
    return f"{kalip}{en_buyuk + 1:04d}"


async def baglantili_bildirim(
    db: AsyncSession,
    *,
    event_type: str,
    alici: str,
    baslik: str,
    govde: str,
    baglanti: str,
    ref_type: str,
    ref_id: Optional[int],
    panel_linki: str = "/client",
    degerler: Optional[Dict[str, Any]] = None,
) -> bool:
    """Ham jetonlu bağlantıyı alıcıya gönderir; kalıcı kayıttan jetonu siler.

    `dispatch` gövdeyi ve bağlantıyı `notifications` tablosuna da yazıyor.
    Ham jeton hiçbir tabloda kalmasın diye gönderimden hemen sonra o
    satırlardaki bağlantı panel adresiyle, gövdedeki adres "…" ile
    değiştiriliyor (imzalı işlem e-postasıyla aynı desen). Ekip üyelerine
    genişletilmiyor: olay `OLAY_IZNI`'nde yok — bağlantı bir yetki belgesi.
    E-posta gerçekten gittiyse True.
    """
    from services.notify import dispatch, render

    try:
        b, g = await render(db, event_type, baslik, govde, {"baglanti": baglanti, **(degerler or {})})
        satirlar = await dispatch(
            db,
            event_type=event_type,
            title=b,
            body=g,
            recipients=[{"email": alici, "role": "client"}],
            link=baglanti,
            ref_type=ref_type,
            ref_id=ref_id,
        )
        gitti = any(getattr(s, "channel", "") == "email" and getattr(s, "delivery_status", "") == "sent" for s in satirlar)
        for s in satirlar:
            if s.body:
                s.body = s.body.replace(baglanti, "…")
            if s.title:
                s.title = s.title.replace(baglanti, "…")
            s.link = panel_linki
        if satirlar:
            await db.commit()
        return gitti
    except Exception:  # noqa: BLE001 - bağlantı üretildi; e-posta düşse de yönetici kopyalayabilir
        logger.exception("Bağlantı e-postası gönderilemedi: %s %s", ref_type, ref_id)
        return False
