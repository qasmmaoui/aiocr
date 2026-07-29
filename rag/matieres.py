# -*- coding: utf-8 -*-
"""Matières juridiques : filtrage de la recherche par domaine.

Le droit ne se cloisonne pas (un « شيك بدون مؤونة » relève du commercial ET
du pénal). On ne coupe donc jamais brutalement : la matière choisie est
PRIORISÉE (bonus de score), les autres restent visibles si elles sont
nettement meilleures — et l'appelant peut demander le mode strict.
"""
from __future__ import annotations

# matière -> collections Qdrant. Les collections absentes sont ignorées.
MATIERES: dict[str, dict] = {
    "penal": {
        "ar": "الجنائية", "fr": "Pénal",
        "collections": ["laws_penal_ocr", "laws_penal_v2", "laws_penal"],
    },
    "commercial": {
        "ar": "التجارية", "fr": "Commercial",
        "collections": ["laws_commercial"],
    },
    "civil": {
        "ar": "المدنية", "fr": "Civil",
        "collections": ["laws_civil"],
    },
    "administratif": {
        "ar": "الإدارية", "fr": "Administratif",
        "collections": ["laws_administratif"],
    },
    "famille": {
        "ar": "الأسرة", "fr": "Famille",
        "collections": ["laws_famille"],
    },
    "social": {
        "ar": "الشغل", "fr": "Social",
        "collections": ["laws_social"],
    },
}

# Bonus appliqué au score des chunks de la matière choisie (mode « priorité »).
BOOST = 1.35


def label(key: str, locale: str = "ar") -> str:
    m = MATIERES.get(key or "")
    return m[locale] if m else ("الكل" if locale == "ar" else "Toutes")


def collections_for(matiere: str | None, strict: bool = False,
                    available: set[str] | None = None) -> list[str] | None:
    """Collections à interroger. None = toutes (comportement par défaut).
    En mode non strict on interroge tout : le tri se fait ensuite par bonus."""
    if not matiere or matiere == "all":
        return None
    m = MATIERES.get(matiere)
    if not m:
        return None
    cols = [c for c in m["collections"]
            if available is None or c in available]
    if strict:
        return cols or None
    return None                    # non strict : tout interroger, puis pondérer


def boost_hits(hits: list[dict], matiere: str | None) -> list[dict]:
    """Repondère les résultats en faveur de la matière choisie, sans exclure
    les autres. Marque `hors_matiere` pour l'affichage côté client."""
    if not matiere or matiere == "all" or matiere not in MATIERES:
        return hits
    wanted = set(MATIERES[matiere]["collections"])
    for h in hits:
        inside = h.get("collection") in wanted
        h["hors_matiere"] = not inside
        if inside:
            h["score"] = h.get("score", 0) * BOOST
    hits.sort(key=lambda h: h.get("score", 0), reverse=True)
    return hits
