# Build stage
FROM python:3.12.13-trixie AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY src/bot/pyproject.toml src/bot/README.md ./
RUN uv sync --no-dev --no-install-project

COPY src/bot/main.py /app/main.py
COPY src/bot/bot_service/ /app/bot_service/


# Final stage
FROM python:3.12.13-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app /app


CMD ["python", "/app/main.py"]

