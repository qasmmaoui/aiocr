# -*- coding: utf-8 -*-
"""Construit la liste des PDF qui entreront dans le corpus (une édition par loi).

Consomme editions_choisies.json (produit par select_best_edition.py) et écrit
corpus_input.txt : un chemin par ligne, la meilleure édition de chaque texte,
sans doublon. C'est CE fichier que le découpage/vectorisation doit lire —
sinon la sélection ne sert à rien.

Écrit aussi corpus_input_report.json : combien de textes par source, combien
d'éditions écartées, et les documents sans couche texte (file OCR).
"""
import json
import os
from collections import Counter

DATA = r"Y:\adala-project\aiocr_data"
CHOICES = os.path.join(DATA, "editions_choisies.json")
OUT = os.path.join(DATA, "corpus_input.txt")
REPORT = os.path.join(DATA, "corpus_input_report.json")
OCR_QUEUE = os.path.join(DATA, "laws_reocr_backlog.txt")


def main() -> None:
    if not os.path.exists(CHOICES):
        raise SystemExit("editions_choisies.json absent — lancez d'abord "
                         "pipeline/select_best_edition.py")
    choices = json.load(open(CHOICES, encoding="utf-8"))

    retenus, ecartes, par_source, a_ocriser = [], 0, Counter(), []
    for _cle, c in choices.items():
        p = c["retenu"]
        if not os.path.exists(p):
            continue
        retenus.append(p)
        par_source[c["source"]] += 1
        ecartes += len(c.get("ecartes", []))
        # une édition retenue mais sans articles détectés = probablement un scan
        if c.get("articles", 0) == 0:
            a_ocriser.append(p)

    retenus = sorted(set(retenus))
    with open(OUT, "w", encoding="utf-8") as f:
        for p in retenus:
            f.write(p + "\n")

    # file de re-OCR : on y ajoute les éditions retenues sans texte exploitable
    existing = set()
    if os.path.exists(OCR_QUEUE):
        existing = {l.split("\t")[0].strip()
                    for l in open(OCR_QUEUE, encoding="utf-8") if l.strip()}
    nouveaux = [p for p in a_ocriser if os.path.basename(p) not in existing]
    if nouveaux:
        with open(OCR_QUEUE, "a", encoding="utf-8") as f:
            for p in nouveaux:
                f.write(f"{os.path.basename(p)}\tsans-texte\n")

    report = {
        "textes_retenus": len(retenus),
        "editions_ecartees": ecartes,
        "par_source": dict(par_source),
        "sans_couche_texte": len(a_ocriser),
        "ajoutes_file_ocr": len(nouveaux),
    }
    json.dump(report, open(REPORT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"\nliste d'entrée du corpus : {OUT}")


if __name__ == "__main__":
    main()
