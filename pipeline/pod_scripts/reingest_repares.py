# -*- coding: utf-8 -*-
"""Ré-indexation des documents dont l'extraction a été refaite.

On ne remplace que ceux qui progressent réellement : si la nouvelle extraction
n'atteint pas le seuil de qualité, on garde l'ancienne plutôt que d'échanger un
défaut contre un autre.
"""
import json, re, sys, uuid
sys.path.insert(0, '/workspace/aiocr')
from rag import store
from rag.chunker import chunk_text
from rag.embeddings import embed_batch
from qdrant_client.http.models import FieldCondition, Filter, MatchValue, PointStruct

CORPUS = '/workspace/data/laws_corpus_v2.jsonl'
SEUIL = 0.75
client = store.client()

repares = {}
for line in open('/workspace/reocr_out.jsonl', encoding='utf-8'):
    try: r = json.loads(line)
    except Exception: continue
    if r['couverture'] >= SEUIL:
        repares[r['file']] = r
print('documents à remplacer :', len(repares), flush=True)

# métadonnées d'origine, pour ne rien perdre du contexte d'indexation
meta = {}
for line in open(CORPUS, encoding='utf-8'):
    r = json.loads(line)
    f = r.get('file') or ''
    if f in repares and f not in meta:
        meta[f] = r

kept = [l for l in open(CORPUS, encoding='utf-8')
        if (json.loads(l).get('file') or '') not in repares]
nouvelles = []
for i, (name, rep) in enumerate(repares.items(), 1):
    m = meta.get(name, {})
    col = m.get('collection') or 'adala_juris_v4'
    pages = rep['pages']
    full = '\n'.join(pages)
    offsets, pos = [], 0
    for t in pages:
        offsets.append(pos); pos += len(t) + 1
    def page_of(idx):
        lo = 0
        for k, off in enumerate(offsets):
            if off <= idx: lo = k
            else: break
        return lo + 1
    flt = Filter(must=[FieldCondition(key='file', match=MatchValue(value=name))])
    ancien = None
    for c in ('adala_juris_v4', 'adala_laws_v4', 'adala_pmp_v4'):
        pts, _ = client.scroll(c, scroll_filter=flt, limit=1, with_payload=True)
        if pts:
            ancien = (c, pts[0].payload); break
    if ancien is None:
        continue
    col, pl = ancien
    client.delete(col, points_selector=flt)
    chunks = chunk_text(full)
    cursor, recs = 0, []
    for j, ch in enumerate(chunks):
        at = full.find(ch['text'][:60], cursor)
        if at >= 0: cursor = at
        recs.append({'text': ch['text'], 'article': ch.get('article'),
                     'chunk': j, 'page': page_of(cursor if at >= 0 else 0)})
    vecs = []
    for k in range(0, len(recs), 64):
        vecs.extend(embed_batch([r['text'] for r in recs[k:k+64]]))
    pts = [PointStruct(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f'{name}|{r["chunk"]}')), vector=v,
        payload={**pl, 'text': r['text'], 'article': r['article'],
                 'chunk': str(r['chunk']), 'n_chunks': str(len(recs)),
                 'page': str(r['page']), 'page_end': str(r['page']),
                 'pages': str(len(pages)), 'method': 'reocr_' + rep['method'],
                 'ocr_hit_rate': str(rep['couverture'])})
        for r, v in zip(recs, vecs)]
    for k in range(0, len(pts), 128):
        client.upsert(col, points=pts[k:k+128], wait=True)
    for r in recs:
        nouvelles.append(json.dumps({
            'collection': col, 'file': name, 'chunk': r['chunk'],
            'law': m.get('law'), 'article': r['article'], 'text': r['text'],
            'page': r['page'], 'status': m.get('status', 'current')},
            ensure_ascii=False))
    if i % 25 == 0: print(f'  {i}/{len(repares)}', flush=True)

with open(CORPUS, 'w', encoding='utf-8') as f:
    f.writelines(kept)
    f.write('\n'.join(nouvelles) + '\n')
print('remplacés :', len(repares), '| fragments réécrits :', len(nouvelles))
