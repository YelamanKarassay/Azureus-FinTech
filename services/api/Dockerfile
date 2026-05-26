FROM python:3.12-slim

ARG GIT_SHA=unknown
ARG GIT_STATUS_CLEAN=false
ARG BUILD_TIME=unknown

ENV BUILD_TIME=${BUILD_TIME}
ENV GIT_SHA=${GIT_SHA}
ENV GIT_STATUS_CLEAN=${GIT_STATUS_CLEAN}
ENV PIP_NO_CACHE_DIR=1
ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md uv.lock ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY azureus ./azureus
COPY data/universe ./data/universe
COPY scripts ./scripts

RUN python -m pip install --upgrade pip \
    && python -m pip install uv \
    && uv sync --frozen --no-dev --no-editable

EXPOSE 8000

CMD ["uvicorn", "azureus.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
