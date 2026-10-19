"""
Bank-first stem helpers for the shared multi-grade workbook flow.

Select ready role-locked templates → fill name placeholders → personalize faces.
Answers come from meta.json (never re-guessed by an LLM).
"""

from __future__ import annotations

import functools
import importlib
import json
import os
import random
import re
import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parent
REPO_ROOT     = PIPELINE_ROOT.parent

try:
    from dotenv import load_dotenv
    _repo_env = REPO_ROOT / ".env"
    if _repo_env.exists():
        load_dotenv(_repo_env)
    else:
        load_dotenv()
except ImportError:
    pass

if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

try:
    from app.grade_config import get_questions_roots, GradeNotFoundError, GradeConfigError
except ImportError:
    from grade_config import get_questions_roots, GradeNotFoundError, GradeConfigError  # type: ignore


def _get_grade_roots(grade_id: str) -> tuple[Path, ...]:
    """
    Resolve question bank roots for the given grade from grade_config.

    Returns a tuple of existing Path objects in priority order (primary first).
    Raises GradeNotFoundError or GradeConfigError if the grade is not configured.
    Does NOT fall back to Grade_1 silently.
    """
    roots = get_questions_roots(grade_id)
    return tuple(roots)

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

# Grammatical gender for family roles (used when object/possessive pronouns are needed)
_ROLE_GRAMMATICAL_GENDER: dict[str, str] = {
    "mother": "f",
    "father": "m",
    "grandmother": "f",
    "grandfather": "m",
    "aunt": "f",
    "uncle": "m",
    "brother": "m",
    "sister": "f",
    "sibling": "n",
}


def pronouns_for_gender(gender: str) -> dict[str, str]:
    """Object / possessive / reflexive pronouns from a UI gender label."""
    g = (gender or "").strip().lower()
    if g in ("boy", "male", "m"):
        return {"object": "him", "poss": "his", "reflexive": "himself"}
    if g in ("girl", "female", "f"):
        return {"object": "her", "poss": "her", "reflexive": "herself"}
    return {"object": "them", "poss": "their", "reflexive": "themselves"}


def pronouns_for_role(role: str) -> dict[str, str]:
    """Object / possessive pronouns from a family role (Mum → her, Dad → him, …)."""
    rg = _ROLE_GRAMMATICAL_GENDER.get((role or "").strip().lower(), "n")
    if rg == "f":
        return {"object": "her", "poss": "her", "reflexive": "herself"}
    if rg == "m":
        return {"object": "him", "poss": "his", "reflexive": "himself"}
    return {"object": "them", "poss": "their", "reflexive": "themselves"}


def _pronoun_placeholder_map(*, child_gender: str = "") -> dict[str, str]:
    """Extra template keys: {user_object}, {mother_poss}, …"""
    out: dict[str, str] = {}
    child_p = pronouns_for_gender(child_gender)
    out["user_object"] = child_p["object"]
    out["user_poss"] = child_p["poss"]
    out["user_reflexive"] = child_p["reflexive"]
    for role in ADULT_ROLES:
        rp = pronouns_for_role(role)
        out[f"{role}_object"] = rp["object"]
        out[f"{role}_poss"] = rp["poss"]
        out[f"{role}_reflexive"] = rp["reflexive"]
    out["adult_object"] = "them"
    out["adult_poss"] = "their"
    return out


