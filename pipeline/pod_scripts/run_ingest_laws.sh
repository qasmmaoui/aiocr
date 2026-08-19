#!/bin/bash
# Ingestion robuste : reset propre puis boucle qui reprend après tout crash.
cd /workspace/aiocr || exit 1
export PYTHONPATH=/workspace/aiocr

# Reset propre (collection + manifeste) — une seule fois, au début.
rm -f /workspace/laws_ingest_done.json /workspace/laws_ingest_current.txt
/workspace/venv/bin/python -c "import sys; sys.path.insert(0,'.'); from rag import store; store.recreate_collection('laws_commercial'); print('collection reset')" >> /workspace/ingest.log 2>&1

for i in $(seq 1 30); do
  /workspace/venv/bin/python -m rag.ingest_laws >> /workspace/ingest.log 2>&1
  if grep -q INGEST_COMPLETE /workspace/ingest.log; then
    echo "WRAPPER: complete after $i run(s)" >> /workspace/ingest.log
    break
  fi
  echo "WRAPPER: process exited without completing (crash?) — resuming (run $i)" >> /workspace/ingest.log
  sleep 2
done
