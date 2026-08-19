# -*- coding: utf-8 -*-
"""Câblage du volet procédures dans answer.py.

Les fiches ne traversent PAS le circuit des lois : `_relevant` les jugerait sur
un score RRF qu'elles n'ont pas, et `_cited` chercherait un numéro d'article
qu'une marche à suivre ne porte pas. Elles voyagent donc dans une liste à part,
posée en tête du contexte, et deviennent des sources de plein droit.
"""
import io
import re
import shutil

SRC = "/workspace/aiocr/rag/answer.py"
shutil.copy(SRC, SRC + ".bak-procedures")
s = io.open(SRC, encoding="utf-8").read()


def sub1(vieux, neuf):
    global s
    assert s.count(vieux) == 1, f"ancrage introuvable ou ambigu : {vieux[:60]!r}"
    s = s.replace(vieux, neuf, 1)


# 1. import
sub1("from rag import memory\n", "from rag import memory\nfrom rag import procedures\n")

# 2. contexte : les fiches d'abord, puis les textes qui les fondent
sub1("def _build_context(hits: list[dict]) -> str:\n    parts = []",
     "def _build_context(hits: list[dict], procs: list[dict] | None = None) -> str:\n"
     "    parts = []\n"
     "    # La marche à suivre passe avant les textes : c'est la réponse à la\n"
     "    # question posée, les articles n'en sont que le fondement.\n"
     "    bloc = procedures.bloc_procedures(procs or [])\n"
     "    if bloc:\n"
     "        parts.append(bloc)")

# 3. messages
sub1("def _build_messages(question: str, hits: list[dict],\n"
     "                    history: list[dict], summary: str) -> list[dict]:",
     "def _build_messages(question: str, hits: list[dict],\n"
     "                    history: list[dict], summary: str,\n"
     "                    procs: list[dict] | None = None) -> list[dict]:")
sub1("_build_context(hits)", "_build_context(hits, procs)")

# 4. answer() — recherche, garde-fou, contexte, sources
sub1("    hits = search_laws(search_q, limit=k, matiere=matiere, strict=strict)\n"
     "    if not hits:\n"
     "        return {",
     "    hits = search_laws(search_q, limit=k, matiere=matiere, strict=strict)\n"
     "    # L'intention se lit sur la question ET sur sa reformulation : un\n"
     "    # « et ensuite ? » ne porte le mot « مسطرة » que dans la seconde.\n"
     "    procs = (procedures.chercher(search_q)\n"
     "             if procedures.veut_une_procedure(question + \" \" + search_q) else [])\n"
     "    if not hits and not procs:\n"
     "        return {")
sub1("\"messages\": _build_messages(question, hits, history, summary),\n"
     "                  \"stream\": False,",
     "\"messages\": _build_messages(question, hits, history, summary, procs),\n"
     "                  \"stream\": False,")
sub1("    sources = _sources(_cited(_relevant(hits), text))",
     "    # les fiches ne subissent ni le filtre de pertinence ni celui des\n"
     "    # citations : elles n'ont ni score RRF ni numéro d'article à repérer\n"
     "    sources = procedures.sources(procs) + _sources(_cited(_relevant(hits), text))")

# 5. answer_stream() — mêmes points
sub1("    hits = search_laws(search_q, limit=k, matiere=matiere, strict=strict)\n"
     "    shown = _relevant(hits)",
     "    hits = search_laws(search_q, limit=k, matiere=matiere, strict=strict)\n"
     "    procs = (procedures.chercher(search_q)\n"
     "             if procedures.veut_une_procedure(question + \" \" + search_q) else [])\n"
     "    shown = _relevant(hits)")
sub1("    yield json.dumps({\"sources\": _sources(shown), \"search_query\": search_q},",
     "    yield json.dumps({\"sources\": procedures.sources(procs) + _sources(shown),\n"
     "                      \"search_query\": search_q},")
sub1("    if not hits:\n"
     "        yield json.dumps(\n"
     "            {\"delta\": \"لم أعثر",
     "    if not hits and not procs:\n"
     "        yield json.dumps(\n"
     "            {\"delta\": \"لم أعثر")
sub1("\"messages\": _build_messages(question, hits, history, summary),\n"
     "                  \"stream\": True,",
     "\"messages\": _build_messages(question, hits, history, summary, procs),\n"
     "                  \"stream\": True,")
sub1("    final = _sources(_cited(shown, answer_text))",
     "    final = procedures.sources(procs) + _sources(_cited(shown, answer_text))")

io.open(SRC, "w", encoding="utf-8").write(s)
print("answer.py câblé — sauvegarde : answer.py.bak-procedures")
