# -*- coding: utf-8 -*-
"""Passe 12 — l'étiquette dit-elle la même chose que l'en-tête imprimé ?

Le champ `article` sert à l'ancrage : quand un juriste demande « المادة 204 »,
c'est lui qu'on interroge. S'il ne correspond pas au numéro réellement imprimé
en tête du fragment, l'article est rangé sous une fausse référence — et une
autre question ramènera ce texte à tort.
"""
import collections, json, re

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl.repare.signale"
ENTETE = re.compile(r"^\s*(?:المادة|الفصل)\s*([\d]{1,5})(?:\s*(?:مكرر|bis))?")
accord = desaccord = sans_entete = sans_etiquette = 0
par_doc = collections.Counter()
ex = []

for line in open(C, encoding="utf-8"):
    r = json.loads(line)
    t = r.get("text") or ""
    a = str(r.get("article") or "")
    m_e = ENTETE.match(t)
    m_a = re.search(r"(\d{1,5})", a)
    if not m_a:
        sans_etiquette += 1
        continue
    if not m_e:
        sans_entete += 1
        continue
    if m_e.group(1) == m_a.group(1):
        accord += 1
    else:
        desaccord += 1
        f = (r.get("file") or "")[:56]
        par_doc[f] += 1
        if len(ex) < 10:
            ex.append((a, m_e.group(1), f, re.sub(r"\s+", " ", t)[:110]))

tot = accord + desaccord
print(f"fragments à étiquette ET en-tête lisibles : {tot:,}")
print(f"  en accord    : {accord:,}  ({accord*100//max(tot,1)} %)")
print(f"  EN DÉSACCORD : {desaccord:,}  ({desaccord*100/max(tot,1):.2f} %)")
print(f"fragments sans en-tête imprimé            : {sans_entete:,}")
print(f"fragments sans étiquette                  : {sans_etiquette:,}")
print()
print("=== désaccords, sur pièces ===")
for a, e, f, t in ex:
    print(f"  étiquette «{a}»  vs  en-tête «{e}»   {f[:44]}")
    print(f"      {t[:100]}")
print()
print("=== documents les plus touchés ===")
for f, n in par_doc.most_common(10):
    print(f"  {n:>5}  {f}")
