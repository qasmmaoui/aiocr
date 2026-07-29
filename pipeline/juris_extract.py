# -*- coding: utf-8 -*-
"""Extraction du texte des arrêts de la Cour de cassation (couche texte).

Les arrêts scannés (sans couche texte) sont listés dans un backlog pour la
future passe OCR (pod GPU). Sorties :
    juris_texts.jsonl       — {file, relpath, npages, text} par arrêt lisible
    juris_ocr_backlog.txt   — chemins relatifs des arrêts à OCRiser
"""
import glob
import json
import os

import fitz

JURIS_DIR = r"Z:\jurisprudence"     # collection canonique (20k+ arrêts)
TEXTS_OUT = r"Y:\adala-project\aiocr_data\juris_texts.jsonl"
BACKLOG_OUT = r"Y:\adala-project\aiocr_data\juris_ocr_backlog.txt"
MIN_CHARS_PER_PAGE = 150


def main() -> None:
    pdfs = glob.glob(os.path.join(JURIS_DIR, "**", "*.pdf"), recursive=True)
    n_text = n_scan = n_err = 0
    with open(TEXTS_OUT, "w", encoding="utf-8") as out, \
         open(BACKLOG_OUT, "w", encoding="utf-8") as backlog:
        for i, p in enumerate(pdfs):
            rel = os.path.relpath(p, JURIS_DIR)
            try:
                doc = fitz.open(p)
                pages = [pg.get_text() for pg in doc]
                doc.close()
            except Exception:
                n_err += 1
                continue
            chars = sum(len(t) for t in pages)
            if pages and chars / len(pages) >= MIN_CHARS_PER_PAGE:
                out.write(json.dumps(
                    {"file": os.path.basename(p), "relpath": rel,
                     "npages": len(pages), "text": "\n\f\n".join(pages)},
                    ensure_ascii=False) + "\n")
                n_text += 1
            else:
                backlog.write(rel + "\n")
                n_scan += 1
            if (i + 1) % 500 == 0:
                print(f"{i + 1}/{len(pdfs)} traités (texte={n_text}, scan={n_scan})",
                      flush=True)
    print(f"terminé: total={len(pdfs)} texte={n_text} scan(backlog OCR)={n_scan} "
          f"erreurs={n_err}")


if __name__ == "__main__":
    main()
