#!/usr/bin/env python3
"""Rewrite Tandoor recipes into detailed, structured steps without changing their ingredients.

usage: enrich_recipes.py preview|apply <recipe name or id> [...]
       enrich_recipes.py apply --all | --pending   (--pending = recipes not yet enriched; suitable for a cron job)
Environment: TANDOOR_BASE_URL, TANDOOR_API_TOKEN, OPENROUTER_API_KEY, ENRICH_MODEL, KITCHEN_HOUSEHOLD. preview prints the result and stores it in ./enriched/<id>.json; apply PATCHes Tandoor
(reusing a stored preview when present) and verifies the result.
"""
import html
import json
import os
import sys
import urllib.parse
import urllib.request

TANDOOR = os.environ.get("TANDOOR_BASE_URL", "http://localhost:8095").rstrip("/") + "/api"
TOKEN = os.environ.get("TANDOOR_API_TOKEN") or sys.exit("error: set TANDOOR_API_TOKEN")
OR_KEY = os.environ.get("OPENROUTER_API_KEY") or sys.exit("error: set OPENROUTER_API_KEY")
MODEL = os.environ.get("ENRICH_MODEL", os.environ.get("KITCHEN_GUIDE_MODEL", "google/gemini-3.8-flash"))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enriched")

HOUSEHOLD = os.environ.get("KITCHEN_HOUSEHOLD") or (
    "Household: a couple living in a Mediterranean city. Kitchen: 3 burners (large, medium, small), air fryer, rice cooker; "
    "the oven is rarely used. Lunch recipes are batch-cooked on Sunday and eaten over the week; dinners are quick; "
    "breakfasts/snacks are for one person.")

PROMPT = HOUSEHOLD + """
Rewrite the recipe into clear, detailed cooking steps in Spanish for a home cook who wants to get it right the first time.
Return JSON only. Rules:
- 4 to 9 steps. The first step is "Preparación" (mise en place: what to wash, cut and how big, what to measure, what to take out of the fridge/freezer).
- Each step: a short title, an instruction of 2-5 sentences with heat level (alto/medio/suave), the device (fogón grande/mediano/pequeño, air fryer, arrocera),
  duration and the visual/texture cue that tells it is done ("la cebolla transparente", "la salsa nappa la cuchara"). Mention quantities when useful.
- time: minutes for that step (integer, 0 if passive/instant).
- ingredients: indexes (from the given list) of the ingredients that go into the pan/bowl IN THAT STEP. The "Preparación" step has
  ingredients = [] (it only describes cutting/measuring). Every index must appear in exactly one later step.
  Do not invent ingredients; salt, pepper or water may be mentioned in the text without an index.
- Keep each pot/pan on the same burner for the whole recipe (e.g. the stew stays on the fogón grande); use another burner only for a
  genuinely separate preparation in parallel.
- Write amounts naturally ("300 g", "2 cebollas", "medio limón"), plain UTF-8 text, no HTML entities, no markdown tables.
- Keep the recipe faithful to the original dish and to the given ingredients and amounts.
- notes: for kind "comida-batch": portioning into tuppers, fridge days (max 3-4), whether/how it freezes, how to reheat without drying.
  For other kinds: storage/reheating only if relevant, plus one useful tip. 2-4 sentences."""

SIMPLE_PROMPT = HOUSEHOLD + """
This is a QUICK breakfast or snack for one person, meant to be made in under 5 minutes on a weekday, without the stove.
Rewrite it in Spanish, minimal and practical. Return JSON only. Rules:
- 2 or 3 steps in total. The first step is "Preparación" ONLY if something must be done in advance (e.g. eggs boiled on Sunday,
  oats soaked overnight); otherwise start directly with the assembly step. Never invent toasting/cooking that is not in the recipe;
  a toaster or microwave is fine if the recipe uses toasted bread.
- Each step: short title, 1-2 short sentences, time in minutes (total <= 5), ingredient indexes used in that step; every index exactly once.
- notes: one short practical tip (1 sentence).
- Plain UTF-8 text, natural amounts, no HTML entities."""

SCHEMA = {
    "name": "enriched_recipe",
    "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False, "required": ["steps", "notes"],
        "properties": {
            "steps": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["title", "instruction", "time", "ingredients"],
                "properties": {"title": {"type": "string"}, "instruction": {"type": "string"},
                               "time": {"type": "integer"}, "ingredients": {"type": "array", "items": {"type": "integer"}}}}},
            "notes": {"type": "string"},
        },
    },
}


