# -*- coding: utf-8 -*-
"""Console d'administration RimLex — tableau de bord, corpus, jurisprudence,
qualité, comptes et audit. Toutes les pages exigent une session (admin_core).

    /api/admin            tableau de bord (stats + graphiques)
    /api/admin/login      connexion (cookie signé)
    /api/admin/docs       inventaire des documents
    /api/admin/doc        fiche document + chunks
    /api/admin/juris      explorateur de la jurisprudence (17k+ arrêts)
    /api/admin/juris/pdf  ouverture du PDF d'un arrêt
    /api/admin/quality    revue qualité OCR (200 pires chunks)
    /api/admin/users      gestion des comptes et rôles (admin)
    /api/admin/audit      journal des actions
    /api/admin/refresh    recharge les caches de données
"""
import glob
import html
import json
import os
from collections import Counter, defaultdict
from functools import lru_cache
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from api import admin_core as core
from api.admin_core import page, require, svg_bars

DATA = r"Y:\adala-project\aiocr_data"
REGISTRY = os.path.join(DATA, "registry.json")
CORPUS = os.path.join(DATA, "laws_corpus_v2.jsonl")
GRAPH = os.path.join(DATA, "version_graph.json")
DEDUP = os.path.join(DATA, "dedup_report.json")
INGEST = os.path.join(DATA, "ingest_report.json")
BACKLOG = os.path.join(DATA, "juris_ocr_backlog.txt")
JURIS_TEXTS = os.path.join(DATA, "juris_texts.jsonl")
JURIS_INDEX = os.path.join(DATA, "juris_index.json")
RELATIONS = os.path.join(DATA, "relations.json")
QUALITY = os.path.join(DATA, "ocr_quality.json")
JURIS_DIR = r"Z:\jurisprudence"

router = APIRouter(prefix="/api/admin")


# ── caches de données ──────────────────────────────────────────────────────
def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except OSError:
        return default


@lru_cache(maxsize=1)
def _registry() -> dict:
    return _load(REGISTRY, {"docs": {}})


@lru_cache(maxsize=1)
def _chunks_by_file() -> dict:
    m = defaultdict(list)
    if os.path.exists(CORPUS):
        for line in open(CORPUS, encoding="utf-8"):
            r = json.loads(line)
            m[r["file"]].append(r)
    for v in m.values():
        v.sort(key=lambda r: int(r["chunk"]) if str(r["chunk"]).isdigit() else 0)
    return dict(m)


@lru_cache(maxsize=1)
def _juris_index() -> list:
    return _load(JURIS_INDEX, [])


@lru_cache(maxsize=1)
def _juris_extracted() -> set:
    s = set()
    if os.path.exists(JURIS_TEXTS):
        for line in open(JURIS_TEXTS, encoding="utf-8"):
            s.add(json.loads(line)["file"])
    return s


@lru_cache(maxsize=1)
def _quality() -> dict:
    return _load(QUALITY, {})


@lru_cache(maxsize=1)
def _juris_pdf_index() -> dict:
    return {os.path.basename(p): p
            for p in glob.glob(os.path.join(JURIS_DIR, "**", "*.pdf"), recursive=True)}


@router.get("/refresh")
def refresh(user: dict = Depends(require("viewer"))):
    for f in (_registry, _chunks_by_file, _juris_index, _juris_extracted,
              _quality, _juris_pdf_index):
        f.cache_clear()
    core.log_action(user["username"], "refresh_caches")
    return RedirectResponse("/api/admin", status_code=303)


