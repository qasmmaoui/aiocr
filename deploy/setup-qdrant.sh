#!/bin/bash
# Install + launch Qdrant server on /workspace (persists). Listens on 127.0.0.1:6333.
set -x
mkdir -p /workspace/qdrant /workspace/qdrant_storage
cd /workspace/qdrant
if [ ! -x /workspace/qdrant/qdrant ]; then
  echo "downloading qdrant binary..."
  curl -fsSL "https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-gnu.tar.gz" -o q.tar.gz \
    && tar xzf q.tar.gz && rm -f q.tar.gz
fi
pkill -f "/workspace/qdrant/qdrant" 2>/dev/null
sleep 1
cd /workspace/qdrant
QDRANT__STORAGE__STORAGE_PATH=/workspace/qdrant_storage \
QDRANT__SERVICE__HOST=127.0.0.1 \
QDRANT__TELEMETRY_DISABLED=true \
nohup /workspace/qdrant/qdrant > /workspace/qdrant.log 2>&1 &
echo "qdrant launched pid $!"
