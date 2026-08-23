# -*- coding: utf-8 -*-
"""Le moteur rattache-t-il chaque article au bon texte ?

Cas d'espèce mesuré le 21 août : le moteur avait servi le الفصل 31 du code de
procédure civile de 1974, et la réponse l'a présenté comme « الفصل 31 من قانون
الجنسية المغربية » — nom emprunté à un passage voisin du contexte. La règle 2
du prompt système l'interdit pourtant explicitement ; l'interdiction n'a pas
suffi.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import re                                                    # noqa: E402
import importlib.util                                        # noqa: E402

# On charge la fonction sans démarrer tout le moteur (pas d'Ollama, pas de Qdrant).
_src = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "rag", "answer.py"), encoding="utf-8").read()
_deb = _src.index("_ATTRIB_RE = re.compile")
_fin = _src.index("def _bandeau_version")
_ns = {"re": re}
exec(_src[_deb:_fin], _ns)
attribution = _ns["_attribution_douteuse"]

CPC = {"article": "الفصل 31", "law": "ظهير شريف بمثابة قانون رقم 1.74.447 "
                                     "بالمصادقة على قانون المسطرة المدنية"}
NAT = {"article": "الفصل 15", "law": "ظهير شريف رقم 1.58.250 بسن قانون "
                                     "الجنسية المغربية"}


def test_la_faute_reelle_est_detectee():
    rep = ("ترفع الدعوى بمقال مكتوب (الفصل 31 من قانون الجنسية المغربية).")
    assert "تحقق من الإسناد" in attribution(rep, [CPC, NAT])


def test_une_attribution_correcte_ne_declenche_rien():
    rep = "ترفع الدعوى بمقال مكتوب (الفصل 31 من قانون المسطرة المدنية)."
    assert attribution(rep, [CPC, NAT]) == ""


def test_un_article_non_servi_est_ignore():
    """On ne juge que ce qu'on a fourni : le reste ne nous regarde pas."""
    rep = "راجع الفصل 999 من مدونة التجارة."
    assert attribution(rep, [CPC, NAT]) == ""


def test_sans_source_aucun_jugement():
    assert attribution("الفصل 31 من أي قانون", []) == ""


def test_les_mots_vides_ne_font_pas_correspondance():
    """« قانون » seul ne prouve rien : deux lois le portent."""
    rep = "الفصل 31 من القانون رقم 12.34."
    assert "تحقق من الإسناد" in attribution(rep, [CPC])


if __name__ == "__main__":
    n = 0
    for nom, fn in sorted(globals().items()):
        if nom.startswith("test_"):
            fn(); print("  ok   ", nom); n += 1
    print(f"{n} épreuves passent")
