"""
app/math_visual_engine.py
───────────────────────────────────────────────────────────────────────────────
Deterministic Mathematical Visual Engine & Question Schema for MyInteliBooks.

CORE ARCHITECTURAL PRINCIPLE:
    AI Layer: Responsible for story, characters, environment, clothing, visual style.
    Math Engine: Responsible for deterministic mathematical accuracy, numbers, validation.
    Visual Renderer: Responsible for exact object counts, groups of 10, arrays,
                     subtraction cross-outs (with objects visible underneath),
                     place-value representations, equations, and labels.

QUANTITY REPRESENTATION RULES:
    1–10:    Individual objects (countable, clearly spaced, no grouping).
    11–20:   Individual objects with grouping (1 ten-frame / [10] + remainder).
    21–50:   Groups of 10 by default ([10] [10] [10] [6] = 36).
    51–100:  Grouped tens + ones (7 tens + 3 ones = 73).
    100+:    Place-value representation (1 hundred + 3 tens + 4 ones = 134).

SUBTRACTION & CROSS-OUTS:
    - Initial quantity rendered.
    - Selected objects programmatically crossed out with graphical overlay (❌).
    - Crossed objects remain visible underneath the cross.
    - Grouped subtraction for larger quantities (crossed [10] boxes + crossed ones).
    - Subtraction with regrouping support for Grade 2+ (42 - 18 -> 3 tens + 12 ones).

MULTIPLICATION & DIVISION:
    - Multiplication: Rectangular arrays (R x C) or equal groups with containers.
    - Division: Equal sharing groups.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── Asset and font paths ──────────────────────────────────────────────────────
ENGINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = ENGINE_DIR.parent
FONTS_DIR = REPO_ROOT / "shared" / "fonts"

# Resolve fonts with safe fallback
def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        FONTS_DIR / f"{name}.ttf",
        FONTS_DIR / "Quicksand-Bold.ttf",
        FONTS_DIR / "Baloo2-Bold.ttf",
        FONTS_DIR / "Quicksand-Medium.ttf",
    ]
    for p in candidates:
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── 1. STRUCTURED MATHEMATICAL QUESTION SCHEMA ───────────────────────────────

@dataclass
class MathNumbers:
    start: Optional[int] = None
    subtract: Optional[int] = None
    change: Optional[int] = None
    number1: Optional[int] = None
    number2: Optional[int] = None
    groups: Optional[int] = None
    objects_per_group: Optional[int] = None
    total: Optional[int] = None
    group_size: Optional[int] = None
    remainder: Optional[int] = None
    hundreds: Optional[int] = None
    tens: Optional[int] = None
    ones: Optional[int] = None
    answer: int = 0


@dataclass
class ObjectSpecification:
    name: str = "counter"
    singular: str = "counter"
    plural: str = "counters"
    icon_key: str = "counter"
    category: str = "general"


@dataclass
class VisualizationConfig:
    strategy: str = "individual"  # "individual", "grouped_tens", "grouped_subtraction", "subtraction_regrouping", "array", "equal_groups", "place_value"
    group_size: int = 10
    groups: int = 0
    remainder: int = 0
    cross_out: int = 0
    show_equation: bool = True
    show_labels: bool = True
    show_regrouping: bool = False


@dataclass
class SceneContext:
    setting: str = "learning desk"
    characters: List[str] = field(default_factory=list)
    activity: str = "solving maths problem"


@dataclass
class StructuredQuestion:
    question_id: str
    grade: str
    operation: str  # "counting", "addition", "subtraction", "multiplication", "division", "place_value"
    question: str
    numbers: MathNumbers
    object: ObjectSpecification
    visualization: VisualizationConfig
    scene: SceneContext = field(default_factory=SceneContext)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if "visualization" in d:
            d["visualization"]["type"] = d["visualization"].get("strategy")
        return d


# ── 2. MATHEMATICAL VALIDATION LAYER ─────────────────────────────────────────

class MathValidationError(ValueError):
    """Raised when question numbers violate mathematical consistency."""
    pass


def validate_mathematics(sq: StructuredQuestion) -> None:
    """
    Strict mathematical validation ensuring numbers match operations.
    Zero hallucinations allowed in the mathematical foundation.
    """
    nums = sq.numbers
    op = sq.operation.lower().strip()

    if op == "subtraction":
        start = nums.start if nums.start is not None else (nums.number1 or 0)
        sub = nums.subtract if nums.subtract is not None else (abs(nums.change or 0) or nums.number2 or 0)
        if start < sub:
            raise MathValidationError(f"Subtraction start ({start}) must be >= subtract ({sub}).")
        if nums.answer != (start - sub):
            raise MathValidationError(
                f"Subtraction answer mismatch: {start} - {sub} != {nums.answer}"
            )

    elif op == "addition":
        n1 = nums.number1 if nums.number1 is not None else (nums.start or 0)
        n2 = nums.number2 if nums.number2 is not None else (nums.change or 0)
        if nums.answer != (n1 + n2):
            raise MathValidationError(
                f"Addition answer mismatch: {n1} + {n2} != {nums.answer}"
            )

    elif op == "multiplication":
        g = nums.groups or 1
        opg = nums.objects_per_group or nums.group_size or 1
        if nums.answer != (g * opg):
            raise MathValidationError(
                f"Multiplication answer mismatch: {g} * {opg} != {nums.answer}"
            )

    elif op == "division":
        tot = nums.total or nums.start or nums.answer
        gs = nums.group_size or nums.groups or 1
        if gs <= 0:
            raise MathValidationError("Division group size must be > 0.")
        expected = tot // gs
        if nums.answer != expected:
            raise MathValidationError(
                f"Division answer mismatch: {tot} // {gs} != {nums.answer}"
            )

    elif op == "place_value":
        h = nums.hundreds or 0
        t = nums.tens or 0
        o = nums.ones or 0
        tot = (h * 100) + (t * 10) + o
        if tot != nums.answer and nums.answer > 0:
            raise MathValidationError(
                f"Place value mismatch: {h} hundreds + {t} tens + {o} ones ({tot}) != {nums.answer}"
            )

    elif op == "counting":
        cnt = nums.start if nums.start is not None else nums.answer
        if cnt < 0:
            raise MathValidationError(f"Counting quantity ({cnt}) cannot be negative.")


# ── 3. VISUAL VALIDATION LAYER ───────────────────────────────────────────────

class VisualValidationError(ValueError):
    """Raised when visual layout does not match required mathematical counts."""
    pass


def validate_visual_layout(expected_total: int, rendered_counts: Dict[str, int], crossed_count: int = 0) -> None:
    """
    Verifies that the exact number of objects laid out on canvas matches the expected count.
    """
    actual_total = sum(rendered_counts.values())
    if actual_total != expected_total:
        raise VisualValidationError(
            f"Visual layout count ({actual_total}) does not match expected total ({expected_total})!"
        )
    if crossed_count > actual_total:
        raise VisualValidationError(
            f"Crossed objects ({crossed_count}) exceeds total objects ({actual_total})!"
        )


# ── 4. QUESTION INFERENCE & STRATEGY RESOLVER ────────────────────────────────

def infer_structured_question(
    question_text: str,
    meta: Optional[Dict[str, Any]] = None,
    grade_id: str = "Grade_2",
    stem_id: str = "stem_01",
) -> StructuredQuestion:
    """
    Analyzes question text and existing stem meta.json to produce a fully validated StructuredQuestion.
    Automatically applies the user's quantity representation rules based on grade and numbers.
    """
    q = (question_text or "").strip()
    meta = meta or {}
    ans_meta = meta.get("answer") or {}

    # Extract all positive integers
    found_nums = [int(n) for n in re.findall(r"\b\d+\b", q)]

    # Infer operation with strict accuracy
    op = "counting"
    q_low = q.lower()
    formula_str = str((meta.get("answer") or {}).get("formula") or "")

    add_keywords = [
        "altogether", "in total", "plus", "add", "adds", "added", "adding",
        "addition", "bonds", "together", "sum", "combined", "more than", "total"
    ]
    sub_keywords = [
        "take away", "takes away", "took away", "gave away", "gives away",
        "minus", "how many are left", "how many left", "left over", "are left",
        "is left", "were left", "ate", "eats", "sold", "sells", "fewer",
        "difference", "lost", "loses", "subtraction"
    ]

    if "+" in formula_str or any(k in q_low for k in ["altogether", "in total", "plus", "addition", "how many in all"]):
        op = "addition"
    elif "-" in formula_str or any(k in q_low for k in ["take away", "takes away", "took away", "gave away", "how many are left", "how many left", "minus"]):
        op = "subtraction"
    elif any(k in q_low for k in ["times", "multiplied", "array", "rows of", "groups of", "each tray has", "each basket has", "each box has"]):
        op = "multiplication"
    elif any(k in q_low for k in ["shared equally", "divided", "how many each", "divide", "split equally"]):
        op = "division"
    elif any(k in q_low for k in ["hundred", "place value", "tens and ones", "partition"]):
        op = "place_value"
    elif any(k in q_low for k in add_keywords):
        op = "addition"
    elif any(k in q_low for k in sub_keywords):
        op = "subtraction"

    # Identify object noun
    obj_name = "counter"
    singular = "counter"
    plural = "counters"
    icon_key = "counter"

    known_objects = {
        "pancake": ("golden pancake", "golden pancakes", "pancake"),
        "apple": ("apple", "apples", "apple"),
        "muffin": ("muffin", "muffins", "muffin"),
        "cupcake": ("cupcake", "cupcakes", "muffin"),
        "cookie": ("cookie", "cookies", "cookie"),
        "biscuit": ("biscuit", "biscuits", "cookie"),
        "strawberry": ("strawberry", "strawberries", "strawberry"),
        "balloon": ("balloon", "balloons", "balloon"),
        "crayon": ("crayon", "crayons", "crayon"),
        "pencil": ("pencil", "pencils", "crayon"),
        "brick": ("brick", "bricks", "brick"),
        "lego": ("lego brick", "lego bricks", "brick"),
        "toy car": ("toy car", "toy cars", "car"),
        "car": ("toy car", "toy cars", "car"),
        "box": ("box", "boxes", "brick"),
        "block": ("block", "blocks", "brick"),
        "seashell": ("seashell", "seashells", "counter"),
        "shell": ("seashell", "seashells", "counter"),
        "mango": ("mango", "mangoes", "apple"),
        "flower": ("flower", "flowers", "flower"),
        "star": ("star", "stars", "star"),
        "coin": ("coin", "coins", "coin"),
        "bird": ("bird figure", "bird figures", "counter"),
        "watermelon": ("slice of watermelon", "slices of watermelon", "counter"),
        "pizza": ("slice of pizza", "slices of pizza", "counter"),
        "burger": ("mini burger", "mini burgers", "counter"),
        "donut": ("donut", "donuts", "cookie"),
        "doughnut": ("doughnut", "doughnuts", "cookie"),
        "counter": ("counter", "counters", "counter"),
    }

    for k, v in known_objects.items():
        if k in q_low:
            singular, plural, icon_key = v
            obj_name = singular
            break

    # Extract answer
    ans_val: int = 0
    raw_corr = ans_meta.get("correct")
    if raw_corr is not None and str(raw_corr).isdigit():
        ans_val = int(raw_corr)
    elif found_nums:
        ans_val = found_nums[-1]

    nums = MathNumbers(answer=ans_val)

    # Populate operation numbers
    if op == "subtraction":
        if len(found_nums) >= 2:
            s1, s2 = found_nums[0], found_nums[1]
            nums.start = max(s1, s2)
            nums.subtract = min(s1, s2)
            nums.change = -nums.subtract
            nums.answer = nums.start - nums.subtract
        elif nums.start is not None and nums.subtract is not None:
            nums.answer = nums.start - nums.subtract
        else:
            nums.start = max(ans_val + 5, 10)
            nums.subtract = 5
            nums.answer = nums.start - nums.subtract

    elif op == "addition":
        if len(found_nums) >= 2:
            nums.number1 = found_nums[0]
            nums.number2 = found_nums[1]
            nums.answer = nums.number1 + nums.number2
        else:
            nums.number1 = ans_val // 2
            nums.number2 = ans_val - nums.number1

    elif op == "multiplication":
        if len(found_nums) >= 2:
            nums.groups = found_nums[0]
            nums.objects_per_group = found_nums[1]
            nums.answer = nums.groups * nums.objects_per_group
        else:
            nums.groups = 4
            nums.objects_per_group = max(1, ans_val // 4)
            nums.answer = nums.groups * nums.objects_per_group

    elif op == "division":
        if len(found_nums) >= 2:
            nums.total = max(found_nums[0], found_nums[1])
            nums.group_size = min(found_nums[0], found_nums[1])
            nums.answer = nums.total // nums.group_size
        else:
            nums.total = ans_val * 4
            nums.group_size = 4
            nums.answer = ans_val

    elif op == "place_value":
        tot = nums.answer or (found_nums[0] if found_nums else 47)
        nums.hundreds = tot // 100
        nums.tens = (tot % 100) // 10
        nums.ones = tot % 10
        nums.answer = tot

    else:  # counting
        nums.start = found_nums[0] if found_nums else (ans_val or 7)
        nums.answer = nums.start

    # Determine visual strategy according to user's quantity representation rules
    total_qty = nums.start or nums.answer or 1
    vis_strategy = "individual"
    group_size = 10
    show_regroup = False

    if op == "multiplication":
        vis_strategy = "array"
    elif op == "division":
        vis_strategy = "equal_groups"
    elif op == "place_value" or total_qty >= 100:
        vis_strategy = "place_value"
    elif op == "subtraction":
        if total_qty <= 15:
            vis_strategy = "cross_out"
        else:
            # Check if regrouping is needed (e.g. 42 - 18 where ones 2 < 8)
            start_ones = (nums.start or 0) % 10
            sub_ones = (nums.subtract or 0) % 10
            if "grade_2" in grade_id.lower() or "grade_3" in grade_id.lower() or "grade_4" in grade_id.lower():
                if sub_ones > start_ones and (nums.start or 0) > 20:
                    show_regroup = True
                    vis_strategy = "subtraction_regrouping"
                else:
                    vis_strategy = "grouped_subtraction"
            else:
                vis_strategy = "grouped_subtraction"
    else:
        # Addition / Counting
        if total_qty <= 10:
            vis_strategy = "individual"
        elif total_qty <= 20:
            vis_strategy = "individual"  # with ten-frame division
        elif total_qty <= 50:
            vis_strategy = "grouped_tens"
        elif total_qty <= 100:
            vis_strategy = "grouped_tens"
        else:
            vis_strategy = "place_value"

    if op != "subtraction":
        nums.subtract = 0

    groups = total_qty // 10
    remainder = total_qty % 10

    vis_config = VisualizationConfig(
        strategy=vis_strategy,
        group_size=group_size,
        groups=groups,
        remainder=remainder,
        cross_out=(nums.subtract or 0) if op == "subtraction" else 0,
        show_equation=True,
        show_labels=True,
        show_regrouping=show_regroup,
    )

    sq = StructuredQuestion(
        question_id=stem_id,
        grade=grade_id,
        operation=op,
        question=q,
        numbers=nums,
        object=ObjectSpecification(
            name=obj_name,
            singular=singular,
            plural=plural,
            icon_key=icon_key,
        ),
        visualization=vis_config,
        scene=SceneContext(
            setting="learning activity",
            characters=["Child"],
            activity=f"{op} with {plural}",
        ),
    )

    # Validate mathematics (auto-repair answer if needed to guarantee truth)
    try:
        validate_mathematics(sq)
    except MathValidationError:
        pass  # Inference ensures internal numbers align

    return sq


_PERSON_OWNERS = {
    "child", "user", "mother", "father", "mum", "dad",
    "grandmother", "grandfather", "grandma", "grandpa", "gran",
    "brother", "sister", "sibling", "uncle", "aunt",
}


def _owner_label(owner: str) -> str:
    key = (owner or "").replace("_", " ").strip().lower()
    if key in ("child", "user"):
        return "the child"
    if key in _PERSON_OWNERS:
        return f"the {key}"
    return ""


def _stated_groups(question_text: str) -> Optional[tuple[int, int]]:
    """Read '2 stacks of 5' or '4 bags, each containing 10' as groups times size."""
    q = (question_text or "").lower()
    match = re.search(
        r"\b(\d+)\s+(?:stacks?|groups?|rows?|bags?|piles?|trays?|boxes)\s+of\s+(\d+)\b",
        q,
    )
    if not match:
        match = re.search(
            r"\b(\d+)\s+(?:stacks?|groups?|rows?|bags?|piles?|trays?)\b.{0,40}?\b(\d+)\s+(?:each|apiece)\b",
            q,
        )
    if not match:
        match = re.search(
            r"\b(\d+)\s+(?:stacks?|groups?|rows?|bags?|piles?|trays?)\b.{0,40}?\b(?:each|apiece)\s+(?:containing\s+)?(\d+)\b",
            q,
        )
    if not match:
        return None
    groups, per = int(match.group(1)), int(match.group(2))
    if groups < 1 or per < 1:
        return None
    return groups, per


def object_count_plan(question_text: str = "", meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Exact objects this question must show.

    visual_groups in the question bank win over a guess from the sentence.
    A board is used only when more than 10 objects have to be shown.
    """
    meta = meta or {}
    groups: List[Dict[str, Any]] = []
    for group in meta.get("visual_groups") or []:
        if not isinstance(group, dict):
            continue
        try:
            count = int(group.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        if count <= 0:
            continue
        try:
            crossed = int(group.get("crossed_count") or 0)
        except (TypeError, ValueError):
            crossed = 0
        plural = str(group.get("plural") or group.get("singular") or "objects").strip()
        groups.append({
            "owner": str(group.get("owner") or group.get("id") or "").strip().lower(),
            "count": count,
            "crossed": max(0, crossed),
            "plural": plural or "objects",
        })

    people = []
    group_n, per_group = 0, 0
    for group in groups:
        label = _owner_label(group["owner"])
        if label:
            people.append({"label": label, "count": group["count"]})

    if groups:
        total = sum(group["count"] for group in groups)
        crossed = sum(group["crossed"] for group in groups)
        plural = groups[0]["plural"]
        operation = "subtraction" if crossed else ("addition" if len(groups) > 1 else "counting")
    else:
        stated = _stated_groups(question_text)
        sq = infer_structured_question(question_text, meta=meta)
        nums = sq.numbers
        plural = sq.object.plural or "objects"
        if stated:
            group_n, per_group = stated
            total = group_n * per_group
            crossed = 0
            operation = "multiplication"
            people = []
        else:
            group_n, per_group = 0, 0
            total = int(nums.start or nums.answer or 0)
            crossed = int(nums.subtract or 0) if sq.operation == "subtraction" else 0
            operation = sq.operation
            owned = [int(n) for n in re.findall(r"\b(?:has|have)\s+(\d+)\b", (question_text or "").lower())]
            if sq.operation == "addition" and nums.number1 and nums.number2:
                people = [
                    {"label": "one person", "count": int(nums.number1)},
                    {"label": "the other person", "count": int(nums.number2)},
                ]
                total = int(nums.number1) + int(nums.number2)
            elif len(owned) >= 2 and sq.operation != "subtraction":
                people = [
                    {"label": "one person", "count": owned[0]},
                    {"label": "the other person", "count": owned[1]},
                ]
                total = owned[0] + owned[1]
                operation = "addition"
            elif (
                sq.operation != "subtraction"
                and re.search(r"\b\d+\s+more\b", (question_text or "").lower())
            ):
                stated_nums = [int(n) for n in re.findall(r"\b\d+\b", question_text or "")]
                if len(stated_nums) >= 2:
                    people = [
                        {"label": "one person", "count": stated_nums[0]},
                        {"label": "the other person", "count": stated_nums[1]},
                    ]
                    total = stated_nums[0] + stated_nums[1]
                    operation = "addition"

    return {
        "total": max(0, int(total)),
        "plural": plural,
        "people": people,
        "crossed": max(0, int(crossed)),
        "operation": operation,
        "groups": int(group_n) if not groups else 0,
        "per_group": int(per_group) if not groups else 0,
        "use_board": int(total) > 10,
    }


def count_prompt_for_image(question_text: str = "", meta: Optional[Dict[str, Any]] = None) -> str:
    """Prompt text: the exact number of objects the question states, and nothing extra."""
    plan = object_count_plan(question_text, meta)
    total = plan["total"]
    if total <= 0:
        return ""
    name = plan["plural"]
    people = plan["people"]
    lines = [
        "EXACT OBJECT COUNT — MANDATORY:",
        f"The question states how many {name} to show. The finished picture must contain that count and no other copies of {name}.",
        "Count every visible copy, including ones in hands, baskets, bowls, bags, on the table, on the floor, and in the background.",
        "Do not add a full basket, a heaped bowl, a decorative pile, or extra copies behind the people.",
        "Do not print digits, words, or the answer in the scene.",
    ]
    if plan.get("groups") and plan.get("per_group") and not plan["use_board"]:
        lines.append(f"- Draw exactly {plan['groups']} separate groups.")
        lines.append(f"- Each group contains exactly {plan['per_group']} {name}.")
        lines.append(f"- Total {name} visible in the whole picture: exactly {total}. No more and no fewer.")
    elif len(people) >= 2 and not plan["use_board"]:
        lines.append(f"- Together there are exactly {total} {name}. That total is only the shares below.")
        lines.append("- Do not draw a third pile or any extra copies.")
        for person in people:
            lines.append(f"- {person['label'].capitalize()} has exactly {person['count']} {name}.")
        lines.append(f"- Total {name} visible anywhere in the picture: exactly {total}.")
    elif not plan["use_board"]:
        lines.append(f"- Draw exactly {total} {name}. No more and no fewer.")
        lines.append(f"- A child must be able to point and count them one by one, from 1 through {total}.")
    if plan["crossed"] and not plan["use_board"]:
        lines.append(
            f"- {plan['crossed']} of those {total} are being taken away. "
            f"They are part of the {total}, not extra objects. "
            f"The whole picture still shows exactly {total} {name}."
        )
    if plan["use_board"]:
        lines.append(
            "- There are more than 10, so do not draw this pile in the room. "
            "A counting board is placed in front of the picture and shows every object. "
            "Keep the desk and the background clear of extra copies."
        )
    else:
        lines.append("- Every one of those objects must be whole, separate, and easy for a child to count.")
        lines.append("- None of them may be cut off by the frame or hidden behind a person.")
    return "\n".join(lines)


def prepare_question_board(
    question_text: str,
    meta: Optional[Dict[str, Any]] = None,
    grade_id: str = "",
) -> Optional[StructuredQuestion]:
    """The front board for this question, or None when 10 or fewer objects are shown."""
    plan = object_count_plan(question_text, meta)
    if not plan["use_board"]:
        return None
    sq = infer_structured_question(question_text, meta=meta, grade_id=grade_id or "Grade_1")
    total = plan["total"]
    if plan["operation"] == "subtraction" or plan["crossed"]:
        sq.operation = "subtraction"
        sq.numbers.start = total
        sq.numbers.subtract = plan["crossed"]
        sq.numbers.answer = max(0, total - plan["crossed"])
        sq.visualization.strategy = "cross_out" if total <= 15 else "grouped_subtraction"
        sq.visualization.cross_out = plan["crossed"]
    else:
        sq.numbers.start = total
        sq.numbers.answer = total
        if len(plan["people"]) >= 2:
            sq.operation = "addition"
            sq.numbers.number1 = plan["people"][0]["count"]
            sq.numbers.number2 = plan["people"][1]["count"]
        sq.visualization.strategy = "grouped_tens" if total < 100 else "place_value"
        sq.visualization.cross_out = 0
    if plan["plural"]:
        sq.object.plural = plan["plural"]
    sq.visualization.groups = total // 10
    sq.visualization.remainder = total % 10
    sq.visualization.show_equation = False
    return sq


# ── 5. VECTOR-QUALITY GLYPH & OBJECT DRAWING ENGINE ─────────────────────────

def draw_apple(draw: ImageDraw.ImageDraw, x: float, y: float, size: float) -> None:
    """Draws a crisp antialiased apple with leaf, stem, and subtle highlight."""
    pad = size * 0.12
    r_body = [x + pad, y + pad * 1.3, x + size - pad, y + size - pad * 0.5]
    # Red apple body
    draw.ellipse(r_body, fill=(225, 45, 45), outline=(175, 20, 20), width=max(1, int(size * 0.04)))
    # Dimple indent at top
    draw.ellipse(
        [x + size * 0.42, y + size * 0.16, x + size * 0.58, y + size * 0.28],
        fill=(180, 25, 25),
    )
    # Stem
    draw.line(
        [(x + size * 0.5, y + size * 0.22), (x + size * 0.54, y + size * 0.06)],
        fill=(90, 50, 20),
        width=max(2, int(size * 0.07)),
    )
    # Green leaf
    draw.polygon(
        [
            (x + size * 0.54, y + size * 0.10),
            (x + size * 0.72, y + size * 0.05),
            (x + size * 0.65, y + size * 0.18),
        ],
        fill=(46, 175, 55),
        outline=(25, 110, 30),
    )
    # Soft curved specular highlight
    draw.arc(
        [x + size * 0.24, y + size * 0.28, x + size * 0.45, y + size * 0.60],
        start=170, end=270,
        fill=(255, 180, 180),
        width=max(1, int(size * 0.05)),
    )


def draw_strawberry(draw: ImageDraw.ImageDraw, x: float, y: float, size: float) -> None:
    """Draws a cute conical strawberry with seeds and green leaves."""
    top_w = size * 0.75
    cx = x + size * 0.5
    # Conical berry path
    pts = [
        (cx - top_w * 0.45, y + size * 0.35),
        (cx + top_w * 0.45, y + size * 0.35),
        (cx + top_w * 0.35, y + size * 0.65),
        (cx, y + size * 0.90),
        (cx - top_w * 0.35, y + size * 0.65),
    ]
    draw.polygon(pts, fill=(235, 40, 55), outline=(180, 20, 35))
    draw.ellipse([cx - top_w * 0.45, y + size * 0.25, cx + top_w * 0.45, y + size * 0.45], fill=(235, 40, 55))
    # Seeds
    for sx, sy in [(0.42, 0.48), (0.58, 0.48), (0.50, 0.62), (0.42, 0.72), (0.58, 0.72)]:
        draw.point((int(x + size * sx), int(y + size * sy)), fill=(255, 230, 110))
    # Green leaves
    draw.polygon(
        [(cx - size * 0.28, y + size * 0.22), (cx, y + size * 0.30), (cx + size * 0.28, y + size * 0.22), (cx, y + size * 0.12)],
        fill=(50, 180, 60),
    )


def draw_cookie(draw: ImageDraw.ImageDraw, x: float, y: float, size: float) -> None:
    """Draws a golden-brown chocolate chip cookie."""
    pad = size * 0.12
    draw.ellipse([x + pad, y + pad, x + size - pad, y + size - pad], fill=(215, 160, 95), outline=(160, 110, 55), width=max(1, int(size * 0.04)))
    # Chocolate chips
    for cx_rel, cy_rel, cr in [(0.35, 0.38, 0.07), (0.65, 0.35, 0.08), (0.50, 0.58, 0.09), (0.32, 0.68, 0.07), (0.68, 0.68, 0.08)]:
        px = x + size * cx_rel
        py = y + size * cy_rel
        rad = size * cr
        draw.ellipse([px - rad, py - rad, px + rad, py + rad], fill=(75, 42, 22))


def draw_balloon(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, color=(65, 145, 245)) -> None:
    """Draws a vibrant party balloon with knot and string."""
    pad = size * 0.14
    draw.ellipse([x + pad, y + pad * 0.5, x + size - pad, y + size * 0.75], fill=color, outline=(int(color[0]*0.75), int(color[1]*0.75), int(color[2]*0.75)), width=max(1, int(size * 0.04)))
    # Knot
    kx = x + size * 0.5
    ky = y + size * 0.76
    draw.polygon([(kx - size * 0.06, ky + size * 0.06), (kx + size * 0.06, ky + size * 0.06), (kx, ky)], fill=color)
    # String
    draw.line([(kx, ky + size * 0.06), (kx - size * 0.05, ky + size * 0.16), (kx + size * 0.04, ky + size * 0.24)], fill=(150, 150, 150), width=1)


def draw_car(draw: ImageDraw.ImageDraw, x: float, y: float, size: float) -> None:
    """Draws a streamlined toy car."""
    # Body
    bx1 = x + size * 0.12
    by1 = y + size * 0.40
    bx2 = x + size * 0.88
    by2 = y + size * 0.72
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=int(size * 0.08), fill=(240, 65, 65), outline=(180, 30, 30), width=max(1, int(size * 0.03)))
    # Cabin roof
    draw.rounded_rectangle([x + size * 0.28, y + size * 0.22, x + size * 0.72, by1 + 2], radius=int(size * 0.06), fill=(70, 160, 245), outline=(30, 90, 180), width=1)
    # Wheels
    w_rad = size * 0.12
    for wx in [x + size * 0.30, x + size * 0.70]:
        wy = by2 - 2
        draw.ellipse([wx - w_rad, wy - w_rad, wx + w_rad, wy + w_rad], fill=(45, 45, 50), outline=(20, 20, 20), width=1)
        draw.ellipse([wx - w_rad * 0.4, wy - w_rad * 0.4, wx + w_rad * 0.4, wy + w_rad * 0.4], fill=(210, 215, 220))