def _fix_repeated_name_pronouns(
    text: str,
    *,
    child_name: str,
    child_gender: str,
    family_names: dict[str, str] | None,
) -> str:
    """
    After name substitution, turn awkward repeats into pronouns, e.g.
    'John has 3 apples in front of John' → '… in front of him' (Boy).
    """
    family_names = family_names or {}
    child_name = (child_name or "").strip()
    if not child_name:
        return text

    # (display name, object pronoun, possessive determiner)
    pairs: list[tuple[str, str, str]] = []
    cp = pronouns_for_gender(child_gender)
    pairs.append((child_name, cp["object"], cp["poss"]))

    placeholders = {
        "mother", "father", "grandmother", "grandfather",
        "mum", "dad", "grandma", "grandad", "uncle", "aunt",
        "brother", "sister", "sibling", "adult", "child",
    }
    for role in ADULT_ROLES:
        name = display_name_for_role(role, family_names)
        if not name or name.lower() in placeholders:
            continue
        rp = pronouns_for_role(role)
        pairs.append((name, rp["object"], rp["poss"]))

    out = text
    for name, obj, poss in pairs:
        esc = re.escape(name)
        out = re.sub(rf"\bin front of {esc}\b", f"in front of {obj}", out, flags=re.I)
        out = re.sub(rf"\bnext to {esc}\b", f"next to {obj}", out, flags=re.I)
        out = re.sub(rf"\bnear {esc}\b", f"near {obj}", out, flags=re.I)
        out = re.sub(rf"\b{esc}'s\b", poss, out, flags=re.I)
    return out


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
    "grapes": "grapes",
    "grape": "grapes",
    "pears": "pears",
    "pear": "pears",
    "donuts": "donuts",
    "donut": "donuts",
    "doughnuts": "donuts",
    "doughnut": "donuts",
    "popcorn": "popcorn",
    "cherries": "cherries",
    "cherry": "cherries",
    "blueberries": "blueberries",
    "blueberry": "blueberries",
    "sandwiches": "sandwiches",
    "sandwich": "sandwiches",
    "peaches": "peaches",
    "peach": "peaches",
    "muffins": "muffins",
    "muffin": "muffins",
    "waffles": "waffles",
    "waffle": "waffles",
    "pineapples": "pineapples",
    "pineapple": "pineapples",
    "avocados": "avocados",
    "avocado": "avocados",
    # batch v3 / v4 addition foods
    "kiwis": "kiwis",
    "kiwi": "kiwis",
    "crackers": "crackers",
    "cracker": "crackers",
    "plums": "plums",
    "plum": "plums",
    "peppers": "peppers",
    "pepper": "peppers",
    "croissants": "croissants",
    "croissant": "croissants",
    "pretzels": "pretzels",
    "pretzel": "pretzels",
    "bagels": "bagels",
    "bagel": "bagels",
    # grade_1_hamdan
    "breadsticks": "breadsticks",
    "breadstick": "breadsticks",
    "biscuits": "biscuits",
    "biscuit": "biscuits",
    "ice_lollies": "ice_lollies",
    "ice_lolly": "ice_lollies",
    "ice lollies": "ice_lollies",
    "ice lolly": "ice_lollies",
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
    "sports": "football",
    "movies": "parties",
    "play": "bubbles",
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
    "soccer": "football",
    "soccer_ball": "football",
    "soccer_balls": "football",
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
    "paintbrushes": "painting",
    "parties": "parties",
    "planes": "planes",
    "playground": "playground",
    "playland": "playground",
    "reading": "reading",
    "books": "reading",
    "book": "reading",
    "seashells": "beach",
    "shells": "shells",
    "shell": "shells",
    "shopping": "shopping",
        "stickers": "stickers",
        "sticker": "stickers",
        "notebooks": "crafts",
        "notebook": "crafts",
        "toy_cars": "toy_cars",
    "toy_car": "toy_cars",
    "cars": "toy_cars",
    "car": "toy_cars",
    "trains": "trains",
    "train": "trains",
    "toy_trains": "trains",
    "toy_train": "trains",
    "toys": "toys",
    "dinosaurs": "toys",
    "dinosaur": "toys",
    "teddy_bears": "toys",
    "teddy_bear": "toys",
    "teddies": "toys",
    "robots": "toys",
    "robot": "toys",
    # grade_1_hamdan
    "pencils": "pencils",
    "pencil": "pencils",
    "stickers": "stickers",
    "sticker": "stickers",
    "candles": "parties",
    "candle": "parties",
    "flowers": "gardening",
    "flower": "gardening",
    "paint_pots": "painting",
    "paint_pot": "painting",
    "gemstones": "collecting",
    "gemstone": "collecting",
    "gems": "collecting",
    "buttons": "crafts",
    "button": "crafts",
    "counting_blocks": "lego",
    "numbered_blocks": "lego",
    "building": "lego",
    "bird_counters": "toys",
    "cat_counters": "toys",
    "bird_figures": "toys",
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
    "grapes": "Grapes",
    "pears": "Pears",
    "donuts": "Donuts",
    "popcorn": "Popcorn",
    "cherries": "Cherries",
    "blueberries": "Blueberries",
    "sandwiches": "Sandwiches",
    "peaches": "Peaches",
    "muffins": "Muffins",
    "waffles": "Waffles",
    "pineapples": "Pineapples",
    "avocados": "Avocados",
    "kiwis": "Kiwis",
    "crackers": "Crackers",
    "plums": "Plums",
    "peppers": "Peppers",
    "croissants": "Croissants",
    "pretzels": "Pretzels",
    "bagels": "Bagels",
    "breadsticks": "Breadsticks",
    "biscuits": "Biscuits",
    "ice_lollies": "Ice lollies",
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
    "lego": "Lego / blocks",
    "building": "Building blocks",
    "marbles": "Marbles",
    "nature": "Nature",
    "painting": "Painting",
    "parties": "Parties / candles",
    "pencils": "Pencils",
    "planes": "Planes",
    "playground": "Playground",
    "reading": "Reading",
    "shells": "Shells",
    "shopping": "Shopping",
    "stickers": "Stickers",
    "toy_cars": "Toy cars",
    "trains": "Trains",
    "toys": "Toys",
}


def _norm_token(value: str) -> str:
    return re.sub(r"\s+", "_", (value or "").strip().lower().replace("-", " "))


def food_label_to_id(label: str) -> str:
    """Normalize a UI favourite-food label to a stable id."""
    raw = _norm_token(label)
    return _OBJECT_TO_FOOD.get(raw, raw)


def hobby_label_to_id(label: str) -> str:
    """Normalize a UI favourite-hobby label to a stable id."""
    raw = _norm_token(label)
    return _OBJECT_TO_HOBBY.get(raw, raw)


def interest_id_to_label(interest_id: str) -> str:
    """Human-readable label for a food/hobby id."""
    iid = _norm_token(interest_id)
    if iid in _INTEREST_LABELS:
        return _INTEREST_LABELS[iid]
    return iid.replace("_", " ").title()

def _iter_bank_stems_for_interests(grade_id: str, *, require_verified: bool = True):
    """Yield loaded stems usable for interest pickers (adult role optional)."""
    for root in _get_grade_roots(grade_id):
        if not root.is_dir():
            continue
        for topic_dir in sorted(root.iterdir()):
            if not topic_dir.is_dir():
                continue
            for stem_dir in sorted(topic_dir.iterdir()):
                if not stem_dir.is_dir() or not (stem_dir / "meta.json").is_file():
                    continue
                stem = load_stem(stem_dir)
                if stem["status"] != "ready":
                    continue
                if require_verified and not stem["verified"]:
                    continue
                if not stem["question_template"]:
                    continue
                yield stem


@functools.lru_cache(maxsize=32)
def list_template_foods(grade_id: str, *, require_verified: bool = True) -> list[str]:
    """Favourite-food labels that appear on at least one ready question template."""
    foods: set[str] = set()
    for stem in list_ready_stems(grade_id, require_verified=require_verified):
        tags = stem_interest_tags(
            stem.get("meta") or {},
            stem_id=stem.get("stem_id") or "",
            question=stem.get("question_template") or "",
        )
        foods |= tags["foods"]
        foods |= set(stem.get("interest_foods") or [])
    return sorted((interest_id_to_label(f) for f in foods), key=str.lower)


@functools.lru_cache(maxsize=32)
def list_template_hobbies(grade_id: str, *, require_verified: bool = True) -> list[str]:
    """Favourite-hobby labels that appear on at least one ready question template."""
    hobbies: set[str] = set()
    for stem in list_ready_stems(grade_id, require_verified=require_verified):
        tags = stem_interest_tags(
            stem.get("meta") or {},
            stem_id=stem.get("stem_id") or "",
            question=stem.get("question_template") or "",
        )
        hobbies |= tags["hobbies"]
        hobbies |= set(stem.get("interest_hobbies") or [])
    return sorted((interest_id_to_label(h) for h in hobbies), key=str.lower)


