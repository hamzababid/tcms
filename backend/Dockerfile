# Backend image: api, worker, migrate and CLI share this image (docs/03 §4).
# Build context is the repository root so the image can include docs/schema (baseline migration).
# Layout mirrors the repository: /app/backend, /app/docs/schema.

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/backend/.venv
# `upgrade`: Debian security fixes published after the base image was built (Trivy gate, M8c).
# libpq5: the C client library psycopg uses (Debian's build instead of the binary wheel's bundled copy).
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y --no-install-recommends libmagic1 libpq5 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --create-home --home-dir /home/tcms tcms
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
WORKDIR /app/backend

FROM base AS deps
# Compilers only here: psycopg-c is built against libpq; the runtime image copies the finished venv.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev \
 && rm -rf /var/lib/apt/lists/*
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --group speedups --no-install-project

FROM deps AS dev
# Local development: dev dependencies too; source is bind-mounted by docker-compose for reload.
RUN uv sync --frozen --group speedups --no-install-project
COPY backend/ ./
COPY docs/schema /app/docs/schema
RUN uv sync --frozen --group speedups
ENV PATH=/app/backend/.venv/bin:$PATH
USER tcms
EXPOSE 8000
CMD ["uvicorn", "--factory", "tcms.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/backend/src"]

FROM base AS runtime
COPY --from=deps /app/backend/.venv /app/backend/.venv
COPY backend/ ./
COPY docs/schema /app/docs/schema
RUN uv sync --frozen --no-dev --group speedups && rm -rf tests
ENV PATH=/app/backend/.venv/bin:$PATH
USER tcms
EXPOSE 8000
CMD ["gunicorn", "tcms.main:create_app()", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "1", "--access-logfile", "-", "--no-control-socket", "--keep-alive", "75"]
