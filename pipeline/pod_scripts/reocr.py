# -*- coding: utf-8 -*-
"""Ré-océrisation des documents dont l'extraction est corrompue.

On teste TROIS voies pour chaque document et on garde la meilleure, mesurée
au même lexique que le contrôle qualité :
  - la couche texte du PDF (parfois saine, comme le décret 2.19.644) ;
  - l'OCR arabe à 300 dpi ;
  - l'OCR arabe+français, pour les textes bilingues.
Aucune supposition : on compare et on choisit.
"""
import json, os, re, subprocess, sys, tempfile
import fitz

TOK = re.compile(r'[؀-ۿ]{3,}')
LEX = set(json.load(open('/workspace/lexique.json', encoding='utf-8')))

def couverture(t):
    toks = TOK.findall(t)
    if len(toks) < 20: return 0.0
    return sum(1 for x in toks if x in LEX) / len(toks)

def ocr(path, lang):
    doc = fitz.open(path); out = []
    env = dict(os.environ, OMP_THREAD_LIMIT='1')
    with tempfile.TemporaryDirectory() as td:
        img, base = td + '/p.png', td + '/p'
        for page in doc:
            page.get_pixmap(dpi=300).save(img)
            subprocess.run(['tesseract', img, base, '-l', lang, '--psm', '6'],
                           env=env, capture_output=True, timeout=600)
            try: out.append(open(base + '.txt', encoding='utf-8').read())
            except FileNotFoundError: out.append('')
    doc.close(); return out

name, path = sys.argv[1], sys.argv[2]
doc = fitz.open(path); brut = [p.get_text() or '' for p in doc]; doc.close()
cands = [('texte', brut)]
for lang in ('ara', 'ara+fra'):
    try: cands.append((lang, ocr(path, lang)))
    except Exception: pass
best = max(cands, key=lambda c: couverture('\n'.join(c[1])))
print(json.dumps({'file': name, 'method': best[0],
                  'couverture': round(couverture('\n'.join(best[1])), 3),
                  'pages': best[1]}, ensure_ascii=False))
