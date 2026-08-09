"""
PDF generation functions
"""
import difflib
import os
import re
import tempfile
from pathlib import Path

import streamlit as st
from fpdf import FPDF
from PIL import Image, ImageChops
from utils import safe_text


class _WorkbookPDF(FPDF):
    """Colourful landscape worksheet PDF with a consistent page footer."""

    def __init__(self, theme_color=(78, 86, 190), *args, **kwargs):
        kwargs.setdefault("orientation", "L")
        kwargs.setdefault("format", "A4")
        super().__init__(*args, **kwargs)
        self.theme_color = theme_color

    def footer(self):
        self.set_y(-10)
        self.set_draw_color(*_mix(self.theme_color, (255, 255, 255), 0.78))
        self.line(14, self.get_y(), self.w - 14, self.get_y())
        self.ln(1)
        self.set_font("Arial", "I", 8)
        self.set_text_color(*_mix(self.theme_color, (70, 70, 85), 0.45))
        self.cell(
            0,
            5,
            safe_text(f"My Maths Practice Book  |  Page {self.page_no()}"),
            align="C",
        )


# Landscape A4 (mm)
_PAGE_W = 297.0
_PAGE_H = 210.0


_TOPIC_PALETTES = [
    ((78, 86, 190), (238, 239, 255)),   # indigo
    ((225, 91, 119), (255, 239, 244)),  # rose
    ((23, 148, 132), (234, 250, 247)),  # teal
    ((232, 139, 45), (255, 246, 232)),  # orange
    ((128, 82, 174), (247, 239, 255)),  # purple
    ((49, 126, 193), (235, 246, 255)),  # blue
]


_COLOUR_NAMES = {
    "red": (214, 62, 72),
    "blue": (54, 111, 196),
    "light blue": (75, 155, 215),
    "sky blue": (74, 157, 211),
    "navy": (43, 62, 128),
    "green": (44, 145, 94),
    "light green": (82, 165, 105),
    "dark green": (35, 108, 72),
    "pink": (220, 87, 145),
    "purple": (126, 76, 173),
    "violet": (126, 76, 173),
    "orange": (225, 126, 47),
    "yellow": (213, 166, 35),
    "gold": (194, 145, 35),
    "teal": (25, 142, 137),
    "turquoise": (31, 157, 163),
    "brown": (139, 92, 66),
    "grey": (105, 113, 128),
    "gray": (105, 113, 128),
    "black": (60, 64, 75),
    "white": (125, 132, 150),
}


def _mix(a, b, amount: float):
    """Mix RGB colour a towards b by amount."""
    amount = max(0.0, min(1.0, amount))
    return tuple(round(a[i] * (1 - amount) + b[i] * amount) for i in range(3))


def _parse_favourite_colour(value: str):
    """Resolve common colour names and #RRGGBB values to a printable accent."""
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if not text:
        return (78, 86, 190)
    match = re.fullmatch(r"#?([0-9a-f]{6})", text)
    if match:
        code = match.group(1)
        return tuple(int(code[i:i + 2], 16) for i in (0, 2, 4))
    for name in sorted(_COLOUR_NAMES, key=len, reverse=True):
        if name in text:
            return _COLOUR_NAMES[name]
    # Stable fallback for creative colour descriptions such as "ocean".
    seed = sum((i + 1) * ord(char) for i, char in enumerate(text))
    return _TOPIC_PALETTES[seed % len(_TOPIC_PALETTES)][0]


_THEME_GROUPS = (
    ("dinosaur", ("dinosaur", "dinosaurs", "dino", "dinos", "jurassic", "trex",
                  "t-rex", "raptor", "rex", "prehistoric")),
    ("spider", ("spiderman", "spider-man", "spider", "spiders", "web", "webs",
                "avengers", "superhero", "superheroes", "marvel")),
    ("space", ("space", "planet", "planets", "rocket", "rockets", "astronaut",
               "galaxy", "moon", "stars", "starwars", "alien")),
    ("football", ("football", "soccer", "ball", "cricket", "basketball",
                  "sports", "sport")),
    ("christmas", ("christmas", "xmas", "snow", "snowman", "santa", "winter",
                   "holiday")),
    ("unicorn", ("unicorn", "unicorns", "rainbow", "fairy", "fairies",
                 "princess", "magic", "butterfly", "butterflies")),
    ("ocean", ("ocean", "sea", "fish", "fishes", "mermaid", "shark", "dolphin",
               "whale", "underwater", "beach")),
    ("car", ("car", "cars", "truck", "trucks", "train", "trains", "plane",
             "planes", "racing", "vehicle")),
    ("animal", ("animal", "animals", "cat", "cats", "kitten", "dog", "dogs",
                "puppy", "lion", "tiger", "elephant", "bear", "panda", "zoo")),
    ("flower", ("flower", "flowers", "garden", "nature", "tree", "trees",
                "plant", "plants")),
)


