"""Faz 3T — teklif (öneri) uçları. Ayrıntı: `services/teklifler.py`.

Üç kapı
-------
* Yönetici `/api/v1/teklif-yonetim`: CRUD, hesap önizleme, gönder (bağlantı
  YALNIZ bu yanıtta bir kez), revize, PDF, fiyat sihirbazından "teklife çevir".
* Girişsiz `/api/v1/teklif/{jeton}`: görüntüle (sayaç artar), karar (kabul —
  ad soyad — / gerekçeli ret; tek), PDF. IP başına dakikada 20 istek.
* Müşteri `/api/v1/tekliflerim` (`faturalar` izni, `teklifler` modülü):
  kendi teklifleri (taslak görünmez), panelden karar, PDF. E-posta jetondan.

Hata gövdesi `{"detail": {"kod": ...}}`; metni ön yüz yedi dilde kuruyor.
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
from models.teklifler import Teklifler
from pydantic import BaseModel, ConfigDict, Field
from services import teklifler as servis
from services.belge_hesap import HesapHatasi, belge_hesapla
from services.teklifler import TeklifHatasi
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

acik_router = APIRouter(prefix="/api/v1/teklif", tags=["teklif"])
yonetici_router = APIRouter(
    prefix="/api/v1/teklif-yonetim", tags=["teklif"], dependencies=[_Depends(yonetici_gerekli)]
)
musteri_router = APIRouter(
    prefix="/api/v1/tekliflerim",
    tags=["teklif"],
    dependencies=[_Depends(izin_gerekli("faturalar")), _Depends(modul_gerekli("teklifler"))],
)

# Faz 7H: imzalı bağlantı denemeleri — sayaç veritabanında (yeniden yayında sıfırlanmıyor).
hiz_siniri = KaliciHizSiniri("teklif-baglanti", 20)


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class KalemGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    aciklama: str
    adet: Any = 1
    birim_fiyat: Any
    kdv_orani: Any = 0
    indirim: Any = 0


class TeklifGirdisi(BaseModel):
    """İstemcinin gönderdiği toplamlar (ara/KDV/genel) şemada yok: sunucu hesaplar."""

    model_config = ConfigDict(extra="ignore")

    baslik: Optional[str] = None
    kalemler: Optional[List[Dict[str, Any]]] = None
    para_birimi: Optional[str] = None
    hesap_email: Optional[str] = None
    aday_ad: Optional[str] = None
    aday_eposta: Optional[str] = None
    gecerlilik: Optional[str] = None
    notlar: Optional[str] = None
    sartlar: Optional[str] = None
    otomatik_sozlesme: Optional[bool] = None
    sozlesme_sablon_id: Optional[int] = None
    otomatik_fatura: Optional[bool] = None
    pesinat_yuzde: Optional[Any] = None
    otomatik_proje: Optional[bool] = None
    #: Faz 3Z: kabulde oluşan projeye uygulanacak proje şablonu.
    proje_sablon_id: Optional[int] = None


class HesapGirdisi(BaseModel):
    kalemler: List[Dict[str, Any]] = []


class GonderGirdisi(BaseModel):
    eposta_gonder: bool = False


class KararGirdisi(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sonuc: str
    ad_soyad: Optional[str] = None
    not_: Optional[str] = Field(None, alias="not")


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _hata(h: Exception) -> HTTPException:
    durum = getattr(h, "durum", 400)
    detay = h.detay() if hasattr(h, "detay") else {"kod": getattr(h, "kod", "hata")}
    return HTTPException(status_code=durum, detail=detay)


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})
    return (kullanici.email or "").strip().lower()


async def _sinir(request: Request) -> str:
    ozet = ip_ozeti(istemci_ip(request))
    if not await izin_ver((hiz_siniri, ozet)):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={"kod": "sinir"})
    return ozet


def pdf_yaniti(veri: bytes, ad: str) -> Response:
    from services.dosya_deposu import icerik_konumu

    return Response(
        content=veri,
        media_type="application/pdf",
        headers={
            "Content-Disposition": icerik_konumu(ad),
            "Cache-Control": "no-store",
            "X-Robots-Tag": "noindex, nofollow",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _govde(girdi: BaseModel) -> Dict[str, Any]:
    return girdi.model_dump(exclude_unset=True)


async def _getir(db: AsyncSession, teklif_id: int) -> Teklifler:
    try:
        return await servis.getir(db, teklif_id)
    except TeklifHatasi as h:
        raise _hata(h)


def _acik_gorunum(teklif: Teklifler, kayit: Any) -> Dict[str, Any]:
    """Girişsiz sayfanın gördüğü alanlar: alıcı e-postası maskeli, iç alanlar yok."""
    from services import imzali_islem

    d = servis.sozluk(teklif)
    d.pop("musteri_eposta", None)
    for gizli in ("fatura_id", "sozlesme_id", "proje_id", "created_at"):
        d.pop(gizli, None)
    gecerli = kayit.id == teklif.islem_id
    d["baglanti_durumu"] = imzali_islem.gecerli_durum(kayit) if gecerli else "iptal"
    d["karar_verilebilir"] = (
        gecerli and d["baglanti_durumu"] == "bekliyor" and teklif.durum in servis.ACIK_DURUMLAR
        and not servis.suresi_gecti_mi(teklif)
    )
    d["alici"] = imzali_islem.eposta_maskele(kayit.alici_eposta)
    d["son_kullanma"] = imzali_islem._utc(kayit.son_kullanma).isoformat() if kayit.son_kullanma else None
    return d


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("")
async def liste(
    request: Request,
    durum: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=120),
    adet: int = Query(300, ge=1, le=1000),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    await servis.sureleri_isle(db)
    sorgu = select(Teklifler)
    if durum:
        sorgu = sorgu.where(Teklifler.durum == durum)
    if q:
        kalip = f"%{q.strip().lower()}%"
        sorgu = sorgu.where(or_(Teklifler.no.ilike(kalip), Teklifler.baslik.ilike(kalip),
                                Teklifler.hesap_email.ilike(kalip), Teklifler.aday_eposta.ilike(kalip)))
    satirlar = (await db.execute(sorgu.order_by(Teklifler.id.desc()).limit(adet))).scalars().all()
    return [servis.sozluk(t, yonetici=True) for t in satirlar]


@yonetici_router.post("/hesapla")
async def hesapla(request: Request, govde: HesapGirdisi = Body(...)):
    """Önizleme: kalemlerden toplamlar (formdaki canlı toplamla aynı kural)."""
    _yonetici_iste(request)
    try:
        belge = belge_hesapla(govde.kalemler, bos_olabilir=True)
    except HesapHatasi as h:
        raise HTTPException(status_code=400, detail=h.detay())
    return {"kalemler": belge.kalem_listesi(), **belge.ozet()}


@yonetici_router.get("/fiyat-talepleri")
async def fiyat_talepleri(request: Request, db: AsyncSession = _Depends(get_db)):
    """"Teklife çevir" seçicisi: son sihirbaz kayıtları ve varsa bağlı teklif."""
    from models.pricing import Pricing_inquiries

    _yonetici_iste(request)
    talepler = (
        await db.execute(select(Pricing_inquiries).order_by(Pricing_inquiries.id.desc()).limit(100))
    ).scalars().all()
    bagli = {}
    if talepler:
        for t in (
            await db.execute(select(Teklifler).where(Teklifler.pricing_inquiry_id.in_([x.id for x in talepler])))
        ).scalars().all():
            bagli[t.pricing_inquiry_id] = {"id": t.id, "no": t.no, "durum": t.durum}
    return [
        {
            "id": t.id, "musteri_eposta": t.musteri_eposta, "musteri_adi": t.musteri_adi,
            "tutar": float(t.hesaplanan_tutar or 0), "period": t.period, "scale_kod": t.scale_kod,
            "ai_pm_tier_kod": t.ai_pm_tier_kod, "invoice_id": t.invoice_id, "durum": t.durum,
            "teklif": bagli.get(t.id),
        }
        for t in talepler
    ]


@yonetici_router.post("/fiyat-talebinden/{talep_id}")
async def fiyat_talebinden(talep_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    try:
        teklif = await servis.fiyat_talebinden(db, talep_id, yonetici)
    except TeklifHatasi as h:
        raise _hata(h)
    return servis.sozluk(teklif, yonetici=True)


@yonetici_router.post("")
async def olustur(request: Request, govde: TeklifGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    try:
        teklif = await servis.olustur(db, _govde(govde), yonetici)
    except TeklifHatasi as h:
        raise _hata(h)
    return servis.sozluk(teklif, yonetici=True)


@yonetici_router.get("/{teklif_id}")
async def ayrinti(teklif_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return servis.sozluk(await _getir(db, teklif_id), yonetici=True)


@yonetici_router.put("/{teklif_id}")
async def guncelle(teklif_id: int, request: Request, govde: TeklifGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    teklif = await _getir(db, teklif_id)
    try:
        teklif = await servis.guncelle(db, teklif, _govde(govde))
    except TeklifHatasi as h:
        raise _hata(h)
    return servis.sozluk(teklif, yonetici=True)


@yonetici_router.delete("/{teklif_id}")
async def sil(teklif_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    teklif = await _getir(db, teklif_id)
    try:
        await servis.sil(db, teklif)
    except TeklifHatasi as h:
        raise _hata(h)
    return {"silindi": teklif_id}


@yonetici_router.post("/{teklif_id}/gonder")
async def gonder(
    teklif_id: int, request: Request, govde: Optional[GonderGirdisi] = Body(None), db: AsyncSession = _Depends(get_db)
):
    """Bağlantıyı üretir. Ham bağlantı YALNIZ bu yanıtta, bir kez döner."""
    yonetici = _yonetici_iste(request)
    teklif = await _getir(db, teklif_id)
    try:
        adres, gitti = await servis.gonder(db, teklif, olusturan=yonetici,
                                           eposta_gonder=bool(govde and govde.eposta_gonder))
    except TeklifHatasi as h:
        raise _hata(h)
    return {"teklif": servis.sozluk(teklif, yonetici=True), "baglanti": adres, "eposta_gonderildi": gitti}


@yonetici_router.post("/{teklif_id}/revize")
async def revize(teklif_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    teklif = await _getir(db, teklif_id)
    try:
        yeni = await servis.revize_et(db, teklif, yonetici)
    except TeklifHatasi as h:
        raise _hata(h)
    return servis.sozluk(yeni, yonetici=True)


@yonetici_router.get("/{teklif_id}/pdf")
async def yonetici_pdf(teklif_id: int, request: Request, dil: str = Query("tr"), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    teklif = await _getir(db, teklif_id)
    from services.pdf_belge import dosya_adi

    return pdf_yaniti(await servis.pdf(db, teklif, dil), dosya_adi("teklif", teklif.no))


# --------------------------------------------------------------------------
# Girişsiz (jeton)
# --------------------------------------------------------------------------
@acik_router.get("/{jeton}")
async def acik_goruntule(jeton: str, request: Request, db: AsyncSession = _Depends(get_db)):
    await _sinir(request)
    try:
        teklif, kayit = await servis.jetondan(db, jeton)
    except TeklifHatasi as h:
        raise _hata(h)
    await servis.goruntulendi(db, teklif)
    return _acik_gorunum(teklif, kayit)


@acik_router.post("/{jeton}/karar")
async def acik_karar(jeton: str, request: Request, govde: KararGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    ip = await _sinir(request)
    try:
        teklif = await servis.karar_ver(
            db, jeton=jeton, sonuc=govde.sonuc, ad=govde.ad_soyad, not_=govde.not_, ip_ozeti=ip, kanal="baglanti"
        )
        _, kayit = await servis.jetondan(db, jeton)
    except TeklifHatasi as h:
        raise _hata(h)
    return _acik_gorunum(teklif, kayit)


@acik_router.get("/{jeton}/pdf")
async def acik_pdf(jeton: str, request: Request, dil: str = Query("tr"), db: AsyncSession = _Depends(get_db)):
    await _sinir(request)
    try:
        teklif, _ = await servis.jetondan(db, jeton)
    except TeklifHatasi as h:
        raise _hata(h)
    from services.pdf_belge import dosya_adi

    return pdf_yaniti(await servis.pdf(db, teklif, dil), dosya_adi("teklif", teklif.no))


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
def _musteri_kosulu(eposta: str):
    return or_(Teklifler.hesap_email == eposta, and_(Teklifler.hesap_email.is_(None), Teklifler.aday_eposta == eposta))


async def _musteri_teklifi(db: AsyncSession, teklif_id: int, eposta: str) -> Teklifler:
    teklif = (
        await db.execute(
            select(Teklifler).where(Teklifler.id == teklif_id, _musteri_kosulu(eposta),
                                    Teklifler.durum.in_(servis.MUSTERI_DURUMLARI))
        )
    ).scalar_one_or_none()
    if teklif is None:
        raise HTTPException(status_code=404, detail={"kod": "teklif_yok"})
    return teklif


def _musteri_gorunumu(teklif: Teklifler) -> Dict[str, Any]:
    d = servis.sozluk(teklif)
    d.pop("musteri_eposta", None)
    d["karar_verilebilir"] = teklif.durum in servis.ACIK_DURUMLAR and bool(teklif.islem_id) and not servis.suresi_gecti_mi(teklif)
    return d


@musteri_router.get("")
async def tekliflerim(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = musteri_baglami(request).hesap_email
    await servis.sureleri_isle(db)
    satirlar = (
        await db.execute(
            select(Teklifler)
            .where(_musteri_kosulu(eposta), Teklifler.durum.in_(servis.MUSTERI_DURUMLARI))
            .order_by(Teklifler.id.desc())
            .limit(200)
        )
    ).scalars().all()
    return [_musteri_gorunumu(t) for t in satirlar]


@musteri_router.get("/{teklif_id}")
async def teklifim(teklif_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = musteri_baglami(request).hesap_email
    return _musteri_gorunumu(await _musteri_teklifi(db, teklif_id, eposta))


@musteri_router.post("/{teklif_id}/karar")
async def teklifim_karar(
    teklif_id: int, request: Request, govde: KararGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    eposta = musteri_baglami(request).hesap_email
    teklif = await _musteri_teklifi(db, teklif_id, eposta)
    try:
        teklif = await servis.karar_ver(
            db, teklif=teklif, eposta=servis.alici(teklif), sonuc=govde.sonuc, ad=govde.ad_soyad, not_=govde.not_,
            ip_ozeti=ip_ozeti(istemci_ip(request)), kanal="panel",
        )
    except TeklifHatasi as h:
        raise _hata(h)
    return _musteri_gorunumu(teklif)


@musteri_router.get("/{teklif_id}/pdf")
async def teklifim_pdf(teklif_id: int, request: Request, dil: str = Query("tr"), db: AsyncSession = _Depends(get_db)):
    eposta = musteri_baglami(request).hesap_email
    teklif = await _musteri_teklifi(db, teklif_id, eposta)
    from services.pdf_belge import dosya_adi

    return pdf_yaniti(await servis.pdf(db, teklif, dil), dosya_adi("teklif", teklif.no))


router = (acik_router, yonetici_router, musteri_router)
