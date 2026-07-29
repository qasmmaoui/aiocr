# -*- coding: utf-8 -*-
"""Extraction des citations arrêts → textes de loi (table `relations`, v1).

Parcourt le texte des arrêts extraits (juris_texts.jsonl) et capture les
références du type «المادة/الفصل N من <texte>» ; résout le texte cité vers un
document du corpus quand un numéro officiel est présent, sinon vers un nom de
code connu (مدونة التجارة، قانون الالتزامات والعقود…).
Sortie : relations.json  [{ruling, article, target_name, target_num, resolved}]
"""
import json
import os
import re

TEXTS = r"Y:\adala-project\aiocr_data\juris_texts.jsonl"
ALIAS = r"Y:\adala-project\aiocr_data\adala_alias_index.json"
OUT = r"Y:\adala-project\aiocr_data\relations.json"

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
NUM = r"[0-9]{1,2}[./][0-9]{2}[./][0-9]{1,4}|[0-9]{1,3}[./][0-9]{2}"

# Corruption de ligature lam-alef dans le texte extrait : «المادة» stocké
# «املادة», «الجنائي» -> «اجلنائي» (le ل se déplace après la lettre suivante).
LIG = re.compile(r"(?<![؀-ۿ])([وفبلك]?)ا([بتثجحخدذرزسشصضطظعغفقمنهي])ل")


def fix_ligatures(t: str) -> str:
    """Ne corrige qu'en début de mot (article défini ال, préfixe optionnel) —
    utilisé pour l'appariement seulement, jamais réécrit dans les données."""
    return LIG.sub(r"\1ال\2", t)

CIT = re.compile(
    r"(?:المادة|الفصل|المادتين|الفصلين)\s*([0-9٠-٩][0-9٠-٩\s./و،-]{0,25}?)\s*"
    r"من\s+((?:مدونة|قانون|القانون|ظهير|الظهير|مرسوم|المرسوم|ق\.?\s?[لمج][\.\s]?[عمج]?\.?)"
    r"[^.\n،;:]{0,60})")

# codes cités par leur nom usuel (sans numéro)
CODE_NAMES = {
    "مدونة التجارة": "15.95", "مدونة الأسرة": "70.03", "مدونة الشغل": "65.99",
    "مدونة الحقوق العينية": "39.08", "مدونة السير": "52.05",
    "قانون الالتزامات والعقود": "ق.ل.ع", "ق.ل.ع": "ق.ل.ع",
    "قانون المسطرة المدنية": "ق.م.م", "ق.م.م": "ق.م.م",
    "قانون المسطرة الجنائية": "22.01", "القانون الجنائي": "ق.ج",
    "مجموعة القانون الجنائي": "ق.ج",
}


def main() -> None:
    alias = json.load(open(ALIAS, encoding="utf-8")) if os.path.exists(ALIAS) else {}
    relations, n_docs = [], 0
    with open(TEXTS, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            n_docs += 1
            text = fix_ligatures(rec["text"].translate(AR_DIGITS))
            seen = set()
            for m in CIT.finditer(text):
                arts_raw, target = m.group(1), m.group(2).strip()
                nm = re.search(r"رقم\s*(" + NUM + r")", target)
                tnum = nm.group(1).replace("/", ".").strip(".") if nm else ""
                if not tnum:
                    for name, code in CODE_NAMES.items():
                        if target.startswith(name) or name in target[:40]:
                            tnum = code
                            break
                arts = [a for a in re.split(r"[و،\s-]+", arts_raw)
                        if a.strip("./").isdigit()][:6]
                for a in arts:
                    key = (a, tnum or target[:30])
                    if key in seen:
                        continue
                    seen.add(key)
                    relations.append({
                        "ruling": rec["file"],
                        "article": a,
                        "target_name": target[:70],
                        "target_num": tnum,
                        "resolved": bool(tnum and (tnum in alias or tnum in
                                                   CODE_NAMES.values())),
                    })
    json.dump(relations, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    resolved = sum(1 for r in relations if r["resolved"])
    rulings = len({r["ruling"] for r in relations})
    print(f"{len(relations)} citations extraites de {rulings}/{n_docs} arrêts "
          f"({resolved} résolues vers un texte identifié) -> {OUT}")
    from collections import Counter
    top = Counter((r["target_num"] or r["target_name"][:25]) for r in relations)
    for t, c in top.most_common(10):
        print(f"  {c:5d}  {t}")


if __name__ == "__main__":
    main()
