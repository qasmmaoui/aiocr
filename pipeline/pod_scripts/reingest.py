# -*- coding: utf-8 -*-
"""Ré-ingestion du code de procédure civile 2026 depuis le texte GÉOMÉTRIQUE.

La couche texte du PDF inverse le lam et l'alef qui le suit (« لأ » sort « أل »,
« لا » sort « ال »), ce qui rend le document quasi introuvable en recherche
lexicale : une requête écrite normalement ne rencontre jamais ces formes. On
repart donc du texte reconstruit par l'extracteur géométrique, et on remplace
proprement l'ingestion précédente — dans Qdrant ET dans le corpus BM25.
"""
import json
import sys
import uuid

sys.path.insert(0, "/workspace/aiocr")
from rag import store                                      # noqa: E402
from rag.chunker import chunk_text                         # noqa: E402
from rag.embeddings import embed_batch                     # noqa: E402
from qdrant_client.http.models import (FieldCondition,     # noqa: E402
                                       Filter, MatchValue, PointStruct)

COLLECTION = "adala_laws_v4"
CORPUS = "/workspace/data/laws_corpus_v2.jsonl"
BASE = "ظهير شريف رقم 1.26.07 بتنفيذ القانون رقم 58.25 المتعلق بالمسطرة المدنية-2026.pdf"
LAW = "قانون المسطرة المدنية 58.25 (2026)"
FOLDER = "المادة المدنية"

pages = json.load(open("/workspace/cpc_pages.json", encoding="utf-8"))
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


client = store.client()
flt = Filter(must=[FieldCondition(key="file", match=MatchValue(value=BASE))])
before = client.count(COLLECTION, count_filter=flt, exact=True).count
client.delete(COLLECTION, points_selector=flt)
print(f"ancienne ingestion retiree : {before} fragments", flush=True)

kept = [l for l in open(CORPUS, encoding="utf-8") if BASE not in l]
print(f"corpus BM25 : {len(kept)} lignes conservees", flush=True)

chunks = chunk_text(full)
cursor, records = 0, []
for i, ch in enumerate(chunks):
    txt = ch["text"]
    at = full.find(txt[:60], cursor)
    if at >= 0:
        cursor = at
    records.append({
        "text": txt, "article": ch.get("article"), "chunk": i,
        "page": page_of(cursor if at >= 0 else 0), "n_chunks": len(chunks),
    })
print(f"{len(pages)} pages -> {len(records)} passages", flush=True)

vectors = []
for i in range(0, len(records), 64):
    vectors.extend(embed_batch([r["text"] for r in records[i:i + 64]]))
print("vectorisation terminee", flush=True)

points = [
    PointStruct(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{BASE}|{r['chunk']}")),
        vector=v,
        payload={
            "text": r["text"], "corpus": "adala_pdfs", "title": LAW, "law": LAW,
            "file": BASE, "folder": FOLDER, "chunk": str(r["chunk"]),
            "n_chunks": str(r["n_chunks"]), "article": r["article"],
            "pages": str(len(pages)), "page": str(r["page"]),
            "page_end": str(r["page"]),
            "pdf": f"rework/input/laws_all/{FOLDER}/{BASE}",
            "method": "geometric", "ocr_conf": "-1",
            "ocr_hit_rate": "1.0", "ocr_flagged": "False",
        },
    )
    for r, v in zip(records, vectors)
]
for i in range(0, len(points), 128):
    client.upsert(COLLECTION, points=points[i:i + 128], wait=True)
print("Qdrant :", client.count(COLLECTION, count_filter=flt, exact=True).count,
      "fragments pour ce code", flush=True)

with open(CORPUS, "w", encoding="utf-8") as f:
    f.writelines(kept)
    for r in records:
        f.write(json.dumps({
            "collection": COLLECTION, "file": BASE, "chunk": r["chunk"],
            "law": LAW, "article": r["article"], "text": r["text"],
            "page": r["page"], "status": "current",
        }, ensure_ascii=False) + "\n")
print("corpus BM25 reecrit", flush=True)
