# -*- coding: utf-8 -*-
"""Console d'administration du corpus (lecture seule).

    /api/admin           tableau de bord (stats globales)
    /api/admin/docs      inventaire filtrable des documents
    /api/admin/doc       fiche d'un document + ses chunks
    /api/admin/refresh   vide les caches (après ingestion/re-génération)
"""
import html
import json
import os
from collections import Counter, defaultdict
from functools import lru_cache
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, RedirectResponse

DATA = r"Y:\adala-project\aiocr_data"
REGISTRY = os.path.join(DATA, "registry.json")
CORPUS = os.path.join(DATA, "laws_corpus_v2.jsonl")
GRAPH = os.path.join(DATA, "version_graph.json")
DEDUP = os.path.join(DATA, "dedup_report.json")
INGEST = os.path.join(DATA, "ingest_report.json")
BACKLOG = os.path.join(DATA, "juris_ocr_backlog.txt")
JURIS_TEXTS = os.path.join(DATA, "juris_texts.jsonl")

router = APIRouter(prefix="/api/admin")

CSS = """
 body{font-family:'Segoe UI',Tahoma,sans-serif;margin:0;background:#f4f2ec;color:#1a1a18}
 header{background:#fff;border-bottom:1px solid #ddd;padding:12px 20px}
 h1{font-size:17px;margin:0} .meta{color:#666;font-size:13px;margin-top:4px}
 nav a{margin-left:14px;color:#1d5fa5;text-decoration:none;font-size:13px}
 .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;padding:14px}
 .card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px;text-align:center}
 .card b{display:block;font-size:22px;font-weight:600}
 .card span{color:#666;font-size:12px}
 table{width:calc(100% - 28px);margin:0 14px 14px;border-collapse:collapse;background:#fff;
       border:1px solid #ddd;border-radius:8px;overflow:hidden}
 th,td{padding:7px 10px;border-bottom:1px solid #eee;font-size:13px;text-align:right}
 th{background:#faf8f2;color:#666}
 a{color:#1d5fa5;text-decoration:none} a:hover{text-decoration:underline}
 .tag{display:inline-block;font-size:11px;border-radius:5px;padding:2px 8px;margin:1px}
 .t-ok{background:#e7f3e7;color:#1d5c1d} .t-warn{background:#fdf3e0;color:#8a5a00}
 .t-danger{background:#fdeaea;color:#8f1d1d} .t-gray{background:#eee;color:#555}
 .t-blue{background:#e6f0fa;color:#15507e}
 form.f{margin:12px 14px 0;display:flex;gap:8px;flex-wrap:wrap}
 input,select{padding:6px 10px;border:1px solid #bbb;border-radius:6px;font-size:13px}
 .pag{margin:0 14px 16px;font-size:13px}
"""


def _page(title: str, body: str, sub: str = "") -> str:
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<title>{title}</title><style>{CSS}</style></head><body>
<header><h1>🗂 {title}
<nav style="display:inline">
 <a href="/api/admin">اللوحة</a><a href="/api/admin/docs">الوثائق</a>
 <a href="/api/viewer/samples">عينات التحقق</a><a href="/api/admin/refresh">🔄 تحديث البيانات</a>
