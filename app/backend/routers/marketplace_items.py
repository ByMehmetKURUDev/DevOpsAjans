"""
Marketplace urunleri -- yonetim ucu.

Bu router entity_guard altinda: okuma icin oturum, yazma icin yonetici
yetkisi gerekiyor. Sitenin kendisi buradan okumuyor; ziyaretcilere acik
olan uc ayri bir dosyada (routers/marketplace_public.py) ve yalnizca
yayindaki urunleri donduruyor. Boyle ayirdim cunku taslak urunleri
"published=false" filtresine guvenerek herkese acik uctan servis etmek,
filtreyi atlayan bir sorguda taslaklari disariya sizdirir.

Kalip blog_posts ile ayni: SDK (client.entities.marketplace_items)
butun entity uclarini ayni bicimde cagiriyor.
"""

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
from services.marketplace_items import Marketplace_itemsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/marketplace_items", tags=["marketplace_items"], dependencies=[_Depends(entity_guard)])


# ---------- Pydantic Schemas ----------
class Marketplace_itemsData(BaseModel):
    """Entity data schema (for create/update)"""
    title: str
    slug: str
    category: str = None
    summary: str = None
    description: str = None
    features: str = None
    price: str = None
    currency: str = None
    price_note: str = None
    delivery_time: str = None
    image_url: str = None
    demo_url: str = None
    badge: str = None
    published: bool = None
    sort_order: int = None


class Marketplace_itemsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    title: Optional[str] = None
    slug: Optional[str] = None
    category: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    features: Optional[str] = None
    price: Optional[str] = None
    currency: Optional[str] = None
    price_note: Optional[str] = None
    delivery_time: Optional[str] = None
    image_url: Optional[str] = None
    demo_url: Optional[str] = None
    badge: Optional[str] = None
    published: Optional[bool] = None
    sort_order: Optional[int] = None


class Marketplace_itemsResponse(BaseModel):
    """Entity response schema"""
    id: int
    title: str
    slug: str
    category: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    features: Optional[str] = None
    price: Optional[str] = None
    currency: Optional[str] = None
    price_note: Optional[str] = None
    delivery_time: Optional[str] = None
    image_url: Optional[str] = None
    demo_url: Optional[str] = None
    badge: Optional[str] = None
    published: Optional[bool] = None
    sort_order: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Marketplace_itemsListResponse(BaseModel):
    """List response schema"""
    items: List[Marketplace_itemsResponse]
    total: int
    skip: int
    limit: int


class Marketplace_itemsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Marketplace_itemsData]


class Marketplace_itemsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Marketplace_itemsUpdateData


class Marketplace_itemsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Marketplace_itemsBatchUpdateItem]


class Marketplace_itemsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Marketplace_itemsListResponse)
async def query_marketplace_itemss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query marketplace_itemss with filtering, sorting, and pagination"""
    logger.debug(f"Querying marketplace_itemss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Marketplace_itemsService(db)
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
        logger.debug(f"Found {result['total']} marketplace_itemss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid marketplace_items query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying marketplace_itemss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Marketplace_itemsListResponse)
async def query_marketplace_itemss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query marketplace_itemss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying marketplace_itemss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Marketplace_itemsService(db)
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
        logger.debug(f"Found {result['total']} marketplace_itemss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid marketplace_items query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying marketplace_itemss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Marketplace_itemsResponse)
async def get_marketplace_items(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single marketplace_items by ID"""
    logger.debug(f"Fetching marketplace_items with id: {id}, fields={fields}")
    
    service = Marketplace_itemsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Marketplace_items with id {id} not found")
            raise HTTPException(status_code=404, detail="Marketplace_items not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching marketplace_items {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Marketplace_itemsResponse, status_code=201)
async def create_marketplace_items(
    data: Marketplace_itemsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new marketplace_items"""
    logger.debug(f"Creating new marketplace_items with data: {data}")
    
    service = Marketplace_itemsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create marketplace_items")
        
        logger.info(f"Marketplace_items created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating marketplace_items: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating marketplace_items: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Marketplace_itemsResponse], status_code=201)
async def create_marketplace_itemss_batch(
    request: Marketplace_itemsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple marketplace_itemss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} marketplace_itemss")
    
    service = Marketplace_itemsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} marketplace_itemss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Marketplace_itemsResponse])
async def update_marketplace_itemss_batch(
    request: Marketplace_itemsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple marketplace_itemss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} marketplace_itemss")
    
    service = Marketplace_itemsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} marketplace_itemss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Marketplace_itemsResponse)
async def update_marketplace_items(
    id: int,
    data: Marketplace_itemsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing marketplace_items"""
    logger.debug(f"Updating marketplace_items {id} with data: {data}")

    service = Marketplace_itemsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Marketplace_items with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Marketplace_items not found")
        
        logger.info(f"Marketplace_items {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating marketplace_items {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating marketplace_items {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_marketplace_itemss_batch(
    request: Marketplace_itemsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple marketplace_itemss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} marketplace_itemss")
    
    service = Marketplace_itemsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} marketplace_itemss successfully")
        return {"message": f"Successfully deleted {deleted_count} marketplace_itemss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_marketplace_items(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single marketplace_items by ID"""
    logger.debug(f"Deleting marketplace_items with id: {id}")
    
    service = Marketplace_itemsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Marketplace_items with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Marketplace_items not found")
        
        logger.info(f"Marketplace_items {id} deleted successfully")
        return {"message": "Marketplace_items deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting marketplace_items {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")