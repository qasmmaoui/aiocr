# -*- coding: utf-8 -*-
"""Le filtrage par matière ne doit pas faire taire ce qu'il ne connaît pas."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rag.matieres import boost_hits, BOOST          # noqa: E402


def _hits():
    return [
        {"nom": "dans la matière",  "folder": "المادة المدنية",  "score": 1.0},
        {"nom": "sans dossier",     "folder": None,              "score": 1.0},
        {"nom": "autre matière",    "folder": "المادة الجنائية", "score": 1.0},
    ]


def test_le_dossier_inconnu_reste_neutre():
    """Une ligne BM25 n'a pas de dossier : elle ne doit pas être écartée."""
    par_nom = {h["nom"]: h for h in boost_hits(_hits(), "civil")}
    assert par_nom["sans dossier"]["hors_matiere"] is False
    assert par_nom["sans dossier"]["score"] > 0


def test_la_matiere_demandee_est_favorisee():
    par_nom = {h["nom"]: h for h in boost_hits(_hits(), "civil")}
    assert par_nom["dans la matière"]["score"] > par_nom["sans dossier"]["score"]


def test_une_autre_matiere_est_signalee():
    par_nom = {h["nom"]: h for h in boost_hits(_hits(), "civil")}
    assert par_nom["autre matière"]["hors_matiere"] is True


def test_sans_matiere_personne_n_est_ecarte():
    for h in boost_hits(_hits(), None):
        assert not h.get("hors_matiere")


if __name__ == "__main__":
    ok = 0
    for nom, fn in sorted(globals().items()):
        if nom.startswith("test_"):
            fn(); print("  ok   ", nom); ok += 1
    print(f"{ok} épreuves passent")
