"""Tesseract vs EasyOCR on fabricated real-format ID fixtures.

Both engines feed the SAME downstream parser (label matching, father's-name
skip, ISO date normalisation), so this isolates the text-acquisition step —
the only thing that changed. Run inside the backend container:

    docker compose exec backend python /scripts/compare_ocr_engines.py
"""

from __future__ import annotations

import sys
from io import BytesIO

sys.path.insert(0, "/app")

from PIL import Image  # noqa: E402

from app.services import ocr_service as svc  # noqa: E402
from tests.fixtures_id_cards import FAKE_PAN, VARIANTS, fake_pan_card  # noqa: E402


def tesseract_generalized(image_bytes: bytes) -> dict:
    """The pre-EasyOCR generalized pipeline, preserved for comparison only."""
    image = Image.open(BytesIO(image_bytes))
    lines, raw = svc._ocr_lines(svc._preprocess(image))
    fields = svc._extract_generalized(lines, raw)
    if not any(fields.values()):  # the gentle-render retry
        try:
            lines2, raw2 = svc._ocr_lines(svc._preprocess_gentle(image), config="--psm 4")
            retry = svc._extract_generalized(lines2, raw2)
            if any(retry.values()):
                fields = retry
        except Exception:  # noqa: BLE001
            pass
    return fields


def easyocr_generalized(image_bytes: bytes) -> dict:
    image = Image.open(BytesIO(image_bytes))
    lines, raw = svc._easyocr_lines(image)
    texts = [line["text"] for line in lines]
    fields = svc._extract_generalized(texts, raw)
    if not any(fields.values()):
        guess = svc._heuristic_name(lines)
        if guess:
            fields = {
                "name": guess,
                "dob": svc._generalized_dob(texts),
                "id_number": svc._generalized_id_number(texts, raw),
            }
    return fields


def score(fields: dict) -> tuple[int, list[str]]:
    checks = {
        "name": svc.names_match(fields.get("name"), FAKE_PAN["name"]),
        "dob": fields.get("dob") == FAKE_PAN["dob_iso"],
        "id": fields.get("id_number") == FAKE_PAN["number"],
    }
    marks = [f"{k}{'OK' if v else 'XX'}" for k, v in checks.items()]
    return sum(checks.values()), marks


def main() -> None:
    header = f"{'fixture':<14}{'engine':<12}{'fields 3':<10}{'name extracted':<26}{'dob':<12}{'id number'}"
    print(header)
    print("-" * len(header))

    totals = {"tesseract": 0, "easyocr": 0}
    for variant in VARIANTS:
        image = fake_pan_card(variant)
        for engine, fn in (("tesseract", tesseract_generalized), ("easyocr", easyocr_generalized)):
            try:
                fields = fn(image)
            except Exception as exc:  # noqa: BLE001
                print(f"{variant:<14}{engine:<12}ERROR: {exc}")
                continue
            correct, _ = score(fields)
            totals[engine] += correct
            print(
                f"{variant:<14}{engine:<12}{correct}/3{'':<7}"
                f"{str(fields.get('name'))[:24]:<26}"
                f"{str(fields.get('dob')):<12}{fields.get('id_number')}"
            )
        print()

    print("-" * len(header))
    denominator = len(VARIANTS) * 3
    for engine, total in totals.items():
        print(f"  {engine:<12} {total}/{denominator} fields correct across {len(VARIANTS)} fixtures")


if __name__ == "__main__":
    main()
