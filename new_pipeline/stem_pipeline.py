"""
Bank-first stem helpers for the new_pipeline workbook flow.

Select ready role-locked templates → fill name placeholders → personalize faces.
Answers come from meta.json (never re-guessed by an LLM).
"""

from __future__ import annotations

import importlib
import json
import random
import re
import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parent
TEMPLATES_ROOT = PIPELINE_ROOT / "question_templates"
GRADE_ROOT = TEMPLATES_ROOT / "grade_1"

if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

ROLE_DISPLAY = {
    "mother": "Mum",
    "father": "Dad",
    "grandmother": "Grandma",
    "grandfather": "Grandad",
    "uncle": "Uncle",
    "aunt": "Aunt",
    "brother": "Brother",
    "sister": "Sister",
    "sibling": "Sibling",
}

ADULT_ROLES = tuple(ROLE_DISPLAY.keys())

# Map visual object_ids / labels → UI food & hobby ids (expand as templates grow)
_OBJECT_TO_FOOD: dict[str, str] = {
    "apples": "apples",
    "apple": "apples",
    "bananas": "bananas",
    "banana": "bananas",
    "burgers": "burgers",
    "burger": "burgers",
    "carrots": "carrots",
    "carrot": "carrots",
    "chocolates": "chocolates",
    "chocolate": "chocolates",
    "cookies": "cookies",
    "cookie": "cookies",
    "cupcakes": "cupcakes",
    "cupcake": "cupcakes",
    "eggs": "eggs",
    "egg": "eggs",
    "fish": "fish",
    "ice_cream": "ice_cream",
    "ice cream": "ice_cream",
    "lemons": "lemons",
    "lemon": "lemons",
    "mangoes": "mangoes",
    "mango": "mangoes",
    "noodles": "noodles",
    "noodle": "noodles",
    "oranges": "oranges",
    "orange": "oranges",
    "pancakes": "pancakes",
    "pancake": "pancakes",
    "pasta": "pasta",
    "pizza": "pizza",
    "smoothies": "smoothies",
    "smoothie": "smoothies",
    "strawberries": "strawberries",
    "strawberry": "strawberries",
    "sweets": "sweets",
    "sweet": "sweets",
    "tomatoes": "tomatoes",
    "tomato": "tomatoes",
    "watermelons": "watermelons",
    "watermelon": "watermelons",
}

_OBJECT_TO_HOBBY: dict[str, str] = {
    "art": "art",
    "arts_and_crafts": "arts_and_crafts",
    "baking": "baking",
    "balloons": "balloons",
    "balloon": "balloons",
    "beach": "beach",
    "bubbles": "bubbles",
    "bubble": "bubbles",
    "butterflies": "butterflies",
    "butterfly": "butterflies",
    "collecting": "collecting",
    "colouring": "colouring",
    "cooking": "cooking",
    "crafts": "crafts",
    "crayons": "crayons",
    "crayon": "crayons",
    "drawing": "drawing",
    "farming": "farming",
    "fishing": "fishing",
    "football": "football",
    "balls": "football",
    "ball": "football",
    "frisbee": "frisbee",
    "gardening": "gardening",
    "kite": "kite",
    "kites": "kite",
    "kite_flying": "kite_flying",
    "lego": "lego",
    "blocks": "lego",
    "block": "lego",
    "marbles": "marbles",
    "marble": "marbles",
    "nature": "nature",
    "painting": "painting",
    "paintbrush": "painting",
    "parties": "parties",
    "planes": "planes",
    "reading": "reading",
    "books": "reading",
    "book": "reading",
    "seashells": "beach",
    "shells": "shells",
    "shell": "shells",
    "shopping": "shopping",
    "stickers": "crafts",
    "sticker": "crafts",
    "toy_cars": "toy_cars",
    "toy_car": "toy_cars",
    "toys": "toys",
}

