"""Faz 5B — belgeler, wiki ve strateji araçları (kurallar `services/belgeler.py`).

Yönetici  /api/v1/belgeler          ajansın belgeleri (wiki, müşteri/proje belgesi, strateji),
                                     müşteriyle paylaşma, sürümler, yapılacaklar, AI, PDF/MD.
                                     Müşterinin AJANSLA PAYLAŞTIĞI belgeler salt okunur.
Müşteri   /api/v1/belgelerim        ajansın paylaştığı belgeler (modülden bağımsız; izin
                                     `belgeler` ya da `dosyalar`) salt okunur + "okudum/onaylıyorum";
                                     kendi belgeleri (modül `belgeler` + izin `belgeler`).

Müşteri e-postası her zaman JETONDAN (etkin hesap); başkasının belgesi ve paylaşılmamış
ajans belgesi "yok" sayılıyor (404) — var olduğu da sızmasın.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, musteri_baglami
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from fastapi.responses import Response
from models.belgeler import BelgeSurumleri, Belgeler
from pydantic import BaseModel
from services import belgeler as bs
from services import belgeler_ai as bai
from services.belgeler import BelgeHatasi
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/belgeler", tags=["belgeler"])
musteri_router = APIRouter(
    prefix="/api/v1/belgelerim",
    tags=["belgeler"],
    # Okuma (paylaşılan belgeler) iki izinden biriyle; yazma uçlarında ayrıca `belgeler` + modül.
    dependencies=[_Depends(izin_gerekli("belgeler", "dosyalar"))],
)
_KENDI = [_Depends(izin_gerekli("belgeler")), _Depends(modul_gerekli("belgeler"))]


def _hata(h: BelgeHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "yonetici_gerekli"})
    return bs.eposta_duzelt(kullanici.email)


# ---------------------------------------------------------------------------
# Şemalar
# ---------------------------------------------------------------------------
class BelgeGirdisi(BaseModel):
    tur: Optional[str] = None
    baslik: Optional[str] = None
    icerik: Optional[Union[str, Dict[str, Any]]] = None
    etiketler: Optional[Any] = None
    alan: Optional[str] = None
    musteri_email: Optional[str] = None
    proje_id: Optional[int] = None
    gorunurluk: Optional[str] = None
    sabit: Optional[bool] = None
    #: Düzenlemede: editörün açtığı sürüm (başkası arada kaydettiyse 409).
    surum: Optional[int] = None


class OnizlemeGirdisi(BaseModel):
    icerik: str = ""


class YapilacakGirdisi(BaseModel):
    satir: int
    metin: Optional[str] = None
    tamam: bool = True


class GorevBagiGirdisi(BaseModel):
    satir: int
    metin: Optional[str] = None
    gorev_id: int


class AiGirdisi(BaseModel):
    islem: str
    metin: Optional[str] = None
    talimat: Optional[str] = None
    tur: Optional[str] = None
    isletme: Optional[str] = None
    dil: Optional[str] = None


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------
def _gecerli_eposta(ham: Optional[str]) -> str:
    e = bs.eposta_duzelt(ham)
    if not e or "@" not in e or len(e) > 200 or " " in e:
        raise BelgeHatasi("gecersiz_eposta", alan="musteri_email")
    return e


async def _proje(db: AsyncSession, proje_id: Any):
    from models.projects import Projects

    if proje_id is None:
        return None
    if isinstance(proje_id, bool) or not isinstance(proje_id, int):
        raise BelgeHatasi("gecersiz", alan="proje_id")
    p = (await db.execute(select(Projects).where(Projects.id == proje_id))).scalars().first()
    if p is None:
        raise BelgeHatasi("proje_yok", 404, alan="proje_id")
    return p


def _icerik_hazirla(tur: str, ham: Any) -> str:
    if bs.strateji_mi(tur):
        import json

        return json.dumps(bs.strateji_dogrula(tur, ham), ensure_ascii=False)
    if isinstance(ham, dict):
        raise BelgeHatasi("gecersiz", alan="icerik")
    return bs._metin(ham, "icerik", bs.SINIR["icerik"])  # noqa: SLF001


async def _ajans_alanlari(db: AsyncSession, b: Belgeler, g: BelgeGirdisi, yeni: bool) -> None:
    """Ajans belgesinde alan / müşteri / proje / görünürlük tutarlılığı."""
    alan = g.alan if g.alan is not None else (b.alan or "ajans")
    if alan not in bs.ALANLAR:
        raise BelgeHatasi("gecersiz", alan="alan")
    gorunurluk = g.gorunurluk if g.gorunurluk is not None else (b.gorunurluk or "ekip")
    if gorunurluk not in bs.GORUNURLUKLER:
        raise BelgeHatasi("gecersiz", alan="gorunurluk")
    if alan == "ajans":
        b.musteri_email, b.proje_id = None, None
        if gorunurluk == "paylasilan":
            raise BelgeHatasi("paylasim_icin_musteri", alan="gorunurluk")
    elif alan == "musteri":
        ham = g.musteri_email if g.musteri_email is not None else b.musteri_email
        if not ham:
            raise BelgeHatasi("metin_gerekli", alan="musteri_email")
        b.musteri_email = _gecerli_eposta(ham)
        b.proje_id = g.proje_id if "proje_id" in g.model_fields_set else (None if yeni else b.proje_id)
        if b.proje_id is not None:
            p = await _proje(db, b.proje_id)
            if bs.eposta_duzelt(p.client_email) != b.musteri_email:
                raise BelgeHatasi("proje_musteri_uyusmuyor", alan="proje_id")
    else:  # proje
        proje_id = g.proje_id if "proje_id" in g.model_fields_set else b.proje_id
        if proje_id is None:
            raise BelgeHatasi("metin_gerekli", alan="proje_id")
        p = await _proje(db, proje_id)
        b.proje_id = p.id
        b.musteri_email = bs.eposta_duzelt(p.client_email) or None
        if gorunurluk == "paylasilan" and not b.musteri_email:
            raise BelgeHatasi("paylasim_icin_musteri", alan="gorunurluk")
    b.alan = alan
    b.gorunurluk = gorunurluk


def _paylasim_gecisi(b: Belgeler, onceki: Optional[str]) -> bool:
    """Görünürlük "paylasilan"a yeni geçtiyse zaman damgası; geri çekildiyse temizle. Yeni paylaşım mı?"""
    if b.gorunurluk == "paylasilan" and onceki != "paylasilan":
        b.paylasildi_at = bs.simdi()
        return True
    if b.gorunurluk != "paylasilan":
        b.paylasildi_at = None
    return False


async def _belge(db: AsyncSession, belge_id: int) -> Belgeler:
    b = (await db.execute(select(Belgeler).where(Belgeler.id == belge_id))).scalars().first()
    if b is None:
        raise BelgeHatasi("bulunamadi", 404)
    return b


async def _ayrinti(db: AsyncSession, b: Belgeler) -> Dict[str, Any]:
    adlar = await bs.proje_adlari(db, [b.proje_id])
    return bs.belge_sozlugu(b, ayrintili=True, proje_adi=adlar.get(b.proje_id) if b.proje_id else None)


async def _liste_yaniti(db: AsyncSession, satirlar: List[Belgeler], etiket: Optional[str]) -> Dict[str, Any]:
    tum = list(satirlar)
    secili = bs.etiket_suz(tum, etiket)
    adlar = await bs.proje_adlari(db, [b.proje_id for b in secili])
    return {
        "items": [bs.belge_sozlugu(b, proje_adi=adlar.get(b.proje_id) if b.proje_id else None) for b in secili],
        "etiketler": bs.etiket_ozeti(tum),
    }


def _pdf_yaniti(veri: bytes, ad: str) -> Response:
    from services.dosya_deposu import icerik_konumu

    return Response(content=veri, media_type="application/pdf", headers={
        "Content-Disposition": icerik_konumu(ad), "Cache-Control": "no-store",
        "X-Robots-Tag": "noindex, nofollow", "X-Content-Type-Options": "nosniff",
    })


def _md_yaniti(metin: str, ad: str) -> Response:
    from services.dosya_deposu import icerik_konumu

    return Response(content=metin.encode("utf-8"), media_type="text/markdown; charset=utf-8", headers={
        "Content-Disposition": icerik_konumu(ad), "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


async def _pdf(db: AsyncSession, b: Belgeler, dil: str) -> Response:
    from services.belge_pdf import belge_pdf

    proje = (await bs.proje_adlari(db, [b.proje_id])).get(b.proje_id) if b.proje_id else None
    veri = {
        "baslik": b.baslik, "tur": b.tur, "surum": b.surum, "guncellendi": b.updated_at or b.created_at,
        "etiketler": bs.json_yukle(b.etiketler, []), "musteri": b.musteri_email or None, "proje": proje,
    }
    if bs.strateji_mi(b.tur):
        veri["strateji"] = bs.strateji_coz(b)
    else:
        veri["icerik"] = b.icerik or ""
    return _pdf_yaniti(belge_pdf(veri, dil), bs.dosya_adi(b, "pdf"))


def _meta(ai_hazir: bool) -> Dict[str, Any]:
    return {
        "turler": list(bs.TURLER),
        "strateji_sablonlari": [s.sozluk() for s in bs.STRATEJI_SABLONLARI.values()],
        "alanlar": list(bs.ALANLAR),
        "gorunurlukler": list(bs.GORUNURLUKLER),
        "sinirlar": dict(bs.SINIR),
        "surum_siniri": bs.SURUM_SINIRI,
        "ai_hazir": ai_hazir,
        "ai_islemleri": list(bai.ISLEMLER),
    }


async def _surum_listesi(db: AsyncSession, b: Belgeler) -> List[Dict[str, Any]]:
    satirlar = (await db.execute(
        select(BelgeSurumleri).where(BelgeSurumleri.belge_id == b.id)
        .order_by(BelgeSurumleri.surum.desc(), BelgeSurumleri.id.desc()).limit(bs.SURUM_SINIRI)
    )).scalars().all()
    return [bs.surum_sozlugu(s) for s in satirlar]


async def _surum(db: AsyncSession, b: Belgeler, surum_id: int) -> BelgeSurumleri:
    s = (await db.execute(
        select(BelgeSurumleri).where(BelgeSurumleri.id == surum_id, BelgeSurumleri.belge_id == b.id)
    )).scalars().first()
    if s is None:
        raise BelgeHatasi("bulunamadi", 404)
    return s


async def _geri_yukle(db: AsyncSession, b: Belgeler, s: BelgeSurumleri, kisi: str, rol: str) -> None:
    if bs.strateji_mi(b.tur):
        # Eski gövde bugünkü şablon kurallarından geçsin (kutu adı değiştiyse temizlensin).
        icerik = _icerik_hazirla(b.tur, s.icerik or "")
    else:
        icerik = s.icerik or ""
    if bs.icerik_degistir(b, baslik=s.baslik, icerik=icerik, kisi=kisi, rol=rol):
        await bs.surum_yaz(db, b, kisi, rol, f"geri_yukleme:{s.surum}")
    await db.commit()


async def _guncelle(db: AsyncSession, b: Belgeler, g: BelgeGirdisi, kisi: str, rol: str) -> bool:
    """Ortak düzenleme (başlık, gövde, etiket, sabit). Yeni paylaşım olduysa True."""
    if g.surum is not None and int(g.surum) != int(b.surum or 1):
        raise BelgeHatasi("surum_catismasi", 409, guncel=int(b.surum or 1))
    baslik = None
    if g.baslik is not None:
        baslik = bs._metin(g.baslik, "baslik", bs.SINIR["baslik"], zorunlu=True, tek_satir=True)  # noqa: SLF001
    icerik = _icerik_hazirla(b.tur, g.icerik) if g.icerik is not None else None
    if g.etiketler is not None:
        import json

        yeni = json.dumps(bs.etiketleri_duzelt(g.etiketler), ensure_ascii=False)
        if yeni != (b.etiketler or "[]"):
            b.etiketler = yeni
            bs.arama_metnini_kur(b)
    if g.sabit is not None:
        b.sabit = bool(g.sabit)
    if bs.icerik_degistir(b, baslik=baslik, icerik=icerik, kisi=kisi, rol=rol):
        await bs.surum_yaz(db, b, kisi, rol, "duzenleme")
    return False


def _yeni_belge(g: BelgeGirdisi, kisi: str, rol: str) -> Belgeler:
    import json

    tur = g.tur or "belge"
    if tur not in bs.TURLER:
        raise BelgeHatasi("gecersiz", alan="tur")
    baslik = bs._metin(g.baslik, "baslik", bs.SINIR["baslik"], zorunlu=True, tek_satir=True)  # noqa: SLF001
    icerik = _icerik_hazirla(tur, g.icerik if g.icerik is not None else ({} if bs.strateji_mi(tur) else ""))
    b = Belgeler(tur=tur, baslik=baslik, icerik=icerik, etiketler=json.dumps(bs.etiketleri_duzelt(g.etiketler), ensure_ascii=False),
                 sabit=bool(g.sabit), surum=1, olusturan=kisi or None, son_duzenleyen=kisi or None, son_duzenleyen_rol=rol,
                 created_at=bs.simdi(), updated_at=bs.simdi())
    bs.arama_metnini_kur(b)
    return b


async def _yapilacak_isaretle(db: AsyncSession, b: Belgeler, g: YapilacakGirdisi, kisi: str, rol: str) -> None:
    if b.tur != "belge":
        raise BelgeHatasi("gecersiz", alan="tur")
    yeni = bs.yapilacak_isaretle(b.icerik or "", g.satir, g.metin, g.tamam)
    if bs.icerik_degistir(b, icerik=yeni, kisi=kisi, rol=rol):
        await bs.surum_yaz(db, b, kisi, rol, "yapilacak", birlestir=True)
    await db.commit()


# ---------------------------------------------------------------------------
# Yönetici
# ---------------------------------------------------------------------------
@yonetici_router.get("/meta")
async def yonetici_meta(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return {**_meta(bai.ai_hazir()), "kullanim": await bai.kullanim_ozeti(db, None)}


@yonetici_router.get("")
async def yonetici_listesi(
    request: Request,
    q: Optional[str] = Query(None),
    etiket: Optional[str] = Query(None),
    tur: Optional[str] = Query(None),
    alan: Optional[str] = Query(None),
    musteri: Optional[str] = Query(None),
    proje_id: Optional[int] = Query(None),
    gorunurluk: Optional[str] = Query(None),
    kaynak: Optional[str] = Query(None),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    try:
        s = select(Belgeler).where(bs.sorgu_ajans_gorur())
        k = bs.tur_kosulu(tur)
        if k is not None:
            s = s.where(k)
        k = bs.arama_kosulu(q)
        if k is not None:
            s = s.where(k)
    except BelgeHatasi as h:
        raise _hata(h)
    if alan in bs.ALANLAR:
        s = s.where(Belgeler.alan == alan)
    if musteri:
        s = s.where(Belgeler.musteri_email == bs.eposta_duzelt(musteri))
    if proje_id is not None:
        s = s.where(Belgeler.proje_id == proje_id)
    if gorunurluk in bs.GORUNURLUKLER:
        s = s.where(Belgeler.gorunurluk == gorunurluk)
    if kaynak == "ajans":
        s = s.where(func.coalesce(Belgeler.sahip_hesap, "") == "")
    elif kaynak == "musteri":
        s = s.where(func.coalesce(Belgeler.sahip_hesap, "") != "")
    satirlar = (await db.execute(s.order_by(*bs.siralama()).limit(bs.LISTE_SINIRI))).scalars().all()
    return await _liste_yaniti(db, list(satirlar), etiket)


@yonetici_router.post("")
async def yonetici_olustur(request: Request, govde: BelgeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    ben = _yonetici_iste(request)
    try:
        b = _yeni_belge(govde, ben, "admin")
        await _ajans_alanlari(db, b, govde, True)
    except BelgeHatasi as h:
        raise _hata(h)
    yeni_paylasim = _paylasim_gecisi(b, None)
    db.add(b)
    await db.flush()
    await bs.surum_yaz(db, b, ben, "admin", "olusturma")
    await db.commit()
    await db.refresh(b)
    if yeni_paylasim:
        await bs.musteriye_paylasildi_bildir(db, b)
    return await _ayrinti(db, b)


@yonetici_router.post("/onizle")
async def yonetici_onizle(request: Request, govde: OnizlemeGirdisi = Body(...)):
    _yonetici_iste(request)
    return _onizleme(govde)


def _onizleme(govde: OnizlemeGirdisi) -> Dict[str, Any]:
    from services.guvenli_html import belge_html

    try:
        icerik = bs._metin(govde.icerik, "icerik", bs.SINIR["icerik"])  # noqa: SLF001
    except BelgeHatasi as h:
        raise _hata(h)
    return {"html": belge_html(icerik), "yapilacaklar": bs.yapilacaklar_cikar(icerik)}


@yonetici_router.get("/yapilacaklar")
async def yonetici_yapilacaklar(
    request: Request, kapsam: str = Query("bana"), tamamlananlar: bool = Query(False), db: AsyncSession = _Depends(get_db)
):
    ben = _yonetici_iste(request)
    satirlar = (await db.execute(
        select(Belgeler).where(bs.sorgu_ajans_gorur(), Belgeler.tur == "belge", Belgeler.icerik.like("%[%]%"))
        .order_by(*bs.siralama()).limit(bs.YAPILACAK_TARAMA_SINIRI)
    )).scalars().all()
    return {"items": bs.tum_yapilacaklar(satirlar, kisi=ben, yalniz_bana=kapsam == "bana", tamamlananlar=tamamlananlar),
            "ben": ben}


@yonetici_router.post("/ai")
async def yonetici_ai(request: Request, govde: AiGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    ben = _yonetici_iste(request)
    try:
        return await bai.calistir(db, kullanim_hesabi=None, kisi=ben, govde=govde.model_dump())
    except BelgeHatasi as h:
        raise _hata(h)


async def _ajans_belgesi(db: AsyncSession, belge_id: int, *, yazma: bool) -> Belgeler:
    b = await _belge(db, belge_id)
    if bs.musteri_belgesi_mi(b):
        if b.gorunurluk != "paylasilan":
            raise BelgeHatasi("bulunamadi", 404)
        if yazma:
            raise BelgeHatasi("musteri_belgesi", 403)
    return b


@yonetici_router.get("/{belge_id}")
async def yonetici_ayrinti(belge_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        b = await _ajans_belgesi(db, belge_id, yazma=False)
    except BelgeHatasi as h:
        raise _hata(h)
    return await _ayrinti(db, b)


@yonetici_router.put("/{belge_id}")
async def yonetici_guncelle(belge_id: int, request: Request, govde: BelgeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    ben = _yonetici_iste(request)
    try:
        b = await _ajans_belgesi(db, belge_id, yazma=True)
        onceki = b.gorunurluk
        await _guncelle(db, b, govde, ben, "admin")
        if any(a in govde.model_fields_set for a in ("alan", "musteri_email", "proje_id", "gorunurluk")):
            await _ajans_alanlari(db, b, govde, False)
    except BelgeHatasi as h:
        await db.rollback()
        raise _hata(h)
    yeni_paylasim = _paylasim_gecisi(b, onceki)
    await db.commit()
    await db.refresh(b)
    if yeni_paylasim:
        await bs.musteriye_paylasildi_bildir(db, b)
    return await _ayrinti(db, b)


@yonetici_router.delete("/{belge_id}")
async def yonetici_sil(belge_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        b = await _ajans_belgesi(db, belge_id, yazma=True)
    except BelgeHatasi as h:
        raise _hata(h)
    await bs.surumleri_sil(db, b.id)
    await db.delete(b)
    await db.commit()
    return {"silindi": belge_id}


@yonetici_router.get("/{belge_id}/surumler")
async def yonetici_surumler(belge_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        b = await _ajans_belgesi(db, belge_id, yazma=False)
    except BelgeHatasi as h:
        raise _hata(h)
    return {"items": await _surum_listesi(db, b), "guncel": int(b.surum or 1)}


@yonetici_router.get("/{belge_id}/surumler/{surum_id}")
async def yonetici_surum(belge_id: int, surum_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        b = await _ajans_belgesi(db, belge_id, yazma=False)
        s = await _surum(db, b, surum_id)
    except BelgeHatasi as h:
        raise _hata(h)
    return _surum_ayrintisi(b, s)


def _surum_ayrintisi(b: Belgeler, s: BelgeSurumleri) -> Dict[str, Any]:
    d = bs.surum_sozlugu(s, icerikli=True)
    if b.tur == "belge":
        from services.guvenli_html import belge_html

        d["html"] = belge_html(s.icerik or "")
    else:
        gecici = Belgeler(tur=b.tur, icerik=s.icerik)
        d["strateji_icerik"] = bs.strateji_coz(gecici)
    return d


@yonetici_router.post("/{belge_id}/surumler/{surum_id}/geri-yukle")
async def yonetici_geri_yukle(belge_id: int, surum_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    ben = _yonetici_iste(request)
    try:
        b = await _ajans_belgesi(db, belge_id, yazma=True)
        s = await _surum(db, b, surum_id)
        await _geri_yukle(db, b, s, ben, "admin")
    except BelgeHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.refresh(b)
    return await _ayrinti(db, b)


@yonetici_router.post("/{belge_id}/yapilacak")
async def yonetici_yapilacak(belge_id: int, request: Request, govde: YapilacakGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    ben = _yonetici_iste(request)
    try:
        b = await _ajans_belgesi(db, belge_id, yazma=True)
        await _yapilacak_isaretle(db, b, govde, ben, "admin")
    except BelgeHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.refresh(b)
    return await _ayrinti(db, b)


@yonetici_router.post("/{belge_id}/yapilacak/gorev")
async def yonetici_gorev_bagla(belge_id: int, request: Request, govde: GorevBagiGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    """Madde Faz 2B ucuyla (`POST /api/v1/gorevler/proje/<id>`) göreve dönüştükten sonra bağı yazar."""
    ben = _yonetici_iste(request)
    from models.proje_gorevleri import ProjectTasks

    try:
        b = await _ajans_belgesi(db, belge_id, yazma=True)
        if b.tur != "belge":
            raise BelgeHatasi("gecersiz", alan="tur")
        g = (await db.execute(select(ProjectTasks).where(ProjectTasks.id == govde.gorev_id))).scalars().first()
        if g is None:
            raise BelgeHatasi("gorev_yok", 404)
        yeni = bs.gorev_bagla(b.icerik or "", govde.satir, govde.metin, g.id)
        if bs.icerik_degistir(b, icerik=yeni, kisi=ben, rol="admin"):
            await bs.surum_yaz(db, b, ben, "admin", f"gorev:{g.id}")
        await db.commit()
    except BelgeHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.refresh(b)
    return await _ayrinti(db, b)


@yonetici_router.get("/{belge_id}/pdf")
async def yonetici_pdf(belge_id: int, request: Request, dil: str = Query("tr"), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        b = await _ajans_belgesi(db, belge_id, yazma=False)
    except BelgeHatasi as h:
        raise _hata(h)
    return await _pdf(db, b, dil)


@yonetici_router.get("/{belge_id}/md")
async def yonetici_md(belge_id: int, request: Request, dil: str = Query("tr"), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        b = await _ajans_belgesi(db, belge_id, yazma=False)
    except BelgeHatasi as h:
        raise _hata(h)
    return _md_yaniti(bs.markdown_disa_aktar(b, bs.pdf_dili(dil)), bs.dosya_adi(b, "md"))


# ---------------------------------------------------------------------------
# Müşteri
# ---------------------------------------------------------------------------
def _paylasilan_kosulu(hesap: str):
    return (func.coalesce(Belgeler.sahip_hesap, "") == "") & (Belgeler.gorunurluk == "paylasilan") & (
        Belgeler.musteri_email == hesap)


async def _modul_acik(db: AsyncSession, hesap: str) -> bool:
    from services.moduller import modul_acik_mi

    return await modul_acik_mi(db, hesap, bs.MODUL)


async def _musteri_belgesi(db: AsyncSession, request: Request, belge_id: int, *, yazma: bool) -> Belgeler:
    """Kendi belgesi (modül açık + `belgeler` izni) ya da ajansın paylaştığı belge (salt okunur)."""
    bg = musteri_baglami(request)
    b = (await db.execute(select(Belgeler).where(Belgeler.id == belge_id))).scalars().first()
    if b is None:
        raise BelgeHatasi("bulunamadi", 404)
    if bs.eposta_duzelt(b.sahip_hesap) == bg.hesap_email:
        if not bg.izin_var("belgeler"):
            raise HTTPException(status_code=403, detail={"kod": "hesap_izni_yok", "izin": "belgeler"})
        if not await _modul_acik(db, bg.hesap_email):
            raise HTTPException(status_code=403, detail={"kod": "modul_kapali", "modul": bs.MODUL})
        return b
    paylasilan = not bs.musteri_belgesi_mi(b) and b.gorunurluk == "paylasilan" and bs.eposta_duzelt(b.musteri_email) == bg.hesap_email
    if not paylasilan:
        raise BelgeHatasi("bulunamadi", 404)
    if yazma:
        raise BelgeHatasi("salt_okunur", 403)
    return b


@musteri_router.get("/ozet")
async def musteri_ozet(request: Request, db: AsyncSession = _Depends(get_db)):
    """Panelin "Dosyalar ve belgeler" sekmesini gösterip göstermeyeceği (tek küçük sorgu)."""
    bg = musteri_baglami(request)
    paylasilan = (await db.execute(
        select(Belgeler.tur, func.count(Belgeler.id)).where(_paylasilan_kosulu(bg.hesap_email)).group_by(Belgeler.tur)
    )).all()
    belge = sum(int(n) for t, n in paylasilan if t == "belge")
    strateji = sum(int(n) for t, n in paylasilan if t != "belge")
    modul = await _modul_acik(db, bg.hesap_email)
    return {"paylasilan": belge + strateji, "paylasilan_belge": belge, "paylasilan_strateji": strateji,
            "modul_acik": modul, "izin": bg.izin_var("belgeler")}


@musteri_router.get("/meta")
async def musteri_meta(request: Request, db: AsyncSession = _Depends(get_db)):
    bg = musteri_baglami(request)
    modul = await _modul_acik(db, bg.hesap_email)
    kendi = modul and bg.izin_var("belgeler")
    d = {**_meta(bai.ai_hazir()), "modul_acik": modul, "kendi_belge": kendi}
    if kendi:
        d["kullanim"] = await bai.kullanim_ozeti(db, bg.hesap_email)
        sinir = await _belge_siniri(db, bg.hesap_email)
        d["belge_siniri"] = sinir
        d["belge_sayisi"] = await _kendi_sayisi(db, bg.hesap_email)
    return d


async def _belge_siniri(db: AsyncSession, hesap: str) -> int:
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, hesap, bs.MODUL, "belge_siniri")
    return int(deger) if deger is not None else bs.VARSAYILAN_BELGE_SINIRI


async def _kendi_sayisi(db: AsyncSession, hesap: str) -> int:
    return int((await db.execute(select(func.count(Belgeler.id)).where(Belgeler.sahip_hesap == hesap))).scalar() or 0)


@musteri_router.get("")
async def musteri_listesi(
    request: Request,
    q: Optional[str] = Query(None),
    etiket: Optional[str] = Query(None),
    tur: Optional[str] = Query(None),
    db: AsyncSession = _Depends(get_db),
):
    bg = musteri_baglami(request)
    kendi = bg.izin_var("belgeler") and await _modul_acik(db, bg.hesap_email)
    kosul = _paylasilan_kosulu(bg.hesap_email)
    if kendi:
        kosul = kosul | (Belgeler.sahip_hesap == bg.hesap_email)
    s = select(Belgeler).where(kosul)
    try:
        k = bs.tur_kosulu(tur)
        if k is not None:
            s = s.where(k)
        k = bs.arama_kosulu(q)
        if k is not None:
            s = s.where(k)
    except BelgeHatasi as h:
        raise _hata(h)
    satirlar = (await db.execute(s.order_by(*bs.siralama()).limit(bs.LISTE_SINIRI))).scalars().all()
    return {**await _liste_yaniti(db, list(satirlar), etiket), "kendi_belge": kendi}


@musteri_router.post("", dependencies=_KENDI)
async def musteri_olustur(request: Request, govde: BelgeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    bg = musteri_baglami(request)
    try:
        if await _kendi_sayisi(db, bg.hesap_email) >= await _belge_siniri(db, bg.hesap_email):
            raise BelgeHatasi("belge_siniri", 409, sinir=await _belge_siniri(db, bg.hesap_email))
        b = _yeni_belge(govde, bg.kisi_email, "client")
        await _musteri_alanlari(db, b, govde, bg.hesap_email)
    except BelgeHatasi as h:
        raise _hata(h)
    yeni_paylasim = _paylasim_gecisi(b, None)
    db.add(b)
    await db.flush()
    await bs.surum_yaz(db, b, bg.kisi_email, "client", "olusturma")
    await db.commit()
    await db.refresh(b)
    if yeni_paylasim:
        await bs.ajansa_paylasildi_bildir(db, b, bg.kisi_email)
    return await _ayrinti(db, b)


async def _musteri_alanlari(db: AsyncSession, b: Belgeler, g: BelgeGirdisi, hesap: str) -> None:
    b.sahip_hesap = hesap
    b.musteri_email = hesap
    if "proje_id" in g.model_fields_set or b.id is None:
        if g.proje_id is not None:
            p = await _proje(db, g.proje_id)
            if bs.eposta_duzelt(p.client_email) != hesap:
                raise BelgeHatasi("proje_yok", 404, alan="proje_id")
            b.proje_id, b.alan = p.id, "proje"
        else:
            b.proje_id, b.alan = None, "musteri"
    if g.gorunurluk is not None:
        if g.gorunurluk not in bs.GORUNURLUKLER:
            raise BelgeHatasi("gecersiz", alan="gorunurluk")
        b.gorunurluk = g.gorunurluk
    elif not b.gorunurluk:
        b.gorunurluk = "ekip"


@musteri_router.post("/onizle", dependencies=_KENDI)
async def musteri_onizle(request: Request, govde: OnizlemeGirdisi = Body(...)):
    musteri_baglami(request)
    return _onizleme(govde)


@musteri_router.get("/yapilacaklar")
async def musteri_yapilacaklar(
    request: Request, kapsam: str = Query("bana"), tamamlananlar: bool = Query(False), db: AsyncSession = _Depends(get_db)
):
    bg = musteri_baglami(request)
    kosul = _paylasilan_kosulu(bg.hesap_email)
    kendi = bg.izin_var("belgeler") and await _modul_acik(db, bg.hesap_email)
    if kendi:
        kosul = kosul | (Belgeler.sahip_hesap == bg.hesap_email)
    satirlar = (await db.execute(
        select(Belgeler).where(kosul, Belgeler.tur == "belge", Belgeler.icerik.like("%[%]%"))
        .order_by(*bs.siralama()).limit(bs.YAPILACAK_TARAMA_SINIRI)
    )).scalars().all()
    ogeler = bs.tum_yapilacaklar(satirlar, kisi=bg.kisi_email, yalniz_bana=kapsam == "bana", tamamlananlar=tamamlananlar)
    sahipler = {b.id: bs.musteri_belgesi_mi(b) for b in satirlar}
    for o in ogeler:
        o["salt_okunur"] = not sahipler.get(o["belge_id"], False)
    return {"items": ogeler, "ben": bg.kisi_email}


@musteri_router.post("/ai", dependencies=_KENDI)
async def musteri_ai(request: Request, govde: AiGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    bg = musteri_baglami(request)
    try:
        return await bai.calistir(db, kullanim_hesabi=bg.hesap_email, kisi=bg.kisi_email, govde=govde.model_dump())
    except BelgeHatasi as h:
        raise _hata(h)


@musteri_router.get("/{belge_id}")
async def musteri_ayrinti(belge_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    try:
        b = await _musteri_belgesi(db, request, belge_id, yazma=False)
    except BelgeHatasi as h:
        raise _hata(h)
    d = await _ayrinti(db, b)
    if not bs.musteri_belgesi_mi(b):
        # Ajans belgesinde iç ayrıntılar (kim düzenledi) müşteriye gerekmiyor.
        d["olusturan"] = None
        d["son_duzenleyen"] = None
    return d


@musteri_router.put("/{belge_id}", dependencies=_KENDI)
async def musteri_guncelle(belge_id: int, request: Request, govde: BelgeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    bg = musteri_baglami(request)
    try:
        b = await _musteri_belgesi(db, request, belge_id, yazma=True)
        onceki = b.gorunurluk
        await _guncelle(db, b, govde, bg.kisi_email, "client")
        await _musteri_alanlari(db, b, govde, bg.hesap_email)
    except BelgeHatasi as h:
        await db.rollback()
        raise _hata(h)
    yeni_paylasim = _paylasim_gecisi(b, onceki)
    await db.commit()
    await db.refresh(b)
    if yeni_paylasim:
        await bs.ajansa_paylasildi_bildir(db, b, bg.kisi_email)
    return await _ayrinti(db, b)


@musteri_router.delete("/{belge_id}", dependencies=_KENDI)
async def musteri_sil(belge_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    try:
        b = await _musteri_belgesi(db, request, belge_id, yazma=True)
    except BelgeHatasi as h:
        raise _hata(h)
    await bs.surumleri_sil(db, b.id)
    await db.delete(b)
    await db.commit()
    return {"silindi": belge_id}


@musteri_router.get("/{belge_id}/surumler", dependencies=_KENDI)
async def musteri_surumler(belge_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    try:
        b = await _musteri_belgesi(db, request, belge_id, yazma=True)
    except BelgeHatasi as h:
        raise _hata(h)
    return {"items": await _surum_listesi(db, b), "guncel": int(b.surum or 1)}


@musteri_router.get("/{belge_id}/surumler/{surum_id}", dependencies=_KENDI)
async def musteri_surum(belge_id: int, surum_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    try:
        b = await _musteri_belgesi(db, request, belge_id, yazma=True)
        s = await _surum(db, b, surum_id)
    except BelgeHatasi as h:
        raise _hata(h)
    return _surum_ayrintisi(b, s)


@musteri_router.post("/{belge_id}/surumler/{surum_id}/geri-yukle", dependencies=_KENDI)
async def musteri_geri_yukle(belge_id: int, surum_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    bg = musteri_baglami(request)
    try:
        b = await _musteri_belgesi(db, request, belge_id, yazma=True)
        s = await _surum(db, b, surum_id)
        await _geri_yukle(db, b, s, bg.kisi_email, "client")
    except BelgeHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.refresh(b)
    return await _ayrinti(db, b)


@musteri_router.post("/{belge_id}/yapilacak", dependencies=_KENDI)
async def musteri_yapilacak(belge_id: int, request: Request, govde: YapilacakGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    bg = musteri_baglami(request)
    try:
        b = await _musteri_belgesi(db, request, belge_id, yazma=True)
        await _yapilacak_isaretle(db, b, govde, bg.kisi_email, "client")
    except BelgeHatasi as h:
        await db.rollback()
        raise _hata(h)
    await db.refresh(b)
    return await _ayrinti(db, b)


@musteri_router.post("/{belge_id}/okundu")
async def musteri_okundu(belge_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Ajansın paylaştığı belge: "okudum / onaylıyorum" (sürüm başına bir kez; yeni sürümde yeniden)."""
    bg = musteri_baglami(request)
    try:
        b = await _musteri_belgesi(db, request, belge_id, yazma=False)
        if bs.musteri_belgesi_mi(b):
            raise BelgeHatasi("gecersiz", alan="belge")
    except BelgeHatasi as h:
        raise _hata(h)
    yeni = b.okundu_surum != int(b.surum or 1)
    if yeni:
        b.okundu_at = bs.simdi()
        b.okuyan = bg.kisi_email
        b.okundu_surum = int(b.surum or 1)
        await db.commit()
        await db.refresh(b)
        await bs.okundu_bildir(db, b, bg.kisi_email)
    d = await _ayrinti(db, b)
    d["olusturan"] = None
    d["son_duzenleyen"] = None
    return d


@musteri_router.get("/{belge_id}/pdf")
async def musteri_pdf(belge_id: int, request: Request, dil: str = Query("tr"), db: AsyncSession = _Depends(get_db)):
    try:
        b = await _musteri_belgesi(db, request, belge_id, yazma=False)
    except BelgeHatasi as h:
        raise _hata(h)
    return await _pdf(db, b, dil)


@musteri_router.get("/{belge_id}/md")
async def musteri_md(belge_id: int, request: Request, dil: str = Query("tr"), db: AsyncSession = _Depends(get_db)):
    try:
        b = await _musteri_belgesi(db, request, belge_id, yazma=False)
    except BelgeHatasi as h:
        raise _hata(h)
    return _md_yaniti(bs.markdown_disa_aktar(b, bs.pdf_dili(dil)), bs.dosya_adi(b, "md"))


router = (yonetici_router, musteri_router)