# ── connexion ──────────────────────────────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
def login_page(err: str = ""):
    core.init_db()
    msg = "<p style='color:#a03434;font-size:13px'>بيانات الدخول غير صحيحة.</p>" if err else ""
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<title>RimLex — دخول</title><style>{core.CSS}
 .login{{max-width:340px;margin:10vh auto;background:#fff;border:1px solid #ddd;
        border-radius:10px;padding:26px}}
 .login h1{{font-size:18px;margin:0 0 4px}} .login p.sub{{color:#666;font-size:13px;margin:0 0 16px}}
 .login input{{width:100%;box-sizing:border-box;margin-bottom:10px}}
 .login button{{width:100%}}</style></head><body>
<div class="login"><h1><span style="color:#a98a44">RimLex</span> · الإدارة</h1>
<p class="sub">منصة المساعد القانوني — الدخول للمخوَّلين فقط</p>{msg}
<form method="post" action="/api/admin/login">
<input type="text" name="username" placeholder="اسم المستعمل" required autofocus>
<input type="password" name="password" placeholder="كلمة السر" required>
<button class="primary">دخول</button></form></div></body></html>"""


@router.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    core.init_db()
    username = username.strip()
    with core.conn() as c:
        r = c.execute("SELECT username, pw, active FROM users "
                      "WHERE username=? COLLATE NOCASE", (username,)).fetchone()
    if r:
        username = r["username"]          # casse canonique du compte
    if not r or not r["active"] or not core.verify_pw(password, r["pw"]):
        core.log_action(username, "login_failed")
        return RedirectResponse("/api/admin/login?err=1", status_code=303)
    core.log_action(username, "login")
    resp = RedirectResponse("/api/admin", status_code=303)
    resp.set_cookie("rimlex_session", core.sign_token(username),
                    httponly=True, samesite="lax", max_age=12 * 3600)
    return resp


@router.get("/logout")
def logout(user: dict = Depends(require("viewer"))):
    core.log_action(user["username"], "logout")
    resp = RedirectResponse("/api/admin/login", status_code=303)
    resp.delete_cookie("rimlex_session")
    return resp


# ── tableau de bord ────────────────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
def dashboard(user: dict = Depends(require("viewer"))):
    reg = _registry()["docs"]
    chunks = _chunks_by_file()
    ji = _juris_index()
    q = _quality()
    coll = Counter(d["collection"] for d in reg.values())
    status = Counter(r.get("status", "current") for v in chunks.values() for r in v)
    backlog = sum(1 for _ in open(BACKLOG, encoding="utf-8")) if os.path.exists(BACKLOG) else 0
    rels = _load(RELATIONS, [])
    with core.conn() as c:
        fb_n = c.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        cor = dict(c.execute("SELECT status, COUNT(*) FROM corrections "
                             "GROUP BY status").fetchall())
        ann_n = c.execute("SELECT COUNT(*) FROM annotations "
                          "WHERE status='validated'").fetchone()[0]
        users_n = c.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0]

    cards = [
        (len(reg), "وثيقة في السجل"),
        (coll.get("laws", 0), "قوانين"), (coll.get("adala", 0), "مجموعة عدالة"),
        (coll.get("juris", 0), "قرارات النقض"),
        (sum(len(v) for v in chunks.values()), "مقطع نصي"),
        (status.get("consolidated", 0), "مقطع محيَّن"),
        (len(ji), "قرار مفهرس"), (len(rels), "إحالة قرار→قانون"),
        (backlog, "بانتظار OCR"), (fb_n, "ملاحظة واردة"),
        (cor.get("proposed", 0), "تصحيح بانتظار المصادقة"),
        (ann_n, "ملاحظة خبير معتمدة"), (users_n, "مستعمل نشط"),
    ]
    body = "<div class='cards'>" + "".join(
        f"<div class='card'><b>{n:,}</b><span>{lbl}</span></div>"
        for n, lbl in cards) + "</div>"

    # décisions par année (index jurisprudence)
    yr = Counter(d["year"] for d in ji if d.get("year"))
    years = sorted(y for y in yr if y >= "1998")
    body += ("<div class='panel'><h2>القرارات القضائية حسب السنة</h2>"
             + svg_bars([(y, yr[y]) for y in years]) + "</div>")

    ch = Counter(d["chamber"] for d in ji)
    body += ("<div class='panel'><h2>حسب الغرفة</h2>"
             + svg_bars(sorted(ch.items(), key=lambda x: -x[1]), color="bar2")
             + "</div>")

    if q:
        buckets = Counter()
        for v in q.values():
            buckets["ممتاز ≥0.9" if v >= .9 else "جيد 0.75-0.9" if v >= .75
                    else "متوسط 0.5-0.75" if v >= .5 else "ضعيف <0.5"] += 1
        order = ["ممتاز ≥0.9", "جيد 0.75-0.9", "متوسط 0.5-0.75", "ضعيف <0.5"]
        body += ("<div class='panel'><h2>جودة الاستخراج (13k مقطع قانوني)</h2>"
                 + svg_bars([(k, buckets.get(k, 0)) for k in order]) + "</div>")

    ing = _load(INGEST, None)
    if ing:
        body += ("<div class='panel'><h2>آخر عملية إدخال</h2><table>"
                 f"<tr><td>جديد</td><td>{len(ing.get('added', []))}</td>"
                 f"<td>نسخ محتملة</td><td>{len(ing.get('new_versions', []))}</td>"
                 f"<td>مكرر مرفوض</td><td>{len(ing.get('duplicates', []))}</td></tr></table></div>")
    return page("لوحة القيادة", body, user, "")


# ── inventaire des documents ───────────────────────────────────────────────
@router.get("/docs", response_class=HTMLResponse)
def docs(user: dict = Depends(require("viewer")), q: str = Query(""),
         collection: str = Query(""), status: str = Query(""), p: int = Query(1, ge=1)):
    reg = _registry()["docs"]
    chunks = _chunks_by_file()
    juris_ok = _juris_extracted()
    rows = []
    for rel, d in reg.items():
        base = os.path.basename(rel)
        if q and q not in base and not any(q in n for n in d.get("nums", [])):
            continue
        if collection and d["collection"] != collection:
            continue
        ch = chunks.get(base, [])
        st = Counter(r.get("status", "current") for r in ch)
        if status == "indexed" and not ch:
            continue
        if status == "flagged" and not (st.get("consolidated") or st.get("possibly_abrogated")):
            continue
        if status == "noocr" and d.get("has_text"):
            continue
        tags = []
        if ch:
            tags.append(f"<span class='tag t-blue'>{len(ch)} مقطع</span>")
        if st.get("consolidated"):
            tags.append(f"<span class='tag t-ok'>محيَّن ×{st['consolidated']}</span>")
        if st.get("possibly_abrogated"):
            tags.append("<span class='tag t-danger'>منسوخ محتمل</span>")
        if d["collection"] == "juris":
            tags.append("<span class='tag t-ok'>نص مستخرج</span>" if base in juris_ok
                        else "<span class='tag t-warn'>بانتظار OCR</span>")
        elif not d.get("has_text"):
            tags.append("<span class='tag t-warn'>بدون طبقة نص</span>")
        if not tags:
            tags.append("<span class='tag t-gray'>غير مفهرس</span>")
        rows.append(f"<tr><td><a href='/api/admin/doc?file={quote(base)}'>"
                    f"{html.escape(base[:75])}</a></td><td>{d['collection']}</td>"
                    f"<td>{d.get('npages', '؟')}</td>"
                    f"<td>{html.escape('، '.join(d.get('nums', [])[:3]))}</td>"
                    f"<td>{''.join(tags)}</td></tr>")
    PER = 60
    total = len(rows)
    rows_p = rows[(p - 1) * PER: p * PER]
    qs = f"&q={quote(q)}&collection={collection}&status={status}"
    nav = f"<div class='pag'>{total:,} وثيقة — صفحة {p}/{max(1, -(-total // PER))} "
    if p > 1:
        nav += f"<a href='?p={p - 1}{qs}'>▶ السابقة</a> "
    if p * PER < total:
        nav += f"<a href='?p={p + 1}{qs}'>التالية ◀</a>"
    nav += "</div>"
    body = f"""<div class="panel"><form class="filters" method="get">
<input type="text" name="q" value="{html.escape(q)}" placeholder="بحث بالاسم أو الرقم الرسمي">
<select name="collection"><option value="">كل المجموعات</option>
<option value="laws" {'selected' if collection == 'laws' else ''}>laws</option>
<option value="adala" {'selected' if collection == 'adala' else ''}>adala</option>
<option value="juris" {'selected' if collection == 'juris' else ''}>juris</option></select>
<select name="status"><option value="">كل الحالات</option>
<option value="indexed" {'selected' if status == 'indexed' else ''}>مفهرس</option>
<option value="flagged" {'selected' if status == 'flagged' else ''}>معدَّل/منسوخ</option>
<option value="noocr" {'selected' if status == 'noocr' else ''}>بدون طبقة نص</option></select>
<button>تصفية</button></form>
<table><tr><th>الوثيقة</th><th>المجموعة</th><th>صفحات</th><th>الأرقام</th><th>الحالة</th></tr>
{''.join(rows_p)}</table>{nav}</div>"""
    return page("الوثائق", body, user, "/docs")


@router.get("/doc", response_class=HTMLResponse)
def doc_detail(file: str = Query(...), user: dict = Depends(require("viewer"))):
    base = os.path.basename(file)
    reg = _registry()["docs"]
    meta = next((d for rel, d in reg.items() if os.path.basename(rel) == base), {})
    ch = _chunks_by_file().get(base, [])
    q = _quality()
    rows = []
    for r in ch:
        st = r.get("status", "current")
        tag = {"consolidated": "<span class='tag t-ok'>محيَّن</span>",
               "possibly_abrogated": "<span class='tag t-danger'>منسوخ محتمل</span>",
               "check_amendments": "<span class='tag t-warn'>تحقق</span>",
               }.get(st, "<span class='tag t-gray'>عادي</span>")
        score = q.get(f"{base}#{r['chunk']}")
        sc = (f"<span class='tag {'t-ok' if score >= .75 else 't-warn' if score >= .5 else 't-danger'}'>"
              f"{score:.2f}</span>") if score is not None else ""
        refs = "، ".join(r.get("amended_by", []))
        rows.append(f"<tr><td><a href='/api/viewer?file={quote(base)}&chunk={r['chunk']}'>"
                    f"مقطع {r['chunk']}</a></td><td>{r.get('page', '؟')}</td>"
                    f"<td>{tag}{(' ' + html.escape(refs)) if refs else ''}</td><td>{sc}</td>"
                    f"<td>{html.escape((r.get('text') or '')[:85])}…</td></tr>")
    law = ch[0].get("law", "") if ch else ""
    info = (f"<div class='panel'><b>{html.escape(law or base)}</b><br>"
            f"<span style='font-size:13px;color:#666'>{html.escape(base)} — "
            f"{meta.get('collection', '؟')} · {meta.get('npages', '؟')} صفحة · "
            f"أرقام: {'، '.join(meta.get('nums', [])) or '—'} · "
            f"<a href='/api/viewer?file={quote(base)}&chunk={ch[0]['chunk'] if ch else '-'}'>"
            f"فتح في المتصفح 🔎</a></span></div>")
    body = info + ("<div class='panel'><table><tr><th>المقطع</th><th>الصفحة</th>"
                   "<th>الحالة</th><th>الجودة</th><th>مقتطف</th></tr>"
                   + "".join(rows) + "</table></div>" if ch else
                   "<div class='panel'>لا مقاطع مفهرسة لهذه الوثيقة.</div>")
    return page(base[:50], body, user, "/docs")


# ── explorateur jurisprudence ──────────────────────────────────────────────
@router.get("/juris", response_class=HTMLResponse)
def juris(user: dict = Depends(require("viewer")), q: str = Query(""),
          chamber: str = Query(""), theme: str = Query(""), year: str = Query(""),
          p: int = Query(1, ge=1)):
    ji = _juris_index()
    chambers = sorted({d["chamber"] for d in ji})
    themes = sorted({t for d in ji for t in d.get("themes", [])})
    years = sorted({d["year"] for d in ji if d.get("year")}, reverse=True)
    res = [d for d in ji
           if (not chamber or d["chamber"] == chamber)
           and (not theme or theme in d.get("themes", []))
           and (not year or d["year"] == year)
           and (not q or q in d.get("qaida_clean", "") or q in d.get("dec_no", "")
                or q in d.get("file_no", ""))]
    PER = 50
    total = len(res)

    def _theme_tags(d):
        return "".join(f"<span class='tag t-blue'>{html.escape(t)}</span>"
                       for t in d.get("themes", []))

    rows = "".join(
        f"<tr><td><a href='/api/admin/juris/pdf?file={quote(d['file'])}' target='_blank'>"
        f"{html.escape(d['dec_no'] or d['file'][:20])}</a></td>"
        f"<td>{html.escape(d['file_no'])}</td><td>{d['year'] or '؟'}</td>"
        f"<td>{html.escape(d['chamber'].replace('الغرفة ', '').replace('غرفة ', ''))}</td>"
        f"<td>{_theme_tags(d)}</td>"
        f"<td style='font-size:12px;color:#555'>{html.escape((d.get('qaida_clean') or '')[:80])}</td></tr>"
        for d in res[(p - 1) * PER: p * PER])
    opts = lambda vals, cur: "".join(  # noqa: E731
        f"<option value='{html.escape(v)}' {'selected' if v == cur else ''}>{html.escape(v)}</option>"
        for v in vals)
    qs = f"&q={quote(q)}&chamber={quote(chamber)}&theme={quote(theme)}&year={year}"
    nav = f"<div class='pag'>{total:,} قرار — صفحة {p}/{max(1, -(-total // PER))} "
    if p > 1:
        nav += f"<a href='?p={p - 1}{qs}'>▶</a> "
    if p * PER < total:
        nav += f"<a href='?p={p + 1}{qs}'>◀</a>"
    nav += "</div>"
    body = f"""<div class="panel"><form class="filters" method="get">
<input type="text" name="q" value="{html.escape(q)}" placeholder="بحث في القاعدة أو الأرقام">
<select name="chamber"><option value="">كل الغرف</option>{opts(chambers, chamber)}</select>
<select name="theme"><option value="">كل المواضيع</option>{opts(themes, theme)}</select>
<select name="year"><option value="">كل السنوات</option>{opts(years, year)}</select>
<button>تصفية</button></form>
<table><tr><th>القرار</th><th>الملف</th><th>السنة</th><th>الغرفة</th><th>المواضيع</th><th>القاعدة</th></tr>
{rows}</table>{nav}</div>"""
    return page("الاجتهاد القضائي", body, user, "/juris")


@router.get("/juris/pdf")
def juris_pdf(file: str = Query(...), user: dict = Depends(require("viewer"))):
    path = _juris_pdf_index().get(os.path.basename(file))
    if not path:
        return HTMLResponse("<p>الملف غير موجود محلياً (ربما بانتظار التحميل).</p>",
                            status_code=404)
    return FileResponse(path, media_type="application/pdf")


# ── revue qualité ──────────────────────────────────────────────────────────
@router.get("/quality", response_class=HTMLResponse)
def quality(user: dict = Depends(require("viewer"))):
    import csv
    path = os.path.join(DATA, "ocr_review_worst.csv")
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    trs = "".join(
        f"<tr><td><span class='tag {'t-danger' if float(r['score']) < .5 else 't-warn'}'>"
        f"{r['score']}</span></td><td>{html.escape(r['law'])}</td>"
        f"<td><a href='{html.escape(r['viewer_url'])}' target='_blank'>مقطع {r['chunk']}"
        f" (ص. {r['page']})</a></td>"
        f"<td style='font-size:12px;color:#555'>{html.escape(r['excerpt'][:100])}</td></tr>"
        for r in rows[:200])
    body = (f"<div class='panel'><h2>أضعف {len(rows)} مقطعاً — راجعها في العارض "
            f"(الصفحة الأصلية بجانب النص)</h2>"
            f"<table><tr><th>الدرجة</th><th>القانون</th><th>المقطع</th><th>مقتطف</th></tr>"
            f"{trs}</table></div>")
    return page("جودة الاستخراج", body, user, "/quality")


# ── gestion des comptes ────────────────────────────────────────────────────
@router.get("/users", response_class=HTMLResponse)
def users_page(user: dict = Depends(require("admin")), msg: str = ""):
    with core.conn() as c:
        rows = c.execute("SELECT * FROM users ORDER BY id").fetchall()
    trs = "".join(
        f"<tr><td>{r['id']}</td><td>{html.escape(r['username'])}</td>"
        f"<td>{html.escape(r['fullname'] or '')}</td>"
        f"<td>{core.ROLE_AR.get(r['role'], r['role'])}</td>"
        f"<td>{'<span class=\"tag t-ok\">نشط</span>' if r['active'] else '<span class=\"tag t-danger\">موقوف</span>'}</td>"
        f"<td><form class='inline' method='post' action='/api/admin/users/{r['id']}/update'>"
        f"<select name='role'>" + "".join(
            f"<option value='{ro}' {'selected' if ro == r['role'] else ''}>{ar}</option>"
            for ro, ar in core.ROLE_AR.items()) +
        f"</select> <input type='text' name='newpw' placeholder='كلمة سر جديدة (اختياري)' size='16'>"
        f"<button name='act' value='save'>حفظ</button> "
        f"<button name='act' value='toggle'>{'إيقاف' if r['active'] else 'تنشيط'}</button>"
        f"</form></td></tr>"
        for r in rows)
    note = f"<p style='color:#1d5c1d;font-size:13px'>{html.escape(msg)}</p>" if msg else ""
    body = f"""{note}<div class="panel"><h2>إنشاء حساب</h2>
<form method="post" action="/api/admin/users/create" class="filters">
<input type="text" name="username" placeholder="اسم الدخول" required>
<input type="text" name="fullname" placeholder="الاسم الكامل">
<select name="role">""" + "".join(
        f"<option value='{ro}'>{ar}</option>" for ro, ar in core.ROLE_AR.items()) + """</select>
<input type="password" name="password" placeholder="كلمة السر" required>
<button class="primary">إنشاء</button></form></div>
<div class="panel"><h2>الحسابات</h2>
<table><tr><th>#</th><th>الدخول</th><th>الاسم</th><th>الدور</th><th>الحالة</th><th>إجراءات</th></tr>
""" + trs + "</table></div>"
    return page("المستعملون", body, user, "/users")


@router.post("/users/create")
def user_create(user: dict = Depends(require("admin")), username: str = Form(...),
                fullname: str = Form(""), role: str = Form("viewer"),
                password: str = Form(...)):
    import time as _t
    role = role if role in core.ROLE_RANK else "viewer"
    try:
        with core.conn() as c:
            c.execute("INSERT INTO users(username, fullname, role, pw, created_ts) "
                      "VALUES(?,?,?,?,?)",
                      (username.strip(), fullname.strip(), role,
                       core.hash_pw(password), _t.time()))
        core.log_action(user["username"], "user_create", f"{username} ({role})")
    except Exception:
        pass
    return RedirectResponse("/api/admin/users", status_code=303)


@router.post("/users/{uid}/update")
def user_update(uid: int, user: dict = Depends(require("admin")),
                role: str = Form("viewer"), newpw: str = Form(""),
                act: str = Form("save")):
    with core.conn() as c:
        target = c.execute("SELECT username, active FROM users WHERE id=?",
                           (uid,)).fetchone()
        if not target:
            return RedirectResponse("/api/admin/users", status_code=303)
        if act == "toggle":
            c.execute("UPDATE users SET active=? WHERE id=?",
                      (0 if target["active"] else 1, uid))
            core.log_action(user["username"], "user_toggle", target["username"])
        else:
            if role in core.ROLE_RANK:
                c.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
            if newpw.strip():
                c.execute("UPDATE users SET pw=? WHERE id=?",
                          (core.hash_pw(newpw.strip()), uid))
            core.log_action(user["username"], "user_update",
                            f"{target['username']} role={role} pw={'oui' if newpw else 'non'}")
    return RedirectResponse("/api/admin/users", status_code=303)


# ── journal d'audit ────────────────────────────────────────────────────────
@router.get("/audit", response_class=HTMLResponse)
def audit(user: dict = Depends(require("validator")), p: int = Query(1, ge=1)):
    import datetime as dt
    PER = 80
    with core.conn() as c:
        total = c.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
        rows = c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ? OFFSET ?",
                         (PER, (p - 1) * PER)).fetchall()
    trs = "".join(
        f"<tr><td class='num'>{dt.datetime.fromtimestamp(r['ts']).strftime('%Y-%m-%d %H:%M')}</td>"
        f"<td>{html.escape(r['user'] or '')}</td><td>{html.escape(r['action'])}</td>"
        f"<td style='font-size:12px;color:#555'>{html.escape(r['detail'] or '')}</td></tr>"
        for r in rows)
    nav = f"<div class='pag'>{total:,} حدث — صفحة {p} "
    if p > 1:
        nav += f"<a href='?p={p - 1}'>▶</a> "
    if p * PER < total:
        nav += f"<a href='?p={p + 1}'>◀</a>"
    body = (f"<div class='panel'><table><tr><th>التاريخ</th><th>المستعمل</th>"
            f"<th>الإجراء</th><th>تفاصيل</th></tr>{trs}</table>{nav}</div></div>")
    return page("سجل الأحداث", body, user, "/audit")
