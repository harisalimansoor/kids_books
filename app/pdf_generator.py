"""
PDF generation functions (Portrait Layout - Fully Corrected)

------------------------------------------------------------------
FONT SETUP (read this if the title / question font looks "wrong")
------------------------------------------------------------------
The workbook is designed around two custom fonts:

    - TITLE FONT  ("Ballpoint")     -> big bubbly heading, e.g. "Baking With Mum"
    - BODY FONT   ("Anicon Sans")   -> question text, MCQ options, "Answer:" label

We don't have license to redistribute the exact "Ballpoint" / "Anicon Sans"
font files, so this script looks for them first and, if they aren't
installed, falls back to a very close free alternative so the workbook
still looks right out of the box:

    fonts/Ballpoint.ttf        (title)   -> falls back to fonts/Baloo2-ExtraBold.ttf
    fonts/Ballpoint-Bold.ttf   (title)   -> falls back to fonts/Baloo2-ExtraBold.ttf
    fonts/AniconSans.ttf       (body)    -> falls back to fonts/Quicksand-Medium.ttf
    fonts/AniconSans-Bold.ttf  (body)    -> falls back to fonts/Quicksand-Bold.ttf

To use the *real* fonts: just drop the .ttf files into the fonts/ folder
next to this script with the exact names above (Ballpoint.ttf / Ballpoint-Bold.ttf /
AniconSans.ttf / AniconSans-Bold.ttf). Nothing else needs to change - this
file will pick them up automatically on the next run.
------------------------------------------------------------------
EMOJI / TOPIC ICON (top-left of every page)
------------------------------------------------------------------
Every page detects what the question is about (baking, money, shapes,
toys, playground, or general maths) and swaps in a matching colour
icon top-left, plus a matching title and a matching little "well done"
badge bottom-right - the same way the sample page you sent does it.

Icons are bundled in icons/<hex-codepoint>.png (Twemoji, colour, MIT
licensed). Drop a differently-named PNG into that folder and point a
category at it below if you'd rather use your own artwork.
------------------------------------------------------------------
SAFE-AREA NOTE (image + bottom doodles vs the page border)
------------------------------------------------------------------
The decorative border is drawn LAST, on top of everything else, at:
    rect(x=6, y=6, w=_PAGE_W-12=198, h=_PAGE_H-12=285)
i.e. it runs along x:[6,204] and y:[6,291]. Anything drawn right up to
those coordinates gets visually chopped by the border stroke. So the
photo and the bottom-left heart/star/sparkle doodles are both kept a
few mm clear of those numbers (see PHOTO_* and DOODLE_* constants
below) - that's what stops a star (baked into the AI photo) or the
mother's face from looking "cut off" / hidden behind the frame.
"""
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fpdf import FPDF
from PIL import Image, ImageFilter, ImageDraw
import numpy as np
try:
    from app.utils import safe_text
    from app.grade_config import get_fonts_dir, get_icons_dir, GradeNotFoundError, get_backcover_image_path
    from app.workbook_layout import (
        BORDER_H,
        BORDER_W,
        BORDER_X,
        BORDER_Y,
        PAGE_BADGE_D,
        PAGE_BADGE_Y,
        PAGE_H,
        PAGE_W,
        QUESTION_Y,
        TEXT_W,
        TEXT_X,
    )
    from app.mcq_options import STICKERS, build_mcq, normalize_trio, page_heading
except ImportError:
    from utils import safe_text  # type: ignore
    from grade_config import get_fonts_dir, get_icons_dir, GradeNotFoundError, get_backcover_image_path  # type: ignore
    from workbook_layout import (  # type: ignore
        BORDER_H,
        BORDER_W,
        BORDER_X,
        BORDER_Y,
        PAGE_BADGE_D,
        PAGE_BADGE_Y,
        PAGE_H,
        PAGE_W,
        QUESTION_Y,
        TEXT_W,
        TEXT_X,
    )
    from mcq_options import STICKERS, build_mcq, normalize_trio, page_heading  # type: ignore

try:
    from dotenv import load_dotenv
    _repo_root = Path(__file__).resolve().parent.parent
    load_dotenv(_repo_root / ".env")
except Exception:
    pass

# Portrait A4 (mm)
_PAGE_W = 210.0
_PAGE_H = 297.0

# ------------------------------------------------------------------
# Safe-area layout constants for the bottom photo + doodles.
# Border frame occupies x:[6,204] y:[6,291] (drawn last, on top).
# Keep real content a few mm inside that so nothing is chopped.
# ------------------------------------------------------------------
_PHOTO_X = 36          # sits along right/bottom, leaving top-left clear for question
_PHOTO_Y = 48          # alongside question on the right, extending down to y=278
_PHOTO_W = 166         # width inside safe area (reaches x=202)
_PHOTO_H = 230         # height inside safe area (reaches y=278)
_DOODLE_Y_OFFSET = 80  # bottom-left doodle clearance


def _get_font_dir(grade_id: str = "Grade_1") -> Path:
    """Resolve font directory via grade_config (grade-specific or shared/fonts/)."""
    try:
        return get_fonts_dir(grade_id)
    except (GradeNotFoundError, FileNotFoundError):
        # Last resort: sibling fonts/ relative to this file's parent's parent
        return Path(__file__).resolve().parent.parent / "shared" / "fonts"


