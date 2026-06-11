# ═══════════════════════════════════════════════════════════
# Zenic-Flijo — Multi-stage Docker Build
# Task IDs: 0-4, 0-7, 0-8
# ═══════════════════════════════════════════════════════════

# ── Stage 1: Builder ──────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies for C extensions (psycopg2, cryptography, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for Docker layer caching
COPY requirements.txt .

# Install Python dependencies into a clean prefix
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Zenic-Flijo Team"
LABEL description="Zenic-Flijo — Workflow Automation Platform"
LABEL org.opencontainers.image.source="https://github.com/albrth647-png/Zenic-Flijo"

# Install only runtime dependencies (no build tools)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r zenic && \
    useradd -r -g zenic -d /app -s /sbin/nologin -c "Zenic-Flijo runtime user" zenic

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Set working directory
WORKDIR /app

# Copy application source code
COPY src/ ./src/
COPY ruff.toml ./
COPY scripts/ ./scripts/

# Create data directory with proper ownership
RUN mkdir -p /app/data && chown -R zenic:zenic /app

# ── Environment variables with defaults ───────────────────
ENV WFD_PRODUCTION=false \
    WFD_DATA_DIR=/app/data \
    WFD_WEB_HOST=0.0.0.0 \
    WFD_WEB_PORT=8080 \
    WFD_WEBHOOK_PORT=8081 \
    WFD_LOG_LEVEL=INFO \
    WFD_SESSION_SECURE=false \
    WFD_OLLAMA_ENABLED=false \
    WFD_OLLAMA_URL=http://localhost:11434 \
    WFD_OLLAMA_MODEL=llama3.2 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER zenic

# Expose ports: 8080 (web UI + API), 8081 (webhook receiver)
EXPOSE 8080 8081

# Health check — verify the web server is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/api/auth/status || exit 1

# Volume for persistent data (SQLite DB, backups, etc.)
VOLUME ["/app/data"]

# Entry point
ENTRYPOINT ["python", "src/main.py"]
