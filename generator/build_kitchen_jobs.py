import json
import os
import sys
import uuid

from build_kitchen_router import (CHAT_IDS, CRED_BRIDGE, CRED_GROCY, CRED_TANDOOR, CRED_TG, GROCY, NORM_JS, TANDOOR,
                                  TIMEZONE, code, http, node)

DUE_DAYS = 3

SIMILAR_JS = r"""
const STOP = new Set(['de', 'del', 'la', 'el', 'los', 'las', 'en', 'con', 'y', 'al', 'lata', 'bote']);
const words = s => norm(s).split(' ').filter(w => w && !STOP.has(w)).map(w => w.length > 3 ? w.replace(/(es|s)$/, '') : w);
const FORMW = new Set(['triturado', 'frito', 'concentrado', 'seco', 'molido', 'polvo', 'congelado', 'zumo', 'jugo', 'salsa', 'crema', 'caldo', 'pure', 'deshidratado', 'ahumado', 'tostado', 'cocido', 'encurtido', 'escabeche', 'desecado', 'rallado']);
// a processed form (crushed, canned, smoked, cooked...) on only one side means a different product
const formClash = (a, b) => a.some(w => FORMW.has(w) && !b.includes(w)) || b.some(w => FORMW.has(w) && !a.includes(w));
const similar = (food, product) => {
  const f = words(food), pl = words(product), p = new Set(pl);
  if (formClash(f, pl)) return 0;
  return f.length ? f.filter(w => p.has(w)).length / f.length : 0;
};
"""

RECIPIENTS = f"const RECIPIENTS = {json.dumps(CHAT_IDS)};\n"


def schedule(name, pos, rule):
    return node(name, "n8n-nodes-base.scheduleTrigger", 1.2, pos, {"rule": {"interval": [rule]}})


def manual_hook(name, pos, path):
    return node(name, "n8n-nodes-base.webhook", 2.1, pos, {
        "httpMethod": "POST", "path": path, "authentication": "headerAuth",
        "responseMode": "onReceived", "options": {}}, credentials=CRED_BRIDGE,
        webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, f"kitchen/{path}")))


def get(name, pos, url, cred):
    return http(name, pos, url, cred, once=True, always=True)


def paginated(n):
    n["parameters"]["options"] = {"pagination": {"pagination": {
        "paginationMode": "responseContainsNextURL", "nextURL": "={{ $response.body.next }}",
        "paginationCompleteWhen": "other", "completeExpression": "={{ !$response.body.next }}",
        "limitPagesFetched": True, "maxRequests": 20}}}
    return n


def tg_broadcast(name, pos):
    return node(name, "n8n-nodes-base.telegram", 1.2, pos, {
        "chatId": "={{ $json.chat_id }}", "text": "={{ $json.text }}",
        "additionalFields": {"appendAttribution": False}}, credentials=CRED_TG, onError="continueRegularOutput")


def chain(*names):
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(names, names[1:])}


def workflow(wid, name, nodes, connections):
    return {"id": wid, "name": name, "active": False, "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "all", "saveDataErrorExecution": "all",
                         "timezone": TIMEZONE}, "pinData": {}}


def triggered(entry, triggers):
    return {t: {"main": [[{"node": entry, "type": "main", "index": 0}]]} for t in triggers}


# ---------------------------------------------------------------- T4 on-hand sync
ONHAND_PLAN = NORM_JS + SIMILAR_JS + r"""
const entries = $('Grocy stock').all().map(i => i.json).filter(e => e && e.product_id);
const products = $('Grocy products').all().map(i => i.json).filter(p => p && p.id);
const foods = $('Tandoor foods').all().flatMap(i => i.json.results || []);
const inStock = new Set(entries.filter(e => Number(e.amount) > 0).map(e => e.product_id));
const foodById = new Map(foods.map(f => [f.id, f]));
const out = [];
const linked = new Map();
const base = name => String(name || '').replace(/\s*\([^)]*\)\s*/g, ' ').trim();
const pick = (cands, key) => cands.filter(f => similar(key(f), p_name) === 1)
  .sort((a, b) => words(key(b)).length - words(key(a)).length || key(a).length - key(b).length)[0];
let p_name = '';
for (const p of products) {
  let fid = Number((p.userfields || {}).tandoor_food_id) || null;
  if (/\(raci[oó]n\)/i.test(p.name)) {
    if (fid) out.push({ json: { target: 'grocy', product_id: p.id, body: { tandoor_food_id: null }, label: `${p.name} (ración): sin enlace` } });
    continue;
  }
  if (!fid || !foodById.has(fid)) {
    p_name = p.name;
    const exact = foods.find(f => norm(f.name) === norm(p.name) || norm(f.plural_name) === norm(p.name));
    const best = exact || pick(foods, f => f.name) || pick(foods, f => base(f.name));
    if (best) {
      fid = best.id;
      out.push({ json: { target: 'grocy', product_id: p.id, body: { tandoor_food_id: fid }, label: `${p.name} → ${best.name}` } });
    } else fid = null;
  }
  if (fid) linked.set(fid, (linked.get(fid) || false) || inStock.has(p.id));
}
for (const f of foods) {
  const has = linked.get(f.id) || false;
  if (Boolean(f.food_onhand) !== has) out.push({ json: { target: 'tandoor', food_id: f.id, body: { food_onhand: has }, label: `${f.name}: ${has ? 'en casa' : 'agotado'}` } });
}
return out;
"""

