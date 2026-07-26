# -*- coding: utf-8 -*-
"""Page Opérations : lancement des jobs du pipeline depuis la console.

Chaque job = un script pipeline/ lancé en sous-processus, journalisé dans
aiocr_data/pipeline_logs/, suivi dans la table jobs (app.db). Un même job ne
peut pas tourner deux fois en parallèle. Lancement réservé au rôle admin ;
consultation dès viewer. L'OCR GPU reste marqué «pod requis» tant que le pod
est éteint.
"""
import datetime as dt
import html
import os
import sqlite3
import subprocess
import sys
import threading
import time

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from api import admin_core as core
from api.admin_core import page, require

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = r"Y:\adala-project\aiocr_data\pipeline_logs"

router = APIRouter(prefix="/api/admin/pipeline")

JOBS = {
    "ingest": {
        "label": "إدخال الوثائق الجديدة (inbox)",
        "desc": "يفحص Y:\\adala-project\\inbox : رفض المكرر، رصد النسخ الجديدة، إدراج الجديد.",
        "cmd": [sys.executable, "-X", "utf8", "pipeline/ingest.py", "add"],
        "minutes": "أقل من دقيقة لكل بضع عشرات من الملفات",
    },
    "juris_index": {
        "label": "إعادة بناء فهرس الاجتهاد القضائي",
        "desc": "يقرأ ملفات Excel للغرف (بما فيها المستكملة حديثاً) ويعيد بناء الفهرس والمواضيع.",
        "cmd": [sys.executable, "-X", "utf8", "pipeline/juris_index.py"],
        "minutes": "1–2 دقيقة",
    },
    "juris_citations": {
        "label": "استخراج الإحالات (قرار → قانون)",
        "desc": "يفحص نصوص القرارات المستخرجة ويحدّث relations.json.",
        "cmd": [sys.executable, "-X", "utf8", "pipeline/juris_citations.py"],
        "minutes": "2–3 دقائق",
    },
    "ocr_quality": {
        "label": "تدقيق جودة الاستخراج",
        "desc": "يعيد حساب درجة الجودة لكل مقطع ويحدّث لائحة الأسوأ 200.",
        "cmd": [sys.executable, "-X", "utf8", "pipeline/ocr_quality.py"],
        "minutes": "أقل من دقيقة",
    },
    "version_graph": {
        "label": "غراف النسخ والتعديلات",
        "desc": "يعيد استخراج هوامش التحيين والنسخ ويحدّث laws_corpus_v2.",
        "cmd": [sys.executable, "-X", "utf8", "pipeline/version_graph.py"],
        "minutes": "5–8 دقائق",
    },
    "page_map": {
        "label": "ربط المقاطع بصفحات PDF",
        "desc": "يعيد حساب صفحة كل مقطع (مطلوب بعد تغيير المدونة).",
        "cmd": [sys.executable, "-X", "utf8", "pipeline/page_map.py"],
        "minutes": "10–15 دقيقة",
    },
    "golden_eval": {
        "label": "تقييم الدقة (الجولدن سيت)",
        "desc": "يختبر استرجاع المصادر على أسئلة معيارية — يجب ألا تتراجع النتيجة مع أي إصدار جديد للمدونة.",
        "cmd": [sys.executable, "-X", "utf8", "pipeline/golden_eval.py"],
        "minutes": "2–4 دقائق",
    },
    "backup": {
        "label": "سخة احتياطية كاملة",
        "desc": "لقطة مؤرَّخة للبيانات الحرجة (Z:) + نسخة خارج الجهاز (GitHub خاص) + مرآة PDF. تشتغل تلقائياً كل ليلة أيضاً.",
        "cmd": [sys.executable, "-X", "utf8", "pipeline/backup.py"],
        "minutes": "2–5 دقائق (المرة الأولى أطول)",
    },
    "rework_all": {
        "label": "🏗 الإعادة الشاملة (بعد اكتمال جمع الوثائق)",
        "desc": "يعيد بناء كل شيء بالترتيب الصحيح: إدخال ← سجل ← نسخ ← صفحات ← فهرس الاجتهاد ← إحالات ← جودة ← تقييم ← نسخة احتياطية. يتوقف عند أول خطأ.",
        "cmd": [sys.executable, "-X", "utf8", "pipeline/rework_all.py"],
        "minutes": "45–90 دقيقة",
    },
    "dedup_clean": {
        "label": "عزل المكررات الداخلية",
        "desc": "ينقل النسخ المكررة داخل نفس المجموعة إلى حجر صحي على Z: (استرجاع ممكن دائماً) ويحدّث السجل.",
        "cmd": [sys.executable, "-X", "utf8", "pipeline/dedup_clean.py"],
        "minutes": "1–2 دقيقة",
    },
    "registry_init": {
        "label": "إعادة بناء السجل الكامل",
        "desc": "يعيد فحص المجموعات الثلاث بالكامل (بصمات، أرقام رسمية). ثقيل — عند الحاجة فقط.",
        "cmd": [sys.executable, "-X", "utf8", "pipeline/ingest.py", "init"],
        "minutes": "20–30 دقيقة",
    },
}