def _map_object_token_to_interests(token: str) -> tuple[set[str], set[str]]:
    """Map one object token to food/hobby id sets."""
    foods: set[str] = set()
    hobbies: set[str] = set()
    oid = _norm_token(token)
    if not oid:
        return foods, hobbies
    # strip layout suffixes from hamdan object ids
    for suffix in (
        "_rows", "_neats", "_formations", "_positioneds", "_two_groups",
        "_one_groups", "_form_ones", "_crossed",
    ):
        if oid.endswith(suffix):
            oid = oid[: -len(suffix)]
    if oid in _OBJECT_TO_FOOD:
        foods.add(_OBJECT_TO_FOOD[oid])
    if oid in _OBJECT_TO_HOBBY:
        hobbies.add(_OBJECT_TO_HOBBY[oid])
    if oid in set(_OBJECT_TO_FOOD.values()):
        foods.add(oid)
    if oid in set(_OBJECT_TO_HOBBY.values()):
        hobbies.add(oid)
    return foods, hobbies


def _tokens_from_stem_id(stem_id: str) -> list[str]:
    """Pull candidate object nouns from a stem folder / stem_id."""
    sid = _norm_token(stem_id)
    parts = [p for p in sid.split("_") if p]
    skip = {
        "add", "sub", "mul", "mult", "frac", "geo", "measure", "money", "time",
        "other", "gen", "count", "user", "adult", "mother", "father",
        "grandmother", "grandfather", "sibling", "brother", "sister", "uncle",
        "aunt", "src", "crossed", "rows", "neats", "formations", "positioneds",
        "two", "groups", "one", "form", "ones", "neat", "altogether", "table",
        "group", "a", "items",
    }
    out: list[str] = []
    # Prefer multi-word object spans known to our maps
    known = set(_OBJECT_TO_FOOD) | set(_OBJECT_TO_HOBBY) | set(_OBJECT_TO_FOOD.values()) | set(_OBJECT_TO_HOBBY.values())
    for n in (3, 2, 1):
        for i in range(len(parts) - n + 1):
            chunk = "_".join(parts[i : i + n])
            if chunk in skip or chunk.isdigit() or chunk.startswith("src"):
                continue
            if any(ch.isdigit() for ch in chunk) and not chunk[0].isdigit():
                # e.g. 4p — skip money amounts
                continue
            if chunk in known or n == 1:
                out.append(chunk)
    # also whole middle segment: add_apples_2_7 → apples
    return out


def stem_interest_tags(meta: dict, *, stem_id: str = "", question: str = "") -> dict[str, set[str]]:
    """
    Foods / hobbies this stem aligns with.

    Reads meta['interests'] when present; also infers from visual_groups,
    stem_id, and a few question keywords so Hamdan stems still match.
    """
    foods: set[str] = set()
    hobbies: set[str] = set()

    interests = meta.get("interests") or {}
    for f in interests.get("foods") or []:
        foods.add(food_label_to_id(str(f)))
    for h in interests.get("hobbies") or []:
        hobbies.add(hobby_label_to_id(str(h)))

    for g in meta.get("visual_groups") or []:
        oid = str(g.get("object_id") or g.get("plural") or g.get("singular") or "")
        f, h = _map_object_token_to_interests(oid)
        foods |= f
        hobbies |= h

    sid = stem_id or str(meta.get("stem_id") or "")
    for tok in _tokens_from_stem_id(sid):
        f, h = _map_object_token_to_interests(tok)
        foods |= f
        hobbies |= h

    q = (question or "").lower()
    if "breadstick" in q:
        foods.add("breadsticks")
    if "biscuit" in q:
        foods.add("biscuits")
    if "apple" in q:
        foods.add("apples")
    if "ice loll" in q or "ice-loll" in q:
        foods.add("ice_lollies")
    if "sticker" in q:
        hobbies.add("stickers")
    if "pencil" in q:
        hobbies.add("pencils")
    if "balloon" in q:
        hobbies.add("balloons")
    if "marble" in q:
        hobbies.add("marbles")
    if "toy car" in q:
        hobbies.add("toy_cars")
    if "seashell" in q or " shell" in q:
        hobbies.add("beach")
    if "candle" in q:
        hobbies.add("parties")

    foods.discard("")
    hobbies.discard("")
    return {"foods": foods, "hobbies": hobbies}


@functools.lru_cache(maxsize=32)
def list_topics(grade_id: str) -> list[str]:
    """All topic IDs that have at least one ready stem for the given grade."""
    topics: set[str] = set()
    for root in _get_grade_roots(grade_id):
        if not root.is_dir():
            continue
        for p in sorted(root.iterdir()):
            if not p.is_dir():
                continue
            if any((p / d / "meta.json").is_file() for d in p.iterdir() if d.is_dir()):
                topics.add(p.name)
    return sorted(topics)


def topic_label(topic_id: str, grade_id: str | None = None) -> str:
    from app.grade_config import get_topic_label
    return get_topic_label(topic_id, grade_id)


def long_path(p: Path) -> Path:
    """
    Make a path usable past the Windows 260-character MAX_PATH limit.

    This project sits under a deep folder name and several templates pair a long
    stem folder with a long image filename, pushing the PNG past 260 characters.
    Windows then reports the file as missing even though it is on disk, so those
    stems were silently dropped from every workbook. The `\\\\?\\` prefix opts
    into extended-length paths and makes them readable again.
    """
    if os.name != "nt":
        return p
    s = os.path.abspath(str(p))
    if s.startswith("\\\\?\\") or len(s) < 250:
        return p
    if s.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + s[2:])
    return Path("\\\\?\\" + s)


