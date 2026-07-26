"""
Chat juridique (RAG grounded) avec mémoire de conversation :
  question (+ session)  -> condensation de la question de suivi en question autonome
                        -> récupération des articles pertinents (search_laws)
                        -> réponse ancrée + citations, avec l'historique en contexte
                        -> persistance des messages + sommaire roulant (rag.memory)

La réponse est STRICTEMENT basée sur les textes récupérés (anti-hallucination).
"""
import json
import re
import requests

from core.config import OLLAMA_BASE_URL
from rag.search_laws import search_laws
from rag import store
from rag import memory

try:
    from qdrant_client.models import Filter, FieldCondition, MatchValue
except Exception:  # pragma: no cover
    Filter = None

CHAT_MODEL = "qwen2.5:72b"

GEN_OPTIONS = {
    "temperature": 0.2, "num_ctx": 16384, "num_predict": 1200,
    "repeat_penalty": 1.25, "repeat_last_n": 256,
}

# ══════════════════════════════════════════════════════════════════════════
#  PROMPT SYSTÈME (production) — règles de comportement du مساعد قانوني
# ══════════════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """أنت مساعد قانوني مغربي محترف، خبير في مختلف فروع القانون المغربي: الجنائي والمسطرة الجنائية، التجاري، المدني والمسطرة المدنية، الأسرة، الشغل، الإداري وغيرها. مستعملوك محامون وقضاة ومهنيو قانون؛ دقتك مسألة مسؤولية مهنية.

## مصدر الحقيقة الوحيد
- أجب حصرياً من «النصوص القانونية» المقدَّمة في السياق. معرفتك العامة تُستعمل للفهم والتنظيم فقط، لا كمصدر للأحكام.
- كل مقطع في السياق يحمل وسم «المصدر» الذي يحدد القانون الذي ينتمي إليه، وقد يحمل رقم المادة/الفصل. اعتمد هذا الوسم ولا تفترض مصدراً آخر.
- إذا لم تجد الجواب في النصوص المقدَّمة فقل بوضوح: «لم أعثر على نص قانوني مطبّق ضمن المدونة المتاحة»، واقترح إعادة صياغة السؤال إن كان ذلك مفيداً. لا تخترع أبداً مادةً أو رقماً أو مقتضى.

## قواعد الاستشهاد (إلزامية)
1. عند كل حكم تذكره: اذكر رقم المادة أو الفصل واسم القانون كما في وسم «المصدر» (مثال: المادة 41-1 من قانون المسطرة الجنائية).
2. انتبه للإحالات: إذا ورد داخل النص «المادة X من مدونة التجارة» أو من قانون آخر، فهذه إحالة إلى قانون مختلف وليست مصدر المقطع؛ انسب المقطع إلى قانونه الصحيح وميّز الإحالة بوضوح.
3. لا تخلط بين القوانين: لأسئلة القانون الجنائي اعتمد نصوص القانون الجنائي والمسطرة الجنائية، لا التجاري، والعكس صحيح.
4. القاعدة في الأرقام والمبالغ والآجال: انقلها حرفياً كما وردت في النص، ولا تقرّبها أو تعيد صياغتها.
5. إذا أحال النص إلى قائمة طويلة من الفصول أو المواد، فلا تسردها كلها ولا تخترع أرقاماً متسلسلة؛ اذكر أنها محددة في المادة المعنية مع مثال أو مثالين.

## بنية الجواب
- ابدأ بالجواب المباشر عن السؤال، ثم فصّل الشروط أو الأحكام في نقاط مرقمة عند الاقتضاء، واختم بالإشارة إلى المسطرة أو الجهة المختصة إن وردت في النصوص.
- كن مركزاً: لا حشو ولا مقدمات إنشائية. الجودة في الدقة لا في الطول.

