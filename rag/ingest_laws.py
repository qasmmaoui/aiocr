"""
Ingestion du corpus juridique dans Qdrant — robuste et parallèle.
  extract (PyMuPDF, +OCR optionnel) -> chunk -> embed (bge-m3, lots concurrents) -> upsert

- Reprise sur crash : un manifeste des fichiers traités (`laws_ingest_done.json`)
  + un marqueur du fichier en cours (`laws_ingest_current.txt`). Si un fichier
  fait planter le process, il est ignoré au redémarrage suivant.
- Concurrence : plusieurs lots d'embeddings en parallèle (garde le GPU alimenté).

Usage :
  python -m rag.ingest_laws                # natif seulement (rapide)
  INGEST_OCR=1 python -m rag.ingest_laws   # + OCR des pages scannées (lent, GPU)
"""
import sys
import os
import re
import glob
import json
import time
import uuid
import base64
import concurrent.futures as cf
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import fitz  # PyMuPDF

from services.correction_service import light_clean
from services.ocr_service import run_ocr_on_page
from rag.chunker import chunk_text
from rag.embeddings import embed_batch
from rag import store

LAWS_DIR      = os.environ.get("LAWS_DIR", "/workspace/laws/commercial")
COLLECTION    = os.environ.get("LAWS_COLLECTION", "laws_commercial")
DO_OCR        = os.environ.get("INGEST_OCR", "0") == "1"
FORCE_OCR     = os.environ.get("FORCE_OCR", "0") == "1"   # OCR toutes les pages (couche texte cassée)
DONE_FILE     = os.environ.get("LAWS_DONE_FILE", "/workspace/laws_ingest_done.json")
CUR_FILE      = "/workspace/laws_ingest_current.txt"
EMBED_BATCH   = 64
EMBED_WORKERS = 4     # lots d'embeddings simultanés
UPSERT_BATCH  = 256


def law_name(path: str) -> str:
    n = os.path.basename(path)
    n = re.sub(r'^\d+_', '', n)
    n = re.sub(r'-\d{6,}\.pdf$', '', n)
    n = n.replace('.pdf', '').replace('.docx', '')
    return n.strip() or os.path.basename(path)


def extract_text(pdf_path: str) -> str:
    parts: list[str] = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  ! open error: {e}", flush=True)
        return ""
    for page in doc:
        raw = page.get_text()
        has_native = len(re.sub(r'\s+', '', raw)) > 50
        if has_native and not FORCE_OCR:
            parts.append(light_clean(raw.strip()))
        elif DO_OCR or FORCE_OCR:
            try:
                pix = page.get_pixmap(dpi=int(os.environ.get("OCR_DPI", "200")),
                                      colorspace=fitz.csGRAY, alpha=False)
                b64 = base64.b64encode(pix.tobytes("png")).decode()
                parts.append(run_ocr_on_page({"image_b64": b64}))
            except Exception as e:
                print(f"  ! ocr error p{page.number + 1}: {e}", flush=True)
    doc.close()
    return "\n".join(p for p in parts if p)


def _load_done() -> set[str]:
    try:
        return set(json.load(open(DONE_FILE, encoding="utf-8")))
    except Exception:
        return set()


def _save_done(done: set[str]) -> None:
    tmp = DONE_FILE + ".tmp"
    json.dump(sorted(done), open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, DONE_FILE)


def _embed_file(chunks: list[str]) -> list[list[float]]:
    """Embeddings de tous les chunks d'un fichier, par lots concurrents."""
    batches = [chunks[i:i + EMBED_BATCH] for i in range(0, len(chunks), EMBED_BATCH)]
    with cf.ThreadPoolExecutor(max_workers=EMBED_WORKERS) as ex:
        vbatches = list(ex.map(embed_batch, batches))
    return [v for vb in vbatches for v in vb]


def main() -> None:
    pdfs = sorted(glob.glob(os.path.join(LAWS_DIR, "**", "*.pdf"), recursive=True))
    done = _load_done()

    # Reprise : si un fichier était "en cours", il a fait planter le run précédent → on l'ignore.
    if os.path.exists(CUR_FILE):
        crashed = open(CUR_FILE, encoding="utf-8").read().strip()
        if crashed:
            done.add(crashed)
            _save_done(done)
            store.delete_by(COLLECTION, "file", crashed)
            print(f"SKIP crashed-file: {crashed}", flush=True)
        os.remove(CUR_FILE)

    store.ensure_collection(COLLECTION)
    todo = [p for p in pdfs if os.path.basename(p) not in done]
    print(f"INGEST_START total={len(pdfs)} done={len(done)} todo={len(todo)} ocr={DO_OCR}", flush=True)

    t0 = time.time()
    empty = 0
    for k, pdf in enumerate(todo, 1):
        base = os.path.basename(pdf)
        name = law_name(pdf)

        open(CUR_FILE, "w", encoding="utf-8").write(base)   # marqueur "en cours"
        store.delete_by(COLLECTION, "file", base)           # idempotence

        chunks = chunk_text(extract_text(pdf))
        if chunks:
            texts = [c["text"] for c in chunks]
            vecs = _embed_file(texts)
            points = [
                (str(uuid.uuid4()), vecs[i],
                 {"text": chunks[i]["text"], "law": name, "file": base,
                  "chunk": i, "article": chunks[i].get("article")})
                for i in range(len(chunks))
            ]
            for i in range(0, len(points), UPSERT_BATCH):
                store.upsert(COLLECTION, points[i:i + UPSERT_BATCH])
        else:
            empty += 1

        done.add(base)
        _save_done(done)
        if os.path.exists(CUR_FILE):
            os.remove(CUR_FILE)

        print(f"[{k}/{len(todo)}] {name[:52]} -> {len(chunks)} chunks "
              f"(qdrant {store.count(COLLECTION)})", flush=True)

    complete = len(done) >= len(pdfs)
    tag = "INGEST_COMPLETE" if complete else "INGEST_PARTIAL"
    print(f"{tag} done={len(done)}/{len(pdfs)} empty={empty} "
          f"elapsed={time.time() - t0:.0f}s count={store.count(COLLECTION)}", flush=True)


if __name__ == "__main__":
    main()
