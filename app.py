"""
Main Streamlit app — Personalised Maths Question Generator
Question bank personalisation + interactive kitchen & hobby templates
(role layout + object placeholders + direct object interaction beautify).
"""

import os
import time
import re
import itertools
import tempfile
from io import BytesIO

import streamlit as st

from file_handlers import get_topics_for_grade, load_sample_questions
from pdf_generator import generate_pdf, cleanup_temp_images, build_workbook_title
from utils import create_safe_filename

# Object keywords still used for hobby/category text substitution in questions
from blueprint_generator import OBJECT_KEYWORDS

# Interactive role templates — kitchen + hobby scene families
from interactive_templates.compositor import (
    compose_interactive_scene,
    food_label_to_object_id,
    hobby_label_to_object_id,
    list_interactive_foods,
    list_interactive_hobbies,
    list_interactive_roles,
)

# Question-bank RAG → image-grounded topic questions
from question_rag.generator import generate_image_grounded_questions
from question_rag.retriever import list_question_bank_topics, resolve_topic

# ------------------------------------------------------------------------------
# Hobby → object mapping
# ------------------------------------------------------------------------------
_HOBBY_MAP = [
    (["football", "soccer", "rugby", "basketball", "tennis", "cricket", "baseball",
      "volleyball", "hockey", "golf", "sports", "ball", "sport", "athletic",
      "bounce", "bouncy", "throw", "catch", "bowling"], "football"),
    (["kite", "kites", "flying a kite"], "kite"),
    (["frisbee", "frisbees", "disc"], "frisbee"),
    (["bubble", "bubbles", "bubble wand"], "bubble wand"),
    (["reading", "books", "book", "story", "stories", "library", "reader"], "book"),
    (["drawing", "art", "painting", "sketch", "coloring", "colouring", "paint",
      "sketching", "artist", "creative"], "crayon"),
    (["crayons", "crayon", "color", "colour", "colors", "colours"], "crayon"),
    (["cooking", "baking", "kitchen", "food", "cake", "cupcake", "chef", "bake"], "cookie"),
    (["music", "singing", "song", "guitar", "piano", "drum", "drums", "musical",
      "dancing", "dance", "ballet", "singer", "choir"], "star"),
    (["cars", "racing", "trucks", "car", "truck", "vehicle", "vehicles",
      "race", "auto", "automobile"], "toy car"),
    (["dolls", "doll", "fashion", "princess", "pony", "ponies", "dress"], "doll"),
    (["blocks", "building", "lego", "construction", "build", "block",
      "architect", "tower"], "block"),
    (["gardening", "flowers", "garden", "nature", "plants", "plant", "flower",
      "outdoor", "seeds", "grow"], "flower"),
    (["swimming", "pool", "fish", "fishes", "fishing", "aquarium", "ocean", "sea"], "fish"),
    (["butterfly", "butterflies", "insects", "bug", "bugs", "caterpillar"], "butterfly"),
    (["trains", "train", "railway", "railroad", "locomotive", "choo"], "train"),
    (["planes", "plane", "airplane", "aeroplane", "flying", "flight", "jet",
      "pilot", "aviation"], "plane"),
    (["boats", "boat", "ships", "ship", "sailing", "sail", "sailor", "navy"], "boat"),
    (["bicycle", "bike", "cycling", "bikes", "bicycles", "cycle", "cyclist"], "bicycle"),
    (["robots", "robot", "tech", "technology", "coding", "programming",
      "computer", "gadget"], "robot"),
    (["teddy", "teddy bear", "teddy bears", "stuffed", "plush", "soft toy", "soft"], "teddy bear"),
    (["balloons", "balloon", "party", "celebrate", "celebration"], "balloon"),
    (["stickers", "sticker", "sticker collecting"], "sticker"),
    (["marbles", "marble"], "marble"),
    (["shells", "shell", "seashell", "beach", "sand", "ocean"], "shell"),
    (["eggs", "egg", "easter", "chick", "chicks"], "egg"),
    (["candy", "candies", "sweets", "sweet", "chocolate", "lollipop", "lollipops",
      "candies", "candy floss", "gummy"], "candy"),
    (["fruit", "fruits", "apple", "banana", "orange", "grapes", "grape", "strawberry",
      "strawberries", "pear", "pears", "lemon", "lemons", "cherry", "cherries",
      "watermelon", "healthy"], "apple"),
    (["pencils", "pencil", "writing", "write", "pen", "pens", "eraser", "erasers",
      "stationery", "school"], "pencil"),
    (["coins", "coin", "money", "treasure", "treasury", "bank", "save"], "coin"),
    (["cookies", "cookie", "biscuit", "biscuits", "snack", "snacks", "treat", "treats",
      "chocolate cookie"], "cookie"),
    (["puzzles", "puzzle", "jigsaw", "board game", "games", "game"], "star"),
]

_HOBBY_FALLBACK = "sticker"

# Free-text hobby → interactive hobby UI label (must match list_interactive_hobbies)
_INTERACTIVE_HOBBY_HINTS = [
    (["football", "soccer", "ball", "sports"], "Football"),
    (["crayon", "colouring", "coloring", "drawing", "sketch"], "Crayons"),
    (["paint", "painting", "art", "artist"], "Painting"),
    (["kite"], "Kite"),
    (["frisbee", "disc"], "Frisbee"),
    (["bubble"], "Bubbles"),
]

# ------------------------------------------------------------------------------
# Number scaling helper
# ------------------------------------------------------------------------------
def _scale_question_numbers(question: str, max_val: int) -> str:
    """Scale all numbers in a question so the largest ≤ max_val."""
    import random as _random
    numbers = [int(n) for n in re.findall(r'\b\d+\b', question)]
    if not numbers:
        return question
    old_max = max(numbers)
    if old_max <= 0 or old_max >= max_val:
        return question
    new_max = _random.randint(old_max, max_val)
    scale = new_max / old_max

    def _scale(m):
        val = int(m.group(0))
        return str(max(1, round(val * scale)))

    return re.sub(r'\b\d+\b', _scale, question)


def map_hobby_to_object(hobby_text: str) -> str | None:
    """Return the singular object keyword matching the user's hobby, or None."""
    if not hobby_text or not hobby_text.strip():
        return None
    text_lower = hobby_text.lower().strip()
    for keywords, obj in _HOBBY_MAP:
        for kw in keywords:
            if kw.lower() in text_lower:
                return obj
    return _HOBBY_FALLBACK


def suggest_interactive_hobby_label(hobby_text: str, available: list[str]) -> str | None:
    """Map free-text hobbies to an interactive hobby UI label when possible."""
    if not hobby_text or not available:
        return None
    text_lower = hobby_text.lower().strip()
    available_l = {a.lower(): a for a in available}
    for keywords, label in _INTERACTIVE_HOBBY_HINTS:
        if any(kw in text_lower for kw in keywords):
            if label.lower() in available_l:
                return available_l[label.lower()]
    # Exact / substring match against available labels
    for label in available:
        if label.lower() in text_lower:
            return label
    return None


def _pluralize(word: str) -> str:
    """Simple pluralization for objects used in questions."""
    overrides = {
        "toy car": "toy cars",
        "teddy bear": "teddy bears",
        "bubble wand": "bubble wands",
        "paintbrush": "paintbrushes",
        "football": "footballs",
        "kite": "kites",
        "frisbee": "frisbees",
    }
    if word in overrides:
        return overrides[word]
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    return word + "s"


# Container/furniture words in OBJECT_KEYWORDS that should NOT be replaced
_SKIP_OBJECTS = frozenset({
    "box", "bowl", "bottle", "cup", "plate", "bag", "basket",
    "table", "chair", "bed", "desk", "shelf", "cabinet",
    "tree", "house", "door", "window", "wall", "floor",
})


