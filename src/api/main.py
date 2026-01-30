"""
FastAPI Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Consultant Copilot API",
    description="AI-копилот для бизнес-консультанта",
    version="0.1.0",
)

# CORS для Telegram Mini App
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check"""
    return {"status": "ok", "service": "consultant-copilot"}


@app.get("/health")
async def health():
    """Health check для мониторинга"""
    return {"status": "healthy"}


# Роуты
from src.api.routes import (
    meetings_router,
    summaries_router,
    clients_router,
    hypotheses_router,
    webhooks_router,
    rag_router,
)

app.include_router(meetings_router, prefix="/api/meetings", tags=["meetings"])
app.include_router(summaries_router, prefix="/api/summaries", tags=["summaries"])
app.include_router(clients_router, prefix="/api/clients", tags=["clients"])
app.include_router(hypotheses_router, prefix="/api/hypotheses", tags=["hypotheses"])
app.include_router(webhooks_router, prefix="/api/webhook", tags=["webhooks"])
app.include_router(rag_router, prefix="/api/rag", tags=["rag"])
