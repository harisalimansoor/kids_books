# 🍳 Kitchen Scenes — Personalised Educational Image & Quiz Pipeline

An end-to-end framework for generating **photorealistic 2-character kitchen interaction templates**, automating **face-swapping & AI seamless face blending**, and generating **aligned Grade 1 educational question sets** for early learners (aged 5–6).

---

## 📁 Directory Structure

```
kitchen_scenes/
├── README.md                      # Pipeline documentation
├── annotate_template.py           # GUI Annotation Tool for face region bounding boxes
├── run_direct_food_templates.py   # Step 1: Template Generator script
├── run_direct_pipeline.py         # Step 2-4: Face Swap, AI Blend & Quiz Generator
├── sample_characters/             # Sample user face photos for swapping
│   ├── new_child.jpg
│   ├── new_mother.jpg
│   ├── grade1_child.jpg
│   ├── mother.jpg
│   └── grandfather.jpg
├── direct_food_templates/         # Base interaction templates (.png + .json metadata)
│   ├── kitchen_pizza_mother_child.png / .json
│   ├── kitchen_baking_cookies_mother_child.png / .json
│   ├── kitchen_ice_cream_father_child.png / .json
│   ├── kitchen_apples_mother_child.png / .json
│   ├── kitchen_burgers_father_child.png / .json
│   ├── kitchen_making_chocolates_father_child.png / .json
│   ├── kitchen_pancake_breakfast_grandfather_child.png / .json
│   └── kitchen_making_smoothies_grandmother_child.png / .json
└── pipeline_output/               # Generated output artifacts
    ├── ali_kitchen_baking_cookies_mother_child_swapped.png
    ├── ali_kitchen_baking_cookies_mother_child_blended.png
    └── ali_kitchen_baking_cookies_mother_child_questions.json
```

---

## ⚙️ Architectural Workflow

```
┌────────────────────────────────┐
│  1. Template Generation        │ ──► Generates 2-character food interaction scenes (1 Child + 1 Adult)
│     (run_direct_food_templates)│     with sharp backgrounds & warm expressions (.png + .json)
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│  2. Face Annotation            │ ──► Annotates face_regions bounding boxes in template JSON
│     (x, y, width, height)      │     for 'child' and 'mother_name' / 'father_name'
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│  3. Face Swapping & Crop       │ ──► Performs top-centre face crop, per-channel brightness
│     (swap_faces)               │     normalisation & soft feathered mask pasting
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│  4. AI Seamless Face Blending  │ ──► Passes pasted image to OpenRouter image model to blend
│     (ai_blend_faces)           │     skin tones, lighting & edges while PRESERVING face angles
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│  5. Vision Quiz Generation     │ ──► GPT-4o analyzes final scene & generates 5 personalised
│     (generate_questions)       │     Grade 1 questions (Counting, Family, Action, Food)
└────────────────────────────────┘
```

---

## 🎨 Detailed Step Breakdown

### Step 1: Base Template Generation (`run_direct_food_templates.py`)
Generates 1024x1024 photorealistic interaction scenes adhering to strict design rules:
- **Strict 2-Character Constraint**: Exactly 1 Child (Grade 1, 5-6yo) + 1 Adult (Mother, Father, Grandfather, Grandmother).
- **Warm Facial Expressions**: Mandated gentle, warm, genuine smiles with friendly expressive eyes.
- **Crisp Sharp Background**: Fully sharp focus throughout — NO bokeh or background blur so background objects remain countable and recognizable for learning.
- **Item Count Precision**: Exact object counts (e.g. 4 pizza slices, 4 cookies, 3 burgers) clearly visible on counters/plates.

### Step 2: Face Region Annotation (`direct_food_templates/*.json`)
Metadata files store template properties and face bounding boxes:
```json
{
  "template_id": "kitchen_baking_cookies_mother_child",
  "favorite_food": "Cookies",
  "face_slots": ["child", "mother_name"],
  "face_regions": [
    { "role": "child", "x": 246, "y": 314, "w": 159, "h": 200 },
    { "role": "mother_name", "x": 508, "y": 213, "w": 150, "h": 219 }
  ],
  "objects": [{ "type": "cookies", "count": 4 }]
}
```

### Step 3: Precise Face Swapping (`swap_faces`)
1. **Top-Centre Crop**: Extracts a square crop from the user photo focusing on head and forehead.
2. **Luminance Matching**: Normalises RGB channels to match ambient lighting of the template region.
3. **Feathered Elliptical Mask**: Applies smooth Gaussian blur along mask edges.

### Step 4: AI Face Blending (`ai_blend_faces`)
Sends the face-pasted image to `gpt-5.4-image-2` via OpenRouter to seamlessly blend skin tone, lighting, and hair transitions while preserving:
- **Exact Head Pose & Face Angle** of the template character.
- **Natural Warm Expressions & Eye Gaze**.
- **Kitchen Scene & Food Items**.

### Step 5: Educational Quiz Generation (`generate_questions`)
GPT-4o inspects the final scene and creates a personalized 5-question Grade 1 quiz:
1. **Counting**: *"How many cookies can you count?"*
2. **Family Recognition**: *"Who is with Ali in the kitchen?"*
3. **Action Recognition**: *"What are Ali and his Mother doing?"*
4. **Comparison**: *"Are there more than 2 cookies in the picture?"*
5. **Favourite Food**: *"What is Ali's favourite food in the picture?"*

---

## 🚀 How to Run

### 1. Execute Full End-to-End Pipeline
Runs face swapping, AI blending, and question generation for the active child profile:
```bash
python -m kitchen_scenes.run_direct_pipeline
```

### 2. Annotate Face Regions for a Template
Launches the OpenCV GUI tool to drag bounding boxes for character faces and save coordinates to JSON:
```bash
python kitchen_scenes/annotate_template.py kitchen_scenes/direct_food_templates/kitchen_baking_cookies_mother_child.png
```

### 3. Generate Additional Food Templates
Generates any missing food/activity templates in `kitchen_scenes/direct_food_templates/`:
```bash
python -m kitchen_scenes.run_direct_food_templates
```

---

## 🔑 Environment Requirements
Ensure `.env` in the root directory contains your active OpenRouter API key:
```env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx
```
