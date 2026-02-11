"""
Страница управления клиентами и Telegram чатами
"""
import streamlit as st
import pandas as pd

from src.dashboard.utils import (
    run_async,
    get_clients,
    create_client,
    get_telegram_chats_with_clients,
    update_chat_client,
    create_telegram_chat,
    toggle_chat_active,
    get_unlinked_meetings,
    link_meeting_to_client,
    bulk_link_meetings_by_pattern,
)

st.set_page_config(page_title="Clients - Consultant Copilot", page_icon="👥", layout="wide")

st.title("👥 Клиенты и Telegram чаты")

# ============================================================================
# Вкладки
# ============================================================================

tab1, tab2, tab3, tab4 = st.tabs(["📋 Клиенты", "📱 Telegram чаты", "🔗 Не связанные", "➕ Добавить чат"])

# ============================================================================
# Tab 1: Клиенты
# ============================================================================

with tab1:
    st.subheader("Список клиентов")

    clients = run_async(get_clients())

    if clients:
        df = pd.DataFrame(clients)
        df = df.rename(columns={
            "name": "Клиент",
            "meetings_count": "Встреч",
            "chats_count": "Чатов",
            "messages_count": "Сообщений",
        })

        st.dataframe(
            df[["Клиент", "Встреч", "Чатов", "Сообщений"]],
            use_container_width=True,
            hide_index=True,
        )

        st.info(f"""
        **Всего клиентов:** {len(clients)}
        **Встреч:** {sum(c['meetings_count'] for c in clients)}
        **Telegram чатов:** {sum(c['chats_count'] for c in clients)}
        """)
    else:
        st.warning("Клиенты не найдены. Создайте первого клиента ниже.")

    st.divider()

    st.subheader("➕ Добавить клиента")

    with st.form("add_client_form"):
        new_client_name = st.text_input("Имя клиента", placeholder="Например: Timeweb Cloud")
        submit = st.form_submit_button("Добавить", type="primary")

        if submit and new_client_name:
            result = run_async(create_client(new_client_name.strip()))
            if result:
                st.success(f"Клиент '{new_client_name}' создан!")
                st.rerun()
            else:
                st.error(f"Клиент с именем '{new_client_name}' уже существует")

# ============================================================================
# Tab 2: Telegram чаты
# ============================================================================