# Display labels for template interest ids (UI multiselect)
_INTEREST_LABELS: dict[str, str] = {
    # Foods
    "apples": "Apples",
    "bananas": "Bananas",
    "burgers": "Burgers",
    "carrots": "Carrots",
    "chocolates": "Chocolates",
    "cookies": "Cookies",
    "cupcakes": "Cupcakes",
    "eggs": "Eggs",
    "fish": "Fish",
    "ice_cream": "Ice cream",
    "lemons": "Lemons",
    "mangoes": "Mangoes",
    "noodles": "Noodles",
    "oranges": "Oranges",
    "pancakes": "Pancakes",
    "pasta": "Pasta",
    "pizza": "Pizza",
    "smoothies": "Smoothies",
    "strawberries": "Strawberries",
    "sweets": "Sweets",
    "tomatoes": "Tomatoes",
    "watermelons": "Watermelons",
    # Hobbies
    "art": "Art",
    "arts_and_crafts": "Arts & crafts",
    "baking": "Baking",
    "balloons": "Balloons",
    "beach": "Beach",
    "bubbles": "Bubbles",
    "butterflies": "Butterflies",
    "collecting": "Collecting",
    "colouring": "Colouring",
    "cooking": "Cooking",
    "crafts": "Crafts",
    "crayons": "Crayons",
    "drawing": "Drawing",
    "farming": "Farming",
    "fishing": "Fishing",
    "football": "Football",
    "frisbee": "Frisbee",
    "gardening": "Gardening",
    "kite": "Kite",
    "kite_flying": "Kite flying",
    "lego": "Lego",
    "marbles": "Marbles",
    "nature": "Nature",
    "painting": "Painting",
    "parties": "Parties",
    "planes": "Planes",
    "reading": "Reading",
    "shells": "Shells",
    "shopping": "Shopping",
    "toy_cars": "Toy cars",
    "toys": "Toys",
}


def _norm_token(value: str) -> str:
    return re.sub(r"\s+", "_", (value or "").strip().lower().replace("-", " "))


def food_label_to_id(label: str) -> str:
    """Normalize a UI favourite-food label to a stable id."""
    try:
        from interactive_templates.compositor import food_label_to_object_id

        return _norm_token(food_label_to_object_id(label))
    except Exception:
        raw = _norm_token(label)
        return _OBJECT_TO_FOOD.get(raw, raw)


def hobby_label_to_id(label: str) -> str:
    """Normalize a UI favourite-hobby label to a stable id."""
    try:
        from interactive_templates.compositor import hobby_label_to_object_id

        mapped = _norm_token(hobby_label_to_object_id(label))
        # compositor may not know newer hobby ids (marbles/lego/reading)
        if mapped and mapped not in _OBJECT_TO_HOBBY and mapped not in set(_OBJECT_TO_HOBBY.values()):
            raw = _norm_token(label)
            return _OBJECT_TO_HOBBY.get(raw, mapped)
        return _OBJECT_TO_HOBBY.get(mapped, mapped)
    except Exception:
        raw = _norm_token(label)
        return _OBJECT_TO_HOBBY.get(raw, raw)


def interest_id_to_label(interest_id: str) -> str:
    """Human-readable label for a food/hobby id."""
    iid = _norm_token(interest_id)
    if iid in _INTEREST_LABELS:
        return _INTEREST_LABELS[iid]
    return iid.replace("_", " ").title()


def list_template_foods(*, require_verified: bool = True) -> list[str]:
    """Favourite-food labels that appear on at least one ready question template."""
    foods: set[str] = set()
    for stem in list_ready_stems(require_verified=require_verified):
        foods |= set(stem.get("interest_foods") or [])
    return sorted((interest_id_to_label(f) for f in foods), key=str.lower)


def list_template_hobbies(*, require_verified: bool = True) -> list[str]:
    """Favourite-hobby labels that appear on at least one ready question template."""
    hobbies: set[str] = set()
    for stem in list_ready_stems(require_verified=require_verified):
        hobbies |= set(stem.get("interest_hobbies") or [])
    return sorted((interest_id_to_label(h) for h in hobbies), key=str.lower)


