# Question templates (Grade 1)

Pre-built visual templates for bank questions. Build each stem **once**; at workbook time only swap faces/names and assemble the PDF.

Source question text lives in `../Question clusters for grade 1/`.  
Templates for those stems live here under `grade_1/<topic>/`.

Both folders sit under `new_pipeline/`.

## Folder layout

```text
new_pipeline/question_templates/
  grade_1/
    addition/
      <stem_id>/
        question.txt      # stem with {user_name}, {mother_name}/{father_name}/…
        meta.json         # facts, answer, face/object regions
        <question_slug>.png  # art named from the question (see image_file in meta)
    subtraction/
    multiplication_and_division/
    fractions/
    money/
    time/
    measurement/
    geometry/
    number_and_place_value/
    general_math/
```

## stem_id rules

- Unique across the grade.
- Encodes topic + short facts + **locked adult role**, e.g. `add_apples_3_2_user_mother`.
- **Template image body = exact role in the question.** Mother question → mother body; father → father body. Do not use a generic “adult” body.
- Need mum + dad variants of the same maths? That is **two stems** (two images), not one shared image.
- At runtime: fill `{mother_name}` / `{user_name}` (etc.) from the family profile; paste matching role faces only.

## meta.json schema

| Field | Purpose |
| --- | --- |
| `stem_id` | Unique id; workbook dedupe key |
| `topic` | Must match parent folder |
| `layout_pattern` | Reusable layout type (`two_group_add`, `three_group_add`, `subtract_from_pile`, `equal_groups`, `half`, `shapes`, `clock`, …) |
| `question_file` / `image_file` | Paths inside the stem folder |
| `personalisation.face_slots` | e.g. `child`, `father` (same as locked role, not generic `adult`) |
| `personalisation.template_adult_role` | Exact body in the PNG (`mother` / `father` / …) — must match question placeholder **and** the adult `face_regions[].role` |
| `personalisation.allowed_adult_roles` | Usually just that one locked role |
| `face_regions` | Pixel boxes for face paste |
| `visual_groups` | Object groups with **exact counts** + positions |
| `answer.correct` / `answer.options` | Source of truth for MCQ + key |
| `answer.formula` | Optional e.g. `3+2` |
| `validation.verified` | Set `true` only after image matches counts and answer ∈ options |
| `status` | `placeholder` → `ready` when shippable |

## Runtime flow (error-free)

1. Select unique `stem_id`s that match available family roles (mother stem only if mother photo exists).
2. Load `meta.json` + image named in `image_file` + `question.txt`.
3. Paste faces into `face_regions` for the **locked** role; fill `{mother_name}` / `{user_name}` (etc.) from the profile.
4. Use `answer.correct` / `answer.options` as-is — do not re-ask an LLM for the key.
5. Skip stem if a required face photo is missing.

## Example stem

See:

`grade_1/addition/add_apples_3_2_user_adult/`

- Question: `{mother_name}` has 3 apples, child has 2 → total 5  
- Template style: **vibrant realistic** kitchen; **mother + child** bodies (role locked in the PNG)  
- Face boxes: auto (YuNet) when possible, otherwise **manual** `face_regions` in `meta.json`  
- After annotation: set `validation.verified: true` and `status: ready`

## Image generation from a question (required)

When asking the image model to build a stem PNG from `question.txt`:

1. Read the **exact adult role** from the question (`{mother_name}` → mother, `{father_name}` → father, etc.).
2. Tell the AI to draw that role’s body only — e.g. “a mother (adult woman) and a young child”, not a generic adult.
3. Match pronouns in the question (`her` / `him`) to that role.
4. Set `template_adult_role` + question placeholder + image to the **same** role. Never generate a mother body for a father question (or vice versa).

## Adding a new stem

1. Create `grade_1/<topic>/<stem_id>/` (include role in the id when useful, e.g. `…_user_mother`).
2. Write `question.txt` with the role placeholder (`{mother_name}`, …) and `meta.json` with matching `template_adult_role`.
3. Generate the `.png` with an explicit role in the prompt; object counts must match `visual_groups`.
4. Validate: counts, `correct` ∈ `options`, face boxes sane, role matches image.
5. Mark `verified` + `ready`.