def replace_objects_in_text(text: str, hobby_obj: str) -> str:
    """Replace any known object word in text with the hobby object (matching plurality)."""
    if not hobby_obj:
        return text
    hobby_plural = _pluralize(hobby_obj)

    known = sorted(OBJECT_KEYWORDS, key=len, reverse=True)

    for obj in known:
        if obj.lower() in _SKIP_OBJECTS:
            continue
        pat = re.compile(r'\b' + re.escape(obj) + r'(?:s|es)?\b', re.IGNORECASE)
        if not pat.search(text):
            continue

        def _replacer(m: re.Match, o: str = obj) -> str:
            raw = m.group(0)
            raw_lower = raw.lower()
            stem = raw_lower[:-2] if raw_lower.endswith("es") else (
                raw_lower[:-1] if raw_lower.endswith("s") and not raw_lower.endswith("ss")
                else raw_lower
            )
            if stem == hobby_obj.lower():
                return raw
            if raw_lower.endswith(("es", "s")) and not raw_lower.endswith("ss"):
                return hobby_plural
            return hobby_obj

        text = pat.sub(_replacer, text)

    return text


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
_IMAGE_CONTEXT_OBJECTS = frozenset({
    "apple", "apples", "banana", "bananas", "orange", "oranges", "grape", "grapes",
    "cookie", "cookies", "biscuit", "biscuits", "cupcake", "cupcakes",
    "pizza", "pizzas", "pizza slice", "pizza slices",
    "smoothie", "smoothies", "smoothie glass", "smoothie glasses",
    "burger", "burgers", "noodle", "noodles", "ice cream", "ice creams",
    "chocolate", "chocolates", "pancake", "pancakes", "pasta", "pastas",
    "football", "footballs", "crayon", "crayons", "paintbrush", "paintbrushes",
    "kite", "kites", "frisbee", "frisbees", "bubble wand", "bubble wands",
    "bubble", "bubbles",
})


def _normalise_image_object(meta: dict) -> tuple[str, str]:
    """Return singular/plural object labels to use in final worksheet text."""
    obj = (meta.get("objects") or [{}])[0]
    obj_type = str(obj.get("type") or "").strip().lower()
    description = str(obj.get("description") or "").strip().lower()

    explicit = {
        "pizza": ("pizza slice", "pizza slices"),
        "smoothies": ("smoothie glass", "smoothie glasses"),
        "chocolates": ("chocolate", "chocolates"),
        "cupcakes": ("cupcake", "cupcakes"),
        "cookies": ("cookie", "cookies"),
        "burgers": ("burger", "burgers"),
        "noodles": ("noodle", "noodles"),
        "pancakes": ("pancake", "pancakes"),
        "apples": ("apple", "apples"),
        "pasta": ("pasta", "pasta"),
        "ice cream": ("ice cream", "ice creams"),
        "ice_cream": ("ice cream", "ice creams"),
        "football": ("football", "footballs"),
        "crayons": ("crayon", "crayons"),
        "painting": ("paintbrush", "paintbrushes"),
        "kite": ("kite", "kites"),
        "frisbee": ("frisbee", "frisbees"),
        "bubbles": ("bubble wand", "bubble wands"),
    }
    if obj_type in explicit:
        return explicit[obj_type]

    if description:
        for phrase in sorted(_IMAGE_CONTEXT_OBJECTS, key=len, reverse=True):
            if phrase in description:
                if phrase.endswith("s"):
                    singular = phrase[:-1] if phrase not in ("pasta",) else phrase
                    return singular, phrase
                return phrase, _pluralize(phrase)

    if obj_type:
        if obj_type.endswith("s"):
            singular = obj_type[:-1]
            return singular, obj_type
        return obj_type, _pluralize(obj_type)

    return "item", "items"


def _replace_visible_count(text: str, count: int) -> str:
    """Update the primary object count in a question without touching comparison thresholds."""
    protected_phrases = ("more than", "less than", "fewer than", "greater than", "at least", "at most")
    matches = list(re.finditer(r"\b\d+\b", text))
    if not matches:
        return text

    for match in matches:
        before = text[max(0, match.start() - 20):match.start()].lower()
        if any(before.rstrip().endswith(phrase) for phrase in protected_phrases):
            continue
        return text[:match.start()] + str(count) + text[match.end():]
    return text


_ADULT_ROLES = ("mother", "father", "grandmother", "grandfather")

_ROLE_GENERIC_WORDS = {
    "mother": ["mother", "mum", "mom", "mommy", "mummy"],
    "father": ["father", "dad", "daddy"],
    "grandmother": ["grandmother", "grandma", "granny", "nana"],
    "grandfather": ["grandfather", "grandpa", "grandad", "granddad"],
}


def _detect_primary_adult_role(
    questions: list[str],
    *,
    available_roles: list[str],
    filled_roles: list[str] | None = None,
) -> str | None:
    """Pick the adult role the worksheet image should use from question context."""
    if not available_roles:
        return None

    available = [r for r in available_roles if r in _ADULT_ROLES]
    if not available:
        return None

    counts = {r: 0 for r in available}
    for q in questions:
        q_l = q.lower()
        for role in available:
            if f"{{{role}_name}}" in q_l:
                counts[role] += 2
            for word in _ROLE_GENERIC_WORDS.get(role, []):
                if re.search(rf"\b{re.escape(word)}\b", q_l):
                    counts[role] += 1

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], available.index(kv[0])))
    if ranked and ranked[0][1] > 0:
        return ranked[0][0]

    filled = [r for r in (filled_roles or []) if r in available]
    if filled:
        return filled[0]
    return available[0]


def _rewrite_roles_to_image_adult(
    text: str,
    adult_role: str,
    family_names: dict[str, str] | None = None,
) -> str:
    """Collapse adult role mentions onto the single adult present in the image."""
    family_names = family_names or {}
    target_name = (family_names.get(adult_role) or "").strip() or adult_role
    skip_names = {
        "mother", "father", "grandmother", "grandfather",
        "mum", "dad", "grandma", "grandad",
    }

    for role in _ADULT_ROLES:
        if role == adult_role:
            continue
        custom = (family_names.get(role) or "").strip()
        if custom and custom.lower() not in skip_names:
            text = re.sub(rf"\b{re.escape(custom)}\b", target_name, text, flags=re.IGNORECASE)
        for word in sorted(_ROLE_GENERIC_WORDS.get(role, []), key=len, reverse=True):
            text = re.sub(rf"\b{re.escape(word)}\b", target_name, text, flags=re.IGNORECASE)

    for word in sorted(_ROLE_GENERIC_WORDS.get(adult_role, []), key=len, reverse=True):
        if word.lower() == target_name.lower():
            continue
        text = re.sub(rf"\b{re.escape(word)}\b", target_name, text, flags=re.IGNORECASE)

    escaped = re.escape(target_name)
    text = re.sub(rf"\b{escaped}\s+and\s+{escaped}\b", target_name, text, flags=re.IGNORECASE)
    return text


