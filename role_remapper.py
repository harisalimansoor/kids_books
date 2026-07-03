"""
role_remapper.py - Dynamically remap question roles to match available face images.

When a question mentions roles that have no uploaded face photo, this module
swaps in roles that DO have uploaded faces, and updates pronouns accordingly.
"""

import re

ROLE_GENDER = {
    "grandfather_name": "male",
    "father_name":      "male",
    "grandmother_name": "female",
    "mother_name":      "female",
    "sibling_name":     "variable",
    "user_name":        "variable",
}

ROLE_KEYS = set(ROLE_GENDER.keys())

# Search for these pronoun patterns within a clause
PRONOUN_PATTERNS = re.compile(
    r"\b(in front of|beside|to)\s+(him|her|his)\b",
    re.IGNORECASE,
)

# Clause boundary: split by sentence ends, commas, and/but/or
_CLAUSE_SPLIT = re.compile(r"[.!?]+|,\s*|\s+and\s+|\s+but\s+|\s+or\s+")


def remap_question_roles(
    q_raw: str,
    q_pers: str,
    face_map: dict[str, str],
    role_to_saved: dict[str, str],
    saved_face_paths: dict[str, str],
    replacements: dict[str, str],
    sibling_gender: str = "Boy",
) -> tuple[str, str, dict[str, str]]:
    """
    Remap question roles to maximize use of uploaded face images.

    Returns (new_q_raw, new_q_pers, new_face_map).
    If no remapping needed, returns originals unchanged.
    """
    # 1. Extract role placeholders from raw question
    all_ph = re.findall(r"\{(\w+)\}", q_raw)
    question_roles = [p for p in all_ph if p in ROLE_KEYS]
    if not question_roles:
        return q_raw, q_pers, face_map

    question_roles_set = set(question_roles)

    # 2. Which roles have uploaded faces?
    available_roles = set()
    for rk, sk in role_to_saved.items():
        if sk in saved_face_paths:
            available_roles.add(rk)

    if not available_roles:
        return q_raw, q_pers, face_map

    roles_with_faces = question_roles_set & available_roles
    roles_without_faces = question_roles_set - available_roles
    extra_roles = available_roles - question_roles_set

    if not roles_without_faces or not extra_roles:
        return q_raw, q_pers, face_map

    # 3. Build remapping: assign extra uploaded roles to missing question roles
    remap = {}
    extra_list = list(extra_roles)
    for missing in roles_without_faces:
        if extra_list:
            remap[missing] = extra_list.pop(0)

    if not remap:
        return q_raw, q_pers, face_map

    # 4. Collect all gender changes before applying (to fix pronouns per-role)
    gender_changes = {}
    for old_role, new_role in remap.items():
        old_g = _effective_gender(old_role, sibling_gender)
        new_g = _effective_gender(new_role, sibling_gender)
        if old_g != new_g:
            gender_changes[old_role] = {"from": old_g, "to": new_g}

    # 5. Apply role placeholder and name replacements
    new_q_raw = q_raw
    new_q_pers = q_pers
    new_face_map = dict(face_map)

    for old_role, new_role in remap.items():
        # Replace role placeholder in q_raw
        new_q_raw = re.sub(r"\{" + old_role + r"\}", "{" + new_role + "}", new_q_raw)

        # Replace role name in q_pers
        old_name = _get_name_for_role(old_role, replacements)
        new_name = _get_name_for_role(new_role, replacements)
        if old_name and new_name and old_name != new_name:
            new_q_pers = re.sub(
                r"\b" + re.escape(old_name) + r"\b",
                new_name,
                new_q_pers,
            )

        # Update face_map: point old_role to the swapped-in face
        saved_key = role_to_saved.get(new_role)
        if saved_key and saved_key in saved_face_paths:
            new_face_map[old_role] = saved_face_paths[saved_key]

    # 6. Fix pronouns per-role (clause-scoped, so we don't affect other roles)
    for old_role, change in gender_changes.items():
        new_role = remap[old_role]

        # Fix q_raw: look for the new placeholder {new_role}
        new_q_raw = _fix_pronouns_for_role(
            new_q_raw, "{" + new_role + "}", change["from"], change["to"],
        )

        # Fix q_pers: look for the new role's personalized name
        new_name = _get_name_for_role(new_role, replacements)
        if new_name:
            new_q_pers = _fix_pronouns_for_role(
                new_q_pers, new_name, change["from"], change["to"],
            )

    return new_q_raw, new_q_pers, new_face_map


def _fix_pronouns_for_role(
    text: str,
    role_marker: str,
    from_gender: str,
    to_gender: str,
) -> str:
    """
    Find the clause containing `role_marker` and fix pronouns within it.
    Only changes pronouns that match `from_gender` to `to_gender`.
    """
    # Split into clauses, find the one containing role_marker
    parts = _CLAUSE_SPLIT.split(text)
    separators = _CLAUSE_SPLIT.findall(text)

    # Rebuild: walk through original text finding which clause has the role
    # Simpler approach: find all pronoun matches, check proximity to role
    def _fix_match(m: re.Match) -> str:
        prefix = m.group(1)  # e.g. "in front of", "beside", "to"
        pronoun = m.group(2).lower()
        # Check if this pronoun is near the role_marker in the text
        start = max(0, m.start() - 80)
        end = m.end()
        nearby = text[start:end].lower()

        if role_marker.lower() in nearby:
            if pronoun in ("him", "his") and to_gender == "female":
                return f"{prefix} her"
            elif pronoun == "her" and to_gender == "male":
                return f"{prefix} him"
        return m.group(0)

    return PRONOUN_PATTERNS.sub(_fix_match, text)


def _effective_gender(role_key: str, sibling_gender: str) -> str:
    """Resolve gender for variable-gender roles (sibling, user)."""
    if role_key == "sibling_name":
        return "male" if sibling_gender == "Boy" else "female"
    if role_key == "user_name":
        return "male" if sibling_gender == "Boy" else "female"
    return ROLE_GENDER.get(role_key, "male")


def _get_name_for_role(role_key: str, replacements: dict[str, str]) -> str | None:
    """Get the personalized name for a role key from the replacements dict."""
    key = r"{" + role_key + r"}"
    for pat, repl in replacements.items():
        if pat.replace("\\", "") == key:
            return repl
    return None
