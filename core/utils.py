"""
╔══════════════════════════════════════════════════════════════╗
║  DMSI · Adala — Utilitaires Généraux                         ║
║  core/utils.py                                               ║
╚══════════════════════════════════════════════════════════════╝
"""

import base64
import hashlib
import requests

from core.config import LOGO_PATH, OLLAMA_BASE_URL, OLLAMA_TIMEOUT, PREFERRED_MODELS, DEFAULT_MODEL


# ── Logo ──────────────────────────────────────────────────────────────────
def get_logo_b64() -> str | None:
    """Retourne le logo encodé en base64 pour l'affichage HTML, ou None."""
    paths = [LOGO_PATH, LOGO_PATH.parent.parent / "zz.png"]
    for p in paths:
        if p.exists():
            return f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}"
    return None


# ── Hash PDF ──────────────────────────────────────────────────────────────
def pdf_hash(content: bytes) -> str:
    """Retourne le hash MD5 du contenu binaire d'un PDF."""
    return hashlib.md5(content).hexdigest()


# ── Ollama ────────────────────────────────────────────────────────────────
def list_ollama_models() -> list[str]:
    """Retourne la liste des modèles disponibles dans Ollama."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=OLLAMA_TIMEOUT)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


def pick_model(candidates: list[str], available: list[str], fallback: str) -> str:
    """Sélectionne le premier modèle candidat disponible, sinon retourne le fallback."""
    for m in candidates:
        if m in available:
            return m
    return fallback


def get_vision_model() -> str:
    """Retourne le meilleur modèle vision disponible."""
    available = list_ollama_models()
    return pick_model(PREFERRED_MODELS, available, DEFAULT_MODEL)
