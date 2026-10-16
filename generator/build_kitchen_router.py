import json
import uuid

from config import (CHAT_IDS, CRED_BRIDGE, CRED_GROCY, CRED_OR, CRED_TANDOOR, CRED_TG, GROCY_URL, GUIDE_MODEL, HOUSEHOLD,
                    LOCALE_HINT, MODEL, OPENROUTER_URL, PERSONAL_NAME, PLANNER_HOOK_PATH, TANDOOR_PUBLIC_URL,
                    TANDOOR_URL, TIMEZONE, WEBHOOK_PATH)

GROCY = GROCY_URL
TANDOOR = TANDOOR_URL
NOOP = f"{GROCY}/system/info"

CATEGORIES = [
    "Frutas y Verduras", "Panadería", "Carne", "Pescados y Mariscos", "Deli", "Queso", "Lácteos",
    "Cereal", "Café y Te", "Dulces", "Untables Dulces", "Untables Salados", "Productos Secos", "Fideos",
    "Enlatados", "Aceite y Vinagre", "Condimentos y Salsas", "Hierbas y Especias", "Hornear", "Jugos",
    "Bebidas", "Alcohol", "Congelados", "Limpieza", "Higiene",
]
LOCATIONS = ["Nevera", "Despensa", "Congelador"]
UNITS = ["Unidad", "Paquete", "kg", "g", "l", "ml"]

ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ticket_name", "product_name", "quantity", "unit", "unit_price", "line_total", "discount",
                 "estimated_price", "category", "location", "best_before_days"],
    "properties": {
        "ticket_name": {"type": "string"},
        "product_name": {"type": "string"},
        "quantity": {"type": "number"},
        "unit": {"type": "string", "enum": UNITS},
        "unit_price": {"type": "number"},
        "line_total": {"type": "number"},
        "discount": {"type": "number"},
        "estimated_price": {"type": "number"},
        "category": {"type": "string", "enum": CATEGORIES},
        "location": {"type": "string", "enum": LOCATIONS},
        "best_before_days": {"type": "integer"},
    },
}

RECEIPT_PROMPT = """You read Spanish purchase receipts and photos of groceries and return structured JSON.
kind:
- grocery_receipt: itemised receipt from a supermarket, greengrocer, butcher, bakery or market stall that sells food or household goods.
- groceries_photo: a photo of purchased food/household products (no receipt), e.g. bags from a market laid on a table.
- other_receipt: restaurant, bar, café, pharmacy, fuel, clothing or any receipt that is not a grocery purchase. items=[].
- unreadable: anything else or not legible. items=[].
Receipt rules:
- One item per purchased product line. Skip totals, VAT breakdown, payment, loyalty, plastic bags and deposits.
- quantity/unit: "3 LECHE ENTERA" -> 3 Unidad. Weighed lines "PLATANO 1,234 kg x 2,10 €/kg" -> 1.234 kg, unit_price 2.10.
- Package size printed in weight/volume -> express the total in kg or l: "LENTEJA PARDINA 1KG" -> 1 kg; "2 ARROZ 500G" -> 1 kg; "ACEITE 1L" -> 1 l; "6 LECHE 1L" -> 6 l. Countable packs -> total units: "HUEVOS 12" -> 12 Unidad; "2 YOGUR PACK4" -> 8 Unidad. Use Paquete only when no size or count is printed.
- unit_price: price per resulting unit (per kg, per l or per Unidad) = line_total / quantity.
- ticket_name: only the product description as printed, without leading quantity, weight, unit price or amount ("6 LECHE ENT. HCD 1L 0,89 5,34" -> "LECHE ENT. HCD 1L"; "SALMON 0,412 kg 19,05 E/kg" -> "SALMON").
- line_total: amount printed for the line before discounts. discount: positive EUR amount of any discount/promotion line that applies to that product (e.g. "2a UNIDAD -50%" -0,45 -> 0.45), else 0.
- estimated_price: 0 for receipts.
Photo rules (groceries_photo):
- One item per distinct product visible. Estimate quantity (count units, or approximate kg for loose produce).
- ticket_name = product_name. unit_price = 0, line_total = 0, discount = 0. estimated_price = typical Spanish retail price in EUR for that quantity.
- total = 0. date = the date given by the user message.
Common rules:
- product_name: short generic Spanish name a household would use ("LECHE ENT HCD 1L" -> "Leche entera"). No brand unless it defines the product.
- category: closest supermarket aisle. location: where it is stored at home (fresh meat/fish/dairy/leafy greens -> Nevera, frozen -> Congelador, shelf-stable, cleaning, whole fruit like bananas/apples/oranges, potatoes, onions and garlic -> Despensa).
- best_before_days: realistic shelf life from purchase (fresh fish 2, minced meat 2, milk 7, eggs 28, frozen 180, pasta 365, cleaning 0).
- store: one of the allowed names when the receipt/caption matches it, else "Otro". store_name: the short commercial brand of the shop, without legal suffixes like S.A., S.L. or S.COOP.V. ("SUPERMERCADO EJEMPLO S.L." -> "Supermercado Ejemplo", "Frutas Pepe", "Mercado Central"); for photos without any hint use "Mercado".
- caption_total: total paid if the user's caption states it ("mercado 14,50" -> 14.5), else 0.
- Decimal comma becomes a decimal point. Prices in EUR. date as YYYY-MM-DD."""

INTENT_PROMPT = """You interpret short Spanish messages sent to a household kitchen bot and return JSON.
intent:
- correction: the user fixes the pending receipt shown below (change a quantity, unit, name, price, location or remove/add a line). Return the FULL corrected list in corrected_items, keeping every unchanged field and line exactly as given. Never recompute line_total, unit_price or discount when only a quantity or unit changes: the amount paid stays the same unless the user explicitly corrects a price. Map units: "unidades"/"uds" -> Unidad, "paquetes" -> Paquete, "kilos" -> kg, "litros" -> l.
- cooked: the user says they cooked a recipe ("he cocinado lentejas para 6", "cociné pollo al curry x4"). recipe_query = recipe name, servings = number of servings (0 if not stated).
- ate: the user consumed or threw away something from the pantry ("me he comido 2 yogures", "gasté 1 l de leche", "comimos lentejas" -> 1 portion). product_query, amount (default 1), unit ("" if none).
- stock: the user asks what is at home ("¿qué tengo en la nevera?", "¿me queda leche?"). product_query = product or "" for everything; location = Nevera/Despensa/Congelador or "".
- shopping: the user asks for the shopping list.
- plan: anything about the weekly menu / meal plan: show it, ask for another proposal, replace, remove, add or move a recipe, or say an ingredient cannot be found ("¿qué comemos esta semana?", "otra propuesta", "cambia la cena del martes", "quita el chili", "añade lentejas el jueves para cenar", "no encuentro gochujang"). plan_request = the user's message verbatim. A pending receipt does not change this: menu messages are plan, not correction.
- new_recipe: the user wants to add or create a recipe by name or description, without a link ("añade la receta de bacalao a la llauna", "guarda una receta de crema de calabaza para batch", "crea una receta nueva de pollo al chilindrón para cenar"). plan_request = the user's message verbatim. This is about the recipe book, not about this week's menu.
- purchase_done: someone says the shopping is done ("compra hecha", "ya hemos comprado", "compra hecha menos el salmón"). except_items = products they did NOT buy ([] if none). only_items = products when they say they bought ONLY specific products or ALSO bought products that were already at home ("compré también la cebolla", "he comprado solo pan y leche"), else [].
- skip_dinner: a planned meal was not eaten ("hoy no hicimos la cena", "no hicimos la cena de ayer", "esta noche cenamos fuera", "hoy no desayuné lo del menú", "no merendé"). day_ref = "yesterday" if they talk about yesterday, else "today". meal_ref = cena, desayuno, merienda, or todo when the whole day's plan was skipped.
- wish: the user wants something in a FUTURE menu, not the current one ("la semana que viene quiero lentejas", "para el próximo menú pon algo de pescado", "apunta fideuá para la semana que viene"). plan_request = the user's message verbatim.
- help: anything else.
Unused fields: "" for strings, 0 for numbers, [] for corrected_items and except_items."""

INTENT_SCHEMA = {
    "name": "intent",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["intent", "recipe_query", "servings", "product_query", "amount", "unit", "location",
                     "corrected_items", "plan_request", "except_items", "only_items", "day_ref", "meal_ref"],
        "properties": {
            "intent": {"type": "string", "enum": ["correction", "cooked", "ate", "stock", "shopping", "plan", "wish", "new_recipe", "purchase_done", "skip_dinner", "help"]},
            "plan_request": {"type": "string"},
            "except_items": {"type": "array", "items": {"type": "string"}},
            "only_items": {"type": "array", "items": {"type": "string"}},
            "day_ref": {"type": "string", "enum": ["", "today", "yesterday"]},
            "meal_ref": {"type": "string", "enum": ["", "cena", "desayuno", "merienda", "todo"]},
            "recipe_query": {"type": "string"},
            "servings": {"type": "number"},
            "product_query": {"type": "string"},
            "amount": {"type": "number"},
            "unit": {"type": "string", "enum": UNITS + [""]},
            "location": {"type": "string", "enum": LOCATIONS + [""]},
            "corrected_items": {"type": "array", "items": ITEM_SCHEMA},
        },
    },
}

HELP_TEXT = ("Puedo ayudarte con:\n"
             "• 📸 Foto o PDF de un ticket → lo leo y, si pulsas Guardar, lo meto en la despensa.\n"
             "• 🧺 Foto de la compra sin ticket (mercado) → estimo cantidades. Pon el total en el pie: \"mercado 14,50\".\n"
             "• ✏️ Corregir el ticket pendiente: \"plátano 1,5 kg\", \"quita el detergente\".\n"
             "• 🍲 \"He cocinado lentejas para 6\" → descuento ingredientes y guardo raciones.\n"
             "• 🥄 \"Me he comido 2 yogures\" → lo descuento.\n"
             "• 🧊 \"¿Qué tengo en la nevera?\", \"¿me queda leche?\"\n"
             "• 🛒 \"Lista de la compra\"; al volver de comprar: \"compra hecha\" (o \"compra hecha menos el salmón\") y lo paso a la despensa.\n"
             "• 🌙 A las 23:30 se descuentan la cena del menú y el desayuno/merienda de __PERSONAL_NAME__; si algo no se hizo: \"hoy no hicimos la cena\", \"hoy no desayuné lo del menú\".\n"
             "• 📅 Menú semanal (te lo propongo los viernes a las 9:00): \"otra propuesta\", \"cambia la cena del martes\", "
             "\"quita el chili\", \"añade lentejas el jueves\", \"no encuentro gochujang\", \"¿qué comemos esta semana?\"\n"
             "• 📝 \"La semana que viene quiero lentejas\" → lo incluyo en la próxima propuesta.\n"
             "• 🔗 Mándame el enlace de una receta y la guardo en Tandoor.\n"
             "• 🧑‍🍳 \"Añade la receta de bacalao a la llauna\" → te la preparo adaptada a tu cocina y la guardo si te gusta.\n"
             "Comandos: /menu (menú de la semana), /propuesta (nueva propuesta), /batch (guía de batch con enlace a Tandoor), /lista (lista de la compra), "
             "/casa (qué hay en casa), /ayuda")

# ---------------------------------------------------------------- shared JS
NORM_JS = r"""
const norm = s => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
  .replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim().replace(/^\d+ /, '');
const eur = n => `${Number(n).toFixed(2).replace('.', ',')} €`;
const num = n => String(Math.round(Number(n) * 1000) / 1000).replace('.', ',');
const qn = (u, n) => !u ? '' : (Number(n) === 1 ? u.name : (u.name_plural || u.name));
const fdate = s => {
  if (!s || s >= '2999') return '';
  const [y, m, d] = s.slice(0, 10).split('-');
  return `${d}/${m}${y === String(new Date().getFullYear()) ? '' : `/${y.slice(2)}`}`;
};
"""

CONV_JS = r"""
const UNIT_G = { g: 1, gr: 1, gramo: 1, gramos: 1, kg: 1000, kilo: 1000, kilos: 1000 };
const UNIT_ML = { ml: 1, cl: 10, l: 1000, litro: 1000, litros: 1000 };
const UNIT_PC = ['', 'unidad', 'unidades', 'ud', 'uds', 'pieza', 'piezas'];
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
const convert = (amount, from, to) => {
  const f = norm(from), t = norm(to);
  if (f === t) return amount;
  if (UNIT_G[f] && UNIT_G[t]) return amount * UNIT_G[f] / UNIT_G[t];
  if (UNIT_ML[f] && UNIT_ML[t]) return amount * UNIT_ML[f] / UNIT_ML[t];
  if (UNIT_PC.includes(f) && UNIT_PC.includes(t)) return amount;
  return null;
};
"""

CLASSIFY = r"""
const u = $input.first().json.body || {};
const msg = u.message || u.edited_message;
const cb = u.callback_query;
let out = { kind: 'other', chat_id: null };
if (cb) {
  const [action, key, opt] = String(cb.data || '').split(':');
  out = { kind: 'callback', chat_id: cb.message.chat.id, query_id: cb.id, action, key, opt: opt || '', from: cb.from.first_name };
} else if (msg) {
  out.chat_id = msg.chat.id;
  out.from = msg.from ? msg.from.first_name : '';
  out.caption = String(msg.caption || '').trim();
  const doc = msg.document;
  if (msg.photo && msg.photo.length) {
    out.kind = 'file'; out.file_type = 'image'; out.file_id = msg.photo[msg.photo.length - 1].file_id;
  } else if (doc && doc.mime_type === 'application/pdf') {
    out.kind = 'file'; out.file_type = 'pdf'; out.file_id = doc.file_id;
  } else if (doc && String(doc.mime_type || '').startsWith('image/')) {
    out.kind = 'file'; out.file_type = 'image'; out.file_id = doc.file_id;
  } else {
    out.kind = 'text'; out.text = String(msg.text || '').trim();
  }
}
return [{ json: out }];
"""

BUILD_LLM = r"""
const c = $('Classify').first().json;
const stores = $('Grocy stores (read)').all().map(i => i.json.name).filter(Boolean);
const buf = await this.helpers.getBinaryDataBuffer(0, 'data');
const mime = ($input.first().binary.data || {}).mimeType || 'image/jpeg';
const b64 = buf.toString('base64');
const media = c.file_type === 'pdf'
  ? { type: 'file', file: { filename: 'ticket.pdf', file_data: `data:application/pdf;base64,${b64}` } }
  : { type: 'image_url', image_url: { url: `data:${mime};base64,${b64}` } };
const schema = JSON.parse(JSON.stringify(__SCHEMA__));
schema.schema.properties.store.enum = [...new Set([...stores, 'Otro'])];
const today = new Date().toISOString().slice(0, 10);
const note = `Today is ${today}. Allowed store names: ${schema.schema.properties.store.enum.join(', ')}. Caption from the user: "${c.caption || ''}".`;
return [{ json: { request: {
  model: __MODEL__,
  temperature: 0,
  messages: [
    { role: 'system', content: __PROMPT__ },
    { role: 'user', content: [{ type: 'text', text: note }, media] },
  ],
  response_format: { type: 'json_schema', json_schema: schema },
} } }];
"""

RECEIPT_SCHEMA = {
    "name": "receipt",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "store", "store_name", "date", "total", "caption_total", "items"],
        "properties": {
            "kind": {"type": "string", "enum": ["grocery_receipt", "groceries_photo", "other_receipt", "unreadable"]},
            "store": {"type": "string", "enum": ["Otro"]},
            "store_name": {"type": "string"},
            "date": {"type": "string"},
            "total": {"type": "number"},
            "caption_total": {"type": "number"},
            "items": {"type": "array", "items": ITEM_SCHEMA},
        },
    },
}

BUILD_LLM = (BUILD_LLM.replace("__MODEL__", json.dumps(MODEL))
             .replace("__PROMPT__", json.dumps(RECEIPT_PROMPT))
             .replace("__SCHEMA__", json.dumps(RECEIPT_SCHEMA, ensure_ascii=False)))

PARSE = NORM_JS + r"""
const c = $('Classify').first().json;
const r = $input.first().json;
let t;
try {
  t = JSON.parse(r.choices[0].message.content);
} catch (e) {
  const reason = (r.error && (r.error.message || r.error)) || 'respuesta del modelo no válida';
  return [{ json: { ok: false, chat_id: c.chat_id, text: `No pude leer la imagen (${reason}). Inténtalo otra vez.` } }];
}
if (t.kind === 'other_receipt') {
  return [{ json: { ok: false, chat_id: c.chat_id, text: `Esto parece un ticket que no es de compra de comida o casa (${t.store_name || 'restaurante, farmacia…'}). No lo meto en la despensa.` } }];
}
if (t.kind === 'unreadable' || !Array.isArray(t.items) || !t.items.length) {
  return [{ json: { ok: false, chat_id: c.chat_id, text: 'No he podido leerlo. Prueba con buena luz y el ticket entero y plano, o los productos separados en la foto.' } }];
}
const photo = t.kind === 'groceries_photo';
let priceKnown = !photo;
if (photo) {
  const est = t.items.reduce((a, it) => a + Number(it.estimated_price || 0), 0);
  const paid = Number(t.caption_total || 0);
  priceKnown = paid > 0 && est > 0;
  for (const it of t.items) {
    it.line_total = priceKnown ? Math.round(Number(it.estimated_price) * paid / est * 100) / 100 : 0;
    it.unit_price = priceKnown && it.quantity ? Math.round(it.line_total / it.quantity * 10000) / 10000 : 0;
    it.discount = 0;
  }
  t.total = priceKnown ? paid : 0;
}
const cleanStore = s => {
  let x = String(s || '').replace(/[\s,]+(s\.?\s?a\.?|s\.?\s?l\.?u?\.?|s\.?\s?coop\.?(\s?v\.?)?)\s*$/i, '').trim();
  if (x && x === x.toUpperCase()) x = x.toLowerCase().replace(/(^|\s)\S/g, m => m.toUpperCase());
  return x;
};
const store = t.store && t.store !== 'Otro' ? t.store : (cleanStore(t.store_name) || 'Otro');
let h = 5381;
const seed = photo ? `photo|${c.chat_id}|${Date.now()}` : `${norm(store)}|${t.date}|${Number(t.total).toFixed(2)}`;
for (const ch of seed) h = ((h << 5) + h + ch.charCodeAt(0)) >>> 0;
const cost = r.usage && typeof r.usage.cost === 'number' ? r.usage.cost : null;
return [{ json: { ok: true, chat_id: c.chat_id, key: h.toString(36),
  ticket: { kind: t.kind, store, date: t.date, total: t.total, price_known: priceKnown, items: t.items }, cost } }];
"""


