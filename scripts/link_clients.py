#!/usr/bin/env python3
"""
Скрипт умного связывания клиентов с встречами и Telegram чатами.

Использование:
    python scripts/link_clients.py --preview          # Показать что будет связано
    python scripts/link_clients.py --apply-confident  # Применить только очевидные связи
    python scripts/link_clients.py --export-uncertain # Экспорт неочевидных в CSV

Логика:
1. Создать клиентов из известных источников (Telegram чаты + паттерны)
2. Связать очевидные встречи (имя клиента в title или часто в транскрипте)
3. Выделить неочевидные в отдельный список для ручной проверки
"""
import asyncio
import argparse
import csv
import logging
import re
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config import get_settings
from src.database.models import Meeting, Client, TelegramChat

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Известные клиенты и их алиасы
# ============================================================================

# Формат: "canonical_name": ["alias1", "alias2", ...]
KNOWN_CLIENTS = {
    "Timeweb Cloud": ["Timeweb", "TimeWeb", "timeweb", "Timeweb.Cloud"],
    "Raft": ["Raft", "Рафт", "RAFT"],
    "GWPro": ["GWPro", "GW Pro", "СИО", "GWpro"],
    "CloudBuying": ["CloudBuying", "Cloud Buying", "Cloudbying"],
    "Stool Group": ["Stool Group", "Stool group", "StoolGroup", "Толстов"],
    "Lunas": ["Lunas", "LUNAS", "Soppa"],
    "Indigo": ["Indigo", "INDIGO", "индиго"],
    "Internet Services": ["Internet Services", "AI Surfers & Internet"],
    "SMS Aero": ["SMS Aero", "СМС Аеро", "SMS-Aero", "SMSAero"],
    "Yandex": ["Yandex", "Яндекс", "yandex"],
    "Litnet": ["Litnet", "LITNET", "litnet"],
}

# Минимальное количество упоминаний в транскрипте для уверенной связи
MIN_MENTIONS_IN_TRANSCRIPT = 3


def normalize_client_name(name: str) -> str | None:
    """Найти canonical имя клиента по алиасу"""
    name_lower = name.lower()
    for canonical, aliases in KNOWN_CLIENTS.items():
        for alias in aliases:
            if alias.lower() in name_lower:
                return canonical
    return None


def find_client_in_text(text: str, client_aliases: list[str]) -> int:
    """Подсчитать количество упоминаний клиента в тексте"""
    if not text:
        return 0

    count = 0
    text_lower = text.lower()
    for alias in client_aliases:
        # Используем word boundaries для точного поиска
        pattern = r'\b' + re.escape(alias.lower()) + r'\b'
        matches = re.findall(pattern, text_lower)
        count += len(matches)

    return count


async def get_telegram_client_names(session: AsyncSession) -> dict[str, str]:
    """Получить client_name из Telegram чатов"""
    result = await session.execute(
        select(TelegramChat.client_name).where(TelegramChat.client_name.isnot(None))
    )
    names = {}
    for row in result.fetchall():
        client_name = row[0]
        # Пробуем нормализовать
        canonical = normalize_client_name(client_name)
        if canonical:
            names[client_name] = canonical
        else:
            # Добавляем как есть
            names[client_name] = client_name
    return names


async def analyze_meetings(session: AsyncSession) -> tuple[list, list]:
    """
    Анализировать все встречи и разделить на очевидные и неочевидные.

    Returns:
        (confident_matches, uncertain_matches)
    """
    # Получаем все встречи
    result = await session.execute(
        select(Meeting.id, Meeting.title, Meeting.transcript, Meeting.date)
        .where(Meeting.client_id.is_(None))  # Только несвязанные
    )
    meetings = result.fetchall()

    confident = []  # (meeting_id, client_name, method)
    uncertain = []  # (meeting_id, title, date, reason)

    for meeting_id, title, transcript, date in meetings:
        matched_client = None
        match_method = None

        # 1. Проверяем название встречи
        for canonical, aliases in KNOWN_CLIENTS.items():
            for alias in aliases:
                if alias.lower() in (title or "").lower():
                    matched_client = canonical
                    match_method = "title"
                    break
            if matched_client:
                break

        # 2. Если не нашли в названии, проверяем транскрипт
        if not matched_client and transcript:
            best_client = None
            best_count = 0

            for canonical, aliases in KNOWN_CLIENTS.items():
                count = find_client_in_text(transcript, aliases)
                if count > best_count:
                    best_count = count
                    best_client = canonical

            if best_count >= MIN_MENTIONS_IN_TRANSCRIPT:
                matched_client = best_client
                match_method = f"transcript({best_count})"

        # Классифицируем
        if matched_client:
            confident.append((meeting_id, matched_client, match_method))
        else:
            reason = "no_match"
            if not transcript:
                reason = "no_transcript"
            uncertain.append((meeting_id, title, date, reason))

    return confident, uncertain


