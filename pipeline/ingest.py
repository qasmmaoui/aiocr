# -*- coding: utf-8 -*-
"""Guichet d'ingestion du corpus : registre + boîte d'entrée avec dédoublonnage.

    python pipeline/ingest.py init          construit le registre des collections
    python pipeline/ingest.py add [dossier] traite la boîte d'entrée (défaut: inbox)

Trois clés de détection par document :
  - sha1 des octets            -> re-téléchargement identique (doublon sûr)
  - empreinte du texte normalisé -> même contenu sous autre nom/date (doublon)
  - numéro officiel            -> même loi : version potentiellement nouvelle
                                  (PAS un doublon -> signalé pour arbitrage)
Rapport écrit dans aiocr_data/ingest_report.json à chaque passage.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import sys

import fitz

BASE = r"Y:\adala-project"
COLLECTIONS = {
    "laws": os.path.join(BASE, "laws"),
    "adala": os.path.join(BASE, "adala_pdfs"),
    "juris": os.path.join(BASE, "juris"),
}
INBOX = os.path.join(BASE, "inbox")
STAGING = os.path.join(BASE, "laws", "incoming")     # destination des nouveaux
REGISTRY = os.path.join(BASE, "aiocr_data", "registry.json")
REPORT = os.path.join(BASE, "aiocr_data", "ingest_report.json")
OCR_BACKLOG = os.path.join(BASE, "aiocr_data", "juris_ocr_backlog.txt")

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
AR_DIAC = re.compile(r"[ً-ٰٟـ]")
NUM = r"[0-9]{1,2}[./][0-9]{2}[./][0-9]{1,4}|[0-9]{1,3}[./][0-9]{2}"
LAW_REF = re.compile(r"(?:القانون|قانون|الظهير|المرسوم|القرار)\s+رقم\s*(" + NUM + r")")


def norm_text(s: str) -> str:
    s = AR_DIAC.sub("", s.translate(AR_DIGITS))
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ى", "ي").replace("ة", "ه"))
    return re.sub(r"\s+", "", s)


def probe(path: str) -> dict:
    """sha1 + empreinte texte (3 premières pages) + numéros officiels du bloc-titre."""
    sha1 = hashlib.sha1(open(path, "rb").read()).hexdigest()
    fp, nums, npages, has_text = None, [], 0, False
    try:
        doc = fitz.open(path)
        npages = len(doc)
        head_txt = "".join(pg.get_text() for pg in doc[:3])
        title_block = (doc[0].get_text() if npages else "").translate(AR_DIGITS)[:500]
        doc.close()
        t = norm_text(head_txt)
        has_text = len(t) > 300
        if has_text:
            fp = hashlib.sha1(t[:4000].encode("utf-8")).hexdigest()
        nums = sorted({m.group(1).replace("/", ".").strip(".")
                       for m in LAW_REF.finditer(title_block)})
    except Exception:
        pass
    return {"sha1": sha1, "text_fp": fp, "nums": nums,
            "npages": npages, "has_text": has_text}


def load_registry() -> dict:
    if os.path.exists(REGISTRY):
        return json.load(open(REGISTRY, encoding="utf-8"))
    return {"docs": {}}          # relpath -> {sha1, text_fp, nums, collection}


def indexes(reg: dict):
    by_sha, by_fp, by_num = {}, {}, {}
    for rel, d in reg["docs"].items():
        by_sha.setdefault(d["sha1"], rel)
        if d.get("text_fp"):
            by_fp.setdefault(d["text_fp"], rel)
        for n in d.get("nums", []):
            by_num.setdefault(n, []).append(rel)
    return by_sha, by_fp, by_num


def cmd_init() -> None:
    reg = {"docs": {}}
    for coll, root in COLLECTIONS.items():
        pdfs = glob.glob(os.path.join(root, "**", "*.pdf"), recursive=True)
        for i, p in enumerate(pdfs):
            rel = os.path.join(coll, os.path.relpath(p, root))
            info = probe(p)
            info["collection"] = coll
            reg["docs"][rel] = info
            if (i + 1) % 500 == 0:
                print(f"{coll}: {i + 1}/{len(pdfs)}", flush=True)
        print(f"{coll}: {len(pdfs)} documents enregistrés", flush=True)
    json.dump(reg, open(REGISTRY, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"registre: {len(reg['docs'])} documents -> {REGISTRY}")


def cmd_add(folder: str) -> None:
    os.makedirs(STAGING, exist_ok=True)
    reg = load_registry()
    if not reg["docs"]:
        print("Registre vide — lancer d'abord: python pipeline/ingest.py init")
        sys.exit(1)
    by_sha, by_fp, by_num = indexes(reg)
    report = {"added": [], "duplicates": [], "new_versions": [], "needs_ocr": []}
    pdfs = glob.glob(os.path.join(folder, "**", "*.pdf"), recursive=True)
    for p in pdfs:
        base = os.path.basename(p)
        info = probe(p)
        if info["sha1"] in by_sha:
            report["duplicates"].append(
                {"file": base, "reason": "octets identiques", "same_as": by_sha[info["sha1"]]})
            continue
        if info["text_fp"] and info["text_fp"] in by_fp:
            report["duplicates"].append(
                {"file": base, "reason": "même contenu (empreinte texte)",
                 "same_as": by_fp[info["text_fp"]]})
            continue
        version_of = sorted({r for n in info["nums"] for r in by_num.get(n, [])})
        dest = os.path.join(STAGING, base)
        shutil.copy2(p, dest)
        rel = os.path.join("laws", "incoming", base)
        info["collection"] = "laws"
        reg["docs"][rel] = info
        by_sha[info["sha1"]] = rel
        if info["text_fp"]:
            by_fp[info["text_fp"]] = rel
        entry = {"file": base, "nums": info["nums"], "pages": info["npages"]}
        if version_of:
            entry["possible_version_of"] = version_of[:5]
            report["new_versions"].append(entry)
        else:
            report["added"].append(entry)
        if not info["has_text"]:
            report["needs_ocr"].append(base)
            with open(OCR_BACKLOG, "a", encoding="utf-8") as bl:
                bl.write(os.path.join("..", "laws", "incoming", base) + "\n")
    json.dump(reg, open(REGISTRY, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(report, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"traités: {len(pdfs)} | nouveaux: {len(report['added'])} "
          f"| versions potentielles: {len(report['new_versions'])} "
          f"| doublons ignorés: {len(report['duplicates'])} "
          f"| à OCRiser: {len(report['needs_ocr'])}")
    print(f"rapport: {REPORT}")
    if report["added"] or report["new_versions"]:
        print("Étapes suivantes: re-chunking des nouveaux textes puis "
              "page_map.py et version_graph.py (et ré-ingestion Qdrant).")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "add"
    if cmd == "init":
        cmd_init()
    else:
        folder = sys.argv[2] if len(sys.argv) > 2 else INBOX
        os.makedirs(folder, exist_ok=True)
        cmd_add(folder)
