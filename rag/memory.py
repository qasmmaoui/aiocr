"""
Mémoire de conversation (sessions + historique + sommaire roulant).

Trois couches, même principe que les assistants type Claude Code :
  1. court terme : les N derniers messages renvoyés intégralement au modèle ;
  2. compaction  : au-delà d'un seuil, l'ancien historique est résumé en un
     « sommaire roulant » stocké sur la session (une seule fois, pas à chaque tour) ;
  3. long terme  : (phase 2) corrections d'expert dans Qdrant — hors de ce module.

Stockage SQLite (stdlib uniquement -> testable sans le pod).
"""
import json
import os
import sqlite3
import time
import uuid

DB_PATH = os.environ.get("CHAT_DB", "/workspace/chat_memory.db")
RECENT_TURNS = 8        # messages récents envoyés tels quels (≈ 4 échanges)
SUMMARIZE_AFTER = 18    # nb total de messages déclenchant la compaction de l'ancien


def _cx() -> sqlite3.Connection:
    cx = sqlite3.connect(DB_PATH, timeout=15)
    cx.execute("PRAGMA journal_mode=WAL")
    return cx


def init() -> None:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with _cx() as cx:
        cx.execute(
            "CREATE TABLE IF NOT EXISTS sessions("
            " id TEXT PRIMARY KEY, title TEXT DEFAULT '', summary TEXT DEFAULT '',"
            " summarized_upto INTEGER DEFAULT 0,"
            " created_at REAL, updated_at REAL)")
        cx.execute(
            "CREATE TABLE IF NOT EXISTS messages("
            " id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,"
            " role TEXT NOT NULL, content TEXT NOT NULL, sources TEXT,"
            " created_at REAL)")
        cx.execute("CREATE INDEX IF NOT EXISTS ix_msg_session ON messages(session_id, id)")


def create_session(title: str = "") -> str:
    sid = uuid.uuid4().hex[:16]
    now = time.time()
    with _cx() as cx:
        cx.execute("INSERT INTO sessions(id, title, created_at, updated_at) VALUES(?,?,?,?)",
                   (sid, title, now, now))
    return sid


def list_sessions(limit: int = 30) -> list[dict]:
    with _cx() as cx:
        rows = cx.execute(
            "SELECT s.id, s.title, s.updated_at,"
            " (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS n"
            " FROM sessions s ORDER BY s.updated_at DESC LIMIT ?", (limit,)).fetchall()
    return [{"id": r[0], "title": r[1] or "محادثة بدون عنوان",
             "updated_at": r[2], "n_messages": r[3]} for r in rows]


def add_message(session_id: str, role: str, content: str,
                sources: list | None = None) -> None:
    now = time.time()
    with _cx() as cx:
        cx.execute(
            "INSERT INTO messages(session_id, role, content, sources, created_at)"
            " VALUES(?,?,?,?,?)",
            (session_id, role, content,
             json.dumps(sources, ensure_ascii=False) if sources else None, now))
        cx.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        # titre auto = début de la 1ère question
        if role == "user":
            cx.execute(
                "UPDATE sessions SET title = ? WHERE id = ? AND (title = '' OR title IS NULL)",
                (content.strip()[:80], session_id))


def get_recent(session_id: str, limit: int = RECENT_TURNS) -> list[dict]:
    """Derniers messages en ordre chronologique, format API chat."""
    with _cx() as cx:
        rows = cx.execute(
            "SELECT role, content FROM messages WHERE session_id = ?"
            " ORDER BY id DESC LIMIT ?", (session_id, limit)).fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def get_messages(session_id: str) -> list[dict]:
    """Historique complet (pour l'affichage UI), avec sources."""
    with _cx() as cx:
        rows = cx.execute(
            "SELECT role, content, sources FROM messages WHERE session_id = ?"
            " ORDER BY id", (session_id,)).fetchall()
    return [{"role": r[0], "content": r[1],
             "sources": json.loads(r[2]) if r[2] else []} for r in rows]


def get_summary(session_id: str) -> str:
    with _cx() as cx:
        row = cx.execute("SELECT summary FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return (row[0] or "") if row else ""


def delete_session(session_id: str) -> None:
    with _cx() as cx:
        cx.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        cx.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def maybe_summarize(session_id: str, llm) -> bool:
    """Compaction : si l'historique dépasse le seuil, résume l'ancien (hors
    RECENT_TURNS) dans sessions.summary. `llm` = callable(prompt_str) -> str,
    injecté par l'appelant (testable avec un stub, sans Ollama)."""
    with _cx() as cx:
        row = cx.execute("SELECT summary, summarized_upto FROM sessions WHERE id = ?",
                         (session_id,)).fetchone()
        if not row:
            return False
        prev_summary, upto = row[0] or "", row[1] or 0
        rows = cx.execute(
            "SELECT id, role, content FROM messages WHERE session_id = ? AND id > ?"
            " ORDER BY id", (session_id, upto)).fetchall()
    if len(rows) <= SUMMARIZE_AFTER:
        return False
    old = rows[:-RECENT_TURNS]                     # tout sauf les récents
    convo = "\n".join(f"{'المستخدم' if r[1] == 'user' else 'المساعد'}: {r[2][:500]}"
                      for r in old)
    prompt = (
        "لخّص المحادثة القانونية التالية في فقرة واحدة مركزة تحفظ: المواضيع "
        "القانونية المطروحة، القوانين والمواد المذكورة، وأي تفضيلات أو سياق "
        "ذكره المستخدم. الملخص سيُستعمل كسياق لاستكمال المحادثة.\n\n"
        + (f"الملخص السابق: {prev_summary}\n\n" if prev_summary else "")
        + f"المحادثة:\n{convo}\n\nالملخص:")
    try:
        summary = (llm(prompt) or "").strip()
    except Exception:
        return False
    if not summary:
        return False
    with _cx() as cx:
        cx.execute("UPDATE sessions SET summary = ?, summarized_upto = ? WHERE id = ?",
                   (summary[:2000], old[-1][0], session_id))
    return True
