"""
Интеграция с Telegram User API (Telethon)
Для чтения истории чатов
"""
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession

from src.config import get_settings


class TelegramHistoryLoader:
    """Загрузка истории чатов для RAG"""

    def __init__(self):
        settings = get_settings()
        self.client = TelegramClient(
            StringSession(settings.telegram_session),
            settings.telegram_api_id,
            settings.telegram_api_hash
        )

    async def connect(self):
        """Подключиться к Telegram"""
        await self.client.connect()

    async def disconnect(self):
        """Отключиться от Telegram"""
        await self.client.disconnect()

    async def get_client_chats(self, client_name: str) -> list:
        """Найти чаты связанные с клиентом"""
        chats = []
        async for dialog in self.client.iter_dialogs():
            if client_name.lower() in dialog.name.lower():
                chats.append({
                    "id": dialog.id,
                    "name": dialog.name,
                    "type": "group" if dialog.is_group else "private"
                })
        return chats

    async def get_chat_history(
        self,
        chat_id: int,
        limit: int = 500,
        min_date: datetime | None = None
    ) -> list:
        """Получить историю чата"""
        messages = []
        async for msg in self.client.iter_messages(
            chat_id,
            limit=limit,
            offset_date=min_date
        ):
            if msg.text:
                messages.append({
                    "id": msg.id,
                    "date": msg.date.isoformat(),
                    "sender_id": msg.sender_id,
                    "text": msg.text,
                    "reply_to": msg.reply_to_msg_id
                })
        return messages

    async def search_messages(self, query: str, limit: int = 100) -> list:
        """Поиск сообщений по тексту"""
        messages = []
        async for msg in self.client.iter_messages(None, search=query, limit=limit):
            if msg.text:
                messages.append({
                    "id": msg.id,
                    "date": msg.date.isoformat(),
                    "chat_id": msg.chat_id,
                    "text": msg.text
                })
        return messages
