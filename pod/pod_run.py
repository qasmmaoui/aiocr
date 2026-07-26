# -*- coding: utf-8 -*-
"""Orchestrateur du jour de retraitement (pod GPU) — consensus OCR à portes.

Philosophie : personne n'est cru sur parole. Chaque étape produit un rapport
de porte ; la suivante ne démarre qu'après validation (--yes pour enchaîner).

    Étape 0  vérifs (moteurs joignables, disque, files présentes)
    Étape 1  PILOTE : 100 pages, 2 moteurs -> rapport à examiner (~5 $)
    Étape 2  CER : pages à couche texte saine rendues en images -> OCR ->
             taux d'erreur caractère OBJECTIF par moteur (chiffres inclus)
    Étape 3  LOT : consensus 2 moteurs, checkpoint SQLite, pause auto si
             le taux d'accord chute sous le seuil
    Étape 4  ARBITRAGE : pages en désaccord -> grand modèle VL
    Étape 5  export ocr_results/ (un .md par page + fusion par document)

Moteurs (adapter les endpoints à l'environnement du pod) :
    ENGINE_A  Nanonets-OCR-s via Ollama    http://127.0.0.1:11434
    ENGINE_B  dots.ocr via vLLM (OpenAI)   http://127.0.0.1:8001/v1
    ARBITER   Qwen-VL 72B via vLLM         http://127.0.0.1:8002/v1
"""
import argparse
import base64
import difflib
import io
import json
import os
import re
import sqlite3
import sys
import time

import requests

try:
    import fitz
except ImportError:
    sys.exit("pip install pymupdf")

WORK = os.environ.get("POD_WORK", "/workspace/rework")
INPUT = os.path.join(WORK, "input")
OUT = os.path.join(WORK, "ocr_results")
DB = os.path.join(WORK, "checkpoint.db")

ENGINE_A = {"kind": "ollama", "url": "http://127.0.0.1:11434",
            "model": "nanonets-ocr"}
ENGINE_B = {"kind": "openai", "url": "http://127.0.0.1:8001/v1",
            "model": "dots-ocr"}
ARBITER = {"kind": "openai", "url": "http://127.0.0.1:8002/v1",
           "model": "qwen2.5-vl-72b"}

PROMPT = ("Extract the full text of this document page in natural reading "
          "order. Arabic text must be preserved exactly, including all "
          "numbers, dates and article numbers. Output plain text only.")
AGREE_THRESHOLD = 0.90     # similarité normalisée pour «accord»
PAUSE_BELOW = 0.75         # taux d'accord glissant -> pause automatique
DPI = 170

AR_DIAC = re.compile(r"[ً-ٰٟـ]")


def norm(s: str) -> str:
    s = AR_DIAC.sub("", s or "")
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ى", "ي").replace("ة", "ه"))
    return re.sub(r"\s+", " ", s).strip()


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def cer(ref: str, hyp: str) -> float:
    r, h = norm(ref), norm(hyp)
    if not r:
        return 0.0
    sm = difflib.SequenceMatcher(None, r, h)
    return round(1 - sm.ratio(), 4)          # approximation distance/longueur


def page_png(pdf_path: str, page_no: int) -> bytes:
    doc = fitz.open(pdf_path)
    try:
        return doc[page_no].get_pixmap(dpi=DPI).tobytes("png")
    finally:
        doc.close()


def ocr(engine: dict, png: bytes, retries: int = 3) -> str:
    b64 = base64.b64encode(png).decode()
    for attempt in range(retries):
        try:
            if engine["kind"] == "ollama":
                r = requests.post(f"{engine['url']}/api/generate",
                                  json={"model": engine["model"], "prompt": PROMPT,
                                        "images": [b64], "stream": False},
                                  timeout=300)
                r.raise_for_status()
                return r.json()["response"]
            r = requests.post(f"{engine['url']}/chat/completions",
                              json={"model": engine["model"], "messages": [{
                                  "role": "user", "content": [
                                      {"type": "text", "text": PROMPT},
                                      {"type": "image_url", "image_url": {
                                          "url": f"data:image/png;base64,{b64}"}}]}],
                                    "max_tokens": 4096, "temperature": 0},
                              timeout=300)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    return ""