def stem_interest_tags(meta: dict) -> dict[str, set[str]]:
    """
    Foods / hobbies this stem aligns with.

    Reads meta['interests'] when present; also infers from visual_groups object_id
    so older stems still match (e.g. apples → food apples).
    """
    foods: set[str] = set()
    hobbies: set[str] = set()

    interests = meta.get("interests") or {}
    for f in interests.get("foods") or []:
        foods.add(food_label_to_id(str(f)))
    for h in interests.get("hobbies") or []:
        hobbies.add(hobby_label_to_id(str(h)))

    for g in meta.get("visual_groups") or []:
        oid = _norm_token(str(g.get("object_id") or g.get("plural") or g.get("singular") or ""))
        if not oid:
            continue
        if oid in _OBJECT_TO_FOOD:
            foods.add(_OBJECT_TO_FOOD[oid])
        if oid in _OBJECT_TO_HOBBY:
            hobbies.add(_OBJECT_TO_HOBBY[oid])
        # explicit object id that is already a food/hobby id
        if oid in set(_OBJECT_TO_FOOD.values()):
            foods.add(oid)
        if oid in set(_OBJECT_TO_HOBBY.values()):
            hobbies.add(oid)

    foods.discard("")
    hobbies.discard("")
    return {"foods": foods, "hobbies": hobbies}


def list_topics() -> list[str]:
    if not GRADE_ROOT.is_dir():
        return []
    topics = []
    for p in sorted(GRADE_ROOT.iterdir()):
        if not p.is_dir():
            continue
        if any((p / d / "meta.json").is_file() for d in p.iterdir() if d.is_dir()):
            topics.append(p.name)
    return topics


def topic_label(topic_id: str) -> str:
    return topic_id.replace("_", " ").title()


def load_stem(stem_dir: Path) -> dict:
    meta = json.loads((stem_dir / "meta.json").read_text(encoding="utf-8"))
    q_file = stem_dir / (meta.get("question_file") or "question.txt")
    question = q_file.read_text(encoding="utf-8").strip() if q_file.exists() else ""
    img_name = meta.get("image_file") or ""
    img_path = stem_dir / img_name if img_name else None
    pers = meta.get("personalisation") or {}
    locked = (pers.get("template_adult_role") or "").strip().lower()
    interests = stem_interest_tags(meta)
    return {
        "stem_dir": stem_dir,
        "stem_id": meta.get("stem_id") or stem_dir.name,
        "topic": meta.get("topic") or stem_dir.parent.name,
        "meta": meta,
        "question_template": question,
        "image_path": img_path,
        "status": (meta.get("status") or "").strip().lower(),
        "verified": bool((meta.get("validation") or {}).get("verified")),
        "template_adult_role": locked,
        "allowed_adult_roles": [
            r.lower() for r in (pers.get("allowed_adult_roles") or ([locked] if locked else []))
        ],
        "interest_foods": interests["foods"],
        "interest_hobbies": interests["hobbies"],
    }


def list_ready_stems(
    *,
    topics: list[str] | None = None,
    require_verified: bool = True,
) -> list[dict]:
    """All ready stems, optionally filtered by topic folder names."""
    if not GRADE_ROOT.is_dir():
        return []
    topic_set = {t.lower() for t in topics} if topics else None
    stems: list[dict] = []
    for topic_dir in sorted(GRADE_ROOT.iterdir()):
        if not topic_dir.is_dir():
            continue
        if topic_set is not None and topic_dir.name.lower() not in topic_set:
            continue
        for stem_dir in sorted(topic_dir.iterdir()):
            if not stem_dir.is_dir() or not (stem_dir / "meta.json").is_file():
                continue
            stem = load_stem(stem_dir)
            if stem["status"] != "ready":
                continue
            if require_verified and not stem["verified"]:
                continue
            if not stem["template_adult_role"]:
                continue
            if not stem["image_path"] or not stem["image_path"].is_file():
                continue
            if not stem["question_template"]:
                continue
            stems.append(stem)
    return stems


