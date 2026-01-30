# Интеграции

## Fireflies.ai

### Описание
Fireflies транскрибирует встречи и отправляет webhook при готовности.

### Настройка webhook

1. Перейти в **Fireflies → Settings → Integrations → Webhooks**
2. Добавить URL: `https://your-server.com/api/webhook/fireflies`
3. Выбрать события: `Transcription completed`

### Получение транскрипта

Fireflies отправляет только `meeting_id`. Полный транскрипт получаем через GraphQL API.

```python
# src/integrations/fireflies.py
import httpx

class FirefliesClient:
    API_URL = "https://api.fireflies.ai/graphql"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def get_transcript(self, meeting_id: str) -> dict:
        query = """
        query GetTranscript($id: String!) {
            transcript(id: $id) {
                id
                title
                date
                duration
                sentences {
                    speaker_name
                    text
                    start_time
                    end_time
                }
                summary {
                    overview
                    action_items
                }
            }
        }
        """

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.API_URL,
                json={
                    "query": query,
                    "variables": {"id": meeting_id}
                },
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            return response.json()["data"]["transcript"]
```

### Переменные окружения

```env
FIREFLIES_API_KEY=your_api_key_here
```

---

## Todoist

### Описание
Создание задач из action items встречи, просмотр и завершение задач.

### API

```python
# src/integrations/todoist.py
from todoist_api_python import TodoistAPI

class TodoistIntegration:
    def __init__(self, api_token: str):
        self.api = TodoistAPI(api_token)

    def create_task(
        self,
        content: str,
        due_date: str = None,
        project_id: str = None,
        labels: list = None
    ) -> dict:
        """Создать задачу после саммари"""
        task = self.api.add_task(
            content=content,
            due_string=due_date,
            project_id=project_id,
            labels=labels or []
        )
        return {
            "id": task.id,
            "content": task.content,
            "url": task.url
        }

    def list_tasks(self, project_id: str = None) -> list:
        """Получить незавершённые задачи проекта"""
        filter_str = f"#project_id:{project_id}" if project_id else None
        tasks = self.api.get_tasks(filter=filter_str)
        return [
            {
                "id": t.id,
                "content": t.content,
                "due": t.due.string if t.due else None
            }
            for t in tasks
        ]

    def complete_task(self, task_id: str) -> bool:
        """Завершить задачу"""
        return self.api.close_task(task_id)
```

### Маппинг клиентов на проекты

```python
# Таблица todoist_mappings в БД
client_id       → todoist_project_id
"Indigo"        → "2326411981"
"GW Pro"        → "2326411982"
```

### Команды бота

| Команда | Действие |
|---------|----------|
| `Задачи Indigo` | Список задач проекта Indigo |
| `Готово 123456` | Завершить задачу с ID |

### Переменные окружения

```env
TODOIST_API_TOKEN=your_token_here
```

---

## Telegram Bot

### Описание
Основной интерфейс для взаимодействия с системой.

### Библиотека
`python-telegram-bot` v20+

### Обработчики

```python
# src/bot/handlers.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

async def handle_new_meeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Уведомление о новой встрече с кнопками выбора типа"""
    meeting_id = context.user_data.get("meeting_id")

    keyboard = [
        [
            InlineKeyboardButton("📋 Рабочая", callback_data=f"type:working:{meeting_id}"),
            InlineKeyboardButton("🔍 Диагностика", callback_data=f"type:diagnostics:{meeting_id}")
        ],
        [
            InlineKeyboardButton("📊 Трекшн", callback_data=f"type:traction:{meeting_id}"),
            InlineKeyboardButton("👋 Интро", callback_data=f"type:intro:{meeting_id}")
        ]
    ]

    await update.message.reply_text(
        f"🎙 Новая встреча: {meeting_title}\n\nВыберите тип:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора типа встречи"""
    query = update.callback_query
    _, meeting_type, meeting_id = query.data.split(":")

    await query.answer("Генерирую саммари...")

    # Генерация саммари
    summary = await summarizer.summarize(meeting_id, meeting_type)

    await query.edit_message_text(summary.text)
```

