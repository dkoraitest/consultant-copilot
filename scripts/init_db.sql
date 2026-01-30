-- Инициализация базы данных
-- Выполняется автоматически при первом запуске PostgreSQL контейнера

-- Включаем расширения
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Таблица клиентов
CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    telegram_chat_id BIGINT,
    todoist_project_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Таблица встреч
CREATE TABLE IF NOT EXISTS meetings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fireflies_id VARCHAR(255) UNIQUE,
    title VARCHAR(500) NOT NULL,
    date TIMESTAMP WITH TIME ZONE,
    transcript TEXT,
    client_id UUID REFERENCES clients(id),
    meeting_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Таблица саммари
CREATE TABLE IF NOT EXISTS summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID REFERENCES meetings(id) ON DELETE CASCADE,
    meeting_type VARCHAR(50) NOT NULL,
    content_text TEXT NOT NULL,
    content_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Таблица лидов
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_tg VARCHAR(255),
    client_name VARCHAR(255) NOT NULL,
    message TEXT,
    channel VARCHAR(100),
    status VARCHAR(50) DEFAULT 'new',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Таблица маппинга Todoist проектов
CREATE TABLE IF NOT EXISTS todoist_mappings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    todoist_project_id VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(client_id)
);

-- Таблица эмбеддингов (для Этапа 2)
CREATE TABLE IF NOT EXISTS embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID REFERENCES meetings(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),
    chunk_index INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индекс для векторного поиска
CREATE INDEX IF NOT EXISTS embeddings_vector_idx ON embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS meetings_client_idx ON meetings(client_id);
CREATE INDEX IF NOT EXISTS meetings_date_idx ON meetings(date DESC);
CREATE INDEX IF NOT EXISTS summaries_meeting_idx ON summaries(meeting_id);
CREATE INDEX IF NOT EXISTS leads_status_idx ON leads(status);

-- Комментарии к таблицам
COMMENT ON TABLE clients IS 'Клиенты консультанта';
COMMENT ON TABLE meetings IS 'Встречи с транскриптами';
COMMENT ON TABLE summaries IS 'Саммари встреч по типам';
COMMENT ON TABLE leads IS 'Потенциальные клиенты (лиды)';
COMMENT ON TABLE embeddings IS 'Эмбеддинги для RAG (Этап 2)';