ONHAND_ROUTE = {"rules": {"values": [
    {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict", "version": 2}, "combinator": "and",
                    "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json.target }}", "rightValue": t,
                                    "operator": {"type": "string", "operation": "equals"}}]},
     "renameOutput": True, "outputKey": t} for t in ("grocy", "tandoor")]}, "options": {}}

onhand_nodes = [
    schedule("Every 30 min", [0, 0], {"field": "minutes", "minutesInterval": 30}),
    manual_hook("Run now", [0, 180], "kitchen-job-onhand"),
    get("Grocy stock", [260, 80], f"{GROCY}/objects/stock", CRED_GROCY),
    get("Grocy products", [520, 80], f"{GROCY}/objects/products", CRED_GROCY),
    paginated(get("Tandoor foods", [780, 80], f"{TANDOOR}/food/?page_size=200", CRED_TANDOOR)),
    code("Sync plan", [1040, 80], ONHAND_PLAN),
    node("Target", "n8n-nodes-base.switch", 3.2, [1300, 80], ONHAND_ROUTE),
    http("Link food in Grocy", [1560, 0], f"={{{{ '{GROCY}/userfields/products/' + $json.product_id }}}}", CRED_GROCY,
         method="PUT", body="={{ JSON.stringify($json.body) }}", on_error="continueRegularOutput"),
    http("Set on-hand in Tandoor", [1560, 180], f"={{{{ '{TANDOOR}/food/' + $json.food_id + '/' }}}}", CRED_TANDOOR,
         method="PATCH", body="={{ JSON.stringify($json.body) }}", on_error="continueRegularOutput"),
]
onhand_conn = {**triggered("Grocy stock", ["Every 30 min", "Run now"]),
               **chain("Grocy stock", "Grocy products", "Tandoor foods", "Sync plan", "Target"),
               "Target": {"main": [[{"node": "Link food in Grocy", "type": "main", "index": 0}],
                                   [{"node": "Set on-hand in Tandoor", "type": "main", "index": 0}]]}}

# ---------------------------------------------------------------- T5 weekly reminder
WEEKLY = NORM_JS + RECIPIENTS + r"""
const plans = ($('Tandoor meal plan').first().json.results || $('Tandoor meal plan').first().json || []);
const entries = ($('Tandoor shopping').first().json.results || []).filter(e => !e.checked);
const days = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
let text = '📅 Semana que viene\n';
const list = Array.isArray(plans) ? plans : [];
if (!list.length) text += 'No hay nada planificado. Abre Tandoor → Plan de comidas y elige recetas: la lista de la compra se llena sola con lo que falte.\n';
else {
  for (const p of list.sort((a, b) => String(a.from_date).localeCompare(String(b.from_date)))) {
    const d = new Date(p.from_date);
    text += `• ${days[d.getDay()]} ${p.meal_type_name || ''}: ${p.recipe_name || p.title}${p.servings ? ` (${num(p.servings)})` : ''}\n`;
  }
}
const groups = {};
for (const e of entries) {
  const cat = (e.food && e.food.supermarket_category && e.food.supermarket_category.name) || 'Otros';
  const amount = e.amount ? `${num(e.amount)} ${e.unit ? e.unit.name : ''}`.trim() : '';
  (groups[cat] ||= []).push(`• ${e.food ? e.food.name : '?'}${amount ? ` — ${amount}` : ''}`);
}
text += entries.length
  ? `\n🛒 Lista de la compra (${entries.length}, sin lo que ya tienes)\n\n` + Object.entries(groups).map(([k, v]) => `${k}\n${v.join('\n')}`).join('\n\n')
  : '\n🛒 La lista de la compra está vacía.';
return RECIPIENTS.map(chat_id => ({ json: { chat_id, text: text.slice(0, 4000) } }));
"""

WEEK_RANGE = ("={{ '" + TANDOOR + "/meal-plan/?page_size=100&from_date=' + $now.plus({days: 1}).toFormat('yyyy-LL-dd')"
              " + '&to_date=' + $now.plus({days: 7}).toFormat('yyyy-LL-dd') }}")

