# -*- coding: utf-8 -*-
"""Volet « procédures » du moteur : reconnaissance d'intention et avertissement.

Trois apports, tous destinés à ce que l'avocat ne suive jamais une démarche
caduque sans le savoir :

1. reconnaître qu'une question porte sur la MARCHE À SUIVRE et non sur le droit
   applicable — « كيف أشتكي » n'appelle pas le même corpus que « ما هو أجل » ;
2. avertir NOMMÉMENT quand la fiche s'appuie sur un texte abrogé : citer les
   articles visés vaut mieux qu'un « des choses ont changé » qu'on finit par
   ignorer ;
3. rappeler le régime transitoire de l'article 643, qui dit précisément QUAND
   l'ancien code continue de s'appliquer. Sans lui, l'avertissement laisserait
   croire que le guide est entièrement caduc — il ne l'est pas.
"""
import json
import re

COLLECTION = "adala_procedures"
# En deçà, aucune fiche ne répond vraiment : mieux vaut ne rien servir
# que d'imposer une marche à suivre étrangère à la question.
PLANCHER = 0.45

# Le guide écrit tantôt « الفصل », tantôt « الفصول » selon le nombre.
# On regroupe sur la famille et on choisit la forme à l'affichage,
# sinon la même fiche apparaît deux fois et « الفصل » précède
# une liste de plusieurs numéros.
_FAMILLE = {"الفصل": "فصل", "الفصول": "فصل",
            "المادة": "مادة", "المواد": "مادة",
            "الفقرة": "فقرة", "الفقرات": "فقرة"}
_LIBELLE = {"فصل": ("الفصل", "الفصول"),
            "مادة": ("المادة", "المواد"),
            "فقرة": ("الفقرة", "الفقرات")}

# Tournures qui demandent une marche à suivre plutôt qu'une règle de droit.
_INTENTION = re.compile(
    r"كيف|ما\s*هي\s*(?:المسطرة|الإجراءات|الخطوات)|مسطرة|إجراءات|خطوات|"
    r"أين\s*(?:أضع|أودع|أقدم)|كيفية|طريقة|"
    r"comment|procédure|démarche|étapes|où\s+déposer|"
    r"how\s+to|procedure|steps|where\s+to\s+file",
    re.IGNORECASE)

# Régime transitoire du nouveau code — la règle qui dit lequel des deux
# régimes s'applique à un dossier donné.
TRANSITOIRE = (
    "المادة 643 من قانون المسطرة المدنية 58.25: يدخل هذا القانون حيز التنفيذ "
    "بعد ستة أشهر من نشره. تظل قواعد الاختصاص السابقة سارية على القضايا "
    "الجاهزة للحكم؛ ويستمر العمل بالمقتضيات المتعلقة بالآجال متى بدأ سريانها "
    "قبل دخوله حيز التنفيذ؛ ولا تطبق مقتضيات طرق الطعن الجديدة على الأحكام "
    "الصادرة قبل ذلك التاريخ.")


def veut_une_procedure(question: str) -> bool:
    return bool(_INTENTION.search(question or ""))


def _renvois(hit: dict) -> list[dict]:
    brut = hit.get("renvois")
    if isinstance(brut, str):
        try:
            return json.loads(brut)
        except Exception:
            return []
    return brut or []


