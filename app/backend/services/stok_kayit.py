"""Faz 6P — Stok ve satış noktası: kayıt işleri (stok hareketi, satış, iade, kasa, sayım, rapor).

Saf kurallar `services/stok_pos.py`'de; burası veritabanına yazan/okuyan katman.

Tutarlılık
----------
* Stok değişimi TEK yoldan geçer: `stok_degistir` — satırı yoksa açar, `miktar = miktar + :d`
  atomik güncellemesini yapar (eksi stok kapalıysa `WHERE miktar + :d >= 0` koşuluyla: eşzamanlı iki
  satış aynı son ürünü isterse yalnız biri düşer, diğeri `yetersiz_stok` alır ve işlemi geri alınır)
  ve hareket kaydını yazar. Çağıran commit eder.
* Kritik stok uyarısı ürün başına TEK olay: `kritik_at` koşullu güncellemesi (`IS NULL` iken dolar);
  stok eşik üstüne çıkınca boşalır, bir sonraki düşüş yeniden uyarır.
* QR menü bağı: bağlı ürünün toplam stoku 0'a inince menü ürünü "tükendi", yeniden artınca geri
  açılır (yalnız geçişte; ayar `qr_stok_esitle`).
* Faz 6S saha malzemeleri (`saha_malzemeleri.stok`) bu katmanı KULLANMIYOR: orada stok bilerek eksiye
  düşebilen basit bir sayaç. Ortaklaştırma önerisi rapor notunda (malzemeleri `stok_urunleri`ne
  `stok_takibi` ile taşıyıp kullanımı `stok_degistir(..., tur="cikis")` ile düşmek).
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.stok_pos import (
    PosAlicilari,
    PosIadeler,
    PosKasaOturumlari,
    PosSatisKalemleri,
    PosSatislari,
    StokAyarlari,
    StokHareketleri,
    StokKonumlari,
    StokSayimKalemleri,
    StokSayimlari,
    StokSeviyeleri,
    StokTedarikcileri,
    StokUrunleri,
)
from services import stok_pos as s
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

KRITIK_OLAYI = "stok_kritik"
#: Otomasyon/webhook olay türleri.
OLAY_KRITIK = "stok.kritik"
OLAY_SATIS = "pos.satis"


@dataclass
class Yetki:
    hesap: str
    kisi: str
    #: Yönetim (ürün, stok, rapor, ayar) — sahip ya da `stok` izni.
    stok: bool
    #: Satış ekranı — `kasa` izni (stok izni de satış yapabilir).
    kasa: bool
    #: Ajans yöneticisi: salt okunur destek görünümü.
    ajans: bool = False


# ---------------------------------------------------------------------------
# Ayarlar, konumlar, sınırlar
# ---------------------------------------------------------------------------
async def ayarlar(db: AsyncSession, hesap: str) -> StokAyarlari:
    a = (await db.execute(select(StokAyarlari).where(StokAyarlari.hesap_email == hesap))).scalars().first()
    if a is not None:
        return a
    a = StokAyarlari(hesap_email=hesap, created_at=s.simdi())
    db.add(a)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        a = (await db.execute(select(StokAyarlari).where(StokAyarlari.hesap_email == hesap))).scalars().first()
    await db.refresh(a)
    return a


async def modul_ayari(db: AsyncSession, hesap: str, alan: str, varsayilan: int) -> int:
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, hesap, s.MODUL, alan)
    return int(deger) if isinstance(deger, int) and not isinstance(deger, bool) else varsayilan


async def konumlar(db: AsyncSession, hesap: str, *, hepsi: bool = False) -> List[StokKonumlari]:
    """Hesabın konumları; hiç yoksa varsayılan "Merkez" açılır (ilk kullanımda)."""
    sorgu = select(StokKonumlari).where(StokKonumlari.hesap_email == hesap)
    liste = (await db.execute(sorgu.order_by(StokKonumlari.sira, StokKonumlari.id))).scalars().all()
    if not liste:
        k = StokKonumlari(hesap_email=hesap, ad="Merkez", varsayilan=True, aktif=True, created_at=s.simdi())
        db.add(k)
        await db.commit()
        await db.refresh(k)
        liste = [k]
    return [k for k in liste if hepsi or k.aktif]


async def varsayilan_konum(db: AsyncSession, hesap: str) -> StokKonumlari:
    liste = await konumlar(db, hesap)
    for k in liste:
        if k.varsayilan:
            return k
    return liste[0]


async def konum_bul(db: AsyncSession, hesap: str, ham: Any, *, varsayilan: bool = True) -> StokKonumlari:
    if ham in (None, "") and varsayilan:
        return await varsayilan_konum(db, hesap)
    kimlik = s.tam_sayi(ham, "konum_id", 1, 2_000_000_000, bos_olabilir=False)
    k = (await db.execute(select(StokKonumlari).where(StokKonumlari.id == kimlik, StokKonumlari.hesap_email == hesap))).scalars().first()
    if k is None or not k.aktif:
        raise s.StokHatasi("konum_yok", "konum_id", durum=404)
    return k


async def urun_sayisi(db: AsyncSession, hesap: str) -> int:
    return int((await db.execute(select(func.count(StokUrunleri.id)).where(
        StokUrunleri.hesap_email == hesap, StokUrunleri.aktif.is_(True)))).scalar() or 0)


# ---------------------------------------------------------------------------
# Ürün
# ---------------------------------------------------------------------------
async def urun_bul(db: AsyncSession, hesap: str, urun_id: Any) -> StokUrunleri:
    kimlik = s.tam_sayi(urun_id, "urun_id", 1, 2_000_000_000, bos_olabilir=False)
    u = (await db.execute(select(StokUrunleri).where(StokUrunleri.id == kimlik, StokUrunleri.hesap_email == hesap))).scalars().first()
    if u is None:
        raise s.StokHatasi("urun_yok", "urun_id", durum=404)
    return u


async def kodla_bul(db: AsyncSession, hesap: str, kod: str) -> Optional[StokUrunleri]:
    """Barkod ya da SKU ile (birebir) aktif ürün."""
    kod = s.okutma_kodu(kod)
    if not kod:
        return None
    return (await db.execute(select(StokUrunleri).where(
        StokUrunleri.hesap_email == hesap, StokUrunleri.aktif.is_(True),
        or_(StokUrunleri.barkod == kod, StokUrunleri.sku == kod)).order_by(StokUrunleri.id).limit(1))).scalars().first()


async def benzersiz_barkod(db: AsyncSession, hesap: str) -> str:
    for _ in range(20):
        kod = s.ic_barkod_uret()
        var = (await db.execute(select(StokUrunleri.id).where(StokUrunleri.hesap_email == hesap, StokUrunleri.barkod == kod))).first()
        if var is None:
            return kod
    raise s.StokHatasi("barkod_uretilemedi", "barkod", durum=500)


async def seviyeler(db: AsyncSession, urun_idler: Iterable[int]) -> Dict[int, Dict[int, int]]:
    idler = sorted(set(urun_idler))
    sonuc: Dict[int, Dict[int, int]] = {i: {} for i in idler}
    if not idler:
        return sonuc
    for uid, kid, miktar in (await db.execute(select(StokSeviyeleri.urun_id, StokSeviyeleri.konum_id, StokSeviyeleri.miktar)
                                              .where(StokSeviyeleri.urun_id.in_(idler)))).all():
        sonuc.setdefault(uid, {})[kid] = int(miktar or 0)
    return sonuc


async def toplam_stok(db: AsyncSession, urun_id: int) -> int:
    return int((await db.execute(select(func.coalesce(func.sum(StokSeviyeleri.miktar), 0))
                                 .where(StokSeviyeleri.urun_id == urun_id))).scalar() or 0)


# ---------------------------------------------------------------------------
# Stok değişimi (TEK yol)
# ---------------------------------------------------------------------------
async def _seviye_satiri(db: AsyncSession, hesap: str, urun_id: int, konum_id: int) -> None:
    var = (await db.execute(select(StokSeviyeleri.id).where(StokSeviyeleri.urun_id == urun_id, StokSeviyeleri.konum_id == konum_id))).first()
    if var is not None:
        return
    try:
        async with db.begin_nested():
            db.add(StokSeviyeleri(hesap_email=hesap, urun_id=urun_id, konum_id=konum_id, miktar=0, updated_at=s.simdi()))
    except IntegrityError:
        pass  # eşzamanlı istek açtı


async def stok_degistir(db: AsyncSession, hesap: str, urun: StokUrunleri, konum_id: int, degisim: int, tur: str, *,
                        kisi: Optional[str], eksi_izin: bool, **ek: Any) -> int:
    """Konumdaki stoku `degisim` (binde bir, işaretli) kadar değiştirir ve hareketi yazar; yeni miktarı döner.

    Eksi stok kapalıysa düşüş koşullu: yetersizse `yetersiz_stok` (409) — çağıran geri alır."""
    if tur not in s.HAREKET_TURLERI:
        raise ValueError(tur)
    await _seviye_satiri(db, hesap, urun.id, konum_id)
    kosul = [StokSeviyeleri.urun_id == urun.id, StokSeviyeleri.konum_id == konum_id]
    if degisim < 0 and not eksi_izin:
        kosul.append(StokSeviyeleri.miktar + degisim >= 0)
    sonuc = await db.execute(update(StokSeviyeleri).where(*kosul)
                             .values(miktar=StokSeviyeleri.miktar + degisim, updated_at=s.simdi())
                             .execution_options(synchronize_session=False))
    if not sonuc.rowcount:
        mevcut = (await db.execute(select(StokSeviyeleri.miktar).where(*kosul[:2]))).scalar() or 0
        raise s.StokHatasi("yetersiz_stok", "kalemler", durum=409, urun_id=urun.id, ad=urun.ad,
                           mevcut=s.miktar_yaz(int(mevcut)), istenen=s.miktar_yaz(-degisim))
    sonra = int((await db.execute(select(StokSeviyeleri.miktar).where(*kosul[:2]))).scalar() or 0)
    db.add(StokHareketleri(hesap_email=hesap, urun_id=urun.id, konum_id=konum_id, tur=tur, miktar=degisim, sonra=sonra,
                           kisi=kisi, zaman=s.simdi(), **ek))
    return sonra


@dataclass
class Gecis:
    urun_id: int
    once: int
    sonra: int


async def gecisleri_isle(db: AsyncSession, hesap: str, gecisler: Sequence[Gecis]) -> List[int]:
    """Commit SONRASI: kritik stok (ürün başına tek olay + bildirim) ve QR menü "tükendi" eşitlemesi.

    Hata fırlatmaz (asıl işlem tamamlandı). Kritik olayı üretilen ürünlerin kimlikleri döner."""
    if not gecisler:
        return []
    try:
        return await _gecisleri_isle(db, hesap, gecisler)
    except Exception:  # noqa: BLE001 - satış/hareket zaten kaydedildi
        logger.exception("Stok geçişleri işlenemedi (%s)", hesap)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return []


async def _gecisleri_isle(db: AsyncSession, hesap: str, gecisler: Sequence[Gecis]) -> List[int]:
    a = await ayarlar(db, hesap)
    birlesik: Dict[int, Gecis] = {}
    for g in gecisler:
        if g.urun_id in birlesik:
            birlesik[g.urun_id] = Gecis(g.urun_id, birlesik[g.urun_id].once, g.sonra)
        else:
            birlesik[g.urun_id] = g
    urunler = {u.id: u for u in (await db.execute(select(StokUrunleri).where(StokUrunleri.id.in_(list(birlesik))))).scalars().all()}
    yeni_kritik: List[StokUrunleri] = []
    an = s.simdi()
    for uid, g in birlesik.items():
        u = urunler.get(uid)
        if u is None or not u.stok_takibi:
            continue
        toplam = await toplam_stok(db, uid)
        if u.kritik_esik is not None:
            if toplam <= u.kritik_esik:
                r = await db.execute(update(StokUrunleri).where(StokUrunleri.id == uid, StokUrunleri.kritik_at.is_(None))
                                     .values(kritik_at=an).execution_options(synchronize_session=False))
                if r.rowcount:
                    yeni_kritik.append(u)
            else:
                await db.execute(update(StokUrunleri).where(StokUrunleri.id == uid, StokUrunleri.kritik_at.isnot(None))
                                 .values(kritik_at=None).execution_options(synchronize_session=False))
        if u.menu_urun_id and a.qr_stok_esitle and (g.once > 0) != (toplam > 0):
            await _menu_esitle(db, hesap, u.menu_urun_id, tukendi=toplam <= 0)
    if yeni_kritik:
        from services import webhook

        for u in yeni_kritik:
            await webhook.olay_yayinla(db, OLAY_KRITIK, hesap, kritik_verisi(u, await toplam_stok(db, u.id)))
    await db.commit()
    if yeni_kritik and a.kritik_bildirim:
        await _kritik_bildir(db, hesap, yeni_kritik)
    return [u.id for u in yeni_kritik]


async def _menu_esitle(db: AsyncSession, hesap: str, menu_urun_id: int, tukendi: bool) -> None:
    """Bağlı QR menü ürününü (yalnız bu hesabın mağazasındaysa) "tükendi" yapar/açar."""
    from models.qr_menu import MenuMagazalari, MenuUrunleri

    magaza = select(MenuMagazalari.id).where(MenuMagazalari.hesap_email == hesap).scalar_subquery()
    await db.execute(update(MenuUrunleri).where(MenuUrunleri.id == menu_urun_id, MenuUrunleri.magaza_id.in_(magaza))
                     .values(stokta_yok=tukendi).execution_options(synchronize_session=False))


def kritik_verisi(u: StokUrunleri, toplam: int) -> Dict[str, Any]:
    """`stok.kritik` olay verisi — kişisel veri yok."""
    return {"urun_id": u.id, "ad": u.ad, "barkod": u.barkod, "sku": u.sku, "birim": u.birim,
            "miktar": s.miktar_yaz(toplam), "esik": s.miktar_yaz(u.kritik_esik)}


async def _kritik_bildir(db: AsyncSession, hesap: str, urunler: Sequence[StokUrunleri]) -> None:
    from services.notify import dispatch, render

    try:
        adlar = ", ".join(u.ad for u in urunler[:5]) + (f" +{len(urunler) - 5}" if len(urunler) > 5 else "")
        baslik, govde = await render(db, KRITIK_OLAYI, f"Kritik stok: {len(urunler)} ürün",
                                     f"Kritik stok seviyesine inen ürünler: {adlar}", {"sayi": len(urunler), "urunler": adlar})
        await dispatch(db, event_type=KRITIK_OLAYI, title=baslik, body=govde, recipients=[{"email": hesap, "role": "client"}],
                       link="/client?sekme=stokPos&bolum=urunler&kritik=1", ref_type="stok_urunleri", ref_id=urunler[0].id)
    except Exception:  # noqa: BLE001
        logger.exception("Kritik stok bildirimi gönderilemedi")


# ---------------------------------------------------------------------------
# Kasa oturumu
# ---------------------------------------------------------------------------
def acik_anahtari(hesap: str, konum_id: int) -> str:
    return f"{hesap}|{konum_id}"


async def acik_oturum(db: AsyncSession, hesap: str, konum_id: int) -> Optional[PosKasaOturumlari]:
    return (await db.execute(select(PosKasaOturumlari).where(
        PosKasaOturumlari.acik_anahtar == acik_anahtari(hesap, konum_id)))).scalars().first()


async def oturum_bul(db: AsyncSession, hesap: str, oturum_id: Any) -> PosKasaOturumlari:
    kimlik = s.tam_sayi(oturum_id, "oturum_id", 1, 2_000_000_000, bos_olabilir=False)
    o = (await db.execute(select(PosKasaOturumlari).where(PosKasaOturumlari.id == kimlik,
                                                          PosKasaOturumlari.hesap_email == hesap))).scalars().first()
    if o is None:
        raise s.StokHatasi("oturum_yok", "oturum_id", durum=404)
    return o


async def ay_kasiyerleri(db: AsyncSession, hesap: str) -> set:
    bugun = s.tr_gunu()
    bas, _ = s.gun_araligi(bugun.replace(day=1), bugun)
    return set((await db.execute(select(PosKasaOturumlari.acan).where(
        PosKasaOturumlari.hesap_email == hesap, PosKasaOturumlari.acilis_at >= bas))).scalars().all())


async def kasa_ac(db: AsyncSession, y: Yetki, govde: Dict[str, Any]) -> PosKasaOturumlari:
    konum = await konum_bul(db, y.hesap, govde.get("konum_id"))
    nakit = s.kurus(govde.get("acilis_nakit"), "acilis_nakit", bos_olabilir=True) or 0
    if await acik_oturum(db, y.hesap, konum.id) is not None:
        raise s.StokHatasi("kasa_zaten_acik", "konum_id", durum=409)
    sinir = await modul_ayari(db, y.hesap, "kasa_kullanici_siniri", s.VARSAYILAN_KASA_KULLANICI_SINIRI)
    kasiyerler = await ay_kasiyerleri(db, y.hesap)
    if y.kisi not in kasiyerler and len(kasiyerler) >= sinir:
        raise s.StokHatasi("kasa_kullanici_siniri", None, durum=403, sinir=sinir)
    o = PosKasaOturumlari(hesap_email=y.hesap, konum_id=konum.id, durum="acik", acik_anahtar=acik_anahtari(y.hesap, konum.id),
                          acan=y.kisi, acilis_at=s.simdi(), acilis_nakit=nakit)
    db.add(o)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise s.StokHatasi("kasa_zaten_acik", "konum_id", durum=409)
    await db.refresh(o)
    return o


async def kasa_kapat(db: AsyncSession, y: Yetki, o: PosKasaOturumlari, govde: Dict[str, Any]) -> PosKasaOturumlari:
    if o.durum != "acik":
        raise s.StokHatasi("kasa_kapali", None, durum=409)
    sayilan = s.kurus(govde.get("sayilan_nakit"), "sayilan_nakit")
    notlar = s.bos_ya_da(govde.get("notlar"), "notlar", 500, cok_satir=True)
    ozet = await oturum_ozeti(db, o)
    beklenen = ozet["nakit"]["beklenen"]
    o.durum, o.acik_anahtar, o.kapatan, o.kapanis_at = "kapali", None, y.kisi, s.simdi()
    o.sayilan_nakit, o.beklenen_nakit, o.fark, o.notlar = sayilan, beklenen, sayilan - beklenen, notlar
    ozet["nakit"].update({"sayilan": sayilan, "fark": sayilan - beklenen})
    o.ozet = s.json_yaz(ozet)
    await db.commit()
    await db.refresh(o)
    return o


# ---------------------------------------------------------------------------
# Özet (Z-benzeri; mali değil)
# ---------------------------------------------------------------------------
def ozet_hesapla(satislar: Sequence[PosSatislari], kalemler: Sequence[PosSatisKalemleri], iadeler: Sequence[PosIadeler],
                 kalem_haritasi: Dict[int, PosSatisKalemleri]) -> Dict[str, Any]:
    """Satış + iade kayıtlarından Z-benzeri özet (iptal edilen satışlar ayrı sayılır)."""
    gecerli = [x for x in satislar if x.durum != "iptal"]
    gecerli_id = {x.id for x in gecerli}
    iptal = [x for x in satislar if x.durum == "iptal"]
    gercek_iade = [i for i in iadeler if i.tur == "iade"]
    odeme = {"nakit": sum(x.nakit for x in gecerli), "kart": sum(x.kart for x in gecerli), "havale": sum(x.havale for x in gecerli)}
    iade_odeme = {"nakit": 0, "kart": 0, "havale": 0}
    for i in gercek_iade:
        iade_odeme[i.odeme_turu] = iade_odeme.get(i.odeme_turu, 0) + int(i.tutar or 0)
    # KDV dökümü ve en çok satanlar: dönemdeki satış satırları − dönemdeki iade satırları.
    kdv_satirlari: List[Tuple[int, int]] = []
    urunler: Dict[int, Dict[str, Any]] = {}
    for k in kalemler:
        if k.satis_id not in gecerli_id:
            continue
        kdv_satirlari.append((k.kdv_orani, k.tutar))
        u = urunler.setdefault(k.urun_id, {"urun_id": k.urun_id, "ad": k.ad, "birim": k.birim, "adet": 0, "tutar": 0})
        u["adet"] += k.adet
        u["tutar"] += k.tutar
    for i in gercek_iade:
        for ik in s.json_yukle(i.kalemler, []) or []:
            k = kalem_haritasi.get(int(ik.get("kalem_id") or 0))
            if k is None:
                continue
            kdv_satirlari.append((k.kdv_orani, -int(ik.get("tutar") or 0)))
            u = urunler.setdefault(k.urun_id, {"urun_id": k.urun_id, "ad": k.ad, "birim": k.birim, "adet": 0, "tutar": 0})
            u["adet"] -= int(ik.get("adet") or 0)
            u["tutar"] -= int(ik.get("tutar") or 0)
    en_cok = sorted((u for u in urunler.values() if u["adet"] > 0), key=lambda u: (-u["adet"], -u["tutar"]))[:10]
    satis_toplam = sum(x.toplam for x in gecerli)
    iade_toplam = sum(int(i.tutar or 0) for i in gercek_iade)
    return {
        "satis_sayisi": len(gecerli),
        "brut": sum(x.ara_toplam for x in gecerli),
        "indirim": sum(x.satir_indirim + x.toplam_indirim for x in gecerli),
        "satis_toplam": satis_toplam,
        "iade_sayisi": len(gercek_iade),
        "iade_toplam": iade_toplam,
        "iptal_sayisi": len(iptal),
        "iptal_toplam": sum(x.toplam for x in iptal),
        "net": satis_toplam - iade_toplam,
        "odemeler": {t: odeme[t] - iade_odeme.get(t, 0) for t in ("nakit", "kart", "havale")},
        "odemeler_brut": odeme,
        "iadeler": iade_odeme,
        "kdv_dokumu": [d for d in s.kdv_dokumu_hesapla(kdv_satirlari) if d["tutar"] or d["kdv"]],
        "en_cok_satanlar": [{**u, "adet": s.miktar_yaz(u["adet"])} for u in en_cok],
        "para_birimi": (satislar[0].para_birimi if satislar else "TRY"),
    }


async def _kalem_haritasi(db: AsyncSession, satis_idler: Iterable[int], iadeler: Sequence[PosIadeler]) -> Tuple[List[PosSatisKalemleri], Dict[int, PosSatisKalemleri]]:
    idler = set(satis_idler)
    kalemler = list((await db.execute(select(PosSatisKalemleri).where(PosSatisKalemleri.satis_id.in_(idler or {0})))).scalars().all())
    harita = {k.id: k for k in kalemler}
    eksik = set()
    for i in iadeler:
        for ik in s.json_yukle(i.kalemler, []) or []:
            kid = int(ik.get("kalem_id") or 0)
            if kid and kid not in harita:
                eksik.add(kid)
    if eksik:
        for k in (await db.execute(select(PosSatisKalemleri).where(PosSatisKalemleri.id.in_(eksik)))).scalars().all():
            harita[k.id] = k
    return kalemler, harita


async def oturum_ozeti(db: AsyncSession, o: PosKasaOturumlari) -> Dict[str, Any]:
    satislar = list((await db.execute(select(PosSatislari).where(PosSatislari.oturum_id == o.id).order_by(PosSatislari.id))).scalars().all())
    iadeler = list((await db.execute(select(PosIadeler).where(PosIadeler.oturum_id == o.id))).scalars().all())
    kalemler, harita = await _kalem_haritasi(db, [x.id for x in satislar], iadeler)
    ozet = ozet_hesapla(satislar, kalemler, iadeler, harita)
    nakit_satis = ozet["odemeler_brut"]["nakit"]
    nakit_iade = ozet["iadeler"]["nakit"]
    ozet["nakit"] = {"acilis": o.acilis_nakit, "satis": nakit_satis, "iade": nakit_iade,
                     "beklenen": o.acilis_nakit + nakit_satis - nakit_iade, "sayilan": o.sayilan_nakit, "fark": o.fark}
    return ozet


async def gun_ozeti(db: AsyncSession, hesap: str, gun: date, konum_id: Optional[int]) -> Dict[str, Any]:
    bas, bit = s.gun_araligi(gun, gun)
    kosul = [PosSatislari.hesap_email == hesap, PosSatislari.zaman >= bas, PosSatislari.zaman < bit]
    ikosul = [PosIadeler.hesap_email == hesap, PosIadeler.zaman >= bas, PosIadeler.zaman < bit]
    if konum_id:
        kosul.append(PosSatislari.konum_id == konum_id)
        ikosul.append(PosIadeler.oturum_id.in_(select(PosKasaOturumlari.id).where(PosKasaOturumlari.konum_id == konum_id)))
    satislar = list((await db.execute(select(PosSatislari).where(*kosul))).scalars().all())
    iadeler = list((await db.execute(select(PosIadeler).where(*ikosul))).scalars().all())
    kalemler, harita = await _kalem_haritasi(db, [x.id for x in satislar], iadeler)
    ozet = ozet_hesapla(satislar, kalemler, iadeler, harita)
    oturumlar = (await db.execute(select(PosKasaOturumlari).where(
        PosKasaOturumlari.hesap_email == hesap, PosKasaOturumlari.acilis_at < bit,
        or_(PosKasaOturumlari.kapanis_at.is_(None), PosKasaOturumlari.kapanis_at >= bas),
        *([PosKasaOturumlari.konum_id == konum_id] if konum_id else [])).order_by(PosKasaOturumlari.id))).scalars().all()
    ozet["oturumlar"] = [oturum_sozlugu(o) for o in oturumlar]
    ozet["tarih"] = gun.isoformat()
    ozet["konum_id"] = konum_id
    return ozet


def oturum_sozlugu(o: PosKasaOturumlari) -> Dict[str, Any]:
    return {"id": o.id, "konum_id": o.konum_id, "durum": o.durum, "acan": o.acan, "acilis_at": s.iso(o.acilis_at),
            "acilis_nakit": o.acilis_nakit, "kapatan": o.kapatan, "kapanis_at": s.iso(o.kapanis_at),
            "sayilan_nakit": o.sayilan_nakit, "beklenen_nakit": o.beklenen_nakit, "fark": o.fark, "notlar": o.notlar}


# ---------------------------------------------------------------------------
# Satış
# ---------------------------------------------------------------------------
@dataclass
class SatisSonucu:
    satis: PosSatislari
    tekrar: bool
    gecisler: List[Gecis]


async def _sayac_artir(db: AsyncSession, hesap: str, alan: str) -> int:
    kolon = getattr(StokAyarlari, alan)
    await db.execute(update(StokAyarlari).where(StokAyarlari.hesap_email == hesap).values({alan: kolon + 1})
                     .execution_options(synchronize_session=False))
    return int((await db.execute(select(kolon).where(StokAyarlari.hesap_email == hesap))).scalar() or 0)


async def satis_bul(db: AsyncSession, hesap: str, satis_id: Any) -> PosSatislari:
    kimlik = s.tam_sayi(satis_id, "satis_id", 1, 2_000_000_000, bos_olabilir=False)
    x = (await db.execute(select(PosSatislari).where(PosSatislari.id == kimlik, PosSatislari.hesap_email == hesap))).scalars().first()
    if x is None:
        raise s.StokHatasi("satis_yok", "satis_id", durum=404)
    return x


async def _kalem_girdileri(db: AsyncSession, hesap: str, ham: Any) -> List[s.KalemGirdi]:
    if not isinstance(ham, list) or not ham:
        raise s.StokHatasi("sepet_bos", "kalemler")
    if len(ham) > s.EN_COK_KALEM:
        raise s.StokHatasi("cok_kalem", "kalemler", en_cok=s.EN_COK_KALEM)
    idler = set()
    for i, k in enumerate(ham):
        if not isinstance(k, dict):
            raise s.StokHatasi("kalem_gecersiz", f"kalemler.{i}")
        idler.add(s.tam_sayi(k.get("urun_id"), f"kalemler.{i}.urun_id", 1, 2_000_000_000, bos_olabilir=False))
    urunler = {u.id: u for u in (await db.execute(select(StokUrunleri).where(
        StokUrunleri.hesap_email == hesap, StokUrunleri.id.in_(idler)))).scalars().all()}
    girdiler: List[s.KalemGirdi] = []
    for i, k in enumerate(ham):
        u = urunler.get(int(k["urun_id"]))
        if u is None or not u.aktif:
            raise s.StokHatasi("urun_yok", f"kalemler.{i}.urun_id", durum=404)
        adet = s.miktar_coz(k.get("adet", 1), f"kalemler.{i}.adet", u.birim)
        brut = s.yuvarla(u.satis_fiyati, adet, 1000)
        indirim = s.kurus(k.get("indirim"), f"kalemler.{i}.indirim", bos_olabilir=True) or 0
        yuzde = k.get("indirim_yuzde")
        if yuzde not in (None, "", 0):
            oran = s.tam_sayi(yuzde, f"kalemler.{i}.indirim_yuzde", 0, 100)
            indirim = max(indirim, s.yuvarla(brut, oran or 0, 100))
        if indirim > brut:
            raise s.StokHatasi("indirim_fazla", f"kalemler.{i}.indirim")
        girdiler.append(s.KalemGirdi(urun_id=u.id, ad=u.ad, barkod=u.barkod, birim=u.birim, adet=adet, birim_fiyat=u.satis_fiyati,
                                     kdv_orani=u.kdv_orani, birim_maliyet=u.alis_fiyati, satir_indirim=indirim))
    return girdiler


def _toplam_indirim(govde: Dict[str, Any], net: int) -> int:
    tutar = s.kurus(govde.get("toplam_indirim"), "toplam_indirim", bos_olabilir=True) or 0
    yuzde = govde.get("toplam_indirim_yuzde")
    if yuzde not in (None, "", 0):
        oran = s.tam_sayi(yuzde, "toplam_indirim_yuzde", 0, 100) or 0
        tutar = max(tutar, s.yuvarla(net, oran, 100))
    if tutar > net:
        raise s.StokHatasi("indirim_fazla", "toplam_indirim")
    return tutar


async def sepet_onizle(db: AsyncSession, hesap: str, govde: Dict[str, Any]) -> s.SepetSonucu:
    girdiler = await _kalem_girdileri(db, hesap, govde.get("kalemler"))
    on = s.sepet_hesapla(girdiler)
    return s.sepet_hesapla(girdiler, _toplam_indirim(govde, on.toplam))


async def satis_olustur(db: AsyncSession, y: Yetki, govde: Dict[str, Any]) -> SatisSonucu:
    istemci = s.istemci_kimligi_duzelt(govde.get("istemci_kimligi"))
    if istemci:
        onceki = (await db.execute(select(PosSatislari).where(PosSatislari.hesap_email == y.hesap,
                                                              PosSatislari.istemci_kimligi == istemci))).scalars().first()
        if onceki is not None:
            return SatisSonucu(onceki, True, [])
    a = await ayarlar(db, y.hesap)
    konum = await konum_bul(db, y.hesap, govde.get("konum_id"))
    oturum = await acik_oturum(db, y.hesap, konum.id)
    if oturum is None:
        raise s.StokHatasi("kasa_kapali", "konum_id", durum=409)
    girdiler = await _kalem_girdileri(db, y.hesap, govde.get("kalemler"))
    sonuc = s.sepet_hesapla(girdiler)
    sonuc = s.sepet_hesapla(girdiler, _toplam_indirim(govde, sonuc.toplam))
    if not y.stok and s.indirim_yuzdesi(sonuc) > int(a.kasa_indirim_yuzde or 0):
        raise s.StokHatasi("indirim_limiti", "toplam_indirim", durum=403, limit=int(a.kasa_indirim_yuzde or 0))
    beklenen = govde.get("beklenen_toplam")
    if beklenen not in (None, ""):
        if s.kurus(beklenen, "beklenen_toplam") != sonuc.toplam:
            raise s.StokHatasi("toplam_degisti", "beklenen_toplam", durum=409, toplam=sonuc.toplam)
    odeme = s.odeme_coz(govde.get("odeme"), sonuc.toplam)
    alici_id = None
    musteri_ad = s.bos_ya_da(govde.get("musteri_ad"), "musteri_ad", 160)
    if govde.get("alici_id") not in (None, ""):
        alici = await alici_bul(db, y.hesap, govde.get("alici_id"))
        alici_id, musteri_ad = alici.id, musteri_ad or alici.ad
    notlar = s.bos_ya_da(govde.get("notlar"), "notlar", 300)

    an = s.simdi()
    try:
        sayac = await _sayac_artir(db, y.hesap, "satis_sayac")
        x = PosSatislari(hesap_email=y.hesap, no=s.fis_no(sayac), konum_id=konum.id, oturum_id=oturum.id, kasiyer=y.kisi,
                         alici_id=alici_id, musteri_ad=musteri_ad, durum="tamamlandi", ara_toplam=sonuc.ara_toplam,
                         satir_indirim=sonuc.satir_indirim, toplam_indirim=sonuc.toplam_indirim, toplam=sonuc.toplam,
                         kdv_toplam=sonuc.kdv_toplam, kdv_dokumu=s.json_yaz(sonuc.kdv_dokumu), odeme_turu=odeme["tur"],
                         nakit=odeme["nakit"], kart=odeme["kart"], havale=odeme["havale"], nakit_alinan=odeme["nakit_alinan"],
                         para_ustu=odeme["para_ustu"], para_birimi=a.para_birimi or "TRY", istemci_kimligi=istemci,
                         notlar=notlar, zaman=an)
        db.add(x)
        await db.flush()
        urunler = {u.id: u for u in (await db.execute(select(StokUrunleri).where(
            StokUrunleri.id.in_({g.urun_id for g in girdiler})))).scalars().all()}
        gecisler: List[Gecis] = []
        for k in sonuc.kalemler:
            g = k.girdi
            db.add(PosSatisKalemleri(satis_id=x.id, hesap_email=y.hesap, urun_id=g.urun_id, ad=g.ad, barkod=g.barkod, birim=g.birim,
                                     adet=g.adet, birim_fiyat=g.birim_fiyat, satir_indirim=k.satir_indirim, indirim=k.indirim, tutar=k.tutar, kdv_orani=g.kdv_orani,
                                     kdv=k.kdv, birim_maliyet=g.birim_maliyet))
            u = urunler[g.urun_id]
            if u.stok_takibi:
                sonra = await stok_degistir(db, y.hesap, u, konum.id, -g.adet, "satis", kisi=y.kisi, eksi_izin=bool(a.eksi_stok),
                                            satis_id=x.id)
                gecisler.append(Gecis(u.id, sonra + g.adet, sonra))
        from services import webhook

        await webhook.olay_yayinla(db, OLAY_SATIS, y.hesap, satis_verisi(x, len(sonuc.kalemler)))
        await db.commit()
    except s.StokHatasi:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        if istemci:
            onceki = (await db.execute(select(PosSatislari).where(PosSatislari.hesap_email == y.hesap,
                                                                  PosSatislari.istemci_kimligi == istemci))).scalars().first()
            if onceki is not None:
                return SatisSonucu(onceki, True, [])
        raise s.StokHatasi("cakisma", None, durum=409)
    await db.refresh(x)
    return SatisSonucu(x, False, gecisler)


def satis_verisi(x: PosSatislari, kalem_sayisi: int) -> Dict[str, Any]:
    """`pos.satis` olay verisi — müşteri adı / alıcı YOK."""
    return {"satis_id": x.id, "no": x.no, "toplam": s.tl(x.toplam), "kdv": s.tl(x.kdv_toplam), "para_birimi": x.para_birimi,
            "kalem_sayisi": kalem_sayisi, "odeme_turu": x.odeme_turu, "konum_id": x.konum_id, "zaman": s.iso(x.zaman)}


async def kalemler(db: AsyncSession, satis_id: int) -> List[PosSatisKalemleri]:
    return list((await db.execute(select(PosSatisKalemleri).where(PosSatisKalemleri.satis_id == satis_id)
                                  .order_by(PosSatisKalemleri.id))).scalars().all())


# ---------------------------------------------------------------------------
# İade ve iptal
# ---------------------------------------------------------------------------
async def iade_yap(db: AsyncSession, y: Yetki, x: PosSatislari, govde: Dict[str, Any]) -> Tuple[PosIadeler, List[Gecis]]:
    if x.durum in ("iade", "iptal"):
        raise s.StokHatasi("iade_edilemez", None, durum=409)
    odeme = govde.get("odeme_turu") or "nakit"
    if odeme not in s.IADE_ODEME_TURLERI:
        raise s.StokHatasi("odeme_turu_gecersiz", "odeme_turu")
    neden = s.bos_ya_da(govde.get("neden"), "neden", 300)
    satirlar = await kalemler(db, x.id)
    harita = {k.id: k for k in satirlar}
    ham = govde.get("kalemler")
    if ham in (None, "hepsi"):
        istek = [(k, k.adet - k.iade_adet) for k in satirlar if k.adet > k.iade_adet]
    else:
        if not isinstance(ham, list) or not ham:
            raise s.StokHatasi("iade_bos", "kalemler")
        istek = []
        for i, r in enumerate(ham):
            if not isinstance(r, dict):
                raise s.StokHatasi("kalem_gecersiz", f"kalemler.{i}")
            k = harita.get(s.tam_sayi(r.get("kalem_id"), f"kalemler.{i}.kalem_id", 1, 2_000_000_000, bos_olabilir=False))
            if k is None:
                raise s.StokHatasi("kalem_yok", f"kalemler.{i}.kalem_id", durum=404)
            adet = s.miktar_coz(r.get("adet"), f"kalemler.{i}.adet", k.birim)
            if adet > k.adet - k.iade_adet:
                raise s.StokHatasi("iade_fazla", f"kalemler.{i}.adet", en_cok=s.miktar_yaz(k.adet - k.iade_adet))
            istek.append((k, adet))
    istek = [(k, a) for k, a in istek if a > 0]
    if not istek:
        raise s.StokHatasi("iade_bos", "kalemler")
    oturum = await acik_oturum(db, y.hesap, x.konum_id)
    if oturum is None and odeme == "nakit":
        raise s.StokHatasi("kasa_kapali", None, durum=409)
    urunler = {u.id: u for u in (await db.execute(select(StokUrunleri).where(StokUrunleri.id.in_({k.urun_id for k, _ in istek})))).scalars().all()}
    try:
        kayit, toplam, gecisler = [], 0, []
        for k, adet in istek:
            tutar = s.iade_tutari(k.tutar, k.adet, k.iade_adet, k.iade_tutar, adet)
            r = await db.execute(update(PosSatisKalemleri).where(PosSatisKalemleri.id == k.id,
                                                                 PosSatisKalemleri.iade_adet + adet <= PosSatisKalemleri.adet)
                                 .values(iade_adet=PosSatisKalemleri.iade_adet + adet, iade_tutar=PosSatisKalemleri.iade_tutar + tutar)
                                 .execution_options(synchronize_session=False))
            if not r.rowcount:
                raise s.StokHatasi("iade_fazla", "kalemler", durum=409)
            kayit.append({"kalem_id": k.id, "urun_id": k.urun_id, "adet": adet, "tutar": tutar})
            toplam += tutar
            u = urunler.get(k.urun_id)
            if u is not None and u.stok_takibi:
                sonra = await stok_degistir(db, y.hesap, u, x.konum_id, adet, "iade", kisi=y.kisi, eksi_izin=True, satis_id=x.id)
                gecisler.append(Gecis(u.id, sonra - adet, sonra))
        iade = PosIadeler(hesap_email=y.hesap, satis_id=x.id, oturum_id=oturum.id if oturum else None, tur="iade", tutar=toplam,
                          odeme_turu=odeme, kalemler=s.json_yaz(kayit), neden=neden, kisi=y.kisi, zaman=s.simdi())
        db.add(iade)
        await db.flush()
        kalan = (await db.execute(select(func.sum(PosSatisKalemleri.adet - PosSatisKalemleri.iade_adet))
                                  .where(PosSatisKalemleri.satis_id == x.id))).scalar() or 0
        await db.execute(update(PosSatislari).where(PosSatislari.id == x.id)
                         .values(iade_toplam=PosSatislari.iade_toplam + toplam, durum="iade" if kalan <= 0 else "kismi_iade")
                         .execution_options(synchronize_session=False))
        await db.commit()
    except s.StokHatasi:
        await db.rollback()
        raise
    await db.refresh(iade)
    await db.refresh(x)
    return iade, gecisler


async def iptal_et(db: AsyncSession, y: Yetki, x: PosSatislari, govde: Dict[str, Any]) -> Tuple[PosIadeler, List[Gecis]]:
    """Satışı iptal eder: yalnız oturumu hâlâ açıkken ve hiç iade yapılmamışsa (aynı gün düzeltme)."""
    if x.durum != "tamamlandi" or x.iade_toplam:
        raise s.StokHatasi("iptal_edilemez", None, durum=409)
    oturum = await acik_oturum(db, y.hesap, x.konum_id)
    if oturum is None or oturum.id != x.oturum_id:
        raise s.StokHatasi("iptal_suresi_gecti", None, durum=409)
    neden = s.bos_ya_da(govde.get("neden"), "neden", 300)
    satirlar = await kalemler(db, x.id)
    urunler = {u.id: u for u in (await db.execute(select(StokUrunleri).where(StokUrunleri.id.in_({k.urun_id for k in satirlar} or {0})))).scalars().all()}
    try:
        r = await db.execute(update(PosSatislari).where(PosSatislari.id == x.id, PosSatislari.durum == "tamamlandi")
                             .values(durum="iptal").execution_options(synchronize_session=False))
        if not r.rowcount:
            raise s.StokHatasi("iptal_edilemez", None, durum=409)
        gecisler = []
        for k in satirlar:
            u = urunler.get(k.urun_id)
            if u is not None and u.stok_takibi:
                sonra = await stok_degistir(db, y.hesap, u, x.konum_id, k.adet, "iptal", kisi=y.kisi, eksi_izin=True, satis_id=x.id)
                gecisler.append(Gecis(u.id, sonra - k.adet, sonra))
        kayit = [{"kalem_id": k.id, "urun_id": k.urun_id, "adet": k.adet, "tutar": k.tutar} for k in satirlar]
        iptal = PosIadeler(hesap_email=y.hesap, satis_id=x.id, oturum_id=oturum.id, tur="iptal", tutar=x.toplam,
                           odeme_turu="nakit" if x.nakit else ("kart" if x.kart else "havale"), kalemler=s.json_yaz(kayit),
                           neden=neden, kisi=y.kisi, zaman=s.simdi())
        db.add(iptal)
        await db.commit()
    except s.StokHatasi:
        await db.rollback()
        raise
    await db.refresh(iptal)
    await db.refresh(x)
    return iptal, gecisler


# ---------------------------------------------------------------------------
# Elle hareket, transfer
# ---------------------------------------------------------------------------
async def elle_hareket(db: AsyncSession, y: Yetki, govde: Dict[str, Any]) -> List[Gecis]:
    tur = govde.get("tur")
    if tur not in s.ELLE_HAREKETLER:
        raise s.StokHatasi("hareket_turu_gecersiz", "tur")
    konum = await konum_bul(db, y.hesap, govde.get("konum_id"))
    a = await ayarlar(db, y.hesap)
    tedarikci_id = None
    if tur == "giris" and govde.get("tedarikci_id") not in (None, ""):
        tedarikci_id = (await tedarikci_bul(db, y.hesap, govde.get("tedarikci_id"))).id
    belge_no = s.bos_ya_da(govde.get("belge_no"), "belge_no", 40)
    aciklama = s.bos_ya_da(govde.get("aciklama"), "aciklama", 300)
    maliyet_guncelle = govde.get("maliyet_guncelle", True) is not False
    ham = govde.get("kalemler")
    if not isinstance(ham, list) or not ham or len(ham) > s.EN_COK_KALEM:
        raise s.StokHatasi("kalemler_gecersiz", "kalemler")
    try:
        gecisler: List[Gecis] = []
        for i, r in enumerate(ham):
            if not isinstance(r, dict):
                raise s.StokHatasi("kalem_gecersiz", f"kalemler.{i}")
            u = await urun_bul(db, y.hesap, r.get("urun_id"))
            if not u.stok_takibi:
                raise s.StokHatasi("stok_takibi_yok", f"kalemler.{i}.urun_id")
            if tur == "duzeltme":
                hedef = s.miktar_coz(r.get("miktar"), f"kalemler.{i}.miktar", u.birim, sifir_olabilir=True)
                mevcut = (await seviyeler(db, [u.id]))[u.id].get(konum.id, 0)
                degisim = hedef - mevcut
                if degisim == 0:
                    continue
            else:
                miktar = s.miktar_coz(r.get("miktar"), f"kalemler.{i}.miktar", u.birim)
                degisim = miktar if tur == "giris" else -miktar
            maliyet = None
            if tur == "giris":
                maliyet = s.kurus(r.get("birim_maliyet"), f"kalemler.{i}.birim_maliyet", bos_olabilir=True)
                if maliyet is not None and maliyet_guncelle:
                    u.alis_fiyati = maliyet
            sonra = await stok_degistir(db, y.hesap, u, konum.id, degisim, tur, kisi=y.kisi,
                                        eksi_izin=bool(a.eksi_stok) or tur == "duzeltme", birim_maliyet=maliyet,
                                        tedarikci_id=tedarikci_id, belge_no=belge_no, aciklama=aciklama)
            gecisler.append(Gecis(u.id, sonra - degisim, sonra))
        await db.commit()
    except s.StokHatasi:
        await db.rollback()
        raise
    return gecisler


async def transfer(db: AsyncSession, y: Yetki, govde: Dict[str, Any]) -> Tuple[str, List[Gecis]]:
    kaynak = await konum_bul(db, y.hesap, govde.get("kaynak_konum_id"), varsayilan=False)
    hedef = await konum_bul(db, y.hesap, govde.get("hedef_konum_id"), varsayilan=False)
    if kaynak.id == hedef.id:
        raise s.StokHatasi("ayni_konum", "hedef_konum_id")
    a = await ayarlar(db, y.hesap)
    aciklama = s.bos_ya_da(govde.get("aciklama"), "aciklama", 300)
    ham = govde.get("kalemler")
    if not isinstance(ham, list) or not ham or len(ham) > s.EN_COK_KALEM:
        raise s.StokHatasi("kalemler_gecersiz", "kalemler")
    kod = secrets.token_hex(6)
    try:
        gecisler: List[Gecis] = []
        for i, r in enumerate(ham):
            if not isinstance(r, dict):
                raise s.StokHatasi("kalem_gecersiz", f"kalemler.{i}")
            u = await urun_bul(db, y.hesap, r.get("urun_id"))
            if not u.stok_takibi:
                raise s.StokHatasi("stok_takibi_yok", f"kalemler.{i}.urun_id")
            miktar = s.miktar_coz(r.get("miktar"), f"kalemler.{i}.miktar", u.birim)
            await stok_degistir(db, y.hesap, u, kaynak.id, -miktar, "transfer_cikis", kisi=y.kisi, eksi_izin=bool(a.eksi_stok),
                                transfer_kodu=kod, aciklama=aciklama)
            await stok_degistir(db, y.hesap, u, hedef.id, miktar, "transfer_giris", kisi=y.kisi, eksi_izin=True,
                                transfer_kodu=kod, aciklama=aciklama)
        await db.commit()
    except s.StokHatasi:
        await db.rollback()
        raise
    return kod, gecisler


# ---------------------------------------------------------------------------
# Sayım
# ---------------------------------------------------------------------------
async def sayim_bul(db: AsyncSession, hesap: str, sayim_id: Any) -> StokSayimlari:
    kimlik = s.tam_sayi(sayim_id, "sayim_id", 1, 2_000_000_000, bos_olabilir=False)
    x = (await db.execute(select(StokSayimlari).where(StokSayimlari.id == kimlik, StokSayimlari.hesap_email == hesap))).scalars().first()
    if x is None:
        raise s.StokHatasi("sayim_yok", "sayim_id", durum=404)
    return x


async def sayim_baslat(db: AsyncSession, y: Yetki, govde: Dict[str, Any]) -> StokSayimlari:
    konum = await konum_bul(db, y.hesap, govde.get("konum_id"))
    acik = (await db.execute(select(StokSayimlari.id).where(StokSayimlari.hesap_email == y.hesap, StokSayimlari.konum_id == konum.id,
                                                            StokSayimlari.durum == "acik"))).first()
    if acik is not None:
        raise s.StokHatasi("sayim_zaten_acik", "konum_id", durum=409, sayim_id=acik[0])
    x = StokSayimlari(hesap_email=y.hesap, konum_id=konum.id, durum="acik", aciklama=s.bos_ya_da(govde.get("aciklama"), "aciklama", 300),
                      baslatan=y.kisi, baslangic=s.simdi())
    db.add(x)
    await db.commit()
    await db.refresh(x)
    return x


async def sayim_kalemi(db: AsyncSession, y: Yetki, x: StokSayimlari, govde: Dict[str, Any]) -> StokSayimKalemleri:
    """Okut-say: `kod` (barkod/SKU) ya da `urun_id`; `ekle` (varsayılan 1) sayılana eklenir, `sayilan` verilirse yerine yazılır."""
    if x.durum != "acik":
        raise s.StokHatasi("sayim_kapali", None, durum=409)
    if govde.get("kod") not in (None, ""):
        u = await kodla_bul(db, y.hesap, govde.get("kod"))
        if u is None:
            raise s.StokHatasi("urun_yok", "kod", durum=404)
    else:
        u = await urun_bul(db, y.hesap, govde.get("urun_id"))
    if not u.stok_takibi:
        raise s.StokHatasi("stok_takibi_yok", "urun_id")
    k = (await db.execute(select(StokSayimKalemleri).where(StokSayimKalemleri.sayim_id == x.id,
                                                           StokSayimKalemleri.urun_id == u.id))).scalars().first()
    if k is None:
        k = StokSayimKalemleri(sayim_id=x.id, hesap_email=y.hesap, urun_id=u.id, sayilan=0)
        db.add(k)
    if govde.get("sayilan") not in (None, ""):
        k.sayilan = s.miktar_coz(govde.get("sayilan"), "sayilan", u.birim, sifir_olabilir=True)
    else:
        k.sayilan = int(k.sayilan or 0) + s.miktar_coz(govde.get("ekle", 1), "ekle", u.birim, eksi_olabilir=True)
        if k.sayilan < 0:
            k.sayilan = 0
    k.updated_at = s.simdi()
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return await sayim_kalemi(db, y, x, govde)
    await db.refresh(k)
    return k


async def sayim_onayla(db: AsyncSession, y: Yetki, x: StokSayimlari, govde: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Gecis]]:
    """Sayılanlar için fark hareketi (`sayim`); `sayilmayanlar_sifir` ise konumda stoku olup sayılmayanlar 0'a çekilir."""
    if x.durum != "acik":
        raise s.StokHatasi("sayim_kapali", None, durum=409)
    sifirla = govde.get("sayilmayanlar_sifir") is True
    satirlar = list((await db.execute(select(StokSayimKalemleri).where(StokSayimKalemleri.sayim_id == x.id))).scalars().all())
    sayilan = {k.urun_id: k for k in satirlar}
    if sifirla:
        for uid, _ in (await db.execute(select(StokSeviyeleri.urun_id, StokSeviyeleri.miktar).where(
                StokSeviyeleri.hesap_email == y.hesap, StokSeviyeleri.konum_id == x.konum_id, StokSeviyeleri.miktar != 0))).all():
            if uid not in sayilan:
                k = StokSayimKalemleri(sayim_id=x.id, hesap_email=y.hesap, urun_id=uid, sayilan=0)
                db.add(k)
                sayilan[uid] = k
    urunler = {u.id: u for u in (await db.execute(select(StokUrunleri).where(StokUrunleri.id.in_(list(sayilan) or [0])))).scalars().all()}
    sev = await seviyeler(db, list(sayilan))
    arti = eksi = deger = 0
    gecisler: List[Gecis] = []
    try:
        for uid, k in sayilan.items():
            u = urunler.get(uid)
            if u is None:
                continue
            mevcut = sev.get(uid, {}).get(x.konum_id, 0)
            fark = int(k.sayilan or 0) - mevcut
            k.sistem, k.fark = mevcut, fark
            if fark:
                await stok_degistir(db, y.hesap, u, x.konum_id, fark, "sayim", kisi=y.kisi, eksi_izin=True, sayim_id=x.id)
                gecisler.append(Gecis(u.id, mevcut, mevcut + fark))
                arti += max(0, fark)
                eksi += max(0, -fark)
                deger += s.yuvarla(u.alis_fiyati, fark, 1000)
        ozet = {"kalem": len(sayilan), "farkli": sum(1 for k in sayilan.values() if k.fark), "fark_arti": s.miktar_yaz(arti),
                "fark_eksi": s.miktar_yaz(eksi), "deger_farki": deger}
        x.durum, x.onaylayan, x.bitis, x.ozet = "onaylandi", y.kisi, s.simdi(), s.json_yaz(ozet)
        await db.commit()
    except s.StokHatasi:
        await db.rollback()
        raise
    return ozet, gecisler


