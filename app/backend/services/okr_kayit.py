"""Faz 6O — Hedefler ve OKR: veritabanı işleri (sözlükler, ilerleme, otomatik yenileme, olaylar, hatırlatma, kapanış).

Kurallar `services/okr.py`'de (ilerleme hesabı TEK yer), otomatik kaynaklar `services/okr_kaynak.py`'de.

Olaylar (webhook + otomasyon, `services/webhook.olay_yayinla`; ajansta hesap boş):
* `okr.kr_riskte` — bir KR'nin güveni "tehlikede"ye GEÇTİĞİNDE (önceki check-in tehlikede değilse) bir kez.
* `okr.hedef_tamamlandi` — hedefin ilerlemesi 1'e ULAŞTIĞINDA bir kez (`tamamlandi_at`; ilerleme düşerse boşalır,
  yeniden ulaşınca yine bir kez).

Haftalık check-in hatırlatması (`zamanli_bakim` içinde): açık dönemdeki etkin hedeflerin ELLE (kaynaksız) KR'leri
son 7 gündür check-in almadıysa sahibine (sahibi boşsa hedefin sahibine, o da boşsa ajansta yöneticilere / müşteride
hesaba) TEK bildirim (`okr_hatirlatma`; kişi başına bir ileti, KR'ler listelenir). Aynı KR için yeniden hatırlatma en
erken 7 gün sonra (`son_hatirlatma_at`).
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.okr import OkrAnahtarSonuclar, OkrCheckinler, OkrDonemler, OkrHedefler
from services import okr as s
from services import okr_kaynak as kaynaklar
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

KR = OkrAnahtarSonuclar
OLAY_RISK = "okr.kr_riskte"
OLAY_TAMAM = "okr.hedef_tamamlandi"
BILDIRIM = "okr_hatirlatma"


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def kilometre_listesi(kr: KR) -> List[Dict[str, Any]]:
    liste = s.json_yukle(kr.kilometre_taslari, []) or []
    return [k for k in liste if isinstance(k, dict)]


def kr_ilerlemesi(kr: KR) -> float:
    return s.kr_ilerleme(kr.tur, kr.baslangic_deger, kr.hedef_deger, kr.mevcut_deger, kr.yon,
                         kilometre_listesi(kr) if kr.tur == "kilometre" else None)


def kr_sozlugu(kr: KR, paylasim: bool = False) -> Dict[str, Any]:
    """`paylasim=True`: müşteriyle paylaşılan kart — yalnız ilerleme alanları (sahip, güven, kaynak, not YOK)."""
    km = kilometre_listesi(kr)
    tamam, toplam = s.kilometre_sayilari(km)
    d: Dict[str, Any] = {
        "id": kr.id, "hedef_id": kr.hedef_id, "baslik": kr.baslik, "tur": kr.tur, "birim": kr.birim or "",
        "para_birimi": kr.para_birimi, "baslangic": kr.baslangic_deger, "hedef": kr.hedef_deger, "mevcut": kr.mevcut_deger,
        "yon": kr.yon, "ilerleme": round(kr_ilerlemesi(kr), 4), "kilometre_tamam": tamam, "kilometre_toplam": toplam,
    }
    if paylasim:
        if kr.tur == "kilometre":
            d["kilometre_taslari"] = [{"metin": k.get("metin"), "tamam": bool(k.get("tamam"))} for k in km]
        return d
    ayar = s.json_yukle(kr.kaynak_ayar, {}) or {}
    d.update({
        "agirlik": int(kr.agirlik or 1), "sahip": kr.sahip or "", "kilometre_taslari": km, "kaynak": kr.kaynak,
        "kaynak_ayar": ayar if isinstance(ayar, dict) else {}, "kaynak_son_yenileme": s.iso(kr.kaynak_son_yenileme),
        "kaynak_hata": kr.kaynak_hata, "guven": kr.guven, "son_checkin_at": s.iso(kr.son_checkin_at),
        "kapanis_puani": kr.kapanis_puani, "tasindi_kaynak_id": kr.tasindi_kaynak_id, "sira": int(kr.sira or 0),
    })
    return d


def donem_sozlugu(d: OkrDonemler, bugun: Optional[date] = None) -> Dict[str, Any]:
    bugun = bugun or s.bugun()
    return {
        "id": d.id, "ad": d.ad or "", "tur": d.tur, "yil": d.yil, "ceyrek": d.ceyrek, "baslangic": d.baslangic.isoformat(),
        "bitis": d.bitis.isoformat(), "etkin": bool(d.etkin), "durum": d.durum, "kapanis_notu": d.kapanis_notu or "",
        "kapandi_at": s.iso(d.kapandi_at), "kapatan": d.kapatan, "beklenen": round(s.beklenen_ilerleme(d.baslangic, d.bitis, bugun), 4),
        "etiket": s.donem_etiketi(d.tur, d.yil, d.ceyrek, d.baslangic, d.bitis, d.ad),
    }


def hedef_sozlugu(h: OkrHedefler, krler: Sequence[KR], beklenen: float, paylasim: bool = False) -> Dict[str, Any]:
    ilerleme = s.hedef_ilerleme((kr_ilerlemesi(k), int(k.agirlik or 1)) for k in krler)
    d: Dict[str, Any] = {
        "id": h.id, "donem_id": h.donem_id, "baslik": h.baslik, "aciklama": h.aciklama or "",
        "ilerleme": None if ilerleme is None else round(ilerleme, 4), "durum_rengi": s.ilerleme_durumu(ilerleme, beklenen),
        "krler": [kr_sozlugu(k, paylasim) for k in krler],
    }
    if paylasim:
        return d
    d.update({
        "sahip": h.sahip or "", "ust_id": h.ust_id, "gorunurluk": h.gorunurluk, "durum": h.durum,
        "musteri_email": h.musteri_email, "musteri_paylasim": bool(h.musteri_paylasim), "tamamlandi_at": s.iso(h.tamamlandi_at),
        "tasindi_kaynak_id": h.tasindi_kaynak_id, "olusturan": h.olusturan, "sira": int(h.sira or 0),
        "kr_sayisi": len(krler),
    })
    return d


def checkin_sozlugu(c: OkrCheckinler) -> Dict[str, Any]:
    return {"id": c.id, "kr_id": c.kr_id, "tur": c.tur, "deger": c.deger, "onceki": c.onceki, "guven": c.guven,
            "notlar": c.notlar or "", "sure_dk": c.sure_dk, "tarih": c.tarih.isoformat(), "yazan": c.yazan,
            "zaman": s.iso(c.created_at)}


# ---------------------------------------------------------------------------
# Sorgular
# ---------------------------------------------------------------------------
def gorunur_kosul(kisi: Optional[str]):
    """Ekip hedefleri + kişinin kendi özel hedefleri (sahibi ya da oluşturanı). `kisi` None: sistem (hepsi)."""
    if kisi is None:
        return True
    return or_(OkrHedefler.gorunurluk == "ekip", OkrHedefler.sahip == kisi, OkrHedefler.olusturan == kisi)


async def donemler(db: AsyncSession, kapsam: str) -> List[OkrDonemler]:
    return list((await db.execute(select(OkrDonemler).where(OkrDonemler.kapsam == kapsam)
                                  .order_by(OkrDonemler.baslangic.desc(), OkrDonemler.id.desc()))).scalars().all())


async def hedefler(db: AsyncSession, kapsam: str, kisi: Optional[str], donem_id: Optional[int] = None) -> List[OkrHedefler]:
    q = select(OkrHedefler).where(OkrHedefler.kapsam == kapsam, gorunur_kosul(kisi))
    if donem_id is not None:
        q = q.where(OkrHedefler.donem_id == donem_id)
    return list((await db.execute(q.order_by(OkrHedefler.sira, OkrHedefler.id))).scalars().all())


async def krler_haritasi(db: AsyncSession, hedef_idleri: Iterable[int]) -> Dict[int, List[KR]]:
    idler = list({int(i) for i in hedef_idleri})
    sonuc: Dict[int, List[KR]] = {i: [] for i in idler}
    if not idler:
        return sonuc
    for k in (await db.execute(select(KR).where(KR.hedef_id.in_(idler)).order_by(KR.sira, KR.id))).scalars().all():
        sonuc.setdefault(k.hedef_id, []).append(k)
    return sonuc


async def donem_ozeti(db: AsyncSession, kapsam: str, d: OkrDonemler, kisi: Optional[str]) -> Dict[str, Any]:
    """Dönem listesi görünümü: hedefler + KR'ler + ilerleme, dönemin genel ilerlemesi (etkin + kapalı hedeflerin
    ortalaması; taslaklar sayılmaz) ve beklenen."""
    bugun = s.bugun()
    beklenen = s.beklenen_ilerleme(d.baslangic, d.bitis, bugun)
    hs = await hedefler(db, kapsam, kisi, d.id)
    harita = await krler_haritasi(db, [h.id for h in hs])
    liste = [hedef_sozlugu(h, harita.get(h.id, []), beklenen) for h in hs]
    olculen = [x["ilerleme"] for x in liste if x["ilerleme"] is not None and x["durum"] != "taslak"]
    genel = (sum(olculen) / len(olculen)) if olculen else None
    return {"donem": donem_sozlugu(d, bugun), "hedefler": liste, "ilerleme": None if genel is None else round(genel, 4),
            "durum_rengi": s.ilerleme_durumu(genel, beklenen)}


async def ust_haritasi(db: AsyncSession, kapsam: str) -> Dict[int, Optional[int]]:
    return dict((await db.execute(select(OkrHedefler.id, OkrHedefler.ust_id).where(OkrHedefler.kapsam == kapsam))).all())


# ---------------------------------------------------------------------------
# İlerleme değişimi → olaylar
# ---------------------------------------------------------------------------
async def _olay(db: AsyncSession, tur: str, hesap: Optional[str], veri: Dict[str, Any]) -> None:
    from services import webhook

    await webhook.olay_yayinla(db, tur, hesap, veri)


async def hedef_denetle(db: AsyncSession, h: OkrHedefler, hesap: Optional[str], krler: Optional[Sequence[KR]] = None) -> bool:
    """İlerleme 1'e ulaştıysa `okr.hedef_tamamlandi` (geçişte bir kez). Çağıran commit eder. Olay yazıldıysa True."""
    if krler is None:
        krler = (await krler_haritasi(db, [h.id])).get(h.id, [])
    ilerleme = s.hedef_ilerleme((kr_ilerlemesi(k), int(k.agirlik or 1)) for k in krler)
    if ilerleme is not None and ilerleme >= 1.0:
        if h.tamamlandi_at is None and h.durum != "taslak":
            h.tamamlandi_at = s.simdi()
            await db.flush()
            await _olay(db, OLAY_TAMAM, hesap, {"hedef_id": h.id, "donem_id": h.donem_id, "baslik": h.baslik})
            return True
        return False
    if h.tamamlandi_at is not None:
        h.tamamlandi_at = None
    return False