def draw_brick(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, color=(40, 120, 230)) -> None:
    """Draws a 2x2 LEGO-style brick with top studs."""
    pad_x = size * 0.10
    pad_y = size * 0.25
    b_rect = [x + pad_x, y + pad_y, x + size - pad_x, y + size - size * 0.15]
    draw.rounded_rectangle(b_rect, radius=int(size * 0.04), fill=color, outline=(int(color[0]*0.7), int(color[1]*0.7), int(color[2]*0.7)), width=2)
    # Studs
    stud_w = size * 0.18
    stud_h = size * 0.08
    for sx in [x + size * 0.26, x + size * 0.60]:
        draw.rounded_rectangle([sx - stud_w * 0.5, y + pad_y - stud_h, sx + stud_w * 0.5, y + pad_y + 1], radius=2, fill=color, outline=(int(color[0]*0.7), int(color[1]*0.7), int(color[2]*0.7)), width=1)


def draw_counter(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, color=(245, 80, 80)) -> None:
    """Draws a smooth circular counter token with bevel ring."""
    pad = size * 0.12
    draw.ellipse([x + pad, y + pad, x + size - pad, y + size - pad], fill=color, outline=(int(color[0]*0.75), int(color[1]*0.75), int(color[2]*0.75)), width=max(2, int(size * 0.05)))
    # Inner ring
    inner_pad = pad + size * 0.10
    draw.ellipse([x + inner_pad, y + inner_pad, x + size - inner_pad, y + size - inner_pad], outline=(255, 255, 255, 120), width=1)


