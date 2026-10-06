"""Faz 5I — İçerik stüdyosu: marka sesi, AI içerik şablonları ve sosyal medya planlayıcı.

Yönetici (`/api/v1/icerik-studyosu/yonetim`) — ajansın kendi içeriği + müşteri İÇİN hazırladığı
içerik (`?hesap=<e-posta>` / gövdede `hesap`; gönderi listesinde `hesap=*` = hepsi).
Müşteri (`/api/v1/icerik-studyom`; modül `icerik_studyosu` açık + ekip izni `icerik`) — etkin
hesabın kendi içeriği; ajansın onaya sunduğu gönderiler salt okunur görünür.

Ortak uçlar:
  GET    /meta                       kanallar, sınır tablosu, görsel önerileri, hazır şablonlar, kullanım
  GET    /kullanim                   bu ayın üretimi, dahil hak, kredi
  GET|POST /markalar · GET|PUT|DELETE /markalar/{id} · POST /markalar/{id}/ses-cikar (AI önerisi; kaydetmez)
  GET|POST /sablonlar · PUT|DELETE /sablonlar/{id}   (kendi şablonu: alanlar + {{alan}} istemi)
  POST   /uret                       marka + şablon + girdi → 1–3 varyasyon (ölçüm + uyarı rozeti)
  POST   /ince-ayar                  kısalt | samimi | emoji_ekle | emoji_cikar (yerel) | cevir | uyarla
  GET    /uretimler · GET /uretimler/{id}            üretim geçmişi
  GET    /gonderiler?bas&bit&tz&kanal&kampanya&durum&marka_id   takvim/liste (saat dilimi)
  POST   /gonderiler · GET|PUT|DELETE /gonderiler/{id}
  POST   /gonderiler/{id}/durum      {durum, not} — geçersiz geçiş 409
  POST   /gonderiler/{id}/kisa-link  kanal başına UTM'li kısa link (Faz 4Q)
  GET    /gonderiler/{id}/paket      "Paylaşıma hazır": kanal metni, bağlantı, ilk yorum, görseller
  GET    /gonderiler/{id}/gorseller.zip
  GET    /disa-aktar.csv             Postiz/Buffer için CSV (tarih, kanal, metin, görsel URL …)
  GET|POST /gorseller                görsel kitaplığı (yükleme: çok parçalı `dosya`)
Yalnız yönetici:
  POST   /gonderiler/{id}/onaya-gonder {gun?, eposta_gonder?} → imzalı bağlantı (BİR KEZ döner)
  GET|PUT /ayarlar                   model, günlük bütçe, blok başına üretim/kredi, ajans günlük sınırı
  GET    /hesaplar                   müşteri listesi (+ modül açık mı)

Müşteri onayı (`/api/v1/icerik-onaylarim`; yalnız ekip izni `icerik`, MODÜLDEN BAĞIMSIZ):
  GET    ""                          ajansın onaya sunduğu bekleyen içerikler
  POST   "/{gonderi_id}"             {sonuc: onay|revizyon, not} (revizyonda not zorunlu)
Herkese açık:
  GET|POST /api/v1/icerik-onay/{jeton}   girişsiz onay sayfası (jeton yetki; tek kullanımlık, süreli)
  GET      /api/v1/icerik-gorsel/{anahtar} gönderi görseli (tahmin edilemez anahtar)

Hata gövdeleri `{"detail": {"kod": ...}}`; metni ön yüz yedi dilde kuruyor.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from models.content_posts import Content_posts
from models.icerik_studyosu import IcerikGorselleri, IcerikMarkalari, IcerikSablonlari, IcerikUretimleri
from services import icerik_planlayici as pl
from services import icerik_studyosu as st
from services.icerik_studyosu import Kapsam, StudyoHatasi
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(
    prefix="/api/v1/icerik-studyosu/yonetim", tags=["icerik_studyosu"], dependencies=[Depends(yonetici_gerekli)],
)
musteri_router = APIRouter(
    prefix="/api/v1/icerik-studyom",
    tags=["icerik_studyosu"],
    dependencies=[Depends(modul_gerekli(st.MODUL)), Depends(izin_gerekli(st.IZIN))],
)
onay_router = APIRouter(prefix="/api/v1/icerik-onaylarim", tags=["icerik_studyosu"],
                        dependencies=[Depends(izin_gerekli(st.IZIN))])
acik_router = APIRouter(prefix="/api/v1", tags=["icerik_studyosu"])

#: Kişi başı: dakikada 20 üretim, 60 yazma; saatte 120 görsel. IP başı: dakikada 20 onay sayfası isteği.
_uretim_hizi = HizSiniri(20, 60.0)
_yazma_hizi = HizSiniri(60, 60.0)
_gorsel_hizi = HizSiniri(120, 3600.0)
_acik_hiz = HizSiniri(20, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_uretim_hizi, _yazma_hizi, _gorsel_hizi, _acik_hiz):
        h.temizle()


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _sh(h: StudyoHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _hiz(sinir: HizSiniri, anahtar: str) -> None:
    if not sinir.izin_var_mi(anahtar or "anonim"):
        raise _hata(429, "cok_hizli")


def _hesap_param(ham: Any) -> Optional[str]:
    e = st.eposta_duzelt(ham)
    if not e:
        return None
    if e == "*":
        return "*"
    if not pl._EPOSTA.match(e):
        raise _hata(400, "eposta_gecersiz", alan="hesap")
    return e


def _yonetici_kapsami(request: Request, hesap: Any = None) -> Kapsam:
    kullanici, _ = _yonetici_mi(request)
    h = _hesap_param(hesap)
    return Kapsam(True, None if h == "*" else h, st.eposta_duzelt(getattr(kullanici, "email", "")))


def _musteri_kapsami(request: Request, hesap: Any = None) -> Kapsam:
    baglam = izin_iste(request, st.IZIN)
    return Kapsam(False, baglam.hesap_email, baglam.kisi_email)


@dataclass
class _Yon:
    yonetici: bool
    kapsam_al: Callable[..., Kapsam]


def _uclar(router: APIRouter, yon: _Yon) -> None:
    kapsam_al = yon.kapsam_al

    # ---------------------------------------------------------------- meta
    @router.get("/meta")
    async def meta(request: Request, hesap: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        from services import yapay_zeka as ai

        k = kapsam_al(request, hesap)
        d = st.meta_sozlugu()
        d.update({
            "yonetici": k.yonetici,
            "hesap": k.hesap,
            "kisi": k.kisi,
            "sahte_mod": ai.sahte_ai_acik_mi(),
            "durumlar": list(pl.DURUMLAR),
            "gecisler": {a: list(b) for a, b in pl.GECISLER.items()},
            "varsayilan_saat_dilimi": pl.VARSAYILAN_SAAT_DILIMI,
            "csv_sutunlari": list(pl.CSV_SUTUNLARI),
            "kullanim": await st.kullanim_ozeti(db, k.kullanim_hesabi),
        })
        return d

    @router.get("/kullanim")
    async def kullanim(request: Request, hesap: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request, hesap)
        # Yönetici bir müşterinin kullanımına da bakabilir (üretim maliyeti ajansta sayılıyor).
        return await st.kullanim_ozeti(db, k.hesap if k.yonetici else k.kullanim_hesabi)

    # ------------------------------------------------------------- markalar
    def _hesap_kosulu(model: Any, hesap: Optional[str]):
        if hesap:
            return model.hesap_email == hesap
        return (model.hesap_email.is_(None)) | (model.hesap_email == "")

    async def _marka(db: AsyncSession, mid: int, k: Kapsam) -> IcerikMarkalari:
        m = (await db.execute(select(IcerikMarkalari).where(IcerikMarkalari.id == mid))).scalars().first()
        if m is None or (not k.yonetici and st.eposta_duzelt(m.hesap_email) != k.hesap):
            raise _hata(404, "marka_yok")
        return m

    @router.get("/markalar")
    async def markalar(request: Request, hesap: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request, hesap)
        satirlar = (await db.execute(select(IcerikMarkalari).where(_hesap_kosulu(IcerikMarkalari, k.hesap))
                                     .order_by(IcerikMarkalari.ad))).scalars().all()
        sinir = (await st.hesap_sinirlari(db, k.hesap)).get("marka_siniri") if not k.yonetici else None
        return {"items": [st.marka_sozlugu(m) for m in satirlar], "sinir": sinir}

    @router.post("/markalar")
    async def marka_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request, govde.get("hesap"))
        _hiz(_yazma_hizi, k.kisi)
        try:
            d = st.marka_dogrula(govde)
        except StudyoHatasi as h:
            raise _sh(h)
        if not k.yonetici:
            sinir = (await st.hesap_sinirlari(db, k.hesap)).get("marka_siniri")
            sayi = int((await db.execute(select(func.count(IcerikMarkalari.id)).where(IcerikMarkalari.hesap_email == k.hesap))).scalar() or 0)
            if sinir is not None and sayi >= int(sinir):
                raise _hata(409, "marka_siniri", sinir=int(sinir))
        m = IcerikMarkalari(hesap_email=k.hesap, olusturan=k.kisi or None, created_at=st.simdi(), **d)
        db.add(m)
        await db.commit()
        await db.refresh(m)
        return st.marka_sozlugu(m)

    @router.get("/markalar/{mid}")
    async def marka_ayrinti(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
        return st.marka_sozlugu(await _marka(db, mid, kapsam_al(request)))

    @router.put("/markalar/{mid}")
    async def marka_guncelle(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _hiz(_yazma_hizi, k.kisi)
        m = await _marka(db, mid, k)
        try:
            d = st.marka_dogrula(govde, m)
        except StudyoHatasi as h:
            raise _sh(h)
        for alan, deger in d.items():
            setattr(m, alan, deger)
        m.updated_at = st.simdi()
        await db.commit()
        await db.refresh(m)
        return st.marka_sozlugu(m)

    @router.delete("/markalar/{mid}")
    async def marka_sil(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        m = await _marka(db, mid, k)
        await db.delete(m)
        await db.commit()
        return {"ok": True}

    @router.post("/markalar/{mid}/ses-cikar")
    async def ses_cikar(mid: int, request: Request, govde: Optional[Dict[str, Any]] = Body(None), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _hiz(_uretim_hizi, k.kisi)
        m = await _marka(db, mid, k)
        # Yöneticide işin hesabı markanın hesabı (marka/şablon doğrulaması o hesaba göre).
        is_kapsami = Kapsam(k.yonetici, st.eposta_duzelt(m.hesap_email) or None, k.kisi)
        try:
            return await st.ses_cikar(db, is_kapsami, m, st.dil_coz((govde or {}).get("dil")))
        except StudyoHatasi as h:
            raise _sh(h)

    # ------------------------------------------------------------- şablonlar
    async def _sablon(db: AsyncSession, sid: int, k: Kapsam) -> IcerikSablonlari:
        s = (await db.execute(select(IcerikSablonlari).where(IcerikSablonlari.id == sid))).scalars().first()
        if s is None or (not k.yonetici and st.eposta_duzelt(s.hesap_email) != k.hesap):
            raise _hata(404, "sablon_yok")
        return s

    @router.get("/sablonlar")
    async def sablonlar(request: Request, hesap: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request, hesap)
        ozel = (await db.execute(select(IcerikSablonlari).where(_hesap_kosulu(IcerikSablonlari, k.hesap))
                                 .order_by(IcerikSablonlari.ad))).scalars().all()
        return {"hazir": st.hazir_sablon_listesi(), "ozel": [st.sablon_sozlugu(s) for s in ozel]}

    @router.post("/sablonlar")
    async def sablon_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request, govde.get("hesap"))
        _hiz(_yazma_hizi, k.kisi)
        try:
            d = st.sablon_dogrula(govde)
        except StudyoHatasi as h:
            raise _sh(h)
        sayi = int((await db.execute(select(func.count(IcerikSablonlari.id)).where(_hesap_kosulu(IcerikSablonlari, k.hesap)))).scalar() or 0)
        if sayi >= 50:
            raise _hata(409, "sablon_siniri", sinir=50)
        s = IcerikSablonlari(hesap_email=k.hesap, olusturan=k.kisi or None, created_at=st.simdi(), **d)
        db.add(s)
        await db.commit()
        await db.refresh(s)
        return st.sablon_sozlugu(s)

    @router.put("/sablonlar/{sid}")
    async def sablon_guncelle(sid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _hiz(_yazma_hizi, k.kisi)
        s = await _sablon(db, sid, k)
        try:
            d = st.sablon_dogrula(govde, s)
        except StudyoHatasi as h:
            raise _sh(h)
        for alan, deger in d.items():
            setattr(s, alan, deger)
        s.updated_at = st.simdi()
        await db.commit()
        await db.refresh(s)
        return st.sablon_sozlugu(s)

    @router.delete("/sablonlar/{sid}")
    async def sablon_sil(sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        s = await _sablon(db, sid, kapsam_al(request))
        await db.delete(s)
        await db.commit()
        return {"ok": True}

    # ------------------------------------------------------------- üretim
    @router.post("/uret")
    async def uret(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request, govde.get("hesap"))
        _hiz(_uretim_hizi, k.kisi)
        try:
            return await st.uret(db, k, govde)
        except StudyoHatasi as h:
            raise _sh(h)

    @router.post("/ince-ayar")
    async def ince_ayar(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request, govde.get("hesap"))
        _hiz(_uretim_hizi, k.kisi)
        try:
            return await st.ince_ayar(db, k, govde)
        except StudyoHatasi as h:
            raise _sh(h)

    @router.get("/uretimler")
    async def uretimler(request: Request, hesap: Optional[str] = Query(None), sinir: int = Query(30, ge=1, le=100),
                        db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request, hesap)
        satirlar = (await db.execute(select(IcerikUretimleri).where(_hesap_kosulu(IcerikUretimleri, k.hesap))
                                     .order_by(desc(IcerikUretimleri.id)).limit(sinir))).scalars().all()
        return {"items": [st.uretim_sozlugu(u) for u in satirlar]}

    @router.get("/uretimler/{uid}")
    async def uretim(uid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        u = (await db.execute(select(IcerikUretimleri).where(IcerikUretimleri.id == uid))).scalars().first()
        if u is None or (not k.yonetici and st.eposta_duzelt(u.hesap_email) != k.hesap):
            raise _hata(404, "bulunamadi")
        return st.uretim_sozlugu(u)

    # ------------------------------------------------------------- gönderiler
    @router.get("/gonderiler")
    async def gonderiler(
        request: Request,
        hesap: Optional[str] = Query(None),
        bas: Optional[str] = Query(None),
        bit: Optional[str] = Query(None),
        tz: Optional[str] = Query(None),
        kanal: Optional[str] = Query(None),
        kampanya: Optional[str] = Query(None),
        durum: Optional[str] = Query(None),
        marka_id: Optional[int] = Query(None),
        tarihsiz: bool = Query(True),
        db: AsyncSession = Depends(get_db),
    ):
        k = kapsam_al(request, hesap)
        filtre = _hesap_param(hesap) if k.yonetici else None
        try:
            return await pl.liste(db, k, hesap_filtresi=filtre, bas=bas, bit=bit, tz=tz, kanal=kanal, kampanya=kampanya,
                                  durum=durum, marka_id=marka_id, tarihsiz=tarihsiz)
        except StudyoHatasi as h:
            raise _sh(h)

    async def _sozluk(db: AsyncSession, g: Content_posts, k: Kapsam) -> Dict[str, Any]:
        onaylar = await pl.onay_bilgileri(db, [g]) if k.yonetici else {}
        markalar = await pl.marka_adlari(db, [g.marka_id])
        return pl.gonderi_sozlugu(g, onay=onaylar.get(g.onay_islem_id) if g.onay_islem_id else None,
                                  marka_adi=markalar.get(g.marka_id))

    @router.post("/gonderiler")
    async def gonderi_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request, govde.get("hesap"))
        _hiz(_yazma_hizi, k.kisi)
        try:
            if not k.yonetici:
                await pl.gonderi_siniri_denetle(db, k.hesap)
            d = await pl.gonderi_dogrula(db, govde, None, k.hesap)
            uretim_id = govde.get("uretim_id")
            if uretim_id is not None and (isinstance(uretim_id, bool) or not isinstance(uretim_id, int)):
                raise StudyoHatasi("gecersiz", alan="uretim_id")
        except StudyoHatasi as h:
            raise _sh(h)
        g = Content_posts(hesap_email=k.hesap, yoneten="ajans" if k.yonetici else "musteri", status="taslak",
                          olusturan_eposta=k.kisi or None, uretim_id=uretim_id, **d)
        db.add(g)
        await db.commit()
        await db.refresh(g)
        return await _sozluk(db, g, k)

    @router.get("/gonderiler/{gid}")
    async def gonderi_ayrinti(gid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        try:
            g = await pl.gonderi_bul(db, gid, k)
        except StudyoHatasi as h:
            raise _sh(h)
        return await _sozluk(db, g, k)

    @router.put("/gonderiler/{gid}")
    async def gonderi_guncelle(gid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _hiz(_yazma_hizi, k.kisi)
        try:
            g = await pl.gonderi_bul(db, gid, k, yazma=True)
            pl.duzenleme_denetle(g, govde)
            d = await pl.gonderi_dogrula(db, govde, g, st.eposta_duzelt(g.hesap_email) or None)
        except StudyoHatasi as h:
            raise _sh(h)
        pl.uygula(g, d)
        await db.commit()
        await db.refresh(g)
        return await _sozluk(db, g, k)

    @router.delete("/gonderiler/{gid}")
    async def gonderi_sil(gid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        try:
            g = await pl.gonderi_bul(db, gid, k, yazma=True)
        except StudyoHatasi as h:
            raise _sh(h)
        await pl.onay_bagini_iptal_et(db, g)
        await db.delete(g)
        await db.commit()
        return {"ok": True}

    @router.post("/gonderiler/{gid}/durum")
    async def gonderi_durum(gid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _hiz(_yazma_hizi, k.kisi)
        try:
            g = await pl.gonderi_bul(db, gid, k, yazma=True)
            g = await pl.durum_degistir(db, g, govde.get("durum"), govde.get("not"), k)
        except StudyoHatasi as h:
            raise _sh(h)
        return await _sozluk(db, g, k)

    @router.post("/gonderiler/{gid}/kisa-link")
    async def kisa_link(gid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _hiz(_yazma_hizi, k.kisi)
        try:
            g = await pl.gonderi_bul(db, gid, k, yazma=True)
            linkler = await pl.kisa_link_uret(db, g, k.kisi)
        except StudyoHatasi as h:
            raise _sh(h)
        return {"kisa_linkler": linkler, "gonderi": await _sozluk(db, g, k)}

    @router.get("/gonderiler/{gid}/paket")
    async def paket(gid: int, request: Request, db: AsyncSession = Depends(get_db)):
        try:
            g = await pl.gonderi_bul(db, gid, kapsam_al(request))
        except StudyoHatasi as h:
            raise _sh(h)
        return pl.paylasim_paketi(g)

    @router.get("/gonderiler/{gid}/gorseller.zip")
    async def gorseller_zip(gid: int, request: Request, db: AsyncSession = Depends(get_db)):
        from services.dosya_deposu import icerik_konumu

        try:
            g = await pl.gonderi_bul(db, gid, kapsam_al(request))
            veri = await pl.gorseller_zip(db, g)
        except StudyoHatasi as h:
            raise _sh(h)
        return Response(veri, media_type="application/zip", headers={
            "Content-Disposition": icerik_konumu(f"icerik-{g.id}-gorseller.zip"), "Cache-Control": "no-store",
        })

    @router.get("/disa-aktar.csv")
    async def disa_aktar(
        request: Request,
        hesap: Optional[str] = Query(None),
        bas: Optional[str] = Query(None),
        bit: Optional[str] = Query(None),
        tz: Optional[str] = Query(None),
        kanal: Optional[str] = Query(None),
        kampanya: Optional[str] = Query(None),
        durum: Optional[str] = Query(None),
        db: AsyncSession = Depends(get_db),
    ):
        from services.dosya_deposu import icerik_konumu

        k = kapsam_al(request, hesap)
        filtre = _hesap_param(hesap) if k.yonetici else None
        try:
            kayitlar, _, _ = await pl.kayitlari_getir(db, k, hesap_filtresi=filtre, bas=bas, bit=bit, tz=tz, kanal=kanal,
                                                      kampanya=kampanya, durum=durum, tarihsiz=False)
        except StudyoHatasi as h:
            raise _sh(h)
        return Response(pl.csv_uret(kayitlar), media_type="text/csv; charset=utf-8", headers={
            "Content-Disposition": icerik_konumu("icerik-plani.csv"), "Cache-Control": "no-store",
        })

    # ------------------------------------------------------------- görseller
    @router.get("/gorseller")
    async def gorseller(request: Request, hesap: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request, hesap)
        satirlar = (await db.execute(select(IcerikGorselleri).where(_hesap_kosulu(IcerikGorselleri, k.hesap))
                                     .order_by(desc(IcerikGorselleri.id)).limit(200))).scalars().all()
        return {"items": [pl.gorsel_sozlugu(g) for g in satirlar]}

    @router.post("/gorseller")
    async def gorsel_yukle(request: Request, dosya: UploadFile = File(...), hesap: Optional[str] = Query(None),
                           db: AsyncSession = Depends(get_db)):
        from services import dosya_deposu

        k = kapsam_al(request, hesap)
        _hiz(_gorsel_hizi, k.kisi)
        sayi = int((await db.execute(select(func.count(IcerikGorselleri.id)).where(_hesap_kosulu(IcerikGorselleri, k.hesap)))).scalar() or 0)
        if sayi >= pl.HESAP_GORSEL_SINIRI:
            raise _hata(409, "gorsel_siniri", sinir=pl.HESAP_GORSEL_SINIRI)
        try:
            hazir = pl.gorsel_hazirla(await dosya.read(pl.GORSEL_EN_COK_BAYT + 1))
        except StudyoHatasi as h:
            raise _sh(h)
        anahtar = pl.gorsel_anahtari()
        try:
            depo = await dosya_deposu.yaz(db, f"icerik/{anahtar}.{pl._uzanti(hazir['tur'])}", hazir["veri"], hazir["tur"])
        except Exception:  # noqa: BLE001
            logger.exception("İçerik görseli yazılamadı")
            raise _hata(503, "depo_hatasi")
        ad = st.metin((dosya.filename or "")[:120], "ad", 120, tek_satir=True) if dosya.filename else ""
        g = IcerikGorselleri(hesap_email=k.hesap, anahtar=anahtar, depo=depo, tur=hazir["tur"], ad=ad or None,
                             genislik=hazir["genislik"], yukseklik=hazir["yukseklik"], boyut=len(hazir["veri"]),
                             yukleyen=k.kisi or None, created_at=st.simdi())
        db.add(g)
        await db.commit()
        return pl.gorsel_sozlugu(g)


# ---------------------------------------------------------------------------
# Yönetici + müşteri uçları
# ---------------------------------------------------------------------------
_uclar(yonetici_router, _Yon(True, _yonetici_kapsami))
_uclar(musteri_router, _Yon(False, _musteri_kapsami))


@yonetici_router.post("/gonderiler/{gid}/onaya-gonder")
async def onaya_gonder(gid: int, request: Request, govde: Optional[Dict[str, Any]] = Body(None), db: AsyncSession = Depends(get_db)):
    k = _yonetici_kapsami(request)
    _hiz(_yazma_hizi, k.kisi)
    govde = govde or {}
    try:
        g = await pl.gonderi_bul(db, gid, k)
        sonuc = await pl.onaya_gonder(db, g, k.kisi, govde.get("gun"), bool(govde.get("eposta_gonder")))
    except StudyoHatasi as h:
        raise _sh(h)
    onaylar = await pl.onay_bilgileri(db, [g])
    sonuc["gonderi"] = pl.gonderi_sozlugu(g, onay=onaylar.get(g.onay_islem_id))
    return sonuc


@yonetici_router.get("/ayarlar")
async def ayarlar(db: AsyncSession = Depends(get_db)):
    return await st.genel_ayarlar(db)


@yonetici_router.put("/ayarlar")
async def ayarlar_yaz(govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    try:
        return await st.genel_ayarlari_yaz(db, govde)
    except StudyoHatasi as h:
        raise _sh(h)


@yonetici_router.get("/hesaplar")
async def hesaplar(db: AsyncSession = Depends(get_db)):
    """Bağlam seçicisi: müşteriler ve İçerik stüdyosu modülü onlarda açık mı (onay için gerekmez)."""
    from services.moduller import musteri_listesi, toplu_durumlar

    liste = await musteri_listesi(db)
    durumlar = await toplu_durumlar(db, [m["eposta"] for m in liste if m.get("eposta")])
    sonuc = []
    for m in liste:
        e = m.get("eposta")
        if not e:
            continue
        mm = durumlar.get(e)
        d = mm.durumlar.get(st.MODUL) if mm is not None else None
        acik = bool(d is not None and d.acik)
        sonuc.append({"eposta": e, "ad": m.get("ad"), "modul_acik": acik})
    return {"items": sonuc}


# ---------------------------------------------------------------------------
# Müşteri: onay bekleyen içerikler (modülden bağımsız)
# ---------------------------------------------------------------------------
@onay_router.get("")
async def onaylarim(request: Request, db: AsyncSession = Depends(get_db)):
    baglam = izin_iste(request, st.IZIN)
    return {"items": await pl.bekleyen_onaylar(db, baglam.hesap_email)}


@onay_router.post("/{gid}")
async def onaylarim_karar(gid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    from services import imzali_islem

    baglam = izin_iste(request, st.IZIN)
    _hiz(_yazma_hizi, baglam.kisi_email)
    g = (await db.execute(select(Content_posts).where(Content_posts.id == gid, Content_posts.hesap_email == baglam.hesap_email))).scalars().first()
    if g is None or not g.onay_islem_id or (g.status or "") != "musteri_onayi":
        raise _hata(404, "bulunamadi")
    try:
        sonuc = await imzali_islem.kullan_id(db, g.onay_islem_id, baglam.hesap_email, str(govde.get("sonuc") or ""),
                                             govde.get("not"), ip_ozeti=ip_ozeti(istemci_ip(request)),
                                             ek={"kisi": baglam.kisi_email})
    except imzali_islem.IslemHatasi as h:
        raise _hata(h.durum, h.kod)
    await imzali_islem.bildirimleri_gonder(db, sonuc.bildirimler)
    await db.refresh(g)
    return {"durum": imzali_islem.gecerli_durum(sonuc.kayit), "sonuc": sonuc.kayit.sonuc, "gonderi_durumu": g.status}


# ---------------------------------------------------------------------------
# Herkese açık: imzalı onay bağlantısı ve görsel
# ---------------------------------------------------------------------------
async def _onay_kaydi(db: AsyncSession, jeton: str):
    from services import imzali_islem

    kayit = await imzali_islem.coz(db, jeton)
    if kayit is None or kayit.tur != "icerik_onay":
        raise _hata(404, "bulunamadi")
    return kayit


@acik_router.get("/icerik-onay/{jeton}")
async def onay_ozeti(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    from services import imzali_islem

    _hiz(_acik_hiz, ip_ozeti(istemci_ip(request)))
    kayit = await _onay_kaydi(db, jeton)
    tanim = imzali_islem.TURLER["icerik_onay"]
    g = (await db.execute(select(Content_posts).where(Content_posts.id == kayit.hedef_id))).scalars().first()
    marka = (await pl.marka_adlari(db, [g.marka_id])).get(g.marka_id) if g is not None else None
    return {
        "durum": imzali_islem.gecerli_durum(kayit),
        "sonuc": kayit.sonuc,
        "sonuclar": list(tanim.sonuclar),
        "not_zorunlu": list(tanim.not_zorunlu),
        "son_kullanma": st.iso(kayit.son_kullanma),
        "kullanildi_at": st.iso(kayit.kullanildi_at),
        "alici": imzali_islem.eposta_maskele(kayit.alici_eposta),
        "gonderi": pl.onizleme_sozlugu(g, marka) if g is not None else None,
    }


@acik_router.post("/icerik-onay/{jeton}")
async def onay_karari(jeton: str, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    from services import imzali_islem

    ip = ip_ozeti(istemci_ip(request))
    _hiz(_acik_hiz, ip)
    await _onay_kaydi(db, jeton)
    try:
        sonuc = await imzali_islem.kullan(db, jeton, str(govde.get("sonuc") or ""), govde.get("not"), ip_ozeti=ip)
    except imzali_islem.IslemHatasi as h:
        raise _hata(h.durum, h.kod)
    await imzali_islem.bildirimleri_gonder(db, sonuc.bildirimler)
    return {"durum": imzali_islem.gecerli_durum(sonuc.kayit), "sonuc": sonuc.kayit.sonuc,
            "kullanildi_at": st.iso(sonuc.kayit.kullanildi_at)}


@acik_router.get("/icerik-gorsel/{anahtar}")
async def gorsel(anahtar: str, db: AsyncSession = Depends(get_db)):
    from services import dosya_deposu

    if not anahtar or len(anahtar) > 64:
        raise _hata(404, "bulunamadi")
    g = (await db.execute(select(IcerikGorselleri).where(IcerikGorselleri.anahtar == anahtar))).scalars().first()
    if g is None:
        raise _hata(404, "bulunamadi")
    try:
        veri = await dosya_deposu.oku(db, g.depo, f"icerik/{g.anahtar}.{pl._uzanti(g.tur)}")
    except Exception:  # noqa: BLE001
        raise _hata(404, "bulunamadi")
    return Response(veri, media_type=g.tur, headers={
        "Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'", "X-Robots-Tag": "noindex",
    })


# Yönetici, müşteri ve onay router'ları önce; herkese açık en sonda.
router = (yonetici_router, musteri_router, onay_router, acik_router)
