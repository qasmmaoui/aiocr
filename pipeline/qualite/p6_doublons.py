# -*- coding: utf-8 -*-
"""Passe 6 — doublons, troncatures, désactivations, contamination."""
import collections, hashlib, json, re

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl"
DIA = re.compile(r"[\u064B-\u0652\u0670]")

def norm(t):
    t = DIA.sub("", t or "")
    return re.sub(r"[^\u0621-\u064A0-9]", "", t)

vus = collections.defaultdict(list)
desactives = collections.Counter()
tronques = 0
ex_tronq = []
n = 0
for line in open(C, encoding="utf-8"):
    r = json.loads(line)
    n += 1
    t = r.get("text") or ""
    if r.get("disabled"):
        desactives[str(r.get("disabled_reason"))[:40]] += 1
    cle = norm(t)
    if len(cle) >= 200:
        vus[hashlib.md5(cle.encode()).hexdigest()].append(
            ((r.get("file") or "")[:44], r.get("chunk"), bool(r.get("disabled"))))
    # troncature : se termine au milieu d'un mot arabe, sans ponctuation
    s = t.rstrip()
    if len(s) > 300 and s and s[-1] not in ".؟!:؛»)\n" and re.match(r"[\u0621-\u064A]", s[-1]):
        tronques += 1
        if len(ex_tronq) < 3:
            ex_tronq.append(((r.get("file") or "")[:40], re.sub(r"\s+", " ", s)[-90:]))

groupes = {k: v for k, v in vus.items() if len(v) > 1}
frag_dupliques = sum(len(v) for v in groupes.values())
actifs_dupliques = sum(sum(1 for x in v if not x[2]) for v in groupes.values())
print(f"fragments                         : {n:,}")
print(f"fragments assez longs pour comparer: {sum(len(v) for v in vus.values()):,}")
print(f"groupes de doublons exacts        : {len(groupes):,}")
print(f"  fragments concernés             : {frag_dupliques:,}")
print(f"  dont ENCORE ACTIFS (non désactivés) : {actifs_dupliques:,}")
print()
print("=== désactivations en place ===")
for k, v in desactives.most_common():
    print(f"  {v:>6}  {k}")
print()
print("=== plus gros groupes de doublons actifs ===")
gros = sorted(((sum(1 for x in v if not x[2]), v) for v in groupes.values()),
              reverse=True, key=lambda z: z[0])[:5]
for k, v in gros:
    if k < 2: continue
    print(f"  {k} copies actives :")
    for f, ch, dis in v[:4]:
        print(f"      {f} chunk={ch}{' [désactivé]' if dis else ''}")
print()
print(f"=== fragments coupés en plein mot : {tronques:,} ({tronques*100//n} %) ===")
for f, fin in ex_tronq:
    print(f"  {f}")
    print(f"     …{fin}")
