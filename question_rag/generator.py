"""
Generate image-grounded Grade 1 questions using question_bank RAG examples.
"""

from __future__ import annotations

import base64
import json
import os
import re
from io import BytesIO
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image

from question_rag.retriever import retrieve_examples, resolve_topic, skill_hint_for_legacy_topic

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Prefer a capable text/vision model; fall through if unavailable
PRIMARY_MODEL = os.getenv("QUESTION_RAG_MODEL", "openai/gpt-4o").strip() or "openai/gpt-4o"
FALLBACK_MODELS = [
    m.strip()
    for m in (
        os.getenv("QUESTION_RAG_FALLBACKS")
        or ",".join([
            "openai/gpt-4o-mini",
            "google/gemini-flash-1.5",
            "meta-llama/llama-3.1-8b-instruct",
            "mistralai/mistral-7b-instruct",
            "anthropic/claude-3-haiku",
        ])
    ).split(",")
    if m.strip()
]

_FEMALE_ROLES = frozenset({"mother", "grandmother"})
_MALE_ROLES = frozenset({"father", "grandfather"})
_ALL_ROLES = ("mother", "father", "grandmother", "grandfather")
_ROLE_WORDS = {
    "mother": ["mother", "mum", "mom", "mommy", "mummy"],
    "father": ["father", "dad", "daddy"],
    "grandmother": ["grandmother", "grandma", "granny", "nana", "nan"],
    "grandfather": ["grandfather", "grandpa", "grandad", "granddad"],
}


def _image_to_data_url(image: Image.Image) -> str:
    buf = BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def _pronouns_for_role(adult_role: str) -> dict[str, str]:
    if adult_role in _FEMALE_ROLES:
        return {"subject": "she", "object": "her", "possessive": "her"}
    if adult_role in _MALE_ROLES:
        return {"subject": "he", "object": "him", "possessive": "his"}
    return {"subject": "they", "object": "them", "possessive": "their"}


def _object_labels(obj_type: str, description: str, count: int) -> tuple[str, str]:
    """
    Return the countable singular/plural for worksheet questions.

    Prefer the composed description (e.g. "4 bowls of noodles") over the raw
    object_id, otherwise "noodles" becomes "noodle strands" and Year 1 kids
    are asked to count soup — which is what produced the broken worksheet.
    """
    desc = (description or "").strip().lower()
    if desc:
        parts = desc.split()
        if parts and parts[0].isdigit() and len(parts) > 1:
            noun = " ".join(parts[1:]).strip()
            if noun:
                # "bowls of noodles" → singular "bowl of noodles"
                if noun.startswith("bowls of "):
                    return "bowl of " + noun[len("bowls of "):], noun
                if noun.startswith("slices of "):
                    return "slice of " + noun[len("slices of "):], noun
                if noun.endswith("es") and not noun.endswith("sses"):
                    return noun[:-2] or noun, noun
                if noun.endswith("s") and not noun.endswith("ss"):
                    return noun[:-1] or noun, noun
                return noun, noun if noun.endswith("s") else noun + "s"

    raw = (obj_type or "item").replace("_", " ").strip().lower()
    mapping = {
        "pizza": ("pizza slice", "pizza slices"),
        "cupcakes": ("cupcake", "cupcakes"),
        "cookies": ("cookie", "cookies"),
        "chocolates": ("chocolate", "chocolates"),
        "apples": ("apple", "apples"),
        "smoothies": ("smoothie", "smoothies"),
        "burgers": ("burger", "burgers"),
        # Countable unit = the bowl on the counter, never individual strands.
        "noodles": ("bowl of noodles", "bowls of noodles"),
        "pasta": ("bowl of pasta", "bowls of pasta"),
        "pancakes": ("pancake", "pancakes"),
        "ice cream": ("ice cream", "ice creams"),
        "ice_cream": ("ice cream", "ice creams"),
        "football": ("football", "footballs"),
        "crayons": ("crayon", "crayons"),
        "painting": ("paintbrush", "paintbrushes"),
        "kite": ("kite", "kites"),
        "frisbee": ("frisbee", "frisbees"),
        "bubbles": ("bubble wand", "bubble wands"),
    }
    if raw in mapping:
        return mapping[raw]
    if raw.endswith("s") and raw not in ("pasta",):
        return raw[:-1], raw
    return raw, raw + "s"


