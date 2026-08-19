"""Real OCR extraction from uploaded ID document images (Tesseract).

Two extraction strategies, tried in order:

1. **synthetic_template** — the Aegis demo cards print labeled fields
   (NAME / DOB / ID NUMBER) as a small gray label line above the value, with
   a light diagonal SYNTHETIC watermark. This is the controlled path that
   powers the demo scenarios and must stay exactly reliable.

2. **generalized_layout** — a best-effort reader for real-world ID layouts
   (Indian PAN/Aadhaar-style): label-anchored search over OCR *lines*,
   tolerant of "Label: value" and "Label\\nvalue" arrangements, multiple date
   formats, and PAN-style document numbers.

A synthetic card never reaches strategy 2, so the demo path cannot be
perturbed by generalization work. If neither strategy finds a field it stays
None and `extraction_method` reports "failed" — an honest no-signal answer is
the goal; a confident wrong answer is not.

Known limitation, accepted deliberately: Tesseract here carries English
training data only, so Devanagari text is not read (its garbled output is
filtered out rather than guessed at), and exotic or heavily photographed
layouts may still return "failed".
"""

from __future__ import annotations

import logging
import math
import re
import statistics
from io import BytesIO

import numpy as np
import pytesseract
from PIL import Image, ImageOps

logger = logging.getLogger("aegis.ocr")

# --- EasyOCR (generalized / real-world path) --------------------------------
# Weights are baked into the image at build time; download_enabled=False makes
# a missing cache fail loudly rather than silently reaching for the network.
_easyocr_reader = None
_easyocr_lock = __import__("threading").Lock()
EASYOCR_MIN_CONFIDENCE = 0.30


def get_easyocr_reader():
    """Process-wide EasyOCR reader. Loads once; never downloads at runtime."""
    global _easyocr_reader
    if _easyocr_reader is None:
        with _easyocr_lock:
            if _easyocr_reader is None:
                import easyocr

                _easyocr_reader = easyocr.Reader(
                    ["en"], gpu=False, verbose=False, download_enabled=False
                )
    return _easyocr_reader

# --- synthetic template patterns -------------------------------------------
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_ID_NUMBER_RE = re.compile(r"\b(SYN-[0-9A-F]{4}-[0-9A-F]{4})\b", re.IGNORECASE)
_SYN_FUZZY_RE = re.compile(r"\bSYN[-_ ]?([0-9A-Z]{4})[-_ ]?([0-9A-Z]{4})\b", re.I)
_NAME_VALUE_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{2,40}$")
_SYNTHETIC_LABELS = {"NAME", "DOB", "ID NUMBER", "ISSUE DATE"}

# Lines that are card furniture, never field values.
_NOISE = {"SYNTHETIC", "PHOTO", "ISSUE DATE", "NAME", "DOB", "ID NUMBER"}

# --- generalized (real-world) patterns --------------------------------------
_DATE_ISO_RE = re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b")
_DATE_DMY_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
_DOB_LABEL_RE = re.compile(r"(date\s*of\s*birth|\bd\.?\s?o\.?\s?b\b|जन्म)", re.I)
_NAME_LABEL_RE = re.compile(r"(?i)\bname\b")
_RELATION_RE = re.compile(r"(?i)\b(father|mother|husband|guardian|spouse)\b")
_PAN_RE = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b")
_ACCOUNT_LABEL_RE = re.compile(
    r"(permanent\s*account\s*number|account\s*number|card\s*number|\bpan\b)", re.I
)
_GENERIC_ID_RE = re.compile(r"\b([A-Z0-9]{10,16})\b")

# Words that appear on ID cards but are never part of a person's name.
_NAME_STOPWORDS = {
    "INCOME", "TAX", "DEPARTMENT", "GOVT", "GOVERNMENT", "OF", "INDIA",
    "PERMANENT", "ACCOUNT", "NUMBER", "DATE", "BIRTH", "FATHER", "MOTHER",
    "NAME", "SIGNATURE", "CARD", "MALE", "FEMALE", "DOB", "ADDRESS",
    "AUTHORITY", "IDENTITY", "SYNTHETIC", "DEMO", "ONLY", "DATA", "PHOTO",
}


# ---------------------------------------------------------------------------
# Image handling
# ---------------------------------------------------------------------------


def _preprocess(image: Image.Image) -> Image.Image:
    """Upscale + grayscale + hard threshold — tuned for the synthetic cards.

    The cards are 400x250 with 9-13px text, too small for reliable OCR at
    native resolution; 3x LANCZOS upscaling fixes that. The threshold (140,
    empirical) drops the light watermark to white while black text survives.
    """
    upscaled = image.convert("L").resize(
        (image.width * 3, image.height * 3), Image.LANCZOS
    )
    return upscaled.point(lambda p: 0 if p < 140 else 255)


