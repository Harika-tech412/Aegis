#  ---------------------------------------------------------------------------
#  COMPATIBILITY COPY. The canonical file is ./Dockerfile at the repository
#  root; this is a byte-identical duplicate of its build instructions so that
#  the deploy works whether the platform's "Dockerfile Path" is set to
#  `./Dockerfile` or to `backend/Dockerfile`.
#
#  IF YOU EDIT THIS FILE, EDIT THE ROOT ONE THE SAME WAY.
#
#  Note what this file still cannot rescue: the BUILD CONTEXT must be the
#  repository root. A context scoped to backend/ cannot COPY ml/ or data/,
#  because they sit outside it — that is a property of Docker, not of a setting.
#  ---------------------------------------------------------------------------

#  Backend image. THIS FILE LIVES AT THE REPOSITORY ROOT ON PURPOSE.
#
#  Build locally exactly the way Render does:
#      docker build -t aegis-backend .
#
#  On Render, every path setting can stay at its default: Root Directory blank,
#  Dockerfile Path ./Dockerfile, Build Context Directory `.`. It was previously
#  at backend/Dockerfile, which required overriding both the Dockerfile path AND
#  the build context directory; getting only the first one right produced a
#  context rooted at backend/ where none of the COPY sources resolved:
#
#      transferring context: 2B
#      COPY backend/requirements.txt . -> "/backend/requirements.txt": not found
#
#  A root Dockerfile removes that failure mode: the context can only be the repo.
#
#  Why the root: the serving path imports the training code directly —
#  app/ml/scoring_service.py does `from explain import ...` and
#  `from features import ...` out of the repo's ml/ package, and loads the
#  trained artifacts from ml/artifacts/. A build context scoped to backend/
#  cannot COPY those (they sit outside it), so the image built fine and then
#  died at import with `ModuleNotFoundError: No module named 'explain'`. It only
#  ever worked locally because docker-compose bind-mounted ./ml over /ml at RUN
#  time — the image itself was never self-contained. Everything the API needs is
#  now baked in, so the image runs anywhere with no volumes.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libpq-dev \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only torch/torchvision first: sentence-transformers pulls torch
# and easyocr pulls torchvision, and the default PyPI linux wheels bundle CUDA
# (~2.5GB). The CPU wheels are ~10x smaller and are all we need for MiniLM
# embeddings and EasyOCR inference. Installing them up front also stops pip
# from backtracking over torch versions when it resolves easyocr.
RUN pip install --no-cache-dir torch==2.5.1 torchvision==0.20.1 \
    --index-url https://download.pytorch.org/whl/cpu

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the EasyOCR English detection + recognition weights (~100MB)
# INTO THE IMAGE at build time. Baked into a layer rather than a runtime
# volume: it survives container recreation with no setup step, and guarantees
# the demo never waits on a model download. Runtime init uses
# download_enabled=False, so a missing cache fails loudly instead of silently
# reaching for the network.
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)" \
    && ls -lh /root/.EasyOCR/model

# ---- Application code ------------------------------------------------------
COPY backend/app/ ./app/

# ---- Shared ML package: feature building, SHAP explanation, trained artifacts
# Imported by app/ml/scoring_service.py, which puts this directory on sys.path.
COPY ml/ ./ml/

# ---- Demo data: sample ID documents for the OCR path, and the training CSV
# the /demo endpoints read to build bot profiles.
COPY data/ ./data/

# ---- Seeding and maintenance scripts (small; needed to populate a fresh DB)
COPY scripts/ ./scripts/

# ---- Synthetic ID cards for the OCR / identity-mismatch demo paths.
# 1,838 PNGs, ~44MB, and every one of them is a pure function of its
# application_id — so they are replayed here from the two CSVs above instead of
# being committed. Keeps the repository small without the deployed image
# missing the images /demo/id-image serves.
RUN python ml/generate_id_documents.py | tail -4

# Pin the ML directory explicitly rather than leaning on relative resolution.
# scoring_service.py can find it either way, but an image should not depend on
# how deep it happens to be nested.
ENV AEGIS_ML_DIR=/app/ml

# Documentation only; the actual port is chosen at runtime (see CMD).
EXPOSE 8000

# Render injects PORT and expects the process to bind it on 0.0.0.0. Falls back
# to 8000 for local runs and docker-compose. `sh -c` is required so ${PORT} is
# expanded by the shell — an exec-form CMD would pass the literal string.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