def load_stem(stem_dir: Path) -> dict:
    meta = json.loads((stem_dir / "meta.json").read_text(encoding="utf-8"))
    q_file = stem_dir / (meta.get("question_file") or "question.txt")
    question = q_file.read_text(encoding="utf-8").strip() if q_file.exists() else ""
    img_name = meta.get("image_file") or ""
    img_path = long_path(stem_dir / img_name) if img_name else None
    pers = meta.get("personalisation") or {}
    locked = (pers.get("template_adult_role") or "").strip().lower()
    interests = stem_interest_tags(meta, stem_id=meta.get("stem_id") or stem_dir.name, question=question)
    face_slots = [str(s).strip().lower() for s in (pers.get("face_slots") or []) if str(s).strip()]
    region_roles = {
        str(r.get("role") or "").strip().lower()
        for r in (meta.get("face_regions") or [])
        if r.get("role")
    }
    # Bank name: 'primary' or 'fallback' based on position in grade roots
    # The folder name is the parent's parent (questions/primary/<topic>/<stem>)
    bank = "primary"
    try:
        bank = stem_dir.parent.parent.name  # 'primary' or 'fallback'
    except Exception:
        pass
    return {
        "stem_dir": stem_dir,
        "stem_id": meta.get("stem_id") or stem_dir.name,
        "topic": meta.get("topic") or stem_dir.parent.name,
        "bank": bank,
        "meta": meta,
        "question_template": question,
        "image_path": img_path,
        "status": (meta.get("status") or "").strip().lower(),
        "verified": bool((meta.get("validation") or {}).get("verified")),
        "template_adult_role": locked,
        "child_gender": (pers.get("child_gender") or "").strip().lower(),
        "allowed_adult_roles": [
            r.lower() for r in (pers.get("allowed_adult_roles") or ([locked] if locked else []))
        ],
        "face_slots": face_slots,
        "region_roles": region_roles,
        "interest_foods": interests["foods"],
        "interest_hobbies": interests["hobbies"],
    }


def attach_count_plan(stem: dict) -> dict:
    """Keep the bank's exact counts and correct answer on the stem."""
    meta = stem.get("meta") or {}
    answer = meta.get("answer") or {}
    try:
        from app.math_visual_engine import object_count_plan
    except ImportError:
        from math_visual_engine import object_count_plan  # type: ignore
    try:
        plan = object_count_plan(stem.get("question_template") or "", meta)
    except Exception:
        plan = {
            "total": 0,
            "plural": "objects",
            "people": [],
            "crossed": 0,
            "operation": "counting",
            "use_board": False,
        }
    plan = dict(plan)
    plan["correct"] = str(answer.get("correct") or "")
    plan["formula"] = str(answer.get("formula") or "")
    stem["count_plan"] = plan
    return stem


def preserve_bank_counts(original_meta: dict | None, updated_meta: dict | None) -> dict:
    """
    A later rewrite may rename the objects.
    The counts, owners, and numeric answer stay the ones stored in the bank.
    """
    updated = dict(updated_meta or {})
    original = original_meta or {}
    old_groups = list(original.get("visual_groups") or [])
    new_groups = [dict(group) for group in (updated.get("visual_groups") or [])]
    if old_groups and new_groups:
        for index, group in enumerate(new_groups):
            if index >= len(old_groups):
                break
            saved = old_groups[index]
            if saved.get("count") is not None:
                group["count"] = saved.get("count")
            if saved.get("crossed_count") is not None:
                group["crossed_count"] = saved.get("crossed_count")
            if saved.get("owner"):
                group["owner"] = saved.get("owner")
        updated["visual_groups"] = new_groups
    old_answer = original.get("answer") or {}
    correct = str(old_answer.get("correct") or "").strip()
    if correct.lstrip("-").isdigit():
        answer = dict(updated.get("answer") or {})
        answer["correct"] = correct
        if old_answer.get("formula"):
            answer["formula"] = old_answer.get("formula")
        updated["answer"] = answer
    return updated


def _stem_has_child_face(stem: dict) -> bool:
    roles = stem.get("region_roles") or set()
    slots = stem.get("face_slots") or []
    return "child" in roles or "user" in roles or "child" in slots or "user" in slots


def _stem_personalizable(stem: dict) -> bool:
    """True when face-swap can run (child box + locked adult box if required)."""
    regions = (stem.get("meta") or {}).get("face_regions") or []
    if not regions:
        return False
    if not _stem_has_child_face(stem):
        return False
    role = (stem.get("template_adult_role") or "").strip().lower()
    if role and role not in (stem.get("region_roles") or set()):
        return False
    return True


_ALL_GRADE_STEMS_CACHE: dict[tuple[str, bool], list[dict]] = {}

_ROLE_FROM_TOKEN = (
    ("grandfather_name", "grandfather"),
    ("grandmother_name", "grandmother"),
    ("father_name", "father"),
    ("mother_name", "mother"),
    ("brother_name", "brother"),
    ("sister_name", "sister"),
    ("uncle_name", "uncle"),
    ("aunt_name", "aunt"),
    ("sibling_name", "sibling"),
)


def _curriculum_adult_role(text: str, filename: str) -> str:
    blob = f"{filename}\n{text}".lower()
    for token, role in _ROLE_FROM_TOKEN:
        if token in blob:
            return role
    return ""


def _read_curriculum_question(path: Path) -> dict:
    """Read a curriculum txt file into question, title, options, answer, and image prompt."""
    raw = path.read_text(encoding="utf-8")
    question_lines: list[str] = []
    image_lines: list[str] = []
    option_lines: list[str] = []
    title = ""
    answer = ""
    section = ""
    for line in raw.splitlines():
        key = line.strip().lower()
        if key.startswith("title:"):
            section = ""
            title = line.split(":", 1)[1].strip()
            continue
        if key.startswith("question_text:"):
            section = "question"
            rest = line.split(":", 1)[1].strip()
            if rest:
                question_lines.append(rest)
            continue
        if key.startswith("options:"):
            section = "options"
            rest = line.split(":", 1)[1].strip()
            if rest:
                option_lines.extend(part.strip() for part in rest.split(",") if part.strip())
            continue
        if key.startswith("answer:"):
            section = ""
            answer = line.split(":", 1)[1].strip()
            continue
        if key.startswith("image_prompt:"):
            section = "image"
            rest = line.split(":", 1)[1].strip()
            if rest:
                image_lines.append(rest)
            continue
        if section == "question":
            question_lines.append(line)
        elif section == "image":
            image_lines.append(line)
        elif section == "options" and line.strip():
            option_lines.append(line.strip())
    question = "\n".join(question_lines).strip()
    if not question:
        question = raw.strip()
    return {
        "question": question,
        "image_prompt": "\n".join(image_lines).strip(),
        "title": title,
        "options": option_lines,
        "answer": answer,
    }


