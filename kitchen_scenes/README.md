# 🍳 Kitchen Scenes — Personalised Educational Image & Quiz Pipeline

An end-to-end framework for generating **photorealistic 2-character kitchen interaction templates**, automating **face-swapping & AI seamless face blending**, and generating **aligned Grade 1 educational question sets** for early learners (aged 5–6).

---

## 📁 Directory Structure

```
kitchen_scenes/
├── README.md                      # Pipeline documentation
├── annotate_template.py           # OpenCV GUI annotation tool for face region bounding boxes
├── run_direct_food_templates.py   # Base template generator script
├── run_direct_pipeline.py         # End-to-End Personalisation & Quiz Pipeline
├── sample_characters/             # Sample user and relation face photos for swapping
│   ├── new_child.jpg
│   ├── new_mother.jpg
│   ├── new_father.jpg
│   ├── new_grandmother.jpg
│   └── grandfather.jpg
├── direct_food_templates/         # Base interaction templates (.png + .json metadata)
│   ├── kitchen_pizza_mother_child.png / .json
│   ├── kitchen_baking_cookies_mother_child.png / .json
│   ├── kitchen_ice_cream_father_child.png / .json
│   ├── kitchen_apples_mother_child.png / .json
│   ├── kitchen_burgers_father_child.png / .json
│   ├── kitchen_making_chocolates_father_child.png / .json
│   ├── kitchen_pancake_breakfast_grandfather_child.png / .json
│   ├── kitchen_making_smoothies_grandmother_child.png / .json
│   ├── kitchen_cupcakes_mother_child.png / .json
│   ├── kitchen_noodles_father_child.png / .json
│   └── kitchen_pasta_mother_child.png / .json
└── pipeline_output/               # Generated output artifacts
    ├── ali_kitchen_making_smoothies_grandmother_child_blended.png
    ├── ali_kitchen_making_smoothies_grandmother_child_questions.json
    ├── ali_kitchen_baking_cookies_mother_child_blended.png
    └── ali_kitchen_baking_cookies_mother_child_questions.json
```

---

## ⚙️ Architectural Workflow

```
┌──────────────────────────────────────────────┐
│  1. User Profile Input                       │ ──► Child name, age, grade, favourite food,
│     (run_direct_pipeline)                    │     and relation photos (child, mother, father, etc.)
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  2. Template Search & Verification           │ ──► Searches direct_food_templates library for food match.
│     (find_template_for_food)                 │     If not found, lists available library templates.
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  3. Dynamic Face Swapping                    │ ──► Performs top-centre crop, brightness matching,
│     (swap_faces)                             │     and soft mask placement for required relation slots.
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  4. AI Seamless Blending & Expressions       │ ──► Passes pasted image to OpenRouter image model (`gpt-5.4-image-2`)
│     (ai_blend_faces)                         │     to harmonise skin tones and adapt joyful facial expressions.
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  5. Vision-Grounded Quiz Generation          │ ──► GPT-4o Vision inspects blended image to generate 5
│     (generate_questions)                     │     personalised Grade 1 questions (Counting, Family, Action).
└──────────────────────────────────────────────┘
```

---

## 🎨 Detailed Step Breakdown

### Step 1: User Profile Input & Template Lookup
The user provides their child's profile and relation photos:
- `child_name`: Child's first name (e.g. "Ali")
- `favorite_food`: Child's favourite food (e.g. "Smoothies", "Cookies", "Pizza", "Ice cream")
- `relation_photos`: Child photo + relation photos (`mother_photo`, `father_photo`, `grandmother_photo`, etc.)

The pipeline searches `direct_food_templates/*.json` for a matching `favorite_food`.

### Step 2: Face Region Annotation (`annotate_template.py`)
If a newly generated template needs face region bounding boxes:
```bash
python kitchen_scenes/annotate_template.py kitchen_scenes/direct_food_templates/kitchen_making_smoothies_grandmother_child.png
```

### Step 3: Precise Face Swapping (`swap_faces`)
1. **Top-Centre Crop**: Extracts a square crop from the user photo focusing on head and forehead.
2. **Luminance Normalization**: Normalizes RGB channels to match ambient lighting of target template region.
3. **Soft Masking**: Pastes the face in-memory onto target coordinates.

### Step 4: AI Face Blending & Expression Adaptation (`ai_blend_faces`)
Sends the face-pasted image in-memory to `openai/gpt-5.4-image-2` via OpenRouter to seamlessly blend skin tone, lighting, and hair transitions while preserving identity and adapting expressions to match the joyful scene.

### Step 5: Educational Quiz Generation (`generate_questions`)
GPT-4o Vision analyzes the final blended image to generate a personalized 5-question Grade 1 quiz:
1. **Counting**: *"How many smoothies can you count, Ali?"*
2. **Family Recognition**: *"Who is with Ali in the kitchen?"*
3. **Action Recognition**: *"What are Ali and his Grandmother doing?"*
4. **Comparison**: *"Are there more than 2 smoothies in the picture?"*
5. **Favourite Food**: *"What is Ali's favourite food in the picture?"*

---

## 🚀 How to Run

### 1. Run Pipeline for any Food & Child Name
```bash
python -m kitchen_scenes.run_direct_pipeline --food Smoothies --name Ali
```

Or for Cookies:
```bash
python -m kitchen_scenes.run_direct_pipeline --food Cookies --name Ali
```

### 2. Run Programmatically in Python
```python
from kitchen_scenes.run_direct_pipeline import run_pipeline, USER_PHOTOS_DIR

user_profile = {
    "child_name": "Ali",
    "child_age": 6,
    "grade": 1,
    "favorite_food": "Smoothies",
    "child_photo": USER_PHOTOS_DIR / "new_child.jpg",
    "grandmother_photo": USER_PHOTOS_DIR / "new_grandmother.jpg",
}

result = run_pipeline(user_profile)
# result contains:
# - result["final_image"]      -> Path to blended PNG
# - result["questions_json"]   -> Path to questions JSON
# - result["questions"]        -> List of 5 generated Grade 1 questions
```

---

## 🔑 Environment Requirements
Ensure `.env` in the root directory contains your active OpenRouter API key:
```env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx
```
