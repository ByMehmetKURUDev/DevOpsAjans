"""Faz 4K — kartvizit ve yorum sayfasının veritabanına dokunan ortak işleri.

Kurallar `services/kartvizit.py`'de; burada iki router'ın (kart, yorum)
paylaştığı sorgular: slug uygunluğu ve değişimi (eski slug 30 gün), değişmez
kod, adres çözümleme (slug → eski slug → kod), görsel kaydet/oku/sil, olay
(analitik) yazımı ve özet sorguları.
"""

import logging
import secrets
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.database import db_manager
from models.kartvizit import (
    KartvizitEskiSluglar,
    KartvizitGorselleri,
    KartvizitOlaylari,
    Kartvizitler,
    YorumSayfalari,
)
from services import dosya_deposu
from services import kartvizit as k
from sqlalchemy import delete, desc, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MODELLER = {"kart": Kartvizitler, "yorum": YorumSayfalari}
Eski = KartvizitEskiSluglar
G = KartvizitGorselleri
T = KartvizitOlaylari


# ---------------------------------------------------------------------------
# Slug ve kod
# ---------------------------------------------------------------------------
async def slug_bos_mu(db: AsyncSession, sahip_tur: str, slug: str, haric_id: Optional[int] = None) -> bool:
    """Etkin slug'lar ve süresi dolmamış eski slug'lar (başka kayda ait) dolu sayılır."""
    model = MODELLER[sahip_tur]
    sorgu = select(model.id).where(model.slug == slug)
    if haric_id is not None:
        sorgu = sorgu.where(model.id != haric_id)
    if (await db.execute(sorgu.limit(1))).first() is not None:
        return False
    eski = select(Eski.id).where(Eski.sahip_tur == sahip_tur, Eski.slug == slug, Eski.bitis > k.simdi())
    if haric_id is not None:
        eski = eski.where(Eski.sahip_id != haric_id)
    return (await db.execute(eski.limit(1))).first() is None


async def benzersiz_kod(db: AsyncSession, sahip_tur: str) -> str:
    model = MODELLER[sahip_tur]
    for _ in range(20):
        kod = k.kod_uret()
        if (await db.execute(select(model.id).where(model.kod == kod).limit(1))).first() is None:
            return kod
    raise k.KartHatasi("kod_uretilemedi", None, durum=503)


async def slug_onerisi(db: AsyncSession, sahip_tur: str, kaynak: str) -> str:
    """Addan boş bir slug: `ad-soyad`, doluysa `ad-soyad-2`…; olmazsa rastgele ek."""
    taban = k.slug_oner(kaynak) or "kart"
    if taban in k.AYRILMIS_SLUGLAR:
        taban = f"{taban}-1"
    taban = taban[:44].strip("-")
    for i in range(0, 30):
        aday = taban if i == 0 else f"{taban}-{i + 1}"
        if k.SLUG_DESENI.match(aday) and await slug_bos_mu(db, sahip_tur, aday):
            return aday
    return f"{taban}-{secrets.token_hex(2)}"


async def slug_degistir(db: AsyncSession, sahip_tur: str, kayit: Any, yeni: str) -> None:
    """Slug değişince eskisi 30 gün yönlensin; kendi eski slug'ına dönülebilir."""
    eski = kayit.slug
    if yeni == eski:
        return
    await db.execute(delete(Eski).where(Eski.sahip_tur == sahip_tur, Eski.slug == yeni, Eski.sahip_id == kayit.id))
    await db.execute(delete(Eski).where(Eski.sahip_tur == sahip_tur, Eski.slug == eski))
    db.add(Eski(sahip_tur=sahip_tur, sahip_id=kayit.id, slug=eski, bitis=k.eski_slug_bitisi()))
    kayit.slug = yeni


async def eski_sluglari_sil(db: AsyncSession, sahip_tur: str, sahip_id: int) -> None:
    await db.execute(delete(Eski).where(Eski.sahip_tur == sahip_tur, Eski.sahip_id == sahip_id))


