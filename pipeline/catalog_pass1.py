# -*- coding: utf-8 -*-
"""
PASS 1 — Catalogue du corpus adala_pdfs (5 000+ PDF juridiques marocains).
Objectif : métadonnées MAXIMALEMENT FIABLES pour un agent IA juridique.

Principes de correction maximale :
  - 3 couches indépendantes : index portail / nom de fichier / 2 premières pages
  - Validation croisée entre couches ; tout désaccord est SIGNALÉ, jamais résolu en silence
  - Normalisation NFKC + chiffres arabes-indiens -> ASCII avant toute regex
  - Mois marocains ET machreqيins ; dates hégirien + grégorien ; فاتح = 1er
  - Doublons détectés par MD5 intégral
  - Champ `flags` par document -> file d'attente de revue humaine (Phase B)

Sortie (dans adala_pdfs/_catalog/) :
  catalog.json      — 1 enregistrement complet par PDF
  report.txt        — statistiques de couverture + problèmes
  review_queue.json — documents nécessitant décision humaine
  version_chains.json — lois présentes en plusieurs versions/doublons

Usage :  python catalog_pass1.py sample   (150 fichiers, contrôle qualité)
         python catalog_pass1.py full
"""
import fitz, re, os, sys, json, glob, hashlib, random, unicodedata
from collections import defaultdict

ROOT = r"Y:\adala-project\adala_pdfs"
OUT  = os.path.join(ROOT, "_catalog")
INDEX = os.path.join(ROOT, "_adala_index.json")

# ── normalisation ──────────────────────────────────────────────────────────
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

def norm(t: str) -> str:
    t = unicodedata.normalize("NFKC", t or "")
    t = t.translate(AR_DIGITS)
    t = re.sub(r"[‎‏‪-‮﻿]", "", t)   # marques bidi
    # artefact d'extraction fréquent : lam-alef inversé (األ ← الأ)
    t = t.replace("األ", "الأ").replace("اإل", "الإ").replace("اآل", "الآ").replace("اال", "الا")
    return t

def norm_num(s: str) -> str:
    """1-02-255 / 1.02.255 / ١.٠٢.٢٥٥ -> 1.02.255"""
    s = norm(s).replace("-", ".").replace("_", ".")
    s = re.sub(r"\.+", ".", s).strip(".")
    return s

# ── mois ───────────────────────────────────────────────────────────────────
GREG = {"يناير":1,"فبراير":2,"مارس":3,"أبريل":4,"ابريل":4,"إبريل":4,"ماي":5,"مايو":5,
        "يونيو":6,"يونيه":6,"يوليوز":7,"يوليو":7,"غشت":8,"أغسطس":8,"اغسطس":8,
        "شتنبر":9,"سبتمبر":9,"أكتوبر":10,"اكتوبر":10,"نونبر":11,"نوفمبر":11,
        "دجنبر":12,"ديسمبر":12}
HIJRI = ["محرم","صفر","ربيع الأول","ربيع الاول","ربيع الآخر","ربيع الثاني",
         "جمادى الأولى","جمادى الاولى","جمادى الآخرة","جمادى الثانية",
         "رجب","شعبان","رمضان","شوال","ذو القعدة","ذي القعدة","ذو الحجة","ذي الحجة"]
GREG_RX  = "|".join(GREG)
HIJRI_RX = "|".join(HIJRI)

