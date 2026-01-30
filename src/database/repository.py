"""
Repository pattern для работы с БД
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Meeting, Summary, Client, Lead, Hypothesis


class MeetingRepository:
    """CRUD операции для встреч"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        title: str,
        fireflies_id: str | None = None,
        date: datetime | None = None,
        transcript: str | None = None,
        client_id: UUID | None = None,
        meeting_type: str | None = None,
    ) -> Meeting:
        meeting = Meeting(
            title=title,
            fireflies_id=fireflies_id,
            date=date,
            transcript=transcript,
            client_id=client_id,
            meeting_type=meeting_type,
        )
        self.session.add(meeting)
        await self.session.commit()
        await self.session.refresh(meeting)
        return meeting

    async def get_by_id(self, meeting_id: UUID) -> Meeting | None:
        result = await self.session.execute(
            select(Meeting).where(Meeting.id == meeting_id)
        )
        return result.scalar_one_or_none()

    async def get_by_fireflies_id(self, fireflies_id: str) -> Meeting | None:
        result = await self.session.execute(
            select(Meeting).where(Meeting.fireflies_id == fireflies_id)
        )
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 20) -> list[Meeting]:
        result = await self.session.execute(
            select(Meeting).order_by(Meeting.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_client(self, client_id: UUID, limit: int = 50) -> list[Meeting]:
        result = await self.session.execute(
            select(Meeting)
            .where(Meeting.client_id == client_id)
            .order_by(Meeting.date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_type(self, meeting_id: UUID, meeting_type: str) -> Meeting | None:
        await self.session.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id)
            .values(meeting_type=meeting_type)
        )
        await self.session.commit()
        return await self.get_by_id(meeting_id)


class SummaryRepository:
    """CRUD операции для саммари"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        meeting_id: UUID,
        meeting_type: str,
        content_text: str,
        content_json: dict | None = None,
    ) -> Summary:
        summary = Summary(
            meeting_id=meeting_id,
            meeting_type=meeting_type,
            content_text=content_text,
            content_json=content_json,
        )
        self.session.add(summary)
        await self.session.commit()
        await self.session.refresh(summary)
        return summary

    async def get_by_meeting(self, meeting_id: UUID) -> list[Summary]:
        result = await self.session.execute(
            select(Summary).where(Summary.meeting_id == meeting_id)
        )
        return list(result.scalars().all())

    async def get_latest_by_meeting(self, meeting_id: UUID) -> Summary | None:
        result = await self.session.execute(
            select(Summary)
            .where(Summary.meeting_id == meeting_id)
            .order_by(Summary.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class ClientRepository:
    """CRUD операции для клиентов"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        name: str,
        telegram_chat_id: int | None = None,
        todoist_project_id: str | None = None,
    ) -> Client:
        client = Client(
            name=name,
            telegram_chat_id=telegram_chat_id,
            todoist_project_id=todoist_project_id,
        )
        self.session.add(client)
        await self.session.commit()
        await self.session.refresh(client)
        return client

    async def get_by_id(self, client_id: UUID) -> Client | None:
        result = await self.session.execute(
            select(Client).where(Client.id == client_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Client | None:
        result = await self.session.execute(
            select(Client).where(Client.name == name)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Client]:
        result = await self.session.execute(
            select(Client).order_by(Client.name)
        )
        return list(result.scalars().all())


class LeadRepository:
    """CRUD операции для лидов"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        client_name: str,
        client_tg: str | None = None,
        message: str | None = None,
        channel: str | None = None,
    ) -> Lead:
        lead = Lead(
            client_name=client_name,
            client_tg=client_tg,
            message=message,
            channel=channel,
        )
        self.session.add(lead)
        await self.session.commit()
        await self.session.refresh(lead)
        return lead

    async def update_status(self, lead_id: UUID, status: str) -> Lead | None:
        await self.session.execute(
            update(Lead).where(Lead.id == lead_id).values(status=status)
        )
        await self.session.commit()
        result = await self.session.execute(
            select(Lead).where(Lead.id == lead_id)
        )
        return result.scalar_one_or_none()

    async def list_by_status(self, status: str) -> list[Lead]:
        result = await self.session.execute(
            select(Lead).where(Lead.status == status).order_by(Lead.created_at.desc())
        )
        return list(result.scalars().all())


class HypothesisRepository:
    """CRUD операции для гипотез"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        client_id: UUID,
        title: str,
        description: str | None = None,
        success_criteria: dict | None = None,
        quarter: str | None = None,
        meeting_id: UUID | None = None,
    ) -> Hypothesis:
        hypothesis = Hypothesis(
            client_id=client_id,
            title=title,
            description=description,
            success_criteria=success_criteria,
            quarter=quarter,
            meeting_id=meeting_id,
        )
        self.session.add(hypothesis)
        await self.session.commit()
        await self.session.refresh(hypothesis)
        return hypothesis

    async def get_by_id(self, hypothesis_id: UUID) -> Hypothesis | None:
        result = await self.session.execute(
            select(Hypothesis).where(Hypothesis.id == hypothesis_id)
        )
        return result.scalar_one_or_none()

    async def list_by_client(
        self,
        client_id: UUID,
        status: str | None = None,
    ) -> list[Hypothesis]:
        query = select(Hypothesis).where(Hypothesis.client_id == client_id)
        if status:
            query = query.where(Hypothesis.status == status)
        query = query.order_by(Hypothesis.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_by_quarter(
        self,
        quarter: str,
        client_id: UUID | None = None,
    ) -> list[Hypothesis]:
        query = select(Hypothesis).where(Hypothesis.quarter == quarter)
        if client_id:
            query = query.where(Hypothesis.client_id == client_id)
        query = query.order_by(Hypothesis.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_by_status(self, status: str) -> list[Hypothesis]:
        result = await self.session.execute(
            select(Hypothesis)
            .where(Hypothesis.status == status)
            .order_by(Hypothesis.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_active(self, limit: int = 20) -> list[Hypothesis]:
        """Список активных гипотез (active и testing)"""
        result = await self.session.execute(
            select(Hypothesis)
            .where(Hypothesis.status.in_(["active", "testing"]))
            .order_by(Hypothesis.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        hypothesis_id: UUID,
        status: str,
        result_text: str | None = None,
        result_data: dict | None = None,
    ) -> Hypothesis | None:
        values = {"status": status}
        if result_text:
            values["result"] = result_text
        if result_data:
            values["result_data"] = result_data
        if status in ("validated", "failed"):
            values["tested_at"] = datetime.utcnow()

        await self.session.execute(
            update(Hypothesis)
            .where(Hypothesis.id == hypothesis_id)
            .values(**values)
        )
        await self.session.commit()
        return await self.get_by_id(hypothesis_id)

    async def get_quarterly_stats(self, quarter: str) -> dict:
        """Статистика по гипотезам за квартал"""
        hypotheses = await self.list_by_quarter(quarter)

        stats = {
            "quarter": quarter,
            "total": len(hypotheses),
            "active": 0,
            "testing": 0,
            "validated": 0,
            "failed": 0,
            "paused": 0,
        }

        for h in hypotheses:
            if h.status in stats:
                stats[h.status] += 1

        stats["success_rate"] = (
            round(stats["validated"] / (stats["validated"] + stats["failed"]) * 100, 1)
            if (stats["validated"] + stats["failed"]) > 0
            else 0
        )

        return stats
