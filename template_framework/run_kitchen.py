"""
run_kitchen.py
Specialized runner for generating Kitchen templates.
"""
from pathlib import Path
from template_framework.config import TemplateCombination
from template_framework.definitions import (
    get_scene, get_family, get_activity, get_camera, get_layout
)
from template_framework.generator import run_generation

# Make a separate folder for kitchen templates
OUTPUT_DIR = Path(__file__).parent / "kitchen_templates"

def generate_kitchen_cluster():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    combinations_to_run = []
    
    scene = get_scene("kitchen")
    camera = get_camera("chest_up")
    layout = get_layout("table_row")
    
    # 1. Mother + Child (Baking in Chef Hats - Count: 4)
    combinations_to_run.append(
        TemplateCombination(scene, get_family("mother_child"), get_activity("baking_chef_hats"), camera, layout, 4, "white placeholder box")
    )
    
    # 2. Father + Child (Cooking a Meal - Count: 3)
    combinations_to_run.append(
        TemplateCombination(scene, get_family("father_child"), get_activity("cooking_meal"), camera, layout, 3, "white placeholder box")
    )
    
    # 3. Mother + Father + Child (Making Homemade Pizza - Count: 4)
    combinations_to_run.append(
        TemplateCombination(scene, get_family("mother_father_child"), get_activity("making_pizza"), camera, layout, 4, "white placeholder box")
    )
    
    # 4. Mother + Child + Sibling (Organizing Groceries - Count: 5)
    combinations_to_run.append(
        TemplateCombination(scene, get_family("mother_child_sibling"), get_activity("organizing_groceries"), camera, layout, 5, "white placeholder box")
    )
    
    # 5. Father + Child + Sibling (Morning Breakfast Prep - Count: 4)
    combinations_to_run.append(
        TemplateCombination(scene, get_family("father_child_sibling"), get_activity("breakfast_prep"), camera, layout, 4, "white placeholder box")
    )
    
    # 6. Full Family: Mother, Father, Child, Sibling (Decorating Pastries - Count: 4)
    combinations_to_run.append(
        TemplateCombination(scene, get_family("full_family"), get_activity("decorating_treats"), camera, layout, 4, "white placeholder box")
    )
    
    # 7. Grandfather + Child (Fruit Snack Washing - Count: 3)
    combinations_to_run.append(
        TemplateCombination(scene, get_family("grandfather_child"), get_activity("fruit_snack_prep"), camera, layout, 3, "white placeholder box")
    )
    
    # 8. Grandmother + Child (Cookie Cutting & Dough - Count: 4)
    combinations_to_run.append(
        TemplateCombination(scene, get_family("grandmother_child"), get_activity("cookie_cutting"), camera, layout, 4, "white placeholder box")
    )
    
    # 9. Grandparents + Child + Sibling (Making Fruit Smoothies - Count: 5)
    combinations_to_run.append(
        TemplateCombination(scene, get_family("grandparents_child_sibling"), get_activity("smoothie_bar"), camera, layout, 5, "white placeholder box")
    )
    
    # 10. Father + Child + Sibling (Kitchen Crafts & Hobbies - Count: 4)
    combinations_to_run.append(
        TemplateCombination(scene, get_family("father_child_sibling"), get_activity("kitchen_crafts"), camera, layout, 4, "white placeholder box")
    )

    print(f"🚀 Starting Kitchen Template Generation...")
    print(f"📊 Queued {len(combinations_to_run)} templates for generation.\n")
    
    for i, combo in enumerate(combinations_to_run, 1):
        print(f"[{i}/{len(combinations_to_run)}] Processing combo: {combo.template_id}")
        run_generation(combo, OUTPUT_DIR)
        
    print("\n✅ Generation Complete! Check the 'template_framework/kitchen_templates' directory.")

if __name__ == "__main__":
    generate_kitchen_cluster()
