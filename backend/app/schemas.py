from typing import List, Optional

from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SourceOut(BaseModel):
    url: str
    title: Optional[str] = None
    excerpt: Optional[str] = None


class VerifyRequest(BaseModel):
    query: str


class VerifyResponse(BaseModel):
    query: str
    trust_score: float
    verdict: str
    ai_summary: str
    sources: List[SourceOut]
    scraped_sources_used: int


class VerificationHistoryItem(BaseModel):
    id: int
    query_text: str
    trust_score: float
    verdict: str
    ai_summary: Optional[str]
    created_at: str

    class Config:
        from_attributes = True
