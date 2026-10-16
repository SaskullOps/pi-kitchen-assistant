# Setup guide: from zero to a working kitchen assistant

This guide rebuilds the whole stack on a fresh machine. The Grocy, Tandoor and n8n parts (first run, master-data
seed, credentials, generation, deploy and the manual job webhooks) were exercised against freshly created containers.
Anything that needs a real Telegram bot or a real LLM key (BotFather steps, receipt reading, intents, menu proposals,
the live polling of `harness.sh`) could not be exercised in that run and is described from the design and the
original deployment.

Contents: [1 Prerequisites](#1-prerequisites) - [2 Telegram](#2-telegram) - [3 Start the stack](#3-start-the-stack) -
[4 First run of each service](#4-first-run-of-each-service) - [5 Master data](#5-master-data-the-generator-expects) -
[6 LLM provider](#6-llm-provider-and-models) - [7 n8n credentials, generation, deploy](#7-n8n-credentials-generation-and-deploy) -
[8 Verify](#8-verify) - [9 Scheduled jobs](#9-scheduled-jobs) - [10 Security](#10-security-notes) -
[11 Troubleshooting](#11-troubleshooting) - [12 Env var reference](#12-environment-variable-reference)

## 1. Prerequisites

| Item | Notes |
|---|---|
| Host | Raspberry Pi 4/5 (64-bit OS) or any Linux box. All images are multi-arch (`arm64` and `amd64`). |
| RAM / disk | 4 GB RAM recommended (Tandoor + Postgres + n8n + Grocy idle around 1.5-2 GB), 8 GB free disk. |
| Docker | Docker Engine 24+ with the `docker compose` plugin (v2). |
| Host tools | `python3` (3.9+, standard library only), `bash`, `curl`. For `scripts/harness.sh` also `jq` and `sqlite3`. |
| n8n version | Tested with n8n 2.43 (`n8nio/n8n:latest`). The generated nodes need a recent 2.x: with 2.32 the workflows import but fail to activate (`Cannot read properties of undefined (reading 'execute')`) because some node versions are missing. `docker compose pull n8n` fixes it. |
| Accounts | A Telegram account, an [OpenRouter](https://openrouter.ai) API key (or another OpenAI-compatible endpoint with JSON-schema structured output and image input). |
| Network | Outbound HTTPS to `api.telegram.org` and the LLM endpoint. No inbound ports are required. |

Clone the repository on the host and work from its root:

```bash
git clone <this repo> pi-kitchen-assistant && cd pi-kitchen-assistant
cp .env.example .env && chmod 600 .env
```

Fill `.env` as you progress. Generate secrets with `openssl rand -hex 24` (webhook secret) and
`openssl rand -hex 32` (`TANDOOR_SECRET_KEY`, `TANDOOR_DB_PASSWORD`).
`.env` is read by `docker compose` and sourced by the scripts, so quote values with spaces.

## 2. Telegram

1. **Create the bot.** In Telegram open `@BotFather`, send `/newbot`, choose a name and a username. Copy the token into
   `TELEGRAM_KITCHEN_BOT_TOKEN`.
2. **Group messages.** If you want to use the bot in a group, send `/setprivacy` to BotFather, pick your bot and choose
   **Disable**. With privacy mode on, the bot only sees commands in groups, not free text like "I cooked lentils for 4".
   If the bot was already in the group when you changed it, remove and re-add it.
3. **Create the group** (optional, a private chat with the bot also works), add the bot and everyone who should use it.
4. **Find the chat IDs.** Start only the bridge with an empty allow-list. It logs every chat it rejects:
   ```bash
   # in .env: KITCHEN_ALLOWED_CHAT_IDS=   (empty)   and a real TELEGRAM_KITCHEN_BOT_TOKEN
   docker compose -f docker-compose.example.yml up -d tg-kitchen-bridge
   # now write "hi" to the bot (private chat) and in the group
   docker logs tg-kitchen-bridge 2>&1 | grep dropped
   # -> dropped update 123 from unauthorized chat -987654321
   ```
   Private chat IDs are positive numbers; group IDs are negative. If a group is later upgraded to a supergroup, its ID
   changes to `-100...` and you must update the allow-list.
   (The bridge needs `n8n` only to forward; with an empty allow-list nothing is forwarded, so it can run before n8n exists.
   `depends_on: [n8n]` will start n8n as well, which is fine.)
5. **Allow the chats.** Put the IDs, comma separated, in `KITCHEN_ALLOWED_CHAT_IDS` (who may talk to the bot) and
   `KITCHEN_CHAT_IDS` (who receives scheduled messages, usually the group). Recreate the bridge:
   `docker compose -f docker-compose.example.yml up -d --force-recreate tg-kitchen-bridge`.
6. **Command menu** (optional): `scripts/set_bot_commands.sh` registers `/menu /propuesta /batch /lista /casa /ayuda`.
   The router strips the `@botname` suffix Telegram adds in groups.

## 3. Start the stack

```bash
docker compose -f docker-compose.example.yml up -d
docker compose -f docker-compose.example.yml ps
```

By default the UIs are published on `127.0.0.1` only (`BIND_ADDR`): Grocy `:9283`, Tandoor `:8095`, n8n `:5678`.
To reach them from your laptop either use an SSH tunnel (`ssh -L 9283:localhost:9283 -L 8095:localhost:8095 -L 5678:localhost:5678 host`)
or set `BIND_ADDR` to the host's LAN/VPN address. Persistent data goes to `./data/` (Grocy config + SQLite, Tandoor
Postgres and media, bridge offset) and the `n8n-data` Docker volume.

Set `TANDOOR_ORIGIN` to the exact URL you type in the browser (for example `http://<host-ip>:8095` or your VPN
hostname) before the first start; otherwise Tandoor's CSRF check rejects logins and form posts.

## 4. First run of each service

### Grocy

1. Open `http://<host>:9283/` **once** before using the API (the first page view creates the database). Log in with
   `admin` / `admin` and change the password immediately (user menu, "Change password").
2. Create the API key: user menu -> **Manage API keys** -> **Add**. Copy the key into `GROCY_API_KEY`.
3. Check: `curl -H "GROCY-API-KEY: $KEY" http://localhost:9283/api/system/info`.

### Tandoor

1. Open `http://<host>:8095/`. On a fresh database it redirects to `/setup/`: create the admin user.
2. **Log in once in the browser.** The first login creates your *space*; before that the API answers 403 for everything.
3. Create an API token and copy it into `TANDOOR_API_TOKEN`. Either in the UI (Settings -> API) with scope
   `read write`, or:
   ```bash
   curl -s -X POST http://localhost:8095/api-token-auth/ -d 'username=<admin>&password=<password>'
   # {"id":..,"token":"tda_xxx",...}
   ```
   It is used as `Authorization: Bearer <token>`.
4. If the API still answers 403 right after the first login, wait 30 seconds without sending requests (in the tested version Tandoor caches
   group lookups per worker for 30 s, and repeated failed calls keep refreshing the stale entry).

### n8n

1. Open `http://<host>:5678/` and create the **owner account** (e-mail + password). There is no basic-auth variable in
   recent n8n versions; the owner account is the login.
2. Nothing else is needed in the UI. Credentials and workflows are created from the command line in step 7.
   (Scripted alternative for CI: `POST /rest/owner/setup` with `{"email","firstName","lastName","password"}`.)

## 5. Master data the generator expects

The workflows address Grocy and Tandoor objects **by name**. The names are Spanish defaults used by the prompts, the
bot messages and the matching code. Create them with the idempotent seed script (safe to run repeatedly):

```bash
python3 scripts/seed_master_data.py --dry-run   # prints what it would create
python3 scripts/seed_master_data.py
```

Needs `GROCY_BASE_URL`, `GROCY_API_KEY`, `TANDOOR_BASE_URL`, `TANDOOR_API_TOKEN` and `KITCHEN_CHAT_IDS` in `.env`
(or exported). What it creates:

| System | Object | Names |
|---|---|---|
| Grocy | Locations | `Nevera`, `Despensa`, `Congelador` |
| Grocy | Quantity units | `Unidad` (plural `Unidades`), `Paquete`, `kg`, `g`, `l`, `ml` |
| Grocy | Product groups (aisles) | `Frutas y Verduras`, `Panadería`, `Carne`, ... (full list in `CATEGORIES` in `generator/build_kitchen_router.py`) |
| Grocy | Product userfields | `ticket_aliases` (text, multi-line): receipt names learned per product. `tandoor_food_id` (integer): link Grocy product -> Tandoor food |
| Tandoor | Meal types | `Comida`, `Cena`, `Desayuno`, `Merienda` (matched case-insensitively) |
| Tandoor | Supermarket categories | the same names as the Grocy product groups |
| Tandoor | User preference | `mealplan_autoadd_shopping = true`, `mealplan_autoexclude_onhand = false` (the bot annotates what is at home itself) |

Created automatically at runtime, no action needed: Grocy **stores** (shopping locations are created from receipts),
Grocy products, Tandoor foods and units used by recipes.

Manual steps and conventions:

- **Different names or language.** Locations, units and aisles are literals in the generator and in the Code-node
  JavaScript. To use other names, edit `LOCATIONS`, `UNITS`, `CATEGORIES` and the literals `'Nevera'`, `'Despensa'`,
  `'Congelador'`, `'Unidad'` in `generator/build_kitchen_router.py`, then re-seed and regenerate. Bot messages are
  Spanish strings in the same file (see "Internationalisation" in the README).
- **Recipe keywords** drive the planner: `comida-batch` (lunch, batch cooked), `cena` (quick dinner), `desayuno`,
  `merienda`, plus optional `fácil`, `fin-de-semana`, `prep-domingo`, `dulce`, `salado`, `congelable`, `temporada-otoño`.
  The bot adds `generada` (recipes it writes) and `sesion-batch` (the Sunday session recipe, excluded from menus).
  `recipes/sample_recipes.py` shows the format; load a pack with `python3 recipes/load_recipes.py [module]`.
  `recipes/enrich_recipes.py preview|apply <recipe>` rewrites a recipe into structured steps with an LLM (needs
  `OPENROUTER_API_KEY`); `apply --pending` is cron friendly.
- **Pantry staples** (salt, oil, water...) should be marked `ignore_shopping` on the Tandoor food so they never reach the
  shopping list (Tandoor UI: Food -> edit -> "Ignore shopping").

## 6. LLM provider and models

1. Create an OpenRouter key and put it in `OPENROUTER_API_KEY`.
2. Models are plain OpenRouter ids set in `.env` and baked into the workflows at generation time:
   `KITCHEN_MODEL` (receipts, intents, proposals, edits, new recipes) and `KITCHEN_GUIDE_MODEL` (Sunday session plan,
   recipe enrichment via `ENRICH_MODEL`). Requirements: image input for receipts, JSON-schema structured outputs
   (`response_format: json_schema`). In the author's tests the cheapest "flash-lite" class model was fine for
   extraction and intents but produced HTML entities and wrong ingredient assignments for the batch plan and recipe
   rewriting, so the guide model is one tier up.
3. To swap models or provider: change `KITCHEN_MODEL` / `KITCHEN_GUIDE_MODEL` (and `OPENROUTER_API_URL` for another
   OpenAI-compatible endpoint), then regenerate and redeploy (step 7). Receipt reading and batch guides are the
   calls most sensitive to model quality.

## 7. n8n credentials, generation and deploy

The generated nodes reference credentials by **id and name**. `scripts/create_credentials.sh` creates all five with those
ids through the n8n CLI (secrets come from `.env`; the temporary file is private and removed afterwards).

| Credential (default name) | n8n type | Fixed id (default) | Content | Used by |
|---|---|---|---|---|
| `Kitchen bot` | Telegram API (`telegramApi`) | `KitchenTgBot0001` | `accessToken` = bot token | every Telegram node |
| `Grocy API` | Header Auth (`httpHeaderAuth`) | `KitchenGrocy0001` | header `GROCY-API-KEY: <key>` | Grocy HTTP nodes |
| `Tandoor API` | Header Auth | `KitchenTandoor01` | header `Authorization: Bearer <token>` | Tandoor HTTP nodes |
| `OpenRouter` | Header Auth | `KitchenORouter01` | header `Authorization: Bearer <key>` | LLM HTTP nodes |
| `Kitchen bridge secret` | Header Auth | `KitchenBridge001` | header `X-Kitchen-Secret: <secret>` | the webhooks (header auth) |

Override ids/names with `N8N_CRED_<TELEGRAM|GROCY|TANDOOR|OPENROUTER|BRIDGE>_<ID|NAME>` in `.env`; they are read by both
the creator script and the generator, so they always agree. Creating the credentials in the UI also works, but n8n
generates random ids; the generated workflows would then not find them. Use the script (re-running it updates the
existing credentials).

```bash
scripts/create_credentials.sh        # credentials, from .env
scripts/build.sh                     # generates build/kitchen-*.json from the environment
scripts/deploy.sh \
  build/kitchen-router.json  KitchenRouter001 \
  build/kitchen-onhand.json  KitchenOnhand001 \
  build/kitchen-expiry.json  KitchenExpiry001 \
  build/kitchen-monthly.json KitchenMonthly01
```

What `deploy.sh` does for every pair: `docker cp` the JSON into the n8n container, `n8n import:workflow`,
`n8n publish:workflow --id` (falls back to `update:workflow --active=true` on n8n 1.x). Then it restarts n8n
(publishing only takes effect after a restart) and polls until the router webhook answers `Authorization data is wrong!`
to an unauthenticated POST, which proves the route is live (n8n writes webhook rows before it serves them).
`build/kitchen-weekly.json` is an older Sunday reminder that the router's own planner replaced; it is generated but not
deployed by default.

Workflow ids are stable, so redeploying replaces the workflow in place. Importing a workflow into an existing n8n keeps
its credentials; the week/pending-ticket state lives in the workflow's static data (see Limitations in the README),
so take a `snapshot` before large redeploys (below).

## 8. Verify

1. **Services and webhooks**
   ```bash
   curl -s -X POST http://localhost:5678/webhook/kitchen-telegram          # -> Authorization data is wrong!
   curl -s -X POST http://localhost:5678/webhook/kitchen-telegram \
     -H "X-Kitchen-Secret: $KITCHEN_WEBHOOK_SECRET" -H 'Content-Type: application/json' \
     -d '{"update_id":1,"message":{"message_id":1,"chat":{"id":<chat id>,"type":"private"},"from":{"first_name":"Tester"},"text":"/ayuda"}}'
   # -> {"message":"Workflow was started"}
   ```
2. **Harness** (`scripts/harness.sh`) sends a simulated update to the webhook, waits for the execution to finish and
   prints the messages the workflow would send:
   ```bash
   scripts/harness.sh text "/ayuda"                       # help text
   scripts/harness.sh text "what do I have in the fridge?"   # intent: stock (needs the LLM key)
   scripts/harness.sh photo ticket.jpg "supermarket"      # test receipt photo (needs bot token + LLM key)
   scripts/harness.sh cb "ok:<key>"                       # press the Save button of a pending ticket
   scripts/harness.sh job kitchen-job-expiry KitchenExpiry001
   scripts/harness.sh job kitchen-job-planner KitchenRouter001 '{"action":"propose","chat":<your private chat id>}'
   ```
   `photo` uploads the file to the allowed chat to get a Telegram `file_id`, so the image really appears there.
   The harness reads n8n's SQLite file from the Docker volume: that path is root-owned, hence the default `sudo`
   (`HARNESS_SUDO=` if your user can read it, or `N8N_SQLITE=<copy>`). Always read the database *with its `-wal` and
   `-shm` files* (copying only `database.sqlite` shows stale data; opening in place with `sqlite3 -readonly` is fine).
3. **Smoke checklist**
   - `/ayuda` returns the help text in the chat.
   - A receipt photo returns a summary with Save / Discard; Save writes products and stock into Grocy.
   - "I cooked lentils for 4" (Spanish: "he cocinado lentejas para 4") offers to consume ingredients and store portions.
   - The planner `propose` job above sends a menu with Accept / Another proposal buttons (needs recipes in Tandoor:
     load some with `recipes/load_recipes.py` and have the keywords from step 5).
   - **Dry run of the weekly plan without touching the real week:** `{"action":"snapshot"}` saves the current week, then
     experiment, then `{"action":"restore"}` brings it back. Send either with `harness.sh job kitchen-job-planner KitchenRouter001 '{...}'`.

## 9. Scheduled jobs

All times are in `KITCHEN_TIMEZONE` (baked into each workflow's settings).

| Workflow | Trigger | What it does | Where to change |
|---|---|---|---|
| Router | Friday 09:00 | Proposes next week's menu (skips a week already accepted, notifies instead) | `sched("Friday 09:00", ...)` in `build_kitchen_router.py` |
| Router | Sunday 10:00 | Batch-cooking session guide + Tandoor session recipe | `sched("Sunday 10:00", ...)` |
| Router | Daily 23:30 | Consumes the planned dinner, breakfast and snack from Grocy | `sched("Daily 23:30", ...)` |
| On-hand sync | Every 30 minutes | Grocy stock -> Tandoor "on hand" flags (via `tandoor_food_id`) | `schedule("Every 30 min", ...)` in `build_kitchen_jobs.py` |
| Expiry alert | Daily 09:00 | Items due within `DUE_DAYS` (3) or expired; silent if nothing is due | `schedule("Daily 09:00", ...)`, `DUE_DAYS` |
| Monthly spend | 1st of month 09:30 | Spend by store, aisle and top products vs previous month | `schedule("1st 09:30", ...)` |

Edit the `field`, `triggerAtDay` (0 = Sunday), `triggerAtHour` / `triggerAtMinute` values, then `scripts/build.sh` and
`scripts/deploy.sh`. Editing triggers in the n8n UI works too but is overwritten by the next deploy.
Every job also has a header-auth webhook for manual runs: `kitchen-job-onhand`, `kitchen-job-expiry`,
`kitchen-job-monthly`, `kitchen-job-weekly` and `kitchen-job-planner` (actions `propose | guide | reset | dinner | snapshot | restore | set_week`).

Optional hourly enrichment of new Tandoor recipes (cron on the host):

```cron
23 * * * *  cd /path/to/pi-kitchen-assistant/recipes && set -a && . ../.env && set +a && python3 enrich_recipes.py apply --pending >> /var/log/enrich.log 2>&1
```

## 10. Security notes

- **No inbound ports for the bot.** The bridge long-polls Telegram, drops updates from chats outside
  `KITCHEN_ALLOWED_CHAT_IDS` and forwards the rest to `http://n8n:5678/...` on the internal Docker network with the
  shared secret header. The n8n webhooks require that header (header-auth credential).
- **Keep the web UIs private.** Grocy, Tandoor and n8n have weak or default login surfaces (Grocy ships `admin`/`admin`).
  Leave `BIND_ADDR=127.0.0.1` or bind to a VPN/tailnet address and put a reverse proxy with an IP allow-list in front;
  do not port-forward them to the Internet. Restrict `TANDOOR_ALLOWED_HOSTS`.
- **Secrets only in `.env`** (mode 600, git-ignored) and in n8n's encrypted credential store. `create_credentials.sh`
  never leaves a plaintext file behind. Rotate by editing `.env`, re-running the script and restarting.
- **The LLM sees receipts and your pantry.** Receipt images, stock names and recipes are sent to the configured provider.
- Anyone in an allowed chat can use every command, including consuming stock and saving receipts.
- Back up `./data/` and the `n8n-data` volume (they hold your data and the planner state).

## 11. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Grocy `POST /login` returns 500 on the very first run | The database is created on the first normal page view; open `/` once, then log in. |
| Tandoor API answers 403 for everything | No space yet (log in once in the browser), or a stale 30 s group cache; wait without calling. |
| Tandoor rejects logins/forms (CSRF) | `TANDOOR_ORIGIN` does not match the URL in your browser. |
| Workflows import but webhooks stay "not registered" | Not published/restarted, or n8n too old (`docker logs n8n` shows `Issue on initial workflow activation`). Upgrade n8n, re-run `scripts/deploy.sh`. |
| Deploy hangs at the end | The router webhook never went live; check `docker logs n8n` for activation errors and that `KITCHEN_WEBHOOK_PATH` matches. |
| Bot does not react in a group | Privacy mode still on (`/setprivacy` -> Disable, re-add the bot) or the group ID is not in `KITCHEN_ALLOWED_CHAT_IDS` (check `docker logs tg-kitchen-bridge` for `dropped update`). |
| Group stopped working after an upgrade to supergroup | The chat ID changed to `-100...`; update both chat ID variables and regenerate. |
| Grocy returns 500 `product_id on null` on stock writes | Concurrent writes make `GetCurrentStock` fail and Grocy rolls the write back. All Grocy write nodes are therefore sent one at a time (batch size 1, 700 ms interval) with 3 retries. Do not "optimise" this away. |
| Fresh tomatoes show as "at home" because a can of crushed tomatoes is in stock | Name matching refuses pairs where only one side has a processed-form word (crushed, smoked, cooked, stock, cream...). Extend `FORMW` in the generators if you hit new cases, and rebuild the product links. |
| A scheduled proposal replaced the week you accepted | Fixed in the generator: scheduled proposals skip accepted weeks and notify. Never overwrite an accepted week from automation; only explicit user requests may. Use `snapshot` / `restore` before experiments. |
| Execution data unreadable or stale when debugging | n8n's SQLite runs in WAL mode: read it together with `database.sqlite-wal` and `-shm`, never only the main file. |
| `publish:workflow` seems to do nothing | n8n has to be restarted for publishing to take effect, and the output must not be piped to `head` (it can kill the command mid-publish). `deploy.sh` handles both. |
| LLM output contains `&amp;`-style entities or bad ingredient assignment | Use a stronger `KITCHEN_GUIDE_MODEL`; the batch plan falls back to putting every ingredient on the first step when validation fails. |

## 12. Environment variable reference

Every variable read by the generator, bridge, scripts, recipes tooling and compose file is documented, with its default,
in [`.env.example`](../.env.example). Required without a default: `TELEGRAM_KITCHEN_BOT_TOKEN`, `KITCHEN_CHAT_IDS`
(generator), `KITCHEN_ALLOWED_CHAT_IDS` and `KITCHEN_WEBHOOK_SECRET` (bridge), `GROCY_API_KEY`, `TANDOOR_API_TOKEN`,
`OPENROUTER_API_KEY`, `TANDOOR_DB_PASSWORD`, `TANDOOR_SECRET_KEY`.