def _stem_from_curriculum_file(path: Path) -> dict | None:
    parsed = _read_curriculum_question(path)
    question = parsed["question"]
    image_prompt = parsed["image_prompt"]
    if not question:
        return None
    topic = path.parent.name
    aliases = [topic]
    if topic == "multiplication_and_division":
        aliases.extend(["multiplication", "division"])
    role = _curriculum_adult_role(question, path.name)
    roles = {"child"}
    if role:
        roles.add(role)
    stem_id = path.stem
    answer_block: dict = {}
    if parsed["answer"]:
        answer_block["correct"] = parsed["answer"]
    if parsed["options"]:
        answer_block["options"] = parsed["options"]
    meta = {
        "stem_id": stem_id,
        "topic": topic,
        "status": "ready",
        "question_file": path.name,
        "title": parsed["title"],
        "answer": answer_block,
        "visual_groups": [],
        "image_prompt": image_prompt,
        "personalisation": {
            "template_adult_role": role,
            "face_slots": ["child", *([role] if role else [])],
            "allowed_adult_roles": [role] if role else [],
        },
        "validation": {"verified": True},
    }
    return {
        "stem_dir": path.parent,
        "stem_id": stem_id,
        "topic": topic,
        "topic_aliases": aliases,
        "bank": "curriculum",
        "meta": meta,
        "question_template": question,
        "image_path": None,
        "status": "ready",
        "verified": True,
        "template_adult_role": role,
        "child_gender": "",
        "allowed_adult_roles": [role] if role else [],
        "face_slots": ["child", *([role] if role else [])],
        "region_roles": roles,
        "interest_foods": set(),
        "interest_hobbies": set(),
    }


def _get_all_grade_ready_stems(grade_id: str, *, require_verified: bool = True) -> list[dict]:
    cache_key = (grade_id, require_verified)
    if cache_key in _ALL_GRADE_STEMS_CACHE:
        return _ALL_GRADE_STEMS_CACHE[cache_key]

    stems: list[dict] = []
    seen: set[str] = set()
    for root in _get_grade_roots(grade_id):
        if not root.is_dir():
            continue
        for topic_dir in sorted(root.iterdir()):
            if not topic_dir.is_dir():
                continue
            for stem_dir in sorted(topic_dir.iterdir()):
                if stem_dir.is_file() and stem_dir.suffix.lower() == ".txt" and root.name == "curriculum":
                    stem = _stem_from_curriculum_file(stem_dir)
                    if not stem or not stem["question_template"]:
                        continue
                    key = f"{stem['topic']}::{stem['stem_id']}"
                    if key in seen:
                        continue
                    seen.add(key)
                    stems.append(attach_count_plan(stem))
                    continue
                if not stem_dir.is_dir() or not (stem_dir / "meta.json").is_file():
                    continue
                stem = load_stem(stem_dir)
                # Prefer first bank (primary) when stem_ids collide
                key = f"{stem['topic']}::{stem['stem_id']}"
                if key in seen:
                    continue
                if stem["status"] != "ready":
                    continue
                if require_verified and not stem["verified"]:
                    continue
                # Adult-locked OR child-only (primary bank often has child/sibling-only scenes)
                if stem["template_adult_role"]:
                    pass
                elif not _stem_has_child_face(stem):
                    continue
                if not stem["question_template"]:
                    continue
                if stem.get("bank") != "curriculum":
                    if not stem["image_path"] or not stem["image_path"].is_file():
                        continue
                seen.add(key)
                stems.append(attach_count_plan(stem))
    _ALL_GRADE_STEMS_CACHE[cache_key] = stems
    return stems


def list_ready_stems(
    grade_id: str,
    *,
    topics: list[str] | None = None,
    require_verified: bool = True,
) -> list[dict]:
    """All ready stems for the given grade, optionally filtered by topic folder names."""
    all_stems = _get_all_grade_ready_stems(grade_id, require_verified=require_verified)
    if not topics:
        return list(all_stems)
    topic_set = {t.lower() for t in topics}
    matched = []
    for stem in all_stems:
        names = {(stem.get("topic") or "").lower()}
        names.update(str(item).lower() for item in (stem.get("topic_aliases") or []))
        keep = False
        for wanted in topic_set:
            if wanted in names:
                keep = True
                break
            for name in names:
                if name and len(name) > 3 and name in wanted:
                    keep = True
                    break
            if keep:
                break
        if keep:
            matched.append(stem)
    return matched


def unfillable_faces(
    stem: dict,
    *,
    available_roles: set[str],
    has_sibling_photo: bool = False,
) -> set[str]:
    """
    Faces in this template that the uploads cannot personalise.

    Any such face stays as the template's own stranger standing next to the
    personalised child — while the question text still calls them "your
    sibling" / "Mum". `sibling` is satisfied by a sibling, brother or sister
    upload; a role nobody can upload (e.g. "teacher") is never fillable.
    """
    avail = {r.lower() for r in available_roles}
    locked = (stem.get("template_adult_role") or "").strip().lower()
    missing: set[str] = set()
    for role in stem.get("region_roles") or set():
        role = str(role).strip().lower()
        if role in ("child", "user", ""):
            continue
        if role == "sibling":
            if not has_sibling_photo:
                missing.add(role)
            continue
        if role not in avail:
            missing.add(role)
    # The locked adult is validated separately by the caller.
    missing.discard(locked)
    return missing


