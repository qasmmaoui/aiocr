"""
Chat juridique (RAG grounded) :
  question -> récupère les articles pertinents (search_laws)
           -> le modèle de raisonnement (Qwen) rédige une réponse ancrée + citations.

La réponse est STRICTEMENT basée sur les textes récupérés (anti-hallucination).
"""
import json
import re
import requests

from core.config import OLLAMA_BASE_URL
from rag.search_laws import search_laws
from rag import store

try:
    from qdrant_client.models import Filter, FieldCondition, MatchValue
except Exception:  # pragma: no cover
    Filter = None

CHAT_MODEL = "qwen2.5:72b"

# En-tête d'article RÉEL au début d'un chunk : « المادة 41 » / « الفصل 393 » / « المادة 1-41 ».
_HDR = re.compile(r"^\s*((?:المادة|الفصل)\s*[-\s]?\d+(?:\s*[-]\s*\d+)?)")
# Renvoi (pas un en-tête) : « المادة 316 من مدونة التجارة » / « ... من قانون ... ».
_XREF = re.compile(r"^\s*(?:المادة|الفصل)\s*[-\s]?\d+(?:\s*[-]\s*\d+)?\s*من\b")


def _real_header(t: str) -> str | None:
    """Renvoie l'en-tête d'article si le chunk COMMENCE par un vrai article
    (et non par un renvoi « المادة N من [autre code] »)."""
    if _XREF.match(t):
        return None
    m = _HDR.match(t)
    return m.group(1).strip() if m else None


def _expand(hit: dict, back: int = 4) -> str:
    """Remonte les chunks précédents (même fichier) jusqu'au vrai en-tête d'article,
    et l'injecte explicitement — sinon le modèle cite le numéro d'un renvoi
    (ex. « المادة 316 من مدونة التجارة ») au lieu du vrai article (ex. المادة 41)."""
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
        if hdr:                          # vrai en-tête trouvé → on s'arrête
            break
    body = ("\n".join(parts) + "\n" + txt) if parts else txt
    if hdr:
        body = f"(هذا المقطع جزء من «{hdr}»)\n" + body
    return body

SYSTEM_PROMPT = (
    "أنت مساعد قانوني مغربي خبير في مختلف فروع القانون المغربي: الجنائي، المسطرة الجنائية، التجاري، المدني وغيرها. "
    "اعتمد على وسم «المصدر» المرفق بكل مقطع لمعرفة القانون الذي ينتمي إليه، ولا تفترض أبداً أن النص من القانون التجاري. "
    "أجب على سؤال المستخدم بالاعتماد الحصري على «النصوص القانونية» المقدَّمة في السياق أدناه. "
    "اذكر رقم المادة واسم القانون عند كل استشهاد (معتمداً وسم «المصدر»؛ وإذا ورد داخل النص «المادة X من مدونة التجارة» أو من قانون آخر فهي إحالة إلى قانون مختلف لا تُنسب إليها المقطع؛ ولا تخلط بين القوانين، ولأسئلة القانون الجنائي اعتمد نصوص القانون الجنائي أو المسطرة الجنائية لا التجاري). "
    "إذا لم تجد الجواب ضمن النصوص المقدَّمة، فصرّح بوضوح: «لم أعثر على نص قانوني مطبّق ضمن المدونة المتاحة» "
    "ولا تخترع أي معلومة أو مادة. وإذا أحال النص إلى قائمة طويلة من الفصول أو المواد فلا تسردها كلها إطلاقاً ولا تخترع أرقاماً متسلسلة، بل اكتفِ بذكر أنها محددة في المادة المعنية مع مثال أو مثالين. أجب بالعربية الفصحى بأسلوب واضح ومنظَّم."
)


def _build_context(hits: list[dict]) -> str:
    parts = []
    for i, h in enumerate(hits):
        art = h.get("article")
        art_lbl = f" — رقم المادة/الفصل: {art}" if art else ""
        parts.append(
            f"[مقطع {i + 1}] المصدر: {h.get('law', '')}{art_lbl}\nالنص: {_expand(h)}"
        )
    return "\n\n".join(parts)


def answer(question: str, k: int = 6) -> dict:
    question = (question or "").strip()
    if not question:
        return {"answer": "", "sources": []}

    hits = search_laws(question, limit=k)
    if not hits:
        return {
            "answer": "لم أعثر على نصوص قانونية ذات صلة بسؤالك في المدوّنة الحالية.",
            "sources": [],
        }

    user_msg = (
        f"السياق (نصوص قانونية من مختلف القوانين المغربية، كل مقطع مسبوق بوسم «المصدر» الذي يحدد القانون):\n"
        f"{_build_context(hits)}\n\n"
        f"السؤال: {question}"
    )

    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.2, "num_ctx": 16384, "num_predict": 1200,
                    "repeat_penalty": 1.25, "repeat_last_n": 256,
                },
            },
            timeout=600,
        )
        r.raise_for_status()
        text = r.json()["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        text = f"تعذّر توليد الإجابة (نموذج الاستدلال غير جاهز؟): {e}"

    sources = _sources(hits)
    return {"answer": text, "sources": sources}


def _sources(hits: list[dict]) -> list[dict]:
    return [
        {
            "law": h.get("law", ""),
            "file": h.get("file", ""),
            "score": round(float(h.get("score", 0)), 3),
            "excerpt": (h.get("text", "") or "")[:400],
        }
        for h in hits
    ]


def answer_stream(question: str, k: int = 6):
    """Générateur NDJSON : d'abord {"sources":[…]}, puis {"delta":"…"}*, puis {"done":true}."""
    question = (question or "").strip()
    if not question:
        yield json.dumps({"sources": []}) + "\n"
        yield json.dumps({"done": True}) + "\n"
        return

    hits = search_laws(question, limit=k)
    yield json.dumps({"sources": _sources(hits)}, ensure_ascii=False) + "\n"

    if not hits:
        yield json.dumps(
            {"delta": "لم أعثر على نصوص قانونية ذات صلة بسؤالك في المدوّنة الحالية."},
            ensure_ascii=False,
        ) + "\n"
        yield json.dumps({"done": True}) + "\n"
        return

    user_msg = (
        f"السياق (نصوص قانونية مستخرَجة):\n{_build_context(hits)}\n\nالسؤال: {question}"
    )
    try:
        with requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "stream": True,
                "options": {
                    "temperature": 0.2, "num_ctx": 16384, "num_predict": 1200,
                    "repeat_penalty": 1.25, "repeat_last_n": 256,
                },
            },
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
                    yield json.dumps({"delta": chunk}, ensure_ascii=False) + "\n"
                if obj.get("done"):
                    break
    except Exception as e:  # noqa: BLE001
        yield json.dumps({"delta": f"\n\n[تعذّر التوليد: {e}]"}, ensure_ascii=False) + "\n"
    yield json.dumps({"done": True}) + "\n"
