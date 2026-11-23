FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[postgres]"

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY seed.py ./seed.py

EXPOSE 8000

# Render provides $PORT. Run migrations, seed, then start uvicorn.
CMD ["sh", "-c", "alembic upgrade head && python seed.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
