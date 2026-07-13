"""
╔══════════════════════════════════════════════════════════════╗
║  المساعد القانوني الذكي — Interface Streamlit (Frontend)      ║
║  app.py                                                      ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import base64
import requests
import streamlit as st
import streamlit.components.v1 as components

from core.config import API_BASE_URL
from search.engine import highlight_matches

# ── Configuration ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="المساعد القانوني الذكي",
    layout="wide",
    page_icon="⚖️",
    initial_sidebar_state="collapsed",
)

# ── Client API ────────────────────────────────────────────────────────────
def api(method: str, path: str, **kwargs):
    url = f"{API_BASE_URL}{path}"
    try:
        r = getattr(requests, method)(url, timeout=180, **kwargs)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ الخدمة الخلفية غير متاحة. شغّل: `uvicorn api.main:app`")
        return None
    except Exception as e:
        st.error(f"❌ خطأ في الاتصال: {e}")
        return None

# ── Session state ─────────────────────────────────────────────────────────
st.session_state.setdefault("sq", "")
st.session_state.setdefault("docs", None)
st.session_state.setdefault("stats", None)

# ── CSS ───────────────────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap');

*, *::before, *::after { font-family: 'Tajawal', sans-serif !important; }
html, body, [data-testid="stAppViewContainer"],
[data-testid="stMain"], .main, .block-container,
[data-testid="stVerticalBlock"], [data-testid="stHorizontalBlock"],
section.main > div { background-color: #f6f7f9 !important; color: #1f2937 !important; }

p, span, div, label, li, td, th, h1, h2, h3, h4, h5,
.stMarkdown, .stText, .stCaption,
[data-testid="stMarkdownContainer"] { color: #1f2937 !important; }

#MainMenu, footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ── Layout helpers ── */
.wrap { max-width: 1120px; margin: 0 auto; padding: 0 20px; }

/* ── Stats ── */
.statbar { max-width:1120px; margin:-14px auto 6px; padding:0 20px; display:flex; gap:16px; justify-content:center; direction:rtl; flex-wrap:wrap; position:relative; z-index:20; }
.statcard { flex:1; min-width:150px; background:#fff; border:1px solid #e8eaed; border-radius:16px; padding:16px 20px; text-align:center; box-shadow:0 4px 14px rgba(11,25,44,.06); }
.statnum { color:#0b192c !important; font-size:2.1rem; font-weight:800; line-height:1; }
.statlbl { color:#6b7280 !important; font-size:.85rem; margin-top:6px; }

/* ── Tabs ── */
.stTabs { max-width:1120px !important; margin:22px auto 0 !important; padding:0 20px; }
.stTabs [data-baseweb="tab-list"] { gap:0; background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.05); border:1px solid #e8eaed; padding:5px; }
.stTabs [data-baseweb="tab"] { font-weight:700 !important; color:#0b192c !important; padding:12px 22px !important; font-size:.95rem !important; border-radius:9px !important; }
.stTabs [data-baseweb="tab"][aria-selected="true"] { background:#0b192c !important; color:#fff !important; }
.stTabs [data-baseweb="tab"][aria-selected="true"] * { color:#fff !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display:none !important; }

.sect-intro { direction:rtl; text-align:right; color:#4b5563 !important; font-size:.92rem; margin:14px 0; }

/* ── Search results ── */
.rcard { background:#fff; border-radius:14px; padding:18px 22px; margin:12px 0; border-right:5px solid #0b192c; box-shadow:0 2px 10px rgba(0,0,0,.05); direction:rtl; text-align:right; }
.rcard .rfn { color:#0b192c !important; font-size:1.05rem; font-weight:700; margin-bottom:4px; }
.rcard .rmt { color:#6b7280 !important; font-size:.78rem; margin-bottom:12px; }
.mline { background:#f6f7f9; border-radius:8px; padding:10px 14px; margin:6px 0; border-right:4px solid #d1ab66; direction:rtl; }
.mpn { color:#b8892f !important; font-weight:700; font-size:.8rem; margin-bottom:4px; }
.mtxt { color:#1f2937 !important; font-size:.9rem; line-height:1.9; }

/* ── Extraction results ── */
.pb2 { background:#fff; border-radius:12px; margin-bottom:14px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.06); border:1px solid #e8eaed; }
.phn2 { background:linear-gradient(90deg,#047857,#059669); color:#fff !important; padding:9px 16px; font-size:.82rem; font-weight:700; direction:rtl; text-align:right; }
.phso2 { background:linear-gradient(90deg,#ea580c,#f59e0b); color:#fff !important; padding:9px 16px; font-size:.82rem; font-weight:700; direction:rtl; text-align:right; }
.pbb2 { padding:16px; background:#fff; }
.ra2 { direction:rtl; text-align:right; font-size:.92rem; line-height:1.95; white-space:pre-wrap; color:#1f2937 !important; }
.colhd { direction:rtl; text-align:right; font-weight:700; color:#0b192c !important; margin:4px 0 10px; font-size:1rem; }

/* ── Document library ── */
.doc-card { background:#fff; border:1px solid #e8eaed; border-radius:16px; padding:18px; box-shadow:0 2px 10px rgba(0,0,0,.05); direction:rtl; text-align:right; transition:.2s; margin-bottom:8px; }
.doc-card:hover { box-shadow:0 8px 22px rgba(11,25,44,.1); transform:translateY(-3px); }
.doc-ic { width:42px; height:42px; border-radius:10px; background:#eef2f7; display:flex; align-items:center; justify-content:center; font-size:1.3rem; margin-bottom:10px; }
.doc-t { color:#0b192c !important; font-weight:700; font-size:1rem; margin-bottom:4px; word-break:break-word; line-height:1.5; }
.doc-m { color:#6b7280 !important; font-size:.8rem; margin-bottom:12px; }

/* ── Empty states ── */
.es { text-align:center; padding:56px 20px; direction:rtl; }
.es h3 { color:#0b192c !important; font-size:1.25rem; margin-bottom:6px; }
.es p { color:#6b7280 !important; font-size:.92rem; }

/* ── Buttons / inputs ── */
[data-testid="stDownloadButton"] button { border-radius:9px !important; background:#0b192c !important; color:#fff !important; font-weight:700 !important; border:none !important; }
[data-testid="stDownloadButton"] button * { color:#fff !important; }
[data-testid="stFileUploader"] { direction:rtl; }
[data-testid="stExpander"] { background:#fff !important; border:1px solid #e8eaed !important; border-radius:10px !important; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary * { color:#0b192c !important; font-weight:700 !important; }
[data-testid="stTextInput"] input { border-radius:10px !important; border:1px solid #dfe3e8 !important; direction:rtl !important; text-align:right !important; padding:12px 16px !important; }
.stAlert p { color:#1f2937 !important; }
</style>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
#  1. HEADER & HERO
# ══════════════════════════════════════════════════════════════════════════
components.html("""
<script src="https://cdn.tailwindcss.com"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap');
body{font-family:'Tajawal',sans-serif;margin:0;background:#f6f7f9;overflow:hidden;}
</style>
<div dir="rtl" lang="ar">
  <header class="bg-[#0b192c] text-white py-4 px-8">
    <div class="container mx-auto flex justify-between items-center max-w-6xl">
      <div class="flex items-center gap-3">
        <svg class="h-8 w-8 text-[#d1ab66]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3"
            stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
        </svg>
        <span class="text-lg font-bold tracking-wide text-[#d1ab66]">المساعد القانوني الذكي</span>
      </div>
    </div>
  </header>
  <section style="background:linear-gradient(180deg,#0b192c 0%,#112a46 100%)" class="text-white relative py-12">
    <div class="container mx-auto max-w-3xl text-center px-4">
      <h1 class="text-2xl md:text-4xl font-bold text-[#d1ab66] mb-3 leading-tight">
        تحليل الملفات القانونية بالذكاء الاصطناعي
      </h1>
      <p class="text-sm md:text-lg text-gray-300">
        ارفع ملفات القضايا لاستخراج نصوصها، البحث داخلها، واستخلاص المعلومات القانونية.
      </p>
    </div>
  </section>
</div>
""", height=300, scrolling=False)

# ══════════════════════════════════════════════════════════════════════════
#  2. STATS
# ══════════════════════════════════════════════════════════════════════════
if st.session_state.stats is None:
    st.session_state.stats = api("get", "/api/stats") or {}
_s = st.session_state.stats
st.markdown(f"""
<div class="statbar">
  <div class="statcard"><div class="statnum">{_s.get('docs', 0)}</div><div class="statlbl">وثيقة مُحلَّلة</div></div>
  <div class="statcard"><div class="statnum">{_s.get('pages', 0)}</div><div class="statlbl">صفحة مُستخرَجة</div></div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
#  3. WORKSPACE
# ══════════════════════════════════════════════════════════════════════════
tab_up, tab_lib = st.tabs(["📤  رفع وتحليل وثيقة", "📁  وثائقي"])

# ── Onglet 1 : Upload & extraction ─────────────────────────────────────────
with tab_up:
    st.markdown(
        '<div class="sect-intro">ارفع ملف PDF (أصلي أو ممسوح ضوئياً). سيُستخرج النص تلقائياً '
        'وتُعرض كل صفحة مع معاينتها.</div>',
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader("PDF", type="pdf", key="up", label_visibility="collapsed")

    if uploaded:
        with st.spinner("⏳ جاري الاستخراج…"):
            result = api("post", "/api/upload",
                         files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")})

        if result:
            nb  = result["nb_pages"]
            src = "⚡ من الذاكرة" if result.get("from_cache") else "✅ تم الاستخراج"
            st.success(f"{src} — {uploaded.name}  ·  {nb} صفحة "
                       f"({result['n_native']} أصلية · {result['n_scan']} OCR)")

            st.session_state.docs  = None
            st.session_state.stats = None

            pages = result.get("pages", [])
            col_txt, col_prev = st.columns([1.6, 1], gap="large")

            with col_txt:
                st.markdown('<div class="colhd">📝 النص المُستخرَج</div>', unsafe_allow_html=True)
                for p in pages:
                    hc = "phn2" if p["type"] == "native" else "phso2"
                    lb = "🟢 نص أصلي" if p["type"] == "native" else "🟠 OCR"
                    st.markdown(f'<div class="pb2"><div class="{hc}">صفحة {p["num"]}/{nb} · {lb}</div><div class="pbb2">', unsafe_allow_html=True)
                    text = (p.get("text") or "").strip()
                    if text:
                        st.markdown(f'<div class="ra2">{text.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="ra2" style="color:#9ca3af!important;">— صفحة فارغة —</div>', unsafe_allow_html=True)
                    st.markdown('</div></div>', unsafe_allow_html=True)

                all_text = "\n\n".join(f"=== صفحة {p['num']} ===\n{p.get('text','')}" for p in pages)
                st.download_button("💾 تحميل النص كاملاً", data=all_text,
                                   file_name=f"{uploaded.name}.txt", mime="text/plain",
                                   use_container_width=True)

            with col_prev:
                st.markdown('<div class="colhd">🖼️ معاينة الصفحات</div>', unsafe_allow_html=True)
                for p in pages:
                    icon = "🟢" if p["type"] == "native" else "🟠"
                    with st.expander(f"{icon} صفحة {p['num']}", expanded=(p["num"] == 1)):
                        pv = p.get("preview_b64", "")
                        if pv:
                            st.image(base64.b64decode(pv), use_container_width=True)
                        else:
                            st.caption("لا توجد معاينة")

# ── Onglet 2 : Bibliothèque + recherche ─────────────────────────────────────
with tab_lib:
    cs1, cs2 = st.columns([20, 3])
    with cs1:
        lq = st.text_input("s", value=st.session_state.sq,
                           placeholder="🔍 ابحث داخل وثائقك…",
                           label_visibility="collapsed", key="lqi")
    with cs2:
        lsearch = st.button("بحث", key="lsb", use_container_width=True)

    # — Résultats de recherche —
    if lsearch and lq:
        st.session_state.sq = lq
        res = api("get", "/api/search", params={"q": lq})
        if res:
            ef = res.get("query_eff", lq)
            if res.get("correction"):
                st.info(f'💡 هل تقصد: "{res["correction"]}"؟')
            st.markdown(
                f'<div class="sect-intro">نتائج البحث عن "<b>{ef}</b>" — '
                f'{res["total"]} وثيقة · {res.get("elapsed_ms", 0):.0f}ms</div>',
                unsafe_allow_html=True,
            )
            if res["results"]:
                for r in res["results"]:
                    st.markdown(
                        f'<div class="rcard"><div class="rfn">📄 {r["filename"]}</div>'
                        f'<div class="rmt">{r["nb_pages"]} صفحة · {len(r["matches"])} سطر مطابق</div>',
                        unsafe_allow_html=True,
                    )
                    for m in r["matches"][:6]:
                        st.markdown(
                            f'<div class="mline"><div class="mpn">صفحة {m["page"]}</div>'
                            f'<div class="mtxt">{highlight_matches(m["line"], ef)}</div></div>',
                            unsafe_allow_html=True,
                        )
                    st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="es"><h3>لا توجد نتائج</h3>'
                            '<p>جرّب كلمات مفتاحية أخرى.</p></div>', unsafe_allow_html=True)

    # — Bibliothèque —
    else:
        if st.session_state.docs is None:
            st.session_state.docs = api("get", "/api/documents") or []
        docs = st.session_state.docs

        if docs:
            st.markdown(f'<div class="sect-intro">{len(docs)} وثيقة في مكتبتك.</div>', unsafe_allow_html=True)
            cols = st.columns(3, gap="medium")
            for i, doc in enumerate(docs):
                with cols[i % 3]:
                    st.markdown(
                        f'<div class="doc-card"><div class="doc-ic">📄</div>'
                        f'<div class="doc-t">{doc["filename"]}</div>'
                        f'<div class="doc-m">{doc["nb_pages"]} صفحة · {doc.get("indexed","")[:10]}</div></div>',
                        unsafe_allow_html=True,
                    )
                    try:
                        pdf_bytes = requests.get(f"{API_BASE_URL}/api/pdf/{doc['filename']}", timeout=30).content
                        st.download_button("⬇️ تحميل", data=pdf_bytes, file_name=doc["filename"],
                                           mime="application/pdf", key=f"dl_{doc['doc_id']}",
                                           use_container_width=True)
                    except Exception:
                        pass
                    if st.button("🗑️ حذف", key=f"del_{doc['doc_id']}", use_container_width=True):
                        api("delete", f"/api/documents/{doc['doc_id']}")
                        st.session_state.docs  = None
                        st.session_state.stats = None
                        st.rerun()
        else:
            st.markdown('<div class="es"><h3>📁 لا توجد وثائق بعد</h3>'
                        '<p>ابدأ من تبويب «رفع وتحليل وثيقة».</p></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
#  4. FOOTER
# ══════════════════════════════════════════════════════════════════════════
components.html("""
<script src="https://cdn.tailwindcss.com"></script>
<style>body{font-family:'Tajawal',sans-serif;margin:0;background:#f6f7f9;}</style>
<footer class="bg-[#0b192c] text-white py-6" dir="rtl">
  <div class="container mx-auto max-w-6xl px-4 text-center text-sm text-gray-400">
    © 2026 المساعد القانوني الذكي — تحليل الوثائق القانونية بالذكاء الاصطناعي
  </div>
</footer>
""", height=80, scrolling=False)
