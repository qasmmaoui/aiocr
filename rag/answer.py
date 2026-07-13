"""
Chat juridique (RAG grounded) :
  question -> récupère les articles pertinents (search_laws)
           -> le modèle de raisonnement (Qwen) rédige une réponse ancrée + citations.

La réponse est STRICTEMENT basée sur les textes récupérés (anti-hallucination).
"""
import requests

from core.config import OLLAMA_BASE_URL
from rag.search_laws import search_laws

CHAT_MODEL = "qwen2.5:14b"

SYSTEM_PROMPT = (
    "أنت مساعد قانوني مغربي متخصص في القانون التجاري. "
    "أجب على سؤال المستخدم بالاعتماد الحصري على «النصوص القانونية» المقدَّمة في السياق أدناه. "
    "اذكر رقم المادة واسم القانون عند كل استشهاد (مثال: المادة 1 من قانون شركات المساهمة). "
    "إذا لم تجد الجواب ضمن النصوص المقدَّمة، فصرّح بوضوح: «لم أعثر على نص قانوني مطبّق ضمن المدونة المتاحة» "
    "ولا تخترع أي معلومة أو مادة. أجب بالعربية الفصحى بأسلوب واضح ومنظَّم."
)


def _build_context(hits: list[dict]) -> str:
    return "\n\n".join(
        f"[{i + 1}] القانون: {h.get('law', '')}\n{h.get('text', '')}"
        for i, h in enumerate(hits)
    )


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
        f"السياق (نصوص قانونية مستخرَجة من القانون التجاري المغربي):\n"
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
                "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 1200},
            },
            timeout=600,
        )
        r.raise_for_status()
        text = r.json()["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        text = f"تعذّر توليد الإجابة (نموذج الاستدلال غير جاهز؟): {e}"

    sources = [
        {
            "law": h.get("law", ""),
            "file": h.get("file", ""),
            "score": round(float(h.get("score", 0)), 3),
            "excerpt": (h.get("text", "") or "")[:400],
        }
        for h in hits
    ]
    return {"answer": text, "sources": sources}