def _theme_kind(theme: str) -> str:
    """
    Resolve a free-text picture preference to a decoration set.

    Parents type this field freehand, so matching is done per word with a
    fuzzy pass for near misses like "dinasaur" rather than requiring the
    exact keyword to appear.
    """
    text = str(theme or "").lower()
    if not text.strip():
        return "generic"

    for kind, words in _THEME_GROUPS:
        if any(word in text for word in words):
            return kind

    tokens = [t for t in re.split(r"[^a-z]+", text) if len(t) > 3]
    for kind, words in _THEME_GROUPS:
        for token in tokens:
            if difflib.get_close_matches(token, words, n=1, cutoff=0.78):
                return kind
    return "generic"


def _draw_star(pdf: FPDF, x: float, y: float, radius: float):
    pdf.line(x - radius, y, x + radius, y)
    pdf.line(x, y - radius, x, y + radius)
    pdf.line(x - radius * .7, y - radius * .7, x + radius * .7, y + radius * .7)
    pdf.line(x + radius * .7, y - radius * .7, x - radius * .7, y + radius * .7)


def _draw_theme_background(pdf: FPDF, theme: str, accent):
    """
    Draw very pale theme objects behind the worksheet.

    FPDF has no reliable transparency across versions, so translucency is
    simulated by mixing the favourite colour 91% into white.
    """
    # Paint an explicit paper colour; some PDF previewers render an untouched
    # page canvas as transparent/black.
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(0, 0, _PAGE_W, _PAGE_H, "F")
    if not str(theme or "").strip():
        return
    pale = _mix(accent, (255, 255, 255), 0.91)
    pdf.set_draw_color(*pale)
    pdf.set_fill_color(*_mix(accent, (255, 255, 255), 0.94))
    pdf.set_line_width(0.7)
    kind = _theme_kind(theme)
    # Landscape anchors — keep clear of the right-side illustration
    anchors = ((10, 42), (140, 48), (12, 110), (145, 118), (14, 175), (138, 182))

    for x, y in anchors:
        if kind == "dinosaur":
            # A large footprint with three toe prints.
            pdf.ellipse(x - 4, y - 6, 8, 12, "F")
            pdf.ellipse(x - 6, y - 9, 3, 4, "F")
            pdf.ellipse(x - 1.5, y - 11, 3, 4, "F")
            pdf.ellipse(x + 3, y - 9, 3, 4, "F")
        elif kind == "spider":
            # Spider web motif; evocative without copying a character.
            for radius in (3, 6, 9):
                pdf.ellipse(x - radius, y - radius, radius * 2, radius * 2)
            for angle_x, angle_y in ((10, 0), (0, 10), (7, 7), (7, -7)):
                pdf.line(x - angle_x, y - angle_y, x + angle_x, y + angle_y)
        elif kind == "football":
            pdf.ellipse(x - 8, y - 8, 16, 16)
            pdf.ellipse(x - 2, y - 2, 4, 4, "F")
            for dx, dy in ((0, -7), (7, 0), (0, 7), (-7, 0)):
                pdf.line(x, y, x + dx, y + dy)
        elif kind == "space":
            pdf.ellipse(x - 6, y - 6, 12, 12, "F")
            pdf.ellipse(x - 10, y - 2, 20, 4)
            _draw_star(pdf, x + 9, y - 9, 2)
        elif kind == "christmas":
            for spread, yy in ((7, y + 7), (5, y + 2), (3, y - 3)):
                pdf.line(x, y - 9, x - spread, yy)
                pdf.line(x, y - 9, x + spread, yy)
                pdf.line(x - spread, yy, x + spread, yy)
            pdf.line(x, y + 7, x, y + 11)
        elif kind == "unicorn":
            _draw_star(pdf, x, y, 7)
            _draw_star(pdf, x + 8, y - 8, 2.5)
            _draw_star(pdf, x - 7, y + 8, 2)
        elif kind == "ocean":
            pdf.ellipse(x - 7, y - 4, 12, 8, "F")
            pdf.line(x + 5, y, x + 10, y - 5)
            pdf.line(x + 5, y, x + 10, y + 5)
            pdf.line(x + 10, y - 5, x + 10, y + 5)
        elif kind == "car":
            pdf.rect(x - 9, y - 2, 18, 6, "F")
            pdf.ellipse(x - 8, y - 7, 12, 6, "F")
            pdf.ellipse(x - 7, y + 3, 5, 5)
            pdf.ellipse(x + 2, y + 3, 5, 5)
        elif kind == "animal":
            # Paw print: pad plus four toes.
            pdf.ellipse(x - 5, y - 2, 10, 8, "F")
            for dx in (-6, -2, 2, 6):
                pdf.ellipse(x + dx - 1.5, y - 8, 3.4, 4.4, "F")
        elif kind == "flower":
            for dx, dy in ((0, -6), (6, 0), (0, 6), (-6, 0)):
                pdf.ellipse(x + dx - 3.5, y + dy - 3.5, 7, 7, "F")
            pdf.ellipse(x - 2.5, y - 2.5, 5, 5)
        else:
            # Neutral translucent bubbles for any unrecognised preference.
            pdf.ellipse(x - 7, y - 7, 14, 14)
            pdf.ellipse(x + 4, y - 10, 5, 5, "F")


