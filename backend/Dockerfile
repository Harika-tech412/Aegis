#  BUILD CONTEXT IS THE REPOSITORY ROOT, not backend/.
#
#  Build locally exactly the way Render does:
#      docker build -f backend/Dockerfile -t aegis-backend .
#
#  On Render: leave the service's Root Directory BLANK and set the Dockerfile
#  path to `backend/Dockerfile`.
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
