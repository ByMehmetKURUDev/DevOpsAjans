from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String


class Analytics_snapshots(Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    channel = Column(String, nullable=False)
    metric_key = Column(String, nullable=False)
    metric_label = Column(String, nullable=True)
    metric_value = Column(Float, nullable=False)
    change_pct = Column(Float, nullable=True)
    unit = Column(String, nullable=True)
    snapshot_date = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)