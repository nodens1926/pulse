from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from config import DATABASE_URL

Base = declarative_base()
engine = create_engine(DATABASE_URL)

class Site(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, nullable=False)
    name = Column(String(255))
    status = Column(String(50), nullable=False, default="pending")
    date_added = Column(DateTime, default=func.now())
    last_crawled = Column(DateTime)

class Page(Base):
    __tablename__ = "pages"
    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, nullable=False)
    url = Column(String, nullable=False)
    title = Column(String(500))
    content = Column(Text)
    crawled_at = Column(DateTime, default=func.now())

class InvertedIndex(Base):
    __tablename__ = "inverted_index"
    word = Column(String(255), primary_key=True)
    page_id = Column(Integer, primary_key=True)
    frequency = Column(Integer, nullable=False)
    weight = Column(Float)