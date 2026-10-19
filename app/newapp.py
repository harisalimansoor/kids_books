"""
app/newapp.py
─────────────────────────────────────────────────────────────────────────────
Streamlit UI for the multi-grade personalized math workbook pipeline.

Form fields: child name, age, gender, family, favourite foods/hobbies, grade, topics, face uploads.
Generation uses pre-built role-locked question templates — not kitchen RAG.
"""

from __future__ import annotations

import base64
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path

import streamlit as st

PIPELINE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

try:
    from app.pdf_generator import generate_pdf
    from app.utils import create_safe_filename
    from app.grade_config import (
        get_grade_topics,
        grade_select_options, is_grade_available,
        generate_job_id, get_runtime_dir, write_job_metadata,
        GradeNotFoundError,
    )
except ImportError:
    from pdf_generator import generate_pdf  # type: ignore
    from utils import create_safe_filename  # type: ignore
    from grade_config import (              # type: ignore
        get_grade_topics,
        grade_select_options, is_grade_available,
        generate_job_id, get_runtime_dir, write_job_metadata,
        GradeNotFoundError,
    )

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except Exception:
    pass

# Reload stem_pipeline so Streamlit picks up new helpers after file edits
import importlib  # noqa: E402
import stem_pipeline as _stem_pipeline  # noqa: E402

_stem_pipeline = importlib.reload(_stem_pipeline)
ADULT_ROLES = _stem_pipeline.ADULT_ROLES
ROLE_DISPLAY = _stem_pipeline.ROLE_DISPLAY
display_name_for_role = _stem_pipeline.display_name_for_role
fill_question_text = _stem_pipeline.fill_question_text
list_ready_stems = _stem_pipeline.list_ready_stems
list_template_foods = _stem_pipeline.list_template_foods
list_template_hobbies = _stem_pipeline.list_template_hobbies
list_topics = _stem_pipeline.list_topics
mcq_from_meta = _stem_pipeline.mcq_from_meta
partition_by_interests = _stem_pipeline.partition_by_interests
partition_by_adult_roles = _stem_pipeline.partition_by_adult_roles
partition_by_child_gender = _stem_pipeline.partition_by_child_gender
select_stems = _stem_pipeline.select_stems
stems_for_available_roles = _stem_pipeline.stems_for_available_roles
topic_label = _stem_pipeline.topic_label

# AI image generation engine (question_image.md + question + family photos)
import image_generator as _image_generator_mod  # noqa: E402
_image_generator_mod = importlib.reload(_image_generator_mod)
build_workbook_items_ai_generated = _image_generator_mod.build_workbook_items_ai_generated

# Front cover generator (reads grades/<grade>/prompts/front_page.md at runtime)
import front_cover_generator as _front_cover_mod  # noqa: E402
_front_cover_mod = importlib.reload(_front_cover_mod)
generate_front_cover = _front_cover_mod.generate_front_cover
FrontCoverError     = _front_cover_mod.FrontCoverError

# ------------------------------------------------------------------------------
# Page
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="My Maths Practice Book — Templates",
    page_icon="📚",
    layout="centered",
)

st.title("📚 My Maths Practice Book")
st.write(
    "Create a personalised maths workbook for the selected year group, with fun illustrations! "
    "Tell us about your child — favourite colour, family, and "
    "favourite foods & hobbies — and we'll make a worksheet from "
    "**pre-built question templates**."
)
st.caption(
    "Illustrations use direct AI scene generation: the selected grade's question_image.md + Question + Reference Photos → "
    "OpenAI GPT-5.4 Image 2. Requires `OPENROUTER_API_KEY` in `.env`."
)

if "pipeline" not in st.session_state:
    st.session_state.pipeline = None

# ------------------------------------------------------------------------------
# Student Information form (aligned with app.py)
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
    help="The PDF workbook theme (headers, badges, accents) uses this colour when you enter one.",
)
if (fav_color or "").strip():
    st.caption(
        f"Workbook theme will use **{(fav_color or '').strip()}** for headings, "
        "question badges, and accent colours in the PDF."
    )
