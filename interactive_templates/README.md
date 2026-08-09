# Interactive Templates

Reusable worksheet image system based on **kitchen-scene style** role templates
with white object placeholders (not one baked-in food image per role).

## Layout

```text
interactive_templates/
  scenes/
    kitchen/
      mother_child/
      father_child/
      grandmother_child/
      grandfather_child/
    hobby/          # future scene family
    pet/            # future scene family
  objects/
    food/           # interaction specs (cupcakes, chocolates, pizza, ...)
    hobby/
    pet/
  assets/
    food/           # transparent PNG object cutouts
    hobby/
    pet/
  generate_role_templates.py
  compositor.py
  run_interactive_pipeline.py
```

## Runtime flow

1. Detect adult role from worksheet questions → pick `scenes/kitchen/<role>_child`
2. Choose object (favourite food / hobby / pet) → load `objects/.../<id>.json` + asset PNG
3. Paste faces into `face_regions`
4. Paste object into `object_positions` (white boxes)
5. AI beautify with **object-specific interaction instructions**
   so hands hold/place/offer the object correctly for that type
6. Sync question text to role + object + count from the same scene spec

## Kitchen role templates

Each role template is a bright modern kitchen, chest-up/counter framing,
exactly 2 characters (child + one adult), with evenly spaced **white rounded
placeholder boxes** on the counter for countable objects.

Object identity is NOT baked into the template image — it is filled at runtime.

Generate kitchen templates with:
```bash
python -m interactive_templates.generate_role_templates
```

## Hobby / park role templates (separate)

Hobby scenes are fully separated under `scenes/hobby/` and use their own generator
(do not use the kitchen generator for these):

```bash
python -m interactive_templates.generate_hobby_role_templates
```

Output:
```text
scenes/hobby/mother_child/
scenes/hobby/father_child/
scenes/hobby/grandmother_child/
scenes/hobby/grandfather_child/
```

Hobby object specs live in `objects/hobby/` (football, painting, crayons, kite, ...).
