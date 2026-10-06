"""Faz 5R — Takvim ve randevu + toplantılar (Calendly benzeri).

Herkese açık (oturumsuz):
  GET  /api/v1/randevu/{slug}                       sayfa + aktif etkinlik türleri (görüntülenme arka planda; bot sayılmaz)
  GET  /api/v1/randevu/{slug}/ozet?tur=             paylaşım önizlemesi (Pages Function `functions/randevu/[[yol]].js`)
  GET  /api/v1/randevu/{slug}/{tur}                 tür ayrıntısı + soru formu (görüntülenme)
  GET  /api/v1/randevu/{slug}/{tur}/musaitlik?bas=YYYY-AA-GG&gun=N&tz=Bölge/Şehir
                                                    müsait başlangıçlar (UTC), ziyaretçinin gününe göre gruplu
  POST /api/v1/randevu/{slug}/{tur}/rezervasyon     rezervasyon: kilitli yer seçimi, hız sınırı + bal küpü
                                                    (`web_adresi`), onay e-postası (.ics REQUEST) ziyaretçiye ve sahibine
  GET  /api/v1/randevu/islem/{jeton}                imzalı yönetim bağlantısı: özet (girişsiz)
  POST /api/v1/randevu/islem/{jeton}/iptal          ziyaretçi iptali (iptal sınırına kadar; .ics CANCEL)
  GET  /api/v1/randevu/islem/{jeton}/musaitlik      yeniden planlama için müsaitlik (kendi randevusu engel sayılmaz)
  POST /api/v1/randevu/islem/{jeton}/yeniden        yeniden planla (aynı UID, SEQUENCE +1)
  GET  /api/v1/randevu/islem/{jeton}/takvim.ics     takvim dosyası (Apple / .ics)
  GET  /api/v1/randevu/besleme/{jeton}.ics          sahibin ICS abonelik beslemesi (gizli jeton; yenilenebilir)
  GET  /api/v1/randevu/gorsel/{anahtar}             sayfa logosu (WebP, değişmez)

Yönetici (`/api/v1/randevu/yonetim`) — ajansın kendi sayfası + bütün müşterilerinki.
Müşteri (`/api/v1/randevularim`; modül `randevu` açık + hesap ekibi izni `randevu`) — etkin hesabın sayfası:
  GET  /meta                         sınırlar ve seçenekler
  GET|POST ""                        sayfalar / yeni sayfa (hesap başına bir sayfa)
  GET|PUT|DELETE /{sid}              ayrıntı / ayarlar / sil (yaklaşan randevu varken 409)
  POST|DELETE /{sid}/logo            logo yükle (JPEG/PNG/WebP ≤ 5 MB → WebP) / kaldır
  POST /{sid}/besleme/yenile         ICS besleme adresini yenile (eskisi geçersiz)
  GET  /{sid}/qr?bicim=png|svg&tur=  sayfanın (ya da türün) QR'ı
  GET  /{sid}/analiz?gun=30          görüntülenme → rezervasyon dönüşümü
  GET|POST /{sid}/turler, PUT|DELETE /{sid}/turler/{tid}      etkinlik türleri (`tur_siniri` modül ayarı)
  GET|POST /{sid}/kisiler, PUT|DELETE /{sid}/kisiler/{kid}    ekip ve haftalık saatler
  GET|POST /{sid}/istisnalar, DELETE /{sid}/istisnalar/{iid}  tarih bazlı istisnalar
  GET  /{sid}/randevular?donem=yaklasan|gecmis|iptal (ya da bas/bit: hafta görünümü)
  GET  /{sid}/randevular/{rid}       ayrıntı
  POST /{sid}/randevular/{rid}/iptal sahibin iptali (ziyaretçiye e-posta + .ics CANCEL)
  PUT  /{sid}/randevular/{rid}/katilim  geldi / gelmedi (başlangıçtan sonra)

Kurallar: müşteri yalnız etkin hesabın sayfasını görür; modül kapalıysa 403 `modul_kapali`; sahibinin
modülü kapanan sayfa herkese 410. Ajans sayfasındaki randevu CRM'e aday + toplantı etkinliği olarak düşer;
müşteri randevuları CRM'e karışmaz.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from core.database import db_manager, get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from models.randevu import (
    RandevuGorselleri,
    RandevuIstisnalari,
    RandevuKisileri,
    RandevuOlaylari,
    Randevular,
    RandevuSayfalari,
    RandevuTurleri,
)
from services import dinamik_qr as qr
from services import randevu as s
from services import randevu_kayit as rk
from services.dosya_deposu import icerik_konumu
from sqlalchemy import delete, desc, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

MODUL = s.MODUL
IZIN = s.IZIN
VARSAYILAN_TUR_SINIRI = 5
EN_COK_TUR_YONETICI = 200

acik_router = APIRouter(prefix="/api/v1/randevu", tags=["randevu"])
besleme_router = APIRouter(prefix="/api/v1/randevu/besleme", tags=["randevu"])
islem_router = APIRouter(prefix="/api/v1/randevu/islem", tags=["randevu"])
gorsel_router = APIRouter(prefix="/api/v1/randevu/gorsel", tags=["randevu"])
yonetici_router = APIRouter(prefix="/api/v1/randevu/yonetim", tags=["randevu"], dependencies=[Depends(yonetici_gerekli)])
musteri_router = APIRouter(
    prefix="/api/v1/randevularim",
    tags=["randevu"],
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(IZIN))],
)

#: Panel (kişi başı): dakikada 60 yazma, 20 görsel/QR.
_yazma_hizi = HizSiniri(60, 60.0)
_gorsel_hizi = HizSiniri(20, 60.0)
#: Ziyaretçi (IP özeti + sayfa): 10 dakikada 5 rezervasyon; dakikada 120 müsaitlik sorgusu.
#: Faz 7H: rezervasyon ve yönetim bağlantısı sayaçları veritabanında (sunucu uyanınca sıfırlanmıyor).
_rezervasyon_hizi = KaliciHizSiniri("randevu-rez", 5, 600.0)
_musaitlik_hizi = HizSiniri(120, 60.0)
_olay_hizi = HizSiniri(60, 60.0)
#: Sayfa başına dakikada 30 rezervasyon (aynı anda çok IP'den gelen saldırıya karşı).
_sayfa_rezervasyon_hizi = KaliciHizSiniri("randevu-sayfa-rez", 30, 60.0)
#: Yönetim bağlantısı (IP özeti): dakikada 30; besleme (jeton): dakikada 30.
_islem_hizi = KaliciHizSiniri("randevu-islem", 30, 60.0)
_besleme_hizi = HizSiniri(30, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _gorsel_hizi, _rezervasyon_hizi, _musaitlik_hizi, _olay_hizi, _sayfa_rezervasyon_hizi,
              _islem_hizi, _besleme_hizi):
        h.temizle()


# ---------------------------------------------------------------------------
# Kapsam ve ortak yardımcılar
# ---------------------------------------------------------------------------
@dataclass
class Kapsam:
    yonetici: bool
    #: Müşteride etkin hesap; yöneticide None (bütün kayıtlar).
    hesap: Optional[str]
    kisi: str


def _yonetici_kapsami(request: Request) -> Kapsam:
    kullanici, _ = _yonetici_mi(request)
    return Kapsam(True, None, (getattr(kullanici, "email", "") or "").strip().lower())


def _musteri_kapsami(request: Request) -> Kapsam:
    baglam = izin_iste(request, IZIN)
    return Kapsam(False, baglam.hesap_email, baglam.kisi_email)


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _r_hatasi(h: s.RandevuHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _hiz(sinir: HizSiniri, anahtar: str) -> None:
    if not sinir.izin_var_mi(anahtar or "anonim"):
        raise _hata(429, "cok_hizli")


async def _kalici_hiz(*denemeler) -> None:
    """Faz 7H: herkese açık uçların veritabanı destekli sayacı ((sınırlayıcı, anahtar) çiftleri)."""
    if not await izin_ver(*denemeler):
        raise _hata(429, "cok_hizli")


def _gorsel_adresi(anahtar: Optional[str], mutlak: bool = False) -> Optional[str]:
    if not anahtar:
        return None
    yol = f"/api/v1/randevu/gorsel/{anahtar}"
    return f"{s.site_adresi()}{yol}" if mutlak else yol


def _sayfa_sozlugu(p: RandevuSayfalari, **ek: Any) -> Dict[str, Any]:
    jeton = s.besleme_jetonu(p.id, int(p.besleme_surumu or 1))
    return {
        "id": p.id,
        "hesap_email": p.hesap_email,
        "slug": p.slug,
        "adres_url": s.sayfa_adresi(p.slug),
        "baslik": p.baslik,
        "karsilama": p.karsilama or "",
        "logo": _gorsel_adresi(p.logo),
        "renk": p.renk,
        "saat_dilimi": p.saat_dilimi,
        "dil": p.dil,
        "arama_motoru": bool(p.arama_motoru),
        "tatilde_kapali": bool(p.tatilde_kapali),
        "hatirlatmalar": s.hatirlatmalar(p.hatirlatmalar),
        "iptal_sinir_dk": int(p.iptal_sinir_dk or 0),
        "saklama_gun": int(p.saklama_gun or s.VARSAYILAN_SAKLAMA_GUN),
        "aktif": bool(p.aktif),
        "besleme_adresi": s.besleme_adresi(jeton),
        "created_at": s.iso(p.created_at),
        "updated_at": s.iso(p.updated_at),
        **ek,
    }


def _tur_sozlugu(t: RandevuTurleri) -> Dict[str, Any]:
    return {
        "id": t.id,
        "sayfa_id": t.sayfa_id,
        "slug": t.slug,
        "ad": t.ad,
        "aciklama": t.aciklama or "",
        "sure_dk": int(t.sure_dk),
        "adim_dk": int(t.adim_dk),
        "konum_turu": t.konum_turu,
        "konum_degeri": t.konum_degeri or "",
        "tampon_once_dk": int(t.tampon_once_dk or 0),
        "tampon_sonra_dk": int(t.tampon_sonra_dk or 0),
        "en_erken_dk": int(t.en_erken_dk or 0),
        "en_gec_gun": int(t.en_gec_gun or 60),
        "gunluk_sinir": t.gunluk_sinir,
        "kapasite": int(t.kapasite or 1),
        "telefon": t.telefon,
        "sorular": s.json_yukle(t.sorular, []) or [],
        "renk": t.renk,
        "atama": t.atama,
        "kisiler": rk.tur_kisileri(t),
        "aktif": bool(t.aktif),
        "sira": int(t.sira or 0),
        "created_at": s.iso(t.created_at),
        "updated_at": s.iso(t.updated_at),
    }


def _kisi_sozlugu(k: RandevuKisileri) -> Dict[str, Any]:
    return {
        "id": k.id,
        "eposta": k.eposta,
        "ad": k.ad,
        "haftalik": s.json_yukle(k.haftalik, None) or {},
        "aktif": bool(k.aktif),
        "sira": int(k.sira or 0),
    }


def _istisna_sozlugu(i: RandevuIstisnalari) -> Dict[str, Any]:
    return {
        "id": i.id,
        "kisi_id": i.kisi_id,
        "tarih": i.tarih.isoformat() if isinstance(i.tarih, date) else str(i.tarih),
        "araliklar": s.json_yukle(i.araliklar, []) or [],
        "aciklama": i.aciklama or "",
    }


def _randevu_sozlugu(r: Randevular, turler: Dict[int, RandevuTurleri], kisiler: Dict[int, RandevuKisileri]) -> Dict[str, Any]:
    t = turler.get(r.tur_id)
    k = kisiler.get(r.kisi_id)
    yanitlar = s.json_yukle(r.yanitlar, {}) or {}
    sorular = {q.get("id"): q.get("etiket") for q in (s.json_yukle(t.sorular, []) or [])} if t else {}
    return {
        "id": r.id,
        "uid": r.uid,
        "tur_id": r.tur_id,
        "tur_adi": t.ad if t else "—",
        "tur_renk": t.renk if t else "#7c3aed",
        "konum_turu": t.konum_turu if t else None,
        "kisi_id": r.kisi_id,
        "kisi_adi": k.ad if k else "—",
        "baslangic": s.iso(r.baslangic),
        "bitis": s.iso(r.bitis),
        "durum": r.durum,
        "katilim": r.katilim,
        "ad": r.ad,
        "eposta": r.eposta,
        "telefon": r.telefon,
        "yanitlar": [{"id": kimlik, "soru": sorular.get(kimlik, kimlik), "yanit": deger} for kimlik, deger in yanitlar.items()],
        "konum": r.konum,
        "ziyaretci_tz": r.ziyaretci_tz,
        "dil": r.dil,
        "iptal_eden": r.iptal_eden,
        "iptal_nedeni": r.iptal_nedeni,
        "iptal_at": s.iso(r.iptal_at),
        "onceki_baslangic": s.iso(r.onceki_baslangic),
        "anonim": bool(r.anonim),
        "crm_aday_id": r.crm_aday_id,
        "created_at": s.iso(r.created_at),
    }


# ---------------------------------------------------------------------------
# Sayfa
# ---------------------------------------------------------------------------
async def _sayfa(db: AsyncSession, sid: int, kapsam: Kapsam) -> RandevuSayfalari:
    sorgu = select(RandevuSayfalari).where(RandevuSayfalari.id == sid)
    if not kapsam.yonetici:
        sorgu = sorgu.where(RandevuSayfalari.hesap_email == kapsam.hesap)
    p = (await db.execute(sorgu)).scalars().first()
    if p is None:
        raise _hata(404, "bulunamadi")
    return p


async def _slug_bos_mu(db: AsyncSession, slug: str, haric: Optional[int] = None) -> bool:
    sorgu = select(RandevuSayfalari.id).where(RandevuSayfalari.slug == slug)
    if haric is not None:
        sorgu = sorgu.where(RandevuSayfalari.id != haric)
    return (await db.execute(sorgu.limit(1))).first() is None


async def _bos_slug(db: AsyncSession, oneri: str) -> str:
    aday = oneri
    for i in range(2, 60):
        if await _slug_bos_mu(db, aday):
            return aday
        aday = f"{oneri[:44]}-{i}"
    return f"{oneri[:40]}-{uuid.uuid4().hex[:6]}"


async def _sayfa_var_mi(db: AsyncSession, hesap: Optional[str]) -> bool:
    kosul = RandevuSayfalari.hesap_email.is_(None) if hesap is None else RandevuSayfalari.hesap_email == hesap
    return (await db.execute(select(RandevuSayfalari.id).where(kosul).limit(1))).first() is not None


def _yerel_ad(eposta: str) -> str:
    return (eposta.split("@", 1)[0] or eposta)[:120]


async def _sayfa_olustur(db: AsyncSession, kapsam: Kapsam, g: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if kapsam.yonetici:
            ham = str(g.get("hesap_email") or "").strip()
            hesap = s.eposta_duzelt(ham, "hesap_email") if ham else None
        else:
            hesap = kapsam.hesap
        if await _sayfa_var_mi(db, hesap):
            raise s.RandevuHatasi("sayfa_var", durum=409)
        baslik = s.metin(g.get("baslik"), "baslik", 120, zorunlu=True)
        if g.get("slug"):
            slug = s.slug_duzelt(g.get("slug"))
            if not await _slug_bos_mu(db, slug):
                raise s.RandevuHatasi("slug_dolu", "slug", durum=409)
        else:
            slug = await _bos_slug(db, s.slug_oner(baslik))
        saat_dilimi = s.saat_dilimi_duzelt(g.get("saat_dilimi") or s.VARSAYILAN_SAAT_DILIMI)
        dil = s.dil_duzelt(g.get("dil") or "tr")
        sahip = hesap or kapsam.kisi
        sahip_ad = s.metin(g.get("ad"), "ad", 120) or _yerel_ad(sahip)
    except s.RandevuHatasi as h:
        raise _r_hatasi(h)
    simdi_ = s.simdi()
    p = RandevuSayfalari(
        hesap_email=hesap, olusturan_email=kapsam.kisi, slug=slug, baslik=baslik, saat_dilimi=saat_dilimi, dil=dil,
        hatirlatmalar=s.json_yaz(list(s.VARSAYILAN_HATIRLATMALAR)), created_at=simdi_,
    )
    db.add(p)
    try:
        await db.flush()
        db.add(RandevuKisileri(sayfa_id=p.id, eposta=sahip, ad=sahip_ad, haftalik=s.json_yaz(s.VARSAYILAN_HAFTALIK),
                               sira=0, created_at=simdi_))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "slug_dolu", alan="slug")
    await db.refresh(p)
    return _sayfa_sozlugu(p)


async def _sayfa_guncelle(db: AsyncSession, p: RandevuSayfalari, g: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if "baslik" in g:
            p.baslik = s.metin(g.get("baslik"), "baslik", 120, zorunlu=True)
        if "karsilama" in g:
            p.karsilama = s.metin(g.get("karsilama"), "karsilama", 1000, cok_satir=True) or None
        if "slug" in g:
            slug = s.slug_duzelt(g.get("slug"))
            if slug != p.slug and not await _slug_bos_mu(db, slug, p.id):
                raise s.RandevuHatasi("slug_dolu", "slug", durum=409)
            p.slug = slug
        if "renk" in g:
            p.renk = s.renk_duzelt(g.get("renk"))
        if "saat_dilimi" in g:
            p.saat_dilimi = s.saat_dilimi_duzelt(g.get("saat_dilimi"))
        if "dil" in g:
            p.dil = s.dil_duzelt(g.get("dil"))
        for alan in ("arama_motoru", "tatilde_kapali", "aktif"):
            if alan in g:
                setattr(p, alan, s.bool_duzelt(g.get(alan), alan))
        if "hatirlatmalar" in g:
            p.hatirlatmalar = s.json_yaz(s.hatirlatmalar_duzelt(g.get("hatirlatmalar")))
        if "iptal_sinir_dk" in g:
            p.iptal_sinir_dk = s.tam_sayi(g.get("iptal_sinir_dk"), "iptal_sinir_dk", 0, s.IPTAL_SINIR_EN_COK)
        if "saklama_gun" in g:
            p.saklama_gun = s.tam_sayi(g.get("saklama_gun"), "saklama_gun", s.SAKLAMA_EN_AZ, s.SAKLAMA_EN_COK)
    except s.RandevuHatasi as h:
        await db.rollback()
        raise _r_hatasi(h)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "slug_dolu", alan="slug")
    await db.refresh(p)
    return _sayfa_sozlugu(p)


async def _sayfa_sil(db: AsyncSession, p: RandevuSayfalari) -> None:
    """Yaklaşan onaylı randevu varken silinmez (önce iptal). Tür/kişi/istisnalar aynı flush'ta
    silinir (çöp kutusu birlikte yakalar); kalan randevuların kişisel alanları hemen anonimleşir."""
    yaklasan = int((await db.execute(
        select(func.count(Randevular.id)).where(Randevular.sayfa_id == p.id, Randevular.durum == "onayli",
                                                Randevular.bitis > s.simdi())
    )).scalar() or 0)
    if yaklasan:
        raise _hata(409, "yaklasan_randevu_var", sayi=yaklasan)
    cocuklar: List[Any] = []
    for model in (RandevuTurleri, RandevuKisileri, RandevuIstisnalari):
        cocuklar += list((await db.execute(select(model).where(model.sayfa_id == p.id))).scalars().all())
    await db.execute(
        update(Randevular).where(Randevular.sayfa_id == p.id, Randevular.anonim.is_(False))
        .values(**rk.KISISEL_BOS).execution_options(synchronize_session=False)
    )
    for kayit in cocuklar:
        await db.delete(kayit)
    await db.delete(p)
    await db.commit()


async def _liste(db: AsyncSession, kapsam: Kapsam, hesap: Optional[str]) -> Dict[str, Any]:
    sorgu = select(RandevuSayfalari)
    if not kapsam.yonetici:
        sorgu = sorgu.where(RandevuSayfalari.hesap_email == kapsam.hesap)
    elif hesap == "ajans":
        sorgu = sorgu.where(RandevuSayfalari.hesap_email.is_(None))
    elif hesap:
        sorgu = sorgu.where(RandevuSayfalari.hesap_email == hesap.strip().lower())
    sayfalar = (await db.execute(sorgu.order_by(RandevuSayfalari.hesap_email.is_not(None),
                                                RandevuSayfalari.hesap_email, RandevuSayfalari.id).limit(500))).scalars().all()
    idler = [p.id for p in sayfalar]
    yaklasan: Dict[int, int] = {}
    tur_sayilari: Dict[int, int] = {}
    if idler:
        yaklasan = dict((await db.execute(
            select(Randevular.sayfa_id, func.count(Randevular.id))
            .where(Randevular.sayfa_id.in_(idler), Randevular.durum == "onayli", Randevular.bitis > s.simdi())
            .group_by(Randevular.sayfa_id)
        )).all())
        tur_sayilari = dict((await db.execute(
            select(RandevuTurleri.sayfa_id, func.count(RandevuTurleri.id))
            .where(RandevuTurleri.sayfa_id.in_(idler)).group_by(RandevuTurleri.sayfa_id)
        )).all())
    return {"items": [_sayfa_sozlugu(p, yaklasan=int(yaklasan.get(p.id, 0)), tur_sayisi=int(tur_sayilari.get(p.id, 0)))
                      for p in sayfalar], "toplam": len(sayfalar)}


async def _tur_siniri(db: AsyncSession, kapsam: Kapsam, p: RandevuSayfalari) -> Optional[int]:
    if kapsam.yonetici or not p.hesap_email:
        return None
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, p.hesap_email, MODUL, "tur_siniri")
    return int(deger) if isinstance(deger, int) and not isinstance(deger, bool) else VARSAYILAN_TUR_SINIRI


async def _meta(db: AsyncSession, kapsam: Kapsam) -> Dict[str, Any]:
    tur_siniri: Optional[int] = None
    if not kapsam.yonetici:
        from services.moduller import musteri_ayari

        deger = await musteri_ayari(db, kapsam.hesap or "", MODUL, "tur_siniri")
        tur_siniri = int(deger) if isinstance(deger, int) and not isinstance(deger, bool) else VARSAYILAN_TUR_SINIRI
    return {
        "yonetici": kapsam.yonetici,
        "sayfa_siniri": None if kapsam.yonetici else 1,
        "tur_siniri": tur_siniri,
        "konum_turleri": list(s.KONUM_TURLERI),
        "atama_turleri": list(s.ATAMA_TURLERI),
        "telefon_secenekleri": list(s.TELEFON_SECENEKLERI),
        "soru_turleri": list(s.SORU_TURLERI),
        "adimlar": list(s.ADIMLAR),
        "hatirlatma_secenekleri": list(s.HATIRLATMA_SECENEKLERI),
        "en_cok_hatirlatma": s.EN_COK_HATIRLATMA,
        "en_cok_soru": s.EN_COK_SORU,
        "sure": [s.SURE_EN_AZ, s.SURE_EN_COK],
        "kapasite_en_cok": s.KAPASITE_EN_COK,
        "diller": list(s.DILLER),
        "adres_tabani": f"{s.site_adresi()}/randevu/",
        "widget_adresi": f"{s.site_adresi()}/randevu-widget.js",
        "varsayilan_saat_dilimi": s.VARSAYILAN_SAAT_DILIMI,
    }


# ---------------------------------------------------------------------------
# Etkinlik türleri
# ---------------------------------------------------------------------------
async def _tur(db: AsyncSession, p: RandevuSayfalari, tid: int) -> RandevuTurleri:
    t = (await db.execute(select(RandevuTurleri).where(RandevuTurleri.id == tid, RandevuTurleri.sayfa_id == p.id))).scalars().first()
    if t is None:
        raise _hata(404, "bulunamadi")
    return t


async def _tur_slug_bos_mu(db: AsyncSession, sid: int, slug: str, haric: Optional[int] = None) -> bool:
    sorgu = select(RandevuTurleri.id).where(RandevuTurleri.sayfa_id == sid, RandevuTurleri.slug == slug)
    if haric is not None:
        sorgu = sorgu.where(RandevuTurleri.id != haric)
    return (await db.execute(sorgu.limit(1))).first() is None


async def _sayfa_kisileri(db: AsyncSession, sid: int) -> List[RandevuKisileri]:
    return list((await db.execute(
        select(RandevuKisileri).where(RandevuKisileri.sayfa_id == sid).order_by(RandevuKisileri.sira, RandevuKisileri.id)
    )).scalars().all())


async def _tur_uygula(db: AsyncSession, p: RandevuSayfalari, t: RandevuTurleri, g: Dict[str, Any], yeni: bool) -> None:
    if "ad" in g or yeni:
        t.ad = s.metin(g.get("ad"), "ad", 120, zorunlu=True)
    if "slug" in g and g.get("slug"):
        slug = s.slug_duzelt(g.get("slug"))
        if not await _tur_slug_bos_mu(db, p.id, slug, None if yeni else t.id):
            raise s.RandevuHatasi("slug_dolu", "slug", durum=409)
        t.slug = slug
    elif yeni:
        oneri = s.slug_oner(t.ad, "gorusme")
        aday = oneri
        for i in range(2, 60):
            if await _tur_slug_bos_mu(db, p.id, aday):
                break
            aday = f"{oneri[:44]}-{i}"
        t.slug = aday
    if "aciklama" in g:
        t.aciklama = s.metin(g.get("aciklama"), "aciklama", 2000, cok_satir=True) or None
    if "sure_dk" in g or yeni:
        t.sure_dk = s.tam_sayi(g.get("sure_dk", 30), "sure_dk", s.SURE_EN_AZ, s.SURE_EN_COK)
    if "adim_dk" in g and g.get("adim_dk") not in (None, ""):
        adim = s.tam_sayi(g.get("adim_dk"), "adim_dk", 5, 120)
        if adim not in s.ADIMLAR:
            raise s.RandevuHatasi("adim_gecersiz", "adim_dk")
        t.adim_dk = adim
    elif yeni:
        t.adim_dk = s.adim_varsayilani(int(t.sure_dk))
    if "konum_turu" in g or "konum_degeri" in g or yeni:
        t.konum_turu, t.konum_degeri = s.konum_duzelt(g.get("konum_turu", t.konum_turu or "jitsi"),
                                                      g.get("konum_degeri", t.konum_degeri))
    for alan, en_cok in (("tampon_once_dk", s.TAMPON_EN_COK), ("tampon_sonra_dk", s.TAMPON_EN_COK),
                         ("en_erken_dk", s.EN_ERKEN_EN_COK)):
        if alan in g:
            setattr(t, alan, s.tam_sayi(g.get(alan), alan, 0, en_cok))
    if "en_gec_gun" in g:
        t.en_gec_gun = s.tam_sayi(g.get("en_gec_gun"), "en_gec_gun", s.EN_GEC_EN_AZ, s.EN_GEC_EN_COK)
    if "gunluk_sinir" in g:
        t.gunluk_sinir = s.tam_sayi(g.get("gunluk_sinir"), "gunluk_sinir", 1, 100, bos_olabilir=True)
    if "kapasite" in g:
        t.kapasite = s.tam_sayi(g.get("kapasite"), "kapasite", 1, s.KAPASITE_EN_COK)
    if "telefon" in g:
        if g.get("telefon") not in s.TELEFON_SECENEKLERI:
            raise s.RandevuHatasi("secim_gecersiz", "telefon")
        t.telefon = g["telefon"]
    if "sorular" in g:
        t.sorular = s.json_yaz(s.sorular_duzelt(g.get("sorular")))
    if "renk" in g:
        t.renk = s.renk_duzelt(g.get("renk"))
    if "atama" in g:
        if g.get("atama") not in s.ATAMA_TURLERI:
            raise s.RandevuHatasi("secim_gecersiz", "atama")
        t.atama = g["atama"]
    kisiler = await _sayfa_kisileri(db, p.id)
    if "kisiler" in g:
        ham = g.get("kisiler")
        gecerli = {k.id for k in kisiler}
        if not isinstance(ham, list) or not ham or len(ham) > s.EN_COK_KISI:
            raise s.RandevuHatasi("kisi_gecersiz", "kisiler")
        idler: List[int] = []
        for x in ham:
            if isinstance(x, bool) or not isinstance(x, int) or x not in gecerli or x in idler:
                raise s.RandevuHatasi("kisi_gecersiz", "kisiler")
            idler.append(x)
        t.kisiler = s.json_yaz(idler)
    elif yeni or not rk.tur_kisileri(t):
        aktif = [k.id for k in kisiler if k.aktif] or [k.id for k in kisiler]
        t.kisiler = s.json_yaz(aktif[:1])
    if "aktif" in g:
        t.aktif = s.bool_duzelt(g.get("aktif"), "aktif")
    if "sira" in g:
        t.sira = s.tam_sayi(g.get("sira"), "sira", 0, 10000)
    if int(t.kapasite or 1) > 1 and (t.atama != "kisi" or len(rk.tur_kisileri(t)) != 1):
        raise s.RandevuHatasi("grup_tek_kisi", "kapasite")
    if t.konum_turu == "telefon" and not t.konum_degeri:
        # Biz arayacağız: ziyaretçinin numarası şart.
        t.telefon = "zorunlu"


# ---------------------------------------------------------------------------
# Ekip adayları
# ---------------------------------------------------------------------------
async def _ekip_adaylari(db: AsyncSession, p: RandevuSayfalari) -> List[Dict[str, str]]:
    adaylar: Dict[str, str] = {}
    if p.hesap_email:
        from services import hesap_ekibi as he

        adaylar[p.hesap_email] = _yerel_ad(p.hesap_email)
        for u in await he.uyeler(db, p.hesap_email):
            if he.gecerli_durum(u) == "aktif" and IZIN in he.izinleri_coz(u.izinler, u.rol):
                adaylar.setdefault(u.uye_email, _yerel_ad(u.uye_email))
    else:
        from models.staff import Staff
        from services import notify

        for a in await notify.admin_recipients(db):
            e = (a.get("email") or "").strip().lower()
            if e:
                adaylar.setdefault(e, _yerel_ad(e))
        for st in (await db.execute(select(Staff).where(or_(Staff.aktif.is_(True), Staff.aktif.is_(None))))).scalars().all():
            e = (st.email or "").strip().lower()
            if e:
                adaylar[e] = (st.ad or _yerel_ad(e))[:120]
    return [{"eposta": e, "ad": a} for e, a in adaylar.items()]


# ---------------------------------------------------------------------------
# Analiz
# ---------------------------------------------------------------------------
async def _analiz(db: AsyncSession, p: RandevuSayfalari, gun: int) -> Dict[str, Any]:
    simdi_ = s.simdi()
    bas = simdi_ - timedelta(days=gun)
    bas_gun = bas.date().isoformat()
    temel = (RandevuOlaylari.sayfa_id == p.id, RandevuOlaylari.gun >= bas_gun, RandevuOlaylari.bot.is_(False))
    gorunum = int((await db.execute(select(func.count(RandevuOlaylari.id)).where(*temel, RandevuOlaylari.tur.in_(("sayfa", "tur"))))).scalar() or 0)
    tekil = int((await db.execute(
        select(func.count(func.distinct(RandevuOlaylari.ip_ozeti))).where(*temel, RandevuOlaylari.tur.in_(("sayfa", "tur")))
    )).scalar() or 0)
    randevular = (await db.execute(
        select(Randevular.tur_id, Randevular.durum, Randevular.created_at).where(Randevular.sayfa_id == p.id,
                                                                                Randevular.created_at >= bas)
    )).all()
    rezervasyon = len(randevular)
    iptal = len([1 for _, d, _ in randevular if d == "iptal"])
    gunluk: Dict[str, Dict[str, int]] = {}
    for g_, n in (await db.execute(
        select(RandevuOlaylari.gun, func.count(RandevuOlaylari.id)).where(*temel, RandevuOlaylari.tur.in_(("sayfa", "tur")))
        .group_by(RandevuOlaylari.gun)
    )).all():
        gunluk.setdefault(g_, {"goruntuleme": 0, "rezervasyon": 0})["goruntuleme"] = int(n)
    for _, _, an in randevular:
        g_ = (s.utc(an) or simdi_).date().isoformat()
        gunluk.setdefault(g_, {"goruntuleme": 0, "rezervasyon": 0})["rezervasyon"] += 1
    tur_gorunum = dict((await db.execute(
        select(RandevuOlaylari.tur_id, func.count(RandevuOlaylari.id)).where(*temel, RandevuOlaylari.tur == "tur")
        .group_by(RandevuOlaylari.tur_id)
    )).all())
    turler = (await db.execute(select(RandevuTurleri).where(RandevuTurleri.sayfa_id == p.id).order_by(RandevuTurleri.sira, RandevuTurleri.id))).scalars().all()
    tur_rez: Dict[int, int] = {}
    for tid, _, _ in randevular:
        tur_rez[tid] = tur_rez.get(tid, 0) + 1
    katilim = dict((await db.execute(
        select(Randevular.katilim, func.count(Randevular.id)).where(Randevular.sayfa_id == p.id, Randevular.durum == "onayli",
                                                                    Randevular.baslangic >= bas, Randevular.baslangic <= simdi_)
        .group_by(Randevular.katilim)
    )).all())
    return {
        "gun": gun,
        "goruntuleme": gorunum,
        "tekil": tekil,
        "rezervasyon": rezervasyon,
        "iptal": iptal,
        "donusum": round(rezervasyon * 100.0 / tekil, 1) if tekil else None,
        "katilim": {k: int(katilim.get(k, 0)) for k in s.KATILIM},
        "gunluk": [{"gun": g_, **v} for g_, v in sorted(gunluk.items())],
        "turler": [
            {"id": t.id, "ad": t.ad, "renk": t.renk, "goruntuleme": int(tur_gorunum.get(t.id, 0)),
             "rezervasyon": int(tur_rez.get(t.id, 0))}
            for t in turler
        ],
    }


def _qr_gorsel(p: RandevuSayfalari, tur_slug: Optional[str], bicim: str) -> qr.Gorsel:
    tasarim = dict(qr.VARSAYILAN_TASARIM)
    if qr.kontrast_orani(p.renk or "#000000", "#ffffff") >= 4.5:
        tasarim["on_renk"] = p.renk
    tasarim = qr.tasarim_duzelt(tasarim)
    icerik = s.sayfa_adresi(p.slug, tur_slug)
    return (qr.png_ciz if bicim == "png" else qr.svg_ciz)(icerik, tasarim, None)


async def _logo_birak(db: AsyncSession, p: RandevuSayfalari, anahtar: Optional[str]) -> None:
    if not anahtar:
        return
    g = (await db.execute(select(RandevuGorselleri).where(RandevuGorselleri.anahtar == anahtar,
                                                          RandevuGorselleri.sayfa_id == p.id))).scalars().first()
    if g is None:
        return
    from services import dosya_deposu

    try:
        await dosya_deposu.sil(db, g.depo, f"randevu/{g.anahtar}.webp")
    except Exception:  # noqa: BLE001
        logger.warning("Randevu logosu silinemedi: %s", g.anahtar)
    await db.delete(g)


async def _logo_yukle(db: AsyncSession, kapsam: Kapsam, p: RandevuSayfalari, dosya: UploadFile) -> Dict[str, Any]:
    _hiz(_gorsel_hizi, kapsam.kisi)
    from services import qr_menu as menu_kurallari

    bayt = await dosya.read(menu_kurallari.GORSEL_EN_COK_BAYT + 1)
    try:
        hazir = menu_kurallari.gorsel_hazirla(bayt)
    except menu_kurallari.MenuHatasi as h:
        raise HTTPException(status_code=h.durum, detail=h.detay())
    from services import dosya_deposu

    anahtar = menu_kurallari.gorsel_anahtari()
    try:
        depo = await dosya_deposu.yaz(db, f"randevu/{anahtar}.webp", hazir.kucuk, "image/webp")
    except dosya_deposu.DepoHatasi:
        await db.rollback()
        raise _hata(502, "depo_hatasi")
    db.add(RandevuGorselleri(sayfa_id=p.id, anahtar=anahtar, depo=depo, genislik=hazir.genislik,
                             yukseklik=hazir.yukseklik))
    eski = p.logo
    p.logo = anahtar
    await _logo_birak(db, p, eski)
    await db.commit()
    await db.refresh(p)
    return _sayfa_sozlugu(p)


# ---------------------------------------------------------------------------
# Randevu işlemleri (panel)
# ---------------------------------------------------------------------------
async def _randevu(db: AsyncSession, p: RandevuSayfalari, rid: int) -> Randevular:
    r = (await db.execute(select(Randevular).where(Randevular.id == rid, Randevular.sayfa_id == p.id))).scalars().first()
    if r is None:
        raise _hata(404, "bulunamadi")
    return r


async def _sozlukler(db: AsyncSession, sid: int):
    turler = {t.id: t for t in (await db.execute(select(RandevuTurleri).where(RandevuTurleri.sayfa_id == sid))).scalars().all()}
    kisiler = {k.id: k for k in (await db.execute(select(RandevuKisileri).where(RandevuKisileri.sayfa_id == sid))).scalars().all()}
    return turler, kisiler


def _iptal_et(r: Randevular, eden: str, neden: Optional[str]) -> None:
    r.durum = "iptal"
    r.iptal_eden = eden
    r.iptal_nedeni = neden or None
    r.iptal_at = s.simdi()
    r.koltuk = None  # yer boşalır
    r.sira_no = int(r.sira_no or 0) + 1


def _an_coz(ham: Any, alan: str) -> datetime:
    try:
        deger = str(ham or "").strip().replace("Z", "+00:00")
        an = datetime.fromisoformat(deger)
    except ValueError:
        raise _hata(400, "zaman_gecersiz", alan=alan)
    if an.tzinfo is None:
        raise _hata(400, "zaman_gecersiz", alan=alan)
    return an.astimezone(s.UTC).replace(microsecond=0)


def _uclari_kur(router: APIRouter, kapsam_al: Callable[[Request], Kapsam]) -> None:
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        return await _meta(db, kapsam_al(request))

    @router.get("")
    async def liste(request: Request, hesap: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _liste(db, kapsam, hesap if kapsam.yonetici else None)

    @router.post("")
    async def olustur(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        return await _sayfa_olustur(db, kapsam, govde)

    @router.get("/{sid}")
    async def ayrinti(sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        p = await _sayfa(db, sid, kapsam)
        return _sayfa_sozlugu(p, tur_siniri=await _tur_siniri(db, kapsam, p),
                              tur_sayisi=int((await db.execute(select(func.count(RandevuTurleri.id)).where(RandevuTurleri.sayfa_id == p.id))).scalar() or 0))

    @router.put("/{sid}")
    async def guncelle(sid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        return await _sayfa_guncelle(db, await _sayfa(db, sid, kapsam), govde)

    @router.delete("/{sid}")
    async def sil(sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        await _sayfa_sil(db, await _sayfa(db, sid, kapsam))
        return {"ok": True}

    @router.post("/{sid}/logo")
    async def logo(sid: int, request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _logo_yukle(db, kapsam, await _sayfa(db, sid, kapsam), dosya)

    @router.delete("/{sid}/logo")
    async def logo_sil(sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        p = await _sayfa(db, sid, kapsam_al(request))
        eski, p.logo = p.logo, None
        await _logo_birak(db, p, eski)
        await db.commit()
        await db.refresh(p)
        return _sayfa_sozlugu(p)

    @router.post("/{sid}/besleme/yenile")
    async def besleme_yenile(sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        p = await _sayfa(db, sid, kapsam)
        p.besleme_surumu = int(p.besleme_surumu or 1) + 1
        await db.commit()
        await db.refresh(p)
        return _sayfa_sozlugu(p)

    @router.get("/{sid}/qr")
    async def sayfa_qr(sid: int, request: Request, bicim: str = Query("png"), tur: Optional[str] = Query(None),
                       db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        if bicim not in ("png", "svg"):
            raise _hata(400, "bicim_gecersiz")
        _hiz(_gorsel_hizi, kapsam.kisi)
        p = await _sayfa(db, sid, kapsam)
        tur_slug = None
        if tur:
            t = (await db.execute(select(RandevuTurleri).where(RandevuTurleri.sayfa_id == p.id, RandevuTurleri.slug == tur))).scalars().first()
            if t is None:
                raise _hata(404, "bulunamadi")
            tur_slug = t.slug
        g = _qr_gorsel(p, tur_slug, bicim)
        ad = f"randevu-{p.slug}{f'-{tur_slug}' if tur_slug else ''}-qr.{bicim}"
        return Response(g.veri, media_type=g.tur, headers={
            "Content-Disposition": icerik_konumu(ad), "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        })

    @router.get("/{sid}/analiz")
    async def analiz(sid: int, request: Request, gun: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
        return await _analiz(db, await _sayfa(db, sid, kapsam_al(request)), gun)

    # --- Etkinlik türleri ---
    @router.get("/{sid}/turler")
    async def turler(sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        p = await _sayfa(db, sid, kapsam)
        kayitlar = (await db.execute(select(RandevuTurleri).where(RandevuTurleri.sayfa_id == p.id)
                                     .order_by(RandevuTurleri.sira, RandevuTurleri.id))).scalars().all()
        return {"items": [_tur_sozlugu(t) for t in kayitlar], "tur_siniri": await _tur_siniri(db, kapsam, p)}

    @router.post("/{sid}/turler")
    async def tur_olustur(sid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        p = await _sayfa(db, sid, kapsam)
        sinir = await _tur_siniri(db, kapsam, p)
        sayi = int((await db.execute(select(func.count(RandevuTurleri.id)).where(RandevuTurleri.sayfa_id == p.id))).scalar() or 0)
        if sayi >= (sinir if sinir is not None else EN_COK_TUR_YONETICI):
            raise _hata(409, "tur_siniri", sinir=sinir if sinir is not None else EN_COK_TUR_YONETICI)
        t = RandevuTurleri(
            sayfa_id=p.id, sira=sayi, renk=p.renk, atama="kisi", telefon="istege_bagli", kapasite=1, aktif=True,
            tampon_once_dk=0, tampon_sonra_dk=0, en_erken_dk=240, en_gec_gun=60, konum_turu="jitsi", created_at=s.simdi(),
        )
        try:
            await _tur_uygula(db, p, t, govde, yeni=True)
        except s.RandevuHatasi as h:
            raise _r_hatasi(h)
        db.add(t)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "slug_dolu", alan="slug")
        await db.refresh(t)
        return _tur_sozlugu(t)

    @router.put("/{sid}/turler/{tid}")
    async def tur_guncelle(sid: int, tid: int, request: Request, govde: Dict[str, Any] = Body(...),
                           db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        p = await _sayfa(db, sid, kapsam)
        t = await _tur(db, p, tid)
        try:
            await _tur_uygula(db, p, t, govde, yeni=False)
        except s.RandevuHatasi as h:
            await db.rollback()
            raise _r_hatasi(h)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "slug_dolu", alan="slug")
        await db.refresh(t)
        return _tur_sozlugu(t)

    @router.delete("/{sid}/turler/{tid}")
    async def tur_sil(sid: int, tid: int, request: Request, db: AsyncSession = Depends(get_db)):
        p = await _sayfa(db, sid, kapsam_al(request))
        t = await _tur(db, p, tid)
        yaklasan = int((await db.execute(select(func.count(Randevular.id)).where(
            Randevular.tur_id == t.id, Randevular.durum == "onayli", Randevular.bitis > s.simdi()))).scalar() or 0)
        if yaklasan:
            raise _hata(409, "yaklasan_randevu_var", sayi=yaklasan)
        await db.delete(t)
        await db.commit()
        return {"ok": True}

    # --- Ekip ---
    @router.get("/{sid}/kisiler")
    async def kisiler(sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        p = await _sayfa(db, sid, kapsam_al(request))
        return {"items": [_kisi_sozlugu(k) for k in await _sayfa_kisileri(db, p.id)],
                "adaylar": await _ekip_adaylari(db, p)}

    @router.post("/{sid}/kisiler")
    async def kisi_ekle(sid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        p = await _sayfa(db, sid, kapsam)
        try:
            eposta = s.eposta_duzelt(govde.get("eposta"))
            adaylar = {a["eposta"]: a["ad"] for a in await _ekip_adaylari(db, p)}
            if not kapsam.yonetici and eposta not in adaylar:
                # Müşteri yalnız hesabının (randevu izni olan, aktif) kişilerini ekleyebilir.
                raise s.RandevuHatasi("kisi_aday_degil", "eposta", durum=403)
            ad = s.metin(govde.get("ad"), "ad", 120) or adaylar.get(eposta) or _yerel_ad(eposta)
            haftalik = s.haftalik_duzelt(govde["haftalik"]) if "haftalik" in govde else dict(s.VARSAYILAN_HAFTALIK)
        except s.RandevuHatasi as h:
            raise _r_hatasi(h)
        mevcut = await _sayfa_kisileri(db, p.id)
        if len(mevcut) >= s.EN_COK_KISI:
            raise _hata(409, "kisi_siniri", sinir=s.EN_COK_KISI)
        k = RandevuKisileri(sayfa_id=p.id, eposta=eposta, ad=ad, haftalik=s.json_yaz(haftalik), sira=len(mevcut),
                            created_at=s.simdi())
        db.add(k)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "kisi_var", alan="eposta")
        await db.refresh(k)
        return _kisi_sozlugu(k)

    @router.put("/{sid}/kisiler/{kid}")
    async def kisi_guncelle(sid: int, kid: int, request: Request, govde: Dict[str, Any] = Body(...),
                            db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        p = await _sayfa(db, sid, kapsam)
        k = (await db.execute(select(RandevuKisileri).where(RandevuKisileri.id == kid, RandevuKisileri.sayfa_id == p.id))).scalars().first()
        if k is None:
            raise _hata(404, "bulunamadi")
        try:
            if "ad" in govde:
                k.ad = s.metin(govde.get("ad"), "ad", 120, zorunlu=True)
            if "haftalik" in govde:
                k.haftalik = s.json_yaz(s.haftalik_duzelt(govde.get("haftalik")))
            if "aktif" in govde:
                k.aktif = s.bool_duzelt(govde.get("aktif"), "aktif")
            if "sira" in govde:
                k.sira = s.tam_sayi(govde.get("sira"), "sira", 0, 1000)
        except s.RandevuHatasi as h:
            await db.rollback()
            raise _r_hatasi(h)
        await db.commit()
        await db.refresh(k)
        return _kisi_sozlugu(k)

    @router.delete("/{sid}/kisiler/{kid}")
    async def kisi_sil(sid: int, kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        p = await _sayfa(db, sid, kapsam_al(request))
        kisiler_ = await _sayfa_kisileri(db, p.id)
        k = next((x for x in kisiler_ if x.id == kid), None)
        if k is None:
            raise _hata(404, "bulunamadi")
        if len(kisiler_) <= 1:
            raise _hata(409, "son_kisi")
        yaklasan = int((await db.execute(select(func.count(Randevular.id)).where(
            Randevular.kisi_id == k.id, Randevular.durum == "onayli", Randevular.bitis > s.simdi()))).scalar() or 0)
        if yaklasan:
            raise _hata(409, "yaklasan_randevu_var", sayi=yaklasan)
        kalan = [x.id for x in kisiler_ if x.id != k.id and x.aktif] or [x.id for x in kisiler_ if x.id != k.id]
        for t in (await db.execute(select(RandevuTurleri).where(RandevuTurleri.sayfa_id == p.id))).scalars().all():
            idler = rk.tur_kisileri(t)
            if k.id in idler:
                yeni = [i for i in idler if i != k.id] or kalan[:1]
                t.kisiler = s.json_yaz(yeni)
        await db.execute(delete(RandevuIstisnalari).where(RandevuIstisnalari.kisi_id == k.id))
        await db.delete(k)
        await db.commit()
        return {"ok": True}

    # --- İstisnalar ---
    @router.get("/{sid}/istisnalar")
    async def istisnalar(sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        p = await _sayfa(db, sid, kapsam_al(request))
        esik = (s.simdi() - timedelta(days=30)).date()
        kayitlar = (await db.execute(select(RandevuIstisnalari).where(RandevuIstisnalari.sayfa_id == p.id,
                                                                      RandevuIstisnalari.tarih >= esik)
                                     .order_by(RandevuIstisnalari.tarih, RandevuIstisnalari.id))).scalars().all()
        return {"items": [_istisna_sozlugu(i) for i in kayitlar]}

    @router.post("/{sid}/istisnalar")
    async def istisna_ekle(sid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        p = await _sayfa(db, sid, kapsam)
        try:
            tarih = s.tarih_duzelt(govde.get("tarih"))
            araliklar = s.araliklar_duzelt(govde.get("araliklar") or [], "araliklar")
            aciklama = s.metin(govde.get("aciklama"), "aciklama", 200) or None
            kisi_id = govde.get("kisi_id")
            if kisi_id is not None:
                if isinstance(kisi_id, bool) or not isinstance(kisi_id, int) or kisi_id not in {k.id for k in await _sayfa_kisileri(db, p.id)}:
                    raise s.RandevuHatasi("kisi_gecersiz", "kisi_id")
        except s.RandevuHatasi as h:
            raise _r_hatasi(h)
        kosul = RandevuIstisnalari.kisi_id.is_(None) if kisi_id is None else RandevuIstisnalari.kisi_id == kisi_id
        await db.execute(delete(RandevuIstisnalari).where(RandevuIstisnalari.sayfa_id == p.id,
                                                          RandevuIstisnalari.tarih == tarih, kosul))
        i = RandevuIstisnalari(sayfa_id=p.id, kisi_id=kisi_id, tarih=tarih, araliklar=s.json_yaz(araliklar),
                               aciklama=aciklama, created_at=s.simdi())
        db.add(i)
        await db.commit()
        await db.refresh(i)
        return _istisna_sozlugu(i)

    @router.delete("/{sid}/istisnalar/{iid}")
    async def istisna_sil(sid: int, iid: int, request: Request, db: AsyncSession = Depends(get_db)):
        p = await _sayfa(db, sid, kapsam_al(request))
        i = (await db.execute(select(RandevuIstisnalari).where(RandevuIstisnalari.id == iid, RandevuIstisnalari.sayfa_id == p.id))).scalars().first()
        if i is None:
            raise _hata(404, "bulunamadi")
        await db.delete(i)
        await db.commit()
        return {"ok": True}

    # --- Randevular ---
    @router.get("/{sid}/randevular")
    async def randevu_listesi(
        sid: int, request: Request, donem: str = Query("yaklasan"), bas: Optional[str] = Query(None),
        bit: Optional[str] = Query(None), tur_id: Optional[int] = Query(None), kisi_id: Optional[int] = Query(None),
        sinir: int = Query(100, ge=1, le=500), atla: int = Query(0, ge=0), db: AsyncSession = Depends(get_db),
    ):
        p = await _sayfa(db, sid, kapsam_al(request))
        await rk.anonimlestir(db, p)
        await db.commit()  # 0 satırda da: açık yazma işlemi (SQLite kilidi) kalmasın
        simdi_ = s.simdi()
        sorgu = select(Randevular).where(Randevular.sayfa_id == p.id)
        if bas or bit:
            if not (bas and bit):
                raise _hata(400, "zaman_gecersiz", alan="bas")
            a, b = _an_coz(bas, "bas"), _an_coz(bit, "bit")
            if b <= a or b - a > timedelta(days=42):
                raise _hata(400, "zaman_gecersiz", alan="bit")
            sorgu = sorgu.where(Randevular.baslangic >= a, Randevular.baslangic < b)
            sira = (Randevular.baslangic,)
        elif donem == "gecmis":
            sorgu = sorgu.where(Randevular.durum == "onayli", Randevular.bitis <= simdi_)
            sira = (desc(Randevular.baslangic),)
        elif donem == "iptal":
            sorgu = sorgu.where(Randevular.durum == "iptal")
            sira = (desc(Randevular.baslangic),)
        else:
            sorgu = sorgu.where(Randevular.durum == "onayli", Randevular.bitis > simdi_)
            sira = (Randevular.baslangic,)
        if tur_id is not None:
            sorgu = sorgu.where(Randevular.tur_id == tur_id)
        if kisi_id is not None:
            sorgu = sorgu.where(Randevular.kisi_id == kisi_id)
        toplam = int((await db.execute(select(func.count()).select_from(sorgu.subquery()))).scalar() or 0)
        kayitlar = (await db.execute(sorgu.order_by(*sira, Randevular.id).offset(atla).limit(sinir))).scalars().all()
        turler_, kisiler_ = await _sozlukler(db, p.id)
        return {"items": [_randevu_sozlugu(r, turler_, kisiler_) for r in kayitlar], "toplam": toplam,
                "saklama_gun": int(p.saklama_gun or s.VARSAYILAN_SAKLAMA_GUN)}

    @router.get("/{sid}/randevular/{rid}")
    async def randevu_ayrinti(sid: int, rid: int, request: Request, db: AsyncSession = Depends(get_db)):
        p = await _sayfa(db, sid, kapsam_al(request))
        await rk.anonimlestir(db, p)
        await db.commit()  # 0 satırda da: açık yazma işlemi (SQLite kilidi) kalmasın
        r = await _randevu(db, p, rid)
        turler_, kisiler_ = await _sozlukler(db, p.id)
        return _randevu_sozlugu(r, turler_, kisiler_)

    @router.post("/{sid}/randevular/{rid}/iptal")
    async def randevu_iptal(sid: int, rid: int, request: Request, arka: BackgroundTasks,
                            govde: Dict[str, Any] = Body(default={}), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        p = await _sayfa(db, sid, kapsam)
        r = await _randevu(db, p, rid)
        if r.durum != "onayli":
            raise _hata(409, "zaten_iptal")
        if s.utc(r.bitis) <= s.simdi():
            raise _hata(409, "gecmis_randevu")
        try:
            neden = s.metin(govde.get("neden"), "neden", 500, cok_satir=True)
        except s.RandevuHatasi as h:
            raise _r_hatasi(h)
        _iptal_et(r, "sahip", neden)
        await db.commit()
        if govde.get("bildir", True) is not False:
            arka.add_task(rk.bildir, r.id, "iptal", None, False, True)
        turler_, kisiler_ = await _sozlukler(db, p.id)
        return _randevu_sozlugu(r, turler_, kisiler_)

    @router.put("/{sid}/randevular/{rid}/katilim")
    async def randevu_katilim(sid: int, rid: int, request: Request, govde: Dict[str, Any] = Body(...),
                              db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        p = await _sayfa(db, sid, kapsam)
        r = await _randevu(db, p, rid)
        if govde.get("katilim") not in s.KATILIM:
            raise _hata(400, "secim_gecersiz", alan="katilim")
        if r.durum != "onayli":
            raise _hata(409, "zaten_iptal")
        if s.utc(r.baslangic) > s.simdi():
            raise _hata(409, "henuz_baslamadi")
        r.katilim = govde["katilim"]
        await db.commit()
        turler_, kisiler_ = await _sozlukler(db, p.id)
        return _randevu_sozlugu(r, turler_, kisiler_)


_uclari_kur(yonetici_router, _yonetici_kapsami)
_uclari_kur(musteri_router, _musteri_kapsami)


# ---------------------------------------------------------------------------
# Herkese açık
# ---------------------------------------------------------------------------
ACIK_BASLIKLAR = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


async def _sayfa_yayinda_mi(db: AsyncSession, p: RandevuSayfalari) -> bool:
    if not p.aktif:
        return False
    if p.hesap_email:
        from services import moduller as modul_servisi

        return await modul_servisi.modul_acik_mi(db, p.hesap_email, MODUL)
    return True


async def _yayinda_sayfa(db: AsyncSession, slug: str) -> RandevuSayfalari:
    """Slug'a göre yayındaki sayfa: yok → 404, pasif / sahibin modülü kapalı → 410."""
    temiz = (slug or "").strip().lower()
    if not s.SLUG_DESENI.match(temiz):
        raise _hata(404, "sayfa_yok")
    p = (await db.execute(select(RandevuSayfalari).where(RandevuSayfalari.slug == temiz))).scalars().first()
    if p is None:
        raise _hata(404, "sayfa_yok")
    if not await _sayfa_yayinda_mi(db, p):
        raise _hata(410, "sayfa_pasif")
    return p


