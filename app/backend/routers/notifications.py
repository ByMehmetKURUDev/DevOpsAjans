"""
Bildirim uçları.

Frontend SDK `client.entities.notifications` üzerinden konuştuğu için
adres düzeni diğer varlıklarla aynı: /api/v1/entities/notifications
"""

import logging
from datetime import datetime
from typing import List, Optional

from core.database import get_db
from dependencies.entity_guard import entity_guard
from fastapi import Depends as _Depends
from fastapi import APIRouter, Depends, HTTPException, Query
from models.notifications import Notifications
from pydantic import BaseModel
from services.notify import send_test
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/notifications", tags=["notifications"], dependencies=[_Depends(entity_guard)])


class NotificationResponse(BaseModel):
    id: int
    recipient_email: str
    recipient_role: Optional[str] = None
    event_type: str
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    channel: str
    delivery_status: Optional[str] = None
    delivery_detail: Optional[str] = None
    ref_type: Optional[str] = None
    ref_id: Optional[int] = None
    read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
    unread: int
    skip: int
    limit: int


class TestRequest(BaseModel):
    """Panelden tek bir kanalı denemek için."""

    channel: str  # email | sms | whatsapp | inapp
    target: str  # e-posta adresi ya da telefon numarası


class DeliveryLogItem(BaseModel):
    id: int
    created_at: Optional[datetime] = None
    event_type: str
    title: str
    recipient_email: str
    channel: str
    delivery_status: Optional[str] = None
    delivery_detail: Optional[str] = None

    class Config:
        from_attributes = True


class DeliveryLogResponse(BaseModel):
    items: List[DeliveryLogItem]
    total: int
    # Kanal başına özet: hangi kanaldan kaç gönderim başarılı/başarısız/atlandı.
    summary: dict


class MarkReadRequest(BaseModel):
    """Boş bırakılırsa alıcının okunmamış her bildirimi işaretlenir."""

    ids: Optional[List[int]] = None


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    recipient_email: str = Query(..., description="Bildirimleri istenen kişinin e-postası"),
    channel: str = Query("inapp", description="inapp | email | sms | whatsapp | all"),
    unread_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    Bir kişinin bildirimleri, en yeniden eskiye.

    Varsayılan olarak yalnızca panel içi (`inapp`) kayıtlar dönüyor: çanda
    aynı olayın e-posta ve SMS kopyaları da görünmesin diye. Gönderim
    kayıtlarını görmek için `channel=all`.
    """
    eposta = recipient_email.strip().lower()
    if not eposta:
        raise HTTPException(status_code=400, detail="recipient_email boş olamaz")

    kosullar = [func.lower(Notifications.recipient_email) == eposta]
    if channel != "all":
        kosullar.append(Notifications.channel == channel)
    if unread_only:
        kosullar.append(Notifications.read_at.is_(None))

    toplam = await db.scalar(select(func.count()).select_from(Notifications).where(*kosullar))

    okunmamis = await db.scalar(
        select(func.count())
        .select_from(Notifications)
        .where(
            func.lower(Notifications.recipient_email) == eposta,
            Notifications.channel == "inapp",
            Notifications.read_at.is_(None),
        )
    )

    sonuc = await db.execute(
        select(Notifications)
        .where(*kosullar)
        .order_by(Notifications.created_at.desc(), Notifications.id.desc())
        .offset(skip)
        .limit(limit)
    )

    return NotificationListResponse(
        items=[NotificationResponse.model_validate(r) for r in sonuc.scalars().all()],
        total=int(toplam or 0),
        unread=int(okunmamis or 0),
        skip=skip,
        limit=limit,
    )


@router.post("/mark-read")
async def mark_read(
    payload: MarkReadRequest,
    recipient_email: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Okundu işaretler.

    `recipient_email` sorgu parametresinde ve WHERE'e giriyor: gövdeye
    başka birinin bildirim kimliği yazılarak okundu işaretlenemesin diye.
    """
    eposta = recipient_email.strip().lower()
    if not eposta:
        raise HTTPException(status_code=400, detail="recipient_email boş olamaz")

    kosullar = [
        func.lower(Notifications.recipient_email) == eposta,
        Notifications.read_at.is_(None),
    ]
    if payload.ids:
        kosullar.append(Notifications.id.in_(payload.ids))

    await db.execute(update(Notifications).where(*kosullar).values(read_at=datetime.now()))
    await db.commit()
    return {"success": True}


@router.get("/log", response_model=DeliveryLogResponse)
async def delivery_log(
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = Query(None, description="sent | failed | skipped"),
    db: AsyncSession = Depends(get_db),
):
    """
    Gönderim kayıtları.

    Panel içi (`inapp`) kayıtlar dışarıda: onlar hep başarılı ve listeyi
    doldurup asıl soruyu — dış kanallar çalışıyor mu — gizliyorlar.
    """
    kosullar = [Notifications.channel != "inapp"]
    if status:
        kosullar.append(Notifications.delivery_status == status)

    toplam = await db.scalar(select(func.count()).select_from(Notifications).where(*kosullar))

    sonuc = await db.execute(
        select(Notifications)
        .where(*kosullar)
        .order_by(Notifications.created_at.desc(), Notifications.id.desc())
        .limit(limit)
    )

    ozet_sonuc = await db.execute(
        select(
            Notifications.channel,
            Notifications.delivery_status,
            func.count().label("adet"),
        )
        .where(Notifications.channel != "inapp")
        .group_by(Notifications.channel, Notifications.delivery_status)
    )

    ozet: dict = {}
    for kanal, durum, adet in ozet_sonuc.all():
        ozet.setdefault(kanal, {})[durum or "bilinmiyor"] = int(adet)

    return DeliveryLogResponse(
        items=[DeliveryLogItem.model_validate(r) for r in sonuc.scalars().all()],
        total=int(toplam or 0),
        summary=ozet,
    )


@router.post("/test")
async def test_channel(payload: TestRequest, db: AsyncSession = Depends(get_db)):
    """
    Bir kanalı dener.

    Gerçek bir olay beklemeden kanalın çalışıp çalışmadığını gösterir;
    sonuç gönderim kayıtlarına da yazılır.
    """
    hedef = payload.target.strip()
    if not hedef:
        raise HTTPException(status_code=400, detail="Hedef adres ya da numara boş olamaz")
    if payload.channel not in {"email", "sms", "whatsapp", "inapp"}:
        raise HTTPException(status_code=400, detail="Geçersiz kanal")

    return await send_test(db, payload.channel, hedef)
