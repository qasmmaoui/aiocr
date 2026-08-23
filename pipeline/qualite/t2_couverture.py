# -*- coding: utf-8 -*-
"""Épreuve d'ensemble — quelle part des articles d'un code est citable ?

Pour chaque code majeur, on prend l'étendue réelle de sa numérotation et on
compte combien d'articles sont atteignables par leur référence exacte, avant
et après la chaîne de réparation. C'est la mesure qui compte : un juriste
cite un numéro, le moteur doit le retrouver.
"""
import collections, json, re

AVANT = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl"
APRES = AVANT + ".repare.signale.courts.renvois"

CODES = [
    ("1.02.255",           "Procédure pénale"),
    ("مدونة الجمارك",       "Douanes"),
    ("الالتزامات والعقود",  "Obligations et contrats"),
    ("1.26.07",            "Procédure civile 2026"),
    ("17.95",              "Sociétés anonymes"),
    ("17.97",              "Propriété industrielle"),
    ("1.10.07",            "Code de la route"),
    ("القانون-الجنائي",     "Code pénal"),
    ("1.02.238",           "Assurances / 17.99"),
]


def numeros(chemin, motif):
    out = set()
    for line in open(chemin, encoding="utf-8"):
        if motif not in line:
            continue
        r = json.loads(line)
        if motif not in (r.get("file") or ""):
            continue
        m = re.search(r"^(\d{1,4})", str(r.get("article") or "")
                      .replace("المادة", "").replace("الفصل", "").strip())
        if m:
            out.add(int(m.group(1)))
    return out


print(f"{'code':<26} {'étendue':>9} {'avant':>10} {'après':>10} {'gain':>8}")
print("-" * 68)
tot_av = tot_ap = tot_et = 0
for motif, nom in CODES:
    av, ap = numeros(AVANT, motif), numeros(APRES, motif)
    if not ap:
        continue
    # Étendue robuste : un code est DENSE jusqu'à son dernier article, puis
    # plus rien. Le maximum brut est trompeur — il capte les numéros encore
    # corrompus. On retient donc le plus grand rang dont le voisinage
    # immédiat est peuplé à plus de la moitié.
    etendue = 0
    for v in sorted(ap):
        if v > 1300:
            break
        voisins = sum(1 for d in range(-10, 11) if (v + d) in ap)
        if voisins >= 11:
            etendue = v
    if not etendue:
        continue
    dans_av = len([v for v in av if 1 <= v <= etendue])
    dans_ap = len([v for v in ap if 1 <= v <= etendue])
    tot_av += dans_av; tot_ap += dans_ap; tot_et += etendue
    gain = dans_ap - dans_av
    print(f"{nom:<26} {etendue:>9} {dans_av:>4} ({dans_av*100//etendue:>3}%) "
          f"{dans_ap:>4} ({dans_ap*100//etendue:>3}%) {gain:>+8}")
print("-" * 68)
print(f"{'TOTAL':<26} {tot_et:>9} {tot_av:>4} ({tot_av*100//tot_et:>3}%) "
      f"{tot_ap:>4} ({tot_ap*100//tot_et:>3}%) {tot_ap-tot_av:>+8}")
