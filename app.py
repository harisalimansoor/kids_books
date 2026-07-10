"""
Main Streamlit app — Personalised Maths Question Generator
Blueprint-to-Render pipeline with deterministic image compositing.
"""

import os
import time
import re
import itertools
from io import BytesIO

import streamlit as st

from config import IMAGE_COST, IMAGE_STYLES

from file_handlers import get_topics_for_grade, load_sample_questions, load_all_questions_for_grade
from prompt_builder import build_family_context
from pdf_generator import generate_pdf, cleanup_temp_images
from utils import create_safe_filename, detect_role, fix_you_verb_conjugation, capitalize_you

# Blueprint-to-Render pipeline (only image generation method)
from blueprint_generator import generate_blueprint, OBJECT_KEYWORDS
from ai_renderer import render_image as ai_render, _build_prompt, _build_text_prompt
from face_swap_processor import swap_faces
from role_remapper import remap_question_roles

# ------------------------------------------------------------------------------
# Hobby → object mapping
# ------------------------------------------------------------------------------
_HOBBY_MAP = [
    (["football", "soccer", "rugby", "basketball", "tennis", "cricket", "baseball",
      "volleyball", "hockey", "golf", "sports", "ball", "sport", "athletic",
      "bounce", "bouncy", "throw", "catch", "bowling"], "ball"),
    (["reading", "books", "book", "story", "stories", "library", "reader"], "book"),
    (["drawing", "art", "painting", "sketch", "coloring", "colouring", "paint",
      "sketching", "artist", "creative"], "crayon"),
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
    (["crayons", "crayon", "color", "colour", "colors", "colours"], "crayon"),
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

# ------------------------------------------------------------------------------
# Category → object mapping (for favourite categories feature)
# ------------------------------------------------------------------------------
_OBJECT_CATEGORY = {
    # Food
    "apple": "food", "banana": "food", "orange": "food", "grape": "food",
    "cookie": "food", "biscuit": "food", "candy": "food", "sweet": "food",
    "chocolate": "food", "lollipop": "food", "egg": "food", "cupcake": "food",
    "sandwich": "food", "cherry": "food", "strawberry": "food", "pear": "food",
    "lemon": "food", "cake": "food", "pizza": "food",
    # Toy
    "ball": "toy", "block": "toy", "doll": "toy", "car": "toy",
    "train": "toy", "plane": "toy", "boat": "toy", "bicycle": "toy",
    "scooter": "toy", "robot": "toy", "marble": "toy", "dice": "toy",
    "teddy bear": "toy",
    # Animal
    "frog": "animal", "fish": "animal", "bird": "animal", "butterfly": "animal",
    "ladybird": "animal", "dog": "animal", "cat": "animal", "rabbit": "animal",
    # Character (minimal mapping — mostly lives in hobby substitution)
    "toy soldier": "character", "doll": "character",
    # Sport
    "ball": "sport",
}

_FAVORITE_OPTIONS = ["animal", "food", "toy", "character", "sport"]


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


def replace_objects_by_category(text: str, selected_categories: list[str],
                                 fav_map: dict[str, str], fav_color: str = "") -> str:
    """
    Replace objects whose category matches a selected favourite category
    with the child's preferred item for that category.
    If fav_color is set, also prepend it to replaced objects.
    """
    if not selected_categories or not fav_map:
        return text
    cat_set = set(selected_categories)

    known = sorted(_OBJECT_CATEGORY.keys(), key=len, reverse=True)
    for obj in known:
        cat = _OBJECT_CATEGORY.get(obj)
        if cat not in cat_set:
            continue
        replacement = fav_map.get(cat)
        if not replacement or not replacement.strip():
            continue
        replacement = replacement.strip().lower()
        # Pluralize
        if replacement.endswith(("s", "x", "ch", "sh")):
            repl_plural = replacement + "es"
        elif replacement.endswith("y") and len(replacement) > 1 and replacement[-2] not in "aeiou":
            repl_plural = replacement[:-1] + "ies"
        else:
            repl_plural = replacement + "s"

        pat = re.compile(r'\b' + re.escape(obj) + r'(?:s|es)?\b', re.IGNORECASE)
        if not pat.search(text):
            continue

        def _replacer(m: re.Match, o: str = obj,
                      r_s: str = replacement, r_p: str = repl_plural) -> str:
            raw = m.group(0)
            raw_lower = raw.lower()
            stem = raw_lower[:-2] if raw_lower.endswith("es") else (
                raw_lower[:-1] if raw_lower.endswith("s") and not raw_lower.endswith("ss")
                else raw_lower
            )
            # Don't replace if stem matches already (avoids double-replacement)
            if stem == r_s:
                return raw
            # Determine singular/plural
            if raw_lower.endswith("es") or (raw_lower.endswith("s") and not raw_lower.endswith("ss")):
                result = r_p
            else:
                result = r_s
            # Prepend favourite colour if set
            if fav_color:
                result = f"{fav_color} {result}"
            return result

        text = pat.sub(_replacer, text)
    return text


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


def _pluralize(word: str) -> str:
    """Simple pluralization for objects used in questions."""
    overrides = {
        "toy car": "toy cars",
        "teddy bear": "teddy bears",
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
    "Just tell us about your child — favourite colour, pets, hobbies, and family — "
    "and we'll make a worksheet that feels like it's just for them."
)

# Pipeline state
if "pipeline" not in st.session_state:
    st.session_state.pipeline = None

# ------------------------------------------------------------------------------
# Student Information form
# ------------------------------------------------------------------------------
st.subheader("👤 About Your Child")

col_name, col_gen = st.columns(2)
with col_name:
    student_name = st.text_input("Name*", placeholder="e.g., Oliver")
with col_gen:
    gender = st.selectbox("Gender*", ["Select", "Boy", "Girl", "Other"])

row2 = st.columns(3)
with row2[0]:
    hobbies = st.text_input("Hobbies / Interests", placeholder="e.g., football, colouring")
with row2[1]:
    fav_color = st.text_input("Favourite Colour", placeholder="e.g., green, pink",
                              help="Used in object descriptions (e.g. 'blue apples')")
with row2[2]:
    pet_name = st.text_input("Pet Name(s)", placeholder="e.g., Buster, Coco")

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

# ------------------------------------------------------------------------------
# Favourite Things  (visible, always shown)
# ------------------------------------------------------------------------------
st.divider()
st.markdown("#### ⭐ Favourite Things")
st.caption("Tell us what your child loves — we'll swap matching objects into the questions (e.g., 'apples' become 'pizzas' if Food is selected).")
selected_categories = st.multiselect(
    "Categories to personalise:", options=_FAVORITE_OPTIONS, default=[],
    help="Select the categories you'd like to fill in. Leave empty to use the child's hobby instead.")
fav_map = {}
if selected_categories:
    fav_rows = [selected_categories[i:i+3] for i in range(0, len(selected_categories), 3)]
    for chunk in fav_rows:
        cols = st.columns(3)
        for ci, cat in enumerate(chunk):
            with cols[ci]:
                fav_map[cat] = st.text_input(
                    f"Favourite {cat.title()}(s):", placeholder=f"e.g., favourite {cat}",
                    key=f"fav_{cat}")

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
    num_questions = st.number_input("Number of questions", min_value=1, max_value=50, value=10)

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

col_ps1, col_ps2, col_ps3 = st.columns(3)
with col_ps1:
    include_images = st.checkbox("Include illustrations", value=True)
with col_ps2:
    counting_ability = st.selectbox("Biggest number to practise", [10, 20, 50], index=1)
with col_ps3:
    theme_style = st.selectbox("Picture style", list(IMAGE_STYLES.keys()), index=0)

anything_else = st.text_area(
    "Anything else for the pictures? (optional)",
    placeholder="e.g., loves dinosaurs, Christmas setting",
    help="Extra context passed to the AI when making the illustrations.")

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
    else:
        # ---------- Family Context ----------
        siblings_str = ", ".join(
            s.get("name", "").strip()
            for s in st.session_state.get("siblings_list", [])
            if s.get("name", "").strip()
        ) if st.session_state.get("siblings_list") else ""
        family_context = build_family_context(
            mother_name, father_name, grandmother_name,
            grandfather_name, siblings_str
        )

        # ---------- Load Questions ----------
        with st.spinner("📄 Loading sample problems..."):
            if use_all_topics or not selected_topics:
                extracted_text = load_all_questions_for_grade(grade)
                topic_header_text = "All topics"
            else:
                blocks = []
                for t in selected_topics:
                    content = load_sample_questions(grade, t)
                    if content and not content.startswith("Error"):
                        blocks.append(f"=== Topic: {t} ===\n{content}\n")
                extracted_text = "\n".join(blocks)
                topic_header_text = ", ".join(selected_topics)

            if not extracted_text or extracted_text.startswith("Error"):
                st.error("Could not load sample questions from the .txt files.")
                st.stop()

            st.success("✅ Loaded sample problems!")

            with st.expander("📄 Preview of source content"):
                preview_text = extracted_text[:800]
                if len(extracted_text) > 800:
                    preview_text += "..."
                st.text(preview_text)

        # ---------- Select & Personalise Questions ----------
        with st.spinner("🤖 Selecting questions from the bank..."):
            # Split topics
            topics = extracted_text.split("=== Topic:")
            topic_questions = []
            for topic in topics:
                if not topic.strip(): continue
                lines = topic.strip().split("\n")
                qs = [l.strip() for l in lines[1:] if l.strip() and "{" in l]
                if qs:
                    topic_questions.append(qs)

            # Round-robin interleaving
            all_raw_questions = []
            for q_tuple in itertools.zip_longest(*topic_questions):
                for q in q_tuple:
                    if q is not None:
                        all_raw_questions.append(q)

            # Use all available questions (segmentation image + JSON is the reference)
            available_questions = list(all_raw_questions)

            if len(available_questions) == 0:
                st.error("No questions found in the selected topics.")
                st.stop()

            # Scale numbers to match counting ability
            selected_raw = available_questions[:num_questions]
            scaled_raw = [_scale_question_numbers(q, counting_ability) for q in selected_raw]

            # Determine hobby object and category favourites
            hobby_obj = map_hobby_to_object(hobbies)
            use_categories = bool(selected_categories and any(fav_map.get(c, "").strip() for c in selected_categories))

            # Pick one sibling per question (random)
            siblings_data = st.session_state.get("siblings_list", [])
            use_multi_sibling = bool(siblings_data and any(s.get("name", "").strip() for s in siblings_data))

            questions_data = []  # (personalized_text, raw_text, sibling_index)
            import random as _random
            for i, q_raw in enumerate(scaled_raw):
                # Pick sibling for this question
                if use_multi_sibling:
                    valid_indices = [idx for idx, s in enumerate(siblings_data) if s.get("name", "").strip()]
                    sib_idx = _random.choice(valid_indices) if valid_indices else -1
                    if sib_idx >= 0:
                        chosen = siblings_data[sib_idx]
                        sib_name = chosen["name"].strip()
                        sib_pronoun = "her" if chosen["gender"] == "Girl" else "him"
                        sib_possessive = "her" if chosen["gender"] == "Girl" else "his"
                    else:
                        sib_idx = -1
                        sib_name = "sibling"
                        sib_pronoun = "him"
                        sib_possessive = "his"
                else:
                    sib_idx = -1
                    sib_name = "sibling"
                    sib_pronoun = "him"
                    sib_possessive = "his"

                replacements = {
                    r'\{user_name\}':            "you",
                    r'\{mother_name\}':          mother_name or "mother",
                    r'\{father_name\}':          father_name or "father",
                    r'\{grandmother_name\}':     grandmother_name or "grandmother",
                    r'\{grandfather_name\}':     grandfather_name or "grandfather",
                    r'\{sibling_name\}':         sib_name,
                    r'\{sibling_pronoun\}':      sib_pronoun,
                    r'\{sibling_possessive\}':   sib_possessive,
                }
                text = q_raw
                for pattern, replacement in replacements.items():
                    text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                # Fix verb conjugation when subject is "you"
                text = fix_you_verb_conjugation(text)
                text = capitalize_you(text)
                # Object replacement: category-based or hobby-based
                if "shapes" not in q_raw.lower():
                    if use_categories:
                        text = replace_objects_by_category(text, selected_categories, fav_map, fav_color)
                        q_raw = replace_objects_by_category(q_raw, selected_categories, fav_map, fav_color)
                    elif hobby_obj:
                        text = replace_objects_in_text(text, hobby_obj)
                        q_raw = replace_objects_in_text(q_raw, hobby_obj)
                questions_data.append((text, q_raw, sib_idx))

            questions = [item[0] for item in questions_data]

            st.info(f"✅ Selected {len(questions)} questions from bank")
            with st.expander("👀 Preview Generated Questions"):
                for i, q in enumerate(questions, 1):
                    st.write(f"{i}. {q}")

        # ---------- Store pipeline state ----------
        sibling_gender_agg = "Girl" if any(s.get("gender") == "Girl" for s in st.session_state.get("siblings_list", [])) else "Boy"
        # Base replacements for role_remapper (uses first sibling as representative)
        first_sib = st.session_state.get("siblings_list", [{}])[0].get("name", "").strip() if st.session_state.get("siblings_list") else "sibling"
        base_replacements = {
            r'\{user_name\}': "you",
            r'\{mother_name\}': mother_name or "mother",
            r'\{father_name\}': father_name or "father",
            r'\{grandmother_name\}': grandmother_name or "grandmother",
            r'\{grandfather_name\}': grandfather_name or "grandfather",
            r'\{sibling_name\}': first_sib,
        }
        st.session_state.pipeline = {
            "phase": "blueprint" if include_images else "pdf",
            "questions_data": questions_data,
            "questions": questions,
            "synced_questions": list(questions),
            "student_name": student_name,
            "gender": gender,

            "sibling_gender": sibling_gender_agg,
            "siblings_list": st.session_state.get("siblings_list", []),
            "grade": grade,
            "topic_header_text": topic_header_text,
            "include_images": include_images,
            "saved_face_paths": saved_face_paths,
            "image_paths": [],
            "replacements": base_replacements,
            "pet_name": pet_name,
            "fav_color": fav_color,
            "selected_categories": selected_categories,
            "fav_map": fav_map,
            "counting_ability": counting_ability,
            "theme_style": theme_style,
            "anything_else": anything_else,
        }
        st.rerun()

# ══════════════════════════════════════════════════════════════════
# PIPELINE EXECUTOR
# ══════════════════════════════════════════════════════════════════
pipeline = st.session_state.get("pipeline")
if pipeline is not None:
    phase = pipeline["phase"]

    if phase == "blueprint":
        pinfo = st.info("📐 Generating blueprints for all questions...")
        blueprints_data = []
        role_to_saved = {
            "grandmother_name": "grandmother",
            "grandfather_name": "grandfather",
            "mother_name": "mother",
            "father_name": "father",
            "sibling_name": "sibling",
            "user_name": "user",
        }
        for idx, item in enumerate(pipeline["questions_data"], start=1):
            q_pers, q_raw, sib_idx = item if len(item) == 3 else (*item, -1)
            # Build face map for all possible roles — blueprint will paste
            # matching faces onto head positions instead of green circles
            face_map_for_bp = {}
            for role_key, saved_key in role_to_saved.items():
                if saved_key in pipeline["saved_face_paths"]:
                    face_map_for_bp[role_key] = pipeline["saved_face_paths"][saved_key]
            # Map the specific sibling's face if we have one
            if sib_idx >= 0:
                sib_face_key = f"sibling_{sib_idx}"
                if sib_face_key in pipeline["saved_face_paths"]:
                    face_map_for_bp["sibling_name"] = pipeline["saved_face_paths"][sib_face_key]

            # Remap roles to maximize use of uploaded face images
            q_raw, q_pers, face_map_for_bp = remap_question_roles(
                q_raw, q_pers, face_map_for_bp,
                role_to_saved,
                pipeline["saved_face_paths"],
                pipeline.get("replacements", {}),
                pipeline.get("sibling_gender", "Boy"),
                user_gender=pipeline.get("gender", "Boy"),
            )
            # Update pipeline state with remapped texts
            pipeline["questions_data"][idx - 1] = (q_pers, q_raw)
            pipeline["synced_questions"][idx - 1] = q_pers

            blueprint, metadata = generate_blueprint(q_raw, face_map=face_map_for_bp)

            # Track which faces were actually used in this question
            question_face_map = {}
            for ch in metadata["characters"]:
                saved_key = role_to_saved.get(ch["role_key"])
                if saved_key and saved_key in pipeline["saved_face_paths"]:
                    question_face_map[ch["role_key"]] = pipeline["saved_face_paths"][saved_key]

            preserve = metadata.get("has_faces", False)
            prompt = _build_prompt(metadata, preserve_faces=preserve,
                                   gender=pipeline.get("gender", "Boy"),
                                   sibling_gender=pipeline.get("sibling_gender", "Boy"),
                                   theme_style=pipeline.get("theme_style", "photorealistic"),
                                   fav_color=pipeline.get("fav_color", ""),
                                   extra_context=pipeline.get("anything_else", ""))
            text_prompt = _build_text_prompt(metadata,
                                             gender=pipeline.get("gender", "Boy"),
                                             sibling_gender=pipeline.get("sibling_gender", "Boy"),
                                             theme_style=pipeline.get("theme_style", "photorealistic"),
                                             fav_color=pipeline.get("fav_color", ""),
                                             extra_context=pipeline.get("anything_else", ""))

            blueprints_data.append({
                "idx": idx,
                "blueprint": blueprint,
                "metadata": metadata,
                "prompt": prompt,
                "question_face_map": question_face_map,
                "preserve_faces": preserve,
            })

        pipeline["blueprints_data"] = blueprints_data
        pipeline["phase"] = "rendering"
        pinfo.empty()
        st.rerun()

    elif phase == "rendering":
        st.subheader("🎨 Rendering images with AI...")
        progress_bar = st.progress(0)

        blueprints_data = pipeline["blueprints_data"]
        image_paths = pipeline["image_paths"]

        for idx, data in enumerate(blueprints_data, start=1):
            timestamp = int(time.time())
            temp_path = f"temp_img_{data['idx']}_{timestamp}.jpg"

            p = (idx - 1) / len(blueprints_data)
            progress_bar.progress(p)

            with st.status(f"🎨 **Q{data['idx']}:** Rendering...", expanded=False) as step_status:
                try:
                    preserve = data.get("preserve_faces", False)
                    result = ai_render(data["blueprint"], data["metadata"],
                                       output_path=temp_path,
                                       preserve_faces=preserve,
                                       gender=pipeline.get("gender", "Boy"),
                                       sibling_gender=pipeline.get("sibling_gender", "Boy"),
                                       theme_style=pipeline.get("theme_style", "photorealistic"),
                                       fav_color=pipeline.get("fav_color", ""),
                                       pet_name=pipeline.get("pet_name", ""),
                                       extra_context=pipeline.get("anything_else", ""))

                    if result and os.path.exists(result):
                        if data["question_face_map"]:
                            step_status.write("🔄 Swapping user faces onto AI-generated characters...")
                            final_path = swap_faces(result, data["metadata"], data["question_face_map"])
                        else:
                            final_path = result
                        image_paths.append(final_path)
                        step_status.write("✅ **Illustration complete!**")
                    else:
                        fallback_path = f"temp_img_{data['idx']}_{timestamp}_fallback.jpg"
                        data["blueprint"].save(fallback_path, quality=90)
                        image_paths.append(fallback_path)
                        step_status.write("⚠️ AI unavailable — using blueprint layout")

                    step_status.update(label=f"✅ **Q{data['idx']} complete**", state="complete")
                except Exception as e:
                    step_status.write(f"❌ **Error:** {str(e)}")
                    step_status.update(label=f"❌ **Q{data['idx']} failed**", state="error")
                    print(f"ERROR Q{data['idx']}: {e}")
                    import traceback
                    traceback.print_exc()
                    image_paths.append(None)

            progress_bar.progress(idx / len(blueprints_data))

        pipeline["phase"] = "pdf"
        st.rerun()

    elif phase == "pdf":
        image_paths = pipeline["image_paths"]
        include_images = pipeline["include_images"]

        print(f"DEBUG: Generating PDF with {len(image_paths)} images")
        with st.spinner("📄 Creating PDF workbook..."):
            pdf_bytes = generate_pdf(
                pipeline["student_name"],
                pipeline["grade"],
                pipeline["topic_header_text"],
                pipeline["synced_questions"],
                image_paths if include_images else None
            )

        print(f"DEBUG: PDF generated, size = {len(pdf_bytes)} bytes")
        pipeline["pdf_bytes"] = pdf_bytes
        if include_images:
            cleanup_temp_images(image_paths)
        pipeline["phase"] = "complete"
        st.rerun()

    elif phase == "complete":
        filename = create_safe_filename(pipeline["student_name"])
        st.success("🎉 Personalised Maths Workbook ready!")
        st.download_button(
            "📥 Download PDF Workbook",
            data=BytesIO(pipeline["pdf_bytes"]),
            file_name=filename,
            mime="application/pdf",
            type="primary",
        )

        # Eval / gold data generation
        eval_filename = filename.replace(".pdf", "_eval.json") if filename.endswith(".pdf") else f"{filename}_eval.json"
        eval_data = {
            "student_name": pipeline["student_name"],
            "grade": pipeline["grade"],
            "topics": pipeline.get("topic_header_text", ""),

            "gender": pipeline.get("gender", "Boy"),
            "siblings": pipeline.get("siblings_list", []),
            "pet_name": pipeline.get("pet_name", ""),
            "fav_color": pipeline.get("fav_color", ""),
            "selected_categories": pipeline.get("selected_categories", []),
            "fav_map": pipeline.get("fav_map", {}),
            "counting_ability": pipeline.get("counting_ability", 20),
            "theme_style": pipeline.get("theme_style", "photorealistic"),
            "questions": [{"index": i + 1, "text": q}
                          for i, q in enumerate(pipeline.get("synced_questions", []))],
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