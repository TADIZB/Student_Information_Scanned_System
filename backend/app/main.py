"""Điểm vào FastAPI app — chỉ tạo app, mount router, CORS."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import auth as auth_router
from .routers import export as export_router
from .routers import history as history_router
from .routers import scan as scan_router
from .routers import students as students_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


_DEFAULT_ORIGINS = "http://localhost:3000,http://localhost:5173"
_origins_env = os.getenv("ALLOWED_ORIGINS", _DEFAULT_ORIGINS)
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]


app = FastAPI(title="TADIZB Scanner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router.router)
app.include_router(students_router.router)
app.include_router(scan_router.router)
app.include_router(history_router.router)
app.include_router(export_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