def _possessive_name(name: str) -> str:
    name = (name or "").strip() or "Your"
    if name.lower().endswith("s"):
        return f"{name}'"
    return f"{name}'s"


def _resolve_marker_font() -> str | None:
    """Prefer a thick, kid-friendly marker / chalkboard style face."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Chalkduster.ttf",
        "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
        "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
        str(Path(__file__).parent / "fonts" / "Chalkduster.ttf"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _register_fonts(pdf: FPDF) -> bool:
    """Register marker question font. Returns True if marker face is available."""
    marker = _resolve_marker_font()
    if not marker:
        return False
    try:
        pdf.add_font("MarkerQ", "", marker)
        pdf.add_font("MarkerQ", "B", marker)
        return True
    except Exception:
        return False


def _soft_corner_image(src_path: str, dest_path: str, *, size_px: int = 900) -> str:
    """
    Prepare a right-side illustration: square crop, soft fade on the
    left (and light top) edge so it blends into the page beside the question.

    Fades are baked onto a white background so PDF viewers that ignore
    PNG alpha still show a smooth blend into the page.
    """
    im = Image.open(src_path).convert("RGBA")
    # Centre-crop to square then resize
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize(
        (size_px, size_px), Image.Resampling.LANCZOS
    )

    # Stronger left fade for side-by-side landscape layout
    mask = Image.new("L", (size_px, size_px), 255)
    fade_l = max(50, size_px // 3)
    fade_t = max(28, size_px // 6)
    for i in range(fade_l):
        a = int(255 * (i / fade_l) ** 1.1)
        col = Image.new("L", (1, size_px), a)
        mask.paste(col, (i, 0))
    for i in range(fade_t):
        a = int(255 * (i / fade_t) ** 1.15)
        row = Image.new("L", (size_px, 1), a)
        existing = mask.crop((0, i, size_px, i + 1))
        mask.paste(ImageChops.darker(existing, row), (0, i))

    alpha = ImageChops.multiply(im.split()[-1], mask)
    im.putalpha(alpha)

    bg = Image.new("RGB", (size_px, size_px), (255, 255, 255))
    bg.paste(im, (0, 0), im)
    bg.save(dest_path, format="PNG")
    return dest_path


def build_mcq_options(
    question: str,
    *,
    count: int | None = None,
    adult_name: str | None = None,
) -> tuple[list[str], str]:
    """
    Build 4 Year-1 friendly choices and the correct answer string.
    Uses picture count / adult name when available.
    """
    q = (question or "").strip()
    low = q.lower()
    adult = (adult_name or "").strip() or "Mum"

    # Yes / no
    if re.search(r"\b(are there|is that|do you|can you see)\b.*\?", low) and re.search(
        r"\b(more than|less than|halves|equal)\b", low
    ):
        # Prefer Yes when count supports "more than 2"
        correct = "Yes"
        if count is not None and re.search(r"more than\s+(\d+)", low):
            thr = int(re.search(r"more than\s+(\d+)", low).group(1))
            correct = "Yes" if count > thr else "No"
        elif count is not None and re.search(r"less than\s+(\d+)", low):
            thr = int(re.search(r"less than\s+(\d+)", low).group(1))
            correct = "Yes" if count < thr else "No"
        opts = [correct, "No" if correct == "Yes" else "Yes", "Maybe", "I don't know"]
        # unique preserve order
        seen, out = set(), []
        for o in opts:
            if o not in seen:
                seen.add(o)
                out.append(o)
        while len(out) < 4:
            out.append(f"Option {len(out)+1}")
        return out[:4], correct

    # Who is with you
    if re.search(r"\bwho\b", low):
        distractors = [n for n in ("Mum", "Dad", "Grandma", "Grandad", "a friend") if n.lower() != adult.lower()]
        opts = [adult] + distractors[:3]
        return opts[:4], adult

    # Counting / how many / write the number
    if count is not None and count >= 0:
        correct = str(count)
        pool = [count - 2, count - 1, count, count + 1, count + 2, count + 3]
        nums = []
        for n in pool:
            if n >= 0 and str(n) not in nums:
                nums.append(str(n))
        # Ensure correct included, take 4
        if correct not in nums:
            nums.insert(0, correct)
        # Stable shuffle by question text
        seed = sum(ord(c) for c in low) or 1
        ordered = [correct] + [n for n in nums if n != correct]
        # Rotate distractors
        distractors = ordered[1:]
        distractors = distractors[seed % max(1, len(distractors)):] + distractors[: seed % max(1, len(distractors))]
        opts = [correct] + distractors
        opts = list(dict.fromkeys(opts))[:4]
        # Shuffle display order but keep correct known
        rot = seed % 4
        opts = opts[rot:] + opts[:rot]
        while len(opts) < 4:
            opts.append(str(count + len(opts)))
        return opts[:4], correct

    # Fallback generic
    opts = ["A", "B", "C", "D"]
    return opts, "A"


def _draw_option_row(pdf: FPDF, x: float, y: float, letter: str, text: str, accent, marker: bool):
    """Draw one multiple-choice bubble + label."""
    # Circle bubble
    pdf.set_draw_color(*accent)
    pdf.set_line_width(0.8)
    pdf.ellipse(x, y, 7, 7)
    pdf.set_xy(x + 0.5, y + 0.8)
    pdf.set_font("MarkerQ" if marker else "Arial", "B", 9)
    pdf.set_text_color(*accent)
    pdf.cell(6, 5, safe_text(letter), align="C")
    pdf.set_xy(x + 10, y + 0.5)
    if marker:
        pdf.set_font("MarkerQ", "", 13)
    else:
        pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(40, 44, 60)
    pdf.cell(90, 7, safe_text(str(text)))


def build_workbook_title(
    student_name: str,
    *,
    scene_slots: list | None = None,
    family_names: dict | None = None,
    favourite_food: str = "",
    favourite_hobby: str = "",
    favourite_foods: list | None = None,
    favourite_hobbies: list | None = None,
) -> tuple[str, str]:
    """
    Build a personalised workbook title / subtitle.

    Example: ("Oliver's Kitchen Maths with Saud", "Personalised Year 1 practice")
    """
    family_names = family_names or {}
    slots = list(scene_slots or [])
    poss = _possessive_name(student_name)

    adults: list[str] = []
    families: list[str] = []
    for slot in slots:
        role = (slot.get("adult_role") or "").strip()
        if not role:
            continue
        fam = (slot.get("scene_family") or "kitchen").strip().lower()
        families.append(fam)
        raw = (family_names.get(role) or "").strip()
        placeholders = {role, "mother", "father", "grandmother", "grandfather", "mum", "dad"}
        if raw and raw.lower() not in placeholders:
            label = raw
        else:
            label = {
                "mother": "Mum",
                "father": "Dad",
                "grandmother": "Grandma",
                "grandfather": "Grandad",
            }.get(role, role.replace("_", " ").title())
        if label not in adults:
            adults.append(label)

    # Setting word from scenes
    uniq_fam = list(dict.fromkeys(families)) if families else []
    if uniq_fam == ["hobby"]:
        setting = "Park"
    elif uniq_fam == ["kitchen"] or not uniq_fam:
        setting = "Kitchen"
    else:
        setting = "Family"

    # Theme hint from foods / hobbies (support list or legacy single string)
    foods = [str(x).strip() for x in (favourite_foods or []) if str(x).strip()]
    hobbies = [str(x).strip() for x in (favourite_hobbies or []) if str(x).strip()]
    if not foods and (favourite_food or "").strip():
        foods = [(favourite_food or "").strip()]
    if not hobbies and (favourite_hobby or "").strip():
        hobbies = [(favourite_hobby or "").strip()]
    foods = [f for f in foods if f.lower() not in {"select", ""}]
    hobbies = [h for h in hobbies if h.lower() not in {"select", ""}]
    # Prefer labels already on scene slots when present
    slot_labels = []
    for s in slots:
        lab = (s.get("object_label") or "").strip()
        if lab and lab not in slot_labels:
            slot_labels.append(lab)
    theme_parts = slot_labels[:3] if slot_labels else (foods[:2] + hobbies[:1])
    theme_bit = " · ".join(theme_parts)

    if adults:
        with_who = adults[0] if len(adults) == 1 else " & ".join(adults[:2])
        title = f"{poss} {setting} Maths with {with_who}"
    else:
        title = f"{poss} {setting} Maths Adventure"

    if theme_bit:
        subtitle = f"Personalised Year 1 practice · {theme_bit}"
    else:
        subtitle = "Personalised Year 1 practice workbook"
    return title, subtitle


def _add_themed_page(
    pdf: FPDF,
    student_name: str,
    grade_display: str,
    first: bool,
    theme: str,
    accent,
    workbook_title: str = "",
    workbook_subtitle: str = "",
    use_marker: bool = False,
):
    pdf.add_page()
    _draw_theme_background(pdf, theme, accent)
    _draw_page_heading(
        pdf,
        student_name,
        grade_display,
        first=first,
        accent=accent,
        workbook_title=workbook_title,
        workbook_subtitle=workbook_subtitle,
        use_marker=use_marker,
    )


def _topic_palette(topic: str, index: int, favourite=None):
    """Return a stable accent/pastel pair for a topic."""
    if topic:
        palette_index = sum(ord(char) for char in topic.lower()) % len(_TOPIC_PALETTES)
    else:
        palette_index = index % len(_TOPIC_PALETTES)
    topic_accent = _TOPIC_PALETTES[palette_index][0]
    accent = _mix(favourite, topic_accent, 0.22) if favourite else topic_accent
    return accent, _mix(accent, (255, 255, 255), 0.88)


def _draw_page_heading(
    pdf: FPDF,
    student_name: str,
    grade_display: str,
    first: bool,
    accent=(52, 61, 139),
    workbook_title: str = "",
    workbook_subtitle: str = "",
    use_marker: bool = False,
):
    """Draw the main cover banner or a compact continuation banner."""
    title = (workbook_title or "").strip() or f"{_possessive_name(student_name)} Maths Adventure"
    # Marker faces read smaller — bump size; shrink a bit for long titles
    if use_marker:
        title_size = 20 if len(title) > 40 else (22 if len(title) > 28 else 24)
        cont_size = 13 if len(title) > 40 else 15
    else:
        title_size = 18 if len(title) > 36 else 20
        cont_size = 11 if len(title) > 40 else 12

    if first:
        pdf.set_fill_color(*_mix(accent, (25, 28, 50), 0.18))
        pdf.rect(0, 0, _PAGE_W, 36 if use_marker else 32, "F")
        pdf.set_xy(14, 7 if use_marker else 8)
        if use_marker:
            pdf.set_font("MarkerQ", "B", title_size)
        else:
            pdf.set_font("Arial", "B", title_size)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(
            _PAGE_W - 28,
            11 if use_marker else 9,
            safe_text(title),
            align="C",
        )
        pdf.set_xy(14, 20 if use_marker else 19)
        pdf.set_font("Arial", "", 10)
        pdf.set_text_color(*_mix(accent, (255, 255, 255), 0.84))
        sub = (workbook_subtitle or "").strip() or f"Personalised {grade_display} practice workbook"
        pdf.cell(
            _PAGE_W - 28,
            6,
            safe_text(sub),
            align="C",
        )
        pdf.set_y(40 if use_marker else 36)
    else:
        pdf.set_fill_color(*_mix(accent, (25, 28, 50), 0.18))
        pdf.rect(0, 0, _PAGE_W, 18 if use_marker else 16, "F")
        pdf.set_xy(14, 4)
        if use_marker:
            pdf.set_font("MarkerQ", "B", cont_size)
        else:
            pdf.set_font("Arial", "B", cont_size)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(
            _PAGE_W - 28,
            9 if use_marker else 7,
            safe_text(title),
            align="C",
        )
        pdf.set_y(22 if use_marker else 20)


def generate_pdf(
    student_name: str,
    grade: str,
    topic_header_text: str,
    questions: list,
    image_paths: list = None,
    question_topics: list | None = None,
    favourite_colour: str = "",
    picture_theme: str = "",
    workbook_title: str = "",
    workbook_subtitle: str = "",
    question_counts: list | None = None,
    question_adults: list | None = None,
    question_options: list | None = None,
) -> bytes:
    """
    Generate a landscape PDF workbook: question + MCQ on the left,
    soft-faded illustration on the right at roughly the same height.
    """
    print(f"DEBUG PDF: Starting with {len(questions)} questions")
    print(f"DEBUG PDF: image_paths = {image_paths}")

    question_topics = list(question_topics or [])
    while len(question_topics) < len(questions):
        question_topics.append("")
    question_counts = list(question_counts or [])
    question_adults = list(question_adults or [])
    question_options = list(question_options or [])
    while len(question_counts) < len(questions):
        question_counts.append(None)
    while len(question_adults) < len(questions):
        question_adults.append(None)
    while len(question_options) < len(questions):
        question_options.append(None)

    theme_accent = _parse_favourite_colour(favourite_colour)
    print(
        f"DEBUG PDF: colour={favourite_colour or '(none)'} -> rgb{theme_accent}, "
        f"theme={picture_theme or '(none)'} -> {_theme_kind(picture_theme)}"
    )
    pdf = _WorkbookPDF(theme_color=theme_accent)
    pdf.set_margins(12, 10, 12)
    pdf.set_auto_page_break(auto=False)
    has_marker = _register_fonts(pdf)

    grade_display = grade.replace("Grade", "Year")
    title = workbook_title or f"{_possessive_name(student_name)} Maths Adventure"
    subtitle = workbook_subtitle or f"Personalised {grade_display} practice workbook"
    print(f"DEBUG PDF: title={title!r} marker_font={has_marker}")
    _add_themed_page(
        pdf,
        student_name,
        grade_display,
        first=True,
        theme=picture_theme,
        accent=theme_accent,
        workbook_title=title,
        workbook_subtitle=subtitle,
        use_marker=has_marker,
    )

    # Focus panel (first page only) — left band on landscape page
    pdf.set_fill_color(*_mix(theme_accent, (255, 255, 255), 0.91))
    pdf.set_draw_color(*_mix(theme_accent, (255, 255, 255), 0.74))
    focus_w = 160
    pdf.rect(14, pdf.get_y(), focus_w, 14, "DF")
    pdf.set_xy(18, pdf.get_y() + 2)
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(*_mix(theme_accent, (35, 38, 55), 0.22))
    pdf.cell(30, 4, safe_text("TODAY'S FOCUS"))
    pdf.set_font("Arial", "", 9)
    pdf.set_text_color(55, 60, 85)
    pdf.set_xy(48, pdf.get_y())
    pdf.multi_cell(focus_w - 40, 4, safe_text(topic_header_text or "Mixed maths practice"))

    faded_temps: list[str] = []
    letters = "ABCD"

    for idx, q in enumerate(questions, start=1):
        topic_label = str(question_topics[idx - 1] or "").strip()
        accent, pastel = _topic_palette(topic_label, idx - 1, theme_accent)
        count = question_counts[idx - 1]
        try:
            count = int(count) if count is not None else None
        except (TypeError, ValueError):
            count = None
        adult = question_adults[idx - 1]

        prebuilt = question_options[idx - 1]
        if isinstance(prebuilt, dict):
            opts = list(prebuilt.get("options") or [])
            correct = str(prebuilt.get("correct_answer") or "")
        elif isinstance(prebuilt, (list, tuple)) and prebuilt:
            opts = list(prebuilt)
            correct = ""
        else:
            opts, correct = build_mcq_options(str(q), count=count, adult_name=adult)
        while len(opts) < 4:
            opts.append("—")
        opts = opts[:4]

        img_path = None
        if image_paths and idx <= len(image_paths) and image_paths[idx - 1]:
            candidate = image_paths[idx - 1]
            if candidate and os.path.exists(candidate):
                img_path = candidate

        if idx > 1:
            _add_themed_page(
                pdf,
                student_name,
                grade_display,
                first=False,
                theme=picture_theme,
                accent=theme_accent,
                workbook_title=title,
                workbook_subtitle=subtitle,
                use_marker=has_marker,
            )
        else:
            pdf.set_y(max(pdf.get_y() + 4, 56))

        # Landscape: question left, picture right — same vertical level
        content_top = pdf.get_y()
        img_w_mm = 138.0
        img_x = _PAGE_W - 8 - img_w_mm
        img_y = content_top
        max_img = _PAGE_H - 14 - content_top
        if img_w_mm > max_img:
            img_w_mm = max(100.0, max_img)
            img_x = _PAGE_W - 8 - img_w_mm

        faded_for_page = None
        if img_path:
            try:
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.close()
                faded_for_page = _soft_corner_image(img_path, tmp.name, size_px=1100)
                faded_temps.append(faded_for_page)
            except Exception as e:
                st.warning(f"Could not prepare image for question {idx}: {e}")
                faded_for_page = None

        left_w = (img_x - 18) if faded_for_page else (_PAGE_W - 28)

        y = content_top
        pdf.set_fill_color(*accent)
        pdf.set_xy(14, y)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 11)
        pdf.cell(28, 9, safe_text(f"Q {idx}"), fill=True, align="C")

        pdf.set_xy(46, y + 1)
        pdf.set_fill_color(*pastel)
        pdf.set_text_color(*accent)
        pdf.set_font("Arial", "B", 9)
        badge = safe_text((topic_label or "Maths").upper())
        pdf.cell(min(left_w - 40, 4.2 * len(badge) + 8), 7, badge, fill=True, align="C")
        y += 14

        pdf.set_xy(14, y)
        if has_marker:
            pdf.set_font("MarkerQ", "", 15)
        else:
            pdf.set_font("Arial", "B", 13)
        pdf.set_text_color(32, 36, 52)
        pdf.multi_cell(left_w, 7, safe_text(str(q)))
        y = pdf.get_y() + 6

        pdf.set_xy(14, y)
        pdf.set_font("Arial", "B", 9)
        pdf.set_text_color(*accent)
        pdf.cell(100, 5, safe_text("Circle the correct answer"))
        y += 8

        opt_y_max = _PAGE_H - 22
        for i, opt in enumerate(opts):
            if y > opt_y_max:
                break
            _draw_option_row(pdf, 16, y, letters[i], opt, accent, has_marker)
            y += 11

        y += 3
        if y <= opt_y_max:
            pdf.set_xy(14, y)
            pdf.set_font("Arial", "B", 9)
            pdf.set_text_color(*accent)
            pdf.cell(28, 5, safe_text("I think…"))
            pdf.set_draw_color(*accent)
            pdf.set_line_width(0.6)
            line_end = min(14 + left_w - 8, img_x - 6) if faded_for_page else (14 + left_w - 8)
            pdf.line(42, y + 4, max(50, line_end), y + 4)

        if correct:
            pdf.set_xy(14, _PAGE_H - 16)
            pdf.set_font("Arial", "I", 7)
            pdf.set_text_color(190, 190, 200)
            pdf.cell(80, 4, safe_text(f"Answer key: {correct}"))

        if faded_for_page:
            try:
                pdf.image(faded_for_page, x=img_x, y=img_y, w=img_w_mm, h=img_w_mm)
            except Exception as e:
                st.warning(f"Could not add image for question {idx}: {e}")

    for path in faded_temps:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    return bytes(pdf.output())


def cleanup_temp_images(image_paths: list):
    """Remove temporary image files."""
    for img_path in image_paths:
        if img_path and os.path.exists(img_path):
            try:
                os.remove(img_path)
            except Exception:
                pass
