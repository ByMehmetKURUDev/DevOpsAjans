"""Faz 2C — Dosyalar ve belge talebi (ayrıntı `services/dosyalar.py`).

Yönetici  /api/v1/dosyalar            listele, yükle, sil, klasör yetkisi,
                                       imzalı indirme adresi, paylaşım bağlantısı,
                                       depo bilgisi ve boyut sınırı ayarı
          /api/v1/belge-talepleri      müşteriden belge iste / listele / iptal
Müşteri   /api/v1/dosyalarim          (modül `dosyalar`) görünür klasörler,
                                       yükle, indir, istenen belgeler + yükleme
Açık      /api/v1/dosya-indir/<id>    imzalı ve süreli (15 dk) indirme
          /api/v1/paylas/<jeton>      girişsiz paylaşım (süre, parola, sayı)

Müşteri e-postası her zaman JETONDAN alınıyor; başkasının dosyası "yok"
sayılıyor (404) — var olduğu da sızmasın.
"""

import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.hesap_baglami import izin_gerekli, kisi_eposta, musteri_eposta
from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi import Depends as _Depends
from fastapi.responses import RedirectResponse, Response
from models.dosyalar import BelgeTalepleri, Dosyalar, DosyaKlasorleri, PaylasimBaglantilari
from pydantic import BaseModel
from services import dosya_deposu
from services import dosyalar as servis
from services.dosyalar import DosyaHatasi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/dosyalar", tags=["dosyalar"])
talep_router = APIRouter(prefix="/api/v1/belge-talepleri", tags=["dosyalar"])
musteri_router = APIRouter(
    prefix="/api/v1/dosyalarim",
    tags=["dosyalar"],
    dependencies=[_Depends(izin_gerekli("dosyalar")), _Depends(modul_gerekli("dosyalar"))],
)
acik_router = APIRouter(prefix="/api/v1", tags=["dosyalar"])


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _kim(kisi: str, hesap: str) -> str:
    """Bildirim metni: ekip üyesi yazdıysa "kişi (hesap)"."""
    return kisi if kisi == hesap else f"{kisi} ({hesap})"


def _hata(h: DosyaHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})
    return servis.eposta_duzelt(kullanici.email)


def _musteri(request: Request) -> str:
    """Etkin hesabın e-postası (Faz 2E: ekip üyesi sahibin hesabında çalışabilir)."""
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not servis.eposta_duzelt(kullanici.email):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "eposta_gerekli"})
    return musteri_eposta(request)


def _eposta_dogrula(ham: Optional[str]) -> str:
    eposta = servis.eposta_duzelt(ham)
    if "@" not in eposta or len(eposta) > 200:
        raise HTTPException(status_code=400, detail={"kod": "gecersiz_eposta"})
    return eposta


async def _dosya(db: AsyncSession, dosya_id: int) -> Dosyalar:
    d = (await db.execute(select(Dosyalar).where(Dosyalar.id == dosya_id))).scalars().first()
    if d is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    return d


async def _musteri_dosyasi(db: AsyncSession, eposta: str, dosya_id: int) -> Dosyalar:
    """Müşterinin kendi dosyası VE müşteriye görünür klasörde; değilse 404."""
    d = (await db.execute(select(Dosyalar).where(Dosyalar.id == dosya_id))).scalars().first()
    if d is None or d.client_email != eposta:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    klasorler = await servis.musteri_klasorleri(db, eposta)
    if klasorler.get(d.klasor) != "musteri":
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    return d


def _indirme_yaniti(d: Dosyalar) -> Dict[str, Any]:
    yol, son = servis.imzali_yol(d.id)
    return {"adres": yol, "son": son}


async def _bildir(db: AsyncSession, **kw: Any) -> None:
    try:
        from services.notify import dispatch

        await dispatch(db, **kw)
    except Exception:  # noqa: BLE001 - bildirim asıl işi bozmasın
        logger.exception("Dosya bildirimi gönderilemedi")


async def _yoneticiler(db: AsyncSession) -> List[Dict[str, Any]]:
    from services.notify import admin_recipients

    return await admin_recipients(db)


def _boyut_metni(bayt: int) -> str:
    if bayt >= 1024 * 1024:
        return f"{bayt / (1024 * 1024):.1f} MB"
    return f"{max(1, bayt // 1024)} KB"


