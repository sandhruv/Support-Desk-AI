"""FastAPI application entry point.

Run with:  python run.py api    (or: uvicorn api.main:app --reload)
Swagger UI: http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from api.routes import router
from llm.model_config import get_settings
from llm.sk_integration import build_semantic_kernel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Enterprise Customer Support Triage and Resolution Desk",
    description=(
        "CSE476 - Agentic AI and Intelligent Automation. Multi-agent customer "
        "support system: Semantic Kernel + Groq + Supabase pgvector (RAG), "
        "persistent memory and human-in-the-loop escalation."
    ),
    version="1.0.0",
)

# CORS: only local frontend origins by default (configurable).
_allowed = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:8501,http://127.0.0.1:8501,http://localhost:5173,"
    "http://127.0.0.1:5173,http://localhost:8000",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _allowed.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup_event() -> None:
    settings = get_settings()
    logger.info("Starting Customer Support AI (env=%s)", settings.app_env)
    logger.info("Groq configured: %s | model: %s", settings.groq_configured, settings.groq_model)
    logger.info("Database configured: %s", settings.database_configured)
    build_semantic_kernel()  # warm the Semantic Kernel service


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")
