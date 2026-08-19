# -*- coding: utf-8 -*-
"""Repérage des points d'ancrage dans answer.py avant de câbler les procédures.

Le câblage doit s'insérer là où la recherche est lancée et là où le contexte est
assemblé. Plutôt que de deviner ces endroits, on les fait dire au fichier.
"""
import re

SRC = "/workspace/aiocr/rag/answer.py"
src = open(SRC, encoding="utf-8").read()
lignes = src.split("\n")

print(f"{len(lignes)} lignes\n")
print("— définitions —")
for i, l in enumerate(lignes, 1):
    if re.match(r"\s*(def |class |from |import )", l):
        print(f"{i:5d}  {l.strip()[:96]}")

print("\n— appels de recherche et assemblage du contexte —")
CLES = r"search|hybrid|rank|retrieve|context|prompt|_version_note|collection|COLLECTION"
for i, l in enumerate(lignes, 1):
    if re.search(CLES, l) and not l.strip().startswith("#"):
        print(f"{i:5d}  {l.rstrip()[:110]}")
