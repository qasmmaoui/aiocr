# -*- coding: utf-8 -*-
"""Passe 4b — dates dans les formules législatives seulement.

La passe précédente ratissait trop large : dans une liste d'avocats, « أبريل »
et « ماي » sont des patronymes. On n'examine donc que les dates enchâssées
dans une formule d'édiction — « صادر في … », « بتاريخ … », « ظهير … » — où le
nombre a valeur normative, et on écarte revues et annuaires.
"""
import collections, json, re

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl"
MOIS_G = r"(?:يناير|فبراير|مارس|أبريل|ماي|مايو|يونيو|يونيه|يوليو|يوليوز|غشت|أغسطس|شتنبر|سبتمبر|أكتوبر|نونبر|نوفمبر|دجنبر|ديسمبر)"
# la date doit suivre une amorce d'édiction, dans les 60 caractères
FORMULE = re.compile(
    r"(?:صادر\s+في|بتاريخ|مؤرخ\s+في|الصادر\s+في)[^\n]{0,60}?"
    r"\(\s*(\d{1,2})\s*" + MOIS_G + r"\s*(\d{1,4})\s*\)")
EXCLUS = ("مجلة", "قائمة", "التقرير السنوي", "دليل", "نشرة", "annuaire")

docs = collections.Counter(); ex = []
tot = 0
for line in open(C, encoding="utf-8"):
    r = json.loads(line)
    f = (r.get("file") or "")
    if any(x in f for x in EXCLUS):
        continue
    t = r.get("text") or ""
    for m in FORMULE.finditer(t):
        tot += 1
        jour, annee = int(m.group(1)), int(m.group(2))
        mauvais = not (1900 <= annee <= 2030) or not (1 <= jour <= 31)
        if mauvais:
            docs[f[:56]] += 1
            if len(ex) < 10:
                ex.append((jour, annee,
                           re.sub(r"\s+", " ", t[max(0, m.start()-40):m.end()+10]),
                           f[:46]))

print(f"dates législatives complètes analysées : {tot:,}")
print(f"  ... aberrantes : {sum(docs.values()):,} sur {len(docs):,} documents")
print(f"  taux de corruption : {sum(docs.values())*100/max(tot,1):.2f} %")
print()
for j, a, ctx, f in ex:
    print(f"  jour={j} année={a}")
    print(f"     …{ctx[-120:]}")
    print(f"     {f}")
print()
print("=== documents concernés ===")
for f, n in docs.most_common(10):
    print(f"  {n:>4}  {f}")
