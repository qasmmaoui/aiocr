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

from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Query, Request
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
from services import attachments
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
from api.eavocat_api import router as eavocat_router  # noqa: E402
app.include_router(eavocat_router)
from api.viewer_v4 import router as src_v4_router  # noqa: E402
app.include_router(src_v4_router)
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
async def upload_document(file: UploadFile = File(...),
                          authorization: str | None = Header(default=None)):
    """Verse un PDF au FONDS DOCUMENTAIRE, consultable par tous.

    À ne pas confondre avec `/api/attachments`, qui reçoit les pièces d'un
    dossier client : celles-là restent cloisonnées dans leur conversation et
    n'entrent jamais dans l'index de recherche.

    Cette route-ci indexe pour de bon. Elle était ouverte : n'importe qui
    pouvait y verser un document, et le rendre consultable par tous les
    utilisateurs via `/api/search`. Elle est désormais réservée aux
    administrateurs.
    """
    from api.mobile_auth import bearer_user
    u = bearer_user(authorization)
    if not u or (u.get("role") or "") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Réservé aux administrateurs. Pour joindre une pièce à une "
                   "conversation, utilisez /api/attachments.")
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
    attachment_ids: list[str] = []     # pièces jointes à la question



# ── Session implicite ────────────────────────────────────────────────────
# L'app Flutter n'envoie pas encore  (Api.ask() accepte le
# paramètre mais aucun appelant ne le passe), donc chaque question arrivait
# sans historique et les questions de suivi (« les documents nécessaires ? »)
# partaient hors contexte. Tant que l'app n'est pas reconstruite, on rattache
# l'appel à une session stable déduite du client (jeton d'auth sinon IP).
_AUTO_SESSIONS: dict[str, str] = {}
_AUTO_SEEN: dict[str, float] = {}
_AUTO_TTL = 20 * 60           # au-delà, on ouvre une nouvelle conversation


def _auto_session(request, authorization: str | None,
                  provided: str | None) -> str | None:
    if provided:
        return provided
    import time as _t
    key = (authorization or "").strip()
    if not key and request is not None and request.client:
        key = f"ip:{request.client.host}"
    if not key:
        return None
    now = _t.time()
    sid = _AUTO_SESSIONS.get(key)
    if sid and now - _AUTO_SEEN.get(key, 0) < _AUTO_TTL:
        _AUTO_SEEN[key] = now
        return sid
    chat_memory.init()
    sid = chat_memory.create_session()
    _AUTO_SESSIONS[key] = sid
    _AUTO_SEEN[key] = now
    return sid


@app.get("/api/laws/search")
def laws_search(q: str = Query(..., min_length=1), k: int = 6):
    """Recherche sémantique dans le corpus juridique (Qdrant + bge-m3)."""
    return {"query": q, "results": search_laws(q, limit=k)}


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request,
         authorization: str | None = Header(default=None)):
    """Chat juridique : réponse ancrée sur les articles récupérés + citations."""
    sid = _auto_session(request, authorization, req.session_id)
    return rag_answer(req.question, k=req.k, session_id=sid,
                      attachment_ids=req.attachment_ids)


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, request: Request,
                authorization: str | None = Header(default=None)):
    """Version streaming (NDJSON) : sources d'abord, puis les tokens de la réponse.
    Avec un Bearer mobile : quota vérifié et question décomptée."""
    from api.mobile_auth import bearer_user, check_quota, count_question
    u = bearer_user(authorization)
    if u:
        check_quota(u["username"])
        count_question(u["username"])
    sid = _auto_session(request, authorization, req.session_id)
    return StreamingResponse(
        rag_answer_stream(req.question, k=req.k, session_id=sid,
                          matiere=getattr(req, "matiere", None),
                          strict=bool(getattr(req, "strict", False)),
                          attachment_ids=req.attachment_ids),
        media_type="application/x-ndjson",
    )

@app.get("/api/matieres")
def list_matieres():
    """Matières proposées au client, avec le nombre de textes disponibles."""
    from rag.matieres import MATIERES, count_for
    from rag import store
    out = []
    for key, m in MATIERES.items():
        try:
            n = count_for(key, store)     # compte par dossier (payload), pas par collection
        except Exception:
            n = 0
        out.append({"key": key, "ar": m["ar"], "fr": m["fr"], "chunks": n,
                    "disponible": n > 0})
    out.sort(key=lambda x: -x["chunks"])   # les matières les mieux fournies d'abord
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
    attachments.oublier_session(session_id)
    chat_memory.delete_session(session_id)
    return {"deleted": session_id}


# ── Point d'entrée direct ─────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    from core.config import API_HOST, API_PORT
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=True)


# ══════════════════════════════════════════════════════════════════════════
#  Pièces jointes d'une conversation
# ══════════════════════════════════════════════════════════════════════════
IMAGES_ACCEPTEES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


