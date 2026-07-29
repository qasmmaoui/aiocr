"""
╔══════════════════════════════════════════════════════════════╗
║  DMSI · Adala — FastAPI Backend                              ║
║  api/main.py                                                 ║
╚══════════════════════════════════════════════════════════════╝
Routes :
    POST /api/upload           — Upload + extraction + indexation
    GET  /api/search           — Recherche full-text
    GET  /api/documents        — Liste des documents indexés
    DELETE /api/documents/{id} — Suppression
    GET  /api/stats            — Statistiques de l'index
    GET  /api/health           — Santé du service
    GET  /api/pdf/{filename}   — Téléchargement du PDF original
    GET  /api/documents/{id}/text — Export texte brut
"""

import sys
from pathlib import Path

# ── Garantit que la racine du projet est dans sys.path ───────────────────
# Nécessaire quelle que soit la façon dont uvicorn est lancé
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
# ─────────────────────────────────────────────────────────────────────────

import base64 as _b64

from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from core.config import API_TITLE, API_VERSION
from core.utils import pdf_hash
from services.extraction_service import (
    extract_pdf,
    save_uploaded_pdf,
    load_cache,
    save_cache,
    merge_cache_into_pages,
    get_pdf_path,
    export_pages_as_text,
)
from services.ocr_service import run_ocr_on_pages
from search.indexer import DocumentIndexer

from pydantic import BaseModel
from rag.search_laws import search_laws
from rag.answer import answer as rag_answer, answer_stream as rag_answer_stream
from rag import memory as chat_memory
from api.openai_compat import router as v1_router
from api.viewer import router as viewer_router
from api.admin import router as admin_router
from api.feedback import router as feedback_router
from api.pipeline import router as pipeline_router
from api.chat_ui import router as chat_ui_router

# ── App ───────────────────────────────────────────────────────────────────
app = FastAPI(title=API_TITLE, version=API_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API publique /v1 (clé API requise) : compatible OpenAI + native structurée
app.include_router(v1_router)
# Visionneuse de preuves (page PDF + texte OCR côte à côte, lecture seule)
app.include_router(viewer_router)
# Console d'administration du corpus (lecture seule)
app.include_router(admin_router)
# Boucle expert : retours, corrections, annotations + file de revue
app.include_router(feedback_router)
# Opérations : lancement des jobs du pipeline depuis la console
app.include_router(pipeline_router)
# Front de chat autonome (pilote) : /chat
app.include_router(chat_ui_router)
# Auth mobile (JWT) + quotas
from api.mobile_auth import router as mobile_auth_router  # noqa: E402
app.include_router(mobile_auth_router)

# App mobile (build web Flutter) servie sur /app — même origine que l'API
import os as _os  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
_APP_WEB = _os.path.join(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__))), "mobile", "build", "web")
if _os.path.isdir(_APP_WEB):
    app.mount("/app", StaticFiles(directory=_APP_WEB, html=True), name="app")

    @app.middleware("http")
    async def _no_cache_app(request, call_next):
        """Phase de développement : le service worker du build web garde
        l'ancienne version des jours durant sur mobile. On interdit donc la
        mise en cache de /app — à retirer quand les versions seront figées."""
        response = await call_next(request)
        if request.url.path.startswith("/app"):
            response.headers["Cache-Control"] = "no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


@app.on_event("startup")
def _init_api_keys():
    """Génère une clé API au premier démarrage si aucune n'existe
    (affichée dans les logs ; fichier sur le volume réseau)."""
    from api.auth import ensure_keys
    ensure_keys()
    # Base de la console (comptes, revue, audit) + compte admin initial
    from api.admin_core import init_db
    init_db()

# ── Singleton indexeur ────────────────────────────────────────────────────
_indexer: DocumentIndexer | None = None

def get_indexer() -> DocumentIndexer:
    global _indexer
    if _indexer is None:
        _indexer = DocumentIndexer()
    return _indexer


# ═════════════════════════════════════════════════════════════════════════
#  ROUTES
# ═════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    return {"status": "ok", "version": API_VERSION}


@app.get("/api/stats")
def stats():
    return get_indexer().stats()


@app.get("/api/documents")
def list_documents():
    return get_indexer().list_documents()


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    get_indexer().remove_document(doc_id)
    return {"deleted": doc_id}


