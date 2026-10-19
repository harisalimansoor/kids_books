"""
Look at one question and build the question page's words.

Options: exactly 3 — 1 correct answer and 2 wrong ones.
Heading: a short title and a sticker taken from THIS question.
A mango question becomes "Mangoes With Gran". Nothing is reused on every page.

The correct answer already stored on the question (meta.json) is kept.
Wrong options are nearby numbers, the way the workbook page shows 6, 8, 10.
"""

from __future__ import annotations

import os
import random
import re
from typing import Any

STICKERS = (
    "building",
    "baking",
    "shopping",
    "time",
    "shapes",
    "toys",
    "playing",
    "animals",
    "sport",
    "garden",
    "counting",
    "maths",
    "food",
    "book",
    "balloon",
    "car",
)

_ADULTS: tuple[tuple[str, str], ...] = (
    (r"grandfathers?", "Grandad"),
    (r"grandmas?|grandmothers?|grann(?:y|ies)|grans?", "Gran"),
    (r"grandads?|grandpas?", "Grandad"),
    (r"mothers?|mums?|moms?", "Mum"),
    (r"fathers?|dads?", "Dad"),
    (r"brothers?", "Brother"),
    (r"sisters?", "Sister"),
    (r"uncles?", "Uncle"),
    (r"aunts?", "Aunt"),
)


def _clean_option(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^[A-Da-d1-4][\.\)\:\-]\s*", "", text).strip()
    return text


def _answer_from_meta(meta: dict | None) -> str:
    answer = (meta or {}).get("answer") or {}
    correct = _clean_option(answer.get("correct"))
    if correct and correct != "-":
        return correct
    formula = str(answer.get("formula") or "").strip()
    match = re.fullmatch(r"(\d+)\s*([+\-])\s*(\d+)", formula)
    if not match:
        return ""
    left, op, right = int(match.group(1)), match.group(2), int(match.group(3))
    value = left + right if op == "+" else left - right
    return str(max(value, 0))


def _solve_question(question: str) -> str:
    """Read the question text and return the correct value when the sum is simple."""
    low = (question or "").lower()
    nums = [int(n) for n in re.findall(r"\b\d+\b", question or "")]
    if re.search(r"\b(is|are|do|does|can|will)\b.+\?", low) and re.search(
        r"\b(more than|less than|equal|same)\b", low
    ):
        return "Yes"
    if len(nums) >= 2:
        a, b = nums[0], nums[1]
        if re.search(r"\b(remain|left|uses|used|eats|eaten|sold|lost|crossed)\b", low) or "take away" in low:
            return str(abs(a - b))
        if re.search(r"\b(altogether|total|more|adds|plus|sum)\b", low):
            return str(a + b)
        return str(abs(a - b))
    if len(nums) == 1:
        return str(nums[0])
    if re.search(r"\b(yes|no)\b", low):
        return "Yes"
    return "1"


def _split_number(correct: str) -> tuple[int, str] | None:
    match = re.fullmatch(r"(\d+)\s*(.*)", (correct or "").strip())
    if not match:
        return None
    suffix = match.group(2)
    if suffix and re.search(r"[a-zA-Z]", suffix) is None and suffix not in ("",):
        return None
    return int(match.group(1)), suffix


def _distractors(correct: str, supplied: list[str]) -> list[str]:
    """Two wrong options. Numbers use the neighbours two steps away (8 → 6 and 10)."""
    parsed = _split_number(correct)
    wrong: list[str] = []
    if parsed is not None:
        value, suffix = parsed
        gap = f" {suffix}" if suffix and not suffix.startswith(" ") else suffix
        for step in (2, 1, 3, 4):
            for candidate in (value - step, value + step):
                if candidate < 0 or candidate == value:
                    continue
                label = f"{candidate}{gap}".strip()
                if label != correct and label not in wrong:
                    wrong.append(label)
                if len(wrong) == 2:
                    return wrong
    if correct.lower() in ("yes", "no"):
        for label in ("Yes", "No", "Maybe"):
            if label.lower() != correct.lower() and label not in wrong:
                wrong.append(label)
            if len(wrong) == 2:
                return wrong
    for item in supplied:
        if item and item != correct and item not in wrong:
            wrong.append(item)
        if len(wrong) == 2:
            return wrong
    while len(wrong) < 2:
        label = str(len(wrong) + 2)
        if label != correct and label not in wrong:
            wrong.append(label)
        else:
            wrong.append(f"{len(wrong) + 3}")
    return wrong[:2]


