"""
API Routes
"""
from src.api.routes.meetings import router as meetings_router
from src.api.routes.summaries import router as summaries_router
from src.api.routes.clients import router as clients_router
from src.api.routes.hypotheses import router as hypotheses_router
from src.api.routes.webhooks import router as webhooks_router

__all__ = [
    "meetings_router",
    "summaries_router",
    "clients_router",
    "hypotheses_router",
    "webhooks_router",
]