def _preprocess_gentle(image: Image.Image) -> Image.Image:
    """Autocontrast only — for photographed documents.

    A hard global threshold destroys real photos with uneven lighting, so the
    second-pass render keeps the greyscale gradient and lets Tesseract do its
    own local binarisation.
    """
    gray = image.convert("L")
    scale = 2 if max(gray.size) < 1200 else 1
    if scale > 1:
        gray = gray.resize((gray.width * scale, gray.height * scale), Image.LANCZOS)
    return ImageOps.autocontrast(gray, cutoff=2)


def _ocr_lines(image: Image.Image, config: str = "--psm 6") -> tuple[list[str], str]:
    """OCR in line-by-line mode; returns (lines, raw_text).

    image_to_data gives per-word boxes with block/paragraph/line indices, so
    words are regrouped into real lines rather than split on whatever
    newlines the text renderer happened to emit.
    """
    data = pytesseract.image_to_data(
        image, config=config, output_type=pytesseract.Output.DICT
    )
    grouped: dict[tuple[int, int, int], list[str]] = {}
    for i, word in enumerate(data["text"]):
        text = (word or "").strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][i])
        except (TypeError, ValueError):
            confidence = -1.0
        if confidence < 0:  # -1 marks layout artifacts, not recognised text
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        grouped.setdefault(key, []).append(text)

    lines = [" ".join(words) for _, words in sorted(grouped.items())]
    return lines, "\n".join(lines)


def _prepare_for_easyocr(image: Image.Image) -> Image.Image:
    """Light touch only — EasyOCR's detector handles noise Tesseract could not.

    EXIF auto-orient (phone photos carry rotation metadata) and a modest
    upscale for small images. No thresholding: destroying the greyscale
    gradient is exactly what hurt the Tesseract path on real documents.
    """
    oriented = ImageOps.exif_transpose(image).convert("RGB")
    if max(oriented.size) < 900:
        scale = 900 / max(oriented.size)
        oriented = oriented.resize(
            (int(oriented.width * scale), int(oriented.height * scale)), Image.LANCZOS
        )
    return oriented


def _easyocr_lines(image: Image.Image) -> tuple[list[dict], str]:
    """Read with EasyOCR and rebuild reading order (top-to-bottom, left-to-right).

    EasyOCR returns detached (bbox, text, confidence) boxes with no line
    structure, so boxes whose vertical centres are within ~60% of a box height
    are grouped into one line and ordered by x.
    """
    prepared = _prepare_for_easyocr(image)
    raw = get_easyocr_reader().readtext(np.array(prepared))

    boxes = []
    skew_angles = []
    for bbox, text, confidence in raw:
        value = (text or "").strip()
        if not value or float(confidence) < EASYOCR_MIN_CONFIDENCE:
            continue
        ys = [float(point[1]) for point in bbox]
        xs = [float(point[0]) for point in bbox]
        # Each detection is a quadrilateral, so its top edge reveals the local
        # text angle. The median across all boxes is the document's skew.
        (x0, y0), (x1, y1) = bbox[0], bbox[1]
        if abs(float(x1) - float(x0)) > 5:
            skew_angles.append(math.atan2(float(y1) - float(y0), float(x1) - float(x0)))
        boxes.append(
            {
                "text": value,
                "conf": float(confidence),
                "cy": sum(ys) / len(ys),
                "cx": sum(xs) / len(xs),
                "x": min(xs),
                "h": max(ys) - min(ys),
            }
        )

    # Group along the SKEWED baseline, not a horizontal one. On a 7-degree
    # scan a word 200px to the right sits ~25px lower on the same logical
    # line, which naive y-grouping shreds into cross-row gibberish.
    skew = statistics.median(skew_angles) if skew_angles else 0.0
    if abs(skew) > math.radians(20):  # implausible for a document scan
        skew = 0.0
    slope = math.tan(skew)
    for box in boxes:
        box["baseline_y"] = box["cy"] - box["cx"] * slope

    boxes.sort(key=lambda b: b["baseline_y"])
    grouped: list[list[dict]] = []
    for box in boxes:
        if grouped:
            previous = grouped[-1][-1]
            tolerance = max(10.0, previous["h"] * 0.6)
            if abs(box["baseline_y"] - previous["baseline_y"]) <= tolerance:
                grouped[-1].append(box)
                continue
        grouped.append([box])

    lines = []
    height = prepared.height or 1
    for group in grouped:
        group.sort(key=lambda b: b["x"])
        lines.append(
            {
                "text": " ".join(b["text"] for b in group),
                "conf": min(b["conf"] for b in group),
                "rel_y": (sum(b["cy"] for b in group) / len(group)) / height,
            }
        )
    return lines, "\n".join(line["text"] for line in lines)