with tab2:
    st.subheader("Telegram чаты")

    chats = run_async(get_telegram_chats_with_clients())
    clients = run_async(get_clients())

    if chats:
        df = pd.DataFrame(chats)

        st.dataframe(
            df[["title", "client_name", "is_active", "messages_count"]].rename(columns={
                "title": "Название чата",
                "client_name": "Клиент",
                "is_active": "Активен",
                "messages_count": "Сообщений",
            }),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()

        st.subheader("🔧 Привязать чат к клиенту")

        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            selected_chat = st.selectbox(
                "Выберите чат",
                options=[(c["id"], c["title"]) for c in chats],
                format_func=lambda x: x[1]
            )

        with col2:
            client_options = [(None, "— Не выбран —")] + [(c["id"], c["name"]) for c in clients]
            selected_client = st.selectbox(
                "Выберите клиента",
                options=client_options,
                format_func=lambda x: x[1]
            )

        with col3:
            if st.button("Сохранить", type="primary", key="save_chat_client"):
                if selected_chat:
                    run_async(update_chat_client(selected_chat[0], selected_client[0]))
                    st.success("Связь сохранена!")
                    st.rerun()

        st.divider()

        st.subheader("🔌 Активировать/деактивировать")

        col1, col2 = st.columns(2)

        with col1:
            chat_for_toggle = st.selectbox(
                "Чат",
                options=[(c["id"], c["title"], c["is_active"]) for c in chats],
                format_func=lambda x: f"{'✅' if x[2] else '❌'} {x[1]}",
                key="chat_toggle_select"
            )

        with col2:
            if chat_for_toggle:
                current_status = chat_for_toggle[2]
                new_status = st.toggle(
                    "Активен",
                    value=current_status,
                    key=f"toggle_{chat_for_toggle[0]}"
                )

                if new_status != current_status:
                    run_async(toggle_chat_active(chat_for_toggle[0], new_status))
                    st.success(f"Статус изменён")
                    st.rerun()

    else:
        st.info("Telegram чаты не найдены")

# ============================================================================
# Tab 3: Не связанные встречи
# ============================================================================

with tab3:
    st.subheader("Встречи без привязки к клиенту")

    # Поиск
    search_query = st.text_input("🔍 Поиск по названию", placeholder="Введите часть названия...")

    # Получаем данные
    meetings, total = run_async(get_unlinked_meetings(limit=50, search=search_query))
    clients = run_async(get_clients())

    st.metric("Всего не связанных", total)

    if meetings:
        # Таблица встреч
        df = pd.DataFrame(meetings)
        df["date_str"] = df["date"].apply(lambda x: x.strftime("%Y-%m-%d") if x else "—")
        df["transcript"] = df["has_transcript"].apply(lambda x: "✅" if x else "❌")

        st.dataframe(
            df[["title", "date_str", "transcript"]].rename(columns={
                "title": "Название",
                "date_str": "Дата",
                "transcript": "Транскрипт"
            }),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()

        # Быстрая привязка одной встречи
        st.subheader("🔗 Быстрая привязка")

        col1, col2, col3 = st.columns([3, 2, 1])

        with col1:
            selected_meeting = st.selectbox(
                "Встреча",
                options=[(m["id"], m["title"]) for m in meetings],
                format_func=lambda x: x[1][:60] + "..." if len(x[1]) > 60 else x[1]
            )

        with col2:
            client_for_link = st.selectbox(
                "Клиент",
                options=[(c["id"], c["name"]) for c in clients],
                format_func=lambda x: x[1],
                key="client_for_meeting"
            )

        with col3:
            if st.button("Связать", type="primary"):
                if selected_meeting and client_for_link:
                    run_async(link_meeting_to_client(selected_meeting[0], client_for_link[0]))
                    st.success("Связано!")
                    st.rerun()

        st.divider()

        # Массовая привязка по паттерну
        st.subheader("📦 Массовая привязка по паттерну")

        st.info("Введите часть названия встречи — все встречи с этим текстом будут привязаны к выбранному клиенту")

        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            pattern = st.text_input("Паттерн", placeholder="Например: Timeweb")

        with col2:
            client_for_bulk = st.selectbox(
                "Клиент",
                options=[(c["id"], c["name"]) for c in clients],
                format_func=lambda x: x[1],
                key="client_for_bulk"
            )

        with col3:
            if st.button("Применить", type="secondary"):
                if pattern and client_for_bulk:
                    updated = run_async(bulk_link_meetings_by_pattern(pattern, client_for_bulk[0]))
                    st.success(f"Связано {updated} встреч!")
                    st.rerun()

    else:
        if search_query:
            st.info(f"Не найдено встреч по запросу '{search_query}'")
        else:
            st.success("Все встречи связаны с клиентами! 🎉")

# ============================================================================
# Tab 4: Добавить чат
# ============================================================================

with tab4:
    st.subheader("Добавить новый Telegram чат")

    st.info("""
    **Как найти chat_id:**
    1. Откройте Telegram Desktop
    2. Правый клик на чат → Copy Link
    3. ID будет в ссылке (например, для группы: -1001234567890)

    Или переслите сообщение боту @userinfobot
    """)

    clients = run_async(get_clients())

    with st.form("add_chat_form"):
        chat_id = st.number_input(
            "Chat ID",
            value=0,
            step=1,
            help="Числовой ID чата в Telegram (может быть отрицательным для групп)"
        )

        chat_title = st.text_input(
            "Название чата",
            placeholder="Например: Project X & Dima"
        )

        client_options = [(None, "— Не выбран —")] + [(c["id"], c["name"]) for c in clients]
        client_id = st.selectbox(
            "Клиент",
            options=client_options,
            format_func=lambda x: x[1]
        )

        submit = st.form_submit_button("Добавить чат", type="primary")

        if submit:
            if chat_id == 0:
                st.error("Введите chat_id")
            elif not chat_title:
                st.error("Введите название чата")
            else:
                result = run_async(create_telegram_chat(
                    chat_id=int(chat_id),
                    title=chat_title,
                    client_id=client_id[0] if client_id else None
                ))

                if result:
                    st.success(f"Чат '{chat_title}' добавлен!")
                    st.info("""
                    **Следующие шаги:**
                    1. Перезапустите telegram_watcher для начала мониторинга
                    2. Или запустите синхронизацию вручную через API

                    ```bash
                    docker compose restart telegram_watcher
                    ```
                    """)
                else:
                    st.error(f"Чат с ID {chat_id} уже существует")
