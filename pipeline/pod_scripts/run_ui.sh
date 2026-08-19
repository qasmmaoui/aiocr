#!/bin/bash
cd /workspace/aiocr
export PYTHONPATH=/workspace/aiocr
/workspace/venv/bin/streamlit run app.py --server.port 8888 --server.address 0.0.0.0 --server.headless true --server.fileWatcherType none --server.enableCORS false --server.enableXsrfProtection false --server.maxUploadSize 50 >/tmp/ui.log 2>&1
echo "STREAMLIT_EXITED rc=$? $(date -u)" >> /tmp/ui.log