def match_js(source):
    return NORM_JS + r"""
const t = $('__SOURCE__').first().json;
const products = $input.all().map(i => i.json).filter(p => p && p.id);
const byAlias = new Map();
const byName = new Map();
for (const p of products) {
  byName.set(norm(p.name), p);
  for (const a of String((p.userfields || {}).ticket_aliases || '').split('\n')) if (a.trim()) byAlias.set(norm(a), p);
}
const items = t.ticket.items.map(it => {
  const p = byAlias.get(norm(it.ticket_name)) || byName.get(norm(it.product_name));
  return { ...it, discount: Number(it.discount || 0), product_id: p ? p.id : null, grocy_name: p ? p.name : null,
           aliases: p ? String((p.userfields || {}).ticket_aliases || '') : '' };
});
const sd = $getWorkflowStaticData('global');
sd.pending = sd.pending || {};
sd.done = sd.done || {};
sd.lastPending = sd.lastPending || {};
const now = Date.now();
for (const [k, v] of Object.entries(sd.pending)) if (now - v.created > 3 * 864e5) delete sd.pending[k];
sd.pending[t.key] = { created: now, chat_id: t.chat_id, kind: t.ticket.kind, store: t.ticket.store, date: t.ticket.date,
                      total: t.ticket.total, price_known: t.ticket.price_known, items };
sd.lastPending[String(t.chat_id)] = t.key;

const photo = t.ticket.kind === 'groceries_photo';
const qty = it => it.unit === 'Unidad' ? `×${num(it.quantity)}` : `${num(it.quantity)} ${it.unit}`;
const price = it => !t.ticket.price_known ? '' : ` — ${eur(it.line_total - it.discount)}${it.discount ? ` (−${eur(it.discount)})` : ''}`;
const lines = items.map(it => `${it.product_id ? '✓' : '✚'} ${it.grocy_name || it.product_name} ${qty(it)}${price(it)}`);
const net = items.reduce((a, it) => a + Number(it.line_total || 0) - it.discount, 0);
const nNew = items.filter(it => !it.product_id).length;
let text = photo
  ? `🧺 Compra sin ticket · ${t.ticket.store} · ${t.ticket.date}${t.ticket.price_known ? ` · ${eur(t.ticket.total)}` : ''}\n(cantidades estimadas)\n\n`
  : `🧾 ${t.ticket.store} · ${t.ticket.date} · ${eur(t.ticket.total)}\n\n`;
text += `${lines.join('\n')}\n\n${items.length} líneas, ${nNew} productos nuevos (✚).`;
if (!photo && Math.abs(net - Number(t.ticket.total)) > 0.05) text += `\n⚠ La suma de líneas (${eur(net)}) no cuadra con el total: revisa antes de guardar.`;
if (photo && !t.ticket.price_known) text += `\nSin precios: si quieres guardarlos, responde con el total pagado ("total 14,50").`;
const bulk = sd.bulk && Date.now() - sd.bulk.at < 48 * 3600e3 ? sd.bulk : null;
if (bulk && items.some(it => it.product_id && bulk.product_ids.includes(it.product_id))) text += `\n⚠ Hace poco marcasteis "compra hecha": si este ticket es de esa compra, guardarlo duplicará el stock. Descártalo o guarda solo si es otra compra.`;
if (sd.done[t.key]) text += `\n⚠ Este ticket ya se guardó el ${sd.done[t.key].at.slice(0, 10)}. Si lo guardas otra vez se duplicará el stock.`;
text += `\n✏️ Puedes corregir respondiendo, p. ej. "plátano 1,5 kg" o "quita el detergente".`;
if (t.cost !== null && t.cost !== undefined) text += `\nCoste de lectura: ${Number(t.cost).toFixed(4)} $`;
return [{ json: { chat_id: t.chat_id, key: t.key, text } }];
""".replace("__SOURCE__", source)


RESOLVE = r"""
const c = $('Classify').first().json;
const sd = $getWorkflowStaticData('global');
const reply = text => [{ json: { mode: 'reply', chat_id: c.chat_id, text } }];
if (c.action === 'ok' || c.action === 'no') {
  const p = (sd.pending || {})[c.key];
  if (!p) return reply('Este ticket ya no está pendiente (caducó o ya se procesó).');
  if (c.action === 'no') {
    delete sd.pending[c.key];
    return reply('Descartado. No se ha guardado nada.');
  }
  return [{ json: { mode: 'save', chat_id: c.chat_id, key: c.key } }];
}
if (c.action === 'ck') {
  const plan = (sd.cooked || {})[c.key];
  if (!plan) return reply('Esta receta ya no está pendiente.');
  if (c.opt === 'x') {
    delete sd.cooked[c.key];
    return reply('Cancelado. No he descontado nada.');
  }
  return [{ json: { mode: 'cook', chat_id: c.chat_id, key: c.key, opt: c.opt } }];
}
if (c.action === 'pl') {
  const week = sd.week;
  if (!week || week.week_start !== c.opt) return reply('Esa propuesta ya no es la actual. Pide "¿qué comemos esta semana?" para ver el plan vigente.');
  if (c.key === 'ok') {
    if (week.status === 'accepted') return reply('Este menú ya está aceptado.');
    return [{ json: { mode: 'plan_accept', chat_id: c.chat_id } }];
  }
  if (c.key === 'new') return [{ json: { mode: 'plan_new', chat_id: c.chat_id } }];
}
if (c.action === 'bt') {
  const w = sd.week;
  if (!w || w.week_start !== c.opt || w.status !== 'accepted') return reply('Ese menú ya no es el actual.');
  if (w.batch_done) return reply('El batch de esta semana ya estaba registrado.');
  return [{ json: { mode: 'batch_done', chat_id: c.chat_id } }];
}
if (c.action === 'nr') {
  const r = (sd.newRecipes || {})[c.opt];
  if (!r) return reply('Esa receta ya no está pendiente.');
  if (c.key !== 'ok') {
    delete sd.newRecipes[c.opt];
    return reply(`Descartada: ${r.name}. No se ha guardado nada.`);
  }
  return [{ json: { mode: 'recipe_save', chat_id: c.chat_id, key: c.opt } }];
}
return reply('Botón desconocido.');
"""

STORE_PLAN = NORM_JS + r"""
const r = $('Resolve callback').first().json;
const p = $getWorkflowStaticData('global').pending[r.key];
const stores = $input.all().map(i => i.json).filter(s => s && s.id);
const found = stores.find(s => norm(s.name) === norm(p.store));
const usable = p.store && p.store !== 'Otro';
return [{ json: { store_id: found ? found.id : null, create: usable && !found, name: p.store } }];
"""

BUILD_WRITES = NORM_JS + r"""
const r = $('Resolve callback').first().json;
const p = $getWorkflowStaticData('global').pending[r.key];
const idx = node => Object.fromEntries($(node).all().map(i => [i.json.name, i.json.id]));
const loc = idx('Grocy locations'), qu = idx('Grocy units'), grp = idx('Grocy groups');
const es = $('Ensure store').first().json;
const shopId = $('Store plan').first().json.store_id || es.created_object_id || null;

const merged = new Map();
for (const it of p.items) {
  const k = it.product_id ? `id:${it.product_id}` : `new:${norm(it.product_name)}`;
  const m = merged.get(k);
  const net = Number(it.line_total || 0) - Number(it.discount || 0);
  if (m) {
    m.quantity += Number(it.quantity); m.net += net; m.lines += 1;
    if (!m.ticket_names.includes(it.ticket_name)) m.ticket_names.push(it.ticket_name);
  } else {
    merged.set(k, { ...it, quantity: Number(it.quantity), net, lines: 1, ticket_names: [it.ticket_name] });
  }
}
const addDays = (d, n) => { const x = new Date(`${d}T12:00:00Z`); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
const purchased = /^\d{4}-\d{2}-\d{2}$/.test(p.date) ? p.date : new Date().toISOString().slice(0, 10);
return [...merged.values()].map(it => {
  const quId = qu[it.unit] || qu['Unidad'];
  const known = new Set(it.aliases.split('\n').map(norm).filter(Boolean));
  const aliases = [...it.aliases.split('\n').filter(a => a.trim()),
                   ...(p.kind === 'groceries_photo' ? [] : it.ticket_names.filter(n => !known.has(norm(n))))].join('\n');
  const stock = {
    amount: it.quantity, transaction_type: 'purchase', purchased_date: purchased,
    best_before_date: it.best_before_days > 0 ? addDays(purchased, it.best_before_days) : '2999-12-31',
    shopping_location_id: shopId,
  };
  if (p.price_known && it.quantity) {
    stock.price = it.lines === 1 && !it.discount && it.unit_price > 0 ? it.unit_price : Math.round(it.net / it.quantity * 10000) / 10000;
  }
  return { json: {
    product_id: it.product_id,
    label: it.grocy_name || it.product_name,
    is_new: !it.product_id,
    create_body: {
      name: it.product_name, location_id: loc[it.location] || loc['Despensa'], product_group_id: grp[it.category] || null,
      qu_id_purchase: quId, qu_id_stock: quId, qu_id_consume: quId, qu_id_price: quId,
      default_best_before_days: it.best_before_days > 0 ? it.best_before_days : -1, shopping_location_id: shopId,
    },
    aliases,
    stock_body: stock,
  } };
});
"""

SUMMARY = r"""
const r = $('Resolve callback').first().json;
const sd = $getWorkflowStaticData('global');
const p = sd.pending[r.key];
const writes = $('Build writes').all().map(i => i.json);
const results = $input.all().map(i => i.json);
const failed = writes.filter((w, i) => !results[i] || results[i].error);
const ok = writes.length - failed.length;
const nNew = writes.filter(w => w.is_new && !failed.includes(w)).length;
if (p.kind !== 'groceries_photo') sd.done[r.key] = { at: new Date().toISOString(), store: p.store, total: p.total };
delete sd.pending[r.key];
const total = p.price_known ? ` · ${Number(p.total).toFixed(2).replace('.', ',')} €` : '';
let text = `✅ Guardado en Grocy: ${ok} productos (${nNew} nuevos) · ${p.store} ${p.date}${total}`;
if (failed.length) text += `\n⚠ No se pudieron guardar: ${failed.map(f => f.label).join(', ')}`;
return [{ json: { chat_id: r.chat_id, text } }];
"""

TEXT_CONTEXT = r"""
const c = $('Classify').first().json;
const raw = String(c.text || '').replace(/^(\/\w+)@\w+/, '$1');
const COMMANDS = { '/menu': '¿qué comemos esta semana?', '/lista': 'dame la lista de la compra', '/casa': '¿qué tengo en casa?' };
const cmd = (raw.match(/^\/\w+/) || [''])[0].toLowerCase();
if (!raw || ['/start', '/ayuda', '/help'].includes(cmd)) return [{ json: { mode: 'help', chat_id: c.chat_id, from: c.from } }];
if (cmd === '/propuesta') return [{ json: { mode: 'propose', chat_id: c.chat_id } }];
if (cmd === '/batch') return [{ json: { mode: 'guide', chat_id: c.chat_id } }];
const text = COMMANDS[cmd] ? `${COMMANDS[cmd]} ${raw.slice(cmd.length)}`.trim() : raw;
const url = (text.match(/https?:\/\/\S+/) || [])[0];
if (url) return [{ json: { mode: 'import', chat_id: c.chat_id, url, hint: text.replace(url, '').trim() } }];
const sd = $getWorkflowStaticData('global');
const key = (sd.lastPending || {})[String(c.chat_id)];
const p = key && (sd.pending || {})[key];
const pendingItems = p ? p.items.map(({ product_id, grocy_name, aliases, ...rest }) => rest) : [];
const context = p
  ? `Pending receipt (${p.store}, ${p.date}, total ${p.total}, kind ${p.kind}):\n${JSON.stringify(pendingItems)}`
  : 'There is no pending receipt, so intent cannot be correction.';
return [{ json: { mode: 'llm', chat_id: c.chat_id, pending_key: p ? key : null, request: {
  model: __MODEL__,
  temperature: 0,
  messages: [
    { role: 'system', content: __PROMPT__ },
    { role: 'user', content: `${context}\n\nMessage: "${text}"` },
  ],
  response_format: { type: 'json_schema', json_schema: __SCHEMA__ },
} } }];
""".replace("__MODEL__", json.dumps(MODEL)).replace("__PROMPT__", json.dumps(INTENT_PROMPT)).replace(
    "__SCHEMA__", json.dumps(INTENT_SCHEMA, ensure_ascii=False))

PARSE_INTENT = r"""
const ctx = $('Text context').first().json;
const r = $input.first().json;
let i;
try { i = JSON.parse(r.choices[0].message.content); } catch (e) { i = { intent: 'help' }; }
const cost = r.usage && typeof r.usage.cost === 'number' ? r.usage.cost : null;
if (i.intent === 'correction' && (!ctx.pending_key || !Array.isArray(i.corrected_items))) i.intent = 'help';
return [{ json: { ...i, chat_id: ctx.chat_id, pending_key: ctx.pending_key, cost } }];
"""

APPLY_CORRECTION = r"""
const i = $('Parse intent').first().json;
const p = $getWorkflowStaticData('global').pending[i.pending_key];
const items = i.corrected_items;
let total = p.total;
const userText = $('Classify').first().json.text || '';
const priceMentioned = /€|eur|precio|cuest|cost|pag/i.test(userText);
if (p.kind !== 'groceries_photo' && !priceMentioned) {
  const orig = new Map(p.items.map(it => [it.ticket_name, it]));
  for (const it of items) {
    const o = orig.get(it.ticket_name);
    if (o) { it.line_total = o.line_total; it.unit_price = o.unit_price; it.discount = o.discount; }
  }
}
if (p.kind === 'groceries_photo') {
  const est = items.reduce((a, it) => a + Number(it.estimated_price || 0), 0);
  if (p.price_known && est > 0) for (const it of items) {
    it.line_total = Math.round(Number(it.estimated_price) * p.total / est * 100) / 100;
    it.unit_price = it.quantity ? Math.round(it.line_total / it.quantity * 10000) / 10000 : 0;
  }
}
return [{ json: { chat_id: i.chat_id, key: i.pending_key, cost: i.cost,
  ticket: { kind: p.kind, store: p.store, date: p.date, total, price_known: p.price_known, items } } }];
"""

PICK_RECIPE = r"""
const i = $('Parse intent').first().json;
const res = $input.first().json;
const list = res.results || [];
if (!list.length) return [{ json: { found: false, chat_id: i.chat_id, text: `No encuentro ninguna receta parecida a "${i.recipe_query}" en Tandoor.` } }];
return [{ json: { found: true, chat_id: i.chat_id, recipe_id: list[0].id } }];
"""

COOK_PLAN = NORM_JS + CONV_JS + r"""
const i = $('Parse intent').first().json;
const recipe = $('Tandoor recipe').first().json;
const stock = $('Grocy stock (cook)').all().map(x => x.json).filter(s => s && s.product_id);
const products = $('Grocy products (cook)').all().map(x => x.json).filter(p => p && p.id);
const units = Object.fromEntries($('Grocy units (cook)').all().map(x => [x.json.id, x.json.name]));
const servings = i.servings > 0 ? i.servings : (recipe.servings || 1);
const factor = servings / (recipe.servings || 1);
const byFood = new Map(), byName = new Map();
for (const s of stock) {
  const uf = (s.product && s.product.userfields) || {};
  if (uf.tandoor_food_id) byFood.set(String(uf.tandoor_food_id), s);
  byName.set(norm(s.product.name), s);
}
const consume = [], skipped = [];
for (const step of recipe.steps || []) for (const ing of step.ingredients || []) {
  if (ing.is_header || !ing.food) continue;
  const s = byFood.get(String(ing.food.id)) || byName.get(norm(ing.food.name))
    || stock.map(x => [similar(ing.food.name, x.product.name), x]).filter(([sc]) => sc === 1)
         .sort((a, b) => words(a[1].product.name).length - words(b[1].product.name).length).map(([, x]) => x)[0];
  if (!s) { skipped.push(`${ing.food.name} (no está en la despensa)`); continue; }
  if (ing.no_amount || !ing.amount) { skipped.push(`${ing.food.name} (sin cantidad)`); continue; }
  const stockUnit = units[s.product.qu_id_stock] || '';
  const amount = convert(ing.amount * factor, ing.unit ? ing.unit.name : '', stockUnit);
  if (amount === null) { skipped.push(`${ing.food.name} (${ing.unit ? ing.unit.name : 'sin unidad'} → ${stockUnit})`); continue; }
  const take = Math.min(amount, Number(s.amount));
  consume.push({ product_id: s.product_id, name: s.product.name, amount: Math.round(take * 1000) / 1000, unit: stockUnit,
                 short: take < amount });
}
const portionName = `${recipe.name} (ración)`;
const existing = products.find(p => norm(p.name) === norm(portionName));
let h = 5381;
for (const ch of `cook|${recipe.id}|${Date.now()}`) h = ((h << 5) + h + ch.charCodeAt(0)) >>> 0;
const key = h.toString(36);
const sd = $getWorkflowStaticData('global');
sd.cooked = sd.cooked || {};
const now = Date.now();
for (const [k, v] of Object.entries(sd.cooked)) if (now - v.created > 2 * 864e5) delete sd.cooked[k];
sd.cooked[key] = { created: now, chat_id: i.chat_id, recipe: recipe.name, servings, consume,
                   portion: { name: portionName, product_id: existing ? existing.id : null } };
let text = `🍲 ${recipe.name} · ${num(servings)} raciones\n\n`;
text += consume.length ? `Descontaré de la despensa:\n${consume.map(c => `• ${c.name} ${num(c.amount)} ${c.unit}${c.short ? ' (todo lo que queda)' : ''}`).join('\n')}` : 'No hay ingredientes de la receta en la despensa para descontar.';
if (skipped.length) text += `\n\nNo descuento:\n${skipped.map(s => `• ${s}`).join('\n')}`;
text += `\n\n¿Guardo las ${num(servings)} raciones?`;
return [{ json: { chat_id: i.chat_id, key, text } }];
"""

COOK_WRITES = r"""
const r = $('Resolve callback').first().json;
const plan = $getWorkflowStaticData('global').cooked[r.key];
if (!plan.consume.length) return [{ json: { noop: true } }];
return plan.consume.map(c => ({ json: { noop: false, product_id: c.product_id, name: c.name,
  body: { amount: c.amount, transaction_type: 'consume', spoiled: false } } }));
"""

PORTION_PLAN = r"""
const r = $('Resolve callback').first().json;
const plan = $getWorkflowStaticData('global').cooked[r.key];
const loc = Object.fromEntries($('Grocy locations (cook)').all().map(i => [i.json.name, i.json.id]));
const qu = Object.fromEntries($('Grocy units (cook2)').all().map(i => [i.json.name, i.json.id]));
const where = r.opt === 'c' ? 'Congelador' : (r.opt === 'n' ? 'Nevera' : null);
const days = where === 'Congelador' ? 90 : 4;
const bb = new Date(Date.now() + days * 864e5).toISOString().slice(0, 10);
return [{ json: {
  skip: !where, where, product_id: plan.portion.product_id,
  create_body: { name: plan.portion.name, location_id: loc['Nevera'], qu_id_purchase: qu['Unidad'], qu_id_stock: qu['Unidad'],
                 qu_id_consume: qu['Unidad'], qu_id_price: qu['Unidad'], default_best_before_days: 4,
                 default_best_before_days_after_freezing: 90, product_group_id: null },
  stock_body: { amount: plan.servings, transaction_type: 'self-production', best_before_date: bb, location_id: loc[where] || loc['Nevera'] },
} }];
"""

COOK_SUMMARY = r"""
const r = $('Resolve callback').first().json;
const sd = $getWorkflowStaticData('global');
const plan = sd.cooked[r.key];
const consumed = $('Consume ingredients').all().map(i => i.json);
const writes = $('Cook writes').all().map(i => i.json).filter(w => !w.noop);
const failed = writes.filter((w, i) => !consumed[i] || consumed[i].error).map(w => w.name);
const pp = $('Portion plan').first().json;
const portionRes = $('Add portions').first().json;
delete sd.cooked[r.key];
let text = `✅ ${plan.recipe}: descontados ${writes.length - failed.length} ingredientes.`;
if (failed.length) text += `\n⚠ No se pudo descontar: ${failed.join(', ')}`;
if (!pp.skip) text += portionRes && !portionRes.error
  ? `\n🥡 Guardadas ${plan.servings} raciones de "${plan.portion.name}" en ${pp.where}.`
  : `\n⚠ No se pudieron guardar las raciones.`;
return [{ json: { chat_id: r.chat_id, text } }];
"""

