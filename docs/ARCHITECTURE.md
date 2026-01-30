# Архитектура Consultant Copilot

## Общая схема

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            VPS ($10-15/мес)                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                      PRESENTATION LAYER                           │ │
│  │  ┌─────────────────┐              ┌─────────────────┐             │ │
│  │  │  Telegram Bot   │              │  Mini App (v2)  │             │ │
│  │  │  (Этап 1)       │              │  React/Vue      │             │ │
│  │  │                 │              │                 │             │ │
│  │  │  • Кнопки       │              │  • Дашборд      │             │ │
│  │  │  • Команды      │              │  • История      │             │ │
│  │  │  • Push-уведомл │              │  • Аналитика    │             │ │
│  │  └────────┬────────┘              └────────┬────────┘             │ │
│  │           │                                │                      │ │
│  │           └────────────┬───────────────────┘                      │ │
│  └────────────────────────┼──────────────────────────────────────────┘ │
│                           ▼                                             │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                         API LAYER (FastAPI)                       │ │
│  │                                                                   │ │
│  │  /api/meetings      — CRUD встреч                                 │ │
│  │  /api/summaries     — генерация/получение саммари                 │ │
│  │  /api/clients       — управление клиентами                        │ │
│  │  /api/tasks         — Todoist интеграция                          │ │
│  │  /api/leads         — CRM лиды                                    │ │
│  │  /api/rag           — RAG Q&A (Этап 2)                            │ │
│  │  /api/analytics     — аналитика (Этап 3)                          │ │
│  │                                                                   │ │
│  │  Auth: Telegram WebApp InitData validation                        │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                           │                                             │
│                           ▼                                             │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                       SERVICE LAYER                               │ │
│  │                                                                   │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │ │
│  │  │ Summarizer  │  │ RAG Engine  │  │ Integrations│               │ │
│  │  │ Service     │  │ (Этап 2)    │  │             │               │ │
│  │  │             │  │             │  │ • Todoist   │               │ │
│  │  │ • Промпты   │  │ • Retriever │  │ • Fireflies │               │ │
│  │  │ • По типам  │  │ • Q&A       │  │ • Telegram  │               │ │
│  │  │ • JSON out  │  │ • Контекст  │  │             │               │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘               │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                           │                                             │
│                           ▼                                             │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                       DATA LAYER                                  │ │
│  │                    PostgreSQL + pgvector                          │ │
│  │                                                                   │ │
│  │  meetings    │ summaries  │ clients   │ leads    │ embeddings     │ │
│  │  tasks       │ users      │ settings  │ logs     │ graph_nodes    │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   Claude API    │
                    │   $20-40/мес    │
                    └─────────────────┘
```

## Принципы архитектуры

### 1. Разделение слоёв

| Слой | Ответственность |
|------|-----------------|
| Presentation | UI: Telegram Bot, Mini App |
| API | Единая точка входа, валидация, роутинг |
| Service | Бизнес-логика |
| Data | Хранение и доступ к данным |

### 2. Bot и Mini App параллельно

- Оба используют один API
- **Bot** — push-уведомления, быстрые команды
- **Mini App** — сложный UI, дашборды, аналитика

### 3. Готовность к Mini App

- FastAPI с самого начала
- Авторизация через Telegram WebApp InitData
- CORS настроен для WebApp

---

## Telegram интеграция

### Два способа работы с Telegram

| Компонент | Назначение | Библиотека |
|-----------|------------|------------|
| Bot API | Отправка сообщений, кнопки, webhook | python-telegram-bot |
| User API | Чтение истории чатов | Telethon |

### Зачем нужен Telethon

Bot API **не даёт доступа** к:
- Истории личных чатов
- Истории групп где бот не добавлен
- Сообщениям до добавления бота

**Telethon** работает от имени вашего аккаунта → полный доступ ко всем чатам.

### Схема интеграции

```
┌─────────────────────────────────────────────────────────────────┐
│                    TELEGRAM ИНТЕГРАЦИЯ                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────┐         ┌─────────────────────┐       │
│  │   Telegram Bot      │         │   Telethon Client   │       │
│  │   (python-telegram- │         │   (User API)        │       │
│  │    bot)             │         │                     │       │
│  │                     │         │                     │       │
│  │   • Отправка        │         │   • Чтение истории  │       │
│  │   • Кнопки          │         │   • Все чаты        │       │
│  │   • Webhook         │         │   • Поиск           │       │
│  │   • Уведомления     │         │   • Экспорт         │       │
│  └──────────┬──────────┘         └──────────┬──────────┘       │
│             │                               │                   │
│             └───────────────┬───────────────┘                   │
│                             ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Telegram MCP Server (опционально)           │   │
│  │              chigwell/telegram-mcp                       │   │
│  │                                                          │   │
│  │   Единый интерфейс для:                                  │   │
│  │   • get_chat_history(chat_id, limit)                     │   │
│  │   • list_dialogs()                                       │   │
│  │   • send_message(chat_id, text)                          │   │
│  │   • search_messages(query)                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## База данных

