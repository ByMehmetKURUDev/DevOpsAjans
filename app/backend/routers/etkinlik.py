"""Faz 6E — Etkinlik ve bilet: kayıt, QR bilet, kapıda okutma.

Herkese açık (oturumsuz):
  GET  /api/v1/etkinlik/{slug}?kod=&davet=          etkinlik + bilet türleri + doluluk (gizli tür yalnız kodla;
                                                     davet jetonu bekleme listesi davetini doğrular)
  GET  /api/v1/etkinlik/{slug}/ozet                 paylaşım önizlemesi + schema.org Event JSON-LD (yalnız
                                                     "arama motorlarında görünsün" seçiliyken) — Pages Function
  POST /api/v1/etkinlik/{slug}/fiyat                fiyat önizlemesi (indirim kodu)
  POST /api/v1/etkinlik/{slug}/kayit                kayıt: kilitli yer ayırma, hız sınırı + bal küpü (`web_adresi`);
                                                     ücretliyse (yalnız ajans) `/ode/<jeton>` ödeme bağlantısı
  POST /api/v1/etkinlik/{slug}/bekleme              bekleme listesi (yalnız dolu tür/etkinlikte)
  GET  /api/v1/etkinlik/bilet/{jeton}               bilet sayfası (imzalı; QR, takvim, online bağlantı yalnız burada)
  GET  /api/v1/etkinlik/bilet/{jeton}/qr/{kod}.svg  bilet QR'ı (içerik: yalnız kod + imza)
  GET  /api/v1/etkinlik/bilet/{jeton}/bilet.pdf     QR'lı bilet PDF'i
  GET  /api/v1/etkinlik/bilet/{jeton}/takvim.ics    takvim dosyası
  POST /api/v1/etkinlik/bilet/{jeton}/iptal         katılımcı iptali (başlangıçtan `iptal_sinir_saat` öncesine kadar)
  GET  /api/v1/etkinlik/giris/{jeton}               görevli (kapı) bağlantısı: yalnız okutma ekranı bilgisi
  POST /api/v1/etkinlik/giris/{jeton}/okut          okut (idempotent; çevrimdışı kuyruk aynı uca gelir)
  GET  /api/v1/etkinlik/giris/{jeton}/sayac         canlı sayaç
  GET  /api/v1/etkinlik/gorsel/{anahtar}            kapak görseli (WebP, değişmez)
  GET  /api/v1/etkinlikler/{slug}                   hesabın herkese açık etkinlik listesi (isteğe bağlı)

Yönetici (`/api/v1/etkinlik/yonetim`) — ajansın kendi etkinlikleri + bütün müşterilerinki.
Müşteri (`/api/v1/etkinliklerim`; modül `etkinlik_bilet` açık; ekip izni `etkinlik` = yönetim,
`etkinlik_giris` = YALNIZ okutma: `/giris-listesi`, `/{eid}/okut`, `/{eid}/sayac`):
  GET /meta · GET|POST "" · GET|PUT|DELETE /{eid} · POST|DELETE /{eid}/kapak · GET /{eid}/qr
  GET|POST /{eid}/bilet-turleri · PUT|DELETE /{eid}/bilet-turleri/{tid}
  GET|POST /{eid}/indirimler · PUT|DELETE /{eid}/indirimler/{iid}
  GET /{eid}/katilimcilar(.csv) · POST /{eid}/katilimcilar (elle ekle)
  POST /{eid}/siparisler/{sid}/iptal · POST /{eid}/siparisler/{sid}/odendi (havale/kapıda — yalnız ajans)
  POST /{eid}/biletler/{bid}/iptal · POST /{eid}/biletler/{bid}/iade · POST|DELETE /{eid}/biletler/{bid}/giris
  GET /{eid}/bekleme · POST /{eid}/bekleme/{wid}/davet · DELETE /{eid}/bekleme/{wid}
  GET /{eid}/istatistik · GET /{eid}/satis · POST /{eid}/duyuru · POST /{eid}/tesekkur
  GET|POST /{eid}/gorevli (süreli imzalı görevli bağlantısı; `yenile` eskilerin hepsini geçersiz kılar)
  GET|POST /{eid}/pazarlama (izin verenleri e-posta pazarlama listesine aktar)
  GET|PUT /liste-ayari (hesabın herkese açık etkinlik listesi)

Kurallar: müşteri yalnız etkin hesabın etkinliklerini görür; modül kapalıysa 403 `modul_kapali`;
sahibinin modülü kapanan etkinlik herkese 410. Ödeme ajansın hesabına gittiği için ücretli bilet
YALNIZ ajans etkinliğinde; müşteri etkinliğinde 409 `ucretli_bilet_yalniz_ajans`.
"""

import csv
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from models.etkinlik import (
    EtkinlikBekleme,
    EtkinlikBiletleri,
    EtkinlikBiletTurleri,
    EtkinlikGorselleri,
    EtkinlikIndirimKodlari,
    EtkinlikListeleri,
    Etkinlikler,
    EtkinlikSiparisleri,
)
from services import dinamik_qr as qr
from services import etkinlik as s
from services import etkinlik_kayit as k
from services.dosya_deposu import icerik_konumu
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

MODUL = s.MODUL
IZIN = s.IZIN
IZIN_GIRIS = s.IZIN_GIRIS
VARSAYILAN_AYLIK_SINIR = 5
VARSAYILAN_KAPASITE_SINIRI = 500
AJANS_KAPSAMI = "@ajans"

acik_router = APIRouter(prefix="/api/v1/etkinlik", tags=["etkinlik"])
bilet_router = APIRouter(prefix="/api/v1/etkinlik/bilet", tags=["etkinlik"])
giris_router = APIRouter(prefix="/api/v1/etkinlik/giris", tags=["etkinlik"])
gorsel_router = APIRouter(prefix="/api/v1/etkinlik/gorsel", tags=["etkinlik"])
liste_router = APIRouter(prefix="/api/v1/etkinlikler", tags=["etkinlik"])
yonetici_router = APIRouter(prefix="/api/v1/etkinlik/yonetim", tags=["etkinlik"], dependencies=[Depends(yonetici_gerekli)])
musteri_router = APIRouter(
    prefix="/api/v1/etkinliklerim",
    tags=["etkinlik"],
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(IZIN, IZIN_GIRIS))],
)

#: Panel (kişi başı): dakikada 60 yazma, 20 görsel/QR/CSV, saatte 5 duyuru (etkinlik başı).
_yazma_hizi = HizSiniri(60, 60.0)
_gorsel_hizi = HizSiniri(20, 60.0)
_duyuru_hizi = HizSiniri(5, 3600.0)
#: Okutma (kişi ya da görevli jetonu başı): dakikada 240 (kuyruk boşaltma dahil).
_okut_hizi = HizSiniri(240, 60.0)
#: Ziyaretçi (IP özeti + etkinlik): 10 dakikada 6 kayıt / 5 bekleme; dakikada 60 fiyat.
#: Faz 7H: kayıt, bekleme listesi ve bilet bağlantısı sayaçları veritabanında.
_kayit_hizi = KaliciHizSiniri("etkinlik-kayit", 6, 600.0)
_bekleme_hizi = KaliciHizSiniri("etkinlik-bekleme", 5, 600.0)
_fiyat_hizi = HizSiniri(60, 60.0)
#: Etkinlik başına dakikada 60 kayıt (çok IP'den gelen saldırıya karşı).
_etkinlik_kayit_hizi = KaliciHizSiniri("etkinlik-genel", 60, 60.0)
#: Bilet sayfası (IP özeti): dakikada 60.
_bilet_hizi = KaliciHizSiniri("etkinlik-bilet", 60, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _gorsel_hizi, _duyuru_hizi, _okut_hizi, _kayit_hizi, _bekleme_hizi, _fiyat_hizi,
              _etkinlik_kayit_hizi, _bilet_hizi):
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


def _musteri_giris_kapsami(request: Request) -> Kapsam:
    baglam = izin_iste(request, IZIN, IZIN_GIRIS)
    return Kapsam(False, baglam.hesap_email, baglam.kisi_email)


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _e_hatasi(h: s.TemelHata) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _hiz(sinir: HizSiniri, anahtar: str) -> None:
    if not sinir.izin_var_mi(anahtar or "anonim"):
        raise _hata(429, "cok_hizli")


async def _kalici_hiz(*denemeler) -> None:
    """Faz 7H: herkese açık uçların veritabanı destekli sayacı ((sınırlayıcı, anahtar) çiftleri)."""
    if not await izin_ver(*denemeler):
        raise _hata(429, "cok_hizli")


async def _modul_ayari(db: AsyncSession, hesap: Optional[str], ad: str, varsayilan: int) -> Optional[int]:
    if not hesap:
        return None
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, hesap, MODUL, ad)
    return int(deger) if isinstance(deger, int) and not isinstance(deger, bool) else varsayilan


def _gorevli_bitisi(e: Etkinlikler) -> datetime:
    return s.utc(e.bitis) + timedelta(hours=s.GOREVLI_EK_SAAT)


def _etkinlik_sozlugu(e: Etkinlikler, **ek: Any) -> Dict[str, Any]:
    return {
        "id": e.id,
        "hesap_email": e.hesap_email,
        "ajans": e.hesap_email is None,
        "slug": e.slug,
        "adres_url": s.sayfa_adresi(e.slug),
        "baslik": e.baslik,
        "ozet": e.ozet or "",
        "aciklama": e.aciklama or "",
        "kapak": s.kapak_adresi(e.kapak),
        "renk": e.renk,
        "bicim": e.bicim,
        "mekan_adi": e.mekan_adi or "",
        "adres": e.adres or "",
        "harita_url": e.harita_url or "",
        "online_baglanti": e.online_baglanti or "",
        "saat_dilimi": e.saat_dilimi,
        "baslangic": s.iso(e.baslangic),
        "bitis": s.iso(e.bitis),
        "oturumlar": s.json_yukle(e.oturumlar, []) or [],
        "kapasite": e.kapasite,
        "kayit_acilis": s.iso(e.kayit_acilis),
        "kayit_kapanis": s.iso(e.kayit_kapanis),
        "durum": e.durum,
        "dil": e.dil,
        "organizator_ad": e.organizator_ad or "",
        "organizator_eposta": e.organizator_eposta or "",
        "organizator_url": e.organizator_url or "",
        "iade_politikasi": e.iade_politikasi or "",
        "kvkk_metni": e.kvkk_metni or "",
        "odeme_notu": e.odeme_notu or "",
        "arama_motoru": bool(e.arama_motoru),
        "listede_goster": bool(e.listede_goster),
        "katilimci_adlari": bool(e.katilimci_adlari),
        "telefon": e.telefon,
        "sorular": s.json_yukle(e.sorular, []) or [],
        "bekleme_listesi": bool(e.bekleme_listesi),
        "iptal_sinir_saat": int(e.iptal_sinir_saat or 0),
        "saklama_gun": int(e.saklama_gun or s.VARSAYILAN_SAKLAMA_GUN),
        "tesekkur_aktif": bool(e.tesekkur_aktif),
        "tesekkur_metni": e.tesekkur_metni or "",
        "anket_url": e.anket_url or "",
        "tesekkur_at": s.iso(e.tesekkur_at),
        "created_at": s.iso(e.created_at),
        "updated_at": s.iso(e.updated_at),
        **ek,
    }


def _tur_sozlugu(t: EtkinlikBiletTurleri, d: Optional[k.Doluluk] = None, e: Optional[Etkinlikler] = None) -> Dict[str, Any]:
    return {
        "id": t.id, "etkinlik_id": t.etkinlik_id, "ad": t.ad, "aciklama": t.aciklama or "", "fiyat": int(t.fiyat or 0),
        "para_birimi": t.para_birimi, "kontenjan": t.kontenjan, "satis_bas": s.iso(t.satis_bas), "satis_bit": s.iso(t.satis_bit),
        "kisi_basi_en_cok": int(t.kisi_basi_en_cok or 1), "gizli": bool(t.gizli), "gizli_kod": t.gizli_kod or "",
        "aktif": bool(t.aktif), "sira": int(t.sira or 0),
        "satilan": d.tur_aktif.get(t.id, 0) if d is not None else None,
        "kalan": d.musait(e, t) if d is not None and e is not None else None,
    }


def _indirim_sozlugu(i: EtkinlikIndirimKodlari) -> Dict[str, Any]:
    return {
        "id": i.id, "kod": i.kod, "tur": i.tur, "deger": int(i.deger or 0), "kullanim_siniri": i.kullanim_siniri,
        "kullanilan": int(i.kullanilan or 0), "bilet_turleri": s.json_yukle(i.bilet_turleri, []) or [],
        "son_tarih": s.iso(i.son_tarih), "aktif": bool(i.aktif), "created_at": s.iso(i.created_at),
    }