# ---------------------------------------------------------------------------
# Tedarikçi, alıcı
# ---------------------------------------------------------------------------
async def tedarikci_bul(db: AsyncSession, hesap: str, kimlik: Any) -> StokTedarikcileri:
    k = s.tam_sayi(kimlik, "tedarikci_id", 1, 2_000_000_000, bos_olabilir=False)
    t = (await db.execute(select(StokTedarikcileri).where(StokTedarikcileri.id == k, StokTedarikcileri.hesap_email == hesap))).scalars().first()
    if t is None:
        raise s.StokHatasi("tedarikci_yok", "tedarikci_id", durum=404)
    return t


async def alici_bul(db: AsyncSession, hesap: str, kimlik: Any) -> PosAlicilari:
    k = s.tam_sayi(kimlik, "alici_id", 1, 2_000_000_000, bos_olabilir=False)
    a = (await db.execute(select(PosAlicilari).where(PosAlicilari.id == k, PosAlicilari.hesap_email == hesap))).scalars().first()
    if a is None:
        raise s.StokHatasi("alici_yok", "alici_id", durum=404)
    return a


def alici_alanlari(govde: Dict[str, Any], kismi: bool = False) -> Dict[str, Any]:
    alanlar: Dict[str, Any] = {}
    if not kismi or "ad" in govde:
        alanlar["ad"] = s.metin(govde.get("ad"), "ad", 160, zorunlu=True)
    if not kismi or "tur" in govde:
        tur = govde.get("tur") or "bireysel"
        if tur not in s.ALICI_TURLERI:
            raise s.StokHatasi("tur_gecersiz", "tur")
        alanlar["tur"] = tur
    for ad, sinir in (("vergi_dairesi", 80), ("telefon", 32)):
        if not kismi or ad in govde:
            alanlar[ad] = s.bos_ya_da(govde.get(ad), ad, sinir)
    if not kismi or "adres" in govde:
        alanlar["adres"] = s.bos_ya_da(govde.get("adres"), "adres", 500, cok_satir=True)
    if not kismi or "vergi_no" in govde:
        alanlar["vergi_no"] = s.vergi_no_duzelt(govde.get("vergi_no"))
    if not kismi or "eposta" in govde:
        alanlar["eposta"] = s.eposta(govde.get("eposta"))
    return alanlar