</nav></h1><div class="meta">{sub}</div></header>{body}</body></html>"""


@lru_cache(maxsize=1)
def _registry() -> dict:
    if os.path.exists(REGISTRY):
        return json.load(open(REGISTRY, encoding="utf-8"))
    return {"docs": {}}


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
def _juris_extracted() -> set:
    s = set()
    if os.path.exists(JURIS_TEXTS):
        for line in open(JURIS_TEXTS, encoding="utf-8"):
            s.add(json.loads(line)["file"])
    return s


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except OSError:
        return default


@router.get("/refresh")
def refresh():
    _registry.cache_clear()
    _chunks_by_file.cache_clear()
    _juris_extracted.cache_clear()
    return RedirectResponse("/api/admin", status_code=303)


@router.get("", response_class=HTMLResponse)
def dashboard():
    reg = _registry()["docs"]
    chunks = _chunks_by_file()
    coll = Counter(d["collection"] for d in reg.values())
    n_chunks = sum(len(v) for v in chunks.values())
    status = Counter(r.get("status", "current") for v in chunks.values() for r in v)
    backlog = sum(1 for _ in open(BACKLOG, encoding="utf-8")) if os.path.exists(BACKLOG) else 0
    dd = _load(DEDUP, {})
    graph = _load(GRAPH, {"edges": []})
    ing = _load(INGEST, None)
    cards = [
        (coll.get("laws", 0), "قوانين (مدونة الإجابات)"),
        (coll.get("adala", 0), "مجموعة عدالة"),
        (coll.get("juris", 0), "قرارات محكمة النقض"),
        (len(chunks), "وثيقة مفهرسة بمقاطع"),
        (n_chunks, "مقطع نصي"),
        (status.get("consolidated", 0), "مقطع محيَّن"),
        (status.get("possibly_abrogated", 0), "منسوخ محتمل"),
        (len(graph.get("edges", [])), "علاقة تعديل مستخرجة"),
        (len(dd.get("exact_duplicates", {})), "زوج مكرر (لائحة القوانين)"),
        (len(_juris_extracted()), "قرار مستخرج النص"),
        (backlog, "بانتظار OCR"),
    ]
    body = "<div class='cards'>" + "".join(
        f"<div class='card'><b>{n:,}</b><span>{lbl}</span></div>" for n, lbl in cards) + "</div>"
    if ing:
        body += ("<table><tr><th colspan=2>آخر عملية إدخال (inbox)</th></tr>"
                 f"<tr><td>جديد</td><td>{len(ing.get('added', []))}</td></tr>"
                 f"<tr><td>نسخ محتملة من نصوص موجودة</td><td>{len(ing.get('new_versions', []))}</td></tr>"
                 f"<tr><td>مكرر مرفوض</td><td>{len(ing.get('duplicates', []))}</td></tr></table>")
    sub = "" if reg else "⚠ السجل غير مبني بعد — python pipeline/ingest.py init"
    return _page("إدارة المدونة القانونية", body, sub)


@router.get("/docs", response_class=HTMLResponse)
def docs(q: str = Query(""), collection: str = Query(""), status: str = Query(""),
         p: int = Query(1, ge=1)):
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
        stat_tags = []
        if ch:
            stat_tags.append(f"<span class='tag t-blue'>{len(ch)} مقطع</span>")
        if st.get("consolidated"):
            stat_tags.append(f"<span class='tag t-ok'>محيَّن ×{st['consolidated']}</span>")
        if st.get("possibly_abrogated"):
            stat_tags.append("<span class='tag t-danger'>منسوخ محتمل</span>")
        if d["collection"] == "juris":
            stat_tags.append("<span class='tag t-ok'>نص مستخرج</span>" if base in juris_ok
                             else "<span class='tag t-warn'>بانتظار OCR</span>")
        elif not d.get("has_text"):
            stat_tags.append("<span class='tag t-warn'>بدون طبقة نص</span>")
        if not stat_tags:
            stat_tags.append("<span class='tag t-gray'>غير مفهرس</span>")
        if status == "indexed" and not ch:
            continue
        if status == "flagged" and not (st.get("consolidated") or st.get("possibly_abrogated")):
            continue
        if status == "noocr" and d.get("has_text"):
            continue
        rows.append(
            f"<tr><td><a href='/api/admin/doc?file={quote(base)}'>{html.escape(base[:75])}</a></td>"
            f"<td>{d['collection']}</td><td>{d.get('npages', '؟')}</td>"
            f"<td>{html.escape('، '.join(d.get('nums', [])[:3]))}</td>"
            f"<td>{''.join(stat_tags)}</td></tr>")
    PER = 60
    total = len(rows)
    rows_p = rows[(p - 1) * PER: p * PER]
    nav = f"<div class='pag'>{total:,} وثيقة — صفحة {p}/{max(1, -(-total // PER))} "
    qs = f"&q={quote(q)}&collection={collection}&status={status}"
    if p > 1:
        nav += f"<a href='?p={p - 1}{qs}'>▶ السابقة</a> "
    if p * PER < total:
        nav += f"<a href='?p={p + 1}{qs}'>التالية ◀</a>"
    nav += "</div>"
    body = f"""<form class="f" method="get">
