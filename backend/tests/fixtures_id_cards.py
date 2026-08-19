"""Fabricated ID-card fixtures for OCR testing.

Every fixture is GENERATED LOCALLY with Pillow and contains entirely invented
data. No real person's document, name, or number appears here or is committed
to the repository.

Variants simulate the real-world conditions that defeat threshold-based OCR:
a security-pattern background, a skewed scan, and uneven lighting.
"""

from __future__ import annotations

import math
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

FAKE_PAN = {
    "name": "TESTUSER SPECIMEN",
    "father": "SPECIMEN GUARDIAN",
    "number": "ABCDE1234F",
    "dob_printed": "15/08/1990",
    "dob_iso": "1990-08-15",
}

VARIANTS = ("clean", "textured", "rotated", "lowcontrast")


def _font(size: int, bold: bool = False):
    path = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    )
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size=size)


def _draw_card(background: Image.Image) -> Image.Image:
    draw = ImageDraw.Draw(background)
    draw.text((30, 24), "INCOME TAX DEPARTMENT", font=_font(26, True), fill="black")
    draw.text((30, 60), "GOVT. OF INDIA", font=_font(22), fill="black")

    y = 130
    for label, value in [
        ("Permanent Account Number", FAKE_PAN["number"]),
        ("Name", FAKE_PAN["name"]),
        ("Father's Name", FAKE_PAN["father"]),
        ("Date of Birth", FAKE_PAN["dob_printed"]),
    ]:
        draw.text((30, y), label, font=_font(22), fill="black")
        draw.text((30, y + 34), value, font=_font(30, True), fill="black")
        y += 95
    return background


def _security_pattern(size: tuple[int, int]) -> Image.Image:
    """Faint guilloche-style waves, as printed on real identity documents."""
    canvas = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(canvas)
    width, height = size
    for offset in range(-height, height * 2, 14):
        points = [
            (x, offset + int(18 * math.sin(x / 38.0)))
            for x in range(0, width + 1, 8)
        ]
        draw.line(points, fill=(214, 222, 236), width=2)
    for offset in range(-width, width * 2, 26):
        draw.line([(offset, 0), (offset + height, height)], fill=(226, 232, 244), width=1)
    return canvas


def fake_pan_card(variant: str = "clean") -> bytes:
    """Render a fabricated PAN-style card under the requested condition."""
    size = (860, 540)

    if variant == "textured":
        card = _draw_card(_security_pattern(size))
    else:
        card = _draw_card(Image.new("RGB", size, "white"))

    if variant == "rotated":
        # A skewed phone photo / crooked scan.
        card = card.rotate(-7, resample=Image.BICUBIC, expand=True, fillcolor="white")

    if variant == "lowcontrast":
        # Grey down the ink and lay a diagonal lighting gradient over the card,
        # so no single global threshold separates text from background.
        faded = Image.blend(card, Image.new("RGB", card.size, (255, 255, 255)), 0.45)
        width, height = faded.size
        gradient = Image.new("L", (width, height))
        gdraw = ImageDraw.Draw(gradient)
        for x in range(width):
            gdraw.line([(x, 0), (x, height)], fill=int(215 - 95 * (x / width)))
        shadow = Image.new("RGB", faded.size, (90, 90, 95))
        card = Image.composite(faded, shadow, gradient)

    buffer = BytesIO()
    card.save(buffer, "PNG")
    return buffer.getvalue()
