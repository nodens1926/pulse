from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, LargeBinary, func, PrimaryKeyConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY, REAL
from database import Base

class Site(Base):
    __tablename__ = 'sites'
    
    id = Column(Integer, primary_key=True)
    url = Column(Text, nullable=False)
    name = Column(String(255))
    status = Column(String(50), nullable=False, default='pending')
    date_added = Column(DateTime, default=func.now())
    last_crawled = Column(DateTime)
    
    pages = relationship("Page", back_populates="site", cascade="all, delete-orphan")

class Page(Base):
    __tablename__ = 'pages'
    
    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey('sites.id', ondelete='CASCADE'))
    url = Column(Text, nullable=False)
    title = Column(String(500))
    content = Column(Text)
    crawled_at = Column(DateTime, default=func.now())
    embedding = Column(LargeBinary)
    tf_idf = Column(ARRAY(REAL))
    token_text = Column(Text)
    relevantnost = Column(Float)
    
    site = relationship("Site", back_populates="pages")
    inverted_index_entries = relationship("InvertedIndex", back_populates="page", cascade="all, delete-orphan")

class InvertedIndex(Base):
    __tablename__ = 'inverted_index'
    
    word = Column(String(255), primary_key=True)
    page_id = Column(Integer, ForeignKey('pages.id', ondelete='CASCADE'), primary_key=True)
    frequency = Column(Integer, nullable=False)
    weight = Column(Float)
    
    page = relationship("Page", back_populates="inverted_index_entries")
