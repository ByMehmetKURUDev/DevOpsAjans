"""Faz 5K — ortaklık (referans) programı uçları. Ayrıntı: `services/ortaklik.py`.

Üç kapı
-------
* Herkese açık `/api/v1/ortaklik`: program bilgisi (koşul metni ayarlardan),
  başvuru (KVKK aydınlatma + ayrı pazarlama izni; IP özeti başına saatte 5,
  bal küpü), `?ref=` tıklaması (günlük toplam; IP saklanmaz, yalnız bellek içi
  hız sınırı).
* Ortak `/api/v1/ortakligim`: KİŞİYE ait (oturumdaki kişinin e-postası; ekip
  hesabı başlığı doğrulanır ama veri kişinindir) — panel, IBAN, ödeme talebi,
  ödenmiş talebin dekontu; ayrıca her oturumlu kişi için kayıt sonrası referans
  (`kayit-referansi`, yalnız yeni açılmış hesapta atıf).
* Yönetici `/api/v1/ortaklik-yonetim`: ortaklar, başvuru kararı, komisyonlar,
  ödeme talepleri ("ödendi" + dekont + ortağa e-posta), CSV (komisyon defteri,
  ödeme talepleri — IBAN maskeli), program ayarları.

Hata gövdesi `{"detail": {"kod": ...}}`; metni ön yüz yedi dilde kuruyor.
"""

import json
import logging
from typing import Any, Dict, Optional

from core.database import get_db
from dependencies.hesap_baglami import musteri_baglami
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile
from fastapi import Depends as _Depends
from fastapi.responses import JSONResponse, Response
from models.ortaklik import AJANS, OrtakKomisyonlari, OrtakOdemeTalepleri, Ortaklar
from services import ortaklik as servis
from services.ortaklik import OrtaklikHatasi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

acik_router = APIRouter(prefix="/api/v1/ortaklik", tags=["ortaklik"])
musteri_router = APIRouter(prefix="/api/v1/ortakligim", tags=["ortaklik"])
yonetici_router = APIRouter(prefix="/api/v1/ortaklik-yonetim", tags=["ortaklik"],
                            dependencies=[_Depends(yonetici_gerekli)])

#: Başvuru: IP özeti başına saatte 5 (kalıcı sayaç).
basvuru_hizi = KaliciHizSiniri("ortaklik-basvuru", 5, 3600.0)
#: Tıklama: IP özeti başına saatte 60 — yalnız bellekte (IP özeti bile diske yazılmasın).
tiklama_hizi = HizSiniri(60, 3600.0)
GOVDE_SINIRI = 8 * 1024
BAL_KUPU = "web_sitesi"


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    basvuru_hizi.temizle()
    tiklama_hizi.temizle()


def _hata(h: Exception) -> HTTPException:
    return HTTPException(status_code=getattr(h, "durum", 400), detail=h.detay() if hasattr(h, "detay") else {"kod": "hata"})


async def _govde(request: Request) -> Dict[str, Any]:
    ham = await request.body()
    if len(ham) > GOVDE_SINIRI:
        raise HTTPException(status_code=413, detail={"kod": "govde_buyuk"})
    try:
        g = json.loads(ham.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail={"kod": "govde_gecersiz"})
    if not isinstance(g, dict):
        raise HTTPException(status_code=400, detail={"kod": "govde_gecersiz"})
    return g


def _yonetici(request: Request) -> str:
    kullanici, _ = _yonetici_mi(request)
    return (getattr(kullanici, "email", "") or "").strip().lower()


# --------------------------------------------------------------------------
# Herkese açık
# --------------------------------------------------------------------------
@acik_router.get("/program")
async def program(dil: str = Query("tr", max_length=5), db: AsyncSession = _Depends(get_db)):
    veri = servis.program_bilgisi(await servis.ayarlar(db), dil)
    return JSONResponse(veri, headers={"Cache-Control": "public, max-age=120"})


@acik_router.post("/basvuru")
async def basvuru(request: Request, db: AsyncSession = _Depends(get_db)):
    if not await izin_ver((basvuru_hizi, ip_ozeti(istemci_ip(request)))):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"})
    g = await _govde(request)
    if str(g.get(BAL_KUPU) or "").strip():
        logger.info("Ortaklık: bal küpü dolu, başvuru yok sayıldı")
        return {"ok": True}
    try:
        o, sonuc = await servis.basvuru_yap(db, g)
    except OrtaklikHatasi as h:
        raise _hata(h)
    if o is not None and sonuc in ("yeni", "guncellendi"):
        try:
            await servis.basvuru_bildir(db, o)
        except Exception:  # noqa: BLE001 - bildirim düşse de başvuru kaydedildi
            logger.exception("Ortaklık başvuru bildirimi gönderilemedi")
    # Var olan ortağın adresi sızmasın: her durumda aynı yanıt.
    return {"ok": True}


