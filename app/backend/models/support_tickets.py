from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Support_tickets(Base):
    __tablename__ = "support_tickets"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    client_name = Column(String, nullable=True)
    client_email = Column(String, nullable=True)
    subject = Column(String, nullable=False)
    message = Column(String, nullable=False)
    reply = Column(String, nullable=True)
    status = Column(String, nullable=True)
    priority = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)