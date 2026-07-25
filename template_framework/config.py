"""
config.py
Configuration and Data Models for the Template Generation Framework.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class Scene:
    id: str
    name: str
    prompt_description: str
    tags: List[str]

@dataclass
class FamilyConfig:
    id: str
    name: str
    prompt_description: str
    face_slots: List[str]
    tags: List[str]

@dataclass
class Activity:
    id: str
    name: str
    prompt_description: str
    tags: List[str]

@dataclass
class CameraAngle:
    id: str
    prompt_description: str

@dataclass
class ObjectLayout:
    id: str
    prompt_description: str

@dataclass
class TemplateCombination:
    scene: Scene
    family: FamilyConfig
    activity: Activity
    camera: CameraAngle
    layout: ObjectLayout
    placeholder_count: int
    object_name: str = "white placeholder box"
    
    @property
    def template_id(self) -> str:
        return f"{self.scene.id}_{self.family.id}_{self.activity.id}_{self.layout.id}_{self.camera.id}_{self.placeholder_count}_{self.object_name.replace(' ', '_')}"
