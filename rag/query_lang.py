# -*- coding: utf-8 -*-
"""Requêtes non arabes : traduction vers l'arabe juridique avant recherche.

Le corpus est en arabe et la recherche hybride l'est aussi : le tokenizer BM25
de `rag/hybrid.py` ne reconnaît que [؀-ۿ] et les chiffres, donc une question en
français produit ZÉRO token lexical, et la seule similarité vectorielle
cross-lingue ne suffit pas sur la terminologie juridique (« grâce royale »
n'atteint pas « العفو الملكي »).

On traduit donc la question en arabe pour la RECHERCHE uniquement ; la langue
de la RÉPONSE reste celle de l'utilisateur.
"""
from __future__ import annotations

import re

_AR = re.compile(r"[؀-ۿ]")
_LAT = re.compile(r"[A-Za-zÀ-ÿ]")

TRANSLATE_PROMPT = (
    "أنت مترجم قانوني. ترجم السؤال التالي إلى العربية القانونية المغربية "
    "الرسمية، باستعمال المصطلحات المستعملة في النصوص التشريعية المغربية "
    "(مثال: grâce royale ← العفو الملكي، procureur du Roi ← وكيل الملك، "
    "pourvoi en cassation ← الطعن بالنقض). أخرج الترجمة فقط، بدون شرح."
)


def detect_lang(text: str) -> str:
    """'ar' si la question est majoritairement arabe, sinon 'lat'."""
    t = text or ""
    ar = len(_AR.findall(t))
    lat = len(_LAT.findall(t))
    if ar == 0 and lat == 0:
        return "ar"
    return "ar" if ar >= lat else "lat"


def needs_translation(text: str) -> bool:
    return detect_lang(text) == "lat" and len(_LAT.findall(text or "")) >= 4


def to_arabic(question: str, llm) -> str:
    """Traduit pour la recherche. `llm` = callable(messages) -> str.
    En cas d'échec on renvoie la question d'origine (jamais d'exception)."""
    try:
        out = llm([{"role": "system", "content": TRANSLATE_PROMPT},
                   {"role": "user", "content": question}])
        out = (out or "").strip().strip('"').strip()
        # garde-fou : la traduction doit être arabe et non vide
        if out and _AR.search(out):
            return out
    except Exception:
        pass
    return question


def search_query_for(question: str, llm) -> tuple[str, str | None]:
    """(requête_de_recherche, traduction_ou_None)."""
    if not needs_translation(question):
        return question, None
    ar = to_arabic(question, llm)
    if ar and ar != question:
        # on concatène : l'arabe porte la recherche, l'original aide le
        # vectoriel si un nom propre latin figure dans le texte.
        return ar, ar
    return question, None


def answer_language_rule(question: str) -> str:
    """Consigne de langue explicite ajoutée au prompt système."""
    if detect_lang(question) == "lat":
        return ("\n\n## RAPPEL DE LANGUE (impératif pour cette requête)\n"
                "La question est posée en français : rédige TOUTE ta réponse "
                "en français. Garde les citations et les noms officiels des "
                "textes en arabe, suivis si utile d'une traduction française.")
    return ("\n\n## تذكير باللغة (ملزم لهذا الطلب)\n"
            "السؤال بالعربية: اكتب الجواب كله بالعربية الفصحى.")
