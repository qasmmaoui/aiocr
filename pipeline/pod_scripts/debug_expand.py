import sys
sys.path.insert(0, "/workspace/aiocr")
from rag.search_laws import search_laws
from rag.answer import _expand, _real_header

q = "شروط مسطرة الصلح في القانون الجنائي"
hits = search_laws(q, limit=8)
print("=== hits + expansion ===")
for h in hits:
    exp = _expand(h)
    injected = exp.split("\n", 1)[0] if exp.startswith("(") else "(no header injected)"
    print(f"file={h.get('file','')[:30]} chunk={h.get('chunk')} -> {injected}")