async def risk_olayi(db: AsyncSession, kr: KR, h: OkrHedefler, hesap: Optional[str]) -> None:
    await _olay(db, OLAY_RISK, hesap, {"kr_id": kr.id, "hedef_id": h.id, "baslik": kr.baslik, "hedef": h.baslik,
                                       "ilerleme": round(kr_ilerlemesi(kr) * 100, 1), "guven": kr.guven})


async def checkin_yaz(db: AsyncSession, kr: KR, h: OkrHedefler, hesap: Optional[str], *, deger: float, guven: Optional[str],
                      notlar: Optional[str], tarih: date, yazan: Optional[str], tur: str = "elle",
                      sure_dk: Optional[int] = None) -> OkrCheckinler:
    """Değer geçmişine satır + KR'nin mevcut değeri / güveni. "Tehlikede"ye geçişte `okr.kr_riskte`. Çağıran commit eder."""
    onceki_guven = kr.guven
    c = OkrCheckinler(kapsam=kr.kapsam, hesap_email=kr.hesap_email, kr_id=kr.id, hedef_id=h.id, tur=tur, deger=float(deger),
                      onceki=kr.mevcut_deger, guven=guven, notlar=notlar, sure_dk=sure_dk, tarih=tarih, yazan=yazan)
    db.add(c)
    if tur != "odak":
        kr.mevcut_deger = float(deger)
    if guven:
        kr.guven = guven
    if tur == "elle":
        kr.son_checkin_at = s.simdi()
    kr.updated_at = s.simdi()
    await db.flush()
    if guven == "tehlikede" and onceki_guven != "tehlikede":
        await risk_olayi(db, kr, h, hesap)
    return c


