"""
RAG сервис для Q&A по истории встреч
"""
import logging
import re
from datetime import datetime, timedelta
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
class DateRange:
    """Временной диапазон для фильтрации"""
    start: datetime
    end: datetime
    description: str  # Для логирования, напр. "Q4 2025"


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

    def _parse_date_range(self, question: str) -> DateRange | None:
        """
        Извлечь временной диапазон из вопроса.
        Поддерживает: кварталы, года, месяцы, "прошлый год/квартал/месяц".
        """
        question_lower = question.lower()
        now = datetime.now()

        # Определяем текущий год для относительных дат
        current_year = now.year

        # Паттерны для кварталов: "Q4 2025", "4 квартал 2025", "четвертый квартал"
        quarter_patterns = [
            (r'q([1-4])\s*(\d{4})', lambda m: (int(m.group(1)), int(m.group(2)))),
            (r'(\d{4})\s*q([1-4])', lambda m: (int(m.group(2)), int(m.group(1)))),
            (r'([1-4])\s*(?:й|ый|ой|ий)?\s*квартал\s*(\d{4})', lambda m: (int(m.group(1)), int(m.group(2)))),
            (r'([1-4])\s*(?:й|ый|ой|ий)?\s*квартал', lambda m: (int(m.group(1)), current_year)),
        ]

        # Словесные кварталы
        quarter_words = {
            'первый': 1, 'первого': 1, 'первом': 1,
            'второй': 2, 'второго': 2, 'втором': 2,
            'третий': 3, 'третьего': 3, 'третьем': 3,
            'четвертый': 4, 'четвертого': 4, 'четвертом': 4,
        }

        for word, q_num in quarter_words.items():
            if word in question_lower and 'квартал' in question_lower:
                # Ищем год рядом
                year_match = re.search(r'(\d{4})', question_lower)
                year = int(year_match.group(1)) if year_match else current_year
                return self._quarter_to_range(q_num, year)

        for pattern, extractor in quarter_patterns:
            match = re.search(pattern, question_lower)
            if match:
                q_num, year = extractor(match)
                return self._quarter_to_range(q_num, year)

        # "прошлый квартал", "предыдущий квартал"
        if re.search(r'прошл\w*\s+квартал|предыдущ\w*\s+квартал', question_lower):
            # Вычисляем предыдущий квартал
            current_quarter = (now.month - 1) // 3 + 1
            if current_quarter == 1:
                return self._quarter_to_range(4, current_year - 1)
            else:
                return self._quarter_to_range(current_quarter - 1, current_year)

        # Год: "2025 год", "за 2025", "в 2025"
        year_match = re.search(r'(?:за|в|на)\s*(\d{4})\s*(?:год|г\.?)?', question_lower)
        if year_match:
            year = int(year_match.group(1))
            return DateRange(
                start=datetime(year, 1, 1),
                end=datetime(year, 12, 31, 23, 59, 59),
                description=f"{year} год"
            )

        # "прошлый год", "предыдущий год"
        if re.search(r'прошл\w*\s+год|предыдущ\w*\s+год', question_lower):
            year = current_year - 1
            return DateRange(
                start=datetime(year, 1, 1),
                end=datetime(year, 12, 31, 23, 59, 59),
                description=f"{year} год"
            )

        # Месяцы
        months_ru = {
            'январ': 1, 'феврал': 2, 'март': 3, 'апрел': 4,
            'ма': 5, 'июн': 6, 'июл': 7, 'август': 8,
            'сентябр': 9, 'октябр': 10, 'ноябр': 11, 'декабр': 12
        }

        for month_prefix, month_num in months_ru.items():
            if month_prefix in question_lower:
                year_match = re.search(r'(\d{4})', question_lower)
                year = int(year_match.group(1)) if year_match else current_year

                # Последний день месяца
                if month_num == 12:
                    end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
                else:
                    end_date = datetime(year, month_num + 1, 1) - timedelta(days=1)

                return DateRange(
                    start=datetime(year, month_num, 1),
                    end=datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59),
                    description=f"{month_prefix}* {year}"
                )

        # "прошлый месяц"
        if re.search(r'прошл\w*\s+месяц|предыдущ\w*\s+месяц', question_lower):
            first_of_this_month = datetime(now.year, now.month, 1)
            last_of_prev_month = first_of_this_month - timedelta(days=1)
            first_of_prev_month = datetime(last_of_prev_month.year, last_of_prev_month.month, 1)
            return DateRange(
                start=first_of_prev_month,
                end=datetime(last_of_prev_month.year, last_of_prev_month.month, last_of_prev_month.day, 23, 59, 59),
                description="прошлый месяц"
            )

        # "последние N месяцев/недель"
        last_n_match = re.search(r'последни[ех]\s+(\d+)\s*(месяц|недел|дн)', question_lower)
        if last_n_match:
            n = int(last_n_match.group(1))
            unit = last_n_match.group(2)
            if 'месяц' in unit:
                start = now - timedelta(days=n * 30)
            elif 'недел' in unit:
                start = now - timedelta(weeks=n)
            else:  # дней
                start = now - timedelta(days=n)
            return DateRange(
                start=start,
                end=now,
                description=f"последние {n} {unit}*"
            )

        return None

    def _quarter_to_range(self, quarter: int, year: int) -> DateRange:
        """Преобразовать квартал в DateRange"""
        quarter_starts = {1: 1, 2: 4, 3: 7, 4: 10}
        quarter_ends = {1: 3, 2: 6, 3: 9, 4: 12}

        start_month = quarter_starts[quarter]
        end_month = quarter_ends[quarter]

        # Последний день квартала
        if end_month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, end_month + 1, 1) - timedelta(days=1)

        return DateRange(
            start=datetime(year, start_month, 1),
            end=datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59),
            description=f"Q{quarter} {year}"
        )

    async def search_similar_diversified(
        self,
        query: str,
        max_chunks_per_meeting: int = 2,
        max_total_chunks: int = 30,
        min_similarity: float = 0.15,
        client_id: UUID | None = None,
        title_filter: str | None = None,
        date_range: DateRange | None = None,
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

        if date_range:
            conditions.append("m.date >= :date_start AND m.date <= :date_end")
            params["date_start"] = date_range.start
            params["date_end"] = date_range.end

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

        # Автоматическое определение временного диапазона
        date_range = self._parse_date_range(question)
        if date_range:
            logger.info(f"Auto-detected date range: {date_range.description} ({date_range.start} - {date_range.end})")

        # Выбор стратегии поиска
        if title_filter or client_id or date_range:
            # Специфичный вопрос: 2 чанка/встречу, до 30 чанков — покрываем все встречи
            sources = await self.search_similar_diversified(
                query=question,
                max_chunks_per_meeting=2,
                max_total_chunks=30,
                min_similarity=0.15,
                client_id=client_id,
                title_filter=title_filter,
                date_range=date_range,
            )
            # Fallback: если с фильтрами слишком мало — убираем date_range
            if len(sources) < 3 and date_range:
                logger.info(f"Too few results with date filter, searching without date range")
                sources = await self.search_similar_diversified(
                    query=question,
                    max_chunks_per_meeting=2,
                    max_total_chunks=30,
                    min_similarity=0.15,
                    client_id=client_id,
                    title_filter=title_filter,
                )
            # Fallback 2: если всё ещё мало — убираем client filter
            if len(sources) < 3 and title_filter:
                logger.info(f"Too few results with client filter '{title_filter}', searching without filter")
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

        # Дополнительный контекст для промпта
        filter_note = ""
        if title_filter:
            filter_note += f"\nВажно: пользователь спрашивает конкретно про клиента/компанию «{title_filter}». Фокусируйся ТОЛЬКО на информации об этом клиенте."
        if date_range:
            filter_note += f"\nПользователь спрашивает про период: {date_range.description}. Учитывай только информацию за этот период."

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