# ---------------------------------------------------------------------------
# Etkinlik
# ---------------------------------------------------------------------------
async def _etkinlik(db: AsyncSession, eid: int, kapsam: Kapsam) -> Etkinlikler:
    sorgu = select(Etkinlikler).where(Etkinlikler.id == eid)
    if not kapsam.yonetici:
        sorgu = sorgu.where(Etkinlikler.hesap_email == kapsam.hesap)
    e = (await db.execute(sorgu)).scalars().first()
    if e is None:
        raise _hata(404, "bulunamadi")
    return e


async def _slug_bos_mu(db: AsyncSession, slug: str, haric: Optional[int] = None) -> bool:
    sorgu = select(Etkinlikler.id).where(Etkinlikler.slug == slug)
    if haric is not None:
        sorgu = sorgu.where(Etkinlikler.id != haric)
    return (await db.execute(sorgu.limit(1))).first() is None


async def _bos_slug(db: AsyncSession, oneri: str) -> str:
    aday = oneri
    for i in range(2, 60):
        if await _slug_bos_mu(db, aday):
            return aday
        aday = f"{oneri[:44]}-{i}"
    import uuid

    return f"{oneri[:40]}-{uuid.uuid4().hex[:6]}"


async def _etkinlik_uygula(db: AsyncSession, kapsam: Kapsam, e: Etkinlikler, g: Dict[str, Any], yeni: bool) -> Dict[str, Any]:
    """Alanları doğrular ve uygular. Döner: yan etkiler ({"iptal_edildi": bool, "kapasite_artti": bool})."""
    yan: Dict[str, Any] = {"iptal_edildi": False, "kapasite_artti": False}
    if "baslik" in g or yeni:
        e.baslik = s.metin(g.get("baslik"), "baslik", 160, zorunlu=True)
    if "slug" in g and g.get("slug"):
        slug = s.slug_duzelt(g.get("slug"))
        if slug != e.slug and not await _slug_bos_mu(db, slug, None if yeni else e.id):
            raise s.EtkinlikHatasi("slug_dolu", "slug", durum=409)
        e.slug = slug
    elif yeni:
        e.slug = await _bos_slug(db, s.slug_oner(e.baslik))
    for alan, sinir, cok in (("ozet", 300, False), ("aciklama", 20000, True), ("mekan_adi", 160, False),
                             ("adres", 500, True), ("organizator_ad", 160, False), ("iade_politikasi", 3000, True),
                             ("kvkk_metni", 3000, True), ("odeme_notu", 1000, True), ("tesekkur_metni", 3000, True)):
        if alan in g:
            setattr(e, alan, s.metin(g.get(alan), alan, sinir, cok_satir=cok) or None)
    for alan in ("harita_url", "online_baglanti", "organizator_url", "anket_url"):
        if alan in g:
            setattr(e, alan, s.https_duzelt(g.get(alan), alan))
    if "organizator_eposta" in g:
        e.organizator_eposta = s.eposta_duzelt(g.get("organizator_eposta"), "organizator_eposta", zorunlu=False) or None
    if "renk" in g:
        e.renk = s.renk_duzelt(g.get("renk"))
    if "bicim" in g or yeni:
        bicim = g.get("bicim", e.bicim or "yuz_yuze")
        if bicim not in s.BICIMLER:
            raise s.EtkinlikHatasi("secim_gecersiz", "bicim")
        e.bicim = bicim
    if "saat_dilimi" in g or yeni:
        e.saat_dilimi = s.saat_dilimi_duzelt(g.get("saat_dilimi") or e.saat_dilimi or s.VARSAYILAN_SAAT_DILIMI)
    if "dil" in g or yeni:
        e.dil = s.dil_duzelt(g.get("dil") or e.dil or "tr")
    if "baslangic" in g or yeni:
        e.baslangic = s.zaman_coz(g.get("baslangic"), "baslangic")
    if "bitis" in g or yeni:
        e.bitis = s.zaman_coz(g.get("bitis"), "bitis")
    bas, bit = s.utc(e.baslangic), s.utc(e.bitis)
    if bit <= bas:
        raise s.EtkinlikHatasi("bitis_once", "bitis")
    if bit - bas > timedelta(days=62):
        raise s.EtkinlikHatasi("sure_uzun", "bitis")
    if "oturumlar" in g:
        e.oturumlar = s.json_yaz(s.oturumlar_duzelt(g.get("oturumlar"), bas, bit)) if g.get("oturumlar") else None
    elif e.oturumlar:
        s.oturumlar_duzelt(s.json_yukle(e.oturumlar, []), bas, bit)
    if "kayit_acilis" in g:
        e.kayit_acilis = s.zaman_coz(g.get("kayit_acilis"), "kayit_acilis", bos_olabilir=True)
    if "kayit_kapanis" in g:
        e.kayit_kapanis = s.zaman_coz(g.get("kayit_kapanis"), "kayit_kapanis", bos_olabilir=True)
    if e.kayit_kapanis and s.utc(e.kayit_kapanis) > bit:
        raise s.EtkinlikHatasi("kapanis_sonra", "kayit_kapanis")
    if e.kayit_acilis and s.utc(e.kayit_acilis) >= (s.utc(e.kayit_kapanis) if e.kayit_kapanis else bas):
        raise s.EtkinlikHatasi("acilis_sonra", "kayit_acilis")
    tavan = await _modul_ayari(db, e.hesap_email, "kapasite_siniri", VARSAYILAN_KAPASITE_SINIRI)
    if "kapasite" in g or yeni:
        eski = e.kapasite
        ham = g.get("kapasite")
        e.kapasite = s.tam_sayi(ham, "kapasite", 1, s.KAPASITE_EN_COK, bos_olabilir=True)
        if e.kapasite is None and tavan is not None:
            e.kapasite = tavan
        yan["kapasite_artti"] = eski is not None and (e.kapasite is None or e.kapasite > eski)
    if tavan is not None and e.kapasite is not None and e.kapasite > tavan:
        raise s.EtkinlikHatasi("kapasite_siniri", "kapasite", durum=409, sinir=tavan)
    for alan in ("arama_motoru", "listede_goster", "katilimci_adlari", "bekleme_listesi", "tesekkur_aktif"):
        if alan in g:
            setattr(e, alan, s.bool_duzelt(g.get(alan), alan))
    if "telefon" in g:
        if g.get("telefon") not in s.TELEFON_SECENEKLERI:
            raise s.EtkinlikHatasi("secim_gecersiz", "telefon")
        e.telefon = g["telefon"]
    if "sorular" in g:
        e.sorular = s.json_yaz(s.sorular_duzelt(g.get("sorular"))) if g.get("sorular") else None
    if "iptal_sinir_saat" in g:
        e.iptal_sinir_saat = s.tam_sayi(g.get("iptal_sinir_saat"), "iptal_sinir_saat", 0, s.IPTAL_SINIR_EN_COK)
    if "saklama_gun" in g:
        e.saklama_gun = s.tam_sayi(g.get("saklama_gun"), "saklama_gun", s.SAKLAMA_EN_AZ, s.SAKLAMA_EN_COK)
    if "durum" in g:
        durum = g.get("durum")
        if durum not in s.DURUMLAR:
            raise s.EtkinlikHatasi("secim_gecersiz", "durum")
        if durum == "yayinda" and e.durum != "yayinda":
            if yeni or not (await db.execute(select(EtkinlikBiletTurleri.id).where(
                    EtkinlikBiletTurleri.etkinlik_id == e.id, EtkinlikBiletTurleri.aktif.is_(True)).limit(1))).first():
                raise s.EtkinlikHatasi("bilet_turu_yok", "durum", durum=409)
            if e.bicim in ("online", "karma") and not e.online_baglanti:
                raise s.EtkinlikHatasi("online_baglanti_gerekli", "online_baglanti")
        if e.durum == "iptal" and durum != "iptal":
            raise s.EtkinlikHatasi("iptal_geri_alinamaz", "durum", durum=409)
        yan["iptal_edildi"] = durum == "iptal" and e.durum != "iptal"
        e.durum = durum
    return yan


async def _olustur(db: AsyncSession, kapsam: Kapsam, g: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if kapsam.yonetici:
            ham = str(g.get("hesap_email") or "").strip()
            hesap = s.eposta_duzelt(ham, "hesap_email") if ham else None
        else:
            hesap = kapsam.hesap
        if hesap and not kapsam.yonetici:
            sinir = await _modul_ayari(db, hesap, "aylik_etkinlik_siniri", VARSAYILAN_AYLIK_SINIR)
            an = s.simdi()
            ay_basi = an.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            sayi = int((await db.execute(select(func.count(Etkinlikler.id)).where(
                Etkinlikler.hesap_email == hesap, Etkinlikler.created_at >= ay_basi))).scalar() or 0)
            if sinir is not None and sayi >= sinir:
                raise s.EtkinlikHatasi("aylik_etkinlik_siniri", durum=409, sinir=sinir)
        e = Etkinlikler(hesap_email=hesap, olusturan_email=kapsam.kisi, durum="taslak", renk="#7c3aed", telefon="istege_bagli",
                        bekleme_listesi=True, listede_goster=True, iptal_sinir_saat=24, saklama_gun=s.VARSAYILAN_SAKLAMA_GUN,
                        gorevli_surumu=1, kilit=0, created_at=s.simdi())
        g = dict(g)
        g.pop("durum", None)  # yeni etkinlik taslak; bilet türü eklenince yayına alınır
        await _etkinlik_uygula(db, kapsam, e, g, yeni=True)
        if not e.organizator_ad:
            e.organizator_ad = "By Mehmet KURU Dev" if hesap is None else None
    except s.TemelHata as h:
        raise _e_hatasi(h)
    db.add(e)
    try:
        await db.flush()
        # Kolaylık: her yeni etkinlik ücretsiz bir "Standart" bilet türüyle başlar.
        if g.get("varsayilan_tur", True) is not False:
            db.add(EtkinlikBiletTurleri(etkinlik_id=e.id, ad="Standart", fiyat=0, para_birimi="TRY", kisi_basi_en_cok=5,
                                        gizli=False, aktif=True, sira=0, created_at=s.simdi()))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "slug_dolu", alan="slug")
    await db.refresh(e)
    return _etkinlik_sozlugu(e)


async def _liste(db: AsyncSession, kapsam: Kapsam, hesap: Optional[str]) -> Dict[str, Any]:
    sorgu = select(Etkinlikler)
    if not kapsam.yonetici:
        sorgu = sorgu.where(Etkinlikler.hesap_email == kapsam.hesap)
    elif hesap == "ajans":
        sorgu = sorgu.where(Etkinlikler.hesap_email.is_(None))
    elif hesap:
        sorgu = sorgu.where(Etkinlikler.hesap_email == hesap.strip().lower())
    kayitlar = (await db.execute(sorgu.order_by(Etkinlikler.baslangic.desc(), Etkinlikler.id.desc()).limit(500))).scalars().all()
    idler = [e.id for e in kayitlar]
    sayilar: Dict[int, Dict[str, int]] = {}
    if idler:
        for eid, n, g_ in (await db.execute(
            select(EtkinlikBiletleri.etkinlik_id, func.count(EtkinlikBiletleri.id), func.count(EtkinlikBiletleri.giris_at))
            .where(EtkinlikBiletleri.etkinlik_id.in_(idler), EtkinlikBiletleri.durum == "gecerli")
            .group_by(EtkinlikBiletleri.etkinlik_id)
        )).all():
            sayilar[eid] = {"bilet": int(n), "giren": int(g_)}
    return {"items": [_etkinlik_sozlugu(e, bilet_sayisi=sayilar.get(e.id, {}).get("bilet", 0),
                                        giren=sayilar.get(e.id, {}).get("giren", 0)) for e in kayitlar],
            "toplam": len(kayitlar)}


async def _meta(db: AsyncSession, kapsam: Kapsam) -> Dict[str, Any]:
    aylik = kapasite = None
    bu_ay = None
    if not kapsam.yonetici:
        aylik = await _modul_ayari(db, kapsam.hesap, "aylik_etkinlik_siniri", VARSAYILAN_AYLIK_SINIR)
        kapasite = await _modul_ayari(db, kapsam.hesap, "kapasite_siniri", VARSAYILAN_KAPASITE_SINIRI)
        an = s.simdi()
        ay_basi = an.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        bu_ay = int((await db.execute(select(func.count(Etkinlikler.id)).where(
            Etkinlikler.hesap_email == kapsam.hesap, Etkinlikler.created_at >= ay_basi))).scalar() or 0)
    return {
        "yonetici": kapsam.yonetici,
        "ucretli_bilet": kapsam.yonetici,
        # Ücretli bilet için ödeme sağlayıcısı anahtarları (Render ortamı); yoksa fiyat alanı kapalı + açıklama.
        "odeme_hazir": bool(kapsam.yonetici and s.odeme_hazir_mi()),
        "aylik_etkinlik_siniri": aylik,
        "bu_ay": bu_ay,
        "kapasite_siniri": kapasite,
        "bicimler": list(s.BICIMLER),
        "durumlar": list(s.DURUMLAR),
        "para_birimleri": list(s.PARA_BIRIMLERI),
        "telefon_secenekleri": list(s.TELEFON_SECENEKLERI),
        "soru_turleri": ["metin", "uzun", "secim", "onay"],
        "en_cok_soru": s.EN_COK_SORU,
        "en_cok_adet": s.EN_COK_ADET,
        "diller": list(s.DILLER),
        "adres_tabani": f"{s.site_adresi()}/etkinlik/",
        "widget_adresi": f"{s.site_adresi()}/etkinlik-widget.js",
        "varsayilan_saat_dilimi": s.VARSAYILAN_SAAT_DILIMI,
        "odeme_suresi_dk": s.ODEME_SURESI_DK,
    }


