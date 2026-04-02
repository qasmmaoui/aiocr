"""
╔══════════════════════════════════════════════════════════════╗
║  DMSI · Adala — Indexeur & Gestionnaire de Recherche         ║
║  search/indexer.py                                           ║
╚══════════════════════════════════════════════════════════════╝
Description :
    - Index inversé persisté en JSON
    - Correction automatique de la requête (OCR_DICT + distance)
    - Suggestions par préfixe
    - Recherche full-text normalisée avec contexte
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

from core.config import DIR_INDEX
from services.correction_service import OCR_DICT
from search.engine import (
    normalize_arabic,
    arabic_edit_distance,
    highlight_matches,
    _RE_ARABIC,
)

_INDEX_FILE = DIR_INDEX / "index.json"


class DocumentIndexer:
    """
    Gère l'index inversé des documents juridiques.

    Structure interne :
        vocab  : { normalized_word : { "f": {original: count}, "n": total } }
        docs   : { doc_id : { fn, np, dt, p, pn } }
    """

    def __init__(self) -> None:
        self.vocab: dict  = {}
        self.docs:  dict  = {}
        self._load()

    # ── Persistance ───────────────────────────────────────────────────────

    def _load(self) -> None:
        if _INDEX_FILE.exists():
            try:
                data = json.loads(_INDEX_FILE.read_text("utf-8"))
                self.vocab = data.get("v", {})
                self.docs  = data.get("d", {})
            except Exception:
                pass

    def _save(self) -> None:
        try:
            _INDEX_FILE.write_text(
                json.dumps({"v": self.vocab, "d": self.docs}, ensure_ascii=False),
                "utf-8",
            )
        except Exception:
            pass

    # ── Indexation ────────────────────────────────────────────────────────

    def index_document(self, doc_id: str, filename: str, pages: list[dict]) -> None:
        """
        Indexe un document et met à jour le vocabulaire.

        Args:
            doc_id:   Hash MD5 du PDF.
            filename: Nom du fichier.
            pages:    Liste de dicts {'num', 'type', 'text'}.
        """
        page_texts:  dict[str, str] = {}
        page_norm:   dict[str, str] = {}

        for page in pages:
            text = page.get("text", "")
            if len(text.strip()) < 5:
                continue
            key = str(page["num"])
            page_texts[key] = text
            norm = normalize_arabic(text)
            page_norm[key]  = norm

            for word in _RE_ARABIC.findall(text):
                nw = normalize_arabic(word)
                if len(nw) < 2:
                    continue
                if nw not in self.vocab:
                    self.vocab[nw] = {"f": {}, "n": 0}
                self.vocab[nw]["f"][word] = self.vocab[nw]["f"].get(word, 0) + 1
                self.vocab[nw]["n"] += 1

        self.docs[doc_id] = {
            "fn": filename,
            "np": len(pages),
            "dt": datetime.now().isoformat(),
            "p":  page_texts,
            "pn": page_norm,
        }
        self._save()

    def remove_document(self, doc_id: str) -> None:
        """Supprime un document de l'index."""
        if doc_id in self.docs:
            del self.docs[doc_id]
            self._save()

    # ── Correction ────────────────────────────────────────────────────────

    def _best_form(self, normalized_word: str) -> str | None:
        """Retourne la forme la plus fréquente d'un mot normalisé."""
        info = self.vocab.get(normalized_word)
        if info:
            return max(info["f"].items(), key=lambda x: x[1])[0]
        return None

    def _closest_word(self, word: str) -> str | None:
        """Cherche le mot du vocabulaire le plus proche (distance ≤ 2)."""
        nw = normalize_arabic(word)

        # Essai dans le dictionnaire de correction
        for wrong, right in OCR_DICT.items():
            if normalize_arabic(wrong) == nw:
                return right

        # Distance d'édition
        best, best_dist = None, 999.0
        for vn, info in self.vocab.items():
            if abs(len(vn) - len(nw)) > 2:
                continue
            dist = arabic_edit_distance(nw, vn)
            if dist < best_dist and dist <= 2.0:
                best_dist = dist
                best = self._best_form(vn)
        return best

    def correct_query(self, query: str) -> str | None:
        """
        Corrige une requête mot par mot.

        Returns:
            La requête corrigée si au moins un mot a été modifié, sinon None.
        """
        words = query.strip().split()
        corrected, changed = [], False

        for word in words:
            if not _RE_ARABIC.match(word):
                corrected.append(word)
                continue
            nw = normalize_arabic(word)
            if nw in self.vocab:
                corrected.append(self._best_form(nw) or word)
            else:
                fix = self._closest_word(word)
                if fix:
                    corrected.append(fix)
                    changed = True
                else:
                    corrected.append(word)

        return " ".join(corrected) if changed else None

    # ── Suggestions ───────────────────────────────────────────────────────

    def suggest(self, prefix: str, limit: int = 8) -> list[str]:
        """Retourne les mots du vocabulaire commençant par prefix."""
        if len(prefix) < 2:
            return []
        np = normalize_arabic(prefix)
        hits: list[tuple[str, int]] = []

        for vn, info in self.vocab.items():
            if vn.startswith(np) and info["n"] >= 2:
                best = self._best_form(vn)
                if best and best not in [x[0] for x in hits]:
                    hits.append((best, info["n"]))

        hits.sort(key=lambda x: -x[1])
        return [x[0] for x in hits[:limit]]

    # ── Recherche ─────────────────────────────────────────────────────────

    def search(self, query: str) -> dict:
        """
        Recherche full-text dans tous les documents indexés.

        Returns:
            {
              "results":     [...],
              "correction":  str | None,
              "suggestions": [...],
              "query_orig":  str,
              "query_eff":   str,
              "total":       int,
              "elapsed_ms":  float,
            }
        """
        query = query.strip()
        if not query:
            return {
                "results": [], "correction": None, "suggestions": [],
                "query_orig": query, "query_eff": query,
                "total": 0, "elapsed_ms": 0.0,
            }

        t0 = time.time()
        correction = self.correct_query(query)
        effective  = correction if correction else query
        nq         = normalize_arabic(effective)
        results    = []

        for doc_id, doc in self.docs.items():
            matches: list[dict] = []
            for page_num, norm_text in doc.get("pn", {}).items():
                if nq not in norm_text:
                    continue
                raw = doc["p"].get(page_num, "")
                excerpt = self._extract_excerpt(raw, norm_text, nq)
                matches.append({"page": int(page_num), "line": excerpt})

            if matches:
                matches.sort(key=lambda x: x["page"])
                results.append(
                    {
                        "doc_id":   doc_id,
                        "filename": doc["fn"],
                        "nb_pages": doc["np"],
                        "matches":  matches,
                    }
                )

        results.sort(key=lambda x: -len(x["matches"]))

        # Suggestions
        suggestions: list[str] = []
        for word in query.split():
            if _RE_ARABIC.match(word):
                suggestions.extend(self.suggest(word, 3))
        suggestions = list(dict.fromkeys(suggestions))[:8]

        elapsed = (time.time() - t0) * 1000

        return {
            "results":     results,
            "correction":  correction,
            "suggestions": suggestions,
            "query_orig":  query,
            "query_eff":   effective,
            "total":       len(results),
            "elapsed_ms":  round(elapsed, 1),
        }

    @staticmethod
    def _extract_excerpt(raw: str, norm_text: str, nq: str) -> str:
        """Extrait un contexte autour de l'occurrence trouvée."""
        for line in raw.split('\n'):
            stripped = line.strip()
            if stripped and nq in normalize_arabic(stripped):
                return stripped[:300]
        pos = norm_text.find(nq)
        if pos >= 0:
            start = max(0, pos - 80)
            end   = min(len(raw), pos + len(nq) + 80)
            return raw[start:end].replace('\n', ' ')[:300]
        return ""

    # ── Statistiques ──────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Retourne les statistiques globales de l'index."""
        return {
            "docs":  len(self.docs),
            "words": len(self.vocab),
            "pages": sum(x["np"] for x in self.docs.values()),
        }

    def list_documents(self) -> list[dict]:
        """Retourne la liste des documents indexés."""
        return [
            {
                "doc_id":   did,
                "filename": doc["fn"],
                "nb_pages": doc["np"],
                "indexed":  doc.get("dt", ""),
            }
            for did, doc in self.docs.items()
        ]

    def highlight(self, text: str, query: str) -> str:
        """Délègue le highlight au moteur."""
        return highlight_matches(text, query)
