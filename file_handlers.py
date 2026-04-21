"""
File handling functions for loading topics and questions
"""
import os
import streamlit as st
from config import GRADE_FOLDER_MAP


def get_topics_for_grade(grade: str):
    """
    Get available topics for a specific grade.
    
    Args:
        grade: Grade level (e.g., "Grade 1")
    
    Returns:
        List of topic names
    """
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
    Load sample questions from a topic file.
    
    Args:
        grade: Grade level
        topic: Topic name
    
    Returns:
        Content of the topic file or error message
    """
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
    
    Args:
        grade: Grade level
    
    Returns:
        Combined content of all topic files
    """
    topics = get_topics_for_grade(grade)
    blocks = []
    for t in topics:
        content = load_sample_questions(grade, t)
        if content and not content.startswith("Error"):
            blocks.append(f"=== Topic: {t} ===\n{content}\n")
    return "\n".join(blocks) if blocks else ""