def _scene_blurb(meta: dict, family_names: dict | None = None) -> dict:
    family_names = family_names or {}
    obj = (meta.get("objects") or [{}])[0]
    count = int(obj.get("count") or meta.get("count") or 0)
    obj_type = str(obj.get("type") or "item")
    description = str(obj.get("description") or "")
    # Prefer explicit singular/plural from the compositor when present.
    singular = str(meta.get("singular") or obj.get("singular") or "").strip()
    plural = str(meta.get("plural") or obj.get("plural") or "").strip()
    if not singular or not plural:
        singular, plural = _object_labels(obj_type, description, count)

    family = [
        str(x).strip().lower()
        for x in (meta.get("family") or [])
        if str(x).strip().lower() != "child"
    ]
    adult_role = family[0] if family else "mother"
    # Prefer custom name; if missing/placeholder, use a friendly role word
    raw_name = (family_names.get(adult_role) or "").strip()
    placeholders = {
        adult_role, "mother", "father", "grandmother", "grandfather",
        "mum", "dad", "grandma", "grandad",
    }
    if raw_name and raw_name.lower() not in placeholders:
        adult_name = raw_name
    else:
        adult_name = {
            "mother": "Mum",
            "father": "Dad",
            "grandmother": "Grandma",
            "grandfather": "Grandad",
        }.get(adult_role, adult_role.replace("_", " ").title())

    scene_family = str(meta.get("scene_family") or "kitchen").strip().lower()
    place = "the park" if scene_family == "hobby" else "the kitchen"
    surface = "the picnic table" if scene_family == "hobby" else "the counter"
    pronouns = _pronouns_for_role(adult_role)

    # Names that must NEVER appear (other family members)
    forbidden_names = []
    for role in _ALL_ROLES:
        if role == adult_role:
            continue
        nm = (family_names.get(role) or "").strip()
        if nm and nm.lower() not in placeholders and nm.lower() != adult_name.lower():
            forbidden_names.append(nm)
        for w in _ROLE_WORDS.get(role, []):
            forbidden_names.append(w)

    return {
        "count": count,
        "singular": singular,
        "plural": plural,
        "object_desc": description or f"{count} {plural}",
        "adult_role": adult_role,
        "adult_name": adult_name,
        "scene_family": scene_family,
        "place": place,
        "surface": surface,
        "pronouns": pronouns,
        "forbidden_names": forbidden_names,
    }


def _parse_questions_json(content: str, n: int) -> list[str]:
    if not content:
        return []
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            out = []
            for item in data:
                if isinstance(item, str) and item.strip():
                    out.append(item.strip())
                elif isinstance(item, dict):
                    q = (item.get("question") or item.get("text") or "").strip()
                    if q:
                        out.append(q)
            if out:
                return out[:n]
        except Exception:
            pass
    lines = []
    for line in content.splitlines():
        line = line.strip().strip('"').strip("'")
        m = re.match(r"^(?:\d+[\).\]]\s*|[-*]\s+)(.+)$", line)
        if m:
            lines.append(m.group(1).strip())
    return lines[:n]


def _strip_look_at_picture(text: str) -> str:
    text = re.sub(
        r"^(?:look at (?:the )?picture[!.,:]?\s*)+",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"^(?:in (?:the )?picture[!.,:]?\s*|from (?:the )?picture[!.,:]?\s*)+",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )
    return text.strip()


