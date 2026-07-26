# -*- coding: utf-8 -*-
"""Socle de la console d'administration : base, comptes, rôles, audit, layout.

Base SQLite unique de l'application (feedback + utilisateurs + audit) :
Y:\\adala-project\\aiocr_data\\app.db — schéma pensé pour migrer tel quel
vers PostgreSQL en phase 1.

Rôles : admin (tout) > validator (valide corrections/annotations) >
expert (testeur, propose) > viewer (lecture seule).
Auth : cookie signé HMAC (stdlib), mots de passe PBKDF2-SHA256.
"""
import hashlib
import hmac
import html
import json
import os
import secrets
import sqlite3
import time

from fastapi import Cookie, HTTPException
from fastapi.responses import RedirectResponse

DATA_DIR = r"Y:\adala-project\aiocr_data"
DB = os.path.join(DATA_DIR, "app.db")
LEGACY_FEEDBACK_DB = os.path.join(DATA_DIR, "feedback.db")
SECRET_FILE = os.path.join(DATA_DIR, "secret_key.txt")
CREDS_FILE = os.path.join(DATA_DIR, "admin_credentials.txt")

ROLE_RANK = {"viewer": 0, "expert": 1, "validator": 2, "admin": 3}
ROLE_AR = {"admin": "مدير", "validator": "مراجع مصادِق", "expert": "خبير مختبِر",
           "viewer": "قارئ"}


def conn():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    return c


def _secret() -> bytes:
    if not os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(32))
    return open(SECRET_FILE, encoding="utf-8").read().strip().encode()


def hash_pw(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000)
    return f"{salt}${dk.hex()}"


