"""
Утилиты для Streamlit Dashboard
"""
import asyncio
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import async_session_maker
from src.database.models import Settings, TelegramChat, TelegramMessage, Meeting, Embedding, TelegramEmbedding, Client


def run_async(coro):
    """Запустить асинхронную функцию в синхронном контексте Streamlit"""
    # Используем asyncio.run для правильной очистки ресурсов
    return asyncio.run(coro)


# ============================================================================
# Settings
# ============================================================================

DEFAULT_SETTINGS = {
    "system_prompt": """Ты — ассистент бизнес-консультанта. Отвечай на вопросы строго на основе предоставленных данных:
- Транскрипты встреч (записи разговоров)
- Переписка в Telegram (рабочие чаты с клиентами)

ПРАВИЛА ОТВЕТА:
1. Давай КОНКРЕТНЫЕ ответы с деталями из источников
2. Цитируй ключевые фразы участников (в кавычках)
3. Указывай даты встреч и сообщений
4. Структурируй ответ: используй нумерованные списки
5. НЕ придумывай информацию, которой нет в контексте
6. Отвечай на русском языке""",
    "min_similarity": "0.15",
    "max_chunks_per_meeting": "2",
    "max_total_chunks": "20",
}


async def get_setting(key: str) -> str | None:
    """Получить настройку из БД"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(Settings.value).where(Settings.key == key)
        )
        row = result.scalar_one_or_none()
        return row if row else DEFAULT_SETTINGS.get(key)


async def set_setting(key: str, value: str, description: str | None = None):
    """Сохранить настройку в БД"""
    async with async_session_maker() as session:
        # Upsert
        existing = await session.execute(
            select(Settings).where(Settings.key == key)
        )
        setting = existing.scalar_one_or_none()

        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
            if description:
                setting.description = description
        else:
            setting = Settings(key=key, value=value, description=description)
            session.add(setting)

        await session.commit()


async def get_all_settings() -> dict[str, str]:
    """Получить все настройки"""
    async with async_session_maker() as session:
        result = await session.execute(select(Settings))
        settings = {s.key: s.value for s in result.scalars().all()}

    # Добавляем дефолты для отсутствующих
    for key, default in DEFAULT_SETTINGS.items():
        if key not in settings:
            settings[key] = default

    return settings


# ============================================================================
# Statistics
# ============================================================================

async def get_stats() -> dict[str, Any]:
    """Получить статистику по индексу"""
    async with async_session_maker() as session:
        # Встречи
        meetings_result = await session.execute(
            text("SELECT COUNT(*) FROM meetings")
        )
        meetings_count = meetings_result.scalar()

        # Встречи с транскриптами
        transcripts_result = await session.execute(
            text("SELECT COUNT(*) FROM meetings WHERE transcript IS NOT NULL AND transcript != ''")
        )
        transcripts_count = transcripts_result.scalar()

        # Эмбеддинги встреч
        embeddings_result = await session.execute(
            text("SELECT COUNT(*) FROM embeddings")
        )
        embeddings_count = embeddings_result.scalar()

        # Telegram чаты
        chats_result = await session.execute(
            text("SELECT COUNT(*) FROM telegram_chats WHERE is_active = true")
        )
        chats_count = chats_result.scalar()

        # Telegram сообщения
        messages_result = await session.execute(
            text("SELECT COUNT(*) FROM telegram_messages")
        )
        messages_count = messages_result.scalar()

        # Telegram эмбеддинги
        tg_embeddings_result = await session.execute(
            text("SELECT COUNT(*) FROM telegram_embeddings")
        )
        tg_embeddings_count = tg_embeddings_result.scalar()

        return {
            "meetings_total": meetings_count,
            "meetings_with_transcripts": transcripts_count,
            "meeting_embeddings": embeddings_count,
            "telegram_chats": chats_count,
            "telegram_messages": messages_count,
            "telegram_embeddings": tg_embeddings_count,
        }


# ============================================================================
# Telegram Chats
# ============================================================================

async def get_telegram_chats() -> list[dict]:
    """Получить список Telegram чатов"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(TelegramChat).order_by(TelegramChat.title)
        )
        chats = result.scalars().all()
        return [
            {
                "id": c.id,
                "title": c.title,
                "client_name": c.client_name,
                "is_active": c.is_active,
                "last_synced": c.last_synced_message_id,
            }
            for c in chats
        ]


