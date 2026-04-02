"""
╔══════════════════════════════════════════════════════════════╗
║  DMSI · Adala — Configuration Centrale                       ║
║  core/config.py                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

import multiprocessing
from pathlib import Path


# ── Chemins ──────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR   = BASE_DIR / "data"
DIR_UPLOAD = DATA_DIR / "uploads"
DIR_CACHE  = DATA_DIR / "cache_corrections"
DIR_INDEX  = DATA_DIR / "search_index"
ASSETS_DIR = BASE_DIR / "assets"
LOGO_PATH  = ASSETS_DIR / "zz.png"

for d in [DIR_UPLOAD, DIR_CACHE, DIR_INDEX, ASSETS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ── Ollama / LLM ─────────────────────────────────────────────────────────
OLLAMA_BASE_URL   = "http://localhost:11434"
OLLAMA_TIMEOUT    = 3
PREFERRED_MODELS  = ["qwen2.5vl:3b", "qwen2.5vl:7b", "qwen3-vl:4b", "qwen2.5:1.5b"]
DEFAULT_MODEL     = "qwen2.5vl:3b"

CPU    = multiprocessing.cpu_count()
N_THREADS = max(2, CPU - 2)

LLM_OPTIONS = {
    "num_thread":  N_THREADS,
    "num_ctx":     512,
    "num_predict": 800,
    "temperature": 0,
}


# ── FastAPI ───────────────────────────────────────────────────────────────
API_TITLE   = "Adala · API القانونية لوزارة العدل"
API_VERSION = "1.0.0"
API_HOST    = "0.0.0.0"
API_PORT    = 8000

# ── Streamlit ─────────────────────────────────────────────────────────────
API_BASE_URL = "http://localhost:8000"   # URL que le frontend Streamlit appelle
