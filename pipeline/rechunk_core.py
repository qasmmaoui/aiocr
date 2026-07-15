"""
Re-découpe les fichiers donnés avec le NOUVEAU chunker (article-aware), SANS ré-OCR.
Reconstruit le texte à partir des chunks existants dans Qdrant, re-chunk, re-embed,
puis remplace — mais UNIQUEMENT si le nouveau découpage est valide (garde-fou).
Usage: python rechunk_core.py <collection> <file1.pdf> [file2.pdf ...]
"""
import sys, uuid
sys.path.insert(0, "/workspace/aiocr")
from rag import store
from rag.chunker import chunk_text
from rag.embeddings import embed_batch
from qdrant_client.models import Filter, FieldCondition, MatchValue


def file_chunks_sorted(col, f):
    c = store.client()
    pts, off = [], None
    while True:
        b, off = c.scroll(col, scroll_filter=Filter(must=[
            FieldCondition(key="file", match=MatchValue(value=f))]),
            limit=500, offset=off, with_payload=True)
        pts += b
        if off is None:
            break
    pts.sort(key=lambda p: p.payload.get("chunk", 0))
    return pts


def rechunk(col, f):
    pts = file_chunks_sorted(col, f)
    if not pts:
        print(f"  SKIP {f[:40]}: no existing chunks")
        return
    law = pts[0].payload.get("law", "")
    full = " ".join(p.payload.get("text", "") for p in pts)
    new = chunk_text(full)
    # garde-fou : le nouveau découpage doit être non vide et capturer des articles
    arts = [c["article"] for c in new if c["article"]]
    if len(new) < 5 or len(arts) < 3:
        print(f"  ABORT {f[:40]}: new chunking looks wrong "
              f"(chunks={len(new)}, articles={len(arts)}) — kept OLD chunks")
        return
    texts = [c["text"] for c in new]
    vecs = []
    for i in range(0, len(texts), 64):
        vecs += embed_batch(texts[i:i + 64])
    points = [
        (str(uuid.uuid4()), vecs[i],
         {"text": new[i]["text"], "law": law, "file": f,
          "chunk": i, "article": new[i].get("article")})
        for i in range(len(new))
    ]
    store.delete_by(col, "file", f)
    for i in range(0, len(points), 256):
        store.upsert(col, points[i:i + 256])
    print(f"  OK {f[:40]}: {len(pts)} old -> {len(new)} new chunks, "
          f"{len(set(arts))} distinct articles")


if __name__ == "__main__":
    col = sys.argv[1]
    for f in sys.argv[2:]:
        rechunk(col, f)
    print("laws_penal total now:", store.count("laws_penal"))
