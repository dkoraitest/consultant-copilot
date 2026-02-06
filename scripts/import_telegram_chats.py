#!/usr/bin/env python3
"""
Скрипт импорта сообщений из Telegram чатов.

ВАЖНО: Этот скрипт использует ТОЛЬКО методы чтения.
Никакие сообщения не отправляются, не удаляются и не редактируются.

Использование:
    python scripts/import_telegram_chats.py [--dry-run] [--limit N]

Параметры:
    --dry-run   Только показать что будет импортировано, без записи в БД
    --limit N   Ограничить количество сообщений на чат (для тестирования)
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config import get_settings
from src.services.telegram_sync_service import TelegramSyncService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Чаты для импорта: (chat_id, title, client_name)
CHATS_TO_IMPORT = [
    # Клиентские чаты с саммари
    (4267171658, "Стратегия Raft AI", "Raft"),
    (4174461755, "GWPro (СИО) & Dima/Pasha", "СИО"),
    (2528902506, "CloudBuying & Dima", "CloudBuying"),
    (5092277045, "Stool Group & AI Surfers", "Stool Group"),
    (4864908224, "Project: Lunas", "Lunas"),
    (4986330661, "Indigo (3)", "Indigo"),
    (4737735399, "AI Surfers & Internet Services", "Internet Services"),
]


async def dry_run_import(settings):
    """Показать что будет импортировано без записи в БД"""
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.types import PeerChannel

    client = TelegramClient(
        StringSession(settings.telegram_session),
        settings.telegram_api_id,
        settings.telegram_api_hash
    )
    await client.connect()

    if not await client.is_user_authorized():
        logger.error("Telegram session is not authorized")
        return

    me = await client.get_me()
    logger.info(f"Connected as: {me.first_name} (@{me.username})")

    print("\n" + "="*70)
    print("DRY RUN: Показываю что будет импортировано")
    print("="*70)

    total_messages = 0

    for chat_id, title, client_name in CHATS_TO_IMPORT:
        try:
            # Пробуем найти чат
            entity = None
            try:
                entity = await client.get_entity(PeerChannel(chat_id))
            except Exception:
                async for dialog in client.iter_dialogs():
                    if abs(dialog.id) == chat_id:
                        entity = dialog.entity
                        break

            if not entity:
                print(f"\n❌ {title}: НЕ НАЙДЕН")
                continue

            # Считаем сообщения (только с текстом)
            count = 0
            async for msg in client.iter_messages(entity, limit=None):
                if msg.text and len(msg.text) >= 50:
                    count += 1

            total_messages += count
            print(f"\n✅ {title}")
            print(f"   Client: {client_name}")
            print(f"   Messages (>50 chars): {count}")

        except Exception as e:
            print(f"\n❌ {title}: ERROR - {e}")

    print("\n" + "="*70)
    print(f"ИТОГО: {total_messages} сообщений для индексации")
    print("="*70)

    await client.disconnect()


async def run_import(settings, limit: int | None = None):
    """Выполнить импорт сообщений"""
    # Создаём подключение к БД
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        service = TelegramSyncService(session)

        try:
            total_stats = {
                "chats": 0,
                "new_messages": 0,
                "indexed": 0,
                "errors": 0,
            }

            for chat_id, title, client_name in CHATS_TO_IMPORT:
                print(f"\n{'='*70}")
                print(f"📁 {title} (client: {client_name})")
                print(f"{'='*70}")

                try:
                    # Регистрируем чат
                    await service.register_chat(chat_id, title, client_name)

                    # Синхронизируем сообщения
                    print("\n📥 Синхронизация сообщений...")
                    sync_stats = await service.sync_chat_messages(chat_id, limit=limit)
                    print(f"   Получено: {sync_stats['total_fetched']}")
                    print(f"   Новых: {sync_stats['new_messages']}")
                    print(f"   Пропущено: {sync_stats['skipped']}")

                    # Индексируем
                    print("\n🔍 Создание эмбеддингов...")
                    index_stats = await service.index_chat_messages(chat_id)
                    print(f"   Проиндексировано: {index_stats['indexed']}")
                    print(f"   Пропущено (короткие): {index_stats['skipped']}")

                    total_stats["chats"] += 1
                    total_stats["new_messages"] += sync_stats["new_messages"]
                    total_stats["indexed"] += index_stats["indexed"]

                except Exception as e:
                    logger.error(f"Error processing {title}: {e}")
                    total_stats["errors"] += 1

            print(f"\n{'='*70}")
            print("📊 ИТОГО:")
            print(f"   Чатов обработано: {total_stats['chats']}")
            print(f"   Новых сообщений: {total_stats['new_messages']}")
            print(f"   Проиндексировано: {total_stats['indexed']}")
            print(f"   Ошибок: {total_stats['errors']}")
            print(f"{'='*70}")

        finally:
            await service.close()

    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(
        description="Импорт сообщений из Telegram чатов"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать что будет импортировано"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничить количество сообщений на чат"
    )
    args = parser.parse_args()

    settings = get_settings()

    # Проверяем настройки Telegram
    if not all([settings.telegram_api_id, settings.telegram_api_hash, settings.telegram_session]):
        logger.error(
            "Missing Telegram credentials. Set TELEGRAM_API_ID, "
            "TELEGRAM_API_HASH, TELEGRAM_SESSION in .env"
        )
        sys.exit(1)

    if args.dry_run:
        asyncio.run(dry_run_import(settings))
    else:
        asyncio.run(run_import(settings, limit=args.limit))


if __name__ == "__main__":
    main()
