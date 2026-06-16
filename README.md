# Personalized Math Question Generator

Welcome to the **Personalized Math Question Generator**! A Streamlit web app that creates customized math workbooks for kids — with AI-generated photorealistic illustrations, face swapping, and exact object counting.

## Pipeline Overview

```
Question Bank → Blueprint (geometric layout) → AI Render (GPT-5.4 Image 2) → Face Swap → PDF
```

1. **Blueprint Generator** — Parses the question, detects roles & object counts, draws a deterministic 1024×1024 geometric layout (blue bodies, green heads, red objects).
2. **AI Renderer** — Sends the blueprint to OpenRouter's `openai/gpt-5.4-image-2` for photorealistic conversion. Falls back to text2img if img2img fails.
3. **Face Swap** — Uses insightface to swap user-uploaded face photos onto AI-generated characters (left-to-right matching).
4. **PDF Generator** — Assembles A4 workbook with questions + images, then cleans up temp files.

## Tech Stack

- **Python** + **Streamlit** (UI)
- **OpenRouter** — `openai/gpt-5.4-image-2` for image generation
- **Insightface** — face detection & swapping (InSwapper)
- **FPDF** — PDF generation
- **Pillow** — image manipulation
- **python-dotenv** — API key management

## Project Structure

```
kids_books/
├── app.py                       # Streamlit orchestrator (UI + pipeline phases)
├── blueprint_generator.py       # Step 1: parse question → geometric blueprint
├── ai_renderer.py               # Step 2: blueprint → photorealistic AI render
├── face_swap_processor.py       # Step 3: swap user faces onto AI characters
├── file_handlers.py             # Load question bank topics & questions
├── pdf_generator.py             # Generate A4 PDF workbook + cleanup
├── prompt_builder.py            # Legacy: family context builder
├── utils.py                     # safe_text, filename sanitization, detect_role
├── config.py                    # API keys, model names, pricing, toggles
├── extracted_bank/              # Grade 1 question bank (master categorized file)
├── personalized_faces/          # User-uploaded face photos
│
├── config_README.md             # Per-module documentation
├── app_README.md
├── blueprint_generator_README.md
├── ai_renderer_README.md
├── face_swap_processor_README.md
├── file_handlers_README.md
├── pdf_generator_README.md
├── prompt_builder_README.md
├── utils_README.md
└── requirements.txt
```

## Installation

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Create `.env`:
```
OPENROUTER_API_KEY="your_key_here"
```

## Usage

```bash
streamlit run app.py
```

1. Enter student name, gender, family names, hobbies
2. Upload face photos (optional)
3. Select grade & topics
4. Click **Generate Personalized Workbook**
5. Download PDF

## Key Design Decisions

- **Deterministic blueprints** ensure exact object counts (no hallucinated quantities)
- **Gender-aware prompts** — "young boy" / "young girl" based on selection
- **Face preservation mode** uses lower img2img strength (0.4) to keep pasted faces intact
- **Hobby object replacement** swaps generic objects in questions with the child's interest (e.g. "ball" for football fans)
- **Temp cleanup** runs immediately after PDF generation (not after download)
