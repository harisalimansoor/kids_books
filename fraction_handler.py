"""
fraction_handler.py - Self-contained handler for FRACTIONS category questions.

Integrates with blueprint_generator.py via:
  detect_fraction_type(question) -> dict | None
  draw_fraction_question(parsed, fraction_info, face_map) -> (Image, dict) | None
  apply_half_circled_overlay(draw, metadata) -> None

For half-circled questions, normal blueprint drawing runs first, then
apply_half_circled_overlay adds green rings. For other fraction types,
draw_fraction_question handles the entire blueprint.
"""

import re
import math
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Self-contained constants (mirrors blueprint_generator values)
# ---------------------------------------------------------------------------
CANVAS_SIZE = (1024, 1024)
BG_COLOR = (255, 255, 255)

OBJ_COLOR = (255, 0, 0)
OBJ_RADIUS = 24
OBJ_GAP = 12
OBJ_START_Y = 700

GROUND_Y = 720
GROUND_COLOR = (200, 200, 200)

CIRCLE_RING_COLOR = (0, 200, 0)
CIRCLE_RING_WIDTH = 5


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_fraction_type(question: str) -> dict | None:
    """Detect fraction question patterns. Returns fraction_info dict or None."""
    # Type 1: "{role} has N objects. Half of them are circled."
    if re.search(r'[Hh]alf of them are circled', question):
        total = 0
        m = re.search(r'has (\d+)', question)
        if m:
            total = int(m.group(1))
        return {
            "fraction_type": "half_circled",
            "answer": total // 2,
        }

    # Type 2: "There are N objects divided into G equal groups."
    m = re.search(r'(\d+)\s+(\w+).*?divided into (\d+) equal groups', question)
    if m:
        total = int(m.group(1))
        obj = m.group(2)
        groups = int(m.group(3))
        return {
            "fraction_type": "equal_groups",
            "total": total,
            "object": obj,
            "groups": groups,
            "per_group": total // groups,
            "answer": total // groups,
        }

    # Type 3: "There are N objects, each divided/cut into P parts/halves."
    #   Pattern A: "There are 3 oranges, each cut into 2 halves."
    m = re.search(r'(\d+)\s+(\w+),\s*each\s+(?:divided|cut)\s+into\s+(\d+)\s+(?:parts|halves)', question)
    #   Pattern B: "There are 3 oranges. Each orange is cut into 2 halves."
    if not m:
        m = re.search(r'(\d+)\s+(\w+)\.\s*Each\s+\w+\s+is\s+(?:divided|cut)\s+into\s+(\d+)\s+(?:parts|halves)', question)
    if m:
        count = int(m.group(1))
        obj = m.group(2)
        parts = int(m.group(3))
        return {
            "fraction_type": "each_divided",
            "count": count,
            "object": obj,
            "parts": parts,
            "answer": count * parts,
        }

    # Type 4: Clock — three-quarters
    if re.search(r'clock.*?three-quarters', question):
        return {
            "fraction_type": "clock",
            "answer": 45,
        }

    return None


# ---------------------------------------------------------------------------
# Main integration entry points
# ---------------------------------------------------------------------------

def draw_fraction_question(
    parsed: dict,
    fraction_info: dict,
    face_map: dict[str, str] | None = None,
) -> tuple[Image.Image, dict] | None:
    """Draw a complete custom blueprint for Types 2-4.
    Returns (canvas, metadata) or None if not handled here."""
    ft = fraction_info["fraction_type"]

    if ft == "half_circled":
        return None  # handled by normal drawing + overlay
    elif ft == "equal_groups":
        return _draw_equal_groups(fraction_info)
    elif ft == "each_divided":
        return _draw_each_divided(fraction_info)
    elif ft == "clock":
        return _draw_clock(fraction_info)
    return None


def apply_half_circled_overlay(draw: ImageDraw.ImageDraw, metadata: dict) -> None:
    """Draw green rings around the first half of objects (half-circled type)."""
    for obj_group in metadata.get("objects", []):
        positions = obj_group.get("positions", [])
        half = len(positions) // 2
        for i in range(half):
            p = positions[i]
            ox, oy = p["x"], p["y"]
            r = OBJ_RADIUS + 4
            draw.ellipse(
                [ox - r, oy - r, ox + r, oy + r],
                outline=CIRCLE_RING_COLOR, width=CIRCLE_RING_WIDTH,
            )


# ---------------------------------------------------------------------------
# Type 2: Equal Groups  —  e.g. "8 pennies divided into 4 equal groups"
# ---------------------------------------------------------------------------

