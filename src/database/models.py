"""
SQLAlchemy модели базы данных
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text, DateTime, ForeignKey, BigInteger, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


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


class Embedding(Base):
    """Эмбеддинги чанков транскриптов для RAG"""
    __tablename__ = "embeddings"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    chunk_text: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)
    embedding = mapped_column(Vector(1536))  # OpenAI text-embedding-ada-002
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    meeting: Mapped["Meeting"] = relationship()


# ============================================================================
# Telegram Chat Integration
# ============================================================================

class TelegramChat(Base):
    """Telegram чат для синхронизации"""
    __tablename__ = "telegram_chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram chat_id
    title: Mapped[str] = mapped_column(String(500))
    client_name: Mapped[str | None] = mapped_column(String(255))  # для связи с meetings по title
    last_synced_message_id: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    messages: Mapped[list["TelegramMessage"]] = relationship(back_populates="chat")


class TelegramMessage(Base):
    """Сообщение из Telegram чата"""
    __tablename__ = "telegram_messages"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("telegram_chats.id", ondelete="CASCADE"))
    message_id: Mapped[int] = mapped_column(BigInteger)  # telegram message_id
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sender_name: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str | None] = mapped_column(Text)
    has_media: Mapped[bool] = mapped_column(default=False)
    media_type: Mapped[str | None] = mapped_column(String(50))  # document, photo, video, link
    meeting_id: Mapped[UUID | None] = mapped_column(ForeignKey("meetings.id"))  # если это саммари
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    chat: Mapped["TelegramChat"] = relationship(back_populates="messages")
    meeting: Mapped["Meeting"] = relationship()
    embeddings: Mapped[list["TelegramEmbedding"]] = relationship(back_populates="message")

    __table_args__ = (
        UniqueConstraint("chat_id", "message_id", name="uq_telegram_message"),
    )


class TelegramEmbedding(Base):
    """Эмбеддинги сообщений Telegram для RAG"""
    __tablename__ = "telegram_embeddings"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(ForeignKey("telegram_messages.id", ondelete="CASCADE"))
    chunk_text: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    embedding = mapped_column(Vector(1536))  # OpenAI text-embedding-ada-002
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    message: Mapped["TelegramMessage"] = relationship(back_populates="embeddings")
