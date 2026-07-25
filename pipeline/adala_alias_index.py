# -*- coding: utf-8 -*-
"""Index numéro officiel -> fichiers, sur le bloc-titre (500 premiers chars de
la page 1) des PDF adala_pdfs. Les noms de fichiers étant souvent tronqués,
seul le contenu fait foi. Sortie : adala_alias_index.json {num: [relpaths]}."""
import glob
import json
import os
import re

import fitz

ADALA_DIR = r"Y:\adala-project\adala_pdfs"
OUT = r"Y:\adala-project\aiocr_data\adala_alias_index.json"

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
NUM = r"[0-9]{1,2}[./][0-9]{2}[./][0-9]{1,4}|[0-9]{1,3}[./][0-9]{2}"
LAW_REF = re.compile(r"(?:القانون|قانون|الظهير|المرسوم|القرار)\s+رقم\s*(" + NUM + r")")


def main() -> None:
    pdfs = glob.glob(os.path.join(ADALA_DIR, "**", "*.pdf"), recursive=True)
    idx: dict[str, list[str]] = {}
    n_err = 0
    for i, p in enumerate(pdfs):
        rel = os.path.relpath(p, ADALA_DIR)
        try:
            doc = fitz.open(p)
            head = doc[0].get_text().translate(AR_DIGITS)[:500]
            doc.close()
        except Exception:
            n_err += 1
            continue
        for m in LAW_REF.finditer(head):
            num = m.group(1).replace("/", ".").strip(".")
            idx.setdefault(num, []).append(rel)
        if (i + 1) % 1000 == 0:
            print(f"{i + 1}/{len(pdfs)}", flush=True)
    json.dump(idx, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"terminé: {len(pdfs)} pdfs, {len(idx)} numéros indexés, {n_err} erreurs")


if __name__ == "__main__":
    main()
