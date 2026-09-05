import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.analytics_snapshots import Analytics_snapshotsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/analytics_snapshots", tags=["analytics_snapshots"])


# ---------- Pydantic Schemas ----------
class Analytics_snapshotsData(BaseModel):
    """Entity data schema (for create/update)"""
    channel: str
    metric_key: str
    metric_label: str = None
    metric_value: float
    change_pct: float = None
    unit: str = None
    snapshot_date: str = None


class Analytics_snapshotsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    channel: Optional[str] = None
    metric_key: Optional[str] = None
    metric_label: Optional[str] = None
    metric_value: Optional[float] = None
    change_pct: Optional[float] = None
    unit: Optional[str] = None
    snapshot_date: Optional[str] = None


class Analytics_snapshotsResponse(BaseModel):
    """Entity response schema"""
    id: int
    channel: str
    metric_key: str
    metric_label: Optional[str] = None
    metric_value: float
    change_pct: Optional[float] = None
    unit: Optional[str] = None
    snapshot_date: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Analytics_snapshotsListResponse(BaseModel):
    """List response schema"""
    items: List[Analytics_snapshotsResponse]
    total: int
    skip: int
    limit: int


class Analytics_snapshotsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Analytics_snapshotsData]


class Analytics_snapshotsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Analytics_snapshotsUpdateData


class Analytics_snapshotsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Analytics_snapshotsBatchUpdateItem]


class Analytics_snapshotsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Analytics_snapshotsListResponse)
async def query_analytics_snapshotss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query analytics_snapshotss with filtering, sorting, and pagination"""
    logger.debug(f"Querying analytics_snapshotss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Analytics_snapshotsService(db)
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
        logger.debug(f"Found {result['total']} analytics_snapshotss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid analytics_snapshots query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying analytics_snapshotss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Analytics_snapshotsListResponse)
async def query_analytics_snapshotss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query analytics_snapshotss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying analytics_snapshotss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Analytics_snapshotsService(db)
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
        logger.debug(f"Found {result['total']} analytics_snapshotss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid analytics_snapshots query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying analytics_snapshotss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Analytics_snapshotsResponse)
async def get_analytics_snapshots(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single analytics_snapshots by ID"""
    logger.debug(f"Fetching analytics_snapshots with id: {id}, fields={fields}")
    
    service = Analytics_snapshotsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Analytics_snapshots with id {id} not found")
            raise HTTPException(status_code=404, detail="Analytics_snapshots not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching analytics_snapshots {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Analytics_snapshotsResponse, status_code=201)
async def create_analytics_snapshots(
    data: Analytics_snapshotsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new analytics_snapshots"""
    logger.debug(f"Creating new analytics_snapshots with data: {data}")
    
    service = Analytics_snapshotsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create analytics_snapshots")
        
        logger.info(f"Analytics_snapshots created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating analytics_snapshots: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating analytics_snapshots: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Analytics_snapshotsResponse], status_code=201)
async def create_analytics_snapshotss_batch(
    request: Analytics_snapshotsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple analytics_snapshotss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} analytics_snapshotss")
    
    service = Analytics_snapshotsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} analytics_snapshotss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Analytics_snapshotsResponse])
async def update_analytics_snapshotss_batch(
    request: Analytics_snapshotsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple analytics_snapshotss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} analytics_snapshotss")
    
    service = Analytics_snapshotsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} analytics_snapshotss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Analytics_snapshotsResponse)
async def update_analytics_snapshots(
    id: int,
    data: Analytics_snapshotsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing analytics_snapshots"""
    logger.debug(f"Updating analytics_snapshots {id} with data: {data}")

    service = Analytics_snapshotsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Analytics_snapshots with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Analytics_snapshots not found")
        
        logger.info(f"Analytics_snapshots {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating analytics_snapshots {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating analytics_snapshots {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_analytics_snapshotss_batch(
    request: Analytics_snapshotsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple analytics_snapshotss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} analytics_snapshotss")
    
    service = Analytics_snapshotsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} analytics_snapshotss successfully")
        return {"message": f"Successfully deleted {deleted_count} analytics_snapshotss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_analytics_snapshots(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single analytics_snapshots by ID"""
    logger.debug(f"Deleting analytics_snapshots with id: {id}")
    
    service = Analytics_snapshotsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Analytics_snapshots with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Analytics_snapshots not found")
        
        logger.info(f"Analytics_snapshots {id} deleted successfully")
        return {"message": "Analytics_snapshots deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting analytics_snapshots {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")