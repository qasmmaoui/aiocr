# -*- coding: utf-8 -*-
"""Filet de sécurité — annule les réparations qui se contredisent.

Les passes travaillent chacune de leur côté ; rien ne garantit qu'elles ne
convergent pas. Deux numéros corrompus DIFFÉRENTS qui aboutissent au même
article, dans des fragments éloignés, signalent une résolution fautive : l'un
des deux au moins est faux, et rien ici ne dit lequel.

Constaté sur le texte relatif au contrôle de la chasse : « الفصل 2013 » et
« الفصل 2113 » ramenés tous deux à l'article 13, alors que le second renvoie
« إلى غاية الفصل 13 أعلاه » — il se situe donc APRÈS.

Dans le doute, on rend les deux à leur état d'origine. Une étiquette corrompue
est un article introuvable ; une étiquette fausse est un article qui répond à
la place d'un autre. Le second défaut est le plus grave.
"""
import collections
import json
import re

# Un fragment de CONTINUATION ne réimprime pas l'en-tête ; deux
# fragments qui le portent chacun sont deux articles distincts.
ENTETE = re.compile(r"^\s*(?:المادة|الفصل)\s*\d")

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl.repare.signale.courts.renvois"
SORTIE = C + ".final"

# repérage
par_doc = collections.defaultdict(lambda: collections.defaultdict(list))
for i, line in enumerate(open(C, encoding="utf-8")):
    r = json.loads(line)
    if not r.get("article_avant_reparation"):
        continue
    par_doc[r.get("file") or ""][str(r.get("article"))].append(
        (i, str(r["article_avant_reparation"]),
         r.get("chunk") if isinstance(r.get("chunk"), int) else 0,
         bool(ENTETE.match(r.get("text") or ""))))

a_annuler = set()
groupes = 0
for f, etiqs in par_doc.items():
    for cible, lst in etiqs.items():
        origines = {o for _, o, _, _ in lst}
        if len(origines) < 2:
            continue
        # Un article étalé sur plusieurs fragments n'imprime son en-tête
        # qu'une fois. Si plusieurs en portent un, ce sont des articles
        # DIFFÉRENTS ramenés à tort au même numéro.
        avec_entete = sum(1 for _, _, _, e in lst if e)
        if avec_entete < 2:
            continue
        groupes += 1
        a_annuler.update(i for i, _, _, _ in lst)

n = 0
with open(C, encoding="utf-8") as src, open(SORTIE, "w", encoding="utf-8") as dst:
    for i, line in enumerate(src):
        if i in a_annuler:
            r = json.loads(line)
            r["article"] = r.pop("article_avant_reparation")
            r.pop("note_collee", None)
            r.pop("preuve", None)
            r["reparation_annulee"] = "convergence ambiguë"
            line = json.dumps(r, ensure_ascii=False) + "\n"
            n += 1
        dst.write(line)

print(f"groupes de convergence détectés : {groupes}")
print(f"réparations annulées            : {n}")
print(f"\nsortie : {SORTIE}")
