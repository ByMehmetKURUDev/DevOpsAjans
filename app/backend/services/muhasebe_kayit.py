"""Faz 6M — Ön muhasebe: veritabanı işleri (bakiye, cari, raporlar, tekrarlar, otomatik yansıma, bütçe).

Kurallar `services/muhasebe.py`'de; uçlar `routers/muhasebe.py`'de. Çağıran commit eder (aksi yazılmadıkça).

Otomatik yansıma (eşitleme)
---------------------------
Kaynak başına "beklenen" kayıtlar hesaplanır ve defterdeki ETKİN yansımalarla karşılaştırılır:

* yeni kaynak kaydı → yeni hareket (`kaynak_id` = "<ref>#<sürüm>"; (kapsam, kaynak, kaynak_id) benzersiz →
  iki eşitleme aynı anda koşsa da tek kayıt — eklemeler SAVEPOINT içinde, çakışan atlanır),
* kaynak silindi / iptal edildi / artık geçerli değil → TERS KAYIT (aslının eksisi, "~ters" ekli kimlik) ve
  aslına `ters_kayit_id`,
* tutar / tür / para birimi / KDV değişti → ters kayıt + yeni sürüm.

Aktarım kapatılınca var olan yansımalara dokunulmaz (yeni yansıma üretilmez; bekleyen öneriler silinir). Başlangıç
tarihinden eski kaynak kayıtları alınmaz; zaten yansıtılmış olanlar ise pencere dışında kalsa da izlenir (başlangıç
ileri alınınca eski kayıtlar ters çevrilmez).

Otomatik mi, onaylı mı? Kaynak ayarındaki `onay` (varsayılanı `s.AKTARIM_ONAY_VARSAYILAN`): açıksa yeni/değişen
kayıt deftere değil `muhasebe_oneriler`e yazılır; kullanıcı onaylayınca (`oneri_onayla`) aynı kaynak kimliğiyle
harekete çevrilir — benzersizlik aynı, iki kez sayılmaz. Ödeme kaydı olmadan "ödendi" işaretlenen fatura (`fatura`)
her zaman öneridir. Onaylanmış kayıt da kaynağı değişince/silinince ters çevrilir; yeni sürümü yine öneri olur.

Kaynaklar: ajans → `odeme` (müşterilerden gelen ödemeler — Lemon Squeezy / Shopier / havale / elden ödeme kayıtları;
ödemesi kaydedilmemiş "ödendi" faturalar `fatura`); müşteri → `odeme` (ajansa ödediği faturalar: GİDER, kategori
"yazılım ve abonelikler"), `pos` (kapanmış kasa oturumu: nakit / kart / havale ayrı hesaba), `hukuk` (masraflar;
müvekkil avansından karşılananlar işletme gideri sayılmaz, alınmaz), `saha` (tamamlanan iş emrinin tutarı: işçilik +
malzeme + KDV; hedef hesap yoksa saha müşterisinin carisine vadeli alacak).
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from models.muhasebe import (
    MuhasebeAyarlari,
    MuhasebeButceAsimlari,
    MuhasebeButceler,
    MuhasebeCariler,
    MuhasebeEkleri,
    MuhasebeGecikmeIzleri,
    MuhasebeHareketleri,
    MuhasebeHesaplari,
    MuhasebeKategorileri,
    MuhasebeOneriler,
    MuhasebeTekrarlar,
)
from services import muhasebe as s
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

OLAY_BUTCE = "muhasebe.butce_asildi"
OLAY_GECIKME = "muhasebe.alacak_gecikti"
#: Bildirim türü (panel + açık kanallar): bütçe aşıldı (ajansta yöneticilere, müşteride hesaba ve `muhasebe` izinli üyelere).
BILDIRIM_BUTCE = "muhasebe_butce"
H = MuhasebeHareketleri


# ---------------------------------------------------------------------------
# Ayarlar ve kategoriler
# ---------------------------------------------------------------------------
async def ayar_satiri(db: AsyncSession, kapsam: str) -> Optional[MuhasebeAyarlari]:
    return (await db.execute(select(MuhasebeAyarlari).where(MuhasebeAyarlari.kapsam == kapsam))).scalars().first()


async def ayar_al(db: AsyncSession, kapsam: str, hesap: Optional[str]) -> MuhasebeAyarlari:
    """Satır yoksa açar (flush; eşzamanlı ilk açılışta benzersiz kısıt → var olan okunur)."""
    a = await ayar_satiri(db, kapsam)
    if a is not None:
        return a
    a = MuhasebeAyarlari(kapsam=kapsam, hesap_email=hesap, para_birimi="TRY", uyari_yuzde=80, created_at=s.simdi())
    try:
        async with db.begin_nested():
            db.add(a)
    except IntegrityError:
        a = await ayar_satiri(db, kapsam)
    return a  # type: ignore[return-value]


def aktarim_ayarlari(a: Optional[MuhasebeAyarlari], kapsam: str) -> Dict[str, Dict[str, Any]]:
    """Kapsama göre kaynaklar (ajans: odeme; müşteri: pos, hukuk, saha) + varsayılanlar."""
    kaynaklar = s.AJANS_AKTARIMLARI if kapsam == s.AJANS_KAPSAMI else s.MUSTERI_AKTARIMLARI
    ham = s.json_yukle(a.aktarim if a else None, {}) or {}
    sonuc: Dict[str, Dict[str, Any]] = {}
    for k in kaynaklar:
        d = ham.get(k) if isinstance(ham.get(k), dict) else {}
        satir: Dict[str, Any] = {"acik": bool(d.get("acik")), "baslangic": d.get("baslangic"),
                                 "onay": d["onay"] if isinstance(d.get("onay"), bool) else s.AKTARIM_ONAY_VARSAYILAN[k]}
        for alan in s.AKTARIM_HESAPLARI[k]:
            satir[alan] = d.get(alan) if isinstance(d.get(alan), int) else None
        sonuc[k] = satir
    return sonuc


async def kategorileri_tohumla(db: AsyncSession, kapsam: str, hesap: Optional[str]) -> int:
    """Varsayılan Türkçe set — ilk açılışta BİR kez (silinen varsayılan geri gelmez; "varsayılanları geri yükle"
    ayrı uç). Eklenen sayısı."""
    a = await ayar_al(db, kapsam, hesap)
    if a.kategoriler_tohumlandi:
        return 0
    eklenen = await varsayilanlari_ekle(db, kapsam, hesap)
    a.kategoriler_tohumlandi = True
    return eklenen


async def varsayilanlari_ekle(db: AsyncSession, kapsam: str, hesap: Optional[str]) -> int:
    var = {(k.tur, k.anahtar) for k in (await db.execute(select(MuhasebeKategorileri).where(
        MuhasebeKategorileri.kapsam == kapsam))).scalars().all()}
    adlar = {(t, ad) for t, ad in (await db.execute(select(MuhasebeKategorileri.tur, MuhasebeKategorileri.ad).where(
        MuhasebeKategorileri.kapsam == kapsam))).all()}
    eklenen = 0
    for i, (tur, anahtar, ad, renk) in enumerate(s.VARSAYILAN_KATEGORILER):
        if (tur, anahtar) in var or (tur, ad) in adlar:
            continue
        db.add(MuhasebeKategorileri(kapsam=kapsam, hesap_email=hesap, tur=tur, ad=ad, anahtar=anahtar, renk=renk,
                                    sira=i, created_at=s.simdi()))
        eklenen += 1
    await db.flush()
    return eklenen


async def kategori_anahtarla(db: AsyncSession, kapsam: str, hesap: Optional[str], anahtar: str) -> Optional[int]:
    """Otomatik yansımanın kategorisi: anahtarlı kategori (yoksa açılır; adı kullanıcıda varsa o satır)."""
    tur = s.KATEGORI_TURU.get(anahtar)
    if not tur:
        return None
    k = (await db.execute(select(MuhasebeKategorileri).where(
        MuhasebeKategorileri.kapsam == kapsam, MuhasebeKategorileri.tur == tur, MuhasebeKategorileri.anahtar == anahtar)
    )).scalars().first()
    if k is not None:
        return k.id
    ad = s.KATEGORI_ADLARI[anahtar]
    k = (await db.execute(select(MuhasebeKategorileri).where(
        MuhasebeKategorileri.kapsam == kapsam, MuhasebeKategorileri.tur == tur, MuhasebeKategorileri.ad == ad))).scalars().first()
    if k is not None:
        return k.id
    k = MuhasebeKategorileri(kapsam=kapsam, hesap_email=hesap, tur=tur, ad=ad, anahtar=anahtar,
                             renk=s.KATEGORI_RENGI.get(anahtar), sira=100, created_at=s.simdi())
    try:
        async with db.begin_nested():
            db.add(k)
    except IntegrityError:
        return None
    return k.id


# ---------------------------------------------------------------------------
# Bakiyeler
# ---------------------------------------------------------------------------
async def hesap_bakiyeleri(db: AsyncSession, kapsam: str, tarih: Optional[date] = None) -> Dict[int, int]:
    """Hesap → hareket etkisi toplamı (açılış HARİÇ; `tarih` verilirse o gün dahil)."""
    kosul = [H.kapsam == kapsam]
    if tarih:
        kosul.append(H.tarih <= tarih)
    cikis = case((H.tur.in_(("gelir", "tahsilat")), H.tutar), (H.tur.in_(("gider", "odeme", "virman")), -H.tutar), else_=0)
    sonuc: Dict[int, int] = {}
    for hid, toplam in (await db.execute(select(H.hesap_id, func.sum(cikis)).where(*kosul, H.hesap_id.isnot(None))
                                         .group_by(H.hesap_id))).all():
        sonuc[int(hid)] = sonuc.get(int(hid), 0) + int(toplam or 0)
    for hid, toplam in (await db.execute(select(H.hedef_hesap_id, func.sum(func.coalesce(H.hedef_tutar, H.tutar))).where(
            *kosul, H.tur == "virman", H.hedef_hesap_id.isnot(None)).group_by(H.hedef_hesap_id))).all():
        sonuc[int(hid)] = sonuc.get(int(hid), 0) + int(toplam or 0)
    return sonuc


def _cari_ifadesi():
    """Cari bakiyesine etki (borç − alacak): vadeli satış +, vadeli alış −, tahsilat −, cariye ödeme +."""
    return case(
        (and_(H.tur == "gelir", H.hesap_id.is_(None)), H.tutar),
        (and_(H.tur == "gider", H.hesap_id.is_(None)), -H.tutar),
        (H.tur == "tahsilat", -H.tutar),
        (H.tur == "odeme", H.tutar),
        else_=0,
    )


async def cari_bakiyeleri(db: AsyncSession, kapsam: str, idler: Optional[Iterable[int]] = None,
                          once: Optional[date] = None, kadar: Optional[date] = None) -> Dict[int, int]:
    """Cari → hareket etkisi (açılış HARİÇ). `once`: o günden ÖNCEKİler; `kadar`: o gün dahil."""
    kosul = [H.kapsam == kapsam, H.cari_id.isnot(None)]
    if idler is not None:
        idler = list(idler)
        if not idler:
            return {}
        kosul.append(H.cari_id.in_(idler))
    if once:
        kosul.append(H.tarih < once)
    if kadar:
        kosul.append(H.tarih <= kadar)
    return {int(c): int(t or 0) for c, t in (await db.execute(
        select(H.cari_id, func.sum(_cari_ifadesi())).where(*kosul).group_by(H.cari_id))).all()}


def hareket_sayilari_sorgusu(kapsam: str, sutun):
    return select(sutun, func.count(H.id)).where(H.kapsam == kapsam, sutun.isnot(None)).group_by(sutun)


async def kullanimda_mi(db: AsyncSession, kapsam: str, *, hesap_id: Optional[int] = None, kategori_id: Optional[int] = None,
                        cari_id: Optional[int] = None) -> bool:
    if hesap_id:
        n = (await db.execute(select(func.count(H.id)).where(H.kapsam == kapsam, or_(H.hesap_id == hesap_id, H.hedef_hesap_id == hesap_id)))).scalar()
        n = int(n or 0) + int((await db.execute(select(func.count(MuhasebeTekrarlar.id)).where(
            MuhasebeTekrarlar.kapsam == kapsam, MuhasebeTekrarlar.hesap_id == hesap_id))).scalar() or 0)
        return n > 0
    if kategori_id:
        n = int((await db.execute(select(func.count(H.id)).where(H.kapsam == kapsam, H.kategori_id == kategori_id))).scalar() or 0)
        n += int((await db.execute(select(func.count(MuhasebeTekrarlar.id)).where(
            MuhasebeTekrarlar.kapsam == kapsam, MuhasebeTekrarlar.kategori_id == kategori_id))).scalar() or 0)
        n += int((await db.execute(select(func.count(MuhasebeButceler.id)).where(
            MuhasebeButceler.kapsam == kapsam, MuhasebeButceler.kategori_id == kategori_id))).scalar() or 0)
        return n > 0
    if cari_id:
        n = int((await db.execute(select(func.count(H.id)).where(H.kapsam == kapsam, H.cari_id == cari_id))).scalar() or 0)
        n += int((await db.execute(select(func.count(MuhasebeTekrarlar.id)).where(
            MuhasebeTekrarlar.kapsam == kapsam, MuhasebeTekrarlar.cari_id == cari_id))).scalar() or 0)
        return n > 0
    return False


# ---------------------------------------------------------------------------
# Cari ekstre ve yaşlandırma
# ---------------------------------------------------------------------------
async def cari_ekstre(db: AsyncSession, kapsam: str, c: MuhasebeCariler, bas: date, bit: date) -> Dict[str, Any]:
    """Devreden (açılış + `bas`tan önceki hareketler; açılış tarihi aralığa düşüyorsa satır olarak) + satırlar."""
    acilis_tarihi = c.acilis_tarihi or (c.created_at.date() if c.created_at else bas)
    devreden = sum((await cari_bakiyeleri(db, kapsam, [c.id], once=bas)).values())
    satirlar: List[Dict[str, Any]] = []
    bakiye = devreden
    toplam_borc = toplam_alacak = 0
    if c.acilis_bakiyesi and acilis_tarihi < bas:
        devreden += int(c.acilis_bakiyesi)
        bakiye = devreden
    elif c.acilis_bakiyesi and bas <= acilis_tarihi <= bit:
        borc, alacak = (int(c.acilis_bakiyesi), 0) if c.acilis_bakiyesi > 0 else (0, -int(c.acilis_bakiyesi))
        bakiye += borc - alacak
        toplam_borc += borc
        toplam_alacak += alacak
        satirlar.append({"id": None, "tarih": acilis_tarihi, "tur": "acilis", "aciklama": None, "belge_no": None,
                         "vade": None, "borc": borc, "alacak": alacak, "bakiye": bakiye, "ters": False})
    hareketler = (await db.execute(select(H).where(H.kapsam == kapsam, H.cari_id == c.id, H.tarih >= bas, H.tarih <= bit)
                                   .order_by(H.tarih, H.id))).scalars().all()
    for h in hareketler:
        borc, alacak = s.cari_etkisi(h.tur, int(h.tutar), h.hesap_id is not None)
        if not borc and not alacak:
            continue
        bakiye += borc - alacak
        toplam_borc += borc
        toplam_alacak += alacak
        satirlar.append({"id": h.id, "tarih": h.tarih, "tur": h.tur, "aciklama": h.aciklama, "belge_no": h.belge_no,
                         "vade": h.vade_tarihi, "borc": borc, "alacak": alacak, "bakiye": bakiye,
                         "ters": h.ters_edilen_id is not None, "kaynak": h.kaynak})
    return {"devreden": devreden, "satirlar": satirlar, "toplam_borc": toplam_borc, "toplam_alacak": toplam_alacak,
            "kapanis": bakiye}


async def cari_yaslandirma(db: AsyncSession, kapsam: str, cariler: Sequence[MuhasebeCariler], tarih: date,
                           yon: str = "alacak") -> Dict[int, s.Yaslandirma]:
    """`yon="alacak"`: cariden alacaklarımız (vadeli satış, cariye ödeme, artı açılış) — kapatan: tahsilat, vadeli
    alış, eksi açılış. `yon="borc"`: tersi (tedarikçiye borçlarımız). Ters çevrilmiş kayıt ve tersi yok sayılır."""
    if not cariler:
        return {}
    idler = [c.id for c in cariler]
    satirlar = (await db.execute(select(H.id, H.cari_id, H.tur, H.tutar, H.hesap_id, H.tarih, H.vade_tarihi).where(
        H.kapsam == kapsam, H.cari_id.in_(idler), H.tarih <= tarih, H.ters_kayit_id.is_(None), H.ters_edilen_id.is_(None)))).all()
    borclar: Dict[int, List[s.AcikKalem]] = {i: [] for i in idler}
    kapatan: Dict[int, int] = {i: 0 for i in idler}
    for hid, cid, tur, tutar, hesap_id, t, vade in satirlar:
        borc, alacak = s.cari_etkisi(tur, int(tutar), hesap_id is not None)
        if borc == alacak:
            continue  # peşin: etkisiz
        if yon == "borc":
            borc, alacak = alacak, borc
        if borc:
            borclar[cid].append(s.AcikKalem(vade or t, borc, hid))
        if alacak:
            kapatan[cid] += alacak
    sonuc: Dict[int, s.Yaslandirma] = {}
    for c in cariler:
        acilis = int(c.acilis_bakiyesi or 0) * (1 if yon == "alacak" else -1)
        acilis_tarihi = c.acilis_tarihi or (c.created_at.date() if c.created_at else tarih)
        if acilis > 0 and acilis_tarihi <= tarih:
            borclar[c.id].append(s.AcikKalem(acilis_tarihi, acilis, 0))
        elif acilis < 0:
            kapatan[c.id] += -acilis
        sonuc[c.id] = s.yaslandir(borclar[c.id], kapatan[c.id], tarih)
    return sonuc


# ---------------------------------------------------------------------------
# Raporlar
# ---------------------------------------------------------------------------
def _pb_satiri(sozluk: Dict[str, Any], pb: str, uretici) -> Any:
    if pb not in sozluk:
        sozluk[pb] = uretici()
    return sozluk[pb]


async def aylik_rapor(db: AsyncSession, kapsam: str, yil: int) -> Dict[str, Any]:
    bas, bit = date(yil, 1, 1), date(yil, 12, 31)
    satirlar = (await db.execute(select(H.tarih, H.tur, H.tutar, H.para_birimi).where(
        H.kapsam == kapsam, H.tur.in_(("gelir", "gider")), H.tarih >= bas, H.tarih <= bit))).all()
    pbler: Dict[str, Dict[str, Any]] = {}
    for t, tur, tutar, pb in satirlar:
        d = _pb_satiri(pbler, pb or "TRY", lambda: {"aylar": [{"ay": f"{yil:04d}-{a:02d}", "gelir": 0, "gider": 0, "net": 0}
                                                              for a in range(1, 13)]})
        ay = d["aylar"][t.month - 1]
        ay[tur] += int(tutar)
        ay["net"] = ay["gelir"] - ay["gider"]
    sonuc = []
    for pb, d in sorted(pbler.items()):
        gelir = sum(a["gelir"] for a in d["aylar"])
        gider = sum(a["gider"] for a in d["aylar"])
        sonuc.append({"para_birimi": pb, "aylar": d["aylar"], "gelir": gelir, "gider": gider, "net": gelir - gider})
    return {"yil": yil, "para_birimleri": sonuc}


async def kategori_raporu(db: AsyncSession, kapsam: str, bas: date, bit: date, tur: str) -> Dict[str, Any]:
    satirlar = (await db.execute(select(H.kategori_id, H.para_birimi, func.sum(H.tutar)).where(
        H.kapsam == kapsam, H.tur == tur, H.tarih >= bas, H.tarih <= bit).group_by(H.kategori_id, H.para_birimi))).all()
    kategoriler = {k.id: k for k in (await db.execute(select(MuhasebeKategorileri).where(
        MuhasebeKategorileri.kapsam == kapsam))).scalars().all()}
    pbler: Dict[str, List[Dict[str, Any]]] = {}
    for kid, pb, toplam in satirlar:
        k = kategoriler.get(kid) if kid else None
        pbler.setdefault(pb or "TRY", []).append({
            "kategori_id": kid, "ad": k.ad if k else None, "anahtar": k.anahtar if k else None,
            "ad_degisti": _ad_degisti(k) if k else False, "renk": (k.renk if k else None) or "#9ca3af", "tutar": int(toplam or 0)})
    sonuc = []
    for pb, kalemler in sorted(pbler.items()):
        kalemler.sort(key=lambda x: -x["tutar"])
        toplam = sum(x["tutar"] for x in kalemler)
        for x in kalemler:
            x["oran"] = round(x["tutar"] * 100 / toplam, 1) if toplam > 0 else 0
        sonuc.append({"para_birimi": pb, "toplam": toplam, "kalemler": kalemler})
    return {"bas": bas.isoformat(), "bit": bit.isoformat(), "tur": tur, "para_birimleri": sonuc}


async def kar_zarar(db: AsyncSession, kapsam: str, bas: date, bit: date) -> Dict[str, Any]:
    """Kâr-zarar özeti: dönemin gelir ve gider kategorileri KDV HARİÇ (tutar − KDV; ters kayıtlar eksiyle düşer),
    dönem sonucu = gelir − gider, kâr marjı. Tahakkuk / amortisman / stok değişimi düzeltmesi YOK — bilgilendirme amaçlı."""
    satirlar = (await db.execute(select(H.tur, H.kategori_id, H.para_birimi, func.sum(H.tutar), func.sum(H.kdv_tutari)).where(
        H.kapsam == kapsam, H.tur.in_(("gelir", "gider")), H.tarih >= bas, H.tarih <= bit)
        .group_by(H.tur, H.kategori_id, H.para_birimi))).all()
    kategoriler = {k.id: k for k in (await db.execute(select(MuhasebeKategorileri).where(
        MuhasebeKategorileri.kapsam == kapsam))).scalars().all()}
    pbler: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for tur, kid, pb, toplam, kdv in satirlar:
        k = kategoriler.get(kid) if kid else None
        brut, vergi = int(toplam or 0), int(kdv or 0)
        pbler.setdefault(pb or "TRY", {"gelir": [], "gider": []})[tur].append({
            "kategori_id": kid, "ad": k.ad if k else None, "anahtar": k.anahtar if k else None,
            "ad_degisti": _ad_degisti(k) if k else False, "renk": (k.renk if k else None) or "#9ca3af",
            "tutar": brut - vergi, "kdv": vergi, "brut": brut})
    sonuc = []
    for pb, d in sorted(pbler.items()):
        for liste in d.values():
            liste.sort(key=lambda x: -x["tutar"])
        gelir = sum(x["tutar"] for x in d["gelir"])
        gider = sum(x["tutar"] for x in d["gider"])
        sonuc.append({"para_birimi": pb, "gelirler": d["gelir"], "giderler": d["gider"], "toplam_gelir": gelir, "toplam_gider": gider,
                      "sonuc": gelir - gider, "marj": round((gelir - gider) * 100 / gelir, 1) if gelir > 0 else None})
    return {"bas": bas.isoformat(), "bit": bit.isoformat(), "para_birimleri": sonuc, "bilgilendirme": True}


def _ad_degisti(k: MuhasebeKategorileri) -> bool:
    return not k.anahtar or s.KATEGORI_ADLARI.get(k.anahtar) != k.ad


async def kdv_raporu(db: AsyncSession, kapsam: str, yil: int) -> Dict[str, Any]:
    """Hesaplanan (satış/gelir KDV'si) − indirilecek (alış/gider KDV'si) = fark (artı: ödenecek, eksi: devreden).
    BİLGİLENDİRME amaçlıdır; beyanname yerine geçmez."""
    bas, bit = date(yil, 1, 1), date(yil, 12, 31)
    satirlar = (await db.execute(select(H.tarih, H.tur, H.kdv_tutari, H.tutar, H.para_birimi).where(
        H.kapsam == kapsam, H.tur.in_(("gelir", "gider")), H.tarih >= bas, H.tarih <= bit))).all()
    pbler: Dict[str, Dict[str, Any]] = {}
    for t, tur, kdv, tutar, pb in satirlar:
        d = _pb_satiri(pbler, pb or "TRY", lambda: {"aylar": [{"ay": f"{yil:04d}-{a:02d}", "hesaplanan": 0, "indirilecek": 0,
                                                              "fark": 0, "matrah_satis": 0, "matrah_alis": 0}
                                                              for a in range(1, 13)]})
        ay = d["aylar"][t.month - 1]
        kdv = int(kdv or 0)
        if tur == "gelir":
            ay["hesaplanan"] += kdv
            ay["matrah_satis"] += int(tutar) - kdv
        else:
            ay["indirilecek"] += kdv
            ay["matrah_alis"] += int(tutar) - kdv
        ay["fark"] = ay["hesaplanan"] - ay["indirilecek"]
    sonuc = []
    for pb, d in sorted(pbler.items()):
        h = sum(a["hesaplanan"] for a in d["aylar"])
        i = sum(a["indirilecek"] for a in d["aylar"])
        sonuc.append({"para_birimi": pb, "aylar": d["aylar"], "hesaplanan": h, "indirilecek": i, "fark": h - i})
    return {"yil": yil, "para_birimleri": sonuc, "bilgilendirme": True}


NAKIT_UFUKLARI: Tuple[int, ...] = (30, 60, 90)


async def nakit_akisi(db: AsyncSession, kapsam: str, gecmis_ay: int = 6, tahmin_ay: int = s.TAHMIN_AY) -> Dict[str, Any]:
    """Hesaplardaki para: geçmiş aylar (giriş/çıkış/ay sonu bakiyesi; virman akışa girmez) + tekrarlayan
    kayıtlardan sonraki `tahmin_ay` ayın tahmini + önümüzdeki 30 / 60 / 90 gün: carilerin AÇIK vadeli alacak / borç
    kalemleri (FIFO yaşlandırmadaki kalan; vadesi bugün ile ufuk arasında) ve tekrarlayan kayıtlar. Vadesi geçmiş açık
    kalemler ayrıca (`gecikmis`) — ne zaman ödeneceği bilinmez, ufka katılmaz."""
    bugun = s.bugun()
    bu_ay = s.ay_anahtari(bugun)
    ilk_ay = s.ay_ekle(bu_ay, -(gecmis_ay - 1))
    hesaplar = (await db.execute(select(MuhasebeHesaplari).where(MuhasebeHesaplari.kapsam == kapsam))).scalars().all()
    hesap_pb = {h.id: h.para_birimi for h in hesaplar}
    acilis: Dict[str, int] = {}
    for h in hesaplar:
        acilis[h.para_birimi] = acilis.get(h.para_birimi, 0) + int(h.acilis_bakiyesi or 0)
    ilk_bas, _ = s.ay_araligi(ilk_ay)
    # İlk aydan önceki birikim (bakiye zinciri için).
    oncesi: Dict[str, int] = dict(acilis)
    hareketler = (await db.execute(select(H.tarih, H.tur, H.tutar, H.hesap_id, H.hedef_hesap_id, H.hedef_tutar).where(
        H.kapsam == kapsam, or_(H.hesap_id.isnot(None), H.hedef_hesap_id.isnot(None))))).all()
    aylar: Dict[str, Dict[str, Dict[str, int]]] = {}
    for t, tur, tutar, hid, hhid, htutar in hareketler:
        tutar = int(tutar)
        etkiler: List[Tuple[str, int, bool]] = []  # (para birimi, etki, akışa girer mi)
        if hid in hesap_pb:
            e = s.hesap_etkisi(tur, tutar, hid, None, None, hid)
            etkiler.append((hesap_pb[hid], e, tur != "virman"))
        if tur == "virman" and hhid in hesap_pb:
            etkiler.append((hesap_pb[hhid], htutar if htutar is not None else tutar, False))
        for pb, e, akis in etkiler:
            if t < ilk_bas:
                oncesi[pb] = oncesi.get(pb, 0) + e
                continue
            ay = s.ay_anahtari(t)
            d = aylar.setdefault(pb, {}).setdefault(ay, {"giris": 0, "cikis": 0, "degisim": 0})
            d["degisim"] += e
            if akis:
                if e >= 0:
                    d["giris"] += e
                else:
                    d["cikis"] += -e
    tekrarlar = (await db.execute(select(MuhasebeTekrarlar).where(
        MuhasebeTekrarlar.kapsam == kapsam, MuhasebeTekrarlar.aktif.is_(True), MuhasebeTekrarlar.sonraki.isnot(None)))).scalars().all()
    cariler = (await db.execute(select(MuhasebeCariler).where(MuhasebeCariler.kapsam == kapsam, MuhasebeCariler.arsiv.is_(False))
                                .limit(2000))).scalars().all()
    acik: Dict[str, List[Tuple[date, int, int]]] = {}  # para birimi → (vade, alacak, borç)
    if cariler:
        for yon, sozluk in (("alacak", await cari_yaslandirma(db, kapsam, cariler, bugun, "alacak")),
                            ("borc", await cari_yaslandirma(db, kapsam, cariler, bugun, "borc"))):
            for c in cariler:
                y = sozluk.get(c.id)
                for kalem in (y.kalemler if y else []):
                    acik.setdefault(c.para_birimi, []).append(
                        (kalem.vade, kalem.kalan if yon == "alacak" else 0, kalem.kalan if yon == "borc" else 0))
    pbler = sorted(set(acilis) | set(aylar) | {t.para_birimi for t in tekrarlar} | set(acik))
    sonuc = []
    for pb in pbler:
        bakiye = oncesi.get(pb, 0)
        gecmis = []
        for i in range(gecmis_ay):
            ay = s.ay_ekle(ilk_ay, i)
            d = aylar.get(pb, {}).get(ay, {"giris": 0, "cikis": 0, "degisim": 0})
            bakiye += d["degisim"]
            gecmis.append({"ay": ay, "giris": d["giris"], "cikis": d["cikis"], "net": d["giris"] - d["cikis"], "bakiye": bakiye})
        # Bu ayın kalanında (yarından ay sonuna) vadesi gelecek tekrarlar ilk tahmin ayının başlangıcına eklenir.
        _, bu_ay_sonu = s.ay_araligi(bu_ay)
        kalan = _tekrar_akisi([t for t in tekrarlar if t.para_birimi == pb], bugun + timedelta(days=1), bu_ay_sonu)
        bakiye += kalan[0] - kalan[1]
        tahmin = []
        for i in range(1, tahmin_ay + 1):
            ay = s.ay_ekle(bu_ay, i)
            ab, ae = s.ay_araligi(ay)
            giris, cikis = _tekrar_akisi([t for t in tekrarlar if t.para_birimi == pb], ab, ae)
            bakiye += giris - cikis
            tahmin.append({"ay": ay, "giris": giris, "cikis": cikis, "net": giris - cikis, "bakiye": bakiye, "tahmin": True})
        kl = acik.get(pb, [])
        simdiki = gecmis[-1]["bakiye"] if gecmis else oncesi.get(pb, 0)
        beklenen = []
        for gun in NAKIT_UFUKLARI:
            son = bugun + timedelta(days=gun)
            tahsilat = sum(a for v, a, _ in kl if bugun <= v <= son)
            odeme = sum(b_ for v, _, b_ in kl if bugun <= v <= son)
            tg, tc = _tekrar_akisi([t for t in tekrarlar if t.para_birimi == pb], bugun + timedelta(days=1), son)
            net = tahsilat + tg - odeme - tc
            beklenen.append({"gun": gun, "tahsilat": tahsilat, "odeme": odeme, "tekrar_giris": tg, "tekrar_cikis": tc, "net": net,
                             "bakiye": simdiki + net})
        sonuc.append({"para_birimi": pb, "gecmis": gecmis, "tahmin": tahmin,
                      "bu_ay_kalan": {"giris": kalan[0], "cikis": kalan[1]}, "beklenen": beklenen,
                      "gecikmis": {"tahsilat": sum(a for v, a, _ in kl if v < bugun), "odeme": sum(b_ for v, _, b_ in kl if v < bugun)}})
    return {"bugun": bugun.isoformat(), "para_birimleri": sonuc}


def _tekrar_akisi(tekrarlar: Sequence[MuhasebeTekrarlar], bas: date, bit: date) -> Tuple[int, int]:
    giris = cikis = 0
    for t in tekrarlar:
        if bit < bas:
            break
        ilk = max(bas, t.sonraki or bas)
        for _ in s.donemler(t.baslangic, t.periyot, ilk, bit, t.bitis):
            if t.tur == "gelir":
                giris += int(t.tutar)
            else:
                cikis += int(t.tutar)
    return giris, cikis


# ---------------------------------------------------------------------------
# Bütçe
# ---------------------------------------------------------------------------
async def butce_durumu(db: AsyncSession, kapsam: str, ay: str, uyari_yuzde: int = 80) -> Dict[str, Any]:
    bas, bit = s.ay_araligi(ay)
    butceler = (await db.execute(select(MuhasebeButceler).where(
        MuhasebeButceler.kapsam == kapsam, MuhasebeButceler.ay.in_((ay, "*"))))).scalars().all()
    gecerli: Dict[Tuple[int, str], Tuple[int, str, int]] = {}
    for b in sorted(butceler, key=lambda x: 0 if x.ay == "*" else 1):
        gecerli[(b.kategori_id, b.para_birimi)] = (int(b.tutar), "ay" if b.ay == ay else "her_ay", b.id)
    harcanan = {(kid, pb): int(t or 0) for kid, pb, t in (await db.execute(select(H.kategori_id, H.para_birimi, func.sum(H.tutar)).where(
        H.kapsam == kapsam, H.tur == "gider", H.tarih >= bas, H.tarih <= bit, H.kategori_id.isnot(None))
        .group_by(H.kategori_id, H.para_birimi))).all()}
    kategoriler = {k.id: k for k in (await db.execute(select(MuhasebeKategorileri).where(
        MuhasebeKategorileri.kapsam == kapsam, MuhasebeKategorileri.tur == "gider"))).scalars().all()}
    asimlar = {(a.kategori_id, a.para_birimi): a for a in (await db.execute(select(MuhasebeButceAsimlari).where(
        MuhasebeButceAsimlari.kapsam == kapsam, MuhasebeButceAsimlari.ay == ay))).scalars().all()}
    kalemler = []
    for anahtar in sorted(set(gecerli) | set(harcanan), key=lambda x: (x[1], (kategoriler[x[0]].sira if x[0] in kategoriler else 999), x[0])):
        kid, pb = anahtar
        k = kategoriler.get(kid)
        if k is None:
            continue
        butce = gecerli.get(anahtar)
        gerceklesen = harcanan.get(anahtar, 0)
        oran = round(gerceklesen * 100 / butce[0], 1) if butce and butce[0] > 0 else None
        if not butce:
            durum = "butcesiz"
        elif gerceklesen > butce[0]:
            durum = "asildi"
        elif oran is not None and oran >= uyari_yuzde:
            durum = "yaklasti"
        else:
            durum = "normal"
        kalemler.append({"kategori_id": kid, "ad": k.ad, "anahtar": k.anahtar, "ad_degisti": _ad_degisti(k), "renk": k.renk,
                         "para_birimi": pb, "butce": butce[0] if butce else None, "butce_id": butce[2] if butce else None,
                         "butce_kaynak": butce[1] if butce else None, "gerceklesen": gerceklesen, "oran": oran,
                         "kalan": (butce[0] - gerceklesen) if butce else None, "durum": durum,
                         "uyari_at": s.iso(asimlar[anahtar].created_at) if anahtar in asimlar else None})
    toplamlar: Dict[str, Dict[str, int]] = {}
    for x in kalemler:
        t = toplamlar.setdefault(x["para_birimi"], {"butce": 0, "gerceklesen": 0})
        t["butce"] += x["butce"] or 0
        t["gerceklesen"] += x["gerceklesen"] if x["butce"] else 0
    return {"ay": ay, "uyari_yuzde": uyari_yuzde, "kalemler": kalemler,
            "toplamlar": [{"para_birimi": pb, **v} for pb, v in sorted(toplamlar.items())],
            "asim_sayisi": sum(1 for x in kalemler if x["durum"] == "asildi")}


async def butce_denetle(db: AsyncSession, kapsam: str, hesap: Optional[str], aylar: Iterable[str]) -> int:
    """Aşan (kategori, ay, para birimi) için iz satırı (BİR kez) + `muhasebe.butce_asildi` olayı + bildirim (ajansta
    yöneticilere, müşteride hesaba). Bildirim gönderilirse oturum commit edilir (`notify.dispatch`); aksi hâlde
    çağıran commit eder."""
    from services import webhook

    yeni: List[Tuple[MuhasebeButceAsimlari, str]] = []
    a = await ayar_satiri(db, kapsam)
    for ay in sorted(set(aylar)):
        durum = await butce_durumu(db, kapsam, ay, a.uyari_yuzde if a else 80)
        for x in durum["kalemler"]:
            if x["durum"] != "asildi" or x["uyari_at"]:
                continue
            iz = MuhasebeButceAsimlari(kapsam=kapsam, hesap_email=hesap, kategori_id=x["kategori_id"], ay=ay,
                                       para_birimi=x["para_birimi"], butce=int(x["butce"]), gerceklesen=int(x["gerceklesen"]),
                                       created_at=s.simdi())
            try:
                async with db.begin_nested():
                    db.add(iz)
            except IntegrityError:
                continue
            yeni.append((iz, x["ad"]))
            await webhook.olay_yayinla(db, OLAY_BUTCE, hesap, asim_verisi(iz, x["ad"]))
    if yeni:
        await _asim_bildir(db, hesap, yeni)
    return len(yeni)


async def _asim_bildir(db: AsyncSession, hesap: Optional[str], asimlar: Sequence[Tuple[MuhasebeButceAsimlari, str]]) -> None:
    """Bütçe aşımı bildirimi (aşım başına bir kez — iz satırı kilit). Hata yutar."""
    from services.notify import admin_recipients, dispatch, render

    try:
        parcalar = [f"{ad} ({iz.ay}: {s.kurus_metni(iz.gerceklesen)} / {s.kurus_metni(iz.butce)} {iz.para_birimi})"
                    for iz, ad in asimlar[:5]]
        adlar = ", ".join(parcalar) + (f" +{len(asimlar) - 5}" if len(asimlar) > 5 else "")
        baslik, govde = await render(db, BILDIRIM_BUTCE, f"Bütçe aşıldı: {len(asimlar)} kategori",
                                     f"Bütçesini aşan gider kategorileri: {adlar}", {"sayi": len(asimlar), "kategoriler": adlar})
        if hesap:
            alicilar: List[Dict[str, Any]] = [{"email": hesap, "role": "client"}]
            baglanti = "/client?sekme=onMuhasebe&bolum=butce"
        else:
            alicilar = await admin_recipients(db)
            baglanti = "/admin?sekme=onMuhasebe&bolum=butce"
        await dispatch(db, event_type=BILDIRIM_BUTCE, title=baslik, body=govde, recipients=alicilar, link=baglanti,
                       ref_type="muhasebe_butce_asimlari", ref_id=asimlar[0][0].id)
    except Exception:  # noqa: BLE001
        logger.exception("Bütçe aşımı bildirimi gönderilemedi")


def asim_verisi(iz: MuhasebeButceAsimlari, kategori: Optional[str]) -> Dict[str, Any]:
    """Olay verisi (kişisel veri yok): kategori, ay, bütçe, gerçekleşen, aşım (TL ondalık), yüzde, para birimi."""
    butce, ger = int(iz.butce), int(iz.gerceklesen)
    return {"asim_id": iz.id, "kategori_id": iz.kategori_id, "kategori": kategori, "ay": iz.ay,
            "butce": round(butce / 100, 2), "gerceklesen": round(ger / 100, 2), "asim": round((ger - butce) / 100, 2),
            "yuzde": int(round(ger * 100 / butce)) if butce else None, "para_birimi": iz.para_birimi}


# ---------------------------------------------------------------------------
# Tekrarlayan kayıtlar
# ---------------------------------------------------------------------------
async def tekrarlari_uret(db: AsyncSession, kapsam: str, hesap: Optional[str], bugun: Optional[date] = None) -> Tuple[int, Set[str]]:
    """Vadesi gelen dönemleri harekete çevirir (kaynak `tekrar`, kimlik "<id>:<tarih>" benzersiz → aynı dönem iki
    kez yazılmaz). (üretilen, etkilenen aylar)."""
    bugun = bugun or s.bugun()
    uretilen = 0
    aylar: Set[str] = set()
    tekrarlar = (await db.execute(select(MuhasebeTekrarlar).where(
        MuhasebeTekrarlar.kapsam == kapsam, MuhasebeTekrarlar.aktif.is_(True), MuhasebeTekrarlar.sonraki.isnot(None),
        MuhasebeTekrarlar.sonraki <= bugun))).scalars().all()
    for t in tekrarlar:
        tur_sayisi = 0
        while t.sonraki is not None and t.sonraki <= bugun and tur_sayisi < s.EN_COK_TEKRAR_TUR:
            g = t.sonraki
            if t.bitis and g > t.bitis:
                t.sonraki = None
                break
            kdv = s.kdv_dahilden(int(t.tutar), t.kdv_orani)
            h = H(kapsam=kapsam, hesap_email=hesap, tur=t.tur, tarih=g, tutar=int(t.tutar), para_birimi=t.para_birimi,
                  kdv_orani=t.kdv_orani, kdv_tutari=kdv, kategori_id=t.kategori_id, hesap_id=t.hesap_id, cari_id=t.cari_id,
                  vade_tarihi=g if (t.cari_id and not t.hesap_id) else None, aciklama=t.aciklama, etiketler=t.etiketler,
                  kaynak="tekrar", kaynak_ref=str(t.id), kaynak_id=f"{t.id}:{g.isoformat()}", tekrar_id=t.id,
                  olusturan=None, created_at=s.simdi())
            try:
                async with db.begin_nested():
                    db.add(h)
                uretilen += 1
                aylar.add(s.ay_anahtari(g))
            except IntegrityError:
                pass  # başka bir tur yazdı
            t.son_uretilen = g
            yeni = s.sonraki_donem(t.baslangic, t.periyot, g)
            t.sonraki = None if (t.bitis and yeni > t.bitis) else yeni
            tur_sayisi += 1
    return uretilen, aylar


# ---------------------------------------------------------------------------
# Otomatik yansıma
# ---------------------------------------------------------------------------
@dataclass
class Beklenen:
    ref: str
    tur: str
    tarih: date
    tutar: int
    para_birimi: str
    kdv_tutari: int = 0
    kdv_orani: Optional[int] = None
    hesap_id: Optional[int] = None
    cari_id: Optional[int] = None
    kategori: Optional[str] = None
    aciklama: Optional[str] = None
    belge_no: Optional[str] = None
    vade: Optional[date] = None
    #: Öneride cari henüz yoksa (saha müşterisi): (bagli_tur, bagli_id, ad) — cari ONAYDA açılır (yok sayılan öneri
    #: için boş cari kartı oluşmasın).
    bagli: Optional[Tuple[str, str, str]] = None

    def veri(self) -> Dict[str, Any]:
        return {"tur": self.tur, "tarih": self.tarih.isoformat(), "tutar": self.tutar, "para_birimi": self.para_birimi,
                "kdv_orani": self.kdv_orani, "kdv_tutari": self.kdv_tutari, "hesap_id": self.hesap_id, "cari_id": self.cari_id,
                "kategori": self.kategori, "aciklama": self.aciklama, "belge_no": self.belge_no,
                "vade": self.vade.isoformat() if self.vade else None, "bagli": list(self.bagli) if self.bagli else None}

    def parmak_izi(self) -> str:
        return f"{self.tur}|{self.tutar}|{self.para_birimi}|{self.kdv_tutari}"


def _yerel_gun(an: Any) -> Optional[date]:
    if isinstance(an, datetime):
        a = an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an
        return a.astimezone(s.tz()).date()
    if isinstance(an, date):
        return an
    return None


def _ondaliktan(deger: Any) -> Optional[int]:
    if deger is None:
        return None
    try:
        return int((Decimal(str(deger)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:  # noqa: BLE001
        return None


def _baslangic(ayar: Dict[str, Any]) -> date:
    try:
        return date.fromisoformat(str(ayar.get("baslangic") or "")[:10])
    except ValueError:
        return s.bugun()


def _bas_ani(bas: date) -> datetime:
    """Başlangıç gününün bir gün öncesi 00:00 UTC (saat dilimi kayması payı; gün süzgeci ayrıca uygulanır)."""
    return datetime.combine(bas - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)


async def _hesaplar(db: AsyncSession, kapsam: str) -> Dict[int, MuhasebeHesaplari]:
    return {h.id: h for h in (await db.execute(select(MuhasebeHesaplari).where(MuhasebeHesaplari.kapsam == kapsam))).scalars().all()}


async def _etkin_yansimalar(db: AsyncSession, kapsam: str, kaynaklar: Sequence[str]) -> Dict[Tuple[str, str], H]:
    satirlar = (await db.execute(select(H).where(H.kapsam == kapsam, H.kaynak.in_(kaynaklar), H.ters_edilen_id.is_(None),
                                                 H.ters_kayit_id.is_(None)))).scalars().all()
    return {(h.kaynak, h.kaynak_ref): h for h in satirlar}


async def _odeme_beklenenleri(db: AsyncSession, kapsam: str, ayar: Dict[str, Any], hesaplar: Dict[int, MuhasebeHesaplari],
                              izlenen: Dict[str, Set[str]], atlanan: Dict[str, int],
                              musteri: Optional[str] = None) -> Dict[Tuple[str, str], Beklenen]:
    """Fatura ödemeleri. Ajans (`musteri` yok): müşterilerden gelen ödemeler GELİR (iade → gider), cari = fatura
    e-postasına bağlı cari. Müşteri (`musteri` = hesap): ajansa ödediği faturalar GİDER (iade → gelir), kategori
    "yazılım ve abonelikler". Ödeme kaydı (`payments`, durum odendi/iade) → `odeme`; ödeme kaydı olmadan "ödendi"
    işaretlenen fatura → `fatura`. Hedef hesap kanala göre: elden → nakit, Lemon Squeezy / Shopier / … → çevrim
    içi (POS/sanal POS) hesabı, havale/EFT/diğer → banka (eksikler bankaya düşer)."""
    from models.invoices import Invoices
    from models.payments import Payments

    bas = _baslangic(ayar)
    bas_an = _bas_ani(bas)
    izlenen_odeme = [int(x) for x in izlenen.get("odeme", set()) if x.isdigit()]
    izlenen_fatura = [int(x) for x in izlenen.get("fatura", set()) if x.isdigit()]
    odeme_kosul = [or_(
        and_(Payments.durum.in_(("odendi", "iade")), or_(Payments.odendi_at >= bas_an, Payments.created_at >= bas_an,
                                                          Payments.odeme_tarihi >= bas.isoformat())),
        Payments.id.in_(izlenen_odeme or [0]))]
    if musteri:
        odeme_kosul.append(func.lower(Payments.client_email) == musteri)
    odemeler = (await db.execute(select(Payments).where(*odeme_kosul))).scalars().all()
    fatura_idleri = {p.invoice_id for p in odemeler if p.invoice_id}
    fatura_kosul = [or_(
        and_(func.lower(Invoices.status) == "paid", or_(Invoices.tur.is_(None), Invoices.tur != "iade"),
             Invoices.updated_at >= bas_an),
        Invoices.id.in_((list(fatura_idleri) + izlenen_fatura) or [0]))]
    if musteri:
        fatura_kosul.append(func.lower(Invoices.client_email) == musteri)
    faturalar_ = (await db.execute(select(Invoices).where(*fatura_kosul))).scalars().all()
    faturalar = {f.id: f for f in faturalar_}
    odenmis_fatura = set((await db.execute(select(Payments.invoice_id).where(
        Payments.invoice_id.in_(list(faturalar) or [0]), Payments.durum == "odendi"))).scalars().all())
    cariler: Dict[str, MuhasebeCariler] = {}
    if not musteri:
        cariler = {c.bagli_id: c for c in (await db.execute(select(MuhasebeCariler).where(
            MuhasebeCariler.kapsam == kapsam, MuhasebeCariler.bagli_tur == "musteri_hesabi"))).scalars().all()}
    banka = ayar.get("banka_hesap_id")
    nakit = ayar.get("nakit_hesap_id") or banka
    cevrimici = ayar.get("cevrimici_hesap_id") or banka
    sonuc: Dict[Tuple[str, str], Beklenen] = {}

    def kdv_payi(f: Any, tutar: int) -> Tuple[int, Optional[int]]:
        if f is None or not f.amount or not f.kdv_toplam:
            return 0, None
        toplam = _ondaliktan(f.amount) or 0
        kdv = _ondaliktan(f.kdv_toplam) or 0
        if toplam <= 0:
            return 0, None
        oranlar = {int(k.get("kdv_orani") or 0) for k in (s.json_yukle(f.kalemler, []) or []) if isinstance(k, dict)}
        return s.yuvarla(tutar * kdv, toplam), (oranlar.pop() if len(oranlar) == 1 else None)

    def ekle(kaynak: str, ref: str, b: Beklenen, hedef: Optional[int]) -> None:
        h = hesaplar.get(hedef) if hedef else None
        if h is None:
            atlanan["hesap_yok"] = atlanan.get("hesap_yok", 0) + 1
            return
        if h.para_birimi != b.para_birimi:
            atlanan["para_birimi"] = atlanan.get("para_birimi", 0) + 1
            return
        b.hesap_id = h.id
        sonuc[(kaynak, ref)] = b

    def hedef_hesap(saglayici: Optional[str]) -> Optional[int]:
        k = (saglayici or "").strip().lower()
        if k == "elden":
            return nakit
        if k in s.CEVRIMICI_SAGLAYICILAR:
            return cevrimici
        return banka

    for p in odemeler:
        if p.durum not in ("odendi", "iade"):
            continue
        tutar = _ondaliktan(p.tutar)
        if not tutar or tutar <= 0:
            continue
        gun = None
        if p.odeme_tarihi:
            try:
                gun = date.fromisoformat(str(p.odeme_tarihi)[:10])
            except ValueError:
                gun = None
        gun = gun or _yerel_gun(p.odendi_at) or _yerel_gun(p.created_at) or s.bugun()
        if gun < bas and str(p.id) not in izlenen.get("odeme", set()):
            continue
        f = faturalar.get(p.invoice_id) if p.invoice_id else None
        pb = (p.para_birimi or (f.currency if f else None) or "TRY").upper()
        iade = p.durum == "iade"
        kdv, oran = (0, None) if iade else kdv_payi(f, tutar)
        belge = p.invoice_no or (f.invoice_no if f else None)
        if musteri:
            b = Beklenen(ref=str(p.id), tur="gelir" if iade else "gider", tarih=gun, tutar=tutar, para_birimi=pb, kdv_tutari=kdv,
                         kdv_orani=oran, kategori="diger_gelir" if iade else "yazilim",
                         aciklama="Ajans faturası iadesi" if iade else "Ajans faturası ödemesi", belge_no=belge)
        else:
            c = cariler.get((p.client_email or "").strip().lower())
            b = Beklenen(ref=str(p.id), tur="gider" if iade else "gelir", tarih=gun, tutar=tutar, para_birimi=pb, kdv_tutari=kdv,
                         kdv_orani=oran, cari_id=c.id if (c and c.para_birimi == pb) else None,
                         kategori="diger_gider" if iade else "hizmet",
                         aciklama=("Fatura iadesi (geri ödeme)" if iade else "Fatura tahsilatı") + (f" — {f.client_name}" if f and f.client_name else ""),
                         belge_no=belge)
        ekle("odeme", str(p.id), b, hedef_hesap(p.saglayici))
    for f in faturalar.values():
        if (f.status or "").lower() != "paid" or f.tur == "iade" or f.id in odenmis_fatura:
            continue
        tutar = _ondaliktan(f.amount)
        if not tutar or tutar <= 0:
            continue
        gun = _yerel_gun(f.updated_at) or s.bugun()
        if gun < bas and str(f.id) not in izlenen.get("fatura", set()):
            continue
        pb = (f.currency or "TRY").upper()
        kdv, oran = kdv_payi(f, tutar)
        if musteri:
            b = Beklenen(ref=str(f.id), tur="gider", tarih=gun, tutar=tutar, para_birimi=pb, kdv_tutari=kdv, kdv_orani=oran,
                         kategori="yazilim", aciklama="Ajans faturası (ödendi)", belge_no=f.invoice_no)
        else:
            c = cariler.get((f.client_email or "").strip().lower())
            b = Beklenen(ref=str(f.id), tur="gelir", tarih=gun, tutar=tutar, para_birimi=pb, kdv_tutari=kdv, kdv_orani=oran,
                         cari_id=c.id if (c and c.para_birimi == pb) else None, kategori="hizmet",
                         aciklama="Ödenen fatura" + (f" — {f.client_name}" if f.client_name else ""), belge_no=f.invoice_no)
        ekle("fatura", str(f.id), b, banka)
    return sonuc


async def _pos_beklenenleri(db: AsyncSession, hesap: str, ayar: Dict[str, Any], hesaplar: Dict[int, MuhasebeHesaplari],
                            izlenen: Set[str], atlanan: Dict[str, int], korunan: Set[Tuple[str, str]]) -> Dict[Tuple[str, str], Beklenen]:
    """Kapanmış kasa oturumu → ödeme türü başına gelir (iade fazlası gider). Kapanmış OLAĞAN oturum değişmez: zaten
    yansıtılmışsa özeti yeniden hesaplanmaz (`korunan`); çevrimdışı eşitleme oturumu (Faz 6Q) büyüyebilir, izlenir."""
    from models.stok_pos import PosKasaOturumlari
    from services.stok_kayit import oturum_ozeti

    bas = _baslangic(ayar)
    bas_an = _bas_ani(bas)
    izlenen_id = {int(r.split(":")[0]) for r in izlenen if r.split(":")[0].isdigit()}
    oturumlar = (await db.execute(select(PosKasaOturumlari).where(
        PosKasaOturumlari.hesap_email == hesap, or_(
            and_(PosKasaOturumlari.durum == "kapali", or_(PosKasaOturumlari.kapanis_at >= bas_an, PosKasaOturumlari.acilis_at >= bas_an)),
            PosKasaOturumlari.id.in_(list(izlenen_id) or [0]))))).scalars().all()
    hedefler = {"nakit": ayar.get("nakit_hesap_id"), "kart": ayar.get("kart_hesap_id"),
                "havale": ayar.get("havale_hesap_id") or ayar.get("kart_hesap_id")}
    sonuc: Dict[Tuple[str, str], Beklenen] = {}
    for o in oturumlar:
        if o.durum != "kapali":
            continue
        gun = _yerel_gun(o.kapanis_at) or _yerel_gun(o.acilis_at) or s.bugun()
        if gun < bas and o.id not in izlenen_id:
            continue
        if o.id in izlenen_id and o.tur != "esitleme":
            korunan.update(("pos", r) for r in izlenen if r.split(":")[0] == str(o.id))
            continue
        ozet = await oturum_ozeti(db, o)
        pb = (ozet.get("para_birimi") or "TRY").upper()
        odemeler = ozet.get("odemeler") or {}
        net = sum(int(odemeler.get(t) or 0) for t in ("nakit", "kart", "havale"))
        kdv_toplam = sum(int(d.get("kdv") or 0) for d in ozet.get("kdv_dokumu") or [])
        oranlar = {int(d.get("oran") or 0) for d in ozet.get("kdv_dokumu") or [] if d.get("kdv")}
        oran = oranlar.pop() if len(oranlar) == 1 else None
        for tur in ("nakit", "kart", "havale"):
            tutar = int(odemeler.get(tur) or 0)
            if not tutar:
                continue
            ref = f"{o.id}:{tur}"
            h = hesaplar.get(hedefler[tur]) if hedefler[tur] else None
            if h is None:
                atlanan["hesap_yok"] = atlanan.get("hesap_yok", 0) + 1
                continue
            if h.para_birimi != pb:
                atlanan["para_birimi"] = atlanan.get("para_birimi", 0) + 1
                continue
            iade = tutar < 0
            kdv = 0 if (iade or net <= 0) else s.yuvarla(kdv_toplam * tutar, net)
            sonuc[("pos", ref)] = Beklenen(
                ref=ref, tur="gider" if iade else "gelir", tarih=gun, tutar=abs(tutar), para_birimi=pb, kdv_tutari=kdv,
                kdv_orani=None if iade else oran, hesap_id=h.id, kategori="diger_gider" if iade else "satis",
                aciklama=f"POS gün sonu ({_POS_ADLARI[tur]})" + (" — iade fazlası" if iade else ""), belge_no=f"Z-{o.id}")
    return sonuc


_POS_ADLARI = {"nakit": "nakit", "kart": "kart", "havale": "havale"}
_MASRAF_ADLARI = {"harc": "harç", "tebligat": "tebligat", "bilirkisi": "bilirkişi", "yol": "yol", "diger": "diğer"}


async def _hukuk_beklenenleri(db: AsyncSession, hesap: str, ayar: Dict[str, Any], hesaplar: Dict[int, MuhasebeHesaplari],
                              izlenen: Set[str], atlanan: Dict[str, int]) -> Dict[Tuple[str, str], Beklenen]:
    """Hukuk masrafları → gider. Açıklama GENEL ("Hukuk masrafı (harç)"): dosya/müvekkil bilgisi taşınmaz (sır)."""
    from models.hukuk import HukukMasraflari

    bas = _baslangic(ayar)
    izlenen_id = [int(r) for r in izlenen if r.isdigit()]
    masraflar = (await db.execute(select(HukukMasraflari).where(HukukMasraflari.hesap_email == hesap, or_(
        HukukMasraflari.tarih >= bas, HukukMasraflari.id.in_(izlenen_id or [0]))))).scalars().all()
    h = hesaplar.get(ayar.get("hesap_id")) if ayar.get("hesap_id") else None
    sonuc: Dict[Tuple[str, str], Beklenen] = {}
    for m in masraflar:
        if m.avanstan:
            continue  # müvekkil avansından karşılanan masraf işletme gideri değil
        tutar = int(m.tutar_kurus or 0)
        if tutar <= 0:
            continue
        pb = (m.para_birimi or "TRY").upper()
        if h is None:
            atlanan["hesap_yok"] = atlanan.get("hesap_yok", 0) + 1
            continue
        if h.para_birimi != pb:
            atlanan["para_birimi"] = atlanan.get("para_birimi", 0) + 1
            continue
        sonuc[("hukuk", str(m.id))] = Beklenen(ref=str(m.id), tur="gider", tarih=m.tarih, tutar=tutar, para_birimi=pb,
                                               hesap_id=h.id, kategori="dava_masraf",
                                               aciklama=f"Hukuk masrafı ({_MASRAF_ADLARI.get(m.tur, m.tur)})")
    return sonuc


async def _saha_beklenenleri(db: AsyncSession, kapsam: str, hesap: str, ayar: Dict[str, Any], hesaplar: Dict[int, MuhasebeHesaplari],
                             izlenen: Set[str], atlanan: Dict[str, int], cari_ac: bool = True) -> Dict[Tuple[str, str], Beklenen]:
    """Tamamlanan iş emri: (işçilik + Σ malzeme) KDV hariç + saha ayarındaki KDV. Hedef hesap varsa peşin; yoksa
    saha müşterisinin carisine vadeli alacak (cari yoksa açılır: yalnız ad/firma; `cari_ac=False` — öneri — iken
    açılmaz, `Beklenen.bagli` ile onaya bırakılır)."""
    from models.saha_servisi import SahaAyarlari, SahaIsEmirleri, SahaMalzemeKullanimi, SahaMusterileri

    bas = _baslangic(ayar)
    bas_an = _bas_ani(bas)
    izlenen_id = [int(r) for r in izlenen if r.isdigit()]
    isler = (await db.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.hesap_email == hesap, or_(
        and_(SahaIsEmirleri.durum == "tamamlandi", or_(SahaIsEmirleri.bitir_at >= bas_an, SahaIsEmirleri.updated_at >= bas_an)),
        SahaIsEmirleri.id.in_(izlenen_id or [0]))))).scalars().all()
    if not isler:
        return {}
    sa = (await db.execute(select(SahaAyarlari).where(SahaAyarlari.hesap_email == hesap))).scalars().first()
    oran = int(sa.kdv_orani or 0) if sa else 20
    pb = ((sa.para_birimi if sa else None) or "TRY").upper()
    malzemeler: Dict[int, int] = {}
    for m in (await db.execute(select(SahaMalzemeKullanimi).where(SahaMalzemeKullanimi.is_emri_id.in_([i.id for i in isler])))).scalars().all():
        malzemeler[m.is_emri_id] = malzemeler.get(m.is_emri_id, 0) + int(round(float(m.miktar or 0) * int(m.birim_fiyat or 0)))
    h = hesaplar.get(ayar.get("hesap_id")) if ayar.get("hesap_id") else None
    if h is not None and h.para_birimi != pb:
        atlanan["para_birimi"] = atlanan.get("para_birimi", 0) + 1
        return {}
    musteri_idleri = {i.musteri_id for i in isler}
    musteriler = {m.id: m for m in (await db.execute(select(SahaMusterileri).where(SahaMusterileri.id.in_(list(musteri_idleri) or [0])))).scalars().all()}
    sonuc: Dict[Tuple[str, str], Beklenen] = {}
    for ie in isler:
        if ie.durum != "tamamlandi":
            continue
        gun = _yerel_gun(ie.bitir_at) or _yerel_gun(ie.updated_at) or s.bugun()
        if gun < bas and str(ie.id) not in izlenen:
            continue
        ara = int(ie.iscilik_ucreti or 0) + malzemeler.get(ie.id, 0)
        if ara <= 0:
            continue
        kdv = s.kdv_haricten(ara, oran)
        b = Beklenen(ref=str(ie.id), tur="gelir", tarih=gun, tutar=ara + kdv, para_birimi=pb, kdv_tutari=kdv,
                     kdv_orani=oran, kategori="hizmet", aciklama=f"İş emri {ie.no}: {ie.baslik}"[:300], belge_no=ie.no)
        if h is not None:
            b.hesap_id = h.id
        else:
            c = await _saha_carisi(db, kapsam, hesap, musteriler.get(ie.musteri_id), ie.musteri_id, pb, olustur=cari_ac)
            if c is None and not cari_ac and not await _saha_carisi_var_mi(db, kapsam, ie.musteri_id):
                b.bagli, b.vade = ("saha_musteri", str(ie.musteri_id), _saha_cari_adi(musteriler.get(ie.musteri_id), ie.musteri_id)), gun
                sonuc[("saha", str(ie.id))] = b
                continue
            if c is None:
                atlanan["cari_yok"] = atlanan.get("cari_yok", 0) + 1
                continue
            b.cari_id, b.vade = c.id, gun
        sonuc[("saha", str(ie.id))] = b
    return sonuc


def _saha_cari_adi(m: Any, mid: Any) -> str:
    if m is not None and not m.anonim:
        return ((m.firma or m.ad or "").strip() or f"Saha müşterisi #{mid}")[:160]
    return f"Saha müşterisi #{mid}"


async def _saha_carisi_var_mi(db: AsyncSession, kapsam: str, mid: Any) -> bool:
    return (await db.execute(select(MuhasebeCariler.id).where(MuhasebeCariler.kapsam == kapsam, MuhasebeCariler.bagli_tur == "saha_musteri",
                                                              MuhasebeCariler.bagli_id == str(mid)).limit(1))).scalar() is not None


async def _saha_carisi(db: AsyncSession, kapsam: str, hesap: Optional[str], m: Any, mid: Any, pb: str, olustur: bool = True,
                       ad: Optional[str] = None) -> Optional[MuhasebeCariler]:
    c = (await db.execute(select(MuhasebeCariler).where(MuhasebeCariler.kapsam == kapsam, MuhasebeCariler.bagli_tur == "saha_musteri",
                                                        MuhasebeCariler.bagli_id == str(mid)))).scalars().first()
    if c is not None:
        return c if c.para_birimi == pb else None
    if not olustur:
        return None
    c = MuhasebeCariler(kapsam=kapsam, hesap_email=hesap, tur="musteri", ad=(ad or _saha_cari_adi(m, mid))[:160], para_birimi=pb,
                        acilis_bakiyesi=0, bagli_tur="saha_musteri", bagli_id=str(mid), created_at=s.simdi())
    db.add(c)
    await db.flush()
    return c


def _farkli(h: H, b: Beklenen) -> bool:
    return (int(h.tutar) != b.tutar or h.tur != b.tur or h.para_birimi != b.para_birimi or int(h.kdv_tutari or 0) != b.kdv_tutari)


async def ters_kayit(db: AsyncSession, h: H, bugun: date) -> Optional[H]:
    """Aslının eksisi (aynı tür/hesap/kategori/cari); aslına `ters_kayit_id`. Benzersiz kimlik "~ters"."""
    t = H(kapsam=h.kapsam, hesap_email=h.hesap_email, tur=h.tur, tarih=max(bugun, h.tarih), tutar=-int(h.tutar),
          para_birimi=h.para_birimi, kdv_orani=h.kdv_orani, kdv_tutari=-int(h.kdv_tutari or 0), kategori_id=h.kategori_id,
          hesap_id=h.hesap_id, cari_id=h.cari_id, vade_tarihi=h.vade_tarihi, aciklama=h.aciklama, belge_no=h.belge_no,
          kaynak=h.kaynak, kaynak_ref=h.kaynak_ref, kaynak_id=f"{h.kaynak_id}~ters", ters_edilen_id=h.id, created_at=s.simdi())
    try:
        async with db.begin_nested():
            db.add(t)
            await db.flush()
            h.ters_kayit_id = t.id
            h.updated_at = s.simdi()
    except IntegrityError:
        return None
    return t


def _oneri_mi(kk: str, ayar: Dict[str, Any]) -> bool:
    return kk in s.HEP_ONERI_KAYNAKLARI or bool(ayar.get("onay"))


async def _oneri_yaz(db: AsyncSession, kapsam: str, hesap: Optional[str], kk: str, ref: str, b: Beklenen) -> int:
    """Öneriyi yaz/güncelle. Yeni ya da yeniden açılan (yok sayılmışken kaynağı değişen) öneri için 1."""
    veri = s.json_yaz(b.veri())
    parmak = b.parmak_izi()
    o = (await db.execute(select(MuhasebeOneriler).where(MuhasebeOneriler.kapsam == kapsam, MuhasebeOneriler.kaynak == kk,
                                                         MuhasebeOneriler.kaynak_ref == ref))).scalars().first()
    if o is None:
        o = MuhasebeOneriler(kapsam=kapsam, hesap_email=hesap, kaynak=kk, kaynak_ref=ref, durum="bekliyor", parmak_izi=parmak,
                             veri=veri, tarih=b.tarih, tutar=b.tutar, para_birimi=b.para_birimi, created_at=s.simdi())
        try:
            async with db.begin_nested():
                db.add(o)
        except IntegrityError:
            return 0
        return 1
    if o.durum == "yoksayildi" and o.parmak_izi == parmak:
        return 0
    yeniden = o.durum == "yoksayildi"
    if o.veri != veri or yeniden:
        o.veri, o.parmak_izi, o.tarih, o.tutar, o.para_birimi = veri, parmak, b.tarih, b.tutar, b.para_birimi
        o.durum = "bekliyor"
        o.updated_at = s.simdi()
    return 1 if yeniden else 0


async def _oneri_temizle(db: AsyncSession, kapsam: str, kaynaklar: Sequence[str], kalan: Optional[Set[Tuple[str, str]]] = None) -> int:
    """`kaynaklar`ın, `kalan`da olmayan önerilerini siler (kalan None → hepsi). Silinen sayısı."""
    satirlar = (await db.execute(select(MuhasebeOneriler).where(MuhasebeOneriler.kapsam == kapsam,
                                                                MuhasebeOneriler.kaynak.in_(kaynaklar)))).scalars().all()
    n = 0
    for o in satirlar:
        if kalan is None or (o.kaynak, o.kaynak_ref) not in kalan:
            await db.delete(o)
            n += 1
    return n


KAYNAK_LISTESI: Dict[str, Tuple[str, ...]] = {"odeme": ("odeme", "fatura"), "pos": ("pos",), "hukuk": ("hukuk",), "saha": ("saha",)}


async def yansit(db: AsyncSession, kapsam: str, hesap: Optional[str], ayar_satiri_: Optional[MuhasebeAyarlari] = None) -> Dict[str, Any]:
    """Açık kaynakları defterle eşitler. {"olusturulan", "ters", "oneri", "atlanan": {neden: sayı}, "aylar": [...]}."""
    a = ayar_satiri_ or await ayar_satiri(db, kapsam)
    ayarlar = aktarim_ayarlari(a, kapsam)
    sonuc: Dict[str, Any] = {"olusturulan": 0, "ters": 0, "oneri": 0, "atlanan": {}, "aylar": set()}
    # Kapalı kaynakların bekleyen / yok sayılmış önerileri kalmaz.
    kapali = [kk for k, v in ayarlar.items() if not v.get("acik") for kk in KAYNAK_LISTESI[k]]
    if kapali:
        await _oneri_temizle(db, kapsam, kapali)
    acik = {k: v for k, v in ayarlar.items() if v.get("acik")}
    if not acik:
        return sonuc
    hesaplar = await _hesaplar(db, kapsam)
    kategori_onbellek: Dict[str, Optional[int]] = {}
    bugun = s.bugun()
    for kaynak, ayar in acik.items():
        if hesap and kaynak in s.AKTARIM_MODULU:
            from services.moduller import modul_acik_mi

            if not await modul_acik_mi(db, hesap, s.AKTARIM_MODULU[kaynak]):
                sonuc["atlanan"]["modul_kapali"] = sonuc["atlanan"].get("modul_kapali", 0) + 1
                continue
        kaynaklar = KAYNAK_LISTESI[kaynak]
        etkin = await _etkin_yansimalar(db, kapsam, kaynaklar)
        izlenen: Dict[str, Set[str]] = {}
        for (kk, ref) in etkin:
            izlenen.setdefault(kk, set()).add(ref or "")
        atlanan: Dict[str, int] = sonuc["atlanan"]
        korunan: Set[Tuple[str, str]] = set()
        try:
            if kaynak == "odeme":
                beklenen = await _odeme_beklenenleri(db, kapsam, ayar, hesaplar, izlenen, atlanan, musteri=hesap)
            elif kaynak == "pos":
                beklenen = await _pos_beklenenleri(db, hesap or "", ayar, hesaplar, izlenen.get("pos", set()), atlanan, korunan)
            elif kaynak == "hukuk":
                beklenen = await _hukuk_beklenenleri(db, hesap or "", ayar, hesaplar, izlenen.get("hukuk", set()), atlanan)
            else:
                beklenen = await _saha_beklenenleri(db, kapsam, hesap or "", ayar, hesaplar, izlenen.get("saha", set()), atlanan,
                                                    cari_ac=not _oneri_mi("saha", ayar))
        except Exception:  # noqa: BLE001 - tek kaynak eşitlemeyi düşürmesin
            logger.exception("Muhasebe yansıması okunamadı (%s, %s)", kapsam, kaynak)
            atlanan["hata"] = atlanan.get("hata", 0) + 1
            continue
        # Kaynağı gitmiş / geçersizleşmiş etkin yansımalar (onaylanmış öneriler dahil) → ters kayıt.
        for anahtar, h in etkin.items():
            if anahtar in korunan:
                continue
            b = beklenen.get(anahtar)
            if b is None or _farkli(h, b):
                if await ters_kayit(db, h, bugun):
                    sonuc["ters"] += 1
                    sonuc["aylar"].add(s.ay_anahtari(max(bugun, h.tarih)))
        # Yeni / değişen → yeni sürüm (otomatik) ya da öneri (onaylı).
        oneri_kalan: Set[Tuple[str, str]] = set()
        for anahtar, b in beklenen.items():
            h = etkin.get(anahtar)
            if h is not None and not _farkli(h, b):
                continue
            kk, ref = anahtar
            if _oneri_mi(kk, ayar):
                oneri_kalan.add(anahtar)
                sonuc["oneri"] += await _oneri_yaz(db, kapsam, hesap, kk, ref, b)
                continue
            if b.cari_id is None and b.hesap_id is None:
                atlanan["cari_yok"] = atlanan.get("cari_yok", 0) + 1
                continue
            if b.kategori and b.kategori not in kategori_onbellek:
                kategori_onbellek[b.kategori] = await kategori_anahtarla(db, kapsam, hesap, b.kategori)
            if await _hareket_yaz(db, kapsam, hesap, kk, ref, b, kategori_onbellek.get(b.kategori) if b.kategori else None):
                sonuc["olusturulan"] += 1
                sonuc["aylar"].add(s.ay_anahtari(b.tarih))
        await _oneri_temizle(db, kapsam, kaynaklar, oneri_kalan)
    return sonuc


async def _hareket_yaz(db: AsyncSession, kapsam: str, hesap: Optional[str], kk: str, ref: str, b: Beklenen, kategori_id: Optional[int],
                       olusturan: Optional[str] = None) -> Optional[H]:
    """Yansımanın yeni sürümü (kimlik "<ref>#<sürüm>"; benzersiz kısıt çakışırsa None)."""
    surum = int((await db.execute(select(func.count(H.id)).where(H.kapsam == kapsam, H.kaynak == kk, H.kaynak_ref == ref,
                                                               H.ters_edilen_id.is_(None)))).scalar() or 0) + 1
    yeni = H(kapsam=kapsam, hesap_email=hesap, tur=b.tur, tarih=b.tarih, tutar=b.tutar, para_birimi=b.para_birimi,
             kdv_orani=b.kdv_orani, kdv_tutari=b.kdv_tutari, kategori_id=kategori_id, hesap_id=b.hesap_id, cari_id=b.cari_id,
             vade_tarihi=b.vade if b.hesap_id is None else None, aciklama=(b.aciklama or "")[:300] or None,
             belge_no=(b.belge_no or "")[:60] or None, kaynak=kk, kaynak_ref=ref, kaynak_id=f"{ref}#{surum}", olusturan=olusturan,
             created_at=s.simdi())
    try:
        async with db.begin_nested():
            db.add(yeni)
    except IntegrityError:
        return None
    return yeni


async def oneri_onayla(db: AsyncSession, kapsam: str, hesap: Optional[str], o: MuhasebeOneriler, *, hesap_id: Optional[int] = None,
                       kategori_id: Optional[int] = None, aciklama: Optional[str] = None, kisi: Optional[str] = None) -> H:
    """Öneriyi deftere yazar (aynı kaynak kimliği → iki kez sayılmaz) ve siler. `hesap_id` / `kategori_id` /
    `aciklama` önerilenin yerine (hesap aynı para biriminde ve arşivde olmamalı; kategori türü uymalı). Hesap da
    cari de yoksa (saha: carisi henüz açılmamış müşteri) cari onayda açılır. Commit ÇAĞIRANA."""
    v = s.json_yukle(o.veri, {}) or {}
    etkin = (await db.execute(select(H).where(H.kapsam == kapsam, H.kaynak == o.kaynak, H.kaynak_ref == o.kaynak_ref,
                                              H.ters_edilen_id.is_(None), H.ters_kayit_id.is_(None)))).scalars().first()
    if etkin is not None:  # zaten yazılmış (eşzamanlı onay) — idempotent
        await db.delete(o)
        return etkin
    try:
        tarih = date.fromisoformat(str(v.get("tarih"))[:10])
        vade = date.fromisoformat(str(v["vade"])[:10]) if v.get("vade") else None
    except ValueError:
        raise s.MuhasebeHatasi("oneri_gecersiz", "veri")
    b = Beklenen(ref=o.kaynak_ref, tur=str(v.get("tur")), tarih=tarih, tutar=int(v.get("tutar") or 0), para_birimi=str(v.get("para_birimi") or "TRY"),
                 kdv_tutari=int(v.get("kdv_tutari") or 0), kdv_orani=v.get("kdv_orani"), hesap_id=v.get("hesap_id"), cari_id=v.get("cari_id"),
                 kategori=v.get("kategori"), aciklama=v.get("aciklama"), belge_no=v.get("belge_no"), vade=vade,
                 bagli=tuple(v["bagli"]) if isinstance(v.get("bagli"), list) and len(v["bagli"]) == 3 else None)  # type: ignore[arg-type]
    if b.tur not in ("gelir", "gider") or b.tutar <= 0:
        raise s.MuhasebeHatasi("oneri_gecersiz", "veri")
    if hesap_id is not None:
        h = (await db.execute(select(MuhasebeHesaplari).where(MuhasebeHesaplari.kapsam == kapsam, MuhasebeHesaplari.id == hesap_id))).scalars().first()
        if h is None:
            raise s.MuhasebeHatasi("hesap_bulunamadi", "hesap_id")
        if h.arsiv:
            raise s.MuhasebeHatasi("hesap_arsivde", "hesap_id")
        if h.para_birimi != b.para_birimi:
            raise s.MuhasebeHatasi("para_birimi_uyusmuyor", "hesap_id")
        b.hesap_id = h.id
    elif b.hesap_id is not None:
        h = (await db.execute(select(MuhasebeHesaplari).where(MuhasebeHesaplari.kapsam == kapsam, MuhasebeHesaplari.id == b.hesap_id))).scalars().first()
        if h is None or h.arsiv or h.para_birimi != b.para_birimi:
            raise s.MuhasebeHatasi("hesap_gerekli", "hesap_id")
    if b.cari_id is not None:
        c = (await db.execute(select(MuhasebeCariler).where(MuhasebeCariler.kapsam == kapsam, MuhasebeCariler.id == b.cari_id))).scalars().first()
        if c is None or c.para_birimi != b.para_birimi:
            b.cari_id = None
    if b.hesap_id is None and b.cari_id is None and b.bagli and b.bagli[0] == "saha_musteri":
        c = await _saha_carisi(db, kapsam, hesap, None, b.bagli[1], b.para_birimi, olustur=True, ad=b.bagli[2])
        b.cari_id = c.id if c is not None else None
    if b.hesap_id is None and b.cari_id is None:
        raise s.MuhasebeHatasi("hesap_gerekli", "hesap_id")
    if b.hesap_id is not None:
        b.vade = None
    if kategori_id is not None:
        k = (await db.execute(select(MuhasebeKategorileri).where(MuhasebeKategorileri.kapsam == kapsam,
                                                                 MuhasebeKategorileri.id == kategori_id))).scalars().first()
        if k is None:
            raise s.MuhasebeHatasi("kategori_bulunamadi", "kategori_id")
        if k.tur != b.tur:
            raise s.MuhasebeHatasi("kategori_turu_uyusmuyor", "kategori_id")
        kid: Optional[int] = k.id
    else:
        kid = await kategori_anahtarla(db, kapsam, hesap, b.kategori) if b.kategori else None
    if aciklama is not None:
        b.aciklama = aciklama
    yeni = await _hareket_yaz(db, kapsam, hesap, o.kaynak, o.kaynak_ref, b, kid, olusturan=kisi)
    if yeni is None:
        raise s.MuhasebeHatasi("eszamanli", "id", durum=409)
    await db.delete(o)
    await db.flush()
    return yeni


async def oneri_sayisi(db: AsyncSession, kapsam: str) -> int:
    return int((await db.execute(select(func.count(MuhasebeOneriler.id)).where(
        MuhasebeOneriler.kapsam == kapsam, MuhasebeOneriler.durum == "bekliyor"))).scalar() or 0)


# ---------------------------------------------------------------------------
# Gecikmiş alacak olayı
# ---------------------------------------------------------------------------
async def gecikmeleri_denetle(db: AsyncSession, kapsam: str, hesap: Optional[str], bugun: Optional[date] = None) -> int:
    """Vadesi geçen açık alacak kalemleri (FIFO yaşlandırma): eşik (1 / 30 / 60 / 90 gün) başına BİR iz satırı +
    `muhasebe.alacak_gecikti` olayı (webhook + otomasyon). Çağıran commit eder."""
    from services import webhook

    bugun = bugun or s.bugun()
    cariler = (await db.execute(select(MuhasebeCariler).where(MuhasebeCariler.kapsam == kapsam, MuhasebeCariler.arsiv.is_(False))
                                .limit(2000))).scalars().all()
    if not cariler:
        return 0
    yas = await cari_yaslandirma(db, kapsam, cariler, bugun, "alacak")
    adaylar: List[Tuple[MuhasebeCariler, s.AcikKalem, int, int]] = []
    for c in cariler:
        y = yas.get(c.id)
        for kalem in (y.kalemler if y else []):
            gun = (bugun - kalem.vade).days
            esik = s.gecikme_esigi(gun)
            if esik is not None and kalem.kalan > 0:
                adaylar.append((c, kalem, gun, esik))
    if not adaylar:
        return 0
    mevcut = {(ci, hi, e) for ci, hi, e in (await db.execute(select(
        MuhasebeGecikmeIzleri.cari_id, MuhasebeGecikmeIzleri.hareket_id, MuhasebeGecikmeIzleri.esik).where(
        MuhasebeGecikmeIzleri.kapsam == kapsam, MuhasebeGecikmeIzleri.cari_id.in_({c.id for c, *_ in adaylar})))).all()}
    yeni = 0
    for c, kalem, gun, esik in adaylar:
        hid = int(kalem.hareket_id or 0)
        if (c.id, hid, esik) in mevcut:
            continue
        iz = MuhasebeGecikmeIzleri(kapsam=kapsam, hesap_email=hesap, cari_id=c.id, hareket_id=hid, esik=esik, gun=gun, vade=kalem.vade,
                                   tutar=int(kalem.kalan), para_birimi=c.para_birimi, created_at=s.simdi())
        try:
            async with db.begin_nested():
                db.add(iz)
        except IntegrityError:
            continue
        yeni += 1
        await webhook.olay_yayinla(db, OLAY_GECIKME, hesap, gecikme_verisi(iz, c.ad))
    return yeni


def gecikme_verisi(iz: MuhasebeGecikmeIzleri, cari: Optional[str]) -> Dict[str, Any]:
    """Olay verisi: cari adı (iş ortağı), eşik günü, açık tutar (ondalık), vade. E-posta / telefon YOK (otomasyon
    kişiyi kayıttan okur)."""
    return {"gecikme_id": iz.id, "cari_id": iz.cari_id, "cari": cari, "hareket_id": iz.hareket_id or None, "gun": iz.esik,
            "vade": iz.vade.isoformat(), "tutar": round(int(iz.tutar) / 100, 2), "para_birimi": iz.para_birimi}


async def esitle(db: AsyncSession, kapsam: str, hesap: Optional[str]) -> Dict[str, Any]:
    """Tekrarlar + otomatik yansıma + bütçe denetimi (bu ay ve dokunulan aylar). Commit EDER."""
    a = await ayar_al(db, kapsam, hesap)
    if not a.kategoriler_tohumlandi:
        await kategorileri_tohumla(db, kapsam, hesap)
    tekrar, aylar = await tekrarlari_uret(db, kapsam, hesap)
    y = await yansit(db, kapsam, hesap, a)
    aylar |= set(y.pop("aylar", set()))
    aylar.add(s.ay_anahtari(s.bugun()))
    await db.flush()
    gecikme = await gecikmeleri_denetle(db, kapsam, hesap)
    await db.flush()
    asim = await butce_denetle(db, kapsam, hesap, aylar)
    a = await ayar_al(db, kapsam, hesap)
    ozet = {"tekrar": tekrar, "olusturulan": y["olusturulan"], "ters": y["ters"], "oneri": y["oneri"], "atlanan": y["atlanan"],
            "butce_asimi": asim, "gecikme": gecikme, "bekleyen_oneri": await oneri_sayisi(db, kapsam), "zaman": s.iso(s.simdi())}
    a.son_esitleme = s.json_yaz(ozet)
    a.son_esitleme_at = s.simdi()
    await db.commit()
    return ozet


async def zamanli_bakim(db: AsyncSession) -> Dict[str, Any]:
    """`muhasebe_bakimi` zamanlı işi: ayarı olan her kapsam (müşteride modül açıksa) eşitlenir. Kapsam başına hata
    diğerlerini durdurmaz."""
    from services.moduller import modul_acik_mi

    kapsamlar = [(k, h) for k, h in (await db.execute(select(MuhasebeAyarlari.kapsam, MuhasebeAyarlari.hesap_email))).all()]
    ozet = {"kapsam": 0, "tekrar": 0, "olusturulan": 0, "ters": 0, "oneri": 0, "butce_asimi": 0, "gecikme": 0, "hata": 0}
    for kapsam, hesap in kapsamlar:
        try:
            if hesap and not await modul_acik_mi(db, hesap, s.MODUL):
                continue
            r = await esitle(db, kapsam, hesap)
            ozet["kapsam"] += 1
            for alan in ("tekrar", "olusturulan", "ters", "oneri", "butce_asimi", "gecikme"):
                ozet[alan] += int(r.get(alan) or 0)
        except Exception:  # noqa: BLE001
            logger.exception("Muhasebe eşitlemesi başarısız (%s)", kapsam)
            ozet["hata"] += 1
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
    return ozet


# ---------------------------------------------------------------------------
# Ekler
# ---------------------------------------------------------------------------
async def ek_kaydet(db: AsyncSession, h: H, *, ad_ham: str, veri: bytes, yukleyen: Optional[str]) -> MuhasebeEkleri:
    """Tür içerikten doğrulanır (`services/dosyalar.turu_dogrula`), içerik kalıcı depoya. Commit ÇAĞIRANA."""
    import secrets

    from services import dosya_deposu, dosyalar

    try:
        ad = dosyalar.ad_temizle(ad_ham)
        mime = dosyalar.turu_dogrula(ad, veri)
    except dosyalar.DosyaHatasi as hata:
        raise s.MuhasebeHatasi(hata.kod, "dosya", durum=hata.durum)
    an = s.simdi()
    anahtar = f"muhasebe/{an:%Y/%m}/{secrets.token_hex(16)}"
    try:
        depo = await dosya_deposu.yaz(db, anahtar, veri, mime)
    except dosya_deposu.DepoHatasi:
        raise s.MuhasebeHatasi("depo_hatasi", "dosya", durum=502)
    e = MuhasebeEkleri(kapsam=h.kapsam, hesap_email=h.hesap_email, hareket_id=h.id, ad=ad[:120], tur=mime, boyut=len(veri),
                       depo=depo, depolama_anahtari=anahtar, yukleyen=(yukleyen or None) and yukleyen[:254], created_at=an)
    db.add(e)
    await db.flush()
    return e


# ---------------------------------------------------------------------------
# Haftalık özet (yalnız ajans)
# ---------------------------------------------------------------------------
async def haftalik_ozet_satirlari(db: AsyncSession, bugun: date) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(bu ayın bütçe aşımları, vadesi geçen cari alacaklar) — ajansın kendi muhasebesi."""
    kapsam = s.AJANS_KAPSAMI
    ay = s.ay_anahtari(bugun)
    kategoriler = {k.id: k.ad for k in (await db.execute(select(MuhasebeKategorileri).where(
        MuhasebeKategorileri.kapsam == kapsam))).scalars().all()}
    asimlar = []
    for a in (await db.execute(select(MuhasebeButceAsimlari).where(MuhasebeButceAsimlari.kapsam == kapsam,
                                                                    MuhasebeButceAsimlari.ay == ay)
                               .order_by(MuhasebeButceAsimlari.id))).scalars().all():
        asimlar.append({"kategori": kategoriler.get(a.kategori_id) or "—", "butce": int(a.butce), "gerceklesen": int(a.gerceklesen),
                        "para_birimi": a.para_birimi})
    cariler = (await db.execute(select(MuhasebeCariler).where(MuhasebeCariler.kapsam == kapsam, MuhasebeCariler.arsiv.is_(False))
                                .limit(2000))).scalars().all()
    yas = await cari_yaslandirma(db, kapsam, cariler, bugun, "alacak")
    alacaklar = []
    for c in cariler:
        y = yas.get(c.id)
        if y is None:
            continue
        gecmis = sum(k.kalan for k in y.kalemler if (bugun - k.vade).days > 0)
        if gecmis <= 0:
            continue
        alacaklar.append({"cari": c.ad, "tutar": gecmis, "para_birimi": c.para_birimi, "gun": y.en_eski_gun or 0})
    alacaklar.sort(key=lambda x: -x["gun"])
    return asimlar, alacaklar
