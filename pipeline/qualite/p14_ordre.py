# -*- coding: utf-8 -*-
"""Passe 14 — la suite des articles recule-t-elle ?

Un texte de loi numérote en montant. Quand la suite redescend franchement au
milieu d'un document, deux causes possibles :
  — deux textes différents ont été fusionnés dans un même fichier ;
  — le découpage a mélangé l'ordre des pages.

Dans les deux cas, un fragment peut être servi sous l'identité d'un autre
texte. On mesure les reculs nets, en ignorant les allers-retours d'un ou deux
rangs, qui viennent des renvois internes.
"""
import collections, json, re

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl.repare.signale"
docs = collections.defaultdict(list)
for line in open(C, encoding="utf-8"):
    r = json.loads(line)
    m = re.search(r"(\d{1,5})", str(r.get("article") or ""))
    if not m:
        continue
    ch = r.get("chunk") if isinstance(r.get("chunk"), int) else 0
    docs[r.get("file") or ""].append((ch, int(m.group(1))))

suspects = []
for f, paires in docs.items():
    if len(paires) < 20:
        continue
    paires.sort()
    nums = [v for _, v in paires]
    reculs = []
    sommet = nums[0]
    for i, v in enumerate(nums[1:], 1):
        if v < sommet - 20:            # recul net, pas un simple renvoi
            reculs.append((sommet, v, paires[i][0]))
            sommet = v
        elif v > sommet:
            sommet = v
    if len(reculs) >= 2:
        suspects.append((len(reculs), f, reculs, max(nums)))

suspects.sort(reverse=True)
print(f"documents où la suite recule au moins deux fois : {len(suspects):,}"
      f" sur {len(docs):,} documents numérotés")
print()
for n, f, reculs, maxi in suspects[:12]:
    print(f"  {n:>3} reculs (max article {maxi})  {f[:52]}")
    for a, b, ch in reculs[:3]:
        print(f"        {a} → {b} au chunk {ch}")
