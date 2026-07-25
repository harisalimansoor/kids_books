"""
prompt_builder.py
Generates the specific LLM prompt for generating the template image based on configuration.

TWO-PHASE DESIGN:
  Phase 1 (Template): Characters are posed with hands open/ready, holding generic white boxes.
  Phase 2 (Personalise): AI beautification replaces white boxes with user's chosen object.
"""
from .config import TemplateCombination


def build_prompt(combo: TemplateCombination) -> str:
    """
    Build the Phase 1 image generation prompt.
    Always generates white placeholder boxes — these are swapped during beautification.
    Enforces centered characters, crystal-clear non-blurred background, and active interaction.
    """
    layout_desc = combo.layout.prompt_description.format(count=combo.placeholder_count, object_name="white placeholder box")
    
    prompt = f"""
Create a photorealistic image of {combo.family.prompt_description}

ENVIRONMENT & COMPOSITION:
- Setting: {combo.scene.prompt_description}.
- Activity: They are {combo.activity.prompt_description}.
- Framing: Position both characters in the CENTER of the image frame. Provide generous breathing room and show plenty of the surrounding detailed kitchen background (cabinets, countertops, utensils, appliances) above, behind, and beside them.

CHARACTER INTERACTION:
- Both characters are looking warmly at each other and smiling.
- They are actively interacting with each other and physically holding or touching the white placeholder boxes together.

CHILD AGE — CRITICALLY IMPORTANT:
- The child MUST look exactly 5-6 years old. He is in Grade 1.
- He must have a small, round child's head, chubby cheeks, small nose, bright wide eyes.
- He must NOT look like a teenager, pre-teen, or older than 6 years old.

CAMERA & PLACEHOLDERS:
- {combo.camera.prompt_description}
- {layout_desc}
- The characters are holding or touching these plain white boxes, interacting with them naturally.

STYLE & LIGHTING:
- Ultra-realistic, bright warm lighting, highly vibrant and cheerful colours.
- BACKGROUND FOCUS: Crystal clear, fully sharp background focus. Absolutely NO background blur, NO bokeh, NO depth of field blur. All background kitchen details must be crisp and in sharp focus.

CRITICAL CONSTRAINTS:
- Child must be 5-6 years old (Grade 1). NOT older.
- Characters centered in frame with ample visible background around them.
- Clear, crisp background focus — NO background blur.
- Vibrant, bright colors and cheerful lighting.
- Exactly {combo.placeholder_count} plain white placeholder boxes visible — separated, non-overlapping, and countable.
- No text, no numbers, no words in the image.
- Image size: 1024x1024 pixels square.
"""
    return prompt.strip()


def build_beautify_prompt(
    combo: TemplateCombination,
    personalized_object: str,
    no_glasses_roles: list[str] | None = None,
) -> str:
    """
    Build the Phase 2 beautification prompt.
    Injects the user's personalized object (e.g. 'red apple', 'football', 'cupcake')
    and enforces anatomical alignment + face blending.
    
    Args:
        combo: The template combination metadata.
        personalized_object: The user's chosen object string (e.g. 'cupcake', 'ball').
        no_glasses_roles: List of roles that must NOT have glasses hallucinated.
    """
    count = combo.placeholder_count
    scene_light = "warm kitchen lighting" if "kitchen" in combo.scene.id else "natural outdoor lighting" if "park" in combo.scene.id else "ambient scene lighting"
    
    no_glasses_clause = ""
    if no_glasses_roles:
        roles_str = " and ".join(no_glasses_roles)
        no_glasses_clause = f"\n    5. ACCESSORIES: Do NOT add glasses or accessories that were not in the original faces. The {roles_str} must NOT have glasses."

    return f"""
    You are a master digital retoucher and photographer. I am providing a base image with digitally pasted faces and white placeholder boxes.
    Your job is to produce a single cohesive, ultra-realistic photograph.

    CRITICAL RULES:
    1. ANATOMICAL ALIGNMENT: Both faces have been digitally pasted. Reconstruct the jawline, chin, and neck
       so each face aligns perfectly with the body beneath. NO floating faces. Blend skin tone into neck and chest.
    2. LIGHTING MATCH: Match each pasted face's brightness, shadows, and colour temperature to the {scene_light}. Make the image bright and vibrant.
    3. FACIAL EXPRESSIONS: Give both characters warm, joyful, interacting expressions — looking at each other happily.
    4. FACE PRESERVATION: Preserve each person's core identity — same face, seamlessly attached.{no_glasses_clause}
    5. CHILD AGE: The child MUST appear exactly 5-6 years old — small head, chubby cheeks, young face.
    6. OBJECT REPLACEMENT (MOST CREATIVE TASK): Replace EVERY white placeholder box with a photorealistic,
       beautifully rendered '{personalized_object}'. There must be EXACTLY {count} of them.
       They must be integrated naturally — held in hands, placed on the surface, with correct lighting and contact shadows.
       The characters should appear to be naturally interacting with these '{personalized_object}s' and with each other.
       No white boxes should remain visible anywhere in the image.
    7. STYLE & BACKGROUND: Ultra-realistic, bright warm vibrant lighting, professional photography.
       BACKGROUND FOCUS: Keep the kitchen background crisp, clear, and fully sharp. Do NOT apply background blur or bokeh.

    Output ONLY the final image. No text.
    """.strip()

