# """
# Main Streamlit app - Personalized Math Question Generator
# """
# import os
# import time
# from io import BytesIO
# import streamlit as st

# # Import from our modules
# from config import IMAGE_COST
# from api_clients import generate_image_for_question, download_image, get_question_hash
# from file_handlers import get_topics_for_grade, load_sample_questions, load_all_questions_for_grade
# from prompt_builder import build_prompt, build_family_context
# from pdf_generator import generate_pdf, cleanup_temp_images
# from utils import clean_generated_questions, create_safe_filename


# # ============ Streamlit UI ============
# st.set_page_config(
#     page_title="Personalized Math Question Generator",
#     page_icon="📚",
#     layout="centered"
# )

# st.title("📚 Personalized Math Question Generator")
# st.write(
#     "Generate personalized math worksheets with illustrations based on your curated `.txt` files. "
#     "Pick a grade and topic, personalize with family & hobbies, and export a PDF."
# )

# # --- Student Info ---
# st.subheader("👤 Student Information")

# # Row 1: Name & Siblings
# col_name, col_sib = st.columns(2)
# with col_name:
#     student_name = st.text_input("Student's Name:*", placeholder="e.g., Ali")
# with col_sib:
#     siblings = st.text_input("Siblings' Names:", placeholder="e.g., Sara, Ahmed (optional)")

# # Row 2: Gender & Hobbies
# col_gen, col_hob = st.columns(2)
# with col_gen:
#     gender = st.selectbox("Gender:*", ["Select", "Boy", "Girl", "Other"])
# with col_hob:
#     hobbies = st.text_input("Hobbies/Interests:", placeholder="e.g., football, drawing (optional)")

# # Row 3: Parents
# col_mom, col_dad = st.columns(2)
# with col_mom:
#     mother_name = st.text_input("Mother's Name:", placeholder="Optional")
# with col_dad:
#     father_name = st.text_input("Father's Name:", placeholder="Optional")

# # Row 4: Grandparents
# col_gmo, col_gfa = st.columns(2)
# with col_gmo:
#     grandmother_name = st.text_input("Grandmother's Name:", placeholder="Optional")
# with col_gfa:
#     grandfather_name = st.text_input("Grandfather's Name:", placeholder="Optional")

# # --- Face & Object Customization ---
# saved_face_paths = {}
# with st.expander("👤 Personalize Faces & Objects (for Swapping)"):
#     st.write("Upload photos to see family members in the illustrations!")
    
#     if not os.path.exists("personalized_faces"):
#         os.makedirs("personalized_faces")

#     col_f1, col_f2 = st.columns(2)
    
#     face_map = {}
    
#     with col_f1:
#         self_face = st.file_uploader("Upload Child's Face:", type=["jpg", "png", "jpeg"])
#         if self_face: face_map["user"] = self_face
        
#         mom_face = st.file_uploader("Upload Mother's Face:", type=["jpg", "png", "jpeg"])
#         if mom_face: face_map["mother"] = mom_face
        
#         gmo_face = st.file_uploader("Upload Grandmother's Face:", type=["jpg", "png", "jpeg"])
#         if gmo_face: face_map["grandmother"] = gmo_face

#     with col_f2:
#         sib_face = st.file_uploader("Upload Sibling's Face:", type=["jpg", "png", "jpeg"])
#         if sib_face: face_map["sibling"] = sib_face
        
#         dad_face = st.file_uploader("Upload Father's Face:", type=["jpg", "png", "jpeg"])
#         if dad_face: face_map["father"] = dad_face
        
#         gfa_face = st.file_uploader("Upload Grandfather's Face:", type=["jpg", "png", "jpeg"])
#         if gfa_face: face_map["grandfather"] = gfa_face

#     # Save uploaded files
#     saved_face_paths = {}
#     for role, file in face_map.items():
#         path = os.path.join("personalized_faces", f"{role}_face.png")
#         with open(path, "wb") as f:
#             f.write(file.getbuffer())
#         saved_face_paths[role] = path

# # --- Worksheet Settings ---
# st.subheader("📖 Worksheet Settings")
# grade = st.selectbox("Select Grade:*", ["Select Grade", "Grade 1"], help="More grades coming soon!")

# topics_for_grade = []
# use_all_topics = False
# selected_topics = []

# if grade != "Select Grade":
#     topics_for_grade = get_topics_for_grade(grade)

