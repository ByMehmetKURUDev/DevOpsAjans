"""Faz 6H — Hukuk bürosu: müvekkil, dosya, duruşma/süre takibi, zaman ve masraf, müvekkil portalı.

Müşteri (`/api/v1/hukukum`; modül `hukuk_burosu` açık; ekip izni `hukuk`; GİZLİ dosya yalnız hesap
sahibine ve sorumlu avukata görünür — başkasına 404):
  GET /meta · GET|PUT /ayarlar · GET|POST /tatiller · PUT|DELETE /tatiller/{id} · POST /sure-hesapla
  GET|POST /muvekkiller · GET|PUT|DELETE /muvekkiller/{id} · POST /muvekkiller/{id}/geri-al
  POST|DELETE /muvekkiller/{id}/portal (imzalı bağlantı oluştur/yenile · iptal) · GET /randevu-kayitlari
  POST /catisma (çıkar çatışması: uyarı listesi, engelleme yok)
  GET|POST /dosyalar · GET|PUT|DELETE /dosyalar/{id} · POST /dosyalar/{id}/geri-al · GET /silinenler
  GET|POST /dosyalar/{id}/zaman · DELETE /dosyalar/{id}/zaman/{zid}
  GET|POST /dosyalar/{id}/masraflar · DELETE /dosyalar/{id}/masraflar/{mid} · POST /dosyalar/{id}/masraflar/{mid}/makbuz
  GET|POST /dosyalar/{id}/ekler · POST /dosyalar/{id}/ekler/baglanti · PUT|DELETE /dosyalar/{id}/ekler/{eid}
  GET /dosyalar/{id}/ekler/{eid}/indir · GET /dosyalar/{id}/dokum.pdf · GET /belgelerim
  GET|POST /olaylar · PUT|DELETE /olaylar/{id} · GET /takvim.ics?sorumlu=
  GET|POST /mesajlar · POST /mesajlar/okundu

Yönetici (`/api/v1/hukuk/yonetim`) — destek görünümü YALNIZ META VERİ (sayılar, depolama):
  GET /ozet · GET /hesap/{eposta}

Herkese açık (girişsiz, imzalı jeton; noindex, no-store, no-referrer):
  GET  /api/v1/hukuk/muvekkil/{jeton}                         dosyalarının yalnız "müvekkile görünür" alanları
  GET  /api/v1/hukuk/muvekkil/{jeton}/dosya/{did}/ek/{eid}     paylaşılan belge
  GET  /api/v1/hukuk/muvekkil/{jeton}/dosya/{did}/masraf.pdf   masraf dökümü (alan açıksa)
  POST /api/v1/hukuk/muvekkil/{jeton}/mesaj                    mesaj bırak (büronun panelinde bildirim;
                                                               ajansın gelen kutusuna DÜŞMEZ)

Yok: AI özelliği (hukuki görüş riski), UYAP entegrasyonu (açık API yok; kazıma yapılmaz), herkese açık
tanıtım sayfası / yorum isteme / ilan (Avukatlık Kanunu m.55 ve TBB reklam yasağı), tahsilat/ödeme.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from models.hukuk import (
    HukukAyarlari,
    HukukDosyalari,
    HukukEkleri,
    HukukHatirlatmalari,
    HukukMasraflari,
    HukukMesajlari,
    HukukMuvekkilleri,
    HukukOlaylari,
    HukukTatilleri,
    HukukZamanKayitlari,
)
from services import hukuk as s
from services import hukuk_kayit as k
from services.dosya_deposu import icerik_konumu
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

MODUL = s.MODUL
IZIN = s.IZIN

acik_router = APIRouter(prefix="/api/v1/hukuk", tags=["hukuk"])
yonetici_router = APIRouter(prefix="/api/v1/hukuk/yonetim", tags=["hukuk"], dependencies=[Depends(yonetici_gerekli)])
musteri_router = APIRouter(
    prefix="/api/v1/hukukum",
    tags=["hukuk"],
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(IZIN))],
)

_yazma_hizi = HizSiniri(120, 60.0)
_dosya_hizi = HizSiniri(30, 60.0)
_portal_hizi = KaliciHizSiniri("hukuk-portal", 120, 60.0)
_portal_mesaj_ip = KaliciHizSiniri("hukuk-portal-mesaj", 20, 3600.0)
_portal_mesaj_muvekkil = HizSiniri(5, 600.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _dosya_hizi, _portal_hizi, _portal_mesaj_ip, _portal_mesaj_muvekkil):
        h.temizle()


ACIK_BASLIKLAR = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
GIZLI_BASLIKLAR = {**ACIK_BASLIKLAR, "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"}


# ---------------------------------------------------------------------------
# Bağlam ve ortak yardımcılar
# ---------------------------------------------------------------------------
@dataclass
class Ctx:
    hesap: str
    kisi: str
    #: Hesap sahibi (gizli dosyaların hepsini görür).
    sahip: bool


def _ctx(request: Request) -> Ctx:
    b = izin_iste(request, IZIN)
    return Ctx(b.hesap_email, b.kisi_email, b.rol == "sahip")


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _e(h: s.TemelHata) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _hiz(sinir: HizSiniri, anahtar: str) -> None:
    if not sinir.izin_var_mi(anahtar or "anonim"):
        raise _hata(429, "cok_hizli")


async def _govde(request: Request, sinir: int = 65536) -> Dict[str, Any]:
    ham = await request.body()
    if len(ham) > sinir:
        raise _hata(413, "govde_buyuk")
    try:
        g = json.loads(ham.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise _hata(400, "govde_gecersiz")
    if not isinstance(g, dict):
        raise _hata(400, "govde_gecersiz")
    return g


def _id(ham: Any, alan: str) -> int:
    try:
        deger = int(ham)
    except (TypeError, ValueError):
        raise _hata(400, "gecersiz", alan=alan)
    if deger <= 0:
        raise _hata(400, "gecersiz", alan=alan)
    return deger


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def _muvekkil_soz(m: HukukMuvekkilleri, **ek: Any) -> Dict[str, Any]:
    return {
        "id": m.id, "tur": m.tur, "ad": m.ad, "yetkili": m.yetkili or "", "vergi_no": m.vergi_no or "",
        "eposta": m.eposta or "", "telefon": m.telefon or "", "adres": m.adres or "", "notlar": m.notlar or "",
        "kaynak": m.kaynak, "kaynak_id": m.kaynak_id, "portal_acik": bool(m.portal_acik),
        "portal_baglantisi": s.portal_adresi(s.muvekkil_jetonu(m.id, m.portal_surum)) if m.portal_acik else None,
        "portal_olusturma_at": s.iso(m.portal_olusturma_at), "portal_son_at": s.iso(m.portal_son_at),
        "silindi_at": s.iso(m.silindi_at), "created_at": s.iso(m.created_at), **ek,
    }


def _dosya_soz(d: HukukDosyalari, muvekkil_ad: Optional[str] = None, **ek: Any) -> Dict[str, Any]:
    return {
        "id": d.id, "muvekkil_id": d.muvekkil_id, "muvekkil_ad": muvekkil_ad, "tur": d.tur, "dosya_no": d.dosya_no or "",
        "esas_no": d.esas_no or "", "mahkeme": d.mahkeme or "", "karsi_taraflar": s.json_yukle(d.karsi_taraflar, []) or [],
        "konu": d.konu or "", "durum": d.durum, "sorumlu_email": d.sorumlu_email or "",
        "etiketler": s.json_yukle(d.etiketler, []) or [], "acilis_tarihi": s.gun_iso(d.acilis_tarihi),
        "kapanis_tarihi": s.gun_iso(d.kapanis_tarihi), "notlar": d.notlar or "", "gizli": bool(d.gizli),
        "portal_acik": bool(d.portal_acik), "portal_alanlari": s.portal_alanlari(d.portal_alanlari),
        "muvekkil_notu": d.muvekkil_notu or "", "baslik": s.dosya_basligi(d), "silindi_at": s.iso(d.silindi_at),
        "created_at": s.iso(d.created_at), "updated_at": s.iso(d.updated_at), **ek,
    }


def _olay_soz(o: HukukOlaylari, d: Optional[HukukDosyalari] = None, bugun=None) -> Dict[str, Any]:
    bugun = bugun or s.yerel_bugun()
    return {
        "id": o.id, "dosya_id": o.dosya_id, "dosya_baslik": s.dosya_basligi(d) if d is not None else None,
        "tur": o.tur, "baslik": o.baslik or "", "tarih": s.gun_iso(o.tarih), "saat": o.saat or "", "yer": o.yer or "",
        "notlar": o.notlar or "", "sorumlu_email": o.sorumlu_email or "", "tamamlandi": o.tamamlandi_at is not None,
        "kalan_gun": (o.tarih - bugun).days, "hesap": s.json_yukle(o.hesap, None), "gizli": bool(d.gizli) if d is not None else False,
    }


def _zaman_soz(z: HukukZamanKayitlari) -> Dict[str, Any]:
    return {"id": z.id, "dosya_id": z.dosya_id, "tarih": s.gun_iso(z.tarih), "sure_dk": int(z.sure_dk),
            "aciklama": z.aciklama or "", "faturalanabilir": bool(z.faturalanabilir), "kisi_email": z.kisi_email or ""}


def _masraf_soz(x: HukukMasraflari) -> Dict[str, Any]:
    return {"id": x.id, "dosya_id": x.dosya_id, "tur": x.tur, "tutar_kurus": int(x.tutar_kurus), "para_birimi": x.para_birimi,
            "tarih": s.gun_iso(x.tarih), "aciklama": x.aciklama or "", "avanstan": bool(x.avanstan),
            "makbuz_ek_id": x.makbuz_ek_id, "kisi_email": x.kisi_email or ""}


def _ek_soz(e: HukukEkleri) -> Dict[str, Any]:
    return {"id": e.id, "dosya_id": e.dosya_id, "tip": e.tip, "ad": e.ad, "tur": e.tur or "", "boyut": int(e.boyut or 0),
            "belge_id": e.belge_id, "muvekkile_gorunur": bool(e.muvekkile_gorunur), "yukleyen": e.yukleyen or "",
            "created_at": s.iso(e.created_at)}


def _mesaj_soz(m: HukukMesajlari) -> Dict[str, Any]:
    return {"id": m.id, "muvekkil_id": m.muvekkil_id, "dosya_id": m.dosya_id, "yon": m.yon, "metin": m.metin,
            "yazan": m.yazan or "", "okundu": m.okundu_at is not None, "created_at": s.iso(m.created_at)}


def _tatil_soz(t: HukukTatilleri) -> Dict[str, Any]:
    return {"id": t.id, "ad": t.ad, "tarih": s.gun_iso(t.tarih), "ay_gun": t.tarih.strftime("%m-%d") if t.tarih else None,
            "bitis": s.gun_iso(t.bitis), "tekrar": bool(t.tekrar), "yarim": bool(t.yarim), "tur": t.tur}


def _ayar_soz(a: Optional[HukukAyarlari], hesap: str) -> Dict[str, Any]:
    return {
        "buro_adi": (a.buro_adi if a else "") or "", "hatirlatma_gunleri": s.hatirlatma_gunleri(a.hatirlatma_gunleri if a else None),
        "sabah_saati": (a.sabah_saati if a else None) or "08:00", "adli_tatil_bas": (a.adli_tatil_bas if a else None) or "07-20",
        "adli_tatil_bit": (a.adli_tatil_bit if a else None) or "08-31",
        "adli_tatil_uzatma_gun": int(a.adli_tatil_uzatma_gun if a else 7),
        "adli_tatil_varsayilan": bool(a.adli_tatil_varsayilan) if a else True, "hesap": hesap,
    }


# ---------------------------------------------------------------------------
# Kayıt bulucular (hesap + gizlilik)
# ---------------------------------------------------------------------------
async def _muvekkil(db: AsyncSession, ctx: Ctx, mid: int, silinmis: Optional[bool] = False) -> HukukMuvekkilleri:
    sorgu = select(HukukMuvekkilleri).where(HukukMuvekkilleri.id == mid, HukukMuvekkilleri.hesap_email == ctx.hesap)
    if silinmis is not None:
        sorgu = sorgu.where(HukukMuvekkilleri.silindi_at.isnot(None) if silinmis else HukukMuvekkilleri.silindi_at.is_(None))
    m = (await db.execute(sorgu)).scalars().first()
    if m is None:
        raise _hata(404, "bulunamadi")
    return m


async def _dosya(db: AsyncSession, ctx: Ctx, did: int, silinmis: bool = False) -> HukukDosyalari:
    d = (await db.execute(select(HukukDosyalari).where(
        HukukDosyalari.id == did, HukukDosyalari.hesap_email == ctx.hesap,
        HukukDosyalari.silindi_at.isnot(None) if silinmis else HukukDosyalari.silindi_at.is_(None)))).scalars().first()
    # Gizli dosyanın varlığı da sızmasın: yetkisiz kişiye "yok".
    if d is None or not k.dosya_gorebilir_mi(d, ctx.kisi, ctx.sahip):
        raise _hata(404, "bulunamadi")
    return d


async def _muvekkil_adlari(db: AsyncSession, idler) -> Dict[int, str]:
    idler = sorted({i for i in idler if i})
    if not idler:
        return {}
    return {i: ad for i, ad in (await db.execute(select(HukukMuvekkilleri.id, HukukMuvekkilleri.ad)
                                                  .where(HukukMuvekkilleri.id.in_(idler)))).all()}


# ---------------------------------------------------------------------------
# Çıkar çatışması
# ---------------------------------------------------------------------------
async def _catisma(db: AsyncSession, ctx: Ctx, ad: Any, vergi_no: Any, rol: str, haric_muvekkil: Optional[int] = None,
                   haric_dosya: Optional[int] = None) -> List[Dict[str, Any]]:
    """Uyarı listesi (engelleme yok). Yeni MÜVEKKİL ↔ mevcut karşı taraf ve yeni KARŞI TARAF ↔ mevcut müvekkil
    = "catisma"; aynı roldeki benzer kayıt = "bilgi". Gizli dosyadaki eşleşme yetkisiz kişiye ayrıntısız döner."""
    if not str(ad or "").strip() and not str(vergi_no or "").strip():
        return []
    adaylar, dosyalar, muv = await k.catisma_adaylari(db, ctx.hesap)
    sonuc: List[Dict[str, Any]] = []
    for a, tur in s.eslesmeler(ad, vergi_no or None, adaylar):
        if a.rol == "muvekkil" and haric_muvekkil and a.muvekkil_id == haric_muvekkil:
            continue
        if a.rol == "karsi_taraf" and haric_dosya and a.dosya_id == haric_dosya:
            continue
        onem = "catisma" if a.rol != rol else "bilgi"
        d = dosyalar.get(a.dosya_id) if a.dosya_id else None
        if d is not None and not k.dosya_gorebilir_mi(d, ctx.kisi, ctx.sahip):
            sonuc.append({"rol": a.rol, "eslesme": tur, "onem": onem, "gizli": True})
            continue
        m = muv.get(a.muvekkil_id) if a.muvekkil_id else None
        sonuc.append({"rol": a.rol, "eslesme": tur, "onem": onem, "gizli": False, "ad": a.ad,
                      "muvekkil_id": a.muvekkil_id, "muvekkil_ad": m.ad if m else None, "dosya_id": a.dosya_id,
                      "dosya_baslik": s.dosya_basligi(d) if d is not None else None})
    return sonuc[:30]


# ---------------------------------------------------------------------------
# Müşteri uçları
# ---------------------------------------------------------------------------
@musteri_router.get("/meta")
async def meta(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    from services.moduller import modul_acik_mi

    sinir = await k.modul_ayari(db, ctx.hesap, "dosya_siniri", s.VARSAYILAN_DOSYA_SINIRI)
    gorunur = await k.gorunur_dosya_idleri(db, ctx.hesap, ctx.kisi, ctx.sahip)
    bugun = s.yerel_bugun()
    yaklasan = int((await db.execute(select(func.count(HukukOlaylari.id)).where(
        HukukOlaylari.hesap_email == ctx.hesap, HukukOlaylari.tamamlandi_at.is_(None), HukukOlaylari.tarih >= bugun,
        HukukOlaylari.tarih <= bugun + timedelta(days=s.YAKLASAN_GUN),
        or_(HukukOlaylari.dosya_id.is_(None), HukukOlaylari.dosya_id.in_(gorunur or [-1]))))).scalar() or 0)
    okunmamis = int((await db.execute(select(func.count(HukukMesajlari.id)).where(
        HukukMesajlari.hesap_email == ctx.hesap, HukukMesajlari.yon == "muvekkil", HukukMesajlari.okundu_at.is_(None),
        or_(HukukMesajlari.dosya_id.is_(None), HukukMesajlari.dosya_id.in_(gorunur or [-1]))))).scalar() or 0)
    return {
        "hesap": ctx.hesap, "kisi": ctx.kisi, "sahip": ctx.sahip, "dosya_siniri": sinir,
        "acik_dosya_sayisi": await k.acik_dosya_sayisi(db, ctx.hesap), "ekip": await k.ekip(db, ctx.hesap),
        "yaklasan_olay": yaklasan, "okunmamis_mesaj": okunmamis, "bugun": bugun.isoformat(),
        "belgeler_acik": await modul_acik_mi(db, ctx.hesap, "belgeler"),
        "muvekkil_turleri": list(s.MUVEKKIL_TURLERI), "dosya_turleri": list(s.DOSYA_TURLERI),
        "dosya_durumlari": list(s.DOSYA_DURUMLARI), "olay_turleri": list(s.OLAY_TURLERI),
        "masraf_turleri": list(s.MASRAF_TURLERI), "sure_birimleri": list(s.SURE_BIRIMLERI),
        "para_birimleri": list(s.PARA_BIRIMLERI), "portal_alanlari": dict(s.PORTAL_ALANLARI),
        "silinenler_gun": s.SILINENLER_GUN, "dosya_en_cok_mb": s.DOSYA_EN_COK_MB,
        # Dürüstlük: UYAP'tan otomatik veri çekilmez (açık API yok); AI yok.
        "uyap": False, "ai": False,
    }


@musteri_router.get("/ayarlar")
async def ayarlar_oku(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    return _ayar_soz(await k.ayarlar(db, ctx.hesap), ctx.hesap)


@musteri_router.put("/ayarlar")
async def ayarlar_yaz(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    g = await _govde(request)
    a = await k.ayarlar(db, ctx.hesap, olustur=True)
    try:
        if "buro_adi" in g:
            a.buro_adi = s.metin(g.get("buro_adi"), "buro_adi", 160) or None
        if "hatirlatma_gunleri" in g:
            a.hatirlatma_gunleri = s.json_yaz(s.hatirlatma_gunleri_duzelt(g.get("hatirlatma_gunleri")))
        if "sabah_saati" in g:
            a.sabah_saati = s.saat_duzelt(g.get("sabah_saati"), "sabah_saati") or "08:00"
        if "adli_tatil_bas" in g:
            a.adli_tatil_bas = s.ay_gun_duzelt(g.get("adli_tatil_bas"), "adli_tatil_bas")
        if "adli_tatil_bit" in g:
            a.adli_tatil_bit = s.ay_gun_duzelt(g.get("adli_tatil_bit"), "adli_tatil_bit")
        if a.adli_tatil_bit < a.adli_tatil_bas:
            raise s.HukukHatasi("bitis_once", "adli_tatil_bit")
        if "adli_tatil_uzatma_gun" in g:
            a.adli_tatil_uzatma_gun = s.tam_sayi(g.get("adli_tatil_uzatma_gun"), "adli_tatil_uzatma_gun", 0, 60)
        if "adli_tatil_varsayilan" in g:
            a.adli_tatil_varsayilan = s.bool_duzelt(g.get("adli_tatil_varsayilan"), "adli_tatil_varsayilan")
    except s.TemelHata as h:
        await db.rollback()
        raise _e(h)
    await db.commit()
    await db.refresh(a)
    return _ayar_soz(a, ctx.hesap)


# --- Tatiller ---------------------------------------------------------------
@musteri_router.get("/tatiller")
async def tatiller(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    if await k.tatilleri_tohumla(db, ctx.hesap):
        await db.commit()
    return {"items": [_tatil_soz(t) for t in await k.tatiller(db, ctx.hesap)],
            "sabitler": s.sabit_tatiller()}


def _tatil_uygula(t: HukukTatilleri, g: Dict[str, Any], yeni: bool) -> None:
    if "ad" in g or yeni:
        t.ad = s.metin(g.get("ad"), "ad", 120, zorunlu=True)
    if "tarih" in g or yeni:
        t.tarih = s.tarih_duzelt(g.get("tarih"), "tarih", bos_olabilir=False)
    if "bitis" in g:
        t.bitis = s.tarih_duzelt(g.get("bitis"), "bitis")
    if t.bitis is not None and t.bitis < t.tarih:
        raise s.HukukHatasi("bitis_once", "bitis")
    if t.bitis is not None and (t.bitis - t.tarih).days > 15:
        raise s.HukukHatasi("aralik_disi", "bitis", en_az=0, en_cok=15)
    for alan in ("tekrar", "yarim"):
        if alan in g:
            setattr(t, alan, s.bool_duzelt(g.get(alan), alan))
    if "tur" in g or yeni:
        t.tur = s.secim(g.get("tur") or "dini", s.TATIL_TURLERI, "tur")


@musteri_router.post("/tatiller")
async def tatil_ekle(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    g = await _govde(request)
    if int((await db.execute(select(func.count(HukukTatilleri.id)).where(HukukTatilleri.hesap_email == ctx.hesap))).scalar() or 0) >= 300:
        raise _hata(409, "cok_fazla", alan="tatiller", en_cok=300)
    t = HukukTatilleri(hesap_email=ctx.hesap, tekrar=False, yarim=False, created_at=s.simdi())
    try:
        _tatil_uygula(t, g, yeni=True)
    except s.TemelHata as h:
        raise _e(h)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _tatil_soz(t)


async def _tatil(db: AsyncSession, ctx: Ctx, tid: int) -> HukukTatilleri:
    t = (await db.execute(select(HukukTatilleri).where(HukukTatilleri.id == tid, HukukTatilleri.hesap_email == ctx.hesap))).scalars().first()
    if t is None:
        raise _hata(404, "bulunamadi")
    return t


@musteri_router.put("/tatiller/{tid}")
async def tatil_guncelle(tid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    t = await _tatil(db, ctx, tid)
    g = await _govde(request)
    try:
        _tatil_uygula(t, g, yeni=False)
    except s.TemelHata as h:
        await db.rollback()
        raise _e(h)
    await db.commit()
    await db.refresh(t)
    return _tatil_soz(t)


@musteri_router.delete("/tatiller/{tid}")
async def tatil_sil(tid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    t = await _tatil(db, ctx, tid)
    await db.delete(t)
    await db.commit()
    return {"ok": True}


@musteri_router.post("/sure-hesapla")
async def sure_hesapla(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    g = await _govde(request)
    try:
        sonuc = await k.sure_hesapla(db, ctx.hesap, g)
    except s.TemelHata as h:
        await db.rollback()
        raise _e(h)
    await db.commit()  # ilk hesapta sabit tatiller tohumlanmış olabilir
    return sonuc


# --- Müvekkiller -------------------------------------------------------------
async def _muvekkil_uygula(db: AsyncSession, ctx: Ctx, m: HukukMuvekkilleri, g: Dict[str, Any], yeni: bool) -> None:
    if "tur" in g or yeni:
        m.tur = s.secim(g.get("tur") or "kisi", s.MUVEKKIL_TURLERI, "tur")
    if "ad" in g or yeni:
        m.ad = s.metin(g.get("ad"), "ad", 200, zorunlu=True)
        m.ad_normal = s.ad_normalle(m.ad)
    for alan, sinir, cok in (("yetkili", 160, False), ("adres", 1000, True), ("notlar", 20000, True)):
        if alan in g:
            setattr(m, alan, s.metin(g.get(alan), alan, sinir, cok_satir=cok) or None)
    if "vergi_no" in g:
        m.vergi_no = s.vergi_no_duzelt(g.get("vergi_no"))
    if "eposta" in g:
        m.eposta = s.eposta_duzelt(g.get("eposta"), "eposta", zorunlu=False) or None
    if "telefon" in g:
        m.telefon = s.telefon_duzelt(g.get("telefon"), "telefon")
    if yeni and g.get("kaynak") == "randevu":
        from models.randevu import Randevular

        rid = _id(g.get("kaynak_id"), "kaynak_id")
        var = (await db.execute(select(Randevular.id).where(Randevular.id == rid, Randevular.hesap_email == ctx.hesap))).first()
        if var is None:
            raise s.HukukHatasi("bulunamadi", "kaynak_id", durum=404)
        m.kaynak, m.kaynak_id = "randevu", rid


@musteri_router.get("/muvekkiller")
async def muvekkiller(request: Request, q: Optional[str] = Query(None, max_length=120), db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    sorgu = select(HukukMuvekkilleri).where(HukukMuvekkilleri.hesap_email == ctx.hesap, HukukMuvekkilleri.silindi_at.is_(None))
    kayitlar = (await db.execute(sorgu.order_by(HukukMuvekkilleri.ad).limit(2000))).scalars().all()
    if q and q.strip():
        n = s.ad_normalle(q)
        kayitlar = [m for m in kayitlar if n in (m.ad_normal or "") or (m.vergi_no and q.strip().upper() in m.vergi_no)
                    or (m.eposta and q.strip().lower() in m.eposta)]
    gorunur = await k.gorunur_dosya_idleri(db, ctx.hesap, ctx.kisi, ctx.sahip)
    sayilar: Dict[int, int] = {}
    if gorunur:
        for mid, n_ in (await db.execute(select(HukukDosyalari.muvekkil_id, func.count(HukukDosyalari.id)).where(
                HukukDosyalari.id.in_(gorunur)).group_by(HukukDosyalari.muvekkil_id))).all():
            sayilar[mid] = int(n_)
    okunmamis: Dict[int, int] = {}
    for mid, n_ in (await db.execute(select(HukukMesajlari.muvekkil_id, func.count(HukukMesajlari.id)).where(
            HukukMesajlari.hesap_email == ctx.hesap, HukukMesajlari.yon == "muvekkil", HukukMesajlari.okundu_at.is_(None),
            or_(HukukMesajlari.dosya_id.is_(None), HukukMesajlari.dosya_id.in_(gorunur or [-1])))
            .group_by(HukukMesajlari.muvekkil_id))).all():
        okunmamis[mid] = int(n_)
    return {"items": [_muvekkil_soz(m, dosya_sayisi=sayilar.get(m.id, 0), okunmamis=okunmamis.get(m.id, 0)) for m in kayitlar],
            "toplam": len(kayitlar)}


@musteri_router.post("/muvekkiller")
async def muvekkil_ekle(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    g = await _govde(request)
    if int((await db.execute(select(func.count(HukukMuvekkilleri.id)).where(
            HukukMuvekkilleri.hesap_email == ctx.hesap, HukukMuvekkilleri.silindi_at.is_(None)))).scalar() or 0) >= 20000:
        raise _hata(409, "cok_fazla", alan="muvekkiller")
    m = HukukMuvekkilleri(hesap_email=ctx.hesap, kaynak="elle", portal_acik=False, portal_surum=0, olusturan=ctx.kisi,
                          created_at=s.simdi())
    try:
        await _muvekkil_uygula(db, ctx, m, g, yeni=True)
    except s.TemelHata as h:
        raise _e(h)
    catisma = await _catisma(db, ctx, m.ad, m.vergi_no, "muvekkil")
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return {"muvekkil": _muvekkil_soz(m), "catisma": catisma}


@musteri_router.get("/muvekkiller/{mid}")
async def muvekkil_getir(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    m = await _muvekkil(db, ctx, mid)
    gorunur = await k.gorunur_dosya_idleri(db, ctx.hesap, ctx.kisi, ctx.sahip)
    dosyalar = (await db.execute(select(HukukDosyalari).where(HukukDosyalari.muvekkil_id == m.id,
                                                               HukukDosyalari.id.in_(gorunur or [-1]))
                                 .order_by(HukukDosyalari.id.desc()))).scalars().all()
    return {**_muvekkil_soz(m), "dosyalar": [_dosya_soz(d, m.ad) for d in dosyalar]}


@musteri_router.put("/muvekkiller/{mid}")
async def muvekkil_guncelle(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    m = await _muvekkil(db, ctx, mid)
    g = await _govde(request)
    g.pop("kaynak", None)
    try:
        await _muvekkil_uygula(db, ctx, m, g, yeni=False)
    except s.TemelHata as h:
        await db.rollback()
        raise _e(h)
    catisma = await _catisma(db, ctx, m.ad, m.vergi_no, "muvekkil", haric_muvekkil=m.id) if ("ad" in g or "vergi_no" in g) else []
    await db.commit()
    await db.refresh(m)
    return {"muvekkil": _muvekkil_soz(m), "catisma": catisma}


@musteri_router.delete("/muvekkiller/{mid}")
async def muvekkil_sil(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Silinenlere taşır (30 gün geri alınabilir). Açık (silinmemiş) dosyası olan müvekkil silinmez."""
    ctx = _ctx(request)
    m = await _muvekkil(db, ctx, mid)
    dosya = int((await db.execute(select(func.count(HukukDosyalari.id)).where(
        HukukDosyalari.muvekkil_id == m.id, HukukDosyalari.silindi_at.is_(None)))).scalar() or 0)
    if dosya:
        raise _hata(409, "muvekkilin_dosyasi_var", sayi=dosya)
    m.silindi_at = s.simdi()
    m.portal_acik = False
    await db.commit()
    return {"ok": True, "geri_alinabilir_gun": s.SILINENLER_GUN}