async def _yayinda_tur(db: AsyncSession, p: RandevuSayfalari, tur: str) -> RandevuTurleri:
    temiz = (tur or "").strip().lower()
    t = (await db.execute(select(RandevuTurleri).where(RandevuTurleri.sayfa_id == p.id, RandevuTurleri.slug == temiz,
                                                       RandevuTurleri.aktif.is_(True)))).scalars().first()
    if t is None:
        raise _hata(404, "tur_yok")
    return t


def _ziyaretci_anahtari(request: Request, sayfa_id: int) -> str:
    return f"{sayfa_id}|{ip_ozeti('randevu-hiz|' + istemci_ip(request))}"


def _bot_mu(request: Request) -> bool:
    basliklar = {ad: request.headers.get(ad, "") for ad in ("purpose", "sec-purpose", "x-purpose", "x-moz")}
    return request.method == "HEAD" or qr.bot_mu(request.headers.get("user-agent") or "", basliklar)


def _olay_verisi(request: Request, sayfa_id: int, tur: str, tur_id: Optional[int]) -> Dict[str, Any]:
    simdi_ = s.simdi()
    gun = simdi_.date().isoformat()
    return {
        "sayfa_id": sayfa_id, "tur_id": tur_id, "tur": tur, "zaman": simdi_, "gun": gun,
        # Gün tuzun parçası: aynı günün tekil sayımı için yeter, günler arası izleme yok.
        "ip_ozeti": ip_ozeti(f"randevu|{gun}|{istemci_ip(request)}"),
        "bot": _bot_mu(request),
    }


