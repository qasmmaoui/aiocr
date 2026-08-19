#!/bin/bash
# Attend la fin PROPRE de l OCR (file2) puis stoppe le pod. Sûr : si ça n a pas
# fini proprement (pas de INGEST_COMPLETE done=2/2), laisse le pod ALLUMÉ.
LOG=/workspace/autostop.log
POD=5abylye38ze4p1
{
echo "=== WATCHER START $(date -u) — waiting for OCR to finish ==="
while pgrep -f "redo[_]new|ingest[_]laws" >/dev/null; do sleep 30; done
echo "=== ingest ended $(date -u) ==="
sleep 5
if grep -q "INGEST_COMPLETE done=2/2" /workspace/ingest_new.log; then
  echo "=== INGEST_COMPLETE confirmed — stopping pod $POD $(date -u) ==="
  runpodctl stop pod "$POD"
  echo "stop rc=$?"
else
  echo "=== NOT complete cleanly — leaving pod UP for inspection $(date -u) ==="
  tail -6 /workspace/ingest_new.log
fi
echo "=== WATCHER END $(date -u) ==="
} >> "$LOG" 2>&1
