# -*- coding: utf-8 -*-
"""Ingestion du « دليل المساطر » dans une collection à part.

Pourquoi une collection distincte : une procédure est une SÉQUENCE, pas un
article. Découpée tous les 1 200 caractères comme un code, elle perdrait le
fil — l'étape 3 remonterait sans l'étape 2, le délai sans l'autorité
compétente. Chaque fiche est donc indexée d'un seul tenant.

Ce qui est vectorisé n'est pas la fiche entière mais son résumé utile — titre,
objet, intitulés d'étapes, délais : c'est là que se trouvent les mots d'une
question. La fiche complète voyage dans le payload et sert à la réponse.

Le guide est daté de 2024 : ses renvois au code de procédure civile visent la
numérotation de 1974, abrogée. Chaque fiche porte donc son état, et les 19
fiches concernées portent le détail des articles visés.
"""
import json
import sys
import uuid

sys.path.insert(0, "/workspace/aiocr")
from rag import store                                      # noqa: E402
from rag.embeddings import embed_batch                     # noqa: E402
from qdrant_client.http.models import (Distance,           # noqa: E402
                                       PointStruct, VectorParams)

COLLECTION = "adala_procedures"
CORPUS = "/workspace/data/laws_corpus_v2.jsonl"
GUIDE = "دليل المساطر — وزارة العدل (مشروع محكمتي)"
ANNEE = "2024"
DIM = 1024

fiches = json.load(open("/workspace/fiches_enrichies.json", encoding="utf-8"))
print(f"{len(fiches)} fiches à indexer", flush=True)

client = store.client()
noms = {c.name for c in client.get_collections().collections}
if COLLECTION not in noms:
    client.create_collection(
        COLLECTION,
        vectors_config=VectorParams(size=DIM, distance=Distance.COSINE))
    print("collection créée :", COLLECTION, flush=True)


def texte_recherchable(f: dict) -> str:
    """Ce sur quoi porte la recherche : les mots qu'un avocat emploierait."""
    bouts = [f["titre"], f.get("objet") or ""]
    bouts += [e["intitule"] for e in f["etapes"]]
    if f.get("delais"):
        bouts.append("الآجال: " + f["delais"])
    if f.get("documents"):
        bouts.append("الوثائق: " + f["documents"])
    return "\n".join(b for b in bouts if b)[:2500]


def texte_complet(f: dict) -> str:
    """Ce qui est servi au moteur pour composer la réponse."""
    out = [f"المسطرة: {f['titre']}"]
    for cle, libelle in (("objet", "موضوع ونطاق التطبيق"),
                         ("cadre_legal", "الإطار القانوني"),
                         ("delais", "الآجال"),
                         ("documents", "الوثائق"),
                         ("prerequis", "المتطلبات القبلية")):
        if f.get(cle):
            out.append(f"{libelle}: {f[cle]}")
    # Une procédure se scinde parfois en cas (« الحالة 1 : … ») : sans ce
    # rappel, deux séquences distinctes se liraient comme une seule suite.
    cas_courant = None
    for e in f["etapes"]:
        if e.get("cas") and e["cas"] != cas_courant:
            cas_courant = e["cas"]
            out.append(f"— الحالة: {cas_courant}")
        acteur = f" ({e['acteur']})" if e.get("acteur") else ""
        out.append(f"إجراء {e['numero']}: {e['intitule']}{acteur}")
        out += [f"   - {a}" for a in e["actions"]]
    return "\n".join(out)


recherchables = [texte_recherchable(f) for f in fiches]
vecteurs = []
for i in range(0, len(recherchables), 32):
    vecteurs.extend(embed_batch(recherchables[i:i + 32]))
print("vectorisation terminée", flush=True)

points, lignes = [], []
for f, v in zip(fiches, vecteurs):
    abroge = [r for r in f["renvois"] if r.get("etat") == "abroge"]
    payload = {
        "type": "procedure",
        "titre": f["titre"],
        "text": texte_complet(f),
        "law": GUIDE,
        # nom ASCII : le titre arabe ne survit pas proprement à une URL,
        # et le lien « voir la source » doit rester ouvrable
        "file": "guide_masatir_2024.pdf",
        "pdf": "guide_masatir_2024.pdf",
        "guide_annee": ANNEE,
        "page": str(f["page"]),
        "numero": str(f["numero"]),
        "etapes": json.dumps(f["etapes"], ensure_ascii=False),
        "renvois": json.dumps(f["renvois"], ensure_ascii=False),
        "delais": f.get("delais") or "",
        "documents": f.get("documents") or "",
        "cadre_legal": f.get("cadre_legal") or "",
        # une fiche adossée à un texte abrogé doit se signaler d'elle-même
        "status": "check_amendments" if abroge else "current",
    }
    if abroge:
        payload["pending_amendments"] = ["58.25"]
    points.append(PointStruct(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"procedure|{f['numero']}|{f['page']}")),
        vector=v, payload=payload))
    lignes.append(json.dumps({
        "collection": COLLECTION, "file": payload["file"],
        "chunk": f["page"], "law": GUIDE, "article": f["titre"],
        "text": payload["text"], "page": f["page"],
        "status": payload["status"],
    }, ensure_ascii=False))

for i in range(0, len(points), 64):
    client.upsert(COLLECTION, points=points[i:i + 64], wait=True)
print("Qdrant :", client.count(COLLECTION, exact=True).count, "fiches", flush=True)

# On retire d'abord une éventuelle ingestion précédente du guide.
gardees = [l for l in open(CORPUS, encoding="utf-8")
           if '"guide_masatir_2024.pdf"' not in l]
with open(CORPUS, "w", encoding="utf-8") as fh:
    fh.writelines(gardees)
    fh.write("\n".join(lignes) + "\n")
print(f"corpus lexical : +{len(lignes)} fiches", flush=True)

nb = sum(1 for f in fiches if any(r.get("etat") == "abroge" for r in f["renvois"]))
print(f"fiches signalées comme adossées à un texte abrogé : {nb}")
