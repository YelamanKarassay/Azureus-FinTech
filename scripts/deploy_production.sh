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

if docker info >/dev/null 2>&1; then
  COMPOSE=(docker compose)
else
  COMPOSE=(sudo docker compose)
fi

export BUILD_TIME="${BUILD_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
export GIT_SHA="${GIT_SHA:-unknown}"
export GIT_STATUS_CLEAN="${GIT_STATUS_CLEAN:-true}"

COMPOSE_ARGS=(
  --project-name "${COMPOSE_PROJECT_NAME}"
  --env-file .env.prod
  -f docker-compose.prod.yml
)

if [[ -n "${AZUREUS_API_IMAGE:-}" || -n "${AZUREUS_WORKER_IMAGE:-}" ]]; then
  "${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" pull api worker
else
  "${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" build api worker
fi

"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" run --rm api alembic upgrade head
"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" up -d --remove-orphans
"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" ps

curl --fail --silent --show-error \
  --retry 12 \
  --retry-delay 5 \
  --retry-all-errors \
  "${HEALTH_URL}" >/tmp/azureus-health.json

cat /tmp/azureus-health.json
echo
