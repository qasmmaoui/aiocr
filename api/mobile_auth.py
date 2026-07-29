# -*- coding: utf-8 -*-
"""Authentification mobile (JWT) + quotas d'usage — fondation commerciale.

    POST /api/mobile/auth/login     {username, password, device}
                                    -> {access, refresh, user, plan, usage}
    POST /api/mobile/auth/refresh   {refresh} -> {access, refresh}  (rotation)
    POST /api/mobile/auth/logout    {refresh} -> révocation de l'appareil
    GET  /api/mobile/me             Bearer -> profil + usage du mois

JWT HS256 signé avec la clé de admin_core (stdlib uniquement). Access 15 min,
refresh 30 j rotatif stocké haché en base (révocable). Quota mensuel selon le
plan (free 10 / pro 200 / office illimité) — décompté par question posée.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from api import admin_core as core

router = APIRouter(prefix="/api/mobile")

ACCESS_TTL = 15 * 60
REFRESH_TTL = 30 * 24 * 3600
PLANS = {"free": 10, "pro": 200, "office": None}       # questions / mois


def _b64(d: bytes) -> str:
    return base64.urlsafe_b64encode(d).rstrip(b"=").decode()


def _jwt(payload: dict) -> str:
    h = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(core._secret(), f"{h}.{p}".encode(), "sha256").digest())
    return f"{h}.{p}.{sig}"


def _jwt_read(tok: str) -> dict | None:
    try:
        h, p, sig = tok.split(".")
        good = _b64(hmac.new(core._secret(), f"{h}.{p}".encode(), "sha256").digest())
        if not hmac.compare_digest(sig, good):
            return None
        pad = p + "=" * (-len(p) % 4)
        payload = json.loads(base64.urlsafe_b64decode(pad))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def _ensure_tables():
    core.init_db()
    with core.conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS devices(
          id INTEGER PRIMARY KEY, username TEXT, device TEXT,
          refresh_hash TEXT, created REAL, last_seen REAL, revoked INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS usage(
          username TEXT, month TEXT, questions INTEGER DEFAULT 0,
          PRIMARY KEY(username, month));
        """)
        try:
            c.execute("ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'")
        except Exception:
            pass


def _month() -> str:
    return time.strftime("%Y-%m")


def usage_of(username: str) -> dict:
    _ensure_tables()
    with core.conn() as c:
        row = c.execute("SELECT questions FROM usage WHERE username=? AND month=?",
                        (username, _month())).fetchone()
        u = c.execute("SELECT plan, role FROM users WHERE username=?",
                      (username,)).fetchone()
    plan = (u["plan"] if u else None) or "free"
    role = u["role"] if u else "viewer"
    limit = None if role in ("admin", "validator") else PLANS.get(plan, 10)
    return {"plan": plan, "used": row["questions"] if row else 0,
            "limit": limit, "month": _month()}


def count_question(username: str) -> None:
    with core.conn() as c:
        c.execute("INSERT INTO usage(username, month, questions) VALUES(?,?,1) "
                  "ON CONFLICT(username, month) DO UPDATE SET questions=questions+1",
                  (username, _month()))


def check_quota(username: str) -> None:
    """Les comptes internes (مدير / مراجع) ne sont pas soumis aux quotas :
    ceux-ci servent aux offres commerciales, pas à l'exploitation."""
    with core.conn() as c:
        r = c.execute("SELECT role FROM users WHERE username=?",
                      (username,)).fetchone()
    if r and r["role"] in ("admin", "validator"):
        return
    u = usage_of(username)
    if u["limit"] is not None and u["used"] >= u["limit"]:
        raise HTTPException(429, "بلغت حدّ خطتك لهذا الشهر — قم بالترقية للمتابعة.")


def bearer_user(authorization: str | None = Header(default=None)) -> dict | None:
    """Dépendance : utilisateur JWT si présent, sinon None (compat web/console)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    payload = _jwt_read(authorization.split(" ", 1)[1].strip())
    if not payload or payload.get("typ") != "access":
        return None
    with core.conn() as c:
        r = c.execute("SELECT username, fullname, role, active, plan FROM users "
                      "WHERE username=?", (payload["sub"],)).fetchone()
    return dict(r) if r and r["active"] else None


def _issue(username: str, device: str) -> dict:
    access = _jwt({"sub": username, "typ": "access",
                   "exp": time.time() + ACCESS_TTL})
    refresh = secrets.token_urlsafe(32)
    rhash = hashlib.sha256(refresh.encode()).hexdigest()
    with core.conn() as c:
        c.execute("UPDATE devices SET revoked=1 "
                  "WHERE username=? AND device=? AND revoked=0", (username, device))
        c.execute("INSERT INTO devices(username, device, refresh_hash, created, "
                  "last_seen) VALUES(?,?,?,?,?)",
                  (username, device, rhash, time.time(), time.time()))
    return {"access": access, "refresh": refresh, "expires_in": ACCESS_TTL}


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str
    password: str
    device: str = "mobile"


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    refresh: str
    device: str = "mobile"


@router.post("/auth/login")
def login(body: LoginIn):
    _ensure_tables()
    username = body.username.strip()
    with core.conn() as c:
        r = c.execute("SELECT username, fullname, role, pw, active FROM users "
                      "WHERE username=? COLLATE NOCASE", (username,)).fetchone()
    if not r or not r["active"] or not core.verify_pw(body.password.strip(), r["pw"]):
        core.log_action(username, "mobile_login_failed", body.device)
        raise HTTPException(401, "بيانات الدخول غير صحيحة.")
    core.log_action(r["username"], "mobile_login", body.device)
    tokens = _issue(r["username"], body.device)
    return {**tokens,
            "user": {"username": r["username"], "fullname": r["fullname"],
                     "role": r["role"]},
            "usage": usage_of(r["username"])}


@router.post("/auth/refresh")
def refresh(body: RefreshIn):
    _ensure_tables()
    rhash = hashlib.sha256(body.refresh.strip().encode()).hexdigest()
    with core.conn() as c:
        d = c.execute("SELECT id, username, created FROM devices "
                      "WHERE refresh_hash=? AND revoked=0", (rhash,)).fetchone()
        if not d or time.time() - d["created"] > REFRESH_TTL:
            raise HTTPException(401, "جلسة منتهية — سجّل الدخول من جديد.")
        c.execute("UPDATE devices SET revoked=1, last_seen=? WHERE id=?",
                  (time.time(), d["id"]))
    return _issue(d["username"], body.device)


@router.post("/auth/logout")
def logout(body: RefreshIn):
    _ensure_tables()
    rhash = hashlib.sha256(body.refresh.strip().encode()).hexdigest()
    with core.conn() as c:
        c.execute("UPDATE devices SET revoked=1 WHERE refresh_hash=?", (rhash,))
    return {"status": "ok"}


@router.get("/me")
def me(authorization: str | None = Header(default=None)):
    u = bearer_user(authorization)
    if not u:
        raise HTTPException(401, "جلسة غير صالحة.")
    return {"user": {"username": u["username"], "fullname": u["fullname"],
                     "role": u["role"]},
            "usage": usage_of(u["username"])}
