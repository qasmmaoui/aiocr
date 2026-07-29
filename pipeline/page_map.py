# -*- coding: utf-8 -*-
"""Map each corpus chunk to its PDF page.

Text-native PDFs: fuzzy char-3gram match chunk vs page text (page_src='match').
Scanned PDFs (no usable text layer): linear estimate from chunk order (page_src='est').
Writes laws_corpus_paged.jsonl next to the input corpus.
"""
import json
import os
import re
import glob
from collections import defaultdict

import fitz

CORPUS = r"Y:\adala-project\aiocr_data\laws_corpus.jsonl"
LAWS_DIR = r"Y:\adala-project\laws"
OUT = r"Y:\adala-project\aiocr_data\laws_corpus_paged.jsonl"

AR_DIAC = re.compile(r"[ً-ٰٟـ]")

def norm(s: str) -> str:
    s = AR_DIAC.sub("", s)
    # unify alef/hamza/ya forms; lam-alef ligature artifacts from OCR ("األ" etc.)
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ٱ", "ا").replace("ى", "ي").replace("ة", "ه")
           .replace("ؤ", "و").replace("ئ", "ي"))
    return re.sub(r"[^؀-ۿ0-9]", "", s)

def grams(s: str, n: int = 3) -> set:
    return {s[i:i + n] for i in range(len(s) - n + 1)}

def main() -> None:
    pdf_index = {}
    for p in glob.glob(os.path.join(LAWS_DIR, "**", "*.pdf"), recursive=True):
        pdf_index[os.path.basename(p)] = p

    chunks = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
    by_file = defaultdict(list)
    for c in chunks:
        by_file[c["file"]].append(c)

    stats = {"match": 0, "est": 0, "nofile": 0}
    for fname, recs in by_file.items():
        recs.sort(key=lambda r: int(r["chunk"]))
        path = pdf_index.get(fname)
        if not path:
            for r in recs:
                r["page"], r["page_src"] = None, "nofile"
            stats["nofile"] += len(recs)
            continue
        try:
            doc = fitz.open(path)
            pages = [norm(pg.get_text()) for pg in doc]
            npages = len(pages)
            doc.close()
        except Exception:
            pages, npages = [], 0
        total_text = sum(len(p) for p in pages)
        text_native = npages > 0 and total_text / max(npages, 1) > 150
        if text_native:
            page_grams = [grams(p) for p in pages]
            for r in recs:
                g = grams(norm(r["text"]))
                best, best_score = None, 0.0
                for i, pg in enumerate(page_grams):
                    if not g or not pg:
                        continue
                    score = len(g & pg) / len(g)
                    if score > best_score:
                        best, best_score = i, score
                if best is not None and best_score >= 0.35:
                    r["page"], r["page_src"] = best + 1, "match"
                    stats["match"] += 1
                else:
                    r["page"], r["page_src"] = _est(r, recs, npages), "est"
                    stats["est"] += 1
        else:
            for r in recs:
                r["page"], r["page_src"] = _est(r, recs, npages), "est"
                stats["est"] += 1

    with open(OUT, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print("done:", stats, "->", OUT)

def _est(r, recs, npages: int):
    if npages <= 0:
        return 1
    idx = int(r["chunk"])
    hi = max(int(x["chunk"]) for x in recs) or 1
    return 1 + round(idx / hi * (npages - 1))

if __name__ == "__main__":
    main()