def _order_options(options: list[str]) -> list[str]:
    parsed = [_split_number(item) for item in options]
    if parsed and all(item is not None and item[1] == "" for item in parsed):
        return sorted(options, key=lambda item: int(item))
    mixed = list(options)
    random.shuffle(mixed)
    return mixed


def normalize_trio(correct: str, options: list[Any] | None) -> dict[str, Any]:
    """Force 1 correct answer and 2 wrong ones."""
    correct = _clean_option(correct)
    clean: list[str] = []
    for item in options or []:
        text = _clean_option(item)
        if text and text != "-" and text not in clean:
            clean.append(text)
    if not correct:
        correct = clean[0] if clean else "1"
    if len(clean) == 3 and correct in clean:
        return {"options": _order_options(clean)[:3], "correct_answer": correct}
    trio = _order_options([correct, *_distractors(correct, clean)])
    return {"options": trio[:3], "correct_answer": correct}


# Longer phrases first so "toy cars" is not read as "cars", and "books" wins
# over the word "circle" that often appears in the same sentence.
_TOPICS: tuple[tuple[str, str, str], ...] = (
    (r"toy cars?", "Toy Cars", "car"),
    (r"counting blocks|wooden blocks|blocks?", "Blocks", "building"),
    (r"bricks?|castles?|forts?|lego|towers?", "Blocks", "building"),
    (r"marbles?", "Marbles", "toys"),
    (r"mangoes|mangos?", "Mangoes", "food"),
    (r"apples?", "Apples", "food"),
    (r"bananas?", "Bananas", "food"),
    (r"cupcakes?|cakes?|cookies|biscuits?", "Baking", "baking"),
    (r"books?", "Books", "book"),
    (r"balloons?", "Balloons", "balloon"),
    (r"coins?|pennies|pence", "Coins", "shopping"),
    (r"footballs?", "Football", "sport"),
    (r"balls?", "Balls", "sport"),
    (r"flowers?", "Flowers", "garden"),
    (r"buttons?", "Buttons", "counting"),
    (r"birds?", "Birds", "animals"),
    (r"pencils?", "Pencils", "counting"),
    (r"stickers?", "Stickers", "toys"),
    (r"o'clock|clocks?|minutes?|hours?", "Telling Time", "time"),
    (r"triangles?|squares?|rectangles?|cubes?|shapes?", "Shapes", "shapes"),
)


def _adult_label(question: str, adult: str = "") -> str:
    """The adult on this page only. Never assumes Grandad."""
    low = (question or "").lower()
    for pattern, label in _ADULTS:
        if re.search(rf"\b(?:{pattern})\b", low):
            return label
    name = (adult or "").strip()
    if not name or name.lower() in {"a friend", "friend", "adult"}:
        return ""
    lowered = name.lower()
    for pattern, label in _ADULTS:
        if re.search(rf"\b(?:{pattern})\b", lowered):
            return label
    return name[:18]


def local_heading(question: str, adult: str = "") -> dict[str, str]:
    """Short title and sticker from this question. No network."""
    low = (question or "").lower()
    sticker = "maths"
    verb = "Maths"
    for pattern, label, sticker_id in _TOPICS:
        if re.search(rf"\b(?:{pattern})\b", low):
            sticker = sticker_id
            verb = label
            break
    who = _adult_label(question, adult)
    title = f"{verb} With {who}" if who else verb
    title = re.sub(r"\s+", " ", title).strip()
    return {"title": title[:42], "sticker": sticker if sticker in STICKERS else "maths"}


def _copied_template(title: str, sticker: str, question: str, adult: str = "") -> bool:
    """Reject a fixed sample title that does not belong to this question."""
    del adult
    low_q = (question or "").lower()
    low_t = (title or "").lower()
    if "building with grandad" in low_t:
        return True
    about_building = bool(re.search(r"\b(?:blocks?|bricks?|build(?:ing)?|lego|towers?)\b", low_q))
    if sticker == "building" and not about_building:
        return True
    return False


