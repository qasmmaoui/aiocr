# -*- coding: utf-8 -*-
"""Pièces jointes d'une conversation : stockage, purge, texte servi au modèle.

Ces documents sont des pièces de dossiers de clients, pas des textes publics.
Trois règles les distinguent donc du fonds documentaire :

1. le fichier brut ne survit pas à la conversation — il est effacé après cinq
   minutes sans activité, et son nom d'origine n'est jamais utilisé sur le
   disque (deux « convocation.pdf » s'écraseraient) ;
2. le texte extrait vit avec la session et disparaît avec elle ; il n'entre ni
   dans le cache global d'extraction, indexé sur l'empreinte du contenu et
   jamais purgé, ni dans l'index de recherche, où il deviendrait consultable
   par les autres utilisateurs ;
3. les aperçus de page sont effacés avec le fichier : conserver l'image d'une
   page reviendrait à conserver le document. L'historique garde le nom, le
   nombre de pages et le type — de quoi afficher une carte, pas de quoi
   relire la pièce.
"""
import json
import os
import sqlite3
import time
import uuid

from rag.memory import DB_PATH

# Délai d'inactivité au-delà duquel le fichier brut est effacé.
INACTIVITE = 5 * 60
# Au-delà, le texte servi au modèle est tronqué : dix pièces entières
# noieraient la question et déborderaient la fenêtre de contexte.
MAX_CAR_PIECE = 12_000
MAX_PIECES = 10

_DIR = os.path.join(os.path.dirname(DB_PATH) or ".", "pieces")


def _cx() -> sqlite3.Connection:
    cx = sqlite3.connect(DB_PATH, timeout=30)
    cx.execute("PRAGMA journal_mode=WAL")
    return cx


def init() -> None:
    os.makedirs(_DIR, exist_ok=True)
    with _cx() as cx:
        cx.execute(
            "CREATE TABLE IF NOT EXISTS attachments("
            " id TEXT PRIMARY KEY, session_id TEXT NOT NULL,"
            " filename TEXT NOT NULL, mime TEXT DEFAULT '',"
            " nb_pages INTEGER DEFAULT 0, doc_type TEXT DEFAULT '',"
            " pages TEXT DEFAULT '[]', chemin TEXT DEFAULT '',"
            " fichier_supprime INTEGER DEFAULT 0,"
            " created_at REAL)")
        cx.execute("CREATE INDEX IF NOT EXISTS ix_att_session"
                   " ON attachments(session_id)")


def enregistrer(session_id: str, filename: str, mime: str, contenu: bytes,
                pages: list[dict], doc_type: str) -> dict:
    """Range une pièce et ne conserve du texte que ce qui sert à répondre."""
    init()
    aid = uuid.uuid4().hex
    # nom opaque : le nom d'origine reste une donnée, jamais un chemin
    ext = ".pdf" if mime == "application/pdf" else ".bin"
    chemin = os.path.join(_DIR, aid + ext)
    with open(chemin, "wb") as f:
        f.write(contenu)
    # on ne garde que le texte : les aperçus image partiront avec le fichier
    maigres = [{"num": p["num"], "type": p.get("type", ""),
                "text": p.get("text", "")} for p in pages]
    with _cx() as cx:
        cx.execute(
            "INSERT INTO attachments(id, session_id, filename, mime, nb_pages,"
            " doc_type, pages, chemin, fichier_supprime, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,0,?)",
            (aid, session_id, filename, mime, len(pages), doc_type,
             json.dumps(maigres, ensure_ascii=False), chemin, time.time()))
    return {"id": aid, "filename": filename, "nb_pages": len(pages),
            "doc_type": doc_type, "etat": "pret"}


def lister(session_id: str) -> list[dict]:
    init()
    with _cx() as cx:
        rows = cx.execute(
            "SELECT id, filename, nb_pages, doc_type, fichier_supprime"
            " FROM attachments WHERE session_id = ? ORDER BY created_at",
            (session_id,)).fetchall()
    return [{"id": r[0], "filename": r[1], "nb_pages": r[2], "doc_type": r[3],
             "fichier_disponible": not r[4]} for r in rows]


