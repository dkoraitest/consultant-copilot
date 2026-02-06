"""
Периодическая досинхронизация пропущенных сообщений.

Каждый час проверяет, не было ли пропущено сообщений
(например, во время деплоя или перезапуска), и индексирует их.
"""
import asyncio
import logging
from typing import TYPE_CHECKING

from telethon import TelegramClient
from telethon.tl.types import PeerChannel

from src.database.connection import async_session_maker
from src.database.models import TelegramChat

if TYPE_CHECKING:
    from src.telegram_watcher.handlers import MessageHandler

logger = logging.getLogger(__name__)


class CatchupService:
    """Периодическая досинхронизация пропущенных сообщений"""

    CATCHUP_INTERVAL = 3600  # 1 час

    def __init__(self, client: TelegramClient, handler: "MessageHandler"):
        self.client = client
        self.handler = handler

    async def run_periodic_catchup(self):
        """Фоновая задача: каждый час проверять пропущенные сообщения"""
        while True:
            await asyncio.sleep(self.CATCHUP_INTERVAL)
            try:
                await self.catchup_all_chats()
            except asyncio.CancelledError:
                logger.info("Periodic catchup cancelled")
                break
            except Exception as e:
                logger.error(f"Catchup error: {e}")

    async def catchup_all_chats(self):
        """Досинхронизировать все активные чаты"""
        async with async_session_maker() as session:
            chats = await self.handler.get_active_chats(session)

        total_new = 0
        for chat in chats:
            try:
                new_count = await self.catchup_chat(chat.id, chat.last_synced_message_id)
                total_new += new_count
            except Exception as e:
                logger.error(f"Error catching up chat {chat.id}: {e}")

        if total_new > 0:
            logger.info(f"Catchup completed: {total_new} new messages indexed")
        else:
            logger.debug("Catchup completed: no new messages")

    async def catchup_chat(self, chat_id: int, min_id: int | None) -> int:
        """
        Досинхронизировать один чат.

        Args:
            chat_id: ID чата в Telegram
            min_id: Последний синхронизированный message_id (если есть)

        Returns:
            Количество новых проиндексированных сообщений
        """
        try:
            # Пробуем получить entity разными способами
            entity = None
            try:
                entity = await self.client.get_entity(PeerChannel(chat_id))
            except Exception:
                # Пробуем через dialogs
                async for dialog in self.client.iter_dialogs():
                    if abs(dialog.id) == chat_id or dialog.id == chat_id:
                        entity = dialog.entity
                        break

            if not entity:
                logger.warning(f"Could not find entity for chat {chat_id}")
                return 0

            new_count = 0

            # Итерируем по сообщениям новее min_id
            async for msg in self.client.iter_messages(
                entity,
                min_id=min_id or 0,
                reverse=True  # От старых к новым
            ):
                if msg.text and len(msg.text) >= self.handler.MIN_TEXT_LENGTH:
                    saved = await self.handler._save_and_index_message(
                        chat_id=chat_id,
                        message_id=msg.id,
                        date=msg.date,
                        sender_name=self._get_sender_name(msg),
                        text=msg.text,
                    )
                    if saved:
                        new_count += 1

            if new_count > 0:
                logger.info(f"Chat {chat_id}: caught up {new_count} messages")

            return new_count

        except Exception as e:
            logger.error(f"Error in catchup_chat {chat_id}: {e}")
            return 0

    def _get_sender_name(self, msg) -> str | None:
        """Извлечь имя отправителя из сообщения"""
        try:
            if msg.sender:
                if hasattr(msg.sender, 'first_name'):
                    name = msg.sender.first_name or ""
                    if hasattr(msg.sender, 'last_name') and msg.sender.last_name:
                        name += f" {msg.sender.last_name}"
                    return name.strip() or None
                elif hasattr(msg.sender, 'title'):
                    return msg.sender.title
        except Exception:
            pass
        return None
