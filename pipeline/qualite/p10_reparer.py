# -*- coding: utf-8 -*-
"""Réparation des numéros d'article, sous condition de cohérence prouvée.

Personne ne relira les propositions une à une. Le jugement humain est donc
remplacé par une épreuve objective, appliquée document par document :

    QUALITÉ DE SUITE = part des numéros d'article qui ont un voisin immédiat.

Un code numérote en continu : 1, 2, 3… Chaque numéro y a donc un voisin. Un
numéro corrompu — « 84264 » — n'en a aucun. Réparer doit faire monter cette
part ; si elle stagne ou baisse, la réparation est refusée pour ce document.

Le corpus d'origine n'est jamais modifié : la sortie est un fichier distinct.
"""
import collections, json, re, sys

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl"
SORTIE = C + ".repare"
JOURNAL = r"Y:\adala-project\evaluation_20260821\forensique\journal_reparation.tsv"
NOTE = re.compile(r"(\d{1,3})\s*-\s*(?:تم|تمت|المرسوم|الظهير|القانون|الجريدة|أضيف|نسخ|غير)")
# Le suffixe d'un article « bis » s'écrit tantôt « 618-3 », tantôt
# « 17.1 ». L'ignorer ferait tomber deux articles distincts sous la
# même étiquette — constaté sur 21 cas au premier passage.
ETIQ = re.compile(r"^\s*(?:المادة|الفصل)\s*(\d{1,})([-.]\d{1,3})?")


def num_de(a):
    m = re.search(r"(\d{1,})", str(a or ""))
    return int(m.group(1)) if m else None


def qualite_suite(nums):
    """Part des numéros ayant un voisin immédiat. 1.0 = suite parfaite."""
    ens = set(nums)
    if len(ens) < 3:
        return None
    avec = sum(1 for v in ens if (v - 1) in ens or (v + 1) in ens)
    return avec / len(ens)


# ── regroupement par document ───────────────────────────────────────────
docs = collections.defaultdict(list)
for i, line in enumerate(open(C, encoding="utf-8")):
    r = json.loads(line)
    docs[r.get("file") or ""].append((i, r))

corrections = {}          # index de ligne -> nouvelle étiquette
stats = collections.Counter()
journal = []

