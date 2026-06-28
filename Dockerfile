FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
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

RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.docker.txt

COPY claim_parser.py .

ENTRYPOINT ["python", "claim_parser.py"]
