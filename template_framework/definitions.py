"""
definitions.py
Definitions for Scenes, Families, Activities, Poses, Camera Angles, and Layouts.
"""
from .config import Scene, FamilyConfig, Activity, CameraAngle, ObjectLayout

SCENES = [
    Scene(
        id="living_room",
        name="Living Room",
        prompt_description="a cozy, warmly lit indoor living room",
        tags=["indoor", "home", "cozy"]
    ),
    Scene(
        id="park",
        name="Park",
        prompt_description="a bright, sunny green park with trees in the background",
        tags=["outdoor", "nature", "sunny"]
    ),
    Scene(
        id="classroom",
        name="Classroom",
        prompt_description="a bright UK kindergarten classroom with educational posters",
        tags=["indoor", "school", "bright"]
    ),
    Scene(
        id="kitchen",
        name="Kitchen",
        prompt_description="a spacious, bright, vibrant modern kitchen with crisp sharp background details, marble countertops, wooden cabinets, windows, kitchen island, and a rich, detailed background showing utensils and appliances clearly with generous visible room around the characters",
        tags=["indoor", "home", "food", "kitchen"]
    ),
]

FAMILIES = [
    FamilyConfig(
        id="mother_child",
        name="Mother and Child",
        prompt_description="a young boy (Grade 1 student, exactly 5-6 years old) and his mother. The child is noticeably smaller than his mother.",
        face_slots=["child", "mother_name"],
        tags=["family", "parent"]
    ),
    FamilyConfig(
        id="father_child",
        name="Father and Child",
        prompt_description="a young boy (Grade 1 student, exactly 5-6 years old) and his father. The child is noticeably smaller than his father.",
        face_slots=["child", "father_name"],
        tags=["family", "parent"]
    ),
    FamilyConfig(
        id="grandfather_child",
        name="Grandfather and Child",
        prompt_description="a young boy (Grade 1 student, exactly 5-6 years old) and his grandfather. The child is noticeably smaller than his grandfather.",
        face_slots=["child", "grandfather_name"],
        tags=["family", "grandparent"]
    ),
    FamilyConfig(
        id="grandmother_child",
        name="Grandmother and Child",
        prompt_description="a young boy (Grade 1 student, exactly 5-6 years old) and his grandmother. The child is noticeably smaller than his grandmother.",
        face_slots=["child", "grandmother_name"],
        tags=["family", "grandparent"]
    ),
    FamilyConfig(
        id="mother_father_child",
        name="Mother, Father and Child",
        prompt_description="a young boy (Grade 1 student, exactly 5-6 years old) standing between his mother and father in a happy family group. The parents are standing beside their son.",
        face_slots=["child", "mother_name", "father_name"],
        tags=["family", "parents", "multi_character"]
    ),
    FamilyConfig(
        id="mother_child_sibling",
        name="Mother, Child and Sibling",
        prompt_description="a young boy (Grade 1 student, 5-6 years old), his young sibling (4-7 years old), and their mother standing together in a cheerful group.",
        face_slots=["child", "sibling_1", "mother_name"],
        tags=["family", "parent", "sibling", "multi_character"]
    ),
    FamilyConfig(
        id="father_child_sibling",
        name="Father, Child and Sibling",
        prompt_description="a young boy (Grade 1 student, 5-6 years old), his young sibling (4-7 years old), and their father standing together around the kitchen island.",
        face_slots=["child", "sibling_1", "father_name"],
        tags=["family", "parent", "sibling", "multi_character"]
    ),
    FamilyConfig(
        id="full_family",
        name="Mother, Father, Child and Sibling",
        prompt_description="a complete family group: a young boy (Grade 1 student, 5-6 years old), his young sibling (4-7 years old), their mother, and their father, all gathered together joyfully.",
        face_slots=["child", "sibling_1", "mother_name", "father_name"],
        tags=["family", "parents", "sibling", "multi_character"]
    ),
    FamilyConfig(
        id="grandparents_child_sibling",
        name="Grandmother, Grandfather, Child and Sibling",
        prompt_description="a warm multigenerational group: a young boy (Grade 1 student, 5-6 years old), his young sibling, their grandmother, and their grandfather all gathered at the kitchen counter.",
        face_slots=["child", "sibling_1", "grandmother_name", "grandfather_name"],
        tags=["family", "grandparents", "sibling", "multi_character"]
    ),
]

