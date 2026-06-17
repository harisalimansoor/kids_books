"""
blueprint_generator.py - Step 1 of the Blueprint-to-Render pipeline.

Parses a math question and draws a deterministic "blueprint" image using
colored geometric shapes:
  - Blue rectangles = character bodies (AI renders as realistic people)
  - Green circles = head placeholders (AI generates appropriate heads)
  - Red circles = countable objects (EXACT count enforced)
  - Light gray ground line for spatial reference

Output:
  blueprint_image (PIL Image)  — the shape-based layout
  metadata (dict)              — exact coordinates of all elements
"""

import os
import re
import math
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CANVAS_SIZE = (1024, 1024)
BG_COLOR = (255, 255, 255)

# Character appearance
CHAR_BODY_COLOR = (0, 0, 255)       # blue
CHAR_BODY_SIZE = (130, 260)         # width, height
CHAR_BODY_Y = 380                   # top of body rectangle
HEAD_MARKER_COLOR = (0, 255, 0)     # green
HEAD_MARKER_RADIUS = 55              # placeholder for AI to generate a head
HEAD_MARKER_Y = CHAR_BODY_Y - 60    # center y of head marker (shifted up for bigger circle)

# Object appearance
OBJ_COLOR = (255, 0, 0)            # red
OBJ_RADIUS = 24
OBJ_GAP = 12                        # gap between objects in a row
OBJ_START_Y = CHAR_BODY_Y + CHAR_BODY_SIZE[1] + 60  # first row y
OBJ_ROW_H = OBJ_RADIUS * 2 + OBJ_GAP

# Ground line
GROUND_Y = CHAR_BODY_Y + CHAR_BODY_SIZE[1] + 20
GROUND_COLOR = (200, 200, 200)

# Object patterns — extended list for better parsing
OBJECT_KEYWORDS = [
    "sticker", "book", "notebook", "mango", "marble", "ball",
    "apple", "balloon", "toy car", "car", "shell", "sweet",
    "candy", "pencil", "pen", "eraser", "crayon", "flower",
    "leaf", "stone", "coin", "button", "bead", "star",
    "heart", "square", "triangle", "circle", "ribbon",
    "straw", "stick", "block", "cube", "dice", "egg",
    "cupcake", "cookie", "biscuit", "banana", "orange",
    "grape", "cherry", "strawberry", "pear", "lemon",
    "sweet", "lollipop", "chocolate", "sandwich", "slice of pizza",
    "frog", "fish", "bird", "butterfly", "ladybird",
    "toy soldier", "teddy bear", "doll", "robot", "train",
    "bus", "plane", "boat", "bicycle", "scooter",
    "hat", "cap", "glove", "sock", "shoe",
    "ribbon", "bow", "bell", "candle", "key",
    "clock", "watch", "ring", "necklace", "bracelet",
    "sharpener", "ruler", "bag", "bottle", "cup",
    "plate", "bowl", "spoon", "fork", "glass",
    "tree", "table", "chair", "bed", "box",
]

# Scene context keywords
SCENE_KEYWORDS = {
    "park":           "a sunny park with green grass",
    "garden":         "a beautiful garden with flowers",
    "beach":          "a sandy beach by the sea",
    "sea":            "a sandy beach by the sea",
    "school":         "a bright UK classroom",
    "classroom":      "a bright UK classroom",
    "kitchen":        "a clean kitchen with a table",
    "table":          "a room with a wooden table",
    "bedroom":        "a tidy bedroom",
    "playground":     "a colourful playground",
    "farm":           "a green farm with animals",
    "zoo":            "a sunny day at the zoo",
    "shop":           "a small shop with shelves",
    "supermarket":    "a bright supermarket aisle",
    "home":           "a cosy British home living room",
    "indoor":         "a bright indoor room",
    "outdoor":        "a sunny outdoor scene",
}

DEFAULT_SCENE = "a bright indoor room with a table"


# ---------------------------------------------------------------------------
# Question Parsing
# ---------------------------------------------------------------------------

def _normalise_obj(word: str) -> str:
    """Normalise an object word to its base form."""
    word = word.lower().strip().rstrip("s")
    # Handle irregular plurals
    plural_fixes = {
        "mangoes": "mango", "mangos": "mango",
        "cherries": "cherry", "berries": "berry",
        "leaves": "leaf", "knives": "knife",
        "wolves": "wolf", "halves": "half",
    }
    return plural_fixes.get(word + "s", word)


