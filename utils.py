"""
Utility functions
"""


def safe_text(text: str) -> str:
    """
    Convert text to Latin-1 encoding for PDF compatibility.
    
    Args:
        text: Input text
    
    Returns:
        Latin-1 encoded text
    """
    return text.encode("latin-1", "ignore").decode("latin-1")


def clean_generated_questions(generated_text: str, num_questions: int) -> list:
    """
    Clean and parse generated questions from API response.
    
    Args:
        generated_text: Raw text from API
        num_questions: Expected number of questions
    
    Returns:
        List of cleaned question strings
    """
    raw_lines = [
        ln.strip() 
        for ln in generated_text.split("\n") 
        if ln.strip() and len(ln.split()) > 2
    ]
    
    cleaned = []
    for item in raw_lines:
        # Remove leading bullets, dashes, etc.
        item = item.lstrip(" -•\t")
        
        # Remove leading numbers
        if len(item) > 2 and item[0].isdigit():
            first_space = item.find(" ")
            if 0 <= first_space <= 4:
                item = item[first_space + 1:].strip()
        
        cleaned.append(item)
    
    return cleaned[:num_questions]


def create_safe_filename(student_name: str) -> str:
    """
    Create a safe filename from student name.
    
    Args:
        student_name: Student's name
    
    Returns:
        Sanitized filename
    """
    safe_name = "".join(
        c for c in student_name 
        if c.isalnum() or c in (" ", "_")
    ).strip().replace(" ", "_")
    
    return f"math_workbook_for_{safe_name}.pdf"


def detect_role(question_text: str):
    """
    Detects which family role is mentioned in the question.
    """
    text_lower = question_text.lower()
    if "{mother_name}" in text_lower: return "mother"
    if "{father_name}" in text_lower: return "father"
    if "{sibling_name}" in text_lower: return "sibling"
    if "{grandmother_name}" in text_lower: return "grandmother"
    if "{grandfather_name}" in text_lower: return "grandfather"
    if "{user_name}" in text_lower or "you have" in text_lower: return "user"
    return None