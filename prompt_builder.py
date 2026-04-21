"""
Prompt building functions for question generation
"""
from langchain.prompts import ChatPromptTemplate


def get_pronouns(gender: str):
    """
    Get appropriate pronouns based on gender.
    
    Args:
        gender: "Boy", "Girl", or "Other"
    
    Returns:
        Tuple of (pronoun, possessive)
    """
    if gender == "Boy":
        return "he", "his"
    elif gender == "Girl":
        return "she", "her"
    else:
        return "they", "their"


def build_family_context(
    mother_name: str,
    father_name: str,
    grandmother_name: str,
    grandfather_name: str,
    siblings: str,
    friends: str
) -> str:
    """
    Build family context string from provided names.
    
    Args:
        Various family member names
    
    Returns:
        Formatted family context string
    """
    family_members = []
    if mother_name.strip():
        family_members.append(f"mother {mother_name}")
    if father_name.strip():
        family_members.append(f"father {father_name}")
    if grandmother_name.strip():
        family_members.append(f"grandmother {grandmother_name}")
    if grandfather_name.strip():
        family_members.append(f"grandfather {grandfather_name}")
    if siblings.strip():
        family_members.append(f"siblings {siblings}")
    if friends.strip():
        family_members.append(f"friends {friends}")
    
    return ", ".join(family_members) if family_members else "no specific family/friends mentioned"


def build_prompt(
    student_name: str,
    gender: str,
    grade: str,
    topic_context: str,
    extracted_text: str,
    num_questions: int,
    family_context: str,
    hobbies_context: str,
) -> str:
    """
    Build the complete prompt for question generation.
    
    Args:
        student_name: Student's name
        gender: Student's gender
        grade: Grade level
        topic_context: Description of topics
        extracted_text: Sample questions
        num_questions: Number of questions to generate
        family_context: Family member information
        hobbies_context: Student's hobbies and interests
    
    Returns:
        Formatted prompt string
    """
    pronoun, possessive = get_pronouns(gender)

    template = ChatPromptTemplate.from_template(
        "You are a math teacher creating personalized questions for {student_name}, "
        "a {gender_lower} in {grade}.\n\n"
        "Here are sample math problems ({topic_context}):\n"
        "{extracted_text}\n\n"
        "Generate exactly {num} NEW, CREATIVE, Simple math questions similar to the style and difficulty above. "
        "IMPORTANT: Use the student's name '{student_name}' frequently (at least once per question). "
        "You can also use '{pronoun}' and '{possessive}' but prioritize using the actual name '{student_name}'. "
        "Personalize questions naturally with:\n"
        "- Family members: {family_context}\n"
        "- Hobbies/Interests: {hobbies_context}\n\n"
        "Make the questions relevant to {possessive} interests and daily life. "
        "Ensure questions are at the {grade} level. "
        "Return only the questions, one per line, without numbering, bullets, or explanations."
    )

    prompt = template.format(
        student_name=student_name,
        gender_lower=gender.lower(),
        grade=grade,
        topic_context=topic_context,
        extracted_text=extracted_text,
        num=num_questions,
        pronoun=pronoun,
        possessive=possessive,
        family_context=family_context,
        hobbies_context=hobbies_context if hobbies_context.strip() else "general interests",
    )

    return prompt