_HEURISTIC_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z.'-]*(?: [A-Za-z][A-Za-z.'-]*){1,3}$")


def _heuristic_name(lines: list[dict]) -> str | None:
    """Last-resort name guess when no 'Name' label was found.

    Deliberately narrow: a short, alphabetic, 2-4 word, confidently-read block
    in the top third of the document. Reported as heuristic_fallback so the
    lower confidence is never presented as a labelled read.
    """
    for line in lines:
        if line["rel_y"] > 0.34 or line["conf"] < 0.5:
            continue
        text = " ".join(line["text"].split())
        if any(c.isdigit() for c in text) or not _HEURISTIC_NAME_RE.match(text):
            continue
        if _plausible_name(text):
            return _plausible_name(text)
    return None


def _english_lines(lines: list[str]) -> list[str]:
    """Drop lines that are mostly non-ASCII (e.g. Devanagari OCR garble)."""
    keep = []
    for line in lines:
        if not line:
            continue
        ascii_ratio = sum(1 for c in line if ord(c) < 128) / len(line)
        if ascii_ratio >= 0.8:
            keep.append(line)
    return keep


# ---------------------------------------------------------------------------
# Strategy 1: synthetic template (the demo path — behaviour frozen)
# ---------------------------------------------------------------------------


def _value_after_label(lines: list[str], label: str) -> str | None:
    for i, line in enumerate(lines):
        if line.strip().upper() == label:
            for candidate in lines[i + 1 : i + 3]:  # value is the next real line
                value = candidate.strip()
                if value and value.upper() not in _NOISE:
                    return value
    return None


def _is_synthetic_card(raw_text: str, lines: list[str]) -> bool:
    """Is this one of our generated demo cards?

    Keyed on the SYN-XXXX-XXXX document number (survives OCR on every card
    tested) or on two or more of the exact synthetic label lines. The header
    and watermark text do not survive thresholding, so they are not used.
    """
    if _SYN_FUZZY_RE.search(raw_text):
        return True
    upper = {line.strip().upper() for line in lines}
    return len(upper & _SYNTHETIC_LABELS) >= 2


def _extract_synthetic(lines: list[str], raw_text: str) -> dict:
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
        fuzzy = _SYN_FUZZY_RE.search(raw_text)
        id_number = (
            f"SYN-{fuzzy.group(1).upper()}-{fuzzy.group(2).upper()}" if fuzzy else None
        )

    return {"name": name, "dob": dob, "id_number": id_number}


# ---------------------------------------------------------------------------
# Strategy 2: generalized real-world layouts
# ---------------------------------------------------------------------------


def _plausible_name(value: str | None) -> str | None:
    """Accept only strings that actually look like a person's name."""
    text = " ".join((value or "").replace("|", " ").split())
    if not (4 <= len(text) <= 60):
        return None
    if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]+", text):
        return None
    words = [w for w in re.split(r"[ .]+", text) if w]
    if len(words) < 2:  # 2+ words
        return None
    if any(w.upper() in _NAME_STOPWORDS for w in words):
        return None
    # title-case or all-caps, every word
    if not all(w.isupper() or w[:1].isupper() for w in words):
        return None
    if sum(c.isalpha() for c in text) / len(text) < 0.8:  # mostly alphabetic
        return None
    return text


def _normalize_date(text: str) -> str | None:
    """Parse DD/MM/YYYY, DD-MM-YYYY or YYYY-MM-DD; return YYYY-MM-DD."""
    iso = _DATE_ISO_RE.search(text)
    if iso:
        year, month, day = int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
    else:
        dmy = _DATE_DMY_RE.search(text)
        if not dmy:
            return None
        first, second, year = int(dmy.group(1)), int(dmy.group(2)), int(dmy.group(3))
        # Indian cards use DD/MM/YYYY; only read it the other way round when
        # day-first is impossible (e.g. 12/25/1990).
        day, month = (first, second) if second <= 12 else (second, first)
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _generalized_name(lines: list[str]) -> str | None:
    for i, line in enumerate(lines):
        if not _NAME_LABEL_RE.search(line) or _RELATION_RE.search(line):
            continue
        # "Name: VALUE" / "नाम / Name VALUE" — value on the same line
        tail = _NAME_LABEL_RE.split(line, maxsplit=1)
        if len(tail) > 1:
            candidate = _plausible_name(tail[-1].strip(" :-/|"))
            if candidate:
                return candidate
        # "Name" then VALUE on the following line
        for following in lines[i + 1 : i + 3]:
            if _RELATION_RE.search(following):
                break  # we've walked into the father's-name block
            candidate = _plausible_name(following)
            if candidate:
                return candidate
    return None


