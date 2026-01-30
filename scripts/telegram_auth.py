"""
Скрипт для авторизации Telethon и получения session string

Запуск:
    python scripts/telegram_auth.py

Инструкции:
1. Получите api_id и api_hash на https://my.telegram.org
2. Укажите их ниже или в переменных окружения
3. Запустите скрипт
4. Введите номер телефона и код подтверждения
5. Скопируйте полученный session string в .env
"""
import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession

# Укажите здесь или через переменные окружения
API_ID = os.getenv("TELEGRAM_API_ID") or "YOUR_API_ID"
API_HASH = os.getenv("TELEGRAM_API_HASH") or "YOUR_API_HASH"


async def create_session():
    print("=" * 50)
    print("Telegram Session Generator")
    print("=" * 50)
    print()

    if API_ID == "YOUR_API_ID" or API_HASH == "YOUR_API_HASH":
        print("Ошибка: укажите API_ID и API_HASH")
        print("Получить можно на https://my.telegram.org")
        return

    async with TelegramClient(StringSession(), int(API_ID), API_HASH) as client:
        print()
        print("Авторизация успешна!")
        print()
        print("=" * 50)
        print("TELEGRAM_SESSION:")
        print("=" * 50)
        print()
        print(client.session.save())
        print()
        print("=" * 50)
        print()
        print("Скопируйте строку выше в файл .env:")
        print("TELEGRAM_SESSION=<ваша_строка>")


if __name__ == "__main__":
    asyncio.run(create_session())