else:
    st.caption(
        "Add a favourite colour and the workbook PDF theme (headings, badges, accents) "
        "will match it — e.g. pink → pink accents throughout."
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
row_fam3 = st.columns(2)
with row_fam3[0]:
    uncle_name = st.text_input("Uncle's Name", placeholder="Optional")
with row_fam3[1]:
    aunt_name = st.text_input("Aunt's Name", placeholder="Optional")
row_fam4 = st.columns(2)
with row_fam4[0]:
    brother_name = st.text_input("Brother's Name", placeholder="Optional")
with row_fam4[1]:
    sister_name = st.text_input("Sister's Name", placeholder="Optional")

family_names = {
    "mother": (mother_name or "").strip(),
    "father": (father_name or "").strip(),
    "grandmother": (grandmother_name or "").strip(),
    "grandfather": (grandfather_name or "").strip(),
    "uncle": (uncle_name or "").strip(),
    "aunt": (aunt_name or "").strip(),
    "brother": (brother_name or "").strip(),
    "sister": (sister_name or "").strip(),
}

# --- Favourite Foods & Hobbies (only options that exist on ready templates for selected grade) ---
st.divider()
st.markdown("#### 🍳 Favourite Foods & 🎨 Hobbies")
st.caption(
    "Options come from ready templates in the selected grade's question banks. "
    "When you pick any, the workbook prefers matching stems "
    "(e.g. Apples → apple questions; Stickers → sticker questions). "
    "Leave empty to use any ready stem."
)
# Foods and hobbies come from the selected grade's own question bank.
_grade_options = grade_select_options()
_grade_by_label = {opt["label"]: opt for opt in _grade_options}
_persisted_grade_label = st.session_state.get("np_grade_select")
_pre_grade = _grade_by_label.get(_persisted_grade_label or "")
_pre_grade_id = _pre_grade["id"] if _pre_grade and _pre_grade["available"] else None
if _pre_grade_id:
    try:
        _available_foods = list_template_foods(_pre_grade_id)
        _available_hobbies = list_template_hobbies(_pre_grade_id)
    except Exception:
        _available_foods = []
        _available_hobbies = []
else:
    _available_foods = []
    _available_hobbies = []

_col_food, _col_hobby = st.columns(2)
with _col_food:
    if _available_foods:
        favourite_foods = st.multiselect(
            "Favourite Foods",
            options=_available_foods,
            default=[],
            key="np_favourite_foods_picker",
            help="Only foods tagged on ready templates.",
        )
    else:
        favourite_foods = []
        st.caption("Select Year Group to see available foods.")
with _col_hobby:
    if _available_hobbies:
        favourite_hobbies = st.multiselect(
            "Favourite Hobby Objects",
            options=_available_hobbies,
            default=[],
            key="np_favourite_hobbies_picker",
            help="Only hobbies tagged on ready templates.",
        )
    else:
        favourite_hobbies = []
        st.caption("Select Year Group to see available hobbies.")

# ------------------------------------------------------------------------------
# Workbook & Picture Settings
# ------------------------------------------------------------------------------
st.divider()
col_ws1, col_ws2 = st.columns(2)
with col_ws1:
    # Every registered year group is listed. Unavailable grades stay visible
    # and are labelled so they cannot silently use another grade's content.
    _grade_display_options = ["Select Grade"] + [opt["label"] for opt in _grade_options]
    _grade_label = st.selectbox("Year Group*", _grade_display_options, key="np_grade_select")
    _selected_grade = _grade_by_label.get(_grade_label)
    _grade_id: str | None = _selected_grade["id"] if _selected_grade else None
    _grade_ready = bool(_selected_grade and _selected_grade["available"])
    grade = (_selected_grade["display_name"] if _selected_grade else _grade_label)
with col_ws2:
    num_questions = int(
        st.number_input(
            "Number of questions",
            min_value=1,
            max_value=50,
            value=6,
            step=1,
            key="np_num_questions_input",
        )
    )

# Load topics, foods, and hobbies only from the selected grade's own banks.
if _grade_ready and _grade_id:
    try:
        _all_topic_ids = list_topics(_grade_id)
        _available_foods = list_template_foods(_grade_id)
        _available_hobbies = list_template_hobbies(_grade_id)
    except (GradeNotFoundError, Exception):
        _all_topic_ids = []
else:
    _all_topic_ids = []

_topic_label_to_id = {topic_label(t): t for t in _all_topic_ids}
topics_for_grade = list(_topic_label_to_id.keys())
use_all_topics = False
selected_topic_labels: list[str] = []
selected_topics: list[str] = []

if _grade_id and not _grade_ready:
    st.error(
        f"**{grade}** — content not available yet. "
        "This year group does not have its own questions or prompts, "
        "so a workbook cannot be generated. Grade 1 content will not be used."
    )
elif _grade_ready and _grade_id and topics_for_grade:
    use_all_topics = st.checkbox("Use all topics", value=False, key="np_use_all_topics")
    selected_topic_labels = st.multiselect(
        "Topics",
        options=topics_for_grade,
        default=([] if not topics_for_grade else [topics_for_grade[0]]),
        key="np_topics_multiselect",
        disabled=use_all_topics,
    )
    if use_all_topics:
        selected_topics = list(_all_topic_ids)
        selected_topic_labels = topics_for_grade
    else:
        selected_topics = [_topic_label_to_id[lab] for lab in selected_topic_labels if lab in _topic_label_to_id]
elif _grade_ready and _grade_id and not topics_for_grade:
    st.info(
        "No ready question templates found for the selected grade. "
        "Add stems under `grades/{}/questions/primary/` to get started.".format(_grade_id)
    )

col_ps1, col_ps2 = st.columns(2)
with col_ps1:
    include_images = st.checkbox("Include illustrations", value=True, key="np_include_images")
with col_ps2:
    counting_ability = st.selectbox(
        "Biggest number to practise",
        [10, 20, 50],
        index=1,
        key="np_counting_ability",
    )

# ── Illustration Mode ────────────────────────────────────────────────────────
st.divider()
st.markdown("#### 🖼️ AI Personalised Illustrations")
use_ai_generate = True

if include_images:
    st.info(
        "🤖 **AI Generate Mode**: Uses your uploaded family photos as visual character references, "
        "generating a brand-new educational scene from scratch for each question. "
        "No face-cropping or template-swapping needed."
    )

if include_images and not (_image_generator_mod.API_KEY or "").strip():
    st.warning(
        "⚠️ `OPENROUTER_API_KEY` is not set. Add the key to `.env` and restart Streamlit."
    )

anything_else = st.text_area(
    "Anything else for the pictures? (optional)",
    placeholder="e.g., loves dinosaurs, Christmas setting",
    help="Extra notes kept with the workbook metadata.",
    key="np_anything_else",
)

# ------------------------------------------------------------------------------
# Family photo upload (shown in both AI Generate and Face Swap modes)
# ------------------------------------------------------------------------------
saved_face_paths: dict[str, str] = {}
if include_images:
    _expander_title = "🤖 Upload Family Photos (AI will use as character reference)"
    with st.expander(_expander_title, expanded=True):
        st.markdown(
            """
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
        """,
            unsafe_allow_html=True,
        )
        _caption = (
            "Upload clear photos for the child and any family members in the questions. "
            "The AI will use these as visual references to draw each character's face "
            "and appearance in the fresh generated scene. Child photo is required; "
            "upload the adult whose name appears in the questions."
        )
        st.caption(_caption)

        # Job-specific uploads directory
        if "job_id" not in st.session_state:
            st.session_state.job_id = generate_job_id()
        _current_job_id = st.session_state.job_id
        faces_dir = get_runtime_dir(_current_job_id, "uploads")
        faces_dir.mkdir(parents=True, exist_ok=True)

        face_map = {}
        family_roles = [
            ("user", "Child"),
            ("mother", "Mum"),
            ("father", "Dad"),
            ("grandmother", "Grandma"),
            ("grandfather", "Grandad"),
            ("uncle", "Uncle"),
            ("aunt", "Aunt"),
            ("brother", "Brother"),
            ("sister", "Sister"),
        ]
        fam_cols = st.columns(3)
        for i, (role_key, role_label) in enumerate(family_roles):
            with fam_cols[i % 3]:
                st.markdown(
                    f'<div class="face-upload-card"><div class="label">{role_label}</div></div>',
                    unsafe_allow_html=True,
                )
                uploaded = st.file_uploader(
                    role_label,
                    type=["jpg", "png", "jpeg", "webp", "heic", "heif", "bmp", "tiff", "tif", "gif"],
                    key=f"np_face_{role_key}",
                    label_visibility="collapsed",
                )
                if uploaded:
                    face_map[role_key] = uploaded
                    st.image(uploaded, width=70)
                    st.markdown(
                        f'<div class="uploaded">\u2713 {role_label} uploaded</div>',
                        unsafe_allow_html=True,
                    )

        for role, file in face_map.items():
            path = faces_dir / f"{role}_face.png"
            path.write_bytes(file.getbuffer())
            saved_face_paths[role] = str(path)

        # Drop face files left over from earlier runs.
        if face_map:
            for stale in faces_dir.glob("*_face.png"):
                if stale.stem.removesuffix("_face") not in face_map:
                    try:
                        stale.unlink()
                    except OSError:
                        pass

        # Upload quality warnings
        _small_uploads: list[str] = []
        for role, file in face_map.items():
            try:
                from PIL import Image
                photo = Image.open(saved_face_paths[role])
                w, h = photo.size
                if min(w, h) < 150:
                    label = dict(family_roles).get(role, role.title())
                    _small_uploads.append(f"{label} ({w}x{h}px)")
            except Exception:
                pass
        if _small_uploads:
            st.warning(
                "⚠️ Low-resolution photo(s) detected: **"
                + "**, **".join(_small_uploads)
                + "**. A closer, higher-resolution photo gives a better character likeness."
            )

        # Show which photos will be used
        if saved_face_paths:
            st.markdown("**These photos will be used:**")
            _role_labels = dict(family_roles)
            _cols = st.columns(min(5, len(saved_face_paths)))
            for i, (role, path) in enumerate(sorted(saved_face_paths.items())):
                with _cols[i % len(_cols)]:
                    st.image(path, width=84)
                    st.caption(f"{_role_labels.get(role, role.title())} \u00b7 {face_map[role].name}")

# Close the face-upload conditional block (opened above)
_SIBLING_PHOTO_ROLES = ("sibling", "brother", "sister")
has_child_photo = any(role in saved_face_paths for role in ("user", "child"))
has_sibling_photo = any(role in saved_face_paths for role in _SIBLING_PHOTO_ROLES)
has_mother_photo = "mother" in saved_face_paths
has_father_photo = "father" in saved_face_paths
available_adult_roles = {r for r in ADULT_ROLES if r in saved_face_paths}
if has_mother_photo:
    available_adult_roles.add("mother")
if has_father_photo:
    available_adult_roles.add("father")
if has_sibling_photo:
    available_adult_roles.update(
        role for role in _SIBLING_PHOTO_ROLES if role in saved_face_paths
    )
ready_all = (
    list_ready_stems(_grade_id, topics=selected_topics or None)
    if (_grade_ready and _grade_id and selected_topics)
    else []
)


def _stem_within_counting(stem: dict, max_n: int) -> bool:
    """Keep stems whose answer / object counts fit the practise range."""
    meta = stem.get("meta") or {}
    answer = meta.get("answer") or {}
    correct = str(answer.get("correct") or "").strip()
    nums = []
    if correct.isdigit():
        nums.append(int(correct))
    for g in meta.get("visual_groups") or []:
        try:
            nums.append(int(g.get("count") or 0))
        except (TypeError, ValueError):
            pass
        try:
            if g.get("circled_count") is not None:
                nums.append(int(g["circled_count"]))
        except (TypeError, ValueError):
            pass
    if not nums:
        return True
    return max(nums) <= int(max_n)


ready_counted = [s for s in ready_all if _stem_within_counting(s, counting_ability)]

# Both modes need the uploaded photos; filter eligible stems by available roles.
# (AI Generate uses photos as visual references; Face Swap pastes them directly.)
eligible = (
    stems_for_available_roles(
        ready_counted,
        available_adult_roles,
        has_child_photo=has_child_photo,
        has_sibling_photo=has_sibling_photo,
    )
    if has_child_photo
    else []
)

n_primary_ready = sum(1 for s in ready_counted if s.get("bank") == "primary")
n_fallback_ready = sum(1 for s in ready_counted if s.get("bank") == "fallback")
n_primary_elig = sum(1 for s in eligible if s.get("bank") == "primary")
matched_interests, _other_interests = partition_by_interests(
    eligible,
    favourite_foods=favourite_foods,
    favourite_hobbies=favourite_hobbies,
)

if use_ai_generate:
    st.info(
        f"**{len(ready_counted)}** ready templates (\u2264 {counting_ability}) in selected topics "
        f"(Primary **{n_primary_ready}** \u00b7 Fallback **{n_fallback_ready}**) \u00b7 "
        f"**{len(eligible)}** usable with your photos \u00b7 "
        f"**{len(matched_interests)}** match your food/hobby picks"
    )
else:
    st.info(
        f"**{len(ready_counted)}** ready templates (\u2264 {counting_ability}) in selected topics "
        f"(Primary **{n_primary_ready}** \u00b7 Fallback **{n_fallback_ready}**) \u00b7 "
        f"**{len(eligible)}** usable with your uploaded faces "
        f"(Primary **{n_primary_elig}**) "
        f"({', '.join(ROLE_DISPLAY.get(r, r) for r in sorted(available_adult_roles)) or 'child-only OK'}) \u00b7 "
        f"**{len(matched_interests)}** match your food/hobby picks"
    )
if (favourite_foods or favourite_hobbies) and matched_interests:
    if len(matched_interests) < int(num_questions):
        st.warning(
            f"Only **{len(matched_interests)}** ready stem(s) match your favourites "
            f"with the current topics — the workbook will have at most that many "
            f"questions (won't fill with unrelated foods like cupcakes)."
        )
elif favourite_foods or favourite_hobbies:
    st.warning(
        "No ready stems match your food/hobby picks with the current topics. "
        "Pick different favourites or clear favourites to use any ready stem."
    )

# ------------------------------------------------------------------------------
# Generate
# ------------------------------------------------------------------------------
st.divider()
if st.button("📝 Generate Personalised Workbook", type="primary"):
    if not student_name.strip():
        st.warning("⚠️ Please enter the student's name.")
    elif gender == "Select":
        st.warning("⚠️ Please select the student's gender.")
    elif not _grade_id:
        st.warning("⚠️ Please select a year group.")
    elif not _grade_ready:
        st.error(
            f"**{grade}** — content not available yet. "
            "Workbook generation is blocked so this year group cannot use another grade's questions or prompts."
        )
    elif not selected_topics:
        st.warning("⚠️ Please select at least one topic (or turn on Use all topics).")
    # ── Photo validations (same requirements for both modes) ────────────────
    elif include_images and "user" not in saved_face_paths:
        _photo_noun = "reference photo" if use_ai_generate else "photo"
        st.warning(f"⚠️ Please upload the child's {_photo_noun} (required for illustrations).")
    elif include_images and not available_adult_roles and not any(
        not (s.get("template_adult_role") or "").strip() for s in eligible
    ):
        _hint = "as a visual reference" if use_ai_generate else "to appear in the template"
        st.warning(
            f"⚠️ Upload at least one adult photo (Mum/Dad/Grandma/Grandad) {_hint}, "
            "or use topics with child-only Hamdan templates."
        )
    elif include_images and not eligible:
        _mode_hint = "AI generate" if use_ai_generate else "face-swap"
        st.warning(
            f"⚠️ No ready templates match your uploaded photos, topics, and number range "
            f"({_mode_hint} mode). Add more stems or upload the matching adult photo."
        )
    elif include_images and (favourite_foods or favourite_hobbies) and not matched_interests:
        st.warning(
            "⚠️ No ready templates match your favourite foods/hobbies with the "
            "uploaded photos. Clear favourites or upload matching adult photos."
        )
    # ── Text-only (no images) ──────────────────────────────────────────────
    elif not include_images and not ready_counted:
        st.warning("⚠️ No ready templates for the selected topics / number range.")
    else:
        # Assign a unique job ID for this workbook session
        _job_id = st.session_state.get("job_id") or generate_job_id()
        st.session_state.job_id = _job_id
        st.session_state.pipeline = {
            "phase": "build",
            "job_id": _job_id,
            "student_name": student_name.strip(),
            "gender": gender,
            "child_age": int(child_age),
            "grade": grade,
            "grade_id": _grade_id,
            "family_names": {k: v for k, v in family_names.items() if v},
            "favourite_foods": list(favourite_foods),
            "favourite_hobbies": list(favourite_hobbies),
            "selected_topics": selected_topics,
            "num_questions": int(num_questions),
            "include_images": bool(include_images),
            "use_ai_generate": bool(include_images),
            "counting_ability": int(counting_ability),
            "fav_color": (fav_color or "").strip(),
            "anything_else": (anything_else or "").strip(),
            "saved_face_paths": saved_face_paths,
            "available_adult_roles": sorted(available_adult_roles),
        }
        # Write job metadata
        write_job_metadata(_job_id, {
            "workbook_id": _job_id,
            "created_at": datetime.now().isoformat(),
            "student_name": student_name.strip(),
            "grade_id": _grade_id,
            "grade_display": grade,
            "selected_topics": selected_topics,
            "num_questions": int(num_questions),
            "ai_image_model": _image_generator_mod.IMAGE_GEN_MODEL,
            "generation_status": "in_progress",
        })
        st.rerun()

# ══════════════════════════════════════════════════════════════════
# PIPELINE
# ══════════════════════════════════════════════════════════════════
pipeline = st.session_state.get("pipeline")
if pipeline is None:
    st.stop()

phase = pipeline["phase"]
_grade_id_pipeline = (pipeline.get("grade_id") or "").strip()
_job_id_pipeline = (pipeline.get("job_id") or "").strip()
if phase in ("build", "pdf"):
    if not _grade_id_pipeline:
        st.error(
            "This workbook has no grade_id. Generation stopped so another grade's content is not used."
        )
        st.session_state.pipeline = None
        st.stop()
    if not is_grade_available(_grade_id_pipeline):
        st.error(
            f"**{_grade_id_pipeline}** — content not available yet. "
            "Generation stopped. Grade 1 questions and prompts will not be used."
        )
        st.session_state.pipeline = None
        st.stop()
    if not _job_id_pipeline:
        st.error(
            "This workbook has no job_id. Generation stopped so files are not written into a shared folder."
        )
        st.session_state.pipeline = None
        st.stop()

if phase == "build":
    faces = pipeline["saved_face_paths"]
    adult_roles = set(pipeline["available_adult_roles"])
    pool = list_ready_stems(_grade_id_pipeline, topics=pipeline["selected_topics"])
    pool = [s for s in pool if _stem_within_counting(s, pipeline["counting_ability"])]

    # Filter stems whose cast matches the uploaded photos.
    # In AI Generate mode, the model draws the scene fresh from reference photos + prompt.
    if pipeline["include_images"]:
        pool = stems_for_available_roles(
            pool,
            adult_roles,
            has_child_photo=("user" in faces or "child" in faces),
            has_sibling_photo=any(
                r in faces for r in ("sibling", "brother", "sister")
            ),
            require_personalizable=False,
        )
    n_wanted = int(pipeline["num_questions"])

    # Gender-match: a face swap replaces only the face, not the body / clothes.
    # Prefer templates whose template child matches the uploaded child's gender.
    same_gender, other_gender = partition_by_child_gender(pool, pipeline.get("gender", ""))
    if same_gender:
        if len(same_gender) >= n_wanted:
            pool = same_gender
        else:
            pool = same_gender + other_gender
            st.caption(
                f"Only **{len(same_gender)}** scene(s) show a "
                f"{pipeline.get('gender', 'child').lower()} with your topics — "
                "the rest may show a child of a different gender."
            )

    # Prefer stems that cast the uploaded adults; top up with child-only scenes.
    uses_adult, child_only = partition_by_adult_roles(pool, adult_roles)
    chosen = select_stems(
        uses_adult if len(uses_adult) >= n_wanted else pool,
        n_wanted,
        favourite_foods=pipeline.get("favourite_foods") or [],
        favourite_hobbies=pipeline.get("favourite_hobbies") or [],
        bank_balance=True,
    )
    if adult_roles and uses_adult and len(uses_adult) < n_wanted:
        st.caption(
            f"Only **{len(uses_adult)}** scene(s) cast "
            f"{', '.join(ROLE_DISPLAY.get(r, r) for r in sorted(adult_roles))} "
            f"with your topics — the rest will be child-only scenes."
        )
    if not chosen:
        st.error("No stems available to build the workbook.")
        st.session_state.pipeline = None
        st.stop()

    n_h = sum(1 for s in chosen if s.get("bank") == "primary")
    st.caption(
        f"Selected **{len(chosen)}** stems \u00b7 Primary bank **{n_h}** \u00b7 "
        f"Fallback **{len(chosen) - n_h}** \u00b7 Mode: **AI Generate**"
    )
    items: list = []
    skipped: list = []
    try:
        if pipeline.get("include_images"):
            # ── AI Generate: prompt.md + question + photos as visual reference ───
            progress = st.progress(0, text="Generating AI illustrations…")
            status = st.empty()

            def _on_stem_gen(i: int, total: int, stem_id: str) -> None:
                n_ref = len(pipeline.get("saved_face_paths") or {})
                status.info(
                    f"Generating image {i}/{total}: `{stem_id}` "
                    f"(AI from scratch with {n_ref} reference photo(s))…"
                )
                progress.progress(min(i / max(total, 1), 1.0))

            items, skipped = build_workbook_items_ai_generated(
                chosen,
                user_name=pipeline["student_name"],
                family_names=pipeline["family_names"],
                face_paths=pipeline.get("saved_face_paths") or {},
                child_gender=pipeline.get("gender", ""),
                out_dir=get_runtime_dir(_job_id_pipeline, "generated_images"),
                on_progress=_on_stem_gen,
                grade_id=_grade_id_pipeline,
                fav_color=pipeline.get("fav_color") or "",
                favourite_foods=pipeline.get("favourite_foods") or [],
                favourite_hobbies=pipeline.get("favourite_hobbies") or [],
            )
            progress.progress(1.0, text="Done")
            status.empty()
            if skipped:
                st.warning(
                    f"**{len(skipped)}** stem(s) skipped due to errors — "
                    f"PDF will include **{len(items)}** question(s) generated successfully."
                )
                with st.expander("Skipped stems", expanded=False):
                    for s in skipped:
                        st.markdown(f"- `{s['stem_id']}`: {s['error']}")
            pipeline["skipped_stems"] = skipped
        else:
            # Text-only: still fill names + MCQ from meta
            pipeline["skipped_stems"] = []
            for stem in chosen:
                role = stem["template_adult_role"]
                q_text = fill_question_text(
                    stem["question_template"],
                    user_name=pipeline["student_name"],
                    adult_role=role or "mother",
                    family_names=pipeline["family_names"],
                    child_gender=pipeline.get("gender", ""),
                )
                items.append(
                    {
                        "stem_id": stem["stem_id"],
                        "topic": stem["topic"],
                        "topic_label": topic_label(stem["topic"]),
                        "adult_role": role,
                        "adult_name": display_name_for_role(
                            role, pipeline["family_names"]
                        )
                        if role
                        else "",
                        "question": q_text,
                        "bank": stem.get("bank") or "",
                        "image_path": None,
                        "options": mcq_from_meta(stem["meta"], question=q_text),
                        "correct": str(
                            (stem["meta"].get("answer") or {}).get("correct") or ""
                        ),
                    }
                )
    except Exception as exc:
        st.error(f"Personalisation failed: {exc}")
        st.info(
            "If OpenRouter was overloaded, wait a minute and click **Generate** again. "
            "The app will not put soft-paste sticker faces into the PDF."
        )
        st.session_state.pipeline = None
        st.stop()

    if not items:
        st.error("No questions were personalised successfully.")
        st.session_state.pipeline = None
        st.stop()

    # ── Fill empty MCQ options via AI ────────────────────────────────────────
    # If a question has no options, AI checks the question and generates
    # exactly 1 true answer and 3 wrong distractors.
    def _is_mcq_incomplete(it: dict) -> bool:
        opts_val = it.get("options")
        if not opts_val:
            return True
        if isinstance(opts_val, dict):
            raw = opts_val.get("options") or []
        elif isinstance(opts_val, (list, tuple)):
            raw = opts_val
        else:
            return True
        valid = [str(o).strip() for o in raw if str(o).strip() and str(o).strip() != "-"]
        return len(valid) < 2

    empty_mcq_items = [it for it in items if _is_mcq_incomplete(it)]
    if empty_mcq_items:
        from stem_pipeline import generate_mcq_ai
        with st.spinner(f"🧠 Checking questions & generating MCQ options via AI ({len(empty_mcq_items)} question(s))…"):
            for it in empty_mcq_items:
                ai_mcq = generate_mcq_ai(it["question"])
                if ai_mcq and ai_mcq.get("options"):
                    it["options"] = ai_mcq
                    it["correct"] = ai_mcq.get("correct_answer", "")

    pipeline["items"] = items
    pipeline["phase"] = "pdf"
    st.rerun()

elif phase == "pdf":
    items = pipeline["items"]

    # Safety check: ensure every question has 4 valid options (1 true + 3 wrong)
    def _is_mcq_incomplete(it: dict) -> bool:
        opts_val = it.get("options")
        if not opts_val:
            return True
        if isinstance(opts_val, dict):
            raw = opts_val.get("options") or []
        elif isinstance(opts_val, (list, tuple)):
            raw = opts_val
        else:
            return True
        valid = [str(o).strip() for o in raw if str(o).strip() and str(o).strip() != "-"]
        return len(valid) < 2

    for it in items:
        if _is_mcq_incomplete(it):
            from stem_pipeline import generate_mcq_ai
            ai_mcq = generate_mcq_ai(it["question"])
            if ai_mcq and ai_mcq.get("options"):
                it["options"] = ai_mcq
                it["correct"] = ai_mcq.get("correct_answer", "")

    questions = [f"{i}. {it['question']}" for i, it in enumerate(items, start=1)]
    image_paths = (
        [it.get("image_path") for it in items] if pipeline.get("include_images") else None
    )
    question_topics = [it["topic_label"] for it in items]
    question_adults = [it["adult_name"] for it in items]
    question_options = [it["options"] for it in items]
    topic_header = ", ".join(sorted({it["topic_label"] for it in items}))

    foods = pipeline.get("favourite_foods") or []
    hobbies = pipeline.get("favourite_hobbies") or []
    extras = []
    if foods:
        extras.append("Foods: " + ", ".join(foods))
    if hobbies:
        extras.append("Hobbies: " + ", ".join(hobbies))
    if pipeline.get("anything_else"):
        extras.append(pipeline["anything_else"])
    picture_theme = " · ".join(extras)

    # ── AI-generated front cover (always, regardless of illustrations toggle) ──
    # Every PDF gets a personalised cover as page 1.
    # If cover generation fails we show a warning and continue without it.
    cover_image_path: str | None = None
    if (_front_cover_mod.OPENROUTER_API_KEY or "").strip():
        cover_category = topic_header or pipeline.get("grade") or _grade_id_pipeline
        _cover_topics = pipeline.get("selected_topics") or []
        _cover_topic_labels = [topic_label(t) for t in _cover_topics]
        _cover_catalog = [
            topic_label(t)
            for t in get_grade_topics(_grade_id_pipeline)
            if "mix" not in str(t).lower()
        ]
        with st.spinner("🎨 Generating personalised front cover…"):
            try:
                cover_path = generate_front_cover(
                    child_name=pipeline["student_name"],
                    category=cover_category,
                    face_paths=pipeline.get("saved_face_paths") or {},
                    family_names=pipeline.get("family_names") or {},
                    subject="MATH",
                    selected_topics=_cover_topic_labels,
                    all_available_topics=_cover_catalog,
                    grade=pipeline.get("grade") or "",
                    grade_id=_grade_id_pipeline,
                    job_id=_job_id_pipeline,
                    theme_color=pipeline.get("fav_color") or "",
                )
                cover_image_path = str(cover_path)
                st.success("✅ Front cover generated!")
            except FrontCoverError as fc_exc:
                st.warning(
                    f"⚠️ Front cover generation failed — workbook will have no cover page. "
                    f"Reason: {fc_exc}"
                )
            except Exception as fc_exc:
                st.warning(
                    f"⚠️ Front cover generation failed — workbook will have no cover page. "
                    f"Reason: {fc_exc}"
                )
    else:
        st.info(
            "ℹ️ OPENROUTER_API_KEY not set — front cover skipped. "
            "Add the key to .env and restart to get a personalised cover."
        )

    with st.spinner("📄 Creating PDF workbook…"):
        pdf_bytes = generate_pdf(
            pipeline["student_name"],
            pipeline.get("grade") or _grade_id_pipeline,
            topic_header,
            questions,
            image_paths,
            question_topics=question_topics,
            favourite_colour=pipeline.get("fav_color", ""),
            picture_theme=picture_theme,
            workbook_title=f"{pipeline['student_name']}'s Maths Practice Book",
            workbook_subtitle=f"Personalised {pipeline.get('grade') or _grade_id_pipeline} practice · template bank",
            question_adults=question_adults,
            question_options=question_options,
            cover_image_path=cover_image_path,
            grade_id=_grade_id_pipeline,
        )

    # Save PDF into this workbook's own job folder.
    _pdf_dir = get_runtime_dir(_job_id_pipeline, "generated_pdfs")
    _pdf_filename = create_safe_filename(pipeline["student_name"])
    _pdf_path = _pdf_dir / _pdf_filename
    _pdf_path.write_bytes(pdf_bytes)
    write_job_metadata(_job_id_pipeline, {
        "generation_status": "complete",
        "pdf_path": str(_pdf_path),
        "pdf_filename": _pdf_filename,
        "total_questions": len(items),
        "completed_at": datetime.now().isoformat(),
    })

    pipeline["pdf_bytes"] = pdf_bytes
    pipeline["questions"] = questions
    pipeline["phase"] = "complete"
    st.rerun()

elif phase == "complete":
    filename = create_safe_filename(pipeline["student_name"])
    skipped = pipeline.get("skipped_stems") or []
    if skipped:
        st.success(
            f"🎉 Workbook ready with **{len(pipeline.get('items') or [])}** questions "
            f"({len(skipped)} stem(s) skipped)."
        )
    else:
        st.success("🎉 Personalised Maths Workbook ready!")

    items = pipeline.get("items") or []
    if skipped:
        with st.expander("Skipped stems", expanded=False):
            for s in skipped:
                st.markdown(f"- `{s['stem_id']}`: {s['error']}")
    if items:
        with st.expander("Questions in this workbook", expanded=False):
            for it in items:
                st.markdown(
                    f"**{it['topic_label']}** · {it['adult_name']} · "
                    f"`{it['stem_id']}` → answer **{it['correct']}**"
                )
                st.write(it["question"])
                img = it.get("image_path")
                if img and Path(img).is_file():
                    st.image(img, width=280)
                st.divider()

    pdf_b64 = base64.b64encode(pipeline["pdf_bytes"]).decode("utf-8")
    col_dl, col_open = st.columns(2)
    with col_dl:
        st.download_button(
            "📥 Download PDF",
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

    if st.button("🔄 Start Over"):
        st.session_state.pipeline = None
        st.rerun()
