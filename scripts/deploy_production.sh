#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${1:-$(pwd)}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-azureus}"
HEALTH_URL="${AZUREUS_PUBLIC_HEALTH_URL:-https://azureus.tech/api/v1/health}"

cd "${APP_DIR}"

if [[ ! -f ".env.prod" ]]; then
  echo "Missing .env.prod in ${APP_DIR}" >&2
  exit 1
fi

if [[ ! -f "frontend/dist/index.html" ]]; then
  echo "Missing frontend/dist/index.html; build the Vite frontend before deploy." >&2
  exit 1
fi

export BUILD_TIME="${BUILD_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
export GIT_SHA="${GIT_SHA:-unknown}"
export GIT_STATUS_CLEAN="${GIT_STATUS_CLEAN:-true}"

upsert_env_value() {
  local key="$1"
  local value="$2"

  if grep -q "^${key}=" .env.prod; then
    python3 - "$key" "$value" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

key = sys.argv[1]
value = sys.argv[2]
path = Path(".env.prod")
lines = path.read_text().splitlines()
path.write_text(
    "\n".join(
        f"{key}={value}" if line.startswith(f"{key}=") else line for line in lines
    )
    + "\n"
)
PY
  else
    printf "%s=%s\n" "$key" "$value" >> .env.prod
  fi
}

upsert_env_value BUILD_TIME "${BUILD_TIME}"
upsert_env_value GIT_SHA "${GIT_SHA}"
upsert_env_value GIT_STATUS_CLEAN "${GIT_STATUS_CLEAN}"

compose() {
  if docker info >/dev/null 2>&1; then
    docker compose "$@"
  else
    sudo env \
      "BUILD_TIME=${BUILD_TIME}" \
      "GIT_SHA=${GIT_SHA}" \
      "GIT_STATUS_CLEAN=${GIT_STATUS_CLEAN}" \
      "AZUREUS_API_IMAGE=${AZUREUS_API_IMAGE:-}" \
      "AZUREUS_WORKER_IMAGE=${AZUREUS_WORKER_IMAGE:-}" \
      docker compose "$@"
  fi
}

COMPOSE_ARGS=(
  --project-name "${COMPOSE_PROJECT_NAME}"
  --env-file .env.prod
  -f docker-compose.prod.yml
)

if [[ -n "${AZUREUS_API_IMAGE:-}" || -n "${AZUREUS_WORKER_IMAGE:-}" ]]; then
  compose "${COMPOSE_ARGS[@]}" pull api worker
else
  compose "${COMPOSE_ARGS[@]}" build api worker mlflow
fi

compose "${COMPOSE_ARGS[@]}" run --rm api alembic upgrade head
MLFLOW_DB="${MLFLOW_POSTGRES_DB:-mlflow}"
compose "${COMPOSE_ARGS[@]}" exec -T postgres env "MLFLOW_DB=${MLFLOW_DB}" sh -c '
  if ! psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '\''$MLFLOW_DB'\''" | grep -q 1; then
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE \"$MLFLOW_DB\""
  fi
'
compose "${COMPOSE_ARGS[@]}" up -d --remove-orphans
compose "${COMPOSE_ARGS[@]}" ps

curl --fail --silent --show-error \
  --retry 12 \
  --retry-delay 5 \
  --retry-all-errors \
  "${HEALTH_URL}" >/tmp/azureus-health.json

cat /tmp/azureus-health.json
echo
