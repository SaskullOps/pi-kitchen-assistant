#!/usr/bin/env bash
# Simulates Telegram updates against the router webhook and prints what the workflow sent back.
# usage: harness.sh photo <file> [caption] | text <msg> | cb <callback_data> | job <webhook-path> <workflowId> [json]
# Needs: curl, jq, sqlite3, docker. Reads the n8n SQLite database (including its -wal file) of the running container.
# Note: `photo` uploads the file to the allowed chat with the bot token to obtain a Telegram file_id.
set -e
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
: "${KITCHEN_WEBHOOK_SECRET:?set KITCHEN_WEBHOOK_SECRET in .env}"
S=$KITCHEN_WEBHOOK_SECRET
T=${TELEGRAM_KITCHEN_BOT_TOKEN:-}
CHAT=${HARNESS_CHAT_ID:-${KITCHEN_ALLOWED_CHAT_IDS%%,*}}
SUDO=${HARNESS_SUDO-sudo}
WF=${HARNESS_WORKFLOW_ID:-KitchenRouter001}
HOOK=${KITCHEN_WEBHOOK_PATH:-kitchen-telegram}
datadir=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/home/node/.n8n"}}{{.Source}}{{end}}{{end}}' "$N8N_CONTAINER")
DB=${N8N_SQLITE:-$datadir/database.sqlite}
sql() { $SUDO sqlite3 -readonly "$DB" "$1"; }
[ "$1" = job ] && WF=$3
last() { sql "select id from execution_entity where workflowId='$WF' order by id desc limit 1;"; }
before=$(last)
U=$RANDOM
case "$1" in
  photo)
    fid=$(curl -s -F chat_id="$CHAT" -F caption="[test] $2" -F photo=@"$2" "https://api.telegram.org/bot$T/sendPhoto" | jq -r ".result.photo[-1].file_id")
    body=$(jq -nc --arg f "$fid" --arg c "${3:-}" --argjson u $U --argjson ch "$CHAT" '{update_id:$u,message:{message_id:$u,chat:{id:$ch,type:"private"},from:{first_name:"Tester"},caption:$c,photo:[{file_id:$f}]}}') ;;
  text)
    body=$(jq -nc --arg t "$2" --argjson u $U --argjson ch "$CHAT" '{update_id:$u,message:{message_id:$u,chat:{id:$ch,type:"private"},from:{first_name:"Tester"},text:$t}}') ;;
  job)
    body=${4:-"{}"}; URL=$N8N_URL/webhook/$2 ;;
  cb)
    body=$(jq -nc --arg d "$2" --argjson u $U --argjson ch "$CHAT" '{update_id:$u,callback_query:{id:"0",data:$d,from:{first_name:"Tester"},message:{message_id:$u,chat:{id:$ch}}}}') ;;
  *) sed -n '2,4p' "$0"; exit 2 ;;
esac
curl -s -o /dev/null -X POST "${URL:-$N8N_URL/webhook/$HOOK}" -H "Content-Type: application/json" -H "X-Kitchen-Secret: $S" -d "$body"
timeout 120 bash -c "until [ \"\$($SUDO sqlite3 -readonly '$DB' \"select id from execution_entity where workflowId='$WF' and status!='running' order by id desc limit 1;\")\" != \"$before\" ]; do sleep 2; done"
id=$(last)
st=$(sql "select status from execution_entity where id=$id;")
tmp=$(mktemp)
sql "select data from execution_data where executionId=$id;" > "$tmp"
python3 - "$id" "$st" "$tmp" <<'PY'
import json, sys
raw = json.load(open(sys.argv[3]))
memo = {}
def res(i):
    if i in memo: return memo[i]
    v = raw[i]
    if isinstance(v, dict):
        out = {}; memo[i] = out
        for k, x in v.items(): out[k] = res(int(x)) if isinstance(x, str) else x
        return out
    if isinstance(v, list):
        out = []; memo[i] = out
        for x in v: out.append(res(int(x)) if isinstance(x, str) else x)
        return out
    memo[i] = v
    return v
root = res(0)
rd = root["resultData"]
print(f"== exec {sys.argv[1]} {sys.argv[2]} | last node: {rd.get('lastNodeExecuted')}")
if rd.get("error"): print("ERROR:", rd["error"].get("message"), "@", (rd["error"].get("node") or {}).get("name"))
for name, runs in rd["runData"].items():
    if not name.startswith("Send") and name not in ("Set on-hand in Tandoor", "Link food in Grocy"): continue
    for run in runs:
        for out in (run.get("data") or {}).get("main") or []:
            for item in out or []:
                j = item.get("json", {})
                msg = (j.get("result") or {}).get("text") if isinstance(j.get("result"), dict) else None
                print(f"-- {name}:\n{msg if msg else json.dumps(j, ensure_ascii=False)[:300]}")
PY
rm -f "$tmp"
