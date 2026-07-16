from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Blog_posts(Base):
    __tablename__ = "blog_posts"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    title = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    excerpt = Column(String, nullable=True)
    content = Column(String, nullable=False)
    cover_image = Column(String, nullable=True)
    author = Column(String, nullable=True)
    category = Column(String, nullable=True)
    published = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)