def _fix_basic_grammar(
    text: str,
    adult_name: str | None = None,
    pronouns: dict | None = None,
    singular: str | None = None,
    plural: str | None = None,
) -> str:
    """Year-1 grammar cleanup — agreement, articles, common slips."""
    # you has / you is
    text = re.sub(r"\byou has\b", "you have", text, flags=re.IGNORECASE)
    text = re.sub(r"\byou is\b", "you are", text, flags=re.IGNORECASE)
    text = re.sub(r"\byou was\b", "you were", text, flags=re.IGNORECASE)
    text = re.sub(r"\byou and \w+ is\b", lambda m: m.group(0).rsplit(" ", 1)[0] + " are", text, flags=re.IGNORECASE)
    text = re.sub(r"\byou and \w+ has\b", lambda m: m.group(0).rsplit(" ", 1)[0] + " have", text, flags=re.IGNORECASE)

    # how many X is there → are there
    text = re.sub(r"\b(how many .+?) is there\b", r"\1 are there", text, flags=re.IGNORECASE)
    text = re.sub(r"\bthere is (\d+)\b", r"there are \1", text, flags=re.IGNORECASE)
    text = re.sub(r"\bamount of\b", "number of", text, flags=re.IGNORECASE)

    # After collapsing several names onto one adult: "Nana have" → "Nana has"
    if adult_name:
        esc = re.escape(adult_name)
        text = re.sub(rf"\b({esc})\s+have\b", r"\1 has", text, flags=re.IGNORECASE)
        # Only fix "{Adult} are/were" when Adult is the sole subject (not "you and Adult are")
        text = re.sub(
            rf"(?<!\band )\b({esc})\s+are\b",
            r"\1 is",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"(?<!\band )\b({esc})\s+were\b",
            r"\1 was",
            text,
            flags=re.IGNORECASE,
        )
        # Pronoun gender lock for pictured adult
        if pronouns:
            wrong_subj = "he" if pronouns.get("subject") == "she" else (
                "she" if pronouns.get("subject") == "he" else None
            )
            wrong_poss = "his" if pronouns.get("possessive") == "her" else (
                "her" if pronouns.get("possessive") == "his" else None
            )
            if wrong_subj:
                # "{Adult} ... he/she" in same short sentence — soft fix near name
                text = re.sub(
                    rf"\b({esc})\b([^.?]{{0,40}})\b{wrong_subj}\b",
                    rf"\1\2{pronouns['subject']}",
                    text,
                    flags=re.IGNORECASE,
                )
            if wrong_poss and pronouns.get("possessive"):
                text = re.sub(
                    rf"\b({esc})\b([^.?]{{0,40}})\b{wrong_poss}\b",
                    rf"\1\2{pronouns['possessive']}",
                    text,
                    flags=re.IGNORECASE,
                )

    # Number–noun agreement for scene objects
    if singular and plural and singular.lower() != plural.lower():
        esc_pl = re.escape(plural)
        esc_sg = re.escape(singular)
        text = re.sub(rf"\b1\s+{esc_pl}\b", f"1 {singular}", text, flags=re.IGNORECASE)
        text = re.sub(rf"\bone\s+{esc_pl}\b", f"one {singular}", text, flags=re.IGNORECASE)
        text = re.sub(
            rf"\b([2-9]|[1-9]\d+)\s+{esc_sg}\b",
            lambda m: f"{m.group(1)} {plural}",
            text,
            flags=re.IGNORECASE,
        )
        # a/an + plural → a/an + singular
        art = "an" if singular[:1].lower() in "aeiou" else "a"
        text = re.sub(rf"\b(a|an)\s+{esc_pl}\b", f"{art} {singular}", text, flags=re.IGNORECASE)
        text = re.sub(rf"\b(a|an)\s+{esc_sg}\b", f"{art} {singular}", text, flags=re.IGNORECASE)

    # Tidy punctuation / spacing
    text = re.sub(r"\bthe the\b", "the", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([?!.])", r"\1", text)
    text = re.sub(r"([.!?]){2,}", r"\1", text)
    # Capitalise sentence starts (including after ". ")
    parts = re.split(r"([.!?]\s+)", text)
    rebuilt = []
    for i, part in enumerate(parts):
        if i % 2 == 0 and part:
            part = part[0].upper() + part[1:]
        rebuilt.append(part)
    text = "".join(rebuilt).strip()
    if text and text[-1] not in ".?!":
        text += "?"
    return text


def _enforce_role_consistency(text: str, scene: dict, family_names: dict | None = None) -> str:
    """
    Ensure only the pictured adult appears.
    Wrong names / roles are rewritten to the pictured adult.
    """
    family_names = family_names or {}
    adult_role = scene["adult_role"]
    adult_name = scene["adult_name"]
    pronouns = scene["pronouns"]

    # Replace other custom names first (longest first)
    others = []
    for role in _ALL_ROLES:
        if role == adult_role:
            continue
        nm = (family_names.get(role) or "").strip()
        if nm and nm.lower() != adult_name.lower():
            others.append(nm)
    for nm in sorted(set(others), key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(nm)}\b", adult_name, text, flags=re.IGNORECASE)

    # Replace other role words with adult_name
    for role in _ALL_ROLES:
        if role == adult_role:
            continue
        for word in sorted(_ROLE_WORDS.get(role, []), key=len, reverse=True):
            text = re.sub(rf"\b{re.escape(word)}\b", adult_name, text, flags=re.IGNORECASE)

    # Normalise pictured adult's generic words → their display name
    for word in sorted(_ROLE_WORDS.get(adult_role, []), key=len, reverse=True):
        if word.lower() == adult_name.lower():
            continue
        text = re.sub(rf"\b{re.escape(word)}\b", adult_name, text, flags=re.IGNORECASE)

    # Collapse "Name and Name"
    esc = re.escape(adult_name)
    text = re.sub(rf"\b{esc}\s+and\s+{esc}\b", adult_name, text, flags=re.IGNORECASE)

    # Pronouns near the adult (best-effort): "Grandma ... he" is rare; fix common mismatches
    # after adult name + verb patterns are hard — keep light
    if pronouns["subject"] == "she":
        # "Grandad ... she" already renamed; fix "Dad brings ... his" left as his is ok for dad
        pass

    return text


def _is_picture_answerable(question: str, scene: dict) -> bool:
    """
    Reject questions a Year 1 child cannot answer from the photo.

    Bank RAG often copies multi-set / classroom patterns ("tick the set that
    has more…") when the scene only shows one group of objects on the counter.
    """
    text = (question or "").strip().lower()
    if not text:
        return False

    # Off-picture / empty-set / multi-set classroom wording
    banned = (
        r"\bnot in the\b",
        r"\bnot on the\b",
        r"\bare missing\b",
        r"\bhow many .+ are not\b",
        r"\bempty set\b",
        r"\boff.?camera\b",
        r"\bcannot see\b",
        r"\boutside the (picture|photo|image)\b",
        # Single-group scenes have no second "set" to tick.
        r"\btick\b",
        r"\bwhich set\b",
        r"\bthe set that\b",
        r"\bsets?\s+that\s+has\s+more\b",
        r"\bset\s+a\b",
        r"\bset\s+b\b",
        r"\bgroup\s+a\b",
        r"\bgroup\s+b\b",
        r"\btally chart\b",
        r"\bbar chart\b",
        r"\bpictogram\b",
        r"\bcarroll diagram\b",
        r"\bvenn\b",
        # Classroom / bank props not in our scenes
        r"\bten frames?\b",
        r"\bnumber lines?\b",
        r"\bpartner\b",
        r"\bscissors\b",
        r"\bdomino",
        r"\bwhiteboard\b",
        r"\bworksheet\b",
        r"\bclass(room)?\b",
        r"\bteacher\b",
        r"\bpencil case\b",
        r"\blook at the picture\b",
    )
    if any(re.search(pat, text) for pat in banned):
        return False

    # Sibling / pet story beats are allowed as narrative only (not drawn in the photo).
    # Keep them answerable from the visible count.
    plural = (scene.get("plural") or "").lower()
    singular = (scene.get("singular") or "").lower()
    adult = (scene.get("adult_name") or "").lower()
    place = (scene.get("place") or "").lower()
    surface = (scene.get("surface") or "").lower()
    count = int(scene.get("count") or 0)

    # Must be grounded in this picture's people / place / objects.
    has_object = bool(
        (plural and plural in text) or (singular and singular in text)
    )
    has_people_place = bool(
        (adult and adult in text)
        or (place and place in text)
        or (surface and surface in text)
    )
    if not has_object and not has_people_place:
        return False

    # Reject inventing a hard wrong total ("there are 9 cookies" when count is 4).
    # Allow small story numbers used with "more" / "gives" / "brings".
    if count > 0:
        for m in re.finditer(
            r"\bthere (?:are|is) (\d+)\b|\b(\d+) (?:altogether|in total)\b",
            text,
        ):
            claimed = int(m.group(1) or m.group(2))
            if claimed != count:
                return False

    # If countable unit is a bowl/container, forbid counting the contents alone.
    if "bowl of" in singular or "bowls of" in plural:
        if re.search(r"\bhow many (noodles|pasta|strands)\b", text):
            if "bowl" not in text:
                return False
    return True


def _has_clean_grammar(question: str, scene: dict) -> bool:
    """Reject questions that still look grammatically broken after polish."""
    text = (question or "").strip()
    if len(text) < 8:
        return False
    low = text.lower()
    bad_patterns = (
        r"\byou has\b",
        r"\byou is\b",
        r"\bhow many .+ is there\b",
        r"\b  +\b",
        r"\bthe the\b",
        r"\?\?",
    )
    if any(re.search(p, low) for p in bad_patterns):
        return False
    adult = scene.get("adult_name") or ""
    pro = scene.get("pronouns") or {}
    if adult and pro.get("subject") == "she" and re.search(
        rf"\b{re.escape(adult)}\b.{{0,30}}\bhe\b", text, flags=re.IGNORECASE
    ):
        return False
    if adult and pro.get("subject") == "he" and re.search(
        rf"\b{re.escape(adult)}\b.{{0,30}}\bshe\b", text, flags=re.IGNORECASE
    ):
        return False
    return True


def _statistics_fallback(scene: dict) -> str:
    """Picture-true compare questions when the topic is statistics."""
    c = int(scene.get("count") or 0)
    pl = scene["plural"]
    adult = scene["adult_name"]
    surface = scene["surface"]
    if c >= 3:
        return (
            f"You can see {c} {pl} on {surface}. "
            f"Are there more than 2 {pl}? How many {pl} are there?"
        )
    return (
        f"There are {c} {pl}. {adult} brings 3 more later. "
        f"Who has more at the start — you now, or {adult} later with 3?"
    )


def _first_pet_name(pet_name: str) -> str:
    raw = (pet_name or "").strip()
    if not raw:
        return ""
    # "Buster, Coco" → Buster
    return re.split(r"[,/&]| and ", raw, maxsplit=1)[0].strip().title()


def _sibling_phrases(siblings: list | None) -> list[dict]:
    """Normalise sibling entries into story-ready phrases."""
    out = []
    for sib in siblings or []:
        if not isinstance(sib, dict):
            continue
        name = (sib.get("name") or "").strip()
        if not name:
            continue
        gender = (sib.get("gender") or "Boy").strip().title()
        relation = "brother" if gender == "Boy" else "sister"
        out.append({
            "name": name.title(),
            "relation": relation,
            "phrase": f"your {relation} {name.title()}",
        })
    return out


def _apply_personal_touches(
    questions: list[str],
    scene: dict,
    *,
    child_name: str = "you",
    pet_name: str = "",
    siblings: list | None = None,
    family_names: dict | None = None,
) -> list[str]:
    """
    Guarantee personalisation beats even if the model omitted them:
      - one sibling 'joins later' story question
      - one pet cheerleader line (not part of the maths answer)
    """
    if not questions:
        return questions

    pet = _first_pet_name(pet_name)
    sibs = _sibling_phrases(siblings)
    c = int(scene.get("count") or 0)
    pl = scene.get("plural") or "items"

    out = list(questions)

    # 1) Sibling story beat — replace weakest add-style slot, or last question
    if sibs and c > 0:
        sib = sibs[0]
        story = (
            f"There are {c} {pl}. "
            f"If {sib['phrase']} joins later with 2 more, "
            f"how many {pl} will there be altogether?"
        )
        story = _polish_question(story, scene, family_names)
        already = any(
            re.search(rf"\b{re.escape(sib['name'])}\b", q, flags=re.IGNORECASE)
            or re.search(r"\b(brother|sister)\b", q, flags=re.IGNORECASE)
            for q in out
        )
        if not already:
            # Prefer swapping an addition-ish question; else last
            swap_at = len(out) - 1
            for i, q in enumerate(out):
                if re.search(r"\b(more|altogether|gives|brings)\b", q, flags=re.IGNORECASE):
                    swap_at = i
                    break
            out[swap_at] = story

    # 2) Pet cheerleader — append to a counting question (not the maths answer)
    if pet:
        already_pet = any(re.search(rf"\b{re.escape(pet)}\b", q, flags=re.IGNORECASE) for q in out)
        if not already_pet:
            target = 0
            for i, q in enumerate(out):
                if re.search(r"\bhow many\b|\bcount\b", q, flags=re.IGNORECASE):
                    target = i
                    break
            q = out[target].rstrip()
            q = re.sub(r"[.?!]+$", "", q).strip()
            cheer = f" Tell {pet} how many {pl} you counted!"
            # Avoid duplicating if already ends with Tell …
            if " tell " not in q.lower():
                # Keep the maths ask as a question, then the cheer as a separate sentence.
                out[target] = _polish_question(q + "?" + cheer, scene, family_names)

    # Final polish pass
    cleaned = []
    seen = set()
    for q in out:
        q = _polish_question(q, scene, family_names)
        # Sibling/pet lines are intentional story — don't drop for "not in picture"
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(q)
    return cleaned or out


def _polish_question(text: str, scene: dict, family_names: dict | None = None) -> str:
    text = _strip_look_at_picture(text or "")
    text = _enforce_role_consistency(text, scene, family_names)
    text = _fix_basic_grammar(
        text,
        adult_name=scene.get("adult_name"),
        pronouns=scene.get("pronouns"),
        singular=scene.get("singular"),
        plural=scene.get("plural"),
    )
    return text


def _accept_question(q: str, scene: dict, family_names: dict | None = None) -> str | None:
    """Polish + validate; return cleaned question or None if unusable."""
    q = _polish_question(q, scene, family_names)
    if not q:
        return None
    if not _is_picture_answerable(q, scene):
        return None
    if not _has_clean_grammar(q, scene):
        return None
    return q


def _fallback_questions(
    scene: dict,
    topics: list[str],
    n: int,
    *,
    child_name: str = "you",
) -> list[str]:
    """Deterministic image-true backups if the API fails — no 'Look at the picture'."""
    c, pl, sg = scene["count"], scene["plural"], scene["singular"]
    adult = scene["adult_name"]
    place, surface = scene["place"], scene["surface"]
    pro = scene["pronouns"]
    child = (child_name or "you").strip() or "you"
    # Use first name in a friendly way when it isn't the placeholder "you"
    hello = f"{child}, " if child.lower() not in {"you", ""} else ""

    pool = [
        f"{hello}how many {pl} can you count on {surface}?",
        f"You and {adult} are in {place}. How many {pl} are there altogether?",
        f"There are {c} {pl}. If {adult} brings 1 more, how many {pl} will there be?",
        f"If you give 1 {sg} to {adult}, how many {pl} are left?",
        f"Who is with you in {place}?",
        f"Are there more than 2 {pl} on {surface}?",
        f"Write the number of {pl} you can see.",
        (
            f"{adult} puts the {pl} into 2 equal groups. How many are in each group?"
            if c and c % 2 == 0
            else f"Point to each {sg}. How many did you point to?"
        ),
        f"{adult} is smiling. How many {pl} can you see near {pro['object']}?",
    ]
    out = []
    for i in range(n):
        topic = (topics[i % len(topics)] if topics else "").lower()
        if "fraction" in topic or "half" in topic:
            out.append(f"If you and {adult} share the {pl} into 2 equal groups, is that halves?")
        elif "measure" in topic:
            out.append(f"Who looks taller in the picture, you or {adult}?")
        elif "position" in topic:
            out.append(f"Are the {pl} in front of you and {adult}?")
        elif "geometry" in topic or "shape" in topic:
            out.append(f"What shapes can you see near the {pl}?")
        elif "working with numbers" in topic or "add" in topic:
            out.append(
                f"There are {c} {pl}. {adult} gives you 2 more. "
                f"How many {pl} are there altogether?"
            )
        elif "statistic" in topic or "data" in topic or "compare" in topic:
            out.append(_statistics_fallback(scene))
        else:
            out.append(pool[i % len(pool)])

    final, seen = [], set()
    for q in out:
        q = _accept_question(q, scene) or _polish_question(q, scene)
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        final.append(q)
    # If still short, add numbered counting variants
    i = 0
    while len(final) < n:
        i += 1
        q = _polish_question(
            f"Count the {pl} with {adult}. How many {pl} are there?",
            scene,
        )
        if q.lower() in seen:
            q = f"How many {pl} can you and {adult} see together?"
            if q.lower() in seen:
                q = f"Write how many {pl} are on {surface}."
        if q.lower() in seen:
            break
        seen.add(q.lower())
        final.append(q)
    return final[:n]


def _call_openrouter(
    *,
    model: str,
    content,
    timeout: int = 90,
) -> tuple[int, str]:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8502",
    }
    payload = {
        "model": model,
        "max_tokens": 1400,
        "temperature": 0.25,
        "messages": [{"role": "user", "content": content}],
    }
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
    if resp.status_code != 200:
        return resp.status_code, resp.text[:300]
    raw = resp.json()["choices"][0]["message"]["content"]
    return 200, raw