ATE_PLAN = NORM_JS + CONV_JS + r"""
const i = $('Parse intent').first().json;
const stock = $('Grocy stock (ate)').all().map(x => x.json).filter(s => s && s.product_id);
const unitObj = Object.fromEntries($('Grocy units (ate)').all().map(x => [x.json.id, x.json]));
const units = Object.fromEntries(Object.entries(unitObj).map(([k, v]) => [k, v.name]));
const q = norm(i.product_query);
const score = s => {
  const n = norm(s.product.name);
  if (n === q) return 4;
  if (n.startsWith(q) || q.startsWith(n)) return 3;
  if (n.includes(q) || q.includes(n)) return 2;
  return q.split(' ').some(w => w.length > 3 && n.includes(w)) ? 1 : 0;
};
const ranked = stock.map(s => [score(s) + (/\bracion\b/.test(norm(s.product.name)) ? 0.5 : 0), s])
  .filter(([sc]) => sc >= 1).sort((a, b) => b[0] - a[0]);
if (!ranked.length) return [{ json: { noop: true, chat_id: i.chat_id, text: `No encuentro "${i.product_query}" en la despensa.` } }];
const s = ranked[0][1];
const stockUnit = units[s.product.qu_id_stock] || '';
let amount = convert(i.amount || 1, i.unit || stockUnit, stockUnit);
if (amount === null) amount = i.amount || 1;
const take = Math.round(Math.min(amount, Number(s.amount)) * 1000) / 1000;
const left = Math.round((Number(s.amount) - take) * 1000) / 1000;
return [{ json: { noop: false, chat_id: i.chat_id, product_id: s.product_id,
  body: { amount: take, transaction_type: 'consume', spoiled: false },
  text: `✅ Descontado: ${s.product.name} ${num(take)} ${qn(unitObj[s.product.qu_id_stock], take)}. Quedan ${num(left)} ${qn(unitObj[s.product.qu_id_stock], left)}.` } }];
"""

ATE_REPLY = r"""
const plan = $('Ate plan').first().json;
const res = $input.first().json;
const text = plan.noop || !res.error ? plan.text : `⚠ No pude descontarlo: ${res.error.message || res.error}`;
return [{ json: { chat_id: plan.chat_id, text } }];
"""

STOCK_REPLY = NORM_JS + r"""
const i = $('Parse intent').first().json;
const entries = $('Grocy stock (st)').all().map(x => x.json).filter(s => s && s.product_id && Number(s.amount) > 0);
const products = Object.fromEntries($('Grocy products (st)').all().map(x => [x.json.id, x.json]));
const units = Object.fromEntries($('Grocy units (st)').all().map(x => [x.json.id, x.json]));
const locs = Object.fromEntries($('Grocy locations (st)').all().map(x => [x.json.id, x.json.name]));
const agg = new Map();
for (const e of entries) {
  const k = `${e.product_id}|${e.location_id}`;
  const a = agg.get(k) || { product: products[e.product_id], location: locs[e.location_id] || 'Otros', amount: 0, bb: null };
  a.amount += Number(e.amount);
  if (!a.bb || e.best_before_date < a.bb) a.bb = e.best_before_date;
  agg.set(k, a);
}
const q = norm(i.product_query);
let rows = [...agg.values()].filter(r => r.product);
if (q) rows = rows.filter(r => norm(r.product.name).includes(q) || q.includes(norm(r.product.name)));
if (i.location) rows = rows.filter(r => r.location === i.location);
if (!rows.length) return [{ json: { chat_id: i.chat_id, text: q ? `No queda ${i.product_query}.` : 'No hay nada registrado ahí.' } }];
const fmt = r => `• ${r.product.name} ${num(r.amount)} ${qn(units[r.product.qu_id_stock], r.amount)}${fdate(r.bb) ? ` (cad. ${fdate(r.bb)})` : ''}`;
const groups = {};
for (const r of rows.sort((a, b) => String(a.bb).localeCompare(String(b.bb)))) (groups[r.location] ||= []).push(fmt(r));
const text = Object.entries(groups).map(([k, v]) => `${k === 'Nevera' ? '🧊' : k === 'Congelador' ? '❄️' : '🗄'} ${k}\n${v.join('\n')}`).join('\n\n');
return [{ json: { chat_id: i.chat_id, text: text.slice(0, 4000) } }];
"""

SHOPPING_REPLY = r"""
const chat = $('Parse intent').isExecuted ? $('Parse intent').first().json.chat_id : null;
const entries = $input.all().flatMap(x => x.json.results || (x.json.id ? [x.json] : [])).filter(e => !e.checked);
if (!entries.length) return [{ json: { chat_id: chat, text: '🛒 La lista de la compra está vacía.' } }];
const groups = {};
for (const e of entries) {
  const cat = (e.food && e.food.supermarket_category && e.food.supermarket_category.name) || 'Otros';
  const amount = e.amount ? `${String(Math.round(e.amount * 100) / 100).replace('.', ',')} ${e.unit ? e.unit.name : ''}`.trim() : '';
  (groups[cat] ||= []).push(`• ${e.food ? e.food.name : '?'}${amount ? ` — ${amount}` : ''}`);
}
const text = `🛒 Lista de la compra (${entries.length})\n\n` + Object.entries(groups).map(([k, v]) => `${k}\n${v.join('\n')}`).join('\n\n');
return [{ json: { chat_id: chat, text: text.slice(0, 4000) } }];
"""

HELP = "={{ ($json.from ? 'Hola ' + $json.from + '. ' : '') + " + json.dumps(HELP_TEXT, ensure_ascii=False) + " }}"


# ---------------------------------------------------------------- builders
def node(name, ntype, version, pos, params, **extra):
    n = {"id": str(uuid.uuid4()), "name": name, "type": ntype, "typeVersion": version,
         "position": pos, "parameters": params}
    n.update(extra)
    return n


def tg_send(name, pos, text_expr="={{ $json.text }}", rows=None):
    params = {"chatId": "={{ $json.chat_id }}", "text": text_expr,
              "additionalFields": {"appendAttribution": False}}
    if rows:
        params["replyMarkup"] = "inlineKeyboard"
        params["inlineKeyboard"] = {"rows": [{"row": {"buttons": r}} for r in rows]}
    return node(name, "n8n-nodes-base.telegram", 1.2, pos, params, credentials=CRED_TG)


def btn(text, data):
    return {"text": text, "additionalFields": {"callback_data": data}}


def http(name, pos, url, cred, method="GET", body=None, once=False, always=False, on_error=None):
    params = {"method": method, "url": url, "authentication": "genericCredentialType",
              "genericAuthType": "httpHeaderAuth", "options": {}}
    if body is not None:
        params.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    extra = {"credentials": cred}
    if once:
        extra["executeOnce"] = True
    if always:
        extra["alwaysOutputData"] = True
    if on_error:
        extra["onError"] = on_error
    if cred is CRED_GROCY and method != "GET":
        # Grocy GetCurrentStock races with concurrent stock writes (500 "product_id on null"); n8n does not wait for a batch
        # to finish before the next one, so space the requests out instead of only batching them.
        params["options"]["batching"] = {"batch": {"batchSize": 1, "batchInterval": 700}}
        # Freshly created products sometimes fail GetCurrentStock with a 500; Grocy rolls the write back, so retrying is safe.
        extra.update({"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000})
    return node(name, "n8n-nodes-base.httpRequest", 4.5, pos, params, **extra)


def grocy_get(name, pos, path):
    return http(name, pos, f"{GROCY}/{path}", CRED_GROCY, once=True, always=True)


def openrouter(name, pos):
    n = http(name, pos, OPENROUTER_URL, CRED_OR, method="POST",
             body="={{ JSON.stringify($json.request) }}", on_error="continueRegularOutput")
    n["parameters"]["options"] = {"timeout": 120000}
    return n


def code(name, pos, js):
    return node(name, "n8n-nodes-base.code", 2, pos, {"jsCode": js.strip()})


def switch(name, pos, field, values):
    rules = []
    for v in values:
        rules.append({"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict", "version": 2},
                                     "combinator": "and",
                                     "conditions": [{"id": str(uuid.uuid4()), "leftValue": f"={{{{ $json.{field} }}}}",
                                                     "rightValue": v,
                                                     "operator": {"type": "string", "operation": "equals"}}]},
                      "renameOutput": True, "outputKey": v})
    return node(name, "n8n-nodes-base.switch", 3.2, pos, {"rules": {"values": rules}, "options": {}})


def bool_if(name, pos, expr):
    return node(name, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": str(uuid.uuid4()), "leftValue": expr, "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]},
        "looseTypeValidation": True, "options": {}})


def noop_or(expr_cond, real_url):
    return f"={{{{ {expr_cond} ? '{NOOP}' : {real_url} }}}}"


SUMMARY_ROWS = [[btn("✅ Guardar", "=ok:{{ $json.key }}"), btn("❌ Descartar", "=no:{{ $json.key }}")]]
COOK_ROWS = [[btn("🧊 Nevera", "=ck:{{ $json.key }}:n"), btn("❄️ Congelador", "=ck:{{ $json.key }}:c")],
             [btn("Solo descontar", "=ck:{{ $json.key }}:0"), btn("Cancelar", "=ck:{{ $json.key }}:x")]]

X = 260
nodes = [
    node("Telegram In", "n8n-nodes-base.webhook", 2.1, [0, 600], {
        "httpMethod": "POST", "path": WEBHOOK_PATH, "authentication": "headerAuth",
        "responseMode": "onReceived", "options": {}}, credentials=CRED_BRIDGE,
        webhookId="0b6a3f0e-5a3e-4c55-9d3e-6b1c4b1f7a01"),
    code("Classify", [X, 600], CLASSIFY),
    switch("Route", [2 * X, 600], "kind", ["file", "callback", "text"]),

    # file branch
    tg_send("Ack reading", [3 * X, 0], "=📸 Leyendo…"),
    grocy_get("Grocy stores (read)", [3 * X, 140], "objects/shopping_locations"),
    node("Download file", "n8n-nodes-base.telegram", 1.2, [4 * X, 140], {
        "resource": "file", "fileId": "={{ $('Classify').first().json.file_id }}", "download": True,
        "additionalFields": {}}, credentials=CRED_TG, executeOnce=True),
    code("Build LLM request", [5 * X, 140], BUILD_LLM),
    openrouter("OpenRouter extract", [6 * X, 140]),
    code("Parse ticket", [7 * X, 140], PARSE),
    bool_if("Ticket OK?", [8 * X, 140], "={{ $json.ok }}"),
    grocy_get("Grocy products", [9 * X, 80], "objects/products"),
    code("Match products", [10 * X, 80], match_js("Parse ticket")),
    tg_send("Send summary", [11 * X, 80], rows=SUMMARY_ROWS),
    tg_send("Send read error", [9 * X, 220]),

    # callback branch
    node("Answer button", "n8n-nodes-base.telegram", 1.2, [3 * X, 600], {
        "resource": "callback", "operation": "answerQuery", "queryId": "={{ $json.query_id }}",
        "additionalFields": {"text": "Procesando…"}}, credentials=CRED_TG, onError="continueRegularOutput"),
    code("Resolve callback", [4 * X, 600], RESOLVE),
    switch("Callback mode", [5 * X, 600], "mode", ["save", "cook", "reply"]),
    tg_send("Send callback reply", [6 * X, 760]),

    grocy_get("Grocy locations", [6 * X, 380], "objects/locations"),
    grocy_get("Grocy units", [7 * X, 380], "objects/quantity_units"),
    grocy_get("Grocy groups", [8 * X, 380], "objects/product_groups"),
    grocy_get("Grocy stores", [9 * X, 380], "objects/shopping_locations"),
    code("Store plan", [10 * X, 380], STORE_PLAN),
    http("Ensure store", [11 * X, 380],
         f"={{{{ $json.create ? '{GROCY}/objects/shopping_locations' : '{NOOP}' }}}}", CRED_GROCY,
         method="={{ $json.create ? 'POST' : 'GET' }}", body="={{ JSON.stringify({ name: $json.name }) }}",
         once=True, on_error="continueRegularOutput"),
    code("Build writes", [12 * X, 380], BUILD_WRITES),
    http("Ensure product", [13 * X, 380],
         f"={{{{ $json.product_id ? '{GROCY}/objects/products/' + $json.product_id : '{GROCY}/objects/products' }}}}",
         CRED_GROCY, method="={{ $json.product_id ? 'GET' : 'POST' }}",
         body="={{ JSON.stringify($json.create_body) }}"),
    http("Save aliases", [14 * X, 380],
         f"={{{{ '{GROCY}/userfields/products/' + ($json.created_object_id || $json.id) }}}}", CRED_GROCY,
         method="PUT", body="={{ JSON.stringify({ ticket_aliases: $('Build writes').item.json.aliases }) }}"),
    http("Add stock", [15 * X, 380],
         f"={{{{ '{GROCY}/stock/products/' + ($('Ensure product').item.json.created_object_id || $('Ensure product').item.json.id) + '/add' }}}}",
         CRED_GROCY, method="POST", body="={{ JSON.stringify($('Build writes').item.json.stock_body) }}",
         on_error="continueRegularOutput"),
    code("Summary", [16 * X, 380], SUMMARY),
    tg_send("Send saved", [17 * X, 380]),

    grocy_get("Grocy locations (cook)", [6 * X, 560], "objects/locations"),
    grocy_get("Grocy units (cook2)", [7 * X, 560], "objects/quantity_units"),
    code("Cook writes", [8 * X, 560], COOK_WRITES),
    http("Consume ingredients", [9 * X, 560],
         noop_or("$json.noop", f"'{GROCY}/stock/products/' + $json.product_id + '/consume'"), CRED_GROCY,
         method="={{ $json.noop ? 'GET' : 'POST' }}", body="={{ JSON.stringify($json.body || {}) }}",
         on_error="continueRegularOutput"),
    code("Portion plan", [10 * X, 560], PORTION_PLAN),
    http("Ensure portion product", [11 * X, 560],
         f"={{{{ $json.skip ? '{NOOP}' : ($json.product_id ? '{GROCY}/objects/products/' + $json.product_id : '{GROCY}/objects/products') }}}}",
         CRED_GROCY, method="={{ !$json.skip && !$json.product_id ? 'POST' : 'GET' }}",
         body="={{ JSON.stringify($json.create_body) }}", on_error="continueRegularOutput"),
    http("Add portions", [12 * X, 560],
         f"={{{{ $('Portion plan').first().json.skip ? '{NOOP}' : '{GROCY}/stock/products/' + ($json.created_object_id || $json.id) + '/add' }}}}",
         CRED_GROCY, method="={{ $('Portion plan').first().json.skip ? 'GET' : 'POST' }}",
         body="={{ JSON.stringify($('Portion plan').first().json.stock_body) }}", on_error="continueRegularOutput"),
    code("Cook summary", [13 * X, 560], COOK_SUMMARY),
    tg_send("Send cook done", [14 * X, 560]),

    # text branch
    code("Text context", [3 * X, 1100], TEXT_CONTEXT),
    switch("Text mode", [4 * X, 1100], "mode", ["help", "llm"]),
    tg_send("Send help", [5 * X, 1000], HELP),
    openrouter("OpenRouter intent", [5 * X, 1160]),
    code("Parse intent", [6 * X, 1160], PARSE_INTENT),
    switch("Intent", [7 * X, 1160], "intent", ["correction", "cooked", "ate", "stock", "shopping", "help"]),

    code("Apply correction", [8 * X, 900], APPLY_CORRECTION),
    grocy_get("Grocy products (corr)", [9 * X, 900], "objects/products"),
    code("Match corrected", [10 * X, 900], match_js("Apply correction")),
    tg_send("Send corrected summary", [11 * X, 900], rows=SUMMARY_ROWS),

    http("Tandoor search", [8 * X, 1040],
         f"={{{{ '{TANDOOR}/recipe/?page_size=1&query=' + encodeURIComponent($json.recipe_query) }}}}", CRED_TANDOOR),
    code("Pick recipe", [9 * X, 1040], PICK_RECIPE),
    bool_if("Recipe found?", [10 * X, 1040], "={{ $json.found }}"),
    tg_send("Send no recipe", [11 * X, 1120]),
    http("Tandoor recipe", [11 * X, 1000], f"={{{{ '{TANDOOR}/recipe/' + $json.recipe_id + '/' }}}}", CRED_TANDOOR),
    grocy_get("Grocy stock (cook)", [12 * X, 1000], "stock"),
    grocy_get("Grocy products (cook)", [13 * X, 1000], "objects/products"),
    grocy_get("Grocy units (cook)", [14 * X, 1000], "objects/quantity_units"),
    code("Cook plan", [15 * X, 1000], COOK_PLAN),
    tg_send("Send cook plan", [16 * X, 1000], rows=COOK_ROWS),

    grocy_get("Grocy stock (ate)", [8 * X, 1200], "stock"),
    grocy_get("Grocy units (ate)", [9 * X, 1200], "objects/quantity_units"),
    code("Ate plan", [10 * X, 1200], ATE_PLAN),
    http("Consume eaten", [11 * X, 1200],
         noop_or("$json.noop", f"'{GROCY}/stock/products/' + $json.product_id + '/consume'"), CRED_GROCY,
         method="={{ $json.noop ? 'GET' : 'POST' }}", body="={{ JSON.stringify($json.body || {}) }}",
         on_error="continueRegularOutput"),
    code("Ate reply", [12 * X, 1200], ATE_REPLY),
    tg_send("Send ate", [13 * X, 1200]),

    grocy_get("Grocy stock (st)", [8 * X, 1340], "objects/stock"),
    grocy_get("Grocy products (st)", [8 * X, 1420], "objects/products"),
    grocy_get("Grocy units (st)", [9 * X, 1340], "objects/quantity_units"),
    grocy_get("Grocy locations (st)", [10 * X, 1340], "objects/locations"),
    code("Stock reply", [11 * X, 1340], STOCK_REPLY),
    tg_send("Send stock", [12 * X, 1340]),

    http("Tandoor shopping", [8 * X, 1480], f"{TANDOOR}/shopping-list-entry/?page_size=500", CRED_TANDOOR,
         always=True),
    code("Shopping reply", [9 * X, 1480], SHOPPING_REPLY),
    tg_send("Send shopping", [10 * X, 1480]),

    tg_send("Send intent help", [8 * X, 1620], "=" + HELP_TEXT),
]


def link(*names):
    return [[{"node": n, "type": "main", "index": 0} for n in names]]


def outs(*branches):
    return [[{"node": n, "type": "main", "index": 0} for n in b] for b in branches]


