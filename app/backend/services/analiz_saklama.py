"""Faz 7H — ham analiz olaylarının saklama süresi (13 ay) ve süresi geçmiş hız sayaçları.

Ham olay tabloları her görüntülemede / taramada / tıklamada bir satır büyüyordu ve
hiç silinmiyordu. Zamanlı `saklama_temizligi` görevi (günde bir) 13 aydan
(`SAKLAMA_GUN`) eski ham olayları siliyor:

==========================  ==========================================  ===========================
Tablo                       Panelde ne gösteriliyor                     Silmeden önce
==========================  ==========================================  ===========================
dinamik_qr_taramalari       son 1–365 gün + TÜM ZAMANLAR toplamı        günlük özete toplanır
kartvizit_olaylari          son 1–365 gün + TÜM ZAMANLAR toplamı        günlük özete toplanır
  (kart + yorum sayfası)
ep_tiklamalar               kampanya raporunda bağlantı başına toplam   günlük özete toplanır
menu_olaylari               yalnız seçilen dönem (en çok 365 gün)       yalnız silinir
randevu_olaylari            yalnız seçilen dönem (en çok 365 gün)       yalnız silinir
ep_webhook_olaylari         gösterilmiyor (Resend olay kimliği kilidi)  yalnız silinir
==========================  ==========================================  ===========================

Dönem seçimi en çok 365 gün, saklama 395 gün: seçilen dönemin hiçbir günü
silinmiş olmuyor. "Tüm zamanlar" toplamı ham + `analiz_gunluk_ozetleri` olarak
hesaplanıyor (`toplamlar`); o yüzden kullanıcının gördüğü sayılar silmeden
önceyle aynı. Günler BÜTÜN olarak işleniyor (bir günün yarısı ham, yarısı özet
olmuyor): IP özeti güne tuzlu olduğu için tüm zamanların tekil ziyaretçisi =
günlük tekillerin toplamı, birebir korunuyor.

Özet yalnız hâlâ var olan (ya da çöp kutusunda bekleyen) kayıtlar için
yazılıyor; kalıcı silinmiş kaydın özeti de temizleniyor. Bir turda kaynak
başına en çok `GUN_SINIRI` gün işleniyor (birikmiş geçmiş birkaç turda erir).

Zaten süreli olanlar burada YOK: AI asistan sohbetleri (asistanın saklama
ayarı, varsayılan 90 gün), uptime ölçümleri (90 gün / günlük özet 400 gün),
denetim kaydı (365 gün), otomasyon günlüğü ve webhook teslimatları (30 gün),
CSP raporları (en yeni N satır), site analizleri.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from models.hiz_sayaclari import AnalizGunlukOzetleri
from sqlalchemy import case, delete, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: 13 ay. Panellerdeki dönem seçimi en çok 365 gün; arada pay var.
SAKLAMA_AY = 13
SAKLAMA_GUN = 395
#: Bir turda kaynak başına işlenecek en çok gün (ilk çalışmada birikmiş geçmiş).
GUN_SINIRI = 31

O = AnalizGunlukOzetleri


def bugun_utc() -> date:
    return datetime.now(timezone.utc).date()


def kesim_gunu(bugun: Optional[date] = None) -> date:
    """Bu günden ÖNCEKİ günlerin ham olayları silinir."""
    return (bugun or bugun_utc()) - timedelta(days=SAKLAMA_GUN)


# ---------------------------------------------------------------------------
# Paneller: tüm zamanlar toplamına eklenecek özet
# ---------------------------------------------------------------------------
async def toplamlar(db: AsyncSession, kaynak: str, nesne_id: int) -> Dict[str, Dict[str, int]]:
    """Özetlenmiş (silinmiş) günlerin toplamı, olay başına: {olay: {sayi, tekil, qr, bot}}."""
    satirlar = (
        await db.execute(
            select(O.olay, func.sum(O.sayi), func.sum(O.tekil), func.sum(O.qr), func.sum(O.bot))
            .where(O.kaynak == kaynak, O.nesne_id == int(nesne_id))
            .group_by(O.olay)
        )
    ).all()
    return {
        (olay or ""): {"sayi": int(s or 0), "tekil": int(t or 0), "qr": int(q or 0), "bot": int(b or 0)}
        for olay, s, t, q, b in satirlar
    }


def toplam_al(ozet: Dict[str, Dict[str, int]], alan: str, olay: Optional[str] = None) -> int:
    if olay is not None:
        return int((ozet.get(olay) or {}).get(alan, 0))
    return sum(int(d.get(alan, 0)) for d in ozet.values())


# ---------------------------------------------------------------------------
# Yaşayan kayıtlar (özet yalnız bunlar için)
# ---------------------------------------------------------------------------
async def _yasayanlar(db: AsyncSession, tablo: str, idler: Iterable[int]) -> Set[int]:
    from models.cop_kutusu import CopKutusu

    idler = sorted({int(i) for i in idler if i is not None})
    if not idler:
        return set()
    canli: Set[int] = set()
    for i in range(0, len(idler), 500):
        parca = idler[i : i + 500]
        canli |= {
            int(r[0])
            for r in (await db.execute(text(f"SELECT id FROM {tablo} WHERE id IN ({','.join(str(x) for x in parca)})"))).all()
        }
        cop = (
            await db.execute(
                select(CopKutusu.kayit_id).where(
                    CopKutusu.tablo == tablo, CopKutusu.geri_alindi.is_(False),
                    CopKutusu.kayit_id.in_([str(x) for x in parca]),
                )
            )
        ).all()
        canli |= {int(r[0]) for r in cop if str(r[0] or "").isdigit()}
    return canli


async def _ozete_ekle(db: AsyncSession, kaynak: str, satirlar: List[Tuple[int, str, str, int, int, int, int]]) -> int:
    """(nesne, olay, gün, sayi, tekil, qr, bot) satırlarını özete EKLER (varsa toplar)."""
    if not satirlar:
        return 0
    gunler = sorted({s[2] for s in satirlar})
    nesneler = sorted({s[0] for s in satirlar})
    mevcut = {
        (r.nesne_id, r.olay, r.gun): r
        for r in (
            await db.execute(select(O).where(O.kaynak == kaynak, O.nesne_id.in_(nesneler), O.gun.in_(gunler)))
        ).scalars().all()
    }
    for nesne, olay, gun, sayi, tekil, qr, bot in satirlar:
        r = mevcut.get((nesne, olay, gun))
        if r is None:
            db.add(O(kaynak=kaynak, nesne_id=nesne, olay=olay, gun=gun, sayi=sayi, tekil=tekil, qr=qr, bot=bot))
        else:
            r.sayi, r.tekil, r.qr, r.bot = r.sayi + sayi, r.tekil + tekil, r.qr + qr, r.bot + bot
    return len(satirlar)


async def _eski_gunler(db: AsyncSession, gun_sutunu: Any, kesim: str, sinir: int) -> List[str]:
    return [
        str(r[0])
        for r in (
            await db.execute(select(distinct(gun_sutunu)).where(gun_sutunu < kesim).order_by(gun_sutunu).limit(sinir))
        ).all()
    ]


# ---------------------------------------------------------------------------
# Kaynaklar
# ---------------------------------------------------------------------------
async def _qr(db: AsyncSession, kesim: str) -> Dict[str, int]:
    from models.dinamik_qr import DinamikQrTaramalari as T

    gunler = await _eski_gunler(db, T.gun, kesim, GUN_SINIRI)
    if not gunler:
        return {"gun": 0, "ozet": 0, "silinen": 0}
    insan = case((T.bot.is_(False), 1), else_=0)
    satirlar = (
        await db.execute(
            select(
                T.qr_id, T.gun, func.sum(insan),
                func.count(distinct(case((T.bot.is_(False), T.ip_ozeti), else_=None))),
                func.sum(case((T.bot.is_(True), 1), else_=0)),
            ).where(T.gun.in_(gunler)).group_by(T.qr_id, T.gun)
        )
    ).all()
    canli = await _yasayanlar(db, "dinamik_qr", (r[0] for r in satirlar))
    ozet = await _ozete_ekle(db, "qr", [
        (int(q), "", str(g), int(s or 0), int(t or 0), 0, int(b or 0)) for q, g, s, t, b in satirlar if int(q) in canli
    ])
    silinen = (await db.execute(delete(T).where(T.gun.in_(gunler)))).rowcount
    await db.commit()
    return {"gun": len(gunler), "ozet": ozet, "silinen": int(silinen or 0)}


async def _kartvizit(db: AsyncSession, kesim: str) -> Dict[str, int]:
    from models.kartvizit import KartvizitOlaylari as T

    gunler = await _eski_gunler(db, T.gun, kesim, GUN_SINIRI)
    if not gunler:
        return {"gun": 0, "ozet": 0, "silinen": 0}
    insan = T.bot.is_(False)
    satirlar = (
        await db.execute(
            select(
                T.sahip_tur, T.sahip_id, T.olay, T.gun,
                func.sum(case((insan, 1), else_=0)),
                func.count(distinct(case((insan, T.ip_ozeti), else_=None))),
                func.sum(case(((insan) & (T.kanal == "qr"), 1), else_=0)),
                func.sum(case((T.bot.is_(True), 1), else_=0)),
            ).where(T.gun.in_(gunler)).group_by(T.sahip_tur, T.sahip_id, T.olay, T.gun)
        )
    ).all()
    tablolar = {"kart": "kartvizitler", "yorum": "yorum_sayfalari"}
    ozet = 0
    for sahip_tur, tablo in tablolar.items():
        grup = [r for r in satirlar if r[0] == sahip_tur]
        canli = await _yasayanlar(db, tablo, (r[1] for r in grup))
        ozet += await _ozete_ekle(db, sahip_tur, [
            (int(sid), str(olay or "")[:16], str(g), int(s or 0), int(t or 0), int(q or 0), int(b or 0))
            for _, sid, olay, g, s, t, q, b in grup if int(sid) in canli
        ])
    silinen = (await db.execute(delete(T).where(T.gun.in_(gunler)))).rowcount
    await db.commit()
    return {"gun": len(gunler), "ozet": ozet, "silinen": int(silinen or 0)}


async def _eposta_tiklama(db: AsyncSession, kesim: str) -> Dict[str, int]:
    """Kampanya tıklamaları (`zaman` sütunu; gün yok): bağlantı sırası başına günlük özet."""
    from models.eposta_pazarlama import EpTiklamalar as T

    sinir_an = datetime.combine(date.fromisoformat(kesim), time.min, tzinfo=timezone.utc)
    satirlar = (
        await db.execute(
            select(T.id, T.kampanya_id, T.indeks, T.zaman).where(T.zaman < sinir_an).order_by(T.id).limit(20000)
        )
    ).all()
    if not satirlar:
        return {"ozet": 0, "silinen": 0}
    sayilar: Dict[Tuple[int, str, str], int] = defaultdict(int)
    for _id, kampanya, indeks, zaman in satirlar:
        if kampanya is None:
            continue  # dizi tıklaması: kampanya raporunda gösterilmiyor
        an = zaman if zaman.tzinfo else zaman.replace(tzinfo=timezone.utc)
        sayilar[(int(kampanya), str(indeks), an.astimezone(timezone.utc).date().isoformat())] += 1
    canli = await _yasayanlar(db, "ep_kampanyalar", (k[0] for k in sayilar))
    ozet = await _ozete_ekle(db, "eposta_tik", [
        (k, indeks, gun, n, 0, 0, 0) for (k, indeks, gun), n in sayilar.items() if k in canli
    ])
    idler = [int(r[0]) for r in satirlar]
    silinen = 0
    for i in range(0, len(idler), 1000):
        silinen += int((await db.execute(delete(T).where(T.id.in_(idler[i : i + 1000])))).rowcount or 0)
    await db.commit()
    return {"ozet": ozet, "silinen": silinen}


async def _yalniz_sil(db: AsyncSession, model: Any, kosul: Any) -> int:
    sonuc = await db.execute(delete(model).where(kosul))
    await db.commit()
    return int(sonuc.rowcount or 0)


async def _yetim_ozetler(db: AsyncSession) -> int:
    """Kaydı kalıcı silinmiş (çöp kutusunda da olmayan) nesnelerin özetleri."""
    tablolar = {"qr": "dinamik_qr", "kart": "kartvizitler", "yorum": "yorum_sayfalari", "eposta_tik": "ep_kampanyalar"}
    silinen = 0
    for kaynak, tablo in tablolar.items():
        idler = {int(r[0]) for r in (await db.execute(select(distinct(O.nesne_id)).where(O.kaynak == kaynak))).all()}
        if not idler:
            continue
        yetim = idler - await _yasayanlar(db, tablo, idler)
        if yetim:
            silinen += int((await db.execute(delete(O).where(O.kaynak == kaynak, O.nesne_id.in_(sorted(yetim))))).rowcount or 0)
    if silinen:
        await db.commit()
    return silinen


async def saklama_temizligi(db: AsyncSession, bugun: Optional[date] = None) -> Dict[str, Any]:
    """Zamanlı görev: 13 aydan eski ham olaylar (gerekirse önce günlük özete) + süresi geçmiş hız sayaçları."""
    from models.eposta_pazarlama import EpWebhookOlaylari
    from models.qr_menu import MenuOlaylari
    from models.randevu import RandevuOlaylari
    from utils.hiz_siniri import suresi_gecenleri_sil

    kesim_tarihi = kesim_gunu(bugun)
    kesim = kesim_tarihi.isoformat()
    sinir_an = datetime.combine(kesim_tarihi, time.min, tzinfo=timezone.utc)
    sonuc: Dict[str, Any] = {"kesim": kesim}
    adimlar = (
        ("qr", lambda: _qr(db, kesim)),
        ("kartvizit", lambda: _kartvizit(db, kesim)),
        ("eposta_tiklama", lambda: _eposta_tiklama(db, kesim)),
        ("menu", lambda: _yalniz_sil(db, MenuOlaylari, MenuOlaylari.gun < kesim)),
        ("randevu", lambda: _yalniz_sil(db, RandevuOlaylari, RandevuOlaylari.gun < kesim)),
        ("eposta_webhook", lambda: _yalniz_sil(db, EpWebhookOlaylari, EpWebhookOlaylari.created_at < sinir_an)),
        ("yetim_ozet", lambda: _yetim_ozetler(db)),
        ("hiz_sayaci", lambda: suresi_gecenleri_sil(db)),
    )
    for ad, adim in adimlar:
        try:
            sonuc[ad] = await adim()
        except Exception as h:  # noqa: BLE001 - bir kaynak diğerlerini durdurmasın
            logger.exception("Saklama temizliği adımı hata verdi: %s", ad)
            await db.rollback()
            sonuc[ad] = f"hata: {type(h).__name__}"
    # Panel özeti (zamanlı görev kartı yalnız düz sayıları gösteriyor).
    sonuc["silinen"] = sum(
        (v.get("silinen", 0) if isinstance(v, dict) else (v if isinstance(v, int) else 0))
        for k, v in sonuc.items() if k not in ("kesim", "hiz_sayaci", "yetim_ozet")
    )
    return sonuc


__all__ = ["SAKLAMA_AY", "SAKLAMA_GUN", "kesim_gunu", "toplamlar", "toplam_al", "saklama_temizligi"]
