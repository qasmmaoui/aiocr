#!/bin/bash
# Detached Streamlit (re)start. Launch with: setsid bash restart_ui.sh </dev/null &
pkill -9 -f "streamlit run" 2>/dev/null
sleep 3
cd /workspace/aiocr
exec /workspace/venv/bin/streamlit run app.py \
  --server.port 8888 --server.address 0.0.0.0 \
  --server.headless true --server.enableCORS false --server.enableXsrfProtection false \
  --server.maxUploadSize 50
