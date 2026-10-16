import json
import logging
import os
import time
import urllib.error
import urllib.request

TOKEN = os.environ["TELEGRAM_KITCHEN_BOT_TOKEN"]
TARGET = os.environ["N8N_KITCHEN_WEBHOOK"]
SECRET = os.environ["KITCHEN_WEBHOOK_SECRET"]
ALLOWED = {int(x) for x in os.environ["KITCHEN_ALLOWED_CHAT_IDS"].split(",") if x.strip()}
OFFSET_FILE = os.environ.get("BRIDGE_OFFSET_FILE", "/data/offset")
API = f"https://api.telegram.org/bot{TOKEN}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bridge")


def load_offset():
    try:
        with open(OFFSET_FILE) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def save_offset(offset):
    tmp = OFFSET_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write(str(offset))
    os.replace(tmp, OFFSET_FILE)


def chat_id_of(update):
    for key in ("message", "edited_message", "channel_post"):
        if key in update:
            return update[key]["chat"]["id"]
    if "callback_query" in update:
        return update["callback_query"]["message"]["chat"]["id"]
    return None


def get_updates(offset):
    body = json.dumps({"offset": offset, "timeout": 50,
                       "allowed_updates": ["message", "edited_message", "callback_query"]}).encode()
    req = urllib.request.Request(f"{API}/getUpdates", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=65) as r:
        return json.load(r)["result"]


def forward(update):
    req = urllib.request.Request(TARGET, data=json.dumps(update).encode(),
                                 headers={"Content-Type": "application/json", "X-Kitchen-Secret": SECRET})
    with urllib.request.urlopen(req, timeout=30) as r:
        return 200 <= r.status < 300


def main():
    urllib.request.urlopen(urllib.request.Request(f"{API}/deleteWebhook", data=b""), timeout=15)
    offset = load_offset()
    log.info("started, allowed chats=%s, offset=%s", sorted(ALLOWED), offset)
    while True:
        try:
            updates = get_updates(offset)
        except Exception as e:
            log.warning("getUpdates failed: %s", e)
            time.sleep(5)
            continue
        for u in updates:
            cid = chat_id_of(u)
            if cid not in ALLOWED:
                log.warning("dropped update %s from unauthorized chat %s", u["update_id"], cid)
            else:
                while True:
                    try:
                        if forward(u):
                            break
                    except urllib.error.HTTPError as e:
                        log.warning("n8n rejected update %s: HTTP %s", u["update_id"], e.code)
                    except Exception as e:
                        log.warning("n8n unreachable for update %s: %s", u["update_id"], e)
                    time.sleep(10)
            offset = u["update_id"] + 1
            save_offset(offset)


if __name__ == "__main__":
    main()
