# -*- coding: utf-8 -*-
"""PoC : OCR vision (qwen2.5vl:32b) sur 2 arrêts problématiques -> texte propre."""
import fitz, base64, glob, sys, time, io
sys.path.insert(0, "/workspace/aiocr")
from services.ocr_service import run_ocr_on_page

out = io.open("/workspace/poc/result.txt", "w", encoding="utf-8")
for p in sorted(glob.glob("/workspace/poc/*.pdf")):
    d = fitz.open(p)
    out.write(f"\n===== {p.split('/')[-1]} ({d.page_count} pages) =====\n")
    t0 = time.time()
    for i in range(min(2, d.page_count)):          # 2 premières pages par arrêt
        pix = d[i].get_pixmap(dpi=200, colorspace=fitz.csGRAY, alpha=False)
        b64 = base64.b64encode(pix.tobytes("png")).decode()
        txt = run_ocr_on_page({"image_b64": b64})
        out.write(f"--- page {i+1} ({time.time()-t0:.0f}s) ---\n{txt}\n")
    d.close()
out.close()
print("POC_DONE")