# ── regex arabes ───────────────────────────────────────────────────────────
# NB : les PDF Adala collent souvent le numéro au mot (« رقم2.04.546 »), éclatent
# les dates sur plusieurs lignes avec parenthèses baladeuses (« (22\nأكتوبر(2004 »).
# D'où : \s* après رقم/عدد, séparateurs [()\s]* dans les dates.
_SEP = r"[()\s]*"
RX = {
 "dahir":  re.compile(r"ظهير\s+شريف\s+رقم\s*(\d{1,2}[.\-]\d{1,3}[.\-]\d{1,4})"),
 "law":    re.compile(r"(?:ال)?قانون(?:\s+التنظيمي)?\s+رقم\s*(\d{1,3}[.\-]\d{2,3})(?![.\-]\d)"),
 "decree": re.compile(r"مرسوم(?:\s+بقانون)?(?:\s+ملكي)?\s+رقم\s*(\d[.\-]\d{2}[.\-]\d{1,4})"),
 "decree_royal": re.compile(r"مرسوم\s+ملكي\s+رقم\s*(\d{2,4}[.\-]\d{2})(?![.\-]\d)"),
 "arrete": re.compile(r"قرار(?:\s+مشترك)?\s+(?:\S+\s+){0,8}?رقم\s*([\d][\d.\-]{1,12})"),
 "bo":     re.compile(r"الجريدة\s+الرسمية\s+عدد\s*(\d{3,5})"),
 "bo_date":re.compile(r"الجريدة\s+الرسمية\s+عدد\s*\d{3,5}[^\d]{0,40}?(فاتح|\d{1,2})" + _SEP + r"(?:من\s+)?(" + GREG_RX + r")" + _SEP + r"(\d{4})"),
 "greg":   re.compile(r"(فاتح|\d{1,2})" + _SEP + r"(?:من\s+)?(" + GREG_RX + r")" + _SEP + r"(\d{4})"),
 "hijri":  re.compile(r"(فاتح|\d{1,2})" + _SEP + r"(?:من\s+)?(" + HIJRI_RX + r")" + _SEP + r"(\d{4})"),
 "enacts": re.compile(r"(?:بتنفيذ|بتطبيق)\s+(?:ال)?قانون(?:\s+التنظيمي)?\s+رقم\s*(\d{1,3}[.\-]\d{2,3})"),
 "amends": re.compile(r"(?:بتغيير|بتتميم|بنسخ|يقضي\s+بتغيير|بتغيير\s+وتتميم|بمراجعة)"
                      r"[^.\n]{0,90}?(?:القانون|الظهير|المرسوم|الفصل|المادة)[^.\n]{0,50}?رقم\s*([\d][\d.\-]{1,12})"),
}
# regex françaises (docs FR)
RXF = {
 "dahir":  re.compile(r"[Dd]ahir\s+n[°o]\s*(\d[-.\s]\d{2}[-.\s]\d{1,4})"),
 "law":    re.compile(r"[Ll]oi\s+n[°o]\s*(\d{1,3}[-.\s]\d{2,3})"),
 "decree": re.compile(r"[Dd][ée]cret\s+n[°o]\s*(\d[-.\s]\d{2}[-.\s]\d{1,4})"),
 "bo":     re.compile(r"B\.?\s*O\.?\s*n[°o]?\s*(\d{3,5})"),
}
DOCTYPE_ORDER = [  # classification par position la plus précoce dans l'en-tête
 ("الدستور", "constitution"), ("ظهير شريف", "dahir"), ("مرسوم بقانون", "decret_loi"),
 ("مرسوم", "decret"), ("قانون تنظيمي", "loi_organique"), ("قانون رقم", "loi"),
 ("قرار المحكمة الدستورية", "decision_cc"), ("قرار المجلس الدستوري", "decision_cc"),
 ("قرار مشترك", "arrete_conjoint"), ("قرار", "arrete"), ("اتفاقية", "convention"),
 ("معاهدة", "convention"), ("بروتوكول", "convention"), ("منشور", "circulaire"),
 ("مقرر", "decision"), ("dahir", "dahir"), ("décret", "decret"), ("loi", "loi"),
 ("arrêté", "arrete"), ("convention", "convention"),
]

def greg_date(m):
    d = 1 if m.group(1) == "فاتح" else int(m.group(1))
    return f"{m.group(3)}-{GREG[m.group(2)]:02d}-{d:02d}"

def classify(text):
    """Type = mot-clé apparaissant LE PLUS TÔT dans l'en-tête (pas l'ordre de la liste :
    « بناء على الدستور » en visa ne doit pas classer un مرسوم comme constitution)."""
    tl = text[:800].lower()
    best = (10**9, None)
    for kw, dt in DOCTYPE_ORDER:
        p = tl.find(kw)
        if p >= 0 and p < best[0]:
            best = (p, dt)
    return best[1]

# ── index portail ──────────────────────────────────────────────────────────
def load_portal_index():
    """timestamp(13 chiffres) -> (date portail, thème index)"""
    m = {}
    try:
        idx = json.load(open(INDEX, encoding="utf-8"))
    except Exception:
        return m
    for th in idx.get("themes", []):
        for rel in th.get("rels", []):
            dm = re.match(r"(20\d\d)/(\d\d)/(\d\d)/", rel)
            ts = re.search(r"-(\d{13})\.pdf$", rel)
            if ts:
                m[ts.group(1)] = (f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}" if dm else None,
                                  th.get("name"))
    return m

