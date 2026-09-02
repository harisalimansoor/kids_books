#!/usr/bin/env python3
"""Write question.txt for grade_1 addition stems still missing from the template bank."""
from __future__ import annotations

import re
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent
BANK = PIPELINE / "Question clusters for grade 1" / "addition.txt"
TEMPLATES = PIPELINE / "question_templates" / "grade_1" / "addition"
INDEX = TEMPLATES / "remaining_for_template_images.txt"

ROLE_MAP = {
    "mother_name": "mother",
    "father_name": "father",
    "grandmother_name": "grandmother",
    "grandfather_name": "grandfather",
    "uncle_name": "uncle",
    "aunt_name": "aunt",
    "sibling_name": "sibling",
    "brother_name": "brother",
    "sister_name": "sister",
}
PRON = {
    "mother": "her",
    "father": "him",
    "grandmother": "her",
    "grandfather": "him",
    "uncle": "him",
    "aunt": "her",
    "sibling": "them",
    "brother": "him",
    "sister": "her",
}
PLURAL = {
    "marble": "marbles",
    "pencil": "pencils",
    "sweet": "sweets",
    "shell": "shells",
    "apple": "apples",
    "book": "books",
    "mango": "mangoes",
    "flower": "flowers",
    "balloon": "balloons",
    "cookie": "cookies",
    "coin": "coins",
    "crayon": "crayons",
    "block": "blocks",
    "sticker": "stickers",
    "ball": "balls",
}

COUNT_PAT = re.compile(
    r"\{(user_name|" + "|".join(ROLE_MAP.keys()) + r")\}\s+has\s+(\d+)\s+(.+?)\s+in front of",
    re.I,
)


def norm_object(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw.strip().lower())
    s = re.sub(r"^(colourful|colorful|shiny|big|small|long|golden)\s+", "", s)
    s = s.split(" in front")[0].split(" on ")[0].split(" and ")[0].strip()
    if s.endswith("s"):
        return s.replace(" ", "_")
    return PLURAL.get(s, s + "s").replace(" ", "_")


SINGULAR = {
    "cookies": "cookie",
    "apples": "apple",
    "marbles": "marble",
    "mangoes": "mango",
    "potatoes": "potato",
    "tomatoes": "tomato",
    "cherries": "cherry",
    "berries": "berry",
    "peaches": "peach",
    "pears": "pear",
    "plums": "plum",
    "oranges": "orange",
    "grapes": "grape",
    "lemons": "lemon",
    "carrots": "carrot",
    "flowers": "flower",
    "balloons": "balloon",
    "books": "book",
    "sweets": "sweet",
    "shells": "shell",
    "pencils": "pencil",
    "stickers": "sticker",
    "blocks": "block",
    "coins": "coin",
    "crayons": "crayon",
    "biscuits": "biscuit",
    "breadsticks": "breadstick",
}


def display_object(obj_id: str, n: int) -> str:
    label = obj_id.replace("_", " ")
    if n == 1:
        if label in SINGULAR:
            return SINGULAR[label]
        if label.endswith("ies"):
            return label[:-3] + "y"
        if label.endswith("s"):
            return label[:-1]
        return label
    return label


def format_question(child_n: int, adult_n: int, role: str, obj_id: str) -> str:
    obj_child = display_object(obj_id, child_n)
    obj_adult = display_object(obj_id, adult_n)
    obj_total = display_object(obj_id, child_n + adult_n)
    role_name = f"{{{role}_name}}"
    pron = PRON[role]
    return (
        f"Look at the picture! {{user_name}} has {child_n} {obj_child} in front of {{user_name}}, "
        f"and {role_name} has {adult_n} {obj_adult} in front of {pron}. "
        f"How many {obj_total} are there altogether?"
    )


def _stem_needs_image(stem_dir: Path) -> bool:
    if not stem_dir.is_dir():
        return True
    if not (stem_dir / "question.txt").is_file():
        return True
    pngs = list(stem_dir.glob("*.png"))
    if not pngs:
        return True
    meta_path = stem_dir / "meta.json"
    if not meta_path.is_file():
        return True
    try:
        import json

        meta = json.loads(meta_path.read_text())
    except Exception:
        return True
    return meta.get("status") != "ready"


def find_remaining(*, max_total: int = 9, max_group: int = 6) -> list[tuple[str, str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []

    for line in BANK.read_text().splitlines():
        line = line.strip()
        if not line.startswith("Look at"):
            continue
        matches = COUNT_PAT.findall(line)
        if len(matches) != 2:
            continue
        roles = [m[0] for m in matches]
        if roles.count("user_name") != 1:
            continue
        ui = roles.index("user_name")
        oi = 1 - ui
        role = ROLE_MAP.get(roles[oi])
        if not role:
            continue
        child_n = int(matches[ui][1])
        adult_n = int(matches[oi][1])
        obj = norm_object(matches[ui][2])
        if obj != norm_object(matches[oi][2]):
            continue
        if child_n + adult_n > max_total or min(child_n, adult_n) < 1 or max(child_n, adult_n) > max_group:
            continue
        stem_id = f"add_{obj}_{child_n}_{adult_n}_user_{role}"
        if stem_id in seen:
            continue
        if not _stem_needs_image(TEMPLATES / stem_id):
            continue
        seen.add(stem_id)
        out.append((stem_id, format_question(child_n, adult_n, role, obj), line))
    return sorted(out)


def main() -> None:
    remaining = find_remaining()
    lines = [
        "# Grade 1 addition — question bank stems awaiting template images",
        "# Source: Question clusters for grade 1/addition.txt",
        "# Format: two-group (child + one adult/sibling), sum <= 9, each group 1–6",
        "",
    ]
    for stem_id, question, bank_line in remaining:
        stem_dir = TEMPLATES / stem_id
        stem_dir.mkdir(parents=True, exist_ok=True)
        (stem_dir / "question.txt").write_text(question + "\n")
        lines.append(f"## {stem_id}")
        lines.append(question)
        lines.append(f"# bank: {bank_line}")
        lines.append("")

    INDEX.write_text("\n".join(lines).rstrip() + "\n")
    print(f"Wrote {len(remaining)} question.txt files")
    print(f"Index: {INDEX.relative_to(PIPELINE.parent)}")


if __name__ == "__main__":
    main()