POD_JOBS = [
    ("OCR الاجتهاد القضائي", "5,141+ قرار ممسوح بانتظار OCR (backlog) — يتطلب البود GPU"),
    ("OCR إدخالات جديدة", "27 ملفاً من PMP بانتظار OCR"),
    ("إعادة الإدماج في Qdrant", "بعد أي تغيير في المدونة — التضمينات على البود"),
]


def _ensure_jobs_table():
    with core.conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS jobs(
          id INTEGER PRIMARY KEY, name TEXT, status TEXT, started REAL,
          ended REAL, rc INTEGER, log_path TEXT, launched_by TEXT)""")


def _running(name: str) -> bool:
    with core.conn() as c:
        r = c.execute("SELECT COUNT(*) FROM jobs WHERE name=? AND status='running'",
                      (name,)).fetchone()
    return bool(r[0])


def _run_job(job_id: int, name: str):
    spec = JOBS[name]
    log_path = None
    with core.conn() as c:
        log_path = c.execute("SELECT log_path FROM jobs WHERE id=?",
                             (job_id,)).fetchone()[0]
    rc = -1
    try:
        with open(log_path, "w", encoding="utf-8") as lg:
            p = subprocess.Popen(spec["cmd"], cwd=ROOT, stdout=lg,
                                 stderr=subprocess.STDOUT,
                                 env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            rc = p.wait()
    except Exception as e:
        try:
            with open(log_path, "a", encoding="utf-8") as lg:
                lg.write(f"\nLANCEMENT IMPOSSIBLE: {e}\n")
        except OSError:
            pass
    with core.conn() as c:
        c.execute("UPDATE jobs SET status=?, ended=?, rc=? WHERE id=?",
                  ("done" if rc == 0 else "failed", time.time(), rc, job_id))


@router.post("/{name}/run")
def run(name: str, user: dict = Depends(require("admin"))):
    _ensure_jobs_table()
    if name not in JOBS or _running(name):
        return RedirectResponse("/api/admin/pipeline", status_code=303)
    os.makedirs(LOGS, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOGS, f"{stamp}_{name}.log")
    with core.conn() as c:
        cur = c.execute("INSERT INTO jobs(name,status,started,log_path,launched_by) "
                        "VALUES(?,?,?,?,?)",
                        (name, "running", time.time(), log_path, user["username"]))
        job_id = cur.lastrowid
    core.log_action(user["username"], "pipeline_run", name)
    threading.Thread(target=_run_job, args=(job_id, name), daemon=True).start()
    return RedirectResponse("/api/admin/pipeline", status_code=303)


@router.get("/log/{job_id}", response_class=PlainTextResponse)
def job_log(job_id: int, user: dict = Depends(require("viewer"))):
    with core.conn() as c:
        r = c.execute("SELECT log_path FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r or not os.path.exists(r["log_path"]):
        return "(pas encore de journal)"
    with open(r["log_path"], encoding="utf-8", errors="replace") as f:
        return f.read()[-20000:]


@router.get("", response_class=HTMLResponse)
def pipeline_page(user: dict = Depends(require("viewer")), log: int = Query(0)):
    _ensure_jobs_table()
    with core.conn() as c:
        hist = c.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 25").fetchall()
    running = {r["name"] for r in hist if r["status"] == "running"}
    can_run = user["role"] == "admin"

    cards = []
    for name, spec in JOBS.items():
        on = name in running
        btn = ("<span class='tag t-warn'>⏳ قيد التشغيل…</span>" if on else
               (f"<form class='inline' method='post' action='/api/admin/pipeline/{name}/run'>"
                f"<button class='primary'>تشغيل ▶</button></form>" if can_run else
                "<span class='tag t-gray'>يتطلب دور مدير</span>"))
        cards.append(
            f"<tr><td><b>{spec['label']}</b><br>"
            f"<span style='font-size:12px;color:#666'>{spec['desc']}</span></td>"
            f"<td style='font-size:12px;color:#888'>{spec['minutes']}</td><td>{btn}</td></tr>")

    pod_rows = "".join(
        f"<tr><td><b>{lbl}</b><br><span style='font-size:12px;color:#666'>{d}</span></td>"
        f"<td></td><td><span class='tag t-gray'>🔌 البود مطفأ</span></td></tr>"
        for lbl, d in POD_JOBS)

    hist_rows = "".join(
        f"<tr><td>{r['id']}</td><td>{JOBS.get(r['name'], {}).get('label', r['name'])}</td>"
        f"<td><span class='tag "
        f"{'t-warn' if r['status'] == 'running' else 't-ok' if r['status'] == 'done' else 't-danger'}'>"
        f"{r['status']}</span></td>"
        f"<td class='num'>{dt.datetime.fromtimestamp(r['started']).strftime('%m-%d %H:%M')}</td>"
        f"<td class='num'>{(str(int((r['ended'] or time.time()) - r['started'])) + ' ث')}</td>"
        f"<td>{html.escape(r['launched_by'] or '')}</td>"
        f"<td><a href='?log={r['id']}'>الجرد</a></td></tr>"
        for r in hist)

    log_panel = ""
    if log:
        with core.conn() as c:
            r = c.execute("SELECT * FROM jobs WHERE id=?", (log,)).fetchone()
        if r:
            txt = "(pas encore de journal)"
            if r["log_path"] and os.path.exists(r["log_path"]):
                txt = open(r["log_path"], encoding="utf-8",
                           errors="replace").read()[-8000:]
            auto = ("<meta http-equiv='refresh' content='4'>"
                    if r["status"] == "running" else "")
            log_panel = (f"{auto}<div class='panel'><h2>جرد التنفيذ #{log} — "
                         f"{JOBS.get(r['name'], {}).get('label', r['name'])}</h2>"
                         f"<pre style='background:#1c2b3a;color:#d5e0ea;padding:12px;"
                         f"border-radius:8px;font-size:12px;direction:ltr;text-align:left;"
                         f"overflow-x:auto;max-height:400px;overflow-y:auto'>"
                         f"{html.escape(txt)}</pre></div>")

    body = f"""{log_panel}
<div class="panel"><h2>مهام محلية — تشتغل على هذا الجهاز</h2>
<table><tr><th>المهمة</th><th>المدة التقريبية</th><th></th></tr>{''.join(cards)}</table></div>
<div class="panel"><h2>مهام تتطلب البود (GPU)</h2>
<table><tr><th>المهمة</th><th></th><th>الحالة</th></tr>{pod_rows}</table>
<p style="font-size:12px;color:#666">عند تشغيل البود ستتحول هذه الأزرار إلى قابلة للتشغيل
(الخطوة الأخيرة حسب الخطة).</p></div>
<div class="panel"><h2>آخر التنفيذات</h2>
<table><tr><th>#</th><th>المهمة</th><th>الحالة</th><th>البداية</th><th>المدة</th>
<th>أطلقها</th><th></th></tr>
{hist_rows or '<tr><td colspan=7>لا تنفيذات بعد.</td></tr>'}</table></div>"""
    return page("التشغيل — Pipeline", body, user, "/pipeline")
