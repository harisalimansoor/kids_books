# 📚 My Maths Practice Book — AI Personalized Workbook Generator

An AI-powered system that generates personalized Grade 1 / Year 1 maths practice workbooks as printable landscape PDFs. It customizes word problems with the child's name, family members, and favorite foods/hobbies, and generates high-quality educational illustrations using OpenAI GPT-5.4 Image 2 via OpenRouter.

---

## 🌟 Key Features

- 🎯 **1-Call Direct AI Generation**: Generates full, cohesive educational scenes from scratch in a single multimodal API call. Reference photos of the child and family members are fed directly into the model alongside the question text and `prompt.md`.
- 📚 **Curriculum-Aligned Question Bank**: Over 260+ pre-built, verified math question stems covering 10 key Grade 1 topics (Addition, Subtraction, Money, Time, Fractions, Geometry, Measurement, Number & Place Value, etc.).
- 👥 **Family & Identity Matching**: Automatically slots uploaded photos and names for Child, Mum, Dad, Grandma, Grandad, Sibling, Aunt, or Uncle, adjusting pronouns and relations seamlessly.
- 🎨 **Child Interests & Theming**: Matches questions to the child's favorite foods and hobbies, with custom PDF color palettes tailored to the child's favorite color.
- 📄 **Print-Ready Landscape PDF**: Generates multi-page A4 landscape PDFs with question text, multiple-choice options, and soft-card educational illustrations.

---

## 📁 Project Structure

```text
kids_books/
│
├── 🔑 .env                                 # Environment variables (OpenRouter API key)
├── 📝 prompt.md                            # Master visual styling & character prompt guide
├── 📄 pdf_generator.py                     # Landscape PDF Workbook builder (FPDF2)
├── 🛠️ utils.py                             # Grammar, pronouns & text normalization
├── 📋 requirements.txt                     # Python package dependencies
├── 📖 README.md                            # Project documentation & run guide
│
└── 📁 new_pipeline/
    ├── 🚀 newapp.py                        # Streamlit web interface
    ├── 🎨 image_generator.py               # Multimodal AI image generation engine
    ├── ⚙️ stem_pipeline.py                 # Question selection, role filtering & MCQ logic
    ├── 📄 __init__.py
    │
    ├── 📁 Question clusters for grade 1/   # Plain-text question clusters (10 topics)
    │   ├── addition.txt
    │   ├── fractions.txt
    │   ├── general_math.txt
    │   ├── geometry.txt
    │   ├── measurement.txt
    │   ├── money.txt
    │   ├── multiplication_and_division.txt
    │   ├── number_and_place_value.txt
    │   ├── subtraction.txt
    │   └── time.txt
    │
    └── 📁 question_templates/              # Question templates & metadata
        ├── 📄 __init__.py
        ├── 📁 grade_1/                     # Classic Grade 1 templates (meta.json)
        └── 📁 grade_1_hamdan/              # Curated Grade 1 templates (meta.json)
```

---

## ⚙️ Prerequisites

- **Python**: Version 3.10 or higher
- **OpenRouter API Key**: Required for AI image generation.

---

## 🚀 Quick Start Guide

### 1. Install Dependencies

Install all required Python packages from `requirements.txt`:

```powershell
pip install -r requirements.txt
```

### 2. Set Up Your API Key

Create or edit the `.env` file in the root directory (`kids_books/.env`) and add your OpenRouter API key:

```env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

*(Optional environment variables)*:
```env
# Change the image generation model (Default: openai/gpt-5.4-image-2)
IMAGE_GEN_MODEL=openai/gpt-5.4-image-2

# Retry attempts on API timeouts (Default: 3)
IMAGE_GEN_MAX_ATTEMPTS=3
```

### 3. Run the Application

Launch the Streamlit web application:

```powershell
python -m streamlit run new_pipeline/newapp.py
```

After running the command, open your browser at:
👉 **`http://localhost:8501`**

---

## 📖 How to Use the App

1. **Child Information**: Enter your child's name, age, gender, and favorite color (used for workbook accent colors).
2. **Family Members**: Enter the real names of family members (e.g. Mum, Dad, Brother) and upload clear reference photos.
3. **Favorites & Interests**: Select favorite foods (e.g., apples, cookies) and hobbies (e.g., toy cars, lego) to automatically match math problem themes.
4. **Select Math Topics & Number Range**: Choose Grade 1 topics (Addition, Subtraction, Time, etc.) and the number range (10, 20, or 50).
5. **Generate Workbook**:
   - Click **Generate Workbook**.
   - The AI will generate custom illustrations for each question and assemble the final landscape PDF.
   - Preview questions and images on screen and click **Download PDF Workbook**.

---

## 🛠️ Tech Stack

- **Frontend / UI**: [Streamlit](https://streamlit.io/)
- **Image Generation**: OpenAI `gpt-5.4-image-2` via [OpenRouter API](https://openrouter.ai/)
- **PDF Generation**: [fpdf2](https://py-pdf.github.io/fpdf2/)
- **Image Processing**: [Pillow](https://pillow.readthedocs.io/)
- **Environment Management**: [python-dotenv](https://github.com/theskumar/python-dotenv)
