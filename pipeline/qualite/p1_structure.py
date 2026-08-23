# -*- coding: utf-8 -*-
"""Passe 1 — intégrité structurelle : champs, types, plages, cohérences."""
import collections, json, re, sys

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl"
CHAMPS = collections.Counter()
types_incoherents = collections.Counter()
anomalies = collections.Counter()
ex = collections.defaultdict(list)

def note(cle, r, extra=""):
    anomalies[cle] += 1
    if len(ex[cle]) < 3:
        ex[cle].append(((r.get("file") or "")[:44], r.get("chunk"),
                        (r.get("article") or ""), extra))

n = 0
lignes_illisibles = 0
for brut in open(C, encoding="utf-8"):
    n += 1
    try:
        r = json.loads(brut)
    except Exception:
        lignes_illisibles += 1
        continue
    for k, v in r.items():
        CHAMPS[k] += 1
        types_incoherents[(k, type(v).__name__)] += 1

    t = r.get("text")
    if not isinstance(t, str):
        note("texte_non_chaine", r, type(t).__name__)
        continue
    if not r.get("file"):
        note("sans_fichier", r)
    ch = r.get("chunk")
    if ch is None:
        note("sans_chunk", r)
    elif isinstance(ch, int) and ch < 0:
        note("chunk_negatif", r, str(ch))
    pg = r.get("page")
    if pg is not None:
        try:
            p = int(pg)
            if p <= 0:      note("page_nulle_ou_negative", r, str(pg))
            elif p > 5000:  note("page_invraisemblable", r, str(pg))
        except (TypeError, ValueError):
            note("page_non_numerique", r, repr(pg)[:20])
    a = str(r.get("article") or "").strip()
    if a and a not in ("None",):
        m = re.search(r"(\d{1,5})", a)
        if not m:
            note("article_sans_chiffre", r, a[:30])
        else:
            num = int(m.group(1))
            if num == 0:        note("article_zero", r, a[:20])
            elif num > 2000:    note("article_hors_plage", r, a[:20])
    st = r.get("status", "current")
    if st not in ("current", "check_amendments", "possibly_abrogated",
                  "consolidated"):
        note("statut_inconnu", r, str(st)[:24])
    if st == "possibly_abrogated" and not r.get("replaced_by"):
        note("abroge_sans_texte_naskh", r)
    if st == "check_amendments" and not r.get("pending_amendments"):
        note("modifie_sans_reference", r)

print(f"lignes            : {n:,}")
print(f"lignes illisibles : {lignes_illisibles:,}")
print()
print("=== champs présents (sur combien de lignes) ===")
for k, v in CHAMPS.most_common(18):
    print(f"  {k:<22} {v:>9,}  ({v*100//n} %)")
print()
print("=== champs à type variable (signe de pipelines divergents) ===")
par_champ = collections.defaultdict(set)
for (k, t), c in types_incoherents.items():
    par_champ[k].add((t, c))
for k, ts in sorted(par_champ.items()):
    if len(ts) > 1:
        print(f"  {k:<22} " + ", ".join(f"{t}={c:,}" for t, c in sorted(ts)))
print()
print("=== anomalies structurelles ===")
if not anomalies:
    print("  aucune")
for k, v in anomalies.most_common():
    print(f"  {k:<28} {v:>9,}")
    for f, ch, art, extra in ex[k]:
        print(f"        ex. {f} chunk={ch} art={str(art)[:16]} {extra}")
