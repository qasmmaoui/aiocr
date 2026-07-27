# -*- coding: utf-8 -*-
"""Boucle expert : endpoints publics (retours/corrections depuis le chat) et
pages authentifiées de revue, mصادقة, annotations et historique.

Gouvernance : l'expert PROPOSE, un validateur (rôle validator+) DISPOSE, rien
n'est appliqué à chaud. Les annotations validées sont servies au modèle comme
contexte cité («ملاحظة خبير معتمدة») — voir rag/answer.py.
"""
import html
import json
import time

from fastapi import APIRouter, Depends, Form, Header, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict

from api import admin_core as core
from api.admin_core import page, require

router = APIRouter(prefix="/api")


# ── endpoints publics (appelés depuis le front de chat) ────────────────────
class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str                      # up | down | contest
    question: str = ""
    answer: str = ""
    sources: list = []
    comment: str = ""
    user: str = "anonyme"


class CorrectionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    target_type: str               # chunk_text | metadata | version_status | theme
    target_ref: str
    old_value: str = ""
    proposed_value: str
    evidence: str = ""
    proposed_by: str = "anonyme"


@router.post("/feedback")
def add_feedback(fb: FeedbackIn, authorization: str | None = Header(default=None)):
    core.init_db()
    try:
        from api.mobile_auth import bearer_user
        u = bearer_user(authorization)
        if u:
            fb.user = u["username"]        # identité JWT prioritaire sur le champ libre
    except Exception:
        pass
    with core.conn() as c:
        cur = c.execute(
            "INSERT INTO feedback(ts,user,type,question,answer,sources_json,comment) "
            "VALUES(?,?,?,?,?,?,?)",
            (time.time(), fb.user, fb.type, fb.question, fb.answer,
             json.dumps(fb.sources, ensure_ascii=False), fb.comment))
        return {"feedback_id": cur.lastrowid, "status": "recorded"}


@router.post("/feedback/{fb_id}/correction")
def add_correction(fb_id: int, cor: CorrectionIn):
    core.init_db()
    with core.conn() as c:
        cur = c.execute(
            "INSERT INTO corrections(ts,feedback_id,target_type,target_ref,"
            "old_value,proposed_value,evidence,proposed_by) VALUES(?,?,?,?,?,?,?,?)",
            (time.time(), fb_id, cor.target_type, cor.target_ref,
             cor.old_value, cor.proposed_value, cor.evidence, cor.proposed_by))
        return {"correction_id": cur.lastrowid, "status": "proposed"}


def annotations_for(file_base: str, nums: list[str] | None = None) -> list[dict]:
    """Annotations validées jointes déterministiquement (fichier ou numéro)."""
    try:
        keys = [file_base] + list(nums or [])
        qmarks = ",".join("?" * len(keys))
        with core.conn() as c:
            rows = c.execute(
                f"SELECT text, author_role, article FROM annotations "
                f"WHERE status='validated' AND target_ref IN ({qmarks})",
                keys).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ── file de revue (validator+) ─────────────────────────────────────────────
_TAG = {"new": "t-blue", "proposed": "t-warn", "validated": "t-ok",
        "rejected": "t-danger", "shipped": "t-ok", "handled": "t-gray"}


@router.get("/admin/review", response_class=HTMLResponse)
def review_queue(user: dict = Depends(require("validator")),
                 show: str = Query("pending")):
    with core.conn() as c:
        if show == "history":
            cors = c.execute("SELECT * FROM corrections WHERE status!='proposed' "
                             "ORDER BY decided_ts DESC LIMIT 300").fetchall()
        else:
            cors = c.execute("SELECT * FROM corrections WHERE status='proposed' "
                             "ORDER BY id DESC").fetchall()
        fbs = c.execute("SELECT * FROM feedback ORDER BY id DESC LIMIT 100").fetchall()

    import datetime as dt
    cor_rows = "".join(
        f"<tr><td>{r['id']}</td><td>{html.escape(r['target_type'] or '')}</td>"
        f"<td>{html.escape((r['target_ref'] or '')[:40])}</td>"
        f"<td style='font-size:12px'>{html.escape((r['old_value'] or '')[:50])} ← "
        f"<b>{html.escape((r['proposed_value'] or '')[:50])}</b></td>"
        f"<td>{html.escape(r['proposed_by'] or '')}</td>"
        f"<td><span class='tag {_TAG.get(r['status'], 't-gray')}'>{r['status']}</span></td>"
        + (f"<td><form class='inline' method='post' "
           f"action='/api/admin/review/correction/{r['id']}/decide'>"
           f"<button name='decision' value='validated' class='primary'>✓ مصادقة</button> "
           f"<button name='decision' value='rejected'>✗ رفض</button></form></td>"
           if r["status"] == "proposed" else
           f"<td style='font-size:12px'>{html.escape(r['validated_by'] or '')} — "
           + (dt.datetime.fromtimestamp(r["decided_ts"]).strftime("%Y-%m-%d %H:%M")
              if r["decided_ts"] else "") + "</td>")
        + "</tr>"
        for r in cors)

    fb_rows = "".join(
        f"<tr><td>{r['id']}</td><td><span class='tag t-blue'>{r['type']}</span></td>"
        f"<td>{html.escape((r['question'] or '')[:60])}</td>"
        f"<td>{html.escape((r['comment'] or '')[:60])}</td>"
        f"<td>{html.escape(r['user'] or '')}</td></tr>"
        for r in fbs)

    tab = ("<a href='?show=pending'>⏳ بانتظار المصادقة</a> · "
           "<a href='?show=history'>🗂 السجل التاريخي للقرارات</a>")
    body = f"""<div class="panel"><h2>التصحيحات — {tab}</h2>
<p style="font-size:12.5px;color:#666">المصادقة نهائية وموقَّعة باسمك ({html.escape(user['username'])})
— التصحيحات المصادَق عليها تُطبَّق مع الإصدار القادم للمدونة، لا فورياً.</p>
<table><tr><th>#</th><th>النوع</th><th>الهدف</th><th>التغيير</th><th>اقترحه</th>
<th>الحالة</th><th>{'القرار' if show != 'history' else 'قرّره'}</th></tr>
{cor_rows or '<tr><td colspan=7>لا شيء هنا.</td></tr>'}</table></div>
<div class="panel"><h2>الملاحظات والاعتراضات الواردة من المستعملين</h2>
<table><tr><th>#</th><th>النوع</th><th>السؤال</th><th>تعليق</th><th>المستعمل</th></tr>
{fb_rows or '<tr><td colspan=5>لا ملاحظات بعد.</td></tr>'}</table></div>"""
    return page("المراجعة والمصادقة", body, user, "/review")