def stems_for_available_roles(
    stems: list[dict],
    available_roles: set[str],
) -> list[dict]:
    """Keep stems whose locked adult role has an uploaded photo."""
    avail = {r.lower() for r in available_roles}
    out = []
    for stem in stems:
        role = stem["template_adult_role"]
        allowed = stem["allowed_adult_roles"] or [role]
        if role in avail and role in allowed:
            out.append(stem)
    return out


def stem_matches_interests(
    stem: dict,
    *,
    favourite_foods: list[str] | None = None,
    favourite_hobbies: list[str] | None = None,
) -> bool:
    """True if stem tags overlap selected foods and/or hobbies."""
    want_foods = {food_label_to_id(f) for f in (favourite_foods or []) if str(f).strip()}
    want_hobbies = {hobby_label_to_id(h) for h in (favourite_hobbies or []) if str(h).strip()}
    if not want_foods and not want_hobbies:
        return False
    foods = stem.get("interest_foods") or set()
    hobbies = stem.get("interest_hobbies") or set()
    return bool(foods & want_foods) or bool(hobbies & want_hobbies)


def partition_by_interests(
    stems: list[dict],
    *,
    favourite_foods: list[str] | None = None,
    favourite_hobbies: list[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Split into (interest-matched, other). If no interests selected, matched=[]."""
    want_foods = [f for f in (favourite_foods or []) if str(f).strip()]
    want_hobbies = [h for h in (favourite_hobbies or []) if str(h).strip()]
    if not want_foods and not want_hobbies:
        return [], list(stems)

    matched, other = [], []
    for s in stems:
        if stem_matches_interests(
            s, favourite_foods=want_foods, favourite_hobbies=want_hobbies
        ):
            matched.append(s)
        else:
            other.append(s)
    return matched, other


def select_stems(
    stems: list[dict],
    n: int,
    *,
    prefer_topic_spread: bool = True,
    favourite_foods: list[str] | None = None,
    favourite_hobbies: list[str] | None = None,
) -> list[dict]:
    """
    Pick up to n unique stem_ids.

    Prefer stems tagged with the user's favourite foods/hobbies; if fewer than n
    match, fill the rest from remaining ready stems (fallback). Topic spread
    still applies within each tier.
    """
    if n <= 0 or not stems:
        return []

    matched, other = partition_by_interests(
        stems,
        favourite_foods=favourite_foods,
        favourite_hobbies=favourite_hobbies,
    )

    def _pick(pool: list[dict], need: int) -> list[dict]:
        if need <= 0 or not pool:
            return []
        by_id: dict[str, dict] = {}
        for s in pool:
            by_id.setdefault(s["stem_id"], s)
        unique = list(by_id.values())
        random.shuffle(unique)
        if not prefer_topic_spread or need >= len(unique):
            return unique[:need]
        by_topic: dict[str, list[dict]] = {}
        for s in unique:
            by_topic.setdefault(s["topic"], []).append(s)
        topics = list(by_topic.keys())
        random.shuffle(topics)
        picked: list[dict] = []
        while len(picked) < need and any(by_topic.values()):
            for t in topics:
                bucket = by_topic.get(t) or []
                if not bucket:
                    continue
                picked.append(bucket.pop(0))
                if len(picked) >= need:
                    break
        return picked

    chosen = _pick(matched, n)
    if len(chosen) < n:
        chosen_ids = {s["stem_id"] for s in chosen}
        rest = [s for s in other if s["stem_id"] not in chosen_ids]
        chosen.extend(_pick(rest, n - len(chosen)))
    return chosen


def display_name_for_role(role: str, family_names: dict[str, str] | None = None) -> str:
    family_names = family_names or {}
    role = role.strip().lower()
    raw = (family_names.get(role) or "").strip()
    placeholders = {role, "mother", "father", "grandmother", "grandfather", "mum", "dad", "adult"}
    if raw and raw.lower() not in placeholders:
        return raw
    return ROLE_DISPLAY.get(role, role.replace("_", " ").title())


def fill_question_text(
    template: str,
    *,
    user_name: str,
    adult_role: str,
    family_names: dict[str, str] | None = None,
) -> str:
    """Replace {user_name}, {mother_name}, … with profile names."""
    family_names = family_names or {}
    adult_name = display_name_for_role(adult_role, family_names)
    child = (user_name or "").strip() or "you"

    mapping = {
        "user_name": child,
        "adult_name": adult_name,
        "mother_name": display_name_for_role("mother", family_names),
        "father_name": display_name_for_role("father", family_names),
        "grandmother_name": display_name_for_role("grandmother", family_names),
        "grandfather_name": display_name_for_role("grandfather", family_names),
        "sibling_name": (family_names.get("sibling") or "your sibling").strip(),
        "uncle_name": display_name_for_role("uncle", family_names),
        "aunt_name": display_name_for_role("aunt", family_names),
        "brother_name": display_name_for_role("brother", family_names),
        "sister_name": display_name_for_role("sister", family_names),
    }
    # Locked stem should always use the chosen adult display name for its role token
    mapping[f"{adult_role}_name"] = adult_name

    text = template
    for key, value in mapping.items():
        text = text.replace("{" + key + "}", value)

    # Drop any leftover unknown placeholders conservatively
    text = re.sub(r"\{[a-z_]+\}", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def mcq_from_meta(meta: dict) -> dict:
    answer = meta.get("answer") or {}
    options = [str(o) for o in (answer.get("options") or [])]
    correct = str(answer.get("correct") or "")
    if correct and correct not in options:
        options = [correct] + [o for o in options if o != correct]
    return {
        "options": options[:4],
        "correct_answer": correct,
    }


def build_workbook_items(
    stems: list[dict],
    *,
    user_name: str,
    family_names: dict[str, str],
    face_paths: dict[str, str | Path],
    run_ai_finish: bool = True,
    soft_cartoon: bool = True,
    child_gender: str = "",
    out_dir: Path | None = None,
) -> list[dict]:
    """
    Personalize each stem and return PDF-ready items.

    face_paths keys: user/child, mother, father, grandmother, grandfather
    """
    from question_templates import personalize as _personalize

    importlib.reload(_personalize)
    personalize_stem = _personalize.personalize_stem

    out_dir = Path(out_dir) if out_dir else PIPELINE_ROOT / "_runtime" / "personalized"
    out_dir.mkdir(parents=True, exist_ok=True)

    child_photo = face_paths.get("user") or face_paths.get("child")
    if not child_photo:
        raise ValueError("Child face photo is required.")

    items: list[dict] = []
    for i, stem in enumerate(stems, start=1):
        role = stem["template_adult_role"]
        adult_photo = face_paths.get(role)
        if not adult_photo:
            raise ValueError(f"Missing face photo for locked role '{role}' ({stem['stem_id']}).")

        out_path = out_dir / f"{i:02d}_{stem['stem_id']}_{role}.png"
        personalize_stem(
            stem["stem_dir"],
            child_photo=child_photo,
            adult_photo=adult_photo,
            adult_role=role,
            out_path=out_path,
            run_ai_finish=run_ai_finish,
            soft_cartoon=soft_cartoon,
            child_gender=child_gender,
        )

        q_text = fill_question_text(
            stem["question_template"],
            user_name=user_name,
            adult_role=role,
            family_names=family_names,
        )
        mcq = mcq_from_meta(stem["meta"])
        items.append(
            {
                "stem_id": stem["stem_id"],
                "topic": stem["topic"],
                "topic_label": topic_label(stem["topic"]),
                "adult_role": role,
                "adult_name": display_name_for_role(role, family_names),
                "question": q_text,
                "image_path": str(out_path),
                "options": mcq,
                "correct": mcq["correct_answer"],
                "formula": (stem["meta"].get("answer") or {}).get("formula"),
            }
        )
    return items