def _generalized_dob(lines: list[str]) -> str | None:
    for i, line in enumerate(lines):
        if not _DOB_LABEL_RE.search(line):
            continue
        found = _normalize_date(line)
        if found:
            return found
        for following in lines[i + 1 : i + 3]:
            found = _normalize_date(following)
            if found:
                return found
    return None


def _generalized_id_number(lines: list[str], raw_text: str) -> str | None:
    pan = _PAN_RE.search(raw_text.upper())
    if pan:
        return pan.group(1)
    for i, line in enumerate(lines):
        if not _ACCOUNT_LABEL_RE.search(line):
            continue
        for candidate_line in [line, *lines[i + 1 : i + 3]]:
            for match in _GENERIC_ID_RE.finditer(candidate_line.upper()):
                token = match.group(1)
                if any(c.isdigit() for c in token):  # excludes plain words
                    return token
    return None


def _extract_generalized(lines: list[str], raw_text: str) -> dict:
    english = _english_lines(lines)
    return {
        "name": _generalized_name(english),
        "dob": _generalized_dob(english),
        "id_number": _generalized_id_number(english, "\n".join(english) or raw_text),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_EMPTY = {"name": None, "dob": None, "id_number": None}


def extract_id_fields(image_bytes: bytes) -> dict:
    """Extract identity fields from an ID image.

    Returns {name, dob, id_number, raw_text, extraction_method} where
    extraction_method is "synthetic_template", "generalized_layout" or
    "failed". Any field the reader could not establish is None.
    """
    try:
        image = Image.open(BytesIO(image_bytes))
        lines, raw_text = _ocr_lines(_preprocess(image))
    except Exception as exc:  # noqa: BLE001 - unreadable file, missing binary, etc.
        logger.warning("OCR failed: %s", exc)
        return {**_EMPTY, "raw_text": "", "extraction_method": "failed"}

    # ---- Strategy 1: our own demo cards never leave this branch -------------
    # UNCHANGED. Tesseract template matching, gated by the SYN- marker.
    if _is_synthetic_card(raw_text, lines):
        fields = _extract_synthetic(lines, raw_text)
        if any(fields.values()):
            return {**fields, "raw_text": raw_text, "extraction_method": "synthetic_template"}

    # ---- Strategy 2: real-world layouts, read by EasyOCR --------------------
    # A deep-learning detector/recogniser copes with security patterns, uneven
    # lighting and slight rotation that defeated Tesseract's global threshold.
    # The label-matching parser below is shared with the Tesseract path, so
    # only the text-acquisition step changed.
    try:
        easy_lines, easy_raw = _easyocr_lines(image)
    except Exception as exc:  # noqa: BLE001 - fall back rather than fail the upload
        logger.warning("EasyOCR unavailable, falling back to Tesseract lines: %s", exc)
        easy_lines, easy_raw = [], ""

    if easy_lines:
        texts = [line["text"] for line in easy_lines]
        fields = _extract_generalized(texts, easy_raw)
        if any(fields.values()):
            return {**fields, "raw_text": easy_raw, "extraction_method": "generalized_layout"}

        # No labelled field found — try the narrow positional name guess.
        guess = _heuristic_name(easy_lines)
        if guess:
            return {
                **_EMPTY,
                "name": guess,
                "dob": _generalized_dob(texts),
                "id_number": _generalized_id_number(texts, easy_raw),
                "raw_text": easy_raw,
                "extraction_method": "heuristic_fallback",
            }

    # ---- Strategy 3: Tesseract as a safety net ------------------------------
    fields = _extract_generalized(lines, raw_text)
    if not any(fields.values()):
        try:
            retry_lines, retry_raw = _ocr_lines(_preprocess_gentle(image), config="--psm 4")
            retry_fields = _extract_generalized(retry_lines, retry_raw)
            if any(retry_fields.values()):
                fields, raw_text = retry_fields, retry_raw
        except Exception as exc:  # noqa: BLE001
            logger.info("gentle-pass OCR retry failed: %s", exc)

    if any(fields.values()):
        return {**fields, "raw_text": raw_text, "extraction_method": "generalized_layout"}
    return {**_EMPTY, "raw_text": easy_raw or raw_text, "extraction_method": "failed"}


# ---------------------------------------------------------------------------
# Name comparison helpers
# ---------------------------------------------------------------------------


def normalize_name(name: str | None) -> str:
    """Case/punctuation/whitespace-insensitive form for name comparison."""
    if not name:
        return ""
    return re.sub(r"[^a-z ]", "", name.lower().replace("-", " ")).strip()


def names_match(a: str | None, b: str | None) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    return bool(na) and bool(nb) and " ".join(na.split()) == " ".join(nb.split())