# ---------------------------------------------------------------------------
# Otomatik kaynak yenileme
# ---------------------------------------------------------------------------
async def kr_yenile(db: AsyncSession, kr: KR, h: OkrHedefler, d: OkrDonemler, hesap: Optional[str]) -> Dict[str, Any]:
    """Kaynaklı KR'nin değerini hesaplar; değiştiyse mevcut değer + `otomatik` check-in. Modül kapalı / hata →
    değer DEĞİŞMEZ, `kaynak_hata`. Çağıran commit eder."""
    if not kr.kaynak:
        return {"id": kr.id, "degisti": False, "hata": "kaynak_yok"}
    k = kaynaklar.KAYNAK_SOZLUGU.get(kr.kaynak)
    an = s.simdi()
    if k is None or not await kaynaklar.kaynak_acik_mi(db, k, hesap):
        kr.kaynak_hata = "modul_kapali" if k is not None else "kaynak_gecersiz"
        kr.kaynak_son_yenileme = an
        return {"id": kr.id, "degisti": False, "hata": kr.kaynak_hata}
    ayar = s.json_yukle(kr.kaynak_ayar, {}) or {}
    try:
        deger = await kaynaklar.kaynak_degeri(db, kr.kaynak, hesap, d.baslangic, d.bitis, ayar if isinstance(ayar, dict) else {})
    except s.TemelHata as hata:
        kr.kaynak_hata = hata.kod[:40]
        kr.kaynak_son_yenileme = an
        return {"id": kr.id, "degisti": False, "hata": kr.kaynak_hata}
    except Exception:  # noqa: BLE001 — bir kaynak diğerlerini düşürmesin
        logger.exception("OKR kaynağı hesaplanamadı (%s)", kr.kaynak)
        kr.kaynak_hata = "hesaplanamadi"
        kr.kaynak_son_yenileme = an
        return {"id": kr.id, "degisti": False, "hata": kr.kaynak_hata}
    kr.kaynak_hata = None
    kr.kaynak_son_yenileme = an
    degisti = abs(float(kr.mevcut_deger or 0) - float(deger)) > 1e-9
    if degisti:
        await checkin_yaz(db, kr, h, hesap, deger=deger, guven=None, notlar=None, tarih=s.bugun(), yazan=None, tur="otomatik")
    return {"id": kr.id, "degisti": degisti, "hata": None, "mevcut": float(deger)}