def _get_icon_dir(grade_id: str = "Grade_1") -> Path:
    """Resolve icon directory via grade_config (grade-specific or shared/icons/)."""
    try:
        return get_icons_dir(grade_id)
    except (GradeNotFoundError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent / "shared" / "icons"


# ------------------------------------------------------------------
# TOPIC DETECTION: title + emoji icon + celebratory badge, all driven
# by keywords found in the question text.
# ------------------------------------------------------------------
_CATEGORIES = [
    {
        "keywords": ("coin", "money", "pence", "price", "shop", "buy", "cost", "pound"),
        "title": "Counting Coins With {adult}",
        "icon": "1f4b0",          # money bag
        "badge": "Smart Shopping Skills!",
    },
    {
        "keywords": ("bake", "cupcake", "cake", "cook", "oven", "kitchen", "recipe"),
        "title": "Baking With {adult}",
        "icon": "1f9c1",          # cupcake
        "badge": "Teamwork Tastes Better!",
    },
    {
        "keywords": ("park", "play", "slide", "swing", "seesaw", "ride"),
        "title": "Playing With {adult}",
        "icon": "1f3a1",          # ferris wheel
        "badge": "Fun Times Together!",
    },
    {
        "keywords": ("toy", "lego", "car", "block", "teddy", "doll"),
        "title": "Toys And Fun!",
        "icon": "1f9f8",          # teddy bear
        "badge": "Playtime Problem-Solver!",
    },
    {
        "keywords": ("shape", "triangle", "square", "circle", "rectangle", "corner"),
        "title": "Fun With Shapes",
        "icon": "1f4d0",          # triangular ruler
        "badge": "Shape Detective Skills!",
    },
    {
        "keywords": ("clock", "time", "hour", "minute", "o'clock"),
        "title": "Telling Time With {adult}",
        "icon": "23f0",           # alarm clock
        "badge": "Right On Time!",
    },
]
_DEFAULT_CATEGORY = {
    "title": "Maths With {adult}",
    "icon": "1f522",              # input numbers
    "badge": "Bright Little Mathematician!",
}

# extra decorative doodle icons used bottom-left on every page
_DOODLE_ICONS = ("2764", "2b50", "2728")  # heart, star, sparkles


def _detect_category(question_text: str) -> dict:
    q_lower = (question_text or "").lower()
    for cat in _CATEGORIES:
        if any(word in q_lower for word in cat["keywords"]):
            return cat
    return _DEFAULT_CATEGORY


def _icon_path(codepoint: str, grade_id: str = "Grade_1"):
    icon_dir = _get_icon_dir(grade_id)
    p = icon_dir / f"{codepoint}.png"
    return str(p) if p.exists() else None


def _resolve_food_icon(food_name: str) -> Optional[str]:
    """Resolves or dynamically creates a high-res food icon for the top-left of the page."""
    if not food_name or not str(food_name).strip():
        return None
    raw = str(food_name).strip()
    slug = re.sub(r"[^\w\s-]", "", raw.lower()).replace(" ", "_").strip("_")
    foods_dir = Path(__file__).resolve().parent.parent / "shared" / "icons" / "foods"
    foods_dir.mkdir(parents=True, exist_ok=True)

    # 1. Direct slug candidates
    for cand in (slug, slug.rstrip("s"), f"{slug}s", f"{slug}es"):
        p = foods_dir / f"{cand}.png"
        if p.exists():
            return str(p)

    # 2. Substring matching
    for f in foods_dir.glob("*.png"):
        stem = f.stem.lower()
        if stem in slug or slug in stem:
            return str(f)

    # 3. Dynamic fallback using PIL
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFont
        out_p = foods_dir / f"{slug}.png"
        img = PILImage.new("RGBA", (128, 128), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 124, 124], fill=(255, 237, 213, 255), outline=(249, 115, 22, 255), width=4)
        label = raw[:6].title()
        try:
            font = ImageFont.truetype("arial.ttf", 22)
        except Exception:
            font = ImageFont.load_default()
        bbox = font.getbbox(label) if hasattr(font, "getbbox") else (0, 0, 50, 20)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(((128 - tw) // 2, (128 - th) // 2), label, fill=(194, 65, 12, 255), font=font)
        img.save(out_p, "PNG")
        return str(out_p)
    except Exception as exc:
        print(f"[PDF WARN] Failed creating food icon for {raw}: {exc}")
        return None


def _resolve_character_image(character_name: str) -> Optional[str]:
    """Resolves or dynamically creates a transparent character sticker for the top-right of the page."""
    if not character_name or not str(character_name).strip():
        return None
    raw = str(character_name).strip()
    slug = re.sub(r"[^\w\s-]", "", raw.lower()).replace(" ", "_").strip("_")
    simple_slug = slug.replace("-", "").replace("_", "")
    char_dir = Path(__file__).resolve().parent.parent / "shared" / "characters"
    char_dir.mkdir(parents=True, exist_ok=True)

    # 1. Direct slug or alias matching
    for cand in (slug, simple_slug, slug.replace("-", "_"), slug.replace("_", "-")):
        p = char_dir / f"{cand}.png"
        if p.exists():
            return str(p)

    # 2. Substring matching
    for f in char_dir.glob("*.png"):
        f_simple = f.stem.lower().replace("-", "").replace("_", "")
        if f_simple == simple_slug or f_simple in simple_slug or simple_slug in f_simple:
            return str(f)

    # 3. Dynamic fallback using PIL
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFont
        out_p = char_dir / f"{simple_slug}.png"
        img = PILImage.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([10, 10, 246, 246], fill=(255, 255, 255, 255), outline=(99, 102, 241, 255), width=5)
        draw.ellipse([18, 18, 238, 238], fill=(99, 102, 241, 255))
        draw.ellipse([26, 26, 230, 230], outline=(255, 255, 255, 180), width=3)
        draw.ellipse([50, 42, 206, 178], fill=(199, 210, 254, 255), outline=(255, 255, 255, 220), width=4)

        initial = raw[0].upper()
        try:
            big_font = ImageFont.truetype("arial.ttf", 72)
        except Exception:
            big_font = ImageFont.load_default()
        bbox_i = big_font.getbbox(initial) if hasattr(big_font, "getbbox") else (0, 0, 50, 60)
        iw = bbox_i[2] - bbox_i[0]
        draw.text(((256 - iw) // 2, 70), initial, fill=(30, 41, 59, 255), font=big_font)

        draw.rounded_rectangle([20, 172, 236, 224], radius=14, fill=(255, 255, 255, 255), outline=(79, 70, 229, 255), width=3)
        display_label = raw[:14]
        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except Exception:
            font = ImageFont.load_default()
        bbox = font.getbbox(display_label) if hasattr(font, "getbbox") else (0, 0, 80, 20)
        tw = bbox[2] - bbox[0]
        draw.text(((256 - tw) // 2, 186), display_label, fill=(15, 23, 42, 255), font=font)

        img.save(out_p, "PNG")
        return str(out_p)
    except Exception as exc:
        print(f"[PDF WARN] Failed creating character sticker for {raw}: {exc}")
        return None




class _WorkbookPDF(FPDF):
    """Colourful portrait worksheet PDF."""

    def __init__(self, theme_color=(78, 86, 190), has_cover=False, *args, **kwargs):
        kwargs.setdefault("orientation", "P")
        kwargs.setdefault("format", "A4")
        super().__init__(*args, **kwargs)
        self.theme_color = theme_color
        self.has_cover = has_cover
        self.backcover_page = None

    def footer(self):
        if getattr(self, "has_cover", False) and self.page_no() == 1:
            return
        if getattr(self, "backcover_page", None) is not None and self.page_no() >= self.backcover_page:
            return

        display_num = self.page_no() - 1 if getattr(self, "has_cover", False) else self.page_no()
        d = PAGE_BADGE_D
        x = (PAGE_W - d) / 2
        y = PAGE_BADGE_Y
        self.set_fill_color(*self.theme_color)
        self.ellipse(x, y, d, d, style="F")
        self.set_font(TITLE_FONT["family"], "B", 11)
        self.set_text_color(255, 255, 255)
        self.set_xy(x, y + 2.5)
        self.cell(d, 7, safe_text(str(display_num)), align="C")


_TOPIC_PALETTES = [
    ((78, 86, 190), (238, 239, 255)),   # indigo
    ((225, 91, 119), (255, 239, 244)),  # rose
    ((23, 148, 132), (234, 250, 247)),  # teal
    ((232, 139, 45), (255, 246, 232)),  # orange
    ((128, 82, 174), (247, 239, 255)),  # purple
    ((49, 126, 193), (235, 246, 255)),  # blue
]


_COLOUR_NAMES = {
    "red": (225, 29, 72),
    "ruby": (225, 29, 72),
    "blue": (37, 99, 235),
    "royal blue": (37, 99, 235),
    "sky blue": (14, 165, 233),
    "cyan": (6, 182, 212),
    "pink": (236, 72, 153),
    "rose": (244, 63, 94),
    "purple": (139, 92, 246),
    "violet": (124, 58, 237),
    "orange": (249, 115, 22),
    "sunset": (249, 115, 22),
    "amber": (245, 158, 11),
    "yellow": (234, 179, 8),
    "green": (16, 185, 129),
    "emerald": (16, 185, 129),
    "teal": (20, 184, 166),
    "indigo": (99, 102, 241),
}


def _mix(a, b, amount: float):
    amount = max(0.0, min(1.0, amount))
    return tuple(round(a[i] * (1 - amount) + b[i] * amount) for i in range(3))


def _parse_favourite_colour(value: str):
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if not text:
        return (78, 86, 190)

    # 1. Hex codes e.g. #ec4899, #0ea5e9, #f97316
    hex_clean = text.lstrip("#")
    if len(hex_clean) == 6 and all(c in "0123456789abcdef" for c in hex_clean):
        try:
            return (int(hex_clean[0:2], 16), int(hex_clean[2:4], 16), int(hex_clean[4:6], 16))
        except ValueError:
            pass
    elif len(hex_clean) == 3 and all(c in "0123456789abcdef" for c in hex_clean):
        try:
            return (int(hex_clean[0] * 2, 16), int(hex_clean[1] * 2, 16), int(hex_clean[2] * 2, 16))
        except ValueError:
            pass

    # 2. Named colors (longest match first)
    for name in sorted(_COLOUR_NAMES, key=len, reverse=True):
        if name in text:
            return _COLOUR_NAMES[name]

    # 3. Deterministic palette seed fallback
    seed = sum((i + 1) * ord(char) for i, char in enumerate(text))
    return _TOPIC_PALETTES[seed % len(_TOPIC_PALETTES)][0]


# ------------------------------------------------------------------
# Font resolution (see module docstring for how to swap in the real
# "Ballpoint" / "Anicon Sans" files).
# ------------------------------------------------------------------
def _first_existing(*candidates):
    for c in candidates:
        if c and c.exists():
            return str(c)
    return None


# TITLE_FONT and BODY_FONT are now resolved dynamically per-grade in _resolve_fonts().
# These module-level dicts are initialized at first call via _resolve_fonts().
TITLE_FONT: dict = {"family": "TitleFont", "regular": None, "bold": None}
BODY_FONT:  dict = {"family": "BodyFont",  "regular": None, "bold": None}
HAND_FONT:  dict = {"family": "HandFont",  "regular": None, "bold": None}


def _resolve_fonts(grade_id: str = "Grade_1") -> None:
    """Title is a rounded display face. The question is handwriting."""
    font_dir = _get_font_dir(grade_id)
    shared = Path(__file__).resolve().parent.parent / "shared" / "fonts"

    def pick(*names: str):
        return _first_existing(*[font_dir / name for name in names], *[shared / name for name in names])

    title = pick("LilitaOne-Regular.ttf", "Ballpoint.ttf", "Baloo2-ExtraBold.ttf")
    TITLE_FONT["regular"] = title
    TITLE_FONT["bold"] = title
    hand = pick("PatrickHand-Regular.ttf", "AniconSans.ttf", "Quicksand-Medium.ttf")
    HAND_FONT["regular"] = hand
    HAND_FONT["bold"] = hand
    BODY_FONT["regular"] = pick("AniconSans.ttf", "Quicksand-Medium.ttf", "PatrickHand-Regular.ttf")
    BODY_FONT["bold"] = pick("AniconSans-Bold.ttf", "Quicksand-Bold.ttf", "PatrickHand-Regular.ttf")


def _register_fonts(pdf: FPDF) -> None:
    """Register title, body, and handwriting. Missing files fall back to Helvetica."""
    for spec in (TITLE_FONT, BODY_FONT, HAND_FONT):
        ok = False
        try:
            if spec["regular"]:
                pdf.add_font(spec["family"], "", spec["regular"])
                pdf.add_font(spec["family"], "B", spec["bold"] or spec["regular"])
                ok = True
        except Exception:
            ok = False
        if not ok:
            spec["family"] = "Helvetica"


# ------------------------------------------------------------------
# Page background colour: ONE flat, plain, neutral wash (no dots, no
# pattern, no corner blobs). Kept flat on purpose so the AI-generated
# photo - which is now told to use the same kind of flat neutral
# background - can blend into the page instead of looking like a
# separately pasted image with a visible white/patterned edge.
# ------------------------------------------------------------------
_NEUTRAL_PAGE_TONE = (255, 255, 255)  # pure crisp white paper


def _page_bg_color(theme_color):
    """The single flat colour used for both the page background and the
    canvas the generated photo is composited onto, so the two match."""
    return _NEUTRAL_PAGE_TONE


def _make_page_texture(theme_color, size=(1240, 1754)) -> Image.Image:
    """Flat, plain, clean white page colour - deliberately textureless so a
    pasted photo blends into it rather than looking cut out."""
    return Image.new("RGB", size, (255, 255, 255))


def _draw_bunting(pdf: FPDF, x_start: float, x_end: float, y: float, theme_color):
    """Little triangle pennant banner across the top, like a party garland."""
    colours = [
        theme_color,
        _mix(theme_color, (255, 210, 90), 0.6),
        _mix(theme_color, (90, 200, 255), 0.6),
        _mix(theme_color, (255, 150, 190), 0.6),
    ]
    pdf.set_draw_color(*_mix(theme_color, (0, 0, 0), 0.2))
    pdf.set_line_width(0.3)
    pdf.line(x_start, y, x_end, y)

    flag_w = 9
    gap = 3
    x = x_start
    i = 0
    while x + flag_w <= x_end:
        colour = colours[i % len(colours)]
        pdf.set_fill_color(*colour)
        pdf.polygon([(x, y), (x + flag_w, y), (x + flag_w / 2, y + 10)], style="F")
        x += flag_w + gap
        i += 1


def _prepare_transparent_pet_assets(pet_info: dict) -> dict:
    """Ensures transparent background cutout exists for the pet, using rembg (u2netp) if needed."""
    p_dict = dict(pet_info)
    img_p = p_dict.get("image_path")
    if not img_p or not os.path.exists(str(img_p)):
        return p_dict

    img_path = Path(img_p)
    parent_dir = img_path.parent
    pet_id = p_dict.get("id") or "pet_1"

    # Check for sitting pose
    if not p_dict.get("sitting_path"):
        for name in (f"{pet_id}_sitting_transparent.png", "ai_dog_sitting_transparent.png"):
            cand = parent_dir / name
            if cand.exists():
                p_dict["sitting_path"] = str(cand)
                break

    # Check for lying pose
    if not p_dict.get("lying_path"):
        for name in (f"{pet_id}_lying_transparent.png", "ai_dog_lying_transparent.png"):
            cand = parent_dir / name
            if cand.exists():
                p_dict["lying_path"] = str(cand)
                break

    # Check for transparent base cutout
    if not p_dict.get("transparent_path"):
        for name in (f"{pet_id}_transparent.png", "test_cutout_tight.png", f"{pet_id}_cutout.png"):
            cand = parent_dir / name
            if cand.exists():
                p_dict["transparent_path"] = str(cand)
                break

    # If transparent_path still not found, run lightweight rembg cutout
    if not p_dict.get("transparent_path"):
        try:
            from rembg import new_session, remove
            session = new_session("u2netp")
            with Image.open(img_path) as raw_img:
                rgb_img = raw_img.convert("RGB")
                cutout = remove(rgb_img, session=session)
                bbox = cutout.getbbox()
                if bbox:
                    cutout = cutout.crop(bbox)
                out_p = parent_dir / f"{pet_id}_transparent.png"
                cutout.save(out_p, "PNG")
                p_dict["transparent_path"] = str(out_p)
        except Exception as cut_err:
            print(f"[PDF WARN] rembg transparent cutout failed: {cut_err}")

    # Fallbacks: if sitting or lying not generated, use transparent_path
    base_trans = p_dict.get("transparent_path") or str(img_p)
    if not p_dict.get("sitting_path"):
        p_dict["sitting_path"] = base_trans
    if not p_dict.get("lying_path"):
        p_dict["lying_path"] = base_trans

    return p_dict


def _draw_bottom_badge(pdf: FPDF, badge_text: str, theme_color, pets: list = None, page_num: int = 1):
    """If pets are provided: places the pet illustration with transparent background grounded
    at the bottom right corner (sitting on odd pages, lying on the floor on even pages),
    with NO text and NO border as requested.
    If no pets: falls back to the celebratory pill badge box."""
    if pets:
        valid_pets = [
            p for p in pets
            if p.get("sitting_path") or p.get("lying_path") or p.get("transparent_path") or p.get("image_path")
        ]
        if valid_pets:
            # Place transparent pet(s) directly on the page - NO text, NO border, NO box
            if len(valid_pets) == 1:
                pet = valid_pets[0]
                # Alternate poses: odd pages = sitting, even pages = lying on the floor
                if page_num % 2 == 1:
                    chosen_img = pet.get("sitting_path") or pet.get("transparent_path") or pet.get("image_path")
                else:
                    chosen_img = pet.get("lying_path") or pet.get("transparent_path") or pet.get("image_path")

                if chosen_img and os.path.exists(chosen_img):
                    try:
                        with Image.open(chosen_img) as im:
                            iw, ih = im.size
                        aspect = iw / max(ih, 1)
                        if aspect < 1.0:
                            # Tall / sitting posture: anchor height
                            h = 36.0
                            w = h * aspect
                            if w > 45.0:
                                w = 45.0
                                h = w / aspect
                        else:
                            # Wide / lying posture: anchor width
                            w = 44.0
                            h = w / aspect
                            if h > 34.0:
                                h = 34.0
                                w = h * aspect

                        px = _PAGE_W - 12.0 - w
                        py = _PAGE_H - 8.0 - h
                        pdf.image(chosen_img, x=px, y=py, w=w, h=h)
                    except Exception as err:
                        print(f"[PDF WARN] Failed placing transparent pet pose: {err}")
                return

            elif len(valid_pets) >= 2:
                # 2 pets: place both side-by-side grounded at bottom right
                p1, p2 = valid_pets[0], valid_pets[1]
                img1 = (p1.get("sitting_path") if page_num % 2 == 1 else p1.get("lying_path")) or p1.get("transparent_path") or p1.get("image_path")
                img2 = (p2.get("lying_path") if page_num % 2 == 1 else p2.get("sitting_path")) or p2.get("transparent_path") or p2.get("image_path")

                curr_x = _PAGE_W - 14.0
                for img_p in (img2, img1):
                    if img_p and os.path.exists(img_p):
                        try:
                            with Image.open(img_p) as im:
                                iw, ih = im.size
                            aspect = iw / max(ih, 1)
                            h = 30.0 if aspect < 1.0 else 24.0
                            w = h * aspect
                            curr_x -= (w + 3.0)
                            py = _PAGE_H - 8.0 - h
                            pdf.image(img_p, x=curr_x, y=py, w=w, h=h)
                        except Exception as e:
                            print(f"[PDF WARN] Failed placing dual pet: {e}")
                return

    # Fallback when no pets are provided: standard celebratory badge box
    if not badge_text:
        return
    badge_w = 60
    badge_h = 14
    bx = _PAGE_W - 14 - badge_w
    by = _PAGE_H - 14 - badge_h

    pdf.set_fill_color(*_mix(theme_color, (255, 255, 255), 0.88))
    pdf.set_draw_color(*_mix(theme_color, (255, 255, 255), 0.70))
    pdf.set_line_width(0.4)
    pdf.rect(bx, by, badge_w, badge_h, style="FD", round_corners=True, corner_radius=7)
    pdf.set_xy(bx, by + 1.2)
    pdf.set_font(TITLE_FONT["family"], "B", 10.5)
    pdf.set_text_color(*theme_color)
    badge_clean = re.sub(r"[♡♥]+", "", safe_text(badge_text)).strip()
    tw = pdf.get_string_width(badge_clean)
    text_x = bx + max((badge_w - tw - 6) / 2, 2.0)
    pdf.set_xy(text_x, by + 1.2)
    pdf.cell(tw, badge_h - 2, badge_clean)

    hx = min(text_x + tw + 3.0, bx + badge_w - 4)
    hy = by + (badge_h / 2) - 1.0
    pdf.set_draw_color(*theme_color)
    pdf.set_line_width(0.4)
    t = np.linspace(0, 2 * np.pi, 25)
    xs = 16 * np.sin(t) ** 3 * 0.11 + hx
    ys = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)) * 0.11 + hy
    pts = [(float(xs[i]), float(ys[i])) for i in range(len(t))]
    pdf.polygon(pts, style="D")



def _draw_corner_doodles(pdf: FPDF, x: float, y: float, theme_color, grade_id: str = "Grade_1"):
    """Heart / star / sparkle scatter, bottom-left, echoing the sample page.
    Drawn with clean vector strokes matching the doodle style."""
    # Pink tilted doodle heart outline
    pdf.set_draw_color(244, 95, 150)
    pdf.set_line_width(0.8)
    hx, hy = x + 2, y + 2
    with pdf.rotation(-15, hx + 5, hy + 5):
        t = np.linspace(0, 2 * np.pi, 40)
        xs = 16 * np.sin(t) ** 3
        ys = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))
        xs = hx + 5 + xs * 0.35
        ys = hy + 5 + ys * 0.35
        pts = [(float(xs[i]), float(ys[i])) for i in range(len(t))]
        pdf.polygon(pts, style="D")

    # Yellow tilted star doodle outline
    pdf.set_draw_color(245, 180, 20)
    pdf.set_line_width(0.8)
    sx, sy = x + 7, y + 24
    with pdf.rotation(12, sx, sy):
        angles = np.linspace(-np.pi / 2, 1.5 * np.pi, 10, endpoint=False)
        radii = [6.0 if i % 2 == 0 else 2.6 for i in range(10)]
        star_pts = [(sx + radii[i] * np.cos(angles[i]), sy + radii[i] * np.sin(angles[i])) for i in range(10)]
        pdf.polygon(star_pts, style="D")

    # Yellow sparkle rays
    pdf.set_draw_color(245, 180, 20)
    pdf.set_line_width(0.8)
    pdf.line(x + 2, y + 36, x - 2, y + 40)
    pdf.line(x + 7, y + 39, x + 4, y + 45)


def _resolve_marker_font():
    """Kept for backward compatibility with any external callers."""
    return TITLE_FONT.get("regular")


def _create_freeform_mask(w_px=1660, h_px=2300) -> Image.Image:
    """Generate organic feathered alpha mask for freeform image cropping.
    Clears top-left region for question and vertical checkboxes,
    keeping upper-right and bottom while softly feathering all edges."""
    mask = Image.new("L", (w_px, h_px), 0)
    draw = ImageDraw.Draw(mask)

    base_points = [
        (480, 25),
        (1630, 25),
        (1630, 2260),
        (40, 2260),
        (40, 1220),
        (480, 760),
    ]
    detailed_points = []
    np.random.seed(42)
    for i in range(len(base_points)):
        p1 = np.array(base_points[i], dtype=float)
        p2 = np.array(base_points[(i + 1) % len(base_points)], dtype=float)
        dist = np.linalg.norm(p2 - p1)
        steps = max(int(dist / 14), 1)
        for s in range(steps):
            t = s / steps
            pt = (1 - t) * p1 + t * p2
            if not (p1[0] > 1500 and p2[0] > 1500):
                wobble = (np.sin(t * 14 + i * 2) * 8 + np.cos(t * 28 + i * 3) * 5 + np.random.uniform(-4, 4))
                normal = np.array([-(p2[1] - p1[1]), p2[0] - p1[0]])
                norm_len = np.linalg.norm(normal)
                if norm_len > 0:
                    normal = normal / norm_len
                    pt += normal * wobble
            detailed_points.append((float(pt[0]), float(pt[1])))
    draw.polygon(detailed_points, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(radius=30))


def _freeform_crop_image(src_path: str, dest_path: str, *, target_w: int = 1660, target_h: int = 2300,
                         bg_color=_NEUTRAL_PAGE_TONE, **kwargs) -> str:
    """Crop and blend the image with organic feathered vignette edges into the page."""
    im = Image.open(src_path).convert("RGB")
    scale = max(target_w / im.size[0], target_h / im.size[1])
    new_w, new_h = int(im.size[0] * scale), int(im.size[1] * scale)
    im_scaled = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
    cx = max(0, new_w - target_w)
    cy = 0  # Preserve full top headroom so heads and hair are never cropped
    im_cropped = im_scaled.crop((cx, cy, cx + target_w, cy + target_h))

    mask = _create_freeform_mask(target_w, target_h)
    bg = Image.new("RGB", (target_w, target_h), tuple(int(c) for c in bg_color))
    bg.paste(im_cropped, (0, 0), mask)
    bg.save(dest_path, format="PNG")
    return dest_path


def _soft_corner_image(src_path: str, dest_path: str, *, bg_color=_NEUTRAL_PAGE_TONE, **kwargs) -> str:
    """Backward compatibility wrapper delegating to _freeform_crop_image."""
    return _freeform_crop_image(src_path, dest_path, bg_color=bg_color, **kwargs)


def build_mcq_options(question: str, *, count=None, adult_name=None) -> tuple[list[str], str]:
    """Build dynamic options based on the question."""
    q = (question or "").strip()
    low = q.lower()
    adult = (adult_name or "").strip() or "Mum"

    # Number-extraction fallback (Dynamic calculation)
    q_body = re.sub(r'^\d+\.\s*', '', q)
    found_nums = re.findall(r'\b(\d+)(?:[a-z]*)\b', q_body)
    seen_nums: list[str] = []
    for n in found_nums:
        if n not in seen_nums:
            seen_nums.append(n)

    if len(seen_nums) >= 2:
        opts = list(seen_nums)
        try:
            last_num = int(seen_nums[-1])
            for cand in [last_num + 1, last_num + 2, max(0, last_num - 1), max(0, last_num - 2)]:
                cand_s = str(cand)
                if cand_s not in opts:
                    opts.append(cand_s)
                if len(opts) >= 4:
                    break
        except Exception:
            pass
        while len(opts) < 4:
            opts.append(f"Option {len(opts) + 1}")
        return opts[:4], ""

    return ["A", "B", "C", "D"], "A"


def _option_palette(theme_color):
    """Four distinct, attractive colours (the same family used for the top
    bunting) so each option box + its text gets its own colour instead of
    a plain black outline."""
    return [
        theme_color,
        _mix(theme_color, (255, 170, 60), 0.62),   # warm amber
        _mix(theme_color, (60, 180, 255), 0.55),   # sky blue
        _mix(theme_color, (235, 110, 160), 0.55),  # pink
    ]


def _draw_vertical_options(pdf: FPDF, x: float, start_y: float, options: list[str], width: float | None = None) -> float:
    """Draw options in the empty column. Long text wraps before the image."""
    box_size = 8.0
    text_x = x + box_size + 3.0
    text_w = max(12.0, (width or TEXT_W) - box_size - 4)
    y = start_y
    pdf.set_font(HAND_FONT["family"], "", 14)
    line_h = 6.5
    for opt in options[:3]:
        clean_text = re.sub(r"^Option\s+\d+:\s*", "", str(opt).strip(), flags=re.I)
        words = safe_text(clean_text).split()
        lines: list[str] = []
        current = ""
        for word in words:
            trial = word if not current else f"{current} {word}"
            if current and pdf.get_string_width(trial) > text_w:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        if not lines:
            lines = [""]
        pdf.set_draw_color(35, 35, 45)
        pdf.set_fill_color(255, 255, 255)
        pdf.set_line_width(0.6)
        pdf.rect(x, y, box_size, box_size, style="FD", round_corners=True, corner_radius=1.5)
        pdf.set_text_color(25, 25, 25)
        for index, line in enumerate(lines):
            pdf.set_xy(text_x, y + index * line_h)
            pdf.cell(text_w, line_h, line)
        y += max(box_size, len(lines) * line_h) + 4
    pdf.set_xy(x, y)
    return y


def _draw_square_option_row(pdf: FPDF, x: float, y: float, text: str, colour):
    """Backward compatibility wrapper."""
    box_size = 8
    pdf.set_draw_color(*colour)
    pdf.set_fill_color(255, 255, 255)
    pdf.set_line_width(0.7)
    pdf.rect(x, y, box_size, box_size, style="FD", round_corners=True, corner_radius=1.8)

    pdf.set_xy(x + 12, y - 0.5)
    pdf.set_font(BODY_FONT["family"], "B", 15)
    pdf.set_text_color(25, 25, 25)
    pdf.cell(50, box_size, safe_text(str(text)))


def _draw_answer_tab(pdf: FPDF, x: float, y: float, theme_color, width: float = 178, height: float = 14) -> float:
    """Kept for backward compatibility, not used on the student workbook page."""
    return y


def _draw_question_with_highlighted_names(
    pdf: FPDF, text: str, student_name: str, adult_name: str, theme_color,
    x: float, y: float, w: float = 76.0, line_h: float = 6.8, font_size: int = 13,
    font_family: str | None = None,
) -> None:
    """Prints question text on the top-left with structured word-by-word line wrapping
    and widow/orphan prevention. Lines are fully balanced with zero stranded lone words,
    and child/adult names are highlighted in distinct themed colours."""
    student_colour = theme_color
    adult_colour = _mix(theme_color, (214, 62, 72), 0.55)  # warm, distinct from theme

    names = []
    if student_name and student_name.strip():
        names.append((student_name.strip(), student_colour))
    if adult_name and adult_name.strip() and adult_name.strip().lower() not in ("a friend",):
        names.append((adult_name.strip(), adult_colour))

    name_map = {}
    for nm, col in names:
        clean_nm = nm.strip().lower()
        if clean_nm:
            name_map[clean_nm] = col

    family = font_family or HAND_FONT["family"]
    safe_full = safe_text(text)
    pdf.set_font(family, "", font_size)
    space_w = pdf.get_string_width(" ")
    paragraphs = [p.strip() for p in safe_full.split("\n") if p.strip()]
    cur_y = y

    for p_idx, para in enumerate(paragraphs):
        raw_words = para.split()
        if not raw_words:
            continue

        tagged_words = []
        for word in raw_words:
            clean_w = re.sub(r'^[^\w]+|[^\w]+$', '', word).lower()
            col = name_map.get(clean_w, (25, 25, 25))
            word_w = pdf.get_string_width(word)
            tagged_words.append((word, word_w, col))

        # Build lines word by word so lines are fully structured with no orphans
        lines = []
        cur_line = []
        cur_w = 0.0

        for word, word_w, col in tagged_words:
            pieces = [word]
            if word_w > w:
                pieces = []
                buf = ""
                for ch in word:
                    trial = buf + ch
                    if buf and pdf.get_string_width(trial) > w:
                        pieces.append(buf)
                        buf = ch
                    else:
                        buf = trial
                if buf:
                    pieces.append(buf)
            for piece in pieces:
                piece_w = pdf.get_string_width(piece)
                needed = piece_w if not cur_line else (cur_w + space_w + piece_w)
                if cur_line and needed > w:
                    lines.append(cur_line)
                    cur_line = [(piece, piece_w, col)]
                    cur_w = piece_w
                else:
                    cur_line.append((piece, piece_w, col))
                    cur_w = needed

        if cur_line:
            lines.append(cur_line)

        # Widow / orphan prevention: if the last line has only 1 word,
        # pull one word from the previous line down to keep lines balanced
        if len(lines) >= 2 and len(lines[-1]) == 1 and len(lines[-2]) >= 3:
            lines[-1].insert(0, lines[-2].pop())

        for line_items in lines:
            cur_x = x
            for word, word_w, col in line_items:
                pdf.set_text_color(*col)
                pdf.set_xy(cur_x, cur_y)
                pdf.cell(word_w, line_h, safe_text(word))
                cur_x += word_w + space_w
            cur_y += line_h

        if p_idx < len(paragraphs) - 1:
            cur_y += 2.5  # paragraph spacing

    pdf.set_xy(x, cur_y)


def _extract_dynamic_title(question_text: str, default_adult: str) -> str:
    """Smart Title Extractor, now driven by the same category table used
    for the emoji icon and the bottom-right badge, so all three always agree."""
    adult = default_adult.capitalize() if default_adult and default_adult.strip() else "a Friend"
    category = _detect_category(question_text)
    return category["title"].format(adult=adult)


def _place_full_a4(pdf: FPDF, image_path: str) -> None:
    """Fill one A4 page edge to edge. The page itself stays 210 x 297 mm."""
    try:
        from app.front_cover_generator import to_a4_image
    except ImportError:
        from front_cover_generator import to_a4_image  # type: ignore
    with Image.open(image_path) as source:
        fitted = to_a4_image(source)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    fitted.save(tmp.name, "PNG")
    pdf.image(tmp.name, x=0, y=0, w=210.0, h=297.0)
    try:
        os.remove(tmp.name)
    except Exception:
        pass


def _add_cover_page(
    pdf: FPDF,
    cover_image_path: str,
    grade_label: str = "",
    theme_color: tuple = (78, 86, 190),
) -> None:
    pdf.add_page(orientation="P", format="A4")
    try:
        _place_full_a4(pdf, cover_image_path)
    except Exception:
        pdf.image(cover_image_path, x=0, y=0, w=210.0, h=297.0)


def _add_backcover_page(pdf: _WorkbookPDF, backcover_image_path: str) -> None:
    pdf.add_page(orientation="P", format="A4")
    pdf.backcover_page = pdf.page_no()
    try:
        _place_full_a4(pdf, backcover_image_path)
    except Exception:
        pdf.image(backcover_image_path, x=0, y=0, w=210.0, h=297.0)


def _sticker_file(kind: str) -> str | None:
    """Small activity icon drawn for the title. Same set for every grade."""
    cache = getattr(_sticker_file, "_cache", {})
    kind = kind if kind in STICKERS else "maths"
    cached = cache.get(kind)
    if cached and os.path.exists(cached):
        return cached

    from PIL import Image as PILImage, ImageDraw, ImageFont

    img = PILImage.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if kind == "building":
        draw.rounded_rectangle((48, 90, 208, 220), radius=8, fill=(232, 168, 74, 255))
        draw.rectangle((70, 78, 108, 96), fill=(232, 168, 74, 255))
        draw.rectangle((148, 70, 186, 96), fill=(232, 168, 74, 255))
        draw.polygon([(40, 96), (78, 48), (116, 96)], fill=(180, 92, 48, 255))
        draw.polygon([(138, 96), (176, 40), (214, 96)], fill=(180, 92, 48, 255))
        draw.rounded_rectangle((108, 150, 148, 220), radius=6, fill=(120, 64, 36, 255))
        draw.ellipse((78, 118, 102, 142), fill=(255, 236, 196, 255))
        draw.ellipse((154, 118, 178, 142), fill=(255, 236, 196, 255))
    elif kind == "baking":
        draw.ellipse((58, 110, 198, 210), fill=(244, 164, 196, 255))
        draw.rounded_rectangle((78, 150, 178, 230), radius=16, fill=(186, 104, 72, 255))
        draw.ellipse((108, 48, 148, 120), fill=(255, 255, 255, 255))
    elif kind == "food":
        draw.ellipse((70, 48, 190, 190), fill=(220, 48, 48, 255))
        draw.polygon([(128, 36), (150, 78), (108, 78)], fill=(64, 150, 64, 255))
    elif kind == "book":
        draw.rounded_rectangle((58, 48, 198, 210), radius=8, fill=(64, 120, 210, 255))
        draw.rectangle((78, 48, 92, 210), fill=(40, 80, 160, 255))
        draw.line((110, 90, 176, 90), fill=(255, 255, 255, 255), width=6)
        draw.line((110, 120, 176, 120), fill=(255, 255, 255, 255), width=6)
    elif kind == "balloon":
        draw.ellipse((70, 30, 186, 160), fill=(236, 72, 140, 255))
        draw.line((128, 160, 128, 220), fill=(80, 80, 80, 255), width=4)
        draw.polygon([(118, 156), (138, 156), (128, 176)], fill=(236, 72, 140, 255))
    elif kind == "car":
        draw.rounded_rectangle((36, 110, 220, 170), radius=16, fill=(48, 140, 210, 255))
        draw.polygon([(70, 110), (100, 70), (170, 70), (200, 110)], fill=(48, 140, 210, 255))
        draw.ellipse((60, 150, 100, 190), fill=(40, 40, 40, 255))
        draw.ellipse((160, 150, 200, 190), fill=(40, 40, 40, 255))
    elif kind == "shopping":
        draw.ellipse((48, 48, 208, 208), fill=(242, 184, 48, 255))
        draw.ellipse((78, 78, 178, 178), fill=(255, 214, 96, 255))
    elif kind == "time":
        draw.ellipse((40, 40, 216, 216), fill=(255, 255, 255, 255), outline=(40, 40, 40, 255), width=10)
        draw.line((128, 128, 128, 72), fill=(40, 40, 40, 255), width=8)
        draw.line((128, 128, 172, 148), fill=(220, 70, 70, 255), width=8)
    elif kind == "shapes":
        draw.polygon([(128, 36), (220, 210), (36, 210)], fill=(96, 176, 232, 255))
    elif kind == "animals":
        draw.ellipse((78, 70, 178, 190), fill=(196, 144, 96, 255))
        draw.ellipse((48, 36, 110, 110), fill=(196, 144, 96, 255))
        draw.ellipse((146, 36, 208, 110), fill=(196, 144, 96, 255))
    elif kind == "sport" or kind == "playing":
        draw.ellipse((40, 40, 216, 216), fill=(240, 96, 72, 255))
        draw.arc((40, 40, 216, 216), 20, 200, fill=(255, 255, 255, 255), width=8)
    elif kind == "garden":
        draw.ellipse((98, 40, 158, 100), fill=(236, 84, 120, 255))
        draw.ellipse((48, 88, 118, 158), fill=(246, 196, 72, 255))
        draw.ellipse((138, 88, 208, 158), fill=(96, 176, 96, 255))
        draw.rectangle((118, 150, 138, 220), fill=(72, 140, 72, 255))
    elif kind == "counting":
        draw.ellipse((36, 88, 100, 152), fill=(96, 176, 232, 255))
        draw.ellipse((96, 88, 160, 152), fill=(242, 164, 72, 255))
        draw.ellipse((156, 88, 220, 152), fill=(236, 96, 120, 255))
    else:
        draw.rounded_rectangle((48, 48, 208, 208), radius=36, fill=(120, 96, 220, 255))
        try:
            font = ImageFont.truetype("arialbd.ttf", 120)
        except Exception:
            font = ImageFont.load_default()
        glyph = {"toys": "T", "maths": "+"}.get(kind, "+")
        box = font.getbbox(glyph) if hasattr(font, "getbbox") else (0, 0, 60, 60)
        draw.text(((256 - (box[2] - box[0])) / 2, 70), glyph, fill=(255, 255, 255, 255), font=font)

    folder = Path(tempfile.gettempdir()) / "myintelibooks_stickers"
    folder.mkdir(parents=True, exist_ok=True)
    path = str(folder / f"{kind}.png")
    img.save(path, "PNG")
    cache[kind] = path
    _sticker_file._cache = cache
    return path


def _fit_in_image_box(pdf: FPDF, path: str) -> tuple[float, float, float, float]:
    """Place the scene on the right and return the rectangle it occupies."""
    with Image.open(path) as source:
        width, height = source.size
    if width < 1 or height < 1:
        return (0.0, 0.0, 0.0, 0.0)
    x0 = TEXT_X + TEXT_W + 8
    y0 = 36.0
    max_w = (BORDER_X + BORDER_W) - x0 - 4
    max_h = PAGE_BADGE_Y - y0 - 8
    aspect = width / height
    if max_w / max_h > aspect:
        draw_h = max_h
        draw_w = draw_h * aspect
    else:
        draw_w = max_w
        draw_h = draw_w / aspect
    x = x0 + (max_w - draw_w) / 2
    y = y0
    pdf.image(path, x=x, y=y, w=draw_w, h=draw_h)
    return (x, y, draw_w, draw_h)


def _question_body(question: str) -> str:
    clean = re.sub(r"^\d+\.\s*", "", str(question or ""))
    clean = re.sub(r"(?i)look at the picture!\s*", "", clean)
    clean = re.sub(r"\s+\.", ".", clean).strip()
    sentences = [part.strip() for part in re.split(r"(?<=[.?!])\s+", clean) if part.strip()]
    if len(sentences) > 1:
        return " ".join(sentences[:-1]) + "\n\n" + sentences[-1]
    return clean


def _options_for_page(question: str, raw) -> list[str]:
    correct = ""
    given: list = []
    if isinstance(raw, dict):
        correct = str(raw.get("correct_answer") or raw.get("correct") or "")
        given = list(raw.get("options") or [])
    elif isinstance(raw, (list, tuple)):
        given = list(raw)
    valid = [str(item).strip() for item in given if str(item).strip() and str(item).strip() != "-"]
    if len(valid) >= 2:
        return normalize_trio(correct, valid)["options"]
    return build_mcq(question, allow_network=False)["options"]


def _render_question_page(
    pdf: FPDF,
    *,
    question: str,
    student_name: str,
    adult: str,
    theme: tuple,
    grade_id: str,
    image_path: str | None,
    options: list[str],
    temps: list,
    page_title: str = "",
) -> None:
    """One workbook page. The picture is placed first. Question and options stay to its left."""
    pdf.add_page(orientation="P", format="A4")
    heading = page_heading(str(question), adult=adult, allow_network=True)
    title = (page_title or "").strip() or heading["title"]
    sticker = _sticker_file(heading["sticker"])

    image_left = BORDER_X + BORDER_W
    placed = False
    if image_path and os.path.exists(image_path):
        try:
            image_left = _fit_in_image_box(pdf, image_path)[0]
            placed = True
        except Exception as exc:
            print(f"[PDF WARN] scene image: {exc}")
    if not placed:
        try:
            from app.math_visual_engine import infer_structured_question, render_math_visualization
            card = render_math_visualization(
                infer_structured_question(str(question), grade_id=grade_id),
                card_w=860,
                card_h=1290,
                theme_color=theme,
            )
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            card.save(tmp.name, "PNG")
            temps.append(tmp.name)
            image_left = _fit_in_image_box(pdf, tmp.name)[0]
        except Exception as exc:
            print(f"[PDF MATH CARD WARN] {exc}")

    text_right = image_left - 10
    text_w = max(24.0, text_right - TEXT_X)

    if sticker and os.path.exists(sticker):
        try:
            pdf.image(sticker, x=TEXT_X, y=13, w=14, h=14)
        except Exception as exc:
            print(f"[PDF WARN] sticker: {exc}")

    title_x = TEXT_X + 18
    title_w = max(20.0, text_right - title_x)
    pdf.set_font(TITLE_FONT["family"], "B", 16)
    pdf.set_text_color(*theme)
    title_words = safe_text(title).split()
    title_lines: list[str] = []
    current_title = ""
    for word in title_words:
        trial = word if not current_title else f"{current_title} {word}"
        if current_title and pdf.get_string_width(trial) > title_w:
            title_lines.append(current_title)
            current_title = word
        else:
            current_title = trial
    if current_title:
        title_lines.append(current_title)
    title_y = 16.0
    for index, line in enumerate(title_lines[:2]):
        pdf.set_xy(title_x, title_y + index * 7)
        pdf.cell(title_w, 7, line)
    question_y = max(QUESTION_Y, title_y + max(1, len(title_lines[:2])) * 7 + 4)

    body = _question_body(question)
    font_size, line_h = 14, 7.0
    pdf.set_font(HAND_FONT["family"], "", font_size)
    rough_lines = max(1, int(pdf.get_string_width(safe_text(body.replace("\n", " "))) / max(text_w, 1)) + body.count("\n") + 1)
    while font_size > 11 and question_y + rough_lines * line_h > PAGE_BADGE_Y - 56:
        font_size -= 1
        line_h -= 0.4
        pdf.set_font(HAND_FONT["family"], "", font_size)
        rough_lines = max(1, int(pdf.get_string_width(safe_text(body.replace("\n", " "))) / max(text_w, 1)) + body.count("\n") + 1)

    _draw_question_with_highlighted_names(
        pdf, body, student_name, adult, theme,
        x=TEXT_X, y=question_y, w=text_w, line_h=line_h, font_size=font_size,
        font_family=HAND_FONT["family"],
    )

    opt_y = pdf.get_y() + 6
    _draw_vertical_options(pdf, TEXT_X, opt_y, options[:3], width=text_w)

    pdf.set_draw_color(*theme)
    pdf.set_line_width(1.3)
    pdf.rect(BORDER_X, BORDER_Y, BORDER_W, BORDER_H, style="D", round_corners=True, corner_radius=5)


def generate_pdf(
    student_name: str, grade: str, topic_header_text: str, questions: list,
    image_paths: list = None, question_topics: list = None,
    favourite_colour: str = "", picture_theme: str = "",
    workbook_title: str = "", workbook_subtitle: str = "",
    question_counts: list = None, question_adults: list = None,
    question_options: list = None, cover_image_path: str = None,
    grade_id: str = "",
    backcover_image_path: str | bool | None = None,
    pets: list = None,
    favourite_foods: list = None,
    favourite_sports: list = None,
    favourite_hobbies: list = None,
    favourite_characters: list = None,
    favourite_cartoons: list = None,
) -> bytes:
    if not (grade_id or "").strip():
        raise ValueError(
            "grade_id is required to build the PDF. "
            "Refusing to load another grade's fonts or icons by default."
        )

    # Resolve grade-specific (or shared) font and icon paths
    _resolve_fonts(grade_id)

    theme_accent = _parse_favourite_colour(favourite_colour)
    has_cover = bool(cover_image_path and os.path.exists(cover_image_path))

    # Resolve backcover:
    # If not explicitly specified, auto-load from the backcover folder
    resolved_backcover_path = None
    if backcover_image_path is not False and backcover_image_path != "":
        if backcover_image_path is not None and os.path.exists(str(backcover_image_path)):
            resolved_backcover_path = str(backcover_image_path)
        elif backcover_image_path is None:
            try:
                bc_found = get_backcover_image_path()
                if bc_found and os.path.exists(str(bc_found)):
                    resolved_backcover_path = str(bc_found)
            except Exception:
                resolved_backcover_path = None

    has_backcover = bool(resolved_backcover_path and os.path.exists(resolved_backcover_path))

    pdf = _WorkbookPDF(theme_color=theme_accent, has_cover=has_cover)
    pdf.set_margins(12, 10, 12)
    pdf.set_auto_page_break(auto=False)
    _register_fonts(pdf)

    # Textured background instead of flat white, applied to every add_page().
    pdf.set_page_background(_make_page_texture(theme_accent))
    faded_temps: list[str] = []

    if has_cover:
        _add_cover_page(pdf, cover_image_path, grade_label=grade or grade_id, theme_color=theme_accent)

    for idx, q in enumerate(questions, start=1):
        adult = (question_adults[idx - 1] if question_adults and idx <= len(question_adults) else "") or "a Friend"
        raw_options = question_options[idx - 1] if question_options and idx <= len(question_options) else None
        img_path = image_paths[idx - 1] if image_paths and idx <= len(image_paths) else None
        page_title = str(raw_options.get("title") or "").strip() if isinstance(raw_options, dict) else ""
        _render_question_page(
            pdf,
            question=str(q),
            student_name=student_name,
            adult=adult,
            theme=theme_accent,
            grade_id=grade_id,
            image_path=img_path,
            options=_options_for_page(str(q), raw_options),
            temps=faded_temps,
            page_title=page_title,
        )

    # 5. BACK COVER (appended as final page if backcover image exists)
    if has_backcover:
        _add_backcover_page(pdf, resolved_backcover_path)

    for path in faded_temps:
        try: os.remove(path)
        except Exception: pass

    return bytes(pdf.output())


def cleanup_temp_images(image_paths: list):
    for img_path in image_paths:
        if img_path and os.path.exists(img_path):
            try: os.remove(img_path)
            except Exception: pass