### PostgreSQL + pgvector

**Почему не Notion:**
- Notion не поддерживает хранение эмбеддингов
- Медленные запросы при большом объёме
- Нет возможности векторного поиска

### Основные таблицы

```sql
-- Встречи
CREATE TABLE meetings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fireflies_id VARCHAR(255) UNIQUE,
    title VARCHAR(500),
    date TIMESTAMP WITH TIME ZONE,
    transcript TEXT,
    client_id UUID REFERENCES clients(id),
    meeting_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Саммари
CREATE TABLE summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID REFERENCES meetings(id),
    meeting_type VARCHAR(50),
    content_text TEXT,
    content_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Клиенты
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255),
    telegram_chat_id BIGINT,
    todoist_project_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Лиды
CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_tg VARCHAR(255),
    client_name VARCHAR(255),
    message TEXT,
    channel VARCHAR(100),
    status VARCHAR(50) DEFAULT 'new',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Эмбеддинги (Этап 2)
CREATE TABLE embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID REFERENCES meetings(id),
    chunk_text TEXT,
    embedding vector(1536),
    chunk_index INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индекс для векторного поиска
CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops);
```

---

## Флоу Этапа 1

```
Fireflies webhook
      │
      ▼
┌─────────────────┐
│ Получить        │
│ транскрипт      │
│ (GraphQL API)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Сохранить в БД  │
│ (meetings)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Отправить в TG  │
│ с кнопками      │
│ выбора типа     │
└────────┬────────┘
         │
    [Пользователь нажимает кнопку]
         │
         ▼
┌─────────────────┐
│ Генерация       │
│ саммари         │
│ (Claude API)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Сохранить       │
│ (summaries)     │
│ JSON + текст    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Отправить       │
│ в Telegram      │
└─────────────────┘
```

---

## Структура проекта

```
src/
├── __init__.py
├── config.py                    # Конфигурация из .env
│
├── api/                         # FastAPI
│   ├── __init__.py
│   ├── main.py                  # Приложение FastAPI
│   ├── routes/
│   │   ├── meetings.py
│   │   ├── summaries.py
│   │   ├── clients.py
│   │   ├── tasks.py
│   │   ├── leads.py
│   │   └── webhooks.py          # Fireflies webhook
│   └── auth.py                  # Telegram WebApp auth
│
├── bot/                         # Telegram Bot
│   ├── __init__.py
│   ├── main.py                  # Запуск бота
│   ├── handlers.py              # Обработчики сообщений
│   ├── keyboards.py             # Кнопки выбора типа
│   └── formatters.py            # Форматирование ответов
│
├── summarizer/                  # Движок суммаризации
│   ├── __init__.py
│   ├── engine.py                # Основной движок
│   └── prompts/                 # Промпты по типам
│       ├── working_meeting.md
│       ├── diagnostics.md
│       ├── traction.md
│       └── intro.md
│
├── database/                    # Data Layer
│   ├── __init__.py
│   ├── connection.py            # Подключение к БД
│   ├── models.py                # SQLAlchemy модели
│   └── repository.py            # CRUD операции
│
├── integrations/                # Внешние сервисы
│   ├── __init__.py
│   ├── fireflies.py             # Fireflies GraphQL
│   ├── todoist.py               # Todoist API
│   ├── telegram_client.py       # Отправка в группы
│   └── telegram_history.py      # Telethon для истории
│
└── rag/                         # RAG (Этап 2)
    ├── __init__.py
    ├── embeddings.py            # Генерация эмбеддингов
    ├── retriever.py             # Поиск релевантных чанков
    └── chain.py                 # LangChain RAG chain
```

---

## Технический стек

| Компонент | Технология | Версия |
|-----------|------------|--------|
| Язык | Python | 3.11+ |
| База данных | PostgreSQL + pgvector | 15 |
| ORM | SQLAlchemy | 2.0 |
| API Framework | FastAPI | 0.100+ |
| Telegram Bot | python-telegram-bot | 20+ |
| Telegram User | Telethon | 1.30+ |
| LLM | Claude API | claude-3-5-sonnet |
| Embeddings | OpenAI | text-embedding-3-small |
| RAG | LangChain | 0.1+ |
| Контейнеризация | Docker Compose | 3.8 |

---

## Деплой

### Требования к серверу

- Ubuntu 22.04 LTS
- 2-4 GB RAM
- 20 GB SSD
- Статический IP или домен

### Провайдеры

- Timeweb Cloud ($10-15/мес)
- DigitalOcean ($12-24/мес)
- Hetzner ($5-10/мес)

### Docker Compose

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - db
    restart: unless-stopped

  db:
    image: pgvector/pgvector:pg15
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: copilot
      POSTGRES_USER: copilot
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    restart: unless-stopped

volumes:
  postgres_data:
```
