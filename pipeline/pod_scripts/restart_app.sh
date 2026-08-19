#!/bin/bash
pkill -9 -f "uvicorn" 2>/dev/null
pkill -9 -f "streamlit run" 2>/dev/null
sleep 3
cd /workspace/aiocr
export PYTHONPATH=/workspace/aiocr
nohup /workspace/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 > /workspace/api.log 2>&1 &
sleep 4
exec /workspace/venv/bin/streamlit run app.py --server.port 8888 --server.address 0.0.0.0 --server.headless true --server.enableCORS false --server.enableXsrfProtection false --server.maxUploadSize 50
