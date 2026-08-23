# -*- coding: utf-8 -*-
"""Réparation des collages courts — trois preuves exigées.

« 45 » est indiscernable d'un article 45 pris isolément. On ne le corrige donc
que si trois signaux concordent :

  1. le retrait du préfixe RESTAURE exactement la suite (article courant + 1) ;
  2. les préfixes retirés forment eux-mêmes une suite croissante dans le
     document — les notes de bas de page se numérotent en montant, une note 7
     ne précède jamais une note 3 ;
  3. la qualité de suite du document progresse.

Le corpus source n'est pas modifié : écriture dans un nouveau fichier.
"""
import collections, json, re

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl.repare.signale"
SORTIE = C + ".courts"
JOURNAL = r"Y:\adala-project\evaluation_20260821\forensique\journal_collages_courts.tsv"


def qualite(nums):
    e = set(nums)
    return sum(1 for v in e if (v - 1) in e or (v + 1) in e) / len(e) if len(e) > 2 else None


docs = collections.defaultdict(list)
for i, line in enumerate(open(C, encoding="utf-8")):
    r = json.loads(line)
    a = str(r.get("article") or "").replace("المادة", "").replace("الفصل", "").strip()
    m = re.match(r"(\d{1,6})", a)
    if not m:
        continue
    ch = r.get("chunk") if isinstance(r.get("chunk"), int) else 0
    docs[r.get("file") or ""].append((ch, i, m.group(1), a))

corrections, journal = {}, []
stats = collections.Counter()

for f, lst in docs.items():
    lst.sort()
    courant, suspects = None, []
    for ch, i, brut, complet in lst:
        v = int(brut)
        if courant is None or v == courant or v == courant + 1:
            courant = v if courant is None else v
            continue
        trouve = None
        for L in range(1, len(brut)):
            suf = brut[L:]
            if not suf or suf.startswith("0"):
                continue
            if int(suf) == courant + 1:
                trouve = (int(brut[:L]), int(suf), complet[len(brut):])
                break
        if trouve:
            suspects.append((i, brut, trouve[0], trouve[1], trouve[2]))
            courant = trouve[1]
        elif v > courant:
            courant = v

    if not suspects:
        continue
    # preuve 2 : les notes retirées montent-elles ?
    notes = [n for _, _, n, _, _ in suspects]
    if len(notes) > 1 and any(b < a for a, b in zip(notes, notes[1:])):
        stats["notes_non_croissantes"] += len(suspects)
        journal.append((f[:56], len(suspects), "-", "-", "REFUSÉ notes désordonnées"))
        continue
    # preuve 3 : la suite du document progresse-t-elle ?
    avant = [int(b) for _, _, b, _ in [(a, b, c, d) for a, b, c, d in
             [(x[0], x[1], x[2], x[3]) for x in lst]]]
    avant = [int(x[2]) for x in lst]
    remp = {i: vrai for i, _, _, vrai, _ in suspects}
    apres = [remp.get(x[1], int(x[2])) for x in lst]
    qa, qb = qualite(avant), qualite(apres)
    if qa is None or qb is None or qb <= qa:
        stats["suite_non_amelioree"] += len(suspects)
        journal.append((f[:56], len(suspects), f"{qa}", f"{qb}", "REFUSÉ"))
        continue
    stats["documents"] += 1
    stats["corrections"] += len(suspects)
    journal.append((f[:56], len(suspects), f"{qa:.3f}", f"{qb:.3f}", "accepté"))
    for i, brut, note, vrai, suffixe in suspects:
        corrections[i] = (f"{vrai}{suffixe}", brut, note)

with open(C, encoding="utf-8") as src, open(SORTIE, "w", encoding="utf-8") as dst:
    for i, line in enumerate(src):
        if i in corrections:
            r = json.loads(line)
            nouveau, ancien_num, note = corrections[i]
            ancien = str(r.get("article") or "")
            prefixe = "المادة" if "المادة" in ancien else "الفصل"
            r["article"] = f"{prefixe} {nouveau}"
            r.setdefault("article_avant_reparation", ancien)
            r["note_collee"] = note
            line = json.dumps(r, ensure_ascii=False) + "\n"
        dst.write(line)

with open(JOURNAL, "w", encoding="utf-8") as fh:
    fh.write("document\tcorrections\tqualite_avant\tqualite_apres\tdecision\n")
    for j in journal:
        fh.write("\t".join(str(x) for x in j) + "\n")

print(f"documents corrigés            : {stats['documents']:,}")
print(f"collages courts réparés       : {stats['corrections']:,}")
print(f"refusés — notes désordonnées  : {stats['notes_non_croissantes']:,}")
print(f"refusés — suite non améliorée : {stats['suite_non_amelioree']:,}")
print(f"\nsortie : {SORTIE}")