def alici_sozlugu(a: PosAlicilari) -> Dict[str, Any]:
    return {"id": a.id, "tur": a.tur, "ad": a.ad, "vergi_dairesi": a.vergi_dairesi, "vergi_no": a.vergi_no, "adres": a.adres,
            "eposta": a.eposta, "telefon": a.telefon}


async def fatura_kes(db: AsyncSession, y: Yetki, x: PosSatislari, govde: Dict[str, Any]) -> PosSatislari:
    """Satıştan (bilgi amaçlı, PDF) fatura: numara + alıcı bilgisi satışa yazılır. e-Arşiv entegrasyonu sonra."""
    if x.durum == "iptal":
        raise s.StokHatasi("iptal_satis", None, durum=409)
    if x.fatura_no:
        raise s.StokHatasi("fatura_zaten_var", None, durum=409, fatura_no=x.fatura_no)
    if govde.get("alici_id") not in (None, ""):
        alici = alici_sozlugu(await alici_bul(db, y.hesap, govde.get("alici_id")))
    else:
        alici = alici_alanlari(govde.get("alici") if isinstance(govde.get("alici"), dict) else {})
        if govde.get("kaydet") is True:
            a = PosAlicilari(hesap_email=y.hesap, created_at=s.simdi(), **alici)
            db.add(a)
            await db.flush()
            alici = alici_sozlugu(a)
            x.alici_id = a.id
    sayac = await _sayac_artir(db, y.hesap, "fatura_sayac")
    x.fatura_no = s.fatura_no(s.tr_gunu().year, sayac)
    x.fatura_at = s.simdi()
    x.fatura_alici = s.json_yaz(alici)
    await db.commit()
    await db.refresh(x)
    return x


