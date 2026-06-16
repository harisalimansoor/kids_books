# `app.py` — Main Orchestrator (Streamlit UI)

## Purpose
Entry point for the Streamlit app. Provides the user interface for entering student info, uploading face photos, selecting grade/topics, and generating a personalised PDF workbook via the Blueprint-to-Render pipeline.

## Execution Model
The app uses **`st.session_state.pipeline`** to track multi-step generation through phases. `st.rerun()` advances the phase.

## Pipeline Phases

| Phase | Action |
|---|---|
| **Form** | User fills name, gender, siblings, parents, grandparents, hobbies, face uploads, grade, topics, question count |
| **`"blueprint"`** | For each question, calls `generate_blueprint(q_raw)` to create a geometric layout with exact object counts. Builds face maps, generates `_build_prompt` / `_build_text_prompt` with gender. |
| **`"rendering"`** | For each question, calls `ai_render()` with the blueprint, metadata, and prompt. If faces were uploaded, runs `swap_faces()` post-render. Saves `temp_img_{idx}_{ts}.jpg`. |
| **`"pdf"`** | Calls `generate_pdf()` with all synced questions + image paths. Then `cleanup_temp_images()`. |
| **`"complete"`** | Shows download button and "Start Over" button. |

## Key Functions (module-level)

### `map_hobby_to_object(hobby_text: str) -> str | None`
Maps user's hobby keywords to a concrete object keyword (e.g. "football" → "ball"). Returns `_HOBBY_FALLBACK` ("sticker") on no match.

### `_pluralize(word: str) -> str`
Simple English pluralizer with overrides for "toy car" → "toy cars", "teddy bear" → "teddy bears".

### `replace_objects_in_text(text: str, hobby_obj: str) -> str`
Replaces any known `OBJECT_KEYWORDS` in the question text with the user's hobby object, matching plurality (e.g. "3 apples" → "3 balls" if hobby is "ball"). Skips container/furniture words defined in `_SKIP_OBJECTS`.

## Data Structures

- `_HOBBY_MAP` — 30+ keyword-lists mapped to object names
- `_SKIP_OBJECTS` — frozenset of container/furniture words that should never be replaced
- `pipeline` — dict with keys: `phase`, `questions_data`, `questions`, `synced_questions`, `gender`, `student_name`, `grade`, `topic_header_text`, `include_images`, `saved_face_paths`, `image_paths`, `blueprints_data`, `pdf_bytes`

## Dependencies
- `streamlit`, `PIL`, `os`, `time`, `re`, `itertools`, `io`
- `file_handlers` — `get_topics_for_grade`, `load_sample_questions`, `load_all_questions_for_grade`
- `prompt_builder` — `build_family_context`
- `pdf_generator` — `generate_pdf`, `cleanup_temp_images`
- `utils` — `create_safe_filename`, `detect_role`
- `blueprint_generator` — `generate_blueprint`, `OBJECT_KEYWORDS`
- `ai_renderer` — `render_image`, `_build_prompt`, `_build_text_prompt`
- `face_swap_processor` — `swap_faces`
