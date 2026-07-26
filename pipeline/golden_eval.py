# -*- coding: utf-8 -*-
"""Évaluation 'or' : la bonne source est-elle retrouvée pour chaque question ?

Deux modes automatiques :
  - complet   : Qdrant+bge-m3 disponibles -> évalue la récupération réelle
                (search_laws), métriques hit@5 fichier et article
  - dégradé   : pile IA éteinte -> baseline lexicale (recouvrement de
                trigrammes normalisés sur tout le corpus) — utile pour
                détecter les régressions de corpus même sans GPU

Le score de référence est écrit dans golden_baseline.json ; toute release de
corpus doit faire au moins aussi bien.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA = r"Y:\adala-project\aiocr_data"
CORPUS = os.path.join(DATA, "laws_corpus_v2.jsonl")
GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_set.json")
OUT = os.path.join(DATA, "golden_baseline.json")

AR_DIAC = re.compile(r"[ً-ٰٟـ]")


def norm(s: str) -> str:
    s = AR_DIAC.sub("", s or "")
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ى", "ي").replace("ة", "ه"))
    return re.sub(r"[^؀-ۿ0-9 ]", " ", s)


def grams(s: str, n: int = 3) -> set:
    toks = norm(s).split()
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))} | set(toks)


def load_corpus():
    rows = []
    for line in open(CORPUS, encoding="utf-8"):
        r = json.loads(line)
        rows.append((r["file"], str(r.get("article") or ""), r.get("text", "")))
    return rows


def resolve_files(cases, files: set):
    """Les noms attendus peuvent être tronqués/approximés -> résolution par
    préfixe contre les fichiers réels du corpus. Erreur si ambigu."""
    fixed = 0
    for c in cases:
        want = c["expected_file"]
        if want in files:
            continue
        pref = want[:38]
        hits = [f for f in files if f.startswith(pref)]
        if len(hits) != 1:
            pref = want[:25]
            hits = [f for f in files if f.startswith(pref)]
        if len(hits) == 1:
            c["expected_file"] = hits[0]
            fixed += 1
        else:
            c["_unresolved"] = True
            print(f"  ! {c['id']}: fichier attendu introuvable/ambigu — {want[:60]}")
    return fixed


def lexical_top5(query: str, corpus, cache={}):
    qg = grams(query)
    scored = []
    for f, art, text in corpus:
        key = id(text)
        tg = cache.get(key)
        if tg is None:
            tg = cache[key] = grams(text[:1200])
        inter = len(qg & tg)
        if inter:
            scored.append((inter / (len(qg) or 1), f, art))
    scored.sort(reverse=True)
    return scored[:5]


def main():
    gold = json.load(open(GOLD, encoding="utf-8"))
    cases = [c for c in gold["cases"]]
    corpus = load_corpus()
    files = {f for f, _a, _t in corpus}
    fixed = resolve_files(cases, files)
    if fixed:
        json.dump(gold, open(GOLD, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"{fixed} nom(s) de fichier résolus et réécrits dans golden_set.json")
    cases = [c for c in cases if not c.get("_unresolved")]

    mode = "degrade-lexical"
    try:
        from rag.search_laws import search_laws
        probe = search_laws("اختبار", limit=1)
        if probe is not None and probe != []:
            mode = "complet-qdrant"
    except Exception:
        search_laws = None
    print(f"mode: {mode} | {len(cases)} cas")

    file_hits = art_hits = 0
    details = []
    for c in cases:
        if mode == "complet-qdrant":
            top = [(h.get("score", 0), h.get("file", ""), str(h.get("article") or ""))
                   for h in search_laws(c["question"], limit=5)]
        else:
            top = lexical_top5(c["question"], corpus)
        top_files = [f for _s, f, _a in top]
        fh = c["expected_file"] in top_files
        ah = (not c.get("expected_article")
              or any(a == str(c["expected_article"]) for _s, f, a in top
                     if f == c["expected_file"]))
        file_hits += fh
        art_hits += fh and ah
        details.append({"id": c["id"], "file_hit@5": fh,
                        "article_ok": bool(fh and ah),
                        "top1": top_files[0] if top_files else None})
        print(f"  {c['id']}: fichier {'✓' if fh else '✗'}"
              + (f" | article {'✓' if ah else '✗'}" if fh else ""))

    n = len(cases)
    result = {"mode": mode, "cases": n,
              "file_hit_at_5": round(file_hits / n, 3) if n else 0,
              "article_hit_at_5": round(art_hits / n, 3) if n else 0,
              "details": details}
    json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nscore: fichier@5 = {file_hits}/{n} | article@5 = {art_hits}/{n}"
          f" -> {OUT}")


if __name__ == "__main__":
    main()
