# -*- coding: utf-8 -*-
"""Visualiseur de source pour le corpus v4 (page PDF + surlignage jaune).

Le visualiseur existant (`api/viewer.py`) résout un chunk via un index local
construit pour l'ancien corpus. Les chunks v4 portent désormais eux-mêmes tout
le nécessaire dans leur payload Qdrant — chemin PDF relatif, page, texte — donc
ces routes travaillent directement à partir de ces valeurs, sans index.

  GET /api/src/page.png?pdf=<rel>&page=N[&highlight=<texte>][&dpi=130]
  GET /api/src/pdf?pdf=<rel>                 -> le PDF original
  GET /api/src/info?pdf=<rel>                -> nb de pages, titre
"""
from __future__ import annotations

import os

import fitz
from fastapi import APIRouter, HTTPException, Query, Response

router = APIRouter(prefix="/api/src", tags=["source"])

# Racines autorisées : tout chemin doit rester à l'intérieur (anti-traversal).
PDF_BASE = os.environ.get("PDF_BASE", "/workspace")
ALLOWED_PREFIXES = ("rework/input/", "laws/", "adala_pdfs/")


def _safe_path(rel: str) -> str:
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel.lower().endswith(".pdf"):
        raise HTTPException(400, "Chemin PDF invalide.")
    if not any(rel.startswith(p) for p in ALLOWED_PREFIXES):
        raise HTTPException(403, "Chemin hors des racines autorisées.")
    full = os.path.normpath(os.path.join(PDF_BASE, rel))
    if not full.startswith(os.path.normpath(PDF_BASE) + os.sep):
        raise HTTPException(403, "Chemin hors des racines autorisées.")
    if not os.path.exists(full):
        raise HTTPException(404, "PDF introuvable sur le volume.")
    return full


def _rects_for(pg, text: str) -> list:
    """Rectangles du passage sur la page. Recherche par segments : assez longs
    pour rester uniques, assez courts pour survivre aux écarts OCR / couche
    texte (le texte indexé provient de notre extraction, pas du PDF)."""
    rects = []
    for line in (text or "").splitlines():
        seg = " ".join(line.split()).strip()
        if len(seg) < 12:
            continue
        for i in range(0, len(seg), 40):
            piece = seg[i:i + 40]
            if len(piece) >= 12:
                try:
                    rects += pg.search_for(piece)
                except Exception:
                    pass
    return rects


@router.get("/info")
def info(pdf: str = Query(...)):
    path = _safe_path(pdf)
    doc = fitz.open(path)
    try:
        return {"pdf": pdf, "npages": len(doc),
                "title": os.path.splitext(os.path.basename(path))[0]}
    finally:
        doc.close()


@router.get("/page.png")
def page_png(pdf: str = Query(...), page: int = Query(1, ge=1),
             highlight: str | None = Query(None), dpi: int = Query(130, ge=60, le=300)):
    """Rend une page en PNG, passage surligné en jaune si `highlight` est fourni."""
    path = _safe_path(pdf)
    doc = fitz.open(path)
    try:
        if page > len(doc):
            raise HTTPException(404, f"Page {page} > {len(doc)} pages.")
        pg = doc[page - 1]
        n_hits = 0
        if highlight:
            for r in _rects_for(pg, highlight):
                pg.draw_rect(r, fill=(1, 0.9, 0.2), fill_opacity=0.35, width=0)
                n_hits += 1
        png = pg.get_pixmap(dpi=dpi).tobytes("png")
    finally:
        doc.close()
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400",
                             "X-Highlight-Rects": str(n_hits)})


@router.get("/pdf")
def raw_pdf(pdf: str = Query(...)):
    path = _safe_path(pdf)
    with open(path, "rb") as f:
        data = f.read()
    name = os.path.basename(path)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}"',
                             "Cache-Control": "public, max-age=86400"})