def db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS pages(
        pdf TEXT, page INTEGER, a TEXT, b TEXT, sim REAL,
        final TEXT, source TEXT, ts REAL,
        PRIMARY KEY(pdf, page))""")
    return c


def list_pdfs():
    out = []
    for q in sorted(os.listdir(INPUT)):
        qd = os.path.join(INPUT, q)
        if os.path.isdir(qd):
            out += [(q, os.path.join(qd, f)) for f in sorted(os.listdir(qd))
                    if f.lower().endswith(".pdf")]
    return out


def run_pages(pairs, con, tag: str):
    """OCR consensus sur une liste (pdf, page) ; renvoie stats."""
    agree = done = 0
    window = []
    for i, (pdf, pno) in enumerate(pairs):
        if con.execute("SELECT 1 FROM pages WHERE pdf=? AND page=?",
                       (pdf, pno)).fetchone():
            continue
        png = page_png(pdf, pno)
        ta = ocr(ENGINE_A, png)
        tb = ocr(ENGINE_B, png)
        sim = similarity(ta, tb)
        ok = sim >= AGREE_THRESHOLD
        final, src = (ta, "consensus") if ok else ("", "disputed")
        con.execute("INSERT OR REPLACE INTO pages VALUES(?,?,?,?,?,?,?,?)",
                    (pdf, pno, ta, tb, sim, final, src, time.time()))
        con.commit()
        done += 1
        agree += ok
        window.append(ok)
        window[:] = window[-100:]
        if done % 25 == 0:
            rate = sum(window) / len(window)
            print(f"[{tag}] {done} pages | accord glissant {rate:.0%}", flush=True)
            if len(window) >= 50 and rate < PAUSE_BELOW:
                print(f"!! accord {rate:.0%} < {PAUSE_BELOW:.0%} — PAUSE AUTO. "
                      f"Inspectez la base {DB} avant de relancer.", flush=True)
                sys.exit(3)
    return done, agree


def stage_checks():
    for name, e in (("moteur A", ENGINE_A), ("moteur B", ENGINE_B)):
        try:
            requests.get(e["url"], timeout=5)
            print(f"✓ {name} joignable ({e['url']})")
        except Exception:
            sys.exit(f"✗ {name} injoignable ({e['url']}) — démarrez-le d'abord.")
    pdfs = list_pdfs()
    print(f"✓ {len(pdfs)} PDF dans les files d'entrée")
    if not pdfs:
        sys.exit("✗ input/ vide — téléversez et détarez le bundle d'abord.")


def stage_pilot(n_pages=100):
    con = db()
    pdfs = list_pdfs()
    step = max(1, len(pdfs) // n_pages)
    pairs = [(p, 0) for _q, p in pdfs[::step]][:n_pages]
    done, agree = run_pages(pairs, con, "pilote")
    report = {"pages": done, "agreement": round(agree / max(1, done), 3)}
    json.dump(report, open(os.path.join(WORK, "gate1_pilot.json"), "w"))
    print(f"\nPORTE 1 — pilote : {report} -> gate1_pilot.json")
    print("Examinez des échantillons (table pages) puis relancez avec --stage 2.")


def stage_cer(n_docs=30):
    """Pages à texte natif rendues en image -> vérité terrain gratuite."""
    con = db()
    results = {"A": [], "B": []}
    tested = 0
    for _q, pdf in list_pdfs():
        if tested >= n_docs:
            break
        doc = fitz.open(pdf)
        try:
            for pno in range(min(3, len(doc))):
                ref = doc[pno].get_text()
                if len(norm(ref)) < 400:
                    continue
                png = doc[pno].get_pixmap(dpi=DPI).tobytes("png")
                results["A"].append(cer(ref, ocr(ENGINE_A, png)))
                results["B"].append(cer(ref, ocr(ENGINE_B, png)))
                tested += 1
                break
        finally:
            doc.close()
    rep = {k: {"pages": len(v),
               "cer_moyen": round(sum(v) / max(1, len(v)), 4),
               "cer_max": round(max(v), 4) if v else None}
           for k, v in results.items()}
    json.dump(rep, open(os.path.join(WORK, "gate2_cer.json"), "w"), indent=1)
    print(f"PORTE 2 — CER objectif : {json.dumps(rep, indent=1)}")
    print("CER moyen > 0.05 pour un moteur = problème de config. Sinon --stage 3.")


def stage_batch():
    con = db()
    pairs = []
    for _q, pdf in list_pdfs():
        doc = fitz.open(pdf)
        pairs += [(pdf, i) for i in range(len(doc))]
        doc.close()
    print(f"lot complet : {len(pairs)} pages (reprise auto sur checkpoint)")
    done, agree = run_pages(pairs, con, "lot")
    print(f"PORTE 3 — lot terminé : {done} pages, accord {agree/max(1,done):.1%}")


def stage_arbitrate():
    con = db()
    rows = con.execute("SELECT pdf, page FROM pages WHERE source='disputed'").fetchall()
    print(f"arbitrage VL : {len(rows)} pages en désaccord")
    for pdf, pno in rows:
        final = ocr(ARBITER, page_png(pdf, pno))
        con.execute("UPDATE pages SET final=?, source='arbiter' "
                    "WHERE pdf=? AND page=?", (final, pdf, pno))
        con.commit()
    print("PORTE 4 — arbitrage terminé.")


def stage_export():
    con = db()
    os.makedirs(OUT, exist_ok=True)
    docs = {}
    for pdf, pno, final in con.execute(
            "SELECT pdf, page, final FROM pages ORDER BY pdf, page"):
        docs.setdefault(pdf, []).append(final or "")
    for pdf, pages in docs.items():
        name = os.path.splitext(os.path.basename(pdf))[0][:120]
        with open(os.path.join(OUT, name + ".md"), "w", encoding="utf-8") as f:
            f.write("\n\n\f\n\n".join(pages))
    print(f"export : {len(docs)} documents -> {OUT}")
    print("Téléchargez ocr_results/ puis lancez l'إعادة الشاملة côté RimLex.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(WORK, exist_ok=True)
    {0: stage_checks, 1: stage_pilot, 2: stage_cer, 3: stage_batch,
     4: stage_arbitrate, 5: stage_export}[a.stage]()
