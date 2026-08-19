"""Render synthetic ID document images for applications that uploaded one.

These are **stylized demo cards, not reproductions of any real government ID**.
No jurisdiction's layout, seal, colour scheme, security feature, or typography
is imitated. Every card carries a header, a diagonal watermark, and a footer
all stating that it is synthetic demo data, so none of these images could be
mistaken for - or repurposed as - a genuine identity document.

The name printed on each card comes from `id_document_plan()` in
`generate_synthetic_data.py`: it matches the applicant on legitimate
applications and deliberately mismatches on identity fabrication and on a
share of ring/burst cases. That function is a pure function of
`application_id`, so this script recomputes the same answer the dataset
generator did without anything being stored in the CSV.

Run standalone (after generating the CSVs):

    python ml/generate_id_documents.py

Output:
    data/id_documents/*.png
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

# Sharing the dataset generator's helpers keeps one implementation of the
# name-derivation and match/mismatch rules rather than two that can drift.
from generate_synthetic_data import _stable_hash, id_document_plan

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "id_documents"

SOURCE_CSVS = [
    DATA_DIR / "applications_train.csv",
    DATA_DIR / "applications_holdout.csv",
]

CARD_W, CARD_H = 400, 250

NAVY = (11, 31, 58)
WHITE = (255, 255, 255)
BLACK = (17, 17, 17)
LABEL_GRAY = (110, 120, 135)
RULE_GRAY = (206, 213, 224)
PHOTO_FILL = (232, 236, 242)
PHOTO_EDGE = (194, 203, 217)
WATERMARK = (120, 120, 120, 70)

HEADER_TEXT = "SYNTHETIC ID CARD - DEMO DATA ONLY"
FOOTER_TEXT = "Generated for the Aegis demo - not a government document"


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def _centered(draw: ImageDraw.ImageDraw, text: str, font, y: int, width: int = CARD_W) -> int:
    return (width - _text_width(draw, text, font)) // 2


def _card_details(application_id: str, applied_at: datetime, age: int) -> dict[str, str]:
    """Fabricated DOB / document number / issue date, stable per application."""
    h = _stable_hash(f"iddetails|{application_id}")

    birth_year = applied_at.year - age
    birth_month = (h % 12) + 1
    birth_day = ((h // 12) % 28) + 1

    issue = applied_at - timedelta(days=365 * (1 + (h // 1000) % 6) + (h // 7) % 365)

    return {
        "DOB": f"{birth_year:04d}-{birth_month:02d}-{birth_day:02d}",
        "ID NUMBER": f"SYN-{h % 0xFFFF:04X}-{(h // 0xFFFF) % 0xFFFF:04X}",
        "ISSUE DATE": issue.strftime("%Y-%m-%d"),
    }


def _watermark_layer() -> Image.Image:
    """A diagonal SYNTHETIC watermark sized to overlay the card."""
    scratch = Image.new("RGBA", (CARD_W * 2, CARD_H * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(scratch)
    font = _font(58, bold=True)
    width = _text_width(draw, "SYNTHETIC", font)
    draw.text(
        ((scratch.width - width) // 2, scratch.height // 2 - 36),
        "SYNTHETIC",
        font=font,
        fill=WATERMARK,
    )
    rotated = scratch.rotate(28, resample=Image.BICUBIC)
    left = (rotated.width - CARD_W) // 2
    top = (rotated.height - CARD_H) // 2
    return rotated.crop((left, top, left + CARD_W, top + CARD_H))


def render_card(name: str, details: dict[str, str], watermark: Image.Image) -> Image.Image:
    card = Image.new("RGBA", (CARD_W, CARD_H), WHITE)
    draw = ImageDraw.Draw(card)

    # Header band - the first of three synthetic-data markings.
    draw.rectangle([0, 0, CARD_W, 42], fill=NAVY)
    header_font = _font(12, bold=True)
    draw.text((_centered(draw, HEADER_TEXT, header_font, 0), 15), HEADER_TEXT, font=header_font, fill=WHITE)

    # Photo placeholder - deliberately an empty grey box, no likeness.
    draw.rectangle([300, 62, 376, 152], fill=PHOTO_FILL, outline=PHOTO_EDGE)
    photo_font = _font(10)
    draw.text(
        (300 + (76 - _text_width(draw, "PHOTO", photo_font)) // 2, 102),
        "PHOTO",
        font=photo_font,
        fill=LABEL_GRAY,
    )

    label_font = _font(9, bold=True)
    value_font = _font(13)
    y = 62
    for label, value in [("NAME", name), *details.items()]:
        draw.text((24, y), label, font=label_font, fill=LABEL_GRAY)
        draw.text((24, y + 13), value, font=value_font, fill=BLACK)
        y += 34

    # Footer rule and disclaimer - the third marking.
    draw.line([24, 212, CARD_W - 24, 212], fill=RULE_GRAY, width=1)
    footer_font = _font(8)
    draw.text(
        (_centered(draw, FOOTER_TEXT, footer_font, 0), 222), FOOTER_TEXT, font=footer_font, fill=LABEL_GRAY
    )

    # Diagonal watermark - the second marking, over the top of everything.
    card.alpha_composite(watermark)
    return card.convert("RGB")


def main() -> None:
    missing = [p for p in SOURCE_CSVS if not p.exists()]
    if missing:
        names = ", ".join(str(p.relative_to(PROJECT_ROOT)) for p in missing)
        raise SystemExit(f"Missing input CSV(s): {names}\nRun `python ml/generate_synthetic_data.py` first.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    watermark = _watermark_layer()

    totals = {"generated": 0, "matched": 0, "mismatched": 0}
    per_source: list[tuple[str, int, int, int]] = []

    for csv_path in SOURCE_CSVS:
        df = pd.read_csv(csv_path)
        df["id_document_filename"] = df["id_document_filename"].fillna("")
        with_id = df[df["id_document_filename"].str.len() > 0]

        matched = mismatched = 0
        for row in with_id.itertuples(index=False):
            first, last, is_mismatch = id_document_plan(row.application_id, row.fraud_type)
            applied_at = datetime.fromisoformat(str(row.timestamp))
            details = _card_details(row.application_id, applied_at, int(row.applicant_age))
            card = render_card(f"{first} {last}".upper(), details, watermark)
            card.save(OUTPUT_DIR / row.id_document_filename, "PNG", optimize=True)

            if is_mismatch:
                mismatched += 1
            else:
                matched += 1

        per_source.append((csv_path.name, len(with_id), matched, mismatched))
        totals["generated"] += len(with_id)
        totals["matched"] += matched
        totals["mismatched"] += mismatched

    size_kb = sum(p.stat().st_size for p in OUTPUT_DIR.glob("*.png")) / 1024

    print("=" * 74)
    print("Synthetic ID document generation complete")
    print("(stylized demo cards - not reproductions of any real government ID)")
    print("=" * 74)
    for source, total, matched, mismatched in per_source:
        print(f"{source}: {total:,} documents | name matched {matched:,} | name mismatched {mismatched:,}")
    print()
    print(f"TOTAL: {totals['generated']:,} PNG files written to {OUTPUT_DIR.relative_to(PROJECT_ROOT)}")
    print(f"  name matches applicant:    {totals['matched']:,}")
    print(f"  name mismatches applicant: {totals['mismatched']:,}")
    print(f"  on disk: {size_kb / 1024:.1f} MB")
    print("  every card carries a synthetic-data header, watermark, and footer")


if __name__ == "__main__":
    main()
