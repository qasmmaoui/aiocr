#!/bin/bash
cd /workspace/aiocr
export RIMLEX_ADALA_DIR=/workspace/rework/input
export RIMLEX_LAWS_DIR=/workspace/rework/input/juris
export RIMLEX_DATA_DIR=/workspace/data
# Jeton partagé avec e-avocat (Paramètres › IA › Jeton d'accès RimLex).
# Jeton retiré du dépôt : le vrai vit sur le volume du pod et dans la
# sauvegarde hors dépôt. Fournir par l'environnement avant de lancer.
export EAVOCAT_API_TOKEN=${EAVOCAT_API_TOKEN:?jeton absent}
exec /workspace/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8888
