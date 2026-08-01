# 🍳 Kitchen Scenes — Personalised Educational Image Pipeline

An end-to-end framework for generating **photorealistic 2-character kitchen interaction templates**, automating **face-swapping & AI seamless face blending**, and producing high-fidelity personalized storybook scenes for early learners (aged 5–6).

---

## 📁 Directory Structure

```
kitchen_scenes/
├── README.md                      # Pipeline documentation
├── annotate_template.py           # OpenCV GUI annotation tool for face region bounding boxes
├── run_direct_food_templates.py   # Step 1: Base template generator script
├── run_direct_pipeline.py         # Step 2-3: Face swapping & AI seamless face blending
├── sample_characters/             # Sample user face photos for swapping
│   ├── new_child.jpg
│   ├── new_mother.jpg
│   ├── new_father.jpg
│   └── new_grandmother.jpg
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
    ├── ali_kitchen_baking_cookies_mother_child_blended.png
    ├── ali_kitchen_ice_cream_father_child_blended.png
    └── ali_kitchen_making_smoothies_grandmother_child_blended.png
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
│     (annotate_template.py)     │     for 'child' and 'mother_name' / 'father_name' / 'grandmother_name'
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│  3. Face Swapping (In-Memory)  │ ──► Performs top-centre face crop, per-channel brightness
│     (swap_faces)               │     normalisation & soft feathered mask pasting
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│  4. AI Seamless Face Blending  │ ──► Passes pasted image to OpenRouter AI image model to blend
│     (ai_blend_faces)           │     skin tones, lighting, and adapt joyful facial expressions
└────────────────────────────────┘
```

---

## 🎨 Detailed Step Breakdown

### Step 1: Base Template Generation (`run_direct_food_templates.py`)
Generates 1024x1024 photorealistic interaction scenes adhering to strict design rules:
- **Strict 2-Character Constraint**: Exactly 1 Child (Grade 1, 5-6yo) + 1 Adult (Mother, Father, Grandfather, Grandmother).
- **Warm Facial Expressions**: Mandated gentle, warm, genuine smiles with friendly expressive eyes.
- **Crisp Sharp Background**: Fully sharp focus throughout — NO bokeh or background blur so background objects remain countable and recognizable for learning.
- **Item Count Precision**: Exact object counts (e.g. 4 pizza slices, 4 cookies, 3 burgers, 4 smoothies) clearly visible on counters/plates.

### Step 2: Face Region Annotation (`annotate_template.py`)
Launches a simplified OpenCV GUI tool focused strictly on face bounding box selection. Real pixel coordinates are scaled and saved directly to the template's `.json` metadata file:
```json
{
  "template_id": "kitchen_making_smoothies_grandmother_child",
  "favorite_food": "Smoothies",
  "face_slots": ["child", "grandmother_name"],
  "face_regions": [
    { "role": "child", "x": 240, "y": 284, "w": 223, "h": 223 },
    { "role": "grandmother_name", "x": 489, "y": 80, "w": 244, "h": 306 }
  ],
  "annotation_complete": true
}
```

### Step 3: Precise Face Swapping (`swap_faces`)
1. **Top-Centre Crop**: Extracts a square crop from the user photo focusing on head and forehead.
2. **Luminance Normalization**: Normalizes RGB channels to match ambient lighting of the target template region.
3. **Feathered Elliptical Mask**: Applies smooth Gaussian blur along mask edges and pastes face in-memory.

### Step 4: AI Face Blending & Expression Adaptation (`ai_blend_faces`)
Sends the face-pasted image in-memory to `openai/gpt-5.4-image-2` via OpenRouter to seamlessly blend skin tone, lighting, and hair transitions while preserving:
- **Exact Head Pose & Face Angle** of the template character.
- **Joyful Expression Adaptation**: Adapts the facial expressions of the new faces to match the huge, laughing, candid, warm smiles of the template.
- **Kitchen Scene & Food Items Preservation**.

---

## 🚀 How to Run the Pipeline

### 1. Annotate Face Regions for a Template
Run the OpenCV GUI tool to drag bounding boxes for character faces:
```bash
python kitchen_scenes/annotate_template.py kitchen_scenes/direct_food_templates/kitchen_making_smoothies_grandmother_child.png
```
- Drag a box over each character face slot (e.g., `child`, `mother_name`, `grandmother_name`).
- Press **ENTER** or **SPACE** to confirm each box (or `C` to skip).
- Coordinates save automatically to the `.json` file.

### 2. Configure Profile in `run_direct_pipeline.py`
Open `kitchen_scenes/run_direct_pipeline.py` and set `USER_SETTINGS`:
```python
USER_SETTINGS = {
    "child_name": "Ali",
    "child_age": 6,
    "grade": 1,
    "favorite_food": "Smoothies",   # Matches food in direct_food_templates JSON
    "mother_name": "Sara",
    "father_name": "Ahmed",
    "grandmother_name": "Fatima",
    "child_photo": USER_PHOTOS_DIR / "new_child.jpg",
    "adult_photo": USER_PHOTOS_DIR / "new_grandmother.jpg",  # Used for adult role slot
}
```

### 3. Run the Face Swapping & AI Blending Pipeline
Execute the main pipeline:
```bash
python -m kitchen_scenes.run_direct_pipeline
```
- Automatically selects the correct template based on `favorite_food`.
- Swaps faces in-memory and sends the image for AI blending.
- Saves the final blended image to `kitchen_scenes/pipeline_output/`.

### 4. Generate New Base Templates (Optional)
To generate new food/activity templates:
```bash
python -m kitchen_scenes.run_direct_food_templates
```

---

## 🔑 Environment Requirements
Ensure `.env` in the root directory contains your active OpenRouter API key:
```env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx
```
