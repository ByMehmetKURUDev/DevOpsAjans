from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String


class Invoices(Base):
    __tablename__ = "invoices"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    invoice_no = Column(String, nullable=False)
    client_name = Column(String, nullable=True)
    client_email = Column(String, nullable=True)
    description = Column(String, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=True)
    status = Column(String, nullable=True)
    issue_date = Column(String, nullable=True)
    due_date = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)