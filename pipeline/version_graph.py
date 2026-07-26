# -*- coding: utf-8 -*-
"""Traitement de la complexité versionnelle du corpus juridique.

1. Dédoublonnage : hash exact + numéro officiel (X.YY.ZZZ) en doublon de titre.
2. Extraction des amendements :
   - notes de bas de page des textes consolidés («تم تغيير وتتميم المادة 17
     أعلاه بمقتضى ... رقم 2.23.273») -> amendements DÉJÀ intégrés (info).
   - titres d'actes modificatifs («بتغيير وتتميم القانون رقم 15.95») ->
     cible potentiellement obsolète si sa copie ne mentionne pas cet acte.
3. Sorties :
   - version_graph.json  (arêtes doc->doc, article par article)
   - dedup_report.json
   - laws_corpus_v2.jsonl (chunks enrichis : status, amended_by, notes)
"""
import glob
import hashlib
import json
import os
import re
from collections import defaultdict

import fitz

LAWS_DIR = r"Y:\adala-project\laws"
CORPUS_IN = r"Y:\adala-project\aiocr_data\laws_corpus_paged.jsonl"
CORPUS_OUT = r"Y:\adala-project\aiocr_data\laws_corpus_v2.jsonl"
GRAPH_OUT = r"Y:\adala-project\aiocr_data\version_graph.json"
DEDUP_OUT = r"Y:\adala-project\aiocr_data\dedup_report.json"

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# numéro officiel marocain : 1.11.78 / 2.14.652 / 37.21 ...
NUM = r"[0-9]{1,2}[./][0-9]{2}[./][0-9]{1,4}|[0-9]{1,3}[./][0-9]{2}"

# note de consolidation : action + article(s) + بمقتضى + numéro de l'acte
FOOTNOTE = re.compile(
    r"(?:تم\s+)?(تغيير|تتميم|تغيير\s+وتتميم|نسخ|تعويض|إلغاء|حذف)"
    r"[^.\n]{0,120}?(?:المادة|الفصل|المادتين|الفصلين|المواد|الفصول)"
    r"\s*([0-9٠-٩][0-9٠-٩\s./و،-]{0,40})"
    r"[^.\n]{0,150}?بمقتضى[^.\n]{0,200}?رقم\s*(" + NUM + r")")

# acte modificatif d'après son titre
TITLE_AMEND = re.compile(
    r"(?:بتغيير|بتتميم|بتغيير\s+وتتميم|بنسخ|بإلغاء|يقضي\s+بتغيير)"
    r"[^.]{0,80}?رقم\s*(" + NUM + r")")

ABROGATION = re.compile(
    r"(?:تنسخ|ينسخ|تلغى|يلغى)\s+(?:أحكام\s+)?"
    r"(?:القانون|الظهير|المرسوم|القرار)[^.\n]{0,80}?رقم\s*(" + NUM + r")")


def canon_num(s: str) -> str:
    return s.translate(AR_DIGITS).replace("/", ".").strip(".")


def own_number(title: str) -> str | None:
    m = re.search(r"رقم\s*(" + NUM + r")", title.translate(AR_DIGITS))
    return canon_num(m.group(1)) if m else None


def parse_articles(raw: str) -> list[str]:
    raw = raw.translate(AR_DIGITS)
    return [a for a in re.split(r"[و،\s-]+", raw) if a.strip("./").isdigit()][:12]


