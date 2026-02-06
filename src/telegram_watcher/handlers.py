"""
Обработчик сообщений для Telegram Watcher.

Сохраняет новые сообщения в БД и создаёт эмбеддинги для RAG.
"""
import logging
from uuid import uuid4

from langchain_openai import OpenAIEmbeddings
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import TelegramChat, TelegramMessage, TelegramEmbedding
from src.database.connection import async_session_maker

logger = logging.getLogger(__name__)


class MessageHandler:
    """Обработчик новых сообщений из Telegram"""

    MIN_TEXT_LENGTH = 50  # Минимальная длина текста для индексации

    def __init__(self):
        self.embeddings_model = OpenAIEmbeddings(model="text-embedding-ada-002")

    async def get_active_chat_ids(self, session: AsyncSession) -> list[int]:
        """Получить ID активных чатов для мониторинга"""
        result = await session.execute(
            select(TelegramChat.id).where(TelegramChat.is_active == True)
        )
        return [row[0] for row in result.fetchall()]

    async def get_active_chats(self, session: AsyncSession) -> list[TelegramChat]:
        """Получить активные чаты с их метаданными"""
        result = await session.execute(
            select(TelegramChat).where(TelegramChat.is_active == True)
        )
        return list(result.scalars().all())

    async def process_message(self, event) -> bool:
        """
        Обработать новое сообщение (real-time event).

        Returns:
            True если сообщение было сохранено и проиндексировано
        """
        return await self._save_and_index_message(
            chat_id=event.chat_id,
            message_id=event.id,
            date=event.date,
            sender_name=self._get_sender_name(event),
            text=event.text,
        )

    async def _save_and_index_message(
        self,
        chat_id: int,
        message_id: int,
        date,
        sender_name: str | None,
        text: str | None,
    ) -> bool:
        """
        Сохранить и проиндексировать одно сообщение.

        Returns:
            True если сообщение было сохранено и проиндексировано
        """
        if not text or len(text) < self.MIN_TEXT_LENGTH:
            return False

        async with async_session_maker() as session:
            # Проверка дубликата
            existing = await session.execute(
                select(TelegramMessage.id)
                .where(TelegramMessage.chat_id == chat_id)
                .where(TelegramMessage.message_id == message_id)
            )
            if existing.scalar():
                return False

            try:
                # 1. Сохранить сообщение
                message = TelegramMessage(
                    id=uuid4(),
                    chat_id=chat_id,
                    message_id=message_id,
                    date=date,
                    sender_name=sender_name,
                    text=text,
                    has_media=False,
                )
                session.add(message)
                await session.flush()

                # 2. Создать эмбеддинг
                vector = self.embeddings_model.embed_query(text)
                embedding = TelegramEmbedding(
                    id=uuid4(),
                    message_id=message.id,
                    chunk_text=text,
                    chunk_index=0,
                    embedding=vector,
                )
                session.add(embedding)

                # 3. Обновить last_synced_message_id
                await session.execute(
                    update(TelegramChat)
                    .where(TelegramChat.id == chat_id)
                    .values(last_synced_message_id=message_id)
                )

                await session.commit()
                logger.info(f"Indexed message {message_id} from chat {chat_id}")
                return True

            except Exception as e:
                await session.rollback()
                logger.error(f"Error saving message {message_id}: {e}")
                return False

    def _get_sender_name(self, event) -> str | None:
        """Извлечь имя отправителя из события"""
        try:
            if event.sender:
                if hasattr(event.sender, 'first_name'):
                    name = event.sender.first_name or ""
                    if hasattr(event.sender, 'last_name') and event.sender.last_name:
                        name += f" {event.sender.last_name}"
                    return name.strip() or None
                elif hasattr(event.sender, 'title'):
                    return event.sender.title
        except Exception:
            pass
        return None
