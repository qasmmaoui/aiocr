import sys
sys.path.insert(0, "/workspace/aiocr")
from rag.search_laws import search_laws

q = "شروط مسطرة الصلح في القانون الجنائي"
print("=== SEARCH:", q, "===")
for h in search_laws(q, limit=6):
    law = h.get("law", "")
    print("[%.3f] %s" % (h.get("score", 0), law[:50]))
    print("     file:", h.get("file", "")[:55])
    print("     ", " ".join(h.get("text", "").split())[:160])
    print()
