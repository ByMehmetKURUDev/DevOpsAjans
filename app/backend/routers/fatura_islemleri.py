"""Faz 3T — fatura geliştirmeleri uçları (mevcut `invoices` + `payments` üzerine).

Yönetici `/api/v1/fatura-yonetim`
    POST /hesapla                        kalemlerden toplam önizlemesi (sunucu kuralı)
    GET  /yaslandirma                    alacak yaşlandırma (müşteri × para birimi)
    GET  /ajans  · PUT /ajans            PDF başlığındaki ajans bilgileri (site ayarları)
    GET  /tekrarlayan                    abonelikler + fatura alanları (tek kaynak: abonelik)
    POST /tekrarlayan                    yeni abonelik + otomatik fatura
    PUT  /tekrarlayan/{abonelik_id}      fatura alanlarını aç/kapat/düzenle
    POST /tekrarlayan/calistir           zamanı gelen dönemleri şimdi kes (idempotent)
    GET  /{id}                           ayrıntı: kalemler, KDV dökümü, ödemeler, iadeler, bakiye
    POST /{id}/odemeler                  kısmi ödeme (çok parçalı form: dekont isteğe bağlı)
    DELETE /odemeler/{pid}               ödeme sil (durum yeniden hesaplanır)
    GET  /odemeler/{pid}/dekont          dekontun imzalı (15 dk) indirme adresi
    POST /{id}/iade                      iade (alacak) faturası
    POST /{id}/odeme-baglantisi          kalan bakiyeyle `/ode/<jeton>`
    GET  /{id}/pdf                       fatura PDF'i

Müşteri `/api/v1/faturalarim` (`faturalar` izni): liste (bakiye), ayrıntı,
PDF, ödeme bağlantısı, dekont. E-posta etkin hesaptan (jeton + `X-MK-Hesap`).
"""

import json
import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, musteri_baglami
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi import Depends as _Depends
from models.invoices import Invoices
from models.payments import Payments
from pydantic import BaseModel, ConfigDict
from routers.teklifler import pdf_yaniti
from services import faturalar as servis
from services.belge_hesap import HesapHatasi, belge_hesapla, kayitli_kalemler, para_birimi_duzelt
from services.faturalar import FaturaHatasi
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(
    prefix="/api/v1/fatura-yonetim", tags=["fatura"], dependencies=[_Depends(yonetici_gerekli)]
)
musteri_router = APIRouter(
    prefix="/api/v1/faturalarim",
    tags=["fatura"],
    dependencies=[_Depends(izin_gerekli("faturalar"))],
)


class HesapGirdisi(BaseModel):
    kalemler: List[Dict[str, Any]] = []
    tur: Optional[str] = None


class IadeGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tutar: Optional[Any] = None
    kalemler: Optional[List[Dict[str, Any]]] = None
    neden: Optional[str] = None


class AjansGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    unvan: Optional[str] = None
    adres: Optional[str] = None
    vergi_dairesi: Optional[str] = None
    vergi_no: Optional[str] = None
    iban: Optional[str] = None
    eposta: Optional[str] = None
    telefon: Optional[str] = None


class TekrarlayanGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    client_email: Optional[str] = None
    client_name: Optional[str] = None
    hizmet: Optional[str] = None
    baslik: Optional[str] = None
    para_birimi: Optional[str] = None
    periyot: Optional[str] = None
    fatura_otomatik: Optional[bool] = None
    fatura_kalemleri: Optional[List[Dict[str, Any]]] = None
    fatura_baslangic: Optional[str] = None
    vade_gun: Optional[int] = None


def _hata(h: Exception) -> HTTPException:
    return HTTPException(status_code=getattr(h, "durum", 400), detail=h.detay() if hasattr(h, "detay") else {"kod": "hata"})


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})
    return (kullanici.email or "").strip().lower()


async def _fatura(db: AsyncSession, fatura_id: int) -> Invoices:
    try:
        return await servis.fatura_getir(db, fatura_id)
    except FaturaHatasi as h:
        raise _hata(h)


# --------------------------------------------------------------------------
# Yönetici — sabit yollar (önce: "/{id}" bunları yutmasın)
# --------------------------------------------------------------------------
@yonetici_router.post("/hesapla")
async def hesapla(request: Request, govde: HesapGirdisi = Body(...)):
    _yonetici_iste(request)
    try:
        belge = belge_hesapla(govde.kalemler, eksi_olabilir=govde.tur == "iade", bos_olabilir=True)
    except HesapHatasi as h:
        raise HTTPException(status_code=400, detail=h.detay())
    return {"kalemler": belge.kalem_listesi(), **belge.ozet()}