def _rewrite_question_to_image_context(
    question: str,
    meta: dict,
    *,
    family_names: dict[str, str] | None = None,
) -> str:
    """Align final worksheet question wording to the chosen image template metadata."""
    obj = (meta.get("objects") or [{}])[0]
    count = int(obj.get("count") or 0)
    singular_label, plural_label = _normalise_image_object(meta)

    rewritten = question

    family = [str(x).strip().lower() for x in (meta.get("family") or []) if str(x).strip().lower() != "child"]
    adult_role = family[0] if family else None
    if adult_role:
        rewritten = _rewrite_roles_to_image_adult(rewritten, adult_role, family_names)

    # Replace known objects once, skipping the target labels themselves.
    target_forms = {
        singular_label.lower(),
        plural_label.lower(),
    }
    all_known = sorted(set(OBJECT_KEYWORDS).union(_IMAGE_CONTEXT_OBJECTS), key=len, reverse=True)
    for phrase in all_known:
        phrase_l = phrase.lower()
        if phrase_l in _SKIP_OBJECTS or phrase_l in target_forms:
            continue
        # Avoid rewriting fragments of the target label (e.g. "pizza" inside "pizza slices")
        if phrase_l in singular_label.lower() or phrase_l in plural_label.lower():
            continue
        pat = re.compile(r"\b" + re.escape(phrase) + r"(?:s|es)?\b", re.IGNORECASE)
        if not pat.search(rewritten):
            continue

        def _obj_replacer(m: re.Match, p: str = phrase_l) -> str:
            raw = m.group(0)
            raw_lower = raw.lower()
            is_plural = raw_lower != p and raw_lower.endswith("s") and not raw_lower.endswith("ss")
            replacement = plural_label if is_plural else singular_label
            if raw[:1].isupper():
                replacement = replacement[:1].upper() + replacement[1:]
            return replacement

        rewritten = pat.sub(_obj_replacer, rewritten)

    if count > 0:
        rewritten = _replace_visible_count(rewritten, count)
        # Prefer plural noun immediately after the synced visual count.
        if count != 1:
            rewritten = re.sub(
                rf"\b{count}\s+{re.escape(singular_label)}\b",
                f"{count} {plural_label}",
                rewritten,
                flags=re.IGNORECASE,
            )

    rewritten = re.sub(
        r"(?i)how many [^?]+ can you count\?",
        f"How many {plural_label} can you count?",
        rewritten,
    )
    rewritten = re.sub(
        r"(?i)how many [^?]+ are there\?",
        f"How many {plural_label} are there?",
        rewritten,
    )

    return rewritten


def _is_picture_compatible_question(question: str) -> bool:
    """
    True if a bank question can be fully count-locked to one picture
    (single visible object count). Addition / multiplication with multiple
    numbers are NOT compatible — they should still be kept as topic questions,
    just object-personalised (see _personalise_bank_question_for_scene).
    """
    q = (question or "").strip()
    if not q:
        return False
    q_l = q.lower()

    if any(bad in q_l for bad in (
        "shape", "shapes", "flying in", "sitting in the tree",
        "on a shelf", "another shelf",
    )):
        return False

    # Multiplication / multi-count addition must keep their own numbers
    if "groups of" in q_l or "sets of" in q_l or "×" in q or "x " in q_l:
        return False

    protected = ("more than", "less than", "fewer than", "greater than", "at least", "at most")
    nums = []
    for m in re.finditer(r"\b\d+\b", q):
        before = q_l[max(0, m.start() - 20):m.start()]
        if any(before.rstrip().endswith(p) for p in protected):
            continue
        nums.append(int(m.group(0)))

    if len(nums) >= 2:
        return False

    if "look at the picture" in q_l:
        return True
    if re.search(r"how many .+ (can you (count|see)|are there|do they have)", q_l):
        return True
    if len(nums) <= 1:
        return True
    return False


def _classify_math_kind(question: str) -> str:
    """Rough Year-1 operation label for diversity tracking."""
    q = (question or "").lower()
    if any(x in q for x in ("groups of", "sets of", "×", "times ", "multiply")):
        return "multiply"
    if any(x in q for x in ("take away", "left", "subtract", "minus", "fewer than", "how many fewer")):
        return "subtract"
    if any(x in q for x in ("altogether", "in total", "plus", "add ", "more than", "how many more")):
        # "how many more" is compare/add-ish; "altogether" with 2+ nums is add
        nums = re.findall(r"\b\d+\b", q)
        if len(nums) >= 2 or "altogether" in q or "in total" in q or "plus" in q or "add " in q:
            return "add"
    if any(x in q for x in ("more than", "less than", "fewer than", "greater than")):
        return "compare"
    if any(x in q for x in ("how many", "count", "can you see")):
        return "count"
    return "other"


def _replace_objects_with_scene_labels(text: str, singular_label: str, plural_label: str) -> str:
    """Swap known object words for the scene object; keep numbers and structure."""
    rewritten = text
    target_forms = {singular_label.lower(), plural_label.lower()}
    all_known = sorted(set(OBJECT_KEYWORDS).union(_IMAGE_CONTEXT_OBJECTS), key=len, reverse=True)
    for phrase in all_known:
        phrase_l = phrase.lower()
        if phrase_l in _SKIP_OBJECTS or phrase_l in target_forms:
            continue
        if phrase_l in singular_label.lower() or phrase_l in plural_label.lower():
            continue
        pat = re.compile(r"\b" + re.escape(phrase) + r"(?:s|es)?\b", re.IGNORECASE)
        if not pat.search(rewritten):
            continue

        def _obj_replacer(m: re.Match, p: str = phrase_l) -> str:
            raw = m.group(0)
            raw_lower = raw.lower()
            is_plural = raw_lower != p and raw_lower.endswith("s") and not raw_lower.endswith("ss")
            replacement = plural_label if is_plural else singular_label
            if raw[:1].isupper():
                replacement = replacement[:1].upper() + replacement[1:]
            return replacement

        rewritten = pat.sub(_obj_replacer, rewritten)
    return rewritten


def _adults_mentioned(text: str, family_names: dict[str, str] | None = None) -> list[str]:
    """Return adult roles referenced in text (by custom name or generic word)."""
    family_names = family_names or {}
    found = []
    q = text or ""
    for role in _ADULT_ROLES:
        custom = (family_names.get(role) or "").strip()
        if custom and re.search(rf"\b{re.escape(custom)}\b", q, flags=re.IGNORECASE):
            found.append(role)
            continue
        for word in _ROLE_GENERIC_WORDS.get(role, []):
            if re.search(rf"\b{re.escape(word)}\b", q, flags=re.IGNORECASE):
                found.append(role)
                break
    # unique preserve order
    out = []
    for r in found:
        if r not in out:
            out.append(r)
    return out


def _personalise_bank_question_for_scene(
    question: str,
    meta: dict,
    family_names: dict[str, str] | None = None,
) -> str:
    """
    Keep the bank question's maths (addition / multiplication / etc.),
    but swap objects (and adult when it's a single-adult story) to match
    the illustration theme. Only count-lock when the question is a pure
    single-count picture question.
    """
    family_names = family_names or {}
    kind = _classify_math_kind(question)

    # Pure counting → fully ground to visible placeholder count
    if kind == "count" and _is_picture_compatible_question(question):
        return _rewrite_question_to_image_context(
            question, meta, family_names=family_names
        )

    singular_label, plural_label = _normalise_image_object(meta)
    rewritten = _replace_objects_with_scene_labels(question, singular_label, plural_label)

    family = [
        str(x).strip().lower()
        for x in (meta.get("family") or [])
        if str(x).strip().lower() != "child"
    ]
    adult_role = family[0] if family else "mother"

    # Single-adult stories (typical multiplication) → match the scene adult
    # Multi-adult addition → keep everyone's names; only objects change
    if len(_adults_mentioned(rewritten, family_names)) <= 1:
        rewritten = _rewrite_roles_to_image_adult(rewritten, adult_role, family_names)

    return rewritten


def _picture_scene_labels(meta: dict, family_names: dict[str, str] | None = None) -> dict:
    family_names = family_names or {}
    obj = (meta.get("objects") or [{}])[0]
    count = int(obj.get("count") or 0)
    singular, plural = _normalise_image_object(meta)
    family = [str(x).strip().lower() for x in (meta.get("family") or []) if str(x).strip().lower() != "child"]
    adult_role = family[0] if family else "mother"
    adult_name = (family_names.get(adult_role) or "").strip() or adult_role
    scene_family = str(meta.get("scene_family") or "kitchen").strip().lower()
    if scene_family == "hobby":
        place = "the park"
        surface = "the picnic table"
        activity = "playing"
    else:
        place = "the kitchen"
        surface = "the counter"
        activity = "cooking"
    return {
        "count": count,
        "singular": singular,
        "plural": plural,
        "adult_role": adult_role,
        "adult_name": adult_name,
        "scene_family": scene_family,
        "place": place,
        "surface": surface,
        "activity": activity,
    }


