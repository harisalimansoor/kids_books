"""
Configuration and environment setup
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys
GROK_API_KEY = os.getenv("GROK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Grade folder mapping
GRADE_FOLDER_MAP = {
    "Grade 1": "grade_1",
    "Grade 2": "grade_2",
    "Grade 3": "grade_3",
    "Grade 4": "grade_4",
    "Grade 5": "grade_5",
}

# API Configuration
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash-lite-preview-09-2025"
OPENAI_TEXT_MODEL = "gpt-4o-mini"
OPENROUTER_MODEL = "google/gemma-2-9b-it:free"  # Good free model on OpenRouter
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Toggles for switching between providers
# Order of priority: 1. Groq, 2. OpenRouter, 3. OpenAI
USE_OPENROUTER_FOR_TEXT = True
USE_OPENAI_FOR_TEXT = False

# Image generation settings
IMAGE_STYLES = {
    "cartoon": "colorful cartoon style",
    "simple": "simple flat design style",
    "watercolor": "watercolor painting style",
    "sticker": "cute sticker style",
    "playful": "playful and vibrant style",
    "educational": "educational textbook style"
}

# Image generation models (for future use when credits available)
IMAGE_MODEL_PAID = "black-forest-labs/flux.2-max"
IMAGE_MODEL_FREE = "stabilityai/stable-diffusion-3-medium"

# Use static assets by default (no API credits needed)
# Set to False and ensure credits to use AI generation
USE_STATIC_ASSETS = False
USE_AI_ASSETS = False  # Alias for clarity

# Costs (in USD)
IMAGE_COST = {
    "standard": 0.04,
    "hd": 0.08
}