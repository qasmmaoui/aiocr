# -*- coding: utf-8 -*-
"""Passe 2 — corruption des numéros d'article par collage de notes.

Les PDF officiels portent des appels de note en exposant, collés au numéro de
l'article lors de l'extraction : « المادة 384 » suivi de l'appel « 182 » donne
« المادة 182384 ». L'article devient alors introuvable par sa référence
exacte — le mécanisme d'ancrage cherche « المادة 384 » et ne le voit pas.
"""
import collections, json, re

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl"
NOTE = re.compile(r"(\d{1,3})\s*-\s*(?:تم|المرسوم|الظهير|القانون|الجريدة|تمت|أضيف|نسخ)")
cas = []
par_doc = collections.Counter()
n_suspects = 0

for line in open(C, encoding="utf-8"):
    r = json.loads(line)
    a = str(r.get("article") or "").strip()
    if not a or a == "None":
        continue
    m = re.search(r"(\d{4,6})", a)
    if not m:
        continue
    n_suspects += 1
    brut = m.group(1)
    t = r.get("text") or ""
    notes = set(NOTE.findall(t))
    # le numéro composite commence-t-il par un appel de note trouvé dans le texte ?
    explique = None
    for nt in notes:
        if brut.startswith(nt) and len(brut) > len(nt):
            explique = (nt, brut[len(nt):])
            break
        if brut.endswith(nt) and len(brut) > len(nt):
            explique = (nt, brut[:-len(nt)])
            break
    if explique:
        par_doc[(r.get("file") or "")[:50]] += 1
        if len(cas) < 8:
            cas.append((brut, explique, (r.get("file") or "")[:40],
                        re.sub(r"\s+", " ", t)[:130]))

total_explique = sum(par_doc.values())
print(f"articles à numéro anormalement long (4 à 6 chiffres) : {n_suspects:,}")
print(f"  ... expliqués par un appel de note collé            : {total_explique:,}"
      f"  ({total_explique*100//max(n_suspects,1)} %)")
print()
print("=== mécanisme, sur pièces ===")
for brut, (note, vrai), f, t in cas:
    print(f"  «المادة {brut}»  =  note {note} + article {vrai}   ({f})")
    print(f"     {t}")
    print()
print("=== documents les plus touchés ===")
for f, n in par_doc.most_common(10):
    print(f"  {n:>5} articles corrompus   {f}")