# if grade == "Grade 1":
#     if topics_for_grade:
#         use_all_topics = st.checkbox("Use all topics", value=False)
#         selected_topics = st.multiselect(
#             "Select Topic(s):",
#             options=topics_for_grade,
#             default=([] if not topics_for_grade else [topics_for_grade[0]]),
#             help="You can pick multiple topics. Check 'Use all topics' to include everything."
#         )
#     else:
#         st.info("No topics found. Ensure 'extracted_bank/grade_1_uk_year_1_templated_final_categories_visual.txt' exists.")

# num_questions = st.number_input(
#     "Total number of questions to generate:",
#     min_value=1,
#     max_value=50,
#     value=10
# )

# # --- Image Settings ---
# st.subheader("🎨 Image Settings")
# include_images = st.checkbox(
#     "Include images for each question",
#     value=True,
#     help="Generates AI images for each question (may take a few minutes if face swapping is enabled)"
# )

# # --- Generate Button ---
# if st.button("📝 Generate Personalized Workbook", type="primary"):
#     # Validation
#     if not student_name.strip():
#         st.warning("⚠️ Please enter the student's name.")
#     elif gender == "Select":
#         st.warning("⚠️ Please select the student's gender.")
#     elif grade == "Select Grade":
#         st.warning("⚠️ Please select a grade level.")
#     elif grade == "Grade 1" and not topics_for_grade:
#         st.warning("⚠️ No topic files found for Grade 1.")
#     else:
#         # Build family context
#         family_context = build_family_context(
#             mother_name, father_name, grandmother_name,
#             grandfather_name, siblings
#         )

#         # Load questions
#         with st.spinner("📄 Loading sample problems..."):
#             if use_all_topics or not selected_topics:
#                 extracted_text = load_all_questions_for_grade(grade)
#                 topic_context = "covering various topics"
#                 topic_header_text = "All topics"
#             else:
#                 blocks = []
#                 for t in selected_topics:
#                     content = load_sample_questions(grade, t)
#                     if content and not content.startswith("Error"):
#                         blocks.append(f"=== Topic: {t} ===\n{content}\n")
#                 extracted_text = "\n".join(blocks)
#                 topic_context = f"focusing on {', '.join(selected_topics)}"
#                 topic_header_text = ", ".join(selected_topics)

#         if not extracted_text or extracted_text.startswith("Error"):
#             st.error("Could not load sample questions from the .txt files.")
#         else:
#             st.success("✅ Loaded sample problems!")
            
#             with st.expander("📄 Preview of source content"):
#                 preview_text = extracted_text[:800]
#                 if len(extracted_text) > 800:
#                     preview_text += "..."
#                 st.text(preview_text)

#             # Generate questions -> Selecting from pregenerated bank
#             import os
#             import random
#             import re
#             import itertools
            
#             with st.spinner("🤖 Selecting questions from the bank..."):
#                 topics = extracted_text.split("=== Topic:")
#                 topic_questions = []
#                 for topic in topics:
#                     if not topic.strip(): continue
#                     lines = topic.strip().split("\n")
#                     # Find all lines that look like our templated questions
#                     qs = [l.strip() for l in lines[1:] if l.strip() and "{" in l]
#                     if qs:
#                         topic_questions.append(qs)
                        
#                 all_raw_questions = []
#                 for q_tuple in itertools.zip_longest(*topic_questions):
#                     for q in q_tuple:
#                         if q is not None:
#                             all_raw_questions.append(q)
                            
#                 # Filter by those with pregenerated images
#                 available_questions = []
#                 for q in all_raw_questions:
#                     q_hash = get_question_hash(q)
#                     bank_img_path = f"question_bank_images/grade_1/{q_hash}.png"
#                     if os.path.exists(bank_img_path):
#                         available_questions.append(q)
                        
#                 if len(available_questions) == 0:
#                     st.error("No questions found with pre-generated images in the selected topics. Please run pregenerate_bank_images.py first.")
#                     st.stop()
                    
#                 selected_raw = available_questions[:num_questions]
                