def stems_for_available_roles(
    stems: list[dict],
    available_roles: set[str],
    *,
    has_child_photo: bool = True,
    has_sibling_photo: bool = False,
    require_personalizable: bool = False,
) -> list[dict]:
    """
    Keep only stems whose whole cast can be personalised from the uploads.

    The locked adult must have a photo, AND so must every other non-child face
    in the scene. Without that second condition a child+sibling scene is picked
    even when no brother/sister was uploaded, so the workbook shows the child
    beside a stranger the question calls "your sibling".
    """
    avail = {r.lower() for r in available_roles}
    out = []
    for stem in stems:
        if require_personalizable and not _stem_personalizable(stem):
            continue
        role = (stem.get("template_adult_role") or "").strip().lower()
        if role:
            allowed = stem.get("allowed_adult_roles") or [role]
            if role not in avail or role not in allowed:
                continue
        else:
            if not has_child_photo or not _stem_has_child_face(stem):
                continue
        if unfillable_faces(
            stem, available_roles=avail, has_sibling_photo=has_sibling_photo
        ):
            continue
        out.append(stem)
    return out


def partition_by_child_gender(
    stems: list[dict],
    gender: str,
) -> tuple[list[dict], list[dict]]:
    """
    Split into (matches the child's gender, everything else).

    A face swap replaces the face but not the body, hair or clothes. Putting a
    boy's face on a template whose child is a girl leaves his face above
    pigtails and a girl's cardigan, which is the single most obvious way the
    workbook looks wrong. Templates carry `child_gender` (see
    tag_child_gender.py); `unclear` ones are genuinely ambiguous, so they sit in
    the second list as usable filler rather than being excluded outright.
    """
    g = (gender or "").strip().lower()
    if g in ("boy", "male", "m"):
        want = "boy"
    elif g in ("girl", "female", "f"):
        want = "girl"
    else:
        return [], list(stems)

    match, other = [], []
    for stem in stems:
        if (stem.get("child_gender") or "").strip().lower() == want:
            match.append(stem)
        else:
            other.append(stem)
    return match, other


