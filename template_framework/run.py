"""
run.py
Entry point for the Template Generation Framework.
Generates clusters of visual templates based on specified combinations.
"""
from pathlib import Path
from template_framework.config import TemplateCombination
from template_framework.definitions import (
    get_scene, get_family, get_activity, get_camera, get_layout
)
from template_framework.generator import run_generation

OUTPUT_DIR = Path(__file__).parent / "generated"

def generate_cluster():
    """
    Example: Generate a small cluster of templates for 'park' and 'living_room'
    with varying counts and layouts.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Define combinations to generate
    combinations_to_run = []
    
    # 1. Park + Grandfather & Child + Playing + 3, 5 objects (Ground Scattered)
    scene = get_scene("park")
    family = get_family("grandfather_child")
    activity = get_activity("playing")
    camera = get_camera("eye_level")
    layout = get_layout("ground_scattered")
    
    for count in [3, 5]:
        combo = TemplateCombination(scene, family, activity, camera, layout, count)
        combinations_to_run.append(combo)
        
    # 2. Living Room + Mother & Child + Reading + 4 objects (Table Row)
    scene = get_scene("living_room")
    family = get_family("mother_child")
    activity = get_activity("reading")
    camera = get_camera("chest_up")
    layout = get_layout("table_row")
    
    for count in [4]:
        combo = TemplateCombination(scene, family, activity, camera, layout, count)
        combinations_to_run.append(combo)

    # 3. Classroom + Mother & Child + Playing + 3 objects (Table Row)
    scene = get_scene("classroom")
    family = get_family("mother_child")
    activity = get_activity("playing")
    camera = get_camera("chest_up")
    layout = get_layout("table_row")
    
    for count in [3]:
        combo = TemplateCombination(scene, family, activity, camera, layout, count)
        combinations_to_run.append(combo)

    print(f"🚀 Starting Template Generation Framework...")
    print(f"📊 Queued {len(combinations_to_run)} templates for generation.\n")
    
    for i, combo in enumerate(combinations_to_run, 1):
        print(f"[{i}/{len(combinations_to_run)}] Processing combo...")
        run_generation(combo, OUTPUT_DIR)
        
    print("\n✅ Generation Complete! Check the 'template_framework/generated' directory.")

if __name__ == "__main__":
    generate_cluster()