def _picture_native_question_pool(meta: dict, family_names: dict[str, str] | None = None) -> list[str]:
    """Diverse question patterns that are always true for the composed picture."""
    s = _picture_scene_labels(meta, family_names)
    return _picture_native_builders(s)


def _picture_native_builders(s: dict) -> list[str]:
    """Build a varied Year-1 question list for one scene (count + add/sub/mult)."""
    count, plural, singular = s["count"], s["plural"], s["singular"]
    adult, place, surface, activity = s["adult_name"], s["place"], s["surface"], s["activity"]
    pool = [
        # Counting
        f"Look at the picture! How many {plural} can you count?",
        f"Look at the picture! You and {adult} are in {place}. How many {plural} are there altogether?",
        f"Look at the picture! Are there more than 2 {plural}?",
        f"Look at the picture! Who is with you in {place}?",
        f"Look at the picture! What are you and {adult} doing?",
        f"Look at the picture! Count the {plural}. How many can you see?",
        f"Look at the picture! How many {plural} are on {surface}?",
        f"Look at the picture! Write the number of {plural} you can see.",
        # Comparison
        f"Look at the picture! Are there fewer than 10 {plural}?",
        f"Look at the picture! Are there fewer than 5 {plural}?",
        f"Look at the picture! Are there more {plural} than people?",
    ]
    if count > 0:
        pool.extend([
            f"Look at the picture! There are {count} {plural} on {surface}. How many {plural} can you count?",
            # Addition (picture count + extra)
            f"Look at the picture! You can see {count} {plural}. {adult} brings 2 more. How many {plural} are there altogether?",
            f"Look at the picture! There are {count} {plural}. If you get 1 more, how many {plural} will there be?",
            # Subtraction
            f"Look at the picture! There are {count} {plural}. If you give 1 {singular} to {adult}, how many are left?",
            f"Look at the picture! If you take away 1 {singular}, how many {plural} are left?",
            # Multiplication-style
            f"Look at the picture! {adult} makes 2 groups of {max(1, count // 2)} {plural}. How many {plural} is that altogether?",
            f"Look at the picture! If each person gets 1 {singular}, how many people can share the {plural} you can see?",
        ])
        if count >= 2 and count % 2 == 0:
            pool.append(
                f"Look at the picture! The {count} {plural} are shared into 2 equal groups. How many in each group?"
            )
    # De-dupe while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for q in pool:
        key = q.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(q)
    return unique


def _question_type_key(
    question: str,
    meta: dict,
    family_names: dict[str, str] | None = None,
) -> str:
    """
    Normalise a question so the same *type* matches across roles/objects.
    Includes maths kind so addition ≠ counting ≠ multiplication.
    """
    s = _picture_scene_labels(meta, family_names)
    kind = _classify_math_kind(question)
    text = (question or "").strip().lower()
    tokens = sorted(
        {
            s.get("adult_name", ""),
            s.get("plural", ""),
            s.get("singular", ""),
            s.get("place", ""),
            s.get("surface", ""),
            s.get("activity", ""),
            "the kitchen",
            "the park",
            "the counter",
            "the picnic table",
            "cooking",
            "playing",
        },
        key=lambda x: len(str(x) or ""),
        reverse=True,
    )
    for tok in tokens:
        t = (tok or "").strip().lower()
        if len(t) < 2:
            continue
        text = text.replace(t, "X")
    text = re.sub(r"\b\d+\b", "N", text)
    text = re.sub(r"[^a-z0-9x\s?]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return f"{kind}::{text}"


def _pick_unique_picture_question(
    *,
    meta: dict,
    family_names: dict[str, str],
    bank_candidate: str | None,
    used_exact: set[str],
    used_types: set[str],
    pattern_cursor: int,
) -> tuple[str, int]:
    """
    Prefer the topic bank question (addition / multiplication / …), personalised
    to the scene. Fall back to a varied picture-native pool only when needed.
    """
    pool = _picture_native_question_pool(meta, family_names)
    n_pool = max(1, len(pool))

    candidates: list[str] = []
    if bank_candidate and str(bank_candidate).strip():
        # Always keep topic bank structure — do not require picture-compatibility
        candidates.append(
            _personalise_bank_question_for_scene(
                bank_candidate, meta, family_names=family_names
            )
        )
    for offset in range(n_pool):
        candidates.append(pool[(pattern_cursor + offset) % n_pool])

    chosen = None
    chosen_offset = 0
    for i, q in enumerate(candidates):
        exact = q.strip().lower()
        typ = _question_type_key(q, meta, family_names)
        if not exact or exact in used_exact or typ in used_types:
            continue
        chosen = q
        if i >= 1:
            chosen_offset = min(i, n_pool)
        else:
            chosen_offset = 1
        break

    if chosen is None:
        s = _picture_scene_labels(meta, family_names)
        n = len(used_exact) + 1
        kind_cycle = ["add", "multiply", "subtract", "count"][(n - 1) % 4]
        if kind_cycle == "add":
            chosen = (
                f"Look at the picture! You see some {s['plural']}. "
                f"{s['adult_name']} gives you 2 more. How many {s['plural']} altogether?"
            )
        elif kind_cycle == "multiply":
            chosen = (
                f"Look at the picture! {s['adult_name']} has 2 groups of 2 {s['plural']}. "
                f"How many {s['plural']} are there altogether?"
            )
        elif kind_cycle == "subtract":
            chosen = (
                f"Look at the picture! If 1 {s['singular']} is eaten, "
                f"how many {s['plural']} are left from what you can see?"
            )
        else:
            chosen = (
                f"Look at the picture! Question {n}: how many {s['plural']} "
                f"can you and {s['adult_name']} see together?"
            )
        chosen_offset = 1

    used_exact.add(chosen.strip().lower())
    used_types.add(_question_type_key(chosen, meta, family_names))
    return chosen, (pattern_cursor + max(1, chosen_offset)) % n_pool


def _build_questions_for_picture(
    bank_questions: list[str],
    meta: dict,
    *,
    family_names: dict[str, str] | None = None,
    num_questions: int | None = None,
) -> list[str]:
    """
    Build worksheet questions from the topic bank first (keep addition /
    multiplication structure), personalised to the scene. Fill gaps from a
    mixed picture-native pool.
    """
    n = num_questions or len(bank_questions) or 5
    family_names = family_names or {}
    final: list[str] = []
    used_exact: set[str] = set()
    used_types: set[str] = set()
    cursor = 0

    bank_iter = [q for q in bank_questions if str(q).strip()]
    bi = 0
    while len(final) < n:
        bank_q = bank_iter[bi] if bi < len(bank_iter) else None
        bi += 1
        q, cursor = _pick_unique_picture_question(
            meta=meta,
            family_names=family_names,
            bank_candidate=bank_q,
            used_exact=used_exact,
            used_types=used_types,
            pattern_cursor=cursor,
        )
        final.append(q)

    return final[:n]


def _sync_questions_to_image_metadata(
    questions: list[str],
    meta: dict,
    *,
    family_names: dict[str, str] | None = None,
) -> list[str]:
    """Ground worksheet questions in the composed picture (count/object/role)."""
    return _build_questions_for_picture(
        questions,
        meta,
        family_names=family_names,
        num_questions=len(questions) if questions else None,
    )


# ------------------------------------------------------------------------------
# Page setup
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="My Maths Practice Book — Year 1",
    page_icon="📚",
    layout="centered"
)

