# -*- coding: utf-8 -*-
"""Paquet pénal pour la session GPU : lois pénales (meilleure édition) +
arrêts de la chambre criminelle + scripts + jeu d'évaluation.

Découpe en parties de ~1,8 Go (reprise possible, limites des hébergeurs) et
produit un fichier de sommes de contrôle pour vérifier l'intégrité côté pod.

    python pod/make_penal_bundle.py            # inventaire seul
    python pod/make_penal_bundle.py --build    # construit les archives
"""
import argparse
import hashlib
import json
import os
import tarfile

DATA = r"Y:\adala-project\aiocr_data"
OUT_DIR = r"Y:\adala-project\pod_bundle"
CORPUS = os.path.join(DATA, "laws_corpus_v2.jsonl")
CHOICES = os.path.join(DATA, "editions_choisies.json")
JURIS_PENAL = r"Z:\jurisprudence\الغرفة الجنائية"
PART_MAX = 1_800_000_000          # ~1,8 Go par partie


def penal_law_files() -> list[str]:
    """Lois pénales, dans l'édition retenue par select_best_edition."""
    wanted = {json.loads(l)["file"] for l in open(CORPUS, encoding="utf-8")
              if json.loads(l).get("collection") == "laws_penal"}
    choices = json.load(open(CHOICES, encoding="utf-8"))
    by_name = {os.path.basename(c["retenu"]): c["retenu"]
               for c in choices.values()}
    out, missing = [], []
    for name in sorted(wanted):
        p = by_name.get(name)
        if p and os.path.exists(p):
            out.append(p)
        else:
            # l'édition retenue porte un autre nom : on garde l'original
            for root in (r"Y:\adala-project\laws", r"Y:\adala-project\adala_pdfs",
                         r"Z:\PMP_Textes"):
                for dp, _dn, fn in os.walk(root):
                    if name in fn:
                        out.append(os.path.join(dp, name))
                        break
                else:
                    continue
                break
            else:
                missing.append(name)
    return sorted(set(out)), missing


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()

    laws, missing = penal_law_files()
    juris = [os.path.join(JURIS_PENAL, f) for f in os.listdir(JURIS_PENAL)
             if f.lower().endswith(".pdf")]
    scripts = []
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    for rel in ("pod/pod_run.py", "pipeline/golden_set.json",
                "pipeline/ocr_quality.py", "pipeline/rechunk_core.py",
                "pipeline/export_corpus.py"):
        p = os.path.join(repo, rel.replace("/", os.sep))
        if os.path.exists(p):
            scripts.append(p)

    def mb(paths):
        return sum(os.path.getsize(p) for p in paths) / 2**20

    print(f"lois pénales   : {len(laws):5d} fichiers · {mb(laws):8,.0f} Mo"
          + (f"  ({len(missing)} introuvables)" if missing else ""))
    print(f"arrêts pénaux  : {len(juris):5d} fichiers · {mb(juris):8,.0f} Mo")
    print(f"scripts        : {len(scripts):5d} fichiers")
    print(f"TOTAL          : {mb(laws + juris):8,.0f} Mo")
    if not a.build:
        print("\n(inventaire seul — relancez avec --build pour créer les archives)")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    items = ([("laws_penal", p) for p in laws]
             + [("juris_penal", p) for p in juris]
             + [("scripts", p) for p in scripts])

    part, size, tar, parts = 1, 0, None, []

    def open_part(n):
        path = os.path.join(OUT_DIR, f"penal_{n:02d}.tar")
        print(f"  → {os.path.basename(path)}", flush=True)
        return tarfile.open(path, "w"), path

    tar, path = open_part(part)
    for sub, p in items:
        sz = os.path.getsize(p)
        if size + sz > PART_MAX:
            tar.close()
            parts.append(path)
            part += 1
            size = 0
            tar, path = open_part(part)
        tar.add(p, arcname=f"{sub}/{os.path.basename(p)}")
        size += sz
    tar.close()
    parts.append(path)

    sums = os.path.join(OUT_DIR, "penal_sha256.txt")
    with open(sums, "w", encoding="utf-8") as f:
        for p in parts:
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for blk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(blk)
            f.write(f"{h.hexdigest()}  {os.path.basename(p)}\n")
            print(f"  {os.path.basename(p)} · "
                  f"{os.path.getsize(p)/2**30:.2f} Go · {h.hexdigest()[:16]}…")
    print(f"\n{len(parts)} partie(s) -> {OUT_DIR}")
    print(f"sommes de contrôle : {sums}")


if __name__ == "__main__":
    main()
