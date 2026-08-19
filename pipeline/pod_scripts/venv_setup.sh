#!/bin/bash
LOG=/workspace/venv_setup.log
{
echo "=== VENV SETUP START $(date -u) ==="
rm -rf /workspace/venv
python3 -m venv /workspace/venv
/workspace/venv/bin/pip install --upgrade pip
/workspace/venv/bin/pip install -r /workspace/aiocr/requirements.txt
echo "=== VENV import check ==="
cd /workspace/aiocr && PYTHONPATH=/workspace/aiocr /workspace/venv/bin/python -c "import api.main; print(\"IMPORT_OK\")"
echo "=== VENV SETUP DONE $(date -u) ==="
} >> "$LOG" 2>&1
