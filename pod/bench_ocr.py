# -*- coding: utf-8 -*-
"""Deux mesures qui décident d'une facture de 80 à 500 $.

1. LE PARALLÉLISME TIENT-IL ? On suppose qu'une GPU de 96 Go fait tourner
   4 instances et va 4× plus vite. C'est une hypothèse, pas un fait : l'OCR
   par modèle de vision est limité par le décodage, et rien ne garantit que
   4 flux ne se marchent pas dessus. On mesure 1, 2, 4, 8 flux réels.

2. LE 7B SUFFIT-IL ? Il pèse 6 Go contre 21, tourne 3 à 4× plus vite, et
   16 instances tiennent là où le 32B en met 4. Si sa sortie est proche sur
   NOS scans, la facture est divisée par trois. On compare mot à mot.

    python pod/bench_ocr.py            # les deux mesures
    python pod/bench_ocr.py --seul 7b  # une seule
"""
from __future__ import annotations

import argparse
import base64
import difflib
import json
import os
import re
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

OLLAMA = "http://127.0.0.1:11434/api/generate"
PROMPT = "استخرج النص العربي الكامل من هذه الصفحة حرفيا، دون تعليق ودون ترجمة."
IMGS_DIR = "/workspace/bench_pages"
# on prend des pages VARIÉES : un scan pur, un texte natif, une page dense
SOURCES = [
    "/workspace/rework/input/juris/Chambre_4/2007-265_2005-1-4-68.pdf",
    "/workspace/rework/input/juris/Chambre_4/2007-359_2006-2-4-1185.pdf",
]
DPI = 300


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def preparer() -> list[str]:
    import fitz
    os.makedirs(IMGS_DIR, exist_ok=True)
    out = []
    for src in SOURCES:
        if not os.path.exists(src):
            log(f"ABSENT : {src}")
            continue
        doc = fitz.open(src)
        for p in range(min(3, doc.page_count)):
            dst = os.path.join(
                IMGS_DIR, f"{os.path.basename(src)[:-4]}_p{p+1}.png")
            if not os.path.exists(dst):
                doc[p].get_pixmap(dpi=DPI).save(dst)
            out.append(dst)
        doc.close()
    return out


def ocr(modele: str, img: str, timeout: int = 900) -> tuple[str, float]:
    data = base64.b64encode(open(img, "rb").read()).decode()
    body = json.dumps({
        "model": modele, "prompt": PROMPT, "images": [data], "stream": False,
        "options": {"temperature": 0.0, "num_ctx": 8192, "num_predict": 2000},
    }).encode()
    t0 = time.time()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return r["response"], time.time() - t0


def chauffer(modele: str, img: str) -> None:
    """Le premier appel charge le modèle en VRAM : ne jamais le chronométrer."""
    log(f"  chargement de {modele} en VRAM…")
    _t, dt = ocr(modele, img)
    log(f"  chargé ({dt:.0f} s) — les mesures qui suivent sont à chaud")


def mesure_parallelisme(modele: str, imgs: list[str]) -> None:
    log(f"=== parallélisme · {modele} ===")
    chauffer(modele, imgs[0])
    base = None
    for n in (1, 2, 4, 8):
        lot = [imgs[i % len(imgs)] for i in range(n * 2)]   # 2 pages par flux
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=n) as ex:
            list(ex.map(lambda p: ocr(modele, p), lot))
        dt = time.time() - t0
        pph = len(lot) / dt * 3600
        if base is None:
            base = pph
        log(f"  {n} flux : {len(lot)} pages en {dt:.0f} s · "
            f"{pph:,.0f} pages/h · gain ×{pph/base:.2f}")
    log("  -> si le gain plafonne bien avant le nombre de flux, la grosse GPU "
        "ne se rentabilise pas : rester sur la 5090.")


def mots(t: str) -> list[str]:
    return re.findall(r"\S+", t)


def mesure_7b_vs_32b(imgs: list[str]) -> None:
    log("=== qualité 7b contre 32b, mêmes pages ===")
    chauffer("qwen2.5vl:7b", imgs[0])
    sept = [ocr("qwen2.5vl:7b", p) for p in imgs]
    chauffer("qwen2.5vl:32b", imgs[0])
    trente = [ocr("qwen2.5vl:32b", p) for p in imgs]

    sims, g7, g32 = [], [], []
    for i, (a, b) in enumerate(zip(sept, trente)):
        s = difflib.SequenceMatcher(None, mots(a[0]), mots(b[0])).ratio()
        sims.append(s)
        g7.append(a[1])
        g32.append(b[1])
        log(f"  page {i+1} : similarité {100*s:.1f} % · "
            f"7b {a[1]:.1f} s · 32b {b[1]:.1f} s")
        d = os.path.join(IMGS_DIR, f"cmp_{i+1}")
        open(d + "_7b.txt", "w", encoding="utf-8").write(a[0])
        open(d + "_32b.txt", "w", encoding="utf-8").write(b[0])

    if not sims:
        return
    m = statistics.mean(sims)
    log(f"  MOYENNE : similarité {100*m:.1f} % · "
        f"7b {statistics.mean(g7):.1f} s/page · 32b {statistics.mean(g32):.1f} s/page")
    log(f"  accélération du 7b : ×{statistics.mean(g32)/statistics.mean(g7):.1f}")
    # La similarité seule ne dit pas QUI a raison : les écarts sont à lire.
    log("  -> lisez les fichiers cmp_*_7b.txt / cmp_*_32b.txt : une similarité "
        "de 95 % peut cacher 5 % d'erreurs sur les mots qui comptent.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seul", choices=["par", "7b"])
    a = ap.parse_args()
    imgs = preparer()
    if not imgs:
        sys.exit("aucune page de test — vérifiez les chemins SOURCES")
    log(f"{len(imgs)} pages de test à {DPI} DPI")
    if a.seul != "7b":
        mesure_parallelisme("qwen2.5vl:32b", imgs)
    if a.seul != "par":
        mesure_7b_vs_32b(imgs)
    log("BENCH_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
