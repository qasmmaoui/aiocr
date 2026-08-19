"""
Vector store = serveur Qdrant local (http://127.0.0.1:6333).
Une collection par usage : `laws_commercial` (corpus juridique),
et plus tard `case_<id>` (documents d'une affaire) — le filtrage par
collection/`case_id` est natif dans Qdrant.
"""
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, FilterSelector,
)

from rag.embeddings import EMBED_DIM

QDRANT_URL = "http://127.0.0.1:6333"
_client: QdrantClient | None = None


def client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, timeout=60)
    return _client


def _names() -> list[str]:
    return [c.name for c in client().get_collections().collections]


def ensure_collection(name: str, dim: int = EMBED_DIM) -> None:
    if name not in _names():
        client().create_collection(
            name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
        )


def recreate_collection(name: str, dim: int = EMBED_DIM) -> None:
    c = client()
    if name in _names():
        c.delete_collection(name)
    c.create_collection(name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))


def upsert(name: str, points) -> None:
    """points: iterable de (id:int, vector:list[float], payload:dict)."""
    client().upsert(
        name,
        points=[PointStruct(id=i, vector=v, payload=p) for i, v, p in points],
    )


def search(name: str, vector, limit: int = 8, flt: dict | None = None) -> list[dict]:
    # Désactivation douce : un fragment mis de côté (doublon, débris trop court)
    # reste stocké — on peut le rétablir — mais ne participe plus aux réponses.
    conds = [FieldCondition(key="disabled", match=MatchValue(value=True))]
    must = [FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in (flt or {}).items()]
    qf = Filter(must=must or None, must_not=conds)
    resp = client().query_points(
        name, query=vector, limit=limit, query_filter=qf, with_payload=True
    )
    return [{"score": float(p.score), **(p.payload or {})} for p in resp.points]


def delete_by(name: str, key: str, value) -> None:
    """Supprime tous les points dont payload[key] == value (idempotence)."""
    try:
        client().delete(
            name,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key=key, match=MatchValue(value=value))])
            ),
        )
    except Exception:
        pass


def count(name: str) -> int:
    try:
        return client().count(name).count
    except Exception:
        return 0


def exists(name: str) -> bool:
    try:
        return name in _names()
    except Exception:
        return False