<input name="q" value="{html.escape(q)}" placeholder="بحث بالاسم أو الرقم الرسمي">
<select name="collection"><option value="">كل المجموعات</option>
<option value="laws" {'selected' if collection == 'laws' else ''}>laws</option>
<option value="adala" {'selected' if collection == 'adala' else ''}>adala</option>
<option value="juris" {'selected' if collection == 'juris' else ''}>juris</option></select>
<select name="status"><option value="">كل الحالات</option>
<option value="indexed" {'selected' if status == 'indexed' else ''}>مفهرس بمقاطع</option>
<option value="flagged" {'selected' if status == 'flagged' else ''}>معدَّل/منسوخ</option>
<option value="noocr" {'selected' if status == 'noocr' else ''}>بدون طبقة نص</option></select>
<input type="submit" value="تصفية"></form>
<table><tr><th>الوثيقة</th><th>المجموعة</th><th>صفحات</th><th>الأرقام الرسمية</th><th>الحالة</th></tr>
{''.join(rows_p)}</table>{nav}"""
    return _page("إدارة المدونة — الوثائق", body)


@router.get("/doc", response_class=HTMLResponse)
def doc_detail(file: str = Query(...)):
    reg = _registry()["docs"]
    base = os.path.basename(file)
    meta = next((d for rel, d in reg.items() if os.path.basename(rel) == base), {})
    ch = _chunks_by_file().get(base, [])
    law = ch[0].get("law", "") if ch else ""
    rows = []
    for r in ch:
        st = r.get("status", "current")
        tag = {"consolidated": "<span class='tag t-ok'>محيَّن</span>",
               "possibly_abrogated": "<span class='tag t-danger'>منسوخ محتمل</span>",
               "check_amendments": "<span class='tag t-warn'>تحقق من التعديلات</span>",
               }.get(st, "<span class='tag t-gray'>عادي</span>")
        refs = "، ".join(r.get("amended_by", []))
        rows.append(
            f"<tr><td><a href='/api/viewer?file={quote(base)}&chunk={r['chunk']}'>مقطع {r['chunk']}</a></td>"
            f"<td>{r.get('page', '؟')}</td><td>{tag}{(' رقم ' + html.escape(refs)) if refs else ''}</td>"
            f"<td>{html.escape((r.get('text') or '')[:90])}…</td></tr>")
    info = (f"المجموعة: {meta.get('collection', '؟')} — الصفحات: {meta.get('npages', '؟')}"
            f" — الأرقام الرسمية: {'، '.join(meta.get('nums', [])) or '—'}"
            f" — طبقة نص: {'نعم' if meta.get('has_text') else 'لا'}"
            f" — <a href='/api/viewer?file={quote(base)}&chunk={ch[0]['chunk'] if ch else '-'}'>فتح في المتصفح 🔎</a>")
    body = (f"<div class='cards'><div class='card'><b>{len(ch)}</b><span>مقطع مفهرس</span></div></div>"
            "<table><tr><th>المقطع</th><th>الصفحة</th><th>الحالة</th><th>مقتطف</th></tr>"
            + "".join(rows) + "</table>") if ch else "<p style='margin:16px'>لا مقاطع مفهرسة لهذه الوثيقة.</p>"
    return _page(html.escape(law or base[:60]), info + body, html.escape(base))
