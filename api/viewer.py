# -*- coding: utf-8 -*-
"""Visionneuse de preuves : page PDF originale côte à côte avec le texte OCR.

Endpoints publics (lecture seule, documents légaux publics) :
    GET /api/viewer?file=..&chunk=..          page HTML côte à côte
    GET /api/viewer/page-image?file=..&page=N rendu PNG de la page
"""
import glob
import html
import json
import os
from functools import lru_cache

import fitz
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

# Chemins surchargeables (le pod Linux n'a pas les lettres de lecteur Windows)
LAWS_DIR = os.environ.get("RIMLEX_LAWS_DIR", r"Y:\adala-project\laws")
_DATA = os.environ.get("RIMLEX_DATA_DIR", r"Y:\adala-project\aiocr_data")
PAGED_CORPUS = os.path.join(_DATA, "laws_corpus_v2.jsonl")
# Incrémenter à chaque évolution du rendu (casse le cache navigateur des images)
RENDER_VERSION = 2

router = APIRouter(prefix="/api/viewer")


ADALA_DIR = os.environ.get("RIMLEX_ADALA_DIR", r"Y:\adala-project\adala_pdfs")


@lru_cache(maxsize=1)
def _pdf_index() -> dict:
    """basename -> chemin. Le corpus laws est prioritaire sur adala_pdfs."""
    idx = {os.path.basename(p): p
           for p in glob.glob(os.path.join(ADALA_DIR, "**", "*.pdf"), recursive=True)}
    idx.update({os.path.basename(p): p
                for p in glob.glob(os.path.join(LAWS_DIR, "**", "*.pdf"), recursive=True)})
    return idx


