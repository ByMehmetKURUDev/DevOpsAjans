from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Site_settings(Base):
    __tablename__ = "site_settings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    setting_key = Column(String, nullable=False)
    setting_value = Column(String, nullable=False)
    group_name = Column(String, nullable=True)
    label = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)