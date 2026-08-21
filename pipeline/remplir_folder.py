# -*- coding: utf-8 -*-
"""Rétablit le champ `folder` dans le corpus lexical.

Le filtrage par matière repose entièrement sur ce champ. Il est renseigné dans
les charges utiles Qdrant mais absent de la totalité du corpus JSONL — donc de
toutes les lignes issues de BM25. Résultat : dès qu'un utilisateur choisit une
matière, les résultats lexicaux, qui sont précisément ceux qui portent les
numéros d'articles exacts, sont classés hors matière et perdent le bonus.

Le dossier est déduit de l'arborescence des PDF sources, où chaque document
vit déjà sous sa matière. On apparie sur le nom de fichier, jamais sur une
ressemblance approximative : un rattachement erroné serait pire qu'un champ
vide, puisqu'il ferait taire un texte pertinent.
"""
import collections
import json
import os
import sys

RACINE = sys.argv[1] if len(sys.argv) > 1 else r"Y:\adala-project\adala_pdfs"
CORPUS = sys.argv[2] if len(sys.argv) > 2 else \
    r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl"
SORTIE = CORPUS + ".folders"


# Les codes fondamentaux ne vivent pas dans l'arborescence par matière : ils
# ont été ingérés depuis `laws/` ou `PMP_Textes`. Ce sont aussi les documents
# les plus consultés, donc les plus coûteux à laisser sans matière. La table
# est écrite à la main, document par document, plutôt que devinée : sur des
# textes de cette importance, un rattachement approximatif serait pire que
# l'absence de rattachement.
CODES = {
    "قانون-الالتزامات-والعقود.pdf": "المادة المدنية",
    "مدونة-التجارة-نسخة-نهائية-2.pdf": "المادة التجارية",
    "القانون-الجنائي.pdf": "المادة الجنائية",
    "قانون-المسطرة-الجنائية_compressed.pdf": "المادة الجنائية",
    "مدونة-المحاكم-المالية.pdf": "المادة المالية",
    "2-قانون-رقم-17.95-المتعلق-بشركات-المساهمة.pdf": "المادة التجارية",
    "5-القانون-رقم-17.97-المتعلق-بحماية-الملكية-الصناعية.pdf": "المادة التجارية",
}
# Le nouveau code de procédure civile est enregistré sous un nom dans le
# corpus et sous un autre dans l'arborescence : on le rattache par son numéro.
PAR_MOTIF = [
    ("1.26.07", "المادة المدنية"),          # loi 58.25, procédure civile 2026
    ("1.74.447", "المادة المدنية"),         # procédure civile 1974
    ("1.02.255", "المادة الجنائية"),        # procédure pénale
]
# La jurisprudence est rangée par chambre ; chaque chambre relève d'une
# matière, ce que `rag/matieres.py` sait déjà.
CHAMBRE_VERS_MATIERE = {
    "الغرفة الجنائية": "المادة الجنائية",
    "الغرفة المدنية": "المادة المدنية",
    "الغرفة التجارية": "المادة التجارية",
    "الغرفة الإدارية": "المادة الإدارية",
    "الغرفة الاجتماعية": "المادة الاجتماعية",
    "غرفة الأحوال الشخصية والميراث": "المادة الأسرية",
}


def index_jurisprudence(racine: str) -> dict[str, str]:
    """nom d'arrêt -> matière, déduite de la chambre qui l'a rendu."""
    out: dict[str, str] = {}
    if not os.path.isdir(racine):
        return out
    for chambre in os.listdir(racine):
        matiere = CHAMBRE_VERS_MATIERE.get(chambre)
        chemin = os.path.join(racine, chambre)
        if not matiere or not os.path.isdir(chemin):
            continue
        for f in os.listdir(chemin):
            out[f] = matiere
    return out


def index_dossiers(racine: str) -> dict[str, str]:
    """nom de fichier -> dossier de matière, en écartant les ambigus."""
    par_nom: dict[str, set] = collections.defaultdict(set)
    for dossier in os.listdir(racine):
        chemin = os.path.join(racine, dossier)
        if not os.path.isdir(chemin) or dossier.startswith("_"):
            continue
        for f in os.listdir(chemin):
            par_nom[f].add(dossier)
    # un fichier présent dans deux matières ne peut pas être tranché ici
    return {n: next(iter(d)) for n, d in par_nom.items() if len(d) == 1}


def base(nom: str) -> str:
    return os.path.basename(nom or "")


JURIS = os.environ.get(
    "JURIS_DIR",
    r"Y:dala-project\pod_backup_20260819\juris_partiel\juris")

carte = index_dossiers(RACINE)
carte.update(index_jurisprudence(JURIS))
carte.update(CODES)
print(f"{len(carte):,} fichiers rattachés à une matière unique", flush=True)


def matiere_de(nom_fichier: str) -> str | None:
    d = carte.get(base(nom_fichier))
    if d:
        return d
    for motif, mat in PAR_MOTIF:
        if motif in (nom_fichier or ""):
            return mat
    return None

remplis = deja = introuvables = 0
manquants: collections.Counter = collections.Counter()
with open(CORPUS, encoding="utf-8") as src, \
        open(SORTIE, "w", encoding="utf-8") as dst:
    for line in src:
        r = json.loads(line)
        if not r.get("folder"):
            d = matiere_de(r.get("file") or "")
            if d:
                r["folder"] = d
                remplis += 1
            else:
                introuvables += 1
                manquants[base(r.get("file") or "")[:60]] += 1
        else:
            deja += 1
        dst.write(json.dumps(r, ensure_ascii=False) + "\n")

total = remplis + deja + introuvables
print(f"fragments traités        : {total:,}")
print(f"  dossier rétabli        : {remplis:,}  ({remplis * 100 // total} %)")
print(f"  déjà renseigné         : {deja:,}")
print(f"  sans correspondance    : {introuvables:,}")
print(f"\nsortie : {SORTIE}")
if manquants:
    print("\nprincipaux fichiers non rattachés :")
    for nom, n in manquants.most_common(8):
        print(f"  {n:>6}x  {nom}")