# ---------------------------------------------------------------------------
# İçe aktarma (CSV, QR menü)
# ---------------------------------------------------------------------------
async def csv_ice_aktar(db: AsyncSession, y: Yetki, bayt: bytes) -> Dict[str, Any]:
    """Barkod (yoksa SKU) eşleşen ürün güncellenir, eşleşmeyen eklenir; `stok` sütunu varsayılan konumda
    stoku o miktara çeker (düzeltme hareketi). Hatalı satırlar atlanır ve raporlanır."""
    satirlar = s.csv_coz(bayt)
    a = await ayarlar(db, y.hesap)
    oranlar = s.kdv_oranlari(a.kdv_oranlari)
    konum = await varsayilan_konum(db, y.hesap)
    sinir = await modul_ayari(db, y.hesap, "urun_siniri", s.VARSAYILAN_URUN_SINIRI)
    mevcut_sayi = await urun_sayisi(db, y.hesap)
    eklenen = guncellenen = 0
    hatalar: List[Dict[str, Any]] = []
    gecisler: List[Gecis] = []
    for no, ham in enumerate(satirlar, start=2):
        try:
            barkod = s.barkod_duzelt(ham.get("barkod"))
            sku = s.bos_ya_da(ham.get("sku"), "sku", 64)
            u = None
            if barkod:
                u = (await db.execute(select(StokUrunleri).where(StokUrunleri.hesap_email == y.hesap,
                                                                 StokUrunleri.barkod == barkod))).scalars().first()
            if u is None and sku:
                u = (await db.execute(select(StokUrunleri).where(StokUrunleri.hesap_email == y.hesap,
                                                                 StokUrunleri.sku == sku))).scalars().first()
            kayit = urun_alanlari(ham, oranlar, csv_satiri=True, birim_varsayilan=u.birim if u else "adet")
            birim = kayit.get("birim") or (u.birim if u else "adet")
            stok = None
            if (ham.get("stok") or "").strip():
                stok = s.miktar_coz(ham.get("stok"), "stok", birim, sifir_olabilir=True)
            if u is None:
                if mevcut_sayi + eklenen >= sinir:
                    raise s.StokHatasi("urun_siniri", None, sinir=sinir)
                if not kayit.get("barkod"):
                    kayit["barkod"] = await benzersiz_barkod(db, y.hesap)
                async with db.begin_nested():
                    u = StokUrunleri(hesap_email=y.hesap, created_at=s.simdi(), aktif=True,
                                     **{**urun_varsayilanlari(a, oranlar), **kayit})
                    db.add(u)
                    await db.flush()
                eklenen += 1
            else:
                async with db.begin_nested():
                    for k, v in kayit.items():
                        setattr(u, k, v)
                    u.aktif = True
                    await db.flush()
                guncellenen += 1
            if stok is not None and u.stok_takibi:
                mevcut = (await seviyeler(db, [u.id]))[u.id].get(konum.id, 0)
                if stok != mevcut:
                    sonra = await stok_degistir(db, y.hesap, u, konum.id, stok - mevcut, "duzeltme", kisi=y.kisi, eksi_izin=True,
                                                aciklama="CSV")
                    gecisler.append(Gecis(u.id, mevcut, sonra))
        except s.StokHatasi as h:
            hatalar.append({"satir": no, **h.detay()})
        except IntegrityError:
            hatalar.append({"satir": no, "kod": "cakisma"})
    await db.commit()
    await gecisleri_isle(db, y.hesap, gecisler)
    return {"eklenen": eklenen, "guncellenen": guncellenen, "hatalar": hatalar[:100], "hata_sayisi": len(hatalar)}