def generate_image_grounded_questions(
    *,
    image: Image.Image | None,
    meta: dict,
    topics: list[str],
    num_questions: int,
    family_names: dict | None = None,
    child_name: str = "you",
    counting_ability: int = 20,
    examples_per_topic: int = 6,
    hobbies: str = "",
    pet_name: str = "",
    anything_else: str = "",
    siblings: list | None = None,
) -> list[str]:
    """
    RAG-generate worksheet questions for one scene image via OpenRouter API.
    Questions are topic-styled, image-true, role-consistent, and do not start
    with "Look at the picture".
    """
    n = max(1, int(num_questions))
    family_names = family_names or {}
    topic_list = [t for t in (topics or []) if str(t).strip()] or ["Numbers To 10"]
    assigned_topics = [topic_list[i % len(topic_list)] for i in range(n)]

    scene = _scene_blurb(meta, family_names)
    child = (child_name or "you").strip() or "you"
    pro = scene["pronouns"]
    forbidden = ", ".join(sorted(set(scene["forbidden_names"]))) or "(none)"
    hobby_note = (hobbies or "").strip()
    pet = _first_pet_name(pet_name)
    extra = (anything_else or "").strip()
    sibs = _sibling_phrases(siblings)
    pl = scene["plural"]
    sg = scene["singular"]

    personal_lines = [
        f"- Child's name: {child} (you may start 1 question with \"{child}, …\" — still address as you)",
    ]
    if hobby_note:
        personal_lines.append(
            f"- Interests: {hobby_note} (optional friendly tone only — stay picture-true)"
        )
    if pet:
        personal_lines.append(
            f"- Pet cheerleader: {pet}. On ONE counting question, end with a cheer like "
            f"\"Tell {pet} how many {pl} you counted!\" — the pet is NOT in the picture "
            f"and is NOT part of the maths answer."
        )
    if sibs:
        sib = sibs[0]
        personal_lines.append(
            f"- Sibling story (ONE question only): use a story beat like "
            f"\"If {sib['phrase']} joins later with 2 more, how many {pl} "
            f"will there be altogether?\" Start from the visible count {scene['count']}. "
            f"Do NOT say the sibling is in the picture."
        )
    if extra:
        personal_lines.append(f"- Extra note: {extra[:120]} (tone only; do not invent props)")

    rag_blocks = []
    for topic in dict.fromkeys(assigned_topics):
        hint = skill_hint_for_legacy_topic(topic)
        examples = retrieve_examples(
            topic,
            k=examples_per_topic,
            query=f"{scene['plural']} {scene['adult_name']} count add",
            skill_hint=hint,
        )
        resolved = resolve_topic(topic) or topic
        if examples:
            bullet = "\n".join(f"- {ex}" for ex in examples)
            rag_blocks.append(
                f"TOPIC: {resolved}\nExample skill/style from the bank (adapt — do not copy props):\n{bullet}"
            )
        else:
            rag_blocks.append(f"TOPIC: {resolved}\n(Use clear Year 1 style for this topic.)")

    topic_plan = "\n".join(f"  Q{i+1}: topic = {assigned_topics[i]}" for i in range(n))

    prompt = f"""You are an expert UK Year 1 (age 5–6) maths teacher writing high-quality worksheet questions.

PICTURE FACTS — every question MUST be answerable from THIS picture only:
- Setting: {scene['place']} ({scene['surface']} in the foreground)
- Child: address as "you" (name: {child})
- Adult in the picture: ONLY {scene['adult_name']} (role: {scene['adult_role']})
- Pronouns for {scene['adult_name']}: {pro['subject']} / {pro['object']} / {pro['possessive']}
- Visible countable objects: EXACTLY {scene['count']} {scene['plural']}
- Singular / plural: {scene['singular']} / {scene['plural']}
- Number range for the child: up to {counting_ability}

PERSONAL TOUCH (keep picture-true):
{chr(10).join(personal_lines)}

FORBIDDEN people / names (MUST NOT appear in any question): {forbidden}
There is NO other adult in the picture. Do not mention Mum/Dad/Grandma/Grandad unless that is exactly {scene['adult_name']}.

REFERENCE EXAMPLES (RAG from question_bank — copy the maths skill, not classroom props):
{chr(10).join(rag_blocks)}

TASK:
Write EXACTLY {n} NEW worksheet questions for this picture.
Topic plan (follow this order):
{topic_plan}

GRAMMAR (must be perfect Year 1 English):
- Short clear sentences. Capital letter at the start. End with ? or .
- "you have" / "you are" — never "you has" / "you is"
- "{scene['adult_name']} has / is / was" — never "have / are / were" for one adult
- Use {pro['subject']}/{pro['object']}/{pro['possessive']} for {scene['adult_name']} — never the wrong gender
- "How many {scene['plural']} are there?" — never "is there"
- "1 {scene['singular']}" / "{scene['count']} {scene['plural']}" — correct singular/plural
- No double words ("the the"), no broken fragments

PICTURE RULES:
1. Do NOT start with "Look at the picture". Ask naturally.
2. Every question is about THIS picture: you, {scene['adult_name']}, {scene['place']}, and the {scene['count']} {scene['plural']}.
3. ROLE LOCK: only adult name allowed is "{scene['adult_name']}".
4. Do not invent objects, charts, sets, or classroom equipment.
5. Counting answers must match the visible count {scene['count']}. Never write "there are N …" unless N is {scene['count']}.
6. For addition/subtraction you may add a tiny action ("brings 1 more") but start from {scene['count']}.
7. Each question unique and matched to its assigned topic skill.
8. COUNT THE CONTAINERS, NOT THE CONTENTS: if the plural is "bowls of noodles" / "bowls of pasta",
   ask about bowls (answer = {scene['count']}), NEVER about individual strands.
9. Do NOT ask about things that are NOT in the picture — except ONE optional sibling "joins later" story and ONE pet cheer line.
10. Statistics / compare: one group of {scene['count']} {scene['plural']} only — no Set A/B, no "tick the set".
11. Prefer natural wording a 5–6 year old understands; personalise with {child}'s name where it still sounds natural.

GOOD examples of style (adapt to THIS picture):
- "How many {scene['plural']} can you count on {scene['surface']}?"
- "{child}, you and {scene['adult_name']} are in {scene['place']}. How many {scene['plural']} are there altogether?"
- "There are {scene['count']} {scene['plural']}. If {scene['adult_name']} brings 1 more, how many will there be?"

Return ONLY a JSON array of {n} strings. No markdown, no answers.
"""

    def _finalise(qs: list[str]) -> list[str]:
        return _apply_personal_touches(
            qs[:n],
            scene,
            child_name=child,
            pet_name=pet_name,
            siblings=siblings,
            family_names=family_names,
        )[:n]

    if not API_KEY:
        print("  ⚠️  No OPENROUTER_API_KEY — using fallback image questions")
        return _finalise(_fallback_questions(scene, assigned_topics, n, child_name=child))

    # Build message content (vision when image available)
    if image is not None:
        user_content = [
            {"type": "image_url", "image_url": {"url": _image_to_data_url(image)}},
            {"type": "text", "text": prompt},
        ]
    else:
        user_content = prompt

    models_to_try = [PRIMARY_MODEL] + [m for m in FALLBACK_MODELS if m != PRIMARY_MODEL]
    questions: list[str] = []

    for model in models_to_try:
        print(f"  📚 RAG question gen via API: model={model}, n={n}, adult={scene['adult_name']} ({scene['adult_role']})")
        try:
            status, body = _call_openrouter(model=model, content=user_content)
            if status != 200:
                print(f"  ⚠️  {model} failed ({status}): {body[:160]}")
                # If vision payload failed, retry same model text-only once
                if image is not None and isinstance(user_content, list):
                    print(f"  ↳ retrying {model} text-only…")
                    status, body = _call_openrouter(model=model, content=prompt)
                    if status != 200:
                        print(f"  ⚠️  text-only also failed ({status})")
                        continue
                else:
                    continue

            parsed = _parse_questions_json(body, n)
            clean: list[str] = []
            seen: set[str] = set()
            for q in parsed:
                accepted = _accept_question(q, scene, family_names)
                if not accepted:
                    # One more polish pass then re-check (role rewrite may fix it)
                    q2 = _polish_question(q, scene, family_names)
                    # Allow sibling/pet story lines through even if strict filter hesitates
                    has_story = bool(
                        re.search(r"\b(brother|sister|joins later)\b", q2, flags=re.IGNORECASE)
                        or (pet and re.search(rf"\b{re.escape(pet)}\b", q2, flags=re.IGNORECASE))
                    )
                    if has_story or (
                        _is_picture_answerable(q2, scene) and _has_clean_grammar(q2, scene)
                    ):
                        accepted = q2
                    else:
                        print(f"  ↩︎  Dropped bad question: {(q or '')[:80]}")
                        continue
                # Reject leftover forbidden other-adult names
                bad = False
                for nm in scene["forbidden_names"]:
                    if len(nm) >= 3 and re.search(rf"\b{re.escape(nm)}\b", accepted, flags=re.IGNORECASE):
                        accepted2 = _accept_question(accepted, scene, family_names)
                        if not accepted2 or re.search(rf"\b{re.escape(nm)}\b", accepted2, flags=re.IGNORECASE):
                            bad = True
                            break
                        accepted = accepted2
                if bad:
                    continue
                key = accepted.lower()
                if key in seen:
                    continue
                seen.add(key)
                clean.append(accepted)

            if len(clean) >= n:
                return _finalise(clean[:n])
            if clean:
                questions = clean
                break
        except Exception as e:
            print(f"  ❌ {model} error: {e}")
            continue

    if questions:
        pad = _fallback_questions(scene, assigned_topics, n, child_name=child)
        for q in pad:
            if len(questions) >= n:
                break
            accepted = _accept_question(q, scene, family_names) or _polish_question(q, scene, family_names)
            if accepted.lower() not in {x.lower() for x in questions}:
                if _is_picture_answerable(accepted, scene):
                    questions.append(accepted)
        return _finalise(questions[:n])

    return _finalise(_fallback_questions(scene, assigned_topics, n, child_name=child))
