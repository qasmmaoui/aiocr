#!/bin/bash
LOG=/workspace/pull_models.log
{
echo "=== PULL START $(date -u) ==="
echo "--- pulling qwen2.5:32b (reasoning) ---"
ollama pull qwen2.5:32b
echo "--- pulling qwen2.5vl:32b (OCR vision) ---"
ollama pull qwen2.5vl:32b
echo "=== PULL DONE $(date -u) ==="
ollama list
} >> "$LOG" 2>&1
