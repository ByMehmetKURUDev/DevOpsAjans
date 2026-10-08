"""Faz 6T — toplantılar (ajans ↔ müşteri / CRM adayı). Ayrıntı ve kurallar: `services/toplantilar.py`.

Dört kapı
---------
* Yönetici `/api/v1/toplantilar` (router düzeyi `yonetici_gerekli`: oturumsuz 401, müşteri 403): liste (yaklaşan /
  geçmiş / iptal; müşteri, proje, durum, tarih süzgeci), meta (ekip, müşteriler, projeler, adaylar), çakışma
  denetimi, oluştur / düzenle / sil (çöp kutusu), davet, ertele, iptal, yapıldı, tutanak, paylaş, aksiyonlar
  (+ göreve dönüştür), ICS / PDF / Markdown, müşteri talepleri, ekip takvim abonelikleri.
* Müşteri `/api/v1/toplantilarim` (etkin hesap; `projeler` izni — toplantılar portalın parçası, ayrı modül değil):
  liste, ayrıntı (paylaşılmamış not YOK), katılım yanıtı, ICS, paylaşılmış tutanak PDF/MD, kendisine atanmış
  aksiyonu tamamlama, "Toplantı iste", kişiye özel takvim aboneliği.
* Girişsiz `/api/v1/toplanti-yanit`: imzalı yanıt bağlantısı (GET özet, POST yanıt — jeton GÖVDEDE).
* Girişsiz `/api/v1/toplanti-takvimi/<jeton>.ics`: kişinin gizli ICS akışı (`Cache-Control: private`, noindex).

Hata gövdesi `{"detail": {"kod": ...}}`; metni ön yüz yedi dilde kuruyor.
"""

import json
import logging
from datetime import date
from typing import Any, Dict, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi import Depends as _Depends
from fastapi.responses import JSONResponse, Response
from models.toplantilar import ToplantiAksiyonlari, Toplantilar, ToplantiTalepleri
from services import toplanti_pdf as tpdf
from services import toplantilar as servis
from services.toplantilar import ToplantiHatasi
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/toplantilar", tags=["toplantilar"],
                            dependencies=[_Depends(yonetici_gerekli)])
musteri_router = APIRouter(prefix="/api/v1/toplantilarim", tags=["toplantilar"])
yanit_router = APIRouter(prefix="/api/v1/toplanti-yanit", tags=["toplantilar"])
akis_router = APIRouter(prefix="/api/v1/toplanti-takvimi", tags=["toplantilar"])

IZIN = "projeler"
GOVDE_SINIRI = 64 * 1024
#: Girişsiz yanıt: IP özeti başına 10 dk'da 60 okuma / 20 yazma (kalıcı sayaç).
yanit_okuma_hizi = KaliciHizSiniri("toplanti-yanit-oku", 60, 600.0)
yanit_yazma_hizi = KaliciHizSiniri("toplanti-yanit-yaz", 20, 600.0)
#: Akış: jeton özeti başına saatte 120 (takvim sunucuları ortak IP'den çeker — IP değil jeton). Yalnız bellekte.
akis_hizi = HizSiniri(120, 3600.0)
#: Müşteri talebi: kişi başına saatte 10; yanıt/aksiyon yazmaları dakikada 30.
talep_hizi = HizSiniri(10, 3600.0)
yazma_hizi = HizSiniri(30, 60.0)

GIZLI_BASLIKLAR = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"}


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for s in (yanit_okuma_hizi, yanit_yazma_hizi, akis_hizi, talep_hizi, yazma_hizi):
        s.temizle()