def urun_varsayilanlari(a: StokAyarlari, oranlar: Sequence[int]) -> Dict[str, Any]:
    kdv = a.varsayilan_kdv if a.varsayilan_kdv in oranlar else oranlar[-1]
    return {"birim": "adet", "kdv_orani": kdv, "alis_fiyati": 0, "stok_takibi": True}


def urun_alanlari(govde: Dict[str, Any], oranlar: Sequence[int], *, kismi: bool = False, csv_satiri: bool = False,
                  birim_varsayilan: str = "adet") -> Dict[str, Any]:
    """Ürün gövdesini doğrular; yalnız verilen alanlar döner (oluştururken eksikler `urun_varsayilanlari`).

    Barkod benzersizliği çağıranda (veritabanı kısıtı da var)."""

    def var(ad: str) -> bool:
        if csv_satiri:
            return str(govde.get(ad) or "").strip() != ""
        return not kismi or ad in govde

    alanlar: Dict[str, Any] = {}
    if csv_satiri or var("ad"):
        alanlar["ad"] = s.metin(govde.get("ad"), "ad", 160, zorunlu=True)
    if var("barkod"):
        alanlar["barkod"] = s.barkod_duzelt(govde.get("barkod"))
    if var("sku"):
        alanlar["sku"] = s.bos_ya_da(govde.get("sku"), "sku", 64)
    if var("kategori"):
        alanlar["kategori"] = s.bos_ya_da(govde.get("kategori"), "kategori", 80)
    if var("birim"):
        alanlar["birim"] = s.birim_duzelt(govde.get("birim"))
    if var("alis_fiyati"):
        alanlar["alis_fiyati"] = s.kurus(govde.get("alis_fiyati"), "alis_fiyati", bos_olabilir=True) or 0
    if csv_satiri or var("satis_fiyati"):
        alanlar["satis_fiyati"] = s.kurus(govde.get("satis_fiyati"), "satis_fiyati")
    if var("kdv_orani") and govde.get("kdv_orani") not in (None, ""):
        alanlar["kdv_orani"] = s.kdv_duzelt(govde.get("kdv_orani"), oranlar)
    birim = alanlar.get("birim") or birim_varsayilan
    if var("kritik_esik"):
        ham = govde.get("kritik_esik")
        alanlar["kritik_esik"] = None if ham in (None, "") else s.miktar_coz(ham, "kritik_esik", birim, sifir_olabilir=True)
    if not csv_satiri:
        if var("stok_takibi") and "stok_takibi" in govde:
            alanlar["stok_takibi"] = s.evet_hayir(govde.get("stok_takibi"), "stok_takibi")
        if var("notlar"):
            alanlar["notlar"] = s.bos_ya_da(govde.get("notlar"), "notlar", 1000, cok_satir=True)
    return alanlar


