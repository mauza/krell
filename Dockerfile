# Stage 1: Builder - Install dependencies
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
# --frozen ensures we use the exact versions from uv.lock
# --no-dev excludes development dependencies
RUN uv sync --frozen --no-dev

# Stage 2: Runtime
FROM python:3.12-slim

# Install runtime dependencies (for audio processing, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libsndfile1 \
    libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
# Core application modules
COPY api ./api
COPY core ./core
COPY database ./database
COPY krell ./krell
COPY plugins ./plugins
COPY services ./services
COPY templates ./templates

# Copy TTS models (required for Kyutai TTS)
COPY models ./models

# Copy configuration files
COPY config.py config.yaml main.py ./

# Create data directory for database
RUN mkdir -p ./data

# Set Python path to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

# Expose the application port
EXPOSE 8000

# Health check using the root endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
