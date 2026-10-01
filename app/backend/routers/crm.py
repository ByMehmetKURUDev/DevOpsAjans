"""Faz 3C — CRM ve aday hunisi (modül `crm`, yalnız yönetici) + gömülebilir form.

Yönetici (`/api/v1/crm`, router düzeyinde `yonetici_gerekli`: oturumsuz 401, müşteri 403):
  GET    /meta                         aşamalar, sorumlu adayları, kaynaklar, türler
  GET    /adaylar                      liste (?asama, sorumlu, kaynak, etiket, ara, siralama, sayfa, boyut)
  POST   /adaylar                      elle aday (aynı e-postada açık aday varsa 409)
  GET    /kanban                       aşama başına adaylar + sayı + toplam değer (?sorumlu, kaynak, ara)
  GET    /adaylar/{id}                 ayrıntı: aktiviteler, bağlı kayıtlar, KVKK onayları, puan ayrıntısı
  PATCH  /adaylar/{id}                 alan güncelle (puan yeniden hesaplanır)
  DELETE /adaylar/{id}                 sil — çöp kutusuna (aktivitelerle birlikte)
  POST   /adaylar/{id}/asama           {asama, kaybedilme_nedeni?} — aktivite + asama_degisme_at
  POST   /adaylar/{id}/aktivite        {tur: not|arama|eposta|toplanti, metin}
  POST   /adaylar/{id}/donustur        müşteri daveti (client_invite akışı) + "kazanıldı"
  GET    /asamalar                     aşamalar + aday sayıları
  POST   /asamalar                     {ad, ceviriler?, renk?, tur?, olasilik?}
  PUT    /asamalar/sira                {anahtarlar: [...]} (hepsi, yeni sırayla)
  PATCH  /asamalar/{anahtar}           ad / çeviriler / renk / tür / olasılık
  DELETE /asamalar/{anahtar}?hedef=    içinde aday varsa `hedef` zorunlu (409 tasima_gerekli)
  GET    /ozet                         huni dönüşümü, kaynaklar, aşama süreleri, bu ay kazanılan
  POST   /ice-aktar                    geçmiş talepler + fiyat teklifleri (idempotent)
  GET    /formlar · POST /formlar · PATCH /formlar/{id} · DELETE /formlar/{id}

Herkese açık (`/api/v1/crm/form/{genel_anahtar}`; kurallar `services/crm_form.py`):
  GET    tanım (seçili dilde etiketler + süre jetonu)
  POST   gönderim (köken, hız sınırı, bal küpü, süre, KVKK, alan uzunlukları)
"""

import json
import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from models.crm import (
    CrmAdaylari,
    CrmAktiviteler,
    CrmAsamalari,
    CrmBagliKayitlar,
    CrmFormGonderimleri,
    CrmFormlari,
)
from services import crm as servis
from services import crm_form as formlar
from services import pazarlama_izni
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri
from utils.istemci_ip import istemci_ip, ip_ozeti

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/crm", tags=["crm"], dependencies=[Depends(yonetici_gerekli)])
acik_router = APIRouter(prefix="/api/v1/crm/form", tags=["crm"])

#: IP başına 10 dakikada en çok 5 form gönderimi.
_form_hizi = HizSiniri(5, 600.0)
KANBAN_SINIRI = 200
AKTIVITE_SINIRI = 300


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    _form_hizi.temizle()


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _yapan(request: Request) -> str:
    kullanici, _ = _yonetici_mi(request)
    return servis.eposta_duzelt(getattr(kullanici, "email", "")) or "yonetici"


async def _aday(db: AsyncSession, aday_id: int) -> CrmAdaylari:
    a = (await db.execute(select(CrmAdaylari).where(CrmAdaylari.id == aday_id))).scalars().first()
    if a is None:
        raise _hata(404, "aday_yok")
    return a


async def _asama(db: AsyncSession, anahtar: str) -> CrmAsamalari:
    a = (await db.execute(select(CrmAsamalari).where(CrmAsamalari.anahtar == (anahtar or "").strip()))).scalars().first()
    if a is None:
        raise _hata(404, "asama_yok")
    return a


# ---------------------------------------------------------------------------
# Aday alanları doğrulama
# ---------------------------------------------------------------------------
def _metin(veri: Dict[str, Any], ad: str, sinir: int, tek_satir: bool = True) -> Optional[str]:
    ham = veri.get(ad)
    if ham is None:
        return None
    if not isinstance(ham, (str, int, float)):
        raise _hata(400, "alan_gecersiz", alan=ad)
    s = str(ham).strip()
    if tek_satir:
        s = " ".join(s.split())
    if len(s) > sinir:
        raise _hata(400, "alan_uzun", alan=ad, en_cok=sinir)
    return s or None


