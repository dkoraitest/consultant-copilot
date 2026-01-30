"""
Клавиатуры для Telegram бота
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_meeting_type_keyboard(meeting_id: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора типа встречи"""
    keyboard = [
        [
            InlineKeyboardButton(
                "📋 Рабочая",
                callback_data=f"type:working_meeting:{meeting_id}"
            ),
            InlineKeyboardButton(
                "🔍 Диагностика",
                callback_data=f"type:diagnostics:{meeting_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Трекшн",
                callback_data=f"type:traction:{meeting_id}"
            ),
            InlineKeyboardButton(
                "👋 Интро",
                callback_data=f"type:intro:{meeting_id}"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_confirmation_keyboard(action: str, item_id: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data=f"confirm:{action}:{item_id}"),
            InlineKeyboardButton("❌ Нет", callback_data=f"cancel:{action}:{item_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
