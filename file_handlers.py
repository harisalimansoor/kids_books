"""
File handling functions for loading topics and questions
"""
import os
import streamlit as st
from config import GRADE_FOLDER_MAP

# Paths
EXTRACTED_BANK_FILE = os.path.join(
    "extracted_bank",
    "grade_1_uk_year_1_templated_final_categories_visual_static.txt",
)


def _parse_categorized_file(path):
    """
    Parses the categorized master file and returns a dictionary of {TOPIC: [questions]}.
    """
    if not os.path.exists(path):
        return {}

    categorized_data = {}
    current_topic = None

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("=== ") and line.endswith(" ==="):
                    current_topic = line.strip("= ").title()
                    categorized_data[current_topic] = []
                elif current_topic:
                    categorized_data[current_topic].append(line)
        return categorized_data
    except Exception as e:
        st.error(f"Error parsing the question bank file: {e}")
        return {}


def get_topics_for_grade(grade: str):
    """
    Get available topics for a specific grade.
    Grade 1 uses question_bank/grade_1 (RAG corpus).
    """
    if grade == "Grade 1":
        try:
            from question_rag.retriever import list_question_bank_topics
            topics = list_question_bank_topics()
            if topics:
                return topics
        except Exception:
            pass
        if os.path.exists(EXTRACTED_BANK_FILE):
            data = _parse_categorized_file(EXTRACTED_BANK_FILE)
            if data:
                return sorted(list(data.keys()))
        return []

    folder_name = GRADE_FOLDER_MAP.get(grade)
    if not folder_name:
        return []

    grade_path = os.path.join("question_bank", folder_name)
    if not os.path.exists(grade_path):
        return []

    try:
        topics = []
        for fname in os.listdir(grade_path):
            if fname.lower().endswith(".txt"):
                topics.append(fname[:-4].replace("_", " ").title())
        return sorted(topics)
    except Exception as e:
        st.error(f"Error reading topics: {e}")
        return []


def load_sample_questions(grade: str, topic: str) -> str:
    """
    Load sample questions from question_bank (Grade 1) or grade folders.
    """
    if grade == "Grade 1":
        try:
            from question_rag.retriever import load_topic_examples, resolve_topic
            resolved = resolve_topic(topic) or topic
            examples = load_topic_examples(resolved)
            if examples:
                return f"=== Topic: {resolved} ===\n" + "\n".join(examples)
        except Exception:
            pass
        if os.path.exists(EXTRACTED_BANK_FILE):
            data = _parse_categorized_file(EXTRACTED_BANK_FILE)
            if topic in data:
                return "\n".join(data[topic])
            topic_title = topic.title()
            if topic_title in data:
                return "\n".join(data[topic_title])
            return f"Error: Topic '{topic}' not found in question bank."
        return "Error: Grade 1 question bank not found."

    folder_name = GRADE_FOLDER_MAP.get(grade)
    if not folder_name:
        return f"Error: Unknown grade '{grade}'."

    topic_filename = topic.lower().replace(" ", "_") + ".txt"
    file_path = os.path.join("question_bank", folder_name, topic_filename)

    if not os.path.exists(file_path):
        return f"Error: File not found for topic '{topic}' at {file_path}"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [
                ln.strip()
                for ln in f
                if ln.strip() and not ln.strip().startswith("#")
            ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error loading questions: {e}"


def load_all_questions_for_grade(grade: str) -> str:
    """
    Load all questions for all topics in a grade.
    """
    topics = get_topics_for_grade(grade)
    blocks = []
    for t in topics:
        content = load_sample_questions(grade, t)
        if content and not content.startswith("Error"):
            blocks.append(f"=== Topic: {t} ===\n{content}\n")
    return "\n".join(blocks) if blocks else ""