def _aday_alanlari(veri: Dict[str, Any], yeni: bool) -> Dict[str, Any]:
    S = servis.SINIR
    sonuc: Dict[str, Any] = {}
    if "ad" in veri or yeni:
        ad = _metin(veri, "ad", S["ad"])
        if not ad:
            raise _hata(400, "alan_gerekli", alan="ad")
        sonuc["ad"] = ad
    for ad, sinir, tek in (("firma", S["firma"], True), ("telefon", S["telefon"], True), ("notlar", S["notlar"], False),
                           ("sonraki_adim", S["sonraki_adim"], True), ("kaybedilme_nedeni", S["kaybedilme_nedeni"], False),
                           ("butce", S["butce"], True)):
        if ad in veri:
            sonuc[ad] = _metin(veri, ad, sinir, tek)
    if "email" in veri:
        e = servis.eposta_duzelt(_metin(veri, "email", S["email"]))
        if e and not servis.eposta_gecerli(e):
            raise _hata(400, "eposta_gecersiz", alan="email")
        sonuc["email"] = e or None
    if "deger_tahmini" in veri:
        d = veri.get("deger_tahmini")
        if d in (None, ""):
            sonuc["deger_tahmini"] = None
        else:
            try:
                d = float(d)
            except (TypeError, ValueError):
                raise _hata(400, "alan_gecersiz", alan="deger_tahmini")
            if d < 0 or d > 1e12 or d != d:
                raise _hata(400, "alan_gecersiz", alan="deger_tahmini")
            sonuc["deger_tahmini"] = round(d, 2)
    if "para_birimi" in veri:
        p = str(veri.get("para_birimi") or "").upper()
        if p not in servis.PARA_BIRIMLERI:
            raise _hata(400, "alan_gecersiz", alan="para_birimi")
        sonuc["para_birimi"] = p
    if "olasilik" in veri:
        o = veri.get("olasilik")
        if o in (None, ""):
            sonuc["olasilik"] = None
        else:
            if isinstance(o, bool) or not isinstance(o, (int, float)) or int(o) != o or not 0 <= int(o) <= 100:
                raise _hata(400, "alan_gecersiz", alan="olasilik")
            sonuc["olasilik"] = int(o)
    if "sorumlu" in veri:
        s = servis.eposta_duzelt(_metin(veri, "sorumlu", S["email"]))
        if s and not servis.eposta_gecerli(s):
            raise _hata(400, "eposta_gecersiz", alan="sorumlu")
        sonuc["sorumlu"] = s or None
    if "etiketler" in veri:
        try:
            sonuc["etiketler"] = json.dumps(servis.etiketleri_duzelt(veri.get("etiketler")), ensure_ascii=False)
        except ValueError as h:
            raise _hata(400, str(h), alan="etiketler")
    if "sonraki_adim_tarihi" in veri:
        ham = veri.get("sonraki_adim_tarihi")
        t = servis.tarih_coz(ham)
        if ham not in (None, "") and t is None:
            raise _hata(400, "alan_gecersiz", alan="sonraki_adim_tarihi")
        sonuc["sonraki_adim_tarihi"] = t
    if "kaynak" in veri:
        k = str(veri.get("kaynak") or "")
        if k not in servis.KAYNAKLAR:
            raise _hata(400, "alan_gecersiz", alan="kaynak")
        sonuc["kaynak"] = k
    # Faz 4G: pazarlama izni panelden VERİLEMEZ (açık rıza kişinin kendisinden
    # gelir: form ya da site analizi kutusu); yalnız geri alınabilir — kişi
    # vazgeçtiğini bildirdiğinde. Gönderim kayıtlarındaki izin kanıtı kalıyor.
    if "pazarlama_izni" in veri:
        if veri.get("pazarlama_izni") is not False:
            raise _hata(400, "alan_gecersiz", alan="pazarlama_izni")
        sonuc.update(pazarlama_izni_at=None, pazarlama_izni_kaynak=None, pazarlama_metin_surumu=None)
    return sonuc


# ---------------------------------------------------------------------------
# Meta, liste, kanban
# ---------------------------------------------------------------------------
@yonetici_router.get("/meta")
async def meta(db: AsyncSession = Depends(get_db)):
    from models.staff import Staff
    from services.notify import admin_recipients

    await servis.asamalari_hazirla(db)
    sorumlular: List[Dict[str, Any]] = []
    gorulen = set()
    for a in await admin_recipients(db):
        e = servis.eposta_duzelt(a.get("email"))
        if e and e not in gorulen:
            gorulen.add(e)
            sorumlular.append({"email": e, "ad": None, "rol": "yonetici"})
    for s in (await db.execute(select(Staff).order_by(Staff.ad))).scalars().all():
        e = servis.eposta_duzelt(s.email)
        if e and e not in gorulen and s.aktif is not False:
            gorulen.add(e)
            sorumlular.append({"email": e, "ad": s.ad, "rol": s.rol or "calisan"})
    return {
        "asamalar": [servis.asama_sozlugu(a) for a in await servis.asamalar(db)],
        "sorumlular": sorumlular,
        "kaynaklar": list(servis.KAYNAKLAR),
        "aktivite_turleri": list(servis.ELLE_AKTIVITE_TURLERI),
        "para_birimleri": list(servis.PARA_BIRIMLERI),
        "renkler": list(servis.RENKLER),
        "siralamalar": list(servis.SIRALAMALAR),
        "puan_kurallari": {
            "kaynak": servis.KAYNAK_PUANI, "en_cok": servis.PUAN_EN_COK,
            "kapsam_esikleri": [list(e) for e in servis.KAPSAM_ESIKLERI],
            "etkilesim_puani": servis.ETKILESIM_PUANI, "alan_adi": servis.ALAN_ADI_PUANI,
        },
    }


