# `file_handlers.py` — Topic & Question Loading

## Purpose
Handles loading of question bank data from the filesystem. Supports the master categorized file format (Grade 1) and legacy per-topic file format (other grades).

## Data Source

### `EXTRACTED_BANK_FILE`
Path: `extracted_bank/grade_1_uk_year_1_templated_final_categories_visual.txt`

This is the single master file for Grade 1, containing all topics with `=== TOPIC NAME ===` headers.

## Internal Function

### `_parse_categorized_file(path) -> dict[str, list[str]]`
Parses the master categorized file:
- Lines starting with `=== ` and ending with ` ===` become topic headers
- Lines following a header are collected as questions for that topic
- Returns `{topic_title: [question_lines]}`

## Public API

### `get_topics_for_grade(grade: str) -> list[str]`
Returns sorted list of topic names for a grade:
- **Grade 1**: Parses `EXTRACTED_BANK_FILE` and returns topic keys (titles)
- **Other grades**: Reads `.txt` files from `question_bank/grade_{n}/` folder, strips `.txt` extension, replaces `_` with spaces, title-cases

### `load_sample_questions(grade: str, topic: str) -> str`
Returns questions for a specific topic as a newline-separated string:
- **Grade 1**: Looks up topic in parsed `EXTRACTED_BANK_FILE` (case-insensitive via title-case fallback)
- **Other grades**: Reads `question_bank/grade_{n}/{topic}.txt`, skipping blank lines and `#` comment lines
- Returns `"Error: ..."` string on failure

### `load_all_questions_for_grade(grade: str) -> str`
Loads all topics for a grade into a single string with `=== Topic: {t} ===` separators:
- **Grade 1**: Iterates all topics from `EXTRACTED_BANK_FILE`
- **Other grades**: Iterates `get_topics_for_grade()` and calls `load_sample_questions()` for each

## Dependencies
- `os`, `streamlit`
- `config` — `GRADE_FOLDER_MAP`