async def donemi_yenile(db: AsyncSession, kapsam: str, hesap: Optional[str], d: OkrDonemler,
                        kr_idleri: Optional[Iterable[int]] = None) -> Dict[str, Any]:
    """Dönemin (kapalı değilse) bütün kaynaklı KR'lerini yeniler; değişen hedeflerde tamamlanma denetimi. Commit eder."""
    if d.durum == "kapandi":
        return {"yenilenen": 0, "degisen": 0, "hatali": 0}
    hs = (await db.execute(select(OkrHedefler).where(OkrHedefler.kapsam == kapsam, OkrHedefler.donem_id == d.id,
                                                     OkrHedefler.durum != "kapandi"))).scalars().all()
    harita = await krler_haritasi(db, [h.id for h in hs])
    secili = {int(i) for i in kr_idleri} if kr_idleri is not None else None
    yenilenen = degisen = hatali = 0
    for h in hs:
        degisti = False
        for kr in harita.get(h.id, []):
            if not kr.kaynak or (secili is not None and kr.id not in secili):
                continue
            r = await kr_yenile(db, kr, h, d, hesap)
            yenilenen += 1
            degisen += int(r["degisti"])
            hatali += int(bool(r["hata"]))
            degisti = degisti or r["degisti"]
        if degisti:
            await hedef_denetle(db, h, hesap, harita.get(h.id, []))
    await db.commit()
    return {"yenilenen": yenilenen, "degisen": degisen, "hatali": hatali}


