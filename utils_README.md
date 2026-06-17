# `utils.py` — Utility Functions

## Purpose
Provides small, reusable utility functions used across the codebase.

## Functions

### `safe_text(text: str) -> str`
Encodes text to Latin-1, ignoring characters outside this range, then decodes back.
- **Used by**: `pdf_generator.py` to prevent PDF encoding errors with names containing non-Latin-1 characters.

### `clean_generated_questions(generated_text: str, num_questions: int) -> list[str]`
Parses raw text (typically from an LLM response) into a list of cleaned question strings.
- Splits by newlines, filters empty/short lines
- Strips leading bullets (`- •\t`) and leading numbering (e.g. "1. ", "2. ")
- Returns up to `num_questions` items
- **Note**: This function exists but is **not actively called** in the current pipeline (questions are selected from the pre-existing bank, not LLM-generated).

### `create_safe_filename(student_name: str) -> str`
Creates a filesystem-safe PDF filename from the student's name.
- Keeps only alphanumeric characters, spaces, and underscores
- Replaces spaces with underscores
- Returns: `math_workbook_for_{safe_name}.pdf`

### `detect_role(question_text: str) -> str | None`
Detects which family role is mentioned in a raw question by checking for `{role_name}` placeholder presence.
- Returns: `"mother"`, `"father"`, `"sibling"`, `"grandmother"`, `"grandfather"`, `"user"`, or `None`
- **Note**: This function exists but is **not actively called** in the current pipeline (face assignment is done via blueprint metadata L-R matching instead).

## Dependencies
- None (pure Python standard library)
