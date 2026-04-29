"""
database.py — SQLAlchemy engine, session factory, and Base class.
All models inherit from Base.

Supports both:
  - SQLite  (local dev): sqlite:///./tax_invoice.db
  - PostgreSQL (Supabase): postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tax_invoice.db")

_is_sqlite = DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    # SQLite: disable same-thread check for FastAPI's async/threaded handling
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    # PostgreSQL / Supabase: connection pool tuned for small VPS / free tier
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,   # detect & drop stale connections automatically
        pool_recycle=300,     # recycle connections every 5 min (avoids Supabase idle timeout)
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and guarantees it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
