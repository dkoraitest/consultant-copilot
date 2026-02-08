"""
Страница управления клиентами и Telegram чатами
"""
import streamlit as st
import pandas as pd

from src.dashboard.utils import run_async, get_telegram_chats, toggle_chat_active

st.set_page_config(page_title="Clients - Consultant Copilot", page_icon="👥", layout="wide")

st.title("👥 Клиенты и Telegram чаты")

# ============================================================================
# Telegram чаты
# ============================================================================

st.subheader("📱 Telegram чаты")

chats = run_async(get_telegram_chats())

if chats:
    # Создаём DataFrame
    df = pd.DataFrame(chats)
    df = df.rename(columns={
        "id": "ID",
        "title": "Название",
        "client_name": "Клиент",
        "is_active": "Активен",
        "last_synced": "Последний синхр. ID"
    })

    # Показываем таблицу
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "Активен": st.column_config.CheckboxColumn("Активен", default=True),
        }
    )

    st.divider()

    # Управление активностью
    st.subheader("🔧 Управление чатами")

    col1, col2 = st.columns(2)

    with col1:
        selected_chat = st.selectbox(
            "Выберите чат",
            options=[(c["id"], c["title"]) for c in chats],
            format_func=lambda x: x[1]
        )

    with col2:
        if selected_chat:
            chat_info = next((c for c in chats if c["id"] == selected_chat[0]), None)
            if chat_info:
                current_status = chat_info["is_active"]
                new_status = st.toggle(
                    "Активен",
                    value=current_status,
                    key=f"toggle_{selected_chat[0]}"
                )

                if new_status != current_status:
                    run_async(toggle_chat_active(selected_chat[0], new_status))
                    st.success(f"Статус чата '{selected_chat[1]}' изменён на {'активен' if new_status else 'неактивен'}")
                    st.rerun()

else:
    st.info("Telegram чаты не найдены")

st.divider()

# ============================================================================
# Добавление нового чата
# ============================================================================

st.subheader("➕ Добавить новый чат")

st.warning("""
**Примечание:** Для добавления нового чата нужно:
1. Узнать chat_id (через @userinfobot или Telegram Desktop)
2. Добавить чат через код или API
3. Перезапустить telegram_watcher

Пока что эта функция требует ручной настройки.
""")

with st.expander("📋 Как найти chat_id"):
    st.markdown("""
    1. **Telegram Desktop:**
       - Правый клик на чат → Copy Link
       - ID будет в ссылке (например, -1001234567890)

    2. **@userinfobot:**
       - Перешлите сообщение из чата боту
       - Бот покажет ID чата

    3. **Через API:**
       - Используйте метод `getUpdates` или `getChat`
    """)
