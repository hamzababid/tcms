# Backend image: api, worker, migrate and CLI share this image (docs/03 §4).
# Build context is the repository root so the image can include docs/schema (baseline migration).
# Layout mirrors the repository: /app/backend, /app/docs/schema.

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/backend/.venv
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmagic1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --home /app tcms
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
WORKDIR /app/backend

FROM base AS deps
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM deps AS dev
# Local development: dev dependencies too; source is bind-mounted by docker-compose for reload.
RUN uv sync --frozen --no-install-project
COPY backend/ ./
COPY docs/schema /app/docs/schema
RUN uv sync --frozen
ENV PATH=/app/backend/.venv/bin:$PATH
USER tcms
EXPOSE 8000
CMD ["uvicorn", "--factory", "tcms.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/backend/src"]

FROM deps AS runtime
COPY backend/ ./
COPY docs/schema /app/docs/schema
RUN uv sync --frozen --no-dev && rm -rf tests
ENV PATH=/app/backend/.venv/bin:$PATH
USER tcms
EXPOSE 8000
CMD ["gunicorn", "tcms.main:create_app()", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
