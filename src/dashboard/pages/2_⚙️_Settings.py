"""
Страница настроек
"""
import streamlit as st

from src.dashboard.utils import run_async, get_all_settings, set_setting, DEFAULT_SETTINGS

st.set_page_config(page_title="Settings - Consultant Copilot", page_icon="⚙️", layout="wide")

st.title("⚙️ Настройки")

# Загружаем текущие настройки
settings = run_async(get_all_settings())

# Вкладки
tab1, tab2 = st.tabs(["📝 Промпты", "🔧 Параметры RAG"])

with tab1:
    st.subheader("Системный промпт")
    st.markdown("Этот промпт используется для всех запросов к Claude")

    system_prompt = st.text_area(
        "Промпт",
        value=settings.get("system_prompt", DEFAULT_SETTINGS["system_prompt"]),
        height=400,
        help="Системный промпт для Claude при ответе на вопросы"
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("💾 Сохранить промпт", type="primary"):
            run_async(set_setting("system_prompt", system_prompt, "Системный промпт для RAG"))
            st.success("Промпт сохранён!")

    with col2:
        if st.button("🔄 Сбросить к дефолту"):
            run_async(set_setting("system_prompt", DEFAULT_SETTINGS["system_prompt"]))
            st.success("Промпт сброшен к значению по умолчанию")
            st.rerun()

with tab2:
    st.subheader("Параметры поиска")
    st.markdown("Эти параметры влияют на качество и количество найденных источников")

    col1, col2 = st.columns(2)

    with col1:
        min_similarity = st.slider(
            "Минимальная схожесть",
            min_value=0.0,
            max_value=1.0,
            value=float(settings.get("min_similarity", "0.15")),
            step=0.05,
            help="Порог схожести для включения чанка в контекст. Выше = строже фильтр."
        )

        max_chunks_per_meeting = st.number_input(
            "Макс. чанков на встречу",
            min_value=1,
            max_value=10,
            value=int(settings.get("max_chunks_per_meeting", "2")),
            help="Сколько чанков от одной встречи включать в контекст"
        )

    with col2:
        max_total_chunks = st.number_input(
            "Макс. всего чанков",
            min_value=5,
            max_value=50,
            value=int(settings.get("max_total_chunks", "20")),
            help="Общий лимит чанков в контексте"
        )

    st.divider()

    if st.button("💾 Сохранить параметры", type="primary"):
        run_async(set_setting("min_similarity", str(min_similarity), "Порог схожести"))
        run_async(set_setting("max_chunks_per_meeting", str(max_chunks_per_meeting), "Чанков на встречу"))
        run_async(set_setting("max_total_chunks", str(max_total_chunks), "Всего чанков"))
        st.success("Параметры сохранены!")

    st.info("""
    **Подсказка:**
    - Для точных вопросов по клиенту: similarity 0.15-0.20, chunks 2-3
    - Для общих вопросов: similarity 0.20-0.25, chunks 1-2
    - Больше чанков = больше контекста, но дороже и медленнее
    """)
