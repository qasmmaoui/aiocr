# -*- coding: utf-8 -*-
"""API /api/v1 consommée par e-avocat.

RimLex reste SANS ÉTAT vis-à-vis des dossiers du cabinet : e-avocat détient le
texte, les fichiers et les métadonnées dans son PostgreSQL. Ici on ne stocke que
des vecteurs associés à une référence opaque (`ref`), cloisonnés par `case_ref`.
Une recherche rend des références — seul e-avocat sait les résoudre en texte.

Endpoints :
    POST /api/v1/ocr           {file_base64, filename}  -> {pages[], method}
    POST /api/v1/embed         {texts[]}                -> {embeddings[][]}
    POST /api/v1/complete      {system, user, ...}      -> {text}
    POST /api/v1/index         {case_ref, items[]}      -> {indexed}
    POST /api/v1/search        {case_ref, vector, k}    -> {results[]}
    POST /api/v1/index/delete  {case_ref}               -> {deleted}
    GET  /api/v1/health
"""
from __future__ import annotations

import base64
import hmac
import os
import re
import subprocess
import sys
import tempfile
import uuid

import fitz
import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from qdrant_client.http.models import (Distance, FieldCondition, Filter,
                                       MatchValue, PointStruct, VectorParams)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from rag import store                    # noqa: E402
from rag.answer import CHAT_MODEL, GEN_OPTIONS, OLLAMA_BASE_URL  # noqa: E402
from rag.embeddings import embed_batch   # noqa: E402

# ── Authentification ─────────────────────────────────────────────────────
# L'URL du proxy RunPod est publique : sans jeton, n'importe qui peut faire
# tourner le GPU, lire les références d'un dossier ou effacer son index. Le
# jeton est fourni par l'environnement (cf. start_api.sh) et doit être recopié
# dans e-avocat → Paramètres › IA › « Jeton d'accès RimLex ».
API_TOKEN = os.environ.get("EAVOCAT_API_TOKEN", "").strip()


def require_token(authorization: str = Header(default="")) -> None:
    """Refuse par défaut : un déploiement sans jeton ne doit pas ouvrir l'API."""
    if not API_TOKEN:
        raise HTTPException(503, "EAVOCAT_API_TOKEN non configuré sur le pod")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(value.strip(), API_TOKEN):
        raise HTTPException(401, "jeton invalide")


router = APIRouter(prefix="/api/v1", tags=["e-avocat"])
AUTH = [Depends(require_token)]

CASE_COLLECTION = "ea_case_vectors"
EMBED_DIM = 1024
TESS = "/usr/bin/tesseract"


# ── Cloisonnement ────────────────────────────────────────────────────────
def _ensure_collection() -> None:
    client = store.client()
    names = {c.name for c in client.get_collections().collections}
    if CASE_COLLECTION not in names:
        client.create_collection(
            CASE_COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )


def _case_filter(case_ref: str) -> Filter:
    """Le filtre par dossier n'est jamais optionnel : sans lui, une recherche
    pourrait traverser deux dossiers du cabinet."""
    return Filter(
        must=[FieldCondition(key="case_ref", match=MatchValue(value=case_ref))]
    )


# ── OCR ──────────────────────────────────────────────────────────────────
class OcrIn(BaseModel):
    file_base64: str
    filename: str = "document.pdf"


def _ocr_page(page, tmpdir: str) -> str:
    img = os.path.join(tmpdir, "p.png")
    base = os.path.join(tmpdir, "p")
    page.get_pixmap(dpi=300).save(img)
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    try:
        subprocess.run([TESS, img, base, "-l", "ara+fra", "--psm", "6"],
                       env=env, capture_output=True, timeout=300)
        with open(base + ".txt", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


AR_RE = re.compile(r"[؀-ۿ]")
LAT_RE = re.compile(r"[A-Za-zÀ-ſ]")
WORD_RE = re.compile(r"[A-Za-zÀ-ſ؀-ۿ'’-]{3,}$")


def _usable(text: str) -> bool:
    """La couche texte est-elle du VRAI texte ?

    Un PDF marocain scanné puis « textifié » avec une police à CMap cassée
    rend des centaines de caractères qui ne veulent rien dire ("~7 l~....,J)").
    Un simple seuil de longueur les laissait passer, et l'extraction ne voyait
    alors que les rares mots latins de l'en-tête. On regarde donc la forme :
    du vrai texte est fait de mots, pas de ponctuation dispersée.
    """
    t = (text or "").strip()
    if len(re.sub(r"\s+", "", t)) < 40:
        return False
    tokens = t.split()
    if not tokens:
        return False
    # on retire la ponctuation de bord : « Rabat, » reste un mot
    words = sum(1 for w in tokens if WORD_RE.match(w.strip(".,;:()[]«»\"'’")))
    if words / len(tokens) < 0.45:
        return False
    dense = len(re.sub(r"\s+", "", t)) or 1
    return (len(AR_RE.findall(t)) / dense >= 0.15
            or len(LAT_RE.findall(t)) / dense >= 0.30)


@router.post("/ocr", dependencies=AUTH)
def ocr(inp: OcrIn):
    """Couche texte si elle est exploitable, OCR sinon — page par page."""
    try:
        raw = base64.b64decode(inp.file_base64)
    except Exception:
        raise HTTPException(400, "file_base64 invalide")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "in.pdf")
        with open(path, "wb") as f:
            f.write(raw)
        try:
            doc = fitz.open(path)
        except Exception as e:
            raise HTTPException(422, f"PDF illisible : {e}")
        pages, weak = [], []
        for i, pg in enumerate(doc):
            t = pg.get_text() or ""
            pages.append(t)
            if not _usable(t):
                weak.append(i)
        method = "text"
        if weak:
            method = "ocr" if len(weak) == len(pages) else "mixte"
            for i in weak:
                pages[i] = _ocr_page(doc[i], td)
        doc.close()
    return {"pages": pages, "method": method}


