# -*- coding: utf-8 -*-
"""Datation des textes : qui abroge quoi, qui est modifié par quoi.

Le piège, révélé par le sondage : « كما وقع تغييره وتتميمه » apparaît surtout
dans des ARRÊTS qui citent une loi. Marquer le document qui contient la phrase
reviendrait à déclarer l'arrêt modifié. On extrait donc des RELATIONS, pas des
mots-clés :

    dans un texte de loi D, « ينسخ المرسوم رقم 2.80.813 »
        -> D abroge 2.80.813        (on marque 2.80.813, pas D)

    dans l'en-tête d'une loi D, « كما تم تغييره بالقانون رقم 24.01 »
        -> D est modifié par 24.01  (on marque D)

Deux garde-fous :
  - seuls les textes législatifs sont sources de relations, jamais la
    jurisprudence, qui ne fait que citer ;
  - la cible doit être identifiée par un NUMÉRO présent dans le corpus, sinon
    on ne marque rien : un texte inconnu ne se déduit pas.

Exécution en deux temps : --dry pour compter et échantillonner, puis écriture.
"""
import collections
import json
import re
import sys

CORPUS = "/workspace/data/laws_corpus_v2.jsonl"
DRY = "--dry" in sys.argv

# Numéros de textes marocains : 1.74.447, 2.80.813, 58.25, 24.01, 011.71…
NUM = r"\d{1,3}(?:\.\d{2,3}){1,2}"

# « ينسخ / تنسخ / يُنسخ … رقم X » — le document courant abroge X.
# La cible doit être désignée comme un TEXTE (قانون / ظهير / مرسوم / قرار) :
# sans cela, « تلغى … حساب السلفات رقم 45.14 » marquait la loi 45.14 comme
# abrogée alors qu'il s'agissait d'un compte du Trésor portant le même numéro.
TYPE = r"(?:القانون|قانون|الظهير|ظهير|المرسوم|مرسوم|القرار|قرار)"
ABROGE = re.compile(
    r"(?:ينسخ|تنسخ|يُنسخ|تُنسخ|نسخت|تُلغى|تلغى|ألغيت|يلغى)"
    r"[^.؛]{0,150}?" + TYPE + r"[^.؛]{0,40}?رقم\s*(" + NUM + r")")

# « كما تم/وقع تغييره … بالقانون رقم Y » — le document courant est modifié par Y.
MODIFIE = re.compile(
    r"كما\s+(?:تم|وقع)\s+(?:تغيير|تعديل)[^.؛]{0,80}?"
    r"(?:بالقانون|بالظهير|بالمرسوم)[^.؛]{0,40}?رقم\s*(" + NUM + r")")

NUM_RE = re.compile(NUM)


def numeros_du_nom(name: str) -> set[str]:
    """Numéros portés par le nom de fichier — c'est ainsi qu'on relie une
    relation à un document réel du corpus."""
    return set(NUM_RE.findall(name))


# ── Passe 1 : cartographier les numéros présents dans le corpus ──────────
par_numero: dict[str, set[str]] = collections.defaultdict(set)
fichiers: set[str] = set()
lignes = 0
for line in open(CORPUS, encoding="utf-8"):
    r = json.loads(line)
    f = r.get("file") or ""
    lignes += 1
    if f in fichiers:
        continue
    fichiers.add(f)
    for n in numeros_du_nom(f):
        par_numero[n].add(f)
print(f"{lignes} fragments, {len(fichiers)} documents, "
      f"{len(par_numero)} numéros identifiables", flush=True)

# ── Passe 2 : extraire les relations depuis les seuls textes de loi ──────
abroge_par: dict[str, set[str]] = collections.defaultdict(set)   # cible -> sources
partiel_par: dict[str, set[str]] = collections.defaultdict(set)  # abrogation partielle
modifie_par: dict[str, set[str]] = collections.defaultdict(set)  # doc -> textes
exemples_a, exemples_m = [], []

for line in open(CORPUS, encoding="utf-8"):
    r = json.loads(line)
    col = r.get("collection") or ""
    f = r.get("file") or ""
    # la jurisprudence cite, elle ne légifère pas
    if "juris" in col or "juris" in f.lower():
        continue
    t = r.get("text") or ""
    if not t:
        continue

    propres = numeros_du_nom(f)
    for m in ABROGE.finditer(t):
        cible = m.group(1)
        if cible in propres:          # un texte ne s'abroge pas lui-même
            continue
        if cible not in par_numero:
            continue
        # Abrogation PARTIELLE : « تنسخ أحكام الفصل 14 من … » ne supprime qu'un
        # article. Marquer tout le code comme abrogé serait faux et alarmant —
        # c'est ce qui arrivait à la مجموعة القانون الجنائي pour son article 14.
        partielle = re.search(r"(?:الفصل|المادة|المواد|الفصول|الفقرة|البند)\s*[0-9٠-٩]",
                              m.group(0)) is not None
        for fich in par_numero[cible]:
            if partielle:
                partiel_par[fich].add(f)
            else:
                abroge_par[fich].add(f)
            if len(exemples_a) < 6:
                exemples_a.append((f[:34], cible,
                                   re.sub(r"\s+", " ", m.group(0))[:100]))

    for m in MODIFIE.finditer(t):
        par = m.group(1)
        if par in propres:
            continue
        modifie_par[f].add(par)
        if len(exemples_m) < 6:
            exemples_m.append((f[:34], par,
                               re.sub(r"\s+", " ", m.group(0))[:100]))

print(f"\ndocuments visés par une abrogation : {len(abroge_par)}")
for f, srcs in list(abroge_par.items())[:5]:
    print(f"   {f[:52]:54s} <- {', '.join(list(srcs)[:2])[:44]}")
print("\nexemples de phrases d'abrogation :")
for f, c, s in exemples_a:
    print(f"   [{c}] {s}")

print(f"\ndocuments se déclarant modifiés : {len(modifie_par)}")
for f, c, s in exemples_m:
    print(f"   [{c}] {s}")

if DRY:
    print("\n(passe à blanc — rien n'a été écrit)")
    raise SystemExit

# ── Passe 3 : écrire les statuts ────────────────────────────────────────
n_abr = n_mod = 0
out = []
for line in open(CORPUS, encoding="utf-8"):
    r = json.loads(line)
    f = r.get("file") or ""
    if f in abroge_par:
        r["status"] = "possibly_abrogated"
        r["replaced_by"] = sorted(abroge_par[f])[:3]
        n_abr += 1
    elif (f in modifie_par or f in partiel_par) and r.get("status", "current") == "current":
        r["status"] = "check_amendments"
        r["pending_amendments"] = sorted(
            set(modifie_par.get(f, set())) | set(partiel_par.get(f, set())))[:5]
        n_mod += 1
    out.append(json.dumps(r, ensure_ascii=False))

with open(CORPUS, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out) + "\n")
print(f"\nfragments marqués abrogés : {n_abr}")
print(f"fragments marqués à vérifier (modifiés) : {n_mod}")
