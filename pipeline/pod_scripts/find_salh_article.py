import sys, re
sys.path.insert(0, "/workspace/aiocr")
from rag import store
from qdrant_client.models import Filter, FieldCondition, MatchValue

c = store.client()
FILE = "قانون-المسطرة-الجنائية_compressed.pdf"
pts, off = [], None
while True:
    b, off = c.scroll("laws_penal",
        scroll_filter=Filter(must=[FieldCondition(key="file", match=MatchValue(value=FILE))]),
        limit=500, offset=off, with_payload=True)
    pts += b
    if off is None:
        break
pts.sort(key=lambda p: p.payload.get("chunk", 0))

# distinctive الصلح-procedure phrases
needles = ["نصف الحد الأقصى", "يقترح", "محضر الصلح", "مسطرة الصلح", "على المشتكى", "بالصلح"]
art_re = re.compile(r"(الفصل|المادة)\s*[-\s]*?(\d{1,4})")
print("scanning", len(pts), "chunks for الصلح-procedure text + its article header\n")
for idx, p in enumerate(pts):
    t = p.payload.get("text", "")
    if any(n in t for n in needles):
        # article markers in THIS chunk and the PREVIOUS chunk (header may be split off)
        prev = pts[idx-1].payload.get("text", "") if idx > 0 else ""
        arts_here = [f"{a}{b}" for a, b in art_re.findall(t)]
        arts_prev = [f"{a}{b}" for a, b in art_re.findall(prev)]
        flat = " ".join(t.split())
        print(f"[chunk {p.payload.get('chunk')}] arts_here={arts_here[:6]} | arts_prev_chunk={arts_prev[-3:]}")
        print("   ", flat[:230], "\n")
