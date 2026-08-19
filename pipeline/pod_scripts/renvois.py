# -*- coding: utf-8 -*-
"""Renvois juridiques des fiches de procédure, et texte visé.

Chaque fiche du guide cite des articles. Pour avertir l'avocat de façon utile,
il ne suffit pas de dire « des choses ont changé » : il faut nommer le texte
invoqué et son état. On extrait donc, par fiche, la liste des renvois sous la
forme (type d'article, numéros, loi visée), normalisée pour être résolue
ensuite dans le corpus.

Le guide date de 2024 et cite le code de procédure civile en FUSUL — la
numérotation de 1974, abrogée par la loi 58.25. Ce renvoi-là ne demande aucune
vérification : nous savons qu'il vise un texte abrogé.
"""
import collections
import json
import re
import sys

FICHES = json.load(open(sys.argv[1], encoding="utf-8"))

# « الفصول 134، 141، 142 و143 من قانون المسطرة المدنية »
RENVOI = re.compile(
    r"(الفصول|الفصل|المواد|المادة|الفقرات|الفقرة)\s*"
    r"([0-9٠-٩][0-9٠-٩،؛\s\-و]{0,60}?)\s*"
    r"من\s+([^\.\n\)،]{5,60})")

# Lois connues du corpus, avec leur état tel que nous l'avons établi.
LOIS = [
    (r"المسطرة\s*المدنية", "قانون المسطرة المدنية",
     {"etat": "abroge",
      "remplace_par": "القانون 58.25 (ظهير 1.26.07 du 11 février 2026)",
      "note": "Le guide cite la numérotation en فصول du code de 1974. "
              "Le code de 2026 numérote en مواد et a réformé une partie des "
              "circuits. Voir l'article 643 pour le régime transitoire."}),
    (r"المسطرة\s*الجنائية", "قانون المسطرة الجنائية", {"etat": "a_verifier"}),
    (r"المحاكم\s*التجارية", "قانون إحداث المحاكم التجارية", {"etat": "a_verifier"}),
    (r"المحاكم\s*الإدارية", "قانون إحداث المحاكم الإدارية", {"etat": "a_verifier"}),
    (r"مدونة\s*الأسرة", "مدونة الأسرة", {"etat": "a_verifier"}),
    (r"القانون\s*الجنائي", "مجموعة القانون الجنائي", {"etat": "a_verifier"}),
]

AR2LAT = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def numeros(brut: str) -> list[str]:
    return re.findall(r"\d{1,4}", brut.translate(AR2LAT))


def loi_de(libelle: str) -> tuple[str, dict] | None:
    for pat, nom, meta in LOIS:
        if re.search(pat, libelle):
            return nom, meta
    return None


total, resolus = 0, 0
par_loi = collections.Counter()
for f in FICHES:
    renvois = []
    blob = " ".join(str(f.get(k) or "") for k in
                    ("objet", "cadre_legal", "delais", "documents", "prerequis"))
    blob += " " + " ".join(
        e["intitule"] + " " + " ".join(e["actions"]) for e in f["etapes"])
    for m in RENVOI.finditer(blob):
        total += 1
        cible = loi_de(m.group(3))
        if not cible:
            continue
        resolus += 1
        nom, meta = cible
        par_loi[nom] += 1
        renvois.append({
            "type": m.group(1),
            "articles": numeros(m.group(2)),
            "loi": nom,
            **meta,
        })
    # dédoublonnage : une même loi peut être citée plusieurs fois
    vus, propres = set(), []
    for r in renvois:
        cle = (r["loi"], tuple(r["articles"]))
        if cle in vus:
            continue
        vus.add(cle)
        propres.append(r)
    f["renvois"] = propres

avec = sum(1 for f in FICHES if f["renvois"])
print(f"renvois détectés : {total} | rattachés à une loi connue : {resolus}")
print(f"fiches portant au moins un renvoi : {avec}/{len(FICHES)}")
for nom, n in par_loi.most_common():
    print(f"   {n:3d}×  {nom}")

abrogees = [f for f in FICHES
            if any(r.get("etat") == "abroge" for r in f["renvois"])]
print(f"\nfiches s'appuyant sur un texte ABROGÉ : {len(abrogees)}")
for f in abrogees[:6]:
    arts = [a for r in f["renvois"] if r["etat"] == "abroge" for a in r["articles"]]
    print(f"   p.{f['page']:>3}  {f['titre'][:50]:52s} art. {', '.join(arts[:6])}")

json.dump(FICHES, open(sys.argv[2], "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nfiches enrichies :", sys.argv[2])
