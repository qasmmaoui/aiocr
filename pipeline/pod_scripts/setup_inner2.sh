#!/bin/bash
exec > /workspace/setup.log 2>&1
echo "SETUP2_START $(date -u)"
set -x
export OLLAMA_MODELS=/workspace/ollama
mkdir -p /workspace/ollama
# system deps (container disk; start.sh reinstalls on future boots)
apt-get update -y
apt-get install -y tesseract-ocr tesseract-ocr-ara tesseract-ocr-fra git curl lshw
command -v ollama >/dev/null 2>&1 || (curl -fsSL https://ollama.com/install.sh | sh)
# start ollama and pull the model onto the persistent volume
pkill -f "ollama serve" 2>/dev/null; sleep 1
OLLAMA_MODELS=/workspace/ollama nohup ollama serve > /workspace/ollama.log 2>&1 &
sleep 6
ollama pull qwen2.5vl:7b
# persistent python venv on the volume
python3 -m venv /workspace/venv
/workspace/venv/bin/pip install --upgrade pip -q
cd /workspace/aiocr
/workspace/venv/bin/pip install -r requirements.txt -q
echo "SETUP2_FILES_DONE $(date -u)"
# launch the app
bash /workspace/start.sh
sleep 12
echo "HEALTH:"; curl -s localhost:8000/api/health
echo ""
echo "PORTS:"; ss -tlnp 2>/dev/null | grep -E ':8501|:8000'
echo "MODEL:"; ls /workspace/ollama/models/manifests/registry.ollama.ai/library 2>/dev/null
echo "SETUP2_DONE $(date -u)"
