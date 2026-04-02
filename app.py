"""
╔══════════════════════════════════════════════════════════════╗
║  DMSI · Adala — Interface Streamlit (Frontend)               ║
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

from core.config import API_BASE_URL, LOGO_PATH
from search.engine import highlight_matches

# ── Configuration ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Adala - البوابة القانونية لوزارة العدل",
    layout="wide",
    page_icon="⚖️",
    initial_sidebar_state="expanded",
)

# ── Client API ────────────────────────────────────────────────────────────
def api(method: str, path: str, **kwargs):
    url = f"{API_BASE_URL}{path}"
    try:
        r = getattr(requests, method)(url, timeout=120, **kwargs)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Backend non disponible. Lancez : `uvicorn api.main:app --reload`")
        return None
    except Exception as e:
        st.error(f"❌ Erreur API : {e}")
        return None

# ── Logo ──────────────────────────────────────────────────────────────────
def _logo_tag() -> str:
    for p in [LOGO_PATH, LOGO_PATH.parent.parent / "zz.png"]:
        if p.exists():
            b64 = base64.b64encode(p.read_bytes()).decode()
            return f'<img src="data:image/png;base64,{b64}" style="max-height:80px;margin:0 auto 10px;position:relative;z-index:1;">'
    return ""

# ── Session state ─────────────────────────────────────────────────────────
if "sq"    not in st.session_state: st.session_state.sq    = ""
if "docs"  not in st.session_state: st.session_state.docs  = None
if "stats" not in st.session_state: st.session_state.stats = None

# ── CSS ───────────────────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap');

*, *::before, *::after { font-family: 'Tajawal', sans-serif !important; }
html, body, [data-testid="stAppViewContainer"],
[data-testid="stMain"], .main, .block-container,
[data-testid="stVerticalBlock"], [data-testid="stHorizontalBlock"],
section.main > div { background-color: #f8f9fa !important; color: #1f2937 !important; }

p, span, div, label, li, td, th, h1, h2, h3, h4, h5,
.stMarkdown, .stText, .stCaption,
[data-testid="stMarkdownContainer"] { color: #1f2937 !important; }

[data-testid="stMetricValue"], [data-testid="stMetricLabel"] { color: #1f2937 !important; }

#MainMenu, footer, header, [data-testid="stToolbar"] { display: none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }

[data-testid="stSidebar"] { background: #0b192c !important; }
[data-testid="stSidebar"] * { color: #d1d5db !important; }
[data-testid="stSidebar"] [data-testid="stMetricValue"],
[data-testid="stSidebar"] [data-testid="stMetricLabel"] { color: #ffffff !important; }

.search-wrap { background:#d1ab66; border-radius:12px; padding:24px 32px 28px; max-width:900px; margin:-20px auto 24px; box-shadow:0 4px 6px rgba(0,0,0,.1); position:relative; z-index:20; }
.search-tabs { display:flex; justify-content:center; gap:24px; margin-bottom:16px; font-weight:700; font-size:.95rem; color:#0b192c !important; }
.search-tabs span { padding:8px 12px; cursor:pointer; color:#0b192c !important; }
.search-tabs span.act { background:#0b192c; color:#fff !important; padding:6px 24px; border-radius:9999px; }
.search-wrap [data-testid="stTextInput"] input { border-radius:9999px !important; padding:18px 60px 18px 24px !important; border:none !important; font-size:1.05rem !important; background:#fff !important; color:#1f2937 !important; box-shadow:inset 0 2px 4px rgba(0,0,0,.06) !important; direction:rtl !important; text-align:right !important; height:58px !important; }
.search-wrap [data-testid="stTextInput"] input::placeholder { color:#9ca3af !important; }
.search-wrap [data-testid="stTextInput"] label { display:none !important; }
.search-wrap [data-testid="stHorizontalBlock"] { position:relative !important; }
.search-wrap [data-testid="stHorizontalBlock"]>div:last-child { position:absolute !important; top:50% !important; right:8px !important; transform:translateY(-50%) !important; z-index:5 !important; width:auto !important; flex:none !important; }
.search-wrap [data-testid="stHorizontalBlock"]>div:first-child { width:100% !important; flex:1 !important; max-width:100% !important; }
.search-wrap [data-testid="stButton"] button { background:#d4b264 !important; border:none !important; border-radius:50% !important; width:46px !important; height:46px !important; min-width:46px !important; padding:0 !important; color:#fff !important; font-size:1.3rem !important; }
.search-wrap [data-testid="stButton"] button p { margin:0 !important; line-height:1 !important; color:#fff !important; }

.dym { background:#fffbeb; border:2px solid #d1ab66; border-radius:12px; padding:16px 24px; direction:rtl; text-align:right; margin:16px auto; max-width:900px; }
.dym .lb { color:#92400e !important; font-size:.95rem; }
.dym .cr { color:#0b192c !important; font-weight:800; font-size:1.15rem; text-decoration:underline; }
.rh { direction:rtl; text-align:right; padding:20px 0 8px; max-width:900px; margin:0 auto; }
.rh h2 { color:#0b192c !important; font-size:1.4rem; margin:0 0 4px; font-weight:700; }
.rh .rq { color:#d1ab66 !important; font-weight:800; }
.rh .rm { color:#888 !important; font-size:.82rem; }
.rcard { background:#fff; border-radius:12px; padding:20px 24px; margin:12px auto; max-width:900px; border-right:6px solid #0b192c; box-shadow:0 1px 8px rgba(0,0,0,.05); direction:rtl; text-align:right; transition:.2s; }
.rcard:hover { box-shadow:0 4px 16px rgba(0,0,0,.1); transform:translateX(-3px); }
.rcard .rfn { color:#0b192c !important; font-size:1.05rem; font-weight:700; margin-bottom:6px; }
.rcard .rmt { color:#6b7280 !important; font-size:.78rem; margin-bottom:12px; }
.rcard .mline { background:#f8f9fa; border-radius:8px; padding:12px 16px; margin:6px 0; border-right:4px solid #d1ab66; direction:rtl; }
.rcard .mpn { color:#d1ab66 !important; font-weight:700; font-size:.82rem; margin-bottom:4px; }
.rcard .mtxt { color:#1f2937 !important; font-size:.88rem; line-height:1.9; }
.sgc { direction:rtl; text-align:right; margin:10px auto; max-width:900px; }
.sg2 { display:inline-block; background:#fff; color:#0b192c !important; padding:6px 18px; border-radius:20px; margin:4px; font-size:.85rem; border:1px solid #e0e0e0; }
.sh2 { font-size:1.5rem; font-weight:700; color:#0b192c !important; text-align:right; max-width:1200px; margin:30px auto 16px; padding:0 20px; direction:rtl; }
.dcard2 { background:#0b192c; border-radius:12px; padding:20px; text-align:center; color:#fff !important; display:flex; flex-direction:column; align-items:center; min-height:240px; box-shadow:0 2px 8px rgba(0,0,0,.1); transition:.3s; }
.dcard2 * { color:#fff !important; }
.dcard2:hover { transform:translateY(-4px); box-shadow:0 8px 20px rgba(11,25,44,.3); }
.dcard2 .bdg { background:#d1ab66; color:#0b192c !important; font-size:.75rem; font-weight:700; padding:4px 14px; border-radius:20px; margin-bottom:12px; }
.dcard2 h3 { font-size:.85rem; font-weight:700; margin-bottom:8px; line-height:1.7; direction:rtl; color:#fff !important; }
.dcard2 p { font-size:.75rem; color:#9ca3af !important; line-height:1.6; margin-bottom:12px; direction:rtl; }
.aicard2 { background:#0b192c; border-radius:12px; padding:30px 20px; text-align:center; color:#fff !important; display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:100%; }
.aicard2 * { color:#fff !important; }
.aicard2 h3 { font-size:1.2rem; font-weight:700; margin:16px 0 8px; direction:rtl; }
.aicard2 p { font-size:.9rem; color:#9ca3af !important; line-height:1.7; margin-bottom:20px; direction:rtl; }
.pb2 { background:#fff; border-radius:12px; margin-bottom:14px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.06); border:1px solid #e5e7eb; }
.phn2 { background:linear-gradient(90deg,#047857,#059669); color:#fff !important; padding:10px 16px; font-size:.85rem; font-weight:600; direction:rtl; text-align:right; }
.phso2 { background:linear-gradient(90deg,#ea580c,#f59e0b); color:#fff !important; padding:10px 16px; font-size:.85rem; font-weight:600; direction:rtl; text-align:right; }
.pbb2 { padding:16px; background:#fff; }
.ra2 { direction:rtl; text-align:right; font-size:.9rem; line-height:1.85; white-space:pre-wrap; color:#1f2937 !important; }
.es2 { text-align:center; padding:50px 20px; color:#6b7280 !important; direction:rtl; }
.es2 h3 { color:#0b192c !important; font-size:1.2rem; }
.stTabs [data-baseweb="tab-list"] { gap:0; background:#fff; border-radius:10px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.06); border:1px solid #e5e7eb; }
.stTabs [data-baseweb="tab"] { font-weight:600 !important; color:#0b192c !important; padding:12px 20px !important; font-size:0.9rem !important; }
.stTabs [data-baseweb="tab"][aria-selected="true"] { background:#0b192c !important; color:#fff !important; border-bottom:3px solid #d1ab66 !important; }
.stTabs [data-baseweb="tab"][aria-selected="true"] * { color:#fff !important; }
[data-testid="stDownloadButton"] button { border-radius:8px !important; background:#d1ab66 !important; color:#0b192c !important; font-weight:700 !important; border:none !important; }
[data-testid="stDownloadButton"] button * { color:#0b192c !important; }
[data-testid="stExpander"] { background:#fff !important; border:1px solid #e5e7eb !important; border-radius:8px !important; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary * { color:#0b192c !important; font-weight:600 !important; }
.stAlert p { color:#1f2937 !important; }
</style>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
#  1. HEADER & HERO  — 100 % statique, zéro appel réseau
# ══════════════════════════════════════════════════════════════════════════
TICKER_DEFAULT = "آخر التحديثات: صدر اليوم الظهير الشريف رقم 1.23.45 بتنفيذ قانون المالية لسنة 2024..."

components.html(f"""
<script src="https://cdn.tailwindcss.com?plugins=forms"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap');
body{{font-family:'Tajawal',sans-serif;margin:0;background:#f8f9fa;overflow:hidden;}}
</style>
<div dir="rtl" lang="ar">
  <div class="bg-[#d4b264] text-black py-2 text-center text-sm font-bold">{TICKER_DEFAULT}</div>
  <header class="bg-[#0b192c] text-white py-4 px-8 border-b border-gray-700">
    <div class="container mx-auto flex justify-between items-center max-w-7xl">
      <nav class="flex gap-6 text-sm font-medium">
        <a class="text-[#d1ab66] border-b-2 border-[#d1ab66] pb-1" href="#">الرئيسية</a>
      </nav>
      <svg class="h-12 w-12 text-[#d4b264]" fill="currentColor" viewBox="0 0 24 24">
        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
      </svg>
    </div>
  </header>
  <section style="background:linear-gradient(180deg,#0b192c 0%,#112a46 100%)" class="text-white relative py-16 overflow-hidden">
    <div class="container mx-auto max-w-4xl text-center relative z-10 px-4">
      {_logo_tag()}
      <div class="flex justify-center items-center gap-3 mb-4">
        <svg class="w-6 h-6 text-[#d1ab66]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3"
            stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
        </svg>
        <span class="text-2xl font-bold tracking-wider">Adala</span>
      </div>
      <h1 class="text-4xl md:text-5xl font-bold text-[#d1ab66] mb-4 leading-tight">
        البوابة القانونية لوزارة العدل
      </h1>
      <p class="text-lg md:text-xl text-gray-300">
        بوابتك الشاملة للتشريعات، الاجتهادات القضائية، وتحليل الوثائق القانونية باستخدام الذكاء الاصطناعي.
      </p>
    </div>
  </section>
</div>
""", height=440, scrolling=False)

# ══════════════════════════════════════════════════════════════════════════
#  2. BARRE DE RECHERCHE — statique
# ══════════════════════════════════════════════════════════════════════════
st.markdown("""<div class="search-wrap">
<div class="search-tabs">
  <span>بحث متقدم</span><span>بحث بالمادة</span><span class="act">بحث سريع</span>
</div>""", unsafe_allow_html=True)

sc1, sc2 = st.columns([20, 1])
with sc1:
    q = st.text_input(
        "s", value=st.session_state.sq,
        placeholder="ادخل كلمات مفتاحية، رقم القانون، أو تاريخ الإصدار...",
        label_visibility="collapsed", key="qi",
    )
with sc2:
    search_clicked = st.button("🔍", key="sb")

st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
#  3. RÉSULTATS — appel API uniquement si l'utilisateur cherche
# ══════════════════════════════════════════════════════════════════════════
if search_clicked and q:
    st.session_state.sq = q
    res = api("get", "/api/search", params={"q": q})
    if res:
        if res.get("correction"):
            st.markdown(
                f'<div class="dym"><span class="lb">🔤 هل تقصد: </span>'
                f'<span class="cr">"{res["correction"]}"</span>'
                f'<span class="lb"> بدلاً من "{res["query_orig"]}"؟</span></div>',
                unsafe_allow_html=True,
            )
            if st.button(f'🔍 البحث عن "{res["correction"]}"', key="cr"):
                st.session_state.sq = res["correction"]
                st.rerun()

        ef = res.get("query_eff", q)
        st.markdown(
            f'<div class="rh"><h2>نتائج البحث عن: <span class="rq">"{ef}"</span></h2>'
            f'<div class="rm">⏱️ {res.get("elapsed_ms", 0):.1f}ms — {res["total"]} وثيقة</div></div>',
            unsafe_allow_html=True,
        )

        if res.get("suggestions"):
            chips = "".join(f'<span class="sg2">{s}</span>' for s in res["suggestions"])
            st.markdown(f'<div class="sgc"><span style="color:#888;font-size:.82rem;">💡 ذات صلة: </span>{chips}</div>', unsafe_allow_html=True)
            cols = st.columns(min(len(res["suggestions"]), 6))
            for i, s in enumerate(res["suggestions"][:6]):
                if cols[i].button(s, key=f"sg_{i}"):
                    st.session_state.sq = s
                    st.rerun()

        if res["results"]:
            for r in res["results"]:
                st.markdown(
                    f'<div class="rcard"><div class="rfn">📄 {r["filename"]}</div>'
                    f'<div class="rmt">📃 {r["nb_pages"]} صفحة | {len(r["matches"])} سطر مطابق</div>',
                    unsafe_allow_html=True,
                )
                for m in r["matches"][:6]:
                    st.markdown(
                        f'<div class="mline"><div class="mpn">📃 صفحة {m["page"]}</div>'
                        f'<div class="mtxt">{highlight_matches(m["line"], ef)}</div></div>',
                        unsafe_allow_html=True,
                    )
                st.markdown("</div>", unsafe_allow_html=True)
                try:
                    pdf_bytes = requests.get(f"{API_BASE_URL}/api/pdf/{r['filename']}", timeout=30).content
                    st.download_button(f"⬇️ تحميل {r['filename']}", data=pdf_bytes,
                                       file_name=r["filename"], mime="application/pdf",
                                       key=f"dl_{r['doc_id']}")
                except Exception:
                    pass
        elif not res.get("correction"):
            st.markdown('<div class="es2"><h3>🔍 لم يتم العثور على نتائج</h3></div>', unsafe_allow_html=True)

elif q and not search_clicked and len(q) >= 2:
    res = api("get", "/api/search", params={"q": q})
    if res and res.get("suggestions"):
        cols = st.columns(min(len(res["suggestions"]), 6))
        for i, s in enumerate(res["suggestions"][:6]):
            if cols[i].button(f"💡 {s}", key=f"ls_{i}"):
                st.session_state.sq = s
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════
#  4. ONGLETS — appels API uniquement à l'intérieur de chaque onglet
# ══════════════════════════════════════════════════════════════════════════
st.markdown('<div class="sh2">آخر الوثائق القانونية</div>', unsafe_allow_html=True)
tab1, tab2 = st.tabs(["📚 المستجدات", "📤 رفع واستخراج"])

with tab1:
    # Chargement paresseux : une seule fois par session, mis à jour après upload/suppression
    if st.session_state.docs is None:
        st.session_state.docs = api("get", "/api/documents") or []

    docs = st.session_state.docs

    if docs:
        left, right = st.columns([2, 1], gap="medium")
        with left:
            cc = st.columns(2)
            for i, doc in enumerate(docs):
                badge = (
                    "ظهير شريف"    if "ظهير"  in doc["filename"].lower() else
                    "مرسوم بقانون" if "مرسوم" in doc["filename"].lower() else
                    "قرار وزاري"   if "قرار"  in doc["filename"].lower() else
                    "وثيقة"
                )
                with cc[i % 2]:
                    st.markdown(
                        f'<div class="dcard2"><span class="bdg">{badge}</span>'
                        f'<h3>{doc["filename"]}</h3>'
                        f'<p>{doc["nb_pages"]} صفحة — {doc.get("indexed","")[:10]}</p></div>',
                        unsafe_allow_html=True,
                    )
                    try:
                        pdf_bytes = requests.get(f"{API_BASE_URL}/api/pdf/{doc['filename']}", timeout=30).content
                        st.download_button("اقرأ المزيد", data=pdf_bytes,
                                           file_name=doc["filename"], mime="application/pdf",
                                           key=f"md_{doc['doc_id']}", use_container_width=True)
                    except Exception:
                        pass
                    if st.button("🗑️ حذف", key=f"del_{doc['doc_id']}"):
                        api("delete", f"/api/documents/{doc['doc_id']}")
                        st.session_state.docs  = None  # invalide le cache local
                        st.session_state.stats = None
                        st.rerun()
        with right:
            st.markdown("""<div class="aicard2">
                <svg style="width:100px;height:100px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                          stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"/>
                </svg>
                <h3>منصة استخراج وبحث ذكي</h3>
                <p>ارفع وثائقك القانونية وابحث فيها بكلمات مفتاحية مع تصحيح تلقائي واقتراحات ذكية.</p>
            </div>""", unsafe_allow_html=True)
    else:
        st.markdown('<div class="es2"><h3>📚 لا توجد وثائق — ارفع في "رفع واستخراج"</h3></div>', unsafe_allow_html=True)

with tab2:
    st.markdown('<div style="direction:rtl;text-align:right;"><h3 style="color:#0b192c;">📤 رفع واستخراج</h3></div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("PDF", type="pdf", key="up", label_visibility="collapsed")

    if uploaded:
        with st.spinner("⏳ جاري الاستخراج والفهرسة…"):
            result = api("post", "/api/upload",
                         files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")})

        if result:
            nb  = result["nb_pages"]
            src = "⚡ من الذاكرة" if result.get("from_cache") else "✅ مستخرج"
            st.success(f"{src} — {uploaded.name} ({nb} صفحة · {result['n_native']} أصلية · {result['n_scan']} مسح ضوئي)")

            # Invalide le cache local pour forcer le rechargement dans tab1
            st.session_state.docs  = None
            st.session_state.stats = None

            pages = result.get("pages", [])
            col_txt, col_prev = st.columns([1.6, 1], gap="large")

            with col_prev:
                for p in pages:
                    icon = "🟢" if p["type"] == "native" else "🟠"
                    with st.expander(f"{icon} ص{p['num']}", expanded=(p["num"] == 1)):
                        preview_b64 = p.get("preview_b64", "")
                        if preview_b64:
                            st.image(base64.b64decode(preview_b64), use_container_width=True)
                        else:
                            st.caption("⚠️ Aperçu non disponible")

            with col_txt:
                for p in pages:
                    hc = "phn2" if p["type"] == "native" else "phso2"
                    lb = "🟢 أصلي" if p["type"] == "native" else "🟠 OCR"
                    st.markdown(f'<div class="pb2"><div class="{hc}">ص{p["num"]}/{nb} · {lb}</div><div class="pbb2">', unsafe_allow_html=True)
                    text = p.get("text", "").strip()
                    if text:
                        st.markdown(f'<div class="ra2">{text.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="ra2" style="color:#9ca3af!important;">— صفحة فارغة —</div>', unsafe_allow_html=True)
                    st.markdown('</div></div>', unsafe_allow_html=True)

                all_text = "\n\n".join(f"=== صفحة {p['num']} ===\n{p.get('text','')}" for p in pages)
                st.download_button("💾 تحميل النص", data=all_text,
                                   file_name=f"Brut_{uploaded.name}.txt", mime="text/plain")

# ══════════════════════════════════════════════════════════════════════════
#  5. FOOTER — statique
# ══════════════════════════════════════════════════════════════════════════
components.html("""
<script src="https://cdn.tailwindcss.com"></script>
<style>body{font-family:'Tajawal',sans-serif;margin:0;background:#f8f9fa;}</style>
<footer class="bg-[#0b192c] text-white py-8 border-t border-gray-700" dir="rtl">
  <div class="container mx-auto max-w-7xl px-4 flex flex-col md:flex-row justify-between items-center gap-4 text-sm">
    <div class="flex gap-4">
      <a class="hover:text-[#d1ab66] transition cursor-pointer">خريطة الموقع</a>
      <a class="hover:text-[#d1ab66] transition cursor-pointer">سياسة الخصوصية</a>
      <a class="hover:text-[#d1ab66] transition cursor-pointer">شروط الاستخدام</a>
    </div>
    <div class="text-gray-400">© 2025 وزارة العدل - المملكة المغربية</div>
  </div>
</footer>
""", height=100, scrolling=False)