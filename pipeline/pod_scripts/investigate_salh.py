import sys, re
sys.path.insert(0, "/workspace/aiocr")
from rag import store
from qdrant_client.models import Filter, FieldCondition, MatchValue

c = store.client()
FILE = "قانون-المسطرة-الجنائية_compressed.pdf"

# pull ALL chunks of the new procedure code, ordered by chunk index
pts, off = [], None
while True:
    batch, off = c.scroll("laws_penal",
        scroll_filter=Filter(must=[FieldCondition(key="file", match=MatchValue(value=FILE))]),
        limit=500, offset=off, with_payload=True)
    pts += batch
    if off is None:
        break
pts.sort(key=lambda p: p.payload.get("chunk", 0))
print("total chunks of new procedure code:", len(pts))

# find chunks mentioning الصلح / صلح and show the article markers inside each
art_re = re.compile(r"(الفصل|المادة)\s*[-\s]*?(\d{1,4})")
print("\n=== chunks mentioning صلح (with article markers found INSIDE the chunk) ===")
hits = 0
for p in pts:
    t = p.payload.get("text", "")
    if "الصلح" in t or "صلح" in t:
        arts = art_re.findall(t)
        arts_s = ", ".join(f"{a}{b}" for a, b in arts[:8]) or "(NO article marker in this chunk)"
        flat = " ".join(t.split())
        print(f"\n[chunk {p.payload.get('chunk')}] articles-in-chunk: {arts_s}")
        print("   ", flat[:240])
        hits += 1
        if hits >= 8:
            break