@lru_cache(maxsize=1)
def _chunk_index() -> dict:
    """(file, chunk) -> record du corpus (avec page si mappée)."""
    idx = {}
    if os.path.exists(PAGED_CORPUS):
        with open(PAGED_CORPUS, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                idx[(r["file"], str(r["chunk"]))] = r
    return idx


@lru_cache(maxsize=1)
def _first_chunk() -> dict:
    """file -> plus petit numéro de chunk (point d'entrée d'un document)."""
    first: dict = {}
    for (f, c) in _chunk_index():
        try:
            ci = int(c)
        except ValueError:
            continue
        if f not in first or ci < first[f]:
            first[f] = ci
    return first


def _doc_link(f: str, label: str) -> str:
    """Lien vers un document : chunk d'entrée s'il est indexé, sinon simple
    consultation page à page (chunk='-')."""
    ch = _first_chunk().get(f, "-")
    return (f"<a href='?file={html.escape(f)}&chunk={ch}'>{html.escape(label)}</a>")


def chunk_page(file: str, chunk) -> int | None:
    r = _chunk_index().get((file, str(chunk)))
    return r.get("page") if r else None


def _resolve_pdf(file: str) -> str:
    path = _pdf_index().get(os.path.basename(file))
    if not path:
        raise HTTPException(404, "Document introuvable.")
    return path


@router.get("/samples", response_class=HTMLResponse)
def samples(n: int = Query(30, ge=1, le=200)):
    """Page de test : échantillon aléatoire de mقاطع cliquables."""
    import random
    recs = list(_chunk_index().values())
    picks = random.sample(recs, min(n, len(recs)))
    rows = []
    for r in picks:
        fq = html.escape(r["file"])
        law = html.escape((r.get("law") or r["file"])[:70])
        art = f" — المادة/الفصل {html.escape(str(r['article']))}" if r.get("article") and str(r["article"]) != "None" else ""
        pg = f"ص. {r['page']}" if r.get("page") else "؟"
        exact = "✓ دقيق" if r.get("page_src") == "match" else "≈ تقديري"
        rows.append(
            f"<tr><td><a href='/api/viewer?file={fq}&chunk={r['chunk']}'>{law}{art}</a></td>"
            f"<td>{pg}</td><td>{exact}</td>"
            f"<td class='ex'>{html.escape((r['text'] or '')[:90])}…</td></tr>")
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<title>عينات للتحقق — Adala</title><style>
 body{{font-family:'Segoe UI',Tahoma,sans-serif;margin:0;background:#f4f2ec;color:#1a1a18}}
 header{{background:#fff;border-bottom:1px solid #ddd;padding:12px 20px}}
 h1{{font-size:16px;margin:0}} .meta{{color:#666;font-size:13px;margin-top:4px}}
 table{{width:calc(100% - 28px);margin:14px;border-collapse:collapse;background:#fff;
       border:1px solid #ddd;border-radius:8px;overflow:hidden}}
 th,td{{padding:8px 12px;border-bottom:1px solid #eee;font-size:13px;text-align:right}}
 th{{background:#faf8f2;color:#666;font-weight:600}}
 a{{color:#1d5fa5;text-decoration:none}} a:hover{{text-decoration:underline}}
 .ex{{color:#888;font-size:12px}}
</style></head><body>
<header><h1>🔎 عينات عشوائية للتحقق من جودة الاستخراج</h1>
<div class="meta">{len(picks)} مقطعاً من أصل {len(recs)} — انقر على أي نص لفتح المقارنة مع الصفحة الأصلية
 — <a href="?n={n}">🔄 عينة جديدة</a></div></header>
<table><tr><th>النص القانوني</th><th>الصفحة</th><th>الدقة</th><th>مقتطف</th></tr>
{''.join(rows)}</table></body></html>"""


def _highlight_rects(pg, chunk_text: str) -> list:
    """Rectangles du texte du chunk retrouvé sur la page (recherche par segments)."""
    rects = []
    for line in (chunk_text or "").splitlines():
        seg = " ".join(line.split()).strip()
        if len(seg) < 12:
            continue
        # segments moyens : assez longs pour être uniques, assez courts pour
        # survivre aux différences OCR/couche texte
        for piece in (seg[i:i + 40] for i in range(0, len(seg), 40)):
            if len(piece) >= 12:
                try:
                    rects += pg.search_for(piece)
                except Exception:
                    pass
    return rects


def _strip_watermark_png(pix) -> bytes:
    """Supprime le filigrane coloré du portail (texte du document = noir/gris,
    filigrane = coloré -> pixels saturés remplacés par du blanc). Rendu seul,
    les PDF originaux ne sont jamais modifiés."""
    import numpy as np
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    rgb = arr[:, :, :3].astype(np.int16)
    saturation = rgb.max(axis=2) - rgb.min(axis=2)
    luminance = rgb.mean(axis=2)
    out = arr.copy()
    # filigrane = pixels colorés OU gris clair ; texte = sombre et neutre
    out[(saturation > 12) | (luminance > 145)] = 255
    clean = fitz.Pixmap(fitz.csRGB, pix.width, pix.height, out[:, :, :3].tobytes(), False)
    return clean.tobytes("png")


@router.get("/chunk-info")
def chunk_info(file: str = Query(...), chunk: str = Query("-")):
    """Métadonnées d'un chunk pour les clients natifs (mobile) :
    page résolue, nombre de pages, statut de version."""
    path = _resolve_pdf(file)
    doc = fitz.open(path)
    npages = len(doc)
    doc.close()
    rec = _chunk_index().get((os.path.basename(file), str(chunk)))
    return {
        "page": (rec or {}).get("page") or 1,
        "npages": npages,
        "law": (rec or {}).get("law", ""),
        "status": (rec or {}).get("status", "current"),
        "amended_by": (rec or {}).get("amended_by", []),
        "page_exact": bool(rec and rec.get("page_src") == "match"),
    }


@router.get("/page-image")
def page_image(file: str = Query(...), page: int = Query(1, ge=1),
               chunk: str | None = Query(None), clean: int = Query(0)):
    path = _resolve_pdf(file)
    doc = fitz.open(path)
    try:
        if page > len(doc):
            raise HTTPException(404, f"Page {page} > {len(doc)} pages.")
        pg = doc[page - 1]
        rects = []
        if chunk is not None:
            rec = _chunk_index().get((os.path.basename(file), str(chunk)))
            if rec:
                rects = _highlight_rects(pg, rec.get("text", ""))
        if not clean:
            for r in rects:
                pg.draw_rect(r, fill=(1, 0.9, 0.2), fill_opacity=0.35, width=0)
        pix = pg.get_pixmap(dpi=130)
        if clean:
            # filtre couleur d'abord (le surlignage jaune y survivrait mal),
            # puis surlignage re-dessiné sur l'image nettoyée
            png = _strip_watermark_png(pix)
            if rects:
                import numpy as np
                pix2 = fitz.Pixmap(png)
                arr = np.frombuffer(pix2.samples, dtype=np.uint8).reshape(pix2.height, pix2.width, pix2.n).copy()
                scale = 130 / 72
                for r in rects:
                    x0, y0 = int(r.x0 * scale), int(r.y0 * scale)
                    x1, y1 = int(r.x1 * scale), int(r.y1 * scale)
                    zone = arr[max(0, y0):y1, max(0, x0):x1, :3].astype(np.uint16)
                    arr[max(0, y0):y1, max(0, x0):x1, :3] = (
                        (zone * [1.0, 0.93, 0.45]).clip(0, 255).astype(np.uint8))
                png = fitz.Pixmap(fitz.csRGB, pix2.width, pix2.height,
                                  arr[:, :, :3].tobytes(), False).tobytes("png")
        else:
            png = pix.tobytes("png")
    finally:
        doc.close()
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("", response_class=HTMLResponse)
def viewer(file: str = Query(...), chunk: str = Query("-"),
           page: int | None = Query(None, ge=1), clean: int = Query(0)):
    path = _resolve_pdf(file)
    doc = fitz.open(path)
    npages = len(doc)
    doc.close()

    rec = _chunk_index().get((os.path.basename(file), str(chunk)))
    text = rec["text"] if rec else \
        "(وثيقة للاطلاع فقط — غير مفهرسة في مدونة الإجابات؛ تصفح الصفحات بالأزرار)"
    law = rec.get("law", "") if rec else ""
    article = rec.get("article") if rec else None
    cur = page or (rec.get("page") if rec else None) or 1
    cur = max(1, min(cur, npages))
    est = bool(rec) and rec.get("page_src") != "match"

    fq = html.escape(os.path.basename(file))
    art = f" — المادة/الفصل {html.escape(str(article))}" if article and str(article) != "None" else ""
    warn = ("<p class='warn'>⚠ رقم الصفحة تقديري — استعمل أزرار التنقل للتحقق</p>"
            if est else "")
    status = rec.get("status", "current") if rec else "current"
    if status == "consolidated":
        refs = "، ".join(rec.get("amended_by", []))
        links = " · ".join(_doc_link(d["file"], f"📖 عرض النص المعدِّل رقم {d['num']}")
                           for d in rec.get("amended_by_docs", []))
        warn += (f"<p class='badge ok'>📌 نص محيَّن — عُدِّل بمقتضى رقم {html.escape(refs)}"
                 + (f" — {links}" if links else "") + "</p>")
    elif status == "check_amendments":
        refs = "، ".join(rec.get("pending_amendments", []))
        warn += f"<p class='badge warn2'>⚠ يوجد نص لاحق رقم {html.escape(refs)} يعدّل هذا القانون</p>"
    elif status == "possibly_abrogated":
        links = " · ".join(_doc_link(d["file"], "📖 عرض النص الناسخ")
                           for d in rec.get("abrogated_by_docs", []))
        warn += ("<p class='badge danger'>🛑 ورد ما يفيد نسخ/إلغاء هذا النص — تحقق من النص الناسخ"
                 + (f" — {links}" if links else "") + "</p>")
    nav = "".join(
        f"<a class='btn' href='?file={fq}&chunk={html.escape(str(chunk))}&page={p}&clean={clean}'>{lbl}</a>"
        for p, lbl in [(max(1, cur - 1), "▶ الصفحة السابقة"), (min(npages, cur + 1), "الصفحة التالية ◀")]
    )
    nav += (f"<a class='btn' href='?file={fq}&chunk={html.escape(str(chunk))}&page={cur}&clean={0 if clean else 1}'>"
            f"{'🖼 عرض الأصل' if clean else '🧹 إخفاء العلامة المائية'}</a>")
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<title>التحقق من المصدر — {fq}</title><style>
 body{{font-family:'Segoe UI',Tahoma,sans-serif;margin:0;background:#f4f2ec;color:#1a1a18}}
 header{{background:#fff;border-bottom:1px solid #ddd;padding:12px 20px}}
 h1{{font-size:16px;margin:0}} .meta{{color:#666;font-size:13px;margin-top:4px}}
 .cols{{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:14px;align-items:start}}
 .card{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px}}
 .card h2{{font-size:14px;color:#666;margin:0 0 8px}}
 img{{width:100%;border:1px solid #ccc;border-radius:4px}}
 .ocr{{line-height:2;font-size:15px;white-space:pre-wrap}}
 .btn{{display:inline-block;background:#fff;border:1px solid #bbb;border-radius:6px;
      padding:6px 14px;margin:0 4px;text-decoration:none;color:#1a1a18;font-size:13px}}
 .btn:hover{{background:#f0ede4}} .nav{{text-align:center;margin-top:8px}}
 .pageno{{color:#666;font-size:13px}} .warn{{color:#a05a00;font-size:13px}}
 .badge{{display:inline-block;font-size:13px;border-radius:6px;padding:4px 10px;margin:4px 0}}
 .badge.ok{{background:#e7f3e7;color:#1d5c1d;border:1px solid #bcd8bc}}
 .badge.warn2{{background:#fdf3e0;color:#8a5a00;border:1px solid #e8cf9e}}
 .badge.danger{{background:#fdeaea;color:#8f1d1d;border:1px solid #e8b6b6}}
 @media(max-width:900px){{.cols{{grid-template-columns:1fr}}}}
</style></head><body>
<header><h1>{html.escape(law) or fq}{art}</h1>
<div class="meta">{fq} — الصفحة {cur} من {npages} {warn}</div></header>
<div class="cols">
 <div class="card"><h2>📄 صورة الصفحة الأصلية</h2>
  <img src="/api/viewer/page-image?file={fq}&page={cur}&chunk={html.escape(str(chunk))}&clean={clean}&v={RENDER_VERSION}" alt="page {cur}">
  <div class="nav">{nav}<div class="pageno">صفحة {cur}/{npages}</div></div></div>
 <div class="card"><h2>🔤 النص المستخرج المعتمد في الجواب (OCR)</h2>
  <div class="ocr">{html.escape(text)}</div></div>
</div></body></html>"""
