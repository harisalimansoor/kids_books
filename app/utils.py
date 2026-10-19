"""
Utility functions
"""


def safe_text(text: str) -> str:
    """
    Convert text to Latin-1 encoding for PDF compatibility.
    Normalizes common Unicode punctuation before encoding to avoid silent drops.
    """
    if not text:
        return ""
    s = str(text)
    replacements = {
        "—": "-",
        "–": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "…": "...",
        "\u2022": "*",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return s.encode("latin-1", "ignore").decode("latin-1")


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


def capitalize_you(text: str) -> str:
    """Capitalize 'you' to 'You' only at sentence starts."""
    import re
    text = re.sub(r'^you\b', 'You', text)
    text = re.sub(r'([.!?])\s+you\b', r'\1 You', text)
    return text


def fix_you_verb_conjugation(text: str) -> str:
    """Fix verb conjugation when '{user_name}' has been replaced with 'You'."""
    import re
    fixes = [
        (r'\bYou\s+has\b', 'You have'),
        (r'\byou\s+has\b', 'you have'),
        (r'\bYou\s+is\b', 'You are'),
        (r'\byou\s+is\b', 'you are'),
        (r'\bYou\s+does\b', 'You do'),
        (r'\byou\s+does\b', 'you do'),
        (r'\bdoes\s+You\b', 'do You'),
        (r'\bdoes\s+you\b', 'do you'),
    ]
    for pattern, replacement in fixes:
        text = re.sub(pattern, replacement, text)
    return text


def fix_verb_for_pronoun(text: str, pronoun: str) -> str:
    """Fix verb conjugation when '{user_name}' has been replaced with he/she/they."""
    import re
    if pronoun in ("he", "she"):
        fixes = [
            (rf'\b{pronoun}\s+have\b', f'{pronoun} has'),
            (rf'\b{pronoun}\s+do\b', f'{pronoun} does'),
            (rf'\b{pronoun}\s+are\b', f'{pronoun} is'),
            (rf'\bdo\s+{pronoun}\b', f'does {pronoun}'),
            (rf'\bhave\s+{pronoun}\b', f'has {pronoun}'),
            (rf'{pronoun.capitalize()}\s+have\b', f'{pronoun.capitalize()} has'),
            (rf'{pronoun.capitalize()}\s+do\b', f'{pronoun.capitalize()} does'),
            (rf'{pronoun.capitalize()}\s+are\b', f'{pronoun.capitalize()} is'),
            (rf'\bDo\s+{pronoun.capitalize()}\b', f'Does {pronoun.capitalize()}'),
        ]
    elif pronoun == "they":
        fixes = [
            (r'\bthey\s+has\b', 'they have'),
            (r'\bthey\s+does\b', 'they do'),
            (r'\bthey\s+is\b', 'they are'),
            (r'\bdoes\s+they\b', 'do they'),
            (r'\bhas\s+they\b', 'have they'),
            (r'\bThey\s+has\b', 'They have'),
            (r'\bThey\s+does\b', 'They do'),
            (r'\bThey\s+is\b', 'They are'),
            (r'\bDoes\s+They\b', 'Do they'),
        ]
    else:
        return text
    for pattern, replacement in fixes:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def capitalize_pronoun(text: str, pronoun: str) -> str:
    """Capitalize pronoun (he/she/they/you) at sentence starts."""
    import re
    cap = pronoun.capitalize()
    text = re.sub(f'^{pronoun}\\b', cap, text)
    text = re.sub(f'([.!?])\\s+{pronoun}\\b', rf'\1 {cap}', text)
    return text


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