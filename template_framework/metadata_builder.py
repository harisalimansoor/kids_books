"""
metadata_builder.py
Generates the standard metadata dictionary for a generated template.
"""
from typing import Dict, Any
from .config import TemplateCombination

def build_metadata(combo: TemplateCombination, filename: str) -> Dict[str, Any]:
    # Determine supported question types based on tags and count
    question_types = ["counting", "positions", "visual_search", "family_recognition"]
    if combo.placeholder_count >= 2:
        question_types.append("comparison")
        question_types.append("greater_less")
        
    if "active" in combo.activity.tags:
        question_types.append("action_recognition")
        
    # Clean family array for semantic use (e.g. ['grandfather', 'child'])
    # We derive this from the family.id by splitting on '_'
    family_members = combo.family.id.split("_")
    
    return {
        "template_id": combo.template_id,
        "image_file": filename,
        "scene": combo.scene.id,
        "family": family_members,
        "activity": combo.activity.id,
        "camera": combo.camera.id,
        "object_layout": combo.layout.id,
        "objects": [
            {
                "id": 1,
                "type": "placeholder_box",
                "count": combo.placeholder_count,
                "positions": [] # To be filled in via UI annotation later
            }
        ],
        "face_slots": combo.family.face_slots,
        "face_regions": [], # To be filled in via UI annotation later
        "supported_question_types": question_types,
        "difficulty": "beginner",
        "age_group": "4-7",
        "tags": combo.scene.tags + combo.family.tags + combo.activity.tags
    }
