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
2. Tag stems with `interests.foods` / `interests.hobbies` (and/or `visual_groups.object_id`).
3. At workbook time: pick **ready** stems whose adult role has an uploaded face.
4. **Prefer** stems matching the child's favourite foods/hobbies; fill remaining slots from other ready stems.
5. Fill name placeholders from the family profile.
6. Paste faces + seamless AI blend (`question_templates/personalize.py`).
7. Use `answer.correct` / `answer.options` from `meta.json` — never re-ask an LLM for the key.

As you add templates for more foods and hobbies, selection automatically prefers them when the user picks those interests.

## Run the app

From the repo root:

```bash
streamlit run new_pipeline/newapp.py
```