weekly_nodes = [
    schedule("Sunday 10:00", [0, 0], {"field": "weeks", "weeksInterval": 1, "triggerAtDay": [0], "triggerAtHour": 10}),
    manual_hook("Run now", [0, 180], "kitchen-job-weekly"),
    get("Tandoor meal plan", [260, 80], WEEK_RANGE, CRED_TANDOOR),
    get("Tandoor shopping", [520, 80], f"{TANDOOR}/shopping-list-entry/?page_size=500", CRED_TANDOOR),
    code("Weekly message", [780, 80], WEEKLY),
    tg_broadcast("Send weekly", [1040, 80]),
]
weekly_conn = {**triggered("Tandoor meal plan", ["Sunday 10:00", "Run now"]),
               **chain("Tandoor meal plan", "Tandoor shopping", "Weekly message", "Send weekly")}

# ---------------------------------------------------------------- T6 expiry alert
EXPIRY_PLAN = NORM_JS + r"""
const v = $('Grocy volatile').first().json;
const products = Object.fromEntries($('Grocy products').all().map(i => [i.json.id, i.json]));
const rows = [
  ...(v.expired_products || []).map(x => ({ ...x, state: 'expired' })),
  ...(v.overdue_products || []).map(x => ({ ...x, state: 'overdue' })),
  ...(v.due_products || []).map(x => ({ ...x, state: 'due' })),
].sort((a, b) => String(a.best_before_date).localeCompare(String(b.best_before_date)));
const foodIds = [...new Set(rows.map(r => Number(((products[r.product_id] || {}).userfields || {}).tandoor_food_id)).filter(Boolean))];
return [{ json: { rows, foodIds, skip: !rows.length } }];
"""

EXPIRY_MSG = NORM_JS + RECIPIENTS + r"""
const plan = $('Expiry plan').first().json;
if (plan.skip) return [];
const units = Object.fromEntries($('Grocy units').all().map(i => [i.json.id, i.json]));
const recipes = plan.foodIds.length ? ($('Tandoor recipes').first().json.results || []) : [];
const label = { expired: '❌ Caducado', overdue: '⚠ Pasado de fecha', due: '⏳ Caduca pronto' };
const lines = plan.rows.map(r => `${label[r.state]}: ${r.product.name} ${num(r.amount)} ${qn(units[r.product.qu_id_stock], r.amount)} (${fdate(r.best_before_date)})`);
let text = `🧊 Revisión de la despensa\n\n${lines.join('\n')}`;
if (recipes.length) text += `\n\n🍳 Recetas para aprovecharlo:\n${recipes.slice(0, 5).map(r => `• ${r.name}`).join('\n')}`;
text += '\n\nCuando lo uses, dímelo ("me he comido…") o márcalo en Grocy.';
return RECIPIENTS.map(chat_id => ({ json: { chat_id, text: text.slice(0, 4000) } }));
"""

TANDOOR_RECIPES = ("={{ $json.foodIds.length ? '" + TANDOOR + "/recipe/?page_size=5&' + $json.foodIds.map(f => 'foods_or=' + f).join('&')"
                   " : '" + TANDOOR + "/recipe/?page_size=1' }}")

expiry_nodes = [
    schedule("Daily 09:00", [0, 0], {"field": "days", "daysInterval": 1, "triggerAtHour": 9}),
    manual_hook("Run now", [0, 180], "kitchen-job-expiry"),
    get("Grocy volatile", [260, 80], f"={{{{ '{GROCY}/stock/volatile?due_soon_days=' + ($json.body && $json.body.days ? $json.body.days : {DUE_DAYS}) }}}}", CRED_GROCY),
    get("Grocy products", [520, 80], f"{GROCY}/objects/products", CRED_GROCY),
    get("Grocy units", [780, 80], f"{GROCY}/objects/quantity_units", CRED_GROCY),
    code("Expiry plan", [1040, 80], EXPIRY_PLAN),
    get("Tandoor recipes", [1300, 80], TANDOOR_RECIPES, CRED_TANDOOR),
    code("Expiry message", [1560, 80], EXPIRY_MSG),
    tg_broadcast("Send expiry", [1820, 80]),
]
expiry_conn = {**triggered("Grocy volatile", ["Daily 09:00", "Run now"]),
               **chain("Grocy volatile", "Grocy products", "Grocy units", "Expiry plan", "Tandoor recipes",
                       "Expiry message", "Send expiry")}

