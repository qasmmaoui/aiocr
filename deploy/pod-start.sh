#!/bin/bash
# Adala OCR launcher — UI on port 8888 (the pod's exposed HTTP port). Run after each pod Start.
export OLLAMA_MODELS=/workspace/ollama
apt-get update -y >/tmp/apt.log 2>&1
apt-get install -y tesseract-ocr tesseract-ocr-ara tesseract-ocr-fra git curl lshw >>/tmp/apt.log 2>&1
command -v ollama >/dev/null 2>&1 || (curl -fsSL https://ollama.com/install.sh | sh >/tmp/ollama_install.log 2>&1)
pkill -f "ollama serve" 2>/dev/null; sleep 1
OLLAMA_MODELS=/workspace/ollama nohup ollama serve > /workspace/ollama.log 2>&1 &
sleep 6
cd /workspace/aiocr
# Free the exposed port 8888 (stop Jupyter) so the UI can use it
pkill -f jupyter 2>/dev/null
pkill -f "uvicorn" 2>/dev/null; pkill -f "streamlit" 2>/dev/null; sleep 1
nohup /workspace/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 > /workspace/api.log 2>&1 &
sleep 3
nohup /workspace/venv/bin/streamlit run app.py --server.port 8888 --server.address 0.0.0.0 \
  --server.headless true --server.enableCORS false --server.enableXsrfProtection false \
  --server.maxUploadSize 50 > /workspace/ui.log 2>&1 &
sleep 2
echo "start.sh: services launched (UI on 8888, API on 8000)"
