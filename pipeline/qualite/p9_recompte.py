# -*- coding: utf-8 -*-
"""Recompte des numéros corrompus, en distinguant les codes réellement longs.

Erreur de la passe précédente : tout numéro à quatre chiffres était réputé
corrompu. Or le code des obligations compte 1 250 articles — « الفصل 1000 » y
est parfaitement légitime.

Le bon discriminant n'est pas la longueur du nombre mais sa RÉGULARITÉ : un
numéro élevé authentique prolonge la suite du document et se présente dans
l'ordre des chunks ; un numéro corrompu surgit isolé, sans voisin proche.
"""
import collections, json, re

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl"
docs = collections.defaultdict(list)
for line in open(C, encoding="utf-8"):
    r = json.loads(line)
    a = str(r.get("article") or "")
    m = re.search(r"(\d{1,6})", a)
    if not m:
        continue
    docs[(r.get("file") or "")[:70]].append(
        (r.get("chunk") if isinstance(r.get("chunk"), int) else 0, int(m.group(1))))

legit = corrompu = 0
par_doc = collections.Counter()
for f, paires in docs.items():
    nums = sorted({v for _, v in paires})
    ens = set(nums)
    for v in nums:
        if v < 1000:
            continue
        # authentique s'il a un voisin immédiat dans le document : les codes
        # longs numérotent en continu, la corruption produit des isolés
        voisin = any((v + d) in ens for d in (-2, -1, 1, 2))
        if voisin:
            legit += 1
        else:
            corrompu += 1
            par_doc[f] += 1

print(f"numéros d'article ≥ 1000 rencontrés : {legit + corrompu:,}")
print(f"  authentiques (suite continue)     : {legit:,}")
print(f"  corrompus (isolés)                : {corrompu:,}")
print()
print("=== documents réellement atteints ===")
for f, n in par_doc.most_common(12):
    tot = len({v for _, v in docs[f]})
    print(f"  {n:>4} corrompus sur {tot:>5} numéros distincts   {f[:52]}")