@yonetici_router.get("/yaslandirma")
async def yaslandirma(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return await servis.yaslandirma(db)


AJANS_ALANLARI = {
    "unvan": ("fatura_unvan", "Fatura: ajans unvanı"),
    "adres": ("fatura_adres", "Fatura: adres"),
    "vergi_dairesi": ("fatura_vergi_dairesi", "Fatura: vergi dairesi"),
    "vergi_no": ("fatura_vergi_no", "Fatura: vergi no"),
    "iban": ("fatura_iban", "Fatura: IBAN"),
    "eposta": ("fatura_eposta", "Fatura: e-posta"),
    "telefon": ("fatura_telefon", "Fatura: telefon"),
}


@yonetici_router.get("/ajans")
async def ajans_oku(request: Request, db: AsyncSession = _Depends(get_db)):
    """Kayıtlı değerler (boş = PDF'te gösterilmez) + PDF'te kullanılacak hâli (yedeklerle)."""
    from models.site_settings import Site_settings

    _yonetici_iste(request)
    anahtarlar = [a for a, _ in AJANS_ALANLARI.values()]
    satirlar = (await db.execute(select(Site_settings).where(Site_settings.setting_key.in_(anahtarlar)))).scalars().all()
    degerler = {s.setting_key: s.setting_value or "" for s in satirlar}
    return {
        "kayitli": {alan: degerler.get(anahtar, "") for alan, (anahtar, _) in AJANS_ALANLARI.items()},
        "pdf": await servis.ajans_bilgileri(db),
    }


@yonetici_router.put("/ajans")
async def ajans_yaz(request: Request, govde: AjansGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    from models.site_settings import Site_settings

    _yonetici_iste(request)
    veri = govde.model_dump(exclude_unset=True)
    for alan, deger in veri.items():
        anahtar, etiket = AJANS_ALANLARI[alan]
        temiz = " ".join(str(deger or "").split())[:300] if alan != "adres" else str(deger or "").strip()[:500]
        if alan == "iban":
            temiz = temiz.upper()
        satir = (await db.execute(select(Site_settings).where(Site_settings.setting_key == anahtar))).scalars().first()
        if satir is None:
            db.add(Site_settings(setting_key=anahtar, setting_value=temiz, group_name="fatura", label=etiket))
        else:
            satir.setting_value = temiz
    await db.commit()
    return await ajans_oku(request, db)


def _abonelik_sozlugu(a: Any) -> Dict[str, Any]:
    return {
        "id": a.id, "client_email": a.client_email, "client_name": a.client_name, "hizmet": a.hizmet,
        "baslik": a.baslik, "tutar": a.tutar, "para_birimi": a.para_birimi, "periyot": a.periyot, "durum": a.durum,
        "baslangic": a.baslangic, "fatura_otomatik": bool(a.fatura_otomatik),
        "fatura_kalemleri": kayitli_kalemler(a.fatura_kalemleri), "fatura_baslangic": a.fatura_baslangic,
        "vade_gun": a.vade_gun if a.vade_gun is not None else servis.VARSAYILAN_VADE_GUN,
        "son_fatura_donemi": a.son_fatura_donemi,
    }


async def _tekrarlayan_uygula(a: Any, govde: Dict[str, Any], *, yeni: bool) -> None:
    if "periyot" in govde or yeni:
        periyot = (govde.get("periyot") or "aylik").strip().lower()
        if periyot not in ("aylik", "yillik"):
            raise HTTPException(status_code=400, detail={"kod": "periyot_gecersiz"})
        a.periyot = periyot
    if "para_birimi" in govde or yeni:
        try:
            a.para_birimi = para_birimi_duzelt(govde.get("para_birimi"))
        except HesapHatasi as h:
            raise HTTPException(status_code=400, detail=h.detay())
    if "fatura_kalemleri" in govde or yeni:
        kalemler = govde.get("fatura_kalemleri") or []
        if kalemler:
            try:
                belge = belge_hesapla(kalemler)
            except HesapHatasi as h:
                raise HTTPException(status_code=400, detail=h.detay())
            a.fatura_kalemleri = json.dumps(
                [{k: v for k, v in x.items() if k in ("aciklama", "adet", "birim_fiyat", "kdv_orani", "indirim")}
                 for x in belge.kalem_listesi()], ensure_ascii=False,
            )
            a.tutar = float(belge.genel_toplam)
        else:
            a.fatura_kalemleri = None
    if "fatura_baslangic" in govde or yeni:
        ham = (govde.get("fatura_baslangic") or "").strip()[:7]
        if ham:
            try:
                yil, ay = (int(x) for x in ham.split("-"))
                if not (2000 <= yil <= 2100 and 1 <= ay <= 12):
                    raise ValueError
            except ValueError:
                raise HTTPException(status_code=400, detail={"kod": "donem_gecersiz"})
            a.fatura_baslangic = f"{yil:04d}-{ay:02d}"
        elif yeni or a.fatura_baslangic is None:
            bugun = servis.tr_bugun()
            a.fatura_baslangic = f"{bugun.year:04d}-{bugun.month:02d}"
    if "vade_gun" in govde:
        vade = govde.get("vade_gun")
        if vade is not None and not (0 <= int(vade) <= 365):
            raise HTTPException(status_code=400, detail={"kod": "vade_gecersiz"})
        a.vade_gun = vade
    if "fatura_otomatik" in govde or yeni:
        a.fatura_otomatik = bool(govde.get("fatura_otomatik", True))
    if a.fatura_otomatik and not kayitli_kalemler(a.fatura_kalemleri) and not a.tutar:
        raise HTTPException(status_code=400, detail={"kod": "kalem_gerekli"})
    if a.fatura_otomatik and not a.fatura_baslangic:
        bugun = servis.tr_bugun()
        a.fatura_baslangic = f"{bugun.year:04d}-{bugun.month:02d}"


@yonetici_router.get("/tekrarlayan")
async def tekrarlayan_liste(request: Request, db: AsyncSession = _Depends(get_db)):
    from models.service_subscriptions import Service_subscriptions

    _yonetici_iste(request)
    satirlar = (await db.execute(select(Service_subscriptions).order_by(Service_subscriptions.id.desc()))).scalars().all()
    sayilar = dict(
        (await db.execute(
            select(Invoices.tekrarlayan_id, func.count(Invoices.id))
            .where(Invoices.tekrarlayan_id.isnot(None)).group_by(Invoices.tekrarlayan_id)
        )).all()
    )
    return [{**_abonelik_sozlugu(a), "fatura_sayisi": int(sayilar.get(a.id, 0))} for a in satirlar]


@yonetici_router.post("/tekrarlayan")
async def tekrarlayan_ekle(request: Request, govde: TekrarlayanGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    from models.service_subscriptions import Service_subscriptions

    _yonetici_iste(request)
    veri = govde.model_dump(exclude_unset=True)
    eposta = servis.eposta_duzelt(veri.get("client_email"))
    from services.belge_ortak import eposta_gecerli

    if not eposta_gecerli(eposta):
        raise HTTPException(status_code=400, detail={"kod": "eposta_gecersiz"})
    baslik = " ".join(str(veri.get("baslik") or "").split())[:200]
    if not baslik:
        raise HTTPException(status_code=400, detail={"kod": "baslik_gerekli"})
    bugun = servis.tr_bugun()
    a = Service_subscriptions(
        client_email=eposta, client_name=(veri.get("client_name") or "").strip()[:200] or None,
        hizmet=(veri.get("hizmet") or "genel").strip()[:60] or "genel", baslik=baslik, durum="aktif",
        baslangic=f"{bugun.year:04d}-{bugun.month:02d}", sonraki_rapor=f"{bugun.year:04d}-{bugun.month:02d}",
    )
    veri.setdefault("fatura_otomatik", True)
    await _tekrarlayan_uygula(a, veri, yeni=True)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return {**_abonelik_sozlugu(a), "fatura_sayisi": 0}


@yonetici_router.put("/tekrarlayan/{abonelik_id}")
async def tekrarlayan_guncelle(abonelik_id: int, request: Request, govde: TekrarlayanGirdisi = Body(...),
                               db: AsyncSession = _Depends(get_db)):
    from models.service_subscriptions import Service_subscriptions

    _yonetici_iste(request)
    a = (await db.execute(select(Service_subscriptions).where(Service_subscriptions.id == abonelik_id))).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail={"kod": "abonelik_yok"})
    veri = govde.model_dump(exclude_unset=True)
    if "baslik" in veri and veri["baslik"]:
        a.baslik = " ".join(str(veri["baslik"]).split())[:200]
    await _tekrarlayan_uygula(a, veri, yeni=False)
    await db.commit()
    await db.refresh(a)
    return _abonelik_sozlugu(a)


@yonetici_router.post("/tekrarlayan/calistir")
async def tekrarlayan_calistir(request: Request, abonelik_id: Optional[int] = Query(None),
                               db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return await servis.tekrarlayan_faturalari_uret(db, abonelik_id=abonelik_id)


@yonetici_router.delete("/odemeler/{payment_id}")
async def odeme_sil(payment_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    satir = (await db.execute(select(Payments).where(Payments.id == payment_id))).scalar_one_or_none()
    if satir is None:
        raise HTTPException(status_code=404, detail={"kod": "odeme_yok"})
    if satir.durum == "bekliyor":
        raise HTTPException(status_code=409, detail={"kod": "bekleyen_baglanti"})
    fatura = await servis.odeme_sil(db, satir)
    await db.commit()
    if fatura is None:
        return {"silindi": payment_id}
    await db.refresh(fatura)
    return {"silindi": payment_id, "fatura": await servis.fatura_ozeti(db, fatura, yonetici=True)}


@yonetici_router.get("/odemeler/{payment_id}/dekont")
async def odeme_dekontu(payment_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    from services.dosyalar import imzali_yol

    _yonetici_iste(request)
    satir = (await db.execute(select(Payments).where(Payments.id == payment_id))).scalar_one_or_none()
    if satir is None or not satir.dekont_dosya_id:
        raise HTTPException(status_code=404, detail={"kod": "dekont_yok"})
    yol, son = imzali_yol(satir.dekont_dosya_id)
    return {"adres": yol, "son": son}


# --------------------------------------------------------------------------
# Yönetici — tek fatura
# --------------------------------------------------------------------------
@yonetici_router.get("/{fatura_id}")
async def ayrinti(fatura_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return await servis.fatura_ozeti(db, await _fatura(db, fatura_id), yonetici=True)


@yonetici_router.post("/{fatura_id}/odemeler")
async def odeme_ekle(
    fatura_id: int,
    request: Request,
    tutar: str = Form(...),
    yontem: str = Form("havale"),
    tarih: Optional[str] = Form(None),
    notu: Optional[str] = Form(None),
    geri_odeme: Optional[str] = Form(None),
    dekont: Optional[UploadFile] = File(None),
    db: AsyncSession = _Depends(get_db),
):
    """Kısmi (ya da tam) ödeme; dekont müşterinin "Dekontlar" klasörüne (dosya deposu)."""
    from services import kredi

    yonetici = _yonetici_iste(request)
    fatura = await _fatura(db, fatura_id)
    try:
        dekont_id = None
        if dekont is not None and (dekont.filename or "").strip():
            dekont_id = await servis.dekont_kaydet(db, fatura, dekont, yonetici)
        satir, kredi_ozeti = await servis.odeme_ekle(
            db, fatura, tutar=tutar, yontem=yontem, tarih=tarih, notu=notu, dekont_dosya_id=dekont_id,
            ekleyen=yonetici, geri_odeme=(geri_odeme or "").lower() in ("1", "true", "evet"),
        )
    except FaturaHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.commit()
    await kredi.kredi_yuklendi_bildir(db, kredi_ozeti)
    await db.refresh(fatura)
    return {"odeme_id": satir.id, "fatura": await servis.fatura_ozeti(db, fatura, yonetici=True)}


@yonetici_router.post("/{fatura_id}/iade")
async def iade(fatura_id: int, request: Request, govde: IadeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    fatura = await _fatura(db, fatura_id)
    try:
        iade_faturasi = await servis.iade_faturasi_kes(
            db, fatura, tutar=govde.tutar, kalemler=govde.kalemler, neden=govde.neden, ekleyen=yonetici
        )
    except FaturaHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.commit()
    await db.refresh(fatura)
    return {"iade_fatura_id": iade_faturasi.id, "iade_fatura_no": iade_faturasi.invoice_no,
            "fatura": await servis.fatura_ozeti(db, fatura, yonetici=True)}


@yonetici_router.post("/{fatura_id}/odeme-baglantisi")
async def odeme_baglantisi(fatura_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    fatura = await _fatura(db, fatura_id)
    try:
        kayit = await servis.baglanti_hazirla(db, fatura)
    except FaturaHatasi as h:
        raise _hata(h)
    return {"adres": f"/ode/{kayit.jeton}", "tutar": kayit.tutar, "payment_id": kayit.id}


@yonetici_router.get("/{fatura_id}/pdf")
async def yonetici_pdf(fatura_id: int, request: Request, dil: str = Query("tr"), db: AsyncSession = _Depends(get_db)):
    from services.pdf_belge import dosya_adi

    _yonetici_iste(request)
    fatura = await _fatura(db, fatura_id)
    return pdf_yaniti(await servis.fatura_pdf(db, fatura, dil), dosya_adi("fatura", fatura.invoice_no))


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
async def _musteri_faturasi(db: AsyncSession, fatura_id: int, eposta: str) -> Invoices:
    fatura = (
        await db.execute(
            select(Invoices).where(Invoices.id == fatura_id, func.lower(Invoices.client_email) == eposta)
        )
    ).scalar_one_or_none()
    if fatura is None:
        raise HTTPException(status_code=404, detail={"kod": "fatura_yok"})
    return fatura


@musteri_router.get("")
async def faturalarim(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = musteri_baglami(request).hesap_email
    satirlar = (
        await db.execute(
            select(Invoices).where(func.lower(Invoices.client_email) == eposta).order_by(Invoices.id.desc()).limit(300)
        )
    ).scalars().all()
    if not satirlar:
        return {"faturalar": [], "ozet": []}
    kimlikler = [f.id for f in satirlar]
    odemeler: Dict[int, List[Payments]] = {}
    for o in (await db.execute(select(Payments).where(Payments.invoice_id.in_(kimlikler)))).scalars().all():
        odemeler.setdefault(o.invoice_id, []).append(o)
    iadeler: Dict[int, List[Invoices]] = {}
    for f in satirlar:
        if f.tur == "iade" and f.bagli_fatura_id:
            iadeler.setdefault(f.bagli_fatura_id, []).append(f)
    liste = []
    ozet: Dict[str, Dict[str, float]] = {}
    for f in satirlar:
        if f.tur == "iade":
            b = None
        else:
            b = servis.bakiye_hesapla(f, odemeler.get(f.id, []), iadeler.get(f.id, []))
        bekleyen = next((o for o in reversed(odemeler.get(f.id, [])) if o.durum == "bekliyor" and o.jeton), None)
        liste.append({
            "id": f.id, "invoice_no": f.invoice_no, "description": f.description, "amount": float(servis.D(f.amount)),
            "currency": f.currency or "TRY", "status": f.status, "issue_date": f.issue_date, "due_date": f.due_date,
            "tur": f.tur or "normal", "bagli_fatura_id": f.bagli_fatura_id, "kalemli": bool(f.kalemler),
            "bakiye": b.sozluk() if b else None,
            "odeme_adresi": f"/ode/{bekleyen.jeton}" if bekleyen is not None else None,
        })
        if b is not None and (f.status or "") not in servis.KAPALI_DURUMLAR and b.kalan > servis.EPS:
            t = ozet.setdefault((f.currency or "TRY").upper(), {"kalan": 0.0, "adet": 0})
            t["kalan"] = round(t["kalan"] + float(b.kalan), 2)
            t["adet"] += 1
    return {"faturalar": liste, "ozet": [{"para_birimi": pb, **v} for pb, v in sorted(ozet.items())]}


@musteri_router.get("/{fatura_id}")
async def faturam(fatura_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    eposta = musteri_baglami(request).hesap_email
    return await servis.fatura_ozeti(db, await _musteri_faturasi(db, fatura_id, eposta))


@musteri_router.get("/{fatura_id}/pdf")
async def faturam_pdf(fatura_id: int, request: Request, dil: str = Query("tr"), db: AsyncSession = _Depends(get_db)):
    from services.pdf_belge import dosya_adi

    eposta = musteri_baglami(request).hesap_email
    fatura = await _musteri_faturasi(db, fatura_id, eposta)
    return pdf_yaniti(await servis.fatura_pdf(db, fatura, dil), dosya_adi("fatura", fatura.invoice_no))


@musteri_router.post("/{fatura_id}/odeme-baglantisi")
async def faturam_odeme(fatura_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Kalan bakiye için ödeme sayfası adresi (varsa mevcut bağlantı)."""
    eposta = musteri_baglami(request).hesap_email
    fatura = await _musteri_faturasi(db, fatura_id, eposta)
    try:
        kayit = await servis.baglanti_hazirla(db, fatura)
    except FaturaHatasi as h:
        raise _hata(h)
    return {"adres": f"/ode/{kayit.jeton}", "tutar": kayit.tutar}


@musteri_router.get("/{fatura_id}/odemeler/{payment_id}/dekont")
async def faturam_dekont(fatura_id: int, payment_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    from services.dosyalar import imzali_yol

    eposta = musteri_baglami(request).hesap_email
    fatura = await _musteri_faturasi(db, fatura_id, eposta)
    satir = (
        await db.execute(select(Payments).where(Payments.id == payment_id, Payments.invoice_id == fatura.id))
    ).scalar_one_or_none()
    if satir is None or not satir.dekont_dosya_id or satir.durum not in ("odendi", "iade"):
        raise HTTPException(status_code=404, detail={"kod": "dekont_yok"})
    yol, son = imzali_yol(satir.dekont_dosya_id)
    return {"adres": yol, "son": son}


router = (yonetici_router, musteri_router)