async def menu_kaynaklari(db: AsyncSession, hesap: str) -> List[Dict[str, Any]]:
    from models.qr_menu import MenuMagazalari, MenuUrunleri

    magazalar = (await db.execute(select(MenuMagazalari).where(MenuMagazalari.hesap_email == hesap).order_by(MenuMagazalari.id))).scalars().all()
    if not magazalar:
        return []
    sayilar = dict((await db.execute(select(MenuUrunleri.magaza_id, func.count(MenuUrunleri.id)).where(
        MenuUrunleri.magaza_id.in_([m.id for m in magazalar])).group_by(MenuUrunleri.magaza_id))).all())
    bagli = set((await db.execute(select(StokUrunleri.menu_urun_id).where(
        StokUrunleri.hesap_email == hesap, StokUrunleri.menu_urun_id.isnot(None)))).scalars().all())
    bagli_sayilar: Dict[int, int] = {}
    if bagli:
        for mid, uid in (await db.execute(select(MenuUrunleri.magaza_id, MenuUrunleri.id).where(MenuUrunleri.id.in_(bagli)))).all():
            bagli_sayilar[mid] = bagli_sayilar.get(mid, 0) + 1
    return [{"id": m.id, "ad": m.ad, "duzen": m.duzen, "slug": m.slug, "urun": int(sayilar.get(m.id, 0)),
             "bagli": bagli_sayilar.get(m.id, 0)} for m in magazalar]


