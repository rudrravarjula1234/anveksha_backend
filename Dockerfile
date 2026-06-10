# syntax=docker/dockerfile:1.7
#
# Multi-stage build: produces a slim production image (~150 MB) by
# isolating wheel-building from the runtime layer. The runtime uses a
# non-root user and no build toolchain.

# ─── Stage 1: build wheels ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Build deps for any wheels that need compilation (motor/pymongo are pure
# Python in modern releases but we keep this defensive for forward-compat).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt


# ─── Stage 2: runtime ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Create a non-root user up front so subsequent COPY can chown to it.
RUN groupadd --system anveksha && \
    useradd --system --gid anveksha --no-create-home --home /app anveksha

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY --from=builder /build/wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && \
    rm -rf /wheels

COPY --chown=anveksha:anveksha app/ ./app/

USER anveksha
EXPOSE 8000

# Use uvicorn directly so signals (SIGTERM from docker stop) reach Python
# cleanly without an init-shim PID 1.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