for f, frags in docs.items():
    frags.sort(key=lambda x: (x[1].get("chunk") if isinstance(x[1].get("chunk"), int) else 0))
    presents = {num_de(r.get("article")) for _, r in frags} - {None}
    if not presents:
        continue

    sains = [(k, num_de(r.get("article")))
             for k, (_, r) in enumerate(frags)
             if num_de(r.get("article")) is not None
             and len(str(num_de(r.get("article")))) <= 3]

    propositions = []
    for k, (idx, r) in enumerate(frags):
        a = str(r.get("article") or "")
        m = re.search(r"(\d{4,})", a)
        if not m:
            continue
        val = int(m.group(1))
        # numéro élevé mais authentique : il a un voisin dans le document
        if any((val + d) in presents for d in (-2, -1, 1, 2)):
            continue
        brut, t = m.group(1), r.get("text") or ""
        notes = set(NOTE.findall(t))
        entete = ETIQ.match(t)
        avant = apres = None
        for j, v in sains:
            if j < k:
                avant = v
            elif j > k and apres is None:
                apres = v
        cands = []
        for L in (1, 2, 3, 4):
            if L >= len(brut):
                continue
            suf, pre = brut[-L:], brut[:-L]
            if suf.startswith("0"):
                continue
            cands.append((int(suf), pre))
        utiles = avant is not None and apres is not None and apres > avant
        par_suite = [c for c in cands if utiles and avant <= c[0] <= apres]
        par_note = [c for c in cands if c[1] in notes]
        if len(par_suite) == 1 and par_suite[0] in par_note:
            retenu, conf = par_suite[0], "haute"
        elif len(par_suite) == 1:
            retenu, conf = par_suite[0], "moyenne"
        elif len(par_note) == 1 and (not par_suite or par_note[0] in par_suite):
            retenu, conf = par_note[0], "moyenne"
        else:
            stats["sans_conclusion"] += 1
            continue
        # Le suffixe « bis » vit déjà dans l'étiquette : « المادة 2112.1 »
        # porte le .1. Le relire dans le texte, moins fiable, faisait tomber
        # l'article 12.1 sur l'article 12.
        # Étiquette à plusieurs suffixes — « 41218-4-1 » : on ne sait pas si
        # le dernier groupe appartient à l'article ou à une note. Constaté sur
        # les articles antiterroristes 218-x du code pénal, où l'erreur aurait
        # fait dire à l'article 218-4 ce que dit le 218-1.
        if len(re.findall(r"[-.]\d{1,3}", a)) > 1:
            stats["suffixes_multiples"] += 1
            continue
        m_suf = re.search(r"\d[-.](\d{1,3})\s*$", a.strip())
        if m_suf:
            suffixe = a.strip()[m_suf.start(1) - 1:]
        elif entete and entete.group(2):
            suffixe = entete.group(2)
        else:
            suffixe = ""
        propositions.append((idx, brut, f"{retenu[0]}{suffixe}", retenu[0],
                             retenu[1], conf))

    if not propositions:
        continue

    # ── l'épreuve : la suite s'améliore-t-elle ? ────────────────────────
    avant_nums = [num_de(r.get("article")) for _, r in frags]
    avant_nums = [v for v in avant_nums if v is not None]
    remplace = {idx: n for idx, _, _, n, _, _ in propositions}
    apres_nums = []
    for idx, r in frags:
        v = remplace.get(idx, num_de(r.get("article")))
        if v is not None:
            apres_nums.append(v)
    qa, qb = qualite_suite(avant_nums), qualite_suite(apres_nums)
    if qa is None or qb is None or qb <= qa:
        stats["documents_refuses"] += 1
        journal.append((f[:60], len(propositions), f"{qa}", f"{qb}", "REFUSÉ"))
        continue

    # Deux numéros corrompus différents qui aboutissent au même article
    # signalent une résolution douteuse — sauf s'il s'agit du même article
    # étalé sur des fragments voisins. Dans le doute, on renonce aux deux.
    vers = collections.defaultdict(list)
    for idx, brut, nouveau, _, _, _ in propositions:
        vers[nouveau].append((idx, brut))
    suspects = {idx for nouveau, lst in vers.items() if len({b for _, b in lst}) > 1
                for idx, _ in lst}
    if suspects:
        propositions = [p for p in propositions if p[0] not in suspects]
        stats["ecartes_convergence"] += len(suspects)
        if not propositions:
            stats["documents_refuses"] += 1
            continue

    stats["documents_acceptes"] += 1
    stats["corrections"] += len(propositions)
    journal.append((f[:60], len(propositions), f"{qa:.3f}", f"{qb:.3f}", "accepté"))
    for idx, brut, nouveau, _, note, conf in propositions:
        corrections[idx] = nouveau

# ── écriture, dans un fichier distinct ──────────────────────────────────
etiquette = re.compile(r"^(\s*(?:المادة|الفصل)\s*)\d{1,}([-.]\d{1,3})?")
with open(C, encoding="utf-8") as src, open(SORTIE, "w", encoding="utf-8") as dst:
    for i, line in enumerate(src):
        if i in corrections:
            r = json.loads(line)
            ancien = str(r.get("article") or "")
            prefixe = "المادة" if "المادة" in ancien else "الفصل"
            r["article"] = f"{prefixe} {corrections[i]}"
            r["article_avant_reparation"] = ancien
            line = json.dumps(r, ensure_ascii=False) + "\n"
        dst.write(line)

with open(JOURNAL, "w", encoding="utf-8") as fh:
    fh.write("document\tcorrections\tqualite_avant\tqualite_apres\tdecision\n")
    for j in journal:
        fh.write("\t".join(str(x) for x in j) + "\n")

print(f"documents acceptés  : {stats['documents_acceptes']:,}")
print(f"documents refusés   : {stats['documents_refuses']:,}")
print(f"corrections appliquées : {stats['corrections']:,}")
print(f"cas sans conclusion    : {stats['sans_conclusion']:,}")
print(f"\ncorpus réparé : {SORTIE}")
print(f"journal       : {JOURNAL}")
print("\n=== gains de cohérence les plus nets ===")
for d, n, qa, qb, dec in sorted(
        [j for j in journal if j[4] == "accepté"],
        key=lambda x: -(float(x[3]) - float(x[2])))[:10]:
    print(f"  {float(qa):.2f} → {float(qb):.2f}  ({n:>4} corr.)  {d[:52]}")