@musteri_router.post("/muvekkiller/{mid}/geri-al")
async def muvekkil_geri_al(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    m = await _muvekkil(db, ctx, mid, silinmis=True)
    m.silindi_at = None
    await db.commit()
    await db.refresh(m)
    return _muvekkil_soz(m)


@musteri_router.post("/muvekkiller/{mid}/portal")
async def portal_olustur(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
    """İmzalı portal bağlantısı oluşturur ya da YENİLER (sürüm artar → eski bağlantı çalışmaz)."""
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    m = await _muvekkil(db, ctx, mid)
    m.portal_surum = int(m.portal_surum or 0) + 1
    m.portal_acik = True
    m.portal_olusturma_at = s.simdi()
    await db.commit()
    await db.refresh(m)
    return {"baglanti": s.portal_adresi(s.muvekkil_jetonu(m.id, m.portal_surum)), "muvekkil": _muvekkil_soz(m)}


@musteri_router.delete("/muvekkiller/{mid}/portal")
async def portal_iptal(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    m = await _muvekkil(db, ctx, mid)
    m.portal_acik = False
    await db.commit()
    return {"ok": True}


@musteri_router.get("/randevu-kayitlari")
async def randevu_kayitlari(request: Request, db: AsyncSession = Depends(get_db)):
    """Müvekkil formunu doldurmak için büronun kendi randevu kayıtları (son 90 gün; anonimleşmemiş)."""
    from models.randevu import Randevular

    ctx = _ctx(request)
    satirlar = (await db.execute(select(Randevular).where(
        Randevular.hesap_email == ctx.hesap, Randevular.anonim.is_(False),
        Randevular.baslangic >= s.simdi() - timedelta(days=90)).order_by(Randevular.baslangic.desc()).limit(100))).scalars().all()
    return {"items": [{"id": x.id, "ad": x.ad or "", "eposta": x.eposta or "", "telefon": x.telefon or "",
                       "baslangic": s.iso(x.baslangic), "durum": x.durum} for x in satirlar]}


@musteri_router.post("/catisma")
async def catisma_kontrol(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    g = await _govde(request)
    try:
        rol = s.secim(g.get("rol") or "muvekkil", ("muvekkil", "karsi_taraf"), "rol")
        vergi = s.vergi_no_duzelt(g.get("vergi_no"))
    except s.TemelHata as h:
        raise _e(h)
    haric_m = _id(g["haric_muvekkil_id"], "haric_muvekkil_id") if g.get("haric_muvekkil_id") else None
    haric_d = _id(g["haric_dosya_id"], "haric_dosya_id") if g.get("haric_dosya_id") else None
    return {"items": await _catisma(db, ctx, g.get("ad"), vergi, rol, haric_m, haric_d)}


# --- Dosyalar ------------------------------------------------------------------
async def _dosya_siniri_denetle(db: AsyncSession, ctx: Ctx) -> None:
    sinir = await k.modul_ayari(db, ctx.hesap, "dosya_siniri", s.VARSAYILAN_DOSYA_SINIRI)
    if sinir is not None and await k.acik_dosya_sayisi(db, ctx.hesap) >= int(sinir):
        raise _hata(409, "dosya_siniri", sinir=int(sinir))


async def _dosya_uygula(db: AsyncSession, ctx: Ctx, d: HukukDosyalari, g: Dict[str, Any], yeni: bool) -> None:
    if "muvekkil_id" in g or yeni:
        mid = _id(g.get("muvekkil_id"), "muvekkil_id")
        await _muvekkil(db, ctx, mid)
        d.muvekkil_id = mid
    if "tur" in g or yeni:
        d.tur = s.secim(g.get("tur") or "dava", s.DOSYA_TURLERI, "tur")
    for alan, sinir, cok in (("dosya_no", 60, False), ("esas_no", 60, False), ("mahkeme", 200, False), ("konu", 300, False),
                             ("notlar", 20000, True), ("muvekkil_notu", 2000, True)):
        if alan in g:
            setattr(d, alan, s.metin(g.get(alan), alan, sinir, cok_satir=cok) or None)
    if "karsi_taraflar" in g:
        d.karsi_taraflar = s.json_yaz(s.karsi_taraflar_duzelt(g.get("karsi_taraflar")))
    if "etiketler" in g:
        d.etiketler = s.json_yaz(s.etiketler_duzelt(g.get("etiketler")))
    if "durum" in g or yeni:
        d.durum = s.secim(g.get("durum") or "acik", s.DOSYA_DURUMLARI, "durum")
    if "sorumlu_email" in g:
        e = s.eposta_duzelt(g.get("sorumlu_email"), "sorumlu_email", zorunlu=False) or None
        if e and not await k.sorumlu_gecerli_mi(db, ctx.hesap, e):
            raise s.HukukHatasi("sorumlu_gecersiz", "sorumlu_email")
        d.sorumlu_email = e
    elif yeni:
        d.sorumlu_email = ctx.kisi
    if "acilis_tarihi" in g:
        d.acilis_tarihi = s.tarih_duzelt(g.get("acilis_tarihi"), "acilis_tarihi")
    elif yeni:
        d.acilis_tarihi = s.yerel_bugun()
    if "kapanis_tarihi" in g:
        d.kapanis_tarihi = s.tarih_duzelt(g.get("kapanis_tarihi"), "kapanis_tarihi")
    if d.durum == "kapandi" and d.kapanis_tarihi is None:
        d.kapanis_tarihi = s.yerel_bugun()
    if d.acilis_tarihi and d.kapanis_tarihi and d.kapanis_tarihi < d.acilis_tarihi:
        raise s.HukukHatasi("bitis_once", "kapanis_tarihi")
    for alan in ("gizli", "portal_acik"):
        if alan in g:
            setattr(d, alan, s.bool_duzelt(g.get(alan), alan))
    if "portal_alanlari" in g:
        d.portal_alanlari = s.json_yaz(s.portal_alanlari_duzelt(g.get("portal_alanlari")))
    # Gizli yapan kişi kendi erişimini kaybetmesin (yalnız sahip ya da sorumlu gizli dosyayı görür).
    if d.gizli and not k.dosya_gorebilir_mi(d, ctx.kisi, ctx.sahip):
        raise s.HukukHatasi("gizli_erisim_kaybi", "gizli", durum=409)


async def _dosya_listesi(db: AsyncSession, ctx: Ctx, kayitlar: List[HukukDosyalari]) -> List[Dict[str, Any]]:
    adlar = await _muvekkil_adlari(db, [d.muvekkil_id for d in kayitlar])
    idler = [d.id for d in kayitlar]
    sonraki: Dict[int, Dict[str, Any]] = {}
    if idler:
        bugun = s.yerel_bugun()
        for o in (await db.execute(select(HukukOlaylari).where(
                HukukOlaylari.dosya_id.in_(idler), HukukOlaylari.tamamlandi_at.is_(None), HukukOlaylari.tarih >= bugun)
                .order_by(HukukOlaylari.tarih, HukukOlaylari.saat).limit(5000))).scalars().all():
            sonraki.setdefault(o.dosya_id, {"tur": o.tur, "tarih": s.gun_iso(o.tarih), "saat": o.saat or "",
                                            "kalan_gun": (o.tarih - bugun).days})
    return [_dosya_soz(d, adlar.get(d.muvekkil_id), sonraki_olay=sonraki.get(d.id)) for d in kayitlar]


@musteri_router.get("/dosyalar")
async def dosyalar(request: Request, durum: Optional[str] = Query(None), muvekkil_id: Optional[int] = Query(None),
                   q: Optional[str] = Query(None, max_length=120), sorumlu: Optional[str] = Query(None, max_length=254),
                   db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    sorgu = select(HukukDosyalari).where(HukukDosyalari.hesap_email == ctx.hesap, HukukDosyalari.silindi_at.is_(None),
                                         k.gorunur_dosya_kosulu(ctx.kisi, ctx.sahip))
    if durum in s.DOSYA_DURUMLARI:
        sorgu = sorgu.where(HukukDosyalari.durum == durum)
    if muvekkil_id:
        sorgu = sorgu.where(HukukDosyalari.muvekkil_id == muvekkil_id)
    if sorumlu:
        sorgu = sorgu.where(HukukDosyalari.sorumlu_email == sorumlu.strip().lower())
    kayitlar = list((await db.execute(sorgu.order_by(HukukDosyalari.id.desc()).limit(2000))).scalars().all())
    if q and q.strip():
        n = s.ad_normalle(q)
        adlar = await _muvekkil_adlari(db, [d.muvekkil_id for d in kayitlar])

        def uyar(d: HukukDosyalari) -> bool:
            alanlar = [d.dosya_no, d.esas_no, d.mahkeme, d.konu, adlar.get(d.muvekkil_id)] + \
                [x.get("ad") for x in (s.json_yukle(d.karsi_taraflar, []) or []) if isinstance(x, dict)] + \
                list(s.json_yukle(d.etiketler, []) or [])
            return any(n in s.ad_normalle(x) for x in alanlar if x)

        kayitlar = [d for d in kayitlar if uyar(d)]
    return {"items": await _dosya_listesi(db, ctx, kayitlar), "toplam": len(kayitlar)}


@musteri_router.post("/dosyalar")
async def dosya_ekle(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    g = await _govde(request)
    d = HukukDosyalari(hesap_email=ctx.hesap, olusturan=ctx.kisi, gizli=False, portal_acik=False, created_at=s.simdi())
    try:
        await _dosya_uygula(db, ctx, d, g, yeni=True)
    except s.TemelHata as h:
        raise _e(h)
    if d.durum in ("acik", "beklemede"):
        await _dosya_siniri_denetle(db, ctx)
    catisma: List[Dict[str, Any]] = []
    for x in s.json_yukle(d.karsi_taraflar, []) or []:
        for c in await _catisma(db, ctx, x.get("ad"), x.get("vergi_no") or None, "karsi_taraf"):
            catisma.append({**c, "aranan": x.get("ad")})
    db.add(d)
    await db.commit()
    await db.refresh(d)
    adlar = await _muvekkil_adlari(db, [d.muvekkil_id])
    return {"dosya": _dosya_soz(d, adlar.get(d.muvekkil_id)), "catisma": catisma}


@musteri_router.get("/dosyalar/{did}")
async def dosya_getir(did: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    d = await _dosya(db, ctx, did)
    return (await _dosya_listesi(db, ctx, [d]))[0]


@musteri_router.put("/dosyalar/{did}")
async def dosya_guncelle(did: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    d = await _dosya(db, ctx, did)
    onceki_durum = d.durum
    g = await _govde(request)
    try:
        await _dosya_uygula(db, ctx, d, g, yeni=False)
    except s.TemelHata as h:
        await db.rollback()
        raise _e(h)
    if onceki_durum == "kapandi" and d.durum != "kapandi":
        d.kapanis_tarihi = None if "kapanis_tarihi" not in g else d.kapanis_tarihi
        await db.flush()
        sinir = await k.modul_ayari(db, ctx.hesap, "dosya_siniri", s.VARSAYILAN_DOSYA_SINIRI)
        if sinir is not None and await k.acik_dosya_sayisi(db, ctx.hesap) > int(sinir):
            await db.rollback()
            raise _hata(409, "dosya_siniri", sinir=int(sinir))
    catisma: List[Dict[str, Any]] = []
    if "karsi_taraflar" in g:
        for x in s.json_yukle(d.karsi_taraflar, []) or []:
            for c in await _catisma(db, ctx, x.get("ad"), x.get("vergi_no") or None, "karsi_taraf", haric_dosya=d.id):
                catisma.append({**c, "aranan": x.get("ad")})
    await db.commit()
    await db.refresh(d)
    return {"dosya": (await _dosya_listesi(db, ctx, [d]))[0], "catisma": catisma}


@musteri_router.delete("/dosyalar/{did}")
async def dosya_sil(did: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    d = await _dosya(db, ctx, did)
    d.silindi_at = s.simdi()
    await db.commit()
    return {"ok": True, "geri_alinabilir_gun": s.SILINENLER_GUN}


@musteri_router.post("/dosyalar/{did}/geri-al")
async def dosya_geri_al(did: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    d = await _dosya(db, ctx, did, silinmis=True)
    m = (await db.execute(select(HukukMuvekkilleri).where(HukukMuvekkilleri.id == d.muvekkil_id))).scalars().first()
    if m is None or m.silindi_at is not None:
        raise _hata(409, "muvekkil_silindi")
    if d.durum in ("acik", "beklemede"):
        await _dosya_siniri_denetle(db, ctx)
    d.silindi_at = None
    await db.commit()
    await db.refresh(d)
    return (await _dosya_listesi(db, ctx, [d]))[0]


@musteri_router.get("/silinenler")
async def silinenler(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    muv = (await db.execute(select(HukukMuvekkilleri).where(HukukMuvekkilleri.hesap_email == ctx.hesap,
                                                             HukukMuvekkilleri.silindi_at.isnot(None))
                            .order_by(HukukMuvekkilleri.silindi_at.desc()).limit(500))).scalars().all()
    dos = (await db.execute(select(HukukDosyalari).where(HukukDosyalari.hesap_email == ctx.hesap,
                                                          HukukDosyalari.silindi_at.isnot(None),
                                                          k.gorunur_dosya_kosulu(ctx.kisi, ctx.sahip))
                            .order_by(HukukDosyalari.silindi_at.desc()).limit(500))).scalars().all()
    adlar = await _muvekkil_adlari(db, [d.muvekkil_id for d in dos])
    return {"muvekkiller": [_muvekkil_soz(m) for m in muv], "dosyalar": [_dosya_soz(d, adlar.get(d.muvekkil_id)) for d in dos],
            "gun": s.SILINENLER_GUN}


# --- Zaman kayıtları ---------------------------------------------------------------
@musteri_router.get("/dosyalar/{did}/zaman")
async def zaman_listesi(did: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    d = await _dosya(db, ctx, did)
    kayitlar = (await db.execute(select(HukukZamanKayitlari).where(HukukZamanKayitlari.dosya_id == d.id)
                                 .order_by(HukukZamanKayitlari.tarih.desc(), HukukZamanKayitlari.id.desc()))).scalars().all()
    toplam = sum(int(z.sure_dk) for z in kayitlar)
    fat = sum(int(z.sure_dk) for z in kayitlar if z.faturalanabilir)
    return {"items": [_zaman_soz(z) for z in kayitlar], "toplam_dk": toplam, "faturalanabilir_dk": fat}


@musteri_router.post("/dosyalar/{did}/zaman")
async def zaman_ekle(did: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    d = await _dosya(db, ctx, did)
    g = await _govde(request)
    try:
        z = HukukZamanKayitlari(
            hesap_email=ctx.hesap, dosya_id=d.id, tarih=s.tarih_duzelt(g.get("tarih"), "tarih") or s.yerel_bugun(),
            sure_dk=s.tam_sayi(g.get("sure_dk"), "sure_dk", 1, 1440), aciklama=s.metin(g.get("aciklama"), "aciklama", 500) or None,
            faturalanabilir=s.bool_duzelt(g.get("faturalanabilir", True), "faturalanabilir"), kisi_email=ctx.kisi,
            created_at=s.simdi())
    except s.TemelHata as h:
        raise _e(h)
    db.add(z)
    await db.commit()
    await db.refresh(z)
    return _zaman_soz(z)


@musteri_router.delete("/dosyalar/{did}/zaman/{zid}")
async def zaman_sil(did: int, zid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    d = await _dosya(db, ctx, did)
    z = (await db.execute(select(HukukZamanKayitlari).where(HukukZamanKayitlari.id == zid, HukukZamanKayitlari.dosya_id == d.id))).scalars().first()
    if z is None:
        raise _hata(404, "bulunamadi")
    await db.delete(z)
    await db.commit()
    return {"ok": True}


# --- Masraflar --------------------------------------------------------------------
def _masraf_toplamlari(kayitlar) -> List[Dict[str, Any]]:
    t: Dict[str, Dict[str, int]] = {}
    for x in kayitlar:
        b = t.setdefault(x.para_birimi, {"toplam_kurus": 0, "avans_kurus": 0})
        b["toplam_kurus"] += int(x.tutar_kurus)
        if x.avanstan:
            b["avans_kurus"] += int(x.tutar_kurus)
    return [{"para_birimi": pb, **v} for pb, v in sorted(t.items())]


@musteri_router.get("/dosyalar/{did}/masraflar")
async def masraf_listesi(did: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    d = await _dosya(db, ctx, did)
    kayitlar = (await db.execute(select(HukukMasraflari).where(HukukMasraflari.dosya_id == d.id)
                                 .order_by(HukukMasraflari.tarih.desc(), HukukMasraflari.id.desc()))).scalars().all()
    return {"items": [_masraf_soz(x) for x in kayitlar], "toplamlar": _masraf_toplamlari(kayitlar)}


@musteri_router.post("/dosyalar/{did}/masraflar")
async def masraf_ekle(did: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    d = await _dosya(db, ctx, did)
    g = await _govde(request)
    try:
        x = HukukMasraflari(
            hesap_email=ctx.hesap, dosya_id=d.id, tur=s.secim(g.get("tur") or "diger", s.MASRAF_TURLERI, "tur"),
            tutar_kurus=s.tutar_kurus(g.get("tutar")), para_birimi=s.secim(g.get("para_birimi") or "TRY", s.PARA_BIRIMLERI, "para_birimi"),
            tarih=s.tarih_duzelt(g.get("tarih"), "tarih") or s.yerel_bugun(), aciklama=s.metin(g.get("aciklama"), "aciklama", 300) or None,
            avanstan=s.bool_duzelt(g.get("avanstan", False), "avanstan"), kisi_email=ctx.kisi, created_at=s.simdi())
    except s.TemelHata as h:
        raise _e(h)
    db.add(x)
    await db.commit()
    await db.refresh(x)
    return _masraf_soz(x)


async def _masraf(db: AsyncSession, d: HukukDosyalari, mid: int) -> HukukMasraflari:
    x = (await db.execute(select(HukukMasraflari).where(HukukMasraflari.id == mid, HukukMasraflari.dosya_id == d.id))).scalars().first()
    if x is None:
        raise _hata(404, "bulunamadi")
    return x


@musteri_router.delete("/dosyalar/{did}/masraflar/{mid}")
async def masraf_sil(did: int, mid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    d = await _dosya(db, ctx, did)
    x = await _masraf(db, d, mid)
    if x.makbuz_ek_id:
        await k.ekleri_sil(db, (await db.execute(select(HukukEkleri).where(HukukEkleri.id == x.makbuz_ek_id,
                                                                            HukukEkleri.dosya_id == d.id))).scalars().all())
    await db.delete(x)
    await db.commit()
    return {"ok": True}


async def _dosya_oku(dosya: UploadFile, db: AsyncSession) -> bytes:
    from services import dosyalar

    try:
        sinir = min(await dosyalar.boyut_siniri_bayt(db), s.DOSYA_EN_COK_MB * 1024 * 1024)
        return await dosyalar.akistan_oku(dosya, sinir)
    except dosyalar.DosyaHatasi as h:
        raise _hata(h.durum, h.kod, **h.ek)


async def _ek_kaydet(db: AsyncSession, ctx: Ctx, d: HukukDosyalari, dosya: UploadFile, tip: str, gorunur: bool) -> HukukEkleri:
    import secrets

    from services import dosya_deposu, dosyalar

    veri = await _dosya_oku(dosya, db)
    try:
        ad = dosyalar.ad_temizle(dosya.filename or "dosya")
        mime = dosyalar.turu_dogrula(ad, veri)
    except dosyalar.DosyaHatasi as h:
        raise _hata(h.durum, h.kod, **h.ek)
    an = s.simdi()
    anahtar = f"hukuk/{an:%Y/%m}/{secrets.token_hex(16)}"
    try:
        depo = await dosya_deposu.yaz(db, anahtar, veri, mime)
    except dosya_deposu.DepoHatasi:
        raise _hata(502, "depo_hatasi")
    e = HukukEkleri(hesap_email=ctx.hesap, dosya_id=d.id, tip=tip, ad=ad[:200], tur=mime, boyut=len(veri), depo=depo,
                    anahtar=anahtar, muvekkile_gorunur=gorunur, yukleyen=ctx.kisi, created_at=an)
    db.add(e)
    await db.flush()
    return e


@musteri_router.post("/dosyalar/{did}/masraflar/{mid}/makbuz")
async def makbuz_yukle(did: int, mid: int, request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_dosya_hizi, ctx.kisi)
    d = await _dosya(db, ctx, did)
    x = await _masraf(db, d, mid)
    eski = x.makbuz_ek_id
    e = await _ek_kaydet(db, ctx, d, dosya, "makbuz", False)
    x.makbuz_ek_id = e.id
    if eski:
        await k.ekleri_sil(db, (await db.execute(select(HukukEkleri).where(HukukEkleri.id == eski, HukukEkleri.dosya_id == d.id))).scalars().all())
    await db.commit()
    await db.refresh(x)
    return {"masraf": _masraf_soz(x), "ek": _ek_soz(e)}


# --- Ekler (belgeler) -----------------------------------------------------------------
async def _ek(db: AsyncSession, d: HukukDosyalari, eid: int) -> HukukEkleri:
    e = (await db.execute(select(HukukEkleri).where(HukukEkleri.id == eid, HukukEkleri.dosya_id == d.id))).scalars().first()
    if e is None:
        raise _hata(404, "bulunamadi")
    return e


@musteri_router.get("/dosyalar/{did}/ekler")
async def ek_listesi(did: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    d = await _dosya(db, ctx, did)
    kayitlar = (await db.execute(select(HukukEkleri).where(HukukEkleri.dosya_id == d.id).order_by(HukukEkleri.id.desc()))).scalars().all()
    return {"items": [_ek_soz(e) for e in kayitlar], "toplam_bayt": sum(int(e.boyut or 0) for e in kayitlar)}


@musteri_router.post("/dosyalar/{did}/ekler")
async def ek_yukle(did: int, request: Request, dosya: UploadFile = File(...), muvekkile_gorunur: str = Form("false"),
                   db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_dosya_hizi, ctx.kisi)
    d = await _dosya(db, ctx, did)
    if int((await db.execute(select(func.count(HukukEkleri.id)).where(HukukEkleri.dosya_id == d.id))).scalar() or 0) >= 500:
        raise _hata(409, "cok_fazla", alan="ekler", en_cok=500)
    e = await _ek_kaydet(db, ctx, d, dosya, "belge", str(muvekkile_gorunur).lower() in ("1", "true", "evet", "on"))
    await db.commit()
    await db.refresh(e)
    return _ek_soz(e)


@musteri_router.post("/dosyalar/{did}/ekler/baglanti")
async def ek_baglanti(did: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Belgeler (5B) modülündeki bir kayda bağlantı (isteğe bağlı; içerik kopyalanmaz)."""
    from models.belgeler import Belgeler

    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    d = await _dosya(db, ctx, did)
    g = await _govde(request)
    bid = _id(g.get("belge_id"), "belge_id")
    b = (await db.execute(select(Belgeler).where(Belgeler.id == bid, Belgeler.sahip_hesap == ctx.hesap))).scalars().first()
    if b is None:
        raise _hata(404, "bulunamadi", alan="belge_id")
    e = HukukEkleri(hesap_email=ctx.hesap, dosya_id=d.id, tip="baglanti", ad=b.baslik[:200], boyut=0, belge_id=b.id,
                    muvekkile_gorunur=False, yukleyen=ctx.kisi, created_at=s.simdi())
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return _ek_soz(e)


@musteri_router.put("/dosyalar/{did}/ekler/{eid}")
async def ek_guncelle(did: int, eid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    d = await _dosya(db, ctx, did)
    e = await _ek(db, d, eid)
    g = await _govde(request)
    try:
        if "muvekkile_gorunur" in g:
            gorunur = s.bool_duzelt(g.get("muvekkile_gorunur"), "muvekkile_gorunur")
            if gorunur and e.tip == "baglanti":
                raise s.HukukHatasi("baglanti_paylasilamaz", "muvekkile_gorunur")
            e.muvekkile_gorunur = gorunur
        if "ad" in g and e.tip != "baglanti":
            e.ad = s.metin(g.get("ad"), "ad", 200, zorunlu=True)
    except s.TemelHata as h:
        await db.rollback()
        raise _e(h)
    await db.commit()
    await db.refresh(e)
    return _ek_soz(e)


@musteri_router.delete("/dosyalar/{did}/ekler/{eid}")
async def ek_sil(did: int, eid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    d = await _dosya(db, ctx, did)
    e = await _ek(db, d, eid)
    for x in (await db.execute(select(HukukMasraflari).where(HukukMasraflari.makbuz_ek_id == e.id))).scalars().all():
        x.makbuz_ek_id = None
    await k.ekleri_sil(db, [e])
    await db.commit()
    return {"ok": True}


async def _ek_yaniti(db: AsyncSession, e: HukukEkleri, basliklar: Optional[Dict[str, str]] = None) -> Response:
    from services import dosya_deposu

    if not e.depo or not e.anahtar:
        raise _hata(404, "bulunamadi")
    adres = dosya_deposu.dogrudan_adres(e.depo, e.anahtar, e.ad, e.tur or "application/octet-stream")
    if adres:
        return RedirectResponse(adres, status_code=302, headers={"Cache-Control": "no-store", **(basliklar or {})})
    try:
        veri = await dosya_deposu.oku(db, e.depo, e.anahtar)
    except dosya_deposu.DepoHatasi:
        raise _hata(502, "depo_hatasi")
    return Response(veri, media_type=e.tur or "application/octet-stream",
                    headers={"Content-Disposition": icerik_konumu(e.ad), "Cache-Control": "no-store",
                             "X-Content-Type-Options": "nosniff", **(basliklar or {})})


@musteri_router.get("/dosyalar/{did}/ekler/{eid}/indir")
async def ek_indir(did: int, eid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    d = await _dosya(db, ctx, did)
    return await _ek_yaniti(db, await _ek(db, d, eid))


@musteri_router.get("/belgelerim")
async def belgelerim(request: Request, db: AsyncSession = Depends(get_db)):
    """Bağlanabilecek Belgeler (5B) kayıtları — yalnız modül açıksa (başlık + id)."""
    from models.belgeler import Belgeler
    from services.moduller import modul_acik_mi

    ctx = _ctx(request)
    if not await modul_acik_mi(db, ctx.hesap, "belgeler"):
        return {"items": [], "modul_acik": False}
    satirlar = (await db.execute(select(Belgeler.id, Belgeler.baslik, Belgeler.tur).where(Belgeler.sahip_hesap == ctx.hesap)
                                 .order_by(Belgeler.id.desc()).limit(300))).all()
    return {"items": [{"id": i, "baslik": b, "tur": t} for i, b, t in satirlar], "modul_acik": True}


@musteri_router.get("/dosyalar/{did}/dokum.pdf")
async def dokum(did: int, request: Request, dil: str = Query("tr", max_length=5), masraf: bool = Query(True),
                zaman: bool = Query(True), db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    d = await _dosya(db, ctx, did)
    pdf = await _dokum_pdf(db, d, dil, masraf=masraf, zaman=zaman)
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": icerik_konumu(s.pdf_dosya_adi("dokum", d)), "Cache-Control": "no-store"})


async def _dokum_pdf(db: AsyncSession, d: HukukDosyalari, dil: str, masraf: bool = True, zaman: bool = True) -> bytes:
    a = await k.ayarlar(db, d.hesap_email)
    m = (await db.execute(select(HukukMuvekkilleri).where(HukukMuvekkilleri.id == d.muvekkil_id))).scalars().first()
    masraflar = [_masraf_soz(x) for x in (await db.execute(select(HukukMasraflari).where(HukukMasraflari.dosya_id == d.id)
                                                             .order_by(HukukMasraflari.tarih, HukukMasraflari.id))).scalars().all()] if masraf else []
    zamanlar = [_zaman_soz(z) for z in (await db.execute(select(HukukZamanKayitlari).where(HukukZamanKayitlari.dosya_id == d.id)
                                                          .order_by(HukukZamanKayitlari.tarih, HukukZamanKayitlari.id))).scalars().all()] if zaman else None
    return s.dokum_pdf(buro_adi=(a.buro_adi if a and a.buro_adi else d.hesap_email), muvekkil_adi=m.ad if m else "",
                       dosya={"baslik": s.dosya_basligi(d, dil), "mahkeme": d.mahkeme or ""}, masraflar=masraflar,
                       zamanlar=zamanlar, dil=dil)


# --- Olaylar / takvim ----------------------------------------------------------------
async def _olay_uygula(db: AsyncSession, ctx: Ctx, o: HukukOlaylari, g: Dict[str, Any], yeni: bool) -> None:
    if "dosya_id" in g or yeni:
        if g.get("dosya_id"):
            d = await _dosya(db, ctx, _id(g.get("dosya_id"), "dosya_id"))
            o.dosya_id = d.id
        else:
            o.dosya_id = None
    if "tur" in g or yeni:
        o.tur = s.secim(g.get("tur") or "durusma", s.OLAY_TURLERI, "tur")
    if isinstance(g.get("hesap"), dict) and o.tur == "kesin_sure":
        # Süre hesaplayıcının girdisi sunucuda yeniden hesaplanır (istemcinin adımlarına güvenilmez).
        h = await k.sure_hesapla(db, ctx.hesap, g["hesap"])
        o.hesap = s.json_yaz(h)
        if not g.get("tarih"):
            g["tarih"] = h["son_gun"]
    if "tarih" in g or yeni:
        o.tarih = s.tarih_duzelt(g.get("tarih"), "tarih", bos_olabilir=False)
    if "saat" in g:
        o.saat = s.saat_duzelt(g.get("saat"))
    for alan, sinir, cok in (("baslik", 200, False), ("yer", 200, False), ("notlar", 5000, True)):
        if alan in g:
            setattr(o, alan, s.metin(g.get(alan), alan, sinir, cok_satir=cok) or None)
    if "sorumlu_email" in g:
        e = s.eposta_duzelt(g.get("sorumlu_email"), "sorumlu_email", zorunlu=False) or None
        if e and not await k.sorumlu_gecerli_mi(db, ctx.hesap, e):
            raise s.HukukHatasi("sorumlu_gecersiz", "sorumlu_email")
        o.sorumlu_email = e
    if "tamamlandi" in g:
        o.tamamlandi_at = s.simdi() if s.bool_duzelt(g.get("tamamlandi"), "tamamlandi") else None


async def _olay(db: AsyncSession, ctx: Ctx, oid: int) -> HukukOlaylari:
    o = (await db.execute(select(HukukOlaylari).where(HukukOlaylari.id == oid, HukukOlaylari.hesap_email == ctx.hesap))).scalars().first()
    if o is None:
        raise _hata(404, "bulunamadi")
    if o.dosya_id:
        await _dosya(db, ctx, o.dosya_id)  # gizli dosyanın olayı da yetkisize "yok"
    return o


async def _olay_listesi(db: AsyncSession, ctx: Ctx, bas=None, bit=None, sorumlu: Optional[str] = None,
                        dosya_id: Optional[int] = None, tamamlanan: bool = True):
    gorunur = await k.gorunur_dosya_idleri(db, ctx.hesap, ctx.kisi, ctx.sahip)
    sorgu = select(HukukOlaylari).where(HukukOlaylari.hesap_email == ctx.hesap,
                                        or_(HukukOlaylari.dosya_id.is_(None), HukukOlaylari.dosya_id.in_(gorunur or [-1])))
    if bas:
        sorgu = sorgu.where(HukukOlaylari.tarih >= bas)
    if bit:
        sorgu = sorgu.where(HukukOlaylari.tarih <= bit)
    if dosya_id:
        sorgu = sorgu.where(HukukOlaylari.dosya_id == dosya_id)
    if not tamamlanan:
        sorgu = sorgu.where(HukukOlaylari.tamamlandi_at.is_(None))
    olaylar = list((await db.execute(sorgu.order_by(HukukOlaylari.tarih, HukukOlaylari.saat).limit(3000))).scalars().all())
    dosyalar = {d.id: d for d in (await db.execute(select(HukukDosyalari).where(
        HukukDosyalari.id.in_({o.dosya_id for o in olaylar if o.dosya_id} or {-1})))).scalars().all()}
    if sorumlu:
        e = sorumlu.strip().lower()
        olaylar = [o for o in olaylar if (o.sorumlu_email or (dosyalar[o.dosya_id].sorumlu_email if o.dosya_id in dosyalar else None)
                                          or ctx.hesap) == e]
    return olaylar, dosyalar


@musteri_router.get("/olaylar")
async def olaylar(request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                  sorumlu: Optional[str] = Query(None, max_length=254), dosya_id: Optional[int] = Query(None),
                  tamamlanan: bool = Query(True), db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    try:
        b = s.tarih_duzelt(bas, "bas")
        e = s.tarih_duzelt(bit, "bit")
    except s.TemelHata as h:
        raise _e(h)
    if b and e and (e - b).days > 400:
        raise _hata(400, "aralik_disi", alan="bit", en_cok=400)
    liste, dosyalar_ = await _olay_listesi(db, ctx, b, e, sorumlu, dosya_id, tamamlanan)
    bugun = s.yerel_bugun()
    return {"items": [_olay_soz(o, dosyalar_.get(o.dosya_id), bugun) for o in liste], "bugun": bugun.isoformat()}


@musteri_router.post("/olaylar")
async def olay_ekle(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    g = await _govde(request)
    o = HukukOlaylari(hesap_email=ctx.hesap, olusturan=ctx.kisi, created_at=s.simdi())
    try:
        await _olay_uygula(db, ctx, o, g, yeni=True)
    except s.TemelHata as h:
        raise _e(h)
    db.add(o)
    await db.commit()
    await db.refresh(o)
    d = await _dosya(db, ctx, o.dosya_id) if o.dosya_id else None
    return _olay_soz(o, d)


@musteri_router.put("/olaylar/{oid}")
async def olay_guncelle(oid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    o = await _olay(db, ctx, oid)
    onceki_tarih = o.tarih
    g = await _govde(request)
    try:
        await _olay_uygula(db, ctx, o, g, yeni=False)
    except s.TemelHata as h:
        await db.rollback()
        raise _e(h)
    if o.tarih != onceki_tarih:
        # Tarih değişti: hatırlatmalar yeni tarihe göre yeniden (bir kez) gönderilebilsin.
        for x in (await db.execute(select(HukukHatirlatmalari).where(HukukHatirlatmalari.olay_id == o.id))).scalars().all():
            await db.delete(x)
    await db.commit()
    await db.refresh(o)
    d = await _dosya(db, ctx, o.dosya_id) if o.dosya_id else None
    return _olay_soz(o, d)


@musteri_router.delete("/olaylar/{oid}")
async def olay_sil(oid: int, request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    o = await _olay(db, ctx, oid)
    for x in (await db.execute(select(HukukHatirlatmalari).where(HukukHatirlatmalari.olay_id == o.id))).scalars().all():
        await db.delete(x)
    await db.delete(o)
    await db.commit()
    return {"ok": True}


@musteri_router.get("/takvim.ics")
async def takvim_ics(request: Request, sorumlu: Optional[str] = Query(None, max_length=254), dil: str = Query("tr", max_length=5),
                     db: AsyncSession = Depends(get_db)):
    """Sorumlu avukat başına takvim (son 30 gün + gelecek 1 yıl). Gizli dosyalar yalnız yetkiliye."""
    ctx = _ctx(request)
    bugun = s.yerel_bugun()
    liste, dosyalar_ = await _olay_listesi(db, ctx, bugun - timedelta(days=30), bugun + timedelta(days=366), sorumlu)
    a = await k.ayarlar(db, ctx.hesap)
    ad = (a.buro_adi if a and a.buro_adi else "Hukuk") + (f" — {sorumlu.strip().lower()}" if sorumlu else "")
    metin_ = s.ics_uret(liste, dosyalar_, takvim_adi=ad, dil=dil)
    dosya_adi = "hukuk-takvim" + (f"-{sorumlu.strip().lower().split('@')[0]}" if sorumlu else "") + ".ics"
    return Response(metin_, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": icerik_konumu(dosya_adi), "Cache-Control": "no-store"})


# --- Mesajlar (panel) -------------------------------------------------------------------
@musteri_router.get("/mesajlar")
async def mesajlar(request: Request, muvekkil_id: Optional[int] = Query(None), db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    gorunur = await k.gorunur_dosya_idleri(db, ctx.hesap, ctx.kisi, ctx.sahip)
    sorgu = select(HukukMesajlari).where(HukukMesajlari.hesap_email == ctx.hesap,
                                         or_(HukukMesajlari.dosya_id.is_(None), HukukMesajlari.dosya_id.in_(gorunur or [-1])))
    if muvekkil_id:
        sorgu = sorgu.where(HukukMesajlari.muvekkil_id == muvekkil_id)
    kayitlar = (await db.execute(sorgu.order_by(HukukMesajlari.id.desc()).limit(500))).scalars().all()
    adlar = await _muvekkil_adlari(db, [m.muvekkil_id for m in kayitlar])
    return {"items": [{**_mesaj_soz(m), "muvekkil_ad": adlar.get(m.muvekkil_id)} for m in reversed(kayitlar)]}


@musteri_router.post("/mesajlar")
async def mesaj_yanitla(request: Request, db: AsyncSession = Depends(get_db)):
    """Büronun yanıtı: müvekkil portalında görünür (e-posta GİTMEZ; müvekkil bağlantıdan bakar)."""
    ctx = _ctx(request)
    _hiz(_yazma_hizi, ctx.kisi)
    g = await _govde(request)
    m = await _muvekkil(db, ctx, _id(g.get("muvekkil_id"), "muvekkil_id"))
    try:
        metin_ = s.metin(g.get("metin"), "metin", 4000, zorunlu=True, cok_satir=True)
    except s.TemelHata as h:
        raise _e(h)
    dosya_id = None
    if g.get("dosya_id"):
        d = await _dosya(db, ctx, _id(g.get("dosya_id"), "dosya_id"))
        if d.muvekkil_id != m.id:
            raise _hata(400, "gecersiz", alan="dosya_id")
        dosya_id = d.id
    x = HukukMesajlari(hesap_email=ctx.hesap, muvekkil_id=m.id, dosya_id=dosya_id, yon="buro", metin=metin_, yazan=ctx.kisi,
                       okundu_at=s.simdi(), created_at=s.simdi())
    db.add(x)
    await db.commit()
    await db.refresh(x)
    return _mesaj_soz(x)


@musteri_router.post("/mesajlar/okundu")
async def mesaj_okundu(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = _ctx(request)
    g = await _govde(request)
    m = await _muvekkil(db, ctx, _id(g.get("muvekkil_id"), "muvekkil_id"), silinmis=None)
    gorunur = await k.gorunur_dosya_idleri(db, ctx.hesap, ctx.kisi, ctx.sahip)
    sayi = 0
    for x in (await db.execute(select(HukukMesajlari).where(
            HukukMesajlari.muvekkil_id == m.id, HukukMesajlari.yon == "muvekkil", HukukMesajlari.okundu_at.is_(None),
            or_(HukukMesajlari.dosya_id.is_(None), HukukMesajlari.dosya_id.in_(gorunur or [-1]))))).scalars().all():
        x.okundu_at = s.simdi()
        sayi += 1
    await db.commit()
    return {"ok": True, "sayi": sayi}


# ---------------------------------------------------------------------------
# Yönetici: YALNIZ META VERİ
# ---------------------------------------------------------------------------
@yonetici_router.get("/ozet")
async def yonetim_ozet(db: AsyncSession = Depends(get_db)):
    """Hesap başına sayılar + depolama. Dosya içeriği, not, belge, müvekkil kişisel verisi DÖNMEZ."""
    hesaplar = await k.meta_ozeti(db)
    toplam = {a: sum(int(h[a]) for h in hesaplar) for a in k.META_ALANLARI if a not in ("hesap_email", "modul_acik")}
    return {"hesaplar": hesaplar, "toplam": toplam, "gizlilik": "yalniz_meta"}


@yonetici_router.get("/hesap/{eposta}")
async def yonetim_hesap(eposta: str, db: AsyncSession = Depends(get_db)):
    try:
        e = s.eposta_duzelt(eposta, "eposta")
    except s.TemelHata as h:
        raise _e(h)
    return (await k.meta_ozeti(db, [e]))[0]


# ---------------------------------------------------------------------------
# Girişsiz müvekkil portalı
# ---------------------------------------------------------------------------
def _ph(durum: int, kod: str, **ek: Any) -> HTTPException:
    """Portal hatası: hata yanıtı da dizine kapalı, Referer'sız, ara belleksiz."""
    return HTTPException(status_code=durum, detail={"kod": kod, **ek}, headers=GIZLI_BASLIKLAR)


def _pe(h: s.TemelHata) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay(), headers=GIZLI_BASLIKLAR)


async def _portal(db: AsyncSession, request: Request, jeton: str) -> HukukMuvekkilleri:
    """Biçim/imza/sürüm tutmazsa 404; iptal/silinmiş 410; büronun modülü kapalıysa 410."""
    from services.moduller import modul_acik_mi

    if not await izin_ver((_portal_hizi, ip_ozeti("hukuk-portal|" + istemci_ip(request)))):
        raise _ph(429, "cok_hizli")
    parca = s.jeton_parcala(jeton)
    if parca is None:
        raise _ph(404, "baglanti_gecersiz")
    m = (await db.execute(select(HukukMuvekkilleri).where(HukukMuvekkilleri.id == parca[0]))).scalars().first()
    if m is None or int(m.portal_surum or 0) != parca[1] or not s.jeton_gecerli_mi(jeton, m.id, parca[1]):
        raise _ph(404, "baglanti_gecersiz")
    if not m.portal_acik or m.silindi_at is not None:
        raise _ph(410, "baglanti_kapali")
    if not await modul_acik_mi(db, m.hesap_email, MODUL):
        raise _ph(410, "baglanti_kapali")
    return m


async def _portal_dosyalari(db: AsyncSession, m: HukukMuvekkilleri) -> List[HukukDosyalari]:
    return list((await db.execute(select(HukukDosyalari).where(
        HukukDosyalari.muvekkil_id == m.id, HukukDosyalari.hesap_email == m.hesap_email,
        HukukDosyalari.silindi_at.is_(None), HukukDosyalari.portal_acik.is_(True)).order_by(HukukDosyalari.id.desc()))).scalars().all())


async def _portal_dosyasi(db: AsyncSession, m: HukukMuvekkilleri, did: int, alan: str) -> HukukDosyalari:
    for d in await _portal_dosyalari(db, m):
        if d.id == did and s.portal_alanlari(d.portal_alanlari).get(alan):
            return d
    raise _ph(404, "bulunamadi")


@acik_router.get("/muvekkil/{jeton}")
async def portal(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Müvekkile YALNIZ işaretli alanlar: konu, durum, sonraki duruşma (tarih/saat), paylaşılan belgeler,
    masraf dökümü, büronun notu. Notlar, karşı taraf, esas no, mahkeme, zaman kaydı GÖSTERİLMEZ."""
    m = await _portal(db, request, jeton)
    m.portal_son_at = s.simdi()
    await db.commit()
    a = await k.ayarlar(db, m.hesap_email)
    bugun = s.yerel_bugun()
    sonuc_dosyalar = []
    for sira, d in enumerate(await _portal_dosyalari(db, m), 1):
        alan = s.portal_alanlari(d.portal_alanlari)
        oge: Dict[str, Any] = {"id": d.id, "sira": sira, "tur": d.tur}
        if alan["konu"]:
            oge["konu"] = d.konu or ""
        if alan["durum"]:
            oge["durum"] = d.durum
        if alan["durusma"]:
            o = (await db.execute(select(HukukOlaylari).where(
                HukukOlaylari.dosya_id == d.id, HukukOlaylari.tur == "durusma", HukukOlaylari.tamamlandi_at.is_(None),
                HukukOlaylari.tarih >= bugun).order_by(HukukOlaylari.tarih, HukukOlaylari.saat).limit(1))).scalars().first()
            oge["sonraki_durusma"] = {"tarih": s.gun_iso(o.tarih), "saat": o.saat or ""} if o else None
        if alan["belgeler"]:
            oge["belgeler"] = [{"id": e.id, "ad": e.ad, "boyut": int(e.boyut or 0), "tur": e.tur or "",
                                "created_at": s.iso(e.created_at), "adres": f"/api/v1/hukuk/muvekkil/{jeton}/dosya/{d.id}/ek/{e.id}"}
                               for e in (await db.execute(select(HukukEkleri).where(
                                   HukukEkleri.dosya_id == d.id, HukukEkleri.muvekkile_gorunur.is_(True),
                                   HukukEkleri.tip != "baglanti").order_by(HukukEkleri.id.desc()))).scalars().all()]
        if alan["masraf"]:
            kalemler = (await db.execute(select(HukukMasraflari).where(HukukMasraflari.dosya_id == d.id))).scalars().all()
            oge["masraf"] = {"kalem": len(kalemler), "toplamlar": _masraf_toplamlari(kalemler),
                             "pdf": f"/api/v1/hukuk/muvekkil/{jeton}/dosya/{d.id}/masraf.pdf"}
        if alan["not"] and d.muvekkil_notu:
            oge["not"] = d.muvekkil_notu
        sonuc_dosyalar.append(oge)
    mesajlar_ = (await db.execute(select(HukukMesajlari).where(HukukMesajlari.muvekkil_id == m.id)
                                  .order_by(HukukMesajlari.id.desc()).limit(50))).scalars().all()
    return JSONResponse({
        "buro_adi": (a.buro_adi if a else "") or "",
        "muvekkil": {"ad": m.ad},
        "dosyalar": sonuc_dosyalar,
        "mesajlar": [{"id": x.id, "yon": x.yon, "metin": x.metin, "dosya_id": x.dosya_id, "created_at": s.iso(x.created_at)}
                     for x in reversed(mesajlar_)],
        "bugun": bugun.isoformat(),
    }, headers=GIZLI_BASLIKLAR)


@acik_router.get("/muvekkil/{jeton}/dosya/{did}/ek/{eid}")
async def portal_ek(jeton: str, did: int, eid: int, request: Request, db: AsyncSession = Depends(get_db)):
    m = await _portal(db, request, jeton)
    d = await _portal_dosyasi(db, m, did, "belgeler")
    e = (await db.execute(select(HukukEkleri).where(HukukEkleri.id == eid, HukukEkleri.dosya_id == d.id,
                                                    HukukEkleri.muvekkile_gorunur.is_(True)))).scalars().first()
    if e is None or e.tip == "baglanti":
        raise _ph(404, "bulunamadi")
    return await _ek_yaniti(db, e, {"X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"})


@acik_router.get("/muvekkil/{jeton}/dosya/{did}/masraf.pdf")
async def portal_masraf_pdf(jeton: str, did: int, request: Request, dil: str = Query("tr", max_length=5),
                            db: AsyncSession = Depends(get_db)):
    m = await _portal(db, request, jeton)
    d = await _portal_dosyasi(db, m, did, "masraf")
    pdf = await _dokum_pdf(db, d, dil, masraf=True, zaman=False)
    return Response(pdf, media_type="application/pdf", headers={
        **GIZLI_BASLIKLAR, "Content-Disposition": icerik_konumu(s.pdf_dosya_adi("masraf", d))})


@acik_router.post("/muvekkil/{jeton}/mesaj")
async def portal_mesaj(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    m = await _portal(db, request, jeton)
    if not await izin_ver((_portal_mesaj_ip, ip_ozeti("hukuk-mesaj|" + istemci_ip(request)))):
        raise _ph(429, "cok_hizli")
    if not _portal_mesaj_muvekkil.izin_var_mi(f"muvekkil-{m.id}"):
        raise _ph(429, "cok_hizli")
    g = await _govde(request, 16384)
    try:
        metin_ = s.metin(g.get("metin"), "metin", 2000, zorunlu=True, cok_satir=True)
    except s.TemelHata as h:
        raise _pe(h)
    dosya_id = None
    if g.get("dosya_id"):
        did = _id(g.get("dosya_id"), "dosya_id")
        if did not in {d.id for d in await _portal_dosyalari(db, m)}:
            raise _ph(400, "gecersiz", alan="dosya_id")
        dosya_id = did
    x = HukukMesajlari(hesap_email=m.hesap_email, muvekkil_id=m.id, dosya_id=dosya_id, yon="muvekkil", metin=metin_,
                       yazan=None, created_at=s.simdi())
    db.add(x)
    await db.commit()
    await db.refresh(x)
    try:
        await k.portal_mesaji_bildir(db, m, x.id)
    except Exception:  # noqa: BLE001 - bildirim mesajı bozmasın
        logger.exception("Hukuk portal mesajı bildirimi gönderilemedi")
    return JSONResponse({"ok": True, "id": x.id, "created_at": s.iso(x.created_at)}, headers=GIZLI_BASLIKLAR)


router = (yonetici_router, musteri_router, acik_router)
