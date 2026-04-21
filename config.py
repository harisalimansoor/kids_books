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
DEFAULT_MODEL = "llama-3.1-8b-instant"

# Image generation settings
IMAGE_STYLES = {
    "cartoon": "colorful cartoon style",
    "simple": "simple flat design style",
    "watercolor": "watercolor painting style",
    "sticker": "cute sticker style",
    "playful": "playful and vibrant style",
    "educational": "educational textbook style"
}

# Costs (in USD)
IMAGE_COST = {
    "standard": 0.04,
    "hd": 0.08
}