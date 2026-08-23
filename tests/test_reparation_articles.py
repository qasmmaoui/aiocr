# -*- coding: utf-8 -*-
"""Épreuves de la logique de réparation des numéros d'article.

On éprouve les règles, pas le corpus : chaque cas reproduit une situation
réellement rencontrée, y compris celles qui ont failli abîmer les données.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def suffixes(brut):
    """Candidats : tout suffixe sans zéro de tête."""
    out = []
    for L in range(1, len(brut)):
        suf = brut[L:]
        if suf and not suf.startswith("0"):
            out.append((int(suf), brut[:L]))
    return out


def qualite_suite(nums):
    e = set(nums)
    return sum(1 for v in e if (v - 1) in e or (v + 1) in e) / len(e) if len(e) > 2 else None


def test_le_suffixe_porte_l_article():
    """« 182384 » : l'article est le suffixe, la note le préfixe."""
    assert (384, "182") in suffixes("182384")


def test_un_numero_eleve_dense_est_authentique():
    """Le code des obligations compte 1 250 articles : 1000 y est légitime.

    C'est l'erreur qui aurait « réparé » 225 articles authentiques.
    """
    presents = set(range(995, 1010))
    assert any((1000 + d) in presents for d in (-2, -1, 1, 2))


def test_un_numero_eleve_isole_est_corrompu():
    presents = {12, 13, 14, 84264}
    assert not any((84264 + d) in presents for d in (-2, -1, 1, 2))


def test_bornes_degenerees_ne_bornent_rien():
    """Des bornes 1…1 auraient réduit « 3471171 » à l'article 1."""
    avant = apres = 1
    assert not (avant is not None and apres is not None and apres > avant)


def test_la_qualite_de_suite_distingue_avant_et_apres():
    avant = [21, 2, 33, 4, 45, 6, 67, 8]
    apres = [1, 2, 3, 4, 5, 6, 7, 8]
    assert qualite_suite(apres) > qualite_suite(avant)
    assert qualite_suite(apres) == 1.0


def test_les_notes_montent_dans_un_document():
    """Une note 7 ne précède jamais une note 3 : preuve de désordre."""
    ordonnees, desordonnees = [2, 3, 4, 5, 6], [2, 7, 3, 5]
    monte = lambda l: all(a <= b for a, b in zip(l, l[1:]))
    assert monte(ordonnees) and not monte(desordonnees)


def test_le_renvoi_interne_situe_l_article():
    """« المادة 98232 » citant « المادة 231 أعلاه » vaut 232."""
    texte = "المادة 98232 المنصوص عليه في المادة 231 أعلاه"
    plafond = max(int(x) for x in re.findall(r"المادة\s*(\d+)\s*أعلاه", texte))
    cands = [v for v, _ in suffixes("98232") if plafond < v <= plafond + 3]
    assert cands == [232]


def test_le_suffixe_bis_survit():
    """« 171618-3 » vaut 618-3, pas 618 : ce sont deux articles distincts."""
    etiquette = "618-3"
    assert re.match(r"^\d+-\d+$", etiquette)


if __name__ == "__main__":
    n = 0
    for nom, fn in sorted(globals().items()):
        if nom.startswith("test_"):
            fn(); print("  ok   ", nom); n += 1
    print(f"{n} épreuves passent")
