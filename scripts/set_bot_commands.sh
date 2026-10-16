#!/usr/bin/env bash
# Registers the Telegram command menu (/menu, /propuesta, ...) for the bot. Run once after creating the bot.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
: "${TELEGRAM_KITCHEN_BOT_TOKEN:?set TELEGRAM_KITCHEN_BOT_TOKEN in .env}"
curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_KITCHEN_BOT_TOKEN}/setMyCommands" \
  -H "Content-Type: application/json" \
  -d '{"commands":[
    {"command":"menu","description":"This week'"'"'s menu"},
    {"command":"propuesta","description":"New menu proposal"},
    {"command":"batch","description":"Sunday batch-cooking guide"},
    {"command":"lista","description":"Shopping list"},
    {"command":"casa","description":"What is at home"},
    {"command":"ayuda","description":"Help"}]}'
echo
