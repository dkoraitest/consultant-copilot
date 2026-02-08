"""
Страница статистики
"""
import streamlit as st

from src.dashboard.utils import run_async, get_stats

st.set_page_config(page_title="Stats - Consultant Copilot", page_icon="📊", layout="wide")

st.title("📊 Статистика индекса")

# Загружаем статистику
try:
    stats = run_async(get_stats())

    # Основные метрики
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Встреч всего",
            stats["meetings_total"],
            help="Общее количество встреч в базе"
        )

    with col2:
        st.metric(
            "С транскриптами",
            stats["meetings_with_transcripts"],
            help="Встречи с непустыми транскриптами"
        )

    with col3:
        st.metric(
            "Эмбеддингов встреч",
            stats["meeting_embeddings"],
            help="Количество проиндексированных чанков из встреч"
        )

    st.divider()

    # Telegram статистика
    st.subheader("📱 Telegram")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Активных чатов",
            stats["telegram_chats"],
            help="Telegram чаты для мониторинга"
        )

    with col2:
        st.metric(
            "Сообщений",
            stats["telegram_messages"],
            help="Всего сообщений из Telegram"
        )

    with col3:
        st.metric(
            "Эмбеддингов Telegram",
            stats["telegram_embeddings"],
            help="Проиндексированных сообщений"
        )

    st.divider()

    # Общая статистика
    st.subheader("📈 Общая статистика")

    total_embeddings = stats["meeting_embeddings"] + stats["telegram_embeddings"]

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Всего эмбеддингов",
            total_embeddings,
            help="Суммарное количество чанков для RAG"
        )

    with col2:
        # Примерная стоимость хранения
        storage_mb = total_embeddings * 1536 * 4 / 1024 / 1024  # 1536 dim * 4 bytes
        st.metric(
            "Размер векторов",
            f"{storage_mb:.1f} MB",
            help="Примерный размер векторных данных"
        )

    st.info(f"""
    **Покрытие индексации:**
    - Встречи: {stats['meeting_embeddings']} чанков из {stats['meetings_with_transcripts']} транскриптов
    - Telegram: {stats['telegram_embeddings']} сообщений из {stats['telegram_messages']} всего

    Сообщения короче 50 символов не индексируются.
    """)

except Exception as e:
    st.error(f"Ошибка загрузки статистики: {str(e)}")
    st.info("Убедитесь, что база данных доступна")
