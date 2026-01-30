"""
Сервис создания и управления эмбеддингами
"""
import logging
from uuid import UUID

from langchain_openai import OpenAIEmbeddings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Embedding, Meeting
from src.services.chunking import chunk_transcript

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Сервис для создания и управления эмбеддингами транскриптов"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.embeddings_model = OpenAIEmbeddings(model="text-embedding-ada-002")

    async def index_meeting(self, meeting_id: UUID) -> int:
        """
        Создать эмбеддинги для одной встречи.

        Args:
            meeting_id: ID встречи

        Returns:
            Количество созданных чанков
        """
        # Получаем встречу
        meeting = await self.session.get(Meeting, meeting_id)
        if not meeting:
            logger.warning(f"Meeting {meeting_id} not found")
            return 0

        if not meeting.transcript:
            logger.warning(f"Meeting {meeting_id} has no transcript")
            return 0

        # Проверяем, не проиндексирована ли уже
        existing = await self.session.execute(
            select(Embedding.id).where(Embedding.meeting_id == meeting_id).limit(1)
        )
        if existing.scalar_one_or_none():
            logger.info(f"Meeting {meeting_id} already indexed, skipping")
            return 0

        # Разбиваем на чанки
        chunks = chunk_transcript(meeting.transcript)
        if not chunks:
            logger.warning(f"Meeting {meeting_id} produced no chunks")
            return 0

        # Создаём эмбеддинги (batch)
        vectors = self.embeddings_model.embed_documents(chunks)

        # Сохраняем в БД
        for i, (chunk_text, vector) in enumerate(zip(chunks, vectors)):
            embedding = Embedding(
                meeting_id=meeting_id,
                chunk_text=chunk_text,
                chunk_index=i,
                embedding=vector,
            )
            self.session.add(embedding)

        await self.session.commit()
        logger.info(f"Indexed meeting {meeting_id}: {len(chunks)} chunks")
        return len(chunks)

    async def index_all_meetings(
        self,
        batch_size: int = 10,
        skip_indexed: bool = True
    ) -> dict:
        """
        Индексация всех встреч с транскриптами.

        Args:
            batch_size: Размер батча для обработки
            skip_indexed: Пропускать уже проиндексированные

        Returns:
            Статистика индексации
        """
        stats = {
            "total": 0,
            "indexed": 0,
            "skipped": 0,
            "errors": 0,
            "total_chunks": 0,
        }

        # Получаем все встречи с транскриптами
        result = await self.session.execute(
            select(Meeting.id, Meeting.title)
            .where(Meeting.transcript.isnot(None))
            .where(Meeting.transcript != "")
        )
        meetings = result.fetchall()
        stats["total"] = len(meetings)

        # Получаем уже проиндексированные
        if skip_indexed:
            indexed_result = await self.session.execute(
                select(Embedding.meeting_id).distinct()
            )
            indexed_ids = {row[0] for row in indexed_result.fetchall()}
        else:
            indexed_ids = set()

        for i, (meeting_id, title) in enumerate(meetings, 1):
            if meeting_id in indexed_ids:
                stats["skipped"] += 1
                continue

            try:
                chunks_count = await self.index_meeting(meeting_id)
                if chunks_count > 0:
                    stats["indexed"] += 1
                    stats["total_chunks"] += chunks_count
                else:
                    stats["skipped"] += 1

                # Логируем прогресс каждые 50 встреч
                if i % 50 == 0:
                    logger.info(f"Progress: {i}/{stats['total']} meetings processed")

            except Exception as e:
                logger.error(f"Error indexing meeting {meeting_id}: {e}")
                stats["errors"] += 1
                await self.session.rollback()

        logger.info(
            f"Indexing complete: {stats['indexed']} indexed, "
            f"{stats['skipped']} skipped, {stats['errors']} errors, "
            f"{stats['total_chunks']} total chunks"
        )
        return stats

    async def reindex_meeting(self, meeting_id: UUID) -> int:
        """
        Переиндексировать встречу (удалить старые эмбеддинги и создать новые).
        """
        # Удаляем старые эмбеддинги
        from sqlalchemy import delete
        await self.session.execute(
            delete(Embedding).where(Embedding.meeting_id == meeting_id)
        )
        await self.session.commit()

        # Создаём новые
        return await self.index_meeting(meeting_id)
