"""Faz 6S — Saha servisi: kayıt işleri (iş emri, atama, durum, bildirim, tarama, kanca).

Saf kurallar `services/saha_servisi.py`'de; burası veritabanına yazan/okuyan katman.
Router (`routers/saha_servisi.py`), zamanlı görev (`services/zamanli.py`) ve randevu
kancası (olay altyapısının ek abonesi — `services/webhook.abone_ekle`) buradan çağırıyor.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from models.saha_servisi import (
    SahaAyarlari,
    SahaCihazlari,
    SahaDurumGecmisi,
    SahaIsAtamalari,
    SahaIsCihazlari,
    SahaIsEmirleri,
    SahaIsFotograflari,
    SahaLokasyonlari,
    SahaMalzemeKullanimi,
    SahaMusterileri,
    SahaSablonlari,
    SahaTeknisyenleri,
)
from services import saha_servisi as s
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

BAKIM_OLAYI = "saha_bakim_zamani"
ATAMA_OLAYI = "saha_is_atandi"
#: Katalog dışı (yalnız e-posta): servis müşterisi bir panel kullanıcısı değil.
MUSTERI_OLAYI = "saha_musteri"


# ---------------------------------------------------------------------------
# Ayarlar, sınırlar, tohum
# ---------------------------------------------------------------------------
async def ayarlar(db: AsyncSession, hesap: str) -> SahaAyarlari:
    a = (await db.execute(select(SahaAyarlari).where(SahaAyarlari.hesap_email == hesap))).scalars().first()
    if a is not None:
        return a
    a = SahaAyarlari(hesap_email=hesap, created_at=s.simdi())
    db.add(a)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        a = (await db.execute(select(SahaAyarlari).where(SahaAyarlari.hesap_email == hesap))).scalars().first()
    await db.refresh(a)
    return a


async def modul_ayari(db: AsyncSession, hesap: str, alan: str, varsayilan: int) -> int:
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, hesap, s.MODUL, alan)
    return int(deger) if isinstance(deger, int) and not isinstance(deger, bool) else varsayilan


async def tohumla(db: AsyncSession, a: SahaAyarlari) -> None:
    """Hazır şablonları hesaba BİR kez ekler (silinenler geri gelmez)."""
    if a.tohumlandi:
        return
    an = s.simdi()
    for anahtar in s.HAZIR_SABLONLAR:
        t = s.hazir_sablon(anahtar, a.varsayilan_dil or "tr")
        db.add(SahaSablonlari(hesap_email=a.hesap_email, ad=t["ad"], is_turu=t["is_turu"], maddeler=s.json_yaz(t["maddeler"]),
                              aktif=True, hazir=anahtar, created_at=an))
    a.tohumlandi = True
    await db.commit()


async def teknisyen_bul(db: AsyncSession, hesap: str, eposta: str) -> Optional[SahaTeknisyenleri]:
    return (await db.execute(select(SahaTeknisyenleri).where(
        SahaTeknisyenleri.hesap_email == hesap, SahaTeknisyenleri.eposta == eposta))).scalars().first()


async def yeni_no(db: AsyncSession, hesap: str) -> str:
    yil = s.tr_bugun().year
    kalip = f"IE-{yil}-"
    mevcut = (await db.execute(select(SahaIsEmirleri.no).where(SahaIsEmirleri.hesap_email == hesap,
                                                               SahaIsEmirleri.no.like(f"{kalip}%")))).scalars().all()
    en_buyuk = 0
    for no in mevcut:
        try:
            en_buyuk = max(en_buyuk, int(str(no).rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{kalip}{en_buyuk + 1:04d}"


async def bu_ay_is_emri_sayisi(db: AsyncSession, hesap: str) -> int:
    bugun = s.tr_bugun()
    from zoneinfo import ZoneInfo

    bas = datetime(bugun.year, bugun.month, 1, tzinfo=ZoneInfo("Europe/Istanbul")).astimezone(s.UTC)
    return int((await db.execute(select(func.count(SahaIsEmirleri.id)).where(
        SahaIsEmirleri.hesap_email == hesap, SahaIsEmirleri.created_at >= bas))).scalar() or 0)


# ---------------------------------------------------------------------------
# İlişkiler
# ---------------------------------------------------------------------------
async def atama_haritasi(db: AsyncSession, is_idler: Iterable[int]) -> Dict[int, List[int]]:
    idler = sorted(set(is_idler))
    sonuc: Dict[int, List[int]] = {i: [] for i in idler}
    if not idler:
        return sonuc
    for is_id, tid in (await db.execute(select(SahaIsAtamalari.is_emri_id, SahaIsAtamalari.teknisyen_id)
                                        .where(SahaIsAtamalari.is_emri_id.in_(idler))
                                        .order_by(SahaIsAtamalari.id))).all():
        sonuc.setdefault(is_id, []).append(tid)
    return sonuc


async def cihaz_haritasi(db: AsyncSession, is_idler: Iterable[int]) -> Dict[int, List[int]]:
    idler = sorted(set(is_idler))
    sonuc: Dict[int, List[int]] = {i: [] for i in idler}
    if not idler:
        return sonuc
    for is_id, cid in (await db.execute(select(SahaIsCihazlari.is_emri_id, SahaIsCihazlari.cihaz_id)
                                        .where(SahaIsCihazlari.is_emri_id.in_(idler)))).all():
        sonuc.setdefault(is_id, []).append(cid)
    return sonuc


async def atanan_teknisyenler(db: AsyncSession, is_id: int) -> List[SahaTeknisyenleri]:
    return list((await db.execute(select(SahaTeknisyenleri).join(
        SahaIsAtamalari, SahaIsAtamalari.teknisyen_id == SahaTeknisyenleri.id).where(
        SahaIsAtamalari.is_emri_id == is_id).order_by(SahaIsAtamalari.id))).scalars().all())


async def foto_maddeleri(db: AsyncSession, is_id: int) -> List[str]:
    return [m for m in (await db.execute(select(SahaIsFotograflari.madde_id).where(
        SahaIsFotograflari.is_emri_id == is_id, SahaIsFotograflari.madde_id.isnot(None)))).scalars().all() if m]


def plan_bitisi(ie: SahaIsEmirleri) -> Optional[datetime]:
    if ie.plan_bas is None:
        return None
    return s.utc(ie.plan_bit) if ie.plan_bit else s.utc(ie.plan_bas) + timedelta(minutes=int(ie.tahmini_dk or 60))


async def cakismalar(db: AsyncSession, hesap: str, teknisyen_idler: Sequence[int], bas: Optional[datetime],
                     bit: Optional[datetime], haric: Optional[int] = None) -> List[Dict[str, Any]]:
    """Aynı teknisyenin zaman aralığı örtüşen açık işleri (uyarı; atamayı engellemez)."""
    if not teknisyen_idler or bas is None or bit is None:
        return []
    sorgu = (
        select(SahaIsEmirleri, SahaIsAtamalari.teknisyen_id)
        .join(SahaIsAtamalari, SahaIsAtamalari.is_emri_id == SahaIsEmirleri.id)
        .where(SahaIsEmirleri.hesap_email == hesap, SahaIsAtamalari.teknisyen_id.in_(list(teknisyen_idler)),
               SahaIsEmirleri.durum.in_(("planlandi", "yolda", "iste", "yeni", "ertelendi")),
               SahaIsEmirleri.plan_bas.isnot(None), SahaIsEmirleri.plan_bas < bit)
    )
    if haric is not None:
        sorgu = sorgu.where(SahaIsEmirleri.id != haric)
    sonuc = []
    for ie, tid in (await db.execute(sorgu)).all():
        ie_bit = plan_bitisi(ie)
        if ie_bit is not None and ie_bit > bas:
            sonuc.append({"is_emri_id": ie.id, "no": ie.no, "baslik": ie.baslik, "teknisyen_id": tid,
                          "plan_bas": s.iso(ie.plan_bas), "plan_bit": s.iso(ie_bit)})
    return sonuc


# ---------------------------------------------------------------------------
# İş emri oluştur / güncelle
# ---------------------------------------------------------------------------
async def _musteri(db: AsyncSession, hesap: str, mid: Any) -> SahaMusterileri:
    kimlik = s.tam_sayi(mid, "musteri_id", 1, 2_000_000_000)
    m = (await db.execute(select(SahaMusterileri).where(SahaMusterileri.id == kimlik, SahaMusterileri.hesap_email == hesap))).scalars().first()
    if m is None or m.anonim:
        raise s.SahaHatasi("musteri_yok", "musteri_id", durum=404)
    return m


async def _lokasyon(db: AsyncSession, musteri: SahaMusterileri, lid: Any) -> Optional[SahaLokasyonlari]:
    if lid in (None, ""):
        return None
    kimlik = s.tam_sayi(lid, "lokasyon_id", 1, 2_000_000_000)
    l = (await db.execute(select(SahaLokasyonlari).where(SahaLokasyonlari.id == kimlik,
                                                         SahaLokasyonlari.musteri_id == musteri.id))).scalars().first()
    if l is None:
        raise s.SahaHatasi("lokasyon_yok", "lokasyon_id", durum=404)
    return l


async def _cihaz_idleri(db: AsyncSession, musteri: SahaMusterileri, ham: Any) -> List[int]:
    if ham in (None, ""):
        return []
    if not isinstance(ham, list) or len(ham) > 50:
        raise s.SahaHatasi("liste_gecersiz", "cihazlar")
    idler = sorted({s.tam_sayi(x, "cihazlar", 1, 2_000_000_000) for x in ham})
    if not idler:
        return []
    bulunan = set((await db.execute(select(SahaCihazlari.id).where(SahaCihazlari.id.in_(idler),
                                                                   SahaCihazlari.musteri_id == musteri.id))).scalars().all())
    if bulunan != set(idler):
        raise s.SahaHatasi("cihaz_yok", "cihazlar", durum=404)
    return idler


async def _teknisyen_idleri(db: AsyncSession, hesap: str, ham: Any) -> List[int]:
    if ham in (None, ""):
        return []
    if not isinstance(ham, list) or len(ham) > 10:
        raise s.SahaHatasi("liste_gecersiz", "teknisyenler")
    idler = []
    for x in ham:
        t = s.tam_sayi(x, "teknisyenler", 1, 2_000_000_000)
        if t not in idler:
            idler.append(t)
    if not idler:
        return []
    bulunan = set((await db.execute(select(SahaTeknisyenleri.id).where(
        SahaTeknisyenleri.id.in_(idler), SahaTeknisyenleri.hesap_email == hesap, SahaTeknisyenleri.aktif.is_(True)))).scalars().all())
    if bulunan != set(idler):
        raise s.SahaHatasi("teknisyen_yok", "teknisyenler", durum=404)
    return idler


async def _sablon(db: AsyncSession, hesap: str, sid: Any, tur: str, varsayilan: bool) -> Optional[SahaSablonlari]:
    if sid not in (None, ""):
        kimlik = s.tam_sayi(sid, "sablon_id", 1, 2_000_000_000)
        t = (await db.execute(select(SahaSablonlari).where(SahaSablonlari.id == kimlik, SahaSablonlari.hesap_email == hesap))).scalars().first()
        if t is None:
            raise s.SahaHatasi("sablon_yok", "sablon_id", durum=404)
        return t
    if not varsayilan:
        return None
    return (await db.execute(select(SahaSablonlari).where(SahaSablonlari.hesap_email == hesap, SahaSablonlari.is_turu == tur,
                                                          SahaSablonlari.aktif.is_(True)).order_by(SahaSablonlari.id))).scalars().first()


def _plan(g: Dict[str, Any], ie: Optional[SahaIsEmirleri]) -> Tuple[Optional[datetime], Optional[datetime], int]:
    bas = s.an_duzelt(g.get("plan_bas"), "plan_bas") if "plan_bas" in g else (s.utc(ie.plan_bas) if ie else None)
    tahmini = s.tam_sayi(g.get("tahmini_dk"), "tahmini_dk", 5, 24 * 60) if g.get("tahmini_dk") not in (None, "") else (
        int(ie.tahmini_dk) if ie else 60)
    if "plan_bit" in g:
        bit = s.an_duzelt(g.get("plan_bit"), "plan_bit")
    elif "plan_bas" in g or "tahmini_dk" in g:
        bit = bas + timedelta(minutes=tahmini) if bas else None
    else:
        bit = s.utc(ie.plan_bit) if ie else None
    if bas is None:
        bit = None
    elif bit is None:
        bit = bas + timedelta(minutes=tahmini)
    if bas and bit and bit <= bas:
        raise s.SahaHatasi("plan_gecersiz", "plan_bit")
    if bas and bit and bit - bas > timedelta(days=14):
        raise s.SahaHatasi("plan_gecersiz", "plan_bit")
    return bas, bit, tahmini


def _gecmis(db: AsyncSession, ie: SahaIsEmirleri, eski: Optional[str], yeni: str, kisi: str, neden: Optional[str] = None,
            konum: bool = False) -> None:
    db.add(SahaDurumGecmisi(is_emri_id=ie.id, eski=eski, yeni=yeni, kisi=kisi, neden=neden, konum_alindi=konum, zaman=s.simdi()))


def _otomatik_durum(ie: SahaIsEmirleri, teknisyen_sayisi: int) -> Optional[Tuple[str, str]]:
    """Plan + teknisyen tamamlanınca yeni → planlandi; biri kalkınca planlandi → yeni."""
    if ie.durum in ("yeni", "ertelendi") and ie.plan_bas is not None and teknisyen_sayisi > 0:
        eski = ie.durum
        ie.durum = "planlandi"
        ie.planlandi_at = s.simdi()
        return eski, "planlandi"
    if ie.durum == "planlandi" and (ie.plan_bas is None or teknisyen_sayisi == 0):
        ie.durum = "yeni"
        return "planlandi", "yeni"
    return None


async def _atamalari_yaz(db: AsyncSession, ie: SahaIsEmirleri, idler: List[int]) -> List[int]:
    """Atamaları `idler`e eşitler; YENİ eklenen teknisyenleri döndürür."""
    mevcut = (await db.execute(select(SahaIsAtamalari).where(SahaIsAtamalari.is_emri_id == ie.id))).scalars().all()
    eski = {a.teknisyen_id: a for a in mevcut}
    for tid, a in eski.items():
        if tid not in idler:
            await db.delete(a)
    yeniler = [tid for tid in idler if tid not in eski]
    for tid in yeniler:
        db.add(SahaIsAtamalari(is_emri_id=ie.id, teknisyen_id=tid, hesap_email=ie.hesap_email, created_at=s.simdi()))
    return yeniler


async def _cihazlari_yaz(db: AsyncSession, ie: SahaIsEmirleri, idler: List[int]) -> None:
    await db.execute(delete(SahaIsCihazlari).where(SahaIsCihazlari.is_emri_id == ie.id, SahaIsCihazlari.cihaz_id.notin_(idler or [0])))
    var = set((await db.execute(select(SahaIsCihazlari.cihaz_id).where(SahaIsCihazlari.is_emri_id == ie.id))).scalars().all())
    for cid in idler:
        if cid not in var:
            db.add(SahaIsCihazlari(is_emri_id=ie.id, cihaz_id=cid))


@dataclass
class Sonuc:
    ie: SahaIsEmirleri
    yeni_atananlar: List[int]
    cakismalar: List[Dict[str, Any]]
    musteri_bildirimi: Optional[str] = None


async def is_emri_olustur(db: AsyncSession, hesap: str, g: Dict[str, Any], kisi: str, *, sinir_denetle: bool = True,
                          randevu_id: Optional[int] = None) -> Sonuc:
    if sinir_denetle:
        sinir = await modul_ayari(db, hesap, "aylik_is_emri_siniri", s.VARSAYILAN_AYLIK_SINIR)
        if await bu_ay_is_emri_sayisi(db, hesap) >= sinir:
            raise s.SahaHatasi("aylik_sinir", durum=409, sinir=sinir)
    musteri = await _musteri(db, hesap, g.get("musteri_id"))
    lokasyon = await _lokasyon(db, musteri, g.get("lokasyon_id"))
    cihazlar = await _cihaz_idleri(db, musteri, g.get("cihazlar"))
    tur = s.secim(g.get("tur") or "ariza", "tur", s.IS_TURLERI)
    oncelik = s.secim(g.get("oncelik") or "normal", "oncelik", s.ONCELIKLER)
    baslik = s.metin(g.get("baslik"), "baslik", 160, zorunlu=True)
    aciklama = s.bos_ya_da(g.get("aciklama"), "aciklama", 4000, cok_satir=True)
    teknisyenler = await _teknisyen_idleri(db, hesap, g.get("teknisyenler"))
    bas, bit, tahmini = _plan(g, None)
    sablon = await _sablon(db, hesap, g.get("sablon_id"), tur, varsayilan="sablon_id" not in g)
    iscilik = s.kurus(g.get("iscilik_ucreti"), "iscilik_ucreti")
    an = s.simdi()
    ie = SahaIsEmirleri(
        hesap_email=hesap, no=await yeni_no(db, hesap), uid=uuid.uuid4().hex, tur=tur, oncelik=oncelik, durum="yeni",
        baslik=baslik, aciklama=aciklama, musteri_id=musteri.id, lokasyon_id=lokasyon.id if lokasyon else None,
        plan_bas=bas, plan_bit=bit, tahmini_dk=tahmini, sablon_id=sablon.id if sablon else None,
        kontrol_listesi=s.json_yaz(s.json_yukle(sablon.maddeler, []) if sablon else []), kontrol_yanitlari="{}",
        iscilik_ucreti=iscilik, randevu_id=randevu_id, olusturan=kisi, created_at=an, updated_at=an,
    )
    for deneme in range(3):
        db.add(ie)
        try:
            await db.flush()
            break
        except IntegrityError:
            await db.rollback()
            if randevu_id is not None:
                raise s.SahaHatasi("zaten_var", durum=409)
            ie = SahaIsEmirleri(**{c.name: getattr(ie, c.name) for c in SahaIsEmirleri.__table__.columns if c.name != "id"})
            ie.no = await yeni_no(db, hesap)
            if deneme == 2:
                raise s.SahaHatasi("tekrar_deneyin", durum=409)
    _gecmis(db, ie, None, "yeni", kisi)
    yeniler = await _atamalari_yaz(db, ie, teknisyenler)
    await _cihazlari_yaz(db, ie, cihazlar)
    oto = _otomatik_durum(ie, len(teknisyenler))
    if oto:
        _gecmis(db, ie, oto[0], oto[1], kisi)
    musteri.son_is_at = an
    cak = await cakismalar(db, hesap, teknisyenler, bas, bit, haric=ie.id)
    await db.commit()
    await db.refresh(ie)
    return Sonuc(ie, yeniler, cak, "planlandi" if ie.durum == "planlandi" else None)


async def is_emri_guncelle(db: AsyncSession, ie: SahaIsEmirleri, g: Dict[str, Any], kisi: str) -> Sonuc:
    if ie.durum in s.KAPALI_DURUMLAR and set(g) - {"iscilik_ucreti", "aciklama"}:
        raise s.SahaHatasi("is_kapali", durum=409)
    musteri = await _musteri(db, ie.hesap_email, g.get("musteri_id", ie.musteri_id))
    if "musteri_id" in g and musteri.id != ie.musteri_id:
        if ie.durum not in ("yeni", "planlandi", "ertelendi"):
            raise s.SahaHatasi("is_basladi", "musteri_id", durum=409)
        ie.musteri_id = musteri.id
        ie.lokasyon_id = None
    if "lokasyon_id" in g or "musteri_id" in g:
        l = await _lokasyon(db, musteri, g.get("lokasyon_id"))
        ie.lokasyon_id = l.id if l else None
    if "cihazlar" in g:
        await _cihazlari_yaz(db, ie, await _cihaz_idleri(db, musteri, g.get("cihazlar")))
    if "tur" in g:
        ie.tur = s.secim(g.get("tur"), "tur", s.IS_TURLERI)
    if "oncelik" in g:
        ie.oncelik = s.secim(g.get("oncelik"), "oncelik", s.ONCELIKLER)
    if "baslik" in g:
        ie.baslik = s.metin(g.get("baslik"), "baslik", 160, zorunlu=True)
    if "aciklama" in g:
        ie.aciklama = s.bos_ya_da(g.get("aciklama"), "aciklama", 4000, cok_satir=True)
    if "iscilik_ucreti" in g:
        ie.iscilik_ucreti = s.kurus(g.get("iscilik_ucreti"), "iscilik_ucreti")
    if "sablon_id" in g:
        if ie.durum not in ("yeni", "planlandi", "ertelendi", "yolda"):
            raise s.SahaHatasi("is_basladi", "sablon_id", durum=409)
        t = await _sablon(db, ie.hesap_email, g.get("sablon_id"), ie.tur, varsayilan=False)
        ie.sablon_id = t.id if t else None
        ie.kontrol_listesi = s.json_yaz(s.json_yukle(t.maddeler, []) if t else [])
        ie.kontrol_yanitlari = "{}"
    eski_plan = s.utc(ie.plan_bas)
    if {"plan_bas", "plan_bit", "tahmini_dk"} & set(g):
        if ie.durum in ("iste",):
            raise s.SahaHatasi("is_basladi", "plan_bas", durum=409)
        bas, bit, tahmini = _plan(g, ie)
        ie.plan_bas, ie.plan_bit, ie.tahmini_dk = bas, bit, tahmini
    yeniler: List[int] = []
    if "teknisyenler" in g:
        if ie.durum in ("iste",) and not g.get("teknisyenler"):
            raise s.SahaHatasi("teknisyen_gerekli", "teknisyenler", durum=409)
        yeniler = await _atamalari_yaz(db, ie, await _teknisyen_idleri(db, ie.hesap_email, g.get("teknisyenler")))
    await db.flush()
    atanan = (await atama_haritasi(db, [ie.id]))[ie.id]
    oto = _otomatik_durum(ie, len(atanan))
    if oto:
        _gecmis(db, ie, oto[0], oto[1], kisi)
    ie.updated_at = s.simdi()
    cak = await cakismalar(db, ie.hesap_email, atanan, s.utc(ie.plan_bas), plan_bitisi(ie), haric=ie.id)
    bildirim = None
    if ie.durum == "planlandi" and (oto and oto[1] == "planlandi" or (eski_plan != s.utc(ie.plan_bas))):
        bildirim = "planlandi"
    await db.commit()
    await db.refresh(ie)
    return Sonuc(ie, yeniler, cak, bildirim)


# ---------------------------------------------------------------------------
# Durum geçişi
# ---------------------------------------------------------------------------
async def durum_degistir(db: AsyncSession, ie: SahaIsEmirleri, yeni: str, *, kisi: str, yonetim: bool,
                         teknisyen: Optional[SahaTeknisyenleri], konum_ham: Any = None, neden: Any = None) -> Dict[str, Any]:
    """Geçişi doğrular ve uygular. Konum YALNIZ başla/bitir'de, atanmış teknisyenin geçerli
    rızası varken yazılır; aksi hâlde gelen konum yok sayılır (hiçbir yerde saklanmaz)."""
    eski = ie.durum
    atanan = (await atama_haritasi(db, [ie.id]))[ie.id]
    atanmis_teknisyen = teknisyen is not None and teknisyen.id in atanan and bool(teknisyen.aktif)
    s.gecis_denetle(eski, yeni, yonetim=yonetim, teknisyen=atanmis_teknisyen)
    neden_ = s.bos_ya_da(neden, "neden", 500, cok_satir=True)
    if yeni == "planlandi" and (ie.plan_bas is None or not atanan):
        raise s.SahaHatasi("plan_gerekli", "durum", durum=409)
    if yeni in ("yolda", "iste") and not atanan:
        raise s.SahaHatasi("teknisyen_gerekli", "durum", durum=409)
    a = await ayarlar(db, ie.hesap_email)
    if yeni == "tamamlandi":
        maddeler = s.json_yukle(ie.kontrol_listesi, []) or []
        eksik = s.eksik_zorunlular(maddeler, s.json_yukle(ie.kontrol_yanitlari, {}) or {}, await foto_maddeleri(db, ie.id))
        if eksik:
            raise s.SahaHatasi("zorunlu_madde_eksik", "kontrol", durum=409, maddeler=eksik)
        if a.imza_zorunlu and not ie.imza_anahtari:
            raise s.SahaHatasi("imza_gerekli", "imza", durum=409)
    # Konum: bozuk gövde her durumda 400 (sessizce yutulmasın), ama kayıt yalnız kurala uyarsa.
    konum = s.konum_duzelt(konum_ham)
    an = s.simdi()
    konum_alindi = False
    an_adi = s.KONUMLU_DURUMLAR.get(yeni)
    if konum and an_adi and atanmis_teknisyen and s.riza_gecerli_mi(
            teknisyen.konum_rizasi_at, teknisyen.konum_rizasi_surumu, teknisyen.konum_rizasi_geri_at):
        enlem, boylam, dogruluk = konum
        if an_adi == "basla":
            ie.basla_enlem, ie.basla_boylam, ie.basla_dogruluk = enlem, boylam, dogruluk
        else:
            ie.bitir_enlem, ie.bitir_boylam, ie.bitir_dogruluk = enlem, boylam, dogruluk
        konum_alindi = True
    ie.durum = yeni
    if yeni == "planlandi":
        ie.planlandi_at = an
    elif yeni == "yolda":
        ie.yolda_at = an
    elif yeni == "iste":
        ie.basla_at = ie.basla_at or an
    elif yeni == "tamamlandi":
        ie.bitir_at = an
    elif yeni == "iptal":
        ie.iptal_at = an
    elif yeni == "ertelendi":
        ie.ertele_at = an
        ie.ertele_sayisi = int(ie.ertele_sayisi or 0) + 1
    ie.updated_at = an
    _gecmis(db, ie, eski, yeni, kisi, neden_, konum_alindi)
    if yeni == "tamamlandi":
        await _bakim_tarihlerini_isle(db, ie)
        m = (await db.execute(select(SahaMusterileri).where(SahaMusterileri.id == ie.musteri_id))).scalars().first()
        if m is not None:
            m.son_is_at = an
    await db.commit()
    await db.refresh(ie)
    bildirim = {"planlandi": "planlandi", "yolda": "yolda", "tamamlandi": "tamamlandi"}.get(yeni)
    return {"konum_alindi": konum_alindi, "musteri_bildirimi": bildirim}


async def _bakim_tarihlerini_isle(db: AsyncSession, ie: SahaIsEmirleri) -> None:
    """Bakım/kurulum işi bitince işin cihazlarının son bakım tarihi bugün; bildirim izi sıfırlanır."""
    if ie.tur not in ("bakim", "kurulum"):
        return
    idler = (await cihaz_haritasi(db, [ie.id]))[ie.id]
    if not idler:
        return
    bugun = s.tr_bugun()
    for c in (await db.execute(select(SahaCihazlari).where(SahaCihazlari.id.in_(idler)))).scalars().all():
        if ie.tur == "bakim" or c.son_bakim is None:
            c.son_bakim = bugun
        if ie.tur == "kurulum" and c.kurulum_tarihi is None:
            c.kurulum_tarihi = bugun
        c.bakim_bildirim_tarihi = None


# ---------------------------------------------------------------------------
# Malzeme kullanımı (basit stok düşümü)
# ---------------------------------------------------------------------------
async def malzeme_ekle(db: AsyncSession, ie: SahaIsEmirleri, g: Dict[str, Any], kisi: str) -> SahaMalzemeKullanimi:
    from models.saha_servisi import SahaMalzemeleri

    if ie.durum in s.KAPALI_DURUMLAR:
        raise s.SahaHatasi("is_kapali", durum=409)
    miktar = s.ondalik(g.get("miktar"), "miktar", 0.001, 100_000)
    if g.get("malzeme_id") not in (None, ""):
        kimlik = s.tam_sayi(g.get("malzeme_id"), "malzeme_id", 1, 2_000_000_000)
        m = (await db.execute(select(SahaMalzemeleri).where(SahaMalzemeleri.id == kimlik,
                                                            SahaMalzemeleri.hesap_email == ie.hesap_email))).scalars().first()
        if m is None:
            raise s.SahaHatasi("malzeme_yok", "malzeme_id", durum=404)
        satir = SahaMalzemeKullanimi(is_emri_id=ie.id, hesap_email=ie.hesap_email, malzeme_id=m.id, ad=m.ad, birim=m.birim,
                                     miktar=miktar, birim_fiyat=int(m.birim_fiyat or 0), ekleyen=kisi, created_at=s.simdi())
        if m.stok is not None:
            # Tek koşullu UPDATE: eşzamanlı iki kullanım da doğru düşsün (stok eksiye düşebilir: sahada kullanıldıysa
            # gerçek bu; kritik eşik uyarısı panelde).
            await db.execute(update(SahaMalzemeleri).where(SahaMalzemeleri.id == m.id)
                             .values(stok=SahaMalzemeleri.stok - miktar).execution_options(synchronize_session=False))
            satir.stoktan_dusuldu = True
    else:
        satir = SahaMalzemeKullanimi(
            is_emri_id=ie.id, hesap_email=ie.hesap_email, malzeme_id=None,
            ad=s.metin(g.get("ad"), "ad", 160, zorunlu=True), birim=s.secim(g.get("birim") or "adet", "birim", s.BIRIMLER),
            miktar=miktar, birim_fiyat=s.kurus(g.get("birim_fiyat"), "birim_fiyat"), ekleyen=kisi, created_at=s.simdi())
    db.add(satir)
    await db.commit()
    await db.refresh(satir)
    return satir


async def malzeme_sil(db: AsyncSession, ie: SahaIsEmirleri, kullanim_id: int) -> None:
    from models.saha_servisi import SahaMalzemeleri

    if ie.durum in s.KAPALI_DURUMLAR:
        raise s.SahaHatasi("is_kapali", durum=409)
    k = (await db.execute(select(SahaMalzemeKullanimi).where(SahaMalzemeKullanimi.id == kullanim_id,
                                                             SahaMalzemeKullanimi.is_emri_id == ie.id))).scalars().first()
    if k is None:
        raise s.SahaHatasi("bulunamadi", durum=404)
    if k.stoktan_dusuldu and k.malzeme_id:
        await db.execute(update(SahaMalzemeleri).where(SahaMalzemeleri.id == k.malzeme_id, SahaMalzemeleri.stok.isnot(None))
                         .values(stok=SahaMalzemeleri.stok + k.miktar).execution_options(synchronize_session=False))
    await db.delete(k)
    await db.commit()


# ---------------------------------------------------------------------------
# Görsel deposu
# ---------------------------------------------------------------------------
async def gorsel_yaz(db: AsyncSession, anahtar: str, veri: bytes, tur: str) -> str:
    from services import dosya_deposu

    return await dosya_deposu.yaz(db, anahtar, veri, tur)


async def gorsel_sil(db: AsyncSession, depo: str, *anahtarlar: str) -> None:
    from services import dosya_deposu

    for a in anahtarlar:
        if not a:
            continue
        try:
            await dosya_deposu.sil(db, depo or "veritabani", a)
        except Exception:  # noqa: BLE001 - içerik silinemese de kayıt gitsin
            logger.warning("Saha görseli silinemedi: %s", a)


async def gorsel_oku(db: AsyncSession, depo: str, anahtar: str) -> Optional[bytes]:
    from services import dosya_deposu

    try:
        return await dosya_deposu.oku(db, depo or "veritabani", anahtar)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Bildirimler (arka plan; hatalar yutulur)
# ---------------------------------------------------------------------------
def panel_baglantisi(hesap: str, alici: str, is_id: Optional[int] = None) -> str:
    from urllib.parse import quote

    bag = "/client?sekme=sahaServisi"
    if is_id:
        bag += f"&is={int(is_id)}"
    if alici and alici != hesap:
        bag += f"&hesap={quote(hesap)}"
    return bag


async def _oturumla(isle) -> None:
    from core.database import db_manager

    if not db_manager.async_session_maker:
        return
    try:
        async with db_manager.async_session_maker() as db:
            await isle(db)
    except Exception:  # noqa: BLE001
        logger.exception("Saha servisi arka plan işi çalışamadı")


async def teknisyenlere_bildir(is_id: int, teknisyen_idler: Sequence[int]) -> None:
    """Yeni atanan teknisyenlere "yeni iş" bildirimi (panel + e-posta + Web Push; kişisel tercihe tabi)."""
    if not teknisyen_idler:
        return

    async def isle(db: AsyncSession) -> None:
        from services.notify import dispatch, render

        ie = (await db.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.id == is_id))).scalars().first()
        if ie is None:
            return
        adres = await adres_metni(db, ie)
        zaman = s.yerel_zaman(ie.plan_bas) if ie.plan_bas else "—"
        for t in (await db.execute(select(SahaTeknisyenleri).where(SahaTeknisyenleri.id.in_(list(teknisyen_idler))))).scalars().all():
            baslik, govde = await render(db, ATAMA_OLAYI, f"Yeni iş: {ie.no} — {ie.baslik}",
                                         f"Zaman: {zaman}\nAdres: {adres or '—'}\nÖncelik: {ie.oncelik}",
                                         {"no": ie.no, "baslik": ie.baslik, "zaman": zaman, "adres": adres or ""})
            await dispatch(db, event_type=ATAMA_OLAYI, title=baslik, body=govde,
                           recipients=[{"email": t.eposta, "role": "client", "phone": t.telefon or ""}],
                           link=panel_baglantisi(ie.hesap_email, t.eposta, ie.id), ref_type="saha_is_emirleri", ref_id=ie.id)

    await _oturumla(isle)


async def adres_metni(db: AsyncSession, ie: SahaIsEmirleri) -> Optional[str]:
    if not ie.lokasyon_id:
        return None
    l = (await db.execute(select(SahaLokasyonlari).where(SahaLokasyonlari.id == ie.lokasyon_id))).scalars().first()
    if l is None:
        return None
    parcalar = [l.adres, " ".join(x for x in (l.posta_kodu, l.ilce) if x), l.il]
    return ", ".join(p for p in parcalar if p) or None


async def musteriye_bildir(is_id: int, tur: str) -> None:
    """Servis müşterisine e-posta (planlandı / yolda / tamamlandı). Ayar kapalıysa, müşterinin
    e-postası yoksa ya da aynı bildirim zaten gittiyse gönderilmez. Panel içi kopya tutulmaz,
    bağlantı (yetki belgesi) kalıcı kayıtta maskelenir."""

    async def isle(db: AsyncSession) -> None:
        from services.notify import dispatch

        ie = (await db.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.id == is_id))).scalars().first()
        if ie is None or ie.anonim:
            return
        a = await ayarlar(db, ie.hesap_email)
        if not getattr(a, f"bildirim_{tur}", False):
            return
        m = (await db.execute(select(SahaMusterileri).where(SahaMusterileri.id == ie.musteri_id))).scalars().first()
        if m is None or m.anonim or not m.eposta:
            return
        gidenler = s.json_yukle(ie.musteri_bildirimleri, {}) or {}
        imza = s.iso(ie.plan_bas) if tur == "planlandi" else "1"
        if gidenler.get(tur) == imza:
            return
        firma = a.firma_adi or ie.hesap_email
        teknik = [t.ad for t in (await db.execute(select(SahaTeknisyenleri).join(
            SahaIsAtamalari, SahaIsAtamalari.teknisyen_id == SahaTeknisyenleri.id).where(SahaIsAtamalari.is_emri_id == ie.id))).scalars().all()]
        jeton = s.musteri_jetonu(ie.id, ie.uid)
        adres_ = s.musteri_adresi(jeton)
        konu, govde = s.eposta_metni(
            tur, m.dil or a.varsayilan_dil or "tr", firma=firma, ad=m.ad, no=ie.no, is_turu=ie.tur,
            zaman=s.yerel_zaman(ie.plan_bas, m.dil or "tr") if ie.plan_bas else None, adres=await adres_metni(db, ie),
            teknisyen=", ".join(s.ilk_ad(x) for x in teknik) or None, baglanti=adres_)
        ek = {"reply_to": a.eposta} if a.eposta else None
        satirlar = await dispatch(db, event_type=MUSTERI_OLAYI, title=konu, body=govde,
                                  recipients=[{"email": m.eposta, "role": "client"}], link=None,
                                  ref_type="saha_is_emirleri", ref_id=ie.id, eposta_ek=ek)
        degisti = False
        for satir in list(satirlar):
            if getattr(satir, "channel", None) == "inapp":
                await db.delete(satir)
                degisti = True
            else:
                for alan in ("body", "title"):
                    deger = getattr(satir, alan, None)
                    if deger and jeton in deger:
                        setattr(satir, alan, deger.replace(adres_, "…").replace(jeton, "…"))
                        degisti = True
        gidenler[tur] = imza
        ie.musteri_bildirimleri = s.json_yaz(gidenler)
        await db.commit()

    await _oturumla(isle)


# ---------------------------------------------------------------------------
# Zamanlı: bakım taraması, konum indirgeme, saklama temizliği
# ---------------------------------------------------------------------------
async def bakim_taramasi(db: AsyncSession, bugun: Optional[date] = None) -> Dict[str, Any]:
    """Bakım vadesi `bakim_on_gun` içinde (ya da geçmiş) cihazlar: hesap başına TEK özet bildirim,
    cihaz başına vade başına bir kez (`bakim_bildirim_tarihi`)."""
    from services.moduller import modul_acik_mi
    from services.notify import dispatch, render

    bugun = bugun or s.tr_bugun()
    cihazlar = (await db.execute(select(SahaCihazlari).where(
        SahaCihazlari.aktif.is_(True), SahaCihazlari.bakim_periyot_ay.isnot(None)).order_by(SahaCihazlari.hesap_email, SahaCihazlari.id))).scalars().all()
    hesaplara: Dict[str, List[Tuple[SahaCihazlari, date]]] = {}
    ayar_onbellek: Dict[str, Optional[SahaAyarlari]] = {}
    acik_onbellek: Dict[str, bool] = {}
    for c in cihazlar:
        vade = s.bakim_vadesi(c.son_bakim, c.kurulum_tarihi, c.bakim_periyot_ay)
        if vade is None or c.bakim_bildirim_tarihi == vade:
            continue
        if c.hesap_email not in acik_onbellek:
            acik_onbellek[c.hesap_email] = await modul_acik_mi(db, c.hesap_email, s.MODUL)
            ayar_onbellek[c.hesap_email] = (await db.execute(select(SahaAyarlari).where(
                SahaAyarlari.hesap_email == c.hesap_email))).scalars().first()
        if not acik_onbellek[c.hesap_email]:
            continue
        on_gun = int(getattr(ayar_onbellek[c.hesap_email], "bakim_on_gun", 7) or 7)
        if vade <= bugun + timedelta(days=on_gun):
            hesaplara.setdefault(c.hesap_email, []).append((c, vade))
    gonderilen = 0
    for hesap, liste in hesaplara.items():
        musteri_adlari = dict((await db.execute(select(SahaMusterileri.id, SahaMusterileri.ad).where(
            SahaMusterileri.id.in_([c.musteri_id for c, _ in liste])))).all())
        satirlar = [f"• {c.tur} {c.marka or ''} {c.model or ''} — {musteri_adlari.get(c.musteri_id, '—')} — vade {v.isoformat()}"
                    .replace("  ", " ") for c, v in liste[:30]]
        if len(liste) > 30:
            satirlar.append(f"… +{len(liste) - 30}")
        baslik, govde = await render(db, BAKIM_OLAYI, f"Bakım zamanı gelen {len(liste)} cihaz", "\n".join(satirlar),
                                     {"sayi": len(liste)})
        for c, v in liste:
            c.bakim_bildirim_tarihi = v
        await db.commit()
        await dispatch(db, event_type=BAKIM_OLAYI, title=baslik, body=govde,
                       recipients=[{"email": hesap, "role": "client"}],
                       link="/client?sekme=sahaServisi&bolum=raporlar", ref_type="saha_cihazlari", ref_id=liste[0][0].id)
        gonderilen += 1
    return {"hesap": gonderilen, "cihaz": sum(len(v) for v in hesaplara.values())}


async def konum_indirge(db: AsyncSession, an: Optional[datetime] = None) -> int:
    """Ham koordinat 90 gün sonra silinir; iş emrinin adresi düzeyinde bilgi kalır."""
    an = an or s.simdi()
    esik = an - timedelta(days=s.KONUM_SAKLAMA_GUN)
    toplam = 0
    for an_alani, alanlar in (
        (SahaIsEmirleri.basla_at, {"basla_enlem": None, "basla_boylam": None, "basla_dogruluk": None}),
        (SahaIsEmirleri.bitir_at, {"bitir_enlem": None, "bitir_boylam": None, "bitir_dogruluk": None}),
    ):
        enlem = getattr(SahaIsEmirleri, next(iter(alanlar)))
        sonuc = await db.execute(update(SahaIsEmirleri).where(enlem.isnot(None), an_alani < esik)
                                 .values(**alanlar, konum_indirgendi_at=an).execution_options(synchronize_session=False))
        toplam += int(sonuc.rowcount or 0)
    await db.commit()
    return toplam


_son_istek_temizligi: Dict[str, Optional[float]] = {"an": None}


async def istekle_temizle(db: AsyncSession) -> None:
    """Uyuyan sunucu: konum indirgemesi listeler açılırken de (süreç başına saatte bir) çalışır."""
    son = _son_istek_temizligi["an"]
    if son is not None and time.monotonic() - son < 3600:
        return
    _son_istek_temizligi["an"] = time.monotonic()
    try:
        await konum_indirge(db)
    except Exception:  # noqa: BLE001
        logger.exception("Saha konum indirgemesi çalışamadı")
        await db.rollback()


async def is_emri_anonimlestir(db: AsyncSession, ie: SahaIsEmirleri) -> None:
    """İmza görseli, fotoğraflar, imzalayan adı ve yorum silinir; konum boşaltılır."""
    await gorsel_sil(db, ie.imza_depo, ie.imza_anahtari or "")
    for f in (await db.execute(select(SahaIsFotograflari).where(SahaIsFotograflari.is_emri_id == ie.id))).scalars().all():
        await gorsel_sil(db, f.depo, f.anahtar, f.kucuk_anahtar)
        await db.delete(f)
    ie.imza_anahtari = ie.imza_depo = ie.imza_ad = None
    ie.memnuniyet_yorum = None
    ie.basla_enlem = ie.basla_boylam = ie.basla_dogruluk = None
    ie.bitir_enlem = ie.bitir_boylam = ie.bitir_dogruluk = None
    ie.anonim = True


async def musteri_anonimlestir(db: AsyncSession, m: SahaMusterileri) -> None:
    m.ad = "—"
    m.firma = m.eposta = m.telefon = m.vergi_no = m.notlar = None
    m.anonim = True
    for l in (await db.execute(select(SahaLokasyonlari).where(SahaLokasyonlari.musteri_id == m.id))).scalars().all():
        l.adres = l.posta_kodu = l.notlar = None
    for ie in (await db.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.musteri_id == m.id,
                                                             SahaIsEmirleri.anonim.is_(False)))).scalars().all():
        await is_emri_anonimlestir(db, ie)


async def saklama_temizligi(db: AsyncSession, an: Optional[datetime] = None, sinir: int = 200) -> int:
    """Son işinden `saklama_ay` geçen (açık işi olmayan) servis müşterilerinin kişisel verisi silinir."""
    an = an or s.simdi()
    sayi = 0
    for a in (await db.execute(select(SahaAyarlari))).scalars().all():
        esik = an - timedelta(days=30 * int(a.saklama_ay or 60))
        adaylar = (await db.execute(select(SahaMusterileri).where(
            SahaMusterileri.hesap_email == a.hesap_email, SahaMusterileri.anonim.is_(False),
            func.coalesce(SahaMusterileri.son_is_at, SahaMusterileri.created_at) < esik).limit(sinir - sayi))).scalars().all()
        for m in adaylar:
            acik = (await db.execute(select(SahaIsEmirleri.id).where(SahaIsEmirleri.musteri_id == m.id,
                                                                     SahaIsEmirleri.durum.in_(s.ACIK_DURUMLAR)).limit(1))).first()
            if acik:
                continue
            await musteri_anonimlestir(db, m)
            sayi += 1
        await db.commit()
        if sayi >= sinir:
            break
    return sayi


async def zamanli_gorev(db: AsyncSession) -> Dict[str, Any]:
    bakim = await bakim_taramasi(db)
    konum = await konum_indirge(db)
    anonim = await saklama_temizligi(db)
    return {"bakim": bakim, "konum_indirgenen": konum, "anonimlesen_musteri": anonim}


# ---------------------------------------------------------------------------
# Raporlar
# ---------------------------------------------------------------------------
async def rapor(db: AsyncSession, hesap: str, bas: date, bit: date) -> Dict[str, Any]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Istanbul")
    b = datetime(bas.year, bas.month, bas.day, tzinfo=tz).astimezone(s.UTC)
    e = datetime(bit.year, bit.month, bit.day, tzinfo=tz).astimezone(s.UTC) + timedelta(days=1)
    bitenler = (await db.execute(select(SahaIsEmirleri).where(
        SahaIsEmirleri.hesap_email == hesap, SahaIsEmirleri.durum == "tamamlandi",
        SahaIsEmirleri.bitir_at >= b, SahaIsEmirleri.bitir_at < e))).scalars().all()
    atamalar = await atama_haritasi(db, [x.id for x in bitenler])
    teknisyenler = (await db.execute(select(SahaTeknisyenleri).where(SahaTeknisyenleri.hesap_email == hesap)
                                     .order_by(SahaTeknisyenleri.sira, SahaTeknisyenleri.id))).scalars().all()

    def ozet(isler: List[SahaIsEmirleri]) -> Dict[str, Any]:
        sureler = [(s.utc(x.bitir_at) - s.utc(x.basla_at)).total_seconds() / 60 for x in isler if x.basla_at and x.bitir_at]
        puanlar = [int(x.memnuniyet_puan) for x in isler if x.memnuniyet_puan]
        ilk = [x for x in isler if not x.ertele_sayisi and not x.takip_gerekli]
        return {
            "tamamlanan": len(isler),
            "ortalama_sure_dk": round(sum(sureler) / len(sureler)) if sureler else None,
            "ilk_seferde_oran": round(len(ilk) / len(isler), 3) if isler else None,
            "memnuniyet_ortalama": round(sum(puanlar) / len(puanlar), 2) if puanlar else None,
            "puan_sayisi": len(puanlar),
        }

    satirlar = []
    for t in teknisyenler:
        isler = [x for x in bitenler if t.id in atamalar.get(x.id, [])]
        satirlar.append({"teknisyen_id": t.id, "ad": t.ad, "renk": t.renk, "aktif": bool(t.aktif), **ozet(isler)})
    acik = dict((await db.execute(select(SahaIsEmirleri.durum, func.count(SahaIsEmirleri.id)).where(
        SahaIsEmirleri.hesap_email == hesap, SahaIsEmirleri.durum.in_(s.ACIK_DURUMLAR)).group_by(SahaIsEmirleri.durum))).all())
    return {"bas": bas.isoformat(), "bit": bit.isoformat(), "toplam": ozet(list(bitenler)), "teknisyenler": satirlar,
            "acik": {d: int(acik.get(d, 0)) for d in s.ACIK_DURUMLAR}}


async def bakim_listesi(db: AsyncSession, hesap: str, gun: int = 30) -> List[Dict[str, Any]]:
    bugun = s.tr_bugun()
    cihazlar = (await db.execute(select(SahaCihazlari).where(
        SahaCihazlari.hesap_email == hesap, SahaCihazlari.aktif.is_(True), SahaCihazlari.bakim_periyot_ay.isnot(None)))).scalars().all()
    adlar = dict((await db.execute(select(SahaMusterileri.id, SahaMusterileri.ad).where(
        SahaMusterileri.id.in_([c.musteri_id for c in cihazlar] or [0])))).all())
    sonuc = []
    for c in cihazlar:
        vade = s.bakim_vadesi(c.son_bakim, c.kurulum_tarihi, c.bakim_periyot_ay)
        if vade is None or vade > bugun + timedelta(days=gun):
            continue
        acik = (await db.execute(select(SahaIsEmirleri.id, SahaIsEmirleri.no).join(
            SahaIsCihazlari, SahaIsCihazlari.is_emri_id == SahaIsEmirleri.id).where(
            SahaIsCihazlari.cihaz_id == c.id, SahaIsEmirleri.tur == "bakim", SahaIsEmirleri.durum.in_(s.ACIK_DURUMLAR)).limit(1))).first()
        sonuc.append({"cihaz_id": c.id, "musteri_id": c.musteri_id, "musteri_ad": adlar.get(c.musteri_id), "tur": c.tur,
                      "marka": c.marka, "model": c.model, "seri_no": c.seri_no, "son_bakim": s.iso(c.son_bakim),
                      "vade": vade.isoformat(), "gecikme_gun": max(0, (bugun - vade).days),
                      "acik_is_emri": {"id": acik[0], "no": acik[1]} if acik else None})
    sonuc.sort(key=lambda x: x["vade"])
    return sonuc


# ---------------------------------------------------------------------------
# Faz 5R randevusu → iş emri (olay altyapısının ek abonesi)
# ---------------------------------------------------------------------------
_kanca_onbellek: Dict[str, Any] = {"bitis": 0.0, "hesaplar": None}
_kanca_bekleyen: List[int] = []
_kanca_gorev: Dict[str, Any] = {"pompa": None}
KANCA_ONBELLEK_SN = 30.0


def kanca_onbellegi_temizle() -> None:
    _kanca_onbellek["bitis"] = 0.0
    _kanca_onbellek["hesaplar"] = None


def _kanca_hesaplari() -> Optional[Set[str]]:
    if _kanca_onbellek["hesaplar"] is not None and _kanca_onbellek["bitis"] >= time.monotonic():
        return _kanca_onbellek["hesaplar"]
    return None


def _kanca_hesaplarini_yukle_sync(baglanti) -> Set[str]:
    t = SahaAyarlari.__table__
    hesaplar = {r[0] for r in baglanti.execute(select(t.c.hesap_email).where(t.c.randevu_kancasi.is_(True))).all()}
    _kanca_onbellek["hesaplar"] = hesaplar
    _kanca_onbellek["bitis"] = time.monotonic() + KANCA_ONBELLEK_SN
    return hesaplar


def _kanca_ilgileniyor_mu(tur: Optional[str]) -> bool:
    if tur is not None and tur != "randevu.olusturuldu":
        return False
    hesaplar = _kanca_hesaplari()
    return True if hesaplar is None else bool(hesaplar)


def _kanca_yaz(baglanti, olaylar, baglam) -> int:
    hesaplar = _kanca_hesaplari()
    if hesaplar is None:
        hesaplar = _kanca_hesaplarini_yukle_sync(baglanti)
    sayi = 0
    for tur, hesap, veri, _ in olaylar:
        if tur == "randevu.olusturuldu" and hesap and hesap.strip().lower() in hesaplar and veri.get("randevu_id"):
            _kanca_bekleyen.append(int(veri["randevu_id"]))
            sayi += 1
    return sayi


def _kanca_commit_sonrasi() -> None:
    if not _kanca_bekleyen:
        return
    try:
        dongu = asyncio.get_running_loop()
    except RuntimeError:
        return
    pompa = _kanca_gorev["pompa"]
    if pompa is not None and not pompa.done():
        return
    _kanca_gorev["pompa"] = dongu.create_task(_kanca_pompa())


async def _kanca_pompa() -> None:
    from core.database import db_manager

    for _ in range(20):
        if not _kanca_bekleyen:
            break
        rid = _kanca_bekleyen.pop(0)
        if not db_manager.async_session_maker:
            return
        try:
            async with db_manager.async_session_maker() as db:
                await randevudan_is_emri(db, rid)
        except Exception:  # noqa: BLE001
            logger.exception("Randevudan iş emri açılamadı (randevu %s)", rid)


async def kanca_bitmesini_bekle() -> None:
    """Testler için."""
    pompa = _kanca_gorev["pompa"]
    if pompa is not None:
        await asyncio.wait_for(asyncio.shield(pompa), timeout=30)


async def randevudan_is_emri(db: AsyncSession, randevu_id: int) -> Optional[int]:
    """Randevu modülü ve saha servisi açık, kanca ayarı açıksa randevudan iş emri (bir kez)."""
    from models.randevu import RandevuKisileri, Randevular, RandevuTurleri
    from services.moduller import modul_acik_mi

    r = (await db.execute(select(Randevular).where(Randevular.id == randevu_id))).scalars().first()
    if r is None or not r.hesap_email or r.durum != "onayli":
        return None
    hesap = r.hesap_email
    var = (await db.execute(select(SahaIsEmirleri.id).where(SahaIsEmirleri.randevu_id == r.id))).scalar()
    if var:
        return int(var)
    a = (await db.execute(select(SahaAyarlari).where(SahaAyarlari.hesap_email == hesap))).scalars().first()
    if a is None or not a.randevu_kancasi:
        return None
    if not await modul_acik_mi(db, hesap, s.MODUL) or not await modul_acik_mi(db, hesap, "randevu"):
        return None
    eposta = (r.eposta or "").strip().lower() or None
    m = None
    if eposta:
        m = (await db.execute(select(SahaMusterileri).where(SahaMusterileri.hesap_email == hesap, SahaMusterileri.eposta == eposta,
                                                            SahaMusterileri.anonim.is_(False)).order_by(SahaMusterileri.id))).scalars().first()
    if m is None:
        m = SahaMusterileri(hesap_email=hesap, tur="bireysel", ad=(r.ad or eposta or "—")[:160], eposta=eposta,
                            telefon=r.telefon, dil=(r.dil if r.dil in s.DILLER else "tr"), created_at=s.simdi())
        db.add(m)
        await db.flush()
    rt = (await db.execute(select(RandevuTurleri).where(RandevuTurleri.id == r.tur_id))).scalars().first()
    satirlar = []
    sorular = {q.get("id"): q.get("etiket") for q in (s.json_yukle(rt.sorular, []) if rt else []) or []}
    for kimlik, deger in (s.json_yukle(r.yanitlar, {}) or {}).items():
        satirlar.append(f"{sorular.get(kimlik, kimlik)}: {'✓' if deger is True else deger}")
    teknisyenler: List[int] = []
    k = (await db.execute(select(RandevuKisileri).where(RandevuKisileri.id == r.kisi_id))).scalars().first()
    if k is not None and k.eposta:
        t = await teknisyen_bul(db, hesap, k.eposta.strip().lower())
        if t is not None and t.aktif:
            teknisyenler = [t.id]
    sure = int((s.utc(r.bitis) - s.utc(r.baslangic)).total_seconds() // 60) if r.bitis and r.baslangic else 60
    g = {
        "musteri_id": m.id, "tur": a.randevu_is_turu or "kesif", "oncelik": "normal",
        "baslik": f"{(rt.ad if rt else 'Randevu')} — {r.ad or eposta or ''}"[:160],
        "aciklama": "\n".join(satirlar) or None, "plan_bas": s.iso(r.baslangic), "tahmini_dk": max(5, min(sure, 24 * 60)),
        "teknisyenler": teknisyenler,
    }
    try:
        sonuc = await is_emri_olustur(db, hesap, g, "randevu", randevu_id=r.id)
    except s.SahaHatasi as h:
        logger.info("Randevudan iş emri açılmadı (%s): %s", r.id, h.kod)
        await db.rollback()
        return None
    if sonuc.yeni_atananlar:
        await teknisyenlere_bildir(sonuc.ie.id, sonuc.yeni_atananlar)
    return sonuc.ie.id


def _kanca_kaydet() -> None:
    from services import webhook

    webhook.abone_ekle(webhook.OlayAbonesi(
        ad="saha_servisi",
        ilgileniyor_mu=_kanca_ilgileniyor_mu,
        yaz=_kanca_yaz,
        tablolar=frozenset({"randevular"}),
        commit_sonrasi=_kanca_commit_sonrasi,
    ))


_kanca_kaydet()