def page_heading(
    question: str,
    *,
    adult: str = "",
    allow_network: bool = True,
    api_key: str | None = None,
) -> dict[str, str]:
    """
    Short page title for this question only.
    Uses the model when a key is available, otherwise the local reading.
    """
    fallback = local_heading(question, adult)
    if not allow_network or os.environ.get("PYTEST_CURRENT_TEST"):
        return fallback
    key = (api_key or os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return fallback
    try:
        import requests

        who = _adult_label(question, adult)
        prompt = (
            "Write a short children's workbook page title for THIS maths question only.\n"
            f"QUESTION:\n{question}\n"
            f"ADULT ON THIS PAGE: {who or 'none'}\n\n"
            "Reply with JSON only, using placeholders you replace from this question:\n"
            '{"title": "<2 to 5 words naming the objects in THIS question>", '
            '"sticker": "<sticker id>"}\n'
            "Rules:\n"
            "- The title must name what this question is about (mangoes, coins, books, balloons, blocks).\n"
            "- Do not reuse one fixed title for every question.\n"
            "- Do not use the title Building With Grandad.\n"
            "- No question mark. Do not reveal the numeric answer.\n"
            f"- sticker is exactly one of: {', '.join(STICKERS)}."
        )
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 80,
            },
            timeout=8,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start < 0 or end <= start:
            return fallback
        import json

        data = json.loads(text[start:end])
        title = re.sub(r"\s+", " ", str(data.get("title") or "")).strip(" \"'")
        sticker = str(data.get("sticker") or "").strip().lower()
        if len(title) < 3 or _copied_template(title, sticker, question, adult):
            return fallback
        return {
            "title": title[:42],
            "sticker": sticker if sticker in STICKERS else fallback["sticker"],
        }
    except Exception:
        return fallback


def _ai_trio(question: str, correct: str, *, api_key: str | None, model: str) -> dict[str, Any] | None:
    key = (api_key or os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return None
    try:
        import json
        import requests

        locked = (
            f"The CORRECT answer is exactly {correct}. Do not change it.\n"
            if correct
            else "Work out the single correct answer from the question.\n"
        )
        prompt = (
            "You are writing a children's maths workbook.\n"
            f"{locked}"
            f"QUESTION:\n{question}\n\n"
            "Reply with JSON only:\n"
            '{"correct": "<answer>", "options": ["<wrong>", "<answer>", "<wrong>"], '
            '"title": "<objects in THIS question>", "sticker": "<sticker id>"}\n'
            "Rules:\n"
            "- options has exactly 3 values: the correct answer and 2 wrong ones.\n"
            "- Wrong numbers should be close to the correct answer.\n"
            "- No A/B/C labels.\n"
            "- title names the objects in THIS question only. Do not reuse one title for every question.\n"
            "- Use a building title only when the question is about blocks or building.\n"
            f"- sticker is one of: {', '.join(STICKERS)}."
        )
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model or "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 160,
            },
            timeout=12,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        data = json.loads(text[start:end])
        found = _clean_option(data.get("correct")) or correct
        if correct:
            found = correct
        packed = normalize_trio(found, data.get("options") or [])
        title = re.sub(r"\s+", " ", str(data.get("title") or "")).strip()
        sticker = str(data.get("sticker") or "").strip().lower()
        if title and not _copied_template(title, sticker, question):
            packed["title"] = title[:42]
        if sticker in STICKERS and not _copied_template(title, sticker, question):
            packed["sticker"] = sticker
        return packed
    except Exception as exc:
        print(f"  [MCQ] {exc}")
        return None


def build_mcq(
    question: str,
    *,
    meta: dict | None = None,
    correct: str | None = None,
    allow_network: bool = False,
    api_key: str | None = None,
    model: str = "openai/gpt-4o-mini",
) -> dict[str, Any]:
    """
    Return {"options": [3 items], "correct_answer", "title", "sticker"}.
    """
    known = _clean_option(correct) or _answer_from_meta(meta)
    supplied = []
    stored_title = ""
    if meta:
        supplied = ((meta.get("answer") or {}).get("options") or [])
        stored_title = str(meta.get("title") or "").strip()
    heading = local_heading(question)
    if allow_network and not os.environ.get("PYTEST_CURRENT_TEST"):
        ai = _ai_trio(question, known, api_key=api_key, model=model)
        if ai and len(ai.get("options") or []) == 3:
            ai.setdefault("title", stored_title or heading["title"])
            if stored_title:
                ai["title"] = stored_title
            ai.setdefault("sticker", heading["sticker"])
            return ai
    if not known:
        known = _solve_question(question)
    packed = normalize_trio(known, supplied)
    packed["title"] = stored_title or heading["title"]
    packed["sticker"] = heading["sticker"]
    return packed