def main() -> None:
    pdfs = glob.glob(os.path.join(LAWS_DIR, "**", "*.pdf"), recursive=True)

    # ── 1. dédoublonnage ──────────────────────────────────────────────────
    by_hash, by_num = defaultdict(list), defaultdict(list)
    doc_meta = {}
    for p in pdfs:
        base = os.path.basename(p)
        h = hashlib.sha1(open(p, "rb").read()).hexdigest()
        by_hash[h].append(base)
        num = own_number(base)
        if num:
            by_num[num].append(base)
        doc_meta[base] = {"path": p, "num": num}
    dup_exact = {h: v for h, v in by_hash.items() if len(v) > 1}
    dup_num = {n: v for n, v in by_num.items() if len(v) > 1}
    json.dump({"exact_duplicates": dup_exact, "same_official_number": dup_num},
              open(DEDUP_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ── 2. extraction des amendements ────────────────────────────────────
    edges = []                      # {type, source, target_num, articles, ref}
    consolidated_refs = defaultdict(set)   # doc -> numéros d'actes déjà intégrés
    # alias : un doc est désigné par son numéro de titre (dahir/décret) ET par
    # les numéros de loi promulgués qu'il contient («قانون رقم 20.05»)
    alias_to_docs = defaultdict(set)
    LAW_REF = re.compile(r"(?:القانون|قانون|الظهير|المرسوم|القرار)\s+رقم\s*(" + NUM + r")")
    for base, meta in doc_meta.items():
        try:
            doc = fitz.open(meta["path"])
            text = "\n".join(pg.get_text() for pg in doc).translate(AR_DIGITS)
            # bloc-titre seulement : la loi promulguée y est nommée ; plus loin
            # ce ne sont que des mentions d'autres lois (amendements, renvois)
            head = doc[0].get_text().translate(AR_DIGITS)[:500]
            doc.close()
        except Exception:
            continue
        if meta["num"]:
            alias_to_docs[meta["num"]].add(base)
        for m in LAW_REF.finditer(head):
            alias_to_docs[canon_num(m.group(1))].add(base)
        for m in FOOTNOTE.finditer(text):
            action, arts, ref = m.group(1), parse_articles(m.group(2)), canon_num(m.group(3))
            consolidated_refs[base].add(ref)
            edges.append({"type": "consolidated", "doc": base, "action": action,
                          "articles": arts, "by": ref})
        for m in ABROGATION.finditer(text):
            edges.append({"type": "abrogates", "doc": base,
                          "target_num": canon_num(m.group(1))})
        tm = TITLE_AMEND.search(base.translate(AR_DIGITS))
        if tm:
            edges.append({"type": "amending_act", "doc": base,
                          "target_num": canon_num(tm.group(1))})

    # actes modificatifs dont la cible existe mais n'intègre pas la modif
    num_to_docs = defaultdict(list)
    for b, m in doc_meta.items():
        if m["num"]:
            num_to_docs[m["num"]].append(b)
    warnings = []
    for e in edges:
        if e["type"] != "amending_act":
            continue
        actor_num = doc_meta[e["doc"]]["num"]
        for target in num_to_docs.get(e["target_num"], []):
            if actor_num and actor_num not in consolidated_refs.get(target, set()):
                warnings.append({"target_doc": target, "amended_by_doc": e["doc"],
                                 "amending_num": actor_num})
    json.dump({"edges": edges, "possibly_stale": warnings},
              open(GRAPH_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ── 3. enrichissement des chunks ─────────────────────────────────────
    consolidated_by_article = defaultdict(list)   # (doc, art) -> [refs]
    abrogated_by = defaultdict(set)               # num abrogé -> docs abrogeants
    stale_by_doc = defaultdict(list)
    for e in edges:
        if e["type"] == "consolidated":
            for a in e["articles"]:
                consolidated_by_article[(e["doc"], a)].append(
                    {"action": e["action"], "by": e["by"]})
        elif e["type"] == "abrogates":
            abrogated_by[e["target_num"]].add(e["doc"])
    for w in warnings:
        stale_by_doc[w["target_doc"]].append(w["amending_num"])

    # index contenu de la collection adala_pdfs (bloc-titre), si déjà construit
    adala_idx: dict = {}
    adala_idx_path = r"Y:\adala-project\aiocr_data\adala_alias_index.json"
    if os.path.exists(adala_idx_path):
        adala_idx = json.load(open(adala_idx_path, encoding="utf-8"))
    # chaînes du catalogue récupéré (law_num -> fichiers adala) : 2e source d'alias
    chains_path = r"Y:\adala-project\adala_pdfs\_catalog\version_chains.json"
    if os.path.exists(chains_path):
        try:
            chains = json.load(open(chains_path, encoding="utf-8")).get("chains", {})
            for key, paths in chains.items():
                num = canon_num(key.split(":", 1)[-1])
                if num:
                    adala_idx.setdefault(num, []).extend(paths)
        except Exception:
            pass

    def resolve(ref: str, self_doc: str) -> list[dict]:
        """Numéro cité -> documents (corpus laws d'abord, sinon adala_pdfs)."""
        cands = [d for d in alias_to_docs.get(ref, ()) if d != self_doc]
        titled = [d for d in cands if doc_meta[d]["num"] == ref or ref in d.translate(AR_DIGITS)]
        found = [{"num": ref, "file": d, "origin": "laws"}
                 for d in sorted(titled or cands)[:3]]
        if not found:
            found = [{"num": ref, "file": os.path.basename(rel), "origin": "adala"}
                     for rel in sorted(set(adala_idx.get(ref, [])))[:3]]
        return found

    art_in_text = re.compile(r"(?:المادة|الفصل|المادة\s*رقم)\s*([0-9٠-٩]{1,4})")
    n_flags = 0
    with open(CORPUS_OUT, "w", encoding="utf-8") as out:
        for line in open(CORPUS_IN, encoding="utf-8"):
            r = json.loads(line)
            base = r["file"]
            num = doc_meta.get(base, {}).get("num")
            # articles du chunk : champ métadonnée s'il existe, sinon le texte
            arts = set()
            meta_art = str(r.get("article") or "").translate(AR_DIGITS)
            if meta_art.isdigit():
                arts.add(meta_art)
            arts.update(m.group(1).translate(AR_DIGITS)
                        for m in art_in_text.finditer(r.get("text", "")))
            mods = [m for a in arts
                    for m in consolidated_by_article.get((base, a), [])]
            r["status"] = "current"
            if mods:
                r["status"] = "consolidated"       # texte à jour, intègre la modif
                r["amended_by"] = sorted({m["by"] for m in mods})
                r["amended_by_docs"] = [
                    d for ref in r["amended_by"] for d in resolve(ref, base)]
                n_flags += 1
            if base in stale_by_doc:
                r["status"] = "check_amendments"   # un acte modificatif existe
                r["pending_amendments"] = sorted(set(stale_by_doc[base]))
                n_flags += 1
            if num and num in abrogated_by:
                r["status"] = "possibly_abrogated"
                r["abrogated_by_docs"] = [
                    {"file": d} for s in abrogated_by[num] for d in [s] if d != base]
                n_flags += 1
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"docs={len(pdfs)} | exact_dups={len(dup_exact)} | num_dups={len(dup_num)}")
    print(f"edges={len(edges)} (consolidated={sum(1 for e in edges if e['type']=='consolidated')}, "
          f"amending_acts={sum(1 for e in edges if e['type']=='amending_act')}, "
          f"abrogations={sum(1 for e in edges if e['type']=='abrogates')})")
    print(f"possibly_stale_warnings={len(warnings)} | chunks_flagged={n_flags}")


if __name__ == "__main__":
    main()
