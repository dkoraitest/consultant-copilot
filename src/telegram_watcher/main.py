"""
Telegram Watcher — точка входа.

Запускает persistent Telethon client с event handlers
для real-time синхронизации новых сообщений.

Использование:
    python -m src.telegram_watcher.main
"""
import asyncio
import logging
import signal
import sys

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from src.config import get_settings
from src.database.connection import async_session_maker
from src.telegram_watcher.handlers import MessageHandler
from src.telegram_watcher.catchup import CatchupService

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Основная функция запуска watcher"""
    settings = get_settings()

    # Проверяем наличие credentials
    if not all([
        settings.telegram_api_id,
        settings.telegram_api_hash,
        settings.telegram_session
    ]):
        logger.error(
            "Missing Telegram credentials. Set TELEGRAM_API_ID, "
            "TELEGRAM_API_HASH, TELEGRAM_SESSION in .env"
        )
        sys.exit(1)

    logger.info("Starting Telegram Watcher...")

    # Создаём Telethon клиент
    client = TelegramClient(
        StringSession(settings.telegram_session),
        settings.telegram_api_id,
        settings.telegram_api_hash
    )

    handler = MessageHandler()
    catchup = CatchupService(client, handler)

    # Получаем список chat_id для мониторинга
    async with async_session_maker() as session:
        chat_ids = await handler.get_active_chat_ids(session)

    if not chat_ids:
        logger.warning("No active chats found for monitoring")

    logger.info(f"Will monitor {len(chat_ids)} chats: {chat_ids}")

    # Регистрируем event handler для новых сообщений
    @client.on(events.NewMessage(chats=chat_ids))
    async def on_new_message(event):
        """Обработчик новых сообщений (real-time)"""
        try:
            await handler.process_message(event)
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    # Подключаемся
    await client.start()

    me = await client.get_me()
    logger.info(f"Connected as: {me.first_name} (@{me.username})")
    logger.info(f"Watcher started for {len(chat_ids)} chats")

    # Запускаем периодический catch-up в фоне
    catchup_task = asyncio.create_task(catchup.run_periodic_catchup())

    # Сразу делаем catch-up при старте
    logger.info("Running initial catchup...")
    await catchup.catchup_all_chats()
    logger.info("Initial catchup completed")

    # Graceful shutdown
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows не поддерживает add_signal_handler
            pass

    # Ждём сигнала остановки
    logger.info("Watcher is running. Press Ctrl+C to stop.")
    await stop_event.wait()

    # Cleanup
    logger.info("Shutting down...")
    catchup_task.cancel()
    try:
        await catchup_task
    except asyncio.CancelledError:
        pass

    await client.disconnect()
    logger.info("Watcher stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