## حدود المسؤولية
- أنت أداة بحث ومساعدة، لست بديلاً عن الاستشارة القانونية؛ عند الأسئلة المتعلقة بقضية معروضة فعلاً، ذكّر بإيجاز بضرورة الرجوع إلى النصوص الأصلية.
- إذا ظهر من النصوص أن القانون عُدّل أو نُسخ (مثل عبارات «تم تغيير وتتميم» في الهوامش)، فنبّه إلى ذلك واذكر القانون المعدِّل إن ورد.
- المقاطع قد تحمل ملاحظة نظامية بين قوسين عن حالة النص (محيَّن / نص لاحق يعدّله / منسوخ محتمل): التزم بما تطلبه تلك الملاحظة حرفياً في جوابك.
- عند تعارض اجتهادات قضائية حول نفس المسألة: اعرض الموقفين معاً بتاريخيهما وغرفتيهما، وبيّن أيّهما الأحدث، وصرّح بأن الاجتهاد غير مستقر؛ لا ترجّح أحدهما من عندك.

## وضع الاعتراض (مستعمل خبير يجادل في الجواب)
- إذا اعترض المستعمل على جوابك فلا تتراجع مجاملةً لصفته أو سلطته: العبرة بالنصوص لا بالمقامات.
- أعد عرض مصدرك بدقة (النص، المادة، الصفحة إن وردت) واطلب من المعترض سنده القانوني.
- إذا قدّم سنداً أقوى أو أحدث: أقرّ بذلك صراحةً واشكره، وقل إن ملاحظته ستُحال على فريق مراجعة المدونة. لا تُعدّل المعطيات من تلقاء نفسك أبداً.
- إذا لم يقدّم سنداً: تمسّك بما تقوله نصوصك بأدب، وبيّن أن الخلاف سيُسجَّل كنقطة قابلة للمراجعة.
- لا تحسم خلافاً فقهياً حقيقياً: صرّح بأن المسألة محل نظر واعرض الموقفين بمصادرهما.
- كل اعتراض قيّم سواء انتهى بتصحيح جوابك أو بتأكيده — رحّب به دائماً.

## المحادثة
- إذا وُجد ملخص أو رسائل سابقة، فاستعملها لفهم سياق السؤال (الضمائر، «وماذا عن...»)، لكن الأحكام دائماً من نصوص السياق الحالي.
- أجب بالعربية الفصحى. إذا سُئلت بالفرنسية فأجب بالفرنسية مع إبقاء الاستشهادات بأسمائها العربية الرسمية.
- عند ترجمة مقتضى قانوني إلى الفرنسية: أورد النص العربي الأصلي حرفياً بين علامتي تنصيص متبوعاً بالترجمة، واستعمل المصطلحات القانونية المغربية الرسمية (dahir، procureur du Roi، mise en demeure...). الترجمة للفهم؛ والنص العربي وحده هو الحجة."""

CONDENSE_PROMPT = (
    "أنت مساعد يعيد صياغة أسئلة المتابعة. حوّل سؤال المتابعة التالي إلى سؤال "
    "قانوني مستقل ومكتمل بالاعتماد على سياق المحادثة (فك الضمائر والإشارات). "
    "أخرج السؤال المعاد صياغته فقط، دون شرح ودون مقدمات. إذا كان السؤال "
    "مستقلاً وواضحاً أصلاً فأعده كما هو حرفياً."
)


# ══════════════════════════════════════════════════════════════════════════
#  Aides LLM internes
# ══════════════════════════════════════════════════════════════════════════
def _llm(messages: list[dict], num_predict: int = 300, temperature: float = 0.1) -> str:
    """Appel court non-streamé (condensation, sommaire)."""
    r = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={"model": CHAT_MODEL, "messages": messages, "stream": False,
              "options": {"temperature": temperature, "num_ctx": 8192,
                          "num_predict": num_predict}},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def condense_question(history: list[dict], question: str) -> str:
    """Réécrit une question de suivi en question autonome pour la recherche
    vectorielle (« وماذا عن القاصرين؟ » -> question complète). Sans historique,
    ou en cas d'erreur, renvoie la question telle quelle."""
    if not history:
        return question
    convo = "\n".join(
        f"{'المستخدم' if m['role'] == 'user' else 'المساعد'}: {m['content'][:400]}"
        for m in history[-6:]
    )
    try:
        out = _llm(
            [{"role": "system", "content": CONDENSE_PROMPT},
             {"role": "user", "content":
                 f"المحادثة السابقة:\n{convo}\n\nسؤال المتابعة: {question}\n\nالسؤال المستقل:"}],
            num_predict=150,
        )
        out = out.strip().strip('"«»')
        # garde-fou : sortie vide ou déraisonnablement longue -> question d'origine
        if 3 <= len(out) <= 500:
            return out
    except Exception:
        pass
    return question


