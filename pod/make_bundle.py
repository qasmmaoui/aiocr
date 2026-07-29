# -*- coding: utf-8 -*-
"""Prépare le paquet du «jour de retraitement» (pod GPU).

Rassemble ce que le pod doit recevoir :
  - les 3 files d'attente OCR (arrêts scannés, PMP, lois à couche texte malade)
  - les PDF correspondants (résolus sur Z:/Y:)
  - golden_set.json + scripts pod_run.py
Écrit un manifeste (tailles, comptes) et, avec --tar, l'archive à téléverser.

    python pod/make_bundle.py           # manifeste seul (vérification)
    python pod/make_bundle.py --tar     # + archive pod_bundle.tar
"""
import argparse
import json
import os
import sys
import tarfile

DATA = r"Y:\adala-project\aiocr_data"
OUT_DIR = r"Y:\adala-project\pod_bundle"
QUEUES = {
    "juris": (os.path.join(DATA, "juris_ocr_backlog.txt"),
              [r"Z:\jurisprudence", r"Y:\adala-project\juris"]),
    "laws_sick": (os.path.join(DATA, "laws_reocr_backlog.txt"),
                  [r"Y:\adala-project\laws"]),
}
PMP_STAGING = r"Y:\adala-project\laws\incoming"
EXTRA = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "pod_run.py"),
         os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "pipeline", "golden_set.json")]


def resolve(rel: str, roots: list[str]) -> str | None:
    rel = rel.split("\t")[0].strip()
    for root in roots:
        # les backlogs stockent des chemins relatifs ou de simples noms
        for cand in (os.path.join(root, rel), *(
                os.path.join(dp, os.path.basename(rel))
                for dp, _dn, fn in os.walk(root)
                if os.path.basename(rel) in fn)):
            if os.path.exists(cand):
                return cand
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tar", action="store_true")
    a = ap.parse_args()

    manifest = {"queues": {}, "missing": {}, "total_files": 0, "total_mb": 0.0}
    resolved: dict[str, list[str]] = {}

    for name, (backlog, roots) in QUEUES.items():
        if not os.path.exists(backlog):
            print(f"! file d'attente absente: {backlog}")
            continue
        entries = [l for l in open(backlog, encoding="utf-8") if l.strip()]
        found, missing = [], []
        # index une seule fois par racine pour éviter os.walk répété
        idx = {}
        for root in roots:
            if os.path.isdir(root):
                for dp, _dn, fn in os.walk(root):
                    for f in fn:
                        idx.setdefault(f, os.path.join(dp, f))
        for e in entries:
            rel = e.split("\t")[0].strip()
            p = idx.get(os.path.basename(rel))
            (found if p else missing).append(p or rel)
        resolved[name] = found
        mb = sum(os.path.getsize(p) for p in found) / 2**20
        manifest["queues"][name] = {"listed": len(entries), "found": len(found),
                                    "missing": len(missing), "mb": round(mb, 1)}
        manifest["missing"][name] = missing[:20]
        manifest["total_files"] += len(found)
        manifest["total_mb"] += mb

    if os.path.isdir(PMP_STAGING):
        pmp = [os.path.join(PMP_STAGING, f) for f in os.listdir(PMP_STAGING)
               if f.lower().endswith(".pdf")]
        resolved["pmp"] = pmp
        mb = sum(os.path.getsize(p) for p in pmp) / 2**20
        manifest["queues"]["pmp"] = {"listed": len(pmp), "found": len(pmp),
                                     "missing": 0, "mb": round(mb, 1)}
        manifest["total_files"] += len(pmp)
        manifest["total_mb"] += mb

    manifest["total_mb"] = round(manifest["total_mb"], 1)
    os.makedirs(OUT_DIR, exist_ok=True)
    mpath = os.path.join(OUT_DIR, "manifest.json")
    json.dump(manifest, open(mpath, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(manifest["queues"], ensure_ascii=False, indent=1))
    print(f"total: {manifest['total_files']} fichiers, "
          f"{manifest['total_mb']:,.0f} Mo -> {mpath}")

    if a.tar:
        tpath = os.path.join(OUT_DIR, "pod_bundle.tar")
        with tarfile.open(tpath, "w") as t:
            for name, paths in resolved.items():
                for p in paths:
                    t.add(p, arcname=f"input/{name}/{os.path.basename(p)}")
            for p in EXTRA:
                if os.path.exists(p):
                    t.add(p, arcname=os.path.basename(p))
            t.add(mpath, arcname="manifest.json")
        print(f"archive: {tpath} ({os.path.getsize(tpath)/2**30:.2f} Go)")


if __name__ == "__main__":
    main()