def _suzgecler(sorgu, *, asama=None, sorumlu=None, kaynak=None, etiket=None, ara=None):
    if asama:
        sorgu = sorgu.where(CrmAdaylari.asama == asama)
    if sorumlu == "-":
        sorgu = sorgu.where(or_(CrmAdaylari.sorumlu.is_(None), CrmAdaylari.sorumlu == ""))
    elif sorumlu:
        sorgu = sorgu.where(CrmAdaylari.sorumlu == servis.eposta_duzelt(sorumlu))
    if kaynak:
        sorgu = sorgu.where(CrmAdaylari.kaynak == kaynak)
    if etiket:
        e = " ".join(str(etiket).split()).lower()
        sorgu = sorgu.where(CrmAdaylari.etiketler.like(f"%{json.dumps(e, ensure_ascii=False)}%"))
    if ara:
        a = f"%{str(ara).strip()[:100]}%"
        sorgu = sorgu.where(or_(
            CrmAdaylari.ad.ilike(a), CrmAdaylari.firma.ilike(a), CrmAdaylari.email.ilike(a), CrmAdaylari.telefon.ilike(a)
        ))
    return sorgu


def _siralama(ad: str):
    ters = ad.startswith("-")
    alan = ad.lstrip("-")
    sutun = getattr(CrmAdaylari, alan)
    if alan == "sonraki_adim_tarihi":
        # Tarihi olmayanlar her iki yönde de sonda.
        return [sutun.is_(None), sutun.desc() if ters else sutun.asc(), CrmAdaylari.id.desc()]
    return [sutun.desc() if ters else sutun.asc(), CrmAdaylari.id.desc()]