ACTIVITIES = [
    Activity(
        id="baking_chef_hats",
        name="Baking in Chef Hats",
        prompt_description="wearing matching white chef hats and cute aprons while baking together at the flour-dusted kitchen counter. They are smiling warmly at each other while physically holding and interacting directly with white placeholder boxes on the counter next to a mixing bowl",
        tags=["active", "baking", "chef_hat", "food"]
    ),
    Activity(
        id="cooking_meal",
        name="Cooking a Meal",
        prompt_description="wearing colourful kitchen aprons while cooking together at the modern kitchen island. They are smiling warmly at each other while physically holding and interacting with white placeholder boxes near cooking pots",
        tags=["active", "cooking", "food"]
    ),
    Activity(
        id="making_pizza",
        name="Making Homemade Pizza",
        prompt_description="making mini pizzas at the kitchen counter with rolling pins and flour. They are wearing cute red aprons, smiling joyfully together while holding white placeholder boxes",
        tags=["active", "pizza", "cooking", "food"]
    ),
    Activity(
        id="organizing_groceries",
        name="Organizing Groceries",
        prompt_description="unpacking fresh grocery bags on the kitchen counter together. They are looking joyfully at each other while physically holding and interacting with white placeholder boxes near colourful market baskets",
        tags=["active", "organizing", "groceries"]
    ),
    Activity(
        id="breakfast_prep",
        name="Morning Breakfast Prep",
        prompt_description="preparing morning breakfast pancakes in a sunlit kitchen. They are smiling at each other in casual clothing while holding white placeholder boxes near syrup and milk bottles",
        tags=["active", "breakfast", "food"]
    ),
    Activity(
        id="decorating_treats",
        name="Decorating Pastries",
        prompt_description="decorating treats and cupcakes at the kitchen table. They are wearing chef aprons, holding piping bags and white placeholder boxes, interacting happily",
        tags=["active", "baking", "decorating", "food"]
    ),
    Activity(
        id="fruit_snack_prep",
        name="Fruit Snack Washing",
        prompt_description="washing and arranging fresh fruit in a bright kitchen sink/counter area. They are smiling together while holding white placeholder boxes near a wooden fruit bowl",
        tags=["active", "healthy", "fruit"]
    ),
    Activity(
        id="cookie_cutting",
        name="Cookie Cutting & Dough",
        prompt_description="rolling dough with wooden rolling pins and cookie cutters on the counter. They are wearing flour-dusted chef hats and aprons while holding white placeholder boxes",
        tags=["active", "baking", "cookies"]
    ),
    Activity(
        id="smoothie_bar",
        name="Making Smoothies",
        prompt_description="making fruit smoothies at the kitchen island counter. They are smiling joyfully together while holding white placeholder boxes near a blender and fresh fruit slices",
        tags=["active", "drinks", "healthy"]
    ),
    Activity(
        id="kitchen_crafts",
        name="Kitchen Crafts & Hobbies",
        prompt_description="doing fun hobby crafts and drawing at the kitchen dining table. They are smiling at each other while holding white placeholder boxes near art markers and paper",
        tags=["active", "hobby", "crafts"]
    ),
]

CAMERA_ANGLES = [
    CameraAngle(
        id="chest_up",
        prompt_description="MEDIUM CHEST-UP shot — characters are centered in the middle of the frame, showing faces, necks, shoulders, hands, and upper chest. Cut off at the waist/counter edge. Both characters interact and face slightly toward each other with front-facing faces (no side profiles). Ample breathing room and crystal-clear detailed kitchen background visible all around them."
    ),
    CameraAngle(
        id="eye_level",
        prompt_description="EYE-LEVEL medium shot — characters are centered in the frame from the waist up, interacting together, with sharp vibrant background space visible around them. Front-facing faces, no side profiles."
    )
]

OBJECT_LAYOUTS = [
    ObjectLayout(
        id="table_row",
        prompt_description="On the kitchen counter surface in front of them (or held in their hands), place exactly {count} clearly separated, identical plain white rounded square placeholder boxes in a row. They must be distinct, non-overlapping, and countable."
    ),
    ObjectLayout(
        id="ground_scattered",
        prompt_description="On the surface near them, place exactly {count} clearly separated, identical plain white rounded square placeholder boxes. They must be distinct and countable."
    ),
]

def get_scene(scene_id: str) -> Scene:
    for s in SCENES:
        if s.id == scene_id:
            return s
    raise ValueError(f"Scene {scene_id} not found")

def get_family(family_id: str) -> FamilyConfig:
    for f in FAMILIES:
        if f.id == family_id:
            return f
    raise ValueError(f"Family {family_id} not found")

def get_activity(activity_id: str) -> Activity:
    for a in ACTIVITIES:
        if a.id == activity_id:
            return a
    raise ValueError(f"Activity {activity_id} not found")

def get_camera(camera_id: str) -> CameraAngle:
    for c in CAMERA_ANGLES:
        if c.id == camera_id:
            return c
    raise ValueError(f"Camera {camera_id} not found")

def get_layout(layout_id: str) -> ObjectLayout:
    for l in OBJECT_LAYOUTS:
        if l.id == layout_id:
            return l
    raise ValueError(f"Layout {layout_id} not found")
