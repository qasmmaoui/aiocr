import json, os, sys, uuid
from qdrant_client import QdrantClient
C = {'adala_pdfs':'adala_laws_v4','jurisprudence':'adala_juris_v4','pmp_textes':'adala_pmp_v4'}
cl = QdrantClient(url='http://127.0.0.1:6333', timeout=600)
for corpus, coll in C.items():
    path = f'/workspace/adala_corpus/chunks_v4/{corpus}.jsonl'
    batch, n = [], 0
    for line in open(path, encoding='utf-8'):
        r = json.loads(line); m = r['metadata']
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, r['id']))
        f = m.get('file') or os.path.basename(m.get('pdf') or '')
        batch.append((pid, f))
        if len(batch) >= 2000:
            for fname in set(b[1] for b in batch):
                ids = [b[0] for b in batch if b[1] == fname]
                cl.set_payload(coll, payload={'file': fname}, points=ids, wait=False)
            n += len(batch); batch = []
            if n % 20000 == 0: print(f'{coll} {n}', flush=True)
    if batch:
        for fname in set(b[1] for b in batch):
            ids = [b[0] for b in batch if b[1] == fname]
            cl.set_payload(coll, payload={'file': fname}, points=ids, wait=False)
        n += len(batch)
    print(f'{coll}: {n} payloads patched', flush=True)
print('DONE')
