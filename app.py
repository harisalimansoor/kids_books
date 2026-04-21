"""
Main Streamlit app - Personalized Math Question Generator
"""
import time
from io import BytesIO
import streamlit as st

# Import from our modules
from config import IMAGE_COST
from api_clients import call_groq, generate_image_for_question, download_image
from file_handlers import get_topics_for_grade, load_sample_questions, load_all_questions_for_grade
from prompt_builder import build_prompt, build_family_context
from pdf_generator import generate_pdf, cleanup_temp_images
from utils import clean_generated_questions, create_safe_filename


# ============ Streamlit UI ============
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

# --- Student Info ---
st.subheader("👤 Student Information")
col1, col2 = st.columns(2)

with col1:
    student_name = st.text_input("Student's Name:*", placeholder="e.g., Ali")
    gender = st.selectbox("Gender:*", ["Select", "Boy", "Girl", "Other"])
    mother_name = st.text_input("Mother's Name:", placeholder="Optional")
    father_name = st.text_input("Father's Name:", placeholder="Optional")

with col2:
    siblings = st.text_input("Siblings' Names:", placeholder="e.g., Sara, Ahmed (optional)")
    friends = st.text_input("Friends' Names:", placeholder="e.g., Zain, Fatima (optional)")
    grandmother_name = st.text_input("Grandmother's Name:", placeholder="Optional")
    grandfather_name = st.text_input("Grandfather's Name:", placeholder="Optional")

hobbies = st.text_input("Hobbies/Interests:", placeholder="e.g., football, drawing, reading (optional)")

# --- Worksheet Settings ---
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
        st.info("No topics found in question_bank/grade_1. Add .txt files there.")

num_questions = st.number_input(
    "Total number of questions to generate:",
    min_value=1,
    max_value=50,
    value=10
)

# --- Image Settings ---
st.subheader("🎨 Image Settings")
col_img1, col_img2, col_img3 = st.columns(3)

with col_img1:
    include_images = st.checkbox(
        "Include illustrations for each question",
        value=True,
        help="Generates AI images for each question (may take 2-5 min)"
    )

with col_img2:
    if include_images:
        image_style = st.selectbox(
            "Image Style:",
            ["cartoon", "simple", "watercolor", "sticker", "playful", "educational"],
            help="Visual style for the illustrations"
        )

with col_img3:
    if include_images:
        image_quality = st.selectbox(
            "Image Quality:",
            ["standard", "hd"],
            help="HD costs 2x more but has better detail"
        )

if include_images:
    cost_per_image = IMAGE_COST[image_quality]
    estimated_time = num_questions * 8  # DALL-E 3 takes ~8 seconds per image
    st.info(
        f"ℹ️ Generating {num_questions} {image_quality.upper()} images will take "
        f"approximately {estimated_time//60} min {estimated_time%60} sec and "
        f"cost ~${num_questions * cost_per_image:.2f}"
    )

# --- Generate Button ---
if st.button("📝 Generate Personalized Workbook", type="primary"):
    # Validation
    if not student_name.strip():
        st.warning("⚠️ Please enter the student's name.")
    elif gender == "Select":
        st.warning("⚠️ Please select the student's gender.")
    elif grade == "Select Grade":
        st.warning("⚠️ Please select a grade level.")
    elif grade == "Grade 1" and not topics_for_grade:
        st.warning("⚠️ No topic files found for Grade 1.")
    else:
        # Build family context
        family_context = build_family_context(
            mother_name, father_name, grandmother_name,
            grandfather_name, siblings, friends
        )

        # Load questions
        with st.spinner("📄 Loading sample problems..."):
            if use_all_topics or not selected_topics:
                extracted_text = load_all_questions_for_grade(grade)
                topic_context = "covering various topics"
                topic_header_text = "All topics"
            else:
                blocks = []
                for t in selected_topics:
                    content = load_sample_questions(grade, t)
                    if content and not content.startswith("Error"):
                        blocks.append(f"=== Topic: {t} ===\n{content}\n")
                extracted_text = "\n".join(blocks)
                topic_context = f"focusing on {', '.join(selected_topics)}"
                topic_header_text = ", ".join(selected_topics)

        if not extracted_text or extracted_text.startswith("Error"):
            st.error("Could not load sample questions from the .txt files.")
        else:
            st.success("✅ Loaded sample problems!")
            
            with st.expander("📄 Preview of source content"):
                preview_text = extracted_text[:800]
                if len(extracted_text) > 800:
                    preview_text += "..."
                st.text(preview_text)

            # Build prompt
            prompt = build_prompt(
                student_name, gender, grade, topic_context,
                extracted_text, num_questions, family_context, hobbies
            )

            # Generate questions
            with st.spinner("🤖 Generating personalized questions..."):
                generated_text = call_groq(prompt)

            questions = clean_generated_questions(generated_text, num_questions)

            st.info(f"✅ Generated {len(questions)} questions")
            with st.expander("👀 Preview Generated Questions"):
                for i, q in enumerate(questions, 1):
                    st.write(f"{i}. {q}")

            # Generate Images
            image_paths = []
            if include_images:
                st.write("---")
                st.subheader("🎨 Generating Illustrations...")
                progress_bar = st.progress(0)
                status_text = st.empty()

                for idx, q in enumerate(questions, start=1):
                    status_text.text(f"Creating illustration {idx} of {len(questions)}...")

                    img_url = generate_image_for_question(q, student_name, image_style, image_quality)

                    if img_url:
                        temp_path = f"temp_img_{idx}_{int(time.time())}.png"
                        if download_image(img_url, temp_path):
                            image_paths.append(temp_path)
                        else:
                            image_paths.append(None)
                    else:
                        image_paths.append(None)

                    progress_bar.progress(idx / len(questions))
                    time.sleep(1)  # Delay to avoid rate limits

                status_text.text("✅ All illustrations generated!")
                successful_images = sum(1 for p in image_paths if p is not None)
                st.success(f"Generated {successful_images}/{len(questions)} illustrations successfully")

            # Build PDF
            with st.spinner("📄 Creating PDF workbook..."):
                pdf_bytes = generate_pdf(
                    student_name, grade, topic_header_text,
                    questions, image_paths if include_images else None
                )

            # Clean up temporary image files
            if include_images:
                cleanup_temp_images(image_paths)

            # Download button
            filename = create_safe_filename(student_name)
            st.success("🎉 Personalized Math Workbook ready!")
            st.download_button(
                "📥 Download PDF Workbook",
                data=BytesIO(pdf_bytes),
                file_name=filename,
                mime="application/pdf",
                type="primary"
            )