#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batterie de questions de contrôle contre RimLex — mesure et diagnostic.

Pour chaque question : latence, nombre et nature des sources (loi /
jurisprudence), langue de la réponse, présence de citations, et détection des
réponses « je n'ai pas trouvé ». Sortie JSON + résumé lisible.

Usage: python3 qa_probe.py [out.json]
"""
import json
import re
import sys
import time
import urllib.request

API = "http://127.0.0.1:8888"
AR = re.compile(r"[؀-ۿ]")
LAT = re.compile(r"[A-Za-zÀ-ÿ]")
NOT_FOUND = ("لم أعثر", "لم أجد", "ne trouve pas", "aucun texte")
CITE = re.compile(r"(المادة|الفصل)\s*\d+|article\s*\d+", re.I)

QUESTIONS = [
    ("art_392",       "ماذا ينص الفصل 392 من القانون الجنائي؟"),
    ("art_528",       "ماذا تنص المادة 528 من قانون المسطرة الجنائية؟"),
    ("art_166",       "ماذا تنص المادة 166 من مدونة الأسرة؟"),
    ("hadana",        "ما مدة الحضانة ومن له حق اختيار الحاضن؟"),
    ("preavis",       "ما هي مدة الإشعار المسبق عند إنهاء عقد الشغل غير محدد المدة؟"),
    ("garde_vue",     "ما هي مدة الحراسة النظرية وهل يمكن تمديدها؟"),
    ("chiqaq",        "ما هي مسطرة التطليق للشقاق؟"),
    ("cheque",        "ما عقوبة إصدار شيك بدون رصيد؟"),
    ("expropriation", "ما هي مسطرة نزع الملكية لأجل المنفعة العامة؟"),
    ("juris_licenc",  "ما موقف محكمة النقض من الفصل التعسفي للأجير؟"),
    ("fr_saisie",     "Quelle est la procédure de la saisie conservatoire en droit marocain ?"),
    ("fr_bail",       "Quelles sont les obligations du bailleur dans un bail commercial ?"),
    ("fr_penal",      "Quelles sont les peines prévues pour abus de confiance ?"),
    ("hors_sujet",    "كيف أطبخ الكسكس بالخضر؟"),
    ("ambigu",        "ما هي المدة القانونية؟"),
]

FOLLOWUP = [
    ("ctx_1", "ما هي عقوبة النصب؟"),
    ("ctx_2", "وما هي الظروف المشددة؟"),
    ("ctx_3", "والوثائق المطلوبة لتقديم شكاية؟"),
]


def post(path, payload, timeout=600):
    req = urllib.request.Request(API + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def lang_of(t):
    a, l = len(AR.findall(t or "")), len(LAT.findall(t or ""))
    return "ar" if a >= l else "fr"


def probe(qid, q, session=None):
    if session is None:
        try:
            session = post("/api/sessions", {}).get("session_id")
        except Exception:
            session = None
    t0 = time.time()
    try:
        d = post("/api/chat", {"question": q, "k": 6,
                               **({"session_id": session} if session else {})})
    except Exception as e:
        return {"id": qid, "q": q, "error": repr(e), "sec": round(time.time() - t0, 1)}
    a = d.get("answer") or ""
    srcs = d.get("sources") or []
    return {
        "id": qid, "q": q, "sec": round(time.time() - t0, 1),
        "answer": a, "search_query": d.get("search_query"),
        "n_sources": len(srcs),
        "n_loi": sum(1 for s in srcs if s.get("kind") == "loi"),
        "n_juris": sum(1 for s in srcs if s.get("kind") == "jurisprudence"),
        "lang_q": lang_of(q), "lang_a": lang_of(a),
        "has_citation": bool(CITE.search(a)),
        "not_found": any(m in a for m in NOT_FOUND),
        "top_sources": [{"law": s.get("law", "")[:45], "art": s.get("article"),
                         "page": s.get("page"), "kind": s.get("kind"),
                         "score": s.get("score")} for s in srcs[:4]],
    }


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/workspace/qa_probe.json"
    res = []
    for qid, q in QUESTIONS:
        r = probe(qid, q)
        res.append(r)
        print(f"[{r['sec']:6.1f}s] {qid:16s} src={r.get('n_sources','-')} "
              f"(loi {r.get('n_loi','-')}/juris {r.get('n_juris','-')}) "
              f"lang {r.get('lang_q')}→{r.get('lang_a')} "
              f"cite={r.get('has_citation')} notfound={r.get('not_found')}", flush=True)
    # suivi conversationnel (une seule session)
    sid = post("/api/sessions", {}).get("session_id")
    for qid, q in FOLLOWUP:
        r = probe(qid, q, session=sid)
        r["session"] = sid
        res.append(r)
        print(f"[{r['sec']:6.1f}s] {qid:16s} search_q={str(r.get('search_query'))[:60]}",
              flush=True)
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("written", out)


if __name__ == "__main__":
    main()
