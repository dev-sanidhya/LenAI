#!/bin/sh
# Ollama entrypoint: starts server, pulls required models, warms them up.
# The backend's depends_on health check waits for models to be loaded
# before routing any traffic. Cold-start latency never reaches the user.
#
# Important: the ollama/ollama image has NO curl, wget, or python.
# All readiness probes use the `ollama` CLI itself, which IS present.

set -e

LLM_MODEL="${OLLAMA_LLM_MODEL:-llama3.1:8b}"
EMBED_MODEL="${OLLAMA_EMBED_MODEL:-nomic-embed-text}"

echo "[ollama-entrypoint] Starting Ollama server..."
ollama serve &
SERVER_PID=$!

# Wait for the Ollama API by polling the CLI - `ollama list` returns 0
# only after the local API is responsive.
echo "[ollama-entrypoint] Waiting for Ollama API..."
until ollama list > /dev/null 2>&1; do
  sleep 2
done
echo "[ollama-entrypoint] Ollama API is up."

# Pull models if not already cached in the volume
echo "[ollama-entrypoint] Pulling LLM model: ${LLM_MODEL}"
ollama pull "${LLM_MODEL}"

echo "[ollama-entrypoint] Pulling embedding model: ${EMBED_MODEL}"
ollama pull "${EMBED_MODEL}"

# Warm up the LLM so the first real user request hits a loaded model
echo "[ollama-entrypoint] Warming up LLM..."
ollama run "${LLM_MODEL}" "Hello" > /dev/null 2>&1 || true

# Embedding model warms up on first real call - no need for a separate
# curl warmup that would require curl in the image.

echo "[ollama-entrypoint] Models ready. Server PID: ${SERVER_PID}"

# Keep the container alive by waiting on the server process
wait "${SERVER_PID}"
