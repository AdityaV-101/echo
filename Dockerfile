# syntax=docker/dockerfile:1

# ---- Stage 1: build the frontend static bundle ----
FROM node:22-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: backend, with the wav2vec2 model baked in ----
FROM python:3.12-slim AS final
WORKDIR /app

# ffmpeg: decodes whatever container/codec a browser recorded (webm/opus,
# Safari's mp4/aac, etc.) - see backend/audio_preprocess.py.
# espeak-ng: phonemizer's backend for canonical phoneme lookups.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
# torch/torchaudio from PyPI's default index are the CUDA build, which pulls
# several GB of NVIDIA driver libraries that a Render web service (CPU only,
# no GPU) never uses - installing the same pinned versions from PyTorch's
# CPU-only wheel index instead changes nothing about the model/scoring, just
# which binary distribution of the identical version gets installed. Then
# the rest of requirements.txt installs normally; pip leaves the already-
# satisfied torch/torchaudio pins alone.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.14.0 torchaudio==2.11.0 \
    && pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/

# Bake the wav2vec2 phoneme recognizer (~1.2GB, facebook/wav2vec2-lv-60-
# espeak-cv-ft) into the image at build time, via the exact same loader the
# app calls at runtime (backend/gop_scorer.py's get_model, which also
# verifies the ARPABET<->vocab mapping) - so no container ever starts
# without the weights already on disk, and no request ever waits on a
# HuggingFace download.
RUN cd backend && python -c "from gop_scorer import get_model; get_model()"

COPY --from=frontend-builder /app/frontend/dist ./frontend_dist

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Render injects PORT at runtime; default 8000 covers `docker run` without
# -e PORT (see the "test locally" instructions in DEPLOY_RENDER.md).
CMD ["sh", "-c", "cd backend && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
