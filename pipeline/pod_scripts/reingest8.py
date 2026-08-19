# -*- coding: utf-8 -*-
"""Ré-ingestion des huit documents réparés.

Même principe que pour le code de 2026 : on retire l'ancienne ingestion —
dans Qdrant ET dans le corpus BM25 — avant de réécrire, pour ne pas laisser
cohabiter deux versions du même texte.
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

CORPUS = "/workspace/data/laws_corpus_v2.jsonl"
docs = json.load(open("/workspace/repare8.json", encoding="utf-8"))
client = store.client()

# 1. Nettoyage du corpus lexical, en une passe pour les huit fichiers.
noms = set(docs.keys())
kept = [l for l in open(CORPUS, encoding="utf-8")
        if not any(n in l for n in noms)]
print(f"corpus BM25 : {len(kept)} lignes conservees", flush=True)

nouvelles = []
for name, d in docs.items():
    pages = d["pages"]
    offsets, pos = [], 0
    for t in pages:
        offsets.append(pos)
        pos += len(t) + 1
    full = "\n".join(pages)

    def page_of(idx):
        lo = 0
        for i, off in enumerate(offsets):
            if off <= idx:
                lo = i
            else:
                break
        return lo + 1

    col = d["collection"]
    flt = Filter(must=[FieldCondition(key="file", match=MatchValue(value=name))])
    before = client.count(col, count_filter=flt, exact=True).count
    client.delete(col, points_selector=flt)

    chunks = chunk_text(full)
    cursor, records = 0, []
    for i, ch in enumerate(chunks):
        txt = ch["text"]
        at = full.find(txt[:60], cursor)
        if at >= 0:
            cursor = at
        records.append({"text": txt, "article": ch.get("article"), "chunk": i,
                        "page": page_of(cursor if at >= 0 else 0)})

    vectors = []
    for i in range(0, len(records), 64):
        vectors.extend(embed_batch([r["text"] for r in records[i:i + 64]]))

    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{name}|{r['chunk']}")),
            vector=v,
            payload={
                "text": r["text"], "corpus": d["corpus"], "title": d["law"],
                "law": d["law"], "file": name, "folder": d["folder"],
                "chunk": str(r["chunk"]), "n_chunks": str(len(records)),
                "article": r["article"], "pages": str(len(pages)),
                "page": str(r["page"]), "page_end": str(r["page"]),
                "pdf": d["pdf"], "method": d["method"], "ocr_conf": "-1",
                "ocr_hit_rate": "1.0", "ocr_flagged": "False",
            },
        )
        for r, v in zip(records, vectors)
    ]
    for i in range(0, len(points), 128):
        client.upsert(col, points=points[i:i + 128], wait=True)

    for r in records:
        nouvelles.append(json.dumps({
            "collection": col, "file": name, "chunk": r["chunk"],
            "law": d["law"], "article": r["article"], "text": r["text"],
            "page": r["page"], "status": "current",
        }, ensure_ascii=False))

    print(f"  {name[:44]:46s} {before} -> {len(records)} fragments", flush=True)

with open(CORPUS, "w", encoding="utf-8") as f:
    f.writelines(kept)
    f.write("\n".join(nouvelles) + "\n")
print(f"corpus BM25 reecrit : +{len(nouvelles)} lignes", flush=True)