def partition_by_adult_roles(
    stems: list[dict],
    roles: set[str] | list[str] | None,
) -> tuple[list[dict], list[dict]]:
    """
    Split into (uses one of `roles`, everything else).

    When a parent uploads Mum's photo they expect Mum in the pictures, not a
    child-only scene that quietly ignores the upload. Callers prefer the first
    list and only top up from the second.
    """
    want = {str(r).strip().lower() for r in (roles or []) if str(r).strip()}
    if not want:
        return [], list(stems)
    uses, other = [], []
    for stem in stems:
        role = (stem.get("template_adult_role") or "").strip().lower()
        if role and role in want:
            uses.append(stem)
        else:
            other.append(stem)
    return uses, other


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
    strict_interests: bool = False,
    prefer_hamdan: bool = False,
    bank_balance: bool = True,
) -> list[dict]:
    """
    Pick up to n unique stem_ids.

    When the user selected favourite foods/hobbies, interest-matched stems are
    prioritized first. If strict_interests=False (default), any shortfall is
    automatically topped up from the remaining pool so the workbook is always
    complete. If strict_interests=True, ONLY interest-matched stems are used.

    If no favourites are selected, pick from the full ready pool.
    When bank_balance=True (default), aim for ~50/50 grade_1_hamdan vs grade_1.
    prefer_hamdan is kept for callers but ignored when bank_balance is on.
    """
    if n <= 0 or not stems:
        return []

    want_foods = [f for f in (favourite_foods or []) if str(f).strip()]
    want_hobbies = [h for h in (favourite_hobbies or []) if str(h).strip()]
    has_interests = bool(want_foods or want_hobbies)

    matched, other = partition_by_interests(
        stems,
        favourite_foods=favourite_foods,
        favourite_hobbies=favourite_hobbies,
    )

    def _pick_from(pool: list[dict], need: int) -> list[dict]:
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

    def _pick(pool: list[dict], need: int) -> list[dict]:
        if need <= 0 or not pool:
            return []
        if not bank_balance and not prefer_hamdan:
            return _pick_from(pool, need)

        hamdan = [s for s in pool if (s.get("bank") or "") in ("primary", "grade_1_hamdan")]
        classic = [s for s in pool if (s.get("bank") or "") not in ("primary", "grade_1_hamdan")]

        if bank_balance and hamdan and classic:
            # ~50/50: ceil/floor split, then fill shortfalls from the other bank
            n_hamdan = (need + 1) // 2
            n_classic = need // 2
            # Randomly flip which bank gets the extra slot when need is odd
            if need % 2 == 1 and random.random() < 0.5:
                n_hamdan, n_classic = n_classic, n_hamdan
            chosen_h = _pick_from(hamdan, n_hamdan)
            chosen_c = _pick_from(classic, n_classic)
            chosen = chosen_h + chosen_c
            if len(chosen) < need:
                chosen_ids = {s["stem_id"] for s in chosen}
                leftover = [
                    s for s in (hamdan + classic)
                    if s["stem_id"] not in chosen_ids
                ]
                chosen.extend(_pick_from(leftover, need - len(chosen)))
            random.shuffle(chosen)
            return chosen[:need]

        if prefer_hamdan and hamdan:
            chosen = _pick_from(hamdan, need)
            if len(chosen) < need:
                chosen_ids = {s["stem_id"] for s in chosen}
                fill = [s for s in classic if s["stem_id"] not in chosen_ids]
                chosen.extend(_pick_from(fill, need - len(chosen)))
            return chosen

        return _pick_from(pool, need)

    if has_interests and strict_interests:
        return _pick(matched, n)

    if not has_interests:
        return _pick(stems, n)

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
    child_gender: str = "",
) -> str:
    """Replace {user_name}, {mother_name}, … and pronoun placeholders with profile values."""
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
    mapping.update(_pronoun_placeholder_map(child_gender=child_gender))
    # Locked stem should always use the chosen adult display name for its role token
    mapping[f"{adult_role}_name"] = adult_name

    text = template
    for key, value in mapping.items():
        text = text.replace("{" + key + "}", value)

    # Drop any leftover unknown placeholders conservatively
    text = re.sub(r"\{[a-z_]+\}", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    text = _fix_repeated_name_pronouns(
        text,
        child_name=child,
        child_gender=child_gender,
        family_names=family_names,
    )

    return _clean_third_party_names(
        text,
        user_name=child,
        child_gender=child_gender,
        family_names=family_names,
    )


def _clean_third_party_names(
    text: str,
    *,
    user_name: str,
    child_gender: str = "",
    family_names: dict[str, str] | None = None,
) -> str:
    """
    In fallback/curriculum stems, questions often have hardcoded protagonist
    names from original exam banks (e.g. 'Look at the picture! Maya and Mum are looking at this together.
    Jack has 71p. He buys...').
    This function replaces such third-party character names with the child's name (user_name),
    and adapts their pronouns to match the child's selected gender.
    """
    if not user_name:
        return text

    is_girl = (child_gender or "").strip().lower() in ("girl", "female", "f")
    curriculum_names = (
        "Jack", "Oliver", "Harry", "George", "Leo", "Charlie", "Ben", "Sam", "Tom", "James",
        "William", "Lucas", "Noah", "Jacob", "Lily", "Ella", "Mia", "Emily", "Sophie", "Chloe",
        "Ruby", "Grace", "Evie", "Ava", "Jessica", "Amelia", "Olivia"
    )

    # Check if text has the standard greeting pattern
    prefix_match = re.match(r'^(Look at the picture!\s*.*?are looking at this together\.\s*)(.*)$', text, flags=re.S)
    if prefix_match:
        prefix, rest = prefix_match.group(1), prefix_match.group(2)
        for name in curriculum_names:
            if name.lower() != user_name.lower() and re.search(r'\b' + name + r'\b', rest):
                rest = re.sub(r'\b' + name + r'\'s\b', f"{user_name}'s", rest)
                rest = re.sub(r'\b' + name + r'\b', user_name, rest)
                if is_girl:
                    rest = re.sub(r'\bHe\b', 'She', rest)
                    rest = re.sub(r'\bhe\b', 'she', rest)
                    rest = re.sub(r'\bHis\b', 'Her', rest)
                    rest = re.sub(r'\bhis\b', 'her', rest)
                    rest = re.sub(r'\bhim\b', 'her', rest)
                break
        return prefix + rest

    return text


# ─── Food substitution ────────────────────────────────────────────────
_DEFAULT_FOOD_WORDS: dict[str, str] = {
    # singular → plural (and vice versa)
    "apple": "apples", "apples": "apples",
    "banana": "bananas", "bananas": "bananas",
    "mango": "mangoes", "mangoes": "mangoes",
    "orange": "oranges", "oranges": "oranges",
    "strawberry": "strawberries", "strawberries": "strawberries",
    "cherry": "cherries", "cherries": "cherries",
    "grape": "grapes", "grapes": "grapes",
    "pear": "pears", "pears": "pears",
    "peach": "peaches", "peaches": "peaches",
    "plum": "plums", "plums": "plums",
    "watermelon": "watermelons", "watermelons": "watermelons",
    "lemon": "lemons", "lemons": "lemons",
    "kiwi": "kiwis", "kiwis": "kiwis",
    "blueberry": "blueberries", "blueberries": "blueberries",
    "avocado": "avocados", "avocados": "avocados",
    "pineapple": "pineapples", "pineapples": "pineapples",
    "cake": "cakes", "cakes": "cakes",
    "cookie": "cookies", "cookies": "cookies",
    "cupcake": "cupcakes", "cupcakes": "cupcakes",
    "muffin": "muffins", "muffins": "muffins",
    "donut": "donuts", "donuts": "donuts",
    "pancake": "pancakes", "pancakes": "pancakes",
    "bread": "breads", "breads": "breads",
    "sandwich": "sandwiches", "sandwiches": "sandwiches",
    "pizza": "pizzas", "pizzas": "pizzas",
    "burger": "burgers", "burgers": "burgers",
    "waffle": "waffles", "waffles": "waffles",
    "croissant": "croissants", "croissants": "croissants",
    "bagel": "bagels", "bagels": "bagels",
    "pretzel": "pretzels", "pretzels": "pretzels",
    "sweet": "sweets", "sweets": "sweets",
    "candy": "candies", "candies": "candies",
    "chocolate": "chocolates", "chocolates": "chocolates",
    "lollipop": "lollipops", "lollipops": "lollipops",
    "biscuit": "biscuits", "biscuits": "biscuits",
    "noodle": "noodles", "noodles": "noodles",
    "egg": "eggs", "eggs": "eggs",
    "carrot": "carrots", "carrots": "carrots",
    "tomato": "tomatoes", "tomatoes": "tomatoes",
    "pepper": "peppers", "peppers": "peppers",
}

# Map plural → singular for common irregular/regular forms
_PLURAL_TO_SINGULAR: dict[str, str] = {
    "apples": "apple", "bananas": "banana", "mangoes": "mango",
    "oranges": "orange", "strawberries": "strawberry",
    "cherries": "cherry", "grapes": "grape", "pears": "pear",
    "peaches": "peach", "plums": "plum", "watermelons": "watermelon",
    "lemons": "lemon", "kiwis": "kiwi", "blueberries": "blueberry",
    "avocados": "avocado", "pineapples": "pineapple",
    "cakes": "cake", "cookies": "cookie", "cupcakes": "cupcake",
    "muffins": "muffin", "donuts": "donut", "pancakes": "pancake",
    "breads": "bread", "sandwiches": "sandwich", "pizzas": "pizza",
    "burgers": "burger", "waffles": "waffle", "croissants": "croissant",
    "bagels": "bagel", "pretzels": "pretzel", "sweets": "sweet",
    "candies": "candy", "chocolates": "chocolate", "lollipops": "lollipop",
    "biscuits": "biscuit", "noodles": "noodle", "eggs": "egg",
    "carrots": "carrot", "tomatoes": "tomato", "peppers": "pepper",
}


def _pluralize_food(singular: str) -> str:
    """Simple English pluralization for food words."""
    singular = singular.strip().lower()
    if singular.endswith(("sh", "ch", "x", "s", "z")):
        return singular + "es"
    if singular.endswith("y") and singular[-2:] not in ("ay", "ey", "oy", "uy"):
        return singular[:-1] + "ies"
    if singular.endswith("o") and singular not in ("avocado", "burrito", "taco"):
        return singular + "es"
    return singular + "s"


def _singularize_food(plural: str) -> str:
    """Reverse simple pluralization for food words."""
    plural = plural.strip().lower()
    if plural in _PLURAL_TO_SINGULAR:
        return _PLURAL_TO_SINGULAR[plural]
    if plural.endswith("ies"):
        return plural[:-3] + "y"
    if plural.endswith("oes"):
        return plural[:-2]
    if plural.endswith("es"):
        return plural[:-2]
    if plural.endswith("s"):
        return plural[:-1]
    return plural


def substitute_favourite_foods(
    text: str,
    *,
    favourite_foods: list[str] | None = None,
    _food_index: list[int] | None = None,
) -> str:
    """
    Replace default food items in question text with the child's favourite food(s).

    If multiple favourite foods are selected, cycle through them across calls
    (use a mutable _food_index list as a counter to track position).

    Only replaces food words that actually appear in _DEFAULT_FOOD_WORDS.
    Preserves singular/plural form.
    """
    foods = [f.strip() for f in (favourite_foods or []) if f.strip()]
    if not foods:
        return text

    # Use a mutable list as an index counter (shared across calls in a loop)
    if _food_index is None:
        _food_index = [0]

    # Find all default food words in text (case-insensitive)
    found_foods: list[tuple[str, int, int, bool]] = []  # (match, start, end, is_plural)
    text_lower = text.lower()

    # Sort by length descending to match longer words first (e.g., "ice cream" before "cream")
    sorted_defaults = sorted(_DEFAULT_FOOD_WORDS.keys(), key=len, reverse=True)
    used_ranges: list[tuple[int, int]] = []

    for default_word in sorted_defaults:
        pattern = r'\b' + re.escape(default_word) + r'\b'
        for m in re.finditer(pattern, text_lower):
            start, end = m.start(), m.end()
            # Check no overlap with already matched ranges
            if any(s <= start < e or s < end <= e for s, e in used_ranges):
                continue
            is_plural = default_word in _PLURAL_TO_SINGULAR
            found_foods.append((text[start:end], start, end, is_plural))
            used_ranges.append((start, end))

    if not found_foods:
        return text

    # Sort by position for correct replacement
    found_foods.sort(key=lambda x: x[1])

    # Build new text with replacements
    result_parts = []
    last_end = 0
    for original_word, start, end, is_plural in found_foods:
        result_parts.append(text[last_end:start])

        # Pick a favourite food (cycling through)
        chosen_food = foods[_food_index[0] % len(foods)]
        _food_index[0] += 1

        # Match the plural/singular form
        chosen_food_lower = chosen_food.strip().lower()
        if is_plural:
            replacement = _pluralize_food(chosen_food_lower)
        else:
            replacement = chosen_food_lower

        # Match the case of the original word
        if original_word[0].isupper():
            replacement = replacement.capitalize()

        result_parts.append(replacement)
        last_end = end

    result_parts.append(text[last_end:])
    return "".join(result_parts)


def _format_mcq_options(correct: str, options: list[str]) -> dict:
    """Exactly 3 options: the correct answer and 2 wrong ones."""
    from app.mcq_options import normalize_trio
    return normalize_trio(correct, options)


def _smart_fallback_mcq(question: str) -> dict:
    """Read the question locally and return 1 correct answer plus 2 wrong ones."""
    from app.mcq_options import build_mcq
    return build_mcq(question, allow_network=False)


def mcq_from_meta(meta: dict, question: str = "") -> dict:
    """
    Use the answer stored on the question when it exists.
    Otherwise read the question and build 1 correct option plus 2 wrong ones.
    """
    from app.mcq_options import build_mcq
    return build_mcq(question, meta=meta or {}, allow_network=False)


def generate_mcq_ai(
    question: str,
    api_key: str | None = None,
    model: str = "openai/gpt-4o-mini",
) -> dict:
    """
    Read the question and return exactly 3 options (1 correct, 2 wrong)
    plus a short page title and sticker. Falls back to the local reader
    when the model is unavailable.
    """
    from app.mcq_options import build_mcq
    return build_mcq(
        question,
        allow_network=True,
        api_key=api_key,
        model=model,
    )


def build_workbook_items(
    stems: list[dict],
    *,
    user_name: str,
    family_names: dict | None = None,
    face_paths: dict[str, str] | None = None,
    child_gender: str = "",
    out_dir: Path | str | None = None,
    on_progress=None,
    skip_on_error: bool = True,
    grade_id: str = "",
    **kwargs,
) -> tuple[list[dict], list[dict]]:
    """
    Generate personalised workbook items using the AI generation pipeline
    (question_image.md + question + uploaded photos as visual reference).

    grade_id is required and selects grades/<grade_id>/prompts/question_image.md.
    """
    if not (grade_id or "").strip():
        raise ValueError(
            "grade_id is required to build workbook items. "
            "Refusing to use another grade's questions or prompts."
        )
    try:
        from app.image_generator import build_workbook_items_ai_generated
    except ImportError:
        from image_generator import build_workbook_items_ai_generated

    return build_workbook_items_ai_generated(
        stems,
        user_name=user_name,
        family_names=family_names,
        face_paths=face_paths,
        child_gender=child_gender,
        out_dir=out_dir,
        on_progress=on_progress,
        skip_on_error=skip_on_error,
        grade_id=grade_id,
        max_workers=kwargs.get("max_workers", 4),
        fav_color=kwargs.get("fav_color") or kwargs.get("favourite_colour") or "",
        favourite_colour=kwargs.get("favourite_colour") or kwargs.get("fav_color") or "",
        favourite_foods=kwargs.get("favourite_foods"),
        favourite_sports=kwargs.get("favourite_sports"),
        favourite_hobbies=kwargs.get("favourite_hobbies"),
        favourite_characters=kwargs.get("favourite_characters"),
        favourite_cartoons=kwargs.get("favourite_cartoons"),
    )