#                 # Replace placeholders
#                 questions_data = [] # stores (personalized_text, raw_text)
#                 replacements = {
#                     r'\{user_name\}': student_name or "the child",
#                     r'\{mother_name\}': mother_name or "mother",
#                     r'\{father_name\}': father_name or "father",
#                     r'\{grandmother_name\}': grandmother_name or "grandmother",
#                     r'\{grandfather_name\}': grandfather_name or "grandfather",
#                     r'\{sibling_name\}': siblings.split(',')[0].strip() if siblings else "sibling",
#                 }
                
#                 for q_raw in selected_raw:
#                     text = q_raw
#                     for pattern, replacement in replacements.items():
#                         text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
#                     questions_data.append((text, q_raw))
                    
#                 questions = [item[0] for item in questions_data]

#             st.info(f"✅ Selected {len(questions)} questions from bank")
#             with st.expander("👀 Preview Generated Questions"):
#                 for i, q in enumerate(questions, 1):
#                     st.write(f"{i}. {q}")

#             # Generate Images
#             image_paths = []
#             synced_questions = list(questions)  # will hold vision-synced question text
#             if include_images:
#                 st.write("---")
#                 st.subheader("🎨 Processing Illustrations...")
#                 progress_bar = st.progress(0)
#                 status_text = st.empty()

#                 from utils import detect_role
#                 from api_clients import analyze_image_and_update_question
#                 for idx, (q_pers, q_raw) in enumerate(questions_data, start=1):
#                     status_text.text(f"Processing illustration {idx} of {len(questions_data)}...")

#                     # Detect role from the raw question
#                     role = detect_role(q_raw)
#                     face_path = saved_face_paths.get(role) if role else None
                    
#                     if face_path:
#                         status_text.text(f"Personalizing image for {role} in illustration {idx}...")

#                     img_url = generate_image_for_question(
#                         question_text=q_raw,
#                         student_name=student_name,
#                         saved_face_paths=saved_face_paths,   # Pass the full dictionary!
#                         role=role
#                     )

#                     if img_url:
#                         temp_path = f"temp_img_{idx}_{int(time.time())}.jpg"
#                         if download_image(img_url, temp_path):
#                             image_paths.append(temp_path)
#                             # ── Vision sync: count objects in image, fix question if needed ──
#                             status_text.text(f"🔍 Verifying object count for question {idx}...")
#                             synced_q, was_changed = analyze_image_and_update_question(
#                                 temp_path, questions[idx - 1]
#                             )
#                             synced_questions[idx - 1] = synced_q
#                             if was_changed:
#                                 st.info(f"✏️ Question {idx} was auto-updated to match the generated image.")
#                         else:
#                             image_paths.append(None)
#                     else:
#                         image_paths.append(None)

#                     progress_bar.progress(idx / len(questions_data))
#                     time.sleep(1)  # Delay to avoid rate limits

#                 status_text.text("✅ All illustrations generated!")
#                 successful_images = sum(1 for p in image_paths if p is not None)
#                 st.success(f"Generated {successful_images}/{len(questions)} illustrations successfully")


#             # Build PDF
#             with st.spinner("📄 Creating PDF workbook..."):
#                 pdf_bytes = generate_pdf(
#                     student_name, grade, topic_header_text,
#                     synced_questions, image_paths if include_images else None
#                 )

#             # Clean up temporary image files
#             if include_images:
#                 cleanup_temp_images(image_paths)

#             # Download button
#             filename = create_safe_filename(student_name)
#             st.success("🎉 Personalized Math Workbook ready!")
#             st.download_button(
#                 "📥 Download PDF Workbook",
#                 data=BytesIO(pdf_bytes),
#                 file_name=filename,
#                 mime="application/pdf",
#                 type="primary"
#             )


"""
Main Streamlit app - Personalized Math Question Generator
Version with deterministic image compositing (exact object counts)
"""

import os
import time
import re
import itertools
from io import BytesIO

import streamlit as st

from config import IMAGE_COST  # not actively used, kept for compatibility

from file_handlers import get_topics_for_grade, load_sample_questions, load_all_questions_for_grade
from prompt_builder import build_family_context
from pdf_generator import generate_pdf, cleanup_temp_images
from utils import create_safe_filename, detect_role

# Blueprint-to-Render pipeline (only image generation method)
from blueprint_generator import generate_blueprint, OBJECT_KEYWORDS
from ai_renderer import render_image as ai_render, _build_prompt, _build_text_prompt
from face_swap_processor import swap_faces

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
    page_title="Personalized Math Question Generator",
    page_icon="📚",
    layout="centered"
)

