"""
API publique /v1 : native (citations structurées) + compatible OpenAI.

Compatible OpenAI (`/v1/chat/completions`, `/v1/models`) : n'importe quel outil
parlant le standard OpenAI (Open WebUI, SDK openai en tout langage, LibreChat…)
se branche sur NOTRE RAG juridique en changeant base_url + api_key. Aucune
donnée ne part chez OpenAI — seul le dialecte est imité. Le client renvoie son
historique à chaque appel (mode sans état) ; la condensation des questions de
suivi fonctionne à partir de cet historique.

Native (`/v1/chat`) : mêmes réponses avec `sources` structurées de premier rang
{law, article, file, score, excerpt} + mémoire de session côté serveur.
Streaming des deux en SSE (`text/event-stream`).
"""
import json
import time
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from api.auth import require_api_key
from rag.answer import answer as rag_answer, answer_stream as rag_answer_stream

MODEL_ID = "adala-legal"
router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


# ══════════════════════════════════════════════════════════════════════════
#  Schémas
# ══════════════════════════════════════════════════════════════════════════
class OAIMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str
    content: str | list | None = None

    def text(self) -> str:
        """Aplatit le format multimodal OpenAI ([{type:'text',text:…}])."""
        if isinstance(self.content, str):
            return self.content
        if isinstance(self.content, list):
            return " ".join(p.get("text", "") for p in self.content
                            if isinstance(p, dict) and p.get("type") == "text")
        return ""


class OAIChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")   # tolère tous les champs OpenAI
    model: str = MODEL_ID
    messages: list[OAIMessage]
    stream: bool = False


class NativeChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str
    k: int = 6
    session_id: str | None = None
    stream: bool = False


# ══════════════════════════════════════════════════════════════════════════
#  Aides
# ══════════════════════════════════════════════════════════════════════════
def _split_history(messages: list[OAIMessage]) -> tuple[str, list[dict]]:
    """Dernier message utilisateur = question ; le reste = historique.
    Les messages system du client sont ignorés (notre prompt système fait foi)."""
    turns = [{"role": m.role, "content": m.text()}
             for m in messages if m.role in ("user", "assistant") and m.text()]
    question = ""
    for i in range(len(turns) - 1, -1, -1):
        if turns[i]["role"] == "user":
            question = turns[i]["content"]
            turns = turns[:i]
            break
    return question, turns


def _sources_block(sources: list[dict]) -> str:
    """Bloc «📚 المصادر» ajouté au texte (rendu par tout client OpenAI)."""
    if not sources:
        return ""
    lines = []
    for i, s in enumerate(sources, 1):
        art = f"المادة/الفصل {s['article']} — " if s.get("article") else ""
        lines.append(f"{i}. {art}{s.get('law', '')}")
    return "\n\n---\n📚 **المصادر:**\n" + "\n".join(lines)


def _completion_obj(content: str, sources: list[dict], finish: str = "stop") -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [{"index": 0, "finish_reason": finish,
                     "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "sources": sources,                     # extension non-standard (ignorée sinon)
    }


def _chunk_obj(cid: str, created: int, delta: dict, finish: str | None = None) -> str:
    return "data: " + json.dumps({
        "id": cid, "object": "chat.completion.chunk", "created": created,
        "model": MODEL_ID,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }, ensure_ascii=False) + "\n\n"


def _consume(gen):
    """Consomme le générateur NDJSON interne -> (texte, sources)."""
    text, sources = [], []
    for line in gen:
        obj = json.loads(line)
        if "sources" in obj:
            sources = obj["sources"]
        elif "delta" in obj:
            text.append(obj["delta"])
    return "".join(text), sources


# ══════════════════════════════════════════════════════════════════════════
#  Endpoints compatibles OpenAI
# ══════════════════════════════════════════════════════════════════════════
@router.get("/models")
def list_models():
    """Découverte des modèles (Open WebUI appelle ceci au branchement)."""
    return {"object": "list",
            "data": [{"id": MODEL_ID, "object": "model",
                      "created": int(time.time()), "owned_by": "adala"}]}


@router.post("/chat/completions")
def chat_completions(req: OAIChatRequest):
    question, history = _split_history(req.messages)
    if not question:
        return _completion_obj("لم أستلم سؤالاً.", [])

    if not req.stream:
        text, sources = _consume(rag_answer_stream(question, history=history))
        return _completion_obj(text + _sources_block(sources), sources)

    def sse():
        cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        yield _chunk_obj(cid, created, {"role": "assistant", "content": ""})
        sources: list[dict] = []
        for line in rag_answer_stream(question, history=history):
            obj = json.loads(line)
            if "sources" in obj:
                sources = obj["sources"]
            elif "delta" in obj:
                yield _chunk_obj(cid, created, {"content": obj["delta"]})
        blk = _sources_block(sources)
        if blk:
            yield _chunk_obj(cid, created, {"content": blk})
        yield _chunk_obj(cid, created, {}, finish="stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")


# ══════════════════════════════════════════════════════════════════════════
#  Endpoint natif v1 (citations structurées + sessions serveur)
# ══════════════════════════════════════════════════════════════════════════
@router.post("/chat")
def native_chat(req: NativeChatRequest):
    if not req.stream:
        return rag_answer(req.question, k=req.k, session_id=req.session_id)

    def sse():
        for line in rag_answer_stream(req.question, k=req.k,
                                      session_id=req.session_id):
            yield "data: " + line.rstrip("\n") + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")