# ---------------------------------------------------------------------------
# Haftalık hatırlatma
# ---------------------------------------------------------------------------
async def _bayat_krler(db: AsyncSession, an: datetime, kapsam: Optional[str] = None,
                       hatirlatilmamis: bool = True) -> List[Tuple[KR, OkrHedefler, OkrDonemler]]:
    """Açık (bugünü kapsayan) dönemde etkin hedeflerin elle KR'leri: son 7 gündür check-in yok (hiç yoksa oluşturulma
    zamanı 7 günden eski). `hatirlatilmamis`: son 7 günde hatırlatma gitmemiş olanlar."""
    bugun = an.astimezone(s.tz()).date()
    esik = an - timedelta(days=s.HATIRLATMA_GUN)
    q = (select(KR, OkrHedefler, OkrDonemler)
         .join(OkrHedefler, OkrHedefler.id == KR.hedef_id)
         .join(OkrDonemler, OkrDonemler.id == OkrHedefler.donem_id)
         .where(KR.kaynak.is_(None), OkrHedefler.durum == "etkin", OkrDonemler.durum == "acik",
                OkrDonemler.baslangic <= bugun, OkrDonemler.bitis >= bugun,
                or_(KR.son_checkin_at < esik, and_(KR.son_checkin_at.is_(None), KR.created_at < esik))))
    if kapsam is not None:
        q = q.where(KR.kapsam == kapsam)
    if hatirlatilmamis:
        q = q.where(or_(KR.son_hatirlatma_at.is_(None), KR.son_hatirlatma_at < esik))
    sonuc = []
    for kr, h, d in (await db.execute(q.order_by(KR.id).limit(2000))).all():
        if kr_ilerlemesi(kr) >= 1.0:  # bitmiş KR'ye hatırlatma yok
            continue
        sonuc.append((kr, h, d))
    return sonuc


async def hatirlatmalari_gonder(db: AsyncSession, an: Optional[datetime] = None) -> int:
    """Kişi başına tek bildirim; gönderilen KR'lere `son_hatirlatma_at`. Gönderilen bildirim sayısı. Commit eder."""
    from services.notify import admin_recipients, dispatch, render

    an = an or s.simdi()
    gruplar: Dict[Tuple[Optional[str], str], List[Tuple[KR, OkrHedefler]]] = {}
    for kr, h, d in await _bayat_krler(db, an):
        hesap = kr.hesap_email
        alici = (kr.sahip or h.sahip or "").strip().lower()
        gruplar.setdefault((hesap, alici), []).append((kr, h))
    gonderilen = 0
    for (hesap, alici), liste in gruplar.items():
        try:
            adlar = ", ".join(f"{kr.baslik}" for kr, _ in liste[:5]) + (f" +{len(liste) - 5}" if len(liste) > 5 else "")
            baslik, govde = await render(db, BILDIRIM, f"Check-in zamanı: {len(liste)} anahtar sonuç",
                                         f"Son {s.HATIRLATMA_GUN} gündür güncellenmeyen anahtar sonuçlar: {adlar}",
                                         {"sayi": len(liste), "krler": adlar})
            if hesap:
                alicilar: List[Dict[str, Any]] = [{"email": alici or hesap, "role": "client"}]
                baglanti = "/client?sekme=hedefler"
            else:
                alicilar = [{"email": alici, "role": "admin"}] if alici else await admin_recipients(db)
                baglanti = "/admin?sekme=hedefler"
            await dispatch(db, event_type=BILDIRIM, title=baslik, body=govde, recipients=alicilar, link=baglanti,
                           ref_type="okr_anahtar_sonuclar", ref_id=liste[0][0].id)
            gonderilen += 1
        except Exception:  # noqa: BLE001
            logger.exception("OKR hatırlatması gönderilemedi")
        for kr, _ in liste:
            kr.son_hatirlatma_at = an
        await db.commit()
    return gonderilen


