# -*- coding: utf-8 -*-
"""Matières juridiques — corpus v3 (une collection par corpus, thème en payload).

Changement d'architecture : le corpus v3 place les 48 thèmes des lois dans une
seule collection (`adala_laws_v4`) et les 6 chambres dans `adala_juris_v4`. Le
filtrage par matière ne se fait donc plus en choisissant des collections mais
sur le champ `folder` du payload.

Comme avant : la matière est PRIORISÉE (bonus de score), pas exclusive — sauf
si l'appelant demande `strict=True`.
"""
from __future__ import annotations

# Collections v3 interrogées par défaut. Les anciennes (laws_penal, …) sont
# conservées comme sauvegarde mais ne sont plus interrogées.
CORPUS_COLLECTIONS = ["adala_laws_v4", "adala_juris_v4", "adala_pmp_v4"]

# matière -> dossiers (payload `folder`) côté lois et côté jurisprudence.
MATIERES: dict[str, dict] = {
    "penal": {
        "ar": "الجنائية", "fr": "Pénal",
        "folders": ["المادة الجنائية", "المادة الأمنية"],
        "chambers": ["الغرفة الجنائية"],
    },
    "commercial": {
        "ar": "التجارية", "fr": "Commercial",
        "folders": ["المادة التجارية", "matiere commercial"],
        "chambers": ["الغرفة التجارية"],
    },
    "civil": {
        "ar": "المدنية", "fr": "Civil",
        "folders": ["المادة المدنية", "المادة العقارية"],
        "chambers": ["الغرفة المدنية"],
    },
    "administratif": {
        "ar": "الإدارية", "fr": "Administratif",
        "folders": ["المادة الإدارية", "التنظيم الهيكلي للوزارة",
                    "مادة اختصاصات وتنظيم القطاعات الحكومية والمؤسساتية",
                    "مادة الجماعات الترابية", "السلطة التنفيذية"],
        "chambers": ["الغرفة الإدارية", "Chambre_4"],
    },
    "famille": {
        "ar": "الأسرة", "fr": "Famille",
        "folders": ["المادة الأسرية"],
        "chambers": ["غرفة الأحوال الشخصية والميراث"],
    },
    "social": {
        "ar": "الشغل", "fr": "Social",
        "folders": ["المادة الاجتماعية", "مؤسسات الأعمال الإجتماعية للقطاعات الحكومية"],
        "chambers": ["الغرفة الاجتماعية"],
    },
    "financier": {
        "ar": "المالية والجبائية", "fr": "Financier / Fiscal",
        "folders": ["المادة المالية", "المادة الجبائية", "المجلس الأعلى للحسابات",
                    "المجلس الاقتصادي والاجتماعي والبيئي"],
        "chambers": [],
    },
    "constitutionnel": {
        "ar": "الدستورية", "fr": "Constitutionnel",
        "folders": ["الدستور", "المحكمة الدستورية", "السلطة التشريعية",
                    "السلطة القضائية", "المادة الإنتخابية", "مادة التنظيم القضائي"],
        "chambers": [],
    },
    "droits_humains": {
        "ar": "حقوق الإنسان", "fr": "Droits humains",
        "folders": ["اتفاقيات حقوق الإنسان", "اتفاقيات جنيف", "اتفاقيات دولية",
                    "اتفاقيات إقليمية",
                    "مؤسسات وهيئات حماية حقوق الإنسان والنهوض بها",
                    "الهيئة الوطنية للنزاهة والوقاية من الرشوة ومحاربتها"],
        "chambers": [],
    },
    "sectoriel": {
        "ar": "قطاعية", "fr": "Sectoriel",
        "folders": ["المادة البيئية", "مادة التربية والتعليم", "النقل عبر الطرق",
                    "مادة التأمين و التقاعد", "المادة السمعية البصرية",
                    "مادة الثقافة والسياحة والتراث", "مادة الفلاحة",
                    "مادة الصيد البحري", "حالة الطوارئ الصحية"],
        "chambers": [],
    },
}

BOOST = 1.35

# Compatibilité v2 : d'anciens appelants lisent MATIERES[k]["collections"].
# En v3 toutes les matières vivent dans les mêmes collections (filtrage par
# `folder`), donc on expose la liste complète.
for _m in MATIERES.values():
    _m.setdefault("collections", CORPUS_COLLECTIONS)


