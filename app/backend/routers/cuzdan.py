"""Faz 5C — Cüzdan ve bakiye (müşteri avansı) uçları. Kurallar `services/cuzdan.py`'de.

Yönetici `/api/v1/cuzdan-yonetim` (yalnız yönetici; panelde Ödemeler › Müşteri bakiyeleri)
    GET  /hesaplar                         cüzdanlar (bakiye, son hareket) + para birimi toplamları + bekleyen talepler
    GET  /hesap?eposta=&para_birimi=       hesap ayrıntısı: bakiyeler, defter (sayfalı), talepler, ayarlar
    GET  /ekstre?eposta=&para_birimi=&bicim=pdf|csv&bas=&bit=&dil=
    POST /yukle                            elle yükleme (çok parçalı form; dekont isteğe bağlı)
    POST /iade                             kullanılmayan bakiyenin müşteriye geri ödenmesi
    POST /duzeltme                         işaretli düzeltme (gerekçe zorunlu)
    POST /hareketler/{id}/ters             yükleme/iade/düzeltme satırının ters kaydı (bir kez)
    GET  /hareketler/{id}/dekont           dekontun imzalı (15 dk) indirme adresi
    GET  /talepler?durum=                  yükleme talepleri
    POST /talepler/{id}/onayla             (tutar/tarih/yöntem/not isteğe bağlı) → bakiye artar
    POST /talepler/{id}/reddet             {neden}
    GET  /talepler/{id}/dekont
    GET  /faturalar/{fatura_id}            faturanın para birimindeki bakiye + kalan (fatura ayrıntısı kutusu)
    POST /faturalar/{fatura_id}/uygula     {tutar?, istek_anahtari?} → bakiyeden ödeme
    GET  /ayarlar · PUT /ayarlar           müşteriye gösterilen havale bilgisi (boşsa fatura ayarlarındaki unvan/IBAN)

Müşteri `/api/v1/cuzdanim` (`faturalar` izni; e-posta etkin hesaptan — jeton + `X-MK-Hesap`)
    GET  ""                                bakiyeler, ayarlar (referans kodu), banka bilgisi, talepler, son hareketler
    GET  /hareketler?para_birimi=&sayfa=
    GET  /ekstre?para_birimi=&bicim=pdf|csv&bas=&bit=&dil=
    POST /yukleme-talepleri                (çok parçalı form: tutar, para_birimi, yontem, odeme_tarihi, notu, dekont)
    POST /yukleme-talepleri/{id}/iptal
    GET  /yukleme-talepleri/{id}/dekont
    PUT  /ayarlar                          otomatik ödeme (açarken onay), kısmi, zaman, düşük bakiye eşikleri
    POST /faturalar/{fatura_id}/ode        {tutar?, istek_anahtari?}
    GET  /odeme/{jeton}                    girişsiz ödeme sayfası (oturum varsa): bu hesabın faturası mı + bakiye
"""

import logging
from datetime import date
from typing import Any, Dict, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, musteri_baglami
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi import Depends as _Depends
from fastapi.responses import Response
from models.cuzdan import CuzdanHareketleri, CuzdanYuklemeTalepleri  # noqa: F401 - tablolar bu import'la kurulur
from models.invoices import Invoices
from pydantic import BaseModel, ConfigDict
from services import cuzdan as cz
from services.cuzdan import CuzdanHatasi
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/cuzdan-yonetim", tags=["cuzdan"], dependencies=[_Depends(yonetici_gerekli)])
musteri_router = APIRouter(prefix="/api/v1/cuzdanim", tags=["cuzdan"], dependencies=[_Depends(izin_gerekli("faturalar"))])


class OdemeGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tutar: Optional[Any] = None
    istek_anahtari: Optional[str] = None


class IadeGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hesap_email: Optional[str] = None
    para_birimi: Optional[str] = None
    tutar: Optional[Any] = None
    yontem: Optional[str] = None
    tarih: Optional[str] = None
    notu: Optional[str] = None


class DuzeltmeGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hesap_email: Optional[str] = None
    para_birimi: Optional[str] = None
    tutar: Optional[Any] = None
    gerekce: Optional[str] = None


class TersGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gerekce: Optional[str] = None


class OnayGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tutar: Optional[Any] = None
    tarih: Optional[str] = None
    yontem: Optional[str] = None
    notu: Optional[str] = None


class RetGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    neden: Optional[str] = None


class BankaGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    banka_adi: Optional[str] = None
    hesap_sahibi: Optional[str] = None
    iban: Optional[str] = None
    aciklama: Optional[str] = None


class AyarGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    otomatik_odeme: Optional[bool] = None
    onay: Optional[bool] = None
    otomatik_kismi: Optional[bool] = None
    otomatik_zaman: Optional[str] = None
    dusuk_esikler: Optional[Dict[str, Any]] = None


def _hata(h: CuzdanHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})
    return (kullanici.email or "").strip().lower()


def _eposta_q(ham: Optional[str]) -> str:
    from services.belge_ortak import eposta_gecerli

    e = cz.eposta_duzelt(ham)
    if not eposta_gecerli(e):
        raise HTTPException(status_code=400, detail={"kod": "eposta_gecersiz"})
    return e


def _pb(ham: Any) -> str:
    try:
        return cz.para_birimi_al(ham)
    except CuzdanHatasi as h:
        raise _hata(h)


async def _calistir(fn, *a, **k):
    try:
        return await fn(*a, **k)
    except CuzdanHatasi as h:
        raise _hata(h)


async def _fatura(db: AsyncSession, fatura_id: int) -> Invoices:
    f = (await db.execute(select(Invoices).where(Invoices.id == fatura_id))).scalar_one_or_none()
    if f is None:
        raise HTTPException(status_code=404, detail={"kod": "fatura_yok"})
    return f


