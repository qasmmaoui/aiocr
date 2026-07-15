#!/bin/bash
# Hands-off finalisation: re-chunk core codes (new chunker) -> restart chat on 32B
# (CPU embeddings) -> self-test -> auto-stop the pod. Robust: only stops if the
# self-test produced a real answer; otherwise leaves the pod up for inspection.
LOG=/workspace/overnight2.log
PY=/workspace/venv/bin/python
POD=edk15so0hh5mdx
cd /workspace/aiocr || exit 1
export PYTHONPATH=/workspace/aiocr
{
echo ""
echo "==================== OVERNIGHT2 START $(date -u) ===================="
curl -s http://127.0.0.1:11434/api/tags >/dev/null && echo "ollama UP" || echo "ollama DOWN (!!)"

# --- STEP 1: re-chunk the 2 core codes with the article-aware chunker (GPU embeds) ---
echo "--- STEP1 rechunk core codes $(date -u) ---"
$PY /workspace/rechunk_core.py laws_penal "القانون-الجنائي.pdf" "قانون-المسطرة-الجنائية_compressed.pdf"

# --- STEP 2: restart API+UI on the 32B model (restart_app.sh sets EMBED_NUM_GPU=0) ---
echo "--- STEP2 restart app on 32B $(date -u) ---"
setsid bash /workspace/restart_app.sh >/workspace/ui.log 2>&1 </dev/null &
sleep 22
curl -s http://127.0.0.1:8000/api/health >/dev/null && echo "api up" || echo "api DOWN"

# --- STEP 3: self-test the مسطرة الصلح question, save the answer for review ---
echo "--- STEP3 self-test $(date -u) ---"
cat > /workspace/q.json <<'JSON'
{"question":"ما هي شروط مسطرة الصلح في القانون الجنائي مع ذكر الفصول والمواد؟","k":5}
JSON
curl -s --max-time 280 -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" --data @/workspace/q.json > /workspace/selftest.json 2>&1
$PY -c "import json;d=json.load(open('/workspace/selftest.json',encoding='utf-8'));open('/workspace/selftest.txt','w',encoding='utf-8').write(d.get('answer','') or '')" 2>>"$LOG"
echo "===== SELF-TEST ANSWER ====="; cat /workspace/selftest.txt 2>/dev/null; echo ""; echo "==========================="

# --- STEP 4: auto-stop the pod (only if the self-test produced a real answer) ---
echo "--- STEP4 auto-stop $(date -u) ---"
CHARS=$(wc -c < /workspace/selftest.txt 2>/dev/null || echo 0)
if [ "$CHARS" -gt 200 ]; then
  echo "self-test OK ($CHARS chars) -> stopping pod $POD $(date -u)"
  runpodctl stop pod "$POD"
  echo "stop rc=$?"
else
  echo "self-test SHORT/FAILED ($CHARS chars) -> leaving pod UP for inspection"
fi
echo "==================== OVERNIGHT2 DONE $(date -u) ===================="
} >> "$LOG" 2>&1
