# -*- coding: utf-8 -*-
"""Construit l'index de pages de la visionneuse À PARTIR DE QDRANT (côté pod).

La visionneuse a besoin, pour chaque chunk servi : sa page dans le PDF et son
texte (afin de le retrouver sur la page et le surligner). Ce fichier était
produit sur le PC, mais les numéros de chunks du pod viennent d'une autre
ingestion — d'où l'absence de surlignage. On le régénère donc à la source.

    python pod/build_page_index.py                       # collections servies
    python pod/build_page_index.py --collections laws_penal_ocr
"""
import argparse
import glob
import json
import os
import re
import sys

import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rag import store  # noqa: E402

DATA = os.environ.get("RIMLEX_DATA_DIR", "/workspace/data")
LAWS = os.environ.get("RIMLEX_LAWS_DIR", "/workspace/laws")
OUT = os.path.join(DATA, "laws_corpus_v2.jsonl")

AR_DIAC = re.compile(r"[ً-ٰٟـ]")


def norm(s: str) -> str:
    s = AR_DIAC.sub("", s or "")
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ٱ", "ا").replace("ى", "ي").replace("ة", "ه")
           .replace("ؤ", "و").replace("ئ", "ي"))
    return re.sub(r"[^؀-ۿ0-9]", "", s)


def grams(s: str, n: int = 3) -> set:
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def pdf_index() -> dict:
    return {os.path.basename(p): p
            for p in glob.glob(os.path.join(LAWS, "**", "*.pdf"), recursive=True)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collections", nargs="*",
                    default=["laws_penal", "laws_commercial"])
    a = ap.parse_args()

    pdfs = pdf_index()
    print(f"{len(pdfs)} PDF disponibles sous {LAWS}", flush=True)

    rows = []
    c = store.client()
    existing = {x.name for x in c.get_collections().collections}
    for col in a.collections:
        if col not in existing:
            print(f"  ! collection absente : {col}")
            continue
        offset, n = None, 0
        while True:
            pts, offset = c.scroll(col, limit=512, offset=offset,
                                   with_payload=True, with_vectors=False)
            for p in pts:
                pl = p.payload or {}
                rows.append({"collection": col, "file": pl.get("file", ""),
                             "chunk": pl.get("chunk"), "law": pl.get("law", ""),
                             "article": pl.get("article"),
                             "text": pl.get("text", "")})
            n += len(pts)
            if offset is None:
                break
        print(f"  {col} : {n} chunks", flush=True)

    # regroupement par fichier : on n'ouvre chaque PDF qu'une fois
    by_file = {}
    for r in rows:
        by_file.setdefault(r["file"], []).append(r)

    matched = est = nofile = 0
    for i, (fname, recs) in enumerate(by_file.items(), 1):
        path = pdfs.get(os.path.basename(fname))
        recs.sort(key=lambda r: int(r["chunk"]) if str(r["chunk"]).isdigit() else 0)
        if not path:
            for r in recs:
                r["page"], r["page_src"] = None, "nofile"
            nofile += len(recs)
            continue
        try:
            doc = fitz.open(path)
            pages = [norm(pg.get_text()) for pg in doc]
            npages = len(doc)
            doc.close()
        except Exception:
            pages, npages = [], 0
        page_grams = [grams(p) for p in pages]
        hi = max((int(r["chunk"]) for r in recs
                  if str(r["chunk"]).isdigit()), default=0) or 1
        for r in recs:
            g = grams(norm(r["text"]))
            best, score = None, 0.0
            for k, pg in enumerate(page_grams):
                if not g or not pg:
                    continue
                s = len(g & pg) / len(g)
                if s > score:
                    best, score = k, s
            if best is not None and score >= 0.35:
                r["page"], r["page_src"] = best + 1, "match"
                matched += 1
            else:                       # scan sans couche texte : estimation
                idx = int(r["chunk"]) if str(r["chunk"]).isdigit() else 0
                r["page"] = 1 + round(idx / hi * (npages - 1)) if npages else 1
                r["page_src"] = "est"
                est += 1
        if i % 50 == 0:
            print(f"  {i}/{len(by_file)} documents traités", flush=True)

    os.makedirs(DATA, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            r.setdefault("status", "current")
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n{len(rows)} chunks -> {OUT}")
    print(f"  page exacte : {matched} · estimée : {est} · sans PDF : {nofile}")
    print("Rechargez la visionneuse (redémarrage de l'API) pour l'activer.")


if __name__ == "__main__":
    main()
