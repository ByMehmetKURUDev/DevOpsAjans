"""Faz 3T — sözleşme ve basit elektronik imza uçları. Ayrıntı: `services/sozlesmeler.py`.

* Yönetici `/api/v1/sozlesme-yonetim`: şablonlar (CRUD), sözleşmeler (şablondan
  ya da tekliften oluştur, düzenle — imzalıysa yeni sürüm —, gönder (bağlantı
  bir kez), iptal, sil (imzalı silinmez), sürümler, PDF, imza görseli).
* Girişsiz `/api/v1/sozlesme/{jeton}`: metni göster, imzala (tek), PDF.
* Müşteri `/api/v1/sozlesmelerim` (`faturalar` izni, `sozlesmeler` modülü).

Sayfada ve PDF'te: "Bu, 5070 sayılı Kanun anlamında güvenli elektronik imza
değildir; taraflar arasında basit elektronik onay kaydıdır."
"""

import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, musteri_baglami
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.yonetici_bekcisi import yonetici_gerekli
from dependencies.modul_bekcisi import modul_gerekli
from fastapi import APIRouter, Body, HTTPException, Query, Request, Response, status
from fastapi import Depends as _Depends
from models.sozlesmeler import SozlesmeSablonlari, Sozlesmeler
from pydantic import BaseModel, ConfigDict
from routers.teklifler import pdf_yaniti
from services import sozlesmeler as servis
from services.sozlesmeler import SozlesmeHatasi
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

acik_router = APIRouter(prefix="/api/v1/sozlesme", tags=["sozlesme"])
yonetici_router = APIRouter(
    prefix="/api/v1/sozlesme-yonetim", tags=["sozlesme"], dependencies=[_Depends(yonetici_gerekli)]
)
musteri_router = APIRouter(
    prefix="/api/v1/sozlesmelerim",
    tags=["sozlesme"],
    dependencies=[_Depends(izin_gerekli("faturalar")), _Depends(modul_gerekli("sozlesmeler"))],
)

hiz_siniri = HizSiniri(20)


class SablonGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    baslik: Optional[str] = None
    govde: Optional[str] = None
    baslik_en: Optional[str] = None
    govde_en: Optional[str] = None
    aktif: Optional[bool] = None


class SozlesmeGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sablon_id: Optional[int] = None
    teklif_id: Optional[int] = None
    baslik: Optional[str] = None
    govde: Optional[str] = None
    dil: Optional[str] = None
    hesap_email: Optional[str] = None
    taraf_ad: Optional[str] = None
    taraf_eposta: Optional[str] = None
    baslangic: Optional[str] = None
    bitis: Optional[str] = None


class GonderGirdisi(BaseModel):
    eposta_gonder: bool = False
    gun: Optional[int] = None


class ImzaGirdisi(BaseModel):
    ad_soyad: Optional[str] = None
    onay: bool = False
    #: Sayfada gösterilen metnin özeti (sunucu kendi özetiyle karşılaştırır).
    metin_ozeti: Optional[str] = None
    #: İsteğe bağlı el çizimi: `data:image/png;base64,...`
    imza_png: Optional[str] = None


def _hata(h: Exception) -> HTTPException:
    return HTTPException(status_code=getattr(h, "durum", 400), detail=h.detay() if hasattr(h, "detay") else {"kod": "hata"})


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})
    return (kullanici.email or "").strip().lower()


def _sinir(request: Request) -> str:
    ozet = ip_ozeti(istemci_ip(request))
    if not hiz_siniri.izin_var_mi(ozet):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={"kod": "sinir"})
    return ozet


async def _getir(db: AsyncSession, sozlesme_id: int) -> Sozlesmeler:
    try:
        return await servis.getir(db, sozlesme_id)
    except SozlesmeHatasi as h:
        raise _hata(h)


