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
from services.site_settings import Site_settingsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/site_settings", tags=["site_settings"], dependencies=[_Depends(entity_guard)])


# ---------- Pydantic Schemas ----------
class Site_settingsData(BaseModel):
    """Entity data schema (for create/update)"""
    setting_key: str
    setting_value: str
    group_name: str = None
    label: str = None


class Site_settingsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    setting_key: Optional[str] = None
    setting_value: Optional[str] = None
    group_name: Optional[str] = None
    label: Optional[str] = None


class Site_settingsResponse(BaseModel):
    """Entity response schema"""
    id: int
    setting_key: str
    setting_value: str
    group_name: Optional[str] = None
    label: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Site_settingsListResponse(BaseModel):
    """List response schema"""
    items: List[Site_settingsResponse]
    total: int
    skip: int
    limit: int


class Site_settingsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Site_settingsData]


class Site_settingsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Site_settingsUpdateData


class Site_settingsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Site_settingsBatchUpdateItem]


class Site_settingsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Site_settingsListResponse)
async def query_site_settingss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query site_settingss with filtering, sorting, and pagination"""
    logger.debug(f"Querying site_settingss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Site_settingsService(db)
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
        logger.debug(f"Found {result['total']} site_settingss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid site_settings query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying site_settingss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Site_settingsListResponse)
async def query_site_settingss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query site_settingss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying site_settingss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Site_settingsService(db)
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
        logger.debug(f"Found {result['total']} site_settingss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid site_settings query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying site_settingss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Site_settingsResponse)
async def get_site_settings(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single site_settings by ID"""
    logger.debug(f"Fetching site_settings with id: {id}, fields={fields}")
    
    service = Site_settingsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Site_settings with id {id} not found")
            raise HTTPException(status_code=404, detail="Site_settings not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching site_settings {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Site_settingsResponse, status_code=201)
async def create_site_settings(
    data: Site_settingsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new site_settings"""
    logger.debug(f"Creating new site_settings with data: {data}")
    
    service = Site_settingsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create site_settings")
        
        logger.info(f"Site_settings created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating site_settings: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating site_settings: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Site_settingsResponse], status_code=201)
async def create_site_settingss_batch(
    request: Site_settingsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple site_settingss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} site_settingss")
    
    service = Site_settingsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} site_settingss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Site_settingsResponse])
async def update_site_settingss_batch(
    request: Site_settingsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple site_settingss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} site_settingss")
    
    service = Site_settingsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} site_settingss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Site_settingsResponse)
async def update_site_settings(
    id: int,
    data: Site_settingsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing site_settings"""
    logger.debug(f"Updating site_settings {id} with data: {data}")

    service = Site_settingsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Site_settings with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Site_settings not found")
        
        logger.info(f"Site_settings {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating site_settings {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating site_settings {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_site_settingss_batch(
    request: Site_settingsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple site_settingss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} site_settingss")
    
    service = Site_settingsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} site_settingss successfully")
        return {"message": f"Successfully deleted {deleted_count} site_settingss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_site_settings(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single site_settings by ID"""
    logger.debug(f"Deleting site_settings with id: {id}")
    
    service = Site_settingsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Site_settings with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Site_settings not found")
        
        logger.info(f"Site_settings {id} deleted successfully")
        return {"message": "Site_settings deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting site_settings {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")