async def zamanli_bakim(db: AsyncSession) -> Dict[str, Any]:
    """Zamanlı iş `okr_bakimi`: açık dönemlerin (bugünü kapsayan ya da son 7 günde biten) kaynaklı KR'lerini yenile
    (dönem başına en çok saatte bir — `kaynak_son_yenileme`), sonra haftalık check-in hatırlatmaları."""
    an = s.simdi()
    bugun = an.astimezone(s.tz()).date()
    sonuc = {"donem": 0, "yenilenen": 0, "degisen": 0, "hatirlatma": 0}
    adaylar = (await db.execute(select(OkrDonemler).where(OkrDonemler.durum == "acik", OkrDonemler.baslangic <= bugun,
                                                          OkrDonemler.bitis >= bugun - timedelta(days=7)))).scalars().all()
    esik = an - s.YENILEME_ARALIGI
    for d in adaylar:
        bayat = (await db.execute(select(KR.id).join(OkrHedefler, OkrHedefler.id == KR.hedef_id).where(
            OkrHedefler.donem_id == d.id, KR.kaynak.isnot(None),
            or_(KR.kaynak_son_yenileme.is_(None), KR.kaynak_son_yenileme < esik)))).scalars().all()
        if not bayat:
            continue
        try:
            r = await donemi_yenile(db, d.kapsam, d.hesap_email, d, bayat)
            sonuc["donem"] += 1
            sonuc["yenilenen"] += r["yenilenen"]
            sonuc["degisen"] += r["degisen"]
        except Exception:  # noqa: BLE001
            logger.exception("OKR dönemi yenilenemedi (%s)", d.id)
            await db.rollback()
    sonuc["hatirlatma"] = await hatirlatmalari_gonder(db, an)
    return sonuc


async def haftalik_ozet_satirlari(db: AsyncSession, an: datetime) -> List[Dict[str, Any]]:
    """Ajansın KENDİ OKR'ları: 7+ gündür güncellenmemiş elle KR'ler (hatırlatma gitmiş olsa da)."""
    satirlar = []
    for kr, h, d in await _bayat_krler(db, an, s.AJANS_KAPSAMI, hatirlatilmamis=False):
        son = s.utc(kr.son_checkin_at) or s.utc(kr.created_at) or an
        satirlar.append({"kr": kr.baslik, "hedef": h.baslik, "sahip": kr.sahip or h.sahip, "gun": max(0, (an - son).days)})
    satirlar.sort(key=lambda x: -x["gun"])
    return satirlar