# ---------------------------------------------------------------------------
# Bilet türleri ve indirimler
# ---------------------------------------------------------------------------
async def _tur(db: AsyncSession, e: Etkinlikler, tid: int) -> EtkinlikBiletTurleri:
    t = (await db.execute(select(EtkinlikBiletTurleri).where(EtkinlikBiletTurleri.id == tid,
                                                             EtkinlikBiletTurleri.etkinlik_id == e.id))).scalars().first()
    if t is None:
        raise _hata(404, "bulunamadi")
    return t


async def _tur_uygula(db: AsyncSession, e: Etkinlikler, t: EtkinlikBiletTurleri, g: Dict[str, Any], yeni: bool) -> None:
    if "ad" in g or yeni:
        t.ad = s.metin(g.get("ad"), "ad", 120, zorunlu=True)
    if "aciklama" in g:
        t.aciklama = s.metin(g.get("aciklama"), "aciklama", 500, cok_satir=True) or None
    if "fiyat" in g or yeni:
        eski_fiyat = int(t.fiyat or 0)
        t.fiyat = s.fiyat_duzelt(g.get("fiyat", 0))
        if int(t.fiyat or 0) > 0 and not eski_fiyat and not e.hesap_email and not s.odeme_hazir_mi():
            # Ödeme sağlayıcısı yokken ücretli tür açılmaz (ziyaretçi boş ödeme sayfasına düşmesin).
            raise s.EtkinlikHatasi("odeme_saglayicisi_yok", "fiyat", durum=409)
    if "para_birimi" in g or yeni:
        t.para_birimi = s.para_birimi_duzelt(g.get("para_birimi") or t.para_birimi or "TRY")
    if int(t.fiyat or 0) > 0:
        if e.hesap_email:
            # Ödeme ajansın hesabına gidiyor: müşterinin etkinliği için para toplanmaz.
            raise s.EtkinlikHatasi("ucretli_bilet_yalniz_ajans", "fiyat", durum=409)
        diger = (await db.execute(select(EtkinlikBiletTurleri.para_birimi).where(
            EtkinlikBiletTurleri.etkinlik_id == e.id, EtkinlikBiletTurleri.fiyat > 0,
            EtkinlikBiletTurleri.id != (t.id or -1)))).scalars().all()
        if any(p != t.para_birimi for p in diger):
            raise s.EtkinlikHatasi("para_birimi_farkli", "para_birimi", durum=409)
    if "kontenjan" in g:
        t.kontenjan = s.tam_sayi(g.get("kontenjan"), "kontenjan", 1, s.KAPASITE_EN_COK, bos_olabilir=True)
    for alan in ("satis_bas", "satis_bit"):
        if alan in g:
            setattr(t, alan, s.zaman_coz(g.get(alan), alan, bos_olabilir=True))
    if t.satis_bas and t.satis_bit and s.utc(t.satis_bit) <= s.utc(t.satis_bas):
        raise s.EtkinlikHatasi("satis_araligi", "satis_bit")
    if "kisi_basi_en_cok" in g:
        t.kisi_basi_en_cok = s.tam_sayi(g.get("kisi_basi_en_cok"), "kisi_basi_en_cok", 1, s.EN_COK_ADET)
    if "gizli" in g:
        t.gizli = s.bool_duzelt(g.get("gizli"), "gizli")
    if "gizli_kod" in g:
        t.gizli_kod = s.indirim_kodu_duzelt(g.get("gizli_kod"), "gizli_kod") if g.get("gizli_kod") else None
    if t.gizli and not t.gizli_kod:
        raise s.EtkinlikHatasi("gizli_kod_gerekli", "gizli_kod")
    if "aktif" in g:
        t.aktif = s.bool_duzelt(g.get("aktif"), "aktif")
    if "sira" in g:
        t.sira = s.tam_sayi(g.get("sira"), "sira", 0, 1000)


async def _indirim(db: AsyncSession, e: Etkinlikler, iid: int) -> EtkinlikIndirimKodlari:
    i = (await db.execute(select(EtkinlikIndirimKodlari).where(EtkinlikIndirimKodlari.id == iid,
                                                               EtkinlikIndirimKodlari.etkinlik_id == e.id))).scalars().first()
    if i is None:
        raise _hata(404, "bulunamadi")
    return i


async def _indirim_uygula(db: AsyncSession, e: Etkinlikler, i: EtkinlikIndirimKodlari, g: Dict[str, Any], yeni: bool) -> None:
    if "kod" in g or yeni:
        kod = s.indirim_kodu_duzelt(g.get("kod"))
        var = (await db.execute(select(EtkinlikIndirimKodlari.id).where(
            EtkinlikIndirimKodlari.etkinlik_id == e.id, EtkinlikIndirimKodlari.kod == kod,
            EtkinlikIndirimKodlari.id != (i.id or -1)).limit(1))).first()
        if var:
            raise s.EtkinlikHatasi("kod_var", "kod", durum=409)
        i.kod = kod
    if "tur" in g or yeni:
        if g.get("tur", i.tur or "yuzde") not in s.INDIRIM_TURLERI:
            raise s.EtkinlikHatasi("secim_gecersiz", "tur")
        i.tur = g.get("tur", i.tur or "yuzde")
    if "deger" in g or yeni:
        i.deger = int(s.tam_sayi(g.get("deger"), "deger", 1, 100 if i.tur == "yuzde" else s.FIYAT_EN_COK))
    elif i.tur == "yuzde" and int(i.deger or 0) > 100:
        raise s.EtkinlikHatasi("aralik_disi", "deger", en_az=1, en_cok=100)
    if "kullanim_siniri" in g:
        i.kullanim_siniri = s.tam_sayi(g.get("kullanim_siniri"), "kullanim_siniri", max(1, int(i.kullanilan or 0)),
                                       1_000_000, bos_olabilir=True)
    if "bilet_turleri" in g:
        ham = g.get("bilet_turleri") or []
        gecerli = {t.id for t in await k.tur_listesi(db, e.id)}
        if not isinstance(ham, list) or any(isinstance(x, bool) or x not in gecerli for x in ham):
            raise s.EtkinlikHatasi("tur_gecersiz", "bilet_turleri")
        i.bilet_turleri = s.json_yaz(sorted(set(ham))) if ham else None
    if "son_tarih" in g:
        i.son_tarih = s.zaman_coz(g.get("son_tarih"), "son_tarih", bos_olabilir=True)
    if "aktif" in g:
        i.aktif = s.bool_duzelt(g.get("aktif"), "aktif")


# ---------------------------------------------------------------------------
# Katılımcılar
# ---------------------------------------------------------------------------
async def _katilimci_satirlari(db: AsyncSession, e: Etkinlikler, durum: Optional[str], tur_id: Optional[int],
                               ara: Optional[str], giris: Optional[str], sinir: int, atla: int):
    sorgu = (select(EtkinlikBiletleri, EtkinlikSiparisleri)
             .join(EtkinlikSiparisleri, EtkinlikSiparisleri.id == EtkinlikBiletleri.siparis_id)
             .where(EtkinlikBiletleri.etkinlik_id == e.id))
    if durum and durum != "tum":
        sorgu = sorgu.where(EtkinlikBiletleri.durum == durum)
    if tur_id is not None:
        sorgu = sorgu.where(EtkinlikBiletleri.tur_id == tur_id)
    if giris == "evet":
        sorgu = sorgu.where(EtkinlikBiletleri.giris_at.isnot(None))
    elif giris == "hayir":
        sorgu = sorgu.where(EtkinlikBiletleri.giris_at.is_(None))
    if ara:
        q = f"%{ara.strip().lower()[:80]}%"
        sorgu = sorgu.where(or_(func.lower(EtkinlikSiparisleri.ad).like(q), func.lower(EtkinlikSiparisleri.eposta).like(q),
                                func.lower(EtkinlikBiletleri.katilimci_ad).like(q), func.lower(EtkinlikBiletleri.kod).like(q),
                                func.lower(EtkinlikSiparisleri.kod).like(q)))
    toplam = int((await db.execute(select(func.count()).select_from(sorgu.subquery()))).scalar() or 0)
    satirlar = (await db.execute(sorgu.order_by(EtkinlikBiletleri.id.desc()).offset(atla).limit(sinir))).all()
    return toplam, satirlar


def _katilimci_sozlugu(b: EtkinlikBiletleri, sp: EtkinlikSiparisleri, turler: Dict[int, EtkinlikBiletTurleri],
                       sorular: Dict[str, str]) -> Dict[str, Any]:
    t = turler.get(b.tur_id)
    yanitlar = s.json_yukle(sp.yanitlar, {}) or {}
    return {
        "id": b.id, "kod": b.kod, "tur_id": b.tur_id, "tur_adi": t.ad if t else "—", "katilimci_ad": b.katilimci_ad,
        "durum": b.durum, "giris_at": s.iso(b.giris_at), "iade": b.iade, "fiyat": int(b.fiyat or 0),
        "iptal_at": s.iso(b.iptal_at), "iptal_eden": b.iptal_eden,
        "siparis": {
            "id": sp.id, "kod": sp.kod, "ad": sp.ad, "eposta": sp.eposta, "telefon": sp.telefon, "durum": sp.durum,
            "kaynak": sp.kaynak, "toplam": int(sp.toplam or 0), "indirim": int(sp.indirim or 0), "para_birimi": sp.para_birimi,
            "odeme_son": s.iso(sp.odeme_son), "odendi_at": s.iso(sp.odendi_at), "pazarlama_izni": sp.pazarlama_izni_at is not None,
            "anonim": bool(sp.anonim), "created_at": s.iso(sp.created_at), "crm_aday_id": sp.crm_aday_id,
            "yanitlar": [{"id": kimlik, "soru": sorular.get(kimlik, kimlik), "yanit": deger} for kimlik, deger in yanitlar.items()],
        },
    }


CSV_BASLIKLARI = ("bilet_kodu", "bilet_turu", "katilimci", "siparis_kodu", "ad", "eposta", "telefon", "bilet_durumu",
                  "siparis_durumu", "giris", "fiyat", "para_birimi", "iade", "kayit_zamani", "pazarlama_izni")


async def _csv(db: AsyncSession, e: Etkinlikler) -> str:
    _, satirlar = await _katilimci_satirlari(db, e, "tum", None, None, None, 50000, 0)
    turler = {t.id: t for t in await k.tur_listesi(db, e.id)}
    sorular = [(q.get("id"), q.get("etiket")) for q in (s.json_yukle(e.sorular, []) or [])]
    cikti = io.StringIO()
    yazici = csv.writer(cikti, lineterminator="\r\n")
    yazici.writerow([*CSV_BASLIKLARI, *[etiket for _, etiket in sorular]])
    for b, sp in satirlar:
        yanit = s.json_yukle(sp.yanitlar, {}) or {}
        yazici.writerow([s.csv_hucre(x) for x in (
            b.kod, turler[b.tur_id].ad if b.tur_id in turler else "", b.katilimci_ad or "", sp.kod, sp.ad or "", sp.eposta or "",
            sp.telefon or "", b.durum, sp.durum, s.iso(b.giris_at) or "", f"{int(b.fiyat or 0) / 100:.2f}", sp.para_birimi,
            b.iade, s.iso(sp.created_at) or "", "evet" if sp.pazarlama_izni_at else "hayir",
            *[("✓" if yanit.get(kimlik) is True else str(yanit.get(kimlik) or "")) for kimlik, _ in sorular],
        )])
    return "﻿" + cikti.getvalue()


async def _siparis(db: AsyncSession, e: Etkinlikler, sid: int) -> EtkinlikSiparisleri:
    sp = (await db.execute(select(EtkinlikSiparisleri).where(EtkinlikSiparisleri.id == sid,
                                                             EtkinlikSiparisleri.etkinlik_id == e.id))).scalars().first()
    if sp is None:
        raise _hata(404, "bulunamadi")
    return sp


async def _bilet(db: AsyncSession, e: Etkinlikler, bid: int) -> EtkinlikBiletleri:
    b = (await db.execute(select(EtkinlikBiletleri).where(EtkinlikBiletleri.id == bid,
                                                          EtkinlikBiletleri.etkinlik_id == e.id))).scalars().first()
    if b is None:
        raise _hata(404, "bulunamadi")
    return b


