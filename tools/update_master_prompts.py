"""
tools/update_master_prompts.py
Updates question_image.md across all grades with the Exact Quantity & Mathematical Visualization System rules.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

EXACT_QUANTITY_SECTION = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXACT QUANTITY & MATHEMATICAL VISUALIZATION RULES (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The mathematical question is the PRIMARY SOURCE OF TRUTH.

CRITICAL RULE — DO NOT RELY ON AI FOR EXACT LARGE COUNTS:
When a question requires more than 10 identical objects, DO NOT attempt to generate all objects individually and do not rely on the image-generation model to produce an exact numerical quantity.

Large quantities must be represented visually using mathematically controlled groups, arrays, tens, hundreds, or other structured representations.

The final application renderer is responsible for exact object counts, grouping, labels, and subtraction cross-outs.

AI-GENERATED IMAGERY IS RESPONSIBLE FOR:
- Characters & facial expressions
- Clothing & authentic uniforms
- Environment & atmospheric lighting
- Background depth & camera composition
- Storytelling & emotional warmth
- Small numbers of representative objects (or realistic containers/baskets/shelves)

THE APPLICATION RENDERER IS RESPONSIBLE FOR:
- Exact quantities
- Groups of 10
- Groups of 100
- Remainders
- Arrays
- Mathematical labels
- Cross-outs (❌)
- Equations
- Regrouping
- Place-value representations

QUANTITY REPRESENTATION RULES:
1. For quantities 1–10:
   - Individual objects may be shown in the scene.
   - Objects must be clearly visible and countable.
   - Do not hide, merge, duplicate, or partially obscure objects.

2. For quantities 11–20:
   - Prefer one group of 10 plus the remaining objects (e.g. 14 = 10 + 4).

3. For quantities 21–50:
   - Prefer groups of 10 plus the remainder (e.g. 47 = 10 + 10 + 10 + 10 + 7).
   - Groups should be visually separated and easy for a child to recognise (e.g. baskets, crates, trays, boxes).

4. For quantities 51–100:
   - Use groups of 10 and a remainder (e.g. 73 = 7 groups of 10 + 3).
   - Avoid generating 50–100 individually scattered objects.

5. For quantities above 100:
   - Use hundreds, tens, and ones representations where appropriate (e.g. 134 = 1 hundred + 3 tens + 4 ones).

GROUPING:
Groups should be visually obvious (baskets, trays, boxes, ten-frames, rows, arrays, clusters).
The visual representation must match the mathematical structure of the question.
Do not use random clusters that make it difficult for the child to determine how many objects are in each group.

SUBTRACTION VISUALIZATION:
For subtraction questions, the original objects must remain visible.
Objects being removed must be marked using a clear graphical cross/X overlay added by the renderer.
DO NOT draw crosses into the background or on faces. The application renderer adds the mathematical cross overlay.
Example: 15 − 6
The scene shows the original setting, and the renderer ensures 15 objects are shown with exactly 6 visibly crossed out, leaving exactly 9 uncrossed objects.
The crossed objects must remain visible underneath the cross so that the child understands that the objects existed originally and were removed.

For larger subtraction questions, use grouped tens and ones (e.g. 47 − 13 = 10 + 10 + 10 + 10 + 7, with 1 ten and 3 ones crossed).

SUBTRACTION WITH REGROUPING:
When subtraction requires regrouping, the visualization reflects the mathematical transformation:
Example: 42 − 18 -> 4 tens + 2 ones -> 3 tens + 12 ones -> remove 18 -> 2 tens + 4 ones = 24.

ADDITION:
For larger addition problems, use grouped quantities (e.g. 27 + 15 -> (20 + 7) + (10 + 5)).
Avoid large collections of randomly scattered objects.

MULTIPLICATION:
Represent multiplication using equal groups or arrays:
Example: 4 × 6 -> 4 visually separated groups containing exactly 6 objects each, or a 4-by-6 array.
Example: 5 × 10 -> 5 groups containing exactly 10 objects each.

DIVISION:
Represent division using equal groups:
Example: 40 ÷ 4 -> 40 objects distributed equally into 4 clearly identifiable groups of 10.

PLACE VALUE:
For place-value questions, use structured hundreds, tens, and ones representations.

MATHEMATICAL ACCURACY:
Never change a quantity merely to make the image easier to generate.
The numerical information in the question always takes priority.
Never add extra objects, remove objects, duplicate objects, or merge objects.
"""

def update_all_prompts():
    grades_dir = REPO_ROOT / "grades"
    count = 0
    for p in grades_dir.glob("*/prompts/question_image.md"):
        content = p.read_text(encoding="utf-8")
        if "# EXACT QUANTITY & MATHEMATICAL VISUALIZATION RULES" in content:
            print(f"Skipping {p.parent.parent.name}, already updated.")
            continue
        # Insert after section 1
        marker = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n# 2. QUESTION-FIRST SCENE INTERPRETATION"
        if marker in content:
            parts = content.split(marker, 1)
            new_content = parts[0] + EXACT_QUANTITY_SECTION.strip() + "\n\n" + marker + parts[1]
        else:
            new_content = content + "\n\n" + EXACT_QUANTITY_SECTION.strip() + "\n"
        
        p.write_text(new_content, encoding="utf-8")
        print(f"Updated {p.parent.parent.name} prompt.")
        count += 1
    print(f"Total prompts updated: {count}")

if __name__ == "__main__":
    update_all_prompts()
