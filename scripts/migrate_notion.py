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
from datetime import datetime

from notion_client import Client as NotionClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()


# Настройки
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "dafded61cc2b4fc0997c292359f6e489")
DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")


async def fetch_notion_pages(notion: NotionClient, database_id: str) -> list:
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
    blocks = notion.blocks.children.list(block_id=page_id)
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

        elif block_type == "bulleted_list_item":
            texts = block["bulleted_list_item"].get("rich_text", [])
            content_parts.append("• " + "".join(t["plain_text"] for t in texts))

    return "\n".join(content_parts)


def parse_notion_page(page: dict, notion: NotionClient) -> dict:
    """Парсинг страницы Notion в данные встречи"""
    properties = page["properties"]

    # Извлекаем поля
    title = ""
    if "Meeting Name" in properties:
        title_prop = properties["Meeting Name"]
        if title_prop["type"] == "title":
            title = "".join(t["plain_text"] for t in title_prop["title"])

    meeting_date = None
    if "Meeting Date" in properties:
        date_prop = properties["Meeting Date"]
        if date_prop["type"] == "date" and date_prop["date"]:
            meeting_date = datetime.fromisoformat(date_prop["date"]["start"])

    fireflies_id = None
    if "Transcript ID" in properties:
        id_prop = properties["Transcript ID"]
        if id_prop["type"] == "rich_text" and id_prop["rich_text"]:
            fireflies_id = id_prop["rich_text"][0]["plain_text"]

    # Получаем содержимое страницы (транскрипт)
    transcript = extract_page_content(notion, page["id"])

    return {
        "title": title,
        "date": meeting_date,
        "fireflies_id": fireflies_id,
        "transcript": transcript,
        "notion_id": page["id"]
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
    print("Загрузка страниц...")
    pages = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: fetch_notion_pages(notion, NOTION_DATABASE_ID)
    )
    print(f"Найдено страниц: {len(pages)}")

    # Подключение к PostgreSQL
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Миграция
    migrated = 0
    errors = 0

    for i, page in enumerate(pages, 1):
        try:
            data = parse_notion_page(page, notion)
            print(f"[{i}/{len(pages)}] {data['title'][:50]}...")

            # TODO: Сохранение в БД
            # async with async_session() as session:
            #     meeting = Meeting(**data)
            #     session.add(meeting)
            #     await session.commit()

            migrated += 1

        except Exception as e:
            print(f"  Ошибка: {e}")
            errors += 1

    print()
    print("=" * 50)
    print(f"Миграция завершена")
    print(f"Успешно: {migrated}")
    print(f"Ошибок: {errors}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(migrate())
