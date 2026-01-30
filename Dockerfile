FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY src/ ./src/
COPY config/ ./config/
COPY alembic.ini .
COPY alembic/ ./alembic/

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Default command
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
