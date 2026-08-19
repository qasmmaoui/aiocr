# -*- coding: utf-8 -*-
"""Catalogue unifié des 46 885 documents : jurisprudence + lois, dédoublonnés.

Pourquoi ce fichier existe : les métadonnées sont aujourd'hui éclatées en
7 Excel de chambres (8 colonnes) + un catalog.json de lois (18 champs), avec
5 933 doublons entre deux fonds. Rien ne dit à l'OCR quoi traiter, dans quel
ordre, ni à quelle matière rattacher une décision.

Ce script produit UN fichier par document, avec les métadonnées d'origine
enrichies de ce qui est déductible sans lire le texte :
  - chambre et matière (déduites du numéro de dossier, pas du dossier de rangement)
  - année, présence locale, présence sur le volume, taille, nombre de pages
  - un identifiant stable (doc_id) qui survivra aux déplacements de fichiers

Ce qui exige le texte OCRisé (sens de la décision, articles cités) est
volontairement absent : ces champs viendront après l'OCR, pas avant.

    python pipeline/build_catalog.py            # construit
    python pipeline/build_catalog.py --stats    # relit et résume
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict

JURIS_ROOTS = [r"Z:\jurisprudence", r"Y:\adala-project\juris"]
LAWS_CATALOG = r"Y:\adala-project\adala_pdfs\_catalog\catalog.json"
LAWS_ROOT = r"Y:\adala-project\adala_pdfs"
OUT = r"Y:\adala-project\aiocr_data\catalogue_unifie.jsonl"
STATS = r"Y:\adala-project\aiocr_data\catalogue_stats.json"

# La chambre est le 3e élément du numéro de dossier (2024/2/4/4641 -> 4).
# On la lit LÀ et pas dans le nom du dossier de rangement : un fichier mal
# classé garde son vrai numéro, le dossier ment.
CHAMBRE_MATIERE = {
    1: ("الغرفة المدنية", "civil"),
    2: ("غرفة الأحوال الشخصية والميراث", "famille"),
    3: ("الغرفة التجارية", "commercial"),
    4: ("الغرفة الإدارية", "administratif"),
    5: ("الغرفة الاجتماعية", "social"),
    6: ("الغرفة الجنائية", "penal"),
    7: ("غرفة المشورة", "autre"),
}
NUM_DOSSIER = re.compile(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})[/-](\d+)$")
# 2024-1675_2024-2-4-4641.pdf : la chambre est aussi dans le nom du fichier
NOM_FICHIER = re.compile(r"^(\d{4})-(\d+)_(\d{4})-(\d{1,2})-(\d{1,2})-(\d+)\.pdf$",
                         re.I)


def log(m: str) -> None:
    print(m, flush=True)


# ---------------------------------------------------------------- Excel brut
def lire_xlsx(path: str) -> list[list[str]]:
    """Lecture xlsx sans dépendance : les Excel du scraper sont simples.
    Les libellés arabes sont encodés en entités numériques -> unescape."""
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        s = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
        for si in re.findall(r"<si>(.*?)</si>", s, re.S):
            shared.append(html.unescape("".join(re.findall(r"<t[^>]*>([^<]*)</t>", si))))
    sheets = [n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
    if not sheets:
        return []
    x = z.read(sorted(sheets)[0]).decode("utf-8", "replace")
    out = []
    for r in re.findall(r"<row[^>]*>(.*?)</row>", x, re.S):
        cells = []
        for c in re.findall(r"<c\b[^>]*>.*?</c>|<c\b[^>]*/>", r, re.S):
            inline = re.search(r"<is>.*?<t[^>]*>([^<]*)</t>", c, re.S)
            v = re.search(r"<v>([^<]*)</v>", c)
            t = re.search(r'\st="(\w+)"', c)
            if inline:
                cells.append(html.unescape(inline.group(1)))
            elif t and t.group(1) == "s" and v and v.group(1).isdigit():
                k = int(v.group(1))
                cells.append(shared[k] if k < len(shared) else "")
            else:
                cells.append(html.unescape(v.group(1)) if v else "")
        out.append(cells)
    return out


def excels() -> list[str]:
    found = []
    for root in JURIS_ROOTS:
        if not os.path.isdir(root):
            continue
        for dp, _d, fs in os.walk(root):
            for f in fs:
                if f.lower().startswith("resultats_") and f.lower().endswith(".xlsx"):
                    found.append(os.path.join(dp, f))
    return sorted(found)


# ------------------------------------------------------------------- helpers
def doc_id(kind: str, nom: str) -> str:
    return kind[:1] + hashlib.sha1(nom.encode("utf-8")).hexdigest()[:15]


def chambre_de(num_dossier: str, nom: str) -> int | None:
    m = NUM_DOSSIER.match((num_dossier or "").strip())
    if m:
        c = int(m.group(3))
        if c in CHAMBRE_MATIERE:
            return c
    m = NOM_FICHIER.match(os.path.basename(nom or ""))
    if m:
        c = int(m.group(5))
        if c in CHAMBRE_MATIERE:
            return c
    return None


def index_local() -> dict[str, tuple[str, int]]:
    """nom de fichier -> (chemin, taille). Le premier trouvé gagne."""
    idx: dict[str, tuple[str, int]] = {}
    for root in JURIS_ROOTS + [LAWS_ROOT]:
        if not os.path.isdir(root):
            continue
        for dp, _d, fs in os.walk(root):
            for f in fs:
                if f.lower().endswith(".pdf") and f not in idx:
                    p = os.path.join(dp, f)
                    try:
                        idx[f] = (p, os.path.getsize(p))
                    except OSError:
                        pass
    return idx


# ---------------------------------------------------------------------- main
def construire() -> int:
    local = index_local()
    log(f"fichiers PDF locaux indexés : {len(local):,}")

    docs: dict[str, dict] = {}
    sans_chambre = 0

    for xl in excels():
        rows = lire_xlsx(xl)
        if len(rows) < 2:
            continue
        hdr = rows[0]
        # colonnes attendues : ملف / قرار / تاريخ / قاعدة / data-id / nom / chemin / état
        idx = {h: i for i, h in enumerate(hdr)}
        def col(row, *cands):
            for c in cands:
                i = idx.get(c)
                if i is not None and i < len(row):
                    return row[i].strip()
            return ""

        n = 0
        for row in rows[1:]:
            if not any(c.strip() for c in row):
                continue
            nom = col(row, "اسم ملف PDF")
            num_dossier = col(row, "رقم الملف")
            if not nom:
                continue
            ch = chambre_de(num_dossier, nom)
            if ch is None:
                sans_chambre += 1
            ar, mat = CHAMBRE_MATIERE.get(ch, ("", "inconnu"))
            date = col(row, "تاريخ القرار")
            p, taille = local.get(nom, ("", 0))
            d = {
                "doc_id": doc_id("j", nom),
                "type": "jurisprudence",
                "fichier": nom,
                "chemin_local": p,
                "present_local": bool(p),
                "taille": taille,
                "num_dossier": num_dossier,
                "num_decision": col(row, "رقم القرار"),
                "date": date,
                "annee": date[:4] if len(date) >= 4 and date[:4].isdigit() else "",
                "chambre": ch,
                "chambre_ar": ar,
                "matiere": mat,
                "qaida": col(row, "المفاتيح أو القاعدة أو المحتوى"),
                "data_id": col(row, "data-id (encryptedId)"),
                "source_excel": os.path.basename(xl),
            }
            # doublon : on garde l'entrée la plus riche (qaida la plus longue)
            old = docs.get(nom)
            if old is None or len(d["qaida"]) > len(old.get("qaida", "")):
                docs[nom] = d
            n += 1
        log(f"  {os.path.basename(xl):<32} {n:>7,} lignes")

    log(f"jurisprudence : {len(docs):,} décisions uniques "
        f"({sans_chambre:,} sans chambre déductible)")

    # ------------------------------------------------------------- les lois
    nlois = 0
    if os.path.exists(LAWS_CATALOG):
        cat = json.load(open(LAWS_CATALOG, encoding="utf-8"))
        for e in cat:
            rel = e.get("path", "")
            nom = os.path.basename(rel)
            if not nom:
                continue
            p, taille = local.get(nom, ("", 0))
            docs[nom] = {
                "doc_id": doc_id("l", nom),
                "type": "loi",
                "fichier": nom,
                "chemin_local": p,
                "present_local": bool(p),
                "taille": taille or e.get("size", 0),
                "theme": e.get("theme", ""),
                "matiere": e.get("theme", ""),
                "doc_type": e.get("doc_type", ""),
                "dahir_num": e.get("dahir_num", ""),
                "law_num": e.get("law_num", ""),
                "decree_num": e.get("decree_num", ""),
                "primary_num": e.get("primary_num", ""),
                "bo_issue": e.get("bo_issue", ""),
                "date": e.get("issue_date", "") or e.get("portal_date", ""),
                "annee": (e.get("issue_date", "") or "")[:4],
                "pages": e.get("pages", 0),
                "lang": e.get("lang", ""),
                "md5": e.get("md5", ""),
                "titre": e.get("title_from_name", ""),
            }
            nlois += 1
        log(f"lois : {nlois:,} entrées du catalogue")
    else:
        log(f"ATTENTION : {LAWS_CATALOG} absent — lois non catalogués")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for d in docs.values():
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    log(f"\nÉCRIT : {OUT} — {len(docs):,} documents")
    resumer(docs)
    return 0


def resumer(docs: dict[str, dict]) -> None:
    par_type = Counter(d["type"] for d in docs.values())
    par_mat = Counter(d.get("matiere", "") for d in docs.values()
                      if d["type"] == "jurisprudence")
    par_an = Counter(d.get("annee", "") for d in docs.values() if d.get("annee"))
    absents = sum(1 for d in docs.values() if not d["present_local"])
    sans_qaida = sum(1 for d in docs.values()
                     if d["type"] == "jurisprudence" and not d.get("qaida"))
    stats = {
        "total": len(docs),
        "par_type": dict(par_type),
        "jurisprudence_par_matiere": dict(par_mat.most_common()),
        "annees": dict(sorted(par_an.items())[-12:]),
        "pdf_absent_en_local": absents,
        "jurisprudence_sans_qaida": sans_qaida,
    }
    json.dump(stats, open(STATS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    log("\n=== RÉSUMÉ ===")
    for k, v in par_type.items():
        log(f"  {k:<16} {v:>8,}")
    log("  jurisprudence par matière :")
    for k, v in par_mat.most_common():
        log(f"      {k:<16} {v:>8,}")
    log(f"  PDF référencés mais absents du disque : {absents:,}")
    log(f"  décisions sans قاعدة                  : {sans_qaida:,}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    if a.stats:
        if not os.path.exists(OUT):
            sys.exit(f"{OUT} absent — lancez sans --stats d'abord")
        docs = {}
        for line in open(OUT, encoding="utf-8"):
            d = json.loads(line)
            docs[d["fichier"]] = d
        resumer(docs)
        return 0
    return construire()


if __name__ == "__main__":
    sys.exit(main())
