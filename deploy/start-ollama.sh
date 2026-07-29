#!/bin/bash
# Detached Ollama launcher. Run: setsid bash start_ollama.sh >/workspace/ollama.log 2>&1 </dev/null &
pkill -9 -f "ollama serve" 2>/dev/null
sleep 3
export OLLAMA_MODELS=/workspace/ollama
export OLLAMA_NUM_PARALLEL=4
export OLLAMA_KEEP_ALIVE=30m
exec ollama serve
