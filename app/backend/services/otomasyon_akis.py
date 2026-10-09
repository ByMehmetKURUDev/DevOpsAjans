"""Faz 11C — Otomasyon › Akış görünümü için çalışma özeti.

Kural yapısı doğrusal (tetikleyici → koşul grubu → en çok 5 eylem, "bekle" dahil); akışı ön yüz kuraldan
kendisi çiziyor. Bu modül yalnız sağ sütundaki sayıları üretiyor ve hepsi `otomasyon_calismalari`
tablosundan geliyor (uydurma metrik yok):

- son 30 gün çalışma sayısı (tümü + seçili kural) ve günlük seri (UTC gün kovaları, 30 değer),
- başarı: biten çalışmalarda `tamam / (tamam + hata + atlandi)`; koşulu tutmayan çalışma başarısızlık
  sayılmaz (kural "çalışmadı" demektir), bekleyen henüz bitmemiştir. Hiç biten yoksa oran `None`,
- seçili kuralın son 3 çalışması.

Günlük 30 gün saklanıyor (`saklama_gun`); bu yüzden pencere "bu ay" değil, "son 30 gün".
Sahiplik: `_sahip_kosulu_calisma` (ajans ↔ müşteri hesabı) — günlük ucuyla birebir aynı.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models.otomasyon import OtomasyonCalismalari, OtomasyonKurallari
from services import otomasyon as s
from services.api_erisimi import Sahip
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

PENCERE_GUN = 30
SON_SAYISI = 3
BASARILI = {"tamam"}
BASARISIZ = {"hata", "atlandi"}


def _gun(deger: Any) -> Optional[date]:
    """`func.date()` SQLite'ta metin, PostgreSQL'de date döndürür."""
    if deger is None:
        return None
    if isinstance(deger, datetime):
        return deger.date()
    if isinstance(deger, date):
        return deger
    try:
        return date.fromisoformat(str(deger)[:10])
    except ValueError:
        return None


async def _sayilar(db: AsyncSession, kosul: Any, esik: datetime, bugun: date) -> Dict[str, Any]:
    durumlar = dict(
        (await db.execute(
            select(OtomasyonCalismalari.durum, func.count(OtomasyonCalismalari.id))
            .where(kosul, OtomasyonCalismalari.created_at >= esik)
            .group_by(OtomasyonCalismalari.durum)
        )).all()
    )
    gunluk = (await db.execute(
        select(func.date(OtomasyonCalismalari.created_at), func.count(OtomasyonCalismalari.id))
        .where(kosul, OtomasyonCalismalari.created_at >= esik)
        .group_by(func.date(OtomasyonCalismalari.created_at))
    )).all()
    kova: Dict[date, int] = {}
    for g, n in gunluk:
        d = _gun(g)
        if d is not None:
            kova[d] = kova.get(d, 0) + int(n or 0)
    ilk = bugun - timedelta(days=PENCERE_GUN - 1)
    seri = [kova.get(ilk + timedelta(days=i), 0) for i in range(PENCERE_GUN)]
    basarili = sum(int(durumlar.get(d, 0) or 0) for d in BASARILI)
    basarisiz = sum(int(durumlar.get(d, 0) or 0) for d in BASARISIZ)
    biten = basarili + basarisiz
    return {
        "toplam": int(sum(int(v or 0) for v in durumlar.values())),
        "seri": seri,
        "durumlar": {str(k): int(v or 0) for k, v in durumlar.items()},
        "basari": {
            "basarili": basarili,
            "basarisiz": basarisiz,
            "oran": round(basarili / biten, 4) if biten else None,
        },
    }


async def akis_ozeti(db: AsyncSession, sahip: Sahip, kural: Optional[OtomasyonKurallari] = None,
                     simdi: Optional[datetime] = None) -> Dict[str, Any]:
    an = simdi or datetime.now(timezone.utc)
    bugun = an.date()
    esik = datetime.combine(bugun - timedelta(days=PENCERE_GUN - 1), datetime.min.time(), tzinfo=timezone.utc)
    sahip_kosulu = s._sahip_kosulu_calisma(sahip.sahip_tur, None if sahip.yonetici else sahip.hesap)

    kural_sayisi = int((await db.execute(
        select(func.count(OtomasyonKurallari.id)).where(sahip.sahip_kosulu(OtomasyonKurallari))
    )).scalar() or 0)
    etkin_kural = int((await db.execute(
        select(func.count(OtomasyonKurallari.id)).where(sahip.sahip_kosulu(OtomasyonKurallari), OtomasyonKurallari.aktif.is_(True))
    )).scalar() or 0)

    sonuc: Dict[str, Any] = {
        "pencere_gun": PENCERE_GUN,
        "seri_baslangic": (bugun - timedelta(days=PENCERE_GUN - 1)).isoformat(),
        "kural_sayisi": kural_sayisi,
        "etkin_kural": etkin_kural,
        "tumu": await _sayilar(db, sahip_kosulu, esik, bugun),
        "kural": None,
    }
    if kural is not None:
        k_kosul = and_(sahip_kosulu, OtomasyonCalismalari.kural_id == kural.id)
        ozet = await _sayilar(db, k_kosul, esik, bugun)
        son: List[OtomasyonCalismalari] = list((await db.execute(
            select(OtomasyonCalismalari).where(k_kosul).order_by(OtomasyonCalismalari.id.desc()).limit(SON_SAYISI)
        )).scalars().all())
        ozet.update({
            "id": kural.id,
            "toplam_omur": int(kural.calisma_sayisi or 0),
            "son_calisma_at": s.iso(kural.son_calisma_at),
            "son": [
                {
                    "id": c.id,
                    "durum": c.durum,
                    "neden": c.neden,
                    "olay_hesap": c.olay_hesap,
                    "zaman": s.iso(c.created_at),
                    "bitis": s.iso(c.bitis_at),
                    "eylem_sayisi": len(s._json(c.eylem_sonuclari, [])) if c.eylem_sonuclari else 0,
                }
                for c in son
            ],
        })
        sonuc["kural"] = ozet
    return sonuc
