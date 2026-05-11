# ---- builder: install dependencies only, leverage layer cache ----
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

# ---- final: slim runtime with curl for healthcheck ----
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS final

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 appuser

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app /app

RUN mkdir -p /app/.memoryos && chown -R appuser:appuser /app/.memoryos

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/.memoryos

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["memoryos", "api", "--host", "0.0.0.0", "--port", "8000"]