connections = {
    "Telegram In": {"main": link("Classify")},
    "Classify": {"main": link("Route")},
    "Route": {"main": outs(["Ack reading", "Grocy stores (read)"], ["Answer button"], ["Text context"])},
    "Grocy stores (read)": {"main": link("Download file")},
    "Download file": {"main": link("Build LLM request")},
    "Build LLM request": {"main": link("OpenRouter extract")},
    "OpenRouter extract": {"main": link("Parse ticket")},
    "Parse ticket": {"main": link("Ticket OK?")},
    "Ticket OK?": {"main": outs(["Grocy products"], ["Send read error"])},
    "Grocy products": {"main": link("Match products")},
    "Match products": {"main": link("Send summary")},

    "Answer button": {"main": link("Resolve callback")},
    "Resolve callback": {"main": link("Callback mode")},
    "Callback mode": {"main": outs(["Grocy locations"], ["Grocy locations (cook)"], ["Send callback reply"])},
    "Grocy locations": {"main": link("Grocy units")},
    "Grocy units": {"main": link("Grocy groups")},
    "Grocy groups": {"main": link("Grocy stores")},
    "Grocy stores": {"main": link("Store plan")},
    "Store plan": {"main": link("Ensure store")},
    "Ensure store": {"main": link("Build writes")},
    "Build writes": {"main": link("Ensure product")},
    "Ensure product": {"main": link("Save aliases")},
    "Save aliases": {"main": link("Add stock")},
    "Add stock": {"main": link("Summary")},
    "Summary": {"main": link("Tandoor shopping (tk)")},
    "Tandoor shopping (tk)": {"main": link("Checkoff ops")},
    "Checkoff ops": {"main": link("Tandoor ops (tk)")},
    "Tandoor ops (tk)": {"main": link("Saved msg")},
    "Saved msg": {"main": link("Send saved")},
    "Grocy locations (cook)": {"main": link("Grocy units (cook2)")},
    "Grocy units (cook2)": {"main": link("Cook writes")},
    "Cook writes": {"main": link("Consume ingredients")},
    "Consume ingredients": {"main": link("Portion plan")},
    "Portion plan": {"main": link("Ensure portion product")},
    "Ensure portion product": {"main": link("Add portions")},
    "Add portions": {"main": link("Cook summary")},
    "Cook summary": {"main": link("Send cook done")},

    "Text context": {"main": link("Text mode")},
    "Text mode": {"main": outs(["Send help"], ["OpenRouter intent"])},
    "OpenRouter intent": {"main": link("Parse intent")},
    "Parse intent": {"main": link("Intent")},
    "Intent": {"main": outs(["Apply correction"], ["Tandoor search"], ["Grocy stock (ate)"], ["Grocy stock (st)"],
                            ["Tandoor shopping"], ["Send intent help"])},
    "Apply correction": {"main": link("Grocy products (corr)")},
    "Grocy products (corr)": {"main": link("Match corrected")},
    "Match corrected": {"main": link("Send corrected summary")},
    "Tandoor search": {"main": link("Pick recipe")},
    "Pick recipe": {"main": link("Recipe found?")},
    "Recipe found?": {"main": outs(["Tandoor recipe"], ["Send no recipe"])},
    "Tandoor recipe": {"main": link("Grocy stock (cook)")},
    "Grocy stock (cook)": {"main": link("Grocy products (cook)")},
    "Grocy products (cook)": {"main": link("Grocy units (cook)")},
    "Grocy units (cook)": {"main": link("Cook plan")},
    "Cook plan": {"main": link("Send cook plan")},
    "Grocy stock (ate)": {"main": link("Grocy units (ate)")},
    "Grocy units (ate)": {"main": link("Ate plan")},
    "Ate plan": {"main": link("Consume eaten")},
    "Consume eaten": {"main": link("Ate reply")},
    "Ate reply": {"main": link("Send ate")},
    "Grocy stock (st)": {"main": link("Grocy products (st)")},
    "Grocy products (st)": {"main": link("Grocy units (st)")},
    "Grocy units (st)": {"main": link("Grocy locations (st)")},
    "Grocy locations (st)": {"main": link("Stock reply")},
    "Stock reply": {"main": link("Send stock")},
    "Tandoor shopping": {"main": link("Grocy stock (sh)")},
    "Grocy stock (sh)": {"main": link("Grocy units (sh)")},
    "Grocy units (sh)": {"main": link("Shopping reply")},
    "Shopping reply": {"main": link("Send shopping")},
}

# ---------------------------------------------------------------- weekly planner (W3-W6)
RECIPIENTS_JS = f"const RECIPIENTS = {json.dumps(CHAT_IDS)};\n"
DAY_ENUM = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

PLAN_SCHEMA = {
    "name": "week_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["reply", "show_only", "slots", "substitutions"],
        "properties": {
            "reply": {"type": "string"},
            "show_only": {"type": "boolean"},
            "slots": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["slot", "meal", "recipe_id", "days"],
                "properties": {
                    "slot": {"type": "string"},
                    "meal": {"type": "string", "enum": ["comida", "cena", "desayuno", "merienda"]},
                    "recipe_id": {"type": "integer"},
                    "days": {"type": "array", "items": {"type": "string", "enum": DAY_ENUM}},
                }}},
            "substitutions": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["from", "to"],
                "properties": {"from": {"type": "string"}, "to": {"type": "string"}}}},
        },
    },
}

PROPOSE_PROMPT = HOUSEHOLD + """
Plan next week's menu from the candidate recipes (use only their ids).
Default layout:
- L1: lunch on mon+tue, L2: lunch on wed+thu. Both are batch-cooked together on Sunday, so pick recipes with kind "comida-batch", ideally one that freezes well for L2, and that can be cooked in the same session with 3 burners + air fryer + rice cooker (avoid two oven recipes).
- D1 dinner mon, D2 dinner tue, D3 dinner wed. Pick kind "cena" (quick). Thursday and Friday dinners stay free.
Personal block for __PERSONAL_NAME__ only (1 person, every day mon-sun): pick 2 recipes of kind "desayuno" (slots A1, A2) and 2 of kind "merienda" (slots M1, M2), high in protein,
mostly savory: at most ONE sweet recipe (tag "dulce") in the whole personal block and give it only 1-2 days; every day must have exactly one desayuno and one merienda
(e.g. A1 = mon,tue,wed,thu,fri and A2 = sat,sun; M1 = mon,wed,fri,sat,sun and M2 = tue,thu). Weekdays (mon-fri) may ONLY use recipes tagged "fácil" (no stove, <= 5 min); recipes tagged "fin-de-semana" (cooked) may only go on sat/sun.
Prefer recipes tagged "prep-domingo" for weekdays. Do not repeat the same main ingredient across the personal block (e.g. not eggs both at breakfast and snack, max ~8 eggs per week in total).
Rules for the shared meals: 5 different recipes; vary main protein and cuisine (not two stews, not two chicken dishes, include at least one legume or vegetable-forward meal); never pick ids in avoid_recipe_ids; prefer recipes that use items in expiring_at_home.
Season: month is given; recipes tagged temporada-otoño fit September-December. Include 1-2 seasonal recipes when in season, but keep the variety (not all of them).
wishes: requests the household made for this menu. Satisfy every wish with a matching candidate (by recipe name or main ingredient) in a sensible slot; if no candidate fits a wish, say so in reply and suggest sending the bot a recipe link.
reply: 1-2 short sentences in Spanish explaining the choice (variety, what uses up expiring items). show_only=false, substitutions=[]."""

EDIT_PROMPT = HOUSEHOLD + """
You edit the household's weekly menu according to the user's Spanish message. Return the FULL resulting week.
- Keep every slot the user did not mention exactly as it is (same slot, meal, recipe_id, days).
- Replace: pick another candidate of the right kind (lunch -> "comida-batch", dinner -> "cena", breakfast -> "desayuno", snack/merienda -> "merienda") not already in the week, and keep variety: avoid the main protein already used by 2 or more other slots (e.g. do not add a third chicken dish).
- Remove: drop the slot. Add: create a new slot (L3, D4...) with the requested meal and days. Move: change days.
- "otra propuesta"/"cambia todo": build a new week with the default layout (L1 mon+tue, L2 wed+thu, D1 mon, D2 tue, D3 wed) avoiding the current recipes.
- If current_week is null, create a new week with the default layout.
- Ingredient not found ("no encuentro X", "no tienen X"): look at week_recipe_ingredients. If X is a minor ingredient, keep the recipe and add a substitution {from: X, to: ONE product that can be bought as is in Spanish supermarkets, e.g. "Miel" or "Sriracha"; never a mix like "soja y miel"; if the recipe already has the other components, name only the missing product}. If X is a main ingredient, replace that recipe with a candidate that does not need it.
- Breakfast (desayuno) and snack (merienda) slots are __PERSONAL_NAME__'s personal block (1 person, every day): keep every day covered by exactly one desayuno and one merienda; mostly savory, at most one sweet recipe for 1-2 days; mon-fri only recipes tagged "fácil", "fin-de-semana" recipes only sat/sun.
- If the user only wants to see the menu, return the week unchanged with show_only=true.
reply: one short sentence in Spanish describing what changed."""

GUIDE_PROMPT = HOUSEHOLD + """
Plan the Sunday batch-cooking session in Spanish for the lunches below: cook ALL servings_needed of every lunch recipe now,
interleaving both recipes so the burners work in parallel, plus quick prep for the dinners (chopping, marinades, sauces, without
cooking them) and for __PERSONAL_NAME__'s personal breakfasts/snacks if they need advance prep (e.g. boil eggs, overnight oats).
Return JSON only:
- total_minutes: realistic total session time.
- before: 2-4 sentences: what to take out, wash, chop and measure before starting (mise en place).
- steps: 6 to 14 steps in time order. Each step: title (short), device (one of the allowed values), instruction (2-4 sentences
  with heat level, duration and the cue that tells it is done; say what is running in parallel), time in minutes, and
  ingredients = indexes from lunch_ingredients that go into the pot IN THAT STEP. Every index exactly once across all steps.
  Keep each recipe on the same burner for the whole session. Respect the equipment: max 3 pots/pans at once, one air fryer,
  one rice cooker. Do not include portioning/storage steps (added separately).
- dinner_prep: what to prep today for the dinners (1-4 short sentences, or "" if nothing useful).
- personal_prep: advance prep for __PERSONAL_NAME__'s breakfasts/snacks (1-3 short sentences, or "" if none needed).
Plain UTF-8 text, natural amounts ("600 g", "2 cebollas"), no HTML entities."""

GUIDE_SCHEMA = {
    "name": "batch_session",
    "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False,
        "required": ["total_minutes", "before", "steps", "dinner_prep", "personal_prep"],
        "properties": {
            "total_minutes": {"type": "integer"},
            "before": {"type": "string"},
            "steps": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["title", "device", "instruction", "time", "ingredients"],
                "properties": {
                    "title": {"type": "string"},
                    "device": {"type": "string", "enum": ["Fogón grande", "Fogón mediano", "Fogón pequeño", "Air fryer",
                                                          "Arrocera", "Encimera", "Horno"]},
                    "instruction": {"type": "string"},
                    "time": {"type": "integer"},
                    "ingredients": {"type": "array", "items": {"type": "integer"}},
                }}},
            "dinner_prep": {"type": "string"},
            "personal_prep": {"type": "string"},
        },
    },
}

def plan_js(body):
    return NORM_JS + RECIPIENTS_JS + WEEK_JS + body


WEEK_JS = r"""
const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
const DAY_ES = { mon: 'Lun', tue: 'Mar', wed: 'Mié', thu: 'Jue', fri: 'Vie', sat: 'Sáb', sun: 'Dom' };
const isoDay = d => d.toISOString().slice(0, 10);
const nextMonday = () => { const d = new Date(); const dow = (d.getDay() + 6) % 7; d.setDate(d.getDate() + (7 - dow)); return isoDay(d); };
const dayDate = (ws, day) => { const d = new Date(`${ws}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + DAYS.indexOf(day)); return isoDay(d); };
const weekIsCurrent = w => !!w && dayDate(w.week_start, 'sun') >= isoDay(new Date());
const kwNames = r => (r.keywords || []).map(k => k.name || k.label).filter(Boolean);
const stemW = x => (x.length > 4 ? x.replace(/(es|s)$/, '') : x);
const nameHas = (name, ws) => ws.length > 0 && ws.every(m => norm(name).split(' ').map(stemW).includes(m));
const activeAvoid = sd => (sd.avoid || []).filter(a => Date.now() - a.at < 30 * 864e5);
const candidates = recipes => recipes.filter(r => !kwNames(r).includes('sesion-batch')).map(r => ({
  id: r.id, name: r.name,
  kind: kwNames(r).find(k => ['comida-batch', 'cena', 'desayuno', 'merienda'].includes(k)) || 'otro',
  tags: kwNames(r).filter(k => !['comida-batch', 'cena', 'desayuno', 'merienda'].includes(k)),
  minutes: (r.working_time || 0) + (r.waiting_time || 0),
}));
const validate = (slots, recipes) => {
  const byId = new Map(recipes.map(r => [r.id, r]));
  const out = [], seen = new Set();
  for (const s of slots || []) {
    const r = byId.get(Number(s.recipe_id));
    const days = [...new Set((s.days || []).filter(d => DAYS.includes(d)))].sort((a, b) => DAYS.indexOf(a) - DAYS.indexOf(b));
    if (!r || !days.length) continue;
    let slot = String(s.slot || '').trim() || `${s.meal === 'cena' ? 'D' : 'L'}${out.length + 1}`;
    while (seen.has(slot)) slot += '+';
    seen.add(slot);
    const meal = ['comida', 'cena', 'desayuno', 'merienda'].includes(s.meal) ? s.meal : 'comida';
    out.push({ slot, meal, recipe_id: r.id, recipe_name: r.name, days });
  }
  return out;
};
const fmtWeek = w => {
  const [, m, d] = w.week_start.split('-');
  const order = s => DAYS.indexOf(s.days[0]);
  const lunches = w.slots.filter(s => s.meal === 'comida').sort((a, b) => order(a) - order(b));
  const dinners = w.slots.filter(s => s.meal === 'cena').sort((a, b) => order(a) - order(b));
  const days = s => {
    const idx = s.days.map(x => DAYS.indexOf(x)).sort((a, b) => a - b);
    const runs = [];
    for (const i of idx) { const r = runs[runs.length - 1]; if (r && i === r[1] + 1) r[1] = i; else runs.push([i, i]); }
    return runs.map(([a, b]) => (a === b ? DAY_ES[DAYS[a]] : `${DAY_ES[DAYS[a]]}–${DAY_ES[DAYS[b]]}`)).join(', ');
  };
  let t = `📅 Menú semana del ${d}/${m}${w.status === 'accepted' ? ' ✅' : ' (propuesta)'}\n\n`;
  t += `🍱 Comidas (batch el domingo)\n${lunches.map(s => `• ${days(s)}: ${s.recipe_name} (${s.days.length * 2} raciones)`).join('\n') || '• —'}\n\n`;
  t += `🌙 Cenas\n${dinners.map(s => `• ${days(s)}: ${s.recipe_name}`).join('\n') || '• —'}\n`;
  const taken = new Set(dinners.flatMap(s => s.days));
  const free = ['mon', 'tue', 'wed', 'thu', 'fri'].filter(x => !taken.has(x)).map(x => DAY_ES[x]);
  if (free.length) t += `Cenas libres: ${free.join(', ')}\n`;
  const personal = w.slots.filter(s => s.meal === 'desayuno' || s.meal === 'merienda').sort((a, b) => order(a) - order(b));
  if (personal.length) {
    const block = m => personal.filter(s => s.meal === m).map(s => `• ${days(s)}: ${s.recipe_name}`).join('\n') || '• —';
    t += `\n🥐 Para __PERSONAL_NAME__ (1 persona)\nDesayunos\n${block('desayuno')}\nMeriendas\n${block('merienda')}\n`;
  }
  if ((w.substitutions || []).length) t += `\n🔁 Sustituciones: ${w.substitutions.map(s => `${s.from} → ${s.to}`).join(', ')}\n`;
  if (w.reason) t += `\n💡 ${w.reason}`;
  return t;
};
const HINT = '\n\n✏️ Pide cambios escribiendo: "cambia la cena del martes", "quita el chili", "no encuentro X".';
const homeIndex = (stockRows, unitsById) => {
  const FORMW = new Set(['triturado', 'frito', 'concentrado', 'seco', 'molido', 'polvo', 'congelado', 'zumo', 'jugo', 'salsa', 'crema', 'caldo', 'pure', 'deshidratado', 'ahumado', 'tostado', 'cocido', 'encurtido', 'escabeche', 'desecado', 'rallado']);
  // a processed form (crushed, canned, smoked, cooked...) on only one side means a different product
  const formClash = (a, b) => a.some(w => FORMW.has(w) && !b.includes(w)) || b.some(w => FORMW.has(w) && !a.includes(w));
  const STOPW = new Set(['de', 'del', 'la', 'el', 'los', 'las', 'en', 'con', 'y', 'al', 'lata', 'bote']);
  const ws = x => norm(x).split(' ').filter(w => w && !STOPW.has(w)).map(w => (w.length > 3 ? w.replace(/(es|s)$/, '') : w));
  const UG = { g: 1, kg: 1000 }, UM = { ml: 1, l: 1000 }, UP = ['', 'unidad', 'unidades', 'pieza', 'piezas'];
  const conv = (a, f, t) => { f = norm(f); t = norm(t); if (f === t) return a; if (UG[f] && UG[t]) return a * UG[f] / UG[t];
    if (UM[f] && UM[t]) return a * UM[f] / UM[t]; if (UP.includes(f) && UP.includes(t)) return a; return null; };
  const rows = (stockRows || []).filter(r => r && r.product_id && Number(r.amount) > 0 && !/raci[oó]n/i.test(r.product.name));
  const find = food => rows.find(r => Number((r.product.userfields || {}).tandoor_food_id) === food.id)
    || rows.find(r => norm(r.product.name) === norm(food.name))
    || rows.filter(r => { const f = ws(food.name), pl = ws(r.product.name), pr = new Set(pl); return f.length && !formClash(f, pl) && f.every(w => pr.has(w)); })
      .sort((a, b) => ws(a.product.name).length - ws(b.product.name).length)[0];
  return (food, amount, unit) => {
    const r = food ? find(food) : null;
    if (!r) return null;
    const u = unitsById[r.product.qu_id_stock] || {};
    const have = Number(r.amount);
    const need = conv(amount || 0, unit || '', u.name || '');
    return { text: `en casa: ${num(Math.round(have * 1000) / 1000)} ${qn(u, have)}`.trim(), covered: need !== null && need > 0 && have >= need };
  };
};
const groupList = (entries, home) => {
  const agg = new Map();
  for (const e of entries) {
    const food = e.food ? e.food.name : '?';
    const unit = e.unit ? e.unit.name : '';
    const kws = (((e.list_recipe_data || {}).recipe_data || {}).keywords || []).map(x => x.label || x.name);
    const personal = kws.includes('desayuno') || kws.includes('merienda');
    const k = `${personal ? 'A' : 'S'}|${food}|${unit}`;
    const a = agg.get(k) || { foodObj: e.food, food, unit, amount: 0, personal, cat: (e.food && e.food.supermarket_category && e.food.supermarket_category.name) || 'Otros' };
    a.amount += Number(e.amount || 0);
    agg.set(k, a);
  }
  const groups = {}, covered = [], personalLines = [];
  for (const a of agg.values()) {
    const amount = a.amount ? `${num(Math.round(a.amount * 100) / 100)} ${a.unit}`.trim() : '';
    const h = home ? home(a.foodObj, a.amount, a.unit) : null;
    const line = `• ${a.food}${amount ? ` — ${amount}` : ''}${h ? ` (${h.text})` : ''}`;
    if (h && h.covered) covered.push(line); else if (a.personal) personalLines.push(line); else (groups[a.cat] ||= []).push(line);
  }
  let out = Object.entries(groups).map(([k, v]) => `${k}\n${v.sort().join('\n')}`).join('\n\n');
  if (personalLines.length) out += `${out ? '\n\n' : ''}🥐 Solo __PERSONAL_NAME__ (desayunos y meriendas)\n${personalLines.sort().join('\n')}`;
  if (covered.length) out += `${out ? '\n\n' : ''}✔️ Ya en casa (comprar solo si falta)\n${covered.sort().join('\n')}`;
  return out;
};
const countItems = entries => new Set(entries.map(e => `${e.food ? e.food.name : '?'}|${e.unit ? e.unit.name : ''}|${JSON.stringify((((e.list_recipe_data || {}).recipe_data || {}).keywords || []).map(x => x.label || x.name).filter(k => k === 'desayuno' || k === 'merienda'))}`)).size;
"""

PLANNER_ENTRY = plan_js(r"""
const sd = $getWorkflowStaticData('global');
const rp = $('Run planner').isExecuted ? ($('Run planner').first().json.body || {}) : {};
const chats = $('Classify').isExecuted ? [$('Classify').first().json.chat_id] : (rp.chat ? [rp.chat] : RECIPIENTS);
const exclude = $('Resolve callback').isExecuted && sd.week ? sd.week.slots.map(s => s.recipe_id) : [];
const week_start = rp.week_start || nextMonday();
// The scheduled Friday proposal never replaces a week the household already accepted; explicit requests still can.
const scheduled = !$('Classify').isExecuted && !$('Run planner').isExecuted;
if (scheduled && sd.week && sd.week.week_start === week_start && sd.week.status === 'accepted' && sd.week.slots.length) {
  return chats.map(chat_id => ({ json: { skip: true, chat_id,
    text: '📅 El menú de la semana que viene ya está aceptado ✅ (escribe /menu para verlo). Si queréis una propuesta nueva: /propuesta' } }));
}
return [{ json: { skip: false, chats, exclude, week_start } }];
""")

