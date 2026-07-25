# Template Generation Framework

Welcome to the **Template Generation Framework**. This module is a scalable, modular dataset generation architecture designed to automatically produce tens of thousands of reusable, high-quality visual templates for educational AI applications.

## 🌟 Philosophy: Visual Clusters over Single Questions

Instead of manually crafting one image for every single question (which doesn't scale), this framework generates **Reusable Visual Scenes**. 

A single generated scene (e.g., a grandfather and child playing in the park with 5 objects) serves as the foundation for dozens of different questions:
- *Count the objects.*
- *Are there more objects or more people?*
- *Who is sitting on the left?*
- *What is the child doing?*

By generating robust metadata with each image, the downstream Question Generation LLM knows exactly what questions can be asked about this specific template.

---

## 🏗️ Architecture

The framework is highly modular, avoiding hardcoded prompts. It automatically combines definitions into robust, structured prompts sent to the image generation AI.

### File Structure
- **`config.py`**: Defines the fundamental data models (`Scene`, `FamilyConfig`, `Activity`, etc.) using Pydantic/Dataclasses.
- **`definitions.py`**: The content library. This is where you define your environments, character configurations, activities, and camera angles.
- **`prompt_builder.py`**: Dynamically constructs the strict prompt required for the AI to generate the template correctly (enforcing age limits, style, and placeholder layout).
- **`metadata_builder.py`**: Generates rich, nested JSON metadata for each generated image, tagging it with semantic data like `supported_question_types`, `family` members, and the initialized `objects` array.
- **`generator.py`**: The core execution engine. Handles the API calls to OpenRouter, processes base64/URL images, and writes the final `.png` and `.json` pairs to disk.
- **`run.py`**: The entry point. Multiplies the different dataset variables together to generate a queued cluster of templates.
- **`generated/`**: The output directory where clusters are saved (grouped by scene).

---

## 🚀 How to Use

### 1. Generating a Cluster
To run the template generation process, execute the runner script from the root directory:

```bash
python -m template_framework.run
```

This will output the `.png` templates and their `.json` metadata pairs into the `template_framework/generated/` directory.

### 2. Expanding the Dataset (Adding New Content)
Adding a new scene or activity is incredibly simple and requires **no duplicate prompt engineering**.

Open `definitions.py` and simply add a new object to the respective list. 
For example, to add a "Kitchen" scene:
```python
Scene(
    id="kitchen",
    name="Kitchen",
    prompt_description="a bright, clean modern kitchen with wooden counters",
    tags=["indoor", "home", "food"]
)
```

Now, when you loop over this new scene in `run.py`, the framework will automatically generate hundreds of new image permutations (Kitchen + Mother + Reading + 3 objects, Kitchen + Grandfather + Eating + 5 objects, etc.).

### 3. Annotating the Templates
The framework generates **placeholder boxes** in the images. These boxes exist so that later, transparent object assets (like footballs, apples, toys) can be dynamically pasted onto the image based on user preferences.

After generating templates, you must map the exact pixel coordinates for the faces and placeholder boxes.
Use the annotation tool:
```bash
python template_test/annotate_template.py path/to/generated/image.png
```
This tool will automatically inject the `face_regions` and `positions` coordinates into the template's JSON metadata file.

---

## 📄 Metadata Schema Example

Each generated image comes with a highly structured JSON file. Example:

```json
{
  "template_id": "park_grandfather_child_playing_ground_scattered_eye_level_5",
  "image_file": "park_grandfather_child_playing_ground_scattered_eye_level_5.png",
  "scene": "park",
  "family": [
    "grandfather",
    "child"
  ],
  "activity": "playing",
  "camera": "eye_level",
  "object_layout": "ground_scattered",
  "objects": [
    {
      "id": 1,
      "type": "placeholder_box",
      "count": 5,
      "positions": [] 
    }
  ],
  "face_slots": [
    "child",
    "grandfather_name"
  ],
  "face_regions": [],
  "supported_question_types": [
    "counting",
    "positions",
    "visual_search",
    "family_recognition",
    "comparison",
    "greater_less"
  ],
  "difficulty": "beginner",
  "age_group": "4-7",
  "tags": [
    "outdoor",
    "nature",
    "active",
    "fun"
  ]
}
```
*(Note: `positions` and `face_regions` will be populated once you run the annotation tool).*

---

## 🛠️ Best Practices

- **Strict Constraints**: Always maintain strict prompt instructions in `prompt_builder.py` regarding the child's age (exactly 5-6 years old). Generative models naturally age up children if not explicitly constrained.
- **Placeholder Layout**: If a new `ObjectLayout` is created, ensure the prompt explicitly tells the model to keep the white placeholder boxes clearly separated. If they overlap, the UI clicking/object substitution step will fail.
