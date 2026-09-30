"""Fiyatlandırma v5 — entity_guard korumalı CRUD uçları.

`pricing_scales`, `pricing_profiles`, `pricing_services`, `pricing_addons`,
`ai_pm_tiers` için `/api/v1/entities/<tablo>` altında standart CRUD.
Yetki: `dependencies/entity_guard.py` — bu beş tablo artık `HERKESE_ACIK_OKUMA`
listesinde (okuma girişsiz açık; site ziyaretçisi fiyat/hizmet katalogunu
görebilmeli), yazma hâlâ admin'e kapalı. Fiyat hesaplama ve teklif akışı
kendi korumasız uçlarından geçiyor — bkz. routers/fiyatlandirma.py.

Altıncı router, `pricing_inquiries` ("Teklif Al" ile oluşan lead kaydı) —
bu tablo `HERKESE_ACIK_OKUMA`'da DEĞİL: okuma oturum ister, yazma admin
ister. Amaç ziyaretçiye açmak değil, admin panelinin gelen teklif
taleplerini görebilmesi; kayıt zaten `/api/v1/fiyat-teklif`'ten oluşuyor.

Altı tabloyu tek tek üretilmiş ~300 satırlık dosyalar yerine tek şablonla
kaydediyoruz (bkz. services/pricing_generic.py) — mantık ve URL şekli
`routers/invoices.py` ile birebir aynı, tekrar yok.

`main.py`'deki `include_routers_from_package`, bir modülün `router`
adlı değişkeninin APIRouter ya da APIRouter listesi olmasını kabul
ediyor; bu yüzden burada tek dosyadan altı router bir liste olarak
dışa veriliyor.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Type

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.entity_guard import entity_guard
from models.pricing import (
    Ai_pm_tiers,
    Pricing_addons,
    Pricing_inquiries,
    Pricing_profiles,
    Pricing_scales,
    Pricing_services,
)
from services.pricing_generic import GenericEntityService

logger = logging.getLogger(__name__)

# Bu modelin hangi alanları JSON metni olarak saklanıyor (ozellikler,
# karsilastirma) — response'ta list/dict'e çözülür, create/update'te
# tekrar metne çevrilir.
JSON_TEXT_FIELDS: Dict[str, List[str]] = {
    "pricing_scales": ["ozellikler", "karsilastirma"],
    "ai_pm_tiers": ["ozellikler"],
}


def _parse_json_fields(row_dict: Dict[str, Any], table: str) -> Dict[str, Any]:
    for field in JSON_TEXT_FIELDS.get(table, []):
        raw = row_dict.get(field)
        if isinstance(raw, str):
            try:
                row_dict[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                row_dict[field] = None
    return row_dict


def _dump_json_fields(data: Dict[str, Any], table: str) -> Dict[str, Any]:
    for field in JSON_TEXT_FIELDS.get(table, []):
        if field in data and data[field] is not None and not isinstance(data[field], str):
            data[field] = json.dumps(data[field], ensure_ascii=False)
    return data


def _row_to_dict(obj, table: str) -> Dict[str, Any]:
    row = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    return _parse_json_fields(row, table)


def _make_entity_router(
    *,
    table: str,
    model_cls: Type,
    create_schema: Type[BaseModel],
    update_schema: Type[BaseModel],
) -> APIRouter:
    router = APIRouter(
        prefix=f"/api/v1/entities/{table}",
        tags=[table],
        dependencies=[Depends(entity_guard)],
    )

    @router.get("")
    async def query_list(
        query: str = Query(None, description='JSON, ör. {"scale_kod":"ALFA"}'),
        sort: str = Query(None, description="Alan adı, azalan için başına '-'"),
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=2000),
        db: AsyncSession = Depends(get_db),
    ):
        service = GenericEntityService(model_cls, db)
        try:
            query_dict = json.loads(query) if query else None
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid query JSON format")
        try:
            result = await service.get_list(skip=skip, limit=limit, query_dict=query_dict, sort=sort)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {
            "items": [_row_to_dict(item, table) for item in result["items"]],
            "total": result["total"],
            "skip": result["skip"],
            "limit": result["limit"],
        }

    @router.get("/all")
    async def query_list_all(
        query: str = Query(None),
        sort: str = Query(None),
        skip: int = Query(0, ge=0),
        limit: int = Query(2000, ge=1, le=2000),
        db: AsyncSession = Depends(get_db),
    ):
        return await query_list(query=query, sort=sort, skip=skip, limit=limit, db=db)

    @router.get("/{id}")
    async def get_one(id: int, db: AsyncSession = Depends(get_db)):
        service = GenericEntityService(model_cls, db)
        obj = await service.get_by_id(id)
        if not obj:
            raise HTTPException(status_code=404, detail=f"{table} not found")
        return _row_to_dict(obj, table)

    @router.post("", status_code=201)
    async def create_one(data: create_schema, db: AsyncSession = Depends(get_db)):
        service = GenericEntityService(model_cls, db)
        payload = _dump_json_fields(data.model_dump(), table)
        try:
            obj = await service.create(payload)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return _row_to_dict(obj, table)

    @router.put("/{id}")
    async def update_one(id: int, data: update_schema, db: AsyncSession = Depends(get_db)):
        service = GenericEntityService(model_cls, db)
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        update_dict = _dump_json_fields(update_dict, table)
        obj = await service.update(id, update_dict)
        if not obj:
            raise HTTPException(status_code=404, detail=f"{table} not found")
        return _row_to_dict(obj, table)

    @router.delete("/{id}")
    async def delete_one(id: int, db: AsyncSession = Depends(get_db)):
        service = GenericEntityService(model_cls, db)
        success = await service.delete(id)
        if not success:
            raise HTTPException(status_code=404, detail=f"{table} not found")
        return {"message": f"{table} deleted successfully", "id": id}

    return router


# ---------- Şemalar (create/update) ----------
class PricingScalesData(BaseModel):
    kod: str
    sira: int
    ad: str
    alt_baslik: str
    calisan_araligi: str
    aciklama: str
    baz_aylik_fiyat_usd: float
    ozellikler: Optional[List[str]] = None
    eklenti_limiti: Optional[str] = None
    revizyon_saat: Optional[str] = None
    populer: Optional[bool] = False
    karsilastirma: Optional[Dict[str, Any]] = None


class PricingScalesUpdateData(BaseModel):
    kod: Optional[str] = None
    sira: Optional[int] = None
    ad: Optional[str] = None
    alt_baslik: Optional[str] = None
    calisan_araligi: Optional[str] = None
    aciklama: Optional[str] = None
    baz_aylik_fiyat_usd: Optional[float] = None
    ozellikler: Optional[List[str]] = None
    eklenti_limiti: Optional[str] = None
    revizyon_saat: Optional[str] = None
    populer: Optional[bool] = None
    karsilastirma: Optional[Dict[str, Any]] = None


class PricingProfilesData(BaseModel):
    kod: str
    ad: str
    carpan: float
    etiket: Optional[str] = None
    sira: int


class PricingProfilesUpdateData(BaseModel):
    kod: Optional[str] = None
    ad: Optional[str] = None
    carpan: Optional[float] = None
    etiket: Optional[str] = None
    sira: Optional[int] = None


class PricingServicesData(BaseModel):
    kategori: str
    ad: str
    baz_fiyat_usd: float
    tek_seferlik: Optional[bool] = False
    not_metni: Optional[str] = None
    yeni: Optional[bool] = False


class PricingServicesUpdateData(BaseModel):
    kategori: Optional[str] = None
    ad: Optional[str] = None
    baz_fiyat_usd: Optional[float] = None
    tek_seferlik: Optional[bool] = None
    not_metni: Optional[str] = None
    yeni: Optional[bool] = None


class PricingAddonsData(BaseModel):
    scale_kod: str
    ad: str
    baz_fiyat_usd: float
    birim: Optional[str] = "ay"
    sira: int


class PricingAddonsUpdateData(BaseModel):
    scale_kod: Optional[str] = None
    ad: Optional[str] = None
    baz_fiyat_usd: Optional[float] = None
    birim: Optional[str] = None
    sira: Optional[int] = None


class AiPmTiersData(BaseModel):
    kod: str
    ad: str
    fiyat_aylik_usd: float
    rozet: Optional[str] = None
    ozellikler: Optional[List[str]] = None
    sira: int


class AiPmTiersUpdateData(BaseModel):
    kod: Optional[str] = None
    ad: Optional[str] = None
    fiyat_aylik_usd: Optional[float] = None
    rozet: Optional[str] = None
    ozellikler: Optional[List[str]] = None
    sira: Optional[int] = None


# `pricing_inquiries` `HERKESE_ACIK_OKUMA`'da değil — bu tabloya CRUD router'ı
# eklemek onu ziyaretçiye açmıyor, tam tersi: admin panelinin "Teklif Al"
# taleplerini (lead) listeleyip yönetebilmesi için var. Yaratma zaten
# `/api/v1/fiyat-teklif`'ten geçiyor (bkz. routers/fiyatlandirma.py); bu
# router'ın POST'u panelden manuel kayıt eklemek için duruyor, kullanılması
# beklenmiyor.
class PricingInquiriesData(BaseModel):
    scale_kod: Optional[str] = None
    profile_kod: Optional[str] = None
    ai_pm_tier_kod: Optional[str] = None
    period: Optional[str] = None
    addon_ids: Optional[List[str]] = None
    hesaplanan_tutar: float
    musteri_eposta: str
    musteri_adi: Optional[str] = None
    kaynak: Optional[str] = "website"
    invoice_id: Optional[int] = None


class PricingInquiriesUpdateData(BaseModel):
    scale_kod: Optional[str] = None
    profile_kod: Optional[str] = None
    ai_pm_tier_kod: Optional[str] = None
    period: Optional[str] = None
    addon_ids: Optional[List[str]] = None
    hesaplanan_tutar: Optional[float] = None
    musteri_eposta: Optional[str] = None
    musteri_adi: Optional[str] = None
    kaynak: Optional[str] = None
    invoice_id: Optional[int] = None


JSON_TEXT_FIELDS["pricing_inquiries"] = ["addon_ids"]


# ---------- main.py'nin auto-discovery ile bulacağı router listesi ----------
router = [
    _make_entity_router(
        table="pricing_scales", model_cls=Pricing_scales,
        create_schema=PricingScalesData, update_schema=PricingScalesUpdateData,
    ),
    _make_entity_router(
        table="pricing_profiles", model_cls=Pricing_profiles,
        create_schema=PricingProfilesData, update_schema=PricingProfilesUpdateData,
    ),
    _make_entity_router(
        table="pricing_services", model_cls=Pricing_services,
        create_schema=PricingServicesData, update_schema=PricingServicesUpdateData,
    ),
    _make_entity_router(
        table="pricing_addons", model_cls=Pricing_addons,
        create_schema=PricingAddonsData, update_schema=PricingAddonsUpdateData,
    ),
    _make_entity_router(
        table="ai_pm_tiers", model_cls=Ai_pm_tiers,
        create_schema=AiPmTiersData, update_schema=AiPmTiersUpdateData,
    ),
    _make_entity_router(
        table="pricing_inquiries", model_cls=Pricing_inquiries,
        create_schema=PricingInquiriesData, update_schema=PricingInquiriesUpdateData,
    ),
]