async def _olay_yaz(veri: Dict[str, Any]) -> None:
    """Yanıt gönderildikten sonra tek INSERT. Hata yutulur (analitik sayfayı asla bozmasın)."""
    try:
        if not db_manager.async_session_maker:
            return
        async with db_manager.async_session_maker() as oturum:
            await oturum.execute(insert(RandevuOlaylari).values(**veri))
            await oturum.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Randevu olayı kaydedilemedi")


def _olay_ekle(arka: BackgroundTasks, request: Request, sayfa_id: int, tur: str, tur_id: Optional[int] = None) -> None:
    if _olay_hizi.izin_var_mi(_ziyaretci_anahtari(request, sayfa_id) + "|" + tur):
        arka.add_task(_olay_yaz, _olay_verisi(request, sayfa_id, tur, tur_id))


def _konum_herkese(t: RandevuTurleri) -> Optional[str]:
    """Herkese açık sayfada gösterilen konum: yalnız yüz yüze adres (bağlantı/telefon onaydan sonra)."""
    return t.konum_degeri if t.konum_turu == "yuz_yuze" else None


def _etkin_telefon(t: RandevuTurleri) -> str:
    if t.konum_turu == "telefon" and not t.konum_degeri:
        return "zorunlu"
    return t.telefon


async def _ev_sahipleri(db: AsyncSession, p: RandevuSayfalari, turler: List[RandevuTurleri]) -> Dict[int, List[str]]:
    kisiler = {k.id: k for k in (await db.execute(select(RandevuKisileri).where(RandevuKisileri.sayfa_id == p.id,
                                                                                 RandevuKisileri.aktif.is_(True)))).scalars().all()}
    return {t.id: [kisiler[i].ad for i in rk.tur_kisileri(t) if i in kisiler] for t in turler}


