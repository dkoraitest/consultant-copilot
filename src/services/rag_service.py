"""
RAG сервис для Q&A по истории встреч
"""
import logging
from uuid import UUID
from dataclasses import dataclass
from collections import OrderedDict

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
            anthropic_api_key=settings.anthropic_api_key,
        )

    async def _find_client_filter(self, question: str) -> str | None:
        """
        Попытаться найти имя клиента/компании в вопросе,
        сопоставив с заголовками встреч в базе.
        """
        result = await self.session.execute(
            text("SELECT DISTINCT title FROM meetings WHERE title IS NOT NULL")
        )
        titles = [row[0] for row in result.fetchall()]

        question_lower = question.lower()

        # Извлекаем имена клиентов из заголовков (часть до " - ")
        client_names = set()
        for title in titles:
            parts = title.split(" - ")
            if parts:
                client_name = parts[0].strip()
                if len(client_name) > 2:
                    client_names.add(client_name)

        # Ищем лучшее совпадение с вопросом
        best_match = None
        best_match_len = 0
        for client_name in client_names:
            name_lower = client_name.lower()
            # Проверяем полное имя клиента
            if name_lower in question_lower:
                if len(name_lower) > best_match_len:
                    best_match = client_name
                    best_match_len = len(name_lower)
            else:
                # Проверяем значимые слова (>3 символов)
                for word in name_lower.split():
                    if len(word) > 3 and word in question_lower:
                        if len(word) > best_match_len:
                            best_match = client_name
                            best_match_len = len(word)

        return best_match

    async def search_similar_diversified(
        self,
        query: str,
        max_chunks_per_meeting: int = 2,
        max_total_chunks: int = 30,
        min_similarity: float = 0.15,
        client_id: UUID | None = None,
        title_filter: str | None = None,
    ) -> list[SearchResult]:
        """
        Diversified поиск: возвращает чанки из РАЗНЫХ встреч.

        Использует ROW_NUMBER() OVER (PARTITION BY meeting_id) чтобы
        ограничить количество чанков от одной встречи и обеспечить
        покрытие максимального числа встреч.
        """
        query_embedding = self.embeddings.embed_query(query)
        vector_str = "[" + ",".join(map(str, query_embedding)) + "]"

        # WHERE условия для CTE
        conditions = []
        params = {
            "max_chunks_per_meeting": max_chunks_per_meeting,
            "max_total_chunks": max_total_chunks,
            "min_similarity": min_similarity,
        }

        if client_id:
            conditions.append("m.client_id = :client_id")
            params["client_id"] = str(client_id)

        if title_filter:
            conditions.append("LOWER(m.title) LIKE :title_filter")
            params["title_filter"] = f"%{title_filter.lower()}%"

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"""
            WITH ranked_chunks AS (
                SELECT
                    e.chunk_text,
                    e.meeting_id,
                    m.title AS meeting_title,
                    m.date AS meeting_date,
                    1 - (e.embedding <=> '{vector_str}'::vector) AS similarity,
                    ROW_NUMBER() OVER (
                        PARTITION BY e.meeting_id
                        ORDER BY e.embedding <=> '{vector_str}'::vector
                    ) AS chunk_rank
                FROM embeddings e
                JOIN meetings m ON e.meeting_id = m.id
                {where_clause}
            )
            SELECT
                chunk_text,
                meeting_id,
                meeting_title,
                meeting_date,
                similarity
            FROM ranked_chunks
            WHERE chunk_rank <= :max_chunks_per_meeting
              AND similarity > :min_similarity
            ORDER BY similarity DESC
            LIMIT :max_total_chunks
        """

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

    def _format_context(self, sources: list[SearchResult]) -> str:
        """
        Форматирование результатов с группировкой по встречам.
        Чанки от одной встречи отображаются вместе.
        """
        meetings_chunks: OrderedDict[UUID, list[SearchResult]] = OrderedDict()
        for source in sources:
            if source.meeting_id not in meetings_chunks:
                meetings_chunks[source.meeting_id] = []
            meetings_chunks[source.meeting_id].append(source)

        parts = []
        for i, (meeting_id, chunks) in enumerate(meetings_chunks.items(), 1):
            header_source = chunks[0]
            date_str = f" ({header_source.meeting_date[:10]})" if header_source.meeting_date else ""
            header = f"[Встреча {i}: {header_source.meeting_title}{date_str}]"
            chunk_texts = "\n\n".join(c.chunk_text for c in chunks)
            parts.append(f"{header}\n{chunk_texts}")

        return "\n\n---\n\n".join(parts)

    async def search_similar(
        self,
        query: str,
        limit: int = 12,
        client_id: UUID | None = None,
        title_filter: str | None = None
    ) -> list[SearchResult]:
        """
        Простой поиск похожих чанков (без diversification).
        Используется в get_meeting_context и как fallback.
        """
        query_embedding = self.embeddings.embed_query(query)
        vector_str = "[" + ",".join(map(str, query_embedding)) + "]"

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

        conditions = []
        params = {"limit": limit}

        if client_id:
            conditions.append("m.client_id = :client_id")
            params["client_id"] = str(client_id)

        if title_filter:
            conditions.append("LOWER(m.title) LIKE :title_filter")
            params["title_filter"] = f"%{title_filter.lower()}%"

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += f"""
            ORDER BY e.embedding <=> '{vector_str}'::vector
            LIMIT :limit
        """

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
        num_chunks: int = 12
    ) -> tuple[str, list[SearchResult]]:
        """
        Ответить на вопрос по истории встреч.
        Использует diversified retrieval для покрытия всех встреч.
        """
        # Автоматическое определение клиента из вопроса
        title_filter = await self._find_client_filter(question)
        if title_filter:
            logger.info(f"Auto-detected client filter: {title_filter}")

        # Выбор стратегии поиска
        if title_filter or client_id:
            # Клиентский вопрос: 2 чанка/встречу, до 30 чанков — покрываем все встречи
            sources = await self.search_similar_diversified(
                query=question,
                max_chunks_per_meeting=2,
                max_total_chunks=30,
                min_similarity=0.15,
                client_id=client_id,
                title_filter=title_filter,
            )
            # Fallback: если с фильтром слишком мало
            if len(sources) < 3 and title_filter:
                logger.info(f"Too few results with filter '{title_filter}', searching without filter")
                sources = await self.search_similar_diversified(
                    query=question,
                    max_chunks_per_meeting=1,
                    max_total_chunks=20,
                    min_similarity=0.20,
                    client_id=client_id,
                )
        else:
            # Общий вопрос: 1 чанк/встречу, до 20 чанков
            sources = await self.search_similar_diversified(
                query=question,
                max_chunks_per_meeting=1,
                max_total_chunks=20,
                min_similarity=0.20,
            )

        if not sources:
            return "К сожалению, я не нашёл релевантной информации по вашему вопросу.", []

        # Логируем покрытие встреч
        meeting_ids = set(s.meeting_id for s in sources)
        logger.info(f"Diversified search: {len(sources)} chunks from {len(meeting_ids)} meetings")

        # Формируем контекст с группировкой по встречам
        context = self._format_context(sources)

        # Дополнительный контекст о клиенте для промпта
        filter_note = ""
        if title_filter:
            filter_note = f"\nВажно: пользователь спрашивает конкретно про клиента/компанию «{title_filter}». Фокусируйся ТОЛЬКО на информации об этом клиенте."

        prompt = ChatPromptTemplate.from_messages([
            ("system", """Ты — ассистент бизнес-консультанта. Отвечай на вопросы строго на основе предоставленных транскриптов встреч.
{filter_note}

ПРАВИЛА ОТВЕТА:
1. Давай КОНКРЕТНЫЕ ответы с деталями из транскриптов:
   - Цитируй ключевые фразы участников (в кавычках)
   - Указывай даты встреч
   - Перечисляй конкретные решения, договорённости, цифры, метрики
   - Называй имена участников, если они упоминаются в контексте
2. Структурируй ответ: используй нумерованные списки для перечислений
3. Для каждого тезиса указывай источник — название встречи и дату
4. Если информации недостаточно для полного ответа — честно скажи, чего не хватает
5. НЕ придумывай и НЕ додумывай информацию, которой нет в контексте
6. Отвечай на русском языке
7. Старайся упомянуть информацию из ВСЕХ предоставленных встреч, не ограничивайся 1-2 источниками"""),
            ("human", """Контекст из транскриптов встреч:

{context}

---

Вопрос: {question}

Дай подробный ответ с конкретными деталями из транскриптов:""")
        ])

        chain = prompt | self.llm
        response = await chain.ainvoke({
            "context": context,
            "question": question,
            "filter_note": filter_note
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