# ---------------------------------------------------------------------------
# Yönetici — dosyalar
# ---------------------------------------------------------------------------
class KlasorGirdisi(BaseModel):
    client_email: str
    ad: str
    gorunurluk: str = "musteri"


class AyarGirdisi(BaseModel):
    boyut_siniri_mb: int


class PaylasimGirdisi(BaseModel):
    gun: int = 7
    sifre: Optional[str] = None
    indirme_siniri: Optional[int] = None


@yonetici_router.get("/depo")
async def depo_bilgisi(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    sinir = await servis.boyut_siniri_bayt(db)
    return {
        **dosya_deposu.depo_bilgisi(),
        "boyut_siniri_mb": sinir // (1024 * 1024),
        "izinli_turler": sorted(servis.IZINLI_TURLER),
    }


@yonetici_router.put("/ayarlar")
async def ayar_yaz(request: Request, govde: AyarGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        mb = await servis.boyut_siniri_yaz(db, govde.boyut_siniri_mb)
    except DosyaHatasi as h:
        raise _hata(h)
    return {"boyut_siniri_mb": mb}


@yonetici_router.get("")
async def yonetici_listesi(
    request: Request,
    client_email: Optional[str] = Query(None),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    sorgu = select(Dosyalar).where(Dosyalar.guncel.is_(True)).order_by(Dosyalar.id.desc())
    klasorler: Dict[str, str] = {}
    if client_email:
        eposta = servis.eposta_duzelt(client_email)
        sorgu = sorgu.where(Dosyalar.client_email == eposta)
        klasorler = await servis.musteri_klasorleri(db, eposta)
    satirlar = (await db.execute(sorgu.limit(500))).scalars().all()
    if not client_email:
        # Liste birden çok müşteriyi karıştırıyor: her dosyanın klasör yetkisi kendi müşterisinden.
        epostalar = {d.client_email for d in satirlar}
        yetki: Dict[tuple, str] = {}
        if epostalar:
            for k in (
                await db.execute(select(DosyaKlasorleri).where(DosyaKlasorleri.client_email.in_(epostalar)))
            ).scalars().all():
                yetki[(k.client_email, k.ad)] = k.gorunurluk
        dosyalar = [servis.dosya_sozlugu(d, yetki.get((d.client_email, d.klasor), "ekip")) for d in satirlar]
        return {"dosyalar": dosyalar, "klasorler": []}
    return {
        "dosyalar": [servis.dosya_sozlugu(d, klasorler.get(d.klasor, "ekip")) for d in satirlar],
        "klasorler": [{"ad": ad, "gorunurluk": g} for ad, g in sorted(klasorler.items())],
    }


@yonetici_router.get("/klasorler")
async def klasor_listesi(request: Request, client_email: str = Query(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    eposta = _eposta_dogrula(client_email)
    return [{"ad": ad, "gorunurluk": g} for ad, g in sorted((await servis.musteri_klasorleri(db, eposta)).items())]


@yonetici_router.post("/klasorler")
async def klasor_yaz(request: Request, govde: KlasorGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    """Klasörü açar ya da görünürlüğünü değiştirir (musteri | ekip)."""
    _yonetici_iste(request)
    eposta = _eposta_dogrula(govde.client_email)
    if govde.gorunurluk not in ("musteri", "ekip"):
        raise HTTPException(status_code=400, detail={"kod": "gecersiz_gorunurluk"})
    ad = servis.klasor_temizle(govde.ad)
    k = await servis.klasor_getir(db, eposta, ad)
    if k is None:
        k = DosyaKlasorleri(client_email=eposta, ad=ad, gorunurluk=govde.gorunurluk)
        db.add(k)
    else:
        k.gorunurluk = govde.gorunurluk
    await db.commit()
    return {"ad": k.ad, "gorunurluk": k.gorunurluk}


@yonetici_router.post("/yukle")
async def yonetici_yukle(
    request: Request,
    client_email: str = Form(...),
    klasor: Optional[str] = Form(None),
    gorunurluk: Optional[str] = Form(None),
    proje_id: Optional[int] = Form(None),
    dosya: UploadFile = File(...),
    db: AsyncSession = _Depends(get_db),
):
    yonetici = _yonetici_iste(request)
    eposta = _eposta_dogrula(client_email)
    klasor_adi = servis.klasor_temizle(klasor)
    if gorunurluk is not None and gorunurluk not in ("musteri", "ekip"):
        raise HTTPException(status_code=400, detail={"kod": "gecersiz_gorunurluk"})
    try:
        veri = await servis.akistan_oku(dosya, await servis.boyut_siniri_bayt(db))
        k = await servis.klasor_hazirla(db, eposta, klasor_adi, gorunurluk or "musteri")
        kayit = await servis.dosya_kaydet(
            db, eposta=eposta, klasor=klasor_adi, ad_ham=dosya.filename or "", veri=veri,
            yukleyen=yonetici, yukleyen_rol="admin", proje_id=proje_id,
        )
        await db.commit()
        await db.refresh(kayit)
    except DosyaHatasi as h:
        await db.rollback()
        raise _hata(h)
    if k.gorunurluk == "musteri":
        await _bildir(
            db,
            event_type="dosya_eklendi",
            title=f"Yeni dosya: {kayit.ad}",
            body=f"{klasor_adi} klasörüne {kayit.ad} ({_boyut_metni(kayit.boyut)}) eklendi.",
            recipients=[{"email": eposta, "role": "client"}],
            link="/client?sekme=dosyalar",
            ref_type="dosya",
            ref_id=kayit.id,
        )
    return servis.dosya_sozlugu(kayit, k.gorunurluk)


@yonetici_router.get("/{dosya_id}/surumler")
async def surumler(dosya_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    d = await _dosya(db, dosya_id)
    satirlar = (
        await db.execute(
            select(Dosyalar)
            .where(Dosyalar.client_email == d.client_email, Dosyalar.klasor == d.klasor, Dosyalar.ad == d.ad)
            .order_by(Dosyalar.surum.desc())
        )
    ).scalars().all()
    return [servis.dosya_sozlugu(s) for s in satirlar]


@yonetici_router.post("/{dosya_id}/indirme-baglantisi")
async def yonetici_indirme(dosya_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return _indirme_yaniti(await _dosya(db, dosya_id))


@yonetici_router.delete("/{dosya_id}")
async def dosya_sil(dosya_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    d = await _dosya(db, dosya_id)
    guncel_miydi = bool(d.guncel)
    depo, anahtar = d.depo, d.depolama_anahtari
    # Bağlantılar da ölü: silinen dosyanın paylaşım adresi 404 versin.
    for p in (await db.execute(select(PaylasimBaglantilari).where(PaylasimBaglantilari.dosya_id == d.id))).scalars().all():
        p.iptal = True
    await db.delete(d)
    await db.flush()
    # Faz 2D: kayıt çöp kutusuna düştüyse içerik bekletiliyor (geri alınınca
    # dosya içeriğiyle gelsin); çöp kaydı kalıcı silinince içerik de gidiyor.
    # Çöpe düşmediyse (kanca hatası) içerik eskisi gibi hemen siliniyor.
    from services.cop_kutusu import cop_kutusunda_mi

    if not await cop_kutusunda_mi(db, "files", dosya_id):
        await dosya_deposu.sil(db, depo, anahtar)
    if guncel_miydi:
        onceki = (
            await db.execute(
                select(Dosyalar)
                .where(Dosyalar.client_email == d.client_email, Dosyalar.klasor == d.klasor, Dosyalar.ad == d.ad)
                .order_by(Dosyalar.surum.desc())
            )
        ).scalars().first()
        if onceki is not None:
            onceki.guncel = True
    await db.commit()
    return {"silindi": dosya_id}


@yonetici_router.post("/{dosya_id}/paylasim")
async def paylasim_ac(
    dosya_id: int, request: Request, govde: PaylasimGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    yonetici = _yonetici_iste(request)
    await _dosya(db, dosya_id)
    try:
        kayit, jeton = await servis.paylasim_olustur(
            db, dosya_id, gun=govde.gun, sifre=govde.sifre, indirme_siniri=govde.indirme_siniri, olusturan=yonetici
        )
    except DosyaHatasi as h:
        raise _hata(h)
    # Ham jeton yalnız bu yanıtta; veritabanında özeti var.
    return {**servis.paylasim_sozlugu(kayit), "yol": f"/paylas/{jeton}", "adres": f"{servis.site_adresi()}/paylas/{jeton}"}


@yonetici_router.get("/{dosya_id}/paylasimlar")
async def paylasimlar(dosya_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    satirlar = (
        await db.execute(
            select(PaylasimBaglantilari).where(PaylasimBaglantilari.dosya_id == dosya_id).order_by(PaylasimBaglantilari.id.desc())
        )
    ).scalars().all()
    return [servis.paylasim_sozlugu(p) for p in satirlar]


@yonetici_router.post("/paylasim/{paylasim_id}/iptal")
async def paylasim_iptal(paylasim_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    p = (await db.execute(select(PaylasimBaglantilari).where(PaylasimBaglantilari.id == paylasim_id))).scalars().first()
    if p is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    p.iptal = True
    await db.commit()
    return servis.paylasim_sozlugu(p)


# ---------------------------------------------------------------------------
# Yönetici — belge talepleri
# ---------------------------------------------------------------------------
class BelgeTalebiGirdisi(BaseModel):
    client_email: str
    baslik: str
    aciklama: Optional[str] = None
    son_tarih: Optional[str] = None
    kabul_turleri: Optional[List[str]] = None
    proje_id: Optional[int] = None


async def _talep_dosyalari(db: AsyncSession, talepler: List[BelgeTalepleri]) -> Dict[int, Dosyalar]:
    idler = [t.dosya_id for t in talepler if t.dosya_id]
    if not idler:
        return {}
    return {d.id: d for d in (await db.execute(select(Dosyalar).where(Dosyalar.id.in_(idler)))).scalars().all()}


@talep_router.get("")
async def talep_listesi(request: Request, client_email: Optional[str] = Query(None), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    sorgu = select(BelgeTalepleri).order_by(BelgeTalepleri.id.desc())
    if client_email:
        sorgu = sorgu.where(BelgeTalepleri.client_email == servis.eposta_duzelt(client_email))
    talepler = list((await db.execute(sorgu.limit(300))).scalars().all())
    dosyalar = await _talep_dosyalari(db, talepler)
    return [servis.talep_sozlugu(t, dosyalar.get(t.dosya_id)) for t in talepler]


@talep_router.post("")
async def talep_ac(request: Request, govde: BelgeTalebiGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    eposta = _eposta_dogrula(govde.client_email)
    baslik = (govde.baslik or "").strip()[:200]
    if not baslik:
        raise HTTPException(status_code=400, detail={"kod": "baslik_gerekli"})
    try:
        son_tarih = servis.son_tarih_duzelt(govde.son_tarih)
        turler = servis.kabul_turleri_duzelt(govde.kabul_turleri)
    except DosyaHatasi as h:
        raise _hata(h)
    t = BelgeTalepleri(
        client_email=eposta,
        proje_id=govde.proje_id,
        baslik=baslik,
        aciklama=(govde.aciklama or "").strip()[:4000] or None,
        son_tarih=son_tarih,
        kabul_turleri=turler,
        durum="bekliyor",
        olusturan=yonetici,
        created_at=servis.simdi(),
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    await _bildir(
        db,
        event_type="belge_talebi",
        title=f"Sizden bir belge istendi: {baslik}",
        body=(
            f"{baslik}" + (f"\n{t.aciklama}" if t.aciklama else "")
            + (f"\nSon tarih: {son_tarih}" if son_tarih else "")
            + "\nPanelinizdeki Dosyalar › İstenen belgeler bölümünden yükleyebilirsiniz."
        ),
        recipients=[{"email": eposta, "role": "client"}],
        link="/client?sekme=dosyalar",
        ref_type="belge_talebi",
        ref_id=t.id,
    )
    return servis.talep_sozlugu(t)


@talep_router.post("/{talep_id}/iptal")
async def talep_iptal(talep_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    t = (await db.execute(select(BelgeTalepleri).where(BelgeTalepleri.id == talep_id))).scalars().first()
    if t is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    if t.durum == "bekliyor":
        t.durum = "iptal"
        await db.commit()
    return servis.talep_sozlugu(t)


# ---------------------------------------------------------------------------
# Müşteri
# ---------------------------------------------------------------------------
@musteri_router.get("")
async def musteri_listesi(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = _musteri(request)
    klasorler = await servis.musteri_klasorleri(db, eposta)
    gorunur = sorted(ad for ad, g in klasorler.items() if g == "musteri")
    satirlar = []
    if gorunur:
        satirlar = (
            await db.execute(
                select(Dosyalar)
                .where(Dosyalar.client_email == eposta, Dosyalar.guncel.is_(True), Dosyalar.klasor.in_(gorunur))
                .order_by(Dosyalar.id.desc())
                .limit(500)
            )
        ).scalars().all()
    return {
        "klasorler": gorunur,
        "dosyalar": [servis.dosya_sozlugu(d, "musteri") for d in satirlar],
        "boyut_siniri_mb": (await servis.boyut_siniri_bayt(db)) // (1024 * 1024),
        "izinli_turler": sorted(servis.IZINLI_TURLER),
    }


@musteri_router.post("/yukle")
async def musteri_yukle(
    request: Request,
    klasor: Optional[str] = Form(None),
    dosya: UploadFile = File(...),
    db: AsyncSession = _Depends(get_db),
):
    eposta = _musteri(request)
    kisi = kisi_eposta(request)
    klasor_adi = servis.klasor_temizle(klasor, servis.MUSTERI_KLASORU)
    mevcut = await servis.klasor_getir(db, eposta, klasor_adi)
    if mevcut is not None and mevcut.gorunurluk != "musteri":
        # Ekip klasörüne müşteri yazamaz (varlığını da söylemiyoruz: 404).
        raise HTTPException(status_code=404, detail={"kod": "klasor_yok"})
    try:
        veri = await servis.akistan_oku(dosya, await servis.boyut_siniri_bayt(db))
        await servis.klasor_hazirla(db, eposta, klasor_adi, "musteri")
        kayit = await servis.dosya_kaydet(
            db, eposta=eposta, klasor=klasor_adi, ad_ham=dosya.filename or "", veri=veri,
            yukleyen=kisi, yukleyen_rol="client",
        )
        await db.commit()
        await db.refresh(kayit)
    except DosyaHatasi as h:
        await db.rollback()
        raise _hata(h)
    await _bildir(
        db,
        event_type="dosya_eklendi",
        title=f"Müşteri dosya yükledi: {kayit.ad}",
        body=f"{_kim(kisi, eposta)} → {klasor_adi}/{kayit.ad} ({_boyut_metni(kayit.boyut)})",
        recipients=await _yoneticiler(db),
        link="/admin",
        ref_type="dosya",
        ref_id=kayit.id,
    )
    return servis.dosya_sozlugu(kayit, "musteri")


@musteri_router.post("/{dosya_id}/indirme-baglantisi")
async def musteri_indirme(dosya_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = _musteri(request)
    return _indirme_yaniti(await _musteri_dosyasi(db, eposta, dosya_id))


@musteri_router.get("/talepler")
async def musteri_talepleri(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = _musteri(request)
    talepler = list(
        (
            await db.execute(
                select(BelgeTalepleri)
                .where(BelgeTalepleri.client_email == eposta, BelgeTalepleri.durum != "iptal")
                .order_by(BelgeTalepleri.id.desc())
                .limit(200)
            )
        ).scalars().all()
    )
    dosyalar = await _talep_dosyalari(db, talepler)
    return [servis.talep_sozlugu(t, dosyalar.get(t.dosya_id)) for t in talepler]


@musteri_router.post("/talepler/{talep_id}/yukle")
async def talebe_yukle(
    talep_id: int,
    request: Request,
    dosya: UploadFile = File(...),
    db: AsyncSession = _Depends(get_db),
):
    eposta = _musteri(request)
    kisi = kisi_eposta(request)
    t = (await db.execute(select(BelgeTalepleri).where(BelgeTalepleri.id == talep_id))).scalars().first()
    if t is None or t.client_email != eposta:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    if t.durum == "iptal":
        raise HTTPException(status_code=409, detail={"kod": "talep_iptal"})
    turler = [u for u in (t.kabul_turleri or "").split(",") if u]
    try:
        veri = await servis.akistan_oku(dosya, await servis.boyut_siniri_bayt(db))
        await servis.klasor_hazirla(db, eposta, servis.BELGE_KLASORU, "musteri")
        kayit = await servis.dosya_kaydet(
            db, eposta=eposta, klasor=servis.BELGE_KLASORU, ad_ham=dosya.filename or "", veri=veri,
            yukleyen=kisi, yukleyen_rol="client", proje_id=t.proje_id, belge_talebi_id=t.id,
            izinli=turler or None,
        )
        ilk_teslim = t.durum != "teslim_edildi"
        t.durum = "teslim_edildi"
        t.dosya_id = kayit.id
        t.teslim_at = servis.simdi()
        await db.commit()
        await db.refresh(kayit)
        await db.refresh(t)
    except DosyaHatasi as h:
        await db.rollback()
        raise _hata(h)
    await _bildir(
        db,
        event_type="belge_teslim",
        title=f"Belge teslim edildi: {t.baslik}" + ("" if ilk_teslim else " (yeni sürüm)"),
        body=f"{_kim(kisi, eposta)} istenen belgeyi yükledi: {kayit.ad} ({_boyut_metni(kayit.boyut)}).",
        recipients=await _yoneticiler(db),
        link="/admin",
        ref_type="belge_talebi",
        ref_id=t.id,
    )
    return servis.talep_sozlugu(t, kayit)


# ---------------------------------------------------------------------------
# Açık — imzalı indirme ve paylaşım bağlantısı
# ---------------------------------------------------------------------------
_GUVENLI_BASLIKLAR = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
    # Tarayıcıda açılsa bile betik çalışmasın.
    "Content-Security-Policy": "sandbox; default-src 'none'",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
}


@acik_router.get("/dosya-indir/{dosya_id}")
async def imzali_indir(
    dosya_id: int,
    son: Optional[str] = Query(None),
    imza: Optional[str] = Query(None),
    db: AsyncSession = _Depends(get_db),
):
    if not servis.imza_gecerli_mi(dosya_id, son, imza):
        raise HTTPException(status_code=403, detail={"kod": "imza_gecersiz"})
    d = (await db.execute(select(Dosyalar).where(Dosyalar.id == dosya_id))).scalars().first()
    if d is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    dogrudan = dosya_deposu.dogrudan_adres(d.depo, d.depolama_anahtari, d.ad, d.tur, sure_sn=servis.IMZA_SURESI_SN)
    if dogrudan:
        return RedirectResponse(dogrudan, status_code=302, headers={"Cache-Control": "private, no-store"})
    try:
        veri = await dosya_deposu.oku(db, d.depo, d.depolama_anahtari)
    except dosya_deposu.DepoHatasi:
        raise HTTPException(status_code=404, detail={"kod": "icerik_yok"})
    return Response(
        content=veri,
        media_type=d.tur,
        headers={**_GUVENLI_BASLIKLAR, "Content-Disposition": dosya_deposu.icerik_konumu(d.ad)},
    )


class PaylasimIndirGirdisi(BaseModel):
    sifre: Optional[str] = None


@acik_router.get("/paylas/{jeton}")
async def paylasim_bilgisi(jeton: str, db: AsyncSession = _Depends(get_db)):
    p = await servis.paylasim_bul(db, jeton)
    if p is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    durum = servis.paylasim_durumu(p)
    if durum != "gecerli":
        raise HTTPException(status_code=410, detail={"kod": durum})
    d = (await db.execute(select(Dosyalar).where(Dosyalar.id == p.dosya_id))).scalars().first()
    if d is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    kalan = None if p.indirme_siniri is None else max(0, int(p.indirme_siniri) - int(p.indirme_sayisi or 0))
    # Müşteri e-postası, klasör, depo anahtarı YOK: yalnız indirmek için gereken.
    return {
        "ad": d.ad,
        "boyut": int(d.boyut or 0),
        "tur": d.tur,
        "sifreli": bool(p.sifre_ozeti),
        "son_kullanma": servis.utc(p.son_kullanma).isoformat(),  # type: ignore[union-attr]
        "kalan_indirme": kalan,
    }


@acik_router.post("/paylas/{jeton}/indir")
async def paylasimdan_indir(jeton: str, govde: PaylasimIndirGirdisi = Body(default=PaylasimIndirGirdisi()), db: AsyncSession = _Depends(get_db)):
    """Parola doğruysa sayaç artar ve 2 dakikalık imzalı indirme adresi döner."""
    try:
        _p, d = await servis.paylasimdan_indir(db, jeton, govde.sifre)
    except DosyaHatasi as h:
        raise _hata(h)
    yol, son = servis.imzali_yol(d.id, sure_sn=servis.PAYLASIM_INDIRME_SURESI_SN)
    return {"adres": yol, "son": son, "ad": d.ad}


router = (yonetici_router, talep_router, musteri_router, acik_router)
