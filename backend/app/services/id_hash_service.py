"""ID image reuse detection via perceptual hashing.

The same physical document photo resubmitted under different identities is
one of the strongest documentary fraud signals there is. pHash survives
re-encoding, mild resizing, and compression, so "the same image" is matched
perceptually rather than byte-for-byte.
"""

from __future__ import annotations

from io import BytesIO

import imagehash
from PIL import Image
from sqlalchemy.orm import Session

from app.models import IdDocumentHash
from app.services.ocr_service import normalize_name

# The synthetic cards share one visual template (header band, watermark,
# photo box), so a whole-image 64-bit pHash CANNOT tell two different cards
# apart (measured distance between different cards: 0-4). Instead we hash the
# DISCRIMINATIVE region — the text block carrying name/DOB/ID number — at
# 16x16 (256-bit) resolution. Measured separation: different cards >= 16,
# the same card re-encoded as JPEG and resized 90% = 4. Threshold 8 sits
# between those with margin. Tunable.
HAMMING_THRESHOLD = 8
_HASH_SIZE = 16


def _discriminative_crop(image: Image.Image) -> Image.Image:
    """The card's text block: below the header band, left of the photo box."""
    w, h = image.size
    return image.crop((int(w * 0.04), int(h * 0.20), int(w * 0.72), int(h * 0.82)))


def compute_phash(image_bytes: bytes) -> str:
    image = Image.open(BytesIO(image_bytes))
    return str(imagehash.phash(_discriminative_crop(image), hash_size=_HASH_SIZE))


def check_id_reuse(db: Session, image_bytes: bytes, current_application_name: str | None) -> dict:
    """Has this document image been submitted before, and under which names?"""
    current_hash = imagehash.hex_to_hash(compute_phash(image_bytes))

    prior_uses = 0
    prior_names: list[str] = []
    for row in db.query(IdDocumentHash).all():
        if imagehash.hex_to_hash(row.phash) - current_hash <= HAMMING_THRESHOLD:
            prior_uses += 1
            if row.extracted_name and row.extracted_name not in prior_names:
                prior_names.append(row.extracted_name)

    current_norm = normalize_name(current_application_name)
    same_name_prior_uses = sum(
        1 for n in prior_names if normalize_name(n) == current_norm
    )

    return {
        "reused": prior_uses > 0,
        "prior_uses": prior_uses,
        "prior_names": prior_names,
        "same_name_prior_uses": same_name_prior_uses,
    }


def record_id_hash(
    db: Session, image_bytes: bytes, application_id, extracted_name: str | None
) -> None:
    """Persist this upload's hash so future submissions can be checked against it."""
    db.add(
        IdDocumentHash(
            phash=compute_phash(image_bytes),
            application_id=application_id,
            extracted_name=extracted_name,
        )
    )
