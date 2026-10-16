# Sourced by the other scripts: loads .env from the repo root and sets shared defaults.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi
N8N_CONTAINER="${N8N_CONTAINER:-n8n}"
N8N_URL="${N8N_URL:-http://localhost:${N8N_PORT:-5678}}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.example.yml}"
export COMPOSE_FILE
