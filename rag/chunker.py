"""
Découpage des textes juridiques en passages.
Priorité aux frontières d'articles (المادة / الفصل) ; sinon fenêtres glissantes.
"""
import re

_ARTICLE = re.compile(r'(?:الماد[ةه]|الفصل)\s*[:\-]?\s*\d+')
MAX_CHARS = 1200
OVERLAP   = 150
MIN_CHARS = 40


def chunk_text(text: str) -> list[str]:
    text = re.sub(r'[ \t]+', ' ', (text or '')).strip()
    if len(text) < MIN_CHARS:
        return []

    marks = [m.start() for m in _ARTICLE.finditer(text)]
    if len(marks) >= 3:
        if marks[0] != 0:
            marks = [0] + marks
        segs = [text[marks[i]:marks[i + 1]] for i in range(len(marks) - 1)]
        segs.append(text[marks[-1]:])
    else:
        segs = [text]

    out: list[str] = []
    for seg in segs:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) <= MAX_CHARS:
            out.append(seg)
        else:
            step = MAX_CHARS - OVERLAP
            for i in range(0, len(seg), step):
                w = seg[i:i + MAX_CHARS].strip()
                if len(w) >= MIN_CHARS:
                    out.append(w)
    return [c for c in out if len(c) >= MIN_CHARS]
