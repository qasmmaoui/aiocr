# -*- coding: utf-8 -*-
"""Ingestion d'UN texte de loi dans l'index existant.

Écrit aux deux endroits que le moteur interroge :
  - la collection Qdrant `adala_laws_v4` (recherche vectorielle) ;
  - le corpus JSONL `laws_corpus_v2.jsonl` (BM25 + ancrage par article),
    sans lequel « المادة 134 من قانون المسطرة المدنية » ne trouve rien.
Le découpage réutilise rag.chunker : un passage par article, en-tête recopié.
"""
import json
import os
import sys
import uuid

import fitz

sys.path.insert(0, "/workspace/aiocr")
from rag import store                      # noqa: E402
from rag.chunker import chunk_text          # noqa: E402
from rag.embeddings import embed_batch      # noqa: E402
from qdrant_client.http.models import PointStruct  # noqa: E402

PDF = sys.argv[1]
FOLDER = sys.argv[2]
LAW = sys.argv[3]
COLLECTION = "adala_laws_v4"
CORPUS = "/workspace/data/laws_corpus_v2.jsonl"

doc = fitz.open(PDF)
pages = [p.get_text() or "" for p in doc]
n_pages = len(doc)
doc.close()

# Page de chaque passage : on suit la position du texte dans la concaténation.
offsets, pos = [], 0
for t in pages:
    offsets.append(pos)
    pos += len(t) + 1
full = "\n".join(pages)

def page_of(idx: int) -> int:
    lo = 0
    for i, off in enumerate(offsets):
        if off <= idx:
            lo = i
        else:
            break
    return lo + 1

chunks = chunk_text(full)
print(f"{n_pages} pages -> {len(chunks)} passages", flush=True)

cursor = 0
records = []
for i, ch in enumerate(chunks):
    txt = ch["text"]
    at = full.find(txt[:60], cursor)
    if at >= 0:
        cursor = at
    pg = page_of(cursor if at >= 0 else 0)
    records.append({
        "text": txt, "article": ch.get("article"), "chunk": i,
        "page": pg, "n_chunks": len(chunks),
    })

vectors = []
B = 64
for i in range(0, len(records), B):
    vectors.extend(embed_batch([r["text"] for r in records[i:i + B]]))
    print(f"  vectorisés {min(i + B, len(records))}/{len(records)}", flush=True)

base = os.path.basename(PDF)
points = []
for r, v in zip(records, vectors):
    payload = {
        "text": r["text"], "corpus": "adala_pdfs", "title": LAW, "law": LAW,
        "file": base, "folder": FOLDER, "chunk": str(r["chunk"]),
        "n_chunks": str(r["n_chunks"]), "article": r["article"],
        "pages": str(n_pages), "page": str(r["page"]),
        "page_end": str(r["page"]),
        "pdf": f"rework/input/laws_all/{FOLDER}/{base}",
        "method": "arabic_text", "ocr_conf": "-1",
        "ocr_hit_rate": "1.0", "ocr_flagged": "False",
    }
    points.append(PointStruct(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{base}|{r['chunk']}")),
        vector=v, payload=payload))

client = store.client()
for i in range(0, len(points), 128):
    client.upsert(COLLECTION, points=points[i:i + 128], wait=True)
print("Qdrant :", client.count(COLLECTION, exact=True).count, "fragments au total", flush=True)

with open(CORPUS, "a", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps({
            "collection": COLLECTION, "file": base, "chunk": r["chunk"],
            "law": LAW, "article": r["article"], "text": r["text"],
            "page": r["page"], "status": "current",
        }, ensure_ascii=False) + "\n")
print("corpus BM25 : +", len(records), "lignes", flush=True)