# ---------------------------------------------------------------- T7 monthly spend
MONTHLY = NORM_JS + RECIPIENTS + r"""
const log = $('Grocy stock log').all().map(i => i.json).filter(l => l && l.transaction_type === 'purchase' && !Number(l.undone));
const products = Object.fromEntries($('Grocy products').all().map(i => [i.json.id, i.json]));
const groups = Object.fromEntries($('Grocy groups').all().map(i => [i.json.id, i.json.name]));
const stores = Object.fromEntries($('Grocy stores').all().map(i => [i.json.id, i.json.name]));
const now = new Date();
const ym = d => d.toISOString().slice(0, 7);
const ref = new Date(Date.UTC(now.getFullYear(), now.getMonth(), 1));
const target = $('Run now').isExecuted && $('Run now').first().json.body && $('Run now').first().json.body.month
  ? $('Run now').first().json.body.month
  : ym(new Date(Date.UTC(ref.getUTCFullYear(), ref.getUTCMonth() - 1, 1)));
const [ty, tm] = target.split('-').map(Number);
const prev = ym(new Date(Date.UTC(ty, tm - 2, 1)));
const spend = l => Number(l.amount || 0) * Number(l.price || 0);
const month = l => String(l.purchased_date || l.row_created_timestamp || '').slice(0, 7);
const cur = log.filter(l => month(l) === target);
const before = log.filter(l => month(l) === prev);
const total = cur.reduce((a, l) => a + spend(l), 0);
const totalPrev = before.reduce((a, l) => a + spend(l), 0);
const sumBy = (rows, key) => Object.entries(rows.reduce((acc, l) => { const k = key(l); acc[k] = (acc[k] || 0) + spend(l); return acc; }, {}))
  .sort((a, b) => b[1] - a[1]);
const byStore = sumBy(cur, l => stores[l.shopping_location_id] || 'Sin tienda');
const byGroup = sumBy(cur, l => groups[(products[l.product_id] || {}).product_group_id] || 'Sin grupo');
const byProduct = sumBy(cur, l => (products[l.product_id] || {}).name || `#${l.product_id}`);
const months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
let text = `💶 Gasto de ${months[tm - 1]} ${ty}: ${eur(total)}`;
if (totalPrev > 0) {
  const pct = Math.round((total - totalPrev) / totalPrev * 100);
  text += ` (${pct >= 0 ? '+' : ''}${pct}% vs ${months[(tm + 10) % 12]})`;
}
if (!cur.length) text += '\nNo hay compras con precio registradas ese mes.';
else {
  text += `\n\n🏪 Por tienda\n${byStore.map(([k, v]) => `• ${k}: ${eur(v)}`).join('\n')}`;
  text += `\n\n🧺 Por pasillo\n${byGroup.slice(0, 8).map(([k, v]) => `• ${k}: ${eur(v)}`).join('\n')}`;
  text += `\n\n🔝 Productos con más gasto\n${byProduct.slice(0, 5).map(([k, v]) => `• ${k}: ${eur(v)}`).join('\n')}`;
}
return RECIPIENTS.map(chat_id => ({ json: { chat_id, text: text.slice(0, 4000) } }));
"""

monthly_nodes = [
    schedule("1st 09:30", [0, 0], {"field": "months", "monthsInterval": 1, "triggerAtDayOfMonth": 1,
                                    "triggerAtHour": 9, "triggerAtMinute": 30}),
    manual_hook("Run now", [0, 180], "kitchen-job-monthly"),
    get("Grocy stock log", [260, 80], f"{GROCY}/objects/stock_log", CRED_GROCY),
    get("Grocy products", [520, 80], f"{GROCY}/objects/products", CRED_GROCY),
    get("Grocy groups", [780, 80], f"{GROCY}/objects/product_groups", CRED_GROCY),
    get("Grocy stores", [1040, 80], f"{GROCY}/objects/shopping_locations", CRED_GROCY),
    code("Monthly message", [1300, 80], MONTHLY),
    tg_broadcast("Send monthly", [1560, 80]),
]
monthly_conn = {**triggered("Grocy stock log", ["1st 09:30", "Run now"]),
                **chain("Grocy stock log", "Grocy products", "Grocy groups", "Grocy stores", "Monthly message",
                        "Send monthly")}

WORKFLOWS = {
    "onhand": workflow("KitchenOnhand001", "Kitchen - On-hand sync", onhand_nodes, onhand_conn),
    "weekly": workflow("KitchenWeekly001", "Kitchen - Weekly plan", weekly_nodes, weekly_conn),
    "expiry": workflow("KitchenExpiry001", "Kitchen - Expiry alert", expiry_nodes, expiry_conn),
    "monthly": workflow("KitchenMonthly01", "Kitchen - Monthly spend", monthly_nodes, monthly_conn),
}

if __name__ == "__main__":
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    for key, wf in WORKFLOWS.items():
        with open(os.path.join(out_dir, f"kitchen-{key}.json"), "w") as f:
            json.dump([wf], f, ensure_ascii=False, indent=1)
        print(f"kitchen-{key}.json {wf['id']} nodes={len(wf['nodes'])}")
