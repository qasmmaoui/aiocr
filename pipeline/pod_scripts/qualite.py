# -*- coding: utf-8 -*-
"""Contrôle lexical généralisé de la qualité d'extraction.

Le principe : le corpus est son propre dictionnaire. Sur 44 000 documents,
les mots réellement arabes reviennent des milliers de fois ; les débris
d'extraction, eux, sont uniques. On construit donc un lexique des tokens
fréquents, puis on mesure pour chaque document la part de son texte couverte
par ce lexique. Un document sain dépasse largement les 80 % ; un document
corrompu s'effondre.

Cette mesure attrape les DEUX familles rencontrées — mots retournés et
inversion lam/alef — sans qu'on ait à les décrire, et celles qu'on n'a pas
encore vues.
"""
import collections
import json
import re

CORPUS = '/workspace/data/laws_corpus_v2.jsonl'
TOK = re.compile(r'[؀-ۿ]{3,}')

freq = collections.Counter()
docs = collections.defaultdict(list)
for line in open(CORPUS, encoding='utf-8'):
    r = json.loads(line)
    t = r.get('text') or ''
    docs[r.get('file') or ''].append(t)
    freq.update(TOK.findall(t))

# Un mot vu dans beaucoup de documents distincts est un vrai mot.
lexique = {w for w, n in freq.items() if n >= 50}
print('tokens distincts :', len(freq), '| lexique retenu :', len(lexique), flush=True)

scores = []
for f, parts in docs.items():
    toks = TOK.findall(' '.join(parts))
    if len(toks) < 80:
        continue
    couvert = sum(1 for t in toks if t in lexique)
    scores.append((couvert / len(toks), len(toks), f))

scores.sort()
import statistics
print('documents mesurés :', len(scores))
print('couverture médiane : %.3f' % statistics.median(s[0] for s in scores))
for seuil in (0.30, 0.50, 0.65, 0.75):
    print(f'  sous {seuil:.2f} : {sum(1 for s in scores if s[0] < seuil):5d} documents')
print()
print('les 15 pires :')
for c, n, f in scores[:15]:
    print(f'  {c:.3f}  {n:6d} mots  {f[:62]}')
json.dump([{'couverture': c, 'tokens': n, 'file': f} for c, n, f in scores if c < 0.75],
          open('/workspace/qualite_suspects.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('\nsuspects enregistrés dans /workspace/qualite_suspects.json')
