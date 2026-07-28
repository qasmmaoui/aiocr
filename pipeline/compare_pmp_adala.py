# -*- coding: utf-8 -*-
"""Comparaison PMP vs adala : quelle édition de chaque loi garder ?

Pour chaque texte présent des deux côtés (appariement par numéro officiel,
sinon par titre normalisé), on mesure :
  · ACTUALITÉ   dernière année citée dans le texte + mentions d'amendement
  · QUALITÉ     artefacts de ligature arabe (lettres permutées à l'extraction)
  · COMPLÉTUDE  pages, articles/فصول distincts, volume de mots

Sortie : comparaison_pmp_adala.csv + verdict par paire et global.
"""
import csv
import os
import re
from collections import defaultdict

import fitz

PMP = r"Z:\PMP_Textes"
ADALA = [r"Y:\adala-project\adala_pdfs", r"Y:\adala-project\laws"]
OUT = r"Y:\adala-project\aiocr_data\comparaison_pmp_adala.csv"

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
AR_WORD = re.compile(r"[؀-ۿ]{2,}")
# lettres permutées par l'extraction (ال collé à l'envers) : «العقوابت», «اجلنايئ»
LIG = re.compile(r"(?<![؀-ۿ])[وفبلك]?ا[أإآبتثجحخدذرزسشصضطظعغفقمنهي]ل[؀-ۿ]")
NUM = re.compile(r"(?:القانون|قانون|الظهير|ظهير|المرسوم|مرسوم)[^\n]{0,20}?رقم\s*"
                 r"([0-9]{1,3}[./][0-9]{2,4}(?:[./][0-9]{1,4})?)")
YEAR = re.compile(r"\b(19[5-9][0-9]|20[0-4][0-9])\b")
ART = re.compile(r"(?:الفصل|المادة)\s*([0-9]{1,4})")


def norm_title(name: str) -> str:
    n = os.path.splitext(name)[0].translate(AR_DIGITS)
    n = re.sub(r"^\d{1,3}[-_]", "", n)              # préfixes de tri
    n = re.sub(r"-\d{10,}$", "", n)                 # horodatages
    n = n.replace("-", " ").replace("_", " ")
    n = re.sub(r"[ًٌٍَُِّْـ]", "", n)
    n = (n.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ى", "ي").replace("ة", "ه"))
    return re.sub(r"\s+", " ", n).strip()


def profile(path: str) -> dict | None:
    try:
        doc = fitz.open(path)
        pages = len(doc)
        txt = "".join(p.get_text() for p in doc).translate(AR_DIGITS)
        doc.close()
    except Exception:
        return None
    words = AR_WORD.findall(txt)
    if not words:
        return {"pages": pages, "mots": 0, "lig": 1.0, "annee": 0,
                "articles": 0, "nums": set(), "octets": os.path.getsize(path)}
    years = [int(y) for y in YEAR.findall(txt)]
    return {
        "pages": pages,
        "mots": len(words),
        "lig": len(LIG.findall(txt)) / len(words),
        "annee": max(years) if years else 0,
        "articles": len(set(ART.findall(txt))),
        "nums": {m.replace("/", ".") for m in NUM.findall(txt[:3000])},
        "octets": os.path.getsize(path),
    }


def main() -> None:
    pmp = {}
    for f in sorted(os.listdir(PMP)):
        if f.lower().endswith(".pdf"):
            pmp[f] = norm_title(f)

    # index adala par titre normalisé et par numéro officiel du titre
    adala = {}
    for root in ADALA:
        for dp, _dn, fn in os.walk(root):
            if "incoming" in dp:            # les copies PMP déjà mises en scène
                continue
            for f in fn:
                if f.lower().endswith(".pdf"):
                    adala.setdefault(norm_title(f), []).append(os.path.join(dp, f))

    def candidats(titre_pmp: str) -> list[str]:
        if titre_pmp in adala:
            return adala[titre_pmp]
        mots = [w for w in titre_pmp.split() if len(w) > 3][:6]
        if len(mots) < 3:
            return []
        out = []
        for t, paths in adala.items():
            if sum(1 for w in mots if w in t) >= max(3, len(mots) - 2):
                out += paths
        return out[:3]

    rows, tally = [], defaultdict(int)
    for f, titre in pmp.items():
        cands = candidats(titre)
        p1 = profile(os.path.join(PMP, f))
        if not p1:
            continue
        if not cands:
            tally["pmp_seul"] += 1
            rows.append([f[:70], "—", p1["pages"], "", f"{p1['lig']:.1%}", "",
                         p1["annee"], "", p1["articles"], "", "PMP seul"])
            continue
        best, bp = None, None
        for c in cands:                     # meilleure contrepartie adala
            p2 = profile(c)
            if p2 and (bp is None or (p2["annee"], -p2["lig"]) > (bp["annee"], -bp["lig"])):
                best, bp = c, p2
        if not bp:
            continue
        verdict = []
        if bp["annee"] > p1["annee"] + 1:
            verdict.append("adala plus récent")
        elif p1["annee"] > bp["annee"] + 1:
            verdict.append("PMP plus récent")
        if p1["lig"] > bp["lig"] * 1.5 and p1["lig"] > 0.02:
            verdict.append("adala mieux extrait")
        elif bp["lig"] > p1["lig"] * 1.5 and bp["lig"] > 0.02:
            verdict.append("PMP mieux extrait")
        if not verdict:
            verdict.append("équivalents")
        v = " + ".join(verdict)
        tally[v] += 1
        rows.append([f[:70], os.path.basename(best)[:70], p1["pages"], bp["pages"],
                     f"{p1['lig']:.1%}", f"{bp['lig']:.1%}", p1["annee"],
                     bp["annee"], p1["articles"], bp["articles"], v])

    with open(OUT, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["fichier PMP", "contrepartie adala", "pages PMP", "pages adala",
                    "ligature PMP", "ligature adala", "année PMP", "année adala",
                    "articles PMP", "articles adala", "verdict"])
        w.writerows(rows)

    print(f"{len(rows)} textes comparés -> {OUT}\n")
    for k, n in sorted(tally.items(), key=lambda x: -x[1]):
        print(f"  {n:4d}  {k}")
    print("\nCas où adala l'emporte nettement :")
    for r in rows:
        if "adala" in r[-1] and r[1] != "—":
            print(f"   {r[0][:55]}")
            print(f"      PMP  : {r[2]} p · lig {r[4]} · {r[6]} · {r[8]} art.")
            print(f"      adala: {r[3]} p · lig {r[5]} · {r[7]} · {r[9]} art.")


if __name__ == "__main__":
    main()