def _acik_tur_sozlugu(t: RandevuTurleri, ev_sahipleri: List[str], ayrintili: bool = False) -> Dict[str, Any]:
    d = {
        "slug": t.slug, "ad": t.ad, "aciklama": t.aciklama or "", "sure_dk": int(t.sure_dk), "konum_turu": t.konum_turu,
        "konum": _konum_herkese(t), "renk": t.renk, "kapasite": int(t.kapasite or 1),
        "ev_sahipleri": ev_sahipleri if t.atama == "kisi" else ev_sahipleri[:1] if len(ev_sahipleri) == 1 else [],
        "ekip": t.atama != "kisi" and len(ev_sahipleri) > 1,
    }
    if ayrintili:
        d.update({
            "telefon": _etkin_telefon(t), "sorular": s.json_yukle(t.sorular, []) or [],
            "en_gec_gun": int(t.en_gec_gun or 60), "en_erken_dk": int(t.en_erken_dk or 0),
        })
    return d


def _acik_sayfa_sozlugu(p: RandevuSayfalari) -> Dict[str, Any]:
    return {
        "slug": p.slug, "baslik": p.baslik, "karsilama": p.karsilama or "", "logo": _gorsel_adresi(p.logo),
        "renk": p.renk, "saat_dilimi": p.saat_dilimi, "dil": p.dil, "indekslenebilir": bool(p.arama_motoru),
        "saklama_gun": int(p.saklama_gun or s.VARSAYILAN_SAKLAMA_GUN), "iptal_sinir_dk": int(p.iptal_sinir_dk or 0),
        "ajans": p.hesap_email is None,
    }


