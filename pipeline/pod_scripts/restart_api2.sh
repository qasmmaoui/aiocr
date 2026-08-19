#!/bin/bash
# Relance des deux instances de l'API (8000 interne, 8888 publique).
# Le motif est mis entre crochets pour que pkill ne se reconnaisse pas lui-même ;
# ce script est déposé par scp plutôt que collé dans la commande SSH, sinon le
# motif figure dans la ligne de commande de la session et la tue.
pkill -f "[u]vicorn" 2>/dev/null; sleep 2
cd /workspace/aiocr
export OLLAMA_MODELS=/workspace/ollama OLLAMA_NUM_PARALLEL=1 OLLAMA_KEEP_ALIVE=2h
export RIMLEX_ADALA_DIR=/workspace/rework/input
export RIMLEX_LAWS_DIR=/workspace/rework/input/juris
export RIMLEX_DATA_DIR=/workspace/data
export EAVOCAT_API_TOKEN=$(grep -oP "(?<=^export EAVOCAT_API_TOKEN=).*" /workspace/start_api.sh)
nohup /workspace/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 > /workspace/api.log 2>&1 &
nohup /workspace/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8888 > /workspace/api8888.log 2>&1 &
sleep 1
echo relance-ok
