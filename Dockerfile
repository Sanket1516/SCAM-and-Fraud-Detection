# syntax=docker/dockerfile:1.4
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_RETRIES=10
ENV PIP_TIMEOUT=120
ENV HF_HOME=/models/huggingface
ENV XDG_CACHE_HOME=/models/cache

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libgl1 \
    libglib2.0-0 \
    libmagic1 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.docker.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip && \
    python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    python -m pip install -r requirements.docker.txt

COPY claim_parser.py .
COPY app.py .
COPY templates/ templates/
COPY static/ static/

EXPOSE 5000

ENTRYPOINT ["python", "app.py"]
