"""
database.py — SQLAlchemy engine supporting SQLite (dev) and PostgreSQL/Supabase (prod).
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tax_invoice.db")
_is_sqlite = DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    # Supabase connection pooler settings (port 6543)
    # sslmode=require is mandatory for Supabase pooler
    connect_args = {
        "connect_timeout": 10,
        "sslmode": "require",
        "keepalives": 1,
        "keepalives_idle": 30,
    }
    engine = create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        pool_size=3,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=300,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