@router.post("/admin/review/correction/{cid}/decide")
def decide_correction(cid: int, user: dict = Depends(require("validator")),
                      decision: str = Form(...)):
    if decision not in ("validated", "rejected"):
        decision = "rejected"
    with core.conn() as c:
        c.execute("UPDATE corrections SET status=?, validated_by=?, decided_ts=? "
                  "WHERE id=? AND status='proposed'",
                  (decision, user["username"], time.time(), cid))
    core.log_action(user["username"], f"correction_{decision}", f"id={cid}")
    return RedirectResponse("/api/admin/review", status_code=303)


# ── annotations (validator+) ───────────────────────────────────────────────
@router.get("/admin/annotations", response_class=HTMLResponse)
def annotations_page(user: dict = Depends(require("validator"))):
    with core.conn() as c:
        anns = c.execute("SELECT * FROM annotations ORDER BY id DESC LIMIT 200").fetchall()
    rows = "".join(
        f"<tr><td>{r['id']}</td><td>{html.escape(r['target_ref'] or '')}"
        f"{(' — م. ' + html.escape(r['article'])) if r['article'] else ''}</td>"
        f"<td style='font-size:12.5px'>{html.escape((r['text'] or '')[:110])}</td>"
        f"<td>{html.escape(r['author_role'] or '')}</td>"
        f"<td><span class='tag {'t-ok' if r['status'] == 'validated' else 't-gray'}'>"
        f"{r['status']}</span></td>"
        f"<td><form class='inline' method='post' action='/api/admin/annotations/{r['id']}/toggle'>"
        f"<button>{'تعطيل' if r['status'] == 'validated' else 'تفعيل'}</button></form></td></tr>"
        for r in anns)
    body = f"""<div class="panel"><h2>إضافة ملاحظة معتمدة — تُحقن في سياق النموذج
وتُذكر في الأجوبة كـ«ملاحظة خبير معتمدة»</h2>
<form method="post" action="/api/admin/annotations/create" class="filters" style="align-items:flex-start">
<input type="text" name="target_ref" placeholder="اسم ملف PDF أو رقم رسمي (مثل 2.14.652)" size="34" required>
<input type="text" name="article" placeholder="المادة (اختياري)" size="12">
<input type="text" name="author_role" placeholder="صفة صاحبها (قاضٍ، محامٍ...)" size="18">
<textarea name="text" placeholder="نص الملاحظة" rows="2" cols="46" required></textarea>
<button class="primary">اعتماد وإضافة</button></form></div>
<div class="panel"><h2>الملاحظات</h2>
<table><tr><th>#</th><th>النطاق</th><th>النص</th><th>الصفة</th><th>الحالة</th><th></th></tr>
{rows or '<tr><td colspan=6>لا ملاحظات بعد.</td></tr>'}</table></div>"""
    return page("الملاحظات المعتمدة", body, user, "/annotations")


@router.post("/admin/annotations/create")
def annotation_create(user: dict = Depends(require("validator")),
                      target_ref: str = Form(...), article: str = Form(""),
                      author_role: str = Form("خبير"), text: str = Form(...)):
    with core.conn() as c:
        c.execute("INSERT INTO annotations(ts,scope,target_ref,article,text,"
                  "author_role,status,validated_by) VALUES(?,?,?,?,?,?,?,?)",
                  (time.time(), "doc", target_ref.strip(), article.strip(),
                   text.strip(), author_role.strip() or "خبير", "validated",
                   user["username"]))
    core.log_action(user["username"], "annotation_create", target_ref[:80])
    return RedirectResponse("/api/admin/annotations", status_code=303)


@router.post("/admin/annotations/{aid}/toggle")
def annotation_toggle(aid: int, user: dict = Depends(require("validator"))):
    with core.conn() as c:
        r = c.execute("SELECT status FROM annotations WHERE id=?", (aid,)).fetchone()
        if r:
            new = "retired" if r["status"] == "validated" else "validated"
            c.execute("UPDATE annotations SET status=? WHERE id=?", (new, aid))
            core.log_action(user["username"], f"annotation_{new}", f"id={aid}")
    return RedirectResponse("/api/admin/annotations", status_code=303)
