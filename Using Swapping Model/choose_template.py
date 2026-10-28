"""
Pick a local template for a question, then a skin-tone version of that template.

Several questions can share one cluster. A cluster is one scene. Each scene
can have up to three pictures of the same scene:

    white  light skin
    brown  medium skin
    black  deep skin

The swap uses the picture whose skin is closest to the uploaded child, so a
deep skin tone is pasted onto a deep-skin face, not onto a light-skin face.

Drop the pictures in ghost/templates/ and list them in templates/index.json.
Google Drive replaces this folder later. One template per question comes later too.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

GHOST_ROOT = Path(__file__).resolve().parent
TEMPLATES_ROOT = GHOST_ROOT / "templates"
INDEX_PATH = TEMPLATES_ROOT / "index.json"

SKIN_TONES = ("white", "brown", "black")

# Words that do not identify the scene. Role names are checked separately.
_SKIP_WORDS = {
    "a", "an", "the", "of", "with", "and", "or", "to", "on", "in", "at", "for",
    "from", "by", "be", "is", "are", "was", "were", "will", "how", "many",
    "what", "which", "who", "their", "them", "they", "his", "her", "each",
    "between", "equally", "sharing", "share", "into", "there", "this", "that",
    "do", "does", "did", "before", "after", "when", "where", "have", "has",
    "had", "can", "could", "should", "would", "please", "show", "exactly",
    "include", "including", "one", "two", "title", "question", "text", "options",
    "user", "name", "child", "grandfather", "grandmother", "father", "mother",
    "brother", "sister", "uncle", "aunt", "sibling", "grandpa", "grandma",
}

_ROLE_FROM_PLACEHOLDER = {
    "user_name": "child",
    "child_name": "child",
    "grandfather_name": "grandfather",
    "grandmother_name": "grandmother",
    "father_name": "father",
    "mother_name": "mother",
    "brother_name": "brother",
    "sister_name": "sister",
    "uncle_name": "uncle",
    "aunt_name": "aunt",
    "sibling_name": "sibling",
}


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def load_index(path=None):
    index_path = Path(path) if path else INDEX_PATH
    if not index_path.is_file():
        return {"clusters": []}
    data = json.loads(index_path.read_text(encoding="utf-8-sig"))
    data.setdefault("clusters", [])
    return data


def tone_from_ita(ita):
    """Map a skin ITA angle in degrees to the three template buckets."""
    if ita >= 41:
        return "white"
    if ita >= -10:
        return "brown"
    return "black"


def skin_tone_from_bgr(image):
    """
    Estimate white / brown / black from a BGR photo.

    Uses the median ITA of pixels in a common skin-color range. ITA is the
    dermatology angle between lightness and the yellow-blue axis.
    """
    import cv2
    import numpy as np

    if image is None or image.size == 0:
        raise ValueError("No image to read a skin tone from.")
    ycrcb = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
    mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype("float32")
    lightness = lab[:, :, 0] * (100.0 / 255.0)
    yellow = lab[:, :, 2] - 128.0
    skin = mask > 0
    if int(skin.sum()) < 40:
        h, w = image.shape[:2]
        skin = np.zeros((h, w), dtype=bool)
        skin[h // 5: 4 * h // 5, w // 5: 4 * w // 5] = True
    ita = np.degrees(np.arctan2(lightness[skin] - 50.0, yellow[skin]))
    return tone_from_ita(float(np.median(ita)))


def skin_tone_from_photo(path):
    import cv2

    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Could not read a face photo for skin tone: {path}")
    return skin_tone_from_bgr(image)


def _singular(word):
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("xes", "ches", "shes", "sses")) and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def objects_from_question(question):
    """Scene words from the question, such as apple and plate. No API."""
    words = re.findall(r"[a-z0-9]+", str(question).lower())
    found = []
    for word in words:
        word = _singular(word)
        if word.isdigit() or word in _SKIP_WORDS or word.endswith("_name"):
            continue
        if word not in found:
            found.append(word)
    return found


def roles_mentioned(question):
    text = str(question).lower()
    roles = []
    tokens = sorted(_ROLE_FROM_PLACEHOLDER.items(), key=lambda item: -len(item[0]))
    for token, role in tokens:
        if re.search(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", text) and role not in roles:
            roles.append(role)
    return roles


def cluster_objects(cluster):
    words = []
    for item in cluster.get("objects") or []:
        for word in re.findall(r"[a-z0-9]+", str(item).lower()):
            word = _singular(word)
            if word not in words:
                words.append(word)
    return words


def _listed_question(question, cluster):
    query = _norm(question)
    if not query:
        return False
    for item in list(cluster.get("questions") or []) + list(cluster.get("match") or []):
        name = _norm(item)
        if name and (name == query or name in query or query in name):
            return True
    return False


def _cluster_topic(cluster):
    names = [cluster.get("topic") or ""]
    names.extend(cluster.get("topics") or [])
    return {_norm(name) for name in names if _norm(name)}


def _in_topic(cluster, topic):
    if not topic:
        return True
    return _norm(topic) in _cluster_topic(cluster)


def template_files(cluster, root=None):
    """Template pictures that are actually on disk for this scene."""
    folder = Path(root) if root else TEMPLATES_ROOT
    found = []
    for tone, name in (cluster.get("by_skin") or {}).items():
        filename = str(name or "").strip()
        if not filename:
            continue
        path = Path(filename)
        if not path.is_file():
            path = folder / filename
        if path.is_file():
            found.append((str(tone).strip().lower(), path))
    return found


def find_cluster(question, index, skin=None, topic=None):
    """
    Pick the scene for this question.

    Question words keep apples on an apples scene. A matching skin picture
    ranks higher, but a scene is not dropped only because that tone's file
    is missing. Another picture of an available scene can still be used.
    """
    wanted_objects = set(objects_from_question(question)) if question else set()
    wanted_roles = set(roles_mentioned(question)) if question else set()
    best = None
    best_score = -1
    for cluster in index.get("clusters") or []:
        if not _in_topic(cluster, topic):
            continue
        cluster_roles = {str(role).strip().lower().replace(" ", "_") for role in (cluster.get("roles_left_to_right") or [])}
        if wanted_roles and not wanted_roles.issubset(cluster_roles):
            continue
        declared = set(cluster_objects(cluster))
        overlap = wanted_objects & declared
        listed = _listed_question(question, cluster) if question else False
        if question and declared and not overlap and not listed:
            continue
        if question and not declared and not listed:
            continue
        has_skin = bool(skin) and skin in (cluster.get("by_skin") or {})
        score = len(overlap) + (10 if listed else 0) + (5 if has_skin else 0)
        if score > best_score:
            best = cluster
            best_score = score
    return best


def choose_question(topic, index, root=None, skin=None):
    """
    The child picked a topic, such as addition. Choose a question inside that
    topic whose template picture is actually on disk.
    """
    folder = Path(root) if root else TEMPLATES_ROOT
    ready = []
    for cluster in index.get("clusters") or []:
        if not _in_topic(cluster, topic):
            continue
        files = template_files(cluster, folder)
        if not files:
            continue
        tones = {tone for tone, _path in files}
        ready.append((1 if skin in tones else 0, len(files), cluster))
    if not ready:
        return None
    ready.sort(key=lambda item: (item[0], item[1]), reverse=True)
    cluster = ready[0][2]
    questions = [str(item).strip() for item in (cluster.get("questions") or []) if str(item).strip()]
    return {
        "cluster": cluster,
        "question": questions[0] if questions else (cluster.get("id") or topic),
    }


def child_photo(photos):
    for role in ("child", "user", "son", "daughter", "boy", "girl"):
        if role in photos:
            return photos[role]
    return None


def resolve_template(cluster, skin, root=None):
    """
    Use this skin tone's picture when that file exists and its face tone agrees.

    Otherwise use another template picture that is on disk so the swap still runs.
    """
    files = template_files(cluster, root)
    if not files:
        raise SystemExit(
            f"Cluster {cluster.get('id') or '?'} has no template image on disk."
        )
    ranked = []
    for tone, path in files:
        seen = measured_skin_tone(path)
        if tone == skin and (seen is None or seen == skin):
            rank = 0
        elif seen == skin:
            rank = 1
        else:
            rank = 2
        ranked.append((rank, tone, path))
    ranked.sort(key=lambda item: item[0])
    _rank, tone, path = ranked[0]
    return path, tone


def measured_skin_tone(path):
    """Read skin tone from the template image itself. No API. None if the file is not a photo."""
    try:
        import cv2
    except ImportError:
        return None
    image = cv2.imread(str(path))
    if image is None:
        return None
    return skin_tone_from_bgr(image)


def roles_for_cluster(cluster):
    roles = cluster.get("roles_left_to_right") or []
    cleaned = [str(role).strip().lower().replace(" ", "_") for role in roles if str(role).strip()]
    if not cleaned:
        raise SystemExit(
            f"Cluster {cluster.get('id') or '?'} needs roles_left_to_right."
        )
    return cleaned
