# -*- coding: utf-8 -*-
"""qwen2.5vl:32b sur EXACTEMENT la page qu'Unlimited-OCR vient de lire."""
import base64
import json
import time
import urllib.request

IMG = "/workspace/uocr_test/2007-265_2005-1-4-68_p1.png"
OUT = "/workspace/uocr_test/qwen_p1.txt"
PROMPT = "استخرج النص العربي الكامل من هذه الصفحة حرفيا، دون تعليق ودون ترجمة."

img = base64.b64encode(open(IMG, "rb").read()).decode()
body = json.dumps({
    "model": "qwen2.5vl:32b",
    "prompt": PROMPT,
    "images": [img],
    "stream": False,
    "options": {"temperature": 0.0, "num_ctx": 8192, "num_predict": 2000},
}).encode()

t0 = time.time()
req = urllib.request.Request("http://127.0.0.1:11434/api/generate", body,
                             {"Content-Type": "application/json"})
out = json.loads(urllib.request.urlopen(req, timeout=1800).read())["response"]
dt = time.time() - t0

open(OUT, "w", encoding="utf-8").write(out)
ar = sum(1 for c in out if "؀" <= c <= "ۿ")
print(f"QWEN {dt:.1f}s {len(out)} caracteres dont {ar} arabes", flush=True)
print(out[:1800], flush=True)
print("CMP_DONE", flush=True)
