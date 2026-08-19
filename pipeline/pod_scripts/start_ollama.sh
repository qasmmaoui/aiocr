#!/bin/bash
export OLLAMA_MODELS=/workspace/ollama
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=2
export OLLAMA_KEEP_ALIVE=2h
exec ollama serve
