#!/bin/bash
# ===================================================================
#  RUN AUTONOME (~4h) — données juridiques fiables (laws_penal)
#  1. Retire les anciennes versions périmées des 2 codes de base
#  2. Termine l'OCR pénal (reprise 294 -> 483)
#  3. Ré-ingère les 2 nouveaux codes en FORCE_OCR (couche texte cassée)
#  Tout est journalisé dans /workspace/overnight.log
# ===================================================================
LOG=/workspace/overnight.log
PY=/workspace/venv/bin/python
cd /workspace/aiocr || exit 1
export PYTHONPATH=/workspace/aiocr

{
echo ""
echo "==================== OVERNIGHT START $(date -u) ===================="

# --- santé des services requis -------------------------------------------
echo "--- health check $(date -u) ---"
curl -s http://127.0.0.1:6333/collections >/dev/null && echo "  qdrant: UP" || echo "  qdrant: DOWN (!!)"
curl -s http://127.0.0.1:11434/api/tags   >/dev/null && echo "  ollama: UP" || echo "  ollama: DOWN (!!)"

# --- PRE : retirer les anciens codes de base périmés ----------------------
# 104 = ancien Code pénal (1.59.413) ; 458 = ancien Code de procédure pénale
# (1.02.255, celui qui cite « المادة 41 »). Remplacés par les nouveaux uploads.
# Réversible : les PDF restent sur disque, il suffit de les ré-ingérer.
echo "--- PRE: remove old superseded core codes $(date -u) ---"
$PY - <<'PYEOF'
import sys, glob, os, json
sys.path.insert(0, '.')
from rag import store
try:
    done = set(json.load(open('/workspace/laws_penal_done.json', encoding='utf-8')))
except Exception:
    done = set()
for pref in ('104_', '458_'):
    for p in glob.glob('/workspace/laws/penal/penalAR/' + pref + '*.pdf'):
        b = os.path.basename(p)
        store.delete_by('laws_penal', 'file', b)
        done.add(b)                       # marqué "fait" -> l'étape 1 le saute
        print('  removed + skip:', b[:60])
json.dump(sorted(done), open('/workspace/laws_penal_done.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('  laws_penal count after removal:', store.count('laws_penal'))
PYEOF

# --- STEP 1 : terminer l'OCR pénal (corpus principal penalAR) -------------
echo "--- STEP1: penal OCR resume (penalAR) $(date -u) ---"
LAWS_DIR=/workspace/laws/penal/penalAR \
LAWS_COLLECTION=laws_penal \
LAWS_DONE_FILE=/workspace/laws_penal_done.json \
INGEST_LOG=/workspace/ingest_penal.log \
INGEST_OCR=1 \
bash /workspace/run_ingest.sh
echo "--- STEP1 done $(date -u) | penal=$($PY -c "import sys;sys.path.insert(0,'.');from rag import store;print(store.count('laws_penal'))") ---"

# --- STEP 2 : ré-ingérer les 2 nouveaux codes en FORCE_OCR ----------------
# Leur couche texte native est corrompue (lettres mélangées) -> on OCR toutes
# les pages depuis l'image rendue (le modèle vision lit le texte correctement).
echo "--- STEP2: OCR-reingest new codes (FORCE_OCR) $(date -u) ---"
rm -f /workspace/laws_new_done.json /workspace/laws_ingest_current.txt
: > /workspace/ingest_new.log
FORCE_OCR=1 \
INGEST_OCR=1 \
LAWS_DIR=/workspace/laws/penal/new \
LAWS_COLLECTION=laws_penal \
LAWS_DONE_FILE=/workspace/laws_new_done.json \
INGEST_LOG=/workspace/ingest_new.log \
bash /workspace/run_ingest.sh
echo "--- STEP2 done $(date -u) ---"

echo "==================== OVERNIGHT COMPLETE $(date -u) ===================="
$PY -c "import sys;sys.path.insert(0,'.');from rag import store;print('FINAL  laws_penal:',store.count('laws_penal'),'| laws_commercial:',store.count('laws_commercial'))"
echo "===================================================================="
} >> "$LOG" 2>&1
