# -*- coding: utf-8 -*-
"""Les م manquants viennent-ils du modèle ou du nombre de pixels ?

Même modèle, même page, même prompt, température 0 : seule la résolution change.
Si 300 DPI corrige الملف/لمهنة, la réponse est « acheter des pixels », pas
« acheter du GPU » — et les pixels sont gratuits.
"""
import base64
import json
import time
import urllib.request

import fitz

PDF = "/workspace/rework/input/juris/Chambre_4/2007-265_2005-1-4-68.pdf"
PROMPT = "استخرج النص العربي الكامل من هذه الصفحة حرفيا، دون تعليق ودون ترجمة."
# mots que qwen a ratés à 200 DPI — le test porte sur eux
WATCH = ["الملف", "لمهنة", "تجبه", "التنبر", "المحكمة", "وزير العدل"]


def ask(img_path):
    img = base64.b64encode(open(img_path, "rb").read()).decode()
    body = json.dumps({
        "model": "qwen2.5vl:32b", "prompt": PROMPT, "images": [img],
        "stream": False,
        "options": {"temperature": 0.0, "num_ctx": 8192, "num_predict": 2000},
    }).encode()
    t0 = time.time()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", body,
                                 {"Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=1800).read())["response"]
    return out, time.time() - t0


doc = fitz.open(PDF)
for dpi in (200, 300, 400):
    pix = doc[0].get_pixmap(dpi=dpi)
    p = f"/workspace/uocr_test/dpi{dpi}.png"
    pix.save(p)
    out, dt = ask(p)
    open(f"/workspace/uocr_test/qwen_dpi{dpi}.txt", "w", encoding="utf-8").write(out)
    hits = [w for w in WATCH if w in out]
    print(f"DPI {dpi} · {pix.width}x{pix.height} · {dt:.1f}s · {len(out)} car. "
          f"· mots corrects {len(hits)}/{len(WATCH)} : {hits}", flush=True)
print("DPI_DONE", flush=True)
