# new_pipeline

Bank-first question pipeline for Grade 1 worksheets.

```text
new_pipeline/
  Question clusters for grade 1/   # topic question banks (.txt)
  question_templates/              # visual stems (question + image + meta)
  stem_pipeline.py                 # select / fill / personalize helpers
  newapp.py                        # Streamlit UI for this strategy
```

## Strategy

1. Pre-build role-locked stems (mother body ↔ `{mother_name}`, etc.).
2. At workbook time: pick **ready** stems whose adult role has an uploaded face.
3. Fill name placeholders from the family profile.
4. Paste faces + optional soft-cartoon finish (`question_templates/personalize.py`).
5. Use `answer.correct` / `answer.options` from `meta.json` — never re-ask an LLM for the key.

## Run the app

From the repo root:

```bash
streamlit run new_pipeline/newapp.py
```
