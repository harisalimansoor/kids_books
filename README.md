# My Maths Practice Book — Year 1

Welcome to **My Maths Practice Book**! A Streamlit web app that creates personalised maths workbooks for children — with AI-generated illustrations, face swapping, and exact object counting.

## Pipeline Overview

```
Question Bank → Blueprint (geometric layout) → AI Render (GPT-5.4 Image 2) → Face Swap → PDF
```

1. **Blueprint Generator** — Parses the question, detects roles & object counts, draws a deterministic 1024×1024 geometric layout (blue bodies, green heads, red objects).
2. **AI Renderer** — Sends the blueprint to OpenRouter's `openai/gpt-5.4-image-2` for photorealistic conversion. Falls back to text2img if img2img fails.
3. **Face Swap** — Uses insightface to swap user-uploaded face photos onto AI-generated characters (left-to-right matching).
4. **PDF Generator** — Assembles A4 workbook with questions + images, then cleans up temp files.

## Tech Stack

- **Python 3.10+** + **Streamlit** (UI)
- **OpenRouter** — `openai/gpt-5.4-image-2` for image generation
- **Insightface** — face detection & swapping (InSwapper)
- **FPDF2** — PDF generation
- **Pillow** — image manipulation
- **python-dotenv** — API key management

## Project Structure

```
kids_books/
├── app.py                       # Streamlit orchestrator (UI + pipeline phases)
├── blueprint_generator.py       # Step 1: parse question → geometric blueprint
├── ai_renderer.py               # Step 2: blueprint → AI render
├── face_swap_processor.py       # Step 3: swap user faces onto AI characters
├── fraction_handler.py          # Fraction question detection & custom drawing
├── role_remapper.py             # Dynamically remap roles to match uploaded face images
├── file_handlers.py             # Load question bank topics & questions
├── pdf_generator.py             # Generate A4 PDF workbook + cleanup
├── prompt_builder.py            # Family context builder
├── transform_questions.py       # Question text normalisation
├── utils.py                     # safe_text, filename sanitisation, detect_role
├── config.py                    # API keys, model names, toggles
├── extracted_bank/              # Year 1 question bank (master categorised file)
│   └── grade_1_uk_year_1_templated_final_categories_visual_static.txt
├── question_bank/               # Raw topic-level question files
├── assets_cache/objects/        # Static object images for blueprint rendering
├── personalised_faces/          # User-uploaded face photos
├── kids_books_env/              # Python virtual environment (local)
├── .env                         # API keys (not committed)
├── .env.example                 # Environment template
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/kids_books.git
cd kids_books
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it:

- **Windows:** `venv\Scripts\activate`
- **macOS/Linux:** `source venv/bin/activate`

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

Create a `.env` file in the project root:

```
OPENROUTER_API_KEY="your_openrouter_api_key_here"
```

Get an API key from [OpenRouter](https://openrouter.ai/).

### 5. Run the app

```bash
streamlit run app.py
```

## Usage

1. Tell us about your child — name, pronouns, favourite colour, pets, hobbies, and family
2. Upload face photos for family members (optional — AI generates faces if omitted)
3. Choose a year group and topics
4. Click **Generate Personalised Workbook**
5. Download the PDF

### Face Photo Matching

Uploaded face photos are automatically matched to characters in questions. If a question mentions roles you haven't uploaded photos for, the app dynamically swaps in roles you *did* upload (and updates names and pronouns accordingly). Unmatched roles get AI-generated generic faces.

## Key Design Decisions

- **Deterministic blueprints** ensure exact object counts (no hallucinated quantities)
- **Pronoun-aware prompts** — "he" / "she" / "they" based on selection
- **Chest-up portrait framing** — characters shown from chest upward, no legs or ground
- **Face preservation mode** uses lower img2img strength to keep pasted faces intact
- **Category-based object replacement** — swap objects by category (food, toys, animals, etc.) with the child's favourites
- **Number scaling** — all question numbers are scaled to match the child's counting ability
- **Theme styles** — choose from photorealistic, storybook, cartoon, anime, or pixel art
- **Temp cleanup** runs immediately after PDF generation (not after download)
- **Self-contained fraction handling** — `fraction_handler.py` detects fraction types and draws fraction-specific visuals
- **Dynamic role remapping** — `role_remapper.py` maximises uploaded face usage by swapping question roles at runtime
