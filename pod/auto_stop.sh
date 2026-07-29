#!/bin/bash
# Surveillance d'un job long puis arrêt automatique du pod.
#
# Leçon du 29/07 : l'OCR s'est terminé à 5h07, le pod a facturé jusqu'au réveil
# de l'utilisateur. L'assistant n'agit que lorsqu'on lui écrit — la coupure
# doit donc vivre SUR le pod, pas dans la conversation.
#
#   bash pod/auto_stop.sh <motif-de-fin> <fichier-log> [pod_id]
#
# Sécurité : si le motif n'apparaît jamais (job planté), le pod reste ALLUMÉ —
# on ne coupe que sur une fin propre, jamais sur un silence.

MOTIF="${1:-INGEST_COMPLETE}"
LOG="${2:-/workspace/data/ingest_ocr.log}"
POD_ID="${3:-$RUNPOD_POD_ID}"
EXPORT_DIR=/workspace/export_final

echo "[auto-stop] surveille « $MOTIF » dans $LOG (pod $POD_ID)"

while ! grep -q "$MOTIF" "$LOG" 2>/dev/null; do
    sleep 60
done
echo "[auto-stop] job terminé à $(date -u '+%F %T UTC')"

# 1. export avant toute coupure : le calcul ne doit jamais être perdu
mkdir -p "$EXPORT_DIR"
cd /workspace/aiocr && source /workspace/venv/bin/activate
for COL in laws_penal_ocr laws_commercial; do
    curl -s -X POST "localhost:6333/collections/$COL/snapshots" > /dev/null 2>&1
done
cp /workspace/data/*.jsonl /workspace/data/*.log "$EXPORT_DIR"/ 2>/dev/null
echo "[auto-stop] export prêt dans $EXPORT_DIR"

# 2. arrêt (jamais de terminate : le volume et les données restent)
if command -v runpodctl > /dev/null && [ -n "$POD_ID" ]; then
    echo "[auto-stop] arrêt du pod $POD_ID dans 5 min (fenêtre d'annulation)"
    sleep 300
    runpodctl stop pod "$POD_ID"
else
    echo "[auto-stop] runpodctl absent ou POD_ID inconnu — pod laissé allumé"
fi
