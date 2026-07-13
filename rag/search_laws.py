"""
Recherche sémantique dans le corpus juridique (grounded).
  search_laws("نزاع حول عقد تجاري") -> [{score, text, law, file, ...}, ...]
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from rag.embeddings import embed
from rag import store

# Corpus juridiques interrogés (ajouter les nouveaux ici : laws_civil, ...).
COLLECTIONS = ["laws_commercial", "laws_penal"]


def search_laws(query: str, limit: int = 6, collections: list[str] | None = None) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    qvec = embed(query)
    hits: list[dict] = []
    for col in (collections or COLLECTIONS):
        if store.exists(col):
            for h in store.search(col, qvec, limit=limit):
                h["collection"] = col
                hits.append(h)
    hits.sort(key=lambda h: h.get("score", 0), reverse=True)
    return hits[:limit]


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "نزاع حول عقد تجاري بين شركتين"
    hits = search_laws(q)
    print(f"query: {q}\n")
    for h in hits:
        print(f"[{h['score']:.3f}] {h.get('law','')[:60]}")
        print("   ", " ".join(h.get('text', '')[:220].split()), "\n")
