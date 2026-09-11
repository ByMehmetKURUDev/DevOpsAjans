"""
Proje zaman çizelgesi ve aşama yönetimi.

Yönetici bir projenin aşamasını buradan ilerletiyor; işlem üç şeyi birden
yapıyor: projenin güncel durumunu günceller, geçmişe bir satır yazar ve
müşteriye bildirim gönderir. Üçünün tek uçta olması, "aşama değişti ama
müşteriye haber gitmedi" durumunu imkânsız kılıyor.
"""

import logging
from datetime import datetime
from typing import List, Optional

from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from models.project_events import Project_events
from models.projects import Projects
from pydantic import BaseModel, Field
from services.notify import admin_recipients, dispatch, render
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/project_events", tags=["project_events"])

# Projenin geçtiği aşamalar. Sıra ilerlemeyi de veriyor.
STAGES = ["discovery", "design", "build", "review", "launch", "aftercare"]

STAGE_LABELS = {
    "discovery": "Keşif",
    "design": "Tasarım",
    "build": "Geliştirme",
    "review": "İnceleme",
    "launch": "Yayın",
    "aftercare": "Lansman sonrası",
}


class EventResponse(BaseModel):
    id: int
    project_id: int
    event_type: str
    title: str
    body: Optional[str] = None
    from_value: Optional[str] = None
    to_value: Optional[str] = None
    actor_name: Optional[str] = None
    actor_email: Optional[str] = None
    visible_to_client: Optional[str] = None
    attachment_url: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EventListResponse(BaseModel):
    items: List[EventResponse]
    total: int


class NoteRequest(BaseModel):
    project_id: int
    title: str = Field(..., min_length=1)
    body: Optional[str] = None
    attachment_url: Optional[str] = None
    actor_name: Optional[str] = None
    actor_email: Optional[str] = None
    # Müşteri panelinde görünsün mü? İç notlar için False.
    visible_to_client: bool = True
    # Müşteriye bildirim gidecek mi? İç notta anlamsız.
    notify_client: bool = True


class StageRequest(BaseModel):
    project_id: int
    stage: str
    status: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    note: Optional[str] = None
    actor_name: Optional[str] = None
    actor_email: Optional[str] = None


async def _proje(db: AsyncSession, project_id: int) -> Projects:
    sonuc = await db.execute(select(Projects).where(Projects.id == project_id))
    proje = sonuc.scalar_one_or_none()
    if not proje:
        raise HTTPException(status_code=404, detail="Proje bulunamadı")
    return proje


def _alicilar(proje: Projects) -> List[dict]:
    if not proje.client_email:
        return []
    return [{"email": proje.client_email, "role": "client", "phone": ""}]


@router.get("/stages")
async def list_stages():
    """Aşama listesi; panel açılır menüyü buradan dolduruyor."""
    return {"stages": [{"key": k, "label": STAGE_LABELS[k], "order": i} for i, k in enumerate(STAGES)]}


@router.get("", response_model=EventListResponse)
async def list_events(
    project_id: int = Query(...),
    client_view: bool = Query(False, description="True ise yalnızca müşteriye açık kayıtlar"),
    db: AsyncSession = Depends(get_db),
):
    """Bir projenin zaman çizelgesi, en yeniden eskiye."""
    kosullar = [Project_events.project_id == project_id]
    if client_view:
        kosullar.append(Project_events.visible_to_client == "1")

    toplam = await db.scalar(select(func.count()).select_from(Project_events).where(*kosullar))
    sonuc = await db.execute(
        select(Project_events)
        .where(*kosullar)
        .order_by(Project_events.created_at.desc(), Project_events.id.desc())
    )
    return EventListResponse(
        items=[EventResponse.model_validate(r) for r in sonuc.scalars().all()],
        total=int(toplam or 0),
    )


@router.post("/note", response_model=EventResponse, status_code=201)
async def add_note(payload: NoteRequest, db: AsyncSession = Depends(get_db)):
    """Projeye not ya da dosya ekler."""
    proje = await _proje(db, payload.project_id)

    kayit = Project_events(
        project_id=proje.id,
        event_type="file" if payload.attachment_url else "note",
        title=payload.title,
        body=payload.body,
        actor_name=payload.actor_name,
        actor_email=payload.actor_email,
        visible_to_client="1" if payload.visible_to_client else "0",
        attachment_url=payload.attachment_url,
        created_at=datetime.now(),
    )
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)

    if payload.visible_to_client and payload.notify_client:
        await dispatch(
            db,
            event_type="project_note",
            title=f"{proje.title}: {payload.title}",
            body=payload.body or "",
            recipients=_alicilar(proje),
            link="/client",
            ref_type="project",
            ref_id=proje.id,
        )

    return EventResponse.model_validate(kayit)


@router.post("/stage", response_model=EventResponse)
async def set_stage(payload: StageRequest, db: AsyncSession = Depends(get_db)):
    """
    Projeyi bir aşamaya taşır.

    İlerleme yüzdesi verilmediyse aşamanın sırasından hesaplanıyor;
    böylece yönetici her seferinde sayı girmek zorunda kalmıyor ama
    isterse elle de yazabiliyor.
    """
    if payload.stage not in STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Geçersiz aşama. Geçerli değerler: {', '.join(STAGES)}",
        )

    proje = await _proje(db, payload.project_id)
    onceki = proje.stage

    proje.stage = payload.stage
    if payload.status:
        proje.status = payload.status
    if payload.progress is not None:
        proje.progress = payload.progress
    else:
        proje.progress = round((STAGES.index(payload.stage) + 1) / len(STAGES) * 100)
    proje.updated_at = datetime.now()

    etiket = STAGE_LABELS[payload.stage]
    onceki_etiket = STAGE_LABELS.get(onceki or "", onceki or "—")

    kayit = Project_events(
        project_id=proje.id,
        event_type="stage_change",
        title=f"Aşama: {onceki_etiket} → {etiket}",
        body=payload.note,
        from_value=onceki,
        to_value=payload.stage,
        actor_name=payload.actor_name,
        actor_email=payload.actor_email,
        visible_to_client="1",
        created_at=datetime.now(),
    )
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)

    baslik, govde = await render(
        db,
        "project_stage",
        f"{proje.title}: {etiket} aşamasında",
        payload.note or f"Proje {onceki_etiket} aşamasından {etiket} aşamasına geçti.",
        {
            "proje": proje.title,
            "asama": etiket,
            "oncekiAsama": onceki_etiket,
            "not": payload.note or "",
            "musteri": proje.client_name or "",
        },
    )

    await dispatch(
        db,
        event_type="project_stage",
        title=baslik,
        body=govde,
        recipients=_alicilar(proje) + await admin_recipients(db),
        link="/client",
        ref_type="project",
        ref_id=proje.id,
    )

    return EventResponse.model_validate(kayit)


@router.delete("/{event_id}")
async def delete_event(event_id: int, db: AsyncSession = Depends(get_db)):
    sonuc = await db.execute(select(Project_events).where(Project_events.id == event_id))
    kayit = sonuc.scalar_one_or_none()
    if not kayit:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    await db.delete(kayit)
    await db.commit()
    return {"success": True}
