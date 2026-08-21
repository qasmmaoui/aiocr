# -*- coding: utf-8 -*-
"""Contrôle de fumée : le moteur répond-il encore ?

Écrit après un incident : `FieldCondition(key=disabled, …)` — un identifiant
nu au lieu d'une chaîne — levait un NameError à chaque appel de `store.search`,
donc sur le chemin principal de `search_laws`, sans garde autour. Toute
question partait en erreur, et personne ne l'a su pendant plusieurs jours.

Trois vérifications, de la plus basse à la plus haute :
  1. la recherche vectorielle rend des résultats ;
  2. l'ancrage retrouve un article cité par son numéro ;
  3. le corpus contient bien les textes de référence attendus.

Aucun appel au modèle de langage : on éprouve la récupération, qui est ce qui
casse en silence. À lancer après chaque démarrage du pod.
"""
import sys

ATTENDUS = [
    ("الفصل 540 من القانون الجنائي", "540"),
    ("أجل استئناف الأحكام في القضايا المدنية", None),
    ("مسطرة الصلح", None),
]


def principal() -> int:
    from rag.search_laws import search_laws

    echecs = []
    for question, article in ATTENDUS:
        try:
            hits = search_laws(question, limit=6)
        except Exception as e:                       # noqa: BLE001
            echecs.append(f"« {question[:40]} » : la recherche a levé {e!r}")
            continue
        if not hits:
            echecs.append(f"« {question[:40]} » : aucun résultat")
            continue
        if not any((h.get("text") or "").strip() for h in hits):
            echecs.append(f"« {question[:40]} » : résultats sans texte")
            continue
        if article:
            nums = {str(h.get("article") or "") for h in hits}
            if not any(article in n for n in nums):
                echecs.append(
                    f"« {question[:40]} » : l'article {article} n'est pas "
                    f"remonté (obtenus : {sorted(n for n in nums if n)[:5]})")
        print(f"  ok    {question[:46]:48s} {len(hits)} résultats")

    if echecs:
        print("\nÉCHECS :")
        for e in echecs:
            print("  ✗", e)
        return 1
    print("\nle moteur de recherche répond correctement")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