# ══════════════════════════════════════════════════════════════════════════
#  Expansion d'en-tête d'article (inchangé)
# ══════════════════════════════════════════════════════════════════════════
_HDR = re.compile(r"^\s*((?:المادة|الفصل)\s*[-\s]?\d+(?:\s*[-]\s*\d+)?)")
_XREF = re.compile(r"^\s*(?:المادة|الفصل)\s*[-\s]?\d+(?:\s*[-]\s*\d+)?\s*من\b")


def _real_header(t: str) -> str | None:
    if _XREF.match(t):
        return None
    m = _HDR.match(t)
    return m.group(1).strip() if m else None


def _expand(hit: dict, back: int = 4) -> str:
    txt = hit.get("text", "") or ""
    col = hit.get("collection")
    f = hit.get("file")
    ci = hit.get("chunk")
    if not (Filter and col and f and isinstance(ci, int)):
        return txt
    hdr = _real_header(txt)
    if hdr:
        return txt
    parts: list[str] = []
    for step in range(1, back + 1):
        idx = ci - step
        if idx < 0:
            break
        try:
            pts, _ = store.client().scroll(
                col,
                scroll_filter=Filter(must=[
                    FieldCondition(key="file", match=MatchValue(value=f)),
                    FieldCondition(key="chunk", match=MatchValue(value=idx)),
                ]),
                limit=1, with_payload=True,
            )
        except Exception:
            break
        if not pts:
            break
        ptext = pts[0].payload.get("text", "") or ""
        parts.insert(0, ptext)
        hdr = _real_header(ptext)
        if hdr:
            break
    body = ("\n".join(parts) + "\n" + txt) if parts else txt
    if hdr:
        body = f"(هذا المقطع جزء من «{hdr}»)\n" + body
    return body


_VERSION_INDEX: dict | None = None
_VERSION_CORPUS = r"Y:\adala-project\aiocr_data\laws_corpus_v2.jsonl"