# ── extraction par fichier ─────────────────────────────────────────────────
def extract(path, portal):
    rec = {"path": os.path.relpath(path, ROOT).replace("\\", "/"),
           "theme": os.path.basename(os.path.dirname(path)),
           "flags": []}
    name = os.path.basename(path)
    rec["size"] = os.path.getsize(path)

    # md5 intégral (doublons)
    h = hashlib.md5()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    rec["md5"] = h.hexdigest()

    # couche 1 : index portail
    ts = re.search(r"-(\d{13})\.pdf$", name)
    rec["portal_ts"] = ts.group(1) if ts else None
    if ts and ts.group(1) in portal:
        rec["portal_date"], idx_theme = portal[ts.group(1)]
        if idx_theme and idx_theme != rec["theme"]:
            rec["flags"].append("theme_mismatch_index")
    else:
        rec["portal_date"] = None

    # couche 2 : nom de fichier
    fn = norm(re.sub(r"^\d+_", "", name).rsplit("-", 1)[0])
    rec["title_from_name"] = fn.replace(".pdf", "").strip()
    mn = re.search(r"رقم\s+([\d][\d.\-]{1,12})", fn) or re.search(r"n[°o]\s*([\d][\d.\-\s]{1,12})", fn)
    rec["num_from_name"] = norm_num(mn.group(1)) if mn else None

    # couche 3 : premières pages UTILES (page 1 = souvent couverture quasi vide
    # -> on accumule jusqu'à >=1200 caractères, max 4 pages)
    try:
        d = fitz.open(path)
        rec["pages"] = d.page_count
        parts = []
        for i in range(min(4, d.page_count)):
            parts.append(norm(d[i].get_text()))
            if sum(len(re.sub(r"\s", "", p)) for p in parts) >= 1200:
                break
        t = "\n".join(parts)
        d.close()
    except Exception as e:
        rec["flags"].append("open_error")
        rec["error"] = str(e)[:120]
        return rec

    if len(re.sub(r"\s", "", t)) < 60:
        rec["flags"].append("scanned_no_text")          # -> OCR en Phase C
        return rec

    latin = len(re.findall(r"[A-Za-z]", t)); arab = len(re.findall(r"[؀-ۿ]", t))
    rec["lang"] = "fr" if latin > arab else "ar"
    rx = RXF if rec["lang"] == "fr" else RX

    rec["doc_type"] = classify(t) or classify(fn) or None
    if not rec["doc_type"]:
        rec["flags"].append("doctype_unknown")

    for k in ("dahir", "law", "decree"):
        m = rx.get(k) and rx[k].search(t)
        rec[k + "_num"] = norm_num(m.group(1)) if m else None
    if rec["lang"] == "ar":
        if not rec["decree_num"]:                      # مرسوم ملكي ancien format (1166.66)
            m = RX["decree_royal"].search(t)
            rec["decree_num"] = norm_num(m.group(1)) if m else None
        m = RX["arrete"].search(t)
        rec["arrete_num"] = norm_num(m.group(1)) if m else None
        m = RX["enacts"].search(t)
        rec["enacts_law"] = norm_num(m.group(1)) if m else None
        rec["amends"] = sorted({norm_num(x) for x in RX["amends"].findall(t)}) or None
        m = RX["bo"].search(t)
        rec["bo_issue"] = m.group(1) if m else None
        m = RX["bo_date"].search(t)
        rec["bo_date"] = greg_date(m) if m else None
        # date d'édiction : fiable seulement près de « صادر في » ; sinon fallback SIGNALÉ
        ms = re.search(r"صادر\s+في", t)
        mg = mh = None
        if ms:
            win = t[ms.end(): ms.end() + 160]
            mg = RX["greg"].search(win)
            mh = RX["hijri"].search(win)
        if mg:
            rec["issue_date"], rec["date_src"] = greg_date(mg), "sader_fi"
        else:
            mg = RX["greg"].search(t)
            rec["issue_date"] = greg_date(mg) if mg else None
            rec["date_src"] = "fallback" if mg else None
            if mg:
                rec["flags"].append("date_low_confidence")
        rec["issue_date_hijri"] = mh.group(0)[:40] if mh else None
    else:
        m = RXF["bo"].search(t)
        rec["bo_issue"] = m.group(1) if m else None
        mg = re.search(r"(\d{1,2})(?:er)?\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+(\d{4})", t, re.I)
        FR = {"janvier":1,"février":2,"fevrier":2,"mars":3,"avril":4,"mai":5,"juin":6,"juillet":7,
              "août":8,"aout":8,"septembre":9,"octobre":10,"novembre":11,"décembre":12,"decembre":12}
        rec["issue_date"] = f"{mg.group(3)}-{FR[mg.group(2).lower()]:02d}-{int(mg.group(1)):02d}" if mg else None

    # identifiant principal = numéro PROPRE du document, selon son type
    # (un مرسوم بتطبيق القانون 26.03 a pour numéro 2.04.546, pas 26.03)
    PRIO = {"dahir": ("dahir_num", "law_num", "decree_num", "arrete_num"),
            "loi": ("law_num", "dahir_num", "decree_num", "arrete_num"),
            "loi_organique": ("law_num", "dahir_num", "decree_num", "arrete_num"),
            "decret": ("decree_num", "law_num", "dahir_num", "arrete_num"),
            "decret_loi": ("decree_num", "law_num", "dahir_num", "arrete_num"),
            "arrete": ("arrete_num", "decree_num", "law_num", "dahir_num"),
            "arrete_conjoint": ("arrete_num", "decree_num", "law_num", "dahir_num"),
            "decision_cc": ("arrete_num", "law_num", "dahir_num", "decree_num")}
    order = PRIO.get(rec.get("doc_type"), ("law_num", "dahir_num", "decree_num", "arrete_num"))
    rec["primary_num"] = next((rec.get(k) for k in order if rec.get(k)), None)
    if not rec["primary_num"]:
        rec["flags"].append("no_official_number")
    if not (rec.get("issue_date") or rec.get("portal_date")):
        rec["flags"].append("no_date")

    # conflit nom↔page : seulement si les numéros sont de MÊME famille et diffèrent
    def fam(n):
        if not n: return None
        if re.match(r"^1\.\d{2}\.\d+$", n): return "dahir"
        if re.match(r"^2\.\d{2}\.\d+$", n): return "decree"
        if re.match(r"^\d{1,3}\.\d{2,3}$", n): return "law"
        return "other"
    nn = rec.get("num_from_name")
    page_nums = {rec.get(k) for k in ("law_num","dahir_num","decree_num","arrete_num","enacts_law")} - {None}
    if nn and page_nums and nn not in page_nums:
        if any(fam(nn) == fam(p) for p in page_nums):
            rec["flags"].append("name_page_number_conflict")
        else:
            rec["flags"].append("name_num_not_on_page")   # complémentaire, pas contradictoire
    return rec

