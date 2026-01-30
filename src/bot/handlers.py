"""
Обработчики сообщений Telegram бота
"""
import logging
from uuid import UUID

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.keyboards import get_meeting_type_keyboard, get_main_menu_keyboard
from src.database.connection import async_session_maker
from src.database.repository import MeetingRepository, SummaryRepository, HypothesisRepository
from src.summarizer.engine import SummarizerEngine

logger = logging.getLogger(__name__)

# Маппинг типов встреч на читаемые названия
MEETING_TYPE_NAMES = {
    "working_meeting": "Рабочая",
    "diagnostics": "Диагностика",
    "traction": "Трекшн",
    "intro": "Интро",
}


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    keyboard = get_main_menu_keyboard()
    await update.message.reply_text(
        "Привет! Я Consultant Copilot.\n\n"
        "Я помогу создавать саммари встреч.",
        reply_markup=keyboard
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "*Типы встреч:*\n\n"
        "📋 *Рабочая* — внутренняя встреча с командой\n"
        "🔍 *Диагностика* — первая встреча с клиентом\n"
        "📊 *Трекшн* — еженедельный созвон с клиентом\n"
        "👋 *Интро* — первое знакомство\n\n"
        "Саммари генерируется автоматически после получения транскрипта от Fireflies.",
        parse_mode="Markdown"
    )


HELP_TEXT = (
    "*Типы встреч:*\n\n"
    "📋 *Рабочая* — внутренняя встреча с командой\n"
    "🔍 *Диагностика* — первая встреча с клиентом\n"
    "📊 *Трекшн* — еженедельный созвон с клиентом\n"
    "👋 *Интро* — первое знакомство\n\n"
    "Саммари генерируется автоматически после получения транскрипта от Fireflies."
)


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки главного меню"""
    query = update.callback_query
    await query.answer()

    _, action = query.data.split(":")

    if action == "help":
        await query.message.reply_text(HELP_TEXT, parse_mode="Markdown")

    elif action == "hypotheses":
        try:
            async with async_session_maker() as session:
                repo = HypothesisRepository(session)
                hypotheses = await repo.list_active()

                if not hypotheses:
                    await query.message.reply_text("Нет активных гипотез.")
                    return

                text = "*Активные гипотезы:*\n\n"
                for h in hypotheses[:10]:  # Лимит 10
                    status_emoji = {"active": "🟡", "testing": "🔵", "validated": "✅", "failed": "❌"}.get(h.status, "⚪")
                    text += f"{status_emoji} *{h.title}*\n"
                    if h.quarter:
                        text += f"   Квартал: {h.quarter}\n"
                    text += "\n"

                await query.message.reply_text(text, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error fetching hypotheses: {e}")
            await query.message.reply_text("Ошибка при получении гипотез.")


async def send_meeting_notification(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    meeting_id: str,
    meeting_title: str
):
    """Отправить уведомление о новой встрече с кнопками выбора типа"""
    keyboard = get_meeting_type_keyboard(meeting_id)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"*Новая встреча:* {meeting_title}\n\nВыберите тип:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


async def meeting_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора типа встречи"""
    query = update.callback_query
    await query.answer()

    # Парсим callback_data: "type:meeting_type:meeting_id"
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("Ошибка: неверный формат данных")
        return

    _, meeting_type, meeting_id = parts
    type_name = MEETING_TYPE_NAMES.get(meeting_type, meeting_type)

    await query.edit_message_text(f"Генерирую саммари ({type_name})...")

    try:
        async with async_session_maker() as session:
            meeting_repo = MeetingRepository(session)
            summary_repo = SummaryRepository(session)

            # Получить встречу
            meeting = await meeting_repo.get_by_id(UUID(meeting_id))
            if not meeting:
                await query.edit_message_text("Ошибка: встреча не найдена")
                return

            if not meeting.transcript:
                await query.edit_message_text("Ошибка: транскрипт отсутствует")
                return

            # Генерировать саммари
            engine = SummarizerEngine()
            result = await engine.summarize(meeting.transcript, meeting_type)

            # Сохранить в БД
            await summary_repo.create(
                meeting_id=meeting.id,
                meeting_type=meeting_type,
                content_text=result.text,
                content_json=result.json_data,
            )

            # Обновить тип встречи
            await meeting_repo.update_type(meeting.id, meeting_type)

            # Отправить результат
            # Telegram ограничивает сообщения 4096 символами
            text = result.text
            if len(text) > 4000:
                # Разбиваем на части
                chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
                await query.edit_message_text(chunks[0])
                for chunk in chunks[1:]:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=chunk
                    )
            else:
                await query.edit_message_text(text)

            logger.info(f"Summary generated for meeting {meeting_id}, type: {meeting_type}")

    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        await query.edit_message_text(f"Ошибка при генерации саммари: {str(e)[:100]}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Exception while handling an update: {context.error}")
