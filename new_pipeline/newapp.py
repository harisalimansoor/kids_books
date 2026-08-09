"""
new_pipeline/newapp.py
─────────────────────────────────────────────────────────────────────────────
Streamlit UI for the bank-first Grade 1 workbook pipeline.

Strategy:
  1. Select ready role-locked stems from question_templates/
  2. Only use stems whose adult role has an uploaded face
  3. Fill {user_name}/{mother_name}/… from the family profile
  4. Paste faces + optional soft-cartoon finish (identity-locked)
  5. MCQ + answer key from meta.json (no LLM re-guess)
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

from stem_pipeline import (  # noqa: E402
    ADULT_ROLES,
    ROLE_DISPLAY,
    build_workbook_items,
    list_ready_stems,
    list_topics,
    select_stems,
    stems_for_available_roles,
    topic_label,
)

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
    "Create a personalised Year 1 maths workbook from **pre-built question "
    "templates**. We swap in your family's faces and names — maths answers "
    "come from the template, not a new AI guess."
)

if "pipeline" not in st.session_state:
    st.session_state.pipeline = None

# ------------------------------------------------------------------------------
# Child
# ------------------------------------------------------------------------------
st.subheader("👤 About Your Child")
col_name, col_gen, col_age = st.columns(3)
with col_name:
    student_name = st.text_input("Name*", placeholder="e.g., Oliver")
with col_gen:
    gender = st.selectbox("Gender*", ["Select", "Boy", "Girl", "Other"])
with col_age:
    child_age = st.number_input("Age", min_value=4, max_value=8, value=6)

# ------------------------------------------------------------------------------
# Family names (fill placeholders)
# ------------------------------------------------------------------------------
st.divider()
st.subheader("👨‍👩‍👧 Family Names")
st.caption("Used in questions like “Mum has 3 apples…”. Leave blank to use Mum/Dad/Grandma/Grandad.")
name_cols = st.columns(2)
family_names: dict[str, str] = {}
_name_fields = [
    ("mother", "Mum's name"),
    ("father", "Dad's name"),
    ("grandmother", "Grandma's name"),
    ("grandfather", "Grandad's name"),
]
for i, (role, label) in enumerate(_name_fields):
    with name_cols[i % 2]:
        family_names[role] = st.text_input(label, key=f"name_{role}", placeholder=ROLE_DISPLAY[role])

# ------------------------------------------------------------------------------
# Topics + count
# ------------------------------------------------------------------------------
st.divider()
st.subheader("📖 Topics")
_all_topics = list_topics()
_topic_labels = {topic_label(t): t for t in _all_topics}
selected_labels = st.multiselect(
    "Topics to include*",
    options=list(_topic_labels.keys()),
    default=list(_topic_labels.keys()) if _topic_labels else [],
)
selected_topics = [_topic_labels[lab] for lab in selected_labels]

num_questions = st.slider("Number of questions", min_value=1, max_value=10, value=min(3, 10))

# ------------------------------------------------------------------------------
# Style
# ------------------------------------------------------------------------------
st.divider()
st.markdown("#### 🎨 Illustration finish")
style_choice = st.radio(
    "After face paste",
    options=["Soft cartoon (identity-locked)", "Photo paste only"],
    index=0,
    horizontal=True,
)
run_ai_finish = style_choice.startswith("Soft cartoon")

fav_color = st.text_input("Favourite colour (PDF accent)", placeholder="e.g., blue")

# ------------------------------------------------------------------------------
# Faces
# ------------------------------------------------------------------------------
st.divider()
faces_dir = REPO_ROOT / "personalised_faces"
faces_dir.mkdir(parents=True, exist_ok=True)

saved_face_paths: dict[str, str] = {}
with st.expander("Upload Family Photos (required for templates)", expanded=True):
    st.caption(
        "Upload the **child** plus each adult whose templates you want. "
        "Mother-only stems need Mum’s photo; father stems need Dad’s photo."
    )
    face_roles = [("user", "Child*")] + [(r, ROLE_DISPLAY[r]) for r in ADULT_ROLES]
    fam_cols = st.columns(3)
    uploads = {}
    for i, (role_key, role_label) in enumerate(face_roles):
        with fam_cols[i % 3]:
            uploaded = st.file_uploader(
                role_label,
                type=["jpg", "png", "jpeg"],
                key=f"face_{role_key}",
            )
            if uploaded:
                uploads[role_key] = uploaded
                st.image(uploaded, width=70)

    for role, file in uploads.items():
        path = faces_dir / f"{role}_face.png"
        path.write_bytes(file.getbuffer())
        saved_face_paths[role] = str(path)

available_adult_roles = {r for r in ADULT_ROLES if r in saved_face_paths}
ready_all = list_ready_stems(topics=selected_topics or None)
eligible = stems_for_available_roles(ready_all, available_adult_roles) if "user" in saved_face_paths else []

st.info(
    f"**{len(ready_all)}** ready templates in selected topics · "
    f"**{len(eligible)}** usable with your uploaded faces "
    f"({', '.join(sorted(available_adult_roles)) or 'no adults yet'})"
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
    elif not selected_topics:
        st.warning("⚠️ Please select at least one topic.")
    elif "user" not in saved_face_paths:
        st.warning("⚠️ Please upload the child's photo.")
    elif not available_adult_roles:
        st.warning("⚠️ Upload at least one adult photo (Mum/Dad/Grandma/Grandad).")
    elif not eligible:
        st.warning(
            "⚠️ No ready templates match your uploaded adults and topics. "
            "Add more role-locked stems or upload the matching adult photo."
        )
    else:
        st.session_state.pipeline = {
            "phase": "build",
            "student_name": student_name.strip(),
            "gender": gender,
            "child_age": int(child_age),
            "family_names": {k: v.strip() for k, v in family_names.items() if v and v.strip()},
            "selected_topics": selected_topics,
            "num_questions": int(num_questions),
            "run_ai_finish": run_ai_finish,
            "fav_color": fav_color.strip(),
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
    with st.spinner("Selecting templates and personalising faces…"):
        faces = pipeline["saved_face_paths"]
        adult_roles = set(pipeline["available_adult_roles"])
        pool = stems_for_available_roles(
            list_ready_stems(topics=pipeline["selected_topics"]),
            adult_roles,
        )
        chosen = select_stems(pool, pipeline["num_questions"])
        if not chosen:
            st.error("No stems available to build the workbook.")
            st.session_state.pipeline = None
            st.stop()

        try:
            items = build_workbook_items(
                chosen,
                user_name=pipeline["student_name"],
                family_names=pipeline["family_names"],
                face_paths=faces,
                run_ai_finish=pipeline["run_ai_finish"],
                out_dir=PIPELINE_ROOT / "_runtime" / "personalized",
            )
        except Exception as exc:
            st.error(f"Personalisation failed: {exc}")
            st.session_state.pipeline = None
            st.stop()

        pipeline["items"] = items
        pipeline["phase"] = "pdf"
    st.rerun()

elif phase == "pdf":
    items = pipeline["items"]
    questions = [f"{i}. {it['question']}" for i, it in enumerate(items, start=1)]
    image_paths = [it["image_path"] for it in items]
    question_topics = [it["topic_label"] for it in items]
    question_adults = [it["adult_name"] for it in items]
    question_options = [it["options"] for it in items]
    topic_header = ", ".join(sorted({it["topic_label"] for it in items}))

    with st.spinner("📄 Creating PDF workbook…"):
        pdf_bytes = generate_pdf(
            pipeline["student_name"],
            "Grade 1",
            topic_header,
            questions,
            image_paths,
            question_topics=question_topics,
            favourite_colour=pipeline.get("fav_color", ""),
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
    st.success("🎉 Personalised Maths Workbook ready!")

    items = pipeline.get("items") or []
    if items:
        with st.expander("Questions in this workbook", expanded=False):
            for it in items:
                st.markdown(
                    f"**{it['topic_label']}** · {it['adult_name']} · "
                    f"`{it['stem_id']}` → answer **{it['correct']}**"
                )
                st.write(it["question"])
                if Path(it["image_path"]).is_file():
                    st.image(it["image_path"], width=280)
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
        # Keep personalized previews on disk for debugging; clear session only
        st.session_state.pipeline = None
        st.rerun()