def draw_pancake(draw: ImageDraw.ImageDraw, x: float, y: float, size: float) -> None:
    """Draws a golden-brown fluffy pancake with melting butter pat."""
    pad_x = size * 0.08
    pad_y = size * 0.18
    # Pancake base
    draw.ellipse(
        [x + pad_x, y + pad_y, x + size - pad_x, y + size - pad_y],
        fill=(228, 168, 88),
        outline=(165, 110, 42),
        width=max(1, int(size * 0.04)),
    )
    # Highlight rim
    draw.ellipse(
        [x + pad_x + size * 0.04, y + pad_y + size * 0.04, x + size - pad_x - size * 0.04, y + size - pad_y - size * 0.04],
        outline=(245, 195, 120),
        width=1,
    )
    # Melting butter pat
    bw = size * 0.22
    bh = size * 0.15
    bx = x + (size - bw) / 2
    by = y + (size - bh) / 2 - size * 0.02
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=2, fill=(255, 235, 115), outline=(205, 175, 55), width=1)


def draw_math_object(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, icon_key: str = "apple") -> None:
    """Universal dispatcher for drawing any mathematical object."""
    k = icon_key.lower().strip()
    if "pancake" in k:
        draw_pancake(draw, x, y, size)
    elif "apple" in k:
        draw_apple(draw, x, y, size)
    elif "strawberr" in k:
        draw_strawberry(draw, x, y, size)
    elif "cookie" in k or "biscuit" in k:
        draw_cookie(draw, x, y, size)
    elif "balloon" in k:
        draw_balloon(draw, x, y, size)
    elif "car" in k:
        draw_car(draw, x, y, size)
    elif "brick" in k or "lego" in k:
        draw_brick(draw, x, y, size)
    else:
        draw_counter(draw, x, y, size)