st.title("📚 My Maths Practice Book")
st.write(
    "Create a personalised Year 1 maths workbook with fun illustrations! "
    "Tell us about your child — favourite colour, family, and "
    "favourite foods & hobbies — and we'll make a worksheet that feels like it's just for them. "
    "Questions are RAG-generated from the `question_bank` by topic and grounded in "
    "each kitchen/hobby illustration."
)

# Pipeline state
if "pipeline" not in st.session_state:
    st.session_state.pipeline = None

# ------------------------------------------------------------------------------
# Student Information form
# ------------------------------------------------------------------------------
st.subheader("👤 About Your Child")

col_name, col_gen, col_age = st.columns(3)
with col_name:
    student_name = st.text_input("Name*", placeholder="e.g., Oliver")
with col_gen:
    gender = st.selectbox("Gender*", ["Select", "Boy", "Girl", "Other"])
with col_age:
    child_age = st.number_input("Age", min_value=4, max_value=8, value=6)

fav_color = st.text_input(
    "Favourite Colour",
    placeholder="e.g., green, pink",
    help="Used for workbook colour theme (PDF accents)",
)

st.markdown("#### Family")
row_fam1 = st.columns(2)
with row_fam1[0]:
    mother_name = st.text_input("Mum's Name", placeholder="Optional")
with row_fam1[1]:
    father_name = st.text_input("Dad's Name", placeholder="Optional")
row_fam2 = st.columns(2)
with row_fam2[0]:
    grandmother_name = st.text_input("Grandma's Name", placeholder="Optional")
with row_fam2[1]:
    grandfather_name = st.text_input("Grandad's Name", placeholder="Optional")

st.markdown("#### Siblings")
if "siblings_list" not in st.session_state:
    st.session_state.siblings_list = []
for i, sib in enumerate(st.session_state.siblings_list):
    scols = st.columns([2, 1, 0.3])
    with scols[0]:
        st.session_state.siblings_list[i]["name"] = st.text_input(
            f"Sibling {i+1} Name", value=sib.get("name", ""), placeholder="e.g., Jack", key=f"sib_name_{i}")
    with scols[1]:
        st.session_state.siblings_list[i]["gender"] = st.selectbox(
            "Gender", ["Boy", "Girl"],
            index=0 if sib.get("gender", "Boy") == "Boy" else 1,
            key=f"sib_gender_{i}")
    with scols[2]:
        st.write('<p style="margin-bottom:2px">&nbsp;</p>', unsafe_allow_html=True)
        if st.button("✕", key=f"sib_del_{i}"):
            st.session_state.siblings_list.pop(i)
            st.rerun()
if st.button("+ Add Sibling", key="add_sib"):
    st.session_state.siblings_list.append({"name": "", "gender": "Boy"})
    st.rerun()

# --- Interactive scenes: Favourite Foods (kitchen) + Hobbies (park) ---
st.divider()
st.markdown("#### 🍳 Favourite Foods & 🎨 Hobbies")
st.caption(
    "Pick one or more foods and/or hobbies. Each food uses kitchen role templates; "
    "each hobby uses park templates. Named family roles each get a scene per selected "
    "item. Questions rotate across those scenes so wording and pictures stay matched. "
    "Placeholder count is locked so the picture always matches the question count."
)
_available_foods = list_interactive_foods()
_available_hobbies = list_interactive_hobbies()
_kitchen_roles = list_interactive_roles("kitchen")
_hobby_roles = list_interactive_roles("hobby")

_col_food, _col_hobby = st.columns(2)
with _col_food:
    favourite_foods = st.multiselect(
        "Favourite Foods",
        options=_available_foods,
        default=[],
        key="favourite_foods_picker",
        help="Kitchen scene objects. Select multiple to rotate questions across foods.",
    )
with _col_hobby:
    favourite_hobbies = st.multiselect(
        "Favourite Hobby Objects",
        options=_available_hobbies,
        default=[],
        key="favourite_hobbies_picker",
        help="Park/hobby scene objects. Select multiple to rotate questions across hobbies.",
    )

if favourite_foods:
    if _kitchen_roles:
        st.info(
            f"🍳 **{', '.join(favourite_foods)}** → kitchen roles: "
            + ", ".join(_kitchen_roles)
        )
    else:
        st.warning(
            "⚠️ No interactive kitchen role templates found. "
            "Run: python -m interactive_templates.generate_role_templates"
        )
elif not _available_foods:
    st.warning("⚠️ No interactive food object specs found under interactive_templates/objects/food/.")

if favourite_hobbies:
    if _hobby_roles:
        st.info(
            f"🎨 **{', '.join(favourite_hobbies)}** → hobby/park roles: "
            + ", ".join(_hobby_roles)
        )
    else:
        st.warning(
            "⚠️ No interactive hobby role templates found. "
            "Run: python -m interactive_templates.generate_hobby_role_templates"
        )
elif not _available_hobbies:
    st.warning("⚠️ No interactive hobby object specs found under interactive_templates/objects/hobby/.")

# ------------------------------------------------------------------------------
# Workbook & Picture Settings
# ------------------------------------------------------------------------------
st.divider()
col_ws1, col_ws2 = st.columns(2)
with col_ws1:
    _grade_map = {"Year 1 (age 5-6)": "Grade 1"}
    _grade_label = st.selectbox("Year Group*", ["Select Year", "Year 1 (age 5-6)"])
    grade = _grade_map.get(_grade_label, _grade_label)
with col_ws2:
    num_questions = int(st.number_input(
        "Number of questions",
        min_value=1,
        max_value=50,
        value=10,
        step=1,
        key="num_questions_input",
    ))

topics_for_grade = []
use_all_topics = False
selected_topics = []
if grade != "Select Grade":
    topics_for_grade = get_topics_for_grade(grade)
if grade == "Grade 1" and topics_for_grade:
    use_all_topics = st.checkbox("Use all topics", value=False)
    selected_topics = st.multiselect(
        "Topics", options=topics_for_grade,
        default=([] if not topics_for_grade else [topics_for_grade[0]]))
elif grade == "Grade 1" and not topics_for_grade:
    st.info("No topics found. Check that 'extracted_bank/grade_1_uk_year_1_templated_final_categories_visual_static.txt' is in place.")

col_ps1, col_ps2 = st.columns(2)
with col_ps1:
    include_images = st.checkbox("Include illustrations", value=True)
with col_ps2:
    counting_ability = st.selectbox("Biggest number to practise", [10, 20, 50], index=1)

# Final worksheet images always use a gentle soft-cartoon / storybook look.
image_style = "soft_cartoon"

anything_else = st.text_area(
    "Anything else for the pictures? (optional)",
    placeholder="e.g., loves dinosaurs, Christmas setting",
    help="Extra notes kept with the workbook metadata.")