def verify_pw(pw: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
        return hmac.compare_digest(hash_pw(pw, salt), stored)
    except Exception:
        return False


def sign_token(username: str) -> str:
    ts = str(int(time.time()))
    mac = hmac.new(_secret(), f"{username}|{ts}".encode(), "sha256").hexdigest()
    return f"{username}|{ts}|{mac}"


def read_token(tok: str | None, max_age: int = 12 * 3600) -> str | None:
    if not tok or tok.count("|") != 2:
        return None
    user, ts, mac = tok.split("|")
    good = hmac.new(_secret(), f"{user}|{ts}".encode(), "sha256").hexdigest()
    if not hmac.compare_digest(mac, good):
        return None
    if time.time() - int(ts) > max_age:
        return None
    return user


def init_db() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY, username TEXT UNIQUE, fullname TEXT,
          role TEXT DEFAULT 'viewer', pw TEXT, active INTEGER DEFAULT 1,
          created_ts REAL);
        CREATE TABLE IF NOT EXISTS audit(
          id INTEGER PRIMARY KEY, ts REAL, user TEXT, action TEXT, detail TEXT);
        CREATE TABLE IF NOT EXISTS feedback(
          id INTEGER PRIMARY KEY, ts REAL, user TEXT, type TEXT,
          question TEXT, answer TEXT, sources_json TEXT, comment TEXT,
          status TEXT DEFAULT 'new');
        CREATE TABLE IF NOT EXISTS corrections(
          id INTEGER PRIMARY KEY, ts REAL, feedback_id INTEGER,
          target_type TEXT, target_ref TEXT, old_value TEXT, proposed_value TEXT,
          evidence TEXT, proposed_by TEXT,
          status TEXT DEFAULT 'proposed',
          validated_by TEXT, decided_ts REAL, shipped_in_release TEXT);
        CREATE TABLE IF NOT EXISTS annotations(
          id INTEGER PRIMARY KEY, ts REAL, scope TEXT, target_ref TEXT,
          article TEXT, text TEXT, author_role TEXT,
          status TEXT DEFAULT 'validated', validated_by TEXT);
        """)
    # reprise des données de l'ancienne base feedback.db (une seule fois)
    if os.path.exists(LEGACY_FEEDBACK_DB):
        try:
            with conn() as c:
                c.execute("ATTACH DATABASE ? AS legacy", (LEGACY_FEEDBACK_DB,))
                for t in ("feedback", "corrections", "annotations"):
                    try:
                        c.execute(f"INSERT OR IGNORE INTO {t} SELECT * FROM legacy.{t}")
                    except sqlite3.Error:
                        pass
                c.execute("DETACH DATABASE legacy")
            os.replace(LEGACY_FEEDBACK_DB, LEGACY_FEEDBACK_DB + ".migrated")
        except sqlite3.Error:
            pass
    seed_admin()


def seed_admin() -> None:
    with conn() as c:
        n = c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
        if n:
            return
        pw = secrets.token_urlsafe(10)
        c.execute("INSERT INTO users(username, fullname, role, pw, created_ts) "
                  "VALUES('admin', 'Administrateur', 'admin', ?, ?)",
                  (hash_pw(pw), time.time()))
    with open(CREDS_FILE, "w", encoding="utf-8") as f:
        f.write(f"admin / {pw}\n(compte initial — changez le mot de passe "
                f"depuis la console, page المستعملون)\n")


def log_action(user: str, action: str, detail: str = "") -> None:
    with conn() as c:
        c.execute("INSERT INTO audit(ts, user, action, detail) VALUES(?,?,?,?)",
                  (time.time(), user, action, detail[:500]))


def current_user(rimlex_session: str | None = Cookie(default=None)) -> dict | None:
    username = read_token(rimlex_session)
    if not username:
        return None
    with conn() as c:
        r = c.execute("SELECT username, fullname, role, active FROM users "
                      "WHERE username=?", (username,)).fetchone()
    return dict(r) if r and r["active"] else None


def require(min_role: str):
    """Dépendance FastAPI : session valide + rôle suffisant, sinon redirection."""
    def dep(rimlex_session: str | None = Cookie(default=None)):
        u = current_user(rimlex_session)
        if not u:
            raise HTTPException(status_code=303,
                                headers={"Location": "/api/admin/login"})
        if ROLE_RANK.get(u["role"], 0) < ROLE_RANK[min_role]:
            raise HTTPException(403, "صلاحيات غير كافية لهذه الصفحة.")
        return u
    return dep


# ── layout partagé ─────────────────────────────────────────────────────────
CSS = """
 body{font-family:'Segoe UI',Tahoma,sans-serif;margin:0;background:#f4f2ec;color:#1a1a18}
 header{background:#1c2b3a;color:#fff;padding:10px 20px;display:flex;
        align-items:center;gap:18px;flex-wrap:wrap}
 header h1{font-size:15px;margin:0;font-weight:600}
 header .brand{color:#c9a968;font-weight:700}
 nav{display:flex;gap:2px;flex-wrap:wrap}
 nav a{color:#cfd8e3;text-decoration:none;font-size:12.5px;padding:5px 10px;border-radius:6px}
 nav a:hover{background:#2a3c50} nav a.on{background:#175a47;color:#fff}
 .who{margin-inline-start:auto;font-size:12px;color:#9fb0c3}
 .who a{color:#c9a968;text-decoration:none;margin-inline-start:8px}
 main{padding:14px}
 .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px}
 .card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:10px;text-align:center}
 .card b{display:block;font-size:20px;font-weight:600}
 .card span{color:#666;font-size:11.5px}
 .panel{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px 14px;margin-bottom:14px}
 .panel h2{font-size:14px;margin:0 0 10px;color:#444}
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{padding:7px 10px;border-bottom:1px solid #eee;text-align:right;vertical-align:top}
 th{background:#faf8f2;color:#666;font-size:12px}
 a{color:#1d5fa5;text-decoration:none} a:hover{text-decoration:underline}
 .tag{display:inline-block;font-size:11px;border-radius:5px;padding:2px 8px;margin:1px}
 .t-ok{background:#e7f3e7;color:#1d5c1d}.t-warn{background:#fdf3e0;color:#8a5a00}
 .t-danger{background:#fdeaea;color:#8f1d1d}.t-gray{background:#eee;color:#555}
 .t-blue{background:#e6f0fa;color:#15507e}
 button{border:1px solid #bbb;background:#fff;border-radius:6px;padding:5px 12px;
        cursor:pointer;font-size:12.5px}
 button:hover{background:#f0ede4}
 button.primary{background:#175a47;color:#fff;border-color:#175a47}
 input[type=text],input[type=password],select,textarea{padding:6px 10px;border:1px solid #bbb;
        border-radius:6px;font-size:13px;font-family:inherit}
 form.inline{display:inline} .filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
 .bar{fill:#175a47} .bar2{fill:#c9a968} .axis{font-size:10px;fill:#888}
 .pag{font-size:13px;margin-top:8px}
"""

NAV = [("", "اللوحة"), ("/docs", "الوثائق"), ("/juris", "الاجتهاد القضائي"),
       ("/review", "المراجعة والمصادقة"), ("/annotations", "الملاحظات المعتمدة"),
       ("/quality", "جودة الاستخراج"), ("/users", "المستعملون"), ("/audit", "السجل")]


def page(title: str, body: str, user: dict | None = None, active: str = "") -> str:
    nav = "".join(
        f"<a href='/api/admin{p}' class='{'on' if p == active else ''}'>{lbl}</a>"
        for p, lbl in NAV)
    who = (f"<span class='who'>{html.escape(user['fullname'] or user['username'])} — "
           f"{ROLE_AR.get(user['role'], user['role'])}"
           f"<a href='/api/admin/logout'>خروج</a></span>") if user else ""
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body>
<header><h1><span class="brand">RimLex</span> · إدارة المنصة</h1>
<nav>{nav}</nav>{who}</header><main>{body}</main></body></html>"""


def svg_bars(data: list[tuple[str, int]], width: int = 640, height: int = 150,
             color: str = "bar") -> str:
    """Diagramme à barres SVG inline (sans dépendance)."""
    if not data:
        return "<p style='color:#888;font-size:13px'>لا بيانات.</p>"
    mx = max(v for _, v in data) or 1
    n = len(data)
    bw = max(6, min(46, (width - 10) // n - 4))
    parts = [f"<svg viewBox='0 0 {width} {height + 34}' style='width:100%;max-width:{width}px'>"]
    for i, (lbl, v) in enumerate(data):
        x = 5 + i * (bw + 4)
        h = round(v / mx * height)
        parts.append(f"<rect class='{color}' x='{x}' y='{height - h}' "
                     f"width='{bw}' height='{h}' rx='2'><title>{html.escape(str(lbl))}: {v:,}</title></rect>")
        parts.append(f"<text class='axis' x='{x + bw / 2}' y='{height + 12}' "
                     f"text-anchor='middle'>{html.escape(str(lbl)[:8])}</text>")
        if n <= 30:
            parts.append(f"<text class='axis' x='{x + bw / 2}' y='{height - h - 4}' "
                         f"text-anchor='middle'>{v:,}</text>")
    parts.append("</svg>")
    return "".join(parts)