# ---------------------------------------------------------------------------
# Kapanış ve taşıma
# ---------------------------------------------------------------------------
async def kopyala(db: AsyncSession, h: OkrHedefler, krler: Sequence[KR], hedef_donem: OkrDonemler, kisi: Optional[str]) -> OkrHedefler:
    """Açık KR'lerin sonraki döneme kopyası: hedef (aynı başlık/sahip/üst/görünürlük, `tasindi_kaynak_id`) + KR'ler
    (başlangıç/hedef/mevcut, kaynak ve kilometre taşları aynen; `tasindi_kaynak_id` — eski check-in geçmişine bağ)."""
    yeni = OkrHedefler(kapsam=h.kapsam, hesap_email=h.hesap_email, donem_id=hedef_donem.id, baslik=h.baslik, aciklama=h.aciklama,
                       sahip=h.sahip, ust_id=h.ust_id, gorunurluk=h.gorunurluk, durum="etkin", musteri_email=h.musteri_email,
                       musteri_paylasim=h.musteri_paylasim, tasindi_kaynak_id=h.id, sira=h.sira, olusturan=kisi)
    db.add(yeni)
    await db.flush()
    for kr in krler:
        db.add(KR(kapsam=kr.kapsam, hesap_email=kr.hesap_email, hedef_id=yeni.id, baslik=kr.baslik, tur=kr.tur, birim=kr.birim,
                  para_birimi=kr.para_birimi, baslangic_deger=kr.baslangic_deger, hedef_deger=kr.hedef_deger,
                  mevcut_deger=kr.mevcut_deger, yon=kr.yon, agirlik=kr.agirlik, sahip=kr.sahip,
                  kilometre_taslari=kr.kilometre_taslari, kaynak=kr.kaynak, kaynak_ayar=kr.kaynak_ayar, guven=kr.guven,
                  tasindi_kaynak_id=kr.id, sira=kr.sira))
    await db.flush()
    return yeni


async def tasima_gecmisi(db: AsyncSession, kr: KR, sinir: int = 5) -> List[Dict[str, Any]]:
    """Taşınmış KR'nin önceki dönemlerdeki kopyaları (en yeni önce) — "bağlantı geçmişi"."""
    sonuc = []
    simdiki = kr.tasindi_kaynak_id
    gorulen = set()
    while simdiki and simdiki not in gorulen and len(sonuc) < sinir:
        gorulen.add(simdiki)
        eski = (await db.execute(select(KR).where(KR.id == simdiki, KR.kapsam == kr.kapsam))).scalars().first()
        if eski is None:
            break
        h = (await db.execute(select(OkrHedefler).where(OkrHedefler.id == eski.hedef_id))).scalars().first()
        d = (await db.execute(select(OkrDonemler).where(OkrDonemler.id == h.donem_id))).scalars().first() if h else None
        sonuc.append({"kr_id": eski.id, "hedef_id": eski.hedef_id, "donem_id": d.id if d else None,
                      "donem": donem_sozlugu(d)["etiket"] if d else None, "ilerleme": round(kr_ilerlemesi(eski), 4),
                      "kapanis_puani": eski.kapanis_puani,
                      "checkin_sayisi": int((await db.execute(select(func.count(OkrCheckinler.id)).where(
                          OkrCheckinler.kr_id == eski.id))).scalar() or 0)})
        simdiki = eski.tasindi_kaynak_id
    return sonuc


async def kapsam_temizle(db: AsyncSession, hedef: OkrHedefler) -> None:
    """Hedef silinirken KR'leri ve check-in'leri de (aynı işlemde: çöp kutusunda birlikte geri gelir); alt hedeflerin
    üst bağı kalkar."""
    krler = (await db.execute(select(KR).where(KR.hedef_id == hedef.id))).scalars().all()
    for kr in krler:
        for c in (await db.execute(select(OkrCheckinler).where(OkrCheckinler.kr_id == kr.id))).scalars().all():
            await db.delete(c)
        await db.delete(kr)
    for alt in (await db.execute(select(OkrHedefler).where(OkrHedefler.ust_id == hedef.id, OkrHedefler.kapsam == hedef.kapsam))).scalars().all():
        alt.ust_id = None
    await db.delete(hedef)


__all__ = [
    "kr_sozlugu", "hedef_sozlugu", "donem_sozlugu", "checkin_sozlugu", "donem_ozeti", "kr_yenile", "donemi_yenile",
    "checkin_yaz", "hedef_denetle", "hatirlatmalari_gonder", "zamanli_bakim", "haftalik_ozet_satirlari", "kopyala",
]