async def cozumle(db: AsyncSession, sahip_tur: str, deger: str) -> Tuple[Optional[Any], Optional[str], Optional[str]]:
    """Adres parçası → (kayıt, yönlendirilecek yeni slug, kanal).

    Sıra: değişmez kod (büyük harfli; kanal "qr") → etkin slug → süresi
    dolmamış eski slug (yalnız yönlendirme). Hiçbiri → (None, None, None).
    """
    model = MODELLER[sahip_tur]
    d = (deger or "").strip()
    if k.kod_mu(d):
        kayit = (await db.execute(select(model).where(model.kod == d))).scalars().first()
        if kayit is not None:
            return kayit, None, "qr"
    dl = d.lower()
    if not k.SLUG_DESENI.match(dl):
        return None, None, None
    kayit = (await db.execute(select(model).where(model.slug == dl))).scalars().first()
    if kayit is not None:
        return kayit, None, None
    satir = (
        await db.execute(
            select(Eski.sahip_id).where(Eski.sahip_tur == sahip_tur, Eski.slug == dl, Eski.bitis > k.simdi()).limit(1)
        )
    ).first()
    if satir is not None:
        hedef = (await db.execute(select(model.slug).where(model.id == satir[0]))).scalar()
        if hedef:
            return None, hedef, None
    return None, None, None


# ---------------------------------------------------------------------------
# Görseller
# ---------------------------------------------------------------------------
async def gorsel_kaydet(
    db: AsyncSession, *, hesap: Optional[str], sahip_tur: str, sahip_id: int, tur: str, bayt: bytes, sira: int = 0
) -> KartvizitGorselleri:
    webp, gen, yuk = k.gorsel_hazirla(bayt, tur)
    anahtar = secrets.token_urlsafe(18)
    yol = f"kartvizit/{sahip_tur}/{sahip_id}/{anahtar}.webp"
    try:
        depo = await dosya_deposu.yaz(db, yol, webp, "image/webp")
    except dosya_deposu.DepoHatasi as exc:
        raise k.KartHatasi("depo_hatasi", None, durum=503) from exc
    satir = G(
        hesap_email=hesap, sahip_tur=sahip_tur, sahip_id=sahip_id, tur=tur, anahtar=anahtar, depo=depo,
        depolama_anahtari=yol, boyut=len(webp), genislik=gen, yukseklik=yuk, sira=sira,
    )
    db.add(satir)
    await db.flush()
    return satir


async def gorsel_sil(db: AsyncSession, satir: KartvizitGorselleri) -> None:
    """Tek görsel (değiştirme / kaldırma): içerik hemen silinir, çöpe düşmez."""
    try:
        await dosya_deposu.sil(db, satir.depo, satir.depolama_anahtari)
    except Exception:  # noqa: BLE001 - içerik silinemese de satır gitsin
        logger.warning("Kartvizit görseli içeriği silinemedi: %s", satir.id)
    await db.delete(satir)


async def gorseller(db: AsyncSession, sahip_tur: str, sahip_id: int) -> List[KartvizitGorselleri]:
    return list(
        (
            await db.execute(
                select(G).where(G.sahip_tur == sahip_tur, G.sahip_id == sahip_id).order_by(G.tur, G.sira, G.id)
            )
        ).scalars().all()
    )


async def gorsel_bul(db: AsyncSession, gorsel_id: Optional[int]) -> Optional[KartvizitGorselleri]:
    if not gorsel_id:
        return None
    return (await db.execute(select(G).where(G.id == gorsel_id))).scalars().first()


async def gorsel_icerigi(db: AsyncSession, satir: KartvizitGorselleri) -> bytes:
    return await dosya_deposu.oku(db, satir.depo, satir.depolama_anahtari)


def gorsel_sozlugu(satir: Optional[KartvizitGorselleri]) -> Optional[Dict[str, Any]]:
    if satir is None:
        return None
    return {
        "id": satir.id,
        "tur": satir.tur,
        "url": k.gorsel_adresi(satir.anahtar),
        "genislik": satir.genislik,
        "yukseklik": satir.yukseklik,
        "boyut": satir.boyut,
        "sira": satir.sira,
    }


# ---------------------------------------------------------------------------
# Olaylar (analitik)
# ---------------------------------------------------------------------------
async def olay_yaz(veri: Dict[str, Any]) -> None:
    """Yanıt gönderildikten sonra tek INSERT. Hata yutulur (sayfayı asla bozmaz)."""
    try:
        if not db_manager.async_session_maker:
            return
        async with db_manager.async_session_maker() as oturum:
            await oturum.execute(insert(T).values(**veri))
            await oturum.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Kartvizit olayı kaydedilemedi")