async def menuden_aktar(db: AsyncSession, y: Yetki, magaza_id: Any) -> Dict[str, Any]:
    """QR menü / katalog ürünlerini BAĞLI stok ürünü olarak ekler (zaten bağlı olanlar yalnız ad/fiyat eşitlenir)."""
    from models.qr_menu import MenuKategorileri, MenuMagazalari, MenuUrunleri

    kimlik = s.tam_sayi(magaza_id, "magaza_id", 1, 2_000_000_000, bos_olabilir=False)
    m = (await db.execute(select(MenuMagazalari).where(MenuMagazalari.id == kimlik, MenuMagazalari.hesap_email == y.hesap))).scalars().first()
    if m is None:
        raise s.StokHatasi("magaza_yok", "magaza_id", durum=404)
    a = await ayarlar(db, y.hesap)
    oranlar = s.kdv_oranlari(a.kdv_oranlari)
    kdv = a.varsayilan_kdv if a.varsayilan_kdv in oranlar else oranlar[-1]
    kategoriler = dict((await db.execute(select(MenuKategorileri.id, MenuKategorileri.ad).where(MenuKategorileri.magaza_id == m.id))).all())
    menu_urunleri = (await db.execute(select(MenuUrunleri).where(MenuUrunleri.magaza_id == m.id).order_by(MenuUrunleri.id))).scalars().all()
    mevcut = {u.menu_urun_id: u for u in (await db.execute(select(StokUrunleri).where(
        StokUrunleri.hesap_email == y.hesap, StokUrunleri.menu_urun_id.in_([x.id for x in menu_urunleri] or [0])))).scalars().all()}
    sinir = await modul_ayari(db, y.hesap, "urun_siniri", s.VARSAYILAN_URUN_SINIRI)
    sayi = await urun_sayisi(db, y.hesap)
    eklenen = guncellenen = 0
    for mu in menu_urunleri:
        fiyat = mu.indirimli_fiyat if mu.indirimli_fiyat is not None else mu.fiyat
        u = mevcut.get(mu.id)
        if u is not None:
            u.ad, u.satis_fiyati = mu.ad[:160], int(fiyat or 0)
            guncellenen += 1
            continue
        if sayi + eklenen >= sinir:
            break
        db.add(StokUrunleri(hesap_email=y.hesap, ad=mu.ad[:160], barkod=await benzersiz_barkod(db, y.hesap), birim="adet",
                            kategori=(kategoriler.get(mu.kategori_id) or None), satis_fiyati=int(fiyat or 0), kdv_orani=kdv,
                            menu_urun_id=mu.id, stok_takibi=False, aktif=True, created_at=s.simdi()))
        eklenen += 1
    await db.commit()
    return {"eklenen": eklenen, "guncellenen": guncellenen, "sinir": sinir}