BUILD_PROPOSAL = plan_js(r"""
const e = $('Planner entry').first().json;
const sd = $getWorkflowStaticData('global');
const recipes = $('Tandoor recipes (pl)').all().flatMap(i => i.json.results || []);
const vol = $('Grocy volatile (pl)').first().json || {};
const expiring = [...(vol.due_products || []), ...(vol.overdue_products || [])].map(x => x.product && x.product.name).filter(Boolean);
const history = (sd.history || []).filter(h => h.week_start !== e.week_start).slice(-2).flatMap(h => h.recipe_ids);
const allowed = recipes.filter(r => !activeAvoid(sd).some(a => nameHas(r.name, a.words)));
const input = { week_start: e.week_start, month: new Date().toLocaleString('es-ES', { month: 'long' }), wishes: (sd.wishes || []).map(w => w.text), avoid_recipe_ids: [...new Set([...history, ...e.exclude])],
                expiring_at_home: expiring, candidates: candidates(allowed) };
return [{ json: { request: {
  model: __MODEL__, temperature: 0.7,
  messages: [{ role: 'system', content: __PROMPT__ }, { role: 'user', content: JSON.stringify(input) }],
  response_format: { type: 'json_schema', json_schema: __SCHEMA__ },
} } }];
""").replace("__MODEL__", json.dumps(MODEL)).replace("__PROMPT__", json.dumps(PROPOSE_PROMPT)).replace(
    "__SCHEMA__", json.dumps(PLAN_SCHEMA))

APPLY_PROPOSAL = plan_js(r"""
const e = $('Planner entry').first().json;
const sd = $getWorkflowStaticData('global');
const recipes = $('Tandoor recipes (pl)').all().flatMap(i => i.json.results || []);
const r = $input.first().json;
let p = null;
try { p = JSON.parse(r.choices[0].message.content); } catch (err) { p = null; }
const slots = p ? validate(p.slots, recipes) : [];
if (!slots.length) return e.chats.map(chat_id => ({ json: { ok: false, chat_id, text: 'No he podido preparar la propuesta ahora mismo. Escribe "otra propuesta" para reintentarlo.' } }));
const prev = sd.week && sd.week.week_start === e.week_start ? sd.week : null;
sd.wishes = [];
sd.week = { week_start: e.week_start, status: 'proposed', slots, substitutions: [], reason: p.reply || '',
            created: prev ? (prev.created || []) : [], updated: new Date().toISOString() };
const text = fmtWeek(sd.week) + HINT;
return e.chats.map(chat_id => ({ json: { ok: true, chat_id, week_start: e.week_start, text } }));
""")

WEEK_RECIPE_IDS = plan_js(r"""
const sd = $getWorkflowStaticData('global');
const ids = weekIsCurrent(sd.week) ? [...new Set(sd.week.slots.map(s => s.recipe_id))] : [];
return ids.length ? ids.map(id => ({ json: { id, noop: false } })) : [{ json: { noop: true } }];
""")

BUILD_EDIT = plan_js(r"""
const i = $('Parse intent').first().json;
const sd = $getWorkflowStaticData('global');
const recipes = $('Tandoor recipes (ed)').all().flatMap(x => x.json.results || []);
const details = $('Week recipes (ed)').all().map(x => x.json).filter(d => d && Array.isArray(d.steps));
const w = weekIsCurrent(sd.week) ? sd.week : null;
const msg = i.plan_request || $('Classify').first().json.text || '';
const missing = (norm(msg).match(/no (?:encuentro|encontramos|tienen|tiene|hay|queda|quedan)(?: de)? (.+)$/) || [])[1] || '';
const missingWords = missing.split(' ').filter(x => x.length > 2 && !['en', 'el', 'la', 'los', 'las', 'del', 'supermercado', 'mercado'].includes(x)).map(stemW);
if (missingWords.length) sd.avoid = [...activeAvoid(sd).filter(a => a.words.join(' ') !== missingWords.join(' ')), { words: missingWords, label: missing, at: Date.now() }];
const allowed = recipes.filter(r => !nameHas(r.name, missingWords) && !activeAvoid(sd).some(a => nameHas(r.name, a.words)));
const input = {
  today: isoDay(new Date()),
  missing_ingredient: missing || null,
  current_week: w ? { week_start: w.week_start, status: w.status, substitutions: w.substitutions || [],
    slots: w.slots.map(({ slot, meal, recipe_id, recipe_name, days }) => ({ slot, meal, recipe_id, recipe_name, days })) } : null,
  week_recipe_ingredients: details.map(d => ({ id: d.id, name: d.name,
    ingredients: d.steps.flatMap(s => s.ingredients || []).filter(g => g.food).map(g => g.food.name) })),
  candidates: candidates(allowed),
  message: msg,
};
return [{ json: { request: {
  model: __MODEL__, temperature: 0.3,
  messages: [{ role: 'system', content: __PROMPT__ }, { role: 'user', content: JSON.stringify(input) }],
  response_format: { type: 'json_schema', json_schema: __SCHEMA__ },
} } }];
""").replace("__MODEL__", json.dumps(MODEL)).replace("__PROMPT__", json.dumps(EDIT_PROMPT)).replace(
    "__SCHEMA__", json.dumps(PLAN_SCHEMA))

APPLY_EDIT = plan_js(r"""
const i = $('Parse intent').first().json;
const sd = $getWorkflowStaticData('global');
const recipes = $('Tandoor recipes (ed)').all().flatMap(x => x.json.results || []);
const r = $input.first().json;
let p = null;
try { p = JSON.parse(r.choices[0].message.content); } catch (err) { p = null; }
const send = (route, text, week_start) => [{ json: { route, chat_id: i.chat_id, text, week_start } }];
if (!p) return send('send', 'No he entendido el cambio. Prueba con algo como "cambia la cena del martes".');
const current = weekIsCurrent(sd.week) ? sd.week : null;
if (p.show_only && current) return send(current.status === 'accepted' ? 'send' : 'send_buttons', fmtWeek(current) + (current.status === 'accepted' ? '' : HINT), current.week_start);
const slots = validate(p.slots, recipes);
if (!slots.length) return send('send', 'No he podido aplicar ese cambio. Prueba a decirlo de otra forma.');
const week = current && current.slots.length ? current
  : { week_start: current ? current.week_start : nextMonday(), status: 'proposed', created: current ? (current.created || []) : [] };
week.slots = slots;
week.substitutions = (p.substitutions || []).filter(s => s.from && s.to);
week.reason = p.reply || '';
week.updated = new Date().toISOString();
sd.week = week;
if (week.status === 'accepted') return send('sync', '', week.week_start);
return send('send_buttons', fmtWeek(week) + HINT, week.week_start);
""")

PLAN_OPS = plan_js(r"""
const sd = $getWorkflowStaticData('global');
const w = sd.week;
const types = $('Tandoor meal types').all().flatMap(x => x.json.results || (x.json.id ? [x.json] : []));
const mt = Object.fromEntries(types.map(t => [norm(t.name), t]));
const desired = w.slots.flatMap(s => s.days.map(day => ({ key: `${s.slot}|${day}|${s.recipe_id}`, day, recipe_id: s.recipe_id, recipe_name: s.recipe_name, meal: s.meal })));
const existing = w.created || [];
const dk = new Set(desired.map(d => d.key)), ek = new Set(existing.map(e => e.key));
const ops = [];
for (const e of existing) if (!dk.has(e.key)) ops.push({ op: 'del_plan', key: e.key, method: 'DELETE', path: `/meal-plan/${e.mealplan_id}/`, body: {} });
for (const d of desired) if (!ek.has(d.key)) {
  const t = mt[d.meal] || mt['comida'];
  const date = dayDate(w.week_start, d.day);
  ops.push({ op: 'add_plan', key: d.key, method: 'POST', path: '/meal-plan/', body: {
    recipe: { id: d.recipe_id, name: d.recipe_name, keywords: [] }, servings: d.meal === 'desayuno' || d.meal === 'merienda' ? 1 : 2,
    from_date: `${date}T00:00:00`, to_date: `${date}T00:00:00`,
    meal_type: { id: t.id, name: t.name }, title: '', addshopping: true } });
}
if (!ops.length) ops.push({ op: 'noop', method: 'GET', path: '/meal-type/', body: {} });
return ops.map(o => ({ json: o }));
""")

PLAN_SYNCED = plan_js(r"""
const sd = $getWorkflowStaticData('global');
const w = sd.week;
const ops = $('Plan ops').all().map(x => x.json);
const res = $input.all().map(x => x.json);
let created = (w.created || []).slice();
let failed = 0;
ops.forEach((o, idx) => {
  const r = res[idx] || {};
  if (o.op === 'del_plan') { if (r.error) failed++; else created = created.filter(c => c.key !== o.key); }
  if (o.op === 'add_plan') { if (r.id) created.push({ key: o.key, mealplan_id: r.id }); else failed++; }
});
w.created = created;
w.status = 'accepted';
w.accepted_at = new Date().toISOString();
sd.history = (sd.history || []).filter(h => h.week_start !== w.week_start)
  .concat([{ week_start: w.week_start, recipe_ids: [...new Set(w.slots.map(s => s.recipe_id))] }]).slice(-6);
return [{ json: { failed, changed: ops.filter(o => o.op !== 'noop').length } }];
""")

SUB_OPS = plan_js(r"""
const w = $getWorkflowStaticData('global').week;
const entries = ($('Tandoor shopping (sub)').first().json.results || []).filter(e => !e.checked);
const ops = [];
for (const s of w.substitutions || []) {
  const from = norm(s.from);
  const hits = entries.filter(e => e.food && (norm(e.food.name).includes(from) || from.includes(norm(e.food.name))));
  for (const e of hits) ops.push({ method: 'DELETE', path: `/shopping-list-entry/${e.id}/`, body: {} });
  const hasTo = entries.some(e => e.food && norm(e.food.name) === norm(s.to));
  if (hits.length && !hasTo) {
    const h = hits[0];
    const unitOf = x => (x.unit ? x.unit.name : '');
    const total = hits.filter(x => unitOf(x) === unitOf(h)).reduce((a, x) => a + Number(x.amount || 0), 0);
    ops.push({ method: 'POST', path: '/shopping-list-entry/', body: { food: { name: s.to }, unit: h.unit ? { name: h.unit.name } : null, amount: total || 1 } });
  }
}
if (!ops.length) ops.push({ method: 'GET', path: '/meal-type/', body: {} });
return ops.map(o => ({ json: o }));
""")

PLAN_LIST_MSG = plan_js(r"""
const sd = $getWorkflowStaticData('global');
const chat_id = $('Resolve callback').isExecuted ? $('Resolve callback').first().json.chat_id
  : $('Parse intent').isExecuted ? $('Parse intent').first().json.chat_id : RECIPIENTS[0];
const synced = $('Plan synced').first().json;
const entries = ($('Tandoor shopping (pl)').first().json.results || []).filter(e => !e.checked);
const home = homeIndex($('Grocy stock (list)').all().map(x => x.json), Object.fromEntries($('Grocy units (list)').all().map(x => [x.json.id, x.json])));
let week = fmtWeek(sd.week);
if (synced.failed) week += `\n⚠ ${synced.failed} cambios no se pudieron guardar en Tandoor.`;
const list = entries.length ? `🛒 Lista de la compra del menú (${countItems(entries)} productos)\n\n${groupList(entries, home)}` : '🛒 La lista de la compra está vacía.';
return [{ json: { chat_id, text: week } }, { json: { chat_id, text: list.slice(0, 4000) } }];
""")

GUIDE_ENTRY = plan_js(r"""
const w = $getWorkflowStaticData('global').week;
const rp = $('Run planner').isExecuted ? ($('Run planner').first().json.body || {}) : {};
const chats = $('Classify').isExecuted ? [$('Classify').first().json.chat_id] : (rp.chat ? [rp.chat] : RECIPIENTS);
if (!w || w.status !== 'accepted' || !weekIsCurrent(w)) {
  return chats.map(chat_id => ({ json: { skip: true, chat_id, text: 'No hay un menú aceptado para esta semana: no hay batch que preparar.' } }));
}
return [...new Set(w.slots.map(s => s.recipe_id))].map(id => ({ json: { skip: false, id, chats } }));
""")

BUILD_GUIDE = plan_js(r"""
const details = $input.all().map(x => x.json).filter(d => d && Array.isArray(d.steps));
if (!details.length) return [];
const w = $getWorkflowStaticData('global').week;
const find = id => details.find(x => x.id === id);
const lunchIngredients = [];
const lunches = w.slots.filter(s => s.meal === 'comida').map(s => {
  const d = find(s.recipe_id);
  if (!d) return null;
  const need = s.days.length * 2, factor = need / (d.servings || need);
  for (const st of d.steps) for (const g of st.ingredients || []) {
    if (!g.food || g.is_header) continue;
    lunchIngredients.push({ recipe: d.name, food: g.food.name, unit: g.unit ? g.unit.name : '', note: g.note || '',
                            amount: g.amount ? Math.round(g.amount * factor * 100) / 100 : 0 });
  }
  return { days: s.days, servings_needed: need, name: d.name,
           steps: d.steps.map(st => `${st.name ? st.name + ': ' : ''}${st.instruction}`).join('\n') };
}).filter(Boolean);
const describe = id => { const d = find(id); return d ? { name: d.name, steps: d.steps.map(st => st.instruction).join('\n') } : null; };
const input = {
  lunches,
  lunch_ingredients: lunchIngredients.map((g, i) => `${i}: ${g.amount || ''} ${g.unit} ${g.food} [${g.recipe}]`.replace(/\s+/g, ' ')),
  dinners: w.slots.filter(s => s.meal === 'cena').map(s => ({ days: s.days, recipe: describe(s.recipe_id) })),
  personal_breakfasts_snacks: w.slots.filter(s => s.meal === 'desayuno' || s.meal === 'merienda').map(s => ({ meal: s.meal, days: s.days, recipe: describe(s.recipe_id) })),
};
// Portioning is deterministic: 2 tuppers per lunch day; up to 3 days after Sunday in the fridge, later days frozen.
const freezable = id => ((find(id) || {}).keywords || []).some(k => (k.name || k.label) === 'congelable');
const offset = d => DAYS.indexOf(d) + 1;
const storage = [];
for (const s of w.slots.filter(s => s.meal === 'comida').sort((a, b) => offset(a.days[0]) - offset(b.days[0]))) {
  for (const d of s.days) {
    if (offset(d) <= 3) storage.push(`• ${DAY_ES[d]}: 2 tuppers de ${s.recipe_name} → nevera`);
    else storage.push(`• ${DAY_ES[d]}: 2 tuppers de ${s.recipe_name} → congelador; pásalos a la nevera la noche de ${DAY_ES[DAYS[DAYS.indexOf(d) - 1]].toLowerCase()}` + (freezable(s.recipe_id) ? '' : ' (⚠ no es de las que mejor congelan: si prefieres, cocínalo la noche anterior)'));
  }
}
return [{ json: { storage: storage.join('\n'), lunch_ingredients: lunchIngredients, request: {
  model: __MODEL__, temperature: 0.3,
  messages: [{ role: 'system', content: __PROMPT__ }, { role: 'user', content: JSON.stringify(input) }],
  response_format: { type: 'json_schema', json_schema: __SCHEMA__ },
} } }];
""").replace("__MODEL__", json.dumps(GUIDE_MODEL)).replace("__PROMPT__", json.dumps(GUIDE_PROMPT)).replace(
    "__SCHEMA__", json.dumps(GUIDE_SCHEMA, ensure_ascii=False))

SESSION_PLAN = plan_js(r"""
const sd = $getWorkflowStaticData('global');
const w = sd.week;
const b = $('Build guide').first().json;
const r = $input.first().json;
let g = null;
try { g = JSON.parse(r.choices[0].message.content); } catch (e) { g = null; }
const chats = $('Guide entry').first().json.chats;
if (!g || !Array.isArray(g.steps) || !g.steps.length) return [{ json: { ok: false, chats } }];
const ings = b.lunch_ingredients;
// every lunch ingredient must be used exactly once; otherwise fall back to listing them on the first cooking step
const used = g.steps.flatMap(st => st.ingredients || []);
const valid = used.length === ings.length && new Set(used).size === ings.length && used.every(i => i >= 0 && i < ings.length);
if (!valid) g.steps.forEach((st, i) => { st.ingredients = i === 0 ? ings.map((_, k) => k) : []; });
const ICON = { 'Fogón grande': '🔥', 'Fogón mediano': '🔥', 'Fogón pequeño': '🔥', 'Air fryer': '🌀', 'Arrocera': '🍚', 'Encimera': '🔪', 'Horno': '♨️' };
const sunday = (() => { const d = new Date(`${w.week_start}T12:00:00Z`); d.setUTCDate(d.getUTCDate() - 1); return d.toISOString().slice(0, 10); })();
const [, mm, dd] = sunday.split('-');
const lunchNames = [...new Set(ings.map(x => x.recipe))];
const steps = [{ name: 'Preparación', instruction: g.before, time: 0, order: 0, ingredients: [] }];
g.steps.forEach((st, i) => steps.push({ name: `${ICON[st.device] || ''} ${st.device}: ${st.title}`.trim(), instruction: st.instruction,
  time: Math.max(0, st.time | 0), order: i + 1,
  ingredients: (st.ingredients || []).map((k, j) => ({ food: { name: ings[k].food }, unit: ings[k].unit ? { name: ings[k].unit } : null,
    amount: ings[k].amount, note: `${ings[k].recipe}${ings[k].note ? ' · ' + ings[k].note : ''}`, order: j })) }));
steps.push({ name: 'Reparto en tuppers', instruction: b.storage, time: 0, order: steps.length, ingredients: [] });
if (g.dinner_prep) steps.push({ name: 'Para las cenas', instruction: g.dinner_prep, time: 0, order: steps.length, ingredients: [] });
if (g.personal_prep) steps.push({ name: 'Para __PERSONAL_NAME__', instruction: g.personal_prep, time: 0, order: steps.length, ingredients: [] });
const body = { name: `Batch domingo ${dd}/${mm}`, description: `Sesión de batch: ${lunchNames.join(' + ')}. Generada por el bot.`,
  servings: w.slots.filter(s => s.meal === 'comida').reduce((a, s) => a + s.days.length * 2, 0) || 1, servings_text: 'raciones',
  working_time: g.total_minutes || 0, waiting_time: 0, internal: true, keywords: [{ name: 'sesion-batch' }], steps };
const old = sd.sessionRecipeId;
return [{ json: { ok: true, chats, guide: g, valid, body, old_id: old || null,
  method: old ? 'DELETE' : 'GET', path: old ? `/recipe/${old}/` : '/meal-type/' } }];
""")

GUIDE_MSG = plan_js(r"""
const sd = $getWorkflowStaticData('global');
const w = sd.week;
const plan = $('Session plan').first().json;
const b = $('Build guide').first().json;
const saved = $('Save session').first().json;
const chats = plan.chats;
let text;
if (!plan.ok) {
  text = '⚠ No he podido preparar la guía paso a paso. Las recetas detalladas están en Tandoor.' + (b.storage ? `\n\n🥡 Reparto\n${b.storage}` : '');
} else {
  const g = plan.guide;
  if (saved && saved.id) sd.sessionRecipeId = saved.id;
  const lines = g.steps.map((st, i) => `${i + 1}. [${st.device}] ${st.title}${st.time ? ` (${st.time} min)` : ''}: ${st.instruction}`);
  text = `👩‍🍳 Batch cooking${g.total_minutes ? ` · ⏱ ~${g.total_minutes} min` : ''}\n\n🧾 Antes de empezar\n${g.before}\n\n🔥 Paso a paso\n${lines.join('\n')}`
    + (b.storage ? `\n\n🥡 Reparto\n${b.storage}` : '')
    + (g.dinner_prep ? `\n\n🌙 Para las cenas\n${g.dinner_prep}` : '')
    + (g.personal_prep ? `\n\n🥐 Para __PERSONAL_NAME__\n${g.personal_prep}` : '')
    + ('__TANDOOR_PUBLIC_URL__' && saved && saved.id ? `\n\n📲 Con temporizadores e ingredientes por paso (Tandoor): __TANDOOR_PUBLIC_URL__/recipe/${saved.id}` : '');
}
const chunks = [];
let cur = '';
for (const para of text.split('\n\n')) {
  if ((cur + '\n\n' + para).length > 3800 && cur) { chunks.push(cur); cur = para; } else cur = cur ? `${cur}\n\n${para}` : para;
}
if (cur) chunks.push(cur);
return chats.flatMap(chat_id => [
  ...chunks.map(text => ({ json: { chat_id, text, button: false } })),
  { json: { chat_id, button: true, week_start: w.week_start,
    text: '¿Terminado el batch? Pulsad el botón y descuento los ingredientes de la despensa y guardo los tuppers (nevera/congelador).' } },
]);
""")