@app.post("/api/attachments")
async def joindre_piece(request: Request,
                        file: UploadFile = File(...),
                        session_id: str | None = None,
                        authorization: str | None = Header(default=None)):
    """Reçoit UN document et en extrait le texte, sans l'indexer.

    Une image est traitée comme une page unique scannée : c'est le cas le plus
    fréquent en pratique, la photo d'une convocation prise au téléphone.
    """
    sid = _auto_session(request, authorization, session_id)
    if not sid:
        raise HTTPException(status_code=400,
                            detail="Aucune conversation pour rattacher la pièce.")

    deja = [a for a in attachments.lister(sid)]
    if len(deja) >= attachments.MAX_PIECES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {attachments.MAX_PIECES} pièces par conversation.")

    nom = file.filename or "document"
    bas = nom.lower()
    est_pdf = bas.endswith(".pdf")
    est_image = any(bas.endswith(e) for e in IMAGES_ACCEPTEES)
    if not (est_pdf or est_image):
        raise HTTPException(status_code=400,
                            detail="Formats acceptés : PDF, JPG, PNG, WEBP, TIFF, BMP.")

    contenu = await file.read()
    if not contenu:
        raise HTTPException(status_code=400, detail="Fichier vide.")

    if est_pdf:
        res = extract_pdf(contenu)
        # Un document long n'est pas une pièce jointe à une question : le
        # transcrire mobiliserait le modèle de vision plus d'une heure, pour
        # une réponse que personne n'attendra. On refuse tout de suite plutôt
        # que de lancer un travail invisible et facturé.
        if res["nb_pages"] > attachments.MAX_PAGES:
            raise HTTPException(
                status_code=413,
                detail=f"Document trop long : {res['nb_pages']} pages "
                       f"(maximum {attachments.MAX_PAGES}).")
        pages, doc_type, a_ocr = res["pages"], res["doc_type"], res["n_scan"] > 0
    else:
        # L'OCR travaille sur du base64 (`image_b64`), pas sur des octets :
        # une image devient donc une page scannée unique, décodée par PIL en
        # aval — JPEG, PNG, WEBP ou TIFF passent tels quels.
        pages = [{"num": 1, "type": "scan", "text": "",
                  "image_b64": _b64.b64encode(contenu).decode()}]
        doc_type, a_ocr = "scan", True

    mime = "application/pdf" if est_pdf else "image"

    if not a_ocr:
        # PDF avec couche texte : l'extraction est immédiate, rien à différer.
        return attachments.enregistrer(sid, nom, mime, contenu, pages, doc_type)

    # Document scanné : le modèle de vision met de trente à quatre-vingt-dix
    # secondes par page. Attendre la fin ferait couper la connexion par
    # Cloudflare bien avant. On enregistre la pièce en l'état, on rend la main,
    # et la transcription se poursuit dans un fil séparé.
    fiche = attachments.enregistrer(sid, nom, mime, contenu, pages, doc_type,
                                    etat="lecture")

    def _lire():
        def avancement(ratio: float, _message: str = "") -> None:
            # Lève `Abandonnee` si la pièce a disparu : l'exception remonte à
            # travers l'OCR et arrête la transcription entre deux pages.
            attachments.maj_progres(fiche["id"], round(ratio * 100))

        try:
            run_ocr_on_pages(pages, progress_callback=avancement)
            attachments.marquer_lu(fiche["id"], pages, doc_type)
        except attachments.Abandonnee:
            pass                                 # retirée par l'utilisateur
        except Exception:                        # noqa: BLE001
            attachments.marquer_echec(fiche["id"])

    import threading
    threading.Thread(target=_lire, daemon=True).start()
    return fiche


@app.get("/api/attachments")
def lister_pieces(request: Request, session_id: str | None = None,
                  authorization: str | None = Header(default=None)):
    sid = _auto_session(request, authorization, session_id)
    return {"session_id": sid, "pieces": attachments.lister(sid) if sid else []}


@app.delete("/api/attachments/{attachment_id}")
def retirer_piece(attachment_id: str, request: Request,
                  session_id: str | None = None,
                  authorization: str | None = Header(default=None)):
    """Retrait par l'utilisateur — avant l'envoi, ou après coup."""
    sid = _auto_session(request, authorization, session_id)
    if not sid or not attachments.supprimer(attachment_id, sid):
        raise HTTPException(status_code=404, detail="Pièce introuvable.")
    return {"ok": True}


@app.on_event("startup")
async def _balayeur_pieces():
    """Efface les fichiers des conversations en sommeil depuis cinq minutes.

    Le texte extrait, lui, reste tant que la conversation existe : une
    question de suivi doit rester possible une heure après l'envoi. C'est le
    document original qui ne doit pas s'attarder sur le disque.
    """
    import asyncio

    async def boucle():
        while True:
            try:
                attachments.purger()
            except Exception:            # noqa: BLE001 — jamais fatal au service
                pass
            await asyncio.sleep(60)

    asyncio.create_task(boucle())
