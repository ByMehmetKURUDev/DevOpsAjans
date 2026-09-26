"""Müşteri siteleri, bakım erişimi ve gömülü geri bildirim düğmesi.

Şifre saklamıyoruz
------------------
Müşterinin sitesine girmek için onun şifresi panelde tutulmuyor.
Bakım için ajansa ayrı bir hesap açılıyor; o hesapla yapılan her iş
`access_log` satırı oluyor. Müşteri panelden `bakim_izni`ni tek
düğmeyle kapattığında ajansın kayıt açma hakkı o an bitiyor.

Şifreyi tutsaydık müşterinin sitesinin anahtarı bizde dururdu ve
panel bir gün ele geçse onun sitesi de giderdi. Ayrı hesap artı
günlük hem geri alınabilir hem denetlenebilir.

Geri bildirim düğmesi
---------------------
Müşterinin sitesine `widget.js` gömülüyor; sayfanın kenarında ajans
logosu çıkıyor. Ziyaretçi ya da müşterinin kendisi "şurası şöyle
olsun" yazdığında bu, müşterinin hesabına bir destek talebi olarak
düşüyor ve siteye bakan ekip üyesine atanıyor.

Uç herkese açık olmak zorunda (müşterinin sitesinde oturum yok), bu
yüzden jetonla çalışıyor ve saatlik bir sayaçla sınırlanıyor.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from models.access_log import Access_log
from models.client_sites import Client_sites
from models.support_tickets import Support_tickets
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/musteri-sitesi", tags=["musteri-sitesi"])
musteri_router = APIRouter(prefix="/api/v1/sitelerim", tags=["musteri-sitesi"])
acik_router = APIRouter(prefix="/api/v1/geri-bildirim", tags=["geri-bildirim"])

PLATFORMLAR = {"wordpress", "custom", "shopify", "wix", "webflow", "diger"}
DURUMLAR = {"aktif", "beklemede", "bitti"}
ISLEMLER = {
    "giris",
    "guncelleme",
    "yedek",
    "eklenti",
    "duzeltme",
    "izin_acildi",
    "izin_kapandi",
}

# Bir sitenin geri bildirim düğmesinden saatte kabul edilen en çok
# mesaj. Uç herkese açık; sınır olmasaydı tek bir bot taleplerin
# arasını doldururdu.
SAATLIK_SINIR = 20
MESAJ_EN_COK = 4000


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class SiteGirdisi(BaseModel):
    client_email: str
    ad: str
    adres: Optional[str] = None
    platform: Optional[str] = None
    atanan: Optional[str] = None


class SiteGuncelleme(BaseModel):
    ad: Optional[str] = None
    adres: Optional[str] = None
    platform: Optional[str] = None
    durum: Optional[str] = None
    atanan: Optional[str] = None
    widget_acik: Optional[bool] = None


class SiteSatiri(BaseModel):
    id: int
    client_email: str
    ad: str
    adres: Optional[str] = None
    platform: Optional[str] = None
    durum: Optional[str] = None
    bakim_izni: Optional[bool] = None
    izin_at: Optional[datetime] = None
    izin_notu: Optional[str] = None
    widget_acik: Optional[bool] = None
    atanan: Optional[str] = None

    class Config:
        from_attributes = True


class IzinGirdisi(BaseModel):
    izin: bool
    not_: Optional[str] = None


class ErisimGirdisi(BaseModel):
    islem: str
    aciklama: Optional[str] = None


class GunlukSatiri(BaseModel):
    id: int
    site_id: Optional[int] = None
    site_ad: Optional[str] = None
    kim: str
    islem: str
    aciklama: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GeriBildirimGirdisi(BaseModel):
    eposta: Optional[str] = None
    ad: Optional[str] = None
    mesaj: str
    sayfa: Optional[str] = None


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _eposta(kullanici: Any) -> str:
    return (getattr(kullanici, "email", "") or "").strip().lower()


def _temiz(deger: Optional[str]) -> str:
    return (deger or "").strip()


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem yönetici yetkisi istiyor",
        )
    return _eposta(kullanici)


def _yeni_jeton() -> str:
    return secrets.token_urlsafe(24)


async def _site_bul(db: AsyncSession, site_id: int) -> Client_sites:
    sonuc = await db.execute(select(Client_sites).where(Client_sites.id == site_id))
    site = sonuc.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="Site bulunamadı")
    return site


async def _gunluge_yaz(
    db: AsyncSession,
    *,
    site: Client_sites,
    kim: str,
    islem: str,
    aciklama: Optional[str] = None,
) -> Access_log:
    satir = Access_log(
        site_id=site.id,
        site_ad=site.ad,
        client_email=site.client_email,
        kim=kim or "—",
        islem=islem,
        aciklama=(aciklama or None),
    )
    db.add(satir)
    return satir


# --------------------------------------------------------------------------
# Yönetici uçları
# --------------------------------------------------------------------------
@yonetici_router.get("", response_model=List[SiteSatiri])
async def site_listesi(request: Request, db: AsyncSession = _Depends(get_db)):
    """Bakımını üstlendiğimiz siteler.

    Yönetici hepsini görüyor. Ekip üyesi yalnızca kendine atanmış
    siteleri: çalışana bakmadığı müşterinin sitesini göstermenin
    gereği yok.
    """
    kullanici, yonetici = _yonetici_mi(request)
    eposta = _eposta(kullanici)
    if not eposta:
        raise HTTPException(status_code=403, detail="Oturum gerekli")

    sorgu = select(Client_sites).order_by(Client_sites.id.desc())
    if not yonetici:
        sorgu = sorgu.where(Client_sites.atanan == eposta)

    sonuc = await db.execute(sorgu.limit(500))
    return list(sonuc.scalars().all())


@yonetici_router.post("", response_model=SiteSatiri)
async def site_ekle(
    request: Request,
    govde: SiteGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)

    eposta = _temiz(govde.client_email).lower()
    ad = _temiz(govde.ad)
    if "@" not in eposta or not ad:
        raise HTTPException(status_code=400, detail="Müşteri e-postası ve site adı gerekli")

    platform = (_temiz(govde.platform) or "diger").lower()
    if platform not in PLATFORMLAR:
        platform = "diger"

    kayit = Client_sites(
        client_email=eposta,
        ad=ad,
        adres=_temiz(govde.adres) or None,
        platform=platform,
        durum="aktif",
        bakim_izni=False,
        widget_jetonu=_yeni_jeton(),
        widget_acik=True,
        atanan=_temiz(govde.atanan).lower() or None,
    )
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)
    return kayit


@yonetici_router.patch("/{site_id}", response_model=SiteSatiri)
async def site_guncelle(
    site_id: int,
    request: Request,
    govde: SiteGuncelleme = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    site = await _site_bul(db, site_id)

    if govde.ad is not None:
        yeni = _temiz(govde.ad)
        if not yeni:
            raise HTTPException(status_code=400, detail="Site adı boş bırakılamaz")
        site.ad = yeni
    if govde.adres is not None:
        site.adres = _temiz(govde.adres) or None
    if govde.platform is not None:
        p = _temiz(govde.platform).lower()
        site.platform = p if p in PLATFORMLAR else "diger"
    if govde.durum is not None:
        d = _temiz(govde.durum).lower()
        if d not in DURUMLAR:
            raise HTTPException(status_code=400, detail="Durum aktif, beklemede ya da bitti olmalı")
        site.durum = d
    if govde.atanan is not None:
        site.atanan = _temiz(govde.atanan).lower() or None
    if govde.widget_acik is not None:
        site.widget_acik = bool(govde.widget_acik)

    await db.commit()
    await db.refresh(site)
    return site


@yonetici_router.delete("/{site_id}")
async def site_sil(site_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Siteyi listeden çıkarır.

    Erişim günlüğü SİLİNMİYOR. Site kaydıyla birlikte gitseydi
    "siteme kim girdi" sorusunun cevabı da giderdi; denetim kaydı
    ancak silinmediği sürece denetim kaydıdır.
    """
    _yonetici_iste(request)
    site = await _site_bul(db, site_id)
    await db.delete(site)
    await db.commit()
    return {"silindi": site_id, "gunluk_korundu": True}


