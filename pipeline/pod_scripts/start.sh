#!/bin/bash
# Lanceur complet du pod — tout ce qui est durable vit sous /workspace (persiste
# aux redémarrages) : /workspace/aiocr (code), /workspace/venv (deps),
# /workspace/ollama (modèles), /workspace/qdrant + /workspace/qdrant_storage (index).
# API publique: port 8888.  API interne: 127.0.0.1:8000.  Ollama: 11434.  Qdrant: 6333.
export OLLAMA_MODELS=/workspace/ollama
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_KEEP_ALIVE=2h

# --- Paquets système (disque conteneur effacé à chaque stop) ---
apt-get update -y >/tmp/apt.log 2>&1
apt-get install -y tesseract-ocr tesseract-ocr-ara tesseract-ocr-fra git curl lshw >>/tmp/apt.log 2>&1
command -v ollama >/dev/null 2>&1 || (curl -fsSL https://ollama.com/install.sh | sh >/tmp/ollama_install.log 2>&1)

# --- Ollama (modèles sur le volume) ---
pkill -9 -f "ollama serve" 2>/dev/null; sleep 2
nohup ollama serve > /workspace/ollama.log 2>&1 &
sleep 6

# --- Qdrant (binaire + stockage sur le volume) ---
pkill -9 -f "/workspace/qdrant/qdrant" 2>/dev/null; sleep 1
if [ -x /workspace/qdrant/qdrant ]; then
  cd /workspace/qdrant
  QDRANT__STORAGE__STORAGE_PATH=/workspace/qdrant_storage \
  QDRANT__SERVICE__HOST=127.0.0.1 \
  QDRANT__TELEMETRY_DISABLED=true \
    nohup /workspace/qdrant/qdrant > /workspace/qdrant.log 2>&1 &
fi
sleep 3

# --- Application (API + UI) ---
cd /workspace/aiocr
pkill -f jupyter 2>/dev/null
pkill -f "uvicorn" 2>/dev/null; pkill -f "streamlit" 2>/dev/null; sleep 1
nohup /workspace/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 > /workspace/api.log 2>&1 &
sleep 3
export RIMLEX_ADALA_DIR=/workspace/rework/input
export RIMLEX_LAWS_DIR=/workspace/rework/input/juris
export RIMLEX_DATA_DIR=/workspace/data
export EAVOCAT_API_TOKEN=$(grep -oP "(?<=^export EAVOCAT_API_TOKEN=).*" /workspace/start_api.sh)
nohup /workspace/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8888 > /workspace/api8888.log 2>&1 &
sleep 2
echo "pod-start: ollama + qdrant + api launched (API on 8888)"