IMPORT_BUILD = NORM_JS + r"""
const ctx = $('Text context').first().json;
const r = $input.first().json;
const fail = text => [{ json: { ok: false, chat_id: ctx.chat_id, text } }];
if (r.error === true || !r.recipe || !r.recipe.name) return fail(`No he podido leer una receta en ese enlace${r.msg ? ` (${r.msg})` : ''}. Prueba con otra web o añádela en Tandoor.`);
if (r.recipe_id) return fail('Esa receta ya estaba en Tandoor.');
const rec = r.recipe;
const hint = norm(ctx.hint);
const kind = /cena/.test(hint) ? 'cena' : /comida|batch/.test(hint) ? 'comida-batch' : ((rec.servings || 0) >= 4 ? 'comida-batch' : 'cena');
rec.keywords = [...(rec.keywords || []).map(k => ({ name: k.name || k.label })).filter(k => k.name), { name: kind }, { name: 'importada' }];
rec.internal = true;
rec.steps = (rec.steps || []).map((s, i) => ({ ...s, order: i,
  ingredients: (s.ingredients || []).map((g, j) => ({ ...g, order: j, note: g.note || '' })) }));
return [{ json: { ok: true, chat_id: ctx.chat_id, kind, body: rec } }];
"""

IMPORT_DONE = r"""
const b = $('Import build').first().json;
const res = $input.first().json;
const label = b.kind === 'cena' ? 'cena' : 'comida de batch';
const text = res && res.id
  ? `✅ Guardada en Tandoor: ${res.name} (${res.servings} raciones), como ${label}. Ya puede salir en los menús. Si no encaja como ${label}, cambia la etiqueta en Tandoor.`
  : `⚠ No he podido guardar la receta: ${(res && res.error && (res.error.message || res.error)) || 'error desconocido'}`;
return [{ json: { chat_id: b.chat_id, text } }];
"""


def sched(name, pos, rule):
    return node(name, "n8n-nodes-base.scheduleTrigger", 1.2, pos, {"rule": {"interval": [rule]}})


def tandoor_ops(name, pos):
    return http(name, pos, f"={{{{ '{TANDOOR}' + $json.path }}}}", CRED_TANDOOR, method="={{ $json.method }}",
                body="={{ JSON.stringify($json.body || {}) }}", on_error="continueRegularOutput")


PLAN_ROWS = [[btn("✅ Aceptar", "=pl:ok:{{ $json.week_start }}"), btn("🔄 Otra propuesta", "=pl:new:{{ $json.week_start }}")]]
Y = 1900
nodes += [
    sched("Friday 09:00", [0, Y], {"field": "weeks", "weeksInterval": 1, "triggerAtDay": [5], "triggerAtHour": 9}),
    sched("Sunday 10:00", [0, Y + 300], {"field": "weeks", "weeksInterval": 1, "triggerAtDay": [0], "triggerAtHour": 10}),
    node("Run planner", "n8n-nodes-base.webhook", 2.1, [0, Y + 150], {
        "httpMethod": "POST", "path": PLANNER_HOOK_PATH, "authentication": "headerAuth",
        "responseMode": "onReceived", "options": {}}, credentials=CRED_BRIDGE,
        webhookId="0b6a3f0e-5a3e-4c55-9d3e-6b1c4b1f7a02"),
    switch("Planner action", [X, Y + 150], "body.action", ["propose", "guide", "reset", "dinner", "snapshot", "restore", "set_week"]),
    code("Set week", [2 * X, Y + 270], r"""
const sd = $getWorkflowStaticData('global');
const w = $('Run planner').first().json.body.week;
if (!w || !w.week_start || !Array.isArray(w.slots)) return [{ json: { ok: false } }];
sd.week = w;
return [{ json: { ok: true, week_start: w.week_start, status: w.status, slots: w.slots.length, created: (w.created || []).length } }];
""".strip()),
    code("Snapshot week", [2 * X, Y + 210], r"""
const sd = $getWorkflowStaticData('global');
const restore = $('Run planner').first().json.body.action === 'restore';
if (restore) { if (!sd.weekBackup) return [{ json: { ok: false, msg: 'no backup' } }]; sd.week = JSON.parse(sd.weekBackup); delete sd.weekBackup; }
else sd.weekBackup = JSON.stringify(sd.week || null);
return [{ json: { ok: true, action: restore ? 'restored' : 'saved', week_start: sd.week && sd.week.week_start, slots: sd.week ? sd.week.slots.length : 0 } }];
""".strip()),
    code("Reset week", [2 * X, Y + 150], r"""
const sd = $getWorkflowStaticData('global');
if (!sd.week) return [];
sd.week.slots = [];
sd.week.substitutions = [];
sd.week.reason = 'Menú reiniciado.';
if (($('Run planner').first().json.body || {}).full) { sd.avoid = []; sd.history = []; }
return [{ json: { reset: true } }];
""".strip()),

    code("Planner entry", [2 * X, Y], PLANNER_ENTRY),
    bool_if("Should propose?", [2 * X + 130, Y], "={{ !$json.skip }}"),
    tg_send("Send proposal note", [3 * X, Y + 120]),
    http("Tandoor recipes (pl)", [3 * X, Y], f"{TANDOOR}/recipe/?page_size=200", CRED_TANDOOR, once=True, always=True),
    grocy_get("Grocy volatile (pl)", [4 * X, Y], "stock/volatile?due_soon_days=7"),
    code("Build proposal", [5 * X, Y], BUILD_PROPOSAL),
    openrouter("OpenRouter plan", [6 * X, Y]),
    code("Apply proposal", [7 * X, Y], APPLY_PROPOSAL),
    bool_if("Proposal ok?", [8 * X, Y], "={{ $json.ok }}"),
    tg_send("Send proposal", [9 * X, Y - 60], rows=PLAN_ROWS),
    tg_send("Send proposal error", [9 * X, Y + 60]),

    http("Tandoor recipes (ed)", [8 * X, 1760], f"{TANDOOR}/recipe/?page_size=200", CRED_TANDOOR, once=True, always=True),
    code("Week recipe ids", [9 * X, 1760], WEEK_RECIPE_IDS),
    http("Week recipes (ed)", [10 * X, 1760],
         f"={{{{ $json.noop ? '{TANDOOR}/meal-type/' : '{TANDOOR}/recipe/' + $json.id + '/' }}}}", CRED_TANDOOR,
         on_error="continueRegularOutput"),
    code("Build edit", [11 * X, 1760], BUILD_EDIT),
    openrouter("OpenRouter edit", [12 * X, 1760]),
    code("Apply edit", [13 * X, 1760], APPLY_EDIT),
    switch("Edit route", [14 * X, 1760], "route", ["sync", "send_buttons", "send"]),
    tg_send("Send edited proposal", [15 * X, 1700], rows=PLAN_ROWS),
    tg_send("Send plan msg", [15 * X, 1820]),

    http("Tandoor meal types", [8 * X, 2300], f"{TANDOOR}/meal-type/?page_size=50", CRED_TANDOOR, once=True, always=True),
    code("Plan ops", [9 * X, 2300], PLAN_OPS),
    tandoor_ops("Tandoor ops", [10 * X, 2300]),
    code("Plan synced", [11 * X, 2300], PLAN_SYNCED),
    http("Tandoor shopping (sub)", [12 * X, 2300], f"{TANDOOR}/shopping-list-entry/?page_size=500", CRED_TANDOOR,
         once=True, always=True),
    code("Sub ops", [13 * X, 2300], SUB_OPS),
    tandoor_ops("Tandoor sub ops", [14 * X, 2300]),
    http("Tandoor shopping (pl)", [15 * X, 2300], f"{TANDOOR}/shopping-list-entry/?page_size=500", CRED_TANDOOR,
         once=True, always=True),
    code("Plan list msg", [16 * X, 2300], PLAN_LIST_MSG),
    tg_send("Send plan list", [17 * X, 2300]),

    code("Guide entry", [2 * X, Y + 300], GUIDE_ENTRY),
    http("Week recipes (gd)", [3 * X, Y + 300],
         f"={{{{ $json.skip ? '{TANDOOR}/meal-type/' : '{TANDOOR}/recipe/' + $json.id + '/' }}}}", CRED_TANDOOR,
         on_error="continueRegularOutput"),
    bool_if("Guide ready?", [2 * X + 130, Y + 300], "={{ !$json.skip }}"),
    tg_send("Send guide note", [3 * X, Y + 420]),
    code("Build guide", [4 * X, Y + 300], BUILD_GUIDE),
    openrouter("OpenRouter guide", [5 * X, Y + 300]),
    code("Session plan", [6 * X, Y + 300], SESSION_PLAN),
    tandoor_ops("Delete old session", [7 * X, Y + 360]),
    http("Save session", [8 * X, Y + 360], f"{TANDOOR}/recipe/", CRED_TANDOOR, method="POST",
         body="={{ JSON.stringify($('Session plan').first().json.body) }}", on_error="continueRegularOutput"),
    code("Guide msg", [9 * X, Y + 300], GUIDE_MSG),
    tg_send("Send guide", [7 * X, Y + 300]),

    http("Import parse", [5 * X, 1300], f"{TANDOOR}/recipe-from-source/", CRED_TANDOOR, method="POST",
         body="={{ JSON.stringify({ url: $json.url }) }}", on_error="continueRegularOutput"),
    code("Import build", [6 * X, 1300], IMPORT_BUILD),
    code("Save wish", [8 * X, 1560], plan_js(r"""
const i = $('Parse intent').first().json;
const sd = $getWorkflowStaticData('global');
const text = String(i.plan_request || $('Classify').first().json.text || '').trim();
sd.wishes = [...(sd.wishes || []), { text, at: Date.now() }].slice(-10);
const list = sd.wishes.map(w => `• ${w.text}`).join('\n');
return [{ json: { chat_id: i.chat_id, text: `📝 Apuntado para la próxima propuesta (viernes 9:00):\n${list}\n\nSi la quieres ya, escribe /propuesta.` } }];
""").strip()),
    tg_send("Send wish", [9 * X, 1560]),
    bool_if("Import ok?", [7 * X, 1300], "={{ $json.ok }}"),
    http("Import save", [8 * X, 1260], f"{TANDOOR}/recipe/", CRED_TANDOOR, method="POST",
         body="={{ JSON.stringify($json.body) }}", on_error="continueRegularOutput"),
    code("Import done", [9 * X, 1260], IMPORT_DONE),
    tg_send("Send import", [10 * X, 1260]),
    tg_send("Send import error", [8 * X, 1360]),
]

TANDOOR_UNITS = ["g", "kg", "ml", "l", "piezas", "c/sopera", "c/café", "Pizca", "lata", "taza", ""]
RECIPE_TAGS = ["fogón", "air fryer", "arrocera", "horno", "congelable", "rápida", "temporada-otoño",
               "temporada-invierno", "temporada-primavera", "temporada-verano"]
NEW_RECIPE_SCHEMA = {
    "name": "new_recipe",
    "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False,
        "required": ["ok", "name", "kind", "servings", "cuisine", "tags", "working", "waiting", "description",
                     "ingredients", "steps"],
        "properties": {
            "ok": {"type": "boolean"},
            "name": {"type": "string"},
            "kind": {"type": "string", "enum": ["comida-batch", "cena"]},
            "servings": {"type": "integer"},
            "cuisine": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string", "enum": RECIPE_TAGS}},
            "working": {"type": "integer"},
            "waiting": {"type": "integer"},
            "description": {"type": "string"},
            "ingredients": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["food", "amount", "unit", "note", "aisle"],
                "properties": {
                    "food": {"type": "string"},
                    "amount": {"type": "number"},
                    "unit": {"type": "string", "enum": TANDOOR_UNITS},
                    "note": {"type": "string"},
                    "aisle": {"type": "string", "enum": CATEGORIES},
                }}},
            "steps": {"type": "string"},
        },
    },
}

NEW_RECIPE_PROMPT = HOUSEHOLD + """
Write ONE reliable recipe for the dish the user asks for, in Spanish, faithful to how the dish is really made, adapted to their kitchen
(burners, air fryer, rice cooker; oven only if essential).
- kind: "comida-batch" (servings 4) for stews, legumes, rice or curries meant to be cooked on Sunday and eaten over 2 days;
  "cena" (servings 2) for quick dinners. If the user says "para cenar"/"cena" or "batch"/"comida", follow that.
- ingredients: amounts for the given servings; food = the exact name from known_foods when an equivalent exists
  (e.g. "Tomate Triturado en Lata", "Huevo (Grande)", "Aceite de Oliva"); otherwise a short generic Spanish name
  available in __LOCALE_HINT__. unit only from the allowed list ("" when no unit). aisle = supermarket aisle.
- steps: 4-8 numbered lines ("1. ...\\n2. ..."), say which device (fogón grande/mediano/pequeño, air fryer, arrocera);
  for batch recipes end with how to store it (fridge/freezer).
- tags: devices used, "congelable" if it freezes well, "rápida" if <= 30 min total, a season tag if it is clearly seasonal.
- If the message is not a dish or recipe request, set ok=false and leave the rest minimal."""

BUILD_NEW_RECIPE = plan_js(r"""
const i = $('Parse intent').first().json;
const foods = $('Tandoor foods (nr)').all().flatMap(x => x.json.results || []).map(f => f.name);
const msg = i.plan_request || $('Classify').first().json.text || '';
return [{ json: { request: {
  model: __MODEL__, temperature: 0.4,
  messages: [{ role: 'system', content: __PROMPT__ },
             { role: 'user', content: JSON.stringify({ request: msg, known_foods: foods }) }],
  response_format: { type: 'json_schema', json_schema: __SCHEMA__ },
} } }];
""").replace("__MODEL__", json.dumps(MODEL)).replace("__PROMPT__", json.dumps(NEW_RECIPE_PROMPT)).replace(
    "__SCHEMA__", json.dumps(NEW_RECIPE_SCHEMA, ensure_ascii=False))

RECIPE_PREVIEW = plan_js(r"""
const i = $('Parse intent').first().json;
const sd = $getWorkflowStaticData('global');
const existing = $('Tandoor recipes (nr)').all().flatMap(x => x.json.results || []);
const r = $input.first().json;
let p = null;
try { p = JSON.parse(r.choices[0].message.content); } catch (e) { p = null; }
const fail = text => [{ json: { ok: false, chat_id: i.chat_id, text } }];
if (!p || !p.ok || !p.name || !(p.ingredients || []).length) return fail('No he entendido qué receta quieres. Prueba con "añade la receta de bacalao a la llauna".');
const dup = existing.find(x => norm(x.name) === norm(p.name));
if (dup) return fail(`Ya tienes "${dup.name}" en Tandoor. Si quieres otra versión, dime en qué se diferencia.`);
let h = 5381;
for (const ch of `nr|${p.name}|${Date.now()}`) h = ((h << 5) + h + ch.charCodeAt(0)) >>> 0;
const key = h.toString(36);
sd.newRecipes = sd.newRecipes || {};
for (const [k, v] of Object.entries(sd.newRecipes)) if (Date.now() - v.created > 2 * 864e5) delete sd.newRecipes[k];
sd.newRecipes[key] = { ...p, created: Date.now() };
const label = p.kind === 'cena' ? 'cena' : 'comida de batch';
const ing = p.ingredients.map(g => `• ${g.amount ? `${num(g.amount)} ${g.unit} ` : ''}${g.food}${g.note ? ` (${g.note})` : ''}`.replace(/\s+/g, ' ')).join('\n');
const cost = r.usage && typeof r.usage.cost === 'number' ? `\nCoste: ${r.usage.cost.toFixed(4)} $` : '';
const text = `🧑‍🍳 ${p.name}\n${label} · ${p.servings} raciones · ~${(p.working || 0) + (p.waiting || 0)} min\n${p.description}\n\n🧾 Ingredientes\n${ing}\n\n🔥 Pasos\n${p.steps}${cost}`;
return [{ json: { ok: true, chat_id: i.chat_id, key, text: text.slice(0, 4000) } }];
""")

RECIPE_BODY = r"""
const rs = $('Resolve callback').first().json;
const p = $getWorkflowStaticData('global').newRecipes[rs.key];
const body = {
  name: p.name, description: p.description, servings: p.servings,
  working_time: p.working || 0, waiting_time: p.waiting || 0, internal: true,
  keywords: [...new Set([p.kind, ...(p.cuisine || []).map(c => String(c).toLowerCase()), ...(p.tags || []), 'generada'])].map(name => ({ name })),
  steps: [{ name: '', order: 0, instruction: p.steps, ingredients: p.ingredients.map((g, j) => ({
    food: { name: g.food }, unit: g.unit ? { name: g.unit } : null, amount: g.amount || 0, note: g.note || '', order: j })) }],
};
return [{ json: { chat_id: rs.chat_id, key: rs.key, body } }];
"""

RECIPE_AISLE_OPS = NORM_JS + r"""
const b = $('Recipe body').first().json;
const p = $getWorkflowStaticData('global').newRecipes[b.key];
const saved = $('Save recipe').first().json;
const cats = Object.fromEntries($('Tandoor categories (nr)').all().flatMap(x => x.json.results || []).map(c => [c.name, c]));
const aisleOf = Object.fromEntries(p.ingredients.map(g => [norm(g.food), g.aisle]));
const ops = [];
for (const st of saved.steps || []) for (const g of st.ingredients || []) {
  if (!g.food || g.food.supermarket_category) continue;
  const c = cats[aisleOf[norm(g.food.name)]];
  if (c) ops.push({ method: 'PATCH', path: `/food/${g.food.id}/`, body: { supermarket_category: { id: c.id, name: c.name } } });
}
if (!ops.length) ops.push({ method: 'GET', path: '/meal-type/', body: {} });
return ops.map(o => ({ json: o }));
"""

RECIPE_SAVED = r"""
const b = $('Recipe body').first().json;
const sd = $getWorkflowStaticData('global');
const p = sd.newRecipes[b.key];
const saved = $('Save recipe').first().json;
const newFoods = $('Recipe aisle ops').all().filter(x => x.json.method === 'PATCH').length;
let text;
if (saved && saved.id) {
  delete sd.newRecipes[b.key];
  text = `✅ Guardada en Tandoor: ${saved.name} (${saved.servings} raciones, ${p.kind === 'cena' ? 'cena' : 'comida de batch'}).`
    + (newFoods ? ` ${newFoods} ingredientes nuevos con su pasillo.` : '') + ' Ya puede salir en los menús.';
} else {
  text = `⚠ No he podido guardarla: ${(saved && saved.error && (saved.error.message || saved.error)) || 'error desconocido'}. Sigue pendiente; puedes volver a pulsar Guardar.`;
}
return [{ json: { chat_id: b.chat_id, text } }];
"""

NR_ROWS = [[btn("✅ Guardar", "=nr:ok:{{ $json.key }}"), btn("❌ Descartar", "=nr:no:{{ $json.key }}")]]
YR = 2700
foods_nr = http("Tandoor foods (nr)", [9 * X, YR], f"{TANDOOR}/food/?page_size=200", CRED_TANDOOR, once=True, always=True)
foods_nr["parameters"]["options"] = {"pagination": {"pagination": {
    "paginationMode": "responseContainsNextURL", "nextURL": "={{ $response.body.next }}",
    "paginationCompleteWhen": "other", "completeExpression": "={{ !$response.body.next }}",
    "limitPagesFetched": True, "maxRequests": 20}}}
