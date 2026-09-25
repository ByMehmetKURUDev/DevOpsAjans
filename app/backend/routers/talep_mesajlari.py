"""Talep yazışması: bir talebin altındaki mesajlar.

Neden ayrı tablo
----------------
`support_tickets.reply` tek bir metin alanıydı. İkinci cevap
yazıldığında birincisi siliniyordu, yani müşteriyle aramızdaki
konuşma kayıt altında kalmıyordu. Burada her mesaj kendi satırı.

Kim yazdı
---------
`yazan` alanı gövdeden alınmıyor, oturumdan belirleniyor. Yönetici
isteği "ajans", diğer herkes "musteri" olarak kaydediliyor. Aksi
halde müşteri kendi mesajını ajans imzasıyla gönderebilir, sonra
"siz söylemiştiniz" diyebilirdi.

Kim görebilir
-------------
Bir talebin yazışmasını yalnızca yöneticiler ve talebin sahibi
(e-postası eşleşen kullanıcı) görebiliyor. Talep numarası sıralı
olduğu için, kontrol olmasaydı numarayı arttırarak başkalarının
yazışması okunabilirdi.
"""

import logging
from datetime import datetime
from typing import List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from models.support_tickets import Support_tickets
from models.ticket_replies import Ticket_replies
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/talep", tags=["talep"])

# Müşteri panelindeki hizmet düğmeleri bu anahtarları gönderiyor.
# Listeyi arka uç da biliyor: uydurma bir anahtar kaydedilmesin,
# rapor ve filtre sonradan tutarsız kalmasın.
HIZMETLER = {
    "genel",
    "seo",
    "youtube_pr",
    "sosyal_pr",
    "basin_pr",
    "google_ads",
    "sosyal_ads",
    "website",
    "sosyal_tasarim",
    "youtube_gelistirme",
    "youtube_otomasyon",
    "yeni_ozellik",
}


class MesajGirdisi(BaseModel):
    mesaj: str


class MesajSatiri(BaseModel):
    id: int
    ticket_id: int
    yazan: str
    yazan_ad: Optional[str] = None
    mesaj: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class YazismaYaniti(BaseModel):
    ticket_id: int
    subject: str
    hizmet: Optional[str] = None
    durum: Optional[str] = None
    mesajlar: List[MesajSatiri]


def _eposta(kullanici) -> str:
    deger = getattr(kullanici, "email", None) if kullanici else None
    return str(deger).strip().lower() if deger else ""


def _ad(kullanici) -> Optional[str]:
    if kullanici is None:
        return None
    for alan in ("full_name", "name"):
        deger = getattr(kullanici, alan, None)
        if deger:
            return str(deger)
    return None


async def _talebi_ac(db: AsyncSession, ticket_id: int) -> Support_tickets:
    sonuc = await db.execute(
        select(Support_tickets).where(Support_tickets.id == ticket_id)
    )
    talep = sonuc.scalar_one_or_none()
    if talep is None:
        raise HTTPException(status_code=404, detail="Talep bulunamadı")
    return talep


def _yetki(request: Request, talep: Support_tickets) -> str:
    """Erişimi doğrular ve mesajı kimin yazdığını döndürür."""
    kullanici, yonetici = _yonetici_mi(request)
    if yonetici:
        return "ajans"

    eposta = _eposta(kullanici)
    sahibi = (talep.client_email or "").strip().lower()
    if not eposta or not sahibi or eposta != sahibi:
        # 404 değil 403: talebin var olduğunu zaten biliyor olabilir.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu talebi görme yetkiniz yok",
        )
    return "musteri"


@router.get("/hizmetler")
async def hizmet_listesi():
    """Talep açılabilecek hizmet anahtarları.

    Liste tek yerde dursun diye buradan veriliyor; başlıklar ön yüzün
    dil dosyalarında. Ön yüz kendi listesini tutsaydı, yeni bir hizmet
    eklendiğinde iki yeri güncellemek gerekirdi ve biri unutulurdu.
    """
    return {"hizmetler": sorted(HIZMETLER)}


@router.get("/{ticket_id}/mesajlar", response_model=YazismaYaniti)
async def yazismayi_getir(
    ticket_id: int,
    request: Request,
    db: AsyncSession = _Depends(get_db),
):
    talep = await _talebi_ac(db, ticket_id)
    _yetki(request, talep)

    sonuc = await db.execute(
        select(Ticket_replies)
        .where(Ticket_replies.ticket_id == ticket_id)
        .order_by(Ticket_replies.id.asc())
    )
    satirlar = list(sonuc.scalars().all())

    # Talebin ilk mesajı `support_tickets.message` içinde duruyor ve
    # yazışma tablosunda karşılığı yok. Listeye başa ekliyoruz ki
    # müşteri ne yazdığını görsün. id=0: gerçek bir satır değil.
    acilis = MesajSatiri(
        id=0,
        ticket_id=ticket_id,
        yazan="musteri",
        yazan_ad=talep.client_name,
        mesaj=talep.message or "",
        created_at=talep.created_at,
    )

    mesajlar = [acilis] + [MesajSatiri.model_validate(s) for s in satirlar]

    # Eski taleplerde tek satırlık `reply` alanı dolu olabilir; o
    # cevap yazışma tablosunda yok. Kaybolmasın diye sona ekliyoruz.
    if talep.reply and not satirlar:
        mesajlar.append(
            MesajSatiri(
                id=-1,
                ticket_id=ticket_id,
                yazan="ajans",
                yazan_ad=None,
                mesaj=talep.reply,
                created_at=talep.updated_at,
            )
        )

    return YazismaYaniti(
        ticket_id=talep.id,
        subject=talep.subject,
        hizmet=talep.hizmet,
        durum=talep.status,
        mesajlar=mesajlar,
    )


@router.post("/{ticket_id}/mesaj", response_model=MesajSatiri)
async def mesaj_ekle(
    ticket_id: int,
    request: Request,
    govde: MesajGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    metin = (govde.mesaj or "").strip()
    if not metin:
        raise HTTPException(status_code=400, detail="Mesaj boş olamaz")
    if len(metin) > 8000:
        raise HTTPException(status_code=400, detail="Mesaj çok uzun")

    talep = await _talebi_ac(db, ticket_id)
    yazan = _yetki(request, talep)
    kullanici, _ = _yonetici_mi(request)

    kayit = Ticket_replies(
        ticket_id=talep.id,
        yazan=yazan,
        yazan_ad=_ad(kullanici),
        yazan_email=_eposta(kullanici) or None,
        mesaj=metin,
    )
    db.add(kayit)

    simdi = datetime.now()
    talep.son_mesaj_at = simdi
    # Durum, kimin yazdığına göre ilerliyor: müşteri yazınca top
    # bizde, biz yazınca müşteride. Kapanmış talep yeniden açılıyor.
    talep.status = "open" if yazan == "musteri" else "answered"

    await db.commit()
    await db.refresh(kayit)
    return kayit
