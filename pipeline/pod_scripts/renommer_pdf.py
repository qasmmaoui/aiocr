# -*- coding: utf-8 -*-
"""Aligne le nom du PDF des fiches sur celui que l'API sert réellement.

Le guide a été déposé sous /api/pdf/guide_masatir_2024.pdf (nom ASCII : le nom
arabe d'origine ne survit pas proprement à une URL). Les fiches doivent porter
ce nom, sinon le lien « voir la source » ne mène nulle part et la marche à
suivre devient invérifiable.
"""
import json
import sys

sys.path.insert(0, "/workspace/aiocr")
from rag import store  # noqa: E402

ANCIEN = "دليل المساطر-2024.pdf"
NOUVEAU = "guide_masatir_2024.pdf"
COLLECTION = "adala_procedures"
CORPUS = "/workspace/data/laws_corpus_v2.jsonl"

client = store.client()
pts, _ = client.scroll(COLLECTION, limit=500, with_payload=True, with_vectors=False)
print(f"{len(pts)} fiches à corriger")
client.set_payload(COLLECTION, payload={"file": NOUVEAU, "pdf": NOUVEAU},
                   points=[p.id for p in pts], wait=True)
ech = client.retrieve(COLLECTION, ids=[pts[0].id], with_payload=True)[0].payload
print("payload vérifié :", {k: ech.get(k) for k in ("file", "pdf", "page", "titre")})

n = 0
out = []
for line in open(CORPUS, encoding="utf-8"):
    if ANCIEN in line:
        r = json.loads(line)
        r["file"] = NOUVEAU
        line = json.dumps(r, ensure_ascii=False)
        n += 1
        out.append(line)
    else:
        out.append(line.rstrip("\n"))
with open(CORPUS, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out) + "\n")
print(f"corpus lexical : {n} lignes renommées")