nodes += [
    http("Tandoor recipes (nr)", [8 * X, YR], f"{TANDOOR}/recipe/?page_size=200", CRED_TANDOOR, once=True, always=True),
    foods_nr,
    code("Build new recipe", [10 * X, YR], BUILD_NEW_RECIPE),
    openrouter("OpenRouter recipe", [11 * X, YR]),
    code("Recipe preview", [12 * X, YR], RECIPE_PREVIEW),
    bool_if("Recipe ok?", [13 * X, YR], "={{ $json.ok }}"),
    tg_send("Send recipe preview", [14 * X, YR - 60], rows=NR_ROWS),
    tg_send("Send recipe error", [14 * X, YR + 60]),

    code("Recipe body", [6 * X, YR + 300], RECIPE_BODY),
    http("Save recipe", [7 * X, YR + 300], f"{TANDOOR}/recipe/", CRED_TANDOOR, method="POST",
         body="={{ JSON.stringify($json.body) }}", on_error="continueRegularOutput"),
    http("Tandoor categories (nr)", [8 * X, YR + 300], f"{TANDOOR}/supermarket-category/?page_size=200", CRED_TANDOOR,
         once=True, always=True),
    code("Recipe aisle ops", [9 * X, YR + 300], RECIPE_AISLE_OPS),
    tandoor_ops("Tandoor recipe ops", [10 * X, YR + 300]),
    code("Recipe saved", [11 * X, YR + 300], RECIPE_SAVED),
    tg_send("Send recipe saved", [12 * X, YR + 300]),
]
connections.update({
    "Tandoor recipes (nr)": {"main": link("Tandoor foods (nr)")},
    "Tandoor foods (nr)": {"main": link("Build new recipe")},
    "Build new recipe": {"main": link("OpenRouter recipe")},
    "OpenRouter recipe": {"main": link("Recipe preview")},
    "Recipe preview": {"main": link("Recipe ok?")},
    "Recipe ok?": {"main": outs(["Send recipe preview"], ["Send recipe error"])},
    "Recipe body": {"main": link("Save recipe")},
    "Save recipe": {"main": link("Tandoor categories (nr)")},
    "Tandoor categories (nr)": {"main": link("Recipe aisle ops")},
    "Recipe aisle ops": {"main": link("Tandoor recipe ops")},
    "Tandoor recipe ops": {"main": link("Recipe saved")},
    "Recipe saved": {"main": link("Send recipe saved")},
})


# ---------------------------------------------------------------- household automation (compra hecha, batch hecho, cenas)
CONSUME_JS = r"""
const STOPW = new Set(['de', 'del', 'la', 'el', 'los', 'las', 'en', 'con', 'y', 'al', 'lata', 'bote']);
const wordsOf = s => norm(s).split(' ').filter(w => w && !STOPW.has(w)).map(w => w.length > 3 ? w.replace(/(es|s)$/, '') : w);
const FORMW = new Set(['triturado', 'frito', 'concentrado', 'seco', 'molido', 'polvo', 'congelado', 'zumo', 'jugo', 'salsa', 'crema', 'caldo', 'pure', 'deshidratado', 'ahumado', 'tostado', 'cocido', 'encurtido', 'escabeche', 'desecado', 'rallado']);
// a processed form (crushed, canned, smoked, cooked...) on only one side means a different product
const formClash = (a, b) => a.some(w => FORMW.has(w) && !b.includes(w)) || b.some(w => FORMW.has(w) && !a.includes(w));
const simil = (food, product) => { const f = wordsOf(food), pl = wordsOf(product), pr = new Set(pl); if (formClash(f, pl)) return 0; return f.length ? f.filter(w => pr.has(w)).length / f.length : 0; };
const UG = { g: 1, gr: 1, kg: 1000 }, UM = { ml: 1, cl: 10, l: 1000 }, UP = ['', 'unidad', 'unidades', 'ud', 'uds', 'pieza', 'piezas'];
const conv = (a, f, t) => { f = norm(f); t = norm(t); if (f === t) return a; if (UG[f] && UG[t]) return a * UG[f] / UG[t];
  if (UM[f] && UM[t]) return a * UM[f] / UM[t]; if (UP.includes(f) && UP.includes(t)) return a; return null; };
// recipe ingredients scaled to `servings`, matched against Grocy stock -> consume list + skipped
const planConsumption = (recipe, servings, stock, unitName) => {
  const byFood = new Map(), byName = new Map();
  for (const s of stock) { const uf = (s.product && s.product.userfields) || {};
    if (uf.tandoor_food_id) byFood.set(String(uf.tandoor_food_id), s); byName.set(norm(s.product.name), s); }
  const factor = servings / (recipe.servings || servings || 1);
  const consume = [], skipped = [];
  for (const st of recipe.steps || []) for (const ing of st.ingredients || []) {
    if (ing.is_header || !ing.food || ing.food.ignore_shopping) continue;
    const s = byFood.get(String(ing.food.id)) || byName.get(norm(ing.food.name))
      || stock.filter(x => simil(ing.food.name, x.product.name) === 1).sort((a, b) => wordsOf(a.product.name).length - wordsOf(b.product.name).length)[0];
    if (!s || !ing.amount) { skipped.push(ing.food.name); continue; }
    const su = unitName(s.product.qu_id_stock);
    const amount = conv(ing.amount * factor, ing.unit ? ing.unit.name : '', su);
    if (amount === null) { skipped.push(ing.food.name); continue; }
    const take = Math.round(Math.min(amount, Number(s.amount)) * 1000) / 1000;
    if (take > 0) consume.push({ product_id: s.product_id, name: s.product.name, amount: take, unit: su });
  }
  return { consume, skipped };
};
"""


def hh_js(body):
    return plan_js(CONSUME_JS + body)


def grocy_ops(name, pos):
    # fullResponse keeps one output item per operation (Grocy answers stock writes with a JSON array)
    n = http(name, pos, f"={{{{ '{GROCY}' + $json.path }}}}", CRED_GROCY, method="={{ $json.method }}",
             body="={{ JSON.stringify($json.body || {}) }}", on_error="continueRegularOutput")
    n["parameters"]["options"]["response"] = {"response": {"fullResponse": True}}
    return n


CHECKOFF_OPS = NORM_JS + CONSUME_JS + r"""
const writes = $('Build writes').all().map(i => i.json);
const names = writes.map(w => w.label);
const entries = ($('Tandoor shopping (tk)').first().json.results || []).filter(e => !e.checked && e.food);
const ops = entries.filter(e => names.some(n => norm(n) === norm(e.food.name) || simil(e.food.name, n) === 1))
  .map(e => ({ method: 'PATCH', path: `/shopping-list-entry/${e.id}/`, body: { checked: true } }));
if (!ops.length) ops.push({ method: 'GET', path: '/meal-type/', body: {} });
return ops.map(o => ({ json: o }));
"""

SAVED_MSG = r"""
const s = $('Summary').first().json;
const n = $('Checkoff ops').all().filter(x => x.json.method === 'PATCH').length;
return [{ json: { chat_id: s.chat_id, text: s.text + (n ? `\n🛒 Tachados ${n} productos de la lista de la compra.` : '') } }];
"""

PURCHASE_PLAN = hh_js(r"""
const i = $('Parse intent').first().json;
const entries = ($('Tandoor shopping (pd)').first().json.results || []).filter(e => !e.checked && e.food);
const products = $('Grocy products (pd)').all().map(x => x.json).filter(x => x && x.id);
const qu = Object.fromEntries($('Grocy units (pd)').all().map(x => [x.json.name, x.json.id]));
const quName = Object.fromEntries($('Grocy units (pd)').all().map(x => [x.json.id, x.json.name]));
const loc = Object.fromEntries($('Grocy locations (pd)').all().map(x => [x.json.name, x.json.id]));
const grp = Object.fromEntries($('Grocy groups (pd)').all().map(x => [x.json.name, x.json.id]));
const matches = (list, e) => list.some(x => norm(e.food.name).includes(x) || x.includes(norm(e.food.name)) || simil(x, e.food.name) === 1);
const except = (i.except_items || []).map(norm).filter(Boolean);
const only = (i.only_items || []).map(norm).filter(Boolean);
const home = homeIndex($('Grocy stock (pd)').all().map(x => x.json), Object.fromEntries($('Grocy units (pd)').all().map(x => [x.json.id, x.json])));
const skipped = entries.filter(e => matches(except, e) || (only.length && !matches(only, e)));
const atHome = only.length ? [] : entries.filter(e => !skipped.includes(e) && (home(e.food, e.amount, e.unit ? e.unit.name : '') || {}).covered);
const bought = entries.filter(e => !skipped.includes(e) && !atHome.includes(e));
const FRIDGE = ['Carne', 'Pescados y Mariscos', 'Lácteos', 'Queso', 'Deli'];
const PANTRY_PRODUCE = /patata|cebolla|ajo|boniato|batata|platano|naranja|limon|lima|manzana|calabaza|granada|castana|pera/;
const BB = { 'Carne': 3, 'Pescados y Mariscos': 2, 'Frutas y Verduras': 7, 'Lácteos': 10, 'Queso': 21, 'Deli': 7, 'Panadería': 3, 'Congelados': 180 };
const groups = new Map();
for (const e of bought) {
  const k = `${e.food.id}|${e.unit ? e.unit.name : ''}`;
  const g = groups.get(k) || { food: e.food, unit: e.unit ? e.unit.name : '', amount: 0, entry_ids: [] };
  g.amount += Number(e.amount || 0); g.entry_ids.push(e.id); groups.set(k, g);
}
const out = [];
for (const g of groups.values()) {
  const cat = (g.food.supermarket_category && g.food.supermarket_category.name) || '';
  const p = products.find(x => Number((x.userfields || {}).tandoor_food_id) === g.food.id)
    || products.find(x => norm(x.name) === norm(g.food.name))
    || products.filter(x => simil(g.food.name, x.name) === 1).sort((a, b) => wordsOf(a.name).length - wordsOf(b.name).length)[0];
  const tu = norm(g.unit);
  const newQu = UG[tu] ? 'kg' : UM[tu] ? 'l' : tu === 'lata' ? 'Lata' : 'Unidad';
  const stockQu = p ? quName[p.qu_id_stock] : newQu;
  let amount = conv(g.amount, g.unit, stockQu);
  if (amount === null || !(amount > 0)) amount = 1;
  const location = cat === 'Congelados' ? 'Congelador' : (FRIDGE.includes(cat) || (cat === 'Frutas y Verduras' && !PANTRY_PRODUCE.test(norm(g.food.name)))) ? 'Nevera' : 'Despensa';
  const days = p && p.default_best_before_days > 0 ? p.default_best_before_days : (BB[cat] || 365);
  out.push({ json: {
    product_id: p ? p.id : null, label: p ? p.name : g.food.name, food_id: g.food.id, entry_ids: g.entry_ids,
    create_body: { name: g.food.name, location_id: loc[location] || loc['Despensa'], product_group_id: grp[cat] || null,
      qu_id_purchase: qu[newQu], qu_id_stock: qu[newQu], qu_id_consume: qu[newQu], qu_id_price: qu[newQu],
      default_best_before_days: BB[cat] || -1 },
    stock_body: { amount: Math.round(amount * 1000) / 1000, transaction_type: 'purchase',
      best_before_date: new Date(Date.now() + days * 864e5).toISOString().slice(0, 10) },
    unit_label: stockQu, skipped: skipped.map(e => e.food.name), at_home: atHome.map(e => e.food.name), at_home_ids: atHome.map(e => e.id),
  } });
}
if (!out.length) return [{ json: { empty: true, chat_id: i.chat_id, skipped: skipped.map(e => e.food.name), at_home: atHome.map(e => e.food.name), at_home_ids: atHome.map(e => e.id) } }];
return out;
""")

PURCHASE_OPS = r"""
const items = $('Purchase plan').all().map(x => x.json);
const ensured = $input.all().map(x => x.json);
const ops = [];
items.forEach((it, idx) => {
  if (it.empty) return;
  const pid = it.product_id || (ensured[idx] && (ensured[idx].created_object_id || ensured[idx].id));
  if (!pid) return;
  ops.push({ kind: 'add', label: it.label, product_id: pid, method: 'POST', path: `/stock/products/${pid}/add`, body: it.stock_body });
  if (!it.product_id) ops.push({ kind: 'link', method: 'PUT', path: `/userfields/products/${pid}`, body: { tandoor_food_id: it.food_id } });
});
if (!ops.length) ops.push({ kind: 'noop', method: 'GET', path: '/system/info', body: {} });
return ops.map(o => ({ json: o }));
"""

PURCHASE_CHECKOFF = r"""
const all = $('Purchase plan').all().map(x => x.json);
const items = all.filter(x => !x.empty);
const ids = [...items.flatMap(it => it.entry_ids), ...((all[0] && all[0].at_home_ids) || [])];
const ops = [...new Set(ids)].map(id => ({ method: 'PATCH', path: `/shopping-list-entry/${id}/`, body: { checked: true } }));
if (!ops.length) ops.push({ method: 'GET', path: '/meal-type/', body: {} });
return ops.map(o => ({ json: o }));
"""

PURCHASE_DONE = NORM_JS + r"""
const i = $('Parse intent').first().json;
const sd = $getWorkflowStaticData('global');
const plan = $('Purchase plan').all().map(x => x.json);
if (plan.length === 1 && plan[0].empty) {
  const sk = plan[0].skipped || [], ah = [...new Set(plan[0].at_home || [])];
  const parts = [];
  if (ah.length) parts.push(`ya había en casa: ${ah.join(', ')} (los tacho de la lista)`);
  if (sk.length) parts.push(`no comprados: ${sk.join(', ')}`);
  return [{ json: { chat_id: i.chat_id, text: parts.length ? `No he sumado nada a la despensa — ${parts.join('; ')}.` : '🛒 La lista de la compra ya estaba vacía: no hay nada que pasar a la despensa.' } }];
}
const okRes = r => !!r && !r.error && Number(r.statusCode || 200) < 300;
const ops = $('Purchase ops').all().map(x => x.json);
const res = $('Grocy ops (pd)').all().map(x => x.json);
const added = [], failed = [];
ops.forEach((o, idx) => { if (o.kind !== 'add') return; (okRes(res[idx]) ? added : failed).push(o); });
sd.bulk = { at: Date.now(), product_ids: added.map(o => o.product_id) };
const lines = added.map(o => { const it = plan.find(p => p.label === o.label); return `• ${o.label} ${num(o.body.amount)} ${it ? it.unit_label : ''}`.trim(); });
let text = `✅ Compra pasada a la despensa (${added.length} productos):\n${lines.join('\n')}`;
const skipped = (plan[0] && plan[0].skipped) || [];
if (skipped.length) text += `\n\n⏭ Sin comprar (siguen en la lista): ${skipped.join(', ')}`;
const atHome = [...new Set((plan[0] && plan[0].at_home) || [])];
if (atHome.length) text += `\n\n✔️ No sumados porque ya había en casa: ${atHome.join(', ')}. Si los comprasteis igualmente: "compré también ${atHome[0].toLowerCase()}".`;
if (failed.length) text += `\n⚠ No pude guardar: ${failed.map(f => f.label).join(', ')}`;
text += '\nSin precios: si tenéis el ticket, mandadlo y solo actualizo lo que falte.';
return [{ json: { chat_id: i.chat_id, text: text.slice(0, 4000) } }];
"""

BATCH_ENTRY = plan_js(r"""
const w = $getWorkflowStaticData('global').week;
return w.slots.filter(s => s.meal === 'comida').map(s => ({ json: { id: s.recipe_id, slot: s.slot } }));
""")

BATCH_PLAN = hh_js(r"""
const sd = $getWorkflowStaticData('global');
const w = sd.week;
const recipes = $('Tandoor batch recipes').all().map(x => x.json).filter(r => r && r.id);
const stock = $('Grocy stock (bt)').all().map(x => x.json).filter(x => x && x.product_id);
const products = $('Grocy products (bt)').all().map(x => x.json).filter(x => x && x.id);
const quName = Object.fromEntries($('Grocy units (bt)').all().map(x => [x.json.id, x.json.name]));
const qu = Object.fromEntries($('Grocy units (bt)').all().map(x => [x.json.name, x.json.id]));
const loc = Object.fromEntries($('Grocy locations (bt)').all().map(x => [x.json.name, x.json.id]));
const consume = [], skipped = [], portions = [];
const offset = d => DAYS.indexOf(d) + 1;
for (const s of w.slots.filter(x => x.meal === 'comida')) {
  const r = recipes.find(x => x.id === s.recipe_id);
  if (!r) continue;
  const c = planConsumption(r, s.days.length * 2, stock, id => quName[id] || '');
  consume.push(...c.consume); skipped.push(...c.skipped);
  const fridge = s.days.filter(d => offset(d) <= 3).length * 2, freezer = s.days.filter(d => offset(d) > 3).length * 2;
  const name = `${r.name} (ración)`;
  const existing = products.find(x => norm(x.name) === norm(name));
  portions.push({ name, product_id: existing ? existing.id : null, fridge, freezer });
}
sd.batchRun = { consume, skipped: [...new Set(skipped)], portions };
return portions.map(p => ({ json: { product_id: p.product_id, create_body: {
  name: p.name, location_id: loc['Nevera'], qu_id_purchase: qu['Unidad'], qu_id_stock: qu['Unidad'], qu_id_consume: qu['Unidad'],
  qu_id_price: qu['Unidad'], default_best_before_days: 4, default_best_before_days_after_freezing: 90, product_group_id: null } } }));
""")

BATCH_OPS = r"""
const run = $getWorkflowStaticData('global').batchRun;
const ensured = $input.all().map(x => x.json);
const loc = Object.fromEntries($('Grocy locations (bt)').all().map(x => [x.json.name, x.json.id]));
const day = n => new Date(Date.now() + n * 864e5).toISOString().slice(0, 10);
const ops = run.consume.map(c => ({ kind: 'consume', label: c.name, method: 'POST', path: `/stock/products/${c.product_id}/consume`,
  body: { amount: c.amount, transaction_type: 'consume', spoiled: false } }));
run.portions.forEach((p, idx) => {
  const pid = p.product_id || (ensured[idx] && (ensured[idx].created_object_id || ensured[idx].id));
  if (!pid) return;
  if (p.fridge) ops.push({ kind: 'portion', label: `${p.name} ×${p.fridge} nevera`, method: 'POST', path: `/stock/products/${pid}/add`,
    body: { amount: p.fridge, transaction_type: 'self-production', best_before_date: day(4), location_id: loc['Nevera'] } });
  if (p.freezer) ops.push({ kind: 'portion', label: `${p.name} ×${p.freezer} congelador`, method: 'POST', path: `/stock/products/${pid}/add`,
    body: { amount: p.freezer, transaction_type: 'self-production', best_before_date: day(90), location_id: loc['Congelador'] } });
});
if (!ops.length) ops.push({ kind: 'noop', method: 'GET', path: '/system/info', body: {} });
return ops.map(o => ({ json: o }));
"""

BATCH_DONE = r"""
const rs = $('Resolve callback').first().json;
const sd = $getWorkflowStaticData('global');
const ops = $('Batch ops').all().map(x => x.json);
const res = $('Grocy ops (bt)').all().map(x => x.json);
const okRes = r => !!r && !r.error && Number(r.statusCode || 200) < 300;
const ok = k => ops.filter((o, i) => o.kind === k && okRes(res[i]));
const bad = ops.filter((o, i) => o.kind !== 'noop' && !okRes(res[i]));
sd.week.batch_done = true;
let text = `✅ Batch registrado: descontados ${ok('consume').length} ingredientes.\n🥡 ${ok('portion').map(o => o.label).join('\n🥡 ')}`;
if (sd.batchRun.skipped.length) text += `\n\nNo descontados (no están en la despensa o la unidad no encaja, p. ej. cucharadas vs unidades): ${sd.batchRun.skipped.join(', ')}`;
if (bad.length) text += `\n⚠ Fallaron: ${bad.map(o => o.label).join(', ')}`;
return [{ json: { chat_id: rs.chat_id, text: text.slice(0, 4000) } }];
"""

