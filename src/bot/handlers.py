"""
Обработчики сообщений Telegram бота
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.bot.keyboards import get_meeting_type_keyboard


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "Привет! Я Consultant Copilot.\n\n"
        "Я помогу создавать саммари встреч.\n\n"
        "Команды:\n"
        "/help - Справка"
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "📋 *Типы встреч:*\n\n"
        "• *Рабочая* — внутренняя встреча с командой\n"
        "• *Диагностика* — первая встреча с клиентом\n"
        "• *Трекшн* — еженедельный созвон с клиентом\n"
        "• *Интро* — первое знакомство\n\n"
        "Саммари генерируется автоматически после получения транскрипта от Fireflies.",
        parse_mode="Markdown"
    )


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
        text=f"🎙 *Новая встреча:* {meeting_title}\n\nВыберите тип:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


async def meeting_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора типа встречи"""
    query = update.callback_query
    await query.answer()

    # Парсим callback_data: "type:meeting_type:meeting_id"
    _, meeting_type, meeting_id = query.data.split(":")

    await query.edit_message_text(f"⏳ Генерирую саммари ({meeting_type})...")

    # TODO: Вызвать SummarizerEngine
    # summary = await summarizer.summarize(meeting_id, meeting_type)
    # await query.edit_message_text(summary.text)

    # Заглушка
    await query.edit_message_text(
        f"✅ Саммари для встречи (тип: {meeting_type})\n\n"
        f"[Здесь будет результат суммаризации]"
    )
