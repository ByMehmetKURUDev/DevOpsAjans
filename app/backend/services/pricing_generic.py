"""Fiyatlandırma v5 tabloları için tek, paylaşılan servis katmanı.

Neden ayrı
----------
Mevcut kod tabanındaki her entity (`services/invoices.py` vb.) kendi
~250 satırlık üretilmiş servis dosyasına sahip — dokuz tablo, dokuz
neredeyse birebir aynı dosya. Fiyatlandırma v5 beş yeni tablo daha
ekliyor; aynı kopyala-yapıştırı beş kez tekrarlamak yerine, model
sınıfını parametre alan tek bir jenerik servis yazıldı. Uç noktaların
davranışı (get_list/get_by_id/create/update/delete, `$gte` gibi sorgu
operatörleri, sayfalama) `InvoicesService` ile birebir aynı; sadece
model sabit değil, kurucuya geliyor.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Type

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Boolean, Date, DateTime, Float, Integer, Numeric

logger = logging.getLogger(__name__)


class GenericEntityService:
    """`model_cls` için CRUD + filtreli/sayfalı liste."""

    def __init__(self, model_cls: Type, db: AsyncSession):
        self.model = model_cls
        self.db = db

    @staticmethod
    def _invalid_field_value(field_name: str, value: Any) -> ValueError:
        return ValueError("Invalid value for field " + field_name + ": " + repr(value))

    @classmethod
    def _coerce_field_value(cls, column: Any, value: Any, field_name: str) -> Any:
        try:
            column_type = column.property.columns[0].type
        except (AttributeError, IndexError):
            return value

        if value is None:
            return value

        if isinstance(column_type, DateTime) and isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                try:
                    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    raise cls._invalid_field_value(field_name, value)
            if not getattr(column_type, "timezone", False) and parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            return parsed

        if isinstance(column_type, Date):
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, date):
                return value
            if isinstance(value, str):
                try:
                    return date.fromisoformat(value)
                except ValueError:
                    raise cls._invalid_field_value(field_name, value)

        if isinstance(column_type, Boolean) and isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "t", "yes", "y", "on"}:
                return True
            if normalized in {"false", "0", "f", "no", "n", "off"}:
                return False
            raise cls._invalid_field_value(field_name, value)

        if isinstance(column_type, Integer) and isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                raise cls._invalid_field_value(field_name, value)

        if isinstance(column_type, (Float, Numeric)) and isinstance(value, str):
            try:
                return float(value) if isinstance(column_type, Float) else Decimal(value)
            except (ValueError, ArithmeticError):
                raise cls._invalid_field_value(field_name, value)

        return value

    @classmethod
    def _build_query_conditions(cls, column: Any, raw_value: Any, field_name: str) -> List[Any]:
        operator_map = {
            "$eq": lambda col, value: col == value,
            "$gte": lambda col, value: col >= value,
            "$lte": lambda col, value: col <= value,
            "$gt": lambda col, value: col > value,
            "$lt": lambda col, value: col < value,
        }
        if isinstance(raw_value, dict):
            invalid_operator_keys = [
                operator for operator in raw_value
                if not isinstance(operator, str) or not operator.startswith("$")
            ]
            if invalid_operator_keys:
                raise ValueError("Cannot mix query operators and literal object values for field " + field_name)
            conditions = []
            for operator, value in raw_value.items():
                normalized_operator = operator.lower()
                if normalized_operator not in operator_map:
                    raise ValueError("Unsupported query operator " + operator + " for field " + field_name)
                coerced_value = cls._coerce_field_value(column, value, field_name)
                conditions.append(operator_map[normalized_operator](column, coerced_value))
            return conditions

        coerced_value = cls._coerce_field_value(column, raw_value, field_name)
        return [column == coerced_value]

    async def create(self, data: Dict[str, Any]):
        try:
            obj = self.model(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created {self.model.__tablename__} with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating {self.model.__tablename__}: {str(e)}")
            raise

    async def get_by_id(self, obj_id: int):
        query = select(self.model).where(self.model.id == obj_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_list(
        self,
        skip: int = 0,
        limit: int = 20,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        conditions = []
        if query_dict:
            for field, value in query_dict.items():
                if hasattr(self.model, field):
                    column = getattr(self.model, field)
                    conditions.extend(self._build_query_conditions(column, value, field))

        stmt = select(self.model, func.count().over().label("total_count"))
        for condition in conditions:
            stmt = stmt.where(condition)

        if sort:
            field_name = sort[1:] if sort.startswith("-") else sort
            if hasattr(self.model, field_name):
                column = getattr(self.model, field_name)
                stmt = stmt.order_by(column.desc() if sort.startswith("-") else column)
        else:
            stmt = stmt.order_by(self.model.id.desc())

        result = await self.db.execute(stmt.offset(skip).limit(limit))
        rows = result.all()

        if rows:
            items = [row[0] for row in rows]
            total = rows[0][1]
        else:
            items = []
            count_stmt = select(func.count()).select_from(self.model)
            for condition in conditions:
                count_stmt = count_stmt.where(condition)
            total = (await self.db.execute(count_stmt)).scalar() or 0

        return {"items": items, "total": total, "skip": skip, "limit": limit}

    async def update(self, obj_id: int, update_data: Dict[str, Any]):
        obj = await self.get_by_id(obj_id)
        if not obj:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(obj, key):
                    setattr(obj, key, value)
            await self.db.commit()
            await self.db.refresh(obj)
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating {self.model.__tablename__} {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int) -> bool:
        obj = await self.get_by_id(obj_id)
        if not obj:
            return False
        try:
            await self.db.delete(obj)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting {self.model.__tablename__} {obj_id}: {str(e)}")
            raise
