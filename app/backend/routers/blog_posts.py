import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.blog_posts import Blog_postsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/blog_posts", tags=["blog_posts"])


# ---------- Pydantic Schemas ----------
class Blog_postsData(BaseModel):
    """Entity data schema (for create/update)"""
    title: str
    slug: str
    excerpt: str = None
    content: str
    cover_image: str = None
    author: str = None
    category: str = None
    published: bool = None


class Blog_postsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    title: Optional[str] = None
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    cover_image: Optional[str] = None
    author: Optional[str] = None
    category: Optional[str] = None
    published: Optional[bool] = None


class Blog_postsResponse(BaseModel):
    """Entity response schema"""
    id: int
    title: str
    slug: str
    excerpt: Optional[str] = None
    content: str
    cover_image: Optional[str] = None
    author: Optional[str] = None
    category: Optional[str] = None
    published: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Blog_postsListResponse(BaseModel):
    """List response schema"""
    items: List[Blog_postsResponse]
    total: int
    skip: int
    limit: int


class Blog_postsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Blog_postsData]


class Blog_postsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Blog_postsUpdateData


class Blog_postsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Blog_postsBatchUpdateItem]


class Blog_postsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Blog_postsListResponse)
async def query_blog_postss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query blog_postss with filtering, sorting, and pagination"""
    logger.debug(f"Querying blog_postss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Blog_postsService(db)
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
        logger.debug(f"Found {result['total']} blog_postss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid blog_posts query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying blog_postss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Blog_postsListResponse)
async def query_blog_postss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query blog_postss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying blog_postss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Blog_postsService(db)
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
        logger.debug(f"Found {result['total']} blog_postss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid blog_posts query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying blog_postss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Blog_postsResponse)
async def get_blog_posts(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single blog_posts by ID"""
    logger.debug(f"Fetching blog_posts with id: {id}, fields={fields}")
    
    service = Blog_postsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Blog_posts with id {id} not found")
            raise HTTPException(status_code=404, detail="Blog_posts not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching blog_posts {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Blog_postsResponse, status_code=201)
async def create_blog_posts(
    data: Blog_postsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new blog_posts"""
    logger.debug(f"Creating new blog_posts with data: {data}")
    
    service = Blog_postsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create blog_posts")
        
        logger.info(f"Blog_posts created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating blog_posts: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating blog_posts: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Blog_postsResponse], status_code=201)
async def create_blog_postss_batch(
    request: Blog_postsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple blog_postss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} blog_postss")
    
    service = Blog_postsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} blog_postss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Blog_postsResponse])
async def update_blog_postss_batch(
    request: Blog_postsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple blog_postss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} blog_postss")
    
    service = Blog_postsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} blog_postss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Blog_postsResponse)
async def update_blog_posts(
    id: int,
    data: Blog_postsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing blog_posts"""
    logger.debug(f"Updating blog_posts {id} with data: {data}")

    service = Blog_postsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Blog_posts with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Blog_posts not found")
        
        logger.info(f"Blog_posts {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating blog_posts {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating blog_posts {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_blog_postss_batch(
    request: Blog_postsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple blog_postss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} blog_postss")
    
    service = Blog_postsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} blog_postss successfully")
        return {"message": f"Successfully deleted {deleted_count} blog_postss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_blog_posts(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single blog_posts by ID"""
    logger.debug(f"Deleting blog_posts with id: {id}")
    
    service = Blog_postsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Blog_posts with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Blog_posts not found")
        
        logger.info(f"Blog_posts {id} deleted successfully")
        return {"message": "Blog_posts deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting blog_posts {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")