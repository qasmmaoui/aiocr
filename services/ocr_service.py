"""
╔══════════════════════════════════════════════════════════════╗
║  DMSI · Adala — Service OCR                                  ║
║  services/ocr_service.py                                     ║
╚══════════════════════════════════════════════════════════════╝
Description :
    OCR via Tesseract (ara+fra) avec fallback sur Ollama Vision.
    Applique la correction de texte après chaque extraction.
"""

import base64
from typing import Callable

from ollama import Client as OllamaClient

from core.config import OLLAMA_BASE_URL, LLM_OPTIONS
from core.utils import get_vision_model
from services.correction_service import correct_text


# ── Client Ollama (singleton) ─────────────────────────────────────────────
_ollama_client: OllamaClient | None = None

def _get_client() -> OllamaClient:
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient(host=OLLAMA_BASE_URL)
    return _ollama_client


# ── Tesseract ─────────────────────────────────────────────────────────────
def ocr_tesseract(image_b64: str) -> str | None:
    """
    Tente l'OCR via Tesseract.
    Retourne le texte corrigé, ou None si Tesseract n'est pas installé.
    """
    try:
        import pytesseract
        from PIL import Image
        import io

        pytesseract.pytesseract.tesseract_cmd = (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
        img_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_bytes))
        raw = pytesseract.image_to_string(img, lang="ara+fra", config="--psm 6 --oem 3")
        corrected, _ = correct_text(raw.strip())
        return corrected
    except ImportError:
        return None
    except Exception as e:
        return f"[ERR Tesseract: {e}]"


# ── Ollama Vision ─────────────────────────────────────────────────────────
def ocr_ollama_vision(image_b64: str) -> str:
    """
    Utilise un modèle vision Ollama pour extraire le texte d'une image.
    """
    model = get_vision_model()
    try:
        response = _get_client().generate(
            model=model,
            prompt="انسخ كل النص في هذه الصورة سطراً بسطر.",
            images=[image_b64],
            options=LLM_OPTIONS,
            stream=False,
        )
        raw = response.get("response", "").strip()
        corrected, _ = correct_text(raw)
        return corrected
    except Exception as e:
        return f"[ERR Ollama Vision: {e}]"


# ── Stratégie principale ──────────────────────────────────────────────────
def run_ocr_on_page(page: dict) -> str:
    """
    Applique Tesseract d'abord, puis Ollama Vision en fallback.

    Args:
        page: dict avec les clés 'num', 'type', 'image_b64'

    Returns:
        Texte extrait et corrigé.
    """
    image_b64 = page.get("image_b64", "")
    result = ocr_tesseract(image_b64)

    # Si Tesseract échoue ou retourne une erreur, on bascule sur Ollama
    if result is None or result.startswith("[ERR"):
        result = ocr_ollama_vision(image_b64)

    if result and not result.startswith("[ERR"):
        result, _ = correct_text(result)

    return result or ""


def run_ocr_on_pages(
    pages: list[dict],
    progress_callback: Callable[[float, str], None] | None = None,
) -> int:
    """
    Lance l'OCR sur toutes les pages de type 'scan'.

    Args:
        pages:             Liste de dicts de pages.
        progress_callback: Fonction optionnelle (ratio, message) pour la progression.

    Returns:
        Nombre de pages traitées.
    """
    scan_pages = [p for p in pages if p.get("type") == "scan"]
    total = len(scan_pages)

    for i, page in enumerate(scan_pages):
        if progress_callback:
            progress_callback(
                (i + 1) / total,
                f"📷 OCR page {page['num']} ({i+1}/{total})",
            )
        page["text"] = run_ocr_on_page(page)

    if progress_callback and total:
        progress_callback(1.0, f"✅ {total} page(s) traitée(s)")

    return total