@acik_router.post("/tiklama")
async def tiklama(request: Request, db: AsyncSession = _Depends(get_db)):
    if not tiklama_hizi.izin_var_mi(ip_ozeti(istemci_ip(request))):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"})
    g = await _govde(request)
    return {"gecerli": await servis.tiklama_say(db, str(g.get("kod") or "")[:64])}


# --------------------------------------------------------------------------
# Ortak (kişiye ait)
# --------------------------------------------------------------------------
async def _ortagim(request: Request, db: AsyncSession, *, onayli: bool = True) -> Optional[Ortaklar]:
    kisi = musteri_baglami(request).kisi_email
    o = await servis.ortak_bul(db, kisi)
    if onayli and (o is None or o.durum not in ("onaylandi", "askida")):
        raise HTTPException(status_code=404, detail={"kod": "ortak_degil"})
    return o


@musteri_router.get("/durum")
async def ortaklik_durumum(request: Request, db: AsyncSession = _Depends(get_db)):
    """Panel sekmesi için hafif soru: bu kişi ortak mı? (veri yok, yalnız durum)."""
    o = await _ortagim(request, db, onayli=False)
    return {"durum": o.durum if o is not None else None}


@musteri_router.get("")
async def ortakligim(request: Request, db: AsyncSession = _Depends(get_db)):
    o = await _ortagim(request, db, onayli=False)
    if o is None:
        return {"durum": None}
    if o.durum not in ("onaylandi", "askida"):
        return {"durum": o.durum}
    return {"durum": o.durum, **(await servis.panel(db, o))}


@musteri_router.post("/kayit-referansi")
async def kayit_referansi(request: Request, db: AsyncSession = _Depends(get_db)):
    """Bağlantıdan gelip yeni hesap açan kişi: ön yüz girişten sonra bir kez gönderir (kod sessionStorage /
    rızayla localStorage'dan). Atıf oturumdaki KİŞİNİN e-postasına; yanıt yalnız sonuç (ortak bilgisi yok)."""
    kisi = musteri_baglami(request).kisi_email
    g = await _govde(request)
    if not tiklama_hizi.izin_var_mi("kayit:" + kisi):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"})
    sonuc = await servis.kayit_referansi(db, kisi, str(g.get("kod") or "")[:64])
    return {"atif": sonuc in ("yeni", "guncellendi")}


@musteri_router.put("/iban")
async def iban(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = _Depends(get_db)):
    o = await _ortagim(request, db)
    try:
        o = await servis.iban_kaydet(db, o, govde.get("iban"), govde.get("iban_ad"))
    except OrtaklikHatasi as h:
        raise _hata(h)
    return {"iban": servis.iban_maskele(o.iban), "iban_ad": o.iban_ad}


@musteri_router.post("/odeme-talebi")
async def odeme_talebi(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = _Depends(get_db)):
    o = await _ortagim(request, db)
    try:
        t = await servis.odeme_talebi_olustur(db, o, govde.get("para_birimi"))
    except OrtaklikHatasi as h:
        raise _hata(h)
    return servis.talep_sozlugu(t, yonetici=False)


