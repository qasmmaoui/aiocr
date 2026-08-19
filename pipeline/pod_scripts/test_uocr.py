# -*- coding: utf-8 -*-
"""Test d'Unlimited-OCR (baidu, 3,3 B) sur de l'arabe juridique marocain.

Deux vrais scans de la Chambre 4 SANS couche texte : le cas le plus dur, celui
qui a justifié tout le travail OCR. On compare ensuite mot à mot avec ce que
qwen2.5vl:32b a produit sur les mêmes pages.

L'API exacte de model.infer() n'est pas documentée précisément : on inspecte la
signature au chargement et on n'envoie que les arguments réellement acceptés.
"""
import inspect
import os
import sys
import time

import fitz
import torch
from transformers import AutoModel, AutoTokenizer

MODEL = "baidu/Unlimited-OCR"
OUT = "/workspace/uocr_test"
PDFS = [
    "/workspace/rework/input/juris/Chambre_4/2007-265_2005-1-4-68.pdf",
    "/workspace/rework/input/juris/Chambre_4/2007-359_2006-2-4-1185.pdf",
]
DPI = 200  # même DPI que notre pipeline qwen2.5vl, pour une comparaison honnête


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def render(pdf, page=0):
    doc = fitz.open(pdf)
    pix = doc[page].get_pixmap(dpi=DPI)
    dst = os.path.join(OUT, f"{os.path.basename(pdf)[:-4]}_p{page + 1}.png")
    pix.save(dst)
    doc.close()
    return dst, pix.width, pix.height


def main():
    os.makedirs(OUT, exist_ok=True)
    log(f"GPU : {torch.cuda.get_device_name(0)} · torch {torch.__version__} "
        f"· cuda {torch.version.cuda} · capacité {torch.cuda.get_device_capability(0)}")

    log("chargement du modèle…")
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
    kw = dict(trust_remote_code=True, use_safetensors=True,
              torch_dtype=torch.bfloat16)
    try:
        model = AutoModel.from_pretrained(MODEL, attn_implementation="sdpa", **kw)
    except Exception as e:            # flash-attn absent sur sm_120 : repli eager
        log(f"  sdpa refusé ({type(e).__name__}) — repli sur eager")
        model = AutoModel.from_pretrained(MODEL, attn_implementation="eager", **kw)
    model = model.eval().cuda()
    log(f"  chargé en {time.time() - t0:.0f} s · "
        f"VRAM {torch.cuda.memory_allocated() / 2**30:.1f} Go")

    sig = inspect.signature(model.infer)
    accepted = set(sig.parameters)
    log(f"signature de infer() : {sig}")

    # arguments « gundam » du README, filtrés sur ce que la méthode accepte.
    # output_path n'est pas optionnel malgré son défaut '' : la méthode y écrit.
    wanted = {"base_size": 1024, "image_size": 640, "crop_mode": True,
              "max_length": 32768, "no_repeat_ngram_size": 35,
              "ngram_window": 128, "save_results": False, "test_compress": False,
              "eval_mode": True, "output_path": OUT}
    extra = {k: v for k, v in wanted.items() if k in accepted}
    log(f"arguments retenus : {sorted(extra)}")

    for pdf in PDFS:
        if not os.path.exists(pdf):
            log(f"ABSENT : {pdf}")
            continue
        img, w, h = render(pdf)
        log(f"--- {os.path.basename(pdf)} · page 1 · {w}x{h} px ---")
        t0 = time.time()
        try:
            res = model.infer(tok, prompt="<image>document parsing.",
                              image_file=img, **extra)
        except TypeError as e:
            log(f"  appel refusé : {e} — nouvelle tentative sans extras")
            res = model.infer(tok, prompt="<image>document parsing.",
                              image_file=img)
        dt = time.time() - t0
        text = res if isinstance(res, str) else str(res)
        dst = os.path.join(OUT, os.path.basename(pdf)[:-4] + ".txt")
        open(dst, "w", encoding="utf-8").write(text)
        ar = sum(1 for c in text if "؀" <= c <= "ۿ")
        log(f"  {dt:.1f} s · {len(text)} caractères dont {ar} arabes "
            f"({100 * ar / max(1, len(text)):.0f} %)")
        log("  extrait :\n" + text[:900])
        log(f"  -> {dst}")

    log("UOCR_TEST_DONE")


if __name__ == "__main__":
    sys.exit(main())
