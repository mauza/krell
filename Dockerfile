# Stage 1: Runtime
FROM nvcr.io/nvidia/pytorch:24.12-py3

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# --- FIXED SECTION ---
# 1. Export dependencies to a requirements.txt file (using the lockfile versions)
RUN uv export --frozen --no-dev --no-hashes --output-file requirements.txt

# 2. Remove torch, nvidia, triton, and bitsandbytes packages that are pre-installed in base image
#    Also remove sympy and networkx since torch version in base image has specific version requirements
RUN sed -i '/^torch==/d; /^triton==/d; /^nvidia-/d; /^bitsandbytes==/d; /^setuptools==/d; /^intel-extension-for-pytorch==/d; /^sympy==/d; /^networkx==/d' requirements.txt

# 3. Install remaining dependencies using standard pip (more lenient than uv with version conflicts)
RUN python3 -m pip install --no-deps -r requirements.txt
# ---------------------

# Install system runtime libs
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# Copy application code
COPY api ./api
COPY core ./core
COPY krell ./krell
COPY plugins ./plugins
COPY services ./services
COPY templates ./templates
COPY config.py config.yaml main.py ./

RUN mkdir -p ./data

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]