#!/bin/bash
LOG=/workspace/reocr.log
{
echo "=== RE-OCR CORE CODES (vl:32b) START $(date -u) ==="
rm -f /workspace/laws_new_done.json /workspace/laws_ingest_current.txt
: > /workspace/ingest_new.log
FORCE_OCR=1 INGEST_OCR=1 OCR_MODEL=qwen2.5vl:32b \
LAWS_DIR=/workspace/laws/penal/new LAWS_COLLECTION=laws_penal \
LAWS_DONE_FILE=/workspace/laws_new_done.json INGEST_LOG=/workspace/ingest_new.log \
bash /workspace/run_ingest.sh
echo "=== RE-OCR DONE $(date -u) ==="
grep -a "INGEST_COMPLETE\|-> " /workspace/ingest_new.log | tail -4
} >> "$LOG" 2>&1
