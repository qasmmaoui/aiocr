# -*- coding: utf-8 -*-
"""Passe 17 — le texte de l'article désigne son propre rang.

Un article renvoie presque toujours à celui qui le précède : « المنصوص عليه
في المادة 231 أعلاه ». Le mot « أعلاه » — ci-dessus — garantit que l'article
cité est ANTÉRIEUR. Le numéro courant lui est donc supérieur, et le plus
souvent son successeur immédiat.

Quatrième preuve, indépendante de la suite du document, de l'appel de note et
du contenu jumeau. On ne conclut que si un seul candidat la satisfait.
"""
import collections, json, re

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl.repare.signale.courts"
SORTIE = C + ".renvois"
RENVOI = re.compile(r"(?:المادة|الفصل)\s*(\d{1,4})\s*أعلاه")
ENTETE = re.compile(r"^\s*(?:المادة|الفصل)\s*\d{1,6}")

corrections = {}
stats = collections.Counter()
ex = []

for i, line in enumerate(open(C, encoding="utf-8")):
    r = json.loads(line)
    if r.get("article_avant_reparation"):
        continue
    a = str(r.get("article") or "")
    m = re.search(r"(\d{4,})", a)
    if not m:
        continue
    stats["restants"] += 1
    brut = m.group(1)
    t = r.get("text") or ""
    # renvois vers un article antérieur, hors l'en-tête lui-même
    corps = ENTETE.sub("", t, count=1)
    anterieurs = [int(x) for x in RENVOI.findall(corps)]
    if not anterieurs:
        stats["sans_renvoi"] += 1
        continue
    plafond = max(anterieurs)
    cands = []
    for L in range(1, len(brut)):
        suf = brut[L:]
        if not suf or suf.startswith("0"):
            continue
        v = int(suf)
        # le rang courant suit le plus grand article cité comme antérieur
        if plafond < v <= plafond + 3:
            cands.append((v, brut[:L]))
    if len(cands) == 1:
        stats["tranches"] += 1
        corrections[i] = (cands[0][0], brut, cands[0][1], plafond)
        if len(ex) < 8:
            ex.append((brut, cands[0][0], cands[0][1], plafond,
                       (r.get("file") or "")[:42],
                       re.sub(r"\s+", " ", t)[:95]))
    else:
        stats["ambigu"] += 1

with open(C, encoding="utf-8") as src, open(SORTIE, "w", encoding="utf-8") as dst:
    for i, line in enumerate(src):
        if i in corrections:
            r = json.loads(line)
            vrai, ancien, note, plafond = corrections[i]
            etiq = str(r.get("article") or "")
            prefixe = "المادة" if "المادة" in etiq else "الفصل"
            r["article"] = f"{prefixe} {vrai}"
            r["article_avant_reparation"] = etiq
            r["preuve"] = f"renvoi interne à {plafond} أعلاه"
            line = json.dumps(r, ensure_ascii=False) + "\n"
        dst.write(line)

print(f"numéros encore corrompus     : {stats['restants']:,}")
print(f"  sans renvoi interne        : {stats['sans_renvoi']:,}")
print(f"  ambigus                    : {stats['ambigu']:,}")
print(f"  TRANCHÉS par le renvoi     : {stats['tranches']:,}")
print(f"\nsortie : {SORTIE}\n")
for brut, vrai, note, plaf, f, t in ex:
    print(f"  «{brut}» → article {vrai} (note {note}) — cite «المادة {plaf} أعلاه»")
    print(f"      {t[:88]}")