async def preview(session: AsyncSession):
    """Показать предпросмотр умного связывания"""

    print("\n" + "=" * 80)
    print("ПРЕДПРОСМОТР: Умное связывание клиентов")
    print("=" * 80)

    # Анализируем
    confident, uncertain = await analyze_meetings(session)

    # Группируем confident по клиентам
    client_stats = defaultdict(lambda: {"count": 0, "methods": defaultdict(int)})
    for _, client_name, method in confident:
        client_stats[client_name]["count"] += 1
        client_stats[client_name]["methods"][method.split("(")[0]] += 1

    print(f"\n{'ОЧЕВИДНЫЕ СВЯЗИ (высокая уверенность)':^80}")
    print("-" * 80)
    print(f"{'Клиент':<25} {'Встреч':>10} {'По title':>12} {'По тексту':>12}")
    print("-" * 80)

    total_confident = 0
    for client_name in sorted(client_stats.keys()):
        stats = client_stats[client_name]
        total_confident += stats["count"]
        by_title = stats["methods"].get("title", 0)
        by_text = stats["methods"].get("transcript", 0)
        print(f"{client_name:<25} {stats['count']:>10} {by_title:>12} {by_text:>12}")

    print("-" * 80)
    print(f"{'ИТОГО очевидных:':<25} {total_confident:>10}")

    # Статистика по неочевидным
    uncertain_by_reason = defaultdict(int)
    for _, _, _, reason in uncertain:
        uncertain_by_reason[reason] += 1

    print(f"\n{'НА ПРОВЕРКУ (требуется ручная валидация)':^80}")
    print("-" * 80)
    print(f"Всего неочевидных: {len(uncertain)}")
    for reason, count in sorted(uncertain_by_reason.items()):
        reason_label = {
            "no_match": "Нет совпадений с известными клиентами",
            "no_transcript": "Нет транскрипта",
        }.get(reason, reason)
        print(f"  - {reason_label}: {count}")

    # Примеры неочевидных
    print(f"\nПримеры неочевидных (первые 10):")
    for _, title, date, reason in uncertain[:10]:
        date_str = date.strftime("%Y-%m-%d") if date else "?"
        print(f"  [{date_str}] {title[:60]}...")

    print("\n" + "=" * 80)
    print("Команды:")
    print("  --apply-confident   Применить только очевидные связи")
    print("  --export-uncertain  Экспортировать неочевидные в CSV")
    print("=" * 80)


async def apply_confident(session: AsyncSession):
    """Применить только очевидные связи"""

    print("\n" + "=" * 80)
    print("ПРИМЕНЕНИЕ: Очевидные связи")
    print("=" * 80)

    # 1. Создаём клиентов из KNOWN_CLIENTS
    print("\n1. Создание клиентов...")
    created_count = 0
    client_map = {}  # name -> id

    for canonical_name in KNOWN_CLIENTS.keys():
        result = await session.execute(
            select(Client).where(Client.name == canonical_name)
        )
        existing = result.scalar_one_or_none()

        if existing:
            client_map[canonical_name] = existing.id
        else:
            client = Client(name=canonical_name)
            session.add(client)
            await session.flush()
            client_map[canonical_name] = client.id
            created_count += 1

    await session.commit()
    print(f"   Создано новых клиентов: {created_count}")

    # 2. Анализируем и связываем
    confident, uncertain = await analyze_meetings(session)

    print(f"\n2. Связывание очевидных встреч...")
    linked_count = 0

    for meeting_id, client_name, method in confident:
        if client_name in client_map:
            await session.execute(
                update(Meeting)
                .where(Meeting.id == meeting_id)
                .values(client_id=client_map[client_name])
            )
            linked_count += 1

    await session.commit()
    print(f"   Связано встреч: {linked_count}")

    # 3. Связываем Telegram чаты
    print(f"\n3. Связывание Telegram чатов...")
    result = await session.execute(
        select(TelegramChat.id, TelegramChat.client_name)
        .where(TelegramChat.client_id.is_(None))
    )
    chats = result.fetchall()

    chat_linked = 0
    for chat_id, client_name in chats:
        if client_name:
            canonical = normalize_client_name(client_name)
            if canonical and canonical in client_map:
                await session.execute(
                    update(TelegramChat)
                    .where(TelegramChat.id == chat_id)
                    .values(client_id=client_map[canonical])
                )
                chat_linked += 1

    await session.commit()
    print(f"   Связано чатов: {chat_linked}")

    # Итоги
    print("\n" + "=" * 80)
    print("ИТОГО:")
    print(f"   Клиентов создано: {created_count}")
    print(f"   Встреч связано: {linked_count}")
    print(f"   Чатов связано: {chat_linked}")
    print(f"   Встреч на проверку: {len(uncertain)}")
    print("=" * 80)


async def export_uncertain(session: AsyncSession):
    """Экспортировать неочевидные встречи в CSV"""

    confident, uncertain = await analyze_meetings(session)

    output_file = Path("unlinked_meetings.csv")

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["meeting_id", "title", "date", "reason"])

        for meeting_id, title, date, reason in uncertain:
            date_str = date.strftime("%Y-%m-%d %H:%M") if date else ""
            writer.writerow([str(meeting_id), title, date_str, reason])

    print(f"\nЭкспортировано {len(uncertain)} встреч в {output_file}")
    print(f"Очевидных связей (не экспортировано): {len(confident)}")


async def main(args):
    settings = get_settings()

    db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        if args.preview:
            await preview(session)
        elif args.apply_confident:
            await apply_confident(session)
        elif args.export_uncertain:
            await export_uncertain(session)
        else:
            print("Укажите режим:")
            print("  --preview           Показать предпросмотр")
            print("  --apply-confident   Применить очевидные связи")
            print("  --export-uncertain  Экспорт неочевидных в CSV")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Умное связывание клиентов с встречами"
    )
    parser.add_argument("--preview", action="store_true", help="Предпросмотр")
    parser.add_argument("--apply-confident", action="store_true", help="Применить очевидные")
    parser.add_argument("--export-uncertain", action="store_true", help="Экспорт неочевидных")
    args = parser.parse_args()

    asyncio.run(main(args))