@app.get("/api/pdf/{filename}")
def download_pdf(filename: str):
    path = get_pdf_path(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    return FileResponse(path=str(path), media_type="application/pdf", filename=filename)


@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload un PDF, extrait le texte et l'indexe."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers PDF sont acceptés.")

    content   = await file.read()
    file_hash = pdf_hash(content)

    save_uploaded_pdf(file.filename, content)

    result     = extract_pdf(content)
    pages      = result["pages"]
    from_cache = False

    cached = load_cache(file_hash)
    if cached:
        merge_cache_into_pages(pages, cached)
        from_cache = True
    else:
        if result["n_scan"] > 0:
            run_ocr_on_pages(pages)
        save_cache(file_hash, result)

    get_indexer().index_document(file_hash, file.filename, pages)

    return {
        "doc_id":     file_hash,
        "filename":   file.filename,
        "nb_pages":   result["nb_pages"],
        "n_native":   result["n_native"],
        "n_scan":     result["n_scan"],
        "doc_type":   result["doc_type"],
        "from_cache": from_cache,
        "pages": [
            {
                "num":        p["num"],
                "type":       p["type"],
                "text":       p["text"],
                "preview_b64": _b64.b64encode(p["preview"]).decode()
                               if isinstance(p.get("preview"), bytes)
                               else p.get("preview_b64", ""),
            }
            for p in pages
        ],
    }


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)):
    return get_indexer().search(q)


@app.get("/api/documents/{doc_id}/text")
def export_text(doc_id: str):
    indexer = get_indexer()
    doc = indexer.docs.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable.")
    pages_text = [
        {"num": int(k), "text": v}
        for k, v in sorted(doc["p"].items(), key=lambda x: int(x[0]))
    ]
    text = export_pages_as_text(pages_text)
    return JSONResponse(content={"doc_id": doc_id, "filename": doc["fn"], "text": text})


# ═════════════════════════════════════════════════════════════════════════
#  RAG JURIDIQUE — recherche sémantique + chat ancré (grounded)
# ═════════════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    question: str
    k: int = 6
    session_id: str | None = None      # mémoire de conversation (optionnelle)
    matiere: str | None = None         # domaine priorisé (penal, commercial…)
    strict: bool = False               # True = restreint réellement à la matière


@app.get("/api/laws/search")
def laws_search(q: str = Query(..., min_length=1), k: int = 6):
    """Recherche sémantique dans le corpus juridique (Qdrant + bge-m3)."""
    return {"query": q, "results": search_laws(q, limit=k)}


@app.post("/api/chat")
def chat(req: ChatRequest):
    """Chat juridique : réponse ancrée sur les articles récupérés + citations."""
    return rag_answer(req.question, k=req.k, session_id=req.session_id)


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, authorization: str | None = Header(default=None)):
    """Version streaming (NDJSON) : sources d'abord, puis les tokens de la réponse.
    Avec un Bearer mobile : quota vérifié et question décomptée."""
    from api.mobile_auth import bearer_user, check_quota, count_question
    u = bearer_user(authorization)
    if u:
        check_quota(u["username"])
        count_question(u["username"])
    return StreamingResponse(
        rag_answer_stream(req.question, k=req.k, session_id=req.session_id,
                          matiere=getattr(req, "matiere", None),
                          strict=bool(getattr(req, "strict", False))),
        media_type="application/x-ndjson",
    )

@app.get("/api/matieres")
def list_matieres():
    """Matières proposées au client, avec le nombre de textes disponibles."""
    from rag.matieres import MATIERES
    from rag import store
    try:
        counts = {c.name: store.client().count(c.name).count
                  for c in store.client().get_collections().collections}
    except Exception:
        counts = {}
    out = []
    for key, m in MATIERES.items():
        n = sum(counts.get(c, 0) for c in m["collections"])
        out.append({"key": key, "ar": m["ar"], "fr": m["fr"], "chunks": n,
                    "disponible": n > 0})
    return {"matieres": out}


# ── Sessions de conversation (mémoire) ───────────────────────────────────
@app.post("/api/sessions")
def create_session():
    chat_memory.init()
    return {"session_id": chat_memory.create_session()}


@app.get("/api/sessions")
def list_sessions(limit: int = 30):
    chat_memory.init()
    return {"sessions": chat_memory.list_sessions(limit=limit)}


@app.get("/api/sessions/{session_id}/messages")
def session_messages(session_id: str):
    chat_memory.init()
    return {"session_id": session_id, "messages": chat_memory.get_messages(session_id)}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    chat_memory.init()
    chat_memory.delete_session(session_id)
    return {"deleted": session_id}


# ── Point d'entrée direct ─────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    from core.config import API_HOST, API_PORT
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=True)