def count_for(matiere: str, store_mod) -> int:
    """Nombre de chunks d'une matière (filtre payload `folder`)."""
    folders = folders_for(matiere)
    if not folders:
        return 0
    try:
        from qdrant_client.http.models import Filter, FieldCondition, MatchAny
        flt = Filter(must=[FieldCondition(key="folder",
                                          match=MatchAny(any=folders))])
        client = store_mod.client()
        available = {c.name for c in client.get_collections().collections}
        total = 0
        for col in CORPUS_COLLECTIONS:
            if col in available:
                total += client.count(col, count_filter=flt, exact=True).count
        return total
    except Exception:
        return 0


def label(key: str, locale: str = "ar") -> str:
    m = MATIERES.get(key or "")
    return m[locale] if m else ("الكل" if locale == "ar" else "Toutes")


def folders_for(matiere: str | None) -> list[str]:
    """Valeurs de `folder` (lois + chambres) pour une matière donnée."""
    m = MATIERES.get(matiere or "")
    if not m:
        return []
    return list(m.get("folders", [])) + list(m.get("chambers", []))


def collections_for(matiere: str | None, strict: bool = False,
                    available: set[str] | None = None) -> list[str] | None:
    """v3 : toutes les collections du corpus sont interrogées ; la matière agit
    par filtre/bonus sur le payload, plus par sélection de collection."""
    cols = [c for c in CORPUS_COLLECTIONS
            if available is None or c in available]
    return cols or None


def payload_filter(matiere: str | None, strict: bool = False):
    """Filtre Qdrant restreignant aux dossiers de la matière (mode strict)."""
    if not strict:
        return None
    folders = folders_for(matiere)
    if not folders:
        return None
    try:
        from qdrant_client.http.models import Filter, FieldCondition, MatchAny
        return Filter(must=[FieldCondition(key="folder",
                                           match=MatchAny(any=folders))])
    except Exception:
        return None


# Un assistant juridique doit fonder sa réponse sur le TEXTE, puis illustrer
# par la jurisprudence. Or le vectoriel remonte volontiers des arrêts (qui
# répètent les mots de la question) au-dessus de l'article qui énonce la règle
# une seule fois — le modèle finit alors par répondre de mémoire.
ARTICLE_BOOST = 1.30      # chunk de loi portant un n° d'article
LAW_BOOST = 1.12          # texte législatif sans n° d'article
COMMENTARY_PENALTY = 0.88 # revues et commentaires doctrinaux


def _doc_boost(h: dict) -> float:
    corpus = h.get("corpus") or ""
    folder = h.get("folder") or ""
    if "مجلة" in folder:
        return COMMENTARY_PENALTY
    if corpus == "jurisprudence":
        return 1.0
    return ARTICLE_BOOST if h.get("article") else LAW_BOOST


def boost_hits(hits: list[dict], matiere: str | None) -> list[dict]:
    """Bonus de score aux résultats dont le dossier relève de la matière, et
    marquage `hors_matiere` pour l'affichage (même contrat qu'en v2).
    Pénalise légèrement les textes OCR signalés comme peu fiables."""
    folders = set(folders_for(matiere))
    has_matiere = bool(folders) and matiere not in (None, "", "all")
    for h in hits:
        s = h.get("score", 0) or 0
        if has_matiere:
            folder = h.get("folder")
            if not folder:
                # Dossier inconnu n'est pas dossier étranger. Deux tiers du
                # corpus lexical n'ont pas de matière renseignée, et toutes les
                # lignes venues de BM25 en sont dépourvues — ce sont pourtant
                # celles qui portent les numéros d'articles exacts. Les traiter
                # comme hors sujet revenait à faire taire les résultats les
                # plus précis dès qu'une matière était choisie.
                h["hors_matiere"] = False
            elif folder in folders:
                h["hors_matiere"] = False
                s *= BOOST
            else:
                h["hors_matiere"] = True
        s *= _doc_boost(h)
        if h.get("ocr_flagged"):
            s *= 0.85
        h["score"] = s
    hits.sort(key=lambda h: h.get("score", 0), reverse=True)
    return hits
