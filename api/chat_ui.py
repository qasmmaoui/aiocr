# -*- coding: utf-8 -*-
"""Page de chat RimLex (/chat) — front minimal autonome pour le pilote.

- Streaming NDJSON via /api/chat/stream (sources d'abord, puis deltas)
- Liens de vérification vers la visionneuse (عين الريم)
- Boucle expert intégrée : 👍 صحيح / 👎 خطأ / أعترض -> /api/feedback
  (l'اعتراض ouvre un champ de motif, transmis à la file de revue)
Sans build, sans dépendance : HTML+JS servi par FastAPI. Remplacé à terme
par le front Angular ; le contrat API reste identique.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

PAGE = """<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RimLex — المساعد القانوني</title><style>
:root{--ink:#1c2b3a;--green:#175a47;--gold:#a98a44;--bg:#f4f2ec;--card:#fff;--line:#ddd}
*{box-sizing:border-box}
body{font-family:'Segoe UI',Tahoma,sans-serif;margin:0;background:var(--bg);color:#1a1a18;
     display:flex;flex-direction:column;height:100vh}
header{background:var(--ink);color:#fff;padding:10px 20px;display:flex;align-items:center;gap:12px}
header b{color:var(--gold);font-size:17px}
header span{font-size:12px;color:#9fb0c3}
header a{margin-inline-start:auto;color:#c9a968;font-size:12px;text-decoration:none}
#msgs{flex:1;overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:12px;
      max-width:860px;width:100%;margin:0 auto}
.m{border-radius:12px;padding:12px 16px;max-width:88%;line-height:1.9;font-size:15px;
   white-space:pre-wrap;word-break:break-word}
.q{background:var(--green);color:#fff;align-self:flex-start}
.a{background:var(--card);border:1px solid var(--line);align-self:flex-end;width:88%}
.a .src{margin-top:10px;padding-top:8px;border-top:1px dashed var(--line);font-size:13px}
.a .src a{color:#1d5fa5;text-decoration:none}
.fb{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
.fb button{border:1px solid #bbb;background:#faf8f2;border-radius:16px;padding:4px 14px;
           cursor:pointer;font-size:12.5px;font-family:inherit}
.fb button:hover{background:#efe9da}
.fb button.done{background:#e7f3e7;border-color:#9c9;pointer-events:none}
.contest{margin-top:8px;display:none;gap:6px;flex-direction:column}
.contest textarea{border:1px solid #bbb;border-radius:8px;padding:8px;font-family:inherit;font-size:13px}
.contest .send{align-self:flex-start;background:var(--green);color:#fff;border:none;
               border-radius:8px;padding:6px 16px;cursor:pointer;font-size:13px}
#bar{display:flex;gap:10px;padding:12px 18px;background:var(--card);border-top:1px solid var(--line)}
#bar input{flex:1;border:1px solid #bbb;border-radius:10px;padding:11px 14px;font-size:15px;font-family:inherit}
#bar button{background:var(--green);color:#fff;border:none;border-radius:10px;padding:0 22px;
            font-size:15px;cursor:pointer;font-family:inherit}
#bar button:disabled{opacity:.5}
.note{font-size:12px;color:#8a8a85;text-align:center;padding:4px}
.think{color:#8a8a85;font-size:13px}
</style></head><body>
<header><b>RimLex</b><span>مساعد البحث القانوني — كل جواب يُثبت مصدره · عين الريم 🦌</span>
<a href="/api/admin">الإدارة</a></header>
<div id="msgs"></div>
<div class="note">أداة مساعدة للبحث — النص الأصلي وحده هو الحجة، تحقق دائماً عبر روابط المصادر.</div>
<div id="bar"><input id="q" placeholder="اطرح سؤالك القانوني…" autofocus>
<button id="send">إرسال</button></div>
<script>
const msgs = document.getElementById('msgs'), qi = document.getElementById('q'),
      btn = document.getElementById('send');
let user = localStorage.getItem('rimlex_user') ||
           (localStorage.setItem('rimlex_user',
              prompt('اسمك (يظهر في ملاحظاتك للفريق):') || 'مستعمل'),
            localStorage.getItem('rimlex_user'));

function el(tag, cls, txt){const e = document.createElement(tag);
  if(cls) e.className = cls; if(txt !== undefined) e.textContent = txt; return e}

function srcLinks(sources){
  const d = el('div', 'src');
  if(!sources || !sources.length){return d}
  d.append(el('b', '', '📚 المصادر: '));
  sources.forEach((s, i) => {
    const a = el('a', '', ` [${i+1}] ${ (s.law || s.file || '').slice(0, 55) } 🔎`);
    a.href = '/api/viewer?file=' + encodeURIComponent(s.file || '') +
             '&chunk=' + encodeURIComponent(s.chunk ?? '-');
    a.target = '_blank';
    d.append(a);
  });
  return d;
}

function feedbackBar(box, question, getAnswer, sources){
  const bar = el('div', 'fb');
  const mk = (label, type, needComment) => {
    const b = el('button', '', label);
    b.onclick = async () => {
      let comment = '';
      if(needComment){
        contest.style.display = 'flex'; contest.dataset.type = type; return;
      }
      await send(type, comment);
      bar.querySelectorAll('button').forEach(x => x.classList.remove('done'));
      b.classList.add('done'); b.textContent = label + ' ✓';
    };
    return b;
  };
  const send = async (type, comment) => {
    await fetch('/api/feedback', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({type, question, answer: getAnswer(),
                            sources, comment, user})});
  };
  const contest = el('div', 'contest');
  const ta = el('textarea', '', '');
  ta.placeholder = 'ما وجه الاعتراض؟ اذكر سندك القانوني إن أمكن…';
  ta.rows = 2;
  const go = el('button', 'send', 'إرسال الاعتراض إلى فريق المراجعة');
  go.onclick = async () => {
    await send(contest.dataset.type || 'contest', ta.value.trim());
    contest.replaceChildren(el('span', 'think', '✓ أُحيل اعتراضك على فريق المراجعة — شكراً.'));
  };
  contest.append(ta, go);
  bar.append(mk('👍 صحيح', 'up'), mk('👎 خطأ', 'down'),
             mk('⚖️ أعترض', 'contest', true));
  box.append(bar, contest);
}

async function ask(){
  const q = qi.value.trim(); if(!q) return;
  qi.value = ''; btn.disabled = true;
  msgs.append(Object.assign(el('div', 'm q', q)));
  const box = el('div', 'm a'); const body = el('div', '', '');
  const think = el('div', 'think', '⏳ البحث في المدونة القانونية…');
  box.append(think, body); msgs.append(box); msgs.scrollTop = msgs.scrollHeight;
  let sources = [], text = '';
  try{
    const r = await fetch('/api/chat/stream', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: q, k: 6})});
    const reader = r.body.getReader(); const dec = new TextDecoder();
    let buf = '';
    for(;;){
      const {done, value} = await reader.read(); if(done) break;
      buf += dec.decode(value, {stream: true});
      const lines = buf.split('\\n'); buf = lines.pop();
      for(const line of lines){
        if(!line.trim()) continue;
        let obj; try{obj = JSON.parse(line)}catch{continue}
        if(obj.sources){sources = obj.sources; think.textContent = '✍️ صياغة الجواب…'}
        if(obj.delta){text += obj.delta; body.textContent = text;
                      think.remove?.(); msgs.scrollTop = msgs.scrollHeight}
      }
    }
  }catch(e){ text = text || ('تعذر الاتصال بالخادم: ' + e); body.textContent = text }
  think.remove?.();
  if(!text){body.textContent = 'لم يصل جواب — محرك التوليد غير مشغَّل حالياً (Qdrant/Ollama).' }
  box.append(srcLinks(sources));
  feedbackBar(box, q, () => text, sources);
  msgs.scrollTop = msgs.scrollHeight; btn.disabled = false; qi.focus();
}
btn.onclick = ask;
qi.addEventListener('keydown', e => {if(e.key === 'Enter') ask()});
</script></body></html>"""


@router.get("/chat", response_class=HTMLResponse)
def chat_page():
    return PAGE
