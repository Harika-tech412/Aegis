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

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the EasyOCR English detection + recognition weights (~100MB)
# INTO THE IMAGE at build time. Baked into a layer rather than a runtime
# volume: it survives container recreation with no setup step, and guarantees
# the demo never waits on a model download. Runtime init uses
# download_enabled=False, so a missing cache fails loudly instead of silently
# reaching for the network.
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)" \
    && ls -lh /root/.EasyOCR/model

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