@musteri_router.get("/odeme-talepleri/{talep_id}/dekont")
async def odeme_dekontum(talep_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    from services.dosyalar import imzali_yol

    o = await _ortagim(request, db)
    t = (await db.execute(select(OrtakOdemeTalepleri).where(OrtakOdemeTalepleri.id == talep_id,
                                                             OrtakOdemeTalepleri.ortak_id == o.id))).scalars().first()
    if t is None or not t.dekont_dosya_id or t.durum != "odendi":
        raise HTTPException(status_code=404, detail={"kod": "dekont_yok"})
    yol, son = imzali_yol(t.dekont_dosya_id)
    return {"adres": yol, "son": son}


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("/ozet")
async def ozet(db: AsyncSession = _Depends(get_db)):
    await servis.olgunlasanlari_onayla(db)
    from sqlalchemy import func

    O, T, K = Ortaklar, OrtakOdemeTalepleri, OrtakKomisyonlari
    basvuru = int((await db.execute(select(func.count(O.id)).where(O.hesap == AJANS, O.durum == "beklemede"))).scalar() or 0)
    ortak = int((await db.execute(select(func.count(O.id)).where(O.hesap == AJANS, O.durum == "onaylandi"))).scalar() or 0)
    talep = int((await db.execute(select(func.count(T.id)).where(T.hesap == AJANS, T.durum == "bekliyor"))).scalar() or 0)
    supheli = int((await db.execute(select(func.count(K.id)).where(
        K.hesap == AJANS, K.supheli.isnot(None), K.durum.in_(("beklemede", "onaylandi"))))).scalar() or 0)
    return {"bekleyen_basvuru": basvuru, "ortak": ortak, "bekleyen_talep": talep, "supheli_komisyon": supheli}


@yonetici_router.get("/ortaklar")
async def ortaklar(durum: Optional[str] = Query(None), db: AsyncSession = _Depends(get_db)):
    durumlar = tuple(d for d in (durum or "").split(",") if d in servis.DURUMLAR) or None
    return await servis.ortak_listesi(db, durumlar)


@yonetici_router.get("/ortaklar/{ortak_id}")
async def ortak_ayrinti(ortak_id: int, db: AsyncSession = _Depends(get_db)):
    try:
        o = await servis.ortak_getir(db, ortak_id)
    except OrtaklikHatasi as h:
        raise _hata(h)
    d = servis.ortak_sozlugu(o, yonetici=True, ayar=await servis.ayarlar(db))
    d["bakiyeler"] = await servis.bakiyeler(db, o.id)
    d["tiklama"] = await servis.tiklama_ozeti(db, o.id)
    return d


@yonetici_router.post("/ortaklar/{ortak_id}/karar")
async def karar(ortak_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = _Depends(get_db)):
    try:
        o = await servis.ortak_getir(db, ortak_id)
        o = await servis.karar_ver(db, o, str(govde.get("karar") or ""), _yonetici(request), oran=govde.get("oran"),
                                   kod=govde.get("kod"), neden=govde.get("neden"))
    except OrtaklikHatasi as h:
        raise _hata(h)
    return servis.ortak_sozlugu(o, yonetici=True, ayar=await servis.ayarlar(db))


@yonetici_router.patch("/ortaklar/{ortak_id}")
async def ortak_guncelle(ortak_id: int, govde: Dict[str, Any] = Body(...), db: AsyncSession = _Depends(get_db)):
    try:
        o = await servis.ortak_getir(db, ortak_id)
        o = await servis.ortak_guncelle(db, o, govde)
    except OrtaklikHatasi as h:
        raise _hata(h)
    return servis.ortak_sozlugu(o, yonetici=True, ayar=await servis.ayarlar(db))


async def _komisyon_satirlari(db: AsyncSession, durum: Optional[str], ortak_id: Optional[int], sinir: int):
    await servis.olgunlasanlari_onayla(db)
    s = select(OrtakKomisyonlari).where(OrtakKomisyonlari.hesap == AJANS)
    if durum == "supheli":
        s = s.where(OrtakKomisyonlari.supheli.isnot(None))
    elif durum in servis.KOMISYON_DURUMLARI:
        s = s.where(OrtakKomisyonlari.durum == durum)
    if ortak_id:
        s = s.where(OrtakKomisyonlari.ortak_id == ortak_id)
    return list((await db.execute(s.order_by(OrtakKomisyonlari.id.desc()).limit(sinir))).scalars().all())


def _csv_yaniti(metin: str, ad: str) -> Response:
    return Response(metin.encode("utf-8"), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{ad}"', "Cache-Control": "no-store"})


@yonetici_router.get("/komisyonlar")
async def komisyonlar(durum: Optional[str] = Query(None), ortak_id: Optional[int] = Query(None),
                      db: AsyncSession = _Depends(get_db)):
    satirlar = await _komisyon_satirlari(db, durum, ortak_id, 500)
    adlar = await servis.ortak_adlari(db, {k.ortak_id for k in satirlar})
    return [servis.komisyon_sozlugu(k, yonetici=True, ortak_ad=adlar.get(k.ortak_id)) for k in satirlar]


@yonetici_router.get("/komisyonlar.csv")
async def komisyonlar_csv(durum: Optional[str] = Query(None), ortak_id: Optional[int] = Query(None),
                          db: AsyncSession = _Depends(get_db)):
    """Komisyon defteri (muhasebe için; en çok 10 000 satır, süzgeçler listedekiyle aynı)."""
    satirlar = await _komisyon_satirlari(db, durum, ortak_id, 10_000)
    return _csv_yaniti(await servis.komisyon_csv(db, satirlar), "ortaklik-komisyonlar.csv")


@yonetici_router.post("/komisyonlar/{komisyon_id}/islem")
async def komisyon_islem(komisyon_id: int, request: Request, govde: Dict[str, Any] = Body(...),
                         db: AsyncSession = _Depends(get_db)):
    k = (await db.execute(select(OrtakKomisyonlari).where(OrtakKomisyonlari.id == komisyon_id,
                                                           OrtakKomisyonlari.hesap == AJANS))).scalars().first()
    if k is None:
        raise HTTPException(status_code=404, detail={"kod": "komisyon_yok"})
    try:
        k = await servis.komisyon_islem(db, k, str(govde.get("islem") or ""), _yonetici(request), govde.get("not"))
    except OrtaklikHatasi as h:
        raise _hata(h)
    adlar = await servis.ortak_adlari(db, {k.ortak_id})
    return servis.komisyon_sozlugu(k, yonetici=True, ortak_ad=adlar.get(k.ortak_id))


@yonetici_router.get("/odeme-talepleri")
async def odeme_talepleri(durum: Optional[str] = Query(None), db: AsyncSession = _Depends(get_db)):
    s = select(OrtakOdemeTalepleri).where(OrtakOdemeTalepleri.hesap == AJANS)
    if durum in servis.TALEP_DURUMLARI:
        s = s.where(OrtakOdemeTalepleri.durum == durum)
    satirlar = (await db.execute(s.order_by(OrtakOdemeTalepleri.id.desc()).limit(500))).scalars().all()
    ortaklar_ = {}
    if satirlar:
        ortaklar_ = {o.id: o for o in (await db.execute(select(Ortaklar).where(
            Ortaklar.id.in_({t.ortak_id for t in satirlar})))).scalars().all()}
    return [servis.talep_sozlugu(t, yonetici=True, ortak=ortaklar_.get(t.ortak_id)) for t in satirlar]


@yonetici_router.get("/odeme-talepleri.csv")
async def odeme_talepleri_csv(durum: Optional[str] = Query(None), db: AsyncSession = _Depends(get_db)):
    s = select(OrtakOdemeTalepleri).where(OrtakOdemeTalepleri.hesap == AJANS)
    if durum in servis.TALEP_DURUMLARI:
        s = s.where(OrtakOdemeTalepleri.durum == durum)
    satirlar = list((await db.execute(s.order_by(OrtakOdemeTalepleri.id.desc()).limit(10_000))).scalars().all())
    return _csv_yaniti(await servis.talep_csv(db, satirlar), "ortaklik-odeme-talepleri.csv")


@yonetici_router.post("/odeme-talepleri/{talep_id}/odendi")
async def odendi(talep_id: int, request: Request, notu: Optional[str] = Form(None),
                 dekont: Optional[UploadFile] = File(None), db: AsyncSession = _Depends(get_db)):
    try:
        t = await servis.talep_getir(db, talep_id)
        t = await servis.odendi_isaretle(db, t, _yonetici(request), dekont=dekont, notu=notu)
    except OrtaklikHatasi as h:
        raise _hata(h)
    o = await servis.ortak_getir(db, t.ortak_id)
    return servis.talep_sozlugu(t, yonetici=True, ortak=o)


@yonetici_router.post("/odeme-talepleri/{talep_id}/reddet")
async def reddet(talep_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = _Depends(get_db)):
    try:
        t = await servis.talep_getir(db, talep_id)
        t = await servis.talep_reddet(db, t, _yonetici(request), govde.get("neden"))
    except OrtaklikHatasi as h:
        raise _hata(h)
    o = await servis.ortak_getir(db, t.ortak_id)
    return servis.talep_sozlugu(t, yonetici=True, ortak=o)


@yonetici_router.get("/odeme-talepleri/{talep_id}/dekont")
async def talep_dekontu(talep_id: int, db: AsyncSession = _Depends(get_db)):
    from services.dosyalar import imzali_yol

    try:
        t = await servis.talep_getir(db, talep_id)
    except OrtaklikHatasi as h:
        raise _hata(h)
    if not t.dekont_dosya_id:
        raise HTTPException(status_code=404, detail={"kod": "dekont_yok"})
    yol, son = imzali_yol(t.dekont_dosya_id)
    return {"adres": yol, "son": son}


@yonetici_router.get("/ayarlar")
async def ayarlar(db: AsyncSession = _Depends(get_db)):
    return await servis.ayarlar(db)


@yonetici_router.put("/ayarlar")
async def ayarlari_yaz(govde: Dict[str, Any] = Body(...), db: AsyncSession = _Depends(get_db)):
    return await servis.ayarlari_yaz(db, govde)


router = (acik_router, musteri_router, yonetici_router)