# ------------------------------------------------------------------------------
# Face upload section (collapsible - only this stays collapsed)
# ------------------------------------------------------------------------------
saved_face_paths = {}
with st.expander("Upload Family Photos (for face swapping)", expanded=False):
    st.markdown("""
    <style>
    .face-upload-card {
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 12px;
        margin-bottom: 12px;
        background: #fafafa;
        text-align: center;
        min-height: 140px;
    }
    .face-upload-card .label {
        font-size: 14px;
        font-weight: 600;
        color: #333;
        margin-bottom: 6px;
    }
    .face-upload-card .uploaded {
        margin-top: 6px;
        font-size: 12px;
        color: #2e7d32;
    }
    </style>
    """, unsafe_allow_html=True)
    st.caption("Upload photos and we'll put your family's faces onto the characters in the illustrations!")

    if not os.path.exists("personalised_faces"):
        os.makedirs("personalised_faces")

    face_map = {}

    # --- Fixed family roles in a 3-column grid ---
    family_roles = [
        ("user",  "Child"),
        ("mother", "Mum"),
        ("father", "Dad"),
        ("grandmother", "Grandma"),
        ("grandfather", "Grandad"),
    ]
    fam_cols = st.columns(3)
    for i, (role_key, role_label) in enumerate(family_roles):
        with fam_cols[i % 3]:
            uploaded = st.file_uploader(role_label, type=["jpg", "png", "jpeg"],
                                         key=f"face_{role_key}")
            if uploaded:
                face_map[role_key] = uploaded
                st.image(uploaded, width=70)

    # --- Dynamic sibling uploads ---
    sib_list = st.session_state.get("siblings_list", [])
    if sib_list:
        st.markdown("---")
        sib_cols = st.columns(min(len(sib_list), 3))
        for sib_i, sib in enumerate(sib_list):
            with sib_cols[sib_i % 3]:
                sib_name = sib.get("name", "").strip() or f"Sibling {sib_i+1}"
                uploaded = st.file_uploader(sib_name, type=["jpg", "png", "jpeg"],
                                             key=f"sib_face_{sib_i}")
                if uploaded:
                    face_map[f"sibling_{sib_i}"] = uploaded
                    st.image(uploaded, width=70)

    for role, file in face_map.items():
        path = os.path.join("personalised_faces", f"{role}_face.png")
        with open(path, "wb") as f:
            f.write(file.getbuffer())
        saved_face_paths[role] = path

st.divider()

# ------------------------------------------------------------------------------
# Generate Button & Validation
# ------------------------------------------------------------------------------
if st.button("📝 Generate Personalised Workbook", type="primary"):

    # ---------- Validation ----------
    if not student_name.strip():
        st.warning("⚠️ Please enter the student's name.")
    elif gender == "Select":
        st.warning("⚠️ Please select the student's gender.")
    elif _grade_label == "Select Year":
        st.warning("⚠️ Please select a year group.")
    elif grade == "Grade 1" and not topics_for_grade:
        st.warning("⚠️ No topic files found for Grade 1.")
    elif include_images and not favourite_foods and not favourite_hobbies:
        st.warning("⚠️ Please select at least one favourite food and/or hobby for the worksheet illustrations.")
    else:
        # ---------- Topic plan (question_bank RAG) ----------
        n_requested = max(1, int(num_questions))
        if use_all_topics or not selected_topics:
            rag_topics = list(topics_for_grade) or list_question_bank_topics() or ["Numbers To 10"]
            topic_header_text = "All topics"
        else:
            rag_topics = list(selected_topics)
            topic_header_text = ", ".join(selected_topics)

        if not rag_topics:
            st.error("No topics available in question_bank. Add files under question_bank/grade_1/.")
            st.stop()

        resolved_topics = [resolve_topic(t) or t for t in rag_topics]
        rag_topics = resolved_topics
        question_topic_plan = [rag_topics[i % len(rag_topics)] for i in range(n_requested)]
        st.info(
            f"📚 Will RAG-generate **{n_requested}** image-grounded question(s) "
            f"from `question_bank` topics: " + ", ".join(dict.fromkeys(rag_topics))
        )
        with st.expander("📄 Topic plan + bank preview"):
            for i, t in enumerate(question_topic_plan, 1):
                st.write(f"{i}. {t}")
            preview = load_sample_questions(grade, rag_topics[0])
            if preview and not str(preview).startswith("Error"):
                st.text(preview[:700] + ("..." if len(preview) > 700 else ""))

        questions = [f"(generating {question_topic_plan[i]} question…)" for i in range(n_requested)]
        topic_hints = list(question_topic_plan)

        if not include_images:
            with st.spinner("📚 Generating topic questions from question_bank (RAG)..."):
                # Rotate synthetic metas across selected foods then hobbies
                object_cycle = []
                for food in favourite_foods:
                    object_cycle.append({
                        "scene_family": "kitchen",
                        "object_id": food_label_to_object_id(food),
                        "object_label": food,
                        "category": "food",
                    })
                for hobby in favourite_hobbies:
                    object_cycle.append({
                        "scene_family": "hobby",
                        "object_id": hobby_label_to_object_id(hobby),
                        "object_label": hobby,
                        "category": "hobby",
                    })
                if not object_cycle:
                    object_cycle = [{
                        "scene_family": "kitchen",
                        "object_id": "apples",
                        "object_label": "Apples",
                        "category": "food",
                    }]
                family_names_early = {
                    "mother": (mother_name or "").strip() or "mother",
                    "father": (father_name or "").strip() or "father",
                    "grandmother": (grandmother_name or "").strip() or "grandmother",
                    "grandfather": (grandfather_name or "").strip() or "grandfather",
                }
                questions = []
                for i in range(n_requested):
                    item = object_cycle[i % len(object_cycle)]
                    count = min(4, int(counting_ability))
                    oid = item["object_id"]
                    synth_meta = {
                        "scene_family": item["scene_family"],
                        "family": ["mother", "child"],
                        "objects": [{
                            "type": oid,
                            "count": count,
                            "description": f"{count} {oid.replace('_', ' ')}",
                        }],
                    }
                    batch = generate_image_grounded_questions(
                        image=None,
                        meta=synth_meta,
                        topics=[question_topic_plan[i]],
                        num_questions=1,
                        family_names=family_names_early,
                        child_name=student_name or "you",
                        counting_ability=int(counting_ability),
                        anything_else=anything_else or "",
                        siblings=st.session_state.get("siblings_list") or [],
                    )
                    questions.append(batch[0] if batch else f"How many {oid.replace('_', ' ')} can you count?")
            st.info(f"✅ Generated {len(questions)} question(s) via question_bank RAG")
            with st.expander("👀 Preview Generated Questions"):
                for i, q in enumerate(questions, 1):
                    st.write(f"{i}. {q}")

        # ---------- Store pipeline state ----------
        family_names = {
            "mother": (mother_name or "").strip() or "mother",
            "father": (father_name or "").strip() or "father",
            "grandmother": (grandmother_name or "").strip() or "grandmother",
            "grandfather": (grandfather_name or "").strip() or "grandfather",
        }
        filled_roles = [
            role for role, name in {
                "mother": mother_name,
                "father": father_name,
                "grandmother": grandmother_name,
                "grandfather": grandfather_name,
            }.items()
            if (name or "").strip()
        ]
        worksheet_roles = []
        scene_slots = []
        if include_images:
            if favourite_foods:
                kitchen_roles_avail = list_interactive_roles("kitchen")
                if not kitchen_roles_avail:
                    st.error(
                        "No interactive kitchen role templates found. "
                        "Run: python -m interactive_templates.generate_role_templates"
                    )
                    st.stop()
                food_roles = [r for r in filled_roles if r in kitchen_roles_avail]
                if not food_roles:
                    detected = _detect_primary_adult_role(
                        topic_hints,
                        available_roles=kitchen_roles_avail,
                        filled_roles=filled_roles,
                    )
                    food_roles = [detected] if detected else kitchen_roles_avail[:1]
                for food in favourite_foods:
                    food_oid = food_label_to_object_id(food)
                    for role in food_roles:
                        scene_slots.append({
                            "key": f"kitchen__{role}__{food_oid}",
                            "scene_family": "kitchen",
                            "adult_role": role,
                            "object_id": food_oid,
                            "category": "food",
                            "object_label": food,
                        })
                worksheet_roles.extend(food_roles)

            if favourite_hobbies:
                hobby_roles_avail = list_interactive_roles("hobby")
                if not hobby_roles_avail:
                    st.error(
                        "No interactive hobby role templates found. "
                        "Run: python -m interactive_templates.generate_hobby_role_templates"
                    )
                    st.stop()
                hobby_roles = [r for r in filled_roles if r in hobby_roles_avail]
                if not hobby_roles:
                    detected = _detect_primary_adult_role(
                        topic_hints,
                        available_roles=hobby_roles_avail,
                        filled_roles=filled_roles,
                    )
                    hobby_roles = [detected] if detected else hobby_roles_avail[:1]
                for hobby in favourite_hobbies:
                    hobby_oid = hobby_label_to_object_id(hobby)
                    for role in hobby_roles:
                        scene_slots.append({
                            "key": f"hobby__{role}__{hobby_oid}",
                            "scene_family": "hobby",
                            "adult_role": role,
                            "object_id": hobby_oid,
                            "category": "hobby",
                            "object_label": hobby,
                        })
                for r in hobby_roles:
                    if r not in worksheet_roles:
                        worksheet_roles.append(r)

            if not scene_slots:
                st.error("No scene templates available for the selected food/hobby.")
                st.stop()

            kitchen_slots = [s for s in scene_slots if s["scene_family"] == "kitchen"]
            hobby_slots = [s for s in scene_slots if s["scene_family"] == "hobby"]
            if kitchen_slots and hobby_slots:
                interleaved = []
                for pair in itertools.zip_longest(kitchen_slots, hobby_slots):
                    for s in pair:
                        if s is not None:
                            interleaved.append(s)
                scene_slots = interleaved

            slot_labels = [
                f"{s['scene_family']}/{s['adult_role']} ({family_names.get(s['adult_role'], s['adult_role'])} + {s['object_label']})"
                for s in scene_slots
            ]
            st.info(
                f"🎭 Using **{len(scene_slots)}** scene template(s); "
                f"composing only what **{n_requested}** question(s) need: "
                + ", ".join(slot_labels)
            )

        st.session_state.pipeline = {
            "phase": "illustrate" if include_images else "pdf",
            "questions": questions,
            "synced_questions": list(questions),
            "num_questions": int(n_requested),
            "question_topic_plan": question_topic_plan,
            "rag_topics": rag_topics,
            "student_name": student_name,
            "gender": gender,
            "child_age": child_age,
            "siblings_list": st.session_state.get("siblings_list", []),
            "grade": grade,
            "topic_header_text": topic_header_text,
            "include_images": include_images,
            "saved_face_paths": saved_face_paths,
            "image_paths": [],
            "fav_color": fav_color,
            "favourite_foods": list(favourite_foods),
            "favourite_hobbies": list(favourite_hobbies),
            "worksheet_roles": worksheet_roles,
            "scene_slots": scene_slots,
            "family_names": family_names,
            "counting_ability": counting_ability,
            "image_style": image_style,
            "anything_else": anything_else,
        }
        st.rerun()

