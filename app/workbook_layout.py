"""
Question-page measurements for every grade.

The question lives in the left column. The picture sits on a brown wooden
board on the right. These numbers are the source of truth for both the PDF
and the image-generation prompt, so the generated picture matches the box
it is printed in.

A4 page: 210 mm × 297 mm.

Brown board:  x=92 mm, y=38 mm, 106 mm × 171 mm
Picture box:  x=96 mm, y=42 mm,  98 mm × 147 mm   (exactly 2:3)
Generate at:  1024 × 1536 pixels                  (same 2:3 ratio)

The picture is inset 4 mm from the left, right and top of the board, and
20 mm of the brown board stays visible underneath it.
The question column ends at x=86 mm, so it never enters the board (x=92 mm).
"""

from __future__ import annotations

from PIL import Image

PAGE_W = 210.0
PAGE_H = 297.0

BORDER_X = 7.0
BORDER_Y = 7.0
BORDER_W = 196.0
BORDER_H = 283.0

TEXT_X = 14.0
TEXT_W = 72.0
TEXT_RIGHT = TEXT_X + TEXT_W  # 86 mm
QUESTION_Y = 42.0

STAGE_X = 92.0
STAGE_Y = 38.0
STAGE_W = 106.0
STAGE_H = 171.0  # bottom edge at 209 mm
STAGE_COLOR = (176, 122, 68)
STAGE_EDGE = (132, 84, 42)

IMAGE_X = 96.0
IMAGE_Y = 42.0
IMAGE_W = 98.0
IMAGE_H = 147.0  # 98 * 3/2 = 147, exactly 2:3

IMAGE_PX_W = 1024
IMAGE_PX_H = 1536

PAGE_BADGE_D = 12.0
PAGE_BADGE_Y = 272.0


def to_question_image(img: Image.Image) -> Image.Image:
    """
    Force a scene onto the picture window inside the brown board.

    The window is 98 mm by 147 mm, inset from the board so the wood stays
    visible around it. Any returned picture is center-cropped to that 2:3
    ratio and resized to 1024 by 1536 pixels.
    """
    image = img.convert("RGB")
    width, height = image.size
    if width < 1 or height < 1:
        return image
    target = IMAGE_PX_W / IMAGE_PX_H
    current = width / height
    if abs(current - target) >= 0.004:
        if current > target:
            new_width = max(1, int(round(height * target)))
            left = max(0, (width - new_width) // 2)
            image = image.crop((left, 0, min(width, left + new_width), height))
        else:
            new_height = max(1, int(round(width / target)))
            top = max(0, (height - new_height) // 2)
            image = image.crop((0, top, width, min(height, top + new_height)))
    if image.size != (IMAGE_PX_W, IMAGE_PX_H):
        image = image.resize((IMAGE_PX_W, IMAGE_PX_H), Image.Resampling.LANCZOS)
    return image
