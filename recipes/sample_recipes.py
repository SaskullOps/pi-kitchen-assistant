# Two tiny made-up sample recipes showing the pack format consumed by load_recipes.py.
# Ingredient tuples: (food name in Tandoor, amount, unit, note). Unit "" = no unit.
# `kind` drives the planner: comida-batch (lunch, cooked in bulk), cena (quick dinner), desayuno, merienda.
# Extra tags the planner understands: congelable, rápida, fácil (no stove, <= 5 min), fin-de-semana, prep-domingo,
# dulce/salado, temporada-otoño.

NEW_FOODS = {
    "Sample lentils": "Productos Secos",
    "Sample tomato": "Frutas y Verduras",
}

RECIPES = [
    dict(name="Sample lentil stew", kind="comida-batch", servings=4, cuisine=["mediterránea"],
         tags=["fogón", "congelable"], working=15, waiting=35,
         description="Made-up example recipe.",
         ingredients=[("Sample lentils", 400, "g", ""), ("Sample tomato", 2, "piezas", ""), ("Sal", 1, "Pizca", "")],
         steps="1. Chop the tomato.\n2. Simmer everything with water for 35 minutes.\n3. Portion into 4 containers."),
    dict(name="Sample tomato toast", kind="cena", servings=2, cuisine=["casera"],
         tags=["rápida"], working=5, waiting=0,
         description="Made-up example recipe.",
         ingredients=[("Sample tomato", 2, "piezas", ""), ("Sal", 1, "Pizca", "")],
         steps="1. Toast the bread.\n2. Rub with tomato and add salt."),
]
