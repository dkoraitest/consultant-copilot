"""
Pytest fixtures
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.database.models import Base


@pytest_asyncio.fixture
async def db_session():
    """Тестовая сессия БД (in-memory SQLite)"""
    # Для тестов используем SQLite
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def sample_transcript():
    """Пример транскрипта для тестов"""
    return """
    Дима: Привет всем, давайте начнем встречу.
    Алексей: Привет! Готов обсудить новый проект.
    Дима: Отлично. Первый вопрос - сроки MVP.
    Алексей: Думаю, 2-3 недели реально.
    Дима: Договорились. Задача на тебе - подготовить план.
    Алексей: Сделаю к пятнице.
    Дима: Отлично. Следующий вопрос - бюджет.
    Алексей: По бюджету есть ограничения?
    Дима: Да, максимум 500 тысяч на MVP.
    Алексей: Понял, уложимся.
    """


@pytest.fixture
def sample_hypothesis_data():
    """Пример данных гипотезы"""
    return {
        "title": "Увеличение конверсии лендинга",
        "description": "Если добавить видео на главную, конверсия вырастет на 20%",
        "success_criteria": {
            "metric": "конверсия",
            "target": ">5%",
            "baseline": "4.2%"
        },
        "quarter": "Q1 2026"
    }
