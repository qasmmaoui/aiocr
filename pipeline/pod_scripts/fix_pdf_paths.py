import json, os, glob, uuid
from qdrant_client import QdrantClient
# index basename -> chemin réel, sur TOUTES les racines PDF du volume
roots = ['/workspace/rework/input', '/workspace/laws']
idx = {}
for r in roots:
    for p in glob.glob(os.path.join(r, '**', '*.pdf'), recursive=True):
        idx.setdefault(os.path.basename(p), p)
print('pdf index:', len(idx), 'basenames', flush=True)
cl = QdrantClient(url='http://127.0.0.1:6333', timeout=600)
C = {'adala_pdfs':'adala_laws_v4','jurisprudence':'adala_juris_v4','pmp_textes':'adala_pmp_v4'}
for corpus, coll in C.items():
    fixed = missing = 0
    updates = {}
    src = f'/workspace/adala_corpus/chunks_v4/{corpus}.jsonl'
    out_lines = []
    for line in open(src, encoding='utf-8'):
        r = json.loads(line); m = r['metadata']; p = m.get('pdf') or ''
        if p and not os.path.exists('/workspace/' + p):
            real = idx.get(os.path.basename(p))
            if real:
                newp = os.path.relpath(real, '/workspace')
                m['pdf'] = newp
                updates.setdefault(newp, []).append(str(uuid.uuid5(uuid.NAMESPACE_URL, r['id'])))
                fixed += 1
            else:
                missing += 1
        out_lines.append(json.dumps(r, ensure_ascii=False))
    if fixed:
        open(src, 'w', encoding='utf-8').write('\n'.join(out_lines) + '\n')
        for newp, ids in updates.items():
            for i in range(0, len(ids), 500):
                cl.set_payload(coll, payload={'pdf': newp}, points=ids[i:i+500], wait=False)
    print(f'{corpus}: {fixed} chemins corrigés, {missing} introuvables', flush=True)
print('DONE')