def _hata(h: ToplantiHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


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


def _ben(request: Request) -> Optional[str]:
    kullanici, _ = _yonetici_mi(request)
    return servis.eposta_duzelt(getattr(kullanici, "email", "")) or None


def _tarih(deger: Optional[str]) -> Optional[date]:
    if not deger:
        return None
    try:
        return date.fromisoformat(deger[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail={"kod": "tarih_gecersiz"})


def _dosya(veri: Any, ad: str, tur: str, *, gizli: bool = False) -> Response:
    basliklar = {"Content-Disposition": f'attachment; filename="{ad}"', "Cache-Control": "private, no-store"}
    if gizli:
        basliklar.update({"X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"})
    return Response(content=veri, media_type=tur, headers=basliklar)


async def _ekip(db: AsyncSession) -> Dict[str, str]:
    return {x["email"]: x["ad"] for x in await servis.ekip_listesi(db)}


async def _proje_adi(db: AsyncSession, t: Toplantilar) -> Optional[str]:
    if not t.proje_id:
        return None
    from models.projects import Projects

    return (await db.execute(select(Projects.title).where(Projects.id == t.proje_id))).scalar()


# --------------------------------------------------------------------------
# Yönetici — meta, liste, çakışma
# --------------------------------------------------------------------------
@yonetici_router.get("/meta")
async def meta(db: AsyncSession = _Depends(get_db)):
    from models.crm import CrmAdaylari
    from models.projects import Projects
    from services.moduller import musteri_listesi

    projeler = (await db.execute(select(Projects.id, Projects.title, Projects.client_email)
                                 .where(Projects.client_email.isnot(None)).order_by(Projects.id.desc()).limit(500))).all()
    adaylar = (await db.execute(select(CrmAdaylari.id, CrmAdaylari.ad, CrmAdaylari.email, CrmAdaylari.firma)
                                .order_by(CrmAdaylari.id.desc()).limit(300))).all()
    return {
        "ekip": await servis.ekip_listesi(db),
        "musteriler": [m for m in await musteri_listesi(db) if m.get("eposta")],
        "projeler": [{"id": p[0], "baslik": p[1], "hesap_email": servis.eposta_duzelt(p[2])} for p in projeler],
        "adaylar": [{"id": a[0], "ad": a[1], "email": a[2], "firma": a[3]} for a in adaylar],
        "saat_dilimi": servis.SAAT_DILIMI,
        "sinirlar": {"sure_en_az": servis.EN_AZ_SURE, "sure_en_cok": servis.EN_COK_SURE,
                     "katilimci": servis.KATILIMCI_EN_COK, "gundem": servis.GUNDEM_EN_COK},
    }


@yonetici_router.get("")
async def liste(
    gorunum: str = Query("yaklasan", max_length=12),
    hesap: Optional[str] = Query(None, max_length=254),
    proje_id: Optional[int] = Query(None),
    durum: Optional[str] = Query(None, max_length=12),
    bas: Optional[str] = Query(None, max_length=10),
    bit: Optional[str] = Query(None, max_length=10),
    q: Optional[str] = Query(None, max_length=100),
    db: AsyncSession = _Depends(get_db),
):
    # Panel açılışında hatırlatmalar da denetlenir (ücretsiz sunucu uyur; zamanlı iş de çalışıyor).
    try:
        await servis.hatirlatmalari_gonder(db)
    except Exception:  # noqa: BLE001
        logger.exception("Toplantı hatırlatmaları denetlenemedi")
        await db.rollback()
    try:
        items = await servis.yonetici_listesi(db, gorunum=gorunum, hesap=hesap, proje_id=proje_id, durum=durum,
                                              bas=_tarih(bas), bit=_tarih(bit), q=q)
    except ToplantiHatasi as h:
        raise _hata(h)
    bekleyen_talep = (await db.execute(select(func.count(ToplantiTalepleri.id))
                                       .where(ToplantiTalepleri.durum == "bekliyor"))).scalar() or 0
    return {"items": items, "bekleyen_talep": int(bekleyen_talep)}


@yonetici_router.post("/cakisma")
async def cakisma(request: Request, db: AsyncSession = _Depends(get_db)):
    g = await _govde(request)
    try:
        bas = servis.zaman_coz(g.get("baslangic"), g.get("saat_dilimi"))
        sure = servis._sure(g.get("sure_dk"))  # noqa: SLF001
    except ToplantiHatasi as h:
        raise _hata(h)
    ekip = [e for e in (g.get("ekip") or []) if isinstance(e, str)][: servis.KATILIMCI_EN_COK]
    haric = g.get("haric_id")
    return {"cakismalar": await servis.cakismalar(db, bas, sure, ekip, int(haric) if str(haric or "").isdigit() else None)}


@yonetici_router.get("/jitsi")
async def jitsi():
    return {"baglanti": servis.jitsi_adresi()}


# --------------------------------------------------------------------------
# Yönetici — müşteri talepleri
# --------------------------------------------------------------------------
@yonetici_router.get("/talepler")
async def talepler(durum: Optional[str] = Query(None, max_length=12), db: AsyncSession = _Depends(get_db)):
    s = select(ToplantiTalepleri).order_by(ToplantiTalepleri.created_at.desc()).limit(300)
    if durum:
        s = s.where(ToplantiTalepleri.durum == durum)
    return {"items": [servis.talep_sozlugu(t) for t in (await db.execute(s)).scalars().all()]}


@yonetici_router.get("/talepler/{tid}")
async def talep(tid: int, db: AsyncSession = _Depends(get_db)):
    try:
        t = await servis.talep_bul(db, tid)
    except ToplantiHatasi as h:
        raise _hata(h)
    d = servis.talep_sozlugu(t)
    d["hesap_adi"] = await servis.hesap_adi(db, t.hesap_email)
    return d


@yonetici_router.post("/talepler/{tid}/kapat")
async def talep_kapat(tid: int, db: AsyncSession = _Depends(get_db)):
    try:
        t = await servis.talep_bul(db, tid)
    except ToplantiHatasi as h:
        raise _hata(h)
    await servis.talep_kapat(db, t)
    await db.commit()
    return servis.talep_sozlugu(t)


# --------------------------------------------------------------------------
# Yönetici — takvim abonelikleri (ekip üyeleri ve yöneticinin kendisi)
# --------------------------------------------------------------------------
@yonetici_router.get("/abonelikler")
async def abonelikler(request: Request, db: AsyncSession = _Depends(get_db)):
    from models.toplantilar import ToplantiTakvimAbonelikleri as A

    ben = _ben(request)
    kisiler = [{"ad": x["ad"], "email": x["email"], "tur": "ekip"} for x in await servis.ekip_listesi(db)]
    if ben and not any(k["email"] == ben for k in kisiler):
        kisiler.insert(0, {"ad": None, "email": ben, "tur": "yonetici"})
    var = {a.kisi_email: a for a in (await db.execute(select(A).where(A.kisi_email.in_([k["email"] for k in kisiler])))).scalars().all()}
    return {"items": [{**k, "ben": k["email"] == ben, **servis.abonelik_sozlugu(var.get(k["email"]))} for k in kisiler]}


@yonetici_router.post("/abonelikler")
async def abonelik_uret(request: Request, db: AsyncSession = _Depends(get_db)):
    g = await _govde(request)
    e = servis.eposta_duzelt(g.get("eposta"))
    ben = _ben(request)
    ekip = await _ekip(db)
    if e not in ekip and e != ben:
        raise HTTPException(status_code=400, detail={"kod": "ekip_gecersiz"})
    try:
        adres = await servis.abonelik_uret(db, e, "ekip" if e in ekip else "yonetici", ben)
    except ToplantiHatasi as h:
        raise _hata(h)
    return JSONResponse({"adres": adres, **servis.abonelik_sozlugu(await servis.abonelik_bul(db, e))},
                        headers={"Cache-Control": "no-store"})


@yonetici_router.post("/abonelikler/iptal")
async def abonelik_iptal(request: Request, db: AsyncSession = _Depends(get_db)):
    g = await _govde(request)
    return {"iptal": await servis.abonelik_iptal(db, servis.eposta_duzelt(g.get("eposta")))}


# --------------------------------------------------------------------------
# Yönetici — aksiyonlar (statik yollar /{tid}'den önce)
# --------------------------------------------------------------------------
@yonetici_router.put("/aksiyonlar/{aid}")
async def aksiyon_guncelle(aid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    g = await _govde(request)
    try:
        a, t = await servis.aksiyon_bul(db, aid)
        await servis.aksiyon_uygula(db, t, a, g, yeni=False)
        if a.durum == "tamamlandi" and not a.tamamlayan_eposta:
            a.tamamlayan_eposta = _ben(request)
        await db.commit()
    except ToplantiHatasi as h:
        await db.rollback()
        raise _hata(h)
    return servis.aksiyon_sozlugu(a)


@yonetici_router.delete("/aksiyonlar/{aid}")
async def aksiyon_sil(aid: int, db: AsyncSession = _Depends(get_db)):
    try:
        a, _t = await servis.aksiyon_bul(db, aid)
    except ToplantiHatasi as h:
        raise _hata(h)
    await db.delete(a)
    await db.commit()
    return {"ok": True}


@yonetici_router.post("/aksiyonlar/{aid}/gorev")
async def aksiyon_gorev(aid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    try:
        a, t = await servis.aksiyon_bul(db, aid)
        gorev_id = await servis.goreve_donustur(db, a, t, _ben(request))
    except ToplantiHatasi as h:
        raise _hata(h)
    return {"gorev_id": gorev_id, "proje_id": t.proje_id}


# --------------------------------------------------------------------------
# Yönetici — toplantı
# --------------------------------------------------------------------------
async def _yanit(db: AsyncSession, t: Toplantilar, **ek: Any) -> Dict[str, Any]:
    d = await servis.yonetici_sozlugu(db, t)
    d.update(ek)
    return d


async def _cakismalar(db: AsyncSession, t: Toplantilar) -> list:
    ks = await servis.katilimcilar(db, t.id)
    return await servis.cakismalar(db, t.baslangic, int(t.sure_dk), [k.eposta for k in ks if k.tur == "ekip"], t.id)


@yonetici_router.post("")
async def olustur(request: Request, db: AsyncSession = _Depends(get_db)):
    import secrets

    g = await _govde(request)
    ben = _ben(request)
    talep_kaydi = None
    try:
        if g.get("talep_id") not in (None, "", 0):
            talep_kaydi = await servis.talep_bul(db, int(g["talep_id"]))
        t = Toplantilar(uid=secrets.token_hex(12), durum="planlandi", sira_no=0, olusturan_eposta=ben,
                        notlar_paylasildi=False, guncelleme_bekliyor=False)
        await servis.alanlari_uygula(db, t, g, yeni=True)
        if talep_kaydi is not None:
            t.talep_id = talep_kaydi.id
        db.add(t)
        await db.flush()
        await servis.katilimcilari_yaz(db, t, g.get("katilimcilar") or [])
        if talep_kaydi is not None:
            await servis.talep_kapat(db, talep_kaydi, toplanti_id=t.id)
        await db.commit()
    except ToplantiHatasi as h:
        await db.rollback()
        raise _hata(h)
    except (TypeError, ValueError):
        await db.rollback()
        raise HTTPException(status_code=400, detail={"kod": "govde_gecersiz"})
    await db.refresh(t)
    davet = None
    if g.get("davet_gonder"):
        try:
            davet = await servis.davet_gonder(db, t)
        except ToplantiHatasi as h:
            davet = {"hata": h.kod}
    else:
        await servis.harici_takvim_esitle(db, t, "olusturuldu")
    return await _yanit(db, t, cakismalar=await _cakismalar(db, t), davet=davet)


@yonetici_router.get("/{tid}")
async def ayrinti(tid: int, db: AsyncSession = _Depends(get_db)):
    try:
        t = await servis.toplanti_bul(db, tid)
    except ToplantiHatasi as h:
        raise _hata(h)
    return await _yanit(db, t, cakismalar=await _cakismalar(db, t) if t.durum != "iptal" else [])


@yonetici_router.put("/{tid}")
async def guncelle(tid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    g = await _govde(request)
    try:
        t = await servis.toplanti_bul(db, tid)
        if t.durum == "iptal":
            raise ToplantiHatasi(409, "iptal_edildi")
        degisim = await servis.alanlari_uygula(db, t, g, yeni=False)
        if "katilimcilar" in g:
            await servis.katilimcilari_yaz(db, t, g.get("katilimcilar"))
        servis.zaman_degisti_isle(t, await servis.katilimcilar(db, t.id), degisim)
        await db.commit()
    except ToplantiHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.refresh(t)
    await servis.harici_takvim_esitle(db, t, "guncellendi")
    return await _yanit(db, t, cakismalar=await _cakismalar(db, t))


@yonetici_router.delete("/{tid}")
async def sil(tid: int, db: AsyncSession = _Depends(get_db)):
    try:
        t = await servis.toplanti_bul(db, tid)
    except ToplantiHatasi as h:
        raise _hata(h)
    await servis.harici_takvim_esitle(db, t, "silindi")
    await servis.sil(db, t)
    return {"ok": True}


@yonetici_router.post("/{tid}/davet")
async def davet(tid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    g = await _govde(request)
    try:
        t = await servis.toplanti_bul(db, tid)
        yalniz = g.get("yalniz") if isinstance(g.get("yalniz"), list) else None
        sonuc = await servis.davet_gonder(db, t, yalniz=yalniz)
    except ToplantiHatasi as h:
        raise _hata(h)
    return await _yanit(db, t, davet=sonuc)


@yonetici_router.post("/{tid}/ertele")
async def ertele(tid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    g = await _govde(request)
    try:
        t = await servis.toplanti_bul(db, tid)
        await servis.ertele(db, t, g)
        await db.commit()
    except ToplantiHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.refresh(t)
    davet_sonucu = None
    if t.davet_gonderildi_at is not None and g.get("davet_gonder", True):
        try:
            davet_sonucu = await servis.davet_gonder(db, t)
        except ToplantiHatasi as h:
            davet_sonucu = {"hata": h.kod}
    else:
        await servis.harici_takvim_esitle(db, t, "ertelendi")
    return await _yanit(db, t, cakismalar=await _cakismalar(db, t), davet=davet_sonucu)


@yonetici_router.post("/{tid}/iptal")
async def iptal(tid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    g = await _govde(request)
    try:
        t = await servis.toplanti_bul(db, tid)
        await servis.iptal_et(db, t, g.get("neden"))
        await db.commit()
    except ToplantiHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.refresh(t)
    sonuc = await servis.iptal_gonder(db, t)
    await servis.harici_takvim_esitle(db, t, "iptal")
    return await _yanit(db, t, iptal_bildirimi=sonuc)


@yonetici_router.post("/{tid}/yapildi")
async def yapildi(tid: int, db: AsyncSession = _Depends(get_db)):
    try:
        t = await servis.toplanti_bul(db, tid)
        await servis.yapildi_isaretle(db, t)
        await db.commit()
    except ToplantiHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.refresh(t)
    return await _yanit(db, t)


@yonetici_router.put("/{tid}/tutanak")
async def tutanak(tid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    g = await _govde(request)
    try:
        t = await servis.toplanti_bul(db, tid)
        if "notlar" in g:
            t.notlar = servis._uzun_metin(g.get("notlar"), servis.NOT_SINIRI, "notlar_uzun")  # noqa: SLF001
        if "kararlar" in g:
            t.kararlar = json.dumps(servis.kararlar_duzelt(g.get("kararlar")), ensure_ascii=False)
        await db.commit()
    except ToplantiHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.refresh(t)
    return await _yanit(db, t)


@yonetici_router.post("/{tid}/paylas")
async def paylas(tid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    g = await _govde(request)
    try:
        t = await servis.toplanti_bul(db, tid)
        ilk = await servis.notlari_paylas(db, t, bool(g.get("paylas")))
    except ToplantiHatasi as h:
        raise _hata(h)
    if ilk:
        await servis.paylasim_bildir(db, t)
    await db.refresh(t)
    return await _yanit(db, t)


@yonetici_router.post("/{tid}/aksiyonlar")
async def aksiyon_ekle(tid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    g = await _govde(request)
    try:
        t = await servis.toplanti_bul(db, tid)
        adet = (await db.execute(select(func.count(ToplantiAksiyonlari.id))
                                 .where(ToplantiAksiyonlari.toplanti_id == t.id))).scalar() or 0
        if int(adet) >= servis.AKSIYON_EN_COK:
            raise ToplantiHatasi(409, "aksiyon_cok")
        a = ToplantiAksiyonlari(toplanti_id=t.id, durum="acik", sira=int(adet))
        await servis.aksiyon_uygula(db, t, a, g, yeni=True)
        db.add(a)
        await db.commit()
    except ToplantiHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.refresh(a)
    return servis.aksiyon_sozlugu(a)


@yonetici_router.get("/{tid}/ics")
async def ics(tid: int, db: AsyncSession = _Depends(get_db)):
    try:
        t = await servis.toplanti_bul(db, tid)
    except ToplantiHatasi as h:
        raise _hata(h)
    veri = servis.ics_uret(t, await servis.katilimcilar(db, t.id), "PUBLISH")
    return _dosya(veri, servis.ics_dosya_adi(t), "text/calendar; charset=utf-8")


@yonetici_router.get("/{tid}/pdf")
async def pdf(tid: int, dil: str = Query("tr", max_length=5), db: AsyncSession = _Depends(get_db)):
    try:
        t = await servis.toplanti_bul(db, tid)
    except ToplantiHatasi as h:
        raise _hata(h)
    veri = tpdf.tutanak_pdf(t, await servis.katilimcilar(db, t.id), await servis.aksiyonlar(db, t.id), dil=dil,
                            ekip=await _ekip(db), hesap_adi=await servis.hesap_adi(db, t.hesap_email),
                            proje_adi=await _proje_adi(db, t))
    return _dosya(veri, tpdf.dosya_adi(t, "pdf"), "application/pdf")


@yonetici_router.get("/{tid}/md")
async def markdown(tid: int, dil: str = Query("tr", max_length=5), db: AsyncSession = _Depends(get_db)):
    try:
        t = await servis.toplanti_bul(db, tid)
    except ToplantiHatasi as h:
        raise _hata(h)
    veri = tpdf.tutanak_md(t, await servis.katilimcilar(db, t.id), await servis.aksiyonlar(db, t.id), dil=dil,
                           ekip=await _ekip(db), hesap_adi=await servis.hesap_adi(db, t.hesap_email),
                           proje_adi=await _proje_adi(db, t))
    return _dosya(veri.encode("utf-8"), tpdf.dosya_adi(t, "md"), "text/markdown; charset=utf-8")


# --------------------------------------------------------------------------
# Müşteri (etkin hesap; `projeler` izni)
# --------------------------------------------------------------------------
def _musteri(request: Request):
    return izin_iste(request, IZIN)


@musteri_router.get("/ozet")
async def m_ozet(request: Request, db: AsyncSession = _Depends(get_db)):
    b = _musteri(request)
    return await servis.musteri_ozeti(db, b.hesap_email)


@musteri_router.get("")
async def m_liste(request: Request, db: AsyncSession = _Depends(get_db)):
    b = _musteri(request)
    return {"items": await servis.musteri_toplantilari(db, b.hesap_email, b.kisi_email), "saat_dilimi": servis.SAAT_DILIMI}


@musteri_router.get("/talepler")
async def m_talepler(request: Request, db: AsyncSession = _Depends(get_db)):
    b = _musteri(request)
    satirlar = (await db.execute(select(ToplantiTalepleri).where(ToplantiTalepleri.hesap_email == b.hesap_email)
                                 .order_by(ToplantiTalepleri.created_at.desc()).limit(50))).scalars().all()
    return {"items": [servis.talep_sozlugu(t) for t in satirlar]}


@musteri_router.post("/talepler")
async def m_talep(request: Request, db: AsyncSession = _Depends(get_db)):
    b = _musteri(request)
    if not talep_hizi.izin_var_mi(b.kisi_email):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"})
    g = await _govde(request)
    try:
        t = await servis.talep_olustur(db, b.hesap_email, b.kisi_email, g)
    except ToplantiHatasi as h:
        raise _hata(h)
    await servis.talep_bildir(db, t)
    return servis.talep_sozlugu(t)


@musteri_router.get("/takvim")
async def m_takvim(request: Request, db: AsyncSession = _Depends(get_db)):
    b = _musteri(request)
    return servis.abonelik_sozlugu(await servis.abonelik_bul(db, b.kisi_email))


@musteri_router.post("/takvim")
async def m_takvim_uret(request: Request, db: AsyncSession = _Depends(get_db)):
    b = _musteri(request)
    if not yazma_hizi.izin_var_mi(b.kisi_email):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"})
    try:
        adres = await servis.abonelik_uret(db, b.kisi_email, "musteri", b.kisi_email)
    except ToplantiHatasi as h:
        raise _hata(h)
    return JSONResponse({"adres": adres, **servis.abonelik_sozlugu(await servis.abonelik_bul(db, b.kisi_email))},
                        headers={"Cache-Control": "no-store"})


@musteri_router.delete("/takvim")
async def m_takvim_iptal(request: Request, db: AsyncSession = _Depends(get_db)):
    b = _musteri(request)
    return {"iptal": await servis.abonelik_iptal(db, b.kisi_email)}


@musteri_router.post("/aksiyonlar/{aid}/tamamla")
async def m_aksiyon(aid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    b = _musteri(request)
    if not yazma_hizi.izin_var_mi(b.kisi_email):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"})
    g = await _govde(request)
    a = (await db.execute(select(ToplantiAksiyonlari).where(ToplantiAksiyonlari.id == aid))).scalars().first()
    t = None
    if a is not None:
        t = (await db.execute(select(Toplantilar).where(Toplantilar.id == a.toplanti_id,
                                                        Toplantilar.hesap_email == b.hesap_email))).scalars().first()
    if a is None or t is None or a.sorumlu_tur != "musteri":
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    # "Kendisine atanmış": kişiye atanmışsa o kişi (ya da hesap sahibi); hesaba atanmışsa izinli her üye.
    if a.sorumlu_eposta and a.sorumlu_eposta != b.kisi_email and not b.kendi_hesabi:
        raise HTTPException(status_code=403, detail={"kod": "atanmamis"})
    tamam = bool(g.get("tamam", True))
    a.durum = "tamamlandi" if tamam else "acik"
    a.tamamlandi_at = servis.simdi() if tamam else None
    a.tamamlayan_eposta = b.kisi_email if tamam else None
    await db.commit()
    return {"id": a.id, "durum": a.durum, "tamamlandi_at": servis.iso(a.tamamlandi_at)}


async def _musteri_toplanti(request: Request, db: AsyncSession, tid: int):
    b = _musteri(request)
    try:
        t = await servis.musteri_toplantisi(db, b.hesap_email, tid)
    except ToplantiHatasi as h:
        raise _hata(h)
    return b, t


@musteri_router.get("/{tid}")
async def m_ayrinti(tid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    b, t = await _musteri_toplanti(request, db, tid)
    return servis.musteri_sozlugu(t, await servis.katilimcilar(db, t.id), await servis.aksiyonlar(db, t.id),
                                  b.kisi_email, ayrinti=True)


@musteri_router.post("/{tid}/yanit")
async def m_yanit(tid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    b, t = await _musteri_toplanti(request, db, tid)
    if not yazma_hizi.izin_var_mi(b.kisi_email):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"})
    g = await _govde(request)
    k = next((x for x in await servis.katilimcilar(db, t.id) if x.eposta == b.kisi_email), None)
    if k is None:
        raise HTTPException(status_code=403, detail={"kod": "katilimci_degil"})
    try:
        await servis.yanit_yaz(db, t, k, g.get("yanit"), g.get("not"), "panel")
    except ToplantiHatasi as h:
        raise _hata(h)
    return {"yanit": k.yanit, "yanit_notu": k.yanit_notu, "yanit_at": servis.iso(k.yanit_at)}


@musteri_router.get("/{tid}/ics")
async def m_ics(tid: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _b, t = await _musteri_toplanti(request, db, tid)
    veri = servis.ics_uret(t, [], "PUBLISH")
    return _dosya(veri, servis.ics_dosya_adi(t), "text/calendar; charset=utf-8")


async def _musteri_tutanak(request: Request, db: AsyncSession, tid: int):
    b, t = await _musteri_toplanti(request, db, tid)
    if not t.notlar_paylasildi:
        # Paylaşılmamış tutanak "yok" sayılır (varlığı da sızmasın).
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    ks = await servis.katilimcilar(db, t.id)
    if not any(k.eposta == b.kisi_email for k in ks):
        ks = [k for k in ks if k.tur == "ekip"]  # dış katılımcılar yalnız katılımcılara
    return t, ks


@musteri_router.get("/{tid}/pdf")
async def m_pdf(tid: int, request: Request, dil: str = Query("tr", max_length=5), db: AsyncSession = _Depends(get_db)):
    t, ks = await _musteri_tutanak(request, db, tid)
    veri = tpdf.tutanak_pdf(t, ks, await servis.aksiyonlar(db, t.id), dil=dil, ekip=await _ekip(db),
                            hesap_adi=await servis.hesap_adi(db, t.hesap_email), proje_adi=await _proje_adi(db, t),
                            musteri=True)
    return _dosya(veri, tpdf.dosya_adi(t, "pdf"), "application/pdf")


@musteri_router.get("/{tid}/md")
async def m_md(tid: int, request: Request, dil: str = Query("tr", max_length=5), db: AsyncSession = _Depends(get_db)):
    t, ks = await _musteri_tutanak(request, db, tid)
    veri = tpdf.tutanak_md(t, ks, await servis.aksiyonlar(db, t.id), dil=dil, ekip=await _ekip(db),
                           hesap_adi=await servis.hesap_adi(db, t.hesap_email), proje_adi=await _proje_adi(db, t),
                           musteri=True)
    return _dosya(veri.encode("utf-8"), tpdf.dosya_adi(t, "md"), "text/markdown; charset=utf-8")


# --------------------------------------------------------------------------
# Girişsiz katılım yanıtı (imzalı bağlantı)
# --------------------------------------------------------------------------
@yanit_router.get("/{jeton}")
async def acik_yanit_oku(jeton: str, request: Request, db: AsyncSession = _Depends(get_db)):
    if not await izin_ver((yanit_okuma_hizi, ip_ozeti(istemci_ip(request)))):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"}, headers=GIZLI_BASLIKLAR)
    try:
        t, k = await servis.yanit_coz(db, jeton)
    except ToplantiHatasi as h:
        raise HTTPException(status_code=h.durum, detail=h.detay(), headers=GIZLI_BASLIKLAR)
    return JSONResponse(servis.acik_sozluk(t, k), headers=GIZLI_BASLIKLAR)


@yanit_router.post("")
async def acik_yanit_yaz(request: Request, db: AsyncSession = _Depends(get_db)):
    if not await izin_ver((yanit_yazma_hizi, ip_ozeti(istemci_ip(request)))):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"}, headers=GIZLI_BASLIKLAR)
    g = await _govde(request)
    try:
        t, k = await servis.yanit_coz(db, str(g.get("jeton") or ""))
        await servis.yanit_yaz(db, t, k, g.get("yanit"), g.get("not"), "baglanti")
    except ToplantiHatasi as h:
        raise HTTPException(status_code=h.durum, detail=h.detay(), headers=GIZLI_BASLIKLAR)
    return JSONResponse(servis.acik_sozluk(t, k), headers=GIZLI_BASLIKLAR)


@yanit_router.get("/{jeton}/ics")
async def acik_ics(jeton: str, request: Request, db: AsyncSession = _Depends(get_db)):
    if not await izin_ver((yanit_okuma_hizi, ip_ozeti(istemci_ip(request)))):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"}, headers=GIZLI_BASLIKLAR)
    try:
        t, _k = await servis.yanit_coz(db, jeton)
    except ToplantiHatasi as h:
        raise HTTPException(status_code=h.durum, detail=h.detay(), headers=GIZLI_BASLIKLAR)
    return _dosya(servis.ics_uret(t, [], "PUBLISH"), servis.ics_dosya_adi(t), "text/calendar; charset=utf-8", gizli=True)


# --------------------------------------------------------------------------
# Gizli takvim akışı
# --------------------------------------------------------------------------
@akis_router.get("/{jeton}.ics")
async def akis(jeton: str, db: AsyncSession = _Depends(get_db)):
    basliklar = {"Cache-Control": "private, max-age=300", "X-Robots-Tag": "noindex, nofollow",
                 "Referrer-Policy": "no-referrer"}
    if not akis_hizi.izin_var_mi(servis.jeton_ozeti(jeton)):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"}, headers=basliklar)
    veri = await servis.akis_uret(db, jeton)
    if veri is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"}, headers=basliklar)
    return Response(content=veri, media_type="text/calendar; charset=utf-8",
                    headers={**basliklar, "Content-Disposition": 'inline; filename="toplantilar.ics"'})


router = (yonetici_router, musteri_router, yanit_router, akis_router)
