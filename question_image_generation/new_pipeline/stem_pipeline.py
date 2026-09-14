"""
Bank-first stem helpers for the new_pipeline workbook flow.

Select ready role-locked templates → fill name placeholders → personalize faces.
Answers come from meta.json (never re-guessed by an LLM).
"""

from __future__ import annotations

import importlib
import json
import os
import random
import re
import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parent
TEMPLATES_ROOT = PIPELINE_ROOT / "question_templates"
# Prefer Hamdan bank (richer Grade 1 set); keep original grade_1 as fallback/extra stems
GRADE_ROOT = TEMPLATES_ROOT / "grade_1_hamdan"
GRADE_ROOTS: tuple[Path, ...] = (
    TEMPLATES_ROOT / "grade_1_hamdan",
    TEMPLATES_ROOT / "grade_1",
)

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


def _iter_bank_stems_for_interests(*, require_verified: bool = True):
    """Yield loaded stems usable for interest pickers (adult role optional)."""
    for root in GRADE_ROOTS:
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


def list_template_foods(*, require_verified: bool = True) -> list[str]:
    """Favourite-food labels that appear on at least one ready question template."""
    foods: set[str] = set()
    for stem in _iter_bank_stems_for_interests(require_verified=require_verified):
        foods |= set(stem.get("interest_foods") or [])
    return sorted((interest_id_to_label(f) for f in foods), key=str.lower)


def list_template_hobbies(*, require_verified: bool = True) -> list[str]:
    """Favourite-hobby labels that appear on at least one ready question template."""
    hobbies: set[str] = set()
    for stem in _iter_bank_stems_for_interests(require_verified=require_verified):
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


def list_topics() -> list[str]:
    topics: set[str] = set()
    for root in GRADE_ROOTS:
        if not root.is_dir():
            continue
        for p in sorted(root.iterdir()):
            if not p.is_dir():
                continue
            if any((p / d / "meta.json").is_file() for d in p.iterdir() if d.is_dir()):
                topics.add(p.name)
    return sorted(topics)


def topic_label(topic_id: str) -> str:
    return topic_id.replace("_", " ").title()


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
    # Bank folder name: grade_1_hamdan / grade_1
    bank = "grade_1"
    try:
        # …/question_templates/<bank>/<topic>/<stem>
        bank = stem_dir.parent.parent.name
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


def list_ready_stems(
    *,
    topics: list[str] | None = None,
    require_verified: bool = True,
) -> list[dict]:
    """All ready stems across Grade 1 banks, optionally filtered by topic folder names."""
    topic_set = {t.lower() for t in topics} if topics else None
    stems: list[dict] = []
    seen: set[str] = set()
    for root in GRADE_ROOTS:
        if not root.is_dir():
            continue
        for topic_dir in sorted(root.iterdir()):
            if not topic_dir.is_dir():
                continue
            if topic_set is not None and topic_dir.name.lower() not in topic_set:
                continue
            for stem_dir in sorted(topic_dir.iterdir()):
                if not stem_dir.is_dir() or not (stem_dir / "meta.json").is_file():
                    continue
                stem = load_stem(stem_dir)
                # Prefer first bank (hamdan) when stem_ids collide
                key = f"{stem['topic']}::{stem['stem_id']}"
                if key in seen:
                    continue
                if stem["status"] != "ready":
                    continue
                if require_verified and not stem["verified"]:
                    continue
                # Adult-locked OR child-only (Hamdan often has child/sibling-only scenes)
                if stem["template_adult_role"]:
                    pass
                elif not _stem_has_child_face(stem):
                    continue
                if not stem["image_path"] or not stem["image_path"].is_file():
                    continue
                if not stem["question_template"]:
                    continue
                seen.add(key)
                stems.append(stem)
    return stems


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
    strict_interests: bool = True,
    prefer_hamdan: bool = False,
    bank_balance: bool = True,
) -> list[dict]:
    """
    Pick up to n unique stem_ids.

    When the user selected favourite foods/hobbies and strict_interests=True
    (default), ONLY interest-matched stems are used — no cupcakes/baking
    fallback if those weren't picked.

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

        hamdan = [s for s in pool if (s.get("bank") or "") == "grade_1_hamdan"]
        classic = [s for s in pool if (s.get("bank") or "") != "grade_1_hamdan"]

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

    return _fix_repeated_name_pronouns(
        text,
        child_name=child,
        child_gender=child_gender,
        family_names=family_names,
    )


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
    family_names: dict | None = None,
    face_paths: dict[str, str] | None = None,
    child_gender: str = "",
    out_dir: Path | str | None = None,
    on_progress=None,
    skip_on_error: bool = True,
    **kwargs,
) -> tuple[list[dict], list[dict]]:
    """
    Generate personalised workbook items using the AI generation pipeline
    (prompt.md + question + uploaded photos as visual reference).
    """
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
    )
