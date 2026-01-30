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


# TODO: Подключить роуты
# from src.api.routes import meetings, summaries, clients, tasks, leads, webhooks
# app.include_router(meetings.router, prefix="/api/meetings", tags=["meetings"])
# app.include_router(summaries.router, prefix="/api/summaries", tags=["summaries"])
# app.include_router(clients.router, prefix="/api/clients", tags=["clients"])
# app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
# app.include_router(leads.router, prefix="/api/leads", tags=["leads"])
# app.include_router(webhooks.router, prefix="/api/webhook", tags=["webhooks"])