st.title("📚 Personalized Math Question Generator")
st.write(
    "Generate personalized math worksheets with illustrations based on your curated `.txt` files. "
    "Pick a grade and topic, personalize with family & hobbies, and export a PDF."
)

# Pipeline state
if "pipeline" not in st.session_state:
    st.session_state.pipeline = None

# ------------------------------------------------------------------------------
# Student Information form
# ------------------------------------------------------------------------------
st.subheader("👤 Student Information")
col_name, col_sib = st.columns(2)
with col_name:
    student_name = st.text_input("Student's Name:*", placeholder="e.g., Ali")
with col_sib:
    siblings = st.text_input("Siblings' Names:", placeholder="e.g., Sara, Ahmed (optional)")

col_gen, col_hob = st.columns(2)
with col_gen:
    gender = st.selectbox("Gender:*", ["Select", "Boy", "Girl", "Other"])
with col_hob:
    hobbies = st.text_input("Hobbies/Interests:", placeholder="e.g., football, drawing (optional)")

col_mom, col_dad = st.columns(2)
with col_mom:
    mother_name = st.text_input("Mother's Name:", placeholder="Optional")
with col_dad:
    father_name = st.text_input("Father's Name:", placeholder="Optional")

col_gmo, col_gfa = st.columns(2)
with col_gmo:
    grandmother_name = st.text_input("Grandmother's Name:", placeholder="Optional")
with col_gfa:
    grandfather_name = st.text_input("Grandfather's Name:", placeholder="Optional")

# ------------------------------------------------------------------------------
# Face upload section (collapsible)
# ------------------------------------------------------------------------------
saved_face_paths = {}
with st.expander("👤 Personalize Faces & Objects (for Swapping)"):
    st.write("Upload photos to see family members in the illustrations!")
    if not os.path.exists("personalized_faces"):
        os.makedirs("personalized_faces")

    face_map = {}
    col_f1, col_f2 = st.columns(2)

    with col_f1:
        self_face = st.file_uploader("Upload Child's Face:", type=["jpg", "png", "jpeg"])
        if self_face: face_map["user"] = self_face
        mom_face = st.file_uploader("Upload Mother's Face:", type=["jpg", "png", "jpeg"])
        if mom_face: face_map["mother"] = mom_face
        gmo_face = st.file_uploader("Upload Grandmother's Face:", type=["jpg", "png", "jpeg"])
        if gmo_face: face_map["grandmother"] = gmo_face

    with col_f2:
        sib_face = st.file_uploader("Upload Sibling's Face:", type=["jpg", "png", "jpeg"])
        if sib_face: face_map["sibling"] = sib_face
        dad_face = st.file_uploader("Upload Father's Face:", type=["jpg", "png", "jpeg"])
        if dad_face: face_map["father"] = dad_face
        gfa_face = st.file_uploader("Upload Grandfather's Face:", type=["jpg", "png", "jpeg"])
        if gfa_face: face_map["grandfather"] = gfa_face

    # Save uploaded faces to disk
    for role, file in face_map.items():
        path = os.path.join("personalized_faces", f"{role}_face.png")
        with open(path, "wb") as f:
            f.write(file.getbuffer())
        saved_face_paths[role] = path

# ------------------------------------------------------------------------------
# Worksheet Settings
# ------------------------------------------------------------------------------
st.subheader("📖 Worksheet Settings")
grade = st.selectbox("Select Grade:*", ["Select Grade", "Grade 1"], help="More grades coming soon!")

topics_for_grade = []
use_all_topics = False
selected_topics = []

if grade != "Select Grade":
    topics_for_grade = get_topics_for_grade(grade)

if grade == "Grade 1":
    if topics_for_grade:
        use_all_topics = st.checkbox("Use all topics", value=False)
        selected_topics = st.multiselect(
            "Select Topic(s):",
            options=topics_for_grade,
            default=([] if not topics_for_grade else [topics_for_grade[0]]),
            help="You can pick multiple topics. Check 'Use all topics' to include everything."
        )
    else:
        st.info("No topics found. Ensure 'extracted_bank/grade_1_uk_year_1_templated_final_categories_visual.txt' exists.")

num_questions = st.number_input(
    "Total number of questions to generate:",
    min_value=1,
    max_value=50,
    value=10
)

