"""Faz 4K — Google yorum sayfası (`/yorum/<slug>`).

GOOGLE POLİTİKASI — "review gating" YOK
---------------------------------------
Google, yorumları seçici biçimde istemeyi (yalnız memnun müşteriyi Google'a
yönlendirmek, puan sorup düşük puanı Google'dan uzaklaştırmak) yasaklıyor.
Bu yüzden burada puan SORULMUYOR ve hiçbir koşul Google bağlantısını
değiştirmiyor: herkese açık uç, sayfa etkin olduğu sürece HER ziyaretçiye
aynı `google_adresi`ni döndürüyor. "Bize özel geri bildirim gönder" formu
yalnız EK bir seçenek; Google düğmesinin yanında, onu gizlemeden duruyor.

Herkese açık (`/api/v1/yorum`):
  GET  "/{adres}"                 sayfa (slug | eski slug → {yonlendir} | değişmez kod); 410 / 404
  POST "/{adres}/olay"            {tur: google} — Google düğmesi tıklaması (sendBeacon)
  POST "/{adres}/geri-bildirim"   özel geri bildirim: hız sınırı + bal küpü + imzalı form jetonu

Yönetici (`/api/v1/yorum-sayfalari/yonetim`) ve müşteri
(`/api/v1/yorum-sayfalarim`; modül `google_yorum_sayfasi` + ekip izni `kartvizit`):
  GET "/meta", GET "/slug-uygun", GET "/geri-bildirimler", PUT|DELETE "/geri-bildirimler/{id}",
  GET "", POST "", GET|PUT|DELETE "/{id}", POST|DELETE "/{id}/logo", GET "/{id}/analiz", GET "/{id}/qr"
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from models.kartvizit import KartvizitGorselleri, KartvizitMesajlari, YorumSayfalari
from routers.kartvizit import (
    ACIK_BASLIKLAR,
    Kapsam,
    _govde_oku,
    _hata,
    _hiz,
    _kart_hatasi,
    _musteri_kapsami as _kart_musteri_kapsami,
    _yonetici_kapsami,
    mesaj_bul,
    mesaj_listesi,
    sahip_modulu_acik_mi,
)
from services import dinamik_qr as qr
from services import kartvizit as k
from services import kartvizit_kayit as kk
from services.dosya_deposu import icerik_konumu
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri

logger = logging.getLogger(__name__)

MODUL = "google_yorum_sayfasi"
IZIN = "kartvizit"
VARSAYILAN_SAYFA_SINIRI = 3
YORUM_OLAYLARI = ("goruntulenme", "google", "geri_bildirim")

acik_router = APIRouter(prefix="/api/v1/yorum", tags=["google_yorum"])
yonetici_router = APIRouter(
    prefix="/api/v1/yorum-sayfalari/yonetim", tags=["google_yorum"], dependencies=[Depends(yonetici_gerekli)]
)
musteri_router = APIRouter(
    prefix="/api/v1/yorum-sayfalarim",
    tags=["google_yorum"],
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(IZIN))],
)

_yazma_hizi = HizSiniri(60, 60.0)
_gorunum_hizi = HizSiniri(30, 60.0)
_olay_hizi = HizSiniri(60, 60.0)
_form_hizi = HizSiniri(3, 600.0)
_form_ip_hizi = HizSiniri(10, 3600.0)


def hiz_sinirlarini_temizle() -> None:
    for h in (_yazma_hizi, _gorunum_hizi, _olay_hizi, _form_hizi, _form_ip_hizi):
        h.temizle()


def _musteri_kapsami(request: Request) -> Kapsam:
    return _kart_musteri_kapsami(request)


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def _panel_sozlugu(y: YorumSayfalari, logo: Optional[KartvizitGorselleri], sayilar: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    return {
        "id": y.id,
        "kod": y.kod,
        "slug": y.slug,
        "isletme_adi": y.isletme_adi,
        "place_id": y.place_id,
        "google_adresi": k.google_adresi(y.place_id),
        "tesekkur": y.tesekkur or "",
        "geri_bildirim_acik": bool(y.geri_bildirim_acik),
        "dil": y.dil,
        "renk": y.renk,
        "logo": kk.gorsel_sozlugu(logo),
        "aktif": bool(y.aktif),
        "hesap_email": y.hesap_email,
        "olusturan_email": y.olusturan_email,
        "sayfa_adresi": k.yorum_adresi(y.slug),
        "qr_adresi": k.yorum_adresi(y.kod),
        "son30": sayilar or {},
        "created_at": k.iso(y.created_at),
        "updated_at": k.iso(y.updated_at),
    }


def _acik_sozluk(y: YorumSayfalari, logo: Optional[KartvizitGorselleri]) -> Dict[str, Any]:
    # Google adresi koşulsuz: her ziyaretçiye aynı bağlantı (review gating yok).
    return {
        "durum": "aktif",
        "slug": y.slug,
        "kod": y.kod,
        "dil": y.dil,
        "isletme_adi": y.isletme_adi,
        "tesekkur": y.tesekkur or "",
        "renk": y.renk or "#4285f4",
        "logo": kk.gorsel_sozlugu(logo),
        "google_adresi": k.google_adresi(y.place_id),
        "geri_bildirim": {
            "acik": bool(y.geri_bildirim_acik),
            "jeton": k.form_jetonu_uret("yorum", y.id) if y.geri_bildirim_acik else None,
            "aydinlatma_adresi": k.aydinlatma_adresi(y.dil),
        },
    }


# ---------------------------------------------------------------------------
# Panel işleri
# ---------------------------------------------------------------------------
async def _sayfa(db: AsyncSession, sayfa_id: int, kapsam: Kapsam) -> YorumSayfalari:
    sorgu = select(YorumSayfalari).where(YorumSayfalari.id == sayfa_id)
    if not kapsam.yonetici:
        sorgu = sorgu.where(YorumSayfalari.hesap_email == kapsam.hesap)
    y = (await db.execute(sorgu)).scalars().first()
    if y is None:
        raise _hata(404, "bulunamadi")
    return y


async def _sayfa_siniri(db: AsyncSession, kapsam: Kapsam) -> Optional[int]:
    if kapsam.yonetici:
        return None
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, kapsam.hesap or "", MODUL, "sayfa_siniri")
    return int(deger) if isinstance(deger, int) else VARSAYILAN_SAYFA_SINIRI


async def _sayfa_sayisi(db: AsyncSession, hesap: Optional[str]) -> int:
    sorgu = select(func.count(YorumSayfalari.id))
    sorgu = sorgu.where(YorumSayfalari.hesap_email.is_(None)) if hesap is None else sorgu.where(YorumSayfalari.hesap_email == hesap)
    return int((await db.execute(sorgu)).scalar() or 0)


def _alanlar(govde: Dict[str, Any], kismi: bool) -> Dict[str, Any]:
    d: Dict[str, Any] = {}
    if not kismi or "isletme_adi" in govde:
        d["isletme_adi"] = k.metin(govde.get("isletme_adi"), "isletme_adi", k.SINIR["isletme_adi"], zorunlu=True)
    if not kismi or "place_id" in govde:
        d["place_id"] = k.place_id_dogrula(govde.get("place_id"))
    if not kismi or "tesekkur" in govde:
        d["tesekkur"] = k.metin(govde.get("tesekkur"), "tesekkur", k.SINIR["tesekkur"], cok_satir=True) or None
    if not kismi or "dil" in govde:
        d["dil"] = k.dil_duzelt(govde.get("dil"))
    if not kismi or "renk" in govde:
        d["renk"] = k.renk_duzelt(govde.get("renk"))
    for alan in ("geri_bildirim_acik", "aktif"):
        if not kismi or alan in govde:
            d[alan] = govde.get(alan) is not False if not kismi else bool(govde.get(alan))
    return d


async def _hedef_hesap(kapsam: Kapsam, govde: Dict[str, Any]) -> Optional[str]:
    if not kapsam.yonetici:
        return kapsam.hesap
    ham = (govde.get("hesap_email") or "").strip().lower()
    if not ham:
        return None
    if not qr.eposta_dogru_mu(ham):
        raise k.KartHatasi("eposta_gecersiz", "hesap_email")
    return ham


async def _olustur(db: AsyncSession, kapsam: Kapsam, govde: Dict[str, Any]) -> Dict[str, Any]:
    _hiz(_yazma_hizi, kapsam.kisi)
    try:
        d = _alanlar(govde, kismi=False)
        hesap = await _hedef_hesap(kapsam, govde)
        slug = k.slug_duzelt(govde["slug"]) if govde.get("slug") else None
    except k.KartHatasi as e:
        raise _kart_hatasi(e)
    sinir = await _sayfa_siniri(db, kapsam)
    if sinir is not None and await _sayfa_sayisi(db, hesap) >= sinir:
        raise _hata(409, "sayfa_siniri", sinir=sinir)
    if slug is None:
        slug = await kk.slug_onerisi(db, "yorum", d["isletme_adi"])
    elif not await kk.slug_bos_mu(db, "yorum", slug):
        raise _hata(409, "slug_kullaniliyor", alan="slug")
    try:
        kod = await kk.benzersiz_kod(db, "yorum")
    except k.KartHatasi as e:
        raise _kart_hatasi(e)
    y = YorumSayfalari(hesap_email=hesap, olusturan_email=kapsam.kisi or None, kod=kod, slug=slug, **d)
    db.add(y)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "slug_kullaniliyor", alan="slug")
    await db.refresh(y)
    return _panel_sozlugu(y, None)


async def _guncelle(db: AsyncSession, kapsam: Kapsam, y: YorumSayfalari, govde: Dict[str, Any]) -> Dict[str, Any]:
    _hiz(_yazma_hizi, kapsam.kisi)
    try:
        for ad, deger in _alanlar(govde, kismi=True).items():
            setattr(y, ad, deger)
        if govde.get("slug") and govde.get("slug") != y.slug:
            yeni = k.slug_duzelt(govde.get("slug"))
            if not await kk.slug_bos_mu(db, "yorum", yeni, haric_id=y.id):
                raise _hata(409, "slug_kullaniliyor", alan="slug")
            await kk.slug_degistir(db, "yorum", y, yeni)
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
    await db.refresh(y)
    return _panel_sozlugu(y, await kk.gorsel_bul(db, y.logo_id))


async def _liste(db: AsyncSession, kapsam: Kapsam, ara: Optional[str], hesap: Optional[str]) -> Dict[str, Any]:
    sorgu = select(YorumSayfalari)
    if not kapsam.yonetici:
        sorgu = sorgu.where(YorumSayfalari.hesap_email == kapsam.hesap)
    elif hesap == "ajans":
        sorgu = sorgu.where(YorumSayfalari.hesap_email.is_(None))
    elif hesap:
        sorgu = sorgu.where(YorumSayfalari.hesap_email == hesap.strip().lower())
    if ara and ara.strip():
        from sqlalchemy import or_

        desen = f"%{ara.strip()[:80].lower()}%"
        sorgu = sorgu.where(or_(func.lower(YorumSayfalari.isletme_adi).like(desen), func.lower(YorumSayfalari.slug).like(desen),
                                func.lower(YorumSayfalari.hesap_email).like(desen)))
    sayfalar = (await db.execute(sorgu.order_by(desc(YorumSayfalari.created_at), desc(YorumSayfalari.id)).limit(500))).scalars().all()
    idler = [y.id for y in sayfalar]
    sayilar = await kk.donem_sayilari(db, "yorum", idler)
    logo_idler = [y.logo_id for y in sayfalar if y.logo_id]
    logolar: Dict[int, KartvizitGorselleri] = {}
    if logo_idler:
        logolar = {g.id: g for g in (await db.execute(select(KartvizitGorselleri).where(KartvizitGorselleri.id.in_(logo_idler)))).scalars()}
    okunmamis = dict(
        (int(sid), int(n))
        for sid, n in (
            await db.execute(
                select(KartvizitMesajlari.sahip_id, func.count(KartvizitMesajlari.id))
                .where(KartvizitMesajlari.sahip_tur == "yorum", KartvizitMesajlari.sahip_id.in_(idler or [0]),
                       KartvizitMesajlari.okundu.is_(False))
                .group_by(KartvizitMesajlari.sahip_id)
            )
        ).all()
    )
    ogeler = []
    for y in sayfalar:
        d = _panel_sozlugu(y, logolar.get(y.logo_id) if y.logo_id else None, sayilar.get(y.id))
        d["okunmamis"] = okunmamis.get(y.id, 0)
        ogeler.append(d)
    return {"toplam": len(ogeler), "items": ogeler}


async def _logo_yukle(db: AsyncSession, kapsam: Kapsam, y: YorumSayfalari, dosya: UploadFile) -> Dict[str, Any]:
    _hiz(_yazma_hizi, kapsam.kisi)
    bayt = await dosya.read(k.GORSEL_EN_COK_BAYT + 1)
    try:
        yeni = await kk.gorsel_kaydet(db, hesap=y.hesap_email, sahip_tur="yorum", sahip_id=y.id, tur="logo", bayt=bayt)
    except k.KartHatasi as e:
        await db.rollback()
        raise _kart_hatasi(e)
    eski = await kk.gorsel_bul(db, y.logo_id)
    y.logo_id = yeni.id
    if eski is not None:
        await kk.gorsel_sil(db, eski)
    await db.commit()
    await db.refresh(y)
    return _panel_sozlugu(y, yeni)


async def _logo_kaldir(db: AsyncSession, y: YorumSayfalari) -> Dict[str, Any]:
    eski = await kk.gorsel_bul(db, y.logo_id)
    y.logo_id = None
    if eski is not None:
        await kk.gorsel_sil(db, eski)
    await db.commit()
    await db.refresh(y)
    return _panel_sozlugu(y, None)


async def _sil(db: AsyncSession, y: YorumSayfalari) -> None:
    await kk.eski_sluglari_sil(db, "yorum", y.id)
    for g in await kk.gorseller(db, "yorum", y.id):
        await db.delete(g)
    await db.delete(y)
    await db.commit()


async def _qr_gorseli(db: AsyncSession, y: YorumSayfalari, bicim: str, boyut: Optional[int] = None) -> qr.Gorsel:
    tasarim = dict(qr.VARSAYILAN_TASARIM)
    if boyut:
        tasarim["boyut"] = boyut
    if y.renk and qr.kontrast_orani(y.renk, "#ffffff") >= 4.5:
        tasarim["on_renk"] = y.renk
    tasarim = qr.tasarim_duzelt(tasarim)
    logo = None
    satir = await kk.gorsel_bul(db, y.logo_id)
    if satir is not None:
        try:
            logo = k.png_b64(await kk.gorsel_icerigi(db, satir))
        except Exception:  # noqa: BLE001
            logo = None
    return (qr.png_ciz if bicim == "png" else qr.svg_ciz)(k.yorum_adresi(y.kod), tasarim, logo)


def _uclari_kur(router: APIRouter, kapsam_al: Callable[[Request], Kapsam]) -> None:
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return {
            "diller": list(k.DILLER),
            "sinirlar": k.SINIR,
            "gorsel_en_cok_mb": k.GORSEL_EN_COK_BAYT // (1024 * 1024),
            "sayfa_tabani": k.yorum_adresi(""),
            "eski_slug_gun": k.ESKI_SLUG_GUN,
            "sayfa_siniri": await _sayfa_siniri(db, kapsam),
            "sayfa_sayisi": None if kapsam.yonetici else await _sayfa_sayisi(db, kapsam.hesap),
            "yonetici": kapsam.yonetici,
        }

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
            await _sayfa(db, haric_id, kapsam)
        oneri = await kk.slug_onerisi(db, "yorum", ad or slug)
        try:
            temiz = k.slug_duzelt(slug)
        except k.KartHatasi as e:
            return {"uygun": False, "kod": e.kod, "oneri": oneri}
        if not await kk.slug_bos_mu(db, "yorum", temiz, haric_id=haric_id):
            return {"uygun": False, "kod": "slug_kullaniliyor", "oneri": oneri}
        return {"uygun": True, "slug": temiz, "oneri": oneri}

    @router.get("/geri-bildirimler")
    async def geri_bildirimler(
        request: Request,
        sayfa_id: Optional[int] = Query(None),
        okunmamis: Optional[bool] = Query(None),
        hesap: Optional[str] = Query(None),
        db: AsyncSession = Depends(get_db),
    ):
        kapsam = kapsam_al(request)
        return await mesaj_listesi(
            db, "yorum", YorumSayfalari, "isletme_adi", kapsam.yonetici, kapsam.hesap, sayfa_id, okunmamis,
            hesap if kapsam.yonetici else None,
        )

    @router.put("/geri-bildirimler/{mesaj_id}")
    async def geri_bildirim_guncelle(mesaj_id: int, request: Request, govde: Dict[str, Any] = Body(...),
                                     db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        m = await mesaj_bul(db, "yorum", mesaj_id, kapsam.yonetici, kapsam.hesap)
        if "okundu" in govde:
            m.okundu = bool(govde.get("okundu"))
        await db.commit()
        return {"ok": True, "id": m.id, "okundu": bool(m.okundu)}

    @router.delete("/geri-bildirimler/{mesaj_id}")
    async def geri_bildirim_sil(mesaj_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        m = await mesaj_bul(db, "yorum", mesaj_id, kapsam.yonetici, kapsam.hesap)
        await db.delete(m)
        await db.commit()
        return {"ok": True}

    @router.get("")
    async def liste(request: Request, ara: Optional[str] = Query(None), hesap: Optional[str] = Query(None),
                    db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _liste(db, kapsam, ara, hesap if kapsam.yonetici else None)

    @router.post("")
    async def olustur(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        return await _olustur(db, kapsam_al(request), govde)

    @router.get("/{sayfa_id}")
    async def ayrinti(sayfa_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = await _sayfa(db, sayfa_id, kapsam_al(request))
        return _panel_sozlugu(y, await kk.gorsel_bul(db, y.logo_id))

    @router.put("/{sayfa_id}")
    async def guncelle(sayfa_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _guncelle(db, kapsam, await _sayfa(db, sayfa_id, kapsam), govde)

    @router.delete("/{sayfa_id}")
    async def sil(sayfa_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        await _sil(db, await _sayfa(db, sayfa_id, kapsam_al(request)))
        return {"ok": True}

    @router.post("/{sayfa_id}/logo")
    async def logo_yukle(sayfa_id: int, request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _logo_yukle(db, kapsam, await _sayfa(db, sayfa_id, kapsam), dosya)

    @router.delete("/{sayfa_id}/logo")
    async def logo_kaldir(sayfa_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        return await _logo_kaldir(db, await _sayfa(db, sayfa_id, kapsam_al(request)))

    @router.get("/{sayfa_id}/analiz")
    async def analiz(sayfa_id: int, request: Request, gun: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
        y = await _sayfa(db, sayfa_id, kapsam_al(request))
        return await kk.analiz(db, "yorum", y.id, gun, YORUM_OLAYLARI)

    @router.get("/{sayfa_id}/qr")
    async def qr_indir(
        sayfa_id: int,
        request: Request,
        bicim: str = Query("png"),
        boyut: Optional[int] = Query(None, ge=qr.BOYUT_EN_AZ, le=qr.BOYUT_EN_COK),
        db: AsyncSession = Depends(get_db),
    ):
        if bicim not in ("png", "svg"):
            raise _hata(400, "bicim_gecersiz")
        y = await _sayfa(db, sayfa_id, kapsam_al(request))
        try:
            g = await _qr_gorseli(db, y, bicim, boyut)
        except k.KartHatasi as e:
            raise _kart_hatasi(e)
        return Response(
            g.veri, media_type=g.tur,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                     "Content-Disposition": icerik_konumu(f"yorum-{y.slug}-qr.{bicim}")},
        )


_uclari_kur(yonetici_router, _yonetici_kapsami)
_uclari_kur(musteri_router, _musteri_kapsami)


# ---------------------------------------------------------------------------
# Herkese açık
# ---------------------------------------------------------------------------
async def _acik_sayfa(db: AsyncSession, adres: str):
    y, yonlendir, kanal = await kk.cozumle(db, "yorum", adres)
    if yonlendir:
        return None, yonlendir, None
    if y is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"}, headers=ACIK_BASLIKLAR)
    if not y.aktif or not await sahip_modulu_acik_mi(db, y.hesap_email, MODUL):
        raise HTTPException(status_code=410, detail={"kod": "pasif"}, headers=ACIK_BASLIKLAR)
    return y, None, kanal


@acik_router.get("/{adres}")
async def acik_sayfa(adres: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    y, yonlendir, kanal = await _acik_sayfa(db, adres)
    if yonlendir:
        return JSONResponse({"durum": "yonlendir", "yonlendir": yonlendir}, headers=ACIK_BASLIKLAR)
    if _gorunum_hizi.izin_var_mi(k.hiz_anahtari(request, "yorum", y.id)):
        arka.add_task(kk.olay_yaz, k.olay_satiri(request, "yorum", y.id, "goruntulenme", kanal=kanal))
    return JSONResponse(_acik_sozluk(y, await kk.gorsel_bul(db, y.logo_id)), headers=ACIK_BASLIKLAR)


@acik_router.post("/{adres}/olay")
async def acik_olay(adres: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request, 1024)
    y, yonlendir, _ = await _acik_sayfa(db, adres)
    if yonlendir:
        raise _hata(404, "bulunamadi")
    if govde.get("tur") != "google":
        raise _hata(400, "olay_gecersiz")
    if _olay_hizi.izin_var_mi(k.hiz_anahtari(request, "yorum-olay")):
        arka.add_task(kk.olay_yaz, k.olay_satiri(request, "yorum", y.id, "google"))
    return Response(status_code=204, headers=ACIK_BASLIKLAR)


async def _bildir(db: AsyncSession, y: YorumSayfalari, m: KartvizitMesajlari) -> None:
    from services.notify import admin_recipients, dispatch, render

    try:
        varsayilan_baslik = f"Yorum sayfanıza özel geri bildirim: {y.isletme_adi}"
        govde = (
            f"Sayfa: {y.isletme_adi} ({k.yorum_adresi(y.slug)})\nAd: {m.ad or '—'}\nE-posta: {m.eposta or '—'}\n"
            f"Telefon: {m.telefon or '—'}\n\n{(m.mesaj or '')[:1500]}"
        )
        baslik, metin = await render(
            db, "yorum_geri_bildirim", varsayilan_baslik, govde,
            {"isletme": y.isletme_adi, "ad": m.ad or "", "eposta": m.eposta or ""},
        )
        if y.hesap_email:
            alicilar: List[Dict[str, Any]] = [{"email": y.hesap_email, "role": "client"}]
            link = "/client?sekme=kartvizit&alt=geri-bildirim"
        else:
            alicilar = list(await admin_recipients(db))
            link = "/admin?sekme=kartvizit&alt=geri-bildirim"
        await dispatch(
            db, event_type="yorum_geri_bildirim", title=baslik, body=metin, recipients=alicilar, link=link,
            ref_type="kartvizit_mesaj", ref_id=m.id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Yorum geri bildirimi bildirimi gönderilemedi")


@acik_router.post("/{adres}/geri-bildirim")
async def acik_geri_bildirim(adres: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request)
    y, yonlendir, _ = await _acik_sayfa(db, adres)
    if yonlendir:
        raise _hata(404, "bulunamadi")
    if not y.geri_bildirim_acik:
        raise _hata(403, "form_kapali")
    _hiz(_form_hizi, k.hiz_anahtari(request, "yorum-form", y.id))
    _hiz(_form_ip_hizi, k.hiz_anahtari(request, "yorum-form"))
    if str(govde.get("web_sitesi") or "").strip():
        logger.info("Yorum sayfası formu: bal küpü dolu, gönderim yok sayıldı (sayfa %s)", y.id)
        return {"ok": True}
    try:
        k.form_jetonu_dogrula(govde.get("form_jetonu"), "yorum", y.id)
        d = k.mesaj_dogrula(govde, "yorum")
    except k.KartHatasi as e:
        raise _kart_hatasi(e)
    m = KartvizitMesajlari(
        sahip_tur="yorum", sahip_id=y.id, hesap_email=y.hesap_email, ad=d["ad"] or None, eposta=d["eposta"] or None,
        telefon=d["telefon"] or None, mesaj=d["mesaj"], dil=y.dil, aydinlatma_at=k.simdi(), okundu=False,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    await _bildir(db, y, m)
    arka.add_task(kk.olay_yaz, k.olay_satiri(request, "yorum", y.id, "geri_bildirim"))
    return {"ok": True}


router = (yonetici_router, musteri_router, acik_router)
