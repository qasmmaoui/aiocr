#!/bin/bash
cd /workspace/adala_corpus
/workspace/venv/bin/python ingest_jsonl.py adala_pdfs
/workspace/venv/bin/python ingest_jsonl.py pmp_textes
/workspace/venv/bin/python ingest_jsonl.py jurisprudence
