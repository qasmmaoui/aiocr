#!/bin/bash
# Relance des deux instances de l'API (8000 interne, 8888 publique), puis
# contrôle de fumée.
#
# Le motif de pkill est mis entre crochets pour qu'il ne se reconnaisse pas
# lui-même ; ce script doit être déposé par scp et non collé dans la commande
# SSH, sinon le motif figure dans la ligne de commande de la session et la tue.
pkill -f "[u]vicorn" 2>/dev/null; sleep 2
cd /workspace/aiocr
export OLLAMA_MODELS=/workspace/ollama OLLAMA_NUM_PARALLEL=1 OLLAMA_KEEP_ALIVE=2h
# 80 Go de VRAM : le modèle de vision 32b tient à côté du modèle de
# raisonnement, donc plus de bascule entre lire un document et répondre.
export OCR_MODEL=qwen2.5vl:32b
export RIMLEX_ADALA_DIR=/workspace/rework/input
export RIMLEX_LAWS_DIR=/workspace/rework/input/juris
export RIMLEX_DATA_DIR=/workspace/data
export EAVOCAT_API_TOKEN=$(grep -oP "(?<=^export EAVOCAT_API_TOKEN=).*" /workspace/start_api.sh)
nohup /workspace/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 > /workspace/api.log 2>&1 &
nohup /workspace/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8888 > /workspace/api8888.log 2>&1 &
sleep 25

# Contrôle de fumée : une panne de récupération est silencieuse côté API —
# elle rend un « je n'ai rien trouvé » parfaitement crédible.
echo "--- contrôle de fumée ---"
PYTHONPATH=/workspace/aiocr /workspace/venv/bin/python /workspace/aiocr/tests/fumee.py
CODE=$?
if [ $CODE -ne 0 ]; then
  echo "!!! LE MOTEUR DE RECHERCHE EST EN PANNE — ne pas ouvrir aux utilisateurs"
fi
exit $CODE
