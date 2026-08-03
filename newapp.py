"""
Main Streamlit app — Personalised Maths Question Generator
Kitchen-Scenes-only pipeline: one food template drives both the
personalised illustration AND the maths questions in the workbook.
"""

from io import BytesIO
import tempfile

import streamlit as st

from pdf_generator import generate_pdf, cleanup_temp_images
from utils import create_safe_filename

# Kitchen Scenes Direct Food Template Integration — the ONLY
# question + image generation path used by this app now.
from kitchen_scenes.run_direct_pipeline import (
    list_available_templates,
    run_pipeline as run_kitchen_pipeline,
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
    "Create a personalised Year 1 maths workbook built entirely around your "
    "child's favourite food! Tell us about your child, pick a favourite food, "
    "and we'll generate a personalised kitchen scene illustration together "
    "with maths questions based on it."
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

# ------------------------------------------------------------------------------
# Favourite Food (drives the kitchen scene template + the questions)
# ------------------------------------------------------------------------------
st.divider()
st.markdown("#### 🍳 Favourite Food")
st.caption(
    "Pick your child's favourite food. This picks the kitchen scene template "
    "used for the illustration and for the maths questions in the workbook."
)
_available_foods = [t["food"] for t in list_available_templates() if t.get("annotated")]
favourite_food = st.selectbox(
    "Favourite Food*",
    options=["Select"] + _available_foods,
    index=0,
    key="favourite_food_picker",
)
if favourite_food not in ("Select",):
    st.info(f"✅ Kitchen template available for **{favourite_food}**.")
elif not _available_foods:
    st.warning("⚠️ No annotated kitchen templates found. Please add one before generating a workbook.")

# ------------------------------------------------------------------------------
# Illustration Style
# ------------------------------------------------------------------------------
st.divider()
st.markdown("#### 🎨 Illustration Style")
style_choice = st.radio(
    "Style for the worksheet illustration",
    options=["Realistic", "Cartoonish"],
    index=0,
    horizontal=True,
)
image_style = "cartoon" if style_choice == "Cartoonish" else "realistic"

# ------------------------------------------------------------------------------
# Face upload section (collapsible)
# ------------------------------------------------------------------------------
st.divider()
saved_face_paths = {}
with st.expander("Upload Family Photos (for face swapping)", expanded=False):
    st.caption("Upload photos and we'll put your family's faces onto the characters in the kitchen scene!")

    import os
    if not os.path.exists("personalised_faces"):
        os.makedirs("personalised_faces")

    face_map = {}
    family_roles = [
        ("user", "Child"),
        ("mother", "Mum"),
        ("father", "Dad"),
        ("grandmother", "Grandma"),
        ("grandfather", "Grandad"),
    ]
    fam_cols = st.columns(3)
    for i, (role_key, role_label) in enumerate(family_roles):
        with fam_cols[i % 3]:
            uploaded = st.file_uploader(role_label, type=["jpg", "png", "jpeg"], key=f"face_{role_key}")
            if uploaded:
                face_map[role_key] = uploaded
                st.image(uploaded, width=70)

    for role, file in face_map.items():
        path = os.path.join("personalised_faces", f"{role}_face.png")
        with open(path, "wb") as f:
            f.write(file.getbuffer())
        saved_face_paths[role] = path

st.divider()

# ------------------------------------------------------------------------------
# Helper: turn a kitchen_scenes question dict into workbook-ready text
# ------------------------------------------------------------------------------
def _format_kitchen_question(q: dict, idx: int) -> str:
    text = f"{idx}. {q.get('question', '').strip()}"
    options = q.get("options")
    if options:
        letters = ["A", "B", "C", "D", "E", "F"]
        opt_lines = [f"   {letters[i]}) {opt}" for i, opt in enumerate(options) if i < len(letters)]
        text += "\n" + "\n".join(opt_lines)
    return text


# ------------------------------------------------------------------------------
# Generate Button & Validation
# ------------------------------------------------------------------------------
if st.button("📝 Generate Personalised Workbook", type="primary"):

    if not student_name.strip():
        st.warning("⚠️ Please enter the student's name.")
    elif gender == "Select":
        st.warning("⚠️ Please select the student's gender.")
    elif favourite_food == "Select":
        st.warning("⚠️ Please select a favourite food.")
    else:
        st.session_state.pipeline = {
            "phase": "kitchen",
            "student_name": student_name,
            "gender": gender,
            "child_age": child_age,
            "favourite_food": favourite_food,
            "image_style": image_style,
            "saved_face_paths": saved_face_paths,
        }
        st.rerun()

# ══════════════════════════════════════════════════════════════════
# PIPELINE EXECUTOR
# ══════════════════════════════════════════════════════════════════
pipeline = st.session_state.get("pipeline")
if pipeline is not None:
    phase = pipeline["phase"]

    if phase == "kitchen":
        with st.spinner(f"🍳 Generating personalised kitchen scene & questions for {pipeline['favourite_food']}..."):
            faces = pipeline["saved_face_paths"]
            ks_profile = {
                "child_name": pipeline["student_name"],
                "child_age": pipeline["child_age"],
                "grade": 1,
                "favorite_food": pipeline["favourite_food"],
                "image_style": pipeline.get("image_style", "realistic"),
            }
            # Only include a photo key if the user actually uploaded that
            # photo — no fallback to sample/demo photos. This way the
            # pipeline only swaps/blends faces when real photos exist.
            photo_role_map = {
                "child_photo": "user",
                "mother_photo": "mother",
                "father_photo": "father",
                "grandmother_photo": "grandmother",
                "grandfather_photo": "grandfather",
            }
            for profile_key, role_key in photo_role_map.items():
                if faces.get(role_key):
                    ks_profile[profile_key] = faces[role_key]
            if faces.get("mother"):
                ks_profile["adult_photo"] = faces["mother"]

            ks_result = run_kitchen_pipeline(ks_profile)
            pipeline["kitchen_result"] = ks_result

        if not ks_result or not ks_result.get("final_image"):
            st.error(
                f"❌ Could not generate a kitchen scene for **{pipeline['favourite_food']}**. "
                "The template may need face-region annotation first."
            )
            st.session_state.pipeline = None
            st.stop()

        pipeline["phase"] = "pdf"
        st.rerun()

    elif phase == "pdf":
        ks_result = pipeline["kitchen_result"]
        raw_questions = ks_result.get("questions", [])
        formatted_questions = [
            _format_kitchen_question(q, i + 1) for i, q in enumerate(raw_questions)
        ]

        # ks_result["final_image"] is an in-memory PIL.Image — it was never
        # written to disk by the pipeline. We write it to a genuine OS temp
        # file only for the duration of PDF generation (generate_pdf needs a
        # file path), then delete it immediately. It never lands anywhere
        # inside the project/codebase — only inside the finished PDF.
        temp_img_path = None
        image_paths = None
        if formatted_questions and ks_result.get("final_image") is not None:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            ks_result["final_image"].convert("RGB").save(tmp.name)
            tmp.close()
            temp_img_path = tmp.name
            image_paths = [temp_img_path] * len(formatted_questions)

        with st.spinner("📄 Creating PDF workbook..."):
            pdf_bytes = generate_pdf(
                pipeline["student_name"],
                "Grade 1",
                f"Kitchen Scene — {pipeline['favourite_food']}",
                formatted_questions,
                image_paths,
            )

        if temp_img_path:
            cleanup_temp_images([temp_img_path])

        pipeline["pdf_bytes"] = pdf_bytes
        pipeline["formatted_questions"] = formatted_questions
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