@yonetici_router.get("/adaylar")
async def aday_listesi(
    asama: Optional[str] = Query(None),
    sorumlu: Optional[str] = Query(None),
    kaynak: Optional[str] = Query(None),
    etiket: Optional[str] = Query(None),
    ara: Optional[str] = Query(None),
    siralama: str = Query("-puan"),
    sayfa: int = Query(1, ge=1, le=10000),
    boyut: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    if siralama not in servis.SIRALAMALAR:
        raise _hata(400, "siralama_gecersiz")
    await servis.asamalari_hazirla(db)
    suz = dict(asama=asama, sorumlu=sorumlu, kaynak=kaynak, etiket=etiket, ara=ara)
    toplam = (await db.execute(_suzgecler(select(func.count(CrmAdaylari.id)), **suz))).scalar() or 0
    satirlar = (
        await db.execute(
            _suzgecler(select(CrmAdaylari), **suz).order_by(*_siralama(siralama)).offset((sayfa - 1) * boyut).limit(boyut)
        )
    ).scalars().all()
    return {"items": [servis.aday_sozlugu(a) for a in satirlar], "toplam": toplam, "sayfa": sayfa, "boyut": boyut}


@yonetici_router.get("/kanban")
async def kanban(
    sorumlu: Optional[str] = Query(None),
    kaynak: Optional[str] = Query(None),
    etiket: Optional[str] = Query(None),
    ara: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    await servis.asamalari_hazirla(db)
    liste = await servis.asamalar(db)
    adaylar = (
        await db.execute(
            _suzgecler(select(CrmAdaylari), sorumlu=sorumlu, kaynak=kaynak, etiket=etiket, ara=ara)
            .order_by(CrmAdaylari.puan.desc(), CrmAdaylari.id.desc())
        )
    ).scalars().all()
    gruplar: Dict[str, List[CrmAdaylari]] = {a.anahtar: [] for a in liste}
    for a in adaylar:
        gruplar.setdefault(a.asama, []).append(a)
    sutunlar = []
    for a in liste:
        grup = gruplar.get(a.anahtar, [])
        toplam: Dict[str, float] = {}
        for x in grup:
            if x.deger_tahmini:
                toplam[x.para_birimi or "TRY"] = round(toplam.get(x.para_birimi or "TRY", 0.0) + float(x.deger_tahmini), 2)
        sutunlar.append({
            **servis.asama_sozlugu(a), "sayi": len(grup), "toplam_deger": toplam,
            "adaylar": [servis.aday_sozlugu(x) for x in grup[:KANBAN_SINIRI]],
        })
    return {"asamalar": sutunlar}


# ---------------------------------------------------------------------------
# Aday CRUD
# ---------------------------------------------------------------------------
@yonetici_router.post("/adaylar", status_code=201)
async def aday_olustur(request: Request, veri: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    await servis.asamalari_hazirla(db)
    alanlar = _aday_alanlari(veri, yeni=True)
    liste = await servis.asamalar(db)
    istenen = (veri.get("asama") or "").strip()
    hedef = next((a for a in liste if a.anahtar == istenen), None) if istenen else servis.ilk_asama(liste)
    if hedef is None:
        raise _hata(400, "asama_yok")
    if alanlar.get("email"):
        mevcut = await db.run_sync(lambda s: servis._acik_aday_sync(s.connection(), alanlar["email"]))
        if mevcut:
            raise _hata(409, "ayni_eposta_acik_aday", aday_id=mevcut)
    an = servis.simdi()
    degerler = {"kaynak": "manuel", "para_birimi": "TRY", "olasilik": hedef.olasilik, **alanlar}
    aday = CrmAdaylari(**degerler, asama=hedef.anahtar, created_at=an, updated_at=an, asama_degisme_at=an, puan=0)
    db.add(aday)
    await db.flush()
    db.add(CrmAktiviteler(
        aday_id=aday.id, tur="sistem", olay="aday_olustu",
        veri=json.dumps({"kaynak": aday.kaynak, "elle": True}, ensure_ascii=False), yapan=_yapan(request), zaman=an,
    ))
    await db.flush()
    await servis.puani_guncelle(db, aday)
    await db.commit()
    return servis.aday_sozlugu(aday, ayrintili=True)


async def _bagli_kayitlar(db: AsyncSession, aday_id: int) -> List[Dict[str, Any]]:
    from models.inquiries import Inquiries
    from models.pricing import Pricing_inquiries

    baglar = (
        await db.execute(select(CrmBagliKayitlar).where(CrmBagliKayitlar.aday_id == aday_id).order_by(CrmBagliKayitlar.id))
    ).scalars().all()
    kimlikler: Dict[str, List[int]] = {}
    for b in baglar:
        kimlikler.setdefault(b.tablo, []).append(b.kayit_id)
    talepler = {
        t.id: t for t in (await db.execute(select(Inquiries).where(Inquiries.id.in_(kimlikler.get("inquiries", []))))).scalars().all()
    } if kimlikler.get("inquiries") else {}
    teklifler = {
        t.id: t for t in (
            await db.execute(select(Pricing_inquiries).where(Pricing_inquiries.id.in_(kimlikler.get("pricing_inquiries", []))))
        ).scalars().all()
    } if kimlikler.get("pricing_inquiries") else {}
    gonderimler = {
        g.id: g for g in (
            await db.execute(select(CrmFormGonderimleri).where(CrmFormGonderimleri.id.in_(kimlikler.get("crm_form_gonderimleri", []))))
        ).scalars().all()
    } if kimlikler.get("crm_form_gonderimleri") else {}
    form_adlari: Dict[int, str] = {}
    if gonderimler:
        form_adlari = {
            f.id: f.ad for f in (
                await db.execute(select(CrmFormlari).where(CrmFormlari.id.in_({g.form_id for g in gonderimler.values()})))
            ).scalars().all()
        }

    sonuc = []
    for b in baglar:
        d: Dict[str, Any] = {"tablo": b.tablo, "kayit_id": b.kayit_id, "baglanti_at": servis.iso(b.created_at)}
        if b.tablo == "inquiries":
            t = talepler.get(b.kayit_id)
            d.update({"silinmis": True} if t is None else {
                "baslik": t.subject or (t.message or "")[:80], "kaynak": t.source, "durum": t.status,
                "zaman": servis.iso(t.created_at),
            })
        elif b.tablo == "pricing_inquiries":
            t = teklifler.get(b.kayit_id)
            d.update({"silinmis": True} if t is None else {
                "baslik": " / ".join(p for p in (t.scale_kod, t.profile_kod, t.period) if p) or (t.ai_pm_tier_kod or ""),
                "tutar": t.hesaplanan_tutar, "para_birimi": "USD", "durum": t.durum or "bekliyor",
                "zaman": servis.iso(t.created_at),
            })
        elif b.tablo == "crm_form_gonderimleri":
            g = gonderimler.get(b.kayit_id)
            d.update({"silinmis": True} if g is None else {
                "baslik": form_adlari.get(g.form_id) or f"#{g.form_id}", "form_id": g.form_id,
                "kvkk_surum": g.kvkk_surum, "kvkk_onay_at": servis.iso(g.kvkk_onay_at), "koken": g.koken,
                "pazarlama_izni": bool(g.pazarlama_izni), "pazarlama_izni_at": servis.iso(g.pazarlama_izni_at),
                "pazarlama_metin_surumu": g.pazarlama_metin_surumu,
                "zaman": servis.iso(g.created_at),
            })
        sonuc.append(d)
    return sonuc


@yonetici_router.get("/adaylar/{aday_id}")
async def aday_ayrinti(aday_id: int, db: AsyncSession = Depends(get_db)):
    aday = await _aday(db, aday_id)
    aktiviteler = (
        await db.execute(
            select(CrmAktiviteler).where(CrmAktiviteler.aday_id == aday_id)
            .order_by(CrmAktiviteler.zaman.desc(), CrmAktiviteler.id.desc()).limit(AKTIVITE_SINIRI)
        )
    ).scalars().all()
    return {
        "aday": servis.aday_sozlugu(aday, ayrintili=True),
        "aktiviteler": [servis.aktivite_sozlugu(k) for k in aktiviteler],
        "bagli_kayitlar": await _bagli_kayitlar(db, aday_id),
    }


@yonetici_router.patch("/adaylar/{aday_id}")
async def aday_guncelle(aday_id: int, veri: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    aday = await _aday(db, aday_id)
    alanlar = _aday_alanlari(veri, yeni=False)
    if "sonraki_adim_tarihi" in alanlar and alanlar["sonraki_adim_tarihi"] != aday.sonraki_adim_tarihi:
        aday.hatirlatma_tarihi = None  # yeni tarih için yeniden hatırlat
    for ad, deger in alanlar.items():
        setattr(aday, ad, deger)
    aday.updated_at = servis.simdi()
    await servis.puani_guncelle(db, aday)
    await db.commit()
    return servis.aday_sozlugu(aday, ayrintili=True)


@yonetici_router.delete("/adaylar/{aday_id}")
async def aday_sil(aday_id: int, db: AsyncSession = Depends(get_db)):
    """Aday + aktiviteleri çöp kutusuna (aynı grup: geri alınca birlikte döner).

    Bağlı kayıt satırları ve KVKK onay kayıtları silinmiyor (bkz. models/crm.py).
    """
    aday = await _aday(db, aday_id)
    for k in (await db.execute(select(CrmAktiviteler).where(CrmAktiviteler.aday_id == aday_id))).scalars().all():
        await db.delete(k)
    await db.delete(aday)
    await db.commit()
    return {"silindi": True, "id": aday_id}


@yonetici_router.post("/adaylar/{aday_id}/asama")
async def aday_asama(aday_id: int, request: Request, veri: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    aday = await _aday(db, aday_id)
    hedef = await _asama(db, str(veri.get("asama") or ""))
    neden = _metin(veri, "kaybedilme_nedeni", servis.SINIR["kaybedilme_nedeni"], tek_satir=False) if "kaybedilme_nedeni" in veri else None
    degisti = await servis.asama_tasi(db, aday, hedef, yapan=_yapan(request), kaybedilme_nedeni=neden)
    if degisti:
        aday.updated_at = servis.simdi()
    await db.commit()
    return {"aday": servis.aday_sozlugu(aday, ayrintili=True), "degisti": degisti}


@yonetici_router.post("/adaylar/{aday_id}/aktivite", status_code=201)
async def aday_aktivite(aday_id: int, request: Request, veri: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    aday = await _aday(db, aday_id)
    tur = str(veri.get("tur") or "")
    if tur not in servis.ELLE_AKTIVITE_TURLERI:
        raise _hata(400, "alan_gecersiz", alan="tur")
    metin = _metin(veri, "metin", servis.SINIR["metin"], tek_satir=False)
    if not metin:
        raise _hata(400, "alan_gerekli", alan="metin")
    k = CrmAktiviteler(aday_id=aday.id, tur=tur, metin=metin, yapan=_yapan(request), zaman=servis.simdi())
    db.add(k)
    await db.flush()
    aday.updated_at = servis.simdi()
    await servis.puani_guncelle(db, aday)
    await db.commit()
    return {"aktivite": servis.aktivite_sozlugu(k), "aday": servis.aday_sozlugu(aday, ayrintili=True)}


@yonetici_router.post("/adaylar/{aday_id}/donustur")
async def aday_donustur(aday_id: int, request: Request, veri: Optional[Dict[str, Any]] = Body(None), db: AsyncSession = Depends(get_db)):
    """Müşteriye dönüştür: mevcut müşteri davet akışı (`routers/client_invite.py`) + "kazanıldı"."""
    from routers.client_invite import musteri_davet_et

    veri = veri or {}
    aday = await _aday(db, aday_id)
    eposta = servis.eposta_duzelt(aday.email)
    if not servis.eposta_gecerli(eposta):
        raise _hata(400, "eposta_yok")
    liste = await servis.asamalar(db)
    kazanildi = servis.ilk_asama(liste, "kazanildi")
    if kazanildi is None:
        raise _hata(409, "kazanildi_asamasi_yok")
    proje = _metin(veri, "proje_basligi", 160) or aday.firma or ""
    davet = await musteri_davet_et(db, eposta, aday.ad or "", proje)

    aday = await _aday(db, aday_id)
    yapan = _yapan(request)
    await servis.asama_tasi(db, aday, kazanildi, yapan=yapan)
    aday.musteri_email = eposta
    aday.updated_at = servis.simdi()
    db.add(CrmAktiviteler(
        aday_id=aday.id, tur="sistem", olay="donusturuldu",
        veri=json.dumps({"musteri_email": eposta, "davet": davet.email_status}, ensure_ascii=False),
        yapan=yapan, zaman=servis.simdi(),
    ))
    await db.commit()
    return {"aday": servis.aday_sozlugu(aday, ayrintili=True), "davet": davet.model_dump()}


# ---------------------------------------------------------------------------
# Aşama yönetimi
# ---------------------------------------------------------------------------
def _asama_alanlari(veri: Dict[str, Any], yeni: bool) -> Dict[str, Any]:
    sonuc: Dict[str, Any] = {}
    if "ad" in veri or yeni:
        ad = _metin(veri, "ad", servis.SINIR["asama_ad"])
        if not ad:
            raise _hata(400, "alan_gerekli", alan="ad")
        sonuc["ad"] = ad
    if "ceviriler" in veri:
        sonuc["ceviriler"] = json.dumps(servis.ceviriler_duzelt(veri.get("ceviriler")), ensure_ascii=False)
    if "renk" in veri:
        r = str(veri.get("renk") or "")
        if r not in servis.RENKLER:
            raise _hata(400, "alan_gecersiz", alan="renk")
        sonuc["renk"] = r
    if "tur" in veri:
        t = str(veri.get("tur") or "")
        if t not in servis.ASAMA_TURLERI:
            raise _hata(400, "alan_gecersiz", alan="tur")
        sonuc["tur"] = t
    if "olasilik" in veri:
        o = veri.get("olasilik")
        if o in (None, ""):
            sonuc["olasilik"] = None
        elif isinstance(o, bool) or not isinstance(o, (int, float)) or int(o) != o or not 0 <= int(o) <= 100:
            raise _hata(400, "alan_gecersiz", alan="olasilik")
        else:
            sonuc["olasilik"] = int(o)
    return sonuc


async def _aday_sayilari(db: AsyncSession) -> Dict[str, int]:
    return {
        a: int(n) for a, n in (await db.execute(select(CrmAdaylari.asama, func.count(CrmAdaylari.id)).group_by(CrmAdaylari.asama))).all()
    }


@yonetici_router.get("/asamalar")
async def asama_listesi(db: AsyncSession = Depends(get_db)):
    await servis.asamalari_hazirla(db)
    sayilar = await _aday_sayilari(db)
    return {"asamalar": [servis.asama_sozlugu(a, sayilar.get(a.anahtar, 0)) for a in await servis.asamalar(db)]}


@yonetici_router.post("/asamalar", status_code=201)
async def asama_ekle(veri: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    await servis.asamalari_hazirla(db)
    alanlar = _asama_alanlari(veri, yeni=True)
    liste = await servis.asamalar(db)
    if len(liste) >= 20:
        raise _hata(409, "asama_sayisi")
    anahtar = servis.yeni_asama_anahtari(alanlar["ad"], [a.anahtar for a in liste])
    a = CrmAsamalari(
        anahtar=anahtar, sira=(max((x.sira for x in liste), default=0) + 10),
        **{"renk": "slate", "tur": "acik", **alanlar},
    )
    db.add(a)
    await db.commit()
    return servis.asama_sozlugu(a, 0)


@yonetici_router.put("/asamalar/sira")
async def asama_sirala(veri: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    anahtarlar = veri.get("anahtarlar")
    liste = await servis.asamalar(db)
    if not isinstance(anahtarlar, list) or sorted(map(str, anahtarlar)) != sorted(a.anahtar for a in liste):
        raise _hata(400, "sira_gecersiz")
    harita = {a.anahtar: a for a in liste}
    for i, k in enumerate(anahtarlar):
        harita[str(k)].sira = (i + 1) * 10
    await db.commit()
    return {"asamalar": [servis.asama_sozlugu(a) for a in await servis.asamalar(db)]}


@yonetici_router.patch("/asamalar/{anahtar}")
async def asama_guncelle(anahtar: str, veri: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    a = await _asama(db, anahtar)
    alanlar = _asama_alanlari(veri, yeni=False)
    if "tur" in alanlar and alanlar["tur"] != a.tur:
        ayni = (await db.execute(select(func.count(CrmAsamalari.id)).where(CrmAsamalari.tur == a.tur))).scalar() or 0
        if ayni <= 1:
            raise _hata(409, "son_tur_asamasi", tur=a.tur)
    for k, v in alanlar.items():
        setattr(a, k, v)
    await db.commit()
    return servis.asama_sozlugu(a, (await _aday_sayilari(db)).get(a.anahtar, 0))


@yonetici_router.delete("/asamalar/{anahtar}")
async def asama_sil(anahtar: str, request: Request, hedef: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    a = await _asama(db, anahtar)
    ayni = (await db.execute(select(func.count(CrmAsamalari.id)).where(CrmAsamalari.tur == a.tur))).scalar() or 0
    if ayni <= 1:
        raise _hata(409, "son_tur_asamasi", tur=a.tur)
    adaylar = (await db.execute(select(CrmAdaylari).where(CrmAdaylari.asama == a.anahtar))).scalars().all()
    tasinan = 0
    if adaylar:
        if not hedef:
            raise _hata(409, "tasima_gerekli", sayi=len(adaylar))
        if hedef == a.anahtar:
            raise _hata(400, "hedef_gecersiz")
        hedef_asama = await _asama(db, hedef)
        yapan = _yapan(request)
        for x in adaylar:
            if await servis.asama_tasi(db, x, hedef_asama, yapan=yapan, sebep="asama_silindi"):
                tasinan += 1
    for f in (await db.execute(select(CrmFormlari).where(CrmFormlari.varsayilan_asama == a.anahtar))).scalars().all():
        f.varsayilan_asama = None
    await db.delete(a)
    await db.commit()
    return {"silindi": True, "tasinan": tasinan}


# ---------------------------------------------------------------------------
# Özet ve içe aktarma
# ---------------------------------------------------------------------------
@yonetici_router.get("/ozet")
async def ozet(db: AsyncSession = Depends(get_db)):
    await servis.asamalari_hazirla(db)
    return await servis.ozet(db)


@yonetici_router.post("/ice-aktar")
async def ice_aktar(request: Request, db: AsyncSession = Depends(get_db)):
    return await servis.gecmisi_ice_aktar(db, _yapan(request))


# ---------------------------------------------------------------------------
# Form tanımları (panel)
# ---------------------------------------------------------------------------
def _form_hatasi(h: formlar.FormHatasi) -> HTTPException:
    return _hata(h.durum, h.kod, **h.ek)


async def _form(db: AsyncSession, form_id: int) -> CrmFormlari:
    f = (await db.execute(select(CrmFormlari).where(CrmFormlari.id == form_id))).scalars().first()
    if f is None:
        raise _hata(404, "form_yok")
    return f


@yonetici_router.get("/formlar")
async def form_listesi(db: AsyncSession = Depends(get_db)):
    import os

    satirlar = (await db.execute(select(CrmFormlari).order_by(CrmFormlari.id.desc()))).scalars().all()
    return {
        "formlar": [formlar.form_sozlugu(f) for f in satirlar],
        "site_adresi": (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/"),
        "her_zaman_izinli": formlar.site_alan_adlari(),
        "alan_adlari": list(formlar.ALAN_ADLARI),
        "alan_sinirlari": formlar.ALAN_SINIRLARI,
    }


@yonetici_router.post("/formlar", status_code=201)
async def form_olustur(veri: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    await servis.asamalari_hazirla(db)
    anahtarlar = [a.anahtar for a in await servis.asamalar(db)]
    try:
        alanlar = formlar.tanimi_dogrula(veri, None, anahtarlar)
    except formlar.FormHatasi as h:
        raise _form_hatasi(h)
    f = CrmFormlari(genel_anahtar=formlar.yeni_genel_anahtar(), kvkk_surum=1, gonderim_sayisi=0, **{"aktif": True, **alanlar})
    db.add(f)
    await db.commit()
    return formlar.form_sozlugu(f)


@yonetici_router.patch("/formlar/{form_id}")
async def form_guncelle(form_id: int, veri: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    f = await _form(db, form_id)
    anahtarlar = [a.anahtar for a in await servis.asamalar(db)]
    try:
        alanlar = formlar.tanimi_dogrula(veri, f, anahtarlar)
    except formlar.FormHatasi as h:
        raise _form_hatasi(h)
    for k, v in alanlar.items():
        setattr(f, k, v)
    await db.commit()
    return formlar.form_sozlugu(f)


@yonetici_router.delete("/formlar/{form_id}")
async def form_sil(form_id: int, db: AsyncSession = Depends(get_db)):
    f = await _form(db, form_id)
    await db.delete(f)
    await db.commit()
    return {"silindi": True, "id": form_id}


# ---------------------------------------------------------------------------
# Herkese açık form uçları
# ---------------------------------------------------------------------------
#: Köken reddedilince yanıta konan işaret: CORS başlıklarını ara katman siliyor.
RET = {"x-mk-cors": "ret", "Cache-Control": "no-store"}


async def _acik_form(db: AsyncSession, anahtar: str) -> CrmFormlari:
    f = (
        await db.execute(
            select(CrmFormlari).where(CrmFormlari.genel_anahtar == (anahtar or "")[:64], CrmFormlari.aktif.is_(True))
        )
    ).scalars().first()
    if f is None:
        raise HTTPException(status_code=404, detail={"kod": "form_yok"}, headers={"Cache-Control": "no-store"})
    return f


def _koken_denetle(request: Request, f: CrmFormlari) -> Optional[str]:
    koken = request.headers.get("origin")
    if not formlar.koken_izinli_mi(koken, f.izinli_alanlar):
        raise HTTPException(status_code=403, detail={"kod": "alan_adi_izinsiz"}, headers=RET)
    return (koken or "")[:200] or None


@acik_router.get("/{anahtar}")
async def acik_form_tanimi(anahtar: str, request: Request, dil: str = Query("tr"), db: AsyncSession = Depends(get_db)):
    f = await _acik_form(db, anahtar)
    _koken_denetle(request, f)
    return JSONResponse(formlar.acik_tanim(f, dil), headers={"Cache-Control": "no-store"})


@acik_router.post("/{anahtar}")
async def acik_form_gonder(anahtar: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Gövde JSON (betik `text/plain` gönderiyor: tarayıcı ön kontrol yapmasın)."""
    ip = ip_ozeti(istemci_ip(request))
    if not _form_hizi.izin_var_mi(ip):
        raise _hata(429, "cok_fazla_istek")
    ham = await request.body()
    if len(ham) > formlar.GOVDE_SINIRI:
        raise _hata(413, "govde_buyuk")
    try:
        govde = json.loads(ham.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise _hata(400, "govde_gecersiz")
    if not isinstance(govde, dict):
        raise _hata(400, "govde_gecersiz")

    f = await _acik_form(db, anahtar)
    koken = _koken_denetle(request, f)
    dil = formlar.dil_sec(govde.get("dil"))
    yanit = {"ok": True, "tesekkur": f.tesekkur_metni or formlar.ETIKETLER[dil]["tesekkur"], "yonlendirme": f.yonlendirme_adresi}

    # Bal küpü: bot "başarılı" görsün, hiçbir şey kaydedilmesin.
    if str(govde.get(formlar.BAL_KUPU) or "").strip():
        logger.info("CRM formu: bal küpü dolu, gönderim yok sayıldı (form %s)", f.id)
        return yanit
    try:
        formlar.jeton_dogrula(govde.get("jeton"), f.id)
        degerler = formlar.gonderimi_dogrula(f, govde)
    except formlar.FormHatasi as h:
        raise _form_hatasi(h)

    await servis.asamalari_hazirla(db)
    an = servis.simdi()
    # Faz 4G: pazarlama izni yalnız form soruyorsa ve kutu işaretliyse (JSON true).
    pazarlama = bool(f.pazarlama_izni_sor) and pazarlama_izni.izin_verildi_mi(govde.get("pazarlama_izni"))
    gonderim = CrmFormGonderimleri(
        form_id=f.id, kvkk_surum=int(f.kvkk_surum or 1), kvkk_metin_ozeti=formlar.kvkk_ozeti(f, dil), kvkk_onay_at=an,
        ip_ozeti=ip, koken=koken, created_at=an, pazarlama_izni=pazarlama,
        pazarlama_izni_at=an if pazarlama else None,
        pazarlama_metin_surumu=pazarlama_izni.surum_etiketi(dil) if pazarlama else None,
    )
    db.add(gonderim)
    await db.flush()
    sonuc = await servis.kayit_isle(db, servis.TalepGirdisi(
        tablo="crm_form_gonderimleri", kayit_id=gonderim.id, ad=degerler.get("ad"), email=degerler.get("email"),
        telefon=degerler.get("telefon"), firma=degerler.get("firma"), konu=f.baslik or f.ad,
        mesaj=degerler.get("mesaj"), kaynak="form", kaynak_ham=f.ad, butce=degerler.get("butce"),
        asama=f.varsayilan_asama, etiketler=servis.json_liste(f.varsayilan_etiketler),
        ek_veri={"form": f.ad, "form_id": f.id},
    ))
    gonderim.aday_id = sonuc["aday_id"] if sonuc else None
    if pazarlama:
        await pazarlama_izni.adaya_isle(db, gonderim.aday_id, an, f"form:{f.id}", gonderim.pazarlama_metin_surumu)
    f.gonderim_sayisi = int(f.gonderim_sayisi or 0) + 1
    f.son_gonderim_at = an
    await db.commit()

    if sonuc:
        aday = (await db.execute(select(CrmAdaylari).where(CrmAdaylari.id == sonuc["aday_id"]))).scalars().first()
        if aday is not None:
            await servis.yeni_aday_bildir(db, aday, yeni=sonuc["yeni"], form_adi=f.ad)
    return yanit


# `include_routers_from_package` demet de kabul ediyor.
router = (yonetici_router, acik_router)
