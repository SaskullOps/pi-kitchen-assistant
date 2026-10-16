"""Environment-driven configuration shared by the workflow generators.

Everything environment-specific lives here so that the generated n8n workflows
contain no hardcoded chat IDs, credentials, URLs or personal names.
"""
import os
import re
import sys


def _required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"error: environment variable {name} is required (see .env.example)")
    return value


def _env(name, default):
    return os.environ.get(name, default).strip()


def _cred(prefix, default_id, default_name):
    return {"id": _env(f"{prefix}_ID", default_id), "name": _env(f"{prefix}_NAME", default_name)}


CHAT_IDS = []
for _raw in _required("KITCHEN_CHAT_IDS").split(","):
    if _raw.strip():
        if not re.fullmatch(r"-?\d+", _raw.strip()):
            sys.exit(f"error: KITCHEN_CHAT_IDS contains a non-numeric chat id: {_raw!r}")
        CHAT_IDS.append(int(_raw.strip()))
if not CHAT_IDS:
    sys.exit("error: KITCHEN_CHAT_IDS must contain at least one Telegram chat id")

GROCY_URL = _env("GROCY_API_URL", "http://grocy:80/api")
TANDOOR_URL = _env("TANDOOR_API_URL", "http://tandoor:80/api")
# Optional browser-facing Tandoor URL used for the "open the session plan" link in the batch guide.
TANDOOR_PUBLIC_URL = _env("TANDOOR_PUBLIC_URL", "").rstrip("/")
OPENROUTER_URL = _env("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")

MODEL = _env("KITCHEN_MODEL", "google/gemini-3.5-flash-lite")
GUIDE_MODEL = _env("KITCHEN_GUIDE_MODEL", "google/gemini-3.8-flash")

TIMEZONE = _env("KITCHEN_TIMEZONE", "Europe/Madrid")
WEBHOOK_PATH = _env("KITCHEN_WEBHOOK_PATH", "kitchen-telegram")
PLANNER_HOOK_PATH = _env("KITCHEN_PLANNER_HOOK_PATH", "kitchen-job-planner")

PERSONAL_NAME = _env("KITCHEN_PERSONAL_NAME", "Person A")
if not re.fullmatch(r"[\w .-]{1,40}", PERSONAL_NAME):
    sys.exit("error: KITCHEN_PERSONAL_NAME may only contain letters, digits, spaces, dots and dashes")

HOUSEHOLD = _env(
    "KITCHEN_HOUSEHOLD",
    "Household: a couple living in a Mediterranean city. They shop at a local market, a butcher and a few "
    "supermarket chains, so ingredients must be easy to find. Kitchen: 3 burners (large, medium, small), "
    "an air fryer and a rice cooker; the oven is rarely used. They like everything (Mediterranean, Asian, Indian, "
    "Mexican...), want variety and mostly healthy food. Friday and weekends are outside the plan.",
)
LOCALE_HINT = _env("KITCHEN_LOCALE_HINT", "supermarkets and markets near the household")

CRED_TG = {"telegramApi": _cred("N8N_CRED_TELEGRAM", "KitchenTgBot0001", "Kitchen bot")}
CRED_GROCY = {"httpHeaderAuth": _cred("N8N_CRED_GROCY", "KitchenGrocy0001", "Grocy API")}
CRED_TANDOOR = {"httpHeaderAuth": _cred("N8N_CRED_TANDOOR", "KitchenTandoor01", "Tandoor API")}
CRED_OR = {"httpHeaderAuth": _cred("N8N_CRED_OPENROUTER", "KitchenORouter01", "OpenRouter")}
CRED_BRIDGE = {"httpHeaderAuth": _cred("N8N_CRED_BRIDGE", "KitchenBridge001", "Kitchen bridge secret")}
