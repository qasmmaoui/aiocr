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
import os
from typing import Callable

from ollama import Client as OllamaClient

from core.config import OLLAMA_BASE_URL, LLM_OPTIONS
from core.utils import get_vision_model
from services.correction_service import correct_text, light_clean


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
        import os
        import pytesseract
        from PIL import Image
        import io

        # Windows : chemin explicite si l'exécutable existe.
        # Linux / Docker : tesseract est dans le PATH, ne rien forcer.
        _win_tess = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        _env_tess = os.environ.get("TESSERACT_CMD")
        if _env_tess:
            pytesseract.pytesseract.tesseract_cmd = _env_tess
        elif os.path.exists(_win_tess):
            pytesseract.pytesseract.tesseract_cmd = _win_tess

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
    model = os.environ.get("OCR_MODEL") or get_vision_model()
    prompt = (
        "أنت نظام OCR دقيق جداً. انسخ حرفياً كل النص العربي الظاهر في هذه الصورة "
        "كما هو تماماً، سطراً بسطر، من اليمين إلى اليسار. "
        "حافظ على الأرقام وعلامات الترقيم وفواصل الأسطر. "
        "لا تُضف أي تعليق أو شرح أو ترجمة، وأخرِج النص فقط."
    )
    try:
        response = _get_client().generate(
            model=model,
            prompt=prompt,
            images=[image_b64],
            options=LLM_OPTIONS,
            stream=False,
        )
        raw = response.get("response", "").strip()
        # Sortie du modèle vision déjà propre : nettoyage léger seulement.
        return light_clean(raw)
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

    # Modèle vision (Qwen2.5-VL) en priorité : bien plus précis que Tesseract
    # pour l'arabe. Tesseract sert uniquement de secours si Ollama échoue.
    result = ocr_ollama_vision(image_b64)

    if result is None or result.startswith("[ERR"):
        result = ocr_tesseract(image_b64)

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