@yonetici_router.post("/{site_id}/jeton")
async def jeton_yenile(site_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Geri bildirim jetonunu yeniler; eski gömme kodu o an ölür.

    Yeni gömme kodunu da döndürüyor: jetonu yenileyen kişinin bir
    sonraki işi zaten müşterinin sitesindeki satırı değiştirmek.

    Jeton liste ucunda dönmüyor, yalnızca burada ve `/gomme`da.
    Her site satırında taşınsaydı, panelin herhangi bir ekranını
    gören herkes bütün müşterilerin düğme jetonunu da görürdü.
    """
    _yonetici_iste(request)
    site = await _site_bul(db, site_id)
    site.widget_jetonu = _yeni_jeton()
    await db.commit()
    await db.refresh(site)

    adres = _site_adresi()
    return {
        "id": site.id,
        "widget_jetonu": site.widget_jetonu,
        "jeton": site.widget_jetonu,
        "kod": (
            f'<script src="{adres}/widget.js" '
            f'data-jeton="{site.widget_jetonu}" defer></script>'
        ),
    }


@yonetici_router.get("/{site_id}/gomme")
async def gomme_kodu(site_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Müşterinin sitesine yapıştırılacak tek satır."""
    _yonetici_iste(request)
    site = await _site_bul(db, site_id)
    if not site.widget_jetonu:
        site.widget_jetonu = _yeni_jeton()
        await db.commit()
        await db.refresh(site)

    adres = _site_adresi()
    kod = (
        f'<script src="{adres}/widget.js" '
        f'data-jeton="{site.widget_jetonu}" defer></script>'
    )
    return {"kod": kod, "jeton": site.widget_jetonu, "acik": site.widget_acik is not False}


@yonetici_router.post("/{site_id}/erisim", response_model=GunlukSatiri)
async def erisim_kaydet(
    site_id: int,
    request: Request,
    govde: ErisimGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    """Siteye yapılan bir bakım işini günlüğe yazar.

    İzin kapalıyken kayıt açılamıyor. Amaç, izni kapatmanın gerçekten
    bir şeyi durdurması: panelde "izin kapalı" yazarken günlüğe iş
    düşüyor olsaydı anahtar sahte olurdu.
    """
    kullanici, yonetici = _yonetici_mi(request)
    kim = _eposta(kullanici)
    if not kim:
        raise HTTPException(status_code=403, detail="Oturum gerekli")

    site = await _site_bul(db, site_id)
    if not yonetici and (site.atanan or "") != kim:
        raise HTTPException(status_code=403, detail="Bu site size atanmamış")

    if site.bakim_izni is not True:
        raise HTTPException(
            status_code=409,
            detail="Müşteri bakım iznini kapatmış; kayıt açılamaz",
        )

    islem = _temiz(govde.islem).lower()
    if islem not in ISLEMLER:
        raise HTTPException(status_code=400, detail="Tanımsız işlem türü")

    satir = await _gunluge_yaz(
        db, site=site, kim=kim, islem=islem, aciklama=_temiz(govde.aciklama)
    )
    await db.commit()
    await db.refresh(satir)
    return satir


@yonetici_router.get("/{site_id}/gunluk", response_model=List[GunlukSatiri])
async def site_gunlugu(site_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    kullanici, yonetici = _yonetici_mi(request)
    kim = _eposta(kullanici)
    if not kim:
        raise HTTPException(status_code=403, detail="Oturum gerekli")

    site = await _site_bul(db, site_id)
    if not yonetici and (site.atanan or "") != kim:
        raise HTTPException(status_code=403, detail="Bu site size atanmamış")

    sonuc = await db.execute(
        select(Access_log)
        .where(Access_log.site_id == site_id)
        .order_by(Access_log.id.desc())
        .limit(300)
    )
    return list(sonuc.scalars().all())


# --------------------------------------------------------------------------
# Müşteri uçları
# --------------------------------------------------------------------------
@musteri_router.get("", response_model=List[SiteSatiri])
async def kendi_sitelerim(request: Request, db: AsyncSession = _Depends(get_db)):
    """Müşterinin kendi siteleri.

    Adres oturumdan alınıyor, sorgudan değil: yoksa müşteri
    başkasının adresini yazıp onun sitelerini görebilirdi.
    """
    kullanici, yonetici = _yonetici_mi(request)
    eposta = _eposta(kullanici)
    if not eposta:
        raise HTTPException(status_code=403, detail="Oturum gerekli")

    sorgu = select(Client_sites).order_by(Client_sites.id.desc())
    if not yonetici:
        sorgu = sorgu.where(Client_sites.client_email == eposta)

    sonuc = await db.execute(sorgu.limit(200))
    return list(sonuc.scalars().all())


@musteri_router.post("/{site_id}/izin", response_model=SiteSatiri)
async def bakim_izni_degistir(
    site_id: int,
    request: Request,
    govde: IzinGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    """Bakım iznini tek düğmeyle açar ya da kapatır.

    Açma ve kapatma da günlüğe yazılıyor: izin ne zaman verilmiş, ne
    zaman geri alınmış — sonradan tartışma çıkmasın.
    """
    kullanici, yonetici = _yonetici_mi(request)
    eposta = _eposta(kullanici)
    if not eposta:
        raise HTTPException(status_code=403, detail="Oturum gerekli")

    site = await _site_bul(db, site_id)
    if not yonetici and (site.client_email or "").lower() != eposta:
        raise HTTPException(status_code=403, detail="Bu site sizin değil")

    site.bakim_izni = bool(govde.izin)
    site.izin_at = datetime.now(timezone.utc)
    site.izin_notu = _temiz(govde.not_) or None

    await _gunluge_yaz(
        db,
        site=site,
        kim=eposta,
        islem="izin_acildi" if site.bakim_izni else "izin_kapandi",
        aciklama=site.izin_notu,
    )
    await db.commit()
    await db.refresh(site)
    return site


@musteri_router.get("/{site_id}/gunluk", response_model=List[GunlukSatiri])
async def kendi_site_gunlugum(
    site_id: int, request: Request, db: AsyncSession = _Depends(get_db)
):
    """Müşteri kendi sitesine yapılan her işi görüyor.

    Günlüğü müşteriye açmak bu düzenin şartı: erişimi gören taraf
    olmadan "denetlenebilir erişim" sadece bizim kendimize verdiğimiz
    bir söz olurdu.
    """
    kullanici, yonetici = _yonetici_mi(request)
    eposta = _eposta(kullanici)
    if not eposta:
        raise HTTPException(status_code=403, detail="Oturum gerekli")

    site = await _site_bul(db, site_id)
    if not yonetici and (site.client_email or "").lower() != eposta:
        raise HTTPException(status_code=403, detail="Bu site sizin değil")

    sonuc = await db.execute(
        select(Access_log)
        .where(Access_log.site_id == site_id)
        .order_by(Access_log.id.desc())
        .limit(300)
    )
    return list(sonuc.scalars().all())


# --------------------------------------------------------------------------
# Açık uçlar — müşterinin sitesine gömülen düğme
# --------------------------------------------------------------------------
def _site_adresi() -> str:
    """Kendi sitemizin adresi.

    Host başlığından türetmiyoruz: gömme kodu ve jeton, isteği kimin
    yaptığına göre değişmemeli.
    """
    import os

    return (os.getenv("SITE_ADRESI") or "https://mehmetkuru.dev").rstrip("/")


async def _jetonla_site(db: AsyncSession, jeton: str) -> Client_sites:
    jeton = _temiz(jeton)
    if not jeton:
        raise HTTPException(status_code=404, detail="Geçersiz bağlantı")
    sonuc = await db.execute(select(Client_sites).where(Client_sites.widget_jetonu == jeton))
    site = sonuc.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="Geçersiz bağlantı")
    if site.widget_acik is False:
        raise HTTPException(status_code=403, detail="Geri bildirim kapalı")
    return site


@acik_router.get("/{jeton}")
async def widget_bilgisi(jeton: str, db: AsyncSession = _Depends(get_db)):
    """Düğmenin kendini çizmesi için gereken en az bilgi.

    Müşterinin e-postası, adı, site adresi DÖNMÜYOR: bu uç herkese
    açık, jetonu eline geçiren biri müşteri listesi çıkaramasın.
    """
    site = await _jetonla_site(db, jeton)
    return {
        "ad": site.ad,
        "ajans": "By Mehmet KURU Dev",
        "logo": f"{_site_adresi()}/logo192.png",
        "adres": _site_adresi(),
    }


@acik_router.post("/{jeton}")
async def geri_bildirim_gonder(
    jeton: str,
    govde: GeriBildirimGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    """Sitedeki düğmeden gelen isteği destek talebine çevirir.

    Talep, sitenin sahibinin hesabına düşüyor — gövdeden gelen
    e-postaya değil. Yazan kişi müşterinin kendisi olmayabilir
    (ekibinden biri, hatta bir ziyaretçi); adresi yalnızca "kim
    yazdı" bilgisi olarak saklıyoruz, hesabı o belirlemiyor.
    """
    site = await _jetonla_site(db, jeton)

    mesaj = _temiz(govde.mesaj)
    if len(mesaj) < 3:
        raise HTTPException(status_code=400, detail="Lütfen ne istediğinizi yazın")
    if len(mesaj) > MESAJ_EN_COK:
        mesaj = mesaj[:MESAJ_EN_COK]

    esik = datetime.now(timezone.utc) - timedelta(hours=1)
    sayim = await db.execute(
        select(func.count(Support_tickets.id)).where(
            Support_tickets.client_email == site.client_email,
            Support_tickets.kaynak == "widget",
            Support_tickets.created_at >= esik,
        )
    )
    if (sayim.scalar() or 0) >= SAATLIK_SINIR:
        raise HTTPException(
            status_code=429,
            detail="Bu site için çok fazla istek geldi; biraz sonra tekrar deneyin",
        )

    yazan_eposta = _temiz(govde.eposta).lower()
    yazan_ad = _temiz(govde.ad) or (yazan_eposta.split("@")[0] if yazan_eposta else "Site ziyaretçisi")
    sahibi_mi = bool(yazan_eposta) and yazan_eposta == (site.client_email or "").lower()

    sayfa = _temiz(govde.sayfa)[:500]
    basliklar = [f"Site geri bildirimi — {site.ad}"]
    alt = []
    if sayfa:
        alt.append(f"Sayfa: {sayfa}")
    if yazan_eposta:
        alt.append(f"Yazan: {yazan_ad} <{yazan_eposta}>" + ("" if sahibi_mi else " (üyelik eşleşmedi)"))
    else:
        alt.append(f"Yazan: {yazan_ad} (üyelik bilgisi girilmedi)")

    govde_metni = mesaj + "\n\n---\n" + "\n".join(alt)

    simdi = datetime.now(timezone.utc)
    talep = Support_tickets(
        client_name=yazan_ad,
        client_email=site.client_email,
        subject=basliklar[0],
        message=govde_metni,
        status="open",
        priority="normal",
        hizmet="website",
        kaynak="widget",
        atanan=site.atanan or None,
        son_mesaj_at=simdi,
    )
    db.add(talep)
    await db.commit()
    await db.refresh(talep)

    logger.info("Widget geri bildirimi: site=%s talep=%s", site.id, talep.id)
    # Jeton ya da müşteri adresi geri dönmüyor.
    return {"ok": True, "talep_no": talep.id, "uyelik_eslesti": sahibi_mi}


# `include_routers_from_package` demet de kabul ediyor.
router = (yonetici_router, musteri_router, acik_router)
