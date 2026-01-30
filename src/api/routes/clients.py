"""
API routes для клиентов
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import get_session
from src.database.repository import ClientRepository, MeetingRepository, HypothesisRepository

router = APIRouter()


class ClientCreate(BaseModel):
    name: str
    telegram_chat_id: int | None = None
    todoist_project_id: str | None = None


class ClientResponse(BaseModel):
    id: UUID
    name: str
    telegram_chat_id: int | None
    todoist_project_id: str | None

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[ClientResponse])
async def list_clients(session: AsyncSession = Depends(get_session)):
    """Получить список клиентов"""
    repo = ClientRepository(session)
    clients = await repo.list_all()
    return clients


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Получить клиента по ID"""
    repo = ClientRepository(session)
    client = await repo.get_by_id(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.post("/", response_model=ClientResponse)
async def create_client(
    data: ClientCreate,
    session: AsyncSession = Depends(get_session),
):
    """Создать клиента"""
    repo = ClientRepository(session)
    client = await repo.create(
        name=data.name,
        telegram_chat_id=data.telegram_chat_id,
        todoist_project_id=data.todoist_project_id,
    )
    return client


@router.get("/{client_id}/meetings")
async def get_client_meetings(
    client_id: UUID,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    """Получить встречи клиента"""
    repo = MeetingRepository(session)
    meetings = await repo.list_by_client(client_id, limit)
    return meetings


@router.get("/{client_id}/hypotheses")
async def get_client_hypotheses(
    client_id: UUID,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Получить гипотезы клиента"""
    repo = HypothesisRepository(session)
    hypotheses = await repo.list_by_client(client_id, status)
    return hypotheses
