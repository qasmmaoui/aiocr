#!/bin/bash
# Ingestion générique, robuste et REPRENABLE. Piloté par variables d'environnement :
#   LAWS_DIR, LAWS_COLLECTION, LAWS_DONE_FILE, INGEST_LOG, INGEST_OCR, RESET
#
# Reprise (par défaut) : garde la collection + le manifeste, saute les fichiers déjà faits.
#   LAWS_DIR=/workspace/laws/penal LAWS_COLLECTION=laws_penal \
#   LAWS_DONE_FILE=/workspace/laws_penal_done.json INGEST_LOG=/workspace/ingest_penal.log \
#   INGEST_OCR=1 setsid bash run_ingest.sh </dev/null &
#
# Repartir de zéro : ajouter RESET=1 (efface la collection + le manifeste).
cd /workspace/aiocr || exit 1
export PYTHONPATH=/workspace/aiocr
export LAWS_DIR LAWS_COLLECTION LAWS_DONE_FILE INGEST_OCR

COL="${LAWS_COLLECTION:-laws_commercial}"
DONE="${LAWS_DONE_FILE:-/workspace/laws_ingest_done.json}"
LOG="${INGEST_LOG:-/workspace/ingest.log}"

if [ "${RESET:-0}" = "1" ]; then
  rm -f "$DONE" /workspace/laws_ingest_current.txt
  /workspace/venv/bin/python -c "import sys; sys.path.insert(0,'.'); from rag import store; store.recreate_collection('$COL'); print('RESET — collection recreated:', '$COL')" >> "$LOG" 2>&1
else
  /workspace/venv/bin/python -c "import sys; sys.path.insert(0,'.'); from rag import store; store.ensure_collection('$COL'); print('RESUME — collection kept:', '$COL', 'count=', store.count('$COL'))" >> "$LOG" 2>&1
fi

for i in $(seq 1 40); do
  /workspace/venv/bin/python -m rag.ingest_laws >> "$LOG" 2>&1
  if grep -q INGEST_COMPLETE "$LOG"; then
    echo "WRAPPER: complete after $i run(s)" >> "$LOG"
    break
  fi
  echo "WRAPPER: process exited without completing — resuming (run $i)" >> "$LOG"
  sleep 2
done
