"""
╔══════════════════════════════════════════════════════════════╗
║  DMSI · Adala — Moteur de Recherche Arabe                    ║
║  search/engine.py                                            ║
╚══════════════════════════════════════════════════════════════╝
Description :
    Moteur de recherche intelligent pour textes arabes :
    - Normalisation (tashkeel, hamza, ta marbuta …)
    - Distance d'édition pondérée (lettres similaires)
    - Correction automatique de la requête
    - Suggestions (auto-complétion)
    - Mise en évidence (highlight) des occurrences
"""

import re

# ── Regex ─────────────────────────────────────────────────────────────────
_RE_ARABIC   = re.compile(r'[\u0600-\u06FF\u0750-\u077F]+')
_RE_TASHKEEL = re.compile(r'[\u064B-\u065F\u0670]')

# Lettres "phonétiquement proches" pour la distance pondérée
_SIMILAR: dict[str, str] = {
    'ب': 'تثنيى', 'ت': 'بثنيى', 'ث': 'بتنيى', 'ن': 'بتثيى',
    'ج': 'حخ',    'ح': 'جخ',    'خ': 'جح',
    'د': 'ذ',     'ذ': 'د',
    'ر': 'ز',     'ز': 'ر',
    'س': 'ش',     'ش': 'س',
    'ص': 'ض',     'ض': 'ص',
    'ط': 'ظ',     'ظ': 'ط',
    'ع': 'غ',     'غ': 'ع',
    'ف': 'ق',     'ق': 'ف',
    'ك': 'ل',     'ل': 'ك',
    'ه': 'ة',     'ة': 'ه',
    'و': 'ؤ',     'ؤ': 'و',
    'ي': 'ئى',   'ى': 'يئ',   'ئ': 'يى',
    'ا': 'أإآ',   'أ': 'اإآ',  'إ': 'اأآ', 'آ': 'اأإ',
    'م': 'ن',
}


# ─────────────────────────────────────────────────────────────────────────
#  Normalisation
# ─────────────────────────────────────────────────────────────────────────

def normalize_arabic(text: str) -> str:
    """
    Normalise un texte arabe :
    - Supprime le tashkeel
    - Unifie les formes de الف / ياء / تاء مربوطة / همزة الوصل
    """
    text = _RE_TASHKEEL.sub('', text)
    text = re.sub(r'[إأآا]', 'ا', text)
    text = re.sub(r'[ىي]',   'ي', text)
    text = re.sub(r'ة',      'ه', text)
    text = re.sub(r'ؤ',      'و', text)
    text = re.sub(r'ئ',      'ي', text)
    return text


# ─────────────────────────────────────────────────────────────────────────
#  Distance d'édition pondérée
# ─────────────────────────────────────────────────────────────────────────

def arabic_edit_distance(a: str, b: str) -> float:
    """
    Distance de Levenshtein avec coût réduit (0.5) pour les lettres similaires.
    Retourne 999 si les longueurs diffèrent de plus de 3.
    """
    la, lb = len(a), len(b)
    if abs(la - lb) > 3:
        return 999.0

    dp = [[0.0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        dp[i][0] = float(i)
    for j in range(lb + 1):
        dp[0][j] = float(j)

    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                cost = 0.5 if b[j - 1] in _SIMILAR.get(a[i - 1], '') else 1.0
                dp[i][j] = min(
                    dp[i - 1][j] + 1,
                    dp[i][j - 1] + 1,
                    dp[i - 1][j - 1] + cost,
                )
    return dp[la][lb]


# ─────────────────────────────────────────────────────────────────────────
#  Mise en évidence (highlight)
# ─────────────────────────────────────────────────────────────────────────

def highlight_matches(text: str, query: str) -> str:
    """
    Entoure chaque occurrence des mots de la requête dans le texte
    avec une balise <mark>.
    """
    for qw in query.split():
        nqw = normalize_arabic(qw)
        for tw in set(_RE_ARABIC.findall(text)):
            if normalize_arabic(tw) == nqw:
                text = text.replace(
                    tw,
                    f'<mark style="background:#fde68a;padding:1px 5px;'
                    f'border-radius:3px;font-weight:700;color:#0b192c;">'
                    f'{tw}</mark>',
                    1,
                )
    return text
