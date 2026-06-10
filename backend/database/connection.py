# database/connection.py
"""
SQLite database connection using SQLAlchemy.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

# Database file path
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./yly.db")

# Create engine (SQLite is single-threaded, so we disable check_same_thread)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False  # Set to True for SQL debugging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database sessions.
    Usage: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database tables.
    Call this on application startup.
    """
    from .models import Base
    Base.metadata.create_all(bind=engine)
    print("[DB] Database initialized successfully")
