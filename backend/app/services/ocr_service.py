"""Real OCR extraction from uploaded ID document images (Tesseract).

The synthetic Aegis ID cards print labeled fields (NAME / DOB / ID NUMBER) as
a small gray label line followed by the value line, with a light-gray
diagonal SYNTHETIC watermark over everything. Preprocessing thresholds the
image so the light watermark drops to white while the black field text
survives — Tesseract then reads the fields reliably.

Arbitrary real-world documents will mostly extract nothing (all None), which
is the correct, honest failure mode: no signal rather than a fabricated one.
"""

from __future__ import annotations

import logging
import re
from io import BytesIO

import pytesseract
from PIL import Image

logger = logging.getLogger("aegis.ocr")

# Values live on the line after their label on the synthetic cards.
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_ID_NUMBER_RE = re.compile(r"\b(SYN-[0-9A-F]{4}-[0-9A-F]{4})\b", re.IGNORECASE)
_NAME_VALUE_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{2,40}$")

# Lines that are card furniture, never field values.
_NOISE = {"SYNTHETIC", "PHOTO", "ISSUE DATE", "NAME", "DOB", "ID NUMBER"}


def _preprocess(image: Image.Image) -> Image.Image:
    """Upscale + grayscale + hard threshold.

    The cards are 400x250 with 9-13px text — too small for reliable OCR at
    native resolution. 3x LANCZOS upscaling fixes that. The threshold (140,
    empirical) drops the light watermark to white while black text survives.
    """
    upscaled = image.convert("L").resize(
        (image.width * 3, image.height * 3), Image.LANCZOS
    )
    return upscaled.point(lambda p: 0 if p < 140 else 255)


def _value_after_label(lines: list[str], label: str) -> str | None:
    for i, line in enumerate(lines):
        if line.strip().upper() == label:
            for candidate in lines[i + 1 : i + 3]:  # value is the next real line
                value = candidate.strip()
                if value and value.upper() not in _NOISE:
                    return value
    return None


def extract_id_fields(image_bytes: bytes) -> dict:
    """Extract {name, dob, id_number, raw_text} from an ID image via OCR."""
    try:
        image = Image.open(BytesIO(image_bytes))
        raw_text = pytesseract.image_to_string(_preprocess(image), config="--psm 6")
    except Exception as exc:  # noqa: BLE001 - unreadable file, missing binary, etc.
        logger.warning("OCR failed: %s", exc)
        return {"name": None, "dob": None, "id_number": None, "raw_text": ""}

    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

    # -- name: label line first; structural fallback second (the name value is
    # the first multi-word ALL-CAPS line — small gray labels often garble).
    name = _value_after_label(lines, "NAME")
    if not name or not _NAME_VALUE_RE.match(name):
        name = next(
            (
                ln
                for ln in lines
                if re.match(r"^[A-Z][A-Z]+(?: [A-Z][A-Z'-]+)+$", ln)
                and "SYNTHETIC" not in ln
                and "CARD" not in ln
            ),
            None,
        )

    # -- dob: the card prints DOB above ISSUE DATE, so the FIRST date wins.
    dob_line = _value_after_label(lines, "DOB")
    if dob_line and _DATE_RE.search(dob_line):
        dob = _DATE_RE.search(dob_line).group(1)
    else:
        dates = _DATE_RE.findall(raw_text)
        dob = dates[0] if dates else None

    # -- id number: strict pattern, then a fuzzy variant tolerating a dropped
    # dash or 5<->S style confusions in the hex block.
    id_match = _ID_NUMBER_RE.search(raw_text)
    if id_match:
        id_number = id_match.group(1).upper()
    else:
        fuzzy = re.search(r"\bSYN[-_ ]?([0-9A-Z]{4})[-_ ]?([0-9A-Z]{4})\b", raw_text, re.I)
        id_number = f"SYN-{fuzzy.group(1).upper()}-{fuzzy.group(2).upper()}" if fuzzy else None

    return {"name": name, "dob": dob, "id_number": id_number, "raw_text": raw_text}


def normalize_name(name: str | None) -> str:
    """Case/punctuation/whitespace-insensitive form for name comparison."""
    if not name:
        return ""
    return re.sub(r"[^a-z ]", "", name.lower().replace("-", " ")).strip()


def names_match(a: str | None, b: str | None) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    return bool(na) and bool(nb) and " ".join(na.split()) == " ".join(nb.split())
