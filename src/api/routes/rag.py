"""
API routes для RAG (Retrieval Augmented Generation)
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import get_session
from src.database.repository import EmbeddingRepository
from src.services.embedding_service import EmbeddingService
from src.services.rag_service import RAGService

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response models

class AskRequest(BaseModel):
    question: str
    client_id: UUID | None = None
    num_chunks: int = 5


class SourceInfo(BaseModel):
    meeting_title: str
    meeting_date: str | None
    similarity: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceInfo]


class IndexRequest(BaseModel):
    meeting_ids: list[UUID] | None = None


class IndexResponse(BaseModel):
    status: str
    message: str
    stats: dict | None = None


class StatsResponse(BaseModel):
    total_chunks: int
    indexed_meetings: int


# Endpoints

@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Задать вопрос по истории встреч.

    Использует RAG для поиска релевантных фрагментов транскриптов
    и генерации ответа с помощью Claude.
    """
    try:
        rag = RAGService(session)
        answer, sources = await rag.ask(
            question=request.question,
            client_id=request.client_id,
            num_chunks=request.num_chunks,
        )

        return AskResponse(
            answer=answer,
            sources=[
                SourceInfo(
                    meeting_title=s.meeting_title,
                    meeting_date=s.meeting_date,
                    similarity=round(s.similarity, 3),
                )
                for s in sources
            ]
        )
    except Exception as e:
        logger.error(f"Error in ask: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index", response_model=IndexResponse)
async def index_meetings(
    request: IndexRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Запустить индексацию встреч.

    Если meeting_ids не указаны, индексируются все встречи с транскриптами.
    Индексация выполняется в фоновом режиме.
    """
    embedding_service = EmbeddingService(session)

    if request.meeting_ids:
        # Индексация конкретных встреч
        total_chunks = 0
        for meeting_id in request.meeting_ids:
            try:
                chunks = await embedding_service.index_meeting(meeting_id)
                total_chunks += chunks
            except Exception as e:
                logger.error(f"Error indexing meeting {meeting_id}: {e}")

        return IndexResponse(
            status="completed",
            message=f"Indexed {len(request.meeting_ids)} meetings",
            stats={"total_chunks": total_chunks}
        )
    else:
        # Индексация всех встреч
        stats = await embedding_service.index_all_meetings()
        return IndexResponse(
            status="completed",
            message="Indexing completed",
            stats=stats
        )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    session: AsyncSession = Depends(get_session),
):
    """
    Получить статистику индекса.
    """
    repo = EmbeddingRepository(session)
    stats = await repo.stats()
    return StatsResponse(**stats)


@router.delete("/index/{meeting_id}")
async def delete_meeting_index(
    meeting_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """
    Удалить индекс конкретной встречи.
    """
    repo = EmbeddingRepository(session)
    deleted = await repo.delete_by_meeting(meeting_id)
    return {"deleted_chunks": deleted}


@router.post("/reindex/{meeting_id}")
async def reindex_meeting(
    meeting_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """
    Переиндексировать конкретную встречу.
    """
    embedding_service = EmbeddingService(session)
    chunks = await embedding_service.reindex_meeting(meeting_id)
    return {"chunks_created": chunks}
