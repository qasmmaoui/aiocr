LOG=/workspace/overnight.log
PY=/workspace/venv/bin/python
cd /workspace/aiocr; export PYTHONPATH=/workspace/aiocr
{
echo "=== REDO STEP2 (real FORCE_OCR) $(date -u) ==="
rm -f /workspace/laws_new_done.json /workspace/laws_ingest_current.txt
: > /workspace/ingest_new.log
FORCE_OCR=1 INGEST_OCR=1 LAWS_DIR=/workspace/laws/penal/new LAWS_COLLECTION=laws_penal \
LAWS_DONE_FILE=/workspace/laws_new_done.json INGEST_LOG=/workspace/ingest_new.log \
bash /workspace/run_ingest.sh
echo "=== REDO STEP2 DONE $(date -u) ==="
$PY -c "import sys;sys.path.insert(0,\".\");from rag import store;print(\"FINAL laws_penal:\",store.count(\"laws_penal\"))"
} >> "$LOG" 2>&1
