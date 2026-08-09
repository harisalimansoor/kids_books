"""
Retrieve example questions from question_bank/grade_1 for RAG prompting.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

QUESTION_BANK_DIR = Path(__file__).resolve().parent.parent / "question_bank" / "grade_1"

# Extra keyword bags help score the best examples inside a mixed topic file
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "numbers to 10": ["count", "how many", "ten frame", "number", "fewer", "more", "estimate"],
    "numbers to 20": ["count", "how many", "number line", "greater", "fewer", "order", "20"],
    "working with numbers to 10": [
        "add", "more", "altogether", "total", "number sentence",
        "take away", "left", "subtract", "part-whole", "combine",
    ],
    "fractions": ["half", "halves", "whole", "equal parts", "fraction"],
    "geometry": ["shape", "triangle", "square", "circle", "cube", "sides", "faces", "roll"],
    "measures": ["taller", "shorter", "longer", "longest", "shortest", "tallest", "wider"],
    "time": ["o'clock", "clock", "hour", "minute", "time", "morning", "afternoon"],
    "position": ["above", "below", "next to", "left", "right", "between", "behind", "in front"],
    "statistics": ["sort", "set", "how many", "more", "less", "venn", "group"],
}

# Map legacy / extracted-bank topic names → question_bank topics
_TOPIC_ALIASES: dict[str, str] = {
    "addition": "working with numbers to 10",
    "subtraction": "working with numbers to 10",
    "multiplication": "working with numbers to 10",
    "shapes": "geometry",
    "counting": "numbers to 10",
    "basic addition": "working with numbers to 10",
    "basic subtraction": "working with numbers to 10",
    "basic multiplication": "working with numbers to 10",
    "basic geometry": "geometry",
    "basic fractions": "fractions",
    "basic measurement": "measures",
    "basic time": "time",
    "comparison": "numbers to 20",
    "comparing numbers": "numbers to 20",
}


def _stem_to_title(stem: str) -> str:
    return stem.replace("_", " ").strip().title()


def _title_to_stem(title: str) -> str:
    return re.sub(r"\s+", "_", title.strip().lower())


@lru_cache(maxsize=1)
def list_question_bank_topics() -> list[str]:
    """Display titles for every question_bank/grade_1/*.txt file."""
    if not QUESTION_BANK_DIR.exists():
        return []
    topics = []
    for path in sorted(QUESTION_BANK_DIR.glob("*.txt")):
        topics.append(_stem_to_title(path.stem))
    return topics


def resolve_topic(topic: str) -> str | None:
    """Map a UI / legacy topic name onto a question_bank topic title."""
    if not topic or not str(topic).strip():
        return None
    raw = str(topic).strip()
    available = {t.lower(): t for t in list_question_bank_topics()}
    if raw.lower() in available:
        return available[raw.lower()]
    alias = _TOPIC_ALIASES.get(raw.lower())
    if alias and alias in available:
        return available[alias]
    # fuzzy: substring
    for key, title in available.items():
        if key in raw.lower() or raw.lower() in key:
            return title
    return None


def _parse_examples_from_file(path: Path) -> list[str]:
    examples: list[str] = []
    if not path.exists():
        return examples
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("==="):
            continue
        # Drop leading list markers
        line = re.sub(r"^[\d]+[\.\)]\s*", "", line)
        line = re.sub(r"^[\-\•]+\s*", "", line)
        if len(line) < 12:
            continue
        examples.append(line)
    return examples


@lru_cache(maxsize=32)
def load_topic_examples(topic: str) -> list[str]:
    """All example lines for a topic (resolved against question_bank)."""
    resolved = resolve_topic(topic) or topic
    stem = _title_to_stem(resolved)
    path = QUESTION_BANK_DIR / f"{stem}.txt"
    if not path.exists():
        # try resolved title from list
        for t in list_question_bank_topics():
            if t.lower() == resolved.lower():
                path = QUESTION_BANK_DIR / f"{_title_to_stem(t)}.txt"
                break
    return _parse_examples_from_file(path)


def _score_example(example: str, topic: str, query: str | None) -> float:
    text = example.lower()
    score = 0.0
    keys = _TOPIC_KEYWORDS.get(topic.lower(), [])
    for kw in keys:
        if kw in text:
            score += 1.0
    if query:
        for token in re.findall(r"[a-z0-9']+", query.lower()):
            if len(token) < 3:
                continue
            if token in text:
                score += 0.5
    # Prefer shorter, worksheet-friendly stems
    if 20 <= len(example) <= 140:
        score += 0.5
    if any(bad in text for bad in ("partner", "fold one", "cut along", "ten frame below")):
        score -= 0.8
    return score


def retrieve_examples(
    topic: str,
    *,
    k: int = 8,
    query: str | None = None,
    skill_hint: str | None = None,
) -> list[str]:
    """
    RAG retrieve: return the top-k example questions for a topic from question_bank.
    Optional query / skill_hint bias the ranking (e.g. 'addition', 'half').
    """
    resolved = resolve_topic(topic) or topic
    examples = load_topic_examples(resolved)
    if not examples:
        return []

    q = " ".join(x for x in (query or "", skill_hint or "") if x).strip() or None
    ranked = sorted(
        examples,
        key=lambda ex: _score_example(ex, resolved, q),
        reverse=True,
    )
    # de-dupe case-insensitively
    out: list[str] = []
    seen: set[str] = set()
    for ex in ranked:
        key = ex.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(ex)
        if len(out) >= k:
            break
    return out


def skill_hint_for_legacy_topic(topic: str) -> str | None:
    """When UI still uses Addition/Subtraction/etc., bias retrieval inside mixed files."""
    t = (topic or "").strip().lower()
    if "add" in t:
        return "add more altogether total number sentence"
    if "subtract" in t:
        return "take away left subtract fewer"
    if "multi" in t:
        return "groups sets altogether equal groups"
    if "fraction" in t or "half" in t:
        return "half halves equal parts whole"
    if "shape" in t or "geometry" in t:
        return "shape sides faces triangle square"
    return None
