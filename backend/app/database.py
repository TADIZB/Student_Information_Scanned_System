from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Tải biến môi trường từ backend/.env
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Đọc DATABASE_URL từ biến môi trường (xem file .env)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:Anhduc2703@localhost:5432/QR",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI Dependency: cấp một DB session cho mỗi request rồi đóng lại."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