# ══════════════════════════════════════════════════════════════════
# PIPELINE EXECUTOR
# ══════════════════════════════════════════════════════════════════
pipeline = st.session_state.get("pipeline")
if pipeline is not None:
    phase = pipeline["phase"]

    # ── Compose scenes, then question_bank RAG (image-grounded) ──
    if phase in ("illustrate", "kitchen"):
        from collections import defaultdict

        scene_slots = list(pipeline.get("scene_slots") or [])
        if not scene_slots:
            roles = list(pipeline.get("worksheet_roles") or ["mother"])
            foods = list(pipeline.get("favourite_foods") or [])
            # Back-compat with older single-food pipelines
            if not foods and pipeline.get("favourite_food"):
                foods = [pipeline.get("favourite_food")]
            for food in foods:
                oid = food_label_to_object_id(food)
                for role in roles:
                    if not role:
                        continue
                    scene_slots.append({
                        "key": f"kitchen__{role}__{oid}",
                        "scene_family": "kitchen",
                        "adult_role": role,
                        "object_id": oid,
                        "category": "food",
                        "object_label": food,
                    })

        family_names = pipeline.get("family_names") or {}
        n_q = int(pipeline.get("num_questions") or 0)
        if n_q <= 0:
            n_q = len(pipeline.get("questions") or pipeline.get("synced_questions") or [])
        n_q = max(1, n_q)

        topic_plan = list(pipeline.get("question_topic_plan") or pipeline.get("rag_topics") or ["Numbers To 10"])
        if not topic_plan:
            topic_plan = ["Numbers To 10"]
        if len(topic_plan) < n_q:
            topic_plan = [topic_plan[i % len(topic_plan)] for i in range(n_q)]
        else:
            topic_plan = topic_plan[:n_q]

        faces = pipeline.get("saved_face_paths") or {}
        photos = {
            "child": faces.get("user"),
            "mother": faces.get("mother"),
            "father": faces.get("father"),
            "grandmother": faces.get("grandmother"),
            "grandfather": faces.get("grandfather"),
        }

        slots_needed = []
        seen_keys = set()
        question_scene_keys = []
        for qi in range(n_q):
            slot = scene_slots[qi % len(scene_slots)]
            question_scene_keys.append(slot["key"])
            if slot["key"] not in seen_keys:
                seen_keys.add(slot["key"])
                slots_needed.append(slot)

        scene_results = {}
        progress = st.progress(0.0)
        for i, slot in enumerate(slots_needed):
            role = slot["adult_role"]
            family = slot["scene_family"]
            label = family_names.get(role) or role
            obj_label = slot.get("object_label") or slot.get("object_id")
            emoji = "🎨" if family == "hobby" else "🍳"
            place = "park/hobby" if family == "hobby" else "kitchen"
            with st.spinner(
                f"{emoji} [{i+1}/{len(slots_needed)}] Composing {label} {place} scene "
                f"with {obj_label}..."
            ):
                try:
                    result = compose_interactive_scene(
                        adult_role=role,
                        object_id=slot["object_id"],
                        photos=photos,
                        scene_family=family,
                        category=slot.get("category"),
                        beautify=True,
                        image_style=pipeline.get("image_style") or "soft_cartoon",
                    )
                except Exception as e:
                    st.error(f"❌ Interactive scene failed for **{family}/{role}**: {e}")
                    st.session_state.pipeline = None
                    st.stop()
                if not result or result.get("final_image") is None:
                    st.error(f"❌ No image produced for **{family}/{role}** / **{obj_label}**.")
                    st.session_state.pipeline = None
                    st.stop()
                scene_results[slot["key"]] = result
            progress.progress((i + 1) / max(1, len(slots_needed)))

        by_scene = defaultdict(list)
        for qi, key in enumerate(question_scene_keys):
            by_scene[key].append(qi)

        synced_questions = [""] * n_q
        with st.spinner("📚 Generating image-grounded questions (question_bank RAG)..."):
            for key, indices in by_scene.items():
                result = scene_results[key]
                meta = dict(result.get("metadata") or {})
                # Lock family to the pictured adult only (prevents grandma name on grandpa image)
                slot_role = None
                for s in scene_slots:
                    if s["key"] == key:
                        slot_role = s.get("adult_role")
                        break
                if slot_role:
                    meta["family"] = [slot_role, "child"]
                    meta["adult_role"] = slot_role
                img = result.get("final_image")
                topics_for_call = [topic_plan[i] for i in indices]
                generated = generate_image_grounded_questions(
                    image=img,
                    meta=meta,
                    topics=topics_for_call,
                    num_questions=len(indices),
                    family_names=family_names,
                    child_name=pipeline.get("student_name") or "you",
                    counting_ability=int(pipeline.get("counting_ability") or 20),
                    anything_else=pipeline.get("anything_else") or "",
                    siblings=pipeline.get("siblings_list") or [],
                )
                for offset, qi in enumerate(indices):
                    synced_questions[qi] = (
                        generated[offset] if offset < len(generated) else generated[-1]
                    )

        synced_questions = [q for q in synced_questions if str(q).strip()][:n_q]
        while len(synced_questions) < n_q:
            synced_questions.append(
                synced_questions[-1]
                if synced_questions
                else "How many items can you count?"
            )
        question_scene_keys = question_scene_keys[: len(synced_questions)]

        pipeline["kitchen_result"] = (
            scene_results.get(question_scene_keys[0]) if question_scene_keys else None
        )
        pipeline["role_results"] = scene_results
        pipeline["question_roles"] = question_scene_keys
        pipeline["question_scene_keys"] = question_scene_keys
        pipeline["synced_questions"] = synced_questions
        pipeline["questions"] = list(synced_questions)
        pipeline["question_topic_plan"] = topic_plan[: len(synced_questions)]
        pipeline["num_questions"] = len(synced_questions)
        pipeline["phase"] = "pdf"
        st.rerun()

    elif phase == "pdf":
        include_images = pipeline["include_images"]
        image_paths = None
        temp_img_paths = []
        n_q = int(pipeline.get("num_questions") or 0)
        synced = list(pipeline.get("synced_questions") or pipeline.get("questions") or [])
        if n_q > 0:
            synced = synced[:n_q]
        pipeline["synced_questions"] = synced

        # Per-question illustration: each question uses its assigned scene
        if include_images:
            role_results = pipeline.get("role_results") or {}
            question_roles = (
                pipeline.get("question_scene_keys")
                or pipeline.get("question_roles")
                or []
            )[:len(synced)]
            # Fallback: single kitchen_result for all questions
            if not role_results and pipeline.get("kitchen_result"):
                role_results = {"_single": pipeline["kitchen_result"]}
                question_roles = ["_single"] * len(synced)

            role_temp_paths = {}
            image_paths = []
            for role in question_roles:
                if role not in role_temp_paths:
                    result = role_results.get(role) or {}
                    img = result.get("final_image")
                    if img is None:
                        image_paths.append(None)
                        continue
                    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    img.convert("RGB").save(tmp.name)
                    tmp.close()
                    role_temp_paths[role] = tmp.name
                    temp_img_paths.append(tmp.name)
                image_paths.append(role_temp_paths.get(role))
            pipeline["image_paths"] = list(temp_img_paths)

        print(f"DEBUG: Generating PDF with {len(image_paths or [])} image slots")
        question_topics = list(
            pipeline.get("question_topic_plan") or pipeline.get("rag_topics") or []
        )
        # Align topic labels 1:1 with final questions
        if question_topics:
            while len(question_topics) < len(synced):
                question_topics.append(question_topics[len(question_topics) % len(question_topics)])
            question_topics = question_topics[: len(synced)]
        with st.spinner("📄 Creating PDF workbook..."):
            wb_title, wb_subtitle = build_workbook_title(
                pipeline["student_name"],
                scene_slots=pipeline.get("scene_slots") or [],
                family_names=pipeline.get("family_names") or {},
                favourite_foods=pipeline.get("favourite_foods")
                    or ([pipeline.get("favourite_food")] if pipeline.get("favourite_food") else []),
                favourite_hobbies=pipeline.get("favourite_hobbies")
                    or ([pipeline.get("favourite_hobby")] if pipeline.get("favourite_hobby") else []),
            )
            # Per-question picture facts for MCQ options
            family_names = pipeline.get("family_names") or {}
            role_results = pipeline.get("role_results") or {}
            q_keys = (
                pipeline.get("question_scene_keys")
                or pipeline.get("question_roles")
                or []
            )
            question_counts = []
            question_adults = []
            for key in q_keys[: len(synced)]:
                result = role_results.get(key) or {}
                meta = result.get("metadata") or {}
                objs = meta.get("objects") or [{}]
                c = objs[0].get("count") if objs else meta.get("count")
                try:
                    question_counts.append(int(c) if c is not None else None)
                except (TypeError, ValueError):
                    question_counts.append(None)
                role = (meta.get("adult_role") or "").strip()
                if not role:
                    fam = meta.get("family") or []
                    role = next((x for x in fam if str(x).lower() != "child"), "") or ""
                adult_label = (family_names.get(role) or "").strip()
                if not adult_label or adult_label.lower() == role:
                    adult_label = {
                        "mother": "Mum",
                        "father": "Dad",
                        "grandmother": "Grandma",
                        "grandfather": "Grandad",
                    }.get(role, role.replace("_", " ").title() if role else "Mum")
                question_adults.append(adult_label)
            while len(question_counts) < len(synced):
                question_counts.append(None)
                question_adults.append(None)

            pdf_bytes = generate_pdf(
                pipeline["student_name"],
                pipeline["grade"],
                pipeline["topic_header_text"],
                pipeline["synced_questions"],
                image_paths if include_images else None,
                question_topics=question_topics or None,
                favourite_colour=pipeline.get("fav_color", ""),
                picture_theme=pipeline.get("anything_else", ""),
                workbook_title=wb_title,
                workbook_subtitle=wb_subtitle,
                question_counts=question_counts,
                question_adults=question_adults,
            )

        print(f"DEBUG: PDF generated, size = {len(pdf_bytes)} bytes")
        pipeline["pdf_bytes"] = pdf_bytes
        if temp_img_paths:
            cleanup_temp_images(temp_img_paths)
            pipeline["image_paths"] = []
        pipeline["phase"] = "complete"
        st.rerun()

    elif phase == "complete":
        filename = create_safe_filename(pipeline["student_name"])
        st.success("🎉 Personalised Maths Workbook ready!")

        import base64
        pdf_b64 = base64.b64encode(pipeline["pdf_bytes"]).decode("utf-8")

        col_dl, col_open = st.columns(2)
        with col_dl:
            st.download_button(
                "📥 Download PDF Workbook",
                data=BytesIO(pipeline["pdf_bytes"]),
                file_name=filename,
                mime="application/pdf",
                type="primary",
            )
        with col_open:
            st.markdown(
                f'<a href="data:application/pdf;base64,{pdf_b64}" target="_blank" '
                f'style="display:inline-block;padding:0.5rem 1rem;border-radius:0.5rem;'
                f'background-color:#f0f2f6;color:#31333F;text-decoration:none;'
                f'text-align:center;width:100%;box-sizing:border-box;">📖 Open PDF</a>',
                unsafe_allow_html=True,
            )

        # Eval / gold data generation
        eval_filename = filename.replace(".pdf", "_eval.json") if filename.endswith(".pdf") else f"{filename}_eval.json"
        eval_topics = list(pipeline.get("question_topic_plan") or [])
        eval_data = {
            "student_name": pipeline["student_name"],
            "grade": pipeline["grade"],
            "topics": pipeline.get("topic_header_text", ""),

            "gender": pipeline.get("gender", "Boy"),
            "child_age": pipeline.get("child_age", 6),
            "siblings": pipeline.get("siblings_list", []),
            "fav_color": pipeline.get("fav_color", ""),
            "favourite_foods": pipeline.get("favourite_foods", []),
            "favourite_hobbies": pipeline.get("favourite_hobbies", []),
            "counting_ability": pipeline.get("counting_ability", 20),
            "image_style": pipeline.get("image_style", "soft_cartoon"),
            "questions": [
                {
                    "index": i + 1,
                    "topic": eval_topics[i] if i < len(eval_topics) else None,
                    "text": q,
                }
                for i, q in enumerate(pipeline.get("synced_questions", []))
            ],
            "num_questions": len(pipeline.get("synced_questions", [])),
            "include_images": pipeline.get("include_images", True),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        import json as _json
        eval_json = _json.dumps(eval_data, indent=2)
        st.download_button(
            "📊 Download Eval Data (JSON)",
            data=eval_json,
            file_name=eval_filename,
            mime="application/json",
        )

        if st.button("🔄 Start Over"):
            cleanup_temp_images(pipeline.get("image_paths", []))
            st.session_state.pipeline = None
            st.rerun()
