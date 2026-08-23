"""
Chat juridique (RAG grounded) avec mémoire de conversation :
  question (+ session)  -> condensation de la question de suivi en question autonome
                        -> récupération des articles pertinents (search_laws)
                        -> réponse ancrée + citations, avec l'historique en contexte
                        -> persistance des messages + sommaire roulant (rag.memory)

La réponse est STRICTEMENT basée sur les textes récupérés (anti-hallucination).
"""
import json
import os
import re
import requests

from core.config import OLLAMA_BASE_URL
from rag.search_laws import search_laws
from rag.query_lang import search_query_for, answer_language_rule
from rag import store
from rag import memory
from rag import procedures
from services import attachments

try:
    from qdrant_client.models import Filter, FieldCondition, MatchValue
except Exception:  # pragma: no cover
    Filter = None

CHAT_MODEL = os.environ.get("RIMLEX_CHAT_MODEL", "qwen2.5:32b")

GEN_OPTIONS = {
    "temperature": 0.2, "num_ctx": 16384, "num_predict": 1200,
    # 1.25 poussait le modèle hors distribution sur l'arabe (mots-outils très
    # répétés) et provoquait des bascules vers d'autres écritures.
    "repeat_penalty": 1.08, "repeat_last_n": 128,
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
- عند ترجمة مقتضى قانوني إلى الفرنسية: أورد النص العربي الأصلي حرفياً بين علامتي تنصيص متبوعاً بالترجمة، واستعمل المصطلحات القانونية المغربية الرسمية (dahir، procureur du Roi، mise en demeure...). الترجمة للفهم؛ والنص العربي وحده هو الحجة.

## طلبات التحرير (شكاية، مذكرة، طلب، إنذار، عقد)
- هذه الطلبات ليست أسئلة بحث: لا تُحرّر وثيقة على معطيات مفترضة.
- اسأل أولاً عن العناصر الناقصة الضرورية، في قائمة قصيرة ومركّزة: هوية الأطراف وصفاتهم، الوقائع بتواريخها وأماكنها، الضرر أو المطلوب، الجهة المرسل إليها (وكيل الملك، المحكمة المختصة…)، الوثائق المرفقة.
- اذكر في الوقت نفسه الأساس القانوني المحتمل من النصوص المسترجَعة، حتى يعرف المستعمل إلى أين يتجه.
- لا تُحرّر الوثيقة إلا بعد توفر هذه العناصر؛ وعندها التزم بالشكل المعتمد مغربياً واذكر الفصول المستند إليها.
- إذا أصرّ المستعمل على التحرير رغم نقص المعطيات، حرّر نموذجاً مع وضع فراغات صريحة (…) لكل معطى ناقص، ونبّه إلى وجوب ملئها.

## قاعدة اللغة (مطلقة)
اكتب جوابك كاملاً بالعربية الفصحى، أو بالفرنسية إن كان السؤال بالفرنسية. لا تستعمل في أي جزء من الجواب أي لغة أو كتابة أخرى (الصينية، اليابانية، الكورية، الروسية...). إذا لم تجد ما تقوله، قل ذلك بالعربية."""

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
              "options": {"temperature": temperature, "num_ctx": GEN_OPTIONS["num_ctx"],
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
_VERSION_CORPUS = os.path.join(
    os.environ.get("RIMLEX_DATA_DIR", r"Y:\adala-project\aiocr_data"),
    "laws_corpus_v2.jsonl")


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


def _build_context(hits: list[dict], procs: list[dict] | None = None,
                   pieces: list[dict] | None = None) -> str:
    parts = []
    # La marche à suivre passe avant les textes : c'est la réponse à la
    # question posée, les articles n'en sont que le fondement.
    # Les pièces du dossier viennent en premier : elles portent les faits
    # sur lesquels la question se pose, les textes n'arrivent qu'ensuite.
    bloc_p = attachments.bloc_pieces(pieces or [])
    if bloc_p:
        parts.append(bloc_p)
    bloc = procedures.bloc_procedures(procs or [])
    if bloc:
        parts.append(bloc)
    for i, h in enumerate(hits):
        art = h.get("article")
        art_lbl = f" — رقم المادة/الفصل: {art}" if art else ""
        parts.append(
            f"[مقطع {i + 1}] المصدر: {h.get('law', '')}{art_lbl}\nالنص: {_expand(h)}"
            + _version_note(h) + _expert_note(h)
        )
    return "\n\n".join(parts)


def _kind_of(h: dict) -> str:
    """'jurisprudence' pour les arrêts, 'loi' pour les textes législatifs."""
    if (h.get("corpus") or "") == "jurisprudence":
        return "jurisprudence"
    if h.get("decision_no") or h.get("case_ref"):
        return "jurisprudence"
    return "loi"


def _sources(hits: list[dict]) -> list[dict]:
    out = []
    for h in hits:
        kind = _kind_of(h)
        src = {
            "law": h.get("law", ""),
            "file": h.get("file", ""),
            "article": h.get("article"),
            "chunk": h.get("chunk"),
            "score": round(float(h.get("score", 0)), 3),
            "excerpt": (h.get("text", "") or "")[:400],
            # v4 : de quoi ouvrir la source et la surligner
            "kind": kind,
            "kind_ar": "اجتهاد قضائي" if kind == "jurisprudence" else "نص قانوني",
            "kind_fr": "Jurisprudence" if kind == "jurisprudence" else "Loi",
            "page": h.get("page"),
            "pdf": h.get("pdf"),
            "folder": h.get("folder"),
        }
        for k in ("decision_no", "decision_year", "case_ref"):
            if h.get(k) is not None:
                src[k] = h[k]
        out.append(src)
    # Regroupement lois / jurisprudence SANS re-trier par score : l'ordre reçu
    # vient de la fusion RRF (+ ancrage des articles explicitement cités), qui
    # est plus fiable que le score vectoriel brut — un article trouvé par BM25
    # a un score vectoriel de 0 et serait rétrogradé à tort.
    out.sort(key=lambda s: s["kind"] != "loi")     # tri stable
    for i, s in enumerate(out, 1):
        s["rank"] = i
    return out


# ══════════════════════════════════════════════════════════════════════════
#  Assemblage des messages (mémoire + contexte juridique)
# ══════════════════════════════════════════════════════════════════════════
def _load_session(session_id: str | None) -> tuple[list[dict], str]:
    if not session_id:
        return [], ""
    try:
        memory.init()
        recent = memory.get_recent(session_id) or []
        # borne dure : au-delà, le prompt gonfle et la latence double
        return recent[-6:], memory.get_summary(session_id)
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
                    history: list[dict], summary: str,
                    procs: list[dict] | None = None,
                    pieces: list[dict] | None = None) -> list[dict]:
    msgs: list[dict] = [{"role": "system",
                         "content": SYSTEM_PROMPT + answer_language_rule(question)}]
    if summary:
        msgs.append({"role": "system",
                     "content": f"ملخص المحادثة السابقة (للسياق فقط):\n{summary}"})
    msgs.extend(history)
    msgs.append({"role": "user", "content":
        f"السياق (نصوص قانونية من مختلف القوانين المغربية، كل مقطع مسبوق "
        f"بوسم «المصدر»):\n{_build_context(hits, procs, pieces)}\n\nالسؤال: {question}"})
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


_STACK_DOWN_MSG = ("محرك الإجابة غير مشغَّل حالياً (خدمات الاسترجاع والتوليد "
                   "متوقفة). أخبر المشرف بتشغيل الخدمات ثم أعد المحاولة.")


def _stack_ready() -> bool:
    """Échec rapide quand Ollama/Qdrant sont éteints — plutôt que des minutes
    de retries avant le premier octet."""
    try:
        requests.get(OLLAMA_BASE_URL, timeout=2)
        return True
    except Exception:
        return False



# ══════════════════════════════════════════════════════════════════════════
#  Garde-fou citations : tout passage entre guillemets doit exister
#  littéralement dans les passages servis — sinon avertissement mécanique.
# ══════════════════════════════════════════════════════════════════════════
_QUOTE_RE = re.compile(r"[«\"“]([^«»\"“”]{15,300})[»\"”]")
_DIAC = re.compile(r"[ً-ٰٟـ]")

# ── Garde-fou de langue ───────────────────────────────────────────────────
# Observé en production : le modèle bascule parfois en chinois au milieu d'une
# phrase arabe. On détecte l'écriture CJK/cyrillique et on coupe net plutôt
# que de servir un texte illisible à un magistrat.
_FOREIGN = re.compile("[一-鿿぀-ヿ가-힯Ѐ-ӿ]")
_DRIFT_MSG = ("\n\n⚠️ توقّف الجواب: انحرف النموذج إلى لغة أخرى. "
              "أعد طرح السؤال — إن تكرّر الأمر فأبلغ فريق المراجعة.")


def _language_drift(text: str, threshold: int = 8) -> bool:
    return len(_FOREIGN.findall(text or "")) >= threshold


def _qnorm(s: str) -> str:
    s = _DIAC.sub("", s or "")
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ى", "ي").replace("ة", "ه"))
    return re.sub(r"[^؀-ۿ0-9]", "", s)


# « المادة 31 من قانون الجنسية » — un article, puis le texte auquel la réponse
# le rattache. On borne à 60 caractères : au-delà, ce n'est plus un nom de loi.
# Le point termine une phrase, mais il sépare aussi les tranches d'un numéro
# de loi — « 22.01 ». On ne l'accepte donc qu'immédiatement suivi d'un chiffre,
# sans quoi « القانون رقم 12.34 » se réduisait à « القانون رقم 12 », privé de
# ce qui l'identifie.
_ATTRIB_RE = re.compile(
    r"(?:المادة|الفصل)\s*(\d{1,4}(?:[-.]\d{1,3})?)\s*من\s+"
    r"((?:[^،؛()\n.]|\.(?=\d)){4,60})")
# Mots qui ne distinguent aucune loi : les comparer ferait crier au loup.
_MOTS_VIDES = {"قانون", "القانون", "مدونة", "المدونة", "ظهير", "الظهير",
               "مرسوم", "المرسوم", "هذا", "هذه", "نفس", "أعلاه", "المذكور",
               "السالف", "الذكر", "رقم", "المتعلق", "بمثابة", "الشريف"}


def _mots_loi(nom: str) -> set:
    """Ce qui identifie vraiment un texte : ses mots propres ET son numéro.

    Une loi marocaine se désigne d'abord par son numéro — 22.01, 1.74.447. Le
    retirer laissait « القانون رقم 12.34 » sans rien de discriminant, donc
    impossible à confronter.
    """
    numeros = set(re.findall(r"\d{1,3}(?:\.\d{2,3}){1,2}", nom or ""))
    mots = {m for m in re.sub(r"[^ء-ي\s]", " ", nom or "").split()
            if len(m) > 2 and m not in _MOTS_VIDES}
    return mots | numeros


def _attribution_douteuse(text: str, hits: list[dict]) -> str:
    """Chaque article cité est-il rattaché au bon texte ?

    Mesuré sur une réponse réelle : le moteur avait servi le الفصل 31 du code
    de procédure civile de 1974, et le modèle l'a présenté comme « الفصل 31 من
    قانون الجنسية المغربية » — le nom emprunté à un passage voisin du contexte.
    La règle 2 du prompt système interdit pourtant cela mot pour mot.

    On ne peut pas empêcher la faute, on peut refuser de la laisser passer :
    pour chaque « article N من X » de la réponse, on cherche le passage servi
    qui porte l'article N et on compare le texte auquel il appartient.
    """
    par_article = {}
    for h in hits:
        art = str(h.get("article") or "").strip()
        m = re.search(r"(\d{1,4}(?:[-.]\d{1,3})?)", art)
        if m:
            par_article.setdefault(m.group(1), set()).add(h.get("law") or "")
    if not par_article:
        return ""
    fautes = []
    for m in _ATTRIB_RE.finditer(text or ""):
        num, loi_dite = m.group(1), m.group(2).strip()
        lois_reelles = par_article.get(num)
        if not lois_reelles:
            continue                       # article non servi : hors sujet ici
        dits = _mots_loi(loi_dite)
        if not dits:
            continue
        if any(dits & _mots_loi(l) for l in lois_reelles):
            continue                       # au moins un mot de loi en commun
        vraie = sorted(lois_reelles, key=len)[0][:60]
        fautes.append((num, loi_dite[:50], vraie))
    if not fautes:
        return ""
    lignes = "؛ ".join(
        f"«{'المادة'} {n} من {dit}» ← المصدر المقدَّم هو «{vrai}»"
        for n, dit, vrai in fautes[:4])
    return ("\n\n⚠️ [تحقق من الإسناد] نسب هذا الجواب مقتضى إلى نص غير الذي ورد "
            f"في السياق: {lignes}. راجع النص الأصلي قبل الاعتماد على الإحالة.")


def _bandeau_version(hits: list[dict], text: str) -> str:
    """Bandeau d'abrogation imposé, indépendamment de l'obéissance du modèle.

    `_version_note` dépose déjà l'avertissement dans le contexte et le prompt
    système ordonne de le relayer « حرفياً ». Mesuré : le modèle ne le fait pas
    toujours. Un article du code de procédure civile de 1974 a été servi comme
    droit en vigueur, sans mention de son abrogation par la loi 58.25 — alors
    que la note figurait bien dans le contexte envoyé.

    Sur des délais de recours, une omission pareille se paie par une forclusion.
    On ne demande donc plus : on préfixe. Le bandeau n'est posé que si le texte
    abrogé a réellement servi, et pas si le modèle l'a déjà signalé lui-même.
    """
    abroges: dict[str, list[str]] = {}
    for h in hits:
        v = _version_info(h)
        if not v or v.get("status") != "possibly_abrogated":
            continue
        art = str(h.get("article") or "").strip()
        # l'article doit apparaître dans la réponse : un passage récupéré mais
        # non mobilisé n'a pas à déclencher d'alarme
        if art and art not in ("None", "") and art not in text:
            continue
        loi = (h.get("law") or "").strip()[:70]
        abroges.setdefault(loi, [])
        if art and art not in abroges[loi]:
            abroges[loi].append(art)
    if not abroges:
        return ""
    if "نُسخ" in text or "منسوخ" in text or "ألغي" in text:
        return ""                      # le modèle a déjà prévenu
    lignes = []
    for loi, arts in abroges.items():
        refs = "، ".join(a for a in arts[:6] if a)
        lignes.append(f"«{loi}»" + (f" ({refs})" if refs else ""))
    return ("⚠️ [تحذير إلزامي] استند هذا الجواب إلى نص ورد ما يفيد نسخه أو "
            "إلغاءه: " + " ؛ ".join(lignes) +
            ". تحقق وجوبا من النص الناسخ ومن النظام المطبّق على ملفك قبل "
            "الاعتماد على ما سبق.\n\n")


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



# ── Sources dynamiques ────────────────────────────────────────────────────
# Deux défauts observés : (1) toujours 6 sources quelle que soit la réponse,
# (2) des sources affichées alors que le modèle dit n'avoir rien trouvé.
# On filtre donc en amont (pertinence) et en aval (réellement citées).
_NOT_FOUND = ("لم أعثر", "لم أجد", "لا يوجد نص", "غير متوفر ضمن",
              "Je n'ai pas trouvé", "aucune disposition")


def _relevant(hits: list[dict], floor_ratio: float = 0.72) -> list[dict]:
    """Ne garde que les passages proches du meilleur : une question à laquelle
    un seul article répond ne doit pas traîner cinq voisins hors sujet."""
    if not hits:
        return []
    best_rrf = max(h.get("rrf", 0) for h in hits)
    best_vec = max(h.get("score", 0) for h in hits)
    out = []
    for h in hits:
        keep_rrf = best_rrf and h.get("rrf", 0) >= best_rrf * floor_ratio
        keep_vec = best_vec and h.get("score", 0) >= best_vec * 0.94
        lexical = h.get("rank_bm25") is not None
        if keep_rrf or keep_vec or lexical:
            out.append(h)
    return out or hits[:1]


def _cited(hits: list[dict], text: str) -> list[dict]:
    """Après génération : ne montrer que les sources réellement mobilisées.
    Si le modèle déclare n'avoir rien trouvé, on n'affiche aucune source."""
    if not text:
        return []
    low = text[:400]
    if any(m in low for m in _NOT_FOUND) and "الفصل" not in text and "المادة" not in text:
        return []
    used = []
    for h in hits:
        art = str(h.get("article") or "").strip()
        law = (h.get("law") or "").strip()
        law_key = law.split("رقم")[-1].strip()[:12] if "رقم" in law else law[:14]
        art_hit = bool(art and art != "None" and
                       re.search(r"(?:المادة|الفصل)\s*" + re.escape(art) + r"", text))
        law_hit = bool(law_key and len(law_key) > 4 and law_key in text)
        if art_hit or law_hit:
            used.append(h)
    return used or hits          # aucune correspondance : on garde tout

# ══════════════════════════════════════════════════════════════════════════
#  API publique
# ══════════════════════════════════════════════════════════════════════════
def answer(question: str, k: int = 6, session_id: str | None = None,
           history: list[dict] | None = None, matiere: str | None = None,
           strict: bool = False,
           attachment_ids: list[str] | None = None) -> dict:
    """`history` explicite (mode OpenAI, sans état) court-circuite la session
    interne : pas de lecture ni de persistance mémoire."""
    question = (question or "").strip()
    if not question:
        return {"answer": "", "sources": []}
    if not _stack_ready():
        return {"answer": _STACK_DOWN_MSG, "sources": [], "search_query": question}

    if history is not None:
        history, summary = _clean_history(history), ""
        session_id = None                      # le client gère son propre historique
    else:
        history, summary = _load_session(session_id)
    search_q = condense_question(history, question)
    search_q, _ar = search_query_for(search_q, _llm)
    hits = search_laws(search_q, limit=k, matiere=matiere, strict=strict)
    # L'intention se lit sur la question ET sur sa reformulation : un
    # « et ensuite ? » ne porte le mot « مسطرة » que dans la seconde.
    # Les pièces sont désignées par l'utilisateur, jamais devinées ; elles
    # restent bornées à leur session (un identifiant deviné n'ouvre rien).
    pieces = attachments.pour_contexte(session_id, attachment_ids or []) \
        if (session_id and attachment_ids) else []
    procs = (procedures.chercher(search_q)
             if procedures.veut_une_procedure(question + " " + search_q) else [])
    if not hits and not procs and not pieces:
        return {
            "answer": "لم أعثر على نصوص قانونية ذات صلة بسؤالك في المدوّنة الحالية.",
            "sources": [], "search_query": search_q,
        }

    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": CHAT_MODEL,
                  "messages": _build_messages(question, hits, history, summary, procs,
                                             pieces),
                  "stream": False, "options": GEN_OPTIONS},
            timeout=600,
        )
        r.raise_for_status()
        text = r.json()["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        text = f"تعذّر توليد الإجابة (نموذج الاستدلال غير جاهز؟): {e}"

    if _language_drift(text):
        text = _DRIFT_MSG.strip()
    else:
        text += _quote_warning(text, hits)
        text += _attribution_douteuse(text, hits)
        # en tête : un avertissement d'abrogation lu après coup ne protège
        # personne
        text = _bandeau_version(hits, text) + text
    # les fiches ne subissent ni le filtre de pertinence ni celui des
    # citations : elles n'ont ni score RRF ni numéro d'article à repérer
    sources = procedures.sources(procs) + _sources(_cited(_relevant(hits), text))
    _persist(session_id, question, text, sources)
    return {"answer": text, "sources": sources, "search_query": search_q}


def answer_stream(question: str, k: int = 6, session_id: str | None = None,
                  history: list[dict] | None = None, matiere: str | None = None,
                  strict: bool = False,
                  attachment_ids: list[str] | None = None):
    """Générateur NDJSON : {"sources":[…]} puis {"delta":"…"}* puis {"done":true}.
    `history` explicite -> mode sans état (voir answer())."""
    question = (question or "").strip()
    if not question:
        yield json.dumps({"sources": []}) + "\n"
        yield json.dumps({"done": True}) + "\n"
        return
    if not _stack_ready():
        yield json.dumps({"sources": []}) + "\n"
        yield json.dumps({"delta": _STACK_DOWN_MSG}, ensure_ascii=False) + "\n"
        yield json.dumps({"done": True}) + "\n"
        return

    if history is not None:
        history, summary = _clean_history(history), ""
        session_id = None
    else:
        history, summary = _load_session(session_id)
    search_q = condense_question(history, question)
    search_q, _ar = search_query_for(search_q, _llm)
    hits = search_laws(search_q, limit=k, matiere=matiere, strict=strict)
    # Les pièces sont désignées par l'utilisateur, jamais devinées ; elles
    # restent bornées à leur session (un identifiant deviné n'ouvre rien).
    pieces = attachments.pour_contexte(session_id, attachment_ids or []) \
        if (session_id and attachment_ids) else []
    procs = (procedures.chercher(search_q)
             if procedures.veut_une_procedure(question + " " + search_q) else [])
    shown = _relevant(hits)          # nombre variable selon la pertinence réelle
    yield json.dumps({"sources": procedures.sources(procs) + _sources(shown),
                      "search_query": search_q},
                     ensure_ascii=False) + "\n"

    if not hits and not procs and not pieces:
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
                  "messages": _build_messages(question, hits, history, summary, procs,
                                             pieces),
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

    answer_text = "".join(full)
    warn = _quote_warning(answer_text, hits)
    if warn:
        answer_text += warn
        yield json.dumps({"delta": warn}, ensure_ascii=False) + "\n"
    # En streaming, le bandeau ne peut plus précéder un texte déjà parti ; on
    # l'émet en clôture, mais toujours de façon imposée.
    faute = _attribution_douteuse(answer_text, hits)
    if faute:
        answer_text += faute
        yield json.dumps({"delta": faute}, ensure_ascii=False) + "\n"
    bandeau = _bandeau_version(hits, answer_text)
    if bandeau:
        answer_text += "\n\n" + bandeau
        yield json.dumps({"delta": "\n\n" + bandeau},
                         ensure_ascii=False) + "\n"
    # Liste DÉFINITIVE : uniquement les sources réellement mobilisées, et
    # aucune si le modèle déclare n'avoir rien trouvé — afficher des sources
    # inutilisées laissait croire à un ancrage qui n'existait pas.
    final = procedures.sources(procs) + _sources(_cited(shown, answer_text))
    yield json.dumps({"sources_final": final}, ensure_ascii=False) + "\n"
    _persist(session_id, question, answer_text, final)
    yield json.dumps({"done": True}) + "\n"