# ------------------------------------------------------------------------------
# Image Settings
# ------------------------------------------------------------------------------
st.subheader("🎨 Image Settings")
include_images = st.checkbox(
    "Include images for each question",
    value=True,
    help="Generates images using the Blueprint-to-Render pipeline."
)

# ------------------------------------------------------------------------------
# Generate Button & Validation
# ------------------------------------------------------------------------------
if st.button("📝 Generate Personalized Workbook", type="primary"):

    # ---------- Validation ----------
    if not student_name.strip():
        st.warning("⚠️ Please enter the student's name.")
    elif gender == "Select":
        st.warning("⚠️ Please select the student's gender.")
    elif grade == "Select Grade":
        st.warning("⚠️ Please select a grade level.")
    elif grade == "Grade 1" and not topics_for_grade:
        st.warning("⚠️ No topic files found for Grade 1.")
    else:
        # ---------- Family Context ----------
        family_context = build_family_context(
            mother_name, father_name, grandmother_name,
            grandfather_name, siblings
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

            # Select requested number
            selected_raw = available_questions[:num_questions]

            # Determine hobby object
            hobby_obj = map_hobby_to_object(hobbies)

            # Personalise: replace placeholders with actual names
            questions_data = []  # (personalized_text, raw_text)
            replacements = {
                r'\{user_name\}':        student_name or "the child",
                r'\{mother_name\}':      mother_name or "mother",
                r'\{father_name\}':      father_name or "father",
                r'\{grandmother_name\}': grandmother_name or "grandmother",
                r'\{grandfather_name\}': grandfather_name or "grandfather",
                r'\{sibling_name\}':     siblings.split(',')[0].strip() if siblings else "sibling",
            }
            for q_raw in selected_raw:
                text = q_raw
                # Replace name placeholders
                for pattern, replacement in replacements.items():
                    text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                # Replace object words with the user's hobby object
                if hobby_obj:
                    text = replace_objects_in_text(text, hobby_obj)
                    q_raw = replace_objects_in_text(q_raw, hobby_obj)
                questions_data.append((text, q_raw))

            questions = [item[0] for item in questions_data]

            st.info(f"✅ Selected {len(questions)} questions from bank")
            with st.expander("👀 Preview Generated Questions"):
                for i, q in enumerate(questions, 1):
                    st.write(f"{i}. {q}")

        # ---------- Store pipeline state ----------
        st.session_state.pipeline = {
            "phase": "blueprint" if include_images else "pdf",
            "questions_data": questions_data,
            "questions": questions,
            "synced_questions": list(questions),
            "student_name": student_name,
            "gender": gender,
            "grade": grade,
            "topic_header_text": topic_header_text,
            "include_images": include_images,
            "saved_face_paths": saved_face_paths,
            "image_paths": [],
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
        for idx, (q_pers, q_raw) in enumerate(pipeline["questions_data"], start=1):
            # Build face map for all possible roles — blueprint will paste
            # matching faces onto head positions instead of green circles
            face_map_for_bp = {}
            for role_key, saved_key in role_to_saved.items():
                if saved_key in pipeline["saved_face_paths"]:
                    face_map_for_bp[role_key] = pipeline["saved_face_paths"][saved_key]

            blueprint, metadata = generate_blueprint(q_raw, face_map=face_map_for_bp)

            # Track which faces were actually used in this question
            question_face_map = {}
            for ch in metadata["characters"]:
                saved_key = role_to_saved.get(ch["role_key"])
                if saved_key and saved_key in pipeline["saved_face_paths"]:
                    question_face_map[ch["role_key"]] = pipeline["saved_face_paths"][saved_key]

            preserve = metadata.get("has_faces", False)
            prompt = _build_prompt(metadata, preserve_faces=preserve, gender=pipeline.get("gender", "Boy"))
            text_prompt = _build_text_prompt(metadata, gender=pipeline.get("gender", "Boy"))

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
                                       gender=pipeline.get("gender", "Boy"))

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
        st.success("🎉 Personalized Math Workbook ready!")
        st.download_button(
            "📥 Download PDF Workbook",
            data=BytesIO(pipeline["pdf_bytes"]),
            file_name=filename,
            mime="application/pdf",
            type="primary",
        )

        if st.button("🔄 Start Over"):
            cleanup_temp_images(pipeline.get("image_paths", []))
            st.session_state.pipeline = None
            st.rerun()