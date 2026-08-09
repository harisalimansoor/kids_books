"""
interactive_templates
─────────────────────
Reusable interactive scene system for worksheet images.

Design (kitchen-scene inspired, placeholder-based):
  1. Few ROLE templates per scene family (e.g. kitchen mother/father/grandma/grandad)
     with white object placeholder boxes and annotated face regions.
  2. An OBJECT library (food / hobby / pet) describing how hands should
     interact with that object type.
  3. At worksheet time:
       - pick role template from question context
       - paste faces into face boxes
       - paste the chosen object into placeholder slots
       - AI-beautify so hands/poses interact naturally with THAT object
         (cupcakes ≠ chocolates ≠ pizza slices)

This avoids generating a unique full scene for every food×role combination.
"""

from pathlib import Path

PACKAGE_DIR = Path(__file__).parent
SCENES_DIR = PACKAGE_DIR / "scenes"
OBJECTS_DIR = PACKAGE_DIR / "objects"
ASSETS_DIR = PACKAGE_DIR / "assets"

ADULT_ROLES = ("mother", "father", "grandmother", "grandfather")
SCENE_FAMILIES = ("kitchen", "hobby", "pet")
