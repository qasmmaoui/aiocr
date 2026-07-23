"""
Authentification par clé API pour les endpoints publics /v1/*.

- Clés = env ADALA_API_KEYS (séparées par des virgules) ∪ fichier ADALA_KEYS_FILE
  (une clé par ligne, lignes # ignorées).
- Premier démarrage sans aucune clé : une clé est GÉNÉRÉE et écrite dans le
  fichier (sur le volume réseau -> persistante). Elle s'affiche dans les logs
  du serveur : `cat /workspace/api_keys.txt` pour la récupérer.
- Les endpoints internes /api/* (UI Streamlit sur 127.0.0.1) restent sans clé.
"""
import os
import secrets

from fastapi import Header, HTTPException

KEYS_FILE = os.environ.get("ADALA_KEYS_FILE", "/workspace/api_keys.txt")
_cache: set[str] | None = None


def _load_keys() -> set[str]:
    keys = {k.strip() for k in os.environ.get("ADALA_API_KEYS", "").split(",") if k.strip()}
    try:
        with open(KEYS_FILE, encoding="utf-8") as f:
            keys |= {ln.strip() for ln in f
                     if ln.strip() and not ln.strip().startswith("#")}
    except FileNotFoundError:
        pass
    return keys


def ensure_keys() -> set[str]:
    """Charge les clés ; en génère une au premier démarrage si aucune n'existe."""
    global _cache
    if _cache:
        return _cache
    keys = _load_keys()
    if not keys:
        new = "sk-adala-" + secrets.token_urlsafe(24)
        try:
            os.makedirs(os.path.dirname(KEYS_FILE) or ".", exist_ok=True)
            with open(KEYS_FILE, "a", encoding="utf-8") as f:
                f.write(f"# clé générée automatiquement au premier démarrage\n{new}\n")
            print(f"[auth] Aucune clé API configurée — clé générée dans {KEYS_FILE}")
        except OSError as e:
            print(f"[auth] impossible d'écrire {KEYS_FILE}: {e}")
        keys = {new}
    _cache = keys
    return keys


def reset_cache() -> None:                     # pour les tests
    global _cache
    _cache = None


async def require_api_key(authorization: str | None = Header(None)) -> str:
    """Dépendance FastAPI : exige `Authorization: Bearer <clé>`."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401,
                            detail="Missing API key (Authorization: Bearer sk-...)")
    key = authorization.split(" ", 1)[1].strip()
    if key not in ensure_keys():
        raise HTTPException(status_code=401, detail="Invalid API key")
    return key
