"""
question_rag
────────────
RAG-style Grade 1 question generation grounded in worksheet images.

1. Retrieve example questions from `question_bank/grade_1/` for the chosen topic
2. Generate NEW questions with an LLM (vision when an image is available)
   that follow the topic style but are answerable only from the picture.
"""

from question_rag.retriever import (
    list_question_bank_topics,
    load_topic_examples,
    retrieve_examples,
)
from question_rag.generator import generate_image_grounded_questions

__all__ = [
    "list_question_bank_topics",
    "load_topic_examples",
    "retrieve_examples",
    "generate_image_grounded_questions",
]
