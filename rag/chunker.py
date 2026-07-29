"""
Découpage des textes juridiques en passages, centré sur l'ARTICLE.

Règles :
- On ne coupe QUE sur un vrai en-tête d'article (« المادة 41 » / « الفصل 393 »),
  jamais sur un renvoi croisé (« المادة 316 من مدونة التجارة ») — c'est ce qui
  faisait citer le mauvais numéro.
- Chaque article devient un passage ; s'il est trop long, on le découpe en
  fenêtres MAIS on préfixe chaque morceau par l'en-tête d'article, pour que le
  numéro d'article reste toujours attaché au texte.
- chunk_text() renvoie une liste de dicts {"text", "article"} : le numéro
  d'article est stocké en métadonnée pour des citations exactes.
"""
import re

# Chiffres latins ou arabes-indiens.
_D = r'[0-9٠-٩]'
# Numéro d'article éventuellement composé : 41 / 41-1 / 1-41.
_NUM = rf'{_D}+(?:\s*[-–]\s*{_D}+)?'
# Marqueur d'article.
_MARK = re.compile(rf'(الماد[ةه]|الفصل)\s*[:\-]?\s*({_NUM})')

MAX_CHARS = 1400
OVERLAP = 200
MIN_CHARS = 40


def _is_real_header(text: str, m: re.Match) -> bool:
    """Vrai en-tête d'article, PAS un renvoi « المادة N من ... »."""
    tail = text[m.end():m.end() + 8].lstrip()
    return not tail.startswith("من")


def _norm_num(num: str) -> str:
    return re.sub(r'\s+', '', num)


def _emit(out: list, seg: str, article, header: str = "") -> None:
    seg = seg.strip()
    if len(seg) < MIN_CHARS:
        return
    if len(seg) <= MAX_CHARS:
        out.append({"text": seg, "article": article})
        return
    step = MAX_CHARS - OVERLAP
    first = True
    for i in range(0, len(seg), step):
        w = seg[i:i + MAX_CHARS].strip()
        if len(w) < MIN_CHARS:
            continue
        if not first and header:
            w = f"{header} (تابع): {w}"     # garde le numéro d'article sur les suites
        out.append({"text": w, "article": article})
        first = False


def chunk_text(text: str) -> list[dict]:
    text = re.sub(r'[ \t]+', ' ', (text or '')).strip()
    if len(text) < MIN_CHARS:
        return []

    heads = [
        (m.start(), m.group(0).strip(), _norm_num(m.group(2)))
        for m in _MARK.finditer(text)
        if _is_real_header(text, m)
    ]

    out: list[dict] = []
    if len(heads) >= 2:
        if heads[0][0] > 0:                         # préambule avant le 1er article
            _emit(out, text[:heads[0][0]], None)
        for i, (pos, hdr, num) in enumerate(heads):
            end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
            _emit(out, text[pos:end], num, hdr)
    else:
        # pas de structure d'articles nette -> fenêtres simples
        _emit(out, text, None)

    return [c for c in out if len(c["text"]) >= MIN_CHARS]
