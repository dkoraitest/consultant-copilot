"""
SQLAlchemy модели базы данных
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text, DateTime, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Meeting(Base):
    """Встреча"""
    __tablename__ = "meetings"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    fireflies_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transcript: Mapped[str | None] = mapped_column(Text)
    client_id: Mapped[UUID | None] = mapped_column(ForeignKey("clients.id"))
    meeting_type: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    client: Mapped["Client"] = relationship(back_populates="meetings")
    summaries: Mapped[list["Summary"]] = relationship(back_populates="meeting")


class Summary(Base):
    """Саммари встречи"""
    __tablename__ = "summaries"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id"))
    meeting_type: Mapped[str] = mapped_column(String(50))
    content_text: Mapped[str] = mapped_column(Text)
    content_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    meeting: Mapped["Meeting"] = relationship(back_populates="summaries")


class Client(Base):
    """Клиент"""
    __tablename__ = "clients"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    todoist_project_id: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    meetings: Mapped[list["Meeting"]] = relationship(back_populates="client")
    hypotheses: Mapped[list["Hypothesis"]] = relationship(back_populates="client")


class Lead(Base):
    """Лид (потенциальный клиент)"""
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    client_tg: Mapped[str | None] = mapped_column(String(255))
    client_name: Mapped[str] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Hypothesis(Base):
    """Гипотеза клиента для тестирования"""
    __tablename__ = "hypotheses"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))

    # Описание гипотезы
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)

    # Критерии успеха
    success_criteria: Mapped[dict | None] = mapped_column(JSONB)
    # Пример: {"metric": "конверсия", "target": ">5%", "baseline": "2%"}

    # Статус и результаты
    status: Mapped[str] = mapped_column(String(50), default="active")
    # active, testing, validated, failed, paused
    result: Mapped[str | None] = mapped_column(Text)
    result_data: Mapped[dict | None] = mapped_column(JSONB)
    # Пример: {"actual": "6.2%", "delta": "+4.2%", "conclusion": "успех"}

    # Временные рамки
    quarter: Mapped[str | None] = mapped_column(String(10))  # "Q1 2026"
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Связь с встречей, где гипотеза обсуждалась
    meeting_id: Mapped[UUID | None] = mapped_column(ForeignKey("meetings.id"))

    # Relationships
    client: Mapped["Client"] = relationship(back_populates="hypotheses")
    meeting: Mapped["Meeting"] = relationship()


# Для Этапа 2: Embeddings
# class Embedding(Base):
#     """Эмбеддинги для RAG"""
#     __tablename__ = "embeddings"
#
#     id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
#     meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id"))
#     chunk_text: Mapped[str] = mapped_column(Text)
#     embedding = mapped_column(Vector(1536))  # pgvector
#     chunk_index: Mapped[int] = mapped_column()
#     created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
