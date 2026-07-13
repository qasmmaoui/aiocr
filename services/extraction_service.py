"""
╔══════════════════════════════════════════════════════════════╗
║  DMSI · Adala — Service d'Extraction PDF                     ║
║  services/extraction_service.py                              ║
╚══════════════════════════════════════════════════════════════╝
Description :
    - Extraction native du texte (PyMuPDF / fitz)
    - Classification des pages : native / scan
    - Génération des aperçus (preview) et images haute résolution
    - Gestion du cache JSON (par hash MD5 du PDF)
"""

import base64
import json
import re
from pathlib import Path

import fitz  # PyMuPDF

from core.config import DIR_CACHE, DIR_UPLOAD
from core.utils import pdf_hash
from services.correction_service import correct_text, light_clean


# ─────────────────────────────────────────────────────────────────────────
#  Cache
# ─────────────────────────────────────────────────────────────────────────

def _cache_path(file_hash: str) -> Path:
    return DIR_CACHE / f"{file_hash}.json"


def load_cache(file_hash: str) -> dict | None:
    """
    Charge les données depuis le cache si elles existent.

    Returns:
        dict avec les clés 'pages','doc_type','nb_pages','n_native','n_scan',
        ou None si absent / corrompu.
    """
    p = _cache_path(file_hash)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


def save_cache(file_hash: str, data: dict) -> None:
    """Sauvegarde les métadonnées d'extraction dans le cache JSON."""
    try:
        _cache_path(file_hash).write_text(
            json.dumps(
                {
                    "pages": [
                        {"num": p["num"], "type": p["type"], "text": p["text"]}
                        for p in data["pages"]
                    ],
                    "doc_type": data["doc_type"],
                    "nb_pages": data["nb_pages"],
                    "n_native": data["n_native"],
                    "n_scan":   data["n_scan"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "utf-8",
        )
    except Exception:
        pass


def merge_cache_into_pages(pages: list[dict], cached_data: dict) -> None:
    """
    Injecte les textes du cache dans la liste de pages courante
    (les images ont déjà été regénérées, on écrase seulement le texte).
    """
    cached_map = {str(p["num"]): p["text"] for p in cached_data.get("pages", [])}
    for page in pages:
        key = str(page["num"])
        if key in cached_map:
            page["text"] = cached_map[key]


# ─────────────────────────────────────────────────────────────────────────
#  Extraction principale
# ─────────────────────────────────────────────────────────────────────────

def _classify_page(raw_text: str) -> str:
    """Retourne 'native' si le texte est suffisamment riche, sinon 'scan'."""
    cleaned = re.sub(r"\s+", "", raw_text).strip()
    return "native" if len(cleaned) > 50 else "scan"


def extract_pdf(pdf_bytes: bytes) -> dict:
    """
    Extrait toutes les pages d'un PDF.

    Returns:
        {
            "pages":    [{"num", "type", "text", "image_b64", "preview"}, …],
            "doc_type": "native" | "scan" | "mixed",
            "nb_pages": int,
            "n_native": int,
            "n_scan":   int,
        }
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: list[dict] = []

    for page in doc:
        raw = page.get_text()
        page_type = _classify_page(raw)
        # Texte natif : nettoyage léger uniquement (les heuristiques OCR
        # corrompraient un texte déjà correct). L'OCR se fait plus tard.
        corrected = light_clean(raw.strip())

        # Aperçu basse résolution (pour l'UI)
        preview_pix = page.get_pixmap(
            matrix=fitz.Matrix(0.6, 0.6),
            colorspace=fitz.csRGB,
            alpha=False,
        )
        # Image haute résolution (300 DPI) — uniquement pour les pages 'scan'
        # (les pages natives n'ont pas besoin d'OCR : on évite un rendu coûteux)
        image_b64 = ""
        if page_type == "scan":
            ocr_pix = page.get_pixmap(
                dpi=300,
                colorspace=fitz.csGRAY,
                alpha=False,
            )
            image_b64 = base64.b64encode(ocr_pix.tobytes("png")).decode()

        pages.append(
            {
                "num":       page.number + 1,
                "type":      page_type,
                "text":      corrected,
                "image_b64": image_b64,
                "preview":   preview_pix.tobytes("png"),
            }
        )

    n_native = sum(1 for p in pages if p["type"] == "native")
    n_scan   = len(pages) - n_native

    if n_native == 0:
        doc_type = "scan"
    elif n_scan == 0:
        doc_type = "native"
    else:
        doc_type = "mixed"

    return {
        "pages":    pages,
        "doc_type": doc_type,
        "nb_pages": len(pages),
        "n_native": n_native,
        "n_scan":   n_scan,
    }


# ─────────────────────────────────────────────────────────────────────────
#  Sauvegarde fichier
# ─────────────────────────────────────────────────────────────────────────

def save_uploaded_pdf(filename: str, content: bytes) -> Path:
    """Enregistre le PDF uploadé dans DIR_UPLOAD et retourne son chemin."""
    dest = DIR_UPLOAD / filename
    dest.write_bytes(content)
    return dest


def get_pdf_path(filename: str) -> Path | None:
    """Retourne le chemin du PDF s'il existe dans DIR_UPLOAD."""
    p = DIR_UPLOAD / filename
    return p if p.exists() else None


def export_pages_as_text(pages: list[dict]) -> str:
    """Génère un fichier texte avec le contenu de chaque page."""
    return "\n\n".join(
        f"=== صفحة {p['num']} ===\n{p['text']}" for p in pages
    )
