"""Ekip, talep atama ve müşteri raporları.

Yetki ayrımı
------------
Bu tablo yetki tablosu değil, ekip listesi. Yöneticiliği hâlâ kullanıcı
hesabının `role` alanı belirliyor. `staff` kaydı bir kişiye talep
atanabilmesini ve atandığı talebi görebilmesini sağlıyor.

Böyle ayırmanın nedeni: çalışana talep atayabilmek için ona yönetici
yetkisi vermek gerekseydi, fatura ve site ayarları da açılırdı.

İlk kurulum
-----------
Tablo boşsa iki satır yazılıyor: ajansın yöneticisi ve ilk çalışan.
Adresler ortam değişkeninden geliyor, kodda sabit değil; panelden de
değiştirilebiliyor. Boş bir ekip listesiyle açılan panel ilk gün
kullanılamaz olurdu.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from models.staff import Staff
from models.support_tickets import Support_tickets
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ekip", tags=["ekip"])

ROLLER = {"yonetici", "calisan"}


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class PersonelGirdisi(BaseModel):
    ad: str
    email: str
    rol: str = "calisan"
    hizmetler: Optional[str] = None
    aktif: bool = True


class PersonelSatiri(BaseModel):
    id: int
    ad: str
    email: str
    rol: Optional[str] = None
    hizmetler: Optional[str] = None
    aktif: Optional[bool] = None

    class Config:
        from_attributes = True


class AtamaGirdisi(BaseModel):
    ticket_id: int
    # Boş bırakılırsa atama kaldırılıyor.
    email: Optional[str] = None


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _yonetici_iste(request: Request) -> None:
    _, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem yönetici yetkisi istiyor",
        )


def _temiz_eposta(deger: Optional[str]) -> str:
    return (deger or "").strip().lower()


async def _ilk_kurulum(db: AsyncSession) -> None:
    """Ekip listesi boşsa yöneticiyi ve ilk çalışanı yazar."""
    sonuc = await db.execute(select(Staff).limit(1))
    if sonuc.scalars().first() is not None:
        return

    yonetici = _temiz_eposta(os.getenv("AJANS_YONETICI_EPOSTA") or "mehmetkuru.dev@gmail.com")
    calisan = _temiz_eposta(os.getenv("AJANS_CALISAN_EPOSTA") or "by@mehmetkuru.dev")

    db.add(Staff(ad="Mehmet KURU", email=yonetici, rol="yonetici", aktif=True))
    if calisan and calisan != yonetici:
        db.add(Staff(ad="Ajans ekibi", email=calisan, rol="calisan", aktif=True))
    await db.commit()
    logger.info("Ekip listesi ilk kez dolduruldu")


async def atanabilir_mi(db: AsyncSession, eposta: str) -> bool:
    """Bu adres ekipte ve aktif mi?"""
    eposta = _temiz_eposta(eposta)
    if not eposta:
        return False
    sonuc = await db.execute(select(Staff).where(Staff.email == eposta))
    kisi = sonuc.scalars().first()
    return bool(kisi and kisi.aktif is not False)


# --------------------------------------------------------------------------
# Ekip uçları
# --------------------------------------------------------------------------
@router.get("", response_model=List[PersonelSatiri])
async def ekip_listesi(request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    await _ilk_kurulum(db)
    sonuc = await db.execute(select(Staff).order_by(Staff.id.asc()))
    return list(sonuc.scalars().all())


@router.post("", response_model=PersonelSatiri)
async def personel_ekle(
    request: Request,
    govde: PersonelGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)

    ad = (govde.ad or "").strip()
    eposta = _temiz_eposta(govde.email)
    rol = (govde.rol or "calisan").strip().lower()
    if not ad or "@" not in eposta:
        raise HTTPException(status_code=400, detail="Ad ve geçerli e-posta gerekli")
    if rol not in ROLLER:
        raise HTTPException(status_code=400, detail="Rol yonetici ya da calisan olmalı")

    mevcut = await db.execute(select(Staff).where(Staff.email == eposta))
    if mevcut.scalars().first() is not None:
        raise HTTPException(status_code=409, detail="Bu e-posta ekipte zaten var")

    kayit = Staff(
        ad=ad,
        email=eposta,
        rol=rol,
        hizmetler=(govde.hizmetler or "").strip() or None,
        aktif=bool(govde.aktif),
    )
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)
    return kayit


@router.delete("/{personel_id}")
async def personel_sil(
    personel_id: int,
    request: Request,
    db: AsyncSession = _Depends(get_db),
):
    """Kişiyi listeden çıkarır.

    Ona atanmış talepler silinmiyor, ataması boşaltılıyor: iş kaybolmasın,
    kimsenin bakmadığı talep listede "atanmamış" görünsün.
    """
    _yonetici_iste(request)

    sonuc = await db.execute(select(Staff).where(Staff.id == personel_id))
    kisi = sonuc.scalars().first()
    if kisi is None:
        raise HTTPException(status_code=404, detail="Kişi bulunamadı")

    talepler = await db.execute(
        select(Support_tickets).where(Support_tickets.atanan == kisi.email)
    )
    bosaltilan = 0
    for t in talepler.scalars().all():
        t.atanan = None
        bosaltilan += 1

    await db.delete(kisi)
    await db.commit()
    return {"silindi": personel_id, "bosaltilan_talep": bosaltilan}


# --------------------------------------------------------------------------
# Atama
# --------------------------------------------------------------------------
@router.post("/ata")
async def talep_ata(
    request: Request,
    govde: AtamaGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)

    sonuc = await db.execute(
        select(Support_tickets).where(Support_tickets.id == govde.ticket_id)
    )
    talep = sonuc.scalar_one_or_none()
    if talep is None:
        raise HTTPException(status_code=404, detail="Talep bulunamadı")

    eposta = _temiz_eposta(govde.email)
    if eposta and not await atanabilir_mi(db, eposta):
        # Ekipte olmayan bir adrese atamak, o talebi kimsenin görmediği
        # bir yere göndermek demek.
        raise HTTPException(status_code=400, detail="Bu adres ekip listesinde değil")

    talep.atanan = eposta or None
    await db.commit()
    return {"ticket_id": talep.id, "atanan": talep.atanan}


# --------------------------------------------------------------------------
# Müşteri raporları
# --------------------------------------------------------------------------
@router.get("/musteri-raporlari")
async def musteri_raporlari(request: Request, db: AsyncSession = _Depends(get_db)):
    """Müşteri başına talep özeti.

    Tek sorguyla taleplerin tamamını çekip burada grupluyoruz: müşteri
    sayısı üç haneye çıkana kadar bu, müşteri başına sorgu atmaktan
    hızlı ve veritabanına yük bindirmiyor.
    """
    _yonetici_iste(request)

    sonuc = await db.execute(select(Support_tickets).order_by(Support_tickets.id.desc()))
    talepler = list(sonuc.scalars().all())

    musteriler: Dict[str, Dict[str, Any]] = {}
    for t in talepler:
        anahtar = (t.client_email or "—").strip().lower()
        kayit = musteriler.setdefault(
            anahtar,
            {
                "client_email": t.client_email or "—",
                "client_name": t.client_name,
                "toplam": 0,
                "acik": 0,
                "cevaplanan": 0,
                "kapali": 0,
                "hizmetler": {},
                "son_hareket": None,
            },
        )
        kayit["toplam"] += 1
        durum = (t.status or "open").lower()
        if durum == "closed":
            kayit["kapali"] += 1
        elif durum == "answered":
            kayit["cevaplanan"] += 1
        else:
            kayit["acik"] += 1

        hizmet = t.hizmet or "genel"
        kayit["hizmetler"][hizmet] = kayit["hizmetler"].get(hizmet, 0) + 1

        hareket = t.son_mesaj_at or t.created_at
        if hareket is not None:
            onceki = kayit["son_hareket"]
            if onceki is None or hareket > onceki:
                kayit["son_hareket"] = hareket
        if not kayit["client_name"] and t.client_name:
            kayit["client_name"] = t.client_name

    satirlar = sorted(
        musteriler.values(),
        key=lambda k: (k["acik"], k["toplam"]),
        reverse=True,
    )
    return {
        "musteriler": satirlar,
        "ozet": {
            "musteri_sayisi": len(satirlar),
            "toplam_talep": len(talepler),
            "acik_talep": sum(k["acik"] for k in satirlar),
        },
    }