def http(method, url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def tandoor(method, path, body=None):
    return http(method, f"{TANDOOR}{path}", body, {"Authorization": f"Bearer {TOKEN}"})


def find_recipe(ref):
    if str(ref).isdigit():
        return tandoor("GET", f"/recipe/{ref}/")
    res = tandoor("GET", f"/recipe/?page_size=10&query={urllib.parse.quote(ref)}")["results"]
    hit = next((r for r in res if r["name"].lower() == ref.lower()), res[0] if res else None)
    if not hit:
        raise SystemExit(f"recipe not found: {ref}")
    return tandoor("GET", f"/recipe/{hit['id']}/")


def is_enriched(recipe):
    steps = recipe.get("steps") or []
    if is_simple(recipe):
        # quick recipes: 2-3 named steps plus the final tip step, all titled
        return len(steps) >= 3 and all((st.get("name") or "").strip() for st in steps)
    return len(steps) >= 4 and (steps[0].get("name") or "").strip().lower() == "preparación"


def ingredients_of(recipe):
    return [g for st in recipe["steps"] for g in st.get("ingredients", []) if not g.get("is_header")]


def kind_of(recipe):
    kws = [k.get("name") or k.get("label") for k in recipe.get("keywords", [])]
    return next((k for k in kws if k in ("comida-batch", "cena", "desayuno", "merienda")), "otro")


def is_simple(recipe):
    return any((k.get("name") or k.get("label")) == "fácil" for k in recipe.get("keywords", []))


def generate(recipe):
    ings = ingredients_of(recipe)
    listing = [f"{i}: {g['amount'] or ''} {(g.get('unit') or {}).get('name', '')} {g['food']['name']}{' (' + g['note'] + ')' if g.get('note') else ''}".replace("  ", " ")
               for i, g in enumerate(ings)]
    user = {"name": recipe["name"], "kind": kind_of(recipe), "servings": recipe["servings"],
            "ingredients": listing, "current_instructions": "\n".join(st.get("instruction") or "" for st in recipe["steps"])}
    res = http("POST", os.environ.get("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions"), {
        "model": MODEL, "temperature": 0.3,
        "messages": [{"role": "system", "content": SIMPLE_PROMPT if is_simple(recipe) else PROMPT},
                     {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
        "response_format": {"type": "json_schema", "json_schema": SCHEMA},
    }, {"Authorization": f"Bearer {OR_KEY}"})
    out = json.loads(html.unescape(res["choices"][0]["message"]["content"]))
    for st in out["steps"]:
        st["title"], st["instruction"] = html.unescape(st["title"]), html.unescape(st["instruction"])
    out["notes"] = html.unescape(out["notes"])
    out["cost"] = (res.get("usage") or {}).get("cost")
    validate(out, len(ings), simple=is_simple(recipe))
    return out


def validate(out, n, simple=False):
    used = [i for st in out["steps"] for i in st["ingredients"]]
    if sorted(used) != list(range(n)):
        missing = sorted(set(range(n)) - set(used))
        extra = sorted(i for i in set(used) if used.count(i) > 1 or i >= n)
        raise ValueError(f"ingredient assignment invalid (missing {missing}, duplicated/unknown {extra})")
    if not (2 if simple else 3) <= len(out["steps"]) <= (3 if simple else 10):
        raise ValueError(f"unexpected step count {len(out['steps'])}")


def render(recipe, out):
    lines = [f"🧑‍🍳 {recipe['name']} ({recipe['servings']} rac.)"]
    ings = ingredients_of(recipe)
    for n, st in enumerate(out["steps"], 1):
        used = ", ".join(ings[i]["food"]["name"] for i in st["ingredients"])
        lines.append(f"\n{n}. {st['title']}" + (f" · {st['time']} min" if st["time"] else ""))
        lines.append(st["instruction"])
        if used:
            lines.append(f"   ↳ {used}")
    lines.append(f"\n📝 {out['notes']}")
    return "\n".join(lines)


def apply(recipe, out):
    ings = ingredients_of(recipe)
    steps = []
    for n, st in enumerate(out["steps"]):
        steps.append({"name": st["title"], "instruction": st["instruction"], "time": max(0, int(st["time"])), "order": n,
                      "ingredients": [{**ings[i], "order": j} for j, i in enumerate(st["ingredients"])]})
    steps.append({"name": "Guardar y recalentar" if kind_of(recipe) == "comida-batch" else "Consejos",
                  "instruction": out["notes"], "time": 0, "order": len(steps), "ingredients": []})
    tandoor("PATCH", f"/recipe/{recipe['id']}/", {"steps": steps})
    after = tandoor("GET", f"/recipe/{recipe['id']}/")
    before_ing = sorted((g["food"]["id"], g["amount"], (g.get("unit") or {}).get("id")) for g in ings)
    after_ing = sorted((g["food"]["id"], g["amount"], (g.get("unit") or {}).get("id")) for g in ingredients_of(after))
    if before_ing != after_ing or len(after["steps"]) != len(steps):
        raise RuntimeError(f"verification failed for {recipe['name']}: steps {len(after['steps'])}/{len(steps)}, "
                           f"ingredients equal={before_ing == after_ing}")
    return after


FORCE = "--force" in sys.argv


def main():
    mode, refs = sys.argv[1], [a for a in sys.argv[2:] if a != "--force"]
    os.makedirs(OUT, exist_ok=True)
    if refs in (["--all"], ["--pending"]):
        listed = tandoor("GET", "/recipe/?page_size=200")["results"]
        refs = [str(r["id"]) for r in listed]
        if refs == [] or sys.argv[2] == "--pending":
            refs = [str(r["id"]) for r in listed if not is_enriched(tandoor("GET", f"/recipe/{r['id']}/"))]
            if not refs:
                return
    total = 0.0
    for ref in refs:
        recipe = find_recipe(ref)
        path = os.path.join(OUT, f"{recipe['id']}.json")
        try:
            if mode == "apply" and is_enriched(recipe) and not FORCE:
                continue
            if mode == "apply" and os.path.exists(path) and not FORCE:
                out = json.load(open(path))
            else:
                for attempt in range(2):
                    try:
                        out = generate(recipe)
                        break
                    except ValueError as e:
                        if attempt:
                            raise
                        print(f"  retry {recipe['name']}: {e}", file=sys.stderr)
                json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
            total += out.get("cost") or 0
            if mode == "preview":
                print(render(recipe, out))
                print(f"\n(cost: {out.get('cost')})\n" + "-" * 60)
            else:
                after = apply(recipe, out)
                print(f"ok {recipe['id']} {recipe['name']}: {len(after['steps'])} steps")
        except Exception as e:  # keep going with the other recipes
            print(f"FAIL {recipe['id']} {recipe['name']}: {e}", file=sys.stderr)
    print(f"total cost: {total:.4f} USD", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
