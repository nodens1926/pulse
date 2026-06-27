from pydantic import BaseModel, HttpUrl
from datetime import datetime
from typing import Optional, List

class SiteCreate(BaseModel):
    url: HttpUrl
    name: Optional[str] = None

class SiteResponse(BaseModel):
    id: int
    url: str
    name: Optional[str]
    status: str
    date_added: datetime
    
    class Config:
        from_attributes = True

class SearchRequest(BaseModel):
    query: str
    limit: int = 10

class SearchResult(BaseModel):
    page_id: int
    url: str
    title: Optional[str]
    score: float

class SearchResponse(BaseModel):
    results: List[SearchResult]
    total: int

class StatusResponse(BaseModel):
    site_id: int
    url: str
    status: str
    pages_indexed: int
