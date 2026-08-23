# -*- coding: utf-8 -*-
"""Passe 15 — les collages courts, invisibles à l'œil.

« 45 » peut être l'article 45, ou l'appel de note 4 collé à l'article 5. Rien
dans le nombre ne les distingue : seule la SUITE tranche. Dans un décret dont
les articles vont de 1 à 35, la séquence

    21  2  33  4  45  6  67  8  89  910  1011  12 …

ne laisse aucun doute — un article sur deux a absorbé sa note.

On ne signale un collage que si le retrait du préfixe RESTAURE la suite : le
suffixe doit valoir exactement un de plus que le dernier article accepté.
"""
import collections, json, re

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl.repare.signale"
docs = collections.defaultdict(list)
for i, line in enumerate(open(C, encoding="utf-8")):
    r = json.loads(line)
    m = re.search(r"^(\d{1,6})", str(r.get("article") or "").replace("المادة", "")
                  .replace("الفصل", "").strip())
    if not m:
        continue
    ch = r.get("chunk") if isinstance(r.get("chunk"), int) else 0
    docs[r.get("file") or ""].append((ch, i, m.group(1), bool(r.get("article_avant_reparation"))))

trouves = collections.Counter()
ex = collections.defaultdict(list)
total = 0
for f, lst in docs.items():
    lst.sort()
    # on parcourt en suivant le dernier article jugé authentique
    courant = None
    suspects = []
    for ch, i, brut, deja in lst:
        v = int(brut)
        if courant is None:
            courant = v
            continue
        if v == courant or v == courant + 1:      # suite normale
            courant = v
            continue
        # le retrait d'un préfixe restaure-t-il la suite ?
        restaure = None
        for L in range(1, len(brut)):
            suf = brut[L:]
            if suf.startswith("0") or not suf:
                continue
            if int(suf) == courant + 1:
                restaure = (brut[:L], int(suf))
                break
        if restaure:
            suspects.append((ch, brut, restaure[1], restaure[0]))
            courant = restaure[1]
        elif v > courant:
            courant = v
    if suspects:
        trouves[f[:56]] = len(suspects)
        total += len(suspects)
        if len(ex) < 6:
            ex[f[:46]] = suspects[:6]

print(f"collages restaurant la suite : {total:,} dans {len(trouves):,} documents")
print()
for f, s in ex.items():
    print(f"  {f}")
    for ch, brut, vrai, note in s:
        print(f"      «{brut}» → article {vrai} (note {note}) au chunk {ch}")
    print()
print("=== documents les plus touchés ===")
for f, n in trouves.most_common(12):
    print(f"  {n:>4}  {f}")
