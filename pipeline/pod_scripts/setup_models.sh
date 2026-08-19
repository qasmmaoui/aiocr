#!/bin/bash
LOG=/workspace/setup_models.log
{
echo "=== SETUP MODELS START $(date -u) ==="
command -v ollama >/dev/null 2>&1 || (curl -fsSL https://ollama.com/install.sh | sh)
pkill -9 -f "ollama serve" 2>/dev/null; pkill -9 -f "llama" 2>/dev/null; sleep 3
export OLLAMA_MODELS=/workspace/ollama
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_KEEP_ALIVE=30m
setsid ollama serve >/workspace/ollama.log 2>&1 </dev/null &
sleep 8
echo "--- pulling bge-m3 ---"; ollama pull bge-m3
echo "--- pulling qwen2.5:72b (reasoning ~42G) ---"; ollama pull qwen2.5:72b
echo "--- pulling qwen2.5vl:32b (OCR vision ~21G) ---"; ollama pull qwen2.5vl:32b
echo "=== SETUP MODELS DONE $(date -u) ==="
ollama list
} >> "$LOG" 2>&1