async def _davet_arka_plan(etkinlik_id: int) -> None:
    """İptal sonrası: bekleme listesinden sıradakileri davet et (yanıttan sonra)."""
    try:
        from core.database import db_manager

        if not db_manager.async_session_maker:
            return
        async with db_manager.async_session_maker() as db:
            e = (await db.execute(select(Etkinlikler).where(Etkinlikler.id == etkinlik_id))).scalars().first()
            if e is None:
                return
            idler = await k.bekleme_davet_et(db, e)
        await k.davetleri_gonder(idler)
    except Exception:  # noqa: BLE001
        logger.exception("Bekleme davetleri yapılamadı (%s)", etkinlik_id)


# ---------------------------------------------------------------------------
# İstatistik ve satış
# ---------------------------------------------------------------------------
async def _istatistik(db: AsyncSession, e: Etkinlikler) -> Dict[str, Any]:
    sayac = await k.sayac(db, e)
    bekleme = dict((await db.execute(select(EtkinlikBekleme.durum, func.count(EtkinlikBekleme.id)).where(
        EtkinlikBekleme.etkinlik_id == e.id).group_by(EtkinlikBekleme.durum))).all())
    bekleyen_odeme = int((await db.execute(select(func.count(EtkinlikBiletleri.id)).where(
        EtkinlikBiletleri.etkinlik_id == e.id, EtkinlikBiletleri.durum == "odeme_bekliyor"))).scalar() or 0)
    return {**sayac, "bekleyen_odeme": bekleyen_odeme, "bekleme": {kk: int(v) for kk, v in bekleme.items()},
            "son_okutmalar": await k.son_okutmalar(db, e, 12)}


async def _satis(db: AsyncSession, e: Etkinlikler) -> Dict[str, Any]:
    turler = await k.tur_listesi(db, e.id)
    satirlar = dict(((tid, d), (int(n), int(t or 0))) for tid, d, n, t in (await db.execute(
        select(EtkinlikBiletleri.tur_id, EtkinlikBiletleri.durum, func.count(EtkinlikBiletleri.id), func.sum(EtkinlikBiletleri.fiyat))
        .where(EtkinlikBiletleri.etkinlik_id == e.id).group_by(EtkinlikBiletleri.tur_id, EtkinlikBiletleri.durum)
    )).all())
    siparisler = (await db.execute(select(EtkinlikSiparisleri.durum, func.count(EtkinlikSiparisleri.id),
                                          func.sum(EtkinlikSiparisleri.toplam), func.sum(EtkinlikSiparisleri.indirim))
                                   .where(EtkinlikSiparisleri.etkinlik_id == e.id).group_by(EtkinlikSiparisleri.durum))).all()
    ozet = {d: {"sayi": int(n), "toplam": int(t or 0), "indirim": int(i or 0)} for d, n, t, i in siparisler}
    iade = dict((await db.execute(select(EtkinlikBiletleri.iade, func.count(EtkinlikBiletleri.id)).where(
        EtkinlikBiletleri.etkinlik_id == e.id, EtkinlikBiletleri.iade != "yok").group_by(EtkinlikBiletleri.iade))).all())
    indirimler = (await db.execute(select(EtkinlikIndirimKodlari).where(EtkinlikIndirimKodlari.etkinlik_id == e.id)
                                   .order_by(EtkinlikIndirimKodlari.id))).scalars().all()
    para = next((t.para_birimi for t in turler if int(t.fiyat or 0) > 0), turler[0].para_birimi if turler else "TRY")
    return {
        "para_birimi": para,
        "gelir": ozet.get("onayli", {}).get("toplam", 0),
        "indirim": ozet.get("onayli", {}).get("indirim", 0),
        "bekleyen_odeme": ozet.get("odeme_bekliyor", {}),
        "siparisler": ozet,
        "iade": {kk: int(v) for kk, v in iade.items()},
        "turler": [{
            "id": t.id, "ad": t.ad, "fiyat": int(t.fiyat or 0), "para_birimi": t.para_birimi,
            "gecerli": satirlar.get((t.id, "gecerli"), (0, 0))[0], "brut": satirlar.get((t.id, "gecerli"), (0, 0))[1],
            "bekleyen": satirlar.get((t.id, "odeme_bekliyor"), (0, 0))[0], "iptal": satirlar.get((t.id, "iptal"), (0, 0))[0],
        } for t in turler],
        "indirim_kodlari": [{"kod": i.kod, "kullanilan": int(i.kullanilan or 0), "kullanim_siniri": i.kullanim_siniri}
                            for i in indirimler],
    }


# ---------------------------------------------------------------------------
# Kapak görseli ve QR
# ---------------------------------------------------------------------------
async def _kapak_birak(db: AsyncSession, e: Etkinlikler, anahtar: Optional[str]) -> None:
    if not anahtar:
        return
    g = (await db.execute(select(EtkinlikGorselleri).where(EtkinlikGorselleri.anahtar == anahtar,
                                                           EtkinlikGorselleri.etkinlik_id == e.id))).scalars().first()
    if g is None:
        return
    from services import dosya_deposu

    try:
        await dosya_deposu.sil(db, g.depo, f"etkinlik/{g.anahtar}.webp")
    except Exception:  # noqa: BLE001
        logger.warning("Etkinlik kapağı silinemedi: %s", g.anahtar)
    await db.delete(g)


async def _kapak_yukle(db: AsyncSession, kapsam: Kapsam, e: Etkinlikler, dosya: UploadFile) -> Dict[str, Any]:
    _hiz(_gorsel_hizi, kapsam.kisi)
    from services import dosya_deposu
    from services import qr_menu as menu_kurallari

    bayt = await dosya.read(menu_kurallari.GORSEL_EN_COK_BAYT + 1)
    try:
        hazir = menu_kurallari.gorsel_hazirla(bayt)
    except menu_kurallari.MenuHatasi as h:
        raise HTTPException(status_code=h.durum, detail=h.detay())
    anahtar = menu_kurallari.gorsel_anahtari()
    try:
        depo = await dosya_deposu.yaz(db, f"etkinlik/{anahtar}.webp", hazir.buyuk, "image/webp")
    except dosya_deposu.DepoHatasi:
        await db.rollback()
        raise _hata(502, "depo_hatasi")
    db.add(EtkinlikGorselleri(etkinlik_id=e.id, anahtar=anahtar, depo=depo, genislik=hazir.genislik, yukseklik=hazir.yukseklik))
    eski = e.kapak
    e.kapak = anahtar
    await _kapak_birak(db, e, eski)
    await db.commit()
    await db.refresh(e)
    return _etkinlik_sozlugu(e)


def _qr_gorsel(icerik: str, bicim: str, renk: Optional[str] = None) -> qr.Gorsel:
    tasarim = dict(qr.VARSAYILAN_TASARIM)
    if renk and qr.kontrast_orani(renk, "#ffffff") >= 4.5:
        tasarim["on_renk"] = renk
    tasarim = qr.tasarim_duzelt(tasarim)
    return (qr.png_ciz if bicim == "png" else qr.svg_ciz)(icerik, tasarim, None)


# ---------------------------------------------------------------------------
# Liste ayarı (hesabın herkese açık etkinlik listesi)
# ---------------------------------------------------------------------------
def _liste_kapsami(hesap: Optional[str]) -> str:
    return hesap or AJANS_KAPSAMI


def _liste_sozlugu(l_: Optional[EtkinlikListeleri], kapsam_: str) -> Dict[str, Any]:
    if l_ is None:
        return {"kapsam": kapsam_, "slug": "", "baslik": "", "aciklama": "", "acik": False, "adres_url": None}
    return {"kapsam": l_.kapsam, "slug": l_.slug, "baslik": l_.baslik, "aciklama": l_.aciklama or "", "acik": bool(l_.acik),
            "adres_url": s.liste_adresi(l_.slug)}


