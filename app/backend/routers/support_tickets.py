import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.entity_guard import entity_guard
from fastapi import Depends as _Depends
from services.notify import admin_recipients, dispatch, render
from services.support_tickets import Support_ticketsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/support_tickets", tags=["support_tickets"], dependencies=[_Depends(entity_guard)])


# ---------- Pydantic Schemas ----------
class Support_ticketsData(BaseModel):
    """Entity data schema (for create/update)"""
    client_name: str = None
    client_email: str = None
    subject: str
    message: str
    reply: str = None
    status: str = None
    priority: str = None


class Support_ticketsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None
    reply: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None


class Support_ticketsResponse(BaseModel):
    """Entity response schema"""
    id: int
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    subject: str
    message: str
    reply: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Support_ticketsListResponse(BaseModel):
    """List response schema"""
    items: List[Support_ticketsResponse]
    total: int
    skip: int
    limit: int


class Support_ticketsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Support_ticketsData]


class Support_ticketsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Support_ticketsUpdateData


class Support_ticketsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Support_ticketsBatchUpdateItem]


class Support_ticketsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Support_ticketsListResponse)
async def query_support_ticketss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query support_ticketss with filtering, sorting, and pagination"""
    logger.debug(f"Querying support_ticketss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Support_ticketsService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")
        
        result = await service.get_list(
            skip=skip, 
            limit=limit,
            query_dict=query_dict,
            sort=sort,
        )
        logger.debug(f"Found {result['total']} support_ticketss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid support_tickets query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying support_ticketss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Support_ticketsListResponse)
async def query_support_ticketss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query support_ticketss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying support_ticketss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Support_ticketsService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")

        result = await service.get_list(
            skip=skip,
            limit=limit,
            query_dict=query_dict,
            sort=sort
        )
        logger.debug(f"Found {result['total']} support_ticketss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid support_tickets query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying support_ticketss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Support_ticketsResponse)
async def get_support_tickets(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single support_tickets by ID"""
    logger.debug(f"Fetching support_tickets with id: {id}, fields={fields}")
    
    service = Support_ticketsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Support_tickets with id {id} not found")
            raise HTTPException(status_code=404, detail="Support_tickets not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching support_tickets {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Support_ticketsResponse, status_code=201)
async def create_support_tickets(
    data: Support_ticketsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new support_tickets"""
    logger.debug(f"Creating new support_tickets with data: {data}")
    
    service = Support_ticketsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create support_tickets")
        
        logger.info(f"Support_tickets created successfully with id: {result.id}")

        try:
            baslik, govde = await render(
                db,
                "ticket",
                f"Yeni destek talebi: {data.subject}",
                (
                    f"Müşteri: {data.client_name or data.client_email or '—'}\n"
                    f"Öncelik: {data.priority or 'normal'}\n\n"
                    f"{data.message}"
                ),
                {
                    "musteri": data.client_name or data.client_email or "—",
                    "eposta": data.client_email or "—",
                    "konu": data.subject,
                    "oncelik": data.priority or "normal",
                    "mesaj": data.message,
                },
            )
            await dispatch(
                db,
                event_type="ticket",
                title=baslik,
                body=govde,
                recipients=await admin_recipients(db),
                link="/admin",
                ref_type="ticket",
                ref_id=result.id,
            )
        except Exception as bildirim_hatasi:
            logger.error("Destek bildirimi gönderilemedi: %s", bildirim_hatasi)

        return result
    except ValueError as e:
        logger.error(f"Validation error creating support_tickets: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating support_tickets: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Support_ticketsResponse], status_code=201)
async def create_support_ticketss_batch(
    request: Support_ticketsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple support_ticketss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} support_ticketss")
    
    service = Support_ticketsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} support_ticketss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Support_ticketsResponse])
async def update_support_ticketss_batch(
    request: Support_ticketsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple support_ticketss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} support_ticketss")
    
    service = Support_ticketsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} support_ticketss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Support_ticketsResponse)
async def update_support_tickets(
    id: int,
    data: Support_ticketsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing support_tickets"""
    logger.debug(f"Updating support_tickets {id} with data: {data}")

    service = Support_ticketsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Support_tickets with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Support_tickets not found")
        
        logger.info(f"Support_tickets {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating support_tickets {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating support_tickets {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_support_ticketss_batch(
    request: Support_ticketsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple support_ticketss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} support_ticketss")
    
    service = Support_ticketsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} support_ticketss successfully")
        return {"message": f"Successfully deleted {deleted_count} support_ticketss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_support_tickets(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single support_tickets by ID"""
    logger.debug(f"Deleting support_tickets with id: {id}")
    
    service = Support_ticketsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Support_tickets with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Support_tickets not found")
        
        logger.info(f"Support_tickets {id} deleted successfully")
        return {"message": "Support_tickets deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting support_tickets {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")