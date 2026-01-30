"""
Тесты для repository
"""
import pytest
from uuid import uuid4

from src.database.repository import (
    MeetingRepository,
    ClientRepository,
    HypothesisRepository,
    SummaryRepository,
)


@pytest.mark.asyncio
async def test_create_meeting(db_session):
    """Тест создания встречи"""
    repo = MeetingRepository(db_session)

    meeting = await repo.create(
        title="Test Meeting",
        fireflies_id="ff_123",
        transcript="Hello world",
    )

    assert meeting.id is not None
    assert meeting.title == "Test Meeting"
    assert meeting.fireflies_id == "ff_123"


@pytest.mark.asyncio
async def test_get_meeting_by_fireflies_id(db_session):
    """Тест получения встречи по Fireflies ID"""
    repo = MeetingRepository(db_session)

    await repo.create(
        title="Test Meeting",
        fireflies_id="ff_456",
    )

    meeting = await repo.get_by_fireflies_id("ff_456")
    assert meeting is not None
    assert meeting.title == "Test Meeting"


@pytest.mark.asyncio
async def test_list_recent_meetings(db_session):
    """Тест списка недавних встреч"""
    repo = MeetingRepository(db_session)

    # Создаём несколько встреч
    for i in range(5):
        await repo.create(title=f"Meeting {i}")

    meetings = await repo.list_recent(limit=3)
    assert len(meetings) == 3


@pytest.mark.asyncio
async def test_create_client(db_session):
    """Тест создания клиента"""
    repo = ClientRepository(db_session)

    client = await repo.create(
        name="Test Client",
        telegram_chat_id=123456789,
    )

    assert client.id is not None
    assert client.name == "Test Client"


@pytest.mark.asyncio
async def test_create_hypothesis(db_session, sample_hypothesis_data):
    """Тест создания гипотезы"""
    client_repo = ClientRepository(db_session)
    hypothesis_repo = HypothesisRepository(db_session)

    # Создаём клиента
    client = await client_repo.create(name="Test Client")

    # Создаём гипотезу
    hypothesis = await hypothesis_repo.create(
        client_id=client.id,
        **sample_hypothesis_data
    )

    assert hypothesis.id is not None
    assert hypothesis.title == sample_hypothesis_data["title"]
    assert hypothesis.status == "active"
    assert hypothesis.quarter == "Q1 2026"


@pytest.mark.asyncio
async def test_update_hypothesis_status(db_session, sample_hypothesis_data):
    """Тест обновления статуса гипотезы"""
    client_repo = ClientRepository(db_session)
    hypothesis_repo = HypothesisRepository(db_session)

    client = await client_repo.create(name="Test Client")
    hypothesis = await hypothesis_repo.create(
        client_id=client.id,
        **sample_hypothesis_data
    )

    # Обновляем статус
    updated = await hypothesis_repo.update_status(
        hypothesis_id=hypothesis.id,
        status="validated",
        result_text="Конверсия выросла до 6.5%",
        result_data={"actual": "6.5%", "delta": "+2.3%"}
    )

    assert updated.status == "validated"
    assert updated.result == "Конверсия выросла до 6.5%"
    assert updated.tested_at is not None


@pytest.mark.asyncio
async def test_list_hypotheses_by_quarter(db_session, sample_hypothesis_data):
    """Тест списка гипотез по кварталу"""
    client_repo = ClientRepository(db_session)
    hypothesis_repo = HypothesisRepository(db_session)

    client = await client_repo.create(name="Test Client")

    # Создаём несколько гипотез
    for i in range(3):
        await hypothesis_repo.create(
            client_id=client.id,
            title=f"Hypothesis {i}",
            quarter="Q1 2026"
        )

    await hypothesis_repo.create(
        client_id=client.id,
        title="Q2 Hypothesis",
        quarter="Q2 2026"
    )

    q1_hypotheses = await hypothesis_repo.list_by_quarter("Q1 2026")
    assert len(q1_hypotheses) == 3


@pytest.mark.asyncio
async def test_quarterly_stats(db_session, sample_hypothesis_data):
    """Тест статистики по кварталу"""
    client_repo = ClientRepository(db_session)
    hypothesis_repo = HypothesisRepository(db_session)

    client = await client_repo.create(name="Test Client")

    # Создаём гипотезы с разными статусами
    h1 = await hypothesis_repo.create(
        client_id=client.id,
        title="Hypothesis 1",
        quarter="Q1 2026"
    )
    await hypothesis_repo.update_status(h1.id, "validated")

    h2 = await hypothesis_repo.create(
        client_id=client.id,
        title="Hypothesis 2",
        quarter="Q1 2026"
    )
    await hypothesis_repo.update_status(h2.id, "failed")

    await hypothesis_repo.create(
        client_id=client.id,
        title="Hypothesis 3",
        quarter="Q1 2026"
    )

    stats = await hypothesis_repo.get_quarterly_stats("Q1 2026")

    assert stats["total"] == 3
    assert stats["validated"] == 1
    assert stats["failed"] == 1
    assert stats["active"] == 1
    assert stats["success_rate"] == 50.0


@pytest.mark.asyncio
async def test_create_summary(db_session):
    """Тест создания саммари"""
    meeting_repo = MeetingRepository(db_session)
    summary_repo = SummaryRepository(db_session)

    meeting = await meeting_repo.create(
        title="Test Meeting",
        transcript="Some transcript"
    )

    summary = await summary_repo.create(
        meeting_id=meeting.id,
        meeting_type="working_meeting",
        content_text="Summary text",
        content_json={"key": "value"}
    )

    assert summary.id is not None
    assert summary.meeting_type == "working_meeting"
    assert summary.content_json == {"key": "value"}
