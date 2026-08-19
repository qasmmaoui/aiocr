#!/bin/bash
cd /workspace/adala_corpus
exec /workspace/venv/bin/python make_chunks_v4.py --workers 24
