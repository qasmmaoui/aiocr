# -*- coding: utf-8 -*-
"""Audit qualité OCR du corpus de lois : un score par chunk, revue ciblée.

Signaux (0..1, pondérés) :
  - ratio de caractères arabes/utiles vs bruit
  - ratio de «mots» plausibles (2+ lettres arabes)
  - séquences suspectes (points/pointillés répétés, caractères isolés)
Sorties :
  - ocr_quality.json      score par (file, chunk)
  - ocr_review_worst.csv  les 200 pires, avec lien visionneuse (revue humaine)
"""
import csv
import json
import re
from urllib.parse import quote

CORPUS = r"Y:\adala-project\aiocr_data\laws_corpus_v2.jsonl"
OUT_J = r"Y:\adala-project\aiocr_data\ocr_quality.json"
OUT_C = r"Y:\adala-project\aiocr_data\ocr_review_worst.csv"
VIEWER = "http://localhost:8000/api/viewer"

AR = re.compile(r"[؀-ۿ]")
AR_WORD = re.compile(r"[؀-ۿ]{2,}")
DOTS = re.compile(r"[.…]{4,}|[-_]{4,}")
LONE = re.compile(r"(?:\s[؀-ۿ]\s){3,}")
# artefact de ligature lam-alef de la couche texte PDF : «أعاله», «األولى»,
# «امللف»… — signature d'un document à re-OCRiser sur le pod
LIGATURE_BUG = re.compile(r"(?<![؀-ۿ])[وفبلك]?ا[أإآبتثجحخدذرزسشصضطظعغفقمنهي]ل[؀-ۿ]")


def score(text: str) -> float:
    t = text or ""
    if len(t) < 20:
        return 0.0
    n = len(t)
    ar_ratio = len(AR.findall(t)) / n
    words = AR_WORD.findall(t)
    word_chars = sum(len(w) for w in words)
    word_ratio = word_chars / max(1, len(AR.findall(t)))
    dots_pen = min(0.5, sum(len(m) for m in DOTS.findall(t)) / n * 4)
    lone_pen = 0.2 if LONE.search(t) else 0.0
    s = 0.45 * min(1.0, ar_ratio * 1.6) + 0.55 * word_ratio - dots_pen - lone_pen
    return round(max(0.0, min(1.0, s)), 3)


def main() -> None:
    from collections import defaultdict
    scores, rows = {}, []
    lig_by_file = defaultdict(int)
    words_by_file = defaultdict(int)
    with open(CORPUS, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            t = r.get("text", "")
            s = score(t)
            scores[f"{r['file']}#{r['chunk']}"] = s
            rows.append((s, r))
            lig_by_file[r["file"]] += len(LIGATURE_BUG.findall(t))
            words_by_file[r["file"]] += len(AR_WORD.findall(t))
    json.dump(scores, open(OUT_J, "w", encoding="utf-8"), ensure_ascii=False)

    # documents dont la couche texte est malade -> file d'attente re-OCR (pod)
    reocr = sorted(
        (f for f in lig_by_file
         if words_by_file[f] > 200
         and lig_by_file[f] / words_by_file[f] > 0.02),
        key=lambda f: -lig_by_file[f] / max(1, words_by_file[f]))
    reocr_path = OUT_J.replace("ocr_quality.json", "laws_reocr_backlog.txt")
    with open(reocr_path, "w", encoding="utf-8") as f:
        for name in reocr:
            f.write(f"{name}\t{lig_by_file[name]}/{words_by_file[name]}\n")
    print(f"couche texte malade (artefacts lam-alef >2% des mots): "
          f"{len(reocr)} documents -> {reocr_path}")

    rows.sort(key=lambda x: x[0])
    with open(OUT_C, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["score", "law", "file", "chunk", "page", "excerpt", "viewer_url"])
        for s, r in rows[:200]:
            w.writerow([s, r.get("law", "")[:60], r["file"], r["chunk"],
                        r.get("page", ""), (r.get("text") or "")[:120].replace("\n", " "),
                        f"{VIEWER}?file={quote(r['file'])}&chunk={r['chunk']}"])

    vals = sorted(scores.values())
    n = len(vals)
    med = vals[n // 2]
    bad = sum(1 for v in vals if v < 0.5)
    ok = sum(1 for v in vals if v >= 0.75)
    print(f"{n} chunks notés — médiane {med:.2f} | ≥0.75 (bon): {ok} "
          f"({100*ok//n}%) | <0.50 (à revoir): {bad} ({100*bad//n}%)")
    print(f"revue humaine: {OUT_C} (200 pires, liens visionneuse)")


if __name__ == "__main__":
    main()
