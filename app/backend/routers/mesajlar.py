"""Faz 2G — müşteri ↔ ajans mesajlaşma (ayrıntı `services/mesajlar.py`).

Müşteri (`mesajlar` izni + `mesajlar` modülü; e-posta etkin hesaptan, yazan kişi jetondan)
  GET    /api/v1/mesajlarim/ozet                                   toplam okunmamış (yoklama)
  GET    /api/v1/mesajlarim/konusmalar                             okunmamış sayılarıyla ("Genel" kendiliğinden açılır)
  POST   /api/v1/mesajlarim/konusmalar                             {konu, proje_id?}
  GET    /api/v1/mesajlarim/konusmalar/{id}/mesajlar               ?sonra=&once=&adet=
  POST   /api/v1/mesajlarim/konusmalar/{id}/mesajlar               {metin, ekler?}
  POST   /api/v1/mesajlarim/konusmalar/{id}/okundu                 {mesaj_id}
  PUT    /api/v1/mesajlarim/mesajlar/{id}                          {metin} (kendi mesajı, 15 dk)
  DELETE /api/v1/mesajlarim/mesajlar/{id}                          (kendi mesajı, 15 dk; yumuşak)
  POST   /api/v1/mesajlarim/ekler                                  dosya (tür/boyut sınırları Dosyalar'la aynı)
  POST   /api/v1/mesajlarim/mesajlar/{id}/ekler/{dosya}/indirme-baglantisi

Yönetici (role=admin)
  GET    /api/v1/mesajlar/ozet
  GET    /api/v1/mesajlar/konusmalar                               ?durum=&q=&okunmamis=&hesap=
  POST   /api/v1/mesajlar/konusmalar                               {hesap_email, konu?, proje_id?}
  GET    /api/v1/mesajlar/konusmalar/{id}                          konuşma + hesabın projeleri
  PUT    /api/v1/mesajlar/konusmalar/{id}                          {durum: acik|arsiv, konu?}
  DELETE /api/v1/mesajlar/konusmalar/{id}                          çöp kutusuna (mesajlarıyla)
  GET|POST /api/v1/mesajlar/konusmalar/{id}/mesajlar, POST .../okundu, POST .../ekler
  PUT|DELETE /api/v1/mesajlar/mesajlar/{id}, POST .../ekler/{dosya}/indirme-baglantisi
  POST   /api/v1/mesajlar/konusmalar/{id}/hazir-cevap              {hazir_cevap_id} → {metin}
  POST   /api/v1/mesajlar/konusmalar/{id}/talep                    {mesaj_id?, konu?} → destek talebi
  POST   /api/v1/mesajlar/konusmalar/{id}/gorev                    {proje_id, mesaj_id?, baslik?} → görev

Hız sınırı: kişi başı dakikada 30 mesaj (429 `cok_hizli`).
"""

import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, BackgroundTasks, Body, File, HTTPException, Query, Request, UploadFile
from fastapi import Depends as _Depends
from models.mesajlar import KonusmaMesajlari
from pydantic import BaseModel
from services import mesajlar as servis
from services.mesajlar import MesajHatasi
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri

logger = logging.getLogger(__name__)

musteri_router = APIRouter(
    prefix="/api/v1/mesajlarim",
    tags=["mesajlar"],
    dependencies=[_Depends(izin_gerekli(servis.IZIN)), _Depends(modul_gerekli("mesajlar"))],
)
yonetici_router = APIRouter(prefix="/api/v1/mesajlar", tags=["mesajlar"], dependencies=[_Depends(yonetici_gerekli)])

#: Kişi başı dakikada en çok 30 mesaj; ek yükleme ayrı sayaçta.
_hiz = HizSiniri(30, 60.0)
_ek_hizi = HizSiniri(30, 60.0)


# ---------------------------------------------------------------------------
# Şemalar
# ---------------------------------------------------------------------------
class KonusmaGirdisi(BaseModel):
    konu: Optional[str] = None
    proje_id: Optional[int] = None


class YoneticiKonusmaGirdisi(KonusmaGirdisi):
    hesap_email: str