DINNER_ENTRY = plan_js(r"""
const sd = $getWorkflowStaticData('global');
const w = sd.week;
const rp = $('Run planner').isExecuted ? ($('Run planner').first().json.body || {}) : {};
const today = rp.date || isoDay(new Date());
if (!w || w.status !== 'accepted' || !weekIsCurrent(w)) return [];
if ((sd.dinnerTx || {})[today]) return [];
const skipped = new Set([].concat((sd.skipDinner || {})[today] || []).map(x => (x === true ? 'cena' : x)));
const dk = rp.day || DAYS.find(d => dayDate(w.week_start, d) === today);
const slots = w.slots.filter(s => s.meal !== 'comida' && s.days.includes(dk) && !skipped.has(s.meal) && !skipped.has('todo'));
return slots.map(s => ({ json: { id: s.recipe_id, name: s.recipe_name, meal: s.meal, date: today } }));
""")

DINNER_OPS = hh_js(r"""
const entry = $('Dinner entry').all().map(x => x.json);
const recipes = $('Tandoor dinner recipe').all().map(x => x.json);
const stock = $('Grocy stock (dn)').all().map(x => x.json).filter(x => x && x.product_id);
const quName = Object.fromEntries($('Grocy units (dn)').all().map(x => [x.json.id, x.json.name]));
const ops = [];
entry.forEach((en, idx) => {
  const r = recipes[idx];
  if (!r || !r.id) return;
  const c = planConsumption(r, en.meal === 'cena' ? 2 : 1, stock, id => quName[id] || '');
  for (const x of c.consume) ops.push({ kind: 'consume', meal: en.meal, recipe: r.name, label: x.name, method: 'POST', path: `/stock/products/${x.product_id}/consume`,
    body: { amount: x.amount, transaction_type: 'consume', spoiled: false } });
});
if (!ops.length) ops.push({ kind: 'noop', method: 'GET', path: '/system/info', body: {} });
return ops.map(o => ({ json: o }));
""")

DINNER_DONE = plan_js(r"""
const sd = $getWorkflowStaticData('global');
const entry = $('Dinner entry').all().map(x => x.json);
const ops = $('Dinner ops').all().map(x => x.json);
const res = $('Grocy ops (dn)').all().map(x => x.json);
const tx = {};
res.forEach((r, i) => {
  if (!ops[i] || ops[i].kind !== 'consume' || !r || r.error) return;
  for (const row of [].concat(r.body || [])) if (row && row.transaction_id) (tx[ops[i].meal] ||= []).push(row.transaction_id);
});
const date = entry[0].date;
const weekAgo = isoDay(new Date(Date.now() - 7 * 864e5));
sd.dinnerTx = Object.fromEntries(Object.entries(sd.dinnerTx || {}).filter(([d]) => d >= weekAgo));
sd.dinnerTx[date] = tx;
const okOps = ops.filter((o, i) => o.kind === 'consume' && res[i] && !res[i].error);
const label = { cena: 'cena', desayuno: 'desayuno de __PERSONAL_NAME__', merienda: 'merienda de __PERSONAL_NAME__' };
const parts = entry.map(e => `${label[e.meal] || e.meal}: ${e.name} (${okOps.filter(o => o.meal === e.meal).length} ingr.)`);
const text = okOps.length
  ? `🌙 Descontado de hoy — ${parts.join('; ')}. Si algo no se hizo: "hoy no hicimos la cena", "hoy no desayuné lo del menú" o "no merendé", y lo devuelvo.`
  : `🌙 Hoy (${entry.map(e => e.name).join(', ')}): no había ingredientes registrados en la despensa que descontar.`;
return RECIPIENTS.map(chat_id => ({ json: { chat_id, text } }));
""")

SKIP_DINNER = plan_js(r"""
const i = $('Parse intent').first().json;
const sd = $getWorkflowStaticData('global');
const date = isoDay(new Date(Date.now() - (i.day_ref === 'yesterday' ? 864e5 : 0)));
const meal = i.meal_ref || 'cena';
const meals = meal === 'todo' ? ['cena', 'desayuno', 'merienda'] : [meal];
let rec = (sd.dinnerTx || {})[date];
if (Array.isArray(rec)) rec = { cena: rec };
sd.skipDinner = sd.skipDinner || {};
const prev = [].concat(sd.skipDinner[date] || []).map(x => (x === true ? 'cena' : x));
sd.skipDinner[date] = [...new Set([...prev, ...meals])];
const tx = rec ? meals.flatMap(m => rec[m] || []) : [];
if (rec) { for (const m of meals) delete rec[m]; sd.dinnerTx[date] = rec; }
if (tx.length) return tx.map(t => ({ json: { chat_id: i.chat_id, undo: true, meal, method: 'POST', path: `/stock/transactions/${t}/undo`, body: {} } }));
return [{ json: { chat_id: i.chat_id, undo: false, meal, method: 'GET', path: '/system/info', body: {} } }];
""")

SKIP_DONE = r"""
const items = $('Skip dinner').all().map(x => x.json);
const res = $input.all().map(x => x.json);
const undone = items.filter((it, i) => it.undo && res[i] && !res[i].error && Number(res[i].statusCode || 200) < 300).length;
const what = { cena: 'la cena', desayuno: 'el desayuno', merienda: 'la merienda', todo: 'las comidas del día' }[items[0].meal] || 'la cena';
const text = items[0].undo
  ? `↩️ Hecho: devuelvo a la despensa los ${undone} ingredientes de ${what}.`
  : `👍 Vale, hoy no descuento ${what} del menú.`;
return [{ json: { chat_id: items[0].chat_id, text } }];
"""

BT_ROWS = [[btn("✅ Batch hecho", "=bt:ok:{{ $json.week_start }}")]]
YH = 3300
nodes += [
    bool_if("Guide button?", [7 * X, Y + 300], "={{ $json.button }}"),
    tg_send("Send batch button", [8 * X, Y + 240], rows=BT_ROWS),

    http("Tandoor shopping (tk)", [18 * X, 380], f"{TANDOOR}/shopping-list-entry/?page_size=500", CRED_TANDOOR, once=True, always=True),
    code("Checkoff ops", [19 * X, 380], CHECKOFF_OPS),
    tandoor_ops("Tandoor ops (tk)", [20 * X, 380]),
    code("Saved msg", [21 * X, 380], SAVED_MSG),

    http("Tandoor shopping (pd)", [8 * X, YH], f"{TANDOOR}/shopping-list-entry/?page_size=500", CRED_TANDOOR, once=True, always=True),
    grocy_get("Grocy products (pd)", [9 * X, YH], "objects/products"),
    grocy_get("Grocy units (pd)", [10 * X, YH], "objects/quantity_units"),
    grocy_get("Grocy locations (pd)", [11 * X, YH], "objects/locations"),
    grocy_get("Grocy groups (pd)", [12 * X, YH], "objects/product_groups"),
    code("Purchase plan", [13 * X, YH], PURCHASE_PLAN),
    http("Ensure product (pd)", [14 * X, YH],
         f"={{{{ $json.empty ? '{NOOP}' : ($json.product_id ? '{GROCY}/objects/products/' + $json.product_id : '{GROCY}/objects/products') }}}}",
         CRED_GROCY, method="={{ !$json.empty && !$json.product_id ? 'POST' : 'GET' }}",
         body="={{ JSON.stringify($json.create_body || {}) }}", on_error="continueRegularOutput"),
    code("Purchase ops", [15 * X, YH], PURCHASE_OPS),
    grocy_ops("Grocy ops (pd)", [16 * X, YH]),
    code("Purchase checkoff", [17 * X, YH], PURCHASE_CHECKOFF),
    tandoor_ops("Tandoor ops (pd)", [18 * X, YH]),
    code("Purchase done", [19 * X, YH], PURCHASE_DONE),
    tg_send("Send purchase", [20 * X, YH]),

    grocy_get("Grocy stock (pd)", [8 * X, YH + 120], "stock"),
    grocy_get("Grocy stock (list)", [15 * X, 2440], "stock"),
    grocy_get("Grocy units (list)", [16 * X, 2440], "objects/quantity_units"),
    grocy_get("Grocy stock (sh)", [9 * X, 1560], "stock"),
    grocy_get("Grocy units (sh)", [10 * X, 1560], "objects/quantity_units"),
    code("Batch entry", [6 * X, YH + 300], BATCH_ENTRY),
    http("Tandoor batch recipes", [7 * X, YH + 300], f"={{{{ '{TANDOOR}/recipe/' + $json.id + '/' }}}}", CRED_TANDOOR,
         on_error="continueRegularOutput"),
    grocy_get("Grocy stock (bt)", [8 * X, YH + 300], "stock"),
    grocy_get("Grocy products (bt)", [9 * X, YH + 300], "objects/products"),
    grocy_get("Grocy units (bt)", [10 * X, YH + 300], "objects/quantity_units"),
    grocy_get("Grocy locations (bt)", [11 * X, YH + 300], "objects/locations"),
    code("Batch plan", [12 * X, YH + 300], BATCH_PLAN),
    http("Ensure batch portion", [13 * X, YH + 300],
         f"={{{{ $json.product_id ? '{GROCY}/objects/products/' + $json.product_id : '{GROCY}/objects/products' }}}}",
         CRED_GROCY, method="={{ $json.product_id ? 'GET' : 'POST' }}", body="={{ JSON.stringify($json.create_body) }}",
         on_error="continueRegularOutput"),
    code("Batch ops", [14 * X, YH + 300], BATCH_OPS),
    grocy_ops("Grocy ops (bt)", [15 * X, YH + 300]),
    code("Batch done", [16 * X, YH + 300], BATCH_DONE),
    tg_send("Send batch done", [17 * X, YH + 300]),

    sched("Daily 23:30", [0, YH + 600], {"field": "days", "daysInterval": 1, "triggerAtHour": 23, "triggerAtMinute": 30}),
    code("Dinner entry", [X, YH + 600], DINNER_ENTRY),
    http("Tandoor dinner recipe", [2 * X, YH + 600], f"={{{{ '{TANDOOR}/recipe/' + $json.id + '/' }}}}", CRED_TANDOOR,
         on_error="continueRegularOutput"),
    grocy_get("Grocy stock (dn)", [3 * X, YH + 600], "stock"),
    grocy_get("Grocy units (dn)", [4 * X, YH + 600], "objects/quantity_units"),
    code("Dinner ops", [5 * X, YH + 600], DINNER_OPS),
    grocy_ops("Grocy ops (dn)", [6 * X, YH + 600]),
    code("Dinner done", [7 * X, YH + 600], DINNER_DONE),
    tg_send("Send dinner done", [8 * X, YH + 600]),

    code("Skip dinner", [8 * X, YH + 900], SKIP_DINNER),
    grocy_ops("Grocy ops (sk)", [9 * X, YH + 900]),
    code("Skip done", [10 * X, YH + 900], SKIP_DONE),
    tg_send("Send skip", [11 * X, YH + 900]),
]
connections.update({
    "Tandoor shopping (pd)": {"main": link("Grocy stock (pd)")},
    "Grocy stock (pd)": {"main": link("Grocy products (pd)")},
    "Grocy products (pd)": {"main": link("Grocy units (pd)")},
    "Grocy units (pd)": {"main": link("Grocy locations (pd)")},
    "Grocy locations (pd)": {"main": link("Grocy groups (pd)")},
    "Grocy groups (pd)": {"main": link("Purchase plan")},
    "Purchase plan": {"main": link("Ensure product (pd)")},
    "Ensure product (pd)": {"main": link("Purchase ops")},
    "Purchase ops": {"main": link("Grocy ops (pd)")},
    "Grocy ops (pd)": {"main": link("Purchase checkoff")},
    "Purchase checkoff": {"main": link("Tandoor ops (pd)")},
    "Tandoor ops (pd)": {"main": link("Purchase done")},
    "Purchase done": {"main": link("Send purchase")},
    "Batch entry": {"main": link("Tandoor batch recipes")},
    "Tandoor batch recipes": {"main": link("Grocy stock (bt)")},
    "Grocy stock (bt)": {"main": link("Grocy products (bt)")},
    "Grocy products (bt)": {"main": link("Grocy units (bt)")},
    "Grocy units (bt)": {"main": link("Grocy locations (bt)")},
    "Grocy locations (bt)": {"main": link("Batch plan")},
    "Batch plan": {"main": link("Ensure batch portion")},
    "Ensure batch portion": {"main": link("Batch ops")},
    "Batch ops": {"main": link("Grocy ops (bt)")},
    "Grocy ops (bt)": {"main": link("Batch done")},
    "Batch done": {"main": link("Send batch done")},
    "Daily 23:30": {"main": link("Dinner entry")},
    "Dinner entry": {"main": link("Tandoor dinner recipe")},
    "Tandoor dinner recipe": {"main": link("Grocy stock (dn)")},
    "Grocy stock (dn)": {"main": link("Grocy units (dn)")},
    "Grocy units (dn)": {"main": link("Dinner ops")},
    "Dinner ops": {"main": link("Grocy ops (dn)")},
    "Grocy ops (dn)": {"main": link("Dinner done")},
    "Dinner done": {"main": link("Send dinner done")},
    "Skip dinner": {"main": link("Grocy ops (sk)")},
    "Grocy ops (sk)": {"main": link("Skip done")},
    "Skip done": {"main": link("Send skip")},
})


for n in nodes:
    if n["name"] == "Callback mode":
        n.update(switch("Callback mode", n["position"], "mode", ["save", "cook", "reply", "plan_accept", "plan_new", "recipe_save", "batch_done"])
                 | {"id": n["id"]})
    if n["name"] == "Intent":
        n.update(switch("Intent", n["position"], "intent",
                        ["correction", "cooked", "ate", "stock", "shopping", "plan", "wish", "new_recipe", "purchase_done", "skip_dinner", "help"]) | {"id": n["id"]})
    if n["name"] == "Text mode":
        n.update(switch("Text mode", n["position"], "mode", ["help", "llm", "import", "propose", "guide"]) | {"id": n["id"]})
    if n["name"] == "Shopping reply":
        n["parameters"]["jsCode"] = plan_js(r"""
const chat = $('Parse intent').first().json.chat_id;
const entries = $('Tandoor shopping').all().flatMap(x => x.json.results || (x.json.id ? [x.json] : [])).filter(e => !e.checked);
if (!entries.length) return [{ json: { chat_id: chat, text: '🛒 La lista de la compra está vacía.' } }];
const home = homeIndex($('Grocy stock (sh)').all().map(x => x.json), Object.fromEntries($('Grocy units (sh)').all().map(x => [x.json.id, x.json])));
return [{ json: { chat_id: chat, text: `🛒 Lista de la compra (${countItems(entries)} productos)\n\n${groupList(entries, home)}`.slice(0, 4000) } }];
""").strip()

connections["Callback mode"] = {"main": outs(["Grocy locations"], ["Grocy locations (cook)"], ["Send callback reply"],
                                             ["Tandoor meal types"], ["Planner entry"], ["Recipe body"], ["Batch entry"])}
connections["Intent"] = {"main": outs(["Apply correction"], ["Tandoor search"], ["Grocy stock (ate)"], ["Grocy stock (st)"],
                                      ["Tandoor shopping"], ["Tandoor recipes (ed)"], ["Save wish"], ["Tandoor recipes (nr)"], ["Tandoor shopping (pd)"], ["Skip dinner"], ["Send intent help"])}
connections["Text mode"] = {"main": outs(["Send help"], ["OpenRouter intent"], ["Import parse"], ["Planner entry"], ["Guide entry"])}
connections.update({
    "Friday 09:00": {"main": link("Planner entry")},
    "Sunday 10:00": {"main": link("Guide entry")},
    "Run planner": {"main": link("Planner action")},
    "Planner action": {"main": outs(["Planner entry"], ["Guide entry"], ["Reset week"], ["Dinner entry"], ["Snapshot week"], ["Snapshot week"], ["Set week"])},
    "Reset week": {"main": link("Tandoor meal types")},
    "Planner entry": {"main": link("Should propose?")},
    "Should propose?": {"main": outs(["Tandoor recipes (pl)"], ["Send proposal note"])},
    "Tandoor recipes (pl)": {"main": link("Grocy volatile (pl)")},
    "Grocy volatile (pl)": {"main": link("Build proposal")},
    "Build proposal": {"main": link("OpenRouter plan")},
    "OpenRouter plan": {"main": link("Apply proposal")},
    "Apply proposal": {"main": link("Proposal ok?")},
    "Proposal ok?": {"main": outs(["Send proposal"], ["Send proposal error"])},
    "Tandoor recipes (ed)": {"main": link("Week recipe ids")},
    "Week recipe ids": {"main": link("Week recipes (ed)")},
    "Week recipes (ed)": {"main": link("Build edit")},
    "Build edit": {"main": link("OpenRouter edit")},
    "OpenRouter edit": {"main": link("Apply edit")},
    "Apply edit": {"main": link("Edit route")},
    "Edit route": {"main": outs(["Tandoor meal types"], ["Send edited proposal"], ["Send plan msg"])},
    "Tandoor meal types": {"main": link("Plan ops")},
    "Plan ops": {"main": link("Tandoor ops")},
    "Tandoor ops": {"main": link("Plan synced")},
    "Plan synced": {"main": link("Tandoor shopping (sub)")},
    "Tandoor shopping (sub)": {"main": link("Sub ops")},
    "Sub ops": {"main": link("Tandoor sub ops")},
    "Tandoor sub ops": {"main": link("Tandoor shopping (pl)")},
    "Tandoor shopping (pl)": {"main": link("Grocy stock (list)")},
    "Grocy stock (list)": {"main": link("Grocy units (list)")},
    "Grocy units (list)": {"main": link("Plan list msg")},
    "Plan list msg": {"main": link("Send plan list")},
    "Guide entry": {"main": link("Guide ready?")},
    "Guide ready?": {"main": outs(["Week recipes (gd)"], ["Send guide note"])},
    "Week recipes (gd)": {"main": link("Build guide")},
    "Build guide": {"main": link("OpenRouter guide")},
    "OpenRouter guide": {"main": link("Session plan")},
    "Session plan": {"main": link("Delete old session")},
    "Delete old session": {"main": link("Save session")},
    "Save session": {"main": link("Guide msg")},
    "Guide msg": {"main": link("Guide button?")},
    "Guide button?": {"main": outs(["Send batch button"], ["Send guide"])},
    "Import parse": {"main": link("Import build")},
    "Import build": {"main": link("Import ok?")},
    "Import ok?": {"main": outs(["Import save"], ["Send import error"])},
    "Import save": {"main": link("Import done")},
    "Import done": {"main": link("Send import")},
    "Save wish": {"main": link("Send wish")},
})

workflow = {
    "id": "KitchenRouter001",
    "name": "Kitchen - Telegram router",
    "active": False,
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "all", "saveDataErrorExecution": "all",
                 "timezone": TIMEZONE},
    "pinData": {},
}



def _fill(wf):
    """Replace the __PLACEHOLDER__ tokens embedded in prompts and Code-node JavaScript."""
    subs = {"__PERSONAL_NAME__": PERSONAL_NAME, "__TANDOOR_PUBLIC_URL__": TANDOOR_PUBLIC_URL, "__LOCALE_HINT__": LOCALE_HINT}
    text = json.dumps(wf, ensure_ascii=False)
    for token, value in subs.items():
        text = text.replace(token, json.dumps(value, ensure_ascii=False)[1:-1])
    return json.loads(text)


workflow = _fill(workflow)

if __name__ == "__main__":
    print(json.dumps([workflow], ensure_ascii=False, indent=1))