### Переменные окружения

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_ADMIN_CHAT_ID=123456789
```

---

## Telegram History (Telethon)

### Описание
Чтение истории чатов с клиентами для RAG.

### Зачем нужен Telethon

Bot API **не даёт доступа** к истории чатов. Telethon работает от имени вашего аккаунта.

### Настройка

1. Получить `api_id` и `api_hash` на https://my.telegram.org
2. Авторизоваться один раз (телефон + код)
3. Сохранить session string в `.env`

```python
# scripts/telegram_auth.py
from telethon import TelegramClient
from telethon.sessions import StringSession
import asyncio

API_ID = "your_api_id"
API_HASH = "your_api_hash"

async def create_session():
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        print("Session string:")
        print(client.session.save())

asyncio.run(create_session())

# Запустить: python scripts/telegram_auth.py
# Ввести телефон и код
# Скопировать session string в .env
```

### Использование

```python
# src/integrations/telegram_history.py
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime

class TelegramHistoryLoader:
    def __init__(self, api_id: int, api_hash: str, session_string: str):
        self.client = TelegramClient(
            StringSession(session_string),
            api_id,
            api_hash
        )

    async def connect(self):
        await self.client.connect()

    async def get_client_chats(self, client_name: str) -> list:
        """Найти чаты связанные с клиентом"""
        chats = []
        async for dialog in self.client.iter_dialogs():
            if client_name.lower() in dialog.name.lower():
                chats.append({
                    "id": dialog.id,
                    "name": dialog.name,
                    "type": "group" if dialog.is_group else "private"
                })
        return chats

    async def get_chat_history(
        self,
        chat_id: int,
        limit: int = 500,
        min_date: datetime = None
    ) -> list:
        """Получить историю чата"""
        messages = []
        async for msg in self.client.iter_messages(
            chat_id,
            limit=limit,
            offset_date=min_date
        ):
            if msg.text:
                messages.append({
                    "id": msg.id,
                    "date": msg.date.isoformat(),
                    "sender": msg.sender_id,
                    "text": msg.text
                })
        return messages
```

### Безопасность

- Session string даёт полный доступ к аккаунту — хранить как секрет
- Ограничить частоту запросов (не более 30/сек)
- Не спамить — риск бана аккаунта

### Переменные окружения

```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef
TELEGRAM_SESSION=1BVtsOK...long_string...
```

---

## Telegram MCP (опционально)

Для интеграции с Claude Desktop можно использовать MCP сервер.

### Установка

```json
// claude_desktop_config.json
{
  "mcpServers": {
    "telegram": {
      "command": "uvx",
      "args": ["telegram-mcp"],
      "env": {
        "TELEGRAM_API_ID": "your_api_id",
        "TELEGRAM_API_HASH": "your_api_hash",
        "TELEGRAM_SESSION": "your_session_string"
      }
    }
  }
}
```

### Доступные функции

- `get_chat_history(chat_id, limit)`
- `list_dialogs()`
- `send_message(chat_id, text)`
- `search_messages(query)`

---

## Claude API

### Описание
LLM для суммаризации встреч.

### Использование

```python
# src/summarizer/engine.py
import anthropic

class SummarizerEngine:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    async def summarize(self, transcript: str, meeting_type: str) -> str:
        prompt = self.load_prompt(meeting_type)

        message = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4096,
            system=prompt.system,
            messages=[
                {"role": "user", "content": prompt.user.format(transcript=transcript)}
            ]
        )

        return message.content[0].text
```

### Переменные окружения

```env
ANTHROPIC_API_KEY=sk-ant-...
```

---

## OpenAI Embeddings (Этап 2)

### Описание
Генерация эмбеддингов для RAG.

### Использование

```python
# src/rag/embeddings.py
from openai import OpenAI

class EmbeddingsGenerator:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def generate(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
```

### Переменные окружения

```env
OPENAI_API_KEY=sk-...
```

---

## Сводка переменных окружения

```env
# Database
DATABASE_URL=postgresql://copilot:password@localhost:5432/copilot

# Telegram Bot
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_ADMIN_CHAT_ID=123456789

# Telegram User (Telethon)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef
TELEGRAM_SESSION=1BVtsOK...

# Fireflies
FIREFLIES_API_KEY=...

# Todoist
TODOIST_API_TOKEN=...

# Claude API
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI (Этап 2)
OPENAI_API_KEY=sk-...
```
