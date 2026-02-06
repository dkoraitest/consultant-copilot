"""
Обработчики сообщений Q&A бота
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.database.connection import async_session_maker
from src.services.rag_service import RAGService
from src.database.repository import EmbeddingRepository

logger = logging.getLogger(__name__)


WELCOME_MESSAGE = """👋 Привет! Я Q&A бот Consultant Copilot.

Задайте вопрос, и я найду ответ в транскриптах встреч и переписке в Telegram.

*Примеры вопросов:*
• Какие гипотезы обсуждались с клиентом X?
• Что решили по продукту на прошлой неделе?
• Какие метрики упоминались?
• О чём говорили на встрече с Y?
• Что обсуждали в чате с CloudBuying?

Просто напишите свой вопрос 👇"""


HELP_MESSAGE = """*Как пользоваться ботом:*

1. Просто напишите вопрос
2. Бот найдёт релевантные фрагменты из транскриптов
3. Claude сформирует ответ на основе найденного

*Команды:*
/start — начать работу
/help — эта справка
/stats — статистика индекса

*Совет:* Чем конкретнее вопрос, тем точнее ответ."""


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode="Markdown"
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        HELP_MESSAGE,
        parse_mode="Markdown"
    )


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats"""
    try:
        async with async_session_maker() as session:
            repo = EmbeddingRepository(session)
            stats = await repo.stats()

        await update.message.reply_text(
            f"📊 *Статистика индекса:*\n\n"
            f"Проиндексировано встреч: {stats['indexed_meetings']}\n"
            f"Всего чанков: {stats['total_chunks']}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in stats: {e}")
        await update.message.reply_text("Ошибка при получении статистики.")


async def question_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка вопросов пользователя"""
    question = update.message.text

    if not question or len(question) < 3:
        await update.message.reply_text(
            "Пожалуйста, задайте более развёрнутый вопрос."
        )
        return

    # Показываем, что бот думает
    thinking_msg = await update.message.reply_text("🔍 Ищу ответ в транскриптах и Telegram...")

    try:
        async with async_session_maker() as session:
            rag = RAGService(session)
            answer, meeting_sources, telegram_sources = await rag.ask(question)

        # Формируем ответ
        response = answer

        # Добавляем источники из встреч
        if meeting_sources:
            response += "\n\n📚 Встречи:"
            seen_titles = set()
            for s in meeting_sources:
                if s.meeting_title not in seen_titles:
                    seen_titles.add(s.meeting_title)
                    date_str = f" ({s.meeting_date[:10]})" if s.meeting_date else ""
                    response += f"\n• {s.meeting_title}{date_str}"

        # Добавляем источники из Telegram
        if telegram_sources:
            response += "\n\n💬 Telegram:"
            seen_chats = set()
            for s in telegram_sources:
                if s.chat_title not in seen_chats:
                    seen_chats.add(s.chat_title)
                    client = f" ({s.client_name})" if s.client_name else ""
                    response += f"\n• {s.chat_title}{client}"

        # Удаляем сообщение "Ищу ответ..."
        try:
            await thinking_msg.delete()
        except Exception:
            pass

        # Отправляем ответ (без parse_mode, т.к. Claude может вернуть символы
        # которые конфликтуют с Telegram Markdown парсером)
        # Разбиваем на части если ответ слишком длинный (лимит Telegram 4096)
        if len(response) <= 4096:
            await update.message.reply_text(response)
        else:
            for i in range(0, len(response), 4096):
                await update.message.reply_text(response[i:i+4096])

    except Exception as e:
        logger.error(f"Error answering question: {e}")
        try:
            await thinking_msg.edit_text(
                f"❌ Ошибка при обработке вопроса. Попробуйте позже.\n\nДетали: {str(e)[:100]}"
            )
        except Exception:
            await update.message.reply_text(
                f"❌ Ошибка при обработке вопроса. Попробуйте позже."
            )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Exception while handling an update: {context.error}")