def _draw_equal_groups(fraction_info: dict) -> tuple[Image.Image, dict]:
    fi = fraction_info
    total = fi["total"]
    groups = fi["groups"]
    per_group = fi["per_group"]
    obj_name = fi["object"]

    canvas = Image.new("RGB", CANVAS_SIZE, BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    draw.line([(0, GROUND_Y), (CANVAS_SIZE[0], GROUND_Y)], fill=GROUND_COLOR, width=2)

    group_spacing = (CANVAS_SIZE[0] - 160) // groups
    start_x = (CANVAS_SIZE[0] - (groups - 1) * group_spacing) // 2

    obj_positions = []
    group_centers = []

    for g in range(groups):
        gx = start_x + g * group_spacing
        gy = OBJ_START_Y
        group_centers.append(gx)

        for i in range(per_group):
            ox = gx
            oy = gy + i * (OBJ_RADIUS * 2 + OBJ_GAP)
            draw.ellipse(
                [ox - OBJ_RADIUS, oy - OBJ_RADIUS,
                 ox + OBJ_RADIUS, oy + OBJ_RADIUS],
                fill=OBJ_COLOR,
            )
            obj_positions.append({"x": ox, "y": oy, "group": g})

    # Draw a green ring around the first group
    gx = group_centers[0]
    first_group = [p for p in obj_positions if p["group"] == 0]
    if first_group:
        min_y = min(p["y"] for p in first_group)
        max_y = max(p["y"] for p in first_group)
        center_y = (min_y + max_y) // 2
        rr = OBJ_RADIUS + 10
        draw.ellipse(
            [gx - rr, center_y - rr, gx + rr, center_y + rr],
            outline=CIRCLE_RING_COLOR, width=CIRCLE_RING_WIDTH,
        )

    metadata = _build_metadata(fraction_info, obj_name, total, obj_positions)
    return canvas, metadata


# ---------------------------------------------------------------------------
# Type 3: Each Divided  —  e.g. "3 circles, each divided into 5 parts"
# ---------------------------------------------------------------------------

def _draw_each_divided(fraction_info: dict) -> tuple[Image.Image, dict]:
    fi = fraction_info
    count = fi["count"]
    parts = fi["parts"]
    obj_name = fi["object"]

    canvas = Image.new("RGB", CANVAS_SIZE, BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    draw.line([(0, GROUND_Y), (CANVAS_SIZE[0], GROUND_Y)], fill=GROUND_COLOR, width=2)

    is_circle = "circle" in obj_name.lower()
    is_orange = "orange" in obj_name.lower()

    # Layout
    spacing = CANVAS_SIZE[0] // (count + 1)
    big_rx, big_ry = (70, 70) if is_circle else (75, 55)
    obj_positions = []

    for i in range(count):
        cx = spacing * (i + 1)
        cy = OBJ_START_Y + big_ry + 40

        outline_color = (0, 0, 0) if is_circle else (255, 165, 0)
        divider_color = (150, 150, 150) if is_circle else (200, 100, 0)

        # Draw outer shape
        draw.ellipse(
            [cx - big_rx, cy - big_ry, cx + big_rx, cy + big_ry],
            outline=outline_color, width=3,
        )

        # Draw internal dividing lines
        if is_orange and parts == 2:
            # Orange cut in half — single vertical line
            draw.line([(cx, cy - big_ry), (cx, cy + big_ry)], fill=divider_color, width=3)
        else:
            for p in range(parts):
                angle = 2 * math.pi * p / parts - math.pi / 2
                ex = cx + big_rx * math.cos(angle)
                ey = cy + big_ry * math.sin(angle)
                draw.line([(cx, cy), (ex, ey)], fill=divider_color, width=2)

        obj_positions.append({"x": cx, "y": cy})

    metadata = _build_metadata(fraction_info, obj_name, count, obj_positions)
    return canvas, metadata


# ---------------------------------------------------------------------------
# Type 4: Clock  —  e.g. "The hand has moved three-quarters of the way around"
# ---------------------------------------------------------------------------

def _draw_clock(fraction_info: dict) -> tuple[Image.Image, dict]:
    canvas = Image.new("RGB", CANVAS_SIZE, BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    cx, cy = CANVAS_SIZE[0] // 2, CANVAS_SIZE[1] // 2
    r = 200

    # Clock face
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(0, 0, 0), width=5)
    draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(0, 0, 0))

    # Hour markers (thick ticks at each hour)
    for h in range(12):
        angle = 2 * math.pi * h / 12 - math.pi / 2
        inner = r - 25
        outer = r - 5
        draw.line([
            (cx + inner * math.cos(angle), cy + inner * math.sin(angle)),
            (cx + outer * math.cos(angle), cy + outer * math.sin(angle)),
        ], fill=(0, 0, 0), width=4)

    # Minute markers (small ticks)
    for m in range(60):
        if m % 5 == 0:
            continue
        angle = 2 * math.pi * m / 60 - math.pi / 2
        inner = r - 15
        outer = r - 5
        draw.line([
            (cx + inner * math.cos(angle), cy + inner * math.sin(angle)),
            (cx + outer * math.cos(angle), cy + outer * math.sin(angle)),
        ], fill=(180, 180, 180), width=1)

    # Minute hand at 45 minutes (three-quarters = 9 position)
    minute_angle = -math.pi / 2 + 2 * math.pi * 45 / 60
    draw.line([
        (cx, cy),
        (cx + r * 0.75 * math.cos(minute_angle), cy + r * 0.75 * math.sin(minute_angle)),
    ], fill=(0, 0, 0), width=6)

    # Hour hand — 45 min past 12 = 0.75 of way between 12 and 1
    hour_angle = -math.pi / 2 + (45 / 60) * (2 * math.pi / 12)
    draw.line([
        (cx, cy),
        (cx + r * 0.45 * math.cos(hour_angle), cy + r * 0.45 * math.sin(hour_angle)),
    ], fill=(0, 0, 0), width=10)

    draw.line([(0, GROUND_Y), (CANVAS_SIZE[0], GROUND_Y)], fill=GROUND_COLOR, width=2)

    metadata = _build_metadata(fraction_info, "clock", 1, [{"x": cx, "y": cy}])
    return canvas, metadata


# ---------------------------------------------------------------------------
# Shared metadata builder
# ---------------------------------------------------------------------------

def _build_metadata(fraction_info: dict, obj_name: str, count: int,
                    positions: list[dict]) -> dict:
    return {
        "canvas_size": list(CANVAS_SIZE),
        "characters": [],
        "objects": [{
            "role_key": "generic",
            "object": obj_name,
            "count": count,
            "positions": positions,
        }],
        "scene_context": "a bright indoor room with a table",
        "raw_question": "",
        "has_faces": False,
        "fraction_info": fraction_info,
    }