class MesajGirdisi(BaseModel):
    metin: Optional[str] = ""
    ekler: Optional[List[int]] = None


class DuzenlemeGirdisi(BaseModel):
    metin: Optional[str] = ""


class OkunduGirdisi(BaseModel):
    mesaj_id: int


class KonusmaGuncelleme(BaseModel):
    durum: Optional[str] = None
    konu: Optional[str] = None


class HazirCevapGirdisi(BaseModel):
    hazir_cevap_id: int


class TalepGirdisi(BaseModel):
    mesaj_id: Optional[int] = None
    konu: Optional[str] = None


class GorevGirdisi(BaseModel):
    proje_id: int
    mesaj_id: Optional[int] = None
    baslik: Optional[str] = None


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _hata(h: MesajHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _hiz_denetle(sinirlayici: HizSiniri, taraf: str, kisi: str) -> None:
    if not sinirlayici.izin_var_mi(f"{taraf}:{kisi}"):
        raise HTTPException(status_code=429, detail={"kod": "cok_hizli"})


def _musteri(request: Request):
    """(hesap, kişi, jetondaki ad). Ekip üyesinde `mesajlar` izni yoksa 403."""
    baglam = izin_iste(request, servis.IZIN)
    kullanici, _ = _yonetici_mi(request)
    return baglam.hesap_email, baglam.kisi_email, getattr(kullanici, "name", None)


def _yonetici(request: Request):
    kullanici, _ = _yonetici_mi(request)
    return servis.eposta_duzelt(getattr(kullanici, "email", None)), getattr(kullanici, "name", None)


def _tetikle(arka: BackgroundTasks) -> None:
    """Yoklama isteği bildirim taramasını da tetikler (dakikada en çok bir; yanıttan sonra)."""
    if servis.istekle_tetiklenmeli_mi():
        arka.add_task(servis.arka_planda_isle)


async def _ek_yukle(db: AsyncSession, *, hesap: str, kisi: str, rol: str, dosya: UploadFile) -> Dict[str, Any]:
    """Dosyalar'ın yükleme akışı (içerikten tür doğrulama, boyut sınırı, depo) — `Mesajlar` klasörüne."""
    from services import dosyalar as ds

    try:
        veri = await ds.akistan_oku(dosya, await ds.boyut_siniri_bayt(db))
        await ds.klasor_hazirla(db, hesap, servis.MESAJ_KLASORU, "musteri")
        kayit = await ds.dosya_kaydet(
            db, eposta=hesap, klasor=servis.MESAJ_KLASORU, ad_ham=dosya.filename or "", veri=veri,
            yukleyen=kisi, yukleyen_rol=rol,
        )
        await db.commit()
        await db.refresh(kayit)
    except ds.DosyaHatasi as h:
        await db.rollback()
        raise HTTPException(status_code=h.durum, detail=h.detay())
    return {"id": kayit.id, "ad": kayit.ad, "boyut": int(kayit.boyut or 0), "tur": kayit.tur}


# ---------------------------------------------------------------------------
# Müşteri
# ---------------------------------------------------------------------------
@musteri_router.get("/ozet")
async def musteri_ozet(request: Request, arka: BackgroundTasks, db: AsyncSession = _Depends(get_db)):
    hesap, kisi, _ = _musteri(request)
    _tetikle(arka)
    return await servis.ozet(db, kisi, "client", hesap)


@musteri_router.get("/konusmalar")
async def musteri_konusmalar(request: Request, db: AsyncSession = _Depends(get_db)):
    hesap, kisi, _ = _musteri(request)
    return {"konusmalar": await servis.musteri_konusmalari(db, hesap, kisi)}


@musteri_router.post("/konusmalar")
async def musteri_konusma_ac(request: Request, govde: KonusmaGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    hesap, kisi, _ = _musteri(request)
    try:
        k = await servis.konusma_ac(db, hesap=hesap, konu=govde.konu, proje_id=govde.proje_id, olusturan=kisi, musteri=True)
    except MesajHatasi as h:
        raise _hata(h)
    return servis.konusma_sozlugu(k)


@musteri_router.get("/konusmalar/{konusma_id}/mesajlar")
async def musteri_mesajlar(
    konusma_id: int,
    request: Request,
    sonra: Optional[int] = Query(None, ge=0),
    once: Optional[int] = Query(None, ge=0),
    adet: Optional[int] = Query(None, ge=1, le=servis.EN_COK_SAYFA),
    db: AsyncSession = _Depends(get_db),
):
    hesap, kisi, _ = _musteri(request)
    try:
        k = await servis.konusma_bul(db, konusma_id, hesap)
    except MesajHatasi as h:
        raise _hata(h)
    return await servis.mesaj_listesi(db, k, taraf="client", kisi=kisi, sonra=sonra, once=once, adet=adet)


@musteri_router.post("/konusmalar/{konusma_id}/mesajlar")
async def musteri_mesaj_gonder(
    konusma_id: int, request: Request, govde: MesajGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    hesap, kisi, ad = _musteri(request)
    try:
        k = await servis.konusma_bul(db, konusma_id, hesap)
        _hiz_denetle(_hiz, "client", kisi)
        m = await servis.mesaj_gonder(
            db, k, taraf="client", kisi=kisi, yazan_ad=servis.musteri_adi(kisi, ad), metin=govde.metin, ek_idler=govde.ekler
        )
    except MesajHatasi as h:
        raise _hata(h)
    return servis.mesaj_sozlugu(m, bakan_taraf="client", kisi=kisi)


@musteri_router.post("/konusmalar/{konusma_id}/okundu")
async def musteri_okundu(
    konusma_id: int, request: Request, govde: OkunduGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    hesap, kisi, _ = _musteri(request)
    try:
        k = await servis.konusma_bul(db, konusma_id, hesap)
    except MesajHatasi as h:
        raise _hata(h)
    return {"okudugum": await servis.okundu(db, k, kisi=kisi, taraf="client", mesaj_id=govde.mesaj_id)}


@musteri_router.put("/mesajlar/{mesaj_id}")
async def musteri_mesaj_duzenle(
    mesaj_id: int, request: Request, govde: DuzenlemeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    hesap, kisi, _ = _musteri(request)
    try:
        m, k = await servis.kendi_mesaji(db, mesaj_id, taraf="client", kisi=kisi, hesap=hesap)
        m = await servis.mesaj_duzenle(db, m, k, govde.metin)
    except MesajHatasi as h:
        raise _hata(h)
    return servis.mesaj_sozlugu(m, bakan_taraf="client", kisi=kisi)


@musteri_router.delete("/mesajlar/{mesaj_id}")
async def musteri_mesaj_sil(mesaj_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    hesap, kisi, _ = _musteri(request)
    try:
        m, k = await servis.kendi_mesaji(db, mesaj_id, taraf="client", kisi=kisi, hesap=hesap)
        m = await servis.mesaj_sil(db, m, k)
    except MesajHatasi as h:
        raise _hata(h)
    return servis.mesaj_sozlugu(m, bakan_taraf="client", kisi=kisi)


@musteri_router.post("/ekler")
async def musteri_ek_yukle(request: Request, dosya: UploadFile = File(...), db: AsyncSession = _Depends(get_db)):
    hesap, kisi, _ = _musteri(request)
    _hiz_denetle(_ek_hizi, "client", kisi)
    return await _ek_yukle(db, hesap=hesap, kisi=kisi, rol="client", dosya=dosya)


@musteri_router.post("/mesajlar/{mesaj_id}/ekler/{dosya_id}/indirme-baglantisi")
async def musteri_ek_indir(mesaj_id: int, dosya_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    hesap, _, _ = _musteri(request)
    try:
        yol, son = await servis.ek_indirme(db, mesaj_id, dosya_id, hesap)
    except MesajHatasi as h:
        raise _hata(h)
    return {"adres": yol, "son": son}


# ---------------------------------------------------------------------------
# Yönetici
# ---------------------------------------------------------------------------
@yonetici_router.get("/ozet")
async def yonetici_ozet(request: Request, arka: BackgroundTasks, db: AsyncSession = _Depends(get_db)):
    kisi, _ = _yonetici(request)
    _tetikle(arka)
    return await servis.ozet(db, kisi, "admin")


@yonetici_router.get("/konusmalar")
async def yonetici_konusmalar(
    request: Request,
    durum: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=200),
    okunmamis: bool = Query(False),
    hesap: Optional[str] = Query(None, max_length=254),
    db: AsyncSession = _Depends(get_db),
):
    kisi, _ = _yonetici(request)
    return {
        "konusmalar": await servis.yonetici_konusmalari(db, kisi, durum=durum, q=q, okunmamis=okunmamis, hesap=hesap)
    }


@yonetici_router.post("/konusmalar")
async def yonetici_konusma_ac(
    request: Request, govde: YoneticiKonusmaGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    kisi, _ = _yonetici(request)
    hesap = servis.eposta_duzelt(govde.hesap_email)
    if "@" not in hesap or len(hesap) > 254 or any(c.isspace() for c in hesap):
        raise HTTPException(status_code=400, detail={"kod": "eposta_gecersiz"})
    try:
        k = await servis.konusma_ac(db, hesap=hesap, konu=govde.konu, proje_id=govde.proje_id, olusturan=kisi, musteri=False)
    except MesajHatasi as h:
        raise _hata(h)
    return servis.konusma_sozlugu(k, yonetici=True)


@yonetici_router.get("/konusmalar/{konusma_id}")
async def yonetici_konusma(konusma_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    from models.projects import Projects
    from services.hesap_ekibi import hesap_adlari

    kisi, _ = _yonetici(request)
    try:
        k = await servis.konusma_bul(db, konusma_id)
    except MesajHatasi as h:
        raise _hata(h)
    sayilar = await servis.okunmamis_sayilari(db, [k.id], kisi, "admin")
    adlar = await hesap_adlari(db, [k.hesap_email])
    projeler = (
        await db.execute(
            select(Projects.id, Projects.title)
            .where(func.lower(Projects.client_email) == k.hesap_email)
            .order_by(Projects.id.desc())
            .limit(100)
        )
    ).all()
    return {
        **servis.konusma_sozlugu(k, okunmamis=sayilar.get(k.id, 0), hesap_adi=adlar.get(k.hesap_email), yonetici=True),
        "projeler": [{"id": p[0], "baslik": p[1]} for p in projeler],
    }


@yonetici_router.put("/konusmalar/{konusma_id}")
async def yonetici_konusma_guncelle(
    konusma_id: int, request: Request, govde: KonusmaGuncelleme = Body(...), db: AsyncSession = _Depends(get_db)
):
    try:
        k = await servis.konusma_bul(db, konusma_id)
        if govde.durum is not None:
            if govde.durum not in servis.DURUMLAR:
                raise MesajHatasi(400, "durum_gecersiz")
            k.durum = govde.durum
        if govde.konu is not None and not k.tekil_anahtar:
            konu = servis.konu_temizle(govde.konu)
            if not konu:
                raise MesajHatasi(400, "konu_gerekli")
            k.konu = konu
    except MesajHatasi as h:
        raise _hata(h)
    await db.commit()
    await db.refresh(k)
    return servis.konusma_sozlugu(k, yonetici=True)


@yonetici_router.delete("/konusmalar/{konusma_id}")
async def yonetici_konusma_sil(konusma_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    try:
        k = await servis.konusma_bul(db, konusma_id)
    except MesajHatasi as h:
        raise _hata(h)
    await servis.konusma_sil(db, k)
    return {"silindi": konusma_id}


@yonetici_router.get("/konusmalar/{konusma_id}/mesajlar")
async def yonetici_mesajlar(
    konusma_id: int,
    request: Request,
    sonra: Optional[int] = Query(None, ge=0),
    once: Optional[int] = Query(None, ge=0),
    adet: Optional[int] = Query(None, ge=1, le=servis.EN_COK_SAYFA),
    db: AsyncSession = _Depends(get_db),
):
    kisi, _ = _yonetici(request)
    try:
        k = await servis.konusma_bul(db, konusma_id)
    except MesajHatasi as h:
        raise _hata(h)
    return await servis.mesaj_listesi(db, k, taraf="admin", kisi=kisi, sonra=sonra, once=once, adet=adet)


@yonetici_router.post("/konusmalar/{konusma_id}/mesajlar")
async def yonetici_mesaj_gonder(
    konusma_id: int, request: Request, govde: MesajGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    kisi, jeton_adi = _yonetici(request)
    try:
        k = await servis.konusma_bul(db, konusma_id)
        _hiz_denetle(_hiz, "admin", kisi)
        ad = await servis.ajans_adi(db, kisi, jeton_adi)
        m = await servis.mesaj_gonder(db, k, taraf="admin", kisi=kisi, yazan_ad=ad, metin=govde.metin, ek_idler=govde.ekler)
    except MesajHatasi as h:
        raise _hata(h)
    return servis.mesaj_sozlugu(m, bakan_taraf="admin", kisi=kisi)


@yonetici_router.post("/konusmalar/{konusma_id}/okundu")
async def yonetici_okundu(
    konusma_id: int, request: Request, govde: OkunduGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    kisi, _ = _yonetici(request)
    try:
        k = await servis.konusma_bul(db, konusma_id)
    except MesajHatasi as h:
        raise _hata(h)
    return {"okudugum": await servis.okundu(db, k, kisi=kisi, taraf="admin", mesaj_id=govde.mesaj_id)}


@yonetici_router.post("/konusmalar/{konusma_id}/ekler")
async def yonetici_ek_yukle(
    konusma_id: int, request: Request, dosya: UploadFile = File(...), db: AsyncSession = _Depends(get_db)
):
    kisi, _ = _yonetici(request)
    try:
        k = await servis.konusma_bul(db, konusma_id)
    except MesajHatasi as h:
        raise _hata(h)
    _hiz_denetle(_ek_hizi, "admin", kisi)
    return await _ek_yukle(db, hesap=k.hesap_email, kisi=kisi, rol="admin", dosya=dosya)


@yonetici_router.put("/mesajlar/{mesaj_id}")
async def yonetici_mesaj_duzenle(
    mesaj_id: int, request: Request, govde: DuzenlemeGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    kisi, _ = _yonetici(request)
    try:
        m, k = await servis.kendi_mesaji(db, mesaj_id, taraf="admin", kisi=kisi)
        m = await servis.mesaj_duzenle(db, m, k, govde.metin)
    except MesajHatasi as h:
        raise _hata(h)
    return servis.mesaj_sozlugu(m, bakan_taraf="admin", kisi=kisi)


@yonetici_router.delete("/mesajlar/{mesaj_id}")
async def yonetici_mesaj_sil(mesaj_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    kisi, _ = _yonetici(request)
    try:
        m, k = await servis.kendi_mesaji(db, mesaj_id, taraf="admin", kisi=kisi)
        m = await servis.mesaj_sil(db, m, k)
    except MesajHatasi as h:
        raise _hata(h)
    return servis.mesaj_sozlugu(m, bakan_taraf="admin", kisi=kisi)


@yonetici_router.post("/mesajlar/{mesaj_id}/ekler/{dosya_id}/indirme-baglantisi")
async def yonetici_ek_indir(mesaj_id: int, dosya_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    try:
        yol, son = await servis.ek_indirme(db, mesaj_id, dosya_id)
    except MesajHatasi as h:
        raise _hata(h)
    return {"adres": yol, "son": son}


@yonetici_router.post("/konusmalar/{konusma_id}/hazir-cevap")
async def yonetici_hazir_cevap(
    konusma_id: int, request: Request, govde: HazirCevapGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    """2C'deki hazır cevabı bu konuşmaya göre doldurur ({musteri_adi}, {konu}); gönderMEZ."""
    from models.destek_sla import HazirCevaplar
    from routers.destek import degiskenleri_doldur
    from services.hesap_ekibi import hesap_adlari

    try:
        k = await servis.konusma_bul(db, konusma_id)
    except MesajHatasi as h:
        raise _hata(h)
    h = (await db.execute(select(HazirCevaplar).where(HazirCevaplar.id == govde.hazir_cevap_id))).scalars().first()
    if h is None:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    adlar = await hesap_adlari(db, [k.hesap_email])
    ad = adlar.get(k.hesap_email) or k.hesap_email.split("@")[0]
    return {"metin": degiskenleri_doldur(h.metin, {"musteri_adi": ad, "talep_no": "", "konu": k.konu})}


async def _kaynak_mesaj(db: AsyncSession, k, mesaj_id: Optional[int]) -> Optional[KonusmaMesajlari]:
    """Seçilen mesaj (bu konuşmadan) ya da müşterinin son mesajı."""
    M = KonusmaMesajlari
    sorgu = select(M).where(M.konusma_id == k.id, M.silindi.is_(False))
    if mesaj_id is not None:
        m = (await db.execute(sorgu.where(M.id == mesaj_id))).scalars().first()
        if m is None:
            raise HTTPException(status_code=404, detail={"kod": "mesaj_yok"})
        return m
    return (await db.execute(sorgu.where(M.yazan_rol == "client").order_by(M.id.desc()).limit(1))).scalars().first()


@yonetici_router.post("/konusmalar/{konusma_id}/talep")
async def yonetici_talebe_cevir(
    konusma_id: int, request: Request, govde: TalepGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    """Mevcut talep akışıyla (servis + `talep_acildi`: kurallar, SLA, yönetici bildirimi) destek talebi."""
    from services.destek_talep import talep_acildi
    from services.hesap_ekibi import hesap_adlari
    from services.support_tickets import Support_ticketsService

    try:
        k = await servis.konusma_bul(db, konusma_id)
    except MesajHatasi as h:
        raise _hata(h)
    m = await _kaynak_mesaj(db, k, govde.mesaj_id)
    metin = (m.metin if m else "") or ""
    if m and not metin:
        metin = ", ".join(e["ad"] for e in servis.ekleri_coz(m.ekler))
    if not metin.strip():
        raise HTTPException(status_code=400, detail={"kod": "mesaj_yok"})
    konu = servis.konu_temizle(govde.konu) or servis.konu_temizle(f"{k.konu}: {' '.join(metin.split())[:80]}")
    adlar = await hesap_adlari(db, [k.hesap_email])
    talep = await Support_ticketsService(db).create(
        {
            "client_email": k.hesap_email,
            "client_name": adlar.get(k.hesap_email),
            "subject": konu,
            "message": metin,
            "status": "open",
            "priority": "normal",
            "hizmet": "genel",
            "project_id": k.proje_id,
            "kaynak": "panel",
            "acan_email": (m.yazan_email if m and m.yazan_rol == "client" else None),
        }
    )
    await talep_acildi(db, talep, kanal="panel")
    return {"talep_id": talep.id, "konu": talep.subject}


@yonetici_router.post("/konusmalar/{konusma_id}/gorev")
async def yonetici_goreve_cevir(
    konusma_id: int, request: Request, govde: GorevGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    """Mevcut görev ekleme ucunun kendisiyle (`routers/gorevler.gorev_ekle`) projeye görev."""
    from routers import gorevler as gorev_router

    try:
        k = await servis.konusma_bul(db, konusma_id)
        proje_id = await servis.proje_dogrula(db, k.hesap_email, govde.proje_id)
    except MesajHatasi as h:
        raise _hata(h)
    m = await _kaynak_mesaj(db, k, govde.mesaj_id)
    metin = (m.metin if m else "") or ""
    baslik = servis.konu_temizle(govde.baslik) or servis.konu_temizle(" ".join(metin.split())[:120]) or k.konu
    aciklama = f"{metin}\n\n— Mesajlar › {k.konu} (#{k.id})" if metin else f"Mesajlar › {k.konu} (#{k.id})"
    return await gorev_router.gorev_ekle(
        proje_id,  # type: ignore[arg-type]
        request,
        gorev_router.GorevGirdisi(baslik=baslik, aciklama=aciklama[: gorev_router.ACIKLAMA_SINIRI]),
        db,
    )


router = (musteri_router, yonetici_router)
