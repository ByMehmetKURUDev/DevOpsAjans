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
from services.invoices import InvoicesService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/invoices", tags=["invoices"], dependencies=[_Depends(entity_guard)])


# ---------- Pydantic Schemas ----------
class InvoicesData(BaseModel):
    """Entity data schema (for create/update)"""
    invoice_no: str
    client_name: str = None
    client_email: str = None
    description: str = None
    amount: float
    currency: str = None
    status: str = None
    issue_date: str = None
    due_date: str = None


class InvoicesUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    invoice_no: Optional[str] = None
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None


class InvoicesResponse(BaseModel):
    """Entity response schema"""
    id: int
    invoice_no: str
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    description: Optional[str] = None
    amount: float
    currency: Optional[str] = None
    status: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InvoicesListResponse(BaseModel):
    """List response schema"""
    items: List[InvoicesResponse]
    total: int
    skip: int
    limit: int


class InvoicesBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[InvoicesData]


class InvoicesBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: InvoicesUpdateData


class InvoicesBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[InvoicesBatchUpdateItem]


class InvoicesBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=InvoicesListResponse)
async def query_invoicess(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query invoicess with filtering, sorting, and pagination"""
    logger.debug(f"Querying invoicess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = InvoicesService(db)
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
        logger.debug(f"Found {result['total']} invoicess")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid invoices query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying invoicess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=InvoicesListResponse)
async def query_invoicess_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query invoicess with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying invoicess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = InvoicesService(db)
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
        logger.debug(f"Found {result['total']} invoicess")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid invoices query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying invoicess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=InvoicesResponse)
async def get_invoices(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single invoices by ID"""
    logger.debug(f"Fetching invoices with id: {id}, fields={fields}")
    
    service = InvoicesService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Invoices with id {id} not found")
            raise HTTPException(status_code=404, detail="Invoices not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching invoices {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=InvoicesResponse, status_code=201)
async def create_invoices(
    data: InvoicesData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new invoices"""
    logger.debug(f"Creating new invoices with data: {data}")
    
    service = InvoicesService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create invoices")
        
        logger.info(f"Invoices created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating invoices: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating invoices: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[InvoicesResponse], status_code=201)
async def create_invoicess_batch(
    request: InvoicesBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple invoicess in a single request"""
    logger.debug(f"Batch creating {len(request.items)} invoicess")
    
    service = InvoicesService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} invoicess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[InvoicesResponse])
async def update_invoicess_batch(
    request: InvoicesBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple invoicess in a single request"""
    logger.debug(f"Batch updating {len(request.items)} invoicess")
    
    service = InvoicesService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} invoicess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=InvoicesResponse)
async def update_invoices(
    id: int,
    data: InvoicesUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing invoices"""
    logger.debug(f"Updating invoices {id} with data: {data}")

    service = InvoicesService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Invoices with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Invoices not found")
        
        logger.info(f"Invoices {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating invoices {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating invoices {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_invoicess_batch(
    request: InvoicesBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple invoicess by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} invoicess")
    
    service = InvoicesService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} invoicess successfully")
        return {"message": f"Successfully deleted {deleted_count} invoicess", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_invoices(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single invoices by ID"""
    logger.debug(f"Deleting invoices with id: {id}")
    
    service = InvoicesService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Invoices with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Invoices not found")
        
        logger.info(f"Invoices {id} deleted successfully")
        return {"message": "Invoices deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting invoices {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")