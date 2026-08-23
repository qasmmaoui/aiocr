# -*- coding: utf-8 -*-
"""Épreuve — l'ancrage par référence exacte retrouve-t-il l'article ?

C'est la façon dont un juriste interroge : « المادة 384 من قانون المسطرة
الجنائية ». Le moteur cherche alors dans le corpus lexical un fragment dont
le champ `article` porte ce numéro. Si le numéro a absorbé un appel de note,
le fragment existe mais reste introuvable.

On rejoue exactement la logique de `article_anchors` sur les deux corpus —
avant réparation et après — et on compte ce qui se trouve.
"""
import json, re, sys

AVANT = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl"
APRES = AVANT + ".repare.signale.courts.renvois.final"

# références réellement présentes dans les codes, choisies sur le texte
EPREUVES = [
    ("المادة 384 من قانون المسطرة الجنائية", "384", "1.02.255"),
    ("المادة 40 من قانون المسطرة الجنائية",  "40",  "1.02.255"),
    ("الفصل 264 من قانون الالتزامات والعقود", "264", "الالتزامات"),
    ("الفصل 425 من قانون الالتزامات والعقود", "425", "الالتزامات"),
    ("الفصل 1170 من قانون الالتزامات والعقود", "1170", "الالتزامات"),
    ("المادة 204 من قانون المسطرة المدنية",  "204", "1.26.07"),
    ("الفصل 60 من مدونة الجمارك",            "60",  "الجمارك"),
    ("الفصل 90 من مدونة الجمارك",            "90",  "الجمارك"),
    ("المادة 193 من قانون شركات المساهمة",   "193", "17.95"),
    ("المادة 232 من قانون 17.99",            "232", "17.99"),
]


def index(chemin):
    """article normalisé -> liste de (fichier, extrait)"""
    par_num = {}
    for line in open(chemin, encoding="utf-8"):
        r = json.loads(line)
        a = str(r.get("article") or "")
        m = re.search(r"(\d{1,6}(?:[-.]\d{1,3})?)", a)
        if not m:
            continue
        par_num.setdefault(m.group(1), []).append(
            (r.get("file") or "", re.sub(r"\s+", " ", r.get("text") or "")[:70]))
    return par_num


def essai(par_num, num, indice):
    for f, t in par_num.get(num, []):
        if indice in f:
            return t
    return None


av, ap = index(AVANT), index(APRES)
print(f"{'référence':<44} {'avant':<8} {'après'}")
print("-" * 70)
gagnes = perdus = 0
for q, num, indice in EPREUVES:
    a = essai(av, num, indice)
    b = essai(ap, num, indice)
    if not a and b: gagnes += 1; verdict = "TROUVÉ ✓"
    elif a and not b: perdus += 1; verdict = "PERDU ✗"
    elif a and b: verdict = "déjà bon"
    else: verdict = "toujours absent"
    print(f"{q[:42]:<44} {'oui' if a else 'non':<8} {verdict}")
print("-" * 70)
print(f"articles rendus trouvables : {gagnes}")
print(f"articles perdus            : {perdus}")
print()
for q, num, indice in EPREUVES:
    b = essai(ap, num, indice)
    if b and not essai(av, num, indice):
        print(f"  «{q[:40]}»")
        print(f"      {b}")