def _find_object_matches(text: str):
    """Find all (count, object_name) pairs in text — NO overlapping matches."""
    matches = []
    # Build sorted object keywords (longest first to match multi-word first)
    sorted_objs = sorted(OBJECT_KEYWORDS, key=len, reverse=True)
    obj_pattern = "|".join(re.escape(o) for o in sorted_objs)

    # Single pattern: match N + optional container phrase + object name
    pat = re.compile(
        rf'(\d+)\s+'
        rf'(?:a\s+|the\s+)?'
        rf'(?:bundle(?:s)?\s+of\s+|pair(?:s)?\s+of\s+|box(?:es)?\s+of\s+|'
        rf'pack(?:s)?\s+of\s+|piece(?:s)?\s+of\s+|bunch(?:es)?\s+of\s+|'
        rf'group(?:s)?\s+of\s+|set(?:s)?\s+of\s+)?'
        rf'({obj_pattern})\w*',
        re.IGNORECASE
    )

    # Collect all matches with their positions, then filter overlapping
    raw_matches = []
    for m in pat.finditer(text):
        obj_word = None
        raw_obj = m.group(2).lower().rstrip("s") if m.group(2) else None
        # Try to match against known objects
        for o in sorted_objs:
            if o.lower() == raw_obj or o.lower().rstrip("s") == raw_obj:
                obj_word = o
                break
        if not obj_word and raw_obj:
            # Fuzzy match: check if raw_obj is contained in any known object
            for o in sorted_objs:
                o_clean = o.lower().rstrip("s")
                if raw_obj == o_clean or raw_obj in o_clean or o_clean in raw_obj:
                    obj_word = o
                    break
        if obj_word:
            raw_matches.append({
                "count": int(m.group(1)),
                "object": _normalise_obj(obj_word),
                "start": m.start(),
                "end": m.end(),
            })

    # Deduplicate: skip matches that overlap (start within previous match)
    raw_matches.sort(key=lambda x: x["start"])
    last_end = -1
    for rm in raw_matches:
        if rm["start"] >= last_end:
            matches.append(rm)
            last_end = rm["end"]

    return matches


def _split_into_clauses(text: str) -> list[str]:
    """Split question into clauses by sentence boundaries, commas, and/but/or."""
    # First split by sentence endings
    sentences = re.split(r'[.!?]+', text)
    clauses = []
    for s in sentences:
        if not s.strip():
            continue
        # Split each sentence by comma, and, but, or
        parts = re.split(r',\s*|\s+and\s+|\s+but\s+|\s+or\s+', s)
        for p in parts:
            p = p.strip()
            if p and len(p) > 5:
                clauses.append(p)
    return clauses


# Patterns that indicate "you" is the reader being asked, not a character in the scene
_READER_QUESTION_PATTERN = re.compile(
    r'^(how many|can|could|do|does|did|would|will|what|which|where|when|why|is|are|have)',
    re.IGNORECASE,
)


def _find_role_in_clause(clause: str, known_roles: list[str]) -> str | None:
    """
    Find the first role mentioned in a clause.

    Only treats "you"/"your" as user_name if the clause is a statement
    describing scene action (e.g. "you have 3 apples"), NOT a question
    being asked to the reader (e.g. "how many can you see?").
    """
    clause_lower = clause.lower().strip()
    # Check {role_name} patterns first
    for rk in known_roles:
        if rk.lower() in clause_lower:
            return rk
    # Check "you" / "your" — skip if clause is a reader-directed question
    if re.search(r'\byou\b|\byour\b', clause_lower):
        if _READER_QUESTION_PATTERN.match(clause_lower):
            return None
        return "user_name"
    return None


