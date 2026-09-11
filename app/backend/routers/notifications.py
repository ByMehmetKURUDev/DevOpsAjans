"""
Bildirim uçları.

Frontend SDK `client.entities.notifications` üzerinden konuştuğu için
adres düzeni diğer varlıklarla aynı: /api/v1/entities/notifications
"""

import logging
from datetime import datetime
from typing import List, Optional

from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from models.notifications import Notifications
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/notifications", tags=["notifications"])


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
