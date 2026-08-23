# -*- coding: utf-8 -*-
"""La réponse écarte-t-elle le juge que les textes servis imposent ?

Cas mesuré : à « l'expulsion nécessite-t-elle un jugement ? », le moteur a
répondu « non, pas toujours » en s'appuyant sur un article qui dispense
d'INDEMNITÉ, pas de jugement. Deux dispositions du même corpus donnaient
pourtant compétence à la juridiction.

La consigne du prompt le lui interdit déjà ; il l'a fait quand même. D'où ce
contrôle après coup — une expulsion sans titre exécutoire est une voie de fait.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_src = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "rag", "answer.py"), encoding="utf-8").read()
_deb = _src.index("_NIE_LE_JUGE = re.compile")
_fin = _src.index("def _attribution_douteuse")
_ns = {"re": re}
exec(_src[_deb:_fin], _ns)
verifie = _ns["_nie_la_voie_judiciaire"]

ART56 = {"article": "المادة 56", "law": "قانون الكراء",
         "text": "يمكن للمكري ان يطلب من المحكمة فسخ عقد الكراء وإفراغ المكتري"}
ART8 = {"article": "المادة 8", "law": "قانون الكراء",
        "text": "لا يلزم المكري باداء اي تعويض للمكتري مقابل الإفراغ"}


def test_la_negation_fautive_est_signalee():
    rep = "لا، الإفراغ لا يحتاج دائماً إلى حكم قضائي."
    assert "تناقض محتمل" in verifie(rep, [ART56, ART8])


def test_une_reponse_correcte_ne_declenche_rien():
    rep = "نعم، يجب اللجوء إلى المحكمة للحصول على حكم بالإفراغ."
    assert verifie(rep, [ART56, ART8]) == ""


def test_sans_texte_attribuant_competence_pas_d_alerte():
    """On ne crie au loup que si les sources contredisent réellement."""
    rep = "لا، الإفراغ لا يحتاج إلى حكم قضائي."
    assert verifie(rep, [ART8]) == ""


ART17 = {"article": "المادة 17", "law": "قانون الكراء",
         "text": "المادة 17 يختص رئيس المحكمة في الطلب الرامي الى الإفراغ "
                 "وتحديد قيمة التعويض"}


def test_la_competence_du_president_est_reconnue():
    """« يختص رئيس المحكمة » : l'énoncé le plus net, manqué par la v1."""
    rep = "لا، الإفراغ لا يحتاج دائماً إلى حكم قضائي."
    assert "تناقض محتمل" in verifie(rep, [ART17])


def test_l_article_cite_est_nomme():
    rep = "الإفراغ يتم بدون حكم قضائي."
    out = verifie(rep, [ART56])
    assert "المادة 56" in out


if __name__ == "__main__":
    n = 0
    for nom, fn in sorted(globals().items()):
        if nom.startswith("test_"):
            fn(); print("  ok   ", nom); n += 1
    print(f"{n} épreuves passent")
