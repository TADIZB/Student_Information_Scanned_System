"""Điểm vào FastAPI app — chỉ tạo app, mount router, CORS."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).resolve().parents[1] / os.getenv("ENV_FILE", ".env"))

from .routers import auth as auth_router
from .routers import history as history_router
from .routers import profile as profile_router
from .routers import scan as scan_router
from .routers import students as students_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


ROOT_PATH = os.getenv("ROOT_PATH", "")
_DEFAULT_ORIGINS = "http://localhost:3000,http://localhost:5173"
_origins_env = os.getenv("ALLOWED_ORIGINS", _DEFAULT_ORIGINS)
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]


app = FastAPI(
    title="TADIZB Scanner API",
    root_path=ROOT_PATH,
    docs_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router.router)
app.include_router(profile_router.router)
app.include_router(students_router.router)
app.include_router(scan_router.router)
app.include_router(history_router.router)


@app.get("/docs", include_in_schema=False)
def swagger_docs():
    openapi_url = f"{ROOT_PATH.rstrip('/')}/openapi.json" if ROOT_PATH else "/openapi.json"
    return get_swagger_ui_html(
        openapi_url=openapi_url,
        title="TADIZB Scanner API - Swagger UI",
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


_FRONTEND_DIST_PATH = Path(os.getenv("FRONTEND_DIST_PATH", "/home/ducta/fast.toolhub.app"))
if _FRONTEND_DIST_PATH.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=_FRONTEND_DIST_PATH, html=True),
        name="frontend",
    )
