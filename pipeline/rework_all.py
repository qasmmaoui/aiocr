# -*- coding: utf-8 -*-
"""Grand retraitement — à lancer quand la collecte de documents est terminée.

Enchaîne tout le pipeline local dans le bon ordre, s'arrête à la première
erreur, journalise chaque étape. Ce qui reste ensuite est UNIQUEMENT la part
GPU (OCR du backlog + ré-ingestion Qdrant) sur le pod.

    1. ingest (inbox)          — derniers documents déposés
    2. registry init           — re-fichage complet des 3 collections
    3. version_graph           — dédoublonnage + graphe d'amendements + corpus v2
    4. page_map                — rattachement chunk -> page
    5. juris_index             — fhrs de la jurisprudence (Excel à jour)
    6. juris_citations         — إحالات arrêt -> loi
    7. ocr_quality             — scores de qualité + pires 200
    8. golden_eval             — le score ne doit pas régresser
    9. backup                  — snapshot + GitHub + miroir
"""
import datetime as dt
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEPS = [
    ("ingest inbox", [sys.executable, "-X", "utf8", "pipeline/ingest.py", "add"]),
    ("registre complet", [sys.executable, "-X", "utf8", "pipeline/ingest.py", "init"]),
    ("meilleure édition par loi",
     [sys.executable, "-X", "utf8", "pipeline/select_best_edition.py"]),
    ("liste d'entrée du corpus",
     [sys.executable, "-X", "utf8", "pipeline/build_corpus_input.py"]),
    ("graphe de versions", [sys.executable, "-X", "utf8", "pipeline/version_graph.py"]),
    ("pages PDF", [sys.executable, "-X", "utf8", "pipeline/page_map.py"]),
    ("index jurisprudence", [sys.executable, "-X", "utf8", "pipeline/juris_index.py"]),
    ("citations arrêts→lois", [sys.executable, "-X", "utf8", "pipeline/juris_citations.py"]),
    ("qualité OCR", [sys.executable, "-X", "utf8", "pipeline/ocr_quality.py"]),
    ("évaluation golden", [sys.executable, "-X", "utf8", "pipeline/golden_eval.py"]),
    ("sauvegarde", [sys.executable, "-X", "utf8", "pipeline/backup.py", "--no-mirror"]),
]


def main() -> None:
    t0 = dt.datetime.now()
    print(f"=== GRAND RETRAITEMENT — {t0:%Y-%m-%d %H:%M} ===", flush=True)
    for i, (label, cmd) in enumerate(STEPS, 1):
        print(f"\n[{i}/{len(STEPS)}] {label} …", flush=True)
        r = subprocess.run(cmd, cwd=ROOT,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if r.returncode != 0:
            print(f"\nÉCHEC à l'étape «{label}» (code {r.returncode}) — "
                  f"pipeline arrêté, rien d'autre n'a été modifié.", flush=True)
            sys.exit(r.returncode)
    print(f"\n=== TERMINÉ en {(dt.datetime.now() - t0).seconds // 60} min — "
          f"reste la part GPU (pod) : OCR backlog + ré-ingestion Qdrant ===",
          flush=True)


if __name__ == "__main__":
    main()
