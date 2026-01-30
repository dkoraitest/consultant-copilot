"""
Webhook для Fireflies
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database.connection import get_session
from src.database.repository import MeetingRepository
from src.integrations.fireflies import FirefliesClient

router = APIRouter()
logger = logging.getLogger(__name__)


class FirefliesWebhook(BaseModel):
    meetingId: str
    eventType: str
    clientReferenceId: str | None = None


async def process_fireflies_meeting(
    meeting_id: str,
    session: AsyncSession,
):
    """Фоновая обработка встречи от Fireflies"""
    settings = get_settings()

    try:
        # 1. Получить транскрипт
        fireflies = FirefliesClient()
        transcript_data = await fireflies.get_transcript(meeting_id)

        if not transcript_data:
            logger.error(f"No transcript data for meeting {meeting_id}")
            return

        # 2. Проверить, существует ли уже
        repo = MeetingRepository(session)
        existing = await repo.get_by_fireflies_id(meeting_id)

        if existing:
            logger.info(f"Meeting {meeting_id} already exists")
            return

        # 3. Форматировать транскрипт
        transcript_text = fireflies.format_transcript(transcript_data)

        # 4. Сохранить в БД
        meeting = await repo.create(
            title=transcript_data.get("title", "Untitled Meeting"),
            fireflies_id=meeting_id,
            date=transcript_data.get("date"),
            transcript=transcript_text,
        )

        logger.info(f"Meeting saved: {meeting.id}")

        # 5. TODO: Отправить уведомление в Telegram
        # Здесь можно вызвать функцию отправки в Telegram
        # await send_telegram_notification(meeting.id, meeting.title)

    except Exception as e:
        logger.error(f"Error processing meeting {meeting_id}: {e}")
        raise


@router.post("/fireflies")
async def fireflies_webhook(
    data: FirefliesWebhook,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Принять webhook от Fireflies"""
    logger.info(f"Fireflies webhook: {data.eventType} - {data.meetingId}")

    if data.eventType == "Transcription completed":
        background_tasks.add_task(
            process_fireflies_meeting,
            data.meetingId,
            session,
        )

    return {"status": "ok", "message": "Webhook received"}
