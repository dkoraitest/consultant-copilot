"""
API routes для гипотез
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import get_session
from src.database.repository import HypothesisRepository

router = APIRouter()


class HypothesisCreate(BaseModel):
    client_id: UUID
    title: str
    description: str | None = None
    success_criteria: dict | None = None
    quarter: str | None = None
    meeting_id: UUID | None = None


class HypothesisUpdate(BaseModel):
    status: str
    result: str | None = None
    result_data: dict | None = None


class HypothesisResponse(BaseModel):
    id: UUID
    client_id: UUID
    title: str
    description: str | None
    success_criteria: dict | None
    status: str
    result: str | None
    result_data: dict | None
    quarter: str | None
    meeting_id: UUID | None

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[HypothesisResponse])
async def list_hypotheses(
    status: str | None = None,
    quarter: str | None = None,
    client_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Получить список гипотез с фильтрами"""
    repo = HypothesisRepository(session)

    if quarter:
        hypotheses = await repo.list_by_quarter(quarter, client_id)
    elif status:
        hypotheses = await repo.list_by_status(status)
    elif client_id:
        hypotheses = await repo.list_by_client(client_id)
    else:
        # Получить все активные
        hypotheses = await repo.list_by_status("active")

    return hypotheses


@router.get("/quarter/{quarter}")
async def get_quarterly_stats(
    quarter: str,
    session: AsyncSession = Depends(get_session),
):
    """Получить статистику по гипотезам за квартал"""
    repo = HypothesisRepository(session)
    stats = await repo.get_quarterly_stats(quarter)
    return stats


@router.get("/{hypothesis_id}", response_model=HypothesisResponse)
async def get_hypothesis(
    hypothesis_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Получить гипотезу по ID"""
    repo = HypothesisRepository(session)
    hypothesis = await repo.get_by_id(hypothesis_id)
    if not hypothesis:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    return hypothesis


@router.post("/", response_model=HypothesisResponse)
async def create_hypothesis(
    data: HypothesisCreate,
    session: AsyncSession = Depends(get_session),
):
    """Создать гипотезу"""
    repo = HypothesisRepository(session)
    hypothesis = await repo.create(
        client_id=data.client_id,
        title=data.title,
        description=data.description,
        success_criteria=data.success_criteria,
        quarter=data.quarter,
        meeting_id=data.meeting_id,
    )
    return hypothesis


@router.patch("/{hypothesis_id}", response_model=HypothesisResponse)
async def update_hypothesis_status(
    hypothesis_id: UUID,
    data: HypothesisUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Обновить статус гипотезы"""
    repo = HypothesisRepository(session)

    # Проверить существование
    existing = await repo.get_by_id(hypothesis_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Hypothesis not found")

    # Обновить
    hypothesis = await repo.update_status(
        hypothesis_id=hypothesis_id,
        status=data.status,
        result_text=data.result,
        result_data=data.result_data,
    )
    return hypothesis