def parse_question(question: str) -> dict:
    """
    Parse a personalised math question and return structured data.

    Returns:
      dict with keys:
        - characters: list of {role, role_key, label}
        - objects: list of {role_key, object_name, count}
        - scene_context: str describing the environment
        - raw_question: the original text
    """
    # 1. Extract role placeholders {role_name}
    role_keys = re.findall(r'\{(\w+)\}', question)
    seen = set()
    unique_role_keys = []
    for rk in role_keys:
        if rk not in seen:
            seen.add(rk)
            unique_role_keys.append(rk)

    # 2. Handle "you" / "your" — only add Child character if "you" appears
    #    in a statement clause (scene action), not just reader-directed questions
    if "user_name" not in unique_role_keys:
        for clause in _split_into_clauses(question):
            clause_lower = clause.lower().strip()
            if re.search(r'\byou\b|\byour\b', clause_lower):
                if not _READER_QUESTION_PATTERN.match(clause_lower):
                    unique_role_keys.append("user_name")
                    break
    else:
        # {user_name} was found as a placeholder — remove it if it only
        # appears in reader-directed question clauses (e.g. "how many can
        # {user_name} see?") and NOT in any scene-action clause.
        user_only_in_questions = True
        for clause in _split_into_clauses(question):
            if "{user_name}" in clause:
                clause_lower = clause.lower().strip()
                if not _READER_QUESTION_PATTERN.match(clause_lower):
                    user_only_in_questions = False
                    break
        if user_only_in_questions:
            unique_role_keys.remove("user_name")

    role_labels = {
        "grandmother_name": "Grandmother",
        "grandfather_name": "Grandfather",
        "mother_name":      "Mother",
        "father_name":      "Father",
        "sibling_name":     "Sibling",
        "user_name":        "Child",
        "friend_name":      "Friend",
        "teacher_name":     "Teacher",
    }

    characters = []
    for rk in unique_role_keys:
        characters.append({
            "role": rk,
            "role_key": rk,
            "label": role_labels.get(rk, rk.replace("_name", "").capitalize()),
        })

    # 3. Split into clauses for role-object association
    clauses = _split_into_clauses(question)

    # 4. For each clause, find which role it belongs to and which objects
    raw_objects = []
    for clause in clauses:
        clause_role = _find_role_in_clause(clause, unique_role_keys)
        if not clause_role:
            continue
        clause_matches = _find_object_matches(clause)
        for m in clause_matches:
            raw_objects.append({
                "role_key": clause_role,
                "object": m["object"],
                "count": m["count"],
            })

    # 5. Merge duplicate (role_key, object) pairs
    merged = {}
    for ro in raw_objects:
        key = (ro["role_key"], ro["object"])
        if key in merged:
            merged[key]["count"] += ro["count"]
        else:
            merged[key] = dict(ro)
    objects = list(merged.values())

    # 6. Scene context
    scene_context = DEFAULT_SCENE
    for keyword, scene_desc in SCENE_KEYWORDS.items():
        if keyword in question.lower():
            scene_context = scene_desc
            break

    return {
        "characters": characters,
        "objects": objects,
        "scene_context": scene_context,
        "raw_question": question,
    }


# ---------------------------------------------------------------------------
# Blueprint Drawing
# ---------------------------------------------------------------------------

def _paste_face(canvas: Image.Image, face_path: str, cx: int, cy: int, radius: int):
    """Circle-crop a face photo and paste onto canvas at (cx, cy)."""
    face = Image.open(face_path).convert("RGBA")
    # Crop to centered square
    w, h = face.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    face = face.crop((left, top, left + side, top + side))
    # Resize to target diameter
    target = radius * 2
    face = face.resize((target, target), Image.LANCZOS)
    # Circular alpha mask with soft edge
    mask = Image.new("L", (target, target), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, target, target], fill=255)
    # Paste
    canvas.paste(face, (cx - radius, cy - radius), mask)


