#!/usr/bin/env bash
# Creates (or updates) the n8n credentials the generated workflows reference, with fixed ids/names taken from .env.
# Secrets are read from .env, written to a private temp file, imported through the n8n CLI and removed again.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
umask 077
tmp="$(mktemp)"
trap 'rm -f "$tmp"; docker exec "$N8N_CONTAINER" rm -f /tmp/kitchen-creds.json >/dev/null 2>&1 || true' EXIT
python3 - "$tmp" <<'PY'
import os, sys
sys.path.insert(0, os.path.join(os.environ["ROOT"], "generator"))
import json
import config as c

def need(name):
    v = os.environ.get(name, "").strip()
    if not v or v.startswith("change-me") or v.startswith("000000000:"):
        sys.exit(f"error: set {name} in .env before creating credentials")
    return v

def header(cred, header_name, value):
    (kind, ref), = cred.items()
    return {"id": ref["id"], "name": ref["name"], "type": kind, "data": {"name": header_name, "value": value}}

(tg_kind, tg_ref), = c.CRED_TG.items()
creds = [
    {"id": tg_ref["id"], "name": tg_ref["name"], "type": tg_kind,
     "data": {"accessToken": need("TELEGRAM_KITCHEN_BOT_TOKEN"), "baseUrl": "https://api.telegram.org"}},
    header(c.CRED_GROCY, "GROCY-API-KEY", need("GROCY_API_KEY")),
    header(c.CRED_TANDOOR, "Authorization", "Bearer " + need("TANDOOR_API_TOKEN")),
    header(c.CRED_OR, "Authorization", "Bearer " + need("OPENROUTER_API_KEY")),
    header(c.CRED_BRIDGE, "X-Kitchen-Secret", need("KITCHEN_WEBHOOK_SECRET")),
]
json.dump(creds, open(sys.argv[1], "w"))
PY
docker cp "$tmp" "$N8N_CONTAINER:/tmp/kitchen-creds.json"
docker exec "$N8N_CONTAINER" n8n import:credentials --input=/tmp/kitchen-creds.json
