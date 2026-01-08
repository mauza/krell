#!/bin/bash

# Start Krell Backend
echo "Starting Krell Backend..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "uv not found. Installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env
fi

# Check if Ollama is running (if using local LLM)
if curl -s http://localhost:11434/api/tags &> /dev/null; then
    echo "✓ Ollama is running"
else
    echo "⚠️  Ollama not detected on localhost:11434"
    echo "   If using OpenAI, this is fine."
    echo "   If using local LLM, start Ollama first:"
    echo "   ollama serve"
fi

# Install dependencies
echo "Installing dependencies..."
uv sync

# PyTorch CPU optimizations for M3 Max Performance cores
# Use all performance cores for inference
export OMP_NUM_THREADS=12  # M3 Max has 12 performance cores
export MKL_NUM_THREADS=12
export OPENBLAS_NUM_THREADS=12

# Set PyTorch MPS fallback for Apple Silicon GPU compatibility
# NOTE: Currently using CPU due to MPS compatibility issues with Kyutai model
# export PYTORCH_ENABLE_MPS_FALLBACK=1

# Run the server
echo "Starting server on http://localhost:8000"
echo "Dashboard: http://localhost:8000/dashboard"
echo "API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"

uv run uvicorn main:app --host 0.0.0.0 --port 8000