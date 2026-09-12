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
from services.inquiries import InquiriesService
from services.notify import admin_recipients, dispatch, render

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/inquiries", tags=["inquiries"], dependencies=[_Depends(entity_guard)])


# ---------- Pydantic Schemas ----------
class InquiriesData(BaseModel):
    """Entity data schema (for create/update)"""
    name: str
    email: str
    phone: str = None
    subject: str = None
    message: str
    status: str = None


class InquiriesUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None
    status: Optional[str] = None


class InquiriesResponse(BaseModel):
    """Entity response schema"""
    id: int
    name: str
    email: str
    phone: Optional[str] = None
    subject: Optional[str] = None
    message: str
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InquiriesListResponse(BaseModel):
    """List response schema"""
    items: List[InquiriesResponse]
    total: int
    skip: int
    limit: int


class InquiriesBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[InquiriesData]


class InquiriesBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: InquiriesUpdateData


class InquiriesBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[InquiriesBatchUpdateItem]


class InquiriesBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=InquiriesListResponse)
async def query_inquiriess(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query inquiriess with filtering, sorting, and pagination"""
    logger.debug(f"Querying inquiriess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = InquiriesService(db)
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
        logger.debug(f"Found {result['total']} inquiriess")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid inquiries query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying inquiriess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=InquiriesListResponse)
async def query_inquiriess_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query inquiriess with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying inquiriess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = InquiriesService(db)
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
        logger.debug(f"Found {result['total']} inquiriess")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid inquiries query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying inquiriess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=InquiriesResponse)
async def get_inquiries(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single inquiries by ID"""
    logger.debug(f"Fetching inquiries with id: {id}, fields={fields}")
    
    service = InquiriesService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Inquiries with id {id} not found")
            raise HTTPException(status_code=404, detail="Inquiries not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching inquiries {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=InquiriesResponse, status_code=201)
async def create_inquiries(
    data: InquiriesData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new inquiries"""
    logger.debug(f"Creating new inquiries with data: {data}")
    
    service = InquiriesService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create inquiries")
        
        logger.info(f"Inquiries created successfully with id: {result.id}")

        # Yöneticiye haber ver. Bildirim gönderimi ziyaretçinin gördüğü
        # yanıtı etkilememeli: dispatch kendi hatalarını yutuyor, yine de
        # buradaki try bloğu son bir güvence.
        try:
            # Başlık ve gövde panelde düzenlenebilir; boşsa buradaki
            # varsayılan kullanılıyor.
            baslik, govde = await render(
                db,
                "inquiry",
                f"Yeni iletişim mesajı: {data.name}",
                (
                    f"Ad: {data.name}\n"
                    f"E-posta: {data.email}\n"
                    f"Telefon: {data.phone or '—'}\n"
                    f"Konu: {data.subject or '—'}\n\n"
                    f"{data.message}"
                ),
                {
                    "ad": data.name,
                    "eposta": data.email,
                    "telefon": data.phone or "—",
                    "konu": data.subject or "—",
                    "mesaj": data.message,
                },
            )
            await dispatch(
                db,
                event_type="inquiry",
                title=baslik,
                body=govde,
                recipients=await admin_recipients(db),
                link="/admin",
                ref_type="inquiry",
                ref_id=result.id,
            )
        except Exception as bildirim_hatasi:
            logger.error("İletişim bildirimi gönderilemedi: %s", bildirim_hatasi)

        return result
    except ValueError as e:
        logger.error(f"Validation error creating inquiries: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating inquiries: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[InquiriesResponse], status_code=201)
async def create_inquiriess_batch(
    request: InquiriesBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple inquiriess in a single request"""
    logger.debug(f"Batch creating {len(request.items)} inquiriess")
    
    service = InquiriesService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} inquiriess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[InquiriesResponse])
async def update_inquiriess_batch(
    request: InquiriesBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple inquiriess in a single request"""
    logger.debug(f"Batch updating {len(request.items)} inquiriess")
    
    service = InquiriesService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} inquiriess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=InquiriesResponse)
async def update_inquiries(
    id: int,
    data: InquiriesUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing inquiries"""
    logger.debug(f"Updating inquiries {id} with data: {data}")

    service = InquiriesService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Inquiries with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Inquiries not found")
        
        logger.info(f"Inquiries {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating inquiries {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating inquiries {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_inquiriess_batch(
    request: InquiriesBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple inquiriess by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} inquiriess")
    
    service = InquiriesService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} inquiriess successfully")
        return {"message": f"Successfully deleted {deleted_count} inquiriess", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_inquiries(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single inquiries by ID"""
    logger.debug(f"Deleting inquiries with id: {id}")
    
    service = InquiriesService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Inquiries with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Inquiries not found")
        
        logger.info(f"Inquiries {id} deleted successfully")
        return {"message": "Inquiries deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting inquiries {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")