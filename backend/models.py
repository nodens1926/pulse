from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey, Float, Index, LargeBinary, ARRAY, \
    PrimaryKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import REAL

Base = declarative_base()


class Site(Base):
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(Text, nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    date_added = Column(TIMESTAMP, server_default=func.now())
    last_crawled = Column(TIMESTAMP, nullable=True)

    pages = relationship("Page", back_populates="site", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Site(id={self.id}, url={self.url}, status={self.status})>"


class Page(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(Text, nullable=False, index=True)
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=True)

    # ML поля
    embedding = Column(LargeBinary, nullable=True)
    token_text = Column(Text, nullable=True)
    tf_idf = Column(ARRAY(REAL), nullable=True)

    relevantnost = Column(Float, nullable=True)

    crawled_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("ix_pages_site_url", "site_id", "url", unique=True),
    )

    site = relationship("Site", back_populates="pages")
    inverted_index_entries = relationship("InvertedIndex", back_populates="page", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Page(id={self.id}, url={self.url}, title={self.title})>"


class InvertedIndex(Base):
    __tablename__ = "inverted_index"

    word = Column(String(255), nullable=False)
    page_id = Column(Integer, ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    frequency = Column(Integer, nullable=False)
    weight = Column(Float, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("word", "page_id"),
        Index("ix_inverted_index_word", "word"),
        Index("ix_inverted_index_page_id", "page_id"),
    )

    page = relationship("Page", back_populates="inverted_index_entries")

    def __repr__(self):
        return f"<InvertedIndex(word={self.word}, page_id={self.page_id}, freq={self.frequency}, tf={self.weight})>"