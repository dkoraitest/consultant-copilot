#!/usr/bin/env python3
"""
Скрипт связывания клиентов с встречами и Telegram чатами.

Использование:
    python scripts/link_clients.py --preview   # Показать что будет связано
    python scripts/link_clients.py --apply     # Применить связи

Логика извлечения имени клиента из Meeting.title:
    "Timeweb Cloud - sync call" → "Timeweb Cloud"
    "Raft - strategy session" → "Raft"
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path
from collections import defaultdict

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert

from src.config import get_settings
from src.database.models import Meeting, Client, TelegramChat

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_client_name(title: str) -> str:
    """
    Извлечь имя клиента из названия встречи.

    Формат: "ClientName - description" → "ClientName"
    """
    if not title:
        return ""

    # Разделитель " - " (с пробелами)
    parts = title.split(" - ")
    if len(parts) >= 2:
        return parts[0].strip()

    # Если нет разделителя, возвращаем всё название
    return title.strip()


async def preview(session: AsyncSession):
    """Показать предпросмотр извлечённых клиентов"""

    print("\n" + "=" * 80)
    print("ПРЕДПРОСМОТР: Извлечение клиентов из названий встреч")
    print("=" * 80)

    # Получаем все встречи
    result = await session.execute(select(Meeting.title))
    titles = [row[0] for row in result.fetchall()]

    # Извлекаем имена клиентов и считаем встречи
    client_meetings = defaultdict(list)
    for title in titles:
        client_name = extract_client_name(title)
        if client_name:
            client_meetings[client_name].append(title)

    # Получаем существующие Telegram чаты
    result = await session.execute(select(TelegramChat.title, TelegramChat.client_name))
    telegram_chats = {row[0]: row[1] for row in result.fetchall()}

    # Получаем существующих клиентов
    result = await session.execute(select(Client.name))
    existing_clients = set(row[0] for row in result.fetchall())

    # Сортируем по количеству встреч
    sorted_clients = sorted(
        client_meetings.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )

    print(f"\n{'Client Name':<40} {'Meetings':>10} {'TG Chats':>10} {'Status':>15}")
    print("-" * 80)

    total_meetings = 0
    new_clients = 0

    for client_name, meetings in sorted_clients:
        count = len(meetings)
        total_meetings += count

        # Ищем соответствующие Telegram чаты
        tg_count = sum(1 for tg_name, tg_client in telegram_chats.items()
                      if tg_client == client_name or client_name.lower() in tg_name.lower())

        # Статус: NEW или EXISTS
        if client_name in existing_clients:
            status = "EXISTS"
        else:
            status = "NEW"
            new_clients += 1

        print(f"{client_name:<40} {count:>10} {tg_count:>10} {status:>15}")

    print("-" * 80)
    print(f"{'ИТОГО':<40} {total_meetings:>10}")
    print(f"\nУникальных клиентов: {len(sorted_clients)}")
    print(f"Новых для создания: {new_clients}")
    print(f"Уже существующих: {len(existing_clients)}")

    # Telegram чаты без соответствия
    print("\n" + "=" * 80)
    print("TELEGRAM ЧАТЫ")
    print("=" * 80)

    print(f"\n{'Chat Title':<50} {'client_name':<20}")
    print("-" * 80)

    for tg_title, tg_client in telegram_chats.items():
        print(f"{tg_title:<50} {tg_client or '(не задан)':<20}")

    print("\n" + "=" * 80)
    print("Для применения изменений запустите: python scripts/link_clients.py --apply")
    print("=" * 80)


async def apply(session: AsyncSession):
    """Применить связывание клиентов"""

    print("\n" + "=" * 80)
    print("ПРИМЕНЕНИЕ: Создание клиентов и связей")
    print("=" * 80)

    # Получаем все встречи
    result = await session.execute(select(Meeting.id, Meeting.title))
    meetings = result.fetchall()

    # Извлекаем уникальные имена клиентов
    client_names = set()
    for _, title in meetings:
        client_name = extract_client_name(title)
        if client_name:
            client_names.add(client_name)

    print(f"\nНайдено {len(client_names)} уникальных клиентов")

    # 1. Создаём клиентов (upsert)
    print("\n1. Создание клиентов...")
    created_count = 0

    for name in client_names:
        # Проверяем существование
        result = await session.execute(
            select(Client).where(Client.name == name)
        )
        existing = result.scalar_one_or_none()

        if not existing:
            client = Client(name=name)
            session.add(client)
            created_count += 1

    await session.commit()
    print(f"   Создано новых клиентов: {created_count}")

    # 2. Получаем маппинг client_name → client_id
    result = await session.execute(select(Client.name, Client.id))
    client_map = {row[0]: row[1] for row in result.fetchall()}

    # 3. Обновляем Meeting.client_id
    print("\n2. Связывание встреч с клиентами...")
    updated_meetings = 0

    for meeting_id, title in meetings:
        client_name = extract_client_name(title)
        if client_name and client_name in client_map:
            await session.execute(
                update(Meeting)
                .where(Meeting.id == meeting_id)
                .where(Meeting.client_id.is_(None))  # Только если не связано
                .values(client_id=client_map[client_name])
            )
            updated_meetings += 1

    await session.commit()
    print(f"   Обновлено встреч: {updated_meetings}")

    # 4. Связываем Telegram чаты
    print("\n3. Связывание Telegram чатов с клиентами...")
    result = await session.execute(
        select(TelegramChat.id, TelegramChat.title, TelegramChat.client_name)
    )
    telegram_chats = result.fetchall()

    updated_chats = 0
    for chat_id, tg_title, tg_client_name in telegram_chats:
        # Ищем клиента по client_name или по вхождению в title
        client_id = None

        # Сначала по точному совпадению client_name
        if tg_client_name and tg_client_name in client_map:
            client_id = client_map[tg_client_name]
        else:
            # Ищем по вхождению имени клиента в title чата
            for client_name, cid in client_map.items():
                if client_name.lower() in tg_title.lower():
                    client_id = cid
                    break

        if client_id:
            await session.execute(
                update(TelegramChat)
                .where(TelegramChat.id == chat_id)
                .values(client_id=client_id)
            )
            updated_chats += 1

    await session.commit()
    print(f"   Связано Telegram чатов: {updated_chats}")

    # 5. Итоговая статистика
    print("\n" + "=" * 80)
    print("ИТОГО:")
    print(f"   Создано клиентов: {created_count}")
    print(f"   Связано встреч: {updated_meetings}")
    print(f"   Связано Telegram чатов: {updated_chats}")
    print("=" * 80)

    # Проверка
    result = await session.execute(
        select(Client.name, func.count(Meeting.id))
        .join(Meeting, Meeting.client_id == Client.id)
        .group_by(Client.name)
        .order_by(func.count(Meeting.id).desc())
        .limit(10)
    )

    print("\nТоп-10 клиентов по количеству встреч:")
    for name, count in result.fetchall():
        print(f"   {name}: {count} встреч")


async def main(args):
    settings = get_settings()

    # Создаём подключение к БД
    db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        if args.preview:
            await preview(session)
        elif args.apply:
            await apply(session)
        else:
            print("Укажите --preview или --apply")
            print("  --preview: показать что будет связано")
            print("  --apply: применить связи")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Связывание клиентов с встречами и Telegram чатами"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Показать предпросмотр (без изменений в БД)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Применить связывание"
    )
    args = parser.parse_args()

    asyncio.run(main(args))
