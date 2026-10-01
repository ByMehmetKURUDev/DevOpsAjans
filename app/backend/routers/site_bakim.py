"""Müşteri sitesi bakım kartı, uptime kontrolleri ve herkese açık durum sayfası (Faz 2A).

Yönetici   /api/v1/site-bakim/...            (bitiş tarihleri, uptime, durum sayfası)
Müşteri    /api/v1/sitelerim-bakim/...       (salt okunur kart + durum sayfası aç/kapa)
Açık       /api/v1/durum/{slug}              (yalnız açılmış sayfa; toplulaştırılmış veri)

Müşterinin hiçbir parolası tutulmuyor; yalnız sağlayıcı ADI ve bitiş
tarihleri. Uptime adresi eklenirken SSRF denetiminden geçiyor (iç ağ,
döngü, bulut meta veri adresi reddediliyor); ölçüm anında da her istek
aynı korumalı istemciden gidiyor.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.hesap_baglami import izin_gerekli, musteri_eposta
from fastapi import APIRouter, Body, HTTPException, Request, Response, status
from fastapi import Depends as _Depends
from models.client_sites import Client_sites
from models.site_izleme import SiteIzleme, UptimeKontrolu
from pydantic import BaseModel
from services import site_analizi as sa
from services import site_izleme as si
from services.moduller import modul_acik_mi, toplu_durumlar
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/site-bakim", tags=["site-bakim"])
musteri_router = APIRouter(
    prefix="/api/v1/sitelerim-bakim",
    tags=["site-bakim"],
    # Faz 2E: ekip üyesinde `siteler` izni.
    dependencies=[_Depends(izin_gerekli("siteler")), _Depends(modul_gerekli("sitem"))],
)
acik_router = APIRouter(prefix="/api/v1/durum", tags=["durum-sayfasi"])

KONTROL_SITE_BASINA = 5
METIN_SINIRI = 120
NOT_SINIRI = 4000


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class IzlemeGuncelleme(BaseModel):
    alan_adi: Optional[str] = None
    #: YYYY-MM-DD; "" → sil. Doluysa kaynak "elle" olur ve RDAP ezmez.
    alan_bitis: Optional[str] = None
    alan_saglayici: Optional[str] = None
    hosting_bitis: Optional[str] = None
    hosting_saglayici: Optional[str] = None
    ssl_elle_yenilenir: Optional[bool] = None
    notlar: Optional[str] = None


class KontrolGirdisi(BaseModel):
    url: str
    aralik_dk: Optional[int] = 5
    anahtar_kelime: Optional[str] = None
    beklenen_kod: Optional[int] = 200
    acik: Optional[bool] = True


class KontrolGuncelleme(BaseModel):
    url: Optional[str] = None
    aralik_dk: Optional[int] = None
    anahtar_kelime: Optional[str] = None
    beklenen_kod: Optional[int] = None
    acik: Optional[bool] = None


class DurumSayfasiGirdisi(BaseModel):
    acik: bool
    index: Optional[bool] = None


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _eposta(kullanici: Any) -> str:
    return (getattr(kullanici, "email", "") or "").strip().lower()


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
    return _eposta(kullanici)


def _musteri_iste(request: Request) -> str:
    """Etkin hesabın e-postası (Faz 2E)."""
    kullanici, _ = _yonetici_mi(request)
    if not _eposta(kullanici):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli")
    return musteri_eposta(request)


def _hata(kod: int, anahtar: str) -> HTTPException:
    return HTTPException(status_code=kod, detail={"kod": anahtar})


async def _site_bul(db: AsyncSession, site_id: int) -> Client_sites:
    site = (await db.execute(select(Client_sites).where(Client_sites.id == site_id))).scalar_one_or_none()
    if site is None:
        raise _hata(404, "site_yok")
    return site


async def _kontrol_bul(db: AsyncSession, kontrol_id: int) -> UptimeKontrolu:
    k = (await db.execute(select(UptimeKontrolu).where(UptimeKontrolu.id == kontrol_id))).scalar_one_or_none()
    if k is None:
        raise _hata(404, "kontrol_yok")
    return k


def _metin(deger: Optional[str], sinir: int = METIN_SINIRI) -> Optional[str]:
    d = (deger or "").strip()
    return d[:sinir] or None


def _tarih(deger: Optional[str]) -> Optional[datetime]:
    """YYYY-MM-DD → o günün öğlesi (UTC). Öğle: saat dilimi kaymasıyla gün değişmesin."""
    d = (deger or "").strip()
    if not d:
        return None
    try:
        gun = datetime.strptime(d[:10], "%Y-%m-%d")
    except ValueError as exc:
        raise _hata(400, "tarih_gecersiz") from exc
    if not 2000 <= gun.year <= 2100:
        raise _hata(400, "tarih_gecersiz")
    return gun.replace(hour=12, tzinfo=timezone.utc)


def _aralik(deger: Optional[int]) -> int:
    try:
        d = int(deger if deger is not None else si.EN_AZ_ARALIK_DK)
    except (TypeError, ValueError) as exc:
        raise _hata(400, "aralik_gecersiz") from exc
    if d < si.EN_AZ_ARALIK_DK or d > 1440:
        raise _hata(400, "aralik_gecersiz")
    return d


def _beklenen_kod(deger: Optional[int]) -> int:
    try:
        d = int(deger if deger is not None else 200)
    except (TypeError, ValueError) as exc:
        raise _hata(400, "kod_gecersiz") from exc
    if not 100 <= d <= 599:
        raise _hata(400, "kod_gecersiz")
    return d


async def _adres_denetle(ham: str) -> str:
    try:
        return await si.uptime_adresi_denetle(ham)
    except sa.AnalizHatasi as h:
        raise _hata(400, h.kod) from h


def _kontrol_sozlugu(k: UptimeKontrolu) -> Dict[str, Any]:
    return {
        "id": k.id,
        "site_id": k.site_id,
        "url": k.url,
        "aralik_dk": k.aralik_dk,
        "anahtar_kelime": k.anahtar_kelime,
        "beklenen_kod": k.beklenen_kod,
        "acik": bool(k.acik),
        "son_kontrol_at": si.iso(k.son_kontrol_at),
        "son_durum": k.son_durum,
        "ardisik_hata": int(k.ardisik_hata or 0),
    }


def _durum_adresi(iz: Optional[SiteIzleme]) -> Optional[str]:
    if iz is None or not iz.durum_sayfasi_acik or not iz.durum_slug:
        return None
    return f"/durum/{iz.durum_slug}"


async def _kartlar(
    db: AsyncSession, siteler: List[Client_sites], *, yonetici: bool
) -> List[Dict[str, Any]]:
    """Site kartları: bitişler + uptime özeti (+ yöneticiye kontroller)."""
    idler = [s.id for s in siteler]
    izlemeler = await si.izlemeler_sozlugu(db, idler)
    ozetler = await si.uptime_ozetleri(db, idler)
    kontroller: Dict[int, List[UptimeKontrolu]] = {}
    if yonetici and idler:
        for k in (
            await db.execute(select(UptimeKontrolu).where(UptimeKontrolu.site_id.in_(idler)).order_by(UptimeKontrolu.id))
        ).scalars().all():
            kontroller.setdefault(k.site_id, []).append(k)
    mm = await toplu_durumlar(db, [s.client_email for s in siteler])
    kartlar = []
    for s in siteler:
        iz = izlemeler.get(s.id)
        m = mm.get((s.client_email or "").strip().lower())
        uptime_acik = bool(m and m.durumlar.get("uptime") and m.durumlar["uptime"].acik)
        yenileme_acik = bool(m and m.durumlar.get("yenileme") and m.durumlar["yenileme"].acik)
        ozet = ozetler.get(s.id)
        kart: Dict[str, Any] = {
            "site_id": s.id,
            "ad": s.ad,
            "adres": s.adres,
            "client_email": s.client_email,
            "izleme": si.izleme_sozlugu(iz),
            "durum_adresi": _durum_adresi(iz),
            "uptime_modulu": uptime_acik,
            "yenileme_modulu": yenileme_acik,
        }
        if yonetici:
            kart["uptime"] = ozet
            kart["kontroller"] = [_kontrol_sozlugu(k) for k in kontroller.get(s.id, [])]
        else:
            # Müşteri: modül kapalıysa uptime verisi yok; iç hata kategorisi (sebep) hiç yok.
            kart["uptime"] = None
            if uptime_acik and ozet is not None:
                acik = si.acik_ozet(ozet)
                acik["kontrol_sayisi"] = ozet["kontrol_sayisi"]
                kart["uptime"] = acik
            kart["izleme"].pop("notlar", None)
        kartlar.append(kart)
    return kartlar


async def _durum_sayfasi_ayarla(db: AsyncSession, site: Client_sites, govde: DurumSayfasiGirdisi) -> SiteIzleme:
    iz = await si.izleme_getir(db, site)
    assert iz is not None
    iz.durum_sayfasi_acik = bool(govde.acik)
    if govde.index is not None:
        iz.durum_index = bool(govde.index)
    if govde.acik and not iz.durum_slug:
        for _ in range(5):
            iz.durum_slug = si.slug_uret(site.ad)
            try:
                async with db.begin_nested():
                    await db.flush()
                break
            except IntegrityError:
                continue
    await db.commit()
    await db.refresh(iz)
    return iz


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("")
async def tum_kartlar(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    siteler = list((await db.execute(select(Client_sites).order_by(Client_sites.id.desc()).limit(500))).scalars().all())
    return await _kartlar(db, siteler, yonetici=True)


@yonetici_router.get("/{site_id}")
async def kart(site_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    site = await _site_bul(db, site_id)
    return (await _kartlar(db, [site], yonetici=True))[0]


@yonetici_router.put("/{site_id}")
async def izleme_guncelle(
    site_id: int, request: Request, govde: IzlemeGuncelleme = Body(...), db: AsyncSession = _Depends(get_db)
):
    _yonetici_iste(request)
    site = await _site_bul(db, site_id)
    iz = await si.izleme_getir(db, site)
    assert iz is not None
    alanlar = govde.model_fields_set
    if "alan_adi" in alanlar:
        try:
            yeni_alan = si.alan_adi_dogrula(govde.alan_adi)
        except ValueError as exc:
            raise _hata(400, "alan_gecersiz") from exc
        if yeni_alan != iz.alan_adi:
            iz.alan_adi = yeni_alan
            iz.alan_kontrol_at = None  # yeni alan adı bir sonraki turda taransın
            if iz.alan_bitis_kaynak == "rdap":
                iz.alan_bitis = None
                iz.alan_bitis_kaynak = None
    if "alan_bitis" in alanlar:
        tarih = _tarih(govde.alan_bitis)
        iz.alan_bitis = tarih
        iz.alan_bitis_kaynak = "elle" if tarih else None
        if tarih is None:
            iz.alan_kontrol_at = None
    if "hosting_bitis" in alanlar:
        iz.hosting_bitis = _tarih(govde.hosting_bitis)
    if "alan_saglayici" in alanlar:
        iz.alan_saglayici = _metin(govde.alan_saglayici)
    if "hosting_saglayici" in alanlar:
        iz.hosting_saglayici = _metin(govde.hosting_saglayici)
    if "ssl_elle_yenilenir" in alanlar and govde.ssl_elle_yenilenir is not None:
        iz.ssl_elle_yenilenir = bool(govde.ssl_elle_yenilenir)
    if "notlar" in alanlar:
        iz.notlar = _metin(govde.notlar, NOT_SINIRI)
    await db.commit()
    return (await _kartlar(db, [site], yonetici=True))[0]


@yonetici_router.post("/{site_id}/tara")
async def simdi_tara(site_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """RDAP + SSL'i şimdi okur (elle girilmiş alan adı bitişi ezilmez)."""
    _yonetici_iste(request)
    site = await _site_bul(db, site_id)
    await si.siteyi_tara(db, site)
    await db.commit()
    return (await _kartlar(db, [site], yonetici=True))[0]


