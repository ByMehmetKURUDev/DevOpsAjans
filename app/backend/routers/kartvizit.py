"""Faz 4K — Dijital kartvizit ve bio link.

Herkese açık (`/api/v1/kart`; site tarafında SPA `/kart/<slug>` ve paylaşım
önizlemesi için `functions/kart/[slug].js`):
  GET  "/gorsel/{anahtar}.webp|.jpg"  kart görseli (WebP; paylaşım önizlemesi için JPEG)
  GET  "/{adres}"                     kart (adres = slug | eski slug → {yonlendir} | değişmez kod).
                                      Parolalıysa {durum: kilitli} (kişisel bilgi yok). Pasif /
                                      modülü kapalı → 410, yok → 404. Görüntülenme sayılır.
  GET  "/{adres}/ozet"                paylaşım önizlemesi özeti (başlık, açıklama, görsel, robots);
                                      parolalı kartta kişisel bilgi YOK. Sayılmaz.
  POST "/{adres}/parola"              {parola} → {jeton (2 saat), kart}; IP+kart başı hız sınırı
  GET  "/{adres}/rehber.vcf?j="       vCard 3.0 (4Q üreticisi; fotoğraf ≤ 40 KB gömülü)
  GET  "/{adres}/qr.png|qr.svg?j="    kartın QR'ı (değişmez kodlu adres; logo ortada)
  POST "/{adres}/olay"                {tur: tik|paylas, hedef, j} (sendBeacon: text/plain)
  POST "/{adres}/mesaj"               iletişim bırak formu: hız sınırı + bal küpü + imzalı form jetonu

Yönetici (`/api/v1/kartvizit/yonetim`) — ajansın kendi kartları + müşterilerinki:
Müşteri (`/api/v1/kartvizitlerim`; modül `dijital_kartvizit` açık + ekip izni `kartvizit`):
  GET    "/meta"                       şablonlar, platformlar, sınırlar, kart hakkı
  GET    "/slug-uygun?slug=&haric_id="  slug uygun mu (+ öneri)
  GET    "/mesajlar?kart_id=&okunmamis=" gelen "iletişim bırak" mesajları
  PUT    "/mesajlar/{id}"              {okundu}
  DELETE "/mesajlar/{id}"              çöp kutusuna
  GET    ""                            liste (+ son 30 gün sayıları; yönetici ?hesap=ajans|e-posta)
  POST   ""                            oluştur
  GET    "/{id}"  PUT "/{id}"  DELETE "/{id}"
  POST   "/{id}/gorsel"                çok parçalı {tur: foto|logo|kapak|galeri, dosya}
  DELETE "/{id}/gorsel/{gorsel_id}"
  PUT    "/{id}/galeri-sira"           {idler}
  GET    "/{id}/analiz?gun=30"
  GET    "/{id}/qr?bicim=png|svg"

Mesajlar: ajansın KENDİ kartından gelen mesaj CRM'e aday olarak da düşüyor
(CRM yalnız ajansın satış hunisi — `services/crm.py`). Müşteri kartlarının
mesajları CRM'e karışmıyor; müşterinin panelinde "Kart mesajları" listesinde
duruyor ve `kartvizit_mesaj` bildirimi gidiyor (hesap sahibi + `kartvizit`
izinli ekip üyeleri).
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from models.kartvizit import KartvizitGorselleri, KartvizitMesajlari, Kartvizitler
from services import dinamik_qr as qr
from services import kartvizit as k
from services import kartvizit_kayit as kk
from services.dosya_deposu import icerik_konumu
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver

logger = logging.getLogger(__name__)

MODUL = "dijital_kartvizit"
IZIN = "kartvizit"
VARSAYILAN_KART_SINIRI = 5
KART_OLAYLARI = ("goruntulenme", "rehber", "tik", "form", "paylas")

acik_router = APIRouter(prefix="/api/v1/kart", tags=["kartvizit"])
yonetici_router = APIRouter(
    prefix="/api/v1/kartvizit/yonetim", tags=["kartvizit"], dependencies=[Depends(yonetici_gerekli)]
)
musteri_router = APIRouter(
    prefix="/api/v1/kartvizitlerim",
    tags=["kartvizit"],
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(IZIN))],
)

#: Kişi başı: dakikada 60 yazma, 30 görsel yükleme.
_yazma_hizi = HizSiniri(60, 60.0)
_gorsel_hizi = HizSiniri(30, 60.0)
#: Herkese açık: aynı IP + kart dakikada 30 görüntülenme kaydı (sayfa yine açılır),
#: IP başı dakikada 60 olay, parola denemesi IP+kart başı dakikada 5,
#: form IP+kart başı 10 dakikada 3 ve IP başı saatte 10.
#: Faz 7H: parola ve form sayaçları veritabanında (sunucu uyanınca sıfırlanmıyor); görüntülenme /
#: olay sayaçları yalnız tekrar süzgeci, bellekte kalıyor.
_gorunum_hizi = HizSiniri(30, 60.0)
_olay_hizi = HizSiniri(60, 60.0)
_parola_hizi = KaliciHizSiniri("kart-parola", 5, 60.0)
_form_hizi = KaliciHizSiniri("kart-form", 3, 600.0)
_form_ip_hizi = KaliciHizSiniri("kart-form-ip", 10, 3600.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _gorsel_hizi, _gorunum_hizi, _olay_hizi, _parola_hizi, _form_hizi, _form_ip_hizi):
        h.temizle()


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


def _kart_hatasi(h: k.KartHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _hiz(sinir: HizSiniri, anahtar: str) -> None:
    if not sinir.izin_var_mi(anahtar or "anonim"):
        raise _hata(429, "cok_hizli")


async def _kalici_hiz(*denemeler) -> None:
    """Faz 7H: herkese açık uçların veritabanı destekli sayacı ((sınırlayıcı, anahtar) çiftleri)."""
    if not await izin_ver(*denemeler):
        raise _hata(429, "cok_hizli")


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def _tema(kart: Kartvizitler) -> Dict[str, Any]:
    return {**k.VARSAYILAN_TEMA, **k.json_yukle(kart.tema)}


def tema_ozel_mi(kart: Kartvizitler) -> bool:
    """Faz 4L: kartın kendi teması varsayılandan farklı mı (o zaman marka temasının önünde)."""
    return _tema(kart) != k.VARSAYILAN_TEMA


async def _marka(db: AsyncSession, kart: Kartvizitler) -> Dict[str, Any]:
    from services.marka import acik_marka

    return await acik_marka(db, kart.hesap_email, sayfa_ozel=tema_ozel_mi(kart))


def _gorsel_haritasi(satirlar: List[KartvizitGorselleri], kart: Kartvizitler) -> Dict[str, Any]:
    by_id = {g.id: g for g in satirlar}
    return {
        "foto": kk.gorsel_sozlugu(by_id.get(kart.foto_id)),
        "logo": kk.gorsel_sozlugu(by_id.get(kart.logo_id)),
        "kapak": kk.gorsel_sozlugu(by_id.get(kart.kapak_id)),
        "galeri": [kk.gorsel_sozlugu(g) for g in sorted(
            (g for g in satirlar if g.tur == "galeri"), key=lambda g: (g.sira, g.id))],
    }


def _panel_sozlugu(kart: Kartvizitler, gorseller: List[KartvizitGorselleri], sayilar: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    return {
        "id": kart.id,
        "kod": kart.kod,
        "slug": kart.slug,
        "duzen": kart.duzen,
        "dil": kart.dil,
        "ad_soyad": kart.ad_soyad,
        "unvan": kart.unvan,
        "sirket": kart.sirket,
        "icerik": k.json_yukle(kart.icerik),
        "tema": _tema(kart),
        **_gorsel_haritasi(gorseller, kart),
        "aktif": bool(kart.aktif),
        "form_acik": bool(kart.form_acik),
        "index_acik": bool(kart.index_acik),
        "sifreli": bool(kart.sifre_ozet),
        "hesap_email": kart.hesap_email,
        "olusturan_email": kart.olusturan_email,
        "kart_adresi": k.kart_adresi(kart.slug),
        "qr_adresi": k.kart_adresi(kart.kod),
        "son30": sayilar or {},
        "created_at": k.iso(kart.created_at),
        "updated_at": k.iso(kart.updated_at),
    }


def _acik_sozluk(kart: Kartvizitler, gorseller: List[KartvizitGorselleri]) -> Dict[str, Any]:
    """Herkese açık kart (yalnız kartta görünen alanlar; sahip/oluşturan e-postası yok)."""
    a = k.json_yukle(kart.icerik)
    adres = a.get("adres") or ""
    saatler = a.get("calisma_saatleri") or {}
    return {
        "durum": "aktif",
        "slug": kart.slug,
        "kod": kart.kod,
        "duzen": kart.duzen,
        "dil": kart.dil,
        "tema": _tema(kart),
        "ad_soyad": a.get("ad_soyad") or kart.ad_soyad,
        "unvan": a.get("unvan") or "",
        "sirket": a.get("sirket") or "",
        "tanitim": a.get("tanitim") or "",
        "adres": adres,
        "harita_url": a.get("harita_url") or (k.harita_adresi(adres) if adres else ""),
        "telefonlar": [
            {**t, "tel": k.tel_adresi(t.get("numara", ""))} for t in a.get("telefonlar") or [] if t.get("numara")
        ],
        "eposta": a.get("eposta") or "",
        "webler": a.get("webler") or [],
        "whatsapp_url": k.whatsapp_adresi(a["whatsapp"]) if a.get("whatsapp") else "",
        "sosyal": a.get("sosyal") or [],
        "baglantilar": a.get("baglantilar") or [],
        "hizmetler": a.get("hizmetler") or [],
        "calisma_saatleri": saatler if saatler.get("goster") else None,
        **_gorsel_haritasi(gorseller, kart),
        "form": {
            "acik": bool(kart.form_acik),
            "jeton": k.form_jetonu_uret("kart", kart.id) if kart.form_acik else None,
            "aydinlatma_adresi": k.aydinlatma_adresi(kart.dil),
        },
        "kart_adresi": k.kart_adresi(kart.slug),
        "index": bool(kart.index_acik),
        "vcard_adresi": f"/api/v1/kart/{kart.slug}/rehber.vcf",
        "qr_adresi": f"/api/v1/kart/{kart.slug}/qr.png",
    }


def _kilitli_sozluk(kart: Kartvizitler) -> Dict[str, Any]:
    return {"durum": "kilitli", "slug": kart.slug, "dil": kart.dil, "tema": _tema(kart), "index": False}


# ---------------------------------------------------------------------------
# Panel işleri
# ---------------------------------------------------------------------------
async def _kart(db: AsyncSession, kart_id: int, kapsam: Kapsam) -> Kartvizitler:
    sorgu = select(Kartvizitler).where(Kartvizitler.id == kart_id)
    if not kapsam.yonetici:
        sorgu = sorgu.where(Kartvizitler.hesap_email == kapsam.hesap)
    kart = (await db.execute(sorgu)).scalars().first()
    if kart is None:
        raise _hata(404, "bulunamadi")
    return kart


async def _kart_siniri(db: AsyncSession, kapsam: Kapsam) -> Optional[int]:
    if kapsam.yonetici:
        return None
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, kapsam.hesap or "", MODUL, "kart_siniri")
    return int(deger) if isinstance(deger, int) else VARSAYILAN_KART_SINIRI


async def _kart_sayisi(db: AsyncSession, hesap: Optional[str]) -> int:
    sorgu = select(func.count(Kartvizitler.id))
    sorgu = sorgu.where(Kartvizitler.hesap_email.is_(None)) if hesap is None else sorgu.where(Kartvizitler.hesap_email == hesap)
    return int((await db.execute(sorgu)).scalar() or 0)


def _hedef_hesap(kapsam: Kapsam, govde: Dict[str, Any]) -> Optional[str]:
    """Kartın sahibi: müşteride etkin hesap; yöneticide isteğe bağlı müşteri e-postası (boş = ajans)."""
    if not kapsam.yonetici:
        return kapsam.hesap
    ham = (govde.get("hesap_email") or "").strip().lower()
    if not ham:
        return None
    if not qr.eposta_dogru_mu(ham):
        raise k.KartHatasi("eposta_gecersiz", "hesap_email")
    return ham


def _duzen(ham: Any) -> str:
    deger = ham or "kartvizit"
    if deger not in k.DUZENLER:
        raise k.KartHatasi("duzen_gecersiz", "duzen")
    return deger


async def _olustur(db: AsyncSession, kapsam: Kapsam, govde: Dict[str, Any]) -> Dict[str, Any]:
    _hiz(_yazma_hizi, kapsam.kisi)
    try:
        icerik = k.icerik_dogrula(govde.get("icerik"))
        tema = k.tema_dogrula(govde.get("tema"))
        duzen = _duzen(govde.get("duzen"))
        dil = k.dil_duzelt(govde.get("dil"))
        sifre = k.sifre_dogrula(govde.get("sifre"))
        hesap = _hedef_hesap(kapsam, govde)
        slug = k.slug_duzelt(govde["slug"]) if govde.get("slug") else None
    except k.KartHatasi as e:
        raise _kart_hatasi(e)
    sinir = await _kart_siniri(db, kapsam)
    if sinir is not None and await _kart_sayisi(db, hesap) >= sinir:
        raise _hata(409, "kart_siniri", sinir=sinir)
    if slug is None:
        slug = await kk.slug_onerisi(db, "kart", icerik["ad_soyad"])
    elif not await kk.slug_bos_mu(db, "kart", slug):
        raise _hata(409, "slug_kullaniliyor", alan="slug")
    try:
        kod = await kk.benzersiz_kod(db, "kart")
    except k.KartHatasi as e:
        raise _kart_hatasi(e)
    ozet, tuz = (None, None)
    if sifre:
        from services.dosyalar import sifre_ozetle

        ozet, tuz = sifre_ozetle(sifre)
    kart = Kartvizitler(
        hesap_email=hesap,
        olusturan_email=kapsam.kisi or None,
        kod=kod,
        slug=slug,
        duzen=duzen,
        dil=dil,
        ad_soyad=icerik["ad_soyad"],
        unvan=icerik["unvan"] or None,
        sirket=icerik["sirket"] or None,
        icerik=k.json_dok(icerik),
        tema=k.json_dok(tema),
        aktif=govde.get("aktif") is not False,
        form_acik=govde.get("form_acik") is not False,
        index_acik=bool(govde.get("index_acik")),
        sifre_ozet=ozet,
        sifre_tuz=tuz,
    )
    db.add(kart)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "slug_kullaniliyor", alan="slug")
    await db.refresh(kart)
    return _panel_sozlugu(kart, [])


async def _guncelle(db: AsyncSession, kapsam: Kapsam, kart: Kartvizitler, govde: Dict[str, Any]) -> Dict[str, Any]:
    _hiz(_yazma_hizi, kapsam.kisi)
    try:
        if "icerik" in govde:
            icerik = k.icerik_dogrula(govde.get("icerik"))
            kart.icerik = k.json_dok(icerik)
            kart.ad_soyad = icerik["ad_soyad"]
            kart.unvan = icerik["unvan"] or None
            kart.sirket = icerik["sirket"] or None
        if "tema" in govde:
            kart.tema = k.json_dok(k.tema_dogrula(govde.get("tema")))
        if "duzen" in govde:
            kart.duzen = _duzen(govde.get("duzen"))
        if "dil" in govde:
            kart.dil = k.dil_duzelt(govde.get("dil"))
        for alan in ("aktif", "form_acik", "index_acik"):
            if alan in govde:
                setattr(kart, alan, bool(govde.get(alan)))
        if govde.get("sifre_kaldir"):
            kart.sifre_ozet = kart.sifre_tuz = None
        elif govde.get("sifre"):
            sifre = k.sifre_dogrula(govde.get("sifre"))
            if sifre:
                from services.dosyalar import sifre_ozetle

                kart.sifre_ozet, kart.sifre_tuz = sifre_ozetle(sifre)
        if govde.get("slug") and govde.get("slug") != kart.slug:
            yeni = k.slug_duzelt(govde.get("slug"))
            if not await kk.slug_bos_mu(db, "kart", yeni, haric_id=kart.id):
                raise _hata(409, "slug_kullaniliyor", alan="slug")
            await kk.slug_degistir(db, "kart", kart, yeni)
    except k.KartHatasi as e:
        await db.rollback()
        raise _kart_hatasi(e)
    except HTTPException:
        await db.rollback()
        raise
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "slug_kullaniliyor", alan="slug")
    await db.refresh(kart)
    return _panel_sozlugu(kart, await kk.gorseller(db, "kart", kart.id))


async def _liste(db: AsyncSession, kapsam: Kapsam, ara: Optional[str], hesap: Optional[str]) -> Dict[str, Any]:
    sorgu = select(Kartvizitler)
    if not kapsam.yonetici:
        sorgu = sorgu.where(Kartvizitler.hesap_email == kapsam.hesap)
    elif hesap == "ajans":
        sorgu = sorgu.where(Kartvizitler.hesap_email.is_(None))
    elif hesap:
        sorgu = sorgu.where(Kartvizitler.hesap_email == hesap.strip().lower())
    if ara and ara.strip():
        from sqlalchemy import or_

        desen = f"%{ara.strip()[:80].lower()}%"
        sorgu = sorgu.where(or_(
            func.lower(Kartvizitler.ad_soyad).like(desen), func.lower(Kartvizitler.slug).like(desen),
            func.lower(Kartvizitler.sirket).like(desen), func.lower(Kartvizitler.unvan).like(desen),
            func.lower(Kartvizitler.hesap_email).like(desen),
        ))
    kartlar = (await db.execute(sorgu.order_by(desc(Kartvizitler.created_at), desc(Kartvizitler.id)).limit(500))).scalars().all()
    idler = [x.id for x in kartlar]
    sayilar = await kk.donem_sayilari(db, "kart", idler)
    gorsel_satirlari: Dict[int, List[KartvizitGorselleri]] = {}
    foto_idler = [x.foto_id for x in kartlar if x.foto_id]
    if foto_idler:
        for g in (await db.execute(select(KartvizitGorselleri).where(KartvizitGorselleri.id.in_(foto_idler)))).scalars():
            gorsel_satirlari.setdefault(g.sahip_id, []).append(g)
    okunmamis = dict(
        (int(sid), int(n))
        for sid, n in (
            await db.execute(
                select(KartvizitMesajlari.sahip_id, func.count(KartvizitMesajlari.id))
                .where(KartvizitMesajlari.sahip_tur == "kart", KartvizitMesajlari.sahip_id.in_(idler or [0]),
                       KartvizitMesajlari.okundu.is_(False))
                .group_by(KartvizitMesajlari.sahip_id)
            )
        ).all()
    )
    ogeler = []
    for kart in kartlar:
        d = _panel_sozlugu(kart, gorsel_satirlari.get(kart.id, []), sayilar.get(kart.id))
        d["okunmamis"] = okunmamis.get(kart.id, 0)
        ogeler.append(d)
    return {"toplam": len(ogeler), "items": ogeler}


async def _gorsel_yukle(db: AsyncSession, kapsam: Kapsam, kart: Kartvizitler, tur: str, dosya: UploadFile) -> Dict[str, Any]:
    _hiz(_gorsel_hizi, kapsam.kisi)
    if tur not in k.GORSEL_TURLERI_KART:
        raise _hata(400, "gorsel_turu_gecersiz", alan="tur")
    bayt = await dosya.read(k.GORSEL_EN_COK_BAYT + 1)
    mevcut = await kk.gorseller(db, "kart", kart.id)
    galeri = [g for g in mevcut if g.tur == "galeri"]
    if tur == "galeri" and len(galeri) >= k.EN_COK["galeri"]:
        raise _hata(409, "galeri_dolu", en_cok=k.EN_COK["galeri"])
    try:
        sira = (max((g.sira for g in galeri), default=0) + 1) if tur == "galeri" else 0
        yeni = await kk.gorsel_kaydet(
            db, hesap=kart.hesap_email, sahip_tur="kart", sahip_id=kart.id, tur=tur, bayt=bayt, sira=sira
        )
    except k.KartHatasi as e:
        await db.rollback()
        raise _kart_hatasi(e)
    if tur != "galeri":
        alan = f"{tur}_id"
        eski = next((g for g in mevcut if g.id == getattr(kart, alan)), None)
        setattr(kart, alan, yeni.id)
        if eski is not None:
            await kk.gorsel_sil(db, eski)
    await db.commit()
    await db.refresh(kart)
    return _panel_sozlugu(kart, await kk.gorseller(db, "kart", kart.id))


async def _gorsel_kaldir(db: AsyncSession, kart: Kartvizitler, gorsel_id: int) -> Dict[str, Any]:
    satir = (
        await db.execute(
            select(KartvizitGorselleri).where(
                KartvizitGorselleri.id == gorsel_id, KartvizitGorselleri.sahip_tur == "kart",
                KartvizitGorselleri.sahip_id == kart.id,
            )
        )
    ).scalars().first()
    if satir is None:
        raise _hata(404, "bulunamadi")
    for alan in ("foto_id", "logo_id", "kapak_id"):
        if getattr(kart, alan) == satir.id:
            setattr(kart, alan, None)
    await kk.gorsel_sil(db, satir)
    await db.commit()
    await db.refresh(kart)
    return _panel_sozlugu(kart, await kk.gorseller(db, "kart", kart.id))


async def _galeri_sira(db: AsyncSession, kart: Kartvizitler, govde: Dict[str, Any]) -> Dict[str, Any]:
    idler = govde.get("idler")
    if not isinstance(idler, list):
        raise _hata(400, "gecersiz", alan="idler")
    galeri = {g.id: g for g in await kk.gorseller(db, "kart", kart.id) if g.tur == "galeri"}
    try:
        sirali = [int(x) for x in idler]
    except (TypeError, ValueError):
        raise _hata(400, "gecersiz", alan="idler")
    if set(sirali) != set(galeri) or len(sirali) != len(galeri):
        raise _hata(400, "gecersiz", alan="idler")
    for i, gid in enumerate(sirali, start=1):
        galeri[gid].sira = i
    await db.commit()
    await db.refresh(kart)
    return _panel_sozlugu(kart, await kk.gorseller(db, "kart", kart.id))


async def _sil(db: AsyncSession, kart: Kartvizitler) -> None:
    # Görseller kartla aynı işlemde silinir: çöp kutusu birlikte yakalar, birlikte
    # geri getirir; içerikleri çöp kaydı kalıcı silinene kadar duruyor.
    # Eski slug kilitleri önce (Core silme otomatik flush yapar; görseller kartla AYNI
    # flush'ta silinmeli ki çöp kutusu çocuk tabloyu ebeveyniyle birlikte yakalasın).
    await kk.eski_sluglari_sil(db, "kart", kart.id)
    for g in await kk.gorseller(db, "kart", kart.id):
        await db.delete(g)
    await db.delete(kart)
    await db.commit()


def _hedef_etiketleri(icerik: Dict[str, Any]) -> Dict[str, str]:
    """Tıklama hedef anahtarı → okunur etiket (analiz tablosu için)."""
    e: Dict[str, str] = {"wa": "WhatsApp", "eposta": icerik.get("eposta") or "e-posta", "harita": "Harita"}
    for b in icerik.get("baglantilar") or []:
        e[f"l:{b['id']}"] = b.get("baslik") or b.get("url")
    for i, t in enumerate(icerik.get("telefonlar") or []):
        e[f"tel:{i}"] = t.get("numara") or ""
    for i, w in enumerate(icerik.get("webler") or []):
        e[f"web:{i}"] = w.get("etiket") or w.get("url") or ""
    for s_ in icerik.get("sosyal") or []:
        e[f"s:{s_['platform']}"] = s_["platform"]
    return e


async def _analiz(db: AsyncSession, kart: Kartvizitler, gun: int) -> Dict[str, Any]:
    sonuc = await kk.analiz(db, "kart", kart.id, gun, KART_OLAYLARI)
    etiketler = _hedef_etiketleri(k.json_yukle(kart.icerik))
    for h in sonuc["hedefler"]:
        h["etiket"] = etiketler.get(h["hedef"])
    return sonuc


async def _qr_gorseli(db: AsyncSession, kart: Kartvizitler, bicim: str, boyut: Optional[int] = None) -> qr.Gorsel:
    tasarim = dict(qr.VARSAYILAN_TASARIM)
    if boyut:
        tasarim["boyut"] = boyut
    renk = _tema(kart).get("renk") or "#000000"
    if qr.kontrast_orani(renk, "#ffffff") >= 4.5:
        tasarim["on_renk"] = renk
    tasarim = qr.tasarim_duzelt(tasarim)
    logo = None
    satir = await kk.gorsel_bul(db, kart.logo_id)
    if satir is not None:
        try:
            logo = k.png_b64(await kk.gorsel_icerigi(db, satir))
        except Exception:  # noqa: BLE001 - logo okunamazsa logosuz QR
            logo = None
    icerik = k.kart_adresi(kart.kod)
    return (qr.png_ciz if bicim == "png" else qr.svg_ciz)(icerik, tasarim, logo)


def _qr_yaniti(g: qr.Gorsel, slug: str, bicim: str, indir: bool = True) -> Response:
    basliklar = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if indir:
        basliklar["Content-Disposition"] = icerik_konumu(f"kartvizit-{slug}-qr.{bicim}")
    return Response(g.veri, media_type=g.tur, headers=basliklar)


def _mesaj_sozlugu(m: KartvizitMesajlari, baslik: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": m.id,
        "sahip_tur": m.sahip_tur,
        "sahip_id": m.sahip_id,
        "sahip_baslik": baslik,
        "ad": m.ad,
        "eposta": m.eposta,
        "telefon": m.telefon,
        "mesaj": m.mesaj,
        "dil": m.dil,
        "okundu": bool(m.okundu),
        "crm_aday_id": m.crm_aday_id,
        "hesap_email": m.hesap_email,
        "created_at": k.iso(m.created_at),
    }


async def mesaj_listesi(
    db: AsyncSession, sahip_tur: str, model: Any, baslik_alani: str, yonetici: bool, hesap: Optional[str],
    sahip_id: Optional[int], okunmamis: Optional[bool], hesap_suzgeci: Optional[str],
) -> Dict[str, Any]:
    """Kart mesajları / yorum geri bildirimleri (iki router da kullanıyor)."""
    M = KartvizitMesajlari
    sorgu = select(M).where(M.sahip_tur == sahip_tur)
    if not yonetici:
        sorgu = sorgu.where(M.hesap_email == hesap)
    elif hesap_suzgeci == "ajans":
        sorgu = sorgu.where(M.hesap_email.is_(None))
    elif hesap_suzgeci:
        sorgu = sorgu.where(M.hesap_email == hesap_suzgeci.strip().lower())
    if sahip_id:
        sorgu = sorgu.where(M.sahip_id == sahip_id)
    if okunmamis:
        sorgu = sorgu.where(M.okundu.is_(False))
    satirlar = (await db.execute(sorgu.order_by(desc(M.created_at), desc(M.id)).limit(500))).scalars().all()
    idler = {m.sahip_id for m in satirlar}
    basliklar = dict(
        (await db.execute(select(model.id, getattr(model, baslik_alani)).where(model.id.in_(list(idler) or [0])))).all()
    )
    return {
        "items": [_mesaj_sozlugu(m, basliklar.get(m.sahip_id)) for m in satirlar],
        "okunmamis": sum(1 for m in satirlar if not m.okundu),
    }


async def mesaj_bul(db: AsyncSession, sahip_tur: str, mesaj_id: int, yonetici: bool, hesap: Optional[str]) -> KartvizitMesajlari:
    M = KartvizitMesajlari
    sorgu = select(M).where(M.id == mesaj_id, M.sahip_tur == sahip_tur)
    if not yonetici:
        sorgu = sorgu.where(M.hesap_email == hesap)
    m = (await db.execute(sorgu)).scalars().first()
    if m is None:
        raise _hata(404, "bulunamadi")
    return m


def _meta(kapsam: Kapsam, sinir: Optional[int], sayi: Optional[int]) -> Dict[str, Any]:
    return {
        "duzenler": list(k.DUZENLER),
        "sablonlar": list(k.SABLONLAR),
        "sablon_renkleri": k.SABLON_RENKLERI,
        "yazi_tipleri": list(k.YAZI_TIPLERI),
        "koseler": list(k.KOSELER),
        "platformlar": list(k.PLATFORMLAR),
        "simgeler": list(k.SIMGELER),
        "gunler": list(k.GUNLER),
        "telefon_tipleri": list(k.TELEFON_TIPLERI),
        "diller": list(k.DILLER),
        "en_cok": k.EN_COK,
        "sinirlar": k.SINIR,
        "gorsel_en_cok_mb": k.GORSEL_EN_COK_BAYT // (1024 * 1024),
        "kart_tabani": k.kart_adresi(""),
        "eski_slug_gun": k.ESKI_SLUG_GUN,
        "kart_siniri": sinir,
        "kart_sayisi": sayi,
        "yonetici": kapsam.yonetici,
    }


# ---------------------------------------------------------------------------
# Uçlar — yönetici ve müşteri aynı işleyicileri kendi kapsamlarıyla kullanıyor.
# Sabit yollar `/{kart_id}`'den ÖNCE.
# ---------------------------------------------------------------------------
def _uclari_kur(router: APIRouter, kapsam_al: Callable[[Request], Kapsam]) -> None:
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        sinir = await _kart_siniri(db, kapsam)
        return _meta(kapsam, sinir, None if kapsam.yonetici else await _kart_sayisi(db, kapsam.hesap))

    @router.get("/slug-uygun")
    async def slug_uygun(
        request: Request,
        slug: str = Query(..., max_length=80),
        haric_id: Optional[int] = Query(None),
        ad: Optional[str] = Query(None, max_length=120),
        db: AsyncSession = Depends(get_db),
    ):
        kapsam = kapsam_al(request)
        if haric_id is not None:
            await _kart(db, haric_id, kapsam)
        oneri = await kk.slug_onerisi(db, "kart", ad or slug)
        try:
            temiz = k.slug_duzelt(slug)
        except k.KartHatasi as e:
            return {"uygun": False, "kod": e.kod, "oneri": oneri}
        if not await kk.slug_bos_mu(db, "kart", temiz, haric_id=haric_id):
            return {"uygun": False, "kod": "slug_kullaniliyor", "oneri": oneri}
        return {"uygun": True, "slug": temiz, "oneri": oneri}

    @router.get("/mesajlar")
    async def mesajlar(
        request: Request,
        kart_id: Optional[int] = Query(None),
        okunmamis: Optional[bool] = Query(None),
        hesap: Optional[str] = Query(None),
        db: AsyncSession = Depends(get_db),
    ):
        kapsam = kapsam_al(request)
        return await mesaj_listesi(
            db, "kart", Kartvizitler, "ad_soyad", kapsam.yonetici, kapsam.hesap, kart_id, okunmamis,
            hesap if kapsam.yonetici else None,
        )

    @router.put("/mesajlar/{mesaj_id}")
    async def mesaj_guncelle(mesaj_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        m = await mesaj_bul(db, "kart", mesaj_id, kapsam.yonetici, kapsam.hesap)
        if "okundu" in govde:
            m.okundu = bool(govde.get("okundu"))
        await db.commit()
        await db.refresh(m)
        return _mesaj_sozlugu(m)

    @router.delete("/mesajlar/{mesaj_id}")
    async def mesaj_sil(mesaj_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        m = await mesaj_bul(db, "kart", mesaj_id, kapsam.yonetici, kapsam.hesap)
        await db.delete(m)
        await db.commit()
        return {"ok": True}

    @router.get("")
    async def liste(
        request: Request,
        ara: Optional[str] = Query(None),
        hesap: Optional[str] = Query(None),
        db: AsyncSession = Depends(get_db),
    ):
        kapsam = kapsam_al(request)
        return await _liste(db, kapsam, ara, hesap if kapsam.yonetici else None)

    @router.post("")
    async def olustur(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        return await _olustur(db, kapsam_al(request), govde)

    @router.get("/{kart_id}")
    async def ayrinti(kart_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        kart = await _kart(db, kart_id, kapsam_al(request))
        return _panel_sozlugu(kart, await kk.gorseller(db, "kart", kart.id))

    @router.put("/{kart_id}")
    async def guncelle(kart_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _guncelle(db, kapsam, await _kart(db, kart_id, kapsam), govde)

    @router.delete("/{kart_id}")
    async def sil(kart_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        await _sil(db, await _kart(db, kart_id, kapsam_al(request)))
        return {"ok": True}

    @router.post("/{kart_id}/gorsel")
    async def gorsel_yukle(
        kart_id: int,
        request: Request,
        tur: str = Form(...),
        dosya: UploadFile = File(...),
        db: AsyncSession = Depends(get_db),
    ):
        kapsam = kapsam_al(request)
        return await _gorsel_yukle(db, kapsam, await _kart(db, kart_id, kapsam), tur, dosya)

    @router.delete("/{kart_id}/gorsel/{gorsel_id}")
    async def gorsel_kaldir(kart_id: int, gorsel_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        return await _gorsel_kaldir(db, await _kart(db, kart_id, kapsam_al(request)), gorsel_id)

    @router.put("/{kart_id}/galeri-sira")
    async def galeri_sira(kart_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        return await _galeri_sira(db, await _kart(db, kart_id, kapsam_al(request)), govde)

    @router.get("/{kart_id}/analiz")
    async def analiz(kart_id: int, request: Request, gun: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
        return await _analiz(db, await _kart(db, kart_id, kapsam_al(request)), gun)

    @router.get("/{kart_id}/qr")
    async def qr_indir(
        kart_id: int,
        request: Request,
        bicim: str = Query("png"),
        boyut: Optional[int] = Query(None, ge=qr.BOYUT_EN_AZ, le=qr.BOYUT_EN_COK),
        db: AsyncSession = Depends(get_db),
    ):
        if bicim not in ("png", "svg"):
            raise _hata(400, "bicim_gecersiz")
        kart = await _kart(db, kart_id, kapsam_al(request))
        try:
            g = await _qr_gorseli(db, kart, bicim, boyut)
        except k.KartHatasi as e:
            raise _kart_hatasi(e)
        return _qr_yaniti(g, kart.slug, bicim)


_uclari_kur(yonetici_router, _yonetici_kapsami)
_uclari_kur(musteri_router, _musteri_kapsami)


# ---------------------------------------------------------------------------
# Herkese açık
# ---------------------------------------------------------------------------
ACIK_BASLIKLAR = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


async def sahip_modulu_acik_mi(db: AsyncSession, hesap: Optional[str], modul: str) -> bool:
    """Ajansın kendi kaydı her zaman açık; müşterininki modülü açıksa."""
    if not hesap:
        return True
    from services import moduller

    try:
        return await moduller.modul_acik_mi(db, hesap, modul)
    except Exception:  # noqa: BLE001 - modül okunamazsa açık say (sayfa kırılmasın)
        return True


@dataclass
class AcikKart:
    kart: Optional[Kartvizitler]
    yonlendir: Optional[str]
    kanal: Optional[str]


async def _acik_kart(db: AsyncSession, adres: str) -> AcikKart:
    """Adres → etkin kart. Yok 404, pasif / modülü kapalı 410; eski slug → yönlendirme."""
    kart, yonlendir, kanal = await kk.cozumle(db, "kart", adres)
    if yonlendir:
        return AcikKart(None, yonlendir, None)
    if kart is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"}, headers=ACIK_BASLIKLAR)
    if not kart.aktif or not await sahip_modulu_acik_mi(db, kart.hesap_email, MODUL):
        raise HTTPException(status_code=410, detail={"kod": "pasif"}, headers=ACIK_BASLIKLAR)
    return AcikKart(kart, None, kanal)


def _kilit_acik_mi(kart: Kartvizitler, jeton: Optional[str]) -> bool:
    return not kart.sifre_ozet or k.erisim_jetonu_gecerli_mi(jeton, kart.id, kart.sifre_ozet)


def _kilit_iste(kart: Kartvizitler, jeton: Optional[str]) -> None:
    if not _kilit_acik_mi(kart, jeton):
        raise HTTPException(status_code=401, detail={"kod": "parola_gerekli"}, headers=ACIK_BASLIKLAR)


def _olay_ekle(arka: BackgroundTasks, request: Request, kart_id: int, olay: str, hedef: Optional[str] = None,
               kanal: Optional[str] = None, sinir: Optional[HizSiniri] = None) -> None:
    """Olayı yanıt gönderildikten sonra yaz (hız sınırını aşan istekler kaydedilmez)."""
    if sinir is not None and not sinir.izin_var_mi(k.hiz_anahtari(request, "kart", kart_id, olay)):
        return
    arka.add_task(kk.olay_yaz, k.olay_satiri(request, "kart", kart_id, olay, hedef, kanal))


@acik_router.get("/gorsel/{dosya}")
async def gorsel(dosya: str, db: AsyncSession = Depends(get_db)):
    anahtar, _, uzanti = dosya.rpartition(".")
    if uzanti not in ("webp", "jpg") or not anahtar or len(anahtar) > 40:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    satir = (await db.execute(select(KartvizitGorselleri).where(KartvizitGorselleri.anahtar == anahtar))).scalars().first()
    if satir is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    try:
        veri = await kk.gorsel_icerigi(db, satir)
    except Exception:  # noqa: BLE001 - depo okunamadı
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    if uzanti == "jpg":
        # Paylaşım önizlemesi (WhatsApp / LinkedIn JPEG'i her yerde gösteriyor).
        return Response(
            k.jpeg_uret(veri, 1200), media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"},
        )
    # Adres yüklemeye özel (anahtar her yüklemede yeni): içerik asla değişmiyor.
    return Response(
        veri, media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"},
    )


@acik_router.get("/{adres}")
async def acik_kart(adres: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    a = await _acik_kart(db, adres)
    if a.yonlendir:
        return JSONResponse({"durum": "yonlendir", "yonlendir": a.yonlendir}, headers=ACIK_BASLIKLAR)
    kart = a.kart
    assert kart is not None
    _olay_ekle(arka, request, kart.id, "goruntulenme", kanal=a.kanal, sinir=_gorunum_hizi)
    marka = await _marka(db, kart)
    if not _kilit_acik_mi(kart, request.query_params.get("j")):
        return JSONResponse({**_kilitli_sozluk(kart), "marka": marka}, headers=ACIK_BASLIKLAR)
    return JSONResponse({**_acik_sozluk(kart, await kk.gorseller(db, "kart", kart.id)), "marka": marka}, headers=ACIK_BASLIKLAR)


@acik_router.get("/{adres}/ozet")
async def acik_ozet(adres: str, db: AsyncSession = Depends(get_db)):
    """Paylaşım önizlemesi (Pages Function). Sayılmaz; parolalı kartta kişisel bilgi yok."""
    try:
        a = await _acik_kart(db, adres)
    except HTTPException as h:
        durum = "yok" if h.status_code == 404 else "pasif"
        return JSONResponse({"durum": durum, "index": False}, headers=ACIK_BASLIKLAR)
    if a.yonlendir:
        return JSONResponse({"durum": "yonlendir", "yonlendir": a.yonlendir, "index": False}, headers=ACIK_BASLIKLAR)
    kart = a.kart
    assert kart is not None
    dil = kart.dil if kart.dil in k.DILLER else "tr"
    temel = {
        "slug": kart.slug,
        "dil": dil,
        "locale": k.OG_LOCALE.get(dil, "tr_TR"),
        "kart_adresi": k.kart_adresi(kart.slug),
        # Faz 4L: Function ilk boyamada doğru zemin/renk için (kartın teması ya da marka teması).
        "tema": _tema(kart),
        "marka": await _marka(db, kart),
    }
    if kart.sifre_ozet:
        baslik, aciklama = k.KILITLI_METIN.get(dil, k.KILITLI_METIN["tr"])
        return JSONResponse(
            {**temel, "durum": "kilitli", "index": False, "baslik": baslik, "aciklama": aciklama, "gorsel": None},
            headers=ACIK_BASLIKLAR,
        )
    icerik = k.json_yukle(kart.icerik)
    gorsel_satir = None
    for gid in (kart.foto_id, kart.logo_id, kart.kapak_id):
        gorsel_satir = await kk.gorsel_bul(db, gid)
        if gorsel_satir is not None:
            break
    return JSONResponse(
        {
            **temel,
            "durum": "aktif",
            "index": bool(kart.index_acik),
            "baslik": k.ozet_basligi(icerik, kart),
            "aciklama": k.ozet_aciklamasi(icerik, dil),
            "gorsel": (k.site_adresi() + k.gorsel_adresi(gorsel_satir.anahtar, "jpg")) if gorsel_satir else None,
            "gorsel_genislik": gorsel_satir.genislik if gorsel_satir else None,
            "gorsel_yukseklik": gorsel_satir.yukseklik if gorsel_satir else None,
            "gorsel_alt": icerik.get("ad_soyad") or kart.ad_soyad,
        },
        headers=ACIK_BASLIKLAR,
    )


@acik_router.post("/{adres}/parola")
async def acik_parola(adres: str, request: Request, db: AsyncSession = Depends(get_db)):
    # Herkese açık sayfa gövdeyi `text/plain` JSON gönderiyor (ön kontrol isteği olmasın).
    govde = await _govde_oku(request, 1024)
    a = await _acik_kart(db, adres)
    if a.yonlendir:
        raise _hata(404, "bulunamadi")
    kart = a.kart
    assert kart is not None
    if not kart.sifre_ozet:
        return JSONResponse({"jeton": None, "kart": {**_acik_sozluk(kart, await kk.gorseller(db, "kart", kart.id)),
                                                     "marka": await _marka(db, kart)}},
                            headers=ACIK_BASLIKLAR)
    await _kalici_hiz((_parola_hizi, k.hiz_anahtari(request, "parola", kart.id)))
    from services.dosyalar import sifre_dogru_mu

    parola = str(govde.get("parola") or "")
    if not parola or len(parola) > 128 or not sifre_dogru_mu(parola, kart.sifre_ozet, kart.sifre_tuz or ""):
        raise HTTPException(status_code=403, detail={"kod": "parola_yanlis"}, headers=ACIK_BASLIKLAR)
    return JSONResponse(
        {
            "jeton": k.erisim_jetonu_uret(kart.id, kart.sifre_ozet),
            "kart": {**_acik_sozluk(kart, await kk.gorseller(db, "kart", kart.id)), "marka": await _marka(db, kart)},
        },
        headers=ACIK_BASLIKLAR,
    )


@acik_router.get("/{adres}/rehber.vcf")
async def acik_vcard(adres: str, request: Request, arka: BackgroundTasks, j: Optional[str] = Query(None),
                     db: AsyncSession = Depends(get_db)):
    a = await _acik_kart(db, adres)
    if a.yonlendir:
        raise _hata(404, "bulunamadi")
    kart = a.kart
    assert kart is not None
    _kilit_iste(kart, j)
    icerik = k.json_yukle(kart.icerik)
    foto = None
    satir = await kk.gorsel_bul(db, kart.foto_id)
    if satir is not None:
        try:
            foto = k.jpeg_uret(await kk.gorsel_icerigi(db, satir), k.VCARD_FOTO_KENAR, 80, k.VCARD_FOTO_EN_COK)
        except Exception:  # noqa: BLE001 - fotoğrafsız vCard yine iner
            foto = None
    metin = qr.vcard_uret(k.vcard_alanlari(kart, icerik, foto))
    _olay_ekle(arka, request, kart.id, "rehber", sinir=_olay_hizi)
    return Response(
        metin,
        media_type="text/vcard; charset=utf-8",
        headers={**ACIK_BASLIKLAR, "Content-Disposition": icerik_konumu(k.vcard_dosya_adi(kart.slug))},
    )


@acik_router.get("/{adres}/qr.{bicim}")
async def acik_qr(adres: str, bicim: str, j: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    if bicim not in ("png", "svg"):
        raise _hata(404, "bulunamadi")
    a = await _acik_kart(db, adres)
    if a.yonlendir:
        raise _hata(404, "bulunamadi")
    kart = a.kart
    assert kart is not None
    _kilit_iste(kart, j)
    return _qr_yaniti(await _qr_gorseli(db, kart, bicim), kart.slug, bicim)


async def _govde_oku(request: Request, sinir: int = 8192) -> Dict[str, Any]:
    """JSON gövde (sendBeacon `text/plain` gönderiyor: ön kontrol olmasın)."""
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


@acik_router.post("/{adres}/olay")
async def acik_olay(adres: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request, 2048)
    a = await _acik_kart(db, adres)
    if a.yonlendir:
        raise _hata(404, "bulunamadi")
    kart = a.kart
    assert kart is not None
    _kilit_iste(kart, govde.get("j"))
    tur = govde.get("tur")
    hedef = govde.get("hedef")
    if tur not in ("tik", "paylas") or (tur == "tik" and not k.hedef_gecerli_mi(hedef)):
        raise _hata(400, "olay_gecersiz")
    if _olay_hizi.izin_var_mi(k.hiz_anahtari(request, "olay")):
        arka.add_task(kk.olay_yaz, k.olay_satiri(request, "kart", kart.id, tur, hedef if tur == "tik" else None))
    return Response(status_code=204, headers=ACIK_BASLIKLAR)


async def _musteri_bildir(db: AsyncSession, kart: Kartvizitler, m: KartvizitMesajlari) -> None:
    from services.notify import dispatch, render

    try:
        varsayilan_baslik = f"Dijital kartvizitinize yeni mesaj: {m.ad or '—'}"
        govde = (
            f"Kart: {kart.ad_soyad} ({k.kart_adresi(kart.slug)})\nAd: {m.ad or '—'}\nE-posta: {m.eposta or '—'}\n"
            f"Telefon: {m.telefon or '—'}\n\n{(m.mesaj or '')[:1500]}"
        )
        baslik, metin = await render(
            db, "kartvizit_mesaj", varsayilan_baslik, govde,
            {"ad": m.ad or "", "eposta": m.eposta or "", "telefon": m.telefon or "", "kart": kart.ad_soyad},
        )
        await dispatch(
            db, event_type="kartvizit_mesaj", title=baslik, body=metin,
            recipients=[{"email": kart.hesap_email, "role": "client"}],
            link="/client?sekme=kartvizit&alt=mesajlar", ref_type="kartvizit_mesaj", ref_id=m.id,
        )
    except Exception:  # noqa: BLE001 - bildirim formu bozmasın
        logger.exception("Kartvizit mesaj bildirimi gönderilemedi")


async def _crm_aday(db: AsyncSession, kart: Kartvizitler, m: KartvizitMesajlari) -> None:
    """Ajansın kendi kartı → CRM adayı (aynı e-postada açık aday varsa ona eklenir)."""
    from models.crm import CrmAdaylari
    from services import crm

    try:
        sonuc = await crm.kayit_isle(db, crm.TalepGirdisi(
            tablo="kartvizit_mesajlari", kayit_id=m.id, ad=m.ad, email=m.eposta or None, telefon=m.telefon or None,
            konu=f"Dijital kartvizit: {kart.ad_soyad}", mesaj=m.mesaj, kaynak="form",
            kaynak_ham=f"kartvizit:{kart.slug}", ek_veri={"kartvizit": kart.slug},
        ))
        m.crm_aday_id = sonuc["aday_id"] if sonuc else None
        await db.commit()
        if sonuc:
            aday = (await db.execute(select(CrmAdaylari).where(CrmAdaylari.id == sonuc["aday_id"]))).scalars().first()
            if aday is not None:
                await crm.yeni_aday_bildir(db, aday, yeni=sonuc["yeni"], form_adi=f"Kartvizit {kart.ad_soyad}")
    except Exception:  # noqa: BLE001 - CRM hatası mesajı bozmasın (mesaj zaten kayıtlı)
        logger.exception("Kartvizit mesajı CRM'e aktarılamadı")
        await db.rollback()


@acik_router.post("/{adres}/mesaj")
async def acik_mesaj(adres: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request)
    a = await _acik_kart(db, adres)
    if a.yonlendir:
        raise _hata(404, "bulunamadi")
    kart = a.kart
    assert kart is not None
    if not kart.form_acik:
        raise _hata(403, "form_kapali")
    _kilit_iste(kart, govde.get("j"))
    await _kalici_hiz((_form_hizi, k.hiz_anahtari(request, "form", kart.id)), (_form_ip_hizi, k.hiz_anahtari(request, "form")))
    # Bal küpü: bot "başarılı" görsün, hiçbir şey kaydedilmesin.
    if str(govde.get("web_sitesi") or "").strip():
        logger.info("Kartvizit formu: bal küpü dolu, gönderim yok sayıldı (kart %s)", kart.id)
        return {"ok": True}
    try:
        k.form_jetonu_dogrula(govde.get("form_jetonu"), "kart", kart.id)
        d = k.mesaj_dogrula(govde, "kart")
    except k.KartHatasi as e:
        raise _kart_hatasi(e)
    m = KartvizitMesajlari(
        sahip_tur="kart", sahip_id=kart.id, hesap_email=kart.hesap_email, ad=d["ad"] or None,
        eposta=d["eposta"] or None, telefon=d["telefon"] or None, mesaj=d["mesaj"] or None, dil=kart.dil,
        aydinlatma_at=k.simdi(), okundu=False,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    if kart.hesap_email is None:
        await _crm_aday(db, kart, m)
    else:
        await _musteri_bildir(db, kart, m)
    _olay_ekle(arka, request, kart.id, "form")
    return {"ok": True}


# Yönetici ve müşteri router'ları ÖNCE; herkese açık en sonda.
router = (yonetici_router, musteri_router, acik_router)
