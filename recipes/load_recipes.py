#!/usr/bin/env python3
"""Idempotently load a recipe pack into Tandoor.

usage: load_recipes.py [module]   (default module: sample_recipes; must define NEW_FOODS and RECIPES)
Environment: TANDOOR_BASE_URL (default http://localhost:8095), TANDOOR_API_TOKEN.
"""
import json
import os
import urllib.parse
import urllib.request

import importlib
import sys

_pack = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else "sample_recipes")
NEW_FOODS, RECIPES = _pack.NEW_FOODS, _pack.RECIPES

BASE = os.environ.get("TANDOOR_BASE_URL", "http://localhost:8095").rstrip("/") + "/api"
TOKEN = os.environ.get("TANDOOR_API_TOKEN") or sys.exit("error: set TANDOOR_API_TOKEN")


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode()[:400]}")


def find(path, name):
    res = api("GET", f"{path}?page_size=50&query={urllib.parse.quote(name)}")
    return next((x for x in res["results"] if x["name"].lower() == name.lower()), None)


def main():
    categories = {c["name"]: c for c in api("GET", "/supermarket-category/?page_size=200")["results"]}
    for name, cat in NEW_FOODS.items():
        food = find("/food/", name)
        if not food:
            food = api("POST", "/food/", {"name": name, "supermarket_category": {"id": categories[cat]["id"], "name": cat}})
            print(f"+ food {name} [{cat}]")
        elif not food.get("supermarket_category"):
            api("PATCH", f"/food/{food['id']}/", {"supermarket_category": {"id": categories[cat]["id"], "name": cat}})
            print(f"~ food {name} -> {cat}")

    created = skipped = 0
    for r in RECIPES:
        if find("/recipe/", r["name"]):
            skipped += 1
            continue
        keywords = [r["kind"], *r["cuisine"], *r["tags"]]
        ingredients = [{
            "food": {"name": food},
            "unit": {"name": unit} if unit else None,
            "amount": amount,
            "note": note,
        } for food, amount, unit, note in r["ingredients"]]
        body = {
            "name": r["name"],
            "description": r["description"],
            "servings": r["servings"],
            "working_time": r["working"],
            "waiting_time": r["waiting"],
            "keywords": [{"name": k} for k in keywords],
            "steps": [{"name": "", "instruction": r["steps"], "ingredients": ingredients}],
            "internal": True,
        }
        res = api("POST", "/recipe/", body)
        created += 1
        print(f"+ recipe {res['id']}: {r['name']} ({r['kind']}, {r['servings']} servings)")
    print(f"created={created} skipped={skipped} total_in_pack={len(RECIPES)}")


if __name__ == "__main__":
    main()
