# -*- coding: utf-8 -*-
"""Endpoints des pièces jointes, et raccordement du chat.

Un envoi par fichier, et non un envoi groupé : chaque requête reste courte,
donc le délai de 100 s imposé par Cloudflare devant le proxy RunPod ne peut
mordre que sur un document isolé. L'utilisateur voit ses pièces arriver une à
une, peut en retirer une avant d'envoyer, et l'océrisation se fait pendant
qu'il tape — au moment où il valide, le travail est le plus souvent fini.

Le fonds documentaire garde son propre endpoint `/api/upload` : ces
documents-là sont publics, ils doivent être indexés et mis en cache. Les
pièces d'un dossier, non — voir services/attachments.py.
"""
import io
import shutil
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "/workspace/aiocr/api/main.py"
shutil.copy(SRC, SRC + ".bak-pieces")
s = io.open(SRC, encoding="utf-8").read()


def sub1(vieux, neuf):
    global s
    assert s.count(vieux) == 1, "ancrage introuvable ou ambigu : " + vieux[:70]
    s = s.replace(vieux, neuf, 1)


# ── La requête de chat transporte les pièces désignées ───────────────────
sub1("    strict: bool = False               # True = restreint réellement à la matière",
     "    strict: bool = False               # True = restreint réellement à la matière\n"
     "    attachment_ids: list[str] = []     # pièces jointes à la question")

sub1("    return rag_answer(req.question, k=req.k, session_id=sid)",
     "    return rag_answer(req.question, k=req.k, session_id=sid,\n"
     "                      attachment_ids=req.attachment_ids)")

sub1("                          strict=bool(getattr(req, \"strict\", False))),",
     "                          strict=bool(getattr(req, \"strict\", False)),\n"
     "                          attachment_ids=req.attachment_ids),")

# ── Supprimer une conversation emporte ses pièces ────────────────────────
sub1("    chat_memory.delete_session(session_id)",
     "    attachments.oublier_session(session_id)\n"
     "    chat_memory.delete_session(session_id)")

# ── Import et endpoints ──────────────────────────────────────────────────
sub1("from rag import memory as chat_memory\n",
     "from rag import memory as chat_memory\nfrom services import attachments\n")

ENDPOINTS = '''

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
'''

s = s.rstrip("\n") + "\n" + ENDPOINTS
io.open(SRC, "w", encoding="utf-8").write(s)
print("api/main.py câblé — sauvegarde : main.py.bak-pieces")
