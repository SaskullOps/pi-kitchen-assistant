#!/usr/bin/env bash
# usage: deploy.sh <workflow.json> <workflow-id> [more json/id pairs...]
# Imports and publishes workflows in the n8n container, restarts n8n and waits until the router webhook is live.
# example: deploy.sh build/kitchen-router.json KitchenRouter001 build/kitchen-expiry.json KitchenExpiry001
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
[ $# -ge 2 ] || { sed -n '2,5p' "$0"; exit 2; }
cd "$ROOT"
log=$(mktemp)
trap 'rm -f "$log"' EXIT
while [ $# -ge 2 ]; do
  json=$1; id=$2; shift 2
  docker cp "$json" "$N8N_CONTAINER:/tmp/wf.json"
  docker exec "$N8N_CONTAINER" n8n import:workflow --input=/tmp/wf.json >"$log" 2>&1 || { cat "$log"; exit 1; }
  # n8n 2.x: publish:workflow; older 1.x: update:workflow --active=true
  if ! timeout 150 docker exec "$N8N_CONTAINER" n8n publish:workflow --id="$id" >"$log" 2>&1; then
    timeout 150 docker exec "$N8N_CONTAINER" n8n update:workflow --id="$id" --active=true >"$log" 2>&1 \
      || { echo "publish $id failed"; cat "$log"; exit 1; }
  fi
  docker exec "$N8N_CONTAINER" rm -f /tmp/wf.json
  echo "imported+published $id"
done
# Publishing only takes effect after a restart of n8n.
docker compose restart "${N8N_SERVICE:-n8n}" >/dev/null 2>&1
timeout 120 bash -c "until curl -s -o /dev/null $N8N_URL/healthz; do sleep 3; done"
# Webhook rows exist before activation finishes; wait until n8n actually answers on the route
# (an unauthenticated request gets "Authorization data is wrong!" once the webhook is live).
path="${KITCHEN_WEBHOOK_PATH:-kitchen-telegram}"
timeout 90 bash -c "until curl -s -X POST $N8N_URL/webhook/$path | grep -q 'Authorization data is wrong'; do sleep 2; done"
echo "n8n up, router webhook live"
