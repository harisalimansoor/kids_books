# `config.py` — Configuration & Environment Setup

## Purpose
Central configuration module. Loads API keys from `.env` and defines all app-wide constants (providers, models, pricing, toggles, grade folder mappings, image styles).

## Key Constants

| Constant | Value / Purpose |
|---|---|
| `GROK_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY` | Loaded from `.env` |
| `GRADE_FOLDER_MAP` | Maps "Grade 1"–"Grade 5" to folder names like `grade_1` |
| `GROQ_API_URL` | `https://api.groq.com/openai/v1/chat/completions` |
| `DEFAULT_MODEL` | `google/gemini-2.5-flash-lite-preview-09-2025` (text fallback) |
| `OPENAI_TEXT_MODEL` | `gpt-4o-mini` |
| `OPENROUTER_MODEL` | `google/gemma-2-9b-it:free` |
| `OPENROUTER_URL` | `https://openrouter.ai/api/v1/chat/completions` |
| `USE_OPENROUTER_FOR_TEXT` | `True` — primary text provider |
| `USE_OPENAI_FOR_TEXT` | `False` |
| `IMAGE_STYLES` | Dict mapping style names (cartoon, watercolor, etc.) to descriptions |
| `IMAGE_MODEL_PAID` | `black-forest-labs/flux.2-max` (unused) |
| `IMAGE_MODEL_FREE` | `stabilityai/stable-diffusion-3-medium` (unused) |
| `USE_STATIC_ASSETS` / `USE_AI_ASSETS` | Both `False` — no static/legacy asset mode |
| `IMAGE_COST` | `standard: $0.04`, `hd: $0.08` (informational) |

## Dependencies
- `python-dotenv` for `.env` loading
- `os` standard library

## Flow
1. `load_dotenv()` reads `.env` → populates `os.environ`
2. Constants are exported for use by other modules (`app.py`, `ai_renderer.py`, `file_handlers.py`)
