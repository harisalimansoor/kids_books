"""
new_pipeline/newapp.py
─────────────────────────────────────────────────────────────────────────────
Streamlit UI for the bank-first Grade 1 workbook pipeline.

Form fields: child name, age, gender, family, favourite foods/hobbies, grade, topics, face uploads.
Generation uses pre-built role-locked question templates — not kitchen RAG.
"""

from __future__ import annotations

import base64
import sys
from io import BytesIO
from pathlib import Path

import streamlit as st

PIPELINE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

from pdf_generator import generate_pdf  # noqa: E402
from utils import create_safe_filename  # noqa: E402

# Reload stem_pipeline so Streamlit picks up new helpers after file edits
import importlib  # noqa: E402
import stem_pipeline as _stem_pipeline  # noqa: E402

_stem_pipeline = importlib.reload(_stem_pipeline)
ADULT_ROLES = _stem_pipeline.ADULT_ROLES
ROLE_DISPLAY = _stem_pipeline.ROLE_DISPLAY
build_workbook_items = _stem_pipeline.build_workbook_items
display_name_for_role = _stem_pipeline.display_name_for_role
fill_question_text = _stem_pipeline.fill_question_text
list_ready_stems = _stem_pipeline.list_ready_stems
list_template_foods = _stem_pipeline.list_template_foods
list_template_hobbies = _stem_pipeline.list_template_hobbies
list_topics = _stem_pipeline.list_topics
mcq_from_meta = _stem_pipeline.mcq_from_meta
partition_by_interests = _stem_pipeline.partition_by_interests
select_stems = _stem_pipeline.select_stems
stems_for_available_roles = _stem_pipeline.stems_for_available_roles
topic_label = _stem_pipeline.topic_label

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
    "Create a personalised Year 1 maths workbook with fun illustrations! "
    "Tell us about your child — favourite colour, family, and "
    "favourite foods & hobbies — and we'll make a worksheet from "
    "**pre-built question templates**."
)
st.caption(
    "Illustrations use the kitchen-style pipeline: YuNet face paste → "
    "AI seamless blend (adult then child) → object-count lock. "
    "Requires `OPENROUTER_API_KEY` in `.env`."
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

# --- Favourite Foods & Hobbies (only options that exist on ready templates) ---
st.divider()
st.markdown("#### 🍳 Favourite Foods & 🎨 Hobbies")
st.caption(
    "Options come from ready templates in **grade_1_hamdan** (+ grade_1). "
    "When you pick any, the workbook prefers matching stems "
    "(e.g. Apples → apple questions; Stickers → sticker questions). "
    "Leave empty to use any ready stem."
)
_available_foods = list_template_foods()
_available_hobbies = list_template_hobbies()
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
        st.caption("No food-tagged templates yet.")
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
        st.caption("No hobby-tagged templates yet.")

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

_all_topic_ids = list_topics()
_topic_label_to_id = {topic_label(t): t for t in _all_topic_ids}
topics_for_grade = list(_topic_label_to_id.keys())
use_all_topics = False
selected_topic_labels: list[str] = []
selected_topics: list[str] = []

if grade == "Grade 1" and topics_for_grade:
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
elif grade == "Grade 1" and not topics_for_grade:
    st.info(
        "No ready template topics found. Add stems under "
        "`new_pipeline/question_templates/grade_1_hamdan/` "
        "(or `grade_1/`)."
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

st.markdown("#### 🎨 Illustration Style")
style_choice = st.radio(
    "Style for the worksheet illustration",
    options=["Soft cartoon + seamless blend", "Photoreal seamless blend"],
    index=1,
    horizontal=True,
    key="np_style_choice",
    help=(
        "Photoreal is the default (same as the apples test). "
        "Both modes paste faces into YuNet boxes then AI-blend "
        "(adult first, then child) so edges are not stickers."
    ),
)
soft_cartoon = style_choice.startswith("Soft cartoon")
run_ai_finish = True  # always AI-blend when illustrations are on

# Warn early if API key missing (blend will fall back to paste-only)
from swapping_engine import personalize as _pers_check

importlib.reload(_pers_check)
if include_images and not (_pers_check.API_KEY or "").strip():
    st.warning(
        "⚠️ `OPENROUTER_API_KEY` is not set — illustrations will paste faces "
        "without AI blend (sticker look). Add the key to `.env` and restart Streamlit."
    )

anything_else = st.text_area(
    "Anything else for the pictures? (optional)",
    placeholder="e.g., loves dinosaurs, Christmas setting",
    help="Extra notes kept with the workbook metadata.",
    key="np_anything_else",
)

# ------------------------------------------------------------------------------
# Face upload section
# ------------------------------------------------------------------------------
saved_face_paths: dict[str, str] = {}
with st.expander(
    "Upload Family Photos (for face swapping)",
    expanded=bool(include_images),
):
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
    st.caption(
        "Upload clear face photos. Child + the matching adult (Mum/Dad/…) "
        "are required for each template role you want. "
        "Pipeline: soft-paste into annotated boxes → AI blend adult → AI blend child."
    )

    faces_dir = REPO_ROOT / "personalised_faces"
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
                type=["jpg", "png", "jpeg"],
                key=f"np_face_{role_key}",
                label_visibility="collapsed",
            )
            if uploaded:
                face_map[role_key] = uploaded
                st.image(uploaded, width=70)
                st.markdown(
                    f'<div class="uploaded">✓ {role_label} uploaded</div>',
                    unsafe_allow_html=True,
                )

    for role, file in face_map.items():
        path = faces_dir / f"{role}_face.png"
        path.write_bytes(file.getbuffer())
        saved_face_paths[role] = str(path)

available_adult_roles = {r for r in ADULT_ROLES if r in saved_face_paths}
has_sibling_photo = any(r in saved_face_paths for r in ("sibling", "brother", "sister"))
ready_all = list_ready_stems(topics=selected_topics or None) if selected_topics else []


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
eligible = (
    stems_for_available_roles(
        ready_counted,
        available_adult_roles,
        has_child_photo=("user" in saved_face_paths),
        has_sibling_photo=has_sibling_photo,
        family_names={k: v for k, v in family_names.items() if v},
    )
    if "user" in saved_face_paths
    else []
)
n_hamdan_ready = sum(1 for s in ready_counted if s.get("bank") == "grade_1_hamdan")
n_grade1_ready = sum(1 for s in ready_counted if s.get("bank") == "grade_1")
n_hamdan_elig = sum(1 for s in eligible if s.get("bank") == "grade_1_hamdan")
matched_interests, _other_interests = partition_by_interests(
    eligible,
    favourite_foods=favourite_foods,
    favourite_hobbies=favourite_hobbies,
)

st.info(
    f"**{len(ready_counted)}** ready templates (≤ {counting_ability}) in selected topics "
    f"(Hamdan **{n_hamdan_ready}** · classic **{n_grade1_ready}**) · "
    f"**{len(eligible)}** usable with your uploaded faces "
    f"(Hamdan **{n_hamdan_elig}**) "
    f"({', '.join(ROLE_DISPLAY.get(r, r) for r in sorted(available_adult_roles)) or 'child-only OK'}) · "
    f"**{len(matched_interests)}** match your food/hobby picks"
)
if (favourite_foods or favourite_hobbies) and matched_interests:
    if len(matched_interests) < int(num_questions):
        st.warning(
            f"Only **{len(matched_interests)}** ready stem(s) match your favourites "
            f"with the current faces/topics — the workbook will have at most that many "
            f"questions (won't fill with unrelated foods like cupcakes)."
        )
elif favourite_foods or favourite_hobbies:
    st.warning(
        "No ready stems match your food/hobby picks with the current faces/topics. "
        "Pick different favourites, upload the matching adult photo, or clear favourites."
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
    elif _grade_label == "Select Year" or grade != "Grade 1":
        st.warning("⚠️ Please select a year group.")
    elif not selected_topics:
        st.warning("⚠️ Please select at least one topic (or turn on Use all topics).")
    elif include_images and "user" not in saved_face_paths:
        st.warning("⚠️ Please upload the child's photo (needed for illustrations).")
    elif include_images and not available_adult_roles and not any(
        not (s.get("template_adult_role") or "").strip() for s in eligible
    ):
        st.warning("⚠️ Upload at least one adult photo (Mum/Dad/Grandma/Grandad), or use topics with child-only Hamdan templates.")
    elif include_images and not eligible:
        st.warning(
            "⚠️ No ready templates match your uploaded adults, topics, and number range. "
            "Add more stems or upload the matching adult photo."
        )
    elif include_images and (favourite_foods or favourite_hobbies) and not matched_interests:
        st.warning(
            "⚠️ No ready templates match your favourite foods/hobbies with the "
            "uploaded faces. Clear favourites or pick ones that have matching stems."
        )
    elif not include_images and not ready_counted:
        st.warning("⚠️ No ready templates for the selected topics / number range.")
    else:
        st.session_state.pipeline = {
            "phase": "build",
            "student_name": student_name.strip(),
            "gender": gender,
            "child_age": int(child_age),
            "grade": grade,
            "family_names": {k: v for k, v in family_names.items() if v},
            "favourite_foods": list(favourite_foods),
            "favourite_hobbies": list(favourite_hobbies),
            "selected_topics": selected_topics,
            "num_questions": int(num_questions),
            "include_images": bool(include_images),
            "counting_ability": int(counting_ability),
            "run_ai_finish": bool(run_ai_finish and include_images),
            "soft_cartoon": bool(soft_cartoon),
            "fav_color": (fav_color or "").strip(),
            "anything_else": (anything_else or "").strip(),
            "saved_face_paths": saved_face_paths,
            "available_adult_roles": sorted(available_adult_roles),
        }
        st.rerun()

# ══════════════════════════════════════════════════════════════════
# PIPELINE
# ══════════════════════════════════════════════════════════════════
pipeline = st.session_state.get("pipeline")
if pipeline is None:
    st.stop()

phase = pipeline["phase"]

if phase == "build":
    faces = pipeline["saved_face_paths"]
    adult_roles = set(pipeline["available_adult_roles"])
    pool = list_ready_stems(topics=pipeline["selected_topics"])
    pool = [s for s in pool if _stem_within_counting(s, pipeline["counting_ability"])]
    if pipeline["include_images"]:
        pool = stems_for_available_roles(
            pool,
            adult_roles,
            has_child_photo=("user" in faces or "child" in faces),
            has_sibling_photo=any(
                r in faces for r in ("sibling", "brother", "sister")
            ),
            family_names=pipeline.get("family_names") or {},
            require_personalizable=True,
        )
    chosen = select_stems(
        pool,
        pipeline["num_questions"],
        favourite_foods=pipeline.get("favourite_foods") or [],
        favourite_hobbies=pipeline.get("favourite_hobbies") or [],
        bank_balance=True,
    )
    chosen_ids = {s["stem_id"] for s in chosen}
    backup_pool = [s for s in pool if s["stem_id"] not in chosen_ids]
    backup_stems = select_stems(
        backup_pool,
        max(pipeline["num_questions"] * 3, 6),
        favourite_foods=pipeline.get("favourite_foods") or [],
        favourite_hobbies=pipeline.get("favourite_hobbies") or [],
        strict_interests=False,
        bank_balance=True,
    )
    if not chosen:
        st.error("No stems available to build the workbook.")
        st.session_state.pipeline = None
        st.stop()

    n_h = sum(1 for s in chosen if s.get("bank") == "grade_1_hamdan")
    st.caption(
        f"Selected **{len(chosen)}** stems · Hamdan **{n_h}** · "
        f"classic grade_1 **{len(chosen) - n_h}** (~50/50 when both banks match)."
    )
    items: list = []
    skipped: list = []
    try:
        if pipeline["include_images"]:
            progress = st.progress(0, text="Personalising illustrations…")
            status = st.empty()

            def _on_stem(i: int, total: int, stem_id: str) -> None:
                status.info(f"Blending faces {i}/{total}: `{stem_id}` (adult → child AI)…")
                progress.progress(min(i / max(total, 1), 1.0))

            items, skipped = build_workbook_items(
                chosen,
                user_name=pipeline["student_name"],
                family_names=pipeline["family_names"],
                face_paths=faces,
                run_ai_finish=pipeline["run_ai_finish"],
                soft_cartoon=pipeline.get("soft_cartoon", False),
                child_gender=pipeline.get("gender", ""),
                out_dir=PIPELINE_ROOT / "_runtime" / "personalized",
                on_progress=_on_stem,
                target_count=pipeline["num_questions"],
                backup_stems=backup_stems,
            )
            progress.progress(1.0, text="Done")
            status.empty()
            if skipped:
                short = pipeline["num_questions"] - len(items)
                if short > 0:
                    st.warning(
                        f"**{len(skipped)}** stem(s) failed and **{short}** backup(s) "
                        f"could not fill the gap — PDF has **{len(items)}** of "
                        f"**{pipeline['num_questions']}** requested."
                    )
                else:
                    st.info(
                        f"**{len(skipped)}** stem(s) were replaced by backups — "
                        f"PDF has all **{len(items)}** questions."
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
                        "question": fill_question_text(
                            stem["question_template"],
                            user_name=pipeline["student_name"],
                            adult_role=role or "mother",
                            family_names=pipeline["family_names"],
                            child_gender=pipeline.get("gender", ""),
                        ),
                        "bank": stem.get("bank") or "",
                        "image_path": None,
                        "options": mcq_from_meta(stem["meta"]),
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

    pipeline["items"] = items
    pipeline["phase"] = "pdf"
    st.rerun()

elif phase == "pdf":
    items = pipeline["items"]
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

    with st.spinner("📄 Creating PDF workbook…"):
        pdf_bytes = generate_pdf(
            pipeline["student_name"],
            pipeline.get("grade") or "Grade 1",
            topic_header,
            questions,
            image_paths,
            question_topics=question_topics,
            favourite_colour=pipeline.get("fav_color", ""),
            picture_theme=picture_theme,
            workbook_title=f"{pipeline['student_name']}'s Maths Practice Book",
            workbook_subtitle="Personalised Year 1 practice · template bank",
            question_adults=question_adults,
            question_options=question_options,
        )

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
