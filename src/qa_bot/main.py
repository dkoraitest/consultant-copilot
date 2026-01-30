"""
Q&A Telegram Bot - точка входа
"""
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from src.config import get_settings
from src.qa_bot.handlers import (
    start_handler,
    help_handler,
    stats_handler,
    question_handler,
    error_handler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Запуск Q&A бота"""
    settings = get_settings()

    if not settings.qa_bot_token:
        logger.error("QA_BOT_TOKEN not set in environment")
        return

    # Создание приложения
    application = Application.builder().token(settings.qa_bot_token).build()

    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("stats", stats_handler))

    # Обработчик текстовых сообщений (вопросы)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, question_handler)
    )

    # Обработчик ошибок
    application.add_error_handler(error_handler)

    # Запуск
    logger.info("Starting Q&A bot...")
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
