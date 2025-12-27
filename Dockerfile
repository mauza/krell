# Stage 1: Builder - Install dependencies
FROM python:3.12-slim as builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
# --frozen ensures we use the exact versions from uv.lock
# --no-cache prevents unnecessary cache storage
RUN uv sync --frozen --no-dev --no-cache

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
COPY api ./api
COPY database ./database
COPY rag ./rag
COPY services ./services
COPY config.py ./
COPY config.yaml ./
COPY main.py ./

# Copy models directory (TTS models)
COPY models ./models

# Create data directory for database and vector store
RUN mkdir -p ./data/chroma_db

# Set Python path to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"

# Expose the application port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

