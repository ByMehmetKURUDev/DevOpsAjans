"""
Icerik takvimi -- yonetim ucu.

Yalnizca yoneticiye acik (entity_guard): burasi plan, siteye acilan bir
tarafi yok. Ziyaretcinin gorecegi bir icerik listesi olmadigi icin
marketplace'teki gibi halka acik bir ikiz uc de yazilmadi.
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
from services.content_posts import Content_postsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/content_posts", tags=["content_posts"], dependencies=[_Depends(entity_guard)])


# ---------- Pydantic Schemas ----------
class Content_postsData(BaseModel):
    """Entity data schema (for create/update)"""
    title: str
    channel: str = None
    body: str = None
    hashtags: str = None
    image_url: str = None
    link_url: str = None
    scheduled_at: datetime = None
    status: str = None
    campaign: str = None
    notes: str = None
    published_at: datetime = None


class Content_postsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    title: Optional[str] = None
    channel: Optional[str] = None
    body: Optional[str] = None
    hashtags: Optional[str] = None
    image_url: Optional[str] = None
    link_url: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    status: Optional[str] = None
    campaign: Optional[str] = None
    notes: Optional[str] = None
    published_at: Optional[datetime] = None


class Content_postsResponse(BaseModel):
    """Entity response schema"""
    id: int
    title: str
    channel: Optional[str] = None
    body: Optional[str] = None
    hashtags: Optional[str] = None
    image_url: Optional[str] = None
    link_url: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    status: Optional[str] = None
    campaign: Optional[str] = None
    notes: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Content_postsListResponse(BaseModel):
    """List response schema"""
    items: List[Content_postsResponse]
    total: int
    skip: int
    limit: int


class Content_postsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Content_postsData]


class Content_postsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Content_postsUpdateData


class Content_postsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Content_postsBatchUpdateItem]


class Content_postsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Content_postsListResponse)
async def query_content_postss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query content_postss with filtering, sorting, and pagination"""
    logger.debug(f"Querying content_postss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Content_postsService(db)
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
        logger.debug(f"Found {result['total']} content_postss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid content_posts query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying content_postss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Content_postsListResponse)
async def query_content_postss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query content_postss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying content_postss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Content_postsService(db)
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
        logger.debug(f"Found {result['total']} content_postss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid content_posts query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying content_postss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Content_postsResponse)
async def get_content_posts(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single content_posts by ID"""
    logger.debug(f"Fetching content_posts with id: {id}, fields={fields}")
    
    service = Content_postsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Content_posts with id {id} not found")
            raise HTTPException(status_code=404, detail="Content_posts not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching content_posts {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Content_postsResponse, status_code=201)
async def create_content_posts(
    data: Content_postsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new content_posts"""
    logger.debug(f"Creating new content_posts with data: {data}")
    
    service = Content_postsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create content_posts")
        
        logger.info(f"Content_posts created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating content_posts: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating content_posts: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Content_postsResponse], status_code=201)
async def create_content_postss_batch(
    request: Content_postsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple content_postss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} content_postss")
    
    service = Content_postsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} content_postss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Content_postsResponse])
async def update_content_postss_batch(
    request: Content_postsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple content_postss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} content_postss")
    
    service = Content_postsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} content_postss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Content_postsResponse)
async def update_content_posts(
    id: int,
    data: Content_postsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing content_posts"""
    logger.debug(f"Updating content_posts {id} with data: {data}")

    service = Content_postsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Content_posts with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Content_posts not found")
        
        logger.info(f"Content_posts {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating content_posts {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating content_posts {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_content_postss_batch(
    request: Content_postsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple content_postss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} content_postss")
    
    service = Content_postsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} content_postss successfully")
        return {"message": f"Successfully deleted {deleted_count} content_postss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_content_posts(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single content_posts by ID"""
    logger.debug(f"Deleting content_posts with id: {id}")
    
    service = Content_postsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Content_posts with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Content_posts not found")
        
        logger.info(f"Content_posts {id} deleted successfully")
        return {"message": "Content_posts deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting content_posts {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")