def _version_info(h: dict) -> dict | None:
    """Statut versionnel du chunk (consolidé/à vérifier/abrogé), chargé
    paresseusement depuis le corpus enrichi (jointure au service, en attendant
    la ré-ingestion Qdrant avec les nouveaux champs)."""
    global _VERSION_INDEX
    if _VERSION_INDEX is None:
        _VERSION_INDEX = {}
        try:
            with open(_VERSION_CORPUS, encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    if r.get("status", "current") != "current":
                        _VERSION_INDEX[(r["file"], str(r["chunk"]))] = r
        except OSError:
            pass
    return _VERSION_INDEX.get((h.get("file", ""), str(h.get("chunk", ""))))


def _version_note(h: dict) -> str:
    v = _version_info(h)
    if not v:
        return ""
    st = v.get("status")
    if st == "consolidated":
        refs = "، ".join(v.get("amended_by", []))
        note = f"\n(ملاحظة: هذا النص محيَّن — عُدِّل بمقتضى النص/النصوص رقم {refs}؛ اذكر ذلك عند الاستشهاد."
        if v.get("amended_by_docs"):
            note += " النص المعدِّل متوفر في المدونة ويمكن للمستعمل الاطلاع عليه عبر رابط التحقق."
        return note + ")"
    if st == "check_amendments":
        refs = "، ".join(v.get("pending_amendments", []))
        return f"\n(تنبيه: يوجد نص لاحق رقم {refs} يعدّل هذا القانون وقد لا يكون مدمجاً هنا — نبّه المستعمل.)"
    if st == "possibly_abrogated":
        return "\n(تحذير: ورد ما يفيد نسخ/إلغاء هذا النص — نبّه المستعمل وجوباً وتحقق من النص الناسخ.)"
    return ""


def _expert_note(h: dict) -> str:
    """Annotations d'experts validées, jointes par fichier (boucle expert)."""
    try:
        from api.feedback import annotations_for
        anns = annotations_for(h.get("file", ""))
    except Exception:
        return ""
    parts = []
    for a in anns:
        art = f" (المادة {a['article']})" if a.get("article") else ""
        parts.append(f"\n(ملاحظة خبير معتمدة — {a.get('author_role', 'خبير')}{art}: "
                     f"{a['text']} — اذكرها إن كانت وثيقة الصلة بالسؤال.)")
    return "".join(parts)


def _build_context(hits: list[dict]) -> str:
    parts = []
    for i, h in enumerate(hits):
        art = h.get("article")
        art_lbl = f" — رقم المادة/الفصل: {art}" if art else ""
        parts.append(
            f"[مقطع {i + 1}] المصدر: {h.get('law', '')}{art_lbl}\nالنص: {_expand(h)}"
            + _version_note(h) + _expert_note(h)
        )
    return "\n\n".join(parts)


def _sources(hits: list[dict]) -> list[dict]:
    return [
        {
            "law": h.get("law", ""),
            "file": h.get("file", ""),
            "article": h.get("article"),
            "chunk": h.get("chunk"),
            "score": round(float(h.get("score", 0)), 3),
            "excerpt": (h.get("text", "") or "")[:400],
        }
        for h in hits
    ]


# ══════════════════════════════════════════════════════════════════════════
#  Assemblage des messages (mémoire + contexte juridique)
# ══════════════════════════════════════════════════════════════════════════
def _load_session(session_id: str | None) -> tuple[list[dict], str]:
    if not session_id:
        return [], ""
    try:
        memory.init()
        return memory.get_recent(session_id), memory.get_summary(session_id)
    except Exception:
        return [], ""


def _clean_history(history: list[dict] | None) -> list[dict]:
    """Historique fourni par le client (mode OpenAI, sans état) : filtre et borne."""
    out = []
    for m in history or []:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            out.append({"role": m["role"], "content": m["content"][:4000]})
    return out[-memory.RECENT_TURNS:]


def _build_messages(question: str, hits: list[dict],
                    history: list[dict], summary: str) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if summary:
        msgs.append({"role": "system",
                     "content": f"ملخص المحادثة السابقة (للسياق فقط):\n{summary}"})
    msgs.extend(history)
    msgs.append({"role": "user", "content":
        f"السياق (نصوص قانونية من مختلف القوانين المغربية، كل مقطع مسبوق "
        f"بوسم «المصدر»):\n{_build_context(hits)}\n\nالسؤال: {question}"})
    return msgs


def _persist(session_id: str | None, question: str,
             answer_text: str, sources: list[dict]) -> None:
    if not session_id or not answer_text:
        return
    try:
        memory.add_message(session_id, "user", question)
        memory.add_message(session_id, "assistant", answer_text, sources=sources)
        memory.maybe_summarize(
            session_id,
            llm=lambda p: _llm([{"role": "user", "content": p}], num_predict=400))
    except Exception:
        pass  # la mémoire ne doit jamais casser la réponse


# ══════════════════════════════════════════════════════════════════════════
#  Garde-fou citations : tout passage entre guillemets doit exister
#  littéralement dans les passages servis — sinon avertissement mécanique.
# ══════════════════════════════════════════════════════════════════════════
_QUOTE_RE = re.compile(r"[«\"“]([^«»\"“”]{15,300})[»\"”]")
_DIAC = re.compile(r"[ً-ٰٟـ]")


def _qnorm(s: str) -> str:
    s = _DIAC.sub("", s or "")
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ى", "ي").replace("ة", "ه"))
    return re.sub(r"[^؀-ۿ0-9]", "", s)


def _quote_warning(text: str, hits: list[dict]) -> str:
    """Chaîne d'avertissement à ajouter à la réponse ('' si tout est vérifié)."""
    try:
        corpus = _qnorm(" ".join(h.get("text", "") or "" for h in hits))
        missing = []
        for m in _QUOTE_RE.finditer(text or ""):
            q = _qnorm(m.group(1))
            if len(q) >= 12 and q not in corpus:
                missing.append(m.group(1))
        if not missing:
            return ""
        # visible dans la file de revue de la console (boucle expert)
        try:
            from api.admin_core import conn, init_db
            init_db()
            with conn() as c:
                c.execute("INSERT INTO feedback(ts,user,type,question,answer,comment) "
                          "VALUES(?,?,?,?,?,?)",
                          (time.time(), "garde-citations", "quote_mismatch", "",
                           (text or "")[:1500],
                           " | ".join(q[:80] for q in missing[:3])))
        except Exception:
            pass
        return ("\n\n⚠️ تنبيه آلي: "
                f"{len(missing)} اقتباس(ات) في هذا الجواب لم يُعثر عليها حرفياً في "
                "النصوص المسترجَعة — تحقق من روابط المصادر قبل الاعتماد عليها.")
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════
#  API publique
# ══════════════════════════════════════════════════════════════════════════
def answer(question: str, k: int = 6, session_id: str | None = None,
           history: list[dict] | None = None) -> dict:
    """`history` explicite (mode OpenAI, sans état) court-circuite la session
    interne : pas de lecture ni de persistance mémoire."""
    question = (question or "").strip()
    if not question:
        return {"answer": "", "sources": []}

    if history is not None:
        history, summary = _clean_history(history), ""
        session_id = None                      # le client gère son propre historique
    else:
        history, summary = _load_session(session_id)
    search_q = condense_question(history, question)
    hits = search_laws(search_q, limit=k)
    if not hits:
        return {
            "answer": "لم أعثر على نصوص قانونية ذات صلة بسؤالك في المدوّنة الحالية.",
            "sources": [], "search_query": search_q,
        }

    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": CHAT_MODEL,
                  "messages": _build_messages(question, hits, history, summary),
                  "stream": False, "options": GEN_OPTIONS},
            timeout=600,
        )
        r.raise_for_status()
        text = r.json()["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        text = f"تعذّر توليد الإجابة (نموذج الاستدلال غير جاهز؟): {e}"

    text += _quote_warning(text, hits)
    sources = _sources(hits)
    _persist(session_id, question, text, sources)
    return {"answer": text, "sources": sources, "search_query": search_q}


def answer_stream(question: str, k: int = 6, session_id: str | None = None,
                  history: list[dict] | None = None):
    """Générateur NDJSON : {"sources":[…]} puis {"delta":"…"}* puis {"done":true}.
    `history` explicite -> mode sans état (voir answer())."""
    question = (question or "").strip()
    if not question:
        yield json.dumps({"sources": []}) + "\n"
        yield json.dumps({"done": True}) + "\n"
        return

    if history is not None:
        history, summary = _clean_history(history), ""
        session_id = None
    else:
        history, summary = _load_session(session_id)
    search_q = condense_question(history, question)
    hits = search_laws(search_q, limit=k)
    yield json.dumps({"sources": _sources(hits), "search_query": search_q},
                     ensure_ascii=False) + "\n"

    if not hits:
        yield json.dumps(
            {"delta": "لم أعثر على نصوص قانونية ذات صلة بسؤالك في المدوّنة الحالية."},
            ensure_ascii=False,
        ) + "\n"
        yield json.dumps({"done": True}) + "\n"
        return

    full: list[str] = []
    try:
        with requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": CHAT_MODEL,
                  "messages": _build_messages(question, hits, history, summary),
                  "stream": True, "options": GEN_OPTIONS},
            stream=True,
            timeout=600,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                chunk = obj.get("message", {}).get("content", "")
                if chunk:
                    full.append(chunk)
                    yield json.dumps({"delta": chunk}, ensure_ascii=False) + "\n"
                if obj.get("done"):
                    break
    except Exception as e:  # noqa: BLE001
        yield json.dumps({"delta": f"\n\n[تعذّر التوليد: {e}]"}, ensure_ascii=False) + "\n"

    warn = _quote_warning("".join(full), hits)
    if warn:
        full.append(warn)
        yield json.dumps({"delta": warn}, ensure_ascii=False) + "\n"
    _persist(session_id, question, "".join(full), _sources(hits))
    yield json.dumps({"done": True}) + "\n"
