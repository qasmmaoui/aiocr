# -*- coding: utf-8 -*-
"""Paquet « toutes les lois, meilleure édition » pour le pod.

Lit corpus_input.txt (produit par build_corpus_input.py à partir de la
sélection PMP/adala/laws) et archive ces PDF — un seul exemplaire par loi,
celui retenu sur critères mesurés. Découpe en parties de ~1,8 Go.

    python pod/make_laws_bundle.py            # inventaire
    python pod/make_laws_bundle.py --build    # archives
"""
import argparse
import hashlib
import os
import tarfile

DATA = r"Y:\adala-project\aiocr_data"
INPUT_LIST = os.path.join(DATA, "corpus_input.txt")
OUT_DIR = r"Y:\adala-project\pod_bundle"
PART_MAX = 1_800_000_000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--tout", action="store_true",
                    help="envoyer TOUTES les copies, sans sélection d'édition")
    ap.add_argument("--exclude-penal", action="store_true",
                    help="ne pas ré-envoyer les lois pénales déjà sur le pod")
    a = ap.parse_args()

    if a.tout:
        # TOUT le corpus : chaque PDF de chaque collection, sans sélection.
        # Le tri des éditions se fera côté pod, on ne perd aucune source.
        import glob
        roots = [r"Y:\adala-project\laws", r"Y:\adala-project\adala_pdfs",
                 r"Z:\PMP_Textes"]
        seen, paths = set(), []
        for root in roots:
            for p in glob.glob(os.path.join(root, "**", "*.pdf"), recursive=True):
                key = (os.path.basename(p), os.path.getsize(p))
                if key not in seen:          # doublons stricts seulement
                    seen.add(key)
                    paths.append(p)
    else:
        paths = [l.strip() for l in open(INPUT_LIST, encoding="utf-8") if l.strip()]
    paths = [p for p in paths if os.path.exists(p)]
    if a.exclude_penal:
        import json
        corpus = os.path.join(DATA, "laws_corpus_v2.jsonl")
        penal = {json.loads(l)["file"] for l in open(corpus, encoding="utf-8")
                 if json.loads(l).get("collection") == "laws_penal"}
        paths = [p for p in paths if os.path.basename(p) not in penal]

    total = sum(os.path.getsize(p) / 2**20 for p in paths)
    print(f"{len(paths)} textes (meilleure édition) · {total:,.0f} Mo")
    if not a.build:
        print("(inventaire seul — relancez avec --build)")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    part, size, parts = 1, 0, []
    tar = tarfile.open(os.path.join(OUT_DIR, "laws_01.tar"), "w")
    current = os.path.join(OUT_DIR, "laws_01.tar")
    print(f"  → {os.path.basename(current)}", flush=True)
    for p in paths:
        sz = os.path.getsize(p)
        if size + sz > PART_MAX:
            tar.close()
            parts.append(current)
            part += 1
            size = 0
            current = os.path.join(OUT_DIR, f"laws_{part:02d}.tar")
            tar = tarfile.open(current, "w")
            print(f"  → {os.path.basename(current)}", flush=True)
        # un seul dossier plat : le nom de fichier identifie la loi
        tar.add(p, arcname=f"laws_all/{os.path.basename(p)}")
        size += sz
    tar.close()
    parts.append(current)

    sums = os.path.join(OUT_DIR, "laws_sha256.txt")
    with open(sums, "w", encoding="utf-8") as f:
        for p in parts:
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for blk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(blk)
            f.write(f"{h.hexdigest()}  {os.path.basename(p)}\n")
            print(f"  {os.path.basename(p)} · {os.path.getsize(p)/2**30:.2f} Go")
    print(f"\n{len(parts)} partie(s) -> {OUT_DIR}")


if __name__ == "__main__":
    main()