def _robots(p: RandevuSayfalari) -> Dict[str, str]:
    return {} if p.arama_motoru else {"X-Robots-Tag": "noindex"}


@acik_router.api_route("/{slug}", methods=["GET", "HEAD"])
async def acik_sayfa(slug: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    p = await _yayinda_sayfa(db, slug)
    turler = list((await db.execute(select(RandevuTurleri).where(RandevuTurleri.sayfa_id == p.id, RandevuTurleri.aktif.is_(True))
                                    .order_by(RandevuTurleri.sira, RandevuTurleri.id))).scalars().all())
    sahipler = await _ev_sahipleri(db, p, turler)
    veri = {**_acik_sayfa_sozlugu(p), "turler": [_acik_tur_sozlugu(t, sahipler.get(t.id, [])) for t in turler]}
    _olay_ekle(arka, request, p.id, "sayfa")
    return JSONResponse(veri, headers={**ACIK_BASLIKLAR, "Cache-Control": "no-cache", **_robots(p)})


@acik_router.get("/{slug}/ozet")
async def acik_ozet(slug: str, tur: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    """Pages Function'ın paylaşım önizlemesi (title/og/twitter/canonical/robots) için. Analitiğe yazılmaz."""
    p = await _yayinda_sayfa(db, slug)
    veri: Dict[str, Any] = {
        "slug": p.slug, "baslik": p.baslik, "aciklama": (p.karsilama or "")[:300], "dil": p.dil,
        "gorsel": _gorsel_adresi(p.logo, mutlak=True), "renk": p.renk, "indekslenebilir": bool(p.arama_motoru),
        "adres_url": s.sayfa_adresi(p.slug), "tur": None,
    }
    if tur and s.SLUG_DESENI.match(tur.strip().lower()):
        t = (await db.execute(select(RandevuTurleri).where(RandevuTurleri.sayfa_id == p.id, RandevuTurleri.slug == tur.strip().lower(),
                                                           RandevuTurleri.aktif.is_(True)))).scalars().first()
        if t is not None:
            veri["tur"] = {"slug": t.slug, "ad": t.ad, "aciklama": (t.aciklama or "")[:300], "sure_dk": int(t.sure_dk),
                           "adres_url": s.sayfa_adresi(p.slug, t.slug)}
    return JSONResponse(veri, headers={"Cache-Control": "public, max-age=60", "X-Content-Type-Options": "nosniff"})


@acik_router.get("/{slug}/{tur}")
async def acik_tur(slug: str, tur: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    p = await _yayinda_sayfa(db, slug)
    t = await _yayinda_tur(db, p, tur)
    sahipler = await _ev_sahipleri(db, p, [t])
    _olay_ekle(arka, request, p.id, "tur", t.id)
    return JSONResponse({"sayfa": _acik_sayfa_sozlugu(p), "tur": _acik_tur_sozlugu(t, sahipler.get(t.id, []), ayrintili=True)},
                        headers={**ACIK_BASLIKLAR, "Cache-Control": "no-cache", **_robots(p)})


def _tz_sec(ham: Optional[str], yedek: str) -> str:
    if not ham:
        return yedek
    try:
        return s.saat_dilimi_duzelt(ham, "tz")
    except s.RandevuHatasi as h:
        raise _r_hatasi(h)


async def _musaitlik_yaniti(db: AsyncSession, p: RandevuSayfalari, t: RandevuTurleri, bas: Optional[str], gun: int,
                            tz: Optional[str], haric_id: Optional[int] = None) -> Dict[str, Any]:
    tz_adi = _tz_sec(tz, p.saat_dilimi)
    try:
        bas_gun = s.tarih_duzelt(bas, "bas") if bas else s.simdi().astimezone(s.saat_dilimi(tz_adi)).date()
    except s.RandevuHatasi as h:
        raise _r_hatasi(h)
    a, b = s.ziyaretci_araligi(bas_gun, gun, tz_adi)
    slotlar = await rk.musaitlik(db, p, t, a, b, haric_id=haric_id)
    simdi_ = s.simdi()
    return {
        "tz": tz_adi, "sayfa_tz": p.saat_dilimi, "bas": bas_gun.isoformat(), "gun": gun,
        "gunler": s.gunlere_bol(slotlar, tz_adi), "kapasite": int(t.kapasite or 1),
        "en_gec": s.iso(simdi_ + timedelta(days=int(t.en_gec_gun or 60))),
    }


@acik_router.get("/{slug}/{tur}/musaitlik")
async def acik_musaitlik(slug: str, tur: str, request: Request, bas: Optional[str] = Query(None),
                         gun: int = Query(7, ge=1, le=s.EN_COK_GUN), tz: Optional[str] = Query(None),
                         db: AsyncSession = Depends(get_db)):
    p = await _yayinda_sayfa(db, slug)
    _hiz(_musaitlik_hizi, _ziyaretci_anahtari(request, p.id))
    t = await _yayinda_tur(db, p, tur)
    return JSONResponse(await _musaitlik_yaniti(db, p, t, bas, gun, tz), headers=ACIK_BASLIKLAR)


async def _govde_oku(request: Request, sinir: int = 16384) -> Dict[str, Any]:
    """JSON gövde (gömülü pencereden `text/plain` da gelebilir: ön kontrol olmasın)."""
    ham = await request.body()
    if len(ham) > sinir:
        raise _hata(413, "govde_buyuk")
    try:
        govde = json.loads(ham.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise _hata(400, "govde_gecersiz")
    if not isinstance(govde, dict):
        raise _hata(400, "govde_gecersiz")
    return govde


async def _konum_coz(db: AsyncSession, t: RandevuTurleri, kisi_id: int, bas: datetime, haric: Optional[Randevular] = None) -> Optional[str]:
    if t.konum_turu == "jitsi":
        if haric is not None and haric.konum and int(t.kapasite or 1) == 1:
            return haric.konum  # yeniden planlamada oda aynı kalır
        if int(t.kapasite or 1) > 1:
            # Grup: aynı oturumun bütün katılımcıları aynı odada.
            mevcut_oda = (await db.execute(select(Randevular.konum).where(
                Randevular.tur_id == t.id, Randevular.kisi_id == kisi_id, Randevular.baslangic == bas,
                Randevular.durum == "onayli", Randevular.konum.is_not(None)).limit(1))).scalar()
            if mevcut_oda:
                return mevcut_oda
        return s.jitsi_odasi()
    return t.konum_degeri or None


def _acik_randevu_sozlugu(b: rk.Baglam, r: Randevular, takvim: bool = True) -> Dict[str, Any]:
    simdi_ = s.simdi()
    son = s.utc(r.baslangic) - timedelta(minutes=int(b.sayfa.iptal_sinir_dk or 0))
    d = {
        "uid": r.uid,
        "durum": r.durum,
        "baslangic": s.iso(r.baslangic),
        "bitis": s.iso(r.bitis),
        "onceki_baslangic": s.iso(r.onceki_baslangic),
        "ziyaretci_tz": r.ziyaretci_tz or b.sayfa.saat_dilimi,
        "ad": r.ad,
        "eposta": r.eposta,
        "konum_turu": b.tur.konum_turu,
        "konum": r.konum if b.tur.konum_turu != "telefon" or r.konum else None,
        "telefon": r.telefon,
        "iptal_eden": r.iptal_eden,
        "tur": {"slug": b.tur.slug, "ad": b.tur.ad, "sure_dk": int(b.tur.sure_dk), "renk": b.tur.renk},
        "sayfa": {"slug": b.sayfa.slug, "baslik": b.sayfa.baslik, "renk": b.sayfa.renk, "logo": _gorsel_adresi(b.sayfa.logo),
                  "dil": b.sayfa.dil, "saat_dilimi": b.sayfa.saat_dilimi, "iptal_sinir_dk": int(b.sayfa.iptal_sinir_dk or 0)},
        "kisi": b.kisi.ad if b.kisi else None,
        "degistirilebilir": r.durum == "onayli" and simdi_ < son,
        "son_degisiklik": s.iso(son),
        "gecti": s.utc(r.bitis) <= simdi_,
    }
    if takvim and r.durum == "onayli":
        d["takvim"] = rk.takvim_baglantilari(b, r, r.dil or b.sayfa.dil)
    return d


@acik_router.post("/{slug}/{tur}/rezervasyon")
async def acik_rezervasyon(slug: str, tur: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request)
    p = await _yayinda_sayfa(db, slug)
    await _kalici_hiz((_rezervasyon_hizi, _ziyaretci_anahtari(request, p.id)), (_sayfa_rezervasyon_hizi, str(p.id)))
    t = await _yayinda_tur(db, p, tur)
    # Bal küpü: bot "başarılı" görsün, hiçbir şey kaydedilmesin.
    if str(govde.get("web_adresi") or "").strip():
        logger.info("Randevu: bal küpü dolu, yok sayıldı (sayfa %s)", p.id)
        return JSONResponse({"ok": True, "randevu": None}, headers=ACIK_BASLIKLAR)
    bas = _an_coz(govde.get("baslangic"), "baslangic")
    try:
        tz = s.saat_dilimi_duzelt(govde.get("tz"), "tz") if govde.get("tz") else p.saat_dilimi
        ad = s.metin(govde.get("ad"), "ad", 120, zorunlu=True)
        eposta = s.eposta_duzelt(govde.get("eposta"))
        telefon_kurali = _etkin_telefon(t)
        telefon = None if telefon_kurali == "gizli" else s.telefon_duzelt(govde.get("telefon"), "telefon",
                                                                           zorunlu=telefon_kurali == "zorunlu")
        yanitlar = s.yanitlari_dogrula(s.json_yukle(t.sorular, []) or [], govde.get("yanitlar"))
        dil = govde.get("dil") if govde.get("dil") in s.DILLER else p.dil
        yer = await rk.yerlestir(db, p, t, bas)
    except s.RandevuHatasi as h:
        raise _r_hatasi(h)
    simdi_ = s.simdi()
    b_, e_, db_, de_ = s.tamponlu(bas, int(t.sure_dk), int(t.tampon_once_dk or 0), int(t.tampon_sonra_dk or 0))
    r = Randevular(
        uid=uuid.uuid4().hex, sayfa_id=p.id, tur_id=t.id, kisi_id=yer.kisi_id, hesap_email=p.hesap_email,
        baslangic=b_, bitis=e_, dolu_bas=db_, dolu_bit=de_, koltuk=yer.koltuk, durum="onayli", katilim="bilinmiyor",
        sira_no=0, ad=ad, eposta=eposta, telefon=telefon, yanitlar=s.json_yaz(yanitlar) if yanitlar else None,
        anonim=False, ziyaretci_tz=tz, dil=dil, konum=await _konum_coz(db, t, yer.kisi_id, bas),
        aydinlatma_at=simdi_, created_at=simdi_, updated_at=simdi_,
    )
    db.add(r)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "dolu", alan="baslangic")
    await db.refresh(r)
    arka.add_task(rk.bildir, r.id, "onay")
    if not p.hesap_email:
        arka.add_task(rk.crm_arka_plan, r.id)
    arka.add_task(_olay_yaz, _olay_verisi(request, p.id, "rezervasyon", t.id))
    k = (await db.execute(select(RandevuKisileri).where(RandevuKisileri.id == r.kisi_id))).scalars().first()
    b = rk.Baglam(p, t, k)
    jeton = s.yonetim_jetonu(r.id, r.uid)
    return JSONResponse({"ok": True, "randevu": _acik_randevu_sozlugu(b, r), "yonet_adresi": s.yonetim_adresi(jeton),
                         "jeton": jeton}, headers=ACIK_BASLIKLAR)


# ---------------------------------------------------------------------------
# İmzalı yönetim bağlantısı (girişsiz iptal / yeniden planlama)
# ---------------------------------------------------------------------------
async def _jetonlu(db: AsyncSession, request: Request, jeton: str) -> tuple:
    await _kalici_hiz((_islem_hizi, ip_ozeti("randevu-islem|" + istemci_ip(request))))
    kimlik = s.jeton_kimligi(jeton)
    if kimlik is None:
        raise _hata(404, "baglanti_gecersiz")
    r = (await db.execute(select(Randevular).where(Randevular.id == kimlik))).scalars().first()
    if r is None or not s.yonetim_jetonu_gecerli_mi(jeton, r.id, r.uid):
        raise _hata(404, "baglanti_gecersiz")
    if r.anonim or s.utc(r.bitis) + timedelta(days=s.JETON_OMRU_GUN) < s.simdi():
        raise _hata(410, "baglanti_suresi_doldu")
    b = await rk.baglam(db, r)
    if b is None:
        raise _hata(404, "baglanti_gecersiz")
    return r, b


def _degistirilebilir_mi(b: rk.Baglam, r: Randevular) -> None:
    if r.durum != "onayli":
        raise _hata(409, "zaten_iptal")
    son = s.utc(r.baslangic) - timedelta(minutes=int(b.sayfa.iptal_sinir_dk or 0))
    if s.simdi() >= son:
        raise _hata(409, "iptal_suresi_gecti", son=s.iso(son))


@islem_router.get("/{jeton}")
async def islem_ozeti(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    r, b = await _jetonlu(db, request, jeton)
    return JSONResponse(_acik_randevu_sozlugu(b, r), headers={**ACIK_BASLIKLAR, "X-Robots-Tag": "noindex"})


@islem_router.post("/{jeton}/iptal")
async def islem_iptal(jeton: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request, 4096)
    r, b = await _jetonlu(db, request, jeton)
    _degistirilebilir_mi(b, r)
    try:
        neden = s.metin(govde.get("neden"), "neden", 500, cok_satir=True)
    except s.RandevuHatasi as h:
        raise _r_hatasi(h)
    _iptal_et(r, "ziyaretci", neden)
    await db.commit()
    arka.add_task(rk.bildir, r.id, "iptal")
    return JSONResponse(_acik_randevu_sozlugu(b, r), headers=ACIK_BASLIKLAR)


@islem_router.get("/{jeton}/musaitlik")
async def islem_musaitlik(jeton: str, request: Request, bas: Optional[str] = Query(None),
                          gun: int = Query(7, ge=1, le=s.EN_COK_GUN), tz: Optional[str] = Query(None),
                          db: AsyncSession = Depends(get_db)):
    r, b = await _jetonlu(db, request, jeton)
    _degistirilebilir_mi(b, r)
    if not await _sayfa_yayinda_mi(db, b.sayfa) or not b.tur.aktif:
        raise _hata(410, "sayfa_pasif")
    return JSONResponse(await _musaitlik_yaniti(db, b.sayfa, b.tur, bas, gun, tz or r.ziyaretci_tz, haric_id=r.id),
                        headers=ACIK_BASLIKLAR)


@islem_router.post("/{jeton}/yeniden")
async def islem_yeniden(jeton: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request, 4096)
    r, b = await _jetonlu(db, request, jeton)
    _degistirilebilir_mi(b, r)
    if not await _sayfa_yayinda_mi(db, b.sayfa) or not b.tur.aktif:
        raise _hata(410, "sayfa_pasif")
    bas = _an_coz(govde.get("baslangic"), "baslangic")
    onceki = s.utc(r.baslangic)
    if bas == onceki:
        raise _hata(409, "ayni_zaman")
    try:
        yeni_tz = s.saat_dilimi_duzelt(govde.get("tz"), "tz") if govde.get("tz") else None
        yer = await rk.yerlestir(db, b.sayfa, b.tur, bas, haric=r)
    except s.RandevuHatasi as h:
        raise _r_hatasi(h)
    if yeni_tz:
        r.ziyaretci_tz = yeni_tz
    t = b.tur
    b_, e_, db_, de_ = s.tamponlu(bas, int(t.sure_dk), int(t.tampon_once_dk or 0), int(t.tampon_sonra_dk or 0))
    r.konum = await _konum_coz(db, t, yer.kisi_id, bas, haric=r)
    r.onceki_baslangic = onceki
    r.baslangic, r.bitis, r.dolu_bas, r.dolu_bit = b_, e_, db_, de_
    r.kisi_id, r.koltuk = yer.kisi_id, yer.koltuk
    r.sira_no = int(r.sira_no or 0) + 1
    r.katilim = "bilinmiyor"
    await rk.hatirlatmalari_atla(db, r, b.sayfa)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "dolu", alan="baslangic")
    await db.refresh(r)
    arka.add_task(rk.bildir, r.id, "yeniden", onceki)
    b = await rk.baglam(db, r) or b
    return JSONResponse(_acik_randevu_sozlugu(b, r), headers=ACIK_BASLIKLAR)


@islem_router.get("/{jeton}/takvim.ics")
async def islem_takvim(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    r, b = await _jetonlu(db, request, jeton)
    dil = r.dil or b.sayfa.dil
    metin_ = s.ics_uret([rk.ics_etkinligi(b, r, dil, iptal=r.durum != "onayli")], "PUBLISH")
    return Response(metin_, media_type="text/calendar; charset=utf-8", headers={
        "Content-Disposition": icerik_konumu(f"randevu-{b.tur.slug}.ics"), "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex",
    })


# ---------------------------------------------------------------------------
# ICS abonelik beslemesi (gizli jeton)
# ---------------------------------------------------------------------------
@besleme_router.get("/{jeton}.ics")
async def besleme(jeton: str, kisi: Optional[int] = Query(None), db: AsyncSession = Depends(get_db)):
    _hiz(_besleme_hizi, (jeton or "")[:80])
    coz = s.besleme_jetonu_coz(jeton)
    if coz is None:
        raise _hata(404, "bulunamadi")
    p = (await db.execute(select(RandevuSayfalari).where(RandevuSayfalari.id == coz[0]))).scalars().first()
    if p is None or not s.besleme_jetonu_gecerli_mi(jeton, p.id, int(p.besleme_surumu or 1)):
        raise _hata(404, "bulunamadi")
    if p.hesap_email:
        from services import moduller as modul_servisi

        if not await modul_servisi.modul_acik_mi(db, p.hesap_email, MODUL):
            raise _hata(404, "bulunamadi")
    metin_ = await rk.besleme_ics(db, p, kisi)
    return Response(metin_, media_type="text/calendar; charset=utf-8", headers={
        "Content-Disposition": 'inline; filename="randevular.ics"', "Cache-Control": "private, max-age=300",
        "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex",
    })


# ---------------------------------------------------------------------------
# Logo (herkese açık, değişmez)
# ---------------------------------------------------------------------------
@gorsel_router.get("/{anahtar}")
async def gorsel(anahtar: str, db: AsyncSession = Depends(get_db)):
    if len(anahtar) > 64:
        raise _hata(404, "bulunamadi")
    g = (await db.execute(select(RandevuGorselleri).where(RandevuGorselleri.anahtar == anahtar))).scalars().first()
    if g is None:
        raise _hata(404, "bulunamadi")
    from services import dosya_deposu

    try:
        veri = await dosya_deposu.oku(db, g.depo, f"randevu/{g.anahtar}.webp")
    except dosya_deposu.DepoHatasi:
        raise _hata(404, "bulunamadi")
    return Response(veri, media_type="image/webp", headers={
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
    })


# Yönetici ve müşteri router'ları ÖNCE; sabit önekli herkese açıklar (besleme, işlem, görsel)
# genel `/{slug}/{tur}` kalıbından önce.
router = (yonetici_router, musteri_router, besleme_router, islem_router, gorsel_router, acik_router)
