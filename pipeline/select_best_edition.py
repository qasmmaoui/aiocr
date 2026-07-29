# -*- coding: utf-8 -*-
"""Sélection de la meilleure édition de chaque loi (PMP vs adala vs laws).

Beaucoup de textes existent en plusieurs exemplaires : collection PMP,
scrape adala, corpus laws. Aucun n'est systématiquement meilleur — PMP est
souvent mieux extrait, adala plus souvent à jour. On choisit donc copie par
copie, sur des critères mesurés :

    1. COMPLÉTUDE     nombre d'articles/فصول distincts (poids décisif : une
                      copie partielle ou un simple texte modificatif perd)
    2. EXTRACTION     taux d'artefacts de ligature arabe (lettres permutées)
    3. ACTUALITÉ      dernière année citée dans le texte
    4. VOLUME         mots arabes (départage les ex æquo)

Sorties :
    editions_choisies.json   {clé_loi: {retenu, écartés[], raisons}}
    editions_a_arbitrer.csv  cas serrés -> décision humaine dans la console
Aucun fichier n'est déplacé ni supprimé : le pipeline lit ce choix.
"""
import csv
import json
import os
import re
from collections import defaultdict

import fitz

SOURCES = [
    ("pmp", r"Z:\PMP_Textes"),
    ("adala", r"Y:\adala-project\adala_pdfs"),
    ("laws", r"Y:\adala-project\laws"),
]
OUT_JSON = r"Y:\adala-project\aiocr_data\editions_choisies.json"
OUT_CSV = r"Y:\adala-project\aiocr_data\editions_a_arbitrer.csv"

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
AR_WORD = re.compile(r"[؀-ۿ]{2,}")
LIG = re.compile(r"(?<![؀-ۿ])[وفبلك]?ا[أإآبتثجحخدذرزسشصضطظعغفقمنهي]ل[؀-ۿ]")
NUM = re.compile(r"(?:القانون|قانون|الظهير|ظهير|المرسوم|مرسوم|القرار)"
                 r"[^\n]{0,25}?رقم\s*([0-9]{1,3}[./][0-9]{2,4}(?:[./][0-9]{1,4})?)")
YEAR = re.compile(r"\b(19[5-9][0-9]|20[0-4][0-9])\b")
ART = re.compile(r"(?:الفصل|المادة)\s*([0-9]{1,4})")


def norm_title(name: str) -> str:
    n = os.path.splitext(name)[0].translate(AR_DIGITS)
    n = re.sub(r"^\d{1,3}[-_]", "", n)
    n = re.sub(r"[-_]\d{10,}$", "", n)
    n = n.replace("-", " ").replace("_", " ")
    n = re.sub(r"[ًٌٍَُِّْـ]", "", n)
    n = (n.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ى", "ي").replace("ة", "ه"))
    return re.sub(r"\s+", " ", n).strip()


def profile(path: str) -> dict:
    try:
        doc = fitz.open(path)
        pages = len(doc)
        txt = "".join(p.get_text() for p in doc).translate(AR_DIGITS)
        head = doc[0].get_text().translate(AR_DIGITS)[:600] if pages else ""
        doc.close()
    except Exception:
        return {}
    words = AR_WORD.findall(txt)
    years = [int(y) for y in YEAR.findall(txt)]
    return {
        "path": path, "pages": pages, "mots": len(words),
        "lig": (len(LIG.findall(txt)) / len(words)) if words else 1.0,
        "annee": max(years) if years else 0,
        "articles": len(set(ART.findall(txt))),
        "scan": len(words) < 200,          # pas de couche texte exploitable
        "num": (NUM.search(head).group(1).replace("/", ".")
                if NUM.search(head) else ""),
    }


def cle(p: dict, titre: str) -> str:
    """Regroupe les exemplaires d'une même loi : numéro officiel sinon titre."""
    return f"num:{p['num']}" if p.get("num") else f"titre:{titre}"


def score(p: dict) -> tuple:
    """Ordre de préférence — complétude d'abord, propreté ensuite."""
    return (p["articles"], -round(p["lig"], 3), p["annee"], p["mots"])


def main() -> None:
    groupes = defaultdict(list)
    for src, root in SOURCES:
        if not os.path.isdir(root):
            continue
        for dp, _dn, fn in os.walk(root):
            for f in fn:
                if not f.lower().endswith(".pdf"):
                    continue
                p = profile(os.path.join(dp, f))
                if not p:
                    continue
                p["source"] = src
                p["nom"] = f
                groupes[cle(p, norm_title(f))].append(p)
        print(f"  {src} : {sum(len(v) for v in groupes.values())} exemplaires cumulés",
              flush=True)

    choisies, arbitrer, stats = {}, [], defaultdict(int)
    for k, exemplaires in groupes.items():
        if len(exemplaires) == 1:
            e = exemplaires[0]
            choisies[k] = {"retenu": e["path"], "source": e["source"],
                           "articles": e["articles"], "lig": round(e["lig"], 3),
                           "annee": e["annee"], "ecartes": [],
                           "raison": "exemplaire unique"}
            stats[f"unique ({e['source']})"] += 1
            continue
        classes = sorted(exemplaires, key=score, reverse=True)
        best, second = classes[0], classes[1]
        raisons = []
        if best["articles"] > second["articles"] * 1.2:
            raisons.append(f"plus complet ({best['articles']} vs {second['articles']} art.)")
        if best["lig"] < second["lig"] * 0.7:
            raisons.append(f"mieux extrait ({best['lig']:.1%} vs {second['lig']:.1%})")
        if best["annee"] > second["annee"]:
            raisons.append(f"plus récent ({best['annee']} vs {second['annee']})")
        if not raisons:
            raisons.append("départage au volume")
        choisies[k] = {
            "retenu": best["path"], "source": best["source"],
            "articles": best["articles"], "lig": round(best["lig"], 3),
            "annee": best["annee"],
            "ecartes": [e["path"] for e in classes[1:]],
            "raison": " · ".join(raisons),
        }
        stats[f"choisi: {best['source']}"] += 1
        # cas serré : mérite un œil humain
        serre = (abs(best["articles"] - second["articles"]) <= 2
                 and abs(best["annee"] - second["annee"]) >= 3)
        if serre or (best["scan"] and not second["scan"]):
            arbitrer.append([
                k, best["source"], os.path.basename(best["path"])[:60],
                best["articles"], f"{best['lig']:.1%}", best["annee"],
                second["source"], os.path.basename(second["path"])[:60],
                second["articles"], f"{second['lig']:.1%}", second["annee"]])

    json.dump(choisies, open(OUT_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["clé", "source retenue", "fichier retenu", "articles",
                    "ligature", "année", "source écartée", "fichier écarté",
                    "articles", "ligature", "année"])
        w.writerows(arbitrer)

    print(f"\n{len(groupes)} lois distinctes · {len(choisies)} éditions retenues")
    for k, n in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"   {n:5d}  {k}")
    print(f"\ncas à arbitrer : {len(arbitrer)} -> {OUT_CSV}")
    print(f"choix complet : {OUT_JSON}")


if __name__ == "__main__":
    main()
