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
from rag.matieres import boost_hits, collections_for
from rag.hybrid import fuse

# Corpus juridiques interrogés (ajouter les nouveaux ici : laws_civil, ...).
COLLECTIONS = ["adala_laws_v4", "adala_juris_v4", "adala_pmp_v4"]


def search_laws(query: str, limit: int = 6, collections: list[str] | None = None,
                matiere: str | None = None, strict: bool = False) -> list[dict]:
    """`matiere` priorise un domaine (pénal, commercial…) sans masquer les
    autres ; `strict=True` restreint réellement la recherche."""
    query = (query or "").strip()
    if not query:
        return []
    if collections is None and matiere:
        try:
            available = {c.name for c in store.client().get_collections().collections}
        except Exception:
            available = None
        collections = collections_for(matiere, strict=strict, available=available)
    qvec = embed(query)
    hits: list[dict] = []
    for col in (collections or COLLECTIONS):
        if store.exists(col):
            for h in store.search(col, qvec, limit=limit):
                h["collection"] = col
                hits.append(h)
    hits = boost_hits(hits, matiere)
    hits.sort(key=lambda h: h.get("score", 0), reverse=True)
    # Fusion lexicale (BM25) : indispensable pour les références exactes
    # («المادة 41-1», «2.14.652») que le vectoriel seul ne retrouve pas.
    try:
        hits = fuse(hits[:max(limit * 3, 12)], query, limit=limit)
    except Exception:
        hits = hits[:limit]
    return hits


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "نزاع حول عقد تجاري بين شركتين"
    hits = search_laws(q)
    print(f"query: {q}\n")
    for h in hits:
        print(f"[{h['score']:.3f}] {h.get('law','')[:60]}")
        print("   ", " ".join(h.get('text', '')[:220].split()), "\n")
