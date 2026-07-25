# -*- coding: utf-8 -*-
"""Analyse de liaison jurisprudence (Chambre 6 pénale) <-> catalogue des lois.
1. Couverture Excel (métadonnées portail)
2. Extraction des citations dans le texte des arrêts (échantillon)
3. Taux de résolution vers le catalogue adala_pdfs
"""
import openpyxl, fitz, re, glob, os, json, random, unicodedata, io
from collections import Counter

JDIR = r"Y:\adala-project\juris\Chambre_6\Chambre_6"
XLSX = os.path.join(JDIR, "resultats_Chambre_6.xlsx")
CAT  = r"Y:\adala-project\adala_pdfs\_catalog\catalog.json"
OUT  = r"C:\Users\HP\AppData\Local\Temp\claude\C--Users-HP--claude\805beed1-2d72-4c8a-8626-15bbfe36c597\scratchpad\juris_link_report.txt"

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
def norm(t):
    t = unicodedata.normalize("NFKC", t or "").translate(AR_DIGITS)
    # artefacts ligatures : lam-alef + lam-mim inversés
    t = t.replace("األ","الأ").replace("اإل","الإ").replace("اآل","الآ").replace("اال","الا")
    t = re.sub(r"\bامل", "الم", t)
    t = re.sub(r"\s*/\s*", "/", t)          # dates éclatées 17/\n07/\n2024
    return t

# ── 1. Excel (peut être verrouillé si le scraper tourne encore) ────────────
excel_line = "EXCEL: illisible (scraper en cours ?) — analyse texte seulement\n"
try:
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr, data = rows[0], rows[1:]
    i_date = hdr.index("تاريخ القرار"); i_kw = hdr.index("المفاتيح أو القاعدة أو المحتوى")
    i_pdf = hdr.index("اسم ملف PDF")
    years = Counter(str(r[i_date])[:4] for r in data if r[i_date])
    kw_cov = sum(1 for r in data if r[i_kw] and len(str(r[i_kw])) > 30)
    excel_line = (f"EXCEL: {len(data)} lignes | qa3ida: {kw_cov} ({100*kw_cov//len(data)}%)\n"
                  f"ANNEES: {sorted(years.items())}\n")
except Exception:
    pass
# années depuis les noms de fichiers (fallback fiable)
fyears = Counter(os.path.basename(p)[:4] for p in glob.glob(os.path.join(JDIR, "*.pdf")))

# ── 2. citations dans le texte (échantillon de 120 arrêts) ────────────────
CITE = {
 "law_ref":    re.compile(r"(?:ال)?قانون\s+رقم\s*(\d{1,3}[.\-]\d{2,3})(?![.\-]\d)"),
 "dahir_ref":  re.compile(r"ظهير(?:\s+شريف)?\s+رقم\s*(\d{1,2}[.\-]\d{1,3}[.\-]\d{1,4})"),
 "cpp_art":    re.compile(r"الما?دة\s*(\d{1,4})(?:[^.\n]{0,40}?)من\s+قانون\s+المسطرة\s+الجنائية"),
 "cp_art":     re.compile(r"الفصل\s*(\d{1,4})(?:[^.\n]{0,40}?)من\s+(?:مجموعة\s+)?القانون\s+الجنائي"),
 "any_art":    re.compile(r"(?:الما?دة|الفصل)\s*(\d{1,4})\s*(?:و|،|\s)"),
}
pdfs = glob.glob(os.path.join(JDIR, "*.pdf"))
random.seed(5)
sample = random.sample(pdfs, min(120, len(pdfs)))
stats = Counter(); law_nums_cited = Counter(); native = 0
per_doc_articles = []
for p in sample:
    try:
        d = fitz.open(p)
        t = norm("\n".join(pg.get_text() for pg in d)); d.close()
    except Exception:
        continue
    if len(re.sub(r"\s", "", t)) < 100:
        stats["scanned"] += 1; continue
    native += 1
    found_any = False
    for k in ("law_ref", "dahir_ref", "cpp_art", "cp_art"):
        ms = CITE[k].findall(t)
        if ms:
            stats[k] += 1; found_any = True
            if k in ("law_ref", "dahir_ref"):
                for m in ms: law_nums_cited[m.replace("-", ".")] += 1
    arts = set(CITE["any_art"].findall(t))
    per_doc_articles.append(len(arts))
    if found_any: stats["any_citation"] += 1

# ── 3. résolution vers le catalogue ───────────────────────────────────────
cat = json.load(open(CAT, encoding="utf-8"))
cat_nums = {r.get("primary_num") for r in cat if r.get("primary_num")}
cat_nums |= {r.get("enacts_law") for r in cat if r.get("enacts_law")}
cat_nums |= {r.get("dahir_num") for r in cat if r.get("dahir_num")}
cat_nums -= {None}
resolved = {n: c for n, c in law_nums_cited.items() if n in cat_nums}
unresolved = {n: c for n, c in law_nums_cited.items() if n not in cat_nums}

with io.open(OUT, "w", encoding="utf-8") as f:
    f.write(excel_line)
    top_years = sorted(fyears.items())
    f.write(f"ANNEES (noms de fichiers): {top_years[:3]} ... {top_years[-3:]} | {len(fyears)} annees\n\n")
    f.write(f"ECHANTILLON TEXTE ({len(sample)} arrets): natifs={native} scannes={stats['scanned']}\n")
    for k in ("any_citation", "law_ref", "dahir_ref", "cpp_art", "cp_art"):
        f.write(f"  {k:14s}: {stats[k]:4d}/{native} ({100*stats[k]//max(native,1)}%)\n")
    f.write(f"  articles cites/arret (moyenne): {sum(per_doc_articles)/max(len(per_doc_articles),1):.1f}\n\n")
    f.write(f"NUMEROS DE LOIS CITES: {len(law_nums_cited)} distincts\n")
    f.write(f"  -> RESOLUS dans le catalogue: {len(resolved)} ({100*len(resolved)//max(len(law_nums_cited),1)}%)\n")
    f.write(f"  top resolus: {sorted(resolved.items(), key=lambda x:-x[1])[:10]}\n")
    f.write(f"  top NON resolus: {sorted(unresolved.items(), key=lambda x:-x[1])[:10]}\n")
print(open(OUT, encoding="utf-8").read())