# ── agrégats : doublons + chaînes de versions ─────────────────────────────
def aggregate(records):
    by_md5, by_num = defaultdict(list), defaultdict(list)
    for r in records:
        by_md5[r["md5"]].append(r["path"])
        for k in ("law_num", "dahir_num"):
            if r.get(k):
                by_num[k + ":" + r[k]].append(r["path"])
    dups = {k: v for k, v in by_md5.items() if len(v) > 1}
    chains = {k: v for k, v in by_num.items() if len(v) > 1}
    return dups, chains

# ── main ───────────────────────────────────────────────────────────────────
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "sample"
    os.makedirs(OUT, exist_ok=True)
    portal = load_portal_index()
    pdfs = sorted(glob.glob(os.path.join(ROOT, "**", "*.pdf"), recursive=True))
    if mode == "sample":
        random.seed(7)
        pdfs = random.sample(pdfs, min(150, len(pdfs)))
    print(f"mode={mode} files={len(pdfs)} portal_index={len(portal)}")

    records = []
    for i, p in enumerate(pdfs):
        records.append(extract(p, portal))
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(pdfs)}")

    dups, chains = aggregate(records)
    n = len(records)
    ok = [r for r in records if "open_error" not in r["flags"]]
    scanned = [r for r in records if "scanned_no_text" in r["flags"]]
    stats = {
        "total": n, "open_errors": n - len(ok), "scanned": len(scanned),
        "native": len(ok) - len(scanned),
        "has_primary_num": sum(1 for r in records if r.get("primary_num")),
        "has_issue_date": sum(1 for r in records if r.get("issue_date")),
        "has_portal_date": sum(1 for r in records if r.get("portal_date")),
        "has_any_date": sum(1 for r in records if r.get("issue_date") or r.get("portal_date")),
        "has_bo": sum(1 for r in records if r.get("bo_issue")),
        "doctype_known": sum(1 for r in records if r.get("doc_type")),
        "french": sum(1 for r in records if r.get("lang") == "fr"),
        "amends_detected": sum(1 for r in records if r.get("amends")),
        "conflicts_name_page": sum(1 for r in records if "name_page_number_conflict" in r["flags"]),
        "exact_duplicate_groups": len(dups),
        "version_chain_groups": len(chains),
        "review_queue": sum(1 for r in records if any(f in r["flags"] for f in
            ("no_official_number", "name_page_number_conflict", "open_error", "doctype_unknown"))),
    }
    json.dump(records, open(os.path.join(OUT, "catalog.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"duplicates": dups, "chains": chains},
              open(os.path.join(OUT, "version_chains.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    review = [r for r in records if any(f in r["flags"] for f in
              ("no_official_number", "name_page_number_conflict", "open_error", "doctype_unknown"))]
    json.dump(review, open(os.path.join(OUT, "review_queue.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
        for k, v in stats.items():
            pc = f"  ({100*v//n}%)" if isinstance(v, int) and v <= n and k not in (
                "total", "exact_duplicate_groups", "version_chain_groups") else ""
            f.write(f"{k:28s}: {v}{pc}\n")
    print("--- STATS ---")
    for k, v in stats.items():
        print(f"{k:28s}: {v}")
    print(f"written -> {OUT}")

if __name__ == "__main__":
    main()
