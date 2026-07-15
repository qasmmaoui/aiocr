"""Exporte le corpus juridique (chunks propres + métadonnées) en JSONL portable.
Une ligne = {collection, law, file, article, chunk, text}. Réutilisable partout.
"""
import json, sys, os
sys.path.insert(0, "/workspace/aiocr")
from rag import store

os.makedirs("/workspace/export", exist_ok=True)
out_path = "/workspace/export/laws_corpus.jsonl"
total = 0
with open(out_path, "w", encoding="utf-8") as out:
    c = store.client()
    for col in ["laws_commercial", "laws_penal"]:
        off = None
        n = 0
        while True:
            pts, off = c.scroll(col, limit=1000, offset=off,
                                with_payload=True, with_vectors=False)
            for p in pts:
                pl = p.payload or {}
                out.write(json.dumps({
                    "collection": col,
                    "law": pl.get("law"),
                    "file": pl.get("file"),
                    "article": pl.get("article"),
                    "chunk": pl.get("chunk"),
                    "text": pl.get("text"),
                }, ensure_ascii=False) + "\n")
                n += 1
            if off is None:
                break
        print(f"{col}: {n} chunks")
        total += n
print(f"TOTAL: {total} chunks -> {out_path}")
