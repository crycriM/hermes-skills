#!/bin/bash
# Start <MODEL_NAME> on dedicated port <PORT>
# Generic template for custom-built llama.cpp binaries
set -e

PID_FILE="/tmp/llama-server-<SHORTNAME>.pid"
LOG_FILE="/tmp/llama-server-<SHORTNAME>.log"

# Kill any existing instance
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Killing existing server (PID $OLD_PID)..."
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
    fi
fi

# Build directory for custom llama.cpp
LLAMA_BUILD_DIR="$HOME/sources/llama.cpp/build/bin"
LLAMA_SERVER="$LLAMA_BUILD_DIR/llama-server"

if [ ! -x "$LLAMA_SERVER" ]; then
    echo "ERROR: $LLAMA_SERVER not found. Build it first (see custom-llama-cpp-build skill)."
    exit 1
fi

# Check model file(s)
MODEL="/home/cricri/models/<MODEL_DIR>/<MODEL_FILE>"
if [ ! -f "$MODEL" ]; then
    echo "ERROR: Model not found at $MODEL"
    exit 1
fi

# Env vars required for Vulkan GPU detection on Strix Halo
export VK_ICD_FILENAMES="/usr/share/vulkan/icd.d/radeon_icd.x86_64.json"

# Start inside distrobox
distrobox enter llama-vulkan-amdvlk -- \
  env LD_LIBRARY_PATH="$LLAMA_BUILD_DIR" \
  VK_ICD_FILENAMES="$VK_ICD_FILENAMES" \
  "$LLAMA_SERVER" \
    --host 0.0.0.0 --port <PORT> \
    --model "$MODEL" \
    --jinja \
    --flash-attn on \
    --n-gpu-layers 999 \
    --ctx-size 16384 \
    --batch-size 2048 \
    --ubatch-size 512 \
    --temp 0.6 \
    --top-p 0.95 \
    --min-p 0.01 \
    --repeat-penalty 1.0 \
    --mmap \
    --threads 8 \
    --metrics \
    > "$LOG_FILE" 2>&1 &

SERVER_PID=$!
echo $SERVER_PID > "$PID_FILE"
echo "Started PID: $SERVER_PID"

# Wait for model to appear in /v1/models (more reliable than /health)
echo -n "Waiting for model to load..."
for i in $(seq 1 300); do
    if curl -s http://localhost:<PORT>/v1/models 2>/dev/null | grep -q '"id"'; then
        echo " ready after ${i}s!"
        echo ""
        echo "<MODEL_NAME> running on http://localhost:<PORT>"
        echo "Test: curl http://localhost:<PORT>/v1/chat/completions -H 'Content-Type: application/json' -d '{\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}],\"max_tokens\":50}'"
        echo "Logs: $LOG_FILE"
        exit 0
    fi
    sleep 1
done

echo " timeout after 300s"
echo "Check log: $LOG_FILE"
exit 1