def _acik_gorunum(s: Sozlesmeler, kayit: Any) -> Dict[str, Any]:
    from services import imzali_islem

    d = servis.sozluk(s)
    for gizli in ("teklif_id", "created_at"):
        d.pop(gizli, None)
    gecerli = kayit.id == s.islem_id
    d["baglanti_durumu"] = imzali_islem.gecerli_durum(kayit) if gecerli else "iptal"
    d["imzalanabilir"] = gecerli and d["baglanti_durumu"] == "bekliyor" and s.durum == "gonderildi"
    d["alici"] = imzali_islem.eposta_maskele(kayit.alici_eposta)
    d["son_kullanma"] = imzali_islem._utc(kayit.son_kullanma).isoformat() if kayit.son_kullanma else None
    return d


# --------------------------------------------------------------------------
# Yönetici — şablonlar
# --------------------------------------------------------------------------
@yonetici_router.get("/sablonlar")
async def sablonlar(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    satirlar = (await db.execute(select(SozlesmeSablonlari).order_by(SozlesmeSablonlari.id.desc()))).scalars().all()
    return {
        "sablonlar": [servis.sablon_sozlugu(s) for s in satirlar],
        "yer_tutucular": ["musteri_adi", "musteri_eposta", "teklif_no", "teklif_baslik", "toplam", "tarih",
                          "baslangic", "bitis", "ajans_unvani", "sozlesme_no"],
        "varsayilan_govde": servis.VARSAYILAN_SABLON_TR,
    }


@yonetici_router.post("/sablonlar")
async def sablon_ekle(request: Request, govde: SablonGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        return servis.sablon_sozlugu(await servis.sablon_yaz(db, govde.model_dump(exclude_unset=True)))
    except SozlesmeHatasi as h:
        raise _hata(h)


@yonetici_router.put("/sablonlar/{sablon_id}")
async def sablon_guncelle(sablon_id: int, request: Request, govde: SablonGirdisi = Body(...),
                          db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    sablon = (await db.execute(select(SozlesmeSablonlari).where(SozlesmeSablonlari.id == sablon_id))).scalar_one_or_none()
    if sablon is None:
        raise HTTPException(status_code=404, detail={"kod": "sablon_yok"})
    try:
        return servis.sablon_sozlugu(await servis.sablon_yaz(db, govde.model_dump(exclude_unset=True), sablon))
    except SozlesmeHatasi as h:
        raise _hata(h)


@yonetici_router.delete("/sablonlar/{sablon_id}")
async def sablon_sil(sablon_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    sablon = (await db.execute(select(SozlesmeSablonlari).where(SozlesmeSablonlari.id == sablon_id))).scalar_one_or_none()
    if sablon is None:
        raise HTTPException(status_code=404, detail={"kod": "sablon_yok"})
    await db.delete(sablon)
    await db.commit()
    return {"silindi": sablon_id}


# --------------------------------------------------------------------------
# Yönetici — sözleşmeler
# --------------------------------------------------------------------------
@yonetici_router.get("")
async def liste(
    request: Request,
    durum: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=120),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    sorgu = select(Sozlesmeler)
    if durum:
        sorgu = sorgu.where(Sozlesmeler.durum == durum)
    if q:
        kalip = f"%{q.strip().lower()}%"
        sorgu = sorgu.where(or_(Sozlesmeler.no.ilike(kalip), Sozlesmeler.baslik.ilike(kalip),
                                Sozlesmeler.hesap_email.ilike(kalip), Sozlesmeler.taraf_eposta.ilike(kalip)))
    satirlar = (await db.execute(sorgu.order_by(Sozlesmeler.id.desc()).limit(500))).scalars().all()
    return [servis.sozluk(s, yonetici=True) for s in satirlar]


@yonetici_router.post("")
async def olustur(request: Request, govde: SozlesmeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    try:
        s = await servis.olustur(db, govde.model_dump(exclude_unset=True), yonetici)
    except SozlesmeHatasi as h:
        raise _hata(h)
    return servis.sozluk(s, yonetici=True)


@yonetici_router.get("/{sozlesme_id}")
async def ayrinti(sozlesme_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return servis.sozluk(await _getir(db, sozlesme_id), yonetici=True)


@yonetici_router.get("/{sozlesme_id}/surumler")
async def surumler(sozlesme_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    s = await _getir(db, sozlesme_id)
    satirlar = (
        await db.execute(select(Sozlesmeler).where(Sozlesmeler.kok_id == (s.kok_id or s.id)).order_by(Sozlesmeler.surum))
    ).scalars().all()
    return [servis.sozluk(x, yonetici=True) for x in satirlar]


@yonetici_router.put("/{sozlesme_id}")
async def guncelle(sozlesme_id: int, request: Request, govde: SozlesmeGirdisi = Body(...),
                   db: AsyncSession = _Depends(get_db)):
    """İmzalı sözleşmede metin değişikliği yeni sürüm açar (`yeni_surum: true`, 201 değil 200)."""
    _yonetici_iste(request)
    s = await _getir(db, sozlesme_id)
    try:
        sonuc, yeni = await servis.guncelle(db, s, govde.model_dump(exclude_unset=True))
    except SozlesmeHatasi as h:
        raise _hata(h)
    return {**servis.sozluk(sonuc, yonetici=True), "yeni_surum": yeni}


@yonetici_router.delete("/{sozlesme_id}")
async def sil(sozlesme_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    s = await _getir(db, sozlesme_id)
    try:
        await servis.sil(db, s)
    except SozlesmeHatasi as h:
        raise _hata(h)
    return {"silindi": sozlesme_id}


@yonetici_router.post("/{sozlesme_id}/gonder")
async def gonder(sozlesme_id: int, request: Request, govde: Optional[GonderGirdisi] = Body(None),
                 db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    s = await _getir(db, sozlesme_id)
    govde = govde or GonderGirdisi()
    try:
        adres, gitti = await servis.gonder(db, s, olusturan=yonetici, gun=govde.gun, eposta_gonder=govde.eposta_gonder)
    except SozlesmeHatasi as h:
        raise _hata(h)
    return {"sozlesme": servis.sozluk(s, yonetici=True), "baglanti": adres, "eposta_gonderildi": gitti}


@yonetici_router.post("/{sozlesme_id}/iptal")
async def iptal(sozlesme_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    s = await _getir(db, sozlesme_id)
    try:
        s = await servis.iptal_et(db, s)
    except SozlesmeHatasi as h:
        raise _hata(h)
    return servis.sozluk(s, yonetici=True)


@yonetici_router.get("/{sozlesme_id}/pdf")
async def yonetici_pdf(sozlesme_id: int, request: Request, dil: Optional[str] = Query(None),
                       db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    s = await _getir(db, sozlesme_id)
    from services.pdf_belge import dosya_adi

    return pdf_yaniti(await servis.pdf(db, s, dil), dosya_adi("sozlesme", f"{s.no}-v{s.surum}"))


@yonetici_router.get("/{sozlesme_id}/imza-gorseli")
async def imza_gorseli(sozlesme_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    s = await _getir(db, sozlesme_id)
    veri = await servis.imza_gorseli(db, s)
    if not veri:
        raise HTTPException(status_code=404, detail={"kod": "gorsel_yok"})
    return Response(content=veri, media_type="image/png", headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------
# Girişsiz (jeton)
# --------------------------------------------------------------------------
@acik_router.get("/{jeton}")
async def acik_goruntule(jeton: str, request: Request, db: AsyncSession = _Depends(get_db)):
    _sinir(request)
    try:
        s, kayit = await servis.jetondan(db, jeton)
    except SozlesmeHatasi as h:
        raise _hata(h)
    return _acik_gorunum(s, kayit)


@acik_router.post("/{jeton}/imza")
async def acik_imza(jeton: str, request: Request, govde: ImzaGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    ip = _sinir(request)
    try:
        s = await servis.imzala(
            db, jeton=jeton, ad=govde.ad_soyad, onay=govde.onay, gosterilen_ozet=govde.metin_ozeti,
            imza_png=govde.imza_png, ip_ozeti=ip, tarayici=request.headers.get("user-agent"), kanal="baglanti",
        )
        _, kayit = await servis.jetondan(db, jeton)
    except SozlesmeHatasi as h:
        raise _hata(h)
    return _acik_gorunum(s, kayit)


@acik_router.get("/{jeton}/pdf")
async def acik_pdf(jeton: str, request: Request, dil: Optional[str] = Query(None), db: AsyncSession = _Depends(get_db)):
    _sinir(request)
    try:
        s, _ = await servis.jetondan(db, jeton)
    except SozlesmeHatasi as h:
        raise _hata(h)
    from services.pdf_belge import dosya_adi

    return pdf_yaniti(await servis.pdf(db, s, dil), dosya_adi("sozlesme", f"{s.no}-v{s.surum}"))


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
def _musteri_kosulu(eposta: str):
    return or_(Sozlesmeler.hesap_email == eposta, and_(Sozlesmeler.hesap_email.is_(None), Sozlesmeler.taraf_eposta == eposta))


async def _musteri_sozlesmesi(db: AsyncSession, sozlesme_id: int, eposta: str) -> Sozlesmeler:
    s = (
        await db.execute(
            select(Sozlesmeler).where(Sozlesmeler.id == sozlesme_id, _musteri_kosulu(eposta),
                                      Sozlesmeler.durum.in_(servis.MUSTERI_DURUMLARI))
        )
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(status_code=404, detail={"kod": "sozlesme_yok"})
    return s


def _musteri_gorunumu(s: Sozlesmeler) -> Dict[str, Any]:
    d = servis.sozluk(s)
    d["imzalanabilir"] = s.durum == "gonderildi" and bool(s.islem_id)
    return d


@musteri_router.get("")
async def sozlesmelerim(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = musteri_baglami(request).hesap_email
    satirlar = (
        await db.execute(
            select(Sozlesmeler)
            .where(_musteri_kosulu(eposta), Sozlesmeler.durum.in_(servis.MUSTERI_DURUMLARI))
            .order_by(Sozlesmeler.id.desc())
            .limit(200)
        )
    ).scalars().all()
    return [_musteri_gorunumu(s) for s in satirlar]


@musteri_router.get("/{sozlesme_id}")
async def sozlesmem(sozlesme_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = musteri_baglami(request).hesap_email
    return _musteri_gorunumu(await _musteri_sozlesmesi(db, sozlesme_id, eposta))


@musteri_router.post("/{sozlesme_id}/imza")
async def sozlesmem_imza(sozlesme_id: int, request: Request, govde: ImzaGirdisi = Body(...),
                         db: AsyncSession = _Depends(get_db)):
    eposta = musteri_baglami(request).hesap_email
    s = await _musteri_sozlesmesi(db, sozlesme_id, eposta)
    try:
        s = await servis.imzala(
            db, sozlesme=s, eposta=(s.taraf_eposta or s.hesap_email), ad=govde.ad_soyad, onay=govde.onay,
            gosterilen_ozet=govde.metin_ozeti, imza_png=govde.imza_png, ip_ozeti=ip_ozeti(istemci_ip(request)),
            tarayici=request.headers.get("user-agent"), kanal="panel",
        )
    except SozlesmeHatasi as h:
        raise _hata(h)
    return _musteri_gorunumu(s)


@musteri_router.get("/{sozlesme_id}/pdf")
async def sozlesmem_pdf(sozlesme_id: int, request: Request, dil: Optional[str] = Query(None),
                        db: AsyncSession = _Depends(get_db)):
    eposta = musteri_baglami(request).hesap_email
    s = await _musteri_sozlesmesi(db, sozlesme_id, eposta)
    from services.pdf_belge import dosya_adi

    return pdf_yaniti(await servis.pdf(db, s, dil), dosya_adi("sozlesme", f"{s.no}-v{s.surum}"))


router = (acik_router, yonetici_router, musteri_router)
