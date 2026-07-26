# -*- coding: utf-8 -*-
"""Nettoyage des doublons INTERNES à une collection (même contenu, deux
fichiers). Jamais de suppression : les doublons partent en quarantaine
(Z:\\rimlex_quarantine\\) avec un rapport, et le registre est mis à jour.
Le survivant est le fichier au nom le plus informatif (le plus long).
Les doublons INTER-collections (laws<->adala) sont voulus et non touchés.
"""
import json
import os
import shutil
from collections import defaultdict

BASE = r"Y:\adala-project"
ROOTS = {"laws": os.path.join(BASE, "laws"),
         "adala": os.path.join(BASE, "adala_pdfs"),
         "juris": r"Z:\jurisprudence"}
REGISTRY = os.path.join(BASE, "aiocr_data", "registry.json")
QUAR = r"Z:\rimlex_quarantine"
REPORT = os.path.join(BASE, "aiocr_data", "dedup_clean_report.json")


def main() -> None:
    reg = json.load(open(REGISTRY, encoding="utf-8"))
    groups = defaultdict(list)            # (collection, fp) -> [relpath]
    for rel, d in reg["docs"].items():
        if d.get("text_fp"):
            groups[(d["collection"], d["text_fp"])].append(rel)

    moved, missing, report = 0, 0, []
    for (coll, _fp), rels in groups.items():
        if len(rels) < 2:
            continue
        rels = sorted(rels, key=lambda r: -len(os.path.basename(r)))
        keeper, dupes = rels[0], rels[1:]
        for rel in dupes:
            sub = rel.split(os.sep, 1)[1] if os.sep in rel else rel
            src = os.path.join(ROOTS[coll], sub)
            if not os.path.exists(src):
                missing += 1
                continue
            dst = os.path.join(QUAR, coll, os.path.basename(rel))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst):
                stem, ext = os.path.splitext(dst)
                dst = f"{stem}_{moved}{ext}"
            shutil.move(src, dst)
            reg["docs"].pop(rel, None)
            report.append({"kept": keeper, "quarantined": rel, "moved_to": dst})
            moved += 1

    json.dump(reg, open(REGISTRY, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(report, open(REPORT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"doublons internes mis en quarantaine: {moved} "
          f"(introuvables: {missing}) -> {QUAR}")
    print(f"rapport: {REPORT} — restauration = redéplacer le fichier et "
          f"relancer 'registre complet'.")


if __name__ == "__main__":
    main()
