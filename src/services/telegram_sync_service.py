"""
Сервис синхронизации сообщений из Telegram чатов

ВАЖНО: Этот сервис использует ТОЛЬКО методы чтения Telethon.
Запрещённые методы (send_*, delete_*, edit_*) НЕ используются.
"""
import logging
from datetime import datetime
from uuid import uuid4

from langchain_openai import OpenAIEmbeddings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import PeerChannel

from src.database.models import TelegramChat, TelegramMessage, TelegramEmbedding
from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Минимальная длина текста для индексации
MIN_TEXT_LENGTH = 50


class TelegramSyncService:
    """
    Сервис для синхронизации сообщений из Telegram.

    Использует ТОЛЬКО read-only методы Telethon:
    - get_entity()
    - iter_messages()
    - iter_dialogs()
    - get_me()
    """

    def __init__(
        self,
        session: AsyncSession,
        api_id: int | None = None,
        api_hash: str | None = None,
        session_string: str | None = None,
    ):
        self.db_session = session
        self.api_id = api_id or settings.telegram_api_id
        self.api_hash = api_hash or settings.telegram_api_hash
        self.session_string = session_string or settings.telegram_session
        self.embeddings_model = OpenAIEmbeddings(model="text-embedding-ada-002")
        self._client: TelegramClient | None = None

    async def _get_client(self) -> TelegramClient:
        """Получить подключённый Telegram клиент"""
        if self._client is None:
            self._client = TelegramClient(
                StringSession(self.session_string),
                self.api_id,
                self.api_hash
            )
            await self._client.connect()

            if not await self._client.is_user_authorized():
                raise RuntimeError("Telegram session is not authorized")

            me = await self._client.get_me()
            logger.info(f"Connected to Telegram as {me.first_name} (@{me.username})")

        return self._client

    async def close(self):
        """Закрыть соединение с Telegram"""
        if self._client:
            await self._client.disconnect()
            self._client = None

    async def register_chat(
        self,
        chat_id: int,
        title: str,
        client_name: str | None = None,
    ) -> TelegramChat:
        """
        Зарегистрировать чат для синхронизации.

        Args:
            chat_id: Telegram chat ID
            title: Название чата
            client_name: Имя клиента для связи с meetings
        """
        # Upsert - вставить или обновить
        stmt = insert(TelegramChat).values(
            id=chat_id,
            title=title,
            client_name=client_name,
            is_active=True,
        ).on_conflict_do_update(
            index_elements=['id'],
            set_={
                'title': title,
                'client_name': client_name,
                'is_active': True,
            }
        )
        await self.db_session.execute(stmt)
        await self.db_session.commit()

        chat = await self.db_session.get(TelegramChat, chat_id)
        logger.info(f"Registered chat: {title} (ID: {chat_id}, client: {client_name})")
        return chat

    async def sync_chat_messages(
        self,
        chat_id: int,
        limit: int | None = None,
        min_date: datetime | None = None,
    ) -> dict:
        """
        Синхронизировать сообщения из чата.

        Args:
            chat_id: Telegram chat ID
            limit: Максимальное количество сообщений (None = все)
            min_date: Минимальная дата сообщений

        Returns:
            Статистика синхронизации
        """
        stats = {
            "total_fetched": 0,
            "new_messages": 0,
            "skipped": 0,
            "errors": 0,
        }

        # Проверяем, что чат зарегистрирован
        chat = await self.db_session.get(TelegramChat, chat_id)
        if not chat:
            raise ValueError(f"Chat {chat_id} not registered. Call register_chat() first.")

        client = await self._get_client()

        # Получаем entity для чата
        try:
            entity = await client.get_entity(PeerChannel(chat_id))
        except Exception:
            # Пробуем найти через диалоги
            entity = None
            async for dialog in client.iter_dialogs():
                if abs(dialog.id) == chat_id or dialog.id == chat_id:
                    entity = dialog.entity
                    break

            if not entity:
                raise ValueError(f"Could not find chat with ID {chat_id}")

        logger.info(f"Syncing messages from: {entity.title}")

        # Получаем последний синхронизированный message_id
        last_synced_id = chat.last_synced_message_id or 0

        # Итерируем по сообщениям (READ-ONLY операция)
        async for message in client.iter_messages(
            entity,
            limit=limit,
            min_id=last_synced_id,
            offset_date=min_date,
            reverse=True,  # От старых к новым
        ):
            stats["total_fetched"] += 1

            # Пропускаем сообщения без текста
            if not message.text:
                stats["skipped"] += 1
                continue

            try:
                # Проверяем, есть ли уже это сообщение
                existing = await self.db_session.execute(
                    select(TelegramMessage.id)
                    .where(TelegramMessage.chat_id == chat_id)
                    .where(TelegramMessage.message_id == message.id)
                )
                if existing.scalar_one_or_none():
                    stats["skipped"] += 1
                    continue

                # Определяем имя отправителя
                sender_name = None
                if message.sender:
                    if hasattr(message.sender, 'first_name'):
                        sender_name = f"{message.sender.first_name or ''} {message.sender.last_name or ''}".strip()
                    elif hasattr(message.sender, 'title'):
                        sender_name = message.sender.title

                # Определяем тип медиа
                has_media = message.media is not None
                media_type = None
                if has_media:
                    media_type = type(message.media).__name__.replace('MessageMedia', '').lower()

                # Создаём запись
                tg_message = TelegramMessage(
                    id=uuid4(),
                    chat_id=chat_id,
                    message_id=message.id,
                    date=message.date,
                    sender_name=sender_name,
                    text=message.text,
                    has_media=has_media,
                    media_type=media_type,
                )
                self.db_session.add(tg_message)
                stats["new_messages"] += 1

                # Обновляем last_synced_message_id
                if message.id > last_synced_id:
                    last_synced_id = message.id

                # Коммитим каждые 100 сообщений
                if stats["new_messages"] % 100 == 0:
                    chat.last_synced_message_id = last_synced_id
                    await self.db_session.commit()
                    logger.info(f"Progress: {stats['new_messages']} new messages saved")

            except Exception as e:
                logger.error(f"Error saving message {message.id}: {e}")
                stats["errors"] += 1

        # Финальный коммит
        chat.last_synced_message_id = last_synced_id
        await self.db_session.commit()

        logger.info(
            f"Sync complete for {entity.title}: "
            f"{stats['new_messages']} new, {stats['skipped']} skipped, "
            f"{stats['errors']} errors"
        )
        return stats

    async def index_chat_messages(
        self,
        chat_id: int,
        min_text_length: int = MIN_TEXT_LENGTH,
    ) -> dict:
        """
        Создать эмбеддинги для сообщений чата.

        Args:
            chat_id: Telegram chat ID
            min_text_length: Минимальная длина текста для индексации

        Returns:
            Статистика индексации
        """
        stats = {
            "total": 0,
            "indexed": 0,
            "skipped": 0,
            "errors": 0,
        }

        # Получаем сообщения без эмбеддингов
        result = await self.db_session.execute(
            select(TelegramMessage)
            .where(TelegramMessage.chat_id == chat_id)
            .where(TelegramMessage.text.isnot(None))
            .outerjoin(TelegramEmbedding)
            .where(TelegramEmbedding.id.is_(None))  # Нет эмбеддинга
        )
        messages = result.scalars().all()
        stats["total"] = len(messages)

        # Фильтруем по длине и собираем тексты для батча
        texts_to_embed = []
        messages_to_index = []

        for msg in messages:
            if not msg.text or len(msg.text) < min_text_length:
                stats["skipped"] += 1
                continue

            texts_to_embed.append(msg.text)
            messages_to_index.append(msg)

        if not texts_to_embed:
            logger.info(f"No messages to index for chat {chat_id}")
            return stats

        # Создаём эмбеддинги батчами по 100
        batch_size = 100
        for i in range(0, len(texts_to_embed), batch_size):
            batch_texts = texts_to_embed[i:i+batch_size]
            batch_messages = messages_to_index[i:i+batch_size]

            try:
                vectors = self.embeddings_model.embed_documents(batch_texts)

                for msg, text, vector in zip(batch_messages, batch_texts, vectors):
                    embedding = TelegramEmbedding(
                        id=uuid4(),
                        message_id=msg.id,
                        chunk_text=text,
                        chunk_index=0,
                        embedding=vector,
                    )
                    self.db_session.add(embedding)
                    stats["indexed"] += 1

                await self.db_session.commit()
                logger.info(f"Indexed batch {i//batch_size + 1}: {len(batch_texts)} messages")

            except Exception as e:
                logger.error(f"Error indexing batch: {e}")
                stats["errors"] += len(batch_texts)
                await self.db_session.rollback()

        logger.info(
            f"Indexing complete for chat {chat_id}: "
            f"{stats['indexed']} indexed, {stats['skipped']} skipped"
        )
        return stats

    async def sync_and_index_chat(
        self,
        chat_id: int,
        limit: int | None = None,
    ) -> dict:
        """
        Синхронизировать и проиндексировать чат (удобный метод).
        """
        sync_stats = await self.sync_chat_messages(chat_id, limit=limit)
        index_stats = await self.index_chat_messages(chat_id)

        return {
            "sync": sync_stats,
            "index": index_stats,
        }
