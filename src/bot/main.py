"""
Telegram Bot - точка входа
"""
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from src.config import get_settings
from src.bot.handlers import (
    start_handler,
    help_handler,
    meeting_type_callback,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Запуск бота"""
    settings = get_settings()

    # Создание приложения
    application = Application.builder().token(settings.telegram_bot_token).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CallbackQueryHandler(meeting_type_callback, pattern="^type:"))

    # Запуск
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
