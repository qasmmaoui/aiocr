# -*- coding: utf-8 -*-
"""Un cadre légal qu'on ne sait pas retrouver ne peut pas être dit applicable.

Cas mesuré : la fiche « الإفراغات » du guide donne pour cadre un « ظهير 1980 »
qui n'est PAS dans le corpus — il a été remplacé par la loi 67.12. Le
mécanisme de datation ne pouvait rien : il lit le statut des documents
ingérés, or celui-ci n'y est pas.

La règle est vérifiable et vaut pour toute matière : on ne tient pas de liste
de textes périmés à la main. C'est la donnée qui décide.
"""
import os
import re
import sys
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

_src = open(os.path.join(RACINE, "rag", "procedures.py"), encoding="utf-8").read()
_ns = {"re": re}
exec(_src[_src.index("_TEXTE_CITE = re.compile"):_src.index("def avertissement")], _ns)


def _fonds(*noms):
    """Simule l'index chargé, avec les seuls textes qu'on veut y voir."""
    faux = types.ModuleType("rag.hybrid")
    faux.get_index = lambda: types.SimpleNamespace(
        docs=[{"law": n, "file": ""} for n in noms])
    sys.modules["rag.hybrid"] = faux
    return _ns["references_invérifiables"]


FONDS = ("القانون رقم 67.12 المتعلق بالمحلات المعدة للسكنى أو للاستعمال المهني",
         "ظهير شريف بمثابة قانون رقم 1.74.447 قانون المسطرة المدنية")

FICHE_ABSENTE = {"type": "procedure", "titre": "الإفراغات",
                 "cadre_legal": "ظهير 1980 المتعلق بالمحلات السكنية."}
FICHE_PRESENTE = {"type": "procedure", "titre": "كراء",
                  "cadre_legal": "القانون رقم 67.12 المتعلق بالمحلات المعدة للسكنى."}


def test_le_texte_absent_du_fonds_est_signale():
    assert _fonds(*FONDS)([FICHE_ABSENTE])


def test_un_mot_commun_ne_suffit_pas_a_conclure_qu_on_l_a():
    """« بالمحلات » figure dans les deux : ça ne prouve rien."""
    out = _fonds(*FONDS)([FICHE_ABSENTE])
    assert out and "1980" in out[0][1]


def test_le_texte_present_ne_declenche_rien():
    assert _fonds(*FONDS)([FICHE_PRESENTE]) == []


def test_le_numero_suffit_a_reconnaitre():
    f = {"type": "procedure", "titre": "x", "cadre_legal": "القانون رقم 67.12."}
    assert _fonds(*FONDS)([f]) == []


def test_un_article_de_loi_n_est_pas_une_fiche():
    loi = {"type": "loi", "law": "ظهير 1980", "cadre_legal": "ظهير 1980"}
    assert _fonds(*FONDS)([loi]) == []


def test_sans_index_on_n_accuse_personne():
    faux = types.ModuleType("rag.hybrid")
    faux.get_index = lambda: None
    sys.modules["rag.hybrid"] = faux
    assert _ns["references_invérifiables"]([FICHE_ABSENTE]) == []


if __name__ == "__main__":
    n = 0
    for nom, fn in sorted(globals().items()):
        if nom.startswith("test_"):
            fn(); print("  ok   ", nom); n += 1
    print(f"{n} épreuves passent")