# ---------------------------------------------------------------------------
# Raporlar
# ---------------------------------------------------------------------------
async def donem_raporu(db: AsyncSession, hesap: str, bas: date, bit: date, konum_id: Optional[int]) -> Dict[str, Any]:
    gun_bas, gun_bit = s.gun_araligi(bas, bit)
    kosul = [PosSatislari.hesap_email == hesap, PosSatislari.zaman >= gun_bas, PosSatislari.zaman < gun_bit]
    ikosul = [PosIadeler.hesap_email == hesap, PosIadeler.tur == "iade", PosIadeler.zaman >= gun_bas, PosIadeler.zaman < gun_bit]
    if konum_id:
        kosul.append(PosSatislari.konum_id == konum_id)
        ikosul.append(PosIadeler.satis_id.in_(select(PosSatislari.id).where(PosSatislari.konum_id == konum_id)))
    gunler: Dict[str, Dict[str, int]] = {}

    def gun(an: datetime) -> Dict[str, int]:
        g = s.tr_gunu(an).isoformat()
        return gunler.setdefault(g, {"satis_sayisi": 0, "satis": 0, "iade": 0, "nakit": 0, "kart": 0, "havale": 0, "kdv": 0, "indirim": 0})

    for x in (await db.execute(select(PosSatislari).where(*kosul, PosSatislari.durum != "iptal"))).scalars().all():
        g = gun(x.zaman)
        g["satis_sayisi"] += 1
        g["satis"] += x.toplam
        g["nakit"] += x.nakit
        g["kart"] += x.kart
        g["havale"] += x.havale
        g["kdv"] += x.kdv_toplam
        g["indirim"] += x.satir_indirim + x.toplam_indirim
    for i in (await db.execute(select(PosIadeler).where(*ikosul))).scalars().all():
        g = gun(i.zaman)
        g["iade"] += int(i.tutar or 0)
        g[i.odeme_turu] = g.get(i.odeme_turu, 0) - int(i.tutar or 0)
    satirlar = [{"tarih": k, **v, "net": v["satis"] - v["iade"]} for k, v in sorted(gunler.items())]
    toplam = {a: sum(r[a] for r in satirlar) for a in ("satis_sayisi", "satis", "iade", "net", "nakit", "kart", "havale", "kdv", "indirim")}
    return {"bas": bas.isoformat(), "bit": bit.isoformat(), "konum_id": konum_id, "gunler": satirlar, "toplam": toplam}


async def kar_raporu(db: AsyncSession, hesap: str, bas: date, bit: date, konum_id: Optional[int]) -> Dict[str, Any]:
    """Ürün bazlı kâr: satış matrahı (KDV hariç, iade düşülmüş) − satış anındaki maliyet × net miktar."""
    gun_bas, gun_bit = s.gun_araligi(bas, bit)
    kosul = [PosSatislari.hesap_email == hesap, PosSatislari.zaman >= gun_bas, PosSatislari.zaman < gun_bit, PosSatislari.durum != "iptal"]
    if konum_id:
        kosul.append(PosSatislari.konum_id == konum_id)
    satirlar = (await db.execute(select(PosSatisKalemleri).join(PosSatislari, PosSatislari.id == PosSatisKalemleri.satis_id).where(*kosul))).scalars().all()
    urunler: Dict[int, Dict[str, Any]] = {}
    for k in satirlar:
        net_adet = k.adet - k.iade_adet
        if net_adet <= 0:
            continue
        net_tutar = k.tutar - k.iade_tutar
        net_kdv = k.kdv - s.yuvarla(k.kdv, k.iade_adet, k.adet)
        ciro = net_tutar - net_kdv
        maliyet = s.yuvarla(k.birim_maliyet, net_adet, 1000)
        u = urunler.setdefault(k.urun_id, {"urun_id": k.urun_id, "ad": k.ad, "birim": k.birim, "adet": 0, "ciro": 0, "maliyet": 0})
        u["adet"] += net_adet
        u["ciro"] += ciro
        u["maliyet"] += maliyet
    liste = []
    for u in urunler.values():
        kar = u["ciro"] - u["maliyet"]
        liste.append({**u, "adet": s.miktar_yaz(u["adet"]), "kar": kar,
                      "marj": round(kar * 100 / u["ciro"], 1) if u["ciro"] else None})
    liste.sort(key=lambda r: -r["kar"])
    toplam = {a: sum(r[a] for r in liste) for a in ("ciro", "maliyet", "kar")}
    toplam["marj"] = round(toplam["kar"] * 100 / toplam["ciro"], 1) if toplam["ciro"] else None
    return {"bas": bas.isoformat(), "bit": bit.isoformat(), "konum_id": konum_id, "urunler": liste, "toplam": toplam}


async def stok_degeri(db: AsyncSession, hesap: str, konum_id: Optional[int]) -> Dict[str, Any]:
    kosul = [StokSeviyeleri.hesap_email == hesap]
    if konum_id:
        kosul.append(StokSeviyeleri.konum_id == konum_id)
    satirlar = (await db.execute(select(StokSeviyeleri.urun_id, func.sum(StokSeviyeleri.miktar)).where(*kosul)
                                 .group_by(StokSeviyeleri.urun_id))).all()
    miktarlar = {uid: int(m or 0) for uid, m in satirlar}
    urunler = (await db.execute(select(StokUrunleri).where(StokUrunleri.hesap_email == hesap, StokUrunleri.aktif.is_(True),
                                                           StokUrunleri.stok_takibi.is_(True)).order_by(StokUrunleri.ad))).scalars().all()
    liste = []
    for u in urunler:
        m = miktarlar.get(u.id, 0)
        liste.append({"urun_id": u.id, "ad": u.ad, "barkod": u.barkod, "birim": u.birim, "miktar": s.miktar_yaz(m),
                      "alis_fiyati": u.alis_fiyati, "satis_fiyati": u.satis_fiyati,
                      "maliyet_degeri": s.yuvarla(u.alis_fiyati, max(m, 0), 1000),
                      "satis_degeri": s.yuvarla(u.satis_fiyati, max(m, 0), 1000), "eksi": m < 0})
    toplam = {"maliyet_degeri": sum(r["maliyet_degeri"] for r in liste), "satis_degeri": sum(r["satis_degeri"] for r in liste),
              "urun": len(liste), "eksi": sum(1 for r in liste if r["eksi"])}
    return {"konum_id": konum_id, "urunler": liste, "toplam": toplam}


async def hareketsiz(db: AsyncSession, hesap: str, gun: int) -> Dict[str, Any]:
    """Stoku olup son `gun` günde satılmayan ürünler (en eski satış önce)."""
    esik = s.simdi() - timedelta(days=gun)
    son_satis = dict((await db.execute(select(StokHareketleri.urun_id, func.max(StokHareketleri.zaman)).where(
        StokHareketleri.hesap_email == hesap, StokHareketleri.tur == "satis").group_by(StokHareketleri.urun_id))).all())
    miktarlar = dict((await db.execute(select(StokSeviyeleri.urun_id, func.sum(StokSeviyeleri.miktar)).where(
        StokSeviyeleri.hesap_email == hesap).group_by(StokSeviyeleri.urun_id))).all())
    urunler = (await db.execute(select(StokUrunleri).where(StokUrunleri.hesap_email == hesap, StokUrunleri.aktif.is_(True),
                                                           StokUrunleri.stok_takibi.is_(True)))).scalars().all()
    liste = []
    for u in urunler:
        m = int(miktarlar.get(u.id) or 0)
        son = s.utc(son_satis.get(u.id))
        if m <= 0 or (son is not None and son >= esik):
            continue
        liste.append({"urun_id": u.id, "ad": u.ad, "barkod": u.barkod, "birim": u.birim, "miktar": s.miktar_yaz(m),
                      "son_satis": s.iso(son), "gun": (s.simdi() - son).days if son else None,
                      "maliyet_degeri": s.yuvarla(u.alis_fiyati, m, 1000)})
    liste.sort(key=lambda r: (r["son_satis"] is not None, r["son_satis"] or ""))
    return {"gun": gun, "urunler": liste, "toplam": {"urun": len(liste), "maliyet_degeri": sum(r["maliyet_degeri"] for r in liste)}}


__all__ = [n for n in dir() if not n.startswith("_")]
