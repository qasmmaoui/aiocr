"""
Embeddings via Ollama (bge-m3, multilingue, fort en arabe). 1024 dimensions.
Utilise /api/embed (traitement par lots) pour saturer le GPU au lieu d'appels
un-par-un. Aucun préfixe requis (contrairement à e5).
"""
import time
import requests

from core.config import OLLAMA_BASE_URL

EMBED_MODEL = "bge-m3"
EMBED_DIM   = 1024
_RETRIES    = 6


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embeddings d'un lot de textes en un seul appel (une passe GPU).
    Réessaie sur erreur transitoire (redémarrage d'Ollama, etc.)."""
    inputs = [((t or " ").strip()[:6000] or " ") for t in texts]
    last: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            r = requests.post(
                f"{OLLAMA_BASE_URL}/api/embed",
                json={"model": EMBED_MODEL, "input": inputs},
                timeout=300,
            )
            r.raise_for_status()
            return r.json()["embeddings"]
        except Exception as e:  # noqa: BLE001 — transitoire, on réessaie
            last = e
            time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def embed(text: str) -> list[float]:
    """Embedding d'un seul texte (ex. une requête)."""
    return embed_batch([text])[0]
