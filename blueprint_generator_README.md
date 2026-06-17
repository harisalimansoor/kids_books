# `blueprint_generator.py` — Step 1: Geometric Blueprint Layout

## Purpose
Parses a personalised math question and draws a deterministic 1024×1024 blueprint image using coloured shapes that the AI renderer later converts into photorealistic elements.

## Colour Legend

| Shape | Colour | Meaning |
|---|---|---|
| Blue rectangle | `(0,0,255)` | Character body — AI renders as realistic person |
| Green circle / outline | `(0,255,0)` | Head placeholder — AI generates a head (or real face pasted here) |
| Red circle | `(255,0,0)` | Countable object — EXACT count enforced |
| Grey line | `(200,200,200)` | Ground plane for spatial reference |

## Public API

### `generate_blueprint(question: str, face_map: dict | None = None) -> tuple[Image.Image, dict]`
Full pipeline: parse → draw → return (image, metadata).

- **`question`**: Personalised question with `{role_name}` placeholders.
- **`face_map`**: Optional dict mapping `role_key` → face image file path. When provided, real face photos are pasted at head positions instead of green circles.
- **Returns**: `(PIL Image, metadata_dict)`.

## Question Parsing

### `parse_question(question: str) -> dict`
Returns structured data:
- `characters`: list of `{role, role_key, label}`
- `objects`: list of `{role_key, object, count}` (merged duplicates)
- `scene_context`: string describing environment
- `raw_question`: original text

### `_find_object_matches(text: str) -> list`
Finds `(count, object_name)` pairs. Uses longest-first keyword matching + container phrase skip (e.g. "bundle of", "box of"). Deduplicates overlapping matches.

### `_split_into_clauses(text: str) -> list[str]`
Splits text by `. ! ? , and but or` into clauses for per-role object association.

### `_find_role_in_clause(clause, known_roles) -> str | None`
Finds which role a clause belongs to. Handles `user_name`/"you"/"your" carefully: skips "you" if clause is a reader-directed question (e.g. "how many can you see?") via `_READER_QUESTION_PATTERN`.

### `_READER_QUESTION_PATTERN`
Regex matching question starters: `how many, can, could, do, does, did, would, will, what, which, where, when, why, is, are, have`.

### `_normalise_obj(word: str) -> str`
Normalises object words to base form (removes trailing 's', handles irregular plurals like "mangoes" → "mango").

## Drawing

### `_draw_blueprint(parsed: dict, face_map: dict | None = None) -> tuple[Image.Image, dict]`
- Characters evenly spaced across the canvas
- Each character gets a blue body rectangle + head circle (green or real face)
- Objects are red circles drawn in rows below each character, automatically wrapping when exceeding the character's width
- Ground line drawn below character bodies
- Metadata captures exact coordinates of every element

### `_paste_face(canvas, face_path, cx, cy, radius)`
Circle-crops a face photo, resizes to target diameter, and pastes onto the canvas with a soft-edge alpha mask.

## Constants
- `CANVAS_SIZE`: `(1024, 1024)`
- `OBJECT_KEYWORDS`: 66+ common countable nouns (sticker, book, apple, etc.)
- `SCENE_KEYWORDS`: 15+ scene descriptions (park, beach, classroom, etc.)
- `DEFAULT_SCENE`: `"a bright indoor room with a table"`

## Dependencies
- `PIL` (Image, ImageDraw)
- `os`, `re`, `math`

## Script Test
When run as `__main__`, generates a test blueprint for a sample sticker question and prints detailed metadata.