@yonetici_router.post("/{site_id}/uptime")
async def kontrol_ekle(
    site_id: int, request: Request, govde: KontrolGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    _yonetici_iste(request)
    site = await _site_bul(db, site_id)
    mevcut = (await db.execute(select(UptimeKontrolu).where(UptimeKontrolu.site_id == site.id))).scalars().all()
    if len(mevcut) >= KONTROL_SITE_BASINA:
        raise _hata(409, "kontrol_siniri")
    url = await _adres_denetle(govde.url)
    k = UptimeKontrolu(
        site_id=site.id,
        url=url,
        aralik_dk=_aralik(govde.aralik_dk),
        anahtar_kelime=_metin(govde.anahtar_kelime, si.ANAHTAR_KELIME_EN_COK),
        beklenen_kod=_beklenen_kod(govde.beklenen_kod),
        acik=govde.acik is not False,
        ardisik_hata=0,
    )
    db.add(k)
    await db.commit()
    await db.refresh(k)
    return _kontrol_sozlugu(k)


@yonetici_router.patch("/uptime/{kontrol_id}")
async def kontrol_guncelle(
    kontrol_id: int, request: Request, govde: KontrolGuncelleme = Body(...), db: AsyncSession = _Depends(get_db)
):
    _yonetici_iste(request)
    k = await _kontrol_bul(db, kontrol_id)
    alanlar = govde.model_fields_set
    if "url" in alanlar and govde.url is not None:
        yeni = await _adres_denetle(govde.url)
        if yeni != k.url:
            k.url = yeni
            k.ardisik_hata = 0
            k.ilk_hata_at = None
            k.son_durum = None
    if "aralik_dk" in alanlar:
        k.aralik_dk = _aralik(govde.aralik_dk)
    if "anahtar_kelime" in alanlar:
        k.anahtar_kelime = _metin(govde.anahtar_kelime, si.ANAHTAR_KELIME_EN_COK)
    if "beklenen_kod" in alanlar:
        k.beklenen_kod = _beklenen_kod(govde.beklenen_kod)
    if "acik" in alanlar and govde.acik is not None:
        k.acik = bool(govde.acik)
    await db.commit()
    await db.refresh(k)
    return _kontrol_sozlugu(k)


@yonetici_router.delete("/uptime/{kontrol_id}")
async def kontrol_sil(kontrol_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Kontrolü siler; ölçüm ve kesinti geçmişi kalıyor (durum sayfası geçmişi bozulmasın)."""
    _yonetici_iste(request)
    k = await _kontrol_bul(db, kontrol_id)
    await db.delete(k)
    await db.commit()
    return {"silindi": kontrol_id}


@yonetici_router.post("/{site_id}/durum-sayfasi")
async def yonetici_durum_sayfasi(
    site_id: int, request: Request, govde: DurumSayfasiGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    _yonetici_iste(request)
    site = await _site_bul(db, site_id)
    iz = await _durum_sayfasi_ayarla(db, site, govde)
    return {"durum_sayfasi_acik": bool(iz.durum_sayfasi_acik), "durum_index": bool(iz.durum_index),
            "durum_slug": iz.durum_slug, "durum_adresi": _durum_adresi(iz)}


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
@musteri_router.get("")
async def kendi_kartlarim(request: Request, db: AsyncSession = _Depends(get_db)):
    """Müşterinin kendi siteleri — e-posta JETONDAN, sorgudan değil."""
    eposta = _musteri_iste(request)
    siteler = list(
        (
            await db.execute(
                select(Client_sites).where(Client_sites.client_email == eposta).order_by(Client_sites.id.desc()).limit(200)
            )
        ).scalars().all()
    )
    return await _kartlar(db, siteler, yonetici=False)


@musteri_router.post("/{site_id}/durum-sayfasi")
async def musteri_durum_sayfasi(
    site_id: int, request: Request, govde: DurumSayfasiGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    """Müşteri kendi sitesinin durum sayfasını açıp kapatıyor (uptime modülü gerekli)."""
    eposta = _musteri_iste(request)
    _, yonetici = _yonetici_mi(request)
    site = await _site_bul(db, site_id)
    if not yonetici and (site.client_email or "").strip().lower() != eposta:
        raise _hata(403, "site_sizin_degil")
    if not yonetici and not await modul_acik_mi(db, eposta, "uptime"):
        raise HTTPException(status_code=403, detail={"kod": "modul_kapali", "modul": "uptime"})
    iz = await _durum_sayfasi_ayarla(db, site, govde)
    return {"durum_sayfasi_acik": bool(iz.durum_sayfasi_acik), "durum_index": bool(iz.durum_index),
            "durum_slug": iz.durum_slug, "durum_adresi": _durum_adresi(iz)}


# --------------------------------------------------------------------------
# Herkese açık durum sayfası
# --------------------------------------------------------------------------
@acik_router.get("/{slug}")
async def durum_sayfasi(slug: str, response: Response, db: AsyncSession = _Depends(get_db)):
    """Yalnız açılmış sayfa; yalnız bu sitenin toplulaştırılmış verisi.

    Dönmeyenler: müşteri e-postası, kontrol adresleri, durum kodları, hata
    kategorileri (kesinti sebebi), kontrol kimlikleri. Sahibinin uptime
    modülü kapalıysa sayfa da yok (404 — kapalı sayfa varlığını da
    belli etmiyor).
    """
    slug = (slug or "").strip().lower()[:80]
    if not slug:
        raise _hata(404, "sayfa_yok")
    iz = (await db.execute(select(SiteIzleme).where(SiteIzleme.durum_slug == slug))).scalar_one_or_none()
    if iz is None or not iz.durum_sayfasi_acik:
        raise _hata(404, "sayfa_yok")
    site = (await db.execute(select(Client_sites).where(Client_sites.id == iz.site_id))).scalar_one_or_none()
    if site is None or not await modul_acik_mi(db, (site.client_email or "").strip().lower(), "uptime"):
        raise _hata(404, "sayfa_yok")
    ozet = (await si.uptime_ozetleri(db, [site.id])).get(site.id)
    govde = si.acik_ozet(ozet) if ozet else None
    response.headers["Cache-Control"] = "public, max-age=60"
    if not iz.durum_index:
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {"ad": site.ad, "index": bool(iz.durum_index), **(govde or {})}


router = (yonetici_router, musteri_router, acik_router)
