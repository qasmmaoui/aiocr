# -*- coding: utf-8 -*-
"""Fusionne Z:\adala_pdfs dans Y:\adala-project\adala_pdfs (union des deux copies).

Récupère aussi _catalog/ et _adala_index.json (perdus sur C: lors de l'incident
Storage Sense, retrouvés sur Z:). Dédoublonnage par sha1 puis empreinte texte,
contre le registre ET les fichiers déjà copiés. Le registre est mis à jour.
"""
import hashlib
import json
import os
import re
import shutil
import unicodedata

import fitz

SRC = r"Z:\adala_pdfs"
DST = r"Y:\adala-project\adala_pdfs"
REGISTRY = r"Y:\adala-project\aiocr_data\registry.json"

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
AR_DIAC = re.compile(r"[ً-ٰٟـ]")
NUM = r"[0-9]{1,2}[./][0-9]{2}[./][0-9]{1,4}|[0-9]{1,3}[./][0-9]{2}"
LAW_REF = re.compile(r"(?:القانون|قانون|الظهير|المرسوم|القرار)\s+رقم\s*(" + NUM + r")")


def norm_text(s):
    s = AR_DIAC.sub("", s.translate(AR_DIGITS))
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ى", "ي").replace("ة", "ه"))
    return re.sub(r"\s+", "", s)


def probe(path):
    sha1 = hashlib.sha1(open(path, "rb").read()).hexdigest()
    fp, nums, npages, has_text = None, [], 0, False
    try:
        doc = fitz.open(path)
        npages = len(doc)
        head = "".join(pg.get_text() for pg in doc[:3])
        title = (doc[0].get_text() if npages else "").translate(AR_DIGITS)[:500]
        doc.close()
        t = norm_text(head)
        has_text = len(t) > 300
        if has_text:
            fp = hashlib.sha1(t[:4000].encode()).hexdigest()
        nums = sorted({m.group(1).replace("/", ".").strip(".")
                       for m in LAW_REF.finditer(title)})
    except Exception:
        pass
    return {"sha1": sha1, "text_fp": fp, "nums": nums,
            "npages": npages, "has_text": has_text}


def main():
    reg = json.load(open(REGISTRY, encoding="utf-8"))
    by_sha = {d["sha1"] for d in reg["docs"].values()}
    by_fp = {d["text_fp"] for d in reg["docs"].values() if d.get("text_fp")}

    # 1. métadonnées récupérées (catalog + index du scrape)
    for item in ("_catalog", "_adala_index.json"):
        s, d = os.path.join(SRC, item), os.path.join(DST, item)
        if os.path.exists(s) and not os.path.exists(d):
            (shutil.copytree if os.path.isdir(s) else shutil.copy2)(s, d)
            print(f"récupéré: {item}")

    # 2. union des PDF
    copied = dup_sha = dup_fp = err = 0
    for dp, _dn, fn in os.walk(SRC):
        if "_catalog" in dp:
            continue
        for f in fn:
            if not f.lower().endswith(".pdf"):
                continue
            src = os.path.join(dp, f)
            try:
                info = probe(src)
            except Exception:
                err += 1
                continue
            if info["sha1"] in by_sha:
                dup_sha += 1
                continue
            if info["text_fp"] and info["text_fp"] in by_fp:
                dup_fp += 1
                continue
            theme = os.path.relpath(dp, SRC)
            ddir = os.path.join(DST, theme) if theme != "." else DST
            os.makedirs(ddir, exist_ok=True)
            dst = os.path.join(ddir, f)
            if os.path.exists(dst):
                stem, ext = os.path.splitext(f)
                dst = os.path.join(ddir, f"{stem}_{info['sha1'][:8]}{ext}")
            shutil.copy2(src, dst)
            rel = os.path.join("adala", os.path.relpath(dst, DST))
            info["collection"] = "adala"
            reg["docs"][rel] = info
            by_sha.add(info["sha1"])
            if info["text_fp"]:
                by_fp.add(info["text_fp"])
            copied += 1
            if copied % 200 == 0:
                print(f"copiés: {copied}", flush=True)

    json.dump(reg, open(REGISTRY, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"terminé: nouveaux={copied} | doublons octets={dup_sha} "
          f"| doublons contenu={dup_fp} | erreurs={err}")
    print(f"registre: {len(reg['docs'])} documents")


if __name__ == "__main__":
    main()