def _tarih_q(ham: Optional[str], varsayilan: date) -> date:
    if not ham:
        return varsayilan
    try:
        return date.fromisoformat(str(ham)[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail={"kod": "tarih_gecersiz"})


async def _ekstre_yaniti(db: AsyncSession, eposta: str, pb: str, bicim: str, bas: Optional[str], bit: Optional[str], dil: str) -> Response:
    from services import cuzdan_pdf
    from services.dosya_deposu import icerik_konumu
    from services.faturalar import ajans_bilgileri

    bugun = cz.bugun()
    b1 = _tarih_q(bas, date(bugun.year, 1, 1))
    b2 = _tarih_q(bit, bugun)
    v = await _calistir(cz.ekstre_verisi, db, eposta, pb, b1, b2)
    ad = f"bakiye-ekstresi-{pb}-{b1.isoformat()}-{b2.isoformat()}"
    basliklar = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex, nofollow"}
    if bicim == "csv":
        return Response(cz.ekstre_csv(v, dil).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={**basliklar, "Content-Disposition": icerik_konumu(f"{ad}.csv")})
    if bicim != "pdf":
        raise HTTPException(status_code=400, detail={"kod": "bicim_gecersiz"})
    firma = (await ajans_bilgileri(db)).get("unvan")
    return Response(cuzdan_pdf.ekstre_pdf(v, dil, firma), media_type="application/pdf",
                    headers={**basliklar, "Content-Disposition": icerik_konumu(f"{ad}.pdf")})


async def _dekont_adresi(dosya_id: Optional[int]) -> Dict[str, Any]:
    from services.dosyalar import imzali_yol

    if not dosya_id:
        raise HTTPException(status_code=404, detail={"kod": "dekont_yok"})
    yol, son = imzali_yol(dosya_id)
    return {"adres": yol, "son": son}


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("/hesaplar")
async def hesaplar(request: Request, q: str = Query(""), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return {**await cz.yonetici_listesi(db, q), "banka": await cz.banka_bilgisi(db)}


@yonetici_router.get("/hesap")
async def hesap(request: Request, eposta: str = Query(...), para_birimi: Optional[str] = Query(None),
                sayfa: int = Query(1, ge=1, le=10000), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    pb = _pb(para_birimi) if para_birimi else None
    return await cz.yonetici_ayrintisi(db, _eposta_q(eposta), pb, sayfa)


@yonetici_router.get("/ekstre")
async def yonetici_ekstre(request: Request, eposta: str = Query(...), para_birimi: str = Query("TRY"), bicim: str = Query("pdf"),
                          bas: Optional[str] = Query(None), bit: Optional[str] = Query(None), dil: str = Query("tr"),
                          db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return await _ekstre_yaniti(db, _eposta_q(eposta), _pb(para_birimi), bicim, bas, bit, dil)


@yonetici_router.post("/yukle")
async def elle_yukle(
    request: Request,
    hesap_email: str = Form(...),
    tutar: str = Form(...),
    para_birimi: str = Form("TRY"),
    yontem: str = Form("havale"),
    tarih: Optional[str] = Form(None),
    notu: Optional[str] = Form(None),
    dekont: Optional[UploadFile] = File(None),
    db: AsyncSession = _Depends(get_db),
):
    yonetici = _yonetici_iste(request)
    try:
        h = await cz.elle_yukle(db, eposta=cz.eposta_duzelt(hesap_email), pb=cz.para_birimi_al(para_birimi), tutar=cz.tutar_al(tutar),
                                yontem=cz.yontem_al(yontem), tarih=cz.tarih_al(tarih), yonetici=yonetici, notu=cz.metin_al(notu),
                                dekont=dekont)
    except CuzdanHatasi as e:
        raise _hata(e)
    return {"hareket": cz.hareket_sozlugu(h, yonetici=True), "bakiye": cz.tl(h.sonra)}


@yonetici_router.post("/iade")
async def iade(request: Request, govde: IadeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    try:
        h = await cz.iade_et(db, eposta=_eposta_q(govde.hesap_email), pb=cz.para_birimi_al(govde.para_birimi),
                             tutar=cz.tutar_al(govde.tutar), yontem=cz.yontem_al(govde.yontem), tarih=cz.tarih_al(govde.tarih),
                             yonetici=yonetici, notu=cz.metin_al(govde.notu))
    except CuzdanHatasi as e:
        raise _hata(e)
    return {"hareket": cz.hareket_sozlugu(h, yonetici=True), "bakiye": cz.tl(h.sonra)}


@yonetici_router.post("/duzeltme")
async def duzeltme(request: Request, govde: DuzeltmeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    try:
        h = await cz.duzelt(db, eposta=_eposta_q(govde.hesap_email), pb=cz.para_birimi_al(govde.para_birimi),
                            tutar=cz.tutar_al(govde.tutar, isaretli=True), gerekce=govde.gerekce, yonetici=yonetici)
    except CuzdanHatasi as e:
        raise _hata(e)
    return {"hareket": cz.hareket_sozlugu(h, yonetici=True), "bakiye": cz.tl(h.sonra)}


@yonetici_router.post("/hareketler/{hareket_id}/ters")
async def ters(hareket_id: int, request: Request, govde: TersGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    h = await _calistir(cz.ters_kayit, db, hareket_id, gerekce=govde.gerekce, yonetici=yonetici)
    return {"hareket": cz.hareket_sozlugu(h, yonetici=True), "bakiye": cz.tl(h.sonra)}


@yonetici_router.get("/hareketler/{hareket_id}/dekont")
async def hareket_dekontu(hareket_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    h = (await db.execute(select(CuzdanHareketleri).where(CuzdanHareketleri.id == hareket_id))).scalars().first()
    return await _dekont_adresi(h.dekont_dosya_id if h else None)


@yonetici_router.get("/talepler")
async def talepler(request: Request, durum: str = Query("beklemede"), db: AsyncSession = _Depends(get_db)):
    from services.hesap_ekibi import hesap_adlari

    _yonetici_iste(request)
    sorgu = select(CuzdanYuklemeTalepleri)
    if durum != "hepsi":
        if durum not in ("beklemede", "onaylandi", "reddedildi", "iptal"):
            raise HTTPException(status_code=400, detail={"kod": "durum_gecersiz"})
        sorgu = sorgu.where(CuzdanYuklemeTalepleri.durum == durum)
    satirlar = (await db.execute(sorgu.order_by(CuzdanYuklemeTalepleri.id.desc()).limit(300))).scalars().all()
    adlar = await hesap_adlari(db, {t.hesap_email for t in satirlar})
    return {"items": [cz.talep_sozlugu(t, yonetici=True, ad=adlar.get(t.hesap_email)) for t in satirlar]}


@yonetici_router.post("/talepler/{talep_id}/onayla")
async def talep_onayla(talep_id: int, request: Request, govde: Optional[OnayGirdisi] = Body(None),
                       db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    g = govde or OnayGirdisi()
    try:
        h = await cz.talep_onayla(db, talep_id, yonetici=yonetici,
                                  tutar=cz.tutar_al(g.tutar) if g.tutar not in (None, "") else None,
                                  tarih=cz.tarih_al(g.tarih) if g.tarih else None,
                                  yontem=cz.yontem_al(g.yontem) if g.yontem else None, notu=cz.metin_al(g.notu))
    except CuzdanHatasi as e:
        raise _hata(e)
    t = (await db.execute(select(CuzdanYuklemeTalepleri).where(CuzdanYuklemeTalepleri.id == talep_id))).scalars().first()
    await db.refresh(t)
    return {"talep": cz.talep_sozlugu(t, yonetici=True), "hareket": cz.hareket_sozlugu(h, yonetici=True), "bakiye": cz.tl(h.sonra)}


@yonetici_router.post("/talepler/{talep_id}/reddet")
async def talep_reddet(talep_id: int, request: Request, govde: RetGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    t = await _calistir(cz.talep_reddet, db, talep_id, yonetici=yonetici, neden=govde.neden)
    return {"talep": cz.talep_sozlugu(t, yonetici=True)}


@yonetici_router.get("/talepler/{talep_id}/dekont")
async def talep_dekontu(talep_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    t = (await db.execute(select(CuzdanYuklemeTalepleri).where(CuzdanYuklemeTalepleri.id == talep_id))).scalars().first()
    return await _dekont_adresi(t.dekont_dosya_id if t else None)


@yonetici_router.get("/faturalar/{fatura_id}")
async def fatura_bilgisi(fatura_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return await cz.fatura_bakiye_bilgisi(db, await _fatura(db, fatura_id))


@yonetici_router.post("/faturalar/{fatura_id}/uygula")
async def faturaya_uygula(fatura_id: int, request: Request, govde: OdemeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    f = await _fatura(db, fatura_id)
    return await _calistir(cz.faturayi_ode, db, f, tutar=govde.tutar, yazan=yonetici, yazan_rol="admin",
                           istek_anahtari=govde.istek_anahtari)


@yonetici_router.get("/ayarlar")
async def ayarlar(request: Request, db: AsyncSession = _Depends(get_db)):
    from models.site_settings import Site_settings

    _yonetici_iste(request)
    anahtarlar = [k for k, _ in cz.BANKA_ANAHTARLARI.values()]
    degerler = {s.setting_key: s.setting_value or "" for s in (await db.execute(
        select(Site_settings).where(Site_settings.setting_key.in_(anahtarlar)))).scalars().all()}
    return {"kayitli": {alan: degerler.get(anahtar, "") for alan, (anahtar, _) in cz.BANKA_ANAHTARLARI.items()},
            "gosterilen": await cz.banka_bilgisi(db)}


@yonetici_router.put("/ayarlar")
async def ayarlar_yaz(request: Request, govde: BankaGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    await _calistir(cz.banka_bilgisi_yaz, db, govde.model_dump(exclude_unset=True))
    return await ayarlar(request, db)


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
def _hesap(request: Request) -> str:
    return musteri_baglami(request).hesap_email


@musteri_router.get("")
async def cuzdanim(request: Request, db: AsyncSession = _Depends(get_db)):
    return await cz.musteri_ozeti(db, _hesap(request))


@musteri_router.get("/hareketler")
async def hareketlerim(request: Request, para_birimi: Optional[str] = Query(None), sayfa: int = Query(1, ge=1, le=10000),
                       db: AsyncSession = _Depends(get_db)):
    pb = _pb(para_birimi) if para_birimi else None
    return await cz.hareketler(db, _hesap(request), pb, yonetici=False, sayfa=sayfa)


@musteri_router.get("/ekstre")
async def ekstrem(request: Request, para_birimi: str = Query("TRY"), bicim: str = Query("pdf"), bas: Optional[str] = Query(None),
                  bit: Optional[str] = Query(None), dil: str = Query("tr"), db: AsyncSession = _Depends(get_db)):
    return await _ekstre_yaniti(db, _hesap(request), _pb(para_birimi), bicim, bas, bit, dil)


@musteri_router.post("/yukleme-talepleri")
async def yukleme_talebi(
    request: Request,
    tutar: str = Form(...),
    para_birimi: str = Form("TRY"),
    yontem: str = Form("havale"),
    odeme_tarihi: Optional[str] = Form(None),
    notu: Optional[str] = Form(None),
    dekont: Optional[UploadFile] = File(None),
    db: AsyncSession = _Depends(get_db),
):
    b = musteri_baglami(request)
    try:
        t = await cz.talep_olustur(db, eposta=b.hesap_email, kisi=b.kisi_email, pb=cz.para_birimi_al(para_birimi),
                                   tutar=cz.tutar_al(tutar), yontem=cz.yontem_al(yontem), odeme_tarihi=cz.tarih_al(odeme_tarihi),
                                   notu=cz.metin_al(notu), dekont=dekont)
    except CuzdanHatasi as e:
        raise _hata(e)
    return {"talep": cz.talep_sozlugu(t, yonetici=False)}


@musteri_router.post("/yukleme-talepleri/{talep_id}/iptal")
async def talep_iptal(talep_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    t = await _calistir(cz.talep_iptal, db, talep_id, _hesap(request))
    return {"talep": cz.talep_sozlugu(t, yonetici=False)}


@musteri_router.get("/yukleme-talepleri/{talep_id}/dekont")
async def talep_dekontum(talep_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    t = (await db.execute(select(CuzdanYuklemeTalepleri).where(
        CuzdanYuklemeTalepleri.id == talep_id, CuzdanYuklemeTalepleri.hesap_email == _hesap(request)))).scalars().first()
    return await _dekont_adresi(t.dekont_dosya_id if t else None)


@musteri_router.put("/ayarlar")
async def ayarlarim(request: Request, govde: AyarGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    b = musteri_baglami(request)
    return await _calistir(cz.ayarlari_yaz, db, b.hesap_email, b.kisi_email, govde.model_dump(exclude_unset=True))


async def _musteri_faturasi(db: AsyncSession, fatura_id: int, eposta: str) -> Invoices:
    from services.faturalar import TASLAK_DURUMLARI
    from sqlalchemy import or_

    f = (await db.execute(select(Invoices).where(
        Invoices.id == fatura_id, func.lower(Invoices.client_email) == eposta,
        or_(Invoices.status.is_(None), Invoices.status.notin_(TASLAK_DURUMLARI))))).scalar_one_or_none()
    if f is None:
        raise HTTPException(status_code=404, detail={"kod": "fatura_yok"})
    return f


@musteri_router.post("/faturalar/{fatura_id}/ode")
async def faturami_ode(fatura_id: int, request: Request, govde: OdemeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    b = musteri_baglami(request)
    f = await _musteri_faturasi(db, fatura_id, b.hesap_email)
    return await _calistir(cz.faturayi_ode, db, f, tutar=govde.tutar, yazan=b.kisi_email, yazan_rol="musteri",
                           istek_anahtari=govde.istek_anahtari)


@musteri_router.get("/odeme/{jeton}")
async def odeme_sayfasi(jeton: str, request: Request, db: AsyncSession = _Depends(get_db)):
    """Girişsiz `/ode/<jeton>` sayfası, oturum varsa: jetonun faturası bu hesabınsa bakiye bilgisi (değilse 404 —
    başka hesabın faturası olduğu bile sızmaz)."""
    from models.payments import Payments

    eposta = _hesap(request)
    p = (await db.execute(select(Payments).where(Payments.jeton == jeton))).scalars().first()
    if p is None or not p.invoice_id:
        raise HTTPException(status_code=404, detail={"kod": "fatura_yok"})
    f = await _musteri_faturasi(db, p.invoice_id, eposta)
    return await cz.fatura_bakiye_bilgisi(db, f)


router = (yonetici_router, musteri_router)
