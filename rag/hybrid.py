# -*- coding: utf-8 -*-
"""Recherche hybride : BM25 lexical + vecteurs, fusionnés par RRF.

Pourquoi : les scores vectoriels de bge-m3 sont très resserrés — une question
hors sujet (« prix des tomates ») obtient 0,44 contre 0,59 pour une vraie
question juridique. Impossible de trancher au seuil. Surtout, le vectoriel
ne retrouve PAS les références exactes (« المادة 41-1 », « الفصل 510 »,
« 2.14.652 ») qui sont le cœur du travail juridique.

BM25 comble exactement ces deux trous : nul sur le hors-sujet, excellent sur
les numéros et le vocabulaire littéral. La fusion RRF (Reciprocal Rank Fusion)
combine les deux sans avoir à calibrer des échelles de scores incomparables.

Aucune dépendance externe : BM25 est implémenté ici (12 k chunks -> ~50 ms).
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict

_DIAC = re.compile(r"[ً-ٰٟـ]")
_TOKEN = re.compile(r"[؀-ۿ]+|[0-9]+(?:[./-][0-9]+)*")
# mots-outils arabes : présents partout, ils ne discriminent rien
_STOP = {
    "من", "في", "على", "الى", "إلى", "عن", "مع", "هذا", "هذه", "ذلك", "التي",
    "الذي", "او", "أو", "و", "ما", "لا", "ان", "أن", "إن", "كل", "بين", "قد",
    "كان", "يكون", "غير", "عند", "بعد", "قبل", "حسب", "وفق", "هو", "هي",
}


def norm(s: str) -> str:
    s = _DIAC.sub("", s or "")
    return (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
             .replace("ٱ", "ا").replace("ى", "ي").replace("ة", "ه")
             .replace("ؤ", "و").replace("ئ", "ي"))


def tokens(s: str) -> list[str]:
    return [t for t in _TOKEN.findall(norm(s)) if t not in _STOP and len(t) > 1]


class BM25:
    """BM25 Okapi, compact et suffisant à cette échelle."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs: list[dict] = []          # métadonnées des chunks
        self.freqs: list[Counter] = []
        self.lens: list[int] = []
        self.df: Counter = Counter()
        self.postings: dict[str, list[int]] = defaultdict(list)
        self.avgdl = 0.0

    def add(self, meta: dict, text: str) -> None:
        tf = Counter(tokens(text))
        if not tf:
            return
        i = len(self.docs)
        self.docs.append(meta)
        self.freqs.append(tf)
        self.lens.append(sum(tf.values()))
        for t in tf:
            self.df[t] += 1
            self.postings[t].append(i)

    def finalize(self) -> None:
        self.avgdl = (sum(self.lens) / len(self.lens)) if self.lens else 0.0

    def search(self, query: str, limit: int = 20) -> list[tuple[int, float]]:
        q = tokens(query)
        if not q or not self.docs:
            return []
        n = len(self.docs)
        scores: dict[int, float] = defaultdict(float)
        for t in set(q):
            df = self.df.get(t, 0)
            if not df or df > n * 0.5:       # terme trop courant : sans valeur
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for i in self.postings[t]:
                f = self.freqs[i][t]
                dl = self.lens[i]
                denom = f + self.k1 * (1 - self.b + self.b * dl / max(1e-9, self.avgdl))
                scores[i] += idf * f * (self.k1 + 1) / denom
        return sorted(scores.items(), key=lambda x: -x[1])[:limit]


_INDEX: BM25 | None = None
_INDEX_SRC: str | None = None


def index_path() -> str:
    data = os.environ.get("RIMLEX_DATA_DIR", r"Y:\adala-project\aiocr_data")
    return os.path.join(data, "laws_corpus_v2.jsonl")


def get_index() -> BM25 | None:
    """Index BM25 construit depuis le corpus paginé (même source que la
    visionneuse). Reconstruit si le fichier change."""
    global _INDEX, _INDEX_SRC
    path = index_path()
    if not os.path.exists(path):
        return None
    stamp = f"{path}:{os.path.getmtime(path)}"
    if _INDEX is not None and _INDEX_SRC == stamp:
        return _INDEX
    bm = BM25()
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            bm.add({"collection": r.get("collection", ""), "file": r.get("file", ""),
                    "chunk": r.get("chunk"), "law": r.get("law", ""),
                    "article": r.get("article"), "text": r.get("text", ""),
                    "page": r.get("page"), "status": r.get("status", "current")},
                   r.get("text", ""))
    bm.finalize()
    _INDEX, _INDEX_SRC = bm, stamp
    return bm



# Référence explicite dans la question : « الفصل 510 », « المادة 41-1 ».
# Un juriste qui cite un numéro attend CE texte, pas un voisin sémantique.
_ARTREF = re.compile(r"(?:المادة|الفصل)\s*([0-9]{1,4}(?:\s*-\s*[0-9]{1,3})?)")
_HEADER = re.compile(r"^\s*(?:المادة|الفصل)\s*([0-9]{1,4}(?:\s*-\s*[0-9]{1,3})?)")


def article_anchors(query: str, limit: int = 4) -> list[dict]:
    """Chunks dont l'EN-TÊTE est l'article cité dans la question."""
    bm = get_index()
    if bm is None:
        return []
    wanted = {re.sub(r"\s+", "", a) for a in _ARTREF.findall(query)}
    if not wanted:
        return []
    out = []
    for meta in bm.docs:
        art = str(meta.get("article") or "").strip()
        head = _HEADER.match(meta.get("text", "") or "")
        head_num = re.sub(r"\s+", "", head.group(1)) if head else None
        if (art and re.sub(r"\s+", "", art) in wanted) or (head_num in wanted):
            out.append(dict(meta))
            if len(out) >= limit:
                break
    return out

def _key(h: dict) -> tuple:
    return (h.get("collection", ""), h.get("file", ""), str(h.get("chunk")))


def fuse(vector_hits: list[dict], query: str, limit: int = 6,
         k_rrf: int = 60, bm25_depth: int = 30) -> list[dict]:
    """Fusion RRF : chaque liste vote par le RANG, pas par le score — ce qui
    évite de comparer des échelles incomparables. Renvoie les hits enrichis
    de `rrf`, `rank_vec`, `rank_bm25` (utiles pour le filtrage dynamique)."""
    bm = get_index()
    by_key: dict[tuple, dict] = {}
    rrf: dict[tuple, float] = defaultdict(float)

    for rank, h in enumerate(vector_hits, 1):
        k = _key(h)
        by_key[k] = dict(h)
        by_key[k]["rank_vec"] = rank
        rrf[k] += 1.0 / (k_rrf + rank)

    if bm is not None:
        for rank, (i, sc) in enumerate(bm.search(query, limit=bm25_depth), 1):
            meta = bm.docs[i]
            k = _key(meta)
            if k not in by_key:
                by_key[k] = dict(meta)
                by_key[k]["score"] = 0.0
            by_key[k]["rank_bm25"] = rank
            by_key[k]["bm25"] = round(sc, 3)
            rrf[k] += 1.0 / (k_rrf + rank)

    out = []
    for k, h in by_key.items():
        h["rrf"] = round(rrf[k], 5)
        out.append(h)
    out.sort(key=lambda h: -h["rrf"])

    # Les articles explicitement cités passent devant, sans exception.
    anchors = article_anchors(query)
    if anchors:
        akeys = {_key(a) for a in anchors}
        for a in anchors:
            a.setdefault("score", 0.0)
            a["rrf"] = 1.0
            a["anchor"] = True
        out = anchors + [h for h in out if _key(h) not in akeys]
    return out[:limit]