async def olaylari_sil(db: AsyncSession, sahip_tur: str, sahip_id: int) -> None:
    await db.execute(delete(T).where(T.sahip_tur == sahip_tur, T.sahip_id == sahip_id))


async def donem_sayilari(
    db: AsyncSession, sahip_tur: str, idler: Iterable[int], gun: int = 30
) -> Dict[int, Dict[str, int]]:
    """Liste için: son `gun` gündeki olay sayıları (bot hariç), kayıt başına."""
    idler = list(idler)
    if not idler:
        return {}
    bas = (k.simdi().date() - timedelta(days=gun - 1)).isoformat()
    satirlar = (
        await db.execute(
            select(T.sahip_id, T.olay, func.count(T.id))
            .where(T.sahip_tur == sahip_tur, T.sahip_id.in_(idler), T.bot.is_(False), T.gun >= bas)
            .group_by(T.sahip_id, T.olay)
        )
    ).all()
    sonuc: Dict[int, Dict[str, int]] = {}
    for sid, olay, n in satirlar:
        sonuc.setdefault(int(sid), {})[olay] = int(n)
    return sonuc


async def analiz(db: AsyncSession, sahip_tur: str, sahip_id: int, gun: int, olaylar: Tuple[str, ...]) -> Dict[str, Any]:
    """Toplam / tekil / son `gun` günlük seri / tıklanan öğeler / cihaz dağılımı."""
    bugun = k.simdi().date()
    bas = (bugun - timedelta(days=gun - 1)).isoformat()
    sahip = (T.sahip_tur == sahip_tur, T.sahip_id == sahip_id)
    insan = sahip + (T.bot.is_(False),)
    donem = insan + (T.gun >= bas,)

    async def tek(sorgu) -> int:
        return int((await db.execute(sorgu)).scalar() or 0)

    toplam_ham = dict(
        (o, int(n))
        for o, n in (await db.execute(select(T.olay, func.count(T.id)).where(*insan).group_by(T.olay))).all()
    )
    donem_ham = dict(
        (o, int(n))
        for o, n in (await db.execute(select(T.olay, func.count(T.id)).where(*donem).group_by(T.olay))).all()
    )
    gorunum = (T.olay == "goruntulenme",)
    gunluk_olay: Dict[str, Dict[str, int]] = {}
    for g, o, n in (await db.execute(select(T.gun, T.olay, func.count(T.id)).where(*donem).group_by(T.gun, T.olay))).all():
        gunluk_olay.setdefault(g, {})[o] = int(n)
    gunluk_tekil = {
        g: int(n)
        for g, n in (
            await db.execute(
                select(T.gun, func.count(func.distinct(T.ip_ozeti))).where(*donem, *gorunum).group_by(T.gun)
            )
        ).all()
    }
    gunluk = []
    for i in range(gun):
        g = (bugun - timedelta(days=gun - 1 - i)).isoformat()
        satir = {"gun": g, "tekil": gunluk_tekil.get(g, 0)}
        for o in olaylar:
            satir[o] = gunluk_olay.get(g, {}).get(o, 0)
        gunluk.append(satir)
    hedefler = [
        {"hedef": h, "sayi": int(n)}
        for h, n in (
            await db.execute(
                select(T.hedef, func.count(T.id))
                .where(*donem, T.olay == "tik", T.hedef.is_not(None))
                .group_by(T.hedef)
                .order_by(desc(func.count(T.id)))
                .limit(50)
            )
        ).all()
    ]
    cihazlar = [
        {"anahtar": c, "sayi": int(n)}
        for c, n in (
            await db.execute(
                select(T.cihaz, func.count(T.id)).where(*donem, *gorunum).group_by(T.cihaz).order_by(desc(func.count(T.id)))
            )
        ).all()
    ]
    return {
        "toplam": {o: toplam_ham.get(o, 0) for o in olaylar},
        "tekil": await tek(select(func.count(func.distinct(T.ip_ozeti))).where(*insan, *gorunum)),
        "qr": await tek(select(func.count(T.id)).where(*insan, *gorunum, T.kanal == "qr")),
        "bot": await tek(select(func.count(T.id)).where(*sahip, T.bot.is_(True))),
        "donem": {
            "gun": gun,
            **{o: donem_ham.get(o, 0) for o in olaylar},
            "tekil": sum(x["tekil"] for x in gunluk),
        },
        "gunluk": gunluk,
        "hedefler": hedefler,
        "cihazlar": cihazlar,
    }