def avertissement(hits: list[dict]) -> str:
    """Avertissement nommé, construit à partir des fiches réellement servies.

    On ne dit pas « le guide est ancien » : on dit quelle fiche, quels articles,
    quel texte les a remplacés, et à quelles conditions l'ancien régime survit.
    """
    # Une fiche cite souvent plusieurs groupes d'articles : on les réunit sous
    # son seul intitulé, sinon l'avertissement répète quatre fois la même fiche.
    # Clé (fiche, type de renvoi) : le guide cite tantôt des فصول, tantôt des
    # مواد. Écrire « الفصول » en dur ferait citer à faux l'un pour l'autre.
    par_fiche: dict[tuple[str, str, str], list[str]] = {}
    for h in hits:
        if h.get("type") != "procedure":
            continue
        titre = h.get("titre", "")
        for r in _renvois(h):
            if r.get("etat") != "abroge":
                continue
            fam = _FAMILLE.get(r.get("type", ""), r.get("type", ""))
            cle = (titre, fam, r.get("loi", ""))
            par_fiche.setdefault(cle, [])
            for a in r.get("articles", []):
                if a not in par_fiche[cle]:
                    par_fiche[cle].append(a)
    if not par_fiche:
        return ""
    morceaux = []
    for (titre, fam, loi), arts in par_fiche.items():
        if not arts:
            continue
        nums = sorted(arts, key=int)[:10]
        sing, plur = _LIBELLE.get(fam, (fam, fam))
        label = sing if len(nums) == 1 else plur
        morceaux.append(f"« {titre} » ({label} {'، '.join(nums)} من {loi})")
    liste = " ؛ ".join(morceaux)
    return (
        "\n[تنبيه إلزامي — نصوص متغيرة]\n"
        f"المساطر التالية مستمدة من دليل المساطر لسنة 2024، وتستند إلى نصوص "
        f"نُسخت: {liste}. النص الناسخ هو القانون رقم 58.25 المتعلق بالمسطرة "
        f"المدنية (ظهير 1.26.07 بتاريخ 11 فبراير 2026)، وهو يعتمد ترقيما "
        f"بالمواد لا بالفصول.\n"
        f"{TRANSITOIRE}\n"
        "نبّه المستعمل وجوبا: عليه التحقق من النظام المطبّق على ملفه قبل "
        "اتباع هذه الخطوات، ولا تقدّم الإحالات القديمة على أنها سارية.")


def bloc_procedures(hits: list[dict]) -> str:
    """Les fiches servies au moteur, en étapes plutôt qu'en prose."""
    fiches = [h for h in hits if h.get("type") == "procedure"]
    if not fiches:
        return ""
    out = ["[مساطر — دليل وزارة العدل]"]
    for h in fiches:
        out.append(h.get("text", ""))
        out.append("")
    return "\n".join(out) + avertissement(hits)


def chercher(question: str, limit: int = 3) -> list[dict]:
    """Fiches de procédure les plus proches de la question.

    Recherche purement vectorielle : une fiche est indexée d'un seul tenant, il
    n'y a donc pas d'ancrage d'article à faire jouer comme pour les lois. On en
    ramène peu — trois marches à suivre concurrentes noieraient la bonne.
    """
    from rag import store
    from rag.embeddings import embed

    if not store.exists(COLLECTION):
        return []
    hits = store.search(COLLECTION, embed(question), limit=limit)
    if not hits:
        return []
    # Une fiche nettement moins proche que la meilleure n'est pas une variante,
    # c'est un hors-sujet : servie, elle ferait porter l'avertissement « texte
    # abrogé » sur une procédure que l'utilisateur n'a pas demandée.
    meilleur = max(h.get("score", 0) for h in hits)
    hits = [h for h in hits
            if h.get("score", 0) >= max(meilleur * 0.95, PLANCHER)]
    for h in hits:
        h["type"] = "procedure"
    return hits


def sources(hits: list[dict]) -> list[dict]:
    """Fiches servies, présentées comme sources à part entière.

    L'avocat doit pouvoir remonter à la page du guide : une marche à suivre
    sans référence n'est pas vérifiable.
    """
    out = []
    for h in hits:
        if h.get("type") != "procedure":
            continue
        out.append({
            "law": h.get("law", ""),
            "file": h.get("file", ""),
            "article": h.get("titre", ""),
            "chunk": h.get("page"),
            "page": h.get("page"),
            "score": round(float(h.get("score", 0)), 3),
            "excerpt": (h.get("text", "") or "")[:400],
            "kind": "procedure",
            "kind_ar": "مسطرة إدارية",
            "kind_fr": "Procédure",
            "pdf": h.get("pdf"),
            "folder": h.get("folder"),
        })
    return out
