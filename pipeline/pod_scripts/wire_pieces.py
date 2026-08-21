# -*- coding: utf-8 -*-
"""Câblage des pièces jointes dans answer.py.

Les pièces suivent le même chemin que les fiches de procédure : une liste à
part, posée en tête du contexte, qui ne traverse ni `_relevant` ni `_cited`.
Elles n'ont ni score de pertinence à comparer ni numéro d'article à repérer
dans la réponse — et surtout, elles ne sont pas des sources de droit. Les
mêler aux articles inviterait le modèle à les citer comme une autorité.

Contrairement aux fiches, elles ne sont pas cherchées : c'est l'utilisateur
qui désigne les documents à lire, la question n'a pas à être interprétée.
"""
import io
import shutil
import sys

# Un chemin peut être passé en argument : c'est ainsi que le câblage est
# éprouvé sur une copie avant d'être appliqué au pod.
SRC = sys.argv[1] if len(sys.argv) > 1 else "/workspace/aiocr/rag/answer.py"
shutil.copy(SRC, SRC + ".bak-pieces")
s = io.open(SRC, encoding="utf-8").read()


def sub1(vieux, neuf):
    global s
    assert s.count(vieux) == 1, "ancrage introuvable ou ambigu : " + vieux[:60]
    s = s.replace(vieux, neuf, 1)


# 1. import
sub1("from rag import procedures\n",
     "from rag import procedures\nfrom services import attachments\n")

# 2. contexte : les faits du dossier avant la marche à suivre et les textes
sub1("    bloc = procedures.bloc_procedures(procs or [])\n"
     "    if bloc:\n"
     "        parts.append(bloc)",
     "    # Les pièces du dossier viennent en premier : elles portent les faits\n"
     "    # sur lesquels la question se pose, les textes n'arrivent qu'ensuite.\n"
     "    bloc_p = attachments.bloc_pieces(pieces or [])\n"
     "    if bloc_p:\n"
     "        parts.append(bloc_p)\n"
     "    bloc = procedures.bloc_procedures(procs or [])\n"
     "    if bloc:\n"
     "        parts.append(bloc)")

sub1("def _build_context(hits: list[dict], procs: list[dict] | None = None) -> str:",
     "def _build_context(hits: list[dict], procs: list[dict] | None = None,\n"
     "                   pieces: list[dict] | None = None) -> str:")
sub1("_build_context(hits, procs)", "_build_context(hits, procs, pieces)")

# 3. messages
sub1("                    procs: list[dict] | None = None) -> list[dict]:",
     "                    procs: list[dict] | None = None,\n"
     "                    pieces: list[dict] | None = None) -> list[dict]:")

# 4. signatures publiques
for ancienne in ("def answer(question: str, k: int = 6, session_id: str | None = None,",
                 "def answer_stream(question: str, k: int = 6, session_id: str | None = None,"):
    sub1(ancienne + "\n", ancienne + "\n           _PIECES_MARQUE\n")
s = s.replace(
    "           _PIECES_MARQUE\n"
    "           history: list[dict] | None = None, matiere: str | None = None,\n"
    "           strict: bool = False) -> dict:",
    "           history: list[dict] | None = None, matiere: str | None = None,\n"
    "           strict: bool = False,\n"
    "           attachment_ids: list[str] | None = None) -> dict:")
s = s.replace(
    "           _PIECES_MARQUE\n"
    "                  history: list[dict] | None = None, matiere: str | None = None,\n"
    "                  strict: bool = False):",
    "                  history: list[dict] | None = None, matiere: str | None = None,\n"
    "                  strict: bool = False,\n"
    "                  attachment_ids: list[str] | None = None):")
assert "_PIECES_MARQUE" not in s, "signature non reprise"

# 5. chargement des pièces, dans les deux points d'entrée
ancre = ("    procs = (procedures.chercher(search_q)\n"
         "             if procedures.veut_une_procedure(question + \" \" + search_q) else [])")
neuf = ("    # Les pièces sont désignées par l'utilisateur, jamais devinées ; elles\n"
        "    # restent bornées à leur session (un identifiant deviné n'ouvre rien).\n"
        "    pieces = attachments.pour_contexte(session_id, attachment_ids or []) \\\n"
        "        if (session_id and attachment_ids) else []\n" + ancre)
assert s.count(ancre) == 2, "les deux points d'entrée devraient porter cet ancrage"
s = s.replace(ancre, neuf)

# 6. une question sans texte trouvé reste recevable si une pièce est jointe
sub1("    if not hits and not procs:\n        return {",
     "    if not hits and not procs and not pieces:\n        return {")
sub1("    if not hits and not procs:\n        yield json.dumps(",
     "    if not hits and not procs and not pieces:\n        yield json.dumps(")

# 7. transmission aux messages
sub1("_build_messages(question, hits, history, summary, procs),\n"
     "                  \"stream\": False,",
     "_build_messages(question, hits, history, summary, procs,\n"
     "                                             pieces),\n"
     "                  \"stream\": False,")
sub1("_build_messages(question, hits, history, summary, procs),\n"
     "                  \"stream\": True,",
     "_build_messages(question, hits, history, summary, procs,\n"
     "                                             pieces),\n"
     "                  \"stream\": True,")

io.open(SRC, "w", encoding="utf-8").write(s)
print("answer.py câblé — sauvegarde : answer.py.bak-pieces")
