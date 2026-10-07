"""Faz 5R — Randevu: veritabanı düzeyindeki işler (router ve zamanlı görev ortak).

* `musaitlik`: sayfa + tür + kişiler + istisnalar + resmî tatiller + mevcut
  randevular → `services.randevu.slotlar`.
* `yerlestir`: rezervasyon / yeniden planlama için KİLİTLİ yer seçimi. Okuma
  işlemi kapatılır, aday kişilerin satırları id sırasıyla `UPDATE … SET kilit =
  kilit + 1` ile kilitlenir (PostgreSQL'de satır kilidi; SQLite'ta yazma kilidi —
  eşzamanlı ikinci istek bekler), müsaitlik kilit içinde yeniden hesaplanır,
  kişi seçilir, boş koltuk bulunur. Çağıran satırı yazıp commit eder; aynı
  `(kisi_id, baslangic, koltuk)` için benzersizlik kısıtı son güvence.
* Bildirimler: ziyaretçiye (7 dil, `.ics` ekli) ve sahibine (`randevu_yeni`,
  `randevu_degisti`, `randevu_iptal` — hesap ekibinde `randevu` iznine genişler).
  Ziyaretçi e-postasındaki yönetim bağlantısı bir yetki belgesi: gönderimden sonra
  bildirim satırlarından silinir (imzalı işlem deseni).
* Hatırlatmalar (zamanlı uç, her tur): `randevu_hatirlatmalari` benzersizliği
  her hatırlatmanın TEK KEZ gitmesini sağlar; geç kalınmışsa yalnız en yakını gider.
* Anonimleştirme: saklama süresi dolan randevuların kişisel alanları silinir
  (panel listesi ve zamanlı tur tetikler).
* CRM: YALNIZ ajansın kendi sayfasındaki randevu aday/toplantı etkinliği olur;
  müşteri randevuları CRM'e karışmaz.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from models.randevu import (
    RandevuHatirlatmalari,
    RandevuIstisnalari,
    RandevuKisileri,
    Randevular,
    RandevuSayfalari,
    RandevuTurleri,
)
from services import randevu as s
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Kural nesneleri
# ---------------------------------------------------------------------------
def tur_kurali(t: RandevuTurleri) -> s.TurKurali:
    return s.TurKurali(
        id=t.id, sure_dk=int(t.sure_dk), adim_dk=int(t.adim_dk or s.adim_varsayilani(int(t.sure_dk))),
        tampon_once_dk=int(t.tampon_once_dk or 0), tampon_sonra_dk=int(t.tampon_sonra_dk or 0),
        en_erken_dk=int(t.en_erken_dk or 0), en_gec_gun=int(t.en_gec_gun or 60),
        gunluk_sinir=t.gunluk_sinir, kapasite=max(1, int(t.kapasite or 1)),
    )


def tur_kisileri(t: RandevuTurleri) -> List[int]:
    return [int(x) for x in (s.json_yukle(t.kisiler, []) or []) if isinstance(x, int) or str(x).isdigit()]


def mevcut(r: Randevular) -> s.Mevcut:
    return s.Mevcut(id=r.id, kisi_id=r.kisi_id, tur_id=r.tur_id, bas=s.utc(r.baslangic), bit=s.utc(r.bitis),
                    dolu_bas=s.utc(r.dolu_bas), dolu_bit=s.utc(r.dolu_bit))


async def aktif_kisiler(db: AsyncSession, sayfa: RandevuSayfalari, t: RandevuTurleri) -> List[RandevuKisileri]:
    """Türe atanmış ve aktif kişiler, türdeki sırayla (öncelik)."""
    idler = tur_kisileri(t)
    if not idler:
        return []
    kayitlar = (await db.execute(
        select(RandevuKisileri).where(RandevuKisileri.sayfa_id == sayfa.id, RandevuKisileri.id.in_(idler),
                                      RandevuKisileri.aktif.is_(True))
    )).scalars().all()
    sozluk = {k.id: k for k in kayitlar}
    return [sozluk[i] for i in idler if i in sozluk]


async def tatil_kumeleri(db: AsyncSession, sayfa: RandevuSayfalari) -> Tuple[Set[date], Set[date]]:
    if not sayfa.tatilde_kapali:
        return set(), set()
    try:
        from services.sla import ayarlari_oku

        ayar = await ayarlari_oku(db)
        return set(ayar.mesai.tatiller), set(ayar.mesai.yarim_gunler)
    except Exception:  # noqa: BLE001 - tatil listesi okunamazsa açık say
        logger.warning("Randevu: tatil listesi okunamadı", exc_info=True)
        return set(), set()


async def takvim_verisi(
    db: AsyncSession, sayfa: RandevuSayfalari, kisiler: Sequence[RandevuKisileri], ilk_gun: date, son_gun: date,
) -> Tuple[List[s.KisiTakvimi], Dict[date, List[List[str]]], Set[date], Set[date]]:
    idler = [k.id for k in kisiler]
    istisnalar = (await db.execute(
        select(RandevuIstisnalari).where(
            RandevuIstisnalari.sayfa_id == sayfa.id, RandevuIstisnalari.tarih >= ilk_gun,
            RandevuIstisnalari.tarih <= son_gun,
        )
    )).scalars().all()
    sayfa_ist: Dict[date, List[List[str]]] = {}
    kisi_ist: Dict[int, Dict[date, List[List[str]]]] = {}
    for i in istisnalar:
        araliklar = s.json_yukle(i.araliklar, []) or []
        if i.kisi_id is None:
            sayfa_ist[i.tarih] = araliklar
        elif i.kisi_id in idler:
            kisi_ist.setdefault(i.kisi_id, {})[i.tarih] = araliklar
    takvimler = [
        s.KisiTakvimi(id=k.id, haftalik=s.json_yukle(k.haftalik, None) or {}, istisnalar=kisi_ist.get(k.id, {}))
        for k in kisiler
    ]
    tatiller, yarim = await tatil_kumeleri(db, sayfa)
    return takvimler, sayfa_ist, tatiller, yarim


async def mevcut_randevular(db: AsyncSession, kisi_idler: Iterable[int], bas: datetime, bit: datetime) -> List[s.Mevcut]:
    idler = list(kisi_idler)
    if not idler:
        return []
    kayitlar = (await db.execute(
        select(Randevular).where(
            Randevular.kisi_id.in_(idler), Randevular.durum == "onayli",
            Randevular.dolu_bas < bit, Randevular.dolu_bit > bas,
        )
    )).scalars().all()
    return [mevcut(r) for r in kayitlar]


async def musaitlik(
    db: AsyncSession, sayfa: RandevuSayfalari, t: RandevuTurleri, aralik_bas: datetime, aralik_bit: datetime,
    haric_id: Optional[int] = None, kisiler: Optional[Sequence[RandevuKisileri]] = None,
) -> List[s.Slot]:
    kural = tur_kurali(t)
    kisiler = list(kisiler) if kisiler is not None else await aktif_kisiler(db, sayfa, t)
    if not kisiler:
        return []
    tz = s.saat_dilimi(sayfa.saat_dilimi)
    ilk_gun = aralik_bas.astimezone(tz).date() - timedelta(days=2)
    son_gun = aralik_bit.astimezone(tz).date() + timedelta(days=1)
    takvimler, sayfa_ist, tatiller, yarim = await takvim_verisi(db, sayfa, kisiler, ilk_gun, son_gun)
    # Gün sınırı sayımı için sahibin yerel günlerinin tamamı; tamponlar için pay.
    pay = timedelta(days=2, minutes=s.TAMPON_EN_COK * 2)
    mevcutlar = await mevcut_randevular(db, [k.id for k in kisiler], aralik_bas - pay, aralik_bit + pay)
    return s.slotlar(
        tur=kural, kisiler=takvimler, tz_adi=sayfa.saat_dilimi, aralik_bas=aralik_bas, aralik_bit=aralik_bit,
        mevcutlar=mevcutlar, simdi_=s.simdi(), sayfa_istisnalari=sayfa_ist, tatiller=tatiller, yarim_gunler=yarim,
        tatilde_kapali=bool(sayfa.tatilde_kapali), haric_id=haric_id,
    )


async def dagilim(db: AsyncSession, tur_id: int, kisi_idler: Iterable[int]) -> Dict[int, s.DagilimBilgisi]:
    idler = list(kisi_idler)
    if not idler:
        return {}
    esik = s.simdi() - timedelta(days=s.DAGILIM_GUN)
    satirlar = (await db.execute(
        select(Randevular.kisi_id, func.count(Randevular.id), func.max(Randevular.created_at))
        .where(Randevular.tur_id == tur_id, Randevular.kisi_id.in_(idler), Randevular.durum == "onayli",
               Randevular.created_at >= esik)
        .group_by(Randevular.kisi_id)
    )).all()
    return {int(k): s.DagilimBilgisi(sayi=int(n or 0), son_atama=s.utc(son)) for k, n, son in satirlar}


@dataclass
class Yer:
    kisi_id: int
    koltuk: int
    kalan: int


async def yerlestir(
    db: AsyncSession, sayfa: RandevuSayfalari, t: RandevuTurleri, bas: datetime,
    haric: Optional[Randevular] = None,
) -> Yer:
    """Kilitli yer seçimi (bkz. modül açıklaması). Müsait değilse RandevuHatasi(409, dolu).

    Döndükten sonra işlem AÇIK ve kilitli: çağıran satırı yazıp commit etmeli
    (ya da hata durumunda rollback).
    """
    kural = tur_kurali(t)
    kisiler = await aktif_kisiler(db, sayfa, t)
    haric_id = haric.id if haric is not None else None
    on = await musaitlik(db, sayfa, t, bas, bas + timedelta(minutes=1), haric_id=haric_id, kisiler=kisiler)
    adaylar = sorted(on[0].kisiler) if on and on[0].bas == bas else []
    if not adaylar:
        raise s.RandevuHatasi("dolu", "baslangic", durum=409)
    # Okuma işlemini kapat: kilit UPDATE'i yeni işlemin İLK ifadesi olsun
    # (SQLite'ta okumadan yazmaya yükselmek beklemeden "database is locked" verir).
    await db.commit()
    for kid in adaylar:
        await db.execute(
            update(RandevuKisileri).where(RandevuKisileri.id == kid)
            .values(kilit=RandevuKisileri.kilit + 1).execution_options(synchronize_session=False)
        )
    kilitli = [k for k in kisiler if k.id in adaylar]
    son = await musaitlik(db, sayfa, t, bas, bas + timedelta(minutes=1), haric_id=haric_id, kisiler=kilitli)
    musait = son[0].kisiler if son and son[0].bas == bas else {}
    if not musait:
        await db.rollback()
        raise s.RandevuHatasi("dolu", "baslangic", durum=409)
    oncelik = [k.id for k in kisiler]
    if haric is not None and haric.kisi_id in musait:
        secilen = haric.kisi_id  # yeniden planlamada mümkünse aynı kişi
    else:
        secilen = s.kisi_sec(t.atama, musait.keys(), oncelik, await dagilim(db, t.id, musait.keys()))
    if secilen is None:
        await db.rollback()
        raise s.RandevuHatasi("dolu", "baslangic", durum=409)
    sorgu = select(Randevular.koltuk).where(
        Randevular.kisi_id == secilen, Randevular.baslangic == bas, Randevular.koltuk.is_not(None),
    )
    if haric_id is not None:
        sorgu = sorgu.where(Randevular.id != haric_id)
    dolu = {int(x) for x in (await db.execute(sorgu)).scalars().all()}
    koltuk = next((i for i in range(kural.kapasite) if i not in dolu), None)
    if koltuk is None:
        await db.rollback()
        raise s.RandevuHatasi("dolu", "baslangic", durum=409)
    return Yer(kisi_id=secilen, koltuk=koltuk, kalan=musait[secilen] - 1)


# ---------------------------------------------------------------------------
# Anonimleştirme
# ---------------------------------------------------------------------------
KISISEL_BOS = {"ad": None, "eposta": None, "telefon": None, "yanitlar": None, "iptal_nedeni": None, "anonim": True}


async def anonimlestir(db: AsyncSession, sayfa: Optional[RandevuSayfalari] = None) -> int:
    """Saklama süresi dolan randevuların kişisel alanlarını siler. Commit ETMEZ; etkilenen satır sayısı.

    Süre randevunun BAŞLANGICINDAN sayılır (geçmiş görüşmenin kaydı süre boyunca durur).
    """
    simdi_ = s.simdi()
    sayfalar = [sayfa] if sayfa is not None else (await db.execute(select(RandevuSayfalari))).scalars().all()
    toplam = 0
    for p in sayfalar:
        sinir = simdi_ - timedelta(days=max(1, int(p.saklama_gun or s.VARSAYILAN_SAKLAMA_GUN)))
        idler = [i for (i,) in (await db.execute(
            select(Randevular.id).where(Randevular.sayfa_id == p.id, Randevular.anonim.is_(False), Randevular.baslangic < sinir)
        )).all()]
        for bas_ in range(0, len(idler), 500):
            parca = idler[bas_:bas_ + 500]
            sonuc = await db.execute(
                update(Randevular).where(Randevular.id.in_(parca)).values(**KISISEL_BOS)
                .execution_options(synchronize_session=False)
            )
            toplam += int(sonuc.rowcount or 0)
            await _bildirimleri_anonimlestir(db, parca)
    return toplam


async def _bildirimleri_anonimlestir(db: AsyncSession, idler: Sequence[int]) -> None:
    """Randevuya bağlı bildirim kayıtları da ad / e-posta / telefon / zaman taşıyor: ziyaretçiye
    giden e-posta kayıtları silinir, sahibine gidenlerin başlığı sadeleşir, gövdesi boşalır."""
    from models.notifications import Notifications

    kosul = (Notifications.ref_type == "randevular", Notifications.ref_id.in_(list(idler)))
    await db.execute(delete(Notifications).where(*kosul, Notifications.event_type == ZIYARETCI_OLAYI)
                     .execution_options(synchronize_session=False))
    await db.execute(update(Notifications).where(*kosul)
                     .values(title="Randevu (kişisel bilgiler saklama süresi dolunca silindi)", body=None)
                     .execution_options(synchronize_session=False))


# ---------------------------------------------------------------------------
# Ortak görünüm verisi
# ---------------------------------------------------------------------------
@dataclass
class Baglam:
    sayfa: RandevuSayfalari
    tur: RandevuTurleri
    kisi: Optional[RandevuKisileri]


async def baglam(db: AsyncSession, r: Randevular) -> Optional[Baglam]:
    p = (await db.execute(select(RandevuSayfalari).where(RandevuSayfalari.id == r.sayfa_id))).scalars().first()
    t = (await db.execute(select(RandevuTurleri).where(RandevuTurleri.id == r.tur_id))).scalars().first()
    if p is None or t is None:
        return None
    k = (await db.execute(select(RandevuKisileri).where(RandevuKisileri.id == r.kisi_id))).scalars().first()
    return Baglam(p, t, k)


def ics_etkinligi(b: Baglam, r: Randevular, dil: str, iptal: bool = False) -> s.IcsEtkinligi:
    konum = s.konum_metni(b.tur.konum_turu, r.konum, dil, r.telefon)
    aciklama_parca = [b.tur.ad]
    if r.konum and b.tur.konum_turu in ("jitsi", "baglanti"):
        aciklama_parca.append(r.konum)
    if not iptal and r.uid:
        aciklama_parca.append(s.yonetim_adresi(s.yonetim_jetonu(r.id, r.uid)))
    return s.IcsEtkinligi(
        uid=r.uid, bas=s.utc(r.baslangic), bit=s.utc(r.bitis),
        baslik=f"{b.tur.ad} — {b.sayfa.baslik}" if r.ad is None else f"{b.tur.ad}: {b.sayfa.baslik} / {r.ad}",
        aciklama="\n".join(aciklama_parca), konum=konum,
        adres=r.konum if b.tur.konum_turu in ("jitsi", "baglanti") and r.konum else "",
        sira_no=int(r.sira_no or 0), iptal=iptal,
        duzenleyen_eposta=(b.kisi.eposta if b.kisi else "") or "", duzenleyen_ad=(b.kisi.ad if b.kisi else b.sayfa.baslik),
        katilimci_eposta=r.eposta or "", katilimci_ad=r.ad or "",
    )


def takvim_baglantilari(b: Baglam, r: Randevular, dil: str) -> Dict[str, str]:
    konum = s.konum_metni(b.tur.konum_turu, r.konum, dil, r.telefon)
    baslik = f"{b.tur.ad} — {b.sayfa.baslik}"
    aciklama = s.yonetim_adresi(s.yonetim_jetonu(r.id, r.uid))
    jeton = s.yonetim_jetonu(r.id, r.uid)
    return {
        "google": s.google_takvim_adresi(baslik, s.utc(r.baslangic), s.utc(r.bitis), aciklama, konum),
        "outlook": s.outlook_takvim_adresi(baslik, s.utc(r.baslangic), s.utc(r.bitis), aciklama, konum),
        "ics": f"{s.site_adresi()}/api/v1/randevu/islem/{jeton}/takvim.ics",
    }


# ---------------------------------------------------------------------------
# Bildirimler
# ---------------------------------------------------------------------------
ZIYARETCI_OLAYI = "randevu_ziyaretci"  # katalog dışı: yalnız e-posta (matris yok, push yok)


async def _ziyaretciye(db: AsyncSession, b: Baglam, r: Randevular, tur: str, onceki: Optional[datetime] = None,
                       neden: Optional[str] = None) -> None:
    if not r.eposta:
        return
    from services.notify import dispatch

    dil = r.dil if r.dil in s.DILLER else b.sayfa.dil
    tz = r.ziyaretci_tz or b.sayfa.saat_dilimi
    jeton = s.yonetim_jetonu(r.id, r.uid)
    yonet = s.yonetim_adresi(jeton)
    takvim = takvim_baglantilari(b, r, dil) if tur != "iptal" else {}
    konu, govde = s.eposta_govdesi(
        tur=tur, dil=dil, ad=r.ad or "", sayfa=b.sayfa.baslik, tur_adi=b.tur.ad,
        zaman=s.zaman_yaz(r.baslangic, tz, dil), sure=int(b.tur.sure_dk),
        konum=s.konum_metni(b.tur.konum_turu, r.konum, dil, r.telefon), kiminle=b.kisi.ad if b.kisi else "",
        yonet_adresi=yonet if tur != "iptal" else None, google=takvim.get("google"), outlook=takvim.get("outlook"),
        onceki=s.zaman_yaz(onceki, tz, dil) if onceki else None, neden=neden,
        yeni_randevu=s.sayfa_adresi(b.sayfa.slug, b.tur.slug) if tur == "iptal" else None,
    )
    ekler = []
    if tur != "hatirlatma":
        yontem = "CANCEL" if tur == "iptal" else "REQUEST"
        ekler.append({
            "dosya_adi": "randevu.ics",
            "icerik": s.ics_uret([ics_etkinligi(b, r, dil, iptal=tur == "iptal")], yontem),
            "tur": f"text/calendar; method={yontem}; charset=UTF-8",
        })
    # Faz 4L: sayfanın sahibinde marka teması açıksa HTML sürümünde marka başlığı (logo + ana renk).
    from services.marka import eposta_eki

    ek = await eposta_eki(db, b.sayfa.hesap_email, konu, govde, {"ekler": ekler} if ekler else None)
    satirlar = await dispatch(
        db, event_type=ZIYARETCI_OLAYI, title=konu, body=govde,
        recipients=[{"email": r.eposta, "role": "client"}],
        link=None, ref_type="randevular", ref_id=r.id, eposta_ek=ek,
    )
    # Ziyaretçi bir panel kullanıcısı değil: panel içi kopyası tutulmaz (yalnız e-posta kaydı kalır).
    # Yönetim bağlantısı bir yetki belgesi: kalıcı bildirim kaydında durmasın.
    degisti = False
    for satir in list(satirlar):
        if getattr(satir, "channel", None) == "inapp":
            await db.delete(satir)
            satirlar.remove(satir)
            degisti = True
    for satir in satirlar:
        for alan in ("body", "title"):
            deger = getattr(satir, alan, None)
            if deger and jeton in deger:
                setattr(satir, alan, deger.replace(yonet, "…").replace(jeton, "…"))
                degisti = True
    if degisti:
        await db.commit()


async def _sahibine(db: AsyncSession, b: Baglam, r: Randevular, tur: str, onceki: Optional[datetime] = None) -> None:
    from services import notify

    olay = {"onay": "randevu_yeni", "yeniden": "randevu_degisti", "iptal": "randevu_iptal"}[tur]
    tz = b.sayfa.saat_dilimi
    zaman = s.zaman_yaz(r.baslangic, tz, "tr")
    ad = r.ad or "—"
    if tur == "onay":
        baslik = f"Yeni randevu: {ad} — {b.tur.ad}, {zaman}"
    elif tur == "yeniden":
        baslik = f"Randevu yeniden planlandı: {ad} — {b.tur.ad}, {zaman}"
    else:
        kim = "ziyaretçi" if r.iptal_eden == "ziyaretci" else "siz"
        baslik = f"Randevu iptal edildi ({kim}): {ad} — {b.tur.ad}, {zaman}"
    satirlar = [
        f"Görüşme: {b.tur.ad} ({b.tur.sure_dk} dk)",
        f"Zaman: {zaman}",
    ]
    if onceki:
        satirlar.append(f"Önceki zaman: {s.zaman_yaz(onceki, tz, 'tr')}")
    satirlar += [
        f"Kiminle: {b.kisi.ad if b.kisi else '—'}",
        f"Konum: {s.konum_metni(b.tur.konum_turu, r.konum, 'tr', r.telefon)}",
        f"Ad: {ad}", f"E-posta: {r.eposta or '—'}", f"Telefon: {r.telefon or '—'}",
    ]
    yanitlar = s.json_yukle(r.yanitlar, {}) or {}
    for soru in s.json_yukle(b.tur.sorular, []) or []:
        if soru.get("id") in yanitlar:
            deger = yanitlar[soru["id"]]
            satirlar.append(f"{soru.get('etiket')}: {'✓' if deger is True else deger}")
    if r.iptal_nedeni and tur == "iptal":
        satirlar.append(f"Neden: {r.iptal_nedeni}")
    govde = "\n".join(satirlar)
    baslik, govde = await notify.render(db, olay, baslik, govde, {
        "ad": ad, "tur": b.tur.ad, "zaman": zaman, "eposta": r.eposta or "", "sayfa": b.sayfa.baslik,
    })
    if b.sayfa.hesap_email:
        alicilar = [{"email": b.sayfa.hesap_email, "role": "client"}]
        baglanti = "/client?sekme=randevu"
        if b.kisi and b.kisi.eposta and b.kisi.eposta != b.sayfa.hesap_email:
            alicilar.append({"email": b.kisi.eposta, "role": "client"})
    else:
        alicilar = await notify.admin_recipients(db)
        baglanti = "/admin?sekme=randevu"
        if b.kisi and b.kisi.eposta and all(a["email"] != b.kisi.eposta for a in alicilar):
            alicilar.append({"email": b.kisi.eposta, "role": "admin"})
    ekler = []
    if tur != "iptal":
        ekler.append({"dosya_adi": "randevu.ics", "icerik": s.ics_uret([ics_etkinligi(b, r, "tr")], "PUBLISH"),
                      "tur": "text/calendar; method=PUBLISH; charset=UTF-8"})
    await notify.dispatch(
        db, event_type=olay, title=baslik, body=govde, recipients=alicilar, link=baglanti,
        ref_type="randevular", ref_id=r.id, eposta_ek={"ekler": ekler} if ekler else None,
    )


async def bildir(randevu_id: int, tur: str, onceki: Optional[datetime] = None, sahibine: bool = True,
                 ziyaretciye: bool = True) -> None:
    """Yanıttan sonra (arka plan) ziyaretçiye ve sahibine bildirim. Hatalar yutulur."""
    try:
        from core.database import db_manager

        if not db_manager.async_session_maker:
            return
        async with db_manager.async_session_maker() as db:
            r = (await db.execute(select(Randevular).where(Randevular.id == randevu_id))).scalars().first()
            if r is None:
                return
            b = await baglam(db, r)
            if b is None:
                return
            if ziyaretciye:
                try:
                    await _ziyaretciye(db, b, r, tur, onceki=onceki, neden=r.iptal_nedeni if tur == "iptal" else None)
                except Exception:  # noqa: BLE001
                    logger.exception("Randevu: ziyaretçi e-postası gönderilemedi (%s)", randevu_id)
            if sahibine:
                try:
                    await _sahibine(db, b, r, tur, onceki=onceki)
                except Exception:  # noqa: BLE001
                    logger.exception("Randevu: sahip bildirimi gönderilemedi (%s)", randevu_id)
    except Exception:  # noqa: BLE001 - bildirim rezervasyonu bozmasın
        logger.exception("Randevu bildirimi başarısız (%s)", randevu_id)


# ---------------------------------------------------------------------------
# Hatırlatmalar (zamanlı görev)
# ---------------------------------------------------------------------------
async def hatirlatmalari_atla(db: AsyncSession, r: Randevular, sayfa: RandevuSayfalari) -> None:
    """Yeniden planlamada: eski hatırlatma kayıtları silinir, zamanı ŞİMDİDEN geçmiş
    olanlar "atlandı" yazılır (yeni zamana göre yalnız gelecekteki hatırlatmalar gider)."""
    from sqlalchemy import delete

    await db.execute(delete(RandevuHatirlatmalari).where(RandevuHatirlatmalari.randevu_id == r.id))
    simdi_ = s.simdi()
    for dk in s.hatirlatmalar(sayfa.hatirlatmalar):
        if s.utc(r.baslangic) - timedelta(minutes=dk) <= simdi_:
            db.add(RandevuHatirlatmalari(randevu_id=r.id, dakika=dk, durum="atlandi", zaman=simdi_))


async def _talep_et(db: AsyncSession, randevu_id: int, dakika: int, durum: str) -> bool:
    """Hatırlatmayı sahiplen (benzersiz satır). Başka tur aldıysa False."""
    db.add(RandevuHatirlatmalari(randevu_id=randevu_id, dakika=dakika, durum=durum, zaman=s.simdi()))
    try:
        await db.commit()
        return True
    except IntegrityError:
        await db.rollback()
        return False


async def hatirlatmalari_gonder(db: AsyncSession) -> Dict[str, Any]:
    simdi_ = s.simdi()
    en_uzak = max(s.HATIRLATMA_SECENEKLERI)
    satirlar = (await db.execute(
        select(Randevular, RandevuSayfalari)
        .join(RandevuSayfalari, RandevuSayfalari.id == Randevular.sayfa_id)
        .where(Randevular.durum == "onayli", Randevular.anonim.is_(False),
               Randevular.baslangic > simdi_, Randevular.baslangic <= simdi_ + timedelta(minutes=en_uzak),
               RandevuSayfalari.aktif.is_(True))
        .order_by(Randevular.baslangic)
        .limit(500)
    )).all()
    # Önce düz veriye çevir: talep (claim) satırındaki geri alma ORM nesnelerini düşürür.
    adaylar = [
        (r.id, s.utc(r.baslangic), s.utc(r.created_at) or simdi_, s.hatirlatmalar(p.hatirlatmalar))
        for r, p in satirlar
    ]
    gonderilen = atlanan = 0
    for randevu_id, bas, olusma, dakikalar in adaylar:
        vadesi_gelen = sorted(
            dk for dk in dakikalar
            if bas - timedelta(minutes=dk) <= simdi_ and olusma <= bas - timedelta(minutes=dk)
        )
        if not vadesi_gelen:
            continue
        en_yakin = vadesi_gelen[0]
        gonder = await _talep_et(db, randevu_id, en_yakin, "gonderildi")
        for dk in vadesi_gelen[1:]:
            if await _talep_et(db, randevu_id, dk, "atlandi"):
                atlanan += 1
        if not gonder:
            continue
        try:
            r = (await db.execute(select(Randevular).where(Randevular.id == randevu_id))).scalars().first()
            b = await baglam(db, r) if r is not None else None
            if b is not None:
                await _ziyaretciye(db, b, r, "hatirlatma")
                gonderilen += 1
        except Exception:  # noqa: BLE001
            logger.exception("Randevu hatırlatması gönderilemedi (%s)", randevu_id)
    anonim = await anonimlestir(db)
    await db.commit()  # 0 satırda da: açık yazma işlemi (SQLite kilidi) kalmasın
    return {"gonderilen": gonderilen, "atlanan": atlanan, "anonimlestirilen": anonim}


# ---------------------------------------------------------------------------
# CRM (yalnız ajansın kendi sayfası)
# ---------------------------------------------------------------------------
async def crm_isle(db: AsyncSession, b: Baglam, r: Randevular) -> Optional[int]:
    if b.sayfa.hesap_email:
        return None  # müşteri randevuları CRM'e karışmaz (4K kararı)
    from models.crm import CrmAktiviteler
    from services import crm

    try:
        yanitlar = s.json_yukle(r.yanitlar, {}) or {}
        sorular = {q.get("id"): q.get("etiket") for q in (s.json_yukle(b.tur.sorular, []) or [])}
        mesaj = "\n".join(f"{sorular.get(k, k)}: {'✓' if v is True else v}" for k, v in yanitlar.items()) or None
        zaman = s.zaman_yaz(r.baslangic, b.sayfa.saat_dilimi, "tr")
        sonuc = await crm.kayit_isle(db, crm.TalepGirdisi(
            tablo="randevular", kayit_id=r.id, ad=r.ad, email=r.eposta, telefon=r.telefon,
            konu=f"Randevu: {b.tur.ad}", mesaj=mesaj, kaynak="form",
            kaynak_ham=f"randevu:{b.sayfa.slug}/{b.tur.slug}", ek_veri={"randevu": r.uid, "zaman": s.iso(r.baslangic)},
        ))
        if not sonuc:
            return None
        db.add(CrmAktiviteler(
            aday_id=sonuc["aday_id"], tur="toplanti", olay="randevu",
            veri=s.json_yaz({"randevu_id": r.id, "tur": b.tur.slug, "baslangic": s.iso(r.baslangic)}),
            metin=f"{b.tur.ad} ({b.tur.sure_dk} dk) — {zaman}", yapan="sistem", zaman=s.simdi(),
        ))
        await db.flush()
        await db.run_sync(lambda ses: crm.puani_yenile_sync(ses.connection(), sonuc["aday_id"]))
        r.crm_aday_id = sonuc["aday_id"]
        await db.commit()
        return sonuc["aday_id"]
    except Exception:  # noqa: BLE001 - CRM hatası rezervasyonu bozmasın
        logger.exception("Randevu CRM'e aktarılamadı (%s)", r.id)
        await db.rollback()
        return None


async def crm_arka_plan(randevu_id: int) -> None:
    try:
        from core.database import db_manager

        if not db_manager.async_session_maker:
            return
        async with db_manager.async_session_maker() as db:
            r = (await db.execute(select(Randevular).where(Randevular.id == randevu_id))).scalars().first()
            if r is None:
                return
            b = await baglam(db, r)
            if b is not None:
                await crm_isle(db, b, r)
    except Exception:  # noqa: BLE001
        logger.exception("Randevu CRM işi başarısız (%s)", randevu_id)


# ---------------------------------------------------------------------------
# ICS besleme (abonelik)
# ---------------------------------------------------------------------------
async def besleme_ics(db: AsyncSession, sayfa: RandevuSayfalari, kisi_id: Optional[int] = None) -> str:
    simdi_ = s.simdi()
    sorgu = select(Randevular).where(
        Randevular.sayfa_id == sayfa.id, Randevular.durum == "onayli",
        Randevular.baslangic >= simdi_ - timedelta(days=60), Randevular.baslangic <= simdi_ + timedelta(days=400),
    )
    if kisi_id is not None:
        sorgu = sorgu.where(Randevular.kisi_id == kisi_id)
    kayitlar = (await db.execute(sorgu.order_by(Randevular.baslangic).limit(2000))).scalars().all()
    turler = {t.id: t for t in (await db.execute(select(RandevuTurleri).where(RandevuTurleri.sayfa_id == sayfa.id))).scalars().all()}
    kisiler = {k.id: k for k in (await db.execute(select(RandevuKisileri).where(RandevuKisileri.sayfa_id == sayfa.id))).scalars().all()}
    etkinlikler = []
    for r in kayitlar:
        t = turler.get(r.tur_id)
        if t is None:
            continue
        b = Baglam(sayfa, t, kisiler.get(r.kisi_id))
        e = ics_etkinligi(b, r, sayfa.dil)
        # Sahibin takvimi: başlıkta ziyaretçinin adı ve kişi, açıklamada iletişim.
        e.baslik = f"{t.ad}: {r.ad or '—'}" + (f" ({b.kisi.ad})" if b.kisi and len(kisiler) > 1 else "")
        iletisim = [x for x in (r.eposta, r.telefon) if x]
        e.aciklama = "\n".join([t.ad] + iletisim + ([r.konum] if r.konum and t.konum_turu in ("jitsi", "baglanti") else []))
        etkinlikler.append(e)
    return s.ics_uret(etkinlikler, "PUBLISH", takvim_adi=f"{sayfa.baslik} — randevular", an=simdi_)


__all__ = [
    "musaitlik", "yerlestir", "anonimlestir", "bildir", "hatirlatmalari_gonder", "hatirlatmalari_atla",
    "crm_isle", "crm_arka_plan", "besleme_ics", "tur_kurali", "tur_kisileri", "aktif_kisiler", "baglam",
    "takvim_baglantilari", "ics_etkinligi", "Yer", "Baglam",
]