def _draw_blueprint(parsed: dict,
                    face_map: dict[str, str] | None = None) -> tuple[Image.Image, dict]:
    """
    Draw the blueprint image based on parsed question data.

    Parameters
    ----------
    parsed : dict
        Parsed question data from parse_question().
    face_map : dict[str, str] | None
        Optional mapping from role_key (e.g. 'user_name') to face image file path.
        When provided, the real face is pasted instead of a green head marker.

    Returns (PIL Image, metadata_dict).
    """
    canvas = Image.new("RGB", CANVAS_SIZE, BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    chars = parsed["characters"]
    objs = parsed["objects"]
    n_chars = len(chars)

    # Calculate character positions (evenly spaced)
    if n_chars == 0:
        char_positions = []
    elif n_chars == 1:
        char_positions = [(CANVAS_SIZE[0] // 2 - CHAR_BODY_SIZE[0] // 2, CHAR_BODY_Y)]
    else:
        total_width = n_chars * CHAR_BODY_SIZE[0] + (n_chars - 1) * 80
        start_x = (CANVAS_SIZE[0] - total_width) // 2
        char_positions = []
        for i in range(n_chars):
            x = start_x + i * (CHAR_BODY_SIZE[0] + 80)
            char_positions.append((x, CHAR_BODY_Y))

    metadata_chars = []
    metadata_objects = []
    has_faces = False

    # Group objects by role_key
    objects_by_role = {}
    for obj in objs:
        rk = obj["role_key"]
        if rk not in objects_by_role:
            objects_by_role[rk] = []
        objects_by_role[rk].append(obj)

    # Draw characters
    for i, char in enumerate(chars):
        bx, by = char_positions[i]
        body_rect = [bx, by, bx + CHAR_BODY_SIZE[0], by + CHAR_BODY_SIZE[1]]

        # Blue body rectangle
        draw.rectangle(body_rect, fill=CHAR_BODY_COLOR)

        # Head
        hx = bx + CHAR_BODY_SIZE[0] // 2
        hy = HEAD_MARKER_Y
        face_path = face_map.get(char["role_key"]) if face_map else None
        if face_path and os.path.exists(face_path):
            _paste_face(canvas, face_path, hx, hy, HEAD_MARKER_RADIUS)
            has_faces = True
            # Soft outline to hint the AI where the head boundary is
            draw.ellipse(
                [hx - HEAD_MARKER_RADIUS, hy - HEAD_MARKER_RADIUS,
                 hx + HEAD_MARKER_RADIUS, hy + HEAD_MARKER_RADIUS],
                outline=(100, 255, 100), width=2,
            )
        else:
            # Green placeholder circle (no face uploaded)
            draw.ellipse(
                [hx - HEAD_MARKER_RADIUS, hy - HEAD_MARKER_RADIUS,
                 hx + HEAD_MARKER_RADIUS, hy + HEAD_MARKER_RADIUS],
                fill=HEAD_MARKER_COLOR,
            )

        metadata_chars.append({
            "role": char["role"],
            "role_key": char["role_key"],
            "label": char["label"],
            "body_rect": {"x": bx, "y": by, "w": CHAR_BODY_SIZE[0], "h": CHAR_BODY_SIZE[1]},
            "head_center": {"x": hx, "y": hy},
            "body_bottom_y": by + CHAR_BODY_SIZE[1],
        })

        # Draw objects for this character (sequential, no row reset between types)
        char_objs = objects_by_role.get(char["role_key"], [])
        obj_idx = 0
        current_row_y = OBJ_START_Y
        for obj_entry in char_objs:
            count = obj_entry["count"]
            obj_name = obj_entry["object"]
            object_positions = []

            for _ in range(count):
                max_x = bx + CHAR_BODY_SIZE[0] - OBJ_RADIUS
                ox = bx + OBJ_RADIUS + obj_idx * (OBJ_RADIUS * 2 + OBJ_GAP)
                oy = current_row_y
                # Wrap to next row if needed
                if ox > max_x:
                    obj_idx = 0
                    current_row_y += OBJ_ROW_H
                    ox = bx + OBJ_RADIUS + obj_idx * (OBJ_RADIUS * 2 + OBJ_GAP)
                    oy = current_row_y

                draw.ellipse(
                    [ox - OBJ_RADIUS, oy - OBJ_RADIUS,
                     ox + OBJ_RADIUS, oy + OBJ_RADIUS],
                    fill=OBJ_COLOR,
                )
                object_positions.append({"x": ox, "y": oy})
                obj_idx += 1

            metadata_objects.append({
                "role_key": char["role_key"],
                "object": obj_name,
                "count": count,
                "positions": object_positions,
            })

    # Ground line
    draw.line([(0, GROUND_Y), (CANVAS_SIZE[0], GROUND_Y)],
              fill=GROUND_COLOR, width=2)

    metadata = {
        "canvas_size": list(CANVAS_SIZE),
        "characters": metadata_chars,
        "objects": metadata_objects,
        "scene_context": parsed["scene_context"],
        "raw_question": parsed["raw_question"],
        "has_faces": has_faces,
    }

    return canvas, metadata


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_blueprint(question: str,
                       face_map: dict[str, str] | None = None) -> tuple[Image.Image, dict]:
    """
    Full pipeline: parse question -> draw blueprint -> return (image, metadata).

    Parameters
    ----------
    question : str
        The personalised math question with {role_name} placeholders.
    face_map : dict[str, str] | None
        Optional mapping from role_key to face image path. When provided,
        real face photos are pasted at head positions instead of green circles.

    Returns
    -------
    blueprint_img : PIL.Image
        The RGB blueprint image (1024x1024).
    metadata : dict
        Nested dict with exact positions of all elements.
    """
    parsed = parse_question(question)
    return _draw_blueprint(parsed, face_map)


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_q = (
        "Look at the picture! {grandmother_name} is holding 2 stickers, "
        "{mother_name} has 5 stickers on the table, "
        "and you are showing 2 stickers. How many stickers can you count altogether?"
    )
    img, meta = generate_blueprint(test_q)
    img.save("blueprint_test.png")
    print(f"Generated blueprint: {img.size}")
    print(f"Characters: {len(meta['characters'])}")
    print(f"Object groups: {len(meta['objects'])}")
    total_objs = sum(g["count"] for g in meta["objects"])
    print(f"Grandmother objects: {[o for o in meta['objects'] if o['role_key'] == 'grandmother_name']}")
    print(f"Mother objects: {[o for o in meta['objects'] if o['role_key'] == 'mother_name']}")
    print(f"User objects: {[o for o in meta['objects'] if o['role_key'] == 'user_name']}")
    print(f"Total objects: {total_objs}")
    import json
    print(json.dumps(meta, indent=2))
