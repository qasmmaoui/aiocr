# -*- coding: utf-8 -*-
"""Passe 13 — résoudre par le jumeau : un même texte dans deux documents.

Plusieurs codes figurent en double dans le corpus, issus de PDF différents.
Quand l'un porte un numéro corrompu et l'autre un numéro sain pour le MÊME
texte d'article, le second tranche le premier — sans supposition.

C'est une troisième méthode, indépendante de la suite des articles et de
l'appel de note : elle repose sur l'identité du contenu, pas sur une
inférence.
"""
import collections, json, re

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl.repare.signale"
ENTETE = re.compile(r"^\s*(?:المادة|الفصل)\s*\d{1,6}(?:[-.]\d{1,3})?\s*")
DIA = re.compile(r"[\u064B-\u0652\u0670]")


def empreinte(t: str) -> str:
    """Texte de l'article, en-tête retiré, normalisé — sert de clé d'identité."""
    t = ENTETE.sub("", t or "", count=1)
    t = DIA.sub("", t)
    t = re.sub(r"[^\u0621-\u064A]", "", t)
    return t[:220]


sains = {}          # empreinte -> (numéro, document)
corrompus = []      # fragments dont l'étiquette reste douteuse
for line in open(C, encoding="utf-8"):
    r = json.loads(line)
    a = str(r.get("article") or "")
    m = re.search(r"(\d{1,6})", a)
    if not m:
        continue
    t = r.get("text") or ""
    emp = empreinte(t)
    if len(emp) < 90:
        continue
    num = m.group(1)
    if len(num) <= 3 and not r.get("article_avant_reparation"):
        sains.setdefault(emp, (num, (r.get("file") or "")[:40]))
    elif len(num) >= 4:
        corrompus.append((a, emp, (r.get("file") or "")[:46],
                          re.sub(r"\s+", " ", t)[:100]))

print(f"empreintes d'articles sains indexées : {len(sains):,}")
print(f"fragments encore douteux             : {len(corrompus):,}")

resolus = []
for a, emp, f, t in corrompus:
    jum = sains.get(emp)
    if jum:
        resolus.append((a, jum[0], f, jum[1], t))

print(f"  ... tranchés par un jumeau         : {len(resolus):,}")
print()
for a, num, f, fj, t in resolus[:10]:
    print(f"  «{a}» → {num}")
    print(f"      abîmé  : {f}")
    print(f"      jumeau : {fj}")
    print(f"      {t[:90]}")
    print()