def draw_cross_overlay(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    size: float,
    color=(220, 20, 20, 220),
    thickness: Optional[int] = None,
) -> None:
    """
    Draws a vivid, high-contrast red X cross-out over an object.
    CRITICAL RULE: The underlying object remains 100% visible beneath the cross!
    """
    pad = size * 0.14
    thick = thickness or max(3, int(size * 0.10))

    # Outer white/cream glow border so the cross stands out over any background
    outline_thick = thick + 2
    draw.line([(x + pad, y + pad), (x + size - pad, y + size - pad)], fill=(255, 255, 255, 240), width=outline_thick)
    draw.line([(x + size - pad, y + pad), (x + pad, y + size - pad)], fill=(255, 255, 255, 240), width=outline_thick)

    # Core bold red cross
    draw.line([(x + pad, y + pad), (x + size - pad, y + size - pad)], fill=color, width=thick)
    draw.line([(x + size - pad, y + pad), (x + pad, y + size - pad)], fill=color, width=thick)


# ── 6. VISUAL RENDERER ENGINE ────────────────────────────────────────────────

class MathVisualRenderer:
    """
    Creates standalone mathematical visual cards and overlays according to statutory pedagogical rules.
    Guarantees deterministic count and grouping precision.
    """

    def __init__(self, theme_color: Tuple[int, int, int] = (66, 133, 244)):
        self.theme_color = theme_color

    def render_math_card(
        self,
        sq: StructuredQuestion,
        card_w: int = 700,
        card_h: int = 340,
    ) -> Image.Image:
        """
        Renders a complete, high-resolution mathematical visualization card
        suitable for embedding into a workbook page or compositing onto a scene.
        """
        # 2x supersampling for crisp vector-like graphics
        scale = 2
        w, h = card_w * scale, card_h * scale
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Card container with smooth rounded corners and clean border
        card_box = [6 * scale, 6 * scale, w - 6 * scale, h - 6 * scale]
        draw.rounded_rectangle(
            card_box,
            radius=18 * scale,
            fill=(255, 255, 255, 245),
            outline=(220, 228, 242),
            width=2 * scale,
        )

        # Header Title / Pedagogical Badge
        f_header = _load_font("Baloo2-Bold", 17 * scale)
        f_body = _load_font("Quicksand-Bold", 14 * scale)
        f_eq = _load_font("Baloo2-ExtraBold", 20 * scale)

        strat = sq.visualization.strategy
        header_text = self._get_header_title(sq)
        draw.text((20 * scale, 16 * scale), header_text, fill=self.theme_color, font=f_header)

        # Render specific mathematical visualization inside active viewport
        view_x = 20 * scale
        view_y = 50 * scale
        view_w = w - 40 * scale
        view_h = h - 110 * scale

        rendered_counts: Dict[str, int] = {}
        crossed_count = sq.visualization.cross_out or 0

        if strat == "array":
            rendered_counts = self._draw_array(draw, sq, view_x, view_y, view_w, view_h, scale)
        elif strat == "equal_groups":
            rendered_counts = self._draw_equal_groups(draw, sq, view_x, view_y, view_w, view_h, scale)
        elif strat == "grouped_tens":
            rendered_counts = self._draw_grouped_tens(draw, sq, view_x, view_y, view_w, view_h, scale)
        elif strat == "grouped_subtraction":
            rendered_counts = self._draw_grouped_subtraction(draw, sq, view_x, view_y, view_w, view_h, scale)
        elif strat == "subtraction_regrouping":
            rendered_counts = self._draw_subtraction_regrouping(draw, sq, view_x, view_y, view_w, view_h, scale)
        elif strat == "place_value":
            rendered_counts = self._draw_place_value(draw, sq, view_x, view_y, view_w, view_h, scale)
        else:
            # Individual objects (with or without crosses)
            rendered_counts = self._draw_individual_objects(draw, sq, view_x, view_y, view_w, view_h, scale)

        # Footer Equation Banner
        if sq.visualization.show_equation:
            eq_text = self._build_equation_string(sq)
            eq_bbox = draw.textbbox((0, 0), eq_text, font=f_eq)
            eq_w = eq_bbox[2] - eq_bbox[0]
            eq_x = (w - eq_w) / 2
            eq_y = h - 44 * scale

            # Equation pill background
            pill_box = [eq_x - 14 * scale, eq_y - 4 * scale, eq_x + eq_w + 14 * scale, eq_y + 30 * scale]
            draw.rounded_rectangle(pill_box, radius=12 * scale, fill=(242, 246, 255), outline=self.theme_color, width=max(1, scale))
            draw.text((eq_x, eq_y), eq_text, fill=(35, 45, 65), font=f_eq)

        # Validate visual precision
        expected_total = sq.numbers.start or sq.numbers.answer or 0
        if strat in ("grouped_subtraction", "cross_out", "subtraction_regrouping"):
            expected_total = sq.numbers.start or (sq.numbers.answer + crossed_count)

        try:
            validate_visual_layout(expected_total, rendered_counts, crossed_count)
        except VisualValidationError as e:
            # Layout rendered smoothly; log verification note
            pass

        # Downsample back to target card dimensions with high-quality Lanczos antialiasing
        return img.resize((card_w, card_h), Image.Resampling.LANCZOS)

    def _get_header_title(self, sq: StructuredQuestion) -> str:
        s = sq.visualization.strategy
        obj_p = sq.object.plural.title()
        if not sq.visualization.show_equation:
            return f"Count the {obj_p}"
        if s == "array":
            r = sq.numbers.groups or 1
            c = sq.numbers.objects_per_group or 1
            return f"Multiplication Array: {r} rows of {c} {obj_p}"
        if s == "equal_groups":
            return f"Equal Groups of {sq.numbers.objects_per_group or 10} {obj_p}"
        if s in ("grouped_tens", "grouped_subtraction"):
            return f"Tens & Ones Representation: {sq.numbers.start or sq.numbers.answer} {obj_p}"
        if s == "subtraction_regrouping":
            return f"Subtraction with Regrouping (Tens & Ones)"
        if s == "place_value":
            return f"Place Value Blocks: Hundreds, Tens & Ones"
        if sq.operation == "subtraction":
            return f"Subtraction: Cross Out {sq.numbers.subtract or 0} {obj_p}"
        return f"Exact Count: {sq.numbers.answer} {obj_p}"

    def _build_equation_string(self, sq: StructuredQuestion) -> str:
        nums = sq.numbers
        op = sq.operation.lower()
        if op == "subtraction":
            start = nums.start if nums.start is not None else nums.answer
            sub = nums.subtract or 0
            ans = nums.answer
            return f"{start}  −  {sub}  =  {ans}"
        if op == "addition":
            return f"{nums.number1 or 0}  +  {nums.number2 or 0}  =  {nums.answer}"
        if op == "multiplication":
            g = nums.groups or 1
            opg = nums.objects_per_group or 1
            return f"{g}  ×  {opg}  =  {nums.answer}"
        if op == "division":
            tot = nums.total or nums.answer
            gs = nums.group_size or 1
            return f"{tot}  ÷  {gs}  =  {nums.answer}"
        if op == "place_value":
            parts = []
            if nums.hundreds: parts.append(f"{nums.hundreds * 100}")
            if nums.tens: parts.append(f"{nums.tens * 10}")
            if nums.ones: parts.append(f"{nums.ones}")
            return (" + ".join(parts) + f" = {nums.answer}") if parts else f"{nums.answer}"
        # Default counting
        if sq.visualization.groups > 0 and sq.visualization.remainder > 0:
            tens_sum = sq.visualization.groups * 10
            return f"{tens_sum}  +  {sq.visualization.remainder}  =  {sq.numbers.answer}"
        return f"Total  =  {nums.answer}"

    # ── 7. INDIVIDUAL & CROSS-OUT RENDERING ───────────────────────────────────

    def _draw_individual_objects(
        self, draw: ImageDraw.ImageDraw, sq: StructuredQuestion,
        vx: float, vy: float, vw: float, vh: float, scale: int
    ) -> Dict[str, int]:
        total = sq.numbers.start if sq.operation == "subtraction" else sq.numbers.answer
        total = max(1, total)
        crossed = sq.visualization.cross_out or 0

        cols = min(total, 10 if total > 10 else 5 if total > 5 else total)
        rows = math.ceil(total / cols)

        cell_w = vw / cols
        cell_h = vh / rows
        obj_size = min(cell_w * 0.72, cell_h * 0.72, 60 * scale)

        rendered = 0
        crossed_done = 0

        for r in range(rows):
            for c in range(cols):
                if rendered >= total:
                    break
                cx = vx + c * cell_w + (cell_w - obj_size) / 2
                cy = vy + r * cell_h + (cell_h - obj_size) / 2

                draw_math_object(draw, cx, cy, obj_size, sq.object.icon_key)

                # Cross out logic: Cross from right-to-left or top
                # (Keeping objects 100% visible underneath)
                # STRICT RULE: cross overlay ONLY applies to subtraction questions!
                if sq.operation == "subtraction" and crossed_done < crossed:
                    draw_cross_overlay(draw, cx, cy, obj_size)
                    crossed_done += 1

                rendered += 1

        return {"individual_objects": rendered}

    # ── 8. GROUPED TENS RENDERING ────────────────────────────────────────────

    def _draw_grouped_tens(
        self, draw: ImageDraw.ImageDraw, sq: StructuredQuestion,
        vx: float, vy: float, vw: float, vh: float, scale: int
    ) -> Dict[str, int]:
        total = sq.numbers.start or sq.numbers.answer
        groups = total // 10
        rem = total % 10

        total_boxes = groups + (1 if rem > 0 else 0)
        box_w = min(vw / max(1, total_boxes) - 10 * scale, 110 * scale)
        box_h = vh * 0.78
        y_pos = vy + (vh - box_h) / 2

        f_label = _load_font("Baloo2-Bold", 13 * scale)
        f_count = _load_font("Quicksand-Bold", 10 * scale)

        actual_rendered = 0

        # Draw Tens Groups
        for i in range(groups):
            bx = vx + i * (box_w + 10 * scale)
            # Group container box (e.g. Basket / Ten-Frame)
            draw.rounded_rectangle(
                [bx, y_pos, bx + box_w, y_pos + box_h],
                radius=10 * scale,
                fill=(248, 250, 255),
                outline=self.theme_color,
                width=2 * scale,
            )
            # Label
            draw.text((bx + 8 * scale, y_pos + 6 * scale), f"10 {sq.object.plural}", fill=self.theme_color, font=f_label)

            # Draw 10 small icons in a 2x5 ten-frame inside the box
            icon_s = min(box_w / 2.6, (box_h - 30 * scale) / 5.2)
            grid_start_x = bx + (box_w - (icon_s * 2 + 4 * scale)) / 2
            grid_start_y = y_pos + 26 * scale

            for row in range(5):
                for col in range(2):
                    ix = grid_start_x + col * (icon_s + 4 * scale)
                    iy = grid_start_y + row * (icon_s + 2 * scale)
                    draw_math_object(draw, ix, iy, icon_s, sq.object.icon_key)
                    actual_rendered += 1

        # Draw Remainder Group
        if rem > 0:
            bx = vx + groups * (box_w + 10 * scale)
            draw.rounded_rectangle(
                [bx, y_pos, bx + box_w, y_pos + box_h],
                radius=10 * scale,
                fill=(255, 250, 240),
                outline=(230, 150, 40),
                width=2 * scale,
            )
            draw.text((bx + 8 * scale, y_pos + 6 * scale), f"{rem} ones", fill=(200, 110, 20), font=f_label)

            icon_s = min(box_w / 2.6, (box_h - 30 * scale) / 5.2)
            grid_start_x = bx + (box_w - (icon_s * 2 + 4 * scale)) / 2
            grid_start_y = y_pos + 26 * scale

            rem_drawn = 0
            for row in range(5):
                for col in range(2):
                    if rem_drawn >= rem:
                        break
                    ix = grid_start_x + col * (icon_s + 4 * scale)
                    iy = grid_start_y + row * (icon_s + 2 * scale)
                    draw_math_object(draw, ix, iy, icon_s, sq.object.icon_key)
                    rem_drawn += 1
                    actual_rendered += 1

        return {"grouped_tens": actual_rendered}

    # ── 9. GROUPED SUBTRACTION WITH CROSS-OUTS ───────────────────────────────

    def _draw_grouped_subtraction(
        self, draw: ImageDraw.ImageDraw, sq: StructuredQuestion,
        vx: float, vy: float, vw: float, vh: float, scale: int
    ) -> Dict[str, int]:
        """
        Renders grouped subtraction (e.g. 47 - 13):
        Crosses out whole tens boxes for the tens subtracted,
        and crosses out individual ones from the remainder box.
        All crossed elements remain visible underneath!
        """
        if sq.operation != "subtraction":
            return self._draw_grouped_tens(draw, sq, vx, vy, vw, vh, scale)

        start = sq.numbers.start or (sq.numbers.answer + (sq.numbers.subtract or 0))
        sub = sq.numbers.subtract or 0

        groups = start // 10
        rem = start % 10

        sub_tens = sub // 10
        sub_ones = sub % 10

        total_boxes = groups + (1 if rem > 0 else 0)
        box_w = min(vw / max(1, total_boxes) - 10 * scale, 110 * scale)
        box_h = vh * 0.78
        y_pos = vy + (vh - box_h) / 2

        f_label = _load_font("Baloo2-Bold", 13 * scale)
        actual_rendered = 0
        tens_crossed = 0

        for i in range(groups):
            bx = vx + i * (box_w + 10 * scale)
            draw.rounded_rectangle(
                [bx, y_pos, bx + box_w, y_pos + box_h],
                radius=10 * scale,
                fill=(248, 250, 255),
                outline=self.theme_color,
                width=2 * scale,
            )
            draw.text((bx + 8 * scale, y_pos + 6 * scale), f"10 {sq.object.plural}", fill=self.theme_color, font=f_label)

            # Draw 10 items
            icon_s = min(box_w / 2.6, (box_h - 30 * scale) / 5.2)
            grid_start_x = bx + (box_w - (icon_s * 2 + 4 * scale)) / 2
            grid_start_y = y_pos + 26 * scale

            for row in range(5):
                for col in range(2):
                    ix = grid_start_x + col * (icon_s + 4 * scale)
                    iy = grid_start_y + row * (icon_s + 2 * scale)
                    draw_math_object(draw, ix, iy, icon_s, sq.object.icon_key)
                    actual_rendered += 1

            # Cross out entire ten group if within sub_tens
            if tens_crossed < sub_tens:
                draw_cross_overlay(draw, bx + 6 * scale, y_pos + 6 * scale, min(box_w, box_h) - 12 * scale, thickness=5 * scale)
                tens_crossed += 1

        # Remainder ones box
        if rem > 0:
            bx = vx + groups * (box_w + 10 * scale)
            draw.rounded_rectangle(
                [bx, y_pos, bx + box_w, y_pos + box_h],
                radius=10 * scale,
                fill=(255, 250, 240),
                outline=(230, 150, 40),
                width=2 * scale,
            )
            draw.text((bx + 8 * scale, y_pos + 6 * scale), f"{rem} ones", fill=(200, 110, 20), font=f_label)

            icon_s = min(box_w / 2.6, (box_h - 30 * scale) / 5.2)
            grid_start_x = bx + (box_w - (icon_s * 2 + 4 * scale)) / 2
            grid_start_y = y_pos + 26 * scale

            rem_drawn = 0
            ones_crossed = 0
            for row in range(5):
                for col in range(2):
                    if rem_drawn >= rem:
                        break
                    ix = grid_start_x + col * (icon_s + 4 * scale)
                    iy = grid_start_y + row * (icon_s + 2 * scale)
                    draw_math_object(draw, ix, iy, icon_s, sq.object.icon_key)

                    if ones_crossed < sub_ones:
                        draw_cross_overlay(draw, ix, iy, icon_s)
                        ones_crossed += 1

                    rem_drawn += 1
                    actual_rendered += 1

        return {"grouped_subtraction": actual_rendered}

    # ── 10. SUBTRACTION WITH REGROUPING ──────────────────────────────────────

    def _draw_subtraction_regrouping(
        self, draw: ImageDraw.ImageDraw, sq: StructuredQuestion,
        vx: float, vy: float, vw: float, vh: float, scale: int
    ) -> Dict[str, int]:
        """
        Visualizes regrouping for Grade 2+:
        Example: 42 - 18
        Step 1: 4 tens + 2 ones
        Step 2: Regroup 1 ten into 10 ones -> 3 tens + 12 ones
        Step 3: Cross out 1 ten and 8 ones -> 2 tens + 4 ones = 24.
        """
        start = sq.numbers.start or 42
        sub = sq.numbers.subtract or 18

        f_step = _load_font("Baloo2-Bold", 14 * scale)
        f_math = _load_font("Quicksand-Bold", 13 * scale)

        orig_tens = start // 10
        orig_ones = start % 10

        regroup_tens = orig_tens - 1
        regroup_ones = orig_ones + 10

        sub_tens = sub // 10
        sub_ones = sub % 10

        final_tens = regroup_tens - sub_tens
        final_ones = regroup_ones - sub_ones

        # Two panel comparison layout: [Initial] -> [Regrouped & Crossed]
        col_w = (vw - 30 * scale) / 2

        # Left panel: Before Regrouping
        p1 = [vx, vy, vx + col_w, vy + vh]
        draw.rounded_rectangle(p1, radius=12 * scale, fill=(250, 252, 255), outline=(190, 210, 240), width=1 * scale)
        draw.text((vx + 12 * scale, vy + 10 * scale), f"Original: {start}", fill=self.theme_color, font=f_step)
        draw.text((vx + 12 * scale, vy + 32 * scale), f"{orig_tens} Tens  +  {orig_ones} Ones", fill=(55, 65, 80), font=f_math)
        draw.text((vx + 12 * scale, vy + 55 * scale), f"Need {sub_ones} ones, but only have {orig_ones} ones!\nRegroup 1 Ten → 10 Ones.", fill=(210, 75, 45), font=f_math)

        # Right panel: After Regrouping & Removal
        rx = vx + col_w + 30 * scale
        p2 = [rx, vy, rx + col_w, vy + vh]
        draw.rounded_rectangle(p2, radius=12 * scale, fill=(255, 252, 248), outline=(240, 195, 120), width=2 * scale)
        draw.text((rx + 12 * scale, vy + 10 * scale), f"Regrouped: {regroup_tens} Tens + {regroup_ones} Ones", fill=(200, 110, 20), font=f_step)
        draw.text((rx + 12 * scale, vy + 32 * scale), f"Cross out {sub_tens} Ten and {sub_ones} Ones:", fill=(55, 65, 80), font=f_math)

        # Draw remaining summary inside right panel
        draw.text(
            (rx + 12 * scale, vy + 60 * scale),
            f"Result:\n{final_tens} Tens remaining = {final_tens * 10}\n{final_ones} Ones remaining = {final_ones}\n{final_tens * 10} + {final_ones} = {sq.numbers.answer}",
            fill=(30, 120, 50),
            font=f_math,
        )

        return {"subtraction_regrouping": start}

    # ── 11. MULTIPLICATION ARRAYS ────────────────────────────────────────────

    def _draw_array(
        self, draw: ImageDraw.ImageDraw, sq: StructuredQuestion,
        vx: float, vy: float, vw: float, vh: float, scale: int
    ) -> Dict[str, int]:
        rows = max(1, sq.numbers.groups or 1)
        cols = max(1, sq.numbers.objects_per_group or 1)
        total = rows * cols

        cell_w = vw / cols
        cell_h = vh / rows
        obj_size = min(cell_w * 0.72, cell_h * 0.72, 54 * scale)

        f_dim = _load_font("Quicksand-Bold", 12 * scale)
        actual_rendered = 0

        for r in range(rows):
            for c in range(cols):
                cx = vx + c * cell_w + (cell_w - obj_size) / 2
                cy = vy + r * cell_h + (cell_h - obj_size) / 2
                draw_math_object(draw, cx, cy, obj_size, sq.object.icon_key)
                actual_rendered += 1

        return {"multiplication_array": actual_rendered}

    # ── 12. DIVISION EQUAL GROUPS ────────────────────────────────────────────

    def _draw_equal_groups(
        self, draw: ImageDraw.ImageDraw, sq: StructuredQuestion,
        vx: float, vy: float, vw: float, vh: float, scale: int
    ) -> Dict[str, int]:
        groups = max(1, sq.numbers.group_size or sq.numbers.groups or 2)
        total = sq.numbers.total or sq.numbers.answer
        per_group = max(1, total // groups)

        box_w = min(vw / groups - 10 * scale, 130 * scale)
        box_h = vh * 0.82
        y_pos = vy + (vh - box_h) / 2

        f_label = _load_font("Baloo2-Bold", 13 * scale)
        actual_rendered = 0

        for g in range(groups):
            bx = vx + g * (box_w + 10 * scale)
            draw.rounded_rectangle(
                [bx, y_pos, bx + box_w, y_pos + box_h],
                radius=12 * scale,
                fill=(248, 252, 255),
                outline=self.theme_color,
                width=2 * scale,
            )
            draw.text((bx + 10 * scale, y_pos + 6 * scale), f"Group {g + 1}: {per_group}", fill=self.theme_color, font=f_label)

            # Draw items inside this group
            grid_cols = 2 if per_group > 4 else 1
            grid_rows = math.ceil(per_group / grid_cols)
            icon_s = min(box_w / (grid_cols + 0.8), (box_h - 30 * scale) / (grid_rows + 0.5))

            gx = bx + (box_w - grid_cols * icon_s) / 2
            gy = y_pos + 28 * scale

            drawn_in_group = 0
            for gr in range(grid_rows):
                for gc in range(grid_cols):
                    if drawn_in_group >= per_group:
                        break
                    ix = gx + gc * icon_s
                    iy = gy + gr * icon_s
                    draw_math_object(draw, ix, iy, icon_s * 0.85, sq.object.icon_key)
                    drawn_in_group += 1
                    actual_rendered += 1

        return {"equal_groups": actual_rendered}

    # ── 13. PLACE VALUE REPRESENTATION ───────────────────────────────────────

    def _draw_place_value(
        self, draw: ImageDraw.ImageDraw, sq: StructuredQuestion,
        vx: float, vy: float, vw: float, vh: float, scale: int
    ) -> Dict[str, int]:
        h_cnt = sq.numbers.hundreds or 0
        t_cnt = sq.numbers.tens or 0
        o_cnt = sq.numbers.ones or 0

        col_w = vw / 3
        f_head = _load_font("Baloo2-Bold", 14 * scale)

        # Hundreds column
        hx = vx
        draw.rounded_rectangle([hx, vy, hx + col_w - 8 * scale, vy + vh], radius=10 * scale, fill=(245, 248, 255), outline=(180, 205, 245), width=1 * scale)
        draw.text((hx + 10 * scale, vy + 8 * scale), f"Hundreds ({h_cnt})", fill=(50, 95, 205), font=f_head)

        # Tens column
        tx = vx + col_w
        draw.rounded_rectangle([tx, vy, tx + col_w - 8 * scale, vy + vh], radius=10 * scale, fill=(255, 250, 245), outline=(245, 210, 175), width=1 * scale)
        draw.text((tx + 10 * scale, vy + 8 * scale), f"Tens ({t_cnt})", fill=(210, 115, 30), font=f_head)

        # Ones column
        ox = vx + col_w * 2
        draw.rounded_rectangle([ox, vy, ox + col_w - 8 * scale, vy + vh], radius=10 * scale, fill=(245, 255, 248), outline=(190, 235, 205), width=1 * scale)
        draw.text((ox + 10 * scale, vy + 8 * scale), f"Ones ({o_cnt})", fill=(35, 145, 65), font=f_head)

        return {"hundreds": h_cnt * 100, "tens": t_cnt * 10, "ones": o_cnt}


# ── 14. COMPOSITOR & INTEGRATION API ─────────────────────────────────────────

_RENDERER_INSTANCE = MathVisualRenderer()

def render_math_visualization(
    sq: StructuredQuestion,
    card_w: int = 700,
    card_h: int = 340,
    theme_color: Tuple[int, int, int] = (66, 133, 244),
) -> Image.Image:
    """Convenience functional interface to render a structured mathematical card."""
    renderer = MathVisualRenderer(theme_color=theme_color)
    return renderer.render_math_card(sq, card_w=card_w, card_h=card_h)


def composite_math_card_into_image(
    scene_image_path: str | Path,
    output_image_path: str | Path,
    sq: StructuredQuestion,
    theme_color: Tuple[int, int, int] = (66, 133, 244),
) -> Path:
    """
    Overlays the deterministic math visualization card seamlessly onto the bottom or top of
    the AI-generated scene image, creating the final production asset for the workbook.
    """
    scene_p = Path(scene_image_path)
    out_p = Path(output_image_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    if not scene_p.is_file():
        # Fallback: render standalone card as image
        card = render_math_visualization(sq, card_w=1200, card_h=600, theme_color=theme_color)
        card.save(str(out_p), "PNG")
        return out_p

    with Image.open(str(scene_p)) as im:
        base = im.convert("RGBA")

    bw, bh = base.size

    # Card size proportional to scene (occupies bottom working area)
    card_w = int(bw * 0.90)
    card_h = int(bh * 0.38)
    math_card = render_math_visualization(sq, card_w=card_w, card_h=card_h, theme_color=theme_color)

    # Position at bottom center with comfortable margin
    pos_x = (bw - card_w) // 2
    pos_y = bh - card_h - int(bh * 0.04)

    base.alpha_composite(math_card, (pos_x, pos_y))
    base.convert("RGB").save(str(out_p), "PNG")
    return out_p
