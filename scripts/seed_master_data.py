#!/usr/bin/env python3
"""Idempotently create the master data the generated workflows expect in Grocy and Tandoor.

Grocy:   locations, quantity units, product groups (aisles), and the two product userfields
         `ticket_aliases` (multi-line text) and `tandoor_food_id` (integer).
Tandoor: meal types (comida, cena, desayuno, merienda), supermarket categories (same names as the Grocy groups),
         and the user preferences the shopping-list flow relies on.

Environment (see .env.example): GROCY_BASE_URL, GROCY_API_KEY, TANDOOR_BASE_URL, TANDOOR_API_TOKEN, KITCHEN_CHAT_IDS.
usage: seed_master_data.py [--dry-run]
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "generator"))
from build_kitchen_router import CATEGORIES, LOCATIONS, UNITS  # noqa: E402

GROCY = os.environ.get("GROCY_BASE_URL", "http://localhost:9283").rstrip("/")
TANDOOR = os.environ.get("TANDOOR_BASE_URL", "http://localhost:8095").rstrip("/")
DRY = "--dry-run" in sys.argv

UNIT_PLURALS = {"Unidad": "Unidades", "Paquete": "Paquetes"}
MEAL_TYPES = ["Comida", "Cena", "Desayuno", "Merienda"]
USERFIELDS = [
    {"entity": "products", "name": "ticket_aliases", "caption": "Ticket aliases", "type": "text-multi-line"},
    {"entity": "products", "name": "tandoor_food_id", "caption": "Tandoor food id", "type": "number-integral"},
]


def call(base, headers, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {base}{path} -> HTTP {e.code}: {e.read().decode()[:300]}")
    except urllib.error.URLError as e:
        raise SystemExit(f"cannot reach {base}: {e.reason}")


def need(name):
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("change-me"):
        raise SystemExit(f"error: set {name} in .env first")
    return value


def seed_grocy():
    h = {"GROCY-API-KEY": need("GROCY_API_KEY")}
    api = lambda m, p, b=None: call(GROCY, h, m, "/api" + p, b)  # noqa: E731

    def ensure(entity, names, extra=lambda n: {}):
        have = {o["name"].lower() for o in api("GET", f"/objects/{entity}")}
        for name in names:
            if name.lower() in have:
                continue
            print(f"grocy + {entity}: {name}")
            if not DRY:
                api("POST", f"/objects/{entity}", {"name": name, **extra(name)})

    ensure("locations", LOCATIONS)
    ensure("quantity_units", UNITS, lambda n: {"name_plural": UNIT_PLURALS.get(n, n)})
    ensure("product_groups", CATEGORIES)
    have = {(u["entity"], u["name"]) for u in api("GET", "/objects/userfields")}
    for uf in USERFIELDS:
        if (uf["entity"], uf["name"]) not in have:
            print(f"grocy + userfield: {uf['entity']}.{uf['name']}")
            if not DRY:
                api("POST", "/objects/userfields", uf)


def seed_tandoor():
    h = {"Authorization": "Bearer " + need("TANDOOR_API_TOKEN")}
    api = lambda m, p, b=None: call(TANDOOR, h, m, "/api" + p, b)  # noqa: E731

    def listing(path):
        res = api("GET", path + "?page_size=200")
        return res["results"] if isinstance(res, dict) else res

    have = {m["name"].lower() for m in listing("/meal-type/")}
    for name in MEAL_TYPES:
        if name.lower() not in have:
            print(f"tandoor + meal-type: {name}")
            if not DRY:
                api("POST", "/meal-type/", {"name": name})
    have = {c["name"].lower() for c in listing("/supermarket-category/")}
    for name in CATEGORIES:
        if name.lower() not in have:
            print(f"tandoor + supermarket-category: {name}")
            if not DRY:
                api("POST", "/supermarket-category/", {"name": name})
    # The shopping list should list every plan ingredient (Grocy "at home" annotations are added by the workflow).
    prefs = api("GET", "/user-preference/")
    for pref in prefs if isinstance(prefs, list) else [prefs]:
        want = {"mealplan_autoadd_shopping": True, "mealplan_autoexclude_onhand": False}
        user = pref["user"]["id"] if isinstance(pref["user"], dict) else pref["user"]
        if any(pref.get(k) != v for k, v in want.items()):
            print(f"tandoor ~ user-preference (user {user}): {want}")
            if not DRY:
                api("PATCH", f"/user-preference/{user}/", want)


if __name__ == "__main__":
    seed_grocy()
    seed_tandoor()
    print("done" + (" (dry run, nothing written)" if DRY else ""))