def pour_contexte(session_id: str, ids: list[str]) -> list[dict]:
    """Texte des pièces désignées, borné et rattaché à la seule session.

    Le filtre sur `session_id` n'est pas une précaution de style : sans lui,
    un identifiant deviné donnerait accès à la pièce d'un autre dossier.
    """
    if not ids:
        return []
    init()
    ids = list(dict.fromkeys(ids))[:MAX_PIECES]
    marques = ",".join("?" * len(ids))
    with _cx() as cx:
        rows = cx.execute(
            "SELECT id, filename, nb_pages, pages FROM attachments"
            " WHERE session_id = ? AND id IN (" + marques + ")",
            [session_id, *ids]).fetchall()
    out = []
    for aid, nom, nb, brut in rows:
        try:
            pages = json.loads(brut)
        except Exception:
            pages = []
        morceaux, total = [], 0
        for p in pages:
            t = (p.get("text") or "").strip()
            if not t:
                continue
            bloc = "[صفحة " + str(p.get("num")) + "] " + t
            if total + len(bloc) > MAX_CAR_PIECE:
                morceaux.append("… (بقية الوثيقة غير معروضة)")
                break
            morceaux.append(bloc)
            total += len(bloc)
        out.append({"id": aid, "filename": nom, "nb_pages": nb,
                    "texte": "\n".join(morceaux)})
    return out


def supprimer(attachment_id: str, session_id: str) -> bool:
    """Retrait explicite par l'utilisateur, avant ou après envoi."""
    init()
    with _cx() as cx:
        row = cx.execute("SELECT chemin FROM attachments WHERE id = ?"
                         " AND session_id = ?",
                         (attachment_id, session_id)).fetchone()
        if not row:
            return False
        cx.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    _effacer(row[0])
    return True


def _effacer(chemin: str) -> None:
    try:
        if chemin and os.path.exists(chemin):
            os.remove(chemin)
    except OSError:
        pass


def purger(maintenant: float | None = None) -> int:
    """Efface les fichiers des conversations inactives depuis cinq minutes.

    Le texte, lui, reste : l'utilisateur doit pouvoir poser une question de
    suivi sur une pièce envoyée il y a une heure. C'est le document original
    qui ne doit pas s'attarder sur le disque, pas ce que l'assistant en a lu.
    """
    init()
    t = maintenant if maintenant is not None else time.time()
    limite = t - INACTIVITE
    with _cx() as cx:
        rows = cx.execute(
            "SELECT a.id, a.chemin FROM attachments a"
            " LEFT JOIN sessions s ON s.id = a.session_id"
            " WHERE a.fichier_supprime = 0"
            "   AND COALESCE(s.updated_at, a.created_at) < ?",
            (limite,)).fetchall()
        for aid, chemin in rows:
            _effacer(chemin)
            cx.execute("UPDATE attachments SET fichier_supprime = 1,"
                       " chemin = '' WHERE id = ?", (aid,))
    return len(rows)


def oublier_session(session_id: str) -> None:
    """Suppression d'une conversation : le texte s'en va avec elle."""
    init()
    with _cx() as cx:
        rows = cx.execute("SELECT chemin FROM attachments WHERE session_id = ?",
                          (session_id,)).fetchall()
        cx.execute("DELETE FROM attachments WHERE session_id = ?",
                   (session_id,))
    for (chemin,) in rows:
        _effacer(chemin)


def bloc_pieces(pieces: list[dict]) -> str:
    """Les pièces servies au modèle, séparées des textes de loi.

    Elles ne sont pas une source de droit : ce sont les faits du dossier. Les
    mêler aux articles inviterait le modèle à les citer comme une autorité.
    """
    if not pieces:
        return ""
    out = ["[وثائق أرفقها المستعمل — وقائع الملف، وليست مصدرا للقانون]"]
    for p in pieces:
        out.append("— " + p["filename"] + " (" + str(p["nb_pages"]) + " صفحة)")
        out.append(p["texte"])
        out.append("")
    out.append("استند إلى هذه الوثائق للوقائع، وإلى النصوص القانونية للقاعدة "
               "المطبقة؛ لا تستشهد بالوثائق كما لو كانت نصا قانونيا.")
    return "\n".join(out)
