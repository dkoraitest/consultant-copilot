"""
API routes для саммари
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import get_session
from src.database.repository import MeetingRepository, SummaryRepository
from src.summarizer.engine import SummarizerEngine

router = APIRouter()


class SummaryCreate(BaseModel):
    meeting_id: UUID
    meeting_type: str


class SummaryResponse(BaseModel):
    id: UUID
    meeting_id: UUID
    meeting_type: str
    content_text: str

    model_config = {"from_attributes": True}


@router.post("/generate", response_model=SummaryResponse)
async def generate_summary(
    data: SummaryCreate,
    session: AsyncSession = Depends(get_session),
):
    """Генерировать саммари для встречи"""
    meeting_repo = MeetingRepository(session)
    summary_repo = SummaryRepository(session)

    # Получить встречу
    meeting = await meeting_repo.get_by_id(data.meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if not meeting.transcript:
        raise HTTPException(status_code=400, detail="Meeting has no transcript")

    # Генерировать саммари
    engine = SummarizerEngine()
    result = await engine.summarize(meeting.transcript, data.meeting_type)

    # Сохранить
    summary = await summary_repo.create(
        meeting_id=meeting.id,
        meeting_type=data.meeting_type,
        content_text=result.text,
        content_json=result.json_data,
    )

    # Обновить тип встречи
    await meeting_repo.update_type(meeting.id, data.meeting_type)

    return summary


@router.get("/meeting/{meeting_id}", response_model=list[SummaryResponse])
async def get_meeting_summaries(
    meeting_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Получить саммари для встречи"""
    repo = SummaryRepository(session)
    summaries = await repo.get_by_meeting(meeting_id)
    return summaries
