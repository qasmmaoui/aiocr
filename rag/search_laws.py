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

# Combien de candidats puiser par collection avant pondération et fusion.
# Rien à voir avec le nombre de résultats rendus : c'est la marge de manœuvre
# laissée au classement. Trop étroite, aucun bonus ne peut rattraper un bon
# article mal placé par la similarité brute.
PROFONDEUR_FACTEUR = 8
PROFONDEUR_MIN = 50


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
    # Profondeur de puisage, distincte du nombre de résultats rendus.
    #
    # On ramenait `limit` (6) résultats par collection AVANT toute pondération.
    # Or `adala_laws_v4` compte plus de cent mille points : un article devait
    # figurer dans le tout premier peloton par similarité brute pour avoir la
    # moindre chance d'être vu, et aucun bonus de matière ou d'ancrage ne
    # pouvait le rattraper ensuite. C'est ainsi que la المادة 204 du nouveau
    # code de procédure civile — qui énonce l'unique délai d'appel de trente
    # jours — restait invisible, et que le moteur répondait « aucun texte
    # trouvé » sur une question dont la réponse était dans le corpus.
    #
    # On puise donc large et on laisse la pondération puis la fusion trancher.
    profondeur = max(limit * PROFONDEUR_FACTEUR, PROFONDEUR_MIN)
    hits: list[dict] = []
    for col in (collections or COLLECTIONS):
        if store.exists(col):
            for h in store.search(col, qvec, limit=profondeur):
                h["collection"] = col
                hits.append(h)
    hits = boost_hits(hits, matiere)
    hits.sort(key=lambda h: h.get("score", 0), reverse=True)
    # Fusion lexicale (BM25) : indispensable pour les références exactes
    # («المادة 41-1», «2.14.652») que le vectoriel seul ne retrouve pas.
    try:
        hits = fuse(hits[:profondeur], query, limit=limit)
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
