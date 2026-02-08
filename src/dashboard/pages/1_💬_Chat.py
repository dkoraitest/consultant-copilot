"""
Страница чата с RAG
"""
import streamlit as st

from src.dashboard.utils import run_async
from src.database.connection import async_session_maker
from src.services.rag_service import RAGService

st.set_page_config(page_title="Chat - Consultant Copilot", page_icon="💬", layout="wide")

st.title("💬 Q&A Chat")
st.markdown("Задайте вопрос по истории встреч и переписке в Telegram")

# История чата в session_state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Кнопка очистки истории
if st.button("🗑️ Очистить историю", type="secondary"):
    st.session_state.messages = []
    st.rerun()

# Отображаем историю чата
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "sources" in message:
            with st.expander("📚 Источники"):
                st.markdown(message["sources"])

# Ввод вопроса
if prompt := st.chat_input("Введите ваш вопрос..."):
    # Добавляем вопрос в историю
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Получаем ответ от RAG
    with st.chat_message("assistant"):
        with st.spinner("🔍 Ищу ответ в транскриптах и Telegram..."):
            try:
                async def get_answer():
                    async with async_session_maker() as session:
                        rag = RAGService(session)
                        answer, meeting_sources, telegram_sources = await rag.ask(prompt)
                        return answer, meeting_sources, telegram_sources

                answer, meeting_sources, telegram_sources = run_async(get_answer())

                st.markdown(answer)

                # Формируем источники
                sources_text = ""
                if meeting_sources:
                    sources_text += "**Встречи:**\n"
                    seen = set()
                    for s in meeting_sources[:5]:
                        if s.meeting_title not in seen:
                            seen.add(s.meeting_title)
                            date_str = f" ({s.meeting_date[:10]})" if s.meeting_date else ""
                            sources_text += f"- {s.meeting_title}{date_str}\n"

                if telegram_sources:
                    sources_text += "\n**Telegram чаты:**\n"
                    seen = set()
                    for s in telegram_sources[:3]:
                        if s.chat_title not in seen:
                            seen.add(s.chat_title)
                            sources_text += f"- {s.chat_title}\n"

                if sources_text:
                    with st.expander("📚 Источники"):
                        st.markdown(sources_text)

                # Сохраняем в историю
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "sources": sources_text if sources_text else None
                })

            except Exception as e:
                st.error(f"Ошибка: {str(e)}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"❌ Ошибка: {str(e)}"
                })
