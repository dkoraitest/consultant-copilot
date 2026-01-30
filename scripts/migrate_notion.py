"""
Скрипт миграции данных из Notion в PostgreSQL

Запуск:
    python scripts/migrate_notion.py

Требования:
    - NOTION_TOKEN в .env
    - NOTION_DATABASE_ID в .env
    - DATABASE_URL в .env
"""
import asyncio
import os
import sys
from datetime import datetime

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notion_client import Client as NotionClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from dotenv import load_dotenv

from src.database.models import Meeting

load_dotenv()


# Настройки
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "dafded61cc2b4fc0997c292359f6e489")
DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")


def fetch_notion_pages(notion: NotionClient, database_id: str) -> list:
    """Получить все страницы из Notion базы"""
    pages = []
    has_more = True
    start_cursor = None

    while has_more:
        response = notion.databases.query(
            database_id=database_id,
            start_cursor=start_cursor
        )
        pages.extend(response["results"])
        has_more = response["has_more"]
        start_cursor = response.get("next_cursor")

    return pages


def extract_page_content(notion: NotionClient, page_id: str) -> str:
    """Извлечь текстовое содержимое страницы Notion"""
    try:
        blocks = notion.blocks.children.list(block_id=page_id)
    except Exception:
        return ""

    content_parts = []

    for block in blocks["results"]:
        block_type = block["type"]

        if block_type == "paragraph":
            texts = block["paragraph"].get("rich_text", [])
            content_parts.append("".join(t["plain_text"] for t in texts))

        elif block_type == "heading_1":
            texts = block["heading_1"].get("rich_text", [])
            content_parts.append("# " + "".join(t["plain_text"] for t in texts))

        elif block_type == "heading_2":
            texts = block["heading_2"].get("rich_text", [])
            content_parts.append("## " + "".join(t["plain_text"] for t in texts))

        elif block_type == "heading_3":
            texts = block["heading_3"].get("rich_text", [])
            content_parts.append("### " + "".join(t["plain_text"] for t in texts))

        elif block_type == "bulleted_list_item":
            texts = block["bulleted_list_item"].get("rich_text", [])
            content_parts.append("• " + "".join(t["plain_text"] for t in texts))

        elif block_type == "numbered_list_item":
            texts = block["numbered_list_item"].get("rich_text", [])
            content_parts.append("- " + "".join(t["plain_text"] for t in texts))

    return "\n".join(content_parts)


def parse_notion_page(page: dict, notion: NotionClient) -> dict:
    """Парсинг страницы Notion в данные встречи"""
    properties = page["properties"]

    # Извлекаем title - пробуем разные варианты названий полей
    title = ""
    for title_field in ["Meeting Name", "Name", "Title", "Название"]:
        if title_field in properties:
            title_prop = properties[title_field]
            if title_prop["type"] == "title" and title_prop["title"]:
                title = "".join(t["plain_text"] for t in title_prop["title"])
                break

    # Если title пустой, пробуем взять из других полей
    if not title:
        title = f"Meeting from Notion ({page['id'][:8]})"

    # Извлекаем дату
    meeting_date = None
    for date_field in ["Meeting Date", "Date", "Дата"]:
        if date_field in properties:
            date_prop = properties[date_field]
            if date_prop["type"] == "date" and date_prop["date"]:
                try:
                    meeting_date = datetime.fromisoformat(
                        date_prop["date"]["start"].replace("Z", "+00:00")
                    )
                except Exception:
                    pass
                break

    # Извлекаем fireflies_id
    fireflies_id = None
    for id_field in ["Transcript ID", "Fireflies ID", "ID"]:
        if id_field in properties:
            id_prop = properties[id_field]
            if id_prop["type"] == "rich_text" and id_prop["rich_text"]:
                fireflies_id = id_prop["rich_text"][0]["plain_text"]
                break

    # Получаем содержимое страницы (транскрипт)
    transcript = extract_page_content(notion, page["id"])

    return {
        "title": title,
        "date": meeting_date,
        "fireflies_id": fireflies_id,
        "transcript": transcript if transcript else None,
    }


async def migrate():
    """Основная функция миграции"""
    print("=" * 50)
    print("Миграция данных из Notion")
    print("=" * 50)
    print()

    if not NOTION_TOKEN:
        print("Ошибка: NOTION_TOKEN не указан в .env")
        return

    if not DATABASE_URL:
        print("Ошибка: DATABASE_URL не указан в .env")
        return

    # Подключение к Notion
    notion = NotionClient(auth=NOTION_TOKEN)
    print(f"Подключение к Notion базе: {NOTION_DATABASE_ID}")

    # Получение страниц
    print("Загрузка страниц из Notion...")
    loop = asyncio.get_event_loop()
    pages = await loop.run_in_executor(
        None,
        lambda: fetch_notion_pages(notion, NOTION_DATABASE_ID)
    )
    print(f"Найдено страниц: {len(pages)}")
    print()

    # Подключение к PostgreSQL
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Миграция
    migrated = 0
    skipped = 0
    errors = 0

    async with async_session() as session:
        for i, page in enumerate(pages, 1):
            try:
                # Парсим данные из Notion
                data = await loop.run_in_executor(
                    None,
                    lambda p=page: parse_notion_page(p, notion)
                )

                title_short = data['title'][:50] if data['title'] else "Без названия"
                print(f"[{i}/{len(pages)}] {title_short}...", end=" ")

                # Проверяем, не существует ли уже такая встреча
                if data["fireflies_id"]:
                    existing = await session.execute(
                        select(Meeting).where(Meeting.fireflies_id == data["fireflies_id"])
                    )
                    if existing.scalar_one_or_none():
                        print("(пропуск - уже есть)")
                        skipped += 1
                        continue

                # Создаём новую встречу
                meeting = Meeting(
                    title=data["title"],
                    date=data["date"],
                    fireflies_id=data["fireflies_id"],
                    transcript=data["transcript"],
                )
                session.add(meeting)
                await session.commit()

                print("✓")
                migrated += 1

            except Exception as e:
                print(f"✗ Ошибка: {e}")
                errors += 1
                await session.rollback()

    await engine.dispose()

    print()
    print("=" * 50)
    print(f"Миграция завершена")
    print(f"  Добавлено: {migrated}")
    print(f"  Пропущено: {skipped}")
    print(f"  Ошибок: {errors}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(migrate())
