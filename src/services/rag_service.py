"""
RAG сервис для Q&A по истории встреч
"""
import logging
from uuid import UUID
from dataclasses import dataclass

from langchain_openai import OpenAIEmbeddings
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Embedding, Meeting
from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class SearchResult:
    """Результат поиска"""
    chunk_text: str
    meeting_id: UUID
    meeting_title: str
    meeting_date: str | None
    similarity: float


class RAGService:
    """RAG сервис для ответов на вопросы по истории встреч"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.embeddings = OpenAIEmbeddings(model="text-embedding-ada-002")
        self.llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            api_key=settings.anthropic_api_key,
        )

    async def search_similar(
        self,
        query: str,
        limit: int = 5,
        client_id: UUID | None = None
    ) -> list[SearchResult]:
        """
        Поиск похожих чанков по запросу.

        Args:
            query: Текст запроса
            limit: Максимальное количество результатов
            client_id: Фильтр по клиенту (опционально)

        Returns:
            Список результатов поиска с similarity score
        """
        # Создаём эмбеддинг запроса
        query_embedding = self.embeddings.embed_query(query)

        # Форматируем вектор для pgvector
        vector_str = "[" + ",".join(map(str, query_embedding)) + "]"

        # Формируем SQL запрос с pgvector
        # Используем cosine distance (1 - cosine_similarity)
        # Вектор вставляется напрямую, т.к. он генерируется нами (безопасно)
        sql = f"""
            SELECT
                e.chunk_text,
                e.meeting_id,
                m.title as meeting_title,
                m.date as meeting_date,
                1 - (e.embedding <=> '{vector_str}'::vector) as similarity
            FROM embeddings e
            JOIN meetings m ON e.meeting_id = m.id
        """

        if client_id:
            sql += " WHERE m.client_id = :client_id"

        sql += f"""
            ORDER BY e.embedding <=> '{vector_str}'::vector
            LIMIT :limit
        """

        params = {"limit": limit}
        if client_id:
            params["client_id"] = str(client_id)

        result = await self.session.execute(text(sql), params)
        rows = result.fetchall()

        return [
            SearchResult(
                chunk_text=row.chunk_text,
                meeting_id=row.meeting_id,
                meeting_title=row.meeting_title,
                meeting_date=str(row.meeting_date) if row.meeting_date else None,
                similarity=float(row.similarity),
            )
            for row in rows
        ]

    async def ask(
        self,
        question: str,
        client_id: UUID | None = None,
        num_chunks: int = 5
    ) -> tuple[str, list[SearchResult]]:
        """
        Ответить на вопрос по истории встреч.

        Args:
            question: Вопрос пользователя
            client_id: Фильтр по клиенту (опционально)
            num_chunks: Количество чанков для контекста

        Returns:
            Кортеж (ответ, список источников)
        """
        # Поиск релевантных чанков
        sources = await self.search_similar(question, limit=num_chunks, client_id=client_id)

        if not sources:
            return "К сожалению, я не нашёл релевантной информации по вашему вопросу.", []

        # Формируем контекст из найденных чанков
        context_parts = []
        for i, source in enumerate(sources, 1):
            context_parts.append(
                f"[Источник {i}: {source.meeting_title}"
                f"{f' ({source.meeting_date})' if source.meeting_date else ''}]\n"
                f"{source.chunk_text}"
            )
        context = "\n\n---\n\n".join(context_parts)

        # Создаём промпт
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Ты — умный ассистент бизнес-консультанта. Твоя задача — отвечать на вопросы,
используя контекст из транскриптов прошлых встреч.

Правила:
1. Отвечай на основе предоставленного контекста
2. Если информации недостаточно, честно скажи об этом
3. Указывай, из какой встречи взята информация, если это уместно
4. Будь конкретным и полезным
5. Отвечай на русском языке"""),
            ("human", """Контекст из транскриптов встреч:

{context}

---

Вопрос: {question}

Ответ:""")
        ])

        # Генерируем ответ
        chain = prompt | self.llm
        response = await chain.ainvoke({
            "context": context,
            "question": question
        })

        return response.content, sources

    async def get_meeting_context(
        self,
        meeting_id: UUID,
        question: str = "Расскажи основное содержание"
    ) -> str:
        """
        Получить контекст/саммари конкретной встречи.
        """
        # Получаем все чанки встречи
        result = await self.session.execute(
            select(Embedding.chunk_text)
            .where(Embedding.meeting_id == meeting_id)
            .order_by(Embedding.chunk_index)
        )
        chunks = [row[0] for row in result.fetchall()]

        if not chunks:
            return "Эта встреча не проиндексирована."

        context = "\n\n".join(chunks[:10])  # Берём первые 10 чанков

        prompt = ChatPromptTemplate.from_messages([
            ("system", "Ты — ассистент для анализа транскриптов встреч. Отвечай кратко и по делу."),
            ("human", """Транскрипт встречи:

{context}

---

{question}""")
        ])

        chain = prompt | self.llm
        response = await chain.ainvoke({
            "context": context,
            "question": question
        })

        return response.content
