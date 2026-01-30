"""
API routes для встреч
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import get_session
from src.database.repository import MeetingRepository

router = APIRouter()


class MeetingCreate(BaseModel):
    title: str
    fireflies_id: str | None = None
    transcript: str | None = None
    meeting_type: str | None = None
    client_id: UUID | None = None


class MeetingResponse(BaseModel):
    id: UUID
    title: str
    fireflies_id: str | None
    meeting_type: str | None
    client_id: UUID | None

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[MeetingResponse])
async def list_meetings(
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    """Получить список недавних встреч"""
    repo = MeetingRepository(session)
    meetings = await repo.list_recent(limit)
    return meetings


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Получить встречу по ID"""
    repo = MeetingRepository(session)
    meeting = await repo.get_by_id(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


@router.post("/", response_model=MeetingResponse)
async def create_meeting(
    data: MeetingCreate,
    session: AsyncSession = Depends(get_session),
):
    """Создать встречу"""
    repo = MeetingRepository(session)
    meeting = await repo.create(
        title=data.title,
        fireflies_id=data.fireflies_id,
        transcript=data.transcript,
        meeting_type=data.meeting_type,
        client_id=data.client_id,
    )
    return meeting
