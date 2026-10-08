import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    verifications = relationship("Verification", back_populates="user")


class Verification(Base):
    """
    Stores only the final result + short source excerpts/citations.
    Full scraped article text is NEVER stored here (see app/cache.py) --
    only what already existed in the `sources` field before (short excerpt/citation).
    """

    __tablename__ = "verifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable = guest query
    query_text = Column(Text, nullable=False)
    trust_score = Column(Float, nullable=False)
    verdict = Column(String(32), nullable=False, default="Unverified")
    ai_summary = Column(Text, nullable=True)
    sources = Column(Text, nullable=True)  # JSON-encoded list of {url, title, excerpt}
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="verifications")