# ---------------------------------------------------------------------------
# Panel uçları (yönetici ve müşteri aynı)
# ---------------------------------------------------------------------------
def _uclari_kur(router: APIRouter, kapsam_al: Callable[[Request], Kapsam], giris_kapsami: Callable[[Request], Kapsam]) -> None:
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        return await _meta(db, kapsam_al(request))

    @router.get("/giris-listesi")
    async def giris_listesi(request: Request, db: AsyncSession = Depends(get_db)):
        """Okutma izni olan ekip üyesi için: yalnız etkinlik adı ve zamanı (katılımcı yok)."""
        kapsam = giris_kapsami(request)
        sorgu = select(Etkinlikler).where(Etkinlikler.durum.in_(("yayinda", "tamamlandi")),
                                          Etkinlikler.bitis > s.simdi() - timedelta(days=2))
        sorgu = sorgu.where(Etkinlikler.hesap_email == kapsam.hesap) if not kapsam.yonetici else sorgu
        kayitlar = (await db.execute(sorgu.order_by(Etkinlikler.baslangic).limit(100))).scalars().all()
        return {"items": [{"id": e.id, "baslik": e.baslik, "baslangic": s.iso(e.baslangic), "bitis": s.iso(e.bitis),
                           "saat_dilimi": e.saat_dilimi, "durum": e.durum, "hesap_email": e.hesap_email} for e in kayitlar]}

    @router.get("/liste-ayari")
    async def liste_ayari(request: Request, hesap: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        h = (hesap.strip().lower() or None) if kapsam.yonetici and hesap else (None if kapsam.yonetici else kapsam.hesap)
        kk = _liste_kapsami(h)
        l_ = (await db.execute(select(EtkinlikListeleri).where(EtkinlikListeleri.kapsam == kk))).scalars().first()
        return _liste_sozlugu(l_, kk)

    @router.put("/liste-ayari")
    async def liste_ayari_yaz(request: Request, govde: Dict[str, Any] = Body(...), hesap: Optional[str] = Query(None),
                              db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        h = (hesap.strip().lower() or None) if kapsam.yonetici and hesap else (None if kapsam.yonetici else kapsam.hesap)
        kk = _liste_kapsami(h)
        l_ = (await db.execute(select(EtkinlikListeleri).where(EtkinlikListeleri.kapsam == kk))).scalars().first()
        try:
            baslik = s.metin(govde.get("baslik", l_.baslik if l_ else ""), "baslik", 160, zorunlu=True)
            slug = s.slug_duzelt(govde.get("slug") or (l_.slug if l_ else s.slug_oner(baslik)))
            aciklama = s.metin(govde.get("aciklama", l_.aciklama if l_ else ""), "aciklama", 1000, cok_satir=True) or None
            acik = s.bool_duzelt(govde.get("acik", bool(l_.acik) if l_ else False), "acik")
        except s.TemelHata as h_:
            raise _e_hatasi(h_)
        if l_ is None:
            l_ = EtkinlikListeleri(kapsam=kk, hesap_email=h, slug=slug, baslik=baslik, created_at=s.simdi())
            db.add(l_)
        l_.slug, l_.baslik, l_.aciklama, l_.acik = slug, baslik, aciklama, acik
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "slug_dolu", alan="slug")
        await db.refresh(l_)
        return _liste_sozlugu(l_, kk)

    @router.get("")
    async def liste(request: Request, hesap: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _liste(db, kapsam, hesap if kapsam.yonetici else None)

    @router.post("")
    async def olustur(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        return await _olustur(db, kapsam, govde)

    @router.get("/{eid}")
    async def ayrinti(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        e = await _etkinlik(db, eid, kapsam)
        d = await k.doluluk(db, e)
        return _etkinlik_sozlugu(e, satilan=d.aktif, kalan=d.kalan(e),
                                 kapasite_siniri=await _modul_ayari(db, e.hesap_email, "kapasite_siniri", VARSAYILAN_KAPASITE_SINIRI))

    @router.put("/{eid}")
    async def guncelle(eid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                       db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        try:
            yan = await _etkinlik_uygula(db, kapsam, e, govde, yeni=False)
            if "kapasite" in govde:
                await k.koltuklari_esitle(db, e)
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)
        if yan["iptal_edildi"]:
            # Ücretli biletlerde iade bekleniyor; katılımcılara iptal e-postası.
            for b in (await db.execute(select(EtkinlikBiletleri).where(
                    EtkinlikBiletleri.etkinlik_id == e.id, EtkinlikBiletleri.durum == "gecerli",
                    EtkinlikBiletleri.fiyat > 0))).scalars().all():
                b.iade = "bekliyor"
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "slug_dolu", alan="slug")
        await db.refresh(e)
        if yan["iptal_edildi"] and govde.get("bildir", True) is not False:
            arka.add_task(k.toplu_eposta, e.id, "etkinlik_iptal")
        if yan["kapasite_artti"]:
            arka.add_task(_davet_arka_plan, e.id)
        return _etkinlik_sozlugu(e)

    @router.delete("/{eid}")
    async def sil(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Yaklaşan etkinlikte geçerli bilet varken silinmez (önce iptal). Türler ve indirim kodları
        çöp kutusuna birlikte düşer; kayıtların kişisel alanları hemen anonimleşir."""
        e = await _etkinlik(db, eid, kapsam_al(request))
        aktif = int((await db.execute(select(func.count(EtkinlikBiletleri.id)).where(
            EtkinlikBiletleri.etkinlik_id == e.id, EtkinlikBiletleri.durum.in_(k.AKTIF_BILET)))).scalar() or 0)
        if aktif and e.durum not in ("iptal", "tamamlandi") and s.utc(e.bitis) > s.simdi():
            raise _hata(409, "katilimci_var", sayi=aktif)
        await k.anonimlestir(db, e, hemen=True)
        cocuklar: List[Any] = []
        for model in (EtkinlikBiletTurleri, EtkinlikIndirimKodlari):
            cocuklar += list((await db.execute(select(model).where(model.etkinlik_id == e.id))).scalars().all())
        for kayit in cocuklar:
            await db.delete(kayit)
        await db.delete(e)
        await db.commit()
        return {"ok": True}

    @router.post("/{eid}/kapak")
    async def kapak(eid: int, request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _kapak_yukle(db, kapsam, await _etkinlik(db, eid, kapsam), dosya)

    @router.delete("/{eid}/kapak")
    async def kapak_sil(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        e = await _etkinlik(db, eid, kapsam_al(request))
        eski, e.kapak = e.kapak, None
        await _kapak_birak(db, e, eski)
        await db.commit()
        await db.refresh(e)
        return _etkinlik_sozlugu(e)

    @router.get("/{eid}/qr")
    async def etkinlik_qr(eid: int, request: Request, bicim: str = Query("png"), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        if bicim not in ("png", "svg"):
            raise _hata(400, "bicim_gecersiz")
        _hiz(_gorsel_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        g = _qr_gorsel(s.sayfa_adresi(e.slug), bicim, e.renk)
        return Response(g.veri, media_type=g.tur, headers={
            "Content-Disposition": icerik_konumu(f"etkinlik-{e.slug}-qr.{bicim}"), "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        })

    # --- Bilet türleri ---
    @router.get("/{eid}/bilet-turleri")
    async def turler(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        e = await _etkinlik(db, eid, kapsam_al(request))
        d = await k.doluluk(db, e)
        return {"items": [_tur_sozlugu(t, d, e) for t in await k.tur_listesi(db, e.id)]}

    @router.post("/{eid}/bilet-turleri")
    async def tur_olustur(eid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        mevcut = await k.tur_listesi(db, e.id)
        if len(mevcut) >= s.EN_COK_TUR:
            raise _hata(409, "tur_siniri", sinir=s.EN_COK_TUR)
        t = EtkinlikBiletTurleri(etkinlik_id=e.id, sira=len(mevcut), fiyat=0, para_birimi="TRY", kisi_basi_en_cok=5,
                                 gizli=False, aktif=True, created_at=s.simdi())
        try:
            await _tur_uygula(db, e, t, govde, yeni=True)
        except s.TemelHata as h:
            raise _e_hatasi(h)
        db.add(t)
        await db.commit()
        await db.refresh(t)
        return _tur_sozlugu(t, await k.doluluk(db, e), e)

    @router.put("/{eid}/bilet-turleri/{tid}")
    async def tur_guncelle(eid: int, tid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                           db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        t = await _tur(db, e, tid)
        eski_kontenjan = t.kontenjan
        try:
            await _tur_uygula(db, e, t, govde, yeni=False)
            if "kontenjan" in govde:
                await k.koltuklari_esitle(db, e, t)
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)
        await db.commit()
        await db.refresh(t)
        if eski_kontenjan is not None and (t.kontenjan is None or t.kontenjan > eski_kontenjan):
            arka.add_task(_davet_arka_plan, e.id)
        return _tur_sozlugu(t, await k.doluluk(db, e), e)

    @router.delete("/{eid}/bilet-turleri/{tid}")
    async def tur_sil(eid: int, tid: int, request: Request, db: AsyncSession = Depends(get_db)):
        e = await _etkinlik(db, eid, kapsam_al(request))
        t = await _tur(db, e, tid)
        var = int((await db.execute(select(func.count(EtkinlikBiletleri.id)).where(EtkinlikBiletleri.tur_id == t.id))).scalar() or 0)
        if var:
            raise _hata(409, "bilet_var", sayi=var)
        await db.delete(t)
        await db.commit()
        return {"ok": True}

    # --- İndirim kodları ---
    @router.get("/{eid}/indirimler")
    async def indirimler(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        e = await _etkinlik(db, eid, kapsam_al(request))
        kayitlar = (await db.execute(select(EtkinlikIndirimKodlari).where(EtkinlikIndirimKodlari.etkinlik_id == e.id)
                                     .order_by(EtkinlikIndirimKodlari.id))).scalars().all()
        return {"items": [_indirim_sozlugu(i) for i in kayitlar]}

    @router.post("/{eid}/indirimler")
    async def indirim_olustur(eid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        sayi = int((await db.execute(select(func.count(EtkinlikIndirimKodlari.id)).where(
            EtkinlikIndirimKodlari.etkinlik_id == e.id))).scalar() or 0)
        if sayi >= s.EN_COK_INDIRIM:
            raise _hata(409, "indirim_siniri", sinir=s.EN_COK_INDIRIM)
        i = EtkinlikIndirimKodlari(etkinlik_id=e.id, kullanilan=0, aktif=True, created_at=s.simdi())
        try:
            await _indirim_uygula(db, e, i, govde, yeni=True)
        except s.TemelHata as h:
            raise _e_hatasi(h)
        db.add(i)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "kod_var", alan="kod")
        await db.refresh(i)
        return _indirim_sozlugu(i)

    @router.put("/{eid}/indirimler/{iid}")
    async def indirim_guncelle(eid: int, iid: int, request: Request, govde: Dict[str, Any] = Body(...),
                               db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        i = await _indirim(db, e, iid)
        try:
            await _indirim_uygula(db, e, i, govde, yeni=False)
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "kod_var", alan="kod")
        await db.refresh(i)
        return _indirim_sozlugu(i)

    @router.delete("/{eid}/indirimler/{iid}")
    async def indirim_sil(eid: int, iid: int, request: Request, db: AsyncSession = Depends(get_db)):
        e = await _etkinlik(db, eid, kapsam_al(request))
        i = await _indirim(db, e, iid)
        if int(i.kullanilan or 0):
            i.aktif = False  # kullanılmış kod silinmez (satış raporu), yalnız kapanır
        else:
            await db.delete(i)
        await db.commit()
        return {"ok": True}

    # --- Katılımcılar ---
    @router.get("/{eid}/katilimcilar")
    async def katilimcilar(eid: int, request: Request, durum: Optional[str] = Query(None), tur_id: Optional[int] = Query(None),
                           ara: Optional[str] = Query(None), giris: Optional[str] = Query(None),
                           sinir: int = Query(200, ge=1, le=1000), atla: int = Query(0, ge=0),
                           db: AsyncSession = Depends(get_db)):
        e = await _etkinlik(db, eid, kapsam_al(request))
        await k.suresi_dolanlari_birak(db, e.id)
        await db.commit()
        toplam, satirlar = await _katilimci_satirlari(db, e, durum, tur_id, ara, giris, sinir, atla)
        turler_ = {t.id: t for t in await k.tur_listesi(db, e.id)}
        sorular = {q.get("id"): q.get("etiket") for q in (s.json_yukle(e.sorular, []) or [])}
        return {"items": [_katilimci_sozlugu(b, sp, turler_, sorular) for b, sp in satirlar], "toplam": toplam}

    @router.get("/{eid}/katilimcilar.csv")
    async def katilimci_csv(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_gorsel_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        return Response(await _csv(db, e), media_type="text/csv; charset=utf-8", headers={
            "Content-Disposition": icerik_konumu(f"katilimcilar-{e.slug}.csv"), "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        })

    @router.post("/{eid}/katilimcilar")
    async def katilimci_ekle(eid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                             db: AsyncSession = Depends(get_db)):
        """Elle ekle (kapıda kayıt, davetli konuk): kapasite yine korunur; ödeme alınmaz."""
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        try:
            tid = govde.get("tur_id")
            if isinstance(tid, bool) or not isinstance(tid, int):
                raise s.EtkinlikHatasi("kalem_gecersiz", "tur_id")
            adet = int(s.tam_sayi(govde.get("adet", 1), "adet", 1, s.EN_COK_ADET))
            g = k.KayitGirdisi(
                kalemler=[(tid, adet)], ad=s.metin(govde.get("ad"), "ad", 120, zorunlu=True),
                eposta=s.eposta_duzelt(govde.get("eposta")),
                telefon=s.telefon_duzelt(govde.get("telefon"), "telefon"),
                katilimcilar=[s.metin(x, "katilimcilar", 120) for x in (govde.get("katilimcilar") or [])][:s.EN_COK_ADET],
                dil=s.dil_duzelt(govde.get("dil") or e.dil), kaynak="panel",
            )
            sp, _ = await k.kayit_olustur(db, e, g)
        except s.TemelHata as h:
            raise _e_hatasi(h)
        if govde.get("bildir", True) is not False:
            arka.add_task(k.bilet_epostasi, sp.id)
        return {"ok": True, "siparis_id": sp.id, "kod": sp.kod}

    @router.post("/{eid}/siparisler/{sid}/iptal")
    async def siparis_iptal(eid: int, sid: int, request: Request, arka: BackgroundTasks,
                            govde: Dict[str, Any] = Body(default={}), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        sp = await _siparis(db, e, sid)
        biletler = [b for b in await k.siparis_biletleri(db, sp.id) if b.durum != "iptal"]
        if not biletler:
            raise _hata(409, "zaten_iptal")
        try:
            neden = s.metin(govde.get("neden"), "neden", 500, cok_satir=True)
        except s.TemelHata as h:
            raise _e_hatasi(h)
        await k.biletleri_iptal_et(db, e, biletler, "sahip", iade=govde.get("iade") is True, neden=neden)
        if sp.odeme_jeton and sp.durum == "iptal":
            from models.payments import Payments

            for p in (await db.execute(select(Payments).where(Payments.jeton == sp.odeme_jeton, Payments.durum == "bekliyor"))).scalars().all():
                p.durum = "iptal"
        await db.commit()
        if govde.get("bildir", True) is not False:
            arka.add_task(k.iptal_epostasi, sp.id)
        arka.add_task(_davet_arka_plan, e.id)
        return {"ok": True}

    @router.post("/{eid}/siparisler/{sid}/odendi")
    async def siparis_odendi(eid: int, sid: int, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
        """Havale / kapıda ödeme: bekleyen (ya da süresi dolan) ücretli kaydı onaylar. Yalnız ajans etkinliği."""
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        sp = await _siparis(db, e, sid)
        if sp.durum not in ("odeme_bekliyor", "suresi_doldu") or not sp.odeme_jeton:
            raise _hata(409, "odeme_beklemiyor")
        from models.payments import Payments

        p = (await db.execute(select(Payments).where(Payments.jeton == sp.odeme_jeton))).scalars().first()
        if p is None:
            raise _hata(409, "odeme_beklemiyor")
        p.durum, p.saglayici, p.odendi_at, p.ekleyen_eposta = "odendi", "havale", datetime.now(), kapsam.kisi
        siparis_id = await k.odeme_tamamlandi(db, p)
        await db.commit()
        arka.add_task(k.odeme_sonrasi, siparis_id)
        return {"ok": True}

    @router.post("/{eid}/biletler/{bid}/iptal")
    async def bilet_iptal(eid: int, bid: int, request: Request, arka: BackgroundTasks,
                          govde: Dict[str, Any] = Body(default={}), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        b = await _bilet(db, e, bid)
        if b.durum == "iptal":
            raise _hata(409, "zaten_iptal")
        await k.biletleri_iptal_et(db, e, [b], "sahip", iade=govde.get("iade") is True)
        await db.commit()
        if govde.get("bildir", False) is True:
            arka.add_task(k.iptal_epostasi, b.siparis_id)
        arka.add_task(_davet_arka_plan, e.id)
        return {"ok": True}

    @router.post("/{eid}/biletler/{bid}/iade")
    async def bilet_iade(eid: int, bid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        b = await _bilet(db, e, bid)
        if govde.get("durum") not in ("yok", "bekliyor", "yapildi"):
            raise _hata(400, "secim_gecersiz", alan="durum")
        b.iade = govde["durum"]
        await db.commit()
        return {"ok": True, "iade": b.iade}

    @router.post("/{eid}/biletler/{bid}/giris")
    async def bilet_giris(eid: int, bid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = giris_kapsami(request)
        _hiz(_okut_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        b = await _bilet(db, e, bid)
        return await k.okut(db, e, b.kod, kaynak="panel", yapan=kapsam.kisi)

    @router.delete("/{eid}/biletler/{bid}/giris")
    async def bilet_giris_geri(eid: int, bid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        e = await _etkinlik(db, eid, kapsam)
        b = await _bilet(db, e, bid)
        b.giris_at, b.giris_yapan = None, None
        await db.commit()
        return {"ok": True}

    # --- Bekleme listesi ---
    @router.get("/{eid}/bekleme")
    async def bekleme(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        e = await _etkinlik(db, eid, kapsam_al(request))
        await k.suresi_dolanlari_birak(db, e.id)
        await db.commit()
        kayitlar = (await db.execute(select(EtkinlikBekleme).where(EtkinlikBekleme.etkinlik_id == e.id)
                                     .order_by(EtkinlikBekleme.id).limit(1000))).scalars().all()
        return {"items": [{"id": w.id, "ad": w.ad, "eposta": w.eposta, "telefon": w.telefon, "adet": int(w.adet or 1),
                           "tur_id": w.tur_id, "durum": w.durum, "davet_at": s.iso(w.davet_at), "davet_son": s.iso(w.davet_son),
                           "siparis_id": w.siparis_id, "created_at": s.iso(w.created_at)} for w in kayitlar]}

    @router.post("/{eid}/bekleme/{wid}/davet")
    async def bekleme_davet(eid: int, wid: int, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        w = (await db.execute(select(EtkinlikBekleme).where(EtkinlikBekleme.id == wid,
                                                            EtkinlikBekleme.etkinlik_id == e.id))).scalars().first()
        if w is None:
            raise _hata(404, "bulunamadi")
        if w.durum not in ("bekliyor", "suresi_doldu"):
            raise _hata(409, "davet_edilemez")
        w.durum = "bekliyor"
        await db.commit()
        idler = await k.bekleme_davet_et(db, e)
        if w.id not in idler:
            raise _hata(409, "yer_yok")
        arka.add_task(k.davetleri_gonder, idler)
        return {"ok": True, "davet": idler}

    @router.delete("/{eid}/bekleme/{wid}")
    async def bekleme_sil(eid: int, wid: int, request: Request, db: AsyncSession = Depends(get_db)):
        e = await _etkinlik(db, eid, kapsam_al(request))
        w = (await db.execute(select(EtkinlikBekleme).where(EtkinlikBekleme.id == wid,
                                                            EtkinlikBekleme.etkinlik_id == e.id))).scalars().first()
        if w is None:
            raise _hata(404, "bulunamadi")
        w.durum = "iptal"
        await db.commit()
        return {"ok": True}

    # --- İstatistik, satış, okutma ---
    @router.get("/{eid}/istatistik")
    async def istatistik(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        return await _istatistik(db, await _etkinlik(db, eid, kapsam_al(request)))

    @router.get("/{eid}/satis")
    async def satis(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        return await _satis(db, await _etkinlik(db, eid, kapsam_al(request)))

    @router.get("/{eid}/sayac")
    async def sayac(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        e = await _etkinlik(db, eid, giris_kapsami(request))
        return {**await k.sayac(db, e), "baslik": e.baslik, "baslangic": s.iso(e.baslangic), "bitis": s.iso(e.bitis),
                "saat_dilimi": e.saat_dilimi, "durum": e.durum}

    @router.post("/{eid}/okut")
    async def okut(eid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = giris_kapsami(request)
        _hiz(_okut_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        return await k.okut(db, e, govde.get("kod"), kaynak="panel", yapan=kapsam.kisi,
                            cevrimdisi=govde.get("cevrimdisi") is True, istemci_zaman=_istemci_zamani(govde.get("zaman")))

    # --- Duyuru ve teşekkür (bilgilendirme e-postası; pazarlama değil) ---
    @router.post("/{eid}/duyuru")
    async def duyuru(eid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                     db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        e = await _etkinlik(db, eid, kapsam)
        try:
            konu = s.metin(govde.get("konu"), "konu", 150, zorunlu=True)
            metin_ = s.metin(govde.get("metin"), "metin", 5000, zorunlu=True, cok_satir=True)
        except s.TemelHata as h:
            raise _e_hatasi(h)
        _hiz(_duyuru_hizi, f"{e.id}")
        alici = int((await db.execute(select(func.count(func.distinct(EtkinlikSiparisleri.eposta)))
                                      .join(EtkinlikBiletleri, EtkinlikBiletleri.siparis_id == EtkinlikSiparisleri.id)
                                      .where(EtkinlikSiparisleri.etkinlik_id == e.id, EtkinlikSiparisleri.anonim.is_(False),
                                             EtkinlikBiletleri.durum == "gecerli"))).scalar() or 0)
        if not alici:
            raise _hata(409, "alici_yok")
        arka.add_task(k.toplu_eposta, e.id, "duyuru", konu, metin_)
        return {"ok": True, "alici": alici}

    @router.post("/{eid}/tesekkur")
    async def tesekkur(eid: int, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        e = await _etkinlik(db, eid, kapsam)
        if s.utc(e.bitis) > s.simdi():
            raise _hata(409, "etkinlik_bitmedi")
        _hiz(_duyuru_hizi, f"{e.id}")
        e.tesekkur_at = s.simdi()
        await db.commit()
        arka.add_task(k.toplu_eposta, e.id, "tesekkur")
        return {"ok": True}

    # --- Görevli (kapı) bağlantısı ---
    @router.get("/{eid}/gorevli")
    async def gorevli(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        e = await _etkinlik(db, eid, kapsam_al(request))
        son = _gorevli_bitisi(e)
        jeton = s.gorevli_jetonu(e.id, int(e.gorevli_surumu or 1), son)
        return {"adres": s.gorevli_adresi(jeton), "son": s.iso(son), "surum": int(e.gorevli_surumu or 1)}

    @router.post("/{eid}/gorevli")
    async def gorevli_yeni(eid: int, request: Request, govde: Dict[str, Any] = Body(default={}), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        if govde.get("yenile") is True:
            e.gorevli_surumu = int(e.gorevli_surumu or 1) + 1
            await db.commit()
            await db.refresh(e)
        try:
            saat = s.tam_sayi(govde.get("saat"), "saat", 1, s.GOREVLI_EN_COK_SAAT, bos_olabilir=True)
        except s.TemelHata as h:
            raise _e_hatasi(h)
        son = s.simdi().replace(microsecond=0) + timedelta(hours=saat) if saat else _gorevli_bitisi(e)
        jeton = s.gorevli_jetonu(e.id, int(e.gorevli_surumu or 1), son)
        return {"adres": s.gorevli_adresi(jeton), "son": s.iso(son), "surum": int(e.gorevli_surumu or 1)}

    # --- E-posta pazarlamaya aktarım (yalnız izin verenler) ---
    @router.get("/{eid}/pazarlama")
    async def pazarlama(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        e = await _etkinlik(db, eid, kapsam_al(request))
        from models.eposta_pazarlama import EpListeler
        from services.moduller import modul_acik_mi

        acik = True if e.hesap_email is None else await modul_acik_mi(db, e.hesap_email, "eposta_pazarlama")
        izinli = int((await db.execute(select(func.count(EtkinlikSiparisleri.id)).where(
            EtkinlikSiparisleri.etkinlik_id == e.id, EtkinlikSiparisleri.pazarlama_izni_at.isnot(None),
            EtkinlikSiparisleri.anonim.is_(False)))).scalar() or 0)
        listeler = []
        if acik:
            kosul = EpListeler.hesap_email.is_(None) if e.hesap_email is None else EpListeler.hesap_email == e.hesap_email
            listeler = [{"id": l_.id, "ad": l_.ad} for l_ in (await db.execute(select(EpListeler).where(kosul)
                                                                             .order_by(EpListeler.id))).scalars().all()]
        return {"acik": acik, "izinli": izinli, "listeler": listeler}

    @router.post("/{eid}/pazarlama")
    async def pazarlama_aktar(eid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        e = await _etkinlik(db, eid, kapsam)
        if e.hesap_email is not None:
            from services.moduller import modul_acik_mi

            if not await modul_acik_mi(db, e.hesap_email, "eposta_pazarlama"):
                raise _hata(403, "modul_kapali", modul="eposta_pazarlama")
        liste_id = govde.get("liste_id")
        if isinstance(liste_id, bool) or not isinstance(liste_id, int):
            raise _hata(400, "liste_yok", alan="liste_id")
        try:
            return {"sayilar": await k.pazarlamaya_aktar(db, e, liste_id)}
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)


def _istemci_zamani(ham: Any) -> Optional[datetime]:
    try:
        return s.zaman_coz(ham, "zaman", bos_olabilir=True)
    except s.TemelHata:
        return None


_uclari_kur(yonetici_router, _yonetici_kapsami, _yonetici_kapsami)
_uclari_kur(musteri_router, _musteri_kapsami, _musteri_giris_kapsami)


# ---------------------------------------------------------------------------
# Herkese açık
# ---------------------------------------------------------------------------
ACIK_BASLIKLAR = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


async def _yayinda_mi(db: AsyncSession, e: Etkinlikler) -> bool:
    if e.durum == "taslak":
        return False
    if e.hesap_email:
        from services import moduller as modul_servisi

        return await modul_servisi.modul_acik_mi(db, e.hesap_email, MODUL)
    return True


async def _acik_etkinlik(db: AsyncSession, slug: str) -> Etkinlikler:
    """Slug'a göre: yok/taslak → 404, sahibinin modülü kapalı → 410."""
    temiz = (slug or "").strip().lower()
    if not s.SLUG_DESENI.match(temiz):
        raise _hata(404, "etkinlik_yok")
    e = (await db.execute(select(Etkinlikler).where(Etkinlikler.slug == temiz))).scalars().first()
    if e is None or e.durum == "taslak":
        raise _hata(404, "etkinlik_yok")
    if not await _yayinda_mi(db, e):
        raise _hata(410, "etkinlik_pasif")
    return e


def _ziyaretci(request: Request, etkinlik_id: int) -> str:
    return f"{etkinlik_id}|{ip_ozeti('etkinlik-hiz|' + istemci_ip(request))}"


def _robots(e: Etkinlikler) -> Dict[str, str]:
    return {} if e.arama_motoru else {"X-Robots-Tag": "noindex"}


async def _govde_oku(request: Request, sinir: int = 32768) -> Dict[str, Any]:
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


def _pazarlama_metinleri() -> Dict[str, str]:
    from services import pazarlama_izni

    return dict(pazarlama_izni.METINLER)


async def _acik_sozluk(db: AsyncSession, e: Etkinlikler, gizli_kod: Optional[str], davet: Optional[EtkinlikBekleme]) -> Dict[str, Any]:
    d = await k.doluluk(db, e, haric_davet_id=davet.id if davet is not None else None)
    an = s.simdi()
    acik, neden = k.kayit_acik_mi(e, an)
    turler = []
    for t in await k.tur_listesi(db, e.id):
        if not t.aktif:
            continue
        if t.gizli and not (gizli_kod and t.gizli_kod and gizli_kod.strip().upper() == t.gizli_kod.upper()):
            continue
        if davet is not None and davet.tur_id and davet.tur_id != t.id:
            continue
        musait = d.musait(e, t)
        satis = "acik"
        if t.satis_bas and an < s.utc(t.satis_bas):
            satis = "baslamadi"
        elif t.satis_bit and an > s.utc(t.satis_bit):
            satis = "bitti"
        turler.append({
            "id": t.id, "ad": t.ad, "aciklama": t.aciklama or "", "fiyat": int(t.fiyat or 0), "para_birimi": t.para_birimi,
            "kalan": musait, "dolu": musait is not None and musait <= 0, "satis": satis, "satis_bas": s.iso(t.satis_bas),
            "satis_bit": s.iso(t.satis_bit), "kisi_basi_en_cok": int(t.kisi_basi_en_cok or 1), "gizli": bool(t.gizli),
        })
    kalan = d.kalan(e)
    return {
        "slug": e.slug, "baslik": e.baslik, "ozet": e.ozet or "", "aciklama": e.aciklama or "", "kapak": s.kapak_adresi(e.kapak),
        "renk": e.renk, "bicim": e.bicim, "mekan_adi": e.mekan_adi or "", "adres": e.adres or "",
        "harita": s.harita_adresi(e), "saat_dilimi": e.saat_dilimi, "baslangic": s.iso(e.baslangic), "bitis": s.iso(e.bitis),
        "oturumlar": s.json_yukle(e.oturumlar, []) or [], "durum": e.durum, "dil": e.dil,
        "organizator_ad": e.organizator_ad or "", "organizator_url": e.organizator_url or "",
        "iade_politikasi": e.iade_politikasi or "", "kvkk_metni": e.kvkk_metni or "", "odeme_notu": e.odeme_notu or "",
        "katilimci_adlari": bool(e.katilimci_adlari), "telefon": e.telefon, "sorular": s.json_yukle(e.sorular, []) or [],
        "bekleme_listesi": bool(e.bekleme_listesi), "kapasite": e.kapasite, "kalan": kalan,
        "dolu": kalan is not None and kalan <= 0, "kayit_acik": acik, "kayit_neden": neden,
        "kayit_acilis": s.iso(e.kayit_acilis), "kayit_kapanis": s.iso(e.kayit_kapanis or e.baslangic),
        "indirim_var": bool((await db.execute(select(EtkinlikIndirimKodlari.id).where(
            EtkinlikIndirimKodlari.etkinlik_id == e.id, EtkinlikIndirimKodlari.aktif.is_(True)).limit(1))).first()),
        "gizli_tur_var": any(t.gizli and t.aktif for t in await k.tur_listesi(db, e.id)),
        "indekslenebilir": bool(e.arama_motoru), "ajans": e.hesap_email is None, "turler": turler,
        "pazarlama_metinleri": _pazarlama_metinleri(), "adres_url": s.sayfa_adresi(e.slug),
        "davet": ({"gecerli": True, "son": s.iso(davet.davet_son), "adet": int(davet.adet or 1), "tur_id": davet.tur_id,
                   "ad": davet.ad, "eposta": davet.eposta} if davet is not None else None),
    }


@acik_router.api_route("/{slug}", methods=["GET", "HEAD"])
async def acik_etkinlik(slug: str, request: Request, kod: Optional[str] = Query(None), davet: Optional[str] = Query(None),
                        db: AsyncSession = Depends(get_db)):
    e = await _acik_etkinlik(db, slug)
    davet_kaydi = None
    if davet:
        try:
            davet_kaydi = await k.davet_bul(db, e, davet)
        except s.TemelHata as h:
            raise _e_hatasi(h)
    await k.suresi_dolanlari_birak(db, e.id)
    await db.commit()
    return JSONResponse(await _acik_sozluk(db, e, kod, davet_kaydi),
                        headers={**ACIK_BASLIKLAR, "Cache-Control": "no-cache", **_robots(e)})


@acik_router.get("/{slug}/ozet")
async def acik_ozet(slug: str, db: AsyncSession = Depends(get_db)):
    """Pages Function'ın paylaşım önizlemesi (title/og/twitter/canonical/robots) ve Event JSON-LD'si."""
    e = await _acik_etkinlik(db, slug)
    kapak = s.kapak_adresi(e.kapak, mutlak=True)
    veri: Dict[str, Any] = {
        "slug": e.slug, "baslik": e.baslik, "aciklama": (e.ozet or (e.aciklama or "")[:300])[:300], "dil": e.dil,
        "gorsel": kapak, "renk": e.renk, "indekslenebilir": bool(e.arama_motoru), "adres_url": s.sayfa_adresi(e.slug),
        "baslangic": s.iso(e.baslangic), "bitis": s.iso(e.bitis), "saat_dilimi": e.saat_dilimi, "durum": e.durum,
        "jsonld": None,
    }
    if e.arama_motoru:
        turler = await k.tur_listesi(db, e.id)
        d = await k.doluluk(db, e)
        dolu = {t.id: (d.musait(e, t) is not None and d.musait(e, t) <= 0) for t in turler}
        veri["jsonld"] = s.event_jsonld(e, turler, dolu, kapak)
    return JSONResponse(veri, headers={"Cache-Control": "public, max-age=60", "X-Content-Type-Options": "nosniff"})


def _kayit_alanlari(e: Etkinlikler, govde: Dict[str, Any]) -> Dict[str, Any]:
    telefon_kurali = e.telefon or "istege_bagli"
    return {
        "kalemler": s.kalemleri_duzelt(govde.get("kalemler")),
        "ad": s.metin(govde.get("ad"), "ad", 120, zorunlu=True),
        "eposta": s.eposta_duzelt(govde.get("eposta")),
        "telefon": None if telefon_kurali == "gizli" else s.telefon_duzelt(govde.get("telefon"), "telefon",
                                                                            zorunlu=telefon_kurali == "zorunlu"),
        "dil": govde.get("dil") if govde.get("dil") in s.DILLER else e.dil,
    }


@acik_router.post("/{slug}/fiyat")
async def acik_fiyat(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request, 8192)
    e = await _acik_etkinlik(db, slug)
    _hiz(_fiyat_hizi, _ziyaretci(request, e.id))
    try:
        kalemler = s.kalemleri_duzelt(govde.get("kalemler"))
        turler = {t.id: t for t in await k.tur_listesi(db, e.id)}
        secili = []
        for tid, adet in kalemler:
            t = turler.get(tid)
            if t is None or not t.aktif or not k._gizli_kod_tutuyor_mu(t, govde.get("gizli_kod")):
                raise s.EtkinlikHatasi("tur_yok", "kalemler", durum=404)
            secili.append(s.Kalem(t.id, adet, int(t.fiyat or 0), t.para_birimi))
        indirim = None
        if govde.get("indirim_kodu"):
            indirim = await k.indirim_bul(db, e, govde.get("indirim_kodu"), [x.tur_id for x in secili])
        return JSONResponse(s.fiyat_hesapla(secili, k.indirim_kurali(indirim)), headers=ACIK_BASLIKLAR)
    except s.TemelHata as h:
        raise _e_hatasi(h)


@acik_router.post("/{slug}/kayit")
async def acik_kayit(slug: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request)
    e = await _acik_etkinlik(db, slug)
    await _kalici_hiz((_kayit_hizi, _ziyaretci(request, e.id)), (_etkinlik_kayit_hizi, str(e.id)))
    # Bal küpü: bot "başarılı" görsün, hiçbir şey kaydedilmesin.
    if str(govde.get("web_adresi") or "").strip():
        logger.info("Etkinlik: bal küpü dolu, yok sayıldı (etkinlik %s)", e.id)
        return JSONResponse({"ok": True, "siparis": None}, headers=ACIK_BASLIKLAR)
    acik, neden = k.kayit_acik_mi(e)
    davet_kaydi = None
    try:
        if govde.get("davet"):
            davet_kaydi = await k.davet_bul(db, e, str(govde.get("davet")))
        if not acik:
            raise s.EtkinlikHatasi(neden or "kayit_kapali", durum=409)
        alan = _kayit_alanlari(e, govde)
        yanitlar = s.yanitlari_dogrula(s.json_yukle(e.sorular, []) or [], govde.get("yanitlar"))
        katilimcilar = govde.get("katilimcilar") or []
        if not isinstance(katilimcilar, list):
            raise s.EtkinlikHatasi("katilimci_gecersiz", "katilimcilar")
        katilimcilar = [s.metin(x, f"katilimcilar.{i}", 120) for i, x in enumerate(katilimcilar[:s.EN_COK_ADET])]
        from services import pazarlama_izni

        g = k.KayitGirdisi(
            kalemler=alan["kalemler"], ad=alan["ad"], eposta=alan["eposta"], telefon=alan["telefon"], yanitlar=yanitlar,
            katilimcilar=katilimcilar, indirim_kodu=(str(govde.get("indirim_kodu") or "").strip() or None),
            gizli_kod=(str(govde.get("gizli_kod") or "").strip() or None), davet=davet_kaydi,
            pazarlama_izni=pazarlama_izni.izin_verildi_mi(govde.get("pazarlama_izni")), dil=alan["dil"],
            kaynak="davet" if davet_kaydi is not None else "form",
        )
        sp, biletler = await k.kayit_olustur(db, e, g)
    except s.TemelHata as h:
        raise _e_hatasi(h)
    jeton = s.siparis_jetonu(sp.id, sp.kod)
    yanit: Dict[str, Any] = {
        "ok": True, "siparis": {"kod": sp.kod, "durum": sp.durum, "toplam": int(sp.toplam), "para_birimi": sp.para_birimi,
                                "bilet_sayisi": len(biletler)},
        "jeton": jeton, "bilet_adresi": f"/etkinlik/{e.slug}/bilet/{jeton}",
    }
    if sp.durum == "odeme_bekliyor":
        yanit["odeme_adresi"] = f"/ode/{sp.odeme_jeton}"
        yanit["odeme_son"] = s.iso(sp.odeme_son)
        arka.add_task(k.bilet_epostasi, sp.id, "odeme")
    else:
        arka.add_task(k.bilet_epostasi, sp.id)
        arka.add_task(k.sahip_bildirimi, sp.id, k.SAHIP_KAYIT)
    if e.hesap_email is None:
        arka.add_task(k.crm_isle, sp.id)
    return JSONResponse(yanit, headers=ACIK_BASLIKLAR)


@acik_router.post("/{slug}/bekleme")
async def acik_bekleme(slug: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request, 8192)
    e = await _acik_etkinlik(db, slug)
    await _kalici_hiz((_bekleme_hizi, _ziyaretci(request, e.id)))
    if str(govde.get("web_adresi") or "").strip():
        return JSONResponse({"ok": True}, headers=ACIK_BASLIKLAR)
    try:
        acik, neden = k.kayit_acik_mi(e)
        if not acik:
            raise s.EtkinlikHatasi(neden or "kayit_kapali", durum=409)
        if not e.bekleme_listesi:
            raise s.EtkinlikHatasi("bekleme_kapali", durum=409)
        ad = s.metin(govde.get("ad"), "ad", 120, zorunlu=True)
        eposta = s.eposta_duzelt(govde.get("eposta"))
        telefon = None if e.telefon == "gizli" else s.telefon_duzelt(govde.get("telefon"), "telefon")
        adet = int(s.tam_sayi(govde.get("adet", 1), "adet", 1, s.EN_COK_ADET))
        tur_id = govde.get("tur_id")
        t = None
        if tur_id is not None:
            if isinstance(tur_id, bool) or not isinstance(tur_id, int):
                raise s.EtkinlikHatasi("tur_yok", "tur_id", durum=404)
            t = (await db.execute(select(EtkinlikBiletTurleri).where(EtkinlikBiletTurleri.id == tur_id,
                                                                     EtkinlikBiletTurleri.etkinlik_id == e.id,
                                                                     EtkinlikBiletTurleri.aktif.is_(True)))).scalars().first()
            if t is None or (t.gizli and not k._gizli_kod_tutuyor_mu(t, govde.get("gizli_kod"))):
                raise s.EtkinlikHatasi("tur_yok", "tur_id", durum=404)
            if adet > int(t.kisi_basi_en_cok or 1):
                raise s.EtkinlikHatasi("kisi_basi_siniri", "adet", en_cok=int(t.kisi_basi_en_cok or 1))
        d = await k.doluluk(db, e)
        musait = d.musait(e, t) if t is not None else d.kalan(e)
        if musait is None or musait >= adet:
            raise s.EtkinlikHatasi("yer_var", durum=409)
        var = (await db.execute(select(EtkinlikBekleme.id).where(
            EtkinlikBekleme.etkinlik_id == e.id, EtkinlikBekleme.eposta == eposta,
            EtkinlikBekleme.durum.in_(("bekliyor", "davet"))).limit(1))).first()
        if var:
            raise s.EtkinlikHatasi("zaten_listede", durum=409)
        from services import pazarlama_izni

        dil = govde.get("dil") if govde.get("dil") in s.DILLER else e.dil
        izin = pazarlama_izni.izin_verildi_mi(govde.get("pazarlama_izni"))
    except s.TemelHata as h:
        raise _e_hatasi(h)
    an = s.simdi()
    w = EtkinlikBekleme(etkinlik_id=e.id, tur_id=t.id if t is not None else None, ad=ad, eposta=eposta, telefon=telefon,
                        adet=adet, dil=dil, durum="bekliyor", pazarlama_izni_at=an if izin else None,
                        pazarlama_metin_surumu=pazarlama_izni.surum_etiketi(dil) if izin else None, anonim=False, created_at=an)
    db.add(w)
    await db.commit()
    await db.refresh(w)
    sira = int((await db.execute(select(func.count(EtkinlikBekleme.id)).where(
        EtkinlikBekleme.etkinlik_id == e.id, EtkinlikBekleme.durum == "bekliyor", EtkinlikBekleme.id <= w.id))).scalar() or 1)
    arka.add_task(k.bekleme_epostasi, w.id, "bekleme")
    return JSONResponse({"ok": True, "sira": sira}, headers=ACIK_BASLIKLAR)


# ---------------------------------------------------------------------------
# Bilet sayfası (imzalı bağlantı)
# ---------------------------------------------------------------------------
async def _bilet_jetonlu(db: AsyncSession, request: Request, jeton: str):
    await _kalici_hiz((_bilet_hizi, ip_ozeti("etkinlik-bilet|" + istemci_ip(request))))
    kimlik = s.siparis_jetonu_kimligi(jeton)
    if kimlik is None:
        raise _hata(404, "baglanti_gecersiz")
    sp = (await db.execute(select(EtkinlikSiparisleri).where(EtkinlikSiparisleri.id == kimlik))).scalars().first()
    if sp is None or not s.siparis_jetonu_gecerli_mi(jeton, sp.id, sp.kod):
        raise _hata(404, "baglanti_gecersiz")
    e = (await db.execute(select(Etkinlikler).where(Etkinlikler.id == sp.etkinlik_id))).scalars().first()
    if e is None:
        raise _hata(404, "baglanti_gecersiz")
    if sp.anonim or s.utc(e.bitis) + timedelta(days=s.JETON_OMRU_GUN) < s.simdi():
        raise _hata(410, "baglanti_suresi_doldu")
    if e.hesap_email and not await _yayinda_mi(db, e):
        raise _hata(410, "etkinlik_pasif")
    return sp, e


def _iptal_sonu(e: Etkinlikler) -> datetime:
    return s.utc(e.baslangic) - timedelta(hours=int(e.iptal_sinir_saat or 0))


async def _bilet_sozlugu(db: AsyncSession, sp: EtkinlikSiparisleri, e: Etkinlikler, jeton: str) -> Dict[str, Any]:
    biletler = await k.siparis_biletleri(db, sp.id)
    turler = {t.id: t for t in await k.tur_listesi(db, e.id)}
    dil = sp.dil if sp.dil in s.DILLER else e.dil
    gecerli_var = any(b.durum == "gecerli" for b in biletler)
    adres = s.bilet_adresi(e.slug, jeton)
    taban = f"/api/v1/etkinlik/bilet/{jeton}"
    son = _iptal_sonu(e)
    iptal_edilebilir = (any(b.durum != "iptal" and not b.giris_at for b in biletler) and e.durum == "yayinda"
                        and s.simdi() < son)
    veri: Dict[str, Any] = {
        "siparis": {"kod": sp.kod, "durum": sp.durum, "ad": sp.ad, "eposta": sp.eposta, "toplam": int(sp.toplam or 0),
                    "indirim": int(sp.indirim or 0), "para_birimi": sp.para_birimi, "dil": dil, "created_at": s.iso(sp.created_at),
                    "odeme_adresi": f"/ode/{sp.odeme_jeton}" if sp.durum == "odeme_bekliyor" and sp.odeme_jeton else None,
                    "odeme_son": s.iso(sp.odeme_son) if sp.durum == "odeme_bekliyor" else None},
        "etkinlik": {
            "slug": e.slug, "baslik": e.baslik, "ozet": e.ozet or "", "kapak": s.kapak_adresi(e.kapak), "renk": e.renk,
            "bicim": e.bicim, "mekan_adi": e.mekan_adi or "", "adres": e.adres or "", "harita": s.harita_adresi(e),
            "online_baglanti": e.online_baglanti if gecerli_var and e.bicim in ("online", "karma") else None,
            "baslangic": s.iso(e.baslangic), "bitis": s.iso(e.bitis), "saat_dilimi": e.saat_dilimi, "dil": e.dil,
            "oturumlar": s.json_yukle(e.oturumlar, []) or [], "organizator_ad": e.organizator_ad or "",
            "iade_politikasi": e.iade_politikasi or "", "odeme_notu": e.odeme_notu or "", "durum": e.durum,
        },
        "biletler": [{
            "kod": b.kod, "tur": turler[b.tur_id].ad if b.tur_id in turler else "—", "katilimci_ad": b.katilimci_ad,
            "durum": b.durum, "giris_at": s.iso(b.giris_at), "iade": b.iade,
            "qr": s.qr_icerigi(b.kod) if b.durum == "gecerli" else None,
            "qr_adresi": f"{taban}/qr/{b.kod}.svg" if b.durum == "gecerli" else None,
        } for b in biletler],
        "iptal_edilebilir": iptal_edilebilir, "iptal_son": s.iso(son),
        "pdf_adresi": f"{taban}/bilet.pdf" if gecerli_var else None,
        "ics_adresi": f"{taban}/takvim.ics" if gecerli_var else None,
    }
    if gecerli_var:
        veri["takvim"] = s.takvim_baglantilari(e, dil, adres, f"{s.site_adresi()}{taban}/takvim.ics")
    return veri


@bilet_router.get("/{jeton}")
async def bilet_sayfasi(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    sp, e = await _bilet_jetonlu(db, request, jeton)
    return JSONResponse(await _bilet_sozlugu(db, sp, e, jeton), headers={**ACIK_BASLIKLAR, "X-Robots-Tag": "noindex"})


@bilet_router.get("/{jeton}/qr/{kod}.svg")
async def bilet_qr(jeton: str, kod: str, request: Request, db: AsyncSession = Depends(get_db)):
    sp, e = await _bilet_jetonlu(db, request, jeton)
    b = (await db.execute(select(EtkinlikBiletleri).where(EtkinlikBiletleri.siparis_id == sp.id,
                                                          EtkinlikBiletleri.kod == (kod or "").upper()))).scalars().first()
    if b is None or b.durum != "gecerli":
        raise _hata(404, "bulunamadi")
    g = _qr_gorsel(s.qr_icerigi(b.kod), "svg")
    return Response(g.veri, media_type="image/svg+xml", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    })


@bilet_router.get("/{jeton}/bilet.pdf")
async def bilet_pdf(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    sp, e = await _bilet_jetonlu(db, request, jeton)
    biletler = [b for b in await k.siparis_biletleri(db, sp.id) if b.durum == "gecerli"]
    if not biletler:
        raise _hata(404, "bilet_yok")
    turler = {t.id: t.ad for t in await k.tur_listesi(db, e.id)}
    veri = s.bilet_pdf(e, sp, [(b, turler.get(b.tur_id, "—")) for b in biletler], sp.dil if sp.dil in s.DILLER else e.dil)
    return Response(veri, media_type="application/pdf", headers={
        "Content-Disposition": icerik_konumu(f"bilet-{sp.kod}.pdf"), "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex",
    })


@bilet_router.get("/{jeton}/takvim.ics")
async def bilet_takvim(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    sp, e = await _bilet_jetonlu(db, request, jeton)
    gecerli = any(b.durum == "gecerli" for b in await k.siparis_biletleri(db, sp.id))
    dil = sp.dil if sp.dil in s.DILLER else e.dil
    metin_ = s.ics_uret(e, sp.kod, dil, iptal=not gecerli or e.durum == "iptal", sira_no=0 if gecerli else 1,
                        bilet_adresi_=s.bilet_adresi(e.slug, jeton))
    return Response(metin_, media_type="text/calendar; charset=utf-8", headers={
        "Content-Disposition": icerik_konumu(f"etkinlik-{e.slug}.ics"), "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex",
    })


@bilet_router.post("/{jeton}/iptal")
async def bilet_iptal(jeton: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request, 4096)
    sp, e = await _bilet_jetonlu(db, request, jeton)
    if e.durum != "yayinda":
        raise _hata(409, "iptal_edilemez")
    son = _iptal_sonu(e)
    if s.simdi() >= son:
        raise _hata(409, "iptal_suresi_gecti", son=s.iso(son))
    biletler = [b for b in await k.siparis_biletleri(db, sp.id) if b.durum != "iptal"]
    kodlar = govde.get("kodlar")
    if isinstance(kodlar, list) and kodlar:
        istenen = {str(x).upper() for x in kodlar}
        biletler = [b for b in biletler if b.kod in istenen]
    if not biletler:
        raise _hata(409, "zaten_iptal")
    if any(b.giris_at for b in biletler):
        raise _hata(409, "giris_yapilmis")
    await k.biletleri_iptal_et(db, e, biletler, "katilimci")
    if sp.durum == "iptal" and sp.odeme_jeton:
        from models.payments import Payments

        for p in (await db.execute(select(Payments).where(Payments.jeton == sp.odeme_jeton, Payments.durum == "bekliyor"))).scalars().all():
            p.durum = "iptal"
    await db.commit()
    arka.add_task(k.iptal_epostasi, sp.id)
    arka.add_task(k.sahip_bildirimi, sp.id, k.SAHIP_IPTAL)
    arka.add_task(_davet_arka_plan, e.id)
    await db.refresh(sp)
    return JSONResponse(await _bilet_sozlugu(db, sp, e, jeton), headers=ACIK_BASLIKLAR)


# ---------------------------------------------------------------------------
# Görevli (kapı) bağlantısı — giriş yapmadan yalnız okutma
# ---------------------------------------------------------------------------
async def _gorevli(db: AsyncSession, jeton: str) -> Etkinlikler:
    coz = s.gorevli_jetonu_coz(jeton)
    if coz is None:
        raise _hata(404, "baglanti_gecersiz")
    eid, surum, son = coz
    e = (await db.execute(select(Etkinlikler).where(Etkinlikler.id == eid))).scalars().first()
    if e is None or int(e.gorevli_surumu or 1) != surum:
        raise _hata(404, "baglanti_gecersiz")
    if s.simdi() > son:
        raise _hata(410, "baglanti_suresi_doldu")
    if e.hesap_email and not await _yayinda_mi(db, e):
        raise _hata(410, "etkinlik_pasif")
    return e


@giris_router.get("/{jeton}")
async def gorevli_ozeti(jeton: str, db: AsyncSession = Depends(get_db)):
    e = await _gorevli(db, jeton)
    coz = s.gorevli_jetonu_coz(jeton)
    return JSONResponse({
        "etkinlik": {"baslik": e.baslik, "baslangic": s.iso(e.baslangic), "bitis": s.iso(e.bitis), "saat_dilimi": e.saat_dilimi,
                     "dil": e.dil, "renk": e.renk, "durum": e.durum, "kapak": s.kapak_adresi(e.kapak)},
        "son": s.iso(coz[2]) if coz else None, "sayac": await k.sayac(db, e),
    }, headers={**ACIK_BASLIKLAR, "X-Robots-Tag": "noindex"})


@giris_router.post("/{jeton}/okut")
async def gorevli_okut(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request, 4096)
    _hiz(_okut_hizi, f"gorevli|{(jeton or '')[:60]}")
    e = await _gorevli(db, jeton)
    sonuc = await k.okut(db, e, govde.get("kod"), kaynak="gorevli", yapan="gorevli",
                         cevrimdisi=govde.get("cevrimdisi") is True, istemci_zaman=_istemci_zamani(govde.get("zaman")))
    return JSONResponse(sonuc, headers=ACIK_BASLIKLAR)


@giris_router.get("/{jeton}/sayac")
async def gorevli_sayac(jeton: str, db: AsyncSession = Depends(get_db)):
    e = await _gorevli(db, jeton)
    return JSONResponse(await k.sayac(db, e), headers=ACIK_BASLIKLAR)


# ---------------------------------------------------------------------------
# Kapak (herkese açık, değişmez) ve hesabın etkinlik listesi
# ---------------------------------------------------------------------------
@gorsel_router.get("/{anahtar}")
async def gorsel(anahtar: str, db: AsyncSession = Depends(get_db)):
    if len(anahtar) > 64:
        raise _hata(404, "bulunamadi")
    g = (await db.execute(select(EtkinlikGorselleri).where(EtkinlikGorselleri.anahtar == anahtar))).scalars().first()
    if g is None:
        raise _hata(404, "bulunamadi")
    from services import dosya_deposu

    try:
        veri = await dosya_deposu.oku(db, g.depo, f"etkinlik/{g.anahtar}.webp")
    except dosya_deposu.DepoHatasi:
        raise _hata(404, "bulunamadi")
    return Response(veri, media_type="image/webp", headers={
        "Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
    })


@liste_router.get("/{slug}")
async def hesap_listesi(slug: str, gecmis: bool = Query(False), db: AsyncSession = Depends(get_db)):
    temiz = (slug or "").strip().lower()
    if not s.SLUG_DESENI.match(temiz):
        raise _hata(404, "liste_yok")
    l_ = (await db.execute(select(EtkinlikListeleri).where(EtkinlikListeleri.slug == temiz))).scalars().first()
    if l_ is None or not l_.acik:
        raise _hata(404, "liste_yok")
    if l_.hesap_email:
        from services import moduller as modul_servisi

        if not await modul_servisi.modul_acik_mi(db, l_.hesap_email, MODUL):
            raise _hata(410, "liste_pasif")
    an = s.simdi()
    kosul = Etkinlikler.hesap_email.is_(None) if l_.hesap_email is None else Etkinlikler.hesap_email == l_.hesap_email
    sorgu = select(Etkinlikler).where(kosul, Etkinlikler.listede_goster.is_(True),
                                      Etkinlikler.durum.in_(("yayinda", "tamamlandi", "iptal")))
    sorgu = sorgu.where(Etkinlikler.bitis < an).order_by(Etkinlikler.baslangic.desc()) if gecmis else \
        sorgu.where(Etkinlikler.bitis >= an).order_by(Etkinlikler.baslangic)
    kayitlar = (await db.execute(sorgu.limit(100))).scalars().all()
    ogeler = []
    for e in kayitlar:
        d = await k.doluluk(db, e)
        kalan = d.kalan(e)
        ogeler.append({"slug": e.slug, "baslik": e.baslik, "ozet": e.ozet or "", "kapak": s.kapak_adresi(e.kapak), "renk": e.renk,
                       "bicim": e.bicim, "mekan_adi": e.mekan_adi or "", "baslangic": s.iso(e.baslangic), "bitis": s.iso(e.bitis),
                       "saat_dilimi": e.saat_dilimi, "durum": e.durum, "dolu": kalan is not None and kalan <= 0,
                       "ucretsiz": all(int(t.fiyat or 0) == 0 for t in await k.tur_listesi(db, e.id) if t.aktif and not t.gizli)})
    return JSONResponse({"slug": l_.slug, "baslik": l_.baslik, "aciklama": l_.aciklama or "", "adres_url": s.liste_adresi(l_.slug),
                         "etkinlikler": ogeler, "gecmis": gecmis},
                        headers={"Cache-Control": "public, max-age=60", "X-Content-Type-Options": "nosniff"})


# Yönetici ve müşteri router'ları ÖNCE; sabit önekli herkese açıklar (bilet, giriş, görsel)
# genel `/{slug}` kalıbından önce.
router = (yonetici_router, musteri_router, bilet_router, giris_router, gorsel_router, liste_router, acik_router)