async def toggle_chat_active(chat_id: int, is_active: bool):
    """Активировать/деактивировать чат"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(TelegramChat).where(TelegramChat.id == chat_id)
        )
        chat = result.scalar_one_or_none()
        if chat:
            chat.is_active = is_active
            await session.commit()


# ============================================================================
# Clients
# ============================================================================

async def get_clients() -> list[dict]:
    """Получить список всех клиентов с статистикой"""
    async with async_session_maker() as session:
        # Получаем клиентов с подсчётом встреч и чатов
        result = await session.execute(
            text("""
                SELECT
                    c.id,
                    c.name,
                    c.created_at,
                    COUNT(DISTINCT m.id) as meetings_count,
                    COUNT(DISTINCT tc.id) as chats_count,
                    COUNT(DISTINCT tm.id) as messages_count
                FROM clients c
                LEFT JOIN meetings m ON m.client_id = c.id
                LEFT JOIN telegram_chats tc ON tc.client_id = c.id
                LEFT JOIN telegram_messages tm ON tm.chat_id = tc.id
                GROUP BY c.id, c.name, c.created_at
                ORDER BY c.name
            """)
        )
        rows = result.fetchall()
        return [
            {
                "id": str(row[0]),
                "name": row[1],
                "created_at": row[2],
                "meetings_count": row[3],
                "chats_count": row[4],
                "messages_count": row[5],
            }
            for row in rows
        ]


async def create_client(name: str) -> dict | None:
    """Создать нового клиента"""
    async with async_session_maker() as session:
        # Проверяем уникальность
        result = await session.execute(
            select(Client).where(Client.name == name)
        )
        if result.scalar_one_or_none():
            return None  # Клиент уже существует

        client = Client(name=name)
        session.add(client)
        await session.commit()
        await session.refresh(client)

        return {
            "id": str(client.id),
            "name": client.name,
        }


async def delete_client(client_id: str) -> bool:
    """Удалить клиента (только если нет связанных данных)"""
    from uuid import UUID
    async with async_session_maker() as session:
        result = await session.execute(
            select(Client).where(Client.id == UUID(client_id))
        )
        client = result.scalar_one_or_none()
        if not client:
            return False

        # Проверяем, есть ли связанные встречи или чаты
        meetings_count = await session.execute(
            text("SELECT COUNT(*) FROM meetings WHERE client_id = :cid"),
            {"cid": client_id}
        )
        if meetings_count.scalar() > 0:
            return False  # Есть связанные встречи

        await session.delete(client)
        await session.commit()
        return True


async def update_chat_client(chat_id: int, client_id: str | None):
    """Привязать чат к клиенту"""
    from uuid import UUID
    async with async_session_maker() as session:
        result = await session.execute(
            select(TelegramChat).where(TelegramChat.id == chat_id)
        )
        chat = result.scalar_one_or_none()
        if chat:
            chat.client_id = UUID(client_id) if client_id else None
            await session.commit()


async def create_telegram_chat(chat_id: int, title: str, client_id: str | None = None) -> dict | None:
    """Создать новый Telegram чат"""
    from uuid import UUID
    async with async_session_maker() as session:
        # Проверяем, не существует ли уже
        result = await session.execute(
            select(TelegramChat).where(TelegramChat.id == chat_id)
        )
        if result.scalar_one_or_none():
            return None  # Чат уже существует

        chat = TelegramChat(
            id=chat_id,
            title=title,
            client_id=UUID(client_id) if client_id else None,
            is_active=True,
        )
        session.add(chat)
        await session.commit()

        return {
            "id": chat.id,
            "title": chat.title,
        }


async def get_telegram_chats_with_clients() -> list[dict]:
    """Получить список Telegram чатов с информацией о клиентах"""
    async with async_session_maker() as session:
        result = await session.execute(
            text("""
                SELECT
                    tc.id,
                    tc.title,
                    tc.client_name,
                    tc.client_id,
                    c.name as client_display_name,
                    tc.is_active,
                    tc.last_synced_message_id,
                    COUNT(tm.id) as messages_count
                FROM telegram_chats tc
                LEFT JOIN clients c ON tc.client_id = c.id
                LEFT JOIN telegram_messages tm ON tm.chat_id = tc.id
                GROUP BY tc.id, tc.title, tc.client_name, tc.client_id, c.name, tc.is_active, tc.last_synced_message_id
                ORDER BY tc.title
            """)
        )
        rows = result.fetchall()
        return [
            {
                "id": row[0],
                "title": row[1],
                "client_name_legacy": row[2],
                "client_id": str(row[3]) if row[3] else None,
                "client_name": row[4],
                "is_active": row[5],
                "last_synced": row[6],
                "messages_count": row[7],
            }
            for row in rows
        ]


# ============================================================================
# Unlinked Meetings
# ============================================================================

async def get_unlinked_meetings(limit: int = 100, offset: int = 0, search: str = "") -> tuple[list[dict], int]:
    """Получить встречи без привязки к клиенту"""
    async with async_session_maker() as session:
        # Базовый запрос
        where_clause = "WHERE m.client_id IS NULL"
        params = {"limit": limit, "offset": offset}

        if search:
            where_clause += " AND LOWER(m.title) LIKE :search"
            params["search"] = f"%{search.lower()}%"

        # Получаем встречи
        result = await session.execute(
            text(f"""
                SELECT m.id, m.title, m.date,
                       CASE WHEN m.transcript IS NOT NULL AND m.transcript != '' THEN true ELSE false END as has_transcript
                FROM meetings m
                {where_clause}
                ORDER BY m.date DESC NULLS LAST
                LIMIT :limit OFFSET :offset
            """),
            params
        )
        rows = result.fetchall()

        # Получаем общее количество
        count_result = await session.execute(
            text(f"""
                SELECT COUNT(*) FROM meetings m {where_clause}
            """),
            params
        )
        total = count_result.scalar()

        return [
            {
                "id": str(row[0]),
                "title": row[1],
                "date": row[2],
                "has_transcript": row[3],
            }
            for row in rows
        ], total


async def link_meeting_to_client(meeting_id: str, client_id: str):
    """Привязать встречу к клиенту"""
    from uuid import UUID
    async with async_session_maker() as session:
        await session.execute(
            text("UPDATE meetings SET client_id = :client_id WHERE id = :meeting_id"),
            {"client_id": client_id, "meeting_id": meeting_id}
        )
        await session.commit()


async def bulk_link_meetings_by_pattern(pattern: str, client_id: str) -> int:
    """Массово привязать встречи по паттерну в названии"""
    from uuid import UUID
    async with async_session_maker() as session:
        result = await session.execute(
            text("""
                UPDATE meetings
                SET client_id = :client_id
                WHERE client_id IS NULL
                  AND LOWER(title) LIKE :pattern
                RETURNING id
            """),
            {"client_id": client_id, "pattern": f"%{pattern.lower()}%"}
        )
        updated = len(result.fetchall())
        await session.commit()
        return updated