# ── Vectorisation ────────────────────────────────────────────────────────
class EmbedIn(BaseModel):
    texts: list[str]


@router.post("/embed", dependencies=AUTH)
def embed(inp: EmbedIn):
    if not inp.texts:
        return {"embeddings": []}
    if len(inp.texts) > 2000:
        raise HTTPException(413, "trop de textes en une fois (max 2000)")
    out: list[list[float]] = []
    B = 128
    for i in range(0, len(inp.texts), B):
        out.extend(embed_batch(inp.texts[i:i + B]))
    return {"embeddings": out}


# ── Génération encadrée ──────────────────────────────────────────────────
class CompleteIn(BaseModel):
    system: str = ""
    user: str
    max_tokens: int = Field(1200, ge=16, le=4096)
    temperature: float = Field(0.1, ge=0.0, le=1.0)
    json_mode: bool = Field(False, alias="json")

    model_config = {"populate_by_name": True}


@router.post("/complete", dependencies=AUTH)
def complete(inp: CompleteIn):
    msgs = []
    if inp.system:
        msgs.append({"role": "system", "content": inp.system})
    msgs.append({"role": "user", "content": inp.user})
    opts = dict(GEN_OPTIONS)
    opts["temperature"] = inp.temperature
    opts["num_predict"] = inp.max_tokens
    payload = {"model": CHAT_MODEL, "messages": msgs, "stream": False,
               "options": opts}
    if inp.json_mode:
        payload["format"] = "json"
    try:
        r = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=900)
        r.raise_for_status()
        return {"text": r.json()["message"]["content"].strip()}
    except requests.RequestException as e:
        raise HTTPException(503, f"moteur de génération indisponible : {e}")


# ── Index vectoriel par dossier ──────────────────────────────────────────
class IndexItem(BaseModel):
    ref: str
    vector: list[float]


class IndexIn(BaseModel):
    case_ref: str
    items: list[IndexItem]


@router.post("/index", dependencies=AUTH)
def index(inp: IndexIn):
    """Stocke (référence opaque, vecteur). Aucun texte n'est reçu ni conservé."""
    if not inp.items:
        return {"indexed": 0}
    _ensure_collection()
    points = [
        PointStruct(
            # id déterministe : réindexer une pièce remplace ses points
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{inp.case_ref}|{it.ref}")),
            vector=it.vector,
            payload={"case_ref": inp.case_ref, "ref": it.ref},
        )
        for it in inp.items
    ]
    for i in range(0, len(points), 256):
        store.client().upsert(CASE_COLLECTION, points=points[i:i + 256], wait=True)
    return {"indexed": len(points)}


class SearchIn(BaseModel):
    case_ref: str
    vector: list[float]
    k: int = Field(8, ge=1, le=50)


@router.post("/search", dependencies=AUTH)
def search(inp: SearchIn):
    _ensure_collection()
    hits = store.client().query_points(
        CASE_COLLECTION, query=inp.vector, limit=inp.k,
        query_filter=_case_filter(inp.case_ref), with_payload=True,
    ).points
    return {
        "results": [
            {"ref": (h.payload or {}).get("ref"), "score": float(h.score)}
            for h in hits
            if (h.payload or {}).get("ref")
        ]
    }


class DeleteIn(BaseModel):
    case_ref: str


@router.post("/index/delete", dependencies=AUTH)
def drop_case(inp: DeleteIn):
    """Purge de l'index d'un dossier (fin de mandat, suppression côté cabinet)."""
    _ensure_collection()
    store.client().delete(
        CASE_COLLECTION, points_selector=_case_filter(inp.case_ref)
    )
    return {"deleted": True, "case_ref": inp.case_ref}


@router.get("/health")
def health():
    try:
        _ensure_collection()
        cnt = store.client().count(CASE_COLLECTION, exact=True).count
    except Exception as e:
        return {"status": "degraded", "error": str(e)}
    return {"status": "ok", "collection": CASE_COLLECTION, "vectors": cnt,
            "chat_model": CHAT_MODEL}
