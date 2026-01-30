"""
Конфигурация приложения из переменных окружения
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Настройки приложения"""

    # Database
    database_url: str

    # Telegram Bot
    telegram_bot_token: str
    telegram_admin_chat_id: int

    # Telegram User API (Telethon)
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session: str | None = None

    # Fireflies
    fireflies_api_key: str | None = None

    # Todoist
    todoist_api_token: str | None = None
    todoist_default_project_id: str | None = None

    # Claude API
    anthropic_api_key: str

    # OpenAI (для эмбеддингов)
    openai_api_key: str | None = None

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    webhook_url: str | None = None

    # Notion (для миграции)
    notion_token: str | None = None
    notion_database_id: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Получить настройки (кэшируется)"""
    return Settings()
