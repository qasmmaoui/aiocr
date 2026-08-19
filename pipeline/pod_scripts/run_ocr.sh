#!/bin/bash
cd /workspace/aiocr
source /workspace/venv/bin/activate
export FORCE_OCR=1 OCR_MODEL=qwen2.5vl:32b OCR_DPI=200 OLLAMA_KEEP_ALIVE=24h
export LAWS_DIR=/workspace/rework/input/extracted/laws_penal
export LAWS_COLLECTION=laws_penal_ocr
export LAWS_DONE_FILE=/workspace/data/ingest_penal_ocr.json
exec python rag/ingest_laws.py >> /workspace/data/ingest_ocr.log 2>&1
